#!/usr/bin/env python3
"""Verify an existing Fragmenter Tellipatch phase 1+2 output ISO."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Iterable

from iso9660 import Iso9660, IsoEntry, SECTOR_USER
from iso_patch_engine import read_extent_range
from tellipatch_native import (
    ORIGINAL_ISO_MD5,
    PreparedPatch,
    Progress,
    TellipatchError,
    TextWrite,
    _notify,
    _verify_text_writes,
    prepare_translation,
)
from vcdiff_decoder import VcdiffError, iter_decode_vcdiff

VERIFY_CHUNK = 4 * 1024 * 1024


def _overlay_text_writes(
    window: bytearray,
    *,
    window_offset: int,
    writes: list[TextWrite],
) -> None:
    """Apply final CSV writes that intersect one decoded binary-patch window."""
    window_end = window_offset + len(window)
    for write in writes:
        write_end = write.offset + len(write.replacement)
        overlap_start = max(window_offset, write.offset)
        overlap_end = min(window_end, write_end)
        if overlap_start >= overlap_end:
            continue
        source_start = overlap_start - write.offset
        target_start = overlap_start - window_offset
        size = overlap_end - overlap_start
        window[target_start : target_start + size] = write.replacement[
            source_start : source_start + size
        ]


def _physical_interval(
    iso: Any,
    entry: IsoEntry,
    logical_offset: int,
    length: int,
) -> tuple[int, int]:
    if iso.sector_size != SECTOR_USER or iso.data_offset != 0:
        raise TellipatchError(
            "Unexpected ISO geometry while calculating verification ranges."
        )
    start = (
        (entry.lba + iso.lba_offset) * iso.sector_size
        + iso.data_offset
        + logical_offset
    )
    return start, start + length


def _merge_intervals(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if start < 0 or end < start:
            raise TellipatchError("Invalid allowed-change range during verification.")
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _allowed_change_intervals(
    iso: Any,
    binary: Iterable[PreparedPatch],
    writes: Iterable[TextWrite],
) -> list[tuple[int, int]]:
    intervals: list[tuple[int, int]] = []
    binary_paths: set[str] = set()
    for item in binary:
        binary_paths.add(item.entry.path)
        intervals.append(_physical_interval(iso, item.entry, 0, item.entry.size))
    for write in writes:
        if write.entry.path in binary_paths:
            continue
        intervals.append(
            _physical_interval(
                iso,
                write.entry,
                write.offset,
                len(write.replacement),
            )
        )
    return _merge_intervals(intervals)


def _first_difference(left: bytes, right: bytes) -> int:
    for index, (left_byte, right_byte) in enumerate(zip(left, right)):
        if left_byte != right_byte:
            return index
    return min(len(left), len(right))


def _verify_no_unexpected_changes(
    source: Path,
    output: Path,
    allowed: list[tuple[int, int]],
    progress: Progress | None,
) -> tuple[str, str]:
    """Hash both images and reject changes outside the declared patch ranges."""
    total = source.stat().st_size
    source_digest = hashlib.sha256()
    output_digest = hashlib.sha256()
    processed = 0
    interval_index = 0

    with source.open("rb") as source_handle, output.open("rb") as output_handle:
        while processed < total:
            take = min(VERIFY_CHUNK, total - processed)
            source_chunk = source_handle.read(take)
            output_chunk = output_handle.read(take)
            if len(source_chunk) != take or len(output_chunk) != take:
                raise TellipatchError("Short read while verifying the complete output ISO.")
            source_digest.update(source_chunk)
            output_digest.update(output_chunk)

            chunk_start = processed
            chunk_end = processed + take
            while interval_index < len(allowed) and allowed[interval_index][1] <= chunk_start:
                interval_index += 1

            cursor = chunk_start
            scan_index = interval_index
            while scan_index < len(allowed) and allowed[scan_index][0] < chunk_end:
                allowed_start, allowed_end = allowed[scan_index]
                compare_end = min(allowed_start, chunk_end)
                if cursor < compare_end:
                    local_start = cursor - chunk_start
                    local_end = compare_end - chunk_start
                    left = source_chunk[local_start:local_end]
                    right = output_chunk[local_start:local_end]
                    if left != right:
                        delta = _first_difference(left, right)
                        raise TellipatchError(
                            "English output contains an unexpected change at physical ISO "
                            f"offset 0x{cursor + delta:X}."
                        )
                cursor = max(cursor, min(allowed_end, chunk_end))
                scan_index += 1

            if cursor < chunk_end:
                local_start = cursor - chunk_start
                left = source_chunk[local_start:]
                right = output_chunk[local_start:]
                if left != right:
                    delta = _first_difference(left, right)
                    raise TellipatchError(
                        "English output contains an unexpected change at physical ISO "
                        f"offset 0x{cursor + delta:X}."
                    )

            processed = chunk_end
            _notify(
                progress,
                "verify-image",
                processed,
                total,
                f"Checked complete ISO integrity: {processed:,}/{total:,} bytes",
            )

    return source_digest.hexdigest(), output_digest.hexdigest()


def verify_english_iso(
    source_iso: str | Path,
    output_iso: str | Path,
    *,
    patch_zip: str | Path | None = None,
    translation_csv_gz: str | Path | None = None,
    expected_md5: str | None = ORIGINAL_ISO_MD5,
    iso_factory: Callable[[Path], Any] = Iso9660,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Verify all intended changes and reject any unrelated output corruption."""
    source = Path(source_iso).expanduser().resolve()
    output = Path(output_iso).expanduser().resolve()
    if output == source:
        raise TellipatchError("Output ISO must be separate from the original ISO.")
    if not source.is_file():
        raise TellipatchError(f"Original ISO was not found: {source}")
    if not output.is_file():
        raise TellipatchError(f"English output ISO was not found: {output}")
    if source.stat().st_size != output.stat().st_size:
        raise TellipatchError(
            "English output ISO size differs from the supported original ISO "
            f"({output.stat().st_size:,} != {source.stat().st_size:,})."
        )

    iso, binary, writes, report = prepare_translation(
        source,
        patch_zip=patch_zip,
        translation_csv_gz=translation_csv_gz,
        expected_md5=expected_md5,
        iso_factory=iso_factory,
        progress=progress,
    )
    writes_by_entry: dict[str, list[TextWrite]] = {}
    for write in writes:
        writes_by_entry.setdefault(write.entry.path, []).append(write)

    _notify(progress, "verify-binary", 0, len(binary), "Verifying translated ISO binary patches")
    with source.open("rb") as source_handle, output.open("rb") as output_handle:
        for item_index, item in enumerate(binary, start=1):
            target_offset = 0

            def read_source(
                position: int,
                length: int,
                *,
                entry: IsoEntry = item.entry,
            ) -> bytes:
                return read_extent_range(source_handle, iso, entry, position, length)

            try:
                for offset, decoded in iter_decode_vcdiff(
                    item.patch,
                    item.entry.size,
                    read_source,
                ):
                    expected = bytearray(decoded)
                    _overlay_text_writes(
                        expected,
                        window_offset=offset,
                        writes=writes_by_entry.get(item.entry.path, []),
                    )
                    actual = read_extent_range(
                        output_handle,
                        iso,
                        item.entry,
                        offset,
                        len(expected),
                    )
                    if actual != expected:
                        raise TellipatchError(
                            f"English output verification failed for {item.internal_path} "
                            f"at file offset 0x{offset:X}."
                        )
                    target_offset = offset + len(expected)
            except VcdiffError as exc:
                raise TellipatchError(
                    f"Could not verify {item.asset_name}: {exc}"
                ) from exc
            if target_offset != item.entry.size:
                raise TellipatchError(
                    f"{item.asset_name} produced an incomplete verification target."
                )
            _notify(
                progress,
                "verify-binary",
                item_index,
                len(binary),
                f"Verified {item.internal_path}",
            )

    _notify(progress, "verify-text", 0, 1, "Verifying final translated text")
    _verify_text_writes(output, iso, writes)
    _notify(progress, "verify-text", 1, 1, "Translated text verified")

    allowed = _allowed_change_intervals(iso, binary, writes)
    _notify(progress, "verify-image", 0, source.stat().st_size, "Checking for unexpected ISO changes")
    source_sha256, output_sha256 = _verify_no_unexpected_changes(
        source,
        output,
        allowed,
        progress,
    )
    if output_sha256 == source_sha256:
        raise TellipatchError("English output ISO is byte-identical to the original ISO.")

    report["status"] = "verified"
    report["output"] = {
        "path": str(output),
        "size": output.stat().st_size,
        "sha256": output_sha256,
    }
    report["verification"] = {
        "binary_targets": len(binary),
        "translated_rows": len(writes),
        "allowed_change_ranges": len(allowed),
        "unexpected_changes": 0,
        "source_sha256": source_sha256,
        "visual_phase_3_included": False,
    }
    _notify(progress, "verify", 1, 1, "English Phase 1+2 Preview verified")
    return report

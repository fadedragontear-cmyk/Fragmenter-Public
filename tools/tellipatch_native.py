#!/usr/bin/env python3
"""Apply the verified Tellipatch v3.8 data and English text patches natively.

This intentionally implements Tellipatch phases 1 and 2 only.  The separate
legacy visual-patcher phase is not represented by the supplied resources and
is never silently claimed as complete.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import sys
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660, IsoEntry, SECTOR_USER  # noqa: E402
from iso_patch_engine import read_extent_range, sha256_file, write_extent_range  # noqa: E402
from vcdiff_decoder import VcdiffError, inspect_vcdiff, iter_decode_vcdiff  # noqa: E402


ORIGINAL_ISO_MD5 = "94c82040bf4bb99500eb557a3c0fbb15"
PATCH_RESOURCE = "Tellipatch-v3.8-patches.zip"
PATCH_RESOURCE_SHA256 = "9ae767029f7c1c724ceaaf62882fd36f10e34e254d70e26761b747558c7b9eb9"
CSV_RESOURCE = "Tellipatch-gamelines.csv.gz"
CSV_RESOURCE_SHA256 = "b6dacbab4b6e10829b81821ab62cde69f9f1cfe60116d4a2a7ead7dd0739c56d"
CSV_RAW_SHA256 = "8be9895ae5a53442f66874debd3fcd3b3607e94f40d3c3bc46cd79f0b26244ab"
REQUIRED_COLUMNS = {
    "FILE",
    "OFFSET",
    "LENGTH",
    "TRANSLATED_TEXT",
    "STATUS",
}
EXPECTED_PATCH_TARGETS = {
    "DATA.BIN.xdelta": "DATA/DATA.BIN",
    "GCMNF.PRG.xdelta": "DATA/GCMNF.PRG",
    "GCMNO.PRG.xdelta": "DATA/GCMNO.PRG",
    "HACK_00.ELF.xdelta": "HACK_00.ELF",
    "HACK_01.ELF.xdelta": "HACK_01.ELF",
    "MATCHING.PRG.xdelta": "DATA/MATCHING.PRG",
    "SYSTEM.CNF.xdelta": "SYSTEM.CNF",
}
Progress = Callable[[str, int, int, str], None]


class TellipatchError(RuntimeError):
    """Raised when a source, patch asset, or output fails a safety check."""


@dataclass(frozen=True)
class TextWrite:
    file_key: str
    entry: IsoEntry
    offset: int
    length: int
    replacement: bytes
    row_number: int


@dataclass(frozen=True)
class PreparedPatch:
    asset_name: str
    internal_path: str
    entry: IsoEntry
    patch: bytes
    windows: int


def _resource_path(name: str) -> Path:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "resources" / name)
    candidates.append(TOOLS_DIR.parent / "resources" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise TellipatchError(f"Bundled translation resource is missing: {name}")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _notify(progress: Progress | None, stage: str, current: int, total: int, message: str) -> None:
    if progress is not None:
        progress(stage, current, total, message)


def _read_assets(
    patch_zip: str | Path | None,
    translation_csv_gz: str | Path | None,
) -> tuple[dict[str, bytes], bytes, dict[str, str]]:
    patch_path = Path(patch_zip) if patch_zip else _resource_path(PATCH_RESOURCE)
    csv_path = Path(translation_csv_gz) if translation_csv_gz else _resource_path(CSV_RESOURCE)
    if not patch_path.is_file() or not csv_path.is_file():
        raise TellipatchError("Translation resources were not found.")
    patch_hash = sha256_file(patch_path)
    csv_gz_hash = sha256_file(csv_path)
    if patch_zip is None and patch_hash != PATCH_RESOURCE_SHA256:
        raise TellipatchError("Bundled Tellipatch patch archive failed its integrity check.")
    if translation_csv_gz is None and csv_gz_hash != CSV_RESOURCE_SHA256:
        raise TellipatchError("Bundled translation CSV failed its integrity check.")
    try:
        with zipfile.ZipFile(patch_path) as archive:
            names = set(archive.namelist())
            if names != set(EXPECTED_PATCH_TARGETS):
                missing = sorted(set(EXPECTED_PATCH_TARGETS) - names)
                extra = sorted(names - set(EXPECTED_PATCH_TARGETS))
                raise TellipatchError(
                    f"Patch archive contents differ from v3.8 (missing={missing}, extra={extra})."
                )
            patches = {name: archive.read(name) for name in EXPECTED_PATCH_TARGETS}
        with gzip.open(csv_path, "rb") as compressed:
            csv_bytes = compressed.read()
    except (OSError, zipfile.BadZipFile) as exc:
        raise TellipatchError(f"Could not read translation resources: {exc}") from exc
    if translation_csv_gz is None and _sha256_bytes(csv_bytes) != CSV_RAW_SHA256:
        raise TellipatchError("Decompressed translation CSV failed its integrity check.")
    return patches, csv_bytes, {
        "patch_archive_sha256": patch_hash,
        "translation_csv_gzip_sha256": csv_gz_hash,
        "translation_csv_sha256": _sha256_bytes(csv_bytes),
    }


def _unique_entries_by_name(index: dict[str, IsoEntry]) -> dict[str, IsoEntry]:
    groups: dict[str, list[IsoEntry]] = {}
    for entry in index.values():
        path = Path(entry.path)
        for key in {path.name.casefold(), path.stem.casefold()}:
            groups.setdefault(key, []).append(entry)
    return {key: values[0] for key, values in groups.items() if len(values) == 1}


def _prepare_binary_patches(
    patches: dict[str, bytes], index: dict[str, IsoEntry]
) -> list[PreparedPatch]:
    prepared: list[PreparedPatch] = []
    for asset_name, internal_path in EXPECTED_PATCH_TARGETS.items():
        entry = index.get(internal_path.casefold())
        if entry is None:
            raise TellipatchError(f"Original ISO file was not found: {internal_path}")
        try:
            info = inspect_vcdiff(patches[asset_name])
        except VcdiffError as exc:
            raise TellipatchError(f"Invalid {asset_name}: {exc}") from exc
        if info.target_size != entry.size:
            raise TellipatchError(
                f"{asset_name} produces {info.target_size:,} bytes, but {internal_path} "
                f"is {entry.size:,} bytes. This is not the supported original disc."
            )
        prepared.append(
            PreparedPatch(asset_name, internal_path, entry, patches[asset_name], len(info.windows))
        )
    return prepared


def _prepare_text_writes(csv_bytes: bytes, index: dict[str, IsoEntry]) -> list[TextWrite]:
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TellipatchError(f"Translation CSV is not UTF-8: {exc}") from exc
    reader = csv.DictReader(text.splitlines(keepends=True))
    columns = set(reader.fieldnames or ())
    if not REQUIRED_COLUMNS.issubset(columns):
        raise TellipatchError(
            "Translation CSV is missing columns: "
            + ", ".join(sorted(REQUIRED_COLUMNS - columns))
        )
    by_name = _unique_entries_by_name(index)
    writes: list[TextWrite] = []
    for row_number, row in enumerate(reader, start=2):
        if str(row.get("STATUS") or "").strip().casefold() != "translated":
            continue
        file_key = str(row.get("FILE") or "").strip()
        entry = by_name.get(file_key.casefold())
        if entry is None:
            raise TellipatchError(
                f"CSV row {row_number}: ISO file key {file_key!r} is missing or ambiguous."
            )
        try:
            offset = int(str(row.get("OFFSET") or ""), 10)
            length = int(str(row.get("LENGTH") or ""), 10)
        except ValueError as exc:
            raise TellipatchError(f"CSV row {row_number}: invalid OFFSET or LENGTH.") from exc
        if offset < 0 or length <= 0 or offset + length > entry.size:
            raise TellipatchError(
                f"CSV row {row_number}: write exceeds {entry.path} ({offset}+{length})."
            )
        translated = row.get("TRANSLATED_TEXT")
        if translated is None:
            translated = ""
        if "\x00" in translated:
            raise TellipatchError(f"CSV row {row_number}: translation contains a NUL byte.")
        try:
            encoded = translated.encode("cp932")
        except UnicodeEncodeError as exc:
            raise TellipatchError(f"CSV row {row_number}: text is not CP932 encodable.") from exc
        if len(encoded) > length:
            raise TellipatchError(
                f"CSV row {row_number}: translation needs {len(encoded)} bytes but has {length}."
            )
        writes.append(
            TextWrite(
                file_key=file_key,
                entry=entry,
                offset=offset,
                length=length,
                replacement=encoded + bytes(length - len(encoded)),
                row_number=row_number,
            )
        )
    if not writes:
        raise TellipatchError("Translation CSV contains no Translated rows.")
    return writes


def prepare_translation(
    source_iso: str | Path,
    *,
    patch_zip: str | Path | None = None,
    translation_csv_gz: str | Path | None = None,
    expected_md5: str | None = ORIGINAL_ISO_MD5,
    iso_factory: Callable[[Path], Any] = Iso9660,
    progress: Progress | None = None,
) -> tuple[Any, list[PreparedPatch], list[TextWrite], dict[str, Any]]:
    source = Path(source_iso).expanduser().resolve()
    if not source.is_file():
        raise TellipatchError(f"Original ISO was not found: {source}")
    _notify(progress, "source", 0, 1, "Verifying original ISO")
    actual_md5 = _hash_file(source, "md5")
    if expected_md5 and actual_md5.casefold() != expected_md5.casefold():
        raise TellipatchError(
            "Original ISO MD5 mismatch. Use an unmodified Japanese .hack//Fragment ISO "
            f"(expected {expected_md5}, found {actual_md5})."
        )
    patches, csv_bytes, assets_report = _read_assets(patch_zip, translation_csv_gz)
    try:
        iso = iso_factory(source).open()
        if iso.sector_size != SECTOR_USER or iso.data_offset != 0:
            raise TellipatchError(
                "Translation currently accepts only a standard 2048-byte-sector ISO, not raw BIN."
            )
        index = iso.build_index()
    except TellipatchError:
        raise
    except (OSError, ValueError) as exc:
        raise TellipatchError(f"Could not read the source ISO filesystem: {exc}") from exc
    binary = _prepare_binary_patches(patches, index)
    text_writes = _prepare_text_writes(csv_bytes, index)
    report = {
        "status": "validated",
        "scope": "Tellipatch v3.8 phase 1 + phase 2",
        "visual_phase_3_included": False,
        "source": {
            "path": str(source),
            "size": source.stat().st_size,
            "md5": actual_md5,
        },
        "resources": assets_report,
        "binary_patches": [
            {
                "asset": item.asset_name,
                "path": item.internal_path,
                "bytes": item.entry.size,
                "windows": item.windows,
            }
            for item in binary
        ],
        "translated_rows": len(text_writes),
        "output": None,
    }
    _notify(progress, "source", 1, 1, "Original ISO and translation resources verified")
    return iso, binary, text_writes, report


def _apply_binary_patches(
    source: Path,
    output: Path,
    iso: Any,
    patches: Iterable[PreparedPatch],
    progress: Progress | None,
) -> None:
    items = list(patches)
    with source.open("rb") as source_handle, output.open("r+b") as output_handle:
        for item_index, item in enumerate(items, start=1):
            target_offset = 0

            def read_source(position: int, length: int, *, entry: IsoEntry = item.entry) -> bytes:
                return read_extent_range(source_handle, iso, entry, position, length)

            try:
                for window_index, (offset, window) in enumerate(
                    iter_decode_vcdiff(item.patch, item.entry.size, read_source), start=1
                ):
                    write_extent_range(output_handle, iso, item.entry, offset, window)
                    target_offset = offset + len(window)
                    _notify(
                        progress,
                        "binary",
                        item_index - 1,
                        len(items),
                        f"{item.internal_path}: window {window_index}/{item.windows}",
                    )
            except VcdiffError as exc:
                raise TellipatchError(f"Could not apply {item.asset_name}: {exc}") from exc
            if target_offset != item.entry.size:
                raise TellipatchError(f"{item.asset_name} produced an incomplete target file.")
            _notify(progress, "binary", item_index, len(items), f"Patched {item.internal_path}")
        output_handle.flush()
        os.fsync(output_handle.fileno())


def _apply_text_writes(
    output: Path,
    iso: Any,
    writes: list[TextWrite],
    progress: Progress | None,
) -> None:
    with output.open("r+b") as handle:
        for index, write in enumerate(writes, start=1):
            # CSV order is intentional. It reproduces the original patcher's
            # last-write-wins behavior for the one known overlapping pair.
            write_extent_range(handle, iso, write.entry, write.offset, write.replacement)
            if index == len(writes) or index % 250 == 0:
                _notify(progress, "text", index, len(writes), f"Applied {index:,} translated lines")
        handle.flush()
        os.fsync(handle.fileno())


def _verify_text_writes(output: Path, iso: Any, writes: list[TextWrite]) -> None:
    # Build the final expected byte map so overlapping rows verify with the same
    # last-write-wins semantics used during application.
    expected: dict[tuple[str, int], int] = {}
    entries: dict[str, IsoEntry] = {}
    for write in writes:
        entries[write.entry.path] = write.entry
        for delta, value in enumerate(write.replacement):
            expected[(write.entry.path, write.offset + delta)] = value
    by_entry: dict[str, list[tuple[int, int]]] = {}
    for (entry_path, offset), value in expected.items():
        by_entry.setdefault(entry_path, []).append((offset, value))
    with output.open("rb") as handle:
        for entry_path, positions in by_entry.items():
            positions.sort()
            start = previous = positions[0][0]
            values = bytearray((positions[0][1],))
            for offset, value in positions[1:]:
                if offset == previous + 1:
                    values.append(value)
                else:
                    actual = read_extent_range(handle, iso, entries[entry_path], start, len(values))
                    if actual != values:
                        raise TellipatchError(f"Output text verification failed for {entry_path}.")
                    start = offset
                    values = bytearray((value,))
                previous = offset
            actual = read_extent_range(handle, iso, entries[entry_path], start, len(values))
            if actual != values:
                raise TellipatchError(f"Output text verification failed for {entry_path}.")


def build_english_iso(
    source_iso: str | Path,
    output_iso: str | Path,
    *,
    overwrite: bool = False,
    patch_zip: str | Path | None = None,
    translation_csv_gz: str | Path | None = None,
    expected_md5: str | None = ORIGINAL_ISO_MD5,
    iso_factory: Callable[[Path], Any] = Iso9660,
    progress: Progress | None = None,
) -> dict[str, Any]:
    source = Path(source_iso).expanduser().resolve()
    output = Path(output_iso).expanduser().resolve()
    if output == source:
        raise TellipatchError("Output ISO must be separate from the original ISO.")
    if output.exists() and not overwrite:
        raise TellipatchError(f"Output already exists: {output}")
    iso, binary, writes, report = prepare_translation(
        source,
        patch_zip=patch_zip,
        translation_csv_gz=translation_csv_gz,
        expected_md5=expected_md5,
        iso_factory=iso_factory,
        progress=progress,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.fragmenter.tmp")
    try:
        _notify(progress, "copy", 0, 1, "Copying original ISO to a temporary output")
        shutil.copy2(source, temporary)
        _notify(progress, "copy", 1, 1, "Original ISO copied")
        _apply_binary_patches(source, temporary, iso, binary, progress)
        _apply_text_writes(temporary, iso, writes, progress)
        _notify(progress, "verify", 0, 1, "Verifying final translated text")
        _verify_text_writes(temporary, iso, writes)
        os.replace(temporary, output)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    report["status"] = "applied"
    report["output"] = {
        "path": str(output),
        "size": output.stat().st_size,
        "sha256": sha256_file(output),
    }
    _notify(progress, "verify", 1, 1, "English ISO created and verified")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.analyze:
            _iso, _binary, _writes, report = prepare_translation(args.source_iso)
        else:
            if args.out is None:
                parser.error("--out is required unless --analyze is used")
            report = build_english_iso(args.source_iso, args.out, overwrite=args.overwrite)
    except (OSError, TellipatchError) as exc:
        print(f"Translation refused: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

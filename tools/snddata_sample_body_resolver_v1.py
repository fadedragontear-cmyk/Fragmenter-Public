#!/usr/bin/env python3
"""Resolve detached SNDDATA sample bodies hidden after nested SCEI resources.

The resolver is deliberately conservative. It only scans when the currently
selected body base is a complete SCEI sequence-resource header. Stream offsets
and span lengths remain authoritative; one aligned shift must make every
retained block in every bank entry valid PlayStation ADPCM.
"""
from __future__ import annotations

import struct
from typing import Any, Callable, Iterable

BLOCK_SIZE = 16
SEPARATOR = b"\x00\x07" + b"\x77" * 14
VERS_TAGS = (b"IECSsreV", b"SCEIVers")
SEQU_TAGS = (b"IECSuqeS", b"SCEISequ")
MIDI_TAGS = (b"IECSidiM", b"SCEIMidi")
SEQUENCE_TYPE = 1
MAX_TOP_CANDIDATES = 24
PROBE_BLOCKS_PER_EDGE = 4
_COEF_COUNT = 5


def is_nested_sequence_resource(source: bytes, offset: int) -> bool:
    if offset < 0 or offset + 64 > len(source):
        return False
    return (
        source[offset : offset + 8] in VERS_TAGS
        and struct.unpack_from("<H", source, offset + 14)[0] == SEQUENCE_TYPE
        and source[offset + 16 : offset + 24] in SEQU_TAGS
        and source[offset + 48 : offset + 56] in MIDI_TAGS
    )


def _valid_block(block: bytes) -> bool:
    return (
        len(block) == BLOCK_SIZE
        and (block[0] >> 4) < _COEF_COUNT
        and (block[0] & 0x0F) <= 12
    )


def _entry_rows(entries: Iterable[Any], secondary_size: int) -> list[dict[str, int]]:
    entries = list(entries)
    offsets = sorted({int(entry.stream_offset) for entry in entries})
    rows: list[dict[str, int]] = []
    for entry in entries:
        stream_offset = int(entry.stream_offset)
        next_offsets = [value for value in offsets if value > stream_offset]
        stream_end = next_offsets[0] if next_offsets else secondary_size
        raw_size = stream_end - stream_offset
        if raw_size <= 0:
            raise ValueError(
                f"SCEIVagi stream {getattr(entry, 'index', '?')} has non-positive span {raw_size}"
            )
        rows.append(
            {
                "sample_index": int(getattr(entry, "index", len(rows))),
                "stream_offset": stream_offset,
                "raw_span_size": raw_size,
            }
        )
    return rows


def _row_span(
    source: bytes,
    body_base: int,
    shift: int,
    row: dict[str, int],
) -> bytes | None:
    start = body_base + shift + int(row["stream_offset"])
    end = start + int(row["raw_span_size"])
    if start < 0 or end > len(source):
        return None
    return source[start:end]


def _probe_shift(
    source: bytes,
    body_base: int,
    shift: int,
    rows: list[dict[str, int]],
) -> dict[str, Any]:
    leading_zero_rows = 0
    trailing_separator_rows = 0
    valid_probe_blocks = 0
    probe_blocks = 0
    out_of_bounds_rows = 0
    nested_header_rows = 0

    for row in rows:
        raw = _row_span(source, body_base, shift, row)
        if raw is None:
            out_of_bounds_rows += 1
            continue
        nested_header_rows += int(raw[:8] in VERS_TAGS)
        leading_zero = len(raw) >= BLOCK_SIZE and raw[:BLOCK_SIZE] == b"\x00" * BLOCK_SIZE
        trailing_separator = len(raw) >= BLOCK_SIZE and raw[-BLOCK_SIZE:] == SEPARATOR
        leading_zero_rows += int(leading_zero)
        trailing_separator_rows += int(trailing_separator)

        start = BLOCK_SIZE if leading_zero else 0
        end = len(raw) - BLOCK_SIZE if trailing_separator else len(raw)
        aligned_end = end - (end % BLOCK_SIZE)
        front = range(
            start,
            min(aligned_end, start + PROBE_BLOCKS_PER_EDGE * BLOCK_SIZE),
            BLOCK_SIZE,
        )
        back_start = max(start, aligned_end - PROBE_BLOCKS_PER_EDGE * BLOCK_SIZE)
        positions = sorted(set(front) | set(range(back_start, aligned_end, BLOCK_SIZE)))
        for position in positions:
            block = raw[position : position + BLOCK_SIZE]
            probe_blocks += 1
            valid_probe_blocks += int(_valid_block(block))

    edge_rows = leading_zero_rows + trailing_separator_rows
    return {
        "shift": shift,
        "corrected_body_base": body_base + shift,
        "row_count": len(rows),
        "leading_zero_rows": leading_zero_rows,
        "trailing_separator_rows": trailing_separator_rows,
        "edge_rows": edge_rows,
        "valid_probe_blocks": valid_probe_blocks,
        "probe_blocks": probe_blocks,
        "probe_valid_ratio": round(valid_probe_blocks / probe_blocks, 6)
        if probe_blocks
        else 0.0,
        "out_of_bounds_rows": out_of_bounds_rows,
        "nested_header_rows": nested_header_rows,
        "_score": (
            -out_of_bounds_rows,
            edge_rows,
            valid_probe_blocks,
            leading_zero_rows,
            trailing_separator_rows,
            -nested_header_rows,
        ),
    }


def _confirm_shift(
    source: bytes,
    body_base: int,
    shift: int,
    rows: list[dict[str, int]],
    trim_stream: Callable[[bytes], tuple[bytes, dict[str, Any]]],
) -> dict[str, Any]:
    clean_rows = 0
    invalid_blocks = 0
    payload_blocks = 0
    empty_rows = 0
    source_span_errors = 0
    leading_zero_rows = 0
    trailing_separator_rows = 0

    for row in rows:
        raw = _row_span(source, body_base, shift, row)
        if raw is None:
            source_span_errors += 1
            continue
        payload, trim = trim_stream(raw)
        leading_zero_rows += int(bool(trim.get("leading_zero_block")))
        trailing_separator_rows += int(
            trim.get("terminator_kind")
            in {"007777_separator", "trailing_007777_separator"}
        )
        blocks = [
            payload[position : position + BLOCK_SIZE]
            for position in range(0, len(payload), BLOCK_SIZE)
        ]
        if not blocks:
            empty_rows += 1
            continue
        row_invalid = sum(not _valid_block(block) for block in blocks)
        invalid_blocks += row_invalid
        payload_blocks += len(blocks)
        clean_rows += int(row_invalid == 0)

    return {
        "shift": shift,
        "corrected_body_base": body_base + shift,
        "row_count": len(rows),
        "clean_rows": clean_rows,
        "invalid_blocks": invalid_blocks,
        "payload_blocks": payload_blocks,
        "full_valid_ratio": round(
            (payload_blocks - invalid_blocks) / payload_blocks, 8
        )
        if payload_blocks
        else 0.0,
        "empty_rows": empty_rows,
        "source_span_errors": source_span_errors,
        "leading_zero_rows": leading_zero_rows,
        "trailing_separator_rows": trailing_separator_rows,
        "_score": (
            -source_span_errors,
            clean_rows,
            -invalid_blocks,
            leading_zero_rows + trailing_separator_rows,
            leading_zero_rows,
            trailing_separator_rows,
            -empty_rows,
        ),
    }


def resolve_nested_sequence_body(
    source: bytes,
    body_base: int,
    secondary_size: int,
    entries: Iterable[Any],
    search_end: int,
    trim_stream: Callable[[bytes], tuple[bytes, dict[str, Any]]],
) -> dict[str, Any]:
    """Return one whole-bank-clean corrected body base or an unresolved result."""

    entries = list(entries)
    rows = _entry_rows(entries, secondary_size)
    if not is_nested_sequence_resource(source, body_base):
        return {
            "status": "current_body_base_not_nested_sequence",
            "current_body_base": body_base,
            "corrected_body_base": body_base,
            "selected_shift": 0,
            "row_count": len(rows),
            "fully_clean_candidate_count": 1,
            "candidate_shifts": [],
        }

    max_shift = search_end - body_base - secondary_size
    max_shift_aligned = max_shift - (max_shift % BLOCK_SIZE) if max_shift >= 0 else -1
    if max_shift_aligned < 0:
        return {
            "status": "no_in_bounds_shift_window",
            "current_body_base": body_base,
            "corrected_body_base": None,
            "selected_shift": None,
            "row_count": len(rows),
            "search_end": search_end,
            "secondary_size": secondary_size,
            "max_shift": max_shift,
            "fully_clean_candidate_count": 0,
            "candidate_shifts": [],
        }

    screened = [
        _probe_shift(source, body_base, shift, rows)
        for shift in range(0, max_shift_aligned + 1, BLOCK_SIZE)
    ]
    screened.sort(key=lambda item: item["_score"], reverse=True)
    confirmed: list[dict[str, Any]] = []
    for screen in screened[:MAX_TOP_CANDIDATES]:
        confirmation = _confirm_shift(
            source,
            body_base,
            int(screen["shift"]),
            rows,
            trim_stream,
        )
        confirmation["screen"] = {
            key: value for key, value in screen.items() if not key.startswith("_")
        }
        confirmed.append(confirmation)
    confirmed.sort(key=lambda item: item["_score"], reverse=True)

    fully_clean = [
        item
        for item in confirmed
        if item["clean_rows"] == len(rows)
        and item["invalid_blocks"] == 0
        and item["empty_rows"] == 0
        and item["source_span_errors"] == 0
    ]
    selected = fully_clean[0] if len(fully_clean) == 1 else None
    if len(fully_clean) == 1:
        status = "unique_clean_bank_shift"
    elif len(fully_clean) > 1:
        status = "ambiguous_clean_bank_shift"
    elif confirmed:
        status = "no_clean_bank_shift"
    else:
        status = "no_shift_candidates"

    def public(item: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in item.items() if not key.startswith("_")}

    return {
        "status": status,
        "current_body_base": body_base,
        "corrected_body_base": int(selected["corrected_body_base"]) if selected else None,
        "selected_shift": int(selected["shift"]) if selected else None,
        "row_count": len(rows),
        "search_end": search_end,
        "secondary_size": secondary_size,
        "max_shift": max_shift,
        "max_shift_aligned": max_shift_aligned,
        "fully_clean_candidate_count": len(fully_clean),
        "selected_clean_rows": int(selected["clean_rows"]) if selected else None,
        "selected_invalid_blocks": int(selected["invalid_blocks"]) if selected else None,
        "candidate_shifts": [public(item) for item in confirmed[:10]],
    }

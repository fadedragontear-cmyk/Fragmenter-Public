#!/usr/bin/env python3
"""Install the SCEIVagi-authoritative SNDDATA stream trim policy.

SCEIVagi physical entry starts and the next physical entry start define each raw
sample span. Fragment's exact ``00 07 77...77`` block may occur inside PSound-
decodable audio, so it is not an unconditional terminator. Only an exact
separator occupying the final aligned block of the authoritative span is removed.
"""
from __future__ import annotations

from typing import Any

import snddata_sample_library_v1 as v1

BLOCK_SIZE = 16
SEPARATOR = b"\x00\x07" + b"\x77" * 14
POLICY = "sceivagi_span_trailing_separator_only_v3"
_INSTALLED = False
_ORIGINAL_TRIM_STREAM = v1._trim_stream


def trim_stream(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """Remove structural edge blocks without truncating at internal separators."""

    leading_zero = len(raw) >= BLOCK_SIZE and raw[:BLOCK_SIZE] == b"\x00" * BLOCK_SIZE
    start = BLOCK_SIZE if leading_zero else 0
    aligned_end = len(raw) - (len(raw) % BLOCK_SIZE)

    separator_offsets: list[int] = []
    ignored_flag_07_offsets: list[int] = []
    for offset in range(start, aligned_end, BLOCK_SIZE):
        block = raw[offset : offset + BLOCK_SIZE]
        if block == SEPARATOR:
            separator_offsets.append(offset)
        elif len(block) == BLOCK_SIZE and block[1] == 0x07:
            ignored_flag_07_offsets.append(offset)

    trailing_separator_offset = (
        aligned_end - BLOCK_SIZE
        if aligned_end - BLOCK_SIZE >= start
        and raw[aligned_end - BLOCK_SIZE : aligned_end] == SEPARATOR
        else None
    )
    end = trailing_separator_offset if trailing_separator_offset is not None else aligned_end
    internal_separator_offsets = [
        offset for offset in separator_offsets if offset != trailing_separator_offset
    ]

    payload = raw[start:end]
    payload = payload[: len(payload) - (len(payload) % BLOCK_SIZE)]

    return payload, {
        "policy": POLICY,
        "boundary_authority": "SCEIVagi physical entry span",
        "leading_zero_block": leading_zero,
        "payload_skip": start,
        "terminator_offset": trailing_separator_offset,
        "terminator_kind": (
            "trailing_007777_separator" if trailing_separator_offset is not None else None
        ),
        "internal_007777_separator_count": len(internal_separator_offsets),
        "internal_007777_separator_first_offset": (
            internal_separator_offsets[0] if internal_separator_offsets else None
        ),
        "internal_007777_separator_last_offset": (
            internal_separator_offsets[-1] if internal_separator_offsets else None
        ),
        "ignored_adpcm_flag_07_count": len(ignored_flag_07_offsets),
        "ignored_adpcm_flag_07_first_offset": (
            ignored_flag_07_offsets[0] if ignored_flag_07_offsets else None
        ),
        "ignored_adpcm_flag_07_last_offset": (
            ignored_flag_07_offsets[-1] if ignored_flag_07_offsets else None
        ),
        "trimmed_tail_bytes": len(raw) - end,
        "unaligned_tail_bytes": len(raw) - aligned_end,
    }


def install() -> None:
    """Install the trim policy into the v1 extractor used by v2/v3."""

    global _INSTALLED
    if _INSTALLED and v1._trim_stream is trim_stream:
        return
    v1._trim_stream = trim_stream
    _INSTALLED = True

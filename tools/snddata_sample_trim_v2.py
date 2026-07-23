#!/usr/bin/env python3
"""Install the evidence-based SNDDATA stream trim policy.

SCEIVagi offsets are the stream-boundary authority. A generic PS-ADPCM flag byte of
0x07 is a legal loop-control combination and may occur inside an active stream, so
it must not be treated as an unconditional end marker. Fragment's aligned
``00 07 77...77`` block remains a specific inter-stream separator.
"""
from __future__ import annotations

from typing import Any

import snddata_sample_library_v1 as v1

BLOCK_SIZE = 16
SEPARATOR = b"\x00\x07" + b"\x77" * 14
_INSTALLED = False
_ORIGINAL_TRIM_STREAM = v1._trim_stream


def trim_stream(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """Trim only structural padding and the exact Fragment separator.

    Ordinary blocks whose flag byte is 0x07 are retained and reported. They are
    waveform/loop data, not independently sufficient boundary evidence.
    """

    leading_zero = len(raw) >= BLOCK_SIZE and raw[:BLOCK_SIZE] == b"\x00" * BLOCK_SIZE
    start = BLOCK_SIZE if leading_zero else 0
    aligned_end = len(raw) - (len(raw) % BLOCK_SIZE)

    separator_offset: int | None = None
    ignored_flag_07_offsets: list[int] = []
    for offset in range(start, aligned_end, BLOCK_SIZE):
        block = raw[offset : offset + BLOCK_SIZE]
        if block == SEPARATOR:
            separator_offset = offset
            break
        if len(block) == BLOCK_SIZE and block[1] == 0x07:
            ignored_flag_07_offsets.append(offset)

    end = separator_offset if separator_offset is not None else aligned_end
    payload = raw[start:end]
    payload = payload[: len(payload) - (len(payload) % BLOCK_SIZE)]

    return payload, {
        "policy": "sceivagi_span_exact_separator_only_v2",
        "leading_zero_block": leading_zero,
        "payload_skip": start,
        "terminator_offset": separator_offset,
        "terminator_kind": "007777_separator" if separator_offset is not None else None,
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

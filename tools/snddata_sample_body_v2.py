#!/usr/bin/env python3
"""Install whole-bank detached-body resolution for canonical SNDDATA extraction.

Later Fragment sample-program metadata resources are followed by one or more
SCEI sequence resources before their indexed ADPCM body. The legacy candidate
selector stopped at the first nested resource marker. This patch preserves all
SCEIVagi offsets and span lengths, then accepts a shifted body base only when
one aligned candidate validates the entire bank.
"""
from __future__ import annotations

from typing import Any, Callable

import snddata_sample_library_v1 as v1
from snddata_sample_body_resolver_v1 import resolve_nested_sequence_body

_INSTALLED = False
_BASE_CHOOSE_BODY_BASE: Callable[..., tuple[int, list[dict[str, Any]]]] = (
    v1._choose_body_base
)
_CACHED_SOURCE: bytes | None = None
_CACHED_SAMPLE_PROGRAM_OFFSETS: list[int] = []


def _sample_program_offsets(data: bytes) -> list[int]:
    global _CACHED_SOURCE, _CACHED_SAMPLE_PROGRAM_OFFSETS
    if data is _CACHED_SOURCE:
        return _CACHED_SAMPLE_PROGRAM_OFFSETS
    offsets = [
        candidate_start
        for candidate_start, _candidate_end in v1.resource_spans(data)
        if candidate_start + 16 <= len(data)
        and v1._u16(data, candidate_start + 14) == v1.SAMPLE_PROGRAM_TYPE
    ]
    _CACHED_SOURCE = data
    _CACHED_SAMPLE_PROGRAM_OFFSETS = offsets
    return offsets


def _next_sample_program_offset(data: bytes, resource_start: int) -> int:
    for candidate_start in _sample_program_offsets(data):
        if candidate_start > resource_start:
            return candidate_start
    return len(data)


def choose_body_base(
    data: bytes,
    resource_start: int,
    head_offset: int,
    resource_end: int,
    primary_size: int,
    secondary_size: int,
    entries: list[v1.VagiEntry],
) -> tuple[int, list[dict[str, Any]]]:
    current_base, candidates = _BASE_CHOOSE_BODY_BASE(
        data,
        resource_start,
        head_offset,
        resource_end,
        primary_size,
        secondary_size,
        entries,
    )
    search_end = _next_sample_program_offset(data, resource_start)
    resolution = resolve_nested_sequence_body(
        data,
        current_base,
        secondary_size,
        entries,
        search_end,
        v1._trim_stream,
    )
    status = str(resolution.get("status") or "")
    if status == "current_body_base_not_nested_sequence":
        if candidates:
            candidates[0] = {
                **dict(candidates[0]),
                "resolution_method": status,
                "body_shift": 0,
                "body_resolution": resolution,
            }
        return current_base, candidates

    if status != "unique_clean_bank_shift":
        raise ValueError(
            "detached SNDDATA body base was not uniquely resolved for "
            f"resource 0x{resource_start:X}: {status}; "
            f"clean_candidates={resolution.get('fully_clean_candidate_count')}"
        )

    corrected = int(resolution["corrected_body_base"])
    selected = {
        "body_base": corrected,
        "score": 2.0,
        "valid_adpcm_ratio": 1.0,
        "within_resource_bound": corrected + secondary_size <= resource_end,
        "resolution_method": status,
        "body_shift": int(resolution["selected_shift"]),
        "body_search_end": search_end,
        "body_resolution": resolution,
    }
    legacy = [
        dict(candidate)
        for candidate in candidates
        if int(candidate.get("body_base") or -1) != corrected
    ]
    return corrected, [selected, *legacy[:15]]


def install() -> None:
    global _INSTALLED, _BASE_CHOOSE_BODY_BASE
    if _INSTALLED and v1._choose_body_base is choose_body_base:
        return
    if v1._choose_body_base is not choose_body_base:
        # Capture the already-installed boundary-correction layer rather than
        # bypassing it. Bank-level base resolution runs after any validated
        # per-entry logical-to-physical correction.
        _BASE_CHOOSE_BODY_BASE = v1._choose_body_base
    v1._choose_body_base = choose_body_base
    _INSTALLED = True

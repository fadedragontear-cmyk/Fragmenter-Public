#!/usr/bin/env python3
"""Detect and correct a consistent bank-wide phase before SCEIVagi sample starts.

Some Fragment banks point every VAGI entry a fixed number of bytes before the
actual waveform boundary. The old extractor treated the first 00 07 77..77
separator inside each entry as the end of that entry, producing short WAVs that
contained the tail of the previous sound. This patch recognizes a separator at
the same aligned offset in most entries and advances the secondary body base to
the byte immediately after that separator.
"""
from __future__ import annotations

from collections import Counter
from math import ceil
from typing import Any

import snddata_sample_library_v1 as v1

SEPARATOR = b"\x00\x07" + b"\x77" * 14
MAX_PHASE_SCAN = 0x10000
_MIN_RATIO = 0.50
_INSTALLED = False
_ORIGINAL_CHOOSE_BODY_BASE = v1._choose_body_base
_PHASE_BY_RESOURCE: dict[int, dict[str, Any]] = {}


def _first_separator(raw: bytes) -> int | None:
    limit = min(len(raw) - (len(raw) % 16), MAX_PHASE_SCAN)
    for offset in range(0, max(0, limit), 16):
        if raw[offset : offset + 16] == SEPARATOR:
            return offset
    return None


def _average_adpcm_ratio(
    data: bytes,
    body_base: int,
    resource_end: int,
    entries: list[Any],
) -> float:
    ratios: list[float] = []
    for entry in entries[: min(12, len(entries))]:
        start = body_base + int(entry.stream_offset)
        if start >= resource_end:
            continue
        raw = data[start : min(resource_end, start + 16 * 12)]
        ratios.append(float(v1._valid_adpcm_ratio(raw)))
    return sum(ratios) / len(ratios) if ratios else 0.0


def detect_phase_shift(
    data: bytes,
    body_base: int,
    resource_end: int,
    secondary_size: int,
    entries: list[Any],
) -> dict[str, Any]:
    """Return an evidence record describing an optional positive body-base shift."""
    offsets = sorted({int(entry.stream_offset) for entry in entries})
    observations: list[int] = []
    eligible = 0
    for entry in entries:
        start_offset = int(entry.stream_offset)
        later = [value for value in offsets if value > start_offset]
        if not later:
            continue
        raw_start = body_base + start_offset
        raw_end = min(resource_end, body_base + later[0])
        if raw_end - raw_start < 32:
            continue
        eligible += 1
        hit = _first_separator(data[raw_start:raw_end])
        if hit is not None and hit > 0:
            observations.append(hit)

    result: dict[str, Any] = {
        "applied": False,
        "uncorrected_body_base": int(body_base),
        "corrected_body_base": int(body_base),
        "phase_shift": 0,
        "separator_observations": len(observations),
        "eligible_entries": eligible,
        "separator_histogram": dict(sorted(Counter(observations).items())),
        "reason": "no_consistent_positive_separator_phase",
    }
    if not observations or eligible < 3:
        return result

    phase_offset, support = Counter(observations).most_common(1)[0]
    required = max(3, ceil(eligible * 0.60))
    if support < required:
        result["reason"] = "separator_phase_support_below_threshold"
        result["support"] = support
        result["required_support"] = required
        return result

    shift = int(phase_offset) + 16
    corrected = int(body_base) + shift
    result.update(
        {
            "phase_separator_offset": int(phase_offset),
            "phase_shift": shift,
            "support": support,
            "required_support": required,
            "corrected_body_base": corrected,
        }
    )
    if corrected + int(secondary_size) > int(resource_end):
        result["reason"] = "corrected_secondary_body_exceeds_resource"
        return result

    before_ratio = _average_adpcm_ratio(data, body_base, resource_end, entries)
    after_ratio = _average_adpcm_ratio(data, corrected, resource_end, entries)
    result["valid_adpcm_ratio_before"] = round(before_ratio, 6)
    result["valid_adpcm_ratio_after"] = round(after_ratio, 6)
    if after_ratio < _MIN_RATIO:
        result["reason"] = "corrected_phase_did_not_validate_as_adpcm"
        return result

    result["applied"] = True
    result["reason"] = "consistent_aligned_separator_phase_validated"
    return result


def choose_body_base_with_phase(
    data: bytes,
    resource_start: int,
    head_offset: int,
    resource_end: int,
    primary_size: int,
    secondary_size: int,
    entries: list[Any],
) -> tuple[int, list[dict[str, Any]]]:
    body_base, candidates = _ORIGINAL_CHOOSE_BODY_BASE(
        data,
        resource_start,
        head_offset,
        resource_end,
        primary_size,
        secondary_size,
        entries,
    )
    evidence = detect_phase_shift(
        data,
        body_base,
        resource_end,
        secondary_size,
        entries,
    )
    _PHASE_BY_RESOURCE[int(resource_start)] = evidence
    if evidence.get("applied"):
        corrected = int(evidence["corrected_body_base"])
        candidates = [
            {
                "body_base": corrected,
                "score": 2.0,
                "valid_adpcm_ratio": evidence.get("valid_adpcm_ratio_after"),
                "within_resource_bound": True,
                "boundary_mode": "validated_bank_phase_correction",
                "phase_shift": evidence.get("phase_shift"),
                "phase_support": evidence.get("support"),
            },
            *candidates,
        ]
        return corrected, candidates
    return body_base, candidates


def annotate_report(report: dict[str, Any]) -> dict[str, Any]:
    corrected = 0
    for bank in report.get("banks") or []:
        if not isinstance(bank, dict):
            continue
        resource = int(bank.get("resource_offset") or 0)
        evidence = dict(_PHASE_BY_RESOURCE.get(resource) or {})
        if not evidence:
            continue
        bank["stream_phase"] = evidence
        if evidence.get("applied"):
            corrected += 1
        for row in bank.get("samples") or []:
            if not isinstance(row, dict):
                continue
            row["stream_phase_shift"] = int(evidence.get("phase_shift") or 0)
            row["stream_phase_status"] = str(evidence.get("reason") or "")
            if evidence.get("applied"):
                row["body_base_uncorrected"] = int(evidence.get("uncorrected_body_base") or 0)
                row["boundary_source"] = (
                    "SCEIVagi stream offsets with validated bank-wide separator phase correction"
                )
    summary = report.setdefault("summary", {})
    summary["phase_corrected_banks"] = corrected
    summary["phase_evaluated_banks"] = len(_PHASE_BY_RESOURCE)
    report["sample_boundary_policy"] = {
        "version": 2,
        "separator": "00 07 followed by fourteen 77 bytes",
        "action": (
            "When the same positive aligned separator offset appears in at least 60% "
            "of three or more entries and the shifted starts validate as PS-ADPCM, "
            "advance the bank body base to immediately after that separator."
        ),
        "purpose": "prevent previous-sound tails from being decoded as the next sample",
    }
    return report


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    v1._choose_body_base = choose_body_base_with_phase
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Installed by snddata_sample_library_v3.")

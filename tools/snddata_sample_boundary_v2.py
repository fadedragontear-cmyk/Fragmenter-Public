#!/usr/bin/env python3
"""Evidence-gated per-entry SNDDATA sample boundary correction.

Boundary policy v2 could correct a constant bank-wide phase. Real Fragment banks
may instead expose logical SCEIVagi offsets that omit one aligned separator block
per preceding entry. In that layout the expected start drifts farther behind the
physical waveform on every sample. This module detects either a constant phase or
a progressive aligned drift, validates the resulting starts as PS-ADPCM, and only
then rewrites the in-memory entry offsets used by the read-only extractor.
"""
from __future__ import annotations

from collections import Counter
from math import ceil
from statistics import median
from typing import Any

import snddata_sample_boundary_v1 as legacy
import snddata_sample_library_v1 as v1

SEPARATOR = b"\x00\x07" + b"\x77" * 14
BLOCK_SIZE = 16
MAX_ENTRY_SCAN = 0x10000
MAX_INITIAL_SHIFT = 0x1000
MIN_ADPCM_RATIO = 0.50
MIN_PROGRESSIVE_OBSERVATIONS = 6
_INSTALLED = False
_BASE_CHOOSE_BODY_BASE = legacy._ORIGINAL_CHOOSE_BODY_BASE
_EVIDENCE_BY_RESOURCE: dict[int, dict[str, Any]] = {}


def reset_boundary_evidence() -> None:
    """Clear process-local evidence before a new extraction run."""
    _EVIDENCE_BY_RESOURCE.clear()


def boundary_evidence() -> dict[int, dict[str, Any]]:
    return {key: dict(value) for key, value in _EVIDENCE_BY_RESOURCE.items()}


def _aligned_separator_offsets(raw: bytes) -> list[int]:
    limit = len(raw) - (len(raw) % BLOCK_SIZE)
    return [
        offset
        for offset in range(0, max(0, limit), BLOCK_SIZE)
        if raw[offset : offset + BLOCK_SIZE] == SEPARATOR
    ]


def _valid_after(data: bytes, start: int, resource_end: int) -> float:
    if start < 0 or start >= resource_end:
        return 0.0
    raw = data[start : min(resource_end, start + BLOCK_SIZE * 12)]
    return float(v1._valid_adpcm_ratio(raw))


def _collect_observations(
    data: bytes,
    body_base: int,
    resource_end: int,
    entries: list[Any],
) -> list[dict[str, Any]]:
    ordered = sorted(entries, key=lambda entry: (int(entry.stream_offset), int(entry.index)))
    observations: list[dict[str, Any]] = []
    for ordinal, entry in enumerate(ordered):
        logical = int(entry.stream_offset)
        expected = body_base + logical
        if expected >= resource_end:
            continue
        next_logical = (
            int(ordered[ordinal + 1].stream_offset)
            if ordinal + 1 < len(ordered)
            else None
        )
        gap = max(BLOCK_SIZE * 8, (next_logical - logical) if next_logical is not None else 0)
        # The progressive defect reported by the operator can accumulate hundreds
        # of separator blocks. Scan a bounded window, but never outside the resource.
        scan_size = min(MAX_ENTRY_SCAN, max(0x800, gap + BLOCK_SIZE * (ordinal + 16)))
        raw = data[expected : min(resource_end, expected + scan_size)]
        separators = _aligned_separator_offsets(raw)
        chosen: dict[str, Any] | None = None
        for separator_offset in separators:
            physical = expected + separator_offset + BLOCK_SIZE
            ratio = _valid_after(data, physical, resource_end)
            if ratio < MIN_ADPCM_RATIO:
                continue
            chosen = {
                "entry_index": int(entry.index),
                "ordinal": ordinal,
                "logical_stream_offset": logical,
                "separator_offset": separator_offset,
                "candidate_shift": separator_offset + BLOCK_SIZE,
                "valid_adpcm_ratio_after": round(ratio, 6),
            }
            break
        if chosen is not None:
            observations.append(chosen)
    return observations


def _constant_model(observations: list[dict[str, Any]], eligible: int) -> dict[str, Any] | None:
    shifts = [int(row["candidate_shift"]) for row in observations]
    if not shifts:
        return None
    shift, support = Counter(shifts).most_common(1)[0]
    required = max(3, ceil(max(1, eligible) * 0.60))
    if (
        support < required
        or shift <= 0
        or shift > MAX_INITIAL_SHIFT
        or shift % BLOCK_SIZE
    ):
        return None
    return {
        "mode": "constant_separator_phase",
        "intercept": int(shift),
        "slope_per_entry": 0,
        "support": support,
        "required_support": required,
    }


def _progressive_model(observations: list[dict[str, Any]], eligible: int) -> dict[str, Any] | None:
    rows = sorted(observations, key=lambda row: int(row["ordinal"]))
    if len(rows) < MIN_PROGRESSIVE_OBSERVATIONS:
        return None
    slopes: list[int] = []
    for left, right in zip(rows, rows[1:]):
        index_delta = int(right["ordinal"]) - int(left["ordinal"])
        shift_delta = int(right["candidate_shift"]) - int(left["candidate_shift"])
        if index_delta <= 0 or shift_delta <= 0:
            continue
        per_entry = shift_delta / index_delta
        aligned = int(round(per_entry / BLOCK_SIZE)) * BLOCK_SIZE
        if BLOCK_SIZE <= aligned <= BLOCK_SIZE * 8 and abs(per_entry - aligned) <= 2.0:
            slopes.append(aligned)
    if not slopes:
        return None
    slope, slope_support = Counter(slopes).most_common(1)[0]
    required_slope = max(3, ceil(max(1, len(rows) - 1) * 0.50))
    if slope_support < required_slope:
        return None
    intercept_candidates = [
        int(row["candidate_shift"]) - slope * int(row["ordinal"])
        for row in rows
    ]
    intercept = int(round(median(intercept_candidates) / BLOCK_SIZE)) * BLOCK_SIZE
    if intercept <= 0 or intercept > MAX_INITIAL_SHIFT:
        return None
    residual_rows = [
        row
        for row in rows
        if abs(
            int(row["candidate_shift"])
            - (intercept + slope * int(row["ordinal"]))
        )
        <= BLOCK_SIZE
    ]
    required = max(MIN_PROGRESSIVE_OBSERVATIONS, ceil(max(1, eligible) * 0.55))
    if len(residual_rows) < required:
        return None
    return {
        "mode": "progressive_separator_drift",
        "intercept": intercept,
        "slope_per_entry": slope,
        "support": len(residual_rows),
        "required_support": required,
        "slope_support": slope_support,
        "required_slope_support": required_slope,
    }


def _apply_model(
    data: bytes,
    body_base: int,
    resource_end: int,
    secondary_size: int,
    entries: list[Any],
    model: dict[str, Any],
) -> dict[str, Any] | None:
    ordered = sorted(entries, key=lambda entry: (int(entry.stream_offset), int(entry.index)))
    logical_offsets = [int(entry.stream_offset) for entry in ordered]
    logical_owners = {value: index for index, value in enumerate(logical_offsets)}
    intercept = int(model.get("intercept") or 0)
    slope = int(model.get("slope_per_entry") or 0)
    corrected: list[int] = []
    ratios: list[float] = []
    separator_matches = 0
    logical_collisions = 0
    corrections: list[dict[str, Any]] = []
    for ordinal, (entry, logical) in enumerate(zip(ordered, logical_offsets)):
        shift = intercept + slope * ordinal
        physical = logical + shift
        if shift < 0 or physical < 0 or physical >= secondary_size:
            return None
        absolute = body_base + physical
        if absolute >= resource_end:
            return None
        owner = logical_owners.get(physical)
        if owner is not None and owner != ordinal:
            logical_collisions += 1
        ratio = _valid_after(data, absolute, resource_end)
        ratios.append(ratio)
        if absolute >= BLOCK_SIZE and data[absolute - BLOCK_SIZE : absolute] == SEPARATOR:
            separator_matches += 1
        corrected.append(physical)
        corrections.append(
            {
                "entry_index": int(entry.index),
                "ordinal": ordinal,
                "logical_stream_offset": logical,
                "physical_stream_offset": physical,
                "boundary_shift": shift,
                "valid_adpcm_ratio_after": round(ratio, 6),
            }
        )
    if any(right <= left for left, right in zip(corrected, corrected[1:])):
        return None
    maximum_collisions = max(1, ceil(len(ordered) * 0.10))
    if logical_collisions > maximum_collisions:
        return None
    average = sum(ratios) / len(ratios) if ratios else 0.0
    required_matches = max(3, ceil(len(ordered) * 0.50))
    if average < MIN_ADPCM_RATIO or separator_matches < required_matches:
        return None
    for entry, physical in zip(ordered, corrected):
        entry.stream_offset = physical
    return {
        **model,
        "applied": True,
        "reason": "validated_aligned_per_entry_separator_model",
        "uncorrected_body_base": int(body_base),
        "corrected_body_base": int(body_base),
        "average_valid_adpcm_ratio_after": round(average, 6),
        "separator_matches": separator_matches,
        "required_separator_matches": required_matches,
        "logical_offset_collisions": logical_collisions,
        "maximum_logical_offset_collisions": maximum_collisions,
        "entry_corrections": corrections,
    }


def choose_body_base_with_entry_correction(
    data: bytes,
    resource_start: int,
    head_offset: int,
    resource_end: int,
    primary_size: int,
    secondary_size: int,
    entries: list[Any],
) -> tuple[int, list[dict[str, Any]]]:
    body_base, candidates = _BASE_CHOOSE_BODY_BASE(
        data,
        resource_start,
        head_offset,
        resource_end,
        primary_size,
        secondary_size,
        entries,
    )
    observations = _collect_observations(data, body_base, resource_end, entries)
    evidence: dict[str, Any] = {
        "applied": False,
        "mode": "none",
        "reason": "no_validated_separator_model",
        "uncorrected_body_base": int(body_base),
        "corrected_body_base": int(body_base),
        "eligible_entries": len(entries),
        "separator_observations": len(observations),
        "observations": observations,
    }
    model = _constant_model(observations, len(entries))
    progressive = _progressive_model(observations, len(entries))
    # Prefer the progressive model when it is supported: a constant correction
    # cannot repair cumulative drift even if a few early entries share one shift.
    selected = progressive or model
    if selected is not None:
        applied = _apply_model(
            data,
            body_base,
            resource_end,
            secondary_size,
            entries,
            selected,
        )
        if applied is not None:
            evidence = {**evidence, **applied}
            candidates = [
                {
                    "body_base": int(body_base),
                    "score": 2.25,
                    "valid_adpcm_ratio": applied.get("average_valid_adpcm_ratio_after"),
                    "within_resource_bound": True,
                    "boundary_mode": applied.get("mode"),
                    "boundary_intercept": applied.get("intercept"),
                    "boundary_slope_per_entry": applied.get("slope_per_entry"),
                    "boundary_support": applied.get("support"),
                },
                *candidates,
            ]
    _EVIDENCE_BY_RESOURCE[int(resource_start)] = evidence
    return body_base, candidates


def annotate_report(report: dict[str, Any]) -> dict[str, Any]:
    corrected_banks = 0
    progressive_banks = 0
    corrected_samples = 0
    for bank in report.get("banks") or []:
        if not isinstance(bank, dict):
            continue
        resource = int(bank.get("resource_offset") or 0)
        evidence = dict(_EVIDENCE_BY_RESOURCE.get(resource) or {})
        if not evidence:
            continue
        bank["stream_boundary_model"] = evidence
        corrections = {
            int(row.get("entry_index") or 0): row
            for row in evidence.get("entry_corrections") or []
            if isinstance(row, dict)
        }
        if evidence.get("applied"):
            corrected_banks += 1
            if evidence.get("mode") == "progressive_separator_drift":
                progressive_banks += 1
        for row in bank.get("samples") or []:
            if not isinstance(row, dict):
                continue
            correction = corrections.get(int(row.get("index") or 0))
            row["stream_boundary_mode"] = str(evidence.get("mode") or "none")
            row["stream_boundary_status"] = str(evidence.get("reason") or "")
            if correction is None:
                continue
            corrected_samples += 1
            row["logical_stream_offset"] = int(correction["logical_stream_offset"])
            row["physical_stream_offset"] = int(correction["physical_stream_offset"])
            row["stream_boundary_shift"] = int(correction["boundary_shift"])
            row["boundary_source"] = (
                "SCEIVagi logical offsets with validated per-entry separator correction"
            )
    summary = report.setdefault("summary", {})
    summary["entry_corrected_banks"] = corrected_banks
    summary["progressive_drift_banks"] = progressive_banks
    summary["entry_corrected_samples"] = corrected_samples
    report["sample_boundary_policy"] = {
        "version": 3,
        "separator": "00 07 followed by fourteen 77 bytes",
        "models": ["constant_separator_phase", "progressive_separator_drift"],
        "action": (
            "Fit an aligned separator model across entries. Apply either one constant "
            "shift or an evidence-supported per-entry slope only when corrected starts "
            "remain ordered, avoid collisions with other declared logical starts, at "
            "least half are immediately preceded by the separator, and the resulting "
            "data validates as PS-ADPCM."
        ),
        "purpose": (
            "prevent cumulative logical-to-physical offset drift from trimming later "
            "sample starts and including adjacent sample audio"
        ),
    }
    return report


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    v1._choose_body_base = choose_body_base_with_entry_correction
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Installed by snddata_sample_library_v3.")

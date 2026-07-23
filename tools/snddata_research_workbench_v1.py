#!/usr/bin/env python3
"""Readable research model for the Fragmenter SNDDATA mixer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_sound_v1 import canonical_snddata_path, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_mapping_store_v1 import list_mappings, mapping_store_path
from snddata_music_system_v5 import _compat_candidate, load_catalog, sequence_view_model
from snddata_research_store_v1 import list_candidate_reviews, review_index
from snddata_sample_library_v3 import REPORT_NAME as SAMPLE_REPORT_NAME

FILTERS = ("All", "Renderable", "Needs research", "Saved mapping", "Reviewed")
ROUTING_MODES = ("Auto", "program_change", "channel_as_program")


def _mapping_index(project: FragmenterProjectV1) -> dict[str, dict[str, Any]]:
    source = canonical_snddata_path(project)
    if not source.is_file():
        return {}
    return {
        str(row.get("sequence_id") or ""): row
        for row in list_mappings(mapping_store_path(project), source)
        if isinstance(row, dict)
    }


def _reviews_by_sequence(project: FragmenterProjectV1) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in list_candidate_reviews(project):
        grouped.setdefault(str(row.get("sequence_id") or ""), []).append(row)
    return grouped


def _reviewed_routing(rows: list[dict[str, Any]]) -> str:
    for status in ("confirmed", "plausible"):
        row = next((item for item in rows if item.get("status") == status and item.get("routing_mode")), None)
        if row:
            return str(row["routing_mode"])
    return ""


def _hypothesis(sequence: dict[str, Any], routing_mode: str | None) -> dict[str, Any] | None:
    selected = str(routing_mode or "Auto")
    if selected == "Auto":
        selected = str(sequence.get("preferred_hypothesis") or "")
    return next(
        (row for row in sequence.get("routing_hypotheses") or [] if isinstance(row, dict) and row.get("mode") == selected),
        None,
    )


def _candidate_status_counts(sequence: dict[str, Any]) -> dict[str, int]:
    rows = [
        _compat_candidate(candidate)
        for hypothesis in sequence.get("routing_hypotheses") or []
        if isinstance(hypothesis, dict)
        for candidate in hypothesis.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    return {
        "candidates": len(rows),
        "renderable": sum(row.get("status") == "renderable" for row in rows),
        "missing_programs": sum(row.get("status") == "missing_programs" for row in rows),
        "missing_samples": sum(row.get("status") == "missing_samples" for row in rows),
    }


def sequence_rows(
    project: FragmenterProjectV1,
    *,
    query: str = "",
    status_filter: str = "All",
) -> list[dict[str, Any]]:
    payload = load_catalog(project)
    mappings = _mapping_index(project)
    reviews_by_sequence = _reviews_by_sequence(project)
    needle = str(query or "").strip().casefold()
    output: list[dict[str, Any]] = []
    for raw in payload.get("sequences") or []:
        if not isinstance(raw, dict):
            continue
        counts = _candidate_status_counts(raw)
        sequence_id = str(raw.get("sequence_id") or "")
        saved = mappings.get(sequence_id)
        reviews = reviews_by_sequence.get(sequence_id, [])
        reviewed_routing = _reviewed_routing(reviews)
        row = {
            "sequence_id": sequence_id,
            "resource_offset": int(raw.get("resource_offset") or 0),
            "note_on_count": int(raw.get("note_on_count") or 0),
            "track_count": int(raw.get("track_count") or 0),
            "event_count": int(raw.get("event_count") or 0),
            "preferred_hypothesis": str(raw.get("preferred_hypothesis") or ""),
            "reviewed_routing_mode": reviewed_routing,
            "routing_status": str(raw.get("routing_status") or raw.get("first_wall") or "unresolved"),
            "first_wall": str(raw.get("first_wall") or ""),
            "saved_mapping": saved,
            "review_count": len(reviews),
            **counts,
        }
        haystack = " ".join(
            [
                sequence_id,
                row["preferred_hypothesis"],
                reviewed_routing,
                row["routing_status"],
                str((saved or {}).get("program_resource") or ""),
            ]
        ).casefold()
        if needle and needle not in haystack:
            continue
        selected_filter = str(status_filter or "All")
        if selected_filter == "Renderable" and counts["renderable"] <= 0:
            continue
        if selected_filter == "Needs research" and (saved or reviews):
            continue
        if selected_filter == "Saved mapping" and not saved:
            continue
        if selected_filter == "Reviewed" and not reviews:
            continue
        output.append(row)
    output.sort(
        key=lambda row: (
            0 if row.get("saved_mapping") else 1,
            0 if int(row.get("renderable") or 0) else 1,
            str(row.get("sequence_id") or "").casefold(),
        )
    )
    return output


def candidate_rows(
    project: FragmenterProjectV1,
    sequence_id: str,
    *,
    routing_mode: str = "Auto",
) -> dict[str, Any]:
    model = sequence_view_model(project, sequence_id)
    mappings = _mapping_index(project)
    saved = mappings.get(str(sequence_id))
    reviews = review_index(project, str(sequence_id))
    requested_mode = str(routing_mode or "Auto")
    if requested_mode == "Auto":
        reviewed_rows = list(reviews.values())
        requested_mode = _reviewed_routing(reviewed_rows) or "Auto"
    hypothesis = _hypothesis(model, requested_mode)
    selected_mode = str((hypothesis or {}).get("mode") or "")
    rows: list[dict[str, Any]] = []
    for rank, raw in enumerate((hypothesis or {}).get("candidates") or [], 1):
        if not isinstance(raw, dict):
            continue
        row = _compat_candidate(raw)
        resource = str(row.get("resource_id") or f"resource@0x{int(row.get('resource_offset') or 0):X}")
        required_samples = list(row.get("required_sample_ids") or [])
        missing_programs = list(row.get("missing_program_indexes") or [])
        missing_samples = list(row.get("missing_sample_ids") or [])
        review = reviews.get((selected_mode, resource))
        row.update(
            {
                "rank": rank,
                "routing_mode": selected_mode,
                "resource_id": resource,
                "required_sample_ids": required_samples,
                "missing_program_indexes": missing_programs,
                "missing_sample_ids": missing_samples,
                "coverage": f"{len(row.get('matched_sample_ids') or [])}/{len(required_samples)}",
                "missing_summary": ", ".join(
                    [
                        *(f"Program {value}" for value in missing_programs[:8]),
                        *(f"sample {value}" for value in missing_samples[:8]),
                    ]
                ),
                "review": review,
                "saved": bool(saved and str(saved.get("program_resource") or "") == resource),
            }
        )
        rows.append(row)
    return {
        "sequence": model,
        "routing_mode": selected_mode,
        "hypothesis": hypothesis,
        "candidates": rows,
        "saved_mapping": saved,
        "first_wall": str((hypothesis or {}).get("first_wall") or model.get("first_wall") or "No routing hypothesis selected"),
        "renderable_candidates": sum(row.get("status") == "renderable" for row in rows),
    }


def _load_sample_report(project: FragmenterProjectV1) -> dict[str, Any]:
    path = sound_reports_root(project) / SAMPLE_REPORT_NAME
    if not path.is_file():
        return {"samples": [], "report_path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid SNDDATA sample report: {path}")
    payload["report_path"] = str(path)
    return payload


def sample_rows(project: FragmenterProjectV1, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    report = _load_sample_report(project)
    resource_offset = int(candidate.get("resource_offset") or 0)
    required = {int(value) for value in candidate.get("required_sample_ids") or []}
    missing = {int(value) for value in candidate.get("missing_sample_ids") or []}
    rows: list[dict[str, Any]] = []
    by_index: dict[int, dict[str, Any]] = {}
    for raw in report.get("samples") or []:
        if not isinstance(raw, dict) or int(raw.get("resource_offset") or 0) != resource_offset:
            continue
        index = int(raw.get("index") or 0)
        if required and index not in required:
            continue
        path = Path(str(raw.get("output_path") or ""))
        row = {
            **raw,
            "index": index,
            "required": index in required,
            "missing": index in missing or not path.is_file(),
            "playable": path.is_file() and path.suffix.casefold() == ".wav",
            "output_path": str(path),
        }
        by_index[index] = row
    for index in sorted(required):
        rows.append(
            by_index.get(
                index,
                {
                    "index": index,
                    "display_name": f"sample {index}",
                    "sample_rate": 0,
                    "duration_estimate": 0.0,
                    "output_path": "",
                    "required": True,
                    "missing": True,
                    "playable": False,
                },
            )
        )
    if not required:
        rows = sorted(by_index.values(), key=lambda row: int(row.get("index") or 0))
    return rows


def readiness(project: FragmenterProjectV1) -> dict[str, Any]:
    source = canonical_snddata_path(project)
    catalog = sound_reports_root(project) / "snddata_music_system_v5.json"
    samples = sound_reports_root(project) / SAMPLE_REPORT_NAME
    return {
        "snddata_source": str(source),
        "snddata_exists": source.is_file(),
        "catalog": str(catalog),
        "catalog_exists": catalog.is_file(),
        "sample_report": str(samples),
        "sample_report_exists": samples.is_file(),
        "playback_requirements": [
            "routing hypothesis",
            "Program resource with all required Program indexes",
            "decoded WAV for every required sample ID",
            "available in-process WAV playback backend",
        ],
    }

#!/usr/bin/env python3
"""Project-local automation for Celdra's audio research mode.

This does not guess mappings or alter game data.  It consolidates readiness,
sample-boundary, classification, and mixer evidence into one reproducible report
and chooses the next safe pipeline/reporting action.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_sound_v1 import sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_research_workbench_v1 import readiness, sequence_rows
from snddata_sample_classification_v1 import classification_summary
from snddata_sample_health_v1 import sample_library_health

REPORT_JSON = "celdra_audio_analysis_v1.json"
REPORT_MD = "celdra_audio_analysis_v1.md"
OPERATOR_TIMING_ANCHOR = {
    "flat_sample": 228,
    "bank_ordinal": 2,
    "local_sample": 1,
    "sample_rate": 44094,
    "observation": (
        "First clearly audible adjacent-sample splice reported here; earlier samples "
        "appear to lose progressively more leading audio."
    ),
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _sample_anchor_matches(sample_report: dict[str, Any]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in sample_report.get("samples") or []:
        if not isinstance(row, dict):
            continue
        flat_index = row.get("flat_index")
        bank = int(row.get("bank_ordinal") or 0)
        local = int(row.get("index") if row.get("index") is not None else row.get("sample_id") or 0)
        rate = int(row.get("sample_rate") or 0)
        if (
            (flat_index is not None and int(flat_index) == OPERATOR_TIMING_ANCHOR["flat_sample"])
            or (
                bank == OPERATOR_TIMING_ANCHOR["bank_ordinal"]
                and local == OPERATOR_TIMING_ANCHOR["local_sample"]
                and rate == OPERATOR_TIMING_ANCHOR["sample_rate"]
            )
        ):
            matches.append(
                {
                    "flat_index": flat_index,
                    "bank_ordinal": bank,
                    "sample_id": local,
                    "sample_rate": rate,
                    "logical_stream_offset": row.get("logical_stream_offset"),
                    "physical_stream_offset": row.get("physical_stream_offset"),
                    "stream_boundary_shift": row.get("stream_boundary_shift"),
                    "stream_boundary_mode": row.get("stream_boundary_mode"),
                    "raw_size": row.get("raw_size"),
                    "payload_size": row.get("payload_size"),
                    "duration_estimate": row.get("duration_estimate"),
                    "output_path": row.get("output_path"),
                }
            )
    return matches


def analyze_audio_workspace(project: FragmenterProjectV1) -> dict[str, Any]:
    reports = sound_reports_root(project)
    state = readiness(project)
    health = sample_library_health(project)
    classifications = classification_summary(project)
    sample_report_path = Path(str(state.get("sample_report") or ""))
    catalog_path = Path(str(state.get("catalog") or ""))
    sample_report = _load_json(sample_report_path)

    try:
        sequences = sequence_rows(project) if state.get("catalog_exists") else []
        sequence_error = ""
    except Exception as exc:
        sequences = []
        sequence_error = f"{type(exc).__name__}: {exc}"

    sample_mtime = sample_report_path.stat().st_mtime if sample_report_path.is_file() else 0.0
    catalog_mtime = catalog_path.stat().st_mtime if catalog_path.is_file() else 0.0
    mixer_stale = bool(sample_mtime and catalog_mtime and catalog_mtime < sample_mtime)
    policy_version = int((sample_report.get("sample_boundary_policy") or {}).get("version") or 0)
    summary = sample_report.get("summary") if isinstance(sample_report.get("summary"), dict) else {}
    progressive_banks = int(summary.get("progressive_drift_banks") or 0)
    corrected_samples = int(summary.get("entry_corrected_samples") or 0)

    next_actions: list[dict[str, str]] = []
    if not state.get("snddata_exists"):
        next_actions.append({"action": "sound_extract", "reason": "Canonical SNDDATA source is missing."})
    if not state.get("sample_report_exists") or policy_version < 3 or health.get("rebuild_required"):
        next_actions.append(
            {
                "action": "snddata_samples",
                "reason": "Sample evidence is absent, stale, or predates progressive boundary policy v3.",
            }
        )
    if not state.get("catalog_exists") or mixer_stale:
        next_actions.append(
            {
                "action": "snddata_mixer",
                "reason": "Mixer catalog is missing or older than the current sample report.",
            }
        )
    if progressive_banks:
        next_actions.append(
            {
                "action": "audition_progressive_boundaries",
                "reason": (
                    f"{progressive_banks} bank(s) use per-entry drift correction; audition early, middle, "
                    "late, and operator-anchor samples before trusting renders."
                ),
            }
        )
    unclassified = int(classifications.get("samples") or 0) - int(classifications.get("classified") or 0)
    if unclassified > 0:
        next_actions.append(
            {
                "action": "classify_samples",
                "reason": f"{unclassified:,} decoded sample(s) remain unclassified.",
            }
        )
    renderable_sequences = sum(int(row.get("renderable") or 0) > 0 for row in sequences)
    if state.get("catalog_exists") and renderable_sequences <= 1:
        next_actions.append(
            {
                "action": "treat_current_preview_as_diagnostic_only",
                "reason": (
                    "Zero or one sequence currently has a renderer-complete candidate; this is not enough "
                    "coverage to identify the game's music system."
                ),
            }
        )
    if not next_actions:
        next_actions.append(
            {
                "action": "continue_bounded_listening_tests",
                "reason": "Core reports are current; proceed with evidence-backed classification and candidate reviews.",
            }
        )

    payload: dict[str, Any] = {
        "version": 1,
        "generated_at": _utc_iso(),
        "mode": "Celdra audio analyst",
        "writes_game_data": False,
        "readiness": state,
        "sample_health": health,
        "sample_boundary": {
            "policy_version": policy_version,
            "entry_corrected_banks": int(summary.get("entry_corrected_banks") or 0),
            "progressive_drift_banks": progressive_banks,
            "entry_corrected_samples": corrected_samples,
            "operator_timing_anchor": dict(OPERATOR_TIMING_ANCHOR),
            "operator_anchor_matches": _sample_anchor_matches(sample_report),
        },
        "classification": classifications,
        "mixer": {
            "sequence_rows": len(sequences),
            "sequences_with_note_events": sum(int(row.get("note_on_count") or 0) > 0 for row in sequences),
            "sequences_with_renderable_candidate": renderable_sequences,
            "renderable_candidate_count": sum(int(row.get("renderable") or 0) for row in sequences),
            "saved_mappings": sum(bool(row.get("saved_mapping")) for row in sequences),
            "reviewed_sequences": sum(int(row.get("review_count") or 0) > 0 for row in sequences),
            "catalog_older_than_samples": mixer_stale,
            "catalog_error": sequence_error,
        },
        "next_actions": next_actions,
    }
    json_path = reports / REPORT_JSON
    md_path = reports / REPORT_MD
    payload["report_json"] = str(json_path)
    payload["report_markdown"] = str(md_path)
    _atomic_write(json_path, json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")

    lines = [
        "# Celdra Audio Analysis",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "This report is project-local, read-only with respect to game data, and does not accept a render as proof of authentic routing.",
        "",
        "## Sample boundaries",
        "",
        f"- Policy version: **{policy_version or 'missing'}**",
        f"- Entry-corrected banks: **{int(summary.get('entry_corrected_banks') or 0)}**",
        f"- Progressive-drift banks: **{progressive_banks}**",
        f"- Corrected sample entries: **{corrected_samples}**",
        f"- Operator anchor matches: **{len(payload['sample_boundary']['operator_anchor_matches'])}**",
        "",
        "## Classification",
        "",
        f"- Samples: **{int(classifications.get('samples') or 0):,}**",
        f"- Classified: **{int(classifications.get('classified') or 0):,}**",
        f"- Usable: **{int(classifications.get('usable') or 0):,}**",
        "",
        "## Mixer",
        "",
        f"- Sequence rows: **{len(sequences):,}**",
        f"- Sequences with note events: **{payload['mixer']['sequences_with_note_events']:,}**",
        f"- Sequences with a renderable candidate: **{renderable_sequences:,}**",
        f"- Mixer catalog older than sample report: **{'yes' if mixer_stale else 'no'}**",
        "",
        "## Next safe actions",
        "",
    ]
    lines.extend(
        f"{index}. **{row['action']}** — {row['reason']}"
        for index, row in enumerate(next_actions, 1)
    )
    lines.extend(["", f"JSON evidence: `{json_path}`", ""])
    _atomic_write(md_path, "\n".join(lines))
    return payload


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's Celdra audio mode.")

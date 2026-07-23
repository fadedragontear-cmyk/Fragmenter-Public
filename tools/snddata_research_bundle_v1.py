#!/usr/bin/env python3
"""Create compact, shareable SNDDATA research bundles without game binary data."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_sound_v1 import canonical_snddata_path, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_sample_bridge_v1 import normalized_sample_rows

BUNDLE_VERSION = 1


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _selected_sequence(payload: Any, sequence_id: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return next(
        (
            row
            for row in payload.get("sequences") or []
            if isinstance(row, dict) and str(row.get("sequence_id") or "") == sequence_id
        ),
        None,
    )


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def build_research_bundle(
    project: FragmenterProjectV1,
    sequence: dict[str, Any],
    candidate: dict[str, Any],
    *,
    playback_backend: str = "unknown",
) -> dict[str, Any]:
    """Write a ZIP containing selected catalog/report evidence and no WAV/raw bytes."""
    sequence_id = str(sequence.get("sequence_id") or "unknown_sequence")
    resource_offset = int(candidate.get("resource_offset") or 0)
    reports = sound_reports_root(project)
    source = canonical_snddata_path(project)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    safe_sequence = sequence_id.replace("@", "_").replace("0x", "").replace("/", "_")
    output_dir = reports / "research_bundles"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"snddata_research_{safe_sequence}_{resource_offset:08X}_{stamp}.zip"

    sample_rows = [
        row
        for row in normalized_sample_rows(project)
        if int(row.get("resource_id") if row.get("resource_id") is not None else -1) == resource_offset
    ]
    sample_inventory = [
        {
            "resource_offset": resource_offset,
            "sample_id": int(row.get("sample_id") if row.get("sample_id") is not None else 0),
            "display_name": row.get("display_name"),
            "sample_rate": row.get("sample_rate"),
            "duration_estimate": row.get("duration_estimate"),
            "decode_status": row.get("decode_status"),
            "boundary_source": row.get("boundary_source"),
            "errors": row.get("errors") or [],
            "output_path": row.get("output_path"),
            "output_exists": bool(row.get("output_exists")),
            "metadata_path": row.get("metadata_path"),
        }
        for row in sample_rows
    ]

    source_stat = source.stat() if source.is_file() else None
    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "created_at": now.isoformat(),
        "project_file": str(project.project_path),
        "playback_backend": playback_backend,
        "source": {
            "path": str(source),
            "exists": source.is_file(),
            "size": source_stat.st_size if source_stat else 0,
            "mtime_ns": source_stat.st_mtime_ns if source_stat else 0,
        },
        "selection": {
            "sequence_id": sequence_id,
            "sequence_resource_offset": int(sequence.get("resource_offset") or 0),
            "routing_mode": candidate.get("routing_mode"),
            "program_resource": candidate.get("resource_id"),
            "program_resource_offset": resource_offset,
            "candidate_status": candidate.get("status"),
            "candidate_status_detail": candidate.get("status_detail"),
            "required_program_indexes": candidate.get("required_program_indexes")
            or candidate.get("program_indexes_required")
            or [],
            "missing_program_indexes": candidate.get("missing_program_indexes") or [],
            "required_sample_ids": candidate.get("required_sample_ids") or [],
            "matched_sample_ids": candidate.get("matched_sample_ids") or [],
            "missing_sample_ids": candidate.get("missing_sample_ids") or [],
        },
        "sample_inventory_rows": len(sample_inventory),
        "binary_data_included": False,
        "notes": "Contains JSON/text diagnostics only. No SNDDATA, WAV, PS-ADPCM, ISO, or game assets are included.",
    }

    catalog = _load_json(reports / "snddata_music_system_v5.json")
    forensics = _load_json(reports / "snddata_forensics_v1.json")
    sample_report = _load_json(reports / "snddata_sample_library.json")
    preview = _load_json(reports / "music_preview_last_v5.json")

    selected_catalog = _selected_sequence(catalog, sequence_id)
    selected_forensics = _selected_sequence(forensics, sequence_id)
    sample_report_rows = sample_report.get("samples") or [] if isinstance(sample_report, dict) else []
    filtered_sample_report = {
        "summary": sample_report.get("summary") if isinstance(sample_report, dict) else None,
        "source_sha256": sample_report.get("source_sha256") if isinstance(sample_report, dict) else None,
        "samples": [
            row
            for row in sample_report_rows
            if isinstance(row, dict)
            and int(row.get("resource_offset") if row.get("resource_offset") is not None else -1) == resource_offset
        ],
    }

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("selected_sequence_ui.json", _json_bytes(sequence))
        archive.writestr("selected_candidate_ui.json", _json_bytes(candidate))
        archive.writestr("selected_catalog_sequence.json", _json_bytes(selected_catalog or {}))
        archive.writestr("selected_forensics_sequence.json", _json_bytes(selected_forensics or {}))
        archive.writestr("selected_sample_report.json", _json_bytes(filtered_sample_report))
        archive.writestr("normalized_sample_inventory.json", _json_bytes(sample_inventory))
        archive.writestr("last_preview_report.json", _json_bytes(preview or {}))

    return {
        "status": "written",
        "bundle_path": str(target),
        "bundle_version": BUNDLE_VERSION,
        "sequence_id": sequence_id,
        "program_resource_offset": resource_offset,
        "sample_inventory_rows": len(sample_inventory),
        "binary_data_included": False,
    }

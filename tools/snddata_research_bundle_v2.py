#!/usr/bin/env python3
"""Research bundles that include persistent flags and notes, never game binaries."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_sound_v1 import canonical_snddata_path, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_research_bundle_v1 import build_research_bundle
from snddata_research_workspace_v1 import flagged_records, load_workspace
from snddata_sample_bridge_v1 import normalized_sample_rows

BUNDLE_VERSION = 2


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def build_selected_research_bundle(
    project: FragmenterProjectV1,
    sequence: dict[str, Any],
    candidate: dict[str, Any],
    *,
    playback_backend: str = "unknown",
) -> dict[str, Any]:
    """Build the existing selected bundle and append the persistent research workspace."""
    result = build_research_bundle(
        project,
        sequence,
        candidate,
        playback_backend=playback_backend,
    )
    target = Path(str(result["bundle_path"]))
    workspace = load_workspace(project)
    flagged = flagged_records(project)
    with zipfile.ZipFile(target, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("research_workspace.json", _json_bytes(workspace))
        archive.writestr("flagged_assets.json", _json_bytes(flagged))
    return {
        **result,
        "bundle_version": BUNDLE_VERSION,
        "flagged_assets": len(flagged),
    }


def build_flagged_research_bundle(
    project: FragmenterProjectV1,
    *,
    playback_backend: str = "unknown",
) -> dict[str, Any]:
    """Export all flagged sequence/candidate/sample snapshots and matching report rows."""
    flags = flagged_records(project)
    if not flags:
        raise ValueError("No SNDDATA assets are flagged for a research bundle.")

    reports = sound_reports_root(project)
    source = canonical_snddata_path(project)
    catalog = _load_json(reports / "snddata_music_system_v5.json")
    forensics = _load_json(reports / "snddata_forensics_v1.json")
    sample_rows = normalized_sample_rows(project)
    sequence_ids = {str(row.get("sequence_id") or "") for row in flags if row.get("sequence_id")}
    sample_keys = {
        (int(row.get("resource_offset")), int(row.get("sample_id")))
        for row in flags
        if row.get("kind") == "sample"
        and row.get("resource_offset") is not None
        and row.get("sample_id") is not None
    }

    def selected_sequences(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        return [
            row
            for row in payload.get("sequences") or []
            if isinstance(row, dict) and str(row.get("sequence_id") or "") in sequence_ids
        ]

    selected_samples = [
        row
        for row in sample_rows
        if (int(row.get("resource_id") or -1), int(row.get("sample_id") or 0)) in sample_keys
        or any(
            flag.get("kind") == "candidate"
            and int(flag.get("resource_offset") or -2) == int(row.get("resource_id") or -1)
            for flag in flags
        )
    ]

    now = datetime.now(timezone.utc)
    output_dir = reports / "research_bundles"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"snddata_flagged_research_{now.strftime('%Y%m%dT%H%M%SZ')}.zip"
    source_stat = source.stat() if source.is_file() else None
    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "created_at": now.isoformat(),
        "project_file": str(project.project_path),
        "playback_backend": playback_backend,
        "flagged_asset_count": len(flags),
        "flagged_sequence_count": len(sequence_ids),
        "sample_inventory_rows": len(selected_samples),
        "source": {
            "path": str(source),
            "exists": source.is_file(),
            "size": source_stat.st_size if source_stat else 0,
            "mtime_ns": source_stat.st_mtime_ns if source_stat else 0,
        },
        "binary_data_included": False,
        "notes": "JSON/text research evidence only. No SNDDATA, WAV, PS-ADPCM, ISO, or game assets.",
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("research_workspace.json", _json_bytes(load_workspace(project)))
        archive.writestr("flagged_assets.json", _json_bytes(flags))
        archive.writestr("flagged_catalog_sequences.json", _json_bytes(selected_sequences(catalog)))
        archive.writestr("flagged_forensics_sequences.json", _json_bytes(selected_sequences(forensics)))
        archive.writestr("flagged_sample_inventory.json", _json_bytes(selected_samples))
    return {
        "status": "written",
        "bundle_path": str(target),
        "bundle_version": BUNDLE_VERSION,
        "flagged_assets": len(flags),
        "sample_inventory_rows": len(selected_samples),
        "binary_data_included": False,
    }

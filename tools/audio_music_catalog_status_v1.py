#!/usr/bin/env python3
"""Actionable diagnostics for Fragmenter's SNDDATA music catalogs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import audio_mixer_controller_v1 as mixer_v1
from audio_mapping_controller_v1 import resolve_project_snddata
from project_workspace_v1 import FragmenterProjectV1


def music_catalog_status(project: FragmenterProjectV1) -> dict[str, Any]:
    paths = mixer_v1.music_report_paths(project)
    reports = {
        name: {
            "path": str(path),
            "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else 0,
        }
        for name, path in paths.items()
    }
    try:
        snddata = resolve_project_snddata(project)
    except FileNotFoundError:
        snddata = None

    missing = [name for name, row in reports.items() if not bool(row["exists"])]
    if snddata is None:
        recommended = ("sound_extract", "sound_decode", "snddata_samples", "snddata_mixer")
        reason = "No canonical SNDDATA.BIN source is available to build the catalogs."
    elif missing:
        recommended = ("snddata_samples", "snddata_mixer")
        reason = "SNDDATA exists, but one or more mixer reports have not been generated."
    else:
        recommended = ()
        reason = "All required music catalogs are present."

    return {
        "ready": not missing and snddata is not None,
        "reason": reason,
        "snddata": str(snddata) if isinstance(snddata, Path) else "",
        "snddata_exists": isinstance(snddata, Path) and snddata.is_file(),
        "missing_catalogs": missing,
        "catalogs": reports,
        "recommended_stages": list(recommended),
        "writes_game_data": False,
    }


def music_catalog_message(status: dict[str, Any]) -> str:
    if bool(status.get("ready")):
        return "Music catalogs ready. Refresh the mixer to load sequences."
    missing = ", ".join(str(value) for value in status.get("missing_catalogs") or []) or "catalog set"
    stages = " → ".join(str(value) for value in status.get("recommended_stages") or [])
    suffix = f" Run: {stages}." if stages else ""
    return f"Music catalogs missing: {missing}. {status.get('reason') or ''}{suffix}"

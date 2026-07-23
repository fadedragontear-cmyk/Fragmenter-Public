#!/usr/bin/env python3
"""Create a lightweight Fragmenter next-session bundle from reports that already exist."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celdra_gremlin_memory_v1 import KNOWN_GREMLINS
from celdra_gremlin_memory_v2 import collection_complete, load_memory
from project_preflight_v1 import build_preflight
from project_setup_controller_v1 import load_setup_project
from public_library_cache_v1 import load_cache
from snddata_research_workbench_v1 import readiness


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _latest_files(root: Path, pattern: str, limit: int = 8) -> list[str]:
    if not root.is_dir():
        return []
    rows = [path for path in root.rglob(pattern) if path.is_file()]
    rows.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    return [str(path) for path in rows[:limit]]


def build_morning_research_bundle(project_file: str | Path) -> dict[str, Any]:
    project = load_setup_project(project_file)
    preflight = build_preflight(project)
    prepared = load_cache(project, "summary") or {}
    gremlins = load_memory()
    stable = [name for name in KNOWN_GREMLINS if name in set(gremlins.get("stable") or [])]
    legacy_stable = [name for name in KNOWN_GREMLINS if name in set(gremlins.get("legacy_stable") or [])]
    missing = [name for name in KNOWN_GREMLINS if name not in set(stable)]
    complete = collection_complete(gremlins)
    reward_seen = bool(gremlins.get("collection_reward_seen"))
    try:
        audio = readiness(project)
    except Exception as exc:
        audio = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}

    reports = project.workspace_path("reports")
    run_reports = project.workspace_path("run_reports")
    diagnostics = project.workspace_path("diagnostics")
    payload = {
        "version": 3,
        "created_at": _utc(),
        "project_file": str(project.project_path),
        "workspace": project.workspace_dir,
        "ready": bool(preflight.get("ready")),
        "blockers": list(preflight.get("blockers") or []),
        "prepared_lists": {
            "status": str(prepared.get("status") or "missing"),
            "visual_assets": int(prepared.get("visual_assets") or 0),
            "playable_sounds": int(prepared.get("playable_sounds") or 0),
            "snddata_sequences": int(prepared.get("snddata_sequences") or 0),
        },
        "gremlin_collection": {
            "collection_schema": str(gremlins.get("collection_schema") or "unknown"),
            "legacy_stable_archive": legacy_stable,
            "breakout_seen": bool(gremlins.get("breakout_seen")),
            "captured_count": len(stable),
            "captured": stable,
            "missing": missing,
            "complete": complete,
            "collection_reward_seen": reward_seen,
            "celdra_tab_expected": complete,
        },
        "audio_readiness": audio,
        "latest_run_reports": _latest_files(run_reports, "*.json", 6),
        "latest_audio_reports": _latest_files(reports / "audio", "*.json", 6),
        "latest_visual_reports": _latest_files(reports / "visual", "*.json", 6),
        "latest_diagnostics": _latest_files(diagnostics, "*.txt", 6),
        "next_session_checks": [
            "Confirm the collection schema is v109_individual_capture; legacy resident names may appear only in the archive, not the active stable.",
            "Confirm all 16 Run All stage bars are visible and update during a real scan.",
            "On fresh V109 collection state, confirm the stable introductions, full Run All breakout, recall, and dismissal remain intact.",
            "Confirm the completed main breakout is remembered and does not replay on returning Run All sessions.",
            "Confirm uncaptured Gremlins return individually and each performs its four-beat personality/ability skit.",
            "Confirm each skit ends with Celdra visibly wrangling that Gremlin into the persistent stable.",
            "Confirm the single status strip below the stable displays messages only from Gremlins currently captured.",
            "Confirm the top-level Celdra tab is absent below 9/9 and appears immediately when the stable reaches 9/9.",
            "Confirm the full-collection reward dialogue still plays independently after the ninth capture.",
            "Confirm the unlocked Tavern button opens the Discord invite in the default browser.",
            "Confirm speech bubbles remain opposite Celdra or below her headspace and all temporary skit effects clean up.",
            "Review the newest Run All, SNDDATA, visual, and prepared-list reports before changing parsers.",
        ],
    }

    output = diagnostics / "morning"
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "MORNING_RESEARCH_BUNDLE.json"
    text_path = output / "MORNING_RESEARCH_BUNDLE.txt"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(_render_text(payload), encoding="utf-8")
    return {
        "status": "complete",
        "json_path": str(json_path),
        "text_path": str(text_path),
        "workspace": project.workspace_dir,
    }


def _render_text(payload: dict[str, Any]) -> str:
    prepared = payload["prepared_lists"]
    gremlins = payload["gremlin_collection"]
    lines = [
        "FRAGMENTER MORNING RESEARCH BUNDLE",
        f"Created: {payload['created_at']}",
        f"Project: {payload['project_file']}",
        f"Workspace: {payload['workspace']}",
        f"Setup ready: {'yes' if payload['ready'] else 'no'}",
        f"Blockers: {', '.join(payload['blockers']) if payload['blockers'] else 'none'}",
        "",
        "Prepared lists:",
        f"- status: {prepared['status']}",
        f"- visual assets: {prepared['visual_assets']}",
        f"- playable sounds: {prepared['playable_sounds']}",
        f"- SNDDATA sequences: {prepared['snddata_sequences']}",
        "",
        "Gremlin collection:",
        f"- schema: {gremlins['collection_schema']}",
        f"- archived legacy residents: {', '.join(gremlins['legacy_stable_archive']) if gremlins['legacy_stable_archive'] else 'none'}",
        f"- main breakout seen: {'yes' if gremlins['breakout_seen'] else 'no'}",
        f"- captured: {gremlins['captured_count']}/9",
        f"- stable: {', '.join(gremlins['captured']) if gremlins['captured'] else 'empty'}",
        f"- missing: {', '.join(gremlins['missing']) if gremlins['missing'] else 'none'}",
        f"- full reward seen: {'yes' if gremlins['collection_reward_seen'] else 'no'}",
        f"- Celdra tab expected: {'yes' if gremlins['celdra_tab_expected'] else 'no'}",
        "",
        "Next-session checks:",
    ]
    lines.extend(f"{index}. {line}" for index, line in enumerate(payload["next_session_checks"], 1))
    for label, key in (
        ("Latest Run All reports", "latest_run_reports"),
        ("Latest audio reports", "latest_audio_reports"),
        ("Latest visual reports", "latest_visual_reports"),
        ("Latest diagnostics", "latest_diagnostics"),
    ):
        lines.extend(["", f"{label}:"])
        rows = payload[key]
        lines.extend(f"- {row}" for row in rows) if rows else lines.append("- none found")
    lines.extend(
        [
            "",
            "Morning handoff:",
            "Send MORNING_RESEARCH_BUNDLE.txt plus any newest report named above that looks relevant.",
            "This command only inventories existing evidence; it does not rerun extraction or audio analysis.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Path to project.json or its workspace folder")
    args = parser.parse_args()
    print(json.dumps(build_morning_research_bundle(args.project), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

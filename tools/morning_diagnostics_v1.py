#!/usr/bin/env python3
"""One-shot Fragmenter visual/audio research bundle for real-file acceptance runs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ccsf_asset_diagnostics_v1 import build_research_bundle
from ccsf_studioccs_compare_v1 import write_compare_report
from project_workspace_v1 import FragmenterProjectV1
from snddata_audition_matrix_v1 import render_audition_matrix
from snddata_forensics_v1 import analyze_and_write as analyze_snddata_forensics
from snddata_music_system_v5 import analyze_project_snddata

DEFAULT_ASSET_PATTERNS = ("ca1ab_bl", "aur1body", "aura")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("._") or "asset"


def locate_assets(project: FragmenterProjectV1, patterns: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    root = project.workspace_path("extracted_ccs")
    needles = [value.lower().strip() for value in (patterns or DEFAULT_ASSET_PATTERNS) if value.strip()]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not root.is_dir():
        return rows
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: str(path).lower())
    for needle in needles:
        matches = [path for path in files if needle in path.name.lower() or needle in path.as_posix().lower()]
        for path in matches[:5]:
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"pattern": needle, "path": str(path), "relative_path": path.relative_to(root).as_posix(), "size": path.stat().st_size})
    return rows


def _stage(callback: Callable[[dict[str, Any]], None] | None, name: str, status: str, **extra: Any) -> None:
    if callback is not None:
        callback({"kind": "morning_diagnostics", "stage": name, "status": status, **extra})


def run_morning_diagnostics(
    project: FragmenterProjectV1,
    *,
    asset_patterns: list[str] | tuple[str, ...] | None = None,
    audition_sequences: int = 12,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    root = project.workspace_path("diagnostics") / "morning"
    root.mkdir(parents=True, exist_ok=True)
    assets = locate_assets(project, asset_patterns)
    visual_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    _stage(callback, "visual", "start", assets=len(assets))
    for index, asset in enumerate(assets, 1):
        path = Path(asset["path"])
        output = root / "visual" / _safe(asset["relative_path"])
        row = dict(asset)
        try:
            research = build_research_bundle(path, output)
            compare = write_compare_report(path, output)
            row.update(
                {
                    "status": "complete",
                    "diagnostic_text": research["diagnostics"]["text_report_path"],
                    "diagnostic_json": research["diagnostics"]["report_path"],
                    "obj_path": research["obj"]["obj_path"],
                    "mtl_path": research["obj"]["mtl_path"],
                    "compare_text": compare["text_report_path"],
                    "compare_json": compare["report_path"],
                    "summary": research["diagnostics"]["summary"],
                    "selected_clump": research["diagnostics"]["selected_clump"],
                }
            )
        except Exception as exc:
            row.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            errors.append({"stage": "visual", "item": asset["relative_path"], "error": row["error"]})
        visual_rows.append(row)
        _stage(callback, "visual", "progress", current=index, total=len(assets), asset=asset["relative_path"], result=row["status"])
    _stage(callback, "visual", "finish", complete=sum(1 for row in visual_rows if row["status"] == "complete"), failed=sum(1 for row in visual_rows if row["status"] == "failed"))

    audio: dict[str, Any] = {}
    for stage_name, action in (
        ("music_catalog_v5", lambda: analyze_project_snddata(project, callback=callback)),
        ("snddata_forensics", lambda: analyze_snddata_forensics(project, callback=callback)),
        ("audition_matrix", lambda: render_audition_matrix(project, max_sequences=audition_sequences, callback=callback)),
    ):
        _stage(callback, stage_name, "start")
        try:
            audio[stage_name] = {"status": "complete", "result": action()}
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            audio[stage_name] = {"status": "failed", "error": message}
            errors.append({"stage": stage_name, "item": "snddata", "error": message})
        _stage(callback, stage_name, "finish", result=audio[stage_name]["status"])

    payload = {
        "version": 1,
        "created_at": _utc(),
        "project": str(project.project_path),
        "workspace": project.workspace_dir,
        "asset_patterns": list(asset_patterns or DEFAULT_ASSET_PATTERNS),
        "visual_assets": visual_rows,
        "audio": audio,
        "errors": errors,
        "summary": {
            "visual_assets_found": len(assets),
            "visual_assets_complete": sum(1 for row in visual_rows if row["status"] == "complete"),
            "visual_assets_failed": sum(1 for row in visual_rows if row["status"] == "failed"),
            "audio_stages_complete": sum(1 for row in audio.values() if row["status"] == "complete"),
            "audio_stages_failed": sum(1 for row in audio.values() if row["status"] == "failed"),
            "errors": len(errors),
        },
    }
    json_path = root / "MORNING_DIAGNOSTICS.json"
    text_path = root / "MORNING_DIAGNOSTICS.txt"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(_render_text(payload), encoding="utf-8")
    return {**payload["summary"], "report_path": str(json_path), "text_report_path": str(text_path), "output_root": str(root)}


def _render_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "FRAGMENTER MORNING DIAGNOSTICS",
        f"Created: {payload['created_at']}",
        f"Project: {payload['project']}",
        f"Workspace: {payload['workspace']}",
        "",
        f"Visual: found {summary['visual_assets_found']} | complete {summary['visual_assets_complete']} | failed {summary['visual_assets_failed']}",
        "",
        "Visual assets:",
    ]
    for row in payload["visual_assets"]:
        lines.append(f"- {row['relative_path']} [{row['status']}]")
        if row["status"] == "complete":
            diag = row.get("summary") or {}
            clump = row.get("selected_clump") or {}
            lines.append(
                f"    clump={clump.get('clump_id')} {clump.get('clump_name')} submodels={diag.get('submodels')} faces={diag.get('faces')} texture_links={diag.get('decoded_texture_links')}/{diag.get('submodels')} head={diag.get('head_texture_links_decoded')}/{diag.get('head_submodels')}"
            )
            lines.append(f"    SEND: {row['diagnostic_text']}")
            lines.append(f"    COMPARE: {row['compare_text']}")
            lines.append(f"    OBJ: {row['obj_path']}")
        else:
            lines.append(f"    ERROR: {row.get('error')}")
    lines.extend(["", "Audio:"])
    for name, row in payload["audio"].items():
        lines.append(f"- {name}: {row['status']}")
        if row["status"] == "complete":
            result = row.get("result") or {}
            if name == "music_catalog_v5":
                lines.append(
                    f"    sequences={result.get('sequence_resources')} tracks={result.get('sequences_with_tracks')} notes={result.get('sequences_with_notes')} ProgramChange={result.get('sequences_with_program_changes')} preferred_renderable={result.get('preferred_renderable_candidates')}"
                )
                lines.append(f"    catalog={result.get('report_path')}")
            elif name == "snddata_forensics":
                lines.append(
                    f"    ProgramChange complete={result.get('program_change_complete_inputs')} | channel->Program complete={result.get('channel_as_program_complete_inputs')} | SCEISequ matches={result.get('sequences_with_sequ_program_matches')}"
                )
                lines.append(f"    SEND: {result.get('text_report_path')}")
            elif name == "audition_matrix":
                lines.append(f"    outputs={result.get('outputs')} rendered={result.get('rendered')} no_pcm={result.get('no_pcm_frames')} errors={result.get('render_errors')}")
                lines.append(f"    manifest={result.get('manifest_path')}")
                lines.append(f"    LISTEN: {result.get('output_root')}")
        else:
            lines.append(f"    ERROR: {row.get('error')}")
    if payload["errors"]:
        lines.extend(["", "Errors:"])
        for row in payload["errors"]:
            lines.append(f"- {row['stage']} / {row['item']}: {row['error']}")
    lines.extend(
        [
            "",
            "Morning handoff:",
            "1. Send MORNING_DIAGNOSTICS.txt.",
            "2. Send the asset_diagnostic.txt and fragmenter_studioccs_compare.txt for ca1ab_bl if generated.",
            "3. Send snddata_forensics_v1.txt.",
            "4. Listen to any WAVs in sound/decoded/audition_matrix and report which are recognizable music, rhythm, or coherent layered audio.",
        ]
    )
    return "\n".join(lines) + "\n"

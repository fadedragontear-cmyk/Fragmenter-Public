#!/usr/bin/env python3
"""Fragmenter public RUN ALL v3 with canonical ``project/sound`` audio stages."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

import run_all_executor_v1 as v1
import run_all_executor_v2 as v2
from project_preflight_v1 import require_ready_project
from project_sound_v1 import (
    build_project_sound_library,
    decode_project_sound_sources,
    extract_project_sound_sources,
    sound_reports_root,
)
from project_workspace_v1 import FragmenterProjectV1
from snddata_pipeline_v3 import analyze_project_snddata


def build_run_all_actions_v3(
    project: FragmenterProjectV1,
    *,
    python_executable: str | Path | None = None,
    tools_dir: str | Path | None = None,
) -> list[v1.RunAction]:
    paths = require_ready_project(project)
    old = v2.build_run_all_actions_v2(project, python_executable=python_executable, tools_dir=tools_dir)
    reports = sound_reports_root(project)
    replacements = {
        "known_audio_extract": v1.RunAction(
            "sound_extract",
            "Extract Project Sound",
            "internal",
            internal="extract_project_sound",
            inputs=(str(paths.iso), str(paths.cache_iso / "iso_index.json")),
            outputs=(str(reports / "sound_source_manifest.json"), str(paths.workspace / "sound" / "source")),
        ),
        "known_audio_decode": v1.RunAction(
            "sound_decode",
            "Decode Project Sound",
            "internal",
            internal="decode_project_sound",
            inputs=(str(paths.workspace / "sound" / "source"),),
            outputs=(str(reports / "sound_decode_report.json"), str(paths.workspace / "sound" / "decoded")),
        ),
        "snddata": v1.RunAction(
            "snddata_v3",
            "Analyze SNDDATA Music System",
            "internal",
            internal="analyze_project_snddata_v3",
            inputs=(str(paths.workspace / "sound" / "source" / "data" / "snddata.bin"),),
            outputs=(str(reports / "snddata_music_system_v3.json"), str(reports / "snddata_pipeline_summary_v3.json")),
        ),
        "refresh": v1.RunAction(
            "refresh",
            "Refresh Public Libraries",
            "internal",
            internal="refresh_public_libraries",
            inputs=(str(paths.reports / "asset_library.json"), str(paths.workspace / "sound")),
            outputs=(str(reports / "sound_library.json"),),
        ),
    }
    return [replacements.get(action.key, action) for action in old]


def _progress_bridge(callback: Callable[[dict[str, Any]], None] | None, stage: str):
    def emit(payload: dict[str, Any]) -> None:
        if callback is None:
            return
        current = int(payload.get("current") or 0)
        total = int(payload.get("total") or 0)
        percent = min(100.0, current * 100.0 / total) if current and total else None
        detail = payload.get("iso_path") or payload.get("relative_path") or ""
        v1._event(callback, stage=stage, kind="progress", current=current, total=total, percent=percent, detail=detail, source_event=payload)
    return emit


def _run_internal_v3(action: v1.RunAction, project: FragmenterProjectV1, paths, callback: Callable[[dict[str, Any]], None] | None) -> dict[str, Any]:
    if action.internal == "extract_project_sound":
        return extract_project_sound_sources(project, callback=_progress_bridge(callback, action.key))
    if action.internal == "decode_project_sound":
        return decode_project_sound_sources(project, callback=_progress_bridge(callback, action.key))
    if action.internal == "analyze_project_snddata_v3":
        return analyze_project_snddata(project)
    if action.internal == "refresh_public_libraries":
        library = build_project_sound_library(project)
        return {"sound_library": str(sound_reports_root(project) / "sound_library.json"), "summary": library["summary"]}
    return v2._run_internal_v2(action, project, paths)


def execute_run_all_v3(
    project: FragmenterProjectV1,
    *,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = require_ready_project(project)
    plan = v1.build_run_all_plan(project)
    actions = build_run_all_actions_v3(project)
    state = v1.load_run_state(paths)
    state.setdefault("stages", {})
    results: list[v1.StageResult] = []
    runner = subprocess_runner or v1._run_subprocess

    for action in actions:
        started = v1._utc_iso()
        v1._event(callback, stage=action.key, label=action.label, kind="start")
        if cancel_event is not None and cancel_event.is_set():
            results.append(v1.StageResult(action.key, action.label, "cancelled", started, v1._utc_iso(), "Cancellation requested before stage start."))
            break
        executable_action = action
        try:
            if action.kind == "dynamic_subprocess":
                executable_action = v1._dynamic_action(action, project, paths)
            if reuse and v1.action_reusable(executable_action, state):
                result = v1.StageResult(action.key, action.label, "reused", started, v1._utc_iso(), "Matching inputs and outputs were reused.")
            elif executable_action.kind == "internal":
                payload = _run_internal_v3(executable_action, project, paths, callback)
                if executable_action.internal == "audit_extraction" and payload.get("status") == "blocked":
                    result = v1.StageResult(action.key, action.label, "failed", started, v1._utc_iso(), "; ".join(payload.get("blockers") or []), [payload])
                else:
                    result = v1.StageResult(action.key, action.label, "complete", started, v1._utc_iso(), actions=[payload])
            else:
                payload = runner(executable_action, callback=callback, cancel_event=cancel_event)
                status = str(payload.get("status") or "failed")
                message = ""
                if status == "failed":
                    output = payload.get("output") or []
                    message = str(output[-1]) if output else f"Subprocess exited with {payload.get('returncode')}"
                result = v1.StageResult(action.key, action.label, status, started, v1._utc_iso(), message, [payload])
            results.append(result)
            if result.status in {"failed", "cancelled"}:
                v1._event(callback, stage=action.key, label=action.label, kind="finish", status=result.status, error=result.message)
                break
            state["stages"][executable_action.key] = {"completed_at": result.finished_at, "input_digest": v1.action_input_digest(executable_action), "outputs": list(executable_action.outputs)}
            v1.save_run_state(paths, state)
            v1._event(callback, stage=action.key, label=action.label, kind="finish", status=result.status)
        except Exception as exc:
            result = v1.StageResult(action.key, action.label, "failed", started, v1._utc_iso(), f"{type(exc).__name__}: {exc}")
            results.append(result)
            v1._event(callback, stage=action.key, label=action.label, kind="finish", status="failed", error=result.message)
            break

    rows = [result.to_dict() for result in results]
    scan_json, scan_text = v1.write_scan_summary(project, rows)
    overall = "complete"
    if any(row["status"] == "failed" for row in rows):
        overall = "failed"
    elif any(row["status"] == "cancelled" for row in rows):
        overall = "cancelled"
    elif len(rows) != len(actions):
        overall = "partial"
    return {"version": 3, "origin": "RUN ALL", "status": overall, "workspace": str(paths.workspace), "plan": plan, "results": rows, "scan_summary_json": str(scan_json), "scan_summary_text": str(scan_text), "sound_root": str(paths.workspace / "sound")}

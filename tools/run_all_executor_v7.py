#!/usr/bin/env python3
"""RUN ALL v7 with visible, reusable SNDDATA stages and no monkey-patch recursion."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

import project_sound_v4 as sound_v4
import run_all_executor_v1 as v1
import run_all_executor_v6 as v6
from project_preflight_v1 import require_ready_project
from project_sound_v6 import build_project_sound_library, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_sample_library_v2 import extract_project_snddata_samples, project_paths as snddata_sample_paths

# Capture the validated v6 authorities once. Never overwrite the v6 module globals:
# the previous implementation did that and then called its own replacement recursively.
_BASE_BUILD_ACTIONS = v6.build_run_all_actions_v6
_BASE_RUN_INTERNAL = v6._run_internal_v6


def _progress_bridge(callback: Callable[[dict[str, Any]], None] | None, stage: str):
    def emit(payload: dict[str, Any]) -> None:
        if callback is None:
            return
        current = int(payload.get("current") or 0)
        total = int(payload.get("total") or 0)
        percent = min(100.0, current * 100.0 / total) if current and total else None
        kind = str(payload.get("kind") or "")
        detail = str(payload.get("iso_path") or payload.get("relative_path") or "")
        if kind == "snddata_sample_extract_progress":
            offset = int(payload.get("resource_offset") or 0)
            detail = f"SNDDATA sample banks {current:,}/{total:,} @ 0x{offset:08X}"
        elif kind == "raw_pcm_import_progress":
            detail = f"Legacy raw-PCM research preview {current:,}/{total:,}: {detail}"
        elif kind == "snddata_catalog_progress":
            detail = f"SNDDATA resources {current:,}/{total:,}; sequences {int(payload.get('sequences') or 0):,}"
        v1._event(
            callback,
            stage=stage,
            kind="progress",
            current=current,
            total=total,
            percent=percent,
            detail=detail,
            source_event=payload,
        )

    return emit


def build_run_all_actions_v7(
    project: FragmenterProjectV1,
    *,
    python_executable: str | Path | None = None,
    tools_dir: str | Path | None = None,
) -> list[v1.RunAction]:
    """Build a stable plan with sample extraction as its own reusable stage."""
    old = _BASE_BUILD_ACTIONS(project, python_executable=python_executable, tools_dir=tools_dir)
    _source, _output, sample_report, sample_csv = snddata_sample_paths(project)
    sample_action = v1.RunAction(
        "snddata_samples",
        "Extract SNDDATA Sample Banks",
        "internal",
        internal="extract_snddata_samples_v2",
        inputs=(str(_source),),
        outputs=(str(sample_report), str(sample_csv)),
    )

    actions: list[v1.RunAction] = []
    inserted_samples = False
    for action in old:
        if action.key == "sound_decode":
            # Keep verified container decoding independent from the large SNDDATA
            # sample-bank extraction so either result can be reused separately.
            action = v1.RunAction(
                "sound_decode",
                "Decode Verified Sound Containers",
                "internal",
                internal="decode_project_sound_v4",
                inputs=action.inputs,
                outputs=action.outputs,
            )
        elif action.key == "refresh":
            action = v1.RunAction(
                "refresh",
                "Refresh Public Audio Libraries",
                "internal",
                internal="refresh_public_libraries_v7",
                inputs=action.inputs,
                outputs=action.outputs,
            )
        actions.append(action)
        if action.key == "snddata_v4":
            actions.append(sample_action)
            inserted_samples = True

    if not inserted_samples:
        refresh_index = next((index for index, action in enumerate(actions) if action.key == "refresh"), len(actions))
        actions.insert(refresh_index, sample_action)
    return actions


def _run_internal_v7(
    action: v1.RunAction,
    project: FragmenterProjectV1,
    paths,
    callback: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    bridge = _progress_bridge(callback, action.key)
    if action.internal == "decode_project_sound_v4":
        return sound_v4.decode_project_sound_sources(project, callback=bridge)
    if action.internal == "extract_snddata_samples_v2":
        return extract_project_snddata_samples(project, clean=True, callback=bridge)
    if action.internal == "refresh_public_libraries_v7":
        library = build_project_sound_library(project)
        return {
            "sound_library": str(sound_reports_root(project) / "sound_library.json"),
            "summary": library["summary"],
        }
    return _BASE_RUN_INTERNAL(action, project, paths, callback)


def execute_run_all_v7(
    project: FragmenterProjectV1,
    *,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = require_ready_project(project)
    plan = v1.build_run_all_plan(project)
    actions = build_run_all_actions_v7(project)
    state = v1.load_run_state(paths)
    state.setdefault("stages", {})
    results: list[v1.StageResult] = []
    runner = subprocess_runner or v1._run_subprocess

    for action in actions:
        started = v1._utc_iso()
        v1._event(callback, stage=action.key, label=action.label, kind="start")
        if cancel_event is not None and cancel_event.is_set():
            results.append(
                v1.StageResult(
                    action.key,
                    action.label,
                    "cancelled",
                    started,
                    v1._utc_iso(),
                    "Cancellation requested before stage start.",
                )
            )
            break
        executable_action = action
        try:
            if action.kind == "dynamic_subprocess":
                executable_action = v1._dynamic_action(action, project, paths)
            if reuse and v1.action_reusable(executable_action, state):
                result = v1.StageResult(
                    action.key,
                    action.label,
                    "reused",
                    started,
                    v1._utc_iso(),
                    "Matching inputs and outputs were reused.",
                )
            elif executable_action.kind == "internal":
                payload = _run_internal_v7(executable_action, project, paths, callback)
                if executable_action.internal == "audit_extraction" and payload.get("status") == "blocked":
                    result = v1.StageResult(
                        action.key,
                        action.label,
                        "failed",
                        started,
                        v1._utc_iso(),
                        "; ".join(payload.get("blockers") or []),
                        [payload],
                    )
                else:
                    result = v1.StageResult(
                        action.key,
                        action.label,
                        "complete",
                        started,
                        v1._utc_iso(),
                        actions=[payload],
                    )
            else:
                payload = runner(executable_action, callback=callback, cancel_event=cancel_event)
                status = str(payload.get("status") or "failed")
                message = ""
                if status == "failed":
                    output = payload.get("output") or []
                    message = str(output[-1]) if output else f"Subprocess exited with {payload.get('returncode')}"
                result = v1.StageResult(
                    action.key,
                    action.label,
                    status,
                    started,
                    v1._utc_iso(),
                    message,
                    [payload],
                )
            results.append(result)
            if result.status in {"failed", "cancelled"}:
                v1._event(
                    callback,
                    stage=action.key,
                    label=action.label,
                    kind="finish",
                    status=result.status,
                    error=result.message,
                )
                break
            state["stages"][executable_action.key] = {
                "completed_at": result.finished_at,
                "input_digest": v1.action_input_digest(executable_action),
                "outputs": list(executable_action.outputs),
            }
            v1.save_run_state(paths, state)
            v1._event(callback, stage=action.key, label=action.label, kind="finish", status=result.status)
        except Exception as exc:
            result = v1.StageResult(
                action.key,
                action.label,
                "failed",
                started,
                v1._utc_iso(),
                f"{type(exc).__name__}: {exc}",
            )
            results.append(result)
            v1._event(
                callback,
                stage=action.key,
                label=action.label,
                kind="finish",
                status="failed",
                error=result.message,
            )
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
    return {
        "version": 7,
        "origin": "RUN ALL",
        "status": overall,
        "workspace": str(paths.workspace),
        "plan": plan,
        "results": rows,
        "scan_summary_json": str(scan_json),
        "scan_summary_text": str(scan_text),
        "sound_root": str(paths.workspace / "sound"),
    }


# Compatibility names used by the layered GUI modules.
build_run_all_actions_v6 = build_run_all_actions_v7
execute_run_all_v6 = execute_run_all_v7

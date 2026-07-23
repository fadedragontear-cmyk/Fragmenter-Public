#!/usr/bin/env python3
"""Public RUN ALL v2: full core DATA.BIN scan plus extraction audit.

This wraps the validated v1 executor without changing the preserved implementation.
The original 256 MiB per-container cap can omit late DATA.BIN assets, so the public
release line raises the focused scan bound to 2 GiB, permits larger individual CCSF
bundles, and audits actual bytes scanned.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

import run_all_executor_v1 as v1
from extraction_audit_v1 import audit_extraction
from project_preflight_v1 import require_ready_project
from project_workspace_v1 import FragmenterProjectV1

CORE_SCAN_BYTES = 2 * 1024 * 1024 * 1024
CORE_EXTRACT_CAP = 128 * 1024 * 1024
CORE_CONTAINER_LIMIT = 500


def build_run_all_actions_v2(
    project: FragmenterProjectV1,
    *,
    python_executable: str | Path | None = None,
    tools_dir: str | Path | None = None,
) -> list[v1.RunAction]:
    paths = require_ready_project(project)
    actions = v1.build_run_all_actions(project, python_executable=python_executable, tools_dir=tools_dir)
    patched: list[v1.RunAction] = []
    for action in actions:
        if action.key != "ccsf_extract":
            patched.append(action)
            continue
        argv = list(action.argv)
        argv.extend(
            (
                "--max-scan-bytes",
                str(CORE_SCAN_BYTES),
                "--extract-cap",
                str(CORE_EXTRACT_CAP),
                "--container-limit",
                str(CORE_CONTAINER_LIMIT),
            )
        )
        patched.append(
            v1.RunAction(
                key=action.key,
                label=action.label,
                kind=action.kind,
                argv=tuple(argv),
                internal=action.internal,
                inputs=action.inputs,
                outputs=action.outputs,
            )
        )
    audit_output = paths.reports / "extraction_audit.json"
    insert_at = next((index + 1 for index, action in enumerate(patched) if action.key == "asset_library"), len(patched))
    patched.insert(
        insert_at,
        v1.RunAction(
            key="extraction_audit",
            label="Audit CCSF Extraction",
            kind="internal",
            internal="audit_extraction",
            inputs=(
                str(paths.reports / "iso_ccsf_extraction_index.json"),
                str(paths.reports / "asset_library.json"),
                str(paths.cache_iso / "iso_index.json"),
            ),
            outputs=(str(audit_output),),
        ),
    )
    return patched


def _run_internal_v2(action: v1.RunAction, project: FragmenterProjectV1, paths) -> dict[str, Any]:
    if action.internal == "audit_extraction":
        return audit_extraction(project)
    return v1._run_internal(action, project, paths)


def execute_run_all_v2(
    project: FragmenterProjectV1,
    *,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = require_ready_project(project)
    plan = v1.build_run_all_plan(project)
    actions = build_run_all_actions_v2(project)
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
                payload = _run_internal_v2(executable_action, project, paths)
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
            state["stages"][executable_action.key] = {
                "completed_at": result.finished_at,
                "input_digest": v1.action_input_digest(executable_action),
                "outputs": list(executable_action.outputs),
            }
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
    return {
        "version": 2,
        "origin": "RUN ALL",
        "status": overall,
        "workspace": str(paths.workspace),
        "plan": plan,
        "results": rows,
        "scan_summary_json": str(scan_json),
        "scan_summary_text": str(scan_text),
        "core_scan_bytes": CORE_SCAN_BYTES,
        "core_extract_cap": CORE_EXTRACT_CAP,
        "extraction_audit": str(paths.reports / "extraction_audit.json"),
    }

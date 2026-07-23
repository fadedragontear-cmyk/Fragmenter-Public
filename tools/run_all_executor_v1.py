#!/usr/bin/env python3
"""Cancellable, project-bound Fragmenter 1.0 RUN ALL executor.

The executor composes existing proven command-line tools with new project catalog
writers. It never invokes Deep Disc Discovery and never falls back to the repository
``workspace`` directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from audio_mapping_controller_v1 import find_project_snddata
from project_catalogs_v1 import (
    build_visual_catalogs,
    write_audio_library,
    write_memory_card_identity,
    write_scan_summary,
    write_server_index,
    write_server_save_index,
)
from project_preflight_v1 import ProjectRuntimePaths, require_ready_project
from project_workspace_v1 import FragmenterProjectV1, source_identity, write_project_status
from report_locator_v1 import write_diagnostics_summary
from run_all_plan_v1 import build_run_all_plan

TOOLS = Path(__file__).resolve().parent
STATE_FILENAME = "run_all_state.json"
MAX_CAPTURED_LINES = 200


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RunAction:
    key: str
    label: str
    kind: str
    argv: tuple[str, ...] = ()
    internal: str = ""
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageResult:
    key: str
    label: str
    status: str
    started_at: str
    finished_at: str
    message: str = ""
    actions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _path(value: Path) -> str:
    return str(value)


def build_run_all_actions(
    project: FragmenterProjectV1,
    *,
    python_executable: str | Path | None = None,
    tools_dir: str | Path | None = None,
) -> list[RunAction]:
    paths = require_ready_project(project)
    py = str(python_executable or sys.executable)
    tools = Path(tools_dir).expanduser() if tools_dir is not None else TOOLS
    iso_index = paths.cache_iso / "iso_index.json"
    extraction_json = paths.reports / "iso_ccsf_extraction_index.json"
    extraction_text = paths.reports / "iso_ccsf_extraction_index.txt"
    media_summary = paths.media_pipeline / "reports" / "iso_media_pipeline_summary.json"
    snddata_summary = paths.reports / "snddata_pipeline_summary.json"

    return [
        RunAction(
            "project_check",
            "Validate Project",
            "internal",
            internal="write_project_status",
            inputs=(_path(paths.iso), _path(paths.area_server_root), _path(paths.server_saves), _path(paths.memory_card)),
            outputs=(_path(paths.reports / "project_status.json"),),
        ),
        RunAction(
            "iso_index",
            "Index ISO Filesystem",
            "subprocess",
            argv=(py, str(tools / "iso_index.py"), _path(paths.iso), "--out", _path(iso_index)),
            inputs=(_path(paths.iso),),
            outputs=(_path(iso_index),),
        ),
        RunAction(
            "ccsf_extract",
            "Extract CCSF Library",
            "subprocess",
            argv=(
                py,
                str(tools / "iso_ccsf_extractor.py"),
                _path(paths.iso),
                "--iso-index",
                _path(iso_index),
                "--workspace",
                _path(paths.workspace),
                "--out",
                _path(extraction_json),
                "--text-out",
                _path(extraction_text),
                "--reuse-existing",
                "--index-assets",
                "--ccsf-only",
                "--progress-jsonl",
            ),
            inputs=(_path(paths.iso), _path(iso_index)),
            outputs=(_path(extraction_json), _path(paths.reports / "asset_library.json"), _path(paths.extracted_ccs)),
        ),
        RunAction(
            "asset_library",
            "Build Asset Library",
            "internal",
            internal="verify_asset_library",
            inputs=(_path(extraction_json), _path(paths.extracted_ccs)),
            outputs=(_path(paths.reports / "asset_library.json"),),
        ),
        RunAction(
            "visual_catalogs",
            "Prepare Visual Catalogs",
            "internal",
            internal="build_visual_catalogs",
            inputs=(_path(paths.reports / "asset_library.json"),),
            outputs=(_path(paths.reports / "texture_catalog.json"), _path(paths.reports / "animation_catalog.json")),
        ),
        RunAction(
            "known_audio_extract",
            "Prepare Known Audio: Extract",
            "subprocess",
            argv=(
                py,
                str(tools / "iso_media_pipeline.py"),
                _path(paths.iso),
                "--workspace",
                _path(paths.workspace),
                "--mode",
                "extract",
                "--known-media-targets",
                "--hash",
                "--max-output-mb",
                "2048",
            ),
            inputs=(_path(paths.iso), _path(iso_index)),
            outputs=(_path(paths.media_pipeline / "reports" / "iso_media_extraction.json"),),
        ),
        RunAction(
            "known_audio_decode",
            "Prepare Known Audio: Decode",
            "subprocess",
            argv=(
                py,
                str(tools / "iso_media_pipeline.py"),
                _path(paths.iso),
                "--workspace",
                _path(paths.workspace),
                "--mode",
                "decode",
                "--decode-audio",
            ),
            inputs=(_path(paths.media_pipeline / "reports" / "iso_media_extraction.json"),),
            outputs=(_path(media_summary), _path(paths.media_pipeline / "reports" / "iso_media_decode.json")),
        ),
        RunAction(
            "snddata",
            "Analyze SNDDATA",
            "dynamic_subprocess",
            internal="snddata_command",
            inputs=(_path(paths.media_pipeline),),
            outputs=(_path(snddata_summary),),
        ),
        RunAction(
            "server_index",
            "Index Area Server",
            "internal",
            internal="write_server_index",
            inputs=(_path(paths.area_server_root),),
            outputs=(_path(paths.reports / "server_index.json"),),
        ),
        RunAction(
            "server_saves",
            "Index Server Saves",
            "internal",
            internal="write_server_save_index",
            inputs=(_path(paths.server_saves),),
            outputs=(_path(paths.reports / "server_save_index.json"),),
        ),
        RunAction(
            "memory_card",
            "Verify Memory Card",
            "internal",
            internal="write_memory_card_identity",
            inputs=(_path(paths.memory_card),),
            outputs=(_path(paths.reports / "memory_card_identity.json"),),
        ),
        RunAction(
            "refresh",
            "Refresh Libraries",
            "internal",
            internal="refresh_catalogs",
            inputs=(_path(paths.reports / "asset_library.json"), _path(paths.media_pipeline)),
            outputs=(_path(paths.reports / "audio_library.json"), _path(paths.reports / "diagnostics_summary.txt")),
        ),
    ]


def _fingerprint_path(value: str) -> dict[str, Any]:
    path = Path(value)
    if path.is_file():
        stat = path.stat()
        return {"path": str(path.resolve()), "kind": "file", "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if path.is_dir():
        rows: list[tuple[str, int, int]] = []
        for child in sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: str(item).lower()):
            stat = child.stat()
            rows.append((child.relative_to(path).as_posix(), stat.st_size, stat.st_mtime_ns))
        return {"path": str(path.resolve()), "kind": "directory", "files": rows}
    return {"path": str(path), "kind": "missing"}


def action_input_digest(action: RunAction) -> str:
    payload = {"key": action.key, "argv": action.argv, "internal": action.internal, "inputs": [_fingerprint_path(value) for value in action.inputs]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _outputs_exist(action: RunAction) -> bool:
    return bool(action.outputs) and all(Path(value).exists() for value in action.outputs)


def _state_path(paths: ProjectRuntimePaths) -> Path:
    return paths.cache_iso.parent / STATE_FILENAME


def load_run_state(paths: ProjectRuntimePaths) -> dict[str, Any]:
    target = _state_path(paths)
    if not target.is_file():
        return {"version": 1, "stages": {}}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "stages": {}}
    return payload if isinstance(payload, dict) and isinstance(payload.get("stages"), dict) else {"version": 1, "stages": {}}


def save_run_state(paths: ProjectRuntimePaths, state: dict[str, Any]) -> Path:
    target = _state_path(paths)
    target.parent.mkdir(parents=True, exist_ok=True)
    state["version"] = 1
    state["updated_at"] = _utc_iso()
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return target


def action_reusable(action: RunAction, state: dict[str, Any]) -> bool:
    record = (state.get("stages") or {}).get(action.key)
    return isinstance(record, dict) and record.get("input_digest") == action_input_digest(action) and _outputs_exist(action)


def _event(callback: Callable[[dict[str, Any]], None] | None, **payload: Any) -> None:
    if callback is not None:
        callback({"at": _utc_iso(), "origin": "RUN ALL", **payload})


def _run_subprocess(
    action: RunAction,
    *,
    callback: Callable[[dict[str, Any]], None] | None,
    cancel_event: threading.Event | None,
) -> dict[str, Any]:
    process = subprocess.Popen(
        list(action.argv),
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line.rstrip("\r\n"))
        lines.put(None)

    threading.Thread(target=reader, daemon=True, name=f"run-all-{action.key}-output").start()
    captured: list[str] = []
    stream_closed = False
    while True:
        if cancel_event is not None and cancel_event.is_set() and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            return {"status": "cancelled", "returncode": process.returncode, "output": captured}
        try:
            line = lines.get(timeout=0.1)
        except queue.Empty:
            line = ""
        if line is None:
            stream_closed = True
        elif line:
            captured.append(line)
            captured = captured[-MAX_CAPTURED_LINES:]
            _event(callback, stage=action.key, kind="output", line=line)
        if process.poll() is not None and stream_closed:
            break
    return {"status": "complete" if process.returncode == 0 else "failed", "returncode": process.returncode, "output": captured}


def _dynamic_action(action: RunAction, project: FragmenterProjectV1, paths: ProjectRuntimePaths) -> RunAction:
    if action.internal != "snddata_command":
        raise ValueError(f"Unknown dynamic action: {action.internal}")
    source = find_project_snddata(project)
    if source is None:
        raise FileNotFoundError(f"No SNDDATA.BIN found under {paths.media_pipeline}")
    return RunAction(
        key=action.key,
        label=action.label,
        kind="subprocess",
        argv=(sys.executable, str(TOOLS / "snddata_pipeline.py"), str(source), "--workspace", str(paths.workspace)),
        inputs=(str(source),),
        outputs=action.outputs,
    )


def _run_internal(action: RunAction, project: FragmenterProjectV1, paths: ProjectRuntimePaths) -> dict[str, Any]:
    if action.internal == "write_project_status":
        json_path, text_path = write_project_status(project)
        return {"json": str(json_path), "text": str(text_path)}
    if action.internal == "verify_asset_library":
        target = paths.reports / "asset_library.json"
        if not target.is_file():
            raise FileNotFoundError(target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        return {"path": str(target), "asset_count": int(payload.get("asset_count") or len(payload.get("assets") or []))}
    if action.internal == "build_visual_catalogs":
        return build_visual_catalogs(project)
    if action.internal == "write_server_index":
        return {"path": str(write_server_index(project))}
    if action.internal == "write_server_save_index":
        return {"path": str(write_server_save_index(project))}
    if action.internal == "write_memory_card_identity":
        return {"path": str(write_memory_card_identity(project))}
    if action.internal == "refresh_catalogs":
        audio = write_audio_library(project)
        diagnostics = write_diagnostics_summary(project)
        return {"audio_library": str(audio), "diagnostics_summary": str(diagnostics)}
    raise ValueError(f"Unknown internal RUN ALL action: {action.internal}")


def execute_run_all(
    project: FragmenterProjectV1,
    *,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = require_ready_project(project)
    plan = build_run_all_plan(project)
    actions = build_run_all_actions(project)
    state = load_run_state(paths)
    state.setdefault("stages", {})
    results: list[StageResult] = []
    runner = subprocess_runner or _run_subprocess

    for action in actions:
        started = _utc_iso()
        _event(callback, stage=action.key, label=action.label, kind="start")
        if cancel_event is not None and cancel_event.is_set():
            results.append(StageResult(action.key, action.label, "cancelled", started, _utc_iso(), "Cancellation requested before stage start."))
            break
        executable_action = action
        try:
            if action.kind == "dynamic_subprocess":
                executable_action = _dynamic_action(action, project, paths)
            if reuse and action_reusable(executable_action, state):
                result = StageResult(action.key, action.label, "reused", started, _utc_iso(), "Matching inputs and outputs were reused.")
            elif executable_action.kind == "internal":
                payload = _run_internal(executable_action, project, paths)
                result = StageResult(action.key, action.label, "complete", started, _utc_iso(), actions=[payload])
            else:
                payload = runner(executable_action, callback=callback, cancel_event=cancel_event)
                status = str(payload.get("status") or "failed")
                message = ""
                if status == "failed":
                    output = payload.get("output") or []
                    message = str(output[-1]) if output else f"Subprocess exited with {payload.get('returncode')}"
                result = StageResult(action.key, action.label, status, started, _utc_iso(), message, [payload])
            results.append(result)
            if result.status in {"failed", "cancelled"}:
                break
            state["stages"][executable_action.key] = {
                "completed_at": result.finished_at,
                "input_digest": action_input_digest(executable_action),
                "outputs": list(executable_action.outputs),
            }
            save_run_state(paths, state)
            _event(callback, stage=action.key, label=action.label, kind="finish", status=result.status)
        except Exception as exc:
            result = StageResult(action.key, action.label, "failed", started, _utc_iso(), f"{type(exc).__name__}: {exc}")
            results.append(result)
            _event(callback, stage=action.key, label=action.label, kind="finish", status="failed", error=result.message)
            break

    rows = [result.to_dict() for result in results]
    scan_json, scan_text = write_scan_summary(project, rows)
    overall = "complete"
    if any(row["status"] == "failed" for row in rows):
        overall = "failed"
    elif any(row["status"] == "cancelled" for row in rows):
        overall = "cancelled"
    elif len(rows) != len(actions):
        overall = "partial"
    return {
        "version": 1,
        "origin": "RUN ALL",
        "status": overall,
        "workspace": str(paths.workspace),
        "plan": plan,
        "results": rows,
        "scan_summary_json": str(scan_json),
        "scan_summary_text": str(scan_text),
    }

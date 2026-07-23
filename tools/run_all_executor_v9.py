#!/usr/bin/env python3
"""Patch RUN ALL v8 for final public preparation and frozen-app execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import iso_ccsf_extractor as ccsf_extractor
import run_all_executor_v1 as base
import run_all_executor_v8 as v8
from project_preflight_v1 import require_ready_project
from project_report_layout_v1 import migrate_report_layout
from project_sound_v1 import sound_reports_root
from project_workspace_v1 import FragmenterProjectV1, migrate_workspace_layout
from public_library_cache_v1 import build_public_library_cache, cache_paths, load_cache

_ORIGINAL_BUILD = v8.build_run_all_actions_v8
_ORIGINAL_INTERNAL = v8._run_internal_v8
_ORIGINAL_EXECUTE_RUN_ALL = v8.execute_run_all_v8
_INSTALLED = False

FIRST_RUN_REQUIRED_KEYS = (
    "iso_index",
    "ccsf_extract",
    "asset_library",
    "extraction_audit",
    "visual_catalogs",
    "sound_extract",
    "sound_decode",
    "snddata_samples",
    "snddata_mixer",
    "refresh",
    "public_lists",
)

_FROZEN_INTERNALS = {
    "iso_index": "build_iso_index_frozen_v9",
    "ccsf_extract": "extract_ccsf_frozen_v9",
}


def _with_strict_mixer_fingerprint(action: base.RunAction) -> base.RunAction:
    """Make parser-policy changes invalidate only the SNDDATA mixer stage."""
    if action.key != "snddata_mixer":
        return action
    tools = Path(__file__).resolve().parent
    policy_inputs = (
        str(tools / "scei_midi_v4.py"),
        str(tools / "snddata_strict_routing_patch_v1.py"),
    )
    inputs = tuple(dict.fromkeys((*action.inputs, *policy_inputs)))
    return base.RunAction(
        action.key,
        action.label,
        action.kind,
        argv=tuple(action.argv),
        internal=action.internal,
        inputs=inputs,
        outputs=tuple(action.outputs),
    )


def _with_frozen_safe_execution(action: base.RunAction) -> base.RunAction:
    """Run bundled CLI stages in-process instead of relaunching Fragmenter.exe."""
    internal = _FROZEN_INTERNALS.get(action.key)
    if internal is None or not bool(getattr(sys, "frozen", False)):
        return action
    return base.RunAction(
        action.key,
        action.label,
        "internal",
        internal=internal,
        inputs=tuple(action.inputs),
        outputs=tuple(action.outputs),
    )


def build_run_all_actions_v9(
    project: FragmenterProjectV1,
    *,
    python_executable: str | Path | None = None,
    tools_dir: str | Path | None = None,
) -> list[base.RunAction]:
    actions = [
        _with_frozen_safe_execution(_with_strict_mixer_fingerprint(action))
        for action in _ORIGINAL_BUILD(
            project,
            python_executable=python_executable,
            tools_dir=tools_dir,
        )
    ]
    workspace = Path(project.workspace_dir).expanduser()
    reports = workspace / "reports"
    audio_reports = sound_reports_root(project)
    paths = cache_paths(project)
    public_lists = base.RunAction(
        "public_lists",
        "Prepare Public Lists",
        "internal",
        internal="build_public_library_cache_v1",
        inputs=(
            str(reports / "asset_library.json"),
            str(audio_reports / "sound_library.json"),
            str(audio_reports / "sound_decode_report.json"),
            str(audio_reports / "snddata_sample_library.json"),
            str(audio_reports / "snddata_music_system_v5.json"),
        ),
        outputs=tuple(str(path) for path in paths.values()),
    )
    refresh_index = next(
        (index for index, row in enumerate(actions) if row.key == "refresh"),
        len(actions) - 1,
    )
    actions.insert(min(len(actions), refresh_index + 1), public_lists)
    return actions


def _ccsf_progress_v9(
    callback: Callable[[dict[str, Any]], None] | None,
    stage: str,
) -> Callable[[dict[str, Any]], None]:
    def emit(payload: dict[str, Any]) -> None:
        if callback is None:
            return
        current = int(payload.get("container_index") or 0)
        total = int(payload.get("container_total") or 0)
        percent = min(100.0, current * 100.0 / total) if current and total else None
        detail = str(payload.get("current_container") or payload.get("stage") or "")
        base._event(
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


def _build_iso_index_frozen_v9(project: FragmenterProjectV1) -> dict[str, Any]:
    paths = require_ready_project(project)
    target = paths.cache_iso / "iso_index.json"
    payload = ccsf_extractor.build_iso_index(Path(paths.iso), target, quiet=True)
    if not target.is_file():
        raise FileNotFoundError(target)
    return {
        "path": str(target),
        "count": int(payload.get("count") or 0),
        "execution": "in_process_frozen",
    }


def _extract_ccsf_frozen_v9(
    project: FragmenterProjectV1,
    callback: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    paths = require_ready_project(project)
    iso_index = paths.cache_iso / "iso_index.json"
    extraction_json = paths.reports / "iso_ccsf_extraction_index.json"
    extraction_text = paths.reports / "iso_ccsf_extraction_index.txt"
    args = argparse.Namespace(
        iso_path=str(paths.iso),
        iso_index=str(iso_index),
        workspace=str(paths.workspace),
        out=str(extraction_json),
        text_out=str(extraction_text),
        max_scan_bytes=v8.CORE_SCAN_BYTES,
        extract_cap=v8.CORE_EXTRACT_CAP,
        container_limit=v8.CORE_CONTAINER_LIMIT,
        asset_limit=None,
        limit=None,
        include=[],
        exclude=[],
        container=[],
        build_index=False,
        reuse_existing=True,
        summary_only=False,
        quiet=True,
        index_assets=True,
        include_failed_candidates=False,
        include_non_ccsf_gzip=False,
        ccsf_only=True,
        gzip_only=False,
        max_report_rows=ccsf_extractor.DEFAULT_MAX_REPORT_ROWS,
        asset_index_jsonl=None,
        max_failed_rows=ccsf_extractor.DEFAULT_MAX_FAILED_ROWS,
        progress_jsonl=False,
    )
    report = ccsf_extractor.run(
        args,
        progress_callback=_ccsf_progress_v9(callback, "ccsf_extract"),
    )
    workspace_migration = migrate_workspace_layout(project.workspace_dir)
    report_migration = migrate_report_layout(project)
    asset_library = paths.reports / "asset_library.json"
    if not extraction_json.is_file():
        raise FileNotFoundError(extraction_json)
    if not asset_library.is_file():
        raise FileNotFoundError(asset_library)
    return {
        "execution": "in_process_frozen",
        "report": str(extraction_json),
        "asset_library": str(asset_library),
        "confirmed_ccsf_bundles": int(
            report.get("confirmed_ccsf_bundles_extracted") or 0
        ),
        "assets_indexed": int(report.get("ccsf_assets_indexed") or 0),
        "workspace_layout_migration": workspace_migration,
        "report_layout_migration": report_migration,
    }


def _run_internal_v9(
    action: base.RunAction,
    project: FragmenterProjectV1,
    callback: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    if action.internal == "build_public_library_cache_v1":
        return build_public_library_cache(project)
    if action.internal == "build_iso_index_frozen_v9":
        return _build_iso_index_frozen_v9(project)
    if action.internal == "extract_ccsf_frozen_v9":
        return _extract_ccsf_frozen_v9(project, callback)
    return _ORIGINAL_INTERNAL(action, project, callback)


def _strict_public_list_result(
    project: FragmenterProjectV1,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Do not let full RUN ALL claim success when its final visible lists are partial."""
    if str(result.get("status") or "") != "complete":
        return result
    summary = load_cache(project, "summary") or {}
    if str(summary.get("status") or "") == "complete":
        return result

    errors = summary.get("errors") if isinstance(summary.get("errors"), dict) else {}
    message = "Prepare Public Lists completed only partially"
    if errors:
        message += ": " + "; ".join(f"{key}: {value}" for key, value in errors.items())
    result["status"] = "failed"
    for row in result.get("results") or []:
        if isinstance(row, dict) and str(row.get("key") or "") == "public_lists":
            row["status"] = "failed"
            row["message"] = message
            break
    report_path = Path(str(result.get("report_path") or ""))
    if report_path.is_file():
        temporary = report_path.with_suffix(report_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(report_path)
    return result


def execute_run_all_v9(
    project: FragmenterProjectV1,
    *,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: Any = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = _ORIGINAL_EXECUTE_RUN_ALL(
        project,
        reuse=reuse,
        callback=callback,
        cancel_event=cancel_event,
        subprocess_runner=subprocess_runner,
    )
    return _strict_public_list_result(project, result)


def is_first_scan_v9(project: FragmenterProjectV1) -> bool:
    paths = require_ready_project(project)
    state = base.load_run_state(paths)
    by_key = {action.key: action for action in build_run_all_actions_v9(project)}
    for key in FIRST_RUN_REQUIRED_KEYS:
        action = by_key.get(key)
        if action is None or not base.action_reusable(action, state):
            return True
    summary = load_cache(project, "summary") or {}
    return str(summary.get("status") or "") != "complete"


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    v8.build_run_all_actions_v8 = build_run_all_actions_v9
    v8._run_internal_v8 = _run_internal_v9
    v8.execute_run_all_v8 = execute_run_all_v9
    v8.is_first_scan_v8 = is_first_scan_v9
    v8.build_run_all_actions_v7 = build_run_all_actions_v9
    v8.execute_run_all_v7 = execute_run_all_v9
    v8.PIPELINE_VERSION = 9
    _INSTALLED = True

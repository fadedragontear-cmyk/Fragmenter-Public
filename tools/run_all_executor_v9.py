#!/usr/bin/env python3
"""Patch RUN ALL v8 with final public-list preparation and reliable first-run state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import run_all_executor_v1 as base
import run_all_executor_v8 as v8
from project_preflight_v1 import require_ready_project
from project_sound_v1 import sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from public_library_cache_v1 import build_public_library_cache, cache_paths, load_cache

_ORIGINAL_BUILD = v8.build_run_all_actions_v8
_ORIGINAL_INTERNAL = v8._run_internal_v8
_ORIGINAL_EXECUTE_RUN_ALL = v8.execute_run_all_v8
_INSTALLED = False

# These are the durable evidence stages that distinguish a completed project run
# from a partial/aborted run. Project-status and workspace-layout bookkeeping are
# intentionally omitted because they are rewritten every run.
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


def build_run_all_actions_v9(
    project: FragmenterProjectV1,
    *,
    python_executable: str | Path | None = None,
    tools_dir: str | Path | None = None,
) -> list[base.RunAction]:
    actions = [
        _with_strict_mixer_fingerprint(action)
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
    # Public lists consume the final refreshed catalogs, so this stage belongs after
    # Refresh Public Libraries rather than before it.
    refresh_index = next((index for index, row in enumerate(actions) if row.key == "refresh"), len(actions) - 1)
    actions.insert(min(len(actions), refresh_index + 1), public_lists)
    return actions


def _run_internal_v9(
    action: base.RunAction,
    project: FragmenterProjectV1,
    callback: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    if action.internal == "build_public_library_cache_v1":
        return build_public_library_cache(project)
    return _ORIGINAL_INTERNAL(action, project, callback)


def _strict_public_list_result(project: FragmenterProjectV1, result: dict[str, Any]) -> dict[str, Any]:
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
        temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    """Return true until every durable first-run stage is actually reusable.

    The old test returned false as soon as *any* core stage appeared in run state.
    A cancelled run or a damaged checkout could therefore skip the full Celdra
    production even though required outputs were absent. This check requires both
    matching state and extant outputs for the complete evidence chain.
    """
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
    # Keep compatibility aliases coherent for inherited modules that import them.
    v8.build_run_all_actions_v7 = build_run_all_actions_v9
    v8.execute_run_all_v7 = execute_run_all_v9
    v8.PIPELINE_VERSION = 9
    _INSTALLED = True

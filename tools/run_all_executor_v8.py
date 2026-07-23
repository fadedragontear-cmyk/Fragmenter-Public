#!/usr/bin/env python3
"""Canonical, individually runnable Fragmenter pipeline.

RUN ALL and every per-stage Run button use this one action list, reuse state and
project path authority. Legacy trees may be read only long enough to migrate them;
all active output is written to extracted/, decoded/, work/, cache/ and reports/.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

import run_all_executor_v1 as base
from extraction_audit_v1 import audit_extraction
from project_catalogs_v1 import build_visual_catalogs, write_memory_card_identity, write_server_index, write_server_save_index
from project_preflight_v1 import require_ready_project
from project_report_layout_v1 import migrate_report_layout
from project_sound_v1 import canonical_snddata_path, sound_decoded_root, sound_reports_root, sound_source_root
from project_sound_v7 import build_project_sound_library, extract_project_sound_sources
from project_sound_v8 import decode_project_direct_sound_sources
from project_workspace_v1 import FragmenterProjectV1, migrate_workspace_layout, save_project, write_project_status
from report_locator_v1 import write_diagnostics_summary
from run_all_plan_v2 import build_run_all_plan_v2, stage_unavailable_reason
from snddata_music_system_v5 import analyze_project_snddata
from snddata_sample_library_v3 import extract_project_snddata_samples, project_paths as snddata_sample_paths

PIPELINE_VERSION = 8
CORE_SCAN_BYTES = 2 * 1024 * 1024 * 1024
CORE_EXTRACT_CAP = 128 * 1024 * 1024
CORE_CONTAINER_LIMIT = 500


def _progress_bridge(callback: Callable[[dict[str, Any]], None] | None, stage: str):
    def emit(payload: dict[str, Any]) -> None:
        if callback is None:
            return
        current = int(payload.get("current") or 0)
        total = int(payload.get("total") or 0)
        percent = min(100.0, current * 100.0 / total) if current and total else None
        detail = str(payload.get("iso_path") or payload.get("relative_path") or "")
        kind = str(payload.get("kind") or "")
        if kind == "snddata_sample_extract_progress":
            detail = f"SNDDATA sample banks {current:,}/{total:,} @ 0x{int(payload.get('resource_offset') or 0):08X}"
        elif kind == "snddata_forensics_progress":
            detail = f"SNDDATA routing evidence {current:,}/{total:,}"
        elif kind == "sound_decode_progress":
            detail = f"Direct audio {current:,}/{total:,}: {detail}"
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


def build_run_all_actions_v8(
    project: FragmenterProjectV1,
    *,
    python_executable: str | Path | None = None,
    tools_dir: str | Path | None = None,
) -> list[base.RunAction]:
    paths = require_ready_project(project)
    py = str(python_executable or __import__("sys").executable)
    tools = Path(tools_dir).expanduser() if tools_dir is not None else Path(__file__).resolve().parent
    reports = paths.reports
    run_reports = project.workspace_path("run_reports")
    visual_reports = project.workspace_path("visual_reports")
    audio_reports = sound_reports_root(project)
    server_reports = project.workspace_path("server_reports")
    diagnostics = project.workspace_path("diagnostics")
    sample_source, sample_output, sample_report, sample_csv = snddata_sample_paths(project)
    iso_index = paths.cache_iso / "iso_index.json"
    extraction_json = reports / "iso_ccsf_extraction_index.json"
    extraction_text = reports / "iso_ccsf_extraction_index.txt"
    project_file = str(project.project_path)

    return [
        base.RunAction(
            "project_check",
            "Validate Project",
            "internal",
            internal="write_project_status_v8",
            inputs=(project_file,),
            outputs=(str(run_reports / "project_status.json"),),
        ),
        base.RunAction(
            "workspace_layout",
            "Consolidate Workspace Layout",
            "internal",
            internal="migrate_workspace_layout_v2",
            inputs=(project_file,),
            outputs=(str(run_reports / "workspace_layout.json"), str(run_reports / "report_layout.json")),
        ),
        base.RunAction(
            "iso_index",
            "Index ISO Filesystem",
            "subprocess",
            argv=(py, str(tools / "iso_index.py"), str(paths.iso), "--out", str(iso_index)),
            inputs=(str(paths.iso),),
            outputs=(str(iso_index),),
        ),
        base.RunAction(
            "ccsf_extract",
            "Extract CCSF Library",
            "subprocess",
            argv=(
                py,
                str(tools / "iso_ccsf_extractor.py"),
                str(paths.iso),
                "--iso-index",
                str(iso_index),
                "--workspace",
                str(paths.workspace),
                "--out",
                str(extraction_json),
                "--text-out",
                str(extraction_text),
                "--reuse-existing",
                "--index-assets",
                "--ccsf-only",
                "--progress-jsonl",
                "--max-scan-bytes",
                str(CORE_SCAN_BYTES),
                "--extract-cap",
                str(CORE_EXTRACT_CAP),
                "--container-limit",
                str(CORE_CONTAINER_LIMIT),
            ),
            inputs=(str(paths.iso), str(iso_index)),
            outputs=(str(extraction_json), str(reports / "asset_library.json"), str(paths.extracted_ccs)),
        ),
        base.RunAction(
            "asset_library",
            "Verify Asset Library",
            "internal",
            internal="verify_asset_library_v8",
            inputs=(str(extraction_json), str(paths.extracted_ccs)),
            outputs=(str(reports / "asset_library.json"),),
        ),
        base.RunAction(
            "extraction_audit",
            "Audit CCSF Extraction",
            "internal",
            internal="audit_extraction_v8",
            inputs=(str(extraction_json), str(reports / "asset_library.json"), str(iso_index)),
            outputs=(str(reports / "extraction_audit.json"),),
        ),
        base.RunAction(
            "visual_catalogs",
            "Prepare Visual Catalogs",
            "internal",
            internal="build_visual_catalogs_v8",
            inputs=(str(reports / "asset_library.json"),),
            outputs=(str(visual_reports / "texture_catalog.json"), str(visual_reports / "animation_catalog.json")),
        ),
        base.RunAction(
            "sound_extract",
            "Extract Audio Sources",
            "internal",
            internal="extract_project_sound_v8",
            inputs=(str(paths.iso), str(iso_index)),
            outputs=(str(audio_reports / "sound_source_manifest.json"), str(sound_source_root(project))),
        ),
        base.RunAction(
            "sound_decode",
            "Decode Direct Audio",
            "internal",
            internal="decode_project_sound_v8",
            inputs=(str(sound_source_root(project)),),
            outputs=(str(audio_reports / "sound_decode_report.json"), str(sound_decoded_root(project))),
        ),
        base.RunAction(
            "snddata_samples",
            "Extract SNDDATA Samples",
            "internal",
            internal="extract_snddata_samples_v3",
            inputs=(str(sample_source),),
            outputs=(str(sample_report), str(sample_csv), str(sample_output)),
        ),
        base.RunAction(
            "snddata_mixer",
            "Build SNDDATA Mixer Index",
            "internal",
            internal="analyze_project_snddata_v5",
            inputs=(str(canonical_snddata_path(project)), str(sample_report)),
            outputs=(str(audio_reports / "snddata_music_system_v5.json"), str(audio_reports / "snddata_pipeline_summary_v5.json")),
        ),
        base.RunAction(
            "server_index",
            "Index Area Server",
            "internal",
            internal="write_server_index_v8",
            inputs=(str(paths.area_server_root),),
            outputs=(str(server_reports / "server_index.json"),),
        ),
        base.RunAction(
            "server_saves",
            "Index Server Saves",
            "internal",
            internal="write_server_save_index_v8",
            inputs=(str(paths.server_saves),),
            outputs=(str(server_reports / "server_save_index.json"),),
        ),
        base.RunAction(
            "memory_card",
            "Verify Memory Card",
            "internal",
            internal="write_memory_card_identity_v8",
            inputs=(str(paths.memory_card),),
            outputs=(str(server_reports / "memory_card_identity.json"),),
        ),
        base.RunAction(
            "refresh",
            "Refresh Public Libraries",
            "internal",
            internal="refresh_public_libraries_v8",
            inputs=(str(reports / "asset_library.json"), str(audio_reports)),
            outputs=(str(audio_reports / "sound_library.json"), str(diagnostics / "summary.txt")),
        ),
    ]


def _run_internal_v8(
    action: base.RunAction,
    project: FragmenterProjectV1,
    callback: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    if action.internal == "write_project_status_v8":
        json_path, text_path = write_project_status(project)
        return {"json": str(json_path), "text": str(text_path)}
    if action.internal == "migrate_workspace_layout_v2":
        workspace_report = migrate_workspace_layout(project.workspace_dir)
        report_report = migrate_report_layout(project)
        save_project(project)
        return {"workspace_layout": workspace_report, "report_layout": report_report}
    if action.internal == "verify_asset_library_v8":
        target = project.workspace_path("reports") / "asset_library.json"
        if not target.is_file():
            raise FileNotFoundError(target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        return {"path": str(target), "asset_count": int(payload.get("asset_count") or len(payload.get("assets") or []))}
    if action.internal == "audit_extraction_v8":
        return audit_extraction(project)
    if action.internal == "build_visual_catalogs_v8":
        return build_visual_catalogs(project)
    if action.internal == "extract_project_sound_v8":
        return extract_project_sound_sources(project, callback=_progress_bridge(callback, action.key))
    if action.internal == "decode_project_sound_v8":
        return decode_project_direct_sound_sources(project, callback=_progress_bridge(callback, action.key))
    if action.internal == "extract_snddata_samples_v3":
        return extract_project_snddata_samples(project, clean=True, callback=_progress_bridge(callback, action.key))
    if action.internal == "analyze_project_snddata_v5":
        return analyze_project_snddata(project, callback=_progress_bridge(callback, action.key))
    if action.internal == "write_server_index_v8":
        return {"path": str(write_server_index(project))}
    if action.internal == "write_server_save_index_v8":
        return {"path": str(write_server_save_index(project))}
    if action.internal == "write_memory_card_identity_v8":
        return {"path": str(write_memory_card_identity(project))}
    if action.internal == "refresh_public_libraries_v8":
        library = build_project_sound_library(project)
        diagnostics = write_diagnostics_summary(project)
        return {
            "sound_library": str(sound_reports_root(project) / "sound_library.json"),
            "diagnostics_summary": str(diagnostics),
            "summary": library["summary"],
        }
    raise ValueError(f"Unknown RUN ALL v8 internal action: {action.internal}")


def _selected_actions(project: FragmenterProjectV1, keys: Iterable[str] | None) -> list[base.RunAction]:
    actions = build_run_all_actions_v8(project)
    if keys is None:
        return actions
    wanted = [str(key) for key in keys]
    by_key = {action.key: action for action in actions}
    missing = [key for key in wanted if key not in by_key]
    if missing:
        raise KeyError(f"Unknown pipeline stage(s): {', '.join(missing)}")
    return [by_key[key] for key in wanted]


def is_first_scan_v8(project: FragmenterProjectV1) -> bool:
    paths = require_ready_project(project)
    state = base.load_run_state(paths)
    stages = state.get("stages") if isinstance(state, dict) else None
    return not isinstance(stages, dict) or not any(key in stages for key in {"iso_index", "ccsf_extract", "sound_extract", "snddata_mixer"})


def execute_pipeline_v8(
    project: FragmenterProjectV1,
    *,
    stage_keys: Iterable[str] | None = None,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = require_ready_project(project)
    plan = build_run_all_plan_v2(project)
    actions = _selected_actions(project, stage_keys)
    state = base.load_run_state(paths)
    state.setdefault("stages", {})
    results: list[base.StageResult] = []
    runner = subprocess_runner or base._run_subprocess

    for action in actions:
        started = base._utc_iso()
        base._event(callback, stage=action.key, label=action.label, kind="start")
        if cancel_event is not None and cancel_event.is_set():
            results.append(base.StageResult(action.key, action.label, "cancelled", started, base._utc_iso(), "Cancellation requested before stage start."))
            break
        skip_reason = stage_unavailable_reason(project, action.key)
        if skip_reason:
            result = base.StageResult(
                action.key,
                action.label,
                "skipped",
                started,
                base._utc_iso(),
                skip_reason,
            )
            results.append(result)
            base._event(
                callback,
                stage=action.key,
                label=action.label,
                kind="finish",
                status="skipped",
                message=skip_reason,
            )
            continue
        try:
            can_reuse = reuse and action.key not in {"project_check", "workspace_layout"}
            if can_reuse and base.action_reusable(action, state):
                result = base.StageResult(action.key, action.label, "reused", started, base._utc_iso(), "Matching inputs and outputs were reused.")
            elif action.kind == "internal":
                payload = _run_internal_v8(action, project, callback)
                if action.key == "extraction_audit" and payload.get("status") == "blocked":
                    result = base.StageResult(
                        action.key,
                        action.label,
                        "failed",
                        started,
                        base._utc_iso(),
                        "; ".join(payload.get("blockers") or []),
                        [payload],
                    )
                else:
                    result = base.StageResult(action.key, action.label, "complete", started, base._utc_iso(), actions=[payload])
            else:
                payload = runner(action, callback=callback, cancel_event=cancel_event)
                status = str(payload.get("status") or "failed")
                if status == "complete" and action.key == "ccsf_extract":
                    payload["workspace_layout_migration"] = migrate_workspace_layout(project.workspace_dir)
                    payload["report_layout_migration"] = migrate_report_layout(project)
                message = ""
                if status == "failed":
                    output = payload.get("output") or []
                    message = str(output[-1]) if output else f"Subprocess exited with {payload.get('returncode')}"
                result = base.StageResult(action.key, action.label, status, started, base._utc_iso(), message, [payload])
            results.append(result)
            if result.status in {"failed", "cancelled"}:
                base._event(callback, stage=action.key, label=action.label, kind="finish", status=result.status, error=result.message)
                break
            state["stages"][action.key] = {
                "completed_at": result.finished_at,
                "input_digest": base.action_input_digest(action),
                "outputs": list(action.outputs),
            }
            base.save_run_state(paths, state)
            base._event(callback, stage=action.key, label=action.label, kind="finish", status=result.status)
        except Exception as exc:
            result = base.StageResult(action.key, action.label, "failed", started, base._utc_iso(), f"{type(exc).__name__}: {exc}")
            results.append(result)
            base._event(callback, stage=action.key, label=action.label, kind="finish", status="failed", error=result.message)
            break

    rows = [result.to_dict() for result in results]
    scan_json, scan_text = base.write_scan_summary(project, rows)
    overall = "complete"
    if any(row["status"] == "failed" for row in rows):
        overall = "failed"
    elif any(row["status"] == "cancelled" for row in rows):
        overall = "cancelled"
    elif len(rows) != len(actions):
        overall = "partial"
    elif any(row["status"] == "skipped" for row in rows):
        overall = "complete_with_skips"

    report = {
        "version": PIPELINE_VERSION,
        "origin": "RUN ALL" if stage_keys is None else "PIPELINE STAGE",
        "status": overall,
        "workspace": str(paths.workspace),
        "requested_stages": [action.key for action in actions],
        "plan": plan,
        "results": rows,
        "scan_summary_json": str(scan_json),
        "scan_summary_text": str(scan_text),
        "canonical_paths": {
            "ccsf": str(paths.extracted_ccs),
            "audio_source": str(sound_source_root(project)),
            "audio_decoded": str(sound_decoded_root(project)),
            "run_reports": str(project.workspace_path("run_reports")),
            "visual_reports": str(project.workspace_path("visual_reports")),
            "audio_reports": str(sound_reports_root(project)),
            "server_reports": str(project.workspace_path("server_reports")),
            "diagnostics": str(project.workspace_path("diagnostics")),
        },
    }
    target = project.workspace_path("run_reports") / "pipeline_last.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(target)
    return report


def execute_run_all_v8(
    project: FragmenterProjectV1,
    *,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return execute_pipeline_v8(
        project,
        reuse=reuse,
        callback=callback,
        cancel_event=cancel_event,
        subprocess_runner=subprocess_runner,
    )


def execute_stage_v8(
    project: FragmenterProjectV1,
    stage_key: str,
    *,
    reuse: bool = False,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return execute_pipeline_v8(
        project,
        stage_keys=(stage_key,),
        reuse=reuse,
        callback=callback,
        cancel_event=cancel_event,
        subprocess_runner=subprocess_runner,
    )


build_run_all_actions_v7 = build_run_all_actions_v8
execute_run_all_v7 = execute_run_all_v8

#!/usr/bin/env python3
"""Canonical Fragmenter RUN ALL plan and first-scan Celdra commentary."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from project_preflight_v1 import build_preflight, resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1


@dataclass(frozen=True)
class RunStageV2:
    key: str
    label: str
    description: str
    source_paths: tuple[str, ...]
    output_paths: tuple[str, ...]
    celdra_lines: tuple[str, ...] = ()

    def to_dict(self, *, blocked: bool, state: dict[str, Any] | None = None) -> dict[str, Any]:
        row = asdict(self)
        state = state if isinstance(state, dict) else {}
        outputs = [Path(value) for value in self.output_paths]
        existing = sum(path.exists() for path in outputs)
        if blocked:
            status = "blocked"
        elif state and outputs and existing == len(outputs):
            status = "complete"
        elif outputs and existing == len(outputs):
            status = "available"
        elif existing:
            status = "partial"
        else:
            status = "pending"
        row["status"] = status
        row["last_completed_at"] = str(state.get("completed_at") or "")
        row["task_origin"] = "RUN ALL"
        return row


def _inside(workspace: Path, *paths: Path) -> tuple[str, ...]:
    root = workspace.resolve()
    output: list[str] = []
    for path in paths:
        resolved = path.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"RUN ALL output escapes active project workspace: {path}")
        output.append(str(path))
    return tuple(output)


STAGE_SOURCE_REQUIREMENTS = {
    "iso_index": "iso",
    "ccsf_extract": "iso",
    "asset_library": "iso",
    "extraction_audit": "iso",
    "visual_catalogs": "iso",
    "sound_extract": "iso",
    "sound_decode": "iso",
    "snddata_samples": "iso",
    "snddata_mixer": "iso",
    "refresh": "iso",
    "public_lists": "iso",
    "server_index": "area_server",
    "server_saves": "server_saves",
    "memory_card": "memory_card",
}


def stage_unavailable_reason(project: FragmenterProjectV1, stage_key: str) -> str:
    requirement = STAGE_SOURCE_REQUIREMENTS.get(stage_key)
    if requirement is None:
        return ""
    if requirement == "iso":
        available = bool(project.sources.iso_path) and Path(project.sources.iso_path).expanduser().is_file()
        label = "game ISO"
    elif requirement == "area_server":
        root = Path(project.sources.area_server_root).expanduser() if project.sources.area_server_root else None
        available = bool(root and root.is_dir() and (root / "data").is_dir())
        label = "Area Server"
    elif requirement == "server_saves":
        available = bool(project.sources.server_save_dir) and Path(project.sources.server_save_dir).expanduser().is_dir()
        label = "server-save folder"
    else:
        available = bool(project.sources.memory_card_path) and Path(project.sources.memory_card_path).expanduser().is_file()
        label = "memory-card file"
    return "" if available else f"Skipped: no usable {label} is configured for this project."


def _run_state(project: FragmenterProjectV1) -> dict[str, dict[str, Any]]:
    target = project.workspace_path("cache_iso").parent / "run_all_state.json"
    if not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    stages = payload.get("stages") if isinstance(payload, dict) else None
    return {str(key): dict(value) for key, value in (stages or {}).items() if isinstance(value, dict)}


def stages_for_project(project: FragmenterProjectV1) -> list[RunStageV2]:
    paths = resolve_runtime_paths(project)
    workspace = paths.workspace
    reports = paths.reports
    run_reports = project.workspace_path("run_reports")
    visual_reports = project.workspace_path("visual_reports")
    audio_source = project.workspace_path("audio_source")
    audio_decoded = project.workspace_path("extracted_audio")
    audio_reports = project.workspace_path("audio_reports")
    server_reports = project.workspace_path("server_reports")
    diagnostics = project.workspace_path("diagnostics")
    snddata = audio_source / "data" / "snddata.bin"
    return [
        RunStageV2(
            "project_check",
            "Validate Project",
            "Confirm the project workspace and report which optional sources are currently available.",
            tuple(str(path) for path in (paths.iso, paths.area_server_root, paths.server_saves, paths.memory_card)),
            _inside(workspace, run_reports / "project_status.json"),
            (
                "Hello! What project or idea are you diving into today?",
                "Checking the project sources before I touch the scanners.",
            ),
        ),
        RunStageV2(
            "workspace_layout",
            "Consolidate Workspace Layout",
            "Merge legacy output and report trees into the canonical extracted/decoded/work/reports layout without overwriting conflicts.",
            (str(workspace),),
            _inside(workspace, run_reports / "workspace_layout.json", run_reports / "report_layout.json"),
            (
                "I found another folder named reports. I have placed it with the other reports.",
                "Redundant output paths detected. Applying organization until morale improves.",
            ),
        ),
        RunStageV2(
            "iso_index",
            "Index ISO Filesystem",
            "Build or reuse the lightweight ISO filesystem index used by every extraction stage.",
            (str(paths.iso),),
            _inside(workspace, paths.cache_iso / "iso_index.json"),
            (
                "Reading the ISO directory. This is the organized part.",
                "The disc has a directory. I am choosing to view that as cooperation.",
            ),
        ),
        RunStageV2(
            "ccsf_extract",
            "Extract CCSF Library",
            "Scan the known game containers and extract confirmed CCSF bundles into extracted/ccsf.",
            (str(paths.iso), str(paths.cache_iso / "iso_index.json")),
            _inside(workspace, paths.extracted_ccs, reports / "iso_ccsf_extraction_index.json"),
            (
                "Extracting CCSF assets. The names will become strange shortly.",
                "This scan has several thousand files and at least three of them are probably important.",
            ),
        ),
        RunStageV2(
            "asset_library",
            "Verify Asset Library",
            "Verify the logical asset catalog produced by CCSF extraction.",
            (str(paths.extracted_ccs),),
            _inside(workspace, reports / "asset_library.json"),
            ("Cataloging models, textures and animation records. I am not judging the names yet.",),
        ),
        RunStageV2(
            "extraction_audit",
            "Audit CCSF Extraction",
            "Confirm that the full focused DATA.BIN scan and logical asset index completed without coverage blockers.",
            (str(reports / "iso_ccsf_extraction_index.json"), str(reports / "asset_library.json")),
            _inside(workspace, reports / "extraction_audit.json"),
            ("Auditing the extraction. Trust is useful; byte counts are better.",),
        ),
        RunStageV2(
            "visual_catalogs",
            "Prepare Visual Catalogs",
            "Build lightweight texture and animation catalogs for the accepted 3D workspace.",
            (str(reports / "asset_library.json"),),
            _inside(workspace, visual_reports / "texture_catalog.json", visual_reports / "animation_catalog.json"),
            ("Preparing visual catalogs. The 3D tab is locked, so I will behave.",),
        ),
        RunStageV2(
            "sound_extract",
            "Extract Audio Sources",
            "Extract sound/*, SNDDATA, EFF.HD/BD, BGM and FOOD into extracted/audio.",
            (str(paths.iso), str(paths.cache_iso / "iso_index.json")),
            _inside(workspace, audio_source, audio_reports / "sound_source_manifest.json"),
            ("Collecting the sound banks. Nothing has screamed yet.",),
        ),
        RunStageV2(
            "sound_decode",
            "Decode Direct Audio",
            "Decode direct streams and verified containers into decoded/audio, independent of SNDDATA sequencing.",
            (str(audio_source),),
            _inside(workspace, audio_decoded, audio_reports / "sound_decode_report.json"),
            ("Decoding direct audio. Some files are music; some are apparently policy decisions.",),
        ),
        RunStageV2(
            "snddata_samples",
            "Extract SNDDATA Samples",
            "Extract authoritative SCEIVagi-indexed PS-ADPCM samples and WAVs from SNDDATA.",
            (str(snddata),),
            _inside(workspace, audio_decoded / "snddata" / "samples", audio_reports / "snddata_sample_library.json"),
            ("Extracting SNDDATA samples. Tiny noises are still evidence.",),
        ),
        RunStageV2(
            "snddata_mixer",
            "Build SNDDATA Mixer Index",
            "Parse FF0A sequences, Program resources, slots, exact sample IDs and ranked routing hypotheses.",
            (str(snddata), str(audio_reports / "snddata_sample_library.json")),
            _inside(workspace, audio_reports / "snddata_music_system_v5.json", audio_reports / "snddata_pipeline_summary_v5.json"),
            (
                "Examining SNDDATA. Its organizational choices remain questionable.",
                "I am not inventing Program 0 merely because the file refuses to introduce itself.",
            ),
        ),
        RunStageV2(
            "server_index",
            "Index Area Server",
            "Catalog Area Server files and readable inspection metadata.",
            (str(paths.area_server_root),),
            _inside(workspace, server_reports / "server_index.json"),
            ("Indexing the Area Server. I recognize this one; it has folders on purpose.",),
        ),
        RunStageV2(
            "server_saves",
            "Index Server Saves",
            "Record server-save metadata without editing save contents.",
            (str(paths.server_saves),),
            _inside(workspace, server_reports / "server_save_index.json"),
            ("Recording save metadata. Backup tools only. I have been specifically supervised.",),
        ),
        RunStageV2(
            "memory_card",
            "Verify Memory Card",
            "Record whole-file memory-card identity for verified backup and restore.",
            (str(paths.memory_card),),
            _inside(workspace, server_reports / "memory_card_identity.json"),
            ("Verifying the memory card as one file. No tricks. Not today.",),
        ),
        RunStageV2(
            "refresh",
            "Refresh Public Libraries",
            "Refresh the visual, audio, server and report catalogs from canonical outputs.",
            (str(reports / "asset_library.json"), str(audio_reports)),
            _inside(workspace, audio_reports / "sound_library.json", diagnostics / "summary.txt"),
            ("The fresh scan is complete. I have organized the evidence and concealed my disappointment.",),
        ),
    ]


def build_run_all_plan_v2(project: FragmenterProjectV1) -> dict[str, Any]:
    preflight = build_preflight(project)
    blocked = not bool(preflight.get("ready"))
    state = _run_state(project)
    rows: list[dict[str, Any]] = []
    for stage in stages_for_project(project):
        row = stage.to_dict(blocked=blocked, state=state.get(stage.key))
        reason = "" if blocked else stage_unavailable_reason(project, stage.key)
        if reason:
            row["status"] = "skipped"
            row["skip_reason"] = reason
        rows.append(row)
    return {
        "version": 2,
        "origin": "RUN ALL",
        "ready": not blocked,
        "blockers": list(preflight.get("blockers") or []),
        "warnings": list(preflight.get("warnings") or []),
        "unavailable": list(preflight.get("unavailable") or []),
        "workspace": str(Path(project.workspace_dir).expanduser()),
        "stages": rows,
    }


def celdra_line(stage: dict[str, Any], index: int = 0) -> str:
    lines = stage.get("celdra_lines") if isinstance(stage, dict) else None
    if not isinstance(lines, (list, tuple)) or not lines:
        return ""
    return str(lines[index % len(lines)])

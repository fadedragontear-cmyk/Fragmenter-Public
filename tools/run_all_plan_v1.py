#!/usr/bin/env python3
"""Fragmenter 1.0 RUN ALL and Deep Discovery plan contracts.

This module describes execution; it does not perform long-running work. The GUI
runner will consume these stages and report their actual state. Every normal stage
is bound to the active project and no stage falls back to the repository workspace.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from project_preflight_v1 import build_preflight, resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1


@dataclass(frozen=True)
class RunAllStage:
    key: str
    label: str
    description: str
    source_paths: tuple[str, ...]
    output_paths: tuple[str, ...]
    celdra_lines: tuple[str, ...] = ()

    def to_dict(self, *, blocked: bool) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = "blocked" if blocked else "pending"
        payload["task_origin"] = "RUN ALL"
        return payload


def _inside(workspace: Path, *paths: Path) -> tuple[str, ...]:
    resolved_workspace = workspace.resolve()
    values: list[str] = []
    for path in paths:
        resolved = path.resolve()
        if resolved != resolved_workspace and resolved_workspace not in resolved.parents:
            raise ValueError(f"RUN ALL output escapes active project workspace: {path}")
        values.append(str(path))
    return tuple(values)


def stages_for_project(project: FragmenterProjectV1) -> list[RunAllStage]:
    paths = resolve_runtime_paths(project)
    workspace = paths.workspace
    iso_index = paths.cache_iso / "iso_index.json"
    asset_library = paths.reports / "asset_library.json"
    texture_catalog = paths.reports / "texture_catalog.json"
    animation_catalog = paths.reports / "animation_catalog.json"
    audio_library = paths.reports / "audio_library.json"
    snddata_report = paths.reports / "snddata_summary.json"
    server_index = paths.reports / "server_index.json"
    save_index = paths.reports / "server_save_index.json"
    memory_card_identity = paths.reports / "memory_card_identity.json"

    return [
        RunAllStage(
            "project_check",
            "Validate Project",
            "Confirm ISO, Area Server, server saves, memory card, and workspace belong to the active project.",
            tuple(str(path) for path in (paths.iso, paths.area_server_root, paths.server_saves, paths.memory_card)),
            _inside(workspace, paths.reports / "project_status.json"),
            ("Checking the project sources before I touch the scanners.",),
        ),
        RunAllStage(
            "iso_index",
            "Index ISO Filesystem",
            "Build or reuse the active project's lightweight ISO filesystem index.",
            (str(paths.iso),),
            _inside(workspace, iso_index),
            ("Reading the ISO directory. This is the organized part.",),
        ),
        RunAllStage(
            "ccsf_extract",
            "Extract CCSF Library",
            "Extract confirmed CCSF assets into the active project and never the repository workspace.",
            (str(paths.iso), str(iso_index)),
            _inside(workspace, paths.extracted_ccs),
            ("Extracting CCSF assets. The names will become strange shortly.",),
        ),
        RunAllStage(
            "asset_library",
            "Build Asset Library",
            "Catalog model, object, texture, palette, and animation evidence from extracted CCSF assets.",
            (str(paths.extracted_ccs),),
            _inside(workspace, asset_library),
            ("Cataloging models, textures, and animation records.",),
        ),
        RunAllStage(
            "visual_catalogs",
            "Prepare Visual Catalogs",
            "Build lightweight texture and animation catalogs without decoding the entire library on the Tk thread.",
            (str(asset_library),),
            _inside(workspace, texture_catalog, animation_catalog, paths.cache_ccsf_structure),
            ("Preparing visual catalogs. No, I am not decoding every model at once.",),
        ),
        RunAllStage(
            "known_audio",
            "Prepare Known Audio",
            "Extract and decode known EFF, BGM, FOOD, and SNDDATA targets into the active media pipeline.",
            (str(paths.iso), str(iso_index)),
            _inside(workspace, paths.media_pipeline, audio_library),
            ("Preparing the known sound banks and streams.",),
        ),
        RunAllStage(
            "snddata",
            "Analyze SNDDATA",
            "Parse samples, Programs, Slots, and sequence evidence; preserve unresolved mappings for the resolver.",
            (str(paths.media_pipeline),),
            _inside(workspace, paths.cache_snddata, paths.cache_mappings, snddata_report),
            ("Examining SNDDATA. Its organizational choices remain questionable.",),
        ),
        RunAllStage(
            "server_index",
            "Index Area Server",
            "Catalog server data files and prepare readable inspection metadata.",
            (str(paths.area_server_root), str(paths.area_server_data)),
            _inside(workspace, paths.extracted_server, server_index),
            ("Indexing the Area Server files and their compressed members.",),
        ),
        RunAllStage(
            "server_saves",
            "Index Server Saves",
            "Record Area Server save-file metadata without editing save contents.",
            (str(paths.server_saves),),
            _inside(workspace, save_index, paths.backups_server_saves),
            ("Recording server-save metadata. Backup tools only; no save editing.",),
        ),
        RunAllStage(
            "memory_card",
            "Verify Memory Card",
            "Record whole-file memory-card identity for later verified backup and restore.",
            (str(paths.memory_card),),
            _inside(workspace, memory_card_identity, paths.backups_memory_cards),
            ("Verifying the memory-card file as a whole. I am not opening the saves inside it.",),
        ),
        RunAllStage(
            "refresh",
            "Refresh Libraries",
            "Refresh the public 3D, texture, animation, audio, server, save, and report views from canonical project outputs.",
            tuple(str(path) for path in (asset_library, audio_library, server_index)),
            _inside(workspace, paths.reports),
            ("The project libraries are ready for the interface.",),
        ),
    ]


def build_run_all_plan(project: FragmenterProjectV1) -> dict[str, Any]:
    preflight = build_preflight(project)
    blocked = not bool(preflight.get("ready"))
    stages = [stage.to_dict(blocked=blocked) for stage in stages_for_project(project)]
    return {
        "version": 1,
        "origin": "RUN ALL",
        "ready": not blocked,
        "blockers": list(preflight.get("blockers") or []),
        "workspace": str(Path(project.workspace_dir).expanduser()),
        "stages": stages,
    }


def build_deep_discovery_plan(project: FragmenterProjectV1) -> dict[str, Any]:
    paths = resolve_runtime_paths(project)
    workspace = paths.workspace
    diagnostics = paths.diagnostics / "deep_discovery"
    stage = RunAllStage(
        "deep_disc_discovery",
        "Deep Disc Discovery",
        "Run broad signature, gzip, and unknown-container discovery only when explicitly requested.",
        (str(paths.iso),),
        _inside(workspace, diagnostics),
        ("Beginning deep discovery. This is the slow, broad scan you explicitly requested.",),
    )
    preflight = build_preflight(project)
    blocked = not bool(preflight.get("ready"))
    payload = stage.to_dict(blocked=blocked)
    payload["task_origin"] = "DEEP DISC DISCOVERY"
    return {
        "version": 1,
        "origin": "DEEP DISC DISCOVERY",
        "ready": not blocked,
        "blockers": list(preflight.get("blockers") or []),
        "workspace": str(workspace),
        "stages": [payload],
    }


def celdra_line(stage: dict[str, Any], index: int = 0) -> str:
    lines = stage.get("celdra_lines") if isinstance(stage, dict) else None
    if not isinstance(lines, (list, tuple)) or not lines:
        return ""
    return str(lines[index % len(lines)])

#!/usr/bin/env python3
"""Resolve authoritative Fragmenter project runtime paths."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_workspace_v1 import FragmenterProjectV1, load_project, project_status


@dataclass(frozen=True)
class ProjectRuntimePaths:
    workspace: Path
    project_file: Path
    iso: Path
    area_server_root: Path
    area_server_data: Path
    server_saves: Path
    memory_card: Path
    extracted_ccs: Path
    audio_source: Path
    texture_outputs: Path
    extracted_audio: Path
    extracted_server: Path
    audio_work: Path
    media_pipeline: Path
    cache_iso: Path
    cache_ccsf_structure: Path
    cache_snddata: Path
    cache_mappings: Path
    backups_server_saves: Path
    backups_memory_cards: Path
    reports: Path
    run_reports: Path
    visual_reports: Path
    audio_reports: Path
    server_reports: Path
    diagnostics: Path

    def to_dict(self) -> dict[str, str]:
        return {name: str(value) for name, value in self.__dict__.items()}


def resolve_runtime_paths(project: FragmenterProjectV1) -> ProjectRuntimePaths:
    """Return every canonical runtime path for one active project."""
    workspace = Path(project.workspace_dir).expanduser()
    server_root = Path(project.sources.area_server_root).expanduser() if project.sources.area_server_root else Path()
    return ProjectRuntimePaths(
        workspace=workspace,
        project_file=project.project_path,
        iso=Path(project.sources.iso_path).expanduser() if project.sources.iso_path else Path(),
        area_server_root=server_root,
        area_server_data=server_root / "data" if project.sources.area_server_root else Path(),
        server_saves=Path(project.sources.server_save_dir).expanduser() if project.sources.server_save_dir else Path(),
        memory_card=Path(project.sources.memory_card_path).expanduser() if project.sources.memory_card_path else Path(),
        extracted_ccs=project.workspace_path("extracted_ccs"),
        audio_source=project.workspace_path("audio_source"),
        texture_outputs=project.workspace_path("texture_outputs"),
        extracted_audio=project.workspace_path("extracted_audio"),
        extracted_server=project.workspace_path("extracted_server"),
        audio_work=project.workspace_path("audio_work"),
        media_pipeline=project.workspace_path("media_pipeline"),
        cache_iso=project.workspace_path("cache_iso"),
        cache_ccsf_structure=project.workspace_path("cache_ccsf_structure"),
        cache_snddata=project.workspace_path("cache_snddata"),
        cache_mappings=project.workspace_path("cache_mappings"),
        backups_server_saves=project.workspace_path("backups_server_saves"),
        backups_memory_cards=project.workspace_path("backups_memory_cards"),
        reports=project.workspace_path("reports"),
        run_reports=project.workspace_path("run_reports"),
        visual_reports=project.workspace_path("visual_reports"),
        audio_reports=project.workspace_path("audio_reports"),
        server_reports=project.workspace_path("server_reports"),
        diagnostics=project.workspace_path("diagnostics"),
    )


def load_active_project(project_file_or_workspace: str | Path) -> tuple[FragmenterProjectV1, ProjectRuntimePaths]:
    project = load_project(project_file_or_workspace)
    return project, resolve_runtime_paths(project)


def build_preflight(project: FragmenterProjectV1) -> dict[str, Any]:
    """Build the single readiness/path payload shared by Setup and RUN ALL."""
    status = project_status(project)
    paths = resolve_runtime_paths(project)
    checks = dict(status.get("checks") or {})
    configured = dict(status.get("configured") or {})
    blockers = [] if checks.get("workspace") else ["workspace"]
    warnings = [
        key
        for key in ("iso", "area_server", "server_saves", "memory_card")
        if configured.get(key) and not checks.get(key)
    ]
    return {
        "project_version": project.version,
        "workspace_layout_version": status.get("workspace_layout_version"),
        "ready": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "unavailable": [
            key
            for key in ("iso", "area_server", "server_saves", "memory_card")
            if not checks.get(key)
        ],
        "checks": checks,
        "configured": configured,
        "sources": dict(status.get("sources") or {}),
        "paths": paths.to_dict(),
    }


def require_ready_project(project: FragmenterProjectV1) -> ProjectRuntimePaths:
    """Return runtime paths once the project workspace itself is usable.

    Game, server, save, and memory-card inputs are optional capabilities. Callers
    that need one of them must inspect the corresponding preflight check.
    """
    payload = build_preflight(project)
    if not payload["ready"]:
        raise RuntimeError("Fragmenter project workspace is missing or invalid.")
    return resolve_runtime_paths(project)

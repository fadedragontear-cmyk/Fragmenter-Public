#!/usr/bin/env python3
"""GUI-neutral Setup controller for Fragmenter 1.0 projects."""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_preflight_v1 import build_preflight, load_active_project
from project_workspace_v1 import (
    PROJECT_FILENAME,
    FragmenterProjectV1,
    create_project,
    ensure_workspace_layout,
    save_project,
    write_project_status,
)

SETUP_ROWS = (
    ("iso", "Game ISO", "iso_path"),
    ("area_server", "Area Server", "area_server_root"),
    ("server_saves", "Server Saves", "server_save_dir"),
    ("memory_card", "Memory Card", "memory_card_path"),
    ("workspace", "Workspace", "workspace_dir"),
)


@dataclass(frozen=True)
class SetupRow:
    key: str
    label: str
    path: str
    ok: bool
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "path": self.path,
            "ok": self.ok,
            "status": self.status,
        }


def _stable_workspace_path(workspace_dir: str | Path) -> Path:
    workspace = Path(workspace_dir).expanduser().resolve()
    if bool(getattr(sys, "frozen", False)):
        temporary = Path(tempfile.gettempdir()).resolve()
        if workspace == temporary or temporary in workspace.parents:
            raise ValueError(
                "The Project workspace cannot be inside Windows Temp. Extract the "
                "Fragmenter ZIP to a normal folder, then choose a permanent workspace "
                "with Browse. Do not run Fragmenter.exe from inside the ZIP."
            )
    return workspace


def create_setup_project(
    workspace_dir: str | Path,
    *,
    iso_path: str | Path,
    area_server_root: str | Path,
    server_save_dir: str | Path,
    memory_card_path: str | Path,
) -> FragmenterProjectV1:
    project = create_project(
        _stable_workspace_path(workspace_dir),
        iso_path=iso_path,
        area_server_root=area_server_root,
        server_save_dir=server_save_dir,
        memory_card_path=memory_card_path,
    )
    write_project_status(project)
    return project


def _selected_project_file(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate / PROJECT_FILENAME if candidate.is_dir() else candidate


def _load_relocated_project(path: str | Path, error: ValueError) -> FragmenterProjectV1:
    """Use the explicitly selected project.json location as workspace authority.

    Fragmenter project files store an absolute workspace path. Moving or restoring a
    complete project folder therefore used to produce a blocking popup even though the
    selected project.json and all generated work were present together. Only the exact
    workspace-location mismatch is repaired here; malformed or unsupported projects
    continue to raise their original validation error.
    """
    if "workspace_dir points to" not in str(error) or "project was loaded from" not in str(error):
        raise error

    project_file = _selected_project_file(path).resolve()
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    project = FragmenterProjectV1.from_dict(payload)
    recorded_workspace = str(project.workspace_dir)
    actual_workspace = str(project_file.parent)
    project.workspace_dir = actual_workspace
    project.settings["workspace_rebased_from"] = recorded_workspace
    project.settings["workspace_rebased_to"] = actual_workspace
    ensure_workspace_layout(project)
    save_project(project, project_file)
    return project


def load_setup_project(path: str | Path) -> FragmenterProjectV1:
    try:
        project, _paths = load_active_project(path)
    except ValueError as exc:
        project = _load_relocated_project(path, exc)
    write_project_status(project)
    return project


def setup_rows(project: FragmenterProjectV1) -> list[SetupRow]:
    preflight = build_preflight(project)
    checks = dict(preflight.get("checks") or {})
    rows: list[SetupRow] = []
    for key, label, source_name in SETUP_ROWS:
        if source_name == "workspace_dir":
            path = project.workspace_dir
        else:
            path = str(getattr(project.sources, source_name))
        ok = bool(checks.get(key))
        if ok:
            status = "Ready"
        elif key != "workspace" and not str(path).strip():
            status = "Not configured (optional)"
        else:
            status = "Configured path is missing / invalid"
        rows.append(SetupRow(key=key, label=label, path=path, ok=ok, status=status))
    return rows


def setup_view_model(project: FragmenterProjectV1) -> dict[str, Any]:
    preflight = build_preflight(project)
    return {
        "project_file": str(project.project_path),
        "workspace": project.workspace_dir,
        "ready": preflight["ready"],
        "blockers": list(preflight["blockers"]),
        "warnings": list(preflight.get("warnings") or []),
        "unavailable": list(preflight.get("unavailable") or []),
        "rows": [row.to_dict() for row in setup_rows(project)],
        "runtime_paths": dict(preflight["paths"]),
    }

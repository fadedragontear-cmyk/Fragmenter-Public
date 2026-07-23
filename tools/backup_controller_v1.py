#!/usr/bin/env python3
"""Project-bound backup controller for server saves and whole memory cards."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backup_service_v1 import (
    backup_directory,
    backup_file,
    list_backup_manifests,
    load_manifest,
    restore_backup,
    verify_backup,
)
from project_workspace_v1 import FragmenterProjectV1, sha256_file


def _file_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "name": path.name,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256_file(path),
    }


def _directory_metadata(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"path": str(path), "exists": False, "files": []}
    rows: list[dict[str, Any]] = []
    for file_path in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: str(p).lower()):
        stat = file_path.stat()
        rows.append(
            {
                "relative_path": file_path.relative_to(path).as_posix(),
                "path": str(file_path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return {"path": str(path), "exists": True, "files": rows, "file_count": len(rows)}


def backup_view_model(project: FragmenterProjectV1) -> dict[str, Any]:
    saves = Path(project.sources.server_save_dir).expanduser()
    card = Path(project.sources.memory_card_path).expanduser()
    server_root = project.workspace_path("backups_server_saves")
    card_root = project.workspace_path("backups_memory_cards")
    return {
        "server_saves": _directory_metadata(saves),
        "memory_card": _file_metadata(card),
        "server_save_backups": [str(path) for path in list_backup_manifests(server_root, "server_saves")],
        "memory_card_backups": [str(path) for path in list_backup_manifests(card_root, "memory_cards")],
    }


def backup_server_saves(project: FragmenterProjectV1, *, label: str | None = None) -> dict[str, Any]:
    source = Path(project.sources.server_save_dir).expanduser()
    result = backup_directory(
        source,
        project.workspace_path("backups_server_saves"),
        category="server_saves",
        label=label,
    )
    return {
        "manifest": str(result.manifest_path),
        "backup_dir": str(result.backup_dir),
        "file_count": result.file_count,
        "total_bytes": result.total_bytes,
    }


def backup_memory_card(project: FragmenterProjectV1, *, label: str | None = None) -> dict[str, Any]:
    source = Path(project.sources.memory_card_path).expanduser()
    result = backup_file(
        source,
        project.workspace_path("backups_memory_cards"),
        category="memory_cards",
        label=label,
    )
    return {
        "manifest": str(result.manifest_path),
        "backup_dir": str(result.backup_dir),
        "file_count": result.file_count,
        "total_bytes": result.total_bytes,
    }


def _require_category(manifest_path: str | Path, category: str, kind: str) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    if manifest.get("category") != category or manifest.get("kind") != kind:
        raise ValueError(f"Expected {category}/{kind} backup, got {manifest.get('category')}/{manifest.get('kind')}")
    verification = verify_backup(manifest_path)
    if not verification["ok"]:
        raise IOError("Backup verification failed: " + "; ".join(verification["failures"]))
    return manifest


def restore_server_saves(project: FragmenterProjectV1, manifest_path: str | Path) -> dict[str, Any]:
    _require_category(manifest_path, "server_saves", "directory")
    return restore_backup(
        manifest_path,
        destination=project.sources.server_save_dir,
        safety_backup_root=project.workspace_path("backups_server_saves"),
    )


def restore_memory_card(project: FragmenterProjectV1, manifest_path: str | Path) -> dict[str, Any]:
    _require_category(manifest_path, "memory_cards", "file")
    return restore_backup(
        manifest_path,
        destination=project.sources.memory_card_path,
        safety_backup_root=project.workspace_path("backups_memory_cards"),
    )

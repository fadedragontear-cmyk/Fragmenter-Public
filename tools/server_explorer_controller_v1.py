#!/usr/bin/env python3
"""Project-bound controller for the Fragmenter 1.0 Server Explorer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from binary_preview import GZIP_MAGIC
from project_workspace_v1 import FragmenterProjectV1
from server_explorer_v1 import export_decompressed, inspect_server_file

SERVER_SUFFIXES = {".bin", ".dat", ".ini", ".kif"}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def server_file_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    root = Path(project.sources.area_server_root).expanduser()
    data = root / "data"
    if not root.is_dir():
        return []
    candidates: list[Path] = []
    if data.is_dir():
        candidates.extend(path for path in data.rglob("*") if path.is_file() and path.suffix.lower() in SERVER_SUFFIXES)
    for name in ("profile.ini", "system.dat", "gamekif.dat"):
        path = root / name
        if path.is_file():
            candidates.append(path)
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in sorted(candidates, key=lambda value: str(value).lower()):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        stat = path.stat()
        with path.open("rb") as handle:
            is_gzip = handle.read(2) == GZIP_MAGIC
        rows.append(
            {
                "name": path.name,
                "relative_path": path.relative_to(root).as_posix(),
                "path": str(path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "compression": "gzip" if is_gzip else "none/unknown",
            }
        )
    return rows


def resolve_server_file(project: FragmenterProjectV1, value: str | Path) -> Path:
    root = Path(project.sources.area_server_root).expanduser()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    if not _inside(path, root):
        raise ValueError(f"Selected file is outside the active Area Server root: {path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def inspect_project_server_file(project: FragmenterProjectV1, value: str | Path) -> dict[str, Any]:
    path = resolve_server_file(project, value)
    report = inspect_server_file(path)
    report["project_relative_path"] = path.relative_to(Path(project.sources.area_server_root).expanduser()).as_posix()
    return report


def export_project_server_file(project: FragmenterProjectV1, value: str | Path) -> dict[str, Any]:
    source = resolve_server_file(project, value)
    root = Path(project.sources.area_server_root).expanduser()
    relative = source.relative_to(root)
    suffix = relative.suffix + ".gunz" if relative.suffix else ".gunz"
    destination = project.workspace_path("extracted_server") / relative.with_suffix(suffix)
    result = export_decompressed(source, destination)
    result["project_relative_path"] = relative.as_posix()
    return result


def server_explorer_view_model(project: FragmenterProjectV1) -> dict[str, Any]:
    root = Path(project.sources.area_server_root).expanduser()
    rows = server_file_rows(project)
    return {
        "root": str(root),
        "root_exists": root.is_dir(),
        "files": rows,
        "file_count": len(rows),
        "default_tabs": ["Overview", "Clean Text", "Structure / Members", "Hex"],
        "hex_is_primary": False,
    }

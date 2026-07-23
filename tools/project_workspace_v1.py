#!/usr/bin/env python3
"""Fragmenter project/workspace authority with the canonical v2 folder layout.

The project file format remains version 1 so existing projects continue to load. The
on-disk workspace layout is versioned separately and is migrated non-destructively:
legacy top-level ``extracted_ccs``, ``sound`` and ``media_pipeline`` trees are merged
into one coherent extracted/decoded/work/reports hierarchy.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_VERSION = 1
WORKSPACE_LAYOUT_VERSION = 2
PROJECT_FILENAME = "project.json"
WORKSPACE_PATHS: dict[str, str] = {
    "source": "inputs",
    "extracted_ccs": "extracted/ccsf",
    "extracted_server": "extracted/server",
    "audio_source": "extracted/audio",
    "texture_outputs": "decoded/textures",
    "extracted_audio": "decoded/audio",
    "audio_work": "work/audio",
    # Compatibility authority for older research helpers. It no longer creates a
    # second public audio/output tree at the project root.
    "media_pipeline": "work/legacy_media_pipeline",
    "cache_iso": "cache/iso",
    "cache_ccsf_structure": "cache/ccsf_structure",
    "cache_snddata": "cache/snddata",
    "cache_mappings": "cache/mappings",
    "backups_server_saves": "backups/server_saves",
    "backups_memory_cards": "backups/memory_cards",
    "reports": "reports",
    "run_reports": "reports/run_all",
    "visual_reports": "reports/visual",
    "audio_reports": "reports/audio",
    "server_reports": "reports/server",
    "diagnostics": "reports/diagnostics",
    "asset_diagnostics": "reports/diagnostics/assets",
}
SOURCE_FIELDS = ("iso_path", "area_server_root", "server_save_dir", "memory_card_path")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_text(value: str | Path | None) -> str:
    text = "" if value is None else str(value).strip()
    return str(Path(text).expanduser()) if text else ""


def sha256_file(path: str | Path) -> str:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_identity(path: str | Path | None, *, include_sha256: bool = False) -> dict[str, Any]:
    text = _path_text(path)
    if not text:
        return {"path": "", "exists": False, "kind": "unset"}
    target = Path(text)
    identity: dict[str, Any] = {"path": str(target), "exists": target.exists(), "kind": "missing"}
    if target.is_file():
        stat = target.stat()
        identity.update({"kind": "file", "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        if include_sha256:
            identity["sha256"] = sha256_file(target)
    elif target.is_dir():
        identity.update({"kind": "directory", "mtime_ns": target.stat().st_mtime_ns})
    return identity


def _same_file(left: Path, right: Path) -> bool:
    return left.is_file() and right.is_file() and left.stat().st_size == right.stat().st_size and sha256_file(left) == sha256_file(right)


def _conflict_path(target: Path) -> Path:
    index = 1
    while True:
        candidate = target.with_name(f"{target.name}.legacy{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _remove_empty_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted((item for item in root.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass


def _merge_tree(source: Path, target: Path, actions: list[dict[str, Any]], label: str) -> None:
    if not source.exists() or source.resolve() == target.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted((item for item in source.rglob("*") if item.is_file()), key=lambda item: item.relative_to(source).as_posix().lower()):
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if _same_file(path, destination):
                path.unlink()
                status = "deduplicated"
                final = destination
            else:
                final = _conflict_path(destination)
                shutil.move(str(path), str(final))
                status = "preserved_conflict"
        else:
            shutil.move(str(path), str(destination))
            status = "moved"
            final = destination
        actions.append({"group": label, "source": str(path), "target": str(final), "status": status})
    _remove_empty_tree(source)


def migrate_workspace_layout(root: str | Path) -> dict[str, Any]:
    """Merge known legacy output trees into the canonical v2 layout.

    No differing file is overwritten. Exact duplicates are removed and conflicting
    legacy files receive a ``.legacyN`` suffix beside the canonical destination.
    """
    workspace = Path(root).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    actions: list[dict[str, Any]] = []

    canonical = {key: workspace / relative for key, relative in WORKSPACE_PATHS.items()}
    _merge_tree(workspace / "extracted_ccs", canonical["extracted_ccs"], actions, "ccsf")

    legacy_sound = workspace / "sound"
    _merge_tree(legacy_sound / "source", canonical["audio_source"], actions, "audio_source")
    _merge_tree(legacy_sound / "decoded", canonical["extracted_audio"], actions, "audio_decoded")
    _merge_tree(legacy_sound / "work", canonical["audio_work"], actions, "audio_work")
    _merge_tree(legacy_sound / "reports", canonical["audio_reports"], actions, "audio_reports")
    _remove_empty_tree(legacy_sound)

    legacy_media = workspace / "media_pipeline"
    _merge_tree(legacy_media / "decoded" / "textures", canonical["texture_outputs"], actions, "legacy_textures")
    _merge_tree(legacy_media / "decoded" / "audio", canonical["extracted_audio"] / "legacy_media_pipeline", actions, "legacy_audio")
    _merge_tree(legacy_media / "reports", workspace / "reports" / "legacy_media_pipeline", actions, "legacy_reports")
    _merge_tree(legacy_media, canonical["media_pipeline"], actions, "legacy_work")

    _merge_tree(workspace / "reports" / "visual_flags", canonical["visual_reports"] / "flags", actions, "visual_flags")

    for path in canonical.values():
        path.mkdir(parents=True, exist_ok=True)

    report = {
        "version": WORKSPACE_LAYOUT_VERSION,
        "created_at": _utc_now_iso(),
        "workspace": str(workspace),
        "canonical_paths": {key: str(path) for key, path in canonical.items()},
        "actions": actions,
        "summary": {
            "actions": len(actions),
            "moved": sum(1 for row in actions if row["status"] == "moved"),
            "deduplicated": sum(1 for row in actions if row["status"] == "deduplicated"),
            "preserved_conflicts": sum(1 for row in actions if row["status"] == "preserved_conflict"),
        },
    }
    target = canonical["run_reports"] / "workspace_layout.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    report["report_path"] = str(target)
    return report


@dataclass
class ProjectSources:
    iso_path: str = ""
    area_server_root: str = ""
    server_save_dir: str = ""
    memory_card_path: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProjectSources":
        values = data if isinstance(data, dict) else {}
        return cls(**{name: _path_text(values.get(name)) for name in SOURCE_FIELDS})

    def to_dict(self) -> dict[str, str]:
        return {name: _path_text(getattr(self, name)) for name in SOURCE_FIELDS}


@dataclass
class FragmenterProjectV1:
    workspace_dir: str
    sources: ProjectSources = field(default_factory=ProjectSources)
    version: int = PROJECT_VERSION
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    source_snapshot: dict[str, dict[str, Any]] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def project_path(self) -> Path:
        return Path(self.workspace_dir).expanduser() / PROJECT_FILENAME

    def workspace_path(self, key: str) -> Path:
        try:
            relative = WORKSPACE_PATHS[key]
        except KeyError as exc:
            raise KeyError(f"Unknown Fragmenter workspace path key: {key}") from exc
        return Path(self.workspace_dir).expanduser() / relative

    def refresh_source_snapshot(self) -> dict[str, dict[str, Any]]:
        self.source_snapshot = {name: source_identity(getattr(self.sources, name)) for name in SOURCE_FIELDS}
        return self.source_snapshot

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["workspace_dir"] = _path_text(self.workspace_dir)
        payload["sources"] = self.sources.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FragmenterProjectV1":
        if not isinstance(data, dict):
            raise ValueError("Fragmenter project JSON must contain an object")
        version = int(data.get("version") or 0)
        if version != PROJECT_VERSION:
            raise ValueError(f"Unsupported Fragmenter project version: {version}")
        workspace_dir = _path_text(data.get("workspace_dir"))
        if not workspace_dir:
            raise ValueError("Fragmenter project is missing workspace_dir")
        return cls(
            workspace_dir=workspace_dir,
            sources=ProjectSources.from_dict(data.get("sources")),
            version=version,
            created_at=str(data.get("created_at") or _utc_now_iso()),
            updated_at=str(data.get("updated_at") or _utc_now_iso()),
            source_snapshot=dict(data.get("source_snapshot") or {}),
            settings=dict(data.get("settings") or {}),
        )


def ensure_workspace_layout(project: FragmenterProjectV1) -> None:
    root = Path(project.workspace_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    migrate_workspace_layout(root)
    for relative in WORKSPACE_PATHS.values():
        (root / relative).mkdir(parents=True, exist_ok=True)
    project.settings["workspace_layout_version"] = WORKSPACE_LAYOUT_VERSION


def create_project(
    workspace_dir: str | Path,
    *,
    iso_path: str | Path | None = None,
    area_server_root: str | Path | None = None,
    server_save_dir: str | Path | None = None,
    memory_card_path: str | Path | None = None,
    settings: dict[str, Any] | None = None,
) -> FragmenterProjectV1:
    """Create a fresh project and refuse silent adoption of unrelated output."""
    root = Path(workspace_dir).expanduser()
    entries = sorted(root.iterdir(), key=lambda path: path.name.lower()) if root.exists() else []
    if entries:
        existing = root / PROJECT_FILENAME
        if existing.is_file():
            raise FileExistsError(f"Fragmenter project already exists: {existing}; use load_project()")
        raise FileExistsError(
            f"Workspace is not empty and will not be adopted automatically: {root}. "
            "Choose an empty folder for a fresh Fragmenter project."
        )
    merged_settings = dict(settings or {})
    merged_settings["workspace_layout_version"] = WORKSPACE_LAYOUT_VERSION
    project = FragmenterProjectV1(
        workspace_dir=str(root),
        sources=ProjectSources(
            iso_path=_path_text(iso_path),
            area_server_root=_path_text(area_server_root),
            server_save_dir=_path_text(server_save_dir),
            memory_card_path=_path_text(memory_card_path),
        ),
        settings=merged_settings,
    )
    ensure_workspace_layout(project)
    project.refresh_source_snapshot()
    save_project(project)
    write_project_status(project)
    return project


def save_project(project: FragmenterProjectV1, path: str | Path | None = None) -> Path:
    ensure_workspace_layout(project)
    project.updated_at = _utc_now_iso()
    target = Path(path).expanduser() if path is not None else project.project_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(project.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def load_project(path: str | Path) -> FragmenterProjectV1:
    candidate = Path(path).expanduser()
    project_path = candidate / PROJECT_FILENAME if candidate.is_dir() else candidate
    project = FragmenterProjectV1.from_dict(json.loads(project_path.read_text(encoding="utf-8")))
    if project.project_path.resolve() != project_path.resolve():
        raise ValueError(f"Project workspace_dir points to {project.project_path}, but project was loaded from {project_path}")
    ensure_workspace_layout(project)
    return project


def project_status(project: FragmenterProjectV1) -> dict[str, Any]:
    sources = {name: source_identity(getattr(project.sources, name)) for name in SOURCE_FIELDS}
    iso_ok = sources["iso_path"].get("kind") == "file"
    server_root = Path(project.sources.area_server_root) if project.sources.area_server_root else None
    server_ok = bool(server_root and server_root.is_dir() and (server_root / "data").is_dir())
    saves_ok = sources["server_save_dir"].get("kind") == "directory"
    card_ok = sources["memory_card_path"].get("kind") == "file"
    workspace = Path(project.workspace_dir).expanduser()
    workspace_ok = workspace.is_dir() and project.project_path.is_file()
    checks = {"iso": iso_ok, "area_server": server_ok, "server_saves": saves_ok, "memory_card": card_ok, "workspace": workspace_ok}
    configured = {
        "iso": bool(project.sources.iso_path),
        "area_server": bool(project.sources.area_server_root),
        "server_saves": bool(project.sources.server_save_dir),
        "memory_card": bool(project.sources.memory_card_path),
        "workspace": bool(project.workspace_dir),
    }
    return {
        "project_version": project.version,
        "workspace_layout_version": WORKSPACE_LAYOUT_VERSION,
        "workspace": {
            "path": str(workspace),
            "exists": workspace.is_dir(),
            "project_file": str(project.project_path),
            "project_file_exists": project.project_path.is_file(),
            "ok": workspace_ok,
        },
        "sources": sources,
        "checks": checks,
        "configured": configured,
        "available_sources": [
            key for key in ("iso", "area_server", "server_saves", "memory_card")
            if checks[key]
        ],
        # A project is usable as soon as its workspace and project.json are valid.
        # Source inputs are optional capabilities whose individual tools decide
        # whether they can run.
        "ready": workspace_ok,
    }


def render_project_status(status: dict[str, Any]) -> str:
    checks = dict(status.get("checks") or {})
    labels = (("iso", "ISO"), ("area_server", "Area Server"), ("server_saves", "Server Saves"), ("memory_card", "Memory Card"), ("workspace", "Workspace"))
    lines = [
        "Fragmenter Project Status",
        f"Project version: {status.get('project_version')}",
        f"Workspace layout: {status.get('workspace_layout_version')}",
        f"Ready: {'yes' if status.get('ready') else 'no'}",
        "",
    ]
    configured = dict(status.get("configured") or {})
    for key, label in labels:
        if checks.get(key):
            state = "OK"
        elif key != "workspace" and not configured.get(key):
            state = "OPTIONAL"
        else:
            state = "INVALID"
        lines.append(f"{state}  {label}")
    return "\n".join(lines) + "\n"


def write_project_status(project: FragmenterProjectV1) -> tuple[Path, Path]:
    status = project_status(project)
    reports = project.workspace_path("run_reports")
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / "project_status.json"
    text_path = reports / "project_status.txt"
    json_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(render_project_status(status), encoding="utf-8")
    return json_path, text_path

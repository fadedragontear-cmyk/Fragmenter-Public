#!/usr/bin/env python3
"""Project-state helpers for Fragmenter workbench sessions.

The state file intentionally stores user-selected paths rather than hardcoding a
specific machine layout.  Example only: a Windows user might choose paths such as
``D:\\Games\\Fragment\\SLUS.iso`` and ``D:\\FragmentServer\\area_server``.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KEY_ROOT_FILES = ("profile.ini", "system.dat", "gamekif.dat")
KEY_DATA_FILES = (
    "town.bin", "dungeon.bin", "field.bin", "enemy.bin", "equip.bin", "event.bin",
    "menu.bin", "text.bin", "OnlineEvent.dat", "skill.bin", "pack.bin", "pc.bin", "boss.bin",
)
ISO_PROBE_STRINGS = (
    "DATA.BIN", "data.bin", "CCSFtown04", "town04.cmp", "DMY_merchant",
    "sr4sun", "sr4clo", ".tm2", ".bmp", ".max",
)
EXTRACTED_ASSET_SUFFIXES = (
    ".ccs", ".cmp", ".raw.cmp", ".decompressed.ccs", ".png", ".jpg", ".jpeg",
    ".bmp", ".gif", ".tm2", ".obj", ".json",
)

WORKSPACE_DIR_NAMES = ("reports", "extracted_ccs", "exports", "patch_plans", "cache")
PROJECT_STATE_FILENAME = "fragmenter_project.json"
CURRENT_PATCH_PLAN_FILENAME = "current_patch_plan.json"
PATCH_PLAN_STATUSES = ("planned", "validated", "built", "failed")
SAFE_PATCH_PLAN_ACTION_TYPES = ("note", "export", "research")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class FragmenterSettings:
    celdra_animation_enabled: bool = True
    console_expanded: bool = False
    safe_mode_enabled: bool = True


@dataclass
class FragmenterProjectState:
    iso_path: str | None = None
    area_server_root: str | None = None
    area_server_data_dir: str | None = None
    workspace_dir: str = "workspace"
    extracted_assets_dir: str = "workspace/extracted_ccs"
    reports_dir: str = "workspace/reports"
    last_reports: list[str] = field(default_factory=list)
    last_opened_files: list[str] = field(default_factory=list)
    settings: FragmenterSettings = field(default_factory=FragmenterSettings)

    @classmethod
    def default(cls, root: str | Path = ".") -> "FragmenterProjectState":
        root_path = Path(root)
        workspace = root_path / "workspace"
        return cls(
            workspace_dir=str(workspace),
            extracted_assets_dir=str(workspace / "extracted_ccs"),
            reports_dir=str(workspace / "reports"),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FragmenterProjectState":
        values = dict(data)
        settings = values.get("settings") or {}
        if isinstance(settings, FragmenterSettings):
            values["settings"] = settings
        elif isinstance(settings, dict):
            values["settings"] = FragmenterSettings(**{k: v for k, v in settings.items() if k in FragmenterSettings.__dataclass_fields__})
        else:
            values["settings"] = FragmenterSettings()
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in values.items() if k in allowed})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def state_path(self) -> Path:
        return Path(self.workspace_dir) / PROJECT_STATE_FILENAME


def _file_entry(path: Path, root: Path | None = None) -> dict[str, Any]:
    try:
        stat = path.stat()
        size = stat.st_size
    except OSError:
        size = None
    return {
        "name": path.name,
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if root else path.name,
        "size": size,
        "exists": path.exists(),
    }


def inspect_area_server_root(root: str | Path) -> dict[str, Any]:
    """Return lightweight Area Server project-loading metadata without deep scans."""
    root_path = Path(root).expanduser()
    data_dir = root_path / "data"
    root_files = [_file_entry(root_path / name, root_path) for name in KEY_ROOT_FILES if (root_path / name).is_file()]
    exe = root_path / "AREA SERVER.exe"
    data_files: list[dict[str, Any]] = []
    if data_dir.is_dir():
        data_files = [
            _file_entry(path, root_path)
            for path in sorted([*data_dir.glob("*.bin"), *data_dir.glob("*.dat")], key=lambda p: p.name.lower())
            if path.is_file()
        ]
    data_by_lower = {entry["name"].lower(): entry for entry in data_files}
    return {
        "root": str(root_path),
        "exists": root_path.is_dir(),
        "data_dir": str(data_dir),
        "data_dir_exists": data_dir.is_dir(),
        "area_server_exe": _file_entry(exe, root_path) if exe.is_file() else None,
        "root_files": root_files,
        "data_files": data_files,
        "key_data_files": [data_by_lower[name.lower()] for name in KEY_DATA_FILES if name.lower() in data_by_lower],
        "missing_key_data_files": [name for name in KEY_DATA_FILES if name.lower() not in data_by_lower],
    }


def inspect_iso(path: str | Path, compute_sha1: bool = False, quick_probe: bool = False) -> dict[str, Any]:
    """Return ISO metadata. SHA1 and string probes run only when explicitly requested."""
    iso = Path(path).expanduser()
    info: dict[str, Any] = {"path": str(iso), "exists": iso.is_file(), "size": iso.stat().st_size if iso.is_file() else None}
    if not iso.is_file():
        return info
    if compute_sha1:
        h = hashlib.sha1()
        with iso.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        info["sha1"] = h.hexdigest()
    if quick_probe:
        raw = iso.read_bytes()
        info["quick_probe_hits"] = {term: raw.find(term.encode("ascii")) for term in ISO_PROBE_STRINGS}
        info["quick_probe_hits"] = {k: v for k, v in info["quick_probe_hits"].items() if v >= 0}
    return info


def list_reports(workspace_dir: str | Path) -> list[dict[str, Any]]:
    reports = Path(workspace_dir).expanduser() / "reports"
    if not reports.is_dir():
        return []
    return [_file_entry(path, reports) for path in sorted([*reports.glob("*.txt"), *reports.glob("*.json")], key=lambda p: p.name.lower()) if path.is_file()]


def list_extracted_assets(workspace_dir: str | Path) -> list[dict[str, Any]]:
    extracted = Path(workspace_dir).expanduser() / "extracted_ccs"
    if not extracted.is_dir():
        return []
    rows = []
    for path in sorted((p for p in extracted.rglob("*") if p.is_file()), key=lambda p: str(p).lower()):
        lower_name = path.name.lower()
        if any(lower_name.endswith(suffix) for suffix in EXTRACTED_ASSET_SUFFIXES):
            rows.append(_file_entry(path, extracted))
    return rows


def initialize_workspace(root: str | Path = ".", state: FragmenterProjectState | None = None) -> FragmenterProjectState:
    """Create the standard workbench workspace folders and return project state."""
    project = state or FragmenterProjectState.default(root)
    workspace = Path(project.workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    for name in WORKSPACE_DIR_NAMES:
        (workspace / name).mkdir(parents=True, exist_ok=True)
    project.reports_dir = str(workspace / "reports")
    project.extracted_assets_dir = str(workspace / "extracted_ccs")
    return project


def save_project(state: FragmenterProjectState, path: str | Path | None = None) -> Path:
    """Save project state as JSON, defaulting to workspace/fragmenter_project.json."""
    target = Path(path) if path is not None else state.state_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def load_project(path: str | Path = Path("workspace") / PROJECT_STATE_FILENAME) -> FragmenterProjectState:
    """Load project state from JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return FragmenterProjectState.from_dict(data)


def load_or_initialize(root: str | Path = ".") -> FragmenterProjectState:
    state_path = Path(root) / "workspace" / PROJECT_STATE_FILENAME
    if state_path.exists():
        state = load_project(state_path)
    else:
        state = FragmenterProjectState.default(root)
    return initialize_workspace(root, state)


def _sha1_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _path_hash_summary(path: str | Path | None, *, include_children: bool = False) -> dict[str, Any]:
    """Return a read-only path/hash summary for patch-plan provenance."""
    if not path:
        return {"path": None, "exists": False, "kind": "missing", "sha1": None}
    target = Path(path).expanduser()
    summary: dict[str, Any] = {"path": str(target), "exists": target.exists()}
    if target.is_file():
        stat = target.stat()
        summary.update({"kind": "file", "size": stat.st_size, "sha1": _sha1_file(target)})
        return summary
    summary.update({"kind": "directory" if target.is_dir() else "missing", "sha1": None})
    if target.is_dir() and include_children:
        children = []
        for child in sorted((p for p in target.iterdir() if p.is_file()), key=lambda p: p.name.lower()):
            children.append({
                "name": child.name,
                "relative_path": child.name,
                "size": child.stat().st_size,
                "sha1": _sha1_file(child),
            })
        summary["files"] = children
        joined = "".join(f"{c['relative_path']}:{c['size']}:{c['sha1']}\n" for c in children).encode("utf-8")
        summary["hash_summary"] = hashlib.sha1(joined).hexdigest() if children else None
    return summary


def _server_root_hash_summary(path: str | Path | None) -> dict[str, Any]:
    summary = _path_hash_summary(path)
    root = Path(path).expanduser() if path else None
    if not root or not root.is_dir():
        return summary
    relevant: list[Path] = []
    for name in KEY_ROOT_FILES:
        candidate = root / name
        if candidate.is_file():
            relevant.append(candidate)
    data_dir = root / "data"
    if data_dir.is_dir():
        for name in KEY_DATA_FILES:
            candidate = data_dir / name
            if candidate.is_file():
                relevant.append(candidate)
    files = []
    for child in sorted(relevant, key=lambda p: str(p.relative_to(root)).lower()):
        rel = str(child.relative_to(root))
        files.append({"relative_path": rel, "size": child.stat().st_size, "sha1": _sha1_file(child)})
    joined = "".join(f"{c['relative_path']}:{c['size']}:{c['sha1']}\n" for c in files).encode("utf-8")
    summary.update({"kind": "directory", "files": files, "hash_summary": hashlib.sha1(joined).hexdigest() if files else None})
    return summary


def patch_plan_path(workspace_dir: str | Path = "workspace") -> Path:
    return Path(workspace_dir).expanduser() / "patch_plans" / CURRENT_PATCH_PLAN_FILENAME


def create_patch_plan(state: FragmenterProjectState | None = None, *, notes: list[str] | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    """Create a non-destructive patch plan skeleton with source provenance."""
    state = state or FragmenterProjectState.default(".")
    return {
        "version": 1,
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "project_sources": {
            "iso": _path_hash_summary(state.iso_path),
            "server_root": _server_root_hash_summary(state.area_server_root),
        },
        "planned_actions": [],
        "notes": list(notes or []),
        "warnings": list(warnings or ["Patch plans are read-only metadata; do not write to original ISO or Area Server files."]),
    }


def load_patch_plan(workspace_dir: str | Path = "workspace", state: FragmenterProjectState | None = None) -> dict[str, Any]:
    path = patch_plan_path(workspace_dir)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return create_patch_plan(state)


def save_patch_plan(plan: dict[str, Any], workspace_dir: str | Path = "workspace") -> Path:
    path = patch_plan_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    plan["updated_at"] = _utc_now_iso()
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def add_patch_plan_action(plan: dict[str, Any], *, source: str = "gui", file: str | None = None, member: str | int | None = None, offset: str | int | None = None, type: str = "note", description: str = "", old_value_hash: str | None = None, new_value_hash: str | None = None, status: str = "planned") -> dict[str, Any]:
    """Add a safe planned action. Unknown/destructive action types are rejected."""
    if status not in PATCH_PLAN_STATUSES:
        raise ValueError(f"Invalid patch-plan status: {status}")
    if type not in SAFE_PATCH_PLAN_ACTION_TYPES:
        raise ValueError(f"Unsupported or destructive patch-plan action type: {type}")
    actions = plan.setdefault("planned_actions", [])
    action = {
        "action_id": f"action-{len(actions) + 1:04d}",
        "source": source,
        "file": file,
        "member": member,
        "offset": offset,
        "type": type,
        "description": description,
        "old value/hash": old_value_hash,
        "new value/hash": new_value_hash,
        "status": status,
    }
    actions.append(action)
    return action


def add_safe_note_to_current_patch_plan(state: FragmenterProjectState, *, source: str, file: str | None, member: str | int | None = None, offset: str | int | None = None, description: str = "") -> tuple[Path, dict[str, Any]]:
    plan = load_patch_plan(state.workspace_dir, state)
    plan["project_sources"] = {"iso": _path_hash_summary(state.iso_path), "server_root": _server_root_hash_summary(state.area_server_root)}
    action = add_patch_plan_action(plan, source=source, file=file, member=member, offset=offset, type="note", description=description or "Safe note-only research/export action", status="planned")
    path = save_patch_plan(plan, state.workspace_dir)
    return path, action


if __name__ == "__main__":
    project = load_or_initialize()
    print(save_project(project))

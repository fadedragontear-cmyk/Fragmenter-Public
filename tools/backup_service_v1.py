#!/usr/bin/env python3
"""Verified, non-editor backup/restore primitives for Fragmenter 1.0.

The service supports two public-release workflows:

* Area Server save-folder backups.
* Whole memory-card file backups.

Every backup has a manifest with SHA-256 identities. Restore verifies the stored
copy and snapshots the current destination before replacing any file.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from project_workspace_v1 import sha256_file

BACKUP_MANIFEST_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
OPERATIONS_LOG = "operations.jsonl"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return cleaned.strip("_") or "backup"


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p).lower()):
        yield path


def _unique_backup_dir(root: Path, category: str, label: str) -> Path:
    parent = root / _safe_label(category)
    parent.mkdir(parents=True, exist_ok=True)
    stem = f"{_utc_stamp()}_{_safe_label(label)}"
    candidate = parent / stem
    suffix = 1
    while candidate.exists():
        candidate = parent / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".fragmenter_tmp")
    if temp.exists():
        temp.unlink()
    shutil.copy2(source, temp)
    os.replace(temp, destination)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _append_operation(root: Path, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / OPERATIONS_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


@dataclass(frozen=True)
class BackupResult:
    manifest_path: Path
    backup_dir: Path
    file_count: int
    total_bytes: int


def _file_record(source: Path, relative_path: Path, stored: Path) -> dict[str, Any]:
    stat = source.stat()
    return {
        "relative_path": relative_path.as_posix(),
        "source_path": str(source),
        "stored_path": str(stored),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256_file(source),
    }


def backup_file(
    source: str | Path,
    backup_root: str | Path,
    *,
    category: str = "memory_cards",
    label: str | None = None,
) -> BackupResult:
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    root = Path(backup_root).expanduser()
    backup_dir = _unique_backup_dir(root, category, label or source_path.stem)
    stored = backup_dir / "files" / source_path.name
    _atomic_copy(source_path, stored)
    record = _file_record(source_path, Path(source_path.name), stored)
    if sha256_file(stored) != record["sha256"]:
        raise IOError(f"Backup verification failed: {stored}")
    manifest = {
        "version": BACKUP_MANIFEST_VERSION,
        "created_at": _utc_iso(),
        "kind": "file",
        "category": category,
        "source_path": str(source_path),
        "backup_root": str(root),
        "backup_dir": str(backup_dir),
        "files": [record],
    }
    manifest_path = backup_dir / MANIFEST_FILENAME
    _write_json(manifest_path, manifest)
    _append_operation(root, {"at": _utc_iso(), "action": "backup", "manifest": str(manifest_path), "kind": "file"})
    return BackupResult(manifest_path, backup_dir, 1, int(record["size"]))


def backup_directory(
    source_dir: str | Path,
    backup_root: str | Path,
    *,
    category: str = "server_saves",
    label: str | None = None,
) -> BackupResult:
    source_root = Path(source_dir).expanduser()
    if not source_root.is_dir():
        raise NotADirectoryError(source_root)
    root = Path(backup_root).expanduser()
    backup_dir = _unique_backup_dir(root, category, label or source_root.name)
    records: list[dict[str, Any]] = []
    total = 0
    for source in _iter_files(source_root):
        relative = source.relative_to(source_root)
        stored = backup_dir / "files" / relative
        _atomic_copy(source, stored)
        record = _file_record(source, relative, stored)
        if sha256_file(stored) != record["sha256"]:
            raise IOError(f"Backup verification failed: {stored}")
        records.append(record)
        total += int(record["size"])
    manifest = {
        "version": BACKUP_MANIFEST_VERSION,
        "created_at": _utc_iso(),
        "kind": "directory",
        "category": category,
        "source_path": str(source_root),
        "backup_root": str(root),
        "backup_dir": str(backup_dir),
        "files": records,
    }
    manifest_path = backup_dir / MANIFEST_FILENAME
    _write_json(manifest_path, manifest)
    _append_operation(root, {"at": _utc_iso(), "action": "backup", "manifest": str(manifest_path), "kind": "directory"})
    return BackupResult(manifest_path, backup_dir, len(records), total)


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(payload.get("version") or 0) != BACKUP_MANIFEST_VERSION:
        raise ValueError(f"Unsupported backup manifest version: {payload.get('version')}")
    if payload.get("kind") not in {"file", "directory"}:
        raise ValueError("Backup manifest has an invalid kind")
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("Backup manifest files must be a list")
    return payload


def verify_backup(path: str | Path) -> dict[str, Any]:
    manifest = load_manifest(path)
    checked = 0
    failures: list[str] = []
    for record in manifest["files"]:
        stored = Path(str(record.get("stored_path") or ""))
        expected = str(record.get("sha256") or "")
        if not stored.is_file():
            failures.append(f"missing: {stored}")
            continue
        actual = sha256_file(stored)
        if actual != expected:
            failures.append(f"hash mismatch: {stored}")
            continue
        checked += 1
    return {"ok": not failures, "checked": checked, "failures": failures, "manifest": str(Path(path))}


def _snapshot_destination(manifest: dict[str, Any], destination: Path, backup_root: Path) -> Path | None:
    if manifest["kind"] == "file":
        if not destination.is_file():
            return None
        return backup_file(destination, backup_root, category="pre_restore", label=destination.stem).manifest_path
    if not destination.is_dir() or not any(destination.iterdir()):
        return None
    return backup_directory(destination, backup_root, category="pre_restore", label=destination.name).manifest_path


def restore_backup(
    manifest_path: str | Path,
    *,
    destination: str | Path | None = None,
    safety_backup_root: str | Path | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    verification = verify_backup(manifest_path)
    if not verification["ok"]:
        raise IOError("Backup verification failed: " + "; ".join(verification["failures"]))
    target = Path(destination).expanduser() if destination is not None else Path(str(manifest["source_path"])).expanduser()
    root = Path(safety_backup_root).expanduser() if safety_backup_root is not None else Path(str(manifest["backup_root"])).expanduser()
    safety_manifest = _snapshot_destination(manifest, target, root)

    restored = 0
    if manifest["kind"] == "file":
        record = manifest["files"][0]
        stored = Path(str(record["stored_path"]))
        _atomic_copy(stored, target)
        if sha256_file(target) != record["sha256"]:
            raise IOError(f"Restore verification failed: {target}")
        restored = 1
    else:
        target.mkdir(parents=True, exist_ok=True)
        for record in manifest["files"]:
            stored = Path(str(record["stored_path"]))
            out = target / Path(str(record["relative_path"]))
            _atomic_copy(stored, out)
            if sha256_file(out) != record["sha256"]:
                raise IOError(f"Restore verification failed: {out}")
            restored += 1

    result = {
        "at": _utc_iso(),
        "action": "restore",
        "manifest": str(Path(manifest_path).expanduser()),
        "destination": str(target),
        "restored_files": restored,
        "pre_restore_manifest": str(safety_manifest) if safety_manifest else None,
    }
    _append_operation(root, result)
    return result


def list_backup_manifests(backup_root: str | Path, category: str | None = None) -> list[Path]:
    root = Path(backup_root).expanduser()
    search_root = root / _safe_label(category) if category else root
    if not search_root.is_dir():
        return []
    return sorted(search_root.rglob(MANIFEST_FILENAME), key=lambda p: p.stat().st_mtime_ns, reverse=True)

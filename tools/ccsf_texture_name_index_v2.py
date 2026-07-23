#!/usr/bin/env python3
"""Persistent exact-name index for external CCS MAT/TEX/CLUT records.

Normal candidate lookup is intentionally cheap and never scans the complete
library. The GUI may call ensure_index() in a background worker once, after a
local textured preview is already visible. CCS object names live near the file
front, so indexing reads only a bounded leading window from each asset.
"""
from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

ASSET_SUFFIXES = {".ccs", ".ccsf", ".tmp", ".bin"}
NAME_PATTERN = re.compile(rb"(?:TEX|MAT|CLT|CLUT)_[\x20-\x7e]{1,29}(?=\x00)")
VERSION = 2
INDEX_SCAN_BYTES = 32 * 1024 * 1024
_INDEX: dict[str, dict[str, list[Path]]] = {}
_LOCAL: dict[tuple[str, str], list[Path]] = {}
_EVENTS: dict[str, threading.Event] = {}
_LOCK = threading.Lock()


def root_for(source: str | Path) -> Path:
    resolved = Path(source).expanduser().resolve()
    for candidate in (resolved, resolved.parent, *resolved.parents):
        if candidate.name.lower() == "extracted_ccs":
            return candidate
    return resolved.parent


def report_path(source: str | Path) -> Path:
    root = root_for(source)
    return root.parent / "diagnostics" / "visual" / "ccsf_texture_name_index_v2.json"


def _read_index_head(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(INDEX_SCAN_BYTES)


def _load(root: Path) -> dict[str, list[Path]] | None:
    path = report_path(root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != VERSION:
        return None
    output: dict[str, list[Path]] = {}
    for name, rows in (payload.get("names") or {}).items():
        paths = []
        for relative in rows or []:
            candidate = root / Path(*str(relative).replace("\\", "/").split("/"))
            if candidate.is_file():
                paths.append(candidate.resolve())
        if paths:
            output[str(name)] = list(dict.fromkeys(paths))
    return output


def index_ready(source: str | Path) -> bool:
    root = root_for(source)
    key = str(root.resolve())
    with _LOCK:
        if key in _INDEX:
            return True
    loaded = _load(root)
    if loaded is None:
        return False
    with _LOCK:
        _INDEX[key] = loaded
    return True


def _local_candidates(source: Path, name: str) -> list[Path]:
    key = (str(source.parent.resolve()), name)
    if key in _LOCAL:
        return list(_LOCAL[key])
    needle = name.encode("cp1252", errors="ignore") + b"\x00"
    rows = []
    for candidate in sorted(source.parent.iterdir(), key=lambda item: item.name.lower()):
        if not candidate.is_file() or candidate.suffix.lower() not in ASSET_SUFFIXES:
            continue
        try:
            if needle in _read_index_head(candidate):
                rows.append(candidate.resolve())
        except OSError:
            continue
    _LOCAL[key] = rows
    return list(rows)


def candidate_files(source: str | Path, object_name: str) -> list[Path]:
    source_path = Path(source).expanduser().resolve()
    root = root_for(source_path)
    key = str(root.resolve())
    rows = _local_candidates(source_path, object_name)
    with _LOCK:
        index = _INDEX.get(key)
    if index is None:
        index = _load(root)
        if index is not None:
            with _LOCK:
                _INDEX[key] = index
    if index is not None:
        rows.extend(index.get(object_name, []))
    unique = list(dict.fromkeys(path.resolve() for path in rows if path.is_file()))
    unique.sort(key=lambda path: (0 if path == source_path else 1 if path.parent == source_path.parent else 2, path.as_posix().lower()))
    return unique


def ensure_index(
    source: str | Path,
    *,
    rebuild: bool = False,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    root = root_for(source)
    key = str(root.resolve())
    if not rebuild and index_ready(root):
        with _LOCK:
            current = _INDEX.get(key, {})
        return {"status": "ready", "names": len(current), "report_path": str(report_path(root)), "reused": True}

    with _LOCK:
        event = _EVENTS.get(key)
        if event is None:
            event = threading.Event()
            _EVENTS[key] = event
            owner = True
        else:
            owner = False
    if not owner:
        event.wait()
        with _LOCK:
            current = _INDEX.get(key, {})
        return {"status": "ready", "names": len(current), "report_path": str(report_path(root)), "reused": True}

    files = [path for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()) if path.is_file() and path.suffix.lower() in ASSET_SUFFIXES]
    names: dict[str, list[Path]] = defaultdict(list)
    skipped = []
    truncated_files = 0
    try:
        for number, candidate in enumerate(files, 1):
            try:
                size = candidate.stat().st_size
                data = _read_index_head(candidate)
                if size > len(data):
                    truncated_files += 1
            except OSError:
                skipped.append({"path": candidate.relative_to(root).as_posix()})
                continue
            for match in NAME_PATTERN.finditer(data):
                names[match.group(0).decode("cp1252", errors="ignore")].append(candidate.resolve())
            if callback is not None and (number == len(files) or number % 25 == 0):
                callback({"current": number, "total": len(files), "detail": candidate.name})
        normalized = {name: list(dict.fromkeys(paths)) for name, paths in names.items()}
        payload = {
            "version": VERSION,
            "root": key,
            "scan_bytes_per_file": INDEX_SCAN_BYTES,
            "files_considered": len(files),
            "files_scanned": len(files) - len(skipped),
            "files_larger_than_scan_window": truncated_files,
            "names_indexed": len(normalized),
            "skipped": skipped,
            "names": {name: [path.relative_to(root).as_posix() for path in paths] for name, paths in sorted(normalized.items())},
        }
        target = report_path(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with _LOCK:
            _INDEX[key] = normalized
        return {
            "status": "built",
            "names": len(normalized),
            "files_scanned": payload["files_scanned"],
            "skipped": len(skipped),
            "report_path": str(target),
            "reused": False,
        }
    finally:
        with _LOCK:
            finished = _EVENTS.pop(key, None)
            if finished is not None:
                finished.set()

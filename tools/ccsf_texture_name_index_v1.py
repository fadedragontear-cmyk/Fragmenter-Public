#!/usr/bin/env python3
"""One-pass exact MAT/TEX/CLUT name index for extracted CCS libraries."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ASSET_SUFFIXES = {".ccs", ".ccsf", ".tmp", ".bin"}
_NAME_PATTERN = re.compile(rb"(?:TEX|MAT|CLT|CLUT)_[\x20-\x7E]{1,29}(?=\x00)")
_ROOT_INDEX: dict[str, dict[str, list[Path]]] = {}


def _root_for(source: Path) -> Path:
    resolved = source.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name.lower() == "extracted_ccs":
            return parent
    return resolved.parent


def clear_name_index(root: str | Path | None = None) -> None:
    if root is None:
        _ROOT_INDEX.clear()
    else:
        _ROOT_INDEX.pop(str(Path(root).expanduser().resolve()), None)


def _load_probe(root: Path, index: dict[str, list[Path]]) -> None:
    report_path = root.parent / "diagnostics" / "visual" / "ccsf_texture_library_probe_v1.json"
    if not report_path.is_file():
        return
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for name, rows in (payload.get("texture_name_index") or {}).items():
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            relative = str(row.get("asset") or "").strip()
            candidate = root / Path(*relative.replace("\\", "/").split("/"))
            if candidate.is_file():
                index[str(name)].append(candidate.resolve())


def _build(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = defaultdict(list)
    _load_probe(root, index)
    for candidate in sorted(root.rglob("*"), key=lambda path: path.as_posix().lower()):
        if not candidate.is_file() or candidate.suffix.lower() not in ASSET_SUFFIXES:
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        names = {
            match.group(0).decode("cp1252", errors="ignore")
            for match in _NAME_PATTERN.finditer(data)
        }
        resolved = candidate.resolve()
        for name in names:
            index[name].append(resolved)
    return {
        name: list(dict.fromkeys(paths))
        for name, paths in index.items()
    }


def candidate_files(source: str | Path, object_name: str) -> list[Path]:
    source_path = Path(source).expanduser().resolve()
    root = _root_for(source_path)
    key = str(root.resolve())
    index = _ROOT_INDEX.get(key)
    if index is None:
        index = _build(root)
        _ROOT_INDEX[key] = index
    candidates = list(index.get(object_name, []))
    candidates.sort(key=lambda path: (0 if path.parent == source_path.parent else 1, path.as_posix().lower()))
    return candidates

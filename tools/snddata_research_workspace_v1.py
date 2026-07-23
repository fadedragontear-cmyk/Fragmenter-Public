#!/usr/bin/env python3
"""Persistent notes and research-bundle flags for SNDDATA assets."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_sound_v1 import sound_reports_root
from project_workspace_v1 import FragmenterProjectV1

STORE_NAME = "snddata_research_workspace_v1.json"
STORE_VERSION = 1


def store_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / STORE_NAME


def _empty() -> dict[str, Any]:
    return {"version": STORE_VERSION, "assets": {}}


def load_workspace(project: FragmenterProjectV1) -> dict[str, Any]:
    path = store_path(project)
    if not path.is_file():
        return _empty()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), dict):
        return _empty()
    payload.setdefault("version", STORE_VERSION)
    return payload


def _write(project: FragmenterProjectV1, payload: dict[str, Any]) -> Path:
    path = store_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def asset_key(
    kind: str,
    *,
    sequence_id: str,
    resource_offset: int | None = None,
    sample_id: int | None = None,
) -> str:
    parts = [str(kind), str(sequence_id)]
    if resource_offset is not None:
        parts.append(f"resource@0x{int(resource_offset):X}")
    if sample_id is not None:
        parts.append(f"sample@{int(sample_id):04d}")
    return "|".join(parts)


def get_record(project: FragmenterProjectV1, key: str) -> dict[str, Any]:
    row = (load_workspace(project).get("assets") or {}).get(str(key))
    return dict(row) if isinstance(row, dict) else {}


def save_record(
    project: FragmenterProjectV1,
    key: str,
    *,
    kind: str,
    sequence_id: str,
    resource_offset: int | None = None,
    sample_id: int | None = None,
    flagged: bool | None = None,
    notes: str | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = load_workspace(project)
    assets = payload.setdefault("assets", {})
    current = dict(assets.get(str(key)) or {})
    current.update(
        {
            "key": str(key),
            "kind": str(kind),
            "sequence_id": str(sequence_id),
            "resource_offset": int(resource_offset) if resource_offset is not None else None,
            "sample_id": int(sample_id) if sample_id is not None else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if flagged is not None:
        current["flagged"] = bool(flagged)
    current.setdefault("flagged", False)
    if notes is not None:
        current["notes"] = str(notes)
    current.setdefault("notes", "")
    if snapshot is not None:
        current["snapshot"] = dict(snapshot)
    assets[str(key)] = current
    _write(project, payload)
    return current


def flagged_records(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in (load_workspace(project).get("assets") or {}).values()
        if isinstance(row, dict) and bool(row.get("flagged"))
    ]
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("sequence_id") or ""),
            str(row.get("kind") or ""),
            int(row.get("resource_offset") or -1),
            int(row.get("sample_id") or -1),
        ),
    )

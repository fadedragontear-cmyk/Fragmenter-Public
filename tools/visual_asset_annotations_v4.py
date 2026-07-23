#!/usr/bin/env python3
"""Canonical visual-report path compatibility for workspace layout v2.

The accepted annotation behavior remains unchanged. This layer only reads the new
``reports/visual/classifications`` ledger first and rewrites historical
``reports/visual_flags`` references after the files have been migrated to
``reports/visual/flags``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import visual_asset_annotations_v1 as base
import visual_asset_annotations_v3  # noqa: F401  # install reviewed defaults first

_PREVIOUS_MERGE = base._merge_latest_ledger
_PREVIOUS_LOAD = base.load_annotation
_PREVIOUS_RECORDS = base.annotation_records


def _canonical_report_path(project, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.replace("\\", "/")
    marker = "/reports/visual_flags/"
    lower = normalized.casefold()
    index = lower.find(marker)
    if index < 0:
        return text
    relative = normalized[index + len(marker) :]
    target = project.workspace_path("visual_reports") / "flags" / Path(relative)
    return str(target)


def _record_from_ledger_row(project, row: dict[str, Any]) -> tuple[str, dict[str, Any], str] | None:
    key = str(row.get("asset_key") or "").strip()
    if not key:
        return None
    category = str(row.get("manual_category") or "").strip()
    record: dict[str, Any] = {
        "category": category,
        "notes": str(row.get("notes") or ""),
        "flagged": bool(row.get("flagged", False)),
        "last_report": _canonical_report_path(project, row.get("last_report")),
        "default_animation": str(row.get("default_animation") or ""),
        "default_frame": max(0, int(row.get("default_frame") or 0)),
    }
    if bool(row.get("camera_saved", False)):
        record.update(
            {
                "camera_saved": True,
                "camera_yaw": row.get("camera_yaw"),
                "camera_pitch": row.get("camera_pitch"),
                "camera_zoom": row.get("camera_zoom"),
                "camera_pan_x": row.get("camera_pan_x"),
                "camera_pan_y": row.get("camera_pan_y"),
                "camera_background": row.get("camera_background"),
                "camera_basis": row.get("camera_basis") or [],
                "camera_position": row.get("camera_position") or [],
            }
        )
    return key, record, category


def _merge_layout_v2_ledger(project, store: dict[str, Any]) -> None:
    path = project.workspace_path("visual_reports") / "classifications" / "visual_classifications_latest.json"
    payload = base._read_json(path)
    rows = payload.get("records") or []
    if not isinstance(rows, list):
        return
    recovered: dict[str, dict[str, Any]] = {}
    categories: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _record_from_ledger_row(project, row)
        if parsed is None:
            continue
        key, record, category = parsed
        recovered[key] = record
        if category:
            categories.append(category)
    base._merge_payload(store, {"categories": categories, "assets": recovered}, overwrite=False)


def _merge_latest_ledger_v4(project, store: dict[str, Any]) -> None:
    _merge_layout_v2_ledger(project, store)
    _PREVIOUS_MERGE(project, store)


def _normalize_store_paths(project) -> bool:
    store = base._store(project)
    changed = False
    for raw in store.get("assets", {}).values():
        if not isinstance(raw, dict):
            continue
        previous = str(raw.get("last_report") or "")
        current = _canonical_report_path(project, previous)
        if current != previous:
            raw["last_report"] = current
            changed = True
    if changed:
        base._write_sidecar(project, store)
    return changed


def load_annotation(project, source: str | Path) -> dict[str, Any]:
    _normalize_store_paths(project)
    result = dict(_PREVIOUS_LOAD(project, source))
    result["last_report"] = _canonical_report_path(project, result.get("last_report"))
    return result


def annotation_records(project) -> dict[str, dict[str, Any]]:
    _normalize_store_paths(project)
    return _PREVIOUS_RECORDS(project)


def install() -> None:
    base._merge_latest_ledger = _merge_latest_ledger_v4
    base.load_annotation = load_annotation
    base.annotation_records = annotation_records


install()

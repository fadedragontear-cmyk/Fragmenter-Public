#!/usr/bin/env python3
"""Free-fly camera-position extension for durable visual annotations."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

import visual_asset_annotations_v1 as base

_BASE_LOAD_ANNOTATION = base.load_annotation
_BASE_SAVE_ANNOTATION = base.save_annotation
_BASE_MERGE_LATEST_LEDGER = base._merge_latest_ledger


def _position(value: Iterable[float] | None) -> list[float]:
    try:
        rows = [float(component) for component in (value or ())]
    except (TypeError, ValueError):
        return []
    if len(rows) != 3 or not all(math.isfinite(component) for component in rows):
        return []
    return rows


def _merge_latest_ledger_v2(project, store: dict[str, Any]) -> None:
    _BASE_MERGE_LATEST_LEDGER(project, store)
    path = project.workspace_path("reports") / "visual_classifications" / "visual_classifications_latest.json"
    payload = base._read_json(path)
    records = payload.get("records") or []
    if not isinstance(records, list):
        return
    for row in records:
        if not isinstance(row, dict):
            continue
        key = str(row.get("asset_key") or "").strip()
        if not key:
            continue
        position = _position(row.get("camera_position"))
        if not position:
            position = _position(
                (
                    row.get("camera_position_x"),
                    row.get("camera_position_y"),
                    row.get("camera_position_z"),
                )
            )
        if not position:
            continue
        current = store.get("assets", {}).setdefault(key, {})
        if isinstance(current, dict) and not _position(current.get("camera_position")):
            current["camera_position"] = position


def load_annotation(project, source: str | Path) -> dict[str, Any]:
    result = dict(_BASE_LOAD_ANNOTATION(project, source))
    raw = base._store(project)["assets"].get(base.asset_key(project, source))
    raw = raw if isinstance(raw, dict) else {}
    position = _position(raw.get("camera_position"))
    camera = result.get("camera")
    if isinstance(camera, dict) and position:
        camera = dict(camera)
        camera["position"] = position
        result["camera"] = camera
    return result


def save_annotation(
    project,
    source: str | Path,
    *,
    category: str | None = None,
    notes: str | None = None,
    flagged: bool | None = None,
    last_report: str | None = None,
    default_animation: str | None = None,
    default_frame: int | None = None,
    camera_yaw: float | None = None,
    camera_pitch: float | None = None,
    camera_zoom: float | None = None,
    camera_pan_x: float | None = None,
    camera_pan_y: float | None = None,
    camera_background: str | None = None,
    camera_basis: list[float] | tuple[float, ...] | None = None,
    camera_position: list[float] | tuple[float, ...] | None = None,
    clear_camera: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    # Let v1 update all established fields and its atomic sidecar first. Defer the
    # complete project save until the free-fly position has joined the same record.
    _BASE_SAVE_ANNOTATION(
        project,
        source,
        category=category,
        notes=notes,
        flagged=flagged,
        last_report=last_report,
        default_animation=default_animation,
        default_frame=default_frame,
        camera_yaw=camera_yaw,
        camera_pitch=camera_pitch,
        camera_zoom=camera_zoom,
        camera_pan_x=camera_pan_x,
        camera_pan_y=camera_pan_y,
        camera_background=camera_background,
        camera_basis=camera_basis,
        clear_camera=clear_camera,
        persist=False,
    )
    store = base._store(project)
    key = base.asset_key(project, source)
    raw = store["assets"].setdefault(key, {})
    if not isinstance(raw, dict):
        raw = {}
        store["assets"][key] = raw
    if clear_camera:
        raw.pop("camera_position", None)
    elif camera_position is not None:
        position = _position(camera_position)
        if not position:
            raise ValueError("camera_position must contain three finite values")
        raw["camera_position"] = position
    base._write_sidecar(project, store)
    if persist:
        base.save_project(project)
    return load_annotation(project, source)


def install() -> None:
    base._merge_latest_ledger = _merge_latest_ledger_v2
    base.load_annotation = load_annotation
    base.save_annotation = save_annotation


install()

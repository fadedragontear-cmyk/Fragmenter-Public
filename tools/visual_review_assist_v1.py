#!/usr/bin/env python3
"""Conservative classification-review helpers derived from confirmed asset families."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from visual_asset_annotations_v1 import annotation_records, asset_key

_COLOR_SUFFIX = re.compile(r"_(?:bl|br|gr|yl|pp|rd)$", re.IGNORECASE)


def family_key(value: str | Path) -> str:
    stem = Path(str(value).replace("\\", "/")).stem.lower()
    if stem.startswith("xgfood"):
        return "xgfood"
    if re.fullmatch(r"field_a\d*", stem):
        return "field_a"
    if re.fullmatch(r"cwdhkn\d+(?:_\d+)?", stem):
        return re.sub(r"_\d+$", "", stem)
    if stem in {"xdl_load", "xdl_log"}:
        return "xdl"
    stripped = _COLOR_SUFFIX.sub("", stem)
    return stripped


def _float_list(value: Any, length: int) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        return []
    try:
        return [float(component) for component in value]
    except (TypeError, ValueError):
        return []


def complete_camera(record: dict[str, Any]) -> bool:
    return bool(record.get("camera_saved")) and bool(_float_list(record.get("camera_basis"), 9)) and bool(
        _float_list(record.get("camera_position"), 3)
    )


def suggest_camera_from_records(
    records: dict[str, dict[str, Any]],
    target_key: str,
) -> dict[str, Any] | None:
    target = str(target_key).replace("\\", "/")
    target_family = family_key(target)
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    for key, raw in records.items():
        if str(key).replace("\\", "/") == target or family_key(key) != target_family:
            continue
        if not isinstance(raw, dict) or not complete_camera(raw):
            continue
        similarity = SequenceMatcher(None, Path(target).stem.lower(), Path(key).stem.lower()).ratio()
        candidates.append((similarity, str(key), raw))
    if not candidates:
        return None
    _similarity, source_key, record = max(candidates, key=lambda item: (item[0], item[1]))
    return {
        "source_asset_key": source_key,
        "family": target_family,
        "yaw": float(record.get("camera_yaw") or 0.0),
        "pitch": float(record.get("camera_pitch") or 0.0),
        "zoom": max(0.15, min(8.0, float(record.get("camera_zoom") or 1.0))),
        "pan_x": float(record.get("camera_pan_x") or 0.0),
        "pan_y": float(record.get("camera_pan_y") or 0.0),
        "background": str(record.get("camera_background") or "Dark Gray"),
        "basis": _float_list(record.get("camera_basis"), 9),
        "position": _float_list(record.get("camera_position"), 3),
    }


def suggest_project_camera(project, source: str | Path) -> dict[str, Any] | None:
    key = asset_key(project, source)
    return suggest_camera_from_records(annotation_records(project), key)

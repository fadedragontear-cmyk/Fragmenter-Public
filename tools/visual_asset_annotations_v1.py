#!/usr/bin/env python3
"""Persistent user categories, notes, pose/view choices and report references."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_workspace_v1 import FragmenterProjectV1, save_project

SETTINGS_KEY = "visual_asset_annotations_v1"
SIDECAR_FORMAT = "Fragmenter visual annotations v1"


def asset_key(project: FragmenterProjectV1, source: str | Path) -> str:
    candidate = Path(source).expanduser().resolve()
    root = project.workspace_path("extracted_ccs").resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()


def _workspace_root(project: FragmenterProjectV1) -> Path:
    value = str(getattr(project, "workspace_dir", "") or "").strip()
    if value:
        return Path(value).expanduser()
    return project.workspace_path("extracted_ccs").expanduser().parent


def annotation_sidecar_path(project: FragmenterProjectV1) -> Path:
    return _workspace_root(project) / "review" / "visual_asset_annotations.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _merge_asset_record(target: dict[str, Any], source: dict[str, Any], *, overwrite: bool) -> None:
    for key, value in source.items():
        if overwrite or key not in target or target.get(key) in (None, "", [], {}):
            target[key] = value


def _merge_payload(store: dict[str, Any], payload: dict[str, Any], *, overwrite: bool) -> None:
    categories = payload.get("categories") or []
    known = {str(value).casefold() for value in store["categories"]}
    for value in categories:
        normalized = str(value or "").strip()
        if normalized and normalized.casefold() not in known:
            store["categories"].append(normalized)
            known.add(normalized.casefold())
    assets = payload.get("assets") or {}
    if isinstance(assets, dict):
        for key, value in assets.items():
            if not isinstance(value, dict):
                continue
            current = store["assets"].setdefault(str(key), {})
            if not isinstance(current, dict):
                current = {}
                store["assets"][str(key)] = current
            _merge_asset_record(current, value, overwrite=overwrite)


def _merge_latest_ledger(project: FragmenterProjectV1, store: dict[str, Any]) -> None:
    """Recover missing annotations from the most recent portable ledger.

    The ledger only fills absent fields. Current project settings remain authoritative,
    while the immediate annotation sidecar loaded afterward is allowed to override both.
    """
    path = project.workspace_path("reports") / "visual_classifications" / "visual_classifications_latest.json"
    payload = _read_json(path)
    records = payload.get("records") or []
    if not isinstance(records, list):
        return
    recovered: dict[str, dict[str, Any]] = {}
    categories: list[str] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        key = str(row.get("asset_key") or "").strip()
        if not key:
            continue
        category = str(row.get("manual_category") or "").strip()
        if category:
            categories.append(category)
        record: dict[str, Any] = {
            "category": category,
            "notes": str(row.get("notes") or ""),
            "flagged": bool(row.get("flagged", False)),
            "last_report": str(row.get("last_report") or ""),
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
                }
            )
        recovered[key] = record
    _merge_payload(store, {"categories": categories, "assets": recovered}, overwrite=False)


def _write_sidecar(project: FragmenterProjectV1, store: dict[str, Any]) -> Path:
    path = annotation_sidecar_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": SIDECAR_FORMAT,
        "categories": list(store.get("categories") or []),
        "assets": dict(store.get("assets") or {}),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _store(project: FragmenterProjectV1) -> dict[str, Any]:
    value = project.settings.setdefault(SETTINGS_KEY, {})
    if not isinstance(value, dict):
        value = {}
        project.settings[SETTINGS_KEY] = value
    value.setdefault("categories", [])
    value.setdefault("assets", {})
    if not isinstance(value["categories"], list):
        value["categories"] = []
    if not isinstance(value["assets"], dict):
        value["assets"] = {}
    if not bool(getattr(project, "_fragmenter_visual_annotations_loaded_v1", False)):
        _merge_latest_ledger(project, value)
        sidecar = _read_json(annotation_sidecar_path(project))
        _merge_payload(value, sidecar, overwrite=True)
        value["categories"] = sorted(
            {str(item).strip() for item in value["categories"] if str(item).strip()},
            key=str.casefold,
        )
        setattr(project, "_fragmenter_visual_annotations_loaded_v1", True)
    return value


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _camera_from_raw(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not bool(raw.get("camera_saved", False)):
        return None
    yaw = _optional_float(raw.get("camera_yaw"))
    pitch = _optional_float(raw.get("camera_pitch"))
    zoom = _optional_float(raw.get("camera_zoom"))
    pan_x = _optional_float(raw.get("camera_pan_x"))
    pan_y = _optional_float(raw.get("camera_pan_y"))
    if None in (yaw, pitch, zoom, pan_x, pan_y):
        return None
    raw_basis = raw.get("camera_basis")
    basis = [float(value) for value in raw_basis] if isinstance(raw_basis, (list, tuple)) and len(raw_basis) == 9 else []
    return {
        "yaw": float(yaw),
        "pitch": float(pitch),
        "zoom": max(0.15, min(8.0, float(zoom))),
        "pan_x": float(pan_x),
        "pan_y": float(pan_y),
        "background": str(raw.get("camera_background") or "Dark Gray"),
        "basis": basis,
    }


def annotation_records(project: FragmenterProjectV1) -> dict[str, dict[str, Any]]:
    """Return a defensive copy of every saved visual annotation by asset key."""
    records: dict[str, dict[str, Any]] = {}
    for key, value in _store(project)["assets"].items():
        if isinstance(value, dict):
            records[str(key)] = dict(value)
    return records


def custom_categories(project: FragmenterProjectV1) -> list[str]:
    store = _store(project)
    values = {str(value).strip() for value in store["categories"] if str(value).strip()}
    for row in store["assets"].values():
        if isinstance(row, dict) and str(row.get("category") or "").strip():
            values.add(str(row["category"]).strip())
    return sorted(values, key=str.casefold)


def ensure_category(project: FragmenterProjectV1, category: str, *, persist: bool = True) -> str:
    normalized = str(category or "").strip()
    if not normalized:
        raise ValueError("category cannot be empty")
    store = _store(project)
    existing = {str(value).casefold() for value in store["categories"]}
    if normalized.casefold() not in existing:
        store["categories"].append(normalized)
        store["categories"].sort(key=lambda value: str(value).casefold())
        _write_sidecar(project, store)
        if persist:
            save_project(project)
    return normalized


def load_annotation(project: FragmenterProjectV1, source: str | Path) -> dict[str, Any]:
    store = _store(project)
    raw = store["assets"].get(asset_key(project, source))
    raw = raw if isinstance(raw, dict) else {}
    camera = _camera_from_raw(raw)
    return {
        "category": str(raw.get("category") or "").strip(),
        "notes": str(raw.get("notes") or ""),
        "flagged": bool(raw.get("flagged", False)),
        "last_report": str(raw.get("last_report") or ""),
        "default_animation": str(raw.get("default_animation") or "").strip(),
        "default_frame": max(0, int(raw.get("default_frame") or 0)),
        "camera_saved": camera is not None,
        "camera": camera,
    }


def save_annotation(
    project: FragmenterProjectV1,
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
    clear_camera: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    """Update memory and the small annotation sidecar immediately.

    The complete project file can remain an asynchronous GUI save. Categories,
    notes and pose/view state are durable before this function returns.
    """
    store = _store(project)
    key = asset_key(project, source)
    current = load_annotation(project, source)
    raw = dict(store["assets"].get(key) or {})
    if category is not None:
        current["category"] = str(category).strip()
        if current["category"]:
            existing = {str(value).casefold() for value in store["categories"]}
            if current["category"].casefold() not in existing:
                store["categories"].append(current["category"])
                store["categories"].sort(key=lambda value: str(value).casefold())
    if notes is not None:
        current["notes"] = str(notes)
    if flagged is not None:
        current["flagged"] = bool(flagged)
    if last_report is not None:
        current["last_report"] = str(last_report)
    if default_animation is not None:
        current["default_animation"] = str(default_animation).strip()
    if default_frame is not None:
        current["default_frame"] = max(0, int(default_frame))

    raw.update(
        {
            "category": current["category"],
            "notes": current["notes"],
            "flagged": current["flagged"],
            "last_report": current["last_report"],
            "default_animation": current["default_animation"],
            "default_frame": current["default_frame"],
        }
    )
    camera_values = (camera_yaw, camera_pitch, camera_zoom, camera_pan_x, camera_pan_y)
    if clear_camera:
        for field in (
            "camera_saved",
            "camera_yaw",
            "camera_pitch",
            "camera_zoom",
            "camera_pan_x",
            "camera_pan_y",
            "camera_background",
            "camera_basis",
        ):
            raw.pop(field, None)
    elif any(value is not None for value in camera_values) or camera_background is not None or camera_basis is not None:
        if any(value is None for value in camera_values):
            raise ValueError("saving a camera view requires yaw, pitch, zoom, pan_x and pan_y")
        basis = [float(value) for value in (camera_basis or [])]
        if basis and len(basis) != 9:
            raise ValueError("camera_basis must contain nine matrix values")
        raw.update(
            {
                "camera_saved": True,
                "camera_yaw": float(camera_yaw),
                "camera_pitch": float(camera_pitch),
                "camera_zoom": max(0.15, min(8.0, float(camera_zoom))),
                "camera_pan_x": float(camera_pan_x),
                "camera_pan_y": float(camera_pan_y),
                "camera_background": str(camera_background or "Dark Gray"),
                "camera_basis": basis,
            }
        )
    store["assets"][key] = raw
    _write_sidecar(project, store)
    if persist:
        save_project(project)
    return load_annotation(project, source)


def apply_annotation(project: FragmenterProjectV1, row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    annotation = load_annotation(project, row["absolute_path"])
    automatic_kind = str(row.get("automatic_kind") or row.get("kind") or "")
    automatic_confidence = str(
        row.get("automatic_classification_confidence")
        or row.get("classification_confidence")
        or ""
    ).strip()
    automatic_source = str(
        row.get("automatic_classification_source")
        or row.get("classification_source")
        or ""
    ).strip()
    automatic_evidence = list(
        row.get("automatic_classification_evidence")
        or row.get("classification_evidence")
        or []
    )
    output["automatic_kind"] = automatic_kind
    output["automatic_classification_confidence"] = automatic_confidence
    output["automatic_classification_source"] = automatic_source
    output["automatic_classification_evidence"] = automatic_evidence
    marker_parts: list[str] = []
    if annotation["category"]:
        output["kind"] = annotation["category"]
        output["classification_source"] = "user category"
        output["classification_evidence"] = [f"manual category override; automatic category: {automatic_kind}"]
        marker_parts.append("manual")
    else:
        output["kind"] = automatic_kind
        output["classification_source"] = automatic_source
        output["classification_evidence"] = automatic_evidence
        if automatic_confidence:
            marker_parts.append(automatic_confidence)
    if annotation["notes"].strip():
        marker_parts.append("notes")
    if annotation["flagged"]:
        marker_parts.append("flagged")
    if annotation["default_animation"]:
        marker_parts.append("pose")
    if annotation["camera_saved"]:
        marker_parts.append("view")
    output["classification_confidence"] = " • ".join(marker_parts)
    output["user_notes"] = annotation["notes"]
    output["flagged_for_report"] = annotation["flagged"]
    output["last_report"] = annotation["last_report"]
    output["default_animation"] = annotation["default_animation"]
    output["default_frame"] = annotation["default_frame"]
    output["camera_saved"] = annotation["camera_saved"]
    output["saved_camera"] = annotation["camera"]
    return output

#!/usr/bin/env python3
"""Persistent non-destructive per-asset preview profiles."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from project_workspace_v1 import FragmenterProjectV1, save_project

SETTINGS_KEY = "asset_preview_profiles_v1"
DEFAULT_PROFILE: dict[str, Any] = {
    "clump_id": None,
    "animation": "",
    "frame": 0,
    "camera": {"yaw": -0.55, "pitch": 0.35, "zoom": 1.25, "pan_x": 0.0, "pan_y": 0.0},
    "transform": {
        "scale": [1.0, 1.0, 1.0],
        "rotation_degrees": [0.0, 0.0, 0.0],
        "translation": [0.0, 0.0, 0.0],
        "flip_winding": False,
    },
}


def _float_list(value: Any, default: list[float]) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < len(default):
        return list(default)
    rows: list[float] = []
    for index, fallback in enumerate(default):
        try:
            rows.append(float(value[index]))
        except (TypeError, ValueError):
            rows.append(float(fallback))
    return rows


def profile_key(project: FragmenterProjectV1, source: str | Path) -> str:
    candidate = Path(source).expanduser().resolve()
    extracted = project.workspace_path("extracted_ccs").resolve()
    try:
        return candidate.relative_to(extracted).as_posix()
    except ValueError:
        return candidate.as_posix()


def normalize_profile(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    camera = raw.get("camera") if isinstance(raw.get("camera"), dict) else {}
    transform = raw.get("transform") if isinstance(raw.get("transform"), dict) else {}
    clump = raw.get("clump_id")
    try:
        clump_id = int(clump) if clump is not None else None
    except (TypeError, ValueError):
        clump_id = None
    return {
        "clump_id": clump_id,
        "animation": str(raw.get("animation") or ""),
        "frame": max(0, int(raw.get("frame") or 0)),
        "camera": {
            "yaw": float(camera.get("yaw", DEFAULT_PROFILE["camera"]["yaw"])),
            "pitch": float(camera.get("pitch", DEFAULT_PROFILE["camera"]["pitch"])),
            "zoom": max(0.15, min(8.0, float(camera.get("zoom", DEFAULT_PROFILE["camera"]["zoom"])))),
            "pan_x": float(camera.get("pan_x", 0.0)),
            "pan_y": float(camera.get("pan_y", 0.0)),
        },
        "transform": {
            "scale": _float_list(transform.get("scale"), [1.0, 1.0, 1.0]),
            "rotation_degrees": _float_list(transform.get("rotation_degrees"), [0.0, 0.0, 0.0]),
            "translation": _float_list(transform.get("translation"), [0.0, 0.0, 0.0]),
            "flip_winding": bool(transform.get("flip_winding", False)),
        },
    }


def load_profile(project: FragmenterProjectV1, source: str | Path) -> dict[str, Any]:
    profiles = project.settings.get(SETTINGS_KEY)
    stored = profiles.get(profile_key(project, source)) if isinstance(profiles, dict) else None
    return normalize_profile(stored)


def save_profile(project: FragmenterProjectV1, source: str | Path, profile: dict[str, Any]) -> dict[str, Any]:
    profiles = project.settings.setdefault(SETTINGS_KEY, {})
    if not isinstance(profiles, dict):
        profiles = {}
        project.settings[SETTINGS_KEY] = profiles
    normalized = normalize_profile(profile)
    profiles[profile_key(project, source)] = normalized
    save_project(project)
    return normalized


def delete_profile(project: FragmenterProjectV1, source: str | Path) -> bool:
    profiles = project.settings.get(SETTINGS_KEY)
    if not isinstance(profiles, dict):
        return False
    removed = profiles.pop(profile_key(project, source), None) is not None
    if removed:
        save_project(project)
    return removed

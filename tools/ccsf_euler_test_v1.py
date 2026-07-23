#!/usr/bin/env python3
"""Session-only Euler/axis-angle test profile for Gen1 puppetry research.

The profile is deliberately global to the active preview process: wireframe, textured
playback and puppetry reports must evaluate the same experiment. It is never written
into an asset annotation or project file.
"""
from __future__ import annotations

from threading import RLock
from typing import Any

ORDERS = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")
MAPS = ORDERS
SIGNS = ("+++", "-++", "+-+", "++-", "--+", "-+-", "+--", "---")
PARENT_MODES = ("LXP", "PXL")

# Confirmed against ca1ab_bl on 2026-07-15.  This combination keeps the established
# StudioCCS Z/-Y/X component conversion, applies the resulting local rotations in ZYX
# order, and resolves the row-vector hierarchy as local * parent.
_DEFAULT = {
    "component_map": "ZYX",
    "order": "ZYX",
    "signs": "+-+",
    "parent_mode": "LXP",
}
_PROFILE = dict(_DEFAULT)
_LOCK = RLock()


def _choice(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    normalized = str(value or "").strip().upper().replace("×", "X")
    return normalized if normalized in allowed else fallback


def normalize_profile(value: Any = None) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {
        "component_map": _choice(raw.get("component_map"), MAPS, _DEFAULT["component_map"]),
        "order": _choice(raw.get("order"), ORDERS, _DEFAULT["order"]),
        "signs": _choice(raw.get("signs"), SIGNS, _DEFAULT["signs"]),
        "parent_mode": _choice(raw.get("parent_mode"), PARENT_MODES, _DEFAULT["parent_mode"]),
    }


def get_profile() -> dict[str, str]:
    with _LOCK:
        return dict(_PROFILE)


def set_profile(
    *,
    component_map: str | None = None,
    order: str | None = None,
    signs: str | None = None,
    parent_mode: str | None = None,
) -> dict[str, str]:
    with _LOCK:
        candidate = dict(_PROFILE)
        if component_map is not None:
            candidate["component_map"] = component_map
        if order is not None:
            candidate["order"] = order
        if signs is not None:
            candidate["signs"] = signs
        if parent_mode is not None:
            candidate["parent_mode"] = parent_mode
        _PROFILE.clear()
        _PROFILE.update(normalize_profile(candidate))
        return dict(_PROFILE)


def reset_profile() -> dict[str, str]:
    """Return to the user-confirmed Fragment default, not the retired XYZ baseline."""
    with _LOCK:
        _PROFILE.clear()
        _PROFILE.update(_DEFAULT)
        return dict(_PROFILE)


def studio_ccs_profile() -> dict[str, str]:
    """Apply the confirmed StudioCCS-derived Fragment profile."""
    return set_profile(component_map="ZYX", order="ZYX", signs="+-+", parent_mode="LXP")


def mapped_components(rotation: Any, profile: dict[str, str] | None = None) -> dict[str, float]:
    try:
        source_values = tuple(float(value) for value in rotation)
    except (TypeError, ValueError):
        source_values = (0.0, 0.0, 0.0)
    if len(source_values) != 3:
        source_values = (0.0, 0.0, 0.0)
    source = dict(zip("XYZ", source_values))
    active = normalize_profile(profile or get_profile())
    mapping = active["component_map"]
    signs = active["signs"]
    return {
        local_axis: source[source_axis] * (-1.0 if sign == "-" else 1.0)
        for local_axis, source_axis, sign in zip("XYZ", mapping, signs)
    }


def pipeline_label(profile: dict[str, str] | None = None) -> str:
    active = normalize_profile(profile or get_profile())
    chain = "local * parent" if active["parent_mode"] == "LXP" else "parent * local"
    return (
        "Gen1 Euler radians -> shortest-arc component interpolation -> "
        f"map {active['component_map']} signs {active['signs']} -> "
        f"row-vector {active['order']} axis-angle matrices -> {chain} hierarchy"
    )

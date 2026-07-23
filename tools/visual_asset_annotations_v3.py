#!/usr/bin/env python3
"""Final canonical visual classifications from the completed 2026-07-15 review.

The repository snapshot is fallback data. Merge order remains:

1. existing project settings,
2. latest portable classification ledger,
3. canonical repository defaults for fields still missing,
4. the immediate review sidecar as newest authority.

Later local edits therefore remain authoritative.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import visual_asset_annotations_v1 as base

FORMAT = "Fragmenter canonical visual classifications v2"
STATE_FORMAT = "Fragmenter canonical visual state v2"
CANONICAL_PATH = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "visual_classifications"
    / "visual_classifications_canonical_v1.json"
)

_BASE_MERGE_LATEST_LEDGER = base._merge_latest_ledger
_BASE_LOAD_ANNOTATION = base.load_annotation
_CANONICAL_CACHE: dict[str, Any] | None = None
_CANONICAL_ASSET_CACHE: dict[str, dict[str, Any]] | None = None
_CANONICAL_STATE_CACHE: dict[str, dict[str, Any]] | None = None
_CANONICAL_RULE_CACHE: list[tuple[re.Pattern[str], str, str]] | None = None


def canonical_payload() -> dict[str, Any]:
    global _CANONICAL_CACHE
    if _CANONICAL_CACHE is None:
        try:
            raw = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        _CANONICAL_CACHE = raw if isinstance(raw, dict) and raw.get("format") == FORMAT else {}
    return dict(_CANONICAL_CACHE)


def _resource_path(raw: Any) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    candidate = (CANONICAL_PATH.parent / value).resolve()
    root = CANONICAL_PATH.parent.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _section_assets(path: Path) -> dict[str, dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    category = ""
    assets: dict[str, dict[str, Any]] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            category = line[1:-1].strip()
            continue
        if category:
            assets[line.casefold()] = {"category": category}
    return assets


def _camera_fields(value: Any) -> dict[str, Any]:
    if not isinstance(value, list) or len(value) != 8:
        return {}
    yaw, pitch, zoom, pan_x, pan_y, background, basis, position = value
    return {
        "camera_saved": True,
        "camera_yaw": yaw,
        "camera_pitch": pitch,
        "camera_zoom": zoom,
        "camera_pan_x": pan_x,
        "camera_pan_y": pan_y,
        "camera_background": str(background or "Dark Gray"),
        "camera_basis": list(basis) if isinstance(basis, list) else [],
        "camera_position": list(position) if isinstance(position, list) else [],
    }


def _canonical_state(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    global _CANONICAL_STATE_CACHE
    if _CANONICAL_STATE_CACHE is not None:
        return {key: dict(value) for key, value in _CANONICAL_STATE_CACHE.items()}
    rows: list[Any] = []
    for raw_path in payload.get("state_files") or []:
        path = _resource_path(raw_path)
        if path is None:
            continue
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            candidate = {}
        if isinstance(candidate, dict) and candidate.get("format") == STATE_FORMAT:
            rows.extend(candidate.get("records") or [])
    state: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 7:
            continue
        key, notes, flagged, report, animation, frame, camera = row
        normalized = str(key or "").strip().casefold()
        if not normalized:
            continue
        record: dict[str, Any] = {
            "notes": str(notes or ""),
            "flagged": bool(flagged),
            "last_report": str(report or ""),
            "default_animation": str(animation or ""),
            "default_frame": max(0, int(frame or 0)),
        }
        record.update(_camera_fields(camera))
        state[normalized] = record
    _CANONICAL_STATE_CACHE = {key: dict(value) for key, value in state.items()}
    return {key: dict(value) for key, value in state.items()}


def _canonical_assets(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    global _CANONICAL_ASSET_CACHE
    if _CANONICAL_ASSET_CACHE is not None:
        return {key: dict(value) for key, value in _CANONICAL_ASSET_CACHE.items()}
    assets: dict[str, dict[str, Any]] = {}
    for raw_path in payload.get("asset_files") or []:
        path = _resource_path(raw_path)
        if path is not None:
            assets.update(_section_assets(path))
    for key, state in _canonical_state(payload).items():
        current = assets.setdefault(key, {})
        for field, value in state.items():
            current.setdefault(field, value)
    _CANONICAL_ASSET_CACHE = {key: dict(value) for key, value in assets.items()}
    return {key: dict(value) for key, value in assets.items()}


def _canonical_rules(payload: dict[str, Any]) -> list[tuple[re.Pattern[str], str, str]]:
    global _CANONICAL_RULE_CACHE
    if _CANONICAL_RULE_CACHE is not None:
        return list(_CANONICAL_RULE_CACHE)
    rules: list[tuple[re.Pattern[str], str, str]] = []
    for raw in payload.get("classification_rules") or []:
        if not isinstance(raw, dict):
            continue
        pattern = str(raw.get("pattern") or "").strip()
        category = str(raw.get("category") or "").strip()
        description = str(raw.get("description") or "canonical reviewed filename family").strip()
        if not pattern or not category:
            continue
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        rules.append((compiled, category, description))
    _CANONICAL_RULE_CACHE = list(rules)
    return rules


def canonical_default(source: str | Path) -> dict[str, Any]:
    payload = canonical_payload()
    name = Path(source).name.casefold()
    result = dict(_canonical_assets(payload).get(name) or {})
    evidence = ""
    if result.get("category"):
        evidence = "explicit final visual review"
    else:
        for pattern, category, description in _canonical_rules(payload):
            if pattern.fullmatch(name):
                result["category"] = category
                evidence = description
                break
    state = _canonical_state(payload).get(name)
    if state:
        for field, value in state.items():
            result.setdefault(field, value)
    if result:
        result["canonical_source"] = "final 2026-07-15 visual ledger"
        result["canonical_evidence"] = evidence or "saved final review state"
    return result


def canonical_summary() -> dict[str, Any]:
    payload = canonical_payload()
    state = _canonical_state(payload)
    categories = payload.get("categories")
    categories = categories if isinstance(categories, list) else []
    return {
        "path": str(CANONICAL_PATH),
        "format": str(payload.get("format") or ""),
        "declared_record_count": int(payload.get("record_count") or 0),
        "explicit_record_count": len(_canonical_assets(payload)),
        "state_record_count": len(state),
        "category_count": len(categories),
        "category_counts": dict(payload.get("category_counts") or {}),
        "notes_count": int(payload.get("notes_count") or 0),
        "flagged_count": int(payload.get("flagged_count") or 0),
        "camera_count": int(payload.get("camera_count") or 0),
        "rule_count": len(_canonical_rules(payload)),
        "source_counts": dict(payload.get("source_counts") or {}),
        "report_backed_corrections": dict(payload.get("report_backed_corrections") or {}),
    }


def _merge_canonical_defaults(store: dict[str, Any]) -> None:
    payload = canonical_payload()
    categories = [
        str(value).strip()
        for value in (payload.get("categories") or [])
        if str(value).strip()
    ]
    base._merge_payload(
        store,
        {"categories": categories, "assets": _canonical_assets(payload)},
        overwrite=False,
    )


def _merge_latest_ledger_v3(project, store: dict[str, Any]) -> None:
    _BASE_MERGE_LATEST_LEDGER(project, store)
    _merge_canonical_defaults(store)


def load_annotation(project, source: str | Path) -> dict[str, Any]:
    result = dict(_BASE_LOAD_ANNOTATION(project, source))
    canonical = canonical_default(source)
    if not canonical:
        return result

    store = base._store(project)
    key = base.asset_key(project, source)
    raw = store["assets"].setdefault(key, {})
    if not isinstance(raw, dict):
        raw = {}
        store["assets"][key] = raw

    changed = False
    for field in (
        "category",
        "notes",
        "last_report",
        "default_animation",
        "camera_yaw",
        "camera_pitch",
        "camera_zoom",
        "camera_pan_x",
        "camera_pan_y",
        "camera_background",
        "camera_basis",
        "camera_position",
    ):
        value = canonical.get(field)
        if field not in canonical:
            continue
        if field not in raw or raw.get(field) in (None, "", [], {}):
            raw[field] = value
            changed = True
    for field in ("flagged", "camera_saved"):
        if field in canonical and field not in raw:
            raw[field] = bool(canonical[field])
            changed = True
    if "default_frame" in canonical and "default_frame" not in raw:
        raw["default_frame"] = max(0, int(canonical.get("default_frame") or 0))
        changed = True

    if changed:
        result = dict(_BASE_LOAD_ANNOTATION(project, source))
    result["canonical_source"] = str(canonical.get("canonical_source") or "")
    result["canonical_evidence"] = str(canonical.get("canonical_evidence") or "")
    return result


def install() -> None:
    base._merge_latest_ledger = _merge_latest_ledger_v3
    base.load_annotation = load_annotation


install()

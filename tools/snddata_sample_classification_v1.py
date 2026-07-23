#!/usr/bin/env python3
"""Persistent classification records for decoded SNDDATA samples."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_sound_v1 import sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_sample_bridge_v1 import normalized_sample_rows

STORE_NAME = "snddata_sample_classification_v1.json"
STORE_VERSION = 2
CATEGORIES = (
    "Unclassified",
    "Instrument",
    "Percussion",
    "Voice",
    "Ambience",
    "Effect",
    "Interface",
    "Unknown",
)
PLAYBACK_MODES = ("Pitched", "One-shot", "Drum", "Texture")
USABILITY = ("Unreviewed", "Usable", "Questionable", "Reject")


def store_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / STORE_NAME


def sample_key(resource_offset: int, sample_id: int) -> str:
    return f"resource@0x{int(resource_offset):X}|sample@{int(sample_id):04d}"


def _empty() -> dict[str, Any]:
    return {"version": STORE_VERSION, "custom_categories": [], "samples": {}}


def load_store(project: FragmenterProjectV1) -> dict[str, Any]:
    path = store_path(project)
    if not path.is_file():
        return _empty()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(payload, dict) or not isinstance(payload.get("samples"), dict):
        return _empty()
    payload.setdefault("version", STORE_VERSION)
    payload.setdefault("custom_categories", [])
    return payload


def _write(project: FragmenterProjectV1, payload: dict[str, Any]) -> Path:
    path = store_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["version"] = STORE_VERSION
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def _clean_category_name(value: str) -> str:
    name = " ".join(str(value or "").strip().split())
    if not name:
        raise ValueError("Category name cannot be empty")
    if len(name) > 48:
        raise ValueError("Category names are limited to 48 characters")
    if name.casefold() == "all":
        raise ValueError("'All' is reserved for filters")
    return name


def available_categories(project: FragmenterProjectV1) -> tuple[str, ...]:
    payload = load_store(project)
    custom: list[str] = []
    seen = {value.casefold() for value in CATEGORIES}
    for raw in payload.get("custom_categories") or []:
        try:
            name = _clean_category_name(str(raw))
        except ValueError:
            continue
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        custom.append(name)
    custom.sort(key=str.casefold)
    return (*CATEGORIES, *custom)


def create_category(project: FragmenterProjectV1, name: str) -> str:
    cleaned = _clean_category_name(name)
    existing = available_categories(project)
    match = next((value for value in existing if value.casefold() == cleaned.casefold()), None)
    if match is not None:
        return match
    payload = load_store(project)
    custom = [str(value) for value in payload.get("custom_categories") or []]
    custom.append(cleaned)
    payload["custom_categories"] = custom
    _write(project, payload)
    return cleaned


def get_classification(
    project: FragmenterProjectV1,
    resource_offset: int,
    sample_id: int,
) -> dict[str, Any]:
    key = sample_key(resource_offset, sample_id)
    row = (load_store(project).get("samples") or {}).get(key)
    return dict(row) if isinstance(row, dict) else {}


def save_classification(
    project: FragmenterProjectV1,
    resource_offset: int,
    sample_id: int,
    *,
    label: str,
    category: str,
    family: str,
    playback_mode: str,
    root_note: int,
    usability: str,
    tags: str = "",
    notes: str = "",
    source_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    categories = available_categories(project)
    canonical_category = next(
        (value for value in categories if value.casefold() == str(category).casefold()),
        None,
    )
    if canonical_category is None:
        raise ValueError(f"Unknown sample category: {category}")
    if playback_mode not in PLAYBACK_MODES:
        raise ValueError(f"Unknown playback mode: {playback_mode}")
    if usability not in USABILITY:
        raise ValueError(f"Unknown usability status: {usability}")
    root_note = max(0, min(127, int(root_note)))

    payload = load_store(project)
    samples = payload.setdefault("samples", {})
    key = sample_key(resource_offset, sample_id)
    row = dict(samples.get(key) or {})
    row.update(
        {
            "key": key,
            "resource_offset": int(resource_offset),
            "sample_id": int(sample_id),
            "label": str(label).strip() or f"sample {int(sample_id):04d}",
            "category": canonical_category,
            "family": str(family).strip(),
            "playback_mode": playback_mode,
            "root_note": root_note,
            "usability": usability,
            "tags": str(tags).strip(),
            "notes": str(notes),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if source_snapshot is not None:
        row["source_snapshot"] = dict(source_snapshot)
    samples[key] = row
    _write(project, payload)
    return row


def send_to_category(
    project: FragmenterProjectV1,
    resource_offset: int,
    sample_id: int,
    category: str,
    *,
    source_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assign only the category while preserving all existing classification fields."""
    current = get_classification(project, resource_offset, sample_id)
    source = dict(source_snapshot or {})
    default_mode = {
        "Percussion": "Drum",
        "Ambience": "Texture",
        "Effect": "One-shot",
        "Interface": "One-shot",
        "Voice": "One-shot",
    }.get(str(category), "Pitched")
    return save_classification(
        project,
        resource_offset,
        sample_id,
        label=str(
            current.get("label")
            or source.get("classification_label")
            or source.get("display_name")
            or f"sample {int(sample_id):04d}"
        ),
        category=category,
        family=str(current.get("family") or source.get("family") or ""),
        playback_mode=str(current.get("playback_mode") or source.get("playback_mode") or default_mode),
        root_note=int(
            current.get("root_note")
            if current.get("root_note") is not None
            else source.get("root_note") if source.get("root_note") is not None else 60
        ),
        usability=str(current.get("usability") or source.get("usability") or "Unreviewed"),
        tags=str(current.get("tags") or source.get("tags") or ""),
        notes=str(current.get("notes") or source.get("classification_notes") or ""),
        source_snapshot=source or None,
    )


def classified_sample_rows(
    project: FragmenterProjectV1,
    *,
    query: str = "",
    category: str = "All",
    usability: str = "All",
) -> list[dict[str, Any]]:
    store = load_store(project)
    records = store.get("samples") or {}
    needle = str(query or "").strip().casefold()
    output: list[dict[str, Any]] = []

    for raw in normalized_sample_rows(project):
        if not isinstance(raw, dict):
            continue
        resource = int(
            raw.get("resource_id")
            if raw.get("resource_id") is not None
            else raw.get("resource_offset") or 0
        )
        sample_id = int(
            raw.get("sample_id")
            if raw.get("sample_id") is not None
            else raw.get("index") or 0
        )
        key = sample_key(resource, sample_id)
        saved = records.get(key) if isinstance(records.get(key), dict) else {}
        row = {
            **raw,
            "key": key,
            "resource_offset": resource,
            "resource_id": resource,
            "sample_id": sample_id,
            "index": sample_id,
            "classification_label": str(saved.get("label") or raw.get("display_name") or f"sample {sample_id:04d}"),
            "category": str(saved.get("category") or "Unclassified"),
            "family": str(saved.get("family") or ""),
            "playback_mode": str(saved.get("playback_mode") or "Pitched"),
            "root_note": int(saved.get("root_note") if saved.get("root_note") is not None else 60),
            "usability": str(saved.get("usability") or "Unreviewed"),
            "tags": str(saved.get("tags") or ""),
            "classification_notes": str(saved.get("notes") or ""),
            "classified": bool(saved),
        }
        path = Path(str(row.get("output_path") or ""))
        row["playable"] = (
            path.is_file()
            and path.suffix.casefold() == ".wav"
            and not row.get("errors")
        )
        haystack = " ".join(
            (
                key,
                row["classification_label"],
                row["category"],
                row["family"],
                row["playback_mode"],
                row["usability"],
                row["tags"],
                str(row.get("display_name") or ""),
                str(row.get("output_path") or ""),
            )
        ).casefold()
        if needle and needle not in haystack:
            continue
        if category != "All" and row["category"] != category:
            continue
        if usability != "All" and row["usability"] != usability:
            continue
        output.append(row)

    output.sort(
        key=lambda row: (
            0 if row.get("classified") else 1,
            int(row.get("resource_offset") or 0),
            int(row.get("sample_id") or 0),
        )
    )
    return output


def sequencer_sample_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    return [
        row
        for row in classified_sample_rows(project)
        if row.get("playable") and row.get("usability") != "Reject"
    ]


def classification_summary(project: FragmenterProjectV1) -> dict[str, Any]:
    rows = classified_sample_rows(project)
    categories = available_categories(project)
    return {
        "samples": len(rows),
        "playable": sum(bool(row.get("playable")) for row in rows),
        "classified": sum(bool(row.get("classified")) for row in rows),
        "usable": sum(row.get("usability") == "Usable" for row in rows),
        "categories": {
            category: sum(row.get("category") == category for row in rows)
            for category in categories
        },
        "available_categories": list(categories),
        "store_path": str(store_path(project)),
    }


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's Sample Classifier.")

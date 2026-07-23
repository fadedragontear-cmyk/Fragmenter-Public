#!/usr/bin/env python3
"""Unified project-local metadata and canonical exports for playable audio.

SNDDATA samples continue to use the authoritative sample-classification store. Direct
playable WAVs use this companion path-keyed store. The merged inventory is read-only
with respect to game data and deduplicates rows by decoded WAV path.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_sound_v1 import canonical_snddata_path, sound_reports_root
from project_sound_v7 import build_project_sound_library
from project_workspace_v1 import FragmenterProjectV1, sha256_file
from snddata_sample_classification_v1 import classified_sample_rows

STORE_NAME = "audio_library_research_v1.json"
CANONICAL_JSON = "canonical_audio_research_v1.json"
CANONICAL_CSV = "canonical_audio_research_v1.csv"
STORE_VERSION = 1


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def store_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / STORE_NAME


def _empty_store() -> dict[str, Any]:
    return {"version": STORE_VERSION, "updated_at": _utc_iso(), "items": {}}


def load_store(project: FragmenterProjectV1) -> dict[str, Any]:
    path = store_path(project)
    if not path.is_file():
        return _empty_store()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), dict):
        return _empty_store()
    payload["version"] = STORE_VERSION
    payload.setdefault("updated_at", _utc_iso())
    return payload


def _save_store(project: FragmenterProjectV1, payload: dict[str, Any]) -> Path:
    path = store_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["version"] = STORE_VERSION
    payload["updated_at"] = _utc_iso()
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def _path_from_row(row: dict[str, Any]) -> Path | None:
    for key in ("output_path", "path", "decoded_path"):
        text = str(row.get(key) or "").strip()
        if text:
            return Path(text).expanduser()
    wav = row.get("wav")
    if isinstance(wav, dict):
        for key in ("path", "output_path"):
            text = str(wav.get(key) or "").strip()
            if text:
                return Path(text).expanduser()
    return None


def _path_identity(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve()).replace("\\", "/").casefold()
    except OSError:
        return str(path).replace("\\", "/").casefold()


def direct_item_key(row: dict[str, Any]) -> str:
    relative = str(row.get("relative_path") or "").strip().replace("\\", "/")
    if relative:
        return "direct|" + relative.casefold()
    path = _path_from_row(row)
    identity = _path_identity(path)
    if not identity:
        raise ValueError("Playable audio row has no stable path")
    return "direct|" + identity


def direct_record(project: FragmenterProjectV1, row: dict[str, Any]) -> dict[str, Any]:
    try:
        key = direct_item_key(row)
    except ValueError:
        return {}
    value = (load_store(project).get("items") or {}).get(key)
    return dict(value) if isinstance(value, dict) else {}


def save_direct_record(
    project: FragmenterProjectV1,
    row: dict[str, Any],
    *,
    label: str,
    category: str,
    playback_mode: str,
    root_note: int,
    usability: str,
    tags: str,
    notes: str,
) -> dict[str, Any]:
    key = direct_item_key(row)
    payload = load_store(project)
    items = payload.setdefault("items", {})
    current = dict(items.get(key) or {})
    path = _path_from_row(row)
    current.update(
        {
            "key": key,
            "kind": "direct_playable_wav",
            "label": str(label or "").strip() or str(row.get("name") or (path.name if path else "audio")),
            "category": str(category or "Unclassified").strip() or "Unclassified",
            "playback_mode": str(playback_mode or "One-shot"),
            "root_note": max(0, min(127, int(root_note))),
            "usability": str(usability or "Unreviewed"),
            "tags": str(tags or "").strip(),
            "notes": str(notes or ""),
            "relative_path": str(row.get("relative_path") or ""),
            "output_path": str(path or ""),
            "updated_at": _utc_iso(),
        }
    )
    current.setdefault("created_at", current["updated_at"])
    items[key] = current
    _save_store(project, payload)
    return current


def _sample_unified_row(row: dict[str, Any]) -> dict[str, Any]:
    path = _path_from_row(row)
    resource = int(row.get("resource_offset") or row.get("resource_id") or 0)
    sample_id = int(row.get("sample_id") if row.get("sample_id") is not None else row.get("index") or 0)
    return {
        **row,
        "unified_key": f"sample|0x{resource:X}|{sample_id:04d}",
        "item_type": "SNDDATA Sample",
        "is_snddata_sample": True,
        "name": str(row.get("classification_label") or row.get("display_name") or (path.name if path else "sample")),
        "category": str(row.get("category") or "Unclassified"),
        "playback_mode": str(row.get("playback_mode") or "Pitched"),
        "root_note": int(row.get("root_note") if row.get("root_note") is not None else 60),
        "usability": str(row.get("usability") or "Unreviewed"),
        "tags": str(row.get("tags") or ""),
        "notes": str(row.get("classification_notes") or ""),
        "output_path": str(path or ""),
        "playable": bool(path and path.is_file() and path.suffix.casefold() == ".wav" and not row.get("errors")),
    }


def _direct_unified_row(project: FragmenterProjectV1, row: dict[str, Any]) -> dict[str, Any] | None:
    path = _path_from_row(row)
    if path is None or path.suffix.casefold() != ".wav" or not path.is_file() or not row.get("playable"):
        return None
    record = direct_record(project, row)
    wav = row.get("wav") if isinstance(row.get("wav"), dict) else {}
    return {
        **row,
        "unified_key": direct_item_key(row),
        "item_type": "Direct WAV",
        "is_snddata_sample": False,
        "name": str(record.get("label") or row.get("name") or path.name),
        "category": str(record.get("category") or row.get("category") or "Other Playable"),
        "playback_mode": str(record.get("playback_mode") or "One-shot"),
        "root_note": int(record.get("root_note") if record.get("root_note") is not None else 60),
        "usability": str(record.get("usability") or "Unreviewed"),
        "tags": str(record.get("tags") or ""),
        "notes": str(record.get("notes") or ""),
        "sample_rate": int(wav.get("sample_rate") or row.get("sample_rate") or 0),
        "duration_estimate": float(wav.get("duration") or row.get("duration") or row.get("duration_estimate") or 0.0),
        "output_path": str(path),
        "playable": True,
    }


def merged_audio_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for raw in classified_sample_rows(project):
        row = _sample_unified_row(raw)
        identity = _path_identity(_path_from_row(row))
        if identity:
            seen_paths.add(identity)
        rows.append(row)

    library = build_project_sound_library(project, query="", category="All", include_pcm_research=False)
    for raw in library.get("items") or []:
        if not isinstance(raw, dict):
            continue
        row = _direct_unified_row(project, raw)
        if row is None:
            continue
        identity = _path_identity(_path_from_row(row))
        if identity in seen_paths:
            continue
        seen_paths.add(identity)
        rows.append(row)

    rows.sort(
        key=lambda row: (
            str(row.get("category") or "").casefold(),
            str(row.get("name") or "").casefold(),
            str(row.get("output_path") or "").casefold(),
        )
    )
    return rows


def export_canonical_audio_research(project: FragmenterProjectV1) -> dict[str, Any]:
    rows = merged_audio_rows(project)
    snddata = canonical_snddata_path(project)
    source = {
        "path": str(snddata),
        "exists": snddata.is_file(),
        "sha256": sha256_file(snddata) if snddata.is_file() else "",
    }
    canonical_rows = [
        {
            "key": str(row.get("unified_key") or ""),
            "type": str(row.get("item_type") or ""),
            "label": str(row.get("name") or ""),
            "category": str(row.get("category") or ""),
            "playback_mode": str(row.get("playback_mode") or ""),
            "root_note": int(row.get("root_note") or 0),
            "usability": str(row.get("usability") or ""),
            "tags": str(row.get("tags") or ""),
            "notes": str(row.get("notes") or ""),
            "sample_rate": int(row.get("sample_rate") or 0),
            "duration": float(row.get("duration_estimate") or 0.0),
            "resource_offset": row.get("resource_offset"),
            "sample_id": row.get("sample_id"),
            "output_path": str(row.get("output_path") or ""),
        }
        for row in rows
    ]
    payload = {
        "version": 1,
        "created_at": _utc_iso(),
        "project": str(project.project_path),
        "snddata_source": source,
        "summary": {
            "items": len(canonical_rows),
            "snddata_samples": sum(row["type"] == "SNDDATA Sample" for row in canonical_rows),
            "direct_wavs": sum(row["type"] == "Direct WAV" for row in canonical_rows),
            "categorized": sum(row["category"] not in {"", "Unclassified", "Other Playable"} for row in canonical_rows),
            "with_notes": sum(bool(row["notes"].strip()) for row in canonical_rows),
        },
        "items": canonical_rows,
        "scope": "Research metadata only; no game, ISO, SNDDATA, save, or memory-card bytes are modified.",
    }
    reports = sound_reports_root(project)
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / CANONICAL_JSON
    csv_path = reports / CANONICAL_CSV
    temporary = json_path.with_name(json_path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, json_path)
    fieldnames = list(canonical_rows[0]) if canonical_rows else [
        "key", "type", "label", "category", "playback_mode", "root_note", "usability", "tags", "notes", "sample_rate", "duration", "resource_offset", "sample_id", "output_path"
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(canonical_rows)
    return {**payload["summary"], "json_path": str(json_path), "csv_path": str(csv_path)}


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's unified Audio Library / Classifier.")

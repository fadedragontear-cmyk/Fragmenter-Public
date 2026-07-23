#!/usr/bin/env python3
"""Project-local SNDDATA sequence/program mapping decisions.

Mappings are evidence, not patches. They are bound to the exact SNDDATA SHA-256
and allow the Music Mixer to audition unresolved Program candidates, then retain a
manual choice without writing to the game data.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from project_workspace_v1 import FragmenterProjectV1, sha256_file

STORE_VERSION = 1
STORE_FILENAME = "snddata_mappings.json"
MAPPING_STATUSES = {"manual", "confirmed", "structural"}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def mapping_store_path(project: FragmenterProjectV1) -> Path:
    return project.workspace_path("cache_mappings") / STORE_FILENAME


def source_fingerprint(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    stat = source.stat()
    digest = sha256_file(source)
    return {
        "path": str(source),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest,
        "source_id": digest,
    }


def _empty_store() -> dict[str, Any]:
    return {"version": STORE_VERSION, "updated_at": _utc_iso(), "sources": {}}


def load_store(path: str | Path) -> dict[str, Any]:
    store_path = Path(path).expanduser()
    if not store_path.is_file():
        return _empty_store()
    payload = json.loads(store_path.read_text(encoding="utf-8"))
    if int(payload.get("version") or 0) != STORE_VERSION:
        raise ValueError(f"Unsupported SNDDATA mapping store version: {payload.get('version')}")
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("SNDDATA mapping store sources must be an object")
    return payload


def save_store(path: str | Path, store: dict[str, Any]) -> Path:
    store_path = Path(path).expanduser()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store["version"] = STORE_VERSION
    store["updated_at"] = _utc_iso()
    temp = store_path.with_name(store_path.name + ".tmp")
    temp.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, store_path)
    return store_path


def _sequence_key(value: str | int) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("sequence_id must not be empty")
    return text


def _program_key(value: str | int) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("program_resource must not be empty")
    return text


def set_mapping(
    store_path: str | Path,
    snddata_path: str | Path,
    sequence_id: str | int,
    program_resource: str | int,
    *,
    status: str = "manual",
    notes: str = "",
    program_index: int | None = None,
) -> dict[str, Any]:
    if status not in MAPPING_STATUSES:
        raise ValueError(f"Unsupported mapping status: {status}")
    fingerprint = source_fingerprint(snddata_path)
    store = load_store(store_path)
    sources = store.setdefault("sources", {})
    source_entry = sources.setdefault(
        fingerprint["source_id"],
        {
            "source": fingerprint,
            "mappings": {},
            "created_at": _utc_iso(),
        },
    )
    source_entry["source"] = fingerprint
    mappings = source_entry.setdefault("mappings", {})
    sequence_key = _sequence_key(sequence_id)
    existing = mappings.get(sequence_key) if isinstance(mappings.get(sequence_key), dict) else {}
    record = {
        "sequence_id": sequence_key,
        "program_resource": _program_key(program_resource),
        "program_index": program_index,
        "status": status,
        "notes": str(notes or ""),
        "created_at": existing.get("created_at") or _utc_iso(),
        "updated_at": _utc_iso(),
    }
    mappings[sequence_key] = record
    save_store(store_path, store)
    return record


def get_mapping(
    store_path: str | Path,
    snddata_path: str | Path,
    sequence_id: str | int,
) -> dict[str, Any] | None:
    fingerprint = source_fingerprint(snddata_path)
    store = load_store(store_path)
    source_entry = (store.get("sources") or {}).get(fingerprint["source_id"])
    if not isinstance(source_entry, dict):
        return None
    mappings = source_entry.get("mappings")
    if not isinstance(mappings, dict):
        return None
    record = mappings.get(_sequence_key(sequence_id))
    return dict(record) if isinstance(record, dict) else None


def remove_mapping(store_path: str | Path, snddata_path: str | Path, sequence_id: str | int) -> bool:
    fingerprint = source_fingerprint(snddata_path)
    store = load_store(store_path)
    source_entry = (store.get("sources") or {}).get(fingerprint["source_id"])
    if not isinstance(source_entry, dict) or not isinstance(source_entry.get("mappings"), dict):
        return False
    removed = source_entry["mappings"].pop(_sequence_key(sequence_id), None) is not None
    if removed:
        save_store(store_path, store)
    return removed


def list_mappings(store_path: str | Path, snddata_path: str | Path) -> list[dict[str, Any]]:
    fingerprint = source_fingerprint(snddata_path)
    store = load_store(store_path)
    source_entry = (store.get("sources") or {}).get(fingerprint["source_id"])
    if not isinstance(source_entry, dict):
        return []
    mappings = source_entry.get("mappings")
    if not isinstance(mappings, dict):
        return []
    return [dict(mappings[key]) for key in sorted(mappings, key=lambda value: (len(value), value))]


def normalize_program_candidates(candidates: Iterable[str | int]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for candidate in candidates:
        value = str(candidate).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def resolver_view_model(
    sequence_id: str | int,
    candidates: Iterable[str | int],
    *,
    selected_program: str | int | None = None,
    saved_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_program_candidates(candidates)
    selected = str(selected_program).strip() if selected_program is not None else ""
    if selected not in normalized:
        selected = normalized[0] if normalized else ""
    return {
        "sequence_id": _sequence_key(sequence_id),
        "status": "resolved" if saved_mapping else "program unresolved",
        "candidates": normalized,
        "selected_program": selected,
        "saved_mapping": dict(saved_mapping) if saved_mapping else None,
        "can_audition": bool(selected),
        "can_try_next": len(normalized) > 1,
        "can_use_mapping": bool(selected),
    }


def next_candidate(candidates: Iterable[str | int], current: str | int | None) -> str | None:
    normalized = normalize_program_candidates(candidates)
    if not normalized:
        return None
    current_text = str(current).strip() if current is not None else ""
    if current_text not in normalized:
        return normalized[0]
    index = normalized.index(current_text)
    return normalized[(index + 1) % len(normalized)]

#!/usr/bin/env python3
"""Project-local research decisions for SNDDATA sequence candidates.

This store records audition results only. It is bound to the exact SNDDATA SHA-256
and never modifies the source file, ISO, Area Server, saves, or memory card.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_sound_v1 import canonical_snddata_path
from project_workspace_v1 import FragmenterProjectV1
from snddata_mapping_store_v1 import source_fingerprint

STORE_VERSION = 1
STORE_FILENAME = "snddata_research.json"
REVIEW_STATUSES = {"plausible", "confirmed", "rejected"}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def research_store_path(project: FragmenterProjectV1) -> Path:
    return project.workspace_path("cache_mappings") / STORE_FILENAME


def _empty_store() -> dict[str, Any]:
    return {"version": STORE_VERSION, "updated_at": _utc_iso(), "sources": {}}


def load_store(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not target.is_file():
        return _empty_store()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if int(payload.get("version") or 0) != STORE_VERSION:
        raise ValueError(f"Unsupported SNDDATA research store version: {payload.get('version')}")
    if not isinstance(payload.get("sources"), dict):
        raise ValueError("SNDDATA research store sources must be an object")
    return payload


def save_store(path: str | Path, store: dict[str, Any]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    store["version"] = STORE_VERSION
    store["updated_at"] = _utc_iso()
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return target


def _candidate_key(routing_mode: str, program_resource: str | int) -> str:
    mode = str(routing_mode or "").strip()
    resource = str(program_resource or "").strip()
    if not mode or not resource:
        raise ValueError("routing_mode and program_resource are required")
    return f"{mode}|{resource}"


def _source_entry(project: FragmenterProjectV1, store: dict[str, Any], *, create: bool) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    source = canonical_snddata_path(project)
    fingerprint = source_fingerprint(source)
    sources = store.setdefault("sources", {})
    entry = sources.get(fingerprint["source_id"])
    if not isinstance(entry, dict) and create:
        entry = {
            "source": fingerprint,
            "sequences": {},
            "created_at": _utc_iso(),
        }
        sources[fingerprint["source_id"]] = entry
    if isinstance(entry, dict):
        entry["source"] = fingerprint
        entry.setdefault("sequences", {})
    return entry if isinstance(entry, dict) else None, fingerprint


def set_candidate_review(
    project: FragmenterProjectV1,
    sequence_id: str,
    routing_mode: str,
    program_resource: str | int,
    *,
    status: str,
    notes: str = "",
    preview_path: str | Path | None = None,
) -> dict[str, Any]:
    if status not in REVIEW_STATUSES:
        raise ValueError(f"Unsupported research status: {status}")
    sequence_key = str(sequence_id or "").strip()
    if not sequence_key:
        raise ValueError("sequence_id is required")
    resource = str(program_resource or "").strip()
    key = _candidate_key(routing_mode, resource)
    path = research_store_path(project)
    store = load_store(path)
    source_entry, _fingerprint = _source_entry(project, store, create=True)
    assert source_entry is not None
    sequences = source_entry.setdefault("sequences", {})
    sequence = sequences.setdefault(sequence_key, {"candidates": {}, "created_at": _utc_iso()})
    candidates = sequence.setdefault("candidates", {})
    existing = candidates.get(key) if isinstance(candidates.get(key), dict) else {}
    preview = str(Path(preview_path).expanduser()) if preview_path else str(existing.get("preview_path") or "")
    record = {
        "sequence_id": sequence_key,
        "routing_mode": str(routing_mode),
        "program_resource": resource,
        "status": status,
        "notes": str(notes or ""),
        "preview_path": preview,
        "created_at": existing.get("created_at") or _utc_iso(),
        "updated_at": _utc_iso(),
    }
    candidates[key] = record
    sequence["updated_at"] = _utc_iso()
    save_store(path, store)
    return record


def clear_candidate_review(
    project: FragmenterProjectV1,
    sequence_id: str,
    routing_mode: str,
    program_resource: str | int,
) -> bool:
    path = research_store_path(project)
    store = load_store(path)
    source_entry, _fingerprint = _source_entry(project, store, create=False)
    if source_entry is None:
        return False
    sequences = source_entry.get("sequences")
    sequence = sequences.get(str(sequence_id)) if isinstance(sequences, dict) else None
    candidates = sequence.get("candidates") if isinstance(sequence, dict) else None
    if not isinstance(candidates, dict):
        return False
    removed = candidates.pop(_candidate_key(routing_mode, program_resource), None) is not None
    if removed:
        sequence["updated_at"] = _utc_iso()
        save_store(path, store)
    return removed


def list_candidate_reviews(project: FragmenterProjectV1, sequence_id: str | None = None) -> list[dict[str, Any]]:
    path = research_store_path(project)
    store = load_store(path)
    source_entry, _fingerprint = _source_entry(project, store, create=False)
    if source_entry is None:
        return []
    sequences = source_entry.get("sequences")
    if not isinstance(sequences, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key in sorted(sequences, key=lambda value: (len(value), value)):
        if sequence_id is not None and key != str(sequence_id):
            continue
        sequence = sequences.get(key)
        candidates = sequence.get("candidates") if isinstance(sequence, dict) else None
        if not isinstance(candidates, dict):
            continue
        rows.extend(dict(value) for value in candidates.values() if isinstance(value, dict))
    return rows


def review_index(project: FragmenterProjectV1, sequence_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(row.get("routing_mode") or ""), str(row.get("program_resource") or "")): row
        for row in list_candidate_reviews(project, sequence_id)
    }

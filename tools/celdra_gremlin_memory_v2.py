#!/usr/bin/env python3
"""Installation-local memory for Celdra's fictional Gremlin stable.

Only presentation progression is stored. The file never contains project paths,
media identities, browser data, Discord data, extracted content, or game binaries.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from celdra_gremlin_memory_v1 import KNOWN_GREMLINS, memory_path

MEMORY_VERSION = 2
COLLECTION_SCHEMA_V109 = "v109_individual_capture"
LEGACY_COLLECTION_SCHEMA = "legacy_appearance_progress"


def _clean_names(values: Iterable[Any]) -> list[str]:
    supplied = {str(value).upper() for value in values}
    return [name for name in KNOWN_GREMLINS if name in supplied]


def default_memory() -> dict[str, Any]:
    return {
        "version": MEMORY_VERSION,
        "collection_schema": COLLECTION_SCHEMA_V109,
        "seen": [],
        "stable": [],
        "legacy_stable": [],
        "visit_count": 0,
        "history_gag_seen": False,
        "collection_reward_seen": False,
        "breakout_seen": False,
        # Retained for V99/V100 compatibility. In V109 it mirrors a complete stable.
        "resident_console_unlocked": False,
    }


def normalize_memory(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(payload or {})
    seen = _clean_names(source.get("seen") or [])
    stable = _clean_names(source.get("stable") or source.get("caught") or [])
    schema = str(source.get("collection_schema") or LEGACY_COLLECTION_SCHEMA)
    legacy_stable = _clean_names(source.get("legacy_stable") or [])
    if (
        schema != COLLECTION_SCHEMA_V109
        and bool(source.get("resident_console_unlocked"))
    ):
        legacy_stable = _clean_names((*legacy_stable, *seen, *stable))

    stable_set = set(stable)
    seen_set = set(seen) | stable_set
    complete = stable_set == set(KNOWN_GREMLINS)
    return {
        "version": MEMORY_VERSION,
        "collection_schema": schema,
        "seen": [name for name in KNOWN_GREMLINS if name in seen_set],
        "stable": [name for name in KNOWN_GREMLINS if name in stable_set],
        "legacy_stable": legacy_stable,
        "visit_count": max(0, int(source.get("visit_count") or 0)),
        "history_gag_seen": bool(source.get("history_gag_seen")),
        "collection_reward_seen": bool(source.get("collection_reward_seen")) and complete,
        "breakout_seen": bool(source.get("breakout_seen")),
        "resident_console_unlocked": complete,
    }


def load_memory(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else memory_path()
    if not target.is_file():
        return default_memory()
    payload: dict[str, Any] = {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            payload = raw
    except (OSError, json.JSONDecodeError):
        payload = {}
    return normalize_memory(payload)


def save_memory(payload: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else memory_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_memory(payload)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def begin_v109_collection(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Migrate legacy appearance progress into the real individual-capture game.

    Older releases could unlock a resident console after all Gremlins merely appeared.
    That state must not count as nine individual captures. Existing stable names are
    archived as presentation history, then the V109 stable starts empty exactly once.
    """
    state = normalize_memory(payload if payload is not None else load_memory())
    if state.get("collection_schema") == COLLECTION_SCHEMA_V109:
        return state
    archived = set(state.get("legacy_stable") or []) | set(state.get("stable") or [])
    state["collection_schema"] = COLLECTION_SCHEMA_V109
    state["legacy_stable"] = [name for name in KNOWN_GREMLINS if name in archived]
    state["stable"] = []
    state["collection_reward_seen"] = False
    state["resident_console_unlocked"] = False
    state["breakout_seen"] = False
    save_memory(state)
    return normalize_memory(state)


def record_visit(name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state = normalize_memory(payload if payload is not None else load_memory())
    folded = str(name or "").upper()
    if folded in KNOWN_GREMLINS:
        seen = set(state["seen"])
        seen.add(folded)
        state["seen"] = [value for value in KNOWN_GREMLINS if value in seen]
        state["visit_count"] = int(state["visit_count"]) + 1
    save_memory(state)
    return normalize_memory(state)


def capture_in_stable(name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state = normalize_memory(payload if payload is not None else load_memory())
    folded = str(name or "").upper()
    if folded in KNOWN_GREMLINS:
        stable = set(state["stable"])
        seen = set(state["seen"])
        stable.add(folded)
        seen.add(folded)
        state["stable"] = [value for value in KNOWN_GREMLINS if value in stable]
        state["seen"] = [value for value in KNOWN_GREMLINS if value in seen]
    save_memory(state)
    return normalize_memory(state)


def mark_breakout_seen(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state = normalize_memory(payload if payload is not None else load_memory())
    state["breakout_seen"] = True
    save_memory(state)
    return normalize_memory(state)


def mark_collection_reward_seen(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state = normalize_memory(payload if payload is not None else load_memory())
    if set(state["stable"]) == set(KNOWN_GREMLINS):
        state["collection_reward_seen"] = True
    save_memory(state)
    return normalize_memory(state)


def collection_complete(payload: dict[str, Any] | None = None) -> bool:
    state = normalize_memory(payload if payload is not None else load_memory())
    return set(state["stable"]) == set(KNOWN_GREMLINS)

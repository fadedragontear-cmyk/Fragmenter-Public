#!/usr/bin/env python3
"""Small installation-local memory for Celdra's fictional Gremlin visitors.

The store records presentation state only. It never contains project paths, media
identifiers, browser data, Discord data, or file-extraction results.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

MEMORY_VERSION = 1
KNOWN_GREMLINS = ("BYTE", "HEX", "CACHE", "LOOP", "PING", "PATCH", "ROOT", "NULL", "GLITCH")


def installation_state_root() -> Path:
    """Return state owned by this checkout, not by every Fragmenter clone on the PC.

    ``FRAGMENTER_STATE_ROOT`` remains available for packaged builds and tests. A
    source checkout defaults to ``<checkout>/.fragmenter_state`` so a genuinely
    fresh clone starts at 0/9 while repeated launches from the same installation
    retain its fictional collection progress.
    """
    override = str(os.environ.get("FRAGMENTER_STATE_ROOT") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / ".fragmenter_state"


def memory_path() -> Path:
    return installation_state_root() / "celdra_gremlins.json"


def legacy_machine_memory_path() -> Path:
    """Return the pre-V112 machine-global path for diagnostics only.

    It is deliberately not loaded automatically: importing it into every new
    checkout would recreate the false "returning user" behavior V112 removes.
    """
    appdata = os.environ.get("APPDATA")
    root = Path(appdata).expanduser() / "Fragmenter" if appdata else Path.home() / ".config" / "fragmenter"
    return root / "celdra_gremlins.json"


def _clean_seen(values: Iterable[Any]) -> list[str]:
    known = set(KNOWN_GREMLINS)
    supplied = {str(value).upper() for value in values}
    return [name for name in KNOWN_GREMLINS if name in known and name in supplied]


def default_memory() -> dict[str, Any]:
    return {
        "version": MEMORY_VERSION,
        "seen": [],
        "visit_count": 0,
        "resident_console_unlocked": False,
        "history_gag_seen": False,
    }


def load_memory(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else memory_path()
    payload: dict[str, Any] = {}
    if target.is_file():
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
        except (OSError, json.JSONDecodeError):
            payload = {}
    result = default_memory()
    result.update(
        {
            "seen": _clean_seen(payload.get("seen") or []),
            "visit_count": max(0, int(payload.get("visit_count") or 0)),
            "resident_console_unlocked": bool(payload.get("resident_console_unlocked")),
            "history_gag_seen": bool(payload.get("history_gag_seen")),
        }
    )
    return result


def save_memory(payload: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else memory_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = default_memory()
    normalized.update(
        {
            "seen": _clean_seen(payload.get("seen") or []),
            "visit_count": max(0, int(payload.get("visit_count") or 0)),
            "resident_console_unlocked": bool(payload.get("resident_console_unlocked")),
            "history_gag_seen": bool(payload.get("history_gag_seen")),
        }
    )
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def record_visit(name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state = dict(payload or load_memory())
    seen = set(_clean_seen(state.get("seen") or []))
    folded = str(name or "").upper()
    if folded in KNOWN_GREMLINS:
        seen.add(folded)
    state["seen"] = [value for value in KNOWN_GREMLINS if value in seen]
    state["visit_count"] = max(0, int(state.get("visit_count") or 0)) + 1
    save_memory(state)
    return state


def unlock_resident_console(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state = dict(payload or load_memory())
    state["seen"] = list(KNOWN_GREMLINS)
    state["resident_console_unlocked"] = True
    save_memory(state)
    return state

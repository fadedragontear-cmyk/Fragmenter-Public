#!/usr/bin/env python3
"""Small local profile store for Celdra's remembered user name.

The profile is installation-local data, not repository content.  On Windows it
lives below APPDATA/Fragmenter; other platforms use the user's config folder.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

PROFILE_VERSION = 1
MAX_NAME_LENGTH = 32
_ALLOWED = re.compile(r"[^A-Za-z0-9 _.'-]+")


def profile_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        root = Path(appdata).expanduser() / "Fragmenter"
    else:
        root = Path.home() / ".config" / "fragmenter"
    return root / "celdra_profile.json"


def normalize_user_name(value: str, *, fallback: str = "") -> str:
    text = " ".join(str(value or "").strip().split())
    text = _ALLOWED.sub("", text)[:MAX_NAME_LENGTH].strip()
    return text or fallback


def load_profile(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else profile_path()
    if not target.is_file():
        return {"version": PROFILE_VERSION, "name": ""}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": PROFILE_VERSION, "name": ""}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "version": PROFILE_VERSION,
        "name": normalize_user_name(str(payload.get("name") or "")),
    }


def save_profile(name: str, path: str | Path | None = None) -> Path:
    clean_name = normalize_user_name(name, fallback="noname")
    target = Path(path).expanduser() if path is not None else profile_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": PROFILE_VERSION, "name": clean_name}
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def clear_profile(path: str | Path | None = None) -> None:
    target = Path(path).expanduser() if path is not None else profile_path()
    try:
        target.unlink()
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    raise SystemExit("Import this module from Fragmenter's Celdra presentation layer.")

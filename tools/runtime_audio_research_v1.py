#!/usr/bin/env python3
"""Project-local PCSX2/IOP audio observations for SNDDATA research."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_sound_v1 import canonical_snddata_path, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1

REPORT_NAME = "runtime_audio_observations_v1.json"
FUNCTIONS = (
    "sceMidi_Load",
    "sceMidi_SelectMidi",
    "sceMidi_SelectSong",
    "sceMidi_MidiPlaySwitch",
    "sceMidi_SongPlaySwitch",
    "sceMidi_SongSetLocation",
    "sceHSyn_Load",
)


def report_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / REPORT_NAME


def parse_hex(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value & 0xFFFFFFFF
    text = str(value).strip().replace("_", "")
    if not text:
        return None
    if text.casefold().startswith("0x"):
        text = text[2:]
    try:
        return int(text, 16) & 0xFFFFFFFF
    except ValueError:
        return None


def format_hex(value: Any) -> str:
    parsed = parse_hex(value)
    return "" if parsed is None else f"0x{parsed:08X}"


def is_iop_pointer_like(value: Any) -> bool:
    parsed = parse_hex(value)
    return parsed is not None and 0x00001000 <= parsed < 0x00200000


def load_observations(project: FragmenterProjectV1) -> dict[str, Any]:
    path = report_path(project)
    if not path.is_file():
        return {"version": 1, "observations": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "observations": []}
    if not isinstance(payload, dict):
        return {"version": 1, "observations": []}
    rows = payload.get("observations")
    payload["observations"] = rows if isinstance(rows, list) else []
    payload["version"] = 1
    return payload


def _fingerprint(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row.get(key) or "")
        for key in ("cue_name", "function", "function_address", "a0", "a1", "a2", "a3", "ra")
    )


def save_observation(project: FragmenterProjectV1, observation: dict[str, Any]) -> dict[str, Any]:
    payload = load_observations(project)
    row = {
        "cue_name": str(observation.get("cue_name") or "Unnamed cue").strip(),
        "screen": str(observation.get("screen") or "").strip(),
        "trigger": str(observation.get("trigger") or "").strip(),
        "module": str(observation.get("module") or "modmidi").strip(),
        "function": str(observation.get("function") or "").strip(),
        "function_address": format_hex(observation.get("function_address")),
        "a0": format_hex(observation.get("a0")),
        "a1": format_hex(observation.get("a1")),
        "a2": format_hex(observation.get("a2")),
        "a3": format_hex(observation.get("a3")),
        "ra": format_hex(observation.get("ra")),
        "notes": str(observation.get("notes") or "").strip(),
        "captured_at": str(observation.get("captured_at") or datetime.now(timezone.utc).isoformat()),
    }
    row["pointer_like_registers"] = [
        key for key in ("a0", "a1", "a2", "a3", "ra") if is_iop_pointer_like(row.get(key))
    ]
    existing = {_fingerprint(item) for item in payload["observations"] if isinstance(item, dict)}
    if _fingerprint(row) not in existing:
        payload["observations"].append(row)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = report_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return row


def seed_2026_07_21_captures(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    """Record the three clean R3000 captures from the login/menu transition."""
    rows = (
        {
            "cue_name": "Login/menu transition",
            "screen": "ONLINE x OFFLINE title/login path",
            "trigger": "Initial MIDI setup",
            "module": "modmidi",
            "function": "sceMidi_Load",
            "function_address": "000B5AD8",
            "a0": "000D0388",
            "a1": "00000000",
            "a2": "0012B6A0",
            "a3": "054C73D3",
            "notes": "First captured load. Function addresses are session-relative because IOP modules relocate.",
        },
        {
            "cue_name": "Login/menu transition",
            "screen": "ONLINE x OFFLINE title/login path",
            "trigger": "MIDI selection after load",
            "module": "modmidi",
            "function": "sceMidi_SelectMidi",
            "function_address": "000B7480",
            "a0": "000D0388",
            "a1": "00000001",
            "a2": "00000000",
            "a3": "000B8F9F",
            "notes": "Observed MIDI selector 1 using the same context pointer/value in a0.",
        },
        {
            "cue_name": "Login/menu transition",
            "screen": "ONLINE x OFFLINE title/login path",
            "trigger": "Second MIDI load",
            "module": "modmidi",
            "function": "sceMidi_Load",
            "function_address": "000B5AD8",
            "a0": "000D0388",
            "a1": "00000002",
            "a2": "0012CF80",
            "a3": "054CFD3B",
            "notes": "Second captured load. a1 changed from 0 to 2 and a2 changed to another IOP-RAM pointer-like value.",
        },
    )
    return [save_observation(project, row) for row in rows]


def sequence_signature(
    project: FragmenterProjectV1,
    resource_offset: int,
    *,
    length: int = 16,
) -> dict[str, Any]:
    source = canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(f"Canonical SNDDATA source is missing: {source}")
    offset = max(0, int(resource_offset))
    size = max(4, min(64, int(length)))
    data = source.read_bytes()
    block = data[offset : offset + size]
    if len(block) < 4:
        raise ValueError(f"No usable SNDDATA bytes at file offset 0x{offset:X}")
    return {
        "source": str(source),
        "resource_offset": offset,
        "length": len(block),
        "hex_bytes": " ".join(f"{value:02X}" for value in block),
        "ascii": "".join(chr(value) if 32 <= value < 127 else "." for value in block),
        "warning": "File offsets and IOP RAM addresses are different. Search for these bytes; do not equate the numbers.",
    }


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's SNDDATA Research Mixer.")

#!/usr/bin/env python3
"""Portable authoring-project model for Celdra crops, events, branches, and staging."""
from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

AUTHORING_SCHEMA = "fragmenter.celdra.authoring.v1"
EVENT_ACTIONS = (
    "console",
    "chat",
    "status",
    "progress",
    "pose",
    "asset",
    "bubble",
    "move",
    "window",
    "viewport_pulse",
    "viewport_shake",
    "console_whiteout",
    "condition",
    "wait",
    "avatar",
    "avatar_takeover",
    "show_avatar",
    "hide_avatar",
    "show_dialogue",
    "hide_dialogue",
    "name_prompt",
    "result",
    "energy_hatch",
    "egg_glitch",
    "ascii",
    "breakpoint",
)
KNOWN_CONDITIONS = (
    "",
    "is_test",
    "first_scan",
    "run_all_active",
    "run_all_complete",
    "run_all_failed",
    "ccsf_running",
    "ccsf_complete",
    "ccsf_failed",
)
LAYOUT_ACTIONS = {
    "window",
    "viewport_pulse",
    "viewport_shake",
    "pose",
    "avatar",
    "asset",
    "move",
    "avatar_takeover",
    "show_avatar",
    "show_dialogue",
}


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value: Any, default: str = "") -> str:
    result = str(value if value is not None else default).strip()
    return result


def normalize_event(row: dict[str, Any] | None, index: int = 0) -> dict[str, Any]:
    data = dict(row if isinstance(row, dict) else {})
    event_id = _text(data.get("id"), f"event-{index + 1:04d}")
    action = _text(data.get("action"), "console").casefold()
    if action not in EVENT_ACTIONS:
        action = "console"
    explicit_default = action in LAYOUT_ACTIONS
    return {
        "id": event_id,
        "at_ms": max(0, _integer(data.get("at_ms"), 0)),
        "duration_ms": max(0, _integer(data.get("duration_ms"), 0)),
        "sequence": _text(data.get("sequence"), "main") or "main",
        "action": action,
        "speaker": _text(data.get("speaker")),
        "text": str(data.get("text") or ""),
        "asset": _text(data.get("asset")),
        "x": _integer(data.get("x"), 0),
        "y": _integer(data.get("y"), 0),
        "scale": max(10, min(500, _integer(data.get("scale"), 100))),
        "window_percent": max(4, min(99, _integer(data.get("window_percent"), 56))),
        "window_height_percent": max(
            20,
            min(100, _integer(data.get("window_height_percent"), 100)),
        ),
        "window_y_percent": max(0, min(80, _integer(data.get("window_y_percent"), 0))),
        "layout_override": bool(data.get("layout_override", explicit_default)),
        "bubble_style": _text(data.get("bubble_style"), "Rounded blue"),
        "bubble_x": max(0, min(90, _integer(data.get("bubble_x"), 4))),
        "bubble_y": max(0, min(90, _integer(data.get("bubble_y"), 3))),
        "bubble_width": max(15, min(95, _integer(data.get("bubble_width"), 52))),
        "condition": _text(data.get("condition")),
        "true_sequence": _text(data.get("true_sequence")),
        "false_sequence": _text(data.get("false_sequence")),
        "enabled": bool(data.get("enabled", True)),
        "notes": str(data.get("notes") or ""),
    }


def normalize_events(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    events = [normalize_event(row, index) for index, row in enumerate(rows) if isinstance(row, dict)]
    events.sort(key=lambda row: (int(row["at_ms"]), str(row["sequence"]), str(row["id"])))
    return events


def timeline_event_to_row(event: Any, index: int) -> dict[str, Any]:
    action = str(getattr(event, "action", "console") or "console")
    asset = str(getattr(event, "avatar_phase", "") or "")
    if action == "avatar_takeover":
        action = "pose"
        asset = "shy"
    return normalize_event(
        {
            "id": f"canonical-{index + 1:04d}",
            "at_ms": getattr(event, "at_ms", 0),
            "duration_ms": getattr(event, "duration_ms", 0),
            "sequence": "main",
            "action": action,
            "speaker": getattr(event, "speaker", ""),
            "text": getattr(event, "text", ""),
            "asset": asset,
            "window_percent": 56,
            "window_height_percent": 100,
            "window_y_percent": 0,
            "layout_override": action in LAYOUT_ACTIONS,
            "scale": 100,
        },
        index,
    )


def project_payload(
    *,
    events: Iterable[dict[str, Any]],
    preview: dict[str, Any],
    shy_entrance: dict[str, Any],
    manifest: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": AUTHORING_SCHEMA,
        "metadata": dict(metadata or {}),
        "events": normalize_events(events),
        "preview": dict(preview or {}),
        "shy_entrance": dict(shy_entrance or {}),
        "manifest": dict(manifest or {}),
    }


def write_project(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    clean = dict(payload)
    clean["schema"] = AUTHORING_SCHEMA
    clean["events"] = normalize_events(clean.get("events") or [])
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def read_project(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Celdra authoring project must contain a JSON object")
    payload.setdefault("schema", AUTHORING_SCHEMA)
    payload["events"] = normalize_events(payload.get("events") or [])
    payload.setdefault("preview", {})
    payload.setdefault("shy_entrance", {})
    payload.setdefault("manifest", {})
    return payload


def write_bundle(
    path: str | Path,
    *,
    payload: dict[str, Any],
    asset_root: str | Path,
    generated_files: Iterable[str | Path] = (),
) -> Path:
    target = Path(path).expanduser()
    if target.suffix.casefold() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    root = Path(asset_root).expanduser()
    with tempfile.TemporaryDirectory(prefix="fragmenter-celdra-") as directory:
        staging = Path(directory)
        project_path = write_project(staging / "celdra_authoring_project.json", payload)
        manifest_path = root / "manifest.json"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(project_path, "celdra_authoring_project.json")
            if manifest_path.is_file():
                archive.write(manifest_path, "manifest.json")
            for item in generated_files:
                source = Path(item)
                if not source.is_file():
                    continue
                try:
                    relative = source.relative_to(root)
                except ValueError:
                    relative = Path("generated_emotes") / source.name
                archive.write(source, str(relative).replace("\\", "/"))
    return target


if __name__ == "__main__":
    raise SystemExit("Import this module from Fragmenter's Celdra authoring studio.")

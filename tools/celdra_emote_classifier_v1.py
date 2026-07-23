#!/usr/bin/env python3
"""Persistent, non-destructive crop definitions for Celdra emote sheets."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

MANIFEST_VERSION = 1
DEFAULT_STATES = (
    "unclassified",
    "neutral",
    "idle",
    "talk",
    "happy",
    "smirk",
    "thinking",
    "annoyed",
    "surprised",
    "embarrassed",
    "sleepy",
    "error",
)


@dataclass(frozen=True, slots=True)
class EmoteDefinition:
    id: str
    source: str
    state: str
    pose: str
    crop: dict[str, int]
    tags: tuple[str, ...] = ()
    notes: str = ""
    output: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        return payload


def slugify(value: str, fallback: str = "pose") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return text or fallback


def normalize_crop(
    crop: dict[str, Any] | None,
    *,
    source_width: int = 0,
    source_height: int = 0,
) -> dict[str, int]:
    data = crop if isinstance(crop, dict) else {}
    x = max(0, int(data.get("x") or 0))
    y = max(0, int(data.get("y") or 0))
    width = max(1, int(data.get("width") or 1))
    height = max(1, int(data.get("height") or 1))
    if source_width > 0:
        x = min(x, max(0, source_width - 1))
        width = min(width, max(1, source_width - x))
    if source_height > 0:
        y = min(y, max(0, source_height - 1))
        height = min(height, max(1, source_height - y))
    return {"x": x, "y": y, "width": width, "height": height}


def _tags(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = re.split(r"[,;]", value)
    elif isinstance(value, (list, tuple, set)):
        values = [str(item) for item in value]
    else:
        values = []
    cleaned: list[str] = []
    for item in values:
        tag = item.strip()
        if tag and tag.casefold() not in {existing.casefold() for existing in cleaned}:
            cleaned.append(tag)
    return tuple(cleaned)


def make_definition(
    source: str,
    *,
    state: str,
    pose: str,
    crop: dict[str, Any],
    tags: Any = (),
    notes: str = "",
    entry_id: str = "",
    output: str = "",
    enabled: bool = True,
    source_width: int = 0,
    source_height: int = 0,
) -> EmoteDefinition:
    clean_source = str(source or "").replace("\\", "/").lstrip("/")
    clean_state = slugify(state, "unclassified")
    clean_pose = str(pose or clean_state).strip() or clean_state
    clean_crop = normalize_crop(
        crop,
        source_width=source_width,
        source_height=source_height,
    )
    generated_id = entry_id.strip() if entry_id else ""
    if not generated_id:
        stem = slugify(Path(clean_source).stem, "sheet")
        generated_id = (
            f"{stem}-{clean_state}-{slugify(clean_pose)}-"
            f"x{clean_crop['x']}-y{clean_crop['y']}-"
            f"w{clean_crop['width']}-h{clean_crop['height']}"
        )
    clean_output = str(output or "").replace("\\", "/").lstrip("/")
    if not clean_output:
        clean_output = f"generated_emotes/{clean_state}/{slugify(generated_id)}.png"
    return EmoteDefinition(
        id=slugify(generated_id),
        source=clean_source,
        state=clean_state,
        pose=clean_pose,
        crop=clean_crop,
        tags=_tags(tags),
        notes=str(notes or "").strip(),
        output=clean_output,
        enabled=bool(enabled),
    )


def load_manifest(root: str | Path) -> dict[str, Any]:
    path = Path(root).expanduser() / "manifest.json"
    if not path.is_file():
        return {"version": MANIFEST_VERSION, "states": {}, "emotes": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": MANIFEST_VERSION, "states": {}, "emotes": []}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("version", MANIFEST_VERSION)
    payload.setdefault("states", {})
    legacy = payload.get("crops") if isinstance(payload.get("crops"), list) else []
    if not isinstance(payload.get("emotes"), list):
        payload["emotes"] = list(legacy)
    return payload


def definitions_from_manifest(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = payload if isinstance(payload, dict) else {}
    rows = data.get("emotes") if isinstance(data.get("emotes"), list) else []
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        definition = make_definition(
            str(row.get("source") or ""),
            state=str(row.get("state") or "unclassified"),
            pose=str(row.get("pose") or row.get("state") or f"pose {index + 1}"),
            crop=row.get("crop") if isinstance(row.get("crop"), dict) else {},
            tags=row.get("tags") or (),
            notes=str(row.get("notes") or ""),
            entry_id=str(row.get("id") or ""),
            output=str(row.get("output") or ""),
            enabled=bool(row.get("enabled", True)),
        )
        output.append(definition.to_dict())
    output.sort(key=lambda row: (str(row.get("source")), str(row.get("state")), str(row.get("pose"))))
    return output


def write_manifest(root: str | Path, payload: dict[str, Any]) -> Path:
    base = Path(root).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    path = base / "manifest.json"
    clean = dict(payload if isinstance(payload, dict) else {})
    clean["version"] = MANIFEST_VERSION
    clean.setdefault("states", {})
    clean["emotes"] = definitions_from_manifest(clean)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def upsert_definition(root: str | Path, definition: EmoteDefinition | dict[str, Any]) -> Path:
    payload = load_manifest(root)
    row = definition.to_dict() if isinstance(definition, EmoteDefinition) else dict(definition)
    normalized = make_definition(
        str(row.get("source") or ""),
        state=str(row.get("state") or "unclassified"),
        pose=str(row.get("pose") or row.get("state") or "pose"),
        crop=row.get("crop") if isinstance(row.get("crop"), dict) else {},
        tags=row.get("tags") or (),
        notes=str(row.get("notes") or ""),
        entry_id=str(row.get("id") or ""),
        output=str(row.get("output") or ""),
        enabled=bool(row.get("enabled", True)),
    ).to_dict()
    rows = definitions_from_manifest(payload)
    rows = [existing for existing in rows if str(existing.get("id")) != str(normalized.get("id"))]
    rows.append(normalized)
    payload["emotes"] = rows
    return write_manifest(root, payload)


def remove_definition(root: str | Path, entry_id: str) -> Path:
    payload = load_manifest(root)
    payload["emotes"] = [
        row for row in definitions_from_manifest(payload) if str(row.get("id")) != str(entry_id)
    ]
    return write_manifest(root, payload)


def grid_crops(
    width: int,
    height: int,
    *,
    rows: int,
    columns: int,
    padding_x: int = 0,
    padding_y: int = 0,
    gutter_x: int = 0,
    gutter_y: int = 0,
) -> list[dict[str, int]]:
    width = max(1, int(width))
    height = max(1, int(height))
    rows = max(1, int(rows))
    columns = max(1, int(columns))
    padding_x = max(0, int(padding_x))
    padding_y = max(0, int(padding_y))
    gutter_x = max(0, int(gutter_x))
    gutter_y = max(0, int(gutter_y))
    usable_width = width - (padding_x * 2) - (gutter_x * (columns - 1))
    usable_height = height - (padding_y * 2) - (gutter_y * (rows - 1))
    if usable_width < columns or usable_height < rows:
        raise ValueError("Grid padding/gutters leave no usable cell area")
    cell_width = usable_width // columns
    cell_height = usable_height // rows
    crops: list[dict[str, int]] = []
    for row in range(rows):
        for column in range(columns):
            x = padding_x + column * (cell_width + gutter_x)
            y = padding_y + row * (cell_height + gutter_y)
            final_width = cell_width if column < columns - 1 else width - padding_x - x
            final_height = cell_height if row < rows - 1 else height - padding_y - y
            crops.append({"x": x, "y": y, "width": final_width, "height": final_height})
    return crops


def classifier_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    definitions = [row for row in rows if isinstance(row, dict)]
    states: dict[str, int] = {}
    sources: set[str] = set()
    for row in definitions:
        state = str(row.get("state") or "unclassified")
        states[state] = states.get(state, 0) + 1
        sources.add(str(row.get("source") or ""))
    return {
        "definition_count": len(definitions),
        "source_count": len({source for source in sources if source}),
        "states": dict(sorted(states.items())),
    }


if __name__ == "__main__":
    raise SystemExit("Import this module from Fragmenter's Celdra Test tools.")

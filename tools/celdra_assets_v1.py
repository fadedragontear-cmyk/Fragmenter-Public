#!/usr/bin/env python3
"""Discover bundled Celdra images without requiring user-side installation."""
from __future__ import annotations

import json
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".png", ".gif"}
_NUMBERED = re.compile(r"^(.*?)(\d{2,4})$")


@dataclass(frozen=True, slots=True)
class CeldraAsset:
    path: str
    relative_path: str
    suffix: str
    width: int
    height: int
    kind: str
    group: str
    frame_index: int | None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _png_dimensions(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return 0, 0
    if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR":
        return struct.unpack(">II", header[16:24])
    return 0, 0


def _gif_dimensions(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as handle:
            header = handle.read(10)
    except OSError:
        return 0, 0
    if len(header) >= 10 and header[:6] in {b"GIF87a", b"GIF89a"}:
        return struct.unpack("<HH", header[6:10])
    return 0, 0


def image_dimensions(path: Path) -> tuple[int, int]:
    suffix = path.suffix.casefold()
    if suffix == ".png":
        return _png_dimensions(path)
    if suffix == ".gif":
        return _gif_dimensions(path)
    return 0, 0


def _classify(path: Path, width: int, height: int) -> tuple[str, str, int | None, str]:
    folded = path.as_posix().casefold()
    match = _NUMBERED.match(path.stem)
    frame_index = int(match.group(2)) if match else None
    group_stem = (match.group(1).rstrip("_-. ") if match else path.stem) or path.parent.name
    group = f"{path.parent.as_posix()}::{group_stem}".casefold()

    if path.suffix.casefold() == ".gif":
        return "animated_gif", group, None, "GIF animation; frame timing is read at runtime when supported."
    if any(term in folded for term in ("emote", "expression", "dragongirl", "sheet")):
        note = "Likely emote/sprite sheet; use the Celdra Test crop controls before assigning reactions."
        return "sprite_sheet", group, frame_index, note
    if frame_index is not None:
        return "sequence_frame", group, frame_index, "Numbered PNG sequence frame."
    if width >= 384 or height >= 384 or (width and height and width / max(1, height) >= 1.8):
        return "sprite_sheet", group, None, "Large image; inspect/crop in the Celdra Test tab."
    return "image", group, None, "Standalone image."


def discover_celdra_assets(root: str | Path) -> list[dict[str, Any]]:
    base = Path(root).expanduser()
    if not base.is_dir():
        return []
    rows: list[CeldraAsset] = []
    for path in sorted(
        (item for item in base.rglob("*") if item.is_file() and item.suffix.casefold() in IMAGE_SUFFIXES),
        key=lambda item: item.as_posix().casefold(),
    ):
        width, height = image_dimensions(path)
        kind, group, frame_index, notes = _classify(path, width, height)
        rows.append(
            CeldraAsset(
                path=str(path),
                relative_path=path.relative_to(base).as_posix(),
                suffix=path.suffix.casefold(),
                width=width,
                height=height,
                kind=kind,
                group=group,
                frame_index=frame_index,
                notes=notes,
            )
        )
    return [row.to_dict() for row in rows]


def grouped_sequences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("kind") != "sequence_frame":
            continue
        groups.setdefault(str(row.get("group") or ""), []).append(row)
    output: list[dict[str, Any]] = []
    for key, members in groups.items():
        ordered = sorted(
            members,
            key=lambda row: (
                int(row.get("frame_index") if row.get("frame_index") is not None else 10**9),
                str(row.get("relative_path") or "").casefold(),
            ),
        )
        output.append(
            {
                "group": key,
                "frame_count": len(ordered),
                "frames": ordered,
                "width": max((int(row.get("width") or 0) for row in ordered), default=0),
                "height": max((int(row.get("height") or 0) for row in ordered), default=0),
            }
        )
    output.sort(key=lambda group: (-int(group["frame_count"]), str(group["group"])))
    return output


def load_manifest(root: str | Path) -> dict[str, Any]:
    path = Path(root).expanduser() / "manifest.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def asset_inventory(root: str | Path) -> dict[str, Any]:
    rows = discover_celdra_assets(root)
    sequences = grouped_sequences(rows)
    kinds: dict[str, int] = {}
    for row in rows:
        kind = str(row.get("kind") or "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "root": str(Path(root).expanduser()),
        "asset_count": len(rows),
        "kinds": kinds,
        "sequence_groups": sequences,
        "sprite_sheets": [row for row in rows if row.get("kind") == "sprite_sheet"],
        "animated_gifs": [row for row in rows if row.get("kind") == "animated_gif"],
        "manifest": load_manifest(root),
        "assets": rows,
    }


def crop_manifest_entry(
    relative_path: str,
    *,
    state: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    return {
        "state": str(state or "reaction").strip() or "reaction",
        "source": str(relative_path),
        "crop": {
            "x": max(0, int(x)),
            "y": max(0, int(y)),
            "width": max(1, int(width)),
            "height": max(1, int(height)),
        },
    }


if __name__ == "__main__":
    raise SystemExit("Import this module from Fragmenter's Celdra presentation layer.")

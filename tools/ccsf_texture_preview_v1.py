#!/usr/bin/env python3
"""Decode one selected CCSF TEX record into a lightweight 2D PNG preview."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v7 as pose_v7
import ccsf_structure_decoder as structure
import ccsf_texture_decoder_v2 as texture_v2
import ccsf_texture_decoder_v3 as texture_v3


def _matching_record(parsed: Any, section_type: int, object_id: int) -> dict[str, Any] | None:
    for record in parsed.report.records:
        if int(record.get("masked_section_type") or 0) != int(section_type):
            continue
        if int(record.get("object_id") or 0) == int(object_id):
            return record
    return None


def export_texture_preview(
    source: str | Path,
    object_id: int,
    output_path: str | Path,
) -> dict[str, Any]:
    parsed = pose_v7.load_pose_source(source)
    texture_record = _matching_record(parsed, structure.SECTION_TEXTURE, int(object_id))
    if texture_record is None:
        raise ValueError(f"texture object 0x{int(object_id):X} was not found")

    generation = str(parsed.report.header.get("generation") or "Unknown")
    texture = texture_v2.parse_texture_record(parsed.data, texture_record, generation)
    if texture.get("status") != "pixel_data_decoded":
        warnings = "; ".join(str(value) for value in texture.get("warnings") or [])
        detail = warnings or str(texture.get("status") or "texture pixels unavailable")
        raise ValueError(f"texture 0x{int(object_id):X} cannot be previewed: {detail}")

    clut = None
    clut_id = texture.get("clut_id")
    if isinstance(clut_id, int):
        clut_record = _matching_record(parsed, structure.SECTION_CLUT, clut_id)
        if clut_record is not None:
            clut = texture_v2.parse_clut_record(parsed.data, clut_record)

    rgba = texture_v3.decode_rgba(texture, clut)
    width = int(texture["width"])
    height = int(texture["height"])
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    texture_v2.write_rgba_png(output, width, height, rgba)
    alpha = rgba[3::4]
    return {
        "source": str(Path(source)),
        "output_path": str(output),
        "object_id": int(object_id),
        "object_name": str(texture.get("object_name") or ""),
        "width": width,
        "height": height,
        "texture_type": str(
            texture.get("texture_type_name") or texture.get("texture_type") or ""
        ),
        "clut_id": clut_id,
        "alpha_min": min(alpha) if alpha else 0,
        "alpha_max": max(alpha) if alpha else 0,
        "display_transform": dict(texture.get("display_transform") or {}),
        "warnings": list(texture.get("warnings") or []),
    }

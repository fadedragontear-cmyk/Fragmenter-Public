#!/usr/bin/env python3
"""Hardened CCSF textured preview with zero-safe MAT/TEX resolution."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ccsf_structure_decoder
from ccsf_texture_decoder_v1 import (
    _json_safe_clut,
    _json_safe_texture,
    decode_rgba,
    parse_clut_record,
    parse_texture_record,
    write_rgba_png,
)
from ccsf_textured_preview_v1 import DEFAULT_HEIGHT, DEFAULT_WIDTH, _render, _safe_name


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def resolve_submodel_texture_id(report, mat_tex_id: Any) -> tuple[int | None, str]:
    """Resolve a Gen1 submodel reference as MAT→TEX or direct TEX.

    Object ID zero is valid and must not be collapsed into a missing sentinel.
    """
    object_id = _optional_int(mat_tex_id)
    if object_id is None or object_id < 0:
        return None, "missing mat/tex reference"
    entry = report.object_lookup.get(object_id)
    if not isinstance(entry, dict):
        return None, f"object {object_id} missing from index"
    section_type = _optional_int(entry.get("section_type"))
    if section_type == ccsf_structure_decoder.SECTION_TEXTURE:
        return object_id, "direct TEX reference"
    material = entry.get("material") if isinstance(entry.get("material"), dict) else None
    if material is not None:
        texture_id = _optional_int(material.get("texture_object_id"))
        if texture_id is not None and texture_id >= 0:
            return texture_id, "MAT → TEX reference"
    return None, f"object {object_id} is neither decoded MAT nor TEX"


def build_textured_preview(
    asset_path: str | Path,
    output_dir: str | Path,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    yaw: float = -0.55,
    pitch: float = 0.35,
) -> dict[str, Any]:
    source = Path(asset_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    output_root = Path(output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    report = ccsf_structure_decoder.decode(source)
    generation = str(report.header.get("generation") or "Unknown")

    cluts: dict[int, dict[str, Any]] = {}
    clut_rows: list[dict[str, Any]] = []
    for record in report.records:
        if _optional_int(record.get("masked_section_type")) != ccsf_structure_decoder.SECTION_CLUT:
            continue
        try:
            parsed = parse_clut_record(data, record)
            cluts[int(parsed["object_id"])] = parsed
            clut_rows.append(_json_safe_clut(parsed))
        except Exception as exc:
            clut_rows.append({"object_id": record.get("object_id"), "object_name": record.get("object_name"), "status": "error", "error": str(exc)})

    textures: dict[int, dict[str, Any]] = {}
    texture_rows: list[dict[str, Any]] = []
    for record in report.records:
        if _optional_int(record.get("masked_section_type")) != ccsf_structure_decoder.SECTION_TEXTURE:
            continue
        try:
            parsed = parse_texture_record(data, record, generation)
            row = _json_safe_texture(parsed)
            clut_id = _optional_int(parsed.get("clut_id"))
            clut = cluts.get(clut_id) if clut_id is not None else None
            row["clut_name"] = clut.get("object_name") if clut else None
            if parsed.get("status") == "pixel_data_decoded":
                rgba = decode_rgba(parsed, clut)
                parsed["rgba"] = rgba
                name = _safe_name(str(parsed.get("object_name") or f"texture_{parsed.get('object_id')}"))
                png = write_rgba_png(output_root / "textures" / f"{name}.png", int(parsed["width"]), int(parsed["height"]), rgba)
                row.update({"status": "png_exported", "png_path": str(png), "rgba_bytes": len(rgba)})
                textures[int(parsed["object_id"])] = parsed
            texture_rows.append(row)
        except Exception as exc:
            texture_rows.append({"object_id": record.get("object_id"), "object_name": record.get("object_name"), "status": "error", "error": str(exc)})

    triangles: list[dict[str, Any]] = []
    mapped_faces = 0
    unmapped_faces = 0
    material_links: list[dict[str, Any]] = []
    for record in report.records:
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if not model:
            continue
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions: list[tuple[float, float, float]] = []
            for raw in submodel.get("vertices") or []:
                value = raw.get("position") if isinstance(raw, dict) else raw
                if isinstance(value, (list, tuple)) and len(value) >= 3:
                    positions.append((float(value[0]), float(value[1]), float(value[2])))
            uvs: list[tuple[float, float]] = []
            for raw in submodel.get("uvs") or []:
                value = raw.get("uv") if isinstance(raw, dict) else raw
                if isinstance(value, (list, tuple)) and len(value) >= 2:
                    uvs.append((float(value[0]), float(value[1])))

            material_id = _optional_int(submodel.get("mat_tex_id"))
            texture_id, resolution = resolve_submodel_texture_id(report, material_id)
            material = report.object_lookup.get(material_id) if material_id is not None else None
            texture = textures.get(texture_id) if texture_id is not None else None
            link = {
                "model": record.get("object_name") or record.get("object_id"),
                "submodel": submodel.get("index"),
                "material_or_texture_id": material_id,
                "material_or_texture_name": material.get("name") if isinstance(material, dict) else None,
                "texture_id": texture_id,
                "texture_name": texture.get("object_name") if texture else None,
                "resolution": resolution,
                "uv_count": len(uvs),
                "vertex_count": len(positions),
                "face_count": len(submodel.get("faces") or []),
                "mapped": bool(texture is not None and len(uvs) == len(positions)),
            }
            material_links.append(link)
            for face in submodel.get("faces") or []:
                if not isinstance(face, (list, tuple)) or len(face) < 3:
                    continue
                indices = (int(face[0]), int(face[1]), int(face[2]))
                if not all(0 <= index < len(positions) for index in indices):
                    continue
                face_uvs = tuple(uvs[index] for index in indices) if texture is not None and len(uvs) == len(positions) else None
                if face_uvs is None:
                    unmapped_faces += 1
                else:
                    mapped_faces += 1
                triangles.append(
                    {
                        "positions": tuple(positions[index] for index in indices),
                        "uvs": face_uvs,
                        "texture": texture,
                        "model": link["model"],
                        "submodel": link["submodel"],
                    }
                )

    snapshot = None
    display_path = None
    status = "no_renderable_geometry"
    if triangles:
        snapshot = _render(triangles, output_root / "textured_snapshot.png", width=width, height=height, yaw=yaw, pitch=pitch)
        display_path = snapshot["snapshot_path"]
        status = "textured_snapshot_rendered" if mapped_faces else "untextured_snapshot_rendered"
    exported = [row["png_path"] for row in texture_rows if row.get("png_path")]
    if display_path is None and exported:
        display_path = exported[0]
        status = "textures_extracted_no_renderable_model"

    result = {
        "version": 2,
        "source": str(source),
        "generation": generation,
        "status": status,
        "display_path": display_path,
        "textures": texture_rows,
        "cluts": clut_rows,
        "material_links": material_links,
        "summary": {
            "texture_records": len(texture_rows),
            "clut_records": len(clut_rows),
            "png_exported": len(exported),
            "triangles": len(triangles),
            "mapped_faces": mapped_faces,
            "unmapped_faces": unmapped_faces,
            "material_links": len(material_links),
            "resolved_material_links": sum(1 for row in material_links if row.get("texture_id") is not None),
        },
        "snapshot": snapshot,
        "errors": list(report.errors),
        "warnings": list(report.warnings),
        "writes_game_data": False,
    }
    report_path = output_root / "textured_preview_report.json"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["report_path"] = str(report_path)
    return result

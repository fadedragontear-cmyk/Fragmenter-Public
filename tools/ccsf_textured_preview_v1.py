#!/usr/bin/env python3
"""Render a conservative textured snapshot from decoded Gen1 CCSF geometry.

The existing Tk wireframe remains the interactive view.  This module performs the
missing vertical slice for one selected asset:

    MDL submodel -> MAT object -> TEX object -> CLUT -> UV sampled PNG

It never modifies game data. Unsupported texture formats and unresolved material
links remain visible in the returned report instead of receiving fake colors.
"""
from __future__ import annotations

import json
import math
import re
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

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
MAX_TEXTURED_FACES = 6000


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return cleaned or "texture"


def _project(position: tuple[float, float, float], yaw: float, pitch: float) -> tuple[float, float, float]:
    x, y, z = position
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    rx = cy * x + sy * z
    rz = -sy * x + cy * z
    ry = cp * y - sp * rz
    depth = sp * y + cp * rz
    return rx, ry, depth


def _edge(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    return (px - ax) * (by - ay) - (py - ay) * (bx - ax)


def _sample(texture: dict[str, Any], u: float, v: float) -> tuple[int, int, int, int]:
    width = int(texture["width"])
    height = int(texture["height"])
    rgba = texture["rgba"]
    u = u % 1.0
    v = v % 1.0
    x = min(width - 1, max(0, int(u * width)))
    y = min(height - 1, max(0, int((1.0 - v) * height)))
    offset = (y * width + x) * 4
    return tuple(rgba[offset : offset + 4])  # type: ignore[return-value]


def _blend(dst: bytearray, offset: int, color: tuple[int, int, int, int]) -> None:
    r, g, b, a = color
    if a >= 255:
        dst[offset : offset + 4] = bytes((r, g, b, 255))
        return
    if a <= 0:
        return
    inv = 255 - a
    dst[offset] = (r * a + dst[offset] * inv) // 255
    dst[offset + 1] = (g * a + dst[offset + 1] * inv) // 255
    dst[offset + 2] = (b * a + dst[offset + 2] * inv) // 255
    dst[offset + 3] = 255


def _render(
    triangles: list[dict[str, Any]],
    output_path: Path,
    *,
    width: int,
    height: int,
    yaw: float,
    pitch: float,
) -> dict[str, Any]:
    projected_positions = [_project(position, yaw, pitch) for tri in triangles for position in tri["positions"]]
    if not projected_positions:
        raise ValueError("no triangles available for textured rendering")
    min_x = min(value[0] for value in projected_positions)
    max_x = max(value[0] for value in projected_positions)
    min_y = min(value[1] for value in projected_positions)
    max_y = max(value[1] for value in projected_positions)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    scale = min((width - 40) / span_x, (height - 40) / span_y)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    background = (12, 20, 28, 255)
    pixels = bytearray(background * (width * height))
    z_buffer = [float("inf")] * (width * height)
    rasterized = 0
    textured = 0
    untextured = 0

    for tri in triangles[:MAX_TEXTURED_FACES]:
        projected = [_project(position, yaw, pitch) for position in tri["positions"]]
        screen = [
            ((x - center_x) * scale + width / 2.0, height / 2.0 - (y - center_y) * scale, depth)
            for x, y, depth in projected
        ]
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = screen
        area = _edge(x0, y0, x1, y1, x2, y2)
        if abs(area) < 1e-9:
            continue
        min_px = max(0, int(math.floor(min(x0, x1, x2))))
        max_px = min(width - 1, int(math.ceil(max(x0, x1, x2))))
        min_py = max(0, int(math.floor(min(y0, y1, y2))))
        max_py = min(height - 1, int(math.ceil(max(y0, y1, y2))))
        texture = tri.get("texture")
        uvs = tri.get("uvs")
        default_color = tri.get("default_color") or (88, 112, 132, 255)
        for py in range(min_py, max_py + 1):
            sample_y = py + 0.5
            for px in range(min_px, max_px + 1):
                sample_x = px + 0.5
                w0 = _edge(x1, y1, x2, y2, sample_x, sample_y) / area
                w1 = _edge(x2, y2, x0, y0, sample_x, sample_y) / area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-6 or w1 < -1e-6 or w2 < -1e-6:
                    continue
                depth = w0 * z0 + w1 * z1 + w2 * z2
                index = py * width + px
                if depth >= z_buffer[index]:
                    continue
                z_buffer[index] = depth
                if texture is not None and uvs is not None:
                    u = w0 * uvs[0][0] + w1 * uvs[1][0] + w2 * uvs[2][0]
                    v = w0 * uvs[0][1] + w1 * uvs[1][1] + w2 * uvs[2][1]
                    color = _sample(texture, u, v)
                    textured += 1
                else:
                    color = default_color
                    untextured += 1
                _blend(pixels, index * 4, color)
                rasterized += 1

    write_rgba_png(output_path, width, height, bytes(pixels))
    return {
        "snapshot_path": str(output_path),
        "width": width,
        "height": height,
        "triangles_submitted": min(len(triangles), MAX_TEXTURED_FACES),
        "triangles_total": len(triangles),
        "pixels_rasterized": rasterized,
        "textured_pixel_writes": textured,
        "untextured_pixel_writes": untextured,
        "face_cap_applied": len(triangles) > MAX_TEXTURED_FACES,
    }


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
        if int(record.get("masked_section_type") or 0) != ccsf_structure_decoder.SECTION_CLUT:
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
        if int(record.get("masked_section_type") or 0) != ccsf_structure_decoder.SECTION_TEXTURE:
            continue
        try:
            parsed = parse_texture_record(data, record, generation)
            row = _json_safe_texture(parsed)
            clut = cluts.get(int(parsed.get("clut_id") or -1))
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
            positions = []
            for raw in submodel.get("vertices") or []:
                value = raw.get("position") if isinstance(raw, dict) else raw
                if isinstance(value, (list, tuple)) and len(value) >= 3:
                    positions.append((float(value[0]), float(value[1]), float(value[2])))
            uvs = []
            for raw in submodel.get("uvs") or []:
                value = raw.get("uv") if isinstance(raw, dict) else raw
                if isinstance(value, (list, tuple)) and len(value) >= 2:
                    uvs.append((float(value[0]), float(value[1])))
            material_id = int(submodel.get("mat_tex_id") or -1)
            material = report.object_lookup.get(material_id) if material_id >= 0 else None
            texture_id = None
            if isinstance(material, dict) and isinstance(material.get("material"), dict):
                raw_texture_id = material["material"].get("texture_object_id")
                texture_id = int(raw_texture_id) if isinstance(raw_texture_id, int) else None
            texture = textures.get(texture_id) if texture_id is not None else None
            link = {
                "model": record.get("object_name") or record.get("object_id"),
                "submodel": submodel.get("index"),
                "material_id": material_id,
                "material_name": material.get("name") if isinstance(material, dict) else None,
                "texture_id": texture_id,
                "texture_name": texture.get("object_name") if texture else None,
                "uv_count": len(uvs),
                "face_count": len(submodel.get("faces") or []),
                "mapped": bool(texture and len(uvs) == len(positions)),
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
        "version": 1,
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

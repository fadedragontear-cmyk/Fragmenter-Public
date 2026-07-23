#!/usr/bin/env python3
"""Cached, posed and textured Gen1 CCSF software preview scene."""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as base
from ccsf_gen1_pose_v1 import Gen1PoseContext, build_pose_context, pose_summary, transformed_submodel_positions
from ccsf_texture_decoder_v1 import decode_rgba, parse_clut_record, parse_texture_record, write_rgba_png

DEFAULT_WIDTH = 760
DEFAULT_HEIGHT = 560
MAX_RENDER_FACES = 20_000
_SCENE_CACHE: dict[tuple[str, int, int, str, int], "TexturedScene"] = {}


@dataclass
class TexturedScene:
    source: Path
    context: Gen1PoseContext
    triangles: list[dict[str, Any]]
    textures: dict[int, dict[str, Any]]
    texture_rows: list[dict[str, Any]]
    materials: dict[int, dict[str, Any]]
    material_rows: list[dict[str, Any]]
    unresolved: dict[str, int]
    summary: dict[str, Any]


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _parse_materials(context: Gen1PoseContext) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    data = context.data
    materials: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for record in context.report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_MATERIAL:
            continue
        start = int(record.get("payload_start") or 0)
        end = int(record.get("payload_end") or 0)
        row: dict[str, Any] = {"object_id": record.get("object_id"), "object_name": record.get("object_name"), "payload_size": max(0, end - start)}
        try:
            if start < 0 or start + 12 > end or end > len(data):
                raise ValueError("Gen1 Material payload is shorter than 12 bytes")
            texture_id = struct.unpack_from("<i", data, start)[0]
            alpha = struct.unpack_from("<f", data, start + 4)[0]
            raw_u, raw_v = struct.unpack_from("<hh", data, start + 8)
            row.update({"texture_id": texture_id, "alpha": alpha, "texture_offset": [raw_u / 256.0, raw_v / 256.0], "texture_offset_raw": [raw_u, raw_v], "status": "parsed_gen1_material"})
            materials[int(record.get("object_id") or 0)] = row
        except Exception as exc:
            row.update({"status": "error", "error": str(exc)})
        rows.append(row)
    return materials, rows


def _parse_textures(context: Gen1PoseContext) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    data = context.data
    report = context.report
    generation = str(report.header.get("generation") or "Unknown")
    cluts: dict[int, dict[str, Any]] = {}
    for record in report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_CLUT:
            continue
        try:
            parsed = parse_clut_record(data, record)
            cluts[int(parsed["object_id"])] = parsed
        except Exception:
            continue

    textures: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for record in report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_TEXTURE:
            continue
        row: dict[str, Any] = {"object_id": record.get("object_id"), "object_name": record.get("object_name")}
        try:
            parsed = parse_texture_record(data, record, generation)
            row.update({"texture_type": parsed.get("texture_type"), "format_name": parsed.get("format_name"), "width": parsed.get("width"), "height": parsed.get("height"), "clut_id": parsed.get("clut_id"), "decode_status": parsed.get("status")})
            if parsed.get("status") != "pixel_data_decoded":
                row["status"] = "unsupported_or_metadata_only"
            else:
                clut_id = _optional_int(parsed.get("clut_id"))
                clut = cluts.get(clut_id) if clut_id is not None else None
                rgba = decode_rgba(parsed, clut)
                parsed["rgba"] = rgba
                parsed["clut_resolved"] = clut is not None
                textures[int(parsed["object_id"])] = parsed
                row.update({"status": "decoded_rgba", "rgba_bytes": len(rgba), "clut_resolved": clut is not None})
        except Exception as exc:
            row.update({"status": "error", "error": str(exc)})
        rows.append(row)
    return textures, rows


def _resolve_texture(context: Gen1PoseContext, materials: dict[int, dict[str, Any]], textures: dict[int, dict[str, Any]], mat_tex_id: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    object_id = _optional_int(mat_tex_id)
    if object_id is None or object_id < 0:
        return None, None, "missing material/texture reference"
    entry = context.report.object_lookup.get(object_id)
    if not isinstance(entry, dict):
        return None, None, f"object {object_id} missing from object index"
    section_type = _optional_int(entry.get("section_type"))
    if section_type == base.SECTION_TEXTURE:
        texture = textures.get(object_id)
        return texture, None, "direct TEX reference" if texture else "direct TEX is not decoded"
    material = materials.get(object_id)
    if material is not None:
        texture_id = _optional_int(material.get("texture_id"))
        texture = textures.get(texture_id) if texture_id is not None else None
        return texture, material, "MAT -> TEX reference" if texture else "MAT references undecoded TEX"
    return None, None, f"object {object_id} is not a decoded MAT or TEX"


def _scene_cache_key(source: Path, animation_name: str | None, frame: int) -> tuple[str, int, int, str, int]:
    stat = source.stat()
    return (str(source.resolve()), stat.st_size, stat.st_mtime_ns, str(animation_name or ""), int(frame))


def clear_scene_cache(source: str | Path | None = None) -> None:
    if source is None:
        _SCENE_CACHE.clear()
        return
    resolved = str(Path(source).expanduser().resolve())
    for key in [key for key in _SCENE_CACHE if key[0] == resolved]:
        _SCENE_CACHE.pop(key, None)


def load_textured_scene(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> TexturedScene:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    key = _scene_cache_key(source, animation_name, frame)
    cached = _SCENE_CACHE.get(key)
    if cached is not None:
        return cached

    context = build_pose_context(source, animation_name=animation_name, frame=frame)
    materials, material_rows = _parse_materials(context)
    textures, texture_rows = _parse_textures(context)
    triangles: list[dict[str, Any]] = []
    unresolved: dict[str, int] = {}

    for record in context.report.records:
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if not model:
            continue
        model_id = int(record.get("object_id") or 0)
        model_name = str(record.get("object_name") or model_id)
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = transformed_submodel_positions(context, model_id=model_id, submodel=submodel)
            uvs = []
            for raw in submodel.get("uvs") or []:
                value = raw.get("uv") if isinstance(raw, dict) else raw
                if isinstance(value, (list, tuple)) and len(value) >= 2:
                    uvs.append((float(value[0]), float(value[1])))
            texture, material, resolution = _resolve_texture(context, materials, textures, submodel.get("mat_tex_id"))
            offset = list((material or {}).get("texture_offset") or [0.0, 0.0])
            alpha = float((material or {}).get("alpha") if material is not None else 1.0)
            if texture is None:
                unresolved[resolution] = unresolved.get(resolution, 0) + len(submodel.get("faces") or [])
            elif len(uvs) != len(positions):
                reason = f"UV/vertex count mismatch ({len(uvs)}/{len(positions)})"
                unresolved[reason] = unresolved.get(reason, 0) + len(submodel.get("faces") or [])

            for face in submodel.get("faces") or []:
                if not isinstance(face, (list, tuple)) or len(face) < 3:
                    continue
                indices = (int(face[0]), int(face[1]), int(face[2]))
                if not all(0 <= index < len(positions) for index in indices):
                    unresolved["face index outside decoded positions"] = unresolved.get("face index outside decoded positions", 0) + 1
                    continue
                face_uvs = None
                if texture is not None and len(uvs) == len(positions):
                    face_uvs = tuple((uvs[index][0] + float(offset[0]), uvs[index][1] + float(offset[1])) for index in indices)
                triangles.append({"positions": tuple(positions[index] for index in indices), "uvs": face_uvs, "texture": texture, "material_alpha": alpha, "model": model_name, "submodel": submodel.get("index"), "resolution": resolution})

    summary = {
        **pose_summary(context),
        "texture_records": len(texture_rows),
        "decoded_textures": len(textures),
        "material_records": len(material_rows),
        "parsed_materials": len(materials),
        "triangles": len(triangles),
        "textured_triangles": sum(1 for row in triangles if row.get("texture") is not None and row.get("uvs") is not None),
        "unresolved_triangles": sum(1 for row in triangles if row.get("texture") is None or row.get("uvs") is None),
        "unresolved_reasons": dict(sorted(unresolved.items())),
        "cache_key": list(key),
    }
    scene = TexturedScene(source=source, context=context, triangles=triangles, textures=textures, texture_rows=texture_rows, materials=materials, material_rows=material_rows, unresolved=unresolved, summary=summary)
    _SCENE_CACHE[key] = scene
    return scene


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
    x = min(width - 1, max(0, int((u % 1.0) * width)))
    y = min(height - 1, max(0, int((1.0 - (v % 1.0)) * height)))
    offset = (y * width + x) * 4
    return tuple(int(value) for value in rgba[offset : offset + 4])  # type: ignore[return-value]


def _blend(pixels: bytearray, offset: int, color: tuple[int, int, int, int]) -> None:
    r, g, b, a = color
    if a <= 0:
        return
    if a >= 255:
        pixels[offset : offset + 4] = bytes((r, g, b, 255))
        return
    inverse = 255 - a
    pixels[offset] = (r * a + pixels[offset] * inverse) // 255
    pixels[offset + 1] = (g * a + pixels[offset + 1] * inverse) // 255
    pixels[offset + 2] = (b * a + pixels[offset + 2] * inverse) // 255
    pixels[offset + 3] = 255


def _line(pixels: bytearray, width: int, height: int, left: tuple[float, float], right: tuple[float, float], color: tuple[int, int, int, int]) -> None:
    x0, y0 = int(round(left[0])), int(round(left[1]))
    x1, y1 = int(round(right[0])), int(round(right[1]))
    dx, sx = abs(x1 - x0), 1 if x0 < x1 else -1
    dy, sy = -abs(y1 - y0), 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        if 0 <= x0 < width and 0 <= y0 < height:
            _blend(pixels, (y0 * width + x0) * 4, color)
        if x0 == x1 and y0 == y1:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def render_textured_scene(scene: TexturedScene, output_path: str | Path, *, yaw: float = -0.55, pitch: float = 0.35, zoom: float = 1.0, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> dict[str, Any]:
    if not scene.triangles:
        raise ValueError("scene contains no renderable triangles")
    projected_all = [_project(position, yaw, pitch) for triangle in scene.triangles for position in triangle["positions"]]
    min_x = min(value[0] for value in projected_all)
    max_x = max(value[0] for value in projected_all)
    min_y = min(value[1] for value in projected_all)
    max_y = max(value[1] for value in projected_all)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    fit_scale = min((width - 48) / span_x, (height - 48) / span_y)
    scale = fit_scale * max(0.1, min(12.0, float(zoom)))
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    background = (14, 21, 29, 255)
    pixels = bytearray(background * (width * height))
    z_buffer = [float("inf")] * (width * height)
    textured_faces = 0
    unresolved_faces = 0
    pixel_writes = 0
    unresolved_edges: list[tuple[tuple[float, float], tuple[float, float]]] = []

    for triangle in scene.triangles[:MAX_RENDER_FACES]:
        projected = [_project(position, yaw, pitch) for position in triangle["positions"]]
        screen = [((x - center_x) * scale + width / 2.0, height / 2.0 - (y - center_y) * scale, depth) for x, y, depth in projected]
        texture = triangle.get("texture")
        uvs = triangle.get("uvs")
        if texture is None or uvs is None:
            unresolved_faces += 1
            unresolved_edges.extend([((screen[0][0], screen[0][1]), (screen[1][0], screen[1][1])), ((screen[1][0], screen[1][1]), (screen[2][0], screen[2][1])), ((screen[2][0], screen[2][1]), (screen[0][0], screen[0][1]))])
            continue

        textured_faces += 1
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = screen
        area = _edge(x0, y0, x1, y1, x2, y2)
        if abs(area) < 1e-9:
            continue
        min_px = max(0, int(math.floor(min(x0, x1, x2))))
        max_px = min(width - 1, int(math.ceil(max(x0, x1, x2))))
        min_py = max(0, int(math.floor(min(y0, y1, y2))))
        max_py = min(height - 1, int(math.ceil(max(y0, y1, y2))))
        material_alpha = max(0.0, min(1.0, float(triangle.get("material_alpha") or 0.0)))
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
                pixel_index = py * width + px
                if depth >= z_buffer[pixel_index]:
                    continue
                z_buffer[pixel_index] = depth
                u = w0 * uvs[0][0] + w1 * uvs[1][0] + w2 * uvs[2][0]
                v = w0 * uvs[0][1] + w1 * uvs[1][1] + w2 * uvs[2][1]
                r, g, b, a = _sample(texture, u, v)
                _blend(pixels, pixel_index * 4, (r, g, b, int(a * material_alpha)))
                pixel_writes += 1

    for left, right in unresolved_edges[: MAX_RENDER_FACES * 3]:
        _line(pixels, width, height, left, right, (150, 90, 110, 180))

    target = Path(output_path).expanduser()
    write_rgba_png(target, width, height, bytes(pixels))
    return {"output_path": str(target), "yaw": yaw, "pitch": pitch, "zoom": zoom, "width": width, "height": height, "triangles_total": len(scene.triangles), "triangles_submitted": min(len(scene.triangles), MAX_RENDER_FACES), "textured_faces": textured_faces, "unresolved_faces": unresolved_faces, "pixel_writes": pixel_writes, "face_cap_applied": len(scene.triangles) > MAX_RENDER_FACES, "scene_summary": scene.summary}


def export_scene_textures(scene: TexturedScene, output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for texture_id, texture in sorted(scene.textures.items()):
        name = str(texture.get("object_name") or f"texture_{texture_id}")
        safe = "".join(character if character.isalnum() or character in "._-" else "_" for character in name).strip("._") or f"texture_{texture_id}"
        path = write_rgba_png(root / f"{safe}.png", int(texture["width"]), int(texture["height"]), texture["rgba"])
        rows.append({"texture_id": texture_id, "texture_name": name, "path": str(path), "width": texture["width"], "height": texture["height"]})
    return {"source": str(scene.source), "textures": rows, "count": len(rows)}

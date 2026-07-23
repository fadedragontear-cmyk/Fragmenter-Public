#!/usr/bin/env python3
"""Corrected, clump-authoritative Gen1 preview scene and adaptive rasterizer."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v4 as pose_v4
import ccsf_textured_scene_v3 as scene_core
import ccsf_textured_scene_v5 as scene_v5
from ccsf_texture_decoder_v1 import write_rgba_png

# V5 resolves the pose module at call time. Keep its proven clump-instance and
# MAT/TEX/CLUT assembly while replacing the pose authority with the exact
# OpenTK-compatible Gen1 matrix implementation.
scene_v5.pose_v3 = pose_v4
scene_v5.clear_scene_cache()

TexturedScene = scene_v5.TexturedScene
clear_scene_cache = scene_v5.clear_scene_cache
set_preferred_clump = scene_v5.set_preferred_clump
preferred_clump_id = scene_v5.preferred_clump_id
export_scene_textures = scene_v5.export_scene_textures
scene_wireframe_payload = scene_v5.scene_wireframe_payload

DEFAULT_WIDTH = scene_core.DEFAULT_WIDTH
DEFAULT_HEIGHT = scene_core.DEFAULT_HEIGHT
MAX_RENDER_FACES = scene_core.MAX_RENDER_FACES


def load_textured_scene(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> TexturedScene:
    return scene_v5.load_textured_scene(path, animation_name=animation_name, frame=frame)


def load_scene_bundle(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    face_cap: int = 30_000,
) -> dict[str, Any]:
    """Load one authoritative scene and derive wireframe from those same triangles."""
    scene = load_textured_scene(path, animation_name=animation_name, frame=frame)
    wireframe = scene_wireframe_payload(scene, face_cap=max(1, int(face_cap)))
    wireframe["parser"] = "clump_scene_bundle_v6"
    return {"scene": scene, "wireframe": wireframe}


def load_posed_wireframe_payload(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    face_cap: int = 30_000,
) -> dict[str, Any]:
    return load_scene_bundle(path, animation_name=animation_name, frame=frame, face_cap=face_cap)["wireframe"]


def preview_pixel_step(quality: str) -> int:
    return {"Fast": 3, "Balanced": 2, "Full": 1}.get(str(quality or "Balanced"), 2)


def auto_texture_eligibility(summary: dict[str, Any], *, max_triangles: int = 8_000) -> tuple[bool, str]:
    decoded = int(summary.get("decoded_textures") or 0)
    textured = int(summary.get("textured_triangles") or 0)
    triangles = int(summary.get("triangles") or 0)
    if decoded <= 0:
        return False, "no decoded TEX/CLUT image"
    if textured <= 0:
        return False, "no triangles have resolved texture + UV data"
    if triangles > int(max_triangles):
        return False, f"{triangles:,} triangles exceeds auto-texture limit {int(max_triangles):,}"
    return True, f"{textured:,} textured triangles / {decoded} decoded texture(s)"


def render_textured_scene(
    scene: TexturedScene,
    output_path: str | Path,
    *,
    yaw: float = -0.55,
    pitch: float = 0.35,
    zoom: float = 1.0,
    pan_x: float = 0.0,
    pan_y: float = 0.0,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    pixel_step: int = 1,
) -> dict[str, Any]:
    """Software-render a posed scene with shared camera state and adaptive pixels.

    ``pixel_step`` preserves output dimensions while sampling/filling small pixel
    blocks. Balanced/Fast preview therefore stays visually large instead of
    displaying a physically smaller PNG on the Tk canvas.
    """
    if not scene.triangles:
        raise ValueError("scene contains no renderable triangles")
    width = max(32, int(width))
    height = max(32, int(height))
    pixel_step = max(1, min(4, int(pixel_step)))
    projected_all = [scene_core._project(position, yaw, pitch) for triangle in scene.triangles for position in triangle["positions"]]
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
    screen_center_x = width / 2.0 + float(pan_x) * width
    screen_center_y = height / 2.0 + float(pan_y) * height

    background = (14, 21, 29, 255)
    pixels = bytearray(background * (width * height))
    z_buffer = [float("inf")] * (width * height)
    textured_faces = 0
    unresolved_faces = 0
    pixel_writes = 0
    unresolved_edges: list[tuple[tuple[float, float], tuple[float, float]]] = []

    for triangle in scene.triangles[:MAX_RENDER_FACES]:
        projected = [scene_core._project(position, yaw, pitch) for position in triangle["positions"]]
        screen = [
            ((x - center_x) * scale + screen_center_x, screen_center_y - (y - center_y) * scale, depth)
            for x, y, depth in projected
        ]
        texture = triangle.get("texture")
        uvs = triangle.get("uvs")
        if texture is None or uvs is None:
            unresolved_faces += 1
            unresolved_edges.extend(
                [
                    ((screen[0][0], screen[0][1]), (screen[1][0], screen[1][1])),
                    ((screen[1][0], screen[1][1]), (screen[2][0], screen[2][1])),
                    ((screen[2][0], screen[2][1]), (screen[0][0], screen[0][1])),
                ]
            )
            continue

        textured_faces += 1
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = screen
        area = scene_core._edge(x0, y0, x1, y1, x2, y2)
        if abs(area) < 1e-9:
            continue
        min_px = max(0, int(math.floor(min(x0, x1, x2))))
        max_px = min(width - 1, int(math.ceil(max(x0, x1, x2))))
        min_py = max(0, int(math.floor(min(y0, y1, y2))))
        max_py = min(height - 1, int(math.ceil(max(y0, y1, y2))))
        material_alpha = max(0.0, min(1.0, float(triangle.get("material_alpha") if triangle.get("material_alpha") is not None else 1.0)))

        for py in range(min_py, max_py + 1, pixel_step):
            sample_y = py + pixel_step * 0.5
            for px in range(min_px, max_px + 1, pixel_step):
                sample_x = px + pixel_step * 0.5
                w0 = scene_core._edge(x1, y1, x2, y2, sample_x, sample_y) / area
                w1 = scene_core._edge(x2, y2, x0, y0, sample_x, sample_y) / area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-6 or w1 < -1e-6 or w2 < -1e-6:
                    continue
                depth = w0 * z0 + w1 * z1 + w2 * z2
                u = w0 * uvs[0][0] + w1 * uvs[1][0] + w2 * uvs[2][0]
                v = w0 * uvs[0][1] + w1 * uvs[1][1] + w2 * uvs[2][1]
                r, g, b, a = scene_core._sample(texture, u, v)
                color = (r, g, b, int(a * material_alpha))
                for block_y in range(py, min(height, py + pixel_step)):
                    for block_x in range(px, min(width, px + pixel_step)):
                        pixel_index = block_y * width + block_x
                        if depth >= z_buffer[pixel_index]:
                            continue
                        z_buffer[pixel_index] = depth
                        scene_core._blend(pixels, pixel_index * 4, color)
                        pixel_writes += 1

    for left, right in unresolved_edges[: MAX_RENDER_FACES * 3]:
        scene_core._line(pixels, width, height, left, right, (150, 90, 110, 180))

    target = Path(output_path).expanduser()
    write_rgba_png(target, width, height, bytes(pixels))
    return {
        "output_path": str(target),
        "yaw": yaw,
        "pitch": pitch,
        "zoom": zoom,
        "pan_x": pan_x,
        "pan_y": pan_y,
        "width": width,
        "height": height,
        "pixel_step": pixel_step,
        "triangles_total": len(scene.triangles),
        "triangles_submitted": min(len(scene.triangles), MAX_RENDER_FACES),
        "textured_faces": textured_faces,
        "unresolved_faces": unresolved_faces,
        "pixel_writes": pixel_writes,
        "face_cap_applied": len(scene.triangles) > MAX_RENDER_FACES,
        "scene_summary": scene.summary,
    }

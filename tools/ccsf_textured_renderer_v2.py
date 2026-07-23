#!/usr/bin/env python3
"""Cancellable alpha-aware software renderer for interactive CCSF previews."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import ccsf_textured_scene_v3 as scene_core
from ccsf_texture_decoder_v1 import write_rgba_png

MAX_RENDER_FACES = 100_000


class RenderCancelled(RuntimeError):
    """Raised when a newer camera or asset request supersedes this render."""


def _screen_triangle(
    triangle: dict[str, Any],
    *,
    yaw: float,
    pitch: float,
    center_x: float,
    center_y: float,
    scale: float,
    screen_center_x: float,
    screen_center_y: float,
) -> list[tuple[float, float, float]]:
    projected = [scene_core._project(position, yaw, pitch) for position in triangle["positions"]]
    return [
        ((x - center_x) * scale + screen_center_x, screen_center_y - (y - center_y) * scale, depth)
        for x, y, depth in projected
    ]


def render_textured_scene(
    scene: Any,
    output_path: str | Path,
    *,
    yaw: float = -0.55,
    pitch: float = 0.35,
    zoom: float = 1.0,
    pan_x: float = 0.0,
    pan_y: float = 0.0,
    width: int = 760,
    height: int = 560,
    pixel_step: int = 1,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    def check_cancel() -> None:
        if cancel_check is not None and cancel_check():
            raise RenderCancelled("render superseded by a newer preview request")

    if not scene.triangles:
        raise ValueError("scene contains no renderable triangles")
    check_cancel()
    width = max(32, int(width))
    height = max(32, int(height))
    pixel_step = max(1, min(4, int(pixel_step)))
    triangles = list(scene.triangles[:MAX_RENDER_FACES])
    projected_all = [scene_core._project(position, yaw, pitch) for triangle in triangles for position in triangle["positions"]]
    check_cancel()
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
    opaque_z = [float("inf")] * (width * height)
    unresolved_edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    textured_faces = 0
    unresolved_faces = 0
    opaque_pixel_writes = 0
    translucent_pixel_writes = 0

    screen_rows: list[tuple[dict[str, Any], list[tuple[float, float, float]], float]] = []
    for triangle_index, triangle in enumerate(triangles):
        if triangle_index % 256 == 0:
            check_cancel()
        screen = _screen_triangle(
            triangle,
            yaw=yaw,
            pitch=pitch,
            center_x=center_x,
            center_y=center_y,
            scale=scale,
            screen_center_x=screen_center_x,
            screen_center_y=screen_center_y,
        )
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
        average_depth = sum(point[2] for point in screen) / 3.0
        screen_rows.append((triangle, screen, average_depth))

    def raster(row: tuple[dict[str, Any], list[tuple[float, float, float]], float], *, translucent: bool) -> int:
        triangle, screen, _average_depth = row
        texture = triangle["texture"]
        uvs = triangle["uvs"]
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = screen
        area = scene_core._edge(x0, y0, x1, y1, x2, y2)
        if abs(area) < 1e-9:
            return 0
        min_px = max(0, int(math.floor(min(x0, x1, x2))))
        max_px = min(width - 1, int(math.ceil(max(x0, x1, x2))))
        min_py = max(0, int(math.floor(min(y0, y1, y2))))
        max_py = min(height - 1, int(math.ceil(max(y0, y1, y2))))
        material_alpha = max(0.0, min(1.0, float(triangle.get("material_alpha") if triangle.get("material_alpha") is not None else 1.0)))
        writes = 0
        for row_number, py in enumerate(range(min_py, max_py + 1, pixel_step)):
            if row_number % 16 == 0:
                check_cancel()
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
                r, g, b, sampled_alpha = scene_core._sample(texture, u, v)
                alpha = int(sampled_alpha * material_alpha)
                if alpha <= 2:
                    continue
                is_translucent = alpha < 250
                if is_translucent != translucent:
                    continue
                for block_y in range(py, min(height, py + pixel_step)):
                    for block_x in range(px, min(width, px + pixel_step)):
                        pixel_index = block_y * width + block_x
                        if depth >= opaque_z[pixel_index]:
                            continue
                        if not translucent:
                            opaque_z[pixel_index] = depth
                        scene_core._blend(pixels, pixel_index * 4, (r, g, b, alpha))
                        writes += 1
        return writes

    for row_index, row in enumerate(screen_rows):
        if row_index % 64 == 0:
            check_cancel()
        opaque_pixel_writes += raster(row, translucent=False)
    for row_index, row in enumerate(sorted(screen_rows, key=lambda item: item[2], reverse=True)):
        if row_index % 64 == 0:
            check_cancel()
        translucent_pixel_writes += raster(row, translucent=True)

    for edge_index, (left, right) in enumerate(unresolved_edges[: MAX_RENDER_FACES * 3]):
        if edge_index % 512 == 0:
            check_cancel()
        scene_core._line(pixels, width, height, left, right, (150, 90, 110, 180))

    check_cancel()
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
        "triangles_submitted": len(triangles),
        "textured_faces": textured_faces,
        "unresolved_faces": unresolved_faces,
        "opaque_pixel_writes": opaque_pixel_writes,
        "translucent_pixel_writes": translucent_pixel_writes,
        "face_cap_applied": len(scene.triangles) > MAX_RENDER_FACES,
        "alpha_depth_policy": "transparent texels skip depth; translucent triangles render far-to-near against opaque depth",
        "scene_summary": scene.summary,
    }

#!/usr/bin/env python3
"""Perspective free-fly extension of the stable CCSF software renderer."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Iterable

import camera_fly_v1 as camera_fly
import camera_orbit_v1 as camera_orbit
import ccsf_textured_scene_v3 as scene_core
from ccsf_texture_decoder_v1 import write_rgba_png

MAX_RENDER_FACES = 100_000
MAX_UNRESOLVED_EDGES = 24_000
_PREVIEW_BACKGROUND_RGBA = (24, 28, 32, 255)
_PREVIEW_CAMERA_BASIS: tuple[float, ...] | None = None
_PREVIEW_CAMERA_POSITION: tuple[float, float, float] | None = None


class RenderCancelled(RuntimeError):
    """Raised when a newer camera, pose, or asset request supersedes this render."""


def _normalize_background(value: Iterable[int] | None) -> tuple[int, int, int, int]:
    if value is None:
        return _PREVIEW_BACKGROUND_RGBA
    rows = list(value)
    if len(rows) == 3:
        rows.append(255)
    if len(rows) != 4:
        raise ValueError("preview background must contain RGB or RGBA values")
    return tuple(max(0, min(255, int(component))) for component in rows)  # type: ignore[return-value]


def set_preview_background(value: Iterable[int]) -> tuple[int, int, int, int]:
    global _PREVIEW_BACKGROUND_RGBA
    _PREVIEW_BACKGROUND_RGBA = _normalize_background(value)
    return _PREVIEW_BACKGROUND_RGBA


def preview_background() -> tuple[int, int, int, int]:
    return _PREVIEW_BACKGROUND_RGBA


def set_preview_camera_basis(value: Iterable[float] | None) -> tuple[float, ...] | None:
    global _PREVIEW_CAMERA_BASIS
    if value is None:
        _PREVIEW_CAMERA_BASIS = None
    else:
        _PREVIEW_CAMERA_BASIS = camera_orbit.flatten_basis(camera_orbit.basis_from_flat(value))
    return _PREVIEW_CAMERA_BASIS


def preview_camera_basis() -> tuple[float, ...] | None:
    return _PREVIEW_CAMERA_BASIS


def set_preview_camera_position(value: Iterable[float] | None) -> tuple[float, float, float] | None:
    """Set normalized camera position relative to each scene's center and radius."""
    global _PREVIEW_CAMERA_POSITION
    if value is None:
        _PREVIEW_CAMERA_POSITION = None
    else:
        _PREVIEW_CAMERA_POSITION = camera_fly.normalize_position(value)
    return _PREVIEW_CAMERA_POSITION


def preview_camera_position() -> tuple[float, float, float] | None:
    return _PREVIEW_CAMERA_POSITION


def _project_orthographic(
    position: Iterable[float],
    yaw: float,
    pitch: float,
    camera_basis: tuple[float, ...] | None,
) -> tuple[float, float, float]:
    if camera_basis is None:
        return scene_core._project(tuple(float(value) for value in position), yaw, pitch)
    return camera_orbit.project(position, camera_orbit.basis_from_flat(camera_basis))


def _screen_triangle(
    triangle: dict[str, Any],
    *,
    yaw: float,
    pitch: float,
    camera_basis: tuple[float, ...] | None,
    camera_world: camera_fly.Vec3 | None,
    near_plane: float,
    center_x: float,
    center_y: float,
    scale: float,
    screen_center_x: float,
    screen_center_y: float,
) -> list[tuple[float, float, float]] | None:
    if camera_world is not None and camera_basis is not None:
        basis = camera_orbit.basis_from_flat(camera_basis)
        projected = [
            camera_fly.perspective_project(
                position,
                basis,
                camera_world,
                focal_length=scale,
                screen_center_x=screen_center_x,
                screen_center_y=screen_center_y,
                near_plane=near_plane,
            )
            for position in triangle["positions"]
        ]
        if any(value is None for value in projected):
            return None
        return [value for value in projected if value is not None]
    projected = [
        _project_orthographic(position, yaw, pitch, camera_basis)
        for position in triangle["positions"]
    ]
    return [
        ((x - center_x) * scale + screen_center_x, screen_center_y - (y - center_y) * scale, depth)
        for x, y, depth in projected
    ]


def _alpha_profile(texture: dict[str, Any]) -> tuple[int, int]:
    cached = texture.get("_renderer_alpha_profile_v4")
    if isinstance(cached, (list, tuple)) and len(cached) == 2:
        return int(cached[0]), int(cached[1])
    rgba = texture.get("rgba")
    if not isinstance(rgba, (bytes, bytearray)) or len(rgba) < 4:
        profile = (255, 255)
    else:
        view = memoryview(rgba)
        minimum = 255
        maximum = 0
        for offset in range(3, len(view), 4):
            value = int(view[offset])
            minimum = min(minimum, value)
            maximum = max(maximum, value)
            if minimum <= 2 and maximum >= 250:
                break
        profile = (minimum, maximum)
    texture["_renderer_alpha_profile_v4"] = list(profile)
    return profile


def _effective_alpha_mode(texture: dict[str, Any], material_alpha: float) -> str:
    minimum, maximum = _alpha_profile(texture)
    material = max(0.0, min(1.0, float(material_alpha)))
    effective_min = int(minimum * material)
    effective_max = int(maximum * material)
    if effective_max <= 2:
        return "invisible"
    if effective_min >= 250:
        return "opaque"
    if effective_max < 250:
        return "translucent"
    return "mixed"


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
    background_rgba: Iterable[int] | None = None,
    camera_basis: Iterable[float] | None = None,
    camera_position: Iterable[float] | None = None,
) -> dict[str, Any]:
    def check_cancel() -> None:
        if cancel_check is not None and cancel_check():
            raise RenderCancelled("render superseded by a newer preview request")

    if not scene.triangles:
        raise ValueError("scene contains no renderable triangles")
    check_cancel()
    width = max(32, int(width))
    height = max(32, int(height))
    pixel_step = max(1, min(6, int(pixel_step)))
    triangles = list(scene.triangles[:MAX_RENDER_FACES])
    basis_source = tuple(float(value) for value in camera_basis) if camera_basis is not None else _PREVIEW_CAMERA_BASIS
    basis = camera_orbit.flatten_basis(camera_orbit.basis_from_flat(basis_source)) if basis_source is not None else None
    position_source = (
        camera_fly.normalize_position(camera_position)
        if camera_position is not None
        else _PREVIEW_CAMERA_POSITION
    )
    perspective = basis is not None and position_source is not None
    scene_center: camera_fly.Vec3 | None = None
    scene_radius: float | None = None
    camera_world: camera_fly.Vec3 | None = None
    near_plane = 0.0

    if perspective:
        scene_center, scene_radius = camera_fly.scene_center_radius(
            position for triangle in triangles for position in triangle["positions"]
        )
        camera_world = camera_fly.world_position(scene_center, scene_radius, position_source)
        center_x = 0.0
        center_y = 0.0
        scale = min(width, height) * 0.85 * max(0.1, min(12.0, float(zoom)))
        near_plane = max(scene_radius * 0.005, 1e-7)
    else:
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for triangle_index, triangle in enumerate(triangles):
            if triangle_index % 512 == 0:
                check_cancel()
            for position in triangle["positions"]:
                x, y, _depth = _project_orthographic(position, yaw, pitch, basis)
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
        if not math.isfinite(min_x) or not math.isfinite(min_y):
            raise ValueError("scene has no finite projected positions")
        span_x = max(max_x - min_x, 1e-9)
        span_y = max(max_y - min_y, 1e-9)
        fit_scale = min((width - 48) / span_x, (height - 48) / span_y)
        scale = fit_scale * max(0.1, min(12.0, float(zoom)))
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0

    screen_center_x = width / 2.0 + float(pan_x) * width
    screen_center_y = height / 2.0 + float(pan_y) * height
    background = _normalize_background(background_rgba)
    pixels = bytearray(background * (width * height))
    opaque_z = [float("inf")] * (width * height)
    textured_faces = 0
    unresolved_faces = 0
    invisible_faces = 0
    clipped_faces = 0
    opaque_pixel_writes = 0
    translucent_pixel_writes = 0

    opaque_rows: list[tuple[dict[str, Any], list[tuple[float, float, float]], float, str]] = []
    translucent_rows: list[tuple[dict[str, Any], list[tuple[float, float, float]], float, str]] = []
    unresolved_screens: list[list[tuple[float, float, float]]] = []

    for triangle_index, triangle in enumerate(triangles):
        if triangle_index % 256 == 0:
            check_cancel()
        screen = _screen_triangle(
            triangle,
            yaw=yaw,
            pitch=pitch,
            camera_basis=basis,
            camera_world=camera_world,
            near_plane=near_plane,
            center_x=center_x,
            center_y=center_y,
            scale=scale,
            screen_center_x=screen_center_x,
            screen_center_y=screen_center_y,
        )
        if screen is None:
            clipped_faces += 1
            continue
        texture = triangle.get("texture")
        uvs = triangle.get("uvs")
        if texture is None or uvs is None:
            unresolved_faces += 1
            unresolved_screens.append(screen)
            continue
        textured_faces += 1
        material_alpha = float(triangle.get("material_alpha") if triangle.get("material_alpha") is not None else 1.0)
        mode = _effective_alpha_mode(texture, material_alpha)
        if mode == "invisible":
            invisible_faces += 1
            continue
        average_depth = sum(point[2] for point in screen) / 3.0
        row = (triangle, screen, average_depth, mode)
        if mode in {"opaque", "mixed"}:
            opaque_rows.append(row)
        if mode in {"translucent", "mixed"}:
            translucent_rows.append(row)

    def raster(
        row: tuple[dict[str, Any], list[tuple[float, float, float]], float, str],
        *,
        translucent: bool,
    ) -> int:
        triangle, screen, _average_depth, alpha_mode = row
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
        opaque_fast = alpha_mode == "opaque" and not translucent
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
                alpha = 255 if opaque_fast else int(sampled_alpha * material_alpha)
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
                        target = pixel_index * 4
                        if not translucent:
                            opaque_z[pixel_index] = depth
                            if opaque_fast:
                                pixels[target : target + 4] = bytes((r, g, b, 255))
                            else:
                                scene_core._blend(pixels, target, (r, g, b, alpha))
                        else:
                            scene_core._blend(pixels, target, (r, g, b, alpha))
                        writes += 1
        return writes

    for row_index, row in enumerate(opaque_rows):
        if row_index % 64 == 0:
            check_cancel()
        opaque_pixel_writes += raster(row, translucent=False)
    for row_index, row in enumerate(sorted(translucent_rows, key=lambda item: item[2], reverse=True)):
        if row_index % 64 == 0:
            check_cancel()
        translucent_pixel_writes += raster(row, translucent=True)

    total_edges = len(unresolved_screens) * 3
    edge_step = max(1, math.ceil(total_edges / MAX_UNRESOLVED_EDGES))
    edge_index = 0
    drawn_edges = 0
    for screen_index, screen in enumerate(unresolved_screens):
        if screen_index % 256 == 0:
            check_cancel()
        for left, right in ((screen[0], screen[1]), (screen[1], screen[2]), (screen[2], screen[0])):
            if edge_index % edge_step == 0:
                scene_core._line(pixels, width, height, (left[0], left[1]), (right[0], right[1]), (150, 90, 110, 180))
                drawn_edges += 1
            edge_index += 1

    check_cancel()
    target = Path(output_path).expanduser()
    write_rgba_png(target, width, height, bytes(pixels))
    return {
        "output_path": str(target),
        "yaw": yaw,
        "pitch": pitch,
        "camera_basis": list(basis) if basis is not None else None,
        "camera_position": list(position_source) if position_source is not None else None,
        "camera_world": list(camera_world) if camera_world is not None else None,
        "scene_center": list(scene_center) if scene_center is not None else None,
        "scene_radius": scene_radius,
        "projection": "perspective_free_fly" if perspective else "orthographic_fit",
        "zoom": zoom,
        "pan_x": pan_x,
        "pan_y": pan_y,
        "width": width,
        "height": height,
        "pixel_step": pixel_step,
        "background_rgba": list(background),
        "triangles_total": len(scene.triangles),
        "triangles_submitted": len(triangles),
        "textured_faces": textured_faces,
        "unresolved_faces": unresolved_faces,
        "clipped_faces": clipped_faces,
        "invisible_faces": invisible_faces,
        "opaque_rows": len(opaque_rows),
        "translucent_rows": len(translucent_rows),
        "opaque_pixel_writes": opaque_pixel_writes,
        "translucent_pixel_writes": translucent_pixel_writes,
        "unresolved_edges_total": total_edges,
        "unresolved_edges_drawn": drawn_edges,
        "face_cap_applied": len(scene.triangles) > MAX_RENDER_FACES,
        "alpha_depth_policy": "opaque textures raster once; mixed alpha raster by opaque/translucent passes; transparent texels skip depth",
        "scene_summary": scene.summary,
    }

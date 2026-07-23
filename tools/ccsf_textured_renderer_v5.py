#!/usr/bin/env python3
"""Lower-cost fast passes around the stable Python software renderer.

Full-quality renders remain untouched.  Files explicitly produced as responsive,
camera-fast or animation-fast previews are bounded to a smaller framebuffer before
entering the per-pixel Python raster loop.  This reduces work quadratically while the
existing idle refinement still replaces the image with a viewport-resolution render.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import ccsf_textured_renderer_v4 as base

MAX_RENDER_FACES = base.MAX_RENDER_FACES
MAX_UNRESOLVED_EDGES = base.MAX_UNRESOLVED_EDGES
RenderCancelled = base.RenderCancelled
set_preview_background = base.set_preview_background
preview_background = base.preview_background
set_preview_camera_basis = base.set_preview_camera_basis
preview_camera_basis = base.preview_camera_basis
set_preview_camera_position = base.set_preview_camera_position
preview_camera_position = base.preview_camera_position

FAST_MAX_WIDTH = 640
FAST_MAX_HEIGHT = 480
_FAST_MARKERS = ("_fast", "camera_fast", "animation_fast", "responsive")


def is_fast_preview_path(path: str | Path) -> bool:
    stem = Path(path).stem.casefold()
    return any(marker in stem for marker in _FAST_MARKERS)


def bounded_fast_dimensions(width: int, height: int) -> tuple[int, int]:
    requested_width = max(32, int(width))
    requested_height = max(32, int(height))
    scale = min(
        1.0,
        FAST_MAX_WIDTH / float(requested_width),
        FAST_MAX_HEIGHT / float(requested_height),
    )
    return (
        max(32, int(round(requested_width * scale))),
        max(32, int(round(requested_height * scale))),
    )


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
    cancel_check=None,
    background_rgba: Iterable[int] | None = None,
    camera_basis: Iterable[float] | None = None,
    camera_position: Iterable[float] | None = None,
) -> dict[str, Any]:
    requested = (max(32, int(width)), max(32, int(height)))
    fast = is_fast_preview_path(output_path)
    render_size = bounded_fast_dimensions(*requested) if fast else requested
    result = base.render_textured_scene(
        scene,
        output_path,
        yaw=yaw,
        pitch=pitch,
        zoom=zoom,
        pan_x=pan_x,
        pan_y=pan_y,
        width=render_size[0],
        height=render_size[1],
        pixel_step=pixel_step,
        cancel_check=cancel_check,
        background_rgba=background_rgba,
        camera_basis=camera_basis,
        camera_position=camera_position,
    )
    result["preview_performance_policy"] = (
        "bounded fast framebuffer; full scene geometry retained"
        if fast
        else "full requested framebuffer"
    )
    result["requested_width"] = requested[0]
    result["requested_height"] = requested[1]
    result["fast_preview"] = fast
    result["framebuffer_pixel_reduction"] = round(
        1.0 - (render_size[0] * render_size[1]) / float(requested[0] * requested[1]),
        6,
    )
    return result

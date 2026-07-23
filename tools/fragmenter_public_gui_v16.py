#!/usr/bin/env python3
"""Sixteenth public GUI pass: cancellable texture renders for responsive navigation."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import Any

import ccsf_textured_scene_v9 as scene_v9
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v15 import PublicFragmenterAppV15


def _is_cancelled(error: Exception | None) -> bool:
    return error is not None and type(error).__name__ == "RenderCancelled"


class PublicFragmenterAppV16(PublicFragmenterAppV15):
    """Abort obsolete software raster jobs instead of merely hiding their results."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Responsive 3D / Texture Mapping")

    def _camera_tuple(self) -> tuple[float, float, float, float, float]:
        return (
            float(self._wire_yaw),
            float(self._wire_pitch),
            float(self._wire_zoom),
            float(self._wire_pan_x),
            float(self._wire_pan_y),
        )

    def _render_progressive(self, scene: Any, row: dict[str, Any], load_generation: int) -> None:
        project = self.project
        if project is None:
            return
        self._progressive_render_generation += 1
        render_generation = self._progressive_render_generation
        width = max(480, self.visual_canvas.winfo_width())
        height = max(360, self.visual_canvas.winfo_height())
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview_fast.png"
        camera = self._camera_tuple()
        self.visual_status.set("Rendering responsive textured preview…")

        def cancelled() -> bool:
            return (
                load_generation != self._texture_load_generation
                or render_generation != self._progressive_render_generation
                or self._preview_mode != "textured"
                or camera != self._camera_tuple()
            )

        def done(result: Any, error: Exception | None) -> None:
            if _is_cancelled(error) or cancelled():
                return
            if error:
                self.visual_status.set(f"Responsive texture render failed: {error}")
                return
            self._show_png_on_visual_canvas(Path(result["output_path"]))
            self.visual_progress["value"] = 75.0
            summary = scene.summary
            self.visual_status.set(
                f"Responsive preview: {summary.get('textured_triangles', 0):,} textured / "
                f"{summary.get('unresolved_triangles', 0):,} unresolved triangles. Full resolution waits for idle."
            )
            if self._camera_refine_after is not None:
                try:
                    self.after_cancel(self._camera_refine_after)
                except tk.TclError:
                    pass
            self._camera_refine_after = self.after(700, self._start_camera_refine)

        self._local_worker(
            "textured-responsive-v16",
            lambda: scene_v9.render_textured_scene(
                scene,
                output,
                yaw=camera[0],
                pitch=camera[1],
                zoom=camera[2],
                pan_x=camera[3],
                pan_y=camera[4],
                width=width,
                height=height,
                pixel_step=3,
                cancel_check=cancelled,
            ),
            done,
        )

    def _start_camera_interactive_render(self) -> None:
        self._settled_render_after = None
        if self._camera_render_busy:
            self._camera_render_pending = True
            return
        scene = self._textured_scene
        row = self._textured_scene_row
        project = self.project
        if scene is None or row is None or project is None or self._preview_mode != "textured":
            return
        self._camera_render_busy = True
        self._camera_render_pending = False
        self._camera_render_generation += 1
        generation = self._camera_render_generation
        camera = self._camera_tuple()
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_camera_fast.png"
        width = max(480, self.visual_canvas.winfo_width())
        height = max(360, self.visual_canvas.winfo_height())
        self.visual_status.set("Rendering interactive textured camera view…")

        def cancelled() -> bool:
            return (
                generation != self._camera_render_generation
                or self._preview_mode != "textured"
                or scene is not self._textured_scene
                or camera != self._camera_tuple()
            )

        def done(result: Any, error: Exception | None) -> None:
            self._camera_render_busy = False
            stale = cancelled()
            if not stale and not error:
                self._show_png_on_visual_canvas(Path(result["output_path"]))
                self.visual_status.set("Interactive textured view ready; full-resolution refinement waits for idle.")
            elif error and not _is_cancelled(error) and not stale:
                self.visual_status.set(f"Interactive camera render failed: {error}")
            if self._camera_render_pending or stale or _is_cancelled(error):
                self._camera_render_pending = False
                if self._preview_mode == "textured" and self._textured_scene is not None:
                    self.after(30, self._start_camera_interactive_render)
                return
            self._camera_refine_after = self.after(900, self._start_camera_refine)

        self._local_worker(
            "textured-camera-fast-v16",
            lambda: scene_v9.render_textured_scene(
                scene,
                output,
                yaw=camera[0],
                pitch=camera[1],
                zoom=camera[2],
                pan_x=camera[3],
                pan_y=camera[4],
                width=width,
                height=height,
                pixel_step=3,
                cancel_check=cancelled,
            ),
            done,
        )

    def _start_camera_refine(self) -> None:
        self._camera_refine_after = None
        if self._camera_render_busy:
            self._camera_render_pending = True
            return
        scene = self._textured_scene
        row = self._textured_scene_row
        project = self.project
        if scene is None or row is None or project is None or self._preview_mode != "textured":
            return
        self._camera_render_busy = True
        self._camera_render_generation += 1
        generation = self._camera_render_generation
        camera = self._camera_tuple()
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview.png"
        width = max(480, self.visual_canvas.winfo_width())
        height = max(360, self.visual_canvas.winfo_height())
        self.visual_status.set("Refining full-resolution textured view…")

        def cancelled() -> bool:
            return (
                generation != self._camera_render_generation
                or self._preview_mode != "textured"
                or scene is not self._textured_scene
                or camera != self._camera_tuple()
            )

        def done(result: Any, error: Exception | None) -> None:
            self._camera_render_busy = False
            stale = cancelled()
            if not stale and not error:
                self._show_png_on_visual_canvas(Path(result["output_path"]))
                self.visual_progress["value"] = 100.0
                self.visual_status.set("Full-resolution textured camera view ready.")
            elif error and not _is_cancelled(error) and not stale:
                self.visual_status.set(f"Camera refinement failed: {error}")
            if self._camera_render_pending or stale or _is_cancelled(error):
                self._camera_render_pending = False
                if self._preview_mode == "textured" and self._textured_scene is not None:
                    self.after(30, self._start_camera_interactive_render)

        self._local_worker(
            "textured-camera-refine-v16",
            lambda: scene_v9.render_textured_scene(
                scene,
                output,
                yaw=camera[0],
                pitch=camera[1],
                zoom=camera[2],
                pan_x=camera[3],
                pan_y=camera[4],
                width=width,
                height=height,
                pixel_step=self._settled_pixel_step(),
                cancel_check=cancelled,
            ),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV16()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

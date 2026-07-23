#!/usr/bin/env python3
"""Twenty-second public GUI pass: true low-resolution interactive raster buffers."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import Any

import ccsf_textured_scene_v9 as scene_v9
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v16 import _is_cancelled
from fragmenter_public_gui_v21 import PublicFragmenterAppV21


class PublicFragmenterAppV22(PublicFragmenterAppV21):
    """Render fast views at half size; retain full resolution only for idle refine."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Stable Textured 3D Review")

    def _show_low_resolution_png(self, path: Path, label: str) -> None:
        photo = tk.PhotoImage(file=str(path))
        canvas_width = max(1, self.visual_canvas.winfo_width())
        canvas_height = max(1, self.visual_canvas.winfo_height())
        ratio = min(canvas_width / max(1, photo.width()), canvas_height / max(1, photo.height()))
        factor = 2 if ratio >= 1.95 else 1
        if factor > 1:
            photo = photo.zoom(factor, factor)
        self._texture_photo = photo
        self.visual_canvas.delete("all")
        self.visual_canvas.create_image(canvas_width / 2, canvas_height / 2, image=photo, anchor="center")
        self.visual_canvas.create_text(
            10,
            10,
            anchor="nw",
            fill="#EAF4FF",
            text=f"{label} | displayed {photo.width()}x{photo.height()} from half-resolution software buffer",
        )

    def _show_animation_png(self, path: Path) -> None:
        self._show_low_resolution_png(path, "Textured playback")

    def _fast_dimensions(self) -> tuple[int, int]:
        return (
            max(240, self.visual_canvas.winfo_width() // 2),
            max(180, self.visual_canvas.winfo_height() // 2),
        )

    def _render_progressive(self, scene: Any, row: dict[str, Any], load_generation: int) -> None:
        project = self.project
        if project is None:
            return
        self._progressive_render_generation += 1
        render_generation = self._progressive_render_generation
        width, height = self._fast_dimensions()
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview_fast.png"
        camera = self._camera_tuple()
        self.visual_status.set("Rendering half-resolution responsive textured preview…")

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
            self._show_low_resolution_png(Path(result["output_path"]), "Responsive textured preview")
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
            "textured-responsive-v22",
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
                pixel_step=1,
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
        width, height = self._fast_dimensions()
        self.visual_status.set("Rendering half-resolution interactive textured camera view…")

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
                self._show_low_resolution_png(Path(result["output_path"]), "Interactive textured view")
                self.visual_status.set("Interactive textured view ready; full-resolution refinement waits for idle.")
            elif error and not _is_cancelled(error) and not stale:
                self.visual_status.set(f"Interactive camera render failed: {error}")
            if self._camera_render_pending or stale or _is_cancelled(error):
                self._camera_render_pending = False
                if self._preview_mode == "textured" and self._textured_scene is not None:
                    self._queue_camera_render(30)
                return
            self._camera_refine_after = self.after(800, self._start_camera_refine)

        self._local_worker(
            "textured-camera-fast-v22",
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
                pixel_step=1,
                cancel_check=cancelled,
            ),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV22()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

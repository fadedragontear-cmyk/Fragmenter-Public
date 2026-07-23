#!/usr/bin/env python3
"""Fifteenth public GUI pass: coalesced texture refinement and selection work."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import Any

import ccsf_textured_scene_v9 as scene_v9
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v14 import PublicFragmenterAppV14


class PublicFragmenterAppV15(PublicFragmenterAppV14):
    """Stabilize the accepted v13 layout and staged v14 preview pipeline."""

    def __init__(self) -> None:
        self._contents_after: str | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — 3D / Texture Stabilization")

    def _visual_asset_selected(self, _event: tk.Event) -> None:
        self._texture_load_generation += 1
        self._progressive_render_generation += 1
        self._external_enrichment_generation += 1
        self._camera_render_generation += 1
        self._camera_render_pending = False
        for token_name in (
            "_settled_render_after",
            "_camera_refine_after",
            "_auto_texture_after",
            "_contents_after",
        ):
            token = getattr(self, token_name, None)
            if token is not None:
                try:
                    self.after_cancel(token)
                except tk.TclError:
                    pass
                setattr(self, token_name, None)
        self._preview_mode = "wireframe"
        self._textured_scene = None
        self._textured_scene_row = None
        self._schedule_wireframe_load()
        # Geometry is the primary interaction. Starting the contents parser almost
        # immediately caused two decoders to compete for CPU and disk on selection.
        self._contents_after = self.after(650, self._run_scheduled_contents_load)

    def _run_scheduled_contents_load(self) -> None:
        self._contents_after = None
        self._load_selected_ccsf_contents()

    def _render_progressive(self, scene: Any, row: dict[str, Any], load_generation: int) -> None:
        """Render one responsive image, then refine through the single camera queue.

        The previous implementation launched a second uncancellable full raster from
        inside the fast-render callback. Camera movement could therefore compete with
        that render. V15 schedules refinement only after an idle window.
        """
        project = self.project
        if project is None:
            return
        self._progressive_render_generation += 1
        render_generation = self._progressive_render_generation
        width = max(480, self.visual_canvas.winfo_width())
        height = max(360, self.visual_canvas.winfo_height())
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview_fast.png"
        camera = (self._wire_yaw, self._wire_pitch, self._wire_zoom, self._wire_pan_x, self._wire_pan_y)
        self.visual_status.set("Rendering responsive textured preview…")

        def done(result: Any, error: Exception | None) -> None:
            if load_generation != self._texture_load_generation or render_generation != self._progressive_render_generation:
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
            "textured-responsive-v15",
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
            ),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV15()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

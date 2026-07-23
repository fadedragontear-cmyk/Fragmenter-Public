#!/usr/bin/env python3
"""Fourteenth public GUI pass: responsive geometry, staged textures and camera."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import Any

import ccsf_texture_audit_v1 as texture_audit_v1
import ccsf_texture_name_index_v2 as texture_index_v2
import ccsf_textured_scene_v9 as scene_v9
import ccsf_wireframe_scene_v2 as wireframe_v2
import fragmenter_public_gui_v5 as gui_v5
import fragmenter_public_gui_v7 as gui_v7
import fragmenter_public_gui_v8 as gui_v8
import fragmenter_public_gui_v11 as gui_v11
import fragmenter_public_gui_v13 as gui_v13
from ccsf_asset_tree_v1 import inspect_ccsf_contents
from ccsf_gen1_pose_v5 import INITIAL_POSE_NAME
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v13 import PublicFragmenterAppV13

# Every inherited geometry path is cheap and texture-free. Every textured path uses
# the staged scene authority, so local records can render before the external index.
gui_v5.load_textured_scene = scene_v9.load_textured_scene
gui_v5.load_posed_wireframe_payload = wireframe_v2.load_complete_wireframe_payload
gui_v5.render_textured_scene = scene_v9.render_textured_scene
gui_v5.export_scene_textures = scene_v9.export_scene_textures
gui_v7.scene_v5 = scene_v9
gui_v8.scene_v6 = scene_v9
gui_v8.load_clump_wireframe_payload = wireframe_v2.load_complete_wireframe_payload
gui_v11.scene_v7 = scene_v9
gui_v13.scene_v8 = scene_v9
texture_audit_v1.load_textured_scene = scene_v9.load_textured_scene


class PublicFragmenterAppV14(PublicFragmenterAppV13):
    """Keep the accepted v13 layout while removing blocking preview work."""

    def __init__(self) -> None:
        self._external_enrichment_generation = 0
        self._camera_render_busy = False
        self._camera_render_pending = False
        self._camera_render_generation = 0
        self._camera_refine_after: str | None = None
        self._navigation_textured = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Responsive 3D / Texture Focus")

    # ------------------------------------------------------------------
    # Asset selection: one geometry load, one independent contents load
    # ------------------------------------------------------------------
    def _visual_asset_selected(self, _event: tk.Event) -> None:
        self._texture_load_generation += 1
        self._progressive_render_generation += 1
        self._external_enrichment_generation += 1
        self._camera_render_generation += 1
        self._camera_render_pending = False
        for token_name in ("_settled_render_after", "_camera_refine_after", "_auto_texture_after"):
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
        # Let the geometry worker start first. The two parsers are independent, but
        # staggering them avoids an immediate CPU/disk spike on lower-power laptops.
        self.after(120, self._load_selected_ccsf_contents)

    def _load_selected_ccsf_contents(self) -> None:
        row = self._selected_visual_row()
        self._stop_animation()
        self._ccsf_tree_generation += 1
        generation = self._ccsf_tree_generation
        self._clear_ccsf_contents()
        if row is None:
            return
        self.visual_status.set(f"Reading objects, clumps, materials, textures and animations: {row['name']}…")

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._ccsf_tree_generation:
                return
            if error:
                self.visual_status.set(f"CCSF contents failed: {error}")
                return
            self._ccsf_contents_model = model
            self._populate_ccsf_contents(model)
            animations = [item for item in model.get("animations") or [] if isinstance(item, dict) and item.get("pose_ready")]
            self._animation_rows_by_name = {str(item.get("object_name") or item.get("object_id")): item for item in animations}
            names = (INITIAL_POSE_NAME, *tuple(self._animation_rows_by_name))
            self.animation_combo.configure(values=names)
            self.animation_name.set(INITIAL_POSE_NAME)
            self._configure_animation_range()
            summary = model.get("summary") or {}
            self.visual_status.set(
                f"CCSF indexed: {summary.get('clumps', 0)} clumps, {summary.get('materials', 0)} materials, "
                f"{summary.get('textures', 0)} textures, {summary.get('animations', 0)} animations."
            )
            # Deliberately do not rebuild the wireframe here. The asset-selection
            # geometry worker already loaded this same initial pose.

        self._local_worker("ccsf-contents-v14", lambda: inspect_ccsf_contents(row["absolute_path"]), done)

    # ------------------------------------------------------------------
    # Local texture preview, then exact external enrichment
    # ------------------------------------------------------------------
    def _start_textured_preview(self, *, force: bool) -> None:
        self._auto_texture_after = None
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None or row is None:
            return
        if not force and (self.auto_texture_var is None or not self.auto_texture_var.get() or self._animation_playing):
            return
        if force:
            self._stop_animation()
        self._set_preview_mode_controls("textured")
        self._texture_load_generation += 1
        generation = self._texture_load_generation
        self._external_enrichment_generation += 1
        enrichment_generation = self._external_enrichment_generation
        animation = self.animation_name.get().strip() or INITIAL_POSE_NAME
        frame = max(0, int(self.animation_frame.get()))
        active_row = dict(row)
        mode = scene_v9.SELECTED_CLUMP if self.scene_assembly_mode is not None and self.scene_assembly_mode.get() == "Selected Clump" else scene_v9.WHOLE_FILE
        scene_v9.set_assembly_mode(row["absolute_path"], mode)
        self.visual_status.set(f"Texture phase 1/2: resolving local MAT/TEX/CLUT records for {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(55)

        def local_done(scene: Any, error: Exception | None) -> None:
            if generation != self._texture_load_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self._preview_mode = "wireframe"
                self._set_preview_mode_controls("wireframe")
                self.visual_status.set(f"Local texture mapping failed: {error}")
                self._replace_info(self.visual_details, f"Local texture mapping failed:\n{error}")
                return
            eligible, reason = scene_v9.auto_texture_eligibility(scene.summary, max_triangles=self._auto_texture_limit)
            self._textured_scene = scene
            self._textured_scene_row = active_row
            self._write_scene_evidence(scene, reason)
            if not force and not eligible:
                self.visual_progress["value"] = 100.0
                self._preview_mode = "wireframe"
                self._set_preview_mode_controls("wireframe")
                self.visual_status.set(f"Wireframe retained: {reason}. Select Textured to force a render.")
                return
            self._preview_mode = "textured"
            self.visual_progress["value"] = 35.0
            self._render_progressive(scene, active_row, generation)
            self.after(
                500,
                lambda: self._start_external_enrichment(
                    active_row,
                    animation,
                    frame,
                    mode,
                    generation,
                    enrichment_generation,
                ),
            )

        self._local_worker(
            "local-texture-map-v14",
            lambda: scene_v9.load_textured_scene(
                row["absolute_path"],
                animation_name=animation,
                frame=frame,
                assembly=mode,
                external_lookup=False,
            ),
            local_done,
        )

    def _start_external_enrichment(
        self,
        row: dict[str, Any],
        animation: str,
        frame: int,
        mode: str,
        load_generation: int,
        enrichment_generation: int,
    ) -> None:
        if load_generation != self._texture_load_generation or enrichment_generation != self._external_enrichment_generation:
            return
        current = self._selected_visual_row()
        if current is None or str(current.get("absolute_path")) != str(row.get("absolute_path")):
            return
        self.visual_status.set("Texture phase 2/2: preparing reusable exact-name MAT/TEX/CLUT index in background…")

        def index_done(index_result: Any, error: Exception | None) -> None:
            if load_generation != self._texture_load_generation or enrichment_generation != self._external_enrichment_generation:
                return
            if error:
                self.visual_status.set(f"Local textures retained; external texture index failed: {error}")
                return
            self.visual_status.set(
                f"External index ready ({index_result.get('names', 0):,} names). Enriching unresolved texture links…"
            )

            def scene_done(scene: Any, scene_error: Exception | None) -> None:
                if load_generation != self._texture_load_generation or enrichment_generation != self._external_enrichment_generation:
                    return
                if scene_error:
                    self.visual_status.set(f"Local textures retained; external enrichment failed: {scene_error}")
                    return
                previous = self._textured_scene
                previous_count = int((previous.summary if previous is not None else {}).get("textured_triangles") or 0)
                new_count = int(scene.summary.get("textured_triangles") or 0)
                self._textured_scene = scene
                self._textured_scene_row = row
                self._write_scene_evidence(scene, "external exact-name enrichment complete")
                if new_count > previous_count and self._preview_mode == "textured":
                    self.visual_status.set(
                        f"External mapping added {new_count - previous_count:,} textured triangle(s); refreshing preview…"
                    )
                    self._render_progressive(scene, row, load_generation)
                else:
                    self.visual_status.set(
                        f"External mapping complete: {new_count:,} textured / {scene.summary.get('unresolved_triangles', 0):,} unresolved triangles."
                    )

            self._local_worker(
                "external-texture-map-v14",
                lambda: scene_v9.load_textured_scene(
                    row["absolute_path"],
                    animation_name=animation,
                    frame=frame,
                    assembly=mode,
                    external_lookup=True,
                ),
                scene_done,
            )

        self._local_worker(
            "texture-name-index-v14",
            lambda: texture_index_v2.ensure_index(row["absolute_path"]),
            index_done,
        )

    def _settled_pixel_step(self) -> int:
        return 2 if self._preview_quality() == "Fast" else 1

    def _render_progressive(self, scene: Any, row: dict[str, Any], load_generation: int) -> None:
        project = self.project
        if project is None:
            return
        self._progressive_render_generation += 1
        render_generation = self._progressive_render_generation
        width = max(480, self.visual_canvas.winfo_width())
        height = max(360, self.visual_canvas.winfo_height())
        output_dir = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"]))
        fast_path = output_dir / "textured_preview_fast.png"
        final_path = output_dir / "textured_preview.png"
        camera = (self._wire_yaw, self._wire_pitch, self._wire_zoom, self._wire_pan_x, self._wire_pan_y)
        self.visual_status.set("Rendering responsive texture preview…")

        def fast_done(result: Any, error: Exception | None) -> None:
            if load_generation != self._texture_load_generation or render_generation != self._progressive_render_generation:
                return
            if error:
                self.visual_status.set(f"Fast texture render failed: {error}")
                return
            self._show_png_on_visual_canvas(Path(result["output_path"]))
            self.visual_progress["value"] = 70.0
            self.visual_status.set("Fast preview ready; refining at full viewport resolution…")

            def final_done(final: Any, final_error: Exception | None) -> None:
                if load_generation != self._texture_load_generation or render_generation != self._progressive_render_generation:
                    return
                if final_error:
                    self.visual_status.set(f"Fast preview retained; refined render failed: {final_error}")
                    return
                self._show_png_on_visual_canvas(Path(final["output_path"]))
                self.visual_progress["value"] = 100.0
                summary = scene.summary
                self.visual_status.set(
                    f"Scene ready: {summary.get('model_instances', 0)} model instances, "
                    f"{summary.get('textured_triangles', 0):,} textured / {summary.get('unresolved_triangles', 0):,} unresolved triangles, "
                    f"{summary.get('external_decoded_textures', 0)} external texture(s)."
                )

            self._local_worker(
                "textured-refine-v14",
                lambda: scene_v9.render_textured_scene(
                    scene,
                    final_path,
                    yaw=camera[0],
                    pitch=camera[1],
                    zoom=camera[2],
                    pan_x=camera[3],
                    pan_y=camera[4],
                    width=width,
                    height=height,
                    pixel_step=self._settled_pixel_step(),
                ),
                final_done,
            )

        self._local_worker(
            "textured-fast-v14",
            lambda: scene_v9.render_textured_scene(
                scene,
                fast_path,
                yaw=camera[0],
                pitch=camera[1],
                zoom=camera[2],
                pan_x=camera[3],
                pan_y=camera[4],
                width=width,
                height=height,
                pixel_step=3,
            ),
            fast_done,
        )

    # ------------------------------------------------------------------
    # Camera navigation: wireframe while moving, one coalesced raster afterward
    # ------------------------------------------------------------------
    def _show_navigation_wireframe(self) -> None:
        if self._wireframe_payload is None:
            return
        previous = self._preview_mode
        self._preview_mode = "wireframe"
        try:
            super()._draw_wireframe()
        finally:
            self._preview_mode = previous

    def _wire_start_drag(self, event: tk.Event) -> None:
        self._navigation_textured = self._preview_mode == "textured" and self._textured_scene is not None
        super()._wire_start_drag(event)
        if self._navigation_textured:
            self._show_navigation_wireframe()

    def _wire_drag_motion(self, event: tk.Event) -> None:
        if not self._navigation_textured:
            super()._wire_drag_motion(event)
            return
        if self._wire_drag is None:
            return
        old_x, old_y = self._wire_drag
        self._wire_yaw += (event.x - old_x) * 0.01
        self._wire_pitch += (event.y - old_y) * 0.01
        self._wire_drag = (event.x, event.y)
        self._show_navigation_wireframe()
        self.visual_status.set("Wireframe navigation preview; textured view will update after release.")

    def _wire_release_drag(self, _event: tk.Event) -> None:
        self._wire_drag = None
        if self._navigation_textured:
            self._navigation_textured = False
            self._schedule_textured_render(delay=120)

    def _wire_start_pan(self, event: tk.Event) -> None:
        self._navigation_textured = self._preview_mode == "textured" and self._textured_scene is not None
        super()._wire_start_pan(event)
        if self._navigation_textured:
            self._show_navigation_wireframe()

    def _wire_pan_motion(self, event: tk.Event) -> None:
        if not self._navigation_textured:
            super()._wire_pan_motion(event)
            return
        if self._wire_pan_drag is None:
            return
        old_x, old_y = self._wire_pan_drag
        width = max(1, self.visual_canvas.winfo_width())
        height = max(1, self.visual_canvas.winfo_height())
        self._wire_pan_x += (event.x - old_x) / float(width)
        self._wire_pan_y += (event.y - old_y) / float(height)
        self._wire_pan_drag = (event.x, event.y)
        self._show_navigation_wireframe()
        self.visual_status.set("Wireframe pan preview; textured view will update after release.")

    def _wire_release_pan(self, _event: tk.Event) -> None:
        self._wire_pan_drag = None
        if self._navigation_textured:
            self._navigation_textured = False
            self._schedule_textured_render(delay=120)

    def _wire_mousewheel(self, event: tk.Event) -> None:
        if self._preview_mode != "textured" or self._textured_scene is None:
            super()._wire_mousewheel(event)
            return
        self._wire_zoom = max(0.15, min(8.0, self._wire_zoom * (1.12 if event.delta > 0 else 0.89)))
        self._sync_zoom_control()
        self._show_navigation_wireframe()
        self._schedule_textured_render(delay=260)

    def _zoom_scale_changed(self, value: str) -> None:
        if self._preview_mode != "textured" or self._textured_scene is None:
            super()._zoom_scale_changed(value)
            return
        self._wire_zoom = max(0.15, min(8.0, float(value)))
        self._show_navigation_wireframe()
        self._schedule_textured_render(delay=260)

    def _schedule_textured_render(self, delay: int = 180) -> None:
        if self._textured_scene is None or self._textured_scene_row is None or self._preview_mode != "textured":
            return
        for token_name in ("_settled_render_after", "_camera_refine_after"):
            token = getattr(self, token_name, None)
            if token is not None:
                try:
                    self.after_cancel(token)
                except tk.TclError:
                    pass
                setattr(self, token_name, None)
        self._settled_render_after = self.after(max(0, int(delay)), self._start_camera_interactive_render)

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
        camera = (self._wire_yaw, self._wire_pitch, self._wire_zoom, self._wire_pan_x, self._wire_pan_y)
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_camera_fast.png"
        width = max(480, self.visual_canvas.winfo_width())
        height = max(360, self.visual_canvas.winfo_height())
        self.visual_status.set("Rendering interactive textured camera view…")

        def done(result: Any, error: Exception | None) -> None:
            self._camera_render_busy = False
            current_camera = (self._wire_yaw, self._wire_pitch, self._wire_zoom, self._wire_pan_x, self._wire_pan_y)
            stale = generation != self._camera_render_generation or camera != current_camera
            if not stale and not error and self._preview_mode == "textured":
                self._show_png_on_visual_canvas(Path(result["output_path"]))
                self.visual_status.set("Interactive textured view ready; full-resolution refinement waits for idle.")
            elif error and not stale:
                self.visual_status.set(f"Interactive camera render failed: {error}")
            if self._camera_render_pending or stale:
                self._camera_render_pending = False
                self.after(30, self._start_camera_interactive_render)
                return
            self._camera_refine_after = self.after(900, self._start_camera_refine)

        self._local_worker(
            "textured-camera-fast-v14",
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
        camera = (self._wire_yaw, self._wire_pitch, self._wire_zoom, self._wire_pan_x, self._wire_pan_y)
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview.png"
        width = max(480, self.visual_canvas.winfo_width())
        height = max(360, self.visual_canvas.winfo_height())

        def done(result: Any, error: Exception | None) -> None:
            self._camera_render_busy = False
            current_camera = (self._wire_yaw, self._wire_pitch, self._wire_zoom, self._wire_pan_x, self._wire_pan_y)
            stale = generation != self._camera_render_generation or camera != current_camera
            if not stale and not error and self._preview_mode == "textured":
                self._show_png_on_visual_canvas(Path(result["output_path"]))
                self.visual_status.set("Full-resolution textured camera view ready.")
            elif error and not stale:
                self.visual_status.set(f"Camera refinement failed: {error}")
            if self._camera_render_pending or stale:
                self._camera_render_pending = False
                self.after(30, self._start_camera_interactive_render)

        self._local_worker(
            "textured-camera-refine-v14",
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
            ),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV14()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

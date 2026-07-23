#!/usr/bin/env python3
"""Twenty-first public GUI pass: stable camera queues and bounded playback."""
from __future__ import annotations

import math
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

import ccsf_textured_scene_v9 as scene_v9
import fragmenter_visual_runtime_v5 as visual_runtime_v5
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v20 import PublicFragmenterAppV20


class PublicFragmenterAppV21(PublicFragmenterAppV20):
    """Keep the accepted layout while bounding all repeated 3D interaction work."""

    def __init__(self) -> None:
        self._camera_queue_after: str | None = None
        self._interactive_geometry_cache: dict[str, Any] = {}
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Stable Textured 3D Review")

    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        # V20 created this checkbutton before the cancellation behavior was known.
        for child in self.animation_play_button.master.winfo_children():
            try:
                if isinstance(child, ttk.Checkbutton) and str(child.cget("text")) == "Textured playback":
                    child.configure(command=self._textured_animation_toggled)
            except tk.TclError:
                continue

    def _visual_asset_selected(self, event: tk.Event) -> None:
        self._stop_animation()
        self._interactive_geometry_cache.clear()
        super()._visual_asset_selected(event)

    # ------------------------------------------------------------------
    # One coalesced camera queue
    # ------------------------------------------------------------------
    def _cancel_camera_work(self) -> None:
        super()._cancel_camera_work()
        if self._camera_queue_after is not None:
            try:
                self.after_cancel(self._camera_queue_after)
            except tk.TclError:
                pass
            self._camera_queue_after = None

    def _queue_camera_render(self, delay: int) -> None:
        if self._camera_queue_after is not None:
            try:
                self.after_cancel(self._camera_queue_after)
            except tk.TclError:
                pass

        def run() -> None:
            self._camera_queue_after = None
            self._start_camera_interactive_render()

        self._camera_queue_after = self.after(max(0, int(delay)), run)

    def _finish_camera_interaction(self) -> None:
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._queue_camera_render(35)
        else:
            self._draw_wireframe()

    def _wire_mousewheel(self, event: tk.Event) -> None:
        self._cancel_camera_work()
        self._wire_zoom = max(0.15, min(8.0, self._wire_zoom * (1.12 if event.delta > 0 else 0.89)))
        self._sync_zoom_control()
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._camera_interacting = True
            self._draw_interactive_wireframe()
            self._camera_interacting = False
            self._queue_camera_render(90)
        else:
            self._draw_wireframe()

    def _right_orbit_motion(self, event: tk.Event) -> None:
        if self._right_orbit_drag is None:
            return
        old_x, old_y = self._right_orbit_drag
        delta_x = event.x - old_x
        delta_y = event.y - old_y
        self._wire_yaw += delta_x * 0.008
        # The established camera controls use negative pitch for the top view.
        # Therefore dragging upward (negative delta_y) must reduce pitch.
        self._wire_pitch = max(-1.52, min(1.52, self._wire_pitch + delta_y * 0.008))
        self._right_orbit_drag = (event.x, event.y)
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"Orbit yaw {self._wire_yaw:.2f}, pitch {self._wire_pitch:.2f} | release for textured view"
        )

    # ------------------------------------------------------------------
    # Bounded wireframe projection
    # ------------------------------------------------------------------
    def _interactive_geometry(self) -> dict[str, Any] | None:
        payload = self._wireframe_payload
        if not payload or not payload.get("vertices") or not payload.get("faces"):
            return None
        key = (id(payload), len(payload["vertices"]), len(payload["faces"]))
        if self._interactive_geometry_cache.get("key") == key:
            return self._interactive_geometry_cache

        vertices = payload["vertices"]
        xs = [float(row[0]) for row in vertices]
        ys = [float(row[1]) for row in vertices]
        zs = [float(row[2]) for row in vertices]
        minimum = (min(xs), min(ys), min(zs))
        maximum = (max(xs), max(ys), max(zs))
        corners = [
            (x, y, z)
            for x in (minimum[0], maximum[0])
            for y in (minimum[1], maximum[1])
            for z in (minimum[2], maximum[2])
        ]

        samples: dict[int, tuple[list[Any], list[int]]] = {}
        faces = payload["faces"]
        for limit in (1200, 6000):
            step = max(1, math.ceil(len(faces) / limit))
            selected = list(faces[::step])
            indices = sorted(
                {
                    int(index)
                    for face in selected
                    if isinstance(face, (list, tuple)) and len(face) >= 3
                    for index in face[:3]
                    if 0 <= int(index) < len(vertices)
                }
            )
            samples[limit] = (selected, indices)

        self._interactive_geometry_cache = {
            "key": key,
            "vertices": vertices,
            "faces_total": len(faces),
            "corners": corners,
            "samples": samples,
        }
        return self._interactive_geometry_cache

    def _draw_wireframe(self) -> None:
        if self._preview_mode == "textured" and not self._camera_interacting:
            return
        self._draw_interactive_wireframe()

    def _draw_interactive_wireframe(self) -> None:
        canvas = getattr(self, "visual_canvas", None)
        geometry = self._interactive_geometry()
        if canvas is None:
            return
        canvas.delete("all")
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        if geometry is None:
            canvas.create_text(20, 20, anchor="nw", fill="#BFD7EA", text="No geometry is ready for camera interaction.")
            return

        cy, sy = math.cos(self._wire_yaw), math.sin(self._wire_yaw)
        cp, sp = math.cos(self._wire_pitch), math.sin(self._wire_pitch)

        def project(position: Any) -> tuple[float, float, float]:
            x, y, z = (float(position[0]), float(position[1]), float(position[2]))
            rx = cy * x + sy * z
            rz = -sy * x + cy * z
            ry = cp * y - sp * rz
            depth = sp * y + cp * rz
            return rx, ry, depth

        projected_corners = [project(row) for row in geometry["corners"]]
        min_x = min(row[0] for row in projected_corners)
        max_x = max(row[0] for row in projected_corners)
        min_y = min(row[1] for row in projected_corners)
        max_y = max(row[1] for row in projected_corners)
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)
        scale = min((width - 50) / span_x, (height - 50) / span_y) * self._wire_zoom
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        screen_center_x = width / 2.0 + self._wire_pan_x * width
        screen_center_y = height / 2.0 + self._wire_pan_y * height

        limit = 1200 if self._camera_interacting else 6000
        faces, indices = geometry["samples"][limit]
        screen: dict[int, tuple[float, float, float]] = {}
        for index in indices:
            x, y, depth = project(geometry["vertices"][index])
            screen[index] = (
                (x - center_x) * scale + screen_center_x,
                screen_center_y - (y - center_y) * scale,
                depth,
            )

        displayed = 0
        for face in faces:
            if not isinstance(face, (list, tuple)) or len(face) < 3:
                continue
            a, b, c = (int(face[0]), int(face[1]), int(face[2]))
            if a not in screen or b not in screen or c not in screen:
                continue
            points = (screen[a], screen[b], screen[c])
            canvas.create_line(
                points[0][0], points[0][1], points[1][0], points[1][1],
                points[2][0], points[2][1], points[0][0], points[0][1],
                fill="#77C8FF", width=1,
            )
            displayed += 1
        canvas.create_text(
            10, 10, anchor="nw", fill="#EAF4FF",
            text=(
                f"Bounded wireframe {displayed:,}/{geometry['faces_total']:,} faces | "
                "right orbit | middle pan | wheel zoom"
            ),
        )

    # ------------------------------------------------------------------
    # Texture enrichment and bounded textured animation
    # ------------------------------------------------------------------
    def _start_external_enrichment(self, *args: Any, **kwargs: Any) -> None:
        scene = self._textured_scene
        unresolved = getattr(scene, "unresolved", {}) if scene is not None else {}
        needs_external = any(
            count and ("external" in reason.lower() or "indexed" in reason.lower())
            for reason, count in unresolved.items()
        )
        if scene is not None and not needs_external:
            recovery = scene.summary.get("indexed_setup_recovery") or {}
            self.visual_progress["value"] = 100.0
            self.visual_status.set(
                f"Local texture mapping complete: {scene.summary.get('textured_triangles', 0):,} textured triangles; "
                f"{recovery.get('count', 0)} skipped setup record(s) recovered."
            )
            return
        super()._start_external_enrichment(*args, **kwargs)

    def _textured_animation_toggled(self) -> None:
        if not self._textured_animation_enabled() and self._animation_playing:
            self._stop_animation()
            self.visual_status.set("Textured playback disabled; animation stopped.")

    def _show_animation_png(self, path: Path) -> None:
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
            10, 10, anchor="nw", fill="#EAF4FF",
            text=f"Textured playback {photo.width()}x{photo.height()} display | half-resolution software frame",
        )

    def _request_animation_frame(self, frame: int) -> None:
        if not self._textured_animation_enabled():
            super()._request_animation_frame(frame)
            return
        row = self._selected_visual_row()
        animation = self._animation_row()
        project = self.project
        if row is None or animation is None or project is None:
            return
        frame_count = max(1, int(animation.get("frame_count") or 1))
        frame = int(frame) % frame_count
        self.animation_frame.set(frame)
        self.animation_frame_scale.set(frame)
        self._update_animation_frame_label(frame)
        if self._animation_frame_job or self._textured_animation_busy:
            self._animation_pending_frame = frame
            return

        self._animation_frame_job = True
        self._textured_animation_busy = True
        self._animation_frame_generation += 1
        self._textured_animation_generation += 1
        generation = self._animation_frame_generation
        texture_generation = self._textured_animation_generation
        animation_name = self.animation_name.get()
        source = str(row["absolute_path"])
        active_row = dict(row)
        mode = scene_v9.SELECTED_CLUMP if self.scene_assembly_mode is not None and self.scene_assembly_mode.get() == "Selected Clump" else scene_v9.WHOLE_FILE
        started = time.perf_counter()
        self.visual_status.set(f"Textured animation frame {frame}/{frame_count - 1}: evaluating pose…")

        def scene_work() -> Any:
            scene = scene_v9.load_textured_scene(
                source,
                animation_name=animation_name,
                frame=frame,
                assembly=mode,
                external_lookup=True,
            )
            visual_runtime_v5.trim_scene_cache_for_source(source, keep_scene=scene)
            return scene

        def scene_done(scene: Any, error: Exception | None) -> None:
            if generation != self._animation_frame_generation or texture_generation != self._textured_animation_generation:
                return
            if error:
                self._animation_frame_job = False
                self._textured_animation_busy = False
                self.visual_status.set(f"Textured animation failed: {error}")
                self._stop_animation()
                return
            self._textured_scene = scene
            self._textured_scene_row = active_row
            self._wireframe_payload = scene_v9.scene_wireframe_payload(scene, face_cap=6000)
            self._interactive_geometry_cache.clear()
            self._preview_mode = "textured"
            self._set_preview_mode_controls("textured")
            output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_animation_fast.png"
            width = max(240, self.visual_canvas.winfo_width() // 2)
            height = max(180, self.visual_canvas.winfo_height() // 2)
            camera = self._camera_tuple()
            self.visual_status.set(f"Textured animation frame {frame}/{frame_count - 1}: rendering half-resolution frame…")

            def cancelled() -> bool:
                return (
                    generation != self._animation_frame_generation
                    or texture_generation != self._textured_animation_generation
                    or not self._textured_animation_enabled()
                )

            def render_done(result: Any, render_error: Exception | None) -> None:
                if cancelled():
                    return
                self._animation_frame_job = False
                self._textured_animation_busy = False
                if render_error:
                    self.visual_status.set(f"Textured animation render failed: {render_error}")
                    self._stop_animation()
                    return
                self._show_animation_png(Path(result["output_path"]))
                elapsed = max(0.001, time.perf_counter() - started)
                self.visual_status.set(
                    f"Textured animation {animation_name} frame {frame}/{frame_count - 1} | "
                    f"{scene.summary.get('textured_triangles', 0):,} textured triangles | {elapsed:.2f}s"
                )
                pending = self._animation_pending_frame
                self._animation_pending_frame = None
                if pending is not None and pending != frame:
                    self._request_animation_frame(pending)
                elif self._animation_playing:
                    advance = max(1, min(8, int(round(elapsed / 0.10))))
                    next_frame = (frame + advance) % frame_count
                    self._animation_tick_after = self.after(15, lambda: self._request_animation_frame(next_frame))

            self._local_worker(
                "textured-animation-render-v21",
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
                render_done,
            )

        self._local_worker("textured-animation-scene-v21", scene_work, scene_done)


def main() -> int:
    app = PublicFragmenterAppV21()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Twentieth public GUI pass: bounded camera interaction and textured playback."""
from __future__ import annotations

import math
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import ccsf_textured_scene_v9 as scene_v9
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v19 import PublicFragmenterAppV19


class PublicFragmenterAppV20(PublicFragmenterAppV19):
    """Keep navigation responsive and make textured animation explicitly opt-in."""

    def __init__(self) -> None:
        self._camera_interacting = False
        self._right_orbit_drag: tuple[int, int] | None = None
        self._textured_animation_busy = False
        self._textured_animation_generation = 0
        self.textured_animation_var: tk.BooleanVar | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Stable 3D / Texture Review")

    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)

        # Right drag is orbit, middle drag is pan. These bindings deliberately do
        # not reuse the historical left-drag callback because its vertical sign was
        # inverted and it had no pitch clamp.
        for sequence in ("<ButtonPress-3>", "<B3-Motion>", "<ButtonRelease-3>"):
            self.visual_canvas.unbind(sequence)
        self.visual_canvas.bind("<ButtonPress-3>", self._right_orbit_start)
        self.visual_canvas.bind("<B3-Motion>", self._right_orbit_motion)
        self.visual_canvas.bind("<ButtonRelease-3>", self._right_orbit_release)

        for sequence in ("<ButtonPress-2>", "<B2-Motion>", "<ButtonRelease-2>"):
            self.visual_canvas.unbind(sequence)
        self.visual_canvas.bind("<ButtonPress-2>", self._middle_pan_start)
        self.visual_canvas.bind("<B2-Motion>", self._middle_pan_motion)
        self.visual_canvas.bind("<ButtonRelease-2>", self._middle_pan_release)

        self.textured_animation_var = tk.BooleanVar(value=False)
        animation_bar = self.animation_play_button.master
        ttk.Checkbutton(
            animation_bar,
            text="Textured playback",
            variable=self.textured_animation_var,
        ).grid(row=0, column=7, padx=(8, 0), sticky="w")
        ttk.Label(animation_bar, text="(low-res, frame-skipping)").grid(row=0, column=8, padx=(4, 0), sticky="w")

    # ------------------------------------------------------------------
    # Camera interaction
    # ------------------------------------------------------------------
    def _cancel_camera_work(self) -> None:
        self._camera_render_generation += 1
        self._progressive_render_generation += 1
        self._camera_render_pending = False
        for attr in ("_settled_render_after", "_camera_refine_after"):
            token = getattr(self, attr, None)
            if token is not None:
                try:
                    self.after_cancel(token)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def _right_orbit_start(self, event: tk.Event) -> None:
        self._cancel_camera_work()
        self._camera_interacting = True
        self._right_orbit_drag = (event.x, event.y)
        self._draw_interactive_wireframe()

    def _right_orbit_motion(self, event: tk.Event) -> None:
        if self._right_orbit_drag is None:
            return
        old_x, old_y = self._right_orbit_drag
        delta_x = event.x - old_x
        delta_y = event.y - old_y
        self._wire_yaw += delta_x * 0.008
        # Dragging upward tilts the camera upward; keep away from the pole singularity.
        self._wire_pitch = max(-1.52, min(1.52, self._wire_pitch - delta_y * 0.008))
        self._right_orbit_drag = (event.x, event.y)
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"Orbit yaw {self._wire_yaw:.2f}, pitch {self._wire_pitch:.2f} | release for textured view"
        )

    def _right_orbit_release(self, _event: tk.Event) -> None:
        self._right_orbit_drag = None
        self._camera_interacting = False
        self._finish_camera_interaction()

    def _middle_pan_start(self, event: tk.Event) -> None:
        self._cancel_camera_work()
        self._camera_interacting = True
        self._wire_pan_drag = (event.x, event.y)
        self._draw_interactive_wireframe()

    def _middle_pan_motion(self, event: tk.Event) -> None:
        if self._wire_pan_drag is None:
            return
        old_x, old_y = self._wire_pan_drag
        width = max(1, self.visual_canvas.winfo_width())
        height = max(1, self.visual_canvas.winfo_height())
        self._wire_pan_x += (event.x - old_x) / float(width)
        self._wire_pan_y += (event.y - old_y) / float(height)
        self._wire_pan_drag = (event.x, event.y)
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"Pan {self._wire_pan_x:.2f}, {self._wire_pan_y:.2f} | release for textured view"
        )

    def _middle_pan_release(self, _event: tk.Event) -> None:
        self._wire_pan_drag = None
        self._camera_interacting = False
        self._finish_camera_interaction()

    def _finish_camera_interaction(self) -> None:
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self.after(35, self._start_camera_interactive_render)
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
            self.after(90, self._start_camera_interactive_render)
        else:
            self._draw_wireframe()

    def _draw_wireframe(self) -> None:
        if self._camera_interacting:
            self._draw_interactive_wireframe()
            return
        super()._draw_wireframe()

    def _draw_interactive_wireframe(self) -> None:
        canvas = getattr(self, "visual_canvas", None)
        payload = self._wireframe_payload
        if canvas is None:
            return
        canvas.delete("all")
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        if not payload or not payload.get("vertices") or not payload.get("faces"):
            canvas.create_text(20, 20, anchor="nw", fill="#BFD7EA", text="No geometry is ready for camera interaction.")
            return

        cy, sy = math.cos(self._wire_yaw), math.sin(self._wire_yaw)
        cp, sp = math.cos(self._wire_pitch), math.sin(self._wire_pitch)
        projected: list[tuple[float, float, float]] = []
        for x, y, z in payload["vertices"]:
            rx = cy * x + sy * z
            rz = -sy * x + cy * z
            ry = cp * y - sp * rz
            depth = sp * y + cp * rz
            projected.append((rx, ry, depth))
        min_x = min(value[0] for value in projected)
        max_x = max(value[0] for value in projected)
        min_y = min(value[1] for value in projected)
        max_y = max(value[1] for value in projected)
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)
        scale = min((width - 50) / span_x, (height - 50) / span_y) * self._wire_zoom
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        screen_center_x = width / 2.0 + self._wire_pan_x * width
        screen_center_y = height / 2.0 + self._wire_pan_y * height
        screen = [
            ((x - center_x) * scale + screen_center_x, screen_center_y - (y - center_y) * scale, depth)
            for x, y, depth in projected
        ]

        faces = payload["faces"]
        maximum = 1200 if self._camera_interacting else 6000
        step = max(1, math.ceil(len(faces) / maximum))
        displayed = 0
        for face in faces[::step]:
            if len(face) < 3:
                continue
            a, b, c = int(face[0]), int(face[1]), int(face[2])
            if not all(0 <= index < len(screen) for index in (a, b, c)):
                continue
            points = (screen[a], screen[b], screen[c])
            canvas.create_line(
                points[0][0], points[0][1], points[1][0], points[1][1],
                points[2][0], points[2][1], points[0][0], points[0][1],
                fill="#77C8FF", width=1,
            )
            displayed += 1
        canvas.create_text(
            10,
            10,
            anchor="nw",
            fill="#EAF4FF",
            text=(
                f"Interactive wireframe {displayed:,}/{len(faces):,} faces | "
                f"right orbit | middle pan | wheel zoom"
            ),
        )

    # ------------------------------------------------------------------
    # Textured animation playback
    # ------------------------------------------------------------------
    def _textured_animation_enabled(self) -> bool:
        return bool(self.textured_animation_var is not None and self.textured_animation_var.get())

    def _toggle_animation_play(self) -> None:
        if not self._textured_animation_enabled():
            super()._toggle_animation_play()
            return
        if self._animation_row() is None:
            messagebox.showinfo("Animation", "Select a parsed animation first.")
            return
        if self._animation_playing:
            self._stop_animation()
            return
        self._animation_playing = True
        self.animation_play_button.configure(text="Pause")
        self._preview_mode = "textured"
        self._set_preview_mode_controls("textured")
        self._schedule_animation_tick(delay=0)

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
        self.visual_status.set(f"Textured animation frame {frame}/{frame_count - 1}: assembling pose…")

        def scene_work() -> Any:
            # Keep at most the active animation frame for this source. Texture and
            # setup recovery caches remain reusable.
            scene_v9.clear_scene_cache(source)
            return scene_v9.load_textured_scene(
                source,
                animation_name=animation_name,
                frame=frame,
                assembly=mode,
                external_lookup=True,
            )

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
            self._preview_mode = "textured"
            self._set_preview_mode_controls("textured")
            output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_animation_fast.png"
            width = max(360, self.visual_canvas.winfo_width())
            height = max(280, self.visual_canvas.winfo_height())
            camera = self._camera_tuple()
            self.visual_status.set(f"Textured animation frame {frame}/{frame_count - 1}: rendering low-resolution preview…")

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
                self._show_png_on_visual_canvas(Path(result["output_path"]))
                self.visual_status.set(
                    f"Textured animation {animation_name} frame {frame}/{frame_count - 1} | "
                    f"{scene.summary.get('textured_triangles', 0):,} textured triangles"
                )
                pending = self._animation_pending_frame
                self._animation_pending_frame = None
                if pending is not None and pending != frame:
                    self._request_animation_frame(pending)
                elif self._animation_playing:
                    self._schedule_animation_tick(delay=35)

            self._local_worker(
                "textured-animation-render-v20",
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
                    pixel_step=5,
                    cancel_check=cancelled,
                ),
                render_done,
            )

        self._local_worker("textured-animation-scene-v20", scene_work, scene_done)

    def _stop_animation(self) -> None:
        self._textured_animation_generation += 1
        self._textured_animation_busy = False
        self._animation_frame_job = False
        super()._stop_animation()


def main() -> int:
    app = PublicFragmenterAppV20()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

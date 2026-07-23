#!/usr/bin/env python3
"""Eighth public GUI pass: one 3D authority, corrected poses and research export."""
from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import ccsf_texture_audit_v1 as texture_audit_v1
import ccsf_textured_scene_v6 as scene_v6
import fragmenter_public_gui_v5 as gui_v5
from ccsf_asset_diagnostics_v1 import build_research_bundle
from ccsf_asset_tree_v1 import inspect_ccsf_contents
from ccsf_wireframe_scene_v1 import load_clump_wireframe_payload
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v7 import PublicFragmenterAppV7

# V5 owns the validated animation/textured-preview lifecycle and resolves these
# module globals at call time.  Replace its preview backends with the corrected
# clump-authoritative implementations.  V8 overrides the normal wireframe load
# too, so the old V2 global raw-model assembler is no longer a public path.
gui_v5.load_textured_scene = scene_v6.load_textured_scene
gui_v5.load_posed_wireframe_payload = load_clump_wireframe_payload
gui_v5.render_textured_scene = scene_v6.render_textured_scene
gui_v5.export_scene_textures = scene_v6.export_scene_textures
texture_audit_v1.load_textured_scene = scene_v6.load_textured_scene


class PublicFragmenterAppV8(PublicFragmenterAppV7):
    def __init__(self) -> None:
        self._wire_pan_x = 0.0
        self._wire_pan_y = 0.0
        self._wire_pan_drag: tuple[int, int] | None = None
        self._auto_texture_after: str | None = None
        self._auto_texture_limit = 8_000
        self.auto_texture_var: tk.BooleanVar | None = None
        self.preview_quality_var: tk.StringVar | None = None
        self.preview_zoom_var: tk.DoubleVar | None = None
        super().__init__()
        self._wire_zoom = 1.25
        if self.preview_zoom_var is not None:
            self.preview_zoom_var.set(self._wire_zoom)

    # ------------------------------------------------------------------
    # Visual controls and one authoritative scene path
    # ------------------------------------------------------------------
    def _build_visual(self, parent: ttk.Frame) -> None:
        super()._build_visual(parent)
        self._retitle_texture_actions(parent)

        controls = ttk.LabelFrame(parent, text="3D preview controls", padding=5)
        controls.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.auto_texture_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Auto texture", variable=self.auto_texture_var, command=self._auto_texture_toggled).pack(side="left")
        ttk.Label(controls, text="Quality").pack(side="left", padx=(12, 4))
        self.preview_quality_var = tk.StringVar(value="Balanced")
        quality = ttk.Combobox(controls, textvariable=self.preview_quality_var, values=("Fast", "Balanced", "Full"), state="readonly", width=10)
        quality.pack(side="left")
        quality.bind("<<ComboboxSelected>>", lambda _event: self._preview_quality_changed())
        ttk.Label(controls, text="Zoom").pack(side="left", padx=(12, 4))
        self.preview_zoom_var = tk.DoubleVar(value=1.25)
        zoom = ttk.Scale(controls, from_=0.15, to=8.0, orient="horizontal", length=180, variable=self.preview_zoom_var, command=self._zoom_scale_changed)
        zoom.pack(side="left")
        ttk.Button(controls, text="Fit", command=self._fit_view).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Source Reference", command=self._source_reference_pose).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Diagnostic + OBJ", command=self._asset_research_bundle, style="Accent.TButton").pack(side="left", padx=(6, 0))
        ttk.Label(controls, text="Left drag rotate | right/middle drag pan | wheel zoom | double-click fit").pack(side="right")

        self.visual_canvas.bind("<ButtonPress-2>", self._wire_start_pan)
        self.visual_canvas.bind("<B2-Motion>", self._wire_pan_motion)
        self.visual_canvas.bind("<ButtonRelease-2>", self._wire_release_pan)
        self.visual_canvas.bind("<ButtonPress-3>", self._wire_start_pan)
        self.visual_canvas.bind("<B3-Motion>", self._wire_pan_motion)
        self.visual_canvas.bind("<ButtonRelease-3>", self._wire_release_pan)
        self.visual_canvas.bind("<Double-1>", lambda _event: self._fit_view())

    def _retitle_texture_actions(self, widget: tk.Misc) -> None:
        try:
            if isinstance(widget, ttk.Button) and str(widget.cget("text")) == "Extract Textures":
                widget.configure(text="Export Textures", command=self._export_selected_textures)
            for child in widget.winfo_children():
                self._retitle_texture_actions(child)
        except tk.TclError:
            return

    def _visual_textures(self) -> None:
        self._export_selected_textures()

    def _load_selected_ccsf_contents(self) -> None:
        row = self._selected_visual_row()
        self._stop_animation()
        self._ccsf_tree_generation += 1
        generation = self._ccsf_tree_generation
        self._clear_ccsf_contents()
        if row is None:
            return
        self.visual_status.set(f"Reading internal CCSF tree: {row['name']}…")

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
            names = tuple(self._animation_rows_by_name)
            self.animation_combo.configure(values=names)
            if names:
                preferred = next((name for name in names if "nut" in name.lower()), names[0])
                self.animation_name.set(preferred)
                self._configure_animation_range()
                # A source-backed nut/reference frame is preferable to inventing a
                # T-pose.  Preserve every original track and show the exact source.
                self._request_animation_frame(0)
            summary = model.get("summary") or {}
            self.visual_status.set(
                f"CCSF tree ready: {summary.get('clumps', 0)} clumps, {summary.get('materials', 0)} materials, "
                f"{summary.get('textures', 0)} textures, {summary.get('animations', 0)} animations. "
                f"Reference pose: {self.animation_name.get() or 'identity'} frame 0."
            )

        self._local_worker("ccsf-contents-v8", lambda: inspect_ccsf_contents(row["absolute_path"]), done)

    def _wireframe_load(self, generation: int | None = None, *, allow_auto_texture: bool | None = None) -> None:
        row = self._selected_visual_row()
        if row is None:
            return
        if generation is not None and generation != self._wireframe_generation:
            return
        auto_after = generation is not None if allow_auto_texture is None else bool(allow_auto_texture)
        self._wireframe_generation += 1
        active_generation = self._wireframe_generation
        animation = self.animation_name.get().strip() if hasattr(self, "animation_name") else ""
        frame = max(0, int(self.animation_frame.get())) if hasattr(self, "animation_frame") else 0
        self.visual_status.set(f"Building clump scene wireframe: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)
        active_row = dict(row)

        def done(payload: Any, error: Exception | None) -> None:
            if active_generation != self._wireframe_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Wireframe failed: {error}")
                _replace_text(self.visual_details, f"Clump scene wireframe failed:\n{error}")
                return
            self.visual_progress["value"] = 100.0
            self._preview_mode = "wireframe"
            self._textured_scene = None
            self._textured_scene_row = None
            self._wireframe_payload = payload
            self._wire_yaw, self._wire_pitch, self._wire_zoom = -0.55, 0.35, 1.25
            self._wire_pan_x = self._wire_pan_y = 0.0
            self._sync_zoom_control()
            self._draw_wireframe()
            summary = payload.get("scene_summary") or {}
            self.visual_status.set(
                f"Clump wireframe: {summary.get('selected_clump_name') or 'no clump'} | "
                f"{payload.get('vertex_count', 0):,} vertices / {payload.get('face_count', 0):,} faces | "
                f"{payload.get('selected_animation') or 'identity'} frame {payload.get('frame', 0)}"
            )
            _replace_text(self.visual_details, _json_text({key: value for key, value in payload.items() if key not in {"vertices", "faces"}}))
            if auto_after:
                self._schedule_auto_texture(active_row, payload, delay=100)

        self._local_worker(
            "clump-wireframe-v8",
            lambda: load_clump_wireframe_payload(row["absolute_path"], animation_name=animation or None, frame=frame),
            done,
        )

    def _preview_clump_selected(self) -> None:
        row = self._selected_visual_row()
        label = self.preview_clump_name.get()
        clump_id = self._preview_clumps_by_label.get(label)
        if row is None or clump_id is None:
            return
        scene_v6.set_preferred_clump(row["absolute_path"], clump_id)
        self.preview_clump_status.set(f"Selected 0x{clump_id:X}; rebuilding exact clump instances")
        self._stop_animation()
        self._wireframe_load(allow_auto_texture=True)

    # ------------------------------------------------------------------
    # Animation: fast exact-clump wireframe, texture only after settling
    # ------------------------------------------------------------------
    def _request_animation_frame(self, frame: int) -> None:
        row = self._selected_visual_row()
        animation = self._animation_row()
        if row is None or animation is None:
            return
        frame_count = max(1, int(animation.get("frame_count") or 1))
        frame = int(frame) % frame_count
        self.animation_frame.set(frame)
        self.animation_frame_scale.set(frame)
        self._update_animation_frame_label(frame)
        self._wireframe_generation += 1  # invalidate a queued raw asset-selection load
        if self._animation_frame_job:
            self._animation_pending_frame = frame
            return

        self._animation_frame_job = True
        self._animation_frame_generation += 1
        generation = self._animation_frame_generation
        source = str(row["absolute_path"])
        animation_name = self.animation_name.get()
        active_row = dict(row)
        self.visual_status.set(f"Evaluating {animation_name} frame {frame}/{frame_count - 1}…")

        def done(payload: Any, error: Exception | None) -> None:
            self._animation_frame_job = False
            if generation != self._animation_frame_generation:
                return
            if error:
                self.visual_status.set(f"Animation frame failed: {error}")
                self._stop_animation()
                return
            self._preview_mode = "wireframe"
            self._textured_scene = None
            self._textured_scene_row = None
            self._wireframe_payload = payload
            self._draw_wireframe()
            self.visual_status.set(
                f"Animation wireframe: {payload.get('selected_animation') or animation_name} frame {payload.get('frame', frame)} | "
                f"{payload.get('vertex_count', 0):,} vertices / {payload.get('face_count', 0):,} faces"
            )
            _replace_text(self.visual_details, _json_text({key: value for key, value in payload.items() if key not in {"vertices", "faces"}}))
            pending = self._animation_pending_frame
            self._animation_pending_frame = None
            if pending is not None and pending != frame:
                self._request_animation_frame(pending)
            elif self._animation_playing:
                self._schedule_animation_tick()
            else:
                self._schedule_auto_texture(active_row, payload, delay=120)

        self._local_worker(
            "animation-frame-v8",
            lambda: load_clump_wireframe_payload(source, animation_name=animation_name, frame=frame),
            done,
        )

    def _toggle_animation_play(self) -> None:
        was_playing = self._animation_playing
        super()._toggle_animation_play()
        if was_playing:
            row = self._selected_visual_row()
            if row is not None and self._wireframe_payload is not None:
                self._schedule_auto_texture(dict(row), self._wireframe_payload, delay=160)

    def _source_reference_pose(self) -> None:
        names = tuple(self._animation_rows_by_name)
        if not names:
            messagebox.showinfo("Source Reference", "The selected CCSF has no parsed pose-ready animation.")
            return
        preferred = next((name for name in names if "nut" in name.lower()), names[0])
        self._stop_animation()
        self.animation_name.set(preferred)
        self._configure_animation_range()
        self._request_animation_frame(0)
        self.visual_status.set(f"Source-backed reference pose: {preferred} frame 0. No fabricated T-pose transforms were added.")

    # ------------------------------------------------------------------
    # Camera / viewport
    # ------------------------------------------------------------------
    def _sync_zoom_control(self) -> None:
        if self.preview_zoom_var is not None:
            self.preview_zoom_var.set(float(self._wire_zoom))

    def _set_camera(self, yaw: float, pitch: float, zoom: float | None = None) -> None:
        self._wire_yaw = float(yaw)
        self._wire_pitch = float(pitch)
        if zoom is not None:
            self._wire_zoom = max(0.15, min(8.0, float(zoom)))
        self._sync_zoom_control()
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render(delay=20)
        else:
            self._draw_wireframe()

    def _camera_front(self) -> None:
        self._set_camera(0.0, 0.0, 1.25)

    def _camera_side(self) -> None:
        self._set_camera(math.pi / 2.0, 0.0, 1.25)

    def _camera_top(self) -> None:
        self._set_camera(0.0, -math.pi / 2.0, 1.25)

    def _camera_reset(self) -> None:
        self._wire_pan_x = self._wire_pan_y = 0.0
        self._set_camera(-0.55, 0.35, 1.25)

    def _fit_view(self) -> None:
        self._wire_zoom = 1.25
        self._wire_pan_x = self._wire_pan_y = 0.0
        self._sync_zoom_control()
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render(delay=20)
        else:
            self._draw_wireframe()

    def _zoom_scale_changed(self, value: str) -> None:
        self._wire_zoom = max(0.15, min(8.0, float(value)))
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render(delay=220)
        else:
            self._draw_wireframe()

    def _wire_drag_motion(self, event: tk.Event) -> None:
        if self._wire_drag is None:
            return
        old_x, old_y = self._wire_drag
        self._wire_yaw += (event.x - old_x) * 0.01
        self._wire_pitch += (event.y - old_y) * 0.01
        self._wire_drag = (event.x, event.y)
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self.visual_status.set(f"Camera moving | yaw {self._wire_yaw:.2f} pitch {self._wire_pitch:.2f} | release to rerender")
        else:
            self._draw_wireframe()

    def _wire_release_drag(self, _event: tk.Event) -> None:
        self._wire_drag = None
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render(delay=20)

    def _wire_start_pan(self, event: tk.Event) -> None:
        self._wire_pan_drag = (event.x, event.y)

    def _wire_pan_motion(self, event: tk.Event) -> None:
        if self._wire_pan_drag is None:
            return
        old_x, old_y = self._wire_pan_drag
        width = max(1, self.visual_canvas.winfo_width())
        height = max(1, self.visual_canvas.winfo_height())
        self._wire_pan_x += (event.x - old_x) / float(width)
        self._wire_pan_y += (event.y - old_y) / float(height)
        self._wire_pan_drag = (event.x, event.y)
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self.visual_status.set(f"Camera pan {self._wire_pan_x:.2f}, {self._wire_pan_y:.2f} | release to rerender")
        else:
            self._draw_wireframe()

    def _wire_release_pan(self, _event: tk.Event) -> None:
        self._wire_pan_drag = None
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render(delay=20)

    def _wire_mousewheel(self, event: tk.Event) -> None:
        self._wire_zoom = max(0.15, min(8.0, self._wire_zoom * (1.12 if event.delta > 0 else 0.89)))
        self._sync_zoom_control()
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self.visual_status.set(f"Camera zoom {self._wire_zoom:.2f} | waiting to rerender texture…")
            self._schedule_textured_render(delay=260)
        else:
            self._draw_wireframe()

    def _draw_wireframe(self) -> None:
        if getattr(self, "_preview_mode", "wireframe") == "textured" and getattr(self, "_textured_scene", None) is not None:
            return
        canvas = getattr(self, "visual_canvas", None)
        payload = self._wireframe_payload
        if canvas is None:
            return
        canvas.delete("all")
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        if not payload or not payload.get("vertices") or not payload.get("faces"):
            canvas.create_text(20, 20, anchor="nw", fill="#BFD7EA", text="Select an asset to decode its clump scene wireframe.")
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
        for a, b, c in payload["faces"]:
            points = (screen[a], screen[b], screen[c])
            canvas.create_line(
                points[0][0], points[0][1], points[1][0], points[1][1], points[2][0], points[2][1], points[0][0], points[0][1],
                fill="#77C8FF", width=1,
            )
        canvas.create_text(
            10,
            10,
            anchor="nw",
            fill="#EAF4FF",
            text=(
                f"{payload['vertex_count']:,} vertices | {payload['face_count']:,} faces | "
                f"zoom {self._wire_zoom:.2f} | pan {self._wire_pan_x:.2f},{self._wire_pan_y:.2f} | "
                "left rotate | right/middle pan | wheel zoom"
            ),
        )

    # ------------------------------------------------------------------
    # Textured preview: decoded scene stays in memory; export is separate
    # ------------------------------------------------------------------
    def _preview_quality(self) -> str:
        return self.preview_quality_var.get() if self.preview_quality_var is not None else "Balanced"

    def _preview_quality_changed(self) -> None:
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render(delay=20)

    def _auto_texture_toggled(self) -> None:
        if self.auto_texture_var is not None and self.auto_texture_var.get():
            row = self._selected_visual_row()
            if row is not None and self._wireframe_payload is not None:
                self._schedule_auto_texture(dict(row), self._wireframe_payload, delay=60)

    def _schedule_auto_texture(self, row: dict[str, Any], payload: dict[str, Any], *, delay: int = 120) -> None:
        if self.auto_texture_var is None or not self.auto_texture_var.get() or self._animation_playing:
            return
        face_count = int(payload.get("decoded_face_count") or payload.get("face_count") or 0)
        if face_count > self._auto_texture_limit:
            self.visual_status.set(f"Wireframe ready; auto texture skipped: {face_count:,} faces exceeds {self._auto_texture_limit:,} limit. Textured Preview can force it.")
            return
        if self._auto_texture_after is not None:
            try:
                self.after_cancel(self._auto_texture_after)
            except tk.TclError:
                pass
        self._auto_texture_after = self.after(max(0, int(delay)), lambda: self._start_textured_preview(force=False))

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
        animation = self.animation_name.get().strip() or None
        frame = max(0, int(self.animation_frame.get()))
        active_row = dict(row)
        width, height = max(320, self.visual_canvas.winfo_width()), max(240, self.visual_canvas.winfo_height())
        yaw, pitch, zoom = self._wire_yaw, self._wire_pitch, self._wire_zoom
        pan_x, pan_y = self._wire_pan_x, self._wire_pan_y
        quality = self._preview_quality()
        pixel_step = scene_v6.preview_pixel_step(quality)
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview.png"
        self.visual_status.set(f"Loading MAT/TEX/CLUT scene: {row['name']} / {animation or 'identity'} frame {frame}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def work() -> Any:
            scene = scene_v6.load_textured_scene(row["absolute_path"], animation_name=animation, frame=frame)
            eligible, reason = scene_v6.auto_texture_eligibility(scene.summary, max_triangles=self._auto_texture_limit)
            if not force and not eligible:
                return {"scene": scene, "eligible": False, "reason": reason, "render": None}
            render = scene_v6.render_textured_scene(
                scene,
                output,
                yaw=yaw,
                pitch=pitch,
                zoom=zoom,
                pan_x=pan_x,
                pan_y=pan_y,
                width=width,
                height=height,
                pixel_step=pixel_step,
            )
            return {"scene": scene, "eligible": eligible, "reason": reason, "render": render}

        def done(result: Any, error: Exception | None) -> None:
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Textured preview failed: {error}")
                _replace_text(self.visual_details, f"Textured preview failed:\n{error}")
                return
            scene = result["scene"]
            if result["render"] is None:
                self.visual_progress["value"] = 100.0
                self._preview_mode = "wireframe"
                self.visual_status.set(f"Wireframe retained; auto texture skipped: {result['reason']}. Textured Preview can force it.")
                _replace_text(self.visual_details, _json_text({"scene": scene.summary, "auto_texture": {"eligible": False, "reason": result["reason"]}, "texture_records": scene.texture_rows}))
                return
            self.visual_progress["value"] = 100.0
            self._preview_mode = "textured"
            self._textured_scene = scene
            self._textured_scene_row = active_row
            self._show_png_on_visual_canvas(Path(result["render"]["output_path"]))
            summary = dict(scene.summary)
            _replace_text(
                self.visual_details,
                _json_text(
                    {
                        "scene": summary,
                        "auto_texture": {"eligible": result["eligible"], "reason": result["reason"]},
                        "texture_records": scene.texture_rows,
                        "render": {key: value for key, value in result["render"].items() if key != "scene_summary"},
                    }
                ),
            )
            self.visual_status.set(
                f"Textured {quality}: {summary.get('textured_triangles', 0):,} textured / {summary.get('unresolved_triangles', 0):,} unresolved; "
                f"{summary.get('decoded_textures', 0)}/{summary.get('texture_records', 0)} TEX decoded; "
                f"{summary.get('selected_animation') or 'identity'} frame {summary.get('frame', 0)}"
            )

        self._local_worker("textured-scene-v8", work, done)

    def _visual_textured_snapshot(self) -> None:
        self._start_textured_preview(force=True)

    def _start_textured_render_v5(self) -> None:
        self._textured_render_after = None
        scene = self._textured_scene
        row = self._textured_scene_row
        project = self.project
        if scene is None or row is None or project is None or self._preview_mode != "textured":
            return
        if self._textured_render_busy:
            self._textured_render_pending = True
            return
        self._textured_render_busy = True
        self._textured_render_pending = False
        self._textured_render_generation += 1
        generation = self._textured_render_generation
        yaw, pitch, zoom = self._wire_yaw, self._wire_pitch, self._wire_zoom
        pan_x, pan_y = self._wire_pan_x, self._wire_pan_y
        width, height = max(320, self.visual_canvas.winfo_width()), max(240, self.visual_canvas.winfo_height())
        quality = self._preview_quality()
        pixel_step = scene_v6.preview_pixel_step(quality)
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview.png"
        self.visual_status.set(f"Rendering settled textured view ({quality})…")

        def done(result: Any, error: Exception | None) -> None:
            self._textured_render_busy = False
            if generation == self._textured_render_generation and self._preview_mode == "textured":
                if error:
                    self.visual_status.set(f"Textured rerender failed: {error}")
                else:
                    try:
                        self._show_png_on_visual_canvas(Path(result["output_path"]))
                        self.visual_status.set(
                            f"Textured {quality} | yaw {yaw:.2f} pitch {pitch:.2f} zoom {zoom:.2f} pan {pan_x:.2f},{pan_y:.2f} | "
                            f"{result['textured_faces']:,} textured / {result['unresolved_faces']:,} unresolved"
                        )
                    except Exception as exc:
                        self.visual_status.set(f"Textured PNG display failed: {exc}")
            if self._textured_render_pending and self._preview_mode == "textured":
                self._textured_render_pending = False
                self._schedule_textured_render(delay=20)

        self._local_worker(
            "textured-rerender-v8",
            lambda: scene_v6.render_textured_scene(
                scene,
                output,
                yaw=yaw,
                pitch=pitch,
                zoom=zoom,
                pan_x=pan_x,
                pan_y=pan_y,
                width=width,
                height=height,
                pixel_step=pixel_step,
            ),
            done,
        )

    def _export_selected_textures(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None or row is None:
            return
        animation = self.animation_name.get().strip() or None
        frame = max(0, int(self.animation_frame.get()))
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textures"
        self.visual_status.set(f"Exporting decoded textures: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def work() -> Any:
            scene = scene_v6.load_textured_scene(row["absolute_path"], animation_name=animation, frame=frame)
            return scene_v6.export_scene_textures(scene, output)

        def done(result: Any, error: Exception | None) -> None:
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            self.visual_progress["value"] = 0.0 if error else 100.0
            if error:
                self.visual_status.set(f"Texture export failed: {error}")
                return
            self.visual_status.set(f"Exported {result.get('count', 0)} decoded texture(s) to {output}")
            _replace_text(self.visual_details, _json_text(result))

        self._local_worker("texture-export-v8", work, done)

    # ------------------------------------------------------------------
    # Derived diagnostic + OBJ/MTL export with provenance retained
    # ------------------------------------------------------------------
    def _asset_research_bundle(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None or row is None:
            return
        animation = self.animation_name.get().strip() or None
        frame = max(0, int(self.animation_frame.get()))
        output = project.workspace_path("asset_diagnostics") / _safe_folder(str(row["relative_path"]))
        self.visual_status.set(f"Building asset diagnostic + provenance OBJ: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def done(result: Any, error: Exception | None) -> None:
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            self.visual_progress["value"] = 0.0 if error else 100.0
            if error:
                self.visual_status.set(f"Asset diagnostic failed: {error}")
                _replace_text(self.visual_details, str(error))
                return
            summary = result["diagnostics"]["summary"]
            self.visual_status.set(
                f"Asset diagnostic ready: {summary['submodels']} submodels; {summary['decoded_texture_links']} texture links decoded; "
                f"head rows {summary['head_submodels']} / textured {summary['head_texture_links_decoded']}. Output: {output}"
            )
            _replace_text(
                self.visual_details,
                _json_text(
                    {
                        "summary": summary,
                        "selected_clump": result["diagnostics"]["selected_clump"],
                        "reference_pose_candidates": result["diagnostics"]["reference_pose_candidates"],
                        "report_path": result["diagnostics"]["report_path"],
                        "text_report_path": result["diagnostics"]["text_report_path"],
                        "obj": result["obj"],
                    }
                ),
            )

        self._local_worker(
            "asset-research-v8",
            lambda: build_research_bundle(row["absolute_path"], output, animation_name=animation, frame=frame),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV8()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

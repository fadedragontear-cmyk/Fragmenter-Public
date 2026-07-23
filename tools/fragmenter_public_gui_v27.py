#!/usr/bin/env python3
"""Twenty-seventh public GUI pass: strict camera axes and reliable pose/view restore."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

import ccsf_textured_renderer_v3 as renderer_v3
from ccsf_asset_tree_v1 import inspect_ccsf_contents
from ccsf_gen1_pose_v5 import INITIAL_POSE_NAME
from fragmenter_public_gui_v25 import PublicFragmenterAppV25
from fragmenter_public_gui_v26 import PublicFragmenterAppV26
from visual_asset_annotations_v1 import apply_annotation, load_annotation, save_annotation


class PublicFragmenterAppV27(PublicFragmenterAppV26):
    """Use one-axis orbit gestures and restore pose/view against the focused asset."""

    ORBIT_KEY_STEP = 0.12
    DRAG_RADIANS_PER_PIXEL = 0.008

    def __init__(self) -> None:
        self._camera_overlay_v27: tk.Frame | None = None
        self._camera_overlay_buttons_v27: list[tk.Button] = []
        self._right_orbit_origin_v27: tuple[int, int] | None = None
        self._right_orbit_last_v27: tuple[int, int] | None = None
        self._right_orbit_axis_v27: str | None = None
        self._active_view_source_v27: str | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Axis Camera / Persistent Pose Review")

    # ------------------------------------------------------------------
    # Focused asset authority: multi-selection remains available for batch moves,
    # but preview/save/load operations always use the row the user last focused.
    # ------------------------------------------------------------------
    def _selected_visual_row(self) -> dict[str, Any] | None:
        tree = getattr(self, "visual_tree", None)
        if tree is None:
            return None
        focus = tree.focus()
        if focus and focus in self.visual_payloads:
            return self.visual_payloads[focus]
        for iid in tree.selection():
            row = self.visual_payloads.get(iid)
            if row is not None:
                return row
        return None

    # ------------------------------------------------------------------
    # Minimal viewport overlay. Tk child widgets cannot be alpha-transparent, so
    # the frame is borderless and always matches the selected framebuffer color.
    # ------------------------------------------------------------------
    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        if self._camera_overlay_v26 is not None:
            try:
                self._camera_overlay_v26.destroy()
            except tk.TclError:
                pass
            self._camera_overlay_v26 = None
        self._build_camera_overlay_v27()
        self._bind_camera_keys_v27()

    def _build_camera_overlay_v27(self) -> None:
        _rgba, canvas_color, text_color, _line_color = self._background_values_v25()
        overlay = tk.Frame(
            self.visual_canvas,
            background=canvas_color,
            borderwidth=0,
            highlightthickness=0,
            takefocus=0,
        )
        self._camera_overlay_v27 = overlay
        self._camera_overlay_buttons_v27 = []

        def button(text: str, command, row: int, column: int, *, width: int = 3) -> tk.Button:
            widget = tk.Button(
                overlay,
                text=text,
                command=command,
                width=width,
                padx=1,
                pady=0,
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                background=canvas_color,
                activebackground=canvas_color,
                foreground=text_color,
                activeforeground=text_color,
                font=("Segoe UI Symbol", 11, "bold"),
                takefocus=0,
            )
            widget.grid(row=row, column=column, padx=1, pady=1)
            self._camera_overlay_buttons_v27.append(widget)
            return widget

        button("↑", lambda: self._orbit_nudge_v27(vertical=-1), 0, 1)
        button("←", lambda: self._orbit_nudge_v27(horizontal=-1), 1, 0)
        button("•", self._fit_view, 1, 1)
        button("→", lambda: self._orbit_nudge_v27(horizontal=1), 1, 2)
        button("↓", lambda: self._orbit_nudge_v27(vertical=1), 2, 1)
        button("+", lambda: self._zoom_nudge_v27(1.12), 0, 3)
        button("−", lambda: self._zoom_nudge_v27(0.89), 2, 3)

        backgrounds = tk.Frame(overlay, background=canvas_color, borderwidth=0, highlightthickness=0)
        backgrounds.grid(row=3, column=0, columnspan=4, pady=(2, 0))
        for label, name in (("B", "Black"), ("D", "Dark Gray"), ("G", "Gray"), ("W", "White")):
            widget = tk.Button(
                backgrounds,
                text=label,
                command=lambda value=name: self._set_background_v27(value),
                width=2,
                padx=0,
                pady=0,
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                background=canvas_color,
                activebackground=canvas_color,
                foreground=text_color,
                activeforeground=text_color,
                font=("Segoe UI", 8, "bold"),
                takefocus=0,
            )
            widget.pack(side="left", padx=1)
            self._camera_overlay_buttons_v27.append(widget)

        overlay.place(relx=1.0, x=-8, y=8, anchor="ne")
        overlay.lift()

    def _style_camera_overlay_v27(self) -> None:
        if self._camera_overlay_v27 is None:
            return
        _rgba, canvas_color, text_color, _line_color = self._background_values_v25()
        try:
            self._camera_overlay_v27.configure(background=canvas_color)
            for child in self._camera_overlay_v27.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(background=canvas_color)
            for widget in self._camera_overlay_buttons_v27:
                widget.configure(
                    background=canvas_color,
                    activebackground=canvas_color,
                    foreground=text_color,
                    activeforeground=text_color,
                )
            self._camera_overlay_v27.lift()
        except tk.TclError:
            pass

    def _lift_camera_overlay_v26(self) -> None:
        self._style_camera_overlay_v27()

    def _set_background_v27(self, name: str) -> None:
        if self.preview_background_var is None or name not in self.BACKGROUNDS:
            return
        self.preview_background_var.set(name)
        self._preview_background_changed_v25()
        self._style_camera_overlay_v27()
        self.visual_canvas.focus_set()

    def _preview_background_changed_v25(self, *, render: bool = True) -> None:
        super()._preview_background_changed_v25(render=render)
        self._style_camera_overlay_v27()

    # ------------------------------------------------------------------
    # Keyboard and overlay controls call the same strict yaw/pitch/zoom functions.
    # ------------------------------------------------------------------
    def _bind_camera_keys_v27(self) -> None:
        self.visual_canvas.configure(takefocus=1)
        self.visual_canvas.bind("<Button-1>", lambda _event: self.visual_canvas.focus_set(), add="+")
        self.visual_canvas.bind("<Left>", lambda _event: self._orbit_nudge_v27(horizontal=-1))
        self.visual_canvas.bind("<Right>", lambda _event: self._orbit_nudge_v27(horizontal=1))
        self.visual_canvas.bind("<Up>", lambda _event: self._orbit_nudge_v27(vertical=-1))
        self.visual_canvas.bind("<Down>", lambda _event: self._orbit_nudge_v27(vertical=1))
        self.visual_canvas.bind("<plus>", lambda _event: self._zoom_nudge_v27(1.12))
        self.visual_canvas.bind("<equal>", lambda _event: self._zoom_nudge_v27(1.12))
        self.visual_canvas.bind("<minus>", lambda _event: self._zoom_nudge_v27(0.89))
        self.visual_canvas.bind("<KP_Add>", lambda _event: self._zoom_nudge_v27(1.12))
        self.visual_canvas.bind("<KP_Subtract>", lambda _event: self._zoom_nudge_v27(0.89))

    def _finish_discrete_camera_change_v27(self) -> None:
        self._camera_interacting = False
        self._finish_camera_interaction()
        self.visual_canvas.focus_set()
        self._style_camera_overlay_v27()

    def _orbit_nudge_v27(self, *, horizontal: int = 0, vertical: int = 0) -> str:
        if not horizontal and not vertical:
            return "break"
        self._cancel_camera_work()
        self._camera_interacting = True
        if horizontal:
            self._wire_yaw += int(horizontal) * self.ORBIT_KEY_STEP
        if vertical:
            self._wire_pitch = max(
                -1.52,
                min(1.52, self._wire_pitch + int(vertical) * self.ORBIT_KEY_STEP),
            )
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"Camera axis orbit | yaw {self._wire_yaw:.2f}, pitch {self._wire_pitch:.2f} | "
            "arrows/right-drag rotate; wheel/+/- zoom"
        )
        self._finish_discrete_camera_change_v27()
        return "break"

    def _zoom_nudge_v27(self, factor: float) -> str:
        self._cancel_camera_work()
        self._wire_zoom = max(0.15, min(8.0, self._wire_zoom * float(factor)))
        self._sync_zoom_control()
        self._camera_interacting = True
        self._draw_interactive_wireframe()
        self.visual_status.set(f"Camera zoom {self._wire_zoom:.2f}")
        self._finish_discrete_camera_change_v27()
        return "break"

    # ------------------------------------------------------------------
    # Right drag locks to the dominant initial screen axis for the entire gesture.
    # A horizontal drag changes yaw only; a vertical drag changes pitch only.
    # ------------------------------------------------------------------
    def _right_orbit_start(self, event: tk.Event) -> None:
        self.visual_canvas.focus_set()
        self._cancel_camera_work()
        self._camera_interacting = True
        point = (event.x, event.y)
        self._right_orbit_origin_v27 = point
        self._right_orbit_last_v27 = point
        self._right_orbit_drag = point
        self._right_orbit_axis_v27 = None
        self._right_orbit_axis = None
        self._draw_interactive_wireframe()

    def _right_orbit_motion(self, event: tk.Event) -> None:
        origin = self._right_orbit_origin_v27
        previous = self._right_orbit_last_v27
        if origin is None or previous is None:
            return
        total_x = event.x - origin[0]
        total_y = event.y - origin[1]
        if self._right_orbit_axis_v27 is None:
            if max(abs(total_x), abs(total_y)) < 4:
                return
            self._right_orbit_axis_v27 = "horizontal" if abs(total_x) >= abs(total_y) else "vertical"
            self._right_orbit_axis = self._right_orbit_axis_v27
        delta_x = event.x - previous[0]
        delta_y = event.y - previous[1]
        if self._right_orbit_axis_v27 == "horizontal":
            self._wire_yaw += delta_x * self.DRAG_RADIANS_PER_PIXEL
        else:
            self._wire_pitch = max(
                -1.52,
                min(1.52, self._wire_pitch + delta_y * self.DRAG_RADIANS_PER_PIXEL),
            )
        point = (event.x, event.y)
        self._right_orbit_last_v27 = point
        self._right_orbit_drag = point
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"{self._right_orbit_axis_v27.title()} camera orbit | "
            f"yaw {self._wire_yaw:.2f}, pitch {self._wire_pitch:.2f} | release to texture"
        )

    def _right_orbit_release(self, _event: tk.Event) -> None:
        self._right_orbit_origin_v27 = None
        self._right_orbit_last_v27 = None
        self._right_orbit_drag = None
        self._right_orbit_axis_v27 = None
        self._right_orbit_axis = None
        self._camera_interacting = False
        self._finish_camera_interaction()
        self._style_camera_overlay_v27()

    def _middle_pan_start(self, event: tk.Event) -> None:
        self.visual_canvas.focus_set()
        super()._middle_pan_start(event)

    # ------------------------------------------------------------------
    # Pose/view persistence. Animation metadata must be ready before the saved pose
    # is selected; camera/background are applied against the same focused source.
    # ------------------------------------------------------------------
    def _visual_asset_selected(self, event: tk.Event) -> None:
        if self._suppress_visual_selection_v23:
            return
        row = self._selected_visual_row()
        self._active_view_source_v27 = (
            str(Path(row["absolute_path"]).resolve()) if row is not None else None
        )
        # Bypass v26's early restore. The v27 CCSF completion callback below owns
        # the authoritative restore after animations and the focused row are known.
        PublicFragmenterAppV25._visual_asset_selected(self, event)
        self._style_camera_overlay_v27()

    def _preferred_animation_v27(self, names: tuple[str, ...], saved: str) -> str:
        if saved == INITIAL_POSE_NAME:
            return INITIAL_POSE_NAME
        if saved and saved in names:
            return saved
        return self._preferred_animation_name_v25(names, "")

    def _apply_saved_camera_v27(self, annotation: dict[str, Any]) -> None:
        camera = annotation.get("camera")
        if not isinstance(camera, dict):
            self._apply_camera_v26(*self.DEFAULT_CAMERA, queue_render=False)
            return
        background = str(camera.get("background") or "Dark Gray")
        if self.preview_background_var is not None and background in self.BACKGROUNDS:
            self.preview_background_var.set(background)
            rgba, canvas_color, _text, _line = self.BACKGROUNDS[background]
            renderer_v3.set_preview_background(rgba)
            self.visual_canvas.configure(background=canvas_color)
        self._apply_camera_v26(
            float(camera["yaw"]),
            float(camera["pitch"]),
            float(camera["zoom"]),
            float(camera["pan_x"]),
            float(camera["pan_y"]),
            queue_render=False,
        )
        self._style_camera_overlay_v27()

    def _load_selected_ccsf_contents(self) -> None:
        row = self._selected_visual_row()
        self._stop_animation()
        self._ccsf_tree_generation += 1
        generation = self._ccsf_tree_generation
        self._clear_ccsf_contents()
        if row is None:
            return
        source = str(Path(row["absolute_path"]).resolve())
        active_row = dict(row)
        self.visual_status.set(f"Reading objects, textures and saved pose/view: {row['name']}…")

        def done(model: Any, error: Exception | None) -> None:
            current = self._selected_visual_row()
            current_source = (
                str(Path(current["absolute_path"]).resolve()) if current is not None else None
            )
            if generation != self._ccsf_tree_generation or current_source != source:
                return
            if error:
                self.visual_status.set(f"CCSF contents failed: {error}")
                return
            self._ccsf_contents_model = model
            self._populate_ccsf_contents(model)
            animations = [
                item
                for item in model.get("animations") or []
                if isinstance(item, dict) and item.get("pose_ready")
            ]
            self._animation_rows_by_name = {
                str(item.get("object_name") or item.get("object_id")): item
                for item in animations
            }
            animation_names = tuple(self._animation_rows_by_name)
            self.animation_combo.configure(values=(INITIAL_POSE_NAME, *animation_names))
            annotation = load_annotation(self.project, source) if self.project is not None else {}
            preferred = self._preferred_animation_v27(
                animation_names,
                str(annotation.get("default_animation") or ""),
            )
            frame = max(0, int(annotation.get("default_frame") or 0))
            self.animation_name.set(preferred)
            self._configure_animation_range()
            animation_row = self._animation_rows_by_name.get(preferred)
            frame_count = max(1, int((animation_row or {}).get("frame_count") or 1))
            frame = min(frame, frame_count - 1)
            self.animation_frame.set(frame)
            self.animation_frame_scale.set(frame)
            self._update_animation_frame_label(frame)
            self._apply_saved_camera_v27(annotation)

            summary = model.get("summary") or {}
            if animation_row is not None:
                self.visual_status.set(
                    f"Restoring {active_row['name']}: {preferred} frame {frame}; "
                    f"{summary.get('textures', 0)} textures / {summary.get('animations', 0)} animations."
                )
                self.after_idle(lambda: self._request_animation_frame(frame))
            else:
                self.animation_name.set(INITIAL_POSE_NAME)
                self.visual_status.set(
                    f"Restoring {active_row['name']}: Initial Pose; "
                    f"{summary.get('textures', 0)} textures / no selected pose-ready animation."
                )
                self.after_idle(lambda: self._wireframe_load(allow_auto_texture=True))

        self._local_worker(
            "ccsf-contents-v27",
            lambda: inspect_ccsf_contents(row["absolute_path"]),
            done,
        )

    def _save_pose_view_for_row_v26(self, row: dict[str, Any]) -> None:
        project = self._require_project()
        if project is None:
            return
        animation = self.animation_name.get().strip() or INITIAL_POSE_NAME
        frame = max(0, int(self.animation_frame.get())) if animation != INITIAL_POSE_NAME else 0
        background = (
            self.preview_background_var.get()
            if self.preview_background_var is not None
            else "Dark Gray"
        )
        save_annotation(
            project,
            row["absolute_path"],
            default_animation=animation,
            default_frame=frame,
            camera_yaw=self._wire_yaw,
            camera_pitch=self._wire_pitch,
            camera_zoom=self._wire_zoom,
            camera_pan_x=self._wire_pan_x,
            camera_pan_y=self._wire_pan_y,
            camera_background=background,
            persist=False,
        )
        self._refresh_annotation_marker_v26(row)
        self._visual_context_row = None
        self._visual_context_rows_v25 = []
        self._queue_annotation_persist_v24()
        self.visual_status.set(
            f"Saved {row['name']}: {animation} frame {frame}; camera yaw {self._wire_yaw:.2f}, "
            f"pitch {self._wire_pitch:.2f}, zoom {self._wire_zoom:.2f}."
        )


def main() -> int:
    app = PublicFragmenterAppV27()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

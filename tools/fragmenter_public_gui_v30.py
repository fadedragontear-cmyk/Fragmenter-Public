#!/usr/bin/env python3
"""Thirtieth public GUI pass: perspective WASD navigation and left-drag free look."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Any

import camera_fly_v1 as camera_fly
import camera_orbit_v1 as camera_orbit
import ccsf_textured_renderer_v4 as renderer_v4
from ccsf_gen1_pose_v5 import INITIAL_POSE_NAME
from fragmenter_public_gui_v29 import PublicFragmenterAppV29
from visual_asset_annotations_v1 import save_annotation


class PublicFragmenterAppV30(PublicFragmenterAppV29):
    """Add a normalized perspective camera without removing established review controls."""

    LOOK_RADIANS_PER_PIXEL = 0.006
    DEFAULT_MOVE_STEP = 0.12
    DEFAULT_CAMERA_DISTANCE = 3.0

    def __init__(self) -> None:
        initial_basis = camera_orbit.basis_from_yaw_pitch(-0.55, 0.35)
        self._camera_position_v30 = camera_fly.default_position(initial_basis, self.DEFAULT_CAMERA_DISTANCE)
        self._camera_position_vars_v30: list[tk.DoubleVar] = []
        self._camera_move_step_var_v30: tk.DoubleVar | None = None
        self._camera_position_readout_v30: tk.StringVar | None = None
        self._left_look_last_v30: tuple[int, int] | None = None
        super().__init__()
        self._sync_renderer_camera_v30()
        self._sync_camera_panel_v29()
        self.title("Fragmenter 1.0 WIP — WASD Free-Fly 3D Review")

    # ------------------------------------------------------------------
    # Viewport bindings and visible free-fly controls
    # ------------------------------------------------------------------
    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        for sequence in (
            "<Button-1>",
            "<ButtonPress-1>",
            "<B1-Motion>",
            "<ButtonRelease-1>",
        ):
            self.visual_canvas.unbind(sequence)
        self.visual_canvas.bind("<ButtonPress-1>", self._left_look_start_v30)
        self.visual_canvas.bind("<B1-Motion>", self._left_look_motion_v30)
        self.visual_canvas.bind("<ButtonRelease-1>", self._left_look_release_v30)
        for key, forward, strafe in (
            ("w", 1, 0),
            ("W", 1, 0),
            ("s", -1, 0),
            ("S", -1, 0),
            ("a", 0, -1),
            ("A", 0, -1),
            ("d", 0, 1),
            ("D", 0, 1),
        ):
            self.visual_canvas.bind(
                f"<KeyPress-{key}>",
                lambda _event, f=forward, s=strafe: self._move_camera_v30(forward=f, strafe=s),
            )
        self._augment_camera_panel_v30()
        self._sync_renderer_camera_v30()
        self._sync_camera_panel_v29()

    def _augment_camera_panel_v30(self) -> None:
        target = self._camera_panel_frame_v29
        if target is None:
            return
        position = ttk.LabelFrame(target, text="Free-fly position", padding=7)
        position.grid(row=2, column=0, sticky="ew", pady=(7, 0))
        position.columnconfigure(1, weight=1)
        self._camera_position_vars_v30 = [tk.DoubleVar(value=value) for value in self._camera_position_v30]
        for index, (label, variable) in enumerate(zip(("Position X", "Position Y", "Position Z"), self._camera_position_vars_v30)):
            ttk.Label(position, text=label).grid(row=index, column=0, sticky="w", padx=(0, 7), pady=2)
            slider = ttk.Scale(
                position,
                from_=-12.0,
                to=12.0,
                variable=variable,
                orient="horizontal",
                command=lambda _value: self._position_panel_changed_v30(),
            )
            slider.grid(row=index, column=1, sticky="ew", pady=2)
            slider.bind("<ButtonRelease-1>", self._position_panel_released_v30)
            ttk.Label(position, textvariable=variable, width=9).grid(row=index, column=2, sticky="e", padx=(6, 0))

        self._camera_move_step_var_v30 = tk.DoubleVar(value=self.DEFAULT_MOVE_STEP)
        ttk.Label(position, text="WASD step").grid(row=3, column=0, sticky="w", padx=(0, 7), pady=(5, 2))
        ttk.Scale(
            position,
            from_=0.01,
            to=0.75,
            variable=self._camera_move_step_var_v30,
            orient="horizontal",
        ).grid(row=3, column=1, sticky="ew", pady=(5, 2))
        ttk.Label(position, textvariable=self._camera_move_step_var_v30, width=9).grid(row=3, column=2, sticky="e", padx=(6, 0))
        self._camera_position_readout_v30 = tk.StringVar(value="")
        ttk.Label(
            position,
            textvariable=self._camera_position_readout_v30,
            wraplength=520,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(
            position,
            text="W/S move forward/backward in view space. A/D strafe. Left-drag looks without moving. Right-drag orbits the scene.",
            wraplength=520,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(3, 0))

    # ------------------------------------------------------------------
    # One camera state shared by wireframe, texture, playback, panel and saves
    # ------------------------------------------------------------------
    def _sync_renderer_camera_v30(self) -> None:
        renderer_v4.set_preview_camera_basis(camera_orbit.flatten_basis(self._camera_basis_v29))
        renderer_v4.set_preview_camera_position(self._camera_position_v30)
        if self.preview_background_var is not None and self.preview_background_var.get() in self.BACKGROUNDS:
            renderer_v4.set_preview_background(self.BACKGROUNDS[self.preview_background_var.get()][0])

    def _set_basis_v29(self, basis: camera_orbit.Basis, *, sync_panel: bool = True) -> None:
        super()._set_basis_v29(basis, sync_panel=sync_panel)
        renderer_v4.set_preview_camera_basis(camera_orbit.flatten_basis(self._camera_basis_v29))

    def _set_position_v30(self, position: camera_fly.Vec3, *, sync_panel: bool = True) -> None:
        self._camera_position_v30 = camera_fly.normalize_position(position)
        renderer_v4.set_preview_camera_position(self._camera_position_v30)
        if sync_panel:
            self._sync_camera_panel_v29()

    def _camera_tuple(self) -> tuple[float, ...]:
        return (*super()._camera_tuple(), *self._camera_position_v30)

    def _preview_background_changed_v25(self, *, render: bool = True) -> None:
        super()._preview_background_changed_v25(render=render)
        if self.preview_background_var is not None and self.preview_background_var.get() in self.BACKGROUNDS:
            renderer_v4.set_preview_background(self.BACKGROUNDS[self.preview_background_var.get()][0])

    def _apply_camera_v26(
        self,
        yaw: float,
        pitch: float,
        zoom: float,
        pan_x: float,
        pan_y: float,
        *,
        queue_render: bool = True,
    ) -> None:
        super()._apply_camera_v26(yaw, pitch, zoom, pan_x, pan_y, queue_render=False)
        self._set_position_v30(
            camera_fly.default_position(self._camera_basis_v29, self.DEFAULT_CAMERA_DISTANCE),
            sync_panel=False,
        )
        self._sync_camera_panel_v29()
        if queue_render and self._preview_mode == "textured" and self._textured_scene is not None:
            self._draw_interactive_wireframe()
            self._queue_camera_render(20)
        else:
            self._draw_wireframe()

    def _apply_saved_camera_v27(self, annotation: dict[str, Any]) -> None:
        super()._apply_saved_camera_v27(annotation)
        camera = annotation.get("camera")
        raw_position = camera.get("position") if isinstance(camera, dict) else None
        position = (
            camera_fly.normalize_position(raw_position)
            if isinstance(raw_position, (list, tuple)) and len(raw_position) == 3
            else camera_fly.default_position(self._camera_basis_v29, self.DEFAULT_CAMERA_DISTANCE)
        )
        self._set_position_v30(position, sync_panel=False)
        self._sync_renderer_camera_v30()
        self._sync_camera_panel_v29()
        self._draw_wireframe()

    def _sync_camera_panel_v29(self) -> None:
        super()._sync_camera_panel_v29()
        if not self._camera_position_vars_v30:
            return
        self._camera_panel_syncing_v29 = True
        try:
            for variable, value in zip(self._camera_position_vars_v30, self._camera_position_v30):
                variable.set(round(float(value), 4))
        finally:
            self._camera_panel_syncing_v29 = False
        self._update_camera_readout_v29()

    def _update_camera_readout_v29(self) -> None:
        if self._camera_readout_v29 is None:
            return
        heading, elevation = camera_orbit.heading_elevation(self._camera_basis_v29)
        x, y, z = self._camera_position_v30
        background = self.preview_background_var.get() if self.preview_background_var is not None else "Dark Gray"
        self._camera_readout_v29.set(
            f"View: horizontal {heading:.2f}°, vertical {elevation:.2f}°, position ({x:.3f}, {y:.3f}, {z:.3f}), "
            f"zoom {self._wire_zoom:.3f}, pan ({self._wire_pan_x:.3f}, {self._wire_pan_y:.3f}), background {background}."
        )
        if self._camera_position_readout_v30 is not None:
            step = self._movement_step_v30()
            self._camera_position_readout_v30.set(
                f"Normalized scene position: X {x:.4f}, Y {y:.4f}, Z {z:.4f}. Current movement step: {step:.4f}."
            )

    def _position_panel_changed_v30(self) -> None:
        if self._camera_panel_syncing_v29 or len(self._camera_position_vars_v30) != 3:
            return
        self._cancel_camera_work()
        self._camera_interacting = True
        self._set_position_v30(tuple(variable.get() for variable in self._camera_position_vars_v30), sync_panel=False)
        self._update_camera_readout_v29()
        self._draw_interactive_wireframe()

    def _position_panel_released_v30(self, _event: tk.Event) -> None:
        if self._camera_panel_syncing_v29:
            return
        self._camera_interacting = False
        self._finish_camera_interaction()

    # ------------------------------------------------------------------
    # WASD translation and left-drag look direction
    # ------------------------------------------------------------------
    def _movement_step_v30(self) -> float:
        if self._camera_move_step_var_v30 is None:
            return self.DEFAULT_MOVE_STEP
        return max(0.005, min(1.5, float(self._camera_move_step_var_v30.get())))

    def _move_camera_v30(self, *, forward: int = 0, strafe: int = 0) -> str:
        if not forward and not strafe:
            return "break"
        self._cancel_camera_work()
        self._camera_interacting = True
        step = self._movement_step_v30()
        self._set_position_v30(
            camera_fly.move_position(
                self._camera_position_v30,
                self._camera_basis_v29,
                forward=float(forward) * step,
                strafe=float(strafe) * step,
            )
        )
        self._draw_interactive_wireframe()
        action = "forward/backward" if forward else "strafe"
        self.visual_status.set(f"WASD {action} movement; normalized camera position {self._camera_position_v30}.")
        self._finish_discrete_camera_change_v27()
        return "break"

    def _left_look_start_v30(self, event: tk.Event) -> None:
        self.visual_canvas.focus_set()
        self._cancel_camera_work()
        self._camera_interacting = True
        self._left_look_last_v30 = (event.x, event.y)
        self._draw_interactive_wireframe()

    def _left_look_motion_v30(self, event: tk.Event) -> None:
        previous = self._left_look_last_v30
        if previous is None:
            return
        delta_x = event.x - previous[0]
        delta_y = event.y - previous[1]
        self._set_basis_v29(
            camera_orbit.orbit_camera_relative(
                self._camera_basis_v29,
                horizontal=delta_x * self.LOOK_RADIANS_PER_PIXEL,
                vertical=delta_y * self.LOOK_RADIANS_PER_PIXEL,
            )
        )
        self._left_look_last_v30 = (event.x, event.y)
        self._draw_interactive_wireframe()
        self.visual_status.set("Left-drag free look changed view direction only; camera position is unchanged.")

    def _left_look_release_v30(self, _event: tk.Event) -> None:
        self._left_look_last_v30 = None
        self._camera_interacting = False
        self._finish_camera_interaction()

    # ------------------------------------------------------------------
    # Existing orbit controls now rotate both camera position and orientation
    # around the scene center. Their screen-axis lock is retained.
    # ------------------------------------------------------------------
    def _orbit_nudge_v27(self, *, horizontal: int = 0, vertical: int = 0) -> str:
        if not horizontal and not vertical:
            return "break"
        self._cancel_camera_work()
        self._camera_interacting = True
        position, basis = camera_fly.orbit_around_origin(
            self._camera_position_v30,
            self._camera_basis_v29,
            horizontal=float(horizontal) * self.ORBIT_KEY_STEP,
            vertical=float(vertical) * self.ORBIT_KEY_STEP,
        )
        self._camera_position_v30 = position
        self._set_basis_v29(basis)
        self._sync_renderer_camera_v30()
        self._draw_interactive_wireframe()
        self.visual_status.set("Arrow control orbited camera position around the scene center.")
        self._finish_discrete_camera_change_v27()
        return "break"

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
        horizontal = delta_x * self.DRAG_RADIANS_PER_PIXEL if self._right_orbit_axis_v27 == "horizontal" else 0.0
        vertical = delta_y * self.DRAG_RADIANS_PER_PIXEL if self._right_orbit_axis_v27 == "vertical" else 0.0
        position, basis = camera_fly.orbit_around_origin(
            self._camera_position_v30,
            self._camera_basis_v29,
            horizontal=horizontal,
            vertical=vertical,
        )
        self._camera_position_v30 = position
        self._set_basis_v29(basis)
        self._sync_renderer_camera_v30()
        point = (event.x, event.y)
        self._right_orbit_last_v27 = point
        self._right_orbit_drag = point
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"{self._right_orbit_axis_v27.title()} orbit around scene center; release to texture."
        )

    def _fit_view(self) -> None:
        self._cancel_camera_work()
        self._camera_interacting = True
        self._set_position_v30(
            camera_fly.default_position(self._camera_basis_v29, self.DEFAULT_CAMERA_DISTANCE),
            sync_panel=False,
        )
        self._wire_zoom = 1.0
        self._wire_pan_x = 0.0
        self._wire_pan_y = 0.0
        self._sync_zoom_control()
        self._sync_camera_panel_v29()
        self._draw_interactive_wireframe()
        self.visual_status.set("Fit restored the camera to three scene radii from the asset center.")
        self._finish_discrete_camera_change_v27()

    # ------------------------------------------------------------------
    # Perspective wireframe matching the software texture renderer
    # ------------------------------------------------------------------
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
            self._style_camera_overlay_v27()
            return

        center, radius = camera_fly.scene_center_radius(geometry["corners"])
        camera_world = camera_fly.world_position(center, radius, self._camera_position_v30)
        focal = min(width, height) * 0.85 * self._wire_zoom
        near = max(radius * 0.005, 1e-7)
        screen_center_x = width / 2.0 + self._wire_pan_x * width
        screen_center_y = height / 2.0 + self._wire_pan_y * height
        limit = 1200 if self._camera_interacting else 6000
        faces, indices = geometry["samples"][limit]
        screen: dict[int, tuple[float, float, float] | None] = {}
        for index in indices:
            screen[index] = camera_fly.perspective_project(
                geometry["vertices"][index],
                self._camera_basis_v29,
                camera_world,
                focal_length=focal,
                screen_center_x=screen_center_x,
                screen_center_y=screen_center_y,
                near_plane=near,
            )

        displayed = 0
        clipped = 0
        _rgba, _canvas, text_color, line_color = self._background_values_v25()
        for face in faces:
            if not isinstance(face, (list, tuple)) or len(face) < 3:
                continue
            a, b, c = (int(face[0]), int(face[1]), int(face[2]))
            points = (screen.get(a), screen.get(b), screen.get(c))
            if any(point is None for point in points):
                clipped += 1
                continue
            first, second, third = points
            assert first is not None and second is not None and third is not None
            canvas.create_line(
                first[0], first[1], second[0], second[1],
                third[0], third[1], first[0], first[1],
                fill=line_color,
                width=1,
            )
            displayed += 1
        canvas.create_text(
            10,
            10,
            anchor="nw",
            fill=text_color,
            text=(
                f"Perspective wireframe {displayed:,}/{geometry['faces_total']:,} faces | {clipped:,} near-clipped | "
                "WASD move | left look | right orbit | middle pan | wheel zoom"
            ),
        )
        self._sync_renderer_camera_v30()
        self._style_camera_overlay_v27()

    # ------------------------------------------------------------------
    # Save normalized free-fly position with the established pose/view record
    # ------------------------------------------------------------------
    def _save_pose_view_for_row_v26(self, row: dict[str, Any]) -> None:
        project = self._require_project()
        if project is None:
            return
        animation = self.animation_name.get().strip() or INITIAL_POSE_NAME
        frame = max(0, int(self.animation_frame.get())) if animation != INITIAL_POSE_NAME else 0
        background = self.preview_background_var.get() if self.preview_background_var is not None else "Dark Gray"
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
            camera_basis=list(camera_orbit.flatten_basis(self._camera_basis_v29)),
            camera_position=list(self._camera_position_v30),
            persist=False,
        )
        self._refresh_annotation_marker_v26(row)
        self._visual_context_row = None
        self._visual_context_rows_v25 = []
        self._queue_annotation_persist_v24()
        self._sync_camera_panel_v29()
        self.visual_status.set(
            f"Saved {row['name']} pose, free-fly position, view direction, orbit basis, zoom, pan and background."
        )


def main() -> int:
    app = PublicFragmenterAppV30()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Thirty-third public GUI pass: full camera flight controls and compact review layout."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

import camera_fly_v1 as camera_fly
import camera_orbit_v1 as camera_orbit
from ccsf_gen1_pose_v5 import INITIAL_POSE_NAME
from fragmenter_public_gui_v32 import PublicFragmenterAppV32


class PublicFragmenterAppV33(PublicFragmenterAppV32):
    """Add camera-relative roll/elevation movement and simplify the review workspace."""

    DEFAULT_MOVEMENT_SENSITIVITY = 1.0
    DEFAULT_ROLL_STEP = math.radians(5.0)

    def __init__(self) -> None:
        self._movement_sensitivity_v33: tk.DoubleVar | None = None
        self._control_overlay_v33: tk.Label | None = None
        self._research_tab_v33: ttk.Frame | None = None
        self._preview_clump_label_v33: ttk.Label | None = None
        self._preview_clump_reload_v33: ttk.Button | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Full Camera Flight / Review Reports")

    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        self._bind_extended_flight_keys_v33()
        self._build_viewport_control_overlay_v33()
        self._move_audits_to_research_v33(parent)

    # ------------------------------------------------------------------
    # Camera / Pose: sliders only, no duplicate numeric/readout text.
    # ------------------------------------------------------------------
    def _build_camera_view_section_v32(self, parent: ttk.Frame) -> None:
        camera = ttk.LabelFrame(parent, text="Camera view", padding=7)
        camera.grid(row=0, column=0, sticky="ew")
        camera.columnconfigure(1, weight=1)
        variables = (
            ("Horizontal orbit", self._camera_heading_var_v29, -180.0, 180.0),
            ("Vertical orbit", self._camera_elevation_var_v29, -89.0, 89.0),
            ("Zoom", self._camera_zoom_var_v29, 0.15, 8.0),
            ("Pan X", self._camera_pan_x_var_v29, -1.0, 1.0),
            ("Pan Y", self._camera_pan_y_var_v29, -1.0, 1.0),
        )
        for index, (label, variable, minimum, maximum) in enumerate(variables):
            if variable is None:
                continue
            ttk.Label(camera, text=label).grid(row=index, column=0, sticky="w", padx=(0, 7), pady=2)
            scale = ttk.Scale(
                camera,
                from_=minimum,
                to=maximum,
                variable=variable,
                orient="horizontal",
                command=lambda _value: self._camera_panel_changed_v29(),
            )
            scale.grid(row=index, column=1, sticky="ew", pady=2)
            scale.bind("<ButtonRelease-1>", self._camera_panel_released_v29)

        actions = ttk.Frame(camera)
        actions.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(actions, text="Background").pack(side="left")
        background = ttk.Combobox(
            actions,
            textvariable=self.preview_background_var,
            values=tuple(self.BACKGROUNDS),
            state="readonly",
            width=12,
        )
        background.pack(side="left", padx=(6, 10))
        background.bind("<<ComboboxSelected>>", lambda _event: self._panel_background_changed_v29())
        ttk.Button(actions, text="Fit", command=self._fit_view).pack(side="left")
        ttk.Button(
            actions,
            text="Save Pose / Position",
            command=self._save_selected_pose_view_v26,
            style="Accent.TButton",
        ).pack(side="right")
        ttk.Button(
            actions,
            text="Reset to Default",
            command=self._reset_camera_pose_v33,
        ).pack(side="right", padx=(0, 6))

    def _build_free_fly_section_v32(self, parent: ttk.Frame) -> None:
        position = ttk.LabelFrame(parent, text="Free-fly position", padding=7)
        position.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        position.columnconfigure(1, weight=1)
        if len(self._camera_position_vars_v30) != 3:
            self._camera_position_vars_v30 = [tk.DoubleVar(value=value) for value in self._camera_position_v30]
        for index, (label, variable) in enumerate(
            zip(("Position X", "Position Y", "Position Z"), self._camera_position_vars_v30)
        ):
            ttk.Label(position, text=label).grid(row=index, column=0, sticky="w", padx=(0, 7), pady=2)
            scale = ttk.Scale(
                position,
                from_=-24.0,
                to=24.0,
                variable=variable,
                orient="horizontal",
                command=lambda _value: self._position_panel_changed_v30(),
            )
            scale.grid(row=index, column=1, sticky="ew", pady=2)
            scale.bind("<ButtonRelease-1>", self._position_panel_released_v30)

        self._movement_sensitivity_v33 = tk.DoubleVar(value=self.DEFAULT_MOVEMENT_SENSITIVITY)
        # Preserve the inherited variable name for code that displays or exports the
        # current movement setting. V33 interprets it as a multiplier, not a raw step.
        self._camera_move_step_var_v30 = self._movement_sensitivity_v33
        ttk.Label(position, text="Movement sensitivity").grid(
            row=3, column=0, sticky="w", padx=(0, 7), pady=(6, 2)
        )
        ttk.Scale(
            position,
            from_=0.1,
            to=5.0,
            variable=self._movement_sensitivity_v33,
            orient="horizontal",
        ).grid(row=3, column=1, sticky="ew", pady=(6, 2))

    def _build_scene_section_v32(self, _parent: ttk.Frame) -> None:
        # Preview Clump now lives in the compact animation strip above the details
        # notebook. Keeping a second selector here caused stale-widget regressions.
        self._scene_controls_v31 = None

    def _reset_camera_pose_v33(self) -> None:
        self._stop_animation()
        basis = camera_orbit.basis_from_yaw_pitch(-0.55, 0.35)
        self._set_basis_v29(basis, sync_panel=False)
        self._set_position_v30(
            camera_fly.default_position(basis, self.DEFAULT_CAMERA_DISTANCE),
            sync_panel=False,
        )
        self._wire_zoom = 1.0
        self._wire_pan_x = 0.0
        self._wire_pan_y = 0.0
        if self.preview_background_var is not None:
            self.preview_background_var.set("Dark Gray")
            self._preview_background_changed_v25(render=False)
        if hasattr(self, "animation_name"):
            self.animation_name.set(INITIAL_POSE_NAME)
            self._configure_animation_range()
            self.animation_frame.set(0)
            self.animation_frame_scale.set(0)
            self._update_animation_frame_label(0)
        self._sync_renderer_camera_v30()
        self._sync_camera_panel_v29()
        self._draw_interactive_wireframe()
        self.visual_status.set("Reset current pose and camera to defaults. Use Save Pose / Position to retain it.")
        self.after_idle(lambda: self._wireframe_load(allow_auto_texture=True))

    # ------------------------------------------------------------------
    # W/S forward/back, A/D strafe, Z/X local up/down and Q/E local roll.
    # ------------------------------------------------------------------
    def _bind_extended_flight_keys_v33(self) -> None:
        for key, vertical in (("z", 1), ("Z", 1), ("x", -1), ("X", -1)):
            self.visual_canvas.bind(
                f"<KeyPress-{key}>",
                lambda _event, value=vertical: self._move_camera_v30(vertical=value),
            )
        for key, direction in (("q", -1), ("Q", -1), ("e", 1), ("E", 1)):
            self.visual_canvas.bind(
                f"<KeyPress-{key}>",
                lambda _event, value=direction: self._roll_camera_v33(value),
            )

    def _movement_sensitivity_value_v33(self) -> float:
        variable = self._movement_sensitivity_v33
        if variable is None:
            return self.DEFAULT_MOVEMENT_SENSITIVITY
        return max(0.1, min(5.0, float(variable.get())))

    def _movement_step_v30(self) -> float:
        return self.DEFAULT_MOVE_STEP * self._movement_sensitivity_value_v33()

    def _roll_step_v33(self) -> float:
        return self.DEFAULT_ROLL_STEP * self._movement_sensitivity_value_v33()

    def _move_camera_v30(self, *, forward: int = 0, strafe: int = 0, vertical: int = 0) -> str:
        if not forward and not strafe and not vertical:
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
                vertical=float(vertical) * step,
            )
        )
        self._draw_interactive_wireframe()
        if vertical:
            action = "local up/down"
        elif forward:
            action = "forward/backward"
        else:
            action = "strafe"
        self.visual_status.set(f"Camera {action} movement at sensitivity {self._movement_sensitivity_value_v33():.2f}.")
        self._finish_discrete_camera_change_v27()
        return "break"

    def _roll_camera_v33(self, direction: int) -> str:
        if not direction:
            return "break"
        self._cancel_camera_work()
        self._camera_interacting = True
        right, up, forward = camera_orbit.orthonormalize(self._camera_basis_v29)
        angle = float(direction) * self._roll_step_v33()
        rolled = camera_orbit.orthonormalize(
            (
                camera_orbit.rotate_vector(right, forward, angle),
                camera_orbit.rotate_vector(up, forward, angle),
                forward,
            )
        )
        self._set_basis_v29(rolled)
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"Camera barrel roll {'right' if direction > 0 else 'left'} at sensitivity "
            f"{self._movement_sensitivity_value_v33():.2f}."
        )
        self._finish_discrete_camera_change_v27()
        return "break"

    # ------------------------------------------------------------------
    # Preview clump occupies the former top animation-selector position. Animation
    # moves to the left side of the compact frame slider below it.
    # ------------------------------------------------------------------
    def _compact_animation_controls_v32(self) -> None:
        bar = getattr(self, "animation_combo", None)
        bar = bar.master if bar is not None else None
        if bar is None:
            return
        bar.columnconfigure(1, weight=1)
        bar.columnconfigure(2, weight=2)

        pose_label = None
        frame_title = None
        frame_counter = None
        apply_button = None
        textured_toggle = None
        low_res_label = None
        for child in bar.winfo_children():
            try:
                text = str(child.cget("text"))
            except tk.TclError:
                continue
            if isinstance(child, ttk.Label) and text in {"Pose / Animation", "Animation"}:
                pose_label = child
            elif isinstance(child, ttk.Label) and text == "Frame":
                frame_title = child
            elif isinstance(child, ttk.Button) and text in {"Apply", "Apply Frame"}:
                apply_button = child
            elif isinstance(child, ttk.Checkbutton) and text == "Textured playback":
                textured_toggle = child
            elif isinstance(child, ttk.Label) and "frame-skipping" in text:
                low_res_label = child
            elif isinstance(child, ttk.Label) and str(child.cget("textvariable")) == str(self.animation_frame_label):
                frame_counter = child
            elif text in {"Camera", "Front", "Side", "Top", "Reset"}:
                child.grid_remove()

        old_combo = getattr(self, "preview_clump_combo", None)
        if self._widget_alive_v31(old_combo):
            try:
                old_combo.destroy()
            except tk.TclError:
                pass
        self._preview_clump_label_v33 = ttk.Label(bar, text="Preview Clump")
        self._preview_clump_label_v33.grid(row=0, column=0, sticky="w")
        self.preview_clump_combo = ttk.Combobox(
            bar,
            textvariable=self.preview_clump_name,
            values=tuple(self._preview_clumps_by_label),
            state="readonly",
            width=34,
        )
        self.preview_clump_combo.grid(row=0, column=1, columnspan=4, sticky="ew", padx=(5, 8))
        self.preview_clump_combo.bind("<<ComboboxSelected>>", lambda _event: self._preview_clump_selected())
        self._preview_clump_reload_v33 = ttk.Button(
            bar,
            text="Reload",
            command=self._reload_focused_contents_v31,
        )
        self._preview_clump_reload_v33.grid(row=0, column=5, padx=(0, 5))

        if pose_label is not None:
            pose_label.configure(text="Animation")
            pose_label.grid_configure(row=1, column=0, sticky="w", pady=(3, 0))
        self.animation_combo.grid_configure(row=1, column=1, columnspan=1, sticky="ew", padx=(5, 7), pady=(3, 0))
        self.animation_frame_scale.grid_configure(row=1, column=2, columnspan=4, sticky="ew", padx=(0, 6), pady=(3, 0))
        self.animation_play_button.grid_configure(row=0, column=6, padx=(4, 0))
        if apply_button is not None:
            apply_button.grid_configure(row=1, column=6, padx=(4, 0), pady=(3, 0))
        if textured_toggle is not None:
            textured_toggle.grid_configure(row=0, column=7, padx=(8, 0), sticky="w")
        for widget in (frame_title, frame_counter, low_res_label):
            if widget is not None:
                widget.grid_remove()
        if self.textured_animation_var is not None:
            self.textured_animation_var.set(True)

    # ------------------------------------------------------------------
    # Controls are explained once in the viewport instead of beneath sliders.
    # ------------------------------------------------------------------
    def _build_viewport_control_overlay_v33(self) -> None:
        _rgba, canvas_color, text_color, _line = self._background_values_v25()
        self._control_overlay_v33 = tk.Label(
            self.visual_canvas,
            text=(
                "W/S forward/back   A/D strafe   Z/X up/down   Q/E roll\n"
                "Left-drag look   Right-drag orbit   Middle-drag pan   Wheel zoom"
            ),
            justify="left",
            anchor="nw",
            padx=4,
            pady=3,
            borderwidth=0,
            highlightthickness=0,
            background=canvas_color,
            foreground=text_color,
            font=("Segoe UI", 8),
        )
        self._control_overlay_v33.place(x=8, y=8, anchor="nw")
        self._control_overlay_v33.lift()

    def _style_control_overlay_v33(self) -> None:
        overlay = self._control_overlay_v33
        if overlay is None or not self._widget_alive_v31(overlay):
            return
        _rgba, canvas_color, text_color, _line = self._background_values_v25()
        overlay.configure(background=canvas_color, foreground=text_color)
        overlay.lift()

    def _preview_background_changed_v25(self, *, render: bool = True) -> None:
        super()._preview_background_changed_v25(render=render)
        self._style_control_overlay_v33()

    def _draw_interactive_wireframe(self) -> None:
        super()._draw_interactive_wireframe()
        for item in self.visual_canvas.find_all():
            if self.visual_canvas.type(item) != "text":
                continue
            try:
                text = str(self.visual_canvas.itemcget(item, "text"))
            except tk.TclError:
                continue
            marker = " | WASD move"
            if marker in text:
                self.visual_canvas.itemconfigure(item, text=text.split(marker, 1)[0])
        self._style_control_overlay_v33()

    def _show_png_on_visual_canvas(self, path) -> None:
        super()._show_png_on_visual_canvas(path)
        self._style_control_overlay_v33()

    # ------------------------------------------------------------------
    # Audit tools belong in Research, not the day-to-day 3D review toolbar.
    # ------------------------------------------------------------------
    def _move_audits_to_research_v33(self, visual_parent: tk.Misc) -> None:
        def remove_buttons(widget: tk.Misc) -> None:
            try:
                children = widget.winfo_children()
            except tk.TclError:
                return
            for child in children:
                if isinstance(child, ttk.Button):
                    try:
                        text = str(child.cget("text"))
                    except tk.TclError:
                        text = ""
                    if text in {"Audit X-Series", "Texture Audit"}:
                        child.destroy()
                        continue
                remove_buttons(child)

        remove_buttons(visual_parent)
        notebook = self.notebook
        for tab_id in notebook.tabs():
            if str(notebook.tab(tab_id, "text")) == "Research":
                candidate = notebook.nametowidget(tab_id)
                if isinstance(candidate, ttk.Frame):
                    self._research_tab_v33 = candidate
                return
        research = ttk.Frame(notebook, padding=8)
        notebook.add(research, text="Research")
        self.tabs["Research"] = research
        self._research_tab_v33 = research
        research.columnconfigure(0, weight=1)
        ttk.Label(research, text="Visual format research", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            research,
            text=(
                "Generate evidence packages for extraction coverage and texture/material mapping. "
                "These tools write into the active project's reports folder."
            ),
            wraplength=900,
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))
        actions = ttk.Frame(research)
        actions.grid(row=2, column=0, sticky="w")
        ttk.Button(actions, text="Audit X-Series", command=self._audit_x_series_v25).pack(side="left")
        ttk.Button(actions, text="Texture Audit", command=self._visual_texture_audit).pack(side="left", padx=(7, 0))


def main() -> int:
    app = PublicFragmenterAppV33()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

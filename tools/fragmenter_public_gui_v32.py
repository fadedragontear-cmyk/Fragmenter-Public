#!/usr/bin/env python3
"""Thirty-second public GUI pass: visible notes and compact textured animation review."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from fragmenter_public_gui_v31 import PublicFragmenterAppV31


class PublicFragmenterAppV32(PublicFragmenterAppV31):
    """Separate notes from camera controls and keep animation review visible."""

    def __init__(self) -> None:
        self._notes_tab_v32: ttk.Frame | None = None
        self._notes_tab_id_v32: str | None = None
        self._notes_status_v32: tk.StringVar | None = None
        self._camera_scroll_canvas_v32: tk.Canvas | None = None
        self._camera_scroll_inner_v32: ttk.Frame | None = None
        self._texture_mapping_sink_v32: tk.Text | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Notes / Scrollable Camera / Textured Animation")

    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        self._rebuild_scrollable_camera_panel_v32()
        self._build_notes_tab_v32()
        self._compact_animation_controls_v32()
        self._sync_camera_panel_v29()

    # ------------------------------------------------------------------
    # Camera/Pose owns camera controls only and scrolls vertically.
    # ------------------------------------------------------------------
    def _rebuild_scrollable_camera_panel_v32(self) -> None:
        notebook = self._visual_details_notebook
        target_id = self._camera_panel_tab_v29
        if notebook is None or target_id is None:
            return
        target = notebook.nametowidget(target_id)
        if not isinstance(target, ttk.Frame):
            return
        for child in target.winfo_children():
            child.destroy()
        target.columnconfigure(0, weight=1)
        target.rowconfigure(0, weight=1)

        canvas = tk.Canvas(target, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(target, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas, padding=6)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.columnconfigure(0, weight=1)

        def inner_changed(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def canvas_changed(event: tk.Event) -> None:
            canvas.itemconfigure(window, width=max(1, event.width))

        inner.bind("<Configure>", inner_changed)
        canvas.bind("<Configure>", canvas_changed)
        self._camera_scroll_canvas_v32 = canvas
        self._camera_scroll_inner_v32 = inner
        self._camera_panel_frame_v29 = inner

        self._build_camera_view_section_v32(inner)
        self._build_free_fly_section_v32(inner)
        self._build_scene_section_v32(inner)
        self.after_idle(lambda: canvas.configure(scrollregion=canvas.bbox("all")))

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
            ttk.Label(camera, textvariable=variable, width=9).grid(row=index, column=2, sticky="e", padx=(6, 0))

        actions = ttk.Frame(camera)
        actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
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
        if self._camera_readout_v29 is not None:
            ttk.Label(camera, textvariable=self._camera_readout_v29, wraplength=520).grid(
                row=6, column=0, columnspan=3, sticky="w", pady=(7, 0)
            )
        if self._pose_readout_v29 is not None:
            ttk.Label(camera, textvariable=self._pose_readout_v29, wraplength=520).grid(
                row=7, column=0, columnspan=3, sticky="w", pady=(2, 0)
            )

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
                from_=-12.0,
                to=12.0,
                variable=variable,
                orient="horizontal",
                command=lambda _value: self._position_panel_changed_v30(),
            )
            scale.grid(row=index, column=1, sticky="ew", pady=2)
            scale.bind("<ButtonRelease-1>", self._position_panel_released_v30)
            ttk.Label(position, textvariable=variable, width=9).grid(row=index, column=2, sticky="e", padx=(6, 0))
        if self._camera_move_step_var_v30 is None:
            self._camera_move_step_var_v30 = tk.DoubleVar(value=self.DEFAULT_MOVE_STEP)
        ttk.Label(position, text="WASD step").grid(row=3, column=0, sticky="w", padx=(0, 7), pady=(5, 2))
        ttk.Scale(
            position,
            from_=0.01,
            to=0.75,
            variable=self._camera_move_step_var_v30,
            orient="horizontal",
        ).grid(row=3, column=1, sticky="ew", pady=(5, 2))
        ttk.Label(position, textvariable=self._camera_move_step_var_v30, width=9).grid(
            row=3, column=2, sticky="e", padx=(6, 0)
        )
        if self._camera_position_readout_v30 is not None:
            ttk.Label(position, textvariable=self._camera_position_readout_v30, wraplength=520).grid(
                row=4, column=0, columnspan=3, sticky="w", pady=(6, 0)
            )
        ttk.Label(
            position,
            text="W/S move forward/backward. A/D strafe. Left-drag looks. Right-drag orbits. Middle-drag pans.",
            wraplength=520,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(3, 0))

    def _build_scene_section_v32(self, parent: ttk.Frame) -> None:
        scene = ttk.LabelFrame(parent, text="Scene assembly / CCSF", padding=7)
        scene.grid(row=2, column=0, sticky="ew", pady=(7, 0))
        scene.columnconfigure(1, weight=1)
        self._scene_controls_v31 = scene
        ttk.Label(scene, text="Preview clump").grid(row=0, column=0, sticky="w", padx=(0, 7))
        self.preview_clump_combo = ttk.Combobox(
            scene,
            textvariable=self.preview_clump_name,
            values=tuple(self._preview_clumps_by_label),
            state="readonly",
            width=42,
        )
        self.preview_clump_combo.grid(row=0, column=1, sticky="ew")
        self.preview_clump_combo.bind("<<ComboboxSelected>>", lambda _event: self._preview_clump_selected())
        ttk.Button(scene, text="Reload Contents", command=self._reload_focused_contents_v31).grid(
            row=0, column=2, padx=(7, 0)
        )
        ttk.Label(scene, textvariable=self.preview_clump_status, wraplength=520).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(5, 0)
        )

    # ------------------------------------------------------------------
    # Texture Mapping becomes a dedicated notes workspace.
    # ------------------------------------------------------------------
    def _build_notes_tab_v32(self) -> None:
        notebook = self._visual_details_notebook
        if notebook is None:
            return
        target: ttk.Frame | None = None
        target_id: str | None = None
        for tab_id in notebook.tabs():
            if str(notebook.tab(tab_id, "text")) == "Texture Mapping":
                target_id = str(tab_id)
                candidate = notebook.nametowidget(tab_id)
                if isinstance(candidate, ttk.Frame):
                    target = candidate
                break
        if target is None or target_id is None:
            target = ttk.Frame(notebook, padding=7)
            notebook.add(target, text="Notes")
            target_id = str(target)
        else:
            for child in target.winfo_children():
                child.destroy()
            notebook.tab(target_id, text="Notes")
        target.columnconfigure(0, weight=1)
        target.rowconfigure(1, weight=1)
        self._notes_tab_v32 = target
        self._notes_tab_id_v32 = target_id

        self._note_asset_v29 = self._note_asset_v29 or tk.StringVar(value="No asset selected")
        ttk.Label(target, textvariable=self._note_asset_v29).grid(row=0, column=0, sticky="w", pady=(0, 5))
        editor = tk.Text(target, wrap="word", undo=True)
        scroll = ttk.Scrollbar(target, orient="vertical", command=editor.yview)
        editor.configure(yscrollcommand=scroll.set)
        editor.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        editor.bind("<<Modified>>", self._note_modified_v29)
        editor.bind("<Control-Return>", self._save_notes_from_key_v32)
        self._note_text_v29 = editor

        actions = ttk.Frame(target)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._notes_status_v32 = tk.StringVar(value="Notes save to the durable review record and classification export.")
        ttk.Label(actions, textvariable=self._notes_status_v32).pack(side="left")
        ttk.Button(actions, text="Save Notes", command=self._save_notes_v32, style="Accent.TButton").pack(side="right")

        # Retain a live but hidden sink for legacy texture-mapping evidence writers.
        # They must not overwrite the user-facing Notes editor or call a destroyed Tk widget.
        self._texture_mapping_sink_v32 = tk.Text(target, height=1, width=1)
        self.texture_mapping_text = self._texture_mapping_sink_v32
        self.texture_audit_text = self._texture_mapping_sink_v32
        self._load_note_panel_v29(self._selected_visual_row())

    def _save_notes_from_key_v32(self, _event: tk.Event) -> str:
        self._save_notes_v32()
        return "break"

    def _save_notes_v32(self) -> None:
        self._save_notes_v29()
        row = self._selected_visual_row()
        if self._notes_status_v32 is not None and row is not None:
            self._notes_status_v32.set(f"Saved notes for {row['name']}.")

    def _edit_context_notes(self) -> None:
        row = self._selected_visual_row()
        self._load_note_panel_v29(row)
        if self._notes_tab_id_v32 is not None and self._visual_details_notebook is not None:
            self._visual_details_notebook.select(self._notes_tab_id_v32)
        if self._note_text_v29 is not None:
            self._note_text_v29.focus_set()

    # ------------------------------------------------------------------
    # Compact two-row animation strip. Textured playback is visible and enabled by
    # default; inherited v20 playback renders each decoded frame into the 3D viewport.
    # ------------------------------------------------------------------
    def _compact_animation_controls_v32(self) -> None:
        bar = getattr(self, "animation_combo", None)
        bar = bar.master if bar is not None else None
        if bar is None:
            return
        bar.columnconfigure(1, weight=1)
        bar.columnconfigure(3, weight=0)
        self.animation_combo.grid_configure(row=0, column=1, columnspan=3, sticky="ew", padx=(5, 8))
        self.animation_play_button.grid_configure(row=0, column=5, padx=(4, 0))
        self.animation_frame_scale.grid_configure(row=1, column=1, columnspan=4, sticky="ew", padx=(5, 6), pady=(3, 0))

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
            if isinstance(child, ttk.Label) and text == "Frame":
                frame_title = child
            elif isinstance(child, ttk.Button) and text in {"Apply", "Apply Frame"}:
                apply_button = child
            elif isinstance(child, ttk.Checkbutton) and text == "Textured playback":
                textured_toggle = child
            elif isinstance(child, ttk.Label) and "frame-skipping" in text:
                low_res_label = child
            elif isinstance(child, ttk.Label) and str(child.cget("textvariable")) == str(self.animation_frame_label):
                frame_counter = child
        if frame_title is not None:
            frame_title.grid_configure(row=1, column=0, sticky="w", pady=(3, 0))
        if frame_counter is not None:
            frame_counter.grid_configure(row=1, column=5, sticky="w", pady=(3, 0))
        if apply_button is not None:
            apply_button.grid_configure(row=1, column=6, padx=(4, 0), pady=(3, 0))
        if textured_toggle is not None:
            textured_toggle.grid_configure(row=0, column=6, padx=(8, 0), sticky="w")
        if low_res_label is not None:
            low_res_label.grid_configure(row=0, column=7, padx=(4, 0), sticky="w")
        if self.textured_animation_var is not None:
            self.textured_animation_var.set(True)


def main() -> int:
    app = PublicFragmenterAppV32()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Thirteenth public GUI pass: 3D-first scene, texture and pose workbench."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import ccsf_texture_audit_v1 as texture_audit_v1
import ccsf_textured_scene_v8 as scene_v8
import fragmenter_public_gui_v5 as gui_v5
import fragmenter_public_gui_v7 as gui_v7
import fragmenter_public_gui_v8 as gui_v8
import fragmenter_public_gui_v11 as gui_v11
import fragmenter_public_gui_v12 as gui_v12
from asset_classifier_v2 import CATEGORY_ORDER
from ccsf_asset_tree_v1 import inspect_ccsf_contents
from ccsf_gen1_pose_v5 import INITIAL_POSE_NAME
from fragmenter_public_gui import _json_text
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v12 import PublicFragmenterAppV12
from project_sound_v7 import analyze_or_extract_sound_item, build_project_sound_library

# Route every inherited preview path through the same whole-file scene authority.
gui_v5.load_textured_scene = scene_v8.load_textured_scene
gui_v5.load_posed_wireframe_payload = scene_v8.load_posed_wireframe_payload
gui_v5.render_textured_scene = scene_v8.render_textured_scene
gui_v5.export_scene_textures = scene_v8.export_scene_textures
gui_v5.build_project_sound_library = build_project_sound_library
gui_v5.analyze_or_extract_sound_item = analyze_or_extract_sound_item
gui_v7.scene_v5 = scene_v8
gui_v8.scene_v6 = scene_v8
gui_v8.load_clump_wireframe_payload = scene_v8.load_posed_wireframe_payload
gui_v11.scene_v7 = scene_v8
gui_v11.build_project_sound_library = build_project_sound_library
gui_v12.build_project_sound_library = build_project_sound_library
texture_audit_v1.load_textured_scene = scene_v8.load_textured_scene


class PublicFragmenterAppV13(PublicFragmenterAppV12):
    """Prioritize complete scene assembly, texture evidence and explicit poses."""

    def __init__(self) -> None:
        self._visual_outer_paned: ttk.Panedwindow | None = None
        self._visual_left_paned: ttk.Panedwindow | None = None
        self.texture_mapping_text: tk.Text | None = None
        self.scene_assembly_mode: tk.StringVar | None = None
        self._texture_load_generation = 0
        self._progressive_render_generation = 0
        self._settled_render_after: str | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — 3D / Texture Focus")
        self._auto_texture_limit = 30_000
        self.after_idle(self._restore_v13_visual_layout)

    # ------------------------------------------------------------------
    # 3D-first layout
    # ------------------------------------------------------------------
    def _build_visual(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.visual_search = tk.StringVar()
        ttk.Label(controls, text="Search").pack(side="left")
        ttk.Entry(controls, textvariable=self.visual_search, width=30).pack(side="left", padx=(6, 8))
        ttk.Label(controls, text="Category").pack(side="left")
        self.visual_category = tk.StringVar(value="All")
        self.visual_category_combo = ttk.Combobox(
            controls,
            textvariable=self.visual_category,
            values=("All", *CATEGORY_ORDER),
            state="readonly",
            width=28,
        )
        self.visual_category_combo.pack(side="left", padx=(6, 8))
        self.visual_category_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_visual_assets())
        ttk.Button(controls, text="Refresh Assets", command=self._refresh_visual_assets).pack(side="left")
        ttk.Button(controls, text="Texture Mapping Audit", command=self._visual_texture_audit).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Export Resolved Textures", command=self._export_selected_textures).pack(side="left", padx=(6, 0))
        ttk.Label(
            controls,
            text="Whole File includes every parsed clump and unclumped Object→Model instance.",
        ).pack(side="right")

        status = ttk.Frame(parent)
        status.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        status.columnconfigure(1, weight=1)
        self.visual_status = tk.StringVar(value="No project loaded")
        ttk.Label(status, textvariable=self.visual_status).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.visual_progress = ttk.Progressbar(status, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar")
        self.visual_progress.grid(row=0, column=1, sticky="ew")

        outer = ttk.Panedwindow(parent, orient="horizontal")
        outer.grid(row=2, column=0, sticky="nsew")
        self._visual_outer_paned = outer

        left = ttk.Panedwindow(outer, orient="vertical")
        self._visual_left_paned = left
        outer.add(left, weight=2)

        tree_frame = ttk.LabelFrame(left, text="Asset library", padding=4)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.visual_tree = ttk.Treeview(tree_frame, columns=("kind", "size", "path"), show="tree headings")
        for column, title, width in (
            ("#0", "Asset", 230),
            ("kind", "Type", 130),
            ("size", "Size", 85),
            ("path", "Project-relative path", 320),
        ):
            self.visual_tree.heading(column, text=title, command=lambda key=column: self._sort_visual_tree(key))
            self.visual_tree.column(column, width=width, stretch=column in {"#0", "path"})
        tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.visual_tree.yview)
        tree_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.visual_tree.xview)
        self.visual_tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
        self.visual_tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree_x.grid(row=1, column=0, sticky="ew")
        left.add(tree_frame, weight=3)

        details = ttk.Notebook(left)
        self._visual_details_notebook = details
        left.add(details, weight=2)

        details_tab = ttk.Frame(details)
        details_tab.rowconfigure(0, weight=1)
        details_tab.columnconfigure(0, weight=1)
        self.visual_details = tk.Text(details_tab, wrap="word")
        details_y = ttk.Scrollbar(details_tab, orient="vertical", command=self.visual_details.yview)
        self.visual_details.configure(yscrollcommand=details_y.set)
        self.visual_details.grid(row=0, column=0, sticky="nsew")
        details_y.grid(row=0, column=1, sticky="ns")
        details.add(details_tab, text="Scene Details")

        contents_tab = ttk.Frame(details)
        contents_tab.rowconfigure(0, weight=1)
        contents_tab.columnconfigure(0, weight=1)
        self.ccsf_contents_tree = ttk.Treeview(contents_tab, columns=("kind",), show="tree headings")
        self.ccsf_contents_tree.heading("#0", text="CCSF file contents")
        self.ccsf_contents_tree.heading("kind", text="Kind")
        self.ccsf_contents_tree.column("#0", width=520, stretch=True)
        self.ccsf_contents_tree.column("kind", width=140, stretch=False)
        contents_y = ttk.Scrollbar(contents_tab, orient="vertical", command=self.ccsf_contents_tree.yview)
        self.ccsf_contents_tree.configure(yscrollcommand=contents_y.set)
        self.ccsf_contents_tree.grid(row=0, column=0, sticky="nsew")
        contents_y.grid(row=0, column=1, sticky="ns")
        self.ccsf_contents_tree.bind("<<TreeviewSelect>>", lambda _event: self._ccsf_contents_selected())
        details.add(contents_tab, text="CCSF Contents")

        mapping_tab = ttk.Frame(details)
        mapping_tab.rowconfigure(0, weight=1)
        mapping_tab.columnconfigure(0, weight=1)
        self.texture_mapping_text = tk.Text(mapping_tab, wrap="word")
        mapping_y = ttk.Scrollbar(mapping_tab, orient="vertical", command=self.texture_mapping_text.yview)
        mapping_x = ttk.Scrollbar(mapping_tab, orient="horizontal", command=self.texture_mapping_text.xview)
        self.texture_mapping_text.configure(yscrollcommand=mapping_y.set, xscrollcommand=mapping_x.set)
        self.texture_mapping_text.grid(row=0, column=0, sticky="nsew")
        mapping_y.grid(row=0, column=1, sticky="ns")
        mapping_x.grid(row=1, column=0, sticky="ew")
        details.add(mapping_tab, text="Texture Mapping")
        self.texture_audit_tab = mapping_tab
        self.texture_audit_text = self.texture_mapping_text

        adjustments_tab = ttk.Frame(details, padding=6)
        adjustments_tab.columnconfigure(0, weight=1)
        details.add(adjustments_tab, text="Preview Adjustments")
        self._build_slider_adjustments(adjustments_tab)

        preview = ttk.LabelFrame(outer, text="Complete 3D scene preview", padding=4)
        preview.rowconfigure(1, weight=1)
        preview.columnconfigure(0, weight=1)
        outer.add(preview, weight=5)
        self._build_preview_toolbar(preview)

        self.visual_canvas = tk.Canvas(preview, background="#101820", highlightthickness=0)
        self.visual_canvas.grid(row=1, column=0, sticky="nsew")
        self.visual_canvas.create_text(20, 20, anchor="nw", fill="#BFD7EA", text="Select an asset to assemble its complete scene.")
        self.visual_canvas.bind("<Configure>", self._visual_canvas_resized_v6)
        self.visual_canvas.bind("<ButtonPress-1>", self._wire_start_drag)
        self.visual_canvas.bind("<B1-Motion>", self._wire_drag_motion)
        self.visual_canvas.bind("<ButtonRelease-1>", self._wire_release_drag)
        self.visual_canvas.bind("<ButtonPress-2>", self._wire_start_pan)
        self.visual_canvas.bind("<B2-Motion>", self._wire_pan_motion)
        self.visual_canvas.bind("<ButtonRelease-2>", self._wire_release_pan)
        self.visual_canvas.bind("<ButtonPress-3>", self._wire_start_pan)
        self.visual_canvas.bind("<B3-Motion>", self._wire_pan_motion)
        self.visual_canvas.bind("<ButtonRelease-3>", self._wire_release_pan)
        self.visual_canvas.bind("<MouseWheel>", self._wire_mousewheel)
        self.visual_canvas.bind("<Double-1>", lambda _event: self._fit_view())

        self._build_animation_controls(preview)
        self._build_camera_controls(preview)

        self.visual_payloads: dict[str, dict[str, Any]] = {}
        self._visual_search_after = None
        self.visual_search.trace_add("write", lambda *_: self._debounce_visual_refresh())
        self.visual_tree.bind("<<TreeviewSelect>>", self._visual_asset_selected)
        self.visual_tree.bind("<Double-1>", lambda _event: self._wireframe_load(allow_auto_texture=True))
        self.after_idle(self._restore_v13_visual_layout)

    def _build_preview_toolbar(self, preview: ttk.LabelFrame) -> None:
        bar = ttk.Frame(preview, padding=(3, 2))
        bar.grid(row=0, column=0, sticky="ew")
        self.preview_wireframe_var = tk.BooleanVar(value=True)
        self.preview_textured_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Wireframe", variable=self.preview_wireframe_var, command=self._select_wireframe_mode).pack(side="left")
        ttk.Checkbutton(bar, text="Textured", variable=self.preview_textured_var, command=self._select_textured_mode).pack(side="left", padx=(8, 0))
        self.auto_texture_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Auto", variable=self.auto_texture_var, command=self._auto_texture_toggled).pack(side="left", padx=(10, 0))
        ttk.Label(bar, text="Quality").pack(side="left", padx=(10, 4))
        self.preview_quality_var = tk.StringVar(value="Balanced")
        quality = ttk.Combobox(bar, textvariable=self.preview_quality_var, values=("Fast", "Balanced", "Full"), state="readonly", width=9)
        quality.pack(side="left")
        quality.bind("<<ComboboxSelected>>", lambda _event: self._preview_quality_changed())
        ttk.Label(bar, text="Assembly").pack(side="left", padx=(12, 4))
        self.scene_assembly_mode = tk.StringVar(value="Whole File")
        assembly = ttk.Combobox(bar, textvariable=self.scene_assembly_mode, values=("Whole File", "Selected Clump"), state="readonly", width=16)
        assembly.pack(side="left")
        assembly.bind("<<ComboboxSelected>>", lambda _event: self._assembly_changed())
        ttk.Label(bar, text="Fast preview appears first; full-quality render replaces it.").pack(side="right")

    def _build_animation_controls(self, preview: ttk.LabelFrame) -> None:
        animation = ttk.Frame(preview, padding=(3, 3))
        animation.grid(row=2, column=0, sticky="ew")
        animation.columnconfigure(3, weight=1)
        self.animation_name = tk.StringVar(value=INITIAL_POSE_NAME)
        ttk.Label(animation, text="Pose / Animation").grid(row=0, column=0, sticky="w")
        self.animation_combo = ttk.Combobox(animation, textvariable=self.animation_name, values=(INITIAL_POSE_NAME,), state="readonly", width=28)
        self.animation_combo.grid(row=0, column=1, sticky="w", padx=(5, 10))
        self.animation_combo.bind("<<ComboboxSelected>>", lambda _event: self._animation_selected())
        ttk.Label(animation, text="Frame").grid(row=0, column=2, sticky="w")
        self.animation_frame = tk.IntVar(value=0)
        self.animation_frame_scale = ttk.Scale(animation, from_=0, to=0, orient="horizontal", command=self._animation_scale_changed)
        self.animation_frame_scale.grid(row=0, column=3, sticky="ew", padx=(5, 6))
        self.animation_frame_scale.bind("<ButtonRelease-1>", lambda _event: self._apply_animation_frame())
        self.animation_frame_label = tk.StringVar(value="0 / 0")
        ttk.Label(animation, textvariable=self.animation_frame_label, width=12).grid(row=0, column=4, sticky="w")
        ttk.Button(animation, text="Apply", command=self._apply_animation_frame).grid(row=0, column=5, padx=(4, 0))
        self.animation_play_button = ttk.Button(animation, text="Play", command=self._toggle_animation_play, style="Accent.TButton")
        self.animation_play_button.grid(row=0, column=6, padx=(6, 0))

    def _build_camera_controls(self, preview: ttk.LabelFrame) -> None:
        camera = ttk.Frame(preview, padding=(3, 3))
        camera.grid(row=3, column=0, sticky="ew")
        ttk.Label(camera, text="Camera").pack(side="left")
        for label, command in (("Front", self._camera_front), ("Side", self._camera_side), ("Top", self._camera_top), ("Reset", self._camera_reset), ("Fit", self._fit_view)):
            ttk.Button(camera, text=label, command=command).pack(side="left", padx=(4, 0))
        ttk.Label(camera, text="Zoom").pack(side="left", padx=(12, 4))
        self.preview_zoom_var = tk.DoubleVar(value=1.25)
        ttk.Scale(camera, from_=0.15, to=8.0, orient="horizontal", length=170, variable=self.preview_zoom_var, command=self._zoom_scale_changed).pack(side="left")
        self.preview_clump_name = tk.StringVar(value="")
        self.preview_clump_status = tk.StringVar(value="No clump selected")
        ttk.Label(camera, text="Clump").pack(side="left", padx=(12, 4))
        self.preview_clump_combo = ttk.Combobox(camera, textvariable=self.preview_clump_name, values=(), state="readonly", width=34)
        self.preview_clump_combo.pack(side="left")
        self.preview_clump_combo.bind("<<ComboboxSelected>>", lambda _event: self._preview_clump_selected())
        ttk.Label(camera, textvariable=self.preview_clump_status).pack(side="left", padx=(8, 0))

    def _build_slider_adjustments(self, parent: ttk.Frame) -> None:
        self.profile_scale = [tk.DoubleVar(value=1.0) for _ in range(3)]
        self.profile_rotation = [tk.DoubleVar(value=0.0) for _ in range(3)]
        self.profile_translation = [tk.DoubleVar(value=0.0) for _ in range(3)]
        self.profile_flip_winding = tk.BooleanVar(value=False)
        self.preview_profile_status = tk.StringVar(value="No saved adjustment loaded")

        group = ttk.LabelFrame(parent, text="Non-destructive per-asset transform", padding=6)
        group.grid(row=0, column=0, sticky="nsew")
        group.columnconfigure(2, weight=1)
        row_index = 0
        for label, variables, start, finish, increment in (
            ("Scale", self.profile_scale, 0.05, 5.0, 0.05),
            ("Rotate °", self.profile_rotation, -180.0, 180.0, 1.0),
            ("Translate", self.profile_translation, -100.0, 100.0, 0.1),
        ):
            ttk.Label(group, text=label).grid(row=row_index, column=0, sticky="nw", padx=(0, 8), pady=(4, 0))
            for axis, variable in zip("XYZ", variables):
                ttk.Label(group, text=axis).grid(row=row_index, column=1, sticky="e", padx=(0, 4))
                slider = ttk.Scale(group, from_=start, to=finish, orient="horizontal", variable=variable)
                slider.grid(row=row_index, column=2, sticky="ew", padx=(0, 5), pady=2)
                slider.bind("<ButtonRelease-1>", lambda _event: self._apply_preview_profile())
                ttk.Spinbox(group, from_=start, to=finish, increment=increment, textvariable=variable, width=9).grid(row=row_index, column=3, sticky="w")
                row_index += 1
        ttk.Checkbutton(group, text="Flip triangle winding", variable=self.profile_flip_winding, command=self._apply_preview_profile).grid(row=row_index, column=0, columnspan=2, sticky="w", pady=(5, 0))
        actions = ttk.Frame(group)
        actions.grid(row=row_index, column=2, columnspan=2, sticky="e", pady=(5, 0))
        ttk.Button(actions, text="Apply", command=self._apply_preview_profile, style="Accent.TButton").pack(side="left")
        ttk.Button(actions, text="Save for Asset", command=self._save_preview_profile).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Reset Saved", command=self._reset_preview_profile).pack(side="left", padx=(6, 0))
        row_index += 1
        ttk.Label(group, textvariable=self.preview_profile_status, wraplength=520).grid(row=row_index, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def _restore_v13_visual_layout(self) -> None:
        try:
            if self._visual_outer_paned is not None and self._visual_outer_paned.winfo_width() > 600:
                self._visual_outer_paned.sashpos(0, max(390, int(self._visual_outer_paned.winfo_width() * 0.34)))
            if self._visual_left_paned is not None and self._visual_left_paned.winfo_height() > 400:
                self._visual_left_paned.sashpos(0, max(260, int(self._visual_left_paned.winfo_height() * 0.56)))
        except (tk.TclError, IndexError):
            return

    def _notebook_tab_changed(self, event: tk.Event) -> None:
        super()._notebook_tab_changed(event)
        try:
            selected = self.notebook.select()
            if self.notebook.tab(selected, "text") == "3D / Assets":
                self.after(30, self._restore_v13_visual_layout)
        except tk.TclError:
            return

    def _visual_asset_selected(self, _event: tk.Event) -> None:
        self._schedule_wireframe_load()
        self._load_selected_ccsf_contents()

    # ------------------------------------------------------------------
    # Complete assembly and explicit pose selection
    # ------------------------------------------------------------------
    def _assembly_changed(self) -> None:
        row = self._selected_visual_row()
        if row is None or self.scene_assembly_mode is None:
            return
        mode = scene_v8.SELECTED_CLUMP if self.scene_assembly_mode.get() == "Selected Clump" else scene_v8.WHOLE_FILE
        scene_v8.set_assembly_mode(row["absolute_path"], mode)
        self._stop_animation()
        self._wireframe_load(allow_auto_texture=True)

    def _preview_clump_selected(self) -> None:
        if self.scene_assembly_mode is not None:
            self.scene_assembly_mode.set("Selected Clump")
        row = self._selected_visual_row()
        if row is not None:
            scene_v8.set_assembly_mode(row["absolute_path"], scene_v8.SELECTED_CLUMP)
        super()._preview_clump_selected()

    def _load_selected_ccsf_contents(self) -> None:
        row = self._selected_visual_row()
        self._stop_animation()
        self._ccsf_tree_generation += 1
        generation = self._ccsf_tree_generation
        self._clear_ccsf_contents()
        if row is None:
            return
        self.visual_status.set(f"Indexing objects, clumps, materials, textures and animations: {row['name']}…")

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
                f"{summary.get('textures', 0)} textures, {summary.get('animations', 0)} animations. Initial Pose selected."
            )
            self.after_idle(lambda: self._wireframe_load(allow_auto_texture=True))

        self._local_worker("ccsf-contents-v13", lambda: inspect_ccsf_contents(row["absolute_path"]), done)

    def _animation_row(self) -> dict[str, Any] | None:
        if self.animation_name.get() == INITIAL_POSE_NAME:
            return None
        return self._animation_rows_by_name.get(self.animation_name.get())

    def _animation_selected(self) -> None:
        if self.animation_name.get() == INITIAL_POSE_NAME:
            self._stop_animation()
            self._configure_animation_range()
            self._wireframe_load(allow_auto_texture=True)
            return
        super()._animation_selected()

    def _apply_animation_frame(self) -> None:
        if self.animation_name.get() == INITIAL_POSE_NAME:
            self._wireframe_load(allow_auto_texture=True)
            return
        super()._apply_animation_frame()

    # ------------------------------------------------------------------
    # Progressive textured rendering
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
        animation = self.animation_name.get().strip() or INITIAL_POSE_NAME
        frame = max(0, int(self.animation_frame.get()))
        active_row = dict(row)
        mode = scene_v8.SELECTED_CLUMP if self.scene_assembly_mode is not None and self.scene_assembly_mode.get() == "Selected Clump" else scene_v8.WHOLE_FILE
        scene_v8.set_assembly_mode(row["absolute_path"], mode)
        self.visual_status.set(f"Phase 1/3: assembling complete scene and mapping exact MAT/TEX/CLUT links for {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(55)

        def done(scene: Any, error: Exception | None) -> None:
            if generation != self._texture_load_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self._preview_mode = "wireframe"
                self._set_preview_mode_controls("wireframe")
                self.visual_status.set(f"Scene/texture mapping failed: {error}")
                self._replace_info(self.visual_details, f"Scene/texture mapping failed:\n{error}")
                return
            eligible, reason = scene_v8.auto_texture_eligibility(scene.summary, max_triangles=self._auto_texture_limit)
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
            self.visual_progress["value"] = 40.0
            self._render_progressive(scene, active_row, generation)

        self._local_worker(
            "whole-file-texture-map-v13",
            lambda: scene_v8.load_textured_scene(row["absolute_path"], animation_name=animation, frame=frame, assembly=mode),
            done,
        )

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
        self.visual_status.set("Phase 2/3: rendering fast mapped preview…")

        def fast_done(result: Any, error: Exception | None) -> None:
            if load_generation != self._texture_load_generation or render_generation != self._progressive_render_generation:
                return
            if error:
                self.visual_status.set(f"Fast texture render failed: {error}")
                return
            self._show_png_on_visual_canvas(Path(result["output_path"]))
            self.visual_progress["value"] = 70.0
            self.visual_status.set("Fast preview ready. Phase 3/3: refining settled textured view…")

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
                    f"Whole scene: {summary.get('clumps_included', 0)}/{summary.get('clumps_available', 0)} clumps, "
                    f"{summary.get('model_instances', 0)} model instances, {summary.get('textured_triangles', 0):,} textured / "
                    f"{summary.get('unresolved_triangles', 0):,} unresolved triangles, "
                    f"{summary.get('external_decoded_textures', 0)} exact external texture(s), pose {summary.get('selected_animation')}."
                )

            self._local_worker(
                "textured-refine-v13",
                lambda: scene_v8.render_textured_scene(
                    scene,
                    final_path,
                    yaw=camera[0],
                    pitch=camera[1],
                    zoom=camera[2],
                    pan_x=camera[3],
                    pan_y=camera[4],
                    width=width,
                    height=height,
                    pixel_step=scene_v8.preview_pixel_step(self._preview_quality()),
                ),
                final_done,
            )

        self._local_worker(
            "textured-fast-v13",
            lambda: scene_v8.render_textured_scene(
                scene,
                fast_path,
                yaw=camera[0],
                pitch=camera[1],
                zoom=camera[2],
                pan_x=camera[3],
                pan_y=camera[4],
                width=width,
                height=height,
                pixel_step=4,
            ),
            fast_done,
        )

    def _schedule_textured_render(self, delay: int = 180) -> None:
        if self._textured_scene is None or self._textured_scene_row is None or self._preview_mode != "textured":
            return
        if self._settled_render_after is not None:
            try:
                self.after_cancel(self._settled_render_after)
            except tk.TclError:
                pass
        self._settled_render_after = self.after(max(0, int(delay)), self._rerender_settled_scene)

    def _rerender_settled_scene(self) -> None:
        self._settled_render_after = None
        scene = self._textured_scene
        row = self._textured_scene_row
        project = self.project
        if scene is None or row is None or project is None or self._preview_mode != "textured":
            return
        self._progressive_render_generation += 1
        generation = self._progressive_render_generation
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview.png"
        width = max(480, self.visual_canvas.winfo_width())
        height = max(360, self.visual_canvas.winfo_height())
        camera = (self._wire_yaw, self._wire_pitch, self._wire_zoom, self._wire_pan_x, self._wire_pan_y)
        self.visual_status.set("Rerendering settled textured camera view…")

        def done(result: Any, error: Exception | None) -> None:
            if generation != self._progressive_render_generation or self._preview_mode != "textured":
                return
            if error:
                self.visual_status.set(f"Textured camera rerender failed: {error}")
                return
            self._show_png_on_visual_canvas(Path(result["output_path"]))
            self.visual_status.set(
                f"Textured view updated: {result.get('textured_faces', 0):,} textured / {result.get('unresolved_faces', 0):,} unresolved faces."
            )

        self._local_worker(
            "textured-camera-v13",
            lambda: scene_v8.render_textured_scene(
                scene,
                output,
                yaw=camera[0],
                pitch=camera[1],
                zoom=camera[2],
                pan_x=camera[3],
                pan_y=camera[4],
                width=width,
                height=height,
                pixel_step=scene_v8.preview_pixel_step(self._preview_quality()),
            ),
            done,
        )

    def _write_scene_evidence(self, scene: Any, eligibility_reason: str) -> None:
        payload = {
            "scene": scene.summary,
            "auto_texture": {"reason": eligibility_reason},
            "texture_records": scene.texture_rows,
            "material_records": scene.material_rows,
            "unresolved_reasons": scene.unresolved,
        }
        text = _json_text(payload)
        self._replace_info(self.visual_details, text)
        if self.texture_mapping_text is not None:
            self._replace_info(self.texture_mapping_text, text)

    @staticmethod
    def _replace_info(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)


def main() -> int:
    app = PublicFragmenterAppV13()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

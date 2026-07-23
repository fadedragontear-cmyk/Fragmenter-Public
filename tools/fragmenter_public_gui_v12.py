#!/usr/bin/env python3
"""Twelfth public GUI pass: restored RUN ALL visibility and compact sortable workspaces."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

import fragmenter_public_gui as gui_base
import fragmenter_public_gui_v3 as gui_v3
import fragmenter_public_gui_v4 as gui_v4
import fragmenter_public_gui_v5 as gui_v5
import fragmenter_public_gui_v6 as gui_v6
import fragmenter_public_gui_v8 as gui_v8
import fragmenter_public_gui_v10 as gui_v10
import fragmenter_public_gui_v11 as gui_v11
from asset_classifier_v2 import category_sort_key
from fragmenter_public_gui_v11 import PublicFragmenterAppV11
from fragmenter_public_gui_v3 import discover_visual_assets_v3
from project_sound_v6 import analyze_or_extract_sound_item, build_project_sound_library
from run_all_executor_v7 import build_run_all_actions_v7, execute_run_all_v7
from snddata_sample_library_v2 import extract_project_snddata_samples


def _replace_text_editable(widget: tk.Text, text: str) -> None:
    """Replace informational text while leaving it selectable, editable and pasteable."""
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)


# Layered GUI modules imported _replace_text directly. Replace each module-level
# reference so reports and diagnostics remain copy/paste capable everywhere.
for _module in (gui_base, gui_v3, gui_v4, gui_v5, gui_v6, gui_v8, gui_v10):
    if hasattr(_module, "_replace_text"):
        setattr(_module, "_replace_text", _replace_text_editable)

# Preserve the validated GUI lifecycle while routing all public work through the
# non-recursive pipeline and cleaned audio library.
gui_v5.build_project_sound_library = build_project_sound_library
gui_v5.analyze_or_extract_sound_item = analyze_or_extract_sound_item
gui_v5.build_run_all_actions_v4 = build_run_all_actions_v7
gui_v5.execute_run_all_v4 = execute_run_all_v7
gui_v11.build_project_sound_library = build_project_sound_library
gui_v11.extract_project_snddata_samples = extract_project_snddata_samples


class PublicFragmenterAppV12(PublicFragmenterAppV11):
    """Compact workbench layout without changing the active visual decoder path."""

    def __init__(self) -> None:
        self._visual_rows_cache: list[dict[str, Any]] = []
        self._visual_sort_column = "type"
        self._visual_sort_reverse = False
        self._audio_rows_cache: list[dict[str, Any]] = []
        self._audio_sort_column = "name"
        self._audio_sort_reverse = False
        self._visual_preview_paned: ttk.Panedwindow | None = None
        self.preview_wireframe_var: tk.BooleanVar | None = None
        self.preview_textured_var: tk.BooleanVar | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Stabilization Pass")
        self._install_text_context_menus(self)
        self.notebook.bind("<<NotebookTabChanged>>", self._notebook_tab_changed, add="+")
        self.after_idle(self._restore_visual_split)

    # ------------------------------------------------------------------
    # Compact 3D workspace
    # ------------------------------------------------------------------
    def _build_visual(self, parent: ttk.Frame) -> None:
        super()._build_visual(parent)

        # The previous four full-width bars compressed the actual viewport. Remove
        # them and rebuild the useful controls inside the preview/details panes.
        for child in tuple(parent.winfo_children()):
            if isinstance(child, ttk.LabelFrame) and str(child.cget("text")) in {
                "Animation / pose preview",
                "Scene assembly",
                "3D preview controls",
                "Per-asset preview adjustment",
            }:
                child.destroy()
        self._remove_controls_by_text(
            parent,
            {
                "Load Wireframe",
                "Wireframe",
                "Textured Preview",
                "Textured Snapshot",
                "Scene Metadata",
                "Animation Metadata",
            },
        )

        self._install_visual_tree_scrollbar(parent)
        self._configure_visual_sort_headings()

        preview_frame = self.visual_canvas.master
        paned = preview_frame.master
        if isinstance(paned, ttk.Panedwindow):
            self._visual_preview_paned = paned
        preview_frame.configure(text="3D preview")
        preview_frame.rowconfigure(0, weight=0)
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.rowconfigure(2, weight=0)
        preview_frame.rowconfigure(3, weight=0)
        preview_frame.columnconfigure(0, weight=1)
        self.visual_canvas.grid_configure(row=1, column=0, sticky="nsew")

        self._build_preview_mode_bar(preview_frame)
        self._build_animation_camera_controls(preview_frame)
        self._build_profile_editor_tab()
        self.after_idle(self._restore_visual_split)

    def _install_visual_tree_scrollbar(self, parent: ttk.Frame) -> None:
        self.visual_tree.grid_configure(padx=(0, 22))
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.visual_tree.yview)
        self.visual_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=2, column=0, sticky="nse", padx=(0, 6))
        self.visual_tree_scrollbar = scrollbar

    def _build_preview_mode_bar(self, preview_frame: ttk.LabelFrame) -> None:
        bar = ttk.Frame(preview_frame, padding=(5, 3))
        bar.grid(row=0, column=0, sticky="ew")
        self.preview_wireframe_var = tk.BooleanVar(value=True)
        self.preview_textured_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Wireframe", variable=self.preview_wireframe_var, command=self._select_wireframe_mode).pack(side="left")
        ttk.Checkbutton(bar, text="Textured", variable=self.preview_textured_var, command=self._select_textured_mode).pack(side="left", padx=(8, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Checkbutton(bar, text="Auto texture", variable=self.auto_texture_var, command=self._auto_texture_toggled).pack(side="left")
        ttk.Label(bar, text="Quality").pack(side="left", padx=(12, 4))
        quality = ttk.Combobox(
            bar,
            textvariable=self.preview_quality_var,
            values=("Fast", "Balanced", "Full"),
            state="readonly",
            width=10,
        )
        quality.pack(side="left")
        quality.bind("<<ComboboxSelected>>", lambda _event: self._preview_quality_changed())
        ttk.Label(bar, text="Left drag rotate · right/middle pan · wheel zoom").pack(side="right")

    def _build_animation_camera_controls(self, preview_frame: ttk.LabelFrame) -> None:
        animation = ttk.Frame(preview_frame, padding=(5, 3))
        animation.grid(row=2, column=0, sticky="ew")
        animation.columnconfigure(3, weight=1)
        ttk.Label(animation, text="Animation").grid(row=0, column=0, sticky="w")
        self.animation_combo = ttk.Combobox(
            animation,
            textvariable=self.animation_name,
            values=tuple(self._animation_rows_by_name),
            state="readonly",
            width=26,
        )
        self.animation_combo.grid(row=0, column=1, sticky="w", padx=(5, 10))
        self.animation_combo.bind("<<ComboboxSelected>>", lambda _event: self._animation_selected())
        ttk.Label(animation, text="Frame").grid(row=0, column=2, sticky="w")
        self.animation_frame_scale = ttk.Scale(
            animation,
            from_=0,
            to=0,
            orient="horizontal",
            command=self._animation_scale_changed,
        )
        self.animation_frame_scale.grid(row=0, column=3, sticky="ew", padx=(5, 6))
        self.animation_frame_scale.bind("<ButtonRelease-1>", lambda _event: self._apply_animation_frame())
        ttk.Label(animation, textvariable=self.animation_frame_label, width=12).grid(row=0, column=4, sticky="w")
        ttk.Button(animation, text="Apply", command=self._apply_animation_frame).grid(row=0, column=5, padx=(4, 0))
        self.animation_play_button = ttk.Button(animation, text="Play", command=self._toggle_animation_play, style="Accent.TButton")
        self.animation_play_button.grid(row=0, column=6, padx=(6, 0))

        camera = ttk.Frame(preview_frame, padding=(5, 3))
        camera.grid(row=3, column=0, sticky="ew")
        ttk.Label(camera, text="Camera").pack(side="left")
        for label, command in (
            ("Front", self._camera_front),
            ("Side", self._camera_side),
            ("Top", self._camera_top),
            ("Reset", self._camera_reset),
            ("Fit", self._fit_view),
        ):
            ttk.Button(camera, text=label, command=command).pack(side="left", padx=(4, 0))
        ttk.Label(camera, text="Zoom").pack(side="left", padx=(12, 4))
        ttk.Scale(
            camera,
            from_=0.15,
            to=8.0,
            orient="horizontal",
            length=150,
            variable=self.preview_zoom_var,
            command=self._zoom_scale_changed,
        ).pack(side="left")
        ttk.Label(camera, text="Clump").pack(side="left", padx=(12, 4))
        self.preview_clump_combo = ttk.Combobox(
            camera,
            textvariable=self.preview_clump_name,
            values=tuple(self._preview_clumps_by_label),
            state="readonly",
            width=31,
        )
        self.preview_clump_combo.pack(side="left")
        self.preview_clump_combo.bind("<<ComboboxSelected>>", lambda _event: self._preview_clump_selected())
        ttk.Label(camera, textvariable=self.preview_clump_status).pack(side="left", padx=(8, 0))

    def _build_profile_editor_tab(self) -> None:
        notebook = self.visual_details.master.master
        if not isinstance(notebook, ttk.Notebook):
            return
        tab = ttk.Frame(notebook, padding=7)
        tab.columnconfigure(0, weight=1)
        notebook.add(tab, text="Preview Adjustments")
        profile = ttk.LabelFrame(tab, text="Non-destructive per-asset adjustment", padding=7)
        profile.grid(row=0, column=0, sticky="ew")
        self._populate_profile_editor(profile)
        ttk.Label(
            tab,
            text=(
                "These settings affect Fragmenter's preview only and are stored per asset in project.json. "
                "They do not modify CCSF files."
            ),
            wraplength=620,
        ).grid(row=1, column=0, sticky="w", pady=(7, 0))

    def _populate_profile_editor(self, profile: ttk.LabelFrame) -> None:
        def vector_controls(row: int, label: str, values: list[tk.DoubleVar], increment: float) -> None:
            ttk.Label(profile, text=label).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=2)
            for index, axis in enumerate("XYZ"):
                ttk.Label(profile, text=axis).grid(row=row, column=1 + index * 2, sticky="e")
                ttk.Spinbox(
                    profile,
                    from_=-10000.0,
                    to=10000.0,
                    increment=increment,
                    textvariable=values[index],
                    width=9,
                ).grid(row=row, column=2 + index * 2, padx=(2, 7), sticky="w")

        vector_controls(0, "Scale", self.profile_scale, 0.05)
        vector_controls(1, "Rotate °", self.profile_rotation, 5.0)
        vector_controls(2, "Translate", self.profile_translation, 0.1)
        ttk.Checkbutton(profile, text="Flip triangle winding", variable=self.profile_flip_winding).grid(row=3, column=0, columnspan=3, sticky="w", pady=(5, 0))
        actions = ttk.Frame(profile)
        actions.grid(row=3, column=3, columnspan=4, sticky="e", pady=(5, 0))
        ttk.Button(actions, text="Apply", command=self._apply_preview_profile, style="Accent.TButton").pack(side="left")
        ttk.Button(actions, text="Save for Asset", command=self._save_preview_profile).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Reset Saved", command=self._reset_preview_profile).pack(side="left", padx=(6, 0))
        ttk.Label(profile, textvariable=self.preview_profile_status, wraplength=620).grid(row=4, column=0, columnspan=7, sticky="w", pady=(6, 0))

    def _remove_controls_by_text(self, widget: tk.Misc, labels: set[str]) -> None:
        try:
            for child in tuple(widget.winfo_children()):
                if isinstance(child, ttk.Button) and str(child.cget("text")) in labels:
                    child.destroy()
                    continue
                self._remove_controls_by_text(child, labels)
        except tk.TclError:
            return

    def _select_wireframe_mode(self) -> None:
        self._set_preview_mode_controls("wireframe")
        self._wireframe_load(allow_auto_texture=False)

    def _select_textured_mode(self) -> None:
        self._set_preview_mode_controls("textured")
        self._start_textured_preview(force=True)

    def _set_preview_mode_controls(self, mode: str) -> None:
        if self.preview_wireframe_var is not None:
            self.preview_wireframe_var.set(mode == "wireframe")
        if self.preview_textured_var is not None:
            self.preview_textured_var.set(mode == "textured")

    def _wireframe_load(self, generation: int | None = None, *, allow_auto_texture: bool | None = None) -> None:
        self._set_preview_mode_controls("wireframe")
        super()._wireframe_load(generation=generation, allow_auto_texture=allow_auto_texture)

    def _start_textured_preview(self, *, force: bool) -> None:
        self._set_preview_mode_controls("textured")
        super()._start_textured_preview(force=force)

    def _notebook_tab_changed(self, _event: tk.Event) -> None:
        try:
            selected = self.notebook.select()
            if self.notebook.tab(selected, "text") == "3D / Assets":
                self.after(30, self._restore_visual_split)
        except tk.TclError:
            return

    def _restore_visual_split(self) -> None:
        paned = self._visual_preview_paned
        if paned is None:
            return
        try:
            height = paned.winfo_height()
            if height < 200:
                self.after(80, self._restore_visual_split)
                return
            paned.sashpos(0, max(330, int(height * 0.72)))
        except (tk.TclError, IndexError):
            return

    # ------------------------------------------------------------------
    # Sortable visual library
    # ------------------------------------------------------------------
    def _configure_visual_sort_headings(self) -> None:
        for column, title in (("#0", "Asset"), ("kind", "Type"), ("size", "Size"), ("path", "Project-relative path")):
            self.visual_tree.heading(column, text=title, command=lambda key=column: self._sort_visual_tree(key))

    def _sort_visual_tree(self, column: str) -> None:
        normalized = {"#0": "name", "kind": "type", "size": "size", "path": "path"}.get(column, "name")
        if normalized == self._visual_sort_column:
            self._visual_sort_reverse = not self._visual_sort_reverse
        else:
            self._visual_sort_column = normalized
            self._visual_sort_reverse = normalized == "size"
        self._populate_visual_rows(self._visual_rows_cache)

    def _refresh_visual_assets(self) -> None:
        project = self.project
        self._visual_generation += 1
        generation = self._visual_generation
        self.visual_tree.delete(*self.visual_tree.get_children())
        self.visual_payloads.clear()
        if project is None:
            return
        self.visual_status.set("Classifying extracted CCSF library…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)
        query = self.visual_search.get()
        category = self.visual_category.get() if hasattr(self, "visual_category") else "All"

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._visual_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            self.visual_progress["value"] = 100.0 if not error else 0.0
            if error:
                self.visual_status.set(f"Asset classification failed: {error}")
                return
            self._visual_rows_cache = list(rows)
            self._populate_visual_rows(self._visual_rows_cache)

        self._local_worker("visual-classification-v12", lambda: discover_visual_assets_v3(project, query, category), done)

    def _populate_visual_rows(self, rows: list[dict[str, Any]]) -> None:
        self.visual_tree.delete(*self.visual_tree.get_children())
        self.visual_payloads.clear()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row.get("kind") or "Unknown"), []).append(row)

        def asset_key(row: dict[str, Any]):
            if self._visual_sort_column == "size":
                return int(row.get("size") or 0)
            if self._visual_sort_column == "path":
                return str(row.get("relative_path") or "").lower()
            if self._visual_sort_column == "type":
                return (category_sort_key(str(row.get("kind") or "")), str(row.get("name") or "").lower())
            return str(row.get("name") or "").lower()

        kinds = list(grouped)
        if self._visual_sort_column == "size":
            kinds.sort(key=lambda kind: sum(int(row.get("size") or 0) for row in grouped[kind]), reverse=self._visual_sort_reverse)
        else:
            kinds.sort(key=category_sort_key, reverse=self._visual_sort_reverse if self._visual_sort_column == "type" else False)

        asset_index = 0
        query_active = bool(self.visual_search.get().strip())
        category_filter = self.visual_category.get() if hasattr(self, "visual_category") else "All"
        for group_index, kind in enumerate(kinds):
            children = sorted(grouped[kind], key=asset_key, reverse=self._visual_sort_reverse)
            category_iid = f"category_{group_index}"
            total_size = sum(int(row.get("size") or 0) for row in children)
            self.visual_tree.insert(
                "",
                "end",
                iid=category_iid,
                text=kind,
                values=(f"{len(children):,} assets", f"{total_size:,}", ""),
                open=query_active or category_filter != "All",
            )
            for row in children:
                iid = f"asset_{asset_index}"
                asset_index += 1
                confidence = str(row.get("classification_confidence") or "")
                self.visual_tree.insert(
                    category_iid,
                    "end",
                    iid=iid,
                    text=row.get("name") or "",
                    values=(confidence, f"{int(row.get('size') or 0):,}", row.get("relative_path") or ""),
                )
                self.visual_payloads[iid] = row
        direction = "descending" if self._visual_sort_reverse else "ascending"
        self.visual_status.set(
            f"Showing {len(rows):,} assets in {len(grouped):,} categories; sorted by {self._visual_sort_column} {direction}."
        )

    # ------------------------------------------------------------------
    # Cleaner sortable audio library
    # ------------------------------------------------------------------
    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        for child in tuple(parent.winfo_children()):
            if isinstance(child, ttk.LabelFrame) and str(child.cget("text")) == "Extracted sample library":
                child.destroy()
        self._configure_audio_library_controls()
        self._configure_audio_scrollbars()
        self._configure_audio_sort_headings()

    def _audio_library_parent(self) -> ttk.Frame | None:
        try:
            paned = self.simple_audio_tree.master.master
            parent = paned.master
            return parent if isinstance(parent, ttk.Frame) else None
        except (AttributeError, tk.TclError):
            return None

    def _configure_audio_library_controls(self) -> None:
        library = self._audio_library_parent()
        if library is None:
            return
        controls = next(
            (
                child
                for child in library.winfo_children()
                if isinstance(child, ttk.Frame) and int(child.grid_info().get("row", -1)) == 0
            ),
            None,
        )
        if controls is None:
            return
        ttk.Button(controls, text="Extract SNDDATA", command=self._extract_snddata_sample_library, style="Accent.TButton").pack(side="left", padx=(6, 0))
        ttk.Label(controls, text="Volume").pack(side="left", padx=(14, 4))
        ttk.Scale(
            controls,
            from_=0.0,
            to=1.0,
            variable=self.audio_gain,
            length=120,
            command=self._audio_gain_changed,
        ).pack(side="left")

    def _configure_audio_scrollbars(self) -> None:
        tree_frame = self.simple_audio_tree.master
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.simple_audio_tree.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.simple_audio_tree.xview)
        self.simple_audio_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        sequence_parent = self.sequence_tree.master
        sequence_parent.columnconfigure(0, weight=1)
        sequence_scroll = ttk.Scrollbar(sequence_parent, orient="vertical", command=self.sequence_tree.yview)
        self.sequence_tree.configure(yscrollcommand=sequence_scroll.set)
        sequence_scroll.grid(row=1, column=0, sticky="nse")

        program_parent = self.program_tree.master
        program_parent.columnconfigure(0, weight=1)
        program_scroll = ttk.Scrollbar(program_parent, orient="vertical", command=self.program_tree.yview)
        self.program_tree.configure(yscrollcommand=program_scroll.set)
        program_scroll.grid(row=0, column=1, sticky="ns")

    def _configure_audio_sort_headings(self) -> None:
        columns = (
            ("#0", "Audio", "name"),
            ("kind", "Kind", "kind"),
            ("category", "Category", "category"),
            ("duration", "Duration", "duration"),
            ("action", "Action", "action"),
            ("size", "Size", "size"),
            ("path", "project/sound relative path", "path"),
        )
        for column, title, key in columns:
            self.simple_audio_tree.heading(column, text=title, command=lambda sort_key=key: self._sort_audio_tree(sort_key))

    def _sort_audio_tree(self, column: str) -> None:
        if column == self._audio_sort_column:
            self._audio_sort_reverse = not self._audio_sort_reverse
        else:
            self._audio_sort_column = column
            self._audio_sort_reverse = column in {"size", "duration"}
        self._populate_audio_rows(self._audio_rows_cache)

    def _refresh_simple_audio(self) -> None:
        project = self.project
        if not hasattr(self, "simple_audio_tree"):
            return
        self._simple_audio_generation += 1
        generation = self._simple_audio_generation
        self.simple_audio_tree.delete(*self.simple_audio_tree.get_children())
        self._simple_audio_rows.clear()
        if project is None:
            self.simple_audio_status.set("No project loaded")
            return
        query = self.simple_audio_query.get()
        category = self.simple_audio_category.get()
        self.simple_audio_status.set("Reading active project/sound catalog…")

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._simple_audio_generation:
                return
            if error:
                self.simple_audio_status.set(f"Sound library failed: {error}")
                return
            categories = ("All", *model.get("categories", []))
            if self._sound_category_combo is not None:
                self._sound_category_combo.configure(values=categories)
            self._audio_rows_cache = list(model.get("items") or [])
            self._populate_audio_rows(self._audio_rows_cache)
            summary = model["summary"]
            self.simple_audio_status.set(
                f"{summary['playable_wavs']:,} playable WAVs; {summary.get('snddata_sample_wavs', 0):,} SNDDATA samples; "
                f"{summary.get('hidden_raw_pcm_rows', 0):,} raw-PCM research rows hidden."
            )

        self._local_worker(
            "project-sound-library-v6",
            lambda: build_project_sound_library(project, query=query, category=category),
            done,
        )

    def _populate_audio_rows(self, rows: list[dict[str, Any]]) -> None:
        self.simple_audio_tree.delete(*self.simple_audio_tree.get_children())
        self._simple_audio_rows.clear()

        def sort_key(item: dict[str, Any]):
            wav = item.get("wav") if isinstance(item.get("wav"), dict) else {}
            values = {
                "name": str(item.get("name") or "").lower(),
                "kind": str(item.get("kind") or "").lower(),
                "category": str(item.get("category") or "").lower(),
                "duration": float(wav.get("duration") or 0.0),
                "action": str(item.get("primary_action") or "").lower(),
                "size": int(item.get("size") or 0),
                "path": str(item.get("relative_path") or "").lower(),
            }
            return values[self._audio_sort_column]

        for index, item in enumerate(sorted(rows, key=sort_key, reverse=self._audio_sort_reverse)):
            iid = f"simple_audio_{index}"
            wav = item.get("wav") if isinstance(item.get("wav"), dict) else {}
            duration = f"{float(wav.get('duration') or 0):.2f}s" if item.get("playable") else "—"
            self.simple_audio_tree.insert(
                "",
                "end",
                iid=iid,
                text=item.get("name") or "",
                values=(
                    item.get("kind") or "",
                    item.get("category") or "",
                    duration,
                    item.get("primary_action") or "",
                    f"{int(item.get('size') or 0):,}",
                    item.get("relative_path") or "",
                ),
            )
            self._simple_audio_rows[iid] = item

    def _audio_gain_changed(self, value: str) -> None:
        try:
            self.playback.set_gain(max(0.0, min(1.0, float(value))))
        except Exception:
            return

    # ------------------------------------------------------------------
    # Editable report/details text
    # ------------------------------------------------------------------
    def _install_text_context_menus(self, widget: tk.Misc) -> None:
        try:
            for child in widget.winfo_children():
                if isinstance(child, tk.Text):
                    child.configure(state="normal")
                    child.bind("<Control-a>", lambda event, target=child: self._select_all_text(event, target), add="+")
                    child.bind("<Button-3>", lambda event, target=child: self._show_text_menu(event, target), add="+")
                self._install_text_context_menus(child)
        except tk.TclError:
            return

    @staticmethod
    def _select_all_text(_event: tk.Event, widget: tk.Text) -> str:
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "1.0")
        widget.see("insert")
        return "break"

    def _show_text_menu(self, event: tk.Event, widget: tk.Text) -> None:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_command(label="Select All", command=lambda: self._select_all_text(event, widget))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


def main() -> int:
    app = PublicFragmenterAppV12()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

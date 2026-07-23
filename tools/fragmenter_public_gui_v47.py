#!/usr/bin/env python3
"""V47: sample classifier and a Standard-MIDI Original Sequencer."""
from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from fragmenter_public_gui_v46 import PublicFragmenterAppV46
from original_sequencer_v1 import load_state as load_sequencer_state
from original_sequencer_v1 import render_midi_project
from original_sequencer_v1 import save_state as save_sequencer_state
from project_sound_v1 import sound_work_root
from snddata_sample_classification_v1 import (
    CATEGORIES,
    PLAYBACK_MODES,
    USABILITY,
    classified_sample_rows,
    save_classification,
    sequencer_sample_rows,
)
from standard_midi_v1 import parse_midi_file, write_original_demo_midi


class PublicFragmenterAppV47(PublicFragmenterAppV46):
    """Run format research and original MIDI/sample experiments side by side."""

    def __init__(self) -> None:
        self.audio_subnotebook_v47: ttk.Notebook | None = None
        self.sample_classifier_tab_v47: ttk.Frame | None = None
        self.original_sequencer_tab_v47: ttk.Frame | None = None
        self.classifier_rows_v47: dict[str, dict[str, Any]] = {}
        self.classifier_current_v47: dict[str, Any] | None = None
        self.sequencer_parsed_v47: dict[str, Any] | None = None
        self.sequencer_channel_rows_v47: dict[str, dict[str, Any]] = {}
        self.sequencer_channel_mappings_v47: dict[str, dict[str, Any]] = {}
        self.sequencer_sample_choices_v47: dict[str, dict[str, Any]] = {}
        self.sequencer_sample_combo_v47: ttk.Combobox | None = None
        self.sequencer_last_preview_v47: Path | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Audio Research + Original Sequencer")

    # ------------------------------------------------------------------
    # Audio sub-tabs
    # ------------------------------------------------------------------
    def _build_audio(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.audio_subnotebook_v47 = notebook

        library = ttk.Frame(notebook, padding=7)
        pipeline = ttk.Frame(notebook, padding=7)
        research = ttk.Frame(notebook, padding=7)
        classifier = ttk.Frame(notebook, padding=7)
        sequencer = ttk.Frame(notebook, padding=7)
        notebook.add(library, text="Audio Library")
        notebook.add(pipeline, text="Audio Pipeline")
        notebook.add(research, text="SNDDATA Research Mixer")
        notebook.add(classifier, text="Sample Classifier")
        notebook.add(sequencer, text="Original Sequencer")

        self.sample_classifier_tab_v47 = classifier
        self.original_sequencer_tab_v47 = sequencer
        self._build_simple_audio_library(library)
        self._build_audio_pipeline_v38(pipeline)
        self._build_research_mixer_v40(research)
        self._build_sample_classifier_v47(classifier)
        self._build_original_sequencer_v47(sequencer)
        notebook.bind("<<NotebookTabChanged>>", self._audio_subtab_changed_v47, add="+")

    def _audio_subtab_changed_v47(self, _event: Any = None) -> None:
        notebook = self.audio_subnotebook_v47
        if notebook is None or self.project is None:
            return
        try:
            label = str(notebook.tab(notebook.select(), "text"))
        except tk.TclError:
            return
        if label == "Sample Classifier":
            self._refresh_sample_classifier_v47()
        elif label == "Original Sequencer":
            self._refresh_sequencer_sample_choices_v47()

    # ------------------------------------------------------------------
    # Notes and Flags become separate research pages.
    # ------------------------------------------------------------------
    def _build_research_quadrant_v46(self, parent: ttk.Panedwindow) -> None:
        super()._build_research_quadrant_v46(parent)
        tabs = self.audio_research_tabs_v46
        if tabs is None:
            return
        tab_widgets: dict[str, ttk.Frame] = {}
        for tab_id in tabs.tabs():
            label = str(tabs.tab(tab_id, "text"))
            widget = tabs.nametowidget(tab_id)
            if isinstance(widget, ttk.Frame):
                tab_widgets[label] = widget

        notes = tab_widgets.get("Notes & Flags")
        bundle = tab_widgets.get("Research Bundle")
        if notes is not None:
            tabs.tab(str(notes), text="Notes")
            self._destroy_button_text_v47(notes, "Toggle Research Flag")
        if bundle is None:
            return

        for child in tuple(bundle.winfo_children()):
            child.destroy()
        bundle.columnconfigure(0, weight=1)
        ttk.Label(
            bundle,
            text=(
                "Bundle exports are separate from persistent flags. Selected exports include "
                "the active sequence/candidate; flagged exports collect every marked asset."
            ),
            wraplength=760,
        ).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        bundle_actions = ttk.Frame(bundle)
        bundle_actions.grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        ttk.Button(
            bundle_actions,
            text="Export Selected Bundle",
            command=self._export_selected_bundle_v46,
        ).pack(side="left")
        ttk.Button(
            bundle_actions,
            text="Export All Flagged",
            command=self._export_flagged_bundle_v46,
            style="Accent.TButton",
        ).pack(side="left", padx=(6, 0))

        flags = ttk.Frame(tabs)
        flags.columnconfigure(0, weight=1)
        flags.rowconfigure(1, weight=1)
        insert_index = max(0, list(tabs.tabs()).index(str(bundle)))
        tabs.insert(insert_index, flags, text="Flags")
        ttk.Label(
            flags,
            text="Right-click a sequence, Program candidate, or sample to flag it for comparison.",
            wraplength=760,
        ).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.audio_flag_tree_v46 = ttk.Treeview(
            flags,
            columns=("kind", "sequence", "resource", "sample", "notes"),
            show="headings",
        )
        for key, label, width, numeric in (
            ("kind", "Type", 80, False),
            ("sequence", "Sequence", 170, False),
            ("resource", "Resource", 110, False),
            ("sample", "Sample", 70, True),
            ("notes", "Notes", 320, False),
        ):
            self.audio_flag_tree_v46.heading(
                key,
                text=label,
                command=lambda c=key, n=numeric: self._sort_tree_v46(
                    self.audio_flag_tree_v46, c, n
                ),
            )
            self.audio_flag_tree_v46.column(
                key, width=width, stretch=key in {"sequence", "notes"}
            )
        flag_y = ttk.Scrollbar(
            flags, orient="vertical", command=self.audio_flag_tree_v46.yview
        )
        self.audio_flag_tree_v46.configure(yscrollcommand=flag_y.set)
        self.audio_flag_tree_v46.grid(row=1, column=0, sticky="nsew", padx=(5, 0))
        flag_y.grid(row=1, column=1, sticky="ns")
        actions = ttk.Frame(flags)
        actions.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Button(
            actions, text="Refresh Flags", command=self._refresh_flagged_assets_v46
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Export All Flagged",
            command=self._export_flagged_bundle_v46,
        ).pack(side="left", padx=(6, 0))
        self._refresh_flagged_assets_v46()

    def _destroy_button_text_v47(self, widget: tk.Misc, text: str) -> None:
        for child in tuple(widget.winfo_children()):
            if isinstance(child, ttk.Button) and str(child.cget("text")) == text:
                child.destroy()
                continue
            self._destroy_button_text_v47(child, text)

    # ------------------------------------------------------------------
    # Sample Classifier
    # ------------------------------------------------------------------
    def _build_sample_classifier_v47(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(toolbar, text="Find").pack(side="left")
        self.classifier_search_v47 = tk.StringVar(value="")
        search = ttk.Entry(toolbar, textvariable=self.classifier_search_v47, width=28)
        search.pack(side="left", padx=(5, 9))
        search.bind("<Return>", lambda _event: self._refresh_sample_classifier_v47())
        ttk.Label(toolbar, text="Category").pack(side="left")
        self.classifier_category_filter_v47 = tk.StringVar(value="All")
        category = ttk.Combobox(
            toolbar,
            textvariable=self.classifier_category_filter_v47,
            values=("All", *CATEGORIES),
            state="readonly",
            width=14,
        )
        category.pack(side="left", padx=(5, 9))
        category.bind("<<ComboboxSelected>>", lambda _event: self._refresh_sample_classifier_v47())
        ttk.Label(toolbar, text="Usability").pack(side="left")
        self.classifier_usability_filter_v47 = tk.StringVar(value="All")
        usability = ttk.Combobox(
            toolbar,
            textvariable=self.classifier_usability_filter_v47,
            values=("All", *USABILITY),
            state="readonly",
            width=13,
        )
        usability.pack(side="left", padx=(5, 9))
        usability.bind("<<ComboboxSelected>>", lambda _event: self._refresh_sample_classifier_v47())
        ttk.Button(
            toolbar,
            text="Refresh Samples",
            command=self._refresh_sample_classifier_v47,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            toolbar, text="Play Selected", command=self._play_classifier_sample_v47
        ).pack(side="left", padx=(6, 0))
        self.classifier_status_v47 = tk.StringVar(value="Open this tab to classify decoded WAVs.")
        ttk.Label(toolbar, textvariable=self.classifier_status_v47).pack(side="right")

        split = ttk.Panedwindow(parent, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew")
        listing = ttk.LabelFrame(split, text="Decoded sample assets", padding=4)
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.classifier_tree_v47 = ttk.Treeview(
            listing,
            columns=("bank", "sample", "rate", "duration", "category", "mode", "root", "usable"),
            show="tree headings",
            selectmode="browse",
        )
        for key, label, width, numeric in (
            ("#0", "Label", 230, False),
            ("bank", "Bank / resource", 120, False),
            ("sample", "Sample", 65, True),
            ("rate", "Rate", 75, True),
            ("duration", "Duration", 75, True),
            ("category", "Category", 90, False),
            ("mode", "Mode", 85, False),
            ("root", "Root", 50, True),
            ("usable", "Usability", 85, False),
        ):
            self.classifier_tree_v47.heading(
                key,
                text=label,
                command=lambda c=key, n=numeric: self._sort_tree_v46(
                    self.classifier_tree_v47, c, n
                ),
            )
            self.classifier_tree_v47.column(
                key, width=width, stretch=key in {"#0", "bank"}
            )
        ybar = ttk.Scrollbar(listing, orient="vertical", command=self.classifier_tree_v47.yview)
        xbar = ttk.Scrollbar(listing, orient="horizontal", command=self.classifier_tree_v47.xview)
        self.classifier_tree_v47.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.classifier_tree_v47.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        self.classifier_tree_v47.bind("<<TreeviewSelect>>", lambda _event: self._classifier_selected_v47())
        self.classifier_tree_v47.bind("<Double-1>", lambda _event: self._play_classifier_sample_v47())
        self.classifier_tree_v47.bind("<Button-3>", self._classifier_context_menu_v47)
        split.add(listing, weight=3)

        editor = ttk.LabelFrame(split, text="Classification / instrument metadata", padding=7)
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(7, weight=1)
        self.classifier_label_v47 = tk.StringVar()
        self.classifier_category_v47 = tk.StringVar(value="Unclassified")
        self.classifier_family_v47 = tk.StringVar()
        self.classifier_mode_v47 = tk.StringVar(value="Pitched")
        self.classifier_root_v47 = tk.IntVar(value=60)
        self.classifier_usability_v47 = tk.StringVar(value="Unreviewed")
        self.classifier_tags_v47 = tk.StringVar()
        fields = (
            ("Label", ttk.Entry(editor, textvariable=self.classifier_label_v47)),
            ("Category", ttk.Combobox(editor, textvariable=self.classifier_category_v47, values=CATEGORIES, state="readonly")),
            ("Family", ttk.Entry(editor, textvariable=self.classifier_family_v47)),
            ("Playback mode", ttk.Combobox(editor, textvariable=self.classifier_mode_v47, values=PLAYBACK_MODES, state="readonly")),
            ("Root MIDI note", ttk.Spinbox(editor, from_=0, to=127, textvariable=self.classifier_root_v47)),
            ("Usability", ttk.Combobox(editor, textvariable=self.classifier_usability_v47, values=USABILITY, state="readonly")),
            ("Tags", ttk.Entry(editor, textvariable=self.classifier_tags_v47)),
        )
        for row_index, (label, control) in enumerate(fields):
            ttk.Label(editor, text=label).grid(row=row_index, column=0, sticky="w", padx=(0, 7), pady=3)
            control.grid(row=row_index, column=1, sticky="ew", pady=3)
        ttk.Label(editor, text="Notes").grid(row=7, column=0, sticky="nw", padx=(0, 7), pady=3)
        self.classifier_notes_v47 = tk.Text(editor, height=8, wrap="word")
        self.classifier_notes_v47.grid(row=7, column=1, sticky="nsew", pady=3)
        actions = ttk.Frame(editor)
        actions.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Save Classification", command=self._save_classifier_sample_v47, style="Accent.TButton").pack(side="left")
        ttk.Button(actions, text="Play Sample", command=self._play_classifier_sample_v47).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Use in Sequencer", command=self._use_classifier_in_sequencer_v47).pack(side="left", padx=(6, 0))
        split.add(editor, weight=2)

    def _refresh_sample_classifier_v47(self) -> None:
        project = self.project
        if project is None or not hasattr(self, "classifier_tree_v47"):
            return
        query = self.classifier_search_v47.get()
        category = self.classifier_category_filter_v47.get()
        usability = self.classifier_usability_filter_v47.get()
        self.classifier_status_v47.set("Loading normalized sample inventory…")

        def done(rows: Any, error: Exception | None) -> None:
            if error:
                self.classifier_status_v47.set(f"Sample classifier failed: {error}")
                return
            tree = self.classifier_tree_v47
            tree.delete(*tree.get_children())
            self.classifier_rows_v47.clear()
            for index, row in enumerate(rows):
                iid = f"classifier_{index}"
                resource = int(row.get("resource_offset") or 0)
                sample_id = int(row.get("sample_id") or 0)
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=str(row.get("classification_label") or row.get("display_name")),
                    values=(
                        f"0x{resource:X}",
                        f"{sample_id:04d}",
                        f"{int(row.get('sample_rate') or 0):,}",
                        f"{float(row.get('duration_estimate') or 0.0):.3f}s",
                        row.get("category"),
                        row.get("playback_mode"),
                        row.get("root_note"),
                        row.get("usability"),
                    ),
                    tags=(str(row.get("usability") or "Unreviewed"),),
                )
                self.classifier_rows_v47[iid] = row
            tree.tag_configure("Usable", foreground="#147a36")
            tree.tag_configure("Questionable", foreground="#a05a00")
            tree.tag_configure("Reject", foreground="#9b1c1c")
            self.classifier_status_v47.set(f"{len(rows)} sample assets shown.")

        self._local_worker(
            "snddata-sample-classifier-v47",
            lambda: classified_sample_rows(project, query=query, category=category, usability=usability),
            done,
        )

    def _selected_classifier_row_v47(self) -> dict[str, Any] | None:
        selected = self.classifier_tree_v47.selection()
        return self.classifier_rows_v47.get(selected[0]) if selected else None

    def _classifier_selected_v47(self) -> None:
        row = self._selected_classifier_row_v47()
        self.classifier_current_v47 = row
        if row is None:
            return
        self.classifier_label_v47.set(str(row.get("classification_label") or row.get("display_name") or ""))
        self.classifier_category_v47.set(str(row.get("category") or "Unclassified"))
        self.classifier_family_v47.set(str(row.get("family") or ""))
        self.classifier_mode_v47.set(str(row.get("playback_mode") or "Pitched"))
        self.classifier_root_v47.set(int(row.get("root_note") or 60))
        self.classifier_usability_v47.set(str(row.get("usability") or "Unreviewed"))
        self.classifier_tags_v47.set(str(row.get("tags") or ""))
        self.classifier_notes_v47.delete("1.0", "end")
        self.classifier_notes_v47.insert("1.0", str(row.get("classification_notes") or ""))

    def _save_classifier_sample_v47(self) -> None:
        project = self._require_project()
        row = self._selected_classifier_row_v47()
        if project is None or row is None:
            messagebox.showinfo("Sample Classifier", "Select a decoded sample first.")
            return
        try:
            save_classification(
                project,
                int(row.get("resource_offset") or 0),
                int(row.get("sample_id") or 0),
                label=self.classifier_label_v47.get(),
                category=self.classifier_category_v47.get(),
                family=self.classifier_family_v47.get(),
                playback_mode=self.classifier_mode_v47.get(),
                root_note=int(self.classifier_root_v47.get()),
                usability=self.classifier_usability_v47.get(),
                tags=self.classifier_tags_v47.get(),
                notes=self.classifier_notes_v47.get("1.0", "end-1c"),
                source_snapshot=row,
            )
        except Exception as exc:
            messagebox.showerror("Sample Classifier", str(exc))
            return
        self.classifier_status_v47.set("Classification saved.")
        self._refresh_sample_classifier_v47()
        self._refresh_sequencer_sample_choices_v47()

    def _play_classifier_sample_v47(self) -> None:
        row = self._selected_classifier_row_v47()
        if row is None:
            return
        path = Path(str(row.get("output_path") or ""))
        if not path.is_file():
            messagebox.showinfo("Sample Classifier", f"Decoded WAV is missing:\n{path}")
            return
        try:
            self.playback.load(path)
            self.playback.play()
            self.classifier_status_v47.set(f"Playing {row.get('classification_label') or path.name}")
        except Exception as exc:
            messagebox.showerror("Sample Classifier", str(exc))

    def _classifier_context_menu_v47(self, event: tk.Event) -> str:
        iid = self.classifier_tree_v47.identify_row(event.y)
        if iid:
            self.classifier_tree_v47.selection_set(iid)
            self.classifier_tree_v47.focus(iid)
            self._classifier_selected_v47()
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Play Sample", command=self._play_classifier_sample_v47)
        menu.add_command(label="Save Classification", command=self._save_classifier_sample_v47)
        menu.add_command(label="Use in Original Sequencer", command=self._use_classifier_in_sequencer_v47)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _use_classifier_in_sequencer_v47(self) -> None:
        row = self._selected_classifier_row_v47()
        if row is None or self.audio_subnotebook_v47 is None or self.original_sequencer_tab_v47 is None:
            return
        self._refresh_sequencer_sample_choices_v47(preselect=row)
        self.audio_subnotebook_v47.select(self.original_sequencer_tab_v47)

    # ------------------------------------------------------------------
    # Original Sequencer
    # ------------------------------------------------------------------
    def _build_original_sequencer_v47(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        toolbar.columnconfigure(1, weight=1)
        ttk.Label(toolbar, text="MIDI").grid(row=0, column=0, sticky="w")
        self.sequencer_midi_path_v47 = tk.StringVar(value="")
        ttk.Entry(toolbar, textvariable=self.sequencer_midi_path_v47).grid(row=0, column=1, sticky="ew", padx=(5, 6))
        ttk.Button(toolbar, text="Browse", command=self._browse_midi_v47).grid(row=0, column=2)
        ttk.Button(toolbar, text="Analyze", command=self._analyze_midi_v47).grid(row=0, column=3, padx=(5, 0))
        ttk.Button(toolbar, text="Create Original Demo MIDI", command=self._create_demo_midi_v47).grid(row=0, column=4, padx=(5, 0))
        ttk.Button(toolbar, text="Render & Play", command=lambda: self._render_original_sequencer_v47(play=True), style="Accent.TButton").grid(row=0, column=5, padx=(12, 0))
        ttk.Button(toolbar, text="Render WAV", command=lambda: self._render_original_sequencer_v47(play=False)).grid(row=0, column=6, padx=(5, 0))
        ttk.Button(toolbar, text="Stop", command=self._audio_stop).grid(row=0, column=7, padx=(5, 0))

        workspace = ttk.Panedwindow(parent, orient="horizontal")
        workspace.grid(row=1, column=0, sticky="nsew")
        channels = ttk.LabelFrame(workspace, text="MIDI channels / tracks", padding=4)
        channels.columnconfigure(0, weight=1)
        channels.rowconfigure(1, weight=1)
        ttk.Label(channels, text="Map each used MIDI channel to one classified sample instrument.", wraplength=500).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.sequencer_channel_tree_v47 = ttk.Treeview(channels, columns=("notes", "programs", "range", "sample"), show="tree headings", selectmode="browse")
        for key, label, width in (("#0", "Channel", 80), ("notes", "Notes", 60), ("programs", "MIDI Programs", 100), ("range", "Note range", 85), ("sample", "Assigned Fragment sample", 300)):
            self.sequencer_channel_tree_v47.heading(key, text=label)
            self.sequencer_channel_tree_v47.column(key, width=width, stretch=key == "sample")
        channel_y = ttk.Scrollbar(channels, orient="vertical", command=self.sequencer_channel_tree_v47.yview)
        self.sequencer_channel_tree_v47.configure(yscrollcommand=channel_y.set)
        self.sequencer_channel_tree_v47.grid(row=1, column=0, sticky="nsew")
        channel_y.grid(row=1, column=1, sticky="ns")
        self.sequencer_channel_tree_v47.bind("<<TreeviewSelect>>", lambda _event: self._sequencer_channel_selected_v47())
        workspace.add(channels, weight=2)

        right = ttk.Panedwindow(workspace, orient="vertical")
        mapping = ttk.LabelFrame(right, text="Selected channel sample mapping", padding=7)
        mapping.columnconfigure(1, weight=1)
        self.sequencer_sample_choice_v47 = tk.StringVar(value="")
        self.sequencer_mode_v47 = tk.StringVar(value="Pitched")
        self.sequencer_root_v47 = tk.IntVar(value=60)
        self.sequencer_transpose_v47 = tk.IntVar(value=0)
        self.sequencer_channel_gain_v47 = tk.DoubleVar(value=1.0)
        self.sequencer_pan_v47 = tk.IntVar(value=64)
        self.sequencer_gain_v47 = tk.DoubleVar(value=0.8)
        self.sequencer_tempo_scale_v47 = tk.DoubleVar(value=1.0)
        self.sequencer_sample_combo_v47 = ttk.Combobox(mapping, textvariable=self.sequencer_sample_choice_v47, values=(), state="readonly")
        fields = (
            ("Classified sample", self.sequencer_sample_combo_v47),
            ("Mode", ttk.Combobox(mapping, textvariable=self.sequencer_mode_v47, values=PLAYBACK_MODES, state="readonly")),
            ("Root note", ttk.Spinbox(mapping, from_=0, to=127, textvariable=self.sequencer_root_v47)),
            ("Transpose", ttk.Spinbox(mapping, from_=-36, to=36, textvariable=self.sequencer_transpose_v47)),
            ("Channel gain", ttk.Scale(mapping, from_=0.0, to=2.0, variable=self.sequencer_channel_gain_v47)),
            ("Pan", ttk.Scale(mapping, from_=0, to=127, variable=self.sequencer_pan_v47)),
            ("Master gain", ttk.Scale(mapping, from_=0.0, to=1.5, variable=self.sequencer_gain_v47)),
            ("Tempo scale", ttk.Scale(mapping, from_=0.5, to=2.0, variable=self.sequencer_tempo_scale_v47)),
        )
        for row_index, (label, control) in enumerate(fields):
            ttk.Label(mapping, text=label).grid(row=row_index, column=0, sticky="w", padx=(0, 7), pady=3)
            control.grid(row=row_index, column=1, sticky="ew", pady=3)
        actions = ttk.Frame(mapping)
        actions.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(7, 0))
        ttk.Button(actions, text="Save Channel Mapping", command=self._save_channel_mapping_v47, style="Accent.TButton").pack(side="left")
        ttk.Button(actions, text="Auto-map Unassigned", command=self._auto_map_channels_v47).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Play Assigned Sample", command=self._play_assigned_sample_v47).pack(side="left", padx=(6, 0))
        right.add(mapping, weight=2)

        timeline = ttk.LabelFrame(right, text="MIDI note overview", padding=4)
        timeline.columnconfigure(0, weight=1)
        timeline.rowconfigure(0, weight=1)
        self.sequencer_timeline_v47 = tk.Canvas(timeline, background="#10151d", highlightthickness=1, highlightbackground="#344253", height=220)
        self.sequencer_timeline_v47.grid(row=0, column=0, sticky="nsew")
        self.sequencer_timeline_v47.bind("<Configure>", lambda _event: self._draw_sequencer_timeline_v47())
        right.add(timeline, weight=3)
        workspace.add(right, weight=3)

        status = ttk.Frame(parent)
        status.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        status.columnconfigure(0, weight=1)
        self.sequencer_status_v47 = tk.StringVar(value="Import a legally obtained Standard MIDI file or create the original demo. Copyrighted song MIDI files are not bundled.")
        ttk.Label(status, textvariable=self.sequencer_status_v47).grid(row=0, column=0, sticky="w")
        self.sequencer_progress_v47 = ttk.Progressbar(status, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar")
        self.sequencer_progress_v47.grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _browse_midi_v47(self) -> None:
        path = filedialog.askopenfilename(title="Open Standard MIDI file", filetypes=(("MIDI files", "*.mid *.midi"), ("All files", "*.*")))
        if path:
            self.sequencer_midi_path_v47.set(path)
            self._analyze_midi_v47()

    def _create_demo_midi_v47(self) -> None:
        project = self._require_project()
        if project is None:
            return
        target = sound_work_root(project) / "original_sequencer" / "fragmenter_original_demo.mid"
        try:
            write_original_demo_midi(target)
        except Exception as exc:
            messagebox.showerror("Original Sequencer", str(exc))
            return
        self.sequencer_midi_path_v47.set(str(target))
        self._analyze_midi_v47()

    def _analyze_midi_v47(self) -> None:
        project = self.project
        path = self.sequencer_midi_path_v47.get().strip()
        if project is None or not path:
            return
        self.sequencer_status_v47.set("Parsing Standard MIDI tracks, tempo, channels, and note durations…")
        self.sequencer_progress_v47.configure(mode="indeterminate")
        self.sequencer_progress_v47.start(60)

        def done(result: Any, error: Exception | None) -> None:
            self.sequencer_progress_v47.stop()
            self.sequencer_progress_v47.configure(mode="determinate")
            if error:
                self.sequencer_progress_v47["value"] = 0
                self.sequencer_status_v47.set(f"MIDI analysis failed: {error}")
                return
            self.sequencer_progress_v47["value"] = 100
            self.sequencer_parsed_v47 = result
            saved = load_sequencer_state(project)
            if str(saved.get("midi_path") or "") == str(Path(path)):
                self.sequencer_channel_mappings_v47 = {str(key): dict(value) for key, value in (saved.get("channel_mappings") or {}).items() if isinstance(value, dict)}
            else:
                self.sequencer_channel_mappings_v47 = {}
            self._populate_sequencer_channels_v47()
            self._draw_sequencer_timeline_v47()
            summary = result.get("summary") or {}
            self.sequencer_status_v47.set(f"MIDI parsed: {summary.get('notes', 0)} notes, {summary.get('channels', 0)} channels, {float(summary.get('duration_seconds') or 0.0):.2f}s.")

        self._local_worker("original-sequencer-midi-parse-v47", lambda: parse_midi_file(path), done)

    def _populate_sequencer_channels_v47(self) -> None:
        tree = self.sequencer_channel_tree_v47
        tree.delete(*tree.get_children())
        self.sequencer_channel_rows_v47.clear()
        for row in (self.sequencer_parsed_v47 or {}).get("channels") or []:
            channel = int(row.get("channel") or 0)
            iid = f"channel_{channel}"
            mapping = self.sequencer_channel_mappings_v47.get(str(channel)) or {}
            tree.insert("", "end", iid=iid, text=str(channel + 1), values=(row.get("note_count"), ", ".join(str(value) for value in row.get("programs") or []) or "—", f"{row.get('lowest_note')}–{row.get('highest_note')}", mapping.get("label") or "Unassigned"))
            self.sequencer_channel_rows_v47[iid] = row
        first = next(iter(self.sequencer_channel_rows_v47), None)
        if first:
            tree.selection_set(first)
            tree.focus(first)
            self._sequencer_channel_selected_v47()

    def _selected_sequencer_channel_v47(self) -> int | None:
        selected = self.sequencer_channel_tree_v47.selection()
        if not selected:
            return None
        row = self.sequencer_channel_rows_v47.get(selected[0])
        return int(row.get("channel") or 0) if row is not None else None

    def _refresh_sequencer_sample_choices_v47(self, preselect: dict[str, Any] | None = None) -> None:
        project = self.project
        if project is None or self.sequencer_sample_choice_v47 is None:
            return
        try:
            rows = sequencer_sample_rows(project)
        except Exception as exc:
            self.sequencer_status_v47.set(f"Sample choices unavailable: {exc}")
            return
        self.sequencer_sample_choices_v47.clear()
        selected_label = ""
        for row in rows:
            resource = int(row.get("resource_offset") or 0)
            sample_id = int(row.get("sample_id") or 0)
            label = f"0x{resource:X} / {sample_id:04d} — {row.get('classification_label') or row.get('display_name')} [{row.get('category')}, {row.get('playback_mode')}]"
            self.sequencer_sample_choices_v47[label] = row
            if preselect is not None and int(preselect.get("resource_offset") or -1) == resource and int(preselect.get("sample_id") or -1) == sample_id:
                selected_label = label
        if self.sequencer_sample_combo_v47 is not None:
            self.sequencer_sample_combo_v47.configure(values=tuple(self.sequencer_sample_choices_v47))
        if selected_label:
            self.sequencer_sample_choice_v47.set(selected_label)
            row = self.sequencer_sample_choices_v47[selected_label]
            self.sequencer_mode_v47.set(str(row.get("playback_mode") or "Pitched"))
            self.sequencer_root_v47.set(int(row.get("root_note") or 60))

    def _sequencer_channel_selected_v47(self) -> None:
        channel = self._selected_sequencer_channel_v47()
        if channel is None:
            return
        mapping = self.sequencer_channel_mappings_v47.get(str(channel)) or {}
        choice = ""
        key = str(mapping.get("key") or "")
        for label, row in self.sequencer_sample_choices_v47.items():
            if str(row.get("key") or "") == key:
                choice = label
                break
        self.sequencer_sample_choice_v47.set(choice)
        self.sequencer_mode_v47.set(str(mapping.get("playback_mode") or "Pitched"))
        self.sequencer_root_v47.set(int(mapping.get("root_note") if mapping.get("root_note") is not None else 60))
        self.sequencer_transpose_v47.set(int(mapping.get("transpose") or 0))
        self.sequencer_channel_gain_v47.set(float(mapping.get("gain") if mapping.get("gain") is not None else 1.0))
        self.sequencer_pan_v47.set(int(mapping.get("pan") if mapping.get("pan") is not None else 64))

    def _mapping_from_sample_v47(self, row: dict[str, Any]) -> dict[str, Any]:
        return {"key": row.get("key"), "resource_offset": int(row.get("resource_offset") or 0), "sample_id": int(row.get("sample_id") or 0), "label": str(row.get("classification_label") or row.get("display_name") or ""), "output_path": str(row.get("output_path") or ""), "sample_rate": int(row.get("sample_rate") or 0), "playback_mode": self.sequencer_mode_v47.get(), "root_note": int(self.sequencer_root_v47.get()), "transpose": int(self.sequencer_transpose_v47.get()), "gain": float(self.sequencer_channel_gain_v47.get()), "pan": int(float(self.sequencer_pan_v47.get()))}

    def _save_channel_mapping_v47(self) -> None:
        project = self._require_project()
        channel = self._selected_sequencer_channel_v47()
        row = self.sequencer_sample_choices_v47.get(self.sequencer_sample_choice_v47.get())
        if project is None or channel is None or row is None:
            messagebox.showinfo("Original Sequencer", "Select a MIDI channel and a classified sample first.")
            return
        self.sequencer_channel_mappings_v47[str(channel)] = self._mapping_from_sample_v47(row)
        save_sequencer_state(project, midi_path=self.sequencer_midi_path_v47.get(), channel_mappings=self.sequencer_channel_mappings_v47)
        self._populate_sequencer_channels_v47()
        self.sequencer_status_v47.set(f"Mapped MIDI channel {channel + 1} to {row.get('classification_label')}.")

    def _auto_map_channels_v47(self) -> None:
        project = self._require_project()
        parsed = self.sequencer_parsed_v47 or {}
        if project is None or not parsed:
            return
        rows = list(self.sequencer_sample_choices_v47.values())
        if not rows:
            messagebox.showinfo("Original Sequencer", "Classify at least one playable sample first.")
            return
        melodic = next((row for row in rows if row.get("playback_mode") == "Pitched" and row.get("usability") in {"Usable", "Unreviewed"}), rows[0])
        drum = next((row for row in rows if row.get("playback_mode") == "Drum" or row.get("category") == "Percussion"), melodic)
        for channel_row in parsed.get("channels") or []:
            channel = int(channel_row.get("channel") or 0)
            if str(channel) in self.sequencer_channel_mappings_v47:
                continue
            row = drum if channel == 9 else melodic
            self.sequencer_channel_mappings_v47[str(channel)] = {"key": row.get("key"), "resource_offset": int(row.get("resource_offset") or 0), "sample_id": int(row.get("sample_id") or 0), "label": str(row.get("classification_label") or row.get("display_name") or ""), "output_path": str(row.get("output_path") or ""), "sample_rate": int(row.get("sample_rate") or 0), "playback_mode": "Drum" if channel == 9 else str(row.get("playback_mode") or "Pitched"), "root_note": int(row.get("root_note") or 60), "transpose": 0, "gain": 1.0, "pan": 64}
        save_sequencer_state(project, midi_path=self.sequencer_midi_path_v47.get(), channel_mappings=self.sequencer_channel_mappings_v47)
        self._populate_sequencer_channels_v47()
        self.sequencer_status_v47.set("Auto-mapped unassigned channels. Review root notes before treating pitch as meaningful.")

    def _play_assigned_sample_v47(self) -> None:
        channel = self._selected_sequencer_channel_v47()
        mapping = self.sequencer_channel_mappings_v47.get(str(channel)) if channel is not None else None
        path = Path(str((mapping or {}).get("output_path") or ""))
        if not path.is_file():
            return
        try:
            self.playback.load(path)
            self.playback.play()
        except Exception as exc:
            messagebox.showerror("Original Sequencer", str(exc))

    def _render_original_sequencer_v47(self, *, play: bool) -> None:
        project = self._require_project()
        path = self.sequencer_midi_path_v47.get().strip()
        if project is None:
            return
        if not path:
            messagebox.showinfo("Original Sequencer", "Select or create a Standard MIDI file first.")
            return
        if not self.sequencer_channel_mappings_v47:
            messagebox.showinfo("Original Sequencer", "Map at least one MIDI channel to a sample first.")
            return
        self.sequencer_status_v47.set("Rendering MIDI notes through classified Fragment samples…")
        self.sequencer_progress_v47.configure(mode="indeterminate")
        self.sequencer_progress_v47.start(60)
        gain = float(self.sequencer_gain_v47.get())
        tempo_scale = float(self.sequencer_tempo_scale_v47.get())

        def done(result: Any, error: Exception | None) -> None:
            self.sequencer_progress_v47.stop()
            self.sequencer_progress_v47.configure(mode="determinate")
            if error:
                self.sequencer_progress_v47["value"] = 0
                self.sequencer_status_v47.set(f"Original Sequencer render failed: {error}")
                return
            self.sequencer_progress_v47["value"] = 100
            output = Path(str(result.get("output_path") or ""))
            self.sequencer_last_preview_v47 = output
            metadata = result.get("metadata") or {}
            self.sequencer_status_v47.set(f"Rendered {metadata.get('voices', 0)} voices to {output.name}; {float(metadata.get('duration_seconds') or 0.0):.2f}s.")
            if play:
                try:
                    self.playback.load(output)
                    self.playback.set_gain(gain)
                    self.playback.play()
                except Exception as exc:
                    self.sequencer_status_v47.set(f"WAV rendered but playback failed: {exc}")

        self._local_worker("original-sequencer-render-v47", lambda: render_midi_project(project, path, self.sequencer_channel_mappings_v47, master_gain=gain, tempo_scale=tempo_scale), done)

    def _draw_sequencer_timeline_v47(self) -> None:
        canvas = getattr(self, "sequencer_timeline_v47", None)
        parsed = self.sequencer_parsed_v47
        if canvas is None:
            return
        width = max(40, canvas.winfo_width())
        height = max(40, canvas.winfo_height())
        canvas.delete("all")
        canvas.create_text(8, 8, anchor="nw", text="STANDARD MIDI NOTE OVERVIEW", fill="#9fb2c9", font=("Segoe UI", 8, "bold"))
        if not parsed or not parsed.get("notes"):
            canvas.create_text(width / 2, height / 2, text="Load a Standard MIDI file to inspect its note layout.", fill="#718197")
            return
        notes = list(parsed.get("notes") or [])
        duration = max(0.001, float((parsed.get("summary") or {}).get("duration_seconds") or 0.0))
        low = min(int(note.get("note") or 60) for note in notes)
        high = max(int(note.get("note") or 60) for note in notes)
        span = max(1, high - low + 1)
        top = 28
        bottom = height - 12
        for note in notes[:3000]:
            start = float(note.get("start_seconds") or 0.0)
            length = max(0.02, float(note.get("duration_seconds") or 0.1))
            x0 = 8 + start / duration * max(1, width - 16)
            x1 = 8 + min(duration, start + length) / duration * max(1, width - 16)
            y = bottom - (int(note.get("note") or low) - low) / span * max(1, bottom - top)
            canvas.create_line(x0, y, max(x0 + 1, x1), y, fill="#5f89b5", width=2)
        canvas.create_text(8, height - 4, anchor="sw", text=f"{len(notes)} notes • {duration:.2f}s • range {low}–{high}", fill="#9fb2c9", font=("Segoe UI", 8))


def main() -> int:
    app = PublicFragmenterAppV47()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

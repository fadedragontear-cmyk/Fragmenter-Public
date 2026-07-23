#!/usr/bin/env python3
"""V113 layout correction and unified playable-audio classification workspace."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any

from audio_library_research_v1 import (
    export_canonical_audio_research,
    merged_audio_rows,
    save_direct_record,
)
from fragmenter_public_gui_v40 import PublicFragmenterAppV40
from snddata_sample_classification_v1 import (
    PLAYBACK_MODES,
    USABILITY,
    available_categories,
    create_category,
    save_classification,
    send_to_category,
)


class FragmenterLayoutAudioMixinV113:
    """Remove obsolete surfaces and make RUN ALL/audio usable at desktop scale."""

    def __init__(self) -> None:
        self._audio_library_rows_v113: dict[str, dict[str, Any]] = {}
        self._audio_library_generation_v113 = 0
        self._audio_library_search_v113: tk.StringVar | None = None
        self._audio_library_category_filter_v113: tk.StringVar | None = None
        self._audio_library_type_filter_v113: tk.StringVar | None = None
        self._audio_library_status_v113: tk.StringVar | None = None
        self._audio_library_label_v113: tk.StringVar | None = None
        self._audio_library_category_v113: tk.StringVar | None = None
        self._audio_library_mode_v113: tk.StringVar | None = None
        self._audio_library_root_v113: tk.IntVar | None = None
        self._audio_library_usability_v113: tk.StringVar | None = None
        self._audio_library_tags_v113: tk.StringVar | None = None
        self._audio_library_selection_v113: tk.StringVar | None = None
        self._audio_library_tree_v113: ttk.Treeview | None = None
        self._audio_library_notes_v113: tk.Text | None = None
        self._audio_library_category_combo_v113: ttk.Combobox | None = None
        self._audio_library_filter_combo_v113: ttk.Combobox | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Consolidated Workspace V113")
        self.after_idle(self._apply_desktop_geometry_v113)

    # ------------------------------------------------------------------
    # Top-level visibility and desktop geometry.
    # ------------------------------------------------------------------
    def _build_tabs(self) -> None:
        super()._build_tabs()
        self._hide_top_level_tabs_v113({"Research", "Settings"})

    def _hide_top_level_tabs_v113(self, labels: set[str]) -> None:
        notebook = getattr(self, "notebook", None)
        if not isinstance(notebook, ttk.Notebook):
            return
        for tab_id in tuple(notebook.tabs()):
            try:
                label = str(notebook.tab(tab_id, "text"))
            except tk.TclError:
                continue
            if label in labels:
                try:
                    notebook.hide(tab_id)
                except tk.TclError:
                    pass

    def _apply_desktop_geometry_v113(self) -> None:
        try:
            screen_width = max(1200, int(self.winfo_screenwidth()))
            screen_height = max(760, int(self.winfo_screenheight()))
            width = min(1720, max(1320, screen_width - 70))
            height = min(980, max(780, screen_height - 100))
            self.geometry(f"{width}x{height}")
            self.minsize(1180, 720)
        except tk.TclError:
            return
        self.after_idle(self._apply_default_celdra_layout_v50)

    # ------------------------------------------------------------------
    # RUN ALL: no Research prep tab, more stage width, real gremlin space.
    # ------------------------------------------------------------------
    def _build_run_all(self, parent: ttk.Frame) -> None:
        super()._build_run_all(parent)
        self._remove_research_prep_tab_v113()
        self.after_idle(self._apply_default_celdra_layout_v50)

    def _remove_research_prep_tab_v113(self) -> None:
        host = getattr(self, "_run_stage_host_v104", None)
        if host is None:
            return
        for child in tuple(host.winfo_children()):
            if not isinstance(child, ttk.Notebook):
                continue
            for tab_id in tuple(child.tabs()):
                try:
                    label = str(child.tab(tab_id, "text"))
                except tk.TclError:
                    continue
                if label != "Research prep":
                    continue
                try:
                    widget = child.nametowidget(tab_id)
                    child.forget(tab_id)
                    widget.destroy()
                except (KeyError, tk.TclError):
                    pass
        self._research_prep_status_v104 = None

    def _apply_default_celdra_layout_v50(self) -> None:
        try:
            super()._apply_default_celdra_layout_v50()
        except (AttributeError, tk.TclError):
            pass
        # The wider window lets stages and Celdra each receive useful space. The
        # old 46% stage allocation clipped the rightmost Run buttons.
        self._set_sash_fraction_v50(getattr(self, "run_paned", None), 0.57)
        self._set_sash_fraction_v50(getattr(self, "run_top_split_v50", None), 0.61)
        self._set_sash_fraction_v50(getattr(self, "run_bottom_split_v50", None), 0.50)
        self._set_sash_fraction_v50(getattr(self, "celdra_comms_split_v50", None), 0.58)
        self.after_idle(self._apply_middle_layout_v101)

    def _apply_middle_layout_v101(self) -> None:
        pane = getattr(self, "celdra_visual_split_v50", None)
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if pane is None or frame is None or bool(getattr(self, "_celdra_middle_hidden_v103", False)):
            return
        try:
            self.update_idletasks()
            panes = tuple(pane.panes())
            if len(panes) < 3:
                return
            width = max(720, int(pane.winfo_width()))
            # Stable/gremlin content is a real page, not a sliver between portrait
            # and console. Keep all three regions visible at ordinary desktop sizes.
            stable_width = max(245, min(330, round(width * 0.34)))
            console_width = max(245, min(310, round(width * 0.30)))
            avatar_width = max(210, width - stable_width - console_width)
            if avatar_width + stable_width + console_width > width:
                stable_width = max(220, width - avatar_width - console_width)
            pane.sashpos(0, avatar_width)
            pane.sashpos(1, avatar_width + stable_width)
            self._stable_layout_applied_v112 = True
            self._stable_layout_signature_v112 = (round(width / 40) * 40, len(panes))
            wrap = max(205, stable_width - 22)
            for child in frame.winfo_children():
                if isinstance(child, (tk.Label, ttk.Label)):
                    try:
                        child.configure(wraplength=wrap, justify="left")
                    except tk.TclError:
                        pass
            status = getattr(self, "_stable_status_label_v109", None)
            if isinstance(status, tk.Label):
                status.configure(wraplength=wrap, justify="left", anchor="w", font=("Consolas", 8))
        except (AttributeError, tk.TclError):
            pass

    # ------------------------------------------------------------------
    # Audio notebook: one library/classifier, no duplicate classifier page.
    # ------------------------------------------------------------------
    def _build_audio(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.audio_subnotebook_v47 = notebook

        library = ttk.Frame(notebook, padding=7)
        pipeline = ttk.Frame(notebook, padding=7)
        mixer = ttk.Frame(notebook, padding=7)
        sequencer = ttk.Frame(notebook, padding=7)
        notebook.add(library, text="Audio Library / Classifier")
        notebook.add(pipeline, text="Audio Pipeline")
        notebook.add(mixer, text="SNDDATA Research Mixer")
        notebook.add(sequencer, text="Original Sequencer")

        self.sample_classifier_tab_v47 = library
        self.original_sequencer_tab_v47 = sequencer
        self._build_audio_library_classifier_v113(library)
        self._build_audio_pipeline_v38(pipeline)
        self._build_research_mixer_v40(mixer)
        self._build_original_sequencer_v47(sequencer)
        notebook.bind("<<NotebookTabChanged>>", self._audio_subtab_changed_v47, add="+")

    def _audio_subtab_changed_v47(self, _event: Any = None) -> None:
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if notebook is None or getattr(self, "project", None) is None:
            return
        try:
            label = str(notebook.tab(notebook.select(), "text"))
        except tk.TclError:
            return
        if label == "Audio Library / Classifier":
            self._refresh_audio_library_v113()
        elif label == "SNDDATA Research Mixer":
            self._refresh_audio_sequences()
        elif label == "Original Sequencer":
            self._refresh_sequencer_sample_choices_v47()

    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        # Use the compact functional three-column mixer. The V104 lower Celdra guide
        # displaced the sequence list and duplicated help already available elsewhere.
        PublicFragmenterAppV40._build_research_mixer_v40(self, parent)

    # ------------------------------------------------------------------
    # Unified playable audio list and metadata editor.
    # ------------------------------------------------------------------
    def _build_audio_library_classifier_v113(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(toolbar, text="Find").pack(side="left")
        self._audio_library_search_v113 = tk.StringVar(value="")
        search = ttk.Entry(toolbar, textvariable=self._audio_library_search_v113, width=27)
        search.pack(side="left", padx=(5, 9))
        search.bind("<Return>", lambda _event: self._refresh_audio_library_v113())

        ttk.Label(toolbar, text="Category").pack(side="left")
        self._audio_library_category_filter_v113 = tk.StringVar(value="All")
        filter_combo = ttk.Combobox(
            toolbar,
            textvariable=self._audio_library_category_filter_v113,
            values=("All",),
            state="readonly",
            width=17,
        )
        filter_combo.pack(side="left", padx=(5, 9))
        filter_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_audio_library_v113())
        self._audio_library_filter_combo_v113 = filter_combo

        ttk.Label(toolbar, text="Type").pack(side="left")
        self._audio_library_type_filter_v113 = tk.StringVar(value="All")
        type_combo = ttk.Combobox(
            toolbar,
            textvariable=self._audio_library_type_filter_v113,
            values=("All", "SNDDATA Sample", "Direct WAV"),
            state="readonly",
            width=16,
        )
        type_combo.pack(side="left", padx=(5, 9))
        type_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_audio_library_v113())

        ttk.Button(toolbar, text="Refresh", command=self._refresh_audio_library_v113).pack(side="left")
        ttk.Button(toolbar, text="Play Selected", command=self._play_audio_library_v113, style="Accent.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Stop", command=self._audio_stop).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Create Category", command=self._create_audio_category_v113).pack(side="left", padx=(12, 0))
        ttk.Button(toolbar, text="Update Canonical Research", command=self._export_audio_research_v113).pack(side="left", padx=(6, 0))

        self._audio_library_status_v113 = tk.StringVar(value="Open a project to load playable WAVs.")
        ttk.Label(toolbar, textvariable=self._audio_library_status_v113).pack(side="right", padx=(10, 0))

        split = ttk.Panedwindow(parent, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew")

        listing = ttk.LabelFrame(split, text="Playable audio and decoded samples", padding=4)
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            listing,
            columns=("type", "category", "rate", "duration", "usable", "path"),
            show="tree headings",
            selectmode="extended",
        )
        for key, label, width, stretch in (
            ("#0", "Audio", 260, True),
            ("type", "Type", 115, False),
            ("category", "Category", 125, False),
            ("rate", "Rate", 78, False),
            ("duration", "Duration", 78, False),
            ("usable", "Usability", 88, False),
            ("path", "Decoded path", 420, True),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=stretch)
        ybar = ttk.Scrollbar(listing, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(listing, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        tree.bind("<<TreeviewSelect>>", lambda _event: self._audio_library_selected_v113())
        tree.bind("<Double-1>", self._audio_library_double_click_v113)
        tree.bind("<Button-3>", self._audio_library_context_menu_v113)
        tree.tag_configure("Usable", foreground="#147a36")
        tree.tag_configure("Questionable", foreground="#a05a00")
        tree.tag_configure("Reject", foreground="#9b1c1c")
        split.add(listing, weight=4)
        self._audio_library_tree_v113 = tree

        # Compatibility aliases used by existing refresh and playback hooks.
        self.simple_audio_tree = tree
        self.classifier_tree_v47 = tree
        self.classifier_rows_v47 = self._audio_library_rows_v113

        editor = ttk.LabelFrame(split, text="Category, playback metadata, and notes", padding=7)
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(7, weight=1)
        self._audio_library_selection_v113 = tk.StringVar(value="No selection")
        ttk.Label(editor, textvariable=self._audio_library_selection_v113, font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5)
        )
        self._audio_library_label_v113 = tk.StringVar()
        self._audio_library_category_v113 = tk.StringVar(value="Unclassified")
        self._audio_library_mode_v113 = tk.StringVar(value="Pitched")
        self._audio_library_root_v113 = tk.IntVar(value=60)
        self._audio_library_usability_v113 = tk.StringVar(value="Unreviewed")
        self._audio_library_tags_v113 = tk.StringVar()
        category_combo = ttk.Combobox(editor, textvariable=self._audio_library_category_v113, values=(), state="readonly")
        self._audio_library_category_combo_v113 = category_combo
        fields = (
            ("Label", ttk.Entry(editor, textvariable=self._audio_library_label_v113)),
            ("Category", category_combo),
            ("Playback mode", ttk.Combobox(editor, textvariable=self._audio_library_mode_v113, values=PLAYBACK_MODES, state="readonly")),
            ("Root MIDI note", ttk.Spinbox(editor, from_=0, to=127, textvariable=self._audio_library_root_v113)),
            ("Usability", ttk.Combobox(editor, textvariable=self._audio_library_usability_v113, values=USABILITY, state="readonly")),
            ("Tags", ttk.Entry(editor, textvariable=self._audio_library_tags_v113)),
        )
        for index, (label, control) in enumerate(fields, 1):
            ttk.Label(editor, text=label).grid(row=index, column=0, sticky="w", padx=(0, 7), pady=3)
            control.grid(row=index, column=1, sticky="ew", pady=3)
        ttk.Label(editor, text="Notes").grid(row=7, column=0, sticky="nw", padx=(0, 7), pady=3)
        notes = tk.Text(editor, height=10, wrap="word")
        notes.grid(row=7, column=1, sticky="nsew", pady=3)
        notes_y = ttk.Scrollbar(editor, orient="vertical", command=notes.yview)
        notes.configure(yscrollcommand=notes_y.set)
        notes_y.grid(row=7, column=2, sticky="ns")
        self._audio_library_notes_v113 = notes
        actions = ttk.Frame(editor)
        actions.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Save Metadata to Selected", command=self._save_audio_metadata_v113, style="Accent.TButton").pack(side="left")
        ttk.Button(actions, text="Play", command=self._play_audio_library_v113).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Create Category", command=self._create_audio_category_v113).pack(side="left", padx=(6, 0))
        split.add(editor, weight=2)

        self._audio_library_search_v113.trace_add("write", lambda *_: self._debounce_audio_library_v113())
        self.after_idle(self._sync_audio_categories_v113)

    def _debounce_audio_library_v113(self) -> None:
        identifier = getattr(self, "_audio_library_after_v113", None)
        if identifier is not None:
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
        self._audio_library_after_v113 = self.after(220, self._refresh_audio_library_v113)

    def _sync_audio_categories_v113(self, rows: list[dict[str, Any]] | None = None) -> tuple[str, ...]:
        project = getattr(self, "project", None)
        categories: list[str] = []
        if project is not None:
            try:
                categories.extend(available_categories(project))
            except Exception:
                pass
        for row in rows or self._audio_library_rows_v113.values():
            value = str(row.get("category") or "").strip()
            if value and value not in categories:
                categories.append(value)
        categories = sorted(dict.fromkeys(categories), key=str.casefold)
        values = ("All", *categories)
        if self._audio_library_filter_combo_v113 is not None:
            self._audio_library_filter_combo_v113.configure(values=values)
        if self._audio_library_category_combo_v113 is not None:
            self._audio_library_category_combo_v113.configure(values=tuple(categories))
        return tuple(categories)

    def _refresh_audio_library_v113(self) -> None:
        project = getattr(self, "project", None)
        tree = self._audio_library_tree_v113
        if project is None or tree is None:
            if self._audio_library_status_v113 is not None:
                self._audio_library_status_v113.set("No project loaded")
            return
        self._audio_library_generation_v113 += 1
        generation = self._audio_library_generation_v113
        selected_keys = {
            str(self._audio_library_rows_v113.get(iid, {}).get("unified_key") or "")
            for iid in tree.selection()
        }
        query = self._audio_library_search_v113.get().strip().casefold() if self._audio_library_search_v113 is not None else ""
        category = self._audio_library_category_filter_v113.get() if self._audio_library_category_filter_v113 is not None else "All"
        item_type = self._audio_library_type_filter_v113.get() if self._audio_library_type_filter_v113 is not None else "All"
        if self._audio_library_status_v113 is not None:
            self._audio_library_status_v113.set("Loading playable audio inventory…")

        def work() -> list[dict[str, Any]]:
            output: list[dict[str, Any]] = []
            for row in merged_audio_rows(project):
                haystack = " ".join(
                    str(row.get(key) or "")
                    for key in ("name", "category", "item_type", "output_path", "tags", "notes")
                ).casefold()
                if query and query not in haystack:
                    continue
                if category != "All" and str(row.get("category") or "") != category:
                    continue
                if item_type != "All" and str(row.get("item_type") or "") != item_type:
                    continue
                output.append(row)
            return output

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._audio_library_generation_v113:
                return
            tree.delete(*tree.get_children())
            self._audio_library_rows_v113.clear()
            if error:
                if self._audio_library_status_v113 is not None:
                    self._audio_library_status_v113.set(f"Audio inventory failed: {error}")
                return
            restored: list[str] = []
            for index, row in enumerate(rows or []):
                iid = f"audio_v113_{index}"
                rate = int(row.get("sample_rate") or 0)
                duration = float(row.get("duration_estimate") or 0.0)
                usability = str(row.get("usability") or "Unreviewed")
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=str(row.get("name") or Path(str(row.get("output_path") or "audio.wav")).name),
                    values=(
                        str(row.get("item_type") or ""),
                        str(row.get("category") or "Unclassified"),
                        f"{rate:,} Hz" if rate else "—",
                        f"{duration:.3f}s",
                        usability,
                        str(row.get("output_path") or ""),
                    ),
                    tags=(usability,),
                )
                self._audio_library_rows_v113[iid] = dict(row)
                if str(row.get("unified_key") or "") in selected_keys:
                    restored.append(iid)
            self._sync_audio_categories_v113(list(rows or []))
            if restored:
                tree.selection_set(restored)
                tree.focus(restored[0])
                tree.see(restored[0])
            elif tree.get_children(""):
                first = tree.get_children("")[0]
                tree.selection_set(first)
                tree.focus(first)
            self._audio_library_selected_v113()
            if self._audio_library_status_v113 is not None:
                samples = sum(str(row.get("item_type")) == "SNDDATA Sample" for row in rows or [])
                direct = len(rows or []) - samples
                self._audio_library_status_v113.set(
                    f"{len(rows or []):,} playable rows: {samples:,} SNDDATA samples, {direct:,} direct WAVs. Ctrl/Shift select multiple."
                )

        self._local_worker("unified-audio-library-v113", work, done)

    def _selected_audio_rows_v113(self) -> list[dict[str, Any]]:
        tree = self._audio_library_tree_v113
        if tree is None:
            return []
        return [self._audio_library_rows_v113[iid] for iid in tree.selection() if iid in self._audio_library_rows_v113]

    def _selected_classifier_row_v47(self) -> dict[str, Any] | None:
        rows = self._selected_audio_rows_v113()
        return rows[0] if rows else None

    def _audio_library_selected_v113(self) -> None:
        rows = self._selected_audio_rows_v113()
        if self._audio_library_selection_v113 is not None:
            self._audio_library_selection_v113.set(
                "No selection" if not rows else str(rows[0].get("name") or "audio") if len(rows) == 1 else f"{len(rows)} audio rows selected"
            )
        if not rows:
            return
        row = rows[0]
        self._audio_library_label_v113.set(str(row.get("name") or ""))
        self._audio_library_category_v113.set(str(row.get("category") or "Unclassified"))
        self._audio_library_mode_v113.set(str(row.get("playback_mode") or "Pitched"))
        self._audio_library_root_v113.set(int(row.get("root_note") if row.get("root_note") is not None else 60))
        self._audio_library_usability_v113.set(str(row.get("usability") or "Unreviewed"))
        self._audio_library_tags_v113.set(str(row.get("tags") or ""))
        if self._audio_library_notes_v113 is not None:
            self._audio_library_notes_v113.delete("1.0", "end")
            self._audio_library_notes_v113.insert("1.0", str(row.get("notes") or ""))

    def _audio_library_double_click_v113(self, event: tk.Event) -> str:
        tree = self._audio_library_tree_v113
        if tree is not None:
            iid = tree.identify_row(event.y)
            if iid:
                tree.focus(iid)
                if iid not in tree.selection():
                    tree.selection_set(iid)
        self._play_audio_library_v113()
        return "break"

    def _play_audio_library_v113(self) -> None:
        rows = self._selected_audio_rows_v113()
        if not rows:
            return
        path = Path(str(rows[0].get("output_path") or ""))
        if not path.is_file():
            messagebox.showinfo("Audio Library", f"Decoded WAV is missing:\n{path}")
            return
        try:
            self.playback.load(path)
            self.playback.play()
            if self._audio_library_status_v113 is not None:
                self._audio_library_status_v113.set(f"Playing {rows[0].get('name') or path.name}")
        except Exception as exc:
            messagebox.showerror("Audio Library", str(exc))

    def _play_classifier_sample_v47(self) -> None:
        self._play_audio_library_v113()

    def _simple_audio_primary_action(self) -> None:
        self._play_audio_library_v113()

    def _refresh_simple_audio(self) -> None:
        self._refresh_audio_library_v113()

    def _refresh_sample_classifier_v47(self) -> None:
        self._refresh_audio_library_v113()

    def _create_audio_category_v113(self, *, assign: bool = False) -> None:
        project = self._require_project()
        if project is None:
            return
        name = simpledialog.askstring("Create audio category", "New project-local category name:", parent=self)
        if name is None:
            return
        try:
            created = create_category(project, name)
        except Exception as exc:
            messagebox.showerror("Create audio category", str(exc))
            return
        self._sync_audio_categories_v113()
        if self._audio_library_category_v113 is not None:
            self._audio_library_category_v113.set(created)
        if assign:
            self._send_audio_category_v113(created)
        elif self._audio_library_status_v113 is not None:
            self._audio_library_status_v113.set(f"Category ready: {created}")

    def _save_row_metadata_v113(self, row: dict[str, Any], *, preserve_label: bool) -> None:
        project = self._require_project()
        if project is None:
            return
        label = str(row.get("name") or "audio") if preserve_label else self._audio_library_label_v113.get()
        category = self._audio_library_category_v113.get()
        mode = self._audio_library_mode_v113.get()
        root = int(self._audio_library_root_v113.get())
        usability = self._audio_library_usability_v113.get()
        tags = self._audio_library_tags_v113.get()
        notes = self._audio_library_notes_v113.get("1.0", "end-1c") if self._audio_library_notes_v113 is not None else ""
        if row.get("is_snddata_sample"):
            save_classification(
                project,
                int(row.get("resource_offset") or 0),
                int(row.get("sample_id") or 0),
                label=label,
                category=category,
                family=str(row.get("family") or ""),
                playback_mode=mode,
                root_note=root,
                usability=usability,
                tags=tags,
                notes=notes,
                source_snapshot=row,
            )
        else:
            save_direct_record(
                project,
                row,
                label=label,
                category=category,
                playback_mode=mode,
                root_note=root,
                usability=usability,
                tags=tags,
                notes=notes,
            )

    def _save_audio_metadata_v113(self) -> None:
        rows = self._selected_audio_rows_v113()
        if not rows:
            messagebox.showinfo("Audio Library", "Select one or more audio rows first.")
            return
        try:
            for row in rows:
                self._save_row_metadata_v113(row, preserve_label=len(rows) > 1)
        except Exception as exc:
            messagebox.showerror("Audio Library", str(exc))
            return
        if self._audio_library_status_v113 is not None:
            self._audio_library_status_v113.set(f"Saved category, playback metadata, and notes to {len(rows)} row(s).")
        self._refresh_audio_library_v113()
        self._refresh_sequencer_sample_choices_v47()

    def _save_classifier_sample_v47(self) -> None:
        self._save_audio_metadata_v113()

    def _send_audio_category_v113(self, category: str) -> None:
        project = self._require_project()
        rows = self._selected_audio_rows_v113()
        if project is None or not rows:
            messagebox.showinfo("Audio Library", "Select one or more audio rows first.")
            return
        try:
            for row in rows:
                if row.get("is_snddata_sample"):
                    send_to_category(
                        project,
                        int(row.get("resource_offset") or 0),
                        int(row.get("sample_id") or 0),
                        category,
                        source_snapshot=row,
                    )
                else:
                    save_direct_record(
                        project,
                        row,
                        label=str(row.get("name") or "audio"),
                        category=category,
                        playback_mode=str(row.get("playback_mode") or "One-shot"),
                        root_note=int(row.get("root_note") if row.get("root_note") is not None else 60),
                        usability=str(row.get("usability") or "Unreviewed"),
                        tags=str(row.get("tags") or ""),
                        notes=str(row.get("notes") or ""),
                    )
        except Exception as exc:
            messagebox.showerror("Send to category", str(exc))
            return
        if self._audio_library_status_v113 is not None:
            self._audio_library_status_v113.set(f"Sent {len(rows)} row(s) to {category}.")
        self._refresh_audio_library_v113()
        self._refresh_sequencer_sample_choices_v47()

    def _audio_library_context_menu_v113(self, event: tk.Event) -> str:
        tree = self._audio_library_tree_v113
        if tree is None:
            return "break"
        iid = tree.identify_row(event.y)
        if iid and iid not in tree.selection():
            tree.selection_set(iid)
            tree.focus(iid)
            self._audio_library_selected_v113()
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Play Selected", command=self._play_audio_library_v113)
        categories = tk.Menu(menu, tearoff=False)
        for category in self._sync_audio_categories_v113():
            categories.add_command(label=category, command=lambda value=category: self._send_audio_category_v113(value))
        menu.add_cascade(label="Send to Category", menu=categories)
        menu.add_command(label="Create Category", command=lambda: self._create_audio_category_v113(assign=True))
        menu.add_separator()
        menu.add_command(label="Save Notes / Metadata", command=self._save_audio_metadata_v113)
        menu.add_command(label="Update Canonical Research", command=self._export_audio_research_v113)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _classifier_context_menu_v47(self, event: tk.Event) -> str:
        return self._audio_library_context_menu_v113(event)

    def _export_audio_research_v113(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            report = export_canonical_audio_research(project)
        except Exception as exc:
            messagebox.showerror("Canonical audio research", str(exc))
            return
        if self._audio_library_status_v113 is not None:
            self._audio_library_status_v113.set(
                f"Canonical research updated: {report.get('items', 0)} rows, {report.get('with_notes', 0)} with notes."
            )
        messagebox.showinfo(
            "Canonical audio research updated",
            f"JSON:\n{report['json_path']}\n\nCSV:\n{report['csv_path']}",
        )

#!/usr/bin/env python3
"""V46: split SNDDATA research workspace, sortable assets, flags, notes and Celdra reserve."""
from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from fragmenter_public_gui import _json_text, _open_path, _replace_text
from fragmenter_public_gui_v45 import PublicFragmenterAppV45
from snddata_music_system_v5 import MusicSystemError
from snddata_music_system_v9 import render_sequence_event_proof
from snddata_research_bundle_v2 import (
    build_flagged_research_bundle,
    build_selected_research_bundle,
)
from snddata_research_workspace_v1 import (
    asset_key,
    flagged_records,
    get_record,
    save_record,
)
from snddata_research_workbench_v1 import FILTERS, ROUTING_MODES


class PublicFragmenterAppV46(PublicFragmenterAppV45):
    """Turn the mixer into a persistent, resizable audio-research workstation."""

    def __init__(self) -> None:
        self._research_active_key_v46: str | None = None
        self._research_active_kind_v46: str | None = None
        self._research_active_row_v46: dict[str, Any] | None = None
        self._research_sort_reverse_v46: dict[tuple[str, str], bool] = {}
        self.audio_notes_target_v46: tk.StringVar | None = None
        self.audio_deck_sequence_v46: tk.StringVar | None = None
        self.audio_deck_candidate_v46: tk.StringVar | None = None
        self.audio_deck_mode_v46: tk.StringVar | None = None
        self.audio_notes_text_v46: tk.Text | None = None
        self.audio_flag_tree_v46: ttk.Treeview | None = None
        self.audio_research_tabs_v46: ttk.Notebook | None = None
        self.audio_deck_canvas_v46: tk.Canvas | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — SNDDATA Research Deck")
        self.after_idle(self._set_audio_sashes_v46)

    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(
            controls,
            text="Rebuild Mixer Index",
            command=self._rebuild_mixer_index_v40,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(controls, text="Refresh Catalog", command=self._refresh_audio_sequences).pack(
            side="left", padx=(6, 12)
        )
        ttk.Label(controls, text="Find sequence").pack(side="left")
        self.audio_sequence_search_v40 = tk.StringVar(value="")
        search = ttk.Entry(controls, textvariable=self.audio_sequence_search_v40, width=24)
        search.pack(side="left", padx=(5, 10))
        self.audio_sequence_search_v40.trace_add(
            "write", lambda *_: self._debounce_mixer_refresh_v40()
        )
        ttk.Label(controls, text="Show").pack(side="left")
        self.audio_sequence_filter_v40 = tk.StringVar(value="All")
        status_filter = ttk.Combobox(
            controls,
            textvariable=self.audio_sequence_filter_v40,
            values=FILTERS,
            state="readonly",
            width=15,
        )
        status_filter.pack(side="left", padx=(5, 10))
        status_filter.bind(
            "<<ComboboxSelected>>", lambda _event: self._refresh_audio_sequences()
        )
        ttk.Label(controls, text="Routing").pack(side="left")
        self.audio_routing_mode = tk.StringVar(value="Auto")
        routing = ttk.Combobox(
            controls,
            textvariable=self.audio_routing_mode,
            values=ROUTING_MODES,
            state="readonly",
            width=19,
        )
        routing.pack(side="left", padx=(5, 10))
        routing.bind(
            "<<ComboboxSelected>>", lambda _event: self._refresh_audio_candidates()
        )
        ttk.Button(
            controls,
            text="Open Audio Reports",
            command=self._open_audio_reports_v40,
        ).pack(side="right")
        self.audio_readiness_v40 = tk.StringVar(
            value="Load a project to inspect mixer readiness."
        )
        ttk.Label(controls, textvariable=self.audio_readiness_v40).pack(
            side="right", padx=(12, 14)
        )

        self.audio_workspace_paned_v46 = ttk.Panedwindow(parent, orient="vertical")
        self.audio_workspace_paned_v46.grid(row=1, column=0, sticky="nsew")

        top = ttk.Panedwindow(self.audio_workspace_paned_v46, orient="horizontal")
        self._build_sequence_list_v46(top)
        self._build_candidate_list_v46(top)
        self._build_playback_deck_v46(top)
        self.audio_workspace_paned_v46.add(top, weight=3)

        bottom = ttk.Panedwindow(self.audio_workspace_paned_v46, orient="horizontal")
        self._build_research_quadrant_v46(bottom)
        self._build_celdra_reserve_v46(bottom)
        self.audio_workspace_paned_v46.add(bottom, weight=2)
        self.audio_bottom_paned_v46 = bottom

        status = ttk.Frame(parent)
        status.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        status.columnconfigure(1, weight=1)
        self.audio_status = tk.StringVar(
            value="Mixer catalog has not been loaded. Right-click assets for research actions."
        )
        ttk.Label(status, textvariable=self.audio_status).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.audio_progress = ttk.Progressbar(
            status,
            maximum=100.0,
            mode="determinate",
            style="Accent.Horizontal.TProgressbar",
        )
        self.audio_progress.grid(row=0, column=1, sticky="ew")
        ttk.Label(
            status, text=f"Playback: {self.playback.backend_name}"
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

        self.sequence_payloads = self._mixer_sequence_rows_v40
        self.program_payloads = self._mixer_candidate_rows_v40

    def _build_sequence_list_v46(self, parent: ttk.Panedwindow) -> None:
        frame = ttk.LabelFrame(parent, text="Sequences", padding=4)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text="Sortable sequence assets — right-click to flag or annotate",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.sequence_tree = ttk.Treeview(
            frame,
            columns=("notes", "tracks", "routing", "renderable", "review"),
            show="tree headings",
            selectmode="browse",
        )
        headings = (
            ("#0", "Sequence", 180, False),
            ("notes", "Notes", 58, True),
            ("tracks", "Tracks", 52, True),
            ("routing", "Routing", 125, False),
            ("renderable", "Ready", 52, True),
            ("review", "Saved / reviewed", 115, False),
        )
        for key, label, width, numeric in headings:
            self.sequence_tree.heading(
                key,
                text=label,
                command=lambda c=key, n=numeric: self._sort_tree_v46(
                    self.sequence_tree, c, n
                ),
            )
            self.sequence_tree.column(
                key, width=width, stretch=key in {"#0", "routing", "review"}
            )
        ybar = ttk.Scrollbar(
            frame, orient="vertical", command=self.sequence_tree.yview
        )
        xbar = ttk.Scrollbar(
            frame, orient="horizontal", command=self.sequence_tree.xview
        )
        self.sequence_tree.configure(
            yscrollcommand=ybar.set, xscrollcommand=xbar.set
        )
        self.sequence_tree.grid(row=1, column=0, sticky="nsew")
        ybar.grid(row=1, column=1, sticky="ns")
        xbar.grid(row=2, column=0, sticky="ew")
        self.sequence_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._sequence_selected_v46()
        )
        self._bind_research_context_v46(self.sequence_tree, "sequence")
        parent.add(frame, weight=2)

    def _build_candidate_list_v46(self, parent: ttk.Panedwindow) -> None:
        frame = ttk.LabelFrame(parent, text="Program candidates", padding=4)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text="Ranked hypotheses, not confirmed sequence-to-bank links",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.program_tree = ttk.Treeview(
            frame,
            columns=("rank", "status", "coverage", "review", "missing"),
            show="tree headings",
            selectmode="browse",
        )
        headings = (
            ("#0", "Program resource", 150, False),
            ("rank", "Rank", 42, True),
            ("status", "Renderer", 95, False),
            ("coverage", "Samples", 62, False),
            ("review", "Verdict", 68, False),
            ("missing", "First missing wall", 190, False),
        )
        for key, label, width, numeric in headings:
            self.program_tree.heading(
                key,
                text=label,
                command=lambda c=key, n=numeric: self._sort_tree_v46(
                    self.program_tree, c, n
                ),
            )
            self.program_tree.column(
                key, width=width, stretch=key in {"#0", "missing"}
            )
        ybar = ttk.Scrollbar(
            frame, orient="vertical", command=self.program_tree.yview
        )
        xbar = ttk.Scrollbar(
            frame, orient="horizontal", command=self.program_tree.xview
        )
        self.program_tree.configure(
            yscrollcommand=ybar.set, xscrollcommand=xbar.set
        )
        self.program_tree.grid(row=1, column=0, sticky="nsew")
        ybar.grid(row=1, column=1, sticky="ns")
        xbar.grid(row=2, column=0, sticky="ew")
        self.program_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._candidate_selected_v40()
        )
        self._bind_research_context_v46(self.program_tree, "candidate")
        parent.add(frame, weight=2)

    def _build_playback_deck_v46(self, parent: ttk.Panedwindow) -> None:
        deck = ttk.LabelFrame(parent, text="Playback / render deck", padding=7)
        deck.columnconfigure(0, weight=1)
        deck.rowconfigure(1, weight=1)

        identity = ttk.Frame(deck)
        identity.grid(row=0, column=0, sticky="ew")
        identity.columnconfigure(1, weight=1)
        self.audio_deck_sequence_v46 = tk.StringVar(value="No sequence selected")
        self.audio_deck_candidate_v46 = tk.StringVar(value="No Program candidate selected")
        self.audio_deck_mode_v46 = tk.StringVar(
            value="EVENT / PCM PROOF  •  mapped instruments unresolved"
        )
        ttk.Label(identity, text="NOW INSPECTING", font=("Segoe UI", 8, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            identity,
            textvariable=self.audio_deck_mode_v46,
            font=("Segoe UI", 8),
        ).grid(row=0, column=1, sticky="e")
        ttk.Label(
            identity,
            textvariable=self.audio_deck_sequence_v46,
            font=("Segoe UI", 13, "bold"),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Label(
            identity, textvariable=self.audio_deck_candidate_v46
        ).grid(row=2, column=0, columnspan=2, sticky="w")

        self.audio_deck_canvas_v46 = tk.Canvas(
            deck,
            height=112,
            background="#10151d",
            highlightthickness=1,
            highlightbackground="#344253",
        )
        self.audio_deck_canvas_v46.grid(row=1, column=0, sticky="nsew", pady=(7, 7))
        self.audio_deck_canvas_v46.bind(
            "<Configure>", lambda _event: self._draw_audio_deck_v46()
        )

        primary = ttk.Frame(deck)
        primary.grid(row=2, column=0, sticky="ew")
        ttk.Button(
            primary,
            text="Render Event / PCM Proof",
            command=self._render_event_proof_v46,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            primary,
            text="Render Candidate",
            command=lambda: self._render_selected_v40(play=True),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            primary,
            text="Rough Proof",
            command=self._render_rough_proof_v44,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            primary,
            text="Silent Gaps",
            command=self._render_with_silent_placeholders_v43,
        ).pack(side="left", padx=(6, 0))

        transport = ttk.Frame(deck)
        transport.grid(row=3, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(
            transport, text="Render WAV", command=lambda: self._render_selected_v40(play=False)
        ).pack(side="left")
        ttk.Button(
            transport, text="Play Last", command=self._play_last_preview_v40
        ).pack(side="left", padx=(5, 0))
        ttk.Button(transport, text="Stop", command=self._audio_stop).pack(
            side="left", padx=(5, 0)
        )
        self.pause_button = ttk.Button(
            transport,
            text="Pause",
            command=self._audio_pause,
            state="normal" if self.playback.supports_pause else "disabled",
        )
        self.pause_button.pack(side="left", padx=(5, 0))
        self.resume_button = ttk.Button(
            transport,
            text="Resume",
            command=self._audio_resume,
            state="normal" if self.playback.supports_pause else "disabled",
        )
        self.resume_button.pack(side="left", padx=(5, 12))
        self.audio_gain = tk.DoubleVar(value=0.8)
        ttk.Label(transport, text="Gain").pack(side="left")
        ttk.Scale(
            transport,
            from_=0.0,
            to=1.0,
            variable=self.audio_gain,
            length=120,
        ).pack(side="left", padx=(4, 0))
        parent.add(deck, weight=2)

    def _build_research_quadrant_v46(self, parent: ttk.Panedwindow) -> None:
        frame = ttk.LabelFrame(parent, text="Evidence / samples / research", padding=5)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        tabs = ttk.Notebook(frame)
        tabs.grid(row=0, column=0, sticky="nsew")
        self.audio_research_tabs_v46 = tabs

        evidence = ttk.Frame(tabs)
        samples = ttk.Frame(tabs)
        notes = ttk.Frame(tabs)
        bundle = ttk.Frame(tabs)
        tabs.add(evidence, text="Evidence")
        tabs.add(samples, text="Samples")
        tabs.add(notes, text="Notes & Flags")
        tabs.add(bundle, text="Research Bundle")

        evidence.rowconfigure(0, weight=1)
        evidence.columnconfigure(0, weight=1)
        self.audio_details = tk.Text(evidence, wrap="word", state="disabled")
        evidence_y = ttk.Scrollbar(
            evidence, orient="vertical", command=self.audio_details.yview
        )
        self.audio_details.configure(yscrollcommand=evidence_y.set)
        self.audio_details.grid(row=0, column=0, sticky="nsew")
        evidence_y.grid(row=0, column=1, sticky="ns")

        samples.rowconfigure(0, weight=1)
        samples.columnconfigure(0, weight=1)
        self.audio_sample_tree_v40 = ttk.Treeview(
            samples,
            columns=("rate", "duration", "status"),
            show="tree headings",
            selectmode="browse",
        )
        for key, label, width, numeric in (
            ("#0", "Sample asset", 270, False),
            ("rate", "Rate", 85, True),
            ("duration", "Duration", 82, True),
            ("status", "Status", 100, False),
        ):
            self.audio_sample_tree_v40.heading(
                key,
                text=label,
                command=lambda c=key, n=numeric: self._sort_tree_v46(
                    self.audio_sample_tree_v40, c, n
                ),
            )
            self.audio_sample_tree_v40.column(
                key, width=width, stretch=key in {"#0", "status"}
            )
        sample_y = ttk.Scrollbar(
            samples, orient="vertical", command=self.audio_sample_tree_v40.yview
        )
        sample_x = ttk.Scrollbar(
            samples, orient="horizontal", command=self.audio_sample_tree_v40.xview
        )
        self.audio_sample_tree_v40.configure(
            yscrollcommand=sample_y.set, xscrollcommand=sample_x.set
        )
        self.audio_sample_tree_v40.grid(row=0, column=0, sticky="nsew")
        sample_y.grid(row=0, column=1, sticky="ns")
        sample_x.grid(row=1, column=0, sticky="ew")
        self.audio_sample_tree_v40.bind(
            "<Double-1>", lambda _event: self._play_selected_sample_v40()
        )
        self.audio_sample_tree_v40.bind(
            "<<TreeviewSelect>>", lambda _event: self._sample_selected_v46()
        )
        self._bind_research_context_v46(self.audio_sample_tree_v40, "sample")
        ttk.Button(
            samples,
            text="Play Selected Sample",
            command=self._play_selected_sample_v40,
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))

        notes.columnconfigure(0, weight=1)
        notes.rowconfigure(2, weight=1)
        self.audio_notes_target_v46 = tk.StringVar(value="No research asset selected")
        ttk.Label(
            notes,
            textvariable=self.audio_notes_target_v46,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=5, pady=(5, 3))
        ttk.Label(
            notes,
            text="Persistent asset notes. Use the context menu to choose the exact sequence, candidate, or sample target.",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", padx=5, pady=(0, 5))
        note_frame = ttk.Frame(notes)
        note_frame.grid(row=2, column=0, sticky="nsew", padx=5)
        note_frame.columnconfigure(0, weight=1)
        note_frame.rowconfigure(0, weight=1)
        self.audio_notes_text_v46 = tk.Text(note_frame, height=7, wrap="word")
        note_y = ttk.Scrollbar(
            note_frame, orient="vertical", command=self.audio_notes_text_v46.yview
        )
        self.audio_notes_text_v46.configure(yscrollcommand=note_y.set)
        self.audio_notes_text_v46.grid(row=0, column=0, sticky="nsew")
        note_y.grid(row=0, column=1, sticky="ns")
        note_actions = ttk.Frame(notes)
        note_actions.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        ttk.Button(
            note_actions,
            text="Save Asset Notes",
            command=self._save_active_notes_v46,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            note_actions,
            text="Toggle Research Flag",
            command=self._toggle_active_flag_v46,
        ).pack(side="left", padx=(6, 0))

        verdict = ttk.LabelFrame(notes, text="Candidate verdict / exact-SNDDATA mapping", padding=5)
        verdict.grid(row=4, column=0, sticky="ew", padx=5, pady=(0, 5))
        verdict.columnconfigure(1, weight=1)
        ttk.Label(verdict, text="Verdict note").grid(row=0, column=0, sticky="w")
        self.audio_review_notes_v40 = tk.StringVar(value="")
        ttk.Entry(
            verdict, textvariable=self.audio_review_notes_v40
        ).grid(row=0, column=1, sticky="ew", padx=(5, 7))
        ttk.Button(
            verdict,
            text="Plausible",
            command=lambda: self._review_candidate_v40("plausible"),
        ).grid(row=0, column=2)
        ttk.Button(
            verdict,
            text="Confirm",
            command=lambda: self._review_candidate_v40("confirmed"),
        ).grid(row=0, column=3, padx=(5, 0))
        ttk.Button(
            verdict,
            text="Reject",
            command=lambda: self._review_candidate_v40("rejected"),
        ).grid(row=0, column=4, padx=(5, 0))
        ttk.Button(
            verdict,
            text="Clear",
            command=self._clear_candidate_review_v40,
        ).grid(row=0, column=5, padx=(5, 0))

        bundle.columnconfigure(0, weight=1)
        bundle.rowconfigure(1, weight=1)
        ttk.Label(
            bundle,
            text="Flag any sequence, candidate, or sample from its right-click menu. Flagged exports contain JSON/text evidence only.",
            wraplength=760,
        ).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.audio_flag_tree_v46 = ttk.Treeview(
            bundle,
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
            bundle, orient="vertical", command=self.audio_flag_tree_v46.yview
        )
        self.audio_flag_tree_v46.configure(yscrollcommand=flag_y.set)
        self.audio_flag_tree_v46.grid(row=1, column=0, sticky="nsew", padx=(5, 0))
        flag_y.grid(row=1, column=1, sticky="ns")
        bundle_actions = ttk.Frame(bundle)
        bundle_actions.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
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
        ttk.Button(
            bundle_actions,
            text="Refresh Flags",
            command=self._refresh_flagged_assets_v46,
        ).pack(side="left", padx=(6, 0))
        self._refresh_flagged_assets_v46()
        parent.add(frame, weight=3)

    def _build_celdra_reserve_v46(self, parent: ttk.Panedwindow) -> None:
        frame = ttk.LabelFrame(parent, text="Celdra — reserved research space", padding=7)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text="Reserved for guided format analysis, anomaly summaries, and experiment suggestions.",
            wraplength=420,
        ).grid(row=0, column=0, sticky="w", pady=(0, 7))
        console = tk.Text(
            frame,
            wrap="word",
            state="normal",
            background="#121820",
            foreground="#b8c6d9",
            insertbackground="#b8c6d9",
        )
        console.insert(
            "1.0",
            "CELDRA RESERVE\n\n"
            "No automated conclusions are active here yet.\n\n"
            "Planned inputs:\n"
            "• selected sequence parser health\n"
            "• Program/slot anomalies\n"
            "• flagged sample evidence\n"
            "• preview failures and substitution logs\n"
            "• proposed next experiments\n",
        )
        console.configure(state="disabled")
        console.grid(row=1, column=0, sticky="nsew")
        parent.add(frame, weight=2)

    def _sort_tree_v46(
        self, tree: ttk.Treeview, column: str, numeric: bool = False
    ) -> None:
        key = (str(tree), column)
        reverse = not self._research_sort_reverse_v46.get(key, False)
        self._research_sort_reverse_v46[key] = reverse

        def value(iid: str) -> Any:
            raw = tree.item(iid, "text") if column == "#0" else tree.set(iid, column)
            if not numeric:
                return str(raw).casefold()
            text = str(raw).replace(",", "").replace("s", "").strip()
            if "/" in text:
                left, _right = text.split("/", 1)
                text = left
            try:
                return float(text)
            except ValueError:
                return float("-inf")

        rows = list(tree.get_children(""))
        rows.sort(key=value, reverse=reverse)
        for index, iid in enumerate(rows):
            tree.move(iid, "", index)

    def _bind_research_context_v46(
        self, tree: ttk.Treeview, kind: str
    ) -> None:
        tree.bind(
            "<Button-3>",
            lambda event, widget=tree, asset_kind=kind: self._show_research_menu_v46(
                event, widget, asset_kind
            ),
        )

    def _show_research_menu_v46(
        self, event: tk.Event, tree: ttk.Treeview, kind: str
    ) -> str:
        iid = tree.identify_row(event.y)
        if not iid:
            return "break"
        tree.selection_set(iid)
        tree.focus(iid)
        target = self._target_for_kind_v46(kind)
        if target is None:
            return "break"
        key, row = target
        project = self.project
        flagged = bool(get_record(project, key).get("flagged")) if project else False
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="Remove Research Flag" if flagged else "Flag for Research Bundle",
            command=lambda: self._set_target_flag_v46(kind, row, not flagged),
        )
        menu.add_command(
            label="Edit Persistent Notes",
            command=lambda: self._activate_research_target_v46(kind, row, select_notes=True),
        )
        menu.add_command(
            label="Copy Asset Identifier",
            command=lambda: self._copy_asset_identifier_v46(kind, row),
        )
        if kind == "sample":
            menu.add_separator()
            menu.add_command(
                label="Play Sample", command=self._play_selected_sample_v40
            )
        if kind == "candidate":
            menu.add_separator()
            menu.add_command(
                label="Export Selected Research Bundle",
                command=self._export_selected_bundle_v46,
            )
            menu.add_command(
                label="Render Rough Proof", command=self._render_rough_proof_v44
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _target_for_kind_v46(
        self, kind: str
    ) -> tuple[str, dict[str, Any]] | None:
        sequence = self._selected_sequence_v40()
        if sequence is None:
            return None
        sequence_id = str(sequence.get("sequence_id") or "")
        if kind == "sequence":
            return asset_key("sequence", sequence_id=sequence_id), sequence
        candidate = self._selected_candidate_v40()
        if kind == "candidate" and candidate is not None:
            resource = int(candidate.get("resource_offset") or 0)
            return (
                asset_key(
                    "candidate",
                    sequence_id=sequence_id,
                    resource_offset=resource,
                ),
                candidate,
            )
        sample = self._selected_sample_v46()
        if kind == "sample" and candidate is not None and sample is not None:
            resource = int(candidate.get("resource_offset") or 0)
            sample_id = int(
                sample.get("sample_id")
                if sample.get("sample_id") is not None
                else sample.get("index") or 0
            )
            selected_sample = {**sample, "resource_offset": resource, "sample_id": sample_id}
            return (
                asset_key(
                    "sample",
                    sequence_id=sequence_id,
                    resource_offset=resource,
                    sample_id=sample_id,
                ),
                selected_sample,
            )
        return None

    def _selected_sample_v46(self) -> dict[str, Any] | None:
        selected = self.audio_sample_tree_v40.selection()
        return self._mixer_sample_rows_v40.get(selected[0]) if selected else None

    def _sequence_selected_v46(self) -> None:
        self._refresh_audio_candidates()
        sequence = self._selected_sequence_v40()
        if sequence is not None:
            self._activate_research_target_v46("sequence", sequence)
        self._sync_audio_deck_v46()

    def _candidate_selected_v40(self) -> None:
        super()._candidate_selected_v40()
        candidate = self._selected_candidate_v40()
        if candidate is not None:
            self._activate_research_target_v46("candidate", candidate)
        self._sync_audio_deck_v46()

    def _sample_selected_v46(self) -> None:
        sample = self._selected_sample_v46()
        if sample is not None:
            self._activate_research_target_v46("sample", sample)

    def _activate_research_target_v46(
        self, kind: str, row: dict[str, Any], *, select_notes: bool = False
    ) -> None:
        project = self.project
        target = self._target_for_kind_v46(kind)
        if project is None or target is None:
            return
        key, selected_row = target
        record = get_record(project, key)
        self._research_active_key_v46 = key
        self._research_active_kind_v46 = kind
        self._research_active_row_v46 = dict(selected_row)
        if self.audio_notes_target_v46 is not None:
            self.audio_notes_target_v46.set(
                f"{kind.title()} research target: {key}"
                + ("  [FLAGGED]" if record.get("flagged") else "")
            )
        if self.audio_notes_text_v46 is not None:
            self.audio_notes_text_v46.delete("1.0", "end")
            self.audio_notes_text_v46.insert("1.0", str(record.get("notes") or ""))
        if select_notes and self.audio_research_tabs_v46 is not None:
            self.audio_research_tabs_v46.select(2)

    def _save_active_notes_v46(self) -> None:
        project = self._require_project()
        if project is None or not self._research_active_key_v46:
            messagebox.showinfo("SNDDATA research notes", "Select a research asset first.")
            return
        sequence = self._selected_sequence_v40() or {}
        row = self._research_active_row_v46 or {}
        kind = str(self._research_active_kind_v46 or "asset")
        resource = row.get("resource_offset")
        sample_id = (
            row.get("sample_id")
            if row.get("sample_id") is not None
            else row.get("index")
        )
        notes = (
            self.audio_notes_text_v46.get("1.0", "end-1c")
            if self.audio_notes_text_v46 is not None
            else ""
        )
        current = get_record(project, self._research_active_key_v46)
        save_record(
            project,
            self._research_active_key_v46,
            kind=kind,
            sequence_id=str(sequence.get("sequence_id") or ""),
            resource_offset=int(resource) if resource is not None else None,
            sample_id=int(sample_id) if sample_id is not None else None,
            flagged=bool(current.get("flagged")),
            notes=notes,
            snapshot=row,
        )
        self.audio_status.set(f"Saved persistent research notes for {self._research_active_key_v46}.")
        self._refresh_flagged_assets_v46()

    def _toggle_active_flag_v46(self) -> None:
        if not self._research_active_kind_v46 or not self._research_active_row_v46:
            messagebox.showinfo("SNDDATA research flag", "Select a research asset first.")
            return
        project = self.project
        if project is None or not self._research_active_key_v46:
            return
        flagged = bool(get_record(project, self._research_active_key_v46).get("flagged"))
        self._set_target_flag_v46(
            self._research_active_kind_v46,
            self._research_active_row_v46,
            not flagged,
        )

    def _set_target_flag_v46(
        self, kind: str, row: dict[str, Any], flagged: bool
    ) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        if project is None or sequence is None:
            return
        target = self._target_for_kind_v46(kind)
        if target is None:
            return
        key, selected_row = target
        resource = selected_row.get("resource_offset")
        sample_id = (
            selected_row.get("sample_id")
            if selected_row.get("sample_id") is not None
            else selected_row.get("index")
        )
        current = get_record(project, key)
        save_record(
            project,
            key,
            kind=kind,
            sequence_id=str(sequence.get("sequence_id") or ""),
            resource_offset=int(resource) if resource is not None else None,
            sample_id=int(sample_id) if sample_id is not None else None,
            flagged=flagged,
            notes=str(current.get("notes") or ""),
            snapshot=selected_row,
        )
        self._activate_research_target_v46(kind, row)
        self._refresh_flagged_assets_v46()
        self.audio_status.set(
            f"{'Flagged' if flagged else 'Unflagged'} {key} for research export."
        )

    def _refresh_flagged_assets_v46(self) -> None:
        tree = self.audio_flag_tree_v46
        project = self.project
        if tree is None:
            return
        tree.delete(*tree.get_children())
        if project is None:
            return
        for index, row in enumerate(flagged_records(project)):
            resource = (
                f"0x{int(row['resource_offset']):X}"
                if row.get("resource_offset") is not None
                else ""
            )
            sample = (
                f"{int(row['sample_id']):04d}"
                if row.get("sample_id") is not None
                else ""
            )
            tree.insert(
                "",
                "end",
                iid=f"flagged_{index}",
                values=(
                    row.get("kind"),
                    row.get("sequence_id"),
                    resource,
                    sample,
                    str(row.get("notes") or "").replace("\n", " ")[:240],
                ),
            )

    def _copy_asset_identifier_v46(
        self, kind: str, row: dict[str, Any]
    ) -> None:
        target = self._target_for_kind_v46(kind)
        if target is None:
            return
        key, _selected = target
        self.clipboard_clear()
        self.clipboard_append(key)
        self.audio_status.set(f"Copied asset identifier: {key}")

    def _draw_audio_deck_v46(self) -> None:
        canvas = self.audio_deck_canvas_v46
        if canvas is None:
            return
        width = max(20, canvas.winfo_width())
        height = max(20, canvas.winfo_height())
        canvas.delete("all")
        middle = height / 2.0
        canvas.create_line(0, middle, width, middle, fill="#344253")
        bars = max(24, width // 12)
        for index in range(bars):
            phase = index / max(1, bars - 1)
            amplitude = (
                0.18
                + 0.52 * abs(math.sin(phase * math.pi * 5.0))
                + 0.12 * abs(math.sin(phase * math.pi * 17.0))
            )
            x = 6 + phase * max(1, width - 12)
            half = amplitude * height * 0.38
            canvas.create_line(x, middle - half, x, middle + half, fill="#5f89b5")
        canvas.create_line(width * 0.18, 8, width * 0.18, height - 8, fill="#d7a84b", width=2)
        canvas.create_text(
            10,
            10,
            anchor="nw",
            text="PREVIEW MONITOR  /  waveform becomes authoritative only after mapped PCM",
            fill="#9fb2c9",
            font=("Segoe UI", 8),
        )

    def _sync_audio_deck_v46(self) -> None:
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if self.audio_deck_sequence_v46 is not None:
            self.audio_deck_sequence_v46.set(
                str((sequence or {}).get("sequence_id") or "No sequence selected")
            )
        if self.audio_deck_candidate_v46 is not None:
            if candidate is None:
                self.audio_deck_candidate_v46.set("No Program candidate selected")
            else:
                self.audio_deck_candidate_v46.set(
                    f"{candidate.get('resource_id')}  •  {candidate.get('status')}  •  "
                    f"coverage {candidate.get('coverage')}"
                )

    def _render_event_proof_v46(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None:
            return
        if sequence is None:
            messagebox.showinfo(
                "SNDDATA event / PCM proof",
                "Select a sequence first. A Program candidate is optional.",
            )
            return
        preferred_resource = (
            int(candidate["resource_offset"])
            if candidate is not None and candidate.get("resource_offset") is not None
            else None
        )
        gain = float(self.audio_gain.get())
        self.audio_status.set(
            f"Building independent event / PCM proof for {sequence['sequence_id']}…"
        )
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(result: Any, error: Exception | None) -> None:
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                if isinstance(error, MusicSystemError):
                    _replace_text(
                        self.audio_details,
                        _json_text(
                            {
                                "status": "event_pcm_proof_failed",
                                "error": str(error),
                                "remaining_walls": error.missing,
                                "sequence": sequence,
                                "preferred_candidate": candidate,
                            }
                        ),
                    )
                    self.audio_status.set(str(error))
                else:
                    messagebox.showerror("SNDDATA event / PCM proof", str(error))
                return
            self.audio_progress["value"] = 100.0
            output = Path(str(result["output_path"]))
            self.audio_last_preview_v40 = output
            _replace_text(self.audio_details, _json_text(result))
            try:
                self.playback.load(output)
                self.playback.set_gain(gain)
                self.playback.play()
            except Exception as exc:
                self.audio_status.set(
                    f"Event-proof WAV rendered but playback failed: {exc}"
                )
                return
            evidence = (result.get("metadata") or {}).get("event_timing_evidence") or {}
            mode = str(evidence.get("timing_mode") or "unknown")
            notes = int(evidence.get("proof_note_events") or 0)
            if self.audio_deck_mode_v46 is not None:
                self.audio_deck_mode_v46.set(
                    f"EVENT / PCM PROOF  •  {mode}  •  {notes} pulse(s)"
                )
            self.audio_status.set(
                f"Playing event / PCM proof: {output.name}; {notes} pulse(s), mode {mode}. "
                "Programs, slots and instruments remain bypassed."
            )

        self._local_worker(
            "snddata-event-pcm-proof-v46",
            lambda: render_sequence_event_proof(
                project,
                sequence["sequence_id"],
                preferred_resource_offset=preferred_resource,
                master_gain=gain,
            ),
            done,
        )

    def _export_selected_bundle_v46(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None:
            return
        if sequence is None or candidate is None:
            messagebox.showinfo(
                "SNDDATA research bundle",
                "Select a sequence and Program candidate first.",
            )
            return
        try:
            result = build_selected_research_bundle(
                project,
                sequence,
                candidate,
                playback_backend=self.playback.backend_name,
            )
            target = Path(str(result["bundle_path"]))
            self.audio_status.set(
                f"Selected research bundle written: {target.name}; "
                f"{int(result.get('flagged_assets') or 0)} flagged asset record(s) included."
            )
            messagebox.showinfo(
                "SNDDATA research bundle",
                "Diagnostic bundle created. JSON/text evidence only; no game binaries or WAV files.\n\n"
                f"{target}",
            )
            _open_path(target.parent)
        except Exception as exc:
            messagebox.showerror("SNDDATA research bundle", str(exc))

    def _export_flagged_bundle_v46(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            result = build_flagged_research_bundle(
                project,
                playback_backend=self.playback.backend_name,
            )
            target = Path(str(result["bundle_path"]))
            self.audio_status.set(
                f"Flagged research bundle written: {target.name}; "
                f"{int(result.get('flagged_assets') or 0)} asset(s)."
            )
            messagebox.showinfo(
                "SNDDATA flagged research bundle",
                "Flagged diagnostic bundle created. JSON/text evidence only; no game binaries or WAV files.\n\n"
                f"{target}",
            )
            _open_path(target.parent)
        except Exception as exc:
            messagebox.showerror("SNDDATA flagged research bundle", str(exc))

    def _export_research_bundle_v42(self) -> None:
        self._export_selected_bundle_v46()

    def _set_audio_sashes_v46(self) -> None:
        try:
            total = self.audio_workspace_paned_v46.winfo_height()
            if total > 200:
                self.audio_workspace_paned_v46.sashpos(0, int(total * 0.56))
        except (AttributeError, tk.TclError):
            pass
        try:
            total = self.audio_bottom_paned_v46.winfo_width()
            if total > 200:
                self.audio_bottom_paned_v46.sashpos(0, int(total * 0.68))
        except (AttributeError, tk.TclError):
            pass


def main() -> int:
    app = PublicFragmenterAppV46()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

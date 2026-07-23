#!/usr/bin/env python3
"""V40: lazy project startup and a workflow-oriented SNDDATA research mixer."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from fragmenter_public_gui import _json_text, _open_path, _replace_text
from fragmenter_public_gui_v39 import PublicFragmenterAppV39
from project_report_layout_v1 import migrate_report_layout
from project_sound_v1 import canonical_snddata_path, sound_reports_root
from snddata_mapping_store_v1 import mapping_store_path, remove_mapping, set_mapping
from snddata_music_system_v5 import MusicSystemError, analyze_project_snddata, render_sequence
from snddata_research_store_v1 import clear_candidate_review, set_candidate_review
from snddata_research_workbench_v1 import (
    FILTERS,
    ROUTING_MODES,
    candidate_rows,
    readiness,
    sample_rows,
    sequence_rows,
)


class PublicFragmenterAppV40(PublicFragmenterAppV39):
    """Load heavy tabs on demand and make SNDDATA audition decisions explicit."""

    def __init__(self) -> None:
        self._lazy_loaded_tabs_v40: set[str] = set()
        self._project_generation_v40 = 0
        self._mixer_sequence_generation_v40 = 0
        self._mixer_candidate_generation_v40 = 0
        self._mixer_sample_generation_v40 = 0
        self._mixer_search_after_v40: str | None = None
        self._mixer_sequence_rows_v40: dict[str, dict[str, Any]] = {}
        self._mixer_candidate_rows_v40: dict[str, dict[str, Any]] = {}
        self._mixer_sample_rows_v40: dict[str, dict[str, Any]] = {}
        self.audio_last_preview_v40: Path | None = None
        self.audio_sequence_search_v40: tk.StringVar | None = None
        self.audio_sequence_filter_v40: tk.StringVar | None = None
        self.audio_review_notes_v40: tk.StringVar | None = None
        self.audio_readiness_v40: tk.StringVar | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Audio Research Workbench")
        self.notebook.bind("<<NotebookTabChanged>>", self._tab_changed_v40, add="+")

    # ------------------------------------------------------------------
    # Startup: keep Tk responsive and hydrate heavy tabs only when opened.
    # ------------------------------------------------------------------
    def _project_loaded(self) -> None:
        assert self.project is not None
        self._project_generation_v40 += 1
        generation = self._project_generation_v40
        self._lazy_loaded_tabs_v40 = {"Setup", "RUN ALL", "Settings"}
        self.project_label.set(str(self.project.project_path))
        self.setup_vars["iso"].set(self.project.sources.iso_path)
        self.setup_vars["server"].set(self.project.sources.area_server_root)
        self.setup_vars["saves"].set(self.project.sources.server_save_dir)
        self.setup_vars["card"].set(self.project.sources.memory_card_path)
        self.setup_vars["workspace"].set(self.project.workspace_dir)
        self._refresh_setup()
        self._refresh_run_plan()
        self._load_settings()
        self.status_label.set("Project loaded. 3D, audio, server, backups, and reports load when their tabs are opened.")
        self.current_task_label.set("Project ready; background maintenance queued")

        project = self.project

        def done(result: Any, error: Exception | None) -> None:
            if generation != self._project_generation_v40:
                return
            if error:
                self._append_log(f"Background report migration warning: {error}")
                self.current_task_label.set("Project ready; report migration warning")
            else:
                summary = (result or {}).get("summary") or {}
                self._append_log(
                    "Background report migration complete: "
                    f"{int(summary.get('moved') or 0)} moved, "
                    f"{int(summary.get('deduplicated') or 0)} deduplicated, "
                    f"{int(summary.get('preserved_conflicts') or 0)} conflicts preserved."
                )
                self.current_task_label.set("Idle")
                if self._selected_tab_label_v40() == "Reports":
                    self._refresh_reports()

        self._local_worker("project-report-migration-v40", lambda: migrate_report_layout(project), done)
        self.after_idle(self._tab_changed_v40)

    def _selected_tab_label_v40(self) -> str:
        try:
            return str(self.notebook.tab(self.notebook.select(), "text"))
        except tk.TclError:
            return ""

    def _tab_changed_v40(self, _event: Any = None) -> None:
        label = self._selected_tab_label_v40()
        if not label or label in self._lazy_loaded_tabs_v40 or self.project is None:
            return
        self._lazy_loaded_tabs_v40.add(label)

        def hydrate() -> None:
            if label == "3D / Assets":
                self._refresh_visual_assets()
            elif label == "Audio":
                self._refresh_audio_readiness_v40()
                self._refresh_audio_sequences()
            elif label == "Server Explorer":
                self._refresh_server()
            elif label == "Backups":
                self._refresh_backups()
            elif label == "Reports":
                self._refresh_reports()

        self.after_idle(hydrate)

    def _refresh_all(self) -> None:
        """Refresh only already-opened workspaces after a pipeline operation."""
        self._refresh_setup()
        self._refresh_run_plan()
        self._load_settings()
        loaded = set(self._lazy_loaded_tabs_v40)
        if "3D / Assets" in loaded:
            self._refresh_visual_assets()
        if "Audio" in loaded:
            self._refresh_audio_readiness_v40()
            self._refresh_audio_sequences()
        if "Server Explorer" in loaded:
            self._refresh_server()
        if "Backups" in loaded:
            self._refresh_backups()
        if "Reports" in loaded:
            self._refresh_reports()

    # ------------------------------------------------------------------
    # Audio workspace: library, pipeline, and one functional research flow.
    # ------------------------------------------------------------------
    def _build_audio(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")
        library = ttk.Frame(notebook, padding=7)
        pipeline = ttk.Frame(notebook, padding=7)
        research = ttk.Frame(notebook, padding=7)
        notebook.add(library, text="Audio Library")
        notebook.add(pipeline, text="Audio Pipeline")
        notebook.add(research, text="SNDDATA Research Mixer")
        self._build_simple_audio_library(library)
        self._build_audio_pipeline_v38(pipeline)
        self._build_research_mixer_v40(research)

    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        workflow = ttk.LabelFrame(parent, text="Research workflow", padding=6)
        workflow.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        workflow.columnconfigure(0, weight=1)
        ttk.Label(
            workflow,
            text=(
                "1 Rebuild the mixer index after SNDDATA extraction  →  2 choose a sequence  →  "
                "3 audition renderer-complete candidates  →  4 mark plausible, confirmed, or rejected. "
                "Non-renderable candidates remain inspectable and state the exact missing Program/sample wall."
            ),
            wraplength=1250,
        ).grid(row=0, column=0, sticky="ew")
        self.audio_readiness_v40 = tk.StringVar(value="Load a project to inspect mixer readiness.")
        ttk.Label(workflow, textvariable=self.audio_readiness_v40).grid(row=1, column=0, sticky="ew", pady=(5, 0))

        controls = ttk.Frame(parent)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(controls, text="Rebuild Mixer Index", command=self._rebuild_mixer_index_v40, style="Accent.TButton").pack(side="left")
        ttk.Button(controls, text="Refresh Catalog", command=self._refresh_audio_sequences).pack(side="left", padx=(6, 12))
        ttk.Label(controls, text="Find sequence").pack(side="left")
        self.audio_sequence_search_v40 = tk.StringVar(value="")
        search = ttk.Entry(controls, textvariable=self.audio_sequence_search_v40, width=24)
        search.pack(side="left", padx=(5, 10))
        self.audio_sequence_search_v40.trace_add("write", lambda *_: self._debounce_mixer_refresh_v40())
        ttk.Label(controls, text="Show").pack(side="left")
        self.audio_sequence_filter_v40 = tk.StringVar(value="All")
        status_filter = ttk.Combobox(controls, textvariable=self.audio_sequence_filter_v40, values=FILTERS, state="readonly", width=16)
        status_filter.pack(side="left", padx=(5, 10))
        status_filter.bind("<<ComboboxSelected>>", lambda _event: self._refresh_audio_sequences())
        ttk.Label(controls, text="Routing").pack(side="left")
        self.audio_routing_mode = tk.StringVar(value="Auto")
        routing = ttk.Combobox(controls, textvariable=self.audio_routing_mode, values=ROUTING_MODES, state="readonly", width=20)
        routing.pack(side="left", padx=(5, 10))
        routing.bind("<<ComboboxSelected>>", lambda _event: self._refresh_audio_candidates())
        ttk.Button(controls, text="Open Audio Reports", command=self._open_audio_reports_v40).pack(side="right")

        main = ttk.Panedwindow(parent, orient="horizontal")
        main.grid(row=2, column=0, sticky="nsew")

        sequence_frame = ttk.LabelFrame(main, text="1. Sequences", padding=4)
        sequence_frame.rowconfigure(0, weight=1)
        sequence_frame.columnconfigure(0, weight=1)
        self.sequence_tree = ttk.Treeview(
            sequence_frame,
            columns=("notes", "tracks", "routing", "renderable", "review"),
            show="tree headings",
            selectmode="browse",
        )
        self.sequence_tree.heading("#0", text="Sequence")
        for key, label, width in (
            ("notes", "Notes", 65),
            ("tracks", "Tracks", 55),
            ("routing", "Routing", 145),
            ("renderable", "Playable", 65),
            ("review", "Saved / reviewed", 120),
        ):
            self.sequence_tree.heading(key, text=label)
            self.sequence_tree.column(key, width=width, stretch=key == "routing")
        self.sequence_tree.column("#0", width=175, stretch=False)
        sequence_y = ttk.Scrollbar(sequence_frame, orient="vertical", command=self.sequence_tree.yview)
        self.sequence_tree.configure(yscrollcommand=sequence_y.set)
        self.sequence_tree.grid(row=0, column=0, sticky="nsew")
        sequence_y.grid(row=0, column=1, sticky="ns")
        self.sequence_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_audio_candidates())
        main.add(sequence_frame, weight=2)

        candidate_frame = ttk.LabelFrame(main, text="2. Program candidates", padding=4)
        candidate_frame.rowconfigure(0, weight=1)
        candidate_frame.columnconfigure(0, weight=1)
        self.program_tree = ttk.Treeview(
            candidate_frame,
            columns=("rank", "status", "coverage", "review", "missing"),
            show="tree headings",
            selectmode="browse",
        )
        self.program_tree.heading("#0", text="Program resource")
        for key, label, width in (
            ("rank", "Rank", 45),
            ("status", "Renderer", 105),
            ("coverage", "Samples", 70),
            ("review", "Verdict", 75),
            ("missing", "First missing wall", 210),
        ):
            self.program_tree.heading(key, text=label)
            self.program_tree.column(key, width=width, stretch=key == "missing")
        self.program_tree.column("#0", width=155, stretch=False)
        candidate_y = ttk.Scrollbar(candidate_frame, orient="vertical", command=self.program_tree.yview)
        self.program_tree.configure(yscrollcommand=candidate_y.set)
        self.program_tree.grid(row=0, column=0, sticky="nsew")
        candidate_y.grid(row=0, column=1, sticky="ns")
        self.program_tree.bind("<<TreeviewSelect>>", lambda _event: self._candidate_selected_v40())
        main.add(candidate_frame, weight=2)

        evidence = ttk.LabelFrame(main, text="3. Evidence and samples", padding=4)
        evidence.rowconfigure(0, weight=1)
        evidence.columnconfigure(0, weight=1)
        evidence_tabs = ttk.Notebook(evidence)
        evidence_tabs.grid(row=0, column=0, sticky="nsew")
        summary_tab = ttk.Frame(evidence_tabs)
        samples_tab = ttk.Frame(evidence_tabs)
        evidence_tabs.add(summary_tab, text="Readable summary")
        evidence_tabs.add(samples_tab, text="Required samples")
        summary_tab.rowconfigure(0, weight=1)
        summary_tab.columnconfigure(0, weight=1)
        self.audio_details = tk.Text(summary_tab, wrap="word", state="disabled")
        summary_y = ttk.Scrollbar(summary_tab, orient="vertical", command=self.audio_details.yview)
        self.audio_details.configure(yscrollcommand=summary_y.set)
        self.audio_details.grid(row=0, column=0, sticky="nsew")
        summary_y.grid(row=0, column=1, sticky="ns")
        samples_tab.rowconfigure(0, weight=1)
        samples_tab.columnconfigure(0, weight=1)
        self.audio_sample_tree_v40 = ttk.Treeview(
            samples_tab,
            columns=("rate", "duration", "status"),
            show="tree headings",
            selectmode="browse",
        )
        self.audio_sample_tree_v40.heading("#0", text="Sample")
        for key, label, width in (("rate", "Rate", 80), ("duration", "Duration", 75), ("status", "Status", 100)):
            self.audio_sample_tree_v40.heading(key, text=label)
            self.audio_sample_tree_v40.column(key, width=width, stretch=key == "status")
        sample_y = ttk.Scrollbar(samples_tab, orient="vertical", command=self.audio_sample_tree_v40.yview)
        self.audio_sample_tree_v40.configure(yscrollcommand=sample_y.set)
        self.audio_sample_tree_v40.grid(row=0, column=0, sticky="nsew")
        sample_y.grid(row=0, column=1, sticky="ns")
        self.audio_sample_tree_v40.bind("<Double-1>", lambda _event: self._play_selected_sample_v40())
        ttk.Button(samples_tab, text="Play Selected Sample", command=self._play_selected_sample_v40).grid(row=1, column=0, sticky="w", pady=(5, 0))
        main.add(evidence, weight=2)

        playback = ttk.LabelFrame(parent, text="4. Audition and record the result", padding=6)
        playback.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(playback, text="Render & Play Candidate", command=lambda: self._render_selected_v40(play=True), style="Accent.TButton").pack(side="left")
        ttk.Button(playback, text="Render WAV Only", command=lambda: self._render_selected_v40(play=False)).pack(side="left", padx=(6, 0))
        ttk.Button(playback, text="Play Last Preview", command=self._play_last_preview_v40).pack(side="left", padx=(6, 0))
        ttk.Button(playback, text="Stop", command=self._audio_stop).pack(side="left", padx=(6, 0))
        self.pause_button = ttk.Button(playback, text="Pause", command=self._audio_pause, state="normal" if self.playback.supports_pause else "disabled")
        self.pause_button.pack(side="left", padx=(6, 0))
        self.resume_button = ttk.Button(playback, text="Resume", command=self._audio_resume, state="normal" if self.playback.supports_pause else "disabled")
        self.resume_button.pack(side="left", padx=(6, 12))
        self.audio_gain = tk.DoubleVar(value=0.8)
        ttk.Label(playback, text="Gain").pack(side="left")
        ttk.Scale(playback, from_=0.0, to=1.0, variable=self.audio_gain, length=110).pack(side="left", padx=(4, 12))
        ttk.Label(playback, text="Notes").pack(side="left")
        self.audio_review_notes_v40 = tk.StringVar(value="")
        ttk.Entry(playback, textvariable=self.audio_review_notes_v40, width=28).pack(side="left", padx=(4, 8), fill="x", expand=True)
        ttk.Button(playback, text="Plausible", command=lambda: self._review_candidate_v40("plausible")).pack(side="left")
        ttk.Button(playback, text="Confirm Mapping", command=lambda: self._review_candidate_v40("confirmed")).pack(side="left", padx=(5, 0))
        ttk.Button(playback, text="Reject", command=lambda: self._review_candidate_v40("rejected")).pack(side="left", padx=(5, 0))
        ttk.Button(playback, text="Clear Review", command=self._clear_candidate_review_v40).pack(side="left", padx=(5, 0))

        status = ttk.Frame(parent)
        status.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        status.columnconfigure(1, weight=1)
        self.audio_status = tk.StringVar(value="Mixer catalog has not been loaded.")
        ttk.Label(status, textvariable=self.audio_status).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.audio_progress = ttk.Progressbar(status, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar")
        self.audio_progress.grid(row=0, column=1, sticky="ew")
        ttk.Label(status, text=f"Playback: {self.playback.backend_name}").grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.sequence_payloads = self._mixer_sequence_rows_v40
        self.program_payloads = self._mixer_candidate_rows_v40

    # ------------------------------------------------------------------
    # Research mixer loading and selection.
    # ------------------------------------------------------------------
    def _debounce_mixer_refresh_v40(self) -> None:
        if self._mixer_search_after_v40 is not None:
            try:
                self.after_cancel(self._mixer_search_after_v40)
            except tk.TclError:
                pass
        self._mixer_search_after_v40 = self.after(250, self._refresh_audio_sequences)

    def _refresh_audio_readiness_v40(self) -> None:
        if self.audio_readiness_v40 is None or self.project is None:
            return
        try:
            state = readiness(self.project)
            missing = []
            if not state["snddata_exists"]:
                missing.append("SNDDATA source")
            if not state["sample_report_exists"]:
                missing.append("sample library")
            if not state["catalog_exists"]:
                missing.append("mixer index")
            backend = self.playback.backend_name
            if missing:
                self.audio_readiness_v40.set("Not ready: " + ", ".join(missing) + ". Run the Audio Pipeline or the missing individual stage.")
            else:
                self.audio_readiness_v40.set(f"Ready for evidence-backed auditions. WAV playback backend: {backend}.")
        except Exception as exc:
            self.audio_readiness_v40.set(f"Readiness check failed: {exc}")

    def _selected_sequence_v40(self) -> dict[str, Any] | None:
        selected = self.sequence_tree.selection()
        return self._mixer_sequence_rows_v40.get(selected[0]) if selected else None

    def _selected_candidate_v40(self) -> dict[str, Any] | None:
        selected = self.program_tree.selection()
        return self._mixer_candidate_rows_v40.get(selected[0]) if selected else None

    def _selected_sequence(self) -> dict[str, Any] | None:
        return self._selected_sequence_v40()

    def _selected_program(self) -> dict[str, Any] | None:
        return self._selected_candidate_v40()

    def _selected_routing_mode(self, model: dict[str, Any] | None = None) -> str | None:
        selected = self.audio_routing_mode.get() if self.audio_routing_mode is not None else "Auto"
        if selected != "Auto":
            return selected
        if model is not None:
            return str(model.get("preferred_hypothesis") or "") or None
        sequence = self._selected_sequence_v40()
        return str((sequence or {}).get("preferred_hypothesis") or "") or None

    def _refresh_audio_sequences(self, preselect: str | None = None) -> None:
        project = self.project
        self._mixer_sequence_generation_v40 += 1
        generation = self._mixer_sequence_generation_v40
        self.sequence_tree.delete(*self.sequence_tree.get_children())
        self.program_tree.delete(*self.program_tree.get_children())
        self.audio_sample_tree_v40.delete(*self.audio_sample_tree_v40.get_children())
        self._mixer_sequence_rows_v40.clear()
        self._mixer_candidate_rows_v40.clear()
        self._mixer_sample_rows_v40.clear()
        if project is None:
            return
        query = self.audio_sequence_search_v40.get() if self.audio_sequence_search_v40 is not None else ""
        status_filter = self.audio_sequence_filter_v40.get() if self.audio_sequence_filter_v40 is not None else "All"
        self.audio_status.set("Loading the sequence research catalog off the UI thread…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._mixer_sequence_generation_v40:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Mixer catalog unavailable: {error}")
                _replace_text(
                    self.audio_details,
                    f"Mixer catalog unavailable:\n{error}\n\nRun Extract SNDDATA Samples and Build SNDDATA Mixer Index on the Audio Pipeline tab.",
                )
                return
            self.audio_progress["value"] = 100.0
            selected_iid = None
            for index, row in enumerate(rows):
                iid = f"sequence_{index}"
                saved = row.get("saved_mapping") or {}
                reviewed = int(row.get("review_count") or 0)
                review_text = str(saved.get("status") or "")
                if reviewed:
                    review_text = f"{review_text or 'reviewed'} ({reviewed})"
                routing = str(row.get("preferred_hypothesis") or "unresolved")
                self.sequence_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=row["sequence_id"],
                    values=(row.get("note_on_count", 0), row.get("track_count", 0), routing, row.get("renderable", 0), review_text),
                )
                self._mixer_sequence_rows_v40[iid] = row
                if preselect and row["sequence_id"] == preselect:
                    selected_iid = iid
            selected_iid = selected_iid or next(iter(self._mixer_sequence_rows_v40), None)
            if selected_iid:
                self.sequence_tree.selection_set(selected_iid)
                self.sequence_tree.focus(selected_iid)
                self.sequence_tree.see(selected_iid)
                self._refresh_audio_candidates()
            else:
                _replace_text(self.audio_details, "No sequences match the current search/filter.")
            renderable = sum(int(row.get("renderable") or 0) > 0 for row in rows)
            saved_count = sum(bool(row.get("saved_mapping")) for row in rows)
            self.audio_status.set(f"{len(rows)} sequences shown; {renderable} have at least one renderer-complete candidate; {saved_count} saved mappings.")

        self._local_worker(
            "snddata-research-sequences-v40",
            lambda: sequence_rows(project, query=query, status_filter=status_filter),
            done,
        )

    def _refresh_audio_candidates(self, preselect_resource: str | None = None) -> None:
        project = self.project
        sequence = self._selected_sequence_v40()
        self._mixer_candidate_generation_v40 += 1
        generation = self._mixer_candidate_generation_v40
        self.program_tree.delete(*self.program_tree.get_children())
        self.audio_sample_tree_v40.delete(*self.audio_sample_tree_v40.get_children())
        self._mixer_candidate_rows_v40.clear()
        self._mixer_sample_rows_v40.clear()
        if project is None or sequence is None:
            return
        routing = self.audio_routing_mode.get() if self.audio_routing_mode is not None else "Auto"
        self.audio_status.set(f"Resolving {sequence['sequence_id']} under {routing}…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._mixer_candidate_generation_v40:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Candidate resolver failed: {error}")
                _replace_text(self.audio_details, str(error))
                return
            self.audio_progress["value"] = 100.0
            selected_iid = None
            fallback_iid = None
            for index, row in enumerate(model.get("candidates") or []):
                iid = f"candidate_{index}"
                review = row.get("review") or {}
                verdict = str(review.get("status") or ("saved" if row.get("saved") else ""))
                missing = str(row.get("missing_summary") or row.get("status_detail") or "")
                self.program_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=row["resource_id"],
                    values=(row.get("rank"), row.get("status"), row.get("coverage"), verdict, missing),
                    tags=(str(row.get("status") or ""), str(verdict or "untested")),
                )
                self._mixer_candidate_rows_v40[iid] = row
                if preselect_resource and row["resource_id"] == preselect_resource:
                    selected_iid = iid
                if row.get("saved"):
                    selected_iid = selected_iid or iid
                if fallback_iid is None and row.get("status") == "renderable" and verdict != "rejected":
                    fallback_iid = iid
            self.program_tree.tag_configure("renderable", foreground="#147a36")
            self.program_tree.tag_configure("missing_programs", foreground="#a05a00")
            self.program_tree.tag_configure("missing_samples", foreground="#a05a00")
            self.program_tree.tag_configure("rejected", foreground="#9b1c1c")
            selected_iid = selected_iid or fallback_iid or next(iter(self._mixer_candidate_rows_v40), None)
            if selected_iid:
                self.program_tree.selection_set(selected_iid)
                self.program_tree.focus(selected_iid)
                self.program_tree.see(selected_iid)
                self._candidate_selected_v40()
            else:
                _replace_text(
                    self.audio_details,
                    self._sequence_summary_text_v40(model),
                )
            self.audio_status.set(
                f"{model.get('routing_mode') or 'unresolved'}: {len(model.get('candidates') or [])} candidates; "
                f"{int(model.get('renderable_candidates') or 0)} renderer-complete. First wall: {model.get('first_wall')}"
            )

        self._local_worker(
            "snddata-research-candidates-v40",
            lambda: candidate_rows(project, sequence["sequence_id"], routing_mode=routing),
            done,
        )

    def _sequence_summary_text_v40(self, model: dict[str, Any]) -> str:
        sequence = model.get("sequence") or {}
        return (
            f"Sequence: {sequence.get('sequence_id')}\n"
            f"Selected routing: {model.get('routing_mode') or 'none'}\n"
            f"Candidates: {len(model.get('candidates') or [])}\n"
            f"Renderer-complete: {model.get('renderable_candidates') or 0}\n"
            f"First unresolved wall: {model.get('first_wall') or 'none'}\n\n"
            "Choose an explicit routing mode when Auto has no evidence-backed preference. "
            "No implicit Program 0 mapping is invented."
        )

    def _candidate_summary_text_v40(self, sequence: dict[str, Any], candidate: dict[str, Any]) -> str:
        review = candidate.get("review") or {}
        missing_programs = candidate.get("missing_program_indexes") or []
        missing_samples = candidate.get("missing_sample_ids") or []
        status = str(candidate.get("status") or "unknown")
        can_render = status == "renderable"
        lines = [
            f"Sequence: {sequence.get('sequence_id')}",
            f"Routing hypothesis: {candidate.get('routing_mode') or 'unresolved'}",
            f"Program resource: {candidate.get('resource_id')}",
            f"Evidence rank: {candidate.get('rank')}",
            f"Renderer status: {status}",
            f"Program records: {candidate.get('program_count') or 0}",
            f"Required Program indexes: {candidate.get('required_program_indexes') or candidate.get('program_indexes_required') or []}",
            f"Required sample IDs: {candidate.get('required_sample_ids') or []}",
            f"Decoded sample coverage: {candidate.get('coverage')}",
            f"Missing Program indexes: {missing_programs}",
            f"Missing sample IDs: {missing_samples}",
            f"Saved mapping: {'yes' if candidate.get('saved') else 'no'}",
            f"Research verdict: {review.get('status') or 'untested'}",
            f"Research notes: {review.get('notes') or ''}",
            "",
        ]
        if can_render:
            lines.append("This candidate has the inputs required by the current renderer. Render & Play produces a bounded WAV preview.")
        else:
            lines.append(
                "This candidate cannot currently render. The listed missing Program/sample evidence must be found or the routing interpretation must change. "
                "It remains available for inspection and sample playback."
            )
        lines.extend(
            [
                "",
                "Research verdicts and mappings are bound to the exact SNDDATA SHA-256. They do not modify game data.",
            ]
        )
        return "\n".join(lines)

    def _candidate_selected_v40(self) -> None:
        project = self.project
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        self._mixer_sample_generation_v40 += 1
        generation = self._mixer_sample_generation_v40
        self.audio_sample_tree_v40.delete(*self.audio_sample_tree_v40.get_children())
        self._mixer_sample_rows_v40.clear()
        if project is None or sequence is None or candidate is None:
            return
        review = candidate.get("review") or {}
        if self.audio_review_notes_v40 is not None:
            self.audio_review_notes_v40.set(str(review.get("notes") or ""))
        _replace_text(self.audio_details, self._candidate_summary_text_v40(sequence, candidate))

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._mixer_sample_generation_v40:
                return
            if error:
                self.audio_status.set(f"Sample evidence failed: {error}")
                return
            for index, row in enumerate(rows):
                iid = f"sample_{index}"
                status = "playable" if row.get("playable") else "missing"
                self.audio_sample_tree_v40.insert(
                    "",
                    "end",
                    iid=iid,
                    text=str(row.get("display_name") or f"sample {row.get('index')}") ,
                    values=(f"{int(row.get('sample_rate') or 0):,}", f"{float(row.get('duration_estimate') or 0.0):.3f}s", status),
                )
                self._mixer_sample_rows_v40[iid] = row

        self._local_worker("snddata-candidate-samples-v40", lambda: sample_rows(project, candidate), done)

    # ------------------------------------------------------------------
    # Rendering, playback, and research decisions.
    # ------------------------------------------------------------------
    def _render_selected_v40(self, *, play: bool) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None:
            return
        if sequence is None or candidate is None:
            messagebox.showinfo("SNDDATA Research Mixer", "Select a sequence and Program candidate first.")
            return
        if candidate.get("status") != "renderable":
            missing = candidate.get("missing_summary") or candidate.get("status_detail") or candidate.get("status")
            messagebox.showinfo(
                "Candidate is not renderable",
                f"The current renderer cannot build this candidate.\n\nMissing wall: {missing}\n\nInspect its required samples or try another routing hypothesis/candidate.",
            )
            return
        mode = str(candidate.get("routing_mode") or "")
        if mode not in {"program_change", "channel_as_program"}:
            messagebox.showinfo("SNDDATA Research Mixer", "Select an explicit usable routing hypothesis first.")
            return
        self.audio_status.set(f"Rendering {sequence['sequence_id']} with {candidate['resource_id']}…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)
        gain = float(self.audio_gain.get())

        def done(result: Any, error: Exception | None) -> None:
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                if isinstance(error, MusicSystemError):
                    _replace_text(
                        self.audio_details,
                        _json_text({"status": "not_renderable", "error": str(error), "missing": error.missing, "candidate": candidate}),
                    )
                    self.audio_status.set(str(error))
                else:
                    messagebox.showerror("SNDDATA render", str(error))
                return
            self.audio_progress["value"] = 100.0
            output = Path(result["output_path"])
            self.audio_last_preview_v40 = output
            if play:
                try:
                    self.playback.load(output)
                    self.playback.set_gain(gain)
                    self.playback.play()
                except Exception as exc:
                    messagebox.showerror("Playback", str(exc))
                    return
            _replace_text(self.audio_details, _json_text(result))
            self.audio_status.set(("Playing" if play else "Rendered") + f" {output.name} ({float(result.get('duration') or 0.0):.2f}s)")

        self._local_worker(
            "snddata-render-v40",
            lambda: render_sequence(
                project,
                sequence["sequence_id"],
                program_resource_offset=int(candidate["resource_offset"]),
                routing_mode=mode,
                master_gain=gain,
            ),
            done,
        )

    def _audio_render_play(self) -> None:
        self._render_selected_v40(play=True)

    def _play_last_preview_v40(self) -> None:
        path = self.audio_last_preview_v40
        if path is None or not path.is_file():
            messagebox.showinfo("SNDDATA Research Mixer", "No preview has been rendered in this session.")
            return
        try:
            self.playback.load(path)
            self.playback.set_gain(float(self.audio_gain.get()))
            self.playback.play()
            self.audio_status.set(f"Playing {path.name}")
        except Exception as exc:
            messagebox.showerror("Playback", str(exc))

    def _play_selected_sample_v40(self) -> None:
        selected = self.audio_sample_tree_v40.selection()
        row = self._mixer_sample_rows_v40.get(selected[0]) if selected else None
        if not row or not row.get("playable"):
            messagebox.showinfo("Sample playback", "Select a decoded, playable sample WAV.")
            return
        try:
            path = Path(str(row["output_path"]))
            self.playback.load(path)
            self.playback.set_gain(float(self.audio_gain.get()))
            self.playback.play()
            self.audio_status.set(f"Playing sample {row.get('index')}: {path.name}")
        except Exception as exc:
            messagebox.showerror("Sample playback", str(exc))

    def _review_candidate_v40(self, status: str) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None or sequence is None or candidate is None:
            messagebox.showinfo("SNDDATA research", "Select a sequence and candidate first.")
            return
        notes = self.audio_review_notes_v40.get() if self.audio_review_notes_v40 is not None else ""
        preview = self.audio_last_preview_v40 if self.audio_last_preview_v40 and self.audio_last_preview_v40.is_file() else None
        try:
            record = set_candidate_review(
                project,
                sequence["sequence_id"],
                str(candidate.get("routing_mode") or ""),
                candidate["resource_id"],
                status=status,
                notes=notes,
                preview_path=preview,
            )
            source = canonical_snddata_path(project)
            if status == "confirmed":
                set_mapping(
                    mapping_store_path(project),
                    source,
                    sequence["sequence_id"],
                    candidate["resource_id"],
                    status="confirmed",
                    notes=notes,
                )
            elif status == "rejected" and candidate.get("saved"):
                remove_mapping(mapping_store_path(project), source, sequence["sequence_id"])
            self.audio_status.set(f"Recorded {status}: {sequence['sequence_id']} → {candidate['resource_id']}")
            candidate["review"] = record
            self._refresh_audio_candidates(preselect_resource=candidate["resource_id"])
        except Exception as exc:
            messagebox.showerror("SNDDATA research", str(exc))

    def _audio_use_mapping(self) -> None:
        self._review_candidate_v40("confirmed")

    def _clear_candidate_review_v40(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None or sequence is None or candidate is None:
            return
        try:
            clear_candidate_review(
                project,
                sequence["sequence_id"],
                str(candidate.get("routing_mode") or ""),
                candidate["resource_id"],
            )
            self.audio_status.set("Candidate review cleared. Confirmed mapping is retained until explicitly replaced or rejected.")
            self._refresh_audio_candidates(preselect_resource=candidate["resource_id"])
        except Exception as exc:
            messagebox.showerror("Clear review", str(exc))

    def _rebuild_mixer_index_v40(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self.audio_status.set("Rebuilding FF0A sequence, routing, Program, slot, and sample evidence…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(result: Any, error: Exception | None) -> None:
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Mixer index rebuild failed: {error}")
                _replace_text(self.audio_details, str(error))
                return
            self.audio_progress["value"] = 100.0
            self.audio_status.set("Mixer index rebuilt. Loading sequences…")
            self._refresh_audio_readiness_v40()
            self._refresh_audio_sequences()
            if "Reports" in self._lazy_loaded_tabs_v40:
                self._refresh_reports()

        self._local_worker("snddata-index-v40", lambda: analyze_project_snddata(project), done)

    def _open_audio_reports_v40(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            _open_path(sound_reports_root(project))
        except Exception as exc:
            messagebox.showerror("Open Audio Reports", str(exc))


def main() -> int:
    app = PublicFragmenterAppV40()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

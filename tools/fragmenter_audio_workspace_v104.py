#!/usr/bin/env python3
"""V104 audio workspace, RUN ALL hydration, and Celdra research layout."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from asset_classifier_v2 import category_sort_key
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v38 import PublicFragmenterAppV38
from fragmenter_public_gui_v40 import PublicFragmenterAppV40
from project_sound_v7 import build_project_sound_library
from public_library_cache_v1 import load_cache
from snddata_research_workbench_v1 import FILTERS, ROUTING_MODES, readiness


class FragmenterAudioWorkspaceMixinV104:
    """Replace the inherited audio clutter with prepared, sortable workspaces."""

    AUDIO_STAGE_LABELS = {
        "Extract audio sources": "sound_extract",
        "Decode direct playable audio": "sound_decode",
        "Extract corrected SNDDATA samples": "snddata_samples",
        "Build SNDDATA mixer index": "snddata_mixer",
    }

    def __init__(self) -> None:
        self._audio_library_sort_reverse_v104: dict[str, bool] = {}
        self._audio_library_category_host_v104: ttk.Frame | None = None
        self._audio_library_sidebar_canvas_v104: tk.Canvas | None = None
        self._audio_pipeline_stage_v104: tk.StringVar | None = None
        self._run_stage_host_v104: ttk.LabelFrame | None = None
        self._research_prep_status_v104: tk.StringVar | None = None
        self._audio_top_paned_v104: ttk.Panedwindow | None = None
        self._audio_bottom_paned_v104: ttk.Panedwindow | None = None
        super().__init__()

    # ------------------------------------------------------------------
    # RUN ALL: scrollable direct stages plus one-click research preparation.
    # ------------------------------------------------------------------
    def _build_run_all(self, parent: ttk.Frame) -> None:
        super()._build_run_all(parent)
        host = self.stage_progress_frame
        if not isinstance(host, ttk.LabelFrame):
            return
        self._run_stage_host_v104 = host
        for child in tuple(host.winfo_children()):
            child.destroy()
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        tabs = ttk.Notebook(host)
        tabs.grid(row=0, column=0, sticky="nsew")

        stages = ttk.Frame(tabs)
        stages.columnconfigure(0, weight=1)
        stages.rowconfigure(0, weight=1)
        tabs.add(stages, text="Stages")
        canvas = tk.Canvas(stages, highlightthickness=0, borderwidth=0)
        ybar = ttk.Scrollbar(stages, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=ybar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        stage_inner = ttk.Frame(canvas, padding=(3, 2, 7, 3))
        window = canvas.create_window((0, 0), window=stage_inner, anchor="nw")
        stage_inner.columnconfigure(1, weight=1)
        stage_inner.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=max(100, event.width)),
        )
        self.stage_progress_frame = stage_inner

        research = ttk.Frame(tabs, padding=8)
        research.columnconfigure(0, weight=1)
        research.rowconfigure(4, weight=1)
        tabs.add(research, text="Research prep")
        ttk.Label(
            research,
            text=(
                "RUN ALL includes visual catalogs, direct audio decoding, corrected SNDDATA samples, "
                "the mixer index, and prebuilt public lists. Use the audio-only action only when the full project run is unnecessary."
            ),
            wraplength=520,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        actions = ttk.Frame(research)
        actions.grid(row=1, column=0, sticky="ew")
        ttk.Button(
            actions,
            text="RUN ALL + Prepare Lists",
            command=self._run_all,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Prepare Audio Research",
            command=self._prepare_audio_research_v104,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            actions,
            text="Refresh Prepared Lists",
            command=self._hydrate_public_lists_v104,
        ).pack(side="left", padx=(6, 0))
        self._research_prep_status_v104 = tk.StringVar(value="Research preparation status will appear here.")
        ttk.Label(
            research,
            textvariable=self._research_prep_status_v104,
            wraplength=520,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(9, 0))
        self.after_idle(self._update_research_prep_status_v104)

    def _refresh_run_plan(self) -> None:
        super()._refresh_run_plan()
        self._update_research_prep_status_v104()

    def _update_research_prep_status_v104(self) -> None:
        variable = self._research_prep_status_v104
        project = getattr(self, "project", None)
        if variable is None:
            return
        if project is None:
            variable.set("No project loaded.")
            return
        try:
            state = readiness(project)
            summary = load_cache(project, "summary") or {}
            variable.set(
                "Audio: "
                + ("ready" if state.get("catalog_exists") and state.get("sample_report_exists") else "needs preparation")
                + f". Prepared lists: {int(summary.get('visual_assets') or 0):,} visual assets, "
                + f"{int(summary.get('playable_sounds') or 0):,} playable sounds, "
                + f"{int(summary.get('snddata_sequences') or 0):,} sequences."
            )
        except Exception as exc:
            variable.set(f"Research preparation check failed: {exc}")

    # ------------------------------------------------------------------
    # Playable-only Audio Library with a scrollable category sidebar.
    # ------------------------------------------------------------------
    def _build_simple_audio_library(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        split = ttk.Panedwindow(parent, orient="horizontal")
        split.grid(row=0, column=0, sticky="nsew")

        sidebar = ttk.LabelFrame(split, text="Playable library", padding=5)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)
        ttk.Label(sidebar, text="Search playable sounds").grid(row=0, column=0, sticky="w")
        self.simple_audio_query = tk.StringVar(value="")
        search = ttk.Entry(sidebar, textvariable=self.simple_audio_query)
        search.grid(row=1, column=0, sticky="ew", pady=(3, 7))
        self.simple_audio_category = tk.StringVar(value="All")
        category_canvas = tk.Canvas(sidebar, width=190, highlightthickness=0, borderwidth=0)
        category_y = ttk.Scrollbar(sidebar, orient="vertical", command=category_canvas.yview)
        category_canvas.configure(yscrollcommand=category_y.set)
        category_canvas.grid(row=2, column=0, sticky="nsew")
        category_y.grid(row=2, column=1, sticky="ns")
        category_host = ttk.Frame(category_canvas)
        category_window = category_canvas.create_window((0, 0), window=category_host, anchor="nw")
        category_host.bind(
            "<Configure>",
            lambda _event: category_canvas.configure(scrollregion=category_canvas.bbox("all")),
        )
        category_canvas.bind(
            "<Configure>",
            lambda event: category_canvas.itemconfigure(category_window, width=max(80, event.width)),
        )
        self._audio_library_sidebar_canvas_v104 = category_canvas
        self._audio_library_category_host_v104 = category_host
        ttk.Label(
            sidebar,
            text="Only playable WAV assets appear here. Raw PCM, binary containers, reports, and metadata stay in research views.",
            wraplength=185,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        split.add(sidebar, weight=1)

        workspace = ttk.Frame(split)
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(workspace)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.simple_audio_primary = ttk.Button(
            toolbar,
            text="Play Selected",
            command=self._simple_audio_primary_action,
            style="Accent.TButton",
        )
        self.simple_audio_primary.pack(side="left")
        ttk.Button(toolbar, text="Stop", command=self._audio_stop).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Refresh", command=self._refresh_simple_audio).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Open Folder", command=self._open_simple_audio_folder).pack(side="left", padx=(6, 0))
        self.simple_audio_status = tk.StringVar(value="No project loaded")
        ttk.Label(toolbar, textvariable=self.simple_audio_status).pack(side="right")

        vertical = ttk.Panedwindow(workspace, orient="vertical")
        vertical.grid(row=1, column=0, sticky="nsew")
        listing = ttk.Frame(vertical)
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.simple_audio_tree = ttk.Treeview(
            listing,
            columns=("category", "duration", "rate", "size", "path"),
            show="tree headings",
            selectmode="browse",
        )
        for key, label, width, numeric in (
            ("#0", "Sound", 235, False),
            ("category", "Category", 135, False),
            ("duration", "Duration", 82, True),
            ("rate", "Rate", 82, True),
            ("size", "Size", 92, True),
            ("path", "Decoded path", 460, False),
        ):
            self.simple_audio_tree.heading(
                key,
                text=label,
                command=lambda column=key, is_numeric=numeric: self._sort_audio_library_v104(column, is_numeric),
            )
            self.simple_audio_tree.column(key, width=width, stretch=key in {"#0", "path"})
        audio_y = ttk.Scrollbar(listing, orient="vertical", command=self.simple_audio_tree.yview)
        audio_x = ttk.Scrollbar(listing, orient="horizontal", command=self.simple_audio_tree.xview)
        self.simple_audio_tree.configure(yscrollcommand=audio_y.set, xscrollcommand=audio_x.set)
        self.simple_audio_tree.grid(row=0, column=0, sticky="nsew")
        audio_y.grid(row=0, column=1, sticky="ns")
        audio_x.grid(row=1, column=0, sticky="ew")
        self.simple_audio_tree.bind("<<TreeviewSelect>>", lambda _event: self._sound_selection_changed())
        self.simple_audio_tree.bind("<Double-1>", lambda _event: self._simple_audio_primary_action())
        vertical.add(listing, weight=4)

        details = ttk.LabelFrame(vertical, text="Playable sound details", padding=4)
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=1)
        self.simple_audio_details = tk.Text(details, height=6, wrap="word")
        details_y = ttk.Scrollbar(details, orient="vertical", command=self.simple_audio_details.yview)
        self.simple_audio_details.configure(yscrollcommand=details_y.set)
        self.simple_audio_details.grid(row=0, column=0, sticky="nsew")
        details_y.grid(row=0, column=1, sticky="ns")
        vertical.add(details, weight=1)
        split.add(workspace, weight=5)

        self.simple_audio_query.trace_add("write", lambda *_: self._debounce_simple_audio())
        self._rebuild_audio_categories_v104(("All",))

    def _rebuild_audio_categories_v104(self, categories: tuple[str, ...] | list[str]) -> None:
        host = self._audio_library_category_host_v104
        if host is None:
            return
        for child in tuple(host.winfo_children()):
            child.destroy()
        for row, category in enumerate(("All", *tuple(value for value in categories if value != "All"))):
            ttk.Radiobutton(
                host,
                text=category,
                value=category,
                variable=self.simple_audio_category,
                command=self._refresh_simple_audio,
            ).grid(row=row, column=0, sticky="ew", pady=1)
        host.columnconfigure(0, weight=1)

    def _refresh_simple_audio(self) -> None:
        project = getattr(self, "project", None)
        if not hasattr(self, "simple_audio_tree"):
            return
        self._simple_audio_generation += 1
        generation = self._simple_audio_generation
        self.simple_audio_tree.delete(*self.simple_audio_tree.get_children())
        self._simple_audio_rows.clear()
        if project is None:
            self.simple_audio_status.set("No project loaded")
            return
        query = self.simple_audio_query.get().strip().casefold()
        selected_category = self.simple_audio_category.get() or "All"
        self.simple_audio_status.set("Loading prepared playable sounds…")

        def work() -> dict[str, Any]:
            cached = load_cache(project, "audio")
            if cached is None:
                model = build_project_sound_library(
                    project,
                    query="",
                    category="All",
                    include_pcm_research=False,
                )
            else:
                model = cached
            source_items = [row for row in model.get("items") or [] if isinstance(row, dict)]
            playable = [
                dict(row)
                for row in source_items
                if bool(row.get("playable"))
                and str(row.get("path") or row.get("relative_path") or "").casefold().endswith(".wav")
            ]
            categories: list[str] = []
            for row in playable:
                category = str(row.get("category") or "Other Playable")
                if category not in categories:
                    categories.append(category)
            rows = []
            for row in playable:
                haystack = " ".join(
                    str(row.get(key) or "")
                    for key in ("name", "category", "relative_path", "usage_group", "provenance")
                ).casefold()
                if query and query not in haystack:
                    continue
                if selected_category != "All" and str(row.get("category") or "") != selected_category:
                    continue
                rows.append(row)
            rows.sort(key=lambda row: (str(row.get("category") or "").casefold(), str(row.get("name") or "").casefold()))
            return {"items": rows, "categories": categories, "total": len(playable)}

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._simple_audio_generation:
                return
            if error:
                self.simple_audio_status.set(f"Playable library failed: {error}")
                return
            self._rebuild_audio_categories_v104(tuple(model.get("categories") or ()))
            for index, item in enumerate(model.get("items") or []):
                iid = f"simple_audio_{index}"
                wav = item.get("wav") if isinstance(item.get("wav"), dict) else {}
                duration = float(wav.get("duration") or item.get("duration") or item.get("duration_estimate") or 0.0)
                rate = int(wav.get("sample_rate") or item.get("sample_rate") or 0)
                self.simple_audio_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=str(item.get("name") or Path(str(item.get("path") or "sound.wav")).name),
                    values=(
                        str(item.get("category") or "Other Playable"),
                        f"{duration:.2f}s",
                        f"{rate:,} Hz" if rate else "—",
                        f"{int(item.get('size') or 0):,}",
                        str(item.get("relative_path") or item.get("path") or ""),
                    ),
                )
                self._simple_audio_rows[iid] = dict(item)
            self.simple_audio_status.set(
                f"Showing {len(model.get('items') or []):,} of {int(model.get('total') or 0):,} playable sounds. Raw PCM and containers are hidden."
            )

        self._local_worker("playable-audio-library-v104", work, done)

    def _sort_audio_library_v104(self, column: str, numeric: bool) -> None:
        reverse = not self._audio_library_sort_reverse_v104.get(column, False)
        self._audio_library_sort_reverse_v104[column] = reverse

        def value(iid: str) -> Any:
            raw = self.simple_audio_tree.item(iid, "text") if column == "#0" else self.simple_audio_tree.set(iid, column)
            if not numeric:
                return str(raw).casefold()
            cleaned = str(raw).replace(",", "").replace("Hz", "").replace("s", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                return float("-inf")

        rows = list(self.simple_audio_tree.get_children(""))
        rows.sort(key=value, reverse=reverse)
        for index, iid in enumerate(rows):
            self.simple_audio_tree.move(iid, "", index)

    # ------------------------------------------------------------------
    # One-click Audio Pipeline. Advanced stages remain available in one selector.
    # ------------------------------------------------------------------
    def _build_audio_pipeline_v38(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)
        ttk.Label(
            parent,
            text=(
                "RUN ALL already prepares the complete audio research workspace. This page is the audio-only path: "
                "extract sources, decode playable streams, extract corrected SNDDATA samples, build the mixer index, then refresh the lists."
            ),
            wraplength=1150,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 7))

        primary = ttk.LabelFrame(parent, text="Recommended action", padding=7)
        primary.grid(row=1, column=0, sticky="ew")
        prepare = ttk.Button(
            primary,
            text="Prepare Complete Audio Workspace",
            command=self._prepare_audio_research_v104,
            style="Accent.TButton",
        )
        prepare.pack(side="left")
        refresh = ttk.Button(
            primary,
            text="Refresh Prepared Lists",
            command=self._hydrate_public_lists_v104,
        )
        refresh.pack(side="left", padx=(6, 0))
        ttk.Button(primary, text="Open Decoded Audio", command=self._open_decoded_audio_v38).pack(side="left", padx=(6, 0))
        ttk.Button(primary, text="Open Audio Reports", command=self._open_audio_reports_v40).pack(side="left", padx=(6, 0))
        self._audio_pipeline_buttons_v38.extend((prepare, refresh))

        advanced = ttk.LabelFrame(parent, text="Advanced single-stage rerun", padding=7)
        advanced.grid(row=2, column=0, sticky="ew", pady=(7, 0))
        ttk.Label(advanced, text="Stage").pack(side="left")
        self._audio_pipeline_stage_v104 = tk.StringVar(value=next(iter(self.AUDIO_STAGE_LABELS)))
        stage = ttk.Combobox(
            advanced,
            textvariable=self._audio_pipeline_stage_v104,
            values=tuple(self.AUDIO_STAGE_LABELS),
            state="readonly",
            width=37,
        )
        stage.pack(side="left", padx=(6, 7))
        run_stage = ttk.Button(advanced, text="Run Selected Stage", command=self._run_selected_audio_stage_v104)
        run_stage.pack(side="left")
        self._audio_pipeline_buttons_v38.append(run_stage)
        self.audio_pipeline_status_v38 = tk.StringVar(value="Audio workspace readiness has not been checked.")
        ttk.Label(advanced, textvariable=self.audio_pipeline_status_v38).pack(side="left", padx=(12, 0), fill="x", expand=True)

        details_frame = ttk.Frame(parent)
        details_frame.grid(row=3, column=0, sticky="nsew", pady=(7, 0))
        details_frame.columnconfigure(0, weight=1)
        details_frame.rowconfigure(0, weight=1)
        self.audio_pipeline_details_v38 = tk.Text(details_frame, wrap="word")
        details_y = ttk.Scrollbar(details_frame, orient="vertical", command=self.audio_pipeline_details_v38.yview)
        self.audio_pipeline_details_v38.configure(yscrollcommand=details_y.set)
        self.audio_pipeline_details_v38.grid(row=0, column=0, sticky="nsew")
        details_y.grid(row=0, column=1, sticky="ns")
        _replace_text(
            self.audio_pipeline_details_v38,
            _json_text(
                {
                    "run_all_includes": [
                        "sound_extract",
                        "sound_decode",
                        "snddata_samples",
                        "snddata_mixer",
                        "public_lists",
                    ],
                    "audio_library": "playable WAV assets only",
                    "mixer": "FF0A sequence -> routing hypothesis -> Program resource -> exact sample IDs -> bounded WAV proof",
                    "writes_game_data": False,
                }
            ),
        )
        self.after_idle(self._refresh_audio_pipeline_status_v104)

    def _refresh_audio_pipeline_status_v104(self) -> None:
        variable = self.audio_pipeline_status_v38
        project = getattr(self, "project", None)
        if variable is None:
            return
        if project is None:
            variable.set("Open a project to prepare audio research.")
            return
        try:
            state = readiness(project)
            missing = [
                label
                for label, key in (
                    ("SNDDATA source", "snddata_exists"),
                    ("corrected samples", "sample_report_exists"),
                    ("mixer index", "catalog_exists"),
                )
                if not state.get(key)
            ]
            variable.set("Ready for sequence research." if not missing else "Missing: " + ", ".join(missing))
        except Exception as exc:
            variable.set(f"Readiness check failed: {exc}")

    def _prepare_audio_research_v104(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        state = readiness(project)
        stages: list[str] = []
        if not state.get("snddata_exists"):
            stages.extend(("sound_extract", "sound_decode"))
        if not state.get("sample_report_exists"):
            stages.append("snddata_samples")
        if not state.get("catalog_exists"):
            stages.append("snddata_mixer")
        ordered = tuple(dict.fromkeys(stages))
        if ordered:
            self._run_audio_work_v38(ordered, "Prepare Audio Research")
            if hasattr(self, "_audio_celdra_say_v98"):
                self._audio_celdra_say_v98(
                    "Preparing audio research",
                    "Running the missing extraction, corrected sample, and mixer-index stages as one operation. The normal library will still show only playable WAV sounds.",
                    "excited",
                )
            return
        self._refresh_audio_readiness_v40()
        self._refresh_audio_sequences()
        self._refresh_simple_audio()
        self._refresh_audio_pipeline_status_v104()
        if hasattr(self, "_audio_celdra_research_status_v98"):
            self._audio_celdra_research_status_v98()

    def _run_selected_audio_stage_v104(self) -> None:
        selected = self._audio_pipeline_stage_v104.get() if self._audio_pipeline_stage_v104 is not None else ""
        key = self.AUDIO_STAGE_LABELS.get(selected)
        if key:
            self._run_audio_stage_v38(key)

    def _install_music_catalog_controls_v101(self) -> None:
        # V101's graph/container-map readiness widget belongs to an obsolete
        # controller and falsely reports missing reports beside the v5 mixer.
        return

    def _prepare_music_catalogs_v101(self) -> None:
        self._prepare_audio_research_v104()

    def _update_music_catalog_status_v101(self) -> dict[str, Any] | None:
        project = getattr(self, "project", None)
        if project is None:
            return None
        state = readiness(project)
        self._refresh_audio_pipeline_status_v104()
        return {"ready": bool(state.get("catalog_exists") and state.get("sample_report_exists")), **state}

    def _refresh_audio_sequences(self, preselect: str | None = None) -> None:
        # Bypass the obsolete V101 graph/container-map gate. The live research
        # mixer is authoritative on snddata_music_system_v5.json.
        if hasattr(self, "_audio_celdra_say_v98") and getattr(self, "project", None) is not None:
            self._audio_celdra_say_v98(
                "Loading prepared sequences",
                "Reading the RUN ALL mixer index and applying the current search, readiness filter, and routing view.",
                "smile",
            )
        PublicFragmenterAppV40._refresh_audio_sequences(self, preselect)

    def _audio_pipeline_done_v38(self, result: Any, error: Exception | None) -> None:
        PublicFragmenterAppV38._audio_pipeline_done_v38(self, result, error)
        self._refresh_audio_readiness_v40()
        self._refresh_audio_pipeline_status_v104()
        self._update_research_prep_status_v104()
        if hasattr(self, "_audio_celdra_research_status_v98"):
            self.after_idle(self._audio_celdra_research_status_v98)

    # ------------------------------------------------------------------
    # Mixer layout: sortable assets above; research bottom-left; guide and
    # controls immediately left of Celdra's far-right viewport.
    # ------------------------------------------------------------------
    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        self._audio_research_page_v98 = parent
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(
            controls,
            text="Prepare / Refresh Audio Research",
            command=self._prepare_audio_research_v104,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Label(controls, text="Find sequence").pack(side="left", padx=(10, 0))
        self.audio_sequence_search_v40 = tk.StringVar(value="")
        search = ttk.Entry(controls, textvariable=self.audio_sequence_search_v40, width=25)
        search.pack(side="left", padx=(5, 9))
        self._audio_sequence_search_entry_v98 = search
        self.audio_sequence_search_v40.trace_add("write", lambda *_: self._debounce_mixer_refresh_v40())
        ttk.Label(controls, text="Show").pack(side="left")
        self.audio_sequence_filter_v40 = tk.StringVar(value="All")
        status_filter = ttk.Combobox(
            controls,
            textvariable=self.audio_sequence_filter_v40,
            values=FILTERS,
            state="readonly",
            width=15,
        )
        status_filter.pack(side="left", padx=(5, 9))
        status_filter.bind("<<ComboboxSelected>>", lambda _event: self._refresh_audio_sequences())
        ttk.Label(controls, text="Routing").pack(side="left")
        self.audio_routing_mode = tk.StringVar(value="Auto")
        routing = ttk.Combobox(
            controls,
            textvariable=self.audio_routing_mode,
            values=ROUTING_MODES,
            state="readonly",
            width=19,
        )
        routing.pack(side="left", padx=(5, 9))
        routing.bind("<<ComboboxSelected>>", lambda _event: self._refresh_audio_candidates())
        self.audio_readiness_v40 = tk.StringVar(value="RUN ALL prepares this mixer automatically.")
        ttk.Label(controls, textvariable=self.audio_readiness_v40).pack(side="right", padx=(10, 0))

        workspace = ttk.Panedwindow(parent, orient="vertical")
        workspace.grid(row=1, column=0, sticky="nsew")
        self.audio_workspace_paned_v46 = workspace
        top = ttk.Panedwindow(workspace, orient="horizontal")
        self._audio_top_paned_v104 = top
        self._build_sequence_list_v46(top)
        self._build_candidate_list_v46(top)
        self._build_playback_deck_v46(top)
        workspace.add(top, weight=3)
        bottom = ttk.Panedwindow(workspace, orient="horizontal")
        self._audio_bottom_paned_v104 = bottom
        self._build_research_quadrant_v46(bottom)
        self._build_celdra_reserve_v104(bottom)
        workspace.add(bottom, weight=2)
        self.audio_bottom_paned_v46 = bottom

        status = ttk.Frame(parent)
        status.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        status.columnconfigure(1, weight=1)
        self.audio_status = tk.StringVar(value="Mixer catalog has not been loaded.")
        ttk.Label(status, textvariable=self.audio_status).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.audio_progress = ttk.Progressbar(
            status,
            maximum=100.0,
            mode="determinate",
            style="Accent.Horizontal.TProgressbar",
        )
        self.audio_progress.grid(row=0, column=1, sticky="ew")
        ttk.Label(status, text=f"Playback: {self.playback.backend_name}").grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.sequence_payloads = self._mixer_sequence_rows_v40
        self.program_payloads = self._mixer_candidate_rows_v40
        self._install_audio_shortcuts_v98()
        self.after_idle(self._set_audio_sashes_v46)

    def _build_celdra_reserve_v104(self, parent: ttk.Panedwindow) -> None:
        frame = ttk.LabelFrame(parent, text="Celdra — audio research guide", padding=7)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        header.columnconfigure(0, weight=1)
        self._audio_celdra_title_v98 = tk.StringVar(value="CELDRA — AUDIO RESEARCH")
        self._audio_celdra_pose_label_v98 = tk.StringVar(value="SMILE")
        ttk.Label(header, textvariable=self._audio_celdra_title_v98, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._audio_celdra_pose_label_v98, font=("Fixedsys", 8)).grid(row=0, column=1, sticky="e")

        body = ttk.Panedwindow(frame, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew")
        guide = ttk.Frame(body, padding=(3, 2, 7, 2))
        guide.columnconfigure(0, weight=1)
        guide.rowconfigure(1, weight=1)
        self._audio_celdra_step_v98 = tk.StringVar(value="What we are looking for")
        ttk.Label(guide, textvariable=self._audio_celdra_step_v98, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))
        text_frame = ttk.Frame(guide)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        text = tk.Text(
            text_frame,
            wrap="word",
            state="disabled",
            background="#151b24",
            foreground="#d6e3f1",
            insertbackground="#d6e3f1",
            padx=8,
            pady=7,
        )
        text_y = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=text_y.set)
        text.grid(row=0, column=0, sticky="nsew")
        text_y.grid(row=0, column=1, sticky="ns")
        self._audio_celdra_text_v98 = text
        primary = ttk.Frame(guide)
        primary.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(primary, text="Prepare / Refresh", command=self._prepare_audio_research_v104, style="Accent.TButton").pack(side="left")
        ttk.Button(primary, text="Explain Selection", command=self._audio_celdra_explain_selection_v98).pack(side="left", padx=(5, 0))
        ttk.Button(primary, text="Next Experiment", command=self._audio_celdra_next_experiment_v98).pack(side="left", padx=(5, 0))
        secondary = ttk.Frame(guide)
        secondary.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(secondary, text="Tutorial", command=self._audio_celdra_start_tutorial_v98).pack(side="left")
        ttk.Button(secondary, text="Back", command=lambda: self._audio_celdra_tutorial_delta_v98(-1)).pack(side="left", padx=(4, 0))
        ttk.Button(secondary, text="Next", command=lambda: self._audio_celdra_tutorial_delta_v98(1)).pack(side="left", padx=(4, 0))
        ttk.Button(secondary, text="Research Status", command=self._audio_celdra_research_status_v98).pack(side="left", padx=(8, 0))
        body.add(guide, weight=3)

        portrait = ttk.Frame(body, padding=(7, 2, 2, 2))
        portrait.columnconfigure(0, weight=1)
        portrait.rowconfigure(0, weight=1)
        canvas = tk.Canvas(
            portrait,
            width=225,
            height=255,
            background="#10151d",
            highlightthickness=1,
            highlightbackground="#344253",
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.bind("<Configure>", self._audio_celdra_canvas_resized_v98)
        self._audio_celdra_canvas_v98 = canvas
        ttk.Label(
            portrait,
            text="Current research pose\nSelection-aware guide",
            justify="center",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        body.add(portrait, weight=2)
        parent.add(frame, weight=2)
        self._audio_celdra_show_overview_v98()

    def _set_audio_sashes_v46(self) -> None:
        try:
            self.update_idletasks()
            top = self._audio_top_paned_v104
            if top is not None and len(tuple(top.panes())) >= 3:
                width = max(600, top.winfo_width())
                top.sashpos(0, round(width * 0.37))
                top.sashpos(1, round(width * 0.72))
            bottom = self._audio_bottom_paned_v104
            if bottom is not None and len(tuple(bottom.panes())) >= 2:
                width = max(500, bottom.winfo_width())
                bottom.sashpos(0, round(width * 0.55))
            workspace = getattr(self, "audio_workspace_paned_v46", None)
            if workspace is not None and len(tuple(workspace.panes())) >= 2:
                height = max(400, workspace.winfo_height())
                workspace.sashpos(0, round(height * 0.58))
        except (AttributeError, tk.TclError):
            pass

    def _sequence_selected_v46(self) -> None:
        super()._sequence_selected_v46()
        if hasattr(self, "_audio_celdra_explain_selection_v98"):
            self.after(120, self._audio_celdra_explain_selection_v98)

    def _candidate_selected_v40(self) -> None:
        super()._candidate_selected_v40()
        if hasattr(self, "_audio_celdra_explain_selection_v98"):
            self.after(120, self._audio_celdra_explain_selection_v98)

    def _sample_selected_v46(self) -> None:
        super()._sample_selected_v46()
        if hasattr(self, "_audio_celdra_explain_selection_v98"):
            self.after(120, self._audio_celdra_explain_selection_v98)

    # ------------------------------------------------------------------
    # Consume the RUN ALL caches before users open heavy tabs.
    # ------------------------------------------------------------------
    def _refresh_visual_assets(self) -> None:
        project = getattr(self, "project", None)
        self._visual_generation += 1
        generation = self._visual_generation
        self.visual_tree.delete(*self.visual_tree.get_children())
        self.visual_payloads.clear()
        if project is None:
            return
        query = self.visual_search.get().strip().casefold()
        category = self.visual_category.get() if hasattr(self, "visual_category") else "All"
        self.visual_status.set("Loading prepared 3D asset list…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def work() -> list[dict[str, Any]]:
            cached = load_cache(project, "visual")
            if cached is None:
                from fragmenter_public_gui_v3 import discover_visual_assets_v3

                return discover_visual_assets_v3(project, query=query, category=category, limit=100_000)
            rows = [dict(row) for row in cached.get("items") or [] if isinstance(row, dict)]
            output = []
            for row in rows:
                if category != "All" and str(row.get("kind") or "") != category:
                    continue
                haystack = " ".join(str(row.get(key) or "") for key in ("name", "kind", "relative_path")).casefold()
                if query and query not in haystack:
                    continue
                output.append(row)
            return output

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._visual_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Asset list failed: {error}")
                return
            self.visual_progress["value"] = 100.0
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(str(row.get("kind") or "Unclassified"), []).append(row)
            asset_index = 0
            for group_index, kind in enumerate(sorted(grouped, key=category_sort_key)):
                category_iid = f"category_{group_index}"
                children = grouped[kind]
                self.visual_tree.insert(
                    "",
                    "end",
                    iid=category_iid,
                    text=kind,
                    values=(f"{len(children):,} assets", "", ""),
                    open=bool(query) or category != "All",
                )
                for row in children:
                    iid = f"asset_{asset_index}"
                    asset_index += 1
                    confidence = str(row.get("classification_confidence") or "")
                    self.visual_tree.insert(
                        category_iid,
                        "end",
                        iid=iid,
                        text=str(row.get("name") or "asset"),
                        values=(confidence, f"{int(row.get('size') or 0):,}", str(row.get("relative_path") or "")),
                    )
                    self.visual_payloads[iid] = row
            self.visual_status.set(f"Prepared list loaded: {len(rows):,} assets in {len(grouped):,} categories.")

        self._local_worker("prepared-visual-list-v104", work, done)

    def _hydrate_public_lists_v104(self) -> None:
        if getattr(self, "project", None) is None:
            return
        loaded = getattr(self, "_lazy_loaded_tabs_v40", None)
        if isinstance(loaded, set):
            loaded.update({"3D / Assets", "Audio"})
        self._refresh_visual_assets()
        self._refresh_simple_audio()
        self._refresh_audio_readiness_v40()
        self._refresh_audio_sequences()
        self._refresh_audio_pipeline_status_v104()
        self._update_research_prep_status_v104()

    def _project_loaded(self) -> None:
        super()._project_loaded()
        if getattr(self, "project", None) is not None and load_cache(self.project, "summary") is not None:
            self.after_idle(self._hydrate_public_lists_v104)

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        super()._run_all_done(result, error)
        if not error and isinstance(result, dict) and str(result.get("status") or "") == "complete":
            self.after(180, self._hydrate_public_lists_v104)

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V104"
            metadata["run_all_public_list_preparation"] = True
            metadata["audio_library_policy"] = "playable_wav_only"
            metadata["audio_library_scrollable_sidebar"] = True
            metadata["audio_library_click_sort"] = True
            metadata["obsolete_graph_catalog_gate_removed"] = True
            metadata["mixer_layout"] = "sortable_top_research_bottom_left_celdra_far_right"
            metadata["celdra_audio_guide_selection_aware"] = True
        return payload

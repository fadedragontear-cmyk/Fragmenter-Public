#!/usr/bin/env python3
"""V38: canonical project pipeline, runnable stages, first-scan Celdra and audio workbench.

The accepted V37 visual implementation is inherited unchanged. This layer only
rebuilds RUN ALL and audio around the consolidated workspace and pipeline v8.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import fragmenter_public_gui_v5 as gui_v5
import fragmenter_public_gui_v9 as gui_v9
import fragmenter_public_gui_v12 as gui_v12
from fragmenter_public_gui import _json_text, _open_path, _replace_text
from fragmenter_public_gui_v37 import PublicFragmenterAppV37
from project_sound_v1 import canonical_snddata_path, sound_decoded_root, sound_reports_root, sound_source_root
from run_all_executor_v8 import (
    build_run_all_actions_v8,
    execute_pipeline_v8,
    execute_run_all_v8,
    execute_stage_v8,
    is_first_scan_v8,
)
from run_all_plan_v2 import build_run_all_plan_v2, celdra_line
from snddata_audition_matrix_v1 import render_audition_matrix
from snddata_mapping_store_v1 import (
    list_mappings,
    mapping_store_path,
    remove_mapping,
    set_mapping,
)
from snddata_music_system_v5 import sequence_rows as sequence_rows_v5

# Retain the layered GUI lifecycle while replacing the old recursive pipeline
# globals wherever inherited methods still resolve them at runtime.
gui_v5.build_run_all_actions_v4 = build_run_all_actions_v8
gui_v5.execute_run_all_v4 = execute_run_all_v8
gui_v12.build_run_all_plan = build_run_all_plan_v2

CELDRA_WAIT_LINES = (
    "Still scanning. The progress bar is moving, which is more than I can say for the file naming convention.",
    "I have encountered another compressed member. It has declined to explain itself.",
    "No intervention is required. I am merely being observed by several thousand assets.",
    "The scanner remains operational. The ISO remains committed to suspense.",
    "I am counting bytes because counting intentions has proven unreliable.",
    "This is taking a while. I have used the time to develop concerns about SNDDATA.",
)


def sequence_rows_v38(project) -> list[dict[str, Any]]:
    """Merge exact-source manual mappings into the active v5 sequence catalog."""
    rows = [dict(row) for row in sequence_rows_v5(project)]
    source = canonical_snddata_path(project)
    if not source.is_file():
        return rows
    saved = {str(row.get("sequence_id") or ""): row for row in list_mappings(mapping_store_path(project), source)}
    for row in rows:
        mapping = saved.get(str(row.get("sequence_id") or ""))
        if not mapping:
            continue
        row["saved_mapping"] = mapping
        old = str(row.get("routing_status") or "unresolved")
        row["routing_status"] = f"saved {mapping.get('status')}: {mapping.get('program_resource')} | {old}"
        row["mapping_status"] = "saved"
    return rows


gui_v9.sequence_rows = sequence_rows_v38


class PublicFragmenterAppV38(PublicFragmenterAppV37):
    """Keep V37 visuals frozen while making project preparation and audio testable."""

    def __init__(self) -> None:
        self._stage_run_buttons_v38: dict[str, ttk.Button] = {}
        self._pipeline_plan_rows_v38: dict[str, dict[str, Any]] = {}
        self._audio_pipeline_buttons_v38: list[ttk.Button] = []
        self._celdra_console_v38: tk.Text | None = None
        self._celdra_first_scan_v38 = False
        self._celdra_progress_marks_v38: set[tuple[str, int]] = set()
        self._celdra_stage_index_v38 = 0
        self.audio_pipeline_status_v38: tk.StringVar | None = None
        self.audio_pipeline_details_v38: tk.Text | None = None
        self.audio_mapping_status_v38: tk.StringVar | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Canonical Pipeline + Audio")

    # ------------------------------------------------------------------
    # RUN ALL / individually runnable stages
    # ------------------------------------------------------------------
    def _build_run_all(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.run_button = ttk.Button(toolbar, text="RUN ALL", command=self._run_all, style="Accent.TButton")
        self.run_button.pack(side="left", padx=(0, 6))
        self.cancel_button = ttk.Button(toolbar, text="Cancel", command=self._cancel_task, state="disabled")
        self.cancel_button.pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Refresh Plan", command=self._refresh_run_plan).pack(side="left")
        ttk.Label(
            toolbar,
            text="Every stage uses the same canonical pipeline. Individual Run buttons force only that stage.",
        ).pack(side="right")

        self.run_paned = ttk.Panedwindow(parent, orient="vertical")
        self.run_paned.grid(row=1, column=0, sticky="nsew")

        top = ttk.Frame(self.run_paned)
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)
        top.rowconfigure(0, weight=1)

        tree_frame = ttk.LabelFrame(top, text="Pipeline plan", padding=4)
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.run_tree = ttk.Treeview(tree_frame, columns=("status", "description"), show="tree headings")
        self.run_tree.heading("#0", text="Stage")
        self.run_tree.heading("status", text="Status")
        self.run_tree.heading("description", text="Description")
        self.run_tree.column("#0", width=205, stretch=False)
        self.run_tree.column("status", width=90, stretch=False)
        self.run_tree.column("description", width=560, stretch=True)
        tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.run_tree.yview)
        self.run_tree.configure(yscrollcommand=tree_y.set)
        self.run_tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")

        progress_box = ttk.LabelFrame(top, text="Stage progress / direct run", padding=5)
        progress_box.grid(row=0, column=1, sticky="nsew")
        progress_box.columnconfigure(1, weight=1)
        self.stage_progress_frame = progress_box
        self.run_paned.add(top, weight=3)

        bottom = ttk.Frame(self.run_paned)
        bottom.columnconfigure(0, weight=2)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(2, weight=1)

        self.overall_progress_label = tk.StringVar(value="Overall progress: idle")
        ttk.Label(bottom, textvariable=self.overall_progress_label).grid(row=0, column=0, columnspan=2, sticky="w")
        self.overall_progress = ttk.Progressbar(bottom, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar")
        self.overall_progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 5))

        log_frame = ttk.LabelFrame(bottom, text="Pipeline console", padding=4)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 7))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.run_log = tk.Text(log_frame, height=9, wrap="word")
        log_y = ttk.Scrollbar(log_frame, orient="vertical", command=self.run_log.yview)
        self.run_log.configure(yscrollcommand=log_y.set)
        self.run_log.grid(row=0, column=0, sticky="nsew")
        log_y.grid(row=0, column=1, sticky="ns")

        celdra = ttk.LabelFrame(bottom, text="Celdra — first-scan console", padding=4)
        celdra.grid(row=2, column=1, sticky="nsew")
        celdra.columnconfigure(0, weight=1)
        celdra.rowconfigure(0, weight=1)
        self._celdra_console_v38 = tk.Text(celdra, height=9, wrap="word", state="disabled")
        celdra_y = ttk.Scrollbar(celdra, orient="vertical", command=self._celdra_console_v38.yview)
        self._celdra_console_v38.configure(yscrollcommand=celdra_y.set)
        self._celdra_console_v38.grid(row=0, column=0, sticky="nsew")
        celdra_y.grid(row=0, column=1, sticky="ns")
        self._set_celdra_text_v38("Celdra remains offline until the first full project scan.\n")
        self.run_paned.add(bottom, weight=1)

    def _refresh_run_plan(self) -> None:
        if not hasattr(self, "run_tree"):
            return
        self.run_tree.delete(*self.run_tree.get_children())
        for child in tuple(self.stage_progress_frame.winfo_children()):
            child.destroy()
        self._stage_bars.clear()
        self._stage_values.clear()
        self._stage_order.clear()
        self._stage_run_buttons_v38.clear()
        self._pipeline_plan_rows_v38.clear()
        project = self.project
        if project is None:
            return
        try:
            plan = build_run_all_plan_v2(project)
        except Exception as exc:
            self._append_log(str(exc))
            return
        for row_index, stage in enumerate(plan["stages"]):
            key = str(stage["key"])
            self._pipeline_plan_rows_v38[key] = dict(stage)
            self.run_tree.insert(
                "",
                "end",
                iid=key,
                text=stage["label"],
                values=(stage["status"], stage["description"]),
            )
            ttk.Label(self.stage_progress_frame, text=stage["label"]).grid(row=row_index, column=0, sticky="w", padx=(0, 6), pady=2)
            bar = ttk.Progressbar(self.stage_progress_frame, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar", length=150)
            bar.grid(row=row_index, column=1, sticky="ew", pady=2)
            button = ttk.Button(self.stage_progress_frame, text="Run", width=7, command=lambda stage_key=key: self._run_stage_v38(stage_key))
            button.grid(row=row_index, column=2, padx=(6, 0), pady=2)
            self._stage_bars[key] = bar
            self._stage_values[key] = 0.0
            self._stage_order.append(key)
            self._stage_run_buttons_v38[key] = button
        self.overall_progress["value"] = 0.0
        self.overall_progress_label.set("Overall progress: ready")

    def _set_busy(self, active: bool, label: str = "Idle") -> None:
        super()._set_busy(active, label)
        state = "disabled" if active else "normal"
        for button in tuple(self._stage_run_buttons_v38.values()):
            try:
                button.configure(state=state)
            except tk.TclError:
                pass
        for button in tuple(self._audio_pipeline_buttons_v38):
            try:
                button.configure(state=state)
            except tk.TclError:
                pass

    def _run_all(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        self.cancel_event = threading.Event()
        self._celdra_first_scan_v38 = is_first_scan_v8(project)
        self._celdra_progress_marks_v38.clear()
        self._celdra_stage_index_v38 = 0
        if self._celdra_first_scan_v38:
            self._set_celdra_text_v38("")
            self._celdra_say_v38("Hello! What project or idea are you diving into today?")
        else:
            self._set_celdra_text_v38("This project already has a completed scan state. Celdra commentary is disabled for repeat runs.\n")
        self._set_busy(True, "RUN ALL")
        self.run_log.delete("1.0", "end")
        self.overall_progress["value"] = 0.0
        self.overall_progress_label.set("Overall progress: starting")

        def callback(event: dict[str, Any]) -> None:
            self.events.put({"kind": "run_event", "event": event})

        self._background(
            "RUN ALL",
            lambda: execute_run_all_v8(project, callback=callback, cancel_event=self.cancel_event),
            self._run_all_done,
            already_busy=True,
        )

    def _run_stage_v38(self, stage_key: str) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        stage = self._pipeline_plan_rows_v38.get(stage_key) or {"label": stage_key}
        label = f"Pipeline: {stage.get('label') or stage_key}"
        self._celdra_first_scan_v38 = False
        self.cancel_event = threading.Event()
        self._set_busy(True, label)
        self._set_stage_progress(stage_key, 0.0, "running")

        def callback(event: dict[str, Any]) -> None:
            self.events.put({"kind": "run_event", "event": event})

        self._background(
            label,
            lambda: execute_stage_v8(project, stage_key, reuse=False, callback=callback, cancel_event=self.cancel_event),
            lambda result, error: self._pipeline_stage_done_v38(stage_key, result, error),
            already_busy=True,
        )

    def _pipeline_stage_done_v38(self, stage_key: str, result: Any, error: Exception | None) -> None:
        if error:
            self._set_stage_progress(stage_key, self._stage_values.get(stage_key, 0.0), "failed")
            self._append_log(f"{stage_key} failed: {error}")
        else:
            status = str(result.get("status") or "complete")
            self._set_stage_progress(stage_key, 100.0 if status == "complete" else self._stage_values.get(stage_key, 0.0), status)
            self._append_log(f"{stage_key}: {status}")
        self._refresh_run_plan()
        self._refresh_reports()
        self._refresh_simple_audio()
        self._refresh_audio_sequences()

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        super()._handle_run_event(event)
        if not self._celdra_first_scan_v38:
            return
        stage_key = str(event.get("stage") or "")
        kind = str(event.get("kind") or "")
        if kind == "start":
            row = self._pipeline_plan_rows_v38.get(stage_key) or {}
            lines = list(row.get("celdra_lines") or [])
            index = 1 if stage_key == "project_check" and len(lines) > 1 else 0
            line = celdra_line(row, index)
            if line:
                self._celdra_say_v38(line)
            self._celdra_stage_index_v38 += 1
        elif kind == "progress":
            percent = event.get("percent")
            if not isinstance(percent, (int, float)):
                return
            for mark in (25, 50, 75):
                marker = (stage_key, mark)
                if float(percent) >= mark and marker not in self._celdra_progress_marks_v38:
                    self._celdra_progress_marks_v38.add(marker)
                    offset = (self._celdra_stage_index_v38 + mark // 25) % len(CELDRA_WAIT_LINES)
                    self._celdra_say_v38(CELDRA_WAIT_LINES[offset])
        elif kind == "finish" and str(event.get("status") or "") == "failed":
            self._celdra_say_v38("The scan has stopped at a real error. I have preserved the evidence and resisted improvisation.")

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        if self._celdra_first_scan_v38:
            if error or (result and result.get("status") == "failed"):
                self._celdra_say_v38("Fresh scan incomplete. The logs know why. I have declined to fabricate success.")
            else:
                self._celdra_say_v38("Fresh scan complete. I will now return to being decorative.")
        super()._run_all_done(result, error)
        self._celdra_first_scan_v38 = False

    def _set_celdra_text_v38(self, text: str) -> None:
        widget = self._celdra_console_v38
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _celdra_say_v38(self, text: str) -> None:
        widget = self._celdra_console_v38
        if widget is None or not text:
            return
        widget.configure(state="normal")
        widget.insert("end", f"Celdra> {text.rstrip()}\n")
        widget.see("end")
        widget.configure(state="disabled")

    # ------------------------------------------------------------------
    # Canonical audio pipeline and mixer persistence
    # ------------------------------------------------------------------
    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        notebook = next((child for child in parent.winfo_children() if isinstance(child, ttk.Notebook)), None)
        if notebook is not None:
            pipeline = ttk.Frame(notebook, padding=7)
            pipeline.columnconfigure(0, weight=1)
            pipeline.rowconfigure(3, weight=1)
            notebook.insert(0, pipeline, text="Audio Pipeline")
            self._build_audio_pipeline_v38(pipeline)

        mixer = self.sequence_tree.master
        controls = ttk.LabelFrame(mixer, text="Canonical mixer audition / mapping", padding=5)
        controls.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for label, command in (
            ("Previous Candidate", lambda: self._select_candidate_delta_v38(-1)),
            ("Next Candidate", lambda: self._select_candidate_delta_v38(1)),
            ("Save Mapping", self._audio_use_mapping),
            ("Clear Mapping", self._audio_clear_mapping_v38),
            ("Audition Matrix", self._audio_audition_matrix_v38),
        ):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=(0, 6))
        self.audio_mapping_status_v38 = tk.StringVar(value="Mappings are bound to the exact SNDDATA SHA-256 and never modify game data.")
        ttk.Label(controls, textvariable=self.audio_mapping_status_v38).pack(side="left", padx=(6, 0), fill="x", expand=True)

    def _build_audio_pipeline_v38(self, parent: ttk.Frame) -> None:
        intro = ttk.Label(
            parent,
            text=(
                "One canonical audio workspace: extracted/audio → decoded/audio → reports/audio. "
                "Direct streams and SNDDATA sequencing are separate stages."
            ),
            wraplength=1100,
        )
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 7))

        actions = ttk.LabelFrame(parent, text="Pipeline", padding=6)
        actions.grid(row=1, column=0, sticky="ew")
        buttons = (
            ("Run Audio Pipeline", self._run_audio_pipeline_v38, True),
            ("Extract Sources", lambda: self._run_audio_stage_v38("sound_extract"), False),
            ("Decode Direct Audio", lambda: self._run_audio_stage_v38("sound_decode"), False),
            ("Extract SNDDATA Samples", lambda: self._run_audio_stage_v38("snddata_samples"), False),
            ("Build Mixer Index", lambda: self._run_audio_stage_v38("snddata_mixer"), False),
            ("Refresh Library", self._refresh_simple_audio, False),
            ("Open Decoded Audio", self._open_decoded_audio_v38, False),
        )
        for label, command, accent in buttons:
            kwargs: dict[str, Any] = {"text": label, "command": command}
            if accent:
                kwargs["style"] = "Accent.TButton"
            button = ttk.Button(actions, **kwargs)
            button.pack(side="left", padx=(0, 6))
            self._audio_pipeline_buttons_v38.append(button)

        self.audio_pipeline_status_v38 = tk.StringVar(value="Audio pipeline ready.")
        ttk.Label(parent, textvariable=self.audio_pipeline_status_v38).grid(row=2, column=0, sticky="ew", pady=(7, 4))
        details_frame = ttk.Frame(parent)
        details_frame.grid(row=3, column=0, sticky="nsew")
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
                    "source": "extracted/audio",
                    "decoded": "decoded/audio",
                    "reports": "reports/audio",
                    "work": "work/audio",
                    "mixer": "Sequence → routing mode → Program resource → exact sample IDs → WAV",
                    "writes_game_data": False,
                }
            ),
        )

    def _run_audio_pipeline_v38(self) -> None:
        self._run_audio_work_v38(("sound_extract", "sound_decode", "snddata_samples", "snddata_mixer"), "Audio Pipeline")

    def _run_audio_stage_v38(self, stage_key: str) -> None:
        self._run_audio_work_v38((stage_key,), f"Audio: {stage_key}")

    def _run_audio_work_v38(self, stage_keys: tuple[str, ...], label: str) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        self.cancel_event = threading.Event()
        self._celdra_first_scan_v38 = False
        self._set_busy(True, label)
        if self.audio_pipeline_status_v38 is not None:
            self.audio_pipeline_status_v38.set(f"Running {', '.join(stage_keys)}…")

        def callback(event: dict[str, Any]) -> None:
            self.events.put({"kind": "run_event", "event": event})

        self._background(
            label,
            lambda: execute_pipeline_v8(project, stage_keys=stage_keys, reuse=False, callback=callback, cancel_event=self.cancel_event),
            self._audio_pipeline_done_v38,
            already_busy=True,
        )

    def _audio_pipeline_done_v38(self, result: Any, error: Exception | None) -> None:
        if self.audio_pipeline_status_v38 is not None:
            self.audio_pipeline_status_v38.set(f"Audio pipeline failed: {error}" if error else f"Audio pipeline: {result.get('status')}")
        if self.audio_pipeline_details_v38 is not None:
            _replace_text(self.audio_pipeline_details_v38, str(error) if error else _json_text(result))
        self._refresh_run_plan()
        self._refresh_simple_audio()
        self._refresh_audio_sequences()
        self._refresh_reports()

    def _select_candidate_delta_v38(self, delta: int) -> None:
        children = list(self.program_tree.get_children())
        if not children:
            return
        selected = self.program_tree.selection()
        current = children.index(selected[0]) if selected and selected[0] in children else 0
        target = children[(current + int(delta)) % len(children)]
        self.program_tree.selection_set(target)
        self.program_tree.focus(target)
        self.program_tree.see(target)
        candidate = self.program_payloads.get(target)
        if candidate is not None:
            _replace_text(self.audio_details, _json_text(candidate))

    def _audio_use_mapping(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence()
        candidate = self._selected_program()
        if project is None:
            return
        if sequence is None or candidate is None:
            messagebox.showinfo("Music Mixer", "Select a sequence and Program-resource candidate.")
            return
        source = canonical_snddata_path(project)
        if not source.is_file():
            messagebox.showerror("Save Mapping", f"Canonical SNDDATA is missing: {source}")
            return
        resource = str(candidate.get("resource_id") or "")
        if not resource and candidate.get("resource_offset") is not None:
            resource = f"resource@0x{int(candidate['resource_offset']):X}"
        mode = self._selected_routing_mode() if hasattr(self, "_selected_routing_mode") else None
        required = list(candidate.get("required_program_indexes") or candidate.get("program_indexes_required") or [])
        program_index = int(required[0]) if len(required) == 1 else None
        try:
            record = set_mapping(
                mapping_store_path(project),
                source,
                str(sequence["sequence_id"]),
                resource,
                status="manual",
                notes=f"Fragmenter V38 audition; routing={mode or 'unresolved'}",
                program_index=program_index,
            )
            sequence["saved_mapping"] = record
            if self.audio_mapping_status_v38 is not None:
                self.audio_mapping_status_v38.set(f"Saved {sequence['sequence_id']} → {resource}")
            _replace_text(self.audio_details, _json_text({"saved_mapping": record, "candidate": candidate, "writes_game_data": False}))
            selected = self.sequence_tree.selection()
            if selected:
                try:
                    self.sequence_tree.set(selected[0], "mapping", f"saved: {resource}")
                except tk.TclError:
                    pass
        except Exception as exc:
            messagebox.showerror("Save Mapping", str(exc))

    def _audio_clear_mapping_v38(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence()
        if project is None or sequence is None:
            return
        source = canonical_snddata_path(project)
        try:
            removed = remove_mapping(mapping_store_path(project), source, str(sequence["sequence_id"]))
            sequence.pop("saved_mapping", None)
            if self.audio_mapping_status_v38 is not None:
                self.audio_mapping_status_v38.set("Mapping removed." if removed else "No saved mapping existed for this sequence.")
            self._refresh_audio_sequences()
        except Exception as exc:
            messagebox.showerror("Clear Mapping", str(exc))

    def _audio_audition_matrix_v38(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence()
        if project is None or self.task_active:
            return
        sequence_ids = [str(sequence["sequence_id"])] if sequence else None
        self.audio_status.set("Rendering bounded evidence-backed audition matrix…")

        def done(result: Any, error: Exception | None) -> None:
            if error:
                self.audio_status.set(f"Audition Matrix failed: {error}")
                _replace_text(self.audio_details, str(error))
            else:
                self.audio_status.set(f"Audition Matrix rendered {result.get('rendered', 0)} WAVs.")
                _replace_text(self.audio_details, _json_text(result))
                self._refresh_simple_audio()
                self._refresh_reports()

        self._background(
            "Audition Matrix",
            lambda: render_audition_matrix(project, sequence_ids=sequence_ids),
            done,
        )

    def _open_decoded_audio_v38(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            _open_path(sound_decoded_root(project))
        except Exception as exc:
            messagebox.showerror("Open Decoded Audio", str(exc))


def main() -> int:
    app = PublicFragmenterAppV38()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

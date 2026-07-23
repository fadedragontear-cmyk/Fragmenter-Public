#!/usr/bin/env python3
"""Tenth public GUI pass: isolate read-only research tools from normal workflows."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from audio_diagnostics_v1 import write_audio_diagnostics
from ccsf_asset_diagnostics_v1 import build_research_bundle
from ccsf_studioccs_compare_v1 import write_compare_report
from ccsf_texture_library_probe_v1 import run_texture_library_probe
from fragmenter_public_gui import _json_text, _open_path, _replace_text
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v8 import PublicFragmenterAppV8
from fragmenter_public_gui_v9 import PublicFragmenterAppV9
from morning_diagnostics_v1 import run_morning_diagnostics
from snddata_audition_matrix_v1 import render_audition_matrix
from snddata_field_probe_v1 import write_field_probe
from snddata_forensics_v1 import analyze_and_write as analyze_snddata_forensics
from snddata_music_system_v5 import analyze_project_snddata

PUBLIC_TABS_V10 = (
    "Setup",
    "RUN ALL",
    "3D / Assets",
    "Audio",
    "Server Explorer",
    "Backups",
    "Research",
    "Reports",
    "Settings",
)


class PublicFragmenterAppV10(PublicFragmenterAppV9):
    """Keep release-facing workflows clean while retaining the research workbench."""

    def __init__(self) -> None:
        self._research_active = False
        self._research_buttons: list[ttk.Button] = []
        self.research_status: tk.StringVar | None = None
        self.research_progress: ttk.Progressbar | None = None
        self.research_details: tk.Text | None = None
        self.research_texture_pattern: tk.StringVar | None = None
        self.research_max_assets: tk.IntVar | None = None
        super().__init__()

    # ------------------------------------------------------------------
    # Tab layout
    # ------------------------------------------------------------------
    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tabs: dict[str, ttk.Frame] = {}
        builders = {
            "Setup": self._build_setup,
            "RUN ALL": self._build_run_all,
            "3D / Assets": self._build_visual,
            "Audio": self._build_audio,
            "Server Explorer": self._build_server,
            "Backups": self._build_backups,
            "Research": self._build_research,
            "Reports": self._build_reports,
            "Settings": self._build_settings,
        }
        for label in PUBLIC_TABS_V10:
            frame = ttk.Frame(self.notebook, padding=8)
            self.notebook.add(frame, text=label)
            self.tabs[label] = frame
            builders[label](frame)

    def _build_visual(self, parent: ttk.Frame) -> None:
        # Bypass V9 only because V9 does not own visual behavior. V8 remains the
        # active preview implementation; V10 removes its research-only button.
        PublicFragmenterAppV8._build_visual(self, parent)
        self._remove_button_by_text(parent, "Diagnostic + OBJ")

    def _build_audio(self, parent: ttk.Frame) -> None:
        # Build the V8 working audio page without V9's research toolbar. V9's v5
        # sequence/candidate/render methods remain inherited and authoritative.
        PublicFragmenterAppV8._build_audio(self, parent)
        mixer = self.sequence_tree.master
        mixer.rowconfigure(1, weight=1)
        tools = ttk.LabelFrame(mixer, text="Mixer routing", padding=5)
        tools.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        ttk.Label(tools, text="Routing").pack(side="left")
        self.audio_routing_mode = tk.StringVar(value="Auto")
        routing = ttk.Combobox(
            tools,
            textvariable=self.audio_routing_mode,
            values=("Auto", "program_change", "channel_as_program"),
            state="readonly",
            width=20,
        )
        routing.pack(side="left", padx=(6, 10))
        routing.bind("<<ComboboxSelected>>", lambda _event: self._refresh_audio_candidates())
        ttk.Button(
            tools,
            text="Rebuild Mixer Index",
            command=self._rebuild_mixer_index_v5,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Label(tools, text="Diagnostics and experimental probes are in Research.").pack(side="right")

    def _remove_button_by_text(self, widget: tk.Misc, text: str) -> None:
        try:
            for child in tuple(widget.winfo_children()):
                if isinstance(child, ttk.Button) and str(child.cget("text")) == text:
                    child.destroy()
                    continue
                self._remove_button_by_text(child, text)
        except tk.TclError:
            return

    # ------------------------------------------------------------------
    # Research tab
    # ------------------------------------------------------------------
    def _build_research(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)

        ttk.Label(
            parent,
            text=(
                "Read-only format research and diagnostic exports. These tools can scan thousands of assets or "
                "reparse the full SNDDATA container; they are intentionally separated from normal preview and playback."
            ),
            wraplength=1120,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        visual = ttk.LabelFrame(parent, text="Visual / CCSF research", padding=7)
        visual.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        visual.columnconfigure(5, weight=1)
        self._research_button(visual, "Selected Asset Bundle + OBJ", self._research_selected_asset).grid(row=0, column=0, padx=(0, 8), pady=2)
        ttk.Label(visual, text="Library filter").grid(row=0, column=1, sticky="e")
        self.research_texture_pattern = tk.StringVar()
        ttk.Entry(visual, textvariable=self.research_texture_pattern, width=24).grid(row=0, column=2, padx=(5, 8), sticky="ew")
        ttk.Label(visual, text="Max assets (0 = all)").grid(row=0, column=3, sticky="e")
        self.research_max_assets = tk.IntVar(value=0)
        ttk.Spinbox(visual, from_=0, to=100000, textvariable=self.research_max_assets, width=9).grid(row=0, column=4, padx=(5, 8))
        self._research_button(visual, "Texture Library Probe", self._research_texture_library).grid(row=0, column=5, sticky="w", pady=2)
        ttk.Label(
            visual,
            text="Selected Asset uses the current 3D asset, animation and frame. Library Probe inventories ownership/setup patterns across extracted CCS files.",
            wraplength=1050,
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(5, 0))

        audio = ttk.LabelFrame(parent, text="Audio / SNDDATA research", padding=7)
        audio.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        for column in range(5):
            audio.columnconfigure(column, weight=1)
        for column, (label, command) in enumerate(
            (
                ("SNDDATA Field Probe", self._research_audio_field_probe),
                ("Parser Funnel Diagnostics", self._run_audio_diagnostics),
                ("Routing Forensics", self._run_snddata_forensics),
                ("Audition Matrix", self._run_audition_matrix),
                ("Rebuild Mixer Index v5", self._research_rebuild_mixer_index),
            )
        ):
            self._research_button(audio, label, command).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0), pady=2)

        bundles = ttk.LabelFrame(parent, text="Bundles and outputs", padding=7)
        bundles.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        self._research_button(bundles, "Run Texture + Audio Probes", self._research_all_probes, style="Accent.TButton").pack(side="left")
        self._research_button(bundles, "Morning Research Bundle", self._run_morning_bundle).pack(side="left", padx=(6, 0))
        ttk.Button(bundles, text="Open Diagnostics Folder", command=self._open_diagnostics_folder).pack(side="left", padx=(6, 0))
        ttk.Button(bundles, text="Refresh Reports Tab", command=self._refresh_reports).pack(side="left", padx=(6, 0))

        output = ttk.Frame(parent)
        output.grid(row=4, column=0, sticky="nsew")
        output.columnconfigure(0, weight=1)
        output.rowconfigure(2, weight=1)
        self.research_status = tk.StringVar(value="Research workbench ready. No source files are modified by these actions.")
        ttk.Label(output, textvariable=self.research_status, wraplength=1120).grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.research_progress = ttk.Progressbar(output, maximum=100.0, mode="determinate")
        self.research_progress.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.research_details = tk.Text(output, wrap="word")
        self.research_details.grid(row=2, column=0, sticky="nsew")
        _replace_text(
            self.research_details,
            _json_text(
                {
                    "research_tab": "read_only",
                    "visual": ["selected asset provenance bundle", "StudioCCS comparison", "library texture ownership census"],
                    "audio": ["field/ADPCM probe", "strict MIDI boundaries", "routing hypotheses", "bounded audition WAVs"],
                    "outputs": "project/reports/diagnostics",
                }
            ),
        )

    def _research_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        style: str | None = None,
    ) -> ttk.Button:
        kwargs: dict[str, Any] = {"text": text, "command": command}
        if style:
            kwargs["style"] = style
        button = ttk.Button(parent, **kwargs)
        self._research_buttons.append(button)
        return button

    def _set_research_busy(self, busy: bool, label: str = "") -> None:
        self._research_active = busy
        for button in self._research_buttons:
            try:
                button.configure(state="disabled" if busy else "normal")
            except tk.TclError:
                pass
        if self.research_progress is not None:
            if busy:
                self.research_progress.configure(mode="indeterminate")
                self.research_progress.start(60)
            else:
                self.research_progress.stop()
                self.research_progress.configure(mode="determinate")
        if busy and self.research_status is not None:
            self.research_status.set(label)

    def _research_job(
        self,
        label: str,
        status: str,
        work: Callable[[], Any],
        *,
        refresh_sequences: bool = False,
    ) -> None:
        if self._research_active:
            messagebox.showinfo("Research", "Another research task is already running.")
            return
        self._set_research_busy(True, status)
        if self.research_progress is not None:
            self.research_progress["value"] = 0.0

        def done(result: Any, error: Exception | None) -> None:
            self._set_research_busy(False)
            if error:
                if self.research_progress is not None:
                    self.research_progress["value"] = 0.0
                if self.research_status is not None:
                    self.research_status.set(f"{label} failed: {error}")
                if self.research_details is not None:
                    _replace_text(self.research_details, f"{type(error).__name__}: {error}")
                return
            if self.research_progress is not None:
                self.research_progress["value"] = 100.0
            if self.research_status is not None:
                self.research_status.set(f"{label} complete")
            if self.research_details is not None:
                _replace_text(self.research_details, _json_text(result))
            if refresh_sequences:
                self._refresh_audio_sequences()
            self._refresh_reports()
            self._refresh_simple_audio()

        self._local_worker(label.lower().replace(" ", "-"), work, done)

    # ------------------------------------------------------------------
    # Visual research actions
    # ------------------------------------------------------------------
    def _research_selected_asset(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None:
            return
        if row is None:
            messagebox.showinfo("Research", "Select an asset in 3D / Assets first.")
            return
        animation = self.animation_name.get().strip() or None
        frame = max(0, int(self.animation_frame.get()))
        output = project.workspace_path("asset_diagnostics") / _safe_folder(str(row["relative_path"]))

        def work() -> dict[str, Any]:
            research = build_research_bundle(row["absolute_path"], output, animation_name=animation, frame=frame)
            compare = write_compare_report(row["absolute_path"], output, animation_name=animation, frame=frame)
            return {
                "source": row["absolute_path"],
                "relative_path": row["relative_path"],
                "animation": animation,
                "frame": frame,
                "output_dir": str(output),
                "summary": research["diagnostics"]["summary"],
                "diagnostic_json": research["diagnostics"]["report_path"],
                "diagnostic_text": research["diagnostics"]["text_report_path"],
                "obj": research["obj"],
                "compare_json": compare["report_path"],
                "compare_text": compare["text_report_path"],
            }

        self._research_job(
            "Selected Asset Bundle",
            f"Building diagnostic, StudioCCS comparison and provenance OBJ for {row['name']}…",
            work,
        )

    def _texture_probe_arguments(self) -> tuple[list[str] | None, int]:
        pattern = self.research_texture_pattern.get().strip() if self.research_texture_pattern is not None else ""
        try:
            maximum = max(0, int(self.research_max_assets.get())) if self.research_max_assets is not None else 0
        except (tk.TclError, ValueError):
            maximum = 0
        return ([pattern] if pattern else None), maximum

    def _research_texture_library(self) -> None:
        project = self._require_project()
        if project is None:
            return
        patterns, maximum = self._texture_probe_arguments()
        scope = f"up to {maximum:,} matching assets" if maximum else "the full matching CCS library"
        self._research_job(
            "Texture Library Probe",
            f"Scanning {scope} for Texture/CLUT ownership and missing setup-record patterns…",
            lambda: run_texture_library_probe(project, patterns=patterns, max_assets=maximum),
        )

    # ------------------------------------------------------------------
    # Audio research actions
    # ------------------------------------------------------------------
    def _research_audio_field_probe(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._research_job(
            "SNDDATA Field Probe",
            "Inspecting SCEIHead/Vagi/Smpl/Sset fields, ADPCM density and strict MIDI boundaries…",
            lambda: write_field_probe(project),
        )

    def _run_audio_diagnostics(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._research_job(
            "Audio Diagnostics",
            "Comparing raw SCEI tags with retained parser sections…",
            lambda: write_audio_diagnostics(project),
        )

    def _run_snddata_forensics(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._research_job(
            "Routing Forensics",
            "Testing Program Change, channel→Program and SCEISequ evidence…",
            lambda: analyze_snddata_forensics(project),
        )

    def _run_audition_matrix(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._research_job(
            "Audition Matrix",
            "Rendering bounded proof WAVs only for complete Program/slot/sample hypotheses…",
            lambda: render_audition_matrix(project),
        )

    def _research_rebuild_mixer_index(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._research_job(
            "Mixer Index v5",
            "Parsing FF0A tracks, Program tables, slots, sample coverage and routing hypotheses…",
            lambda: analyze_project_snddata(project),
            refresh_sequences=True,
        )

    def _research_all_probes(self) -> None:
        project = self._require_project()
        if project is None:
            return
        patterns, maximum = self._texture_probe_arguments()

        def work() -> dict[str, Any]:
            return {
                "texture_probe": run_texture_library_probe(project, patterns=patterns, max_assets=maximum),
                "audio_probe": write_field_probe(project),
            }

        self._research_job(
            "Texture + Audio Probes",
            "Running the library texture census followed by the SNDDATA field probe…",
            work,
        )

    def _run_morning_bundle(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._research_job(
            "Morning Research Bundle",
            "Running selected visual provenance, StudioCCS comparison, audio forensics and bounded auditions…",
            lambda: run_morning_diagnostics(project),
            refresh_sequences=True,
        )

    def _open_diagnostics_folder(self) -> None:
        project = self._require_project()
        if project is None:
            return
        path = project.workspace_path("diagnostics")
        path.mkdir(parents=True, exist_ok=True)
        try:
            _open_path(path)
        except Exception as exc:
            if self.research_status is not None:
                self.research_status.set(f"Diagnostics folder: {path} ({exc})")


def main() -> int:
    app = PublicFragmenterAppV10()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

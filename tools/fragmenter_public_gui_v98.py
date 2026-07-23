#!/usr/bin/env python3
"""V98: put Celdra's dragongirl research guide inside the SNDDATA mixer."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from celdra_audio_guide_v1 import NEXT_STEPS, QUICK_HELP, RESEARCH_OVERVIEW, TUTORIAL_STEPS
from fragmenter_public_gui_v97 import PublicFragmenterAppV97
from snddata_research_workbench_v1 import readiness


class PublicFragmenterAppV98(PublicFragmenterAppV97):
    """Make the reserved mixer quadrant a useful, selection-aware Celdra guide."""

    def __init__(self) -> None:
        self._audio_research_page_v98: ttk.Frame | None = None
        self._audio_sequence_search_entry_v98: ttk.Entry | None = None
        self._audio_celdra_canvas_v98: tk.Canvas | None = None
        self._audio_celdra_title_v98: tk.StringVar | None = None
        self._audio_celdra_pose_label_v98: tk.StringVar | None = None
        self._audio_celdra_step_v98: tk.StringVar | None = None
        self._audio_celdra_text_v98: tk.Text | None = None
        self._audio_celdra_tutorial_index_v98 = 0
        self._audio_celdra_current_pose_v98 = "smile"
        self._audio_celdra_pose_cache_v98: dict[str, tuple[tk.PhotoImage, tk.PhotoImage, tk.PhotoImage]] = {}
        self._audio_celdra_display_v98: tk.PhotoImage | None = None
        self._audio_celdra_resize_after_v98: str | None = None
        self._audio_celdra_initialized_v98 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra SNDDATA Research Guide V98")
        self.after_idle(self._initialize_audio_celdra_v98)

    # ------------------------------------------------------------------
    # Mixer construction and navigation bindings.
    # ------------------------------------------------------------------
    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        self._audio_research_page_v98 = parent
        super()._build_research_mixer_v40(parent)
        self._audio_sequence_search_entry_v98 = self._find_audio_search_entry_v98(parent)
        self._install_audio_shortcuts_v98()

    def _build_celdra_reserve_v46(self, parent: ttk.Panedwindow) -> None:
        frame = ttk.LabelFrame(parent, text="Celdra - SNDDATA research guide", padding=7)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        self._audio_celdra_title_v98 = tk.StringVar(value="SNDDATA RESEARCH GUIDE")
        self._audio_celdra_pose_label_v98 = tk.StringVar(value="SMILE")
        ttk.Label(
            header,
            textvariable=self._audio_celdra_title_v98,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self._audio_celdra_pose_label_v98,
            font=("Fixedsys", 8),
        ).grid(row=0, column=1, sticky="e")

        body = ttk.Panedwindow(frame, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew")

        portrait = ttk.Frame(body, padding=3)
        portrait.columnconfigure(0, weight=1)
        portrait.rowconfigure(0, weight=1)
        canvas = tk.Canvas(
            portrait,
            width=190,
            height=235,
            background="#10151d",
            highlightthickness=1,
            highlightbackground="#344253",
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.bind("<Configure>", self._audio_celdra_canvas_resized_v98)
        self._audio_celdra_canvas_v98 = canvas
        ttk.Label(
            portrait,
            text="Classified dragongirl pose\nIndependent of RUN ALL playback",
            justify="center",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        body.add(portrait, weight=2)

        guide = ttk.Frame(body, padding=(7, 3))
        guide.columnconfigure(0, weight=1)
        guide.rowconfigure(1, weight=1)
        self._audio_celdra_step_v98 = tk.StringVar(value="Overview")
        ttk.Label(
            guide,
            textvariable=self._audio_celdra_step_v98,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        text_frame = ttk.Frame(guide)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        text = tk.Text(
            text_frame,
            wrap="word",
            height=10,
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
        body.add(guide, weight=3)

        tutorial = ttk.Frame(frame)
        tutorial.grid(row=2, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(tutorial, text="Start Tutorial", command=self._audio_celdra_start_tutorial_v98).pack(side="left")
        ttk.Button(tutorial, text="Back", command=lambda: self._audio_celdra_tutorial_delta_v98(-1)).pack(side="left", padx=(5, 0))
        ttk.Button(tutorial, text="Next", command=lambda: self._audio_celdra_tutorial_delta_v98(1), style="Accent.TButton").pack(side="left", padx=(5, 10))
        ttk.Button(tutorial, text="Explain Selection", command=self._audio_celdra_explain_selection_v98).pack(side="left")
        ttk.Button(tutorial, text="Research Status", command=self._audio_celdra_research_status_v98).pack(side="left", padx=(5, 0))
        ttk.Button(tutorial, text="Next Experiment", command=self._audio_celdra_next_experiment_v98).pack(side="left", padx=(5, 0))

        browse = ttk.Frame(frame)
        browse.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(browse, text="Navigate").pack(side="left", padx=(0, 5))
        ttk.Button(browse, text="Prev Seq", command=lambda: self._audio_tree_delta_v98(self.sequence_tree, -1)).pack(side="left")
        ttk.Button(browse, text="Next Seq", command=lambda: self._audio_tree_delta_v98(self.sequence_tree, 1)).pack(side="left", padx=(4, 8))
        ttk.Button(browse, text="Prev Candidate", command=lambda: self._audio_tree_delta_v98(self.program_tree, -1)).pack(side="left")
        ttk.Button(browse, text="Next Candidate", command=lambda: self._audio_tree_delta_v98(self.program_tree, 1)).pack(side="left", padx=(4, 8))
        ttk.Button(browse, text="Find", command=self._audio_celdra_focus_search_v98).pack(side="left")
        ttk.Button(browse, text="Clear Find", command=self._audio_celdra_clear_search_v98).pack(side="left", padx=(4, 0))

        pages = ttk.Frame(frame)
        pages.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        ttk.Label(pages, text="Research pages").pack(side="left", padx=(0, 5))
        for label in ("Evidence", "Samples", "Notes", "Flags", "Research Bundle"):
            ttk.Button(
                pages,
                text=label,
                command=lambda selected=label: self._select_audio_research_page_v98(selected),
            ).pack(side="left", padx=(0, 4))
        ttk.Button(pages, text="Audio Pipeline", command=lambda: self._select_audio_subtab_v98("Audio Pipeline")).pack(side="right")
        ttk.Button(pages, text="Sample Classifier", command=lambda: self._select_audio_subtab_v98("Sample Classifier")).pack(side="right", padx=(0, 4))

        ttk.Label(
            frame,
            text="Ctrl+F search  |  Alt+Up/Down sequence  |  Alt+Left/Right candidate  |  All research actions are project-local and non-destructive.",
            anchor="w",
        ).grid(row=5, column=0, sticky="ew", pady=(6, 0))

        parent.add(frame, weight=2)
        self._audio_celdra_show_overview_v98()

    @staticmethod
    def _descendants_v98(widget: tk.Misc):
        for child in widget.winfo_children():
            yield child
            yield from PublicFragmenterAppV98._descendants_v98(child)

    def _find_audio_search_entry_v98(self, parent: tk.Misc) -> ttk.Entry | None:
        variable = self.audio_sequence_search_v40
        if variable is None:
            return None
        for child in self._descendants_v98(parent):
            if not isinstance(child, ttk.Entry):
                continue
            try:
                if str(child.cget("textvariable")) == str(variable):
                    return child
            except tk.TclError:
                continue
        return None

    def _install_audio_shortcuts_v98(self) -> None:
        self.bind("<Control-f>", self._audio_shortcut_find_v98, add="+")
        self.bind("<Alt-Up>", lambda event: self._audio_shortcut_tree_v98(event, self.sequence_tree, -1), add="+")
        self.bind("<Alt-Down>", lambda event: self._audio_shortcut_tree_v98(event, self.sequence_tree, 1), add="+")
        self.bind("<Alt-Left>", lambda event: self._audio_shortcut_tree_v98(event, self.program_tree, -1), add="+")
        self.bind("<Alt-Right>", lambda event: self._audio_shortcut_tree_v98(event, self.program_tree, 1), add="+")

    def _audio_mixer_active_v98(self) -> bool:
        if self._selected_tab_label_v40() != "Audio":
            return False
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if notebook is None:
            return False
        try:
            return str(notebook.tab(notebook.select(), "text")) == "SNDDATA Research Mixer"
        except tk.TclError:
            return False

    def _audio_shortcut_find_v98(self, _event: tk.Event) -> str | None:
        if not self._audio_mixer_active_v98():
            return None
        self._audio_celdra_focus_search_v98()
        return "break"

    def _audio_shortcut_tree_v98(self, _event: tk.Event, tree: ttk.Treeview, delta: int) -> str | None:
        if not self._audio_mixer_active_v98():
            return None
        self._audio_tree_delta_v98(tree, delta)
        return "break"

    def _audio_tree_delta_v98(self, tree: ttk.Treeview, delta: int) -> None:
        rows = list(tree.get_children(""))
        if not rows:
            self._audio_celdra_say_v98("Nothing to navigate", "This table is empty under the current project, search, filter, or routing mode.", "confused")
            return
        selected = tree.selection()
        current = rows.index(selected[0]) if selected and selected[0] in rows else 0
        target = rows[(current + int(delta)) % len(rows)]
        tree.selection_set(target)
        tree.focus(target)
        tree.see(target)
        tree.event_generate("<<TreeviewSelect>>")
        tree.focus_set()

    def _audio_celdra_focus_search_v98(self) -> None:
        entry = self._audio_sequence_search_entry_v98
        if entry is None:
            return
        entry.focus_set()
        entry.selection_range(0, "end")
        self._audio_celdra_say_v98("Find a sequence", "Type any part of a sequence ID, routing state, or mapped resource. The filter applies before the table is populated.", "smile")

    def _audio_celdra_clear_search_v98(self) -> None:
        if self.audio_sequence_search_v40 is not None:
            self.audio_sequence_search_v40.set("")
        if self.audio_sequence_filter_v40 is not None:
            self.audio_sequence_filter_v40.set("All")
        self._refresh_audio_sequences()
        self._audio_celdra_say_v98("Search cleared", "Showing the full sequence catalog again. Saved mappings and renderer-complete rows remain sorted toward the top.", "wink")

    # ------------------------------------------------------------------
    # Independent dragongirl portrait for the mixer.
    # ------------------------------------------------------------------
    def _initialize_audio_celdra_v98(self) -> None:
        if self._audio_celdra_initialized_v98:
            return
        self._audio_celdra_initialized_v98 = True
        self._audio_celdra_set_pose_v98("smile")
        self._audio_celdra_show_overview_v98()

    def _audio_celdra_canvas_resized_v98(self, _event: tk.Event | None = None) -> None:
        if self._audio_celdra_resize_after_v98 is not None:
            try:
                self.after_cancel(self._audio_celdra_resize_after_v98)
            except tk.TclError:
                pass
        self._audio_celdra_resize_after_v98 = self.after(120, self._audio_celdra_redraw_v98)

    def _audio_celdra_set_pose_v98(self, pose: str) -> None:
        folded = str(pose or "smile").casefold()
        self._audio_celdra_current_pose_v98 = folded
        if self._audio_celdra_pose_label_v98 is not None:
            self._audio_celdra_pose_label_v98.set(folded.upper())
        if folded not in self._audio_celdra_pose_cache_v98:
            try:
                self._reload_manifest_emotes_v56()
                row = self._celdra_manifest_emotes_v56.get(folded)
                if row is None:
                    for fallback in ("smile", "neutral", "wink", "confused"):
                        row = self._celdra_manifest_emotes_v56.get(fallback)
                        if row is not None:
                            folded = fallback
                            self._audio_celdra_current_pose_v98 = folded
                            break
                if row is None:
                    raise KeyError("No classified dragongirl pose is available")
                source = self.celdra_asset_root_v50 / str(row.get("source") or "")
                if not source.is_file():
                    raise FileNotFoundError(source)
                image = tk.PhotoImage(file=str(source))
                crop = row.get("crop") if isinstance(row.get("crop"), dict) else {}
                cropped = self._crop_photo_v52(
                    image,
                    {
                        "x": int(crop.get("x") or 0),
                        "y": int(crop.get("y") or 0),
                        "width": max(1, int(crop.get("width") or 1)),
                        "height": max(1, int(crop.get("height") or 1)),
                    },
                )
                prepared = cropped.zoom(2, 2) if cropped.width() <= 260 else cropped
                self._audio_celdra_pose_cache_v98[folded] = (image, cropped, prepared)
            except (KeyError, OSError, ValueError, tk.TclError) as exc:
                canvas = self._audio_celdra_canvas_v98
                if canvas is not None:
                    canvas.delete("all")
                    canvas.create_text(
                        12,
                        12,
                        anchor="nw",
                        fill="#efbd70",
                        text=f"CELDRA PORTRAIT UNAVAILABLE\n{exc}",
                    )
                return
        self._audio_celdra_redraw_v98()

    def _audio_celdra_redraw_v98(self) -> None:
        self._audio_celdra_resize_after_v98 = None
        canvas = self._audio_celdra_canvas_v98
        cached = self._audio_celdra_pose_cache_v98.get(self._audio_celdra_current_pose_v98)
        if canvas is None or cached is None:
            return
        width = max(80, canvas.winfo_width())
        height = max(100, canvas.winfo_height())
        prepared = cached[2]
        display = self._fit_photo_v50(prepared, max(60, width - 12), max(70, height - 26))
        self._audio_celdra_display_v98 = display
        canvas.delete("all")
        canvas.create_image(width // 2, max(8, (height - 18) // 2), image=display, anchor="center")
        canvas.create_rectangle(0, height - 20, width, height, fill="#071426", outline="")
        canvas.create_text(
            width // 2,
            height - 10,
            text=f"CELDRA // AUDIO RESEARCH // {self._audio_celdra_current_pose_v98.upper()}",
            fill="#79cff1",
            font=("Fixedsys", 7, "bold"),
            anchor="center",
        )

    # ------------------------------------------------------------------
    # Tutorial, context summaries, and useful next actions.
    # ------------------------------------------------------------------
    def _audio_celdra_replace_text_v98(self, value: str) -> None:
        widget = self._audio_celdra_text_v98
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", str(value or ""))
        widget.configure(state="disabled")
        widget.see("1.0")

    def _audio_celdra_say_v98(self, title: str, body: str, pose: str = "smile") -> None:
        if self._audio_celdra_title_v98 is not None:
            self._audio_celdra_title_v98.set("CELDRA - AUDIO RESEARCH")
        if self._audio_celdra_step_v98 is not None:
            self._audio_celdra_step_v98.set(str(title or "Research guidance"))
        self._audio_celdra_replace_text_v98(str(body or ""))
        self.after_idle(lambda selected=pose: self._audio_celdra_set_pose_v98(selected))

    def _audio_celdra_show_overview_v98(self) -> None:
        self._audio_celdra_say_v98("What this page is for", RESEARCH_OVERVIEW, "smile")

    def _audio_celdra_start_tutorial_v98(self) -> None:
        self._audio_celdra_tutorial_index_v98 = 0
        self._audio_celdra_show_tutorial_step_v98()

    def _audio_celdra_tutorial_delta_v98(self, delta: int) -> None:
        self._audio_celdra_tutorial_index_v98 = (
            self._audio_celdra_tutorial_index_v98 + int(delta)
        ) % len(TUTORIAL_STEPS)
        self._audio_celdra_show_tutorial_step_v98()

    def _audio_celdra_show_tutorial_step_v98(self) -> None:
        step = TUTORIAL_STEPS[self._audio_celdra_tutorial_index_v98]
        self._audio_celdra_say_v98(str(step["title"]), str(step["body"]), str(step["pose"]))

    def _audio_celdra_explain_selection_v98(self) -> None:
        sample = self._selected_sample_v46()
        candidate = self._selected_candidate_v40()
        sequence = self._selected_sequence_v40()
        if sample is not None:
            sample_id = sample.get("sample_id") if sample.get("sample_id") is not None else sample.get("index")
            playable = bool(sample.get("playable"))
            missing = bool(sample.get("missing"))
            body = (
                f"Sample {sample_id}: {int(sample.get('sample_rate') or 0):,} Hz, "
                f"approximately {float(sample.get('duration_estimate') or 0.0):.3f} seconds. "
                f"Playable WAV: {'yes' if playable else 'no'}. Missing from required coverage: {'yes' if missing else 'no'}.\n\n"
                + (
                    "Play it, compare its timbre against neighboring IDs, then record instrument family, root note, loop behavior, and confidence in Notes."
                    if playable
                    else "This row is evidence of a required sample wall. Trace the sample ID through the corrected bank boundary report before changing routing assumptions."
                )
            )
            self._audio_celdra_say_v98("Selected sample", body, "smile" if playable else "sad")
            return
        if candidate is not None and sequence is not None:
            review = candidate.get("review") or {}
            status = str(candidate.get("status") or "unknown")
            missing = str(candidate.get("missing_summary") or candidate.get("status_detail") or "none listed")
            body = (
                f"Sequence {sequence.get('sequence_id')} under {candidate.get('routing_mode') or 'unresolved'} routing.\n"
                f"Candidate {candidate.get('resource_id')} is rank {candidate.get('rank')} with renderer status {status}.\n"
                f"Decoded sample coverage: {candidate.get('coverage')}. First missing wall: {missing}.\n"
                f"Saved mapping: {'yes' if candidate.get('saved') else 'no'}. Review: {review.get('status') or 'untested'}.\n\n"
                + self._candidate_advice_v98(candidate)
            )
            pose = "excited" if status == "renderable" else "suspicious"
            self._audio_celdra_say_v98("Selected Program candidate", body, pose)
            return
        if sequence is not None:
            body = (
                f"Sequence {sequence.get('sequence_id')} contains {int(sequence.get('note_on_count') or 0):,} note-on events across "
                f"{int(sequence.get('track_count') or 0)} tracks. Preferred routing: {sequence.get('preferred_hypothesis') or 'unresolved'}. "
                f"Candidates: {int(sequence.get('candidates') or 0)}, renderer-complete: {int(sequence.get('renderable') or 0)}, "
                f"reviews: {int(sequence.get('review_count') or 0)}. First wall: {sequence.get('first_wall') or sequence.get('routing_status') or 'not reported'}."
            )
            self._audio_celdra_say_v98("Selected sequence", body, "confused" if not sequence.get("preferred_hypothesis") else "smile")
            return
        self._audio_celdra_say_v98("Select a research target", "Choose a sequence first. Fragmenter will load ranked Program candidates and exact required sample evidence without reparsing SNDDATA on every click.", "confused")

    @staticmethod
    def _candidate_advice_v98(candidate: dict[str, Any]) -> str:
        status = str(candidate.get("status") or "unknown")
        if status == "renderable":
            return "This candidate can produce the bounded current preview. Render Event / PCM Proof first, render the candidate, listen critically, then record a verdict instead of treating successful playback as confirmation."
        if status == "missing_programs":
            return "Required Program indexes are absent from this resource. Compare the alternate routing mode and neighboring Program resources before searching for replacement samples."
        if status == "missing_samples":
            return "Program coverage exists, but required sample IDs are missing or undecoded. Open Samples and trace those exact IDs through the corrected sample library."
        return "Inspect the evidence summary and first wall. Flag the candidate when the unresolved structure deserves a focused comparison bundle."

    def _audio_celdra_research_status_v98(self) -> None:
        project = self.project
        if project is None:
            self._audio_celdra_say_v98("Research status", "No project is loaded. Load a project before asking the mixer to prove anything.", "confused")
            return
        try:
            state = readiness(project)
        except Exception as exc:
            self._audio_celdra_say_v98("Research status failed", str(exc), "sad")
            return
        source = "ready" if state.get("snddata_exists") else "missing"
        catalog = "ready" if state.get("catalog_exists") else "missing"
        samples = "ready" if state.get("sample_report_exists") else "missing"
        body = (
            f"SNDDATA source: {source}. Mixer catalog: {catalog}. Corrected sample report: {samples}.\n"
            f"Loaded view: {len(self._mixer_sequence_rows_v40):,} sequences, {len(self._mixer_candidate_rows_v40):,} candidates, "
            f"{len(self._mixer_sample_rows_v40):,} required sample rows. Playback backend: {self.playback.backend_name}.\n\n"
            "Current research frontier:\n- " + "\n- ".join(NEXT_STEPS)
        )
        pose = "smile" if source == catalog == samples == "ready" else "suspicious"
        self._audio_celdra_say_v98("Current audio research status", body, pose)

    def _audio_celdra_next_experiment_v98(self) -> None:
        project = self.project
        if project is None:
            self._audio_celdra_say_v98("Next experiment", "Load a project. The guide will not invent paths or use repository-level sample data as a substitute.", "confused")
            return
        try:
            state = readiness(project)
        except Exception as exc:
            self._audio_celdra_say_v98("Next experiment", str(exc), "sad")
            return
        if not state.get("snddata_exists") or not state.get("sample_report_exists") or not state.get("catalog_exists"):
            missing = [
                label
                for label, key in (
                    ("SNDDATA source", "snddata_exists"),
                    ("corrected sample report", "sample_report_exists"),
                    ("mixer catalog", "catalog_exists"),
                )
                if not state.get(key)
            ]
            self._select_audio_subtab_v98("Audio Pipeline")
            self._audio_celdra_say_v98("Next experiment - complete the pipeline", "Missing: " + ", ".join(missing) + ". I opened Audio Pipeline. Run only the missing stages, then return and refresh the catalog.", "suspicious")
            return
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if sequence is None:
            self.sequence_tree.focus_set()
            self._audio_celdra_say_v98("Next experiment - choose a sequence", "Select a sequence with unresolved routing or at least one renderer-complete candidate. Start with a small event count when testing a new interpretation.", "smile")
            return
        if candidate is None:
            self.program_tree.focus_set()
            self._audio_celdra_say_v98("Next experiment - choose a candidate", "Compare Auto with each explicit routing mode. Select the highest-ranked non-rejected candidate whose first wall answers a useful question.", "confused")
            return
        status = str(candidate.get("status") or "unknown")
        if status == "missing_samples":
            self._select_audio_research_page_v98("Samples")
            self._audio_celdra_say_v98("Next experiment - trace missing samples", "I opened Samples. Record the exact missing IDs, compare corrected boundaries and flat comparison IDs, and decide whether the wall is extraction, aliasing, or the routing hypothesis itself.", "suspicious")
            return
        if status == "missing_programs":
            self._audio_celdra_say_v98("Next experiment - test routing", "Switch between program_change and channel_as_program, then compare neighboring Program resources. Do not compensate for absent Program indexes by assigning convenient samples.", "confused")
            return
        if status == "renderable":
            self._audio_celdra_say_v98("Next experiment - bounded listening test", "Render Event / PCM Proof, then Render Candidate. Compare timing, instrument identity, pitch, loops, and envelope behavior. Save a Plausible, Confirmed, or Rejected verdict with the reason you heard—not merely that a WAV was produced.", "excited")
            return
        self._select_audio_research_page_v98("Evidence")
        self._audio_celdra_say_v98("Next experiment - document the wall", self._candidate_advice_v98(candidate) + " I opened Evidence so the unresolved structure remains visible while you write the next test.", "suspicious")

    def _select_audio_research_page_v98(self, label: str) -> None:
        tabs = self.audio_research_tabs_v46
        if tabs is None:
            return
        wanted = str(label)
        for tab_id in tabs.tabs():
            try:
                current = str(tabs.tab(tab_id, "text"))
            except tk.TclError:
                continue
            if current == wanted:
                tabs.select(tab_id)
                help_text = dict(QUICK_HELP).get(wanted, f"Opened {wanted}.")
                self._audio_celdra_say_v98(wanted, help_text, "wink" if wanted in {"Notes", "Flags", "Research Bundle"} else "smile")
                return

    def _select_audio_subtab_v98(self, label: str) -> None:
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if notebook is None:
            return
        for tab_id in notebook.tabs():
            try:
                current = str(notebook.tab(tab_id, "text"))
            except tk.TclError:
                continue
            if current == label:
                notebook.select(tab_id)
                return

    # ------------------------------------------------------------------
    # Selection hooks keep Celdra useful without taking over the page.
    # ------------------------------------------------------------------
    def _sequence_selected_v46(self) -> None:
        super()._sequence_selected_v46()
        self.after_idle(self._audio_celdra_explain_selection_v98)

    def _candidate_selected_v40(self) -> None:
        super()._candidate_selected_v40()
        self.after_idle(self._audio_celdra_explain_selection_v98)

    def _sample_selected_v46(self) -> None:
        super()._sample_selected_v46()
        self.after_idle(self._audio_celdra_explain_selection_v98)

    def _refresh_audio_sequences(self, preselect: str | None = None) -> None:
        if self._audio_celdra_text_v98 is not None:
            self._audio_celdra_say_v98("Refreshing sequence catalog", "Reading the cached mixer research model off the UI thread. The selected sequence will be restored when possible.", "smile")
        super()._refresh_audio_sequences(preselect=preselect)

    def _audio_subtab_changed_v47(self, _event: Any = None) -> None:
        super()._audio_subtab_changed_v47(_event)
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if notebook is None:
            return
        try:
            label = str(notebook.tab(notebook.select(), "text"))
        except tk.TclError:
            return
        if label == "SNDDATA Research Mixer" and self._audio_celdra_text_v98 is not None:
            self.after_idle(self._audio_celdra_explain_selection_v98)

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V98"
            metadata["snddata_celdra_dragongirl_guide"] = True
            metadata["snddata_celdra_selection_aware"] = True
            metadata["snddata_celdra_tutorial_steps"] = len(TUTORIAL_STEPS)
        return payload


def main() -> int:
    app = PublicFragmenterAppV98()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

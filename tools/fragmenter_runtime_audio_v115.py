#!/usr/bin/env python3
"""V115 runtime-audio evidence capture, five-layer sampler, and narrow layout repair."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from audio_layer_sampler_v1 import render_layer_sampler
from audio_library_research_v1 import merged_audio_rows
from fragmenter_public_gui import _open_path
from runtime_audio_research_v1 import (
    FUNCTIONS,
    load_observations,
    report_path as runtime_report_path,
    save_observation,
    seed_2026_07_21_captures,
    sequence_signature,
)


class FragmenterRuntimeAudioMixinV115:
    """Add evidence capture and sample layering without altering the pipeline."""

    def __init__(self) -> None:
        self.layer_sampler_tab_v115: ttk.Frame | None = None
        self._layer_sampler_slots_v115: list[dict[str, Any]] = []
        self._layer_sampler_choice_paths_v115: dict[str, str] = {}
        self._layer_sampler_choice_generation_v115 = 0
        self._layer_sampler_last_preview_v115: Path | None = None
        self._layer_sampler_status_v115: tk.StringVar | None = None
        self._runtime_audio_status_v115: tk.StringVar | None = None
        self._runtime_audio_signature_v115: tk.StringVar | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Runtime Audio Research V115")

    # ------------------------------------------------------------------
    # Narrow RUN ALL geometry correction.
    # ------------------------------------------------------------------
    def _refresh_run_plan(self) -> None:
        super()._refresh_run_plan()
        frame = getattr(self, "stage_progress_frame", None)
        if frame is None:
            return
        try:
            frame.columnconfigure(0, minsize=84, weight=0)
            frame.columnconfigure(1, minsize=215, weight=0)
            frame.columnconfigure(2, weight=1)
            for button in getattr(self, "_stage_run_buttons_v38", {}).values():
                button.configure(width=10)
                button.grid_configure(sticky="ew", padx=(0, 7))
        except (AttributeError, tk.TclError):
            pass

    def _apply_middle_layout_v101(self) -> None:
        super()._apply_middle_layout_v101()
        self.after_idle(self._reassert_middle_layout_v115)

    def _reassert_middle_layout_v115(self) -> None:
        """Keep avatar, Gremlin stable, and console as three visible neighbours."""
        pane = getattr(self, "celdra_visual_split_v50", None)
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if pane is None or frame is None or bool(getattr(self, "_celdra_middle_hidden_v103", False)):
            return
        try:
            self.update_idletasks()
            panes = tuple(pane.panes())
            if len(panes) < 3:
                return
            width = max(760, int(pane.winfo_width()))
            stable_width = max(205, min(270, round(width * 0.25)))
            console_width = max(235, min(305, round(width * 0.28)))
            avatar_width = max(190, width - stable_width - console_width)
            pane.sashpos(0, avatar_width)
            pane.sashpos(1, avatar_width + stable_width)
            self._stable_layout_applied_v112 = True
            self._stable_layout_signature_v112 = (round(width / 40) * 40, len(panes))
            wrap = max(175, stable_width - 20)
            status = getattr(self, "_stable_status_label_v109", None)
            if isinstance(status, tk.Label):
                status.configure(wraplength=wrap, justify="left", anchor="w")
        except (AttributeError, tk.TclError):
            pass

    # ------------------------------------------------------------------
    # Audio notebook: preserve existing pages and add one independent sampler.
    # ------------------------------------------------------------------
    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if not isinstance(notebook, ttk.Notebook):
            return
        sampler = ttk.Frame(notebook, padding=7)
        notebook.add(sampler, text="Layer Sampler")
        self.layer_sampler_tab_v115 = sampler
        self._build_layer_sampler_v115(sampler)

    def _audio_subtab_changed_v47(self, event: Any = None) -> None:
        super()._audio_subtab_changed_v47(event)
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if notebook is None or getattr(self, "project", None) is None:
            return
        try:
            label = str(notebook.tab(notebook.select(), "text"))
        except tk.TclError:
            return
        if label == "Layer Sampler":
            self._refresh_layer_sampler_choices_v115()

    def _build_layer_sampler_v115(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(
            parent,
            text=(
                "Layer up to five decoded mono WAVs. Each slot has its own start time, source-WAV loop region, "
                "pitch offset, and gain. This renders a research preview; it does not emulate the PS2 synthesizer."
            ),
            wraplength=1280,
            justify="left",
        ).grid(row=0, column=0, columnspan=10, sticky="ew", pady=(0, 7))

        headers = ("On", "Sample WAV", "", "Start", "Loop", "Loop in", "Loop out", "Pitch", "Gain")
        for column, label in enumerate(headers):
            ttk.Label(parent, text=label).grid(row=1, column=column, sticky="w", padx=(0, 5))

        self._layer_sampler_slots_v115.clear()
        for index in range(5):
            enabled = tk.BooleanVar(value=index == 0)
            sample = tk.StringVar(value="")
            start = tk.DoubleVar(value=0.0)
            loop = tk.BooleanVar(value=False)
            loop_start = tk.DoubleVar(value=0.0)
            loop_end = tk.DoubleVar(value=0.0)
            pitch = tk.DoubleVar(value=0.0)
            gain = tk.DoubleVar(value=1.0)
            combo = ttk.Combobox(parent, textvariable=sample, values=(), state="normal", width=54)
            row = index + 2
            ttk.Checkbutton(parent, variable=enabled).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=2)
            combo.grid(row=row, column=1, sticky="ew", padx=(0, 5), pady=2)
            ttk.Button(
                parent,
                text="Browse",
                command=lambda slot=index: self._browse_layer_sampler_slot_v115(slot),
            ).grid(row=row, column=2, sticky="w", padx=(0, 7), pady=2)
            ttk.Entry(parent, textvariable=start, width=7).grid(row=row, column=3, sticky="w", padx=(0, 7), pady=2)
            ttk.Checkbutton(parent, variable=loop).grid(row=row, column=4, sticky="w", padx=(0, 7), pady=2)
            ttk.Entry(parent, textvariable=loop_start, width=7).grid(row=row, column=5, sticky="w", padx=(0, 7), pady=2)
            ttk.Entry(parent, textvariable=loop_end, width=7).grid(row=row, column=6, sticky="w", padx=(0, 7), pady=2)
            ttk.Spinbox(parent, from_=-36, to=36, increment=1, textvariable=pitch, width=6).grid(
                row=row, column=7, sticky="w", padx=(0, 7), pady=2
            )
            ttk.Spinbox(parent, from_=0.0, to=2.0, increment=0.05, textvariable=gain, width=6).grid(
                row=row, column=8, sticky="w", pady=2
            )
            self._layer_sampler_slots_v115.append(
                {
                    "enabled": enabled,
                    "sample": sample,
                    "combo": combo,
                    "start": start,
                    "loop": loop,
                    "loop_start": loop_start,
                    "loop_end": loop_end,
                    "pitch": pitch,
                    "gain": gain,
                }
            )

        controls = ttk.LabelFrame(parent, text="Preview mix", padding=6)
        controls.grid(row=7, column=0, columnspan=10, sticky="ew", pady=(8, 0))
        ttk.Label(controls, text="Duration (s)").pack(side="left")
        self._layer_sampler_duration_v115 = tk.DoubleVar(value=12.0)
        ttk.Spinbox(
            controls,
            from_=0.1,
            to=120.0,
            increment=0.5,
            textvariable=self._layer_sampler_duration_v115,
            width=7,
        ).pack(side="left", padx=(4, 10))
        ttk.Label(controls, text="Master gain").pack(side="left")
        self._layer_sampler_master_gain_v115 = tk.DoubleVar(value=0.8)
        ttk.Spinbox(
            controls,
            from_=0.0,
            to=2.0,
            increment=0.05,
            textvariable=self._layer_sampler_master_gain_v115,
            width=7,
        ).pack(side="left", padx=(4, 10))
        ttk.Button(
            controls,
            text="Render & Play",
            command=lambda: self._render_layer_sampler_v115(play=True),
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            controls,
            text="Render WAV",
            command=lambda: self._render_layer_sampler_v115(play=False),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Stop", command=self._audio_stop).pack(side="left", padx=(6, 0))
        ttk.Button(
            controls,
            text="Refresh WAV Choices",
            command=lambda: self._refresh_layer_sampler_choices_v115(force=True),
        ).pack(side="left", padx=(12, 0))
        self._layer_sampler_status_v115 = tk.StringVar(
            value="Choose one to five WAVs. Loop out 0 uses the end of the source WAV."
        )
        ttk.Label(controls, textvariable=self._layer_sampler_status_v115).pack(
            side="left", padx=(12, 0), fill="x", expand=True
        )

    def _refresh_layer_sampler_choices_v115(self, *, force: bool = False) -> None:
        project = getattr(self, "project", None)
        if project is None or not self._layer_sampler_slots_v115:
            return
        if self._layer_sampler_choice_paths_v115 and not force:
            return
        self._layer_sampler_choice_generation_v115 += 1
        generation = self._layer_sampler_choice_generation_v115
        if self._layer_sampler_status_v115 is not None:
            self._layer_sampler_status_v115.set("Loading playable WAV choices…")

        def work() -> list[dict[str, Any]]:
            return [
                dict(row)
                for row in merged_audio_rows(project)
                if Path(str(row.get("output_path") or "")).is_file()
                and Path(str(row.get("output_path") or "")).suffix.casefold() == ".wav"
            ]

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._layer_sampler_choice_generation_v115:
                return
            if error:
                if self._layer_sampler_status_v115 is not None:
                    self._layer_sampler_status_v115.set(f"WAV choice load failed: {error}")
                return
            mapping: dict[str, str] = {}
            for index, row in enumerate(rows or []):
                path = Path(str(row.get("output_path") or ""))
                name = str(row.get("name") or path.name)
                category = str(row.get("category") or "Unclassified")
                label = f"{name} [{category}] — {path.name}"
                if label in mapping:
                    label = f"{label} #{index + 1}"
                mapping[label] = str(path)
            self._layer_sampler_choice_paths_v115 = mapping
            values = tuple(mapping)
            for slot in self._layer_sampler_slots_v115:
                combo = slot.get("combo")
                if isinstance(combo, ttk.Combobox):
                    combo.configure(values=values)
            if self._layer_sampler_status_v115 is not None:
                self._layer_sampler_status_v115.set(f"{len(values):,} playable WAV choices loaded.")

        self._local_worker("layer-sampler-choices-v115", work, done)

    def _browse_layer_sampler_slot_v115(self, slot_index: int) -> None:
        path = filedialog.askopenfilename(
            title=f"Choose WAV for sampler slot {slot_index + 1}",
            filetypes=(("WAV files", "*.wav"), ("All files", "*.*")),
        )
        if not path:
            return
        slot = self._layer_sampler_slots_v115[slot_index]
        slot["sample"].set(path)
        slot["enabled"].set(True)

    def _layer_sampler_configuration_v115(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for slot in self._layer_sampler_slots_v115:
            try:
                enabled = bool(slot["enabled"].get())
                selected = str(slot["sample"].get()).strip()
                path = self._layer_sampler_choice_paths_v115.get(selected, selected)
                output.append(
                    {
                        "enabled": enabled,
                        "path": path,
                        "start_seconds": float(slot["start"].get()),
                        "loop": bool(slot["loop"].get()),
                        "loop_start_seconds": float(slot["loop_start"].get()),
                        "loop_end_seconds": float(slot["loop_end"].get()),
                        "pitch_semitones": float(slot["pitch"].get()),
                        "gain": float(slot["gain"].get()),
                    }
                )
            except (tk.TclError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid Layer Sampler value: {exc}") from exc
        return output

    def _render_layer_sampler_v115(self, *, play: bool) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            slots = self._layer_sampler_configuration_v115()
            duration = float(self._layer_sampler_duration_v115.get())
            master_gain = float(self._layer_sampler_master_gain_v115.get())
        except (tk.TclError, TypeError, ValueError) as exc:
            messagebox.showerror("Layer Sampler", str(exc))
            return
        if self._layer_sampler_status_v115 is not None:
            self._layer_sampler_status_v115.set("Rendering five-slot research preview…")

        def done(result: Any, error: Exception | None) -> None:
            if error:
                if self._layer_sampler_status_v115 is not None:
                    self._layer_sampler_status_v115.set(f"Render failed: {error}")
                messagebox.showerror("Layer Sampler", str(error))
                return
            target = Path(str((result or {}).get("output_path") or ""))
            self._layer_sampler_last_preview_v115 = target
            metadata = (result or {}).get("metadata") or {}
            if self._layer_sampler_status_v115 is not None:
                self._layer_sampler_status_v115.set(
                    f"Rendered {int(metadata.get('slot_count') or 0)} slots to {target.name}."
                )
            if play:
                try:
                    self.playback.load(target)
                    self.playback.play()
                except Exception as exc:
                    messagebox.showerror("Layer Sampler playback", str(exc))

        self._local_worker(
            "layer-sampler-render-v115",
            lambda: render_layer_sampler(
                project,
                slots,
                duration_seconds=duration,
                master_gain=master_gain,
            ),
            done,
        )

    # ------------------------------------------------------------------
    # Mixer: record emulator evidence without pretending RAM addresses are mappings.
    # ------------------------------------------------------------------
    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        super()._build_research_mixer_v40(parent)
        rows = []
        for child in parent.winfo_children():
            try:
                info = child.grid_info()
                if info:
                    rows.append(int(info.get("row") or 0))
            except (TypeError, ValueError, tk.TclError):
                continue
        target_row = max(rows, default=0) + 1
        frame = ttk.LabelFrame(parent, text="PCSX2 runtime evidence", padding=6)
        frame.grid(row=target_row, column=0, sticky="ew", pady=(6, 0))
        frame.columnconfigure(13, weight=1)

        self._runtime_audio_cue_v115 = tk.StringVar(value="Login/menu transition")
        self._runtime_audio_function_v115 = tk.StringVar(value="sceMidi_Load")
        self._runtime_audio_address_v115 = tk.StringVar(value="")
        self._runtime_audio_a0_v115 = tk.StringVar(value="")
        self._runtime_audio_a1_v115 = tk.StringVar(value="")
        self._runtime_audio_a2_v115 = tk.StringVar(value="")
        self._runtime_audio_a3_v115 = tk.StringVar(value="")
        self._runtime_audio_ra_v115 = tk.StringVar(value="")
        self._runtime_audio_notes_v115 = tk.StringVar(value="")

        fields = (
            ("Cue", ttk.Entry(frame, textvariable=self._runtime_audio_cue_v115, width=20)),
            ("Function", ttk.Combobox(frame, textvariable=self._runtime_audio_function_v115, values=FUNCTIONS, width=20)),
            ("Addr", ttk.Entry(frame, textvariable=self._runtime_audio_address_v115, width=11)),
            ("a0", ttk.Entry(frame, textvariable=self._runtime_audio_a0_v115, width=11)),
            ("a1", ttk.Entry(frame, textvariable=self._runtime_audio_a1_v115, width=11)),
            ("a2", ttk.Entry(frame, textvariable=self._runtime_audio_a2_v115, width=11)),
            ("a3", ttk.Entry(frame, textvariable=self._runtime_audio_a3_v115, width=11)),
            ("ra", ttk.Entry(frame, textvariable=self._runtime_audio_ra_v115, width=11)),
        )
        column = 0
        for label, control in fields:
            ttk.Label(frame, text=label).grid(row=0, column=column, sticky="w", padx=(0, 3))
            control.grid(row=0, column=column + 1, sticky="w", padx=(0, 7))
            column += 2

        ttk.Label(frame, text="Notes").grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Entry(frame, textvariable=self._runtime_audio_notes_v115).grid(
            row=1, column=1, columnspan=10, sticky="ew", padx=(0, 7), pady=(5, 0)
        )
        ttk.Button(frame, text="Save Capture", command=self._save_runtime_audio_capture_v115).grid(
            row=1, column=11, sticky="w", padx=(0, 5), pady=(5, 0)
        )
        ttk.Button(frame, text="Record Today's 3 Captures", command=self._seed_runtime_audio_captures_v115).grid(
            row=1, column=12, sticky="w", padx=(0, 5), pady=(5, 0)
        )
        ttk.Button(frame, text="Attach Selected Sequence", command=self._attach_runtime_sequence_v115).grid(
            row=1, column=13, sticky="w", padx=(0, 5), pady=(5, 0)
        )
        ttk.Button(frame, text="Open Runtime Log", command=self._open_runtime_audio_log_v115).grid(
            row=1, column=14, sticky="w", pady=(5, 0)
        )

        self._runtime_audio_signature_v115 = tk.StringVar(
            value="Select a sequence, then attach it to produce a 16-byte PCSX2 memory-search signature."
        )
        ttk.Label(
            frame,
            textvariable=self._runtime_audio_signature_v115,
            wraplength=1180,
            justify="left",
        ).grid(row=2, column=0, columnspan=16, sticky="ew", pady=(5, 0))
        self._runtime_audio_status_v115 = tk.StringVar(
            value=(
                "Runtime addresses are session-relative IOP RAM values, not SNDDATA file offsets. "
                "Today confirmed sceMidi_Load and sceMidi_SelectMidi activity during the login/menu transition."
            )
        )
        ttk.Label(
            frame,
            textvariable=self._runtime_audio_status_v115,
            wraplength=1180,
            justify="left",
        ).grid(row=3, column=0, columnspan=16, sticky="ew", pady=(3, 0))

    def _save_runtime_audio_capture_v115(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            save_observation(
                project,
                {
                    "cue_name": self._runtime_audio_cue_v115.get(),
                    "screen": self._runtime_audio_cue_v115.get(),
                    "trigger": "Manual PCSX2 breakpoint capture",
                    "module": "modmidi",
                    "function": self._runtime_audio_function_v115.get(),
                    "function_address": self._runtime_audio_address_v115.get(),
                    "a0": self._runtime_audio_a0_v115.get(),
                    "a1": self._runtime_audio_a1_v115.get(),
                    "a2": self._runtime_audio_a2_v115.get(),
                    "a3": self._runtime_audio_a3_v115.get(),
                    "ra": self._runtime_audio_ra_v115.get(),
                    "notes": self._runtime_audio_notes_v115.get(),
                },
            )
            count = len(load_observations(project).get("observations") or [])
            if self._runtime_audio_status_v115 is not None:
                self._runtime_audio_status_v115.set(f"Runtime capture saved. {count} unique observations in the project log.")
        except Exception as exc:
            messagebox.showerror("Runtime audio capture", str(exc))

    def _seed_runtime_audio_captures_v115(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            seed_2026_07_21_captures(project)
            count = len(load_observations(project).get("observations") or [])
            if self._runtime_audio_status_v115 is not None:
                self._runtime_audio_status_v115.set(
                    f"Today's three clean R3000 captures are recorded. {count} unique observations total."
                )
        except Exception as exc:
            messagebox.showerror("Runtime audio capture", str(exc))

    def _attach_runtime_sequence_v115(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        if project is None or sequence is None:
            messagebox.showinfo("Runtime audio research", "Select a sequence in the left mixer list first.")
            return
        try:
            signature = sequence_signature(project, int(sequence.get("resource_offset") or 0), length=16)
        except Exception as exc:
            messagebox.showerror("Runtime audio research", str(exc))
            return
        sequence_id = str(sequence.get("sequence_id") or "sequence")
        offset = int(signature["resource_offset"])
        existing = self._runtime_audio_notes_v115.get().strip()
        detail = f"{sequence_id}; SNDDATA file offset 0x{offset:X}"
        self._runtime_audio_notes_v115.set(f"{existing}; {detail}".strip("; "))
        if self._runtime_audio_signature_v115 is not None:
            self._runtime_audio_signature_v115.set(
                f"PCSX2 memory search bytes for {sequence_id} @ file 0x{offset:X}: "
                f"{signature['hex_bytes']}  | ASCII {signature['ascii']}  | "
                "Search the bytes; do not treat the file offset as a RAM address."
            )

    def _open_runtime_audio_log_v115(self) -> None:
        project = self._require_project()
        if project is None:
            return
        path = runtime_report_path(project)
        if not path.exists():
            messagebox.showinfo("Runtime audio research", "No runtime captures have been saved yet.")
            return
        _open_path(path)

#!/usr/bin/env python3
"""Ninth public GUI pass: v5 SNDDATA mixer and integrated research actions."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from audio_diagnostics_v1 import write_audio_diagnostics
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v8 import PublicFragmenterAppV8
from morning_diagnostics_v1 import run_morning_diagnostics
from snddata_audition_matrix_v1 import render_audition_matrix
from snddata_forensics_v1 import analyze_and_write as analyze_snddata_forensics
from snddata_music_system_v5 import (
    MusicSystemError,
    _compat_candidate,
    analyze_project_snddata,
    render_sequence,
    sequence_rows,
    sequence_view_model,
)


class PublicFragmenterAppV9(PublicFragmenterAppV8):
    def __init__(self) -> None:
        self.audio_routing_mode: tk.StringVar | None = None
        super().__init__()

    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        mixer = self.sequence_tree.master
        mixer.rowconfigure(1, weight=1)
        tools = ttk.LabelFrame(mixer, text="SNDDATA research / routing", padding=5)
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

        ttk.Button(tools, text="Rebuild Mixer Index", command=self._rebuild_mixer_index_v5, style="Accent.TButton").pack(side="left")
        ttk.Button(tools, text="Audio Diagnostics", command=self._run_audio_diagnostics).pack(side="left", padx=(6, 0))
        ttk.Button(tools, text="Routing Forensics", command=self._run_snddata_forensics).pack(side="left", padx=(6, 0))
        ttk.Button(tools, text="Audition Matrix", command=self._run_audition_matrix).pack(side="left", padx=(6, 0))
        ttk.Button(tools, text="Morning Bundle", command=self._run_morning_bundle).pack(side="left", padx=(6, 0))
        ttk.Button(tools, text="Open Diagnostics", command=self._open_diagnostics_folder).pack(side="right")

    def _selected_routing_mode(self, model: dict[str, Any] | None = None) -> str | None:
        selected = self.audio_routing_mode.get() if self.audio_routing_mode is not None else "Auto"
        if selected != "Auto":
            return selected
        if model is not None:
            return model.get("preferred_hypothesis")
        sequence = self._selected_sequence()
        return sequence.get("preferred_hypothesis") if sequence else None

    def _refresh_audio_sequences(self) -> None:
        project = self.project
        self._audio_generation += 1
        generation = self._audio_generation
        self.sequence_tree.delete(*self.sequence_tree.get_children())
        self.program_tree.delete(*self.program_tree.get_children())
        self.sequence_payloads.clear()
        self.program_payloads.clear()
        if project is None:
            return
        self.audio_status.set("Loading the v5 FF0A-track mixer catalog off the UI thread…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._audio_generation:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Mixer index is not ready: {error}")
                _replace_text(self.audio_details, f"{error}\n\nUse Rebuild Mixer Index. This no longer falls back to implicit Program 0.")
                return
            self.audio_progress["value"] = 100.0
            for index, row in enumerate(rows):
                iid = f"sequence_{index}"
                routing = str(row.get("routing_status") or "unresolved")
                self.sequence_tree.insert("", "end", iid=iid, text=row["sequence_id"], values=(row.get("note_on_count", 0), routing))
                self.sequence_payloads[iid] = row
            program_change = sum(1 for row in rows if row.get("preferred_hypothesis") == "program_change")
            channel = sum(1 for row in rows if row.get("preferred_hypothesis") == "channel_as_program")
            unresolved = len(rows) - program_change - channel
            self.audio_status.set(
                f"Loaded {len(rows)} v5 sequences: Program Change {program_change}; channel→Program hypothesis {channel}; unresolved {unresolved}."
            )
            first = next(iter(self.sequence_payloads), None)
            if first:
                self.sequence_tree.selection_set(first)
                self.sequence_tree.focus(first)
                self._refresh_audio_candidates()

        self._local_worker("music-system-v5-sequences", lambda: sequence_rows(project), done)

    def _refresh_audio_candidates(self) -> None:
        project = self.project
        sequence = self._selected_sequence()
        self._candidate_generation += 1
        generation = self._candidate_generation
        self.program_tree.delete(*self.program_tree.get_children())
        self.program_payloads.clear()
        if project is None or sequence is None:
            return
        selected = self.audio_routing_mode.get() if self.audio_routing_mode is not None else "Auto"
        self.audio_status.set(f"Reading v5 routing evidence for {sequence['sequence_id']} ({selected})…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._candidate_generation:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Program resolver failed: {error}")
                _replace_text(self.audio_details, str(error))
                return
            self.audio_progress["value"] = 100.0
            mode = self._selected_routing_mode(model)
            hypothesis = next((row for row in model.get("routing_hypotheses") or [] if row.get("mode") == mode), None)
            candidates = [_compat_candidate(row) for row in (hypothesis.get("candidates") or [])] if hypothesis else []
            for index, row in enumerate(candidates):
                iid = f"program_{index}"
                self.program_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=row["resource_id"],
                    values=(row["program_count"], len(row.get("required_sample_ids") or []), row["decoded_sample_count"]),
                )
                self.program_payloads[iid] = row
            _replace_text(
                self.audio_details,
                _json_text(
                    {
                        "sequence": {key: value for key, value in model.items() if key not in {"routing_hypotheses", "candidates"}},
                        "selected_hypothesis": hypothesis,
                        "all_hypotheses": model.get("routing_hypotheses"),
                    }
                ),
            )
            best = next((iid for iid, row in self.program_payloads.items() if row.get("status") == "renderable"), next(iter(self.program_payloads), None))
            if best:
                self.program_tree.selection_set(best)
                self.program_tree.focus(best)
            renderable = sum(1 for row in candidates if row.get("status") == "renderable")
            wall = (hypothesis or {}).get("first_wall") or model.get("first_wall") or "no hypothesis selected"
            self.audio_status.set(f"{mode or 'unresolved'}: {len(candidates)} candidates; {renderable} renderer-complete. First wall: {wall}")

        self._local_worker("music-system-v5-candidates", lambda: sequence_view_model(project, sequence["sequence_id"]), done)

    def _audio_render_play(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence()
        candidate = self._selected_program()
        if project is None:
            return
        if sequence is None:
            messagebox.showinfo("Music Mixer", "Select a sequence first.")
            return
        mode = self._selected_routing_mode()
        if mode not in {"program_change", "channel_as_program"}:
            messagebox.showinfo("Music Mixer", "This sequence has no usable routing mode. Run Routing Forensics or select an explicit hypothesis.")
            return
        resource_offset = int(candidate["resource_offset"]) if candidate is not None else None
        self.audio_status.set(f"Rendering {mode} with exact parsed Program slots and decoded sample IDs…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(result: Any, error: Exception | None) -> None:
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                if isinstance(error, MusicSystemError):
                    payload = {
                        "status": "not_renderable",
                        "routing_mode": mode,
                        "error": str(error),
                        "missing": error.missing,
                        "sequence": sequence,
                        "candidate": candidate,
                        "implicit_program_zero": False,
                    }
                    _replace_text(self.audio_details, _json_text(payload))
                    self.audio_status.set(str(error))
                else:
                    messagebox.showerror("Music Mixer", str(error))
                return
            self.audio_progress["value"] = 100.0
            try:
                self.playback.load(result["output_path"])
                self.playback.set_gain(min(1.0, self.audio_gain.get()))
                self.playback.play()
                _replace_text(self.audio_details, _json_text(result))
                self.audio_status.set(f"Playing {mode} preview: {Path(result['output_path']).name}")
                self._refresh_simple_audio()
            except Exception as exc:
                messagebox.showerror("Playback", str(exc))

        self._local_worker(
            "music-system-v5-render",
            lambda: render_sequence(
                project,
                sequence["sequence_id"],
                program_resource_offset=resource_offset,
                routing_mode=mode,
                master_gain=self.audio_gain.get(),
            ),
            done,
        )

    def _audio_use_mapping(self) -> None:
        sequence = self._selected_sequence()
        candidate = self._selected_program()
        mode = self._selected_routing_mode()
        if sequence is None or candidate is None:
            messagebox.showinfo("Music Mixer", "Select a sequence and Program-resource candidate.")
            return
        _replace_text(
            self.audio_details,
            _json_text(
                {
                    "selection": {
                        "sequence_id": sequence["sequence_id"],
                        "routing_mode": mode,
                        "program_resource": candidate["resource_id"],
                    },
                    "note": "Selected for this audition only. SNDDATA is not modified; Program 0 and sample-ID remaps are not invented.",
                    "candidate_evidence": candidate,
                }
            ),
        )
        self.audio_status.set(f"Audition selection: {mode} / {candidate['resource_id']}")

    def _audio_research_job(self, label: str, status: str, work: Callable[[], Any], *, refresh_sequences: bool = False) -> None:
        self.audio_status.set(status)
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(result: Any, error: Exception | None) -> None:
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"{label} failed: {error}")
                _replace_text(self.audio_details, f"{type(error).__name__}: {error}")
                return
            self.audio_progress["value"] = 100.0
            self.audio_status.set(f"{label} complete")
            _replace_text(self.audio_details, _json_text(result))
            if refresh_sequences:
                self._refresh_audio_sequences()
            self._refresh_reports()
            self._refresh_simple_audio()

        self._local_worker(label.lower().replace(" ", "-"), work, done)

    def _rebuild_mixer_index_v5(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._audio_research_job(
            "Mixer Index v5",
            "Parsing FF0A tracks, Program tables, slots, sample coverage and routing hypotheses…",
            lambda: analyze_project_snddata(project),
            refresh_sequences=True,
        )

    def _run_audio_diagnostics(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._audio_research_job("Audio Diagnostics", "Comparing raw SCEI tags with retained parser sections…", lambda: write_audio_diagnostics(project))

    def _run_snddata_forensics(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._audio_research_job("Routing Forensics", "Testing Program Change, channel→Program and SCEISequ evidence…", lambda: analyze_snddata_forensics(project))

    def _run_audition_matrix(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._audio_research_job(
            "Audition Matrix",
            "Rendering bounded proof WAVs only for complete Program/slot/sample hypotheses…",
            lambda: render_audition_matrix(project),
        )

    def _run_morning_bundle(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self._audio_research_job(
            "Morning Bundle",
            "Running visual provenance, StudioCCS comparison, audio forensics and bounded auditions…",
            lambda: run_morning_diagnostics(project),
            refresh_sequences=True,
        )

    def _open_diagnostics_folder(self) -> None:
        project = self._require_project()
        if project is None:
            return
        path = project.workspace_path("diagnostics")
        path.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            self.audio_status.set(str(path))


def main() -> int:
    app = PublicFragmenterAppV9()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V42: normalized SNDDATA sample access and compact research controls."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from snddata_sample_bridge_v1 import install as install_sample_bridge

# Install before importing the GUI stack so v5 cataloging, forensic inventory, and
# renderer PCM loading all consume the same authoritative sample metadata.
install_sample_bridge()

from fragmenter_public_gui import _open_path  # noqa: E402
from fragmenter_public_gui_v41 import PublicFragmenterAppV41  # noqa: E402
from snddata_research_bundle_v1 import build_research_bundle  # noqa: E402


class PublicFragmenterAppV42(PublicFragmenterAppV41):
    """Keep the V41 safety layer while repairing sample discovery and mixer layout."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — SNDDATA Research + Normalized Playback")

    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        super()._build_research_mixer_v40(parent)
        workflow = None
        playback = None
        for child in parent.winfo_children():
            try:
                label = str(child.cget("text"))
            except tk.TclError:
                continue
            if label == "Research workflow":
                workflow = child
            elif label == "4. Audition and record the result":
                playback = child

        if workflow is not None:
            workflow.destroy()
        if playback is not None:
            self._rebuild_audition_controls_v42(playback)

    def _rebuild_audition_controls_v42(self, playback: ttk.LabelFrame) -> None:
        gain_value = float(self.audio_gain.get()) if self.audio_gain is not None else 0.8
        notes_value = self.audio_review_notes_v40.get() if self.audio_review_notes_v40 is not None else ""
        for child in playback.winfo_children():
            child.destroy()
        playback.columnconfigure(0, weight=1)

        audition = ttk.Frame(playback)
        audition.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            audition,
            text="Render & Play Candidate",
            command=lambda: self._render_selected_v40(play=True),
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            audition,
            text="Render WAV Only",
            command=lambda: self._render_selected_v40(play=False),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(audition, text="Play Last Preview", command=self._play_last_preview_v40).pack(side="left", padx=(6, 0))
        ttk.Button(audition, text="Stop", command=self._audio_stop).pack(side="left", padx=(6, 0))
        self.pause_button = ttk.Button(
            audition,
            text="Pause",
            command=self._audio_pause,
            state="normal" if self.playback.supports_pause else "disabled",
        )
        self.pause_button.pack(side="left", padx=(6, 0))
        self.resume_button = ttk.Button(
            audition,
            text="Resume",
            command=self._audio_resume,
            state="normal" if self.playback.supports_pause else "disabled",
        )
        self.resume_button.pack(side="left", padx=(6, 12))
        self.audio_gain = tk.DoubleVar(value=gain_value)
        ttk.Label(audition, text="Gain").pack(side="left")
        ttk.Scale(audition, from_=0.0, to=1.0, variable=self.audio_gain, length=150).pack(side="left", padx=(4, 0))

        review = ttk.Frame(playback)
        review.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        review.columnconfigure(1, weight=1)
        ttk.Label(review, text="Notes").grid(row=0, column=0, sticky="w")
        self.audio_review_notes_v40 = tk.StringVar(value=notes_value)
        ttk.Entry(review, textvariable=self.audio_review_notes_v40).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Button(review, text="Plausible", command=lambda: self._review_candidate_v40("plausible")).grid(row=0, column=2)
        ttk.Button(review, text="Confirm Mapping", command=lambda: self._review_candidate_v40("confirmed")).grid(row=0, column=3, padx=(5, 0))
        ttk.Button(review, text="Reject", command=lambda: self._review_candidate_v40("rejected")).grid(row=0, column=4, padx=(5, 0))
        ttk.Button(review, text="Clear Review", command=self._clear_candidate_review_v40).grid(row=0, column=5, padx=(5, 0))
        ttk.Button(review, text="Export Research Bundle", command=self._export_research_bundle_v42).grid(row=0, column=6, padx=(12, 0))

    def _export_research_bundle_v42(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None:
            return
        if sequence is None or candidate is None:
            messagebox.showinfo("SNDDATA research bundle", "Select a sequence and Program candidate first.")
            return
        try:
            result = build_research_bundle(
                project,
                sequence,
                candidate,
                playback_backend=self.playback.backend_name,
            )
            target = Path(str(result["bundle_path"]))
            self.audio_status.set(
                f"Research bundle written: {target.name} ({int(result.get('sample_inventory_rows') or 0)} normalized sample rows)"
            )
            messagebox.showinfo(
                "SNDDATA research bundle",
                "Diagnostic bundle created. It contains JSON evidence only—no game binaries or audio samples.\n\n"
                f"{target}",
            )
            _open_path(target.parent)
        except Exception as exc:
            messagebox.showerror("SNDDATA research bundle", str(exc))


def main() -> int:
    app = PublicFragmenterAppV42()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

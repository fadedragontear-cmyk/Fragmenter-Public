#!/usr/bin/env python3
"""V44: sample-name inference and an audible rough SNDDATA proof path."""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from snddata_sample_bridge_v1 import install as install_sample_bridge
from snddata_research_patch_v2 import install as install_research_patch

install_sample_bridge()
install_research_patch()

from fragmenter_public_gui import _json_text, _replace_text  # noqa: E402
from fragmenter_public_gui_v43 import PublicFragmenterAppV43  # noqa: E402
from snddata_music_system_v5 import MusicSystemError  # noqa: E402
from snddata_music_system_v7 import render_sequence_rough_proof  # noqa: E402


class PublicFragmenterAppV44(PublicFragmenterAppV43):
    """Add a deliberately non-authoritative route to audible proof-of-concept output."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — SNDDATA Rough Proof Auditions")

    def _rebuild_audition_controls_v42(self, playback: ttk.LabelFrame) -> None:
        super()._rebuild_audition_controls_v42(playback)
        frames = [child for child in playback.winfo_children() if isinstance(child, ttk.Frame)]
        if not frames:
            return
        audition = frames[0]
        play_last = next(
            (
                child
                for child in audition.winfo_children()
                if isinstance(child, ttk.Button) and str(child.cget("text")) == "Play Last Preview"
            ),
            None,
        )
        button = ttk.Button(
            audition,
            text="Render Rough Proof",
            command=self._render_rough_proof_v44,
            style="Accent.TButton",
        )
        options: dict[str, Any] = {"side": "left", "padx": (6, 0)}
        if play_last is not None:
            options["before"] = play_last
        button.pack(**options)

    def _render_rough_proof_v44(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None:
            return
        if sequence is None or candidate is None:
            messagebox.showinfo("SNDDATA rough proof", "Select a sequence and Program candidate first.")
            return
        missing_programs = [int(value) for value in candidate.get("missing_program_indexes") or []]
        if missing_programs:
            messagebox.showinfo(
                "Choose a candidate with complete Programs",
                "Rough proof rendering can substitute samples, but not missing Program records.\n\n"
                + ", ".join(f"Program {value}" for value in missing_programs),
            )
            return
        mode = str(candidate.get("routing_mode") or "")
        if mode not in {"program_change", "channel_as_program"}:
            messagebox.showinfo("SNDDATA rough proof", "Select an explicit public routing hypothesis first.")
            return

        self.audio_status.set(
            f"Building rough proof for {sequence['sequence_id']} with same-bank sample aliases…"
        )
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
                        _json_text(
                            {
                                "status": "rough_proof_failed",
                                "error": str(error),
                                "remaining_walls": error.missing,
                                "candidate": candidate,
                            }
                        ),
                    )
                    self.audio_status.set(str(error))
                else:
                    messagebox.showerror("SNDDATA rough proof", str(error))
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
                self.audio_status.set(f"Rough proof WAV rendered but playback failed: {exc}")
                return
            substitutions = int(
                ((result.get("metadata") or {}).get("rough_sample_substitution_count") or 0)
            )
            self.audio_status.set(
                f"Playing rough proof: {output.name}; {substitutions} experimental substitution(s). Cannot confirm mapping."
            )

        self._local_worker(
            "snddata-rough-proof-render-v44",
            lambda: render_sequence_rough_proof(
                project,
                sequence["sequence_id"],
                program_resource_offset=int(candidate["resource_offset"]),
                routing_mode=mode,
                master_gain=gain,
            ),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV44()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
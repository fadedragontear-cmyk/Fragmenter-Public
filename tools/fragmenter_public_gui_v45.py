#!/usr/bin/env python3
"""V45: sparse Program-index fix and independent sequence timing proof."""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from snddata_player_patch_v1 import install as install_player_patch
from snddata_sample_bridge_v1 import install as install_sample_bridge
from snddata_research_patch_v2 import install as install_research_patch

# Correct Program lookup before inherited mapped renderers are used.
install_player_patch()
install_sample_bridge()
install_research_patch()

from fragmenter_public_gui import _json_text, _replace_text  # noqa: E402
from fragmenter_public_gui_v44 import PublicFragmenterAppV44  # noqa: E402
from snddata_music_system_v5 import MusicSystemError  # noqa: E402
from snddata_music_system_v8 import render_sequence_timing_proof  # noqa: E402


class PublicFragmenterAppV45(PublicFragmenterAppV44):
    """Separate verified timing/PCM mechanics from unresolved Program-slot routing."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — SNDDATA Timing Proof")

    def _rebuild_audition_controls_v42(self, playback: ttk.LabelFrame) -> None:
        super()._rebuild_audition_controls_v42(playback)
        frames = [child for child in playback.winfo_children() if isinstance(child, ttk.Frame)]
        if not frames:
            return
        audition = frames[0]
        rough = next(
            (
                child
                for child in audition.winfo_children()
                if isinstance(child, ttk.Button) and str(child.cget("text")) == "Render Rough Proof"
            ),
            None,
        )
        button = ttk.Button(
            audition,
            text="Render Timing Proof",
            command=self._render_timing_proof_v45,
            style="Accent.TButton",
        )
        options: dict[str, Any] = {"side": "left", "padx": (6, 0)}
        if rough is not None:
            options["before"] = rough
        button.pack(**options)

    def _render_timing_proof_v45(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None:
            return
        if sequence is None:
            messagebox.showinfo("SNDDATA timing proof", "Select a sequence first. A Program candidate is optional.")
            return

        preferred_resource = None
        if candidate is not None and candidate.get("resource_offset") is not None:
            preferred_resource = int(candidate["resource_offset"])
        self.audio_status.set(
            f"Rendering timing proof for {sequence['sequence_id']} with one known-good decoded sample…"
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
                                "status": "timing_proof_failed",
                                "error": str(error),
                                "remaining_walls": error.missing,
                                "sequence": sequence,
                                "preferred_candidate": candidate,
                            }
                        ),
                    )
                    self.audio_status.set(str(error))
                else:
                    messagebox.showerror("SNDDATA timing proof", str(error))
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
                self.audio_status.set(f"Timing-proof WAV rendered but playback failed: {exc}")
                return
            note_count = int(((result.get("metadata") or {}).get("proof_note_events") or 0))
            self.audio_status.set(
                f"Playing timing proof: {output.name}; {note_count} decoded note time(s). Routing intentionally bypassed."
            )

        self._local_worker(
            "snddata-timing-proof-render-v45",
            lambda: render_sequence_timing_proof(
                project,
                sequence["sequence_id"],
                preferred_resource_offset=preferred_resource,
                master_gain=gain,
            ),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV45()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

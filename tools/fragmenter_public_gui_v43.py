#!/usr/bin/env python3
"""V43: honest renderable counts and explicit silent-gap research auditions."""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from snddata_sample_bridge_v1 import install as install_sample_bridge
from snddata_research_patch_v2 import install as install_research_patch

# Install model corrections before the inherited GUI imports workbench functions.
install_sample_bridge()
install_research_patch()

from fragmenter_public_gui import _json_text, _replace_text  # noqa: E402
from fragmenter_public_gui_v42 import PublicFragmenterAppV42  # noqa: E402
from snddata_music_system_v5 import MusicSystemError  # noqa: E402
from snddata_music_system_v6 import render_sequence_with_silent_placeholders  # noqa: E402


class PublicFragmenterAppV43(PublicFragmenterAppV42):
    """Expose failed-sample silence as an experiment, never as format authority."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — SNDDATA Silent-Gap Research")

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
            text="Render & Play w/ Silent Gaps",
            command=self._render_with_silent_placeholders_v43,
        )
        options: dict[str, Any] = {"side": "left", "padx": (6, 0)}
        if play_last is not None:
            options["before"] = play_last
        button.pack(**options)

    def _render_with_silent_placeholders_v43(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence_v40()
        candidate = self._selected_candidate_v40()
        if project is None:
            return
        if sequence is None or candidate is None:
            messagebox.showinfo("SNDDATA silent-gap audition", "Select a sequence and Program candidate first.")
            return
        missing_programs = [int(value) for value in candidate.get("missing_program_indexes") or []]
        if missing_programs:
            messagebox.showinfo(
                "Silent gaps cannot repair this candidate",
                "This candidate is missing Program records, not only decoded samples.\n\n"
                + ", ".join(f"Program {value}" for value in missing_programs),
            )
            return
        mode = str(candidate.get("routing_mode") or "")
        if mode not in {"program_change", "channel_as_program"}:
            messagebox.showinfo("SNDDATA silent-gap audition", "Select an explicit public routing hypothesis first.")
            return

        self.audio_status.set(
            f"Experimentally rendering {sequence['sequence_id']} with silent placeholders for failed sample entries…"
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
                                "status": "silent_gap_render_failed",
                                "error": str(error),
                                "missing_or_diagnostic": error.missing,
                                "candidate": candidate,
                            }
                        ),
                    )
                    self.audio_status.set(str(error))
                else:
                    messagebox.showerror("SNDDATA silent-gap render", str(error))
                return

            self.audio_progress["value"] = 100.0
            output = Path(str(result["output_path"]))
            self.audio_last_preview_v40 = output
            try:
                self.playback.load(output)
                self.playback.set_gain(gain)
                self.playback.play()
            except Exception as exc:
                _replace_text(self.audio_details, _json_text(result))
                self.audio_status.set(f"Experimental WAV rendered but playback failed: {exc}")
                return
            _replace_text(self.audio_details, _json_text(result))
            count = int(((result.get("metadata") or {}).get("synthetic_silence_count") or 0))
            self.audio_status.set(
                f"Playing experimental silent-gap preview: {output.name}; {count} placeholder sample(s). Not confirmable evidence."
            )

        self._local_worker(
            "snddata-silent-gap-render-v43",
            lambda: render_sequence_with_silent_placeholders(
                project,
                sequence["sequence_id"],
                program_resource_offset=int(candidate["resource_offset"]),
                routing_mode=mode,
                master_gain=gain,
            ),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV43()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

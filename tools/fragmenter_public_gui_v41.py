#!/usr/bin/env python3
"""V41: final safety and persistence polish for the SNDDATA research mixer."""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from fragmenter_public_gui_v40 import PublicFragmenterAppV40
from snddata_research_workbench_v1 import readiness


class PublicFragmenterAppV41(PublicFragmenterAppV40):
    """Restore reviewed previews and prevent false confirmed mappings."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — SNDDATA Research + Playback")

    def _refresh_audio_readiness_v40(self) -> None:
        if self.audio_readiness_v40 is None or self.project is None:
            return
        try:
            state = readiness(self.project)
            missing = []
            if not state["snddata_exists"]:
                missing.append("SNDDATA source")
            if not state["sample_report_exists"]:
                missing.append("sample library")
            if not state["catalog_exists"]:
                missing.append("mixer index")
            backend = self.playback.backend_name
            if missing:
                self.audio_readiness_v40.set(
                    "Not ready: " + ", ".join(missing) + ". Run the Audio Pipeline or the missing individual stage."
                )
            elif backend == "unavailable":
                self.audio_readiness_v40.set(
                    "Renderer ready, but local WAV playback is unavailable. Render WAV Only still works; install pygame or simpleaudio for in-app playback."
                )
            else:
                self.audio_readiness_v40.set(f"Ready for evidence-backed auditions. WAV playback backend: {backend}.")
        except Exception as exc:
            self.audio_readiness_v40.set(f"Readiness check failed: {exc}")

    def _candidate_selected_v40(self) -> None:
        super()._candidate_selected_v40()
        candidate = self._selected_candidate_v40()
        review = (candidate or {}).get("review") or {}
        preview_text = str(review.get("preview_path") or "").strip()
        if preview_text:
            preview = Path(preview_text).expanduser()
            if preview.is_file():
                self.audio_last_preview_v40 = preview

    def _review_candidate_v40(self, status: str) -> None:
        candidate = self._selected_candidate_v40()
        if status == "confirmed" and candidate is not None and candidate.get("status") != "renderable":
            missing = candidate.get("missing_summary") or candidate.get("status_detail") or candidate.get("status")
            messagebox.showinfo(
                "Cannot confirm this mapping",
                "A confirmed mapping must first produce a renderer-complete preview.\n\n"
                f"Current wall: {missing}\n\nUse Plausible to retain the hypothesis without asserting that reconstruction is complete.",
            )
            return
        super()._review_candidate_v40(status)


def main() -> int:
    app = PublicFragmenterAppV41()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

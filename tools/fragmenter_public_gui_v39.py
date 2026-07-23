#!/usr/bin/env python3
"""V39: finalize canonical pipeline task lifecycle over the V38 workspace."""
from __future__ import annotations

from typing import Any

import fragmenter_public_gui_v38 as gui_v38
from fragmenter_public_gui_v38 import PublicFragmenterAppV38
from project_report_layout_v1 import migrate_report_layout

# First-scan-only flavor remains static and project-specific. No chatbot or
# autonomous behavior is introduced here.
gui_v38.CELDRA_WAIT_LINES = (
    *gui_v38.CELDRA_WAIT_LINES,
    "The World has accepted the scan request. Whether it intends to explain the file names is another matter.",
    "I am an AI inspecting a fictional MMO inside a PlayStation 2 game. This seems appropriately recursive.",
    "No Data Drain detected. I am still keeping one process between me and the suspicious assets.",
    "The assets are forming a party. Their classes appear to be Texture, Clump, and Unknown.",
)


class PublicFragmenterAppV39(PublicFragmenterAppV38):
    """Apply report migration on load and release busy state after focused jobs."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Canonical Pipeline + Audio Mixer")

    def _project_loaded(self) -> None:
        assert self.project is not None
        try:
            migrate_report_layout(self.project)
        except Exception as exc:
            self._append_log(f"Report-layout migration warning: {exc}")
        super()._project_loaded()

    def _pipeline_stage_done_v38(self, stage_key: str, result: Any, error: Exception | None) -> None:
        try:
            super()._pipeline_stage_done_v38(stage_key, result, error)
        finally:
            self._set_busy(False)

    def _audio_pipeline_done_v38(self, result: Any, error: Exception | None) -> None:
        try:
            super()._audio_pipeline_done_v38(result, error)
        finally:
            self._set_busy(False)


def main() -> int:
    app = PublicFragmenterAppV39()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

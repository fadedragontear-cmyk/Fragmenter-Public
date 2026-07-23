#!/usr/bin/env python3
"""V57: make the initial deployment bar a complete independent 0-to-100 job."""
from __future__ import annotations

from celdra_startup_timeline_v3 import CCSF_HATCH_DELAY_MS, DEPLOY_MIN_MS, DEPLOY_STATUS
from fragmenter_public_gui_v56 import PublicFragmenterAppV56


class PublicFragmenterAppV57(PublicFragmenterAppV56):
    """Keep every Celdra presentation status on the same staged loading model."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Staged Evolution Presentation")

    def _prepare_first_run_surface_v51(self) -> None:
        super()._prepare_first_run_surface_v51()
        self._set_status_segment_v51(DEPLOY_STATUS, 0, 100, DEPLOY_MIN_MS)

    def _start_timeline_test_v51(self, speed: float) -> None:
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._cancel_progress_animation_v51()
        self._celdra_session_active_v49 = True
        self._celdra_first_scan_v51 = True
        self._celdra_first_scan_v49 = False
        self._celdra_timeline_started_v51 = False
        self._celdra_timeline_breakpoint_v51 = False
        self._prepare_first_run_surface_v51()
        scale = max(0.01, float(speed))
        scaled_gate = max(1, round(CCSF_HATCH_DELAY_MS * scale))
        self._set_status_segment_v51(
            DEPLOY_STATUS,
            0,
            100,
            max(1, round(DEPLOY_MIN_MS * scale)),
        )
        self._remember_after_v49(
            scaled_gate,
            lambda: self._begin_first_run_timeline_v51(speed),
        )


def main() -> int:
    app = PublicFragmenterAppV57()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

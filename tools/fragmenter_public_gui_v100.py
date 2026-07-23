#!/usr/bin/env python3
"""V100: tokenized dragongirl transitions and fully paced Gremlin introductions."""
from __future__ import annotations

import tkinter as tk
from typing import Any

from celdra_v99_content import GREMLIN_PERSONALITIES
from fragmenter_public_gui_v99 import PublicFragmenterAppV99


class PublicFragmenterAppV100(PublicFragmenterAppV99):
    """Prevent stale portrait flashes and give every Gremlin a readable entrance."""

    def __init__(self) -> None:
        self._celdra_pose_transition_after_v100: str | None = None
        self._celdra_pose_transition_token_v100 = 0
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Stable Intro + Gremlin Theatre V100")

    # ------------------------------------------------------------------
    # Short blank handoff between post-intro poses. A newer request invalidates
    # an older callback, preventing delayed PNGs or bubbles from flashing in a
    # position that belongs to the next scene.
    # ------------------------------------------------------------------
    def _runtime_pose_v70(self, pose: str, text: str) -> None:
        if not bool(getattr(self, "_celdra_takeover_active_v58", False)):
            super()._runtime_pose_v70(pose, text)
            return
        self._celdra_pose_transition_token_v100 += 1
        token = self._celdra_pose_transition_token_v100
        if self._celdra_pose_transition_after_v100 is not None:
            try:
                self.after_cancel(self._celdra_pose_transition_after_v100)
            except tk.TclError:
                pass
            self._celdra_pose_transition_after_v100 = None
        self._hide_speech_bubble_v58()
        self.celdra_current_external_v50 = None
        self.celdra_current_pixel_v50 = None
        self.after_idle(self._redraw_celdra_avatar_v50)

        def apply() -> None:
            self._celdra_pose_transition_after_v100 = None
            if token != self._celdra_pose_transition_token_v100:
                return
            if not bool(getattr(self, "_celdra_takeover_active_v58", False)):
                return
            super(PublicFragmenterAppV100, self)._runtime_pose_v70(pose, text)

        self._celdra_pose_transition_after_v100 = self.after(
            self._scaled_runtime_ms_v88(180),
            apply,
        )

    def _cancel_pose_transition_v100(self) -> None:
        self._celdra_pose_transition_token_v100 += 1
        if self._celdra_pose_transition_after_v100 is not None:
            try:
                self.after_cancel(self._celdra_pose_transition_after_v100)
            except tk.TclError:
                pass
            self._celdra_pose_transition_after_v100 = None

    # ------------------------------------------------------------------
    # The nine introductions now receive 7.2 seconds each. Riot motion begins
    # only after the complete roster has been presented.
    # ------------------------------------------------------------------
    def _start_gremlin_show_v94(self) -> None:
        if self._celdra_gremlin_active_v94 or not self._celdra_intro_gate_open_v99:
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._celdra_single_visit_v99 = False
        self._celdra_gremlin_active_v94 = True
        self._celdra_gremlin_token_v94 += 1
        self._celdra_gremlin_reported_stages_v94.clear()
        self._runtime_pose_v70(
            "wink",
            "Wanna see a trick? I restored the retired hatchling design, gave each copy a palette and a personality, and made the mistake of telling them this was a workplace.",
        )
        self._schedule_gremlin_v94(3_000, self._spawn_gremlin_swarm_v95)
        self._schedule_gremlin_v94(8_000, self._introduce_gremlin_personalities_v96)
        self._schedule_gremlin_v94(76_000, self._scatter_gremlin_swarm_v95)
        self._schedule_gremlin_v94(86_000, self._push_console_with_swarm_v95)
        self._schedule_gremlin_v94(96_000, self._start_gremlin_havoc_v95)
        self._schedule_gremlin_v94(108_000, self._start_gremlin_ui_chaos_v99)
        self._schedule_gremlin_v94(121_000, self._tour_ui_with_swarm_v95)
        self._schedule_gremlin_v94(134_000, self._start_console_hump_v99)
        self._schedule_gremlin_v94(147_000, self._form_gremlin_parties_v95)
        self._schedule_gremlin_v94(161_000, self._gremlins_annoy_celdra_v96)
        self._schedule_gremlin_v94(174_000, self._celdra_gremlin_rage_v96)
        self._schedule_gremlin_v94(189_000, self._banish_gremlins_v96)
        self._schedule_gremlin_v94(206_000, self._finish_gremlin_banishment_v96)

    def _introduce_gremlin_personalities_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._append_console_v49(
            "[CORE] PERSONALITY ROSTER BEGIN // NINE LEGACY HATCHLINGS // WRITE PERMISSIONS 0"
        )
        poses = (
            "smile",
            "confused",
            "wink",
            "love",
            "suspicious",
            "unenthused",
            "excited",
            "confused",
            "shocked",
        )
        for index, personality in enumerate(GREMLIN_PERSONALITIES):
            self._schedule_gremlin_v94(
                index * 7_200,
                lambda selected=dict(personality), selected_pose=poses[index]: self._introduce_one_gremlin_v99(
                    selected,
                    selected_pose,
                ),
            )

    def _prepare_first_run_surface_v51(self) -> None:
        self._cancel_pose_transition_v100()
        super()._prepare_first_run_surface_v51()

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_pose_transition_v100()
        super()._cancel_celdra_cues_v49()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V100"
            metadata["tokenized_pose_transition_ms"] = 180
            metadata["gremlin_introduction_hold_ms"] = 7_200
            metadata["gremlin_full_show_ms"] = 206_000
        return payload


def main() -> int:
    app = PublicFragmenterAppV100()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

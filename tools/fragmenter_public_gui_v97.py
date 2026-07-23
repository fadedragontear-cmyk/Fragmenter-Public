#!/usr/bin/env python3
"""V97: finalize the live CCSF crossing and personality-specific Gremlin riot."""
from __future__ import annotations

import time
import tkinter as tk
from typing import Any

from celdra_v96_content import GREMLIN_HAVOC_STAGES, GREMLIN_PERSONALITIES
from fragmenter_public_gui_v96 import PublicFragmenterAppV96


class PublicFragmenterAppV97(PublicFragmenterAppV96):
    """Trigger the CCSF scene on the real progress crossing and finish Gremlin identities."""

    def __init__(self) -> None:
        self._celdra_banish_reset_until_v97 = 0.0
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Live Scan Theatre V97")

    # The final container progress JSON can set CCSF to 100% before the executor
    # emits its finish event.  Observe the real overall-bar crossing here.
    def _handle_run_event(self, event: dict[str, Any]) -> None:
        before = self._overall_progress_value_v96(getattr(self, "overall_progress", {}))
        super()._handle_run_event(event)
        after = self._overall_progress_value_v96(getattr(self, "overall_progress", {}))
        if (
            str(event.get("stage") or "") == "ccsf_extract"
            and str(event.get("kind") or "") == "output"
            and not self._celdra_ccsf_jump_reacted_v96
            and before < 26.5 <= after
        ):
            self._react_to_ccsf_gate_v96(before=before, after=after, reused=False)

    def _react_to_ccsf_gate_v96(self, *, before: float, after: float, reused: bool) -> None:
        if self._celdra_ccsf_jump_reacted_v96:
            return
        self._celdra_ccsf_jump_reacted_v96 = True
        mode = "REUSED VERIFIED OUTPUT" if reused else "EXTRACTION COMPLETE"
        actual_after = max(before, after)
        self._append_console_v49(
            f"[CORE] CCSF GATE {mode} // OVERALL RUN ALL LOW-TWENTIES -> {actual_after:.0f}%"
        )
        self._append_console_v49(
            f"[CORE] CCSF FINAL COUNTERS // {self._ccsf_metric_text_v96()}"
        )
        scenes = [
            (
                "excited",
                "There it is—the long CCSF gate just moved the whole run from about twenty-one percent to twenty-seven. "
                + self._ccsf_metric_text_v96()
                + ".",
                10_500,
            ),
            (
                "smile",
                "That jump means we crossed from scanning containers into verifying a real extracted library. The remaining stages can work from evidence instead of the raw disc.",
                10_500,
            ),
            (
                "suspicious",
                "Next comes asset verification and extraction audit. A folder full of files is encouraging; provenance and coverage are what make it trustworthy.",
                9_500,
            ),
        ]
        self._celdra_live_scene_queue_v96[0:0] = scenes
        if self._celdra_live_scene_after_v96 is None:
            self._play_next_live_scene_v96()

    # Each restored hatchling announces its own harmless objective through CORE.
    def _introduce_gremlin_personalities_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._append_console_v49(
            "[CORE] GREMLIN ROSTER ONLINE // 9 LEGACY HATCHLINGS // WRITE PERMISSIONS: 0"
        )
        for index, personality in enumerate(GREMLIN_PERSONALITIES):
            name = str(personality.get("name") or f"G{index + 1}")
            role = str(personality.get("role") or "unassigned nuisance").upper()
            claim = str(personality.get("claim") or "IDLE").upper()
            self._schedule_gremlin_v94(
                500 + index * 720,
                lambda selected_name=name, selected_role=role, selected_claim=claim: self._append_console_v49(
                    f"[CORE] GREMLIN {selected_name} // {selected_role} // {selected_claim}"
                ),
            )
        self._schedule_gremlin_v94(
            7_300,
            lambda: self._append_console_v49(
                "[BRAIN] YOU GAVE EVERY BUG A JOB TITLE. THIS IS HOW DEPARTMENTS HAPPEN."
            ),
        )
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(
                "BYTE HEX CACHE LOOP PING PATCH ROOT NULL GLITCH // ALL UNSUPERVISED"
            )

    # Use the V96 personality meter instead of the inherited V95 anonymous one.
    def _start_gremlin_havoc_v95(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        started = time.monotonic()
        scaled = max(1, self._scaled_runtime_ms_v88(18_000))
        token = self._celdra_gremlin_token_v94

        for item in self._celdra_gremlin_swarm_v95:
            personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
            temperament = str(personality.get("temperament") or "idle")
            item["sequence"] = self._personality_sequence_v96(temperament)

        def tick() -> None:
            self._celdra_gremlin_havoc_after_v94 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            progress = min(100, round((time.monotonic() - started) * 1000.0 / scaled * 100))
            if self._celdra_gremlin_status_progress_v95 is not None:
                try:
                    self._celdra_gremlin_status_progress_v95["value"] = progress
                except tk.TclError:
                    pass
            threshold_value = 0
            label = GREMLIN_HAVOC_STAGES[0][1]
            for threshold, candidate in GREMLIN_HAVOC_STAGES:
                if progress >= threshold:
                    threshold_value = threshold
                    label = candidate
            if self._celdra_gremlin_status_label_v95 is not None:
                self._celdra_gremlin_status_label_v95.set(label)
            if threshold_value not in self._celdra_gremlin_reported_stages_v94:
                self._celdra_gremlin_reported_stages_v94.add(threshold_value)
                if threshold_value in {17, 35, 53, 71, 88, 94, 100}:
                    self._append_console_v49(f"[CORE] GREMLIN RIOT // {label}")
                if threshold_value == 44:
                    self._append_console_v49(
                        "[BRAIN] PING IS HITTING THE PROGRESS BAR. THAT DOES NOT MAKE IT FASTER."
                    )
                elif threshold_value == 53:
                    self._append_console_v49(
                        "[BRAIN] PATCH HAS REACHED THE HORN. REPEAT: PATCH HAS REACHED THE HORN."
                    )
                elif threshold_value == 71:
                    self._append_console_v49(
                        "[BRAIN] NULL CANNOT BE MISSING WHILE I AM LOOKING DIRECTLY AT IT."
                    )
                elif threshold_value == 94:
                    self._append_console_v49(
                        "[BRAIN] TEMPER EVENT CONFIRMED. EVERYONE OFF THE DRAGON."
                    )
            if progress < 100:
                self._celdra_gremlin_havoc_after_v94 = self.after(55, tick)

        tick()

    def _gremlins_annoy_celdra_v96(self) -> None:
        super()._gremlins_annoy_celdra_v96()
        if not self._celdra_gremlin_active_v94:
            return
        self._schedule_gremlin_v94(
            1_000,
            lambda: self._append_console_v49(
                "[CORE] PATCH CONTACT: CELDRA LEFT HORN // PATCH AUTHORITY: SELF-ISSUED"
            ),
        )
        self._schedule_gremlin_v94(
            2_000,
            lambda: self._append_console_v49(
                "[CORE] CACHE HAS STORED 14 BRAIN COMPLAINTS AND LABELED THEM TRAINING DATA"
            ),
        )
        self._schedule_gremlin_v94(
            3_000,
            lambda: self._append_console_v49(
                "[CORE] LOOP COMPLETED UI TOUR 4 TIMES // DESTINATION REMAINS UNCHANGED"
            ),
        )
        self._schedule_gremlin_v94(
            4_000,
            lambda: self._append_console_v49(
                "[CORE] ROOT REQUESTED PARTY LEAD // REQUEST DENIED BY EVERYONE EXCEPT ROOT"
            ),
        )

    def _celdra_gremlin_rage_v96(self) -> None:
        super()._celdra_gremlin_rage_v96()
        if not self._celdra_gremlin_active_v94:
            return
        self._append_console_v49(
            "[CORE] RED AMBIENT FIELD SOURCES: CELDRA DIALOGUE / GREMLIN NAMES / BANISHMENT COMMANDS"
        )
        self._append_console_v49(
            "[BRAIN] SHE TURNED THE BACKGROUND RED. THIS IS THE PART WHERE TINY THINGS LEARN CONSEQUENCES."
        )

    # Fixed timed pose changes must not repaint the viewport while the Gremlin
    # riot, Angry state, or short Neutral reset hold owns the presentation.
    def _runtime_filler_pose_v87(self, pose: str, text: str) -> None:
        if bool(getattr(self, "_celdra_gremlin_active_v94", False)):
            return
        if bool(getattr(self, "_celdra_ambient_rage_v96", False)):
            return
        if time.monotonic() < self._celdra_banish_reset_until_v97:
            return
        super()._runtime_filler_pose_v87(pose, text)

    def _finish_gremlin_banishment_v96(self) -> None:
        self._celdra_banish_reset_until_v97 = time.monotonic() + (
            self._scaled_runtime_ms_v88(15_000) / 1000.0
        )
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(
                "BANISHMENT EXECUTING // BYTE HEX CACHE LOOP PING PATCH ROOT NULL GLITCH"
            )
        super()._finish_gremlin_banishment_v96()

    def _prepare_first_run_surface_v51(self) -> None:
        self._celdra_banish_reset_until_v97 = 0.0
        super()._prepare_first_run_surface_v51()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V97"
            metadata["ccsf_crossing_trigger"] = "actual_overall_progress_crosses_26_5"
            metadata["gremlin_personality_havoc_meter"] = True
            metadata["gremlin_scene_owns_timed_pose_channel"] = True
        return payload


def main() -> int:
    app = PublicFragmenterAppV97()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

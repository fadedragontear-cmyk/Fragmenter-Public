#!/usr/bin/env python3
"""Resume the V109 Gremlin collection during returning RUN ALL sessions."""
from __future__ import annotations

import tkinter as tk

from celdra_gremlin_memory_v2 import collection_complete


class FragmenterCollectionResumeMixinV109:
    def __init__(self) -> None:
        self._collection_resume_after_v109: str | None = None
        super().__init__()

    def _start_celdra_session_v49(self, first_scan: bool) -> None:
        super()._start_celdra_session_v49(first_scan)
        if first_scan or not bool(self._celdra_gremlin_memory_v99.get("breakout_seen")):
            return
        self._celdra_intro_gate_open_v99 = True
        self._gremlin_stage_enabled_v106 = True
        self._gremlin_intro_started_v106 = True
        self._gremlin_dismissed_v108 = False
        if self._collection_resume_after_v109 is not None:
            try:
                self.after_cancel(self._collection_resume_after_v109)
            except tk.TclError:
                pass
        self._collection_resume_after_v109 = self.after(
            self._scaled_runtime_ms_v88(4_000),
            self._resume_collection_v109,
        )

    def _resume_collection_v109(self) -> None:
        self._collection_resume_after_v109 = None
        if not bool(getattr(self, "_celdra_session_active_v49", False)):
            return
        if not bool(self._celdra_gremlin_memory_v99.get("breakout_seen")):
            return
        self._gremlin_main_scene_complete_v109 = True
        if self._stable_names_v101():
            self._install_gremlin_stable_v101()
        if collection_complete(self._celdra_gremlin_memory_v99):
            self._sync_celdra_tab_v109()
            return
        self._runtime_pose_v70(
            "smile",
            "Collection session resumed. The stable remembers who is contained, and the remaining Gremlins are still loose enough to make this interesting.",
        )
        self._append_console_v49(
            f"[CORE] GREMLIN COLLECTION RESUMED // {len(self._stable_names_v101())}/9 CONTAINED"
        )
        self._schedule_random_event_v99(initial=True)

    def _cancel_celdra_cues_v49(self) -> None:
        if self._collection_resume_after_v109 is not None:
            try:
                self.after_cancel(self._collection_resume_after_v109)
            except tk.TclError:
                pass
            self._collection_resume_after_v109 = None
        super()._cancel_celdra_cues_v49()

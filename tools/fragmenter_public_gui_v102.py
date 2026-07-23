#!/usr/bin/env python3
"""V102: seal V101 scene ownership and preserve V2 stable memory."""
from __future__ import annotations

import tkinter as tk
from typing import Any

from celdra_gremlin_memory_v2 import save_memory
from fragmenter_public_gui_v101 import PublicFragmenterAppV101


class PublicFragmenterAppV102(PublicFragmenterAppV101):
    """Prevent inherited filler/random callbacks from interrupting directed scenes."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Gremlin Stable Director's Cut V102")

    def _runtime_filler_pose_v87(self, pose: str, text: str) -> None:
        if self._celdra_internal_show_v101 or self._celdra_collection_reward_active_v101:
            return
        super()._runtime_filler_pose_v87(pose, text)

    def _play_next_live_scene_v96(self) -> None:
        if self._celdra_collection_reward_active_v101:
            self._celdra_live_scene_after_v96 = self.after(
                self._scaled_runtime_ms_v88(3_000),
                self._play_next_live_scene_v96,
            )
            return
        super()._play_next_live_scene_v96()

    def _run_random_event_v99(self) -> None:
        if self._celdra_collection_reward_active_v101:
            self._celdra_random_event_after_v99 = None
            self._schedule_random_event_v99()
            return
        super()._run_random_event_v99()

    def _finish_history_gag_v99(self) -> None:
        self._cancel_history_gag_v99()
        self._runtime_pose_v70(
            "unenthused",
            "Ehh. I've seen worse. I've seen better, but I've seen worse. For legal and technical clarity, I saw absolutely nothing because this was a fake progress bar.",
        )
        self._append_console_v49("[CORE] RESULT GENERATED WITHOUT READING BROWSER DATA")
        self._celdra_gremlin_memory_v99["history_gag_seen"] = True
        save_memory(self._celdra_gremlin_memory_v99)

    def _finish_collection_reward_v101(self) -> None:
        super()._finish_collection_reward_v101()
        if self._celdra_live_scene_queue_v96 and self._celdra_live_scene_after_v96 is None:
            self._play_next_live_scene_v96()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V102"
            metadata["directed_scene_exclusivity"] = [
                "main_gremlin_roster",
                "chaos_management",
                "angry_hard_stop",
                "full_collection_reward",
            ]
            metadata["stable_memory_schema"] = 2
        return payload


def main() -> int:
    app = PublicFragmenterAppV102()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

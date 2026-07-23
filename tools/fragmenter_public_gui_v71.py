#!/usr/bin/env python3
"""V71: guarantee persistent dragongirl poses own a visible viewport."""
from __future__ import annotations

from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v70 import PublicFragmenterAppV70


class PublicFragmenterAppV71(PublicFragmenterAppV70):
    """Open the avatar surface and keep completed runs locked to Cool."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Persistent Runtime")

    def _runtime_pose_v70(self, pose: str, text: str) -> None:
        if (
            self._celdra_pipeline_success_v70
            and self._celdra_placeholder_started_v70
            and str(pose or "").casefold() != "cool"
        ):
            pose = "cool"
            text = "RUN ALL complete. Everything that survived is officially part of the plan."

        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._celdra_external_offset_y_v58 = 0
        self._slide_chat_v54(show=False, duration_ms=320)
        if not self._load_takeover_reaction_v58(pose):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.56, 650)
        self.after_idle(self._redraw_celdra_avatar_v50)
        self._show_speech_bubble_v58(text)


def main() -> int:
    app = PublicFragmenterAppV71()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

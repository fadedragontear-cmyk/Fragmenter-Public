#!/usr/bin/env python3
"""V55: preserve a user-selected stage/console ratio during Celdra animations."""
from __future__ import annotations

import tkinter as tk

from fragmenter_public_gui_v54 import PublicFragmenterAppV54


class PublicFragmenterAppV55(PublicFragmenterAppV54):
    """Let manual divider placement override default evolution-stage widths."""

    def __init__(self) -> None:
        self._celdra_stage_user_fraction_v55: float | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Sliding Evolution Stage")

    def _capture_stage_fraction_v54(self, event: tk.Event | None = None) -> None:
        if self._celdra_stage_animating_v54:
            return
        super()._capture_stage_fraction_v54(event)
        pane = self.celdra_visual_split_v50
        if pane is None:
            return
        try:
            total = max(1, pane.winfo_width())
            fraction = pane.sashpos(0) / total
        except (AttributeError, tk.TclError):
            return
        if fraction >= 0.12:
            self._celdra_stage_user_fraction_v55 = max(0.30, min(0.74, fraction))

    def _animate_stage_fraction_v54(self, fraction: float, duration_ms: int = 900) -> None:
        selected = float(fraction)
        if (
            self._celdra_stage_user_fraction_v55 is not None
            and selected > self._celdra_stage_closed_fraction_v54 + 0.05
        ):
            selected = self._celdra_stage_user_fraction_v55
        super()._animate_stage_fraction_v54(selected, duration_ms)

    def _reset_celdra_layout_v50(self) -> None:
        self._celdra_stage_user_fraction_v55 = None
        super()._reset_celdra_layout_v50()
        self.after_idle(
            lambda: self._set_stage_fraction_v54(
                self._celdra_stage_closed_fraction_v54
                if not (
                    self._celdra_stage_avatar_visible_v54
                    or self._celdra_stage_dialogue_visible_v54
                )
                else self._celdra_stage_open_fraction_v54
            )
        )


def main() -> int:
    app = PublicFragmenterAppV55()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

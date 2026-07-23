#!/usr/bin/env python3
"""V59: cleanup safeguards for Celdra's interactive first-run branch."""
from __future__ import annotations

import tkinter as tk

from fragmenter_public_gui_v58 import PublicFragmenterAppV58


class PublicFragmenterAppV59(PublicFragmenterAppV58):
    """Prevent delayed prompt/takeover callbacks after resets or failures."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Interactive System Integration")

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_name_timer_v58()
        super()._cancel_celdra_cues_v49()

    def _show_timeline_failure_v51(self) -> None:
        self._cancel_name_timer_v58()
        self._hide_name_input_v58()
        self._takeover_restore_v58()
        super()._show_timeline_failure_v51()
        self.after_idle(self._scroll_all_text_v58)

    def _takeover_restore_v58(self) -> None:
        if self._celdra_creep_after_v58 is not None:
            try:
                self.after_cancel(self._celdra_creep_after_v58)
            except tk.TclError:
                pass
            self._celdra_creep_after_v58 = None
        super()._takeover_restore_v58()


def main() -> int:
    app = PublicFragmenterAppV59()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V65: reserve a clear speech-bubble column beside compact dragongirl portraits."""
from __future__ import annotations

import tkinter as tk

from fragmenter_public_gui_v64 import PublicFragmenterAppV64


class PublicFragmenterAppV65(PublicFragmenterAppV64):
    """Shift takeover portraits right so the bubble never covers Celdra's face."""

    def __init__(self) -> None:
        self._celdra_external_offset_x_v65 = 0
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Textual Corruption Presentation")

    def _start_avatar_takeover_v58(self) -> None:
        self._celdra_external_offset_x_v65 = 0
        super()._start_avatar_takeover_v58()

    def _begin_shy_reveal_v64(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        width = canvas.winfo_width() if canvas is not None else 520
        self._celdra_external_offset_x_v65 = max(42, min(92, width // 8))
        super()._begin_shy_reveal_v64()

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        external = self.celdra_current_external_v50
        if (
            canvas is not None
            and external is not None
            and self._celdra_takeover_active_v58
            and not self._celdra_energy_active_v63
        ):
            canvas.delete("all")
            canvas.create_image(
                max(1, canvas.winfo_width()) // 2 + self._celdra_external_offset_x_v65,
                max(1, canvas.winfo_height()) // 2
                + 12
                + self._celdra_external_offset_y_v58,
                image=external,
                anchor="center",
            )
            return
        super()._redraw_celdra_avatar_v50()

    def _takeover_restore_v58(self) -> None:
        self._celdra_external_offset_x_v65 = 0
        super()._takeover_restore_v58()


def main() -> int:
    app = PublicFragmenterAppV65()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

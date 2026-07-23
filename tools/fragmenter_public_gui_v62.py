#!/usr/bin/env python3
"""V62: keep the blue-smoke hatch inside accelerated timeline boundaries."""
from __future__ import annotations

from fragmenter_public_gui_v61 import PublicFragmenterAppV61


class PublicFragmenterAppV62(PublicFragmenterAppV61):
    """Scale smoke frame timing with the active presentation speed."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Static-Smoke Integration")

    def _tick_blue_smoke_v61(self) -> None:
        self._celdra_smoke_after_v61 = None
        if not self._celdra_smoke_active_v61:
            return
        self._redraw_celdra_avatar_v50()
        self._celdra_smoke_step_v61 += 1
        if self._celdra_smoke_step_v61 >= 20:
            self._celdra_smoke_active_v61 = False
            self.celdra_current_pixel_v50 = None
            self._redraw_celdra_avatar_v50()
            self._hide_avatar_v51()
            return
        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        interval = max(12, round(90 * speed))
        self._celdra_smoke_after_v61 = self.after(interval, self._tick_blue_smoke_v61)

    def _test_production_smoke_v61(self) -> None:
        self._celdra_timeline_speed_v51 = 1.0
        super()._test_production_smoke_v61()


def main() -> int:
    app = PublicFragmenterAppV62()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

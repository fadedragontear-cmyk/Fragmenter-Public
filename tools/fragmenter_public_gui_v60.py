#!/usr/bin/env python3
"""V60: concept-approved hatchling, staged viewport pressure, and cleaner test lab."""
from __future__ import annotations

import tkinter as tk

from celdra_v60_runtime_mixin import CeldraV60RuntimeMixin
from celdra_v60_test_lab_mixin import CeldraV60TestLabMixin
from fragmenter_public_gui_v59 import PublicFragmenterAppV59


class PublicFragmenterAppV60(
    CeldraV60TestLabMixin,
    CeldraV60RuntimeMixin,
    PublicFragmenterAppV59,
):
    """Use the approved baby-dragon concept throughout Celdra's first-run show."""

    BASE_STATUS_MARKERS = (
        "checking user for base",
        "gathering the user's base",
        "obtaining user's base",
        "checking for additional base",
    )

    def __init__(self) -> None:
        self._celdra_test_divider_v60: tk.Frame | None = None
        self._celdra_test_top_height_v60 = 260
        self._celdra_preview_choice_v60: tk.StringVar | None = None
        self._celdra_preview_map_v60: dict[str, str] = {}
        self._celdra_squished_active_v60 = False
        self._celdra_base_failed_pending_v60 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Approved Hatchling Presentation")


def main() -> int:
    app = PublicFragmenterAppV60()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

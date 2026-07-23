#!/usr/bin/env python3
"""Nineteenth public GUI pass: bounded review-session memory use."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk

import fragmenter_visual_runtime_v3 as visual_runtime_v3
from fragmenter_public_gui_v18 import PublicFragmenterAppV18


class PublicFragmenterAppV19(PublicFragmenterAppV18):
    def __init__(self) -> None:
        self._last_visual_source: str | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — 3D Review / Texture Mapping")

    def _visual_asset_selected(self, event: tk.Event) -> None:
        row = self._selected_visual_row()
        current = str(Path(row["absolute_path"]).resolve()) if row is not None else None
        previous = self._last_visual_source
        if previous and previous != current:
            visual_runtime_v3.release_visual_source(previous)
            self._texture_photo = None
        self._last_visual_source = current
        self._visual_context_row = None
        super()._visual_asset_selected(event)


def main() -> int:
    app = PublicFragmenterAppV19()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

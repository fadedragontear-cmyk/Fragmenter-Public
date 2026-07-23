#!/usr/bin/env python3
"""Seventeenth public GUI pass: preserve full rendered viewport resolution."""
from __future__ import annotations

import math
from pathlib import Path
import tkinter as tk

from fragmenter_public_gui_v16 import PublicFragmenterAppV16


class PublicFragmenterAppV17(PublicFragmenterAppV16):
    """Avoid halving a render because it is only a few pixels larger than canvas."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — 3D / Texture Mapping Stabilization")

    def _show_png_on_visual_canvas(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        photo = tk.PhotoImage(file=str(path))
        canvas_width = max(1, self.visual_canvas.winfo_width())
        canvas_height = max(1, self.visual_canvas.winfo_height())
        ratio = max(photo.width() / canvas_width, photo.height() / canvas_height)
        # Active renders are intentionally canvas-sized. The inherited implementation
        # subtracted 20 pixels and used ceil(), turning a 1.02 ratio into a 2x
        # downsample. Only reduce images that are materially larger than the canvas.
        factor = math.ceil(ratio) if ratio > 1.10 else 1
        if factor > 1:
            photo = photo.subsample(factor, factor)
        self._texture_photo = photo
        self.visual_canvas.delete("all")
        self.visual_canvas.create_image(
            canvas_width / 2,
            canvas_height / 2,
            image=photo,
            anchor="center",
        )
        self.visual_canvas.create_text(
            10,
            10,
            anchor="nw",
            fill="#EAF4FF",
            text=f"{path.name} | displayed {photo.width()}x{photo.height()} | source render retained at viewport resolution",
        )


def main() -> int:
    app = PublicFragmenterAppV17()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

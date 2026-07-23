#!/usr/bin/env python3
"""V69: validate Tk stipple masks for translucent green corruption."""
from __future__ import annotations

import tkinter as tk
from typing import Any

from fragmenter_public_gui_v68 import PublicFragmenterAppV68


class PublicFragmenterAppV69(PublicFragmenterAppV68):
    """Normalize every simulated-alpha mask before drawing on Windows Tk."""

    VALID_STIPPLES = {"gray12", "gray25", "gray50", "gray75"}

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Green Corruption Hatch")

    @classmethod
    def _normalize_stipple_v69(cls, value: object, fallback: str = "gray12") -> str:
        text = str(value or "")
        return text if text in cls.VALID_STIPPLES else fallback

    @staticmethod
    def _safe_text_v68(canvas: tk.Canvas, x: float, y: float, **kwargs: Any) -> None:
        stipple = PublicFragmenterAppV69._normalize_stipple_v69(
            kwargs.get("stipple"),
            "gray12",
        )
        kwargs["stipple"] = stipple
        try:
            canvas.create_text(x, y, **kwargs)
        except tk.TclError:
            kwargs.pop("angle", None)
            try:
                canvas.create_text(x, y, **kwargs)
            except tk.TclError:
                kwargs.pop("stipple", None)
                canvas.create_text(x, y, **kwargs)

    @staticmethod
    def _safe_line_v68(canvas: tk.Canvas, *coords: float, **kwargs: Any) -> None:
        kwargs["stipple"] = PublicFragmenterAppV69._normalize_stipple_v69(
            kwargs.get("stipple"),
            "gray12",
        )
        try:
            canvas.create_line(*coords, **kwargs)
        except tk.TclError:
            kwargs.pop("stipple", None)
            canvas.create_line(*coords, **kwargs)


def main() -> int:
    app = PublicFragmenterAppV69()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

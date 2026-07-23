#!/usr/bin/env python3
"""Twenty-eighth public GUI pass: authoritative pose restore and visible camera controls."""
from __future__ import annotations

import tkinter as tk

from fragmenter_public_gui_v27 import PublicFragmenterAppV27


class PublicFragmenterAppV28(PublicFragmenterAppV27):
    """Remove competing selection loads and keep the viewport control visually minimal."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Reliable Axis Camera / Saved Views")

    # ------------------------------------------------------------------
    # Selection owns one load path. The inherited v13 stack scheduled a generic
    # wireframe 260 ms after selection while the CCSF animation tree was loading.
    # v27 already loads the correct saved animation/Initial Pose when that tree is
    # ready, so the generic delayed load is both redundant and able to win a race.
    # ------------------------------------------------------------------
    def _schedule_wireframe_load(self) -> None:
        self._wireframe_generation += 1

    def _visual_asset_selected(self, event: tk.Event) -> None:
        # Invalidate an animation worker from the previously focused asset and allow
        # the newly restored frame to start immediately instead of becoming an
        # unconsumed pending frame behind the obsolete worker.
        self._animation_frame_generation += 1
        self._animation_frame_job = False
        self._animation_pending_frame = None
        self._wireframe_generation += 1
        super()._visual_asset_selected(event)

    # ------------------------------------------------------------------
    # Borderless canvas-matched overlay: arrows and +/- are the same operations as
    # keyboard and right-drag. Full background names remain visible at all times.
    # ------------------------------------------------------------------
    def _build_camera_overlay_v27(self) -> None:
        _rgba, canvas_color, text_color, _line_color = self._background_values_v25()
        overlay = tk.Frame(
            self.visual_canvas,
            background=canvas_color,
            borderwidth=0,
            highlightthickness=0,
            takefocus=0,
        )
        self._camera_overlay_v27 = overlay
        self._camera_overlay_buttons_v27 = []

        def button(text: str, command, row: int, column: int, *, width: int = 3) -> tk.Button:
            widget = tk.Button(
                overlay,
                text=text,
                command=command,
                width=width,
                padx=1,
                pady=0,
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                background=canvas_color,
                activebackground=canvas_color,
                foreground=text_color,
                activeforeground=text_color,
                font=("Segoe UI Symbol", 11, "bold"),
                takefocus=0,
            )
            widget.grid(row=row, column=column, padx=1, pady=1)
            self._camera_overlay_buttons_v27.append(widget)
            return widget

        button("↑", lambda: self._orbit_nudge_v27(vertical=-1), 0, 1)
        button("←", lambda: self._orbit_nudge_v27(horizontal=-1), 1, 0)
        button("•", self._fit_view, 1, 1)
        button("→", lambda: self._orbit_nudge_v27(horizontal=1), 1, 2)
        button("↓", lambda: self._orbit_nudge_v27(vertical=1), 2, 1)
        button("+", lambda: self._zoom_nudge_v27(1.12), 0, 3)
        button("−", lambda: self._zoom_nudge_v27(0.89), 2, 3)

        backgrounds = tk.Frame(
            overlay,
            background=canvas_color,
            borderwidth=0,
            highlightthickness=0,
        )
        backgrounds.grid(row=3, column=0, columnspan=4, pady=(3, 0), sticky="e")
        for label, name, width in (
            ("Black", "Black", 5),
            ("Dark", "Dark Gray", 4),
            ("Gray", "Gray", 4),
            ("White", "White", 5),
        ):
            widget = tk.Button(
                backgrounds,
                text=label,
                command=lambda value=name: self._set_background_v27(value),
                width=width,
                padx=0,
                pady=0,
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                background=canvas_color,
                activebackground=canvas_color,
                foreground=text_color,
                activeforeground=text_color,
                font=("Segoe UI", 8),
                takefocus=0,
            )
            widget.pack(side="left", padx=1)
            self._camera_overlay_buttons_v27.append(widget)

        overlay.place(relx=1.0, x=-8, y=8, anchor="ne")
        overlay.lift()


def main() -> int:
    app = PublicFragmenterAppV28()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

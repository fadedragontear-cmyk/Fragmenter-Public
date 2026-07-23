#!/usr/bin/env python3
"""Replace the inherited stable status gag with a captured-only V109 feed."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from celdra_gremlin_memory_v1 import KNOWN_GREMLINS


class FragmenterStableStatusMixinV109:
    """Own the only status strip below the stable and bind it to captured names."""

    def __init__(self) -> None:
        self._stable_status_progress_v109: ttk.Progressbar | None = None
        super().__init__()

    # V103 calls these names from several inherited lifecycle hooks. Redirect all
    # of them to the V109 feed so the old all-roster gag cannot overlap it.
    def _ensure_stable_status_v103(self) -> None:
        self._ensure_stable_status_v109()

    def _start_stable_status_v103(self) -> None:
        self._refresh_stable_status_v109()

    def _cancel_stable_status_v103(self) -> None:
        identifier = getattr(self, "_stable_status_after_v109", None)
        if identifier is not None:
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
            self._stable_status_after_v109 = None
        super()._cancel_stable_status_v103()

    def _ensure_stable_status_v109(self) -> None:
        super()._ensure_stable_status_v109()
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if frame is None:
            return
        bar = self._stable_status_progress_v109
        if bar is not None:
            try:
                if bar.winfo_exists() and bar.master is frame:
                    return
            except tk.TclError:
                pass
        bar = ttk.Progressbar(
            frame,
            orient="horizontal",
            mode="determinate",
            maximum=len(KNOWN_GREMLINS),
            value=0,
            style="RunAll.Visible.Horizontal.TProgressbar",
        )
        bar.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self._stable_status_progress_v109 = bar

    def _refresh_stable_status_v109(self) -> None:
        super()._refresh_stable_status_v109()
        bar = self._stable_status_progress_v109
        if bar is None:
            return
        names = self._stable_names_v101()
        try:
            if not names:
                bar.grid_remove()
                return
            bar.grid()
            bar.configure(maximum=len(KNOWN_GREMLINS))
            bar["value"] = len(names)
        except tk.TclError:
            pass

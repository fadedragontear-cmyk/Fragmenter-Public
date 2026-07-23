#!/usr/bin/env python3
"""Cancellation-safe transient cleanup for V110 presentation effects."""
from __future__ import annotations

import tkinter as tk
from typing import Any


class FragmenterCeldraCleanupMixinV110:
    """Guarantee the three-flash detector cannot leave the console recolored."""

    def __init__(self) -> None:
        self._v110_detection_original_colors: tuple[str, str, str] | None = None
        super().__init__()

    def _restore_console_detection_v110(self) -> None:
        console = getattr(self, "_celdra_console_v49", None)
        colors = self._v110_detection_original_colors
        self._v110_detection_original_colors = None
        self._v110_detection_flash_active = False
        if not isinstance(console, tk.Text) or colors is None:
            return
        try:
            console.configure(
                background=colors[0],
                foreground=colors[1],
                insertbackground=colors[2],
            )
        except tk.TclError:
            pass

    def _flash_console_detection_v110(self) -> None:
        if bool(getattr(self, "_v110_detection_flash_active", False)):
            return
        console = getattr(self, "_celdra_console_v49", None)
        if not isinstance(console, tk.Text):
            return
        try:
            colors = (
                str(console.cget("background")),
                str(console.cget("foreground")),
                str(console.cget("insertbackground")),
            )
        except tk.TclError:
            return
        self._v110_detection_original_colors = colors
        self._v110_detection_flash_active = True
        phase = {"value": 0}

        def tick() -> None:
            self._v110_detection_flash_after = None
            if phase["value"] >= 6:
                self._restore_console_detection_v110()
                return
            red = phase["value"] % 2 == 0
            original = self._v110_detection_original_colors
            if original is None:
                self._restore_console_detection_v110()
                return
            try:
                console.configure(
                    background="#5a0611" if red else original[0],
                    foreground="#fff1f3" if red else original[1],
                    insertbackground="#fff1f3" if red else original[2],
                )
            except tk.TclError:
                self._restore_console_detection_v110()
                return
            phase["value"] += 1
            self._v110_detection_flash_after = self.after(170, tick)

        tick()

    def _cancel_v110_transients(self) -> None:
        identifier = getattr(self, "_v110_detection_flash_after", None)
        if identifier is not None:
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
            self._v110_detection_flash_after = None
        self._restore_console_detection_v110()
        super()._cancel_v110_transients()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["v110_detection_cleanup"] = "original_console_colors_restored_on_every_exit"
        return payload

#!/usr/bin/env python3
"""V116 public-release surface: visible Gremlin stage and reduced public Audio tabs."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class FragmenterPublicSurfaceMixinV116:
    """Expose only release-facing audio tools while preserving research implementations."""

    PUBLIC_VISIBLE_AUDIO_TABS_V116 = (
        "Audio Library / Classifier",
        "Layer Sampler",
    )
    PRESERVED_HIDDEN_AUDIO_TABS_V116 = (
        "Audio Pipeline",
        "SNDDATA Research Mixer",
        "Original Sequencer",
    )

    def __init__(self) -> None:
        self._preserved_audio_tabs_v116: dict[str, tk.Misc] = {}
        super().__init__()
        self.title("Fragmenter 1.0 - Public Release Candidate V116")

    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        self._enforce_public_audio_surface_v116()

    def _enforce_public_audio_surface_v116(self) -> None:
        """Hide non-public tabs without destroying their widgets or implementation."""
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if not isinstance(notebook, ttk.Notebook):
            return
        hidden = set(self.PRESERVED_HIDDEN_AUDIO_TABS_V116)
        visible_widgets: dict[str, tk.Misc] = {}
        for tab_id in tuple(notebook.tabs()):
            try:
                label = str(notebook.tab(tab_id, "text"))
                widget = notebook.nametowidget(tab_id)
            except (KeyError, tk.TclError):
                continue
            if label in hidden:
                self._preserved_audio_tabs_v116[label] = widget
                try:
                    notebook.hide(tab_id)
                except tk.TclError:
                    pass
            else:
                visible_widgets[label] = widget

        preferred = visible_widgets.get("Audio Library / Classifier")
        if preferred is not None:
            try:
                notebook.select(preferred)
            except tk.TclError:
                pass

    def _restore_preserved_audio_tabs_v116(self) -> None:
        """Internal recovery hook for later research builds; not exposed in the public GUI."""
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if not isinstance(notebook, ttk.Notebook):
            return
        for label in self.PRESERVED_HIDDEN_AUDIO_TABS_V116:
            widget = self._preserved_audio_tabs_v116.get(label)
            if widget is None:
                continue
            try:
                notebook.add(widget, text=label)
            except tk.TclError:
                pass

    def _celdra_skit_active_v116(self) -> bool:
        mode = str(getattr(self, "_celdra_middle_mode_v101", "stable") or "stable")
        return bool(
            getattr(self, "_celdra_internal_show_v101", False)
            or getattr(self, "_celdra_gremlin_active_v94", False)
            or getattr(self, "_celdra_collection_reward_active_v101", False)
            or getattr(self, "_celdra_yell_mode_v101", False)
            or mode in {"roster", "chaos", "attention", "depart", "reward"}
        )

    @staticmethod
    def _middle_widths_v116(width: int, *, active_skit: bool) -> tuple[int, int, int]:
        """Return avatar, Gremlin, and console widths that exactly fill the pane."""
        width = max(1, int(width))
        if active_skit:
            stable = max(250, min(380, round(width * 0.39)))
            console = max(165, min(225, round(width * 0.20)))
            avatar_floor = 180
        else:
            stable = max(225, min(325, round(width * 0.31)))
            console = max(180, min(250, round(width * 0.23)))
            avatar_floor = 200

        avatar = width - stable - console
        if avatar < avatar_floor:
            deficit = avatar_floor - avatar
            console_floor = 135 if active_skit else 150
            take = min(deficit, max(0, console - console_floor))
            console -= take
            deficit -= take
            stable_floor = 190 if active_skit else 180
            take = min(deficit, max(0, stable - stable_floor))
            stable -= take
            avatar = width - stable - console

        if avatar < 100:
            avatar = max(1, round(width * 0.34))
            stable = max(1, round(width * (0.43 if active_skit else 0.38)))
            console = max(1, width - avatar - stable)
        else:
            console = max(1, width - avatar - stable)
        return avatar, stable, console

    def _reassert_middle_layout_v115(self) -> None:
        """Give Gremlin skits more width by moving the Core/BRAIN console right."""
        pane = getattr(self, "celdra_visual_split_v50", None)
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if pane is None or frame is None or bool(getattr(self, "_celdra_middle_hidden_v103", False)):
            return
        try:
            self.update_idletasks()
            panes = tuple(pane.panes())
            if len(panes) < 3:
                return
            width = int(pane.winfo_width())
            if width <= 1:
                return
            avatar_width, stable_width, _console_width = self._middle_widths_v116(
                width,
                active_skit=self._celdra_skit_active_v116(),
            )
            pane.sashpos(0, avatar_width)
            pane.sashpos(1, avatar_width + stable_width)
            self._stable_layout_applied_v112 = True
            self._stable_layout_signature_v112 = (round(width / 40) * 40, len(panes))
            wrap = max(150, stable_width - 20)
            status = getattr(self, "_stable_status_label_v109", None)
            if isinstance(status, tk.Label):
                status.configure(wraplength=wrap, justify="left", anchor="w")
        except (AttributeError, tk.TclError):
            pass

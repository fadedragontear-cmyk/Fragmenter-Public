#!/usr/bin/env python3
"""V54: horizontally anchored Celdra console with sliding evolution stage."""
from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Iterable

from celdra_assets_v1 import asset_inventory
from celdra_evolution_pixel_v1 import (
    CELDRA_BLUE_PALETTE,
    CRACK_ONE_LOOP,
    CRACK_TWO_LOOP,
    EGG_LOOP,
    EYES_LOOP,
    EVOLUTION_PHASES,
    HATCH_SEQUENCE,
    PHASE_OPEN_FRACTIONS,
    YOUNG_DRAGON_IDLE,
    frame_resolution,
)
from celdra_pixel_pet_v1 import PixelFrame
from fragmenter_public_gui_v53 import PublicFragmenterAppV53


class PublicFragmenterAppV54(PublicFragmenterAppV53):
    """Keep Celdra's console fixed on the right while presentation panels slide."""

    def __init__(self) -> None:
        self._celdra_stage_ready_v54 = False
        self._celdra_stage_animation_v54: str | None = None
        self._celdra_chat_animation_v54: str | None = None
        self._celdra_stage_open_fraction_v54 = 0.59
        self._celdra_stage_closed_fraction_v54 = 0.035
        self._celdra_stage_phase_v54 = "egg_wait"
        self._celdra_stage_avatar_visible_v54 = False
        self._celdra_stage_dialogue_visible_v54 = False
        self._celdra_stage_animating_v54 = False
        self._celdra_stage_chat_frame_v54: tk.Frame | None = None
        self._celdra_stage_title_v54: tk.StringVar | None = None
        self._celdra_stage_detail_v54: tk.StringVar | None = None
        self._celdra_stage_chat_v54: tk.Text | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Sliding Evolution Stage")

    # ------------------------------------------------------------------
    # Horizontal stage: evolving viewport/dialogue on the left, console fixed right.
    # ------------------------------------------------------------------
    def _build_run_all(self, parent: ttk.Frame) -> None:
        super()._build_run_all(parent)
        self._install_horizontal_celdra_stage_v54()

    def _install_horizontal_celdra_stage_v54(self) -> None:
        pane = self.celdra_visual_split_v50
        stage = self._celdra_avatar_pane_v51
        comms = self._celdra_comms_pane_v51
        if pane is None or stage is None or comms is None:
            return

        # V51 removed the viewport pane when dormant.  Reinsert it once and keep
        # it alive permanently; scripted transitions now move only the sash.
        if str(stage) not in pane.panes():
            try:
                pane.insert(0, stage, weight=3)
            except tk.TclError:
                pane.add(stage, weight=3)
        if str(comms) not in pane.panes():
            pane.add(comms, weight=2)

        stage.configure(padding=0)
        stage.columnconfigure(0, weight=1)
        stage.rowconfigure(0, weight=1)
        canvas = self.celdra_avatar_canvas_v50
        if canvas is not None:
            canvas.configure(background="#081321", highlightthickness=0)
            canvas.grid(row=0, column=0, sticky="nsew")

        self._celdra_stage_title_v54 = tk.StringVar(value="CELDRA EVOLUTION VIEWPORT")
        self._celdra_stage_detail_v54 = tk.StringVar(value="20×20 • DORMANT DRAGONEGG")
        title_bar = tk.Frame(stage, background="#0d2035", highlightthickness=0)
        title_bar.place(x=0, y=0, relwidth=1.0, height=43)
        tk.Label(
            title_bar,
            textvariable=self._celdra_stage_title_v54,
            background="#0d2035",
            foreground="#d9f1ff",
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).pack(fill="x", padx=9, pady=(5, 0))
        tk.Label(
            title_bar,
            textvariable=self._celdra_stage_detail_v54,
            background="#0d2035",
            foreground="#83c7f1",
            anchor="w",
            font=("Consolas", 8),
        ).pack(fill="x", padx=9, pady=(0, 4))

        chat_frame = tk.Frame(stage, background="#101a28", highlightthickness=0)
        chat_header = tk.Label(
            chat_frame,
            text="CELDRA CONVERSATIONAL LINK",
            background="#10243b",
            foreground="#d9f1ff",
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        )
        chat_header.pack(fill="x", padx=0, pady=0, ipady=8)
        chat = tk.Text(
            chat_frame,
            wrap="word",
            state="disabled",
            background="#101a28",
            foreground="#e2f5ff",
            insertbackground="#e2f5ff",
            relief="flat",
            padx=12,
            pady=10,
        )
        chat.pack(fill="both", expand=True)
        tk.Label(
            chat_frame,
            text="ONE-WAY LINK — INPUT CHANNEL NOT INSTALLED",
            background="#10243b",
            foreground="#83c7f1",
            anchor="center",
            font=("Consolas", 8),
        ).pack(fill="x", ipady=5)
        chat_frame.place_forget()
        self._celdra_stage_chat_frame_v54 = chat_frame
        self._celdra_stage_chat_v54 = chat

        # Redirect inherited dialogue writes into the sliding stage.  The old
        # vertical dialogue pane remains detached and is no longer used.
        self._celdra_chat_v49 = chat
        self._celdra_chat_frame_v49 = chat_frame
        self._celdra_notebook_v49 = None
        self._celdra_chat_visible_v49 = False

        pane.bind("<ButtonRelease-1>", self._capture_stage_fraction_v54, add="+")
        self._celdra_stage_ready_v54 = True
        self.after_idle(lambda: self._set_stage_fraction_v54(self._celdra_stage_closed_fraction_v54))

    def _capture_stage_fraction_v54(self, _event: tk.Event | None = None) -> None:
        if self._celdra_stage_animating_v54:
            return
        pane = self.celdra_visual_split_v50
        if pane is None:
            return
        try:
            total = max(1, pane.winfo_width())
            fraction = pane.sashpos(0) / total
        except (AttributeError, tk.TclError):
            return
        if fraction >= 0.12:
            self._celdra_stage_open_fraction_v54 = max(0.30, min(0.74, fraction))

    def _bounded_stage_fraction_v54(self, fraction: float) -> float:
        pane = self.celdra_visual_split_v50
        if pane is None:
            return max(0.02, min(0.78, fraction))
        total = max(1, pane.winfo_width())
        console_minimum = 285
        maximum = max(0.30, 1.0 - console_minimum / total)
        return max(0.02, min(maximum, float(fraction)))

    def _set_stage_fraction_v54(self, fraction: float) -> None:
        pane = self.celdra_visual_split_v50
        if pane is None:
            return
        try:
            total = pane.winfo_width()
            if total > 1:
                pane.sashpos(0, int(total * self._bounded_stage_fraction_v54(fraction)))
        except (AttributeError, tk.TclError):
            pass

    def _cancel_stage_animation_v54(self) -> None:
        if self._celdra_stage_animation_v54 is not None:
            try:
                self.after_cancel(self._celdra_stage_animation_v54)
            except tk.TclError:
                pass
            self._celdra_stage_animation_v54 = None

    def _animate_stage_fraction_v54(self, fraction: float, duration_ms: int = 900) -> None:
        pane = self.celdra_visual_split_v50
        if pane is None or not self._celdra_stage_ready_v54:
            return
        self._cancel_stage_animation_v54()
        try:
            total = max(1, pane.winfo_width())
            start = pane.sashpos(0) / total
        except (AttributeError, tk.TclError):
            start = self._celdra_stage_closed_fraction_v54
        target = self._bounded_stage_fraction_v54(fraction)
        started = time.monotonic()
        self._celdra_stage_animating_v54 = True

        def tick() -> None:
            elapsed = (time.monotonic() - started) * 1000.0
            progress = min(1.0, elapsed / max(1, duration_ms))
            eased = 1.0 - (1.0 - progress) ** 3
            self._set_stage_fraction_v54(start + (target - start) * eased)
            if progress < 1.0:
                self._celdra_stage_animation_v54 = self.after(16, tick)
            else:
                self._celdra_stage_animation_v54 = None
                self._celdra_stage_animating_v54 = False

        tick()

    def _cancel_chat_animation_v54(self) -> None:
        if self._celdra_chat_animation_v54 is not None:
            try:
                self.after_cancel(self._celdra_chat_animation_v54)
            except tk.TclError:
                pass
            self._celdra_chat_animation_v54 = None

    def _slide_chat_v54(self, *, show: bool, duration_ms: int = 700) -> None:
        frame = self._celdra_stage_chat_frame_v54
        stage = self._celdra_avatar_pane_v51
        if frame is None or stage is None:
            return
        self._cancel_chat_animation_v54()
        stage.update_idletasks()
        width = max(1, stage.winfo_width())
        start = -width if show else 0
        target = 0 if show else -width
        if show:
            frame.place(x=start, y=0, relwidth=1.0, relheight=1.0)
            frame.lift()
        started = time.monotonic()

        def tick() -> None:
            current_width = max(1, stage.winfo_width())
            elapsed = (time.monotonic() - started) * 1000.0
            progress = min(1.0, elapsed / max(1, duration_ms))
            eased = progress * progress * (3.0 - 2.0 * progress)
            x = round(((-current_width) if show else 0) + ((0 if show else -current_width) - ((-current_width) if show else 0)) * eased)
            frame.place_configure(x=x, y=0, relwidth=1.0, relheight=1.0)
            if progress < 1.0:
                self._celdra_chat_animation_v54 = self.after(16, tick)
            else:
                self._celdra_chat_animation_v54 = None
                if not show:
                    frame.place_forget()

        tick()

    def _show_avatar_v51(self) -> None:
        if not self._celdra_stage_ready_v54:
            super()._show_avatar_v51()
            return
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._slide_chat_v54(show=False, duration_ms=420)
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA EVOLUTION VIEWPORT")
        target = PHASE_OPEN_FRACTIONS.get(
            self._celdra_stage_phase_v54,
            self._celdra_stage_open_fraction_v54,
        )
        self._animate_stage_fraction_v54(target, 1050)
        self.after_idle(self._redraw_celdra_avatar_v50)

    def _hide_avatar_v51(self) -> None:
        if not self._celdra_stage_ready_v54:
            super()._hide_avatar_v51()
            return
        self._celdra_stage_avatar_visible_v54 = False
        if not self._celdra_stage_dialogue_visible_v54:
            self._animate_stage_fraction_v54(self._celdra_stage_closed_fraction_v54, 850)

    def _show_dialogue_v51(self) -> None:
        if not self._celdra_stage_ready_v54:
            super()._show_dialogue_v51()
            return
        self._celdra_stage_dialogue_visible_v54 = True
        self._celdra_stage_avatar_visible_v54 = False
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA CONVERSATIONAL LINK")
        target = max(0.54, self._celdra_stage_open_fraction_v54)
        self._animate_stage_fraction_v54(target, 900)
        self.after(180, lambda: self._slide_chat_v54(show=True, duration_ms=720))
        self._celdra_chat_visible_v49 = True

    def _hide_dialogue_v51(self) -> None:
        if not self._celdra_stage_ready_v54:
            super()._hide_dialogue_v51()
            return
        self._celdra_stage_dialogue_visible_v54 = False
        self._celdra_chat_visible_v49 = False
        self._slide_chat_v54(show=False, duration_ms=540)
        if not self._celdra_stage_avatar_visible_v54:
            self.after(
                280,
                lambda: self._animate_stage_fraction_v54(
                    self._celdra_stage_closed_fraction_v54,
                    760,
                ),
            )

    # ------------------------------------------------------------------
    # Generated evolution art and progressively larger stage targets.
    # ------------------------------------------------------------------
    def _load_celdra_avatar_frames_v49(self) -> None:
        self.celdra_asset_inventory_v50 = asset_inventory(self.celdra_asset_root_v50)
        self.celdra_external_frames_v50 = {}
        self._play_pixel_sequence_v50(EGG_LOOP, loop=True)

    def _set_avatar_phase_v51(self, phase: str) -> None:
        phase = str(phase or "egg_wait").casefold()
        self._celdra_stage_phase_v54 = phase
        frames = EVOLUTION_PHASES.get(phase, EGG_LOOP)
        loop = phase not in {"hatch_open", "baby_rise"}
        next_state = "idle" if phase in {"hatch_open", "baby_rise"} else None
        self._play_pixel_sequence_v50(frames, loop=loop, next_state=next_state)
        self._update_evolution_detail_v54(phase, frames)
        if self._celdra_stage_avatar_visible_v54:
            self._animate_stage_fraction_v54(
                PHASE_OPEN_FRACTIONS.get(phase, self._celdra_stage_open_fraction_v54),
                780,
            )

    def _set_avatar_state_v49(self, state: str) -> None:
        state = str(state or "idle").casefold()
        self._celdra_avatar_state_v49 = state
        self._celdra_avatar_index_v49 = 0
        if self._celdra_avatar_after_v49 is not None:
            try:
                self.after_cancel(self._celdra_avatar_after_v49)
            except tk.TclError:
                pass
            self._celdra_avatar_after_v49 = None

        if state in {"boot", "hatch"}:
            frames = EGG_LOOP + CRACK_ONE_LOOP + CRACK_TWO_LOOP + EYES_LOOP + HATCH_SEQUENCE
            phase = "hatch_open"
            self._play_pixel_sequence_v50(frames, loop=False, next_state="idle")
        elif state == "egg":
            frames = EGG_LOOP
            phase = "egg_wait"
            self._play_pixel_sequence_v50(frames, loop=True)
        else:
            phase = state if state in EVOLUTION_PHASES else "idle"
            frames = EVOLUTION_PHASES.get(phase, EVOLUTION_PHASES["idle"])
            self._play_pixel_sequence_v50(frames, loop=len(frames) > 1)
        self._celdra_stage_phase_v54 = phase
        self._update_evolution_detail_v54(phase, frames)

    def _update_evolution_detail_v54(
        self,
        phase: str,
        frames: Iterable[PixelFrame],
    ) -> None:
        frame_tuple = tuple(frames)
        width, height = frame_resolution(frame_tuple[0]) if frame_tuple else (0, 0)
        labels = {
            "egg_wait": "DORMANT DRAGONEGG",
            "crack_one": "SHELL STRESS DETECTED",
            "crack_two": "HATCH SEQUENCE ESCALATING",
            "eyes": "LIFE SIGNS CONFIRMED",
            "hatch_open": "SHELL RELEASE",
            "baby_rise": "HATCHLING FORMING",
            "idle": "BLUE DRAGON HATCHLING",
            "baby_idle": "BLUE DRAGON HATCHLING",
            "talk": "VOCALIZATION TEST",
            "thinking": "COGNITIVE ACTIVITY",
            "smirk": "SASS SUBSYSTEM ONLINE",
            "young_dragon": "YOUNG DRAGON BRIDGE FORM",
            "dragongirl": "CLASSIFIED DRAGONGIRL ART TARGET",
        }
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set(
                f"{width}×{height} • {labels.get(phase, phase.upper())}"
            )

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        canvas.delete("all")
        external = self.celdra_current_external_v50
        if external is not None:
            canvas.create_image(
                max(1, canvas.winfo_width()) // 2,
                max(1, canvas.winfo_height()) // 2 + 12,
                image=external,
                anchor="center",
            )
            return
        frame = self.celdra_current_pixel_v50
        if frame is None:
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height() - 43)
        rows = frame.rows
        columns = max((len(row) for row in rows), default=1)
        scale = max(2, min(width // max(1, columns), height // max(1, len(rows))))
        art_width = columns * scale
        art_height = len(rows) * scale
        x0 = (width - art_width) // 2
        y0 = 43 + max(0, (height - art_height) // 2)
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = CELDRA_BLUE_PALETTE.get(symbol, "")
                if not color:
                    continue
                canvas.create_rectangle(
                    x0 + column_index * scale,
                    y0 + row_index * scale,
                    x0 + (column_index + 1) * scale,
                    y0 + (row_index + 1) * scale,
                    fill=color,
                    outline=color,
                )

    # ------------------------------------------------------------------
    # Temporary visual controls while the egg/hatchling art is refined.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        frame = self.tabs.get("Celdra Test")
        if frame is None:
            return
        controls = next(
            (
                child
                for child in frame.winfo_children()
                if isinstance(child, ttk.LabelFrame)
                and str(child.cget("text")) == "Script and avatar tests"
            ),
            None,
        )
        if controls is None:
            return
        ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=7)
        for label, phase in (
            ("V54 Polished Egg Loop", "egg_wait"),
            ("V54 First Crack Loop", "crack_one"),
            ("V54 Advanced Crack Loop", "crack_two"),
            ("V54 Eyes in Egg", "eyes"),
            ("V54 Cute Hatch Sequence", "hatch_open"),
            ("V54 Hatchling Idle", "idle"),
            ("V54 Young Dragon 32×32", "young_dragon"),
        ):
            ttk.Button(
                controls,
                text=label,
                command=lambda selected=phase: self._test_evolution_phase_v54(selected),
                width=25,
            ).pack(fill="x", pady=2)
        ttk.Button(
            controls,
            text="V54 Dragongirl Canvas Target",
            command=self._test_dragongirl_canvas_v54,
            width=25,
        ).pack(fill="x", pady=2)
        ttk.Button(
            controls,
            text="V54 Slide Dialogue",
            command=self._test_dialogue_slide_v54,
            width=25,
        ).pack(fill="x", pady=2)

    def _test_evolution_phase_v54(self, phase: str) -> None:
        self._select_run_all_tab_v50()
        self._celdra_session_active_v49 = True
        self._hide_dialogue_v51()
        self._set_avatar_phase_v51(phase)
        self._show_avatar_v51()

    def _test_dragongirl_canvas_v54(self) -> None:
        self._select_run_all_tab_v50()
        self._celdra_stage_phase_v54 = "dragongirl"
        self._update_evolution_detail_v54("dragongirl", YOUNG_DRAGON_IDLE)
        self._show_avatar_v51()
        self._animate_stage_fraction_v54(PHASE_OPEN_FRACTIONS["dragongirl"], 1100)

    def _test_dialogue_slide_v54(self) -> None:
        self._select_run_all_tab_v50()
        self._celdra_session_active_v49 = True
        self._show_dialogue_v51()
        if self._celdra_chat_v49 is not None:
            self._replace_chat_v49("")
            self.after(
                500,
                lambda: self._append_chat_v49(
                    "Celdra> This panel slides now. The console stays exactly where you left it."
                ),
            )



def main() -> int:
    app = PublicFragmenterAppV54()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

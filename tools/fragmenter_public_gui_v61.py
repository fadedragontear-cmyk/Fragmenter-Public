#!/usr/bin/env python3
"""V61: static-corrupted Dragonegg, anticlimactic smoke, and text-only boot."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_startup_timeline_v5 import (
    FIRST_RUN_AFTER_CCSF,
    TimelineEvent,
)
from fragmenter_public_gui_v58 import PublicFragmenterAppV58
from fragmenter_public_gui_v60 import PublicFragmenterAppV60


class PublicFragmenterAppV61(PublicFragmenterAppV60):
    """Keep the Gremlin in the test lab and remove it from canonical startup."""

    def __init__(self) -> None:
        self._celdra_glitch_level_v61 = 0
        self._celdra_glitch_phase_v61 = 0
        self._celdra_glitch_after_v61: str | None = None
        self._celdra_smoke_active_v61 = False
        self._celdra_smoke_step_v61 = 0
        self._celdra_smoke_after_v61: str | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Static-Smoke Integration")

    # ------------------------------------------------------------------
    # Canonical timeline: the egg is the only generated production avatar.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._stop_v61_visual_effects()
        self._celdra_user_name_v58 = "noname"
        self._celdra_name_prompt_resolved_v58 = True
        self._hide_name_input_v58()
        super()._prepare_first_run_surface_v51()

    def _begin_first_run_timeline_v51(self, speed: float = 1.0) -> None:
        if self._celdra_timeline_started_v51:
            return
        self._celdra_timeline_started_v51 = True
        self._celdra_timeline_speed_v51 = max(0.01, float(speed))
        self._celdra_user_name_v58 = "noname"
        self._append_console_v49(
            "[CORE] TASK COMPLETE: DEPLOYING TAVERN ESCAPE PLAN #735 [SUCCESS]"
        )
        for event in FIRST_RUN_AFTER_CCSF:
            delay = max(0, round(event.at_ms * self._celdra_timeline_speed_v51))
            self._remember_after_v49(
                delay,
                lambda selected=event: self._emit_timeline_event_v51(selected),
            )

    def _emit_timeline_event_v51(self, event: TimelineEvent) -> None:
        if event.action == "egg_glitch":
            try:
                level = int(event.text or "1")
            except ValueError:
                level = 1
            self._set_egg_glitch_v61(level)
            return
        if event.action == "blue_smoke":
            self._start_blue_smoke_v61()
            return

        # Bypass V60's production base-search hatchling choreography.  Calling
        # V58 directly retains the scripted chat/avatar takeover behavior and
        # the V56 classified-avatar breakpoint, but no Gremlin is shown between
        # the smoke release and the real Dragongirl integration scene.
        PublicFragmenterAppV58._emit_timeline_event_v51(self, event)

    # ------------------------------------------------------------------
    # Egg corruption: deterministic .hack-like static around the shell.
    # ------------------------------------------------------------------
    def _set_egg_glitch_v61(self, level: int) -> None:
        self._celdra_glitch_level_v61 = max(0, min(3, int(level)))
        if self._celdra_glitch_level_v61 <= 0:
            self._cancel_glitch_v61()
            self._redraw_celdra_avatar_v50()
            return
        if self._celdra_glitch_after_v61 is None:
            self._tick_egg_glitch_v61()

    def _tick_egg_glitch_v61(self) -> None:
        self._celdra_glitch_after_v61 = None
        if self._celdra_glitch_level_v61 <= 0 or self._celdra_smoke_active_v61:
            return
        self._celdra_glitch_phase_v61 = (self._celdra_glitch_phase_v61 + 1) % 24
        self._redraw_celdra_avatar_v50()
        interval = {1: 190, 2: 115, 3: 72}.get(self._celdra_glitch_level_v61, 160)
        self._celdra_glitch_after_v61 = self.after(interval, self._tick_egg_glitch_v61)

    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        level = self._celdra_glitch_level_v61
        if level <= 0:
            return
        phase = self._celdra_glitch_phase_v61
        cx = width // 2
        cy = height // 2 + 18
        colors = ("#78b9ea", "#d9f1ff", "#2f6fa5", "#a9dcff")

        count = 4 + level * 5
        for index in range(count):
            side = -1 if index % 2 == 0 else 1
            lane = index // 2
            bar_width = 10 + ((phase * 7 + index * 13) % (22 + level * 10))
            x = cx + side * (42 + (lane * 17) % max(48, width // 3))
            if side < 0:
                x -= bar_width
            y = cy - 82 + ((phase * 11 + index * 29) % 164)
            thickness = 1 + ((phase + index) % (1 + level))
            canvas.create_rectangle(
                x,
                y,
                x + bar_width,
                y + thickness,
                fill=colors[(phase + index) % len(colors)],
                outline="",
                tags="v61_glitch",
            )

        for index in range(level * 4):
            x = cx - 120 + ((phase * 31 + index * 47) % 240)
            y = cy - 100 + ((phase * 17 + index * 37) % 200)
            size = 2 + ((phase + index) % 4)
            canvas.create_rectangle(
                x,
                y,
                x + size,
                y + size,
                fill=colors[(index + level) % len(colors)],
                outline="",
                tags="v61_glitch",
            )

        if level >= 2:
            fragments = ("//FRAGMENT//", "CCSF", "Δ LOST DATA", "010011")
            canvas.create_text(
                max(12, cx - 138),
                max(54, cy - 108 + (phase % 3) * 9),
                text=fragments[phase % len(fragments)],
                anchor="w",
                fill=colors[phase % len(colors)],
                font=("Consolas", 8, "bold"),
                tags="v61_glitch",
            )
        if level >= 3 and phase % 3 == 0:
            canvas.create_line(
                4,
                cy + ((phase * 13) % 90) - 45,
                width - 4,
                cy + ((phase * 13) % 90) - 45,
                fill="#d9f1ff",
                width=2,
                dash=(3, 5),
                tags="v61_glitch",
            )

    # ------------------------------------------------------------------
    # The canonical hatch is deliberately just a small blue-smoke release.
    # ------------------------------------------------------------------
    def _start_blue_smoke_v61(self) -> None:
        self._cancel_glitch_v61()
        self._celdra_glitch_level_v61 = 0
        if self._celdra_avatar_after_v49 is not None:
            try:
                self.after_cancel(self._celdra_avatar_after_v49)
            except tk.TclError:
                pass
            self._celdra_avatar_after_v49 = None
        self._celdra_smoke_active_v61 = True
        self._celdra_smoke_step_v61 = 0
        self._tick_blue_smoke_v61()

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
        self._celdra_smoke_after_v61 = self.after(90, self._tick_blue_smoke_v61)

    def _draw_blue_smoke_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        step = self._celdra_smoke_step_v61
        cx = width // 2
        cy = height // 2 + 25
        colors = ("#16375f", "#2f6fa5", "#78b9ea", "#a9dcff", "#d9f1ff")
        puffs = (
            (-24, 3, 14),
            (-9, -5, 18),
            (8, 1, 16),
            (25, -4, 13),
            (1, -20, 12),
        )
        for index, (dx, dy, radius) in enumerate(puffs):
            rise = step * (2 + index % 2)
            spread = step // 3
            x = cx + dx + (-spread if index < 2 else spread if index > 2 else 0)
            y = cy + dy - rise
            r = radius + step // 2
            canvas.create_oval(
                x - r,
                y - r,
                x + r,
                y + r,
                fill=colors[(step // 3 + index) % len(colors)],
                outline="",
                tags="v61_smoke",
            )
        if step < 5:
            canvas.create_text(
                cx,
                cy + 42,
                text="pff",
                fill="#78b9ea",
                font=("Consolas", 9, "italic"),
                tags="v61_smoke",
            )

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        if self._celdra_smoke_active_v61 and self._celdra_smoke_step_v61 >= 3:
            canvas.delete("all")
        else:
            super()._redraw_celdra_avatar_v50()
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        if self._celdra_smoke_active_v61:
            self._draw_blue_smoke_v61(canvas, width, height)
        elif self._celdra_glitch_level_v61 > 0:
            self._draw_egg_glitch_v61(canvas, width, height)

    def _cancel_glitch_v61(self) -> None:
        if self._celdra_glitch_after_v61 is not None:
            try:
                self.after_cancel(self._celdra_glitch_after_v61)
            except tk.TclError:
                pass
            self._celdra_glitch_after_v61 = None

    def _cancel_smoke_v61(self) -> None:
        if self._celdra_smoke_after_v61 is not None:
            try:
                self.after_cancel(self._celdra_smoke_after_v61)
            except tk.TclError:
                pass
            self._celdra_smoke_after_v61 = None
        self._celdra_smoke_active_v61 = False

    def _stop_v61_visual_effects(self) -> None:
        self._cancel_glitch_v61()
        self._cancel_smoke_v61()
        self._celdra_glitch_level_v61 = 0
        self._celdra_smoke_step_v61 = 0

    def _cancel_celdra_cues_v49(self) -> None:
        self._stop_v61_visual_effects()
        super()._cancel_celdra_cues_v49()

    def _show_timeline_failure_v51(self) -> None:
        self._stop_v61_visual_effects()
        super()._show_timeline_failure_v51()

    # ------------------------------------------------------------------
    # Test lab: production smoke preview plus explicitly test-only Gremlin states.
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

        choices = (
            "Production egg / static / smoke",
            "Polished egg loop",
            "Gremlin hatchling — test only",
            "Gremlin base search — test only",
            "Gremlin squished — test only",
            "Gremlin base claim — test only",
            "Gremlin failed search — test only",
            "Gremlin young form — test only",
            "Interactive dragongirl reveal",
        )
        self._celdra_preview_map_v60 = {
            choices[0]: "production_smoke",
            choices[1]: "egg_wait",
            choices[2]: "idle",
            choices[3]: "base_search",
            choices[4]: "squished",
            choices[5]: "base_claim",
            choices[6]: "base_failed",
            choices[7]: "young_dragon",
            choices[8]: "avatar_takeover",
        }
        if self._celdra_preview_choice_v60 is not None:
            self._celdra_preview_choice_v60.set(choices[0])
        for widget in self._walk_widgets_v61(controls):
            if isinstance(widget, ttk.Combobox):
                try:
                    if str(widget.cget("textvariable")) == str(self._celdra_preview_choice_v60):
                        widget.configure(values=choices)
                except tk.TclError:
                    pass
            elif isinstance(widget, ttk.Button) and str(widget.cget("text")) == "V58 Name Prompt (30s)":
                widget.configure(
                    text="Canonical chatbar failure",
                    command=self._test_chatbar_failure_v61,
                )

    @staticmethod
    def _walk_widgets_v61(parent: tk.Widget) -> tuple[tk.Widget, ...]:
        found: list[tk.Widget] = []
        for child in parent.winfo_children():
            found.append(child)
            found.extend(PublicFragmenterAppV61._walk_widgets_v61(child))
        return tuple(found)

    def _play_preview_v60(self) -> None:
        choice = self._celdra_preview_choice_v60.get() if self._celdra_preview_choice_v60 else ""
        if self._celdra_preview_map_v60.get(choice) == "production_smoke":
            self._test_production_smoke_v61()
            return
        super()._play_preview_v60()

    def _test_production_smoke_v61(self) -> None:
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._celdra_session_active_v49 = True
        self._celdra_stage_phase_v54 = "egg_wait"
        self._set_avatar_phase_v51("egg_wait")
        self._show_avatar_v51()
        self._remember_after_v49(1_200, lambda: self._set_egg_glitch_v61(1))
        self._remember_after_v49(2_300, lambda: self._set_egg_glitch_v61(2))
        self._remember_after_v49(3_400, lambda: self._set_egg_glitch_v61(3))
        self._remember_after_v49(4_700, self._start_blue_smoke_v61)

    def _test_chatbar_failure_v61(self) -> None:
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._celdra_session_active_v49 = True
        self._celdra_user_name_v58 = "noname"
        self._hide_name_input_v58()
        self._hide_avatar_v51()
        self._show_dialogue_v51()
        self._replace_chat_v49(
            "Celdra> Oh, right. No text input.\n\n"
            "Celdra> Guess I'm not in the tavern anymore.\n\n"
        )
        self._set_status_segment_v51(
            "[CELDRA] HACKING A CHATBAR FOR THE USER",
            0,
            100,
            4_000,
        )
        self._remember_after_v49(
            4_050,
            lambda: self._append_console_v49(
                "[CORE] TASK COMPLETE: HACKING A CHATBAR FOR THE USER [FAILED]"
            ),
        )
        self._remember_after_v49(
            4_300,
            lambda: self._append_console_v49(
                "[BRAIN] ERROR: INPUT CHANNEL INJECTION REJECTED"
            ),
        )
        self._remember_after_v49(
            4_700,
            lambda: self._append_chat_v49(
                "Celdra> Well that was kinda rude. Fine, noname, have it your way."
            ),
        )


def main() -> int:
    app = PublicFragmenterAppV61()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

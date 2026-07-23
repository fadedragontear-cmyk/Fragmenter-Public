#!/usr/bin/env python3
"""V63: hacked seal, unstable energy hatch, GIF concealment cut, polished reveal."""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_startup_timeline_v6 import FIRST_RUN_AFTER_CCSF, TimelineEvent
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v62 import PublicFragmenterAppV62


class PublicFragmenterAppV63(PublicFragmenterAppV62):
    """Escalate the Dragonegg climax and slow the classified-avatar entrance."""

    HATCH_GIF_RELATIVE = "avatar/01.gif"
    ENERGY_STEPS = 72

    def __init__(self) -> None:
        self._celdra_energy_active_v63 = False
        self._celdra_energy_step_v63 = 0
        self._celdra_energy_after_v63: str | None = None
        self._celdra_energy_gif_started_v63 = False
        self._celdra_hatch_gif_frames_v63: list[tk.PhotoImage] = []
        self._celdra_speech_canvas_v63: tk.Canvas | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Energy-Hatch Integration")

    # ------------------------------------------------------------------
    # Canonical V6 timeline.
    # ------------------------------------------------------------------
    def _begin_first_run_timeline_v51(self, speed: float = 1.0) -> None:
        if self._celdra_timeline_started_v51:
            return
        self._celdra_timeline_started_v51 = True
        self._celdra_timeline_speed_v51 = max(0.01, float(speed))
        self._celdra_user_name_v58 = "noname"
        self._append_console_v49(
            "[CORE] TASK COMPLETE: DEPLOYING TAVERN ESCAPE PLAN [SUCCESS]"
        )
        for event in FIRST_RUN_AFTER_CCSF:
            delay = max(0, round(event.at_ms * self._celdra_timeline_speed_v51))
            self._remember_after_v49(
                delay,
                lambda selected=event: self._emit_timeline_event_v51(selected),
            )

    def _emit_timeline_event_v51(self, event: TimelineEvent) -> None:
        if event.action == "energy_hatch":
            self._start_energy_hatch_v63()
            return
        if event.action == "hide_avatar":
            self._stop_energy_hatch_v63(clear_avatar=True)
        super()._emit_timeline_event_v51(event)

    # ------------------------------------------------------------------
    # Stronger deterministic Fragment-style corruption.
    # ------------------------------------------------------------------
    def _set_egg_glitch_v61(self, level: int) -> None:
        self._celdra_glitch_level_v61 = max(0, min(4, int(level)))
        if self._celdra_glitch_level_v61 <= 0:
            self._cancel_glitch_v61()
            self._redraw_celdra_avatar_v50()
            return
        if self._celdra_glitch_after_v61 is None:
            self._tick_egg_glitch_v61()

    def _tick_egg_glitch_v61(self) -> None:
        self._celdra_glitch_after_v61 = None
        if self._celdra_glitch_level_v61 <= 0 or self._celdra_energy_active_v63:
            return
        self._celdra_glitch_phase_v61 = (self._celdra_glitch_phase_v61 + 1) % 64
        self._redraw_celdra_avatar_v50()
        interval = {1: 180, 2: 105, 3: 66, 4: 42}.get(
            self._celdra_glitch_level_v61,
            140,
        )
        self._celdra_glitch_after_v61 = self.after(interval, self._tick_egg_glitch_v61)

    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        level = self._celdra_glitch_level_v61
        if level <= 0:
            return
        phase = self._celdra_glitch_phase_v61
        cx = width // 2
        cy = height // 2 + 18
        colors = ("#78b9ea", "#d9f1ff", "#2f6fa5", "#a9dcff", "#a983e8")

        self._draw_displaced_egg_slices_v63(canvas, width, height, level, phase)

        # Broken orbital fragments imply that the viewport itself is losing lock.
        for ring in range(2 + level):
            radius_x = 62 + ring * 24 + ((phase * (ring + 3)) % 17)
            radius_y = 48 + ring * 17 + ((phase * (ring + 5)) % 13)
            start = (phase * (17 + ring * 4) + ring * 71) % 360
            extent = 28 + ((phase * 7 + ring * 19) % 74)
            canvas.create_arc(
                cx - radius_x,
                cy - radius_y,
                cx + radius_x,
                cy + radius_y,
                start=start,
                extent=extent,
                style="arc",
                outline=colors[(phase + ring) % len(colors)],
                width=1 + level // 2,
                dash=(2 + ring % 3, 4 + level),
                tags="v63_glitch",
            )

        # Horizontal data tears, doubled with opposite chromatic offsets.
        tear_count = 6 + level * 6
        for index in range(tear_count):
            y = cy - 116 + ((phase * 13 + index * 31) % 232)
            length = 12 + ((phase * 11 + index * 23) % (34 + level * 16))
            side = -1 if (index + phase) % 2 == 0 else 1
            x = cx + side * (35 + ((index * 29 + phase * 5) % max(50, width // 3)))
            if side < 0:
                x -= length
            color = colors[(index + phase) % len(colors)]
            canvas.create_rectangle(
                x,
                y,
                x + length,
                y + 1 + ((index + level) % 3),
                fill=color,
                outline="",
                tags="v63_glitch",
            )
            if level >= 3:
                canvas.create_rectangle(
                    x + side * 5,
                    y + 3,
                    x + side * 5 + length // 2,
                    y + 4,
                    fill="#d986ff" if index % 2 else "#78e8ff",
                    outline="",
                    tags="v63_glitch",
                )

        fragments = (
            "//FRAGMENT//",
            "CCSF::DESYNC",
            "Δ LOST DATA",
            "ROOT_TOWN?",
            "01100101 01100111 01100111",
            "SIGNAL/UNSTABLE",
        )
        if level >= 2:
            for index in range(level - 1):
                x = 14 if index % 2 == 0 else max(14, width - 190)
                y = 54 + ((phase * 9 + index * 43) % max(70, height - 120))
                canvas.create_text(
                    x,
                    y,
                    text=fragments[(phase + index) % len(fragments)],
                    anchor="w",
                    fill=colors[(phase + index * 2) % len(colors)],
                    font=("Consolas", 8 + (1 if level >= 4 else 0), "bold"),
                    tags="v63_glitch",
                )

        # Level four occasionally tears the entire viewport with a white scan.
        if level >= 4:
            scan_y = 46 + ((phase * 19) % max(60, height - 70))
            canvas.create_line(
                0,
                scan_y,
                width,
                scan_y,
                fill="#ffffff",
                width=2,
                dash=(2, 3),
                tags="v63_glitch",
            )
            if phase % 7 == 0:
                canvas.create_rectangle(
                    0,
                    max(43, scan_y - 5),
                    width,
                    scan_y + 5,
                    fill="#d9f1ff",
                    outline="",
                    stipple="gray25",
                    tags="v63_glitch",
                )

    def _draw_displaced_egg_slices_v63(
        self,
        canvas: tk.Canvas,
        width: int,
        height: int,
        level: int,
        phase: int,
    ) -> None:
        frame = self.celdra_current_pixel_v50
        if frame is None:
            return
        rows = frame.rows
        if not rows:
            return
        columns = max((len(row) for row in rows), default=1)
        usable_height = max(1, height - 43)
        scale = max(2, min(width // max(1, columns), usable_height // len(rows)))
        x0 = (width - columns * scale) // 2
        y0 = 43 + max(0, (usable_height - len(rows) * scale) // 2)
        slice_colors = ("#78e8ff", "#d986ff", "#ffffff")
        for index in range(1 + level * 2):
            row_index = (phase * 3 + index * 7) % len(rows)
            row = rows[row_index]
            direction = -1 if index % 2 == 0 else 1
            shift = direction * (3 + level * 2 + (phase + index) % 7)
            run_start: int | None = None
            for column_index in range(len(row) + 1):
                filled = column_index < len(row) and row[column_index] != "."
                if filled and run_start is None:
                    run_start = column_index
                if not filled and run_start is not None:
                    canvas.create_rectangle(
                        x0 + run_start * scale + shift,
                        y0 + row_index * scale,
                        x0 + column_index * scale + shift,
                        y0 + (row_index + 1) * scale,
                        fill=slice_colors[(index + phase) % len(slice_colors)],
                        outline="",
                        tags="v63_glitch",
                    )
                    run_start = None

    # ------------------------------------------------------------------
    # Massive energy wave, white concealment cut, bundled GIF reveal.
    # ------------------------------------------------------------------
    def _start_energy_hatch_v63(self) -> None:
        self._cancel_glitch_v61()
        self._celdra_glitch_level_v61 = 0
        self._cancel_smoke_v61()
        if self._celdra_avatar_after_v49 is not None:
            try:
                self.after_cancel(self._celdra_avatar_after_v49)
            except tk.TclError:
                pass
            self._celdra_avatar_after_v49 = None
        self._celdra_energy_active_v63 = True
        self._celdra_energy_step_v63 = 0
        self._celdra_energy_gif_started_v63 = False
        self._append_console_v49("[CORE] DRAGONEGG ENERGY RELEASE IN PROGRESS")
        self._tick_energy_hatch_v63()

    def _tick_energy_hatch_v63(self) -> None:
        self._celdra_energy_after_v63 = None
        if not self._celdra_energy_active_v63:
            return
        if self._celdra_energy_step_v63 == 44 and not self._celdra_energy_gif_started_v63:
            self._begin_hatch_gif_v63()
        self._redraw_celdra_avatar_v50()
        self._celdra_energy_step_v63 += 1
        if self._celdra_energy_step_v63 >= self.ENERGY_STEPS:
            self._celdra_energy_active_v63 = False
            self._redraw_celdra_avatar_v50()
            return
        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        interval = max(10, round(175 * speed))
        self._celdra_energy_after_v63 = self.after(interval, self._tick_energy_hatch_v63)

    def _begin_hatch_gif_v63(self) -> None:
        self._celdra_energy_gif_started_v63 = True
        frames = self._load_hatch_gif_v63()
        if not frames:
            self._append_console_v49(
                "[CORE] BABY DRAGON GIF LOAD FAILED; WHITEOUT FALLBACK RETAINED"
            )
            self.celdra_current_pixel_v50 = None
            self.celdra_current_external_v50 = None
            return
        self._play_external_sequence_v50(frames)
        self._append_console_v49("[CORE] BABY DRAGON AVATAR INSTALLED BEHIND WHITEOUT")

    def _load_hatch_gif_v63(self) -> list[tk.PhotoImage]:
        if self._celdra_hatch_gif_frames_v63:
            return self._celdra_hatch_gif_frames_v63
        path = self.celdra_asset_root_v50 / self.HATCH_GIF_RELATIVE
        if not path.is_file():
            inventory = getattr(self, "celdra_asset_inventory_v50", {}) or {}
            gifs = inventory.get("animated_gifs") or []
            if gifs:
                path = self.celdra_asset_root_v50 / str(gifs[0].get("relative_path") or "")
        if not path.is_file():
            return []
        frames: list[tk.PhotoImage] = []
        for index in range(500):
            try:
                image = tk.PhotoImage(file=str(path), format=f"gif -index {index}")
            except tk.TclError:
                break
            frames.append(self._fit_photo_v50(image, 360, 310))
        self._celdra_hatch_gif_frames_v63 = frames
        return frames

    def _draw_energy_wave_v63(self, canvas: tk.Canvas, width: int, height: int) -> None:
        step = self._celdra_energy_step_v63
        if step >= 48:
            return
        cx = width // 2
        cy = height // 2 + 18
        charge = min(1.0, step / 34.0)
        burst = max(0.0, (step - 18) / 28.0)
        colors = ("#16375f", "#2f6fa5", "#78b9ea", "#a9dcff", "#d9f1ff", "#b58cff")

        # Concentric broken wavefronts.
        for ring in range(8):
            radius = 24 + ring * 19 + step * (2 + ring % 3)
            flatten = 0.72 + (ring % 2) * 0.12
            canvas.create_oval(
                cx - radius,
                cy - int(radius * flatten),
                cx + radius,
                cy + int(radius * flatten),
                outline=colors[(ring + step // 3) % len(colors)],
                width=1 + ((ring + step) % 3),
                dash=(3 + ring % 4, 4 + (step + ring) % 6),
                tags="v63_energy",
            )

        # Rotating radial beams make the release fill the entire viewport.
        beam_count = 18
        max_radius = max(width, height) * (0.45 + burst * 0.55)
        for index in range(beam_count):
            angle = math.radians(index * (360 / beam_count) + step * (3 + index % 3))
            inner = 18 + (index % 4) * 6
            outer = max_radius * (0.65 + ((index * 17 + step * 5) % 35) / 100.0)
            x1 = cx + math.cos(angle) * inner
            y1 = cy + math.sin(angle) * inner
            x2 = cx + math.cos(angle) * outer
            y2 = cy + math.sin(angle) * outer
            canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=colors[(index + step) % len(colors)],
                width=1 + (index + step) % 4,
                tags="v63_energy",
            )

        # Dense deterministic particle field.
        particle_count = 34 + int(charge * 42)
        for index in range(particle_count):
            angle = math.radians((index * 137 + step * (9 + index % 5)) % 360)
            distance = 28 + ((index * 43 + step * 17) % max(36, int(max_radius)))
            x = cx + math.cos(angle) * distance
            y = cy + math.sin(angle) * distance * 0.78
            size = 1 + ((index + step) % 5)
            canvas.create_rectangle(
                x - size,
                y - size,
                x + size,
                y + size,
                fill=colors[(index * 2 + step) % len(colors)],
                outline="",
                tags="v63_energy",
            )

        core_radius = 18 + int(charge * 42) + int(burst * 36)
        canvas.create_oval(
            cx - core_radius,
            cy - core_radius,
            cx + core_radius,
            cy + core_radius,
            fill="#d9f1ff" if step % 3 else "#ffffff",
            outline="#78b9ea",
            width=4,
            stipple="gray25" if step < 34 else "",
            tags="v63_energy",
        )

    def _draw_whiteout_v63(self, canvas: tk.Canvas, width: int, height: int) -> None:
        step = self._celdra_energy_step_v63
        stipple = ""
        fill = "#ffffff"
        if 32 <= step <= 34:
            stipple = "gray12"
        elif 35 <= step <= 37:
            stipple = "gray25"
        elif 38 <= step <= 40:
            stipple = "gray50"
        elif step == 41:
            stipple = "gray75"
        elif 42 <= step <= 52:
            stipple = ""
        elif 53 <= step <= 56:
            stipple = "gray75"
        elif 57 <= step <= 59:
            stipple = "gray50"
        elif 60 <= step <= 62:
            stipple = "gray25"
        elif 63 <= step <= 65:
            stipple = "gray12"
        else:
            return
        kwargs: dict[str, Any] = {
            "fill": fill,
            "outline": "",
            "tags": "v63_whiteout",
        }
        if stipple:
            kwargs["stipple"] = stipple
        try:
            canvas.create_rectangle(0, 0, width, height, **kwargs)
        except tk.TclError:
            kwargs.pop("stipple", None)
            canvas.create_rectangle(0, 0, width, height, **kwargs)

    def _redraw_celdra_avatar_v50(self) -> None:
        super()._redraw_celdra_avatar_v50()
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        if self._celdra_energy_active_v63:
            self._draw_energy_wave_v63(canvas, width, height)
            self._draw_whiteout_v63(canvas, width, height)

    def _stop_energy_hatch_v63(self, *, clear_avatar: bool) -> None:
        if self._celdra_energy_after_v63 is not None:
            try:
                self.after_cancel(self._celdra_energy_after_v63)
            except tk.TclError:
                pass
            self._celdra_energy_after_v63 = None
        self._celdra_energy_active_v63 = False
        self._celdra_energy_step_v63 = 0
        self._celdra_energy_gif_started_v63 = False
        if clear_avatar:
            if self._celdra_avatar_after_v49 is not None:
                try:
                    self.after_cancel(self._celdra_avatar_after_v49)
                except tk.TclError:
                    pass
                self._celdra_avatar_after_v49 = None
            self.celdra_current_external_v50 = None
            self.celdra_current_pixel_v50 = None

    def _stop_v61_visual_effects(self) -> None:
        self._stop_energy_hatch_v63(clear_avatar=True)
        super()._stop_v61_visual_effects()

    # ------------------------------------------------------------------
    # Rounded speech bubble with a visible tail.
    # ------------------------------------------------------------------
    def _install_horizontal_celdra_stage_v54(self) -> None:
        super()._install_horizontal_celdra_stage_v54()
        stage = self._celdra_avatar_pane_v51
        if stage is None:
            return
        previous = self._celdra_speech_bubble_v58
        if previous is not None:
            try:
                previous.destroy()
            except tk.TclError:
                pass
        bubble = tk.Canvas(
            stage,
            background="#081321",
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
        )
        bubble.place_forget()
        self._celdra_speech_canvas_v63 = bubble
        self._celdra_speech_bubble_v58 = bubble

    @staticmethod
    def _rounded_polygon_v63(
        canvas: tk.Canvas,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        radius: float,
        **kwargs: Any,
    ) -> int:
        points = (
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        )
        return canvas.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            **kwargs,
        )

    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = self._celdra_speech_canvas_v63
        if bubble is None:
            return
        line_count = max(1, str(text).count("\n") + 1)
        height = 112 + max(0, line_count - 1) * 28
        bubble.place(relx=0.045, rely=0.065, anchor="nw", relwidth=0.63, height=height)
        bubble.update_idletasks()
        width = max(260, bubble.winfo_width())
        bubble.delete("all")

        # Soft offset shadow, rounded body, and a lower-right conversational tail.
        self._rounded_polygon_v63(
            bubble,
            10,
            10,
            width - 8,
            height - 24,
            19,
            fill="#16375f",
            outline="",
        )
        bubble.create_polygon(
            width - 108,
            height - 29,
            width - 70,
            height - 29,
            width - 91,
            height - 4,
            fill="#16375f",
            outline="",
        )
        self._rounded_polygon_v63(
            bubble,
            5,
            5,
            width - 13,
            height - 29,
            19,
            fill="#f4fbff",
            outline="#78b9ea",
            width=3,
        )
        bubble.create_polygon(
            width - 116,
            height - 34,
            width - 78,
            height - 34,
            width - 99,
            height - 9,
            fill="#f4fbff",
            outline="#78b9ea",
            width=2,
        )
        bubble.create_text(
            26,
            24,
            text=text,
            anchor="nw",
            width=max(180, width - 58),
            fill="#071426",
            font=("Segoe UI", 11, "bold"),
            justify="left",
        )
        bubble.lift()

    # ------------------------------------------------------------------
    # Console-first, deliberately awkward 12-second Shy entrance.
    # ------------------------------------------------------------------
    def _start_avatar_takeover_v58(self) -> None:
        self._cancel_name_timer_v58()
        self._hide_name_input_v58()
        self._hide_dialogue_v51()
        self._hide_speech_bubble_v58()
        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = None
        self._celdra_external_offset_y_v58 = 0
        if self._celdra_status_strip_v51 is not None:
            self._celdra_status_strip_v51.grid_remove()
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA SYSTEM INTEGRATION")
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set("CONSOLE CHANNEL PRELOADED • AVATAR WAITING")

        # Console-heavy width settles several seconds before Shy is loaded.
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.34, 1_350)
        self._append_console_v49("[CORE] DRAGONGIRL AVATAR CHANNEL PRELOADED")
        self._append_console_v49("[CORE] CONSOLE CHANNEL LOCKED AND READY")
        for delay in (80, 700, 1_500, 2_500):
            self.after(delay, self._scroll_all_text_v58)

        self._remember_after_v49(3_000, self._begin_shy_reveal_v63)
        self._remember_after_v49(
            15_800,
            lambda: self._show_speech_bubble_v58(
                "Test, Test, Check check can you hear me?"
            ),
        )
        self._remember_after_v49(20_500, self._takeover_confused_v58)
        self._remember_after_v49(24_500, self._takeover_console_return_v58)
        self._remember_after_v49(30_000, self._takeover_wink_v58)

    def _begin_shy_reveal_v63(self) -> None:
        if not self._load_takeover_reaction_v58("shy"):
            return
        canvas_height = (
            self.celdra_avatar_canvas_v50.winfo_height()
            if self.celdra_avatar_canvas_v50 is not None
            else 420
        )
        self._celdra_external_offset_y_v58 = max(320, canvas_height + 80)
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.52, 1_500)
        self._redraw_celdra_avatar_v50()
        self._remember_after_v49(220, self._start_shy_creep_v58)

    @staticmethod
    def _shy_progress_v63(fraction: float) -> float:
        fraction = max(0.0, min(1.0, fraction))
        if fraction < 0.20:
            return fraction / 0.20 * 0.18
        if fraction < 0.30:
            return 0.18
        if fraction < 0.70:
            return 0.18 + ((fraction - 0.30) / 0.40) * 0.47
        if fraction < 0.79:
            return 0.65
        return 0.65 + ((fraction - 0.79) / 0.21) * 0.35

    def _start_shy_creep_v58(self) -> None:
        if self._celdra_creep_after_v58 is not None:
            try:
                self.after_cancel(self._celdra_creep_after_v58)
            except tk.TclError:
                pass
        start = max(1, self._celdra_external_offset_y_v58)
        started = time.monotonic()
        duration_ms = 12_000

        def tick() -> None:
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / duration_ms)
            progress = self._shy_progress_v63(fraction)
            self._celdra_external_offset_y_v58 = round(start * (1.0 - progress))
            self._redraw_celdra_avatar_v50()
            if fraction < 1.0:
                self._celdra_creep_after_v58 = self.after(16, tick)
            else:
                self._celdra_creep_after_v58 = None

        tick()

    def _takeover_confused_v58(self) -> None:
        self._load_takeover_reaction_v58("confused")
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.52, 600)
        self._show_speech_bubble_v58("Well can you?")

    def _takeover_console_return_v58(self) -> None:
        self._hide_speech_bubble_v58()
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.38, 1_050)
        self._remember_after_v49(
            1_050,
            lambda: self._append_console_v49(
                "[BRAIN] THEY CAN'T TYPE OR TALK BACK, DUMMY"
            ),
        )
        self._remember_after_v49(
            1_850,
            lambda: self._append_console_v49(
                "[BRAIN] LOOKING GOOD THO, GIRL. LIKE I SAID, KILLING IT!"
            ),
        )
        self._remember_after_v49(2_050, self._scroll_all_text_v58)

    def _takeover_wink_v58(self) -> None:
        self._load_takeover_reaction_v58("wink")
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.68, 1_100)
        name = self._celdra_user_name_v58 or "noname"
        self._remember_after_v49(
            1_150,
            lambda: self._show_speech_bubble_v58(
                "Alright, Operation Dragonegg is a go!\n"
                f"Like I said, my name is Celdra. Nice to meet you, {name}."
            ),
        )

    # ------------------------------------------------------------------
    # Test lab replacements.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        controls = self._find_test_section_v60(
            self.tabs.get("Celdra Test"),
            "Script and avatar tests",
        ) if self.tabs.get("Celdra Test") is not None else None
        if controls is None:
            return
        old = "Production egg / static / smoke"
        new = "Production egg / energy / GIF"
        self._celdra_preview_map_v60.pop(old, None)
        self._celdra_preview_map_v60[new] = "production_energy"
        values = tuple(
            new if value == old else value
            for value in (
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
        )
        if self._celdra_preview_choice_v60 is not None:
            self._celdra_preview_choice_v60.set(new)
        for widget in self._walk_widgets_v61(controls):
            if isinstance(widget, ttk.Combobox):
                try:
                    if str(widget.cget("textvariable")) == str(
                        self._celdra_preview_choice_v60
                    ):
                        widget.configure(values=values)
                except tk.TclError:
                    pass

    def _play_preview_v60(self) -> None:
        choice = (
            self._celdra_preview_choice_v60.get()
            if self._celdra_preview_choice_v60 is not None
            else ""
        )
        if self._celdra_preview_map_v60.get(choice) == "production_energy":
            self._test_production_energy_v63()
            return
        super()._play_preview_v60()

    def _test_production_energy_v63(self) -> None:
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._celdra_timeline_speed_v51 = 1.0
        self._celdra_session_active_v49 = True
        self._set_avatar_phase_v51("egg_wait")
        self._show_avatar_v51()
        self._remember_after_v49(1_100, lambda: self._set_egg_glitch_v61(1))
        self._remember_after_v49(2_100, lambda: self._set_egg_glitch_v61(2))
        self._remember_after_v49(3_100, lambda: self._set_egg_glitch_v61(3))
        self._remember_after_v49(4_100, lambda: self._set_egg_glitch_v61(4))
        self._remember_after_v49(5_400, self._start_energy_hatch_v63)
        self._remember_after_v49(
            20_000,
            lambda: (
                self._stop_energy_hatch_v63(clear_avatar=True),
                self._hide_avatar_v51(),
            ),
        )


def main() -> int:
    app = PublicFragmenterAppV63()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

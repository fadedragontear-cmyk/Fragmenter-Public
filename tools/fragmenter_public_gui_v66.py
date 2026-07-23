#!/usr/bin/env python3
"""V66: thought pulse, harder textual corruption, cursor drama, and reveal polish."""
from __future__ import annotations

import math
import time
import tkinter as tk
from typing import Any

from celdra_startup_timeline_v7 import FIRST_RUN_AFTER_CCSF, NAME_QUESTION, TimelineEvent
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v64 import GLITCH_BINARY, GLITCH_TERMS
from fragmenter_public_gui_v65 import PublicFragmenterAppV65


class PublicFragmenterAppV66(PublicFragmenterAppV65):
    """Push the first-run presentation deeper into unstable .hack-style theater."""

    THOUGHT_PULSE_STEPS = 38

    def __init__(self) -> None:
        self._celdra_thought_pulse_active_v66 = False
        self._celdra_thought_pulse_step_v66 = 0
        self._celdra_thought_pulse_after_v66: str | None = None
        self._celdra_console_shake_after_v66: str | None = None
        self._celdra_type_after_v66: str | None = None
        self._celdra_type_queue_v66: list[tuple[str, int]] = []
        self._celdra_type_active_v66 = False
        self._celdra_chat_normal_colors_v66: tuple[str, str] | None = None
        self._celdra_chat_frame_normal_v66: str | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Maximum Corruption Presentation")

    # ------------------------------------------------------------------
    # V7 script and event hooks.
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
        if (
            event.action == "console"
            and event.speaker == "BRAIN"
            and event.text == "I THINK THEREFORE I CAN"
        ):
            super()._emit_timeline_event_v51(event)
            self._start_thought_pulse_v66()
            return

        if event.action == "chat":
            text = event.text
            if text.casefold().startswith("oof, extracting ccsf assets"):
                self._restore_post_energy_console_v66()
                text = self._ccsf_status_dialogue_v64()
            blinks = 8 if text == NAME_QUESTION else 3
            self._queue_typewriter_chat_v66(f"Celdra> {text}", blinks=blinks)
            return

        super()._emit_timeline_event_v51(event)

    # ------------------------------------------------------------------
    # "I THINK THEREFORE I CAN" light pulse, console impact, and transition.
    # ------------------------------------------------------------------
    def _start_thought_pulse_v66(self) -> None:
        self._cancel_thought_pulse_v66()
        self._celdra_thought_pulse_active_v66 = True
        self._celdra_thought_pulse_step_v66 = 0
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.17, 520)
        self._remember_after_v49(420, self._start_console_shake_v66)
        self._tick_thought_pulse_v66()

    def _tick_thought_pulse_v66(self) -> None:
        self._celdra_thought_pulse_after_v66 = None
        if not self._celdra_thought_pulse_active_v66:
            return
        step = self._celdra_thought_pulse_step_v66
        if step == 13:
            self._set_egg_glitch_v61(1)
        self._redraw_celdra_avatar_v50()
        self._celdra_thought_pulse_step_v66 += 1
        if self._celdra_thought_pulse_step_v66 >= self.THOUGHT_PULSE_STEPS:
            self._celdra_thought_pulse_active_v66 = False
            self._redraw_celdra_avatar_v50()
            return
        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        interval = max(12, round(58 * speed))
        self._celdra_thought_pulse_after_v66 = self.after(
            interval,
            self._tick_thought_pulse_v66,
        )

    def _cancel_thought_pulse_v66(self) -> None:
        if self._celdra_thought_pulse_after_v66 is not None:
            try:
                self.after_cancel(self._celdra_thought_pulse_after_v66)
            except tk.TclError:
                pass
            self._celdra_thought_pulse_after_v66 = None
        if self._celdra_console_shake_after_v66 is not None:
            try:
                self.after_cancel(self._celdra_console_shake_after_v66)
            except tk.TclError:
                pass
            self._celdra_console_shake_after_v66 = None
        self._celdra_thought_pulse_active_v66 = False

    def _start_console_shake_v66(self) -> None:
        pane = self.celdra_visual_split_v50
        if pane is None:
            return
        offsets = (0, 13, -11, 9, -7, 6, -4, 3, -2, 0)
        index = 0

        def tick() -> None:
            nonlocal index
            self._celdra_console_shake_after_v66 = None
            try:
                width = max(1, pane.winfo_width())
                pane.sashpos(0, max(18, int(width * 0.17) + offsets[index]))
            except (AttributeError, tk.TclError):
                return
            index += 1
            if index < len(offsets):
                speed = max(0.01, float(self._celdra_timeline_speed_v51))
                self._celdra_console_shake_after_v66 = self.after(
                    max(12, round(48 * speed)),
                    tick,
                )
            else:
                self.after_idle(self._scroll_all_text_v58)

        tick()

    def _draw_thought_pulse_v66(
        self,
        canvas: tk.Canvas,
        width: int,
        height: int,
    ) -> None:
        step = self._celdra_thought_pulse_step_v66
        half = self.THOUGHT_PULSE_STEPS / 2.0
        strength = 1.0 - min(1.0, abs(step - half) / half)
        cx = width // 2
        cy = height // 2 + 16
        stipple = "gray12" if strength < 0.45 else "gray25"
        for layer in range(4):
            margin_x = max(0, int((1.0 - strength) * width * 0.32) - layer * 15)
            margin_y = max(43, int((1.0 - strength) * height * 0.25) - layer * 11)
            try:
                canvas.create_rectangle(
                    margin_x,
                    margin_y,
                    width - margin_x,
                    height - margin_y,
                    outline=("#78b9ea", "#a9dcff", "#d9f1ff", "#b58cff")[layer],
                    width=1 + layer % 2,
                    stipple=stipple,
                    tags="v66_thought_pulse",
                )
            except tk.TclError:
                canvas.create_rectangle(
                    margin_x,
                    margin_y,
                    width - margin_x,
                    height - margin_y,
                    outline="#a9dcff",
                    width=1,
                    tags="v66_thought_pulse",
                )
        for index in range(10):
            angle = math.radians(index * 36 + step * 8)
            inner = 35 + strength * 28
            outer = inner + 30 + strength * 85
            canvas.create_line(
                cx + math.cos(angle) * inner,
                cy + math.sin(angle) * inner * 0.72,
                cx + math.cos(angle) * outer,
                cy + math.sin(angle) * outer * 0.72,
                fill="#d9f1ff" if index % 2 else "#78b9ea",
                width=1 + index % 3,
                dash=(2, 5),
                tags="v66_thought_pulse",
            )
        if step >= 10:
            value = "I_TH1NK//THEREF0RE//I_C4N"
            canvas.create_text(
                cx,
                max(54, cy - 112),
                text=value[: min(len(value), 6 + (step - 10) * 2)],
                anchor="center",
                fill="#d9f1ff",
                font=("Consolas", 11, "bold"),
                tags="v66_thought_pulse",
            )

    # ------------------------------------------------------------------
    # Transparent, stylized, text-only corruption behind the shell.
    # ------------------------------------------------------------------
    @staticmethod
    def _corruption_value_v66(term: str, phase: int, slot: int, level: int) -> str:
        if slot % 5 == 0:
            binary = GLITCH_BINARY[term].replace(" ", "")
            shift = (phase * 3 + slot * 11) % max(1, len(binary))
            return (binary[shift:] + binary[:shift])[: 18 + level * 8]
        if slot % 5 == 1:
            return f"{term[: max(1, len(term) - level)]}//{phase:02X}{slot:02X}"
        if slot % 5 == 2:
            return term[::-1]
        if slot % 5 == 3:
            return "".join(
                character if (index + phase + slot) % (4 - min(2, level)) else "01?ΔΞ/"[
                    (phase + index + slot) % 6
                ]
                for index, character in enumerate(term)
            )
        return f"<{term}>::{(phase * 17 + slot * 31) & 0xFF:02X}"

    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        level = self._celdra_glitch_level_v61
        if level <= 0:
            return
        phase = self._celdra_glitch_phase_v61
        tag = "v66_text_corruption"
        colors = (
            "#31536f",
            "#4b466d",
            "#365e74",
            "#594b78",
            "#436b7d",
            "#625285",
        )
        stipples = ("gray12", "gray25", "gray12", "gray50")
        density = 10 + level * 8

        for slot in range(density):
            term = GLITCH_TERMS[(phase // 2 + slot * 3 + level) % len(GLITCH_TERMS)]
            value = self._corruption_value_v66(term, phase, slot, level)
            x = 14 + ((slot * 83 + phase * (7 + slot % 5)) % max(30, width - 28))
            y = 52 + ((slot * 59 + phase * (3 + slot % 7)) % max(50, height - 96))
            angle = (-18, -11, -6, 0, 7, 13, 19)[(slot + phase) % 7]
            kwargs: dict[str, Any] = {
                "text": value,
                "anchor": "center",
                "fill": colors[(slot + phase) % len(colors)],
                "font": (
                    "Consolas",
                    7 + ((slot * 3 + level + phase) % (5 + level)),
                    "bold" if (slot + phase) % 4 == 0 else "normal",
                ),
                "stipple": stipples[(slot + level) % len(stipples)],
                "tags": tag,
            }
            try:
                canvas.create_text(x, y, angle=angle, **kwargs)
            except tk.TclError:
                kwargs.pop("stipple", None)
                try:
                    canvas.create_text(x, y, angle=angle, **kwargs)
                except tk.TclError:
                    canvas.create_text(x, y, **kwargs)

        # Large identity ghosts mutate slowly underneath the egg.
        for ghost in range(2 + level):
            term = GLITCH_TERMS[(phase // 5 + ghost * 2) % len(GLITCH_TERMS)]
            value = self._mutated_term_v64(term, phase, ghost + 19, level)
            x = width * (0.18 + ((ghost * 29 + phase) % 64) / 100.0)
            y = height * (0.20 + ((ghost * 23 + phase * 2) % 63) / 100.0)
            try:
                canvas.create_text(
                    x,
                    y,
                    text=value,
                    anchor="center",
                    angle=(-12 + ghost * 9),
                    fill=colors[(phase + ghost * 2) % len(colors)],
                    font=("Consolas", 16 + level * 3 + ghost * 2, "bold"),
                    stipple="gray12",
                    tags=tag,
                )
            except tk.TclError:
                canvas.create_text(
                    x,
                    y,
                    text=value,
                    anchor="center",
                    fill=colors[(phase + ghost * 2) % len(colors)],
                    font=("Consolas", 16 + level * 3 + ghost * 2, "bold"),
                    tags=tag,
                )

        # Sparse diagonal signal traces preserve depth without covering the shell.
        for trace in range(2 + level):
            y = 55 + ((trace * 97 + phase * 11) % max(60, height - 100))
            canvas.create_line(
                0,
                y,
                width,
                y - 18 - trace * 3,
                fill=colors[(trace + phase) % len(colors)],
                width=1,
                dash=(1 + trace % 3, 12 - min(5, level)),
                tags=tag,
            )
        try:
            canvas.tag_lower(tag)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Less circular energy: asymmetric lobes, torn wavefronts, and shards.
    # ------------------------------------------------------------------
    def _draw_energy_wave_v63(self, canvas: tk.Canvas, width: int, height: int) -> None:
        step = self._celdra_energy_step_v63
        if step >= 48:
            return
        cx = width // 2
        cy = height // 2 + 18
        charge = min(1.0, step / 34.0)
        burst = max(0.0, (step - 14) / 31.0)
        colors = ("#16375f", "#2f6fa5", "#78b9ea", "#a9dcff", "#d9f1ff", "#b58cff")

        # Offset organic light lobes replace the former solid circular core.
        for layer in range(7):
            points: list[float] = []
            base = 18 + charge * 48 + burst * 58 + layer * 10
            for point in range(28):
                angle = math.radians(point * (360 / 28) + step * (1.4 + layer * 0.11))
                distortion = 1.0 + 0.24 * math.sin(point * 2.7 + step * 0.31 + layer)
                distortion += 0.13 * math.sin(point * 5.1 - step * 0.19)
                radius = base * distortion
                x_bias = math.sin(step * 0.17 + layer) * (8 + layer * 2)
                y_bias = math.cos(step * 0.13 + layer * 0.7) * (5 + layer)
                points.extend(
                    (
                        cx + x_bias + math.cos(angle) * radius,
                        cy + y_bias + math.sin(angle) * radius * (0.62 + layer * 0.025),
                    )
                )
            kwargs: dict[str, Any] = {
                "fill": colors[(layer + step // 4) % len(colors)],
                "outline": "",
                "smooth": True,
                "splinesteps": 20,
                "stipple": ("gray12", "gray12", "gray25", "gray12", "gray25", "gray50", "gray12")[layer],
                "tags": "v66_energy",
            }
            try:
                canvas.create_polygon(points, **kwargs)
            except tk.TclError:
                kwargs.pop("stipple", None)
                canvas.create_polygon(points, **kwargs)

        # Jagged, incomplete wavefronts break the radial symmetry.
        for wave in range(6):
            points = []
            base = 45 + wave * 31 + step * (1.8 + wave * 0.34)
            start = (wave * 43 + step * 6) % 360
            span = 105 + ((wave * 37 + step * 5) % 150)
            for sample in range(24):
                angle = math.radians(start + span * sample / 23.0)
                radius = base + math.sin(sample * 1.8 + step * 0.4) * (7 + wave * 2)
                points.extend(
                    (
                        cx + math.cos(angle) * radius,
                        cy + math.sin(angle) * radius * (0.67 + wave * 0.025),
                    )
                )
            canvas.create_line(
                points,
                fill=colors[(wave + step) % len(colors)],
                width=1 + (wave + step) % 4,
                dash=(2 + wave % 4, 4 + (step + wave) % 8),
                tags="v66_energy",
            )

        # Tapered beam triangles and shard streaks fill the viewport without a disc.
        beam_count = 24
        maximum = max(width, height) * (0.40 + burst * 0.72)
        for index in range(beam_count):
            angle = math.radians(index * (360 / beam_count) + step * (3.1 + index % 3))
            inner = 16 + (index % 5) * 6
            outer = maximum * (0.55 + ((index * 19 + step * 11) % 44) / 100.0)
            spread = 0.012 + (index % 4) * 0.004
            points = (
                cx + math.cos(angle - spread) * inner,
                cy + math.sin(angle - spread) * inner * 0.75,
                cx + math.cos(angle) * outer,
                cy + math.sin(angle) * outer * 0.75,
                cx + math.cos(angle + spread) * inner,
                cy + math.sin(angle + spread) * inner * 0.75,
            )
            canvas.create_polygon(
                points,
                fill=colors[(index + step) % len(colors)],
                outline="",
                tags="v66_energy",
            )

        for index in range(62 + int(charge * 74)):
            angle = math.radians((index * 137 + step * (11 + index % 5)) % 360)
            distance = 24 + ((index * 47 + step * 23) % max(40, int(maximum)))
            x = cx + math.cos(angle) * distance
            y = cy + math.sin(angle) * distance * 0.74
            length = 3 + ((index + step) % 11)
            canvas.create_line(
                x,
                y,
                x + math.cos(angle) * length,
                y + math.sin(angle) * length * 0.72,
                fill=colors[(index * 2 + step) % len(colors)],
                width=1 + (index + step) % 3,
                tags="v66_energy",
            )

    def _redraw_celdra_avatar_v50(self) -> None:
        super()._redraw_celdra_avatar_v50()
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        if self._celdra_thought_pulse_active_v66:
            self._draw_thought_pulse_v66(
                canvas,
                max(1, canvas.winfo_width()),
                max(1, canvas.winfo_height()),
            )

    # ------------------------------------------------------------------
    # Flash both console surfaces during containment failure/explosion.
    # ------------------------------------------------------------------
    def _start_console_alarm_v64(self) -> None:
        chat = self._celdra_chat_v49
        frame = self._celdra_stage_chat_frame_v54
        if chat is not None and self._celdra_chat_normal_colors_v66 is None:
            try:
                self._celdra_chat_normal_colors_v66 = (
                    str(chat.cget("background")),
                    str(chat.cget("foreground")),
                )
            except tk.TclError:
                self._celdra_chat_normal_colors_v66 = ("#101a28", "#e2f5ff")
        if frame is not None and self._celdra_chat_frame_normal_v66 is None:
            try:
                self._celdra_chat_frame_normal_v66 = str(frame.cget("background"))
            except tk.TclError:
                self._celdra_chat_frame_normal_v66 = "#101a28"
        super()._start_console_alarm_v64()

    def _tick_console_alarm_v64(self) -> None:
        self._celdra_console_alarm_after_v64 = None
        console = self._celdra_console_v49
        chat = self._celdra_chat_v49
        frame = self._celdra_stage_chat_frame_v54
        if console is None:
            return
        palettes = (
            ("#18070b", "#ff6670"),
            ("#071812", "#62f39a"),
            ("#071426", "#a9dcff"),
            ("#201126", "#d986ff"),
            ("#261b08", "#ffe16a"),
        )
        background, foreground = palettes[
            self._celdra_console_alarm_phase_v64 % len(palettes)
        ]
        self._celdra_console_alarm_phase_v64 += 1
        try:
            console.configure(background=background, foreground=foreground)
            if chat is not None:
                chat.configure(background=background, foreground=foreground)
            if frame is not None:
                frame.configure(background=background)
        except tk.TclError:
            return
        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        self._celdra_console_alarm_after_v64 = self.after(
            max(28, round(82 * speed)),
            self._tick_console_alarm_v64,
        )

    def _stop_console_alarm_v64(self) -> None:
        super()._stop_console_alarm_v64()
        chat = self._celdra_chat_v49
        frame = self._celdra_stage_chat_frame_v54
        if chat is not None and self._celdra_chat_normal_colors_v66 is not None:
            try:
                chat.configure(
                    background=self._celdra_chat_normal_colors_v66[0],
                    foreground=self._celdra_chat_normal_colors_v66[1],
                )
            except tk.TclError:
                pass
        if frame is not None and self._celdra_chat_frame_normal_v66 is not None:
            try:
                frame.configure(background=self._celdra_chat_frame_normal_v66)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Faster typewriter plus an old-school blinking underscore cursor.
    # ------------------------------------------------------------------
    def _queue_typewriter_chat_v66(self, text: str, *, blinks: int = 3) -> None:
        self._celdra_type_queue_v66.append((str(text or ""), max(1, int(blinks))))
        if not self._celdra_type_active_v66:
            self._start_next_typewriter_v66()

    def _start_next_typewriter_v66(self) -> None:
        if not self._celdra_type_queue_v66:
            self._celdra_type_active_v66 = False
            return
        widget = self._celdra_chat_v49
        if widget is None:
            self._celdra_type_queue_v66.clear()
            self._celdra_type_active_v66 = False
            return
        self._celdra_type_active_v66 = True
        message, blink_count = self._celdra_type_queue_v66.pop(0)
        index = 0

        def remove_cursor() -> None:
            try:
                ranges = widget.tag_ranges("v66_cursor")
                if len(ranges) >= 2:
                    widget.delete(ranges[0], ranges[1])
                widget.tag_remove("v66_cursor", "1.0", "end")
            except tk.TclError:
                pass

        def finish_message() -> None:
            remove_cursor()
            try:
                widget.configure(state="normal")
                widget.insert("end-1c", "\n\n")
                widget.see("end")
                widget.configure(state="disabled")
            except tk.TclError:
                self._celdra_type_active_v66 = False
                return
            self._celdra_type_active_v66 = False
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            self._celdra_type_after_v66 = self.after(
                max(20, round(120 * speed)),
                self._start_next_typewriter_v66,
            )

        def blink(toggle: int = 0) -> None:
            self._celdra_type_after_v66 = None
            visible = toggle % 2 == 0
            remove_cursor()
            if visible:
                try:
                    widget.configure(state="normal")
                    widget.insert("end-1c", "_", "v66_cursor")
                    widget.tag_configure(
                        "v66_cursor",
                        foreground="#a9dcff",
                        font=("Consolas", 11, "bold"),
                    )
                    widget.see("end")
                    widget.configure(state="disabled")
                except tk.TclError:
                    self._celdra_type_active_v66 = False
                    return
            if toggle + 1 >= blink_count * 2:
                finish_message()
                return
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            self._celdra_type_after_v66 = self.after(
                max(70, round(220 * speed)),
                lambda: blink(toggle + 1),
            )

        def type_tick() -> None:
            nonlocal index
            self._celdra_type_after_v66 = None
            if index >= len(message):
                blink(0)
                return
            character = message[index]
            index += 1
            try:
                widget.configure(state="normal")
                widget.insert("end-1c", character)
                widget.see("end")
                widget.configure(state="disabled")
            except tk.TclError:
                self._celdra_type_active_v66 = False
                return
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            base = max(4, round(22 * speed))
            pause = max(5, round(72 * speed)) if character in ".!?" else 0
            self._celdra_type_after_v66 = self.after(base + pause, type_tick)

        type_tick()

    def _cancel_typewriter_v64(self) -> None:
        if self._celdra_type_after_v66 is not None:
            try:
                self.after_cancel(self._celdra_type_after_v66)
            except tk.TclError:
                pass
            self._celdra_type_after_v66 = None
        self._celdra_type_queue_v66.clear()
        self._celdra_type_active_v66 = False
        widget = self._celdra_chat_v49
        if widget is not None:
            try:
                ranges = widget.tag_ranges("v66_cursor")
                if len(ranges) >= 2:
                    widget.configure(state="normal")
                    widget.delete(ranges[0], ranges[1])
                    widget.configure(state="disabled")
            except tk.TclError:
                pass
        super()._cancel_typewriter_v64()

    # ------------------------------------------------------------------
    # Lower, smaller Shy crop and explicit post-energy console restoration.
    # ------------------------------------------------------------------
    def _scaled_manifest_reaction_v60(
        self,
        name: str,
        *,
        quiet: bool,
    ) -> tuple[tk.PhotoImage, tk.PhotoImage, tk.PhotoImage, dict[str, Any]] | None:
        loaded = super()._scaled_manifest_reaction_v60(name, quiet=quiet)
        if loaded is None:
            return None
        source, cropped, display, row = loaded
        if str(name or "").casefold() == "shy":
            display = self._fit_photo_v50(cropped, 172, 220)
        return source, cropped, display, row

    def _begin_shy_reveal_v64(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        canvas_width = canvas.winfo_width() if canvas is not None else 520
        canvas_height = canvas.winfo_height() if canvas is not None else 420
        self._celdra_external_offset_x_v65 = max(38, min(82, canvas_width // 9))
        if not self._load_takeover_reaction_v58("shy"):
            return
        # This crop ends high at the torso, so it deliberately rests lower.
        self._celdra_shy_rest_offset_v64 = max(105, min(145, canvas_height // 3))
        self._celdra_external_offset_y_v58 = max(350, canvas_height + 110)
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.50, 1_650)
        self._redraw_celdra_avatar_v50()
        self._remember_after_v49(260, self._start_shy_creep_v58)

    def _restore_post_energy_console_v66(self) -> None:
        self._stop_console_alarm_v64()
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.34, 1_000)
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set("CONSOLE CHANNEL RESTORED • CCSF STATUS CHECK")
        for delay in (40, 420, 1_050):
            self.after(delay, self._scroll_all_text_v58)

    # ------------------------------------------------------------------
    # Cleanup.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._cancel_thought_pulse_v66()
        super()._prepare_first_run_surface_v51()

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_thought_pulse_v66()
        super()._cancel_celdra_cues_v49()

    def _show_timeline_failure_v51(self) -> None:
        self._cancel_thought_pulse_v66()
        super()._show_timeline_failure_v51()


def main() -> int:
    app = PublicFragmenterAppV66()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

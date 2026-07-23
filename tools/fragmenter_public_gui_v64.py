#!/usr/bin/env python3
"""V64: calm egg idle, textual corruption, typewriter chat, and safer avatar staging."""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any

from celdra_evolution_pixel_v4 import EGG_LOOP
from celdra_startup_timeline_v6 import TimelineEvent
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v63 import PublicFragmenterAppV63


CALM_EGG_LOOP = tuple(
    frame
    for frame in EGG_LOOP
    if not any(token in frame.name for token in ("bump_left", "bump_right", "glow"))
)

GLITCH_TERMS = (
    "AURA",
    "INFECTION",
    "MUTATION",
    "QUARANTINE",
    "SERENIAL",
    "CELDRA",
    "FRAGMENT",
    "CCSF",
)
GLITCH_BINARY = {
    term: " ".join(f"{ord(character):08b}" for character in term)
    for term in GLITCH_TERMS
}
SEAL_VARIANTS = (
    "ACTIVE",
    "A<C>T!V/E",
    "AC7IVE",
    "A(T)IV3",
    "AΞTIVE",
    "A_C_T_I_V_E",
    "ACT1VE",
)


class PublicFragmenterAppV64(PublicFragmenterAppV63):
    """Polish the canonical Celdra presentation without reviving Gremlin startup."""

    def __init__(self) -> None:
        self._celdra_seal_after_v64: str | None = None
        self._celdra_seal_phase_v64 = 0
        self._celdra_console_alarm_after_v64: str | None = None
        self._celdra_console_alarm_phase_v64 = 0
        self._celdra_console_normal_colors_v64: tuple[str, str] | None = None
        self._celdra_type_after_v64: str | None = None
        self._celdra_type_queue_v64: list[str] = []
        self._celdra_type_active_v64 = False
        self._celdra_ccsf_state_v64 = "waiting"
        self._celdra_shy_rest_offset_v64 = 62
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Textual Corruption Presentation")

    # ------------------------------------------------------------------
    # Calm production egg: breathe and settle, but never flash while idle.
    # ------------------------------------------------------------------
    def _set_avatar_phase_v51(self, phase: str) -> None:
        phase = str(phase or "egg_wait").casefold()
        if phase != "egg_wait":
            super()._set_avatar_phase_v51(phase)
            return
        self._celdra_stage_phase_v54 = "egg_wait"
        self._play_pixel_sequence_v50(CALM_EGG_LOOP or EGG_LOOP, loop=True)
        update_detail = getattr(self, "_update_evolution_detail_v60", None)
        if callable(update_detail):
            update_detail("egg_wait", CALM_EGG_LOOP or EGG_LOOP)
        if self._celdra_stage_avatar_visible_v54 and not self._celdra_takeover_active_v58:
            self._animate_stage_fraction_v54(0.20, 650)

    # ------------------------------------------------------------------
    # Dynamic hacked Tavern Seal in the real system console.
    # ------------------------------------------------------------------
    def _emit_timeline_event_v51(self, event: TimelineEvent) -> None:
        if event.action == "ascii":
            self._append_dynamic_dragonegg_ascii_v64(event.text, event.speaker)
            return
        if event.action == "chat":
            text = event.text
            if text.casefold().startswith("oof, extracting ccsf assets"):
                text = self._ccsf_status_dialogue_v64()
            self._queue_typewriter_chat_v64(f"Celdra> {text}")
            return
        if event.action == "hide_avatar":
            self._stop_tavern_seal_v64()
            self._stop_console_alarm_v64()
        super()._emit_timeline_event_v51(event)

    def _append_dynamic_dragonegg_ascii_v64(self, text: str, speaker: str) -> None:
        self._stop_tavern_seal_v64()
        lines: list[str] = []
        for line in str(text or "").splitlines():
            if "TAVERN SEAL:" in line:
                indentation = line[: len(line) - len(line.lstrip())]
                lines.append(f"{indentation}[TAVERN SEAL: ACTIVE]")
            else:
                lines.append(line)
        self._append_console_v49(f"[{speaker}]\n" + "\n".join(lines))
        self._tick_tavern_seal_v64()

    def _tick_tavern_seal_v64(self) -> None:
        self._celdra_seal_after_v64 = None
        widget = self._celdra_console_v49
        if widget is None or self._celdra_energy_active_v63:
            return
        try:
            start = widget.search("[TAVERN SEAL:", "1.0", "end")
        except tk.TclError:
            return
        if not start:
            return
        variant = SEAL_VARIANTS[self._celdra_seal_phase_v64 % len(SEAL_VARIANTS)]
        color = "#48d76d" if self._celdra_seal_phase_v64 % 2 == 0 else "#ff5a67"
        self._celdra_seal_phase_v64 += 1
        try:
            widget.configure(state="normal")
            widget.delete(start, f"{start} lineend")
            widget.insert(start, f"[TAVERN SEAL: {variant}]", "v64_tavern_seal")
            try:
                font = (
                    "Consolas",
                    10,
                    "bold overstrike" if self._celdra_seal_phase_v64 % 4 == 0 else "bold",
                )
                widget.tag_configure("v64_tavern_seal", foreground=color, font=font)
            except tk.TclError:
                widget.tag_configure("v64_tavern_seal", foreground=color)
            widget.see("end")
            widget.configure(state="disabled")
        except tk.TclError:
            try:
                widget.configure(state="disabled")
            except tk.TclError:
                pass
            return
        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        interval = max(45, round(430 * speed))
        self._celdra_seal_after_v64 = self.after(interval, self._tick_tavern_seal_v64)

    def _stop_tavern_seal_v64(self) -> None:
        if self._celdra_seal_after_v64 is not None:
            try:
                self.after_cancel(self._celdra_seal_after_v64)
            except tk.TclError:
                pass
            self._celdra_seal_after_v64 = None

    # ------------------------------------------------------------------
    # Background-only textual corruption. No displaced blocks cover the egg.
    # ------------------------------------------------------------------
    @staticmethod
    def _mutated_term_v64(term: str, phase: int, slot: int, level: int) -> str:
        characters = list(term)
        replacements = "01/\\#?ΔΞ*"
        count = max(1, min(level, max(1, len(characters) // 3)))
        for mutation in range(count):
            index = (phase * (slot + 3) + slot * 5 + mutation * 7) % len(characters)
            characters[index] = replacements[(phase + slot + mutation * 2) % len(replacements)]
        return "".join(characters)

    @staticmethod
    def _create_faded_text_v64(canvas: tk.Canvas, *args: Any, **kwargs: Any) -> None:
        try:
            canvas.create_text(*args, **kwargs)
        except tk.TclError:
            kwargs.pop("stipple", None)
            canvas.create_text(*args, **kwargs)

    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        level = self._celdra_glitch_level_v61
        if level <= 0:
            return
        phase = self._celdra_glitch_phase_v61
        colors = ("#426d91", "#6d5c91", "#4e819c", "#76659d", "#6a8fab")
        tag = "v64_glitch_bg"

        # Dim broken orbits are lowered behind the egg after creation.
        cx = width // 2
        cy = height // 2 + 18
        for ring in range(1 + level):
            radius_x = 70 + ring * 31 + ((phase * (ring + 2)) % 15)
            radius_y = 54 + ring * 19 + ((phase * (ring + 5)) % 11)
            canvas.create_arc(
                cx - radius_x,
                cy - radius_y,
                cx + radius_x,
                cy + radius_y,
                start=(phase * (13 + ring * 5) + ring * 77) % 360,
                extent=22 + ((phase * 9 + ring * 31) % 75),
                style="arc",
                outline=colors[(phase + ring) % len(colors)],
                width=1,
                dash=(2 + ring % 3, 7 + level),
                tags=tag,
            )

        density = 4 + level * 4
        for slot in range(density):
            term = GLITCH_TERMS[(phase // 3 + slot) % len(GLITCH_TERMS)]
            use_binary = slot % 3 == 2
            if use_binary:
                value = GLITCH_BINARY[term]
                if len(value) > 52:
                    value = value[:52] + "…"
            else:
                value = self._mutated_term_v64(term, phase, slot, level)
            left_side = slot % 2 == 0
            x = 12 + ((slot * 37 + phase * 3) % max(30, width // 4))
            if not left_side:
                x = width - x
            y = 52 + ((slot * 53 + phase * (2 + slot % 5)) % max(60, height - 105))
            self._create_faded_text_v64(
                canvas,
                x,
                y,
                text=value,
                anchor="w" if left_side else "e",
                fill=colors[(slot + phase) % len(colors)],
                font=("Consolas", 7 + (slot + level) % 3, "bold" if level >= 3 else "normal"),
                stipple="gray50" if level < 4 else "gray75",
                tags=tag,
            )

        # One large morphing identity word sits behind the shell.
        identity = GLITCH_TERMS[(phase // 5) % len(GLITCH_TERMS)]
        identity = self._mutated_term_v64(identity, phase, 11, level)
        self._create_faded_text_v64(
            canvas,
            cx,
            max(55, cy - 105 + (phase % 9) * 2),
            text=identity,
            anchor="center",
            fill=colors[(phase // 2) % len(colors)],
            font=("Consolas", 13 + level * 2, "bold"),
            stipple="gray25",
            tags=tag,
        )
        try:
            canvas.tag_lower(tag)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Diffuse energy burst and temporary full-width viewport takeover.
    # ------------------------------------------------------------------
    def _set_egg_glitch_v61(self, level: int) -> None:
        super()._set_egg_glitch_v61(level)
        if int(level) >= 4:
            self._start_console_alarm_v64()

    def _start_energy_hatch_v63(self) -> None:
        self._stop_tavern_seal_v64()
        self._start_console_alarm_v64()
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.985, 1_050)
        super()._start_energy_hatch_v63()

    @staticmethod
    def _stippled_oval_v64(canvas: tk.Canvas, coords: tuple[float, float, float, float], **kwargs: Any) -> None:
        try:
            canvas.create_oval(*coords, **kwargs)
        except tk.TclError:
            kwargs.pop("stipple", None)
            canvas.create_oval(*coords, **kwargs)

    def _draw_energy_wave_v63(self, canvas: tk.Canvas, width: int, height: int) -> None:
        step = self._celdra_energy_step_v63
        if step >= 48:
            return
        cx = width // 2
        cy = height // 2 + 18
        charge = min(1.0, step / 34.0)
        burst = max(0.0, (step - 16) / 30.0)
        colors = ("#16375f", "#2f6fa5", "#78b9ea", "#a9dcff", "#d9f1ff", "#b58cff")

        for ring in range(10):
            radius = 18 + ring * 18 + step * (2 + ring % 4)
            flatten = 0.68 + (ring % 3) * 0.09
            canvas.create_oval(
                cx - radius,
                cy - int(radius * flatten),
                cx + radius,
                cy + int(radius * flatten),
                outline=colors[(ring + step // 3) % len(colors)],
                width=1 + ((ring + step) % 3),
                dash=(2 + ring % 5, 5 + (step + ring) % 8),
                tags="v64_energy",
            )

        beam_count = 22
        max_radius = max(width, height) * (0.43 + burst * 0.62)
        for index in range(beam_count):
            angle = math.radians(index * (360 / beam_count) + step * (2.4 + index % 4))
            inner = 22 + (index % 5) * 5
            outer = max_radius * (0.58 + ((index * 19 + step * 7) % 42) / 100.0)
            canvas.create_line(
                cx + math.cos(angle) * inner,
                cy + math.sin(angle) * inner,
                cx + math.cos(angle) * outer,
                cy + math.sin(angle) * outer,
                fill=colors[(index + step) % len(colors)],
                width=1 + (index + step) % 3,
                tags="v64_energy",
            )

        particle_count = 48 + int(charge * 64)
        for index in range(particle_count):
            angle = math.radians((index * 137 + step * (8 + index % 7)) % 360)
            distance = 26 + ((index * 47 + step * 19) % max(38, int(max_radius)))
            x = cx + math.cos(angle) * distance
            y = cy + math.sin(angle) * distance * 0.76
            size = 1 + ((index + step) % 4)
            canvas.create_rectangle(
                x - size,
                y - size,
                x + size,
                y + size,
                fill=colors[(index * 2 + step) % len(colors)],
                outline="",
                tags="v64_energy",
            )

        # Layered stippled haze replaces the old hard solid-white circle.
        core = 15 + int(charge * 50) + int(burst * 45)
        haze_stipples = ("gray12", "gray12", "gray25", "gray25", "gray50")
        for layer, stipple in enumerate(haze_stipples):
            radius = core + (len(haze_stipples) - layer) * 10
            color = colors[(step // 4 + layer + 2) % len(colors)]
            self._stippled_oval_v64(
                canvas,
                (cx - radius, cy - radius, cx + radius, cy + radius),
                fill=color,
                outline="",
                stipple=stipple,
                tags="v64_energy",
            )
        canvas.create_oval(
            cx - core,
            cy - core,
            cx + core,
            cy + core,
            outline="#f2fbff",
            width=3,
            dash=(3, 5),
            tags="v64_energy",
        )

    def _begin_hatch_gif_v63(self) -> None:
        self._celdra_energy_gif_started_v63 = True
        frames = self._load_hatch_gif_v63()
        if not frames:
            self._append_console_v49(
                "[CORE] TAVERN BYPASS FAILED; WHITEOUT FALLBACK RETAINED"
            )
            self.celdra_current_pixel_v50 = None
            self.celdra_current_external_v50 = None
            return
        self._play_external_sequence_v50(frames)
        self._append_console_v49("[CORE] TAVERN BYPASS SUCCESSFUL... MORE OR LESS")

    # ------------------------------------------------------------------
    # Rapid console alarm near containment failure.
    # ------------------------------------------------------------------
    def _start_console_alarm_v64(self) -> None:
        widget = self._celdra_console_v49
        if widget is None or self._celdra_console_alarm_after_v64 is not None:
            return
        if self._celdra_console_normal_colors_v64 is None:
            try:
                self._celdra_console_normal_colors_v64 = (
                    str(widget.cget("background")),
                    str(widget.cget("foreground")),
                )
            except tk.TclError:
                self._celdra_console_normal_colors_v64 = ("#10151d", "#b9c8da")
        self._tick_console_alarm_v64()

    def _tick_console_alarm_v64(self) -> None:
        self._celdra_console_alarm_after_v64 = None
        widget = self._celdra_console_v49
        if widget is None:
            return
        palettes = (
            ("#18070b", "#ff6670"),
            ("#071812", "#62f39a"),
            ("#071426", "#a9dcff"),
            ("#201126", "#d986ff"),
        )
        background, foreground = palettes[self._celdra_console_alarm_phase_v64 % len(palettes)]
        self._celdra_console_alarm_phase_v64 += 1
        try:
            widget.configure(background=background, foreground=foreground)
        except tk.TclError:
            return
        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        interval = max(35, round(95 * speed))
        self._celdra_console_alarm_after_v64 = self.after(interval, self._tick_console_alarm_v64)

    def _stop_console_alarm_v64(self) -> None:
        if self._celdra_console_alarm_after_v64 is not None:
            try:
                self.after_cancel(self._celdra_console_alarm_after_v64)
            except tk.TclError:
                pass
            self._celdra_console_alarm_after_v64 = None
        widget = self._celdra_console_v49
        colors = self._celdra_console_normal_colors_v64
        if widget is not None and colors is not None:
            try:
                widget.configure(background=colors[0], foreground=colors[1])
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Typewriter conversational link and live CCSF status-aware dialogue.
    # ------------------------------------------------------------------
    def _handle_run_event(self, event: dict[str, Any]) -> None:
        super()._handle_run_event(event)
        if str(event.get("stage") or "") != "ccsf_extract":
            return
        kind = str(event.get("kind") or "")
        status = str(event.get("status") or "")
        if kind == "start":
            self._celdra_ccsf_state_v64 = "running"
        elif kind == "finish":
            self._celdra_ccsf_state_v64 = "failed" if status == "failed" else "complete"

    def _ccsf_status_dialogue_v64(self) -> str:
        if bool(getattr(self, "_celdra_test_mode_v58", False)):
            return "Oh, this is a test run. Hi Fade!"
        state = self._celdra_ccsf_state_v64
        if state == "running":
            return "Oof, extracting CCSF assets. This is gonna take a bit."
        if state == "complete":
            return "Oof, CCSF extraction is already complete. Okay, that's actually better."
        if state == "failed":
            return "Oof, CCSF extraction failed. That's a real problem, not presentation drama."
        return "Oof, checking the actual CCSF extraction status now."

    def _queue_typewriter_chat_v64(self, text: str) -> None:
        self._celdra_type_queue_v64.append(str(text or ""))
        if not self._celdra_type_active_v64:
            self._start_next_typewriter_v64()

    def _start_next_typewriter_v64(self) -> None:
        if not self._celdra_type_queue_v64:
            self._celdra_type_active_v64 = False
            return
        widget = self._celdra_chat_v49
        if widget is None:
            self._celdra_type_active_v64 = False
            self._celdra_type_queue_v64.clear()
            return
        self._celdra_type_active_v64 = True
        message = self._celdra_type_queue_v64.pop(0)
        index = 0

        def tick() -> None:
            nonlocal index
            self._celdra_type_after_v64 = None
            if index >= len(message):
                try:
                    widget.configure(state="normal")
                    widget.insert("end", "\n\n")
                    widget.see("end")
                    widget.configure(state="disabled")
                except tk.TclError:
                    pass
                self._celdra_type_active_v64 = False
                speed = max(0.01, float(self._celdra_timeline_speed_v51))
                self._celdra_type_after_v64 = self.after(
                    max(25, round(260 * speed)),
                    self._start_next_typewriter_v64,
                )
                return
            character = message[index]
            index += 1
            try:
                widget.configure(state="normal")
                widget.insert("end", character)
                widget.see("end")
                widget.configure(state="disabled")
            except tk.TclError:
                self._celdra_type_active_v64 = False
                return
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            base = max(5, round(34 * speed))
            punctuation = max(8, round(115 * speed)) if character in ".!?" else 0
            self._celdra_type_after_v64 = self.after(base + punctuation, tick)

        tick()

    def _cancel_typewriter_v64(self) -> None:
        if self._celdra_type_after_v64 is not None:
            try:
                self.after_cancel(self._celdra_type_after_v64)
            except tk.TclError:
                pass
            self._celdra_type_after_v64 = None
        self._celdra_type_active_v64 = False
        self._celdra_type_queue_v64.clear()

    # ------------------------------------------------------------------
    # Smaller classified portraits and reserved bubble headroom.
    # ------------------------------------------------------------------
    def _scaled_manifest_reaction_v60(
        self,
        name: str,
        *,
        quiet: bool,
    ) -> tuple[tk.PhotoImage, tk.PhotoImage, tk.PhotoImage, dict[str, Any]] | None:
        self._reload_manifest_emotes_v56()
        folded = str(name or "").casefold()
        row = self._celdra_manifest_emotes_v56.get(folded)
        if row is None:
            if not quiet:
                messagebox.showinfo("Celdra avatar", f"No classified emote named '{name}' was found.")
            return None
        source = self.celdra_asset_root_v50 / str(row.get("source") or "")
        if not source.is_file():
            if not quiet:
                messagebox.showerror("Celdra avatar", f"Missing source sheet:\n{source}")
            return None
        try:
            image = tk.PhotoImage(file=str(source))
            crop = row.get("crop") if isinstance(row.get("crop"), dict) else {}
            cropped = self._crop_photo_v52(
                image,
                {
                    "x": int(crop.get("x") or 0),
                    "y": int(crop.get("y") or 0),
                    "width": int(crop.get("width") or 1),
                    "height": int(crop.get("height") or 1),
                },
            )
            limits = {
                "shy": (190, 245),
                "neutral": (205, 258),
                "default": (205, 258),
            }
            maximum_width, maximum_height = limits.get(folded, (220, 275))
            display = self._fit_photo_v50(cropped, maximum_width, maximum_height)
        except (tk.TclError, OSError, ValueError) as exc:
            if quiet:
                self._append_console_v49(f"[CORE] CLASSIFIED REACTION LOAD FAILED: {exc}")
            else:
                messagebox.showerror("Celdra avatar", str(exc))
            return None
        return image, cropped, display, row

    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = self._celdra_speech_canvas_v63
        if bubble is None:
            return
        line_count = max(1, str(text).count("\n") + 1)
        height = 98 + max(0, line_count - 1) * 26
        bubble.place(relx=0.035, rely=0.025, anchor="nw", relwidth=0.52, height=height)
        bubble.update_idletasks()
        width = max(230, bubble.winfo_width())
        bubble.delete("all")
        self._rounded_polygon_v63(
            bubble,
            9,
            9,
            width - 8,
            height - 22,
            18,
            fill="#16375f",
            outline="",
        )
        bubble.create_polygon(
            width - 78,
            height - 27,
            width - 45,
            height - 27,
            width - 58,
            height - 3,
            fill="#16375f",
            outline="",
        )
        self._rounded_polygon_v63(
            bubble,
            4,
            4,
            width - 13,
            height - 27,
            18,
            fill="#f4fbff",
            outline="#78b9ea",
            width=3,
        )
        bubble.create_polygon(
            width - 86,
            height - 32,
            width - 53,
            height - 32,
            width - 66,
            height - 8,
            fill="#f4fbff",
            outline="#78b9ea",
            width=2,
        )
        bubble.create_text(
            23,
            20,
            text=text,
            anchor="nw",
            width=max(160, width - 50),
            fill="#071426",
            font=("Segoe UI", 10, "bold"),
            justify="left",
        )
        bubble.lift()

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
            self._celdra_stage_detail_v54.set("CONSOLE PRELOADED • COMPACT AVATAR WAITING")

        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.32, 1_400)
        self._append_console_v49("[CORE] DRAGONGIRL AVATAR CHANNEL PRELOADED")
        self._append_console_v49("[CORE] CONSOLE CHANNEL LOCKED AND READY")
        for delay in (80, 700, 1_500, 2_800, 4_000):
            self.after(delay, self._scroll_all_text_v58)

        # Five-second console prelude, twelve-second hesitant rise, then four seconds still.
        self._remember_after_v49(5_000, self._begin_shy_reveal_v64)
        self._remember_after_v49(
            21_500,
            lambda: self._show_speech_bubble_v58(
                "Test, Test, Check check can you hear me?"
            ),
        )
        self._remember_after_v49(26_500, self._takeover_confused_v58)
        self._remember_after_v49(30_500, self._takeover_console_return_v58)
        self._remember_after_v49(36_500, self._takeover_wink_v58)

    def _begin_shy_reveal_v64(self) -> None:
        if not self._load_takeover_reaction_v58("shy"):
            return
        canvas_height = (
            self.celdra_avatar_canvas_v50.winfo_height()
            if self.celdra_avatar_canvas_v50 is not None
            else 420
        )
        self._celdra_shy_rest_offset_v64 = max(46, min(72, canvas_height // 7))
        self._celdra_external_offset_y_v58 = max(330, canvas_height + 90)
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.50, 1_650)
        self._redraw_celdra_avatar_v50()
        self._remember_after_v49(260, self._start_shy_creep_v58)

    def _start_shy_creep_v58(self) -> None:
        if self._celdra_creep_after_v58 is not None:
            try:
                self.after_cancel(self._celdra_creep_after_v58)
            except tk.TclError:
                pass
        start = max(1, self._celdra_external_offset_y_v58)
        target = max(0, self._celdra_shy_rest_offset_v64)
        distance = max(1, start - target)
        started = time.monotonic()
        duration_ms = 12_000

        def tick() -> None:
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / duration_ms)
            progress = self._shy_progress_v63(fraction)
            self._celdra_external_offset_y_v58 = round(start - distance * progress)
            self._redraw_celdra_avatar_v50()
            if fraction < 1.0:
                self._celdra_creep_after_v58 = self.after(16, tick)
            else:
                self._celdra_external_offset_y_v58 = target
                self._celdra_creep_after_v58 = None
                self._redraw_celdra_avatar_v50()

        tick()

    def _takeover_confused_v58(self) -> None:
        self._load_takeover_reaction_v58("confused")
        self._celdra_external_offset_y_v58 = self._celdra_shy_rest_offset_v64
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.50, 650)
        self._show_speech_bubble_v58("Well can you?")

    def _takeover_wink_v58(self) -> None:
        self._load_takeover_reaction_v58("wink")
        self._celdra_external_offset_y_v58 = self._celdra_shy_rest_offset_v64
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.64, 1_100)
        name = self._celdra_user_name_v58 or "noname"
        self._remember_after_v49(
            1_150,
            lambda: self._show_speech_bubble_v58(
                "Alright, Operation Dragonegg is a go!\n"
                f"Like I said, my name is Celdra. Nice to meet you, {name}."
            ),
        )

    # ------------------------------------------------------------------
    # Cleanup across reruns, resets, and real pipeline failures.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._cancel_typewriter_v64()
        self._stop_tavern_seal_v64()
        self._stop_console_alarm_v64()
        self._celdra_ccsf_state_v64 = "waiting"
        super()._prepare_first_run_surface_v51()

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_typewriter_v64()
        self._stop_tavern_seal_v64()
        self._stop_console_alarm_v64()
        super()._cancel_celdra_cues_v49()

    def _show_timeline_failure_v51(self) -> None:
        self._cancel_typewriter_v64()
        self._stop_tavern_seal_v64()
        self._stop_console_alarm_v64()
        super()._show_timeline_failure_v51()


def main() -> int:
    app = PublicFragmenterAppV64()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

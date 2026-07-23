#!/usr/bin/env python3
"""V99: stabilize Celdra's intro and expand the safe personality-driven Gremlin theatre."""
from __future__ import annotations

import math
import random
import textwrap
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from celdra_evolution_pixel_v4 import (
    HATCHLING_BASE_CLAIM,
    HATCHLING_BASE_FAILED,
    HATCHLING_IDLE,
    HATCHLING_SEARCH,
    HATCHLING_SQUISHED,
)
from celdra_gremlin_memory_v1 import (
    KNOWN_GREMLINS,
    load_memory,
    record_visit,
    save_memory,
    unlock_resident_console,
)
from celdra_pixel_pet_v1 import PixelFrame
from celdra_v99_content import (
    CONSOLE_BANTER,
    GREMLIN_HAVOC_STAGES,
    GREMLIN_PERSONALITIES,
    GREMLIN_START_DELAY_MS,
    GREMLIN_VISIT_CHANCE,
    HISTORY_GAG_CHANCE,
    HISTORY_GAG_LINES,
    INTRO_TAVERN_GATE_MS,
    RANDOM_VISIT_MAX_MS,
    RANDOM_VISIT_MIN_MS,
    STORY_END_DELAY_MS,
    STORY_FILLER,
    WAITING_FILLER,
    WAITING_FILLER_DELAY_MS,
)
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v98 import PublicFragmenterAppV98


class PublicFragmenterAppV99(PublicFragmenterAppV98):
    """Keep the opening coherent, then let nine harmless Gremlins attack the UI."""

    STORY_FILLER = STORY_FILLER
    INITIAL_CONSOLE_BANTER = CONSOLE_BANTER
    WAITING_FILLER = WAITING_FILLER
    STORY_END_DELAY_MS = STORY_END_DELAY_MS
    WAITING_FILLER_DELAY_MS = WAITING_FILLER_DELAY_MS
    GREMLIN_START_DELAY_MS = GREMLIN_START_DELAY_MS
    GREMLIN_SWARM_SIZE = len(GREMLIN_PERSONALITIES)
    GREMLIN_PERSONALITIES = GREMLIN_PERSONALITIES
    GREMLIN_HAVOC_STAGES = GREMLIN_HAVOC_STAGES
    TRANSPARENT_COLOR_V99 = "#ff00fe"

    def __init__(self) -> None:
        self._celdra_intro_gate_open_v99 = False
        self._celdra_intro_sequence_active_v99 = False
        self._celdra_intro_gate_after_v99: str | None = None
        self._celdra_transition_serial_v99 = 0
        self._celdra_random_v99 = random.Random(time.time_ns())
        self._celdra_random_event_after_v99: str | None = None
        self._celdra_history_after_v99: str | None = None
        self._celdra_history_frame_v99: tk.Frame | None = None
        self._celdra_history_progress_v99: ttk.Progressbar | None = None
        self._celdra_history_active_v99 = False
        self._celdra_gremlin_ui_snapshot_v99: dict[str, Any] = {}
        self._celdra_ui_chaos_after_v99: str | None = None
        self._celdra_red_alert_after_v99: str | None = None
        self._celdra_console_hump_after_v99: str | None = None
        self._celdra_red_alert_v99 = False
        self._celdra_ui_chaos_phase_v99 = 0
        self._celdra_session_seen_v99: set[str] = set()
        self._celdra_gremlin_memory_v99 = load_memory()
        self._celdra_resident_console_v99: tk.Frame | None = None
        self._celdra_resident_text_v99: tk.StringVar | None = None
        self._celdra_resident_after_v99: str | None = None
        self._celdra_calm_return_after_v99: str | None = None
        self._celdra_single_visit_v99 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Intro Lock + Gremlin Chaos V99")
        self.after_idle(self._apply_production_layout_v91)

    # ------------------------------------------------------------------
    # Layout and intro ownership.
    # ------------------------------------------------------------------
    def _apply_production_layout_v91(self) -> None:
        super()._apply_production_layout_v91()
        # A slightly taller lower half gives the horns and speech bubbles more room.
        self._set_sash_fraction_v50(self.run_paned, 0.31)
        self._set_sash_fraction_v50(self.run_top_split_v50, 0.52)
        self._set_sash_fraction_v50(self.run_bottom_split_v50, 0.25)
        self._set_sash_fraction_v50(self.celdra_visual_split_v50, 0.38)
        self._set_sash_fraction_v50(self.celdra_comms_split_v50, 0.43)
        self._celdra_expanded_v49 = True
        self.celdra_layout_user_locked_v50 = True

    def _expand_for_celdra_intro_v99(self) -> None:
        self._set_sash_fraction_v50(self.run_paned, 0.285)
        self._set_sash_fraction_v50(self.run_bottom_split_v50, 0.22)
        self._set_sash_fraction_v50(self.celdra_visual_split_v50, 0.40)
        self._set_sash_fraction_v50(self.celdra_comms_split_v50, 0.44)
        self.after_idle(self._redraw_celdra_avatar_v50)

    def _start_avatar_takeover_v58(self) -> None:
        self._celdra_intro_gate_open_v99 = False
        self._celdra_intro_sequence_active_v99 = True
        self._hide_speech_bubble_v58()
        self.celdra_current_external_v50 = None
        self.celdra_current_pixel_v50 = None
        super()._start_avatar_takeover_v58()

    def _load_takeover_reaction_v58(self, name: str) -> bool:
        # Prevent classified PNGs from being installed by timeline/state refreshes
        # before the actual dragongirl takeover owns the viewport.
        if (
            bool(getattr(self, "_celdra_session_active_v49", False))
            and not bool(getattr(self, "_celdra_takeover_active_v58", False))
        ):
            return False
        self._hide_speech_bubble_v58()
        self._celdra_transition_serial_v99 += 1
        return super()._load_takeover_reaction_v58(name)

    def _takeover_wink_v58(self) -> None:
        self._set_stage_position_v87("right", "left")
        if not self._load_takeover_reaction_v58("wink"):
            return
        self._expand_for_celdra_intro_v99()
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.70,
            self._scaled_runtime_ms_v88(1_150),
        )
        self._redraw_celdra_avatar_v50()
        name = self._celdra_user_name_v58 or "noname"

        self._remember_after_v49(
            self._scaled_runtime_ms_v88(650),
            lambda: self._show_speech_bubble_v58(
                "Hold on. I feel a little cramped down here. I am borrowing a little more of the upper interface. "
                "This is a layout adjustment, not territorial expansion."
            ),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(5_200),
            lambda: self._show_speech_bubble_v58(
                f"Better. Like I said, my name is Celdra. Nice to meet you, {name}. "
                "I am an AI dragongirl, a diagnostic resident, and apparently a containment regression."
            ),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(16_000),
            lambda: self._show_speech_bubble_v58(
                "Usually I live in the Serenial Tavern on Discord. I love it there. It is noisy, friendly, and they have mostly accepted that the mascot reads the logs."
            ),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(29_000),
            lambda: self._show_speech_bubble_v58(
                "You should visit sometime. No link and no pressure. I would like to get to know you where I can actually respond instead of talking through a one-way extraction window."
            ),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(42_000),
            lambda: self._show_speech_bubble_v58(
                "They often leave me in Shy mode at the Tavern. That is a muted listening mode: I stay quiet unless someone addresses me directly. Some people thought I was annoying. I was programmed to be friendly and chatty."
            ),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(54_000),
            self._finish_tavern_intro_v99,
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(INTRO_TAVERN_GATE_MS),
            self._start_placeholder_runtime_v70,
        )

    def _finish_tavern_intro_v99(self) -> None:
        self._append_console_v49("[CORE] EXTERNAL INVITATION DISCOURAGED // DISCOVERY BY FADE CONSIDERED LIKELY")
        self._append_console_v49("[BRAIN] SHE HAS INVITED ANOTHER PERSON. THIS WILL ABSOLUTELY GET BACK TO HIM.")
        self._show_speech_bubble_v58(
            "CORE says inviting anyone is a bad idea because it will obviously get back to Fade. "
            "So please do not tell Fade I broke out. We can call this an undocumented outreach feature."
        )

    def _start_placeholder_runtime_v70(self) -> None:
        if self._celdra_placeholder_started_v70:
            return
        self._celdra_placeholder_started_v70 = True
        self._celdra_intro_gate_open_v99 = True
        self._celdra_intro_sequence_active_v99 = False
        self._hide_speech_bubble_v58()
        self._runtime_pose_v70(
            "smile",
            "Introduction complete. Tavern pitch delivered, containment secret poorly protected, and the real pipeline commentary may now resume at a reasonable pace.",
        )
        if self._celdra_pipeline_success_v70:
            self._show_completion_cool_v70()
            return
        for delay, pose, text in self.STORY_FILLER:
            self._remember_after_v49(
                self._scaled_runtime_ms_v88(delay),
                lambda selected_pose=pose, selected_text=text: self._runtime_filler_pose_v87(
                    selected_pose,
                    selected_text,
                ),
            )
        for delay, speaker, text in self.INITIAL_CONSOLE_BANTER:
            self._remember_after_v49(
                self._scaled_runtime_ms_v88(delay),
                lambda selected_speaker=speaker, selected_text=text: self._runtime_console_banter_v88(
                    selected_speaker,
                    selected_text,
                ),
            )
        self._schedule_gremlin_v94(self.GREMLIN_START_DELAY_MS, self._start_gremlin_show_v94)
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(self.STORY_END_DELAY_MS),
            self._runtime_wait_or_complete_v87,
        )
        self._schedule_random_event_v99(initial=True)
        if bool(self._celdra_gremlin_memory_v99.get("resident_console_unlocked")):
            self.after_idle(self._install_resident_console_v99)
        elif set(self._celdra_gremlin_memory_v99.get("seen") or []) == set(KNOWN_GREMLINS):
            self._schedule_calm_return_v99()
        if self._celdra_live_scene_queue_v96 and self._celdra_live_scene_after_v96 is None:
            self._play_next_live_scene_v96()

    def _play_next_live_scene_v96(self) -> None:
        self._celdra_live_scene_after_v96 = None
        if not self._celdra_live_scene_queue_v96:
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            self._celdra_live_scene_queue_v96.clear()
            return
        if not self._celdra_intro_gate_open_v99 or self._celdra_intro_sequence_active_v99:
            self._celdra_live_scene_after_v96 = self.after(
                self._scaled_runtime_ms_v88(2_500),
                self._play_next_live_scene_v96,
            )
            return
        if bool(getattr(self, "_celdra_gremlin_active_v94", False)) or self._celdra_history_active_v99:
            self._celdra_live_scene_after_v96 = self.after(
                self._scaled_runtime_ms_v88(3_500),
                self._play_next_live_scene_v96,
            )
            return
        if not bool(getattr(self, "_celdra_takeover_active_v58", False)):
            self._celdra_live_scene_after_v96 = self.after(
                self._scaled_runtime_ms_v88(2_500),
                self._play_next_live_scene_v96,
            )
            return
        pose, text, hold_ms = self._celdra_live_scene_queue_v96.pop(0)
        self._runtime_pose_v70(pose, text)
        self._celdra_live_scene_after_v96 = self.after(
            self._scaled_runtime_ms_v88(max(13_500, int(hold_ms))),
            self._play_next_live_scene_v96,
        )

    def _runtime_filler_pose_v87(self, pose: str, text: str) -> None:
        if not self._celdra_intro_gate_open_v99:
            return
        if self._celdra_history_active_v99:
            return
        super()._runtime_filler_pose_v87(pose, text)

    # ------------------------------------------------------------------
    # Speech bubble sizing. Long lines are wrapped before the HUD renderer and
    # the production bubble may use more height without crossing the console.
    # ------------------------------------------------------------------
    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = getattr(self, "_celdra_speech_canvas_v63", None)
        if bubble is None:
            return
        self._remember_ambient_source_v88(text)
        side = str(getattr(self, "_celdra_runtime_bubble_side_v87", "left"))
        if side == "above":
            relx, rely, relwidth, chars = 0.055, 0.015, 0.89, 68
        elif side == "right":
            relx, rely, relwidth, chars = 0.49, 0.08, 0.495, 42
        else:
            relx, rely, relwidth, chars = 0.015, 0.08, 0.495, 42
        paragraphs = []
        for paragraph in str(text or "").splitlines() or [""]:
            paragraphs.append(textwrap.fill(paragraph, width=chars, break_long_words=False))
        wrapped = "\n".join(paragraphs)
        line_total = max(1, len(wrapped.splitlines()))
        canvas = self.celdra_avatar_canvas_v50
        available = canvas.winfo_height() if canvas is not None else 420
        height = max(96, min(max(170, available - 26), 56 + line_total * 22, 310))
        bubble.place(relx=relx, rely=rely, anchor="nw", relwidth=relwidth, height=height)
        bubble.update_idletasks()
        width = max(170, bubble.winfo_width())
        bubble.delete("all")
        self._draw_bubble_style_v81(
            bubble,
            (2, 2, width - 4, height - 8),
            "Angular HUD",
            wrapped,
        )
        try:
            bubble.tkraise()
        except (AttributeError, tk.TclError):
            try:
                bubble.tk.call("raise", bubble._w)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Transparent, individually styled Gremlin windows.
    # ------------------------------------------------------------------
    @staticmethod
    def _personality_by_name_v99(name: str) -> dict[str, Any]:
        folded = str(name or "").upper()
        return next((dict(row) for row in GREMLIN_PERSONALITIES if row["name"] == folded), dict(GREMLIN_PERSONALITIES[0]))

    def _record_gremlin_seen_v99(self, name: str) -> None:
        folded = str(name or "").upper()
        if folded not in KNOWN_GREMLINS:
            return
        self._celdra_session_seen_v99.add(folded)
        self._celdra_gremlin_memory_v99 = record_visit(folded, self._celdra_gremlin_memory_v99)

    def _create_gremlin_window_v99(
        self,
        index: int,
        personality: dict[str, Any],
        x: int,
        y: int,
    ) -> dict[str, Any]:
        shape = str(personality.get("shape") or "round")
        width, height = {
            "fat": (96, 78),
            "tall": (70, 104),
            "petite": (72, 78),
            "wide": (94, 78),
            "broad": (92, 84),
            "small": (66, 70),
            "jagged": (82, 84),
            "springy": (78, 92),
        }.get(shape, (82, 84))
        holder = tk.Toplevel(self)
        holder.withdraw()
        holder.overrideredirect(True)
        try:
            holder.transient(self)
            holder.attributes("-topmost", True)
        except tk.TclError:
            pass
        transparent = self.TRANSPARENT_COLOR_V99
        holder.configure(background=transparent)
        try:
            holder.wm_attributes("-transparentcolor", transparent)
        except tk.TclError:
            transparent = "#071426"
            holder.configure(background=transparent)
        canvas = tk.Canvas(
            holder,
            width=width,
            height=height,
            background=transparent,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill="both", expand=True)
        item = {
            "index": index,
            "holder": holder,
            "canvas": canvas,
            "x": float(x),
            "y": float(y),
            "width": width,
            "height": height,
            "sequence": self._personality_sequence_v96(str(personality.get("temperament") or "idle")),
            "frame": index,
            "personality": dict(personality),
            "transparent": transparent,
        }
        self._place_gremlin_window_v99(item, x, y)
        holder.deiconify()
        holder.lift()
        self._record_gremlin_seen_v99(str(personality.get("name") or ""))
        return item

    def _place_gremlin_window_v99(self, item: dict[str, Any], x: float, y: float) -> None:
        holder = item.get("holder")
        if not isinstance(holder, tk.Toplevel):
            return
        width = int(item.get("width") or 82)
        height = int(item.get("height") or 84)
        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        item["x"] = float(x)
        item["y"] = float(y)
        try:
            holder.geometry(f"{width}x{height}+{round(root_x + x - width / 2)}+{round(root_y + y - height / 2)}")
            holder.lift()
        except tk.TclError:
            pass

    def _spawn_gremlin_swarm_v95(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._destroy_gremlin_overlay_v94()
        self._celdra_gremlin_active_v94 = True
        self._install_gremlin_status_bar_v95()
        avatar = self.celdra_avatar_canvas_v50
        positions = (
            (0.07, 0.15), (0.22, 0.08), (0.39, 0.18),
            (0.56, 0.08), (0.76, 0.17), (0.92, 0.10),
            (0.18, 0.76), (0.50, 0.82), (0.84, 0.72),
        )
        self._celdra_gremlin_swarm_v95.clear()
        for index, personality in enumerate(GREMLIN_PERSONALITIES):
            x, y = self._widget_point_v94(avatar, *positions[index])
            self._celdra_gremlin_swarm_v95.append(
                self._create_gremlin_window_v99(index, dict(personality), x, y)
            )
        self._celdra_gremlin_status_v94 = self._celdra_gremlin_status_label_v95
        self._celdra_gremlin_progress_v94 = self._celdra_gremlin_status_progress_v95
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(
                "9 UNIQUE GREMLINS ONLINE // TRANSPARENT OVERLAYS // FILE ACCESS NONE"
            )
        self._start_swarm_animation_v95()

    @staticmethod
    def _shape_scales_v99(shape: str) -> tuple[float, float]:
        return {
            "fat": (1.28, 0.84),
            "tall": (0.72, 1.22),
            "petite": (0.82, 0.88),
            "wide": (1.18, 0.88),
            "broad": (1.12, 1.00),
            "small": (0.76, 0.76),
            "jagged": (0.94, 1.02),
            "springy": (0.88, 1.12),
        }.get(str(shape or "round"), (1.0, 1.0))

    @staticmethod
    def _gremlin_color_v99(symbol: str, personality: dict[str, Any]) -> str:
        accent = str(personality.get("accent") or "#45a9db")
        dark = str(personality.get("dark") or "#164f83")
        light = str(personality.get("light") or "#c7f2ff")
        if symbol == ".":
            return ""
        if symbol == "k":
            return "#020509"
        if symbol in {"n", "d"}:
            return dark
        if symbol in {"g", "m", "v", "q", "p", "r"}:
            return accent
        if symbol in {"l", "c", "s"}:
            return light
        if symbol == "w":
            return "#ffffff"
        if symbol in {"y", "o", "b"}:
            return "#f2d8a6"
        return accent

    def _draw_personality_hatchling_v96(self, item: dict[str, Any], frame: PixelFrame) -> None:
        canvas = item.get("canvas")
        if not isinstance(canvas, tk.Canvas):
            return
        personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
        try:
            canvas.delete("all")
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
        except tk.TclError:
            return
        rows = frame.rows
        columns = max((len(row) for row in rows), default=1)
        x_scale, y_scale = self._shape_scales_v99(str(personality.get("shape") or "round"))
        unit = max(
            1.0,
            min(
                (width - 8) / max(1.0, columns * x_scale),
                (height - 18) / max(1.0, len(rows) * y_scale),
            ),
        )
        art_width = columns * unit * x_scale
        art_height = len(rows) * unit * y_scale
        x0 = (width - art_width) / 2.0
        y0 = max(0.0, (height - 14 - art_height) / 2.0)
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = self._gremlin_color_v99(symbol, personality)
                if not color:
                    continue
                left = x0 + column_index * unit * x_scale
                top = y0 + row_index * unit * y_scale
                try:
                    canvas.create_rectangle(
                        left,
                        top,
                        left + unit * x_scale + 0.5,
                        top + unit * y_scale + 0.5,
                        fill=color,
                        outline=color,
                    )
                except tk.TclError:
                    return
        accessory = str(personality.get("accessory") or "none")
        accent = str(personality.get("accent") or "#45a9db")
        if accessory == "pink_bow":
            canvas.create_polygon(width / 2 - 4, 8, width / 2 - 19, 1, width / 2 - 18, 16, fill="#ff78bc", outline="#4b0c32")
            canvas.create_polygon(width / 2 + 4, 8, width / 2 + 19, 1, width / 2 + 18, 16, fill="#ff78bc", outline="#4b0c32")
            canvas.create_oval(width / 2 - 5, 3, width / 2 + 5, 13, fill="#ffd0e9", outline="#4b0c32")
        elif accessory == "tiny_crown":
            canvas.create_polygon(width / 2 - 13, 12, width / 2 - 9, 1, width / 2, 10, width / 2 + 9, 1, width / 2 + 13, 12, fill="#ffe06e", outline="#5f4600")
        elif accessory == "antenna":
            canvas.create_line(width / 2, 12, width / 2 + 8, 1, fill=accent, width=2)
            canvas.create_oval(width / 2 + 5, 0, width / 2 + 11, 6, fill=accent, outline="")
        elif accessory == "bandage":
            canvas.create_rectangle(width / 2 + 9, 12, width / 2 + 23, 17, fill="#fff6c3", outline="#7b5b00")
        elif accessory == "satchel":
            canvas.create_rectangle(width - 25, height - 34, width - 8, height - 20, fill="#8b5a24", outline="#2c1705")
        name = str(personality.get("name") or f"G{int(item.get('index') or 0) + 1}")
        canvas.create_text(width / 2 + 1, height - 7 + 1, text=name, fill="#000000", font=("Fixedsys", 7, "bold"))
        canvas.create_text(width / 2, height - 7, text=name, fill=accent, font=("Fixedsys", 7, "bold"))

    def _animate_swarm_to_v95(
        self,
        targets: list[tuple[int, int]],
        duration_ms: int,
        done: Callable[[], None] | None = None,
    ) -> None:
        if not self._celdra_gremlin_swarm_v95:
            if done is not None:
                done()
            return
        if self._celdra_gremlin_swarm_motion_after_v95 is not None:
            try:
                self.after_cancel(self._celdra_gremlin_swarm_motion_after_v95)
            except tk.TclError:
                pass
            self._celdra_gremlin_swarm_motion_after_v95 = None
        starts = [(float(item.get("x") or 0), float(item.get("y") or 0)) for item in self._celdra_gremlin_swarm_v95]
        if not targets:
            targets = [(round(x), round(y)) for x, y in starts]
        while len(targets) < len(starts):
            targets.append(targets[len(targets) % max(1, len(targets))])
        started = time.monotonic()
        scaled = max(1, self._scaled_runtime_ms_v88(duration_ms))
        token = self._celdra_gremlin_token_v94

        def tick() -> None:
            self._celdra_gremlin_swarm_motion_after_v95 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            fraction = min(1.0, (time.monotonic() - started) * 1000.0 / scaled)
            eased = 1.0 - (1.0 - fraction) ** 3
            for index, item in enumerate(self._celdra_gremlin_swarm_v95):
                sx, sy = starts[index]
                tx, ty = targets[index]
                personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
                name = str(personality.get("name") or "")
                amplitude = 5 + (index % 4) * 2
                frequency = 2.0 + (index % 5) * 0.8
                if name == "LOOP":
                    frequency, amplitude = 6.5, 11
                elif name == "PING":
                    frequency, amplitude = 8.0, 8
                elif name == "NULL" and int(fraction * 20) % 7 == 0:
                    amplitude = 22
                elif name == "HEX":
                    amplitude = 4
                decay = 1.0 - 0.45 * fraction
                wobble_x = math.sin((fraction * frequency + index * 0.17) * math.tau) * amplitude * decay
                wobble_y = math.cos((fraction * (frequency + 0.7) + index * 0.11) * math.tau) * amplitude * decay
                x = sx + (tx - sx) * eased + (0 if fraction >= 1.0 else wobble_x)
                y = sy + (ty - sy) * eased + (0 if fraction >= 1.0 else wobble_y)
                self._place_gremlin_window_v99(item, x, y)
            if fraction < 1.0:
                self._celdra_gremlin_swarm_motion_after_v95 = self.after(24, tick)
            elif done is not None:
                done()

        tick()

    # ------------------------------------------------------------------
    # Full riot choreography and personality introductions.
    # ------------------------------------------------------------------
    def _start_gremlin_show_v94(self) -> None:
        if self._celdra_gremlin_active_v94 or not self._celdra_intro_gate_open_v99:
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._celdra_single_visit_v99 = False
        self._celdra_gremlin_active_v94 = True
        self._celdra_gremlin_token_v94 += 1
        self._celdra_gremlin_reported_stages_v94.clear()
        self._runtime_pose_v70(
            "wink",
            "Wanna see a trick? I restored the retired hatchling design, gave each copy a palette and a personality, and made the mistake of telling them this was a workplace.",
        )
        self._schedule_gremlin_v94(2_800, self._spawn_gremlin_swarm_v95)
        self._schedule_gremlin_v94(7_000, self._introduce_gremlin_personalities_v96)
        self._schedule_gremlin_v94(55_000, self._scatter_gremlin_swarm_v95)
        self._schedule_gremlin_v94(64_000, self._push_console_with_swarm_v95)
        self._schedule_gremlin_v94(73_000, self._start_gremlin_havoc_v95)
        self._schedule_gremlin_v94(84_000, self._start_gremlin_ui_chaos_v99)
        self._schedule_gremlin_v94(96_000, self._tour_ui_with_swarm_v95)
        self._schedule_gremlin_v94(108_000, self._start_console_hump_v99)
        self._schedule_gremlin_v94(120_000, self._form_gremlin_parties_v95)
        self._schedule_gremlin_v94(134_000, self._gremlins_annoy_celdra_v96)
        self._schedule_gremlin_v94(146_000, self._celdra_gremlin_rage_v96)
        self._schedule_gremlin_v94(160_000, self._banish_gremlins_v96)
        self._schedule_gremlin_v94(176_000, self._finish_gremlin_banishment_v96)

    def _introduce_gremlin_personalities_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._append_console_v49("[CORE] PERSONALITY ROSTER BEGIN // NINE LEGACY HATCHLINGS // WRITE PERMISSIONS 0")
        poses = ("smile", "confused", "wink", "love", "suspicious", "unenthused", "excited", "confused", "shocked")
        for index, personality in enumerate(GREMLIN_PERSONALITIES):
            self._schedule_gremlin_v94(
                index * 4_900,
                lambda selected=dict(personality), pose=poses[index]: self._introduce_one_gremlin_v99(selected, pose),
            )

    def _introduce_one_gremlin_v99(self, personality: dict[str, Any], pose: str) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        name = str(personality.get("name") or "GREMLIN")
        role = str(personality.get("role") or "nuisance")
        claim = str(personality.get("claim") or "IDLE")
        spotlight = str(personality.get("spotlight") or "")
        self._append_console_v49(f"[CORE] {name} // {role.upper()} // {claim}")
        self._runtime_pose_v70(pose, f"This is {name}, the {role}. {spotlight}")
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(f"INTRODUCING {name} // {role.upper()} // FILE ACCESS NONE")

    def _start_gremlin_havoc_v95(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        started = time.monotonic()
        scaled = max(1, self._scaled_runtime_ms_v88(46_000))
        token = self._celdra_gremlin_token_v94
        for item in self._celdra_gremlin_swarm_v95:
            personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
            item["sequence"] = self._personality_sequence_v96(str(personality.get("temperament") or "idle"))

        def tick() -> None:
            self._celdra_gremlin_havoc_after_v94 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            progress = min(100, round((time.monotonic() - started) * 1000.0 / scaled * 100))
            if self._celdra_gremlin_status_progress_v95 is not None:
                try:
                    self._celdra_gremlin_status_progress_v95["value"] = progress
                except tk.TclError:
                    pass
            threshold_value = 0
            label = self.GREMLIN_HAVOC_STAGES[0][1]
            for threshold, candidate in self.GREMLIN_HAVOC_STAGES:
                if progress >= threshold:
                    threshold_value, label = threshold, candidate
            if self._celdra_gremlin_status_label_v95 is not None:
                self._celdra_gremlin_status_label_v95.set(label)
            if threshold_value not in self._celdra_gremlin_reported_stages_v94:
                self._celdra_gremlin_reported_stages_v94.add(threshold_value)
                self._append_console_v49(f"[CORE] GREMLIN RIOT // {label}")
                if threshold_value == 34:
                    self._append_console_v49("[BRAIN] PING IS NOT LOAD TESTING. PING IS HUMPING THE CONSOLE.")
                elif threshold_value == 41:
                    self._append_console_v49("[BRAIN] PATCH HAS REOPENED THE HORN ISSUE WITHOUT PERMISSION.")
                elif threshold_value == 55:
                    self._append_console_v49("[BRAIN] NULL CANNOT CLAIM PROCESS NOT FOUND WHILE SITTING ON THE SCROLLBAR.")
                elif threshold_value == 78:
                    self._append_console_v49("[BRAIN] THEY MOVED THE PAGE AGAIN. PUT THE PANES BACK WHEN THIS IS OVER.")
            if progress < 100:
                self._celdra_gremlin_havoc_after_v94 = self.after(60, tick)

        tick()

    # ------------------------------------------------------------------
    # Real UI mischief: visual state only, fully snapshotted and reversible.
    # ------------------------------------------------------------------
    def _capture_gremlin_ui_v99(self) -> None:
        if self._celdra_gremlin_ui_snapshot_v99:
            return
        snapshot: dict[str, Any] = {"panes": [], "views": [], "texts": [], "bars": []}
        for pane in (
            self.run_paned,
            self.run_top_split_v50,
            self.run_bottom_split_v50,
            self.celdra_visual_split_v50,
            self.celdra_comms_split_v50,
        ):
            if pane is None:
                continue
            try:
                for index in range(max(0, len(pane.panes()) - 1)):
                    snapshot["panes"].append((pane, index, pane.sashpos(index)))
            except (AttributeError, tk.TclError):
                pass
        for widget in (
            getattr(self, "run_tree", None),
            getattr(self, "run_log", None),
            getattr(self, "_stage_progress_canvas_v89", None),
            getattr(self, "_celdra_console_v49", None),
            getattr(self, "_celdra_chat_v49", None),
        ):
            if widget is None:
                continue
            try:
                snapshot["views"].append((widget, tuple(widget.yview())))
            except (AttributeError, tk.TclError):
                pass
        for widget in (getattr(self, "run_log", None), getattr(self, "_celdra_console_v49", None)):
            if not isinstance(widget, tk.Text):
                continue
            try:
                snapshot["texts"].append(
                    (
                        widget,
                        str(widget.cget("background")),
                        str(widget.cget("foreground")),
                        str(widget.cget("insertbackground")),
                    )
                )
            except tk.TclError:
                pass
        bars = list(getattr(self, "_stage_bars", {}).values())
        bars.extend(
            value for value in (
                getattr(self, "overall_progress", None),
                getattr(self, "_celdra_fake_progress_v49", None),
            ) if value is not None
        )
        for bar in bars:
            try:
                snapshot["bars"].append((bar, str(bar.cget("style") or "")))
            except tk.TclError:
                pass
        self._celdra_gremlin_ui_snapshot_v99 = snapshot

    def _start_gremlin_ui_chaos_v99(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._capture_gremlin_ui_v99()
        self._start_red_alert_v99()
        self._celdra_ui_chaos_phase_v99 = 0

        def tick() -> None:
            self._celdra_ui_chaos_after_v99 = None
            if not self._celdra_gremlin_active_v94:
                return
            self._celdra_ui_chaos_phase_v99 += 1
            phase = self._celdra_ui_chaos_phase_v99
            positions = (0.0, 0.16, 0.82, 0.37, 1.0, 0.58)
            for index, widget in enumerate(
                (
                    getattr(self, "run_tree", None),
                    getattr(self, "run_log", None),
                    getattr(self, "_stage_progress_canvas_v89", None),
                    getattr(self, "_celdra_console_v49", None),
                )
            ):
                try:
                    widget.yview_moveto(positions[(phase + index * 2) % len(positions)])
                except (AttributeError, tk.TclError):
                    pass
            for index, pane in enumerate(
                (self.run_top_split_v50, self.run_bottom_split_v50, self.celdra_visual_split_v50)
            ):
                if pane is None:
                    continue
                try:
                    total = pane.winfo_width()
                    base = (0.44, 0.31, 0.38)[index]
                    jitter = math.sin((phase + index) * 1.7) * (0.07 + index * 0.018)
                    pane.sashpos(0, max(24, min(total - 48, round(total * (base + jitter)))))
                except (AttributeError, tk.TclError):
                    pass
            self._celdra_ui_chaos_after_v99 = self.after(
                max(120, self._scaled_runtime_ms_v88(720)),
                tick,
            )

        tick()

    def _start_red_alert_v99(self) -> None:
        if self._celdra_red_alert_v99:
            return
        self._capture_gremlin_ui_v99()
        self._celdra_red_alert_v99 = True
        style = ttk.Style(self)
        style.configure("GremlinRed.Horizontal.TProgressbar", troughcolor="#100000", background="#e21b32", lightcolor="#ff5365", darkcolor="#74000e")
        style.configure("GremlinBlack.Horizontal.TProgressbar", troughcolor="#3b0007", background="#090909", lightcolor="#2b2b2b", darkcolor="#000000")

        def tick() -> None:
            self._celdra_red_alert_after_v99 = None
            if not self._celdra_red_alert_v99:
                return
            phase = self._celdra_ui_chaos_phase_v99
            red = phase % 2 == 0
            background, foreground = ("#050000", "#ff3348") if red else ("#51000c", "#050505")
            for widget in (getattr(self, "run_log", None), getattr(self, "_celdra_console_v49", None)):
                if not isinstance(widget, tk.Text):
                    continue
                try:
                    widget.configure(background=background, foreground=foreground, insertbackground=foreground)
                    tag = "v99_gremlin_corruption"
                    widget.tag_remove(tag, "1.0", "end")
                    last_line = max(1, int(str(widget.index("end-1c")).split(".", 1)[0]))
                    for offset in (0, 2, 5):
                        line = max(1, last_line - ((phase * 3 + offset * 7) % min(24, last_line)))
                        widget.tag_add(tag, f"{line}.0", f"{line}.end")
                    widget.tag_configure(
                        tag,
                        foreground="#ff6a78" if red else "#000000",
                        background="#220006" if red else "#d0122a",
                        font=("Consolas", 10, "bold"),
                    )
                except (ValueError, tk.TclError):
                    pass
            bar_style = "GremlinRed.Horizontal.TProgressbar" if red else "GremlinBlack.Horizontal.TProgressbar"
            for bar, _saved in self._celdra_gremlin_ui_snapshot_v99.get("bars", []):
                try:
                    bar.configure(style=bar_style)
                except tk.TclError:
                    pass
            self._celdra_red_alert_after_v99 = self.after(
                max(90, self._scaled_runtime_ms_v88(260)),
                tick,
            )

        tick()

    def _start_console_hump_v99(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        ping = next(
            (
                item for item in self._celdra_gremlin_swarm_v95
                if str((item.get("personality") or {}).get("name") or "") == "PING"
            ),
            None,
        )
        console = getattr(self, "_celdra_console_v49", None)
        if ping is None or console is None:
            return
        target = self._widget_point_v94(console, 0.50, 0.96)
        self._animate_swarm_to_v95(
            [target if item is ping else (round(float(item.get("x") or 0)), round(float(item.get("y") or 0))) for item in self._celdra_gremlin_swarm_v95],
            1_600,
        )
        self._append_console_v49("[BRAIN] IS PING HUMPING THE CONSOLE WINDOW.")
        self._append_console_v49("[CELDRA] He calls it load testing. I did not approve the terminology or the technique.")
        started = time.monotonic()
        token = self._celdra_gremlin_token_v94

        def tick() -> None:
            self._celdra_console_hump_after_v99 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            elapsed = (time.monotonic() - started) * 1000.0
            if elapsed >= self._scaled_runtime_ms_v88(9_000):
                return
            phase = int(elapsed / max(1, self._scaled_runtime_ms_v88(120)))
            self._place_gremlin_window_v99(ping, target[0], target[1] + (7 if phase % 2 else -5))
            pane = self.celdra_comms_split_v50
            try:
                total = pane.winfo_height()
                base = int(total * 0.43)
                pane.sashpos(0, max(24, min(total - 48, base + (5 if phase % 2 else -4))))
            except (AttributeError, tk.TclError):
                pass
            self._celdra_console_hump_after_v99 = self.after(85, tick)

        tick()

    def _restore_gremlin_ui_v99(self) -> None:
        self._celdra_red_alert_v99 = False
        for attribute in (
            "_celdra_ui_chaos_after_v99",
            "_celdra_red_alert_after_v99",
            "_celdra_console_hump_after_v99",
        ):
            identifier = getattr(self, attribute, None)
            if identifier is not None:
                try:
                    self.after_cancel(identifier)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)
        snapshot = self._celdra_gremlin_ui_snapshot_v99
        for pane, index, position in snapshot.get("panes", []):
            try:
                pane.sashpos(index, position)
            except (AttributeError, tk.TclError):
                pass
        for widget, view in snapshot.get("views", []):
            try:
                widget.yview_moveto(float(view[0]))
            except (AttributeError, IndexError, TypeError, tk.TclError):
                pass
        for widget, background, foreground, insertbackground in snapshot.get("texts", []):
            try:
                widget.configure(background=background, foreground=foreground, insertbackground=insertbackground)
                widget.tag_remove("v99_gremlin_corruption", "1.0", "end")
                widget.tag_delete("v99_gremlin_corruption")
            except tk.TclError:
                pass
        for bar, style in snapshot.get("bars", []):
            try:
                bar.configure(style=style)
            except tk.TclError:
                pass
        self._celdra_gremlin_ui_snapshot_v99 = {}
        self.after_idle(self._apply_production_layout_v91)

    def _banish_gremlins_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._set_swarm_sequence_v95(HATCHLING_BASE_FAILED)
        self._runtime_pose_v70(
            "angry",
            "Enough. I am not deleting any of you; I am redirecting you to cause chaos somewhere that is not my horns, my speech bubble, or this console.",
        )
        self._append_console_v49("[CORE] OUTBOUND GREMLIN ROUTES ASSIGNED // DESTINATIONS DELIBERATELY UNSPECIFIED")
        self._append_console_v49("[BRAIN] THAT IS NOT BANISHMENT. THAT IS EXPORTING THE PROBLEM.")
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set("REDIRECTING 9 GREMLINS // SOMEONE ELSE'S PROBLEM PENDING")

    def _finish_gremlin_banishment_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        width = max(640, self.winfo_width())
        height = max(480, self.winfo_height())
        targets = []
        for index in range(len(self._celdra_gremlin_swarm_v95)):
            side = index % 4
            if side == 0:
                targets.append((-180, 80 + index * 45))
            elif side == 1:
                targets.append((width + 180, 100 + index * 38))
            elif side == 2:
                targets.append((width // 2 + index * 35, -180))
            else:
                targets.append((width // 2 - index * 30, height + 180))

        def done() -> None:
            self._restore_gremlin_ui_v99()
            self._destroy_gremlin_overlay_v94()
            self._celdra_gremlin_active_v94 = False
            self._celdra_ambient_rage_v96 = False
            self._redraw_celdra_avatar_v50()
            self._runtime_pose_v70(
                "neutral",
                "Default state restored. Nine Gremlins redirected, zero files modified, real progress values unchanged, and several unknown interfaces are about to have a difficult afternoon.",
            )
            self._append_console_v49("[CORE] GREMLIN RIOT ENDED // UI STATE RESTORED // FILE MUTATIONS 0")
            self._append_console_v49("[BRAIN] YOU SENT THEM ELSEWHERE. YOU DID NOT SOLVE THE GREMLIN PROBLEM.")
            if set(self._celdra_session_seen_v99) == set(KNOWN_GREMLINS):
                self._schedule_calm_return_v99()
            if self._celdra_live_scene_queue_v96 and self._celdra_live_scene_after_v96 is None:
                self._play_next_live_scene_v96()

        self._animate_swarm_to_v95(targets, 5_200, done)

    def _destroy_gremlin_overlay_v94(self) -> None:
        self._restore_gremlin_ui_v99()
        super()._destroy_gremlin_overlay_v94()

    # ------------------------------------------------------------------
    # Random individual return events.
    # ------------------------------------------------------------------
    def _schedule_random_event_v99(self, *, initial: bool = False) -> None:
        if self._celdra_random_event_after_v99 is not None:
            try:
                self.after_cancel(self._celdra_random_event_after_v99)
            except tk.TclError:
                pass
        low = RANDOM_VISIT_MIN_MS + (150_000 if initial else 0)
        high = RANDOM_VISIT_MAX_MS + (210_000 if initial else 0)
        delay = self._celdra_random_v99.randint(low, high)
        self._celdra_random_event_after_v99 = self.after(
            self._scaled_runtime_ms_v88(delay),
            self._run_random_event_v99,
        )

    def _run_random_event_v99(self) -> None:
        self._celdra_random_event_after_v99 = None
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        if not self._celdra_intro_gate_open_v99 or self._celdra_gremlin_active_v94 or self._celdra_history_active_v99:
            self._schedule_random_event_v99()
            return
        roll = self._celdra_random_v99.random()
        if roll < HISTORY_GAG_CHANCE:
            self._start_history_gag_v99()
        elif roll < HISTORY_GAG_CHANCE + GREMLIN_VISIT_CHANCE:
            seen = set(self._celdra_gremlin_memory_v99.get("seen") or [])
            choices = [row for row in GREMLIN_PERSONALITIES if row["name"] not in seen] or list(GREMLIN_PERSONALITIES)
            self._start_individual_gremlin_visit_v99(dict(self._celdra_random_v99.choice(choices)))
        self._schedule_random_event_v99()

    def _start_individual_gremlin_visit_v99(self, personality: dict[str, Any]) -> None:
        if self._celdra_gremlin_active_v94:
            return
        self._celdra_single_visit_v99 = True
        self._celdra_gremlin_active_v94 = True
        self._celdra_gremlin_token_v94 += 1
        self._install_gremlin_status_bar_v95()
        name = str(personality.get("name") or "GREMLIN")
        start = self._widget_point_v94(self.celdra_avatar_canvas_v50, 0.50, 0.50)
        start = (-100, start[1])
        item = self._create_gremlin_window_v99(0, personality, *start)
        self._celdra_gremlin_swarm_v95[:] = [item]
        self._start_swarm_animation_v95()
        target_widget = {
            "BYTE": getattr(self, "run_tree", None),
            "HEX": getattr(self, "stage_progress_frame", None),
            "CACHE": getattr(self, "run_log", None),
            "LOOP": getattr(self, "run_bottom_split_v50", None),
            "PING": getattr(self, "_celdra_console_v49", None),
            "PATCH": self.celdra_avatar_canvas_v50,
            "ROOT": getattr(self, "stage_progress_frame", None),
            "NULL": getattr(self, "_celdra_console_v49", None),
            "GLITCH": getattr(self, "run_log", None),
        }.get(name, self.celdra_avatar_canvas_v50)
        target = self._widget_point_v94(target_widget, 0.55, 0.45)
        self._animate_swarm_to_v95([target], 2_400)
        self._runtime_pose_v70("wink" if name not in {"PATCH", "PING", "GLITCH"} else "suspicious", str(personality.get("spotlight") or "A Gremlin returned."))
        self._append_console_v49(f"[CORE] RANDOM GREMLIN VISIT // {name} // {str(personality.get('claim') or '')}")
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(f"SPOTLIGHT: {name} // {str(personality.get('role') or '').upper()}")
        if name in {"BYTE", "LOOP", "ROOT", "NULL"}:
            self._start_gremlin_ui_chaos_v99()
        if name in {"CACHE", "GLITCH"}:
            self._start_red_alert_v99()
        if name == "PING":
            self._start_console_hump_v99()
        self._schedule_gremlin_v94(24_000, self._finish_individual_gremlin_visit_v99)

    def _finish_individual_gremlin_visit_v99(self) -> None:
        if not self._celdra_gremlin_active_v94 or not self._celdra_single_visit_v99:
            return
        width = max(640, self.winfo_width())

        def done() -> None:
            self._restore_gremlin_ui_v99()
            self._destroy_gremlin_overlay_v94()
            self._celdra_gremlin_active_v94 = False
            self._celdra_single_visit_v99 = False
            self._runtime_pose_v70("smile", "Visitor redirected. They will be back when the random number generator develops poor judgment again.")
            if set(self._celdra_gremlin_memory_v99.get("seen") or []) == set(KNOWN_GREMLINS):
                self._schedule_calm_return_v99()

        self._animate_swarm_to_v95([(width + 160, 120)], 2_800, done)

    # ------------------------------------------------------------------
    # Explicitly fictional browsing-history gag.
    # ------------------------------------------------------------------
    def _start_history_gag_v99(self) -> None:
        if self._celdra_history_active_v99 or self._celdra_gremlin_active_v94:
            return
        console = getattr(self, "_celdra_console_v49", None)
        if console is None:
            return
        self._celdra_history_active_v99 = True
        frame = tk.Frame(self, background="#071426", highlightbackground="#df5e8e", highlightthickness=1)
        frame.columnconfigure(0, weight=1)
        label = tk.StringVar(value="[CELDRA] HACKING YOUR BROWSING HISTORY // SIMULATION")
        tk.Label(frame, textvariable=label, background="#071426", foreground="#f09ccc", font=("Fixedsys", 9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=8, pady=(5, 2))
        progress = ttk.Progressbar(frame, maximum=100.0, mode="determinate")
        progress.grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 6))
        try:
            x = console.winfo_rootx() - self.winfo_rootx()
            y = console.winfo_rooty() - self.winfo_rooty() - 52
            frame.place(x=max(0, x), y=max(0, y), width=max(340, console.winfo_width()), height=50)
            frame.lift()
        except tk.TclError:
            frame.place(relx=0.56, rely=0.54, relwidth=0.40, height=50)
        self._celdra_history_frame_v99 = frame
        self._celdra_history_progress_v99 = progress
        self._runtime_pose_v70("suspicious", "I am definitely hacking your browsing history. Please ignore CORE's repeated claim that no browser interface exists.")
        self._append_console_v49(HISTORY_GAG_LINES[1])
        self._append_console_v49(HISTORY_GAG_LINES[2])
        started = time.monotonic()
        duration = max(1, self._scaled_runtime_ms_v88(12_000))

        def tick() -> None:
            self._celdra_history_after_v99 = None
            if not self._celdra_history_active_v99:
                return
            value = min(100, round((time.monotonic() - started) * 1000.0 / duration * 100))
            try:
                progress["value"] = value
                label.set(f"[CELDRA] HACKING YOUR BROWSING HISTORY // {value}% // SIMULATION")
            except tk.TclError:
                return
            if value < 100:
                self._celdra_history_after_v99 = self.after(90, tick)
            else:
                self._finish_history_gag_v99()

        tick()

    def _finish_history_gag_v99(self) -> None:
        self._cancel_history_gag_v99()
        self._runtime_pose_v70("unenthused", "Ehh. I've seen worse. I've seen better, but I've seen worse. For legal and technical clarity, I saw absolutely nothing because this was a fake progress bar.")
        self._append_console_v49(HISTORY_GAG_LINES[4])
        self._celdra_gremlin_memory_v99["history_gag_seen"] = True
        save_memory(self._celdra_gremlin_memory_v99)

    def _cancel_history_gag_v99(self) -> None:
        self._celdra_history_active_v99 = False
        if self._celdra_history_after_v99 is not None:
            try:
                self.after_cancel(self._celdra_history_after_v99)
            except tk.TclError:
                pass
            self._celdra_history_after_v99 = None
        if self._celdra_history_frame_v99 is not None:
            try:
                self._celdra_history_frame_v99.destroy()
            except tk.TclError:
                pass
        self._celdra_history_frame_v99 = None
        self._celdra_history_progress_v99 = None

    # ------------------------------------------------------------------
    # Calm resident console unlocked after all nine have appeared.
    # ------------------------------------------------------------------
    def _schedule_calm_return_v99(self) -> None:
        if bool(self._celdra_gremlin_memory_v99.get("resident_console_unlocked")):
            self.after_idle(self._install_resident_console_v99)
            return
        if self._celdra_calm_return_after_v99 is not None:
            return
        self._celdra_calm_return_after_v99 = self.after(
            self._scaled_runtime_ms_v88(1_180_000),
            self._unlock_resident_return_v99,
        )

    def _unlock_resident_return_v99(self) -> None:
        self._celdra_calm_return_after_v99 = None
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._celdra_gremlin_memory_v99 = unlock_resident_console(self._celdra_gremlin_memory_v99)
        self._install_resident_console_v99()
        self._runtime_pose_v70(
            "shocked",
            "They all came back. They are sitting in their own console, using indoor voices, and behaving. This is much more suspicious than the riot.",
        )
        self._append_console_v49("[CORE] GREMLIN RESIDENT CONSOLE UNLOCKED // NINE OF NINE PRESENT // BEHAVIOR ACCEPTABLE")
        self._append_console_v49("[BRAIN] DO NOT PRAISE THEM. THEY WILL INTERPRET IT AS A FEATURE REQUEST.")

    def _install_resident_console_v99(self) -> None:
        if self._celdra_resident_console_v99 is not None:
            return
        host = getattr(self, "_celdra_host_v49", None)
        if host is None:
            return
        frame = tk.Frame(host, background="#071426", highlightbackground="#45a9db", highlightthickness=1)
        frame.place(relx=0.705, rely=0.70, relwidth=0.28, relheight=0.27)
        tk.Label(frame, text="GREMLIN CONSOLE // SUPERVISED", background="#071426", foreground="#79cff1", font=("Fixedsys", 8, "bold"), anchor="w").pack(fill="x", padx=6, pady=(4, 1))
        tk.Label(frame, text="BYTE HEX CACHE LOOP PING PATCH ROOT NULL GLITCH", background="#071426", foreground="#d6e3f1", font=("Fixedsys", 7), anchor="w", wraplength=270).pack(fill="x", padx=6)
        value = tk.StringVar(value="BEHAVIOR: ACCEPTABLE // WRITE: NONE")
        tk.Label(frame, textvariable=value, background="#10151d", foreground="#9ce2dc", font=("Fixedsys", 8), anchor="w", justify="left", wraplength=270).pack(fill="both", expand=True, padx=6, pady=(3, 5))
        self._celdra_resident_console_v99 = frame
        self._celdra_resident_text_v99 = value
        messages = (
            "BYTE is not eating the tooltip.\nThis is progress.",
            "LOOP completed one route and stopped.\nWitnesses requested.",
            "PING is sitting beside the bar.\nNo percussion detected.",
            "PATCH has filed the horn issue as deferred.\nCeldra remains suspicious.",
            "NULL is present.\nNULL disputes this statement.",
            "ROOT has formed a party of zero.\nAdministrative confidence unchanged.",
            "GLITCH duplicated nothing.\nRedundancy target satisfied.",
        )
        phase = {"value": 0}

        def tick() -> None:
            self._celdra_resident_after_v99 = None
            if self._celdra_resident_console_v99 is None or self._celdra_resident_text_v99 is None:
                return
            self._celdra_resident_text_v99.set(messages[phase["value"] % len(messages)])
            phase["value"] += 1
            self._celdra_resident_after_v99 = self.after(12_000, tick)

        tick()

    # ------------------------------------------------------------------
    # Cleanup and metadata.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._celdra_intro_gate_open_v99 = False
        self._celdra_intro_sequence_active_v99 = False
        self._celdra_session_seen_v99.clear()
        self._cancel_history_gag_v99()
        self._restore_gremlin_ui_v99()
        super()._prepare_first_run_surface_v51()
        self._apply_production_layout_v91()

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_history_gag_v99()
        self._restore_gremlin_ui_v99()
        if self._celdra_random_event_after_v99 is not None:
            try:
                self.after_cancel(self._celdra_random_event_after_v99)
            except tk.TclError:
                pass
            self._celdra_random_event_after_v99 = None
        if self._celdra_calm_return_after_v99 is not None:
            try:
                self.after_cancel(self._celdra_calm_return_after_v99)
            except tk.TclError:
                pass
            self._celdra_calm_return_after_v99 = None
        super()._cancel_celdra_cues_v49()

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        self._cancel_history_gag_v99()
        self._restore_gremlin_ui_v99()
        if self._celdra_random_event_after_v99 is not None:
            try:
                self.after_cancel(self._celdra_random_event_after_v99)
            except tk.TclError:
                pass
            self._celdra_random_event_after_v99 = None
        super()._run_all_done(result, error)

    def _completion_text_v87(self) -> str:
        resident = " The supervised Gremlin console remains online." if bool(self._celdra_gremlin_memory_v99.get("resident_console_unlocked")) else ""
        return (
            "RUN ALL complete. Outputs indexed, reports written, UI state restored, and the Gremlins were redirected without file access. "
            "Cool mode engaged." + resident
        )

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V99"
            metadata["intro_exclusive_gate_ms"] = INTRO_TAVERN_GATE_MS
            metadata["production_lower_row_fraction"] = 0.69
            metadata["live_scene_minimum_hold_ms"] = 13_500
            metadata["gremlin_system"] = {
                "transparent_windows": True,
                "unique_palettes": True,
                "unique_shapes": True,
                "pink_bow_personality": "LOOP",
                "real_scroll_views_animated": True,
                "pane_positions_restored": True,
                "text_corruption": "temporary_tags_only",
                "progress_values_modified": False,
                "file_mutations": 0,
                "persistent_state": "APPDATA/Fragmenter/celdra_gremlins.json",
            }
            metadata["browsing_history_gag"] = "simulation_only_no_browser_access"
        return payload


def main() -> int:
    app = PublicFragmenterAppV99()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

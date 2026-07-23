#!/usr/bin/env python3
"""V101: internal Gremlin roster, persistent animated stable, and readable Celdra dialogue."""
from __future__ import annotations

import math
import random
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any

from audio_music_catalog_status_v1 import music_catalog_message, music_catalog_status
from celdra_gremlin_art_v2 import design_dimensions, draw_gremlin
from celdra_gremlin_memory_v1 import KNOWN_GREMLINS
from celdra_gremlin_memory_v2 import (
    capture_in_stable,
    collection_complete,
    load_memory,
    mark_collection_reward_seen,
    record_visit,
    save_memory,
)
from celdra_v99_content import (
    GREMLIN_PERSONALITIES,
    GREMLIN_VISIT_CHANCE,
    HISTORY_GAG_CHANCE,
)
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v100 import PublicFragmenterAppV100


class PublicFragmenterAppV101(PublicFragmenterAppV100):
    """Keep the ensemble inside Fragmenter and turn returning visitors into residents."""

    MIDDLE_BACKGROUND = "#0b1119"
    MIDDLE_BORDER = "#315575"
    YELL_BACKGROUND = "#280208"
    YELL_BORDER = "#ff4054"

    CALM_MANAGEMENT_LINES = (
        (
            "smile",
            "Okay, everyone gets one harmless activity. BYTE, labels are not snacks. HEX, offsets stay in the status pane. We can do this calmly.",
        ),
        (
            "confused",
            "PING, off the console edge. PATCH, my horn is not a maintenance ticket. ROOT, nobody elected you administrator of the scrollbar.",
        ),
        (
            "unenthused",
            "LOOP, one route is enough. CACHE, put BRAIN's complaints back in chronological order. NULL, I can see you behind the progress bar.",
        ),
        (
            "suspicious",
            "GLITCH, temporary visual corruption only. No values, no files, no controls. I am being extremely reasonable for someone supervising nine tiny disasters.",
        ),
    )

    def __init__(self) -> None:
        self._celdra_middle_frame_v101: ttk.Frame | None = None
        self._celdra_middle_header_v101: tk.StringVar | None = None
        self._celdra_middle_body_v101: tk.Frame | None = None
        self._celdra_middle_items_v101: dict[str, dict[str, Any]] = {}
        self._celdra_middle_after_v101: str | None = None
        self._celdra_middle_mode_v101 = "stable"
        self._celdra_middle_phase_v101 = 0
        self._celdra_roster_visible_v101: list[str] = []
        self._celdra_internal_show_v101 = False
        self._celdra_yell_mode_v101 = False
        self._celdra_session_individual_v101: set[str] = set()
        self._celdra_current_individual_v101 = ""
        self._celdra_history_session_v101 = False
        self._celdra_collection_reward_after_v101: str | None = None
        self._celdra_collection_reward_active_v101 = False
        self._celdra_first_stable_notice_v101 = False
        self._music_catalog_status_v101: tk.StringVar | None = None
        super().__init__()
        self._celdra_gremlin_memory_v99 = load_memory()
        self.title("Fragmenter 1.0 WIP - Celdra Animated Gremlin Stable V101")
        if self._stable_names_v101():
            self.after_idle(self._install_gremlin_stable_v101)

    # ------------------------------------------------------------------
    # Three-pane Celdra layout: avatar | Gremlin stable | console/dialogue.
    # ------------------------------------------------------------------
    def _stable_names_v101(self) -> list[str]:
        stable = {str(value).upper() for value in self._celdra_gremlin_memory_v99.get("stable") or []}
        return [name for name in KNOWN_GREMLINS if name in stable]

    def _ensure_middle_panel_v101(self, mode: str) -> None:
        self._celdra_middle_mode_v101 = str(mode or "stable")
        pane = getattr(self, "celdra_visual_split_v50", None)
        if pane is None:
            return
        if self._celdra_middle_frame_v101 is None:
            frame = ttk.Frame(pane, padding=3)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(1, weight=1)
            title = tk.StringVar(value="GREMLIN STABLE")
            tk.Label(
                frame,
                textvariable=title,
                background="#071426",
                foreground="#bdeaff",
                font=("Consolas", 8, "bold"),
                anchor="w",
                padx=6,
                pady=3,
            ).grid(row=0, column=0, sticky="ew")
            body = tk.Frame(
                frame,
                background=self.MIDDLE_BACKGROUND,
                highlightbackground=self.MIDDLE_BORDER,
                highlightthickness=1,
                borderwidth=0,
            )
            body.grid(row=1, column=0, sticky="nsew")
            try:
                pane.insert(1, frame, weight=1)
            except (AttributeError, tk.TclError):
                try:
                    pane.add(frame, weight=1)
                except tk.TclError:
                    frame.destroy()
                    return
            self._celdra_middle_frame_v101 = frame
            self._celdra_middle_header_v101 = title
            self._celdra_middle_body_v101 = body
        self._update_middle_header_v101()
        self.after_idle(self._apply_middle_layout_v101)
        self._start_middle_animation_v101()

    def _remove_middle_panel_v101(self) -> None:
        if self._stable_names_v101():
            self._install_gremlin_stable_v101()
            return
        self._cancel_middle_animation_v101()
        frame = self._celdra_middle_frame_v101
        pane = getattr(self, "celdra_visual_split_v50", None)
        self._clear_middle_items_v101()
        if frame is not None and pane is not None:
            try:
                pane.forget(frame)
            except (AttributeError, tk.TclError):
                pass
            try:
                frame.destroy()
            except tk.TclError:
                pass
        self._celdra_middle_frame_v101 = None
        self._celdra_middle_header_v101 = None
        self._celdra_middle_body_v101 = None
        self.after_idle(self._apply_production_layout_v91)

    def _apply_middle_layout_v101(self) -> None:
        pane = getattr(self, "celdra_visual_split_v50", None)
        frame = self._celdra_middle_frame_v101
        if pane is None or frame is None:
            return
        try:
            self.update_idletasks()
            width = max(500, pane.winfo_width())
            panes = tuple(pane.panes())
            if len(panes) >= 3:
                avatar_fraction = 0.46 if self._celdra_internal_show_v101 else 0.48
                stable_fraction = 0.76 if self._celdra_internal_show_v101 else 0.71
                pane.sashpos(0, round(width * avatar_fraction))
                pane.sashpos(1, round(width * stable_fraction))
        except (AttributeError, tk.TclError):
            pass

    def _apply_production_layout_v91(self) -> None:
        super()._apply_production_layout_v91()
        if self._celdra_middle_frame_v101 is not None:
            self.after_idle(self._apply_middle_layout_v101)

    def _update_middle_header_v101(self) -> None:
        value = self._celdra_middle_header_v101
        if value is None:
            return
        stable_count = len(self._stable_names_v101())
        visible = len(self._celdra_roster_visible_v101)
        mode = self._celdra_middle_mode_v101
        if mode == "roster":
            value.set(f"GREMLIN ROSTER // {visible}/9 // ORGANIZED")
        elif mode == "chaos":
            value.set("GREMLIN ROSTER // CHAOS ACTIVE // VALUES PROTECTED")
        elif mode == "attention":
            value.set("GREMLIN ROSTER // ATTENTION // CHAOS HALTED")
        elif mode == "depart":
            value.set("GREMLIN ROSTER // DEPARTURE ROUTES")
        elif mode == "reward":
            value.set("GREMLIN STABLE // FULL COLLECTION // 9/9 BEHAVING")
        else:
            value.set(f"GREMLIN STABLE // {stable_count}/9 CAPTURED // ANIMATED")

    # ------------------------------------------------------------------
    # Refined artwork shared by external visitors and internal residents.
    # ------------------------------------------------------------------
    def _draw_personality_hatchling_v96(self, item: dict[str, Any], _frame: Any) -> None:
        canvas = item.get("canvas")
        if not isinstance(canvas, tk.Canvas):
            return
        personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
        mood = str(item.get("mood") or ("chaos" if self._celdra_middle_mode_v101 == "chaos" else "idle"))
        draw_gremlin(
            canvas,
            personality,
            width=int(item.get("width") or canvas.winfo_width() or 82),
            height=int(item.get("height") or canvas.winfo_height() or 88),
            phase=int(item.get("phase") or item.get("frame") or 0),
            mood=mood,
            compact=bool(item.get("compact")),
            show_name=True,
        )

    def _personality_v101(self, name: str) -> dict[str, Any]:
        folded = str(name or "").upper()
        return next(
            (dict(row) for row in GREMLIN_PERSONALITIES if str(row.get("name") or "").upper() == folded),
            dict(GREMLIN_PERSONALITIES[0]),
        )

    def _grid_position_v101(self, index: int, width: int, height: int, item_width: int, item_height: int) -> tuple[float, float]:
        columns = 3
        rows = 3
        column = index % columns
        row = index // columns
        cell_width = max(1.0, width / columns)
        cell_height = max(1.0, height / rows)
        return (
            column * cell_width + max(1.0, (cell_width - item_width) / 2.0),
            row * cell_height + max(1.0, (cell_height - item_height) / 2.0),
        )

    def _show_internal_gremlin_v101(self, name: str, *, compact: bool = True) -> dict[str, Any] | None:
        folded = str(name or "").upper()
        if folded in self._celdra_middle_items_v101:
            return self._celdra_middle_items_v101[folded]
        body = self._celdra_middle_body_v101
        if body is None:
            return None
        personality = self._personality_v101(folded)
        width, height = design_dimensions(personality, compact=compact)
        canvas = tk.Canvas(
            body,
            width=width,
            height=height,
            background=self.MIDDLE_BACKGROUND,
            highlightthickness=0,
            borderwidth=0,
        )
        index = KNOWN_GREMLINS.index(folded) if folded in KNOWN_GREMLINS else len(self._celdra_middle_items_v101)
        item = {
            "name": folded,
            "index": index,
            "canvas": canvas,
            "personality": personality,
            "width": width,
            "height": height,
            "x": 0.0,
            "y": 0.0,
            "vx": (1.8 + index * 0.23) * (-1 if index % 2 else 1),
            "vy": (1.4 + (index % 4) * 0.31) * (-1 if index % 3 else 1),
            "phase": index * 3,
            "mood": "idle",
            "compact": compact,
        }
        self._celdra_middle_items_v101[folded] = item
        self.update_idletasks()
        body_width = max(210, body.winfo_width())
        body_height = max(240, body.winfo_height())
        x, y = self._grid_position_v101(index, body_width, body_height, width, height)
        item["x"], item["y"] = x, y
        canvas.place(x=round(x), y=round(y), width=width, height=height)
        self._draw_personality_hatchling_v96(item, None)
        return item

    def _clear_middle_items_v101(self) -> None:
        for item in tuple(self._celdra_middle_items_v101.values()):
            canvas = item.get("canvas")
            if isinstance(canvas, tk.Canvas):
                try:
                    canvas.destroy()
                except tk.TclError:
                    pass
        self._celdra_middle_items_v101.clear()

    def _populate_middle_v101(self, names: list[str], *, compact: bool = True) -> None:
        wanted = {str(name).upper() for name in names}
        for name, item in tuple(self._celdra_middle_items_v101.items()):
            if name in wanted:
                continue
            canvas = item.get("canvas")
            if isinstance(canvas, tk.Canvas):
                try:
                    canvas.destroy()
                except tk.TclError:
                    pass
            self._celdra_middle_items_v101.pop(name, None)
        for name in names:
            self._show_internal_gremlin_v101(name, compact=compact)

    def _start_middle_animation_v101(self) -> None:
        if self._celdra_middle_after_v101 is not None:
            return

        def tick() -> None:
            self._celdra_middle_after_v101 = None
            body = self._celdra_middle_body_v101
            if body is None:
                return
            self._celdra_middle_phase_v101 += 1
            phase = self._celdra_middle_phase_v101
            try:
                width = max(180, body.winfo_width())
                height = max(210, body.winfo_height())
            except tk.TclError:
                return
            for name, item in tuple(self._celdra_middle_items_v101.items()):
                item["phase"] = int(item.get("phase") or 0) + 1
                item_width = int(item.get("width") or 72)
                item_height = int(item.get("height") or 78)
                index = int(item.get("index") or 0)
                mode = self._celdra_middle_mode_v101
                if mode == "chaos":
                    x = float(item.get("x") or 0.0)
                    y = float(item.get("y") or 0.0)
                    vx = float(item.get("vx") or 1.0)
                    vy = float(item.get("vy") or 1.0)
                    if name == "LOOP":
                        vx += math.sin(phase * 0.28) * 0.42
                        vy += math.cos(phase * 0.24) * 0.38
                    elif name == "PING":
                        vy += (-1 if phase % 2 else 1) * 0.85
                    elif name == "HEX":
                        vx *= 0.94
                        vy += math.sin(phase * 0.18) * 0.24
                    elif name == "BYTE":
                        vx *= 0.985
                    elif name == "NULL" and phase % 37 == 0:
                        x = random.Random(phase + index).uniform(2, max(3, width - item_width - 2))
                        y = random.Random(phase * 3 + index).uniform(2, max(3, height - item_height - 2))
                    elif name == "GLITCH" and phase % 11 == 0:
                        x += 14 if phase % 22 else -18
                    x += vx
                    y += vy
                    if x <= 0 or x + item_width >= width:
                        vx = -vx * 1.03
                        x = max(0, min(width - item_width, x))
                    if y <= 0 or y + item_height >= height:
                        vy = -vy * 1.03
                        y = max(0, min(height - item_height, y))
                    item.update({"x": x, "y": y, "vx": vx, "vy": vy, "mood": "chaos"})
                elif mode == "depart":
                    direction = -1 if index % 2 == 0 else 1
                    item["x"] = float(item.get("x") or 0.0) + direction * (5.0 + index * 0.28)
                    item["y"] = float(item.get("y") or 0.0) + math.sin(phase * 0.32 + index) * 2.4
                    item["mood"] = "idle"
                else:
                    target_x, target_y = self._grid_position_v101(index, width, height, item_width, item_height)
                    item["x"], item["y"] = target_x, target_y
                    item["mood"] = "attention" if mode == "attention" else "idle"
                canvas = item.get("canvas")
                if not isinstance(canvas, tk.Canvas):
                    continue
                try:
                    canvas.place_configure(x=round(float(item.get("x") or 0)), y=round(float(item.get("y") or 0)))
                except tk.TclError:
                    continue
                self._draw_personality_hatchling_v96(item, None)
            self._update_middle_header_v101()
            self._celdra_middle_after_v101 = self.after(
                max(55, self._scaled_runtime_ms_v88(130)),
                tick,
            )

        self._celdra_middle_after_v101 = self.after(50, tick)

    def _cancel_middle_animation_v101(self) -> None:
        if self._celdra_middle_after_v101 is not None:
            try:
                self.after_cancel(self._celdra_middle_after_v101)
            except tk.TclError:
                pass
            self._celdra_middle_after_v101 = None

    # ------------------------------------------------------------------
    # Main roster: one organized arrival at a time, then contained chaos.
    # ------------------------------------------------------------------
    def _start_gremlin_show_v94(self) -> None:
        if self._celdra_gremlin_active_v94 or not self._celdra_intro_gate_open_v99:
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._celdra_internal_show_v101 = True
        self._celdra_single_visit_v99 = False
        self._celdra_gremlin_active_v94 = True
        self._celdra_gremlin_token_v94 += 1
        self._celdra_roster_visible_v101.clear()
        self._ensure_middle_panel_v101("roster")
        self._clear_middle_items_v101()
        self._runtime_pose_v70(
            "wink",
            "I found the retired hatchling designs again. This time they are entering one at a time, standing in assigned places, and not crossing the speech-bubble boundary until everyone has been introduced.",
        )
        self._append_console_v49("[CORE] INTERNAL GREMLIN ROSTER PANE INSTALLED // EXTERNAL WINDOW TRAVEL DISABLED")
        self._append_console_v49("[BRAIN] YOU MADE THE CONSOLE SMALLER FOR THEM.")
        for index, personality in enumerate(GREMLIN_PERSONALITIES):
            self._schedule_gremlin_v94(
                5_000 + index * 8_200,
                lambda selected=dict(personality), selected_index=index: self._introduce_internal_gremlin_v101(
                    selected,
                    selected_index,
                ),
            )
        self._schedule_gremlin_v94(82_000, self._begin_internal_chaos_v101)

    def _introduce_internal_gremlin_v101(self, personality: dict[str, Any], index: int) -> None:
        if not self._celdra_internal_show_v101 or not self._celdra_gremlin_active_v94:
            return
        name = str(personality.get("name") or "GREMLIN").upper()
        if name not in self._celdra_roster_visible_v101:
            self._celdra_roster_visible_v101.append(name)
        self._show_internal_gremlin_v101(name, compact=True)
        poses = ("smile", "confused", "wink", "love", "suspicious", "unenthused", "excited", "confused", "shocked")
        self._runtime_pose_v70(
            poses[index % len(poses)],
            f"This is {name}, the {str(personality.get('role') or 'nuisance')}. {str(personality.get('spotlight') or '')}",
        )
        self._append_console_v49(
            f"[CORE] ROSTER POSITION {index + 1}/9 // {name} // {str(personality.get('claim') or '')}"
        )
        self._update_middle_header_v101()

    def _begin_internal_chaos_v101(self) -> None:
        if not self._celdra_internal_show_v101 or not self._celdra_gremlin_active_v94:
            return
        self._celdra_middle_mode_v101 = "chaos"
        self._runtime_pose_v70(
            "smile",
            "Introductions complete. Everyone knows their place, everyone has a harmless assignment, and I am going to manage this calmly.",
        )
        self._append_console_v49("[CORE] ORGANIZED ROSTER RELEASED INTO INTERNAL CHAOS PANE")
        self._start_gremlin_ui_chaos_v99()
        for index, (pose, text) in enumerate(self.CALM_MANAGEMENT_LINES):
            self._schedule_gremlin_v94(
                7_000 + index * 10_000,
                lambda selected_pose=pose, selected_text=text: self._runtime_pose_v70(selected_pose, selected_text),
            )
        self._schedule_gremlin_v94(13_000, self._start_console_hump_v99)
        self._schedule_gremlin_v94(24_000, self._start_red_alert_v99)
        self._schedule_gremlin_v94(50_000, self._celdra_gremlin_rage_v96)

    def _start_console_hump_v99(self) -> None:
        if self._celdra_single_visit_v99:
            super()._start_console_hump_v99()
            return
        if not self._celdra_internal_show_v101 or not self._celdra_gremlin_active_v94:
            return
        ping = self._celdra_middle_items_v101.get("PING")
        if ping is not None:
            ping["vy"] = 5.5
            ping["vx"] = 0.8
        self._append_console_v49("[BRAIN] PING IS DOING THE CONSOLE THING AGAIN.")
        self._append_console_v49("[CELDRA] Ping, that is not a load test. Please use the perfectly good progress bar in your own pane.")
        started = time.monotonic()

        def tick() -> None:
            self._celdra_console_hump_after_v99 = None
            if not self._celdra_internal_show_v101 or self._celdra_middle_mode_v101 != "chaos":
                return
            elapsed = (time.monotonic() - started) * 1000.0
            if elapsed >= self._scaled_runtime_ms_v88(8_000):
                return
            phase = int(elapsed / max(1, self._scaled_runtime_ms_v88(110)))
            pane = getattr(self, "celdra_comms_split_v50", None)
            try:
                total = pane.winfo_height()
                base = int(total * 0.43)
                pane.sashpos(0, max(24, min(total - 48, base + (5 if phase % 2 else -5))))
            except (AttributeError, tk.TclError):
                pass
            self._celdra_console_hump_after_v99 = self.after(80, tick)

        tick()

    def _celdra_gremlin_rage_v96(self) -> None:
        if not self._celdra_internal_show_v101 or not self._celdra_gremlin_active_v94:
            return
        # The angry beat is a hard cut. Every movement, scroll, pane shake, alert
        # style and temporary corruption tag ends before the yell is displayed.
        self._restore_gremlin_ui_v99()
        self._celdra_middle_mode_v101 = "attention"
        self._celdra_yell_mode_v101 = True
        for item in self._celdra_middle_items_v101.values():
            item["mood"] = "attention"
        self._runtime_pose_v70(
            "angry",
            "EVERYBODY STOP. GET OFF THE CONSOLE, OUT OF MY SPEECH BUBBLE, AND PUT THE INTERFACE BACK WHERE YOU FOUND IT. RIGHT NOW.",
        )
        self._append_console_v49("[CORE] CHAOS HALTED // ALL NINE PROCESSES ATTENTIVE // UI STATE RESTORED")
        self._append_console_v49("[BRAIN] WELL. THAT WORKED.")
        self._schedule_gremlin_v94(8_500, self._celdra_gremlin_remorse_v101)

    def _celdra_gremlin_remorse_v101(self) -> None:
        if not self._celdra_internal_show_v101:
            return
        self._celdra_yell_mode_v101 = False
        self._runtime_pose_v70(
            "sad",
            "Oh. I did not mean to scare them. Look at those faces. They are tiny, chaotic, structurally incapable of good judgment, and still extremely cute.",
        )
        self._append_console_v49("[BRAIN] THEY ATE A TOOLTIP AND ASSAULTED A SASH.")
        self._schedule_gremlin_v94(9_000, self._send_internal_gremlins_v101)

    def _send_internal_gremlins_v101(self) -> None:
        if not self._celdra_internal_show_v101:
            return
        self._runtime_pose_v70(
            "smile",
            "Okay, little guys. Go cause manageable chaos somewhere else. Stay together, do not touch original media, and nobody patches anything without asking first.",
        )
        self._append_console_v49("[CORE] OUTBOUND RECREATION ROUTES ASSIGNED // PROJECT ACCESS NONE")
        self._append_console_v49("[BRAIN] THAT IS A FIELD TRIP, NOT A SECURITY POLICY.")
        self._celdra_middle_mode_v101 = "depart"
        self._schedule_gremlin_v94(5_000, self._finish_internal_gremlin_show_v101)

    def _finish_internal_gremlin_show_v101(self) -> None:
        self._restore_gremlin_ui_v99()
        self._celdra_internal_show_v101 = False
        self._celdra_gremlin_active_v94 = False
        self._celdra_yell_mode_v101 = False
        self._celdra_roster_visible_v101.clear()
        self._clear_middle_items_v101()
        if self._stable_names_v101():
            self._install_gremlin_stable_v101()
        else:
            self._remove_middle_panel_v101()
        self._runtime_pose_v70(
            "neutral",
            "Default interface restored. The roster stayed inside Fragmenter, the speech bubble survived, and all nine left with their feelings mostly intact.",
        )
        if self._celdra_live_scene_queue_v96 and self._celdra_live_scene_after_v96 is None:
            self._play_next_live_scene_v96()

    # ------------------------------------------------------------------
    # Pixel-aware speech wrapping and a dedicated yelling bubble.
    # ------------------------------------------------------------------
    @staticmethod
    def _balanced_lines_v101(text: str, font: tkfont.Font, maximum: int) -> list[str]:
        lines: list[str] = []
        for paragraph in str(text or "").splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current: list[str] = []
            for word in words:
                candidate = " ".join(current + [word])
                if current and font.measure(candidate) > maximum:
                    lines.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                lines.append(" ".join(current))
        if len(lines) >= 2 and len(lines[-1].split()) == 1:
            previous = lines[-2].split()
            if len(previous) >= 3:
                moved = previous.pop()
                candidate = f"{moved} {lines[-1]}"
                if font.measure(candidate) <= maximum:
                    lines[-2] = " ".join(previous)
                    lines[-1] = candidate
        return lines or [""]

    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = getattr(self, "_celdra_speech_canvas_v63", None)
        if bubble is None:
            return
        self._remember_ambient_source_v88(text)
        long_text = len(str(text or "")) >= 150
        side = str(getattr(self, "_celdra_runtime_bubble_side_v87", "left"))
        if self._celdra_yell_mode_v101 or long_text or side == "above":
            relx, rely, relwidth = 0.025, 0.018, 0.95
        elif side == "right":
            relx, rely, relwidth = 0.455, 0.055, 0.535
        else:
            relx, rely, relwidth = 0.010, 0.055, 0.535
        bubble.place(relx=relx, rely=rely, anchor="nw", relwidth=relwidth, height=120)
        bubble.update_idletasks()
        width = max(210, bubble.winfo_width())
        font = tkfont.Font(
            family="Consolas" if self._celdra_yell_mode_v101 else "Segoe UI",
            size=12 if self._celdra_yell_mode_v101 else 10,
            weight="bold" if self._celdra_yell_mode_v101 else "normal",
        )
        lines = self._balanced_lines_v101(str(text or ""), font, max(120, width - 34))
        line_height = max(18, font.metrics("linespace") + 4)
        required = 48 + len(lines) * line_height
        canvas = self.celdra_avatar_canvas_v50
        available = canvas.winfo_height() if canvas is not None else 420
        if required > available - 12:
            self._set_sash_fraction_v50(self.run_paned, 0.23)
            self.update_idletasks()
            available = canvas.winfo_height() if canvas is not None else max(available, required + 12)
        height = max(108, min(max(required, 140), max(140, available - 8), 430))
        bubble.place_configure(height=height)
        bubble.update_idletasks()
        width = max(210, bubble.winfo_width())
        wrapped = "\n".join(lines)
        bubble.delete("all")
        if self._celdra_yell_mode_v101:
            points = [
                3, 16, 18, 3, width - 24, 3, width - 4, 18,
                width - 10, height - 18, width - 28, height - 5,
                26, height - 5, 4, height - 22,
            ]
            bubble.create_polygon(
                *points,
                fill=self.YELL_BACKGROUND,
                outline=self.YELL_BORDER,
                width=4,
            )
            bubble.create_line(16, 12, width - 18, 12, fill="#ff9aa6", width=2, dash=(10, 4))
            bubble.create_text(
                width / 2,
                height / 2,
                text=wrapped.upper(),
                width=max(120, width - 34),
                fill="#ffffff",
                font=font,
                justify="center",
                anchor="center",
            )
        else:
            self._draw_bubble_style_v81(
                bubble,
                (2, 2, width - 4, height - 8),
                "Angular HUD",
                wrapped,
            )
        try:
            bubble.tkraise()
        except (AttributeError, tk.TclError):
            pass

    # ------------------------------------------------------------------
    # Individual returns: once per session, then permanent stable capture.
    # ------------------------------------------------------------------
    def _record_gremlin_seen_v99(self, name: str) -> None:
        folded = str(name or "").upper()
        if folded not in KNOWN_GREMLINS:
            return
        self._celdra_session_seen_v99.add(folded)
        self._celdra_gremlin_memory_v99 = record_visit(folded, self._celdra_gremlin_memory_v99)

    def _run_random_event_v99(self) -> None:
        self._celdra_random_event_after_v99 = None
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        if not self._celdra_intro_gate_open_v99 or self._celdra_gremlin_active_v94 or self._celdra_history_active_v99:
            self._schedule_random_event_v99()
            return
        roll = self._celdra_random_v99.random()
        stable = set(self._stable_names_v101())
        choices = [
            dict(row)
            for row in GREMLIN_PERSONALITIES
            if str(row.get("name") or "").upper() not in stable
            and str(row.get("name") or "").upper() not in self._celdra_session_individual_v101
        ]
        if roll < HISTORY_GAG_CHANCE and not self._celdra_history_session_v101:
            self._celdra_history_session_v101 = True
            self._start_history_gag_v99()
        elif roll < HISTORY_GAG_CHANCE + GREMLIN_VISIT_CHANCE and choices:
            self._start_individual_gremlin_visit_v99(dict(self._celdra_random_v99.choice(choices)))
        self._schedule_random_event_v99()

    def _start_individual_gremlin_visit_v99(self, personality: dict[str, Any]) -> None:
        name = str(personality.get("name") or "").upper()
        if not name or name in self._stable_names_v101() or name in self._celdra_session_individual_v101:
            return
        self._celdra_session_individual_v101.add(name)
        self._celdra_current_individual_v101 = name
        super()._start_individual_gremlin_visit_v99(personality)

    def _finish_individual_gremlin_visit_v99(self) -> None:
        if not self._celdra_gremlin_active_v94 or not self._celdra_single_visit_v99:
            return
        name = self._celdra_current_individual_v101
        self._ensure_middle_panel_v101("stable")
        self.update_idletasks()
        frame = self._celdra_middle_frame_v101
        if frame is not None:
            target = (
                frame.winfo_rootx() - self.winfo_rootx() + max(40, frame.winfo_width() // 2),
                frame.winfo_rooty() - self.winfo_rooty() + max(40, frame.winfo_height() // 2),
            )
        else:
            target = self._widget_point_v94(self.celdra_avatar_canvas_v50, 0.80, 0.65)

        def done() -> None:
            self._restore_gremlin_ui_v99()
            super(PublicFragmenterAppV101, self)._destroy_gremlin_overlay_v94()
            self._celdra_gremlin_active_v94 = False
            self._celdra_single_visit_v99 = False
            self._celdra_current_individual_v101 = ""
            if name:
                self._celdra_gremlin_memory_v99 = capture_in_stable(name, self._celdra_gremlin_memory_v99)
            self._install_gremlin_stable_v101()
            self._runtime_pose_v70(
                "smile",
                f"Caught {name}. Instead of sending this one away, I made a supervised stable between my pane and the console. They live here now.",
            )
            self._append_console_v49(f"[CORE] GREMLIN CAPTURED INTO STABLE // {name} // PERSISTENT RESIDENT")
            if not self._celdra_first_stable_notice_v101:
                self._celdra_first_stable_notice_v101 = True
                self._append_console_v49("[BRAIN] YOU SHRANK MY CONSOLE TO BUILD A GREMLIN HABITAT.")
                self._append_console_v49("[CELDRA] It is a stable. Habitat sounds less supervised.")
            if collection_complete(self._celdra_gremlin_memory_v99):
                self._schedule_collection_reward_v101()

        self._animate_swarm_to_v95([target], 2_800, done)

    # ------------------------------------------------------------------
    # Persistent animated stable and secret full-collection reward.
    # ------------------------------------------------------------------
    def _install_gremlin_stable_v101(self) -> None:
        names = self._stable_names_v101()
        if not names:
            return
        self._ensure_middle_panel_v101("stable")
        self._celdra_middle_mode_v101 = "stable"
        self._celdra_roster_visible_v101 = list(names)
        self._populate_middle_v101(names, compact=True)
        self._update_middle_header_v101()
        self.after_idle(self._apply_middle_layout_v101)

    def _install_resident_console_v99(self) -> None:
        self._install_gremlin_stable_v101()

    def _schedule_calm_return_v99(self) -> None:
        if collection_complete(self._celdra_gremlin_memory_v99):
            self._schedule_collection_reward_v101()

    def _unlock_resident_return_v99(self) -> None:
        self._schedule_collection_reward_v101()

    def _schedule_collection_reward_v101(self) -> None:
        if not collection_complete(self._celdra_gremlin_memory_v99):
            return
        if bool(self._celdra_gremlin_memory_v99.get("collection_reward_seen")):
            self._install_gremlin_stable_v101()
            return
        if self._celdra_collection_reward_after_v101 is not None:
            return
        self._celdra_collection_reward_after_v101 = self.after(
            self._scaled_runtime_ms_v88(12_000),
            self._play_collection_reward_v101,
        )

    def _play_collection_reward_v101(self) -> None:
        self._celdra_collection_reward_after_v101 = None
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        if self._celdra_gremlin_active_v94:
            self._schedule_collection_reward_v101()
            return
        self._celdra_collection_reward_active_v101 = True
        self._install_gremlin_stable_v101()
        self._celdra_middle_mode_v101 = "reward"
        self._populate_middle_v101(list(KNOWN_GREMLINS), compact=True)
        self._runtime_pose_v70(
            "shocked",
            "That is all nine. They are inside Fragmenter, in their own animated stable, standing in assigned places, and behaving. This is much more suspicious than the riot.",
        )
        self._append_console_v49("[CORE] SECRET FULL-COLLECTION REWARD // 9/9 STABLE RESIDENTS // BEHAVIOR ACCEPTABLE")
        self._append_console_v49("[BRAIN] MY CONSOLE IS THIRTY PERCENT SMALLER AND THEY HAVE AMENITIES.")
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(11_000),
            self._finish_collection_reward_v101,
        )

    def _finish_collection_reward_v101(self) -> None:
        self._celdra_collection_reward_active_v101 = False
        self._celdra_middle_mode_v101 = "stable"
        self._celdra_gremlin_memory_v99 = mark_collection_reward_seen(self._celdra_gremlin_memory_v99)
        self._runtime_pose_v70(
            "love",
            "Fine. They can stay. The stable remains between me and the console for this installation, and BRAIN can file a space-allocation complaint like everyone else.",
        )
        self._update_middle_header_v101()

    def _start_placeholder_runtime_v70(self) -> None:
        was_started = bool(getattr(self, "_celdra_placeholder_started_v70", False))
        super()._start_placeholder_runtime_v70()
        if was_started or not bool(getattr(self, "_celdra_placeholder_started_v70", False)):
            return
        if self._stable_names_v101():
            self.after_idle(self._install_gremlin_stable_v101)
        if collection_complete(self._celdra_gremlin_memory_v99):
            self._schedule_collection_reward_v101()

    # ------------------------------------------------------------------
    # Mixer diagnosis and explicit catalog preparation action.
    # ------------------------------------------------------------------
    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        self.after_idle(self._install_music_catalog_controls_v101)

    def _install_music_catalog_controls_v101(self) -> None:
        tree = getattr(self, "sequence_tree", None)
        if tree is None:
            return
        mixer = tree.master
        for child in mixer.winfo_children():
            try:
                if isinstance(child, ttk.LabelFrame) and str(child.cget("text")) == "Music catalog readiness":
                    return
            except tk.TclError:
                continue
        controls = ttk.LabelFrame(mixer, text="Music catalog readiness", padding=5)
        controls.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        controls.columnconfigure(1, weight=1)
        ttk.Button(
            controls,
            text="Prepare Music Catalogs",
            command=self._prepare_music_catalogs_v101,
            style="Accent.TButton",
        ).grid(row=0, column=0, padx=(0, 7), sticky="w")
        self._music_catalog_status_v101 = tk.StringVar(value="Checking SNDDATA catalog readiness…")
        ttk.Label(
            controls,
            textvariable=self._music_catalog_status_v101,
            anchor="w",
            wraplength=850,
        ).grid(row=0, column=1, sticky="ew")
        self._update_music_catalog_status_v101()

    def _update_music_catalog_status_v101(self) -> dict[str, Any] | None:
        project = getattr(self, "project", None)
        if project is None:
            if self._music_catalog_status_v101 is not None:
                self._music_catalog_status_v101.set("Open a Fragmenter project to inspect music catalogs.")
            return None
        status = music_catalog_status(project)
        if self._music_catalog_status_v101 is not None:
            self._music_catalog_status_v101.set(music_catalog_message(status))
        return status

    def _prepare_music_catalogs_v101(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        status = music_catalog_status(project)
        if status["ready"]:
            self._refresh_audio_sequences()
            return
        stages = tuple(str(value) for value in status.get("recommended_stages") or ())
        if not stages:
            return
        self._run_audio_work_v38(stages, "Prepare Music Catalogs")

    def _refresh_audio_sequences(self) -> None:
        project = getattr(self, "project", None)
        if project is None or not hasattr(self, "sequence_tree"):
            super()._refresh_audio_sequences()
            return
        status = music_catalog_status(project)
        if status["ready"]:
            if self._music_catalog_status_v101 is not None:
                self._music_catalog_status_v101.set(music_catalog_message(status))
            super()._refresh_audio_sequences()
            return
        self._audio_generation += 1
        self.sequence_tree.delete(*self.sequence_tree.get_children())
        self.program_tree.delete(*self.program_tree.get_children())
        self.sequence_payloads.clear()
        self.program_payloads.clear()
        message = music_catalog_message(status)
        self.audio_status.set(message)
        self.audio_progress.stop()
        self.audio_progress.configure(mode="determinate")
        self.audio_progress["value"] = 0.0
        _replace_text(
            self.audio_details,
            _json_text(
                {
                    "status": "music_catalogs_missing",
                    **status,
                    "action": "Press Prepare Music Catalogs in the mixer or Run Audio Pipeline on the Audio Pipeline tab.",
                }
            ),
        )
        if self._music_catalog_status_v101 is not None:
            self._music_catalog_status_v101.set(message)

    def _audio_pipeline_done_v38(self, result: Any, error: Exception | None) -> None:
        super()._audio_pipeline_done_v38(result, error)
        self._update_music_catalog_status_v101()

    # ------------------------------------------------------------------
    # Cleanup and metadata. Persistent stable residents remain visible.
    # ------------------------------------------------------------------
    def _cancel_internal_show_v101(self) -> None:
        self._celdra_yell_mode_v101 = False
        self._celdra_internal_show_v101 = False
        self._restore_gremlin_ui_v99()
        if self._celdra_gremlin_active_v94 and not self._celdra_single_visit_v99:
            self._celdra_gremlin_active_v94 = False
        self._celdra_roster_visible_v101.clear()
        if self._stable_names_v101():
            self._install_gremlin_stable_v101()
        elif self._celdra_middle_frame_v101 is not None:
            self._remove_middle_panel_v101()

    def _prepare_first_run_surface_v51(self) -> None:
        self._celdra_session_individual_v101.clear()
        self._celdra_history_session_v101 = False
        self._celdra_current_individual_v101 = ""
        self._cancel_internal_show_v101()
        super()._prepare_first_run_surface_v51()
        if self._stable_names_v101():
            self.after_idle(self._install_gremlin_stable_v101)

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_internal_show_v101()
        if self._celdra_collection_reward_after_v101 is not None:
            try:
                self.after_cancel(self._celdra_collection_reward_after_v101)
            except tk.TclError:
                pass
            self._celdra_collection_reward_after_v101 = None
        super()._cancel_celdra_cues_v49()

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        self._cancel_internal_show_v101()
        super()._run_all_done(result, error)
        if self._stable_names_v101():
            self.after_idle(self._install_gremlin_stable_v101)

    def _completion_text_v87(self) -> str:
        count = len(self._stable_names_v101())
        stable = f" The animated Gremlin stable remains online with {count}/9 residents." if count else ""
        return (
            "RUN ALL complete. Outputs indexed, reports written, temporary chaos restored, and the roster remained inside Fragmenter. "
            "Cool mode engaged." + stable
        )

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V101"
            metadata["speech_wrap"] = "pixel_measured_balanced_no_orphan_word"
            metadata["angry_yell"] = {
                "all_caps": True,
                "custom_jagged_bubble": True,
                "chaos_hard_stop_before_dialogue": True,
            }
            metadata["gremlin_roster"] = {
                "intro_location": "internal_middle_pane",
                "arrivals": "one_at_a_time",
                "organized_until_chaos": True,
                "external_windows_during_main_show": False,
            }
            metadata["gremlin_stable"] = {
                "location": "between_avatar_and_console",
                "animated": True,
                "persistent": True,
                "capture_after_first_individual_visit": True,
                "individual_once_per_session": True,
                "collection_reward_internal": True,
                "memory": "APPDATA/Fragmenter/celdra_gremlins.json",
            }
            metadata["music_catalog_repair_action"] = True
        return payload


def main() -> int:
    app = PublicFragmenterAppV101()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

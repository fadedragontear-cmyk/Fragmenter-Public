#!/usr/bin/env python3
"""Egg-first startup, expanded stable, padded art, and resident behavior for V103."""
from __future__ import annotations

import math
import random
import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_gremlin_art_v2 import draw_gremlin
from celdra_gremlin_memory_v1 import KNOWN_GREMLINS


class DragoneggStableMixinV103:
    STABLE_STATUS_GAGS = {
        "BYTE": ("TOOLTIP RATIONS", "DOCUMENTATION CONSUMED", "METADATA CRUMBS"),
        "HEX": ("OFFSET PATROL", "COORDINATE FOOTPRINTS", "0x ROUTE VERIFIED"),
        "CACHE": ("BRAIN COMPLAINT CACHE", "LOG SATCHEL CAPACITY", "RECENT LINES HOARDED"),
        "LOOP": ("ROUTE COMPLETE", "RESTARTING ROUTE", "SUCCESS REPEATED"),
        "PING": ("STABLE LATENCY TEST", "PROGRESS BAR PERCUSSION", "BOUNCE DIAGNOSTIC"),
        "PATCH": ("HORN TICKETS OPEN", "UNREQUESTED REPAIRS", "WRENCH AUTHORITY 0"),
        "ROOT": ("SELF-ASSIGNED QUORUM", "PARTY ADMIN CLAIM", "TERMS ACCEPTED 0"),
        "NULL": ("RESIDENT LOOKUP", "PROCESS NOT FOUND", "PROCESS STILL VISIBLE"),
        "GLITCH": ("STATUS DUPLICATION", "REDUNDANCY THREAT", "VISUAL FAULT TOLERANCE"),
    }

    def __init__(self) -> None:
        self._celdra_stable_reveal_v103 = False
        self._celdra_stable_status_var_v103: tk.StringVar | None = None
        self._celdra_stable_status_bar_v103: ttk.Progressbar | None = None
        self._celdra_stable_status_after_v103: str | None = None
        self._celdra_stable_status_phase_v103 = 0
        self._celdra_middle_hidden_v103 = False
        super().__init__()

    def _install_gremlin_stable_v101(self) -> None:
        if not self._celdra_stable_reveal_v103:
            return
        super()._install_gremlin_stable_v101()
        self._ensure_stable_status_v103()

    def _start_placeholder_runtime_v70(self) -> None:
        was_open = bool(getattr(self, "_celdra_intro_gate_open_v99", False))
        super()._start_placeholder_runtime_v70()
        if was_open or not bool(getattr(self, "_celdra_intro_gate_open_v99", False)):
            return
        self._celdra_stable_reveal_v103 = True
        if self._stable_names_v101():
            self.after(self._scaled_runtime_ms_v88(6_000), self._install_gremlin_stable_v101)

    def _finish_individual_gremlin_visit_v99(self) -> None:
        self._celdra_stable_reveal_v103 = True
        super()._finish_individual_gremlin_visit_v99()

    def _play_collection_reward_v101(self) -> None:
        self._celdra_stable_reveal_v103 = True
        super()._play_collection_reward_v101()

    def _ensure_middle_panel_v101(self, mode: str) -> None:
        super()._ensure_middle_panel_v101(mode)
        self._ensure_stable_status_v103()

    def _ensure_stable_status_v103(self) -> None:
        frame = self._celdra_middle_frame_v101
        if frame is None or not frame.winfo_exists():
            return
        bar_alive = False
        if self._celdra_stable_status_bar_v103 is not None:
            try:
                bar_alive = bool(self._celdra_stable_status_bar_v103.winfo_exists())
            except tk.TclError:
                bar_alive = False
        if not bar_alive:
            self._cancel_stable_status_v103()
            self._celdra_stable_status_var_v103 = tk.StringVar(value="STABLE STATUS // WAITING FOR RESIDENTS")
            tk.Label(
                frame,
                textvariable=self._celdra_stable_status_var_v103,
                background="#071426",
                foreground="#9edfff",
                font=("Consolas", 8, "bold"),
                anchor="w",
                padx=6,
                pady=2,
            ).grid(row=2, column=0, sticky="ew", pady=(3, 0))
            self._celdra_stable_status_bar_v103 = ttk.Progressbar(
                frame, orient="horizontal", mode="determinate", maximum=100, value=0
            )
            self._celdra_stable_status_bar_v103.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self._start_stable_status_v103()

    def _start_stable_status_v103(self) -> None:
        if self._celdra_stable_status_after_v103 is not None:
            return

        def tick() -> None:
            self._celdra_stable_status_after_v103 = None
            label, bar, frame = (
                self._celdra_stable_status_var_v103,
                self._celdra_stable_status_bar_v103,
                self._celdra_middle_frame_v101,
            )
            if label is None or bar is None or frame is None or not frame.winfo_exists():
                return
            self._celdra_stable_status_phase_v103 += 1
            phase = self._celdra_stable_status_phase_v103
            mode = str(self._celdra_middle_mode_v101 or "stable")
            names = self._stable_names_v101()
            if mode == "roster":
                count = len(self._celdra_roster_visible_v101)
                label.set(f"ROSTER STATUS // {count}/9 INTRODUCED // CHAOS LOCKED")
                value = count / max(1, len(KNOWN_GREMLINS)) * 100
            elif mode == "attention":
                label.set("DISCIPLINE STATUS // 9/9 ATTENTIVE // FEELINGS: BRUISED")
                value = 100
            elif mode == "reward":
                label.set("FULL COLLECTION // GOOD BEHAVIOR PROBABILITY: SUSPICIOUS")
                value = 100
            elif names:
                name = names[(phase // 2) % len(names)]
                phrases = self.STABLE_STATUS_GAGS.get(name, ("RESIDENT ACTIVE",))
                phrase = phrases[(phase // max(1, len(names))) % len(phrases)]
                label.set(f"{name} // {phrase} // RESIDENTS {len(names)}/9")
                value = (phase * 13 + KNOWN_GREMLINS.index(name) * 9) % 101
            else:
                label.set("STABLE STATUS // EMPTY // NEXT VISITOR UNRESOLVED")
                value = 0
            try:
                bar["value"] = value
            except tk.TclError:
                return
            self._celdra_stable_status_after_v103 = self.after(
                max(650, self._scaled_runtime_ms_v88(1_750)), tick
            )

        self._celdra_stable_status_after_v103 = self.after(250, tick)

    def _cancel_stable_status_v103(self) -> None:
        if self._celdra_stable_status_after_v103 is not None:
            try:
                self.after_cancel(self._celdra_stable_status_after_v103)
            except tk.TclError:
                pass
            self._celdra_stable_status_after_v103 = None

    def _apply_middle_layout_v101(self) -> None:
        pane, frame = getattr(self, "celdra_visual_split_v50", None), self._celdra_middle_frame_v101
        if pane is None or frame is None or self._celdra_middle_hidden_v103:
            return
        try:
            self.update_idletasks()
            width = max(500, pane.winfo_width())
            if len(tuple(pane.panes())) >= 3:
                pane.sashpos(0, round(width * 0.34))
                pane.sashpos(1, round(width * 0.80))
        except (AttributeError, tk.TclError):
            pass

    def _show_internal_gremlin_v101(self, name: str, *, compact: bool = True) -> dict[str, Any] | None:
        item = super()._show_internal_gremlin_v101(name, compact=compact)
        if item is None or item.get("v103_padded"):
            return item
        canvas = item.get("canvas")
        if not isinstance(canvas, tk.Canvas):
            return item
        old_w, old_h = int(item.get("width") or 80), int(item.get("height") or 84)
        pad_x = 22 if str(name).upper() in {"BYTE", "CACHE", "PATCH", "ROOT"} else 14
        item.update(v103_padded=True, art_width=old_w, art_height=old_h,
                    art_offset_x=pad_x // 2, art_offset_y=4, width=old_w + pad_x, height=old_h + 8)
        try:
            canvas.configure(width=old_w + pad_x, height=old_h + 8)
            canvas.place_configure(width=old_w + pad_x, height=old_h + 8)
        except tk.TclError:
            pass
        self._draw_personality_hatchling_v96(item, None)
        return item

    def _create_gremlin_window_v99(self, index: int, personality: dict[str, Any], x: int, y: int) -> dict[str, Any]:
        item = super()._create_gremlin_window_v99(index, personality, x, y)
        canvas, holder = item.get("canvas"), item.get("holder")
        if not isinstance(canvas, tk.Canvas) or not isinstance(holder, tk.Toplevel):
            return item
        old_w, old_h = int(item.get("width") or 82), int(item.get("height") or 84)
        name = str(personality.get("name") or "").upper()
        pad_x = 24 if name in {"BYTE", "CACHE", "PATCH", "ROOT"} else 16
        item.update(art_width=old_w, art_height=old_h, art_offset_x=pad_x // 2,
                    art_offset_y=5, width=old_w + pad_x, height=old_h + 10)
        try:
            canvas.configure(width=old_w + pad_x, height=old_h + 10)
            holder.geometry(f"{old_w + pad_x}x{old_h + 10}")
        except tk.TclError:
            pass
        self._place_gremlin_window_v99(item, x, y)
        self._draw_personality_hatchling_v96(item, None)
        return item

    def _draw_personality_hatchling_v96(self, item: dict[str, Any], _frame: Any) -> None:
        canvas = item.get("canvas")
        if not isinstance(canvas, tk.Canvas):
            return
        personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
        mood = str(item.get("mood") or ("chaos" if self._celdra_middle_mode_v101 == "chaos" else "idle"))
        draw_gremlin(
            canvas,
            personality,
            width=int(item.get("art_width") or item.get("width") or 82),
            height=int(item.get("art_height") or item.get("height") or 88),
            phase=int(item.get("phase") or item.get("frame") or 0),
            mood=mood,
            compact=bool(item.get("compact")),
            show_name=True,
        )
        try:
            canvas.move("v101_gremlin", int(item.get("art_offset_x") or 0), int(item.get("art_offset_y") or 0))
        except tk.TclError:
            pass

    def _start_middle_animation_v101(self) -> None:
        if self._celdra_middle_after_v101 is not None:
            return

        def tick() -> None:
            self._celdra_middle_after_v101 = None
            body = self._celdra_middle_body_v101
            if body is None or not body.winfo_exists():
                return
            self._celdra_middle_phase_v101 += 1
            phase = self._celdra_middle_phase_v101
            try:
                width, height = max(220, body.winfo_width()), max(230, body.winfo_height())
            except tk.TclError:
                return
            mode = str(self._celdra_middle_mode_v101 or "stable")
            for name, item in tuple(self._celdra_middle_items_v101.items()):
                item["phase"] = int(item.get("phase") or 0) + 1
                iw, ih, index = int(item.get("width") or 82), int(item.get("height") or 88), int(item.get("index") or 0)
                canvas = item.get("canvas")
                if not isinstance(canvas, tk.Canvas):
                    continue
                visible = True
                if mode == "stable":
                    x, y, visible = self._stable_position_v103(name, item, phase, width, height, iw, ih)
                    item.update(x=x, y=y, mood="idle")
                elif mode == "depart":
                    item["x"] = float(item.get("x") or 0) + (-1 if index % 2 == 0 else 1) * (5 + index * .28)
                    item["y"] = float(item.get("y") or 0) + math.sin(phase * .32 + index) * 2.4
                    item["mood"] = "idle"
                else:
                    x, y = self._grid_position_v101(index, width, height, iw, ih)
                    item.update(x=x, y=y, mood="attention" if mode == "attention" else "idle")
                try:
                    if visible:
                        canvas.place_configure(x=round(float(item.get("x") or 0)), y=round(float(item.get("y") or 0)), width=iw, height=ih)
                        self._draw_personality_hatchling_v96(item, None)
                    else:
                        canvas.place_forget()
                except tk.TclError:
                    continue
            self._update_middle_header_v101()
            self._celdra_middle_after_v101 = self.after(max(45, self._scaled_runtime_ms_v88(105)), tick)

        self._celdra_middle_after_v101 = self.after(50, tick)

    def _stable_position_v103(self, name: str, item: dict[str, Any], phase: int,
                              width: int, height: int, iw: int, ih: int) -> tuple[float, float, bool]:
        index = int(item.get("index") or 0)
        left, top, right, bottom = 3.0, 3.0, max(3.0, width - iw - 3.0), max(3.0, height - ih - 3.0)
        cx, cy, t = (left + right) / 2, (top + bottom) / 2, phase * .045 + index * .73
        if name == "LOOP":
            return cx + math.cos(t * 1.35) * (right-left) * .38, cy + math.sin(t * 1.35) * (bottom-top) * .34, True
        if name == "PING":
            return left + ((phase * 2.7 + index * 31) % max(1.0, right-left)), bottom - abs(math.sin(t * 2.8)) * min(54.0, bottom-top), True
        if name == "HEX":
            span_x, span_y = right-left, bottom-top
            cursor = (phase * 2.1 + index * 37) % max(4.0, 2 * (span_x + span_y))
            if cursor <= span_x: return left + cursor, top, True
            cursor -= span_x
            if cursor <= span_y: return right, top + cursor, True
            cursor -= span_y
            if cursor <= span_x: return right - cursor, bottom, True
            return left, bottom - (cursor - span_x), True
        if name == "CACHE": return left + (right-left)*.22 + math.cos(t*.55)*24, bottom-18 + math.sin(t*.75)*11, True
        if name == "PATCH": return left+8 + abs(math.sin(t*.8))*34, top + (bottom-top)*.34 + math.sin(t*2.1)*8, True
        if name == "ROOT": return cx + math.sin(t*.42)*(right-left)*.25, top+8 + abs(math.sin(t*.65))*24, True
        if name == "NULL":
            if (phase + index*11) % 92 < 14:
                return float(item.get("x") or cx), float(item.get("y") or cy), False
            rng = random.Random((phase // 92) * 7919 + index * 101)
            return rng.uniform(left, right), rng.uniform(top, bottom), True
        if name == "GLITCH":
            jump = 9 if phase % 9 == 0 else -6 if phase % 13 == 0 else 0
            x, y = cx + math.sin(t*1.8)*(right-left)*.34 + jump, cy + math.cos(t*1.33)*(bottom-top)*.32 - jump/2
            return max(left, min(right, x)), max(top, min(bottom, y)), True
        x = float(item["x"] if item.get("x") is not None else left + (index*17) % max(1.0, right-left))
        y = float(item["y"] if item.get("y") is not None else top + (index*19) % max(1.0, bottom-top))
        vx, vy = float(item.get("vx") or 1.2), float(item.get("vy") or .9)
        x, y = x + vx, y + vy
        if x <= left or x >= right: vx, x = -vx, max(left, min(right, x))
        if y <= top or y >= bottom: vy, y = -vy, max(top, min(bottom, y))
        item["vx"], item["vy"] = vx, vy
        return x, y, True

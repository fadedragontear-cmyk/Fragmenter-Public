#!/usr/bin/env python3
"""RUN ALL-bounded main Gremlin chaos for V103."""
from __future__ import annotations

import math
import random
import tkinter as tk
from typing import Any

from celdra_gremlin_memory_v1 import KNOWN_GREMLINS
from celdra_v99_content import GREMLIN_PERSONALITIES


class DragoneggChaosMixinV103:
    def __init__(self) -> None:
        self._celdra_internal_chaos_after_v103: str | None = None
        self._celdra_internal_chaos_phase_v103 = 0
        self._celdra_internal_chaos_active_v103 = False
        super().__init__()

    def _begin_internal_chaos_v101(self) -> None:
        if not self._celdra_internal_show_v101 or not self._celdra_gremlin_active_v94:
            return
        self._celdra_middle_mode_v101 = "chaos"
        self._runtime_pose_v70("smile", "Introductions complete. Everyone knows their place, everyone has a harmless assignment, and I am going to manage this calmly.")
        self._append_console_v49("[CORE] ORGANIZED ROSTER RELEASED ACROSS RUN ALL // WINDOW BOUNDS ENFORCED")
        self._hide_middle_for_chaos_v103()
        self._spawn_internal_chaos_v103()
        self._start_gremlin_ui_chaos_v99()
        for index, (pose, text) in enumerate(self.CALM_MANAGEMENT_LINES):
            self._schedule_gremlin_v94(7_000 + index * 10_000,
                lambda selected_pose=pose, selected_text=text: self._runtime_pose_v70(selected_pose, selected_text))
        self._schedule_gremlin_v94(13_000, self._start_console_hump_v99)
        self._schedule_gremlin_v94(24_000, self._start_red_alert_v99)
        self._schedule_gremlin_v94(50_000, self._celdra_gremlin_rage_v96)

    def _hide_middle_for_chaos_v103(self) -> None:
        frame, pane = self._celdra_middle_frame_v101, getattr(self, "celdra_visual_split_v50", None)
        if frame is None or pane is None or self._celdra_middle_hidden_v103:
            return
        self._cancel_middle_animation_v101()
        try:
            pane.forget(frame)
            self._celdra_middle_hidden_v103 = True
        except (AttributeError, tk.TclError):
            return
        self.after_idle(self._apply_production_layout_v91)

    def _show_middle_after_chaos_v103(self, mode: str) -> None:
        frame, pane = self._celdra_middle_frame_v101, getattr(self, "celdra_visual_split_v50", None)
        if frame is None or pane is None:
            self._ensure_middle_panel_v101(mode)
            return
        self._celdra_middle_mode_v101 = mode
        if self._celdra_middle_hidden_v103:
            try:
                pane.insert(1, frame, weight=1)
            except (AttributeError, tk.TclError):
                try: pane.add(frame, weight=1)
                except tk.TclError: return
            self._celdra_middle_hidden_v103 = False
        self._start_middle_animation_v101()
        self.after_idle(self._apply_middle_layout_v101)

    def _run_all_bounds_v103(self) -> tuple[float, float, float, float]:
        widget = getattr(self, "run_paned", None)
        if widget is None: widget = self
        try:
            self.update_idletasks()
            left, top = float(widget.winfo_rootx() - self.winfo_rootx()), float(widget.winfo_rooty() - self.winfo_rooty())
            return left, top, left + max(320, widget.winfo_width()), top + max(280, widget.winfo_height())
        except tk.TclError:
            return 0.0, 0.0, float(max(640, self.winfo_width())), float(max(480, self.winfo_height()))

    def _spawn_internal_chaos_v103(self) -> None:
        self._destroy_internal_chaos_v103()
        self._celdra_internal_chaos_active_v103 = True
        left, top, right, bottom = self._run_all_bounds_v103()
        self._celdra_gremlin_swarm_v95.clear()
        for index, personality in enumerate(GREMLIN_PERSONALITIES):
            x = left + (index % 3 + .65) * (right-left) / 3
            y = top + (index // 3 + .55) * (bottom-top) / 3
            item = self._create_gremlin_window_v99(index, dict(personality), round(x), round(y))
            holder = item.get("holder")
            if isinstance(holder, tk.Toplevel):
                try:
                    holder.attributes("-topmost", False)
                    holder.transient(self)
                except tk.TclError: pass
            item.update(internal_main_v103=True, mood="chaos",
                vx=(1.8 + index*.19) * (-1 if index % 2 else 1),
                vy=(1.4 + (index % 4)*.27) * (-1 if index % 3 else 1),
                angle_v103=index*.71, hidden_v103=False)
            self._celdra_gremlin_swarm_v95.append(item)
        self._start_internal_chaos_motion_v103()

    def _start_internal_chaos_motion_v103(self) -> None:
        if self._celdra_internal_chaos_after_v103 is not None: return

        def tick() -> None:
            self._celdra_internal_chaos_after_v103 = None
            if not self._celdra_internal_chaos_active_v103 or not self._celdra_internal_show_v101 or self._celdra_middle_mode_v101 != "chaos": return
            self._celdra_internal_chaos_phase_v103 += 1
            phase = self._celdra_internal_chaos_phase_v103
            items = [row for row in self._celdra_gremlin_swarm_v95 if row.get("internal_main_v103")]
            try: root_visible = str(self.state()) not in {"iconic", "withdrawn"}
            except tk.TclError: root_visible = False
            if not root_visible:
                for row in items:
                    holder = row.get("holder")
                    if isinstance(holder, tk.Toplevel):
                        try: holder.withdraw()
                        except tk.TclError: pass
                self._celdra_internal_chaos_after_v103 = self.after(120, tick)
                return
            left, top, right, bottom = self._run_all_bounds_v103()
            avg_x = sum(float(row.get("x") or 0) for row in items) / max(1, len(items))
            avg_y = sum(float(row.get("y") or 0) for row in items) / max(1, len(items))
            for item in items:
                personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
                name, holder = str(personality.get("name") or "GREMLIN").upper(), item.get("holder")
                if not isinstance(holder, tk.Toplevel): continue
                if not item.get("hidden_v103"):
                    try: holder.deiconify()
                    except tk.TclError: pass
                w, h = int(item.get("width") or 86), int(item.get("height") or 90)
                min_x, max_x = left+w/2, max(left+w/2, right-w/2)
                min_y, max_y = top+h/2, max(top+h/2, bottom-h/2)
                x, y = float(item.get("x") or min_x), float(item.get("y") or min_y)
                vx, vy = float(item.get("vx") or 1), float(item.get("vy") or 1)
                if name == "LOOP":
                    angle = float(item.get("angle_v103") or 0) + .075; item["angle_v103"] = angle
                    x, y = (left+right)/2 + math.cos(angle)*(right-left)*.37, (top+bottom)/2 + math.sin(angle*1.14)*(bottom-top)*.34
                elif name == "PING": x, y = x + vx*1.4, max_y - abs(math.sin(phase*.31))*min(130, max_y-min_y)
                elif name == "HEX":
                    if abs(vx) >= abs(vy): y, x = round(y/24)*24, x + vx*1.2
                    else: x, y = round(x/24)*24, y + vy*1.2
                    if phase % 43 == 0: vx, vy = -vy, vx
                elif name == "CACHE":
                    tx, ty = right-(right-left)*.17, bottom-(bottom-top)*.20
                    x, y = x+(tx-x)*.025+math.sin(phase*.09)*1.8, y+(ty-y)*.025+math.cos(phase*.11)*1.4
                elif name == "PATCH":
                    avatar = getattr(self, "celdra_avatar_canvas_v50", None)
                    try: tx, ty = avatar.winfo_rootx()-self.winfo_rootx()+avatar.winfo_width()*.52, avatar.winfo_rooty()-self.winfo_rooty()+avatar.winfo_height()*.22
                    except (AttributeError, tk.TclError): tx, ty = avg_x, avg_y
                    x, y = x+(tx-x)*.035+math.sin(phase*.45)*2.5, y+(ty-y)*.035+math.cos(phase*.37)*2
                elif name == "ROOT": x, y = x+(avg_x-x)*.018+vx*.35, y+(avg_y-y)*.018+vy*.35
                elif name == "NULL":
                    cycle = phase % 96
                    if cycle == 0:
                        rng = random.Random(phase*1009 + int(item.get("index") or 0)); x, y = rng.uniform(min_x, max_x), rng.uniform(min_y, max_y)
                    hidden = 1 <= cycle <= 13
                    if hidden != bool(item.get("hidden_v103")):
                        item["hidden_v103"] = hidden
                        try: holder.withdraw() if hidden else holder.deiconify()
                        except tk.TclError: pass
                elif name == "GLITCH":
                    x += vx + (12 if phase % 11 == 0 else -8 if phase % 17 == 0 else 0)
                    y += vy + (-9 if phase % 13 == 0 else 6 if phase % 19 == 0 else 0)
                    if phase % 47 == 0: self._append_console_v49("[GLITCH] STATUS STATUS // DUPLICATE DISPLAY ONLY // VALUES UNCHANGED")
                else: x, y = x + vx*.72, y + vy*.62  # BYTE
                if x <= min_x or x >= max_x: vx, x = -vx, max(min_x, min(max_x, x))
                if y <= min_y or y >= max_y: vy, y = -vy, max(min_y, min(max_y, y))
                item.update(x=x, y=y, vx=vx, vy=vy, phase=int(item.get("phase") or 0)+1)
                if not item.get("hidden_v103"):
                    self._place_gremlin_window_v99(item, x, y)
                    self._draw_personality_hatchling_v96(item, None)
            self._celdra_internal_chaos_after_v103 = self.after(max(24, self._scaled_runtime_ms_v88(52)), tick)

        self._celdra_internal_chaos_after_v103 = self.after(30, tick)

    def _destroy_internal_chaos_v103(self) -> None:
        self._celdra_internal_chaos_active_v103 = False
        if self._celdra_internal_chaos_after_v103 is not None:
            try: self.after_cancel(self._celdra_internal_chaos_after_v103)
            except tk.TclError: pass
            self._celdra_internal_chaos_after_v103 = None
        survivors: list[dict[str, Any]] = []
        for item in tuple(getattr(self, "_celdra_gremlin_swarm_v95", [])):
            if not item.get("internal_main_v103"): survivors.append(item); continue
            holder = item.get("holder")
            if isinstance(holder, tk.Toplevel):
                try: holder.destroy()
                except tk.TclError: pass
        self._celdra_gremlin_swarm_v95[:] = survivors

    def _celdra_gremlin_rage_v96(self) -> None:
        if not self._celdra_internal_show_v101 or not self._celdra_gremlin_active_v94: return
        self._destroy_internal_chaos_v103()
        self._show_middle_after_chaos_v103("attention")
        self._populate_middle_v101(list(KNOWN_GREMLINS), compact=True)
        super()._celdra_gremlin_rage_v96()

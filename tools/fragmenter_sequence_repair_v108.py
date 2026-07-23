#!/usr/bin/env python3
"""V108 acceptance sequence: visible progress, stable introductions, breakout, and dismissal."""
from __future__ import annotations

import math
import random
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any

from celdra_gremlin_art_v2 import design_dimensions, draw_gremlin
from celdra_gremlin_memory_v1 import KNOWN_GREMLINS
from celdra_v99_content import GREMLIN_PERSONALITIES
from fragmenter_gremlin_scene_v106 import _OffsetCanvasProxyV106
from run_all_plan_v2 import build_run_all_plan_v2


POWER_LINES_V108 = {
    "BYTE": "BYTE is eating labels and leaving the actual pipeline data untouched.",
    "HEX": "HEX has converted the work area into an offset grid and is patrolling every coordinate.",
    "CACHE": "CACHE is hoarding recent status messages in the lower-right corner.",
    "LOOP": "LOOP has found a route around the entire Run All interface and refuses to stop taking it.",
    "PING": "PING is bounce-testing the progress region. The real progress values remain protected.",
    "PATCH": "PATCH is attempting unauthorized cosmetic repairs near Celdra's horns.",
    "ROOT": "ROOT has declared temporary administrative authority over the other Gremlins.",
    "NULL": "NULL has removed itself from the display without removing itself from the process list.",
    "GLITCH": "GLITCH is duplicating presentation state. No project values or files are changing.",
}


class FragmenterSequenceRepairMixinV108:
    """Restore the accepted Run All presentation contract without changing pipeline work."""

    CHAOS_TRANSPARENT_KEY_V108 = "#010203"
    CHAOS_TICK_MS_V108 = 120
    CHAOS_REDRAW_EVERY_V108 = 5

    def __init__(self) -> None:
        self._run_stage_canvas_v108: tk.Canvas | None = None
        self._run_stage_notebook_v108: ttk.Notebook | None = None
        self._gremlin_breakout_window_v108: tk.Toplevel | None = None
        self._gremlin_breakout_canvas_v108: tk.Canvas | None = None
        self._gremlin_breakout_items_v108: dict[str, dict[str, Any]] = {}
        self._gremlin_breakout_after_v108: str | None = None
        self._gremlin_breakout_phase_v108 = 0
        self._gremlin_dismissed_v108 = False
        super().__init__()
        self._configure_progress_style_v108()
        self.after_idle(self._refresh_run_plan)

    # ------------------------------------------------------------------
    # RUN ALL progress is rendered directly into V104's final live Stages body.
    # Do not route through V89's stale scroll-host references again.
    # ------------------------------------------------------------------
    def _configure_progress_style_v108(self) -> None:
        style = ttk.Style(self)
        try:
            style.configure(
                "RunAll.Visible.Horizontal.TProgressbar",
                troughcolor="#1a2633",
                background="#45b9ea",
                lightcolor="#73d4f5",
                darkcolor="#2587b5",
                bordercolor="#315575",
                thickness=14,
            )
        except tk.TclError:
            pass

    def _live_stage_host_v108(self) -> ttk.Frame | None:
        host = getattr(self, "stage_progress_frame", None)
        if not isinstance(host, ttk.Frame):
            return None
        try:
            if not host.winfo_exists():
                return None
        except tk.TclError:
            return None
        try:
            host.columnconfigure(0, weight=0, minsize=155)
            host.columnconfigure(1, weight=1, minsize=170)
            host.columnconfigure(2, weight=0, minsize=54)
        except tk.TclError:
            return None
        canvas = host.master
        if isinstance(canvas, tk.Canvas):
            self._run_stage_canvas_v108 = canvas
            stages = canvas.master
            notebook = getattr(stages, "master", None)
            if isinstance(notebook, ttk.Notebook):
                self._run_stage_notebook_v108 = notebook
        return host

    def _refresh_run_plan(self) -> None:
        if not hasattr(self, "run_tree"):
            return
        host = self._live_stage_host_v108()
        if host is None:
            return
        try:
            self.run_tree.delete(*self.run_tree.get_children())
            for child in tuple(host.winfo_children()):
                child.destroy()
        except tk.TclError:
            return

        self._stage_bars.clear()
        self._stage_values.clear()
        self._stage_order.clear()
        self._stage_run_buttons_v38.clear()
        self._pipeline_plan_rows_v38.clear()

        project = getattr(self, "project", None)
        if project is None:
            ttk.Label(
                host,
                text="Load a Fragmenter project to display the 16-stage Run All progress board.",
                wraplength=430,
                justify="left",
            ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=8)
            self._update_stage_scroll_v108()
            return

        try:
            plan = build_run_all_plan_v2(project)
        except Exception as exc:
            self._append_log(f"RUN ALL plan failed: {exc}")
            ttk.Label(host, text=f"Plan unavailable: {exc}", wraplength=430).grid(
                row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=8
            )
            self._update_stage_scroll_v108()
            return

        for row_index, stage in enumerate(plan.get("stages") or []):
            key = str(stage.get("key") or f"stage_{row_index}")
            self._pipeline_plan_rows_v38[key] = dict(stage)
            self.run_tree.insert(
                "",
                "end",
                iid=key,
                text=str(stage.get("label") or key),
                values=(str(stage.get("status") or "pending"), str(stage.get("description") or "")),
            )
            ttk.Label(host, text=str(stage.get("label") or key)).grid(
                row=row_index, column=0, sticky="w", padx=(5, 8), pady=3
            )
            bar = ttk.Progressbar(
                host,
                maximum=100.0,
                mode="determinate",
                value=0.0,
                style="RunAll.Visible.Horizontal.TProgressbar",
                length=180,
            )
            bar.grid(row=row_index, column=1, sticky="ew", pady=3)
            button = ttk.Button(
                host,
                text="Run",
                width=7,
                command=lambda stage_key=key: self._run_stage_v38(stage_key),
            )
            button.grid(row=row_index, column=2, padx=(8, 5), pady=3)
            self._stage_bars[key] = bar
            self._stage_values[key] = 0.0
            self._stage_order.append(key)
            self._stage_run_buttons_v38[key] = button

        try:
            self.overall_progress.configure(style="RunAll.Visible.Horizontal.TProgressbar")
            self.overall_progress["value"] = 0.0
            self.overall_progress_label.set(f"Overall progress: ready // {len(self._stage_order)} stages")
        except (AttributeError, tk.TclError):
            pass
        self._update_stage_scroll_v108(select_stages=True)
        try:
            self._update_research_prep_status_v104()
        except (AttributeError, tk.TclError):
            pass

    def _update_stage_scroll_v108(self, *, select_stages: bool = False) -> None:
        host = self._live_stage_host_v108()
        canvas = self._run_stage_canvas_v108
        if host is None:
            return
        try:
            host.update_idletasks()
            if canvas is not None:
                canvas.configure(scrollregion=canvas.bbox("all"))
            if select_stages and self._run_stage_notebook_v108 is not None:
                stages = canvas.master if canvas is not None else None
                if stages is not None:
                    self._run_stage_notebook_v108.select(stages)
        except tk.TclError:
            pass

    def _project_loaded(self) -> None:
        super()._project_loaded()
        self.after_idle(self._refresh_run_plan)

    # ------------------------------------------------------------------
    # Celdra speech stays opposite her current stage position. Center-stage
    # dialogue uses a lower caption band instead of occupying her headspace.
    # ------------------------------------------------------------------
    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = getattr(self, "_celdra_speech_canvas_v63", None)
        if bubble is None:
            return
        cleaned = " ".join(str(text or "").split())
        self._remember_ambient_source_v88(cleaned)
        stage = str(getattr(self, "_celdra_runtime_stage_v87", "center"))
        yelling = bool(getattr(self, "_celdra_yell_mode_v101", False))
        if yelling:
            relx, rely, relwidth, maximum_height = 0.04, 0.64, 0.92, 190
        elif stage == "left":
            relx, rely, relwidth, maximum_height = 0.57, 0.08, 0.41, 215
        elif stage == "right":
            relx, rely, relwidth, maximum_height = 0.02, 0.08, 0.41, 215
        else:
            relx, rely, relwidth, maximum_height = 0.06, 0.68, 0.88, 145

        bubble.place(relx=relx, rely=rely, anchor="nw", relwidth=relwidth, height=110)
        bubble.update_idletasks()
        width = max(190, bubble.winfo_width())
        font = tkfont.Font(
            family="Consolas" if yelling else "Segoe UI",
            size=12 if yelling else 10,
            weight="bold" if yelling else "normal",
        )
        lines = self._balanced_lines_v101(cleaned, font, max(120, width - 34))
        line_height = max(18, font.metrics("linespace") + 4)
        height = max(96, min(maximum_height, 42 + len(lines) * line_height))
        bubble.place_configure(height=height)
        bubble.update_idletasks()
        width = max(190, bubble.winfo_width())
        bubble.delete("all")
        if yelling:
            points = [3, 14, 18, 3, width - 24, 3, width - 4, 18, width - 10, height - 16, width - 28, height - 5, 26, height - 5, 4, height - 20]
            bubble.create_polygon(*points, fill=self.YELL_BACKGROUND, outline=self.YELL_BORDER, width=4)
            bubble.create_text(
                width / 2,
                height / 2,
                text=cleaned.upper(),
                width=max(120, width - 34),
                fill="#ffffff",
                font=font,
                justify="center",
                anchor="center",
            )
        else:
            self._draw_bubble_style_v81(bubble, (2, 2, width - 4, height - 8), "Angular HUD", cleaned)
        try:
            bubble.tkraise()
        except (AttributeError, tk.TclError):
            pass

    # ------------------------------------------------------------------
    # Accepted sequence: introduce inside stable, break out across Run All,
    # exercise distinct harmless powers, get recalled, then disappear.
    # ------------------------------------------------------------------
    def _start_celdra_session_v49(self, first_scan: bool) -> None:
        self._gremlin_dismissed_v108 = False
        self._destroy_breakout_v108()
        super()._start_celdra_session_v49(first_scan)

    def _start_gremlin_show_v94(self) -> None:
        self._gremlin_dismissed_v108 = False
        super()._start_gremlin_show_v94()
        if not bool(getattr(self, "_celdra_internal_show_v101", False)):
            return
        self._celdra_middle_mode_v101 = "stable"
        self._update_middle_header_v101()
        self._append_console_v49(
            "[CORE] GREMLIN STABLE OPEN // INTRODUCTIONS ONE AT A TIME // BREAKOUT ROUTE LOCKED UNTIL 9/9"
        )

    def _update_middle_header_v101(self) -> None:
        value = getattr(self, "_celdra_middle_header_v101", None)
        if (
            value is not None
            and bool(getattr(self, "_celdra_internal_show_v101", False))
            and str(getattr(self, "_celdra_middle_mode_v101", "")) == "stable"
            and not self._gremlin_dismissed_v108
        ):
            value.set(
                f"GREMLIN STABLE // INTRODUCTIONS {len(self._celdra_roster_visible_v101)}/9 // CONTAINMENT: OPTIMISTIC"
            )
            return
        super()._update_middle_header_v101()

    def _begin_internal_chaos_v101(self) -> None:
        if not self._celdra_internal_show_v101 or not self._celdra_gremlin_active_v94:
            return
        self._celdra_middle_mode_v101 = "chaos"
        self._runtime_pose_v70(
            "shocked",
            "That was the complete stable roster. It was also, apparently, a complete list of everyone participating in the breakout.",
        )
        self._append_console_v49(
            "[CORE] STABLE CONTAINMENT FAILED // NINE GREMLINS RELEASED ACROSS RUN ALL // FILE ACCESS NONE"
        )
        self._hide_middle_scene_v106()
        self._spawn_breakout_v108()
        self._start_gremlin_ui_chaos_v99()
        for index, name in enumerate(KNOWN_GREMLINS):
            self._schedule_gremlin_v94(
                3_000 + index * 3_600,
                lambda selected=name: self._announce_power_v108(selected),
            )
        for index, (pose, line) in enumerate(self.CALM_MANAGEMENT_LINES):
            self._schedule_gremlin_v94(
                8_000 + index * 9_000,
                lambda selected_pose=pose, selected_line=line: self._runtime_pose_v70(selected_pose, selected_line),
            )
        self._schedule_gremlin_v94(22_000, self._start_red_alert_v99)
        self._schedule_gremlin_v94(48_000, self._celdra_gremlin_rage_v96)

    def _run_all_overlay_geometry_v108(self) -> tuple[int, int, int, int]:
        widget = getattr(self, "run_paned", None) or self
        self.update_idletasks()
        root_x = int(widget.winfo_rootx())
        root_y = int(widget.winfo_rooty())
        return root_x, root_y, max(480, int(widget.winfo_width())), max(360, int(widget.winfo_height()))

    def _spawn_breakout_v108(self) -> None:
        self._destroy_breakout_v108()
        try:
            root_x, root_y, width, height = self._run_all_overlay_geometry_v108()
        except tk.TclError:
            return
        holder = tk.Toplevel(self)
        holder.withdraw()
        holder.overrideredirect(True)
        transparent = self.CHAOS_TRANSPARENT_KEY_V108
        holder.configure(background=transparent)
        try:
            holder.transient(self)
            holder.attributes("-topmost", False)
            holder.geometry(f"{width}x{height}+{root_x}+{root_y}")
            holder.update_idletasks()
            holder.wm_attributes("-transparentcolor", transparent)
        except tk.TclError:
            try:
                holder.destroy()
            except tk.TclError:
                pass
            self._append_console_v49(
                "[CORE] FULL-UI GREMLIN OVERLAY UNAVAILABLE // USING INTERNAL CHAOS FALLBACK"
            )
            self._show_middle_scene_v106("chaos")
            self._populate_middle_v101(list(KNOWN_GREMLINS), compact=True)
            return

        canvas = tk.Canvas(
            holder,
            width=width,
            height=height,
            background=transparent,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill="both", expand=True)
        self._gremlin_breakout_window_v108 = holder
        self._gremlin_breakout_canvas_v108 = canvas
        self._gremlin_breakout_items_v108.clear()
        for index, personality in enumerate(GREMLIN_PERSONALITIES):
            name = str(personality.get("name") or KNOWN_GREMLINS[index]).upper()
            art_width, art_height = design_dimensions(dict(personality), compact=True)
            item_width, item_height = art_width + 18, art_height + 10
            column, row = index % 3, index // 3
            x = (column + 0.5) * width / 3 - item_width / 2
            y = (row + 0.5) * height / 3 - item_height / 2
            item = {
                "name": name,
                "index": index,
                "personality": dict(personality),
                "width": item_width,
                "height": item_height,
                "art_width": art_width,
                "art_height": art_height,
                "x": float(x),
                "y": float(y),
                "vx": (1.9 + index * 0.18) * (-1 if index % 2 else 1),
                "vy": (1.35 + index % 4 * 0.24) * (-1 if index % 3 else 1),
                "phase": index * 7,
                "tag": f"v108_breakout_{name}",
                "visible": True,
            }
            self._gremlin_breakout_items_v108[name] = item
            self._draw_breakout_item_v108(item)
        holder.deiconify()
        holder.lift()
        self._start_breakout_motion_v108()

    def _draw_breakout_item_v108(self, item: dict[str, Any]) -> None:
        canvas = self._gremlin_breakout_canvas_v108
        if not isinstance(canvas, tk.Canvas):
            return
        tag = str(item.get("tag") or "")
        proxy = _OffsetCanvasProxyV106(
            canvas,
            tag=tag,
            x=float(item.get("x") or 0.0) + 9,
            y=float(item.get("y") or 0.0) + 5,
            width=int(item.get("art_width") or 82),
            height=int(item.get("art_height") or 88),
        )
        proxy.delete("all")
        draw_gremlin(
            proxy,
            item.get("personality") if isinstance(item.get("personality"), dict) else {},
            width=int(item.get("art_width") or 82),
            height=int(item.get("art_height") or 88),
            phase=int(item.get("phase") or 0),
            mood="chaos",
            compact=True,
            show_name=True,
        )
        item["drawn_x"] = float(item.get("x") or 0.0)
        item["drawn_y"] = float(item.get("y") or 0.0)

    def _start_breakout_motion_v108(self) -> None:
        if self._gremlin_breakout_after_v108 is not None:
            return

        def tick() -> None:
            self._gremlin_breakout_after_v108 = None
            if (
                not self._celdra_internal_show_v101
                or not self._celdra_gremlin_active_v94
                or self._celdra_middle_mode_v101 != "chaos"
            ):
                return
            canvas = self._gremlin_breakout_canvas_v108
            holder = self._gremlin_breakout_window_v108
            if not isinstance(canvas, tk.Canvas) or not isinstance(holder, tk.Toplevel):
                return
            self._gremlin_breakout_phase_v108 += 1
            phase = self._gremlin_breakout_phase_v108
            try:
                root_x, root_y, width, height = self._run_all_overlay_geometry_v108()
                if phase % 5 == 0:
                    holder.geometry(f"{width}x{height}+{root_x}+{root_y}")
            except tk.TclError:
                return
            items = list(self._gremlin_breakout_items_v108.values())
            avg_x = sum(float(row.get("x") or 0.0) for row in items) / max(1, len(items))
            avg_y = sum(float(row.get("y") or 0.0) for row in items) / max(1, len(items))
            for item in items:
                name = str(item.get("name") or "")
                iw, ih = int(item.get("width") or 82), int(item.get("height") or 88)
                left, top = 2.0, 2.0
                right, bottom = max(left, width - iw - 2.0), max(top, height - ih - 2.0)
                x, y = float(item.get("x") or left), float(item.get("y") or top)
                vx, vy = float(item.get("vx") or 1.0), float(item.get("vy") or 1.0)
                t = phase * 0.10 + int(item.get("index") or 0) * 0.71
                visible = True
                if name == "LOOP":
                    x = (left + right) / 2 + math.cos(t) * (right - left) * 0.42
                    y = (top + bottom) / 2 + math.sin(t * 1.17) * (bottom - top) * 0.38
                elif name == "PING":
                    x += vx * 1.7
                    y = bottom - abs(math.sin(t * 2.9)) * min(145.0, bottom - top)
                elif name == "HEX":
                    x += vx * 1.25
                    y = round(y / 24.0) * 24.0
                    if phase % 39 == 0:
                        vx, vy = -vy, vx
                elif name == "CACHE":
                    x += (right * 0.86 - x) * 0.035 + math.sin(t) * 1.4
                    y += (bottom * 0.84 - y) * 0.035 + math.cos(t * 1.2)
                elif name == "PATCH":
                    target_x, target_y = width * 0.24, height * 0.66
                    x += (target_x - x) * 0.045 + math.sin(t * 2.0) * 2.2
                    y += (target_y - y) * 0.045 + math.cos(t * 1.7) * 1.8
                elif name == "ROOT":
                    x += (avg_x - x) * 0.025 + vx * 0.45
                    y += (avg_y - y) * 0.025 + vy * 0.45
                elif name == "NULL":
                    cycle = phase % 92
                    visible = not 1 <= cycle <= 15
                    if cycle == 16:
                        rng = random.Random(phase * 1009 + int(item.get("index") or 0))
                        x, y = rng.uniform(left, right), rng.uniform(top, bottom)
                elif name == "GLITCH":
                    x += vx + (12 if phase % 11 == 0 else -8 if phase % 17 == 0 else 0)
                    y += vy + (-9 if phase % 13 == 0 else 6 if phase % 19 == 0 else 0)
                else:
                    x += vx * 0.78
                    y += vy * 0.68
                if x <= left or x >= right:
                    vx = -vx
                    x = max(left, min(right, x))
                if y <= top or y >= bottom:
                    vy = -vy
                    y = max(top, min(bottom, y))
                item.update(x=x, y=y, vx=vx, vy=vy, phase=int(item.get("phase") or 0) + 1, visible=visible)
                tag = str(item.get("tag") or "")
                try:
                    canvas.itemconfigure(tag, state="normal" if visible else "hidden")
                except tk.TclError:
                    continue
                if not visible:
                    continue
                old_x, old_y = float(item.get("drawn_x") or x), float(item.get("drawn_y") or y)
                if phase % self.CHAOS_REDRAW_EVERY_V108 == 0 or not canvas.find_withtag(tag):
                    self._draw_breakout_item_v108(item)
                else:
                    canvas.move(tag, x - old_x, y - old_y)
                    item["drawn_x"], item["drawn_y"] = x, y
            self._gremlin_breakout_after_v108 = self.after(
                max(90, self._scaled_runtime_ms_v88(self.CHAOS_TICK_MS_V108)), tick
            )

        self._gremlin_breakout_after_v108 = self.after(80, tick)

    def _announce_power_v108(self, name: str) -> None:
        if self._celdra_middle_mode_v101 != "chaos" or not self._celdra_gremlin_active_v94:
            return
        folded = str(name or "").upper()
        line = POWER_LINES_V108.get(folded, f"{folded} has activated an undocumented presentation ability.")
        self._append_console_v49(f"[{folded}] UNIQUE POWER ACTIVE // PRESENTATION-ONLY // PROJECT MUTATIONS 0")
        self._runtime_pose_v70("suspicious" if folded not in {"PING", "LOOP"} else "confused", line)
        canvas = self._gremlin_breakout_canvas_v108
        if isinstance(canvas, tk.Canvas):
            try:
                canvas.delete("v108_power_banner")
                canvas.create_text(
                    max(180, canvas.winfo_width() / 2),
                    18,
                    text=f"{folded} POWER // PRESENTATION ONLY",
                    fill="#d8f5ff",
                    font=("Consolas", 10, "bold"),
                    tags="v108_power_banner",
                )
            except tk.TclError:
                pass

    def _destroy_breakout_v108(self) -> None:
        if self._gremlin_breakout_after_v108 is not None:
            try:
                self.after_cancel(self._gremlin_breakout_after_v108)
            except tk.TclError:
                pass
            self._gremlin_breakout_after_v108 = None
        holder = self._gremlin_breakout_window_v108
        if isinstance(holder, tk.Toplevel):
            try:
                holder.destroy()
            except tk.TclError:
                pass
        self._gremlin_breakout_window_v108 = None
        self._gremlin_breakout_canvas_v108 = None
        self._gremlin_breakout_items_v108.clear()

    def _destroy_internal_chaos_v103(self) -> None:
        self._destroy_breakout_v108()
        super()._destroy_internal_chaos_v103()

    def _celdra_gremlin_rage_v96(self) -> None:
        self._destroy_breakout_v108()
        self._restore_gremlin_ui_v99()
        super()._celdra_gremlin_rage_v96()

    def _finish_internal_gremlin_show_v101(self) -> None:
        self._destroy_breakout_v108()
        self._restore_gremlin_ui_v99()
        self._celdra_internal_show_v101 = False
        self._celdra_gremlin_active_v94 = False
        self._celdra_yell_mode_v101 = False
        self._celdra_roster_visible_v101.clear()
        self._clear_middle_items_v101()
        self._gremlin_dismissed_v108 = True
        self._gremlin_stage_enabled_v106 = False
        self._celdra_stable_reveal_v103 = False
        self._hide_middle_scene_v106()
        self._runtime_pose_v70(
            "neutral",
            "Gremlin breakout concluded. Nine presentation processes dismissed, Run All restored, and the stable is closed until a future directed event.",
        )
        self._append_console_v49(
            "[CORE] GREMLINS DISMISSED // STABLE CLOSED // RUN ALL UI RESTORED // FILE MUTATIONS 0"
        )
        if self._celdra_live_scene_queue_v96 and self._celdra_live_scene_after_v96 is None:
            self._play_next_live_scene_v96()

    def _install_gremlin_stable_v101(self) -> None:
        if self._gremlin_dismissed_v108:
            self._celdra_stable_reveal_v103 = False
            self._hide_middle_scene_v106()
            return
        super()._install_gremlin_stable_v101()

    def _cancel_internal_show_v101(self) -> None:
        self._destroy_breakout_v108()
        super()._cancel_internal_show_v101()

    def _end_celdra_session_v49(self) -> None:
        super()._end_celdra_session_v49()
        if self._gremlin_dismissed_v108:
            self._celdra_stable_reveal_v103 = False
            self._hide_middle_scene_v106()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V108"
            metadata["run_all_progress_renderer"] = "direct_live_v104_stage_host"
            metadata["gremlin_sequence"] = "stable_introductions_then_full_run_all_breakout_then_dismissal"
            metadata["gremlin_breakout_renderer"] = "single_keyed_transparent_overlay"
            metadata["gremlin_unique_powers"] = list(POWER_LINES_V108)
            metadata["speech_bubble_headspace_policy"] = "opposite_stage_or_lower_caption_band"
        return payload

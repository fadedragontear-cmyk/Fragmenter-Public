#!/usr/bin/env python3
"""V110 presentation polish without restructuring Celdra's accepted sequence."""
from __future__ import annotations

import math
import random
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any

from celdra_gremlin_memory_v1 import KNOWN_GREMLINS


class FragmenterCeldraPolishMixinV110:
    """Tighten scene framing, stable geometry, and Gremlin personality motion."""

    STABLE_WIDTH_FRACTION_V110 = 0.21
    STABLE_MIN_WIDTH_V110 = 210
    STABLE_MAX_WIDTH_V110 = 270
    CONSOLE_MIN_WIDTH_V110 = 285

    def __init__(self) -> None:
        self._v110_shy_core_announced = False
        self._v110_detection_flash_after: str | None = None
        self._v110_detection_flash_active = False
        self._v110_null_restore_after: list[str] = []
        self._v110_null_tag_serial = 0
        self._v110_rage_ramp_active = False
        self._v110_departure_after: str | None = None
        super().__init__()

    # ------------------------------------------------------------------
    # Scene ownership: an old sliding chat surface must never remain visible
    # after the avatar, riot, or visitor scene takes ownership of the stage.
    # ------------------------------------------------------------------
    def _hide_legacy_stagepieces_v110(self, *, hide_bubble: bool = False) -> None:
        cancel = getattr(self, "_cancel_chat_animation_v54", None)
        if callable(cancel):
            cancel()
        frame = getattr(self, "_celdra_stage_chat_frame_v54", None)
        if frame is not None:
            try:
                frame.place_forget()
            except tk.TclError:
                pass
        self._celdra_stage_dialogue_visible_v54 = False
        self._celdra_chat_visible_v49 = False
        if hide_bubble:
            hide = getattr(self, "_hide_speech_bubble_v58", None)
            if callable(hide):
                hide()

    def _start_avatar_takeover_v58(self) -> None:
        self._hide_legacy_stagepieces_v110(hide_bubble=True)
        super()._start_avatar_takeover_v58()

    def _runtime_pose_v70(self, pose: str, text: str) -> None:
        self._hide_legacy_stagepieces_v110()
        super()._runtime_pose_v70(pose, text)
        # V87 starts an animated hide even when the legacy chat frame is already
        # obsolete. Cancel that animation and make the scene boundary immediate.
        self._hide_legacy_stagepieces_v110()

    # ------------------------------------------------------------------
    # Shy introduction: reserve a real lane above her head and lower the avatar.
    # ------------------------------------------------------------------
    def _begin_shy_reveal_v64(self) -> None:
        self._hide_legacy_stagepieces_v110(hide_bubble=True)
        self._celdra_runtime_bubble_side_v87 = "above"
        self._celdra_runtime_stage_v87 = "center"
        self._celdra_external_offset_x_v65 = 0
        if not self._load_takeover_reaction_v58("shy"):
            return
        canvas = getattr(self, "celdra_avatar_canvas_v50", None)
        canvas_height = canvas.winfo_height() if canvas is not None else 420
        # The old zero-offset rest position put the upper bubble over Shy's face.
        self._celdra_shy_rest_offset_v64 = max(108, min(146, canvas_height // 3))
        self._celdra_external_offset_y_v58 = max(360, canvas_height + 110)
        self._animate_stage_fraction_v54(0.50, 1_650)
        self._redraw_celdra_avatar_v50()
        if not self._v110_shy_core_announced:
            self._v110_shy_core_announced = True
            self._append_console_v49(
                "[CORE] SHY DRAGONGIRL CHANNEL STABLE // SPEECH LANE RESERVED ABOVE AVATAR"
            )
        self._remember_after_v49(260, self._start_shy_creep_v58)

    def _show_speech_bubble_v58(self, text: str) -> None:
        pose = str(getattr(self, "_celdra_runtime_current_pose_v87", "")).casefold()
        stage = str(getattr(self, "_celdra_runtime_stage_v87", ""))
        if pose != "shy" or stage != "center":
            super()._show_speech_bubble_v58(text)
            return
        bubble = getattr(self, "_celdra_speech_canvas_v63", None)
        if bubble is None:
            return
        cleaned = " ".join(str(text or "").split())
        self._remember_ambient_source_v88(cleaned)
        bubble.place(relx=0.09, rely=0.008, anchor="nw", relwidth=0.82, height=104)
        bubble.update_idletasks()
        width = max(220, bubble.winfo_width())
        font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        lines = self._balanced_lines_v101(cleaned, font, max(150, width - 38))
        height = max(96, min(146, 38 + len(lines) * max(18, font.metrics("linespace") + 3)))
        bubble.place_configure(height=height)
        bubble.update_idletasks()
        width = max(220, bubble.winfo_width())
        bubble.delete("all")
        self._draw_bubble_style_v81(
            bubble,
            (2, 2, width - 4, height - 8),
            "Angular HUD",
            cleaned,
        )
        try:
            bubble.tkraise()
        except (AttributeError, tk.TclError):
            pass

    # ------------------------------------------------------------------
    # Fixed compact stable. It is always about 45% of V103's former width and
    # does not grow when the ninth resident is captured.
    # ------------------------------------------------------------------
    def _apply_middle_layout_v101(self) -> None:
        pane = getattr(self, "celdra_visual_split_v50", None)
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if pane is None or frame is None or bool(getattr(self, "_celdra_middle_hidden_v103", False)):
            return
        try:
            self.update_idletasks()
            width = max(640, int(pane.winfo_width()))
            if len(tuple(pane.panes())) < 3:
                return
            stable_width = max(
                self.STABLE_MIN_WIDTH_V110,
                min(self.STABLE_MAX_WIDTH_V110, round(width * self.STABLE_WIDTH_FRACTION_V110)),
            )
            console_width = max(self.CONSOLE_MIN_WIDTH_V110, min(360, round(width * 0.28)))
            second = max(stable_width + 180, width - console_width)
            first = max(180, second - stable_width)
            pane.sashpos(0, first)
            pane.sashpos(1, second)
            wrap = max(150, stable_width - 18)
            for child in frame.grid_slaves(row=0, column=0):
                if isinstance(child, tk.Label):
                    child.configure(anchor="center", justify="center", wraplength=wrap, font=("Consolas", 7, "bold"))
            status = getattr(self, "_stable_status_label_v109", None)
            if isinstance(status, tk.Label):
                status.configure(wraplength=wrap, justify="left", anchor="w", font=("Consolas", 7))
        except (AttributeError, tk.TclError):
            pass

    def _update_middle_header_v101(self) -> None:
        value = getattr(self, "_celdra_middle_header_v101", None)
        if value is None:
            return
        stable_count = len(self._stable_names_v101())
        visible = len(getattr(self, "_celdra_roster_visible_v101", ()))
        mode = str(getattr(self, "_celdra_middle_mode_v101", "stable"))
        internal = bool(getattr(self, "_celdra_internal_show_v101", False))
        if internal and mode in {"stable", "roster"}:
            text = f"STABLE // INTRO {visible}/9"
        elif mode == "chaos":
            text = "RIOT // 9/9 OUT"
        elif mode == "attention":
            text = "STABLE // ALL STOPPED"
        elif mode == "depart":
            text = "EXIT ROUTES // 9/9"
        elif mode == "reward":
            text = "STABLE // 9/9 COMPLETE"
        else:
            text = f"STABLE // {stable_count}/9 CAPTURED"
        value.set(text)

    def _refresh_stable_status_v109(self) -> None:
        super()._refresh_stable_status_v109()
        names = self._stable_names_v101()
        variable = getattr(self, "_stable_status_var_v109", None)
        if names and variable is not None:
            current = str(variable.get() or "")
            prefix = f"{len(names)}/9 // "
            if current and not current.startswith(prefix):
                variable.set(prefix + current)
        bar = getattr(self, "_stable_status_progress_v109", None)
        if isinstance(bar, ttk.Progressbar):
            try:
                bar.configure(maximum=len(KNOWN_GREMLINS))
                bar["value"] = len(names)
            except tk.TclError:
                pass
        self.after_idle(self._apply_middle_layout_v101)

    # ------------------------------------------------------------------
    # Resident behavior refinements.
    # ------------------------------------------------------------------
    def _stable_position_v103(
        self,
        name: str,
        item: dict[str, Any],
        phase: int,
        width: int,
        height: int,
        iw: int,
        ih: int,
    ) -> tuple[float, float, bool]:
        left, top = 3.0, 3.0
        right = max(left, width - iw - 3.0)
        bottom = max(top, height - ih - 3.0)
        span_x = max(1.0, right - left)
        folded = str(name or "").upper()
        if folded == "PING":
            cursor = (phase * 2.9 + int(item.get("index") or 0) * 17) % (span_x * 2.0)
            x = left + (cursor if cursor <= span_x else span_x * 2.0 - cursor)
            y = bottom - abs(math.sin(phase * 0.30)) * min(48.0, max(1.0, bottom - top))
            return x, y, True
        if folded == "CACHE":
            return left + 2.0, bottom, True
        if folded == "PATCH":
            return min(right, left + max(62.0, span_x * 0.44)), bottom, True
        if folded == "GLITCH":
            anchor = item.get("_v110_glitch_anchor")
            if not isinstance(anchor, tuple) or len(anchor) != 2 or phase % 43 == 0:
                rng = random.Random((phase // 43 + 1) * 7919 + int(item.get("index") or 0) * 131)
                anchor = (rng.uniform(left, right), rng.uniform(top, bottom))
                item["_v110_glitch_anchor"] = anchor
            jump_x = 8 if phase % 9 == 0 else -6 if phase % 13 == 0 else math.sin(phase * 0.45) * 2
            jump_y = -7 if phase % 11 == 0 else 5 if phase % 17 == 0 else math.cos(phase * 0.39) * 2
            return (
                max(left, min(right, float(anchor[0]) + jump_x)),
                max(top, min(bottom, float(anchor[1]) + jump_y)),
                True,
            )
        return super()._stable_position_v103(folded, item, phase, width, height, iw, ih)

    # ------------------------------------------------------------------
    # Individual visits: no global pane movement. Detection is three red flashes
    # on the console only; each Gremlin's V109 four-beat skit remains authoritative.
    # ------------------------------------------------------------------
    def _start_individual_gremlin_visit_v99(self, personality: dict[str, Any]) -> None:
        self._hide_legacy_stagepieces_v110(hide_bubble=True)
        super()._start_individual_gremlin_visit_v99(personality)
        if bool(getattr(self, "_celdra_single_visit_v99", False)):
            self._flash_console_detection_v110()

    def _start_gremlin_ui_chaos_v99(self) -> None:
        if bool(getattr(self, "_celdra_single_visit_v99", False)):
            return
        super()._start_gremlin_ui_chaos_v99()

    def _start_red_alert_v99(self) -> None:
        if bool(getattr(self, "_celdra_single_visit_v99", False)):
            self._flash_console_detection_v110()
            return
        super()._start_red_alert_v99()

    def _start_console_hump_v99(self) -> None:
        if bool(getattr(self, "_celdra_single_visit_v99", False)):
            # PING may bounce against the console visually, but a visit never
            # resizes the console or moves its sash.
            return
        super()._start_console_hump_v99()

    def _flash_console_detection_v110(self) -> None:
        if self._v110_detection_flash_active:
            return
        console = getattr(self, "_celdra_console_v49", None)
        if not isinstance(console, tk.Text):
            return
        try:
            original = (
                str(console.cget("background")),
                str(console.cget("foreground")),
                str(console.cget("insertbackground")),
            )
        except tk.TclError:
            return
        self._v110_detection_flash_active = True
        phase = {"value": 0}

        def tick() -> None:
            self._v110_detection_flash_after = None
            if phase["value"] >= 6:
                try:
                    console.configure(
                        background=original[0],
                        foreground=original[1],
                        insertbackground=original[2],
                    )
                except tk.TclError:
                    pass
                self._v110_detection_flash_active = False
                return
            red = phase["value"] % 2 == 0
            try:
                console.configure(
                    background="#5a0611" if red else original[0],
                    foreground="#fff1f3" if red else original[1],
                    insertbackground="#fff1f3" if red else original[2],
                )
            except tk.TclError:
                self._v110_detection_flash_active = False
                return
            phase["value"] += 1
            self._v110_detection_flash_after = self.after(170, tick)

        tick()

    def _play_capture_beat_v109(self, name: str, beat_index: int) -> None:
        super()._play_capture_beat_v109(name, beat_index)
        if str(name or "").upper() == "NULL" and beat_index in {0, 1, 2}:
            self._blank_one_text_line_v110()

    def _blank_one_text_line_v110(self) -> None:
        self._v110_null_tag_serial += 1
        serial = self._v110_null_tag_serial
        for slot, widget in enumerate(
            (getattr(self, "_celdra_console_v49", None), getattr(self, "run_log", None))
        ):
            if not isinstance(widget, tk.Text):
                continue
            tag = f"v110_null_blank_{serial}_{slot}"
            try:
                last_line = max(1, int(str(widget.index("end-1c")).split(".", 1)[0]))
                line = max(1, last_line - 1 - slot)
                widget.tag_add(tag, f"{line}.0", f"{line}.end")
                widget.tag_configure(tag, elide=True)
            except (ValueError, tk.TclError):
                continue

            def restore(selected=widget, selected_tag=tag) -> None:
                try:
                    selected.tag_remove(selected_tag, "1.0", "end")
                    selected.tag_delete(selected_tag)
                except tk.TclError:
                    pass

            identifier = self.after(self._scaled_runtime_ms_v88(1_450), restore)
            self._v110_null_restore_after.append(identifier)

    # ------------------------------------------------------------------
    # Riot escalation and full offscreen departure.
    # ------------------------------------------------------------------
    def _begin_internal_chaos_v101(self) -> None:
        self._hide_legacy_stagepieces_v110(hide_bubble=True)
        self._v110_rage_ramp_active = False
        super()._begin_internal_chaos_v101()

    def _celdra_gremlin_rage_v96(self) -> None:
        if not bool(getattr(self, "_celdra_internal_show_v101", False)):
            super()._celdra_gremlin_rage_v96()
            return
        if self._v110_rage_ramp_active:
            return
        self._v110_rage_ramp_active = True
        self._rage_step_v110(
            "unenthused",
            "Okay. That was the second warning. I am still being calm, but calm is now doing administrative work.",
            "[CORE] CELDRA PATIENCE LEVEL // LOW // RIOT CONTINUES",
        )
        self._schedule_gremlin_v94(
            3_600,
            lambda: self._rage_step_v110(
                "suspicious",
                "Everyone listen carefully. Put the labels down, stop testing the console, and back away from my horns.",
                "[CORE] CELDRA PATIENCE LEVEL // CRITICAL // COMPLIANCE 0/9",
            ),
        )
        self._schedule_gremlin_v94(
            7_200,
            lambda: self._rage_step_v110(
                "shocked",
                "Last warning. I have asked nicely, explained the boundaries, and watched NULL erase the warning.",
                "[BRAIN] SHE SAID LAST WARNING. COUNT THEM NOW.",
            ),
        )
        self._schedule_gremlin_v94(10_800, self._finish_rage_ramp_v110)

    def _rage_step_v110(self, pose: str, line: str, console_line: str) -> None:
        if not self._v110_rage_ramp_active or not bool(getattr(self, "_celdra_gremlin_active_v94", False)):
            return
        self._runtime_pose_v70(pose, line)
        self._append_console_v49(console_line)

    def _finish_rage_ramp_v110(self) -> None:
        if not self._v110_rage_ramp_active:
            return
        self._v110_rage_ramp_active = False
        super()._celdra_gremlin_rage_v96()

    def _send_internal_gremlins_v101(self) -> None:
        if not bool(getattr(self, "_celdra_internal_show_v101", False)):
            super()._send_internal_gremlins_v101()
            return
        self._hide_legacy_stagepieces_v110(hide_bubble=True)
        self._runtime_pose_v70(
            "smile",
            "Okay, little guys. Out through the program boundaries. Stay together, circle the user's computer once, and do not touch anything with write access.",
        )
        self._append_console_v49(
            "[CORE] NINE OFFSCREEN FLIGHT ROUTES OPEN // MONITOR BOUNDARIES AUTHORIZED // PROJECT ACCESS NONE"
        )
        self._append_console_v49(
            "[BRAIN] THEY ARE NOT LEAVING. THEY ARE GOING AROUND THE BACK OF THE MONITOR."
        )
        self._celdra_middle_mode_v101 = "depart"
        self._start_boundary_departure_v110()

    def _start_boundary_departure_v110(self) -> None:
        self._cancel_boundary_departure_v110()
        self._spawn_breakout_v108()
        if self._gremlin_breakout_after_v108 is not None:
            try:
                self.after_cancel(self._gremlin_breakout_after_v108)
            except tk.TclError:
                pass
            self._gremlin_breakout_after_v108 = None
        canvas = getattr(self, "_gremlin_breakout_canvas_v108", None)
        items = list(getattr(self, "_gremlin_breakout_items_v108", {}).values())
        if not isinstance(canvas, tk.Canvas) or not items:
            self._schedule_gremlin_v94(900, self._finish_internal_gremlin_show_v101)
            return
        width = max(480, canvas.winfo_width())
        height = max(360, canvas.winfo_height())
        starts = [(float(item.get("x") or 0.0), float(item.get("y") or 0.0)) for item in items]
        targets: list[tuple[float, float]] = []
        for index, item in enumerate(items):
            iw = float(item.get("width") or 82)
            ih = float(item.get("height") or 88)
            side = index % 4
            if side == 0:
                targets.append((-iw - 240.0, height * (0.18 + 0.13 * (index % 5))))
            elif side == 1:
                targets.append((width + iw + 240.0, height * (0.14 + 0.12 * (index % 6))))
            elif side == 2:
                targets.append((width * (0.20 + 0.09 * (index % 6)), -ih - 220.0))
            else:
                targets.append((width * (0.76 - 0.08 * (index % 5)), height + ih + 220.0))
        started = time.monotonic()
        duration = max(1, self._scaled_runtime_ms_v88(4_800))

        def tick() -> None:
            self._v110_departure_after = None
            if not bool(getattr(self, "_celdra_internal_show_v101", False)):
                return
            fraction = min(1.0, (time.monotonic() - started) * 1000.0 / duration)
            eased = fraction * fraction * (3.0 - 2.0 * fraction)
            for index, item in enumerate(items):
                sx, sy = starts[index]
                tx, ty = targets[index]
                arc = math.sin(fraction * math.pi) * (34 + index * 3)
                x = sx + (tx - sx) * eased
                y = sy + (ty - sy) * eased - arc
                tag = str(item.get("tag") or "")
                old_x = float(item.get("drawn_x") if item.get("drawn_x") is not None else sx)
                old_y = float(item.get("drawn_y") if item.get("drawn_y") is not None else sy)
                try:
                    canvas.move(tag, x - old_x, y - old_y)
                except tk.TclError:
                    continue
                item["x"], item["y"] = x, y
                item["drawn_x"], item["drawn_y"] = x, y
            if fraction < 1.0:
                self._v110_departure_after = self.after(24, tick)
                return
            self._destroy_breakout_v108()
            self._finish_internal_gremlin_show_v101()

        tick()

    # ------------------------------------------------------------------
    # Cleanup.
    # ------------------------------------------------------------------
    def _cancel_boundary_departure_v110(self) -> None:
        if self._v110_departure_after is not None:
            try:
                self.after_cancel(self._v110_departure_after)
            except tk.TclError:
                pass
            self._v110_departure_after = None

    def _cancel_v110_transients(self) -> None:
        self._v110_rage_ramp_active = False
        self._cancel_boundary_departure_v110()
        if self._v110_detection_flash_after is not None:
            try:
                self.after_cancel(self._v110_detection_flash_after)
            except tk.TclError:
                pass
            self._v110_detection_flash_after = None
        self._v110_detection_flash_active = False
        for identifier in tuple(self._v110_null_restore_after):
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
        self._v110_null_restore_after.clear()
        for widget in (getattr(self, "_celdra_console_v49", None), getattr(self, "run_log", None)):
            if not isinstance(widget, tk.Text):
                continue
            try:
                for tag in tuple(widget.tag_names()):
                    if str(tag).startswith("v110_null_blank_"):
                        widget.tag_remove(tag, "1.0", "end")
                        widget.tag_delete(tag)
            except tk.TclError:
                pass
        self._hide_legacy_stagepieces_v110(hide_bubble=True)

    def _prepare_first_run_surface_v51(self) -> None:
        self._cancel_v110_transients()
        self._v110_shy_core_announced = False
        super()._prepare_first_run_surface_v51()

    def _cancel_internal_show_v101(self) -> None:
        self._cancel_v110_transients()
        super()._cancel_internal_show_v101()

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_v110_transients()
        super()._cancel_celdra_cues_v49()

    def _end_celdra_session_v49(self) -> None:
        self._cancel_v110_transients()
        super()._end_celdra_session_v49()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V110"
            metadata["shy_bubble_lane"] = "above_head_with_lowered_avatar"
            metadata["scene_boundary_cleanup"] = "cancel_and_hide_legacy_chat_surface"
            metadata["stable_width_policy"] = "fixed_compact_21_percent"
            metadata["individual_detection"] = "console_only_three_red_flashes"
            metadata["individual_layout_policy"] = "no_global_sash_or_scroll_chaos"
            metadata["riot_annoyance_ramp"] = 3
            metadata["riot_departure"] = "fully_offscreen_monitor_boundaries"
            metadata["stable_motion"] = {
                "PING": "reversing_wall_bounce_loop",
                "GLITCH": "random_teleport_plus_micro_jumps",
                "CACHE": "grounded_bottom_left",
                "PATCH": "grounded_bottom_left",
            }
        return payload

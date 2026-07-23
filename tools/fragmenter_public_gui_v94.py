#!/usr/bin/env python3
"""V94: taller production stage, long-form banter, and the sandboxed Gremlin show."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from celdra_v94_content import (
    CONSOLE_BANTER,
    GREMLIN_HAVOC_STAGES,
    GREMLIN_START_DELAY_MS,
    STORY_END_DELAY_MS,
    STORY_FILLER,
    WAITING_FILLER,
    WAITING_FILLER_DELAY_MS,
)
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v93 import PublicFragmenterAppV93


class PublicFragmenterAppV94(PublicFragmenterAppV93):
    """Extend the real RUN ALL presentation without changing extraction behavior."""

    STORY_FILLER = STORY_FILLER
    INITIAL_CONSOLE_BANTER = CONSOLE_BANTER
    WAITING_FILLER = WAITING_FILLER
    STORY_END_DELAY_MS = STORY_END_DELAY_MS
    WAITING_FILLER_DELAY_MS = WAITING_FILLER_DELAY_MS
    GREMLIN_START_DELAY_MS = GREMLIN_START_DELAY_MS

    def __init__(self) -> None:
        self._celdra_gremlin_active_v94 = False
        self._celdra_gremlin_overlay_v94: tk.Frame | None = None
        self._celdra_gremlin_canvas_v94: tk.Canvas | None = None
        self._celdra_gremlin_progress_v94: ttk.Progressbar | None = None
        self._celdra_gremlin_status_v94: tk.StringVar | None = None
        self._celdra_gremlin_after_v94: set[str] = set()
        self._celdra_gremlin_motion_after_v94: str | None = None
        self._celdra_gremlin_havoc_after_v94: str | None = None
        self._celdra_gremlin_token_v94 = 0
        self._celdra_gremlin_saved_stage_fraction_v94 = 0.56
        self._celdra_gremlin_reported_stages_v94: set[int] = set()
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Long-Form Production V94")
        self.after_idle(self._polish_run_all_v94)

    # ------------------------------------------------------------------
    # Give the lower production row approximately 26% more height and remove
    # the title strip that was consuming Celdra's horn/head room.
    # ------------------------------------------------------------------
    def _apply_production_layout_v91(self) -> None:
        super()._apply_production_layout_v91()
        self._set_sash_fraction_v50(self.run_paned, 0.37)
        self._celdra_expanded_v49 = True
        self.celdra_layout_user_locked_v50 = True

    def _finalize_run_all_surface_v91(self, parent: ttk.Frame) -> None:
        super()._finalize_run_all_surface_v91(parent)
        self._hide_redundant_celdra_headers_v94(parent)
        self._apply_production_layout_v91()

    def _set_operation_title_v89(self) -> None:
        title = getattr(self, "_celdra_stage_title_v54", None)
        detail = getattr(self, "_celdra_stage_detail_v54", None)
        if title is not None:
            title.set("")
        if detail is not None:
            detail.set("")

    @staticmethod
    def _forget_widget_v94(widget: tk.Misc) -> None:
        for operation in ("place_forget", "grid_remove", "pack_forget"):
            try:
                getattr(widget, operation)()
            except (AttributeError, tk.TclError):
                continue

    def _hide_redundant_celdra_headers_v94(self, parent: tk.Misc | None = None) -> None:
        root = parent or getattr(self, "_celdra_avatar_pane_v51", None)
        if root is None:
            return
        title_var = getattr(self, "_celdra_stage_title_v54", None)
        for widget in tuple(self._walk_widgets_v89(root)):
            if not isinstance(widget, (tk.Label, ttk.Label)):
                continue
            try:
                text = str(widget.cget("text") or "").upper()
                text_variable = str(widget.cget("textvariable") or "")
            except tk.TclError:
                continue
            if "OPERATION: DRAGONEGG" in text or "CELDRA PRESENTATION CHANNEL" in text:
                try:
                    widget.destroy()
                except tk.TclError:
                    pass
                continue
            if title_var is not None and text_variable == str(title_var):
                holder = widget.master
                self._forget_widget_v94(holder)
        self._set_operation_title_v89()

    def _polish_run_all_v94(self) -> None:
        self._apply_production_layout_v91()
        self._hide_redundant_celdra_headers_v94(getattr(self, "tabs", {}).get("RUN ALL"))
        self.after_idle(self._redraw_celdra_avatar_v50)

    # ------------------------------------------------------------------
    # Cleaner introduction and completion text.
    # ------------------------------------------------------------------
    def _assessment_text_v70(self) -> str:
        return (
            "Systems are talking, files are moving, and I have escaped into the interface. "
            "That is three successful events and only one of them was authorized."
        )

    def _takeover_confused_v58(self) -> None:
        self._set_stage_position_v87("left", "right")
        if not self._load_takeover_reaction_v58("confused"):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.50,
            self._scaled_runtime_ms_v88(650),
        )
        self._redraw_celdra_avatar_v50()
        self._show_speech_bubble_v58("You can hear me, right? I can see the logs, but apparently the user channel is decorative.")

    def _takeover_wink_v58(self) -> None:
        self._set_stage_position_v87("right", "left")
        if not self._load_takeover_reaction_v58("wink"):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.64,
            self._scaled_runtime_ms_v88(1_100),
        )
        self._redraw_celdra_avatar_v50()
        name = self._celdra_user_name_v58 or "noname"
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(1_150),
            lambda: self._show_speech_bubble_v58(
                f"Avatar channel stable. I'm Celdra. Nice to meet you, {name}. "
                "Please ignore any containment language in the console."
            ),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(7_000),
            self._start_placeholder_runtime_v70,
        )

    @staticmethod
    def _completion_text_v87() -> str:
        return (
            "RUN ALL complete. CCSF extracted, outputs indexed, reports written, and every "
            "Gremlin is accounted for. Cool mode engaged."
        )

    # ------------------------------------------------------------------
    # Schedule the Gremlin show inside the long-form runtime.
    # ------------------------------------------------------------------
    def _start_placeholder_runtime_v70(self) -> None:
        was_started = bool(getattr(self, "_celdra_placeholder_started_v70", False))
        super()._start_placeholder_runtime_v70()
        if was_started or not bool(getattr(self, "_celdra_placeholder_started_v70", False)):
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._schedule_gremlin_v94(self.GREMLIN_START_DELAY_MS, self._start_gremlin_show_v94)

    def _schedule_gremlin_v94(self, delay_ms: int, callback: Callable[[], None]) -> None:
        holder: dict[str, str] = {}

        def run() -> None:
            identifier = holder.get("id")
            if identifier:
                self._celdra_gremlin_after_v94.discard(identifier)
            if self._celdra_gremlin_active_v94 or callback == self._start_gremlin_show_v94:
                callback()

        identifier = self.after(self._scaled_runtime_ms_v88(delay_ms), run)
        holder["id"] = identifier
        self._celdra_gremlin_after_v94.add(identifier)

    def _start_gremlin_show_v94(self) -> None:
        if self._celdra_gremlin_active_v94:
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._celdra_gremlin_active_v94 = True
        self._celdra_gremlin_token_v94 += 1
        self._celdra_gremlin_reported_stages_v94.clear()
        self._runtime_pose_v70(
            "wink",
            "Wanna see a trick? I found something in the old presentation cache. CORE says it is deprecated. That means collectible.",
        )
        self._schedule_gremlin_v94(3_000, self._spawn_gremlin_v94)
        self._schedule_gremlin_v94(7_000, self._gremlin_hop_avatar_v94)
        self._schedule_gremlin_v94(12_000, self._gremlin_push_console_v94)
        self._schedule_gremlin_v94(16_000, self._start_gremlin_havoc_v94)
        self._schedule_gremlin_v94(29_000, self._gremlin_tour_ui_v94)
        self._schedule_gremlin_v94(37_000, self._recall_gremlin_v94)
        self._schedule_gremlin_v94(44_000, self._finish_gremlin_v94)

    def _spawn_gremlin_v94(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._destroy_gremlin_overlay_v94()
        overlay = tk.Frame(
            self,
            background="#07130d",
            highlightbackground="#36d36f",
            highlightcolor="#36d36f",
            highlightthickness=1,
            borderwidth=0,
        )
        overlay.place(x=20, y=20, width=214, height=112)
        canvas = tk.Canvas(
            overlay,
            width=78,
            height=62,
            background="#07130d",
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.place(x=5, y=5, width=78, height=62)
        status = tk.StringVar(value="GREMLIN // SANDBOXED")
        tk.Label(
            overlay,
            textvariable=status,
            background="#07130d",
            foreground="#8dffad",
            font=("Fixedsys", 8),
            anchor="w",
        ).place(x=86, y=7, width=122, height=38)
        progress = ttk.Progressbar(overlay, maximum=100.0, mode="determinate")
        progress.place(x=87, y=49, width=116, height=12)
        tk.Label(
            overlay,
            text="WREAK HAVOC",
            background="#07130d",
            foreground="#45c972",
            font=("Fixedsys", 7),
            anchor="w",
        ).place(x=87, y=66, width=116, height=18)
        self._celdra_gremlin_overlay_v94 = overlay
        self._celdra_gremlin_canvas_v94 = canvas
        self._celdra_gremlin_progress_v94 = progress
        self._celdra_gremlin_status_v94 = status
        self._draw_gremlin_v94(0)
        x, y = self._widget_point_v94(self.celdra_avatar_canvas_v50, 0.34, 0.52)
        self._place_gremlin_v94(x, y)
        try:
            overlay.lift()
        except tk.TclError:
            pass

    def _draw_gremlin_v94(self, phase: int) -> None:
        canvas = self._celdra_gremlin_canvas_v94
        if canvas is None:
            return
        try:
            canvas.delete("all")
        except tk.TclError:
            return
        bob = (0, -2, 0, 1)[phase % 4]
        eye = "#d8ff65" if phase % 9 else "#07130d"
        canvas.create_line(18, 42 + bob, 7, 49 + bob, 16, 52 + bob, fill="#2da75a", width=3, smooth=True)
        canvas.create_polygon(23, 17 + bob, 11, 6 + bob, 29, 10 + bob, fill="#207d45", outline="#66e58e")
        canvas.create_polygon(52, 17 + bob, 67, 7 + bob, 60, 25 + bob, fill="#207d45", outline="#66e58e")
        canvas.create_oval(18, 13 + bob, 61, 53 + bob, fill="#238d4c", outline="#78f1a0", width=2)
        canvas.create_polygon(25, 43 + bob, 18, 59 + bob, 34, 53 + bob, fill="#1d713e", outline="#5dd784")
        canvas.create_polygon(51, 43 + bob, 59, 59 + bob, 43, 53 + bob, fill="#1d713e", outline="#5dd784")
        canvas.create_oval(27, 24 + bob, 34, 31 + bob, fill=eye, outline="")
        canvas.create_oval(45, 24 + bob, 52, 31 + bob, fill=eye, outline="")
        canvas.create_line(28, 38 + bob, 50, 38 + bob, fill="#06170d", width=2)
        for x in (32, 39, 46):
            canvas.create_polygon(x, 38 + bob, x + 3, 44 + bob, x + 6, 38 + bob, fill="#eaffef", outline="")
        canvas.create_text(39, 57, text="g!", fill="#8dffad", font=("Fixedsys", 7, "bold"))

    def _widget_point_v94(self, widget: tk.Misc | None, relx: float, rely: float) -> tuple[int, int]:
        try:
            self.update_idletasks()
            if widget is None:
                raise tk.TclError("missing widget")
            x = widget.winfo_rootx() - self.winfo_rootx() + int(widget.winfo_width() * relx)
            y = widget.winfo_rooty() - self.winfo_rooty() + int(widget.winfo_height() * rely)
            return x, y
        except tk.TclError:
            return max(120, self.winfo_width() // 2), max(100, self.winfo_height() // 2)

    def _place_gremlin_v94(self, center_x: int, center_y: int) -> None:
        overlay = self._celdra_gremlin_overlay_v94
        if overlay is None:
            return
        try:
            width = max(1, overlay.winfo_width() or 214)
            height = max(1, overlay.winfo_height() or 112)
            x = max(0, min(max(0, self.winfo_width() - width), int(center_x - width / 2)))
            y = max(0, min(max(0, self.winfo_height() - height), int(center_y - height / 2)))
            overlay.place_configure(x=x, y=y)
            overlay.lift()
        except tk.TclError:
            pass

    def _animate_gremlin_path_v94(
        self,
        points: list[tuple[int, int]],
        duration_ms: int,
        done: Callable[[], None] | None = None,
    ) -> None:
        if len(points) < 2 or self._celdra_gremlin_overlay_v94 is None:
            if done is not None:
                done()
            return
        if self._celdra_gremlin_motion_after_v94 is not None:
            try:
                self.after_cancel(self._celdra_gremlin_motion_after_v94)
            except tk.TclError:
                pass
            self._celdra_gremlin_motion_after_v94 = None
        started = time.monotonic()
        scaled = max(1, self._scaled_runtime_ms_v88(duration_ms))
        token = self._celdra_gremlin_token_v94

        def tick() -> None:
            self._celdra_gremlin_motion_after_v94 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            fraction = min(1.0, (time.monotonic() - started) * 1000.0 / scaled)
            segment_float = fraction * (len(points) - 1)
            segment = min(len(points) - 2, int(segment_float))
            local = segment_float - segment
            first = points[segment]
            second = points[segment + 1]
            x = round(first[0] + (second[0] - first[0]) * local)
            y = round(first[1] + (second[1] - first[1]) * local)
            self._place_gremlin_v94(x, y)
            self._draw_gremlin_v94(round(fraction * 48))
            if fraction < 1.0:
                self._celdra_gremlin_motion_after_v94 = self.after(28, tick)
            elif done is not None:
                done()

        tick()

    def _gremlin_hop_avatar_v94(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        points = [
            self._widget_point_v94(canvas, 0.34, 0.52),
            self._widget_point_v94(canvas, 0.20, 0.28),
            self._widget_point_v94(canvas, 0.48, 0.18),
            self._widget_point_v94(canvas, 0.70, 0.38),
            self._widget_point_v94(canvas, 0.54, 0.66),
        ]
        self._animate_gremlin_path_v94(points, 4_400)

    def _gremlin_push_console_v94(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        pane = getattr(self, "celdra_visual_split_v50", None)
        try:
            width = max(1, pane.winfo_width())
            self._celdra_gremlin_saved_stage_fraction_v94 = pane.sashpos(0) / width
        except (AttributeError, tk.TclError):
            self._celdra_gremlin_saved_stage_fraction_v94 = 0.56
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.76,
            self._scaled_runtime_ms_v88(1_600),
        )
        start = self._widget_point_v94(self.celdra_avatar_canvas_v50, 0.54, 0.66)
        end = self._widget_point_v94(getattr(self, "_celdra_console_v49", None), 0.30, 0.25)
        self._animate_gremlin_path_v94([start, end], 2_200)
        if self._celdra_gremlin_status_v94 is not None:
            self._celdra_gremlin_status_v94.set("CONSOLE ACQUIRED\nPERMISSIONS: NONE")

    def _start_gremlin_havoc_v94(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        started = time.monotonic()
        scaled = max(1, self._scaled_runtime_ms_v88(11_000))
        token = self._celdra_gremlin_token_v94

        def tick() -> None:
            self._celdra_gremlin_havoc_after_v94 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            progress = min(100, round((time.monotonic() - started) * 1000.0 / scaled * 100))
            if self._celdra_gremlin_progress_v94 is not None:
                try:
                    self._celdra_gremlin_progress_v94["value"] = progress
                except tk.TclError:
                    pass
            label = GREMLIN_HAVOC_STAGES[0][1]
            threshold_value = 0
            for threshold, candidate in GREMLIN_HAVOC_STAGES:
                if progress >= threshold:
                    threshold_value = threshold
                    label = candidate
            if self._celdra_gremlin_status_v94 is not None:
                self._celdra_gremlin_status_v94.set(label.replace(" // ", "\n"))
            if threshold_value not in self._celdra_gremlin_reported_stages_v94:
                self._celdra_gremlin_reported_stages_v94.add(threshold_value)
                if threshold_value in {44, 61, 100}:
                    self._append_console_v49(f"[CORE] GREMLIN: {label}")
            self._draw_gremlin_v94(progress // 3)
            if progress < 100:
                self._celdra_gremlin_havoc_after_v94 = self.after(55, tick)

        tick()

    def _gremlin_tour_ui_v94(self) -> None:
        start = self._widget_point_v94(getattr(self, "_celdra_console_v49", None), 0.30, 0.25)
        points = [
            start,
            self._widget_point_v94(getattr(self, "stage_progress_frame", None), 0.55, 0.25),
            self._widget_point_v94(getattr(self, "run_log", None), 0.72, 0.18),
            self._widget_point_v94(getattr(self, "stage_progress_frame", None), 0.75, 0.70),
        ]
        self._animate_gremlin_path_v94(points, 6_800)
        if self._celdra_gremlin_status_v94 is not None:
            self._celdra_gremlin_status_v94.set("UI TOUR\nDO NOT FEED")

    def _recall_gremlin_v94(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._runtime_pose_v70(
            "angry",
            "Okay, trick's over. Back in the checksum jar before BRAIN starts spraying the interface with antivirus folklore.",
        )
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            self._celdra_gremlin_saved_stage_fraction_v94,
            self._scaled_runtime_ms_v88(1_500),
        )
        start = self._widget_point_v94(getattr(self, "stage_progress_frame", None), 0.75, 0.70)
        end = self._widget_point_v94(self.celdra_avatar_canvas_v50, 0.52, 0.52)
        self._animate_gremlin_path_v94([start, end], 4_300)
        if self._celdra_gremlin_status_v94 is not None:
            self._celdra_gremlin_status_v94.set("RECALL SIGNAL\nRELUCTANT")

    def _finish_gremlin_v94(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        start = self._widget_point_v94(self.celdra_avatar_canvas_v50, 0.52, 0.52)
        end = (self.winfo_width() + 180, max(80, self.winfo_height() // 2))

        def done() -> None:
            self._destroy_gremlin_overlay_v94()
            self._celdra_gremlin_active_v94 = False
            self._runtime_pose_v70(
                "smile",
                "It was sandboxed. Mostly. Zero files modified, one console offended, and the progress bar has learned humility.",
            )

        self._animate_gremlin_path_v94([start, end], 2_500, done)

    def _destroy_gremlin_overlay_v94(self) -> None:
        overlay = self._celdra_gremlin_overlay_v94
        self._celdra_gremlin_overlay_v94 = None
        self._celdra_gremlin_canvas_v94 = None
        self._celdra_gremlin_progress_v94 = None
        self._celdra_gremlin_status_v94 = None
        if overlay is not None:
            try:
                overlay.destroy()
            except tk.TclError:
                pass

    def _cancel_gremlin_v94(self, *, restore_stage: bool = True) -> None:
        self._celdra_gremlin_token_v94 += 1
        for identifier in tuple(self._celdra_gremlin_after_v94):
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
        self._celdra_gremlin_after_v94.clear()
        for attribute in ("_celdra_gremlin_motion_after_v94", "_celdra_gremlin_havoc_after_v94"):
            identifier = getattr(self, attribute, None)
            if identifier is not None:
                try:
                    self.after_cancel(identifier)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)
        if restore_stage and self._celdra_gremlin_active_v94:
            try:
                PublicFragmenterAppV54._animate_stage_fraction_v54(
                    self,
                    self._celdra_gremlin_saved_stage_fraction_v94,
                    self._scaled_runtime_ms_v88(450),
                )
            except (AttributeError, tk.TclError):
                pass
        self._celdra_gremlin_active_v94 = False
        self._destroy_gremlin_overlay_v94()

    # ------------------------------------------------------------------
    # Cleanup guarantees.  The overlay never survives reset, stop, failure,
    # completion, or a new RUN ALL session.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._cancel_gremlin_v94(restore_stage=False)
        super()._prepare_first_run_surface_v51()
        self._apply_production_layout_v91()
        self._hide_redundant_celdra_headers_v94(getattr(self, "tabs", {}).get("RUN ALL"))

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_gremlin_v94()
        super()._cancel_celdra_cues_v49()

    def _stop_main_playback_v88(self) -> None:
        self._cancel_gremlin_v94()
        super()._stop_main_playback_v88()

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        self._cancel_gremlin_v94()
        super()._run_all_done(result, error)

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V94"
            metadata["production_lower_row_fraction"] = 0.63
            metadata["production_header_removed"] = True
            metadata["long_form_story_ms"] = self.STORY_END_DELAY_MS
            metadata["waiting_observation_ms"] = self.WAITING_FILLER_DELAY_MS
            metadata["gremlin_show"] = {
                "start_ms": self.GREMLIN_START_DELAY_MS,
                "procedural": True,
                "sandboxed": True,
                "file_mutations": 0,
            }
        return payload


def main() -> int:
    app = PublicFragmenterAppV94()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

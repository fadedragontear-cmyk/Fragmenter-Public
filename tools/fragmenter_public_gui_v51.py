#!/usr/bin/env python3
"""V51: slow, CCSF-gated Celdra boot timeline with a blue pixel dragon."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable

from celdra_assets_v1 import asset_inventory
from celdra_pixel_pet_v2 import (
    BLUE_PALETTE,
    FULL_HATCH_SEQUENCE,
    PHASE_FRAMES,
    PixelFrame,
)
from celdra_presentation_v1 import FIRST_SCAN_CUES
from celdra_startup_timeline_v2 import (
    CCSF_HATCH_DELAY_MS,
    DEPLOY_MIN_MS,
    DEPLOY_STATUS,
    FIRST_RUN_AFTER_CCSF,
    TimelineEvent,
)
from fragmenter_public_gui_v48 import PublicFragmenterAppV48
from fragmenter_public_gui_v50 import PublicFragmenterAppV50
from run_all_executor_v8 import execute_run_all_v8, is_first_scan_v8


class PublicFragmenterAppV51(PublicFragmenterAppV50):
    """Coordinate Celdra's presentation with real CCSF extraction events."""

    def __init__(self) -> None:
        self._celdra_avatar_pane_v51: tk.Widget | None = None
        self._celdra_comms_pane_v51: tk.Widget | None = None
        self._celdra_console_pane_v51: tk.Widget | None = None
        self._celdra_dialogue_pane_v51: tk.Widget | None = None
        self._celdra_status_strip_v51: ttk.Frame | None = None
        self._celdra_progress_after_v51: str | None = None
        self._celdra_progress_token_v51 = 0
        self._celdra_first_scan_v51 = False
        self._celdra_ccsf_gate_scheduled_v51 = False
        self._celdra_timeline_started_v51 = False
        self._celdra_timeline_breakpoint_v51 = False
        self._celdra_pipeline_finished_v51 = False
        self._celdra_timeline_speed_v51 = 1.0
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Slow Celdra Startup Timeline")

    # ------------------------------------------------------------------
    # Keep status/progress visible while avatar and dialogue panes come and go.
    # ------------------------------------------------------------------
    def _build_run_all(self, parent: ttk.Frame) -> None:
        super()._build_run_all(parent)
        self._capture_celdra_panes_v51()

        host = self._celdra_host_v49
        if host is not None:
            strip = ttk.Frame(host)
            strip.grid(row=2, column=0, sticky="ew", pady=(5, 0))
            strip.columnconfigure(0, weight=1)
            self._celdra_status_strip_v51 = strip
            self._celdra_fake_status_v49 = tk.StringVar(value="[CELDRA] OFFLINE")
            ttk.Label(
                strip,
                textvariable=self._celdra_fake_status_v49,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")
            self._celdra_fake_progress_v49 = ttk.Progressbar(
                strip,
                maximum=100.0,
                mode="determinate",
                style="Accent.Horizontal.TProgressbar",
            )
            self._celdra_fake_progress_v49.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # V50 put the first status/bubble widgets under the avatar.  The V51
        # status strip replaces them so the avatar can be removed completely.
        avatar = self._celdra_avatar_pane_v51
        if avatar is not None:
            for row in (1, 2, 3):
                for child in avatar.grid_slaves(row=row):
                    child.grid_remove()

        self._hide_avatar_v51()
        self._hide_dialogue_v51()
        self._set_celdra_text_v38(
            "[CORE] CELDRA PRESENTATION LAYER AVAILABLE\n"
            "[CORE] WAITING FOR FULL RUN ALL\n"
        )

    def _capture_celdra_panes_v51(self) -> None:
        visual = self.celdra_visual_split_v50
        comms = self.celdra_comms_split_v50
        if visual is not None:
            panes = visual.panes()
            if len(panes) >= 2:
                self._celdra_avatar_pane_v51 = self.nametowidget(panes[0])
                self._celdra_comms_pane_v51 = self.nametowidget(panes[1])
        if comms is not None:
            panes = comms.panes()
            if len(panes) >= 2:
                self._celdra_console_pane_v51 = self.nametowidget(panes[0])
                self._celdra_dialogue_pane_v51 = self.nametowidget(panes[1])

    @staticmethod
    def _pane_contains_v51(pane: ttk.Panedwindow | None, child: tk.Widget | None) -> bool:
        return bool(pane is not None and child is not None and str(child) in pane.panes())

    def _show_avatar_v51(self) -> None:
        pane = self.celdra_visual_split_v50
        child = self._celdra_avatar_pane_v51
        if pane is None or child is None or self._pane_contains_v51(pane, child):
            return
        try:
            pane.insert(0, child, weight=2)
        except tk.TclError:
            pane.add(child, weight=2)
        self.after_idle(self._redraw_celdra_avatar_v50)
        if not self.celdra_layout_user_locked_v50:
            self._set_celdra_expanded_v49(True)

    def _hide_avatar_v51(self) -> None:
        pane = self.celdra_visual_split_v50
        child = self._celdra_avatar_pane_v51
        if not self._pane_contains_v51(pane, child):
            return
        try:
            pane.forget(child)
        except tk.TclError:
            pass

    def _show_dialogue_v51(self) -> None:
        pane = self.celdra_comms_split_v50
        child = self._celdra_dialogue_pane_v51
        if pane is None or child is None or self._pane_contains_v51(pane, child):
            return
        try:
            pane.add(child, weight=1)
        except tk.TclError:
            return
        self._celdra_chat_visible_v49 = True
        if not self.celdra_layout_user_locked_v50:
            self._set_celdra_expanded_v49(True)

    def _hide_dialogue_v51(self) -> None:
        pane = self.celdra_comms_split_v50
        child = self._celdra_dialogue_pane_v51
        if not self._pane_contains_v51(pane, child):
            return
        try:
            pane.forget(child)
        except tk.TclError:
            pass
        self._celdra_chat_visible_v49 = False

    def _show_celdra_chat_v49(self, *, force: bool = False) -> None:
        self._show_dialogue_v51()
        if self._celdra_chat_v49 is not None:
            self._celdra_chat_v49.focus_set()
            self._celdra_chat_v49.see("end")
        if force:
            self._set_celdra_expanded_v49(True, force=True)

    # ------------------------------------------------------------------
    # Blue built-in pixel creature only for this pass.  Bundled artwork stays
    # visible in the Celdra Test inventory but is not selected by startup.
    # ------------------------------------------------------------------
    def _load_celdra_avatar_frames_v49(self) -> None:
        self.celdra_asset_inventory_v50 = asset_inventory(self.celdra_asset_root_v50)
        self.celdra_external_frames_v50 = {}
        self._play_pixel_sequence_v50(PHASE_FRAMES["egg_wait"], loop=True)

    def _set_avatar_state_v49(self, state: str) -> None:
        state = str(state or "idle").casefold()
        self._celdra_avatar_state_v49 = state
        self._celdra_avatar_index_v49 = 0
        if self._celdra_avatar_after_v49 is not None:
            try:
                self.after_cancel(self._celdra_avatar_after_v49)
            except tk.TclError:
                pass
            self._celdra_avatar_after_v49 = None
        if state in {"boot", "egg", "hatch"}:
            self._play_pixel_sequence_v50(
                FULL_HATCH_SEQUENCE,
                loop=False,
                next_state="idle",
            )
            return
        frames = PHASE_FRAMES.get(state, PHASE_FRAMES["idle"])
        self._play_pixel_sequence_v50(frames, loop=len(frames) > 1)

    def _set_avatar_phase_v51(self, phase: str) -> None:
        phase = str(phase or "egg_wait").casefold()
        frames = PHASE_FRAMES.get(phase, PHASE_FRAMES["egg_wait"])
        if phase == "hatch_open":
            self._play_pixel_sequence_v50(frames, loop=False)
        elif phase == "baby_rise":
            self._play_pixel_sequence_v50(frames, loop=False, next_state="idle")
        else:
            self._play_pixel_sequence_v50(frames, loop=True)

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        canvas.delete("all")
        frame = self.celdra_current_pixel_v50
        if frame is None:
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        rows = frame.rows
        columns = max((len(row) for row in rows), default=1)
        scale = max(2, min(width // max(1, columns), height // max(1, len(rows))))
        art_width = columns * scale
        art_height = len(rows) * scale
        x0 = (width - art_width) // 2
        y0 = (height - art_height) // 2
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = BLUE_PALETTE.get(symbol, "")
                if not color:
                    continue
                canvas.create_rectangle(
                    x0 + column_index * scale,
                    y0 + row_index * scale,
                    x0 + (column_index + 1) * scale,
                    y0 + (row_index + 1) * scale,
                    fill=color,
                    outline=color,
                )

    # ------------------------------------------------------------------
    # Smooth presentation progress.  This never controls real pipeline state.
    # ------------------------------------------------------------------
    def _cancel_progress_animation_v51(self) -> None:
        self._celdra_progress_token_v51 += 1
        if self._celdra_progress_after_v51 is not None:
            try:
                self.after_cancel(self._celdra_progress_after_v51)
            except tk.TclError:
                pass
            self._celdra_progress_after_v51 = None

    def _animate_progress_v51(self, start: float, end: float, duration_ms: int) -> None:
        self._cancel_progress_animation_v51()
        token = self._celdra_progress_token_v51
        duration_ms = max(1, int(duration_ms))
        started = time.monotonic()
        self._set_celdra_fake_progress_v49(start)

        def tick() -> None:
            if token != self._celdra_progress_token_v51:
                return
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / duration_ms)
            self._set_celdra_fake_progress_v49(start + (end - start) * fraction)
            if fraction < 1.0:
                self._celdra_progress_after_v51 = self.after(250, tick)
            else:
                self._celdra_progress_after_v51 = None

        tick()

    def _set_status_segment_v51(
        self,
        text: str,
        start: float,
        end: float,
        duration_ms: int,
    ) -> None:
        if self._celdra_fake_status_v49 is not None:
            self._celdra_fake_status_v49.set(text)
        self._animate_progress_v51(start, end, duration_ms)

    # ------------------------------------------------------------------
    # First-run pipeline integration.
    # ------------------------------------------------------------------
    def _run_all(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        self.cancel_event = threading.Event()
        first_scan = is_first_scan_v8(project)
        self._celdra_first_scan_v51 = bool(first_scan)
        self._celdra_first_scan_v49 = False
        self._celdra_first_scan_v38 = False
        self._celdra_session_active_v49 = True
        self._celdra_pipeline_finished_v51 = False
        self._celdra_ccsf_gate_scheduled_v51 = False
        self._celdra_timeline_started_v51 = False
        self._celdra_timeline_breakpoint_v51 = False
        self._cancel_celdra_cues_v49()
        self._cancel_progress_animation_v51()

        if first_scan:
            self._prepare_first_run_surface_v51()
        else:
            self._prepare_returning_surface_v51()

        self._set_busy(True, "RUN ALL")
        self.run_log.delete("1.0", "end")
        self.overall_progress["value"] = 0.0
        self.overall_progress_label.set("Overall progress: starting")

        def callback(event: dict[str, Any]) -> None:
            self.events.put({"kind": "run_event", "event": event})

        self._background(
            "RUN ALL",
            lambda: execute_run_all_v8(
                project,
                callback=callback,
                cancel_event=self.cancel_event,
            ),
            self._run_all_done,
            already_busy=True,
        )

    def _prepare_first_run_surface_v51(self) -> None:
        self._hide_avatar_v51()
        self._hide_dialogue_v51()
        self._set_celdra_text_v38("")
        self._replace_chat_v49("")
        self._set_status_segment_v51(DEPLOY_STATUS, 0, 12, DEPLOY_MIN_MS)
        self._append_console_v49("[CORE] PRESENTATION CHANNEL INITIALIZED")
        self._append_console_v49("[CORE] WAITING FOR CCSF EXTRACTION GATE")
        self._set_avatar_phase_v51("egg_wait")

    def _prepare_returning_surface_v51(self) -> None:
        self._hide_avatar_v51()
        self._show_dialogue_v51()
        self._set_celdra_text_v38("")
        self._replace_chat_v49("")
        self._set_status_segment_v51(
            "[CELDRA] RECONNECTING TO FRAGMENTER",
            0,
            100,
            20_000,
        )
        self._remember_after_v49(2_000, lambda: self._append_chat_v49("Celdra> Welcome back!"))
        self._remember_after_v49(
            10_000,
            lambda: self._append_chat_v49("Celdra> This shouldn't take long at all."),
        )

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        # V49 contains the old fast Celdra event layer.  Temporarily mark the
        # presentation inactive while base pipeline widgets consume the event.
        active = self._celdra_session_active_v49
        self._celdra_session_active_v49 = False
        try:
            super()._handle_run_event(event)
        finally:
            self._celdra_session_active_v49 = active

        if not active:
            return
        stage = str(event.get("stage") or "")
        kind = str(event.get("kind") or "")
        status = str(event.get("status") or "")

        if (
            self._celdra_first_scan_v51
            and stage == "ccsf_extract"
            and kind == "start"
            and not self._celdra_ccsf_gate_scheduled_v51
        ):
            self._celdra_ccsf_gate_scheduled_v51 = True
            self._remember_after_v49(
                CCSF_HATCH_DELAY_MS,
                lambda: self._begin_first_run_timeline_v51(1.0),
            )
        elif kind == "finish" and status == "failed":
            self._show_timeline_failure_v51()

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        failed = bool(error) or bool(result and result.get("status") == "failed")
        self._celdra_pipeline_finished_v51 = True
        PublicFragmenterAppV48._run_all_done(self, result, error)
        if failed:
            self._show_timeline_failure_v51()
        elif not self._celdra_first_scan_v51:
            self._remember_after_v49(
                1_000,
                lambda: self._append_chat_v49("Celdra> You're all set. Have fun!"),
            )

    def _show_timeline_failure_v51(self) -> None:
        self._cancel_celdra_cues_v49()
        self._cancel_progress_animation_v51()
        self._hide_avatar_v51()
        self._show_dialogue_v51()
        self._append_console_v49("[CORE] PIPELINE INTERRUPTION DETECTED")
        self._append_chat_v49(
            "Celdra> That one is a real error. I preserved the evidence instead of inventing success."
        )
        if self._celdra_fake_status_v49 is not None:
            self._celdra_fake_status_v49.set("[CELDRA] WAITING FOR DEBUGGING")
        self._set_celdra_fake_progress_v49(0)

    # ------------------------------------------------------------------
    # Timeline scheduler and actions.
    # ------------------------------------------------------------------
    def _begin_first_run_timeline_v51(self, speed: float = 1.0) -> None:
        if self._celdra_timeline_started_v51:
            return
        self._celdra_timeline_started_v51 = True
        self._celdra_timeline_speed_v51 = max(0.01, float(speed))
        for event in FIRST_RUN_AFTER_CCSF:
            delay = max(0, round(event.at_ms * self._celdra_timeline_speed_v51))
            self._remember_after_v49(
                delay,
                lambda selected=event: self._emit_timeline_event_v51(selected),
            )

    def _emit_timeline_event_v51(self, event: TimelineEvent) -> None:
        action = event.action
        speed = self._celdra_timeline_speed_v51
        duration = max(1, round(event.duration_ms * speed)) if event.duration_ms else 0
        if action == "show_avatar":
            self._show_avatar_v51()
        elif action == "hide_avatar":
            self._hide_avatar_v51()
        elif action == "show_dialogue":
            self._show_dialogue_v51()
        elif action == "avatar":
            self._set_avatar_phase_v51(event.avatar_phase)
        elif action == "ascii":
            self._append_console_v49(f"[{event.speaker}]\n{event.text}")
        elif action == "console":
            self._append_console_v49(f"[{event.speaker}] {event.text}")
        elif action == "chat":
            self._append_chat_v49(f"Celdra> {event.text}")
        elif action == "status":
            self._set_status_segment_v51(
                event.text,
                float(event.progress_start or 0),
                float(event.progress_end or event.progress_start or 0),
                duration,
            )
        elif action == "progress":
            self._animate_progress_v51(
                float(event.progress_start or 0),
                float(event.progress_end or event.progress_start or 0),
                duration,
            )
        elif action == "breakpoint":
            self._celdra_timeline_breakpoint_v51 = True

    # ------------------------------------------------------------------
    # Temporary test-tab controls: accelerated preview and exact real timing.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        frame = self.tabs.get("Celdra Test")
        if frame is None:
            return
        controls = next(
            (
                child
                for child in frame.winfo_children()
                if isinstance(child, ttk.LabelFrame)
                and str(child.cget("text")) == "Script and avatar tests"
            ),
            None,
        )
        if controls is None:
            return
        ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=7)
        ttk.Button(
            controls,
            text="V51 Timeline Preview (20×)",
            command=lambda: self._start_timeline_test_v51(0.05),
            width=25,
        ).pack(fill="x", pady=2)
        ttk.Button(
            controls,
            text="V51 Timeline Real Timing",
            command=lambda: self._start_timeline_test_v51(1.0),
            width=25,
        ).pack(fill="x", pady=2)

    def _test_celdra_cues_v50(
        self,
        cues: Iterable[Any],
        first_scan: bool,
    ) -> None:
        if first_scan and tuple(cues) == tuple(FIRST_SCAN_CUES):
            self._start_timeline_test_v51(0.05)
            return
        super()._test_celdra_cues_v50(cues, first_scan)

    def _start_timeline_test_v51(self, speed: float) -> None:
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._cancel_progress_animation_v51()
        self._celdra_session_active_v49 = True
        self._celdra_first_scan_v51 = True
        self._celdra_first_scan_v49 = False
        self._celdra_timeline_started_v51 = False
        self._celdra_timeline_breakpoint_v51 = False
        self._prepare_first_run_surface_v51()
        scaled_gate = max(1, round(CCSF_HATCH_DELAY_MS * max(0.01, speed)))
        # Scale the initial deployment hold in the test harness as well.
        self._set_status_segment_v51(
            DEPLOY_STATUS,
            0,
            12,
            max(1, round(DEPLOY_MIN_MS * max(0.01, speed))),
        )
        self._remember_after_v49(
            scaled_gate,
            lambda: self._begin_first_run_timeline_v51(speed),
        )

    def _reset_celdra_test_v50(self) -> None:
        self._cancel_progress_animation_v51()
        super()._reset_celdra_test_v50()
        self._hide_avatar_v51()
        self._hide_dialogue_v51()
        if self._celdra_fake_status_v49 is not None:
            self._celdra_fake_status_v49.set("[CELDRA] STANDING BY")


def main() -> int:
    app = PublicFragmenterAppV51()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

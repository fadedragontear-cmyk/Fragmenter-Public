#!/usr/bin/env python3
"""V91: production-only Operation Dragonegg layout, pacing, and hatch reveal."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_evolution_pixel_v4 import EGG_LOOP
from fragmenter_public_gui_v64 import CALM_EGG_LOOP
from fragmenter_public_gui_v90 import PublicFragmenterAppV90


class PublicFragmenterAppV91(PublicFragmenterAppV90):
    """Ship the calm egg and final Celdra sequence without the authoring lab."""

    # Stretch the post-breakpoint material across several minutes.  CCSF
    # extraction is normally the longest first-run stage, so each observation
    # should remain readable instead of competing with the next one.
    STORY_FILLER = tuple(
        (round(delay * 3.6), pose, text)
        for delay, pose, text in PublicFragmenterAppV90.STORY_FILLER
    )
    INITIAL_CONSOLE_BANTER = tuple(
        (round(delay * 3.6), speaker, text)
        for delay, speaker, text in PublicFragmenterAppV90.INITIAL_CONSOLE_BANTER
    )
    STORY_END_DELAY_MS = 285_000
    WAITING_FILLER_DELAY_MS = 32_000

    REMOVED_RUN_ALL_CONTROLS = {
        "Celdra Test",
        "Reset Pane Layout",
        "Focus Dialogue",
        "Expand Celdra",
        "Compact Celdra",
    }

    def __init__(self) -> None:
        self._celdra_shake_stage_v91 = "off"
        self._celdra_shake_started_v91 = 0.0
        self._celdra_pending_hatch_frames_v91: list[tk.PhotoImage] = []
        self._celdra_hatch_release_after_v91: str | None = None
        self._celdra_hatch_fade_after_v91: str | None = None
        self._celdra_hatch_whiteout_hold_v91 = False
        self._celdra_hatch_whiteout_opacity_v91 = 0.0
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Operation Dragonegg Production V91")
        self.after_idle(self._install_production_idle_v91)

    # ------------------------------------------------------------------
    # Production surface only: do not create the Celdra Test tab.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        return

    def _build_run_all(self, parent: ttk.Frame) -> None:
        super()._build_run_all(parent)
        self.after_idle(lambda: self._finalize_run_all_surface_v91(parent))

    def _finalize_run_all_surface_v91(self, parent: ttk.Frame) -> None:
        # Collect first because destroying widgets while recursively walking the
        # hierarchy can invalidate Tk's child list.
        for widget in tuple(self._walk_widgets_v89(parent)):
            try:
                if isinstance(widget, ttk.Button) and str(widget.cget("text")) in self.REMOVED_RUN_ALL_CONTROLS:
                    widget.destroy()
                    continue
                if isinstance(widget, ttk.Label):
                    text = str(widget.cget("text") or "")
                    if text == "All Celdra surfaces remain visible. Drag any divider to resize.":
                        widget.configure(text="OPERATION: DRAGONEGG // CELDRA PRESENTATION CHANNEL")
            except tk.TclError:
                continue
        self._celdra_chat_button_v49 = None
        self._celdra_expand_button_v49 = None
        self._apply_production_layout_v91()
        self._install_production_idle_v91()

    def _apply_production_layout_v91(self) -> None:
        # Fixed production proportions: Celdra owns most of the lower row while
        # the pipeline plan and real console remain readable above it.
        self._set_sash_fraction_v50(self.run_paned, 0.50)
        self._set_sash_fraction_v50(self.run_top_split_v50, 0.52)
        self._set_sash_fraction_v50(self.run_bottom_split_v50, 0.28)
        self._set_sash_fraction_v50(self.celdra_visual_split_v50, 0.24)
        self._set_sash_fraction_v50(self.celdra_comms_split_v50, 0.38)
        self._celdra_expanded_v49 = True
        self.celdra_layout_user_locked_v50 = True

    # ------------------------------------------------------------------
    # Calm egg before RUN ALL.  The old boot loop contained bright frames.
    # ------------------------------------------------------------------
    def _load_celdra_avatar_frames_v49(self) -> None:
        super()._load_celdra_avatar_frames_v49()
        self._install_production_idle_v91()

    def _install_production_idle_v91(self) -> None:
        if bool(getattr(self, "_celdra_timeline_started_v51", False)) or bool(getattr(self, "task_active", False)):
            return
        if self._celdra_avatar_after_v49 is not None:
            try:
                self.after_cancel(self._celdra_avatar_after_v49)
            except tk.TclError:
                pass
            self._celdra_avatar_after_v49 = None
        self._celdra_glitch_level_v61 = 0
        self._celdra_instability_red_v70 = False
        self._celdra_energy_active_v63 = False
        self._celdra_takeover_active_v58 = False
        self._celdra_stage_phase_v54 = "egg_wait"
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self.celdra_current_external_v50 = None
        self._play_pixel_sequence_v50(CALM_EGG_LOOP or EGG_LOOP, loop=True)
        chat_frame = getattr(self, "_celdra_stage_chat_frame_v54", None)
        if chat_frame is not None:
            try:
                chat_frame.place_forget()
            except tk.TclError:
                pass
        self._set_stage_fraction_v54(0.24)
        self._set_operation_title_v89()
        self.after_idle(self._redraw_celdra_avatar_v50)

    # ------------------------------------------------------------------
    # Remove every early pane shake.  The final two instability stages remain.
    # ------------------------------------------------------------------
    def _start_console_shake_v66(self) -> None:
        # Suppress the old I THINK THEREFORE I CAN impact shake.
        return

    def _start_crack_pulse_v89(
        self,
        values: tuple[float, ...],
        *,
        interval_ms: int = 250,
    ) -> None:
        # Crack animation remains in the egg frames; the screen no longer pulses.
        self._cancel_crack_pulse_v89()

    def _start_instability_shake_v89(self) -> None:
        if self._celdra_instability_shake_active_v89:
            return
        pane = self.celdra_visual_split_v50
        if pane is None:
            return
        self._cancel_crack_pulse_v89()
        self._celdra_instability_shake_active_v89 = True
        self._celdra_instability_shake_phase_v89 = 0
        self._celdra_shake_stage_v91 = "shell_instability"
        self._celdra_shake_started_v91 = time.monotonic()
        try:
            total = max(1, pane.winfo_width())
            self._celdra_instability_base_fraction_v89 = pane.sashpos(0) / total
        except (AttributeError, tk.TclError):
            self._celdra_instability_base_fraction_v89 = 0.24
        self._tick_final_shakes_v91()

    def _begin_containment_failure_shake_v91(self) -> None:
        if not self._celdra_instability_shake_active_v89:
            self._start_instability_shake_v89()
        self._celdra_shake_stage_v91 = "containment_failure"
        self._celdra_instability_shake_phase_v89 = 0
        self._celdra_shake_started_v91 = time.monotonic()

    def _tick_final_shakes_v91(self) -> None:
        self._celdra_instability_shake_after_v89 = None
        if not self._celdra_instability_shake_active_v89:
            return
        pane = self.celdra_visual_split_v50
        if pane is None:
            return
        phase = self._celdra_instability_shake_phase_v89
        if self._celdra_shake_stage_v91 == "containment_failure":
            pattern = (0, 2, -2, 3, -3, 4, -4, 2, -3, 3, -2)
            direction = pattern[phase % len(pattern)]
            self._celdra_viewport_shake_x_v89 = direction * 2
            self._celdra_viewport_shake_y_v89 = pattern[(phase + 4) % len(pattern)]
            sash_jitter = direction * 5
            interval_ms = 38
        else:
            pattern = (0, 1, -1, 1, 0, -1, 1, -1)
            direction = pattern[phase % len(pattern)]
            self._celdra_viewport_shake_x_v89 = direction * 2
            self._celdra_viewport_shake_y_v89 = pattern[(phase + 3) % len(pattern)]
            sash_jitter = direction * 5
            interval_ms = 82
        try:
            width = max(1, pane.winfo_width())
            base = int(width * self._celdra_instability_base_fraction_v89)
            pane.sashpos(0, max(18, min(width - 36, base + sash_jitter)))
        except (AttributeError, tk.TclError):
            pass
        self._celdra_instability_shake_phase_v89 += 1
        self._redraw_celdra_avatar_v50()
        self._celdra_instability_shake_after_v89 = self.after(
            max(12, self._scaled_runtime_ms_v88(interval_ms)),
            self._tick_final_shakes_v91,
        )

    def _stop_instability_shake_v89(self, *, restore_stage: bool = False) -> None:
        super()._stop_instability_shake_v89(restore_stage=restore_stage)
        self._celdra_shake_stage_v91 = "off"

    def _emit_timeline_event_v51(self, event: Any) -> None:
        action = str(getattr(event, "action", "") or "").casefold()
        text = str(getattr(event, "text", "") or "").strip()
        speaker = str(getattr(event, "speaker", "") or "").upper()
        super()._emit_timeline_event_v51(event)
        if (
            action == "console"
            and speaker == "CORE"
            and text.upper() == "HATCH VECTOR ENERGY CONTAINMENT FAILURE."
        ):
            self._begin_containment_failure_shake_v91()
        if action == "console" and speaker == "CELDRA" and text.upper() == "ONLINE":
            # INITIALIZED and ONLINE have now both appeared in black against the
            # white console.  Only now may the dragon fade back into view.
            self._schedule_hatch_release_v91(1_250)

    # ------------------------------------------------------------------
    # Keep the dragon behind white until INITIALIZED and ONLINE are visible.
    # ------------------------------------------------------------------
    def _start_energy_hatch_v63(self) -> None:
        self._clear_hatch_release_v91(clear_frames=True)
        super()._start_energy_hatch_v63()

    def _begin_hatch_gif_v63(self) -> None:
        self._celdra_energy_gif_started_v63 = True
        frames = self._load_hatch_gif_v63()
        if not frames:
            self._append_console_v49("[CORE] TAVERN BYPASS FAILED; WHITEOUT FALLBACK RETAINED")
            self.celdra_current_pixel_v50 = None
            self.celdra_current_external_v50 = None
            return
        self._celdra_pending_hatch_frames_v91 = list(frames)
        self._celdra_hatch_gif_latched_v87 = False
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = None
        self._celdra_hatch_whiteout_hold_v91 = True
        self._celdra_hatch_whiteout_opacity_v91 = 1.0
        self._append_console_v49("[CORE] TAVERN BYPASS SUCCESSFUL... MORE OR LESS")
        self._redraw_celdra_avatar_v50()
        # Safety fallback for a malformed or interrupted timeline.
        self._schedule_hatch_release_v91(14_500)

    def _schedule_hatch_release_v91(self, delay_ms: int) -> None:
        if not self._celdra_pending_hatch_frames_v91:
            return
        if self._celdra_hatch_release_after_v91 is not None:
            try:
                self.after_cancel(self._celdra_hatch_release_after_v91)
            except tk.TclError:
                pass
        self._celdra_hatch_release_after_v91 = self.after(
            self._scaled_runtime_ms_v88(delay_ms),
            self._release_hatch_gif_v91,
        )

    def _release_hatch_gif_v91(self) -> None:
        self._celdra_hatch_release_after_v91 = None
        frames = self._celdra_pending_hatch_frames_v91
        if not frames:
            return
        self._celdra_pending_hatch_frames_v91 = []
        self._play_external_sequence_v50(frames)
        self._celdra_hatch_gif_latched_v87 = True
        self.celdra_current_pixel_v50 = None
        self._celdra_hatch_whiteout_hold_v91 = True
        self._celdra_hatch_whiteout_opacity_v91 = 1.0
        self._start_hatch_fade_v91()

    def _start_hatch_fade_v91(self) -> None:
        if self._celdra_hatch_fade_after_v91 is not None:
            try:
                self.after_cancel(self._celdra_hatch_fade_after_v91)
            except tk.TclError:
                pass
        started = time.monotonic()
        duration_ms = self._scaled_runtime_ms_v88(1_850)

        def tick() -> None:
            self._celdra_hatch_fade_after_v91 = None
            progress = min(1.0, (time.monotonic() - started) * 1000.0 / max(1, duration_ms))
            self._celdra_hatch_whiteout_opacity_v91 = 1.0 - progress
            self._redraw_celdra_avatar_v50()
            if progress < 1.0:
                self._celdra_hatch_fade_after_v91 = self.after(32, tick)
            else:
                self._celdra_hatch_whiteout_hold_v91 = False
                self._celdra_hatch_whiteout_opacity_v91 = 0.0
                self._redraw_celdra_avatar_v50()

        tick()

    def _clear_hatch_release_v91(self, *, clear_frames: bool) -> None:
        for attribute in ("_celdra_hatch_release_after_v91", "_celdra_hatch_fade_after_v91"):
            value = getattr(self, attribute, None)
            if value is not None:
                try:
                    self.after_cancel(value)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)
        if clear_frames:
            self._celdra_pending_hatch_frames_v91 = []
        self._celdra_hatch_whiteout_hold_v91 = False
        self._celdra_hatch_whiteout_opacity_v91 = 0.0

    def _redraw_celdra_avatar_v50(self) -> None:
        super()._redraw_celdra_avatar_v50()
        if not self._celdra_hatch_whiteout_hold_v91:
            return
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        opacity = max(0.0, min(1.0, self._celdra_hatch_whiteout_opacity_v91))
        if opacity <= 0.0:
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        kwargs: dict[str, Any] = {
            "fill": "#ffffff",
            "outline": "",
            "tags": "v91_hatch_whiteout",
        }
        if opacity < 0.88:
            kwargs["stipple"] = (
                "gray75" if opacity >= 0.64
                else "gray50" if opacity >= 0.40
                else "gray25" if opacity >= 0.18
                else "gray12"
            )
        try:
            canvas.create_rectangle(0, 0, width, height, **kwargs)
        except tk.TclError:
            kwargs.pop("stipple", None)
            canvas.create_rectangle(0, 0, width, height, **kwargs)

    # ------------------------------------------------------------------
    # Long-running extraction observations continue at a restrained cadence.
    # ------------------------------------------------------------------
    def _runtime_wait_or_complete_v87(self) -> None:
        if bool(getattr(self, "_celdra_test_mode_v58", False)):
            self._runtime_pose_v70(
                "cool",
                "Test sequence complete. Operation Dragonegg is stable enough for one clean run.",
            )
            return
        if self._celdra_pipeline_failed_v87:
            self._runtime_pose_v70(
                "sad",
                "RUN ALL failed. I am leaving the evidence visible and judging the responsible subsystem quietly.",
            )
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_finished_v51:
            if self._celdra_runtime_current_pose_v87 != "cool":
                self._show_completion_cool_v70()
            return
        pose, text = self.WAITING_FILLER[
            self._celdra_runtime_wait_index_v87 % len(self.WAITING_FILLER)
        ]
        self._celdra_runtime_wait_index_v87 += 1
        self._runtime_pose_v70(pose, text)
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(self.WAITING_FILLER_DELAY_MS),
            self._runtime_wait_or_complete_v87,
        )

    def _prepare_first_run_surface_v51(self) -> None:
        self._clear_hatch_release_v91(clear_frames=True)
        super()._prepare_first_run_surface_v51()
        self._apply_production_layout_v91()

    def _cancel_celdra_cues_v49(self) -> None:
        self._clear_hatch_release_v91(clear_frames=True)
        super()._cancel_celdra_cues_v49()

    def _hide_avatar_v51(self) -> None:
        self._clear_hatch_release_v91(clear_frames=True)
        super()._hide_avatar_v51()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V91"
            metadata["production_only"] = True
            metadata["calm_pre_run_egg"] = True
            metadata["retained_shake_stages"] = [
                "shell_signal_instability",
                "hatch_vector_energy_containment_failure",
            ]
            metadata["post_breakpoint_story_ms"] = self.STORY_END_DELAY_MS
            metadata["waiting_observation_ms"] = self.WAITING_FILLER_DELAY_MS
        return payload


def main() -> int:
    app = PublicFragmenterAppV91()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

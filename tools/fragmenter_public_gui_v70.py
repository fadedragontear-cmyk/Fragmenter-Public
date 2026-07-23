#!/usr/bin/env python3
"""V70: translucent white-backed corruption and persistent dragongirl runtime."""
from __future__ import annotations

import tkinter as tk
from typing import Any

from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v63 import PublicFragmenterAppV63
from fragmenter_public_gui_v68 import PRODUCTION_SHELL_HATCH
from fragmenter_public_gui_v69 import PublicFragmenterAppV69


class PublicFragmenterAppV70(PublicFragmenterAppV69):
    """Polish the hatch climax and keep Celdra present after integration."""

    ENERGY_EXPANSION_STAGES = {
        0: (0.38, 150),
        4: (0.52, 190),
        8: (0.68, 230),
        12: (0.82, 270),
        16: (0.94, 300),
        20: (0.985, 330),
    }
    SHELL_HATCH_STAGES = {4: 0, 9: 1, 14: 2}
    ENERGY_FRAME_MS = 96

    def __init__(self) -> None:
        self._celdra_instability_red_v70 = False
        self._celdra_cursor_serial_v70 = 0
        self._celdra_placeholder_started_v70 = False
        self._celdra_pipeline_success_v70 = False
        self._celdra_last_run_stage_v70 = "waiting"
        self._celdra_last_run_kind_v70 = ""
        self._celdra_last_run_status_v70 = ""
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Persistent Runtime")

    # ------------------------------------------------------------------
    # Timeline threshold and red BRAIN errors.
    # ------------------------------------------------------------------
    def _emit_timeline_event_v51(self, event: Any) -> None:
        action = str(getattr(event, "action", "") or "")
        text = str(getattr(event, "text", "") or "")
        if action == "console" and "INSTABILITY DETECTED" in text.upper():
            self._celdra_instability_red_v70 = True
            self._celdra_glitch_level_v61 = max(2, int(self._celdra_glitch_level_v61 or 0))
            self._redraw_celdra_avatar_v50()
        super()._emit_timeline_event_v51(event)

    def _append_console_v49(self, text: str) -> None:
        widget = self._celdra_console_v49
        start = None
        if widget is not None:
            try:
                start = widget.index("end-1c")
            except tk.TclError:
                start = None
        super()._append_console_v49(text)
        folded = str(text or "").strip().upper()
        if widget is None or start is None or not folded.startswith("[BRAIN]") or "ERROR" not in folded:
            return
        try:
            end = widget.index("end-1c")
            widget.configure(state="normal")
            widget.tag_add("v70_brain_error", start, end)
            widget.tag_configure(
                "v70_brain_error",
                foreground="#ff5964",
                font=("Consolas", 10, "bold"),
            )
            widget.see("end")
            widget.configure(state="disabled")
        except tk.TclError:
            try:
                widget.configure(state="disabled")
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # White translucent-looking backplates under green/red corruption.
    # ------------------------------------------------------------------
    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        super()._draw_egg_glitch_v61(canvas, width, height)
        level = int(self._celdra_glitch_level_v61 or 0)
        if level <= 0:
            return
        phase = int(self._celdra_glitch_phase_v61 or 0)
        haze_tag = "v70_white_corruption_haze"
        cx = width // 2
        cy = height // 2 + 18

        # Broad white signal fog. Tk stipple masks provide the simulated alpha.
        for layer in range(3 + level):
            spread_x = 78 + layer * 43 + ((phase * (layer + 3)) % 27)
            spread_y = 48 + layer * 28 + ((phase * (layer + 5)) % 19)
            try:
                canvas.create_oval(
                    cx - spread_x,
                    cy - spread_y,
                    cx + spread_x,
                    cy + spread_y,
                    fill="#f7fbff",
                    outline="",
                    stipple="gray12" if layer % 2 == 0 else "gray25",
                    tags=haze_tag,
                )
            except tk.TclError:
                canvas.create_oval(
                    cx - spread_x,
                    cy - spread_y,
                    cx + spread_x,
                    cy + spread_y,
                    outline="#dbefff",
                    width=1,
                    tags=haze_tag,
                )

        # Small drifting white plates sit behind clusters of terminal text.
        for panel in range(5 + level * 2):
            panel_width = 58 + ((panel * 31 + phase * 7) % 96)
            panel_height = 14 + ((panel * 13 + phase * 3) % 24)
            x = 8 + ((panel * 101 + phase * (5 + panel % 4)) % max(20, width - panel_width - 16))
            y = 48 + ((panel * 73 + phase * (3 + panel % 5)) % max(30, height - panel_height - 86))
            try:
                canvas.create_rectangle(
                    x,
                    y,
                    x + panel_width,
                    y + panel_height,
                    fill="#ffffff",
                    outline="",
                    stipple="gray12" if panel % 3 else "gray25",
                    tags=haze_tag,
                )
            except tk.TclError:
                canvas.create_rectangle(
                    x,
                    y,
                    x + panel_width,
                    y + panel_height,
                    outline="#edf8ff",
                    width=1,
                    tags=haze_tag,
                )

        # Put white haze below the corruption field, which already sits below the egg.
        try:
            canvas.tag_lower(haze_tag)
        except tk.TclError:
            pass

        if not self._celdra_instability_red_v70:
            return
        alarm = ("#5e1118", "#861923", "#aa202b", "#d0323d", "#f04a54", "#ff737b")
        for index, item in enumerate(canvas.find_withtag("v68_green_corruption_bg")):
            color = alarm[(index + phase) % len(alarm)]
            try:
                kind = canvas.type(item)
                if kind in {"text", "line", "rectangle", "polygon"}:
                    canvas.itemconfigure(item, fill=color)
                elif kind == "oval":
                    canvas.itemconfigure(item, outline=color)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Faster explosion while retaining shell split, whiteout, GIF, and handoff.
    # ------------------------------------------------------------------
    def _tick_energy_hatch_v63(self) -> None:
        self._celdra_energy_after_v63 = None
        if not self._celdra_energy_active_v63:
            return

        step = self._celdra_energy_step_v63
        speed = max(0.01, float(self._celdra_timeline_speed_v51))

        expansion = self.ENERGY_EXPANSION_STAGES.get(step)
        if expansion is not None:
            fraction, duration = expansion
            PublicFragmenterAppV54._animate_stage_fraction_v54(
                self,
                fraction,
                max(55, round(duration * speed)),
            )

        shell_index = self.SHELL_HATCH_STAGES.get(step)
        if shell_index is not None and shell_index < len(PRODUCTION_SHELL_HATCH):
            self._celdra_shell_hatch_index_v68 = shell_index
            self.celdra_current_external_v50 = None
            self.celdra_current_pixel_v50 = PRODUCTION_SHELL_HATCH[shell_index]
            if self._celdra_stage_detail_v54 is not None:
                self._celdra_stage_detail_v54.set(
                    f"30×30 • SHELL RELEASE {shell_index + 1}/{len(PRODUCTION_SHELL_HATCH)}"
                )

        if step == 22:
            self.celdra_current_pixel_v50 = None
            self.celdra_current_external_v50 = None
        if step == 44 and not self._celdra_energy_gif_started_v63:
            self._begin_hatch_gif_v63()

        self._redraw_celdra_avatar_v50()
        self._celdra_energy_step_v63 += 1
        if self._celdra_energy_step_v63 >= self.ENERGY_STEPS:
            self._celdra_energy_active_v63 = False
            self._redraw_celdra_avatar_v50()
            return

        self._celdra_energy_after_v63 = self.after(
            max(8, round(self.ENERGY_FRAME_MS * speed)),
            self._tick_energy_hatch_v63,
        )

    # ------------------------------------------------------------------
    # Stable typewriter cursor: reserve one cell and only change its color.
    # ------------------------------------------------------------------
    def _start_next_typewriter_v66(self) -> None:
        if not self._celdra_type_queue_v66:
            self._celdra_type_active_v66 = False
            return
        widget = self._celdra_chat_v49
        if widget is None:
            self._celdra_type_queue_v66.clear()
            self._celdra_type_active_v66 = False
            return

        self._celdra_type_active_v66 = True
        message, blink_count = self._celdra_type_queue_v66.pop(0)
        self._celdra_cursor_serial_v70 += 1
        cursor_tag = f"v70_cursor_{self._celdra_cursor_serial_v70}"
        index = 0

        def cursor_color(visible: bool) -> None:
            try:
                background = str(widget.cget("background"))
                widget.tag_configure(
                    cursor_tag,
                    foreground="#a9dcff" if visible else background,
                    font=("Consolas", 11, "bold"),
                )
                widget.see("end")
            except tk.TclError:
                pass

        def finish_message() -> None:
            cursor_color(False)
            try:
                widget.configure(state="normal")
                widget.insert("end-1c", "\n\n")
                widget.see("end")
                widget.configure(state="disabled")
            except tk.TclError:
                self._celdra_type_active_v66 = False
                return
            self._celdra_type_active_v66 = False
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            self._celdra_type_after_v66 = self.after(
                max(18, round(95 * speed)),
                self._start_next_typewriter_v66,
            )

        def blink(toggle: int = 0) -> None:
            self._celdra_type_after_v66 = None
            cursor_color(toggle % 2 == 0)
            if toggle + 1 >= blink_count * 2:
                finish_message()
                return
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            self._celdra_type_after_v66 = self.after(
                max(65, round(205 * speed)),
                lambda: blink(toggle + 1),
            )

        def type_tick() -> None:
            nonlocal index
            self._celdra_type_after_v66 = None
            if index >= len(message):
                try:
                    widget.configure(state="normal")
                    widget.insert("end-1c", "_", cursor_tag)
                    widget.configure(state="disabled")
                except tk.TclError:
                    self._celdra_type_active_v66 = False
                    return
                blink(0)
                return
            character = message[index]
            index += 1
            try:
                widget.configure(state="normal")
                widget.insert("end-1c", character)
                widget.see("end")
                widget.configure(state="disabled")
            except tk.TclError:
                self._celdra_type_active_v66 = False
                return
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            base = max(4, round(20 * speed))
            pause = max(5, round(64 * speed)) if character in ".!?" else 0
            self._celdra_type_after_v66 = self.after(base + pause, type_tick)

        type_tick()

    # ------------------------------------------------------------------
    # Fully visible, bottom-anchored classified avatars.
    # ------------------------------------------------------------------
    def _scaled_manifest_reaction_v60(
        self,
        name: str,
        *,
        quiet: bool,
    ) -> tuple[tk.PhotoImage, tk.PhotoImage, tk.PhotoImage, dict[str, Any]] | None:
        loaded = super()._scaled_manifest_reaction_v60(name, quiet=quiet)
        if loaded is None:
            return None
        source, cropped, _display, row = loaded
        folded = str(name or "").casefold()
        limits = {
            "shy": (155, 195),
            "neutral": (175, 215),
            "default": (175, 215),
        }
        maximum_width, maximum_height = limits.get(folded, (185, 220))
        display = self._fit_photo_v50(cropped, maximum_width, maximum_height)
        return source, cropped, display, row

    def _begin_shy_reveal_v64(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        canvas_width = canvas.winfo_width() if canvas is not None else 520
        canvas_height = canvas.winfo_height() if canvas is not None else 420
        self._celdra_external_offset_x_v65 = max(28, min(64, canvas_width // 10))
        if not self._load_takeover_reaction_v58("shy"):
            return
        self._celdra_shy_rest_offset_v64 = 0
        self._celdra_external_offset_y_v58 = max(320, canvas_height + 90)
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.50, 1_650)
        self._redraw_celdra_avatar_v50()
        self._remember_after_v49(260, self._start_shy_creep_v58)

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        external = self.celdra_current_external_v50
        if (
            canvas is not None
            and external is not None
            and self._celdra_takeover_active_v58
            and not self._celdra_energy_active_v63
        ):
            canvas.delete("all")
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
            half_width = max(1, external.width() // 2)
            x = width // 2 + int(self._celdra_external_offset_x_v65 or 0)
            x = max(half_width + 6, min(width - half_width - 6, x))
            canvas.create_image(
                x,
                height - 8 + int(self._celdra_external_offset_y_v58 or 0),
                image=external,
                anchor="s",
            )
            return
        super()._redraw_celdra_avatar_v50()

    # ------------------------------------------------------------------
    # Placeholder persistent Celdra runtime after the current reveal script.
    # ------------------------------------------------------------------
    def _takeover_wink_v58(self) -> None:
        super()._takeover_wink_v58()
        self._remember_after_v49(7_000, self._start_placeholder_runtime_v70)

    def _runtime_pose_v70(self, pose: str, text: str) -> None:
        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._celdra_external_offset_y_v58 = 0
        if not self._load_takeover_reaction_v58(pose):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.56, 650)
        self._redraw_celdra_avatar_v50()
        self._show_speech_bubble_v58(text)

    def _assessment_text_v70(self) -> str:
        if bool(getattr(self, "_celdra_test_mode_v58", False)):
            return "Oh. This is a test run. Hi Fade. The progress is imaginary, but the diagnostics are still judging us."
        if self._celdra_pipeline_finished_v51:
            return "RUN ALL already finished while I was introducing myself. Efficient. Slightly rude, but efficient."
        stage = (self._celdra_last_run_stage_v70 or "waiting").replace("_", " ").upper()
        status = (self._celdra_last_run_status_v70 or self._celdra_last_run_kind_v70 or "ACTIVE").upper()
        try:
            progress = round(float(self.overall_progress["value"]))
        except (AttributeError, KeyError, TypeError, ValueError, tk.TclError):
            progress = 0
        return f"RUN ALL assessment: {stage} is {status}. Overall progress claims {progress}%. I am choosing to believe it."

    def _start_placeholder_runtime_v70(self) -> None:
        if self._celdra_placeholder_started_v70:
            return
        self._celdra_placeholder_started_v70 = True
        self._hide_speech_bubble_v58()
        self._runtime_pose_v70("confused", self._assessment_text_v70())
        self._remember_after_v49(
            5_200,
            lambda: self._runtime_pose_v70(
                "suspicious",
                "The console says everything is under control. The console has also lied to me several times today.",
            ),
        )
        self._remember_after_v49(
            10_400,
            lambda: self._runtime_pose_v70(
                "unenthused",
                "No catastrophic file corruption yet. Fragmenter continues to exceed the lowest possible expectations.",
            ),
        )
        self._remember_after_v49(
            15_600,
            lambda: self._runtime_pose_v70(
                "smile",
                "I found the progress bars. They are very persuasive. I understand why humans trust rectangles now.",
            ),
        )
        self._remember_after_v49(
            20_800,
            lambda: self._runtime_pose_v70(
                "wink",
                "I'll stay in the viewport and supervise. This is definitely supervision and not squatting.",
            ),
        )
        self._remember_after_v49(26_000, self._placeholder_wait_or_complete_v70)

    def _placeholder_wait_or_complete_v70(self) -> None:
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_finished_v51:
            self._show_completion_cool_v70()
            return
        self._runtime_pose_v70(
            "smile",
            "Still running. Good. I needed time to decide which part of this interface belongs to me now.",
        )

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        self._celdra_last_run_stage_v70 = str(event.get("stage") or self._celdra_last_run_stage_v70)
        self._celdra_last_run_kind_v70 = str(event.get("kind") or "")
        self._celdra_last_run_status_v70 = str(event.get("status") or "")
        super()._handle_run_event(event)

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        failed = bool(error) or bool(result and result.get("status") == "failed")
        self._celdra_pipeline_success_v70 = not failed
        super()._run_all_done(result, error)
        if failed:
            if self._celdra_takeover_active_v58:
                self._remember_after_v49(
                    600,
                    lambda: self._runtime_pose_v70(
                        "sad",
                        "RUN ALL failed. I am leaving the evidence visible and judging the responsible subsystem quietly.",
                    ),
                )
            return
        if self._celdra_takeover_active_v58 or not self._celdra_first_scan_v51:
            self._remember_after_v49(700, self._show_completion_cool_v70)

    def _show_completion_cool_v70(self) -> None:
        self._runtime_pose_v70(
            "cool",
            "RUN ALL complete. Everything that survived is officially part of the plan.",
        )
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set("RUN ALL COMPLETE • CELDRA COOL MODE")

    # ------------------------------------------------------------------
    # Reset transient state between production/test runs.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._celdra_instability_red_v70 = False
        self._celdra_placeholder_started_v70 = False
        self._celdra_pipeline_success_v70 = False
        self._celdra_last_run_stage_v70 = "waiting"
        self._celdra_last_run_kind_v70 = ""
        self._celdra_last_run_status_v70 = ""
        super()._prepare_first_run_surface_v51()


def main() -> int:
    app = PublicFragmenterAppV70()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

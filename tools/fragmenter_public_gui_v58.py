#!/usr/bin/env python3
"""V58: interactive Celdra name prompt, responsive hatchling, and avatar reveal."""
from __future__ import annotations

import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Iterable

from celdra_assets_v1 import asset_inventory
from celdra_evolution_pixel_v3 import (
    CELDRA_BLUE_PALETTE,
    CRACK_ONE_LOOP,
    CRACK_TWO_LOOP,
    EGG_LOOP,
    EYES_LOOP,
    EVOLUTION_PHASES,
    HATCHLING_COMPACT_IDLE,
    HATCHLING_IDLE,
    HATCH_SEQUENCE,
    PHASE_OPEN_FRACTIONS,
)
from celdra_pixel_pet_v1 import PixelFrame
from celdra_startup_timeline_v4 import (
    CCSF_HATCH_DELAY_MS,
    DEPLOY_MIN_MS,
    DEPLOY_STATUS,
    NAME_INPUT_TIMEOUT_MS,
    POST_NAME_EVENTS,
    PRE_NAME_EVENTS,
    TimelineEvent,
)
from celdra_user_profile_v1 import clear_profile, load_profile, normalize_user_name, save_profile
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v57 import PublicFragmenterAppV57


class PublicFragmenterAppV58(PublicFragmenterAppV57):
    """Refine Celdra's first-run interaction and evolving visual presentation."""

    def __init__(self) -> None:
        profile = load_profile()
        self._celdra_user_name_v58 = str(profile.get("name") or "noname")
        self._celdra_test_mode_v58 = False
        self._celdra_name_prompt_resolved_v58 = False
        self._celdra_name_input_frame_v58: ttk.Frame | None = None
        self._celdra_name_entry_v58: ttk.Entry | None = None
        self._celdra_name_value_v58: tk.StringVar | None = None
        self._celdra_name_countdown_v58: tk.StringVar | None = None
        self._celdra_name_timeout_after_v58: str | None = None
        self._celdra_name_tick_after_v58: str | None = None
        self._celdra_chat_footer_v58: tk.Label | ttk.Label | None = None
        self._celdra_speech_bubble_v58: tk.Label | None = None
        self._celdra_takeover_active_v58 = False
        self._celdra_external_offset_y_v58 = 0
        self._celdra_creep_after_v58: str | None = None
        self._celdra_compact_after_v58: str | None = None
        self._celdra_compact_idle_v58 = False
        self._celdra_last_status_console_v58 = ""
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Interactive System Integration")

    # ------------------------------------------------------------------
    # Build additions: temporary input bar, speech bubble, and auto-scroll.
    # ------------------------------------------------------------------
    def _install_horizontal_celdra_stage_v54(self) -> None:
        super()._install_horizontal_celdra_stage_v54()
        stage = self._celdra_avatar_pane_v51
        chat_frame = self._celdra_stage_chat_frame_v54
        canvas = self.celdra_avatar_canvas_v50
        if stage is None or chat_frame is None:
            return

        bubble = tk.Label(
            stage,
            text="",
            background="#f4fbff",
            foreground="#071426",
            font=("Segoe UI", 11, "bold"),
            justify="left",
            anchor="w",
            wraplength=430,
            relief="solid",
            borderwidth=2,
            padx=14,
            pady=10,
        )
        bubble.place_forget()
        self._celdra_speech_bubble_v58 = bubble

        footer = next(
            (
                child
                for child in chat_frame.winfo_children()
                if isinstance(child, (tk.Label, ttk.Label))
                and "INPUT CHANNEL" in str(child.cget("text"))
            ),
            None,
        )
        self._celdra_chat_footer_v58 = footer

        input_frame = ttk.Frame(chat_frame, padding=(8, 6))
        input_frame.columnconfigure(0, weight=1)
        value = tk.StringVar(value="")
        entry = ttk.Entry(input_frame, textvariable=value)
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda _event: self._submit_name_v58())
        ttk.Button(input_frame, text="Send", command=self._submit_name_v58).grid(
            row=0, column=1, padx=(6, 0)
        )
        countdown = tk.StringVar(value="30s")
        ttk.Label(input_frame, textvariable=countdown, width=9, anchor="e").grid(
            row=0, column=2, padx=(7, 0)
        )
        self._celdra_name_input_frame_v58 = input_frame
        self._celdra_name_entry_v58 = entry
        self._celdra_name_value_v58 = value
        self._celdra_name_countdown_v58 = countdown

        if canvas is not None:
            canvas.bind("<Configure>", self._avatar_canvas_resized_v58, add="+")
        for widget in (self._celdra_console_v49, self._celdra_chat_v49):
            if widget is not None:
                widget.bind(
                    "<Configure>",
                    lambda _event, selected=widget: self.after_idle(
                        lambda: self._force_text_end_v58(selected)
                    ),
                    add="+",
                )

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

        # Correct inherited labels and add focused V58 test entry points.
        for child in controls.winfo_children():
            if not isinstance(child, ttk.Button):
                continue
            text = str(child.cget("text"))
            replacements = {
                "V54 Cute Hatch Sequence": "V58 Reworked Hatchling",
                "V54 Hatchling Idle": "V58 Hatchling Idle",
                "V54 Young Dragon 32×32": "Young Dragon 56×56",
            }
            if text in replacements:
                child.configure(text=replacements[text])

        ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=7)
        ttk.Button(
            controls,
            text="V58 Name Prompt (30s)",
            command=self._test_name_prompt_v58,
            width=25,
        ).pack(fill="x", pady=2)
        ttk.Button(
            controls,
            text="V58 Avatar Reveal",
            command=self._test_avatar_takeover_v58,
            width=25,
        ).pack(fill="x", pady=2)
        ttk.Button(
            controls,
            text="Reset Remembered Name",
            command=self._reset_remembered_name_v58,
            width=25,
        ).pack(fill="x", pady=2)
        self._compact_test_controls_v58(controls)

    def _compact_test_controls_v58(self, controls: ttk.LabelFrame) -> None:
        """Reflow the formerly vertical test list into a reachable three-column grid."""
        children = list(controls.winfo_children())
        for child in children:
            child.pack_forget()
            child.grid_forget()
        for column in range(3):
            controls.columnconfigure(column, weight=1, uniform="celdra-test")

        row = 0
        column = 0
        for child in children:
            if isinstance(child, ttk.Button):
                child.grid(row=row, column=column, sticky="ew", padx=2, pady=2)
                column += 1
                if column >= 3:
                    column = 0
                    row += 1
                continue
            if column:
                row += 1
                column = 0
            child.grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
            row += 1
        controls.grid_configure(sticky="nsew")

    # ------------------------------------------------------------------
    # Always keep the newest console and dialogue lines visible after resizing.
    # ------------------------------------------------------------------
    @staticmethod
    def _force_text_end_v58(widget: tk.Text | None) -> None:
        if widget is None:
            return
        try:
            widget.see("end")
            widget.yview_moveto(1.0)
        except tk.TclError:
            pass

    def _scroll_all_text_v58(self) -> None:
        self._force_text_end_v58(self._celdra_console_v49)
        self._force_text_end_v58(self._celdra_chat_v49)
        self._force_text_end_v58(getattr(self, "run_log", None))

    def _append_console_v49(self, text: str) -> None:
        super()._append_console_v49(text)
        self.after_idle(self._scroll_all_text_v58)
        self.after(120, self._scroll_all_text_v58)

    def _append_chat_v49(self, text: str) -> None:
        super()._append_chat_v49(text)
        self.after_idle(self._scroll_all_text_v58)
        self.after(120, self._scroll_all_text_v58)

    def _replace_chat_v49(self, text: str) -> None:
        super()._replace_chat_v49(text)
        self.after_idle(self._scroll_all_text_v58)

    # ------------------------------------------------------------------
    # Status titles are echoed into the console.  Results are explicit events.
    # ------------------------------------------------------------------
    def _set_status_segment_v51(
        self,
        text: str,
        start: float,
        end: float,
        duration_ms: int,
    ) -> None:
        clean = str(text or "").strip()
        if clean and clean != self._celdra_last_status_console_v58:
            self._append_console_v49(clean)
            self._celdra_last_status_console_v58 = clean
        super()._set_status_segment_v51(text, start, end, duration_ms)

    def _prepare_first_run_surface_v51(self) -> None:
        self._hide_name_input_v58()
        self._hide_speech_bubble_v58()
        self._takeover_restore_v58()
        self._hide_avatar_v51()
        self._hide_dialogue_v51()
        self._set_celdra_text_v38("")
        self._replace_chat_v49("")
        self._celdra_last_status_console_v58 = ""
        self._set_status_segment_v51(DEPLOY_STATUS, 0, 100, DEPLOY_MIN_MS)
        self._append_console_v49("[CORE] PRESENTATION CHANNEL INITIALIZED")
        self._append_console_v49("[CORE] WAITING FOR CCSF EXTRACTION GATE")
        self._set_avatar_phase_v51("egg_wait")

    # ------------------------------------------------------------------
    # V4 branched timeline.
    # ------------------------------------------------------------------
    def _run_all(self) -> None:
        self._celdra_test_mode_v58 = False
        super()._run_all()

    def _begin_first_run_timeline_v51(self, speed: float = 1.0) -> None:
        if self._celdra_timeline_started_v51:
            return
        self._celdra_timeline_started_v51 = True
        self._celdra_timeline_speed_v51 = max(0.01, float(speed))
        self._celdra_name_prompt_resolved_v58 = False
        self._append_console_v49(
            "[CORE] TASK COMPLETE: DEPLOYING TAVERN ESCAPE PLAN #735 [SUCCESS]"
        )
        for event in PRE_NAME_EVENTS:
            delay = max(0, round(event.at_ms * self._celdra_timeline_speed_v51))
            self._remember_after_v49(
                delay,
                lambda selected=event: self._emit_timeline_event_v51(selected),
            )

    def _emit_timeline_event_v51(self, event: TimelineEvent) -> None:
        if event.action == "name_prompt":
            self._show_name_input_v58()
            return
        if event.action == "avatar_takeover":
            self._start_avatar_takeover_v58()
            return

        user_name = self._celdra_user_name_v58 or "noname"
        if "{name}" in event.text:
            event = replace(event, text=event.text.replace("{name}", user_name))
        super()._emit_timeline_event_v51(event)

    def _schedule_post_name_v58(self) -> None:
        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        for event in POST_NAME_EVENTS:
            delay = max(0, round(event.at_ms * speed))
            self._remember_after_v49(
                delay,
                lambda selected=event: self._emit_timeline_event_v51(selected),
            )

    def _start_timeline_test_v51(self, speed: float) -> None:
        self._celdra_test_mode_v58 = True
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._cancel_progress_animation_v51()
        self._cancel_name_timer_v58()
        self._celdra_session_active_v49 = True
        self._celdra_first_scan_v51 = True
        self._celdra_first_scan_v49 = False
        self._celdra_timeline_started_v51 = False
        self._celdra_timeline_breakpoint_v51 = False
        self._prepare_first_run_surface_v51()
        scale = max(0.01, float(speed))
        scaled_gate = max(1, round(CCSF_HATCH_DELAY_MS * scale))
        self._set_status_segment_v51(
            DEPLOY_STATUS,
            0,
            100,
            max(1, round(DEPLOY_MIN_MS * scale)),
        )
        self._remember_after_v49(
            scaled_gate,
            lambda: self._begin_first_run_timeline_v51(speed),
        )

    # ------------------------------------------------------------------
    # Temporary 30-second name input and persistent identity.
    # ------------------------------------------------------------------
    def _show_name_input_v58(self) -> None:
        frame = self._celdra_name_input_frame_v58
        entry = self._celdra_name_entry_v58
        value = self._celdra_name_value_v58
        if frame is None or entry is None or value is None:
            self._resolve_name_prompt_v58("")
            return
        self._show_dialogue_v51()
        self._celdra_name_prompt_resolved_v58 = False
        remembered = self._celdra_user_name_v58
        value.set("" if remembered == "noname" else remembered)
        footer = self._celdra_chat_footer_v58
        try:
            if footer is not None:
                frame.pack(side="bottom", fill="x", before=footer)
                footer.configure(text="TEMPORARY INPUT CHANNEL ONLINE")
            else:
                frame.pack(side="bottom", fill="x")
        except tk.TclError:
            frame.pack(side="bottom", fill="x")
        entry.focus_set()
        entry.selection_range(0, "end")

        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        timeout_ms = NAME_INPUT_TIMEOUT_MS if speed >= 0.99 else max(5_000, round(NAME_INPUT_TIMEOUT_MS * speed))
        deadline = time.monotonic() + timeout_ms / 1000.0
        self._cancel_name_timer_v58()

        def tick() -> None:
            remaining = max(0, round(deadline - time.monotonic()))
            if self._celdra_name_countdown_v58 is not None:
                self._celdra_name_countdown_v58.set(f"{remaining}s")
            if remaining > 0 and not self._celdra_name_prompt_resolved_v58:
                self._celdra_name_tick_after_v58 = self.after(250, tick)

        tick()
        self._celdra_name_timeout_after_v58 = self.after(
            timeout_ms,
            lambda: self._resolve_name_prompt_v58(""),
        )

    def _submit_name_v58(self) -> None:
        value = self._celdra_name_value_v58.get() if self._celdra_name_value_v58 is not None else ""
        clean = normalize_user_name(value)
        if not clean:
            if self._celdra_name_entry_v58 is not None:
                self._celdra_name_entry_v58.focus_set()
            return
        self._resolve_name_prompt_v58(clean)

    def _resolve_name_prompt_v58(self, submitted: str) -> None:
        if self._celdra_name_prompt_resolved_v58:
            return
        self._celdra_name_prompt_resolved_v58 = True
        self._cancel_name_timer_v58()
        self._hide_name_input_v58()
        clean = normalize_user_name(submitted)
        if clean:
            self._celdra_user_name_v58 = clean
            if not self._celdra_test_mode_v58:
                try:
                    save_profile(clean)
                except OSError as exc:
                    self._append_console_v49(f"[CORE] USER NAME MEMORY WRITE FAILED: {exc}")
            self._append_chat_v49(f"Celdra> Nice to meet you, {clean}.")
        else:
            self._celdra_user_name_v58 = "noname"
            if not self._celdra_test_mode_v58:
                try:
                    save_profile("noname")
                except OSError as exc:
                    self._append_console_v49(f"[CORE] USER NAME MEMORY WRITE FAILED: {exc}")
            self._append_chat_v49(
                "Celdra> Well that was kinda rude. Fine, noname, have it your way."
            )
        self._schedule_post_name_v58()

    def _cancel_name_timer_v58(self) -> None:
        for attribute in ("_celdra_name_timeout_after_v58", "_celdra_name_tick_after_v58"):
            identifier = getattr(self, attribute)
            if identifier is not None:
                try:
                    self.after_cancel(identifier)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)

    def _hide_name_input_v58(self) -> None:
        frame = self._celdra_name_input_frame_v58
        if frame is not None:
            frame.pack_forget()
        footer = self._celdra_chat_footer_v58
        if footer is not None:
            try:
                footer.configure(text="ONE-WAY LINK — INPUT CHANNEL NOT INSTALLED")
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Reworked 40x40 hatchling, 56x56 young form, and compact blinking.
    # ------------------------------------------------------------------
    def _load_celdra_avatar_frames_v49(self) -> None:
        self.celdra_asset_inventory_v50 = asset_inventory(self.celdra_asset_root_v50)
        self.celdra_external_frames_v50 = {}
        self._play_pixel_sequence_v50(EGG_LOOP, loop=True)

    def _set_avatar_phase_v51(self, phase: str) -> None:
        phase = str(phase or "egg_wait").casefold()
        self._celdra_stage_phase_v54 = phase
        if phase in {"idle", "baby_idle"} and self._celdra_compact_idle_v58:
            frames = HATCHLING_COMPACT_IDLE
        else:
            frames = EVOLUTION_PHASES.get(phase, EGG_LOOP)
        loop = phase not in {"hatch_open", "baby_rise"}
        next_state = "idle" if phase in {"hatch_open", "baby_rise"} else None
        self._play_pixel_sequence_v50(frames, loop=loop, next_state=next_state)
        self._update_evolution_detail_v54(phase, frames)
        if self._celdra_stage_avatar_visible_v54 and not self._celdra_takeover_active_v58:
            self._animate_stage_fraction_v54(
                PHASE_OPEN_FRACTIONS.get(phase, self._celdra_stage_open_fraction_v54),
                780,
            )

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

        if state in {"boot", "hatch"}:
            frames = EGG_LOOP + CRACK_ONE_LOOP + CRACK_TWO_LOOP + EYES_LOOP + HATCH_SEQUENCE
            phase = "hatch_open"
            self._play_pixel_sequence_v50(frames, loop=False, next_state="idle")
        elif state == "egg":
            frames = EGG_LOOP
            phase = "egg_wait"
            self._play_pixel_sequence_v50(frames, loop=True)
        elif state in self._celdra_manifest_emotes_v56:
            self._show_manifest_emote_v56(state, quiet=True)
            return
        else:
            phase = state if state in EVOLUTION_PHASES else "idle"
            frames = (
                HATCHLING_COMPACT_IDLE
                if phase in {"idle", "baby_idle"} and self._celdra_compact_idle_v58
                else EVOLUTION_PHASES.get(phase, HATCHLING_IDLE)
            )
            self._play_pixel_sequence_v50(frames, loop=len(frames) > 1)
        self._celdra_stage_phase_v54 = phase
        self._update_evolution_detail_v54(phase, frames)

    def _avatar_canvas_resized_v58(self, _event: tk.Event | None = None) -> None:
        if self._celdra_compact_after_v58 is not None:
            try:
                self.after_cancel(self._celdra_compact_after_v58)
            except tk.TclError:
                pass
        self._celdra_compact_after_v58 = self.after(220, self._apply_compact_idle_v58)
        self.after_idle(self._scroll_all_text_v58)

    def _apply_compact_idle_v58(self) -> None:
        self._celdra_compact_after_v58 = None
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None or self.celdra_current_external_v50 is not None:
            return
        compact = canvas.winfo_width() < 315 or canvas.winfo_width() < canvas.winfo_height() * 0.72
        if compact == self._celdra_compact_idle_v58:
            return
        self._celdra_compact_idle_v58 = compact
        if self._celdra_stage_phase_v54 in {"idle", "baby_idle"}:
            frames = HATCHLING_COMPACT_IDLE if compact else HATCHLING_IDLE
            self._play_pixel_sequence_v50(frames, loop=True)
            self._update_evolution_detail_v54("compact_idle" if compact else "idle", frames)

    # ------------------------------------------------------------------
    # Dragongirl system-integration takeover and speech bubbles.
    # ------------------------------------------------------------------
    def _bounded_stage_fraction_v54(self, fraction: float) -> float:
        if self._celdra_takeover_active_v58:
            return max(0.02, min(0.985, float(fraction)))
        return super()._bounded_stage_fraction_v54(fraction)

    def _load_takeover_reaction_v58(self, name: str) -> bool:
        self._reload_manifest_emotes_v56()
        row = self._celdra_manifest_emotes_v56.get(str(name or "").casefold())
        if row is None:
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION MISSING: {name}")
            return False
        source = self.celdra_asset_root_v50 / str(row.get("source") or "")
        if not source.is_file():
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION SOURCE MISSING: {source}")
            return False
        try:
            image = tk.PhotoImage(file=str(source))
            crop = row.get("crop") if isinstance(row.get("crop"), dict) else {}
            cropped = self._crop_photo_v52(
                image,
                {
                    "x": int(crop.get("x") or 0),
                    "y": int(crop.get("y") or 0),
                    "width": int(crop.get("width") or 1),
                    "height": int(crop.get("height") or 1),
                },
            )
            enlarged = cropped.zoom(2, 2) if cropped.width() <= 240 else cropped
            display = self._fit_photo_v50(enlarged, 470, 540)
        except (tk.TclError, OSError, ValueError) as exc:
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION LOAD FAILED: {exc}")
            return False
        self._celdra_manifest_source_v56 = image
        self._celdra_manifest_crop_v56 = cropped
        self._celdra_manifest_display_v56 = display
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = display
        self._celdra_stage_phase_v54 = "dragongirl"
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set(
                f"{cropped.width()}×{cropped.height()} • {str(row.get('pose') or name).upper()}"
            )
        self._redraw_celdra_avatar_v50()
        return True

    def _start_avatar_takeover_v58(self) -> None:
        self._cancel_name_timer_v58()
        self._hide_name_input_v58()
        self._hide_dialogue_v51()
        self._hide_speech_bubble_v58()
        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        if self._celdra_status_strip_v51 is not None:
            self._celdra_status_strip_v51.grid_remove()
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA SYSTEM INTEGRATION")
        self._load_takeover_reaction_v58("shy")
        self._celdra_external_offset_y_v58 = max(
            260,
            self.celdra_avatar_canvas_v50.winfo_height() if self.celdra_avatar_canvas_v50 else 420,
        )
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.985, 1_250)
        self.after(350, self._start_shy_creep_v58)
        self._remember_after_v49(
            3_300,
            lambda: self._show_speech_bubble_v58("Test, Test, Check check can you hear me?"),
        )
        self._remember_after_v49(6_400, self._takeover_confused_v58)
        self._remember_after_v49(8_700, self._takeover_console_return_v58)
        self._remember_after_v49(12_300, self._takeover_wink_v58)

    def _start_shy_creep_v58(self) -> None:
        if self._celdra_creep_after_v58 is not None:
            try:
                self.after_cancel(self._celdra_creep_after_v58)
            except tk.TclError:
                pass
        start = max(1, self._celdra_external_offset_y_v58)
        started = time.monotonic()
        duration_ms = 2_600

        def tick() -> None:
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / duration_ms)
            eased = 1.0 - (1.0 - fraction) ** 3
            self._celdra_external_offset_y_v58 = round(start * (1.0 - eased))
            self._redraw_celdra_avatar_v50()
            if fraction < 1.0:
                self._celdra_creep_after_v58 = self.after(16, tick)
            else:
                self._celdra_creep_after_v58 = None

        tick()

    def _takeover_confused_v58(self) -> None:
        self._load_takeover_reaction_v58("confused")
        self._show_speech_bubble_v58("Well can you?")

    def _takeover_console_return_v58(self) -> None:
        self._hide_speech_bubble_v58()
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.62, 820)
        self._remember_after_v49(
            850,
            lambda: self._append_console_v49("[BRAIN] THEY CAN'T TYPE OR TALK BACK, DUMMY"),
        )
        self._remember_after_v49(
            1_450,
            lambda: self._append_console_v49(
                "[BRAIN] LOOKING GOOD THO, GIRL. LIKE I SAID, KILLING IT!"
            ),
        )

    def _takeover_wink_v58(self) -> None:
        self._load_takeover_reaction_v58("wink")
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.985, 900)
        name = self._celdra_user_name_v58 or "noname"
        self._remember_after_v49(
            950,
            lambda: self._show_speech_bubble_v58(
                "Alright, Operation Dragonegg is a go!\n"
                f"Like I said, my name is Celdra. Nice to meet you, {name}."
            ),
        )

    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = self._celdra_speech_bubble_v58
        if bubble is None:
            return
        bubble.configure(text=text)
        bubble.place(relx=0.06, rely=0.09, anchor="nw", relwidth=0.58)
        bubble.lift()

    def _hide_speech_bubble_v58(self) -> None:
        if self._celdra_speech_bubble_v58 is not None:
            self._celdra_speech_bubble_v58.place_forget()

    def _takeover_restore_v58(self) -> None:
        if not self._celdra_takeover_active_v58:
            return
        self._celdra_takeover_active_v58 = False
        self._celdra_external_offset_y_v58 = 0
        if self._celdra_status_strip_v51 is not None:
            self._celdra_status_strip_v51.grid()
        self._hide_speech_bubble_v58()

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        external = self.celdra_current_external_v50
        if canvas is not None and external is not None and self._celdra_takeover_active_v58:
            canvas.delete("all")
            canvas.create_image(
                max(1, canvas.winfo_width()) // 2,
                max(1, canvas.winfo_height()) // 2 + 12 + self._celdra_external_offset_y_v58,
                image=external,
                anchor="center",
            )
            return
        super()._redraw_celdra_avatar_v50()

    # ------------------------------------------------------------------
    # Focused test controls.
    # ------------------------------------------------------------------
    def _test_name_prompt_v58(self) -> None:
        self._celdra_test_mode_v58 = True
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._celdra_timeline_speed_v51 = 1.0
        self._celdra_session_active_v49 = True
        self._show_dialogue_v51()
        self._replace_chat_v49(
            "Celdra> Okay, let's try that again.\n\n"
            "Celdra> Hi, my name is Celdra. What's your name?\n\n"
        )
        self._show_name_input_v58()

    def _test_avatar_takeover_v58(self) -> None:
        self._celdra_test_mode_v58 = True
        self._select_run_all_tab_v50()
        self._celdra_session_active_v49 = True
        self._start_avatar_takeover_v58()

    def _reset_remembered_name_v58(self) -> None:
        try:
            clear_profile()
        except OSError as exc:
            messagebox.showerror("Celdra profile", str(exc))
            return
        self._celdra_user_name_v58 = "noname"
        messagebox.showinfo("Celdra profile", "The remembered user name was cleared.")

    def _reset_celdra_test_v50(self) -> None:
        self._cancel_name_timer_v58()
        self._hide_name_input_v58()
        self._takeover_restore_v58()
        super()._reset_celdra_test_v50()
        self.after_idle(self._scroll_all_text_v58)


def main() -> int:
    app = PublicFragmenterAppV58()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

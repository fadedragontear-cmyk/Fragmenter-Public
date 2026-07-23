#!/usr/bin/env python3
"""V88: realtime production playback and restrained ambient Celdra corruption."""
from __future__ import annotations

import math
import re
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_authoring_post_breakpoint_v1 import (
    BUBBLE_GEOMETRY,
    DRAGONGIRL_BUBBLE_STYLE,
    DRAGONGIRL_SCALE,
    DRAGONGIRL_Y,
    SHY_SCALE,
    SHY_Y,
    STAGE_X,
    extend_with_post_breakpoint,
)
from celdra_authoring_project_v1 import normalize_events
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v87 import PublicFragmenterAppV87


class PublicFragmenterAppV88(PublicFragmenterAppV87):
    """Expose real production playback and finish the dragongirl presentation polish."""

    AMBIENT_TAG = "v88_ambient_green_text"
    AMBIENT_COLORS = ("#062d1d", "#083924", "#0b472c", "#0f5735", "#176a42", "#218051")
    DRAGONGIRL_ASSETS = {
        "shy",
        "confused",
        "suspicious",
        "unenthused",
        "smile",
        "yawn",
        "excited",
        "shocked",
        "laugh",
        "wink",
        "sad",
        "cool",
        "love",
        "angry",
        "neutral",
        "default",
    }
    INITIAL_CONSOLE_BANTER = (
        (7_800, "BRAIN", "SHE'S BEEN HERE THIRTY SECONDS AND ALREADY CLAIMED A PANE."),
        (13_000, "CORE", "CELDRA DISPLAY RESERVATION ACKNOWLEDGED."),
        (23_400, "BRAIN", "THAT IS NOT WHAT ACKNOWLEDGED MEANS."),
        (33_800, "CORE", "CCSF EXTRACTION REMAINS ACTIVE. PLEASE STOP NARRATING THE PROGRESS BAR."),
        (40_000, "BRAIN", "NO."),
    )

    def __init__(self) -> None:
        self._celdra_main_playback_status_v88: tk.StringVar | None = None
        self._celdra_main_playback_multiplier_v88 = 1.0
        self._celdra_ambient_after_v88: str | None = None
        self._celdra_ambient_phase_v88 = 0
        self._celdra_ambient_sources_v88: list[str] = [
            "CELDRA ONLINE",
            "CCSF EXTRACTION ACTIVE",
            "FRAGMENTER SUPERVISION CHANNEL",
            "RUN ALL STATUS NOMINAL",
        ]
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Realtime Production Preview V88")
        self._apply_dragongirl_authoring_profile_v87()
        self.after_idle(self._refresh_author_event_tree_v74)

    # ------------------------------------------------------------------
    # Visible production-surface playback controls.
    # ------------------------------------------------------------------
    def _build_author_preview_tab_v74(self, parent: ttk.Frame) -> None:
        super()._build_author_preview_tab_v74(parent)
        self._install_main_playback_bar_v88(parent)

    def _build_author_timeline_tab_v74(self, parent: ttk.Frame) -> None:
        super()._build_author_timeline_tab_v74(parent)
        self._install_main_playback_bar_v88(parent)

    def _install_main_playback_bar_v88(self, parent: ttk.Frame) -> None:
        for child in parent.winfo_children():
            if not isinstance(child, ttk.LabelFrame):
                continue
            try:
                if str(child.cget("text")) == "Production RUN ALL playback":
                    return
            except tk.TclError:
                continue
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        bar = ttk.LabelFrame(
            parent,
            text="Production RUN ALL playback",
            padding=(6, 4),
        )
        bar.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        for column in range(5):
            bar.columnconfigure(column, weight=0 if column < 4 else 1)
        for column, (label, multiplier) in enumerate(
            (("Realtime 1x", 1.0), ("5x", 5.0), ("20x", 20.0))
        ):
            ttk.Button(
                bar,
                text=label,
                command=lambda value=multiplier: self._start_main_playback_v88(value),
            ).grid(row=0, column=column, sticky="w", padx=(0, 4))
        ttk.Button(
            bar,
            text="Stop main playback",
            command=self._stop_main_playback_v88,
        ).grid(row=0, column=3, sticky="w", padx=(0, 8))
        if self._celdra_main_playback_status_v88 is None:
            self._celdra_main_playback_status_v88 = tk.StringVar(
                value="Production player stopped. 1x uses exact authored timing."
            )
        ttk.Label(
            bar,
            textvariable=self._celdra_main_playback_status_v88,
            anchor="w",
        ).grid(row=0, column=4, sticky="ew")

    def _start_main_playback_v88(self, multiplier: float) -> None:
        multiplier = max(1.0, float(multiplier))
        self._celdra_main_playback_multiplier_v88 = multiplier
        if self._celdra_main_playback_status_v88 is not None:
            label = "realtime" if multiplier == 1.0 else f"{multiplier:g}x"
            self._celdra_main_playback_status_v88.set(
                f"Running complete production preview at {label} in RUN ALL."
            )
        self._start_timeline_test_v51(1.0 / multiplier)

    def _stop_main_playback_v88(self) -> None:
        self._cancel_celdra_cues_v49()
        self._cancel_progress_animation_v51()
        self._cancel_name_timer_v58()
        self._hide_speech_bubble_v58()
        self._stop_ambient_v88()
        self._celdra_session_active_v49 = False
        if self._celdra_main_playback_status_v88 is not None:
            self._celdra_main_playback_status_v88.set("Production player stopped.")

    def _scaled_runtime_ms_v88(self, milliseconds: int) -> int:
        speed = max(0.01, float(getattr(self, "_celdra_timeline_speed_v51", 1.0)))
        return max(1, round(int(milliseconds) * speed))

    # ------------------------------------------------------------------
    # Keep the authoring model aligned with Shy 150/Y30 and other PNGs 125/Y0.
    # ------------------------------------------------------------------
    def _apply_dragongirl_authoring_profile_v87(self) -> None:
        super()._apply_dragongirl_authoring_profile_v87()
        rows = extend_with_post_breakpoint(getattr(self, "_celdra_author_events_v74", ()))
        result: list[dict[str, Any]] = []
        for row in rows:
            current = dict(row)
            event_id = str(current.get("id") or "")
            asset = str(current.get("asset") or "").casefold()
            generated = (
                event_id == "canonical-0067"
                or event_id.startswith("dragongirl-")
                or event_id.startswith("runtime-")
            )
            if generated and asset in self.DRAGONGIRL_ASSETS and int(current.get("at_ms") or 0) >= 506_000:
                current["bubble_style"] = DRAGONGIRL_BUBBLE_STYLE
                if asset == "shy":
                    current.update(
                        {
                            "x": STAGE_X["center"],
                            "y": SHY_Y,
                            "scale": SHY_SCALE,
                            **BUBBLE_GEOMETRY["above"],
                        }
                    )
                else:
                    current["y"] = DRAGONGIRL_Y
                    current["scale"] = DRAGONGIRL_SCALE
            result.append(current)
        self._celdra_author_events_v74 = normalize_events(result)
        self._celdra_author_event_serial_v74 = max(
            int(getattr(self, "_celdra_author_event_serial_v74", 0)),
            len(self._celdra_author_events_v74),
        )

    def _author_project_payload_v74(self) -> dict[str, Any]:
        self._apply_dragongirl_authoring_profile_v87()
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V88"
            metadata["canonical_dragongirl_staging"] = {
                "shy": {"scale": SHY_SCALE, "avatar_y": SHY_Y, "avatar_x": STAGE_X["center"]},
                "other_png_emotes": {"scale": DRAGONGIRL_SCALE, "avatar_y": DRAGONGIRL_Y},
                "side_stage_x": {"left": STAGE_X["left"], "right": STAGE_X["right"]},
                "bubble_style": DRAGONGIRL_BUBBLE_STYLE,
            }
            metadata["main_production_playback"] = [1, 5, 20]
            metadata["ambient_green_dialogue_corruption"] = True
        return payload

    # ------------------------------------------------------------------
    # Load Shy at 150%; use a bottom-safe 125% display for every other PNG.
    # ------------------------------------------------------------------
    def _load_takeover_reaction_v58(self, name: str) -> bool:
        folded = str(name or "").casefold()
        self._reload_manifest_emotes_v56()
        row = self._celdra_manifest_emotes_v56.get(folded)
        if row is None:
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION MISSING: {name}")
            return False
        source = self.celdra_asset_root_v50 / str(row.get("source") or "")
        if not source.is_file():
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION SOURCE MISSING: {source}")
            return False
        scale_percent = SHY_SCALE if folded == "shy" else DRAGONGIRL_SCALE
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
            display = (
                cropped.zoom(3, 3).subsample(2, 2)
                if scale_percent == 150
                else cropped.zoom(5, 5).subsample(4, 4)
            )
        except (tk.TclError, OSError, ValueError) as exc:
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION LOAD FAILED: {exc}")
            return False
        self._celdra_manifest_source_v56 = image
        self._celdra_manifest_crop_v56 = cropped
        self._celdra_manifest_display_v56 = display
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = display
        self._celdra_stage_phase_v54 = "dragongirl"
        self._celdra_runtime_current_pose_v87 = folded
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set(
                f"{cropped.width()}x{cropped.height()} -> {display.width()}x{display.height()} "
                f"at {scale_percent}% - {str(row.get('pose') or name).upper()}"
            )
        self._redraw_celdra_avatar_v50()
        return True

    def _set_stage_position_v87(self, stage: str, bubble_side: str) -> None:
        self._celdra_runtime_stage_v87 = stage
        self._celdra_runtime_bubble_side_v87 = bubble_side
        self._celdra_external_offset_x_v65 = STAGE_X[stage]
        self._celdra_external_offset_y_v58 = DRAGONGIRL_Y

    # ------------------------------------------------------------------
    # Scale every callback-driven takeover beat for 1x, 5x, and 20x playback.
    # ------------------------------------------------------------------
    def _start_avatar_takeover_v58(self) -> None:
        self._cancel_name_timer_v58()
        self._hide_name_input_v58()
        self._hide_dialogue_v51()
        self._hide_speech_bubble_v58()
        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = None
        self._celdra_external_offset_y_v58 = 0
        if self._celdra_status_strip_v51 is not None:
            self._celdra_status_strip_v51.grid_remove()
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA SYSTEM INTEGRATION")
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set("CONSOLE PRELOADED - COMPACT AVATAR WAITING")
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.32,
            self._scaled_runtime_ms_v88(1_400),
        )
        self._append_console_v49("[CORE] DRAGONGIRL AVATAR CHANNEL PRELOADED")
        self._append_console_v49("[CORE] CONSOLE CHANNEL LOCKED AND READY")
        for delay in (80, 700, 1_500, 2_800, 4_000):
            self.after(self._scaled_runtime_ms_v88(delay), self._scroll_all_text_v58)
        self._start_ambient_v88()
        self._remember_after_v49(self._scaled_runtime_ms_v88(5_000), self._begin_shy_reveal_v64)
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(21_500),
            lambda: self._show_speech_bubble_v58("Test, Test, check check. Can you hear me?"),
        )
        self._remember_after_v49(self._scaled_runtime_ms_v88(26_500), self._takeover_confused_v58)
        self._remember_after_v49(self._scaled_runtime_ms_v88(30_500), self._takeover_console_return_v58)
        self._remember_after_v49(self._scaled_runtime_ms_v88(36_500), self._takeover_wink_v58)

    def _begin_shy_reveal_v64(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        canvas_height = canvas.winfo_height() if canvas is not None else 420
        self._celdra_runtime_bubble_side_v87 = "above"
        self._celdra_runtime_stage_v87 = "center"
        self._celdra_external_offset_x_v65 = STAGE_X["center"]
        if not self._load_takeover_reaction_v58("shy"):
            return
        self._celdra_shy_rest_offset_v64 = SHY_Y
        self._celdra_external_offset_y_v58 = max(320, canvas_height + 90)
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.50,
            self._scaled_runtime_ms_v88(1_650),
        )
        self._redraw_celdra_avatar_v50()
        self._remember_after_v49(self._scaled_runtime_ms_v88(260), self._start_shy_creep_v58)

    def _start_shy_creep_v58(self) -> None:
        if self._celdra_creep_after_v58 is not None:
            try:
                self.after_cancel(self._celdra_creep_after_v58)
            except tk.TclError:
                pass
        start = max(1, int(self._celdra_external_offset_y_v58 or 0))
        target = SHY_Y
        distance = max(1, start - target)
        started = time.monotonic()
        duration_ms = self._scaled_runtime_ms_v88(12_000)

        def tick() -> None:
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / max(1, duration_ms))
            progress = self._shy_progress_v63(fraction)
            self._celdra_external_offset_y_v58 = round(start - distance * progress)
            self._redraw_celdra_avatar_v50()
            if fraction < 1.0:
                self._celdra_creep_after_v58 = self.after(16, tick)
            else:
                self._celdra_external_offset_y_v58 = target
                self._celdra_creep_after_v58 = None
                self._redraw_celdra_avatar_v50()

        tick()

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
        self._show_speech_bubble_v58("Well, can you?")

    def _takeover_console_return_v58(self) -> None:
        self._hide_speech_bubble_v58()
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.62,
            self._scaled_runtime_ms_v88(820),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(850),
            lambda: self._append_console_v49("[BRAIN] THEY CAN'T TYPE OR TALK BACK, DUMMY"),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(1_450),
            lambda: self._append_console_v49(
                "[BRAIN] LOOKING GOOD THO, GIRL. LIKE I SAID, KILLING IT!"
            ),
        )

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
                "Alright, Operation Dragonegg is a go!\n"
                f"Like I said, my name is Celdra. Nice to meet you, {name}."
            ),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(7_000),
            self._start_placeholder_runtime_v70,
        )

    def _runtime_pose_v70(self, pose: str, text: str) -> None:
        folded = str(pose or "neutral").casefold()
        if (
            self._celdra_pipeline_success_v70
            and self._celdra_placeholder_started_v70
            and folded != "cool"
        ):
            folded = "cool"
            text = self._completion_text_v87()
        stage, bubble_side = self.POSE_STAGE.get(folded, ("right", "left"))
        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._slide_chat_v54(show=False, duration_ms=self._scaled_runtime_ms_v88(320))
        self._set_stage_position_v87(stage, bubble_side)
        if not self._load_takeover_reaction_v58(folded):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.56,
            self._scaled_runtime_ms_v88(650),
        )
        self.after_idle(self._redraw_celdra_avatar_v50)
        self._show_speech_bubble_v58(text)

    def _start_placeholder_runtime_v70(self) -> None:
        if self._celdra_placeholder_started_v70:
            return
        self._celdra_placeholder_started_v70 = True
        self._hide_speech_bubble_v58()
        self._runtime_pose_v70("confused", self._assessment_text_v70())
        if self._celdra_pipeline_success_v70:
            self._show_completion_cool_v70()
            return
        for delay, pose, text in self.INITIAL_FILLER:
            self._remember_after_v49(
                self._scaled_runtime_ms_v88(delay),
                lambda selected_pose=pose, selected_text=text: self._runtime_filler_pose_v87(
                    selected_pose,
                    selected_text,
                ),
            )
        for delay, speaker, text in self.INITIAL_CONSOLE_BANTER:
            self._remember_after_v49(
                self._scaled_runtime_ms_v88(delay),
                lambda selected_speaker=speaker, selected_text=text: self._runtime_console_banter_v88(
                    selected_speaker,
                    selected_text,
                ),
            )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(46_800),
            self._runtime_wait_or_complete_v87,
        )

    def _runtime_console_banter_v88(self, speaker: str, text: str) -> None:
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._append_console_v49(f"[{speaker}] {text}")

    def _runtime_wait_or_complete_v87(self) -> None:
        if bool(getattr(self, "_celdra_test_mode_v58", False)):
            self._runtime_pose_v70(
                "cool",
                "Test sequence complete. The poses fit, the bubbles stayed in their lanes, "
                "and nothing caught fire where you could see it.",
            )
            if self._celdra_main_playback_status_v88 is not None:
                self._celdra_main_playback_status_v88.set("Production preview complete - Cool pose locked.")
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
            self._scaled_runtime_ms_v88(7_000),
            self._runtime_wait_or_complete_v87,
        )

    # ------------------------------------------------------------------
    # Restrained ambient green corruption sourced from current dialogue/console.
    # ------------------------------------------------------------------
    def _remember_ambient_source_v88(self, text: str) -> None:
        for raw in str(text or "").splitlines():
            clean = re.sub(r"^\s*\[[^]]+\]\s*", "", raw).strip()
            clean = re.sub(r"\s+", " ", clean)
            if len(clean) < 3:
                continue
            self._celdra_ambient_sources_v88.append(clean[:96])
        self._celdra_ambient_sources_v88 = self._celdra_ambient_sources_v88[-18:]

    def _append_console_v49(self, text: str) -> None:
        self._remember_ambient_source_v88(text)
        super()._append_console_v49(text)

    def _append_chat_v49(self, text: str) -> None:
        self._remember_ambient_source_v88(text)
        super()._append_chat_v49(text)

    def _show_speech_bubble_v58(self, text: str) -> None:
        self._remember_ambient_source_v88(text)
        super()._show_speech_bubble_v58(text)

    def _start_ambient_v88(self) -> None:
        if self._celdra_ambient_after_v88 is not None:
            return

        def tick() -> None:
            self._celdra_ambient_after_v88 = None
            if not bool(getattr(self, "_celdra_takeover_active_v58", False)):
                return
            self._celdra_ambient_phase_v88 += 1
            self._redraw_celdra_avatar_v50()
            speed = max(0.20, float(getattr(self, "_celdra_timeline_speed_v51", 1.0)))
            self._celdra_ambient_after_v88 = self.after(max(120, round(720 * speed)), tick)

        self._celdra_ambient_after_v88 = self.after(120, tick)

    def _stop_ambient_v88(self) -> None:
        if self._celdra_ambient_after_v88 is not None:
            try:
                self.after_cancel(self._celdra_ambient_after_v88)
            except tk.TclError:
                pass
            self._celdra_ambient_after_v88 = None
        canvas = self.celdra_avatar_canvas_v50
        if canvas is not None:
            try:
                canvas.delete(self.AMBIENT_TAG)
            except tk.TclError:
                pass

    @staticmethod
    def _ambient_fragment_v88(source: str, slot: int, phase: int) -> str:
        words = re.findall(r"[A-Z0-9_.%/-]+", str(source or "").upper())
        if not words:
            return "CELDRA//00"
        start = (slot * 2 + phase) % len(words)
        take = min(4, len(words))
        fragment = " ".join(words[(start + index) % len(words)] for index in range(take))[:34]
        mode = (slot + phase) % 5
        if mode == 0:
            return fragment
        if mode == 1:
            return fragment[::-1]
        if mode == 2:
            noise = "01?#/"
            return "".join(
                noise[(index + slot + phase) % len(noise)] if index % 5 == 0 else character
                for index, character in enumerate(fragment)
            )
        if mode == 3:
            checksum = sum(ord(character) for character in fragment) & 0xFF
            return f"{fragment[:24]} // {checksum:02X}"
        return " ".join(f"{ord(character):02X}" for character in fragment[:7])

    def _draw_ambient_v88(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if (
            canvas is None
            or not bool(getattr(self, "_celdra_takeover_active_v58", False))
            or self.celdra_current_external_v50 is None
            or bool(getattr(self, "_celdra_energy_active_v63", False))
        ):
            return
        try:
            canvas.delete(self.AMBIENT_TAG)
        except tk.TclError:
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        if width < 120 or height < 120:
            return
        sources = self._celdra_ambient_sources_v88 or ["CELDRA ONLINE"]
        phase = self._celdra_ambient_phase_v88
        count = max(5, min(9, width // 115))
        usable_width = max(30, width - 40)
        usable_height = max(30, height - 110)
        for slot in range(count):
            source = sources[(slot * 3 + phase) % len(sources)]
            text = self._ambient_fragment_v88(source, slot, phase)
            x = 20 + ((slot * 109 + phase * (3 + slot % 4)) % usable_width)
            y = 58 + ((slot * 71 + phase * (2 + slot % 3)) % usable_height)
            canvas.create_text(
                x,
                y,
                text=text,
                anchor="center",
                fill=self.AMBIENT_COLORS[(slot + phase) % len(self.AMBIENT_COLORS)],
                font=("Fixedsys", 7 + (slot + phase) % 3),
                tags=self.AMBIENT_TAG,
            )
        try:
            canvas.tag_lower(self.AMBIENT_TAG)
        except tk.TclError:
            pass

    def _redraw_celdra_avatar_v50(self) -> None:
        super()._redraw_celdra_avatar_v50()
        self._draw_ambient_v88()

    # ------------------------------------------------------------------
    # Reset transient playback/ambient state without altering the early timeline.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._stop_ambient_v88()
        self._celdra_ambient_phase_v88 = 0
        self._celdra_ambient_sources_v88 = [
            "CELDRA ONLINE",
            "CCSF EXTRACTION ACTIVE",
            "FRAGMENTER SUPERVISION CHANNEL",
            "RUN ALL STATUS NOMINAL",
        ]
        super()._prepare_first_run_surface_v51()

    def _cancel_celdra_cues_v49(self) -> None:
        self._stop_ambient_v88()
        super()._cancel_celdra_cues_v49()


def main() -> int:
    app = PublicFragmenterAppV88()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

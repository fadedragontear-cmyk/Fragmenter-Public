#!/usr/bin/env python3
"""Reusable V60 Celdra viewport and avatar behavior."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Any, Iterable

from celdra_assets_v1 import asset_inventory
from celdra_evolution_pixel_v1 import frame_resolution
from celdra_evolution_pixel_v4 import (
    CELDRA_BLUE_PALETTE, CRACK_ONE_LOOP, CRACK_TWO_LOOP, EGG_LOOP, EYES_LOOP, EVOLUTION_PHASES,
    HATCHLING_BASE_FAILED, HATCHLING_IDLE, HATCHLING_SEARCH,
    HATCHLING_SQUISHED, HATCH_SEQUENCE, PHASE_OPEN_FRACTIONS,
)
from celdra_pixel_pet_v1 import PixelFrame
from fragmenter_public_gui_v54 import PublicFragmenterAppV54


class CeldraV60RuntimeMixin:
    def _load_celdra_avatar_frames_v49(self) -> None:
        self.celdra_asset_inventory_v50 = asset_inventory(self.celdra_asset_root_v50)
        self.celdra_external_frames_v50 = {}
        self._play_pixel_sequence_v50(EGG_LOOP, loop=True)

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        external = self.celdra_current_external_v50
        if external is not None:
            offset = self._celdra_external_offset_y_v58 if self._celdra_takeover_active_v58 else 0
            canvas.create_image(
                width // 2,
                height // 2 + 12 + offset,
                image=external,
                anchor="center",
            )
            return
        frame = self.celdra_current_pixel_v50
        if frame is None:
            return
        rows = frame.rows
        columns = max((len(row) for row in rows), default=1)
        usable_height = max(1, height - 43)
        scale = max(2, min(width // max(1, columns), usable_height // max(1, len(rows))))
        art_width = columns * scale
        art_height = len(rows) * scale
        x0 = (width - art_width) // 2
        y0 = 43 + max(0, (usable_height - art_height) // 2)
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = CELDRA_BLUE_PALETTE.get(symbol, "")
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

    def _show_avatar_v51(self) -> None:
        if not self._celdra_stage_ready_v54:
            super()._show_avatar_v51()
            return
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._slide_chat_v54(show=False, duration_ms=420)
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA EVOLUTION VIEWPORT")
        target = PHASE_OPEN_FRACTIONS.get(
            self._celdra_stage_phase_v54,
            self._celdra_stage_open_fraction_v54,
        )
        self._animate_stage_fraction_v54(target, 1_050)
        self.after_idle(self._redraw_celdra_avatar_v50)

    def _set_avatar_phase_v51(self, phase: str) -> None:
        phase = str(phase or "egg_wait").casefold()
        self._celdra_stage_phase_v54 = phase
        frames = EVOLUTION_PHASES.get(phase, EGG_LOOP)
        loop = phase not in {"hatch_open", "baby_rise"}
        next_state = "idle" if phase in {"hatch_open", "baby_rise"} else None
        self._play_pixel_sequence_v50(frames, loop=loop, next_state=next_state)
        self._update_evolution_detail_v60(phase, frames)
        if self._celdra_stage_avatar_visible_v54 and not self._celdra_takeover_active_v58:
            self._animate_stage_fraction_v54(
                PHASE_OPEN_FRACTIONS.get(phase, self._celdra_stage_open_fraction_v54),
                820,
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
            frames = EVOLUTION_PHASES.get(phase, HATCHLING_IDLE)
            self._play_pixel_sequence_v50(frames, loop=len(frames) > 1)
        self._celdra_stage_phase_v54 = phase
        self._update_evolution_detail_v60(phase, frames)

    def _update_evolution_detail_v60(
        self,
        phase: str,
        frames: Iterable[PixelFrame],
    ) -> None:
        frame_tuple = tuple(frames)
        width, height = frame_resolution(frame_tuple[0]) if frame_tuple else (0, 0)
        labels = {
            "egg_wait": "SEALED DRAGONEGG",
            "crack_one": "SHELL STRESS",
            "crack_two": "HATCHING ESCALATION",
            "eyes": "HATCHLING AWAKE",
            "hatch_open": "SHELL RELEASE / VIEWPORT EXPANSION",
            "baby_rise": "BABY DRAGON EMERGING",
            "idle": "APPROVED BLUE HATCHLING",
            "baby_idle": "APPROVED BLUE HATCHLING",
            "base_search": "SEARCHING USER BASE",
            "searching": "SEARCHING USER BASE",
            "compact_idle": "CONSOLE PRESSURE DETECTED",
            "squished": "CONSOLE PRESSURE DETECTED",
            "distressed": "CONSOLE PRESSURE DETECTED",
            "base_claim": "BASE ACQUISITION CONFIDENCE",
            "base_failed": "NO ADDITIONAL BASE FOUND",
            "talk": "VOCALIZATION",
            "thinking": "COGNITIVE SEARCH",
            "smirk": "SASS SUBSYSTEM",
            "young_dragon": "YOUNG DRAGON FORM",
            "dragongirl": "DRAGONGIRL AVATAR",
        }
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set(
                f"{width}×{height} • {labels.get(phase, phase.upper())}"
            )

    def _emit_timeline_event_v51(self, event: Any) -> None:
        action = str(getattr(event, "action", "") or "")
        text = str(getattr(event, "text", "") or "")
        folded = text.casefold()

        if action == "status" and any(marker in folded for marker in self.BASE_STATUS_MARKERS):
            self._set_avatar_phase_v51("base_search")
            self._show_avatar_v51()
        super()._emit_timeline_event_v51(event)

        if action == "base_joke_end":
            self._remember_after_v49(420, self._show_base_failed_v60)
        elif action == "console" and "checking for additional base [failed]" in folded:
            self._remember_after_v49(650, self._show_base_failed_v60)

    def _show_base_failed_v60(self) -> None:
        if self._celdra_takeover_active_v58 or self._celdra_base_failed_pending_v60:
            return
        self._celdra_base_failed_pending_v60 = True
        self._celdra_stage_phase_v54 = "base_failed"
        self._play_pixel_sequence_v50(HATCHLING_BASE_FAILED, loop=True)
        self._update_evolution_detail_v60("base_failed", HATCHLING_BASE_FAILED)
        self._show_avatar_v51()
        self._remember_after_v49(2_600, self._finish_base_failed_v60)

    def _finish_base_failed_v60(self) -> None:
        self._celdra_base_failed_pending_v60 = False
        self._hide_avatar_v51()

    def _apply_compact_idle_v58(self) -> None:
        self._celdra_compact_after_v58 = None
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None or self.celdra_current_external_v50 is not None:
            return
        width = canvas.winfo_width()
        height = max(1, canvas.winfo_height())
        compact = width < 350 or width < height * 0.74
        if compact == self._celdra_squished_active_v60:
            return
        self._celdra_squished_active_v60 = compact
        phase = self._celdra_stage_phase_v54
        if phase not in {"idle", "baby_idle", "base_search", "searching"}:
            return
        if compact:
            frames = HATCHLING_SQUISHED
            label = "squished"
        elif phase in {"base_search", "searching"}:
            frames = HATCHLING_SEARCH
            label = "base_search"
        else:
            frames = HATCHLING_IDLE
            label = "idle"
        self._play_pixel_sequence_v50(frames, loop=True)
        self._update_evolution_detail_v60(label, frames)

    def _scaled_manifest_reaction_v60(
        self,
        name: str,
        *,
        quiet: bool,
    ) -> tuple[tk.PhotoImage, tk.PhotoImage, tk.PhotoImage, dict[str, Any]] | None:
        self._reload_manifest_emotes_v56()
        row = self._celdra_manifest_emotes_v56.get(str(name or "").casefold())
        if row is None:
            if not quiet:
                messagebox.showinfo("Celdra avatar", f"No classified emote named '{name}' was found.")
            return None
        source = self.celdra_asset_root_v50 / str(row.get("source") or "")
        if not source.is_file():
            if not quiet:
                messagebox.showerror("Celdra avatar", f"Missing source sheet:\n{source}")
            return None
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
            display = cropped.zoom(3, 3).subsample(2, 2)
            display = self._fit_photo_v50(display, 340, 400)
        except (tk.TclError, OSError, ValueError) as exc:
            if not quiet:
                messagebox.showerror("Celdra avatar", str(exc))
            else:
                self._append_console_v49(f"[CORE] CLASSIFIED REACTION LOAD FAILED: {exc}")
            return None
        return image, cropped, display, row

    def _show_manifest_emote_v56(self, name: str, *, quiet: bool = False) -> bool:
        loaded = self._scaled_manifest_reaction_v60(name, quiet=quiet)
        if loaded is None:
            return False
        image, cropped, display, row = loaded
        self._celdra_manifest_source_v56 = image
        self._celdra_manifest_crop_v56 = cropped
        self._celdra_manifest_display_v56 = display
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = display
        self._celdra_stage_phase_v54 = "dragongirl"
        pose = str(row.get("pose") or row.get("state") or "reaction")
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA DRAGONGIRL AVATAR")
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set(
                f"{cropped.width()}×{cropped.height()} • {pose.upper()} • 75% DISPLAY"
            )
        self._show_avatar_v51()
        self.after_idle(self._redraw_celdra_avatar_v50)
        return True

    def _show_emote_in_celdra_v52(self) -> None:
        cropped = self._preview_emote_crop_v52()
        if cropped is None:
            return
        fitted = self._fit_photo_v50(cropped, 280, 340)
        self.emote_preview_image_v52 = fitted
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = fitted
        self._celdra_stage_phase_v54 = "dragongirl"
        self._show_avatar_v51()
        self._select_run_all_tab_v50()
        self._redraw_celdra_avatar_v50()

    def _load_takeover_reaction_v58(self, name: str) -> bool:
        loaded = self._scaled_manifest_reaction_v60(name, quiet=True)
        if loaded is None:
            return False
        image, cropped, display, row = loaded
        self._celdra_manifest_source_v56 = image
        self._celdra_manifest_crop_v56 = cropped
        self._celdra_manifest_display_v56 = display
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = display
        self._celdra_stage_phase_v54 = "dragongirl"
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set(
                f"{cropped.width()}×{cropped.height()} • {str(row.get('pose') or name).upper()} • 75% DISPLAY"
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
        canvas_height = self.celdra_avatar_canvas_v50.winfo_height() if self.celdra_avatar_canvas_v50 else 360
        self._celdra_external_offset_y_v58 = max(90, min(170, canvas_height // 3))

        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.58, 1_050)
        self.after(260, self._scroll_all_text_v58)
        self.after(350, self._start_shy_creep_v58)
        self._remember_after_v49(
            3_300,
            lambda: self._show_speech_bubble_v58("Test, Test, Check check can you hear me?"),
        )
        self._remember_after_v49(6_400, self._takeover_confused_v58)
        self._remember_after_v49(8_700, self._takeover_console_return_v58)
        self._remember_after_v49(12_300, self._takeover_wink_v58)

    def _takeover_confused_v58(self) -> None:
        self._load_takeover_reaction_v58("confused")
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.60, 520)
        self._show_speech_bubble_v58("Well can you?")

    def _takeover_console_return_v58(self) -> None:
        self._hide_speech_bubble_v58()
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.46, 820)
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
        self._remember_after_v49(1_650, self._scroll_all_text_v58)

    def _takeover_wink_v58(self) -> None:
        self._load_takeover_reaction_v58("wink")
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.80, 900)
        name = self._celdra_user_name_v58 or "noname"
        self._remember_after_v49(
            950,
            lambda: self._show_speech_bubble_v58(
                "Alright, Operation Dragonegg is a go!\n"
                f"Like I said, my name is Celdra. Nice to meet you, {name}."
            ),
        )

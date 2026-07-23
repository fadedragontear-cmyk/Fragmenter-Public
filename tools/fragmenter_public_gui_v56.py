#!/usr/bin/env python3
"""V56: staged Celdra progress, cuter hatchling, base gag, and emote runtime."""
from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Iterable

from celdra_assets_v1 import asset_inventory
from celdra_emote_classifier_v1 import definitions_from_manifest, load_manifest
from celdra_evolution_pixel_v2 import (
    CELDRA_BLUE_PALETTE,
    CRACK_ONE_LOOP,
    CRACK_TWO_LOOP,
    EGG_LOOP,
    EYES_LOOP,
    EVOLUTION_PHASES,
    HATCH_SEQUENCE,
    PHASE_OPEN_FRACTIONS,
    frame_resolution,
)
from celdra_pixel_pet_v1 import PixelFrame
from celdra_startup_timeline_v3 import (
    CCSF_HATCH_DELAY_MS,
    DEPLOY_MIN_MS,
    DEPLOY_STATUS,
    FIRST_RUN_AFTER_CCSF,
    TimelineEvent,
)
from fragmenter_public_gui_v55 import PublicFragmenterAppV55


class PublicFragmenterAppV56(PublicFragmenterAppV55):
    """Integrate the classified dragongirl art with the refined first-run show."""

    def __init__(self) -> None:
        self._celdra_progress_percent_v56: tk.StringVar | None = None
        self._celdra_base_overlay_v56: tk.Label | None = None
        self._celdra_manifest_emotes_v56: dict[str, dict[str, Any]] = {}
        self._celdra_manifest_source_v56: tk.PhotoImage | None = None
        self._celdra_manifest_crop_v56: tk.PhotoImage | None = None
        self._celdra_manifest_display_v56: tk.PhotoImage | None = None
        self._celdra_manifest_selector_v56: tk.StringVar | None = None
        super().__init__()
        self._reload_manifest_emotes_v56()
        self.title("Fragmenter 1.0 WIP — Celdra Staged Evolution Presentation")

    # ------------------------------------------------------------------
    # Progress is a sequence of complete presentation jobs, not one global bar.
    # ------------------------------------------------------------------
    def _build_run_all(self, parent: ttk.Frame) -> None:
        super()._build_run_all(parent)
        strip = self._celdra_status_strip_v51
        if strip is not None:
            self._celdra_progress_percent_v56 = tk.StringVar(value="0%")
            ttk.Label(
                strip,
                textvariable=self._celdra_progress_percent_v56,
                width=5,
                anchor="e",
            ).grid(row=0, column=1, sticky="e", padx=(8, 0))

    def _animate_progress_v51(self, start: float, end: float, duration_ms: int) -> None:
        self._cancel_progress_animation_v51()
        token = self._celdra_progress_token_v51
        duration_ms = max(1, int(duration_ms))
        started = time.monotonic()
        self._set_celdra_fake_progress_v49(start)
        if self._celdra_progress_percent_v56 is not None:
            self._celdra_progress_percent_v56.set(f"{round(start):d}%")

        def tick() -> None:
            if token != self._celdra_progress_token_v51:
                return
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / duration_ms)
            value = start + (end - start) * fraction
            self._set_celdra_fake_progress_v49(value)
            if self._celdra_progress_percent_v56 is not None:
                self._celdra_progress_percent_v56.set(f"{round(value):d}%")
            if fraction < 1.0:
                self._celdra_progress_after_v51 = self.after(200, tick)
            else:
                self._celdra_progress_after_v51 = None

        tick()

    # ------------------------------------------------------------------
    # V3 timing: hatch is one 0-100 bar; every base job resets to zero.
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
        if event.action == "base_joke":
            self._start_base_joke_v56(event.text)
            return
        if event.action == "base_joke_end":
            self._end_base_joke_v56()
            return
        if event.action == "breakpoint":
            super()._emit_timeline_event_v51(event)
            # The viability checkpoint now proves that the classified sheet can
            # become a live viewport portrait without exporting a separate PNG.
            self._show_manifest_emote_v56("neutral", quiet=True)
            return
        super()._emit_timeline_event_v51(event)

    # ------------------------------------------------------------------
    # Larger, cuter 36x36 hatchling and 48x48 young-dragon presentation.
    # ------------------------------------------------------------------
    def _load_celdra_avatar_frames_v49(self) -> None:
        self.celdra_asset_inventory_v50 = asset_inventory(self.celdra_asset_root_v50)
        self.celdra_external_frames_v50 = {}
        self._play_pixel_sequence_v50(EGG_LOOP, loop=True)

    def _show_avatar_v51(self) -> None:
        if not self._celdra_stage_ready_v54:
            super()._show_avatar_v51()
            return
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._slide_chat_v54(show=False, duration_ms=420)
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA EVOLUTION VIEWPORT")
        self._animate_stage_fraction_v54(
            PHASE_OPEN_FRACTIONS.get(
                self._celdra_stage_phase_v54,
                self._celdra_stage_open_fraction_v54,
            ),
            1050,
        )
        self.after_idle(self._redraw_celdra_avatar_v50)

    def _set_avatar_phase_v51(self, phase: str) -> None:
        phase = str(phase or "egg_wait").casefold()
        self._celdra_stage_phase_v54 = phase
        frames = EVOLUTION_PHASES.get(phase, EGG_LOOP)
        loop = phase not in {"hatch_open", "baby_rise"}
        next_state = "idle" if phase in {"hatch_open", "baby_rise"} else None
        self._play_pixel_sequence_v50(frames, loop=loop, next_state=next_state)
        self._update_evolution_detail_v54(phase, frames)
        if self._celdra_stage_avatar_visible_v54:
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
            frames = EVOLUTION_PHASES.get(phase, EVOLUTION_PHASES["idle"])
            self._play_pixel_sequence_v50(frames, loop=len(frames) > 1)
        self._celdra_stage_phase_v54 = phase
        self._update_evolution_detail_v54(phase, frames)

    # ------------------------------------------------------------------
    # Animated ALL YOUR BASE interlude.
    # ------------------------------------------------------------------
    def _install_horizontal_celdra_stage_v54(self) -> None:
        super()._install_horizontal_celdra_stage_v54()
        stage = self._celdra_avatar_pane_v51
        if stage is None or self._celdra_base_overlay_v56 is not None:
            return
        overlay = tk.Label(
            stage,
            text="",
            background="#071426",
            foreground="#e2f5ff",
            font=("Consolas", 17, "bold"),
            justify="center",
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=8,
        )
        overlay.place_forget()
        self._celdra_base_overlay_v56 = overlay

    def _start_base_joke_v56(self, _text: str) -> None:
        self._set_avatar_phase_v51("base_claim")
        self._show_avatar_v51()
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("BASE ACQUISITION SUBROUTINE")
        overlay = self._celdra_base_overlay_v56
        if overlay is None:
            return
        overlay.place(relx=0.5, rely=0.78, anchor="center", relwidth=0.92)
        overlay.lift()
        phrases = (
            (0, "ALL"),
            (900, "ALL YOUR"),
            (1800, "ALL YOUR BASE"),
            (3000, "ALL YOUR BASE\nARE"),
            (4300, "ALL YOUR BASE\nARE BELONG"),
            (5700, "ALL YOUR BASE\nARE BELONG TO"),
            (7200, "ALL YOUR BASE\nARE BELONG TO US"),
            (8600, "ALL YOUR BASE\nARE BELONG TO US_"),
            (9400, "ALL YOUR BASE\nARE BELONG TO US"),
        )
        speed = max(0.01, float(self._celdra_timeline_speed_v51))
        for index, (delay, phrase) in enumerate(phrases):
            self._remember_after_v49(
                max(1, round(delay * speed)),
                lambda value=phrase, selected=index: self._set_base_text_v56(value, selected),
            )

    def _set_base_text_v56(self, text: str, index: int) -> None:
        overlay = self._celdra_base_overlay_v56
        if overlay is None:
            return
        colors = ("#e2f5ff", "#83c7f1", "#b9e8ff", "#ead77d")
        overlay.configure(text=text, foreground=colors[index % len(colors)])

    def _end_base_joke_v56(self) -> None:
        if self._celdra_base_overlay_v56 is not None:
            self._celdra_base_overlay_v56.place_forget()
        self._hide_avatar_v51()

    # ------------------------------------------------------------------
    # Runtime use of the user-classified emote sheets.
    # ------------------------------------------------------------------
    def _reload_manifest_emotes_v56(self) -> None:
        rows = definitions_from_manifest(load_manifest(self.celdra_asset_root_v50))
        mapping: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not bool(row.get("enabled", True)):
                continue
            for key in (str(row.get("state") or ""), str(row.get("pose") or "")):
                folded = key.strip().casefold()
                if folded:
                    mapping.setdefault(folded, row)
        self._celdra_manifest_emotes_v56 = mapping
        selector = self._celdra_manifest_selector_v56
        if selector is not None and not selector.get() and mapping:
            selector.set("neutral" if "neutral" in mapping else sorted(mapping)[0])

    def _show_manifest_emote_v56(self, name: str, *, quiet: bool = False) -> bool:
        self._reload_manifest_emotes_v56()
        row = self._celdra_manifest_emotes_v56.get(str(name or "").casefold())
        if row is None:
            if not quiet:
                messagebox.showinfo("Celdra avatar", f"No classified emote named '{name}' was found.")
            return False
        source = self.celdra_asset_root_v50 / str(row.get("source") or "")
        if not source.is_file():
            if not quiet:
                messagebox.showerror("Celdra avatar", f"Missing source sheet:\n{source}")
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
            display = self._fit_photo_v50(enlarged, 430, 510)
        except (tk.TclError, OSError, ValueError) as exc:
            if not quiet:
                messagebox.showerror("Celdra avatar", str(exc))
            return False

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
                f"{cropped.width()}×{cropped.height()} • {pose.upper()}"
            )
        self._show_avatar_v51()
        self.after_idle(self._redraw_celdra_avatar_v50)
        return True

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
        self._reload_manifest_emotes_v56()
        states = sorted(
            {
                str(row.get("state") or "")
                for row in self._celdra_manifest_emotes_v56.values()
                if row.get("state")
            }
        )
        self._celdra_manifest_selector_v56 = tk.StringVar(
            value="neutral" if "neutral" in states else (states[0] if states else "")
        )
        box = ttk.LabelFrame(controls, text="Classified dragongirl reactions", padding=4)
        box.pack(fill="x", pady=(7, 2))
        ttk.Combobox(
            box,
            textvariable=self._celdra_manifest_selector_v56,
            values=states,
            state="readonly",
            width=19,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            box,
            text="Show",
            command=lambda: self._show_manifest_emote_v56(
                self._celdra_manifest_selector_v56.get()
            ),
        ).pack(side="right", padx=(5, 0))


def main() -> int:
    app = PublicFragmenterAppV56()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

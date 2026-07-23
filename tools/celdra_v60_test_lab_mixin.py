#!/usr/bin/env python3
"""Reusable V60 Celdra Test layout and preview controls."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class CeldraV60TestLabMixin:
    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        frame = self.tabs.get("Celdra Test")
        if frame is None:
            return
        controls = self._find_test_section_v60(frame, "Script and avatar tests")
        assets = self._find_test_section_v60(frame, "Bundled asset inventory / crop calibration")
        classifier = self._find_test_section_v60(frame, "Emote PNG separator / pose classifier")
        if controls is not None:
            self._clean_test_controls_v60(controls)
        if controls is not None and assets is not None and classifier is not None:
            self._install_test_divider_v60(frame, controls, assets, classifier)

    @staticmethod
    def _find_test_section_v60(frame: ttk.Frame, title: str) -> ttk.LabelFrame | None:
        return next(
            (
                child
                for child in frame.winfo_children()
                if isinstance(child, ttk.LabelFrame)
                and str(child.cget("text")) == title
            ),
            None,
        )

    def _clean_test_controls_v60(self, controls: ttk.LabelFrame) -> None:
        redundant = {
            "Full First-Run Intro",
            "Pixel Egg / Hatch",
            "Baby Idle",
            "Talk",
            "Thinking",
            "Smirk",
            "V54 Polished Egg Loop",
            "V54 First Crack Loop",
            "V54 Advanced Crack Loop",
            "V54 Eyes in Egg",
            "V58 Reworked Hatchling",
            "V58 Hatchling Idle",
            "Young Dragon 56×56",
            "V54 Dragongirl Canvas Target",
            "V54 Slide Dialogue",
            "V58 Avatar Reveal",
        }
        visible_children: list[tk.Widget] = []
        for child in controls.winfo_children():
            text = str(child.cget("text")) if isinstance(child, ttk.Button) else ""
            if text in redundant or isinstance(child, ttk.Separator):
                child.grid_forget()
                child.pack_forget()
                continue
            visible_children.append(child)

        preview_box = ttk.LabelFrame(controls, text="Animation preview", padding=5)
        choices = (
            "Polished egg loop",
            "Egg to hatchling",
            "Cute hatchling idle",
            "Search for base",
            "Squished / distressed",
            "All your base claim",
            "No additional base",
            "Young dragon 68×68",
            "Interactive avatar reveal",
        )
        self._celdra_preview_map_v60 = {
            choices[0]: "egg_wait",
            choices[1]: "hatch_open",
            choices[2]: "idle",
            choices[3]: "base_search",
            choices[4]: "squished",
            choices[5]: "base_claim",
            choices[6]: "base_failed",
            choices[7]: "young_dragon",
            choices[8]: "avatar_takeover",
        }
        self._celdra_preview_choice_v60 = tk.StringVar(value=choices[0])
        ttk.Combobox(
            preview_box,
            textvariable=self._celdra_preview_choice_v60,
            values=choices,
            state="readonly",
            width=29,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(preview_box, text="Play", command=self._play_preview_v60).pack(
            side="right", padx=(6, 0)
        )
        visible_children.insert(0, preview_box)

        for child in controls.winfo_children():
            child.grid_forget()
            child.pack_forget()
        for column in range(4):
            controls.columnconfigure(column, weight=1, uniform="celdra-test-v60")

        row = 0
        column = 0
        for child in visible_children:
            if child is preview_box or not isinstance(child, ttk.Button):
                if column:
                    row += 1
                    column = 0
                child.grid(row=row, column=0, columnspan=4, sticky="ew", padx=2, pady=3)
                row += 1
                continue
            child.grid(row=row, column=column, sticky="ew", padx=2, pady=2)
            column += 1
            if column >= 4:
                column = 0
                row += 1
        controls.grid_configure(sticky="nsew")

    def _play_preview_v60(self) -> None:
        choice = self._celdra_preview_choice_v60.get() if self._celdra_preview_choice_v60 else ""
        phase = self._celdra_preview_map_v60.get(choice, "egg_wait")
        self._select_run_all_tab_v50()
        self._celdra_session_active_v49 = True
        if phase == "avatar_takeover":
            self._start_avatar_takeover_v58()
            return
        self._hide_dialogue_v51()
        if phase == "hatch_open":
            self._set_avatar_state_v49("hatch")
        else:
            self._set_avatar_phase_v51(phase)
        self._show_avatar_v51()

    def _install_test_divider_v60(
        self,
        frame: ttk.Frame,
        controls: ttk.LabelFrame,
        assets: ttk.LabelFrame,
        classifier: ttk.LabelFrame,
    ) -> None:
        controls.grid_configure(row=1, column=0, sticky="nsew", padx=(0, 7), pady=0)
        assets.grid_configure(row=1, column=1, sticky="nsew", pady=0)
        classifier.grid_configure(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 0))
        frame.rowconfigure(1, weight=0, minsize=self._celdra_test_top_height_v60)
        frame.rowconfigure(2, weight=0, minsize=9)
        frame.rowconfigure(3, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=3)

        handle = tk.Frame(
            frame,
            height=9,
            background="#35536f",
            cursor="sb_v_double_arrow",
            highlightthickness=0,
        )
        handle.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        tk.Label(
            handle,
            text="⋯  DRAG TO RESIZE TESTS / CLASSIFIER  ⋯",
            background="#35536f",
            foreground="#d9f1ff",
            font=("Segoe UI", 8, "bold"),
            cursor="sb_v_double_arrow",
        ).pack(fill="x")
        for widget in (handle, *handle.winfo_children()):
            widget.bind(
                "<B1-Motion>",
                lambda event, selected_frame=frame, selected_controls=controls, selected_assets=assets: self._drag_test_divider_v60(
                    event,
                    selected_frame,
                    selected_controls,
                    selected_assets,
                ),
            )
        self._celdra_test_divider_v60 = handle
        self.after_idle(
            lambda: self._set_test_top_height_v60(
                frame,
                controls,
                assets,
                self._celdra_test_top_height_v60,
            )
        )

    def _drag_test_divider_v60(
        self,
        event: tk.Event,
        frame: ttk.Frame,
        controls: ttk.LabelFrame,
        assets: ttk.LabelFrame,
    ) -> None:
        try:
            desired_y = int(event.y_root) - frame.winfo_rooty()
            top_origin = min(controls.winfo_y(), assets.winfo_y())
            available = max(420, frame.winfo_height())
        except tk.TclError:
            return
        height = max(165, min(available - 250, desired_y - top_origin))
        self._set_test_top_height_v60(frame, controls, assets, height)

    def _set_test_top_height_v60(
        self,
        frame: ttk.Frame,
        controls: ttk.LabelFrame,
        assets: ttk.LabelFrame,
        height: int,
    ) -> None:
        self._celdra_test_top_height_v60 = max(165, int(height))
        for widget in (controls, assets):
            try:
                widget.grid_propagate(False)
                widget.configure(height=self._celdra_test_top_height_v60)
            except tk.TclError:
                pass
        frame.rowconfigure(1, minsize=self._celdra_test_top_height_v60)

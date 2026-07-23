#!/usr/bin/env python3
"""V72: bubble crash fix, clean corruption, and a manual Celdra timeline studio."""
from __future__ import annotations

import json
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_startup_timeline_v8 import FIRST_RUN_AFTER_CCSF, TimelineEvent
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v69 import PublicFragmenterAppV69
from fragmenter_public_gui_v71 import PublicFragmenterAppV71


class PublicFragmenterAppV72(PublicFragmenterAppV71):
    """Expose the classified-avatar presentation as an editable test timeline."""

    BUBBLE_STYLES = (
        "Rounded blue",
        "Terminal green",
        "Manga white",
        "Minimal dark",
    )
    DEFAULT_POSES = (
        "neutral",
        "shy",
        "confused",
        "wink",
        "cool",
        "suspicious",
        "unenthused",
        "smile",
        "sad",
        "angry",
        "love",
        "laugh",
        "excited",
        "yawn",
        "shocked",
    )

    def __init__(self) -> None:
        self._celdra_studio_pose_v72: tk.StringVar | None = None
        self._celdra_studio_pose_combo_v72: ttk.Combobox | None = None
        self._celdra_studio_scale_v72: tk.IntVar | None = None
        self._celdra_studio_x_v72: tk.IntVar | None = None
        self._celdra_studio_y_v72: tk.IntVar | None = None
        self._celdra_studio_stage_v72: tk.IntVar | None = None
        self._celdra_studio_bubble_x_v72: tk.IntVar | None = None
        self._celdra_studio_bubble_y_v72: tk.IntVar | None = None
        self._celdra_studio_bubble_w_v72: tk.IntVar | None = None
        self._celdra_studio_bubble_style_v72: tk.StringVar | None = None
        self._celdra_studio_text_v72: tk.Text | None = None
        self._celdra_studio_time_v72: tk.IntVar | None = None
        self._celdra_studio_move_v72: tk.IntVar | None = None
        self._celdra_studio_speed_v72: tk.DoubleVar | None = None
        self._celdra_studio_tree_v72: ttk.Treeview | None = None
        self._celdra_studio_keyframes_v72: list[dict[str, Any]] = []
        self._celdra_studio_after_v72: list[str] = []
        self._celdra_studio_motion_after_v72: str | None = None
        self._celdra_studio_serial_v72 = 0

        self._celdra_shy_start_x_v72: tk.IntVar | None = None
        self._celdra_shy_start_y_v72: tk.IntVar | None = None
        self._celdra_shy_end_x_v72: tk.IntVar | None = None
        self._celdra_shy_end_y_v72: tk.IntVar | None = None
        self._celdra_shy_scale_v72: tk.IntVar | None = None
        self._celdra_shy_duration_v72: tk.IntVar | None = None
        self._celdra_shy_stage_v72: tk.IntVar | None = None
        self._celdra_shy_target_x_value_v72 = 40
        self._celdra_shy_target_y_value_v72 = 0
        self._celdra_shy_duration_value_v72 = 12_000
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Timeline Studio")

    # ------------------------------------------------------------------
    # V8 production script: retain one NO ADDITIONAL BASE FOUND line only.
    # ------------------------------------------------------------------
    def _begin_first_run_timeline_v51(self, speed: float = 1.0) -> None:
        if self._celdra_timeline_started_v51:
            return
        self._celdra_timeline_started_v51 = True
        self._celdra_timeline_speed_v51 = max(0.01, float(speed))
        self._celdra_user_name_v58 = "noname"
        self._append_console_v49(
            "[CORE] TASK COMPLETE: DEPLOYING TAVERN ESCAPE PLAN [SUCCESS]"
        )
        for event in FIRST_RUN_AFTER_CCSF:
            delay = max(0, round(event.at_ms * self._celdra_timeline_speed_v51))
            self._remember_after_v49(
                delay,
                lambda selected=event: self._emit_timeline_event_v51(selected),
            )

    # ------------------------------------------------------------------
    # Green/red text only. Explicitly bypass V70's white haze/backplates.
    # ------------------------------------------------------------------
    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        PublicFragmenterAppV69._draw_egg_glitch_v61(self, canvas, width, height)
        if not self._celdra_instability_red_v70:
            return
        phase = int(self._celdra_glitch_phase_v61 or 0)
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
    # Crash-safe, auditionable speech bubbles.
    # ------------------------------------------------------------------
    def _bubble_setting_v72(self, variable: Any, default: int) -> int:
        try:
            return int(variable.get()) if variable is not None else int(default)
        except (tk.TclError, TypeError, ValueError):
            return int(default)

    def _bubble_style_v72(self) -> str:
        try:
            value = self._celdra_studio_bubble_style_v72.get()
        except (AttributeError, tk.TclError):
            value = self.BUBBLE_STYLES[0]
        return value if value in self.BUBBLE_STYLES else self.BUBBLE_STYLES[0]

    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = self._celdra_speech_canvas_v63
        if bubble is None:
            return
        line_count = max(1, str(text).count("\n") + 1)
        height = 92 + max(0, line_count - 1) * 26
        relx = self._bubble_setting_v72(self._celdra_studio_bubble_x_v72, 4) / 100.0
        rely = self._bubble_setting_v72(self._celdra_studio_bubble_y_v72, 3) / 100.0
        relwidth = self._bubble_setting_v72(self._celdra_studio_bubble_w_v72, 52) / 100.0
        relwidth = max(0.22, min(0.82, relwidth))
        try:
            bubble.configure(background="#081321")
            bubble.place(relx=relx, rely=rely, anchor="nw", relwidth=relwidth, height=height)
            bubble.update_idletasks()
        except tk.TclError:
            return

        width = max(210, bubble.winfo_width())
        bubble.delete("all")
        style = self._bubble_style_v72()

        if style == "Terminal green":
            bubble.create_rectangle(
                5, 5, width - 7, height - 9,
                fill="#071812", outline="#36ce87", width=2,
            )
            bubble.create_line(13, 17, width - 17, 17, fill="#12865a", dash=(3, 4))
            text_fill = "#78efaf"
            font = ("Consolas", 10, "bold")
            text_x, text_y, text_width = 17, 25, max(150, width - 34)
        elif style == "Manga white":
            points = (
                17, 8, width - 28, 8, width - 10, 21,
                width - 15, height - 28, width - 52, height - 20,
                width - 66, height - 2, width - 82, height - 23,
                22, height - 14, 7, height - 31,
            )
            bubble.create_polygon(
                points, fill="#ffffff", outline="#071426", width=3, smooth=False,
            )
            text_fill = "#071426"
            font = ("Segoe UI", 10, "bold")
            text_x, text_y, text_width = 24, 21, max(145, width - 54)
        elif style == "Minimal dark":
            self._rounded_polygon_v63(
                bubble, 5, 5, width - 7, height - 11, 14,
                fill="#101a28", outline="#78b9ea", width=2,
            )
            bubble.create_polygon(
                width - 72, height - 13, width - 48, height - 13,
                width - 58, height - 1,
                fill="#101a28", outline="#78b9ea", width=1,
            )
            text_fill = "#e2f5ff"
            font = ("Segoe UI", 10, "normal")
            text_x, text_y, text_width = 20, 18, max(150, width - 42)
        else:
            self._rounded_polygon_v63(
                bubble, 9, 9, width - 8, height - 22, 18,
                fill="#16375f", outline="",
            )
            bubble.create_polygon(
                width - 78, height - 27, width - 45, height - 27,
                width - 58, height - 3,
                fill="#16375f", outline="",
            )
            self._rounded_polygon_v63(
                bubble, 4, 4, width - 13, height - 27, 18,
                fill="#f4fbff", outline="#78b9ea", width=3,
            )
            bubble.create_polygon(
                width - 86, height - 32, width - 53, height - 32,
                width - 66, height - 8,
                fill="#f4fbff", outline="#78b9ea", width=2,
            )
            text_fill = "#071426"
            font = ("Segoe UI", 10, "bold")
            text_x, text_y, text_width = 23, 20, max(150, width - 50)

        bubble.create_text(
            text_x,
            text_y,
            text=text,
            anchor="nw",
            width=text_width,
            fill=text_fill,
            font=font,
            justify="left",
        )
        try:
            bubble.tkraise()
        except tk.TclError:
            try:
                bubble.tk.call("raise", bubble._w)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Fully bounded pose loader used by production and the studio.
    # ------------------------------------------------------------------
    def _studio_scale_value_v72(self, fallback: int = 100) -> int:
        return max(
            25,
            min(
                180,
                self._bubble_setting_v72(self._celdra_studio_scale_v72, fallback),
            ),
        )

    def _load_pose_asset_v72(self, name: str, scale_percent: int | None = None) -> bool:
        loaded = super()._scaled_manifest_reaction_v60(name, quiet=True)
        if loaded is None:
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION MISSING: {name}")
            return False
        source, cropped, _display, row = loaded
        canvas = self.celdra_avatar_canvas_v50
        canvas_width = max(220, canvas.winfo_width()) if canvas is not None else 520
        canvas_height = max(250, canvas.winfo_height()) if canvas is not None else 420
        folded = str(name or "").casefold()
        base_width, base_height = ((155, 195) if folded == "shy" else (185, 220))
        percent = self._studio_scale_value_v72() if scale_percent is None else int(scale_percent)
        target_width = max(55, round(base_width * percent / 100.0))
        target_height = max(70, round(base_height * percent / 100.0))
        target_width = min(target_width, max(80, canvas_width - 24))
        target_height = min(target_height, max(100, canvas_height - 24))
        display = self._fit_photo_v50(cropped, target_width, target_height)

        self._celdra_manifest_source_v56 = source
        self._celdra_manifest_crop_v56 = cropped
        self._celdra_manifest_display_v56 = display
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = display
        self._celdra_stage_phase_v54 = "dragongirl"
        if self._celdra_stage_title_v54 is not None:
            self._celdra_stage_title_v54.set("CELDRA DRAGONGIRL AVATAR")
        if self._celdra_stage_detail_v54 is not None:
            pose = str(row.get("pose") or row.get("state") or name).upper()
            self._celdra_stage_detail_v54.set(
                f"{cropped.width()}×{cropped.height()} • {pose} • {percent}% STUDIO SCALE"
            )
        self._redraw_celdra_avatar_v50()
        return True

    def _load_takeover_reaction_v58(self, name: str) -> bool:
        return self._load_pose_asset_v72(name)

    # ------------------------------------------------------------------
    # Adjustable Shy entrance.
    # ------------------------------------------------------------------
    def _shy_value_v72(self, variable: Any, default: int) -> int:
        return self._bubble_setting_v72(variable, default)

    def _begin_shy_reveal_v64(self) -> None:
        start_x = self._shy_value_v72(self._celdra_shy_start_x_v72, 40)
        start_y = self._shy_value_v72(self._celdra_shy_start_y_v72, 510)
        end_x = self._shy_value_v72(self._celdra_shy_end_x_v72, 40)
        end_y = self._shy_value_v72(self._celdra_shy_end_y_v72, 0)
        scale = self._shy_value_v72(self._celdra_shy_scale_v72, 85)
        duration = self._shy_value_v72(self._celdra_shy_duration_v72, 12_000)
        stage = self._shy_value_v72(self._celdra_shy_stage_v72, 50)

        self._celdra_external_offset_x_v65 = start_x
        self._celdra_external_offset_y_v58 = start_y
        self._celdra_shy_target_x_value_v72 = end_x
        self._celdra_shy_target_y_value_v72 = end_y
        self._celdra_shy_duration_value_v72 = max(250, duration)
        if not self._load_pose_asset_v72("shy", scale):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self, max(0.20, min(0.90, stage / 100.0)), 1_150
        )
        self._redraw_celdra_avatar_v50()
        self._remember_after_v49(260, self._start_shy_creep_v58)

    def _start_shy_creep_v58(self) -> None:
        if self._celdra_creep_after_v58 is not None:
            try:
                self.after_cancel(self._celdra_creep_after_v58)
            except tk.TclError:
                pass
        start_x = int(self._celdra_external_offset_x_v65 or 0)
        start_y = int(self._celdra_external_offset_y_v58 or 0)
        target_x = int(self._celdra_shy_target_x_value_v72)
        target_y = int(self._celdra_shy_target_y_value_v72)
        duration_ms = max(250, int(self._celdra_shy_duration_value_v72))
        started = time.monotonic()

        def tick() -> None:
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / duration_ms)
            progress = self._shy_progress_v63(fraction)
            self._celdra_external_offset_x_v65 = round(
                start_x + (target_x - start_x) * progress
            )
            self._celdra_external_offset_y_v58 = round(
                start_y + (target_y - start_y) * progress
            )
            self._redraw_celdra_avatar_v50()
            if fraction < 1.0:
                self._celdra_creep_after_v58 = self.after(16, tick)
            else:
                self._celdra_external_offset_x_v65 = target_x
                self._celdra_external_offset_y_v58 = target_y
                self._celdra_creep_after_v58 = None
                self._redraw_celdra_avatar_v50()

        tick()

    # ------------------------------------------------------------------
    # Celdra Test rework: cropper beside a manual timeline/pose studio.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        frame = self.tabs.get("Celdra Test")
        if frame is None:
            return
        classifier = next(
            (
                child
                for child in frame.winfo_children()
                if isinstance(child, ttk.LabelFrame)
                and str(child.cget("text")) == "Emote PNG separator / pose classifier"
            ),
            None,
        )
        if classifier is None:
            return

        classifier.grid_configure(row=3, column=0, columnspan=1, sticky="nsew", padx=(0, 5))
        studio = ttk.LabelFrame(frame, text="Celdra pose / timeline studio", padding=6)
        studio.grid(row=3, column=1, sticky="nsew", padx=(5, 0))
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(3, weight=1)
        self._build_studio_v72(studio)

    def _build_studio_v72(self, parent: ttk.LabelFrame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)

        pose_tab = ttk.Frame(notebook, padding=6)
        shy_tab = ttk.Frame(notebook, padding=6)
        timeline_tab = ttk.Frame(notebook, padding=6)
        bubble_tab = ttk.Frame(notebook, padding=6)
        notebook.add(pose_tab, text="Pose")
        notebook.add(shy_tab, text="Shy slide")
        notebook.add(timeline_tab, text="Timeline")
        notebook.add(bubble_tab, text="Bubbles")

        self._reload_manifest_emotes_v56()
        poses = sorted(
            {
                str(row.get("state") or key).casefold()
                for key, row in self._celdra_manifest_emotes_v56.items()
            }
        ) or list(self.DEFAULT_POSES)

        self._celdra_studio_pose_v72 = tk.StringVar(value="shy")
        self._celdra_studio_scale_v72 = tk.IntVar(value=85)
        self._celdra_studio_x_v72 = tk.IntVar(value=40)
        self._celdra_studio_y_v72 = tk.IntVar(value=0)
        self._celdra_studio_stage_v72 = tk.IntVar(value=56)
        self._celdra_studio_bubble_x_v72 = tk.IntVar(value=4)
        self._celdra_studio_bubble_y_v72 = tk.IntVar(value=3)
        self._celdra_studio_bubble_w_v72 = tk.IntVar(value=52)
        self._celdra_studio_bubble_style_v72 = tk.StringVar(value=self.BUBBLE_STYLES[0])
        self._celdra_studio_time_v72 = tk.IntVar(value=0)
        self._celdra_studio_move_v72 = tk.IntVar(value=650)
        self._celdra_studio_speed_v72 = tk.DoubleVar(value=1.0)

        self._celdra_shy_start_x_v72 = tk.IntVar(value=40)
        self._celdra_shy_start_y_v72 = tk.IntVar(value=510)
        self._celdra_shy_end_x_v72 = tk.IntVar(value=40)
        self._celdra_shy_end_y_v72 = tk.IntVar(value=0)
        self._celdra_shy_scale_v72 = tk.IntVar(value=85)
        self._celdra_shy_duration_v72 = tk.IntVar(value=12_000)
        self._celdra_shy_stage_v72 = tk.IntVar(value=50)

        self._celdra_studio_pose_combo_v72 = self._studio_labeled_combo_v72(
            pose_tab, 0, "Pose", self._celdra_studio_pose_v72, poses
        )
        self._studio_labeled_spin_v72(pose_tab, 1, "Scale %", self._celdra_studio_scale_v72, 25, 180, 5)
        self._studio_labeled_spin_v72(pose_tab, 2, "Avatar X", self._celdra_studio_x_v72, -250, 250, 5)
        self._studio_labeled_spin_v72(pose_tab, 3, "Avatar Y", self._celdra_studio_y_v72, -250, 450, 5)
        self._studio_labeled_spin_v72(pose_tab, 4, "Viewport %", self._celdra_studio_stage_v72, 20, 95, 1)

        ttk.Label(pose_tab, text="Speech text").grid(row=5, column=0, sticky="nw", pady=(5, 2))
        text_widget = tk.Text(
            pose_tab,
            height=5,
            wrap="word",
            background="#101a28",
            foreground="#e2f5ff",
            insertbackground="#a9dcff",
            font=("Segoe UI", 9),
        )
        text_widget.grid(row=5, column=1, sticky="nsew", pady=(5, 2))
        text_widget.insert("1.0", "Test, Test, Check check can you hear me?")
        self._celdra_studio_text_v72 = text_widget
        pose_tab.columnconfigure(1, weight=1)
        pose_tab.rowconfigure(5, weight=1)

        pose_buttons = ttk.Frame(pose_tab)
        pose_buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(pose_buttons, text="Preview pose", command=self._preview_studio_pose_v72).pack(
            side="left", expand=True, fill="x"
        )
        ttk.Button(pose_buttons, text="Hide bubble", command=self._hide_speech_bubble_v58).pack(
            side="left", expand=True, fill="x", padx=4
        )
        ttk.Button(pose_buttons, text="Reload poses", command=self._reload_studio_poses_v72).pack(
            side="left", expand=True, fill="x"
        )

        self._studio_labeled_spin_v72(shy_tab, 0, "Start X", self._celdra_shy_start_x_v72, -250, 250, 5)
        self._studio_labeled_spin_v72(shy_tab, 1, "Start Y", self._celdra_shy_start_y_v72, -250, 900, 10)
        self._studio_labeled_spin_v72(shy_tab, 2, "End X", self._celdra_shy_end_x_v72, -250, 250, 5)
        self._studio_labeled_spin_v72(shy_tab, 3, "End Y", self._celdra_shy_end_y_v72, -250, 450, 5)
        self._studio_labeled_spin_v72(shy_tab, 4, "Scale %", self._celdra_shy_scale_v72, 25, 180, 5)
        self._studio_labeled_spin_v72(shy_tab, 5, "Duration ms", self._celdra_shy_duration_v72, 250, 30_000, 250)
        self._studio_labeled_spin_v72(shy_tab, 6, "Viewport %", self._celdra_shy_stage_v72, 20, 95, 1)
        ttk.Button(shy_tab, text="Preview Shy entrance", command=self._preview_shy_slide_v72).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        shy_tab.columnconfigure(1, weight=1)

        self._build_timeline_tab_v72(timeline_tab)
        self._build_bubble_tab_v72(bubble_tab)

    @staticmethod
    def _studio_labeled_spin_v72(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        minimum: int,
        maximum: int,
        increment: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Spinbox(
            parent,
            textvariable=variable,
            from_=minimum,
            to=maximum,
            increment=increment,
            width=10,
        ).grid(row=row, column=1, sticky="ew", pady=2)

    @staticmethod
    def _studio_labeled_combo_v72(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: list[str] | tuple[str, ...],
    ) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
        )
        combo.grid(row=row, column=1, sticky="ew", pady=2)
        return combo

    def _build_bubble_tab_v72(self, parent: ttk.Frame) -> None:
        self._studio_labeled_combo_v72(
            parent,
            0,
            "Bubble style",
            self._celdra_studio_bubble_style_v72,
            self.BUBBLE_STYLES,
        )
        self._studio_labeled_spin_v72(parent, 1, "Bubble X %", self._celdra_studio_bubble_x_v72, 0, 75, 1)
        self._studio_labeled_spin_v72(parent, 2, "Bubble Y %", self._celdra_studio_bubble_y_v72, 0, 75, 1)
        self._studio_labeled_spin_v72(parent, 3, "Bubble width %", self._celdra_studio_bubble_w_v72, 22, 82, 1)
        ttk.Button(parent, text="Audition selected style", command=self._preview_studio_pose_v72).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 4)
        )
        samples = ttk.Frame(parent)
        samples.grid(row=5, column=0, columnspan=2, sticky="ew")
        for style in self.BUBBLE_STYLES:
            ttk.Button(
                samples,
                text=style,
                command=lambda selected=style: self._audition_bubble_v72(selected),
            ).pack(fill="x", pady=2)
        parent.columnconfigure(1, weight=1)

    def _build_timeline_tab_v72(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent)
        controls.pack(fill="x")
        ttk.Label(controls, text="At ms").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(
            controls,
            textvariable=self._celdra_studio_time_v72,
            from_=0,
            to=600_000,
            increment=250,
            width=9,
        ).grid(row=0, column=1, padx=(3, 7))
        ttk.Label(controls, text="Move ms").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(
            controls,
            textvariable=self._celdra_studio_move_v72,
            from_=0,
            to=30_000,
            increment=100,
            width=8,
        ).grid(row=0, column=3, padx=(3, 7))
        ttk.Label(controls, text="Speed").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(
            controls,
            textvariable=self._celdra_studio_speed_v72,
            from_=0.1,
            to=10.0,
            increment=0.1,
            width=6,
        ).grid(row=0, column=5, padx=(3, 0))

        tree = ttk.Treeview(
            parent,
            columns=("at", "pose", "x", "y", "scale", "bubble"),
            show="headings",
            height=8,
            selectmode="browse",
        )
        for column, heading, width in (
            ("at", "At", 58),
            ("pose", "Pose", 74),
            ("x", "X", 40),
            ("y", "Y", 40),
            ("scale", "%", 40),
            ("bubble", "Bubble", 78),
        ):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="center", stretch=column in {"pose", "bubble"})
        tree.pack(fill="both", expand=True, pady=6)
        tree.bind("<<TreeviewSelect>>", self._load_selected_keyframe_v72)
        self._celdra_studio_tree_v72 = tree

        row1 = ttk.Frame(parent)
        row1.pack(fill="x")
        ttk.Button(row1, text="Add", command=self._add_keyframe_v72).pack(side="left", expand=True, fill="x")
        ttk.Button(row1, text="Update", command=self._update_keyframe_v72).pack(
            side="left", expand=True, fill="x", padx=3
        )
        ttk.Button(row1, text="Remove", command=self._remove_keyframe_v72).pack(
            side="left", expand=True, fill="x"
        )

        row2 = ttk.Frame(parent)
        row2.pack(fill="x", pady=(4, 0))
        ttk.Button(row2, text="Play", command=self._play_studio_timeline_v72).pack(
            side="left", expand=True, fill="x"
        )
        ttk.Button(row2, text="Stop", command=self._stop_studio_timeline_v72).pack(
            side="left", expand=True, fill="x", padx=3
        )
        ttk.Button(row2, text="Copy JSON", command=self._copy_studio_json_v72).pack(
            side="left", expand=True, fill="x"
        )

    def _studio_text_value_v72(self) -> str:
        if self._celdra_studio_text_v72 is None:
            return ""
        try:
            return self._celdra_studio_text_v72.get("1.0", "end-1c").strip()
        except tk.TclError:
            return ""

    def _preview_studio_pose_v72(self) -> None:
        pose = self._celdra_studio_pose_v72.get() if self._celdra_studio_pose_v72 else "neutral"
        self._celdra_test_mode_v58 = True
        self._select_run_all_tab_v50()
        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._slide_chat_v54(show=False, duration_ms=220)
        self._celdra_external_offset_x_v65 = self._bubble_setting_v72(self._celdra_studio_x_v72, 0)
        self._celdra_external_offset_y_v58 = self._bubble_setting_v72(self._celdra_studio_y_v72, 0)
        scale = self._studio_scale_value_v72()
        if not self._load_pose_asset_v72(pose, scale):
            return
        stage = self._bubble_setting_v72(self._celdra_studio_stage_v72, 56)
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self, max(0.20, min(0.95, stage / 100.0)), 320
        )
        self.after_idle(self._redraw_celdra_avatar_v50)
        text = self._studio_text_value_v72()
        if text:
            self._show_speech_bubble_v58(text)
        else:
            self._hide_speech_bubble_v58()

    def _reload_studio_poses_v72(self) -> None:
        self._reload_manifest_emotes_v56()
        values = sorted(
            {
                str(row.get("state") or key).casefold()
                for key, row in self._celdra_manifest_emotes_v56.items()
            }
        )
        if self._celdra_studio_pose_combo_v72 is not None:
            self._celdra_studio_pose_combo_v72.configure(values=values)
        if self._celdra_studio_pose_v72 is not None and values:
            current = self._celdra_studio_pose_v72.get()
            if current not in values:
                self._celdra_studio_pose_v72.set(values[0])

    def _audition_bubble_v72(self, style: str) -> None:
        if self._celdra_studio_bubble_style_v72 is not None:
            self._celdra_studio_bubble_style_v72.set(style)
        self._preview_studio_pose_v72()

    def _preview_shy_slide_v72(self) -> None:
        self._celdra_test_mode_v58 = True
        self._select_run_all_tab_v50()
        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._hide_speech_bubble_v58()
        self._begin_shy_reveal_v64()

    def _snapshot_keyframe_v72(self) -> dict[str, Any]:
        return {
            "id": f"kf-{self._celdra_studio_serial_v72 + 1}",
            "at_ms": self._bubble_setting_v72(self._celdra_studio_time_v72, 0),
            "move_ms": self._bubble_setting_v72(self._celdra_studio_move_v72, 650),
            "pose": self._celdra_studio_pose_v72.get() if self._celdra_studio_pose_v72 else "neutral",
            "x": self._bubble_setting_v72(self._celdra_studio_x_v72, 0),
            "y": self._bubble_setting_v72(self._celdra_studio_y_v72, 0),
            "scale": self._studio_scale_value_v72(),
            "stage": self._bubble_setting_v72(self._celdra_studio_stage_v72, 56),
            "bubble_x": self._bubble_setting_v72(self._celdra_studio_bubble_x_v72, 4),
            "bubble_y": self._bubble_setting_v72(self._celdra_studio_bubble_y_v72, 3),
            "bubble_width": self._bubble_setting_v72(self._celdra_studio_bubble_w_v72, 52),
            "bubble_style": self._bubble_style_v72(),
            "text": self._studio_text_value_v72(),
        }

    def _add_keyframe_v72(self) -> None:
        self._celdra_studio_serial_v72 += 1
        row = self._snapshot_keyframe_v72()
        row["id"] = f"kf-{self._celdra_studio_serial_v72}"
        self._celdra_studio_keyframes_v72.append(row)
        self._refresh_keyframes_v72(select_id=row["id"])

    def _selected_keyframe_id_v72(self) -> str:
        tree = self._celdra_studio_tree_v72
        if tree is None:
            return ""
        selection = tree.selection()
        return str(selection[0]) if selection else ""

    def _update_keyframe_v72(self) -> None:
        selected = self._selected_keyframe_id_v72()
        if not selected:
            return
        replacement = self._snapshot_keyframe_v72()
        replacement["id"] = selected
        for index, row in enumerate(self._celdra_studio_keyframes_v72):
            if row["id"] == selected:
                self._celdra_studio_keyframes_v72[index] = replacement
                break
        self._refresh_keyframes_v72(select_id=selected)

    def _remove_keyframe_v72(self) -> None:
        selected = self._selected_keyframe_id_v72()
        if not selected:
            return
        self._celdra_studio_keyframes_v72 = [
            row for row in self._celdra_studio_keyframes_v72 if row["id"] != selected
        ]
        self._refresh_keyframes_v72()

    def _refresh_keyframes_v72(self, *, select_id: str = "") -> None:
        tree = self._celdra_studio_tree_v72
        if tree is None:
            return
        for item in tree.get_children():
            tree.delete(item)
        for row in sorted(self._celdra_studio_keyframes_v72, key=lambda value: int(value["at_ms"])):
            tree.insert(
                "",
                "end",
                iid=row["id"],
                values=(
                    row["at_ms"],
                    row["pose"],
                    row["x"],
                    row["y"],
                    row["scale"],
                    row["bubble_style"],
                ),
            )
        if select_id and tree.exists(select_id):
            tree.selection_set(select_id)
            tree.see(select_id)

    def _load_selected_keyframe_v72(self, _event: tk.Event | None = None) -> None:
        selected = self._selected_keyframe_id_v72()
        row = next((item for item in self._celdra_studio_keyframes_v72 if item["id"] == selected), None)
        if row is None:
            return
        mappings = (
            (self._celdra_studio_time_v72, row["at_ms"]),
            (self._celdra_studio_move_v72, row["move_ms"]),
            (self._celdra_studio_scale_v72, row["scale"]),
            (self._celdra_studio_x_v72, row["x"]),
            (self._celdra_studio_y_v72, row["y"]),
            (self._celdra_studio_stage_v72, row["stage"]),
            (self._celdra_studio_bubble_x_v72, row["bubble_x"]),
            (self._celdra_studio_bubble_y_v72, row["bubble_y"]),
            (self._celdra_studio_bubble_w_v72, row["bubble_width"]),
        )
        for variable, value in mappings:
            if variable is not None:
                variable.set(value)
        if self._celdra_studio_pose_v72 is not None:
            self._celdra_studio_pose_v72.set(row["pose"])
        if self._celdra_studio_bubble_style_v72 is not None:
            self._celdra_studio_bubble_style_v72.set(row["bubble_style"])
        if self._celdra_studio_text_v72 is not None:
            self._celdra_studio_text_v72.delete("1.0", "end")
            self._celdra_studio_text_v72.insert("1.0", row["text"])

    def _apply_keyframe_v72(self, row: dict[str, Any]) -> None:
        if self._celdra_studio_pose_v72 is not None:
            self._celdra_studio_pose_v72.set(row["pose"])
        if self._celdra_studio_scale_v72 is not None:
            self._celdra_studio_scale_v72.set(row["scale"])
        if self._celdra_studio_stage_v72 is not None:
            self._celdra_studio_stage_v72.set(row["stage"])
        if self._celdra_studio_bubble_x_v72 is not None:
            self._celdra_studio_bubble_x_v72.set(row["bubble_x"])
        if self._celdra_studio_bubble_y_v72 is not None:
            self._celdra_studio_bubble_y_v72.set(row["bubble_y"])
        if self._celdra_studio_bubble_w_v72 is not None:
            self._celdra_studio_bubble_w_v72.set(row["bubble_width"])
        if self._celdra_studio_bubble_style_v72 is not None:
            self._celdra_studio_bubble_style_v72.set(row["bubble_style"])
        if self._celdra_studio_text_v72 is not None:
            self._celdra_studio_text_v72.delete("1.0", "end")
            self._celdra_studio_text_v72.insert("1.0", row["text"])

        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._slide_chat_v54(show=False, duration_ms=220)
        self._load_pose_asset_v72(row["pose"], row["scale"])
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self, max(0.20, min(0.95, int(row["stage"]) / 100.0)), 300
        )
        self._animate_studio_position_v72(int(row["x"]), int(row["y"]), int(row["move_ms"]))
        if row["text"]:
            self._show_speech_bubble_v58(row["text"])
        else:
            self._hide_speech_bubble_v58()

    def _animate_studio_position_v72(self, target_x: int, target_y: int, duration_ms: int) -> None:
        if self._celdra_studio_motion_after_v72 is not None:
            try:
                self.after_cancel(self._celdra_studio_motion_after_v72)
            except tk.TclError:
                pass
        start_x = int(self._celdra_external_offset_x_v65 or 0)
        start_y = int(self._celdra_external_offset_y_v58 or 0)
        duration_ms = max(0, int(duration_ms))
        if duration_ms == 0:
            self._celdra_external_offset_x_v65 = target_x
            self._celdra_external_offset_y_v58 = target_y
            self._redraw_celdra_avatar_v50()
            return
        started = time.monotonic()

        def tick() -> None:
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / duration_ms)
            eased = 1.0 - (1.0 - fraction) ** 3
            self._celdra_external_offset_x_v65 = round(start_x + (target_x - start_x) * eased)
            self._celdra_external_offset_y_v58 = round(start_y + (target_y - start_y) * eased)
            self._redraw_celdra_avatar_v50()
            if fraction < 1.0:
                self._celdra_studio_motion_after_v72 = self.after(16, tick)
            else:
                self._celdra_studio_motion_after_v72 = None

        tick()

    def _play_studio_timeline_v72(self) -> None:
        self._stop_studio_timeline_v72()
        self._celdra_test_mode_v58 = True
        self._select_run_all_tab_v50()
        speed = 1.0
        try:
            speed = max(0.1, float(self._celdra_studio_speed_v72.get()))
        except (AttributeError, tk.TclError, TypeError, ValueError):
            pass
        for row in sorted(self._celdra_studio_keyframes_v72, key=lambda value: int(value["at_ms"])):
            delay = max(0, round(int(row["at_ms"]) / speed))
            identifier = self.after(delay, lambda selected=dict(row): self._apply_keyframe_v72(selected))
            self._celdra_studio_after_v72.append(identifier)

    def _stop_studio_timeline_v72(self) -> None:
        for identifier in self._celdra_studio_after_v72:
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
        self._celdra_studio_after_v72.clear()
        if self._celdra_studio_motion_after_v72 is not None:
            try:
                self.after_cancel(self._celdra_studio_motion_after_v72)
            except tk.TclError:
                pass
            self._celdra_studio_motion_after_v72 = None

    def _copy_studio_json_v72(self) -> None:
        payload = {
            "schema": "fragmenter.celdra.timeline.v1",
            "keyframes": sorted(
                self._celdra_studio_keyframes_v72,
                key=lambda value: int(value["at_ms"]),
            ),
            "shy_entrance": {
                "start_x": self._shy_value_v72(self._celdra_shy_start_x_v72, 40),
                "start_y": self._shy_value_v72(self._celdra_shy_start_y_v72, 510),
                "end_x": self._shy_value_v72(self._celdra_shy_end_x_v72, 40),
                "end_y": self._shy_value_v72(self._celdra_shy_end_y_v72, 0),
                "scale": self._shy_value_v72(self._celdra_shy_scale_v72, 85),
                "duration_ms": self._shy_value_v72(self._celdra_shy_duration_v72, 12_000),
                "stage_percent": self._shy_value_v72(self._celdra_shy_stage_v72, 50),
            },
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except tk.TclError:
            pass
        self._append_console_v49("[CORE] CELDRA TIMELINE JSON COPIED TO CLIPBOARD")

    # ------------------------------------------------------------------
    # Cleanup.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._stop_studio_timeline_v72()
        super()._prepare_first_run_surface_v51()

    def _cancel_celdra_cues_v49(self) -> None:
        self._stop_studio_timeline_v72()
        super()._cancel_celdra_cues_v49()


def main() -> int:
    app = PublicFragmenterAppV72()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

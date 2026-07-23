#!/usr/bin/env python3
"""V50: four-way resizable RUN ALL dashboard and bundled Celdra asset lab."""
from __future__ import annotations

import json
import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Iterable

from celdra_assets_v1 import asset_inventory, crop_manifest_entry
from celdra_pixel_pet_v1 import HATCH_SEQUENCE, PALETTE, STATE_FRAMES, PixelFrame
from celdra_presentation_v1 import (
    ALT_F4_SECOND,
    FAILURE_CUES,
    FIRST_DONE_CUES,
    FIRST_SCAN_CUES,
    RETURNING_DONE_CUES,
    RETURNING_START_CUES,
    STAGE_CUES,
    CeldraCue,
)
from fragmenter_public_gui_v49 import PublicFragmenterAppV49


class PublicFragmenterAppV50(PublicFragmenterAppV49):
    """Keep every operational and Celdra surface visible and independently resizable."""

    def __init__(self) -> None:
        self.run_top_split_v50: ttk.Panedwindow | None = None
        self.run_bottom_split_v50: ttk.Panedwindow | None = None
        self.celdra_visual_split_v50: ttk.Panedwindow | None = None
        self.celdra_comms_split_v50: ttk.Panedwindow | None = None
        self.celdra_avatar_canvas_v50: tk.Canvas | None = None
        self.celdra_layout_user_locked_v50 = False
        self.celdra_asset_root_v50 = Path(__file__).resolve().parents[1] / "assets" / "celdra"
        self.celdra_asset_inventory_v50: dict[str, Any] = {}
        self.celdra_external_frames_v50: dict[str, list[tk.PhotoImage]] = {}
        self.celdra_pixel_sequence_v50: tuple[PixelFrame, ...] = ()
        self.celdra_pixel_index_v50 = 0
        self.celdra_current_pixel_v50: PixelFrame | None = None
        self.celdra_current_external_v50: tk.PhotoImage | None = None
        self.celdra_test_asset_rows_v50: dict[str, dict[str, Any]] = {}
        self.celdra_test_preview_image_v50: tk.PhotoImage | None = None
        self.celdra_alt_f4_popup_v50: tk.Toplevel | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Four-Pane Test Lab")
        self._install_celdra_test_tab_v50()

    # ------------------------------------------------------------------
    # RUN ALL: top-left plan, top-right log, bottom-left stages, bottom-right Celdra.
    # ------------------------------------------------------------------
    def _build_run_all(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.run_button = ttk.Button(
            toolbar,
            text="RUN ALL",
            command=self._run_all,
            style="Accent.TButton",
        )
        self.run_button.pack(side="left", padx=(0, 6))
        self.cancel_button = ttk.Button(
            toolbar,
            text="Cancel",
            command=self._cancel_task,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Refresh Plan", command=self._refresh_run_plan).pack(
            side="left"
        )
        ttk.Button(
            toolbar,
            text="Celdra Test",
            command=self._open_celdra_test_tab_v50,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            toolbar,
            text="Reset Pane Layout",
            command=self._reset_celdra_layout_v50,
        ).pack(side="left", padx=(6, 0))
        ttk.Label(
            toolbar,
            text="Real progress and Celdra presentation progress remain separate.",
        ).pack(side="right")

        overall = ttk.Frame(parent)
        overall.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        overall.columnconfigure(1, weight=1)
        self.overall_progress_label = tk.StringVar(value="Overall progress: idle")
        ttk.Label(overall, textvariable=self.overall_progress_label).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.overall_progress = ttk.Progressbar(
            overall,
            maximum=100.0,
            mode="determinate",
            style="Accent.Horizontal.TProgressbar",
        )
        self.overall_progress.grid(row=0, column=1, sticky="ew")

        outer = ttk.Panedwindow(parent, orient="vertical")
        outer.grid(row=2, column=0, sticky="nsew")
        self.run_paned = outer
        outer.bind("<ButtonRelease-1>", self._remember_user_layout_v50, add="+")

        top = ttk.Frame(outer)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(0, weight=1)
        top_split = ttk.Panedwindow(top, orient="horizontal")
        top_split.grid(row=0, column=0, sticky="nsew")
        top_split.bind("<ButtonRelease-1>", self._remember_user_layout_v50, add="+")
        self.run_top_split_v50 = top_split

        tree_frame = ttk.LabelFrame(top_split, text="Pipeline plan", padding=4)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.run_tree = ttk.Treeview(
            tree_frame,
            columns=("status", "description"),
            show="tree headings",
        )
        self.run_tree.heading("#0", text="Stage")
        self.run_tree.heading("status", text="Status")
        self.run_tree.heading("description", text="Description")
        self.run_tree.column("#0", width=205, stretch=False)
        self.run_tree.column("status", width=90, stretch=False)
        self.run_tree.column("description", width=520, stretch=True)
        tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.run_tree.yview)
        self.run_tree.configure(yscrollcommand=tree_y.set)
        self.run_tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        top_split.add(tree_frame, weight=3)

        log_frame = ttk.LabelFrame(top_split, text="Pipeline console", padding=4)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.run_log = tk.Text(log_frame, wrap="word")
        log_y = ttk.Scrollbar(log_frame, orient="vertical", command=self.run_log.yview)
        self.run_log.configure(yscrollcommand=log_y.set)
        self.run_log.grid(row=0, column=0, sticky="nsew")
        log_y.grid(row=0, column=1, sticky="ns")
        top_split.add(log_frame, weight=2)

        bottom = ttk.Frame(outer)
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)
        bottom_split = ttk.Panedwindow(bottom, orient="horizontal")
        bottom_split.grid(row=0, column=0, sticky="nsew")
        bottom_split.bind("<ButtonRelease-1>", self._remember_user_layout_v50, add="+")
        self.run_bottom_split_v50 = bottom_split

        progress_box = ttk.LabelFrame(
            bottom_split,
            text="Stage progress / direct run",
            padding=5,
        )
        progress_box.columnconfigure(1, weight=1)
        self.stage_progress_frame = progress_box
        bottom_split.add(progress_box, weight=1)

        celdra = ttk.LabelFrame(
            bottom_split,
            text="Celdra — console, dialogue, and avatar",
            padding=4,
        )
        celdra.columnconfigure(0, weight=1)
        celdra.rowconfigure(1, weight=1)
        self._celdra_host_v49 = celdra
        self._run_bottom_v49 = bottom
        bottom_split.add(celdra, weight=1)

        header = ttk.Frame(celdra)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="All Celdra surfaces remain visible. Drag any divider to resize.",
        ).grid(row=0, column=0, sticky="w")
        self._celdra_chat_button_v49 = ttk.Button(
            header,
            text="Focus Dialogue",
            command=lambda: self._show_celdra_chat_v49(force=True),
        )
        self._celdra_chat_button_v49.grid(row=0, column=1, padx=(5, 0))
        self._celdra_expand_button_v49 = ttk.Button(
            header,
            text="Expand Celdra",
            command=lambda: self._set_celdra_expanded_v49(
                not self._celdra_expanded_v49,
                force=True,
            ),
        )
        self._celdra_expand_button_v49.grid(row=0, column=2, padx=(5, 0))

        visual_split = ttk.Panedwindow(celdra, orient="horizontal")
        visual_split.grid(row=1, column=0, sticky="nsew")
        visual_split.bind("<ButtonRelease-1>", self._remember_user_layout_v50, add="+")
        self.celdra_visual_split_v50 = visual_split

        avatar = ttk.Frame(visual_split, padding=4)
        avatar.columnconfigure(0, weight=1)
        avatar.rowconfigure(0, weight=1)
        canvas = tk.Canvas(
            avatar,
            width=280,
            height=250,
            background="#10151d",
            highlightthickness=0,
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.bind("<Configure>", lambda _event: self._redraw_celdra_avatar_v50())
        self.celdra_avatar_canvas_v50 = canvas
        self._celdra_avatar_label_v49 = None

        self._celdra_bubble_v49 = tk.StringVar(value="")
        ttk.Label(
            avatar,
            textvariable=self._celdra_bubble_v49,
            wraplength=300,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 3))
        self._celdra_fake_status_v49 = tk.StringVar(value="[CELDRA] OFFLINE")
        ttk.Label(
            avatar,
            textvariable=self._celdra_fake_status_v49,
            wraplength=300,
        ).grid(row=2, column=0, sticky="ew")
        self._celdra_fake_progress_v49 = ttk.Progressbar(
            avatar,
            maximum=100.0,
            mode="determinate",
            style="Accent.Horizontal.TProgressbar",
        )
        self._celdra_fake_progress_v49.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        visual_split.add(avatar, weight=2)

        comms = ttk.Panedwindow(celdra, orient="vertical")
        comms.bind("<ButtonRelease-1>", self._remember_user_layout_v50, add="+")
        self.celdra_comms_split_v50 = comms

        console_frame = ttk.LabelFrame(comms, text="Celdra system console", padding=3)
        console_frame.columnconfigure(0, weight=1)
        console_frame.rowconfigure(0, weight=1)
        console = tk.Text(
            console_frame,
            wrap="word",
            state="disabled",
            background="#10151d",
            foreground="#b9c8da",
            insertbackground="#b9c8da",
        )
        console_y = ttk.Scrollbar(console_frame, orient="vertical", command=console.yview)
        console.configure(yscrollcommand=console_y.set)
        console.grid(row=0, column=0, sticky="nsew")
        console_y.grid(row=0, column=1, sticky="ns")
        self._celdra_console_v49 = console
        self._celdra_console_v38 = console
        comms.add(console_frame, weight=1)

        chat_frame = ttk.LabelFrame(
            comms,
            text="Celdra dialogue — one-way link",
            padding=3,
        )
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        chat = tk.Text(
            chat_frame,
            wrap="word",
            state="disabled",
            background="#151b24",
            foreground="#d6e3f1",
            insertbackground="#d6e3f1",
        )
        chat_y = ttk.Scrollbar(chat_frame, orient="vertical", command=chat.yview)
        chat.configure(yscrollcommand=chat_y.set)
        chat.grid(row=0, column=0, sticky="nsew")
        chat_y.grid(row=0, column=1, sticky="ns")
        ttk.Label(
            chat_frame,
            text="ONE-WAY LINK — INPUT CHANNEL NOT INSTALLED",
            anchor="center",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        self._celdra_chat_v49 = chat
        self._celdra_chat_frame_v49 = chat_frame
        self._celdra_notebook_v49 = None
        self._celdra_chat_visible_v49 = True
        comms.add(chat_frame, weight=1)
        visual_split.add(comms, weight=3)

        outer.add(top, weight=3)
        outer.add(bottom, weight=2)

        self._set_celdra_text_v38(
            "[CORE] CELDRA PRESENTATION LAYER AVAILABLE\n"
            "[CORE] SYSTEM CONSOLE AND DIALOGUE LINK VISIBLE\n"
        )
        self._load_celdra_avatar_frames_v49()
        self.after_idle(self._apply_default_celdra_layout_v50)

    def _apply_default_celdra_layout_v50(self) -> None:
        self._set_sash_fraction_v50(self.run_paned, 0.64)
        self._set_sash_fraction_v50(self.run_top_split_v50, 0.58)
        self._set_sash_fraction_v50(self.run_bottom_split_v50, 0.46)
        self._set_sash_fraction_v50(self.celdra_visual_split_v50, 0.38)
        self._set_sash_fraction_v50(self.celdra_comms_split_v50, 0.46)

    def _reset_celdra_layout_v50(self) -> None:
        self.celdra_layout_user_locked_v50 = False
        self._celdra_expanded_v49 = False
        self.after_idle(self._apply_default_celdra_layout_v50)
        if self._celdra_expand_button_v49 is not None:
            self._celdra_expand_button_v49.configure(text="Expand Celdra")

    def _remember_user_layout_v50(self, _event: tk.Event | None = None) -> None:
        self.celdra_layout_user_locked_v50 = True

    def _set_sash_fraction_v50(
        self,
        pane: ttk.Panedwindow | None,
        fraction: float,
    ) -> None:
        if pane is None:
            return
        try:
            size = pane.winfo_width() if str(pane.cget("orient")) == "horizontal" else pane.winfo_height()
            if size > 1:
                pane.sashpos(0, int(size * max(0.15, min(0.85, fraction))))
        except (AttributeError, tk.TclError):
            pass

    def _set_celdra_expanded_v49(self, expanded: bool, *, force: bool = False) -> None:
        if not force and (not self._dynamic_celdra_ui_v49() or self.celdra_layout_user_locked_v50):
            return
        self._celdra_expanded_v49 = bool(expanded)
        outer_fraction = 0.54 if expanded else 0.64
        bottom_fraction = 0.34 if expanded else 0.46
        self._animate_sash_fraction_v50(self.run_paned, outer_fraction)
        self._animate_sash_fraction_v50(self.run_bottom_split_v50, bottom_fraction)
        if self._celdra_expand_button_v49 is not None:
            self._celdra_expand_button_v49.configure(
                text="Compact Celdra" if expanded else "Expand Celdra"
            )

    def _animate_sash_fraction_v50(
        self,
        pane: ttk.Panedwindow | None,
        fraction: float,
    ) -> None:
        if pane is None:
            return
        try:
            orient = str(pane.cget("orient"))
            total = pane.winfo_width() if orient == "horizontal" else pane.winfo_height()
            current = pane.sashpos(0)
        except (AttributeError, tk.TclError):
            return
        target = int(max(1, total) * fraction)
        for step in range(1, 8):
            value = round(current + (target - current) * step / 7)
            self._remember_after_v49(
                step * 24,
                lambda selected=value, selected_pane=pane: self._set_pane_sash_v50(
                    selected_pane, selected
                ),
            )

    def _set_pane_sash_v50(self, pane: ttk.Panedwindow, value: int) -> None:
        try:
            pane.sashpos(0, int(value))
        except (AttributeError, tk.TclError):
            pass

    def _show_celdra_chat_v49(self, *, force: bool = False) -> None:
        if self._celdra_chat_v49 is not None:
            self._celdra_chat_v49.focus_set()
            self._celdra_chat_v49.see("end")
        if force:
            self._set_celdra_expanded_v49(True, force=True)

    # ------------------------------------------------------------------
    # Built-in pixel pet plus optional bundled PNG/GIF sequences.
    # ------------------------------------------------------------------
    def _load_celdra_avatar_frames_v49(self) -> None:
        self.celdra_asset_inventory_v50 = asset_inventory(self.celdra_asset_root_v50)
        self.celdra_external_frames_v50 = {}

        manifest = self.celdra_asset_inventory_v50.get("manifest") or {}
        states = manifest.get("states") if isinstance(manifest, dict) else None
        if isinstance(states, dict):
            for state, spec in states.items():
                paths: list[Path] = []
                if isinstance(spec, dict):
                    values = spec.get("frames") or ([spec.get("file")] if spec.get("file") else [])
                    if isinstance(values, list):
                        paths = [
                            self.celdra_asset_root_v50 / str(value)
                            for value in values
                            if value
                        ]
                loaded = self._load_external_paths_v50(paths)
                if loaded:
                    self.celdra_external_frames_v50[str(state).casefold()] = loaded

        if not self.celdra_external_frames_v50:
            sequences = self.celdra_asset_inventory_v50.get("sequence_groups") or []
            for group in sequences:
                frames = [
                    Path(str(row.get("path") or ""))
                    for row in group.get("frames") or []
                ]
                loaded = self._load_external_paths_v50(frames)
                if not loaded:
                    continue
                folded = str(group.get("group") or "").casefold()
                if "hatch" in folded or "egg" in folded:
                    self.celdra_external_frames_v50.setdefault("hatch", loaded)
                elif "baby" in folded or "dragon" in folded:
                    self.celdra_external_frames_v50.setdefault("idle", loaded)
                elif "talk" in folded:
                    self.celdra_external_frames_v50.setdefault("talk", loaded)
                else:
                    self.celdra_external_frames_v50.setdefault("idle", loaded)
                if "idle" in self.celdra_external_frames_v50:
                    break

        if "idle" not in self.celdra_external_frames_v50:
            gifs = self.celdra_asset_inventory_v50.get("animated_gifs") or []
            if gifs:
                loaded = self._load_gif_frames_v50(Path(str(gifs[0].get("path") or "")))
                if loaded:
                    self.celdra_external_frames_v50["idle"] = loaded

        self._play_pixel_sequence_v50(STATE_FRAMES["boot"], loop=True)

    def _load_external_paths_v50(self, paths: Iterable[Path]) -> list[tk.PhotoImage]:
        loaded: list[tk.PhotoImage] = []
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix.casefold() == ".gif":
                loaded.extend(self._load_gif_frames_v50(path))
                continue
            try:
                image = tk.PhotoImage(file=str(path))
            except tk.TclError:
                continue
            loaded.append(self._fit_photo_v50(image))
        return loaded

    def _load_gif_frames_v50(self, path: Path) -> list[tk.PhotoImage]:
        if not path.is_file():
            return []
        frames: list[tk.PhotoImage] = []
        for index in range(500):
            try:
                image = tk.PhotoImage(file=str(path), format=f"gif -index {index}")
            except tk.TclError:
                break
            frames.append(self._fit_photo_v50(image))
        return frames

    def _fit_photo_v50(self, image: tk.PhotoImage, max_width: int = 320, max_height: int = 260) -> tk.PhotoImage:
        factor = max(
            1,
            int(
                math.ceil(
                    max(
                        image.width() / float(max_width),
                        image.height() / float(max_height),
                    )
                )
            ),
        )
        return image.subsample(factor, factor) if factor > 1 else image

    def _set_avatar_state_v49(self, state: str) -> None:
        self._celdra_avatar_state_v49 = str(state or "idle").casefold()
        self._celdra_avatar_index_v49 = 0
        if self._celdra_avatar_after_v49 is not None:
            try:
                self.after_cancel(self._celdra_avatar_after_v49)
            except tk.TclError:
                pass
            self._celdra_avatar_after_v49 = None

        if self._celdra_avatar_state_v49 in {"boot", "egg", "hatch"}:
            self._play_pixel_sequence_v50(HATCH_SEQUENCE, loop=False, next_state="idle")
            return

        external = self.celdra_external_frames_v50.get(self._celdra_avatar_state_v49)
        if external is None:
            external = self.celdra_external_frames_v50.get("idle")
        if external:
            self._play_external_sequence_v50(external)
            return

        frames = STATE_FRAMES.get(
            self._celdra_avatar_state_v49,
            STATE_FRAMES["idle"],
        )
        self._play_pixel_sequence_v50(frames, loop=True)

    def _play_pixel_sequence_v50(
        self,
        frames: Iterable[PixelFrame],
        *,
        loop: bool,
        next_state: str | None = None,
    ) -> None:
        self.celdra_pixel_sequence_v50 = tuple(frames)
        self.celdra_pixel_index_v50 = 0
        self.celdra_current_external_v50 = None

        def advance() -> None:
            if not self.celdra_pixel_sequence_v50:
                return
            frame = self.celdra_pixel_sequence_v50[
                self.celdra_pixel_index_v50 % len(self.celdra_pixel_sequence_v50)
            ]
            self.celdra_current_pixel_v50 = frame
            self._redraw_celdra_avatar_v50()
            self.celdra_pixel_index_v50 += 1
            if self.celdra_pixel_index_v50 < len(self.celdra_pixel_sequence_v50):
                self._celdra_avatar_after_v49 = self.after(frame.duration_ms, advance)
            elif loop:
                self.celdra_pixel_index_v50 = 0
                self._celdra_avatar_after_v49 = self.after(frame.duration_ms, advance)
            elif next_state:
                self._celdra_avatar_after_v49 = self.after(
                    frame.duration_ms,
                    lambda: self._set_avatar_state_v49(next_state),
                )

        advance()

    def _play_external_sequence_v50(self, frames: list[tk.PhotoImage]) -> None:
        self.celdra_pixel_sequence_v50 = ()
        self.celdra_current_pixel_v50 = None

        def advance() -> None:
            if not frames:
                return
            self.celdra_current_external_v50 = frames[
                self._celdra_avatar_index_v49 % len(frames)
            ]
            self._redraw_celdra_avatar_v50()
            if len(frames) > 1 and self._avatar_animation_enabled_v49():
                self._celdra_avatar_index_v49 = (
                    self._celdra_avatar_index_v49 + 1
                ) % len(frames)
                self._celdra_avatar_after_v49 = self.after(120, advance)

        advance()

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        if self.celdra_current_external_v50 is not None:
            canvas.create_image(
                width // 2,
                height // 2,
                image=self.celdra_current_external_v50,
                anchor="center",
            )
            return
        frame = self.celdra_current_pixel_v50
        if frame is None:
            return
        rows = frame.rows
        columns = max((len(row) for row in rows), default=1)
        scale = max(2, min(width // max(1, columns), height // max(1, len(rows))))
        art_width = columns * scale
        art_height = len(rows) * scale
        x0 = (width - art_width) // 2
        y0 = (height - art_height) // 2
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = PALETTE.get(symbol, "")
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
    # Disposable Celdra Test tab and asset calibration bench.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        if "Celdra Test" in getattr(self, "tabs", {}):
            return
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="Celdra Test")
        self.tabs["Celdra Test"] = frame
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)

        intro = ttk.Label(
            frame,
            text=(
                "Temporary development surface: replay Celdra without extraction, inspect bundled "
                "PNG/GIF assets, and calibrate crop rectangles for multi-emote sheets."
            ),
            wraplength=1100,
        )
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))

        controls = ttk.LabelFrame(frame, text="Script and avatar tests", padding=6)
        controls.grid(row=1, column=0, sticky="nsw", padx=(0, 7))
        for label, command in (
            ("Full First-Run Intro", lambda: self._test_celdra_cues_v50(FIRST_SCAN_CUES, True)),
            ("Returning User", lambda: self._test_celdra_cues_v50(RETURNING_START_CUES, False)),
            ("CCSF Extraction Moment", lambda: self._test_celdra_cues_v50(STAGE_CUES["ccsf_extract"], True)),
            ("Completion", lambda: self._test_celdra_cues_v50(FIRST_DONE_CUES, True)),
            ("Failure", lambda: self._test_celdra_cues_v50(FAILURE_CUES, True)),
            ("Pixel Egg / Hatch", lambda: self._test_avatar_state_v50("boot")),
            ("Baby Idle", lambda: self._test_avatar_state_v50("idle")),
            ("Talk", lambda: self._test_avatar_state_v50("talk")),
            ("Thinking", lambda: self._test_avatar_state_v50("thinking")),
            ("Smirk", lambda: self._test_avatar_state_v50("smirk")),
            ("BLOCKED BY CELDRA", self._test_alt_f4_v50),
            ("Stop / Reset", self._reset_celdra_test_v50),
        ):
            ttk.Button(controls, text=label, command=command, width=25).pack(
                fill="x", pady=2
            )

        assets = ttk.LabelFrame(frame, text="Bundled asset inventory / crop calibration", padding=6)
        assets.grid(row=1, column=1, sticky="nsew")
        assets.columnconfigure(0, weight=1)
        assets.rowconfigure(1, weight=1)
        action_row = ttk.Frame(assets)
        action_row.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Button(
            action_row,
            text="Refresh Assets",
            command=self._refresh_celdra_assets_v50,
        ).pack(side="left")
        self.celdra_test_status_v50 = tk.StringVar(value="Asset inventory not loaded.")
        ttk.Label(action_row, textvariable=self.celdra_test_status_v50).pack(
            side="left", padx=(8, 0)
        )

        asset_split = ttk.Panedwindow(assets, orient="horizontal")
        asset_split.grid(row=1, column=0, sticky="nsew")

        tree_frame = ttk.Frame(asset_split)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            tree_frame,
            columns=("kind", "size", "notes", "path"),
            show="headings",
        )
        for key, label, width in (
            ("kind", "Kind", 110),
            ("size", "Dimensions", 90),
            ("notes", "Use", 260),
            ("path", "Bundled path", 360),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key in {"notes", "path"})
        tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=tree_y.set)
        tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", lambda _event: self._preview_selected_asset_v50())
        self.celdra_test_asset_tree_v50 = tree
        asset_split.add(tree_frame, weight=3)

        preview = ttk.Frame(asset_split)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        self.celdra_test_preview_label_v50 = ttk.Label(
            preview,
            text="Select an asset.",
            anchor="center",
            justify="center",
        )
        self.celdra_test_preview_label_v50.grid(
            row=0, column=0, columnspan=8, sticky="nsew"
        )
        self.celdra_crop_vars_v50 = {
            "state": tk.StringVar(value="reaction"),
            "x": tk.IntVar(value=0),
            "y": tk.IntVar(value=0),
            "width": tk.IntVar(value=128),
            "height": tk.IntVar(value=128),
        }
        for column, (label, key) in enumerate(
            (("State", "state"), ("X", "x"), ("Y", "y"), ("W", "width"), ("H", "height"))
        ):
            ttk.Label(preview, text=label).grid(row=1, column=column, sticky="w", padx=2)
            ttk.Entry(
                preview,
                textvariable=self.celdra_crop_vars_v50[key],
                width=12 if key == "state" else 7,
            ).grid(row=2, column=column, sticky="ew", padx=2)
        ttk.Button(
            preview,
            text="Preview Crop",
            command=lambda: self._preview_selected_asset_v50(crop=True),
        ).grid(row=2, column=5, padx=(6, 2))
        ttk.Button(
            preview,
            text="Copy Crop JSON",
            command=self._copy_celdra_crop_json_v50,
        ).grid(row=2, column=6, padx=2)
        asset_split.add(preview, weight=2)

        self._refresh_celdra_assets_v50()

    def _open_celdra_test_tab_v50(self) -> None:
        frame = self.tabs.get("Celdra Test")
        if frame is not None:
            self.notebook.select(frame)

    def _select_run_all_tab_v50(self) -> None:
        frame = self.tabs.get("RUN ALL")
        if frame is not None:
            self.notebook.select(frame)

    def _test_celdra_cues_v50(
        self,
        cues: Iterable[CeldraCue],
        first_scan: bool,
    ) -> None:
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._celdra_session_active_v49 = True
        self._celdra_first_scan_v49 = first_scan
        self._set_celdra_text_v38("")
        self._replace_chat_v49("")
        self._set_celdra_fake_progress_v49(0)
        self._set_avatar_state_v49("boot" if first_scan else "idle")
        self._schedule_celdra_cues_v49(cues)

    def _test_avatar_state_v50(self, state: str) -> None:
        self._select_run_all_tab_v50()
        self._celdra_session_active_v49 = True
        self._set_avatar_state_v49(state)

    def _reset_celdra_test_v50(self) -> None:
        self._cancel_celdra_cues_v49()
        self._celdra_session_active_v49 = False
        self._set_celdra_text_v38(
            "[CORE] CELDRA TEST RESET\n"
            "[CORE] REAL PIPELINE UNAFFECTED\n"
        )
        self._replace_chat_v49("")
        self._set_celdra_fake_progress_v49(0)
        if self._celdra_fake_status_v49 is not None:
            self._celdra_fake_status_v49.set("[CELDRA] STANDING BY")
        self._set_avatar_state_v49("idle")

    def _refresh_celdra_assets_v50(self) -> None:
        self.celdra_asset_inventory_v50 = asset_inventory(self.celdra_asset_root_v50)
        tree = getattr(self, "celdra_test_asset_tree_v50", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        self.celdra_test_asset_rows_v50.clear()
        for index, row in enumerate(self.celdra_asset_inventory_v50.get("assets") or []):
            iid = f"celdra_asset_{index}"
            dimensions = (
                f"{int(row.get('width') or 0)}×{int(row.get('height') or 0)}"
                if row.get("width") and row.get("height")
                else "unknown"
            )
            tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row.get("kind"),
                    dimensions,
                    row.get("notes"),
                    row.get("relative_path"),
                ),
            )
            self.celdra_test_asset_rows_v50[iid] = row
        count = len(self.celdra_test_asset_rows_v50)
        sheets = len(self.celdra_asset_inventory_v50.get("sprite_sheets") or [])
        gifs = len(self.celdra_asset_inventory_v50.get("animated_gifs") or [])
        self.celdra_test_status_v50.set(
            f"{count} bundled image file(s); {sheets} sheet(s); {gifs} GIF(s)."
        )
        self._load_celdra_avatar_frames_v49()

    def _selected_celdra_asset_v50(self) -> dict[str, Any] | None:
        tree = getattr(self, "celdra_test_asset_tree_v50", None)
        if tree is None:
            return None
        selected = tree.selection()
        return self.celdra_test_asset_rows_v50.get(selected[0]) if selected else None

    def _preview_selected_asset_v50(self, *, crop: bool = False) -> None:
        row = self._selected_celdra_asset_v50()
        label = getattr(self, "celdra_test_preview_label_v50", None)
        if row is None or label is None:
            return
        path = Path(str(row.get("path") or ""))
        try:
            image = tk.PhotoImage(file=str(path))
            if crop:
                x = max(0, int(self.celdra_crop_vars_v50["x"].get()))
                y = max(0, int(self.celdra_crop_vars_v50["y"].get()))
                width = max(1, int(self.celdra_crop_vars_v50["width"].get()))
                height = max(1, int(self.celdra_crop_vars_v50["height"].get()))
                cropped = tk.PhotoImage(width=width, height=height)
                cropped.tk.call(
                    str(cropped),
                    "copy",
                    str(image),
                    "-from",
                    x,
                    y,
                    x + width,
                    y + height,
                    "-to",
                    0,
                    0,
                )
                image = cropped
            image = self._fit_photo_v50(image, 460, 340)
        except (tk.TclError, OSError, ValueError) as exc:
            label.configure(image="", text=f"Preview failed:\n{exc}")
            self.celdra_test_preview_image_v50 = None
            return
        self.celdra_test_preview_image_v50 = image
        label.configure(image=image, text="")

    def _copy_celdra_crop_json_v50(self) -> None:
        row = self._selected_celdra_asset_v50()
        if row is None:
            return
        entry = crop_manifest_entry(
            str(row.get("relative_path") or ""),
            state=self.celdra_crop_vars_v50["state"].get(),
            x=self.celdra_crop_vars_v50["x"].get(),
            y=self.celdra_crop_vars_v50["y"].get(),
            width=self.celdra_crop_vars_v50["width"].get(),
            height=self.celdra_crop_vars_v50["height"].get(),
        )
        text = json.dumps(entry, indent=2)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.celdra_test_status_v50.set("Crop manifest JSON copied to clipboard.")

    # ------------------------------------------------------------------
    # Alt+F4 joke: one clear block, apology, and an explicit real-exit path.
    # ------------------------------------------------------------------
    def _test_alt_f4_v50(self) -> None:
        self._select_run_all_tab_v50()
        self._show_alt_f4_blocked_v50()

    def _celdra_alt_f4_v49(self, _event: tk.Event) -> str | None:
        if (
            not self._celdra_session_active_v49
            or not self.task_active
            or not self._alt_f4_enabled_v49()
        ):
            return None
        self._celdra_alt_f4_count_v49 += 1
        if self._celdra_alt_f4_count_v49 == 1:
            self._show_alt_f4_blocked_v50()
            return "break"
        self._append_chat_v49(f"Celdra> {ALT_F4_SECOND}")
        self.after(100, self._close)
        return "break"

    def _show_alt_f4_blocked_v50(self) -> None:
        if self.celdra_alt_f4_popup_v50 is not None:
            try:
                self.celdra_alt_f4_popup_v50.lift()
                return
            except tk.TclError:
                self.celdra_alt_f4_popup_v50 = None

        self._append_chat_v49(
            "Celdra> Nice try, noob. Alt+F4 does not make extraction faster.\n"
            "Celdra> ...Okay, that sounded mean. Sorry. You're probably not a noob."
        )
        self._set_avatar_state_v49("smirk")
        self._set_celdra_expanded_v49(True)

        popup = tk.Toplevel(self)
        self.celdra_alt_f4_popup_v50 = popup
        popup.title("BLOCKED BY CELDRA")
        popup.transient(self)
        popup.resizable(False, False)
        popup.protocol("WM_DELETE_WINDOW", lambda: self._dismiss_alt_f4_popup_v50())
        frame = ttk.Frame(popup, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="BLOCKED BY CELDRA",
            font=("Segoe UI", 18, "bold"),
            anchor="center",
        ).pack(fill="x")
        ttk.Label(
            frame,
            text=(
                "Nice try, noob. Alt+F4 does not make extraction faster.\n\n"
                "...Okay, that was a little mean. Sorry.\n"
                "You are probably not a noob. The evidence is inconclusive."
            ),
            justify="center",
            wraplength=460,
        ).pack(fill="x", pady=(12, 16))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(
            buttons,
            text="Continue Extraction",
            command=self._dismiss_alt_f4_popup_v50,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Actually Exit…",
            command=self._real_exit_from_celdra_popup_v50,
        ).pack(side="right")
        popup.update_idletasks()
        x = self.winfo_rootx() + max(20, (self.winfo_width() - popup.winfo_width()) // 2)
        y = self.winfo_rooty() + max(20, (self.winfo_height() - popup.winfo_height()) // 2)
        popup.geometry(f"+{x}+{y}")
        popup.grab_set()

    def _dismiss_alt_f4_popup_v50(self) -> None:
        popup = self.celdra_alt_f4_popup_v50
        self.celdra_alt_f4_popup_v50 = None
        if popup is not None:
            try:
                popup.grab_release()
                popup.destroy()
            except tk.TclError:
                pass
        self._set_avatar_state_v49("idle")

    def _real_exit_from_celdra_popup_v50(self) -> None:
        self._dismiss_alt_f4_popup_v50()
        self.after(50, self._close)


def main() -> int:
    app = PublicFragmenterAppV50()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

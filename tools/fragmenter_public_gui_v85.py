#!/usr/bin/env python3
"""V85: 2D viewport authoring, complete sizing history, and reliable mini playback."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_authoring_project_v1 import normalize_event, normalize_events
from celdra_evolution_pixel_v4 import CELDRA_BLUE_PALETTE, EVOLUTION_PHASES
from fragmenter_public_gui_v84 import PublicFragmenterAppV84


class PublicFragmenterAppV85(PublicFragmenterAppV84):
    """Make every timeline beat previewable with editable width and height."""

    CELDRA_DRAFT_MIN_WIDTH = 34
    CELDRA_DRAFT_MIN_HEIGHT = 52

    def __init__(self) -> None:
        self._celdra_event_height_v85: tk.IntVar | None = None
        self._celdra_event_top_v85: tk.IntVar | None = None
        self._celdra_event_layout_override_v85: tk.BooleanVar | None = None
        self._celdra_geometry_editor_guard_v85 = False
        self._celdra_main_vertical_preview_v85 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra 2D Timeline Sequencer")

    # ------------------------------------------------------------------
    # Add a dedicated 2D viewport editor to the selected-event inspector.
    # ------------------------------------------------------------------
    def _build_author_timeline_tab_v74(self, parent: ttk.Frame) -> None:
        super()._build_author_timeline_tab_v74(parent)
        self._install_viewport_editor_v85()
        self._install_realtime_speed_buttons_v85()

    def _selected_event_notebook_v85(self) -> ttk.Notebook | None:
        tree = self._celdra_author_event_tree_v74
        if tree is None:
            return None
        paned = tree.master.master
        for child in paned.winfo_children():
            if not isinstance(child, ttk.LabelFrame):
                continue
            try:
                if str(child.cget("text")) != "Selected event":
                    continue
            except tk.TclError:
                continue
            for nested in child.winfo_children():
                if isinstance(nested, ttk.Notebook):
                    return nested
        return None

    def _install_viewport_editor_v85(self) -> None:
        notebook = self._selected_event_notebook_v85()
        if notebook is None:
            return
        for tab_id in notebook.tabs():
            try:
                if str(notebook.tab(tab_id, "text")) == "Viewport 2D":
                    return
            except tk.TclError:
                continue

        tab = ttk.Frame(notebook, padding=7)
        notebook.add(tab, text="Viewport 2D")
        tab.columnconfigure(1, weight=1)

        self._celdra_event_height_v85 = tk.IntVar(value=100)
        self._celdra_event_top_v85 = tk.IntVar(value=0)
        self._celdra_event_layout_override_v85 = tk.BooleanVar(value=False)

        ttk.Label(
            tab,
            text=(
                "Width changes the avatar/console split. Height and top Y define "
                "Celdra's vertical display area. Enable the override to save this "
                "geometry on any event type."
            ),
            wraplength=350,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))

        ttk.Label(tab, text="Viewport width %").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Spinbox(
            tab,
            textvariable=self._celdra_event_window_v74,
            from_=4,
            to=99,
            increment=1,
            width=12,
        ).grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(tab, text="Viewport height %").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Spinbox(
            tab,
            textvariable=self._celdra_event_height_v85,
            from_=20,
            to=100,
            increment=1,
            width=12,
        ).grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Label(tab, text="Viewport top Y %").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Spinbox(
            tab,
            textvariable=self._celdra_event_top_v85,
            from_=0,
            to=80,
            increment=1,
            width=12,
        ).grid(row=3, column=1, sticky="ew", pady=2)

        ttk.Checkbutton(
            tab,
            text="Apply viewport geometry on this event",
            variable=self._celdra_event_layout_override_v85,
            command=self._preview_editor_geometry_v85,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 4))

        actions = ttk.Frame(tab)
        actions.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        for column in range(2):
            actions.columnconfigure(column, weight=1)
        ttk.Button(
            actions,
            text="Preview unsaved geometry",
            command=self._preview_editor_geometry_v85,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(
            actions,
            text="Preview geometry in main",
            command=self._preview_editor_geometry_main_v85,
        ).grid(row=0, column=1, sticky="ew", padx=(2, 0), pady=2)
        ttk.Button(
            actions,
            text="Save geometry to event",
            command=self._save_selected_geometry_v85,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(
            actions,
            text="Full-height working area",
            command=lambda: self._set_editor_geometry_v85(56, 100, 0),
        ).grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=2)
        ttk.Button(
            actions,
            text="Draft Celdra minimum",
            command=lambda: self._set_editor_geometry_v85(
                self.CELDRA_DRAFT_MIN_WIDTH,
                self.CELDRA_DRAFT_MIN_HEIGHT,
                24,
            ),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=2)

        ttk.Label(
            tab,
            text=(
                "Draft minimum marker: 34% wide x 52% high. This is only an "
                "authoring warning for now; later Celdra can object when the user "
                "pushes her below the reserved area."
            ),
            wraplength=350,
            justify="left",
        ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        for variable in (
            self._celdra_event_window_v74,
            self._celdra_event_height_v85,
            self._celdra_event_top_v85,
        ):
            if variable is not None:
                variable.trace_add("write", lambda *_args: self._geometry_changed_v85())

    def _install_realtime_speed_buttons_v85(self) -> None:
        scale = self._celdra_mini_scale_v84
        if scale is None:
            return
        transport = scale.master
        presets = ttk.Frame(transport)
        presets.grid(row=2, column=0, columnspan=8, sticky="ew", pady=(4, 0))
        ttk.Label(presets, text="Playback presets").pack(side="left")
        for label, speed in (("Realtime 1x", 1.0), ("5x", 5.0), ("20x", 20.0)):
            ttk.Button(
                presets,
                text=label,
                command=lambda value=speed: self._set_mini_speed_v85(value),
            ).pack(side="left", padx=(4, 0))

    def _set_mini_speed_v85(self, speed: float) -> None:
        if self._celdra_mini_speed_var_v84 is not None:
            self._celdra_mini_speed_var_v84.set(float(speed))
        if self._celdra_mini_status_v84 is not None:
            label = "realtime" if float(speed) == 1.0 else f"{speed:g}x"
            self._celdra_mini_status_v84.set(
                f"Playback speed set to {label} at {self._format_time_v84(self._celdra_mini_playhead_ms_v84)}"
            )

    # ------------------------------------------------------------------
    # Persist and reload the new geometry fields.
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_int_v85(variable: tk.Variable | None, default: int) -> int:
        if variable is None:
            return int(default)
        try:
            return int(variable.get())
        except (tk.TclError, TypeError, ValueError):
            return int(default)

    def _event_snapshot_v74(self, *, event_id: str = "") -> dict[str, Any]:
        row = super()._event_snapshot_v74(event_id=event_id)
        row["window_height_percent"] = max(
            20,
            min(100, self._safe_int_v85(self._celdra_event_height_v85, 100)),
        )
        row["window_y_percent"] = max(
            0,
            min(80, self._safe_int_v85(self._celdra_event_top_v85, 0)),
        )
        row["layout_override"] = bool(
            self._celdra_event_layout_override_v85.get()
            if self._celdra_event_layout_override_v85 is not None
            else row.get("layout_override", False)
        )
        return normalize_event(row, self._celdra_author_event_serial_v74)

    def _load_selected_author_event_v74(self, event: tk.Event | None = None) -> None:
        self._celdra_geometry_editor_guard_v85 = True
        try:
            super()._load_selected_author_event_v74(event)
            row = self._celdra_author_event_rows_v74.get(self._selected_author_event_id_v74())
            if row is None:
                return
            if self._celdra_event_height_v85 is not None:
                self._celdra_event_height_v85.set(int(row.get("window_height_percent") or 100))
            if self._celdra_event_top_v85 is not None:
                self._celdra_event_top_v85.set(int(row.get("window_y_percent") or 0))
            if self._celdra_event_layout_override_v85 is not None:
                self._celdra_event_layout_override_v85.set(bool(row.get("layout_override", False)))
        finally:
            self._celdra_geometry_editor_guard_v85 = False
        self._preview_editor_geometry_v85()

    def _geometry_changed_v85(self) -> None:
        if self._celdra_geometry_editor_guard_v85:
            return
        if self._celdra_event_layout_override_v85 is not None:
            self._celdra_event_layout_override_v85.set(True)
        self.after_idle(self._preview_editor_geometry_v85)

    def _set_editor_geometry_v85(self, width: int, height: int, top: int) -> None:
        self._celdra_geometry_editor_guard_v85 = True
        try:
            if self._celdra_event_window_v74 is not None:
                self._celdra_event_window_v74.set(width)
            if self._celdra_event_height_v85 is not None:
                self._celdra_event_height_v85.set(height)
            if self._celdra_event_top_v85 is not None:
                self._celdra_event_top_v85.set(top)
            if self._celdra_event_layout_override_v85 is not None:
                self._celdra_event_layout_override_v85.set(True)
        finally:
            self._celdra_geometry_editor_guard_v85 = False
        self._preview_editor_geometry_v85()

    def _save_selected_geometry_v85(self) -> None:
        if self._celdra_event_layout_override_v85 is not None:
            self._celdra_event_layout_override_v85.set(True)
        self._update_author_event_v74()
        self._preview_editor_geometry_v85()

    def _editor_preview_state_v85(self) -> dict[str, Any] | None:
        row = self._celdra_author_event_rows_v74.get(self._selected_author_event_id_v74())
        if row is None:
            return None
        state, _active = self._timeline_state_at_v84(float(row.get("at_ms") or 0))
        state["window_percent"] = max(
            4,
            min(99, self._safe_int_v85(self._celdra_event_window_v74, 56)),
        )
        state["window_height_percent"] = max(
            20,
            min(100, self._safe_int_v85(self._celdra_event_height_v85, 100)),
        )
        state["window_y_percent"] = max(
            0,
            min(80, self._safe_int_v85(self._celdra_event_top_v85, 0)),
        )
        asset = str(
            self._celdra_event_asset_v74.get()
            if self._celdra_event_asset_v74 is not None
            else row.get("asset") or ""
        ).strip()
        if asset:
            state["asset"] = asset
            state["visible"] = True
        state["x"] = self._safe_int_v85(self._celdra_event_x_v74, int(state.get("x") or 0))
        state["y"] = self._safe_int_v85(self._celdra_event_y_v74, int(state.get("y") or 0))
        state["scale"] = self._safe_int_v85(self._celdra_event_scale_v74, int(state.get("scale") or 100))
        text = self._event_text_value_v74(self._celdra_event_text_v74)
        action = str(
            self._celdra_event_action_v74.get()
            if self._celdra_event_action_v74 is not None
            else row.get("action") or ""
        ).casefold()
        if text and action in {"bubble", "chat", "pose", "avatar", "asset"}:
            state["bubble_text"] = text
            state["bubble_style"] = (
                self._celdra_event_bubble_style_v74.get()
                if self._celdra_event_bubble_style_v74 is not None
                else state.get("bubble_style")
            )
            state["bubble_x"] = self._safe_int_v85(self._celdra_event_bubble_x_v74, 4)
            state["bubble_y"] = self._safe_int_v85(self._celdra_event_bubble_y_v74, 3)
            state["bubble_width"] = self._safe_int_v85(self._celdra_event_bubble_width_v74, 52)
        return state

    def _preview_editor_geometry_v85(self) -> None:
        state = self._editor_preview_state_v85()
        if state is None:
            return
        self._render_timeline_mini_v84(state)
        if self._celdra_mini_status_v84 is not None:
            self._celdra_mini_status_v84.set(
                "Unsaved editor geometry preview - use Save geometry to event to persist"
            )

    def _preview_editor_geometry_main_v85(self) -> None:
        state = self._editor_preview_state_v85()
        if state is None:
            return
        values = dict(state)
        values["text"] = str(state.get("bubble_text") or "")
        self._preview_values_in_main_v77(values)

    # ------------------------------------------------------------------
    # Make the tree show inherited versus explicit 2D geometry.
    # ------------------------------------------------------------------
    def _refresh_author_event_tree_v74(self, *, select_id: str = "") -> None:
        super()._refresh_author_event_tree_v74(select_id=select_id)
        tree = self._celdra_author_event_tree_v74
        if tree is None:
            return
        try:
            tree.heading("viewport", text="Viewport W x H / Y")
            tree.column("viewport", width=124, stretch=False)
        except tk.TclError:
            return
        explicit_count = 0
        for event_id, row in self._celdra_author_event_rows_v74.items():
            if not tree.exists(event_id):
                continue
            if bool(row.get("layout_override", False)):
                explicit_count += 1
                value = (
                    f"{int(row.get('window_percent') or 56)} x "
                    f"{int(row.get('window_height_percent') or 100)} / "
                    f"{int(row.get('window_y_percent') or 0)}"
                )
            else:
                value = "inherited"
            try:
                tree.set(event_id, "viewport", value)
            except tk.TclError:
                pass
        if self._celdra_timeline_summary_v84 is not None:
            rows = normalize_events(self._celdra_author_events_v74)
            end_ms = self._timeline_end_v84(rows)
            after_break = sum(1 for row in rows if int(row.get("at_ms") or 0) > 542_000)
            self._celdra_timeline_summary_v84.set(
                f"{len(rows)} events - {after_break} after breakpoint - "
                f"{explicit_count} geometry overrides - end {end_ms / 1000:.2f}s"
            )

    # ------------------------------------------------------------------
    # Reconstruct width, height, top, visibility, and assets at any time.
    # ------------------------------------------------------------------
    def _timeline_state_at_v84(self, target_ms: float) -> tuple[dict[str, Any], str]:
        state, active_id = super()._timeline_state_at_v84(target_ms)
        state.setdefault("window_height_percent", 100)
        state.setdefault("window_y_percent", 0)
        active_branch = ""
        rows = normalize_events(
            row for row in self._celdra_author_events_v74 if row.get("enabled", True)
        )
        for row in rows:
            if int(row.get("at_ms") or 0) > target_ms:
                break
            sequence = str(row.get("sequence") or "main")
            if sequence != "main" and sequence != active_branch:
                continue
            action = str(row.get("action") or "console").casefold()
            if action == "condition":
                result = self._evaluate_author_condition_v74(str(row.get("condition") or ""))
                active_branch = str(
                    row.get("true_sequence") if result else row.get("false_sequence") or ""
                )
                continue
            if bool(row.get("layout_override", False)):
                state["window_percent"] = int(row.get("window_percent") or state["window_percent"])
                state["window_height_percent"] = int(
                    row.get("window_height_percent") or state["window_height_percent"]
                )
                state["window_y_percent"] = int(
                    row.get("window_y_percent") or state["window_y_percent"]
                )
            asset = str(row.get("asset") or "").strip()
            if action in {"pose", "avatar", "asset", "move", "avatar_takeover"}:
                if asset:
                    state["asset"] = asset
                state["visible"] = True
            elif action in {"show_avatar", "ascii", "energy_hatch"}:
                state["visible"] = True
                if action == "ascii" and not asset:
                    state["asset"] = "egg_wait"
            elif action == "hide_avatar":
                state["visible"] = False
        if target_ms < 180_000 and str(state.get("asset") or "") in {
            "egg_wait",
            "crack_one",
            "crack_two",
            "hatch_open",
            "hatch_gif",
        }:
            state["visible"] = True
        return state, active_id

    # ------------------------------------------------------------------
    # Render the mini-player as a true 2D viewport rather than a full-height strip.
    # ------------------------------------------------------------------
    def _viewport_rect_v85(
        self,
        canvas_width: int,
        canvas_height: int,
        state: dict[str, Any],
    ) -> tuple[int, int, int, int]:
        width_percent = max(4, min(99, int(state.get("window_percent") or 56)))
        height_percent = max(20, min(100, int(state.get("window_height_percent") or 100)))
        top_percent = max(0, min(80, int(state.get("window_y_percent") or 0)))
        stage_width = max(90, min(canvas_width - 105, round(canvas_width * width_percent / 100.0)))
        stage_height = max(72, min(canvas_height, round(canvas_height * height_percent / 100.0)))
        stage_y = round(canvas_height * top_percent / 100.0)
        stage_y = max(0, min(canvas_height - stage_height, stage_y))
        return 0, stage_y, stage_width, stage_y + stage_height

    def _render_timeline_mini_v84(self, state: dict[str, Any] | None = None) -> None:
        canvas = self._celdra_mini_canvas_v84
        if canvas is None:
            return
        if state is None:
            state, _active = self._timeline_state_at_v84(self._celdra_mini_playhead_ms_v84)
        width = max(420, canvas.winfo_width())
        height = max(245, canvas.winfo_height())
        x1, y1, x2, y2 = self._viewport_rect_v85(width, height, state)
        stage_width = x2 - x1
        stage_height = y2 - y1
        canvas.delete("all")
        self._celdra_mini_refs_v84.clear()
        canvas.create_rectangle(0, 0, width, height, fill="#10151d", outline="")
        canvas.create_rectangle(x1, y1, x2, y2, fill="#081321", outline="#78b9ea", width=2)
        canvas.create_rectangle(x1, y1, x2, min(y2, y1 + 28), fill="#0d2035", outline="")
        canvas.create_text(
            x1 + 7,
            y1 + 6,
            text=(
                f"CELDRA {int(state.get('window_percent') or 56)}x"
                f"{int(state.get('window_height_percent') or 100)} "
                f"Y{int(state.get('window_y_percent') or 0)} - "
                f"{self._format_time_v84(state.get('time_ms') or 0)}"
            ),
            anchor="nw",
            fill="#d9f1ff",
            font=("Consolas", 7, "bold"),
        )

        self._draw_mini_corruption_v85(canvas, x1, y1, x2, y2, state)
        self._draw_mini_avatar_v85(canvas, x1, y1, x2, y2, state)
        if state.get("energy_active"):
            self._draw_mini_energy_v85(canvas, x1, y1, x2, y2, state)

        bubble_text = str(state.get("bubble_text") or "")
        if bubble_text:
            values = {
                "bubble_x": state.get("bubble_x", 4),
                "bubble_y": state.get("bubble_y", 3),
                "bubble_width": state.get("bubble_width", 52),
                "bubble_style": state.get("bubble_style", "Rounded blue"),
            }
            local = self._bubble_bounds_v81(stage_width, stage_height, values, bubble_text)
            bounds = (local[0], y1 + local[1], local[2], y1 + local[3])
            self._draw_bubble_style_v81(
                canvas,
                bounds,
                str(state.get("bubble_style") or "Rounded blue"),
                bubble_text,
            )

        console_x = x2 + 7
        canvas.create_text(
            console_x,
            7,
            text="CONSOLE",
            anchor="nw",
            fill="#48d76d",
            font=("Consolas", 8, "bold"),
        )
        console_width = max(55, width - console_x - 6)
        console_y = 25
        for line in list(state.get("console_lines") or [])[-10:]:
            folded = str(line).upper()
            fill = "#ff5964" if "[BRAIN]" in folded and "ERROR" in folded else "#8db1c8"
            item = canvas.create_text(
                console_x,
                console_y,
                text=str(line),
                anchor="nw",
                width=console_width,
                fill=fill,
                font=("Consolas", 6),
            )
            bounds = canvas.bbox(item)
            console_y = bounds[3] + 2 if bounds else console_y + 14
            if console_y > height - 24:
                break

        too_small = (
            int(state.get("window_percent") or 56) < self.CELDRA_DRAFT_MIN_WIDTH
            or int(state.get("window_height_percent") or 100) < self.CELDRA_DRAFT_MIN_HEIGHT
        )
        footer = (
            "CELDRA SPACE BELOW DRAFT MINIMUM"
            if too_small
            else f"viewport {stage_width}x{stage_height}px / console {width - x2}px"
        )
        canvas.create_text(
            width - 6,
            height - 5,
            text=footer,
            anchor="se",
            fill="#ff7380" if too_small else "#557c9e",
            font=("Consolas", 6, "bold" if too_small else "normal"),
        )

    def _draw_mini_avatar_v85(
        self,
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        state: dict[str, Any],
    ) -> None:
        if not state.get("visible"):
            return
        stage_width = x2 - x1
        stage_height = y2 - y1
        asset = str(state.get("asset") or "egg_wait").casefold()
        if state.get("energy_active"):
            elapsed = int(state.get("energy_elapsed") or 0)
            if 4 * 96 <= elapsed < 44 * 96:
                asset = "hatch_open"
            elif elapsed >= 44 * 96:
                asset = "hatch_gif"
        if asset in getattr(self, "GENERATED_PREVIEW_PHASES", ()):
            self._draw_mini_generated_v85(canvas, x1, y1, x2, y2, asset, state)
            return
        photo = self._preview_photo_for_asset_v74(
            asset,
            max(10, min(500, int(state.get("scale") or 100))),
        )
        if photo is None:
            canvas.create_rectangle(
                x1 + 12,
                y1 + 38,
                x2 - 12,
                y2 - 12,
                outline="#ff5964",
                dash=(4, 3),
            )
            canvas.create_text(
                (x1 + x2) // 2,
                (y1 + y2) // 2,
                text=f"ASSET NOT RESOLVED\n{asset}",
                justify="center",
                fill="#ff8b94",
                font=("Consolas", 7, "bold"),
            )
            return
        divisor = max(
            1,
            math.ceil(photo.width() / max(45, stage_width * 0.82)),
            math.ceil(photo.height() / max(55, stage_height - 38)),
        )
        display = photo if divisor <= 1 else photo.subsample(divisor, divisor)
        self._celdra_mini_refs_v84.extend([photo, display])
        x = (x1 + x2) // 2 + int(state.get("x") or 0)
        x = max(x1 + display.width() // 2 + 3, min(x2 - display.width() // 2 - 3, x))
        bottom = y2 - 7 + int(state.get("y") or 0)
        canvas.create_image(x, bottom, image=display, anchor="s")

    def _draw_mini_generated_v85(
        self,
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        phase: str,
        state: dict[str, Any],
    ) -> None:
        frames = EVOLUTION_PHASES.get(phase)
        if not frames:
            return
        rows = frames[0].rows
        columns = max((len(row) for row in rows), default=1)
        stage_width = x2 - x1
        stage_height = y2 - y1
        pixel = max(
            1,
            min(
                max(1, (stage_width - 16) // max(1, columns)),
                max(1, (stage_height - 38) // max(1, len(rows))),
            ),
        )
        pixel = min(
            pixel,
            max(1, round(3 * max(10, min(500, int(state.get("scale") or 100))) / 100.0)),
        )
        art_width = columns * pixel
        art_height = len(rows) * pixel
        x0 = (x1 + x2) // 2 - art_width // 2 + int(state.get("x") or 0)
        y0 = y2 - 7 - art_height + int(state.get("y") or 0)
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = CELDRA_BLUE_PALETTE.get(symbol, "")
                if not color:
                    continue
                canvas.create_rectangle(
                    x0 + column_index * pixel,
                    y0 + row_index * pixel,
                    x0 + (column_index + 1) * pixel,
                    y0 + (row_index + 1) * pixel,
                    fill=color,
                    outline=color,
                )

    @staticmethod
    def _draw_mini_corruption_v85(
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        state: dict[str, Any],
    ) -> None:
        level = int(state.get("glitch_level") or 0)
        if level <= 0:
            return
        alarm = bool(state.get("instability"))
        colors = (
            ("#5e1118", "#861923", "#aa202b", "#d0323d", "#f04a54")
            if alarm
            else ("#0a3b26", "#0d5734", "#117044", "#168956", "#35c982")
        )
        terms = ("AURA", "INFECTION", "MUTATION", "QUARANTINE", "SERENIAL", "CELDRA", "FRAGMENT", "CCSF")
        phase = int(float(state.get("time_ms") or 0) // 120)
        width = max(20, x2 - x1 - 16)
        height = max(20, y2 - y1 - 42)
        for slot in range(5 + level * 4):
            term = terms[(slot * 3 + phase) % len(terms)]
            text = term if slot % 3 == 0 else term[::-1] if slot % 3 == 1 else f"{(slot * 31 + phase) & 0xFF:02X}//{term}"
            x = x1 + 8 + ((slot * 53 + phase * (2 + slot % 3)) % width)
            y = y1 + 31 + ((slot * 37 + phase * (3 + slot % 4)) % height)
            canvas.create_text(
                x,
                y,
                text=text,
                anchor="center",
                fill=colors[(slot + phase) % len(colors)],
                font=("Consolas", 5 + slot % 3),
            )

    @staticmethod
    def _draw_mini_energy_v85(
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        state: dict[str, Any],
    ) -> None:
        elapsed = int(state.get("energy_elapsed") or 0)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2 + 8
        phase = elapsed / 96.0
        radius = 14 + min(max(20, (x2 - x1) * 0.42), phase * 2.8)
        for ray in range(18):
            angle = math.radians(ray * 20 + phase * 7)
            inner = radius * (0.28 + (ray % 4) * 0.04)
            outer = radius * (0.82 + (ray % 5) * 0.07)
            canvas.create_line(
                cx + math.cos(angle) * inner,
                cy + math.sin(angle) * inner,
                cx + math.cos(angle) * outer,
                cy + math.sin(angle) * outer,
                fill="#d9f6ff" if ray % 3 else "#6fdcff",
                width=1 + ray % 2,
            )
        if 44 * 96 <= elapsed < 5_200:
            canvas.create_rectangle(x1, y1, x2, y2, fill="#ffffff", outline="")
            canvas.create_text(
                cx,
                cy,
                text="WHITEOUT / GIF SWAP",
                fill="#4b6070",
                font=("Consolas", 7, "bold"),
            )

    # ------------------------------------------------------------------
    # Apply vertical preview geometry to the real RUN ALL surface.
    # ------------------------------------------------------------------
    def _preview_values_in_main_v77(self, values: dict[str, Any]) -> None:
        data = dict(values)
        height_percent = max(20, min(100, int(data.get("window_height_percent") or 100)))
        top_percent = max(0, min(80, int(data.get("window_y_percent") or 0)))
        bubble_y = max(0, min(90, int(data.get("bubble_y") or 3)))
        transformed = dict(data)
        transformed["bubble_y"] = round(top_percent + height_percent * bubble_y / 100.0)
        super()._preview_values_in_main_v77(transformed)
        self.after_idle(
            lambda: self._apply_main_vertical_geometry_v85(height_percent, top_percent)
        )

    def _apply_main_vertical_geometry_v85(self, height_percent: int, top_percent: int) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        height_fraction = max(0.20, min(1.0, height_percent / 100.0))
        top_fraction = max(0.0, min(0.80, top_percent / 100.0))
        top_fraction = min(top_fraction, 1.0 - height_fraction)
        try:
            if height_percent >= 100 and top_percent <= 0:
                self._restore_main_vertical_geometry_v85()
                return
            canvas.grid_remove()
            canvas.place(
                relx=0.0,
                rely=top_fraction,
                relwidth=1.0,
                relheight=height_fraction,
            )
            self._celdra_main_vertical_preview_v85 = True
            self._redraw_celdra_avatar_v50()
        except tk.TclError:
            pass

    def _restore_main_vertical_geometry_v85(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        try:
            canvas.place_forget()
            canvas.grid(row=0, column=0, sticky="nsew")
            self._celdra_main_vertical_preview_v85 = False
        except tk.TclError:
            pass

    def _prepare_first_run_surface_v51(self) -> None:
        self._restore_main_vertical_geometry_v85()
        super()._prepare_first_run_surface_v51()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V85"
            metadata["viewport_2d"] = True
            metadata["realtime_playback"] = True
            metadata["draft_celdra_minimum"] = {
                "width_percent": self.CELDRA_DRAFT_MIN_WIDTH,
                "height_percent": self.CELDRA_DRAFT_MIN_HEIGHT,
            }
        return payload


def main() -> int:
    app = PublicFragmenterAppV85()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

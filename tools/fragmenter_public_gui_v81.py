#!/usr/bin/env python3
"""V81: complete post-breakpoint authoring and production-accurate framing lab."""
from __future__ import annotations

import json
import math
import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_authoring_post_breakpoint_v1 import extend_with_post_breakpoint
from celdra_authoring_project_v1 import read_project
from fragmenter_public_gui_v80 import PublicFragmenterAppV80


class PublicFragmenterAppV81(PublicFragmenterAppV80):
    """Expose hidden runtime beats and make avatar/bubble framing measurable."""

    IMPORT_FALLBACK_RELATIVE = "authoring/imports/fade-v79-2026-07-17.json"
    PREVIEW_BUBBLE_STYLES = (
        "Rounded blue",
        "Terminal green",
        "Manga white",
        "Minimal dark",
        "Soft cyan glass",
        "Pixel terminal",
        "Angular HUD",
        "Caption ribbon",
        "Cloud comic",
    )
    AUDIT_WIDTHS = (34, 50, 56, 64, 70)

    def __init__(self) -> None:
        self._celdra_framing_canvas_v81: tk.Canvas | None = None
        self._celdra_framing_audit_canvas_v81: tk.Canvas | None = None
        self._celdra_framing_refs_v81: list[tk.PhotoImage] = []
        self._celdra_framing_audit_refs_v81: list[tk.PhotoImage] = []
        self._celdra_framing_asset_v81: tk.StringVar | None = None
        self._celdra_framing_scale_v81: tk.IntVar | None = None
        self._celdra_framing_x_v81: tk.IntVar | None = None
        self._celdra_framing_y_v81: tk.IntVar | None = None
        self._celdra_framing_window_v81: tk.IntVar | None = None
        self._celdra_framing_style_v81: tk.StringVar | None = None
        self._celdra_framing_bubble_x_v81: tk.IntVar | None = None
        self._celdra_framing_bubble_y_v81: tk.IntVar | None = None
        self._celdra_framing_bubble_w_v81: tk.IntVar | None = None
        self._celdra_framing_text_v81: tk.Text | None = None
        self._celdra_framing_guides_v81: tk.BooleanVar | None = None
        self._celdra_framing_metrics_v81: tk.StringVar | None = None
        self._celdra_main_preview_values_v81: dict[str, Any] | None = None
        self._celdra_loaded_project_v81 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Framing + Timeline Workspace")
        self._ensure_post_breakpoint_events_v81()
        self.after_idle(self._autoload_authoring_project_v81)

    # ------------------------------------------------------------------
    # Make callback-driven runtime beats visible after the 542s breakpoint.
    # ------------------------------------------------------------------
    def _ensure_post_breakpoint_events_v81(self) -> None:
        self._celdra_author_events_v74 = extend_with_post_breakpoint(
            self._celdra_author_events_v74
        )
        self._celdra_author_event_serial_v74 = max(
            self._celdra_author_event_serial_v74,
            len(self._celdra_author_events_v74),
        )
        if self._celdra_author_event_tree_v74 is not None:
            self._refresh_author_event_tree_v74()

    def _reset_canonical_events_v74(self) -> None:
        super()._reset_canonical_events_v74()
        self._ensure_post_breakpoint_events_v81()

    def _apply_author_project_payload_v74(self, payload: dict[str, Any]) -> None:
        super()._apply_author_project_payload_v74(payload)
        self._ensure_post_breakpoint_events_v81()
        framing = payload.get("framing_lab")
        if isinstance(framing, dict):
            self._apply_framing_values_v81(framing, update_editor=False)
        self._render_framing_v81()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        payload["events"] = extend_with_post_breakpoint(payload.get("events") or [])
        payload["framing_lab"] = self._framing_values_v81()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V81"
            metadata["post_breakpoint_events"] = True
            metadata["framing_lab"] = True
            metadata["bubble_styles"] = list(self.PREVIEW_BUBBLE_STYLES)
        return payload

    def _autoload_authoring_project_v81(self) -> None:
        if self._celdra_loaded_project_v81:
            return
        self._celdra_loaded_project_v81 = True
        primary = self.celdra_asset_root_v50 / self.AUTHOR_PROJECT_RELATIVE
        fallback = self.celdra_asset_root_v50 / self.IMPORT_FALLBACK_RELATIVE
        candidate = primary if primary.is_file() else fallback if fallback.is_file() else None
        if candidate is None:
            self._ensure_post_breakpoint_events_v81()
            return
        try:
            payload = read_project(candidate)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if self._celdra_author_project_status_v74 is not None:
                self._celdra_author_project_status_v74.set(
                    f"Could not auto-load {candidate.name}: {exc}"
                )
            return
        self._apply_author_project_payload_v74(payload)
        self._celdra_author_project_path_v74 = primary
        if self._celdra_author_project_status_v74 is not None:
            source = "local saved project" if candidate == primary else "preserved V79 import"
            self._celdra_author_project_status_v74.set(f"Loaded {source}: {candidate}")

    # ------------------------------------------------------------------
    # Add a dedicated resizable Framing Lab subtab.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        notebook = getattr(self, "_celdra_author_notebook_v74", None)
        if notebook is None:
            return
        for tab_id in notebook.tabs():
            try:
                if str(notebook.tab(tab_id, "text")) == "Framing Lab":
                    return
            except tk.TclError:
                continue
        framing = ttk.Frame(notebook, padding=6)
        notebook.add(framing, text="Framing Lab")
        self._build_framing_lab_v81(framing)

    def _build_framing_lab_v81(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        outer = ttk.Panedwindow(parent, orient="vertical")
        outer.grid(row=0, column=0, sticky="nsew")

        preview_box = ttk.LabelFrame(
            outer,
            text="Frozen production framing — drag the horizontal divider",
            padding=4,
        )
        preview_box.rowconfigure(0, weight=1)
        preview_box.columnconfigure(0, weight=1)
        canvas = tk.Canvas(
            preview_box,
            width=1100,
            height=590,
            background="#081321",
            highlightthickness=1,
            highlightbackground="#35536f",
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.bind("<Configure>", lambda _event: self.after_idle(self._render_framing_v81))
        self._celdra_framing_canvas_v81 = canvas
        outer.add(preview_box, weight=5)

        lower = ttk.Frame(outer)
        lower.rowconfigure(0, weight=1)
        lower.columnconfigure(0, weight=1)
        tabs = ttk.Notebook(lower)
        tabs.grid(row=0, column=0, sticky="nsew")
        controls_tab = ttk.Frame(tabs, padding=7)
        audit_tab = ttk.Frame(tabs, padding=5)
        tabs.add(controls_tab, text="Frame controls")
        tabs.add(audit_tab, text="Width + bubble audit")
        outer.add(lower, weight=2)

        self._celdra_framing_asset_v81 = tk.StringVar(value="shy")
        self._celdra_framing_scale_v81 = tk.IntVar(value=100)
        self._celdra_framing_x_v81 = tk.IntVar(value=0)
        self._celdra_framing_y_v81 = tk.IntVar(value=0)
        self._celdra_framing_window_v81 = tk.IntVar(value=56)
        self._celdra_framing_style_v81 = tk.StringVar(value="Rounded blue")
        self._celdra_framing_bubble_x_v81 = tk.IntVar(value=4)
        self._celdra_framing_bubble_y_v81 = tk.IntVar(value=3)
        self._celdra_framing_bubble_w_v81 = tk.IntVar(value=52)
        self._celdra_framing_guides_v81 = tk.BooleanVar(value=True)
        self._celdra_framing_metrics_v81 = tk.StringVar(value="Frame metrics unavailable.")
        for variable in (
            self._celdra_framing_scale_v81,
            self._celdra_framing_x_v81,
            self._celdra_framing_y_v81,
            self._celdra_framing_window_v81,
            self._celdra_framing_bubble_x_v81,
            self._celdra_framing_bubble_y_v81,
            self._celdra_framing_bubble_w_v81,
        ):
            variable.trace_add("write", lambda *_args: self.after_idle(self._render_framing_v81))

        controls_tab.columnconfigure(1, weight=1)
        assets = self._available_author_assets_v74()
        self._framing_combo_v81(controls_tab, 0, "Pose / asset", self._celdra_framing_asset_v81, assets)
        self._framing_spin_v81(controls_tab, 1, "Scale %", self._celdra_framing_scale_v81, 10, 500, 5)
        self._framing_spin_v81(controls_tab, 2, "Avatar X", self._celdra_framing_x_v81, -1000, 1000, 5)
        self._framing_spin_v81(controls_tab, 3, "Avatar Y", self._celdra_framing_y_v81, -1000, 1500, 5)
        self._framing_spin_v81(controls_tab, 4, "Viewport width %", self._celdra_framing_window_v81, 10, 99, 1)
        self._framing_combo_v81(
            controls_tab,
            5,
            "Bubble style",
            self._celdra_framing_style_v81,
            list(self.PREVIEW_BUBBLE_STYLES),
        )
        self._framing_spin_v81(controls_tab, 6, "Bubble X %", self._celdra_framing_bubble_x_v81, 0, 90, 1)
        self._framing_spin_v81(controls_tab, 7, "Bubble Y %", self._celdra_framing_bubble_y_v81, 0, 90, 1)
        self._framing_spin_v81(controls_tab, 8, "Bubble width %", self._celdra_framing_bubble_w_v81, 15, 95, 1)
        ttk.Checkbutton(
            controls_tab,
            text="Show headspace, safe-zone, avatar and bubble guides",
            variable=self._celdra_framing_guides_v81,
            command=self._render_framing_v81,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 4))
        ttk.Label(controls_tab, text="Dialogue").grid(row=10, column=0, columnspan=2, sticky="w")
        text = tk.Text(controls_tab, height=4, wrap="word", font=("Segoe UI", 9))
        text.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(2, 5))
        text.insert("1.0", "Test, Test, check check. Can you hear me?")
        text.bind("<KeyRelease>", lambda _event: self._render_framing_v81())
        self._celdra_framing_text_v81 = text

        actions = ttk.Frame(controls_tab)
        actions.grid(row=12, column=0, columnspan=2, sticky="ew")
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        for index, (label, command) in enumerate(
            (
                ("Sync from Preview / Poses", self._sync_framing_from_editor_v81),
                ("Apply to Preview / Poses", self._apply_framing_to_editor_v81),
                ("Preview frozen frame in main", self._preview_framing_main_v81),
                ("Save current as pose preset", self._save_framing_preset_v81),
                ("Render frame + audits", self._render_framing_v81),
                ("Cycle bubble style", self._cycle_bubble_style_v81),
            )
        ):
            ttk.Button(actions, text=label, command=command).grid(
                row=index // 3,
                column=index % 3,
                sticky="ew",
                padx=2,
                pady=2,
            )
        ttk.Label(
            controls_tab,
            textvariable=self._celdra_framing_metrics_v81,
            wraplength=620,
            justify="left",
        ).grid(row=13, column=0, columnspan=2, sticky="ew", pady=(7, 0))

        audit_tab.rowconfigure(0, weight=1)
        audit_tab.columnconfigure(0, weight=1)
        audit = tk.Canvas(
            audit_tab,
            width=1100,
            height=420,
            background="#0a111b",
            highlightthickness=0,
        )
        audit.grid(row=0, column=0, sticky="nsew")
        audit.bind("<Configure>", lambda _event: self.after_idle(self._render_framing_audit_v81))
        self._celdra_framing_audit_canvas_v81 = audit
        self.after_idle(self._sync_framing_from_editor_v81)

    @staticmethod
    def _framing_spin_v81(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        minimum: int,
        maximum: int,
        increment: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Spinbox(parent, textvariable=variable, from_=minimum, to=maximum, increment=increment, width=12).grid(
            row=row, column=1, sticky="ew", pady=2
        )

    def _framing_combo_v81(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: list[str],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        combo.grid(row=row, column=1, sticky="ew", pady=2)
        combo.bind("<<ComboboxSelected>>", lambda _event: self._render_framing_v81())

    def _framing_values_v81(self) -> dict[str, Any]:
        if self._celdra_framing_asset_v81 is None:
            return dict(self._preview_values_v74())
        text = (
            self._celdra_framing_text_v81.get("1.0", "end-1c")
            if self._celdra_framing_text_v81 is not None
            else ""
        )
        return {
            "asset": self._celdra_framing_asset_v81.get(),
            "x": int(self._celdra_framing_x_v81.get()),
            "y": int(self._celdra_framing_y_v81.get()),
            "scale": int(self._celdra_framing_scale_v81.get()),
            "window_percent": int(self._celdra_framing_window_v81.get()),
            "bubble_style": self._celdra_framing_style_v81.get(),
            "bubble_x": int(self._celdra_framing_bubble_x_v81.get()),
            "bubble_y": int(self._celdra_framing_bubble_y_v81.get()),
            "bubble_width": int(self._celdra_framing_bubble_w_v81.get()),
            "text": text,
        }

    def _apply_framing_values_v81(self, values: dict[str, Any], *, update_editor: bool) -> None:
        mappings = (
            (self._celdra_framing_asset_v81, values.get("asset", "shy")),
            (self._celdra_framing_x_v81, values.get("x", 0)),
            (self._celdra_framing_y_v81, values.get("y", 0)),
            (self._celdra_framing_scale_v81, values.get("scale", 100)),
            (self._celdra_framing_window_v81, values.get("window_percent", 56)),
            (self._celdra_framing_style_v81, values.get("bubble_style", "Rounded blue")),
            (self._celdra_framing_bubble_x_v81, values.get("bubble_x", 4)),
            (self._celdra_framing_bubble_y_v81, values.get("bubble_y", 3)),
            (self._celdra_framing_bubble_w_v81, values.get("bubble_width", 52)),
        )
        for variable, value in mappings:
            if variable is not None:
                variable.set(value)
        if self._celdra_framing_text_v81 is not None:
            self._celdra_framing_text_v81.delete("1.0", "end")
            self._celdra_framing_text_v81.insert("1.0", str(values.get("text") or ""))
        if update_editor:
            self._apply_framing_to_editor_v81()
        self._render_framing_v81()

    def _sync_framing_from_editor_v81(self) -> None:
        self._apply_framing_values_v81(self._preview_values_v74(), update_editor=False)

    def _apply_framing_to_editor_v81(self) -> None:
        values = self._framing_values_v81()
        mappings = (
            (self._celdra_studio_pose_v72, values["asset"]),
            (self._celdra_studio_x_v72, values["x"]),
            (self._celdra_studio_y_v72, values["y"]),
            (self._celdra_studio_scale_v72, values["scale"]),
            (self._celdra_studio_stage_v72, values["window_percent"]),
            (self._celdra_studio_bubble_style_v72, values["bubble_style"]),
            (self._celdra_studio_bubble_x_v72, values["bubble_x"]),
            (self._celdra_studio_bubble_y_v72, values["bubble_y"]),
            (self._celdra_studio_bubble_w_v72, values["bubble_width"]),
        )
        for variable, value in mappings:
            if variable is not None:
                variable.set(value)
        if self._celdra_studio_text_v72 is not None:
            self._celdra_studio_text_v72.delete("1.0", "end")
            self._celdra_studio_text_v72.insert("1.0", values["text"])
        self._render_author_preview_v74()

    def _save_framing_preset_v81(self) -> None:
        self._apply_framing_to_editor_v81()
        self._save_pose_preset_v77()

    def _cycle_bubble_style_v81(self) -> None:
        variable = self._celdra_framing_style_v81
        if variable is None:
            return
        styles = list(self.PREVIEW_BUBBLE_STYLES)
        try:
            index = styles.index(variable.get())
        except ValueError:
            index = -1
        variable.set(styles[(index + 1) % len(styles)])
        self._render_framing_v81()

    # ------------------------------------------------------------------
    # Framing renderer and measurable safe areas.
    # ------------------------------------------------------------------
    def _bubble_bounds_v81(
        self,
        stage_width: int,
        height: int,
        values: dict[str, Any],
        text: str,
    ) -> tuple[int, int, int, int]:
        x = round(stage_width * max(0, min(90, int(values.get("bubble_x") or 4))) / 100.0)
        y = round(height * max(0, min(90, int(values.get("bubble_y") or 3))) / 100.0)
        width = round(stage_width * max(15, min(95, int(values.get("bubble_width") or 52))) / 100.0)
        width = max(140, min(max(140, stage_width - x - 8), width))
        estimated_lines = max(1, math.ceil(max(1, len(text)) / max(18, width // 8)))
        style = str(values.get("bubble_style") or "Rounded blue")
        height_px = 58 if style == "Caption ribbon" else max(68, min(220, 42 + estimated_lines * 18))
        return x, y, x + width, min(height - 8, y + height_px)

    @staticmethod
    def _intersection_area_v81(
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
    ) -> int:
        left = max(first[0], second[0])
        top = max(first[1], second[1])
        right = min(first[2], second[2])
        bottom = min(first[3], second[3])
        return max(0, right - left) * max(0, bottom - top)

    def _fit_photo_v81(self, photo: tk.PhotoImage, maximum_width: int, maximum_height: int) -> tk.PhotoImage:
        divisor = max(
            1,
            math.ceil(photo.width() / max(1, maximum_width)),
            math.ceil(photo.height() / max(1, maximum_height)),
        )
        return photo if divisor <= 1 else photo.subsample(divisor, divisor)

    def _render_framing_v81(self) -> None:
        canvas = self._celdra_framing_canvas_v81
        if canvas is None or self._celdra_framing_asset_v81 is None:
            return
        values = self._framing_values_v81()
        width = max(760, canvas.winfo_width())
        height = max(430, canvas.winfo_height())
        stage_width = max(180, round(width * max(10, min(99, int(values["window_percent"]))) / 100.0))
        canvas.delete("all")
        self._celdra_framing_refs_v81.clear()
        canvas.create_rectangle(0, 0, stage_width, height, fill="#081321", outline="")
        canvas.create_rectangle(stage_width, 0, width, height, fill="#10151d", outline="")
        canvas.create_rectangle(0, 0, stage_width, 43, fill="#0d2035", outline="")
        canvas.create_text(
            10,
            8,
            text=f"FROZEN CELDRA VIEWPORT • {values['window_percent']}%",
            anchor="nw",
            fill="#d9f1ff",
            font=("Segoe UI", 10, "bold"),
        )
        canvas.create_text(
            stage_width + 10,
            10,
            text="PRODUCTION CONSOLE WIDTH",
            anchor="nw",
            fill="#36ce87",
            font=("Consolas", 9, "bold"),
        )

        photo = self._preview_photo_for_asset_v74(
            str(values["asset"]),
            max(10, min(500, int(values["scale"]))),
        )
        avatar_bounds = (0, 0, 0, 0)
        if photo is not None:
            self._celdra_framing_refs_v81.append(photo)
            center_x = stage_width // 2 + int(values["x"])
            bottom_y = height - 16 + int(values["y"])
            avatar_bounds = (
                center_x - photo.width() // 2,
                bottom_y - photo.height(),
                center_x + photo.width() // 2,
                bottom_y,
            )
            canvas.create_image(center_x, bottom_y, image=photo, anchor="s")

        dialogue = str(values.get("text") or "")
        bubble_bounds = self._bubble_bounds_v81(stage_width, height, values, dialogue)
        if dialogue:
            self._draw_bubble_style_v81(canvas, bubble_bounds, str(values["bubble_style"]), dialogue)

        canvas.create_rectangle(stage_width, 0, width, height, fill="#10151d", outline="")
        canvas.create_line(stage_width, 0, stage_width, height, fill="#78b9ea", width=2)
        canvas.create_text(
            stage_width + 10,
            34,
            text="Stage content is clipped at this sash.",
            anchor="nw",
            fill="#557c9e",
            font=("Consolas", 8),
        )

        overlap = self._intersection_area_v81(avatar_bounds, bubble_bounds) if dialogue else 0
        headspace = avatar_bounds[1] - 43 if photo is not None else 0
        bottom_margin = height - avatar_bounds[3] if photo is not None else 0
        if self._celdra_framing_guides_v81 is None or self._celdra_framing_guides_v81.get():
            safe_top = 43 + round((height - 43) * 0.12)
            canvas.create_line(0, safe_top, stage_width, safe_top, fill="#efc84a", dash=(6, 5))
            canvas.create_text(
                8,
                safe_top + 3,
                text="12% HEADSPACE GUIDE",
                anchor="nw",
                fill="#efc84a",
                font=("Consolas", 8, "bold"),
            )
            if photo is not None:
                canvas.create_rectangle(*avatar_bounds, outline="#43d9ff", width=2, dash=(4, 3))
            if dialogue:
                canvas.create_rectangle(
                    *bubble_bounds,
                    outline="#ffcb54" if overlap == 0 else "#ff5964",
                    width=2,
                    dash=(4, 3),
                )
            canvas.create_rectangle(
                8,
                51,
                max(10, stage_width - 8),
                max(60, height - 10),
                outline="#35536f",
                dash=(2, 5),
            )
        metric = (
            f"Avatar {photo.width() if photo else 0}×{photo.height() if photo else 0}px • "
            f"headspace {headspace}px • bottom margin {bottom_margin}px • "
            f"bubble/avatar overlap {overlap}px² • "
            f"{'OVERLAP: adjust bubble or pose' if overlap else 'clear separation'}"
        )
        if self._celdra_framing_metrics_v81 is not None:
            self._celdra_framing_metrics_v81.set(metric)
        canvas.create_text(
            10,
            height - 10,
            text=metric,
            anchor="sw",
            fill="#ff7380" if overlap else "#83c7f1",
            font=("Consolas", 8, "bold"),
        )
        self._render_framing_audit_v81()

    def _render_framing_audit_v81(self) -> None:
        canvas = self._celdra_framing_audit_canvas_v81
        if canvas is None or self._celdra_framing_asset_v81 is None:
            return
        values = self._framing_values_v81()
        width = max(860, canvas.winfo_width())
        height = max(390, canvas.winfo_height())
        canvas.delete("all")
        self._celdra_framing_audit_refs_v81.clear()
        local_refs: list[tk.PhotoImage] = []
        card_gap = 8
        card_width = max(150, (width - card_gap * (len(self.AUDIT_WIDTHS) + 1)) // len(self.AUDIT_WIDTHS))
        card_height = max(150, height // 2 - 22)
        source = self._preview_photo_for_asset_v74(
            str(values["asset"]),
            max(10, min(500, int(values["scale"]))),
        )
        for index, percent in enumerate(self.AUDIT_WIDTHS):
            x0 = card_gap + index * (card_width + card_gap)
            y0 = 8
            x1 = x0 + card_width
            y1 = y0 + card_height
            stage = max(50, round(card_width * percent / 100.0))
            canvas.create_rectangle(x0, y0, x1, y1, fill="#10151d", outline="#35536f")
            canvas.create_rectangle(x0, y0, x0 + stage, y1, fill="#081321", outline="")
            if source is not None:
                display = self._fit_photo_v81(source, max(24, stage - 12), max(36, card_height - 38))
                local_refs.append(display)
                canvas.create_image(x0 + stage // 2, y1 - 12, image=display, anchor="s")
            bx = x0 + round(stage * int(values["bubble_x"]) / 100.0)
            by = y0 + round(card_height * int(values["bubble_y"]) / 100.0)
            bw = max(35, round(stage * int(values["bubble_width"]) / 100.0))
            canvas.create_rectangle(
                bx,
                by,
                min(x0 + stage - 3, bx + bw),
                min(y1 - 3, by + 34),
                outline="#ffcb54",
                dash=(2, 2),
            )
            canvas.create_line(x0 + stage, y0, x0 + stage, y1, fill="#78b9ea")
            canvas.create_text(
                x0 + 6,
                y0 + 5,
                text=f"{percent}% viewport",
                anchor="nw",
                fill="#d9f1ff",
                font=("Consolas", 8, "bold"),
            )

        gallery_top = card_height + 32
        styles = list(self.PREVIEW_BUBBLE_STYLES)
        columns = 5
        gallery_width = max(150, (width - 16 * (columns + 1)) // columns)
        gallery_height = 74
        for index, style in enumerate(styles):
            column = index % columns
            row = index // columns
            x = 16 + column * (gallery_width + 16)
            y = gallery_top + row * (gallery_height + 12)
            self._draw_bubble_style_v81(
                canvas,
                (x, y, x + gallery_width, y + gallery_height),
                style,
                style,
                compact=True,
            )
        self._celdra_framing_audit_refs_v81.extend(local_refs)

    # ------------------------------------------------------------------
    # Additional bubble styles, shared by embedded, framing and main previews.
    # ------------------------------------------------------------------
    def _draw_bubble_style_v81(
        self,
        canvas: tk.Canvas,
        bounds: tuple[int, int, int, int],
        style: str,
        text: str,
        *,
        compact: bool = False,
    ) -> None:
        x, y, x2, y2 = bounds
        width = max(40, x2 - x)
        font_size = 8 if compact else 10
        tx, ty = x + 13, y + 12
        text_fill = "#071426"
        font: tuple[Any, ...] = ("Segoe UI", font_size, "bold")

        if style == "Terminal green":
            canvas.create_rectangle(x, y, x2, y2, fill="#071812", outline="#36ce87", width=2)
            canvas.create_line(x + 8, y + 15, x2 - 8, y + 15, fill="#12865a", dash=(3, 4))
            text_fill, font, ty = "#78efaf", ("Consolas", font_size, "bold"), y + 22
        elif style == "Manga white":
            canvas.create_polygon(
                x + 8,
                y,
                x2 - 18,
                y,
                x2,
                y + 13,
                x2 - 8,
                y2 - 15,
                x2 - 38,
                y2 - 12,
                x2 - 53,
                y2 + 7,
                x2 - 66,
                y2 - 13,
                x + 10,
                y2 - 7,
                x,
                y2 - 22,
                fill="#ffffff",
                outline="#071426",
                width=3,
            )
        elif style == "Minimal dark":
            canvas.create_rectangle(x, y, x2, y2, fill="#101a28", outline="#78b9ea", width=2)
            canvas.create_polygon(
                x2 - 48,
                y2,
                x2 - 28,
                y2,
                x2 - 39,
                y2 + 11,
                fill="#101a28",
                outline="#78b9ea",
            )
            text_fill, font = "#e2f5ff", ("Segoe UI", font_size)
        elif style == "Soft cyan glass":
            canvas.create_rectangle(
                x,
                y,
                x2,
                y2,
                fill="#16394a",
                outline="#66e4ff",
                width=2,
                stipple="gray25",
            )
            canvas.create_line(x + 10, y + 7, x2 - 10, y + 7, fill="#9cf3ff")
            text_fill = "#e5fbff"
        elif style == "Pixel terminal":
            canvas.create_rectangle(x + 4, y + 4, x2, y2, fill="#050b0a", outline="#0f4e39")
            canvas.create_rectangle(x, y, x2 - 4, y2 - 4, fill="#06130f", outline="#42f59e", width=2)
            for px, py in ((x, y), (x2 - 4, y), (x, y2 - 4), (x2 - 4, y2 - 4)):
                canvas.create_rectangle(px - 2, py - 2, px + 5, py + 5, fill="#42f59e", outline="")
            text_fill, font = "#a8ffd0", ("Fixedsys", font_size)
        elif style == "Angular HUD":
            canvas.create_polygon(
                x + 18,
                y,
                x2 - 10,
                y,
                x2,
                y + 10,
                x2,
                y2 - 20,
                x2 - 20,
                y2,
                x + 8,
                y2,
                x,
                y2 - 8,
                x,
                y + 18,
                fill="#0b2030",
                outline="#4dc6ff",
                width=2,
            )
            canvas.create_line(x + 12, y + 8, x2 - 24, y + 8, fill="#1d759d")
            text_fill, font, tx, ty = "#d8f5ff", ("Consolas", font_size, "bold"), x + 16, y + 16
        elif style == "Caption ribbon":
            mid = (y + y2) // 2
            ribbon_y = mid - 24
            canvas.create_polygon(
                x,
                ribbon_y,
                x2 - 18,
                ribbon_y,
                x2,
                mid,
                x2 - 18,
                mid + 24,
                x,
                mid + 24,
                x + 12,
                mid,
                fill="#10243b",
                outline="#78b9ea",
                width=2,
            )
            text_fill, font, tx, ty = "#e2f5ff", ("Segoe UI", font_size, "bold"), x + 20, ribbon_y + 13
        elif style == "Cloud comic":
            fill = "#f9fdff"
            radius = max(12, min(24, (y2 - y) // 4))
            canvas.create_oval(x, y + radius, x + radius * 2, y2, fill=fill, outline="#28506f", width=2)
            canvas.create_oval(x + radius, y, x + radius * 4, y2, fill=fill, outline="#28506f", width=2)
            canvas.create_oval(x2 - radius * 4, y, x2 - radius, y2, fill=fill, outline="#28506f", width=2)
            canvas.create_oval(x2 - radius * 2, y + radius, x2, y2, fill=fill, outline="#28506f", width=2)
            canvas.create_rectangle(x + radius, y + radius, x2 - radius, y2 - 2, fill=fill, outline="")
            canvas.create_polygon(
                x2 - 58,
                y2 - 4,
                x2 - 34,
                y2 - 4,
                x2 - 46,
                y2 + 13,
                fill=fill,
                outline="#28506f",
            )
            tx, ty = x + 18, y + 18
        else:
            canvas.create_rectangle(x + 5, y + 6, x2 + 3, y2 + 4, fill="#16375f", outline="")
            canvas.create_rectangle(x, y, x2, y2, fill="#f4fbff", outline="#78b9ea", width=3)
            canvas.create_polygon(
                x2 - 54,
                y2,
                x2 - 30,
                y2,
                x2 - 42,
                y2 + 14,
                fill="#f4fbff",
                outline="#78b9ea",
            )

        canvas.create_text(
            tx,
            ty,
            text=text,
            anchor="nw",
            width=max(40, width - (tx - x) - 12),
            fill=text_fill,
            font=font,
            justify="left",
        )

    def _draw_preview_bubble_v74(
        self,
        canvas: tk.Canvas,
        stage_width: int,
        height: int,
        data: dict[str, Any],
        text: str,
    ) -> None:
        bounds = self._bubble_bounds_v81(stage_width, height, data, text)
        self._draw_bubble_style_v81(
            canvas,
            bounds,
            str(data.get("bubble_style") or "Rounded blue"),
            text,
        )

    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = self._celdra_speech_canvas_v63
        if bubble is None:
            return
        data = dict(self._celdra_main_preview_values_v81 or {})
        if not data:
            data = self._preview_values_v74()
        bubble_x = max(0, min(90, int(data.get("bubble_x") or 4)))
        bubble_y = max(0, min(90, int(data.get("bubble_y") or 3)))
        bubble_width = max(15, min(95, int(data.get("bubble_width") or 52)))
        estimated_pixels = max(180, round(520 * bubble_width / 100.0))
        lines = max(1, math.ceil(max(1, len(str(text))) / max(18, estimated_pixels // 8)))
        style = str(data.get("bubble_style") or "Rounded blue")
        height = 64 if style == "Caption ribbon" else max(78, min(230, 44 + lines * 20))
        bubble.place(
            relx=bubble_x / 100.0,
            rely=bubble_y / 100.0,
            anchor="nw",
            relwidth=bubble_width / 100.0,
            height=height,
        )
        bubble.update_idletasks()
        width = max(180, bubble.winfo_width())
        bubble.delete("all")
        self._draw_bubble_style_v81(bubble, (4, 4, width - 8, height - 16), style, str(text))
        try:
            bubble.tkraise()
        except tk.TclError:
            try:
                bubble.tk.call("raise", bubble._w)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Freeze main-preview layout before showing the pose and bubble.
    # ------------------------------------------------------------------
    def _preview_values_in_main_v77(self, values: dict[str, Any]) -> None:
        data = dict(values)
        if not str(data.get("asset") or "").strip():
            data["asset"] = self._celdra_author_preview_asset_v74 or "shy"
        self._celdra_main_preview_values_v81 = data
        super()._preview_values_in_main_v77(data)
        fraction = max(0.10, min(0.99, int(data.get("window_percent") or 56) / 100.0))
        self._cancel_stage_animation_v54()
        self._set_stage_fraction_v54(fraction)

        def settle() -> None:
            self._redraw_celdra_avatar_v50()
            dialogue = str(data.get("text") or "")
            if dialogue:
                self._show_speech_bubble_v58(dialogue)
            self._draw_main_framing_guides_v81()

        self.after_idle(settle)

    def _preview_framing_main_v81(self) -> None:
        self._preview_values_in_main_v77(self._framing_values_v81())

    def _draw_main_framing_guides_v81(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        try:
            canvas.delete("v81_main_guides")
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
            safe_top = 43 + round((height - 43) * 0.12)
            canvas.create_line(
                0,
                safe_top,
                width,
                safe_top,
                fill="#efc84a",
                dash=(6, 5),
                tags="v81_main_guides",
            )
            canvas.create_text(
                8,
                safe_top + 3,
                text="12% HEADSPACE",
                anchor="nw",
                fill="#efc84a",
                font=("Consolas", 8, "bold"),
                tags="v81_main_guides",
            )
            canvas.create_rectangle(
                6,
                49,
                width - 6,
                height - 8,
                outline="#35536f",
                dash=(2, 5),
                tags="v81_main_guides",
            )
        except tk.TclError:
            pass

    def _prepare_first_run_surface_v51(self) -> None:
        self._celdra_main_preview_values_v81 = None
        super()._prepare_first_run_surface_v51()


def main() -> int:
    app = PublicFragmenterAppV81()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

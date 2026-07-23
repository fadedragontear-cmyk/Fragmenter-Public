#!/usr/bin/env python3
"""V74: full Celdra authoring workspace with embedded preview and event sequencing."""
from __future__ import annotations

import json
import math
import time
import tkinter as tk
from fractions import Fraction
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from celdra_authoring_project_v1 import (
    EVENT_ACTIONS,
    KNOWN_CONDITIONS,
    normalize_event,
    normalize_events,
    project_payload,
    read_project,
    timeline_event_to_row,
    write_bundle,
    write_project,
)
from celdra_emote_classifier_v1 import (
    definitions_from_manifest,
    load_manifest,
    upsert_definition,
)
from celdra_startup_timeline_v8 import FIRST_RUN_AFTER_CCSF
from fragmenter_public_gui_v73 import PublicFragmenterAppV73


class PublicFragmenterAppV74(PublicFragmenterAppV73):
    """Turn Celdra Test into a self-contained authoring and export workspace."""

    AUTHOR_PROJECT_RELATIVE = "authoring/celdra_authoring_project_v1.json"
    PREVIEW_BUBBLE_STYLES = (
        "Rounded blue",
        "Terminal green",
        "Manga white",
        "Minimal dark",
    )

    def __init__(self) -> None:
        self._celdra_author_events_v74: list[dict[str, Any]] = [
            timeline_event_to_row(event, index)
            for index, event in enumerate(FIRST_RUN_AFTER_CCSF)
        ]
        self._celdra_author_event_rows_v74: dict[str, dict[str, Any]] = {}
        self._celdra_author_event_serial_v74 = len(self._celdra_author_events_v74)
        self._celdra_author_after_v74: str | None = None
        self._celdra_author_motion_after_v74: str | None = None
        self._celdra_author_preview_after_v74: str | None = None
        self._celdra_author_active_branch_v74 = ""
        self._celdra_author_console_lines_v74: list[str] = []
        self._celdra_author_preview_refs_v74: list[tk.PhotoImage] = []
        self._celdra_author_preview_asset_v74 = "shy"
        self._celdra_author_preview_text_v74 = ""
        self._celdra_author_preview_visible_v74 = True
        self._celdra_author_preview_canvas_v74: tk.Canvas | None = None
        self._celdra_author_event_tree_v74: ttk.Treeview | None = None
        self._celdra_author_project_status_v74: tk.StringVar | None = None
        self._celdra_author_project_path_v74: Path | None = None
        self._celdra_crop_asset_map_v74: dict[str, dict[str, Any]] = {}
        self._celdra_crop_asset_var_v74: tk.StringVar | None = None
        self._celdra_author_asset_values_v74: list[str] = []

        self._celdra_event_id_v74: tk.StringVar | None = None
        self._celdra_event_at_v74: tk.IntVar | None = None
        self._celdra_event_duration_v74: tk.IntVar | None = None
        self._celdra_event_sequence_v74: tk.StringVar | None = None
        self._celdra_event_action_v74: tk.StringVar | None = None
        self._celdra_event_speaker_v74: tk.StringVar | None = None
        self._celdra_event_asset_v74: tk.StringVar | None = None
        self._celdra_event_x_v74: tk.IntVar | None = None
        self._celdra_event_y_v74: tk.IntVar | None = None
        self._celdra_event_scale_v74: tk.IntVar | None = None
        self._celdra_event_window_v74: tk.IntVar | None = None
        self._celdra_event_bubble_style_v74: tk.StringVar | None = None
        self._celdra_event_bubble_x_v74: tk.IntVar | None = None
        self._celdra_event_bubble_y_v74: tk.IntVar | None = None
        self._celdra_event_bubble_width_v74: tk.IntVar | None = None
        self._celdra_event_condition_v74: tk.StringVar | None = None
        self._celdra_event_true_v74: tk.StringVar | None = None
        self._celdra_event_false_v74: tk.StringVar | None = None
        self._celdra_event_text_v74: tk.Text | None = None
        self._celdra_event_notes_v74: tk.Text | None = None
        self._celdra_event_speed_v74: tk.DoubleVar | None = None
        self._celdra_event_branch_override_v74: tk.StringVar | None = None

        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Authoring Workspace")
        self._celdra_author_project_path_v74 = (
            self.celdra_asset_root_v50 / self.AUTHOR_PROJECT_RELATIVE
        )

    # ------------------------------------------------------------------
    # Egg corruption: text only. No haze, panels, lines, nodes, rings or stipple.
    # ------------------------------------------------------------------
    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        level = int(getattr(self, "_celdra_glitch_level_v61", 0) or 0)
        if level <= 0:
            return
        phase = int(getattr(self, "_celdra_glitch_phase_v61", 0) or 0)
        alarm = bool(getattr(self, "_celdra_instability_red_v70", False))
        tag = "v74_text_only_corruption"
        for old_tag in (
            "v68_green_corruption_bg",
            "v70_white_corruption_haze",
            "v74_text_only_corruption",
        ):
            try:
                canvas.delete(old_tag)
            except tk.TclError:
                pass

        terms = (
            "AURA",
            "INFECTION",
            "MUTATION",
            "QUARANTINE",
            "SERENIAL",
            "CELDRA",
            "FRAGMENT",
            "CCSF",
        )
        green = ("#0a3b26", "#0d5734", "#117044", "#168956", "#1ca969", "#35c982")
        red = ("#4a0b13", "#681019", "#85151f", "#a61c28", "#cf2936", "#ef4b55")
        palette = red if alarm else green
        density = 11 + level * 10
        usable_width = max(80, width - 30)
        usable_height = max(80, height - 96)

        for slot in range(density):
            term = terms[(slot * 5 + phase // 3 + level) % len(terms)]
            mode = (slot + phase) % 6
            binary = "".join(f"{ord(character):08b}" for character in term)
            if mode == 0:
                text = term
            elif mode == 1:
                text = term[::-1]
            elif mode == 2:
                start = (phase * 7 + slot * 11) % max(1, len(binary))
                text = (binary[start:] + binary[:start])[: 12 + level * 8]
            elif mode == 3:
                text = f"{term[: max(1, len(term) - level)]}//{(phase * 29 + slot * 17) & 0xFF:02X}"
            elif mode == 4:
                replacements = "01?/\\ΔΞ#"
                text = "".join(
                    character
                    if (index + slot + phase) % max(2, 6 - level)
                    else replacements[(index + slot + phase) % len(replacements)]
                    for index, character in enumerate(term)
                )
            else:
                text = " ".join(f"{ord(character):02X}" for character in term)

            x = 15 + ((slot * 101 + phase * (3 + slot % 7)) % usable_width)
            y = 48 + ((slot * 67 + phase * (4 + slot % 9)) % usable_height)
            size = 7 + ((slot * 3 + phase + level) % (5 + level))
            try:
                canvas.create_text(
                    x,
                    y,
                    text=text,
                    anchor="center",
                    fill=palette[(slot + phase) % len(palette)],
                    font=("Consolas", size, "bold" if slot % 5 == 0 else "normal"),
                    tags=tag,
                )
            except tk.TclError:
                continue
        try:
            canvas.tag_lower(tag)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Celdra Test top-level subtabs.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        frame = self.tabs.get("Celdra Test")
        if frame is None:
            return

        for child in frame.winfo_children():
            try:
                child.grid_remove()
            except tk.TclError:
                pass
            try:
                child.pack_forget()
            except tk.TclError:
                pass

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        notebook = ttk.Notebook(frame)
        notebook.grid(row=0, column=0, sticky="nsew")
        self._celdra_author_notebook_v74 = notebook

        preview_tab = ttk.Frame(notebook, padding=6)
        timeline_tab = ttk.Frame(notebook, padding=6)
        crop_tab = ttk.Frame(notebook, padding=6)
        project_tab = ttk.Frame(notebook, padding=6)
        notebook.add(preview_tab, text="Preview / Poses")
        notebook.add(timeline_tab, text="Events / Sequences")
        notebook.add(crop_tab, text="Crop / Assets")
        notebook.add(project_tab, text="Save / Export")

        self._build_author_preview_tab_v74(preview_tab)
        self._build_author_timeline_tab_v74(timeline_tab)
        self._build_author_crop_tab_v74(crop_tab)
        self._build_author_project_tab_v74(project_tab)
        self._refresh_author_event_tree_v74()
        self.after_idle(self._render_author_preview_v74)

    # ------------------------------------------------------------------
    # Embedded preview and pose controls.
    # ------------------------------------------------------------------
    def _build_author_preview_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        paned = ttk.Panedwindow(parent, orient="horizontal")
        paned.grid(row=0, column=0, sticky="nsew")

        preview_frame = ttk.LabelFrame(paned, text="Embedded Celdra stage preview", padding=4)
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        canvas = tk.Canvas(
            preview_frame,
            width=820,
            height=560,
            background="#081321",
            highlightthickness=1,
            highlightbackground="#35536f",
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.bind("<Configure>", lambda _event: self.after_idle(self._render_author_preview_v74))
        self._celdra_author_preview_canvas_v74 = canvas
        paned.add(preview_frame, weight=5)

        controls = ttk.LabelFrame(paned, text="Preview controls", padding=5)
        controls.rowconfigure(0, weight=1)
        controls.columnconfigure(0, weight=1)
        control_tabs = ttk.Notebook(controls)
        control_tabs.grid(row=0, column=0, sticky="nsew")
        paned.add(controls, weight=2)

        pose_tab = ttk.Frame(control_tabs, padding=7)
        bubble_tab = ttk.Frame(control_tabs, padding=7)
        shy_tab = ttk.Frame(control_tabs, padding=7)
        asset_tab = ttk.Frame(control_tabs, padding=7)
        control_tabs.add(pose_tab, text="Pose")
        control_tabs.add(bubble_tab, text="Bubble")
        control_tabs.add(shy_tab, text="Shy slide")
        control_tabs.add(asset_tab, text="Assets")

        poses = self._available_pose_names_v74()
        self._celdra_studio_pose_v72 = tk.StringVar(value="shy" if "shy" in poses else (poses[0] if poses else "neutral"))
        self._celdra_studio_scale_v72 = tk.IntVar(value=100)
        self._celdra_studio_x_v72 = tk.IntVar(value=0)
        self._celdra_studio_y_v72 = tk.IntVar(value=0)
        self._celdra_studio_stage_v72 = tk.IntVar(value=56)
        self._celdra_studio_bubble_x_v72 = tk.IntVar(value=4)
        self._celdra_studio_bubble_y_v72 = tk.IntVar(value=3)
        self._celdra_studio_bubble_w_v72 = tk.IntVar(value=52)
        self._celdra_studio_bubble_style_v72 = tk.StringVar(value=self.PREVIEW_BUBBLE_STYLES[0])

        self._labeled_combo_v74(pose_tab, 0, "Pose", self._celdra_studio_pose_v72, poses)
        self._labeled_spin_v74(pose_tab, 1, "Scale %", self._celdra_studio_scale_v72, 10, 500, 5)
        self._labeled_spin_v74(pose_tab, 2, "Avatar X", self._celdra_studio_x_v72, -600, 600, 5)
        self._labeled_spin_v74(pose_tab, 3, "Avatar Y", self._celdra_studio_y_v72, -600, 900, 5)
        self._labeled_spin_v74(pose_tab, 4, "Viewport %", self._celdra_studio_stage_v72, 10, 99, 1)
        ttk.Label(pose_tab, text="Speech / observation").grid(row=5, column=0, columnspan=2, sticky="w", pady=(7, 2))
        text_widget = tk.Text(
            pose_tab,
            height=7,
            wrap="word",
            background="#101a28",
            foreground="#e2f5ff",
            insertbackground="#a9dcff",
            font=("Segoe UI", 9),
        )
        text_widget.grid(row=6, column=0, columnspan=2, sticky="nsew")
        text_widget.insert("1.0", "Test, Test, check check. Can you hear me?")
        self._celdra_studio_text_v72 = text_widget
        pose_tab.rowconfigure(6, weight=1)
        pose_tab.columnconfigure(1, weight=1)
        ttk.Button(pose_tab, text="Render pose here", command=self._preview_pose_embedded_v74).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(7, 0)
        )

        self._labeled_combo_v74(
            bubble_tab,
            0,
            "Style",
            self._celdra_studio_bubble_style_v72,
            self.PREVIEW_BUBBLE_STYLES,
        )
        self._labeled_spin_v74(bubble_tab, 1, "Bubble X %", self._celdra_studio_bubble_x_v72, 0, 90, 1)
        self._labeled_spin_v74(bubble_tab, 2, "Bubble Y %", self._celdra_studio_bubble_y_v72, 0, 90, 1)
        self._labeled_spin_v74(bubble_tab, 3, "Width %", self._celdra_studio_bubble_w_v72, 15, 90, 1)
        for row, style in enumerate(self.PREVIEW_BUBBLE_STYLES, start=4):
            ttk.Button(
                bubble_tab,
                text=f"Audition {style}",
                command=lambda selected=style: self._audition_preview_bubble_v74(selected),
            ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(bubble_tab, text="Hide bubble", command=self._hide_preview_bubble_v74).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(7, 0)
        )
        bubble_tab.columnconfigure(1, weight=1)

        self._celdra_shy_start_x_v72 = tk.IntVar(value=0)
        self._celdra_shy_start_y_v72 = tk.IntVar(value=620)
        self._celdra_shy_end_x_v72 = tk.IntVar(value=0)
        self._celdra_shy_end_y_v72 = tk.IntVar(value=0)
        self._celdra_shy_scale_v72 = tk.IntVar(value=100)
        self._celdra_shy_duration_v72 = tk.IntVar(value=12_000)
        self._celdra_shy_stage_v72 = tk.IntVar(value=50)
        for row, (label, variable, minimum, maximum, increment) in enumerate(
            (
                ("Start X", self._celdra_shy_start_x_v72, -600, 600, 5),
                ("Start Y", self._celdra_shy_start_y_v72, -600, 1200, 10),
                ("End X", self._celdra_shy_end_x_v72, -600, 600, 5),
                ("End Y", self._celdra_shy_end_y_v72, -600, 900, 5),
                ("Scale %", self._celdra_shy_scale_v72, 10, 500, 5),
                ("Duration ms", self._celdra_shy_duration_v72, 250, 60_000, 250),
                ("Viewport %", self._celdra_shy_stage_v72, 10, 99, 1),
            )
        ):
            self._labeled_spin_v74(shy_tab, row, label, variable, minimum, maximum, increment)
        ttk.Button(shy_tab, text="Preview Shy slide here", command=self._preview_shy_embedded_v74).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        shy_tab.columnconfigure(1, weight=1)

        self._celdra_author_asset_values_v74 = self._available_author_assets_v74()
        self._celdra_author_asset_var_v74 = tk.StringVar(
            value=self._celdra_author_asset_values_v74[0] if self._celdra_author_asset_values_v74 else ""
        )
        self._labeled_combo_v74(
            asset_tab,
            0,
            "Image / pose",
            self._celdra_author_asset_var_v74,
            self._celdra_author_asset_values_v74,
            readonly=False,
        )
        ttk.Button(asset_tab, text="Render selected asset", command=self._preview_asset_embedded_v74).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(7, 2)
        )
        ttk.Button(asset_tab, text="Refresh manifest/assets", command=self._refresh_author_assets_v74).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=2
        )
        ttk.Button(asset_tab, text="Clear mock console", command=self._clear_author_console_v74).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=2
        )
        asset_tab.columnconfigure(1, weight=1)

    @staticmethod
    def _labeled_spin_v74(
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
            width=12,
        ).grid(row=row, column=1, sticky="ew", pady=2)

    @staticmethod
    def _labeled_combo_v74(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: list[str] | tuple[str, ...],
        *,
        readonly: bool = True,
    ) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly" if readonly else "normal",
        )
        combo.grid(row=row, column=1, sticky="ew", pady=2)
        return combo

    def _available_pose_names_v74(self) -> list[str]:
        rows = definitions_from_manifest(load_manifest(self.celdra_asset_root_v50))
        names = {
            str(row.get("state") or row.get("pose") or row.get("id") or "").casefold()
            for row in rows
            if row.get("state") or row.get("pose") or row.get("id")
        }
        return sorted(names)

    def _available_author_assets_v74(self) -> list[str]:
        values = list(self._available_pose_names_v74())
        assets = (getattr(self, "celdra_asset_inventory_v50", {}) or {}).get("assets") or []
        for row in assets:
            suffix = str(row.get("suffix") or "").casefold()
            relative = str(row.get("relative_path") or "")
            if relative and suffix in {".png", ".gif"}:
                values.append(f"asset:{relative}")
        return sorted(dict.fromkeys(values))

    def _pose_definition_v74(self, name: str) -> dict[str, Any] | None:
        folded = str(name or "").casefold().strip()
        for row in definitions_from_manifest(load_manifest(self.celdra_asset_root_v50)):
            candidates = {
                str(row.get("state") or "").casefold(),
                str(row.get("pose") or "").casefold(),
                str(row.get("id") or "").casefold(),
            }
            if folded in candidates:
                return row
        return None

    def _scale_photo_percent_v74(self, image: tk.PhotoImage, percent: int) -> tk.PhotoImage:
        percent = max(10, min(500, int(percent)))
        target_width = max(1, round(image.width() * percent / 100.0))
        target_height = max(1, round(image.height() * percent / 100.0))
        maximum = max(target_width, target_height)
        if maximum > 1800:
            factor = 1800 / maximum
            target_width = max(1, round(target_width * factor))
            target_height = max(1, round(target_height * factor))
        ratio = Fraction(target_width, max(1, image.width())).limit_denominator(24)
        result = image.zoom(max(1, ratio.numerator), max(1, ratio.numerator))
        if ratio.denominator > 1:
            result = result.subsample(ratio.denominator, ratio.denominator)
        if result.height() > target_height * 1.12:
            ratio_y = Fraction(target_height, max(1, result.height())).limit_denominator(24)
            result = result.zoom(max(1, ratio_y.numerator), max(1, ratio_y.numerator))
            if ratio_y.denominator > 1:
                result = result.subsample(ratio_y.denominator, ratio_y.denominator)
        return result

    def _preview_photo_for_asset_v74(self, asset: str, scale: int) -> tk.PhotoImage | None:
        definition = self._pose_definition_v74(asset)
        source_image: tk.PhotoImage
        crop_image: tk.PhotoImage
        try:
            if definition is not None:
                source = self.celdra_asset_root_v50 / str(definition.get("source") or "")
                source_image = tk.PhotoImage(file=str(source))
                crop = definition.get("crop") if isinstance(definition.get("crop"), dict) else {}
                crop_image = self._crop_photo_v52(
                    source_image,
                    {
                        "x": int(crop.get("x") or 0),
                        "y": int(crop.get("y") or 0),
                        "width": int(crop.get("width") or 1),
                        "height": int(crop.get("height") or 1),
                    },
                )
            else:
                relative = str(asset or "")
                if relative.startswith("asset:"):
                    relative = relative[6:]
                source = self.celdra_asset_root_v50 / relative
                if not source.is_file():
                    return None
                source_image = tk.PhotoImage(file=str(source))
                crop_image = source_image
            display = self._scale_photo_percent_v74(crop_image, scale)
        except (OSError, tk.TclError, ValueError):
            return None
        self._celdra_author_preview_refs_v74 = [source_image, crop_image, display]
        return display

    def _preview_values_v74(self) -> dict[str, Any]:
        return {
            "asset": self._celdra_studio_pose_v72.get() if self._celdra_studio_pose_v72 else "shy",
            "x": self._bubble_setting_v72(self._celdra_studio_x_v72, 0),
            "y": self._bubble_setting_v72(self._celdra_studio_y_v72, 0),
            "scale": max(10, min(500, self._bubble_setting_v72(self._celdra_studio_scale_v72, 100))),
            "window_percent": self._bubble_setting_v72(self._celdra_studio_stage_v72, 56),
            "bubble_style": self._celdra_studio_bubble_style_v72.get() if self._celdra_studio_bubble_style_v72 else self.PREVIEW_BUBBLE_STYLES[0],
            "bubble_x": self._bubble_setting_v72(self._celdra_studio_bubble_x_v72, 4),
            "bubble_y": self._bubble_setting_v72(self._celdra_studio_bubble_y_v72, 3),
            "bubble_width": self._bubble_setting_v72(self._celdra_studio_bubble_w_v72, 52),
            "text": self._studio_text_value_v72(),
        }

    def _render_author_preview_v74(self, values: dict[str, Any] | None = None) -> None:
        canvas = self._celdra_author_preview_canvas_v74
        if canvas is None:
            return
        data = dict(values or self._preview_values_v74())
        width = max(720, canvas.winfo_width())
        height = max(460, canvas.winfo_height())
        stage_percent = max(10, min(99, int(data.get("window_percent") or 56)))
        stage_width = max(160, round(width * stage_percent / 100.0))
        canvas.delete("all")
        canvas.configure(scrollregion=(0, 0, width, height))
        canvas.create_rectangle(0, 0, stage_width, height, fill="#081321", outline="#35536f")
        canvas.create_rectangle(stage_width, 0, width, height, fill="#060b10", outline="#35536f")
        canvas.create_text(
            12,
            12,
            text=f"CELDRA VIEWPORT • {stage_percent}%",
            anchor="nw",
            fill="#78b9ea",
            font=("Consolas", 9, "bold"),
        )
        canvas.create_text(
            stage_width + 12,
            12,
            text="MOCK RUN ALL CONSOLE",
            anchor="nw",
            fill="#36ce87",
            font=("Consolas", 9, "bold"),
        )
        y_console = 38
        for line in self._celdra_author_console_lines_v74[-18:]:
            color = "#ff5964" if line.upper().startswith("[BRAIN] ERROR") else "#9ce2dc"
            canvas.create_text(
                stage_width + 12,
                y_console,
                text=line,
                anchor="nw",
                width=max(80, width - stage_width - 24),
                fill=color,
                font=("Consolas", 8),
            )
            y_console += 23

        asset = str(data.get("asset") or self._celdra_author_preview_asset_v74 or "")
        self._celdra_author_preview_asset_v74 = asset
        self._celdra_author_preview_text_v74 = str(data.get("text") or "")
        if self._celdra_author_preview_visible_v74 and asset:
            display = self._preview_photo_for_asset_v74(asset, int(data.get("scale") or 100))
            if display is not None:
                image_x = stage_width // 2 + int(data.get("x") or 0)
                image_y = height - 18 + int(data.get("y") or 0)
                canvas.create_image(image_x, image_y, image=display, anchor="s")
                canvas.create_text(
                    12,
                    height - 12,
                    text=f"{asset} • {display.width()}×{display.height()} • {int(data.get('scale') or 100)}%",
                    anchor="sw",
                    fill="#557c9e",
                    font=("Consolas", 8),
                )

        text = str(data.get("text") or "")
        if text:
            self._draw_preview_bubble_v74(canvas, stage_width, height, data, text)

    def _draw_preview_bubble_v74(
        self,
        canvas: tk.Canvas,
        stage_width: int,
        height: int,
        data: dict[str, Any],
        text: str,
    ) -> None:
        style = str(data.get("bubble_style") or self.PREVIEW_BUBBLE_STYLES[0])
        x = round(stage_width * max(0, min(90, int(data.get("bubble_x") or 4))) / 100.0)
        y = round(height * max(0, min(90, int(data.get("bubble_y") or 3))) / 100.0)
        bubble_width = round(stage_width * max(15, min(90, int(data.get("bubble_width") or 52))) / 100.0)
        bubble_width = max(150, min(max(150, stage_width - x - 8), bubble_width))
        lines = max(1, math.ceil(max(1, len(text)) / max(18, bubble_width // 8)))
        bubble_height = max(72, min(210, 44 + lines * 18))
        x2 = x + bubble_width
        y2 = min(height - 8, y + bubble_height)

        if style == "Terminal green":
            canvas.create_rectangle(x, y, x2, y2, fill="#071812", outline="#36ce87", width=2)
            canvas.create_line(x + 8, y + 16, x2 - 8, y + 16, fill="#12865a", dash=(3, 4))
            fill, font, tx, ty = "#78efaf", ("Consolas", 10, "bold"), x + 12, y + 24
        elif style == "Manga white":
            canvas.create_polygon(
                x + 10, y,
                x2 - 18, y,
                x2, y + 14,
                x2 - 8, y2 - 16,
                x2 - 42, y2 - 12,
                x2 - 58, y2 + 8,
                x2 - 70, y2 - 14,
                x + 12, y2 - 8,
                x, y2 - 24,
                fill="#ffffff",
                outline="#071426",
                width=3,
            )
            fill, font, tx, ty = "#071426", ("Segoe UI", 10, "bold"), x + 17, y + 16
        elif style == "Minimal dark":
            canvas.create_rectangle(x, y, x2, y2, fill="#101a28", outline="#78b9ea", width=2)
            canvas.create_polygon(x2 - 52, y2, x2 - 30, y2, x2 - 42, y2 + 13, fill="#101a28", outline="#78b9ea")
            fill, font, tx, ty = "#e2f5ff", ("Segoe UI", 10), x + 14, y + 14
        else:
            canvas.create_rectangle(x + 6, y + 7, x2 + 4, y2 + 5, fill="#16375f", outline="")
            canvas.create_rectangle(x, y, x2, y2, fill="#f4fbff", outline="#78b9ea", width=3)
            canvas.create_polygon(x2 - 56, y2, x2 - 30, y2, x2 - 43, y2 + 16, fill="#f4fbff", outline="#78b9ea")
            fill, font, tx, ty = "#071426", ("Segoe UI", 10, "bold"), x + 14, y + 14
        canvas.create_text(
            tx,
            ty,
            text=text,
            anchor="nw",
            width=max(100, bubble_width - 28),
            fill=fill,
            font=font,
            justify="left",
        )

    def _preview_pose_embedded_v74(self) -> None:
        self._celdra_author_preview_visible_v74 = True
        self._render_author_preview_v74()

    def _preview_asset_embedded_v74(self) -> None:
        asset = self._celdra_author_asset_var_v74.get() if self._celdra_author_asset_var_v74 else ""
        if self._celdra_studio_pose_v72 is not None:
            self._celdra_studio_pose_v72.set(asset)
        self._celdra_author_preview_visible_v74 = True
        self._render_author_preview_v74()

    def _audition_preview_bubble_v74(self, style: str) -> None:
        if self._celdra_studio_bubble_style_v72 is not None:
            self._celdra_studio_bubble_style_v72.set(style)
        self._render_author_preview_v74()

    def _hide_preview_bubble_v74(self) -> None:
        data = self._preview_values_v74()
        data["text"] = ""
        self._render_author_preview_v74(data)

    def _clear_author_console_v74(self) -> None:
        self._celdra_author_console_lines_v74.clear()
        self._render_author_preview_v74()

    def _preview_shy_embedded_v74(self) -> None:
        if self._celdra_author_preview_after_v74 is not None:
            try:
                self.after_cancel(self._celdra_author_preview_after_v74)
            except tk.TclError:
                pass
        start_x = self._bubble_setting_v72(self._celdra_shy_start_x_v72, 0)
        start_y = self._bubble_setting_v72(self._celdra_shy_start_y_v72, 620)
        end_x = self._bubble_setting_v72(self._celdra_shy_end_x_v72, 0)
        end_y = self._bubble_setting_v72(self._celdra_shy_end_y_v72, 0)
        duration = max(250, self._bubble_setting_v72(self._celdra_shy_duration_v72, 12_000))
        scale = max(10, min(500, self._bubble_setting_v72(self._celdra_shy_scale_v72, 100)))
        stage = self._bubble_setting_v72(self._celdra_shy_stage_v72, 50)
        started = time.monotonic()

        def tick() -> None:
            elapsed = (time.monotonic() - started) * 1000.0
            fraction = min(1.0, elapsed / duration)
            progress = self._shy_progress_v63(fraction)
            data = self._preview_values_v74()
            data.update(
                {
                    "asset": "shy",
                    "x": round(start_x + (end_x - start_x) * progress),
                    "y": round(start_y + (end_y - start_y) * progress),
                    "scale": scale,
                    "window_percent": stage,
                    "text": "",
                }
            )
            self._render_author_preview_v74(data)
            if fraction < 1.0:
                self._celdra_author_preview_after_v74 = self.after(16, tick)
            else:
                self._celdra_author_preview_after_v74 = None

        tick()

    # ------------------------------------------------------------------
    # Full event / sequence viewer and editor.
    # ------------------------------------------------------------------
    def _build_author_timeline_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        for label, command in (
            ("Add event", self._add_author_event_v74),
            ("Update", self._update_author_event_v74),
            ("Duplicate", self._duplicate_author_event_v74),
            ("Remove", self._remove_author_event_v74),
            ("Preview selected", self._preview_selected_author_event_v74),
            ("Play", self._play_author_timeline_v74),
            ("Stop", self._stop_author_timeline_v74),
            ("Reset canonical", self._reset_canonical_events_v74),
        ):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 4))
        self._celdra_event_speed_v74 = tk.DoubleVar(value=20.0)
        self._celdra_event_branch_override_v74 = tk.StringVar(value="Auto")
        ttk.Label(toolbar, text="Speed").pack(side="left", padx=(8, 2))
        ttk.Spinbox(
            toolbar,
            textvariable=self._celdra_event_speed_v74,
            from_=0.1,
            to=100.0,
            increment=0.5,
            width=6,
        ).pack(side="left")
        ttk.Label(toolbar, text="Branch").pack(side="left", padx=(8, 2))
        ttk.Combobox(
            toolbar,
            textvariable=self._celdra_event_branch_override_v74,
            values=("Auto", "True", "False"),
            state="readonly",
            width=7,
        ).pack(side="left")

        paned = ttk.Panedwindow(parent, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew")
        tree_frame = ttk.LabelFrame(paned, text="All events and named sequences", padding=4)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        tree = ttk.Treeview(
            tree_frame,
            columns=("time", "sequence", "action", "asset", "branch", "text"),
            show="headings",
            selectmode="browse",
        )
        for key, heading, width in (
            ("time", "At ms", 72),
            ("sequence", "Sequence", 90),
            ("action", "Action", 92),
            ("asset", "Asset", 120),
            ("branch", "IF / OR split", 180),
            ("text", "Text / payload", 330),
        ):
            tree.heading(key, text=heading)
            tree.column(key, width=width, stretch=key in {"asset", "branch", "text"})
        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree.bind("<<TreeviewSelect>>", self._load_selected_author_event_v74)
        self._celdra_author_event_tree_v74 = tree
        paned.add(tree_frame, weight=5)

        inspector = ttk.LabelFrame(paned, text="Selected event", padding=5)
        inspector.rowconfigure(0, weight=1)
        inspector.columnconfigure(0, weight=1)
        inspector_tabs = ttk.Notebook(inspector)
        inspector_tabs.grid(row=0, column=0, sticky="nsew")
        event_tab = ttk.Frame(inspector_tabs, padding=7)
        layout_tab = ttk.Frame(inspector_tabs, padding=7)
        branch_tab = ttk.Frame(inspector_tabs, padding=7)
        inspector_tabs.add(event_tab, text="Event")
        inspector_tabs.add(layout_tab, text="Layout")
        inspector_tabs.add(branch_tab, text="Branch / Text")
        paned.add(inspector, weight=2)

        self._celdra_event_id_v74 = tk.StringVar(value="")
        self._celdra_event_at_v74 = tk.IntVar(value=0)
        self._celdra_event_duration_v74 = tk.IntVar(value=0)
        self._celdra_event_sequence_v74 = tk.StringVar(value="main")
        self._celdra_event_action_v74 = tk.StringVar(value="console")
        self._celdra_event_speaker_v74 = tk.StringVar(value="CELDRA")
        self._celdra_event_asset_v74 = tk.StringVar(value="")
        self._celdra_event_x_v74 = tk.IntVar(value=0)
        self._celdra_event_y_v74 = tk.IntVar(value=0)
        self._celdra_event_scale_v74 = tk.IntVar(value=100)
        self._celdra_event_window_v74 = tk.IntVar(value=56)
        self._celdra_event_bubble_style_v74 = tk.StringVar(value=self.PREVIEW_BUBBLE_STYLES[0])
        self._celdra_event_bubble_x_v74 = tk.IntVar(value=4)
        self._celdra_event_bubble_y_v74 = tk.IntVar(value=3)
        self._celdra_event_bubble_width_v74 = tk.IntVar(value=52)
        self._celdra_event_condition_v74 = tk.StringVar(value="")
        self._celdra_event_true_v74 = tk.StringVar(value="")
        self._celdra_event_false_v74 = tk.StringVar(value="")

        self._labeled_spin_v74(event_tab, 0, "At ms", self._celdra_event_at_v74, 0, 3_600_000, 100)
        self._labeled_spin_v74(event_tab, 1, "Duration ms", self._celdra_event_duration_v74, 0, 600_000, 100)
        self._labeled_entry_v74(event_tab, 2, "Sequence", self._celdra_event_sequence_v74)
        self._labeled_combo_v74(event_tab, 3, "Action", self._celdra_event_action_v74, EVENT_ACTIONS, readonly=False)
        self._labeled_entry_v74(event_tab, 4, "Speaker", self._celdra_event_speaker_v74)
        self._labeled_combo_v74(
            event_tab,
            5,
            "Asset / pose",
            self._celdra_event_asset_v74,
            self._available_author_assets_v74(),
            readonly=False,
        )
        event_tab.columnconfigure(1, weight=1)

        self._labeled_spin_v74(layout_tab, 0, "Avatar X", self._celdra_event_x_v74, -1000, 1000, 5)
        self._labeled_spin_v74(layout_tab, 1, "Avatar Y", self._celdra_event_y_v74, -1000, 1500, 5)
        self._labeled_spin_v74(layout_tab, 2, "Scale %", self._celdra_event_scale_v74, 10, 500, 5)
        self._labeled_spin_v74(layout_tab, 3, "Viewport %", self._celdra_event_window_v74, 10, 99, 1)
        self._labeled_combo_v74(
            layout_tab,
            4,
            "Bubble style",
            self._celdra_event_bubble_style_v74,
            self.PREVIEW_BUBBLE_STYLES,
        )
        self._labeled_spin_v74(layout_tab, 5, "Bubble X %", self._celdra_event_bubble_x_v74, 0, 90, 1)
        self._labeled_spin_v74(layout_tab, 6, "Bubble Y %", self._celdra_event_bubble_y_v74, 0, 90, 1)
        self._labeled_spin_v74(layout_tab, 7, "Bubble width %", self._celdra_event_bubble_width_v74, 15, 90, 1)
        layout_tab.columnconfigure(1, weight=1)

        self._labeled_combo_v74(
            branch_tab,
            0,
            "IF expression",
            self._celdra_event_condition_v74,
            KNOWN_CONDITIONS,
            readonly=False,
        )
        self._labeled_entry_v74(branch_tab, 1, "True sequence", self._celdra_event_true_v74)
        self._labeled_entry_v74(branch_tab, 2, "False sequence", self._celdra_event_false_v74)
        ttk.Label(
            branch_tab,
            text="Conditions accept AND / OR / NOT, for example: is_test OR run_all_failed",
            wraplength=330,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 7))
        ttk.Label(branch_tab, text="Text / payload").grid(row=4, column=0, columnspan=2, sticky="w")
        event_text = tk.Text(branch_tab, height=8, wrap="word", font=("Consolas", 9))
        event_text.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(2, 7))
        self._celdra_event_text_v74 = event_text
        ttk.Label(branch_tab, text="Notes").grid(row=6, column=0, columnspan=2, sticky="w")
        notes = tk.Text(branch_tab, height=4, wrap="word", font=("Segoe UI", 9))
        notes.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(2, 0))
        self._celdra_event_notes_v74 = notes
        branch_tab.rowconfigure(5, weight=2)
        branch_tab.rowconfigure(7, weight=1)
        branch_tab.columnconfigure(1, weight=1)

    @staticmethod
    def _labeled_entry_v74(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=2)

    def _event_text_value_v74(self, widget: tk.Text | None) -> str:
        if widget is None:
            return ""
        try:
            return widget.get("1.0", "end-1c")
        except tk.TclError:
            return ""

    def _event_snapshot_v74(self, *, event_id: str = "") -> dict[str, Any]:
        return normalize_event(
            {
                "id": event_id or (self._celdra_event_id_v74.get() if self._celdra_event_id_v74 else ""),
                "at_ms": self._bubble_setting_v72(self._celdra_event_at_v74, 0),
                "duration_ms": self._bubble_setting_v72(self._celdra_event_duration_v74, 0),
                "sequence": self._celdra_event_sequence_v74.get() if self._celdra_event_sequence_v74 else "main",
                "action": self._celdra_event_action_v74.get() if self._celdra_event_action_v74 else "console",
                "speaker": self._celdra_event_speaker_v74.get() if self._celdra_event_speaker_v74 else "",
                "text": self._event_text_value_v74(self._celdra_event_text_v74),
                "asset": self._celdra_event_asset_v74.get() if self._celdra_event_asset_v74 else "",
                "x": self._bubble_setting_v72(self._celdra_event_x_v74, 0),
                "y": self._bubble_setting_v72(self._celdra_event_y_v74, 0),
                "scale": self._bubble_setting_v72(self._celdra_event_scale_v74, 100),
                "window_percent": self._bubble_setting_v72(self._celdra_event_window_v74, 56),
                "bubble_style": self._celdra_event_bubble_style_v74.get() if self._celdra_event_bubble_style_v74 else self.PREVIEW_BUBBLE_STYLES[0],
                "bubble_x": self._bubble_setting_v72(self._celdra_event_bubble_x_v74, 4),
                "bubble_y": self._bubble_setting_v72(self._celdra_event_bubble_y_v74, 3),
                "bubble_width": self._bubble_setting_v72(self._celdra_event_bubble_width_v74, 52),
                "condition": self._celdra_event_condition_v74.get() if self._celdra_event_condition_v74 else "",
                "true_sequence": self._celdra_event_true_v74.get() if self._celdra_event_true_v74 else "",
                "false_sequence": self._celdra_event_false_v74.get() if self._celdra_event_false_v74 else "",
                "notes": self._event_text_value_v74(self._celdra_event_notes_v74),
            },
            self._celdra_author_event_serial_v74,
        )

    def _selected_author_event_id_v74(self) -> str:
        tree = self._celdra_author_event_tree_v74
        if tree is None:
            return ""
        selected = tree.selection()
        return str(selected[0]) if selected else ""

    def _add_author_event_v74(self) -> None:
        self._celdra_author_event_serial_v74 += 1
        event_id = f"event-{self._celdra_author_event_serial_v74:04d}"
        row = self._event_snapshot_v74(event_id=event_id)
        self._celdra_author_events_v74.append(row)
        self._celdra_author_events_v74 = normalize_events(self._celdra_author_events_v74)
        self._refresh_author_event_tree_v74(select_id=event_id)

    def _update_author_event_v74(self) -> None:
        selected = self._selected_author_event_id_v74()
        if not selected:
            return
        replacement = self._event_snapshot_v74(event_id=selected)
        self._celdra_author_events_v74 = [
            replacement if str(row.get("id")) == selected else row
            for row in self._celdra_author_events_v74
        ]
        self._celdra_author_events_v74 = normalize_events(self._celdra_author_events_v74)
        self._refresh_author_event_tree_v74(select_id=selected)

    def _duplicate_author_event_v74(self) -> None:
        selected = self._selected_author_event_id_v74()
        row = self._celdra_author_event_rows_v74.get(selected)
        if row is None:
            return
        self._celdra_author_event_serial_v74 += 1
        duplicate = dict(row)
        duplicate["id"] = f"event-{self._celdra_author_event_serial_v74:04d}"
        duplicate["at_ms"] = int(duplicate.get("at_ms") or 0) + 250
        self._celdra_author_events_v74.append(normalize_event(duplicate, self._celdra_author_event_serial_v74))
        self._celdra_author_events_v74 = normalize_events(self._celdra_author_events_v74)
        self._refresh_author_event_tree_v74(select_id=duplicate["id"])

    def _remove_author_event_v74(self) -> None:
        selected = self._selected_author_event_id_v74()
        if not selected:
            return
        self._celdra_author_events_v74 = [
            row for row in self._celdra_author_events_v74 if str(row.get("id")) != selected
        ]
        self._refresh_author_event_tree_v74()

    def _refresh_author_event_tree_v74(self, *, select_id: str = "") -> None:
        tree = self._celdra_author_event_tree_v74
        if tree is None:
            return
        tree.delete(*tree.get_children())
        self._celdra_author_event_rows_v74.clear()
        for row in normalize_events(self._celdra_author_events_v74):
            event_id = str(row.get("id"))
            condition = str(row.get("condition") or "")
            branch = ""
            if condition:
                branch = f"IF {condition} → {row.get('true_sequence') or '—'} / {row.get('false_sequence') or '—'}"
            tree.insert(
                "",
                "end",
                iid=event_id,
                values=(
                    row.get("at_ms"),
                    row.get("sequence"),
                    row.get("action"),
                    row.get("asset"),
                    branch,
                    str(row.get("text") or "").replace("\n", " ↵ ")[:220],
                ),
            )
            self._celdra_author_event_rows_v74[event_id] = row
        if select_id and tree.exists(select_id):
            tree.selection_set(select_id)
            tree.see(select_id)

    def _load_selected_author_event_v74(self, _event: tk.Event | None = None) -> None:
        row = self._celdra_author_event_rows_v74.get(self._selected_author_event_id_v74())
        if row is None:
            return
        mappings = (
            (self._celdra_event_id_v74, row.get("id")),
            (self._celdra_event_at_v74, row.get("at_ms")),
            (self._celdra_event_duration_v74, row.get("duration_ms")),
            (self._celdra_event_sequence_v74, row.get("sequence")),
            (self._celdra_event_action_v74, row.get("action")),
            (self._celdra_event_speaker_v74, row.get("speaker")),
            (self._celdra_event_asset_v74, row.get("asset")),
            (self._celdra_event_x_v74, row.get("x")),
            (self._celdra_event_y_v74, row.get("y")),
            (self._celdra_event_scale_v74, row.get("scale")),
            (self._celdra_event_window_v74, row.get("window_percent")),
            (self._celdra_event_bubble_style_v74, row.get("bubble_style")),
            (self._celdra_event_bubble_x_v74, row.get("bubble_x")),
            (self._celdra_event_bubble_y_v74, row.get("bubble_y")),
            (self._celdra_event_bubble_width_v74, row.get("bubble_width")),
            (self._celdra_event_condition_v74, row.get("condition")),
            (self._celdra_event_true_v74, row.get("true_sequence")),
            (self._celdra_event_false_v74, row.get("false_sequence")),
        )
        for variable, value in mappings:
            if variable is not None:
                variable.set(value if value is not None else "")
        for widget, key in (
            (self._celdra_event_text_v74, "text"),
            (self._celdra_event_notes_v74, "notes"),
        ):
            if widget is not None:
                widget.delete("1.0", "end")
                widget.insert("1.0", str(row.get(key) or ""))

    def _preview_selected_author_event_v74(self) -> None:
        row = self._celdra_author_event_rows_v74.get(self._selected_author_event_id_v74())
        if row is not None:
            self._apply_author_event_v74(row)

    def _apply_author_event_v74(self, row: dict[str, Any]) -> None:
        action = str(row.get("action") or "console")
        speaker = str(row.get("speaker") or "")
        text = str(row.get("text") or "")
        asset = str(row.get("asset") or self._celdra_author_preview_asset_v74 or "")
        if action in {"console", "ascii", "status", "egg_glitch", "energy_hatch"}:
            prefix = f"[{speaker}] " if speaker else ""
            self._celdra_author_console_lines_v74.append(prefix + text)
        elif action == "hide_avatar":
            self._celdra_author_preview_visible_v74 = False
        elif action == "show_avatar":
            self._celdra_author_preview_visible_v74 = True
        elif action in {"pose", "avatar", "asset"} and asset:
            self._celdra_author_preview_asset_v74 = asset
            self._celdra_author_preview_visible_v74 = True
        elif action == "condition":
            result = self._evaluate_author_condition_v74(str(row.get("condition") or ""))
            self._celdra_author_console_lines_v74.append(
                f"[BRANCH] {row.get('condition') or '(blank)'} -> {'TRUE' if result else 'FALSE'}"
            )

        bubble_text = text if action in {"chat", "bubble"} else ""
        values = {
            "asset": asset,
            "x": int(row.get("x") or 0),
            "y": int(row.get("y") or 0),
            "scale": int(row.get("scale") or 100),
            "window_percent": int(row.get("window_percent") or 56),
            "bubble_style": row.get("bubble_style") or self.PREVIEW_BUBBLE_STYLES[0],
            "bubble_x": int(row.get("bubble_x") or 4),
            "bubble_y": int(row.get("bubble_y") or 3),
            "bubble_width": int(row.get("bubble_width") or 52),
            "text": bubble_text,
        }
        self._render_author_preview_v74(values)

    def _condition_flags_v74(self) -> dict[str, bool]:
        status = str(getattr(self, "_celdra_last_run_status_v70", "") or "").casefold()
        stage = str(getattr(self, "_celdra_last_run_stage_v70", "") or "").casefold()
        return {
            "is_test": bool(getattr(self, "_celdra_test_mode_v58", True)),
            "first_scan": bool(getattr(self, "_celdra_first_scan_v51", False)),
            "run_all_active": bool(getattr(self, "task_active", False)),
            "run_all_complete": bool(getattr(self, "_celdra_pipeline_finished_v51", False)) and not bool(getattr(self, "_celdra_last_run_status_v70", "") == "failed"),
            "run_all_failed": status == "failed",
            "ccsf_running": stage == "ccsf_extract" and status not in {"complete", "failed"},
            "ccsf_complete": stage == "ccsf_extract" and status in {"complete", "success"},
            "ccsf_failed": stage == "ccsf_extract" and status == "failed",
        }

    def _evaluate_author_condition_v74(self, expression: str) -> bool:
        override = self._celdra_event_branch_override_v74.get() if self._celdra_event_branch_override_v74 else "Auto"
        if override == "True":
            return True
        if override == "False":
            return False
        clean = str(expression or "").strip().casefold()
        if not clean:
            return True
        flags = self._condition_flags_v74()
        or_clauses = [clause.strip() for clause in clean.replace("||", " or ").split(" or ")]
        for clause in or_clauses:
            terms = [term.strip() for term in clause.replace("&&", " and ").split(" and ") if term.strip()]
            passed = True
            for term in terms:
                negate = term.startswith("not ") or term.startswith("!")
                key = term[4:].strip() if term.startswith("not ") else term[1:].strip() if term.startswith("!") else term
                value = bool(flags.get(key, False))
                passed = passed and (not value if negate else value)
            if passed:
                return True
        return False

    def _play_author_timeline_v74(self) -> None:
        self._stop_author_timeline_v74()
        rows = normalize_events(row for row in self._celdra_author_events_v74 if row.get("enabled", True))
        if not rows:
            return
        try:
            speed = max(0.1, float(self._celdra_event_speed_v74.get()))
        except (AttributeError, tk.TclError, TypeError, ValueError):
            speed = 1.0
        self._celdra_author_active_branch_v74 = ""
        self._celdra_author_console_lines_v74.clear()

        def advance(index: int, previous_ms: int) -> None:
            while index < len(rows):
                row = rows[index]
                sequence = str(row.get("sequence") or "main")
                if sequence == "main" or sequence == self._celdra_author_active_branch_v74:
                    break
                index += 1
            if index >= len(rows):
                self._celdra_author_after_v74 = None
                return
            row = rows[index]
            at_ms = int(row.get("at_ms") or 0)
            delay = max(0, round((at_ms - previous_ms) / speed))

            def execute() -> None:
                self._celdra_author_after_v74 = None
                if str(row.get("action")) == "condition":
                    result = self._evaluate_author_condition_v74(str(row.get("condition") or ""))
                    target = str(row.get("true_sequence") if result else row.get("false_sequence") or "")
                    self._celdra_author_active_branch_v74 = target
                self._apply_author_event_v74(row)
                advance(index + 1, at_ms)

            self._celdra_author_after_v74 = self.after(delay, execute)

        advance(0, 0)

    def _stop_author_timeline_v74(self) -> None:
        if self._celdra_author_after_v74 is not None:
            try:
                self.after_cancel(self._celdra_author_after_v74)
            except tk.TclError:
                pass
            self._celdra_author_after_v74 = None
        if self._celdra_author_motion_after_v74 is not None:
            try:
                self.after_cancel(self._celdra_author_motion_after_v74)
            except tk.TclError:
                pass
            self._celdra_author_motion_after_v74 = None

    def _reset_canonical_events_v74(self) -> None:
        if not messagebox.askyesno("Celdra timeline", "Replace the editable timeline with the current canonical events?"):
            return
        self._celdra_author_events_v74 = [
            timeline_event_to_row(event, index)
            for index, event in enumerate(FIRST_RUN_AFTER_CCSF)
        ]
        self._celdra_author_event_serial_v74 = len(self._celdra_author_events_v74)
        self._refresh_author_event_tree_v74()

    # ------------------------------------------------------------------
    # Full-size crop tab, direct save, and embedded crop preview.
    # ------------------------------------------------------------------
    def _build_author_crop_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self._refresh_crop_assets_v74()
        self._celdra_crop_asset_var_v74 = tk.StringVar(
            value=next(iter(self._celdra_crop_asset_map_v74), "")
        )
        ttk.Label(toolbar, text="Source image").pack(side="left")
        self._celdra_crop_asset_combo_v74 = ttk.Combobox(
            toolbar,
            textvariable=self._celdra_crop_asset_var_v74,
            values=list(self._celdra_crop_asset_map_v74),
            state="readonly",
            width=55,
        )
        self._celdra_crop_asset_combo_v74.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(toolbar, text="Load", command=self._use_selected_emote_sheet_v52).pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=self._refresh_crop_assets_v74).pack(side="left", padx=(4, 0))

        save_bar = ttk.Frame(parent)
        save_bar.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        ttk.Button(save_bar, text="Save crop + PNG", command=self._save_crop_and_png_v74).pack(side="left")
        ttk.Button(save_bar, text="Save manifest only", command=self._save_emote_definition_v52).pack(side="left", padx=4)
        ttk.Button(save_bar, text="Export all crop PNGs", command=self._export_all_emotes_v52).pack(side="left")
        ttk.Button(save_bar, text="Show crop in embedded preview", command=self._show_emote_in_celdra_v52).pack(
            side="left", padx=4
        )

        self._install_emote_classifier_v52(parent)
        section = next(
            (
                child
                for child in parent.winfo_children()
                if isinstance(child, ttk.LabelFrame)
                and str(child.cget("text")) == "Emote PNG separator / pose classifier"
            ),
            None,
        )
        if section is not None:
            section.grid_configure(row=2, column=0, columnspan=1, sticky="nsew", pady=0)

    def _refresh_crop_assets_v74(self) -> None:
        assets = (getattr(self, "celdra_asset_inventory_v50", {}) or {}).get("assets") or []
        self._celdra_crop_asset_map_v74 = {
            str(row.get("relative_path")): dict(row)
            for row in assets
            if str(row.get("relative_path") or "")
            and str(row.get("suffix") or "").casefold() in {".png", ".gif"}
        }
        combo = getattr(self, "_celdra_crop_asset_combo_v74", None)
        if combo is not None:
            combo.configure(values=list(self._celdra_crop_asset_map_v74))

    def _use_selected_emote_sheet_v52(self) -> None:
        selected = self._celdra_crop_asset_var_v74.get() if self._celdra_crop_asset_var_v74 else ""
        row = self._celdra_crop_asset_map_v74.get(selected)
        if row is not None:
            self._load_emote_source_v52(row)
            self._new_emote_definition_v52(keep_source=True)
            return
        super()._use_selected_emote_sheet_v52()

    def _save_crop_and_png_v74(self) -> None:
        try:
            definition = self._definition_from_form_v52()
            path = upsert_definition(self.celdra_asset_root_v50, definition)
            output = self._export_definition_v52(definition.to_dict())
        except (OSError, ValueError, tk.TclError) as exc:
            messagebox.showerror("Celdra crop", str(exc))
            return
        self.emote_vars_v52["id"].set(definition.id)
        self._reload_emote_definitions_v52(select_id=definition.id)
        self._refresh_author_assets_v74()
        self.emote_status_v52.set(
            f"Saved {definition.pose} to {path.name} and {output.relative_to(self.celdra_asset_root_v50)}"
        )

    def _show_emote_in_celdra_v52(self) -> None:
        cropped = self._preview_emote_crop_v52()
        if cropped is None:
            return
        try:
            display = self._scale_photo_percent_v74(
                cropped,
                max(10, min(500, self._bubble_setting_v72(self._celdra_studio_scale_v72, 100))),
            )
        except tk.TclError:
            return
        self._celdra_author_preview_refs_v74 = [cropped, display]
        canvas = self._celdra_author_preview_canvas_v74
        if canvas is None:
            return
        width = max(720, canvas.winfo_width())
        height = max(460, canvas.winfo_height())
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#081321", outline="#35536f")
        canvas.create_text(12, 12, text="UNSAVED / CURRENT CROP PREVIEW", anchor="nw", fill="#78b9ea", font=("Consolas", 9, "bold"))
        canvas.create_image(width // 2, height - 18, image=display, anchor="s")
        canvas.create_text(12, height - 12, text=f"{display.width()}×{display.height()}", anchor="sw", fill="#557c9e")
        if self._celdra_author_notebook_v74 is not None:
            try:
                self._celdra_author_notebook_v74.select(0)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Project persistence and portable canonization bundle.
    # ------------------------------------------------------------------
    def _build_author_project_tab_v74(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        self._celdra_author_project_status_v74 = tk.StringVar(
            value="Save the complete event, crop, animation and sizing state here."
        )
        ttk.Label(
            parent,
            text="Celdra authoring project",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(parent, textvariable=self._celdra_author_project_status_v74, wraplength=900).grid(
            row=1, column=0, sticky="ew", pady=(3, 9)
        )

        controls = ttk.LabelFrame(parent, text="Project actions", padding=8)
        controls.grid(row=2, column=0, sticky="new")
        for row, (label, command) in enumerate(
            (
                ("Save project to assets/celdra/authoring", self._save_author_project_v74),
                ("Save project as...", self._save_author_project_as_v74),
                ("Load project...", self._load_author_project_dialog_v74),
                ("Export portable ZIP bundle", self._export_author_bundle_v74),
                ("Copy complete JSON to clipboard", self._copy_author_project_json_v74),
                ("Export all current crop PNGs", self._export_all_emotes_v52),
            )
        ):
            ttk.Button(controls, text=label, command=command).grid(
                row=row, column=0, sticky="ew", pady=3
            )
        controls.columnconfigure(0, weight=1)

        explanation = (
            "The ZIP bundle contains the editable event timeline, IF/OR sequence splits, preview and Shy "
            "geometry, the current crop manifest, and every generated crop PNG. Send that ZIP back for "
            "canonization without manually transcribing settings."
        )
        ttk.Label(parent, text=explanation, wraplength=900, justify="left").grid(
            row=3, column=0, sticky="ew", pady=(12, 0)
        )

    def _author_preview_payload_v74(self) -> dict[str, Any]:
        return self._preview_values_v74()

    def _author_shy_payload_v74(self) -> dict[str, Any]:
        return {
            "start_x": self._bubble_setting_v72(self._celdra_shy_start_x_v72, 0),
            "start_y": self._bubble_setting_v72(self._celdra_shy_start_y_v72, 620),
            "end_x": self._bubble_setting_v72(self._celdra_shy_end_x_v72, 0),
            "end_y": self._bubble_setting_v72(self._celdra_shy_end_y_v72, 0),
            "scale": self._bubble_setting_v72(self._celdra_shy_scale_v72, 100),
            "duration_ms": self._bubble_setting_v72(self._celdra_shy_duration_v72, 12_000),
            "window_percent": self._bubble_setting_v72(self._celdra_shy_stage_v72, 50),
        }

    def _author_project_payload_v74(self) -> dict[str, Any]:
        return project_payload(
            events=self._celdra_author_events_v74,
            preview=self._author_preview_payload_v74(),
            shy_entrance=self._author_shy_payload_v74(),
            manifest=load_manifest(self.celdra_asset_root_v50),
            metadata={
                "tool": "Fragmenter Celdra Authoring Workspace",
                "gui_version": "V74",
                "asset_root": str(self.celdra_asset_root_v50),
            },
        )

    def _save_author_project_v74(self) -> None:
        path = self._celdra_author_project_path_v74 or (
            self.celdra_asset_root_v50 / self.AUTHOR_PROJECT_RELATIVE
        )
        try:
            written = write_project(path, self._author_project_payload_v74())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Celdra project", str(exc))
            return
        self._celdra_author_project_path_v74 = written
        if self._celdra_author_project_status_v74 is not None:
            self._celdra_author_project_status_v74.set(f"Saved authoring project: {written}")

    def _save_author_project_as_v74(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Save Celdra authoring project",
            defaultextension=".json",
            filetypes=(("Celdra project", "*.json"), ("All files", "*.*")),
            initialfile="celdra_authoring_project.json",
        )
        if not selected:
            return
        try:
            written = write_project(selected, self._author_project_payload_v74())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Celdra project", str(exc))
            return
        self._celdra_author_project_path_v74 = written
        if self._celdra_author_project_status_v74 is not None:
            self._celdra_author_project_status_v74.set(f"Saved authoring project: {written}")

    def _load_author_project_dialog_v74(self) -> None:
        selected = filedialog.askopenfilename(
            title="Load Celdra authoring project",
            filetypes=(("Celdra project", "*.json"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            payload = read_project(selected)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Celdra project", str(exc))
            return
        self._apply_author_project_payload_v74(payload)
        self._celdra_author_project_path_v74 = Path(selected)
        if self._celdra_author_project_status_v74 is not None:
            self._celdra_author_project_status_v74.set(f"Loaded authoring project: {selected}")

    def _apply_author_project_payload_v74(self, payload: dict[str, Any]) -> None:
        self._celdra_author_events_v74 = normalize_events(payload.get("events") or [])
        self._celdra_author_event_serial_v74 = max(
            len(self._celdra_author_events_v74),
            self._celdra_author_event_serial_v74,
        )
        preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
        shy = payload.get("shy_entrance") if isinstance(payload.get("shy_entrance"), dict) else {}
        preview_mappings = (
            (self._celdra_studio_pose_v72, preview.get("asset", "shy")),
            (self._celdra_studio_x_v72, preview.get("x", 0)),
            (self._celdra_studio_y_v72, preview.get("y", 0)),
            (self._celdra_studio_scale_v72, preview.get("scale", 100)),
            (self._celdra_studio_stage_v72, preview.get("window_percent", 56)),
            (self._celdra_studio_bubble_style_v72, preview.get("bubble_style", self.PREVIEW_BUBBLE_STYLES[0])),
            (self._celdra_studio_bubble_x_v72, preview.get("bubble_x", 4)),
            (self._celdra_studio_bubble_y_v72, preview.get("bubble_y", 3)),
            (self._celdra_studio_bubble_w_v72, preview.get("bubble_width", 52)),
            (self._celdra_shy_start_x_v72, shy.get("start_x", 0)),
            (self._celdra_shy_start_y_v72, shy.get("start_y", 620)),
            (self._celdra_shy_end_x_v72, shy.get("end_x", 0)),
            (self._celdra_shy_end_y_v72, shy.get("end_y", 0)),
            (self._celdra_shy_scale_v72, shy.get("scale", 100)),
            (self._celdra_shy_duration_v72, shy.get("duration_ms", 12_000)),
            (self._celdra_shy_stage_v72, shy.get("window_percent", 50)),
        )
        for variable, value in preview_mappings:
            if variable is not None:
                variable.set(value)
        if self._celdra_studio_text_v72 is not None:
            self._celdra_studio_text_v72.delete("1.0", "end")
            self._celdra_studio_text_v72.insert("1.0", str(preview.get("text") or ""))
        self._refresh_author_event_tree_v74()
        self._render_author_preview_v74()

    def _copy_author_project_json_v74(self) -> None:
        text = json.dumps(self._author_project_payload_v74(), indent=2, ensure_ascii=False)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except tk.TclError:
            return
        if self._celdra_author_project_status_v74 is not None:
            self._celdra_author_project_status_v74.set("Complete authoring project JSON copied to clipboard.")

    def _export_author_bundle_v74(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Export Celdra canonization bundle",
            defaultextension=".zip",
            filetypes=(("ZIP bundle", "*.zip"), ("All files", "*.*")),
            initialfile="celdra_authoring_bundle.zip",
        )
        if not selected:
            return
        rows = definitions_from_manifest(load_manifest(self.celdra_asset_root_v50))
        generated: list[Path] = []
        failures: list[str] = []
        for row in rows:
            if not bool(row.get("enabled", True)):
                continue
            try:
                generated.append(self._export_definition_v52(row))
            except (OSError, ValueError, tk.TclError) as exc:
                failures.append(f"{row.get('id')}: {exc}")
        try:
            output = write_bundle(
                selected,
                payload=self._author_project_payload_v74(),
                asset_root=self.celdra_asset_root_v50,
                generated_files=generated,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Celdra bundle", str(exc))
            return
        note = f"Exported canonization bundle: {output} ({len(generated)} crop PNGs)"
        if failures:
            note += f"; {len(failures)} crop export failure(s)"
            messagebox.showwarning("Celdra bundle", note + "\n\n" + "\n".join(failures[:8]))
        if self._celdra_author_project_status_v74 is not None:
            self._celdra_author_project_status_v74.set(note)

    def _refresh_author_assets_v74(self) -> None:
        self._reload_manifest_emotes_v56()
        self._celdra_author_asset_values_v74 = self._available_author_assets_v74()
        combo = getattr(self, "_celdra_author_asset_combo_v74", None)
        if combo is not None:
            combo.configure(values=self._celdra_author_asset_values_v74)
        self._refresh_crop_assets_v74()
        self._render_author_preview_v74()

    # ------------------------------------------------------------------
    # Keep inherited production scale editable beyond 100%.
    # ------------------------------------------------------------------
    def _studio_scale_value_v72(self, fallback: int = 100) -> int:
        return max(
            10,
            min(
                500,
                self._bubble_setting_v72(self._celdra_studio_scale_v72, fallback),
            ),
        )

    # ------------------------------------------------------------------
    # Cleanup.
    # ------------------------------------------------------------------
    def _cancel_celdra_cues_v49(self) -> None:
        self._stop_author_timeline_v74()
        if self._celdra_author_preview_after_v74 is not None:
            try:
                self.after_cancel(self._celdra_author_preview_after_v74)
            except tk.TclError:
                pass
            self._celdra_author_preview_after_v74 = None
        super()._cancel_celdra_cues_v49()


def main() -> int:
    app = PublicFragmenterAppV74()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

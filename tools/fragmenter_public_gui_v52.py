#!/usr/bin/env python3
"""V52: interactive Celdra emote-sheet separator and pose classifier."""
from __future__ import annotations

import json
import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from celdra_emote_classifier_v1 import (
    DEFAULT_STATES,
    classifier_summary,
    definitions_from_manifest,
    grid_crops,
    load_manifest,
    make_definition,
    remove_definition,
    upsert_definition,
)
from fragmenter_public_gui_v51 import PublicFragmenterAppV51


class PublicFragmenterAppV52(PublicFragmenterAppV51):
    """Add a non-destructive crop/classification workbench to Celdra Test."""

    def __init__(self) -> None:
        self.emote_source_row_v52: dict[str, Any] | None = None
        self.emote_source_image_v52: tk.PhotoImage | None = None
        self.emote_display_image_v52: tk.PhotoImage | None = None
        self.emote_preview_image_v52: tk.PhotoImage | None = None
        self.emote_display_factor_v52 = 1
        self.emote_canvas_image_id_v52: int | None = None
        self.emote_crop_rect_id_v52: int | None = None
        self.emote_drag_start_v52: tuple[int, int] | None = None
        self.emote_definition_rows_v52: dict[str, dict[str, Any]] = {}
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Emote Separator / Classifier")

    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        frame = self.tabs.get("Celdra Test")
        if frame is None:
            return
        self._install_emote_classifier_v52(frame)

    def _install_emote_classifier_v52(self, frame: ttk.Frame) -> None:
        frame.rowconfigure(2, weight=2)
        section = ttk.LabelFrame(
            frame,
            text="Emote PNG separator / pose classifier",
            padding=6,
        )
        section.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        section.columnconfigure(0, weight=1)
        section.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(section)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Button(
            toolbar,
            text="Use selected Celdra asset",
            command=self._use_selected_emote_sheet_v52,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Reload definitions",
            command=self._reload_emote_definitions_v52,
        ).pack(side="left", padx=(5, 0))
        ttk.Button(
            toolbar,
            text="Copy all definitions JSON",
            command=self._copy_all_emote_json_v52,
        ).pack(side="left", padx=(5, 0))
        ttk.Button(
            toolbar,
            text="Export all defined PNGs",
            command=self._export_all_emotes_v52,
        ).pack(side="left", padx=(5, 0))
        self.emote_status_v52 = tk.StringVar(
            value="Select a multi-pose PNG above, then drag a rectangle around one pose."
        )
        ttk.Label(toolbar, textvariable=self.emote_status_v52).pack(
            side="right", padx=(8, 0)
        )

        body = ttk.Panedwindow(section, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew")

        source_frame = ttk.LabelFrame(body, text="Source sheet — drag to select", padding=4)
        source_frame.columnconfigure(0, weight=1)
        source_frame.rowconfigure(1, weight=1)
        self.emote_source_name_v52 = tk.StringVar(value="No sheet selected")
        ttk.Label(source_frame, textvariable=self.emote_source_name_v52).grid(
            row=0, column=0, sticky="ew", pady=(0, 4)
        )
        canvas = tk.Canvas(
            source_frame,
            width=620,
            height=390,
            background="#10151d",
            highlightthickness=1,
        )
        canvas.grid(row=1, column=0, sticky="nsew")
        canvas.bind("<ButtonPress-1>", self._emote_drag_begin_v52)
        canvas.bind("<B1-Motion>", self._emote_drag_move_v52)
        canvas.bind("<ButtonRelease-1>", self._emote_drag_end_v52)
        self.emote_source_canvas_v52 = canvas
        ttk.Label(
            source_frame,
            text="Drag on the displayed image. Coordinates are converted back to the original PNG.",
            wraplength=600,
        ).grid(row=2, column=0, sticky="ew", pady=(4, 0))
        body.add(source_frame, weight=4)

        list_frame = ttk.LabelFrame(body, text="Defined poses", padding=4)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            list_frame,
            columns=("state", "pose", "crop", "source"),
            show="headings",
            selectmode="browse",
        )
        for key, label, width in (
            ("state", "State", 100),
            ("pose", "Pose", 145),
            ("crop", "Crop", 145),
            ("source", "Source", 220),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key in {"pose", "source"})
        tree_y = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=tree_y.set)
        tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected_definition_v52())
        self.emote_definition_tree_v52 = tree
        body.add(list_frame, weight=3)

        inspector = ttk.LabelFrame(body, text="Crop and classification", padding=6)
        inspector.columnconfigure(1, weight=1)
        inspector.rowconfigure(11, weight=1)
        self.emote_vars_v52 = {
            "id": tk.StringVar(value=""),
            "source": tk.StringVar(value=""),
            "state": tk.StringVar(value="unclassified"),
            "pose": tk.StringVar(value=""),
            "tags": tk.StringVar(value=""),
            "x": tk.IntVar(value=0),
            "y": tk.IntVar(value=0),
            "width": tk.IntVar(value=128),
            "height": tk.IntVar(value=128),
            "grid_rows": tk.IntVar(value=1),
            "grid_columns": tk.IntVar(value=1),
            "padding_x": tk.IntVar(value=0),
            "padding_y": tk.IntVar(value=0),
            "gutter_x": tk.IntVar(value=0),
            "gutter_y": tk.IntVar(value=0),
        }

        row = 0
        ttk.Label(inspector, text="State").grid(row=row, column=0, sticky="w")
        ttk.Combobox(
            inspector,
            textvariable=self.emote_vars_v52["state"],
            values=DEFAULT_STATES,
            state="normal",
        ).grid(row=row, column=1, sticky="ew", padx=(5, 0))
        row += 1
        ttk.Label(inspector, text="Pose name").grid(row=row, column=0, sticky="w")
        ttk.Entry(inspector, textvariable=self.emote_vars_v52["pose"]).grid(
            row=row, column=1, sticky="ew", padx=(5, 0)
        )
        row += 1
        ttk.Label(inspector, text="Tags").grid(row=row, column=0, sticky="w")
        ttk.Entry(inspector, textvariable=self.emote_vars_v52["tags"]).grid(
            row=row, column=1, sticky="ew", padx=(5, 0)
        )
        row += 1

        crop_box = ttk.LabelFrame(inspector, text="Original-image crop", padding=4)
        crop_box.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        for column, (label, key) in enumerate(
            (("X", "x"), ("Y", "y"), ("W", "width"), ("H", "height"))
        ):
            ttk.Label(crop_box, text=label).grid(row=0, column=column, sticky="w", padx=2)
            ttk.Entry(
                crop_box,
                textvariable=self.emote_vars_v52[key],
                width=7,
            ).grid(row=1, column=column, sticky="ew", padx=2)
        row += 1

        preview_box = ttk.LabelFrame(inspector, text="Selected crop preview", padding=4)
        preview_box.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(5, 0))
        preview_box.columnconfigure(0, weight=1)
        preview_box.rowconfigure(0, weight=1)
        self.emote_crop_preview_label_v52 = ttk.Label(
            preview_box,
            text="No crop preview",
            anchor="center",
            justify="center",
        )
        self.emote_crop_preview_label_v52.grid(row=0, column=0, sticky="nsew")
        row += 1

        buttons = ttk.Frame(inspector)
        buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for label, command in (
            ("Preview", self._preview_emote_crop_v52),
            ("Add / Update", self._save_emote_definition_v52),
            ("New", self._new_emote_definition_v52),
            ("Delete", self._delete_emote_definition_v52),
        ):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=(0, 4))
        row += 1

        share = ttk.Frame(inspector)
        share.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        for label, command in (
            ("Copy selected JSON", self._copy_selected_emote_json_v52),
            ("Export selected PNG", self._export_selected_emote_v52),
            ("Show in Celdra viewport", self._show_emote_in_celdra_v52),
        ):
            ttk.Button(share, text=label, command=command).pack(side="left", padx=(0, 4))
        row += 1

        ttk.Separator(inspector, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=7
        )
        row += 1
        grid_box = ttk.LabelFrame(inspector, text="Even-grid candidate generator", padding=4)
        grid_box.grid(row=row, column=0, columnspan=2, sticky="ew")
        fields = (
            ("Rows", "grid_rows"),
            ("Cols", "grid_columns"),
            ("Pad X", "padding_x"),
            ("Pad Y", "padding_y"),
            ("Gap X", "gutter_x"),
            ("Gap Y", "gutter_y"),
        )
        for column, (label, key) in enumerate(fields):
            ttk.Label(grid_box, text=label).grid(row=0, column=column, sticky="w", padx=2)
            ttk.Entry(grid_box, textvariable=self.emote_vars_v52[key], width=6).grid(
                row=1, column=column, sticky="ew", padx=2
            )
        ttk.Button(
            grid_box,
            text="Create unclassified grid poses",
            command=self._generate_emote_grid_v52,
        ).grid(row=2, column=0, columnspan=len(fields), sticky="ew", pady=(5, 0))
        body.add(inspector, weight=3)

        asset_tree = getattr(self, "celdra_test_asset_tree_v50", None)
        if asset_tree is not None:
            asset_tree.bind(
                "<<TreeviewSelect>>",
                lambda _event: self._offer_selected_asset_v52(),
                add="+",
            )
        self._reload_emote_definitions_v52()

    def _offer_selected_asset_v52(self) -> None:
        row = self._selected_celdra_asset_v50()
        if row is None:
            return
        if str(row.get("suffix") or "").casefold() not in {".png", ".gif"}:
            return
        self.emote_status_v52.set(
            f"Selected {row.get('relative_path')}; click 'Use selected Celdra asset' to classify it."
        )

    def _use_selected_emote_sheet_v52(self) -> None:
        row = self._selected_celdra_asset_v50()
        if row is None:
            messagebox.showinfo("Celdra emotes", "Select an image in the bundled asset inventory first.")
            return
        self._load_emote_source_v52(row)
        self._new_emote_definition_v52(keep_source=True)

    def _load_emote_source_v52(self, row: dict[str, Any]) -> bool:
        path = Path(str(row.get("path") or ""))
        if not path.is_file():
            self.emote_status_v52.set(f"Missing source image: {path}")
            return False
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError as exc:
            self.emote_status_v52.set(f"Could not load {path.name}: {exc}")
            return False
        max_width, max_height = 620, 390
        factor = max(
            1,
            int(math.ceil(max(image.width() / max_width, image.height() / max_height))),
        )
        display = image.subsample(factor, factor) if factor > 1 else image
        self.emote_source_row_v52 = dict(row)
        self.emote_source_image_v52 = image
        self.emote_display_image_v52 = display
        self.emote_display_factor_v52 = factor
        canvas = self.emote_source_canvas_v52
        canvas.delete("all")
        self.emote_canvas_image_id_v52 = canvas.create_image(0, 0, image=display, anchor="nw")
        canvas.configure(width=min(max_width, display.width()), height=min(max_height, display.height()))
        self.emote_crop_rect_id_v52 = None
        relative = str(row.get("relative_path") or path.name)
        self.emote_source_name_v52.set(
            f"{relative} — {image.width()}×{image.height()} — display scale 1:{factor}"
        )
        self.emote_vars_v52["source"].set(relative)
        self.emote_status_v52.set("Drag around one pose, name it, and press Add / Update.")
        return True

    def _display_point_v52(self, event: tk.Event) -> tuple[int, int]:
        image = self.emote_display_image_v52
        if image is None:
            return 0, 0
        x = max(0, min(int(event.x), max(0, image.width() - 1)))
        y = max(0, min(int(event.y), max(0, image.height() - 1)))
        return x, y

    def _emote_drag_begin_v52(self, event: tk.Event) -> None:
        if self.emote_display_image_v52 is None:
            return
        self.emote_drag_start_v52 = self._display_point_v52(event)
        x, y = self.emote_drag_start_v52
        if self.emote_crop_rect_id_v52 is not None:
            self.emote_source_canvas_v52.delete(self.emote_crop_rect_id_v52)
        self.emote_crop_rect_id_v52 = self.emote_source_canvas_v52.create_rectangle(
            x, y, x + 1, y + 1, outline="#78b9ea", width=2
        )

    def _emote_drag_move_v52(self, event: tk.Event) -> None:
        if self.emote_drag_start_v52 is None or self.emote_crop_rect_id_v52 is None:
            return
        x0, y0 = self.emote_drag_start_v52
        x1, y1 = self._display_point_v52(event)
        self.emote_source_canvas_v52.coords(
            self.emote_crop_rect_id_v52,
            min(x0, x1),
            min(y0, y1),
            max(x0, x1),
            max(y0, y1),
        )

    def _emote_drag_end_v52(self, event: tk.Event) -> None:
        if self.emote_drag_start_v52 is None:
            return
        x0, y0 = self.emote_drag_start_v52
        x1, y1 = self._display_point_v52(event)
        self.emote_drag_start_v52 = None
        left, top = min(x0, x1), min(y0, y1)
        right, bottom = max(x0, x1), max(y0, y1)
        factor = max(1, self.emote_display_factor_v52)
        self.emote_vars_v52["x"].set(left * factor)
        self.emote_vars_v52["y"].set(top * factor)
        self.emote_vars_v52["width"].set(max(1, (right - left + 1) * factor))
        self.emote_vars_v52["height"].set(max(1, (bottom - top + 1) * factor))
        self._draw_crop_rectangle_v52()
        self._preview_emote_crop_v52()

    def _draw_crop_rectangle_v52(self) -> None:
        if self.emote_display_image_v52 is None:
            return
        factor = max(1, self.emote_display_factor_v52)
        x = int(self.emote_vars_v52["x"].get()) / factor
        y = int(self.emote_vars_v52["y"].get()) / factor
        width = int(self.emote_vars_v52["width"].get()) / factor
        height = int(self.emote_vars_v52["height"].get()) / factor
        if self.emote_crop_rect_id_v52 is not None:
            self.emote_source_canvas_v52.delete(self.emote_crop_rect_id_v52)
        self.emote_crop_rect_id_v52 = self.emote_source_canvas_v52.create_rectangle(
            x,
            y,
            x + width,
            y + height,
            outline="#78b9ea",
            width=2,
        )

    def _current_crop_v52(self) -> dict[str, int]:
        return {
            "x": max(0, int(self.emote_vars_v52["x"].get())),
            "y": max(0, int(self.emote_vars_v52["y"].get())),
            "width": max(1, int(self.emote_vars_v52["width"].get())),
            "height": max(1, int(self.emote_vars_v52["height"].get())),
        }

    def _crop_photo_v52(self, image: tk.PhotoImage, crop: dict[str, int]) -> tk.PhotoImage:
        x = max(0, min(crop["x"], max(0, image.width() - 1)))
        y = max(0, min(crop["y"], max(0, image.height() - 1)))
        width = min(max(1, crop["width"]), max(1, image.width() - x))
        height = min(max(1, crop["height"]), max(1, image.height() - y))
        result = tk.PhotoImage(width=width, height=height)
        result.tk.call(
            str(result),
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
        return result

    def _preview_emote_crop_v52(self) -> tk.PhotoImage | None:
        image = self.emote_source_image_v52
        if image is None:
            return None
        try:
            crop = self._crop_photo_v52(image, self._current_crop_v52())
            preview = self._fit_photo_v50(crop, 300, 220)
        except (tk.TclError, ValueError) as exc:
            self.emote_status_v52.set(f"Crop preview failed: {exc}")
            return None
        self.emote_preview_image_v52 = preview
        self.emote_crop_preview_label_v52.configure(image=preview, text="")
        self._draw_crop_rectangle_v52()
        return crop

    def _new_emote_definition_v52(self, *, keep_source: bool = True) -> None:
        source = self.emote_vars_v52["source"].get() if keep_source else ""
        self.emote_vars_v52["id"].set("")
        self.emote_vars_v52["source"].set(source)
        self.emote_vars_v52["state"].set("unclassified")
        self.emote_vars_v52["pose"].set("")
        self.emote_vars_v52["tags"].set("")
        if self.emote_source_image_v52 is not None:
            self.emote_vars_v52["x"].set(0)
            self.emote_vars_v52["y"].set(0)
            self.emote_vars_v52["width"].set(min(128, self.emote_source_image_v52.width()))
            self.emote_vars_v52["height"].set(min(128, self.emote_source_image_v52.height()))
            self._draw_crop_rectangle_v52()
        tree = getattr(self, "emote_definition_tree_v52", None)
        if tree is not None:
            tree.selection_remove(tree.selection())

    def _definition_from_form_v52(self):
        source = self.emote_vars_v52["source"].get().strip()
        if not source or self.emote_source_image_v52 is None:
            raise ValueError("Select and load a source sheet first")
        return make_definition(
            source,
            state=self.emote_vars_v52["state"].get(),
            pose=self.emote_vars_v52["pose"].get(),
            crop=self._current_crop_v52(),
            tags=self.emote_vars_v52["tags"].get(),
            entry_id=self.emote_vars_v52["id"].get(),
            source_width=self.emote_source_image_v52.width(),
            source_height=self.emote_source_image_v52.height(),
        )

    def _save_emote_definition_v52(self) -> None:
        try:
            definition = self._definition_from_form_v52()
            path = upsert_definition(self.celdra_asset_root_v50, definition)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Celdra emotes", str(exc))
            return
        self.emote_vars_v52["id"].set(definition.id)
        self._reload_emote_definitions_v52(select_id=definition.id)
        self.emote_status_v52.set(f"Saved {definition.pose} to {path.name}.")

    def _reload_emote_definitions_v52(self, *, select_id: str = "") -> None:
        payload = load_manifest(self.celdra_asset_root_v50)
        rows = definitions_from_manifest(payload)
        tree = getattr(self, "emote_definition_tree_v52", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        self.emote_definition_rows_v52.clear()
        selected_iid = ""
        for index, row in enumerate(rows):
            iid = f"emote_{index}"
            crop = row.get("crop") or {}
            tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row.get("state"),
                    row.get("pose"),
                    f"{crop.get('x')},{crop.get('y')} {crop.get('width')}×{crop.get('height')}",
                    row.get("source"),
                ),
            )
            self.emote_definition_rows_v52[iid] = row
            if select_id and str(row.get("id")) == select_id:
                selected_iid = iid
        if selected_iid:
            tree.selection_set(selected_iid)
            tree.see(selected_iid)
        summary = classifier_summary(rows)
        self.emote_status_v52.set(
            f"{summary['definition_count']} pose definition(s) across {summary['source_count']} sheet(s)."
        )

    def _selected_definition_v52(self) -> dict[str, Any] | None:
        tree = self.emote_definition_tree_v52
        selected = tree.selection()
        return self.emote_definition_rows_v52.get(selected[0]) if selected else None

    def _load_selected_definition_v52(self) -> None:
        row = self._selected_definition_v52()
        if row is None:
            return
        source = str(row.get("source") or "")
        asset = next(
            (
                item
                for item in (self.celdra_asset_inventory_v50.get("assets") or [])
                if str(item.get("relative_path") or "") == source
            ),
            None,
        )
        if asset is None:
            path = self.celdra_asset_root_v50 / source
            asset = {
                "path": str(path),
                "relative_path": source,
                "suffix": path.suffix.casefold(),
            }
        if not self._load_emote_source_v52(asset):
            return
        crop = row.get("crop") or {}
        self.emote_vars_v52["id"].set(str(row.get("id") or ""))
        self.emote_vars_v52["source"].set(source)
        self.emote_vars_v52["state"].set(str(row.get("state") or "unclassified"))
        self.emote_vars_v52["pose"].set(str(row.get("pose") or ""))
        self.emote_vars_v52["tags"].set(", ".join(str(tag) for tag in row.get("tags") or []))
        for key in ("x", "y", "width", "height"):
            self.emote_vars_v52[key].set(int(crop.get(key) or (1 if key in {"width", "height"} else 0)))
        self._draw_crop_rectangle_v52()
        self._preview_emote_crop_v52()

    def _delete_emote_definition_v52(self) -> None:
        row = self._selected_definition_v52()
        entry_id = str((row or {}).get("id") or self.emote_vars_v52["id"].get())
        if not entry_id:
            return
        if not messagebox.askyesno("Delete Celdra pose", f"Delete pose definition '{entry_id}'?"):
            return
        try:
            remove_definition(self.celdra_asset_root_v50, entry_id)
        except OSError as exc:
            messagebox.showerror("Celdra emotes", str(exc))
            return
        self._new_emote_definition_v52(keep_source=True)
        self._reload_emote_definitions_v52()

    def _copy_json_v52(self, payload: Any, status: str) -> None:
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.emote_status_v52.set(status)

    def _copy_selected_emote_json_v52(self) -> None:
        row = self._selected_definition_v52()
        if row is None:
            try:
                row = self._definition_from_form_v52().to_dict()
            except ValueError:
                return
        self._copy_json_v52(row, "Selected pose JSON copied to clipboard.")

    def _copy_all_emote_json_v52(self) -> None:
        payload = load_manifest(self.celdra_asset_root_v50)
        self._copy_json_v52(payload, "Celdra manifest JSON copied to clipboard.")

    def _export_definition_v52(self, row: dict[str, Any]) -> Path:
        source = self.celdra_asset_root_v50 / str(row.get("source") or "")
        if not source.is_file():
            raise FileNotFoundError(source)
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
        output = self.celdra_asset_root_v50 / str(row.get("output") or "")
        output.parent.mkdir(parents=True, exist_ok=True)
        cropped.write(str(output), format="png")
        return output

    def _export_selected_emote_v52(self) -> None:
        row = self._selected_definition_v52()
        if row is None:
            try:
                row = self._definition_from_form_v52().to_dict()
            except ValueError as exc:
                messagebox.showerror("Celdra emotes", str(exc))
                return
        try:
            output = self._export_definition_v52(row)
        except (OSError, tk.TclError, ValueError) as exc:
            messagebox.showerror("Celdra emotes", str(exc))
            return
        self.emote_status_v52.set(f"Exported {output.relative_to(self.celdra_asset_root_v50)}")

    def _export_all_emotes_v52(self) -> None:
        rows = definitions_from_manifest(load_manifest(self.celdra_asset_root_v50))
        exported = 0
        failures: list[str] = []
        for row in rows:
            if not bool(row.get("enabled", True)):
                continue
            try:
                self._export_definition_v52(row)
                exported += 1
            except (OSError, tk.TclError, ValueError) as exc:
                failures.append(f"{row.get('id')}: {exc}")
        if failures:
            messagebox.showwarning(
                "Celdra emote export",
                f"Exported {exported}; {len(failures)} failed.\n\n" + "\n".join(failures[:8]),
            )
        self.emote_status_v52.set(f"Exported {exported} classified pose PNG(s).")

    def _show_emote_in_celdra_v52(self) -> None:
        cropped = self._preview_emote_crop_v52()
        if cropped is None:
            return
        fitted = self._fit_photo_v50(cropped, 320, 260)
        self.emote_preview_image_v52 = fitted
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = fitted
        self._show_avatar_v51()
        self._select_run_all_tab_v50()
        self._redraw_celdra_avatar_v50()

    def _generate_emote_grid_v52(self) -> None:
        if self.emote_source_image_v52 is None:
            messagebox.showinfo("Celdra emotes", "Load a source sheet first.")
            return
        try:
            crops = grid_crops(
                self.emote_source_image_v52.width(),
                self.emote_source_image_v52.height(),
                rows=self.emote_vars_v52["grid_rows"].get(),
                columns=self.emote_vars_v52["grid_columns"].get(),
                padding_x=self.emote_vars_v52["padding_x"].get(),
                padding_y=self.emote_vars_v52["padding_y"].get(),
                gutter_x=self.emote_vars_v52["gutter_x"].get(),
                gutter_y=self.emote_vars_v52["gutter_y"].get(),
            )
        except ValueError as exc:
            messagebox.showerror("Celdra emote grid", str(exc))
            return
        source = self.emote_vars_v52["source"].get()
        columns = max(1, int(self.emote_vars_v52["grid_columns"].get()))
        created: list[str] = []
        for index, crop in enumerate(crops):
            grid_row = index // columns + 1
            grid_column = index % columns + 1
            definition = make_definition(
                source,
                state="unclassified",
                pose=f"grid {grid_row}-{grid_column}",
                crop=crop,
                source_width=self.emote_source_image_v52.width(),
                source_height=self.emote_source_image_v52.height(),
            )
            upsert_definition(self.celdra_asset_root_v50, definition)
            created.append(definition.id)
        self._reload_emote_definitions_v52(select_id=created[0] if created else "")
        self.emote_status_v52.set(f"Created {len(created)} unclassified grid pose candidate(s).")


def main() -> int:
    app = PublicFragmenterAppV52()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

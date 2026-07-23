#!/usr/bin/env python3
"""Eighteenth public GUI pass: asset organization and review packages."""
from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Any

import fragmenter_public_gui_v4 as gui_v4
from asset_classifier_v2 import CATEGORY_ORDER
from fragmenter_public_gui_v2 import MAX_VISUAL_ROWS
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v17 import PublicFragmenterAppV17
from visual_asset_annotations_v1 import (
    apply_annotation,
    custom_categories,
    ensure_category,
    load_annotation,
    save_annotation,
)
from visual_report_package_v1 import package_visual_report

_ORIGINAL_DISCOVER = gui_v4.discover_visual_assets_v3


def discover_visual_assets_v18(project, query: str = "", category: str = "All", limit: int = MAX_VISUAL_ROWS) -> list[dict[str, Any]]:
    rows = _ORIGINAL_DISCOVER(project, query=query, category="All", limit=limit)
    annotated = [apply_annotation(project, row) for row in rows]
    if category != "All":
        annotated = [row for row in annotated if str(row.get("kind") or "") == category]
    annotated.sort(key=lambda row: (str(row.get("kind") or "").casefold(), str(row.get("name") or "").casefold(), str(row.get("relative_path") or "").casefold()))
    return annotated[: max(1, int(limit))]


# The inherited v4 refresh method resolves this module global at call time.
gui_v4.discover_visual_assets_v3 = discover_visual_assets_v18


class PublicFragmenterAppV18(PublicFragmenterAppV17):
    def __init__(self) -> None:
        self._visual_context_row: dict[str, Any] | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — 3D Review / Texture Mapping")

    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        self.visual_tree.bind("<Button-3>", self._show_visual_context_menu, add="+")

        # Keep left-drag behavior, add the requested right-drag rotation, and reserve
        # middle-drag exclusively for panning.
        for sequence in ("<ButtonPress-3>", "<B3-Motion>", "<ButtonRelease-3>", "<ButtonPress-2>", "<B2-Motion>", "<ButtonRelease-2>"):
            self.visual_canvas.unbind(sequence)
        self.visual_canvas.bind("<ButtonPress-3>", self._wire_start_drag)
        self.visual_canvas.bind("<B3-Motion>", self._wire_drag_motion)
        self.visual_canvas.bind("<ButtonRelease-3>", self._wire_release_drag)
        self.visual_canvas.bind("<ButtonPress-2>", self._wire_start_pan)
        self.visual_canvas.bind("<B2-Motion>", self._wire_pan_motion)
        self.visual_canvas.bind("<ButtonRelease-2>", self._wire_release_pan)

    def _refresh_visual_assets(self) -> None:
        project = self.project
        if project is not None and hasattr(self, "visual_category_combo"):
            custom = [name for name in custom_categories(project) if name not in CATEGORY_ORDER]
            values = ("All", *CATEGORY_ORDER, *custom)
            self.visual_category_combo.configure(values=values)
            if self.visual_category.get() not in values:
                self.visual_category.set("All")
        super()._refresh_visual_assets()

    def _selected_context_row(self) -> dict[str, Any] | None:
        if self._visual_context_row is not None:
            return dict(self._visual_context_row)
        row = self._selected_visual_row()
        return dict(row) if row is not None else None

    def _show_visual_context_menu(self, event: tk.Event) -> None:
        iid = self.visual_tree.identify_row(event.y)
        row = self.visual_payloads.get(iid)
        if row is None:
            return
        self.visual_tree.selection_set(iid)
        self.visual_tree.focus(iid)
        self._visual_context_row = dict(row)
        project = self.project
        if project is None:
            return

        menu = tk.Menu(self, tearoff=False)
        move = tk.Menu(menu, tearoff=False)
        known = list(CATEGORY_ORDER)
        for name in custom_categories(project):
            if name not in known:
                known.append(name)
        for category in known:
            move.add_command(label=category, command=lambda value=category: self._move_context_asset(value))
        menu.add_cascade(label="Move to category", menu=move)
        menu.add_command(label="Create category…", command=self._create_context_category)
        menu.add_command(label="Add / edit notes…", command=self._edit_context_notes)
        menu.add_separator()
        menu.add_command(label="Flag for report", command=self._flag_context_asset)
        annotation = load_annotation(project, row["absolute_path"])
        if annotation.get("last_report"):
            menu.add_command(label="Open latest report folder", command=self._open_context_report)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _move_context_asset(self, category: str) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        if project is None or row is None:
            return
        save_annotation(project, row["absolute_path"], category=category)
        self._visual_context_row = None
        self.visual_status.set(f"Moved {row['name']} to {category}.")
        self._refresh_visual_assets()

    def _create_context_category(self) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        if project is None or row is None:
            return
        value = simpledialog.askstring("Create visual category", "Category name:", parent=self)
        if value is None or not value.strip():
            return
        category = ensure_category(project, value)
        save_annotation(project, row["absolute_path"], category=category)
        self._visual_context_row = None
        self._refresh_visual_assets()

    def _edit_context_notes(self) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        if project is None or row is None:
            return
        existing = load_annotation(project, row["absolute_path"])["notes"]
        dialog = tk.Toplevel(self)
        dialog.title(f"Notes — {row['name']}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("640x360")
        text = tk.Text(dialog, wrap="word")
        text.pack(fill="both", expand=True, padx=8, pady=8)
        text.insert("1.0", existing)
        buttons = tk.Frame(dialog)
        buttons.pack(fill="x", padx=8, pady=(0, 8))

        def save() -> None:
            save_annotation(project, row["absolute_path"], notes=text.get("1.0", "end-1c"))
            self.visual_status.set(f"Saved notes for {row['name']}.")
            dialog.destroy()

        tk.Button(buttons, text="Save", command=save).pack(side="right")
        tk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))
        dialog.wait_window()

    def _flag_context_asset(self) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        if project is None or row is None:
            return
        source = str(Path(row["absolute_path"]).resolve())
        active_scene = self._textured_scene if self._textured_scene_row and str(Path(self._textured_scene_row["absolute_path"]).resolve()) == source else None
        wireframe = self._wireframe_payload
        contents = self._ccsf_contents_model
        camera = {
            "yaw": self._wire_yaw,
            "pitch": self._wire_pitch,
            "zoom": self._wire_zoom,
            "pan_x": self._wire_pan_x,
            "pan_y": self._wire_pan_y,
            "preview_mode": self._preview_mode,
        }
        annotation = load_annotation(project, source)
        texture_dir = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"]))
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)
        self.visual_status.set(f"Packaging geometry, texture and mapping evidence for {row['name']}…")

        def done(result: Any, error: Exception | None) -> None:
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Report package failed: {error}")
                messagebox.showerror("Flag for report", str(error))
                return
            self.visual_progress["value"] = 100.0
            save_annotation(project, source, flagged=True, last_report=result["zip_path"])
            self.visual_status.set(f"Report package ready: {result['zip_path']}")
            messagebox.showinfo("Flag for report", f"Created:\n{result['zip_path']}")

        self._local_worker(
            "visual-report-package-v1",
            lambda: package_visual_report(
                project,
                row,
                annotation=annotation,
                wireframe_payload=wireframe,
                scene=active_scene,
                contents=contents,
                camera=camera,
                texture_output_dir=texture_dir,
            ),
            done,
        )

    def _open_context_report(self) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        if project is None or row is None:
            return
        value = load_annotation(project, row["absolute_path"]).get("last_report")
        if not value:
            return
        folder = Path(value).expanduser().parent
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # type: ignore[attr-defined]


def main() -> int:
    app = PublicFragmenterAppV18()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

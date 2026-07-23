#!/usr/bin/env python3
"""Twenty-sixth public GUI pass: persistent camera views and explicit orbit controls."""
from __future__ import annotations

import math
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from typing import Any

import ccsf_textured_renderer_v3 as renderer_v3
from asset_classifier_v2 import CATEGORY_ORDER
from fragmenter_public_gui_v25 import PublicFragmenterAppV25
from visual_asset_annotations_v1 import apply_annotation, custom_categories, load_annotation, save_annotation


class PublicFragmenterAppV26(PublicFragmenterAppV25):
    """Treat camera orientation as per-asset review data, separate from model transforms."""

    DEFAULT_CAMERA = (-0.55, 0.35, 1.0, 0.0, 0.0)

    def __init__(self) -> None:
        self._camera_overlay_v26: ttk.LabelFrame | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Persistent 3D Review Views")

    # ------------------------------------------------------------------
    # Explicit camera controls
    # ------------------------------------------------------------------
    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        self._build_camera_overlay_v26()

    def _build_camera_overlay_v26(self) -> None:
        overlay = ttk.LabelFrame(self.visual_canvas, text="Camera view", padding=4)
        self._camera_overlay_v26 = overlay
        for column in range(3):
            overlay.columnconfigure(column, weight=1)
        for column, (label, command) in enumerate(
            (
                ("Front", self._camera_front),
                ("Top", self._camera_top),
                ("Iso", self._camera_reset),
            )
        ):
            ttk.Button(overlay, text=label, width=6, command=command).grid(row=0, column=column, padx=1, pady=1)
        for column, (label, command) in enumerate(
            (
                ("Left", self._camera_left_v26),
                ("Back", self._camera_back_v26),
                ("Right", self._camera_right_v26),
            )
        ):
            ttk.Button(overlay, text=label, width=6, command=command).grid(row=1, column=column, padx=1, pady=1)
        ttk.Button(overlay, text="Fit", width=6, command=self._fit_view).grid(row=2, column=0, padx=1, pady=1)
        ttk.Button(overlay, text="Center", width=6, command=self._center_camera_v26).grid(row=2, column=1, padx=1, pady=1)
        ttk.Button(overlay, text="Save", width=6, command=self._save_selected_pose_view_v26).grid(row=2, column=2, padx=1, pady=1)
        ttk.Separator(overlay, orient="horizontal").grid(row=3, column=0, columnspan=3, sticky="ew", pady=3)
        ttk.Label(
            overlay,
            text="Right drag: orbit\nMiddle drag: pan\nWheel: zoom",
            justify="left",
        ).grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Label(
            overlay,
            text="Model transforms are in\nPreview Adjustments.",
            justify="left",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(3, 0))
        overlay.place(relx=1.0, x=-8, y=8, anchor="ne")
        overlay.lift()

    def _lift_camera_overlay_v26(self) -> None:
        if self._camera_overlay_v26 is not None:
            try:
                self._camera_overlay_v26.lift()
            except tk.TclError:
                pass

    def _draw_interactive_wireframe(self) -> None:
        super()._draw_interactive_wireframe()
        self._lift_camera_overlay_v26()

    def _show_low_resolution_png(self, path: Path, label: str) -> None:
        super()._show_low_resolution_png(path, label)
        self._lift_camera_overlay_v26()

    def _show_png_on_visual_canvas(self, path: Path) -> None:
        super()._show_png_on_visual_canvas(path)
        self._lift_camera_overlay_v26()

    def _apply_camera_v26(
        self,
        yaw: float,
        pitch: float,
        zoom: float,
        pan_x: float,
        pan_y: float,
        *,
        queue_render: bool = True,
    ) -> None:
        self._cancel_camera_work()
        self._wire_yaw = float(yaw)
        self._wire_pitch = max(-1.52, min(1.52, float(pitch)))
        self._wire_zoom = max(0.15, min(8.0, float(zoom)))
        self._wire_pan_x = float(pan_x)
        self._wire_pan_y = float(pan_y)
        self._sync_zoom_control()
        if queue_render and self._preview_mode == "textured" and self._textured_scene is not None:
            self._draw_interactive_wireframe()
            self._queue_camera_render(20)
        else:
            self._draw_wireframe()
        self._lift_camera_overlay_v26()

    def _camera_preset_v26(self, yaw: float, pitch: float, zoom: float = 1.0) -> None:
        self._apply_camera_v26(yaw, pitch, zoom, 0.0, 0.0)

    def _camera_front(self) -> None:
        self._camera_preset_v26(0.0, 0.0)

    def _camera_side(self) -> None:
        self._camera_right_v26()

    def _camera_left_v26(self) -> None:
        self._camera_preset_v26(-math.pi / 2.0, 0.0)

    def _camera_right_v26(self) -> None:
        self._camera_preset_v26(math.pi / 2.0, 0.0)

    def _camera_back_v26(self) -> None:
        self._camera_preset_v26(math.pi, 0.0)

    def _camera_top(self) -> None:
        self._camera_preset_v26(0.0, -math.pi / 2.0 + 0.01)

    def _camera_reset(self) -> None:
        self._camera_preset_v26(*self.DEFAULT_CAMERA[:3])

    def _center_camera_v26(self) -> None:
        self._apply_camera_v26(
            self._wire_yaw,
            self._wire_pitch,
            self._wire_zoom,
            0.0,
            0.0,
        )

    # ------------------------------------------------------------------
    # Camera-relative free orbit: both axes are active during one drag
    # ------------------------------------------------------------------
    def _right_orbit_start(self, event: tk.Event) -> None:
        self._cancel_camera_work()
        self._camera_interacting = True
        self._right_orbit_drag = (event.x, event.y)
        self._right_orbit_axis = None
        self._draw_interactive_wireframe()

    def _right_orbit_motion(self, event: tk.Event) -> None:
        if self._right_orbit_drag is None:
            return
        old_x, old_y = self._right_orbit_drag
        delta_x = event.x - old_x
        delta_y = event.y - old_y
        # Horizontal motion orbits around the model's vertical axis. Vertical motion
        # pitches around the current camera's local horizontal axis.
        self._wire_yaw -= delta_x * 0.008
        self._wire_pitch = max(-1.52, min(1.52, self._wire_pitch + delta_y * 0.008))
        self._right_orbit_drag = (event.x, event.y)
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"Camera orbit | yaw {self._wire_yaw:.2f}, pitch {self._wire_pitch:.2f} | "
            "middle drag pans; release to texture"
        )

    def _right_orbit_release(self, _event: tk.Event) -> None:
        self._right_orbit_drag = None
        self._right_orbit_axis = None
        self._camera_interacting = False
        self._finish_camera_interaction()

    # ------------------------------------------------------------------
    # Restore and persist per-asset pose + complete camera view
    # ------------------------------------------------------------------
    def _visual_asset_selected(self, event: tk.Event) -> None:
        if self._suppress_visual_selection_v23:
            return
        row = self._selected_visual_row()
        if row is not None and self.project is not None:
            annotation = load_annotation(self.project, row["absolute_path"])
            camera = annotation.get("camera")
            if isinstance(camera, dict):
                background = str(camera.get("background") or "Dark Gray")
                if self.preview_background_var is not None and background in self.BACKGROUNDS:
                    self.preview_background_var.set(background)
                    rgba, canvas_color, _text, _line = self.BACKGROUNDS[background]
                    renderer_v3.set_preview_background(rgba)
                    self.visual_canvas.configure(background=canvas_color)
                self._apply_camera_v26(
                    float(camera["yaw"]),
                    float(camera["pitch"]),
                    float(camera["zoom"]),
                    float(camera["pan_x"]),
                    float(camera["pan_y"]),
                    queue_render=False,
                )
            else:
                self._apply_camera_v26(*self.DEFAULT_CAMERA, queue_render=False)
        super()._visual_asset_selected(event)
        self._lift_camera_overlay_v26()

    def _active_annotation_row_v26(self) -> dict[str, Any] | None:
        row = self._selected_context_row()
        if row is None:
            row = self._selected_visual_row()
        return dict(row) if row is not None else None

    def _refresh_annotation_marker_v26(self, row: dict[str, Any]) -> None:
        project = self.project
        if project is None:
            return
        source = self._source_token_v24(row)
        iid = self._asset_iid_for_source_v24(source)
        if iid is None or not self.visual_tree.exists(iid):
            return
        updated = apply_annotation(project, self._automatic_row_v24(row))
        self.visual_payloads[iid] = updated
        self.visual_tree.item(
            iid,
            text=updated["name"],
            values=(
                str(updated.get("classification_confidence") or ""),
                f"{int(updated.get('size') or 0):,}",
                updated["relative_path"],
            ),
        )

    def _save_pose_view_for_row_v26(self, row: dict[str, Any]) -> None:
        project = self._require_project()
        if project is None:
            return
        animation = self.animation_name.get().strip()
        frame = max(0, int(self.animation_frame.get()))
        default_animation = "" if not animation or animation == "Initial Pose" else animation
        default_frame = frame if default_animation else 0
        background = self.preview_background_var.get() if self.preview_background_var is not None else "Dark Gray"
        save_annotation(
            project,
            row["absolute_path"],
            default_animation=default_animation,
            default_frame=default_frame,
            camera_yaw=self._wire_yaw,
            camera_pitch=self._wire_pitch,
            camera_zoom=self._wire_zoom,
            camera_pan_x=self._wire_pan_x,
            camera_pan_y=self._wire_pan_y,
            camera_background=background,
            persist=False,
        )
        self._refresh_annotation_marker_v26(row)
        self._visual_context_row = None
        self._visual_context_rows_v25 = []
        self._queue_annotation_persist_v24()
        pose_text = f"{default_animation} frame {default_frame}" if default_animation else "Initial Pose"
        self.visual_status.set(
            f"Saved {row['name']} default pose + camera view: {pose_text}; "
            f"yaw {self._wire_yaw:.2f}, pitch {self._wire_pitch:.2f}, zoom {self._wire_zoom:.2f}."
        )

    def _save_selected_pose_view_v26(self) -> None:
        row = self._selected_visual_row()
        if row is None:
            messagebox.showinfo("Save Pose + View", "Select one asset first.")
            return
        self._save_pose_view_for_row_v26(dict(row))

    def _save_current_pose_v25(self) -> None:
        row = self._active_annotation_row_v26()
        if row is None:
            return
        self._save_pose_view_for_row_v26(row)

    def _clear_default_pose_v25(self) -> None:
        project = self._require_project()
        row = self._active_annotation_row_v26()
        if project is None or row is None:
            return
        save_annotation(
            project,
            row["absolute_path"],
            default_animation="",
            default_frame=0,
            clear_camera=True,
            persist=False,
        )
        self._refresh_annotation_marker_v26(row)
        self._visual_context_row = None
        self._visual_context_rows_v25 = []
        self._queue_annotation_persist_v24()
        self.visual_status.set(f"Cleared the saved pose and camera view for {row['name']}.")

    # ------------------------------------------------------------------
    # Notes: save to annotation memory immediately, then serialize in background
    # ------------------------------------------------------------------
    def _edit_context_notes(self) -> None:
        project = self._require_project()
        row = self._active_annotation_row_v26()
        if project is None or row is None:
            return
        existing = load_annotation(project, row["absolute_path"])["notes"]
        dialog = tk.Toplevel(self)
        dialog.title(f"Notes — {row['name']}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("680x390")
        text = tk.Text(dialog, wrap="word", undo=True)
        text.pack(fill="both", expand=True, padx=8, pady=8)
        text.insert("1.0", existing)
        text.focus_set()
        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        status = tk.StringVar(value="Notes are included in project.json and Export Classification Record.")
        ttk.Label(buttons, textvariable=status).pack(side="left")

        def save(_event: tk.Event | None = None) -> str:
            value = text.get("1.0", "end-1c")
            save_annotation(project, row["absolute_path"], notes=value, persist=False)
            self._refresh_annotation_marker_v26(row)
            self._visual_context_row = None
            self._visual_context_rows_v25 = []
            self._queue_annotation_persist_v24()
            self.visual_status.set(f"Saved {len(value):,} note character(s) for {row['name']}.")
            dialog.destroy()
            return "break"

        text.bind("<Control-Return>", save)
        ttk.Button(buttons, text="Save", command=save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))
        dialog.wait_window()

    # ------------------------------------------------------------------
    # Context menu wording distinguishes camera view from model transform
    # ------------------------------------------------------------------
    def _show_visual_context_menu(self, event: tk.Event) -> None:
        iid = self.visual_tree.identify_row(event.y)
        row = self.visual_payloads.get(iid)
        if row is None:
            return
        selected = set(self.visual_tree.selection())
        if iid not in selected:
            self.visual_tree.selection_set(iid)
        self.visual_tree.focus(iid)
        rows = [dict(self.visual_payloads[item]) for item in self.visual_tree.selection() if item in self.visual_payloads]
        self._visual_context_rows_v25 = rows
        self._visual_context_row = dict(row)
        project = self.project
        if project is None:
            return

        count = len(rows)
        menu = tk.Menu(self, tearoff=False)
        move = tk.Menu(menu, tearoff=False)
        known = list(CATEGORY_ORDER)
        for name in custom_categories(project):
            if name not in known:
                known.append(name)
        for category in known:
            move.add_command(label=category, command=lambda value=category: self._move_context_asset(value))
        menu.add_cascade(label=f"Move {count} asset{'s' if count != 1 else ''} to category", menu=move)
        menu.add_command(label="Create category and move selection…", command=self._create_context_category)
        if count == 1:
            menu.add_command(label="Add / edit notes…", command=self._edit_context_notes)
            menu.add_command(label="Save current pose + camera view", command=self._save_current_pose_v25)
            annotation = load_annotation(project, row["absolute_path"])
            if annotation.get("default_animation") or annotation.get("camera_saved"):
                menu.add_command(label="Clear saved pose + camera view", command=self._clear_default_pose_v25)
            menu.add_separator()
            menu.add_command(label="Flag for report", command=self._flag_context_asset)
            if annotation.get("last_report"):
                menu.add_command(label="Open latest report folder", command=self._open_context_report)
        menu.add_separator()
        menu.add_command(label="Export classification record", command=self._export_classifications_v25)
        menu.add_command(label="Audit x000-x999 inventory", command=self._audit_x_series_v25)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


def main() -> int:
    app = PublicFragmenterAppV26()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

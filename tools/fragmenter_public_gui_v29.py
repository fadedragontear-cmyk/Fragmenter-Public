#!/usr/bin/env python3
"""Twenty-ninth public GUI pass: camera-relative orbit and durable review UI."""
from __future__ import annotations

import math
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

import camera_orbit_v1 as camera_orbit
import ccsf_textured_renderer_v3 as renderer_v3
from asset_classifier_v2 import category_sort_key
from fragmenter_public_gui_v23 import _natural_key
from fragmenter_public_gui_v25 import discover_visual_assets_v25
from fragmenter_public_gui_v28 import PublicFragmenterAppV28
from visual_asset_annotations_v1 import apply_annotation, load_annotation, save_annotation


class PublicFragmenterAppV29(PublicFragmenterAppV28):
    """Use one camera basis and one visible review panel for every interaction path."""

    def __init__(self) -> None:
        self._camera_basis_v29 = camera_orbit.basis_from_yaw_pitch(-0.55, 0.35)
        self._camera_panel_syncing_v29 = False
        self._camera_panel_frame_v29: ttk.Frame | None = None
        self._camera_panel_tab_v29: str | None = None
        self._camera_heading_var_v29: tk.DoubleVar | None = None
        self._camera_elevation_var_v29: tk.DoubleVar | None = None
        self._camera_zoom_var_v29: tk.DoubleVar | None = None
        self._camera_pan_x_var_v29: tk.DoubleVar | None = None
        self._camera_pan_y_var_v29: tk.DoubleVar | None = None
        self._camera_readout_v29: tk.StringVar | None = None
        self._pose_readout_v29: tk.StringVar | None = None
        self._note_asset_v29: tk.StringVar | None = None
        self._note_text_v29: tk.Text | None = None
        self._note_dirty_v29 = False
        super().__init__()
        renderer_v3.set_preview_camera_basis(camera_orbit.flatten_basis(self._camera_basis_v29))
        self.title("Fragmenter 1.0 WIP — Camera-Relative Review / Durable Classification")

    # ------------------------------------------------------------------
    # Layout and asset-list presentation
    # ------------------------------------------------------------------
    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        self.visual_tree.heading("kind", text="Type")
        self.visual_tree.heading("size", text="Size")
        self.visual_tree.heading("path", text="Notes")
        self.visual_tree.column("kind", width=190, stretch=False)
        self.visual_tree.column("size", width=90, stretch=False)
        self.visual_tree.column("path", width=360, stretch=True)
        self._replace_preview_adjustments_v29()
        self._remove_legacy_camera_bar_v29(parent)
        self._replace_sorting_instruction_v29(parent)
        self._sync_camera_panel_v29()

    def _replace_sorting_instruction_v29(self, widget: tk.Misc) -> None:
        for child in widget.winfo_children():
            try:
                if isinstance(child, ttk.Label) and "Ctrl+click" in str(child.cget("text")):
                    child.configure(text="Connection to Celdra failed... Please try again later.")
                self._replace_sorting_instruction_v29(child)
            except tk.TclError:
                continue

    def _remove_legacy_camera_bar_v29(self, widget: tk.Misc) -> None:
        for child in list(widget.winfo_children()):
            try:
                texts = {
                    str(descendant.cget("text"))
                    for descendant in child.winfo_children()
                    if isinstance(descendant, (ttk.Label, ttk.Button))
                }
                if "Camera" in texts and {"Front", "Side", "Top"}.issubset(texts):
                    child.destroy()
                    continue
                self._remove_legacy_camera_bar_v29(child)
            except tk.TclError:
                continue

    @staticmethod
    def _note_summary_v29(row: dict[str, Any]) -> str:
        value = str(row.get("user_notes") or "").replace("\r", " ").replace("\n", " ⏎ ").strip()
        return value if len(value) <= 180 else value[:177] + "..."

    def _row_values_v29(self, row: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(row.get("kind") or "Unknown CCSF"),
            f"{int(row.get('size') or 0):,}",
            self._note_summary_v29(row),
        )

    def _set_tree_row_v29(self, iid: str, row: dict[str, Any]) -> None:
        if self.visual_tree.exists(iid):
            self.visual_tree.item(iid, text=str(row.get("name") or "asset"), values=self._row_values_v29(row))

    def _normalize_tree_rows_v29(self) -> None:
        for iid, row in self.visual_payloads.items():
            self._set_tree_row_v29(iid, row)

    def _refresh_visual_assets(self) -> None:
        project = self.project
        self._visual_generation += 1
        generation = self._visual_generation
        self.visual_tree.delete(*self.visual_tree.get_children())
        self.visual_payloads.clear()
        if project is None:
            return
        self.visual_status.set("Loading classified assets, durable notes and saved review views…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)
        query = self.visual_search.get()
        category = self.visual_category.get() if hasattr(self, "visual_category") else "All"

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._visual_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Asset classification failed: {error}")
                return
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(str(row.get("kind") or "Unknown CCSF"), []).append(row)
            asset_index = 0
            for group_index, kind in enumerate(sorted(grouped, key=lambda value: (category_sort_key(value), value.casefold()))):
                category_iid = f"category_v29_{group_index}"
                children = sorted(
                    grouped[kind],
                    key=lambda row: (_natural_key(row.get("name")), _natural_key(row.get("relative_path"))),
                )
                self.visual_tree.insert(
                    "",
                    "end",
                    iid=category_iid,
                    text=kind,
                    values=(f"{len(children):,} assets", "", ""),
                    open=bool(query.strip()) or category != "All",
                )
                for row in children:
                    iid = f"asset_v29_{asset_index}"
                    asset_index += 1
                    self.visual_tree.insert(category_iid, "end", iid=iid, text=row["name"], values=self._row_values_v29(row))
                    self.visual_payloads[iid] = row
            self._refresh_category_values_v23()
            self.visual_progress["value"] = 100.0
            self.visual_status.set(
                f"Showing {len(rows):,} assets. Type is the active classification; notes are loaded from the durable review record."
            )

        self._local_worker(
            "visual-classification-v29",
            lambda: discover_visual_assets_v25(project, query=query, category=category, limit=100_000),
            done,
        )

    def _rebuild_visual_tree_cached(self, *args: Any, **kwargs: Any) -> None:
        super()._rebuild_visual_tree_cached(*args, **kwargs)
        self._normalize_tree_rows_v29()

    def _apply_annotation_incremental_v24(self, *args: Any, **kwargs: Any) -> None:
        super()._apply_annotation_incremental_v24(*args, **kwargs)
        self._normalize_tree_rows_v29()

    def _batch_move_rows_v25(self, rows: list[dict[str, Any]], category: str) -> None:
        super()._batch_move_rows_v25(rows, category)
        self._normalize_tree_rows_v29()

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
        self._set_tree_row_v29(iid, updated)

    # ------------------------------------------------------------------
    # Replace the model-transform tab with the actual camera/pose authority.
    # ------------------------------------------------------------------
    def _replace_preview_adjustments_v29(self) -> None:
        notebook = getattr(self, "_visual_details_notebook", None)
        if notebook is None:
            return
        target: ttk.Frame | None = None
        target_id: str | None = None
        for tab_id in notebook.tabs():
            if str(notebook.tab(tab_id, "text")) == "Preview Adjustments":
                target_id = str(tab_id)
                target = notebook.nametowidget(tab_id)
                break
        if target is None or target_id is None:
            return
        for child in target.winfo_children():
            child.destroy()
        notebook.tab(target_id, text="Camera / Pose")
        target.columnconfigure(0, weight=1)
        target.rowconfigure(2, weight=1)
        self._camera_panel_frame_v29 = target
        self._camera_panel_tab_v29 = target_id

        camera = ttk.LabelFrame(target, text="Camera view", padding=7)
        camera.grid(row=0, column=0, sticky="ew")
        camera.columnconfigure(1, weight=1)
        self._camera_heading_var_v29 = tk.DoubleVar(value=0.0)
        self._camera_elevation_var_v29 = tk.DoubleVar(value=0.0)
        self._camera_zoom_var_v29 = tk.DoubleVar(value=1.0)
        self._camera_pan_x_var_v29 = tk.DoubleVar(value=0.0)
        self._camera_pan_y_var_v29 = tk.DoubleVar(value=0.0)
        rows = (
            ("Horizontal orbit", self._camera_heading_var_v29, -180.0, 180.0),
            ("Vertical orbit", self._camera_elevation_var_v29, -89.0, 89.0),
            ("Zoom", self._camera_zoom_var_v29, 0.15, 8.0),
            ("Pan X", self._camera_pan_x_var_v29, -1.0, 1.0),
            ("Pan Y", self._camera_pan_y_var_v29, -1.0, 1.0),
        )
        for index, (label, variable, minimum, maximum) in enumerate(rows):
            ttk.Label(camera, text=label).grid(row=index, column=0, sticky="w", padx=(0, 7), pady=2)
            scale = ttk.Scale(
                camera,
                from_=minimum,
                to=maximum,
                variable=variable,
                orient="horizontal",
                command=lambda _value: self._camera_panel_changed_v29(),
            )
            scale.grid(row=index, column=1, sticky="ew", pady=2)
            scale.bind("<ButtonRelease-1>", self._camera_panel_released_v29)
            ttk.Label(camera, textvariable=variable, width=9).grid(row=index, column=2, sticky="e", padx=(6, 0))

        background_row = ttk.Frame(camera)
        background_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Label(background_row, text="Background").pack(side="left")
        background = ttk.Combobox(
            background_row,
            textvariable=self.preview_background_var,
            values=tuple(self.BACKGROUNDS),
            state="readonly",
            width=12,
        )
        background.pack(side="left", padx=(6, 10))
        background.bind("<<ComboboxSelected>>", lambda _event: self._panel_background_changed_v29())
        ttk.Button(background_row, text="Fit", command=self._fit_view).pack(side="left")
        ttk.Button(background_row, text="Save Pose / Position", command=self._save_selected_pose_view_v26, style="Accent.TButton").pack(side="right")

        self._camera_readout_v29 = tk.StringVar(value="Camera not initialized")
        self._pose_readout_v29 = tk.StringVar(value="Pose: Initial Pose / frame 0")
        ttk.Label(camera, textvariable=self._camera_readout_v29, wraplength=520).grid(row=6, column=0, columnspan=3, sticky="w", pady=(7, 0))
        ttk.Label(camera, textvariable=self._pose_readout_v29, wraplength=520).grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 0))

        notes = ttk.LabelFrame(target, text="Asset notes", padding=7)
        notes.grid(row=1, column=0, sticky="nsew", pady=(7, 0))
        notes.columnconfigure(0, weight=1)
        notes.rowconfigure(1, weight=1)
        self._note_asset_v29 = tk.StringVar(value="No asset selected")
        ttk.Label(notes, textvariable=self._note_asset_v29).grid(row=0, column=0, sticky="w")
        self._note_text_v29 = tk.Text(notes, height=7, wrap="word", undo=True)
        self._note_text_v29.grid(row=1, column=0, sticky="nsew", pady=(4, 5))
        self._note_text_v29.bind("<<Modified>>", self._note_modified_v29)
        actions = ttk.Frame(notes)
        actions.grid(row=2, column=0, sticky="ew")
        ttk.Label(actions, text="Notes appear directly in the asset list and classification export.").pack(side="left")
        ttk.Button(actions, text="Save Notes", command=self._save_notes_v29).pack(side="right")

    # ------------------------------------------------------------------
    # Camera-relative basis shared by mouse, keyboard, sliders and renderer.
    # ------------------------------------------------------------------
    def _set_basis_v29(self, basis: camera_orbit.Basis, *, sync_panel: bool = True) -> None:
        self._camera_basis_v29 = camera_orbit.orthonormalize(basis)
        heading, elevation = camera_orbit.heading_elevation(self._camera_basis_v29)
        self._wire_yaw = math.radians(heading)
        self._wire_pitch = math.radians(elevation)
        renderer_v3.set_preview_camera_basis(camera_orbit.flatten_basis(self._camera_basis_v29))
        if sync_panel:
            self._sync_camera_panel_v29()

    def _camera_tuple(self) -> tuple[float, ...]:
        return (
            float(self._wire_yaw),
            float(self._wire_pitch),
            float(self._wire_zoom),
            float(self._wire_pan_x),
            float(self._wire_pan_y),
            *camera_orbit.flatten_basis(self._camera_basis_v29),
        )

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
        self._set_basis_v29(camera_orbit.basis_from_yaw_pitch(yaw, pitch), sync_panel=False)
        self._wire_zoom = max(0.15, min(8.0, float(zoom)))
        self._wire_pan_x = float(pan_x)
        self._wire_pan_y = float(pan_y)
        self._sync_zoom_control()
        self._sync_camera_panel_v29()
        if queue_render and self._preview_mode == "textured" and self._textured_scene is not None:
            self._draw_interactive_wireframe()
            self._queue_camera_render(20)
        else:
            self._draw_wireframe()
        self._style_camera_overlay_v27()

    def _apply_saved_camera_v27(self, annotation: dict[str, Any]) -> None:
        camera = annotation.get("camera")
        if not isinstance(camera, dict):
            self._apply_camera_v26(*self.DEFAULT_CAMERA, queue_render=False)
            return
        background = str(camera.get("background") or "Dark Gray")
        if self.preview_background_var is not None and background in self.BACKGROUNDS:
            self.preview_background_var.set(background)
            rgba, canvas_color, _text, _line = self.BACKGROUNDS[background]
            renderer_v3.set_preview_background(rgba)
            self.visual_canvas.configure(background=canvas_color)
        basis_values = camera.get("basis")
        if isinstance(basis_values, (list, tuple)) and len(basis_values) == 9:
            self._cancel_camera_work()
            self._set_basis_v29(camera_orbit.basis_from_flat(basis_values), sync_panel=False)
            self._wire_zoom = max(0.15, min(8.0, float(camera.get("zoom") or 1.0)))
            self._wire_pan_x = float(camera.get("pan_x") or 0.0)
            self._wire_pan_y = float(camera.get("pan_y") or 0.0)
            self._sync_zoom_control()
            self._sync_camera_panel_v29()
            self._draw_wireframe()
        else:
            self._apply_camera_v26(
                float(camera.get("yaw") or 0.0),
                float(camera.get("pitch") or 0.0),
                float(camera.get("zoom") or 1.0),
                float(camera.get("pan_x") or 0.0),
                float(camera.get("pan_y") or 0.0),
                queue_render=False,
            )
        self._style_camera_overlay_v27()

    def _orbit_nudge_v27(self, *, horizontal: int = 0, vertical: int = 0) -> str:
        if not horizontal and not vertical:
            return "break"
        self._cancel_camera_work()
        self._camera_interacting = True
        self._set_basis_v29(
            camera_orbit.orbit_camera_relative(
                self._camera_basis_v29,
                horizontal=float(horizontal) * self.ORBIT_KEY_STEP,
                vertical=float(vertical) * self.ORBIT_KEY_STEP,
            )
        )
        self._draw_interactive_wireframe()
        self.visual_status.set("Camera-relative orbit updated from arrow control.")
        self._finish_discrete_camera_change_v27()
        return "break"

    def _right_orbit_motion(self, event: tk.Event) -> None:
        origin = self._right_orbit_origin_v27
        previous = self._right_orbit_last_v27
        if origin is None or previous is None:
            return
        total_x = event.x - origin[0]
        total_y = event.y - origin[1]
        if self._right_orbit_axis_v27 is None:
            if max(abs(total_x), abs(total_y)) < 4:
                return
            self._right_orbit_axis_v27 = "horizontal" if abs(total_x) >= abs(total_y) else "vertical"
            self._right_orbit_axis = self._right_orbit_axis_v27
        delta_x = event.x - previous[0]
        delta_y = event.y - previous[1]
        if self._right_orbit_axis_v27 == "horizontal":
            basis = camera_orbit.orbit_camera_relative(
                self._camera_basis_v29,
                horizontal=delta_x * self.DRAG_RADIANS_PER_PIXEL,
            )
        else:
            basis = camera_orbit.orbit_camera_relative(
                self._camera_basis_v29,
                vertical=delta_y * self.DRAG_RADIANS_PER_PIXEL,
            )
        self._set_basis_v29(basis)
        point = (event.x, event.y)
        self._right_orbit_last_v27 = point
        self._right_orbit_drag = point
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"{self._right_orbit_axis_v27.title()} orbit around the viewport's current axis; release to texture."
        )

    def _middle_pan_motion(self, event: tk.Event) -> None:
        super()._middle_pan_motion(event)
        self._sync_camera_panel_v29()

    def _wire_mousewheel(self, event: tk.Event) -> None:
        super()._wire_mousewheel(event)
        self._sync_camera_panel_v29()

    def _zoom_nudge_v27(self, factor: float) -> str:
        result = super()._zoom_nudge_v27(factor)
        self._sync_camera_panel_v29()
        return result

    def _camera_panel_changed_v29(self) -> None:
        if self._camera_panel_syncing_v29:
            return
        variables = (
            self._camera_heading_var_v29,
            self._camera_elevation_var_v29,
            self._camera_zoom_var_v29,
            self._camera_pan_x_var_v29,
            self._camera_pan_y_var_v29,
        )
        if any(variable is None for variable in variables):
            return
        self._cancel_camera_work()
        self._camera_interacting = True
        self._set_basis_v29(
            camera_orbit.basis_from_heading_elevation(
                self._camera_heading_var_v29.get(),
                self._camera_elevation_var_v29.get(),
            ),
            sync_panel=False,
        )
        self._wire_zoom = max(0.15, min(8.0, self._camera_zoom_var_v29.get()))
        self._wire_pan_x = self._camera_pan_x_var_v29.get()
        self._wire_pan_y = self._camera_pan_y_var_v29.get()
        self._sync_zoom_control()
        self._update_camera_readout_v29()
        self._draw_interactive_wireframe()

    def _camera_panel_released_v29(self, _event: tk.Event) -> None:
        if self._camera_panel_syncing_v29:
            return
        self._camera_interacting = False
        self._finish_camera_interaction()

    def _panel_background_changed_v29(self) -> None:
        self._preview_background_changed_v25()
        self._sync_camera_panel_v29()

    def _sync_camera_panel_v29(self) -> None:
        if self._camera_heading_var_v29 is None:
            return
        heading, elevation = camera_orbit.heading_elevation(self._camera_basis_v29)
        self._camera_panel_syncing_v29 = True
        try:
            self._camera_heading_var_v29.set(round(heading, 3))
            self._camera_elevation_var_v29.set(round(elevation, 3))
            self._camera_zoom_var_v29.set(round(float(self._wire_zoom), 4))
            self._camera_pan_x_var_v29.set(round(float(self._wire_pan_x), 4))
            self._camera_pan_y_var_v29.set(round(float(self._wire_pan_y), 4))
        finally:
            self._camera_panel_syncing_v29 = False
        self._update_camera_readout_v29()
        self._update_pose_readout_v29()

    def _update_camera_readout_v29(self) -> None:
        if self._camera_readout_v29 is None:
            return
        heading, elevation = camera_orbit.heading_elevation(self._camera_basis_v29)
        background = self.preview_background_var.get() if self.preview_background_var is not None else "Dark Gray"
        self._camera_readout_v29.set(
            f"View: horizontal {heading:.2f}°, vertical {elevation:.2f}°, zoom {self._wire_zoom:.3f}, "
            f"pan ({self._wire_pan_x:.3f}, {self._wire_pan_y:.3f}), background {background}."
        )

    def _update_pose_readout_v29(self) -> None:
        if self._pose_readout_v29 is None or not hasattr(self, "animation_name"):
            return
        animation = self.animation_name.get().strip() or "Initial Pose"
        frame = max(0, int(self.animation_frame.get())) if hasattr(self, "animation_frame") else 0
        self._pose_readout_v29.set(f"Pose: {animation} / frame {frame}")

    def _update_animation_frame_label(self, frame: int) -> None:
        super()._update_animation_frame_label(frame)
        self._update_pose_readout_v29()

    def _draw_interactive_wireframe(self) -> None:
        canvas = getattr(self, "visual_canvas", None)
        geometry = self._interactive_geometry()
        if canvas is None:
            return
        canvas.delete("all")
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        if geometry is None:
            canvas.create_text(20, 20, anchor="nw", fill="#BFD7EA", text="No geometry is ready for camera interaction.")
            self._style_camera_overlay_v27()
            return

        projected_corners = [camera_orbit.project(row, self._camera_basis_v29) for row in geometry["corners"]]
        min_x = min(row[0] for row in projected_corners)
        max_x = max(row[0] for row in projected_corners)
        min_y = min(row[1] for row in projected_corners)
        max_y = max(row[1] for row in projected_corners)
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)
        scale = min((width - 50) / span_x, (height - 50) / span_y) * self._wire_zoom
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        screen_center_x = width / 2.0 + self._wire_pan_x * width
        screen_center_y = height / 2.0 + self._wire_pan_y * height

        limit = 1200 if self._camera_interacting else 6000
        faces, indices = geometry["samples"][limit]
        screen: dict[int, tuple[float, float, float]] = {}
        for index in indices:
            x, y, depth = camera_orbit.project(geometry["vertices"][index], self._camera_basis_v29)
            screen[index] = (
                (x - center_x) * scale + screen_center_x,
                screen_center_y - (y - center_y) * scale,
                depth,
            )
        displayed = 0
        _rgba, _canvas, text_color, line_color = self._background_values_v25()
        for face in faces:
            if not isinstance(face, (list, tuple)) or len(face) < 3:
                continue
            a, b, c = (int(face[0]), int(face[1]), int(face[2]))
            if a not in screen or b not in screen or c not in screen:
                continue
            points = (screen[a], screen[b], screen[c])
            canvas.create_line(
                points[0][0], points[0][1], points[1][0], points[1][1],
                points[2][0], points[2][1], points[0][0], points[0][1],
                fill=line_color, width=1,
            )
            displayed += 1
        canvas.create_text(
            10,
            10,
            anchor="nw",
            fill=text_color,
            text=f"Camera-relative wireframe {displayed:,}/{geometry['faces_total']:,} faces",
        )
        renderer_v3.set_preview_camera_basis(camera_orbit.flatten_basis(self._camera_basis_v29))
        self._style_camera_overlay_v27()

    # ------------------------------------------------------------------
    # Durable pose/view and notes against the focused asset.
    # ------------------------------------------------------------------
    def _save_pose_view_for_row_v26(self, row: dict[str, Any]) -> None:
        project = self._require_project()
        if project is None:
            return
        animation = self.animation_name.get().strip() or "Initial Pose"
        frame = max(0, int(self.animation_frame.get())) if animation != "Initial Pose" else 0
        background = self.preview_background_var.get() if self.preview_background_var is not None else "Dark Gray"
        save_annotation(
            project,
            row["absolute_path"],
            default_animation=animation,
            default_frame=frame,
            camera_yaw=self._wire_yaw,
            camera_pitch=self._wire_pitch,
            camera_zoom=self._wire_zoom,
            camera_pan_x=self._wire_pan_x,
            camera_pan_y=self._wire_pan_y,
            camera_background=background,
            camera_basis=list(camera_orbit.flatten_basis(self._camera_basis_v29)),
            persist=False,
        )
        self._refresh_annotation_marker_v26(row)
        self._visual_context_row = None
        self._visual_context_rows_v25 = []
        self._queue_annotation_persist_v24()
        self._sync_camera_panel_v29()
        self.visual_status.set(
            f"Saved {row['name']} pose, frame, camera-relative orientation, zoom, pan and background."
        )

    def _visual_asset_selected(self, event: tk.Event) -> None:
        super()._visual_asset_selected(event)
        row = self._selected_visual_row()
        self._load_note_panel_v29(row)
        self._sync_camera_panel_v29()

    def _load_note_panel_v29(self, row: dict[str, Any] | None) -> None:
        if self._note_text_v29 is None or self._note_asset_v29 is None:
            return
        self._note_text_v29.configure(state="normal")
        self._note_text_v29.delete("1.0", "end")
        if row is None or self.project is None:
            self._note_asset_v29.set("No asset selected")
        else:
            annotation = load_annotation(self.project, row["absolute_path"])
            self._note_asset_v29.set(f"{row['name']} — {row.get('kind') or 'Unknown CCSF'}")
            self._note_text_v29.insert("1.0", annotation.get("notes") or "")
        self._note_text_v29.edit_modified(False)
        self._note_dirty_v29 = False

    def _note_modified_v29(self, _event: tk.Event) -> None:
        if self._note_text_v29 is None:
            return
        if self._note_text_v29.edit_modified():
            self._note_dirty_v29 = True
            self._note_text_v29.edit_modified(False)

    def _save_notes_v29(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None or row is None or self._note_text_v29 is None:
            return
        value = self._note_text_v29.get("1.0", "end-1c")
        save_annotation(project, row["absolute_path"], notes=value, persist=False)
        self._refresh_annotation_marker_v26(row)
        self._queue_annotation_persist_v24()
        self._note_dirty_v29 = False
        self.visual_status.set(f"Saved {len(value):,} note character(s) for {row['name']}; the note is visible in the list.")

    def _edit_context_notes(self) -> None:
        row = self._selected_visual_row()
        self._load_note_panel_v29(row)
        if self._camera_panel_tab_v29 is not None:
            self._visual_details_notebook.select(self._camera_panel_tab_v29)
        if self._note_text_v29 is not None:
            self._note_text_v29.focus_set()


def main() -> int:
    app = PublicFragmenterAppV29()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

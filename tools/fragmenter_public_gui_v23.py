#!/usr/bin/env python3
"""Twenty-third public GUI pass: durable classification and stable asset review."""
from __future__ import annotations

import re
from pathlib import Path
import tkinter as tk
from tkinter import simpledialog
from typing import Any

import ccsf_textured_scene_v9 as scene_v9
import ccsf_wireframe_scene_v2 as wireframe_v2
import fragmenter_public_gui_v3 as gui_v3
import fragmenter_public_gui_v4 as gui_v4
import fragmenter_public_gui_v18 as gui_v18
from asset_classifier_v2 import CATEGORY_ORDER, category_sort_key, classify_visual_asset
from fragmenter_public_gui_v22 import PublicFragmenterAppV22
from visual_asset_annotations_v1 import (
    apply_annotation,
    custom_categories,
    ensure_category,
    load_annotation,
    save_annotation,
)


def _natural_key(value: Any) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", str(value or "")))


def discover_visual_assets_v23(project, query: str = "", category: str = "All", limit: int = 30_000) -> list[dict[str, Any]]:
    """Classify every discovered row before filtering and apply durable overrides."""
    rows = gui_v18._ORIGINAL_DISCOVER(project, query=query, category="All", limit=max(100_000, int(limit)))
    metadata = gui_v3._asset_metadata_by_path(project)
    output: list[dict[str, Any]] = []
    for row in rows:
        source = str(Path(row["absolute_path"]).resolve())
        asset = metadata.get(source, {})
        classification = classify_visual_asset(
            name=str(row.get("name") or ""),
            relative_path=str(row.get("relative_path") or ""),
            existing_kind=str(asset.get("type") or row.get("legacy_kind") or row.get("kind") or ""),
            resource_counts=asset.get("resource_counts") if isinstance(asset.get("resource_counts"), dict) else row.get("resource_counts"),
            identifiers=list(asset.get("identifiers") or []),
            size=int(row.get("size") or 0),
        )
        automatic = {
            **row,
            "kind": classification["category"],
            "classification_confidence": classification["confidence"],
            "classification_evidence": classification["evidence"],
            "classification_source": classification["classification_source"],
            "automatic_kind": classification["category"],
            "automatic_classification_confidence": classification["confidence"],
            "automatic_classification_evidence": classification["evidence"],
            "automatic_classification_source": classification["classification_source"],
        }
        annotated = apply_annotation(project, automatic)
        if category != "All" and str(annotated.get("kind") or "") != category:
            continue
        output.append(annotated)
    output.sort(
        key=lambda row: (
            category_sort_key(str(row.get("kind") or "")),
            _natural_key(row.get("name")),
            _natural_key(row.get("relative_path")),
        )
    )
    return output[: max(1, int(limit))]


# PublicFragmenterAppV4 resolves this global dynamically during every refresh.
gui_v4.discover_visual_assets_v3 = discover_visual_assets_v23


class PublicFragmenterAppV23(PublicFragmenterAppV22):
    """Make asset organization immediate and keep valid geometry on screen."""

    def __init__(self) -> None:
        self._wireframe_by_source: dict[str, dict[str, Any]] = {}
        self._right_orbit_axis: str | None = None
        self._suppress_visual_selection_v23 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Classified Textured 3D Review")

    # ------------------------------------------------------------------
    # Durable, in-place user classification
    # ------------------------------------------------------------------
    def _refresh_category_values_v23(self) -> None:
        project = self.project
        if project is None:
            return
        custom = [name for name in custom_categories(project) if name not in CATEGORY_ORDER]
        values = ("All", *CATEGORY_ORDER, *custom)
        self.visual_category_combo.configure(values=values)
        if self.visual_category.get() not in values:
            self.visual_category.set("All")

    def _cached_visual_rows(self) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for row in self.visual_payloads.values():
            path = str(Path(row["absolute_path"]).resolve())
            unique[path] = dict(row)
        return list(unique.values())

    def _release_selection_suppression_v23(self) -> None:
        self._suppress_visual_selection_v23 = False

    def _rebuild_visual_tree_cached(self, rows: list[dict[str, Any]], *, selected_source: str | None, message: str) -> None:
        category_filter = self.visual_category.get()
        visible = [row for row in rows if category_filter == "All" or str(row.get("kind") or "") == category_filter]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in visible:
            grouped.setdefault(str(row.get("kind") or "Unknown CCSF"), []).append(row)

        self.visual_tree.delete(*self.visual_tree.get_children())
        self.visual_payloads.clear()
        selected_iid: str | None = None
        asset_index = 0
        category_names = sorted(grouped, key=lambda value: (category_sort_key(value), value.casefold()))
        for group_index, kind in enumerate(category_names):
            children = sorted(grouped[kind], key=lambda row: (_natural_key(row.get("name")), _natural_key(row.get("relative_path"))))
            category_iid = f"category_cached_{group_index}"
            category_selected = any(str(Path(row["absolute_path"]).resolve()) == selected_source for row in children)
            self.visual_tree.insert(
                "",
                "end",
                iid=category_iid,
                text=kind,
                values=(f"{len(children):,} assets", "", ""),
                open=category_selected or category_filter != "All" or bool(self.visual_search.get().strip()),
            )
            for row in children:
                iid = f"asset_cached_{asset_index}"
                asset_index += 1
                self.visual_tree.insert(
                    category_iid,
                    "end",
                    iid=iid,
                    text=row["name"],
                    values=(
                        str(row.get("classification_confidence") or ""),
                        f"{int(row.get('size') or 0):,}",
                        row["relative_path"],
                    ),
                )
                self.visual_payloads[iid] = row
                if str(Path(row["absolute_path"]).resolve()) == selected_source:
                    selected_iid = iid
        if selected_iid is not None and self.visual_tree.exists(selected_iid):
            self._suppress_visual_selection_v23 = True
            self.visual_tree.selection_set(selected_iid)
            self.visual_tree.focus(selected_iid)
            self.visual_tree.see(selected_iid)
            self.after_idle(self._release_selection_suppression_v23)
        self.visual_progress.stop()
        self.visual_progress.configure(mode="determinate")
        self.visual_progress["value"] = 100.0
        self.visual_status.set(f"{message} Showing {len(visible):,} cached assets; no library or preview reload was performed.")

    def _apply_context_annotation_in_place(self, row: dict[str, Any], *, message: str) -> None:
        project = self._require_project()
        if project is None:
            return
        source = str(Path(row["absolute_path"]).resolve())
        rows = self._cached_visual_rows()
        updated = apply_annotation(project, row)
        replaced = False
        for index, candidate in enumerate(rows):
            if str(Path(candidate["absolute_path"]).resolve()) == source:
                rows[index] = updated
                replaced = True
                break
        if not replaced:
            rows.append(updated)
        self._visual_context_row = None
        self._refresh_category_values_v23()
        self._rebuild_visual_tree_cached(rows, selected_source=source, message=message)

    def _move_context_asset(self, category: str) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        if project is None or row is None:
            return
        category = ensure_category(project, category)
        save_annotation(project, row["absolute_path"], category=category)
        self._apply_context_annotation_in_place(row, message=f"Moved {row['name']} to {category}.")

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
        self._apply_context_annotation_in_place(row, message=f"Created {category} and moved {row['name']}.")

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
            dialog.destroy()
            self._apply_context_annotation_in_place(row, message=f"Saved notes for {row['name']}.")

        tk.Button(buttons, text="Save", command=save).pack(side="right")
        tk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))
        dialog.wait_window()

    # ------------------------------------------------------------------
    # Stable per-source wireframes
    # ------------------------------------------------------------------
    def _selected_source_v23(self) -> str | None:
        row = self._selected_visual_row()
        return str(Path(row["absolute_path"]).resolve()) if row is not None else None

    def _visual_asset_selected(self, event: tk.Event) -> None:
        if self._suppress_visual_selection_v23:
            return
        source = self._selected_source_v23()
        self._wireframe_payload = self._wireframe_by_source.get(source) if source else None
        super()._visual_asset_selected(event)

    def _wireframe_load(self, generation: int | None = None, *, allow_auto_texture: bool | None = None) -> None:
        row = self._selected_visual_row()
        if row is None:
            return
        if generation is not None and generation != self._wireframe_generation:
            return
        auto_after = generation is not None if allow_auto_texture is None else bool(allow_auto_texture)
        self._wireframe_generation += 1
        active_generation = self._wireframe_generation
        animation = self.animation_name.get().strip() if hasattr(self, "animation_name") else ""
        frame = max(0, int(self.animation_frame.get())) if hasattr(self, "animation_frame") else 0
        mode = scene_v9.SELECTED_CLUMP if self.scene_assembly_mode is not None and self.scene_assembly_mode.get() == "Selected Clump" else scene_v9.WHOLE_FILE
        source = str(Path(row["absolute_path"]).resolve())
        active_row = dict(row)
        self.visual_status.set(f"Building complete wireframe: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def done(payload: Any, error: Exception | None) -> None:
            if active_generation != self._wireframe_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            cached = self._wireframe_by_source.get(source)
            if error or not payload or not payload.get("vertices") or not payload.get("faces"):
                self.visual_progress["value"] = 0.0
                if cached is not None:
                    self._wireframe_payload = cached
                    self._preview_mode = "wireframe"
                    self._set_preview_mode_controls("wireframe")
                    self._draw_wireframe()
                    reason = str(error or "the redundant rebuild returned no renderable faces")
                    self.visual_status.set(f"Retained the previous valid wireframe for {row['name']}; rebuild failed: {reason}")
                else:
                    self._wireframe_payload = None
                    self._preview_mode = "wireframe"
                    self._set_preview_mode_controls("wireframe")
                    self._draw_wireframe()
                    reason = str(error or "no renderable model geometry")
                    self.visual_status.set(f"No wireframe geometry for {row['name']}: {reason}")
                return
            self.visual_progress["value"] = 100.0
            self._preview_mode = "wireframe"
            self._textured_scene = None
            self._textured_scene_row = None
            self._wireframe_payload = payload
            self._wireframe_by_source[source] = payload
            self._interactive_geometry_cache.clear()
            self._set_preview_mode_controls("wireframe")
            self._draw_wireframe()
            summary = payload.get("scene_summary") or {}
            self.visual_status.set(
                f"Wireframe ready: {payload.get('vertex_count', 0):,} vertices / "
                f"{payload.get('face_count', 0):,} submitted faces / {payload.get('decoded_face_count', 0):,} decoded | "
                f"{summary.get('model_instances', 0)} model instances"
            )
            if auto_after:
                self._schedule_auto_texture(active_row, payload, delay=100)

        self._local_worker(
            "stable-wireframe-v23",
            lambda: wireframe_v2.load_complete_wireframe_payload(
                source,
                animation_name=animation or None,
                frame=frame,
                assembly=mode,
                face_cap=60_000,
            ),
            done,
        )

    # ------------------------------------------------------------------
    # Axis-locked right-button orbit
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
        if self._right_orbit_axis is None:
            if max(abs(delta_x), abs(delta_y)) < 3:
                return
            self._right_orbit_axis = "horizontal" if abs(delta_x) >= abs(delta_y) else "vertical"
        if self._right_orbit_axis == "horizontal":
            self._wire_yaw -= delta_x * 0.008
        else:
            self._wire_pitch = max(-1.52, min(1.52, self._wire_pitch + delta_y * 0.008))
        self._right_orbit_drag = (event.x, event.y)
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"{self._right_orbit_axis.title()} orbit locked | yaw {self._wire_yaw:.2f}, pitch {self._wire_pitch:.2f} | release to texture"
        )

    def _right_orbit_release(self, _event: tk.Event) -> None:
        self._right_orbit_drag = None
        self._right_orbit_axis = None
        self._camera_interacting = False
        self._finish_camera_interaction()


def main() -> int:
    app = PublicFragmenterAppV23()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

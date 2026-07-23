#!/usr/bin/env python3
"""Twenty-fifth public GUI pass: batch review, pose defaults and complete x inventory."""
from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Any

import ccsf_textured_renderer_v3 as renderer_v3
import fragmenter_public_gui_v4 as gui_v4
import fragmenter_public_gui_v23 as gui_v23
from asset_classifier_v2 import CATEGORY_ORDER, category_sort_key, classify_visual_asset
from ccsf_asset_tree_v1 import inspect_ccsf_contents
from ccsf_gen1_pose_v5 import INITIAL_POSE_NAME
from fragmenter_public_gui_v24 import PublicFragmenterAppV24
from visual_asset_annotations_v1 import apply_annotation, custom_categories, load_annotation, save_annotation
from visual_classification_ledger_v1 import export_visual_classification_ledger
from x_series_inventory_v1 import export_x_series_inventory, filesystem_x_rows


def discover_visual_assets_v25(project, query: str = "", category: str = "All", limit: int = 30_000) -> list[dict[str, Any]]:
    """Include every x-family extracted file even when its extension is unfamiliar."""
    rows = gui_v23.discover_visual_assets_v23(project, query=query, category="All", limit=max(100_000, int(limit)))
    by_source = {str(Path(row["absolute_path"]).resolve()): dict(row) for row in rows}
    needle = query.strip().casefold().split()
    for xrow in filesystem_x_rows(project):
        source = str(Path(xrow["absolute_path"]).resolve())
        if source in by_source:
            continue
        haystack = f"{xrow['name']} {xrow['relative_path']} x{xrow['number']:03d}".casefold()
        if needle and not all(token in haystack for token in needle):
            continue
        classification = classify_visual_asset(
            name=str(xrow["name"]),
            relative_path=str(xrow["relative_path"]),
            existing_kind="x-series extracted file",
            size=int(xrow["size"]),
        )
        automatic = {
            "name": str(xrow["name"]),
            "kind": classification["category"],
            "legacy_kind": "x-series extracted file",
            "relative_path": str(xrow["relative_path"]),
            "absolute_path": source,
            "size": int(xrow["size"]),
            "source": "x-series filesystem inclusion",
            "resource_counts": {},
            "classification_confidence": classification["confidence"],
            "classification_evidence": classification["evidence"],
            "classification_source": classification["classification_source"],
            "automatic_kind": classification["category"],
            "automatic_classification_confidence": classification["confidence"],
            "automatic_classification_evidence": classification["evidence"],
            "automatic_classification_source": classification["classification_source"],
            "x_series_number": int(xrow["number"]),
            "known_visual_extension": bool(xrow["known_visual_extension"]),
        }
        by_source[source] = apply_annotation(project, automatic)
    output = [
        row
        for row in by_source.values()
        if category == "All" or str(row.get("kind") or "") == category
    ]
    output.sort(
        key=lambda row: (
            category_sort_key(str(row.get("kind") or "")),
            gui_v23._natural_key(row.get("name")),
            gui_v23._natural_key(row.get("relative_path")),
        )
    )
    return output[: max(1, int(limit))]


# PublicFragmenterAppV4 resolves this dynamically for each full refresh.
gui_v4.discover_visual_assets_v3 = discover_visual_assets_v25


class PublicFragmenterAppV25(PublicFragmenterAppV24):
    """Keep classification work local and expose source-backed pose review tools."""

    BACKGROUNDS = {
        "Black": ((0, 0, 0, 255), "#000000", "#EAF4FF", "#77C8FF"),
        "Dark Gray": ((24, 28, 32, 255), "#181C20", "#EAF4FF", "#77C8FF"),
        "Gray": ((112, 112, 112, 255), "#707070", "#FFFFFF", "#CFEFFF"),
        "White": ((255, 255, 255, 255), "#FFFFFF", "#151515", "#202020"),
    }

    def __init__(self) -> None:
        self._visual_context_rows_v25: list[dict[str, Any]] = []
        self.preview_background_var: tk.StringVar | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Batch Classified 3D / Animation Review")

    # ------------------------------------------------------------------
    # Complete x-family discovery and portable review records
    # ------------------------------------------------------------------
    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        self.visual_tree.configure(selectmode="extended")
        tools = ttk.Frame(parent)
        tools.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(tools, text="Export Classification Record", command=self._export_classifications_v25).pack(side="left")
        ttk.Button(tools, text="Audit X-Series", command=self._audit_x_series_v25).pack(side="left", padx=(6, 0))
        ttk.Label(tools, text="Ctrl+click / Shift+click selects multiple assets for a batch category move.").pack(side="right")

    def _all_cached_rows_v25(self) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for row in self.visual_payloads.values():
            unique[str(Path(row["absolute_path"]).resolve())] = dict(row)
        return list(unique.values())

    def _export_classifications_v25(self) -> None:
        project = self._require_project()
        if project is None:
            return
        rows = self._all_cached_rows_v25()
        self.visual_status.set("Exporting portable classification JSON/CSV ledger…")

        def done(result: Any, error: Exception | None) -> None:
            if error:
                self.visual_status.set(f"Classification export failed: {error}")
                messagebox.showerror("Export Classification Record", str(error))
                return
            self.visual_status.set(f"Classification ledger ready: {result['record_count']} saved asset record(s).")
            messagebox.showinfo("Export Classification Record", f"Created:\n{result['zip_path']}")

        self._local_worker(
            "visual-classification-ledger-v25",
            lambda: export_visual_classification_ledger(project, rows),
            done,
        )

    def _audit_x_series_v25(self) -> None:
        project = self._require_project()
        if project is None:
            return
        rows = self._all_cached_rows_v25()
        self.visual_status.set("Auditing x000-x999 files, browser coverage and asset-library identifiers…")

        def done(result: Any, error: Exception | None) -> None:
            if error:
                self.visual_status.set(f"X-series audit failed: {error}")
                messagebox.showerror("Audit X-Series", str(error))
                return
            self.visual_status.set(
                f"X-series audit: {result['filesystem_file_count']} files / {result['file_number_count']} numbers; "
                f"{result['files_not_in_browser_count']} file(s) absent from the current browser snapshot."
            )
            messagebox.showinfo("Audit X-Series", f"Created:\n{result['zip_path']}")

        self._local_worker("x-series-inventory-v25", lambda: export_x_series_inventory(project, rows), done)

    # ------------------------------------------------------------------
    # Preview contrast background
    # ------------------------------------------------------------------
    def _build_preview_toolbar(self, preview) -> None:
        super()._build_preview_toolbar(preview)
        bar = preview.grid_slaves(row=0, column=0)[0]
        self.preview_background_var = tk.StringVar(value="Dark Gray")
        ttk.Label(bar, text="Background").pack(side="left", padx=(12, 4))
        combo = ttk.Combobox(
            bar,
            textvariable=self.preview_background_var,
            values=tuple(self.BACKGROUNDS),
            state="readonly",
            width=10,
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _event: self._preview_background_changed_v25())
        self._preview_background_changed_v25(render=False)

    def _background_values_v25(self) -> tuple[tuple[int, int, int, int], str, str, str]:
        choice = self.preview_background_var.get() if self.preview_background_var is not None else "Dark Gray"
        return self.BACKGROUNDS.get(choice, self.BACKGROUNDS["Dark Gray"])

    def _preview_background_changed_v25(self, *, render: bool = True) -> None:
        rgba, canvas_color, _text_color, _line_color = self._background_values_v25()
        renderer_v3.set_preview_background(rgba)
        if hasattr(self, "visual_canvas"):
            self.visual_canvas.configure(background=canvas_color)
        if not render:
            return
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._progressive_render_generation += 1
            self._camera_render_generation += 1
            self._queue_camera_render(10)
        else:
            self._draw_wireframe()

    def _recolor_canvas_overlay_v25(self) -> None:
        _rgba, _canvas_color, text_color, line_color = self._background_values_v25()
        for item in self.visual_canvas.find_all():
            kind = self.visual_canvas.type(item)
            try:
                if kind == "text":
                    self.visual_canvas.itemconfigure(item, fill=text_color)
                elif kind == "line":
                    self.visual_canvas.itemconfigure(item, fill=line_color)
            except tk.TclError:
                continue

    def _draw_interactive_wireframe(self) -> None:
        super()._draw_interactive_wireframe()
        self._recolor_canvas_overlay_v25()

    def _show_low_resolution_png(self, path: Path, label: str) -> None:
        super()._show_low_resolution_png(path, label)
        self._recolor_canvas_overlay_v25()

    # ------------------------------------------------------------------
    # Extended-selection context menu and local-preserving batch moves
    # ------------------------------------------------------------------
    def _selected_context_rows_v25(self) -> list[dict[str, Any]]:
        if self._visual_context_rows_v25:
            return [dict(row) for row in self._visual_context_rows_v25]
        return [dict(self.visual_payloads[iid]) for iid in self.visual_tree.selection() if iid in self.visual_payloads]

    def _show_visual_context_menu(self, event: tk.Event) -> None:
        iid = self.visual_tree.identify_row(event.y)
        row = self.visual_payloads.get(iid)
        if row is None:
            return
        selected = set(self.visual_tree.selection())
        if iid not in selected:
            self.visual_tree.selection_set(iid)
            selected = {iid}
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
            menu.add_command(label="Use current animation frame as default pose", command=self._save_current_pose_v25)
            annotation = load_annotation(project, row["absolute_path"])
            if annotation.get("default_animation"):
                menu.add_command(label="Clear saved default pose", command=self._clear_default_pose_v25)
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

    def _local_anchor_v25(self, selected_iids: list[str]) -> str | None:
        focus = self.visual_tree.focus()
        primary = focus if focus in selected_iids else (selected_iids[0] if selected_iids else "")
        if not primary or not self.visual_tree.exists(primary):
            return None
        parent = self.visual_tree.parent(primary)
        siblings = list(self.visual_tree.get_children(parent))
        selected_set = set(selected_iids)
        try:
            index = siblings.index(primary)
        except ValueError:
            index = 0
        for candidate in siblings[index + 1 :]:
            if candidate not in selected_set:
                return candidate
        for candidate in reversed(siblings[:index]):
            if candidate not in selected_set:
                return candidate
        return None

    def _move_context_asset(self, category: str) -> None:
        project = self._require_project()
        rows = self._selected_context_rows_v25()
        normalized = str(category or "").strip()
        if project is None or not rows or not normalized:
            return
        self._batch_move_rows_v25(rows, normalized)

    def _create_context_category(self) -> None:
        project = self._require_project()
        rows = self._selected_context_rows_v25()
        if project is None or not rows:
            return
        value = simpledialog.askstring("Create visual category", "Category name:", parent=self)
        normalized = str(value or "").strip()
        if not normalized:
            return
        self._batch_move_rows_v25(rows, normalized)

    def _batch_move_rows_v25(self, rows: list[dict[str, Any]], category: str) -> None:
        project = self._require_project()
        if project is None:
            return
        selected_iids = [
            iid
            for iid in self.visual_tree.selection()
            if iid in self.visual_payloads
        ]
        anchor = self._local_anchor_v25(selected_iids)
        yview = self.visual_tree.yview()
        old_parents: set[str] = set()
        destination = self._ensure_category_node_v24(category)
        category_filter = self.visual_category.get()
        self._suppress_visual_selection_v23 = True

        for row in rows:
            source = self._source_token_v24(row)
            iid = self._asset_iid_for_source_v24(source)
            save_annotation(project, row["absolute_path"], category=category, persist=False)
            updated = apply_annotation(project, self._automatic_row_v24(row))
            if iid is None or not self.visual_tree.exists(iid):
                continue
            old_parent = self.visual_tree.parent(iid)
            old_parents.add(old_parent)
            if category_filter != "All" and category != category_filter:
                self.visual_tree.delete(iid)
                self.visual_payloads.pop(iid, None)
                continue
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
            self._move_asset_sorted_v24(iid, destination, updated)

        for parent in old_parents:
            if parent != destination:
                self._update_category_count_v24(parent)
        self._update_category_count_v24(destination)
        self._refresh_category_values_v23()
        self._visual_context_rows_v25 = []
        self._visual_context_row = None
        if anchor and self.visual_tree.exists(anchor):
            self.visual_tree.selection_set(anchor)
            self.visual_tree.focus(anchor)
        else:
            self.visual_tree.selection_remove(*self.visual_tree.selection())
        if yview:
            self.visual_tree.yview_moveto(yview[0])
        self.after_idle(self._release_selection_suppression_v23)
        self.visual_status.set(
            f"Moved {len(rows)} asset{'s' if len(rows) != 1 else ''} to {category}; retained the current list position."
        )
        self._queue_annotation_persist_v24()

    # ------------------------------------------------------------------
    # Source-backed default pose selection
    # ------------------------------------------------------------------
    @staticmethod
    def _preferred_animation_name_v25(names: tuple[str, ...], saved: str = "") -> str:
        if saved and saved in names:
            return saved
        for token in ("idle", "nut", "stand", "wait", "default"):
            match = next((name for name in names if token in name.casefold()), None)
            if match:
                return match
        return names[0] if names else INITIAL_POSE_NAME

    def _load_selected_ccsf_contents(self) -> None:
        row = self._selected_visual_row()
        self._stop_animation()
        self._ccsf_tree_generation += 1
        generation = self._ccsf_tree_generation
        self._clear_ccsf_contents()
        if row is None:
            return
        self.visual_status.set(f"Reading objects, textures and source-backed animations: {row['name']}…")

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._ccsf_tree_generation:
                return
            if error:
                self.visual_status.set(f"CCSF contents failed: {error}")
                return
            self._ccsf_contents_model = model
            self._populate_ccsf_contents(model)
            animations = [item for item in model.get("animations") or [] if isinstance(item, dict) and item.get("pose_ready")]
            self._animation_rows_by_name = {str(item.get("object_name") or item.get("object_id")): item for item in animations}
            animation_names = tuple(self._animation_rows_by_name)
            self.animation_combo.configure(values=(INITIAL_POSE_NAME, *animation_names))
            annotation = load_annotation(self.project, row["absolute_path"]) if self.project is not None else {}
            preferred = self._preferred_animation_name_v25(animation_names, str(annotation.get("default_animation") or ""))
            frame = max(0, int(annotation.get("default_frame") or 0))
            self.animation_name.set(preferred)
            self._configure_animation_range()
            animation_row = self._animation_rows_by_name.get(preferred)
            frame_count = max(1, int((animation_row or {}).get("frame_count") or 1))
            frame = min(frame, frame_count - 1)
            self.animation_frame.set(frame)
            self.animation_frame_scale.set(frame)
            self._update_animation_frame_label(frame)
            summary = model.get("summary") or {}
            if animation_row is not None:
                self.visual_status.set(
                    f"CCSF indexed: {summary.get('clumps', 0)} clumps, {summary.get('textures', 0)} textures, "
                    f"{summary.get('animations', 0)} animations. Default source pose: {preferred} frame {frame}."
                )
                self.after_idle(lambda: self._request_animation_frame(frame))
            else:
                self.animation_name.set(INITIAL_POSE_NAME)
                self.visual_status.set(
                    f"CCSF indexed: {summary.get('clumps', 0)} clumps, {summary.get('textures', 0)} textures; no pose-ready animation."
                )

        self._local_worker("ccsf-contents-v25", lambda: inspect_ccsf_contents(row["absolute_path"]), done)

    def _save_current_pose_v25(self) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        animation = self.animation_name.get().strip()
        if project is None or row is None or not animation or animation == INITIAL_POSE_NAME:
            messagebox.showinfo("Default Pose", "Select a decoded animation frame first.")
            return
        frame = max(0, int(self.animation_frame.get()))
        save_annotation(
            project,
            row["absolute_path"],
            default_animation=animation,
            default_frame=frame,
            persist=False,
        )
        self._queue_annotation_persist_v24()
        self.visual_status.set(f"Saved default pose for {row['name']}: {animation} frame {frame}.")

    def _clear_default_pose_v25(self) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        if project is None or row is None:
            return
        save_annotation(project, row["absolute_path"], default_animation="", default_frame=0, persist=False)
        self._queue_annotation_persist_v24()
        self.visual_status.set(f"Cleared the saved default pose for {row['name']}.")


def main() -> int:
    app = PublicFragmenterAppV25()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

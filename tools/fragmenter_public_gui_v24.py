#!/usr/bin/env python3
"""Twenty-fourth public GUI pass: constant-time visual category edits."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import simpledialog
from typing import Any

from asset_classifier_v2 import CATEGORY_ORDER, category_sort_key
from fragmenter_public_gui_v23 import PublicFragmenterAppV23, _natural_key
from project_workspace_v1 import save_project
from visual_asset_annotations_v1 import apply_annotation, custom_categories, load_annotation, save_annotation


class PublicFragmenterAppV24(PublicFragmenterAppV23):
    """Move one asset row instead of rebuilding the complete Treeview."""

    def __init__(self) -> None:
        self._live_category_counter_v24 = 0
        self._annotation_save_busy_v24 = False
        self._annotation_save_pending_v24 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Responsive Classified 3D Review")

    # ------------------------------------------------------------------
    # Serialized background persistence
    # ------------------------------------------------------------------
    def _queue_annotation_persist_v24(self) -> None:
        self._annotation_save_pending_v24 = True
        if not self._annotation_save_busy_v24:
            self._start_annotation_persist_v24()

    def _start_annotation_persist_v24(self) -> None:
        project = self.project
        if project is None or self._annotation_save_busy_v24 or not self._annotation_save_pending_v24:
            return
        self._annotation_save_pending_v24 = False
        self._annotation_save_busy_v24 = True

        def done(_result: Any, error: Exception | None) -> None:
            self._annotation_save_busy_v24 = False
            if error:
                self.visual_status.set(f"Category is updated in memory, but project.json could not be saved: {error}")
            if self._annotation_save_pending_v24:
                self.after_idle(self._start_annotation_persist_v24)

        self._local_worker("persist-visual-annotations-v24", lambda: save_project(project), done)

    # ------------------------------------------------------------------
    # Incremental Treeview organization
    # ------------------------------------------------------------------
    @staticmethod
    def _source_token_v24(row: dict[str, Any]) -> str:
        return str(Path(row["absolute_path"]).expanduser().resolve())

    def _asset_iid_for_source_v24(self, source: str) -> str | None:
        for iid in self.visual_tree.selection():
            row = self.visual_payloads.get(iid)
            if row is not None and self._source_token_v24(row) == source:
                return iid
        for iid, row in self.visual_payloads.items():
            if self._source_token_v24(row) == source:
                return iid
        return None

    def _category_iid_v24(self, category: str) -> str | None:
        for iid in self.visual_tree.get_children(""):
            if str(self.visual_tree.item(iid, "text")) == category:
                return iid
        return None

    def _sort_category_roots_v24(self) -> None:
        roots = list(self.visual_tree.get_children(""))
        roots.sort(
            key=lambda iid: (
                category_sort_key(str(self.visual_tree.item(iid, "text"))),
                str(self.visual_tree.item(iid, "text")).casefold(),
            )
        )
        for index, iid in enumerate(roots):
            self.visual_tree.move(iid, "", index)

    def _ensure_category_node_v24(self, category: str) -> str:
        existing = self._category_iid_v24(category)
        if existing is not None:
            return existing
        while True:
            iid = f"category_live_v24_{self._live_category_counter_v24}"
            self._live_category_counter_v24 += 1
            if not self.visual_tree.exists(iid):
                break
        self.visual_tree.insert(
            "",
            "end",
            iid=iid,
            text=category,
            values=("0 assets", "", ""),
            open=True,
        )
        self._sort_category_roots_v24()
        return iid

    def _update_category_count_v24(self, category_iid: str | None) -> None:
        if not category_iid or not self.visual_tree.exists(category_iid):
            return
        children = self.visual_tree.get_children(category_iid)
        if not children:
            self.visual_tree.delete(category_iid)
            return
        values = list(self.visual_tree.item(category_iid, "values") or ())
        while len(values) < 3:
            values.append("")
        values[0] = f"{len(children):,} assets"
        self.visual_tree.item(category_iid, values=tuple(values))

    def _move_asset_sorted_v24(self, iid: str, category_iid: str, row: dict[str, Any]) -> None:
        new_key = (_natural_key(row.get("name")), _natural_key(row.get("relative_path")))
        siblings = [child for child in self.visual_tree.get_children(category_iid) if child != iid]
        index = len(siblings)
        for candidate_index, sibling in enumerate(siblings):
            sibling_row = self.visual_payloads.get(sibling)
            if sibling_row is None:
                continue
            sibling_key = (
                _natural_key(sibling_row.get("name")),
                _natural_key(sibling_row.get("relative_path")),
            )
            if new_key < sibling_key:
                index = candidate_index
                break
        self.visual_tree.move(iid, category_iid, index)

    def _automatic_row_v24(self, row: dict[str, Any]) -> dict[str, Any]:
        base = dict(row)
        if row.get("automatic_kind"):
            base["kind"] = row["automatic_kind"]
            base["classification_confidence"] = row.get("automatic_classification_confidence", "")
            base["classification_source"] = row.get("automatic_classification_source", "")
            base["classification_evidence"] = row.get("automatic_classification_evidence", [])
        return base

    def _apply_annotation_incremental_v24(self, row: dict[str, Any], *, message: str) -> None:
        project = self._require_project()
        if project is None:
            return
        source = self._source_token_v24(row)
        iid = self._asset_iid_for_source_v24(source)
        updated = apply_annotation(project, self._automatic_row_v24(row))
        self._visual_context_row = None
        self._refresh_category_values_v23()

        if iid is None:
            self.visual_status.set(f"{message} The saved override will appear on the next asset refresh.")
            self._queue_annotation_persist_v24()
            return

        old_parent = self.visual_tree.parent(iid)
        category_filter = self.visual_category.get()
        destination_category = str(updated.get("kind") or "Unknown CCSF")
        self._suppress_visual_selection_v23 = True

        if category_filter != "All" and destination_category != category_filter:
            self.visual_tree.delete(iid)
            self.visual_payloads.pop(iid, None)
            self._update_category_count_v24(old_parent)
            self.after_idle(self._release_selection_suppression_v23)
            self.visual_status.set(
                f"{message} Hidden because the current filter is {category_filter}; no library or preview reload was performed."
            )
            self._queue_annotation_persist_v24()
            return

        destination = self._ensure_category_node_v24(destination_category)
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
        if old_parent != destination:
            self._update_category_count_v24(old_parent)
        self._update_category_count_v24(destination)
        self.visual_tree.selection_set(iid)
        self.visual_tree.focus(iid)
        self.visual_tree.see(iid)
        self.after_idle(self._release_selection_suppression_v23)
        self.visual_progress.stop()
        self.visual_progress.configure(mode="determinate")
        self.visual_progress["value"] = 100.0
        self.visual_status.set(f"{message} Updated one row immediately; project save is running in the background.")
        self._queue_annotation_persist_v24()

    def _move_context_asset(self, category: str) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        normalized = str(category or "").strip()
        if project is None or row is None or not normalized:
            return
        save_annotation(project, row["absolute_path"], category=normalized, persist=False)
        self._apply_annotation_incremental_v24(row, message=f"Moved {row['name']} to {normalized}.")

    def _create_context_category(self) -> None:
        project = self._require_project()
        row = self._selected_context_row()
        if project is None or row is None:
            return
        value = simpledialog.askstring("Create visual category", "Category name:", parent=self)
        normalized = str(value or "").strip()
        if not normalized:
            return
        save_annotation(project, row["absolute_path"], category=normalized, persist=False)
        self._apply_annotation_incremental_v24(
            row,
            message=f"Created {normalized} and moved {row['name']}.",
        )

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
            save_annotation(
                project,
                row["absolute_path"],
                notes=text.get("1.0", "end-1c"),
                persist=False,
            )
            dialog.destroy()
            self._apply_annotation_incremental_v24(row, message=f"Saved notes for {row['name']}.")

        tk.Button(buttons, text="Save", command=save).pack(side="right")
        tk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))
        dialog.wait_window()


def main() -> int:
    app = PublicFragmenterAppV24()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

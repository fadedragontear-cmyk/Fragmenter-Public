#!/usr/bin/env python3
"""Thirty-seventh public GUI pass: final visual archive and selected 2D textures."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from ccsf_texture_audit_v1 import audit_texture_links
from ccsf_texture_preview_v1 import export_texture_preview
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v36 import PublicFragmenterAppV36


class PublicFragmenterAppV37(PublicFragmenterAppV36):
    """Close visual implementation with one Research tab and read-only TEX previews."""

    _VISUAL_RESEARCH_BUTTONS = {
        "Audit X-Series",
        "Texture Audit",
        "Texture Mapping Audit",
        "Export Classification Record",
        "Classification Report",
    }

    def __init__(self) -> None:
        self._research_tab_v37: ttk.Frame | None = None
        self._visual_archive_panel_v37: ttk.LabelFrame | None = None
        self._texture_audit_output_v37: tk.Text | None = None
        self._texture2d_generation_v37 = 0
        self._texture2d_path_v37: Path | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Visual Archive / Audio Next")

    def _build_tabs(self) -> None:
        # V33/V36 can create a visual Research tab while the 3D page is being built.
        # Finalize only after every normal top-level page has had a chance to build its
        # own Research page.
        super()._build_tabs()
        self._finalize_research_tabs_v37()

    @staticmethod
    def _descendant_count_v37(widget: tk.Misc) -> int:
        try:
            children = widget.winfo_children()
        except tk.TclError:
            return 0
        return len(children) + sum(
            PublicFragmenterAppV37._descendant_count_v37(child) for child in children
        )

    def _remove_visual_research_buttons_v37(self, widget: tk.Misc) -> None:
        try:
            children = tuple(widget.winfo_children())
        except tk.TclError:
            return
        for child in children:
            if isinstance(child, ttk.Button):
                try:
                    label = str(child.cget("text")).strip()
                except tk.TclError:
                    label = ""
                if label in self._VISUAL_RESEARCH_BUTTONS:
                    child.destroy()
                    continue
            self._remove_visual_research_buttons_v37(child)

    def _destroy_v36_panel_v37(self) -> None:
        for attribute in (
            "_research_actions_v36",
            "_research_description_v36",
            "_research_header_v36",
        ):
            widget = getattr(self, attribute, None)
            try:
                if widget is not None and bool(widget.winfo_exists()):
                    widget.destroy()
            except tk.TclError:
                pass
            setattr(self, attribute, None)

    def _finalize_research_tabs_v37(self) -> None:
        notebook = self.notebook
        candidates: list[tuple[int, str, ttk.Frame]] = []
        for index, tab_id in enumerate(tuple(notebook.tabs())):
            try:
                label = str(notebook.tab(tab_id, "text")).strip()
                widget = notebook.nametowidget(tab_id)
            except (tk.TclError, KeyError):
                continue
            if "research" in label.casefold() and isinstance(widget, ttk.Frame):
                candidates.append((index, str(tab_id), widget))

        if candidates:
            # Preserve the richest existing Research workspace. A tie keeps the later
            # tab, which is normally the audio/general Research page built after 3D.
            _index, keep_id, research = max(
                candidates,
                key=lambda item: (self._descendant_count_v37(item[2]), item[0]),
            )
            for _candidate_index, tab_id, duplicate in candidates:
                if tab_id == keep_id:
                    continue
                try:
                    notebook.forget(tab_id)
                    duplicate.destroy()
                except tk.TclError:
                    pass
            notebook.tab(keep_id, text="Research")
        else:
            research = ttk.Frame(notebook, padding=8)
            notebook.add(research, text="Research")

        self._destroy_v36_panel_v37()
        self._remove_visual_research_buttons_v37(self.tabs.get("3D / Assets", research))
        self._remove_visual_research_buttons_v37(research)
        self.tabs["Research"] = research
        self._research_tab_v33 = research
        self._research_tab_v37 = research
        research.columnconfigure(0, weight=1)

        current = self._visual_archive_panel_v37
        try:
            if current is not None and bool(current.winfo_exists()):
                current.destroy()
        except tk.TclError:
            pass

        occupied_rows: list[int] = []
        for child in research.grid_slaves():
            try:
                occupied_rows.append(int(child.grid_info().get("row", 0)))
            except (tk.TclError, TypeError, ValueError):
                continue
        row = max(occupied_rows, default=-1) + 1

        panel = ttk.LabelFrame(research, text="Completed 3D / visual archive", padding=8)
        panel.grid(row=row, column=0, sticky="nsew", pady=(8, 0))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        ttk.Label(
            panel,
            text=(
                "Final classification exports and read-only extraction/texture evidence. "
                "The active 3D implementation is frozen while work returns to audio."
            ),
            wraplength=950,
        ).grid(row=0, column=0, sticky="w", pady=(0, 7))
        actions = ttk.Frame(panel)
        actions.grid(row=1, column=0, sticky="w", pady=(0, 7))
        ttk.Button(
            actions,
            text="Classification Report",
            command=self._export_classifications_v25,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Audit X-Series",
            command=self._audit_x_series_v25,
        ).pack(side="left", padx=(7, 0))
        ttk.Button(
            actions,
            text="Texture Mapping Audit",
            command=self._visual_texture_audit,
        ).pack(side="left", padx=(7, 0))

        output_frame = ttk.Frame(panel)
        output_frame.grid(row=2, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        output = tk.Text(output_frame, height=12, wrap="none")
        output_y = ttk.Scrollbar(output_frame, orient="vertical", command=output.yview)
        output_x = ttk.Scrollbar(output_frame, orient="horizontal", command=output.xview)
        output.configure(yscrollcommand=output_y.set, xscrollcommand=output_x.set)
        output.grid(row=0, column=0, sticky="nsew")
        output_y.grid(row=0, column=1, sticky="ns")
        output_x.grid(row=1, column=0, sticky="ew")
        _replace_text(
            output,
            "Select an extracted CCSF asset, then run Texture Mapping Audit.\n",
        )
        self._visual_archive_panel_v37 = panel
        self._texture_audit_output_v37 = output

    def _visual_texture_audit(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None:
            return
        if row is None:
            messagebox.showinfo(
                "Texture Mapping Audit",
                "Select an extracted CCSF asset first.",
            )
            return
        self._texture_audit_generation += 1
        generation = self._texture_audit_generation
        output = project.workspace_path("texture_outputs") / _safe_folder(
            str(row["relative_path"])
        )
        json_path = output / "texture_audit.json"
        text_path = output / "texture_audit.txt"
        self.visual_status.set(f"Auditing MAT/TEX/CLUT/UV links: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def work() -> Any:
            return audit_texture_links(
                row["absolute_path"],
                output_json=json_path,
                output_text=text_path,
            )

        def done(result: Any, error: Exception | None) -> None:
            if generation != self._texture_audit_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            target = self._texture_audit_output_v37
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Texture mapping audit failed: {error}")
                if target is not None:
                    _replace_text(target, str(error))
                return
            self.visual_progress["value"] = 100.0
            if target is not None:
                _replace_text(target, _json_text(result))
            if self._research_tab_v37 is not None:
                try:
                    self.notebook.select(self._research_tab_v37)
                except tk.TclError:
                    pass
            summary = result.get("summary") or {}
            issues = summary.get("issue_counts") or {}
            issue_text = ", ".join(
                f"{name}: {count}" for name, count in issues.items()
            ) or "none"
            self.visual_status.set(
                f"Texture mapping audit: {summary.get('decoded_textures', 0)}/"
                f"{summary.get('texture_records', 0)} TEX decoded; "
                f"{summary.get('clean_submodels', 0)}/{summary.get('submodels', 0)} "
                f"submodels clean; issues: {issue_text}."
            )

        self._local_worker("texture-audit-v37", work, done)

    def _ccsf_contents_selected(self) -> None:
        super()._ccsf_contents_selected()
        selected = self.ccsf_contents_tree.selection()
        iid = selected[0] if selected else ""
        node = self._ccsf_tree_payloads.get(iid)
        if not isinstance(node, dict) or str(node.get("kind") or "") != "texture":
            return
        details = node.get("details")
        details = details if isinstance(details, dict) else {}
        object_id = details.get("object_id")
        row = self._selected_visual_row()
        project = self.project
        if not isinstance(object_id, int) or row is None or project is None:
            return

        self._texture2d_generation_v37 += 1
        generation = self._texture2d_generation_v37
        self._stop_animation()
        self._cancel_camera_work()
        token = getattr(self, "_auto_texture_after", None)
        if token is not None:
            try:
                self.after_cancel(token)
            except tk.TclError:
                pass
            self._auto_texture_after = None
        self._preview_mode = "texture2d"
        if self.preview_wireframe_var is not None:
            self.preview_wireframe_var.set(False)
        if self.preview_textured_var is not None:
            self.preview_textured_var.set(False)

        target = (
            project.workspace_path("texture_outputs")
            / _safe_folder(str(row["relative_path"]))
            / "selected_textures"
            / f"texture_0x{object_id:X}.png"
        )
        self.visual_status.set(
            f"Decoding selected TEX 0x{object_id:X} into the 2D preview canvas…"
        )

        def done(result: Any, error: Exception | None) -> None:
            if generation != self._texture2d_generation_v37:
                return
            current = self.ccsf_contents_tree.selection()
            if not current or current[0] != iid:
                return
            if error:
                self.visual_status.set(f"Selected texture preview failed: {error}")
                return
            path = Path(result["output_path"])
            self._texture2d_path_v37 = path
            self._show_png_on_visual_canvas(path)
            self.visual_status.set(
                f"2D TEX 0x{object_id:X}: {result['width']}×{result['height']} "
                f"{result['texture_type']} | alpha {result['alpha_min']}–"
                f"{result['alpha_max']}. Use Wireframe or Textured to return."
            )

        self._local_worker(
            "selected-texture-v37",
            lambda: export_texture_preview(
                row["absolute_path"],
                object_id,
                target,
            ),
            done,
        )


def main() -> int:
    app = PublicFragmenterAppV37()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

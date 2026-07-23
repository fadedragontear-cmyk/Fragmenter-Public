#!/usr/bin/env python3
"""Sixth public GUI acceptance pass: texture-link evidence and raw PCM previews."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import fragmenter_public_gui_v5 as gui_v5
from ccsf_texture_audit_v1 import audit_texture_links
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v4 import _safe_folder
from fragmenter_public_gui_v5 import PublicFragmenterAppV5
from project_sound_v3 import analyze_or_extract_sound_item, build_project_sound_library
from run_all_executor_v5 import build_run_all_actions_v5, execute_run_all_v5

# V5 resolves these imported globals at method-call time. Keep the validated V5 UI
# behavior and replace only the public sound/RUN ALL integrations used by V6.
gui_v5.build_project_sound_library = build_project_sound_library
gui_v5.analyze_or_extract_sound_item = analyze_or_extract_sound_item
gui_v5.build_run_all_actions_v4 = build_run_all_actions_v5
gui_v5.execute_run_all_v4 = execute_run_all_v5


class PublicFragmenterAppV6(PublicFragmenterAppV5):
    def __init__(self) -> None:
        self._texture_audit_generation = 0
        self._visual_details_notebook: ttk.Notebook | None = None
        self.texture_audit_tab: ttk.Frame | None = None
        self.texture_audit_text: tk.Text | None = None
        super().__init__()

    def _build_visual(self, parent: ttk.Frame) -> None:
        super()._build_visual(parent)
        notebook = self.visual_details.master.master
        if isinstance(notebook, ttk.Notebook):
            self._visual_details_notebook = notebook
            self.texture_audit_tab = ttk.Frame(notebook)
            self.texture_audit_tab.rowconfigure(0, weight=1)
            self.texture_audit_tab.columnconfigure(0, weight=1)
            self.texture_audit_text = tk.Text(self.texture_audit_tab, height=10, wrap="none")
            yscroll = ttk.Scrollbar(self.texture_audit_tab, orient="vertical", command=self.texture_audit_text.yview)
            xscroll = ttk.Scrollbar(self.texture_audit_tab, orient="horizontal", command=self.texture_audit_text.xview)
            self.texture_audit_text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
            self.texture_audit_text.grid(row=0, column=0, sticky="nsew")
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll.grid(row=1, column=0, sticky="ew")
            notebook.add(self.texture_audit_tab, text="Texture Audit")

        self._add_texture_audit_button(parent)
        self.visual_canvas.bind("<Configure>", self._visual_canvas_resized_v6, add="+")

    def _add_texture_audit_button(self, widget: tk.Misc) -> bool:
        try:
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button) and str(child.cget("text")) == "Textured Preview":
                    ttk.Button(child.master, text="Texture Audit", command=self._visual_texture_audit).pack(side="left", padx=(6, 0))
                    return True
                if self._add_texture_audit_button(child):
                    return True
        except tk.TclError:
            return False
        return False

    def _visual_canvas_resized_v6(self, _event: tk.Event) -> None:
        if getattr(self, "_preview_mode", "wireframe") == "textured" and getattr(self, "_textured_scene", None) is not None:
            self.visual_status.set("Preview panel resized; waiting to rerender textured view…")
            self._schedule_textured_render(delay=350)

    def _visual_texture_audit(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None:
            return
        if row is None:
            messagebox.showinfo("Texture Audit", "Select an extracted CCSF asset first.")
            return
        self._texture_audit_generation += 1
        generation = self._texture_audit_generation
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"]))
        json_path = output / "texture_audit.json"
        text_path = output / "texture_audit.txt"
        self.visual_status.set(f"Auditing MAT/TEX/CLUT/UV links: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def work() -> Any:
            return audit_texture_links(row["absolute_path"], output_json=json_path, output_text=text_path)

        def done(result: Any, error: Exception | None) -> None:
            if generation != self._texture_audit_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Texture audit failed: {error}")
                if self.texture_audit_text is not None:
                    _replace_text(self.texture_audit_text, str(error))
                return
            self.visual_progress["value"] = 100.0
            if self.texture_audit_text is not None:
                _replace_text(self.texture_audit_text, _json_text(result))
            if self._visual_details_notebook is not None and self.texture_audit_tab is not None:
                self._visual_details_notebook.select(self.texture_audit_tab)
            summary = result.get("summary") or {}
            issues = summary.get("issue_counts") or {}
            issue_text = ", ".join(f"{name}: {count}" for name, count in issues.items()) or "none"
            self.visual_status.set(
                f"Texture audit: {summary.get('decoded_textures', 0)}/{summary.get('texture_records', 0)} TEX decoded; "
                f"{summary.get('clean_submodels', 0)}/{summary.get('submodels', 0)} submodels clean; issues: {issue_text}."
            )

        self._local_worker("texture-audit-v6", work, done)


def main() -> int:
    app = PublicFragmenterAppV6()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

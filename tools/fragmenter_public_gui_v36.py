#!/usr/bin/env python3
"""Thirty-sixth public GUI pass: canonical review data and restrained 3D cleanup."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from fragmenter_public_gui_v35 import PublicFragmenterAppV35


class PublicFragmenterAppV36(PublicFragmenterAppV35):
    """Close the current 3D review pass without changing its accepted workspace."""

    def __init__(self) -> None:
        self._research_header_v36: ttk.Label | None = None
        self._research_description_v36: ttk.Label | None = None
        self._research_actions_v36: ttk.Frame | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Canonical 3D Review")

    # V33 calls this through dynamic dispatch while constructing the 3D tab. Replacing
    # that one hook keeps the accepted layout intact and prevents Texture Audit from ever
    # being rebuilt in Research.
    def _move_audits_to_research_v33(self, visual_parent: tk.Misc) -> None:
        visible_research_actions = {
            "Audit X-Series",
            "Texture Audit",
            "Export Classification Record",
            "Classification Report",
        }

        def remove_legacy_buttons(widget: tk.Misc) -> None:
            try:
                children = widget.winfo_children()
            except tk.TclError:
                return
            for child in children:
                if isinstance(child, ttk.Button):
                    try:
                        text = str(child.cget("text"))
                    except tk.TclError:
                        text = ""
                    if text in visible_research_actions:
                        child.destroy()
                        continue
                remove_legacy_buttons(child)

        def destroy_current_panel() -> None:
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

        # Remove the inherited 3D toolbar actions before creating the single Research
        # authority. This leaves the accepted preview, notes, animation and camera UI alone.
        remove_legacy_buttons(visual_parent)

        notebook = self.notebook
        research_tabs: list[tuple[str, ttk.Frame]] = []
        for tab_id in tuple(notebook.tabs()):
            try:
                text = str(notebook.tab(tab_id, "text")).strip()
                candidate = notebook.nametowidget(tab_id)
            except (tk.TclError, KeyError):
                continue
            if text.casefold() == "research" and isinstance(candidate, ttk.Frame):
                research_tabs.append((str(tab_id), candidate))

        if research_tabs:
            _keep_id, research = research_tabs[0]
            for duplicate_id, duplicate in research_tabs[1:]:
                try:
                    notebook.forget(duplicate_id)
                    duplicate.destroy()
                except tk.TclError:
                    pass
        else:
            research = ttk.Frame(notebook, padding=8)
            notebook.add(research, text="Research")

        # A partial checkout or older GUI layer may already have populated the surviving
        # Research tab. Strip only the superseded actions, not unrelated research panels.
        destroy_current_panel()
        remove_legacy_buttons(research)

        self.tabs["Research"] = research
        self._research_tab_v33 = research
        research.columnconfigure(0, weight=1)

        occupied_rows: list[int] = []
        for child in research.grid_slaves():
            try:
                occupied_rows.append(int(child.grid_info().get("row", 0)))
            except (tk.TclError, TypeError, ValueError):
                continue
        row = max(occupied_rows, default=-1) + 1

        header = ttk.Label(research, text="Visual format research", font=("Segoe UI", 14, "bold"))
        header.grid(row=row, column=0, sticky="w", pady=(0, 8))
        description = ttk.Label(
            research,
            text=(
                "Classification records and extraction-coverage audits are kept here so "
                "the day-to-day 3D review toolbar stays focused."
            ),
            wraplength=900,
        )
        description.grid(row=row + 1, column=0, sticky="w", pady=(0, 10))
        actions = ttk.Frame(research)
        actions.grid(row=row + 2, column=0, sticky="w")
        ttk.Button(actions, text="Audit X-Series", command=self._audit_x_series_v25).pack(side="left")
        ttk.Button(
            actions,
            text="Classification Report",
            command=self._export_classifications_v25,
        ).pack(side="left", padx=(7, 0))
        self._research_header_v36 = header
        self._research_description_v36 = description
        self._research_actions_v36 = actions


def main() -> int:
    app = PublicFragmenterAppV36()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

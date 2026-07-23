#!/usr/bin/env python3
"""V80: restore full-height Celdra Test subtabs and harden vertical navigation."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from fragmenter_public_gui_v79 import PublicFragmenterAppV79


class PublicFragmenterAppV80(PublicFragmenterAppV79):
    """Give the Celdra authoring notebook the complete test-tab client area."""

    def __init__(self) -> None:
        self._celdra_geometry_after_v80: str | None = None
        self._celdra_geometry_bound_v80 = False
        self._celdra_scroll_bound_v80: set[str] = set()
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Authoring Workspace")
        self._schedule_celdra_geometry_repair_v80()

    # ------------------------------------------------------------------
    # The original V50 test page weighted row 1. V74 put the replacement
    # notebook in row 0 without clearing that weight, so Tk kept reserving
    # roughly half of the tab for an empty legacy row.
    # ------------------------------------------------------------------
    def _install_celdra_test_tab_v50(self) -> None:
        super()._install_celdra_test_tab_v50()
        self._repair_celdra_test_geometry_v80()
        self._schedule_celdra_geometry_repair_v80()

    def _schedule_celdra_geometry_repair_v80(self, _event: tk.Event | None = None) -> None:
        if self._celdra_geometry_after_v80 is not None:
            return

        def apply() -> None:
            self._celdra_geometry_after_v80 = None
            self._repair_celdra_test_geometry_v80()

        try:
            self._celdra_geometry_after_v80 = self.after_idle(apply)
        except tk.TclError:
            self._celdra_geometry_after_v80 = None

    def _repair_celdra_test_geometry_v80(self) -> None:
        frame = self.tabs.get("Celdra Test")
        notebook = getattr(self, "_celdra_author_notebook_v74", None)
        if frame is None or notebook is None:
            return

        try:
            # Remove every inherited row/column claim from the disposable V50
            # test layout. Only the authoring notebook owns space now.
            for row in range(12):
                frame.rowconfigure(row, weight=0, minsize=0, pad=0)
            for column in range(6):
                frame.columnconfigure(column, weight=0, minsize=0, pad=0)
            frame.rowconfigure(0, weight=1, minsize=160)
            frame.columnconfigure(0, weight=1, minsize=240)
            frame.grid_propagate(True)

            notebook.grid_configure(
                row=0,
                column=0,
                rowspan=1,
                columnspan=1,
                sticky="nsew",
                padx=0,
                pady=0,
            )
            notebook.tkraise()
            notebook.enable_traversal()
        except tk.TclError:
            return

        # Recalculate every scroll canvas after the notebook receives its real
        # height. This keeps scrollbar thumbs and page navigation accurate.
        self._refresh_author_scroll_regions_v80(notebook)
        if not self._celdra_geometry_bound_v80:
            try:
                frame.bind("<Configure>", self._schedule_celdra_geometry_repair_v80, add="+")
                notebook.bind(
                    "<<NotebookTabChanged>>",
                    self._schedule_celdra_geometry_repair_v80,
                    add="+",
                )
                self._celdra_geometry_bound_v80 = True
            except tk.TclError:
                pass

    @staticmethod
    def _walk_widgets_v80(widget: tk.Misc):
        yield widget
        for child in widget.winfo_children():
            yield from PublicFragmenterAppV80._walk_widgets_v80(child)

    def _refresh_author_scroll_regions_v80(self, root: tk.Misc) -> None:
        for widget in self._walk_widgets_v80(root):
            if not isinstance(widget, tk.Canvas):
                continue
            try:
                yscroll = str(widget.cget("yscrollcommand") or "")
            except tk.TclError:
                continue
            if not yscroll:
                continue
            try:
                bounds = widget.bbox("all")
                if bounds:
                    widget.configure(scrollregion=bounds, takefocus=True)
            except tk.TclError:
                continue
            self._bind_author_canvas_navigation_v80(widget)

    def _bind_author_canvas_navigation_v80(self, canvas: tk.Canvas) -> None:
        key = str(canvas)
        if key in self._celdra_scroll_bound_v80:
            return

        def page_up(_event: tk.Event) -> str:
            try:
                canvas.yview_scroll(-1, "pages")
            except tk.TclError:
                pass
            return "break"

        def page_down(_event: tk.Event) -> str:
            try:
                canvas.yview_scroll(1, "pages")
            except tk.TclError:
                pass
            return "break"

        def home(_event: tk.Event) -> str:
            try:
                canvas.yview_moveto(0.0)
            except tk.TclError:
                pass
            return "break"

        def end(_event: tk.Event) -> str:
            try:
                canvas.yview_moveto(1.0)
            except tk.TclError:
                pass
            return "break"

        try:
            canvas.bind("<Prior>", page_up, add="+")
            canvas.bind("<Next>", page_down, add="+")
            canvas.bind("<Home>", home, add="+")
            canvas.bind("<End>", end, add="+")
            canvas.bind("<Button-4>", lambda event: page_up(event), add="+")
            canvas.bind("<Button-5>", lambda event: page_down(event), add="+")
            self._celdra_scroll_bound_v80.add(key)
        except tk.TclError:
            pass

    def _cancel_celdra_cues_v49(self) -> None:
        if self._celdra_geometry_after_v80 is not None:
            try:
                self.after_cancel(self._celdra_geometry_after_v80)
            except tk.TclError:
                pass
            self._celdra_geometry_after_v80 = None
        super()._cancel_celdra_cues_v49()


def main() -> int:
    app = PublicFragmenterAppV80()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

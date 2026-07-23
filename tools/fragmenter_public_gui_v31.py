#!/usr/bin/env python3
"""Thirty-first public GUI pass: first-click activation and restored CCSF controls."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

from fragmenter_public_gui_v30 import PublicFragmenterAppV30


class PublicFragmenterAppV31(PublicFragmenterAppV30):
    """Keep one clicked-asset authority and replace controls destroyed by v29."""

    def __init__(self) -> None:
        self._clicked_asset_after_v31: str | None = None
        self._active_selection_source_v31: str | None = None
        self._scene_controls_v31: ttk.LabelFrame | None = None
        super().__init__()
        self.after_idle(self._install_left_look_bindings_v31)
        self.title("Fragmenter 1.0 WIP — First-Click CCSF / WASD Review")

    # ------------------------------------------------------------------
    # Layout repair. V29 removed the old camera bar because it contained the retired
    # Front/Side/Top controls, but that same frame also owned preview_clump_combo.
    # Recreate the clump selector in the active Camera/Pose tab so the CCSF loader has
    # a live widget and can populate clumps, animations and the contents tree again.
    # ------------------------------------------------------------------
    def _build_visual(self, parent) -> None:
        super()._build_visual(parent)
        self._install_scene_controls_v31()
        self._install_asset_click_authority_v31()
        self._install_left_look_bindings_v31()

    @staticmethod
    def _widget_alive_v31(widget: tk.Misc | None) -> bool:
        if widget is None:
            return False
        try:
            return bool(int(widget.winfo_exists()))
        except (tk.TclError, ValueError, TypeError):
            return False

    def _install_scene_controls_v31(self) -> None:
        target = self._camera_panel_frame_v29
        if target is None:
            return
        scene = ttk.LabelFrame(target, text="Scene assembly / CCSF", padding=7)
        scene.grid(row=3, column=0, sticky="ew", pady=(7, 0))
        scene.columnconfigure(1, weight=1)
        self._scene_controls_v31 = scene

        ttk.Label(scene, text="Preview clump").grid(row=0, column=0, sticky="w", padx=(0, 7))
        self.preview_clump_combo = ttk.Combobox(
            scene,
            textvariable=self.preview_clump_name,
            values=tuple(self._preview_clumps_by_label),
            state="readonly",
            width=42,
        )
        self.preview_clump_combo.grid(row=0, column=1, sticky="ew")
        self.preview_clump_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._preview_clump_selected(),
        )
        ttk.Button(
            scene,
            text="Reload Contents",
            command=self._reload_focused_contents_v31,
        ).grid(row=0, column=2, padx=(7, 0))
        ttk.Label(
            scene,
            textvariable=self.preview_clump_status,
            wraplength=520,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))

    def _reload_focused_contents_v31(self) -> None:
        self._active_selection_source_v31 = None
        self._activate_focused_asset_v31(force=True)

    def _clear_ccsf_contents(self) -> None:
        # Older code keeps a Python reference after Tk has destroyed the old camera
        # frame. Replace that stale reference with None before the inherited clear.
        if not self._widget_alive_v31(getattr(self, "preview_clump_combo", None)):
            self.preview_clump_combo = None
        super()._clear_ccsf_contents()

    # ------------------------------------------------------------------
    # First-click asset authority. ButtonPress runs before Treeview's class binding,
    # so focus is assigned to the row under the pointer before <<TreeviewSelect>>.
    # An after-idle fallback covers clicks on an already-selected row, where Tk may
    # not emit another virtual selection event. The source token coalesces duplicates.
    # ------------------------------------------------------------------
    def _install_asset_click_authority_v31(self) -> None:
        self.visual_tree.bind("<ButtonPress-1>", self._asset_button_press_v31, add="+")

    def _asset_button_press_v31(self, event: tk.Event) -> None:
        iid = self.visual_tree.identify_row(event.y)
        if not iid or iid not in self.visual_payloads:
            return
        self.visual_tree.focus(iid)
        if self._clicked_asset_after_v31 is not None:
            try:
                self.after_cancel(self._clicked_asset_after_v31)
            except tk.TclError:
                pass
        self._clicked_asset_after_v31 = self.after_idle(
            lambda selected_iid=iid: self._activate_clicked_iid_v31(selected_iid)
        )

    def _activate_clicked_iid_v31(self, iid: str) -> None:
        self._clicked_asset_after_v31 = None
        if not self.visual_tree.exists(iid) or iid not in self.visual_payloads:
            return
        self.visual_tree.focus(iid)
        self._activate_focused_asset_v31()

    def _source_for_row_v31(self, row: dict[str, Any] | None) -> str | None:
        if row is None:
            return None
        return str(Path(row["absolute_path"]).resolve())

    def _activate_focused_asset_v31(self, *, force: bool = False) -> None:
        row = self._selected_visual_row()
        source = self._source_for_row_v31(row)
        if source is None:
            return
        if not force and source == self._active_selection_source_v31:
            return
        self._visual_asset_selected(None)

    def _visual_asset_selected(self, event: tk.Event | None) -> None:
        if self._suppress_visual_selection_v23:
            return
        row = self._selected_visual_row()
        source = self._source_for_row_v31(row)
        if source is None or source == self._active_selection_source_v31:
            return
        self._active_selection_source_v31 = source
        super()._visual_asset_selected(event)

        # The old 650 ms delay was intended to let a competing generic wireframe load
        # finish. V28 removed that competing load. Start the authoritative contents /
        # animation transaction promptly so a single click feels immediate.
        token = getattr(self, "_contents_after", None)
        if token is not None:
            try:
                self.after_cancel(token)
            except tk.TclError:
                pass
        self._contents_after = self.after(80, self._run_scheduled_contents_load)

    def _refresh_visual_assets(self) -> None:
        self._active_selection_source_v31 = None
        super()._refresh_visual_assets()

    # ------------------------------------------------------------------
    # Explicit left-drag free-look authority. Returning "break" prevents a stale
    # inherited left-pan/rotate binding from receiving the same event afterward.
    # Camera position remains unchanged; only the current view basis changes.
    # ------------------------------------------------------------------
    def _install_left_look_bindings_v31(self) -> None:
        canvas = getattr(self, "visual_canvas", None)
        if canvas is None or not self._widget_alive_v31(canvas):
            return
        for sequence in ("<Button-1>", "<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            try:
                canvas.unbind(sequence)
            except tk.TclError:
                pass
        canvas.bind("<ButtonPress-1>", self._left_look_start_v31)
        canvas.bind("<B1-Motion>", self._left_look_motion_v31)
        canvas.bind("<ButtonRelease-1>", self._left_look_release_v31)

    def _left_look_start_v31(self, event: tk.Event) -> str:
        super()._left_look_start_v30(event)
        return "break"

    def _left_look_motion_v31(self, event: tk.Event) -> str:
        super()._left_look_motion_v30(event)
        return "break"

    def _left_look_release_v31(self, event: tk.Event) -> str:
        super()._left_look_release_v30(event)
        return "break"


def main() -> int:
    app = PublicFragmenterAppV31()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

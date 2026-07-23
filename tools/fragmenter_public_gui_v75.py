#!/usr/bin/env python3
"""V75: embedded egg previews and live authoring-asset selector refresh."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable

from celdra_evolution_pixel_v4 import CELDRA_BLUE_PALETTE, EVOLUTION_PHASES
from fragmenter_public_gui_v74 import PublicFragmenterAppV74


class PublicFragmenterAppV75(PublicFragmenterAppV74):
    """Complete the authoring workspace without returning to RUN ALL for previews."""

    GENERATED_PREVIEW_PHASES = (
        "egg_wait",
        "crack_one",
        "crack_two",
        "eyes",
        "hatch_open",
        "baby_rise",
        "idle",
        "base_search",
        "squished",
        "base_claim",
        "base_failed",
        "young_dragon",
    )

    def __init__(self) -> None:
        self._celdra_author_asset_combo_v74: ttk.Combobox | None = None
        self._celdra_author_event_asset_combo_v75: ttk.Combobox | None = None
        self._celdra_author_pose_combo_v75: ttk.Combobox | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Authoring Workspace")

    @staticmethod
    def _walk_widgets_v75(widget: tk.Misc) -> Iterable[tk.Misc]:
        for child in widget.winfo_children():
            yield child
            yield from PublicFragmenterAppV75._walk_widgets_v75(child)

    def _capture_combo_for_variable_v75(
        self,
        root: tk.Misc,
        variable: tk.Variable | None,
    ) -> ttk.Combobox | None:
        if variable is None:
            return None
        expected = str(variable)
        for widget in self._walk_widgets_v75(root):
            if not isinstance(widget, ttk.Combobox):
                continue
            try:
                if str(widget.cget("textvariable")) == expected:
                    return widget
            except tk.TclError:
                continue
        return None

    def _build_author_preview_tab_v74(self, parent: ttk.Frame) -> None:
        super()._build_author_preview_tab_v74(parent)
        self._celdra_author_asset_combo_v74 = self._capture_combo_for_variable_v75(
            parent,
            getattr(self, "_celdra_author_asset_var_v74", None),
        )
        self._celdra_author_pose_combo_v75 = self._capture_combo_for_variable_v75(
            parent,
            self._celdra_studio_pose_v72,
        )
        self._refresh_author_assets_v74()

    def _build_author_timeline_tab_v74(self, parent: ttk.Frame) -> None:
        super()._build_author_timeline_tab_v74(parent)
        self._celdra_author_event_asset_combo_v75 = self._capture_combo_for_variable_v75(
            parent,
            self._celdra_event_asset_v74,
        )
        self._refresh_author_assets_v74()

    def _available_author_assets_v74(self) -> list[str]:
        inherited = super()._available_author_assets_v74()
        values = list(self.GENERATED_PREVIEW_PHASES)
        values.append("hatch_gif")
        values.extend(inherited)
        return sorted(dict.fromkeys(values))

    def _refresh_author_assets_v74(self) -> None:
        super()._refresh_author_assets_v74()
        values = self._available_author_assets_v74()
        for combo in (
            self._celdra_author_asset_combo_v74,
            self._celdra_author_event_asset_combo_v75,
        ):
            if combo is not None:
                try:
                    combo.configure(values=values)
                except tk.TclError:
                    pass
        poses = self._available_pose_names_v74()
        if self._celdra_author_pose_combo_v75 is not None:
            try:
                self._celdra_author_pose_combo_v75.configure(values=poses)
            except tk.TclError:
                pass

    def _preview_photo_for_asset_v74(self, asset: str, scale: int) -> tk.PhotoImage | None:
        if str(asset or "").casefold() == "hatch_gif":
            return super()._preview_photo_for_asset_v74("asset:avatar/01.gif", scale)
        return super()._preview_photo_for_asset_v74(asset, scale)

    def _render_author_preview_v74(self, values: dict[str, Any] | None = None) -> None:
        data = dict(values or self._preview_values_v74())
        asset = str(data.get("asset") or "").casefold()
        if asset not in self.GENERATED_PREVIEW_PHASES:
            super()._render_author_preview_v74(data)
            return

        text = str(data.get("text") or "")
        base = dict(data)
        base["text"] = ""
        super()._render_author_preview_v74(base)
        self._draw_generated_phase_v75(asset, data)
        canvas = self._celdra_author_preview_canvas_v74
        if canvas is not None and text:
            width = max(720, canvas.winfo_width())
            height = max(460, canvas.winfo_height())
            stage_width = max(
                160,
                round(width * max(10, min(99, int(data.get("window_percent") or 56))) / 100.0),
            )
            self._draw_preview_bubble_v74(canvas, stage_width, height, data, text)

    def _draw_generated_phase_v75(self, phase: str, data: dict[str, Any]) -> None:
        canvas = self._celdra_author_preview_canvas_v74
        if canvas is None:
            return
        frames = EVOLUTION_PHASES.get(phase)
        if not frames:
            return
        frame = frames[0]
        rows = frame.rows
        if not rows:
            return
        width = max(720, canvas.winfo_width())
        height = max(460, canvas.winfo_height())
        stage_width = max(
            160,
            round(width * max(10, min(99, int(data.get("window_percent") or 56))) / 100.0),
        )
        columns = max((len(row) for row in rows), default=1)
        percent = max(10, min(500, int(data.get("scale") or 100)))
        pixel = max(1, round(4 * percent / 100.0))
        maximum_pixel = max(
            1,
            min(
                max(1, (stage_width - 24) // max(1, columns)),
                max(1, (height - 54) // max(1, len(rows))),
            ),
        )
        pixel = min(pixel, maximum_pixel)
        art_width = columns * pixel
        art_height = len(rows) * pixel
        x0 = stage_width // 2 - art_width // 2 + int(data.get("x") or 0)
        y0 = height - 22 - art_height + int(data.get("y") or 0)
        tag = "v75_generated_phase"
        canvas.delete(tag)
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = CELDRA_BLUE_PALETTE.get(symbol, "")
                if not color:
                    continue
                canvas.create_rectangle(
                    x0 + column_index * pixel,
                    y0 + row_index * pixel,
                    x0 + (column_index + 1) * pixel,
                    y0 + (row_index + 1) * pixel,
                    fill=color,
                    outline=color,
                    tags=tag,
                )
        canvas.create_text(
            12,
            height - 12,
            text=f"{phase} • generated frame • {percent}%",
            anchor="sw",
            fill="#557c9e",
            font=("Consolas", 8),
            tags=tag,
        )


def main() -> int:
    app = PublicFragmenterAppV75()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

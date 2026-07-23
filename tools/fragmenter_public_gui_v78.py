#!/usr/bin/env python3
"""V78: wrapped authoring actions and descendant-aware scrolling."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from fragmenter_public_gui_v76 import PublicFragmenterAppV76
from fragmenter_public_gui_v77 import PublicFragmenterAppV77


class PublicFragmenterAppV78(PublicFragmenterAppV77):
    """Use the complete test-tab area without allowing controls to become unreachable."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Authoring Workspace")

    @staticmethod
    def _wrapped_actions_v78(
        parent: ttk.Frame,
        actions: tuple[tuple[str, Callable[[], None]], ...],
        *,
        columns: int = 3,
    ) -> None:
        columns = max(1, int(columns))
        for column in range(columns):
            parent.columnconfigure(column, weight=1, uniform="celdra-v78-actions")
        for index, (label, command) in enumerate(actions):
            ttk.Button(parent, text=label, command=command).grid(
                row=index // columns,
                column=index % columns,
                sticky="ew",
                padx=2,
                pady=2,
            )

    def _scroll_host_v77(self, parent: ttk.Frame, *, row: int) -> ttk.Frame:
        parent.rowconfigure(row, weight=1)
        parent.columnconfigure(0, weight=1)
        canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0, background="#10151d")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=row, column=0, sticky="nsew")
        scrollbar.grid(row=row, column=1, sticky="ns")
        body = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body._celdra_scroll_canvas_v78 = canvas  # type: ignore[attr-defined]
        body._celdra_scroll_window_v78 = window_id  # type: ignore[attr-defined]

        def update_region(_event: tk.Event | None = None) -> None:
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except tk.TclError:
                pass

        def fit_window(event: tk.Event) -> None:
            try:
                canvas.itemconfigure(
                    window_id,
                    width=max(1, int(event.width)),
                    height=max(int(event.height), body.winfo_reqheight()),
                )
                update_region()
            except tk.TclError:
                pass

        body.bind("<Configure>", update_region)
        canvas.bind("<Configure>", fit_window)
        return body

    @staticmethod
    def _walk_widgets_v78(widget: tk.Misc):
        yield widget
        for child in widget.winfo_children():
            yield from PublicFragmenterAppV78._walk_widgets_v78(child)

    def _activate_scroll_wheel_v78(self, body: ttk.Frame) -> None:
        canvas = getattr(body, "_celdra_scroll_canvas_v78", None)
        if canvas is None:
            return
        bindtag = f"CeldraV78Scroll{id(canvas)}"

        def wheel(event: tk.Event) -> str:
            try:
                delta = -1 if int(event.delta) > 0 else 1
                canvas.yview_scroll(delta * 3, "units")
            except (AttributeError, tk.TclError, ValueError):
                pass
            return "break"

        canvas.bind_class(bindtag, "<MouseWheel>", wheel)
        for widget in self._walk_widgets_v78(body):
            try:
                tags = widget.bindtags()
                if bindtag not in tags:
                    widget.bindtags((bindtag, *tags))
            except tk.TclError:
                pass

    def _build_author_preview_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self._wrapped_actions_v78(
            actions,
            (
                ("Render here", self._preview_pose_embedded_v74),
                ("Preview current in main viewport", self._preview_current_in_main_v77),
                ("Play editable timeline here", self._play_author_timeline_v74),
                ("Play canonical timeline in main viewport (20×)", self._preview_canonical_main_v77),
                ("Preview egg corruption / climax in main", self._preview_egg_main_v77),
            ),
            columns=3,
        )
        body = self._scroll_host_v77(parent, row=1)
        PublicFragmenterAppV76._build_author_preview_tab_v74(self, body)
        if self._celdra_author_preview_canvas_v74 is not None:
            try:
                self._celdra_author_preview_canvas_v74.configure(height=430)
            except tk.TclError:
                pass
        preset_box = ttk.LabelFrame(body, text="Reusable pose + dialogue presets", padding=6)
        preset_box.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._build_pose_presets_v77(preset_box)
        button_rows = preset_box.grid_slaves(row=2, column=0)
        if button_rows:
            button_frame = button_rows[0]
            buttons = [child for child in button_frame.winfo_children() if isinstance(child, ttk.Button)]
            for child in buttons:
                child.pack_forget()
            for column in range(4):
                button_frame.columnconfigure(column, weight=1)
            for index, button in enumerate(buttons):
                button.grid(row=index // 4, column=index % 4, sticky="ew", padx=2, pady=2)
        self._activate_scroll_wheel_v78(body)

    def _build_author_timeline_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self._wrapped_actions_v78(
            actions,
            (
                ("Play editable timeline here", self._play_author_timeline_v74),
                ("Preview selected in main viewport", self._preview_selected_event_main_v77),
                ("Play canonical timeline in main viewport (20×)", self._preview_canonical_main_v77),
                ("Preview egg corruption / climax in main", self._preview_egg_main_v77),
            ),
            columns=2,
        )
        body = ttk.Frame(parent)
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        PublicFragmenterAppV76._build_author_timeline_tab_v74(self, body)

    def _build_author_crop_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self._wrapped_actions_v78(
            actions,
            (
                ("Save crop + PNG", self._save_crop_and_png_v74),
                ("Save manifest only", self._save_emote_definition_v52),
                ("Preview crop here", self._show_emote_in_celdra_v52),
                ("Preview crop in main viewport", self._preview_crop_main_v77),
                ("Export all crop PNGs", self._export_all_emotes_v52),
            ),
            columns=3,
        )
        body = self._scroll_host_v77(parent, row=1)
        PublicFragmenterAppV76._build_author_crop_tab_v74(self, body)
        self._activate_scroll_wheel_v78(body)


def main() -> int:
    app = PublicFragmenterAppV78()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

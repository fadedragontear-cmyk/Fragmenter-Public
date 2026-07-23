#!/usr/bin/env python3
"""V53: compatibility fixes for the Celdra emote separator preview."""
from __future__ import annotations

import tkinter as tk

from fragmenter_public_gui_v52 import PublicFragmenterAppV52


class PublicFragmenterAppV53(PublicFragmenterAppV52):
    """Keep V52 behavior while handling empty selections and external crop previews."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Emote Separator / Classifier")

    def _new_emote_definition_v52(self, *, keep_source: bool = True) -> None:
        source = self.emote_vars_v52["source"].get() if keep_source else ""
        self.emote_vars_v52["id"].set("")
        self.emote_vars_v52["source"].set(source)
        self.emote_vars_v52["state"].set("unclassified")
        self.emote_vars_v52["pose"].set("")
        self.emote_vars_v52["tags"].set("")
        if self.emote_source_image_v52 is not None:
            self.emote_vars_v52["x"].set(0)
            self.emote_vars_v52["y"].set(0)
            self.emote_vars_v52["width"].set(
                min(128, self.emote_source_image_v52.width())
            )
            self.emote_vars_v52["height"].set(
                min(128, self.emote_source_image_v52.height())
            )
            self._draw_crop_rectangle_v52()
        tree = getattr(self, "emote_definition_tree_v52", None)
        if tree is not None:
            selected = tree.selection()
            if selected:
                tree.selection_remove(*selected)

    def _redraw_celdra_avatar_v50(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        external = self.celdra_current_external_v50
        if canvas is not None and external is not None:
            canvas.delete("all")
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
            canvas.create_image(
                width // 2,
                height // 2,
                image=external,
                anchor="center",
            )
            return
        super()._redraw_celdra_avatar_v50()


def main() -> int:
    app = PublicFragmenterAppV53()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

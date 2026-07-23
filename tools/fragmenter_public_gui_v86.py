#!/usr/bin/env python3
"""V86: make mini-player geometry faithful at the 4% and 99% extremes."""
from __future__ import annotations

from typing import Any

from fragmenter_public_gui_v85 import PublicFragmenterAppV85


class PublicFragmenterAppV86(PublicFragmenterAppV85):
    """Preserve only a tiny inspection gutter instead of distorting authored widths."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra 2D Timeline Sequencer")

    def _viewport_rect_v85(
        self,
        canvas_width: int,
        canvas_height: int,
        state: dict[str, Any],
    ) -> tuple[int, int, int, int]:
        width_percent = max(4, min(99, int(state.get("window_percent") or 56)))
        height_percent = max(20, min(100, int(state.get("window_height_percent") or 100)))
        top_percent = max(0, min(80, int(state.get("window_y_percent") or 0)))
        stage_width = max(
            22,
            min(canvas_width - 36, round(canvas_width * width_percent / 100.0)),
        )
        stage_height = max(
            48,
            min(canvas_height, round(canvas_height * height_percent / 100.0)),
        )
        stage_y = round(canvas_height * top_percent / 100.0)
        stage_y = max(0, min(canvas_height - stage_height, stage_y))
        return 0, stage_y, stage_width, stage_y + stage_height

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V86"
            metadata["faithful_viewport_extremes"] = True
        return payload


def main() -> int:
    app = PublicFragmenterAppV86()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

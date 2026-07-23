#!/usr/bin/env python3
"""V83: preserve dialogue attached directly to authored pose events."""
from __future__ import annotations

from typing import Any

from fragmenter_public_gui_v82 import PublicFragmenterAppV82


class PublicFragmenterAppV83(PublicFragmenterAppV82):
    """Allow a pose row to carry an optional speech bubble for quick authoring."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Framing + Timeline Workspace")

    def _apply_author_event_v74(self, row: dict[str, Any]) -> None:
        super()._apply_author_event_v74(row)
        action = str(row.get("action") or "").casefold()
        text = str(row.get("text") or "").strip()
        if action not in {"pose", "avatar", "asset"} or not text:
            return
        values = dict(row)
        values["text"] = text
        self._render_author_preview_v74(values)

    def _preview_selected_event_main_v77(self) -> None:
        row = self._celdra_author_event_rows_v74.get(
            self._selected_author_event_id_v74()
        )
        if row is not None:
            action = str(row.get("action") or "").casefold()
            if action in {"pose", "avatar", "asset"} and str(
                row.get("text") or ""
            ).strip():
                self._preview_values_in_main_v77(dict(row))
                return
        super()._preview_selected_event_main_v77()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V83"
            metadata["pose_text_shorthand"] = True
        return payload


def main() -> int:
    app = PublicFragmenterAppV83()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

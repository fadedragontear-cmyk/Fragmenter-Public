#!/usr/bin/env python3
"""V79: preserve active poses for dialogue previews and identify exported workspace data."""
from __future__ import annotations

from typing import Any

from fragmenter_public_gui_v78 import PublicFragmenterAppV78


class PublicFragmenterAppV79(PublicFragmenterAppV78):
    """Apply final authoring-preview compatibility guards."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Authoring Workspace")

    def _preview_values_in_main_v77(self, values: dict[str, Any]) -> None:
        data = dict(values)
        if not str(data.get("asset") or "").strip():
            data["asset"] = self._celdra_author_preview_asset_v74 or "shy"
        super()._preview_values_in_main_v77(data)

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V79"
            metadata["preview_surfaces"] = ["embedded", "main_run_all"]
        return payload

    def _apply_author_project_payload_v74(self, payload: dict[str, Any]) -> None:
        super()._apply_author_project_payload_v74(payload)
        highest = self._celdra_preset_serial_v77
        for row in self._celdra_pose_presets_v77:
            suffix = str(row.get("id") or "").rsplit("-", 1)[-1]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
        self._celdra_preset_serial_v77 = highest


def main() -> int:
    app = PublicFragmenterAppV79()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

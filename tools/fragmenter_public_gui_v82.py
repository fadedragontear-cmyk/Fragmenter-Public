#!/usr/bin/env python3
"""V82: recover the user's V79 authoring delta without replacing canonical rows."""
from __future__ import annotations

import json
from typing import Any

from celdra_authoring_project_v1 import normalize_events, read_project
from fragmenter_public_gui_v81 import PublicFragmenterAppV81


class PublicFragmenterAppV82(PublicFragmenterAppV81):
    """Prefer a local full project, otherwise merge the preserved user delta."""

    IMPORT_FALLBACK_RELATIVE = "authoring/imports/fade-v79-2026-07-17-delta.json"

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Framing + Timeline Workspace")

    def _autoload_authoring_project_v81(self) -> None:
        if self._celdra_loaded_project_v81:
            return
        self._celdra_loaded_project_v81 = True
        primary = self.celdra_asset_root_v50 / self.AUTHOR_PROJECT_RELATIVE
        fallback = self.celdra_asset_root_v50 / self.IMPORT_FALLBACK_RELATIVE

        if primary.is_file():
            try:
                payload = read_project(primary)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._set_recovery_status_v82(
                    f"Could not auto-load local saved project {primary.name}: {exc}"
                )
                return
            self._apply_author_project_payload_v74(payload)
            self._celdra_author_project_path_v74 = primary
            self._set_recovery_status_v82(f"Loaded local saved project: {primary}")
            return

        if not fallback.is_file():
            self._ensure_post_breakpoint_events_v81()
            return

        try:
            delta = json.loads(fallback.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._set_recovery_status_v82(
                f"Could not load preserved V79 authoring delta: {exc}"
            )
            return
        if not isinstance(delta, dict):
            self._set_recovery_status_v82(
                "Preserved V79 authoring delta is not a JSON object."
            )
            return

        payload = self._author_project_payload_v74()
        combined: dict[str, dict[str, Any]] = {
            str(row.get("id") or ""): dict(row)
            for row in payload.get("events") or []
            if isinstance(row, dict) and str(row.get("id") or "")
        }
        for row in delta.get("custom_events") or []:
            if not isinstance(row, dict):
                continue
            event_id = str(row.get("id") or "")
            if event_id:
                combined[event_id] = dict(row)
        payload["events"] = normalize_events(combined.values())

        for key in (
            "preview",
            "shy_entrance",
            "pose_dialogue_presets",
            "framing_lab",
        ):
            value = delta.get(key)
            if isinstance(value, dict):
                payload[key] = dict(value)
            elif isinstance(value, list):
                payload[key] = [dict(row) for row in value if isinstance(row, dict)]

        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["recovered_from"] = str(fallback)
            metadata["recovery_mode"] = "merge_delta"
        self._apply_author_project_payload_v74(payload)
        self._celdra_author_project_path_v74 = primary
        self._set_recovery_status_v82(
            "Loaded preserved V79 changes into the editable timeline. "
            "Use Save project to write the merged V82 project locally."
        )

    def _set_recovery_status_v82(self, text: str) -> None:
        if self._celdra_author_project_status_v74 is not None:
            self._celdra_author_project_status_v74.set(text)


def main() -> int:
    app = PublicFragmenterAppV82()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

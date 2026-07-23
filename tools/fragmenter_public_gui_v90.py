#!/usr/bin/env python3
"""V90: expose Operation Dragonegg motion controllers as first-class authoring actions."""
from __future__ import annotations

from typing import Any

from fragmenter_public_gui_v89 import PublicFragmenterAppV89


class PublicFragmenterAppV90(PublicFragmenterAppV89):
    """Make pulse, shake, and whiteout rows directly selectable and auditable."""

    CONTROLLER_ACTIONS = {"viewport_pulse", "viewport_shake", "console_whiteout"}
    MINI_LAYOUT_ACTIONS = set(PublicFragmenterAppV89.MINI_LAYOUT_ACTIONS) | {
        "viewport_pulse",
        "viewport_shake",
    }
    CONTROLLER_ACTION_BY_ID = {
        "v89-motion-crack-one-pulse": "viewport_pulse",
        "v89-motion-crack-two-pulse": "viewport_pulse",
        "v89-motion-instability-shake": "viewport_shake",
        "v89-motion-console-whiteout": "console_whiteout",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Operation Dragonegg Final Preview V90")
        self._upgrade_controller_actions_v90()
        self.after_idle(self._refresh_author_event_tree_v74)

    def _upgrade_controller_actions_v90(self) -> None:
        upgraded: list[dict[str, Any]] = []
        for row in self._celdra_author_events_v74:
            current = dict(row)
            identifier = str(current.get("id") or "")
            action = self.CONTROLLER_ACTION_BY_ID.get(identifier)
            if action:
                current["action"] = action
                current["layout_override"] = action != "console_whiteout"
            upgraded.append(current)
        self._celdra_author_events_v74 = self._normalize_controller_rows_v90(upgraded)

    @staticmethod
    def _normalize_controller_rows_v90(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from celdra_authoring_project_v1 import normalize_events

        return normalize_events(rows)

    def _apply_dragongirl_authoring_profile_v87(self) -> None:
        super()._apply_dragongirl_authoring_profile_v87()
        self._upgrade_controller_actions_v90()

    def _apply_author_project_payload_v74(self, payload: dict[str, Any]) -> None:
        super()._apply_author_project_payload_v74(payload)
        self._upgrade_controller_actions_v90()
        self._refresh_author_event_tree_v74()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        self._upgrade_controller_actions_v90()
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V90"
            metadata["controller_actions"] = [
                "viewport_pulse",
                "viewport_shake",
                "console_whiteout",
            ]
        return payload

    def _controller_pulse_values_v90(self, row: dict[str, Any]) -> tuple[float, ...]:
        identifier = str(row.get("id") or "")
        if "crack-two" in identifier:
            return tuple(0.535 if index % 2 == 0 else 0.485 for index in range(16)) + (0.49,)
        return tuple(0.50 if index % 2 == 0 else 0.45 for index in range(22)) + (0.40,)

    def _apply_author_event_v74(self, row: dict[str, Any]) -> None:
        action = str(row.get("action") or "").casefold()
        if action in self.CONTROLLER_ACTIONS:
            speaker = str(row.get("speaker") or "CORE")
            text = str(row.get("text") or action.replace("_", " ").upper())
            self._celdra_author_console_lines_v74.append(f"[{speaker}] {text}")
            values = {
                "asset": str(row.get("asset") or self._celdra_author_preview_asset_v74 or "crack_two"),
                "x": int(row.get("x") or 0),
                "y": int(row.get("y") or 0),
                "scale": int(row.get("scale") or 100),
                "window_percent": int(row.get("window_percent") or 56),
                "bubble_style": row.get("bubble_style") or "Rounded blue",
                "bubble_x": int(row.get("bubble_x") or 4),
                "bubble_y": int(row.get("bubble_y") or 3),
                "bubble_width": int(row.get("bubble_width") or 52),
                "text": "",
            }
            self._render_author_preview_v74(values)
            return
        super()._apply_author_event_v74(row)

    def _preview_selected_event_main_v77(self) -> None:
        row = self._celdra_author_event_rows_v74.get(self._selected_author_event_id_v74())
        action = str(row.get("action") or "").casefold() if row is not None else ""
        if row is None or action not in self.CONTROLLER_ACTIONS:
            super()._preview_selected_event_main_v77()
            return

        self._prepare_main_preview_v77()
        self._show_avatar_v51()
        phase = "crack_two" if action != "viewport_pulse" or "two" in str(row.get("id") or "") else "crack_one"
        self._set_avatar_phase_v51(phase)

        if action == "viewport_pulse":
            interval = 220 if "two" in str(row.get("id") or "") else 250
            self._start_crack_pulse_v89(
                self._controller_pulse_values_v90(row),
                interval_ms=interval,
            )
            return

        if action == "viewport_shake":
            self._celdra_instability_red_v70 = True
            self._set_egg_glitch_v61(3)
            self._start_instability_shake_v89()
            return

        self._stop_instability_shake_v89(restore_stage=False)
        self._start_console_whiteout_v89()
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(4_400),
            lambda: self._append_whiteout_celdra_line_v89("INITIALIZED"),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(7_200),
            lambda: self._append_whiteout_celdra_line_v89("ONLINE"),
        )
        self._remember_after_v49(
            self._scaled_runtime_ms_v88(8_100),
            self._start_console_restore_v89,
        )


def main() -> int:
    app = PublicFragmenterAppV90()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

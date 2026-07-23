#!/usr/bin/env python3
"""V76: harden authoring-sequence branch playback and final workspace activation."""
from __future__ import annotations

import tkinter as tk

from celdra_authoring_project_v1 import normalize_events
from fragmenter_public_gui_v75 import PublicFragmenterAppV75


class PublicFragmenterAppV76(PublicFragmenterAppV75):
    """Keep empty branch routes empty and sequence playback deterministic."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Authoring Workspace")

    def _play_author_timeline_v74(self) -> None:
        self._stop_author_timeline_v74()
        rows = normalize_events(
            row for row in self._celdra_author_events_v74 if row.get("enabled", True)
        )
        if not rows:
            return
        try:
            speed = max(0.1, float(self._celdra_event_speed_v74.get()))
        except (AttributeError, tk.TclError, TypeError, ValueError):
            speed = 1.0
        self._celdra_author_active_branch_v74 = ""
        self._celdra_author_console_lines_v74.clear()

        def advance(index: int, previous_ms: int) -> None:
            while index < len(rows):
                candidate = rows[index]
                sequence = str(candidate.get("sequence") or "main")
                if sequence == "main" or sequence == self._celdra_author_active_branch_v74:
                    break
                index += 1
            if index >= len(rows):
                self._celdra_author_after_v74 = None
                return

            row = rows[index]
            at_ms = int(row.get("at_ms") or 0)
            delay = max(0, round((at_ms - previous_ms) / speed))

            def execute() -> None:
                self._celdra_author_after_v74 = None
                if str(row.get("action") or "") == "condition":
                    result = self._evaluate_author_condition_v74(
                        str(row.get("condition") or "")
                    )
                    selected = (
                        row.get("true_sequence")
                        if result
                        else row.get("false_sequence")
                    )
                    self._celdra_author_active_branch_v74 = str(selected or "")
                self._apply_author_event_v74(row)
                advance(index + 1, at_ms)

            self._celdra_author_after_v74 = self.after(delay, execute)

        advance(0, 0)


def main() -> int:
    app = PublicFragmenterAppV76()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

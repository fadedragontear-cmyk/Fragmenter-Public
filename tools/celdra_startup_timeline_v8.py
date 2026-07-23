#!/usr/bin/env python3
"""V8 startup script: remove the discarded ALL YOUR BASE gag."""
from __future__ import annotations

from celdra_startup_timeline_v2 import TimelineEvent, ordered
from celdra_startup_timeline_v7 import FIRST_RUN_AFTER_CCSF as V7_EVENTS

REMOVED_BASE_GAG = {"ALL YOUR BASE", "ARE BELONG TO US"}


def _convert() -> tuple[TimelineEvent, ...]:
    events: list[TimelineEvent] = []
    for event in V7_EVENTS:
        if event.action == "console" and event.text.strip().upper() in REMOVED_BASE_GAG:
            continue
        events.append(event)
    return ordered(events)


FIRST_RUN_AFTER_CCSF = _convert()
FIRST_BREAKPOINT_MS = max(event.at_ms for event in FIRST_RUN_AFTER_CCSF)


if __name__ == "__main__":
    raise SystemExit("Celdra startup timeline data is consumed by Fragmenter's GUI.")

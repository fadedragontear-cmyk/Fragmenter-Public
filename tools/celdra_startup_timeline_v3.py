#!/usr/bin/env python3
"""V3 first-run timeline with discrete 0-to-100 presentation jobs.

Hatching owns one uninterrupted progress cycle.  Each later base/investigation
operation receives its own independent loading cycle instead of sharing a
cumulative percentage.
"""
from __future__ import annotations

from celdra_startup_timeline_v2 import (
    AVATAR_HIDE_MS,
    BOOT_ONLINE_MS,
    CCSF_HATCH_DELAY_MS,
    DEFAULT_STATUS_MS,
    DEPLOY_MIN_MS,
    DEPLOY_STATUS,
    DIALOGUE_REVEAL_MS,
    DRAGONEGG_ASCII,
    FIRST_RUN_AFTER_CCSF as V2_EVENTS,
    TimelineEvent,
    ordered,
)


BASE_STATUS_OFFSETS = {180_000, 200_000, 220_000, 240_000}


def _convert() -> tuple[TimelineEvent, ...]:
    events: list[TimelineEvent] = []
    for event in V2_EVENTS:
        # One complete hatch bar spans egg reveal through the point where the
        # viewport retracts after CELDRA ONLINE.
        if event.at_ms == 0 and event.action == "status":
            events.append(
                TimelineEvent(
                    0,
                    "status",
                    "[DRAGONEGG] HATCHING...",
                    progress_start=0,
                    progress_end=100,
                    duration_ms=180_000,
                )
            )
            continue

        # Brain initialization remains visible in the system console without
        # interrupting or resetting the active hatching bar.
        if event.at_ms == 40_000 and event.action == "status":
            events.append(
                TimelineEvent(
                    40_000,
                    "console",
                    "BRAIN INITIALIZATION PROCESS STARTING.",
                    speaker="CORE",
                )
            )
            continue

        # Every base operation is a fresh loading job.
        if event.action == "status" and event.at_ms in BASE_STATUS_OFFSETS:
            events.append(
                TimelineEvent(
                    event.at_ms,
                    "status",
                    event.text,
                    progress_start=0,
                    progress_end=100,
                    duration_ms=DEFAULT_STATUS_MS,
                )
            )
            continue

        # Cumulative bridge progress from V2 is no longer used.
        if event.action == "progress":
            continue

        # Later standalone presentation jobs also reset independently.
        if event.action == "status" and event.at_ms in {400_000, 460_000}:
            events.append(
                TimelineEvent(
                    event.at_ms,
                    "status",
                    event.text,
                    progress_start=0,
                    progress_end=100,
                    duration_ms=event.duration_ms or DEFAULT_STATUS_MS,
                )
            )
            continue

        events.append(event)

    # The hatchling briefly returns during the final base scan to claim the
    # user's base with a deliberately over-produced text animation.
    events.extend(
        (
            TimelineEvent(247_000, "base_joke", "ALL YOUR BASE ARE BELONG TO US"),
            TimelineEvent(259_500, "base_joke_end"),
        )
    )
    return ordered(events)


FIRST_RUN_AFTER_CCSF = _convert()
FIRST_BREAKPOINT_MS = max(event.at_ms for event in FIRST_RUN_AFTER_CCSF)


if __name__ == "__main__":
    raise SystemExit("Celdra startup timeline data is consumed by Fragmenter's GUI.")

#!/usr/bin/env python3
"""Rebase implausibly absolute SCEIMidi event ticks before bounded preview rendering."""
from __future__ import annotations

from typing import Any

import snddata_music_system_v5 as v5

_INSTALLED = False
_ORIGINAL = v5._bounded_preview_events


def bounded_preview_events_rebased(
    midi_reports: list[dict[str, Any]],
    *,
    max_seconds: float = v5.PREVIEW_MAX_SECONDS,
    max_note_events: int = v5.PREVIEW_MAX_NOTE_EVENTS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Preserve the normal window, but retry relative to the first Note On when it hides all notes."""
    events, bounds = _ORIGINAL(
        midi_reports,
        max_seconds=max_seconds,
        max_note_events=max_note_events,
    )
    if int(bounds.get("notes") or 0) > 0:
        return events, bounds

    positive = [
        event
        for report in midi_reports
        for event in report.get("events") or []
        if event.get("event_type") == "note_on"
        and int((event.get("values") or {}).get("velocity") or 0) > 0
    ]
    if not positive:
        return events, bounds

    origin = min(int(event.get("absolute_ticks") or 0) for event in positive)
    rebased_reports: list[dict[str, Any]] = []
    for report in midi_reports:
        cloned_events: list[dict[str, Any]] = []
        for event in report.get("events") or []:
            cloned = dict(event)
            cloned["absolute_ticks"] = max(
                0, int(event.get("absolute_ticks") or 0) - origin
            )
            cloned_events.append(cloned)
        rebased_reports.append({**report, "events": cloned_events})

    retry_events, retry_bounds = _ORIGINAL(
        rebased_reports,
        max_seconds=max_seconds,
        max_note_events=max_note_events,
    )
    retry_bounds.update(
        {
            "origin_rebased": True,
            "source_first_positive_note_tick": origin,
            "source_positive_note_events": len(positive),
            "warning": (
                "Preview ticks were rebased to the first positive Note On because the "
                "absolute-tick window contained no notes. This does not validate parser timing."
            ),
        }
    )
    return retry_events, retry_bounds


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    v5._bounded_preview_events = bounded_preview_events_rebased
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Installed by the Fragmenter public launcher.")

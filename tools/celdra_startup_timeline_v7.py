#!/usr/bin/env python3
"""V7 first-run script refinements for typewriter/cursor presentation.

The production input-channel hack still fails canonically, but Celdra explicitly
asks the user's name first and waits long enough for the conversational cursor to
make the unanswered question feel intentional.
"""
from __future__ import annotations

from dataclasses import replace

from celdra_startup_timeline_v2 import TimelineEvent, ordered
from celdra_startup_timeline_v6 import FIRST_RUN_AFTER_CCSF as V6_EVENTS


NAME_QUESTION = "My name is Celdra. What's your name?"
MESS_STATEMENT = "Let's see what's going on with this mess."


def _convert() -> tuple[TimelineEvent, ...]:
    events: list[TimelineEvent] = []
    for event in V6_EVENTS:
        if event.action == "chat" and event.text in {
            "My name is Celdra, what's yours?",
            "My name is Celdra. What's yours?",
        }:
            events.append(replace(event, text=NAME_QUESTION))
            continue
        if event.action == "chat" and event.text in {
            "Let's see what's going on with this mess?",
            "Let's see whats going on with this mess?",
        }:
            events.append(replace(event, text=MESS_STATEMENT))
            continue
        events.append(event)
    return ordered(events)


FIRST_RUN_AFTER_CCSF = _convert()
FIRST_BREAKPOINT_MS = max(event.at_ms for event in FIRST_RUN_AFTER_CCSF)


if __name__ == "__main__":
    raise SystemExit("Celdra startup timeline data is consumed by Fragmenter's GUI.")

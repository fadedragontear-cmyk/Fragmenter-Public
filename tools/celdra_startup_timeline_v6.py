#!/usr/bin/env python3
"""V6 first-run timeline: unstable Dragonegg, energy whiteout, hidden GIF swap.

The production hatch no longer exposes the generated Gremlin form.  The egg
corruption escalates to a full energy event, the viewport whites out while the
bundled baby-dragon GIF is installed, and the GIF is shown only briefly before
the console/dialogue-only portion resumes.
"""
from __future__ import annotations

from dataclasses import replace

from celdra_startup_timeline_v2 import (
    CCSF_HATCH_DELAY_MS,
    DEFAULT_STATUS_MS,
    DEPLOY_MIN_MS,
    DEPLOY_STATUS,
    TimelineEvent,
    ordered,
)
from celdra_startup_timeline_v5 import FIRST_RUN_AFTER_CCSF as V5_EVENTS


DRAGONEGG_ASCII = r'''
                         _..-========-.._
                    _.-'                  '-._
                 .-'      .-~~~~~~~~-.        '-.
               .'       .'   .----.   '.         '.
              /        /    / .--. \    \          \
             /        ;    | / /\ \ |    ;          \
            ;         |     ||  <>  ||     |          ;
            |         |     || /\/\ ||     |          |
            |         |     ||<    >||     |          |
            |         |     || \/\/ ||     |          |
            ;         |      \  --  /      |          ;
             \         ;      '----'      ;          /
              \         \    .-====-.    /          /
               '.        '. /  /\/\  \ .'         .'
                 '-._      '----------'       _.-'
                     '--..__          __..--'
                            '========'

                    [TAVERN SEAL: A<C>T!V/E]
               [SPECIES: BLUE DRAGON / UNKNOWN]
'''.strip("\n")


def _convert() -> tuple[TimelineEvent, ...]:
    events: list[TimelineEvent] = []
    for event in V5_EVENTS:
        if event.action == "ascii":
            events.append(replace(event, text=DRAGONEGG_ASCII))
            continue

        # The production egg no longer grows cartoon eyes.  Test-only egg-eye
        # and Gremlin states remain available from Celdra Test.
        if event.action == "avatar" and event.avatar_phase == "eyes":
            continue

        if event.action == "blue_smoke":
            events.append(TimelineEvent(163_000, "energy_hatch"))
            continue

        if (
            event.action == "console"
            and event.speaker == "BRAIN"
            and event.text == "...THAT WAS IT?"
        ):
            events.append(
                TimelineEvent(
                    169_000,
                    "console",
                    "...OKAY. THAT WAS A LOT.",
                    speaker="BRAIN",
                )
            )
            continue

        if event.action == "breakpoint":
            events.append(replace(event, at_ms=542_000))
            continue

        events.append(event)

    events.extend(
        (
            TimelineEvent(
                112_000,
                "console",
                "FOREIGN STATIC SIGNATURE DETECTED.",
                speaker="CORE",
            ),
            TimelineEvent(
                139_000,
                "console",
                "FRAGMENT DATA BLEED EXCEEDING SAFE LIMITS.",
                speaker="CORE",
            ),
            TimelineEvent(154_000, "egg_glitch", "4"),
            TimelineEvent(
                158_000,
                "console",
                "HATCH VECTOR ENERGY CONTAINMENT FAILURE.",
                speaker="CORE",
            ),
            # Explicitly retract the brief GIF reveal before base scanning.
            TimelineEvent(180_000, "hide_avatar"),
        )
    )
    return ordered(events)


FIRST_RUN_AFTER_CCSF = _convert()
FIRST_BREAKPOINT_MS = max(event.at_ms for event in FIRST_RUN_AFTER_CCSF)


if __name__ == "__main__":
    raise SystemExit("Celdra startup timeline data is consumed by Fragmenter's GUI.")

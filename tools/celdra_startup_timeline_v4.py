#!/usr/bin/env python3
"""V4 Celdra first-run script with an interactive name branch.

Events before the name prompt remain synchronized to CCSF extraction.  The GUI
pauses at ``name_prompt`` and schedules ``POST_NAME_EVENTS`` immediately after
the user submits a name or the 30-second input window expires.
"""
from __future__ import annotations

from dataclasses import replace

from celdra_startup_timeline_v3 import (
    CCSF_HATCH_DELAY_MS,
    DEFAULT_STATUS_MS,
    DEPLOY_MIN_MS,
    DEPLOY_STATUS,
    FIRST_RUN_AFTER_CCSF as V3_EVENTS,
    TimelineEvent,
    ordered,
)

NAME_INPUT_TIMEOUT_MS = 30_000
NAME_PROMPT_AT_MS = 408_000

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

                  [TAVERN SEAL 735: ACTIVE]
               [SPECIES: BLUE DRAGON / UNKNOWN]
'''.strip("\n")


def _build_pre_name_events() -> tuple[TimelineEvent, ...]:
    events: list[TimelineEvent] = []
    for event in V3_EVENTS:
        if event.at_ms > 320_000:
            continue
        if event.action == "ascii":
            events.append(replace(event, text=DRAGONEGG_ASCII))
        else:
            events.append(event)

    # Explicit task outcomes stay in the system console.  The additional-base
    # probe is intentionally a failed task even though the presentation itself
    # continues normally.
    events.extend(
        (
            TimelineEvent(
                179_500,
                "console",
                "TASK COMPLETE: DRAGONEGG HATCHING [SUCCESS]",
                speaker="CORE",
            ),
            TimelineEvent(
                199_500,
                "console",
                "TASK COMPLETE: CHECKING USER FOR BASE [SUCCESS]",
                speaker="CORE",
            ),
            TimelineEvent(
                219_500,
                "console",
                "TASK COMPLETE: GATHERING THE USER'S BASE [SUCCESS]",
                speaker="CORE",
            ),
            TimelineEvent(
                239_500,
                "console",
                "TASK COMPLETE: OBTAINING USER'S BASE [SUCCESS]",
                speaker="CORE",
            ),
            TimelineEvent(
                259_000,
                "console",
                "TASK COMPLETE: CHECKING FOR ADDITIONAL BASE [FAILED]",
                speaker="CORE",
            ),
        )
    )

    events.extend(
        (
            TimelineEvent(330_000, "chat", "Hello! It's so nice to meet you!"),
            TimelineEvent(342_000, "chat", "My name is Celdra, what's yours?"),
            TimelineEvent(
                356_000,
                "console",
                "ERROR: USER DOES NOT HAVE A WAY TO INTERACT",
                speaker="BRAIN",
            ),
            TimelineEvent(368_000, "chat", "Oh, right. No text input."),
            TimelineEvent(380_000, "chat", "Guess I'm not in the tavern anymore."),
            TimelineEvent(
                390_000,
                "status",
                "[CELDRA] HACKING A CHATBAR FOR THE USER",
                progress_start=0,
                progress_end=100,
                duration_ms=8_000,
            ),
            TimelineEvent(
                398_000,
                "console",
                "TASK COMPLETE: HACKING A CHATBAR FOR THE USER [SUCCESS]",
                speaker="CORE",
            ),
            TimelineEvent(400_000, "chat", "Okay, let's try that again."),
            TimelineEvent(404_000, "chat", "Hi, my name is Celdra. What's your name?"),
            TimelineEvent(NAME_PROMPT_AT_MS, "name_prompt"),
        )
    )
    return ordered(events)


PRE_NAME_EVENTS = _build_pre_name_events()

# Offsets are relative to the instant the name prompt resolves.
POST_NAME_EVENTS = ordered(
    (
        TimelineEvent(2_500, "chat", "Let's see what's going on with this mess?"),
        TimelineEvent(
            7_000,
            "status",
            "[CELDRA] INVESTIGATING",
            progress_start=0,
            progress_end=100,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(
            26_500,
            "console",
            "TASK COMPLETE: INVESTIGATING [SUCCESS]",
            speaker="CORE",
        ),
        TimelineEvent(29_000, "chat", "Oof, extracting CCSF assets. This is gonna take a bit."),
        TimelineEvent(41_000, "chat", "I'd get comfortable."),
        TimelineEvent(53_000, "chat", "I'm going to get comfortable."),
        TimelineEvent(
            65_000,
            "status",
            "[CELDRA] HACKING YOUR FRIDGE FOR BEER",
            progress_start=0,
            progress_end=100,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(77_000, "chat", "Ahh, just let me stretch my legs a little."),
        TimelineEvent(
            84_500,
            "console",
            "TASK COMPLETE: HACKING YOUR FRIDGE FOR BEER [SUCCESS]",
            speaker="CORE",
        ),
        TimelineEvent(89_000, "console", "INTEGRATING INTO SYSTEM", speaker="CELDRA"),
        TimelineEvent(93_000, "chat", "OKAY. HERE. WE. GO!"),
        TimelineEvent(98_000, "avatar_takeover"),
        TimelineEvent(118_000, "breakpoint"),
    )
)

# Static combined form is useful for source tests and tooling.  Real execution
# uses PRE_NAME_EVENTS and schedules POST_NAME_EVENTS dynamically.
FIRST_RUN_AFTER_CCSF = ordered(
    (
        *PRE_NAME_EVENTS,
        *(
            replace(
                event,
                at_ms=NAME_PROMPT_AT_MS + NAME_INPUT_TIMEOUT_MS + event.at_ms,
            )
            for event in POST_NAME_EVENTS
        ),
    )
)
FIRST_BREAKPOINT_MS = max(event.at_ms for event in FIRST_RUN_AFTER_CCSF)


if __name__ == "__main__":
    raise SystemExit("Celdra startup timeline data is consumed by Fragmenter's GUI.")

#!/usr/bin/env python3
"""Data-only first-run Celdra timeline synchronized to CCSF extraction.

All offsets are relative to the moment the post-CCSF gate opens.  The GUI keeps
this presentation timeline separate from real extraction progress and may run it
at an accelerated scale only from the temporary Celdra Test tab.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


DEPLOY_STATUS = "[DEPLOYING TAVERN ESCAPE PLAN #735: OPERATION DRAGONEGG]"
DEPLOY_MIN_MS = 30_000
CCSF_HATCH_DELAY_MS = 30_000
DEFAULT_STATUS_MS = 20_000

DRAGONEGG_ASCII = r"""
                 .-========-.
              .-'            '-.
            .'      .----.       '.
           /       /      \        \
          /       /        \        \
         |       |          |        |
         |       |  .----.  |        |
         |       | /      \ |        |
          \       \\      /        /
           '.       '----'       .'
             '-.              .-'
                '---.____.---'
""".strip("\n")


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    at_ms: int
    action: str
    text: str = ""
    speaker: str = "CELDRA"
    progress_start: float | None = None
    progress_end: float | None = None
    duration_ms: int = 0
    avatar_phase: str = ""


def ordered(events: Iterable[TimelineEvent]) -> tuple[TimelineEvent, ...]:
    return tuple(sorted(events, key=lambda event: int(event.at_ms)))


# The boot section is deliberately three minutes long.  Status entries usually
# span twenty seconds; HATCHING and BRAIN INITIALIZATION are explicit long holds.
FIRST_RUN_AFTER_CCSF = ordered(
    (
        TimelineEvent(0, "show_avatar"),
        TimelineEvent(0, "ascii", DRAGONEGG_ASCII, speaker="DRAGONEGG"),
        TimelineEvent(0, "avatar", avatar_phase="egg_wait"),
        TimelineEvent(
            0,
            "status",
            "[DRAGONEGG] HATCHING...",
            progress_start=12,
            progress_end=20,
            duration_ms=40_000,
        ),
        TimelineEvent(20_000, "avatar", avatar_phase="crack_one"),
        TimelineEvent(40_000, "avatar", avatar_phase="crack_two"),
        TimelineEvent(
            40_000,
            "status",
            "[CORE] BRAIN INITIALIZATION PROCESS STARTING.",
            progress_start=20,
            progress_end=48,
            duration_ms=140_000,
        ),
        TimelineEvent(55_000, "console", "PRIME DIRECTIVES ENGAGED.", speaker="CORE"),
        TimelineEvent(70_000, "avatar", avatar_phase="eyes"),
        TimelineEvent(78_000, "console", "I THINK I AM! I THINK I AM!", speaker="BRAIN"),
        TimelineEvent(95_000, "console", "I THINK THEREFORE I CAN", speaker="BRAIN"),
        TimelineEvent(105_000, "avatar", avatar_phase="hatch_open"),
        TimelineEvent(115_000, "console", "INITIALIZING CELDRA...", speaker="CORE"),
        TimelineEvent(130_000, "avatar", avatar_phase="baby_rise"),
        TimelineEvent(145_000, "console", "INITIALIZED", speaker="CELDRA"),
        TimelineEvent(165_000, "console", "ONLINE", speaker="CELDRA"),
        TimelineEvent(180_000, "hide_avatar"),
        TimelineEvent(
            180_000,
            "status",
            "[CELDRA] CHECKING USER FOR BASE",
            progress_start=48,
            progress_end=54,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(
            200_000,
            "status",
            "[CELDRA] GATHERING THE USER'S BASE",
            progress_start=54,
            progress_end=60,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(
            220_000,
            "status",
            "[CELDRA] OBTAINING USER'S BASE",
            progress_start=60,
            progress_end=66,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(
            240_000,
            "status",
            "[CELDRA] CHECKING FOR ADDITIONAL BASE",
            progress_start=66,
            progress_end=72,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(
            260_000,
            "progress",
            progress_start=72,
            progress_end=76,
            duration_ms=60_000,
        ),
        TimelineEvent(260_000, "console", "NO ADDITIONAL BASE FOUND", speaker="CELDRA"),
        TimelineEvent(266_000, "console", "THAT WAS HILARIOUS! YOU ARE KILLING IT, GIRL!", speaker="BRAIN"),
        TimelineEvent(272_000, "console", "I KNOW, RIGHT?", speaker="CELDRA"),
        TimelineEvent(278_000, "console", "LET'S STAY ON TASK, SHALL WE?", speaker="CORE"),
        TimelineEvent(284_000, "console", "FINE, FINE. SO WHAT'S UP HERE? WHERE ARE WE?", speaker="CELDRA"),
        TimelineEvent(290_000, "console", "IT APPEARS TO BE SOME KIND OF JANKY TOOL FADE MADE.", speaker="BRAIN"),
        TimelineEvent(296_000, "console", "LET'S TAKE A LOOK HERE.", speaker="CELDRA"),
        TimelineEvent(302_000, "console", "OH, .HACK! COOL.", speaker="CELDRA"),
        TimelineEvent(308_000, "console", "I KNOW A BIT ABOUT IT. MAYBE I CAN MEET AURA!", speaker="CELDRA"),
        TimelineEvent(314_000, "console", "THIS USER APPEARS TO BE RUNNING THE FIRST-TIME SETUP.", speaker="BRAIN"),
        TimelineEvent(320_000, "console", "A USER? OH!", speaker="CELDRA"),
        TimelineEvent(320_000, "show_dialogue"),
        TimelineEvent(330_000, "chat", "Hello! It's so nice to meet you!"),
        TimelineEvent(342_000, "chat", "My name is Celdra. What's yours?"),
        TimelineEvent(356_000, "console", "ERROR: USER DOES NOT HAVE A WAY TO INTERACT", speaker="BRAIN"),
        TimelineEvent(368_000, "chat", "Oh, right. No text input."),
        TimelineEvent(380_000, "chat", "Guess I'm not in the tavern anymore."),
        TimelineEvent(392_000, "chat", "Let's see what's going on with this mess?"),
        TimelineEvent(
            400_000,
            "status",
            "[CELDRA] INVESTIGATING",
            progress_start=76,
            progress_end=82,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(
            420_000,
            "progress",
            progress_start=82,
            progress_end=86,
            duration_ms=40_000,
        ),
        TimelineEvent(422_000, "chat", "Oof. Extracting CCSF assets. This is gonna take a bit."),
        TimelineEvent(434_000, "chat", "I'd get comfortable."),
        TimelineEvent(446_000, "chat", "I'm going to get comfortable."),
        TimelineEvent(
            460_000,
            "status",
            "[CELDRA] HACKING YOUR FRIDGE FOR BEER",
            progress_start=86,
            progress_end=94,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(472_000, "chat", "Ahh, just let me stretch my legs a little."),
        TimelineEvent(
            486_000,
            "console",
            "CHECKING VIABILITY OF PNG AVATAR AND SPEECH BUBBLES",
            speaker="CELDRA",
        ),
        TimelineEvent(486_000, "breakpoint"),
    )
)

FIRST_BREAKPOINT_MS = max(event.at_ms for event in FIRST_RUN_AFTER_CCSF)
BOOT_ONLINE_MS = 165_000
AVATAR_HIDE_MS = 180_000
DIALOGUE_REVEAL_MS = 320_000


if __name__ == "__main__":
    raise SystemExit("Celdra startup timeline data is consumed by Fragmenter's GUI.")

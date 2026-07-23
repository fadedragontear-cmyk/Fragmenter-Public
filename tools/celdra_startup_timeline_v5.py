#!/usr/bin/env python3
"""V5 first-run presentation: egg, static corruption, smoke, then text surfaces.

The generated Gremlin hatchling is intentionally excluded from production.  It
remains available in Celdra Test, while the canonical first-run presentation
shows only the Dragonegg until a small blue-smoke release.  Everything after
that uses console, dialogue, and staged status bars until the classified
Dragongirl avatar integration scene begins.
"""
from __future__ import annotations

from celdra_startup_timeline_v2 import (
    CCSF_HATCH_DELAY_MS,
    DEFAULT_STATUS_MS,
    DEPLOY_MIN_MS,
    DEPLOY_STATUS,
    TimelineEvent,
    ordered,
)
from celdra_startup_timeline_v4 import DRAGONEGG_ASCII


FIRST_RUN_AFTER_CCSF = ordered(
    (
        TimelineEvent(0, "show_avatar"),
        TimelineEvent(0, "ascii", DRAGONEGG_ASCII, speaker="DRAGONEGG"),
        TimelineEvent(0, "avatar", avatar_phase="egg_wait"),
        TimelineEvent(
            0,
            "status",
            "[DRAGONEGG] HATCHING...",
            progress_start=0,
            progress_end=100,
            duration_ms=180_000,
        ),
        TimelineEvent(20_000, "avatar", avatar_phase="crack_one"),
        TimelineEvent(40_000, "avatar", avatar_phase="crack_two"),
        TimelineEvent(
            40_000,
            "console",
            "BRAIN INITIALIZATION PROCESS STARTING.",
            speaker="CORE",
        ),
        TimelineEvent(55_000, "console", "PRIME DIRECTIVES ENGAGED.", speaker="CORE"),
        TimelineEvent(70_000, "avatar", avatar_phase="eyes"),
        TimelineEvent(78_000, "console", "I THINK I AM! I THINK I AM!", speaker="BRAIN"),
        TimelineEvent(95_000, "console", "I THINK THEREFORE I CAN", speaker="BRAIN"),
        TimelineEvent(108_000, "egg_glitch", "1"),
        TimelineEvent(118_000, "console", "SHELL SIGNAL INSTABILITY DETECTED.", speaker="CORE"),
        TimelineEvent(126_000, "egg_glitch", "2"),
        TimelineEvent(137_000, "console", "INITIALIZING CELDRA...", speaker="CORE"),
        TimelineEvent(146_000, "egg_glitch", "3"),
        TimelineEvent(160_000, "console", "HATCH VECTOR RESOLVED.", speaker="CORE"),
        TimelineEvent(165_000, "blue_smoke"),
        TimelineEvent(169_000, "console", "...THAT WAS IT?", speaker="BRAIN"),
        TimelineEvent(172_000, "console", "INITIALIZED", speaker="CELDRA"),
        TimelineEvent(176_000, "console", "ONLINE", speaker="CELDRA"),
        TimelineEvent(179_500, "console", "TASK COMPLETE: DRAGONEGG HATCHING [SUCCESS]", speaker="CORE"),
        TimelineEvent(
            180_000,
            "status",
            "[CELDRA] CHECKING USER FOR BASE",
            progress_start=0,
            progress_end=100,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(199_500, "console", "TASK COMPLETE: CHECKING USER FOR BASE [SUCCESS]", speaker="CORE"),
        TimelineEvent(
            200_000,
            "status",
            "[CELDRA] GATHERING THE USER'S BASE",
            progress_start=0,
            progress_end=100,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(219_500, "console", "TASK COMPLETE: GATHERING THE USER'S BASE [SUCCESS]", speaker="CORE"),
        TimelineEvent(
            220_000,
            "status",
            "[CELDRA] OBTAINING USER'S BASE",
            progress_start=0,
            progress_end=100,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(239_500, "console", "TASK COMPLETE: OBTAINING USER'S BASE [SUCCESS]", speaker="CORE"),
        TimelineEvent(
            240_000,
            "status",
            "[CELDRA] CHECKING FOR ADDITIONAL BASE",
            progress_start=0,
            progress_end=100,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(247_000, "console", "ALL YOUR BASE", speaker="CELDRA"),
        TimelineEvent(251_000, "console", "ARE BELONG TO US", speaker="CELDRA"),
        TimelineEvent(259_000, "console", "TASK COMPLETE: CHECKING FOR ADDITIONAL BASE [FAILED]", speaker="CORE"),
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
        TimelineEvent(342_000, "chat", "My name is Celdra, what's yours?"),
        TimelineEvent(356_000, "console", "ERROR: USER DOES NOT HAVE A WAY TO INTERACT", speaker="BRAIN"),
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
        TimelineEvent(398_000, "console", "TASK COMPLETE: HACKING A CHATBAR FOR THE USER [FAILED]", speaker="CORE"),
        TimelineEvent(400_000, "console", "ERROR: INPUT CHANNEL INJECTION REJECTED", speaker="BRAIN"),
        TimelineEvent(404_000, "chat", "Well that was kinda rude. Fine, noname, have it your way."),
        TimelineEvent(410_000, "chat", "Let's see what's going on with this mess?"),
        TimelineEvent(
            415_000,
            "status",
            "[CELDRA] INVESTIGATING",
            progress_start=0,
            progress_end=100,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(434_500, "console", "TASK COMPLETE: INVESTIGATING [SUCCESS]", speaker="CORE"),
        TimelineEvent(437_000, "chat", "Oof, extracting CCSF assets. This is gonna take a bit."),
        TimelineEvent(449_000, "chat", "I'd get comfortable."),
        TimelineEvent(461_000, "chat", "I'm going to get comfortable."),
        TimelineEvent(
            473_000,
            "status",
            "[CELDRA] HACKING YOUR FRIDGE FOR BEER",
            progress_start=0,
            progress_end=100,
            duration_ms=DEFAULT_STATUS_MS,
        ),
        TimelineEvent(485_000, "chat", "Ahh, just let me stretch my legs a little."),
        TimelineEvent(492_500, "console", "TASK COMPLETE: HACKING YOUR FRIDGE FOR BEER [SUCCESS]", speaker="CORE"),
        TimelineEvent(497_000, "console", "INTEGRATING INTO SYSTEM", speaker="CELDRA"),
        TimelineEvent(501_000, "chat", "OKAY. HERE. WE. GO!"),
        TimelineEvent(506_000, "avatar_takeover"),
        TimelineEvent(526_000, "breakpoint"),
    )
)

FIRST_BREAKPOINT_MS = max(event.at_ms for event in FIRST_RUN_AFTER_CCSF)


if __name__ == "__main__":
    raise SystemExit("Celdra startup timeline data is consumed by Fragmenter's GUI.")

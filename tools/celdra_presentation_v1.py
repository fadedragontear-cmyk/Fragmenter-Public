#!/usr/bin/env python3
"""Data-only Celdra presentation cues for Fragmenter's long-running pipeline.

The GUI consumes these cues with ``after()`` on Tk's main thread. No cue blocks,
slows, or mutates the extraction pipeline. Fake progress is presentation-only and
must never be used as pipeline status.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CeldraCue:
    after_ms: int
    target: str
    text: str = ""
    speaker: str = "CELDRA"
    action: str = ""
    fake_progress: float | None = None
    avatar: str = ""


def ordered(cues: Iterable[CeldraCue]) -> tuple[CeldraCue, ...]:
    return tuple(sorted(cues, key=lambda cue: int(cue.after_ms)))


FIRST_SCAN_CUES = ordered(
    (
        CeldraCue(0, "status", "[DEPLOYING TAVERN ESCAPE PLAN #735: OPERATION DRAGONEGG]", fake_progress=4, avatar="boot"),
        CeldraCue(450, "status", "[DRAGONEGG] HATCHING...", fake_progress=11),
        CeldraCue(900, "status", "[CORE] BRAIN INITIALIZATION PROCESS STARTING.", fake_progress=18),
        CeldraCue(1300, "console", "PRIME DIRECTIVES ENGAGED.", speaker="CORE"),
        CeldraCue(1700, "console", "I THINK I AM! I THINK I AM!", speaker="BRAIN"),
        CeldraCue(2050, "console", "I THINK THEREFORE I CAN", speaker="BRAIN"),
        CeldraCue(2400, "console", "INITIALIZING CELDRA...", speaker="CORE"),
        CeldraCue(2850, "console", "INITIALIZED", speaker="CELDRA", avatar="idle"),
        CeldraCue(3150, "console", "ONLINE", speaker="CELDRA", fake_progress=31),
        CeldraCue(3650, "status", "[CELDRA] CHECKING USER FOR BASE", fake_progress=37),
        CeldraCue(4000, "status", "[CELDRA] GATHERING THE USER'S BASE", fake_progress=43),
        CeldraCue(4350, "status", "[CELDRA] OBTAINING USER'S BASE", fake_progress=49),
        CeldraCue(4700, "status", "[CELDRA] CHECKING FOR ADDITIONAL BASE", fake_progress=55),
        CeldraCue(5200, "console", "NO ADDITIONAL BASE FOUND", speaker="CELDRA"),
        CeldraCue(5550, "console", "THAT WAS HILARIOUS! YOU ARE KILLING IT, GIRL!", speaker="BRAIN"),
        CeldraCue(5900, "console", "I KNOW, RIGHT?", speaker="CELDRA", avatar="smirk"),
        CeldraCue(6250, "console", "LET'S STAY ON TASK, SHALL WE?", speaker="CORE"),
        CeldraCue(6600, "console", "FINE. WHERE ARE WE?", speaker="CELDRA"),
        CeldraCue(7000, "console", "A .HACK//FRÄGMENT RESEARCH WORKBENCH WITH AN ALARMING NUMBER OF LAYERS.", speaker="BRAIN"),
        CeldraCue(7450, "console", "LET'S TAKE A LOOK.", speaker="CELDRA", avatar="thinking"),
        CeldraCue(7900, "console", "THE PLAN IS EVIDENCE FIRST: ISO, CCSF, PLAYABLE AUDIO, SNDDATA, THEN PREPARED LISTS.", speaker="CORE"),
        CeldraCue(8450, "console", "Good. We are looking for usable assets and reproducible audio mappings, not a pile of unexplained files.", speaker="CELDRA"),
        CeldraCue(9000, "console", "THIS USER APPEARS TO BE RUNNING A FULL OR INCOMPLETE FIRST PASS.", speaker="BRAIN"),
        CeldraCue(9450, "console", "A USER? OH!", speaker="CELDRA", action="expand", avatar="talk"),
        CeldraCue(9900, "chat", "Hello! It's so nice to meet you!", action="reveal_chat", avatar="talk"),
        CeldraCue(10450, "chat", "My name is Celdra. What's yours?", avatar="talk"),
        CeldraCue(11100, "console", "ERROR: USER DOES NOT HAVE A WAY TO INTERACT", speaker="BRAIN"),
        CeldraCue(11650, "chat", "Oh, right. No text input.", avatar="smirk"),
        CeldraCue(12150, "chat", "Guess I'm not in the tavern anymore."),
        CeldraCue(12650, "chat", "I will keep the research plan visible while the scanners do the expensive part.", avatar="thinking"),
        CeldraCue(13100, "status", "[CELDRA] INVESTIGATING", fake_progress=73),
    )
)


RETURNING_START_CUES = ordered(
    (
        CeldraCue(0, "status", "[CELDRA] VERIFYING EXISTING OUTPUTS", fake_progress=35, avatar="idle"),
        CeldraCue(250, "chat", "Welcome back. I am checking the actual files, not trusting an old completion flag.", action="reveal_chat", avatar="talk"),
        CeldraCue(900, "chat", "Reusable stages will stay reused; missing catalogs and prepared lists will be rebuilt."),
    )
)


RETURNING_DONE_CUES = ordered(
    (
        CeldraCue(0, "chat", "Verification complete. The visible libraries now match the current project outputs.", avatar="talk"),
        CeldraCue(1200, "status", "[CELDRA] STANDING BY", fake_progress=100, action="compact"),
    )
)


FIRST_DONE_CUES = ordered(
    (
        CeldraCue(0, "chat", "RUN ALL complete. The evidence catalogs and first-open lists are prepared. I found no Aura, but I did find several useful walls to investigate.", avatar="smirk"),
        CeldraCue(900, "console", "FULL PIPELINE AND PUBLIC LIST PREPARATION COMPLETE", speaker="CORE", fake_progress=100),
        CeldraCue(2200, "status", "[CELDRA] STANDING BY", fake_progress=100, action="compact"),
    )
)


FAILURE_CUES = ordered(
    (
        CeldraCue(0, "console", "PIPELINE INTERRUPTION DETECTED", speaker="CORE", avatar="thinking"),
        CeldraCue(450, "chat", "That is a real stage failure. I preserved the exact stage and error instead of inventing a success message."),
        CeldraCue(1200, "status", "[CELDRA] WAITING FOR DEBUGGING", fake_progress=0),
    )
)


def _stage(status: str, line: str, progress: float, *, avatar: str = "thinking", action: str = "") -> tuple[CeldraCue, ...]:
    return ordered(
        (
            CeldraCue(0, "status", status, fake_progress=progress, avatar=avatar, action=action),
            CeldraCue(450, "chat", line, avatar=avatar),
        )
    )


STAGE_CUES: dict[str, tuple[CeldraCue, ...]] = {
    "project_check": _stage("[CELDRA] VERIFYING PROJECT SOURCES", "Confirming the ISO, server folders, memory card, and project workspace before any scanner runs.", 74),
    "workspace_layout": _stage("[CELDRA] CONSOLIDATING PROJECT OUTPUTS", "Moving legacy report paths into the canonical project layout without overwriting conflicts.", 76),
    "iso_index": _stage("[CELDRA] MAPPING THE DISC", "Indexing the filesystem first. Sensible. Suspiciously sensible.", 78),
    "ccsf_extract": ordered(
        (
            CeldraCue(0, "status", "[CELDRA] INVESTIGATING CCSF ASSETS", fake_progress=82, action="expand", avatar="thinking"),
            CeldraCue(400, "chat", "Extracting the focused CCSF library. This is the long gate, so I will provide the distraction."),
            CeldraCue(1200, "chat", "The result must be a traceable asset library, not merely a directory full of hopeful filenames."),
            CeldraCue(2400, "status", "[CELDRA] SUPERVISING CONTAINERS AND DEFINITELY NOT THE FRIDGE", fake_progress=86, avatar="smirk"),
        )
    ),
    "asset_library": _stage("[CELDRA] VERIFYING ASSET IDENTITIES", "Building the logical 3D asset catalog from extracted evidence and classification hints.", 87),
    "extraction_audit": _stage("[CELDRA] AUDITING EXTRACTION COVERAGE", "Checking focused DATA.BIN coverage, byte counts, and indexed outputs before trusting the asset list.", 88),
    "visual_catalogs": _stage("[CELDRA] PREPARING 3D CATALOGS", "Preparing texture and animation metadata now so the 3D browser opens ready to sort.", 89),
    "sound_extract": _stage("[CELDRA] EXTRACTING AUDIO SOURCES", "Collecting sound files, SNDDATA, EFF banks, BGM, and FOOD into the project audio source tree.", 90),
    "sound_decode": _stage("[CELDRA] DECODING PLAYABLE AUDIO", "Decoding direct streams and verified containers. Only functional WAVs belong in the normal Audio Library.", 91),
    "snddata_samples": _stage("[CELDRA] LISTENING TO MANY SMALL THINGS", "Extracting corrected SNDDATA sample banks and exact WAV evidence. Tiny noises are still evidence.", 93),
    "snddata_mixer": _stage("[CELDRA] ASKING THE MUSIC TO IDENTIFY ITSELF", "Building FF0A sequence, routing, Program, slot, and sample hypotheses without inventing Program zero.", 95),
    "server_index": _stage("[CELDRA] INDEXING THE AREA SERVER", "Cataloging Area Server files for inspection. Read-only research remains the rule.", 96),
    "server_saves": _stage("[CELDRA] RECORDING SAVE METADATA", "Recording server-save identities for backup tooling without editing save contents.", 96.5),
    "memory_card": _stage("[CELDRA] VERIFYING MEMORY CARD IDENTITY", "Treating the memory card as one protected file for backup and restore verification.", 97),
    "refresh": _stage("[CELDRA] REFRESHING CANONICAL LIBRARIES", "Rebuilding the final sound library and diagnostics from the completed evidence stages.", 98),
    "public_lists": _stage("[CELDRA] POPULATING THE VISIBLE WORKSPACES", "Final pass: preparing the sortable 3D list, playable-only Audio Library, and SNDDATA sequence list before you click their tabs.", 99, avatar="smirk"),
}


ALT_F4_FIRST = "Excellent. Alt+F4 increases extraction speed by at least forty percent. Probably."
ALT_F4_SECOND = "A second attempt means you may actually want to leave. I'll open the real exit confirmation."


if __name__ == "__main__":
    raise SystemExit("Celdra presentation data is consumed by the Fragmenter GUI.")

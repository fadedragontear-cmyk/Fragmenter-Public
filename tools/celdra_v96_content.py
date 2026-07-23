#!/usr/bin/env python3
"""Live RUN ALL reactions and expanded Gremlin personalities for Celdra V96."""
from __future__ import annotations

from celdra_v95_content import (
    CONSOLE_BANTER as V95_CONSOLE_BANTER,
    GREMLIN_HAVOC_STAGES as V95_GREMLIN_HAVOC_STAGES,
    STORY_FILLER as V95_STORY_FILLER,
    WAITING_FILLER as V95_WAITING_FILLER,
)

STORY_END_DELAY_MS = 1_800_000
WAITING_FILLER_DELAY_MS = 55_000
GREMLIN_START_DELAY_MS = 205_000
GREMLIN_SWARM_SIZE = 9

GREMLIN_PERSONALITIES = (
    {
        "name": "BYTE",
        "role": "tooltip eater",
        "accent": "#79cff1",
        "temperament": "search",
        "claim": "REQUESTING TOOLTIP ALLOCATION",
    },
    {
        "name": "HEX",
        "role": "offset tracker",
        "accent": "#b678df",
        "temperament": "claim",
        "claim": "LEAVING 0x FOOTPRINTS",
    },
    {
        "name": "CACHE",
        "role": "log hoarder",
        "accent": "#efbd70",
        "temperament": "idle",
        "claim": "CACHING RECENT BRAIN COMPLAINTS",
    },
    {
        "name": "LOOP",
        "role": "path repeater",
        "accent": "#f09ccc",
        "temperament": "search",
        "claim": "ROUTE COMPLETE // RESTARTING ROUTE",
    },
    {
        "name": "PING",
        "role": "progress-bar percussion",
        "accent": "#9ce2dc",
        "temperament": "claim",
        "claim": "TESTING PROGRESS BAR LATENCY",
    },
    {
        "name": "PATCH",
        "role": "unauthorized fixer",
        "accent": "#ffdaa0",
        "temperament": "squished",
        "claim": "PATCHING CELDRA HORN ALIGNMENT",
    },
    {
        "name": "ROOT",
        "role": "party leader",
        "accent": "#45a9db",
        "temperament": "claim",
        "claim": "CLAIMING ROOT TOWN ADMINISTRATION",
    },
    {
        "name": "NULL",
        "role": "vanishing process",
        "accent": "#c7f2ff",
        "temperament": "failed",
        "claim": "PROCESS NOT FOUND // STILL VISIBLE",
    },
    {
        "name": "GLITCH",
        "role": "status duplicator",
        "accent": "#df5e8e",
        "temperament": "search",
        "claim": "DUPLICATING ONE HARMLESS STATUS LINE",
    },
)

GREMLIN_HAVOC_STAGES = (
    (0, "LEGACY HATCHLINGS // 9 ONLINE"),
    (8, "BYTE // REQUESTING TOOLTIP ALLOCATION"),
    (17, "HEX // LEAVING 0x FOOTPRINTS"),
    (26, "CACHE // ARCHIVING BRAIN COMPLAINTS"),
    (35, "LOOP // RESTARTING COMPLETED ROUTE"),
    (44, "PING // TESTING PROGRESS BAR LATENCY"),
    (53, "PATCH // APPROACHING CELDRA HORN"),
    (62, "ROOT // FORMING PARTY OF THREE"),
    (71, "NULL // PROCESS NOT FOUND // STILL VISIBLE"),
    (80, "GLITCH // DUPLICATING STATUS LINE"),
    (88, "SWARM // OCCUPYING AVATAR SAFE AREA"),
    (94, "CELDRA TEMPER THRESHOLD EXCEEDED"),
    (100, "HAVOC COMPLETE // BANISHMENT PENDING"),
)

# Actual live RUN ALL stages.  These are triggered from executor events rather
# than the fixed presentation clock.
STAGE_SCENES = {
    "project_check": {
        "pose": "confused",
        "start": "First scan: verify the ISO, Area Server, saves, memory card, and workspace before any extractor gets ideas.",
        "finish": "Project sources answered roll call. Nothing is being inferred from a missing path.",
    },
    "workspace_layout": {
        "pose": "unenthused",
        "start": "Workspace consolidation is sorting old extracted, decoded, work, cache, and report paths without overwriting conflicts.",
        "finish": "The folders have been negotiated into one canonical layout. Several of them remain resentful.",
    },
    "iso_index": {
        "pose": "suspicious",
        "start": "The ISO index records filesystem paths, offsets, and sizes. It is the map every later extraction should be able to cite.",
        "finish": "Disc map complete. We know where the files begin before claiming to know what they mean.",
    },
    "ccsf_extract": {
        "pose": "excited",
        "start": "CCSF extraction is scanning confirmed containers, testing gzip members, and preserving each bundle's source path and offset.",
        "finish": "The CCSF gate cleared. The long scan just became an asset library we can reproduce instead of a pile of lucky files.",
    },
    "asset_library": {
        "pose": "smile",
        "start": "The asset library collapses duplicate physical files into logical assets while retaining every source reference.",
        "finish": "Logical assets verified. Duplicate copies may now stop pretending they are unique discoveries.",
    },
    "extraction_audit": {
        "pose": "suspicious",
        "start": "The extraction audit checks coverage, counters, source evidence, and blockers. This is where optimism has to show its work.",
        "finish": "Extraction audit passed. Byte counts are less charming than confidence, but considerably more useful.",
    },
    "visual_catalogs": {
        "pose": "excited",
        "start": "Visual catalogs turn extracted CCSF evidence into searchable texture and animation records without modifying the source bundles.",
        "finish": "Texture and animation catalogs are ready. Poses may now be dramatic in an indexed and reproducible manner.",
    },
    "sound_extract": {
        "pose": "smile",
        "start": "Audio-source extraction separates sound files, SNDDATA, effect banks, BGM, and FOOD into the canonical source library.",
        "finish": "Audio sources collected. Nothing has been decoded merely because its filename sounded musical.",
    },
    "sound_decode": {
        "pose": "confused",
        "start": "Direct-audio decoding handles verified streams and containers. SNDDATA sequencing remains a separate problem on purpose.",
        "finish": "Direct audio decoded. Any remaining drawer-full-of-cutlery noises are now documented drawer-full-of-cutlery noises.",
    },
    "snddata_samples": {
        "pose": "suspicious",
        "start": "SNDDATA sample extraction follows SCEIVagi boundaries and the corrected bank-phase policy before producing PS2 ADPCM and WAV evidence.",
        "finish": "Sample library written. Plausible WAVs are evidence, not a declaration that the whole synthesizer has surrendered.",
    },
    "snddata_mixer": {
        "pose": "wink",
        "start": "The mixer index connects sequences, Program resources, slots, and exact sample IDs while keeping unresolved routing labeled as hypothesis.",
        "finish": "Mixer hypotheses ranked. CORE still refuses to accept 'probably Program zero' as a binary structure.",
    },
    "server_index": {
        "pose": "excited",
        "start": "Area Server indexing records files and readable metadata without altering the server installation.",
        "finish": "Area Server indexed. It has folders on purpose, which makes it the most emotionally stable subsystem here.",
    },
    "server_saves": {
        "pose": "unenthused",
        "start": "Server-save indexing records identity and metadata only. The editing tools remain behind backup and proof gates.",
        "finish": "Server-save metadata recorded. No characters were volunteered for experimental archaeology.",
    },
    "memory_card": {
        "pose": "suspicious",
        "start": "Memory-card verification treats the image as one protected file and records the identity required for safe backup and restore.",
        "finish": "Memory card verified. Whole-file identity first; clever tricks never.",
    },
    "refresh": {
        "pose": "cool",
        "start": "The final refresh rebuilds public libraries and diagnostics from canonical outputs, not from whatever folder happened to be nearby.",
        "finish": "Public libraries refreshed. Reports now describe what actually ran, what it produced, and what remains unresolved.",
    },
}

PROGRESS_REACTIONS = {
    "ccsf_extract": (
        "CCSF scan is one quarter through its selected containers. Slow is acceptable; untraceable is not.",
        "Halfway through the CCSF container list. The extractor has developed a committed relationship with DATA.BIN.",
        "Three quarters through CCSF extraction. BRAIN has begun threatening the remaining offsets personally.",
    ),
    "sound_decode": (
        "Direct-audio decode is one quarter complete. So far the speakers remain structurally attached.",
        "Half of the direct-audio targets have been processed. Several noises have applied for instrument status.",
        "Direct-audio decode is three quarters complete. The cutlery drawer remains under investigation.",
    ),
    "snddata_samples": (
        "One quarter of the SNDDATA banks have been processed under the corrected boundary policy.",
        "Half of the SNDDATA sample banks are cataloged. Sample zero is being watched with appropriate suspicion.",
        "Three quarters of the sample banks are done. The remaining banks have lost the element of surprise.",
    ),
    "snddata_mixer": (
        "Routing analysis is one quarter complete. Exact references are winning against convenient guesses.",
        "Halfway through mixer analysis. Program changes are being asked to identify their samples.",
        "Three quarters through routing analysis. Unknowns remain unknown, but now they have addresses.",
    ),
}

EXTRA_STORY_FILLER = (
    (1_446_000, "confused", "Live RUN ALL events now interrupt this fixed script when a real stage starts. That means the commentary can finally react to the machine instead of predicting it."),
    (1_476_000, "smile", "Project validation is deliberately boring: confirm every source path, then write a report future runs can compare instead of asking the user to remember."),
    (1_506_000, "suspicious", "The ISO index is not extraction. It is the coordinate system that lets every extractor say exactly where its evidence came from."),
    (1_536_000, "excited", "CCSF extraction is the long dungeon. Containers, gzip members, signatures, duplicate hashes, and source offsets all have to survive the trip together."),
    (1_566_000, "wink", "The asset library is where repeated physical files become one logical object with several witnesses. Even bytes benefit from corroboration."),
    (1_596_000, "unenthused", "The extraction audit exists because a folder full of output can still be incomplete. A large result is not automatically a complete result."),
    (1_626_000, "smile", "Visual catalogs preserve the source CCSF while describing textures and animation candidates separately. Presentation should be editable without rewriting evidence."),
    (1_656_000, "confused", "Direct audio and SNDDATA music are different routes. One decoder should not impersonate an entire synthesizer because both eventually make sound."),
    (1_686_000, "suspicious", "SNDDATA samples need correct boundaries. SNDDATA music also needs routing, tuning, loops, envelopes, controllers, and writers. Those are different victories."),
    (1_716_000, "excited", "The server, saves, and memory-card scans complete the project map. Each one stays read-only until backup and reconstruction proofs exist."),
    (1_746_000, "smile", "The final refresh turns all those outputs into the public libraries and support reports you can hand back without sending the game itself."),
    (1_776_000, "wink", "That is Fragmenter's current rule: expose what we know, label what we suspect, preserve what we do not yet understand, and give the Gremlins no write permissions."),
)

EXTRA_CONSOLE_BANTER = (
    (1_451_000, "CORE", "LIVE STAGE COMMENTARY SUBSCRIBED TO RUN ALL EVENT BUS."),
    (1_461_000, "BRAIN", "FINALLY. SHE CAN ARGUE WITH THE ACTUAL PROGRESS BAR."),
    (1_481_000, "CORE", "PROJECT VALIDATION PRODUCES SOURCE IDENTITY AND PREFLIGHT REPORTS."),
    (1_511_000, "BRAIN", "THE ISO INDEX IS A MAP. DO NOT CALL THE MAP THE TREASURE."),
    (1_541_000, "CORE", "CCSF PROGRESS REPORTS CONTAINER COUNTS, BYTES, BUNDLES, AND INDEXED ASSETS."),
    (1_571_000, "BRAIN", "DUPLICATE HASHES: THE SAME MYSTERY WEARING ANOTHER PATH."),
    (1_601_000, "CORE", "EXTRACTION AUDIT MAY BLOCK DOWNSTREAM CLAIMS WHEN COVERAGE IS INCOMPLETE."),
    (1_631_000, "CELDRA", "CORE HAS INVENTED A BOSS FIGHT CALLED COVERAGE BLOCKER."),
    (1_661_000, "CORE", "DIRECT AUDIO DECODE AND SNDDATA ROUTING REMAIN SEPARATE PIPELINES."),
    (1_691_000, "BRAIN", "SOUNDING LIKE MUSIC IS NOT A SERIALIZER. WE HAVE COVERED THIS."),
    (1_721_000, "CORE", "SERVER, SAVE, AND MEMORY-CARD STAGES ARE READ-ONLY IDENTITY SCANS."),
    (1_751_000, "BRAIN", "AND THEN THE REFRESH STAGE SWEEPS UP EVERY REPORT THEY LEFT ON THE FLOOR."),
    (1_781_000, "CORE", "SUPPORT OUTPUT EXCLUDES ISO, SNDDATA, WAV, CCSF, SAVE, AND MEMORY-CARD BINARIES."),
)

STORY_FILLER = tuple(V95_STORY_FILLER) + EXTRA_STORY_FILLER
CONSOLE_BANTER = tuple(V95_CONSOLE_BANTER) + EXTRA_CONSOLE_BANTER
WAITING_FILLER = tuple(V95_WAITING_FILLER) + (
    ("confused", "A live stage update will interrupt me when something real changes. Until then, the progress bar and I are maintaining professional distance."),
    ("smile", "CORE is watching counters, BRAIN is watching for nonsense, and I am watching both of them pretend that is not teamwork."),
    ("suspicious", "The last scan event is still active. No news is not failure; it is merely poor entertainment design."),
    ("wink", "Every completed stage leaves a report. Every Gremlin leaves a complaint. Both are useful for reconstruction."),
)

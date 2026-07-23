#!/usr/bin/env python3
"""Tutorial and research guidance used by Celdra on the SNDDATA mixer page."""
from __future__ import annotations

TUTORIAL_STEPS = (
    {
        "title": "1 / 7 — Prepare the actual Audio pages",
        "pose": "suspicious",
        "body": (
            "Open Audio → Audio Pipeline. Use Prepare Complete Audio Workspace for the normal audio-only path, "
            "or Celdra mode → Prepare Missing + Analyze when you want Fragmenter to run only stale or absent stages and process the reports afterward. "
            "RUN ALL also performs these stages. A current sample report must use boundary policy v3 before later sample WAVs are trusted."
        ),
    },
    {
        "title": "2 / 7 — Classify decoded sounds first",
        "pose": "smile",
        "body": (
            "Open Audio → Sample Classifier. Select a row and use Play Selected. The full editor on the right stores label, family, playback mode, root note, usability, tags, and notes. "
            "For fast sorting, use Quick classification at the bottom: choose a category, then Send Selected or Send + Next. Create Category makes a project-local category when the built-in list is not specific enough."
        ),
    },
    {
        "title": "3 / 7 — Treat boundary problems as extraction problems",
        "pose": "confused",
        "body": (
            "If a WAV loses more of its beginning on later sample numbers, or contains the end of one sound and the start of another, stop classifying that bank as reliable. "
            "Run Extract corrected SNDDATA samples again. Celdra mode records boundary policy, constant or progressive correction, and the sample-0228 timing anchor in its report."
        ),
    },
    {
        "title": "4 / 7 — Find a sequence in the Research Mixer",
        "pose": "smile",
        "body": (
            "Open Audio → SNDDATA Research Mixer. The upper-left table is Sequences. Search or sort it and select a row with note events. "
            "The upper-middle table then shows Program candidates. A row marked renderable means only that Fragmenter can produce a bounded experiment; it does not mean the routing or instruments are authentic."
        ),
    },
    {
        "title": "5 / 7 — Compare the candidate and its exact samples",
        "pose": "suspicious",
        "body": (
            "Use the Routing dropdown above the mixer to compare Auto, program_change, and channel_as_program. Select a Program candidate, then open the Samples research page below to inspect its exact required sample IDs. "
            "Missing Program indexes and missing sample WAVs are evidence walls, not invitations to substitute convenient data."
        ),
    },
    {
        "title": "6 / 7 — Listen to two different proofs",
        "pose": "excited",
        "body": (
            "In the Playback / render deck, Render Event / PCM Proof tests sequence timing and event structure without claiming correct game instruments. Render Candidate tests the current Program and sample hypothesis. "
            "If only one candidate plays and it sounds unlike the game, record that as a failed or incomplete hypothesis; do not treat successful WAV output as confirmation."
        ),
    },
    {
        "title": "7 / 7 — Record the next useful decision",
        "pose": "wink",
        "body": (
            "Use Notes and Flags in the lower research pages, then export a Research Bundle when a comparison matters. Save a mapping or mark a candidate Plausible, Confirmed, or Rejected only after listening and recording why. "
            "Celdra mode automates preparation and report processing, but it deliberately never accepts a mapping or writes game data for you."
        ),
    },
)

RESEARCH_OVERVIEW = (
    "The Audio tab contains separate jobs. Audio Library is for ordinary playable WAVs. Sample Classifier is for listening to and labeling decoded SNDDATA samples. "
    "SNDDATA Research Mixer connects parsed sequence events to routing hypotheses, Program resources, exact sample IDs, and bounded preview renders. Audio Pipeline prepares those reports. "
    "Celdra mode can run stale or missing audio stages and consolidate their reports, but it will not invent mappings, confirm a plausible render, or modify game data. "
    "The current boundary policy must also prove whether a bank has one constant phase or progressive per-entry drift before its later samples are trusted."
)

NEXT_STEPS = (
    "Rebuild samples when the report predates boundary policy v3 or later entries drift into adjacent audio.",
    "Use Sample Classifier quick categories to sort playable samples without losing detailed metadata.",
    "Run Celdra mode to consolidate sample health, classification backlog, mixer coverage, and the next safe action.",
    "Start mixer work with a sequence that has note events and inspect why its best candidate is or is not renderable.",
    "Compare program_change and channel_as_program only where Auto remains unresolved.",
    "Treat a lone strange-sounding preview as diagnostic evidence, not reconstructed game music.",
    "Export flagged evidence before changing parser, decoder, tuning, envelope, or writer assumptions.",
)

QUICK_HELP = (
    ("Audio Pipeline", "Prepare missing or stale audio stages; Celdra mode also processes the resulting reports."),
    ("Sample Classifier", "Play samples, use quick categories, or store detailed instrument/effect metadata."),
    ("Evidence", "Readable routing and candidate evidence for the current mixer selection."),
    ("Samples", "Exact required sample IDs, decoded coverage, boundaries, and individual WAV audition."),
    ("Notes", "Persistent observations for the selected sequence, candidate, or sample."),
    ("Flags", "Assets marked for comparison across sessions and research bundles."),
    ("Research Bundle", "Reproducible metadata exports that exclude copyrighted game payloads."),
)

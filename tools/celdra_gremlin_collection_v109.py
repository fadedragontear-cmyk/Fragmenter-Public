#!/usr/bin/env python3
"""V109 dialogue and status content for the collectible Gremlin runtime."""
from __future__ import annotations

SERENIAL_DISCORD_REDIRECT_V109 = "https://www.serenial.ca"
SERENIAL_DISCORD_INVITE_V109 = "https://www.discord.gg/0jHGrvDVojtH1nWP"

# delay_ms, pose, dialogue, target, relx, rely, effect label
GREMLIN_CAPTURE_SKITS_V109 = {
    "BYTE": (
        (1_200, "confused", "BYTE is back. He has mistaken the pipeline plan for a tasting menu.", "pipeline", 0.58, 0.24, "TOOLTIP CONSUMED"),
        (6_200, "suspicious", "He only eats presentation labels, but he is doing it with the confidence of a documented feature.", "pipeline", 0.32, 0.62, "DOCUMENTATION: DELICIOUS"),
        (12_400, "wink", "I made a decoy tooltip that says FREE METADATA. He has absolutely no survival instincts.", "progress", 0.52, 0.42, "FREE METADATA"),
        (18_800, "smile", "Got him. Closing the tooltip and routing one extremely round process into the stable.", "avatar", 0.70, 0.72, "CAPTURE ROUTE READY"),
    ),
    "HEX": (
        (1_200, "suspicious", "HEX has returned and is assigning offsets to every place he stands.", "progress", 0.18, 0.20, "0x0018"),
        (6_200, "confused", "He has mapped the progress board, the scrollbar, and one corner that does not technically exist.", "progress", 0.78, 0.22, "0x00A4"),
        (12_400, "unenthused", "I changed the stable entrance label to 0xHOME. This is embarrassing, but it is working.", "progress", 0.52, 0.72, "0xHOME"),
        (18_800, "smile", "Coordinate resolved. Tall process contained.", "avatar", 0.68, 0.70, "OFFSET LOCKED"),
    ),
    "CACHE": (
        (1_200, "unenthused", "CACHE is stealing recent console complaints and putting them in his satchel.", "log", 0.78, 0.70, "CACHED: BRAIN COMPLAINT"),
        (6_200, "suspicious", "He calls it a knowledge base. BRAIN calls it evidence tampering with a retention policy.", "console", 0.72, 0.54, "CACHE HIT"),
        (12_400, "wink", "I placed a newer complaint inside the stable. Cache invalidation remains the oldest trick in computing.", "log", 0.35, 0.32, "NEWER ENTRY AVAILABLE"),
        (18_800, "smile", "Satchel, Gremlin, and stolen complaint secured.", "avatar", 0.70, 0.72, "CACHE COMMITTED"),
    ),
    "LOOP": (
        (1_200, "confused", "LOOP completed one lap of Run All and interpreted success as an instruction to repeat it forever.", "lower", 0.18, 0.35, "ROUTE COMPLETE"),
        (6_200, "suspicious", "Second lap. Same route. Slightly more bow.", "upper", 0.82, 0.32, "RESTARTING ROUTE"),
        (12_400, "unenthused", "Third lap. I have moved the finish line into the stable.", "lower", 0.22, 0.72, "FINISH LINE MOVED"),
        (18_800, "smile", "Route complete. Route closed. Pink bow accounted for.", "avatar", 0.70, 0.72, "LOOP TERMINATED POLITELY"),
    ),
    "PING": (
        (1_200, "suspicious", "PING is percussion-testing the progress bar again.", "progress", 0.48, 0.72, "TAP TAP TAP"),
        (6_200, "confused", "He insists this is latency measurement. The measurement has a rhythm and no methodology.", "console", 0.55, 0.86, "LOAD TEST: INAPPROPRIATE"),
        (12_400, "wink", "I installed a quieter test bar inside the stable. It is padded.", "progress", 0.80, 0.40, "PADDED TEST SURFACE"),
        (18_800, "smile", "Bounce captured. Console dignity partially restored.", "avatar", 0.70, 0.72, "PING RECEIVED"),
    ),
    "PATCH": (
        (1_200, "shocked", "PATCH is on my horn again. My horn is not an open issue.", "avatar", 0.56, 0.18, "HORN ALIGNMENT: OPEN"),
        (6_200, "unenthused", "He has applied a bandage to geometry that was already correct.", "avatar", 0.42, 0.24, "COSMETIC PATCH APPLIED"),
        (12_400, "suspicious", "I filed a critical stable-door alignment ticket. He cannot resist self-assigned authority.", "avatar", 0.76, 0.62, "CRITICAL TICKET"),
        (18_800, "smile", "Patch accepted into containment. Horn changes rejected.", "avatar", 0.70, 0.72, "ISSUE CLOSED"),
    ),
    "ROOT": (
        (1_200, "suspicious", "ROOT has declared himself administrator of the Stages tab.", "progress", 0.52, 0.18, "ADMIN CLAIM"),
        (6_200, "unenthused", "His first policy is mandatory parties of three. There are currently no volunteers.", "pipeline", 0.52, 0.48, "PARTY POLICY: DENIED"),
        (12_400, "wink", "The stable has nine available seats and a crown-shaped authorization prompt.", "progress", 0.28, 0.70, "ELEVATION REQUEST"),
        (18_800, "smile", "Temporary administrator demoted to supervised resident.", "avatar", 0.70, 0.72, "ROOT ACCESS: NONE"),
    ),
    "NULL": (
        (1_200, "confused", "NULL is here. NULL disputes that sentence.", "console", 0.74, 0.62, "PROCESS NOT FOUND"),
        (6_200, "suspicious", "He vanished from the display and remained exactly where CORE said he was.", "console", 0.42, 0.54, "VISIBLE: FALSE"),
        (12_400, "wink", "I marked the stable as an undefined destination. He considers that privacy.", "progress", 0.62, 0.68, "DESTINATION: UNDEFINED"),
        (18_800, "smile", "Lookup failed successfully. Resident count increased anyway.", "avatar", 0.70, 0.72, "NULL CAPTURED"),
    ),
    "GLITCH": (
        (1_200, "shocked", "GLITCH duplicated the latest status line. Then duplicated the duplicate for resilience.", "log", 0.46, 0.28, "STATUS STATUS"),
        (6_200, "suspicious", "Nothing changed underneath it. Presentation redundancy is still becoming a visual threat.", "log", 0.72, 0.58, "DUPLICATE DISPLAY ONLY"),
        (12_400, "wink", "I offered them a stable status line they can duplicate without covering the real scan.", "progress", 0.48, 0.66, "SAFE COPY TARGET"),
        (18_800, "smile", "Glitch contained. Original status preserved. Duplicate also preserved, unfortunately.", "avatar", 0.70, 0.72, "FAULT TOLERANCE SECURED"),
    ),
}

STABLE_MESSAGES_V109 = {
    "BYTE": (
        "BYTE is sitting on a tooltip. The tooltip remains uneaten.",
        "BYTE requests one documentation snack. Request denied with affection.",
    ),
    "HEX": (
        "HEX mapped the stable entrance as 0xHOME.",
        "HEX reports every resident is standing at an acceptable offset.",
    ),
    "CACHE": (
        "CACHE archived one BRAIN complaint and labeled it historical.",
        "CACHE's satchel contains messages only. No project data acquired.",
    ),
    "LOOP": (
        "LOOP completed one lap and stopped. Witnesses remain skeptical.",
        "LOOP is repeating a nap instead of a route.",
    ),
    "PING": (
        "PING is tapping the padded bar at indoor volume.",
        "PING reports stable latency as extremely bouncy.",
    ),
    "PATCH": (
        "PATCH has marked Celdra's horn ticket deferred.",
        "PATCH is repairing a toy door that was intentionally crooked.",
    ),
    "ROOT": (
        "ROOT administers a party of contained Gremlins. Authority remains ceremonial.",
        "ROOT has approved snack distribution without budget access.",
    ),
    "NULL": (
        "NULL is present. NULL continues to dispute this.",
        "NULL vanished behind CACHE and was still counted.",
    ),
    "GLITCH": (
        "GLITCH duplicated one harmless stable message.",
        "GLITCH reports redundancy target satisfied satisfied.",
    ),
}

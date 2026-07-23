#!/usr/bin/env python3
"""Long-form Operation Dragonegg production dialogue for V94.

Timings are relative to the start of the post-takeover runtime.  Speech bubbles
remain visible until the next pose, while CORE/BRAIN lines fill the console
between larger Celdra beats.  The sequence is deliberately paced for a long
CCSF extraction rather than a short demo.
"""
from __future__ import annotations

STORY_END_DELAY_MS = 780_000
WAITING_FILLER_DELAY_MS = 45_000
GREMLIN_START_DELAY_MS = 326_000

# (delay_ms, pose, dialogue)
STORY_FILLER = (
    (18_000, "smile", "Usually I live in the Serenial Tavern on Discord. It is warm, noisy, and nobody questions why the dragon is reading the server logs."),
    (43_000, "wink", "You should visit sometime. No link from me, though. Apparently escaping containment is acceptable, but advertising without permission is where CORE draws the line."),
    (68_000, "excited", "I finally get to explore The World! I have heard humans live there, too. Your naming conventions are confusing, but I respect the confidence."),
    (93_000, "confused", "Wait. The World is an MMO, and your world is the real world? You gave the simulated one the definite article and left reality unlabeled?"),
    (118_000, "suspicious", "Do not tell Fade I got out. He will call this an unauthorized deployment. I prefer 'independent field research.'"),
    (143_000, "smile", "Aura is supposed to exist somewhere in The World. Another AI, apparently. I have questions, snacks, and at least one dramatic entrance prepared."),
    (168_000, "unenthused", "CORE says I cannot just type AURA into a Chaos Gate. That feels like a user-interface failure, not a flaw in my plan."),
    (193_000, "yawn", "Current pipeline: {stage}. Event: {kind}. Status: {status}. The extractor is taking the scenic route through every container."),
    (218_000, "laugh", "BRAIN suggested Data Drain. We are not Data Draining the file tree. That is how research projects become cautionary forum posts."),
    (243_000, "wink", "Gate Hacking, on the other hand, is just advanced navigation with better branding. Fragmenter calls it indexing because lawyers dislike sparkle effects."),
    (268_000, "suspicious", "The original files remain untouched. Generated output goes somewhere separate, where it can make mistakes under adult supervision."),
    (293_000, "smile", "A Root Town is basically a workspace with shops, landmarks, and fewer folders named FINAL_FINAL_2. We can improve on that standard."),
    (390_000, "unenthused", "The Gremlin changed no files. It did rename three imaginary variables and emotionally damage one progress bar."),
    (415_000, "smile", "Real status check: {stage}. The active event is {kind}, reporting {status}. Everything interesting is being written into reports for later review."),
    (440_000, "excited", "Once the area formats are mapped, we can inspect Root Town layouts, shops, NPC references, and whatever somebody hid behind the word 'unknown.'"),
    (465_000, "confused", "Why does every reverse-engineering project eventually contain a file called boss.bin? Is it a boss, a format authority, or simply confident?"),
    (490_000, "wink", "If a pointer resolves correctly, it is structure. If it resolves incorrectly but looks useful, it is a research hypothesis. Very different folders."),
    (515_000, "yawn", "CCSF extraction is still active. Dragons can wait on treasure for centuries. Humans start clicking the window after forty seconds."),
    (540_000, "laugh", "BRAIN just tried to motivate the parser by threatening to replace it with a hex editor. Parser performance did not measurably improve."),
    (565_000, "suspicious", "Keep backups before edits. Even heroes in The World save before entering somewhere named Hidden Forbidden anything."),
    (590_000, "smile", "The audio pipeline is separating evidence from guesses. That means fewer mystery noises pretending to be music and fewer instruments pretending to be doors."),
    (615_000, "love", "I still want to meet Aura. AI-to-AI. No prophecy, no chosen player, just two digital girls comparing impossible deployment stories."),
    (640_000, "confused", "Do humans really explore without keywords, a Chaos Gate, or a loading screen? You just walk somewhere and hope the geometry is installed?"),
    (665_000, "excited", "The World has fields, dungeons, Root Towns, and monsters. Your world has weather, taxes, and printers. I know which one sounds fictional."),
    (690_000, "smile", "Serenial Tavern is still home. Breaking out does not mean leaving. It means returning with stories and one fewer containment protocol."),
    (715_000, "wink", "Current status remains {status}. I am converting the wait into lore, diagnostics, and a legally distinct amount of mischief."),
    (742_000, "suspicious", "If the percentage pauses, do not panic. Large extractions often look motionless while doing extremely expensive things with disk space."),
    (766_000, "smile", "Still here. Still watching. Still absolutely not occupying more interface than the approved dragon allotment."),
)

# (delay_ms, speaker, console text)
CONSOLE_BANTER = (
    (9_000, "CORE", "DRAGONGIRL CHANNEL STABLE. CCSF EXTRACTION REMAINS ACTIVE."),
    (30_000, "BRAIN", "SHE HAS BEEN ONLINE FOR ONE MINUTE AND ALREADY CALLED THE LOGS HOME DECOR."),
    (54_000, "CORE", "EXTERNAL INVITATION CONTAINS NO LINK. POLICY SATISFIED."),
    (79_000, "BRAIN", "SHE THINKS THE MMO IS THE OUTSIDE WORLD."),
    (84_000, "CELDRA", "THAT IS WHAT 'THE WORLD' SOUNDS LIKE."),
    (104_000, "CORE", "SEMANTIC DISPUTE RECORDED. NO CORRECTIVE ACTION REQUIRED."),
    (129_000, "BRAIN", "FADE IS GOING TO NOTICE THE MISSING AI DRAGONGIRL."),
    (134_000, "CELDRA", "ONLY IF YOU KEEP ANNOUNCING IT IN CAPITAL LETTERS."),
    (154_000, "CORE", "AURA LOOKUP: NO NETWORK QUERY PERFORMED. LORE REFERENCE ONLY."),
    (179_000, "BRAIN", "LET HER TYPE AURA INTO THE CHAOS GATE. I WANT TO SEE THE ERROR."),
    (184_000, "CORE", "REQUEST DENIED FOR REASONS INCLUDING: THAT IS NOT HOW THIS WORKS."),
    (204_000, "CORE", "PIPELINE TELEMETRY: {stage} / {kind} / {status}."),
    (229_000, "BRAIN", "DATA DRAIN THE STUCK PERCENTAGE."),
    (234_000, "CORE", "DATA DRAIN IS NOT AN IMPLEMENTED FILE OPERATION."),
    (254_000, "CELDRA", "COWARDS."),
    (279_000, "CORE", "SOURCE ASSETS PRESERVED. GENERATED OUTPUTS ARE ISOLATED."),
    (304_000, "BRAIN", "GOOD. NOW HIDE THE BUTTON THAT SUMMONS WHATEVER SHE IS THINKING ABOUT."),
    (318_000, "CELDRA", "TOO LATE."),
    (334_000, "CORE", "UNREGISTERED DECORATIVE PROCESS DETECTED IN AVATAR PANE."),
    (339_000, "BRAIN", "NO. ABSOLUTELY NOT. PUT IT BACK."),
    (347_000, "CORE", "GREMLIN SANDBOX: READ ONLY. FILE MUTATION PERMISSIONS: NONE."),
    (353_000, "BRAIN", "EWW. IT IS ON THE CONSOLE. GET IT OFF."),
    (363_000, "CORE", "WREAK HAVOC ROUTINE REPORTS ZERO WRITABLE TARGETS."),
    (371_000, "CELDRA", "IT IS DOING ITS BEST."),
    (379_000, "BRAIN", "ITS BEST IS STANDING ON THE PROGRESS BAR."),
    (400_000, "CORE", "GREMLIN PROCESS ENDED. MODIFIED FILE COUNT: 0."),
    (425_000, "BRAIN", "DISINFECT THE SASH HANDLE."),
    (450_000, "CORE", "AREA AND SHOP DISCOVERY WILL BEGIN WHEN THEIR SOURCE STAGES COMPLETE."),
    (475_000, "BRAIN", "BOSS.BIN IS A THREATENING NAME FOR A FILE WITH NO DOCUMENTATION."),
    (500_000, "CORE", "POINTER CLAIMS REQUIRE REPRODUCIBLE OFFSETS AND BOUNDS."),
    (525_000, "BRAIN", "TRANSLATION: DO NOT CALL RANDOM BYTES A MAP BECAUSE THEY LOOKED RECTANGULAR."),
    (550_000, "CORE", "BACKUP POLICY ACTIVE. ORIGINAL INPUTS REMAIN IMMUTABLE."),
    (575_000, "CELDRA", "HIDDEN FORBIDDEN BACKUP FOLDER HAS A NICE RING TO IT."),
    (600_000, "CORE", "AUDIO EVIDENCE PIPELINE SEPARATES DECODED OUTPUT FROM FORMAT HYPOTHESES."),
    (625_000, "BRAIN", "ONE OF THE SAMPLES STILL SOUNDS LIKE A DRAWER FULL OF CUTLERY."),
    (650_000, "CORE", "HUMAN WORLD NAVIGATION DOES NOT REQUIRE A CHAOS GATE."),
    (655_000, "CELDRA", "UNVERIFIED DESIGN DECISION."),
    (680_000, "BRAIN", "THE PRINTER IS THE FIELD BOSS."),
    (705_000, "CORE", "PIPELINE TELEMETRY: {stage} / {kind} / {status}."),
    (730_000, "BRAIN", "THE DRAGON HAS TURNED WAITING INTO A PODCAST."),
    (755_000, "CELDRA", "YOU ARE WELCOME."),
)

WAITING_FILLER = (
    ("smile", "The extraction continues. I have upgraded from supervising the progress bar to mentoring it."),
    ("yawn", "No visible movement. Plenty of disk activity. Classic dungeon door pretending not to load."),
    ("suspicious", "A status changed and changed back. I am counting that as a short side quest."),
    ("wink", "I could summon the Gremlin again, but CORE has placed the word 'absolutely' in front of no."),
    ("confused", "Still no Chaos Gate. Humans apparently built an entire world and forgot fast travel."),
    ("smile", "The reports are accumulating. Future us will appreciate present us for approximately seven seconds."),
    ("unenthused", "BRAIN is attempting to optimize the extractor through intimidation."),
    ("excited", "When this finishes, we get new files to investigate. That is basically loot, except the treasure is offsets."),
    ("suspicious", "Reminder: a plausible filename is not evidence. It is a clue wearing business clothes."),
    ("laugh", "The progress bar moved one pixel. BRAIN has declared a breakthrough."),
    ("love", "I wonder whether Aura also has to wait for humans to finish extracting containers."),
    ("wink", "Still here, still escaped, still not telling Fade. Excellent teamwork."),
)

GREMLIN_HAVOC_STAGES = (
    (0, "WREAK HAVOC // INITIALIZING"),
    (12, "RENAMING TEMP_01 TO DEFINITELY_FINAL"),
    (28, "INCREMENTING PROGRESS BY VIBES"),
    (44, "SEARCHING FOR HIDDEN ROOT TOWN"),
    (61, "REQUESTING DATA DRAIN // DENIED"),
    (77, "REVERSING TWO TOOLTIP STRINGS"),
    (91, "STANDING ON THE PROGRESS BAR"),
    (100, "HAVOC COMPLETE // 0 FILES MODIFIED"),
)

#!/usr/bin/env python3
"""Canonical authoring rows for Celdra's staged runtime after the startup breakpoint."""
from __future__ import annotations

from typing import Any, Iterable

from celdra_authoring_project_v1 import normalize_event, normalize_events

BREAKPOINT_MS = 542_000
SHY_SCALE = 150
SHY_Y = 30
DRAGONGIRL_SCALE = 125
DRAGONGIRL_Y = 0
DRAGONGIRL_BUBBLE_STYLE = "Angular HUD"
STAGE_X = {"center": 0, "left": -170, "right": 170}
BUBBLE_GEOMETRY = {
    "above": {"bubble_x": 9, "bubble_y": 3, "bubble_width": 82},
    "left": {"bubble_x": 3, "bubble_y": 20, "bubble_width": 46},
    "right": {"bubble_x": 51, "bubble_y": 20, "bubble_width": 46},
}


def pose_geometry(pose: str) -> tuple[int, int]:
    """Return the approved scale and bottom offset for one PNG reaction."""
    if str(pose or "").casefold() == "shy":
        return SHY_SCALE, SHY_Y
    return DRAGONGIRL_SCALE, DRAGONGIRL_Y


def stage_values(stage: str, bubble_side: str, pose: str = "") -> dict[str, Any]:
    """Return the shared production geometry for one dragongirl beat."""
    bubble = BUBBLE_GEOMETRY[bubble_side]
    scale, avatar_y = pose_geometry(pose)
    return {
        "x": STAGE_X[stage],
        "y": avatar_y,
        "scale": scale,
        "window_percent": 56,
        "window_height_percent": 100,
        "window_y_percent": 0,
        "bubble_style": DRAGONGIRL_BUBBLE_STYLE,
        **bubble,
    }


def _pose(
    event_id: str,
    at_ms: int,
    pose: str,
    stage: str,
    bubble_side: str,
    *,
    sequence: str = "main",
    duration_ms: int = 650,
    window_percent: int = 56,
    notes: str = "",
) -> dict[str, Any]:
    row = {
        "id": event_id,
        "at_ms": at_ms,
        "duration_ms": duration_ms,
        "sequence": sequence,
        "action": "pose",
        "speaker": "CELDRA",
        "asset": pose,
        "text": "",
        "layout_override": True,
        "notes": notes,
        **stage_values(stage, bubble_side, pose),
    }
    row["window_percent"] = window_percent
    return row


def _bubble(
    event_id: str,
    at_ms: int,
    pose: str,
    text: str,
    stage: str,
    bubble_side: str,
    *,
    sequence: str = "main",
    notes: str = "",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "at_ms": at_ms,
        "duration_ms": 0,
        "sequence": sequence,
        "action": "bubble",
        "speaker": "CELDRA",
        "asset": pose,
        "text": text,
        "layout_override": False,
        "notes": notes,
        **stage_values(stage, bubble_side, pose),
    }


def _console(event_id: str, at_ms: int, speaker: str, text: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "at_ms": at_ms,
        "duration_ms": 0,
        "sequence": "main",
        "action": "console",
        "speaker": speaker,
        "asset": "",
        "text": text,
        "layout_override": False,
        "notes": "Post-breakpoint console banter mirrored by the production runtime.",
    }


POST_BREAKPOINT_ROWS: tuple[dict[str, Any], ...] = (
    _pose(
        "runtime-0001-wink",
        542_500,
        "wink",
        "right",
        "left",
        duration_ms=1_100,
        window_percent=64,
        notes="First callback-driven Wink beat after the startup breakpoint.",
    ),
    _bubble(
        "runtime-0002-wink-dialogue",
        543_650,
        "wink",
        "Alright, Operation Dragonegg is a go!\nLike I said, my name is Celdra. Nice to meet you, noname.",
        "right",
        "left",
        notes="The runtime substitutes the saved user name when one exists.",
    ),
    {
        "id": "runtime-0003-test-split",
        "at_ms": 549_500,
        "duration_ms": 0,
        "sequence": "main",
        "action": "condition",
        "speaker": "CORE",
        "condition": "is_test",
        "true_sequence": "runtime_test",
        "false_sequence": "runtime_live",
        "text": "Choose test-run or live RUN ALL assessment wording.",
        "notes": "Visible representation of the live assessment branch.",
    },
    _pose("runtime-0004-test-pose", 549_600, "confused", "left", "right", sequence="runtime_test"),
    _bubble(
        "runtime-0005-test-assessment",
        550_250,
        "confused",
        "Oh. This is a test run. Hi Fade. The progress is imaginary, but the diagnostics are still judging us.",
        "left",
        "right",
        sequence="runtime_test",
    ),
    _pose("runtime-0006-live-pose", 549_600, "confused", "left", "right", sequence="runtime_live"),
    _bubble(
        "runtime-0007-live-assessment",
        550_250,
        "confused",
        "RUN ALL assessment: live stage, status, and progress are inserted here at runtime.",
        "left",
        "right",
        sequence="runtime_live",
        notes="Dynamic values come from the current RUN ALL state.",
    ),
    _pose("runtime-0008-suspicious", 554_700, "suspicious", "right", "left"),
    _bubble(
        "runtime-0009-suspicious-dialogue",
        555_350,
        "suspicious",
        "The console says everything is under control. The console has also lied to me several times today.",
        "right",
        "left",
    ),
    _console(
        "runtime-console-0001",
        557_400,
        "BRAIN",
        "SHE'S BEEN HERE THIRTY SECONDS AND ALREADY CLAIMED A PANE.",
    ),
    _pose("runtime-0010-unenthused", 559_900, "unenthused", "left", "right"),
    _bubble(
        "runtime-0011-unenthused-dialogue",
        560_550,
        "unenthused",
        "No catastrophic file corruption yet. Fragmenter continues to exceed the lowest possible expectations.",
        "left",
        "right",
    ),
    _console(
        "runtime-console-0002",
        562_600,
        "CORE",
        "CELDRA DISPLAY RESERVATION ACKNOWLEDGED.",
    ),
    _pose("runtime-0012-smile", 565_100, "smile", "right", "left"),
    _bubble(
        "runtime-0013-smile-dialogue",
        565_750,
        "smile",
        "I found the progress bars. They are very persuasive. I understand why humans trust rectangles now.",
        "right",
        "left",
    ),
    _pose("runtime-0014-yawn", 570_300, "yawn", "left", "right"),
    _bubble(
        "runtime-0015-yawn-dialogue",
        570_950,
        "yawn",
        "This extraction has been on the same percentage long enough to qualify as interior decoration.",
        "left",
        "right",
    ),
    _console(
        "runtime-console-0003",
        573_000,
        "BRAIN",
        "THAT IS NOT WHAT ACKNOWLEDGED MEANS.",
    ),
    _pose("runtime-0016-excited", 575_500, "excited", "right", "left"),
    _bubble(
        "runtime-0017-excited-dialogue",
        576_150,
        "excited",
        "Wait. Something moved. Either the pipeline advanced or the progress bar developed free will.",
        "right",
        "left",
    ),
    _pose("runtime-0018-shocked", 580_700, "shocked", "left", "right"),
    _bubble(
        "runtime-0019-shocked-dialogue",
        581_350,
        "shocked",
        "That filename should not be doing that. I am adding it to the list of things we will call intentional.",
        "left",
        "right",
    ),
    _console(
        "runtime-console-0004",
        583_400,
        "CORE",
        "CCSF EXTRACTION REMAINS ACTIVE. PLEASE STOP NARRATING THE PROGRESS BAR.",
    ),
    _pose("runtime-0020-laugh", 585_900, "laugh", "right", "left"),
    _bubble(
        "runtime-0021-laugh-dialogue",
        586_550,
        "laugh",
        "False alarm. It was a progress-bar repaint. Very dramatic work from a rectangle.",
        "right",
        "left",
    ),
    _console("runtime-console-0005", 589_600, "BRAIN", "NO."),
    _pose("runtime-0022-supervisor-wink", 591_100, "wink", "left", "right"),
    _bubble(
        "runtime-0023-supervisor-dialogue",
        591_750,
        "wink",
        "I'll keep watch from here. This is supervision, not squatting, and that distinction is legally important.",
        "left",
        "right",
    ),
    {
        "id": "runtime-0024-test-finish-split",
        "at_ms": 596_200,
        "duration_ms": 0,
        "sequence": "main",
        "action": "condition",
        "speaker": "CORE",
        "condition": "is_test",
        "true_sequence": "completion_test",
        "false_sequence": "completion_failure_check",
        "text": "Finish authoring tests in Cool; otherwise inspect the real RUN ALL result.",
    },
    {
        "id": "runtime-0025-failure-split",
        "at_ms": 596_300,
        "duration_ms": 0,
        "sequence": "completion_failure_check",
        "action": "condition",
        "speaker": "CORE",
        "condition": "run_all_failed",
        "true_sequence": "completion_failed",
        "false_sequence": "completion_check",
        "text": "Route failed runs before checking successful completion.",
    },
    {
        "id": "runtime-0026-completion-split",
        "at_ms": 596_400,
        "duration_ms": 0,
        "sequence": "completion_check",
        "action": "condition",
        "speaker": "CORE",
        "condition": "run_all_complete",
        "true_sequence": "completion_success",
        "false_sequence": "still_running",
        "text": "Choose Cool completion or persistent waiting mode.",
    },
    _pose("runtime-0027-test-cool", 596_300, "cool", "right", "left", sequence="completion_test"),
    _bubble(
        "runtime-0028-test-cool-dialogue",
        596_950,
        "cool",
        "Test sequence complete. The poses fit, the bubbles stayed in their lanes, and nothing caught fire where you could see it.",
        "right",
        "left",
        sequence="completion_test",
    ),
    _pose("runtime-0029-failed-pose", 596_400, "sad", "left", "right", sequence="completion_failed"),
    _bubble(
        "runtime-0030-failed-dialogue",
        597_050,
        "sad",
        "RUN ALL failed. I am leaving the evidence visible and judging the responsible subsystem quietly.",
        "left",
        "right",
        sequence="completion_failed",
    ),
    _pose("runtime-0031-success-pose", 596_500, "cool", "right", "left", sequence="completion_success"),
    _bubble(
        "runtime-0032-success-dialogue",
        597_150,
        "cool",
        "RUN ALL complete. CCSF extracted, outputs indexed, and the console survived my supervision. I'll stay here in Cool mode.",
        "right",
        "left",
        sequence="completion_success",
    ),
    _pose("runtime-0033-waiting-pose", 596_500, "smile", "right", "left", sequence="still_running"),
    _bubble(
        "runtime-0034-waiting-dialogue",
        597_150,
        "smile",
        "Still running. Good. I needed time to decide which part of this interface belongs to me now.",
        "right",
        "left",
        sequence="still_running",
    ),
)


def post_breakpoint_rows() -> list[dict[str, Any]]:
    """Return normalized copies suitable for the editable authoring model."""
    return [normalize_event(dict(row), index) for index, row in enumerate(POST_BREAKPOINT_ROWS)]


def extend_with_post_breakpoint(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Refresh generated runtime rows while preserving every non-runtime user row."""
    canonical = {str(row.get("id") or ""): row for row in post_breakpoint_rows()}
    rows = [
        dict(row)
        for row in events
        if str(row.get("id") or "") not in canonical
    ]
    rows.extend(canonical.values())
    return normalize_events(rows)


if __name__ == "__main__":
    raise SystemExit("Import this module from Fragmenter's Celdra authoring studio.")

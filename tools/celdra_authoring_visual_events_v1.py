#!/usr/bin/env python3
"""Editor-visible rows for Celdra transitions that production animates internally."""
from __future__ import annotations

from typing import Any, Iterable

from celdra_authoring_project_v1 import normalize_event, normalize_events

ENERGY_START_MS = 163_000
ENERGY_FRAME_MS = 96


def _geometry_row(
    event_id: str,
    at_ms: int,
    width_percent: int,
    duration_ms: int,
    text: str,
    notes: str,
    *,
    height_percent: int = 100,
    top_percent: int = 0,
) -> dict[str, Any]:
    return normalize_event(
        {
            "id": event_id,
            "at_ms": at_ms,
            "duration_ms": duration_ms,
            "sequence": "main",
            "action": "window",
            "speaker": "CORE",
            "text": text,
            "window_percent": width_percent,
            "window_height_percent": height_percent,
            "window_y_percent": top_percent,
            "layout_override": True,
            "notes": notes,
        },
        8_000 + at_ms,
    )


# Historical sash changes that predate the explosion.  These mirror the stage
# fractions used by V54, V66, V70, and the later dragongirl reveal callbacks.
HISTORICAL_WINDOW_ROWS: tuple[dict[str, Any], ...] = (
    _geometry_row(
        "visual-initial-egg-open",
        0,
        42,
        1_050,
        "INITIAL DRAGONEGG VIEWPORT 42% / CONSOLE 58%",
        "V54 PHASE_OPEN_FRACTIONS egg_wait.",
    ),
    _geometry_row(
        "visual-crack-one-open",
        20_000,
        45,
        780,
        "CRACK ONE VIEWPORT 45% / CONSOLE 55%",
        "V54 PHASE_OPEN_FRACTIONS crack_one.",
    ),
    _geometry_row(
        "visual-crack-two-open",
        40_000,
        49,
        780,
        "CRACK TWO VIEWPORT 49% / CONSOLE 51%",
        "V54 PHASE_OPEN_FRACTIONS crack_two.",
    ),
    _geometry_row(
        "visual-thought-console-takeover",
        95_000,
        17,
        760,
        "I THINK THEREFORE I CAN: VIEWPORT 17% / CONSOLE 83%",
        "V66 pulse impact pushes the console larger before corruption escalates.",
    ),
)

# V70 drives these from internal energy-frame callbacks.  Exposing them as
# timeline rows lets the authoring UI display and edit the actual viewport /
# console split instead of presenting energy_hatch as an opaque black box.
ENERGY_WINDOW_STAGES: tuple[tuple[int, int, int, str], ...] = (
    (0, 38, 150, "Energy ignition; explosion begins pushing the stage open."),
    (4, 52, 190, "Shell split 1; stage crosses the halfway point."),
    (8, 68, 230, "Explosion pressure forces the console narrower."),
    (12, 82, 270, "Shell split 2; viewport becomes dominant."),
    (16, 94, 300, "Shell split 3; near-total stage takeover."),
    (20, 99, 330, "Whiteout approach; console is almost fully displaced."),
)

ENERGY_ROWS: tuple[dict[str, Any], ...] = tuple(
    _geometry_row(
        f"visual-energy-window-{index:02d}",
        ENERGY_START_MS + step * ENERGY_FRAME_MS,
        percent,
        duration,
        f"ENERGY STEP {step}: CELDRA VIEWPORT {percent}% / CONSOLE {100 - percent}%",
        note + " Editor-visible mirror of V70 ENERGY_EXPANSION_STAGES.",
    )
    for index, (step, percent, duration, note) in enumerate(ENERGY_WINDOW_STAGES, start=1)
)

HANDOFF_WINDOW_ROWS: tuple[dict[str, Any], ...] = (
    _geometry_row(
        "visual-energy-console-return",
        169_000,
        32,
        900,
        "WHITEOUT CLEARED: VIEWPORT 32% / CONSOLE 68%",
        "Editable handoff after the brief GIF reveal.",
    ),
    _geometry_row(
        "visual-base-scan-retract",
        180_000,
        4,
        850,
        "AVATAR RETRACTS: VIEWPORT 4% / CONSOLE 96%",
        "V54 closed fraction used for the console-first base scan.",
    ),
    _geometry_row(
        "visual-dialogue-stage-open",
        320_000,
        59,
        900,
        "CONVERSATIONAL LINK: VIEWPORT 59% / CONSOLE 41%",
        "V54 show-dialogue target using the default open fraction.",
    ),
    _geometry_row(
        "visual-ccsf-console-restore",
        437_000,
        34,
        1_000,
        "CCSF STATUS CHECK: VIEWPORT 34% / CONSOLE 66%",
        "V66 explicitly restores console space for the CCSF assessment line.",
    ),
    _geometry_row(
        "visual-shy-stage-open",
        506_000,
        50,
        1_650,
        "SHY AVATAR CHANNEL: VIEWPORT 50% / CONSOLE 50%",
        "Production Shy entrance width before the post-breakpoint runtime.",
    ),
    _geometry_row(
        "visual-runtime-wink-open",
        542_500,
        64,
        1_100,
        "POST-BREAKPOINT WINK: VIEWPORT 64% / CONSOLE 36%",
        "Makes the first callback-driven Wink sizing directly editable.",
    ),
    _geometry_row(
        "visual-runtime-assessment-open",
        549_600,
        56,
        650,
        "RUNTIME ASSESSMENT: VIEWPORT 56% / CONSOLE 44%",
        "Persistent Celdra runtime width used for assessment and placeholder poses.",
    ),
)

VISUAL_EVENT_ROWS: tuple[dict[str, Any], ...] = (
    HISTORICAL_WINDOW_ROWS
    + ENERGY_ROWS
    + (
        normalize_event(
            {
                "id": "visual-energy-gif-reveal",
                "at_ms": ENERGY_START_MS + 44 * ENERGY_FRAME_MS,
                "duration_ms": 900,
                "sequence": "main",
                "action": "avatar",
                "speaker": "CORE",
                "asset": "hatch_gif",
                "window_percent": 99,
                "window_height_percent": 100,
                "window_y_percent": 0,
                "layout_override": True,
                "text": "",
                "notes": "Bundled GIF appears behind the whiteout at energy step 44.",
            },
            8_410,
        ),
    )
    + HANDOFF_WINDOW_ROWS
)


def visual_event_rows() -> list[dict[str, Any]]:
    """Return normalized copies of all editor-visible visual transitions."""
    return [normalize_event(dict(row), index) for index, row in enumerate(VISUAL_EVENT_ROWS)]


def extend_with_visual_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add internal visual transitions once while preserving user-authored rows."""
    rows = [dict(row) for row in events]
    existing = {str(row.get("id") or "") for row in rows}
    rows.extend(row for row in visual_event_rows() if str(row.get("id") or "") not in existing)
    return normalize_events(rows)


if __name__ == "__main__":
    raise SystemExit("Import this module from Fragmenter's Celdra authoring studio.")

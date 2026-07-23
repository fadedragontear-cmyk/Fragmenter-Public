#!/usr/bin/env python3
"""Higher-detail chibi Celdra hatchling and young-dragon frames."""
from __future__ import annotations

from celdra_evolution_pixel_v1 import (
    CELDRA_BLUE_PALETTE,
    CRACK_ONE_LOOP,
    CRACK_TWO_LOOP,
    EGG_LOOP,
    EYES_LOOP,
    HATCH_SEQUENCE as V1_HATCH_SEQUENCE,
    PHASE_OPEN_FRACTIONS as V1_OPEN_FRACTIONS,
    _dragon,
    frame_resolution,
)
from celdra_pixel_pet_v1 import PixelFrame


def _paint(grid: list[list[str]], x: int, y: int, value: str) -> None:
    if 0 <= y < len(grid) and 0 <= x < len(grid[y]):
        grid[y][x] = value


def _decorate(frame: PixelFrame, *, mood: str = "idle") -> PixelFrame:
    """Add detail that only becomes possible at the larger logical resolution."""
    grid = [list(row) for row in frame.rows]
    size = len(grid)
    if not grid or size < 32:
        return frame

    def point(nx: float, ny: float, value: str) -> None:
        _paint(grid, round(nx * (size - 1)), round(ny * (size - 1)), value)

    # Three-point blue crest and brighter inner ear fins.
    for nx, ny, value in (
        (0.44, 0.09, "l"),
        (0.50, 0.05, "c"),
        (0.56, 0.09, "l"),
        (0.18, 0.28, "c"),
        (0.82, 0.28, "c"),
    ):
        point(nx, ny, value)

    # Eye sparkle, nostrils, cheek clusters and tiny lower fangs.
    for nx, ny, value in (
        (0.37, 0.29, "c"),
        (0.63, 0.29, "c"),
        (0.46, 0.40, "k"),
        (0.54, 0.40, "k"),
        (0.27, 0.42, "p"),
        (0.30, 0.43, "p"),
        (0.70, 0.43, "p"),
        (0.73, 0.42, "p"),
        (0.45, 0.47, "w"),
        (0.55, 0.47, "w"),
    ):
        point(nx, ny, value)

    # Belly scale diamonds and wing-membrane highlights.
    for nx, ny in ((0.50, 0.62), (0.46, 0.69), (0.54, 0.69), (0.50, 0.76)):
        point(nx, ny, "c")
    for nx, ny in (
        (0.13, 0.47),
        (0.16, 0.54),
        (0.19, 0.61),
        (0.87, 0.47),
        (0.84, 0.54),
        (0.81, 0.61),
    ):
        point(nx, ny, "l")

    # A cyan tail-tip accent makes the silhouette more readable.
    for nx, ny in ((0.88, 0.70), (0.91, 0.66), (0.93, 0.70)):
        point(nx, ny, "c")

    if mood == "smirk":
        point(0.63, 0.30, "k")
        point(0.58, 0.46, "r")
    elif mood == "talk":
        point(0.50, 0.48, "r")
        point(0.50, 0.50, "p")
    elif mood == "excited":
        for nx, ny in ((0.33, 0.22), (0.67, 0.22), (0.24, 0.34), (0.76, 0.34)):
            point(nx, ny, "y")

    return PixelFrame(frame.name, tuple("".join(row) for row in grid), frame.duration_ms)


def _cute(
    name: str,
    *,
    size: int = 36,
    pose: str = "idle",
    wing_open: bool = False,
    blink: bool = False,
    mood: str = "idle",
    duration_ms: int = 520,
) -> PixelFrame:
    base = _dragon(
        name,
        size=size,
        pose=pose,
        wing_open=wing_open,
        blink=blink,
        duration_ms=duration_ms,
    )
    return _decorate(base, mood=mood)


# The shell remains deliberately low-resolution; Celdra gains visible detail as
# the creature itself appears.
HATCH_SEQUENCE = (
    *V1_HATCH_SEQUENCE[:3],
    _cute("cute_hatchling_curled", pose="curled", blink=True, duration_ms=760),
    _cute("cute_hatchling_peek", blink=True, duration_ms=260),
    _cute("cute_hatchling_first_look", duration_ms=820),
    _cute("cute_hatchling_excited", wing_open=True, mood="excited", duration_ms=620),
    _cute("cute_hatchling_settle", duration_ms=720),
)

HATCHLING_IDLE = (
    _cute("cute_idle_a", duration_ms=720),
    _cute("cute_blink", blink=True, duration_ms=170),
    _cute("cute_idle_b", duration_ms=820),
    _cute("cute_wing_flex", wing_open=True, duration_ms=420),
    _cute("cute_head_tilt", pose="thinking", duration_ms=560),
)

HATCHLING_TALK = (
    _cute("cute_talk_a", pose="talk", mood="talk", duration_ms=300),
    _cute("cute_talk_b", pose="talk", wing_open=True, mood="talk", duration_ms=320),
    _cute("cute_talk_rest", duration_ms=360),
)

HATCHLING_THINK = (
    _cute("cute_thinking", pose="thinking", duration_ms=720),
    _cute("cute_thinking_blink", pose="thinking", blink=True, duration_ms=180),
)

HATCHLING_SMIRK = (
    _cute("cute_smirk", pose="smirk", mood="smirk", duration_ms=620),
    _cute("cute_smirk_wings", pose="smirk", wing_open=True, mood="smirk", duration_ms=420),
)

BASE_CLAIM_LOOP = (
    _cute("base_claim_smirk", pose="smirk", mood="smirk", duration_ms=520),
    _cute("base_claim_talk", pose="talk", mood="talk", duration_ms=320),
    _cute("base_claim_wings", pose="smirk", wing_open=True, mood="excited", duration_ms=430),
    _cute("base_claim_proud", mood="excited", duration_ms=620),
)

YOUNG_DRAGON_IDLE = (
    _cute("young_dragon_a", size=48, wing_open=True, mood="excited", duration_ms=760),
    _cute("young_dragon_blink", size=48, wing_open=True, blink=True, duration_ms=180),
    _cute("young_dragon_b", size=48, duration_ms=860),
)

EVOLUTION_PHASES = {
    "egg_wait": EGG_LOOP,
    "crack_one": CRACK_ONE_LOOP,
    "crack_two": CRACK_TWO_LOOP,
    "eyes": EYES_LOOP,
    "hatch_open": HATCH_SEQUENCE,
    "baby_rise": HATCH_SEQUENCE[3:],
    "idle": HATCHLING_IDLE,
    "baby_idle": HATCHLING_IDLE,
    "talk": HATCHLING_TALK,
    "thinking": HATCHLING_THINK,
    "smirk": HATCHLING_SMIRK,
    "error": HATCHLING_THINK + HATCHLING_SMIRK,
    "base_claim": BASE_CLAIM_LOOP,
    "young_dragon": YOUNG_DRAGON_IDLE,
}

PHASE_OPEN_FRACTIONS = dict(V1_OPEN_FRACTIONS)
PHASE_OPEN_FRACTIONS.update(
    {
        "hatch_open": 0.62,
        "baby_rise": 0.65,
        "idle": 0.65,
        "baby_idle": 0.65,
        "talk": 0.65,
        "thinking": 0.65,
        "smirk": 0.65,
        "error": 0.65,
        "base_claim": 0.66,
        "young_dragon": 0.71,
        "dragongirl": 0.73,
    }
)


if __name__ == "__main__":
    raise SystemExit("Celdra evolution frames are consumed by Fragmenter's GUI.")

#!/usr/bin/env python3
"""Reworked chibi Celdra hatchling with stable body animation.

The hatchling deliberately remains a slightly awkward baby dragon, but its
silhouette is clearer: large head, explicit horns, compact torso, stable belly,
small wings, and a readable tail.  Normal idle blinking is sparse; a separate
compact loop blinks more frequently when the viewport is squeezed narrow.
"""
from __future__ import annotations

from collections.abc import Iterable

from celdra_evolution_pixel_v1 import (
    CELDRA_BLUE_PALETTE,
    CRACK_ONE_LOOP,
    CRACK_TWO_LOOP,
    EGG_LOOP,
    EYES_LOOP,
    PHASE_OPEN_FRACTIONS as V1_OPEN_FRACTIONS,
    _blank,
    _ellipse,
    _frame,
    _line,
    _set,
    frame_resolution,
)
from celdra_evolution_pixel_v2 import HATCH_SEQUENCE as V2_HATCH_SEQUENCE
from celdra_pixel_pet_v1 import PixelFrame


def _triangle(
    grid: list[list[str]],
    points: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    fill: str,
    outline: str = "k",
) -> None:
    (x1, y1), (x2, y2), (x3, y3) = points
    minimum_y = max(0, min(y1, y2, y3))
    maximum_y = min(len(grid) - 1, max(y1, y2, y3))
    denominator = ((y2 - y3) * (x1 - x3)) + ((x3 - x2) * (y1 - y3))
    if denominator == 0:
        return
    for y in range(minimum_y, maximum_y + 1):
        for x in range(max(0, min(x1, x2, x3)), min(len(grid[0]) - 1, max(x1, x2, x3)) + 1):
            a = (((y2 - y3) * (x - x3)) + ((x3 - x2) * (y - y3))) / denominator
            b = (((y3 - y1) * (x - x3)) + ((x1 - x3) * (y - y3))) / denominator
            c = 1.0 - a - b
            if a >= 0 and b >= 0 and c >= 0:
                _set(grid, x, y, fill)
    _line(grid, points + (points[0],), outline)


def _dragon_frame(
    name: str,
    *,
    size: int = 40,
    blink: bool = False,
    look: int = 0,
    wing_open: bool = False,
    mouth: str = "closed",
    mood: str = "idle",
    tail_up: bool = False,
    duration_ms: int = 700,
) -> PixelFrame:
    size = max(40, int(size))
    grid = _blank(size, size)
    scale = size / 40.0

    def p(value: float) -> int:
        return round(value * scale)

    # Wings and tail sit behind a body that never changes shape between idle
    # frames.  This eliminates the previous stomach wobble/morph artifact.
    if wing_open:
        _ellipse(grid, p(8), p(24), p(7), p(9), "d", outline="k")
        _ellipse(grid, p(32), p(24), p(7), p(9), "d", outline="k")
        _line(grid, ((p(4), p(19)), (p(9), p(23)), (p(3), p(27)), (p(8), p(29))), "l")
        _line(grid, ((p(36), p(19)), (p(31), p(23)), (p(37), p(27)), (p(32), p(29))), "l")
    else:
        _ellipse(grid, p(10), p(25), p(4), p(7), "d", outline="k")
        _ellipse(grid, p(30), p(25), p(4), p(7), "d", outline="k")
        _line(grid, ((p(8), p(22)), (p(11), p(25)), (p(8), p(28))), "l")
        _line(grid, ((p(32), p(22)), (p(29), p(25)), (p(32), p(28))), "l")

    tail_points = (
        (p(26), p(30)),
        (p(31), p(32)),
        (p(35), p(31 if tail_up else 34)),
        (p(37), p(27 if tail_up else 31)),
        (p(35), p(25 if tail_up else 29)),
    )
    _line(grid, tail_points, "g")
    _line(grid, tuple((x, y + p(1)) for x, y in tail_points[:-1]), "m")
    _set(grid, *tail_points[-1], "c")

    # Compact pear-shaped body with an invariant belly.
    _ellipse(grid, p(20), p(28), p(8), p(10), "g", outline="k")
    _ellipse(grid, p(20), p(29), p(4), p(8), "l", outline="m")
    for x, y in ((20, 24), (18, 28), (22, 28), (20, 33)):
        _set(grid, p(x), p(y), "c")

    # Oversized baby-dragon head and muzzle.
    _ellipse(grid, p(20), p(13), p(12), p(10), "g", outline="k")
    _ellipse(grid, p(20), p(17), p(7), p(4), "m", outline="d")

    # Actual triangular horns rather than isolated yellow pixels.
    _triangle(grid, ((p(12), p(7)), (p(9), p(0)), (p(16), p(5))), "y")
    _triangle(grid, ((p(28), p(7)), (p(31), p(0)), (p(24), p(5))), "y")
    _triangle(grid, ((p(16), p(5)), (p(20), p(1)), (p(24), p(5))), "l", outline="d")

    # Ear fins.
    _triangle(grid, ((p(9), p(11)), (p(3), p(8)), (p(6), p(16))), "l", outline="d")
    _triangle(grid, ((p(31), p(11)), (p(37), p(8)), (p(34), p(16))), "l", outline="d")

    # Large eyes.  Looking left/right moves only pupils, not the face.
    eye_y = p(12)
    if blink:
        _line(grid, ((p(12), eye_y), (p(16), eye_y)), "k")
        _line(grid, ((p(24), eye_y), (p(28), eye_y)), "k")
    else:
        for eye_x in (14, 26):
            _ellipse(grid, p(eye_x), eye_y, p(3), p(4), "w", outline="k")
            pupil_x = p(eye_x + max(-1, min(1, look)))
            _ellipse(grid, pupil_x, p(13), p(1.2), p(2), "d", outline="k")
            _set(grid, pupil_x - p(1), p(11), "c")

    # Nose, cheeks, and tiny fangs.
    _set(grid, p(18), p(17), "k")
    _set(grid, p(22), p(17), "k")
    for x, y in ((8, 17), (10, 18), (30, 18), (32, 17)):
        _set(grid, p(x), p(y), "p")

    if mouth == "talk":
        _ellipse(grid, p(20), p(20), p(3), p(2), "r", outline="k")
        _set(grid, p(20), p(21), "p")
    elif mouth == "smirk":
        _line(grid, ((p(17), p(20)), (p(20), p(21)), (p(24), p(19))), "k")
    else:
        _line(grid, ((p(18), p(20)), (p(20), p(21)), (p(22), p(20))), "k")
    _set(grid, p(17), p(20), "w")
    _set(grid, p(23), p(20), "w")

    # Stubby feet and claws.
    for foot_x in (15, 25):
        _ellipse(grid, p(foot_x), p(37), p(5), p(2), "m", outline="k")
        _set(grid, p(foot_x - 2), p(38), "w")
        _set(grid, p(foot_x), p(39), "w")
        _set(grid, p(foot_x + 2), p(38), "w")

    if mood == "excited":
        for x, y in ((6, 5), (34, 5), (4, 20), (36, 20)):
            _set(grid, p(x), p(y), "c")
    elif mood == "confused":
        _set(grid, p(34), p(3), "w")
        _set(grid, p(36), p(1), "c")

    return _frame(name, grid, duration_ms)


# The shell remains deliberately coarse, then jumps to a substantially larger
# baby-dragon canvas when Celdra emerges.
HATCH_SEQUENCE = (
    *V2_HATCH_SEQUENCE[:3],
    _dragon_frame("v3_hatchling_curled", blink=True, duration_ms=820),
    _dragon_frame("v3_hatchling_peek", blink=True, look=-1, duration_ms=260),
    _dragon_frame("v3_hatchling_first_look", look=1, duration_ms=920),
    _dragon_frame("v3_hatchling_horns", look=0, duration_ms=820),
    _dragon_frame("v3_hatchling_wing_test", wing_open=True, mood="excited", duration_ms=680),
    _dragon_frame("v3_hatchling_settle", duration_ms=950),
)

# One blink in roughly seven seconds during normal use.
HATCHLING_IDLE = (
    _dragon_frame("v3_idle_a", duration_ms=2100),
    _dragon_frame("v3_idle_look_left", look=-1, tail_up=True, duration_ms=1300),
    _dragon_frame("v3_idle_blink", blink=True, duration_ms=145),
    _dragon_frame("v3_idle_look_right", look=1, duration_ms=1500),
    _dragon_frame("v3_idle_wing_twitch", wing_open=True, duration_ms=430),
    _dragon_frame("v3_idle_rest", duration_ms=1900),
)

# When the pane is narrow, Celdra looks cramped and blinks nervously more often.
HATCHLING_COMPACT_IDLE = (
    _dragon_frame("v3_compact_left", look=-1, duration_ms=720),
    _dragon_frame("v3_compact_blink_a", blink=True, duration_ms=135),
    _dragon_frame("v3_compact_right", look=1, duration_ms=680),
    _dragon_frame("v3_compact_blink_b", blink=True, duration_ms=135),
    _dragon_frame("v3_compact_rest", tail_up=True, duration_ms=760),
)

HATCHLING_TALK = (
    _dragon_frame("v3_talk_a", mouth="talk", duration_ms=340),
    _dragon_frame("v3_talk_rest", duration_ms=420),
    _dragon_frame("v3_talk_b", mouth="talk", wing_open=True, duration_ms=360),
    _dragon_frame("v3_talk_finish", duration_ms=520),
)

HATCHLING_THINK = (
    _dragon_frame("v3_think_left", look=-1, mood="confused", duration_ms=900),
    _dragon_frame("v3_think_right", look=1, mood="confused", duration_ms=900),
)

HATCHLING_SMIRK = (
    _dragon_frame("v3_smirk", mouth="smirk", look=1, tail_up=True, duration_ms=900),
    _dragon_frame("v3_smirk_wings", mouth="smirk", wing_open=True, duration_ms=620),
)

BASE_CLAIM_LOOP = (
    _dragon_frame("v3_base_smirk", mouth="smirk", look=1, duration_ms=650),
    _dragon_frame("v3_base_talk", mouth="talk", duration_ms=380),
    _dragon_frame("v3_base_proud", wing_open=True, tail_up=True, mood="excited", duration_ms=720),
)

YOUNG_DRAGON_IDLE = (
    _dragon_frame("v3_young_a", size=56, wing_open=True, look=-1, duration_ms=1500),
    _dragon_frame("v3_young_blink", size=56, wing_open=True, blink=True, duration_ms=150),
    _dragon_frame("v3_young_b", size=56, look=1, tail_up=True, duration_ms=1700),
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
    "compact_idle": HATCHLING_COMPACT_IDLE,
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
        "hatch_open": 0.64,
        "baby_rise": 0.67,
        "idle": 0.67,
        "baby_idle": 0.67,
        "compact_idle": 0.34,
        "talk": 0.67,
        "thinking": 0.67,
        "smirk": 0.67,
        "error": 0.67,
        "base_claim": 0.68,
        "young_dragon": 0.73,
        "dragongirl": 0.75,
    }
)


def all_frames() -> Iterable[PixelFrame]:
    seen: set[int] = set()
    for sequence in EVOLUTION_PHASES.values():
        identity = id(sequence)
        if identity in seen:
            continue
        seen.add(identity)
        yield from sequence


if __name__ == "__main__":
    raise SystemExit("Celdra evolution frames are consumed by Fragmenter's GUI.")

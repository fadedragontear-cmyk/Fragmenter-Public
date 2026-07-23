#!/usr/bin/env python3
"""Concept-approved baby Celdra pixel animation set.

The hatchling is based on the approved blue chibi baby-dragon concept: a large
rounded head, short muzzle, oversized violet eyes, curved tan horns, blue crest,
pink-purple wing membranes, cream belly, tiny forearms, large feet, and a curled
tail.  The egg remains deliberately small and low-detail, then the logical art
and viewport grow together as Celdra hatches.
"""
from __future__ import annotations

from celdra_evolution_pixel_v1 import _blank, _ellipse, _frame, _line, _set, frame_resolution
from celdra_pixel_pet_v1 import PixelFrame


CELDRA_BLUE_PALETTE = {
    ".": "",
    "k": "#071426",
    "n": "#152a46",
    "d": "#164f83",
    "g": "#2583bf",
    "m": "#45a9db",
    "l": "#79cff1",
    "c": "#c7f2ff",
    "w": "#f4fbff",
    "v": "#8054c8",
    "q": "#b678df",
    "p": "#f09ccc",
    "r": "#df5e8e",
    "y": "#efbd70",
    "o": "#ffdaa0",
    "b": "#f2e5b8",
    "s": "#9ce2dc",
}


def _triangle(
    grid: list[list[str]],
    points: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    fill: str,
    outline: str = "k",
) -> None:
    (x1, y1), (x2, y2), (x3, y3) = points
    minimum_x = max(0, min(x1, x2, x3))
    maximum_x = min(len(grid[0]) - 1, max(x1, x2, x3))
    minimum_y = max(0, min(y1, y2, y3))
    maximum_y = min(len(grid) - 1, max(y1, y2, y3))
    denominator = ((y2 - y3) * (x1 - x3)) + ((x3 - x2) * (y1 - y3))
    if denominator == 0:
        return
    for y in range(minimum_y, maximum_y + 1):
        for x in range(minimum_x, maximum_x + 1):
            a = (((y2 - y3) * (x - x3)) + ((x3 - x2) * (y - y3))) / denominator
            b = (((y3 - y1) * (x - x3)) + ((x1 - x3) * (y - y3))) / denominator
            c = 1.0 - a - b
            if a >= 0 and b >= 0 and c >= 0:
                _set(grid, x, y, fill)
    _line(grid, points + (points[0],), outline)


def _egg(
    name: str,
    *,
    offset_x: int = 0,
    offset_y: int = 0,
    squash: int = 0,
    glow: bool = False,
    crack: int = 0,
    eyes: bool = False,
    blink: bool = False,
    bump: int = 0,
    shine: int = 0,
    duration_ms: int = 420,
) -> PixelFrame:
    size = 26
    grid = _blank(size, size)
    cx = 12.5 + offset_x
    cy = 13.0 + offset_y
    rx = 7.0 + squash * 0.5
    ry = 9.5 - squash * 0.65

    _ellipse(grid, 12.5, 23.2, 7.4, 1.25, "n")
    if glow:
        _ellipse(grid, cx, cy, rx + 1.4, ry + 1.0, "c")
    _ellipse(grid, cx, cy, rx, ry, "l", outline="k")
    _ellipse(grid, cx - 1.2, cy - 1.0, rx - 1.5, ry - 1.7, "m")
    _ellipse(grid, cx - 1.8, cy - 2.2, max(1.0, rx - 3.5), max(1.0, ry - 4.0), "l")

    for x, y, value in (
        (9, 7, "g"), (12, 6, "d"), (15, 7, "g"),
        (8, 12, "g"), (16, 12, "d"), (10, 17, "d"), (14, 18, "g"),
    ):
        _set(grid, x + offset_x, y + offset_y, value)
    highlight_x = 8 + max(0, min(3, shine))
    _set(grid, highlight_x + offset_x, 8 + offset_y, "w")
    _set(grid, highlight_x + 1 + offset_x, 9 + offset_y, "c")

    if bump:
        _set(grid, 6 + offset_x, 14 + offset_y - bump, "c")
        _set(grid, 18 + offset_x, 13 + offset_y + bump, "c")

    if crack >= 1:
        _line(
            grid,
            (
                (13 + offset_x, 4 + offset_y),
                (12 + offset_x, 6 + offset_y),
                (13 + offset_x, 8 + offset_y),
                (11 + offset_x, 10 + offset_y),
                (13 + offset_x, 12 + offset_y),
            ),
            "k",
        )
    if crack >= 2:
        _line(
            grid,
            (
                (13 + offset_x, 12 + offset_y),
                (15 + offset_x, 14 + offset_y),
                (13 + offset_x, 16 + offset_y),
                (14 + offset_x, 18 + offset_y),
            ),
            "k",
        )
        _line(
            grid,
            (
                (12 + offset_x, 10 + offset_y),
                (9 + offset_x, 11 + offset_y),
                (7 + offset_x, 13 + offset_y),
            ),
            "k",
        )
    if crack >= 3:
        _line(
            grid,
            (
                (14 + offset_x, 14 + offset_y),
                (17 + offset_x, 12 + offset_y),
                (19 + offset_x, 10 + offset_y),
            ),
            "k",
        )
        _line(grid, ((10 + offset_x, 16 + offset_y), (8 + offset_x, 18 + offset_y)), "k")

    if eyes:
        if blink:
            _line(grid, ((9 + offset_x, 13 + offset_y), (11 + offset_x, 13 + offset_y)), "k")
            _line(grid, ((15 + offset_x, 13 + offset_y), (17 + offset_x, 13 + offset_y)), "k")
        else:
            for eye_x in (10, 16):
                _ellipse(grid, eye_x + offset_x, 13 + offset_y, 1.35, 1.7, "v", outline="k")
                _set(grid, eye_x + offset_x, 12 + offset_y, "w")

    return _frame(name, grid, duration_ms)


def _shell_open(name: str, opening: int, duration_ms: int = 420) -> PixelFrame:
    size = 30
    grid = _blank(size, size)
    _ellipse(grid, 15, 26, 10, 1.4, "n")
    gap = max(1, opening)
    left_cx = 10.5 - gap * 0.7
    right_cx = 19.5 + gap * 0.7
    _ellipse(grid, left_cx, 19, 6.3, 6.7, "m", outline="k")
    _ellipse(grid, right_cx, 19, 6.3, 6.7, "m", outline="k")
    for y in range(8, 23):
        for x in range(13 - gap, 17 + gap):
            _set(grid, x, y, ".")
    _line(grid, ((5, 19), (8, 17), (10, 19), (12, 17)), "c")
    _line(grid, ((18, 17), (20, 19), (22, 17), (25, 19)), "c")
    return _frame(name, grid, duration_ms)


def _dragon_frame(
    name: str,
    *,
    size: int = 52,
    blink: bool = False,
    look: int = 0,
    mouth: str = "smile",
    wing_open: bool = False,
    tail_pose: int = 0,
    head_tilt: int = 0,
    bob: int = 0,
    search: bool = False,
    squished: bool = False,
    distressed: bool = False,
    sleepy: bool = False,
    y_offset: int = 0,
    duration_ms: int = 700,
) -> PixelFrame:
    size = max(52, int(size))
    grid = _blank(size, size)
    scale = size / 52.0

    def p(value: float) -> int:
        return round(value * scale)

    center = 26 + head_tilt
    body_center = 27 + (head_tilt // 2)
    y_shift = bob + y_offset
    head_rx = 13 if squished else 16
    body_rx = 8 if squished else 10

    _ellipse(grid, p(26), p(49), p(15), p(1.5), "n")

    tail = (
        (p(34), p(38 + y_shift)),
        (p(40), p(41 + y_shift)),
        (p(45), p(39 + tail_pose + y_shift)),
        (p(47), p(34 + tail_pose + y_shift)),
        (p(44), p(31 + tail_pose + y_shift)),
        (p(41), p(34 + tail_pose + y_shift)),
    )
    _line(grid, tail, "d")
    _line(grid, tuple((x, y + p(1)) for x, y in tail[:-1]), "g")
    for x, y in tail[1:-1:2]:
        _set(grid, x, y, "v")

    if squished:
        _ellipse(grid, p(15), p(31 + y_shift), p(3.5), p(8), "d", outline="k")
        _ellipse(grid, p(37), p(31 + y_shift), p(3.5), p(8), "d", outline="k")
        _line(grid, ((p(13), p(27 + y_shift)), (p(17), p(31 + y_shift)), (p(14), p(36 + y_shift))), "q")
        _line(grid, ((p(39), p(27 + y_shift)), (p(35), p(31 + y_shift)), (p(38), p(36 + y_shift))), "q")
    elif wing_open:
        _ellipse(grid, p(12), p(31 + y_shift), p(9), p(10), "d", outline="k")
        _ellipse(grid, p(40), p(31 + y_shift), p(9), p(10), "d", outline="k")
        _triangle(grid, ((p(3), p(25 + y_shift)), (p(13), p(28 + y_shift)), (p(7), p(38 + y_shift))), "q", "d")
        _triangle(grid, ((p(49), p(25 + y_shift)), (p(39), p(28 + y_shift)), (p(45), p(38 + y_shift))), "q", "d")
    else:
        _ellipse(grid, p(14), p(32 + y_shift), p(5), p(8), "d", outline="k")
        _ellipse(grid, p(38), p(32 + y_shift), p(5), p(8), "d", outline="k")
        _triangle(grid, ((p(10), p(28 + y_shift)), (p(15), p(31 + y_shift)), (p(11), p(37 + y_shift))), "q", "d")
        _triangle(grid, ((p(42), p(28 + y_shift)), (p(37), p(31 + y_shift)), (p(41), p(37 + y_shift))), "q", "d")

    _ellipse(grid, p(body_center), p(35 + y_shift), p(body_rx), p(12), "g", outline="k")
    _ellipse(grid, p(body_center), p(36 + y_shift), p(5), p(10), "b", outline="o")
    for yy in (30, 34, 38, 42):
        _line(grid, ((p(body_center - 4), p(yy + y_shift)), (p(body_center + 4), p(yy + y_shift))), "o")

    _ellipse(grid, p(center), p(15 + y_shift), p(head_rx), p(13), "m", outline="k")
    _ellipse(grid, p(center), p(20 + y_shift), p(8 if not squished else 7), p(4), "l", outline="d")

    horn_y = 5 + y_shift
    left_horn = ((p(center - 10), p(8 + y_shift)), (p(center - 14), p(-1 + y_shift)), (p(center - 6), p(5 + y_shift)))
    right_horn = ((p(center + 10), p(8 + y_shift)), (p(center + 14), p(-1 + y_shift)), (p(center + 6), p(5 + y_shift)))
    _triangle(grid, left_horn, "y")
    _triangle(grid, right_horn, "y")
    _line(grid, ((p(center - 12), p(horn_y)), (p(center - 8), p(horn_y + 1))), "o")
    _line(grid, ((p(center + 12), p(horn_y)), (p(center + 8), p(horn_y + 1))), "o")

    _triangle(grid, ((p(center - 4), p(5 + y_shift)), (p(center), p(-1 + y_shift)), (p(center + 3), p(5 + y_shift))), "d", "n")
    _triangle(grid, ((p(center - 1), p(8 + y_shift)), (p(center + 3), p(2 + y_shift)), (p(center + 6), p(8 + y_shift))), "g", "n")
    _triangle(grid, ((p(center - head_rx + 2), p(14 + y_shift)), (p(center - head_rx - 7), p(10 + y_shift)), (p(center - head_rx - 3), p(22 + y_shift))), "q", "d")
    _triangle(grid, ((p(center + head_rx - 2), p(14 + y_shift)), (p(center + head_rx + 7), p(10 + y_shift)), (p(center + head_rx + 3), p(22 + y_shift))), "q", "d")

    eye_y = 15 + y_shift
    if sleepy:
        _line(grid, ((p(center - 10), p(eye_y)), (p(center - 4), p(eye_y + 1))), "k")
        _line(grid, ((p(center + 4), p(eye_y + 1)), (p(center + 10), p(eye_y))), "k")
    elif blink:
        _line(grid, ((p(center - 10), p(eye_y)), (p(center - 4), p(eye_y))), "k")
        _line(grid, ((p(center + 4), p(eye_y)), (p(center + 10), p(eye_y))), "k")
    else:
        for eye_x in (center - 7, center + 7):
            _ellipse(grid, p(eye_x), p(eye_y), p(4), p(5), "w", outline="k")
            pupil_offset = max(-2, min(2, look))
            _ellipse(grid, p(eye_x + pupil_offset), p(eye_y + 1), p(2.5), p(3.5), "v", outline="n")
            _set(grid, p(eye_x + pupil_offset - 1), p(eye_y - 1), "w")
            _set(grid, p(eye_x + pupil_offset + 1), p(eye_y + 2), "p")

    _set(grid, p(center - 2), p(20 + y_shift), "n")
    _set(grid, p(center + 2), p(20 + y_shift), "n")
    _set(grid, p(center - 12), p(21 + y_shift), "p")
    _set(grid, p(center + 12), p(21 + y_shift), "p")
    if mouth == "talk":
        _ellipse(grid, p(center), p(24 + y_shift), p(4), p(2.5), "r", outline="k")
        _set(grid, p(center), p(25 + y_shift), "p")
    elif mouth == "frown":
        _line(grid, ((p(center - 3), p(25 + y_shift)), (p(center), p(23 + y_shift)), (p(center + 3), p(25 + y_shift))), "k")
    elif mouth == "smirk":
        _line(grid, ((p(center - 4), p(23 + y_shift)), (p(center), p(25 + y_shift)), (p(center + 5), p(22 + y_shift))), "k")
    else:
        _line(grid, ((p(center - 4), p(23 + y_shift)), (p(center), p(25 + y_shift)), (p(center + 4), p(23 + y_shift))), "k")
    _set(grid, p(center - 4), p(23 + y_shift), "w")
    _set(grid, p(center + 4), p(23 + y_shift), "w")

    if search:
        _ellipse(grid, p(center - 9), p(30 + y_shift), p(3), p(5), "m", outline="k")
        _line(grid, ((p(center + 4), p(28 + y_shift)), (p(center + 10), p(25 + y_shift)), (p(center + 13), p(27 + y_shift))), "m")
        _line(grid, ((p(center + 7), p(26 + y_shift)), (p(center + 12), p(26 + y_shift))), "c")
    elif squished:
        _ellipse(grid, p(center - 5), p(31 + y_shift), p(3), p(6), "m", outline="k")
        _ellipse(grid, p(center + 5), p(31 + y_shift), p(3), p(6), "m", outline="k")
        _set(grid, p(center - 5), p(27 + y_shift), "c")
        _set(grid, p(center + 5), p(27 + y_shift), "c")
    else:
        _ellipse(grid, p(center - 8), p(32 + y_shift), p(3.5), p(6), "m", outline="k")
        _ellipse(grid, p(center + 8), p(32 + y_shift), p(3.5), p(6), "m", outline="k")
        _set(grid, p(center - 8), p(36 + y_shift), "w")
        _set(grid, p(center + 8), p(36 + y_shift), "w")

    for foot_x in (center - 10, center + 10):
        _ellipse(grid, p(foot_x), p(45 + y_shift), p(7), p(4), "m", outline="k")
        _ellipse(grid, p(foot_x), p(46 + y_shift), p(3), p(2), "p")
        for claw_x in (-3, 0, 3):
            _set(grid, p(foot_x + claw_x), p(48 + y_shift), "w")

    if distressed:
        _set(grid, p(center + head_rx + 2), p(8 + y_shift), "c")
        _set(grid, p(center + head_rx + 3), p(9 + y_shift), "c")
        _line(grid, ((p(3), p(18 + y_shift)), (p(1), p(18 + y_shift))), "r")
        _line(grid, ((p(49), p(18 + y_shift)), (p(51), p(18 + y_shift))), "r")

    return _frame(name, grid, duration_ms)


EGG_LOOP = (
    _egg("v4_egg_rest_a", shine=0, duration_ms=720),
    _egg("v4_egg_breathe", squash=1, shine=1, duration_ms=260),
    _egg("v4_egg_rest_b", shine=2, duration_ms=620),
    _egg("v4_egg_bump_left", offset_x=-1, bump=1, glow=True, shine=3, duration_ms=210),
    _egg("v4_egg_center", shine=2, duration_ms=360),
    _egg("v4_egg_bump_right", offset_x=1, bump=-1, glow=True, shine=1, duration_ms=210),
    _egg("v4_egg_settle", shine=0, duration_ms=820),
)

CRACK_ONE_LOOP = (
    _egg("v4_crack_one_rest", crack=1, shine=1, duration_ms=700),
    _egg("v4_crack_one_glow", crack=1, glow=True, bump=1, shine=2, duration_ms=300),
    _egg("v4_crack_one_wobble", crack=1, offset_x=-1, squash=1, shine=3, duration_ms=220),
    _egg("v4_crack_one_return", crack=1, shine=1, duration_ms=520),
)

CRACK_TWO_LOOP = (
    _egg("v4_crack_two_rest", crack=2, shine=1, duration_ms=620),
    _egg("v4_crack_two_glow", crack=2, glow=True, bump=-1, shine=2, duration_ms=280),
    _egg("v4_crack_three_jump", crack=3, offset_y=-1, glow=True, shine=3, duration_ms=210),
    _egg("v4_crack_three_squash", crack=3, squash=1, shine=0, duration_ms=240),
    _egg("v4_crack_three_hold", crack=3, glow=True, shine=1, duration_ms=620),
)

EYES_LOOP = (
    _egg("v4_eyes_open", crack=3, eyes=True, glow=True, duration_ms=760),
    _egg("v4_eyes_blink", crack=3, eyes=True, blink=True, duration_ms=150),
    _egg("v4_eyes_left", crack=3, eyes=True, offset_x=-1, duration_ms=360),
    _egg("v4_eyes_right", crack=3, eyes=True, offset_x=1, duration_ms=360),
    _egg("v4_eyes_ready", crack=3, eyes=True, glow=True, squash=1, duration_ms=520),
)

HATCH_SEQUENCE = (
    _shell_open("v4_shell_split_a", 1, 420),
    _shell_open("v4_shell_split_b", 2, 420),
    _shell_open("v4_shell_split_c", 3, 520),
    _dragon_frame("v4_hatch_head_peek", blink=True, squished=True, y_offset=12, duration_ms=520),
    _dragon_frame("v4_hatch_rise_a", look=-1, y_offset=8, duration_ms=520),
    _dragon_frame("v4_hatch_rise_b", look=1, y_offset=4, duration_ms=520),
    _dragon_frame("v4_hatch_first_smile", mouth="smile", y_offset=1, duration_ms=760),
    _dragon_frame("v4_hatch_wings", wing_open=True, mouth="talk", duration_ms=620),
    _dragon_frame("v4_hatch_settle", tail_pose=-1, duration_ms=900),
)

HATCHLING_IDLE = (
    _dragon_frame("v4_idle_rest", duration_ms=1800),
    _dragon_frame("v4_idle_tail", tail_pose=-2, look=-1, duration_ms=900),
    _dragon_frame("v4_idle_blink", blink=True, duration_ms=145),
    _dragon_frame("v4_idle_look", look=1, duration_ms=1100),
    _dragon_frame("v4_idle_wing_twitch", wing_open=True, duration_ms=420),
    _dragon_frame("v4_idle_smile", mouth="smile", duration_ms=1600),
)

HATCHLING_SEARCH = (
    _dragon_frame("v4_search_left", look=-2, search=True, head_tilt=-1, duration_ms=720),
    _dragon_frame("v4_search_blink", blink=True, search=True, duration_ms=150),
    _dragon_frame("v4_search_right", look=2, search=True, head_tilt=1, duration_ms=720),
    _dragon_frame("v4_search_sniff", look=0, search=True, mouth="talk", duration_ms=420),
    _dragon_frame("v4_search_wait", look=-1, search=True, tail_pose=-2, duration_ms=650),
)

HATCHLING_SQUISHED = (
    _dragon_frame("v4_squished_start", squished=True, distressed=True, look=-2, duration_ms=520),
    _dragon_frame("v4_squished_blink", squished=True, distressed=True, blink=True, duration_ms=130),
    _dragon_frame("v4_squished_push", squished=True, distressed=True, look=2, mouth="frown", duration_ms=520),
    _dragon_frame("v4_squished_nervous", squished=True, distressed=True, blink=True, tail_pose=-2, duration_ms=140),
    _dragon_frame("v4_squished_hold", squished=True, distressed=True, mouth="frown", duration_ms=620),
)

HATCHLING_BASE_CLAIM = (
    _dragon_frame("v4_base_smirk", mouth="smirk", look=1, tail_pose=-2, duration_ms=620),
    _dragon_frame("v4_base_talk", mouth="talk", search=True, duration_ms=360),
    _dragon_frame("v4_base_wings", mouth="smirk", wing_open=True, duration_ms=520),
    _dragon_frame("v4_base_proud", mouth="smile", wing_open=True, tail_pose=-3, duration_ms=720),
)

HATCHLING_BASE_FAILED = (
    _dragon_frame("v4_base_failed_look", look=-1, mouth="frown", duration_ms=720),
    _dragon_frame("v4_base_failed_blink", blink=True, mouth="frown", duration_ms=180),
    _dragon_frame("v4_base_failed_slump", sleepy=True, mouth="frown", bob=2, duration_ms=920),
)

HATCHLING_TALK = (
    _dragon_frame("v4_talk_a", mouth="talk", duration_ms=320),
    _dragon_frame("v4_talk_rest", duration_ms=360),
    _dragon_frame("v4_talk_b", mouth="talk", wing_open=True, duration_ms=340),
)

HATCHLING_THINK = (
    _dragon_frame("v4_think_left", look=-2, search=True, duration_ms=760),
    _dragon_frame("v4_think_right", look=2, search=True, duration_ms=760),
)

HATCHLING_SMIRK = (
    _dragon_frame("v4_smirk", mouth="smirk", look=1, tail_pose=-2, duration_ms=800),
    _dragon_frame("v4_smirk_wings", mouth="smirk", wing_open=True, duration_ms=520),
)

YOUNG_DRAGON_IDLE = (
    _dragon_frame("v4_young_a", size=68, wing_open=True, look=-1, duration_ms=1400),
    _dragon_frame("v4_young_blink", size=68, wing_open=True, blink=True, duration_ms=150),
    _dragon_frame("v4_young_b", size=68, look=1, tail_pose=-3, duration_ms=1600),
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
    "base_search": HATCHLING_SEARCH,
    "searching": HATCHLING_SEARCH,
    "compact_idle": HATCHLING_SQUISHED,
    "squished": HATCHLING_SQUISHED,
    "distressed": HATCHLING_SQUISHED,
    "base_claim": HATCHLING_BASE_CLAIM,
    "base_failed": HATCHLING_BASE_FAILED,
    "talk": HATCHLING_TALK,
    "thinking": HATCHLING_THINK,
    "smirk": HATCHLING_SMIRK,
    "error": HATCHLING_BASE_FAILED,
    "young_dragon": YOUNG_DRAGON_IDLE,
}

PHASE_OPEN_FRACTIONS = {
    "egg_wait": 0.20,
    "crack_one": 0.24,
    "crack_two": 0.28,
    "eyes": 0.33,
    "hatch_open": 0.58,
    "baby_rise": 0.67,
    "idle": 0.69,
    "baby_idle": 0.69,
    "base_search": 0.34,
    "searching": 0.34,
    "compact_idle": 0.30,
    "squished": 0.30,
    "distressed": 0.30,
    "base_claim": 0.39,
    "base_failed": 0.35,
    "talk": 0.64,
    "thinking": 0.62,
    "smirk": 0.64,
    "error": 0.35,
    "young_dragon": 0.74,
    "dragongirl": 0.60,
}


if __name__ == "__main__":
    raise SystemExit("Celdra evolution frames are consumed by Fragmenter's GUI.")

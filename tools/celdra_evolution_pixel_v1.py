#!/usr/bin/env python3
"""Generated pixel-art stages for Celdra's egg-to-dragon presentation.

The early presentation intentionally starts at a low logical resolution and gains
pixel detail as Celdra forms.  Frames are generated from simple drawing
primitives so they remain bundled, transparent, editable, and independent of
external artwork.
"""
from __future__ import annotations

from collections.abc import Iterable

from celdra_pixel_pet_v1 import PixelFrame


CELDRA_BLUE_PALETTE = {
    ".": "",
    "k": "#071426",
    "d": "#15385f",
    "g": "#2e72ad",
    "m": "#4f98cf",
    "l": "#83c7f1",
    "w": "#e2f5ff",
    "c": "#b9e8ff",
    "p": "#f19ab5",
    "r": "#e55f7d",
    "y": "#ead77d",
    "s": "#9b7ec8",
}


def _blank(width: int, height: int) -> list[list[str]]:
    return [["." for _ in range(width)] for _ in range(height)]


def _set(grid: list[list[str]], x: int, y: int, value: str) -> None:
    if 0 <= y < len(grid) and 0 <= x < len(grid[y]):
        grid[y][x] = value


def _ellipse(
    grid: list[list[str]],
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    fill: str,
    *,
    outline: str | None = None,
) -> None:
    if rx <= 0 or ry <= 0:
        return
    left = max(0, int(cx - rx - 1))
    right = min(len(grid[0]) - 1, int(cx + rx + 1))
    top = max(0, int(cy - ry - 1))
    bottom = min(len(grid) - 1, int(cy + ry + 1))
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            distance = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
            if distance <= 1.0:
                value = fill
                if outline and distance >= 0.72:
                    value = outline
                _set(grid, x, y, value)


def _line(
    grid: list[list[str]],
    points: Iterable[tuple[int, int]],
    value: str,
) -> None:
    for x, y in points:
        _set(grid, x, y, value)


def _frame(name: str, grid: list[list[str]], duration_ms: int) -> PixelFrame:
    return PixelFrame(
        name=name,
        rows=tuple("".join(row) for row in grid),
        duration_ms=max(1, int(duration_ms)),
    )


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
    duration_ms: int = 320,
) -> PixelFrame:
    width = height = 20
    grid = _blank(width, height)
    cx = 9.5 + offset_x
    cy = 10.0 + offset_y
    rx = 5.6 + squash * 0.45
    ry = 7.7 - squash * 0.55

    if glow:
        _ellipse(grid, cx, cy, rx + 1.15, ry + 0.95, "c")
    _ellipse(grid, cx, cy, rx, ry, "l", outline="w")

    # Soft blue shell markings keep the egg visually tied to Celdra.
    for x, y in ((7, 7), (12, 6), (6, 11), (13, 12), (9, 15)):
        _set(grid, x + offset_x, y + offset_y, "m")
    for x, y in ((8, 7), (12, 7), (7, 12), (12, 13)):
        _set(grid, x + offset_x, y + offset_y, "g")

    if crack >= 1:
        _line(
            grid,
            (
                (10 + offset_x, 4 + offset_y),
                (9 + offset_x, 5 + offset_y),
                (10 + offset_x, 6 + offset_y),
                (9 + offset_x, 7 + offset_y),
                (10 + offset_x, 8 + offset_y),
            ),
            "k",
        )
    if crack >= 2:
        _line(
            grid,
            (
                (10 + offset_x, 8 + offset_y),
                (11 + offset_x, 9 + offset_y),
                (10 + offset_x, 10 + offset_y),
                (11 + offset_x, 11 + offset_y),
                (10 + offset_x, 12 + offset_y),
                (9 + offset_x, 13 + offset_y),
            ),
            "k",
        )
        _line(
            grid,
            (
                (10 + offset_x, 9 + offset_y),
                (8 + offset_x, 10 + offset_y),
                (7 + offset_x, 11 + offset_y),
            ),
            "k",
        )
    if crack >= 3:
        _line(
            grid,
            (
                (11 + offset_x, 10 + offset_y),
                (13 + offset_x, 9 + offset_y),
                (14 + offset_x, 8 + offset_y),
            ),
            "k",
        )
    if eyes:
        eye = "k" if blink else "w"
        _set(grid, 8 + offset_x, 10 + offset_y, eye)
        _set(grid, 12 + offset_x, 10 + offset_y, eye)
        if not blink:
            _set(grid, 8 + offset_x, 11 + offset_y, "k")
            _set(grid, 12 + offset_x, 11 + offset_y, "k")

    return _frame(name, grid, duration_ms)


def _shell_open(name: str, openness: int, duration_ms: int = 420) -> PixelFrame:
    width = height = 24
    grid = _blank(width, height)
    gap = max(1, openness)
    left_cx = 8.4 - gap * 0.5
    right_cx = 15.6 + gap * 0.5
    for cx in (left_cx, right_cx):
        _ellipse(grid, cx, 14.2, 5.2, 5.8, "l", outline="w")
    # Clear the center and top so the shell reads as two halves.
    for y in range(4, 15):
        for x in range(10 - gap, 14 + gap):
            _set(grid, x, y, ".")
    _line(grid, ((5, 15), (6, 14), (7, 15), (8, 14), (9, 15)), "k")
    _line(grid, ((15, 15), (16, 14), (17, 15), (18, 14), (19, 15)), "k")
    return _frame(name, grid, duration_ms)


def _dragon(
    name: str,
    *,
    size: int = 24,
    pose: str = "idle",
    wing_open: bool = False,
    blink: bool = False,
    duration_ms: int = 420,
) -> PixelFrame:
    size = max(24, int(size))
    grid = _blank(size, size)
    scale = size / 24.0

    def px(value: float) -> float:
        return value * scale

    # Wings first so the large head/body remain readable in front.
    if wing_open:
        _ellipse(grid, px(5.2), px(13.2), px(4.3), px(5.4), "d", outline="k")
        _ellipse(grid, px(18.8), px(13.2), px(4.3), px(5.4), "d", outline="k")
        _line(
            grid,
            ((int(px(3)), int(px(10))), (int(px(5)), int(px(12))), (int(px(2)), int(px(14)))),
            "l",
        )
        _line(
            grid,
            ((int(px(21)), int(px(10))), (int(px(19)), int(px(12))), (int(px(22)), int(px(14)))),
            "l",
        )
    else:
        _ellipse(grid, px(6.5), px(14.0), px(2.7), px(4.0), "d", outline="k")
        _ellipse(grid, px(17.5), px(14.0), px(2.7), px(4.0), "d", outline="k")

    # Tail curves out from the body.
    tail_y = 18 if pose != "curled" else 19
    _line(
        grid,
        tuple((int(px(x)), int(px(y))) for x, y in ((15, 17), (18, 18), (20, tail_y), (21, tail_y - 2), (20, tail_y - 3))),
        "g",
    )
    _set(grid, int(px(21)), int(px(tail_y - 2)), "l")

    # Chibi proportions: oversized head, compact torso, short limbs.
    body_cy = 16.0 if pose != "curled" else 17.0
    _ellipse(grid, px(12), px(body_cy), px(4.4), px(5.3), "g", outline="k")
    _ellipse(grid, px(12), px(8.0), px(6.1), px(5.1), "g", outline="k")
    _ellipse(grid, px(12), px(9.3), px(3.4), px(2.4), "m")

    # Horns and ear fins.
    for x, direction in ((8, -1), (16, 1)):
        _line(
            grid,
            (
                (int(px(x)), int(px(3))),
                (int(px(x + direction)), int(px(1.5))),
                (int(px(x + direction * 2)), int(px(3.5))),
            ),
            "y",
        )
    _line(grid, ((int(px(6)), int(px(7))), (int(px(4)), int(px(6))), (int(px(5)), int(px(9)))), "l")
    _line(grid, ((int(px(18)), int(px(7))), (int(px(20)), int(px(6))), (int(px(19)), int(px(9)))), "l")

    # Face: large eyes, small muzzle and optional blush.
    if blink:
        _line(grid, ((int(px(8.5)), int(px(8))), (int(px(9.5)), int(px(8)))), "k")
        _line(grid, ((int(px(14.5)), int(px(8))), (int(px(15.5)), int(px(8)))), "k")
    else:
        for eye_x in (9, 15):
            _ellipse(grid, px(eye_x), px(7.7), px(1.25), px(1.55), "w", outline="k")
            _set(grid, int(px(eye_x)), int(px(8)), "d")
            _set(grid, int(px(eye_x - 0.35)), int(px(7.2)), "c")
    _set(grid, int(px(12)), int(px(9.5)), "k")
    if pose == "talk":
        _set(grid, int(px(12)), int(px(11)), "r")
        _set(grid, int(px(11)), int(px(11)), "k")
        _set(grid, int(px(13)), int(px(11)), "k")
    elif pose == "smirk":
        _line(grid, ((int(px(11)), int(px(11))), (int(px(12)), int(px(11))), (int(px(13)), int(px(10.5)))), "k")
    else:
        _line(grid, ((int(px(11.5)), int(px(11))), (int(px(12.5)), int(px(11)))), "k")
    _set(grid, int(px(7)), int(px(10)), "p")
    _set(grid, int(px(17)), int(px(10)), "p")

    # Belly, feet, tiny claws.
    _ellipse(grid, px(12), px(16.5), px(2.2), px(3.2), "l")
    for foot_x in (9, 15):
        _ellipse(grid, px(foot_x), px(21), px(2.3), px(1.3), "m", outline="k")
        _set(grid, int(px(foot_x - 1)), int(px(22)), "w")
        _set(grid, int(px(foot_x + 1)), int(px(22)), "w")

    if pose == "thinking":
        _ellipse(grid, px(20.5), px(4.2), px(1.0), px(1.0), "w", outline="c")
        _ellipse(grid, px(22.2), px(2.4), px(0.65), px(0.65), "w", outline="c")
    if pose == "curled":
        _ellipse(grid, px(12), px(17.5), px(6.0), px(3.6), "d", outline="k")

    return _frame(name, grid, duration_ms)


EGG_LOOP = (
    _egg("egg_rest_a", duration_ms=560),
    _egg("egg_glow_a", glow=True, duration_ms=420),
    _egg("egg_rest_b", duration_ms=520),
    _egg("egg_lean_left", offset_x=-1, offset_y=1, duration_ms=220),
    _egg("egg_center_a", duration_ms=260),
    _egg("egg_lean_right", offset_x=1, offset_y=1, duration_ms=220),
    _egg("egg_center_b", duration_ms=520),
    _egg("egg_squash", squash=1, offset_y=1, duration_ms=180),
    _egg("egg_bounce", offset_y=-1, glow=True, duration_ms=230),
    _egg("egg_settle", duration_ms=620),
)

CRACK_ONE_LOOP = (
    _egg("crack_one_rest", crack=1, duration_ms=520),
    _egg("crack_one_glow", crack=1, glow=True, duration_ms=320),
    _egg("crack_one_left", crack=1, offset_x=-1, duration_ms=190),
    _egg("crack_one_right", crack=1, offset_x=1, duration_ms=190),
    _egg("crack_one_squash", crack=1, squash=1, duration_ms=220),
)

CRACK_TWO_LOOP = (
    _egg("crack_two_rest", crack=2, duration_ms=430),
    _egg("crack_two_glow", crack=2, glow=True, duration_ms=300),
    _egg("crack_two_bounce", crack=2, offset_y=-1, duration_ms=180),
    _egg("crack_three", crack=3, glow=True, duration_ms=380),
    _egg("crack_three_squash", crack=3, squash=1, duration_ms=210),
)

EYES_LOOP = (
    _egg("eyes_open", crack=3, eyes=True, glow=True, duration_ms=650),
    _egg("eyes_blink", crack=3, eyes=True, blink=True, duration_ms=170),
    _egg("eyes_open_again", crack=3, eyes=True, duration_ms=520),
    _egg("eyes_wiggle_left", crack=3, eyes=True, offset_x=-1, duration_ms=210),
    _egg("eyes_wiggle_right", crack=3, eyes=True, offset_x=1, duration_ms=210),
)

HATCH_SEQUENCE = (
    _shell_open("shell_split_a", 1, 360),
    _shell_open("shell_split_b", 2, 360),
    _shell_open("shell_split_c", 3, 420),
    _dragon("hatchling_curled", pose="curled", duration_ms=650),
    _dragon("hatchling_peek", pose="idle", blink=True, duration_ms=260),
    _dragon("hatchling_first_look", pose="idle", duration_ms=720),
    _dragon("hatchling_wings", pose="idle", wing_open=True, duration_ms=560),
    _dragon("hatchling_settle", pose="idle", duration_ms=650),
)

HATCHLING_IDLE = (
    _dragon("hatchling_idle_a", pose="idle", duration_ms=620),
    _dragon("hatchling_blink", pose="idle", blink=True, duration_ms=180),
    _dragon("hatchling_idle_b", pose="idle", duration_ms=720),
    _dragon("hatchling_wing_flex", pose="idle", wing_open=True, duration_ms=360),
)

HATCHLING_TALK = (
    _dragon("hatchling_talk", pose="talk", duration_ms=300),
    _dragon("hatchling_idle_after_talk", pose="idle", duration_ms=340),
)

HATCHLING_THINK = (_dragon("hatchling_thinking", pose="thinking", duration_ms=620),)
HATCHLING_SMIRK = (_dragon("hatchling_smirk", pose="smirk", duration_ms=620),)

# A 32x32 bridge stage proves that the logical artwork resolution and visible
# canvas can grow before the classified dragongirl artwork takes over.
YOUNG_DRAGON_IDLE = (
    _dragon("young_dragon_idle_a", size=32, pose="idle", wing_open=True, duration_ms=680),
    _dragon("young_dragon_blink", size=32, pose="idle", wing_open=True, blink=True, duration_ms=180),
    _dragon("young_dragon_idle_b", size=32, pose="idle", duration_ms=760),
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
    "young_dragon": YOUNG_DRAGON_IDLE,
}

PHASE_OPEN_FRACTIONS = {
    "egg_wait": 0.42,
    "crack_one": 0.45,
    "crack_two": 0.49,
    "eyes": 0.52,
    "hatch_open": 0.57,
    "baby_rise": 0.59,
    "idle": 0.59,
    "baby_idle": 0.59,
    "talk": 0.59,
    "thinking": 0.59,
    "smirk": 0.59,
    "error": 0.59,
    "young_dragon": 0.66,
    "dragongirl": 0.70,
}


def frame_resolution(frame: PixelFrame) -> tuple[int, int]:
    return max((len(row) for row in frame.rows), default=0), len(frame.rows)


if __name__ == "__main__":
    raise SystemExit("Celdra evolution frames are consumed by Fragmenter's GUI.")

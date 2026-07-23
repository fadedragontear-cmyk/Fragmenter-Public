#!/usr/bin/env python3
"""Refined vector artwork for Celdra's nine Gremlin hatchlings.

The drawings are presentation-only Tk canvas primitives. Each design has a
separate silhouette, expression, accessory, prop, and motion signature while
remaining recognizably descended from the retired baby-dragon hatchling.
"""
from __future__ import annotations

import math
from typing import Any


def _mix(first: str, second: str, amount: float) -> str:
    def rgb(value: str) -> tuple[int, int, int]:
        text = str(value).lstrip("#")
        if len(text) != 6:
            return 0, 0, 0
        return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]

    a = max(0.0, min(1.0, float(amount)))
    left = rgb(first)
    right = rgb(second)
    values = [round(left[index] + (right[index] - left[index]) * a) for index in range(3)]
    return "#" + "".join(f"{value:02x}" for value in values)


def _safe_call(canvas: Any, method: str, *args: Any, **kwargs: Any) -> Any:
    try:
        return getattr(canvas, method)(*args, **kwargs)
    except Exception:
        return None


def design_dimensions(personality: dict[str, Any], *, compact: bool = False) -> tuple[int, int]:
    shape = str(personality.get("shape") or "round")
    base = {
        "fat": (104, 86),
        "tall": (78, 112),
        "petite": (82, 90),
        "springy": (86, 106),
        "wide": (104, 88),
        "broad": (102, 94),
        "small": (76, 80),
        "jagged": (92, 96),
    }.get(shape, (92, 94))
    if compact:
        return max(58, round(base[0] * 0.76)), max(62, round(base[1] * 0.76))
    return base


def draw_gremlin(
    canvas: Any,
    personality: dict[str, Any],
    *,
    width: int | None = None,
    height: int | None = None,
    phase: int = 0,
    mood: str = "idle",
    compact: bool = False,
    show_name: bool = True,
) -> None:
    """Draw one animated Gremlin with a character-specific visual language."""
    _safe_call(canvas, "delete", "v101_gremlin")
    try:
        current_width = int(width or canvas.winfo_width() or 1)
        current_height = int(height or canvas.winfo_height() or 1)
    except Exception:
        current_width, current_height = width or 92, height or 94
    current_width = max(48, current_width)
    current_height = max(54, current_height)

    name = str(personality.get("name") or "GREMLIN").upper()
    accent = str(personality.get("accent") or "#64d8ff")
    dark = str(personality.get("dark") or "#07506a")
    light = str(personality.get("light") or "#bdf4ff")
    shape = str(personality.get("shape") or "round")
    accessory = str(personality.get("accessory") or "none")
    outline = "#05080d"
    white = "#f6fbff"
    eye_dark = "#121019"
    name_height = 14 if show_name else 2
    floor = current_height - name_height - 3

    bob_strength = 0 if mood == "attention" else 1 if mood == "idle" else 3
    bob = round(math.sin((phase + len(name)) * 0.55) * bob_strength)
    blink = mood != "attention" and phase % (17 + len(name) % 5) in {0, 1}
    look = 0 if mood == "attention" else round(math.sin(phase * 0.31 + len(name)) * 2)

    dimensions = {
        "fat": (0.37, 0.25, 0.31, 0.22),
        "tall": (0.27, 0.34, 0.27, 0.25),
        "petite": (0.29, 0.26, 0.29, 0.23),
        "springy": (0.28, 0.30, 0.28, 0.24),
        "wide": (0.36, 0.25, 0.33, 0.22),
        "broad": (0.35, 0.29, 0.33, 0.24),
        "small": (0.27, 0.24, 0.27, 0.22),
        "jagged": (0.31, 0.28, 0.30, 0.23),
    }.get(shape, (0.31, 0.28, 0.30, 0.23))
    body_rx, body_ry, head_rx, head_ry = dimensions
    cx = current_width * 0.50
    body_cy = floor - current_height * 0.27 + bob
    head_cy = body_cy - current_height * 0.24
    body_w = current_width * body_rx
    body_h = current_height * body_ry
    head_w = current_width * head_rx
    head_h = current_height * head_ry

    tag = "v101_gremlin"
    _safe_call(canvas, "create_oval", cx - body_w * 1.1, floor - 5, cx + body_w * 1.1, floor + 1,
               fill="#05070b", outline="", stipple="gray50", tags=tag)

    # Character-specific tail silhouettes.
    tail_points = {
        "LOOP": (cx + body_w * 0.72, body_cy + 2, cx + body_w * 1.35, body_cy + 9,
                 cx + body_w * 1.26, body_cy - 10, cx + body_w * 0.84, body_cy - 7),
        "GLITCH": (cx + body_w * 0.72, body_cy + 3, cx + body_w * 1.36, body_cy - 4,
                   cx + body_w * 1.02, body_cy + 13, cx + body_w * 1.46, body_cy + 9),
    }.get(name, (cx + body_w * 0.72, body_cy + 3, cx + body_w * 1.34, body_cy + 10,
                 cx + body_w * 1.20, body_cy - 7, cx + body_w * 0.84, body_cy - 5))
    _safe_call(canvas, "create_line", *tail_points, fill=dark, width=max(3, round(current_width / 24)),
               smooth=name != "GLITCH", capstyle="round", tags=tag)
    _safe_call(canvas, "create_line", *tail_points, fill=accent, width=max(1, round(current_width / 50)),
               smooth=name != "GLITCH", tags=tag)

    # Wings are layered and differ in posture by temperament.
    wing_raise = 7 if mood == "chaos" else 2
    left_wing = (
        cx - body_w * 0.62, body_cy - body_h * 0.32,
        cx - body_w * 1.20, body_cy - body_h * 0.94 - wing_raise,
        cx - body_w * 1.05, body_cy + body_h * 0.12,
    )
    right_wing = (
        cx + body_w * 0.62, body_cy - body_h * 0.32,
        cx + body_w * 1.20, body_cy - body_h * 0.94 - wing_raise,
        cx + body_w * 1.05, body_cy + body_h * 0.12,
    )
    for points in (left_wing, right_wing):
        _safe_call(canvas, "create_polygon", *points, fill=_mix(dark, accent, 0.38), outline=outline,
                   width=2, smooth=True, tags=tag)
        inset = tuple(value * 0.985 + (cx if index % 2 == 0 else body_cy) * 0.015 for index, value in enumerate(points))
        _safe_call(canvas, "create_line", *inset, fill=light, width=1, smooth=True, tags=tag)

    # Body, belly and layered highlights.
    _safe_call(canvas, "create_oval", cx - body_w, body_cy - body_h, cx + body_w, body_cy + body_h,
               fill=dark, outline=outline, width=2, tags=tag)
    _safe_call(canvas, "create_oval", cx - body_w * 0.86, body_cy - body_h * 0.88,
               cx + body_w * 0.86, body_cy + body_h * 0.88,
               fill=accent, outline="", tags=tag)
    _safe_call(canvas, "create_oval", cx - body_w * 0.44, body_cy - body_h * 0.30,
               cx + body_w * 0.44, body_cy + body_h * 0.84,
               fill=_mix(light, "#fff4d3", 0.45), outline=_mix(dark, outline, 0.45), width=1, tags=tag)
    _safe_call(canvas, "create_arc", cx - body_w * 0.72, body_cy - body_h * 0.76,
               cx + body_w * 0.20, body_cy + body_h * 0.42,
               start=62, extent=98, style="arc", outline=light, width=2, tags=tag)

    # Feet and hands communicate shape better than the old uniformly scaled pixels.
    foot_y = floor - 8
    foot_spread = body_w * (0.62 if shape != "tall" else 0.48)
    for direction in (-1, 1):
        fx = cx + direction * foot_spread
        _safe_call(canvas, "create_oval", fx - current_width * 0.12, foot_y - current_height * 0.07,
                   fx + current_width * 0.12, foot_y + current_height * 0.055,
                   fill=_mix(accent, dark, 0.22), outline=outline, width=2, tags=tag)
        claw_color = _mix(light, "#fff4d3", 0.65)
        for claw in (-1, 0, 1):
            x = fx + claw * current_width * 0.038
            _safe_call(canvas, "create_polygon", x - 2, foot_y + 1, x + 2, foot_y + 1, x, foot_y + 6,
                       fill=claw_color, outline=outline, tags=tag)
    arm_y = body_cy - body_h * 0.12
    arm_drop = 5 if mood == "attention" else round(math.sin(phase * 0.63) * 3)
    for direction in (-1, 1):
        shoulder = cx + direction * body_w * 0.72
        hand = cx + direction * body_w * 1.05
        _safe_call(canvas, "create_line", shoulder, arm_y, hand, arm_y + 8 + direction * arm_drop,
                   fill=dark, width=max(3, round(current_width / 25)), capstyle="round", tags=tag)
        _safe_call(canvas, "create_oval", hand - 3, arm_y + 5 + direction * arm_drop,
                   hand + 3, arm_y + 11 + direction * arm_drop, fill=light, outline=outline, tags=tag)

    # Head and muzzle.
    _safe_call(canvas, "create_oval", cx - head_w, head_cy - head_h, cx + head_w, head_cy + head_h,
               fill=dark, outline=outline, width=2, tags=tag)
    _safe_call(canvas, "create_oval", cx - head_w * 0.89, head_cy - head_h * 0.87,
               cx + head_w * 0.89, head_cy + head_h * 0.88,
               fill=accent, outline="", tags=tag)
    _safe_call(canvas, "create_arc", cx - head_w * 0.73, head_cy - head_h * 0.72,
               cx + head_w * 0.04, head_cy + head_h * 0.08,
               start=70, extent=100, style="arc", outline=light, width=2, tags=tag)
    muzzle_y = head_cy + head_h * 0.35
    _safe_call(canvas, "create_oval", cx - head_w * 0.50, muzzle_y - head_h * 0.26,
               cx + head_w * 0.50, muzzle_y + head_h * 0.33,
               fill=_mix(light, "#fff4dd", 0.42), outline=_mix(dark, outline, 0.45), width=1, tags=tag)
    _safe_call(canvas, "create_oval", cx - 3, muzzle_y - 2, cx + 3, muzzle_y + 3,
               fill=outline, outline="", tags=tag)

    # Horns/ears. GLITCH deliberately offsets one; NULL uses ghostly pale horns.
    horn_color = light if name == "NULL" else "#f2d8a6"
    horn_offset = 5 if name == "GLITCH" else 0
    _safe_call(canvas, "create_polygon", cx - head_w * 0.62, head_cy - head_h * 0.62,
               cx - head_w * 0.92, head_cy - head_h * 1.20,
               cx - head_w * 0.30, head_cy - head_h * 0.88,
               fill=horn_color, outline=outline, width=2, tags=tag)
    _safe_call(canvas, "create_polygon", cx + head_w * 0.62, head_cy - head_h * 0.62,
               cx + head_w * 0.94 + horn_offset, head_cy - head_h * 1.12,
               cx + head_w * 0.30, head_cy - head_h * 0.88,
               fill=horn_color, outline=outline, width=2, tags=tag)

    eye_y = head_cy - head_h * 0.12
    eye_gap = head_w * 0.42
    if blink:
        for direction in (-1, 1):
            ex = cx + direction * eye_gap
            _safe_call(canvas, "create_arc", ex - 6, eye_y - 2, ex + 6, eye_y + 4,
                       start=200, extent=140, style="arc", outline=eye_dark, width=2, tags=tag)
    else:
        for direction in (-1, 1):
            ex = cx + direction * eye_gap
            eye_fill = "#ecf7ff" if name != "NULL" else "#ffffff"
            _safe_call(canvas, "create_oval", ex - 6, eye_y - 7, ex + 6, eye_y + 7,
                       fill=eye_fill, outline=outline, width=1, tags=tag)
            pupil_x = ex + look
            pupil_y = eye_y + (1 if mood == "attention" else 0)
            pupil_color = _mix(accent, "#341b52", 0.58)
            _safe_call(canvas, "create_oval", pupil_x - 3, pupil_y - 4, pupil_x + 3, pupil_y + 4,
                       fill=pupil_color, outline=eye_dark, tags=tag)
            _safe_call(canvas, "create_oval", pupil_x - 1, pupil_y - 3, pupil_x + 1, pupil_y - 1,
                       fill=white, outline="", tags=tag)

    mouth_y = muzzle_y + head_h * 0.20
    if mood == "attention":
        _safe_call(canvas, "create_line", cx - 5, mouth_y, cx + 5, mouth_y, fill=eye_dark, width=2, tags=tag)
    elif mood == "chaos":
        _safe_call(canvas, "create_arc", cx - 8, mouth_y - 4, cx + 8, mouth_y + 7,
                   start=190, extent=160, style="arc", outline=eye_dark, width=2, tags=tag)
    else:
        _safe_call(canvas, "create_arc", cx - 7, mouth_y - 4, cx + 7, mouth_y + 4,
                   start=200, extent=140, style="arc", outline=eye_dark, width=2, tags=tag)

    # Distinct character props and surface details.
    if name == "BYTE":
        card_x, card_y = cx + body_w * 0.74, body_cy - body_h * 0.88
        _safe_call(canvas, "create_polygon", card_x, card_y, card_x + 24, card_y, card_x + 24, card_y + 14,
                   card_x + 15, card_y + 14, card_x + 11, card_y + 19, card_x + 10, card_y + 14,
                   card_x, card_y + 14, fill="#f7fcff", outline=dark, width=1, tags=tag)
        _safe_call(canvas, "create_polygon", card_x + 18, card_y - 1, card_x + 25, card_y - 1,
                   card_x + 25, card_y + 7, card_x + 21, card_y + 4, card_x + 18, card_y + 7,
                   fill="#10151d", outline="", tags=tag)
        for offset in (4, 8):
            _safe_call(canvas, "create_line", card_x + 4, card_y + offset, card_x + 15, card_y + offset,
                       fill="#517184", width=1, tags=tag)
    elif name == "HEX":
        for offset in (-10, 0, 10):
            _safe_call(canvas, "create_line", cx + body_w + 3, body_cy + offset,
                       cx + body_w + (9 if offset else 13), body_cy + offset,
                       fill=light, width=1, tags=tag)
        _safe_call(canvas, "create_text", cx, body_cy + body_h * 0.28, text="0x",
                   fill=dark, font=("Consolas", max(6, round(current_width / 13)), "bold"), tags=tag)
    elif name == "CACHE":
        bag_x = cx + body_w * 0.62
        bag_y = body_cy + body_h * 0.10
        _safe_call(canvas, "create_line", cx - body_w * 0.45, body_cy - body_h * 0.58,
                   bag_x, bag_y, fill="#5a3510", width=3, tags=tag)
        _safe_call(canvas, "create_rectangle", bag_x - 11, bag_y - 3, bag_x + 13, bag_y + 18,
                   fill="#9a642b", outline=outline, width=2, tags=tag)
        for offset in (-6, 0, 6):
            _safe_call(canvas, "create_rectangle", bag_x + offset - 3, bag_y - 10 - abs(offset) / 3,
                       bag_x + offset + 4, bag_y + 2, fill="#fff7d0", outline="#6a5a31", tags=tag)
    elif name == "LOOP" or accessory == "pink_bow":
        bow_y = head_cy - head_h * 1.00
        _safe_call(canvas, "create_polygon", cx - 2, bow_y + 5, cx - 17, bow_y - 3, cx - 16, bow_y + 12,
                   fill="#ff78bc", outline="#5c163f", width=2, tags=tag)
        _safe_call(canvas, "create_polygon", cx + 2, bow_y + 5, cx + 17, bow_y - 3, cx + 16, bow_y + 12,
                   fill="#ff78bc", outline="#5c163f", width=2, tags=tag)
        _safe_call(canvas, "create_oval", cx - 5, bow_y, cx + 5, bow_y + 10,
                   fill="#ffd0e9", outline="#5c163f", tags=tag)
    elif name == "PING":
        for direction in (-1, 1):
            x = cx + direction * foot_spread
            points: list[float] = []
            for step in range(7):
                points.extend((x + direction * (4 if step % 2 else -4), foot_y - 3 - step * 2))
            _safe_call(canvas, "create_line", *points, fill=light, width=2, tags=tag)
        bar_x = cx - body_w * 0.52
        bar_y = body_cy + body_h * 0.15
        _safe_call(canvas, "create_rectangle", bar_x, bar_y, bar_x + body_w * 1.05, bar_y + 7,
                   fill="#062d25", outline=outline, tags=tag)
        fill_width = body_w * 0.95 * ((phase % 10) / 9.0)
        _safe_call(canvas, "create_rectangle", bar_x + 2, bar_y + 2, bar_x + 2 + fill_width, bar_y + 5,
                   fill=light, outline="", tags=tag)
    elif name == "PATCH" or accessory == "bandage":
        _safe_call(canvas, "create_rectangle", cx + head_w * 0.18, head_cy - head_h * 0.55,
                   cx + head_w * 0.70, head_cy - head_h * 0.33,
                   fill="#fff6c3", outline="#7b5b00", width=1, tags=tag)
        wrench_x = cx - body_w * 0.86
        _safe_call(canvas, "create_line", wrench_x, body_cy + body_h * 0.55,
                   wrench_x + 18, body_cy - body_h * 0.15, fill="#d9e1e8", width=4, tags=tag)
        _safe_call(canvas, "create_arc", wrench_x + 11, body_cy - body_h * 0.36,
                   wrench_x + 25, body_cy - body_h * 0.04, start=35, extent=290,
                   style="arc", outline="#d9e1e8", width=3, tags=tag)
    elif name == "ROOT" or accessory == "tiny_crown":
        crown_y = head_cy - head_h * 1.16
        _safe_call(canvas, "create_polygon", cx - 15, crown_y + 13, cx - 12, crown_y,
                   cx - 3, crown_y + 9, cx + 3, crown_y - 2, cx + 12, crown_y + 9,
                   cx + 15, crown_y, cx + 16, crown_y + 13,
                   fill="#ffe06e", outline="#5f4600", width=2, tags=tag)
        _safe_call(canvas, "create_polygon", cx - body_w * 0.78, body_cy - body_h * 0.42,
                   cx - body_w * 1.02, floor - 7, cx, floor - 14,
                   fill=_mix(accent, dark, 0.72), outline=outline, width=1, tags=tag)
    elif name == "NULL":
        _safe_call(canvas, "create_oval", cx - head_w * 1.04, head_cy - head_h * 1.04,
                   cx + head_w * 1.04, head_cy + head_h * 1.04,
                   outline=light, width=2, dash=(3, 3), tags=tag)
        _safe_call(canvas, "create_text", cx + body_w * 0.78, body_cy + body_h * 0.55,
                   text="?", fill=light, font=("Consolas", max(9, round(current_width / 8)), "bold"), tags=tag)
    elif name == "GLITCH" or accessory == "antenna":
        _safe_call(canvas, "create_line", cx + head_w * 0.18, head_cy - head_h * 0.86,
                   cx + head_w * 0.55, head_cy - head_h * 1.34, fill=light, width=2, tags=tag)
        _safe_call(canvas, "create_oval", cx + head_w * 0.48, head_cy - head_h * 1.42,
                   cx + head_w * 0.68, head_cy - head_h * 1.22, fill=accent, outline=outline, tags=tag)
        for offset, length in ((-8, 17), (0, 24), (8, 13)):
            y = body_cy + offset
            _safe_call(canvas, "create_rectangle", cx - body_w * 0.95, y,
                       cx - body_w * 0.95 + length, y + 3,
                       fill=light if offset else accent, outline="", tags=tag)
        _safe_call(canvas, "create_line", cx - head_w + 4, eye_y - 10,
                   cx + head_w + 6, eye_y - 10, fill="#ff8a98", width=2, dash=(7, 3), tags=tag)

    if show_name:
        plate_y = current_height - 13
        plate_width = min(current_width - 4, max(44, len(name) * 7 + 16))
        _safe_call(canvas, "create_rectangle", cx - plate_width / 2, plate_y - 8,
                   cx + plate_width / 2, plate_y + 3,
                   fill="#07101a", outline=_mix(accent, "#ffffff", 0.16), width=1, tags=tag)
        _safe_call(canvas, "create_text", cx, plate_y - 2, text=name,
                   fill=light, font=("Consolas", max(6, round(current_width / 14)), "bold"), tags=tag)

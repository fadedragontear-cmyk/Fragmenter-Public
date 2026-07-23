#!/usr/bin/env python3
"""V68: green translucent corruption, violent shell hatch, synchronized expansion."""
from __future__ import annotations

import math
import tkinter as tk
from typing import Any

from celdra_evolution_pixel_v4 import HATCH_SEQUENCE
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v63 import PublicFragmenterAppV63
from fragmenter_public_gui_v64 import GLITCH_BINARY, GLITCH_TERMS
from fragmenter_public_gui_v67 import PublicFragmenterAppV67


# Only the split-shell frames are used in production.  The generated Gremlin
# frames remain test-only and never appear in the canonical startup sequence.
PRODUCTION_SHELL_HATCH = tuple(HATCH_SEQUENCE[:3])


class PublicFragmenterAppV68(PublicFragmenterAppV67):
    """Keep corruption behind the egg and make the blast physically hatch it."""

    ENERGY_EXPANSION_STAGES = {
        0: (0.38, 280),
        6: (0.50, 360),
        12: (0.63, 430),
        18: (0.76, 500),
        24: (0.89, 560),
        30: (0.985, 650),
    }
    SHELL_HATCH_STAGES = {
        8: 0,
        16: 1,
        24: 2,
    }

    def __init__(self) -> None:
        self._celdra_shell_hatch_index_v68 = -1
        self._celdra_egg_shake_phase_v68 = 0
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Green Corruption Hatch")

    # ------------------------------------------------------------------
    # Green, translucent-looking text field behind the shell.
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_text_v68(canvas: tk.Canvas, x: float, y: float, **kwargs: Any) -> None:
        try:
            canvas.create_text(x, y, **kwargs)
        except tk.TclError:
            kwargs.pop("stipple", None)
            kwargs.pop("angle", None)
            canvas.create_text(x, y, **kwargs)

    @staticmethod
    def _safe_line_v68(canvas: tk.Canvas, *coords: float, **kwargs: Any) -> None:
        try:
            canvas.create_line(*coords, **kwargs)
        except tk.TclError:
            kwargs.pop("stipple", None)
            canvas.create_line(*coords, **kwargs)

    @staticmethod
    def _green_corruption_value_v68(term: str, phase: int, slot: int, level: int) -> str:
        binary = GLITCH_BINARY[term].replace(" ", "")
        mode = (phase + slot * 3) % 7
        if mode == 0:
            shift = (phase * 5 + slot * 13) % max(1, len(binary))
            return (binary[shift:] + binary[:shift])[: 16 + level * 10]
        if mode == 1:
            return f"<{term}>::{(phase * 29 + slot * 17) & 0xFFFF:04X}"
        if mode == 2:
            return term[::-1] + f"/{phase:02X}"
        if mode == 3:
            replacement = "01/\\?ΔΞ#"
            return "".join(
                character
                if (index + phase + slot) % max(2, 5 - level)
                else replacement[(phase + slot + index) % len(replacement)]
                for index, character in enumerate(term)
            )
        if mode == 4:
            return f"{term[: max(1, len(term) - level)]}//QUAR::{slot:02X}"
        if mode == 5:
            return " ".join(f"{ord(character):02X}" for character in term)
        return f"[{term}]_{phase:02X}{slot:02X}_INFECT"

    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        level = self._celdra_glitch_level_v61
        if level <= 0:
            return
        phase = self._celdra_glitch_phase_v61
        tag = "v68_green_corruption_bg"
        cx = width // 2
        cy = height // 2 + 18
        greens = (
            "#0b4b35",
            "#0f6845",
            "#12865a",
            "#1ba66c",
            "#36ce87",
            "#78efaf",
        )
        stipples = ("gray12", "gray25", "gray12", "gray50")

        # Faint matrix columns drift vertically behind the egg.
        column_count = 7 + level * 4
        for column in range(column_count):
            term = GLITCH_TERMS[(column * 3 + phase // 4) % len(GLITCH_TERMS)]
            bits = GLITCH_BINARY[term].replace(" ", "")
            start = (phase * (3 + column % 5) + column * 11) % max(1, len(bits))
            stream = (bits[start:] + bits[:start])[: 12 + level * 7]
            x = 18 + ((column * 79 + phase * (2 + column % 4)) % max(36, width - 36))
            y = 48 + ((column * 61 + phase * (7 + column % 3)) % max(60, height - 98))
            self._safe_text_v68(
                canvas,
                x,
                y,
                text="\n".join(stream),
                anchor="center",
                fill=greens[(column + phase) % len(greens)],
                font=("Consolas", 6 + (column + level) % 3, "normal"),
                stipple=stipple[0] if (stipple := stipples[(column + level) % len(stipples)]) else "gray12",
                tags=tag,
            )

        # Floating fragments use different sizes, angles and mutation modes.
        density = 12 + level * 10
        for slot in range(density):
            term = GLITCH_TERMS[(phase // 2 + slot * 5 + level) % len(GLITCH_TERMS)]
            value = self._green_corruption_value_v68(term, phase, slot, level)
            x = 12 + ((slot * 97 + phase * (5 + slot % 7)) % max(34, width - 24))
            y = 52 + ((slot * 67 + phase * (3 + slot % 9)) % max(52, height - 100))
            angle = (-24, -17, -10, -5, 0, 6, 12, 19, 25)[(slot + phase) % 9]
            self._safe_text_v68(
                canvas,
                x,
                y,
                text=value,
                anchor="center",
                angle=angle,
                fill=greens[(slot * 2 + phase) % len(greens)],
                font=(
                    "Consolas",
                    7 + ((slot * 3 + phase + level) % (5 + level)),
                    "bold" if (slot + phase) % 5 == 0 else "normal",
                ),
                stipple=stipples[(slot + phase + level) % len(stipples)],
                tags=tag,
            )

        # Large translucent identity ghosts move slowly behind the central shell.
        for ghost in range(3 + level):
            term = GLITCH_TERMS[(phase // 6 + ghost * 3) % len(GLITCH_TERMS)]
            value = self._green_corruption_value_v68(term, phase // 2, ghost + 41, level)
            x = width * (0.13 + ((ghost * 23 + phase) % 73) / 100.0)
            y = height * (0.18 + ((ghost * 19 + phase * 2) % 66) / 100.0)
            self._safe_text_v68(
                canvas,
                x,
                y,
                text=value,
                anchor="center",
                angle=(-18 + ghost * 8),
                fill=greens[(ghost + phase // 3) % len(greens)],
                font=("Consolas", 17 + level * 3 + ghost * 2, "bold"),
                stipple="gray12",
                tags=tag,
            )

        # Digital containment rings, node links and scan traces add depth without
        # drawing opaque blocks over the egg.
        nodes: list[tuple[float, float]] = []
        node_count = 5 + level * 2
        for node in range(node_count):
            angle = math.radians(node * (360 / node_count) + phase * (3 + node % 3))
            radius_x = 78 + level * 21 + (node % 3) * 22
            radius_y = 55 + level * 14 + (node % 2) * 19
            x = cx + math.cos(angle) * radius_x
            y = cy + math.sin(angle) * radius_y
            nodes.append((x, y))
            canvas.create_oval(
                x - 2,
                y - 2,
                x + 2,
                y + 2,
                outline=greens[(node + phase) % len(greens)],
                width=1,
                tags=tag,
            )
            self._safe_text_v68(
                canvas,
                x + 5,
                y - 5,
                text=f"{(phase * 31 + node * 47) & 0xFF:02X}",
                anchor="w",
                fill=greens[(node + 2 + phase) % len(greens)],
                font=("Consolas", 6, "normal"),
                stipple="gray25",
                tags=tag,
            )
        for index, (x1, y1) in enumerate(nodes):
            x2, y2 = nodes[(index + 1) % len(nodes)]
            self._safe_line_v68(
                canvas,
                x1,
                y1,
                x2,
                y2,
                fill=greens[(index + phase) % len(greens)],
                width=1,
                dash=(1 + index % 3, 10 - min(5, level)),
                stipple="gray25",
                tags=tag,
            )

        for trace in range(3 + level * 2):
            y = 48 + ((trace * 83 + phase * 13) % max(56, height - 92))
            self._safe_line_v68(
                canvas,
                0,
                y,
                width,
                y - 11 - trace * 2,
                fill=greens[(trace + phase) % len(greens)],
                width=1,
                dash=(1 + trace % 4, 14 - min(7, level)),
                stipple="gray12",
                tags=tag,
            )

        try:
            canvas.tag_lower(tag)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Stronger shell shake near the end, without shaking the background field.
    # ------------------------------------------------------------------
    def _redraw_celdra_avatar_v50(self) -> None:
        super()._redraw_celdra_avatar_v50()
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        has_shell = self.celdra_current_pixel_v50 is not None and self.celdra_current_external_v50 is None
        if not has_shell:
            return
        level = int(getattr(self, "_celdra_glitch_level_v61", 0) or 0)
        energy = bool(getattr(self, "_celdra_energy_active_v63", False))
        if level < 3 and not energy:
            return

        self._celdra_egg_shake_phase_v68 += 1
        phase = self._celdra_egg_shake_phase_v68
        magnitude = 1 + max(0, level - 2) * 2
        if energy:
            magnitude = 3 + min(8, int(getattr(self, "_celdra_energy_step_v63", 0) or 0) // 5)
        dx = (0, magnitude, -magnitude, magnitude // 2, -magnitude // 2, 0)[phase % 6]
        dy = (0, -1, 1, 0, -2, 2)[phase % 6]

        for item in canvas.find_all():
            tags = set(canvas.gettags(item))
            if tags:
                continue
            try:
                canvas.move(item, dx, dy)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Hatch the shell inside the blast and push the viewport open in stages.
    # ------------------------------------------------------------------
    def _start_energy_hatch_v63(self) -> None:
        self._stop_tavern_seal_v64()
        self._start_console_alarm_v64()
        self._celdra_shell_hatch_index_v68 = -1
        self._celdra_egg_shake_phase_v68 = 0
        # Bypass V64's single immediate 98.5% jump. V68 widens the stage in
        # lockstep with the explosion from _tick_energy_hatch_v63 instead.
        PublicFragmenterAppV63._start_energy_hatch_v63(self)

    def _tick_energy_hatch_v63(self) -> None:
        self._celdra_energy_after_v63 = None
        if not self._celdra_energy_active_v63:
            return

        step = self._celdra_energy_step_v63
        speed = max(0.01, float(self._celdra_timeline_speed_v51))

        expansion = self.ENERGY_EXPANSION_STAGES.get(step)
        if expansion is not None:
            fraction, duration = expansion
            PublicFragmenterAppV54._animate_stage_fraction_v54(
                self,
                fraction,
                max(70, round(duration * speed)),
            )

        shell_index = self.SHELL_HATCH_STAGES.get(step)
        if shell_index is not None and shell_index < len(PRODUCTION_SHELL_HATCH):
            self._celdra_shell_hatch_index_v68 = shell_index
            self.celdra_current_external_v50 = None
            self.celdra_current_pixel_v50 = PRODUCTION_SHELL_HATCH[shell_index]
            if self._celdra_stage_detail_v54 is not None:
                self._celdra_stage_detail_v54.set(
                    f"30×30 • SHELL RELEASE {shell_index + 1}/{len(PRODUCTION_SHELL_HATCH)}"
                )

        # Once the shell halves have visibly separated, let the energy field own
        # the viewport until the concealed GIF is installed behind the whiteout.
        if step == 31:
            self.celdra_current_pixel_v50 = None
            self.celdra_current_external_v50 = None

        if step == 44 and not self._celdra_energy_gif_started_v63:
            self._begin_hatch_gif_v63()

        self._redraw_celdra_avatar_v50()
        self._celdra_energy_step_v63 += 1
        if self._celdra_energy_step_v63 >= self.ENERGY_STEPS:
            self._celdra_energy_active_v63 = False
            self._redraw_celdra_avatar_v50()
            return

        interval = max(10, round(175 * speed))
        self._celdra_energy_after_v63 = self.after(interval, self._tick_energy_hatch_v63)


def main() -> int:
    app = PublicFragmenterAppV68()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

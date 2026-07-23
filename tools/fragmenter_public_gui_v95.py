#!/usr/bin/env python3
"""V95: restored hatchling Gremlin swarm, outlined poses, and deeper long-form content."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from celdra_evolution_pixel_v4 import (
    CELDRA_BLUE_PALETTE,
    HATCHLING_BASE_CLAIM,
    HATCHLING_BASE_FAILED,
    HATCHLING_IDLE,
    HATCHLING_SEARCH,
    HATCHLING_SQUISHED,
)
from celdra_pixel_pet_v1 import PixelFrame
from celdra_v95_content import (
    CONSOLE_BANTER,
    GREMLIN_HAVOC_STAGES,
    GREMLIN_START_DELAY_MS,
    GREMLIN_SWARM_SIZE,
    STORY_END_DELAY_MS,
    STORY_FILLER,
    WAITING_FILLER,
    WAITING_FILLER_DELAY_MS,
)
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v94 import PublicFragmenterAppV94


class PublicFragmenterAppV95(PublicFragmenterAppV94):
    """Use the discarded V60 hatchling as a safe, animated Gremlin swarm."""

    STORY_FILLER = STORY_FILLER
    INITIAL_CONSOLE_BANTER = CONSOLE_BANTER
    WAITING_FILLER = WAITING_FILLER
    STORY_END_DELAY_MS = STORY_END_DELAY_MS
    WAITING_FILLER_DELAY_MS = WAITING_FILLER_DELAY_MS
    GREMLIN_START_DELAY_MS = GREMLIN_START_DELAY_MS
    GREMLIN_SWARM_SIZE = GREMLIN_SWARM_SIZE

    def __init__(self) -> None:
        self._celdra_outline_display_v95: tk.PhotoImage | None = None
        self._celdra_gremlin_swarm_v95: list[dict[str, Any]] = []
        self._celdra_gremlin_status_frame_v95: tk.Frame | None = None
        self._celdra_gremlin_status_label_v95: tk.StringVar | None = None
        self._celdra_gremlin_status_progress_v95: ttk.Progressbar | None = None
        self._celdra_gremlin_swarm_animation_after_v95: str | None = None
        self._celdra_gremlin_swarm_motion_after_v95: str | None = None
        self._celdra_gremlin_swarm_phase_v95 = 0
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Hatchling Gremlin Swarm V95")

    # ------------------------------------------------------------------
    # Celdra PNG polish: replace the rough alpha-edge pixels with a thin
    # inward black rim.  The outline never expands the crop or changes layout.
    # ------------------------------------------------------------------
    def _load_takeover_reaction_v58(self, name: str) -> bool:
        loaded = super()._load_takeover_reaction_v58(name)
        if not loaded:
            return False
        source = self.celdra_current_external_v50
        if source is None:
            return True
        outlined = self._inward_outline_photo_v95(source, thickness=2)
        if outlined is source:
            return True
        self._celdra_outline_display_v95 = outlined
        self._celdra_manifest_display_v56 = outlined
        self.celdra_current_external_v50 = outlined
        self._redraw_celdra_avatar_v50()
        return True

    @staticmethod
    def _inward_outline_photo_v95(source: tk.PhotoImage, *, thickness: int = 2) -> tk.PhotoImage:
        try:
            width = int(source.width())
            height = int(source.height())
            opaque = [
                [not bool(source.transparency_get(x, y)) for x in range(width)]
                for y in range(height)
            ]
        except (AttributeError, tk.TclError, ValueError):
            return source
        if width <= 1 or height <= 1:
            return source

        frontier: set[tuple[int, int]] = set()
        for y in range(height):
            for x in range(width):
                if not opaque[y][x]:
                    continue
                if any(
                    nx < 0
                    or ny < 0
                    or nx >= width
                    or ny >= height
                    or not opaque[ny][nx]
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                ):
                    frontier.add((x, y))

        outline = set(frontier)
        for _layer in range(max(1, int(thickness)) - 1):
            expanded: set[tuple[int, int]] = set()
            for x, y in frontier:
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < width and 0 <= ny < height and opaque[ny][nx] and (nx, ny) not in outline:
                        expanded.add((nx, ny))
            outline.update(expanded)
            frontier = expanded
            if not frontier:
                break

        if not outline:
            return source
        try:
            output = tk.PhotoImage(width=width, height=height)
            output.tk.call(output, "copy", source)
            for x, y in outline:
                output.put("#030609", to=(x, y))
            return output
        except tk.TclError:
            return source

    # ------------------------------------------------------------------
    # Restored Gremlin show.  Every creature is the preserved V60 hatchling
    # PixelFrame design.  The swarm only animates Tk widgets and presentation
    # sashes; it has no file or pipeline mutation path.
    # ------------------------------------------------------------------
    def _start_gremlin_show_v94(self) -> None:
        if self._celdra_gremlin_active_v94:
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._celdra_gremlin_active_v94 = True
        self._celdra_gremlin_token_v94 += 1
        self._celdra_gremlin_reported_stages_v94.clear()
        self._runtime_pose_v70(
            "wink",
            "Wanna see a trick? I found the retired hatchling build in the presentation cache. It was too cute to delete and too chaotic to promote.",
        )
        self._schedule_gremlin_v94(2_800, self._spawn_gremlin_swarm_v95)
        self._schedule_gremlin_v94(7_000, self._scatter_gremlin_swarm_v95)
        self._schedule_gremlin_v94(12_000, self._push_console_with_swarm_v95)
        self._schedule_gremlin_v94(17_000, self._start_gremlin_havoc_v95)
        self._schedule_gremlin_v94(28_000, self._tour_ui_with_swarm_v95)
        self._schedule_gremlin_v94(38_000, self._form_gremlin_parties_v95)
        self._schedule_gremlin_v94(49_000, self._recall_gremlin_swarm_v95)
        self._schedule_gremlin_v94(59_000, self._finish_gremlin_swarm_v95)

    def _spawn_gremlin_v94(self) -> None:
        self._spawn_gremlin_swarm_v95()

    def _spawn_gremlin_swarm_v95(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._destroy_gremlin_overlay_v94()
        self._celdra_gremlin_active_v94 = True
        self._install_gremlin_status_bar_v95()
        avatar = self.celdra_avatar_canvas_v50
        initial_points = (
            (0.16, 0.26),
            (0.34, 0.18),
            (0.52, 0.30),
            (0.72, 0.20),
            (0.24, 0.63),
            (0.52, 0.68),
            (0.78, 0.58),
        )
        for index in range(self.GREMLIN_SWARM_SIZE):
            relx, rely = initial_points[index % len(initial_points)]
            x, y = self._widget_point_v94(avatar, relx, rely)
            holder = tk.Frame(
                self,
                background="#071426",
                highlightbackground="#45a9db",
                highlightcolor="#45a9db",
                highlightthickness=1,
                borderwidth=0,
            )
            holder.place(x=max(0, x - 37), y=max(0, y - 37), width=74, height=74)
            canvas = tk.Canvas(
                holder,
                width=72,
                height=72,
                background="#071426",
                highlightthickness=0,
                borderwidth=0,
            )
            canvas.pack(fill="both", expand=True)
            row = {
                "index": index,
                "holder": holder,
                "canvas": canvas,
                "x": float(x),
                "y": float(y),
                "sequence": HATCHLING_IDLE,
                "frame": index,
            }
            self._celdra_gremlin_swarm_v95.append(row)
            try:
                holder.lift()
            except tk.TclError:
                pass
        self._celdra_gremlin_status_v94 = self._celdra_gremlin_status_label_v95
        self._celdra_gremlin_progress_v94 = self._celdra_gremlin_status_progress_v95
        self._set_swarm_sequence_v95(HATCHLING_IDLE)
        self._start_swarm_animation_v95()

    def _install_gremlin_status_bar_v95(self) -> None:
        frame = tk.Frame(
            self,
            background="#071426",
            highlightbackground="#45a9db",
            highlightcolor="#45a9db",
            highlightthickness=1,
            borderwidth=0,
        )
        frame.columnconfigure(1, weight=1)
        tk.Label(
            frame,
            text="GREMLIN SWARM // WREAK HAVOC",
            background="#071426",
            foreground="#c7f2ff",
            font=("Fixedsys", 8, "bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=(8, 10), pady=(4, 0), sticky="w")
        status = tk.StringVar(value=f"LEGACY HATCHLINGS ONLINE: {self.GREMLIN_SWARM_SIZE} // FILE ACCESS: NONE")
        tk.Label(
            frame,
            textvariable=status,
            background="#071426",
            foreground="#79cff1",
            font=("Fixedsys", 8),
            anchor="w",
        ).grid(row=0, column=1, padx=(0, 8), pady=(4, 0), sticky="ew")
        progress = ttk.Progressbar(frame, maximum=100.0, mode="determinate")
        progress.grid(row=1, column=0, columnspan=2, padx=8, pady=(3, 6), sticky="ew")
        self._celdra_gremlin_status_frame_v95 = frame
        self._celdra_gremlin_status_label_v95 = status
        self._celdra_gremlin_status_progress_v95 = progress
        self._position_gremlin_status_v95()

    def _position_gremlin_status_v95(self) -> None:
        frame = self._celdra_gremlin_status_frame_v95
        console = getattr(self, "_celdra_console_v49", None)
        if frame is None or console is None:
            return
        try:
            self.update_idletasks()
            x = console.winfo_rootx() - self.winfo_rootx()
            y = console.winfo_rooty() - self.winfo_rooty() - 48
            width = max(320, console.winfo_width())
            frame.place(x=max(0, x), y=max(0, y), width=width, height=46)
            frame.lift()
        except tk.TclError:
            pass

    @staticmethod
    def _draw_hatchling_frame_v95(canvas: tk.Canvas, frame: PixelFrame) -> None:
        try:
            canvas.delete("all")
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
        except tk.TclError:
            return
        rows = frame.rows
        columns = max((len(row) for row in rows), default=1)
        scale = max(1, min((width - 4) // max(1, columns), (height - 4) // max(1, len(rows))))
        art_width = columns * scale
        art_height = len(rows) * scale
        x0 = (width - art_width) // 2
        y0 = (height - art_height) // 2
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = CELDRA_BLUE_PALETTE.get(symbol, "")
                if not color:
                    continue
                try:
                    canvas.create_rectangle(
                        x0 + column_index * scale,
                        y0 + row_index * scale,
                        x0 + (column_index + 1) * scale,
                        y0 + (row_index + 1) * scale,
                        fill=color,
                        outline=color,
                    )
                except tk.TclError:
                    return

    def _start_swarm_animation_v95(self) -> None:
        if self._celdra_gremlin_swarm_animation_after_v95 is not None:
            return
        token = self._celdra_gremlin_token_v94

        def tick() -> None:
            self._celdra_gremlin_swarm_animation_after_v95 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            self._celdra_gremlin_swarm_phase_v95 += 1
            self._position_gremlin_status_v95()
            for item in tuple(self._celdra_gremlin_swarm_v95):
                sequence = tuple(item.get("sequence") or HATCHLING_IDLE)
                if not sequence:
                    continue
                frame_index = (self._celdra_gremlin_swarm_phase_v95 + int(item.get("index") or 0) * 2) % len(sequence)
                item["frame"] = frame_index
                self._draw_hatchling_frame_v95(item["canvas"], sequence[frame_index])
                try:
                    item["holder"].lift()
                except tk.TclError:
                    pass
            self._celdra_gremlin_swarm_animation_after_v95 = self.after(
                max(45, self._scaled_runtime_ms_v88(170)),
                tick,
            )

        self._celdra_gremlin_swarm_animation_after_v95 = self.after(45, tick)

    def _set_swarm_sequence_v95(
        self,
        sequence: tuple[PixelFrame, ...],
        indices: set[int] | None = None,
    ) -> None:
        for item in self._celdra_gremlin_swarm_v95:
            if indices is None or int(item.get("index") or 0) in indices:
                item["sequence"] = sequence

    def _animate_swarm_to_v95(
        self,
        targets: list[tuple[int, int]],
        duration_ms: int,
        done: Callable[[], None] | None = None,
    ) -> None:
        if not self._celdra_gremlin_swarm_v95:
            if done is not None:
                done()
            return
        if self._celdra_gremlin_swarm_motion_after_v95 is not None:
            try:
                self.after_cancel(self._celdra_gremlin_swarm_motion_after_v95)
            except tk.TclError:
                pass
            self._celdra_gremlin_swarm_motion_after_v95 = None
        starts = [(float(item.get("x") or 0), float(item.get("y") or 0)) for item in self._celdra_gremlin_swarm_v95]
        if not targets:
            targets = [(round(x), round(y)) for x, y in starts]
        while len(targets) < len(starts):
            targets.append(targets[len(targets) % max(1, len(targets))])
        started = time.monotonic()
        scaled = max(1, self._scaled_runtime_ms_v88(duration_ms))
        token = self._celdra_gremlin_token_v94

        def tick() -> None:
            self._celdra_gremlin_swarm_motion_after_v95 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            fraction = min(1.0, (time.monotonic() - started) * 1000.0 / scaled)
            eased = 1.0 - (1.0 - fraction) ** 3
            for index, item in enumerate(self._celdra_gremlin_swarm_v95):
                sx, sy = starts[index]
                tx, ty = targets[index]
                x = sx + (tx - sx) * eased
                y = sy + (ty - sy) * eased
                item["x"] = x
                item["y"] = y
                try:
                    item["holder"].place_configure(x=round(x - 37), y=round(y - 37))
                    item["holder"].lift()
                except tk.TclError:
                    pass
            if fraction < 1.0:
                self._celdra_gremlin_swarm_motion_after_v95 = self.after(28, tick)
            elif done is not None:
                done()

        tick()

    def _scatter_gremlin_swarm_v95(self) -> None:
        avatar = self.celdra_avatar_canvas_v50
        points = [
            self._widget_point_v94(avatar, 0.08, 0.18),
            self._widget_point_v94(avatar, 0.30, 0.08),
            self._widget_point_v94(avatar, 0.54, 0.16),
            self._widget_point_v94(avatar, 0.86, 0.12),
            self._widget_point_v94(avatar, 0.16, 0.76),
            self._widget_point_v94(avatar, 0.52, 0.82),
            self._widget_point_v94(avatar, 0.84, 0.70),
        ]
        self._set_swarm_sequence_v95(HATCHLING_SEARCH)
        self._animate_swarm_to_v95(points, 3_600)

    def _push_console_with_swarm_v95(self) -> None:
        pane = getattr(self, "celdra_visual_split_v50", None)
        try:
            width = max(1, pane.winfo_width())
            self._celdra_gremlin_saved_stage_fraction_v94 = pane.sashpos(0) / width
        except (AttributeError, tk.TclError):
            self._celdra_gremlin_saved_stage_fraction_v94 = 0.56
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            0.78,
            self._scaled_runtime_ms_v88(1_700),
        )
        console = getattr(self, "_celdra_console_v49", None)
        targets = [
            self._widget_point_v94(console, 0.08, 0.08),
            self._widget_point_v94(console, 0.24, 0.12),
            self._widget_point_v94(console, 0.42, 0.06),
            self._widget_point_v94(console, 0.60, 0.13),
            self._widget_point_v94(console, 0.78, 0.07),
            self._widget_point_v94(console, 0.91, 0.16),
            self._widget_point_v94(console, 0.52, 0.42),
        ]
        self._set_swarm_sequence_v95(HATCHLING_SQUISHED, {0, 1, 2})
        self._animate_swarm_to_v95(targets, 3_300)
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set("CONSOLE OCCUPIED // BRAIN OBJECTION LOGGED")

    def _start_gremlin_havoc_v95(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        started = time.monotonic()
        scaled = max(1, self._scaled_runtime_ms_v88(14_000))
        token = self._celdra_gremlin_token_v94
        self._set_swarm_sequence_v95(HATCHLING_BASE_CLAIM)

        def tick() -> None:
            self._celdra_gremlin_havoc_after_v94 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            progress = min(100, round((time.monotonic() - started) * 1000.0 / scaled * 100))
            if self._celdra_gremlin_status_progress_v95 is not None:
                try:
                    self._celdra_gremlin_status_progress_v95["value"] = progress
                except tk.TclError:
                    pass
            label = GREMLIN_HAVOC_STAGES[0][1]
            threshold_value = 0
            for threshold, candidate in GREMLIN_HAVOC_STAGES:
                if progress >= threshold:
                    threshold_value = threshold
                    label = candidate
            if self._celdra_gremlin_status_label_v95 is not None:
                self._celdra_gremlin_status_label_v95.set(label)
            if threshold_value not in self._celdra_gremlin_reported_stages_v94:
                self._celdra_gremlin_reported_stages_v94.add(threshold_value)
                if threshold_value in {22, 61, 86, 100}:
                    self._append_console_v49(f"[CORE] GREMLIN SWARM: {label}")
            if progress < 100:
                self._celdra_gremlin_havoc_after_v94 = self.after(55, tick)

        tick()

    def _tour_ui_with_swarm_v95(self) -> None:
        targets = [
            self._widget_point_v94(getattr(self, "stage_progress_frame", None), 0.12, 0.18),
            self._widget_point_v94(getattr(self, "stage_progress_frame", None), 0.50, 0.30),
            self._widget_point_v94(getattr(self, "stage_progress_frame", None), 0.84, 0.18),
            self._widget_point_v94(getattr(self, "run_log", None), 0.12, 0.20),
            self._widget_point_v94(getattr(self, "run_log", None), 0.40, 0.12),
            self._widget_point_v94(getattr(self, "run_log", None), 0.70, 0.24),
            self._widget_point_v94(getattr(self, "run_tree", None), 0.60, 0.65),
        ]
        self._set_swarm_sequence_v95(HATCHLING_SEARCH)
        self._animate_swarm_to_v95(targets, 6_800)
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set("UI TOUR // DO NOT FEED OR CLICK")

    def _form_gremlin_parties_v95(self) -> None:
        progress = getattr(self, "stage_progress_frame", None)
        first = self._widget_point_v94(progress, 0.30, 0.72)
        second = self._widget_point_v94(progress, 0.72, 0.72)
        targets = [
            (first[0] - 60, first[1]),
            first,
            (first[0] + 60, first[1]),
            (second[0] - 60, second[1]),
            second,
            (second[0] + 60, second[1]),
            self._widget_point_v94(getattr(self, "_celdra_console_v49", None), 0.50, 0.10),
        ]
        self._set_swarm_sequence_v95(HATCHLING_IDLE)
        self._animate_swarm_to_v95(targets, 4_500)
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set("TWO PARTIES OF THREE // ONE UNASSIGNED MENACE")

    def _recall_gremlin_swarm_v95(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._runtime_pose_v70(
            "angry",
            "Okay, trick's over. Everyone back into the legacy-assets folder before BRAIN starts naming antivirus products.",
        )
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            self._celdra_gremlin_saved_stage_fraction_v94,
            self._scaled_runtime_ms_v88(1_500),
        )
        center = self._widget_point_v94(self.celdra_avatar_canvas_v50, 0.52, 0.52)
        targets = [
            (center[0] - 54 + (index % 3) * 54, center[1] - 42 + (index // 3) * 54)
            for index in range(self.GREMLIN_SWARM_SIZE)
        ]
        self._set_swarm_sequence_v95(HATCHLING_BASE_FAILED)
        self._animate_swarm_to_v95(targets, 5_200)
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set("RECALL SIGNAL // COMPLIANCE RELUCTANT")

    def _finish_gremlin_swarm_v95(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        width = max(640, self.winfo_width())
        height = max(480, self.winfo_height())
        targets = [
            (width + 120 + index * 45, height // 2 + ((index % 3) - 1) * 72)
            for index in range(self.GREMLIN_SWARM_SIZE)
        ]

        def done() -> None:
            self._destroy_gremlin_overlay_v94()
            self._celdra_gremlin_active_v94 = False
            self._runtime_pose_v70(
                "smile",
                "Seven hatchlings recalled, zero files modified, two unauthorized parties dissolved, and BRAIN's console has been emotionally restored.",
            )

        self._animate_swarm_to_v95(targets, 3_000, done)

    def _destroy_gremlin_overlay_v94(self) -> None:
        for attribute in (
            "_celdra_gremlin_swarm_animation_after_v95",
            "_celdra_gremlin_swarm_motion_after_v95",
        ):
            identifier = getattr(self, attribute, None)
            if identifier is not None:
                try:
                    self.after_cancel(identifier)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)
        for item in tuple(self._celdra_gremlin_swarm_v95):
            try:
                item["holder"].destroy()
            except (KeyError, tk.TclError):
                pass
        self._celdra_gremlin_swarm_v95.clear()
        if self._celdra_gremlin_status_frame_v95 is not None:
            try:
                self._celdra_gremlin_status_frame_v95.destroy()
            except tk.TclError:
                pass
        self._celdra_gremlin_status_frame_v95 = None
        self._celdra_gremlin_status_label_v95 = None
        self._celdra_gremlin_status_progress_v95 = None
        self._celdra_gremlin_status_v94 = None
        self._celdra_gremlin_progress_v94 = None
        super()._destroy_gremlin_overlay_v94()

    def _completion_text_v87(self) -> str:
        return (
            "RUN ALL complete. CCSF extracted, outputs indexed, reports written, and all seven "
            "legacy hatchlings returned to containment. Cool mode engaged."
        )

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V95"
            metadata["pose_inward_outline_px"] = 2
            metadata["gremlin_show"] = {
                "source": "celdra_evolution_pixel_v4.HATCHLING_*",
                "swarm_size": self.GREMLIN_SWARM_SIZE,
                "status_bar": "above_celdra_console",
                "procedural_substitute": False,
                "sandboxed": True,
                "file_mutations": 0,
            }
            metadata["long_form_story_ms"] = self.STORY_END_DELAY_MS
            metadata["waiting_observation_ms"] = self.WAITING_FILLER_DELAY_MS
        return payload


def main() -> int:
    app = PublicFragmenterAppV95()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

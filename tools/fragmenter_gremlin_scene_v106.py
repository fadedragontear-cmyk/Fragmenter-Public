#!/usr/bin/env python3
"""V106 Gremlin scene repair: hidden startup, shared-canvas art, and throttled motion."""
from __future__ import annotations

import math
import random
import tkinter as tk
from typing import Any, Callable

from celdra_gremlin_art_v2 import design_dimensions, draw_gremlin
from celdra_gremlin_memory_v1 import KNOWN_GREMLINS
from celdra_v99_content import GREMLIN_PERSONALITIES
from fragmenter_public_gui_v101 import PublicFragmenterAppV101


class _OffsetCanvasProxyV106:
    """Present one region of a shared Tk canvas as a small independent canvas."""

    def __init__(
        self,
        canvas: tk.Canvas,
        *,
        tag: str,
        x: float,
        y: float,
        width: int,
        height: int,
    ) -> None:
        self._canvas = canvas
        self._tag = tag
        self._x = float(x)
        self._y = float(y)
        self._width = int(width)
        self._height = int(height)

    def winfo_width(self) -> int:
        return self._width

    def winfo_height(self) -> int:
        return self._height

    def delete(self, tag: str) -> None:
        self._canvas.delete(self._tag if str(tag) in {"all", "v101_gremlin"} else tag)

    def _kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        output = dict(kwargs)
        output["tags"] = (self._tag, "v106_gremlin")
        return output

    def _pairs(self, values: tuple[Any, ...]) -> tuple[Any, ...]:
        shifted: list[Any] = []
        for index, value in enumerate(values):
            shifted.append(float(value) + (self._x if index % 2 == 0 else self._y))
        return tuple(shifted)

    def create_oval(self, x1: float, y1: float, x2: float, y2: float, **kwargs: Any) -> Any:
        return self._canvas.create_oval(
            x1 + self._x,
            y1 + self._y,
            x2 + self._x,
            y2 + self._y,
            **self._kwargs(kwargs),
        )

    def create_rectangle(self, x1: float, y1: float, x2: float, y2: float, **kwargs: Any) -> Any:
        return self._canvas.create_rectangle(
            x1 + self._x,
            y1 + self._y,
            x2 + self._x,
            y2 + self._y,
            **self._kwargs(kwargs),
        )

    def create_arc(self, x1: float, y1: float, x2: float, y2: float, **kwargs: Any) -> Any:
        return self._canvas.create_arc(
            x1 + self._x,
            y1 + self._y,
            x2 + self._x,
            y2 + self._y,
            **self._kwargs(kwargs),
        )

    def create_line(self, *coords: Any, **kwargs: Any) -> Any:
        return self._canvas.create_line(*self._pairs(coords), **self._kwargs(kwargs))

    def create_polygon(self, *coords: Any, **kwargs: Any) -> Any:
        return self._canvas.create_polygon(*self._pairs(coords), **self._kwargs(kwargs))

    def create_text(self, x: float, y: float, **kwargs: Any) -> Any:
        return self._canvas.create_text(x + self._x, y + self._y, **self._kwargs(kwargs))


class FragmenterGremlinSceneMixinV106:
    """Keep Gremlins dormant until directed and render them without opaque boxes."""

    GREMLIN_SCENE_BACKGROUND_V106 = "#0b1119"
    GREMLIN_TICK_MS_V106 = 150
    GREMLIN_REDRAW_EVERY_V106 = 5
    EXTERNAL_TRANSPARENT_KEY_V106 = "#010203"

    def __init__(self) -> None:
        self._gremlin_stage_enabled_v106 = False
        self._gremlin_intro_started_v106 = False
        self._gremlin_shared_canvas_v106: tk.Canvas | None = None
        self._run_plan_refresh_after_v106: str | None = None
        self._gremlin_schedule_generation_v106 = 0
        super().__init__()
        self._celdra_stable_reveal_v103 = False
        self.after_idle(self._settle_v106_startup)
        self.after(300, self._ensure_run_progress_v106)

    # ------------------------------------------------------------------
    # RUN ALL progress bars must be rebuilt after V104 installs its scroll host.
    # ------------------------------------------------------------------
    def _build_run_all(self, parent) -> None:
        super()._build_run_all(parent)
        self.after_idle(self._ensure_run_progress_v106)

    def _project_loaded(self) -> None:
        super()._project_loaded()
        self._gremlin_stage_enabled_v106 = False
        self._gremlin_intro_started_v106 = False
        self._celdra_stable_reveal_v103 = False
        self.after_idle(self._settle_v106_startup)
        self.after_idle(self._ensure_run_progress_v106)

    def _ensure_run_progress_v106(self) -> None:
        if getattr(self, "project", None) is None or not hasattr(self, "stage_progress_frame"):
            return
        try:
            self._refresh_run_plan()
        except (AttributeError, tk.TclError):
            return

    # ------------------------------------------------------------------
    # Shared scene: one canvas for every internal Gremlin. Individual opaque
    # child canvases previously masked one another whenever characters crossed.
    # ------------------------------------------------------------------
    def _ensure_shared_scene_v106(self) -> tk.Canvas | None:
        body = getattr(self, "_celdra_middle_body_v101", None)
        if body is None:
            return None
        canvas = self._gremlin_shared_canvas_v106
        if canvas is not None:
            try:
                if canvas.winfo_exists() and canvas.master is body:
                    return canvas
            except tk.TclError:
                pass
        for child in tuple(body.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        canvas = tk.Canvas(
            body,
            background=self.GREMLIN_SCENE_BACKGROUND_V106,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.bind("<Configure>", lambda _event: self.after_idle(self._redraw_shared_scene_v106))
        self._gremlin_shared_canvas_v106 = canvas
        return canvas

    def _ensure_middle_panel_v101(self, mode: str) -> None:
        super()._ensure_middle_panel_v101(mode)
        self._ensure_shared_scene_v106()

    @staticmethod
    def _gremlin_personality_v106(name: str) -> dict[str, Any]:
        folded = str(name or "").upper()
        return next(
            (
                dict(row)
                for row in GREMLIN_PERSONALITIES
                if str(row.get("name") or "").upper() == folded
            ),
            dict(GREMLIN_PERSONALITIES[0]),
        )

    def _show_internal_gremlin_v101(
        self,
        name: str,
        *,
        compact: bool = True,
    ) -> dict[str, Any] | None:
        folded = str(name or "").upper()
        current = self._celdra_middle_items_v101.get(folded)
        if current is not None:
            return current
        canvas = self._ensure_shared_scene_v106()
        if canvas is None:
            return None
        personality = self._gremlin_personality_v106(folded)
        art_width, art_height = design_dimensions(personality, compact=compact)
        pad_x = 22 if folded in {"BYTE", "CACHE", "PATCH", "ROOT"} else 14
        width, height = art_width + pad_x, art_height + 8
        index = KNOWN_GREMLINS.index(folded) if folded in KNOWN_GREMLINS else len(self._celdra_middle_items_v101)
        canvas.update_idletasks()
        area_width = max(260, canvas.winfo_width())
        area_height = max(240, canvas.winfo_height())
        x, y = self._grid_position_v101(index, area_width, area_height, width, height)
        item = {
            "name": folded,
            "index": index,
            "canvas": canvas,
            "personality": personality,
            "width": width,
            "height": height,
            "art_width": art_width,
            "art_height": art_height,
            "art_offset_x": pad_x // 2,
            "art_offset_y": 4,
            "x": float(x),
            "y": float(y),
            "vx": (1.45 + index * 0.16) * (-1 if index % 2 else 1),
            "vy": (1.05 + (index % 4) * 0.22) * (-1 if index % 3 else 1),
            "phase": index * 3,
            "mood": "idle",
            "compact": compact,
            "shared_v106": True,
            "tag_v106": f"v106_gremlin_{folded}",
        }
        self._celdra_middle_items_v101[folded] = item
        self._draw_personality_hatchling_v96(item, None)
        self._start_middle_animation_v101()
        return item

    def _clear_middle_items_v101(self) -> None:
        canvas = self._gremlin_shared_canvas_v106
        if canvas is not None:
            try:
                canvas.delete("v106_gremlin")
            except tk.TclError:
                pass
        self._celdra_middle_items_v101.clear()

    def _populate_middle_v101(self, names: list[str], *, compact: bool = True) -> None:
        wanted = [str(name).upper() for name in names]
        canvas = self._ensure_shared_scene_v106()
        for name in tuple(self._celdra_middle_items_v101):
            if name in wanted:
                continue
            item = self._celdra_middle_items_v101.pop(name)
            if canvas is not None:
                try:
                    canvas.delete(str(item.get("tag_v106") or ""))
                except tk.TclError:
                    pass
        for name in wanted:
            self._show_internal_gremlin_v101(name, compact=compact)
        self._redraw_shared_scene_v106()

    def _draw_personality_hatchling_v96(self, item: dict[str, Any], frame: Any) -> None:
        if not item.get("shared_v106"):
            super()._draw_personality_hatchling_v96(item, frame)
            return
        canvas = self._ensure_shared_scene_v106()
        if canvas is None:
            return
        tag = str(item.get("tag_v106") or f"v106_gremlin_{item.get('index', 0)}")
        x = float(item.get("x") or 0.0)
        y = float(item.get("y") or 0.0)
        proxy = _OffsetCanvasProxyV106(
            canvas,
            tag=tag,
            x=x + int(item.get("art_offset_x") or 0),
            y=y + int(item.get("art_offset_y") or 0),
            width=int(item.get("art_width") or item.get("width") or 82),
            height=int(item.get("art_height") or item.get("height") or 88),
        )
        personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
        mood = str(item.get("mood") or "idle")
        draw_gremlin(
            proxy,
            personality,
            width=int(item.get("art_width") or 82),
            height=int(item.get("art_height") or 88),
            phase=int(item.get("phase") or 0),
            mood=mood,
            compact=bool(item.get("compact")),
            show_name=True,
        )
        item["drawn_x_v106"] = x
        item["drawn_y_v106"] = y
        item["drawn_mood_v106"] = mood

    def _redraw_shared_scene_v106(self) -> None:
        for item in tuple(self._celdra_middle_items_v101.values()):
            self._draw_personality_hatchling_v96(item, None)

    def _chaos_position_v106(
        self,
        name: str,
        item: dict[str, Any],
        phase: int,
        width: int,
        height: int,
        item_width: int,
        item_height: int,
    ) -> tuple[float, float, bool]:
        left, top = 2.0, 2.0
        right = max(left, float(width - item_width - 2))
        bottom = max(top, float(height - item_height - 2))
        index = int(item.get("index") or 0)
        x = float(item.get("x") or left)
        y = float(item.get("y") or top)
        vx = float(item.get("vx") or 1.0)
        vy = float(item.get("vy") or 1.0)
        visible = True
        t = phase * 0.08 + index * 0.73

        if name == "LOOP":
            x = (left + right) / 2 + math.cos(t) * (right - left) * 0.39
            y = (top + bottom) / 2 + math.sin(t * 1.13) * (bottom - top) * 0.34
        elif name == "PING":
            x += vx * 1.7
            y = bottom - abs(math.sin(t * 2.7)) * min(72.0, bottom - top)
        elif name == "HEX":
            x += vx * 1.25
            y = round(y / 20.0) * 20.0
            if phase % 31 == 0:
                vx, vy = -vy, vx
        elif name == "CACHE":
            target_x, target_y = right * 0.82, bottom * 0.78
            x += (target_x - x) * 0.05 + math.sin(t) * 1.2
            y += (target_y - y) * 0.05 + math.cos(t * 1.2) * 0.9
        elif name == "PATCH":
            x += vx * 0.75
            y = top + (bottom - top) * 0.34 + math.sin(t * 2.0) * 10
        elif name == "ROOT":
            x += ((left + right) / 2 - x) * 0.025 + vx * 0.45
            y += ((top + bottom) / 2 - y) * 0.025 + vy * 0.45
        elif name == "NULL":
            cycle = (phase + index * 9) % 84
            visible = cycle > 12
            if cycle == 13:
                rng = random.Random(phase * 1009 + index)
                x, y = rng.uniform(left, right), rng.uniform(top, bottom)
        elif name == "GLITCH":
            x += vx + (10 if phase % 13 == 0 else -7 if phase % 19 == 0 else 0)
            y += vy + (-8 if phase % 17 == 0 else 5 if phase % 23 == 0 else 0)
        else:
            x += vx
            y += vy

        if x <= left or x >= right:
            vx = -vx
            x = max(left, min(right, x))
        if y <= top or y >= bottom:
            vy = -vy
            y = max(top, min(bottom, y))
        item["vx"], item["vy"] = vx, vy
        return x, y, visible

    def _start_middle_animation_v101(self) -> None:
        if self._celdra_middle_after_v101 is not None:
            return

        def tick() -> None:
            self._celdra_middle_after_v101 = None
            if not self._gremlin_stage_enabled_v106 or not self._celdra_middle_items_v101:
                return
            canvas = self._ensure_shared_scene_v106()
            if canvas is None:
                return
            self._celdra_middle_phase_v101 += 1
            phase = self._celdra_middle_phase_v101
            try:
                width = max(260, canvas.winfo_width())
                height = max(240, canvas.winfo_height())
            except tk.TclError:
                return
            mode = str(self._celdra_middle_mode_v101 or "roster")
            for name, item in tuple(self._celdra_middle_items_v101.items()):
                item["phase"] = int(item.get("phase") or 0) + 1
                item_width = int(item.get("width") or 82)
                item_height = int(item.get("height") or 88)
                index = int(item.get("index") or 0)
                visible = True
                mood = "idle"
                if mode == "stable":
                    x, y, visible = self._stable_position_v103(
                        name,
                        item,
                        phase,
                        width,
                        height,
                        item_width,
                        item_height,
                    )
                elif mode == "chaos":
                    x, y, visible = self._chaos_position_v106(
                        name,
                        item,
                        phase,
                        width,
                        height,
                        item_width,
                        item_height,
                    )
                    mood = "chaos"
                elif mode == "depart":
                    x = float(item.get("x") or 0.0) + (-1 if index % 2 == 0 else 1) * (5.0 + index * 0.28)
                    y = float(item.get("y") or 0.0) + math.sin(phase * 0.32 + index) * 2.4
                else:
                    x, y = self._grid_position_v101(index, width, height, item_width, item_height)
                    mood = "attention" if mode == "attention" else "idle"
                item.update(x=float(x), y=float(y), mood=mood)
                tag = str(item.get("tag_v106") or "")
                try:
                    canvas.itemconfigure(tag, state="normal" if visible else "hidden")
                except tk.TclError:
                    continue
                if not visible:
                    continue
                old_x = float(item.get("drawn_x_v106") or x)
                old_y = float(item.get("drawn_y_v106") or y)
                redraw = (
                    not canvas.find_withtag(tag)
                    or phase % self.GREMLIN_REDRAW_EVERY_V106 == 0
                    or str(item.get("drawn_mood_v106") or "") != mood
                )
                if redraw:
                    self._draw_personality_hatchling_v96(item, None)
                else:
                    try:
                        canvas.move(tag, float(x) - old_x, float(y) - old_y)
                        item["drawn_x_v106"] = float(x)
                        item["drawn_y_v106"] = float(y)
                    except tk.TclError:
                        self._draw_personality_hatchling_v96(item, None)
            self._update_middle_header_v101()
            self._celdra_middle_after_v101 = self.after(
                max(120, self._scaled_runtime_ms_v88(self.GREMLIN_TICK_MS_V106)),
                tick,
            )

        self._celdra_middle_after_v101 = self.after(80, tick)

    # ------------------------------------------------------------------
    # Directed visibility. Persistent memory no longer opens the stable at
    # startup; the scene is revealed only when the introduction event fires.
    # ------------------------------------------------------------------
    def _hide_middle_scene_v106(self) -> None:
        self._cancel_middle_animation_v101()
        self._clear_middle_items_v101()
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        pane = getattr(self, "celdra_visual_split_v50", None)
        if frame is not None and pane is not None:
            try:
                if str(frame) in tuple(str(value) for value in pane.panes()):
                    pane.forget(frame)
            except (AttributeError, tk.TclError):
                pass
        self._celdra_middle_hidden_v103 = True

    def _show_middle_scene_v106(self, mode: str) -> None:
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if frame is not None and bool(getattr(self, "_celdra_middle_hidden_v103", False)):
            self._show_middle_after_chaos_v103(mode)
        else:
            self._ensure_middle_panel_v101(mode)
        self._celdra_middle_mode_v101 = str(mode or "roster")
        self._celdra_middle_hidden_v103 = False
        self._ensure_shared_scene_v106()

    def _settle_v106_startup(self) -> None:
        self._destroy_internal_chaos_v103()
        self._cancel_stable_status_v103()
        self._gremlin_stage_enabled_v106 = False
        self._gremlin_intro_started_v106 = False
        self._celdra_stable_reveal_v103 = False
        self._hide_middle_scene_v106()

    def _install_gremlin_stable_v101(self) -> None:
        if not self._gremlin_stage_enabled_v106 or not self._gremlin_intro_started_v106:
            return
        super()._install_gremlin_stable_v101()

    def _start_placeholder_runtime_v70(self) -> None:
        super()._start_placeholder_runtime_v70()
        if not self._gremlin_intro_started_v106:
            self._celdra_stable_reveal_v103 = False
            self._hide_middle_scene_v106()

    def _start_celdra_session_v49(self, first_scan: bool) -> None:
        self._gremlin_schedule_generation_v106 += 1
        self._gremlin_stage_enabled_v106 = False
        self._gremlin_intro_started_v106 = False
        self._celdra_stable_reveal_v103 = False
        self._hide_middle_scene_v106()
        super()._start_celdra_session_v49(first_scan)
        self._celdra_stable_reveal_v103 = False
        self._hide_middle_scene_v106()
        self._append_console_v49(
            "[CORE] GREMLIN DIRECTOR V106 // DORMANT UNTIL INTRODUCTION // SHARED-CANVAS RENDERER"
        )

    def _schedule_gremlin_v94(self, delay_ms: int, callback: Callable[[], None]) -> None:
        generation = self._gremlin_schedule_generation_v106
        holder: dict[str, str] = {}

        def run() -> None:
            identifier = holder.get("id")
            if identifier:
                self._celdra_gremlin_after_v94.discard(identifier)
            if generation != self._gremlin_schedule_generation_v106:
                return
            if callback == self._start_gremlin_show_v94:
                if (
                    not bool(getattr(self, "_celdra_session_active_v49", False))
                    or bool(getattr(self, "_celdra_pipeline_success_v70", False))
                    or bool(getattr(self, "_celdra_pipeline_failed_v87", False))
                ):
                    return
                callback()
                return
            if bool(getattr(self, "_celdra_gremlin_active_v94", False)):
                callback()

        identifier = self.after(self._scaled_runtime_ms_v88(delay_ms), run)
        holder["id"] = identifier
        self._celdra_gremlin_after_v94.add(identifier)

    def _start_gremlin_show_v94(self) -> None:
        if (
            bool(getattr(self, "_celdra_gremlin_active_v94", False))
            or not bool(getattr(self, "_celdra_intro_gate_open_v99", False))
            or bool(getattr(self, "_celdra_pipeline_success_v70", False))
            or bool(getattr(self, "_celdra_pipeline_failed_v87", False))
        ):
            return
        self._gremlin_stage_enabled_v106 = True
        self._gremlin_intro_started_v106 = True
        self._celdra_stable_reveal_v103 = True
        self._show_middle_scene_v106("roster")
        super()._start_gremlin_show_v94()

    def _begin_internal_chaos_v101(self) -> None:
        # Deliberately bypass V103's nine Toplevel-window swarm. V101 already
        # owns the complete scene timing and harmless UI gags; our shared canvas
        # supplies the motion without opaque window rectangles or redraw storms.
        PublicFragmenterAppV101._begin_internal_chaos_v101(self)

    def _cancel_internal_show_v101(self) -> None:
        self._gremlin_schedule_generation_v106 += 1
        self._destroy_internal_chaos_v103()
        self._restore_gremlin_ui_v99()
        self._cancel_stable_status_v103()
        self._gremlin_stage_enabled_v106 = False
        self._celdra_stable_reveal_v103 = False
        self._celdra_yell_mode_v101 = False
        self._celdra_internal_show_v101 = False
        self._celdra_gremlin_active_v94 = False
        self._celdra_single_visit_v99 = False
        self._celdra_roster_visible_v101.clear()
        self._celdra_gremlin_token_v94 += 1
        self._hide_middle_scene_v106()

    def _end_celdra_session_v49(self) -> None:
        super()._end_celdra_session_v49()
        if not self._gremlin_intro_started_v106:
            self._gremlin_stage_enabled_v106 = False
            self._celdra_stable_reveal_v103 = False
            self._hide_middle_scene_v106()

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        intro_started = self._gremlin_intro_started_v106
        super()._run_all_done(result, error)
        if not intro_started:
            self._gremlin_stage_enabled_v106 = False
            self._celdra_stable_reveal_v103 = False
            self._hide_middle_scene_v106()

    # ------------------------------------------------------------------
    # Rare external visitors still use a keyed window, but it is prepared
    # offscreen and never shown as an opaque fallback when transparency fails.
    # ------------------------------------------------------------------
    def _create_gremlin_window_v99(
        self,
        index: int,
        personality: dict[str, Any],
        x: int,
        y: int,
    ) -> dict[str, Any]:
        shape = str(personality.get("shape") or "round")
        art_width, art_height = {
            "fat": (96, 78),
            "tall": (70, 104),
            "petite": (72, 78),
            "wide": (94, 78),
            "broad": (92, 84),
            "small": (66, 70),
            "jagged": (82, 84),
            "springy": (78, 92),
        }.get(shape, (82, 84))
        name = str(personality.get("name") or "").upper()
        pad_x = 24 if name in {"BYTE", "CACHE", "PATCH", "ROOT"} else 16
        width, height = art_width + pad_x, art_height + 10
        holder = tk.Toplevel(self)
        holder.withdraw()
        holder.overrideredirect(True)
        holder.geometry(f"{width}x{height}-10000-10000")
        transparent = self.EXTERNAL_TRANSPARENT_KEY_V106
        holder.configure(background=transparent)
        transparency_supported = False
        try:
            holder.transient(self)
            holder.attributes("-topmost", False)
            holder.update_idletasks()
            holder.wm_attributes("-transparentcolor", transparent)
            transparency_supported = True
        except tk.TclError:
            transparency_supported = False
        canvas = tk.Canvas(
            holder,
            width=width,
            height=height,
            background=transparent,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill="both", expand=True)
        item = {
            "index": index,
            "holder": holder,
            "canvas": canvas,
            "x": float(x),
            "y": float(y),
            "width": width,
            "height": height,
            "art_width": art_width,
            "art_height": art_height,
            "art_offset_x": pad_x // 2,
            "art_offset_y": 5,
            "sequence": self._personality_sequence_v96(str(personality.get("temperament") or "idle")),
            "frame": index,
            "phase": index,
            "personality": dict(personality),
            "transparent": transparent,
            "transparent_supported_v106": transparency_supported,
        }
        self._draw_personality_hatchling_v96(item, None)
        self._record_gremlin_seen_v99(name)

        def reveal() -> None:
            try:
                if not holder.winfo_exists():
                    return
            except tk.TclError:
                return
            if not transparency_supported:
                try:
                    holder.destroy()
                except tk.TclError:
                    pass
                self._append_console_v49(
                    f"[CORE] {name or 'GREMLIN'} EXTERNAL VISITOR SUPPRESSED // TRANSPARENTCOLOR UNAVAILABLE"
                )
                return
            self._place_gremlin_window_v99(item, x, y)
            try:
                holder.deiconify()
                holder.lift()
            except tk.TclError:
                pass

        self.after_idle(reveal)
        return item

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V106"
            metadata["gremlin_startup_visibility"] = "hidden_until_introduction_event"
            metadata["gremlin_internal_renderer"] = "single_shared_canvas"
            metadata["gremlin_main_chaos_windows"] = 0
            metadata["gremlin_motion_tick_ms_minimum"] = 120
            metadata["gremlin_vector_redraw_every_ticks"] = self.GREMLIN_REDRAW_EVERY_V106
            metadata["external_gremlin_opaque_fallback"] = False
            metadata["run_all_progress_rebuild_after_workspace_install"] = True
        return payload

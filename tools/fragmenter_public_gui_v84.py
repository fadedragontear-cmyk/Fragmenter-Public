#!/usr/bin/env python3
"""V84: complete visual-event timeline and a seekable bottom-right mini player."""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_authoring_post_breakpoint_v1 import BREAKPOINT_MS, extend_with_post_breakpoint
from celdra_authoring_project_v1 import normalize_events
from celdra_authoring_visual_events_v1 import ENERGY_FRAME_MS, ENERGY_START_MS, extend_with_visual_events
from celdra_evolution_pixel_v4 import CELDRA_BLUE_PALETTE, EVOLUTION_PHASES
from fragmenter_public_gui_v83 import PublicFragmenterAppV83


class PublicFragmenterAppV84(PublicFragmenterAppV83):
    """Expose every visual transition and make the timeline directly scrubbable."""

    MINI_LAYOUT_ACTIONS = {"window", "move", "pose", "avatar", "asset", "bubble", "chat"}

    def __init__(self) -> None:
        self._celdra_timeline_summary_v84: tk.StringVar | None = None
        self._celdra_mini_canvas_v84: tk.Canvas | None = None
        self._celdra_mini_scale_v84: ttk.Scale | None = None
        self._celdra_mini_time_var_v84: tk.DoubleVar | None = None
        self._celdra_mini_speed_var_v84: tk.DoubleVar | None = None
        self._celdra_mini_status_v84: tk.StringVar | None = None
        self._celdra_mini_pause_text_v84: tk.StringVar | None = None
        self._celdra_mini_after_v84: str | None = None
        self._celdra_mini_playing_v84 = False
        self._celdra_mini_paused_v84 = False
        self._celdra_mini_scale_guard_v84 = False
        self._celdra_mini_tree_guard_v84 = False
        self._celdra_mini_playhead_ms_v84 = 0.0
        self._celdra_mini_start_ms_v84 = 0.0
        self._celdra_mini_start_wall_v84 = 0.0
        self._celdra_mini_active_event_v84 = ""
        self._celdra_mini_refs_v84: list[tk.PhotoImage] = []
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Timeline Sequencer")
        self._ensure_complete_author_events_v84()
        self.after_idle(self._finish_timeline_install_v84)

    # ------------------------------------------------------------------
    # Complete event model: canonical + user rows + hidden runtime + visual rows.
    # ------------------------------------------------------------------
    def _ensure_complete_author_events_v84(self) -> None:
        rows = extend_with_post_breakpoint(self._celdra_author_events_v74)
        self._celdra_author_events_v74 = extend_with_visual_events(rows)
        self._celdra_author_event_serial_v74 = max(
            self._celdra_author_event_serial_v74,
            len(self._celdra_author_events_v74),
        )

    def _apply_author_project_payload_v74(self, payload: dict[str, Any]) -> None:
        super()._apply_author_project_payload_v74(payload)
        self._ensure_complete_author_events_v84()
        self._refresh_author_event_tree_v74()

    def _reset_canonical_events_v74(self) -> None:
        super()._reset_canonical_events_v74()
        self._ensure_complete_author_events_v84()
        self._refresh_author_event_tree_v74()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        self._ensure_complete_author_events_v84()
        payload = super()._author_project_payload_v74()
        payload["events"] = normalize_events(self._celdra_author_events_v74)
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V84"
            metadata["explicit_visual_events"] = True
            metadata["timeline_mini_player"] = True
        return payload

    # ------------------------------------------------------------------
    # Keep the existing editor but add a compact player beneath the inspector.
    # ------------------------------------------------------------------
    def _build_author_timeline_tab_v74(self, parent: ttk.Frame) -> None:
        super()._build_author_timeline_tab_v74(parent)
        self._install_timeline_mini_player_v84()

    def _install_timeline_mini_player_v84(self) -> None:
        tree = self._celdra_author_event_tree_v74
        if tree is None:
            return
        tree_frame = tree.master
        paned = tree_frame.master
        inspector: ttk.LabelFrame | None = None
        for child in paned.winfo_children():
            if not isinstance(child, ttk.LabelFrame):
                continue
            try:
                if str(child.cget("text")) == "Selected event":
                    inspector = child
                    break
            except tk.TclError:
                continue
        if inspector is None:
            return

        inspector.rowconfigure(0, weight=3)
        inspector.rowconfigure(1, weight=2, minsize=255)
        inspector.columnconfigure(0, weight=1)
        mini = ttk.LabelFrame(inspector, text="Timeline mini playback — click any event to seek", padding=4)
        mini.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        mini.rowconfigure(1, weight=1)
        mini.columnconfigure(0, weight=1)

        header = ttk.Frame(mini)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        header.columnconfigure(0, weight=1)
        self._celdra_timeline_summary_v84 = tk.StringVar(value="Loading complete timeline…")
        ttk.Label(header, textvariable=self._celdra_timeline_summary_v84).grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Jump eggplosion", command=self._jump_eggplosion_v84).grid(row=0, column=1, padx=2)
        ttk.Button(header, text="Jump past breakpoint", command=self._jump_post_breakpoint_v84).grid(row=0, column=2, padx=2)

        canvas = tk.Canvas(
            mini,
            width=460,
            height=270,
            background="#081321",
            highlightthickness=1,
            highlightbackground="#35536f",
        )
        canvas.grid(row=1, column=0, sticky="nsew")
        canvas.bind("<Configure>", lambda _event: self.after_idle(self._render_timeline_mini_v84))
        self._celdra_mini_canvas_v84 = canvas

        transport = ttk.Frame(mini)
        transport.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        for column in range(8):
            transport.columnconfigure(column, weight=1 if column in {5, 6} else 0)
        ttk.Button(transport, text="◀ Event", command=lambda: self._mini_step_event_v84(-1)).grid(row=0, column=0, padx=1)
        ttk.Button(transport, text="Play selected", command=self._mini_play_selected_v84).grid(row=0, column=1, padx=1)
        self._celdra_mini_pause_text_v84 = tk.StringVar(value="Pause")
        ttk.Button(
            transport,
            textvariable=self._celdra_mini_pause_text_v84,
            command=self._mini_pause_resume_v84,
        ).grid(row=0, column=2, padx=1)
        ttk.Button(transport, text="Stop", command=self._mini_stop_v84).grid(row=0, column=3, padx=1)
        ttk.Button(transport, text="Event ▶", command=lambda: self._mini_step_event_v84(1)).grid(row=0, column=4, padx=1)

        self._celdra_mini_time_var_v84 = tk.DoubleVar(value=0.0)
        scale = ttk.Scale(
            transport,
            from_=0.0,
            to=600_000.0,
            variable=self._celdra_mini_time_var_v84,
            command=self._mini_scrub_command_v84,
        )
        scale.grid(row=0, column=5, columnspan=2, sticky="ew", padx=5)
        self._celdra_mini_scale_v84 = scale

        ttk.Label(transport, text="Speed").grid(row=1, column=0, sticky="e", pady=(3, 0))
        self._celdra_mini_speed_var_v84 = tk.DoubleVar(value=1.0)
        ttk.Combobox(
            transport,
            textvariable=self._celdra_mini_speed_var_v84,
            values=(0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0),
            state="readonly",
            width=6,
        ).grid(row=1, column=1, sticky="w", pady=(3, 0))
        self._celdra_mini_status_v84 = tk.StringVar(value="Stopped at 00:00.000")
        ttk.Label(transport, textvariable=self._celdra_mini_status_v84).grid(
            row=1,
            column=2,
            columnspan=6,
            sticky="w",
            padx=(6, 0),
            pady=(3, 0),
        )

        tree.bind("<Double-1>", lambda _event: self.after_idle(self._mini_play_selected_v84), add="+")
        self._refresh_author_event_tree_v74()
        self.after_idle(lambda: self._mini_seek_v84(0.0))

    def _finish_timeline_install_v84(self) -> None:
        self._ensure_complete_author_events_v84()
        self._refresh_author_event_tree_v74()
        self._mini_seek_v84(self._celdra_mini_playhead_ms_v84)

    # ------------------------------------------------------------------
    # Tree adds a viewport column and visible row classes.
    # ------------------------------------------------------------------
    def _refresh_author_event_tree_v74(self, *, select_id: str = "") -> None:
        self._ensure_complete_author_events_v84()
        tree = self._celdra_author_event_tree_v74
        if tree is None:
            return
        if not select_id:
            selected = tree.selection()
            select_id = str(selected[0]) if selected else ""

        columns = ("time", "sequence", "action", "asset", "viewport", "branch", "text")
        try:
            tree.configure(columns=columns)
            for key, heading, width, stretch in (
                ("time", "At ms", 78, False),
                ("sequence", "Sequence", 105, False),
                ("action", "Action", 92, False),
                ("asset", "Asset", 116, True),
                ("viewport", "View %", 62, False),
                ("branch", "IF / OR split", 170, True),
                ("text", "Text / payload", 310, True),
            ):
                tree.heading(key, text=heading)
                tree.column(key, width=width, stretch=stretch)
            tree.tag_configure("window", background="#102b3c", foreground="#9ee8ff")
            tree.tag_configure("runtime", background="#1b1830", foreground="#d8c8ff")
            tree.tag_configure("condition", background="#2b2036", foreground="#efc8ff")
            tree.tag_configure("breakpoint", background="#402126", foreground="#ffb6bc")
        except tk.TclError:
            return

        tree.delete(*tree.get_children())
        self._celdra_author_event_rows_v74.clear()
        rows = normalize_events(self._celdra_author_events_v74)
        for row in rows:
            event_id = str(row.get("id") or "")
            action = str(row.get("action") or "")
            condition = str(row.get("condition") or "")
            branch = ""
            if condition:
                branch = f"IF {condition} → {row.get('true_sequence') or '—'} / {row.get('false_sequence') or '—'}"
            viewport = f"{int(row.get('window_percent') or 0)}%" if action in self.MINI_LAYOUT_ACTIONS else "—"
            tags: list[str] = []
            if action == "window":
                tags.append("window")
            if event_id.startswith("runtime-"):
                tags.append("runtime")
            if action == "condition":
                tags.append("condition")
            if action == "breakpoint":
                tags.append("breakpoint")
            tree.insert(
                "",
                "end",
                iid=event_id,
                values=(
                    row.get("at_ms"),
                    row.get("sequence"),
                    action,
                    row.get("asset"),
                    viewport,
                    branch,
                    str(row.get("text") or "").replace("\n", " ↵ ")[:220],
                ),
                tags=tuple(tags),
            )
            self._celdra_author_event_rows_v74[event_id] = row

        if select_id and tree.exists(select_id):
            tree.selection_set(select_id)
            tree.see(select_id)

        end_ms = self._timeline_end_v84(rows)
        after_break = sum(1 for row in rows if int(row.get("at_ms") or 0) > BREAKPOINT_MS)
        windows = sum(1 for row in rows if str(row.get("action") or "") == "window")
        if self._celdra_timeline_summary_v84 is not None:
            self._celdra_timeline_summary_v84.set(
                f"{len(rows)} events • {after_break} after breakpoint • {windows} viewport events • end {end_ms / 1000:.2f}s"
            )
        if self._celdra_mini_scale_v84 is not None:
            try:
                self._celdra_mini_scale_v84.configure(to=max(1.0, float(end_ms)))
            except tk.TclError:
                pass

    def _load_selected_author_event_v74(self, event: tk.Event | None = None) -> None:
        super()._load_selected_author_event_v74(event)
        if self._celdra_mini_tree_guard_v84:
            return
        row = self._celdra_author_event_rows_v74.get(self._selected_author_event_id_v74())
        if row is None:
            return
        self._mini_stop_v84(keep_status=True)
        self._mini_seek_v84(float(row.get("at_ms") or 0))

    # ------------------------------------------------------------------
    # State reconstruction at any timeline timestamp.
    # ------------------------------------------------------------------
    @staticmethod
    def _timeline_end_v84(rows: list[dict[str, Any]]) -> int:
        return max(
            (
                int(row.get("at_ms") or 0) + max(0, int(row.get("duration_ms") or 0))
                for row in rows
            ),
            default=0,
        )

    def _timeline_state_at_v84(self, target_ms: float) -> tuple[dict[str, Any], str]:
        state: dict[str, Any] = {
            "asset": "egg_wait",
            "visible": False,
            "x": 0,
            "y": 0,
            "scale": 100,
            "window_percent": 56,
            "bubble_style": "Rounded blue",
            "bubble_x": 4,
            "bubble_y": 3,
            "bubble_width": 52,
            "bubble_text": "",
            "console_lines": [],
            "status": "",
            "glitch_level": 0,
            "instability": False,
            "energy_start": -1,
            "time_ms": float(target_ms),
        }
        active_branch = ""
        active_id = ""
        rows = normalize_events(row for row in self._celdra_author_events_v74 if row.get("enabled", True))
        for row in rows:
            at_ms = int(row.get("at_ms") or 0)
            if at_ms > target_ms:
                break
            sequence = str(row.get("sequence") or "main")
            if sequence != "main" and sequence != active_branch:
                continue
            action = str(row.get("action") or "console").casefold()
            text = str(row.get("text") or "")
            speaker = str(row.get("speaker") or "")
            asset = str(row.get("asset") or "")
            active_id = str(row.get("id") or active_id)

            if action == "condition":
                result = self._evaluate_author_condition_v74(str(row.get("condition") or ""))
                active_branch = str(row.get("true_sequence") if result else row.get("false_sequence") or "")
                state["console_lines"].append(
                    f"[BRANCH] {row.get('condition') or '(blank)'} → {'TRUE' if result else 'FALSE'}"
                )
                continue
            if action == "show_avatar":
                state["visible"] = True
            elif action == "hide_avatar":
                state["visible"] = False
                state["bubble_text"] = ""
            elif action == "window":
                state["window_percent"] = int(row.get("window_percent") or state["window_percent"])
            elif action in {"pose", "avatar", "asset", "move"}:
                if asset:
                    state["asset"] = asset
                state["visible"] = True
                state["x"] = int(row.get("x") or 0)
                state["y"] = int(row.get("y") or 0)
                state["scale"] = int(row.get("scale") or 100)
                state["window_percent"] = int(row.get("window_percent") or state["window_percent"])
                if text:
                    state["bubble_text"] = text
                    state["bubble_style"] = str(row.get("bubble_style") or state["bubble_style"])
                    state["bubble_x"] = int(row.get("bubble_x") or state["bubble_x"])
                    state["bubble_y"] = int(row.get("bubble_y") or state["bubble_y"])
                    state["bubble_width"] = int(row.get("bubble_width") or state["bubble_width"])
            elif action in {"bubble", "chat"}:
                if asset:
                    state["asset"] = asset
                    state["visible"] = True
                state["bubble_text"] = text
                state["bubble_style"] = str(row.get("bubble_style") or state["bubble_style"])
                state["bubble_x"] = int(row.get("bubble_x") or state["bubble_x"])
                state["bubble_y"] = int(row.get("bubble_y") or state["bubble_y"])
                state["bubble_width"] = int(row.get("bubble_width") or state["bubble_width"])
            elif action == "hide_dialogue":
                state["bubble_text"] = ""
            elif action == "egg_glitch":
                try:
                    state["glitch_level"] = max(state["glitch_level"], int(text or 0))
                except ValueError:
                    pass
            elif action == "energy_hatch":
                state["energy_start"] = at_ms
                state["visible"] = True
            elif action == "status":
                state["status"] = text
                state["console_lines"].append(f"[{speaker}] {text}" if speaker else text)
            elif action == "console":
                line = f"[{speaker}] {text}" if speaker else text
                state["console_lines"].append(line)
                if "INSTABILITY DETECTED" in text.upper():
                    state["instability"] = True
            elif action == "ascii":
                state["visible"] = True
                state["asset"] = "egg_wait"

            if len(state["console_lines"]) > 24:
                state["console_lines"] = state["console_lines"][-24:]

        energy_start = int(state.get("energy_start") or -1)
        state["energy_active"] = energy_start >= 0 and energy_start <= target_ms < 169_000
        state["energy_elapsed"] = max(0, int(target_ms) - energy_start) if energy_start >= 0 else 0
        return state, active_id

    # ------------------------------------------------------------------
    # Mini transport.
    # ------------------------------------------------------------------
    def _mini_scrub_command_v84(self, value: str) -> None:
        if self._celdra_mini_scale_guard_v84:
            return
        try:
            target = float(value)
        except (TypeError, ValueError):
            return
        self._mini_stop_v84(keep_status=True)
        self._mini_seek_v84(target)

    def _mini_seek_v84(self, target_ms: float, *, sync_tree: bool = False) -> None:
        rows = normalize_events(self._celdra_author_events_v74)
        end_ms = self._timeline_end_v84(rows)
        target = max(0.0, min(float(end_ms), float(target_ms)))
        self._celdra_mini_playhead_ms_v84 = target
        state, active_id = self._timeline_state_at_v84(target)
        self._celdra_mini_active_event_v84 = active_id
        if self._celdra_mini_time_var_v84 is not None:
            self._celdra_mini_scale_guard_v84 = True
            try:
                self._celdra_mini_time_var_v84.set(target)
            finally:
                self._celdra_mini_scale_guard_v84 = False
        self._render_timeline_mini_v84(state)
        if self._celdra_mini_status_v84 is not None:
            mode = "Playing" if self._celdra_mini_playing_v84 else "Paused" if self._celdra_mini_paused_v84 else "Stopped"
            self._celdra_mini_status_v84.set(f"{mode} at {self._format_time_v84(target)} • {active_id or 'before first event'}")
        if sync_tree and active_id:
            tree = self._celdra_author_event_tree_v74
            if tree is not None and tree.exists(active_id):
                self._celdra_mini_tree_guard_v84 = True
                try:
                    tree.selection_set(active_id)
                    tree.see(active_id)
                finally:
                    self._celdra_mini_tree_guard_v84 = False

    @staticmethod
    def _format_time_v84(milliseconds: float) -> str:
        total = max(0, int(milliseconds))
        minutes, remainder = divmod(total, 60_000)
        seconds, millis = divmod(remainder, 1_000)
        return f"{minutes:02d}:{seconds:02d}.{millis:03d}"

    def _mini_play_selected_v84(self) -> None:
        row = self._celdra_author_event_rows_v74.get(self._selected_author_event_id_v74())
        if row is not None:
            self._mini_seek_v84(float(row.get("at_ms") or 0))
        self._mini_start_playback_v84()

    def _mini_start_playback_v84(self) -> None:
        rows = normalize_events(self._celdra_author_events_v74)
        end_ms = self._timeline_end_v84(rows)
        if self._celdra_mini_playhead_ms_v84 >= end_ms:
            self._mini_seek_v84(0.0)
        self._mini_cancel_after_v84()
        self._celdra_mini_playing_v84 = True
        self._celdra_mini_paused_v84 = False
        self._celdra_mini_start_ms_v84 = self._celdra_mini_playhead_ms_v84
        self._celdra_mini_start_wall_v84 = time.monotonic()
        if self._celdra_mini_pause_text_v84 is not None:
            self._celdra_mini_pause_text_v84.set("Pause")
        self._mini_tick_v84()

    def _mini_tick_v84(self) -> None:
        self._celdra_mini_after_v84 = None
        if not self._celdra_mini_playing_v84:
            return
        try:
            speed = max(0.05, float(self._celdra_mini_speed_var_v84.get())) if self._celdra_mini_speed_var_v84 else 1.0
        except (tk.TclError, TypeError, ValueError):
            speed = 1.0
        elapsed = (time.monotonic() - self._celdra_mini_start_wall_v84) * 1000.0 * speed
        target = self._celdra_mini_start_ms_v84 + elapsed
        end_ms = self._timeline_end_v84(normalize_events(self._celdra_author_events_v74))
        if target >= end_ms:
            self._celdra_mini_playing_v84 = False
            self._celdra_mini_paused_v84 = False
            self._mini_seek_v84(float(end_ms), sync_tree=True)
            if self._celdra_mini_status_v84 is not None:
                self._celdra_mini_status_v84.set(f"Playback complete at {self._format_time_v84(end_ms)}")
            return
        self._mini_seek_v84(target, sync_tree=True)
        self._celdra_mini_after_v84 = self.after(33, self._mini_tick_v84)

    def _mini_pause_resume_v84(self) -> None:
        if self._celdra_mini_playing_v84:
            self._mini_cancel_after_v84()
            self._celdra_mini_playing_v84 = False
            self._celdra_mini_paused_v84 = True
            if self._celdra_mini_pause_text_v84 is not None:
                self._celdra_mini_pause_text_v84.set("Resume")
            self._mini_seek_v84(self._celdra_mini_playhead_ms_v84)
            return
        if self._celdra_mini_paused_v84:
            self._mini_start_playback_v84()
            return
        self._mini_start_playback_v84()

    def _mini_stop_v84(self, *, keep_status: bool = False) -> None:
        self._mini_cancel_after_v84()
        self._celdra_mini_playing_v84 = False
        self._celdra_mini_paused_v84 = False
        if self._celdra_mini_pause_text_v84 is not None:
            self._celdra_mini_pause_text_v84.set("Pause")
        if not keep_status and self._celdra_mini_status_v84 is not None:
            self._celdra_mini_status_v84.set(f"Stopped at {self._format_time_v84(self._celdra_mini_playhead_ms_v84)}")

    def _mini_cancel_after_v84(self) -> None:
        if self._celdra_mini_after_v84 is None:
            return
        try:
            self.after_cancel(self._celdra_mini_after_v84)
        except tk.TclError:
            pass
        self._celdra_mini_after_v84 = None

    def _mini_step_event_v84(self, direction: int) -> None:
        rows = normalize_events(self._celdra_author_events_v74)
        if not rows:
            return
        current = self._celdra_mini_playhead_ms_v84
        if direction < 0:
            candidates = [row for row in rows if int(row.get("at_ms") or 0) < current - 0.5]
            row = candidates[-1] if candidates else rows[0]
        else:
            candidates = [row for row in rows if int(row.get("at_ms") or 0) > current + 0.5]
            row = candidates[0] if candidates else rows[-1]
        event_id = str(row.get("id") or "")
        tree = self._celdra_author_event_tree_v74
        if tree is not None and event_id and tree.exists(event_id):
            tree.selection_set(event_id)
            tree.see(event_id)
        self._mini_seek_v84(float(row.get("at_ms") or 0))

    def _jump_eggplosion_v84(self) -> None:
        self._jump_to_event_v84("visual-energy-window-01")

    def _jump_post_breakpoint_v84(self) -> None:
        rows = normalize_events(self._celdra_author_events_v74)
        target = next((row for row in rows if int(row.get("at_ms") or 0) > BREAKPOINT_MS), None)
        if target is not None:
            self._jump_to_event_v84(str(target.get("id") or ""))

    def _jump_to_event_v84(self, event_id: str) -> None:
        tree = self._celdra_author_event_tree_v74
        row = self._celdra_author_event_rows_v74.get(event_id)
        if tree is None or row is None or not tree.exists(event_id):
            return
        tree.selection_set(event_id)
        tree.see(event_id)
        self._mini_seek_v84(float(row.get("at_ms") or 0))

    # ------------------------------------------------------------------
    # Compact production-like renderer.
    # ------------------------------------------------------------------
    def _render_timeline_mini_v84(self, state: dict[str, Any] | None = None) -> None:
        canvas = self._celdra_mini_canvas_v84
        if canvas is None:
            return
        if state is None:
            state, _active = self._timeline_state_at_v84(self._celdra_mini_playhead_ms_v84)
        width = max(420, canvas.winfo_width())
        height = max(245, canvas.winfo_height())
        stage_width = max(115, min(width - 120, round(width * max(10, min(99, int(state["window_percent"]))) / 100.0)))
        canvas.delete("all")
        self._celdra_mini_refs_v84.clear()
        canvas.create_rectangle(0, 0, stage_width, height, fill="#081321", outline="")
        canvas.create_rectangle(stage_width, 0, width, height, fill="#10151d", outline="")
        canvas.create_rectangle(0, 0, stage_width, 30, fill="#0d2035", outline="")
        canvas.create_text(
            7,
            7,
            text=f"CELDRA {state['window_percent']}% • {self._format_time_v84(state['time_ms'])}",
            anchor="nw",
            fill="#d9f1ff",
            font=("Consolas", 8, "bold"),
        )
        canvas.create_line(stage_width, 0, stage_width, height, fill="#78b9ea", width=2)

        self._draw_mini_corruption_v84(canvas, stage_width, height, state)
        self._draw_mini_avatar_v84(canvas, stage_width, height, state)
        if state.get("energy_active"):
            self._draw_mini_energy_v84(canvas, stage_width, height, state)

        bubble_text = str(state.get("bubble_text") or "")
        if bubble_text:
            values = {
                "bubble_x": state["bubble_x"],
                "bubble_y": state["bubble_y"],
                "bubble_width": state["bubble_width"],
                "bubble_style": state["bubble_style"],
            }
            bounds = self._bubble_bounds_v81(stage_width, height, values, bubble_text)
            self._draw_bubble_style_v81(canvas, bounds, str(state["bubble_style"]), bubble_text)

        canvas.create_text(
            stage_width + 7,
            7,
            text="CONSOLE",
            anchor="nw",
            fill="#48d76d",
            font=("Consolas", 8, "bold"),
        )
        y = 25
        console_width = max(60, width - stage_width - 12)
        for line in list(state.get("console_lines") or [])[-10:]:
            folded = str(line).upper()
            fill = "#ff5964" if "[BRAIN]" in folded and "ERROR" in folded else "#8db1c8"
            item = canvas.create_text(
                stage_width + 7,
                y,
                text=str(line),
                anchor="nw",
                width=console_width,
                fill=fill,
                font=("Consolas", 6),
            )
            bounds = canvas.bbox(item)
            y = (bounds[3] + 2) if bounds else y + 14
            if y > height - 22:
                break
        canvas.create_text(
            width - 6,
            height - 5,
            text=f"stage {stage_width}px / console {width - stage_width}px",
            anchor="se",
            fill="#557c9e",
            font=("Consolas", 6),
        )

    def _draw_mini_avatar_v84(
        self,
        canvas: tk.Canvas,
        stage_width: int,
        height: int,
        state: dict[str, Any],
    ) -> None:
        if not state.get("visible"):
            return
        asset = str(state.get("asset") or "egg_wait").casefold()
        if state.get("energy_active"):
            elapsed = int(state.get("energy_elapsed") or 0)
            if elapsed >= 4 * ENERGY_FRAME_MS and elapsed < 44 * ENERGY_FRAME_MS:
                asset = "hatch_open"
            elif elapsed >= 44 * ENERGY_FRAME_MS:
                asset = "hatch_gif"
        if asset in getattr(self, "GENERATED_PREVIEW_PHASES", ()):
            self._draw_mini_generated_phase_v84(canvas, stage_width, height, asset, state)
            return
        photo = self._preview_photo_for_asset_v74(asset, max(10, min(500, int(state.get("scale") or 100))))
        if photo is None:
            return
        divisor = max(
            1,
            math.ceil(photo.width() / max(45, stage_width * 0.72)),
            math.ceil(photo.height() / max(65, height - 42)),
        )
        display = photo if divisor <= 1 else photo.subsample(divisor, divisor)
        self._celdra_mini_refs_v84.extend([photo, display])
        x = max(display.width() // 2 + 3, min(stage_width - display.width() // 2 - 3, stage_width // 2 + int(state.get("x") or 0)))
        y = height - 8 + int(state.get("y") or 0)
        canvas.create_image(x, y, image=display, anchor="s")

    def _draw_mini_generated_phase_v84(
        self,
        canvas: tk.Canvas,
        stage_width: int,
        height: int,
        phase: str,
        state: dict[str, Any],
    ) -> None:
        frames = EVOLUTION_PHASES.get(phase)
        if not frames:
            return
        rows = frames[0].rows
        columns = max((len(row) for row in rows), default=1)
        pixel = max(1, min((stage_width - 16) // max(1, columns), (height - 44) // max(1, len(rows))))
        pixel = min(pixel, max(1, round(3 * max(10, min(500, int(state.get("scale") or 100))) / 100.0)))
        art_width = columns * pixel
        art_height = len(rows) * pixel
        x0 = stage_width // 2 - art_width // 2 + int(state.get("x") or 0)
        y0 = height - 9 - art_height + int(state.get("y") or 0)
        for row_index, row in enumerate(rows):
            for column_index, symbol in enumerate(row):
                color = CELDRA_BLUE_PALETTE.get(symbol, "")
                if not color:
                    continue
                canvas.create_rectangle(
                    x0 + column_index * pixel,
                    y0 + row_index * pixel,
                    x0 + (column_index + 1) * pixel,
                    y0 + (row_index + 1) * pixel,
                    fill=color,
                    outline=color,
                )

    @staticmethod
    def _draw_mini_corruption_v84(
        canvas: tk.Canvas,
        stage_width: int,
        height: int,
        state: dict[str, Any],
    ) -> None:
        level = int(state.get("glitch_level") or 0)
        if level <= 0:
            return
        alarm = bool(state.get("instability"))
        colors = ("#5e1118", "#861923", "#aa202b", "#d0323d", "#f04a54") if alarm else (
            "#0a3b26",
            "#0d5734",
            "#117044",
            "#168956",
            "#35c982",
        )
        terms = ("AURA", "INFECTION", "MUTATION", "QUARANTINE", "SERENIAL", "CELDRA", "FRAGMENT", "CCSF")
        phase = int(float(state.get("time_ms") or 0) // 120)
        for slot in range(5 + level * 4):
            term = terms[(slot * 3 + phase) % len(terms)]
            text = term if slot % 3 == 0 else term[::-1] if slot % 3 == 1 else f"{(slot * 31 + phase) & 0xFF:02X}//{term}"
            x = 8 + ((slot * 53 + phase * (2 + slot % 3)) % max(20, stage_width - 16))
            y = 34 + ((slot * 37 + phase * (3 + slot % 4)) % max(25, height - 46))
            canvas.create_text(
                x,
                y,
                text=text,
                anchor="center",
                fill=colors[(slot + phase) % len(colors)],
                font=("Consolas", 5 + (slot % 3)),
            )

    @staticmethod
    def _draw_mini_energy_v84(
        canvas: tk.Canvas,
        stage_width: int,
        height: int,
        state: dict[str, Any],
    ) -> None:
        elapsed = int(state.get("energy_elapsed") or 0)
        cx = stage_width // 2
        cy = height // 2 + 12
        phase = elapsed / max(1, ENERGY_FRAME_MS)
        radius = 18 + min(95, phase * 2.8)
        for ray in range(18):
            angle = math.radians(ray * 20 + phase * 7)
            inner = radius * (0.28 + (ray % 4) * 0.04)
            outer = radius * (0.82 + (ray % 5) * 0.07)
            canvas.create_line(
                cx + math.cos(angle) * inner,
                cy + math.sin(angle) * inner,
                cx + math.cos(angle) * outer,
                cy + math.sin(angle) * outer,
                fill="#d9f6ff" if ray % 3 else "#6fdcff",
                width=1 + ray % 2,
            )
        canvas.create_text(
            cx,
            35,
            text=f"ENERGY HATCH • STEP {int(phase)}",
            anchor="n",
            fill="#d9f6ff",
            font=("Consolas", 7, "bold"),
        )
        if 44 * ENERGY_FRAME_MS <= elapsed < 5_200:
            canvas.create_rectangle(0, 0, stage_width, height, fill="#ffffff", outline="")
            canvas.create_text(
                cx,
                cy,
                text="WHITEOUT / GIF SWAP",
                fill="#4b6070",
                font=("Consolas", 7, "bold"),
            )

    def _stop_author_timeline_v74(self) -> None:
        super()._stop_author_timeline_v74()
        self._mini_stop_v84()

    def _cancel_celdra_cues_v49(self) -> None:
        self._mini_stop_v84(keep_status=True)
        super()._cancel_celdra_cues_v49()


def main() -> int:
    app = PublicFragmenterAppV84()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

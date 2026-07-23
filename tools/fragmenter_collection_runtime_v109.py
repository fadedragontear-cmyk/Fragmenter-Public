#!/usr/bin/env python3
"""V109 collectible Gremlin encounters, stable feed, and Celdra unlock tab."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Any

from celdra_gremlin_collection_v109 import (
    GREMLIN_CAPTURE_SKITS_V109,
    SERENIAL_DISCORD_INVITE_V109,
    SERENIAL_DISCORD_REDIRECT_V109,
    STABLE_MESSAGES_V109,
)
from celdra_gremlin_memory_v1 import KNOWN_GREMLINS
from celdra_gremlin_memory_v2 import (
    collection_complete,
    load_memory,
    mark_breakout_seen,
)
from celdra_v99_content import GREMLIN_PERSONALITIES


class FragmenterGremlinCollectionMixinV109:
    """Continue the Gremlin story after the main breakout and unlock Celdra at 9/9."""

    RANDOM_CAPTURE_INITIAL_MIN_MS_V109 = 32_000
    RANDOM_CAPTURE_INITIAL_MAX_MS_V109 = 58_000
    RANDOM_CAPTURE_MIN_MS_V109 = 48_000
    RANDOM_CAPTURE_MAX_MS_V109 = 105_000

    def __init__(self) -> None:
        self._gremlin_main_scene_complete_v109 = False
        self._gremlin_random_waiting_v109 = False
        self._gremlin_effect_widgets_v109: list[tk.Misc] = []
        self._gremlin_effect_after_v109: list[str] = []
        self._stable_status_var_v109: tk.StringVar | None = None
        self._stable_status_label_v109: tk.Label | None = None
        self._stable_status_after_v109: str | None = None
        self._stable_status_index_v109 = 0
        self._celdra_unlock_frame_v109: ttk.Frame | None = None
        self._celdra_unlock_status_v109: tk.StringVar | None = None
        super().__init__()
        self._celdra_gremlin_memory_v99 = load_memory()
        self._gremlin_main_scene_complete_v109 = bool(
            self._celdra_gremlin_memory_v99.get("breakout_seen")
        )
        self.after_idle(self._sync_celdra_tab_v109)

    # ------------------------------------------------------------------
    # The opening breakout is an installation-local one-time prologue. Later
    # RUN ALL sessions continue the persistent capture sequence instead.
    # ------------------------------------------------------------------
    def _start_celdra_session_v49(self, first_scan: bool) -> None:
        self._clear_gremlin_effects_v109()
        self._celdra_gremlin_memory_v99 = load_memory()
        self._gremlin_main_scene_complete_v109 = bool(
            self._celdra_gremlin_memory_v99.get("breakout_seen")
        )
        super()._start_celdra_session_v49(first_scan)

    def _start_placeholder_runtime_v70(self) -> None:
        resumed = bool(self._celdra_gremlin_memory_v99.get("breakout_seen"))
        if resumed:
            self._gremlin_stage_enabled_v106 = True
            self._gremlin_intro_started_v106 = True
            self._gremlin_dismissed_v108 = False
        super()._start_placeholder_runtime_v70()
        self._gremlin_main_scene_complete_v109 = resumed
        if collection_complete(self._celdra_gremlin_memory_v99):
            self._install_gremlin_stable_v101()
            self._sync_celdra_tab_v109()
            return
        if resumed:
            if self._stable_names_v101():
                self._install_gremlin_stable_v101()
            self._runtime_pose_v70(
                "smile",
                "The main breakout is already documented. I am continuing the quieter part: finding each Gremlin, surviving their individual routine, and putting them in the stable.",
            )
            self._schedule_random_event_v99(initial=True)

    def _start_gremlin_show_v94(self) -> None:
        if bool(self._celdra_gremlin_memory_v99.get("breakout_seen")):
            self._gremlin_main_scene_complete_v109 = True
            if collection_complete(self._celdra_gremlin_memory_v99):
                self._install_gremlin_stable_v101()
                self._sync_celdra_tab_v109()
            else:
                if self._stable_names_v101():
                    self._install_gremlin_stable_v101()
                self._schedule_random_event_v99(initial=True)
            return
        super()._start_gremlin_show_v94()

    def _finish_internal_gremlin_show_v101(self) -> None:
        super()._finish_internal_gremlin_show_v101()
        self._celdra_gremlin_memory_v99 = mark_breakout_seen(
            self._celdra_gremlin_memory_v99
        )
        self._gremlin_main_scene_complete_v109 = True
        captured = self._stable_names_v101()
        if captured:
            self._gremlin_stage_enabled_v106 = True
            self._gremlin_intro_started_v106 = True
            self._gremlin_dismissed_v108 = False
            self._install_gremlin_stable_v101()
            self._runtime_pose_v70(
                "smile",
                f"Main breakout dismissed. {len(captured)}/9 are already contained, so the stable is restored. The others will return one at a time.",
            )
        else:
            self._runtime_pose_v70(
                "suspicious",
                "The group breakout is over. None are contained yet. They will come back individually, show off, and make me catch them properly.",
            )
        if not collection_complete(self._celdra_gremlin_memory_v99):
            self._schedule_random_event_v99(initial=True)

    # ------------------------------------------------------------------
    # Random events prioritize uncaptured Gremlins and pause while another
    # presentation scene owns the interface.
    # ------------------------------------------------------------------
    def _schedule_random_event_v99(self, *, initial: bool = False) -> None:
        if self._celdra_random_event_after_v99 is not None:
            try:
                self.after_cancel(self._celdra_random_event_after_v99)
            except tk.TclError:
                pass
            self._celdra_random_event_after_v99 = None
        if not self._gremlin_main_scene_complete_v109:
            self._gremlin_random_waiting_v109 = True
            return
        if collection_complete(self._celdra_gremlin_memory_v99):
            self._sync_celdra_tab_v109()
            return
        low = (
            self.RANDOM_CAPTURE_INITIAL_MIN_MS_V109
            if initial
            else self.RANDOM_CAPTURE_MIN_MS_V109
        )
        high = (
            self.RANDOM_CAPTURE_INITIAL_MAX_MS_V109
            if initial
            else self.RANDOM_CAPTURE_MAX_MS_V109
        )
        delay = self._celdra_random_v99.randint(low, high)
        self._gremlin_random_waiting_v109 = False
        self._celdra_random_event_after_v99 = self.after(
            self._scaled_runtime_ms_v88(delay),
            self._run_random_event_v99,
        )

    def _run_random_event_v99(self) -> None:
        self._celdra_random_event_after_v99 = None
        if not self._gremlin_main_scene_complete_v109:
            self._gremlin_random_waiting_v109 = True
            return
        if collection_complete(self._celdra_gremlin_memory_v99):
            self._sync_celdra_tab_v109()
            return
        if not bool(getattr(self, "_celdra_session_active_v49", False)):
            return
        if (
            not self._celdra_intro_gate_open_v99
            or self._celdra_gremlin_active_v94
            or self._celdra_history_active_v99
        ):
            self._schedule_random_event_v99()
            return

        stable = set(self._stable_names_v101())
        choices = [
            dict(row)
            for row in GREMLIN_PERSONALITIES
            if str(row.get("name") or "").upper() not in stable
            and str(row.get("name") or "").upper()
            not in self._celdra_session_individual_v101
        ]
        if not choices:
            choices = [
                dict(row)
                for row in GREMLIN_PERSONALITIES
                if str(row.get("name") or "").upper() not in stable
            ]
        if not choices:
            self._sync_celdra_tab_v109()
            return

        # The history gag remains rare and can only interrupt between captures.
        if (
            not bool(self._celdra_gremlin_memory_v99.get("history_gag_seen"))
            and self._celdra_random_v99.random() < 0.10
        ):
            self._start_history_gag_v99()
            return
        self._start_individual_gremlin_visit_v99(
            dict(self._celdra_random_v99.choice(choices))
        )

    def _finish_history_gag_v99(self) -> None:
        super()._finish_history_gag_v99()
        if (
            self._gremlin_main_scene_complete_v109
            and not collection_complete(self._celdra_gremlin_memory_v99)
        ):
            self._schedule_random_event_v99()

    # ------------------------------------------------------------------
    # Every returning Gremlin gets a four-beat skit. The inherited V101 finish
    # animation performs the actual persistent capture after the final beat.
    # ------------------------------------------------------------------
    def _start_individual_gremlin_visit_v99(
        self, personality: dict[str, Any]
    ) -> None:
        name = str(personality.get("name") or "").upper()
        if name not in GREMLIN_CAPTURE_SKITS_V109:
            return
        self._gremlin_stage_enabled_v106 = True
        self._gremlin_intro_started_v106 = True
        self._gremlin_dismissed_v108 = False
        self._clear_gremlin_effects_v109()
        super()._start_individual_gremlin_visit_v99(personality)
        if self._celdra_current_individual_v101 != name:
            return
        self._append_console_v49(
            f"[CORE] INDIVIDUAL GREMLIN SKIT START // {name} // CAPTURE PENDING"
        )
        for beat_index, beat in enumerate(GREMLIN_CAPTURE_SKITS_V109[name]):
            delay = int(beat[0])
            self._schedule_gremlin_v94(
                delay,
                lambda selected=name, selected_index=beat_index: self._play_capture_beat_v109(
                    selected, selected_index
                ),
            )

    def _play_capture_beat_v109(self, name: str, beat_index: int) -> None:
        if (
            not self._celdra_gremlin_active_v94
            or not self._celdra_single_visit_v99
            or self._celdra_current_individual_v101 != name
        ):
            return
        beats = GREMLIN_CAPTURE_SKITS_V109.get(name) or ()
        if beat_index < 0 or beat_index >= len(beats):
            return
        _delay, pose, line, target_key, relx, rely, effect = beats[beat_index]
        self._runtime_pose_v70(str(pose), str(line))
        self._append_console_v49(
            f"[{name}] SKIT BEAT {beat_index + 1}/{len(beats)} // {effect}"
        )
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(
                f"{name} // {effect} // CAPTURE {beat_index + 1}/{len(beats)}"
            )
        self._move_individual_v109(str(target_key), float(relx), float(rely))
        self._show_individual_effect_v109(
            name,
            str(effect),
            str(target_key),
            float(relx),
            float(rely),
        )

    def _target_widget_v109(self, key: str) -> tk.Misc | None:
        return {
            "pipeline": getattr(self, "run_tree", None),
            "progress": getattr(self, "stage_progress_frame", None),
            "log": getattr(self, "run_log", None),
            "console": getattr(self, "_celdra_console_v49", None),
            "avatar": getattr(self, "celdra_avatar_canvas_v50", None),
            "lower": getattr(self, "run_bottom_split_v50", None),
            "upper": getattr(self, "run_top_split_v50", None),
        }.get(key)

    def _move_individual_v109(self, key: str, relx: float, rely: float) -> None:
        widget = self._target_widget_v109(key)
        if widget is None or not self._celdra_gremlin_swarm_v95:
            return
        target = self._widget_point_v94(widget, relx, rely)
        self._animate_swarm_to_v95([target], 1_350)

    def _show_individual_effect_v109(
        self,
        name: str,
        text: str,
        key: str,
        relx: float,
        rely: float,
    ) -> None:
        widget = self._target_widget_v109(key)
        if widget is None:
            return
        if name == "NULL" and "VISIBLE: FALSE" in text:
            item = (
                self._celdra_gremlin_swarm_v95[0]
                if self._celdra_gremlin_swarm_v95
                else None
            )
            holder = item.get("holder") if isinstance(item, dict) else None
            if isinstance(holder, tk.Toplevel):
                try:
                    holder.withdraw()
                    identifier = self.after(
                        self._scaled_runtime_ms_v88(1_650),
                        lambda selected=holder: self._reveal_null_v109(selected),
                    )
                    self._gremlin_effect_after_v109.append(identifier)
                except tk.TclError:
                    pass

        copies = 2 if name == "GLITCH" else 1
        for copy_index in range(copies):
            try:
                self.update_idletasks()
                x = (
                    widget.winfo_rootx()
                    - self.winfo_rootx()
                    + int(widget.winfo_width() * relx)
                    + copy_index * 16
                )
                y = (
                    widget.winfo_rooty()
                    - self.winfo_rooty()
                    + int(widget.winfo_height() * rely)
                    + copy_index * 12
                )
            except tk.TclError:
                return
            label = tk.Label(
                self,
                text=text,
                background="#071426",
                foreground="#d8f5ff" if name != "GLITCH" else "#ff8a99",
                highlightbackground="#45a9db" if name != "GLITCH" else "#ff596f",
                highlightthickness=1,
                font=("Consolas", 8, "bold"),
                padx=6,
                pady=3,
            )
            label.place(x=max(4, x - 68), y=max(4, y - 14))
            try:
                label.lift()
            except tk.TclError:
                pass
            self._gremlin_effect_widgets_v109.append(label)
            identifier = self.after(
                self._scaled_runtime_ms_v88(4_600),
                lambda selected=label: self._destroy_effect_widget_v109(selected),
            )
            self._gremlin_effect_after_v109.append(identifier)

    @staticmethod
    def _reveal_null_v109(holder: tk.Toplevel) -> None:
        try:
            holder.deiconify()
            holder.lift()
        except tk.TclError:
            pass

    def _destroy_effect_widget_v109(self, widget: tk.Misc) -> None:
        try:
            widget.destroy()
        except tk.TclError:
            pass
        if widget in self._gremlin_effect_widgets_v109:
            self._gremlin_effect_widgets_v109.remove(widget)

    def _clear_gremlin_effects_v109(self) -> None:
        for identifier in tuple(self._gremlin_effect_after_v109):
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
        self._gremlin_effect_after_v109.clear()
        for widget in tuple(self._gremlin_effect_widgets_v109):
            try:
                widget.destroy()
            except tk.TclError:
                pass
        self._gremlin_effect_widgets_v109.clear()

    def _finish_individual_gremlin_visit_v99(self) -> None:
        name = str(self._celdra_current_individual_v101 or "").upper()
        self._clear_gremlin_effects_v109()
        self._gremlin_stage_enabled_v106 = True
        self._gremlin_intro_started_v106 = True
        self._gremlin_dismissed_v108 = False
        super()._finish_individual_gremlin_visit_v99()
        if name:
            self.after(
                self._scaled_runtime_ms_v88(3_250),
                lambda selected=name: self._after_individual_capture_v109(selected),
            )

    def _after_individual_capture_v109(self, name: str) -> None:
        self._celdra_gremlin_memory_v99 = load_memory()
        if name not in set(self._stable_names_v101()):
            return
        self._install_gremlin_stable_v101()
        count = len(self._stable_names_v101())
        self._append_console_v49(
            f"[CORE] COLLECTION PROGRESS // {name} CONTAINED // {count}/9"
        )
        if collection_complete(self._celdra_gremlin_memory_v99):
            self._schedule_collection_reward_v101()
            return
        self._schedule_random_event_v99()

    # ------------------------------------------------------------------
    # A dedicated stable feed exists only when at least one Gremlin has actually
    # been captured. It rotates messages exclusively from the contained set.
    # ------------------------------------------------------------------
    def _install_gremlin_stable_v101(self) -> None:
        names = self._stable_names_v101()
        if not names:
            return
        if not bool(getattr(self, "_celdra_session_active_v49", False)):
            return
        if not bool(getattr(self, "_celdra_intro_gate_open_v99", False)):
            return
        self._gremlin_stage_enabled_v106 = True
        self._gremlin_intro_started_v106 = True
        self._gremlin_dismissed_v108 = False
        super()._install_gremlin_stable_v101()
        self._ensure_stable_status_v109()
        self._refresh_stable_status_v109()

    def _ensure_middle_panel_v101(self, mode: str) -> None:
        super()._ensure_middle_panel_v101(mode)
        self._ensure_stable_status_v109()

    def _ensure_stable_status_v109(self) -> None:
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if frame is None:
            return
        label = self._stable_status_label_v109
        if label is not None:
            try:
                if label.winfo_exists() and label.master is frame:
                    return
            except tk.TclError:
                pass
        variable = tk.StringVar(value="")
        label = tk.Label(
            frame,
            textvariable=variable,
            background="#071426",
            foreground="#9ce2dc",
            anchor="w",
            justify="left",
            font=("Consolas", 8),
            padx=7,
            pady=4,
            wraplength=330,
        )
        label.grid(row=2, column=0, sticky="ew", pady=(3, 0))
        self._stable_status_var_v109 = variable
        self._stable_status_label_v109 = label

    def _refresh_stable_status_v109(self) -> None:
        label = self._stable_status_label_v109
        variable = self._stable_status_var_v109
        if label is None or variable is None:
            return
        names = self._stable_names_v101()
        if not names:
            try:
                label.grid_remove()
            except tk.TclError:
                pass
            return
        try:
            label.grid()
        except tk.TclError:
            return
        name = names[self._stable_status_index_v109 % len(names)]
        messages = STABLE_MESSAGES_V109.get(name) or (f"{name} is contained.",)
        message_index = (
            self._stable_status_index_v109 // max(1, len(names))
        ) % len(messages)
        variable.set(f"{name} // {messages[message_index]}")
        self._stable_status_index_v109 += 1
        if self._stable_status_after_v109 is not None:
            try:
                self.after_cancel(self._stable_status_after_v109)
            except tk.TclError:
                pass
        self._stable_status_after_v109 = self.after(
            self._scaled_runtime_ms_v88(8_500),
            self._refresh_stable_status_v109,
        )

    # ------------------------------------------------------------------
    # The top-level Celdra tab is absent until the collection reward is earned.
    # ------------------------------------------------------------------
    def _schedule_collection_reward_v101(self) -> None:
        super()._schedule_collection_reward_v101()
        if (
            collection_complete(self._celdra_gremlin_memory_v99)
            and bool(self._celdra_gremlin_memory_v99.get("collection_reward_seen"))
        ):
            self._sync_celdra_tab_v109()

    def _finish_collection_reward_v101(self) -> None:
        super()._finish_collection_reward_v101()
        self._celdra_gremlin_memory_v99 = load_memory()
        self._sync_celdra_tab_v109()
        self._append_console_v49(
            "[CORE] CELDRA TAB UNLOCKED // GREMLIN COLLECTION 9/9 // SERENIAL TAVERN LINK AVAILABLE"
        )
        self._runtime_pose_v70(
            "love",
            "Nine out of nine. I added a Celdra tab. It has the collection record and a doorway back to the Serenial Tavern, where I can actually answer you.",
        )

    def _sync_celdra_tab_v109(self) -> None:
        complete = collection_complete(self._celdra_gremlin_memory_v99)
        reward_seen = bool(
            self._celdra_gremlin_memory_v99.get("collection_reward_seen")
        )
        notebook = getattr(self, "notebook", None)
        if not isinstance(notebook, ttk.Notebook):
            return
        if not (complete and reward_seen):
            frame = self._celdra_unlock_frame_v109
            if frame is not None:
                try:
                    notebook.forget(frame)
                    frame.destroy()
                except tk.TclError:
                    pass
                self._celdra_unlock_frame_v109 = None
                self.tabs.pop("Celdra", None)
            return
        if self._celdra_unlock_frame_v109 is not None:
            return

        frame = ttk.Frame(notebook, padding=18)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        notebook.add(frame, text="Celdra")
        self.tabs["Celdra"] = frame
        self._celdra_unlock_frame_v109 = frame

        ttk.Label(
            frame,
            text="CELDRA // GREMLIN COLLECTION COMPLETE",
            font=("Segoe UI", 20, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text=(
                "All nine Gremlins have been encountered, survived, and wrangled into the supervised stable. "
                "Celdra's Serenial Tavern doorway is now available."
            ),
            wraplength=900,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(7, 14))

        roster = ttk.LabelFrame(frame, text="Stable roster // 9/9", padding=10)
        roster.grid(row=2, column=0, sticky="ew")
        for column in range(3):
            roster.columnconfigure(column, weight=1)
        personalities = {
            str(row.get("name") or "").upper(): row
            for row in GREMLIN_PERSONALITIES
        }
        for index, name in enumerate(KNOWN_GREMLINS):
            row_data = personalities.get(name) or {}
            ttk.Label(
                roster,
                text=f"{name}\n{str(row_data.get('role') or 'resident')}",
                anchor="center",
                justify="center",
                padding=8,
            ).grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=4,
                pady=4,
            )

        doorway = ttk.LabelFrame(frame, text="Serenial Tavern", padding=14)
        doorway.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        doorway.columnconfigure(0, weight=1)
        self._celdra_unlock_status_v109 = tk.StringVar(
            value="Celdra is available in the Serenial Tavern Discord."
        )
        ttk.Label(
            doorway,
            textvariable=self._celdra_unlock_status_v109,
            wraplength=760,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(
            doorway,
            text="Join Celdra in the Serenial Tavern",
            command=self._open_serenial_discord_v109,
            style="Accent.TButton",
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            doorway,
            text="The button opens Serenial's maintained Discord redirect in your default browser.",
            wraplength=760,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _open_serenial_discord_v109(self) -> None:
        opened = False
        try:
            opened = bool(
                webbrowser.open(SERENIAL_DISCORD_REDIRECT_V109, new=2)
            )
            if not opened:
                opened = bool(
                    webbrowser.open(SERENIAL_DISCORD_INVITE_V109, new=2)
                )
        except Exception:
            opened = False
        if opened:
            if self._celdra_unlock_status_v109 is not None:
                self._celdra_unlock_status_v109.set(
                    "Serenial Tavern opened in your default browser."
                )
            return
        messagebox.showerror(
            "Open Serenial Tavern",
            "Fragmenter could not open the browser. Visit https://www.serenial.ca manually.",
        )

    def _cancel_internal_show_v101(self) -> None:
        self._clear_gremlin_effects_v109()
        super()._cancel_internal_show_v101()

    def _cancel_celdra_cues_v49(self) -> None:
        self._clear_gremlin_effects_v109()
        if self._stable_status_after_v109 is not None:
            try:
                self.after_cancel(self._stable_status_after_v109)
            except tk.TclError:
                pass
            self._stable_status_after_v109 = None
        super()._cancel_celdra_cues_v49()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V109"
            metadata["post_breakout_collection"] = (
                "random_individual_skits_then_persistent_stable_capture"
            )
            metadata["stable_status_scope"] = "captured_gremlins_only"
            metadata["celdra_tab_unlock"] = "collection_complete_9_of_9"
            metadata["celdra_discord_redirect"] = SERENIAL_DISCORD_REDIRECT_V109
        return payload

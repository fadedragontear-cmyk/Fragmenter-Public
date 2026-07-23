#!/usr/bin/env python3
"""V112 acceptance fixes for Gremlin state, stable geometry, activity, and gallery."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from celdra_gremlin_collection_v109 import (
    SERENIAL_DISCORD_INVITE_V109,
    SERENIAL_DISCORD_REDIRECT_V109,
)
from celdra_gremlin_memory_v1 import KNOWN_GREMLINS, memory_path
from celdra_gremlin_memory_v2 import collection_complete, load_memory
from celdra_v99_content import GREMLIN_PERSONALITIES


GREMLIN_ACTIVITY_V112: dict[str, tuple[str, ...]] = {
    "BYTE": (
        "QUERY TOOLTIP INVENTORY",
        "TASTE DOCUMENTATION HASH",
        "VERIFY METADATA CRUMBS",
    ),
    "HEX": (
        "TRACE 0xHOME OFFSET",
        "MAP STABLE CORNERS",
        "VALIDATE FOOTPRINT TABLE",
    ),
    "CACHE": (
        "INDEX RECENT COMPLAINTS",
        "COMPACT LOG SATCHEL",
        "EVICT STALE GRUMBLING",
    ),
    "LOOP": (
        "REPLAY SUCCESSFUL ROUTE",
        "CHECK FINISH-LINE LOCATION",
        "HALT AFTER ONE LAP",
    ),
    "PING": (
        "TEST PADDED-BAR LATENCY",
        "BOUNCE RESPONSE QUERY",
        "MEASURE INDOOR VOLUME",
    ),
    "PATCH": (
        "AUDIT CROOKED TOY DOOR",
        "REVIEW HORN TICKET",
        "APPLY ZERO UNASKED FIXES",
    ),
    "ROOT": (
        "COUNT PARTY QUORUM",
        "REVIEW CEREMONIAL ACCESS",
        "APPROVE SNACK DISTRIBUTION",
    ),
    "NULL": (
        "LOOKUP RESIDENT PROCESS",
        "VERIFY INVISIBLE PRESENCE",
        "RESOLVE UNDEFINED NAP",
    ),
    "GLITCH": (
        "DUPLICATE SAFE STATUS",
        "COMPARE ORIGINAL COPY",
        "VERIFY REDUNDANCY REDUNDANCY",
    ),
}


class FragmenterGremlinAcceptanceMixinV112:
    """Make a fresh checkout fresh and stabilize the completed presentation."""

    STABLE_MIN_WIDTH_V112 = 170
    STABLE_MAX_WIDTH_V112 = 218
    STABLE_WIDTH_FRACTION_V112 = 0.17
    CONSOLE_MIN_WIDTH_V112 = 300
    AVATAR_RIGHT_SHIFT_V112 = 18

    def __init__(self) -> None:
        self._stable_activity_after_v112: str | None = None
        self._stable_activity_phase_v112 = 0
        self._stable_layout_signature_v112: tuple[int, int] | None = None
        self._stable_layout_applied_v112 = False
        self._gremlin_gallery_after_v112: str | None = None
        self._gremlin_gallery_phase_v112 = 0
        self._gremlin_gallery_frames_v112: dict[str, list[tk.PhotoImage]] = {}
        self._gremlin_gallery_labels_v112: dict[str, ttk.Label] = {}
        super().__init__()

    # ------------------------------------------------------------------
    # State diagnostics. The memory implementation is checkout-local in V112.
    # ------------------------------------------------------------------
    def _start_celdra_session_v49(self, first_scan: bool) -> None:
        super()._start_celdra_session_v49(first_scan)
        state = load_memory()
        count = len(state.get("stable") or [])
        mode = "RETURNING" if state.get("breakout_seen") else "FRESH PROLOGUE"
        self._append_console_v49(
            f"[CORE] GREMLIN SESSION // {mode} // CAPTURED {count}/9 // STATE {memory_path()}"
        )

    # ------------------------------------------------------------------
    # Compact stable geometry. Apply once when inserted, then leave user sashes
    # alone instead of reasserting geometry on every status/animation refresh.
    # ------------------------------------------------------------------
    def _apply_middle_layout_v101(self) -> None:
        pane = getattr(self, "celdra_visual_split_v50", None)
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if pane is None or frame is None or bool(getattr(self, "_celdra_middle_hidden_v103", False)):
            return
        try:
            self.update_idletasks()
            pane_count = len(tuple(pane.panes()))
            width = max(640, int(pane.winfo_width()))
            if pane_count < 3:
                return
            signature = (round(width / 40) * 40, pane_count)
            if self._stable_layout_applied_v112:
                if bool(getattr(self, "celdra_layout_user_locked_v50", False)):
                    return
                if signature == self._stable_layout_signature_v112:
                    return
            stable_width = max(
                self.STABLE_MIN_WIDTH_V112,
                min(self.STABLE_MAX_WIDTH_V112, round(width * self.STABLE_WIDTH_FRACTION_V112)),
            )
            console_width = max(
                self.CONSOLE_MIN_WIDTH_V112,
                min(350, round(width * 0.29)),
            )
            second = max(stable_width + 240, width - console_width)
            first = max(240, second - stable_width)
            pane.sashpos(0, first)
            pane.sashpos(1, second)
            self._stable_layout_applied_v112 = True
            self._stable_layout_signature_v112 = signature
            wrap = max(136, stable_width - 18)
            for child in frame.grid_slaves(row=0, column=0):
                if isinstance(child, tk.Label):
                    child.configure(
                        anchor="center",
                        justify="center",
                        wraplength=wrap,
                        font=("Consolas", 7, "bold"),
                    )
            status = getattr(self, "_stable_status_label_v109", None)
            if isinstance(status, tk.Label):
                status.configure(
                    wraplength=wrap,
                    justify="left",
                    anchor="w",
                    font=("Consolas", 7),
                )
        except (AttributeError, tk.TclError):
            pass

    def _install_gremlin_stable_v101(self) -> None:
        before = getattr(self, "_celdra_middle_frame_v101", None)
        super()._install_gremlin_stable_v101()
        after = getattr(self, "_celdra_middle_frame_v101", None)
        if after is not None and after is not before:
            self._stable_layout_applied_v112 = False
            self._stable_layout_signature_v112 = None
        self.after_idle(self._apply_middle_layout_v101)

    def _start_avatar_takeover_v58(self) -> None:
        super()._start_avatar_takeover_v58()
        self._celdra_external_offset_x_v65 = self.AVATAR_RIGHT_SHIFT_V112
        self._redraw_celdra_avatar_v50()

    def _begin_shy_reveal_v64(self) -> None:
        super()._begin_shy_reveal_v64()
        self._celdra_external_offset_x_v65 = self.AVATAR_RIGHT_SHIFT_V112
        self._redraw_celdra_avatar_v50()

    # ------------------------------------------------------------------
    # Resident activity: the bar describes the current fictional query/action,
    # not collection completion. It continually cycles even at 9/9.
    # ------------------------------------------------------------------
    def _ensure_stable_status_v103(self) -> None:
        self._ensure_stable_status_v109()

    def _start_stable_status_v103(self) -> None:
        self._refresh_stable_status_v109()

    def _cancel_stable_status_v103(self) -> None:
        self._cancel_stable_activity_v112()

    def _ensure_stable_status_v109(self) -> None:
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if frame is None:
            return
        label = getattr(self, "_stable_status_label_v109", None)
        alive = False
        if isinstance(label, tk.Label):
            try:
                alive = bool(label.winfo_exists() and label.master is frame)
            except tk.TclError:
                alive = False
        if not alive:
            variable = tk.StringVar(value="STABLE ACTIVITY // WAITING FOR FIRST RESIDENT")
            label = tk.Label(
                frame,
                textvariable=variable,
                background="#071426",
                foreground="#9ce2dc",
                anchor="w",
                justify="left",
                font=("Consolas", 7),
                padx=6,
                pady=3,
                wraplength=190,
            )
            label.grid(row=2, column=0, sticky="ew", pady=(3, 0))
            self._stable_status_var_v109 = variable
            self._stable_status_label_v109 = label
        bar = getattr(self, "_stable_status_progress_v109", None)
        bar_alive = False
        if isinstance(bar, ttk.Progressbar):
            try:
                bar_alive = bool(bar.winfo_exists() and bar.master is frame)
            except tk.TclError:
                bar_alive = False
        if not bar_alive:
            bar = ttk.Progressbar(
                frame,
                orient="horizontal",
                mode="determinate",
                maximum=100,
                value=0,
                style="RunAll.Visible.Horizontal.TProgressbar",
            )
            bar.grid(row=3, column=0, sticky="ew", pady=(2, 0))
            self._stable_status_progress_v109 = bar
        self._refresh_stable_status_v109()

    def _refresh_stable_status_v109(self) -> None:
        label = getattr(self, "_stable_status_label_v109", None)
        variable = getattr(self, "_stable_status_var_v109", None)
        bar = getattr(self, "_stable_status_progress_v109", None)
        if label is None or variable is None or bar is None:
            return
        names = list(self._stable_names_v101())
        if not names:
            try:
                label.grid_remove()
                bar.grid_remove()
            except tk.TclError:
                pass
            self._cancel_stable_activity_v112()
            return
        try:
            label.grid()
            bar.grid()
        except tk.TclError:
            return
        phase = self._stable_activity_phase_v112
        ticks_per_action = 21
        action_serial = phase // ticks_per_action
        name = names[action_serial % len(names)]
        actions = GREMLIN_ACTIVITY_V112.get(name) or ("RUN HARMLESS STABLE QUERY",)
        action = actions[(action_serial // max(1, len(names))) % len(actions)]
        progress = (phase % ticks_per_action) * 5
        suffix = "COMPLETE" if progress >= 100 else f"{progress:02d}%"
        variable.set(f"{name} // {action} // {suffix}")
        try:
            bar.configure(maximum=100)
            bar["value"] = progress
        except tk.TclError:
            return
        self._stable_activity_phase_v112 += 1
        if self._stable_activity_after_v112 is None:
            self._stable_activity_after_v112 = self.after(
                max(350, self._scaled_runtime_ms_v88(700)),
                self._stable_activity_tick_v112,
            )

    def _stable_activity_tick_v112(self) -> None:
        self._stable_activity_after_v112 = None
        self._refresh_stable_status_v109()

    def _cancel_stable_activity_v112(self) -> None:
        identifier = self._stable_activity_after_v112
        self._stable_activity_after_v112 = None
        if identifier is not None:
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Celdra tab: absent below 9/9; at 9/9 it becomes a gallery and invitation.
    # ------------------------------------------------------------------
    def _sync_celdra_tab_v109(self) -> None:
        self._celdra_gremlin_memory_v99 = load_memory()
        notebook = getattr(self, "notebook", None)
        if not isinstance(notebook, ttk.Notebook):
            return
        if not collection_complete(self._celdra_gremlin_memory_v99):
            self._remove_celdra_tab_v112(notebook)
            return
        existing = getattr(self, "_celdra_unlock_frame_v109", None)
        if existing is not None:
            try:
                if existing.winfo_exists() and str(existing) in notebook.tabs():
                    return
            except tk.TclError:
                pass
        self._remove_celdra_tab_v112(notebook)
        self._build_celdra_gallery_tab_v112(notebook)

    def _remove_celdra_tab_v112(self, notebook: ttk.Notebook) -> None:
        self._stop_gremlin_gallery_v112()
        candidates: list[tk.Misc] = []
        frame = getattr(self, "_celdra_unlock_frame_v109", None)
        if frame is not None:
            candidates.append(frame)
        for tab_id in tuple(notebook.tabs()):
            try:
                if str(notebook.tab(tab_id, "text")) == "Celdra":
                    candidates.append(notebook.nametowidget(tab_id))
            except (KeyError, tk.TclError):
                continue
        for candidate in dict.fromkeys(candidates):
            try:
                notebook.forget(candidate)
            except tk.TclError:
                pass
            try:
                candidate.destroy()
            except tk.TclError:
                pass
        self._celdra_unlock_frame_v109 = None
        self.tabs.pop("Celdra", None)

    def _build_celdra_gallery_tab_v112(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        notebook.add(frame, text="Celdra")
        self.tabs["Celdra"] = frame
        self._celdra_unlock_frame_v109 = frame

        intro = ttk.LabelFrame(frame, text="A message from Celdra", padding=10)
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        intro.columnconfigure(0, weight=1)
        ttk.Label(
            intro,
            text="CELDRA // GREMLIN COLLECTION COMPLETE",
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            intro,
            text=(
                "You found all nine. They are contained, supervised, and only loosely respectful of process boundaries. "
                "I am Celdra, Serenial's resident AI dragongirl. Fragmenter can show you this scripted doorway; the Serenial Tavern is where the community, Fade, and the live version of me actually are."
            ),
            wraplength=1050,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(5, 0))

        invite = ttk.Frame(frame)
        invite.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        invite.columnconfigure(1, weight=1)
        ttk.Button(
            invite,
            text="Join Celdra and Serenial in the Tavern",
            command=self._open_serenial_discord_v109,
            style="Accent.TButton",
        ).grid(row=0, column=0, sticky="w")
        self._celdra_unlock_status_v109 = tk.StringVar(
            value="Celdra invites you to meet Serenial's community, projects, games, and long-running Tavern regulars."
        )
        ttk.Label(
            invite,
            textvariable=self._celdra_unlock_status_v109,
            wraplength=760,
            justify="left",
        ).grid(row=0, column=1, sticky="ew", padx=(10, 0))

        gallery = ttk.LabelFrame(frame, text="The Gremlin stable // animated residents // 9/9", padding=8)
        gallery.grid(row=2, column=0, sticky="nsew")
        for column in range(3):
            gallery.columnconfigure(column, weight=1, uniform="gremlin_gallery")
        for row in range(3):
            gallery.rowconfigure(row, weight=1, uniform="gremlin_gallery")

        personalities = {
            str(row.get("name") or "").upper(): dict(row)
            for row in GREMLIN_PERSONALITIES
        }
        self._gremlin_gallery_frames_v112.clear()
        self._gremlin_gallery_labels_v112.clear()
        for index, name in enumerate(KNOWN_GREMLINS):
            data = personalities.get(name) or {}
            card = ttk.Frame(gallery, padding=6, relief="ridge")
            card.grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=4,
                pady=4,
            )
            card.columnconfigure(1, weight=1)
            frames = self._load_gremlin_gif_frames_v112(name)
            image_label = ttk.Label(card, anchor="center")
            image_label.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(0, 8))
            if frames:
                image_label.configure(image=frames[0])
                self._gremlin_gallery_frames_v112[name] = frames
                self._gremlin_gallery_labels_v112[name] = image_label
            else:
                image_label.configure(text=f"[{name}]", width=12)
            ttk.Label(
                card,
                text=f"{name} // {str(data.get('role') or 'resident').upper()}",
                font=("Segoe UI", 10, "bold"),
            ).grid(row=0, column=1, sticky="w")
            ttk.Label(
                card,
                text=str(data.get("spotlight") or "A supervised resident of Celdra's stable."),
                wraplength=260,
                justify="left",
            ).grid(row=1, column=1, sticky="new", pady=(3, 2))
            ttk.Label(
                card,
                text=str(data.get("claim") or "STATUS: CONTAINED"),
                font=("Consolas", 7, "bold"),
            ).grid(row=2, column=1, sticky="sw")
        self._start_gremlin_gallery_v112()

    def _load_gremlin_gif_frames_v112(self, name: str) -> list[tk.PhotoImage]:
        path = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "celdra"
            / "gremlins"
            / "v112"
            / f"{name.casefold()}.gif"
        )
        if not path.is_file():
            return []
        frames: list[tk.PhotoImage] = []
        for index in range(32):
            try:
                frames.append(
                    tk.PhotoImage(file=str(path), format=f"gif -index {index}")
                )
            except tk.TclError:
                break
        return frames

    def _start_gremlin_gallery_v112(self) -> None:
        if self._gremlin_gallery_after_v112 is not None:
            return
        if not self._gremlin_gallery_frames_v112:
            return
        self._gremlin_gallery_after_v112 = self.after(170, self._tick_gremlin_gallery_v112)

    def _tick_gremlin_gallery_v112(self) -> None:
        self._gremlin_gallery_after_v112 = None
        frame = getattr(self, "_celdra_unlock_frame_v109", None)
        try:
            if frame is None or not frame.winfo_exists():
                return
        except tk.TclError:
            return
        self._gremlin_gallery_phase_v112 += 1
        for name, frames in tuple(self._gremlin_gallery_frames_v112.items()):
            label = self._gremlin_gallery_labels_v112.get(name)
            if not frames or label is None:
                continue
            try:
                label.configure(image=frames[self._gremlin_gallery_phase_v112 % len(frames)])
            except tk.TclError:
                continue
        self._start_gremlin_gallery_v112()

    def _stop_gremlin_gallery_v112(self) -> None:
        identifier = self._gremlin_gallery_after_v112
        self._gremlin_gallery_after_v112 = None
        if identifier is not None:
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
        self._gremlin_gallery_frames_v112.clear()
        self._gremlin_gallery_labels_v112.clear()

    def _open_serenial_discord_v109(self) -> None:
        opened = False
        try:
            opened = bool(webbrowser.open(SERENIAL_DISCORD_INVITE_V109, new=2))
            if not opened:
                opened = bool(webbrowser.open(SERENIAL_DISCORD_REDIRECT_V109, new=2))
        except Exception:
            opened = False
        if opened:
            status = getattr(self, "_celdra_unlock_status_v109", None)
            if status is not None:
                status.set("Serenial Tavern opened in your default browser. Celdra will see you there.")
            return
        messagebox.showerror(
            "Open Serenial Tavern",
            "Fragmenter could not open the browser. Visit https://www.serenial.ca manually.",
        )

    def _cancel_celdra_cues_v49(self) -> None:
        self._cancel_stable_activity_v112()
        self._stop_gremlin_gallery_v112()
        super()._cancel_celdra_cues_v49()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V112"
            metadata["gremlin_memory_scope"] = "checkout_local_fresh_install"
            metadata["stable_geometry"] = "compact_single_authority_user_sash_safe"
            metadata["stable_progress"] = "resident_query_activity_not_collection_percent"
            metadata["celdra_tab"] = "9_of_9_animated_gallery_and_serenial_invite"
        return payload

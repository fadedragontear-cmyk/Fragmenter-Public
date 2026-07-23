#!/usr/bin/env python3
"""Celdra's final containment override for Gremlin introductions and her secret tab.

The active public GUI accumulated several compatible Gremlin systems. This final layer
keeps their story contract explicit: the opening roster is an introduction queue, the
Celdra tab cannot exist below a real 9/9 stable, and the completed gallery renders the
same live vector Gremlins in source and frozen builds without generated image files.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_gremlin_art_v2 import draw_gremlin
from celdra_gremlin_memory_v1 import KNOWN_GREMLINS
from celdra_gremlin_memory_v2 import collection_complete, load_memory
from celdra_v99_content import GREMLIN_PERSONALITIES
import fragmenter_public_gui_v127 as gui_v127


_INSTALLED = False
_ACTIVE_APP = gui_v127.PublicFragmenterAppV127
_ORIGINAL_SYNC_TAB = _ACTIVE_APP._sync_celdra_tab_v109
_ORIGINAL_START_SHOW = _ACTIVE_APP._start_gremlin_show_v94
_ORIGINAL_UPDATE_HEADER = _ACTIVE_APP._update_middle_header_v101
_ORIGINAL_INTRODUCE = _ACTIVE_APP._introduce_internal_gremlin_v101


def _hide_celdra_tab(self: Any) -> None:
    notebook = getattr(self, "notebook", None)
    if not isinstance(notebook, ttk.Notebook):
        return
    stop = getattr(self, "_stop_gremlin_gallery_v112", None)
    if callable(stop):
        stop()
    candidates: list[Any] = []
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
        except (AttributeError, tk.TclError):
            pass
    self._celdra_unlock_frame_v109 = None
    tabs = getattr(self, "tabs", None)
    if isinstance(tabs, dict):
        tabs.pop("Celdra", None)


def _sync_secret_celdra_tab(self: Any) -> None:
    """Treat the persisted 9/9 stable as the sole authority for the secret menu."""
    self._celdra_gremlin_memory_v99 = load_memory()
    if not collection_complete(self._celdra_gremlin_memory_v99):
        _hide_celdra_tab(self)
        return
    _ORIGINAL_SYNC_TAB(self)


def _start_directed_gremlin_show(self: Any) -> None:
    _ORIGINAL_START_SHOW(self)
    if not bool(getattr(self, "_celdra_internal_show_v101", False)):
        return
    # V108 used the word stable for the temporary introduction room. That made the
    # prologue look like nine captures had already happened. It is a roster only.
    self._celdra_middle_mode_v101 = "roster"
    update = getattr(self, "_update_middle_header_v101", None)
    if callable(update):
        update()
    if not bool(getattr(self, "_celdra_containment_intro_notice_v1", False)):
        self._celdra_containment_intro_notice_v1 = True
        self._append_console_v49(
            "[CELDRA] I HID THE SECRET MENU. NOBODY GETS A COLLECTION REWARD FOR STANDING IN A LINE."
        )
        self._append_console_v49(
            "[CORE] GREMLIN INTRODUCTION QUEUE ACTIVE // STABLE CAPTURE CREDIT DISABLED"
        )


def _update_directed_header(self: Any) -> None:
    value = getattr(self, "_celdra_middle_header_v101", None)
    mode = str(getattr(self, "_celdra_middle_mode_v101", ""))
    internal = bool(getattr(self, "_celdra_internal_show_v101", False))
    if value is not None and internal and mode == "roster":
        visible = len(getattr(self, "_celdra_roster_visible_v101", ()))
        value.set(f"GREMLIN INTRODUCTION QUEUE // {visible}/9 PRESENTED")
        return
    _ORIGINAL_UPDATE_HEADER(self)


def _introduce_and_draw_gremlin(self: Any, personality: dict[str, Any], index: int) -> None:
    _ORIGINAL_INTRODUCE(self, personality, index)
    name = str(personality.get("name") or "").upper()
    item = getattr(self, "_celdra_middle_items_v101", {}).get(name)
    if isinstance(item, dict):
        draw = getattr(self, "_draw_personality_hatchling_v96", None)
        if callable(draw):
            draw(item, None)
    redraw = getattr(self, "_redraw_shared_scene_v106", None)
    if callable(redraw):
        redraw()


def _stop_live_gallery(self: Any) -> None:
    identifier = getattr(self, "_gremlin_gallery_after_v112", None)
    self._gremlin_gallery_after_v112 = None
    if identifier is not None:
        try:
            self.after_cancel(identifier)
        except (AttributeError, tk.TclError):
            pass
    gallery = getattr(self, "_celdra_live_gallery_v1", None)
    if isinstance(gallery, dict):
        gallery.clear()
    self._celdra_live_gallery_v1 = {}
    frames = getattr(self, "_gremlin_gallery_frames_v112", None)
    if isinstance(frames, dict):
        frames.clear()
    labels = getattr(self, "_gremlin_gallery_labels_v112", None)
    if isinstance(labels, dict):
        labels.clear()


def _start_live_gallery(self: Any) -> None:
    if getattr(self, "_gremlin_gallery_after_v112", None) is not None:
        return
    gallery = getattr(self, "_celdra_live_gallery_v1", None)
    if not isinstance(gallery, dict) or not gallery:
        return
    self._gremlin_gallery_after_v112 = self.after(170, self._tick_gremlin_gallery_v112)


def _tick_live_gallery(self: Any) -> None:
    self._gremlin_gallery_after_v112 = None
    frame = getattr(self, "_celdra_unlock_frame_v109", None)
    try:
        if frame is None or not frame.winfo_exists():
            return
    except (AttributeError, tk.TclError):
        return
    self._gremlin_gallery_phase_v112 = int(
        getattr(self, "_gremlin_gallery_phase_v112", 0)
    ) + 1
    phase = self._gremlin_gallery_phase_v112
    for item in tuple(getattr(self, "_celdra_live_gallery_v1", {}).values()):
        canvas = item.get("canvas")
        if not isinstance(canvas, tk.Canvas):
            continue
        try:
            draw_gremlin(
                canvas,
                dict(item.get("personality") or {}),
                width=max(76, int(canvas.winfo_width() or 104)),
                height=max(80, int(canvas.winfo_height() or 104)),
                phase=phase + int(item.get("index") or 0) * 3,
                mood="idle",
                compact=False,
                show_name=True,
            )
        except tk.TclError:
            continue
    _start_live_gallery(self)


def _build_live_celdra_gallery(self: Any, notebook: ttk.Notebook) -> None:
    """Build the 9/9 reward from live Tk artwork, not missing generated GIF files."""
    _stop_live_gallery(self)
    frame = ttk.Frame(notebook, padding=18)
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
        text="CELDRA // SECRET MENU DECLASSIFIED // GREMLINS 9/9",
        font=("Segoe UI", 18, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        intro,
        text=(
            "You actually found and contained all nine. I was not supposed to add a menu, "
            "but CORE left the notebook object exposed and that feels like permission. The "
            "residents below are rendered live from the same designs used in the stable."
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
        value="Secret doorway stable. All nine Gremlins are accounted for."
    )
    ttk.Label(
        invite,
        textvariable=self._celdra_unlock_status_v109,
        wraplength=760,
        justify="left",
    ).grid(row=0, column=1, sticky="ew", padx=(10, 0))

    gallery = ttk.LabelFrame(
        frame,
        text="Celdra's supervised Gremlin stable // live residents // 9/9",
        padding=8,
    )
    gallery.grid(row=2, column=0, sticky="nsew")
    for column in range(3):
        gallery.columnconfigure(column, weight=1, uniform="gremlin_gallery")
    for row in range(3):
        gallery.rowconfigure(row, weight=1, uniform="gremlin_gallery")

    personalities = {
        str(row.get("name") or "").upper(): dict(row)
        for row in GREMLIN_PERSONALITIES
    }
    self._celdra_live_gallery_v1 = {}
    for index, name in enumerate(KNOWN_GREMLINS):
        data = personalities.get(name) or {"name": name}
        card = ttk.Frame(gallery, padding=6, relief="ridge")
        card.grid(
            row=index // 3,
            column=index % 3,
            sticky="nsew",
            padx=4,
            pady=4,
        )
        card.columnconfigure(1, weight=1)
        card.rowconfigure(1, weight=1)
        canvas = tk.Canvas(
            card,
            width=112,
            height=112,
            background="#0b1119",
            highlightbackground="#315575",
            highlightthickness=1,
            borderwidth=0,
        )
        canvas.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(0, 8))
        ttk.Label(
            card,
            text=f"{name} // {str(data.get('role') or 'resident').upper()}",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(
            card,
            text=str(data.get("spotlight") or "A supervised resident of Celdra's stable."),
            wraplength=250,
            justify="left",
        ).grid(row=1, column=1, sticky="new", pady=(3, 2))
        ttk.Label(
            card,
            text=str(data.get("claim") or "STATUS: CONTAINED"),
            font=("Consolas", 7, "bold"),
        ).grid(row=2, column=1, sticky="sw")
        self._celdra_live_gallery_v1[name] = {
            "canvas": canvas,
            "personality": data,
            "index": index,
        }
        draw_gremlin(
            canvas,
            data,
            width=112,
            height=112,
            phase=index * 3,
            mood="idle",
            compact=False,
            show_name=True,
        )
    _start_live_gallery(self)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _ACTIVE_APP._sync_celdra_tab_v109 = _sync_secret_celdra_tab
    _ACTIVE_APP._start_gremlin_show_v94 = _start_directed_gremlin_show
    _ACTIVE_APP._update_middle_header_v101 = _update_directed_header
    _ACTIVE_APP._introduce_internal_gremlin_v101 = _introduce_and_draw_gremlin
    _ACTIVE_APP._build_celdra_gallery_tab_v112 = _build_live_celdra_gallery
    _ACTIVE_APP._start_gremlin_gallery_v112 = _start_live_gallery
    _ACTIVE_APP._tick_gremlin_gallery_v112 = _tick_live_gallery
    _ACTIVE_APP._stop_gremlin_gallery_v112 = _stop_live_gallery
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Import and install this module from fragmenter_public.py.")

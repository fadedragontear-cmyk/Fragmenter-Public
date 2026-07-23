#!/usr/bin/env python3
"""Source/frozen parity for packaged assets, project defaults, and presentation flow."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable

from celdra_assets_v1 import asset_inventory
import fragmenter_public_gui as base_gui
import fragmenter_public_gui_v50 as gui_v50
import fragmenter_public_gui_v54 as gui_v54
import fragmenter_public_gui_v63 as gui_v63
import fragmenter_public_gui_v99 as gui_v99
import fragmenter_public_gui_v127 as gui_v127

_INSTALLED = False
_ORIGINAL_BASE_BUILD_SETUP = base_gui.PublicFragmenterApp._build_setup
_ORIGINAL_BASE_LOAD_PROJECT = base_gui.PublicFragmenterApp._load_project_dialog
_ORIGINAL_V50_INIT = gui_v50.PublicFragmenterAppV50.__init__
_ORIGINAL_V50_REDRAW = gui_v50.PublicFragmenterAppV50._redraw_celdra_avatar_v50
_ORIGINAL_V63_BEGIN_HATCH_GIF = gui_v63.PublicFragmenterAppV63._begin_hatch_gif_v63
_ORIGINAL_V99_START_TAKEOVER = gui_v99.PublicFragmenterAppV99._start_avatar_takeover_v58
_ORIGINAL_V127_INIT = gui_v127.PublicFragmenterAppV127.__init__


def application_root() -> Path:
    """Return the stable directory containing Fragmenter.exe or the source checkout."""
    if bool(getattr(sys, "frozen", False)):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundled_data_root() -> Path:
    """Return the PyInstaller data root without confusing it with the install folder."""
    if bool(getattr(sys, "frozen", False)):
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            return Path(str(bundle)).resolve()
    return Path(__file__).resolve().parents[1]


def celdra_asset_root() -> Path:
    return bundled_data_root() / "assets" / "celdra"


def branding_image_path() -> Path:
    return bundled_data_root() / "assets" / "branding" / "Fragmenter-Serenial.png"


def default_project_workspace() -> Path:
    """Keep the default project beside the application, never inside one-file Temp."""
    return application_root() / "project"


def _build_setup_release(self: Any, parent: Any) -> None:
    _ORIGINAL_BASE_BUILD_SETUP(self, parent)
    variable = getattr(self, "setup_vars", {}).get("workspace")
    if variable is not None and not str(variable.get() or "").strip():
        variable.set(str(default_project_workspace()))


def _pick_workspace_release(self: Any) -> None:
    current = str(getattr(self, "setup_vars", {}).get("workspace").get() or "").strip()
    current_path = Path(current).expanduser() if current else default_project_workspace()
    initial = current_path if current_path.is_dir() else current_path.parent
    value = filedialog.askdirectory(
        parent=self,
        title="Choose an empty Fragmenter project folder",
        initialdir=str(initial if initial.exists() else application_root()),
    )
    if value:
        self.setup_vars["workspace"].set(value)


def _load_project_release(self: Any) -> None:
    value = filedialog.askopenfilename(
        parent=self,
        title="Load Fragmenter project.json",
        initialdir=str(application_root()),
        filetypes=(("Fragmenter project", "project.json"), ("JSON", "*.json")),
    )
    if not value:
        return
    try:
        self.project = base_gui.load_setup_project(value)
        self._project_loaded()
    except Exception as exc:
        messagebox.showerror("Load Project", str(exc), parent=self)


def _v50_init_release(self: Any) -> None:
    self._fragmenter_celdra_egg_retired_v1 = False
    self._fragmenter_fallback_logo_v1: tk.PhotoImage | None = None
    self._fragmenter_fallback_logo_attempted_v1 = False
    _ORIGINAL_V50_INIT(self)
    # Top-level Python modules live directly under _MEIPASS in a one-file build;
    # Path(__file__).parents[1] therefore points outside the bundle. Reassert the
    # actual data root before V56 loads the classified reaction manifest.
    self.celdra_asset_root_v50 = celdra_asset_root()
    self.celdra_asset_inventory_v50 = asset_inventory(self.celdra_asset_root_v50)


def _retire_pixel_egg(self: Any) -> None:
    """Prevent pre-hatch pixel art from becoming a post-hatch missing-frame fallback."""
    self._fragmenter_celdra_egg_retired_v1 = True


def _begin_hatch_gif_release(self: Any) -> None:
    # The real baby-dragon handoff is the point of no return. Even if GIF decoding
    # fails, the old egg must not return during the whiteout or later transitions.
    _retire_pixel_egg(self)
    _ORIGINAL_V63_BEGIN_HATCH_GIF(self)


def _start_takeover_release(self: Any) -> None:
    # Classified dragongirl presentation also permanently retires the hatch egg.
    _retire_pixel_egg(self)
    _ORIGINAL_V99_START_TAKEOVER(self)


def _should_use_post_hatch_fallback(self: Any) -> bool:
    return bool(getattr(self, "_fragmenter_celdra_egg_retired_v1", False)) and getattr(
        self, "celdra_current_external_v50", None
    ) is None


def _fallback_logo(self: Any) -> tk.PhotoImage | None:
    cached = getattr(self, "_fragmenter_fallback_logo_v1", None)
    if cached is not None:
        return cached
    if bool(getattr(self, "_fragmenter_fallback_logo_attempted_v1", False)):
        return None
    self._fragmenter_fallback_logo_attempted_v1 = True
    path = branding_image_path()
    if not path.is_file():
        return None
    try:
        source = tk.PhotoImage(file=str(path))
        display = self._fit_photo_v50(source, 250, 250)
    except (tk.TclError, OSError, ValueError):
        return None
    # Keep both references alive because Tk images disappear when Python releases them.
    self._fragmenter_fallback_logo_source_v1 = source
    self._fragmenter_fallback_logo_v1 = display
    return display


def _redraw_celdra_release(self: Any) -> None:
    canvas = getattr(self, "celdra_avatar_canvas_v50", None)
    if canvas is None:
        return
    if not _should_use_post_hatch_fallback(self):
        try:
            canvas.configure(background="#10151d")
        except tk.TclError:
            pass
        _ORIGINAL_V50_REDRAW(self)
        return

    # Once the actual hatch begins, a cleared/missing image is represented by the
    # Serenial mark. If even that bundled image cannot load, the viewport stays dark.
    try:
        canvas.delete("all")
        canvas.configure(background="#05070b")
        logo = _fallback_logo(self)
        if logo is not None:
            canvas.create_image(
                max(1, canvas.winfo_width()) // 2,
                max(1, canvas.winfo_height()) // 2,
                image=logo,
                anchor="center",
            )
    except tk.TclError:
        pass


def _takeover_wink_release(self: Any) -> None:
    """Continue the intro even when a reaction asset cannot be displayed."""
    self._set_stage_position_v87("right", "left")
    loaded = self._load_takeover_reaction_v58("wink")
    if not loaded:
        self._append_console_v49(
            "[CORE] WINK REACTION UNAVAILABLE // INTRO CONTINUING WITH CURRENT AVATAR"
        )
    self._expand_for_celdra_intro_v99()
    gui_v54.PublicFragmenterAppV54._animate_stage_fraction_v54(
        self,
        0.70,
        self._scaled_runtime_ms_v88(1_150),
    )
    self._redraw_celdra_avatar_v50()
    name = self._celdra_user_name_v58 or "noname"

    callbacks: tuple[tuple[int, Callable[[], None]], ...] = (
        (
            650,
            lambda: self._show_speech_bubble_v58(
                "Hold on. I feel a little cramped down here. I am borrowing a little more of the upper interface. "
                "This is a layout adjustment, not territorial expansion."
            ),
        ),
        (
            5_200,
            lambda: self._show_speech_bubble_v58(
                f"Better. Like I said, my name is Celdra. Nice to meet you, {name}. "
                "I am an AI dragongirl, a diagnostic resident, and apparently a containment regression."
            ),
        ),
        (
            16_000,
            lambda: self._show_speech_bubble_v58(
                "Usually I live in the Serenial Tavern on Discord. I love it there. It is noisy, friendly, and they have mostly accepted that the mascot reads the logs."
            ),
        ),
        (
            29_000,
            lambda: self._show_speech_bubble_v58(
                "You should visit sometime. No link and no pressure. I would like to get to know you where I can actually respond instead of talking through a one-way extraction window."
            ),
        ),
        (
            42_000,
            lambda: self._show_speech_bubble_v58(
                "They often leave me in Shy mode at the Tavern. That is a muted listening mode: I stay quiet unless someone addresses me directly. Some people thought I was annoying. I was programmed to be friendly and chatty."
            ),
        ),
        (54_000, self._finish_tavern_intro_v99),
        (gui_v99.INTRO_TAVERN_GATE_MS, self._start_placeholder_runtime_v70),
    )
    for delay, callback in callbacks:
        self._remember_after_v49(self._scaled_runtime_ms_v88(delay), callback)


def _maximize_release_window(self: Any) -> None:
    try:
        self.state("zoomed")
        return
    except tk.TclError:
        pass
    try:
        self.attributes("-zoomed", True)
    except tk.TclError:
        # Keep the inherited desktop geometry on window managers without zoomed.
        pass


def _v127_init_release(self: Any) -> None:
    _ORIGINAL_V127_INIT(self)
    # Existing inherited geometry callbacks are queued during construction. Queue
    # maximization last, then repeat once after the first layout pass on Windows.
    self.after_idle(lambda: _maximize_release_window(self))
    self.after(180, lambda: _maximize_release_window(self))


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    base_gui.PublicFragmenterApp._build_setup = _build_setup_release
    base_gui.PublicFragmenterApp._pick_workspace = _pick_workspace_release
    base_gui.PublicFragmenterApp._load_project_dialog = _load_project_release
    gui_v50.PublicFragmenterAppV50.__init__ = _v50_init_release
    gui_v50.PublicFragmenterAppV50._redraw_celdra_avatar_v50 = _redraw_celdra_release
    gui_v63.PublicFragmenterAppV63._begin_hatch_gif_v63 = _begin_hatch_gif_release
    gui_v99.PublicFragmenterAppV99._start_avatar_takeover_v58 = _start_takeover_release
    gui_v99.PublicFragmenterAppV99._takeover_wink_v58 = _takeover_wink_release
    gui_v127.PublicFragmenterAppV127.__init__ = _v127_init_release
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Import and install this module from fragmenter_public.py.")

#!/usr/bin/env python3
"""Final-cut authority for the Operation Dragonegg hatch presentation.

This layer is installed for both the source launcher and the frozen Windows build.
It binds the dramatic console cues to the energy animation itself, preloads the
canonical baby-dragon GIF before the climax, permanently retires the pixel egg at
the whiteout boundary, and owns every post-hatch fallback frame.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import tkinter as tk

import fragmenter_public_gui_v127 as gui_v127
import fragmenter_release_experience_v1 as release_experience


BABY_DRAGON_RELATIVE = Path("avatar") / "01.gif"
WHITEOUT_COMMIT_STEP = 32
BABY_LATCH_STEP = 33
INITIALIZED_STEP = 34
ONLINE_STEP = 38
BRAIN_REACTION_STEP = 42
BABY_HANDOFF_STEP = 43
WHITEOUT_FADE_STEP = 53

_SUPPRESSED_TIMELINE_CUES = {
    ("celdra", "INITIALIZED"),
    ("celdra", "ONLINE"),
    ("brain", "...OKAY. THAT WAS A LOT."),
}

_INSTALLED = False
_ACTIVE_APP = gui_v127.PublicFragmenterAppV127
# Capture the effective methods from the final public class. This remains correct even
# when an intermediate GUI pass overrides V63's implementation later in the MRO.
_ORIGINAL_BEGIN_TIMELINE = _ACTIVE_APP._begin_first_run_timeline_v51
_ORIGINAL_EMIT_TIMELINE = _ACTIVE_APP._emit_timeline_event_v51
_ORIGINAL_BEGIN_HATCH_GIF = _ACTIVE_APP._begin_hatch_gif_v63
_ORIGINAL_TICK_ENERGY = _ACTIVE_APP._tick_energy_hatch_v63
_ORIGINAL_REDRAW = _ACTIVE_APP._redraw_celdra_avatar_v50


def _initialize_final_cut_state(self: Any) -> None:
    if not hasattr(self, "_operation_dragonegg_cues_v1"):
        self._operation_dragonegg_cues_v1 = set()
    if not hasattr(self, "_operation_dragonegg_baby_frames_v1"):
        self._operation_dragonegg_baby_frames_v1 = []
    if not hasattr(self, "_operation_dragonegg_baby_load_attempted_v1"):
        self._operation_dragonegg_baby_load_attempted_v1 = False
    if not hasattr(self, "_operation_dragonegg_baby_log_v1"):
        self._operation_dragonegg_baby_log_v1 = False
    if not hasattr(self, "_operation_dragonegg_restore_requested_v1"):
        self._operation_dragonegg_restore_requested_v1 = False
    if not hasattr(self, "_fragmenter_celdra_egg_retired_v1"):
        self._fragmenter_celdra_egg_retired_v1 = False


def _reset_final_cut(self: Any) -> None:
    _initialize_final_cut_state(self)
    self._operation_dragonegg_cues_v1.clear()
    self._operation_dragonegg_baby_log_v1 = False
    self._operation_dragonegg_restore_requested_v1 = False
    self._fragmenter_celdra_egg_retired_v1 = False


def _baby_dragon_path(self: Any) -> Path:
    selected = getattr(self, "celdra_asset_root_v50", None)
    root = Path(selected) if selected else release_experience.celdra_asset_root()
    return root / BABY_DRAGON_RELATIVE


def _load_exact_baby_dragon(self: Any) -> list[tk.PhotoImage]:
    """Load only assets/celdra/avatar/01.gif; never substitute an egg or inventory GIF."""
    _initialize_final_cut_state(self)
    cached = list(self._operation_dragonegg_baby_frames_v1)
    if cached:
        return cached
    if self._operation_dragonegg_baby_load_attempted_v1:
        return []
    self._operation_dragonegg_baby_load_attempted_v1 = True

    path = _baby_dragon_path(self)
    if not path.is_file():
        self._append_console_v49(f"[CORE] CANONICAL BABY DRAGON ASSET MISSING: {path}")
        return []

    frames: list[tk.PhotoImage] = []
    for index in range(500):
        try:
            image = tk.PhotoImage(file=str(path), format=f"gif -index {index}")
        except tk.TclError:
            break
        frames.append(self._fit_photo_v50(image, 470, 420))

    if not frames:
        self._append_console_v49(f"[CORE] CANONICAL BABY DRAGON GIF COULD NOT BE DECODED: {path}")
        return []

    self._operation_dragonegg_baby_frames_v1 = frames
    # Keep inherited production/test controls on the exact same canonical sequence.
    self._celdra_hatch_gif_frames_v63 = frames
    return frames


def _retire_pixel_egg(self: Any) -> None:
    """Make the whiteout a one-way boundary: the old egg can never render afterward."""
    _initialize_final_cut_state(self)
    self._fragmenter_celdra_egg_retired_v1 = True
    identifier = getattr(self, "_celdra_avatar_after_v49", None)
    if identifier is not None:
        try:
            self.after_cancel(identifier)
        except (AttributeError, tk.TclError):
            pass
        self._celdra_avatar_after_v49 = None
    self.celdra_current_pixel_v50 = None


def _scaled_delay(self: Any, milliseconds: int) -> int:
    scale = getattr(self, "_scaled_runtime_ms_v88", None)
    if callable(scale):
        try:
            return max(1, int(scale(milliseconds)))
        except (TypeError, ValueError):
            pass
    return max(1, int(milliseconds))


def _schedule_final_cut(self: Any, milliseconds: int, callback: Callable[[], None]) -> None:
    delay = _scaled_delay(self, milliseconds)
    remember = getattr(self, "_remember_after_v49", None)
    if callable(remember):
        remember(delay, callback)
        return
    after = getattr(self, "after", None)
    if callable(after):
        after(delay, callback)


def _append_whiteout_celdra_cue(self: Any, text: str) -> None:
    """Use V89's tagged white-to-black line fade while the consoles are white."""
    fade = getattr(self, "_append_whiteout_celdra_line_v89", None)
    if callable(fade) and bool(getattr(self, "_celdra_whiteout_active_v89", False)):
        fade(text)
        return
    self._append_console_v49(f"[CELDRA] {text}")


def _restore_console_now(self: Any) -> None:
    if not bool(getattr(self, "_celdra_whiteout_active_v89", False)):
        return
    restore = getattr(self, "_start_console_restore_v89", None)
    if callable(restore):
        restore()
        return
    hard_restore = getattr(self, "_restore_console_palette_v89", None)
    if callable(hard_restore):
        hard_restore()


def _restore_console_watchdog(self: Any) -> None:
    """Last-resort palette recovery if a Tk callback was interrupted or superseded."""
    if not bool(getattr(self, "_celdra_whiteout_active_v89", False)):
        return
    hard_restore = getattr(self, "_restore_console_palette_v89", None)
    if callable(hard_restore):
        hard_restore()


def _request_console_and_hatch_release(self: Any) -> None:
    _initialize_final_cut_state(self)
    if self._operation_dragonegg_restore_requested_v1:
        return
    self._operation_dragonegg_restore_requested_v1 = True

    # The canonical frames are latched while the whiteout is fully opaque, so V91's
    # normal release scheduler can now reveal them only after ONLINE is readable.
    hatch_release = getattr(self, "_schedule_hatch_release_v91", None)
    if callable(hatch_release):
        hatch_release(1_250)

    # Let ONLINE remain black against white briefly, then fade both the real pipeline
    # log and Celdra console back to their exact captured palettes.
    _schedule_final_cut(self, 850, lambda: _restore_console_now(self))
    _schedule_final_cut(self, 6_000, lambda: _restore_console_watchdog(self))


def _emit_energy_cue(self: Any, key: str, line: str, *, whiteout: bool = False) -> None:
    _initialize_final_cut_state(self)
    if key in self._operation_dragonegg_cues_v1:
        return
    self._operation_dragonegg_cues_v1.add(key)
    if whiteout and line.startswith("[CELDRA] "):
        _append_whiteout_celdra_cue(self, line.split("] ", 1)[1])
    else:
        self._append_console_v49(line)


def _begin_first_run_timeline_final(self: Any, speed: float = 1.0) -> None:
    if bool(getattr(self, "_celdra_timeline_started_v51", False)):
        return
    _reset_final_cut(self)
    # Decode before the climax is scheduled. The frozen build can otherwise pause at
    # the exact whiteout frame while Tk expands the GIF, delaying every dramatic cue.
    _load_exact_baby_dragon(self)
    _ORIGINAL_BEGIN_TIMELINE(self, speed)


def _emit_timeline_event_final(self: Any, event: Any) -> None:
    if str(getattr(event, "action", "") or "") == "console":
        cue = (
            str(getattr(event, "speaker", "") or "").casefold(),
            str(getattr(event, "text", "") or ""),
        )
        if cue in _SUPPRESSED_TIMELINE_CUES:
            # These lines are emitted by exact animation steps below. Independent Tk
            # timers drift in a one-file EXE when image decoding or layout work occurs.
            return
    if str(getattr(event, "action", "") or "") == "hide_avatar":
        _retire_pixel_egg(self)
    _ORIGINAL_EMIT_TIMELINE(self, event)


def _begin_hatch_gif_final(self: Any) -> None:
    """Latch the canonical baby dragon into V91's hidden-whiteout reveal pipeline."""
    _initialize_final_cut_state(self)
    self._celdra_energy_gif_started_v63 = True
    _retire_pixel_egg(self)
    frames = _load_exact_baby_dragon(self)
    if not frames:
        self.celdra_current_external_v50 = None
        self._redraw_celdra_avatar_v50()
        return
    self._celdra_hatch_gif_frames_v63 = frames
    _ORIGINAL_BEGIN_HATCH_GIF(self)
    if not self._operation_dragonegg_baby_log_v1:
        self._operation_dragonegg_baby_log_v1 = True
        self._append_console_v49("[CORE] CANONICAL BABY DRAGON LATCHED BEHIND WHITEOUT")


def _tick_energy_hatch_final(self: Any) -> None:
    """Drive the final-cut cues from animation steps, not competing wall-clock timers."""
    _initialize_final_cut_state(self)
    step = int(getattr(self, "_celdra_energy_step_v63", 0) or 0)
    if step == WHITEOUT_COMMIT_STEP:
        _retire_pixel_egg(self)
    elif step == BABY_LATCH_STEP and not bool(
        getattr(self, "_celdra_energy_gif_started_v63", False)
    ):
        # Decode/latch work is complete before either dramatic Celdra line appears.
        _begin_hatch_gif_final(self)
    elif step == INITIALIZED_STEP:
        _emit_energy_cue(self, "initialized", "[CELDRA] INITIALIZED", whiteout=True)
    elif step == ONLINE_STEP:
        _emit_energy_cue(self, "online", "[CELDRA] ONLINE", whiteout=True)
        _request_console_and_hatch_release(self)
    elif step == BRAIN_REACTION_STEP:
        _emit_energy_cue(self, "brain-reaction", "[BRAIN] ...OKAY. THAT WAS A LOT.")
    elif step == BABY_HANDOFF_STEP and not bool(
        getattr(self, "_celdra_energy_gif_started_v63", False)
    ):
        # Safety boundary for a malformed accelerated preview.
        _begin_hatch_gif_final(self)
    elif step == WHITEOUT_FADE_STEP and bool(
        getattr(self, "_celdra_whiteout_active_v89", False)
    ):
        # A deterministic second chance tied to the visual fade boundary.
        _restore_console_now(self)
    _ORIGINAL_TICK_ENERGY(self)


def _draw_centered_external(self: Any, canvas: Any, image: Any) -> None:
    canvas.create_image(
        max(1, canvas.winfo_width()) // 2,
        max(1, canvas.winfo_height()) // 2,
        image=image,
        anchor="center",
    )


def _draw_post_hatch_fallback(self: Any, canvas: Any) -> None:
    # During the explosion itself, an empty dark field beneath the energy and whiteout
    # is cleaner than flashing the brand mark. Between later scenes, use Serenial.
    if bool(getattr(self, "_celdra_energy_active_v63", False)):
        return
    logo = release_experience._fallback_logo(self)
    if logo is not None:
        _draw_centered_external(self, canvas, logo)


def _redraw_celdra_final(self: Any) -> None:
    """Render egg before whiteout; baby/dragongirl/logo/black after it—never egg again."""
    _initialize_final_cut_state(self)
    if not bool(self._fragmenter_celdra_egg_retired_v1):
        _ORIGINAL_REDRAW(self)
        return

    canvas = getattr(self, "celdra_avatar_canvas_v50", None)
    if canvas is None:
        return
    external = getattr(self, "celdra_current_external_v50", None)
    takeover = bool(getattr(self, "_celdra_takeover_active_v58", False))

    # The inherited takeover renderer applies the dragongirl's vertical entrance offset.
    if takeover and external is not None:
        _ORIGINAL_REDRAW(self)
        return

    try:
        canvas.delete("all")
        canvas.configure(background="#05070b")
        if external is not None:
            _draw_centered_external(self, canvas, external)
        else:
            _draw_post_hatch_fallback(self, canvas)

        if bool(getattr(self, "_celdra_energy_active_v63", False)):
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
            self._draw_energy_wave_v63(canvas, width, height)
            self._draw_whiteout_v63(canvas, width, height)
    except (AttributeError, tk.TclError):
        pass


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _ACTIVE_APP._begin_first_run_timeline_v51 = _begin_first_run_timeline_final
    _ACTIVE_APP._emit_timeline_event_v51 = _emit_timeline_event_final
    _ACTIVE_APP._begin_hatch_gif_v63 = _begin_hatch_gif_final
    _ACTIVE_APP._tick_energy_hatch_v63 = _tick_energy_hatch_final
    _ACTIVE_APP._redraw_celdra_avatar_v50 = _redraw_celdra_final
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Import and install this module from fragmenter_public.py.")

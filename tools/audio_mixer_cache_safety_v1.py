#!/usr/bin/env python3
"""Make end-of-run audio cache cleanup tolerant of projects without SNDDATA."""
from __future__ import annotations

from typing import Any, Callable


def install() -> None:
    import audio_mixer_controller_v2 as controller

    current: Callable[..., Any] = controller.clear_music_cache
    if bool(getattr(current, "_fragmenter_missing_snddata_safe", False)):
        return

    def safe_clear_music_cache(project: Any = None) -> None:
        try:
            current(project)
        except FileNotFoundError:
            # RUN ALL may legitimately finish without an extracted SNDDATA source.
            # Cache invalidation is best-effort cleanup and must not turn a
            # successful run into a Tk callback traceback.
            return

    setattr(safe_clear_music_cache, "_fragmenter_missing_snddata_safe", True)
    controller.clear_music_cache = safe_clear_music_cache

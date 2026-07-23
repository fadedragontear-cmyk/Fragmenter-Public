#!/usr/bin/env python3
"""Apply the one-time V109 collection migration before any sequence resumes."""
from __future__ import annotations

from celdra_gremlin_memory_v2 import begin_v109_collection, load_memory


class FragmenterCollectionMigrationMixinV109:
    """Prevent legacy appearance unlocks from counting as individual captures."""

    def __init__(self) -> None:
        super().__init__()
        self._celdra_gremlin_memory_v99 = begin_v109_collection(load_memory())
        self._gremlin_main_scene_complete_v109 = bool(
            self._celdra_gremlin_memory_v99.get("breakout_seen")
        )

    def _start_celdra_session_v49(self, first_scan: bool) -> None:
        self._celdra_gremlin_memory_v99 = begin_v109_collection(load_memory())
        self._gremlin_main_scene_complete_v109 = bool(
            self._celdra_gremlin_memory_v99.get("breakout_seen")
        )
        super()._start_celdra_session_v49(first_scan)

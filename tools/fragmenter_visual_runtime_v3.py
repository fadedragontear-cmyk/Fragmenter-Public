#!/usr/bin/env python3
"""Runtime authority for v18+ visual review and StudioCCS texture layout."""
from __future__ import annotations

from pathlib import Path

import ccsf_texture_decoder_v2 as texture_v2
import ccsf_texture_decoder_v3 as texture_v3
import ccsf_texture_registry_v1 as texture_registry_v1
import ccsf_textured_scene_v9 as scene_v9
import fragmenter_visual_runtime_v2 as runtime_v2

COMPLETE_SCENE_FACE_CAP = runtime_v2.COMPLETE_SCENE_FACE_CAP
MAX_DECODED_EXTERNAL_FILES = 8

# All active local and external texture resolvers call the v2 module dynamically.
# Replacing this single boundary keeps scene rendering and texture export identical.
texture_v2.decode_rgba = texture_v3.decode_rgba


def trim_external_texture_cache(max_files: int = MAX_DECODED_EXTERNAL_FILES) -> int:
    """Keep only the most recently inserted decoded external CCS files."""
    limit = max(1, int(max_files))
    removed = 0
    cache = texture_registry_v1._FILE_CACHE
    while len(cache) > limit:
        oldest = next(iter(cache))
        cache.pop(oldest, None)
        removed += 1
    return removed


def release_visual_source(source: str | Path | None) -> dict[str, int]:
    """Drop full scene buffers for a file while retaining the cheap name index."""
    if source:
        scene_v9.clear_scene_cache(source)
    removed = trim_external_texture_cache()
    return {"external_files_evicted": removed}

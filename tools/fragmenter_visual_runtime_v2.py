#!/usr/bin/env python3
"""Runtime authority for the staged v14+ 3D preview."""
from __future__ import annotations

import ccsf_texture_name_index_v2 as texture_name_index_v2
import ccsf_texture_registry_v1 as texture_registry_v1
import ccsf_texture_registry_v2 as texture_registry_v2
import ccsf_texture_resolution_v1 as texture_resolution_v1
import ccsf_textured_renderer_v2 as renderer_v2
import ccsf_textured_scene_v3 as scene_core
import ccsf_textured_scene_v7 as scene_v7
import ccsf_textured_scene_v8 as scene_v8
import ccsf_textured_scene_v9 as scene_v9
import fragmenter_visual_runtime_v1 as runtime_v1

COMPLETE_SCENE_FACE_CAP = runtime_v1.COMPLETE_SCENE_FACE_CAP

# Candidate lookup is cheap unless the GUI explicitly builds the persistent index.
texture_registry_v1._candidate_files = texture_name_index_v2.candidate_files
texture_registry_v2.install()

# Local textures honor the referenced CLUT first. A fallback is accepted only when
# exactly one compatible CLUT exists in the texture's indexed sub-file.
scene_core._parse_textures = texture_resolution_v1.parse_local_textures
scene_v9.preview_override = scene_v7.preview_override

# V9 has separate local-only and enriched caches. All preview-affecting state changes
# must invalidate those caches as well as the inherited v7/v8 caches.
def _set_assembly_mode(path, mode) -> None:
    scene_v8.set_assembly_mode(path, mode)
    scene_v9.clear_scene_cache(path)


def _set_preferred_clump(path, clump_id) -> None:
    scene_v8.set_preferred_clump(path, clump_id)
    scene_v9.clear_scene_cache(path)


def _set_preview_override(path, override) -> None:
    scene_v7.set_preview_override(path, override)
    scene_v9.clear_scene_cache(path)


scene_v9.set_assembly_mode = _set_assembly_mode
scene_v9.set_preferred_clump = _set_preferred_clump
scene_v9.set_preview_override = _set_preview_override

# The v2 renderer cooperatively aborts stale camera and asset renders.
scene_v9.render_textured_scene = renderer_v2.render_textured_scene
scene_v9.RenderCancelled = renderer_v2.RenderCancelled

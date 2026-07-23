#!/usr/bin/env python3
"""Runtime limits and renderer authority for the 3D-focused public preview."""
from __future__ import annotations

import ccsf_texture_name_index_v1 as texture_name_index_v1
import ccsf_texture_registry_v1 as texture_registry_v1
import ccsf_textured_renderer_v1 as renderer_v1
import ccsf_textured_scene_v3 as scene_core
import ccsf_textured_scene_v5 as scene_v5
import ccsf_textured_scene_v6 as scene_v6
import ccsf_textured_scene_v7 as scene_v7
import ccsf_textured_scene_v8 as scene_v8

# The older 20k software-raster submission cap could make an otherwise complete
# whole-file scene appear to contain only one portion. Keep a finite safety bound
# while allowing normal character/root-town assemblies to submit all triangles.
COMPLETE_SCENE_FACE_CAP = renderer_v1.MAX_RENDER_FACES
scene_core.MAX_RENDER_FACES = COMPLETE_SCENE_FACE_CAP
scene_v6.MAX_RENDER_FACES = COMPLETE_SCENE_FACE_CAP

# Build the cross-file exact-name index once per extracted library instead of
# rescanning every file independently for every unresolved material.
texture_registry_v1._candidate_files = texture_name_index_v1.candidate_files

# Preserve v11's saved per-asset transform/profile contract while replacing the
# scene assembler. The override itself is still applied only to preview triangles.
scene_v8.set_preview_override = scene_v7.set_preview_override
scene_v8.preview_override = scene_v7.preview_override

# One renderer authority for the launcher path. Transparent texels no longer write
# depth and translucent aura geometry is composed after opaque geometry.
scene_v5.render_textured_scene = renderer_v1.render_textured_scene
scene_v6.render_textured_scene = renderer_v1.render_textured_scene
scene_v7.render_textured_scene = renderer_v1.render_textured_scene
scene_v8.render_textured_scene = renderer_v1.render_textured_scene

#!/usr/bin/env python3
"""Runtime authority for recovered models, perspective review and Euler puppetry."""
from __future__ import annotations

from typing import Any

import ccsf_asset_tree_v1 as asset_tree_v1
import ccsf_gen1_deformable_v2 as deformable_v2
import ccsf_gen1_pose_v1 as pose_v1
import ccsf_gen1_pose_v7 as pose_v7
import ccsf_puppetry_v1 as puppetry_v1
import ccsf_textured_renderer_v3 as renderer_v3
import ccsf_textured_renderer_v4 as renderer_v4
import ccsf_textured_renderer_v5 as renderer_v5
import ccsf_textured_scene_v9 as scene_v9
import ccsf_visual_extract_v1 as visual_extract_v1
import ccsf_wireframe_scene_v2 as wireframe_v2

# Install tolerant deformable decoding before runtime v5 captures the pose loader. The
# decoder remains bounded to exact typed Model payloads and can preserve a valid body
# prefix when a later submodel variant is not understood yet.
pose_v1.decode_with_gen1_deformables = deformable_v2.decode_with_gen1_deformables

# Install the testable pose authority before runtime v5 captures the staged-scene
# loader. Wireframe, textured playback, contents and exported puppetry reports then
# evaluate the same process-wide Euler profile.
scene_v9.pose_v5 = pose_v7
wireframe_v2.pose_v5 = pose_v7
asset_tree_v1.pose_v2 = pose_v7
puppetry_v1.pose_v6 = pose_v7
visual_extract_v1.extract_animation_fast = puppetry_v1.export_puppetry_report

import ccsf_asset_tree_v2 as asset_tree_v2  # noqa: E402
import fragmenter_visual_runtime_v5 as runtime_v5  # noqa: E402
import visual_asset_annotations_v2 as annotations_v2  # noqa: E402
import visual_asset_controller_v1 as visual_controller_v1  # noqa: E402
import visual_classification_ledger_v2 as ledger_v2  # noqa: E402

COMPLETE_SCENE_FACE_CAP = runtime_v5.COMPLETE_SCENE_FACE_CAP
trim_external_texture_cache = runtime_v5.trim_external_texture_cache
trim_scene_cache_for_source = runtime_v5.trim_scene_cache_for_source
release_visual_source = runtime_v5.release_visual_source

asset_tree_v2.pose_v6 = pose_v7
asset_tree_v2.puppetry_v1.pose_v6 = pose_v7
asset_tree_v2.install()
annotations_v2.install()
ledger_v2.install()
visual_controller_v1.extract_animation_fast = puppetry_v1.export_puppetry_report

# Carry model-recovery evidence into the scene summary and therefore into flagged
# visual reports. This makes it clear whether a previously missing body was recovered
# completely, partially, or not at all.
if not hasattr(scene_v9, "_fragmenter_base_load_textured_scene_v6"):
    scene_v9._fragmenter_base_load_textured_scene_v6 = scene_v9.load_textured_scene  # type: ignore[attr-defined]
_BASE_LOAD_TEXTURED_SCENE_V6 = scene_v9._fragmenter_base_load_textured_scene_v6  # type: ignore[attr-defined]


def load_textured_scene_v6(*args: Any, **kwargs: Any):
    scene = _BASE_LOAD_TEXTURED_SCENE_V6(*args, **kwargs)
    recovery = dict((scene.context.report.setup or {}).get("deformable_recovery_v2") or {})
    scene.summary["deformable_recovery_v2"] = recovery
    scene.summary["recovered_deformable_models"] = int(recovery.get("recovered_models") or 0)
    scene.summary["partial_deformable_models"] = int(recovery.get("partial_models") or 0)
    scene.summary["eof_clamped_deformable_models"] = int(recovery.get("eof_clamped_models") or 0)
    return scene


scene_v9.load_textured_scene = load_textured_scene_v6

# The active renderer keeps full geometry but bounds explicitly named fast passes to a
# smaller framebuffer. Full-resolution idle refinement still uses the stable v4 path
# through the v5 wrapper. Existing GUI layers share the same process-wide camera state.
scene_v9.render_textured_scene = renderer_v5.render_textured_scene
scene_v9.RenderCancelled = renderer_v5.RenderCancelled
renderer_v3.set_preview_background = renderer_v5.set_preview_background
renderer_v3.preview_background = renderer_v5.preview_background
renderer_v3.set_preview_camera_basis = renderer_v5.set_preview_camera_basis
renderer_v3.preview_camera_basis = renderer_v5.preview_camera_basis
renderer_v4.set_preview_background = renderer_v5.set_preview_background
renderer_v4.set_preview_camera_basis = renderer_v5.set_preview_camera_basis
renderer_v4.set_preview_camera_position = renderer_v5.set_preview_camera_position

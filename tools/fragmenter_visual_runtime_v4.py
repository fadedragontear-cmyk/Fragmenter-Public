#!/usr/bin/env python3
"""Runtime authority for recovered Gen1 textures and stable software rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ccsf_setup_recovery_v1 as setup_recovery_v1
import ccsf_texture_registry_v1 as texture_registry_v1
import ccsf_textured_renderer_v3 as renderer_v3
import ccsf_textured_scene_v3 as scene_core
import ccsf_textured_scene_v9 as scene_v9
import fragmenter_visual_runtime_v3 as runtime_v3

COMPLETE_SCENE_FACE_CAP = runtime_v3.COMPLETE_SCENE_FACE_CAP
trim_external_texture_cache = runtime_v3.trim_external_texture_cache

# runtime_v3/v2 has already installed the StudioCCS display transform and the
# conservative local CLUT resolver. Wrap those active authorities rather than
# replacing them with older implementations.
_BASE_PARSE_MATERIALS = scene_core._parse_materials
_BASE_PARSE_TEXTURES = scene_core._parse_textures
_BASE_REGISTRY_DECODE_FILE = texture_registry_v1._decode_file
_BASE_LOAD_TEXTURED_SCENE = scene_v9.load_textured_scene
_BASE_RELEASE_VISUAL_SOURCE = runtime_v3.release_visual_source


def _ensure_recovered(context: Any) -> dict[str, Any]:
    summary = setup_recovery_v1.recover_context(context)
    setattr(context, "indexed_setup_recovery", summary)
    return summary


def _parse_materials_recovered(context: Any):
    _ensure_recovered(context)
    return _BASE_PARSE_MATERIALS(context)


def _parse_textures_recovered(context: Any):
    _ensure_recovered(context)
    return _BASE_PARSE_TEXTURES(context)


scene_core._parse_materials = _parse_materials_recovered
scene_core._parse_textures = _parse_textures_recovered


def _decode_external_file_recovered(path: Path) -> dict[str, Any]:
    decoded = _BASE_REGISTRY_DECODE_FILE(path)
    setup_recovery_v1.recover_report(decoded["path"], decoded["data"], decoded["report"])
    # The original registry builds this table before recovery. Rebuild it so exact
    # external-name lookup can see recovered TEX/CLUT/MAT records immediately.
    records_by_name: dict[str, list[dict[str, Any]]] = {}
    for record in decoded["report"].records:
        name = str(record.get("object_name") or "")
        if name:
            records_by_name.setdefault(name, []).append(record)
    decoded["records_by_name"] = records_by_name
    return decoded


texture_registry_v1._decode_file = _decode_external_file_recovered


def _load_textured_scene_recovered(*args: Any, **kwargs: Any):
    scene = _BASE_LOAD_TEXTURED_SCENE(*args, **kwargs)
    recovery = dict((scene.context.report.setup or {}).get("indexed_setup_recovery") or {})
    scene.summary["indexed_setup_recovery"] = recovery
    scene.summary["recovered_setup_records"] = int(recovery.get("count") or 0)
    scene.summary["recovered_texture_records"] = int(recovery.get("textures") or 0)
    scene.summary["recovered_clut_records"] = int(recovery.get("cluts") or 0)
    scene.summary["recovered_material_records"] = int(recovery.get("materials") or 0)
    return scene


scene_v9.load_textured_scene = _load_textured_scene_recovered

# Use the lower-allocation alpha-classified renderer everywhere the staged scene
# module is consulted by the active GUI.
scene_v9.render_textured_scene = renderer_v3.render_textured_scene
scene_v9.RenderCancelled = renderer_v3.RenderCancelled


def release_visual_source(source: str | Path | None) -> dict[str, int]:
    result = dict(_BASE_RELEASE_VISUAL_SOURCE(source))
    if source:
        setup_recovery_v1.clear_recovery_cache(source)
    return result


# v19 imported the v3 module object directly. Updating its function keeps the
# inherited selection-time eviction path routed through this v4 authority.
runtime_v3.release_visual_source = release_visual_source

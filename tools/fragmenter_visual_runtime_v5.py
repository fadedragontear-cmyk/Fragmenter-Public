#!/usr/bin/env python3
"""Runtime authority for stable recovered-texture review sessions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v2 as pose_v2
import ccsf_setup_recovery_v2 as setup_recovery_v2
import ccsf_structure_decoder as structure
import ccsf_textured_scene_v3 as scene_core
import ccsf_textured_scene_v9 as scene_v9
import fragmenter_visual_runtime_v3 as runtime_v3
import fragmenter_visual_runtime_v4 as runtime_v4

COMPLETE_SCENE_FACE_CAP = runtime_v4.COMPLETE_SCENE_FACE_CAP
trim_external_texture_cache = runtime_v4.trim_external_texture_cache
_LOCAL_MATERIAL_CACHE: dict[tuple[str, int, int], tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]] = {}
_LOCAL_TEXTURE_CACHE: dict[tuple[str, int, int], tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]] = {}


def _source_key(context: Any) -> tuple[str, int, int]:
    source = Path(context.source).expanduser().resolve()
    stat = source.stat()
    return str(source), stat.st_size, stat.st_mtime_ns


def _copy_parse_result(
    value: tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    # The scene builder adds negative external texture IDs to its returned mapping.
    # Copy containers/rows, but share immutable decoded texture RGBA byte buffers.
    mapping, rows = value
    return dict(mapping), [dict(row) for row in rows]


# Recover the indexed setup records on the immutable pose source itself. This makes
# the scene builder, StudioCCS-style contents tree and animation path agree about
# which local MAT/TEX/CLUT records exist.
if not hasattr(pose_v2, "_fragmenter_base_load_pose_source_v5"):
    pose_v2._fragmenter_base_load_pose_source_v5 = pose_v2.load_pose_source  # type: ignore[attr-defined]
_BASE_LOAD_POSE_SOURCE = pose_v2._fragmenter_base_load_pose_source_v5  # type: ignore[attr-defined]


def load_pose_source_recovered(path: str | Path):
    parsed = _BASE_LOAD_POSE_SOURCE(path)
    if not getattr(parsed, "indexed_setup_recovery_v2", None):
        summary = setup_recovery_v2.recover_report(parsed.source, parsed.data, parsed.report)
        setattr(parsed, "indexed_setup_recovery_v2", dict(summary))
    return parsed


pose_v2.load_pose_source = load_pose_source_recovered


def _recovered_by_id(context: Any, section_type: int) -> dict[int, dict[str, Any]]:
    return {
        int(record.get("object_id") or 0): record
        for record in context.report.records
        if int(record.get("masked_section_type") or 0) == int(section_type)
        and str(record.get("parse_status") or "") == "recovered_indexed_setup_record"
    }


def _annotate_rows(rows: list[dict[str, Any]], recovered: dict[int, dict[str, Any]]) -> None:
    for row in rows:
        record = recovered.get(int(row.get("object_id") or 0))
        if record is None:
            continue
        row["setup_recovered"] = True
        row["setup_recovery"] = dict(record.get("recovery") or {})
        row["setup_record_offset"] = int(record.get("offset") or 0)


# Preserve runtime v4's parsing authority, adding recovery evidence and immutable
# source-level decode reuse across animation frames.
if not hasattr(scene_core, "_fragmenter_base_parse_materials_v5"):
    scene_core._fragmenter_base_parse_materials_v5 = scene_core._parse_materials  # type: ignore[attr-defined]
if not hasattr(scene_core, "_fragmenter_base_parse_textures_v5"):
    scene_core._fragmenter_base_parse_textures_v5 = scene_core._parse_textures  # type: ignore[attr-defined]
_BASE_PARSE_MATERIALS = scene_core._fragmenter_base_parse_materials_v5  # type: ignore[attr-defined]
_BASE_PARSE_TEXTURES = scene_core._fragmenter_base_parse_textures_v5  # type: ignore[attr-defined]


def parse_materials_recovered(context: Any):
    key = _source_key(context)
    cached = _LOCAL_MATERIAL_CACHE.get(key)
    if cached is not None:
        return _copy_parse_result(cached)
    materials, rows = _BASE_PARSE_MATERIALS(context)
    _annotate_rows(rows, _recovered_by_id(context, structure.SECTION_MATERIAL))
    stored = (dict(materials), [dict(row) for row in rows])
    _LOCAL_MATERIAL_CACHE[key] = stored
    return _copy_parse_result(stored)


def parse_textures_recovered(context: Any):
    key = _source_key(context)
    cached = _LOCAL_TEXTURE_CACHE.get(key)
    if cached is not None:
        return _copy_parse_result(cached)
    textures, rows = _BASE_PARSE_TEXTURES(context)
    _annotate_rows(rows, _recovered_by_id(context, structure.SECTION_TEXTURE))
    stored = (dict(textures), [dict(row) for row in rows])
    _LOCAL_TEXTURE_CACHE[key] = stored
    return _copy_parse_result(stored)


scene_core._parse_materials = parse_materials_recovered
scene_core._parse_textures = parse_textures_recovered


if not hasattr(scene_v9, "_fragmenter_base_load_textured_scene_v5"):
    scene_v9._fragmenter_base_load_textured_scene_v5 = scene_v9.load_textured_scene  # type: ignore[attr-defined]
_BASE_LOAD_TEXTURED_SCENE = scene_v9._fragmenter_base_load_textured_scene_v5  # type: ignore[attr-defined]


def load_textured_scene_recovered(*args: Any, **kwargs: Any):
    scene = _BASE_LOAD_TEXTURED_SCENE(*args, **kwargs)
    summary = dict((scene.context.report.setup or {}).get("indexed_setup_recovery") or {})
    scene.summary["indexed_setup_recovery"] = summary
    scene.summary["recovered_material_records"] = int(summary.get("materials") or 0)
    scene.summary["recovered_texture_records"] = int(summary.get("textures") or 0)
    scene.summary["recovered_clut_records"] = int(summary.get("cluts") or 0)
    scene.summary["local_texture_decode_cache"] = "source-level immutable reuse"
    return scene


scene_v9.load_textured_scene = load_textured_scene_recovered


def trim_scene_cache_for_source(source: str | Path, keep_scene: Any = None) -> int:
    """Keep at most one staged scene for a source during textured animation."""
    resolved = str(Path(source).expanduser().resolve())
    removed = 0
    cache = scene_v9._SCENE_CACHE
    for key in list(cache):
        if key[0] != resolved or cache[key] is keep_scene:
            continue
        cache.pop(key, None)
        removed += 1
    return removed


def _clear_local_decode_cache(source: str | Path) -> tuple[int, int]:
    resolved = str(Path(source).expanduser().resolve())
    material_keys = [key for key in _LOCAL_MATERIAL_CACHE if key[0] == resolved]
    texture_keys = [key for key in _LOCAL_TEXTURE_CACHE if key[0] == resolved]
    for key in material_keys:
        _LOCAL_MATERIAL_CACHE.pop(key, None)
    for key in texture_keys:
        _LOCAL_TEXTURE_CACHE.pop(key, None)
    return len(material_keys), len(texture_keys)


def release_visual_source(source: str | Path | None) -> dict[str, int]:
    """Release heavy scene, pose and decoded texture data for the previous selection."""
    scene_entries = 0
    pose_entries = 0
    material_entries = 0
    texture_entries = 0
    if source:
        resolved = str(Path(source).expanduser().resolve())
        scene_entries = sum(1 for key in scene_v9._SCENE_CACHE if key[0] == resolved)
        pose_entries = sum(1 for key in pose_v2._SOURCE_CACHE if key[0] == resolved)
        scene_v9.clear_scene_cache(source)
        pose_v2.clear_pose_source_cache(source)
        material_entries, texture_entries = _clear_local_decode_cache(source)
    external = trim_external_texture_cache()
    return {
        "scene_entries_evicted": scene_entries,
        "pose_sources_evicted": pose_entries,
        "local_material_decodes_evicted": material_entries,
        "local_texture_decodes_evicted": texture_entries,
        "external_files_evicted": external,
    }


# Public GUI v19 calls runtime_v3 by name. Upgrade that call without rewriting the
# accepted review/context-menu layer.
runtime_v3.release_visual_source = release_visual_source
runtime_v4.release_visual_source = release_visual_source

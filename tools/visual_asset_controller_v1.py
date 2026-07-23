#!/usr/bin/env python3
"""Project-bound visual asset controller for CCSF 3D, textures, and animation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ccsf_structure_cache_v1 import CachedStructure, get_or_decode
from ccsf_visual_extract_v1 import (
    extract_animation_fast,
    extract_scene_fast,
    extract_textures_fast,
    fast_visual_index,
)
from project_preflight_v1 import resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1

DECODER_VERSION = "ccsf_record_index_v1"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_visual_asset(project: FragmenterProjectV1, value: str | Path) -> Path:
    paths = resolve_runtime_paths(project)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = paths.extracted_ccs / candidate
    candidate = candidate.resolve()
    if not _inside(candidate, paths.extracted_ccs):
        raise ValueError(f"Selected visual asset is outside the active project CCSF library: {candidate}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def visual_output_paths(project: FragmenterProjectV1, asset: str | Path) -> dict[str, Path]:
    source = resolve_visual_asset(project, asset)
    paths = resolve_runtime_paths(project)
    relative = source.relative_to(paths.extracted_ccs)
    stem = relative.with_suffix("")
    return {
        "structure_cache": paths.cache_ccsf_structure,
        "scene": paths.media_pipeline / "decoded" / "scenes" / stem,
        "textures": paths.texture_outputs / stem,
        "animations": paths.media_pipeline / "decoded" / "animations" / stem,
    }


def inspect_visual_structure(project: FragmenterProjectV1, asset: str | Path) -> CachedStructure:
    source = resolve_visual_asset(project, asset)
    paths = resolve_runtime_paths(project)
    return get_or_decode(
        source,
        paths.cache_ccsf_structure,
        decoder=fast_visual_index,
        decoder_version=DECODER_VERSION,
        options={"purpose": "visual_record_index", "model_geometry": False, "primitive_traces": False},
    )


def extract_visual_textures(project: FragmenterProjectV1, asset: str | Path) -> dict[str, Any]:
    source = resolve_visual_asset(project, asset)
    outputs = visual_output_paths(project, source)
    return extract_textures_fast(source, outputs["textures"])


def extract_visual_animation(project: FragmenterProjectV1, asset: str | Path) -> dict[str, Any]:
    source = resolve_visual_asset(project, asset)
    outputs = visual_output_paths(project, source)
    return extract_animation_fast(source, outputs["animations"])


def extract_visual_scene(project: FragmenterProjectV1, asset: str | Path) -> dict[str, Any]:
    source = resolve_visual_asset(project, asset)
    outputs = visual_output_paths(project, source)
    return extract_scene_fast(source, outputs["scene"])


def visual_asset_view_model(project: FragmenterProjectV1, asset: str | Path) -> dict[str, Any]:
    source = resolve_visual_asset(project, asset)
    cached = inspect_visual_structure(project, source)
    summary = cached.report.get("summary") if isinstance(cached.report.get("summary"), dict) else {}
    outputs = visual_output_paths(project, source)
    return {
        "source": str(source),
        "relative_path": source.relative_to(resolve_runtime_paths(project).extracted_ccs).as_posix(),
        "parser": "ccsf_record_index_v1",
        "full_model_decode_performed": False,
        "primitive_traces_collected": False,
        "cache_hit": cached.cache_hit,
        "cache_path": str(cached.cache_path),
        "summary": summary,
        "outputs": {key: str(path) for key, path in outputs.items()},
        "actions": {
            "inspect_structure": True,
            "extract_textures": True,
            "extract_animation_metadata": True,
            "extract_scene_metadata": True,
            "replace_texture": False,
            "replace_animation": False,
        },
    }

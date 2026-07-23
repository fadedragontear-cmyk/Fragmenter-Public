#!/usr/bin/env python3
"""Cached Gen1 pose-source parsing and cheap per-frame pose evaluation.

The binary and matrix semantics remain those implemented by ``ccsf_gen1_pose_v1``.
This layer separates immutable CCSF parsing from frame evaluation so animation
scrubbing does not decode the entire file for every frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v1 as v1
import ccsf_structure_decoder as base


@dataclass
class Gen1PoseSource:
    source: Path
    data: bytes
    report: Any
    objects: dict[int, dict[str, Any]]
    clumps: list[dict[str, Any]]
    clump_by_object: dict[int, dict[str, Any]]
    animations: list[dict[str, Any]]
    warnings: list[str]


_SOURCE_CACHE: dict[tuple[str, int, int], Gen1PoseSource] = {}


def _cache_key(source: Path) -> tuple[str, int, int]:
    stat = source.stat()
    return str(source.resolve()), stat.st_size, stat.st_mtime_ns


def clear_pose_source_cache(source: str | Path | None = None) -> None:
    if source is None:
        _SOURCE_CACHE.clear()
        return
    resolved = str(Path(source).expanduser().resolve())
    for key in [key for key in _SOURCE_CACHE if key[0] == resolved]:
        _SOURCE_CACHE.pop(key, None)


def load_pose_source(path: str | Path) -> Gen1PoseSource:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    key = _cache_key(source)
    cached = _SOURCE_CACHE.get(key)
    if cached is not None:
        return cached

    data = source.read_bytes()
    report = v1.decode_with_gen1_deformables(source)
    generation = str(report.header.get("generation") or "")
    if generation != "Gen1":
        raise v1.PoseDecodeError(f"Gen1 pose runtime does not support {generation or 'unknown generation'}")

    objects: dict[int, dict[str, Any]] = {}
    clumps: list[dict[str, Any]] = []
    warnings: list[str] = []
    for record in report.records:
        record_type = int(record.get("masked_section_type") or 0)
        try:
            if record_type == base.SECTION_OBJECT:
                row = v1.parse_object_record(data, record, generation)
                objects[int(row["object_id"])] = row
            elif record_type == base.SECTION_CLUMP:
                clumps.append(v1.parse_clump_record(data, record, generation))
        except Exception as exc:
            warnings.append(f"{record.get('object_name') or record.get('object_id')}: {exc}")

    clump_by_object: dict[int, dict[str, Any]] = {}
    for clump in clumps:
        for node_index, object_id in enumerate(clump.get("node_ids") or []):
            clump_by_object[int(object_id)] = {"clump": clump, "node_index": node_index}

    animations = v1.parse_gen1_animations(data, report)
    parsed = Gen1PoseSource(
        source=source,
        data=data,
        report=report,
        objects=objects,
        clumps=clumps,
        clump_by_object=clump_by_object,
        animations=animations,
        warnings=warnings,
    )
    _SOURCE_CACHE[key] = parsed
    return parsed


def build_pose_context(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> v1.Gen1PoseContext:
    parsed = load_pose_source(path)
    selected = v1.select_pose_animation(parsed.animations, animation_name)
    selected_frame = max(0, int(frame))
    local_poses: dict[int, dict[str, Any]] = {
        object_id: {
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "alpha": 1.0,
            "source": "Gen1 identity pose",
        }
        for object_id in parsed.objects
    }
    if selected is not None:
        frame_count = max(1, int(selected.get("frame_count") or 1))
        selected_frame %= frame_count
        for controller in selected.get("controllers") or []:
            target_id = controller.get("target_object_id")
            if not isinstance(target_id, int) or target_id not in local_poses:
                continue
            tracks = controller.get("tracks") or {}
            local_poses[target_id] = {
                "position": v1.evaluate_track(tracks["position"], selected_frame, frame_count),
                "rotation": v1.evaluate_track(tracks["rotation"], selected_frame, frame_count),
                "scale": v1.evaluate_track(tracks["scale"], selected_frame, frame_count),
                "alpha": v1.evaluate_track(tracks["alpha"], selected_frame, frame_count),
                "source": str(selected.get("object_name") or selected.get("object_id")),
            }

    local_matrices = {
        object_id: v1.pose_matrix(list(pose["position"]), list(pose["rotation"]), list(pose["scale"]))
        for object_id, pose in local_poses.items()
    }
    world_matrices: dict[int, list[list[float]]] = {}
    warnings = list(parsed.warnings)
    visiting: set[int] = set()

    def resolve_world(object_id: int) -> list[list[float]]:
        if object_id in world_matrices:
            return world_matrices[object_id]
        if object_id in visiting:
            warnings.append(f"object parent cycle while resolving {object_id}")
            return v1.identity_matrix()
        visiting.add(object_id)
        row = parsed.objects.get(object_id)
        local = local_matrices.get(object_id, v1.identity_matrix())
        parent_id = int((row or {}).get("parent_object_id") or 0)
        world = v1.matrix_multiply(local, resolve_world(parent_id)) if parent_id and parent_id in parsed.objects else local
        visiting.discard(object_id)
        world_matrices[object_id] = world
        return world

    for object_id in parsed.objects:
        resolve_world(object_id)

    return v1.Gen1PoseContext(
        source=parsed.source,
        data=parsed.data,
        report=parsed.report,
        objects=parsed.objects,
        clumps=parsed.clumps,
        clump_by_object=parsed.clump_by_object,
        animations=parsed.animations,
        selected_animation=selected,
        frame=selected_frame,
        local_poses=local_poses,
        world_matrices=world_matrices,
        warnings=warnings,
    )


# Re-export helpers used by the scene renderer and tests.
Gen1PoseContext = v1.Gen1PoseContext
pose_summary = v1.pose_summary
transformed_submodel_positions = v1.transformed_submodel_positions
select_pose_animation = v1.select_pose_animation

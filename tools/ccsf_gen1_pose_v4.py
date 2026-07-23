#!/usr/bin/env python3
"""OpenTK-compatible Gen1 CCSF pose evaluation.

StudioCCS reads Gen1 Euler tracks through Util.ReadVec3Rotation and constructs
``new Quaternion(Vector3)`` before building a row-major pose matrix.  Earlier
Fragmenter layers matched the axis fix but used a different Euler/quaternion
sign convention.  This layer keeps the parsed source and track evaluation
unchanged, then rebuilds local/world matrices with the OpenTK constructor math.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v1 as pose_v1
import ccsf_gen1_pose_v2 as pose_v2
import ccsf_gen1_pose_v3 as pose_v3

Gen1PoseContext = pose_v2.Gen1PoseContext
clear_pose_source_cache = pose_v2.clear_pose_source_cache
load_pose_source = pose_v2.load_pose_source
pose_summary = pose_v2.pose_summary
select_pose_animation = pose_v2.select_pose_animation
clump_node_object = pose_v3.clump_node_object


def opentk_quaternion_from_euler(rotation: list[float] | tuple[float, float, float]) -> tuple[float, float, float, float]:
    """Return ``Quaternion(Vector3)`` components from OpenTK's X->Y->Z formula."""
    rotation_x, rotation_y, rotation_z = (float(rotation[0]), float(rotation[1]), float(rotation[2]))
    rotation_x *= 0.5
    rotation_y *= 0.5
    rotation_z *= 0.5
    c1, c2, c3 = math.cos(rotation_x), math.cos(rotation_y), math.cos(rotation_z)
    s1, s2, s3 = math.sin(rotation_x), math.sin(rotation_y), math.sin(rotation_z)
    w = (c1 * c2 * c3) - (s1 * s2 * s3)
    x = (s1 * c2 * c3) + (c1 * s2 * s3)
    y = (c1 * s2 * c3) - (s1 * c2 * s3)
    z = (c1 * c2 * s3) + (s1 * s2 * c3)
    return x, y, z, w


def opentk_pose_matrix(position: list[float], rotation: list[float], scale: list[float]) -> list[list[float]]:
    """Mirror StudioCCS Scale * CreateFromQuaternion * Translation for row vectors."""
    x, y, z, w = opentk_quaternion_from_euler(rotation)
    length_squared = x * x + y * y + z * z + w * w
    s2 = 2.0 / length_squared if length_squared > 0.0 else 0.0
    rotation_matrix = [
        [1.0 - s2 * (y * y + z * z), s2 * (x * y + z * w), s2 * (x * z - y * w), 0.0],
        [s2 * (x * y - z * w), 1.0 - s2 * (x * x + z * z), s2 * (y * z + x * w), 0.0],
        [s2 * (x * z + y * w), s2 * (y * z - x * w), 1.0 - s2 * (x * x + y * y), 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    scale_matrix = pose_v1.identity_matrix()
    scale_matrix[0][0], scale_matrix[1][1], scale_matrix[2][2] = (float(scale[0]), float(scale[1]), float(scale[2]))
    translation = pose_v1.identity_matrix()
    translation[3][0], translation[3][1], translation[3][2] = (float(position[0]), float(position[1]), float(position[2]))
    return pose_v1.matrix_multiply(pose_v1.matrix_multiply(scale_matrix, rotation_matrix), translation)


def _rebuild_world_matrices(context: Gen1PoseContext) -> None:
    local_matrices = {
        object_id: opentk_pose_matrix(list(pose["position"]), list(pose["rotation"]), list(pose["scale"]))
        for object_id, pose in context.local_poses.items()
    }
    world_matrices: dict[int, list[list[float]]] = {}
    visiting: set[int] = set()

    def resolve_world(object_id: int) -> list[list[float]]:
        if object_id in world_matrices:
            return world_matrices[object_id]
        if object_id in visiting:
            context.warnings.append(f"object parent cycle while resolving {object_id}")
            return pose_v1.identity_matrix()
        visiting.add(object_id)
        row = context.objects.get(object_id)
        local = local_matrices.get(object_id, pose_v1.identity_matrix())
        parent_id = int((row or {}).get("parent_object_id") or 0)
        world = pose_v1.matrix_multiply(local, resolve_world(parent_id)) if parent_id and parent_id in context.objects else local
        visiting.discard(object_id)
        world_matrices[object_id] = world
        return world

    for object_id in context.objects:
        resolve_world(object_id)
    context.world_matrices = world_matrices


def build_pose_context(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> Gen1PoseContext:
    context = pose_v2.build_pose_context(path, animation_name=animation_name, frame=frame)
    _rebuild_world_matrices(context)
    return context


def transformed_submodel_positions(
    context: Gen1PoseContext,
    *,
    model_id: int,
    submodel: dict[str, Any],
    owner_object_id: int | None = None,
    clump: dict[str, Any] | None = None,
) -> list[tuple[float, float, float]]:
    return pose_v3.transformed_submodel_positions(
        context,
        model_id=model_id,
        submodel=submodel,
        owner_object_id=owner_object_id,
        clump=clump,
    )

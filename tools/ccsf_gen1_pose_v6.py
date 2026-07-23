#!/usr/bin/env python3
"""Gen1 CCSF puppetry using Euler tracks and explicit axis-angle matrices.

The source controller payload stores three Euler components for Gen1.  Earlier
Fragmenter layers converted those components to an OpenTK-style quaternion before
building a matrix.  This layer keeps the rotation as Euler data throughout track
evaluation, interpolates each component on its shortest angular arc, then composes
row-vector X, Y and Z axis-angle matrices directly.

This is intentionally isolated as a new layer so the previous quaternion path remains
available for comparison while animation research is still active.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

import ccsf_gen1_pose_v1 as pose_v1
import ccsf_gen1_pose_v2 as pose_v2
import ccsf_gen1_pose_v3 as pose_v3
import ccsf_gen1_pose_v5 as pose_v5

Gen1PoseContext = pose_v2.Gen1PoseContext
clear_pose_source_cache = pose_v2.clear_pose_source_cache
load_pose_source = pose_v2.load_pose_source
transformed_submodel_positions = pose_v3.transformed_submodel_positions
clump_node_object = pose_v3.clump_node_object
INITIAL_POSE_NAME = pose_v5.INITIAL_POSE_NAME
INITIAL_POSE_TOKEN = pose_v5.INITIAL_POSE_TOKEN
is_initial_pose_name = pose_v5.is_initial_pose_name
select_pose_animation = pose_v5.select_pose_animation

ROTATION_PIPELINE = (
    "Gen1 Euler radians -> shortest-arc component interpolation -> "
    "row-vector X/Y/Z axis-angle matrices -> local * parent hierarchy"
)


def _finite3(value: Iterable[float], fallback: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    try:
        rows = tuple(float(component) for component in value)
    except (TypeError, ValueError):
        return fallback
    if len(rows) != 3 or not all(math.isfinite(component) for component in rows):
        return fallback
    return rows[0], rows[1], rows[2]


def axis_angle_matrix(axis: Iterable[float], angle: float) -> list[list[float]]:
    """Create a row-vector rotation matrix from one normalized axis and angle."""
    x, y, z = _finite3(axis)
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 1e-12 or not math.isfinite(float(angle)):
        return pose_v1.identity_matrix()
    x, y, z = x / length, y / length, z / length
    cosine = math.cos(float(angle))
    sine = math.sin(float(angle))
    one_minus = 1.0 - cosine
    # Transposed Rodrigues matrix because Fragmenter/StudioCCS transform row vectors.
    return [
        [one_minus * x * x + cosine, one_minus * x * y + sine * z, one_minus * x * z - sine * y, 0.0],
        [one_minus * x * y - sine * z, one_minus * y * y + cosine, one_minus * y * z + sine * x, 0.0],
        [one_minus * x * z + sine * y, one_minus * y * z - sine * x, one_minus * z * z + cosine, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def euler_axis_angle_matrix(rotation: Iterable[float]) -> list[list[float]]:
    """Compose source Euler components as explicit local X, Y and Z rotations.

    With row vectors, ``Rx * Ry * Rz`` applies the source components in X/Y/Z order.
    No quaternion is constructed or interpolated.
    """
    x, y, z = _finite3(rotation)
    matrix = pose_v1.identity_matrix()
    for axis, angle in (((1.0, 0.0, 0.0), x), ((0.0, 1.0, 0.0), y), ((0.0, 0.0, 1.0), z)):
        matrix = pose_v1.matrix_multiply(matrix, axis_angle_matrix(axis, angle))
    return matrix


def axis_angle_pose_matrix(position: Iterable[float], rotation: Iterable[float], scale: Iterable[float]) -> list[list[float]]:
    position3 = _finite3(position)
    scale3 = _finite3(scale, (1.0, 1.0, 1.0))
    scale_matrix = pose_v1.identity_matrix()
    scale_matrix[0][0], scale_matrix[1][1], scale_matrix[2][2] = scale3
    translation = pose_v1.identity_matrix()
    translation[3][0], translation[3][1], translation[3][2] = position3
    return pose_v1.matrix_multiply(
        pose_v1.matrix_multiply(scale_matrix, euler_axis_angle_matrix(rotation)),
        translation,
    )


def _shortest_delta(left: float, right: float) -> float:
    return (float(right) - float(left) + math.pi) % (2.0 * math.pi) - math.pi


def _track_key_pair(track: dict[str, Any], frame: int, frame_count: int) -> tuple[dict[str, Any], dict[str, Any], float] | None:
    keys = list(track.get("keys") or [])
    if len(keys) < 2:
        return None
    current_index = 0
    for index, key in enumerate(keys):
        if int(key.get("frame") or 0) <= int(frame):
            current_index = index
        else:
            break
    current = keys[current_index]
    if current_index + 1 < len(keys):
        following = keys[current_index + 1]
        start = int(current.get("frame") or 0)
        finish = int(following.get("frame") or 0)
        amount = (int(frame) - start) / float(max(1, finish - start))
    else:
        following = keys[0]
        start = int(current.get("frame") or 0)
        finish = max(start + 1, int(frame_count))
        amount = (int(frame) - start) / float(max(1, finish - start))
    return current, following, max(0.0, min(1.0, amount))


def evaluate_euler_track(track: dict[str, Any], frame: int, frame_count: int) -> list[float]:
    """Evaluate an Euler track without quaternion interpolation.

    Sparse keyframes interpolate each component along the shortest angular arc.  Fixed,
    missing and one-key tracks retain the established values.
    """
    status = str(track.get("status") or "")
    if status == "fixed":
        return list(_finite3(track.get("fixed") or (0.0, 0.0, 0.0)))
    keys = list(track.get("keys") or [])
    if status != "animated" or not keys:
        return list(_finite3(track.get("default") or (0.0, 0.0, 0.0)))
    if len(keys) == 1:
        return list(_finite3(keys[0].get("value") or (0.0, 0.0, 0.0)))
    pair = _track_key_pair(track, frame, frame_count)
    if pair is None:
        return list(_finite3(keys[0].get("value") or (0.0, 0.0, 0.0)))
    current, following, amount = pair
    left = _finite3(current.get("value") or (0.0, 0.0, 0.0))
    right = _finite3(following.get("value") or (0.0, 0.0, 0.0))
    return [left[index] + _shortest_delta(left[index], right[index]) * amount for index in range(3)]


def _world_matrices(
    objects: dict[int, dict[str, Any]],
    local_poses: dict[int, dict[str, Any]],
    warnings: list[str],
) -> dict[int, list[list[float]]]:
    local_matrices = {
        object_id: axis_angle_pose_matrix(pose["position"], pose["rotation"], pose["scale"])
        for object_id, pose in local_poses.items()
    }
    world: dict[int, list[list[float]]] = {}
    visiting: set[int] = set()

    def resolve(object_id: int) -> list[list[float]]:
        if object_id in world:
            return world[object_id]
        if object_id in visiting:
            warnings.append(f"object parent cycle while resolving {object_id}")
            return pose_v1.identity_matrix()
        visiting.add(object_id)
        row = objects.get(object_id)
        local = local_matrices.get(object_id, pose_v1.identity_matrix())
        parent_id = int((row or {}).get("parent_object_id") or 0)
        matrix = pose_v1.matrix_multiply(local, resolve(parent_id)) if parent_id and parent_id in objects else local
        visiting.discard(object_id)
        world[object_id] = matrix
        return matrix

    for object_id in objects:
        resolve(object_id)
    return world


def build_pose_context(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> Gen1PoseContext:
    parsed = pose_v2.load_pose_source(path)
    selected = select_pose_animation(parsed.animations, animation_name)
    selected_frame = max(0, int(frame))
    local_poses: dict[int, dict[str, Any]] = {
        object_id: {
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "alpha": 1.0,
            "source": "Gen1 source identity pose",
            "rotation_pipeline": ROTATION_PIPELINE,
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
                "position": pose_v1.evaluate_track(tracks["position"], selected_frame, frame_count),
                "rotation": evaluate_euler_track(tracks["rotation"], selected_frame, frame_count),
                "scale": pose_v1.evaluate_track(tracks["scale"], selected_frame, frame_count),
                "alpha": pose_v1.evaluate_track(tracks["alpha"], selected_frame, frame_count),
                "source": str(selected.get("object_name") or selected.get("object_id")),
                "rotation_pipeline": ROTATION_PIPELINE,
            }

    warnings = list(parsed.warnings)
    return pose_v1.Gen1PoseContext(
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
        world_matrices=_world_matrices(parsed.objects, local_poses, warnings),
        warnings=warnings,
    )


def _track_summary(track: dict[str, Any]) -> dict[str, Any]:
    keys = list(track.get("keys") or [])
    return {
        "status": track.get("status"),
        "key_count": int(track.get("key_count") or len(keys)),
        "key_frames": [int(key.get("frame") or 0) for key in keys],
        "fixed": track.get("fixed"),
        "first_value": keys[0].get("value") if keys else None,
        "last_value": keys[-1].get("value") if keys else None,
    }


def puppetry_rows(context: Gen1PoseContext) -> list[dict[str, Any]]:
    """Return evaluated per-part controller bindings for the selected frame."""
    selected = context.selected_animation or {}
    rows: list[dict[str, Any]] = []
    children_by_parent: dict[int, list[int]] = {}
    for object_id, object_row in context.objects.items():
        parent_id = int(object_row.get("parent_object_id") or 0)
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(object_id)
    for controller in selected.get("controllers") or []:
        target_id = controller.get("target_object_id")
        if not isinstance(target_id, int):
            continue
        target = context.objects.get(target_id) or {}
        parent_id = int(target.get("parent_object_id") or 0)
        membership = context.clump_by_object.get(target_id) or {}
        clump = membership.get("clump") if isinstance(membership, dict) else None
        pose = context.local_poses.get(target_id) or {}
        rotation = list(_finite3(pose.get("rotation") or (0.0, 0.0, 0.0)))
        tracks = controller.get("tracks") or {}
        rows.append(
            {
                "target_object_id": target_id,
                "target_object_name": str(controller.get("target_object_name") or (context.report.object_lookup.get(target_id) or {}).get("name") or ""),
                "parent_object_id": parent_id,
                "parent_object_name": str((context.report.object_lookup.get(parent_id) or {}).get("name") or "") if parent_id else "",
                "child_object_ids": sorted(children_by_parent.get(target_id, [])),
                "clump_id": int((clump or {}).get("object_id") or 0),
                "clump_name": str((clump or {}).get("object_name") or ""),
                "clump_node_index": membership.get("node_index") if isinstance(membership, dict) else None,
                "position": list(pose.get("position") or [0.0, 0.0, 0.0]),
                "rotation_radians": rotation,
                "rotation_degrees": [math.degrees(value) for value in rotation],
                "scale": list(pose.get("scale") or [1.0, 1.0, 1.0]),
                "alpha": float(pose.get("alpha") if pose.get("alpha") is not None else 1.0),
                "tracks": {name: _track_summary(track) for name, track in tracks.items() if isinstance(track, dict)},
                "local_matrix": axis_angle_pose_matrix(
                    pose.get("position") or [0.0, 0.0, 0.0],
                    rotation,
                    pose.get("scale") or [1.0, 1.0, 1.0],
                ),
                "world_matrix": context.world_matrices.get(target_id, pose_v1.identity_matrix()),
                "rotation_pipeline": ROTATION_PIPELINE,
            }
        )
    return rows


def pose_summary(context: Gen1PoseContext) -> dict[str, Any]:
    summary = pose_v5.pose_summary(context)
    puppet_rows = puppetry_rows(context)
    summary.update(
        {
            "rotation_storage": "three Gen1 Euler float components (axis-fixed to radians)",
            "rotation_pipeline": ROTATION_PIPELINE,
            "rotation_quaternion_used": False,
            "puppetry_bindings": len(puppet_rows),
            "puppetry_clumps": len({row["clump_id"] for row in puppet_rows if row["clump_id"]}),
            "puppetry_parented_parts": sum(bool(row["parent_object_id"]) for row in puppet_rows),
        }
    )
    return summary

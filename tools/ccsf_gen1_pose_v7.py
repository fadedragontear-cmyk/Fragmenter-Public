#!/usr/bin/env python3
"""Live Euler mapping/order/sign/hierarchy experiments for Gen1 puppetry.

This layer leaves the accepted v6 implementation intact and changes only the active
preview runtime. Tester choices are session-only and are never written to annotations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import ccsf_euler_test_v1 as euler_test
import ccsf_gen1_pose_v6 as base

Gen1PoseContext = base.Gen1PoseContext
clear_pose_source_cache = base.clear_pose_source_cache
load_pose_source = base.load_pose_source
transformed_submodel_positions = base.transformed_submodel_positions
clump_node_object = base.clump_node_object
INITIAL_POSE_NAME = base.INITIAL_POSE_NAME
INITIAL_POSE_TOKEN = base.INITIAL_POSE_TOKEN
is_initial_pose_name = base.is_initial_pose_name
select_pose_animation = base.select_pose_animation
axis_angle_matrix = base.axis_angle_matrix
evaluate_euler_track = base.evaluate_euler_track
pose_v1 = base.pose_v1
pose_v2 = base.pose_v2

ROTATION_PIPELINE = euler_test.pipeline_label()


def _refresh_pipeline() -> str:
    global ROTATION_PIPELINE
    ROTATION_PIPELINE = euler_test.pipeline_label()
    return ROTATION_PIPELINE


def euler_test_profile() -> dict[str, str]:
    return euler_test.get_profile()


def set_euler_test_profile(
    *,
    component_map: str | None = None,
    order: str | None = None,
    signs: str | None = None,
    parent_mode: str | None = None,
) -> dict[str, str]:
    profile = euler_test.set_profile(
        component_map=component_map,
        order=order,
        signs=signs,
        parent_mode=parent_mode,
    )
    _refresh_pipeline()
    return profile


def reset_euler_test_profile() -> dict[str, str]:
    profile = euler_test.reset_profile()
    _refresh_pipeline()
    return profile


def studio_ccs_euler_test_profile() -> dict[str, str]:
    profile = euler_test.studio_ccs_profile()
    _refresh_pipeline()
    return profile


def euler_axis_angle_matrix(rotation: Iterable[float]) -> list[list[float]]:
    active = euler_test.get_profile()
    mapped = euler_test.mapped_components(rotation, active)
    axes = {
        "X": (1.0, 0.0, 0.0),
        "Y": (0.0, 1.0, 0.0),
        "Z": (0.0, 0.0, 1.0),
    }
    matrix = pose_v1.identity_matrix()
    for axis_name in active["order"]:
        matrix = pose_v1.matrix_multiply(
            matrix,
            axis_angle_matrix(axes[axis_name], mapped[axis_name]),
        )
    return matrix


def axis_angle_pose_matrix(
    position: Iterable[float],
    rotation: Iterable[float],
    scale: Iterable[float],
) -> list[list[float]]:
    position3 = base._finite3(position)
    scale3 = base._finite3(scale, (1.0, 1.0, 1.0))
    scale_matrix = pose_v1.identity_matrix()
    scale_matrix[0][0], scale_matrix[1][1], scale_matrix[2][2] = scale3
    translation = pose_v1.identity_matrix()
    translation[3][0], translation[3][1], translation[3][2] = position3
    return pose_v1.matrix_multiply(
        pose_v1.matrix_multiply(scale_matrix, euler_axis_angle_matrix(rotation)),
        translation,
    )


def _world_matrices(
    objects: dict[int, dict[str, Any]],
    local_poses: dict[int, dict[str, Any]],
    warnings: list[str],
) -> dict[int, list[list[float]]]:
    local_matrices = {
        object_id: axis_angle_pose_matrix(pose["position"], pose["rotation"], pose["scale"])
        for object_id, pose in local_poses.items()
    }
    active = euler_test.get_profile()
    parent_first = active["parent_mode"] == "PXL"
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
        if parent_id and parent_id in objects:
            parent = resolve(parent_id)
            matrix = (
                pose_v1.matrix_multiply(parent, local)
                if parent_first
                else pose_v1.matrix_multiply(local, parent)
            )
        else:
            matrix = local
        visiting.discard(object_id)
        world[object_id] = matrix
        return matrix

    for object_id in objects:
        resolve(object_id)
    return world


def build_pose_context(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
) -> Gen1PoseContext:
    parsed = pose_v2.load_pose_source(path)
    selected = select_pose_animation(parsed.animations, animation_name)
    selected_frame = max(0, int(frame))
    pipeline = _refresh_pipeline()
    local_poses: dict[int, dict[str, Any]] = {
        object_id: {
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "alpha": 1.0,
            "source": "Gen1 source identity pose",
            "rotation_pipeline": pipeline,
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
                "rotation_pipeline": pipeline,
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


def puppetry_rows(context: Gen1PoseContext) -> list[dict[str, Any]]:
    rows = base.puppetry_rows(context)
    pipeline = _refresh_pipeline()
    for row in rows:
        target_id = int(row.get("target_object_id") or 0)
        pose = context.local_poses.get(target_id) or {}
        rotation = pose.get("rotation") or [0.0, 0.0, 0.0]
        row["local_matrix"] = axis_angle_pose_matrix(
            pose.get("position") or [0.0, 0.0, 0.0],
            rotation,
            pose.get("scale") or [1.0, 1.0, 1.0],
        )
        row["world_matrix"] = context.world_matrices.get(target_id, pose_v1.identity_matrix())
        row["rotation_pipeline"] = pipeline
        row["euler_test_profile"] = euler_test.get_profile()
    return rows


def pose_summary(context: Gen1PoseContext) -> dict[str, Any]:
    summary = base.pose_summary(context)
    rows = puppetry_rows(context)
    summary.update(
        {
            "rotation_pipeline": _refresh_pipeline(),
            "rotation_quaternion_used": False,
            "euler_test_profile": euler_test.get_profile(),
            "puppetry_bindings": len(rows),
        }
    )
    return summary

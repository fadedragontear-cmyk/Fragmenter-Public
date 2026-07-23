#!/usr/bin/env python3
"""Explicit initial-pose and animation evaluation for Gen1 CCSF previews.

Earlier preview layers treated a missing animation name as permission to select a
``nut`` animation or the animation with the most controllers. That made it
impossible to inspect the source identity arrangement. This layer makes initial
pose an explicit mode while retaining the OpenTK-compatible matrices.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v1 as pose_v1
import ccsf_gen1_pose_v2 as pose_v2
import ccsf_gen1_pose_v4 as pose_v4

Gen1PoseContext = pose_v2.Gen1PoseContext
clear_pose_source_cache = pose_v2.clear_pose_source_cache
load_pose_source = pose_v2.load_pose_source
transformed_submodel_positions = pose_v4.transformed_submodel_positions
clump_node_object = pose_v4.clump_node_object

INITIAL_POSE_NAME = "Initial Pose"
INITIAL_POSE_TOKEN = "__fragmenter_initial_pose__"


def is_initial_pose_name(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    return text in {"", INITIAL_POSE_NAME.lower(), INITIAL_POSE_TOKEN.lower(), "identity", "bind pose", "initial"}


def select_pose_animation(animations: list[dict[str, Any]], preferred_name: str | None = None) -> dict[str, Any] | None:
    if is_initial_pose_name(preferred_name):
        return None
    return pose_v1.select_pose_animation(animations, preferred_name)


def _world_matrices(
    objects: dict[int, dict[str, Any]],
    local_poses: dict[int, dict[str, Any]],
    warnings: list[str],
) -> dict[int, list[list[float]]]:
    local_matrices = {
        object_id: pose_v4.opentk_pose_matrix(
            list(pose["position"]),
            list(pose["rotation"]),
            list(pose["scale"]),
        )
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
                "rotation": pose_v1.evaluate_track(tracks["rotation"], selected_frame, frame_count),
                "scale": pose_v1.evaluate_track(tracks["scale"], selected_frame, frame_count),
                "alpha": pose_v1.evaluate_track(tracks["alpha"], selected_frame, frame_count),
                "source": str(selected.get("object_name") or selected.get("object_id")),
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


def pose_summary(context: Gen1PoseContext) -> dict[str, Any]:
    summary = pose_v2.pose_summary(context)
    summary["pose_mode"] = "animation" if context.selected_animation is not None else "initial_identity"
    summary["selected_animation"] = (context.selected_animation or {}).get("object_name") or INITIAL_POSE_NAME
    controlled = {
        int(controller["target_object_id"])
        for controller in (context.selected_animation or {}).get("controllers") or []
        if isinstance(controller.get("target_object_id"), int) and int(controller["target_object_id"]) in context.objects
    }
    summary["controlled_objects"] = len(controlled)
    summary["posed_object_count"] = len(controlled)
    summary["uncontrolled_objects"] = max(0, len(context.objects) - len(controlled))
    summary["initial_pose_is_identity"] = context.selected_animation is None
    return summary

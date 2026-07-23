#!/usr/bin/env python3
"""Instance-aware Gen1 pose transforms for clump-authoritative previews."""
from __future__ import annotations

from typing import Any

import ccsf_gen1_pose_v1 as pose_v1
import ccsf_gen1_pose_v2 as pose_v2

Gen1PoseContext = pose_v2.Gen1PoseContext
build_pose_context = pose_v2.build_pose_context
clear_pose_source_cache = pose_v2.clear_pose_source_cache
load_pose_source = pose_v2.load_pose_source
pose_summary = pose_v2.pose_summary
select_pose_animation = pose_v2.select_pose_animation


def clump_node_object(
    context: Gen1PoseContext,
    owner_object_id: int | None,
    node_index: int,
    *,
    clump: dict[str, Any] | None = None,
) -> int | None:
    active_clump = clump
    if active_clump is None and owner_object_id is not None:
        membership = context.clump_by_object.get(owner_object_id)
        active_clump = membership.get("clump") if isinstance(membership, dict) else None
    nodes = active_clump.get("node_ids") if isinstance(active_clump, dict) else None
    if not isinstance(nodes, list) or not (0 <= int(node_index) < len(nodes)):
        return None
    return int(nodes[int(node_index)])


def transformed_submodel_positions(
    context: Gen1PoseContext,
    *,
    model_id: int,
    submodel: dict[str, Any],
    owner_object_id: int | None = None,
    clump: dict[str, Any] | None = None,
) -> list[tuple[float, float, float]]:
    owner_id = int(owner_object_id) if owner_object_id is not None else pose_v1.model_owner_object(context, model_id)
    parser_mode = str(submodel.get("parser_mode") or "")
    vertices = list(submodel.get("vertices") or [])
    output: list[tuple[float, float, float]] = []

    if parser_mode == "studioccs_gen1_deform_weighted":
        for vertex in vertices:
            bone_ids = list(vertex.get("bone_ids") or [0, 0])
            weights = list(vertex.get("weights") or [1.0, 0.0])
            positions = [vertex.get("position") or [0.0, 0.0, 0.0], vertex.get("position2") or [0.0, 0.0, 0.0]]
            total = [0.0, 0.0, 0.0]
            applied = False
            for index in range(2):
                weight = float(weights[index] if index < len(weights) else 0.0)
                if weight == 0.0:
                    continue
                node_index = int(bone_ids[index] if index < len(bone_ids) else 0)
                object_id = clump_node_object(context, owner_id, node_index, clump=clump)
                matrix = context.world_matrices.get(object_id, pose_v1.identity_matrix())
                transformed = pose_v1.transform_point(positions[index], matrix)
                total[0] += transformed[0] * weight
                total[1] += transformed[1] * weight
                total[2] += transformed[2] * weight
                applied = True
            output.append(tuple(total) if applied else tuple(float(value) for value in positions[0]))
        return output

    if parser_mode == "studioccs_gen1_deform_rigid":
        node_index = int(submodel.get("parent_id") or 0)
        object_id = clump_node_object(context, owner_id, node_index, clump=clump)
        matrix = context.world_matrices.get(object_id, pose_v1.identity_matrix())
    else:
        # StudioCCS binds a rigid model to the actual CCSObject instance reached
        # through CCSClump.Render.  Do not reinterpret a model/submodel field as a
        # global object owner when the clump traversal already supplied the owner.
        object_id = owner_id
        matrix = context.world_matrices.get(object_id, pose_v1.identity_matrix())

    for vertex in vertices:
        point = vertex.get("position") if isinstance(vertex, dict) else vertex
        if isinstance(point, (list, tuple)) and len(point) >= 3:
            output.append(pose_v1.transform_point(point, matrix))
    return output

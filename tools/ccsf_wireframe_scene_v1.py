#!/usr/bin/env python3
"""Fast texture-free wireframe payload from the authoritative clump scene."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v4 as pose_v4
import ccsf_textured_scene_v5 as scene_v5
from ccsf_clump_instances_v1 import iter_clump_model_instances, select_preview_clump


def load_clump_wireframe_payload(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    face_cap: int = 30_000,
) -> dict[str, Any]:
    context = pose_v4.build_pose_context(path, animation_name=animation_name, frame=frame)
    preferred = scene_v5.preferred_clump_id(context.source)
    selected = select_preview_clump(context, preferred)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    face_total = 0
    instances: list[dict[str, Any]] = []

    for instance in iter_clump_model_instances(context, preferred):
        submodel_indices: list[int] = []
        for submodel in instance["model"].get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = pose_v4.transformed_submodel_positions(
                context,
                model_id=int(instance["model_id"]),
                submodel=submodel,
                owner_object_id=int(instance["object_id"]),
                clump=instance.get("clump"),
            )
            base_index = len(vertices)
            vertices.extend(tuple(float(value) for value in position[:3]) for position in positions)
            for face in submodel.get("faces") or []:
                face_total += 1
                if len(faces) >= max(1, int(face_cap)):
                    continue
                if not isinstance(face, (list, tuple)) or len(face) < 3:
                    continue
                indices = (int(face[0]), int(face[1]), int(face[2]))
                if all(0 <= index < len(positions) for index in indices):
                    faces.append(tuple(base_index + index for index in indices))
            submodel_indices.append(int(submodel.get("index") or 0))
        instances.append(
            {
                "clump_id": instance.get("clump_id"),
                "clump_name": instance.get("clump_name"),
                "clump_node_index": instance.get("node_index"),
                "object_id": instance.get("object_id"),
                "object_name": instance.get("object_name"),
                "model_id": instance.get("model_id"),
                "model_name": instance.get("model_name"),
                "submodels": submodel_indices,
            }
        )

    summary = pose_v4.pose_summary(context)
    summary.update(
        {
            "selected_clump_id": int(selected.get("object_id") or 0) if selected is not None else None,
            "selected_clump_name": str(selected.get("object_name") or "") if selected is not None else "",
            "selected_clump_node_count": len(selected.get("node_ids") or []) if selected is not None else 0,
            "instance_count": len(instances),
            "instances": instances,
        }
    )
    return {
        "source": str(context.source),
        "vertices": vertices,
        "faces": faces,
        "vertex_count": len(vertices),
        "face_count": len(faces),
        "decoded_face_count": face_total,
        "displayed_face_count": len(faces),
        "parser": "clump_instance_wireframe_v1",
        "selected_animation": summary.get("selected_animation"),
        "frame": summary.get("frame", 0),
        "face_cap_applied": face_total > int(face_cap),
        "scene_summary": summary,
    }

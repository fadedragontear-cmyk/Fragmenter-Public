#!/usr/bin/env python3
"""Fast geometry-only whole-file CCSF wireframe assembly.

The v13 wireframe path accidentally called the complete textured-scene builder.
That meant an asset click could decode every local texture and start cross-file
MAT/TEX/CLUT discovery before a wireframe appeared.  This module keeps pose and
clump instance traversal identical to the textured scene while never parsing or
resolving textures.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v5 as pose_v5
import ccsf_textured_scene_v8 as scene_v8


def load_complete_wireframe_payload(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    assembly: str | None = None,
    clump_id: int | None = None,
    face_cap: int = 60_000,
) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    mode = (
        scene_v8.SELECTED_CLUMP
        if str(assembly or scene_v8.assembly_mode(source)).strip().lower() == scene_v8.SELECTED_CLUMP
        else scene_v8.WHOLE_FILE
    )
    preferred = int(clump_id) if clump_id is not None else scene_v8.preferred_clump_id(source)
    context = pose_v5.build_pose_context(source, animation_name=animation_name, frame=frame)
    instances = list(scene_v8._iter_instances(context, mode, preferred))

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    decoded_face_count = 0
    invalid_face_count = 0
    cap = max(1, int(face_cap))

    for instance in instances:
        model_id = int(instance["model_id"])
        for submodel in instance["model"].get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = pose_v5.transformed_submodel_positions(
                context,
                model_id=model_id,
                submodel=submodel,
                owner_object_id=int(instance["object_id"]),
                clump=instance.get("clump"),
            )
            base_index = len(vertices)
            vertices.extend(tuple(float(value) for value in position[:3]) for position in positions)
            for face in submodel.get("faces") or []:
                if not isinstance(face, (list, tuple)) or len(face) < 3:
                    invalid_face_count += 1
                    continue
                indices = (int(face[0]), int(face[1]), int(face[2]))
                if not all(0 <= index < len(positions) for index in indices):
                    invalid_face_count += 1
                    continue
                decoded_face_count += 1
                if len(faces) < cap:
                    faces.append(tuple(base_index + index for index in indices))

    summary = {
        **pose_v5.pose_summary(context),
        **scene_v8._instance_summary(context, instances, mode, preferred),
        "geometry_only": True,
        "texture_decode_performed": False,
        "decoded_vertices": len(vertices),
        "decoded_faces": decoded_face_count,
        "submitted_faces": len(faces),
        "invalid_faces": invalid_face_count,
        "face_cap": cap,
        "face_cap_applied": decoded_face_count > cap,
    }
    return {
        "source": str(source),
        "vertices": vertices,
        "faces": faces,
        "vertex_count": len(vertices),
        "face_count": len(faces),
        "decoded_face_count": decoded_face_count,
        "parser": "geometry_only_whole_file_wireframe_v2",
        "selected_animation": summary.get("selected_animation"),
        "frame": summary.get("frame", 0),
        "face_cap_applied": decoded_face_count > cap,
        "scene_summary": summary,
    }

#!/usr/bin/env python3
"""V4 CCSF preview integration: cached poses, expanded textures and wire payloads."""
from __future__ import annotations

from typing import Any

import ccsf_gen1_pose_v2 as pose_v2
import ccsf_texture_decoder_v2 as texture_v2
import ccsf_textured_scene_v3 as v3

# V3 resolves these globals at call time. Keep the proven scene/rasterizer logic and
# replace only the source decoders used to build a scene.
v3.build_pose_context = pose_v2.build_pose_context
v3.parse_texture_record = texture_v2.parse_texture_record
v3.decode_rgba = texture_v2.decode_rgba
v3.parse_clut_record = texture_v2.parse_clut_record

TexturedScene = v3.TexturedScene
clear_scene_cache = v3.clear_scene_cache
load_textured_scene = v3.load_textured_scene
render_textured_scene = v3.render_textured_scene
export_scene_textures = v3.export_scene_textures


def animation_rows(path: str) -> list[dict[str, Any]]:
    parsed = pose_v2.load_pose_source(path)
    rows: list[dict[str, Any]] = []
    for animation in parsed.animations:
        rows.append(
            {
                "object_id": animation.get("object_id"),
                "object_name": animation.get("object_name"),
                "frame_count": int(animation.get("frame_count") or 0),
                "playback_name": animation.get("playback_name"),
                "controller_count": int(animation.get("controller_count") or 0),
                "pose_ready": bool(animation.get("pose_ready")),
                "warnings": list(animation.get("warnings") or []),
            }
        )
    return rows


def _wireframe_from_context(context, *, face_cap: int) -> dict[str, Any]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    face_total = 0
    for record in context.report.records:
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if not model:
            continue
        model_id = int(record.get("object_id") or 0)
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = pose_v2.transformed_submodel_positions(context, model_id=model_id, submodel=submodel)
            base_index = len(vertices)
            vertices.extend(tuple(float(value) for value in position[:3]) for position in positions)
            for face in submodel.get("faces") or []:
                face_total += 1
                if len(faces) >= face_cap:
                    continue
                if not isinstance(face, (list, tuple)) or len(face) < 3:
                    continue
                indices = (int(face[0]), int(face[1]), int(face[2]))
                if all(0 <= index < len(positions) for index in indices):
                    faces.append(tuple(base_index + index for index in indices))
    summary = pose_v2.pose_summary(context)
    return {
        "source": str(context.source),
        "vertices": vertices,
        "faces": faces,
        "vertex_count": len(vertices),
        "face_count": len(faces),
        "parser": "pose_only_wireframe_v4",
        "selected_animation": summary.get("selected_animation"),
        "frame": summary.get("frame", 0),
        "face_cap_applied": face_total > face_cap,
        "scene_summary": summary,
    }


def load_posed_wireframe_payload(
    path: str,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    face_cap: int = 30_000,
) -> dict[str, Any]:
    """Evaluate one pose without parsing textures or constructing textured triangles."""
    context = pose_v2.build_pose_context(path, animation_name=animation_name, frame=frame)
    return _wireframe_from_context(context, face_cap=max(1, int(face_cap)))


def scene_wireframe_payload(scene: TexturedScene, *, face_cap: int = 30_000) -> dict[str, Any]:
    """Build a posed wireframe payload from the exact scene triangles.

    Positions are de-duplicated by exact decoded float tuples. This is intended for
    interactive animation/camera preview; the texture rasterizer remains the source
    for textured output.
    """
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    by_position: dict[tuple[float, float, float], int] = {}
    for triangle in scene.triangles[: max(1, int(face_cap))]:
        indices: list[int] = []
        for raw in triangle.get("positions") or ():
            position = (float(raw[0]), float(raw[1]), float(raw[2]))
            index = by_position.get(position)
            if index is None:
                index = len(vertices)
                by_position[position] = index
                vertices.append(position)
            indices.append(index)
        if len(indices) == 3:
            faces.append((indices[0], indices[1], indices[2]))
    return {
        "source": str(scene.source),
        "vertices": vertices,
        "faces": faces,
        "vertex_count": len(vertices),
        "face_count": len(faces),
        "parser": "posed_scene_wireframe_v4",
        "selected_animation": scene.summary.get("selected_animation"),
        "frame": scene.summary.get("frame", 0),
        "face_cap_applied": len(scene.triangles) > face_cap,
        "scene_summary": scene.summary,
    }

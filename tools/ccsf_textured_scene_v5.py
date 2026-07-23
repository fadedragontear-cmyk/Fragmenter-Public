#!/usr/bin/env python3
"""V5 CCSF preview scene assembled through StudioCCS-style clump instances."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v3 as pose_v3
import ccsf_textured_scene_v3 as scene_v3
import ccsf_textured_scene_v4 as scene_v4  # installs verified v2 texture decoder globals in v3
from ccsf_clump_instances_v1 import iter_clump_model_instances, preview_clump_rows as _preview_clump_rows, select_preview_clump

TexturedScene = scene_v3.TexturedScene
render_textured_scene = scene_v4.render_textured_scene
export_scene_textures = scene_v4.export_scene_textures
animation_rows = scene_v4.animation_rows
scene_wireframe_payload = scene_v4.scene_wireframe_payload

_SCENE_CACHE: dict[tuple[str, int, int, str, int, int], TexturedScene] = {}
_PREFERRED_CLUMP_BY_SOURCE: dict[str, int] = {}


def _resolved_source(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def set_preferred_clump(path: str | Path, clump_id: int | None) -> None:
    key = str(_resolved_source(path))
    if clump_id is None:
        _PREFERRED_CLUMP_BY_SOURCE.pop(key, None)
    else:
        _PREFERRED_CLUMP_BY_SOURCE[key] = int(clump_id)
    clear_scene_cache(path)


def preferred_clump_id(path: str | Path) -> int | None:
    return _PREFERRED_CLUMP_BY_SOURCE.get(str(_resolved_source(path)))


def preview_clump_rows(path: str | Path) -> list[dict[str, Any]]:
    parsed = pose_v3.load_pose_source(path)
    return _preview_clump_rows(parsed)


def _cache_key(source: Path, animation_name: str | None, frame: int, preferred_clump: int | None) -> tuple[str, int, int, str, int, int]:
    stat = source.stat()
    return (
        str(source.resolve()),
        stat.st_size,
        stat.st_mtime_ns,
        str(animation_name or ""),
        int(frame),
        int(preferred_clump) if preferred_clump is not None else -1,
    )


def clear_scene_cache(source: str | Path | None = None) -> None:
    if source is None:
        _SCENE_CACHE.clear()
        scene_v4.clear_scene_cache()
        return
    resolved = str(_resolved_source(source))
    for key in [key for key in _SCENE_CACHE if key[0] == resolved]:
        _SCENE_CACHE.pop(key, None)
    scene_v4.clear_scene_cache(source)


def _instance_summary(context: Any, instances: list[dict[str, Any]], selected_clump: dict[str, Any] | None) -> dict[str, Any]:
    clump_id = int(selected_clump.get("object_id") or 0) if selected_clump is not None else None
    clump_name = str(selected_clump.get("object_name") or "") if selected_clump is not None else ""
    return {
        "scene_assembly": "clump_node_object_child_model",
        "selected_clump_id": clump_id,
        "selected_clump_id_hex": f"0x{clump_id:X}" if clump_id is not None else None,
        "selected_clump_name": clump_name,
        "selected_clump_node_count": len(selected_clump.get("node_ids") or []) if selected_clump is not None else 0,
        "model_instances": len(instances),
        "instance_models": [
            {
                "clump_id": row.get("clump_id"),
                "clump_name": row.get("clump_name"),
                "node_index": row.get("node_index"),
                "object_id": row.get("object_id"),
                "object_name": row.get("object_name"),
                "model_id": row.get("model_id"),
                "model_name": row.get("model_name"),
            }
            for row in instances
        ],
        "clump_candidates": _preview_clump_rows(context),
    }


def load_textured_scene(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    clump_id: int | None = None,
) -> TexturedScene:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    preferred = int(clump_id) if clump_id is not None else preferred_clump_id(source)
    key = _cache_key(source, animation_name, frame, preferred)
    cached = _SCENE_CACHE.get(key)
    if cached is not None:
        return cached

    context = pose_v3.build_pose_context(source, animation_name=animation_name, frame=frame)
    materials, material_rows = scene_v3._parse_materials(context)
    textures, texture_rows = scene_v3._parse_textures(context)
    selected_clump = select_preview_clump(context, preferred)
    instances = list(iter_clump_model_instances(context, preferred))
    triangles: list[dict[str, Any]] = []
    unresolved: dict[str, int] = {}

    for instance in instances:
        model = instance["model"]
        model_id = int(instance["model_id"])
        model_name = str(instance["model_name"])
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = pose_v3.transformed_submodel_positions(
                context,
                model_id=model_id,
                submodel=submodel,
                owner_object_id=int(instance["object_id"]),
                clump=instance.get("clump"),
            )
            uvs: list[tuple[float, float]] = []
            for raw in submodel.get("uvs") or []:
                value = raw.get("uv") if isinstance(raw, dict) else raw
                if isinstance(value, (list, tuple)) and len(value) >= 2:
                    uvs.append((float(value[0]), float(value[1])))
            texture, material, resolution = scene_v3._resolve_texture(context, materials, textures, submodel.get("mat_tex_id"))
            offset = list((material or {}).get("texture_offset") or [0.0, 0.0])
            alpha = float((material or {}).get("alpha") if material is not None else 1.0)
            if texture is None:
                unresolved[resolution] = unresolved.get(resolution, 0) + len(submodel.get("faces") or [])
            elif len(uvs) != len(positions):
                reason = f"UV/vertex count mismatch ({len(uvs)}/{len(positions)})"
                unresolved[reason] = unresolved.get(reason, 0) + len(submodel.get("faces") or [])

            for face in submodel.get("faces") or []:
                if not isinstance(face, (list, tuple)) or len(face) < 3:
                    continue
                indices = (int(face[0]), int(face[1]), int(face[2]))
                if not all(0 <= index < len(positions) for index in indices):
                    unresolved["face index outside decoded positions"] = unresolved.get("face index outside decoded positions", 0) + 1
                    continue
                face_uvs = None
                if texture is not None and len(uvs) == len(positions):
                    face_uvs = tuple((uvs[index][0] + float(offset[0]), uvs[index][1] + float(offset[1])) for index in indices)
                triangles.append(
                    {
                        "positions": tuple(positions[index] for index in indices),
                        "uvs": face_uvs,
                        "texture": texture,
                        "material_alpha": alpha,
                        "model": model_name,
                        "submodel": submodel.get("index"),
                        "resolution": resolution,
                        "clump_id": instance.get("clump_id"),
                        "clump_name": instance.get("clump_name"),
                        "node_index": instance.get("node_index"),
                        "object_id": instance.get("object_id"),
                        "object_name": instance.get("object_name"),
                    }
                )

    summary = {
        **pose_v3.pose_summary(context),
        **_instance_summary(context, instances, selected_clump),
        "texture_records": len(texture_rows),
        "decoded_textures": len(textures),
        "material_records": len(material_rows),
        "parsed_materials": len(materials),
        "triangles": len(triangles),
        "textured_triangles": sum(1 for row in triangles if row.get("texture") is not None and row.get("uvs") is not None),
        "unresolved_triangles": sum(1 for row in triangles if row.get("texture") is None or row.get("uvs") is None),
        "unresolved_reasons": dict(sorted(unresolved.items())),
        "cache_key": list(key),
    }
    scene = TexturedScene(
        source=source,
        context=context,
        triangles=triangles,
        textures=textures,
        texture_rows=texture_rows,
        materials=materials,
        material_rows=material_rows,
        unresolved=unresolved,
        summary=summary,
    )
    _SCENE_CACHE[key] = scene
    return scene


def load_posed_wireframe_payload(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    face_cap: int = 30_000,
    clump_id: int | None = None,
) -> dict[str, Any]:
    source = Path(path).expanduser()
    preferred = int(clump_id) if clump_id is not None else preferred_clump_id(source)
    context = pose_v3.build_pose_context(source, animation_name=animation_name, frame=frame)
    selected_clump = select_preview_clump(context, preferred)
    instances = list(iter_clump_model_instances(context, preferred))
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    face_total = 0

    for instance in instances:
        model = instance["model"]
        model_id = int(instance["model_id"])
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = pose_v3.transformed_submodel_positions(
                context,
                model_id=model_id,
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

    summary = {
        **pose_v3.pose_summary(context),
        **_instance_summary(context, instances, selected_clump),
    }
    return {
        "source": str(context.source),
        "vertices": vertices,
        "faces": faces,
        "vertex_count": len(vertices),
        "face_count": len(faces),
        "parser": "clump_instance_pose_wireframe_v5",
        "selected_animation": summary.get("selected_animation"),
        "frame": summary.get("frame", 0),
        "selected_clump_id": summary.get("selected_clump_id"),
        "selected_clump_name": summary.get("selected_clump_name"),
        "model_instances": summary.get("model_instances", 0),
        "face_cap_applied": face_total > max(1, int(face_cap)),
        "scene_summary": summary,
    }

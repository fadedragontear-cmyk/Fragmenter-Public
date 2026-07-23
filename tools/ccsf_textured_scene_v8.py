#!/usr/bin/env python3
"""Whole-file CCSF scene assembly with exact external texture mapping.

The previous preview selected one clump and therefore omitted every model instance
owned by other clumps.  V8 supports a complete file assembly, a selected-clump
inspection mode, explicit initial pose, and exact-name TEX/MAT lookup across the
extracted CCS library.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import ccsf_structure_decoder as base
import ccsf_gen1_pose_v5 as pose_v5
import ccsf_textured_scene_v3 as scene_core
import ccsf_textured_scene_v4 as scene_v4  # installs texture decoder v2 into scene_core
import ccsf_textured_scene_v6 as scene_v6
import ccsf_textured_scene_v7 as scene_v7
from ccsf_clump_instances_v1 import model_records_by_id, preview_clump_rows, select_preview_clump
from ccsf_texture_registry_v1 import resolve_material_texture_by_name, resolve_texture_by_name

TexturedScene = scene_v6.TexturedScene
render_textured_scene = scene_v6.render_textured_scene
export_scene_textures = scene_v6.export_scene_textures
scene_wireframe_payload = scene_v6.scene_wireframe_payload
preview_pixel_step = scene_v6.preview_pixel_step
auto_texture_eligibility = scene_v6.auto_texture_eligibility
preferred_clump_id = scene_v6.preferred_clump_id

WHOLE_FILE = "whole_file"
SELECTED_CLUMP = "selected_clump"
_ASSEMBLY_MODE_BY_SOURCE: dict[str, str] = {}
_SCENE_CACHE: dict[tuple[str, int, int, str, int, str, int], TexturedScene] = {}


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def assembly_mode(path: str | Path) -> str:
    return _ASSEMBLY_MODE_BY_SOURCE.get(str(_resolved(path)), WHOLE_FILE)


def set_assembly_mode(path: str | Path, mode: str) -> None:
    normalized = SELECTED_CLUMP if str(mode).strip().lower() in {SELECTED_CLUMP, "selected", "selected clump"} else WHOLE_FILE
    _ASSEMBLY_MODE_BY_SOURCE[str(_resolved(path))] = normalized
    clear_scene_cache(path)


def set_preferred_clump(path: str | Path, clump_id: int | None) -> None:
    scene_v6.set_preferred_clump(path, clump_id)
    clear_scene_cache(path)


def clear_scene_cache(source: str | Path | None = None) -> None:
    if source is None:
        _SCENE_CACHE.clear()
        scene_v7.clear_scene_cache()
        return
    resolved = str(_resolved(source))
    for key in [key for key in _SCENE_CACHE if key[0] == resolved]:
        _SCENE_CACHE.pop(key, None)
    scene_v7.clear_scene_cache(source)


def _cache_key(source: Path, animation_name: str | None, frame: int, mode: str, preferred: int | None) -> tuple[str, int, int, str, int, str, int]:
    stat = source.stat()
    return (
        str(source.resolve()),
        stat.st_size,
        stat.st_mtime_ns,
        str(animation_name or pose_v5.INITIAL_POSE_NAME),
        int(frame),
        mode,
        int(preferred) if preferred is not None else -1,
    )


def _instance_row(context: Any, models: dict[int, dict[str, Any]], clump: dict[str, Any] | None, node_index: int | None, object_id: int) -> dict[str, Any] | None:
    object_row = context.objects.get(int(object_id))
    if not isinstance(object_row, dict):
        return None
    model_id = int(object_row.get("model_id") or 0)
    record = models.get(model_id)
    if model_id == 0 or record is None:
        return None
    clump_id = int(clump.get("object_id") or 0) if clump is not None else None
    clump_name = str(clump.get("object_name") or (context.report.object_lookup.get(clump_id) or {}).get("name") or clump_id or "") if clump is not None else ""
    return {
        "clump": clump,
        "clump_id": clump_id,
        "clump_name": clump_name,
        "node_index": node_index,
        "object_id": int(object_id),
        "object_name": str(object_row.get("object_name") or (context.report.object_lookup.get(int(object_id)) or {}).get("name") or object_id),
        "object": object_row,
        "model_id": model_id,
        "model_name": str(record.get("object_name") or (context.report.object_lookup.get(model_id) or {}).get("name") or model_id),
        "model_record": record,
        "model": record["model"],
    }


def _iter_instances(context: Any, mode: str, preferred: int | None) -> Iterator[dict[str, Any]]:
    models = model_records_by_id(context)
    emitted_objects: set[int] = set()
    clumps = list(context.clumps)
    if mode == SELECTED_CLUMP:
        selected = select_preview_clump(context, preferred)
        clumps = [selected] if selected is not None else []

    for clump in clumps:
        for node_index, raw_object_id in enumerate(clump.get("node_ids") or []):
            row = _instance_row(context, models, clump, node_index, int(raw_object_id))
            if row is None:
                continue
            emitted_objects.add(int(row["object_id"]))
            row["source"] = "whole_file_clump_instance" if mode == WHOLE_FILE else "selected_clump_instance"
            yield row

    if mode == WHOLE_FILE:
        # Preserve models that are reachable from Object records but absent from a
        # parsed Clump.  These are reported explicitly instead of silently dropped.
        for object_id in sorted(context.objects):
            if object_id in emitted_objects:
                continue
            row = _instance_row(context, models, None, None, object_id)
            if row is not None:
                row["source"] = "whole_file_unclumped_object"
                yield row


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _resolve_texture(
    source: Path,
    context: Any,
    materials: dict[int, dict[str, Any]],
    textures: dict[int, dict[str, Any]],
    mat_tex_id: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str, dict[str, Any] | None]:
    object_id = _optional_int(mat_tex_id)
    if object_id is None or object_id < 0:
        return None, None, "missing material/texture reference", None

    direct = textures.get(object_id)
    if direct is not None:
        return direct, None, "direct local TEX id", None

    entry = context.report.object_lookup.get(object_id) or {}
    entry_name = str(entry.get("name") or entry.get("object_name") or "")
    section_type = _optional_int(entry.get("section_type"))
    material = materials.get(object_id)
    if material is not None:
        texture_id = _optional_int(material.get("texture_id"))
        texture = textures.get(texture_id) if texture_id is not None else None
        if texture is not None:
            return texture, material, "local MAT -> local TEX id", None
        texture_entry = context.report.object_lookup.get(texture_id) if texture_id is not None else None
        texture_name = str((texture_entry or {}).get("name") or "")
        if texture_name:
            external, evidence = resolve_texture_by_name(source, texture_name)
            if external is not None:
                return external, material, "local MAT -> exact external TEX name", evidence
            return None, material, f"MAT target TEX {texture_name!r} was not decoded locally or externally", evidence
        return None, material, "MAT references an unnamed/undecoded TEX", None

    if section_type == base.SECTION_TEXTURE or entry_name.startswith("TEX_"):
        external, evidence = resolve_texture_by_name(source, entry_name)
        if external is not None:
            return external, None, "exact external TEX name", evidence
        return None, None, f"indexed TEX {entry_name!r} has no decoded setup record", evidence

    if section_type == base.SECTION_MATERIAL or entry_name.startswith("MAT_"):
        external, external_material, evidence = resolve_material_texture_by_name(source, entry_name)
        if external is not None:
            return external, external_material, "exact external MAT -> TEX name", evidence
        return None, external_material, f"indexed MAT {entry_name!r} has no resolved setup/texture", evidence

    return None, None, f"object {object_id} is not a resolved MAT/TEX", None


def _instance_summary(context: Any, instances: list[dict[str, Any]], mode: str, preferred: int | None) -> dict[str, Any]:
    clump_ids = sorted({int(row["clump_id"]) for row in instances if row.get("clump_id") is not None})
    return {
        "scene_assembly": mode,
        "preferred_clump_id": preferred,
        "clumps_available": len(context.clumps),
        "clumps_included": len(clump_ids),
        "included_clump_ids": clump_ids,
        "model_instances": len(instances),
        "unclumped_model_instances": sum(1 for row in instances if row.get("clump_id") is None),
        "clump_candidates": preview_clump_rows(context),
        "instance_models": [
            {
                "clump_id": row.get("clump_id"),
                "clump_name": row.get("clump_name"),
                "node_index": row.get("node_index"),
                "object_id": row.get("object_id"),
                "object_name": row.get("object_name"),
                "model_id": row.get("model_id"),
                "model_name": row.get("model_name"),
                "source": row.get("source"),
            }
            for row in instances
        ],
    }


def load_textured_scene(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    assembly: str | None = None,
    clump_id: int | None = None,
) -> TexturedScene:
    source = _resolved(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    mode = SELECTED_CLUMP if str(assembly or assembly_mode(source)).lower() == SELECTED_CLUMP else WHOLE_FILE
    preferred = int(clump_id) if clump_id is not None else preferred_clump_id(source)
    key = _cache_key(source, animation_name, frame, mode, preferred)
    cached = _SCENE_CACHE.get(key)
    if cached is not None:
        return cached

    context = pose_v5.build_pose_context(source, animation_name=animation_name, frame=frame)
    materials, material_rows = scene_core._parse_materials(context)
    textures, texture_rows = scene_core._parse_textures(context)
    instances = list(_iter_instances(context, mode, preferred))
    triangles: list[dict[str, Any]] = []
    unresolved: dict[str, int] = {}
    external_keys: dict[tuple[str, str], int] = {}
    external_evidence: list[dict[str, Any]] = []

    for instance in instances:
        model = instance["model"]
        model_id = int(instance["model_id"])
        model_name = str(instance["model_name"])
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = pose_v5.transformed_submodel_positions(
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
            texture, material, resolution, evidence = _resolve_texture(source, context, materials, textures, submodel.get("mat_tex_id"))
            if texture is not None and texture.get("external_source"):
                external_key = (str(texture.get("external_source")), str(texture.get("object_name") or texture.get("external_object_id")))
                texture_id = external_keys.get(external_key)
                if texture_id is None:
                    texture_id = -(len(external_keys) + 1)
                    external_keys[external_key] = texture_id
                    textures[texture_id] = texture
                    texture_rows.append(
                        {
                            "object_id": texture_id,
                            "object_name": texture.get("object_name"),
                            "status": "decoded_rgba_external_exact_name",
                            "width": texture.get("width"),
                            "height": texture.get("height"),
                            "texture_type_name": texture.get("texture_type_name"),
                            "clut_id": texture.get("clut_id"),
                            "clut_resolved": texture.get("clut_resolved"),
                            "external_source": texture.get("external_source"),
                        }
                    )
                if evidence is not None:
                    external_evidence.append(evidence)
            offset = list((material or {}).get("texture_offset") or [0.0, 0.0])
            alpha = float((material or {}).get("alpha") if material is not None else 1.0)
            face_count = len(submodel.get("faces") or [])
            if texture is None:
                unresolved[resolution] = unresolved.get(resolution, 0) + face_count
            elif len(uvs) != len(positions):
                reason = f"UV/vertex count mismatch ({len(uvs)}/{len(positions)})"
                unresolved[reason] = unresolved.get(reason, 0) + face_count

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
                        "mapping_evidence": evidence,
                        "clump_id": instance.get("clump_id"),
                        "clump_name": instance.get("clump_name"),
                        "node_index": instance.get("node_index"),
                        "object_id": instance.get("object_id"),
                        "object_name": instance.get("object_name"),
                    }
                )

    summary = {
        **pose_v5.pose_summary(context),
        **_instance_summary(context, instances, mode, preferred),
        "texture_records": len(texture_rows),
        "decoded_textures": len(textures),
        "local_decoded_textures": len(textures) - len(external_keys),
        "external_decoded_textures": len(external_keys),
        "external_mapping_attempts": len(external_evidence),
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
    scene = scene_v7._apply_override(scene, scene_v7.preview_override(source))
    _SCENE_CACHE[key] = scene
    return scene


def load_scene_bundle(path: str | Path, *, animation_name: str | None = None, frame: int = 0, face_cap: int = 60_000) -> dict[str, Any]:
    scene = load_textured_scene(path, animation_name=animation_name, frame=frame)
    wireframe = scene_wireframe_payload(scene, face_cap=max(1, int(face_cap)))
    wireframe["parser"] = "whole_file_scene_bundle_v8"
    return {"scene": scene, "wireframe": wireframe}


def load_posed_wireframe_payload(path: str | Path, *, animation_name: str | None = None, frame: int = 0, face_cap: int = 60_000) -> dict[str, Any]:
    return load_scene_bundle(path, animation_name=animation_name, frame=frame, face_cap=face_cap)["wireframe"]

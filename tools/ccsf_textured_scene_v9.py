#!/usr/bin/env python3
"""Staged whole-file textured scenes: local links first, external enrichment second."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ccsf_structure_decoder as base
import ccsf_gen1_pose_v5 as pose_v5
import ccsf_textured_scene_v3 as scene_core
import ccsf_textured_scene_v4 as scene_v4  # installs texture decoder v2 into scene_core
import ccsf_textured_scene_v6 as scene_v6
import ccsf_textured_scene_v7 as scene_v7
import ccsf_textured_scene_v8 as v8
from ccsf_texture_registry_v1 import resolve_material_texture_by_name, resolve_texture_by_name

TexturedScene = scene_v6.TexturedScene
render_textured_scene = scene_v6.render_textured_scene
export_scene_textures = scene_v6.export_scene_textures
scene_wireframe_payload = scene_v6.scene_wireframe_payload
preview_pixel_step = scene_v6.preview_pixel_step
auto_texture_eligibility = scene_v6.auto_texture_eligibility
preferred_clump_id = scene_v6.preferred_clump_id

WHOLE_FILE = v8.WHOLE_FILE
SELECTED_CLUMP = v8.SELECTED_CLUMP
assembly_mode = v8.assembly_mode
set_assembly_mode = v8.set_assembly_mode
set_preferred_clump = v8.set_preferred_clump
_iter_instances = v8._iter_instances
_instance_summary = v8._instance_summary
_optional_int = v8._optional_int

_SCENE_CACHE: dict[tuple[str, int, int, str, int, str, int, bool], TexturedScene] = {}


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def clear_scene_cache(source: str | Path | None = None) -> None:
    if source is None:
        _SCENE_CACHE.clear()
        v8.clear_scene_cache()
        return
    resolved = str(_resolved(source))
    for key in [key for key in _SCENE_CACHE if key[0] == resolved]:
        _SCENE_CACHE.pop(key, None)
    v8.clear_scene_cache(source)


def _cache_key(
    source: Path,
    animation_name: str | None,
    frame: int,
    mode: str,
    preferred: int | None,
    external_lookup: bool,
) -> tuple[str, int, int, str, int, str, int, bool]:
    stat = source.stat()
    return (
        str(source.resolve()),
        stat.st_size,
        stat.st_mtime_ns,
        str(animation_name or pose_v5.INITIAL_POSE_NAME),
        int(frame),
        mode,
        int(preferred) if preferred is not None else -1,
        bool(external_lookup),
    )


def _resolve_texture(
    source: Path,
    context: Any,
    materials: dict[int, dict[str, Any]],
    textures: dict[int, dict[str, Any]],
    mat_tex_id: Any,
    *,
    external_lookup: bool,
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
        if not external_lookup:
            return None, material, f"external TEX lookup deferred for {texture_name or texture_id}", None
        if texture_name:
            external, evidence = resolve_texture_by_name(source, texture_name)
            if external is not None:
                return external, material, "local MAT -> exact external TEX name", evidence
            return None, material, f"MAT target TEX {texture_name!r} was not decoded locally or externally", evidence
        return None, material, "MAT references an unnamed/undecoded TEX", None

    if section_type == base.SECTION_TEXTURE or entry_name.startswith("TEX_"):
        if not external_lookup:
            return None, None, f"external TEX lookup deferred for {entry_name or object_id}", None
        external, evidence = resolve_texture_by_name(source, entry_name)
        if external is not None:
            return external, None, "exact external TEX name", evidence
        return None, None, f"indexed TEX {entry_name!r} has no decoded setup record", evidence

    if section_type == base.SECTION_MATERIAL or entry_name.startswith("MAT_"):
        if not external_lookup:
            return None, None, f"external MAT lookup deferred for {entry_name or object_id}", None
        external, external_material, evidence = resolve_material_texture_by_name(source, entry_name)
        if external is not None:
            return external, external_material, "exact external MAT -> TEX name", evidence
        return None, external_material, f"indexed MAT {entry_name!r} has no resolved setup/texture", evidence

    return None, None, f"object {object_id} is not a resolved MAT/TEX", None


def load_textured_scene(
    path: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
    assembly: str | None = None,
    clump_id: int | None = None,
    external_lookup: bool = True,
) -> TexturedScene:
    source = _resolved(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    mode = SELECTED_CLUMP if str(assembly or assembly_mode(source)).lower() == SELECTED_CLUMP else WHOLE_FILE
    preferred = int(clump_id) if clump_id is not None else preferred_clump_id(source)
    key = _cache_key(source, animation_name, frame, mode, preferred, external_lookup)
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
            texture, material, resolution, evidence = _resolve_texture(
                source,
                context,
                materials,
                textures,
                submodel.get("mat_tex_id"),
                external_lookup=external_lookup,
            )
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
                            "clut_external_source": texture.get("clut_external_source"),
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
        "texture_mapping_phase": "local_plus_external" if external_lookup else "local_only",
        "external_lookup_enabled": bool(external_lookup),
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
    wireframe["parser"] = "staged_whole_file_scene_bundle_v9"
    return {"scene": scene, "wireframe": wireframe}


def load_posed_wireframe_payload(path: str | Path, *, animation_name: str | None = None, frame: int = 0, face_cap: int = 60_000) -> dict[str, Any]:
    return load_scene_bundle(path, animation_name=animation_name, frame=frame, face_cap=face_cap)["wireframe"]

#!/usr/bin/env python3
"""Read-only CCSF character/asset diagnostics and provenance-preserving OBJ export."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v4 as pose_v4
import ccsf_structure_decoder as base
import ccsf_textured_scene_v6 as scene_v6
from ccsf_clump_instances_v1 import iter_clump_model_instances, select_preview_clump


def _safe(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return cleaned or "unnamed"


def _name(context: Any, object_id: int | None) -> str:
    if object_id is None:
        return ""
    row = context.report.object_lookup.get(int(object_id))
    return str(row.get("name") or "") if isinstance(row, dict) else ""


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _bounds(positions: list[tuple[float, float, float]]) -> dict[str, Any] | None:
    if not positions:
        return None
    minimum = [min(point[axis] for point in positions) for axis in range(3)]
    maximum = [max(point[axis] for point in positions) for axis in range(3)]
    return {
        "min": minimum,
        "max": maximum,
        "size": [maximum[index] - minimum[index] for index in range(3)],
        "center": [(minimum[index] + maximum[index]) * 0.5 for index in range(3)],
    }


def _degenerate_faces(positions: list[tuple[float, float, float]], faces: list[Any]) -> int:
    count = 0
    for face in faces:
        if not isinstance(face, (list, tuple)) or len(face) < 3:
            continue
        indices = [int(face[0]), int(face[1]), int(face[2])]
        if not all(0 <= index < len(positions) for index in indices):
            count += 1
            continue
        a, b, c = (positions[index] for index in indices)
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        if sum(value * value for value in cross) <= 1e-18:
            count += 1
    return count


def _texture_link(scene: Any, mat_tex_id: Any) -> dict[str, Any]:
    context = scene.context
    object_id = _optional_int(mat_tex_id)
    entry = context.report.object_lookup.get(object_id) if object_id is not None else None
    section_type = _optional_int((entry or {}).get("section_type")) if isinstance(entry, dict) else None
    material = scene.materials.get(object_id) if object_id is not None else None
    texture_id: int | None = None
    resolution = "missing material/texture reference"
    if section_type == base.SECTION_TEXTURE:
        texture_id = object_id
        resolution = "direct TEX reference"
    elif material is not None:
        texture_id = _optional_int(material.get("texture_id"))
        resolution = "MAT -> TEX reference"
    elif object_id is not None:
        resolution = "reference is not a decoded MAT/TEX"
    texture = scene.textures.get(texture_id) if texture_id is not None else None
    clut_id = _optional_int((texture or {}).get("clut_id")) if isinstance(texture, dict) else None
    return {
        "mat_tex_id": object_id,
        "mat_tex_name": _name(context, object_id),
        "reference_section_type": section_type,
        "reference_section_name": base.type_name(section_type) if section_type is not None else None,
        "material_id": object_id if material is not None else None,
        "material_name": _name(context, object_id) if material is not None else "",
        "texture_id": texture_id,
        "texture_name": _name(context, texture_id),
        "texture_decoded": texture is not None,
        "texture_format": (texture or {}).get("texture_type_name") or (texture or {}).get("format_name") if isinstance(texture, dict) else None,
        "texture_width": (texture or {}).get("width") if isinstance(texture, dict) else None,
        "texture_height": (texture or {}).get("height") if isinstance(texture, dict) else None,
        "clut_id": clut_id,
        "clut_name": _name(context, clut_id),
        "clut_resolved": bool((texture or {}).get("clut_resolved")) if isinstance(texture, dict) else False,
        "resolution": resolution,
    }


def _part_identity(context: Any, clump: dict[str, Any] | None, submodel: dict[str, Any]) -> dict[str, Any]:
    parser_mode = str(submodel.get("parser_mode") or "")
    parent_id = _optional_int(submodel.get("parent_id"))
    node_index = parent_id
    if node_index is None and parser_mode == "studioccs_gen1_deform_weighted":
        # StudioCCS leaves the final deformable SubModel.ParentID at zero; its tree
        # therefore names that bendy submodel from clump node zero.
        node_index = 0
    nodes = list((clump or {}).get("node_ids") or [])
    object_id = int(nodes[node_index]) if node_index is not None and 0 <= node_index < len(nodes) else None
    return {
        "part_node_index": node_index,
        "part_object_id": object_id,
        "part_object_name": _name(context, object_id),
    }


def build_asset_diagnostics(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> dict[str, Any]:
    scene = scene_v6.load_textured_scene(path, animation_name=animation_name, frame=frame)
    context = scene.context
    preferred = scene.summary.get("selected_clump_id")
    clump = select_preview_clump(context, int(preferred) if preferred is not None else None)
    selected_nodes = [int(value) for value in (clump or {}).get("node_ids") or []]
    selected_node_index = {object_id: index for index, object_id in enumerate(selected_nodes)}
    submodels: list[dict[str, Any]] = []
    instances: list[dict[str, Any]] = []

    for instance in iter_clump_model_instances(context, int(preferred) if preferred is not None else None):
        model = instance["model"]
        instance_submodels = []
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = pose_v4.transformed_submodel_positions(
                context,
                model_id=int(instance["model_id"]),
                submodel=submodel,
                owner_object_id=int(instance["object_id"]),
                clump=instance.get("clump"),
            )
            faces = list(submodel.get("faces") or [])
            uvs = list(submodel.get("uvs") or [])
            texture = _texture_link(scene, submodel.get("mat_tex_id"))
            part = _part_identity(context, instance.get("clump"), submodel)
            warnings = list(submodel.get("warnings") or [])
            if len(uvs) != len(positions):
                warnings.append(f"UV/position count mismatch {len(uvs)}/{len(positions)}")
            if not texture["texture_decoded"]:
                warnings.append(f"texture unresolved: {texture['resolution']}")
            row = {
                "clump_id": instance.get("clump_id"),
                "clump_name": instance.get("clump_name"),
                "clump_node_index": instance.get("node_index"),
                "owner_object_id": instance.get("object_id"),
                "owner_object_name": instance.get("object_name"),
                "model_id": instance.get("model_id"),
                "model_name": instance.get("model_name"),
                "actual_model_type": model.get("actual_model_type"),
                "masked_model_type": model.get("model_type"),
                "model_type_name": model.get("model_type_name"),
                "submodel_index": submodel.get("index"),
                "parser_mode": submodel.get("parser_mode"),
                **part,
                "vertices": len(positions),
                "faces": len(faces),
                "uvs": len(uvs),
                "degenerate_or_invalid_faces": _degenerate_faces(positions, faces),
                "posed_bounds": _bounds(positions),
                **texture,
                "warnings": warnings,
            }
            submodels.append(row)
            instance_submodels.append(row["submodel_index"])
        instances.append(
            {
                "clump_node_index": instance.get("node_index"),
                "object_id": instance.get("object_id"),
                "object_name": instance.get("object_name"),
                "model_id": instance.get("model_id"),
                "model_name": instance.get("model_name"),
                "submodels": instance_submodels,
            }
        )

    animations: list[dict[str, Any]] = []
    for animation in context.animations:
        controllers = []
        selected_targets = 0
        for controller in animation.get("controllers") or []:
            target_id = _optional_int(controller.get("target_object_id"))
            in_selected = target_id in selected_node_index if target_id is not None else False
            selected_targets += int(in_selected)
            tracks = controller.get("tracks") or {}
            controllers.append(
                {
                    "external_id": controller.get("external_id"),
                    "external_name": controller.get("external_name"),
                    "target_object_id": target_id,
                    "target_object_name": controller.get("target_object_name") or _name(context, target_id),
                    "target_in_selected_clump": in_selected,
                    "selected_clump_node_index": selected_node_index.get(target_id),
                    "tracks": {
                        key: {
                            "status": value.get("status"),
                            "key_count": int(value.get("key_count") or len(value.get("keys") or [])),
                        }
                        for key, value in tracks.items()
                        if isinstance(value, dict)
                    },
                }
            )
        animations.append(
            {
                "animation_id": animation.get("object_id"),
                "animation_name": animation.get("object_name"),
                "frame_count": int(animation.get("frame_count") or 0),
                "playback_name": animation.get("playback_name"),
                "controller_count": len(controllers),
                "selected_clump_target_count": selected_targets,
                "selected_clump_coverage": selected_targets / len(selected_nodes) if selected_nodes else 0.0,
                "pose_ready": bool(animation.get("pose_ready")),
                "controllers": controllers,
                "warnings": list(animation.get("warnings") or []),
            }
        )

    reference_candidates = [
        {
            "animation_id": row["animation_id"],
            "animation_name": row["animation_name"],
            "frame_count": row["frame_count"],
            "playback_name": row["playback_name"],
            "selected_clump_target_count": row["selected_clump_target_count"],
        }
        for row in animations
        if "nut" in str(row.get("animation_name") or "").lower() and row.get("pose_ready")
    ]
    head_rows = [row for row in submodels if "head" in str(row.get("part_object_name") or "").lower()]
    payload = {
        "version": 1,
        "source": str(scene.source),
        "generation": context.report.header.get("generation"),
        "selected_animation": scene.summary.get("selected_animation"),
        "frame": scene.summary.get("frame"),
        "selected_clump": {
            "clump_id": (clump or {}).get("object_id"),
            "clump_name": (clump or {}).get("object_name"),
            "node_count": len(selected_nodes),
            "node_ids": selected_nodes,
        },
        "scene_summary": dict(scene.summary),
        "instances": instances,
        "submodels": submodels,
        "animations": animations,
        "reference_pose_candidates": reference_candidates,
        "summary": {
            "instances": len(instances),
            "submodels": len(submodels),
            "vertices": sum(int(row["vertices"]) for row in submodels),
            "faces": sum(int(row["faces"]) for row in submodels),
            "decoded_texture_links": sum(1 for row in submodels if row["texture_decoded"]),
            "unresolved_texture_links": sum(1 for row in submodels if not row["texture_decoded"]),
            "uv_mismatches": sum(1 for row in submodels if int(row["vertices"]) != int(row["uvs"])),
            "head_submodels": len(head_rows),
            "head_texture_links_decoded": sum(1 for row in head_rows if row["texture_decoded"]),
            "animations": len(animations),
            "reference_pose_candidates": len(reference_candidates),
        },
    }
    return payload


def _render_text_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    clump = payload["selected_clump"]
    lines = [
        f"CCSF Asset Diagnostic: {payload['source']}",
        f"Clump: {clump.get('clump_id')} {clump.get('clump_name')} | {clump.get('node_count')} nodes",
        f"Pose: {payload.get('selected_animation') or 'identity'} frame {payload.get('frame', 0)}",
        f"Instances: {summary['instances']} | submodels {summary['submodels']} | vertices {summary['vertices']} | faces {summary['faces']}",
        f"Texture links: {summary['decoded_texture_links']} decoded | {summary['unresolved_texture_links']} unresolved | UV mismatches {summary['uv_mismatches']}",
        f"Head submodels: {summary['head_submodels']} | decoded texture links {summary['head_texture_links_decoded']}",
        "",
        "Submodels:",
    ]
    for row in payload["submodels"]:
        warning = "; ".join(row["warnings"]) or "OK"
        lines.append(
            f"- node {row['clump_node_index']} {row['owner_object_name']} -> {row['model_name']}[{row['submodel_index']}] "
            f"part={row['part_object_name'] or row['part_node_index']} parser={row['parser_mode']} "
            f"v/f/uv={row['vertices']}/{row['faces']}/{row['uvs']} "
            f"MAT={row['material_id']} {row['material_name']} -> TEX={row['texture_id']} {row['texture_name']} "
            f"CLUT={row['clut_id']} {row['clut_name']} decoded={row['texture_decoded']} | {warning}"
        )
    lines.extend(["", "Reference-pose candidates:"])
    for row in payload["reference_pose_candidates"]:
        lines.append(
            f"- {row['animation_id']} {row['animation_name']} | {row['frame_count']} frames | {row['playback_name']} | "
            f"selected-clump targets {row['selected_clump_target_count']}"
        )
    lines.extend(["", "Animation coverage:"])
    for row in payload["animations"]:
        lines.append(
            f"- {row['animation_id']} {row['animation_name']} | controllers {row['controller_count']} | "
            f"selected-clump targets {row['selected_clump_target_count']} | coverage {row['selected_clump_coverage']:.1%}"
        )
    return "\n".join(lines) + "\n"


def write_asset_diagnostics(
    path: str | Path,
    output_dir: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
) -> dict[str, Any]:
    payload = build_asset_diagnostics(path, animation_name=animation_name, frame=frame)
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "asset_diagnostic.json"
    text_path = root / "asset_diagnostic.txt"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(_render_text_report(payload), encoding="utf-8")
    payload["report_path"] = str(json_path)
    payload["text_report_path"] = str(text_path)
    return payload


def export_research_obj(
    path: str | Path,
    output_dir: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
) -> dict[str, Any]:
    """Export derived OBJ/MTL/PNG research files without mutating the CCSF source."""
    scene = scene_v6.load_textured_scene(path, animation_name=animation_name, frame=frame)
    context = scene.context
    preferred = scene.summary.get("selected_clump_id")
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    texture_export = scene_v6.export_scene_textures(scene, root / "textures")
    texture_paths = {int(row["texture_id"]): Path(row["path"]).name for row in texture_export["textures"]}
    obj_path = root / "asset_research.obj"
    mtl_path = root / "asset_research.mtl"
    obj_lines = [
        f"# Fragmenter derived research export; source remains untouched: {scene.source}",
        f"# selected_clump={scene.summary.get('selected_clump_id')} {scene.summary.get('selected_clump_name')}",
        f"# selected_animation={scene.summary.get('selected_animation')} frame={scene.summary.get('frame', 0)}",
        f"mtllib {mtl_path.name}",
        "",
    ]
    mtl_lines = ["# Fragmenter derived research materials", ""]
    written_materials: set[str] = set()
    vertex_offset = 1
    uv_offset = 1
    groups = 0
    faces_written = 0

    for instance in iter_clump_model_instances(context, int(preferred) if preferred is not None else None):
        model = instance["model"]
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            positions = pose_v4.transformed_submodel_positions(
                context,
                model_id=int(instance["model_id"]),
                submodel=submodel,
                owner_object_id=int(instance["object_id"]),
                clump=instance.get("clump"),
            )
            if not positions:
                continue
            raw_uvs = list(submodel.get("uvs") or [])
            uvs: list[tuple[float, float]] = []
            for raw in raw_uvs:
                value = raw.get("uv") if isinstance(raw, dict) else raw
                if isinstance(value, (list, tuple)) and len(value) >= 2:
                    uvs.append((float(value[0]), float(value[1])))
            texture_link = _texture_link(scene, submodel.get("mat_tex_id"))
            part = _part_identity(context, instance.get("clump"), submodel)
            group_name = "__".join(
                [
                    f"CMP_{int(instance.get('clump_id') or 0):04X}_{_safe(instance.get('clump_name'))}",
                    f"OBJ_{int(instance['object_id']):04X}_{_safe(instance.get('object_name'))}",
                    f"MDL_{int(instance['model_id']):04X}_{_safe(instance.get('model_name'))}",
                    f"sub_{int(submodel.get('index') or 0):02d}",
                    f"part_{int(part.get('part_object_id') or 0):04X}_{_safe(part.get('part_object_name') or part.get('part_node_index'))}",
                ]
            )
            material_name = f"MAT_{int(texture_link.get('material_id') or texture_link.get('mat_tex_id') or 0):04X}__TEX_{int(texture_link.get('texture_id') or 0):04X}"
            obj_lines.extend(
                [
                    f"# clump_node={instance.get('node_index')} owner_object={instance['object_id']} model={instance['model_id']} submodel={submodel.get('index')} part_node={part.get('part_node_index')} part_object={part.get('part_object_id')}",
                    f"g {group_name}",
                ]
            )
            if texture_link.get("texture_decoded"):
                obj_lines.append(f"usemtl {material_name}")
                if material_name not in written_materials:
                    written_materials.add(material_name)
                    mtl_lines.extend([f"newmtl {material_name}", "Ka 1.0 1.0 1.0", "Kd 1.0 1.0 1.0", "Ks 0.0 0.0 0.0"])
                    texture_id = int(texture_link["texture_id"])
                    if texture_id in texture_paths:
                        mtl_lines.append(f"map_Kd textures/{texture_paths[texture_id]}")
                    mtl_lines.append("")
            for x, y, z in positions:
                obj_lines.append(f"v {x:.9g} {y:.9g} {z:.9g}")
            has_uvs = len(uvs) == len(positions)
            if has_uvs:
                for u, v in uvs:
                    obj_lines.append(f"vt {u:.9g} {v:.9g}")
            for face in submodel.get("faces") or []:
                if not isinstance(face, (list, tuple)) or len(face) < 3:
                    continue
                indices = [int(face[0]), int(face[1]), int(face[2])]
                if not all(0 <= index < len(positions) for index in indices):
                    continue
                if has_uvs:
                    refs = [f"{vertex_offset + index}/{uv_offset + index}" for index in indices]
                else:
                    refs = [str(vertex_offset + index) for index in indices]
                obj_lines.append("f " + " ".join(refs))
                faces_written += 1
            obj_lines.append("")
            vertex_offset += len(positions)
            if has_uvs:
                uv_offset += len(uvs)
            groups += 1

    obj_path.write_text("\n".join(obj_lines) + "\n", encoding="utf-8")
    mtl_path.write_text("\n".join(mtl_lines) + "\n", encoding="utf-8")
    return {
        "source": str(scene.source),
        "obj_path": str(obj_path),
        "mtl_path": str(mtl_path),
        "texture_export": texture_export,
        "groups": groups,
        "vertices": vertex_offset - 1,
        "faces": faces_written,
        "selected_clump_id": scene.summary.get("selected_clump_id"),
        "selected_clump_name": scene.summary.get("selected_clump_name"),
        "selected_animation": scene.summary.get("selected_animation"),
        "frame": scene.summary.get("frame", 0),
        "derived_export_only": True,
    }


def build_research_bundle(
    path: str | Path,
    output_dir: str | Path,
    *,
    animation_name: str | None = None,
    frame: int = 0,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    diagnostics = write_asset_diagnostics(path, root, animation_name=animation_name, frame=frame)
    obj = export_research_obj(path, root, animation_name=animation_name, frame=frame)
    return {"diagnostics": diagnostics, "obj": obj, "output_dir": str(root)}

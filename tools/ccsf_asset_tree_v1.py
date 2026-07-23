#!/usr/bin/env python3
"""Build a StudioCCS-style read-only contents tree for one CCSF file."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v2 as pose_v2
import ccsf_structure_decoder as base
import ccsf_texture_decoder_v2 as texture_v2

SECTION_BBOX = 0x0C00


def _name(lookup: dict[int, dict[str, Any]], object_id: int | None) -> str:
    row = lookup.get(int(object_id or 0))
    return str(row.get("name") or "") if isinstance(row, dict) else ""


def _node(label: str, kind: str, details: dict[str, Any] | None = None, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"label": label, "kind": kind, "details": details or {}, "children": children or []}


def _model_nodes(parsed, lookup: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for record in parsed.report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_MODEL:
            continue
        model = record.get("model") if isinstance(record.get("model"), dict) else {}
        model_id = int(record.get("object_id") or 0)
        submodels = []
        for sub in model.get("submodels") or []:
            mat_id = sub.get("mat_tex_id")
            material_name = _name(lookup, int(mat_id)) if isinstance(mat_id, int) else ""
            submodels.append(
                _node(
                    f"Sub Model {sub.get('index')}: {sub.get('decoded_vertex_count', 0)} vertices / {sub.get('triangle_count', 0)} triangles",
                    "submodel",
                    {
                        "index": sub.get("index"),
                        "parser_mode": sub.get("parser_mode"),
                        "parent_id": sub.get("parent_id"),
                        "parent_id_kind": sub.get("parent_id_kind") or sub.get("bone_id_kind"),
                        "material_or_texture_id": mat_id,
                        "material_or_texture_name": material_name,
                        "vertices": sub.get("decoded_vertex_count"),
                        "triangles": sub.get("triangle_count"),
                        "warnings": list(sub.get("warnings") or []),
                    },
                )
            )
        rows[model_id] = _node(
            f"Model 0x{model_id:X}: {_name(lookup, model_id)}",
            "model",
            {
                "model_id": model_id,
                "model_type": model.get("model_type"),
                "model_type_name": model.get("model_type_name"),
                "submodel_count": len(model.get("submodels") or []),
                "parse_status": model.get("parse_status"),
                "vertex_scale": model.get("vertex_scale"),
                "warnings": list(model.get("warnings") or []),
            },
            submodels,
        )
    return rows


def _object_node(object_id: int, parsed, models: dict[int, dict[str, Any]], children_by_parent: dict[int, list[int]], seen: set[int]) -> dict[str, Any]:
    if object_id in seen:
        return _node(f"Object 0x{object_id:X}: {_name(parsed.report.object_lookup, object_id)} [cycle]", "object_cycle")
    seen = set(seen)
    seen.add(object_id)
    row = parsed.objects.get(object_id) or {}
    model_id = int(row.get("model_id") or 0)
    shadow_id = int(row.get("shadow_id") or 0)
    children: list[dict[str, Any]] = []
    if model_id:
        children.append(models.get(model_id) or _node(f"Model 0x{model_id:X}: {_name(parsed.report.object_lookup, model_id)} [not decoded]", "model_missing"))
    if shadow_id:
        shadow = models.get(shadow_id)
        children.append(shadow or _node(f"Shadow 0x{shadow_id:X}: {_name(parsed.report.object_lookup, shadow_id)} [not decoded]", "shadow_missing"))
    for child_id in children_by_parent.get(object_id, []):
        children.append(_object_node(child_id, parsed, models, children_by_parent, seen))
    parent_id = int(row.get("parent_object_id") or 0)
    return _node(
        f"Object 0x{object_id:X}: {_name(parsed.report.object_lookup, object_id)}",
        "object",
        {
            "object_id": object_id,
            "parent_object_id": parent_id,
            "parent_object_name": _name(parsed.report.object_lookup, parent_id),
            "model_id": model_id,
            "model_name": _name(parsed.report.object_lookup, model_id),
            "shadow_id": shadow_id,
            "shadow_name": _name(parsed.report.object_lookup, shadow_id),
            "clump_node_index": (parsed.clump_by_object.get(object_id) or {}).get("node_index"),
        },
        children,
    )


def _clump_group(parsed, models: dict[int, dict[str, Any]]) -> dict[str, Any]:
    children: list[dict[str, Any]] = []
    for clump in parsed.clumps:
        node_ids = [int(value) for value in clump.get("node_ids") or []]
        node_set = set(node_ids)
        children_by_parent: dict[int, list[int]] = {}
        roots: list[int] = []
        for object_id in node_ids:
            row = parsed.objects.get(object_id) or {}
            parent_id = int(row.get("parent_object_id") or 0)
            if parent_id and parent_id in node_set:
                children_by_parent.setdefault(parent_id, []).append(object_id)
            else:
                roots.append(object_id)
        object_nodes = [_object_node(object_id, parsed, models, children_by_parent, set()) for object_id in roots]
        clump_id = int(clump.get("object_id") or 0)
        children.append(
            _node(
                f"Clump 0x{clump_id:X}: {clump.get('object_name') or _name(parsed.report.object_lookup, clump_id)}",
                "clump",
                {"clump_id": clump_id, "node_count": len(node_ids), "node_ids": node_ids},
                object_nodes,
            )
        )
    return _node(f"Clumps ({len(children)})", "group", children=children)


def _material_group(parsed) -> dict[str, Any]:
    children = []
    for record in parsed.report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_MATERIAL:
            continue
        object_id = int(record.get("object_id") or 0)
        start = int(record.get("payload_start") or 0)
        end = int(record.get("payload_end") or 0)
        details: dict[str, Any] = {"object_id": object_id, "payload_size": max(0, end - start)}
        if start + 12 <= end and end <= len(parsed.data):
            texture_id = struct.unpack_from("<i", parsed.data, start)[0]
            alpha = struct.unpack_from("<f", parsed.data, start + 4)[0]
            raw_u, raw_v = struct.unpack_from("<hh", parsed.data, start + 8)
            details.update(
                {
                    "texture_id": texture_id,
                    "texture_name": _name(parsed.report.object_lookup, texture_id),
                    "alpha": alpha,
                    "uv_offset": [raw_u / 256.0, raw_v / 256.0],
                }
            )
        children.append(_node(f"Material 0x{object_id:X}: {_name(parsed.report.object_lookup, object_id)}", "material", details))
    return _node(f"Materials ({len(children)})", "group", children=children)


def _texture_group(parsed) -> dict[str, Any]:
    cluts: dict[int, dict[str, Any]] = {}
    for record in parsed.report.records:
        if int(record.get("masked_section_type") or 0) == base.SECTION_CLUT:
            try:
                row = texture_v2.parse_clut_record(parsed.data, record)
                cluts[int(row["object_id"])] = row
            except Exception:
                pass
    children = []
    generation = str(parsed.report.header.get("generation") or "Unknown")
    for record in parsed.report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_TEXTURE:
            continue
        object_id = int(record.get("object_id") or 0)
        try:
            texture = texture_v2.parse_texture_record(parsed.data, record, generation)
            clut_id = texture.get("clut_id")
            details = {
                key: value
                for key, value in texture.items()
                if key not in {"pixel_data"}
            }
            details["clut_name"] = _name(parsed.report.object_lookup, int(clut_id)) if isinstance(clut_id, int) else ""
        except Exception as exc:
            details = {"object_id": object_id, "status": "error", "error": str(exc)}
        children.append(_node(f"Texture 0x{object_id:X}: {_name(parsed.report.object_lookup, object_id)}", "texture", details))
    return _node(f"Textures ({len(children)})", "group", children=children)


def _record_group(parsed, section_types: set[int], label: str, kind: str) -> dict[str, Any]:
    children = []
    for record in parsed.report.records:
        if int(record.get("masked_section_type") or 0) not in section_types:
            continue
        object_id = int(record.get("object_id") or 0)
        children.append(
            _node(
                f"0x{object_id:X}: {_name(parsed.report.object_lookup, object_id)}",
                kind,
                {
                    "object_id": object_id,
                    "type_name": record.get("type_name"),
                    "payload_start": record.get("payload_start"),
                    "payload_end": record.get("payload_end"),
                    "payload_size": max(0, int(record.get("payload_end") or 0) - int(record.get("payload_start") or 0)),
                    "parse_status": record.get("parse_status"),
                },
            )
        )
    return _node(f"{label} ({len(children)})", "group", children=children)


def _animation_group(parsed) -> dict[str, Any]:
    children = []
    for animation in parsed.animations:
        object_id = int(animation.get("object_id") or 0)
        controllers = []
        for controller in animation.get("controllers") or []:
            target_id = controller.get("target_object_id")
            tracks = controller.get("tracks") or {}
            controllers.append(
                _node(
                    f"Object Controller -> 0x{int(target_id or 0):X}: {controller.get('target_object_name') or _name(parsed.report.object_lookup, target_id)}",
                    "object_controller",
                    {
                        "external_id": controller.get("external_id"),
                        "external_name": controller.get("external_name"),
                        "target_object_id": target_id,
                        "target_object_name": controller.get("target_object_name"),
                        "tracks": {
                            name: {
                                "status": track.get("status"),
                                "key_count": track.get("key_count", len(track.get("keys") or [])),
                                "fixed": track.get("fixed"),
                            }
                            for name, track in tracks.items()
                            if isinstance(track, dict)
                        },
                    },
                )
            )
        children.append(
            _node(
                f"Animation 0x{object_id:X}: {animation.get('object_name')} — {animation.get('frame_count', 0)} frames / {animation.get('playback_name')}",
                "animation",
                {
                    "object_id": object_id,
                    "object_name": animation.get("object_name"),
                    "frame_count": animation.get("frame_count"),
                    "playback_name": animation.get("playback_name"),
                    "controller_count": animation.get("controller_count"),
                    "pose_ready": animation.get("pose_ready"),
                    "warnings": list(animation.get("warnings") or []),
                },
                controllers,
            )
        )
    return _node(f"Animations ({len(children)})", "group", children=children)


def inspect_ccsf_contents(path: str | Path) -> dict[str, Any]:
    parsed = pose_v2.load_pose_source(path)
    models = _model_nodes(parsed, parsed.report.object_lookup)
    groups = [
        _clump_group(parsed, models),
        _material_group(parsed),
        _texture_group(parsed),
        _record_group(parsed, {base.SECTION_HITMESH}, "Hit Meshes", "hit_mesh"),
        _record_group(parsed, {SECTION_BBOX}, "Bounding Boxes", "bounding_box"),
        _record_group(parsed, {base.SECTION_DUMMYPOS, base.SECTION_DUMMYPOSROT}, "Dummies", "dummy"),
        _animation_group(parsed),
    ]
    animations = [
        {
            "object_id": row.get("object_id"),
            "object_name": row.get("object_name"),
            "frame_count": int(row.get("frame_count") or 0),
            "playback_name": row.get("playback_name"),
            "controller_count": int(row.get("controller_count") or 0),
            "pose_ready": bool(row.get("pose_ready")),
        }
        for row in parsed.animations
    ]
    return {
        "source": str(parsed.source),
        "header": dict(parsed.report.header),
        "file_count": len(parsed.report.file_index),
        "object_count": len(parsed.report.object_index),
        "groups": groups,
        "animations": animations,
        "summary": {
            "clumps": len(parsed.clumps),
            "materials": len(groups[1]["children"]),
            "textures": len(groups[2]["children"]),
            "hit_meshes": len(groups[3]["children"]),
            "bounding_boxes": len(groups[4]["children"]),
            "dummies": len(groups[5]["children"]),
            "animations": len(animations),
        },
    }

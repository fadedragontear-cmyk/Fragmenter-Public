#!/usr/bin/env python3
"""Render Fragmenter's CCSF parse in a StudioCCS-like comparison layout.

This is not a byte-for-byte StudioCCS report clone. It deliberately prints the
same structural concepts and both decimal/hex IDs so human comparison can expose
missing clumps, models, submodels, materials, textures, and animation targets.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ccsf_asset_diagnostics_v1 as diagnostics
import ccsf_structure_decoder as base
import ccsf_textured_scene_v6 as scene_v6


def _id(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "<None>"
    return f"{number} (0x{number:X})"


def build_compare_report(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> dict[str, Any]:
    source = Path(path).expanduser()
    scene = scene_v6.load_textured_scene(source, animation_name=animation_name, frame=frame)
    diag = diagnostics.build_asset_diagnostics(source, animation_name=animation_name, frame=frame)
    report = scene.context.report

    def object_name(value: Any) -> str:
        try:
            row = report.object_lookup.get(int(value))
        except (TypeError, ValueError):
            row = None
        return str((row or {}).get("name") or "") if isinstance(row, dict) else ""

    section_counts: dict[str, int] = {}
    for record in report.records:
        name = base.type_name(int(record.get("masked_section_type") or 0))
        section_counts[name] = section_counts.get(name, 0) + 1

    materials = []
    for material_id, row in sorted(scene.materials.items()):
        materials.append(
            {
                "material_id": int(material_id),
                "material_name": object_name(material_id),
                "texture_id": row.get("texture_id"),
                "texture_name": object_name(row.get("texture_id")),
                "alpha": row.get("alpha"),
                "texture_offset": row.get("texture_offset"),
                "texture_offset_raw": row.get("texture_offset_raw"),
                "status": row.get("status"),
            }
        )

    textures = []
    for row in scene.texture_rows:
        textures.append(
            {
                "texture_id": row.get("object_id"),
                "texture_name": row.get("object_name"),
                "status": row.get("status"),
                "decode_status": row.get("decode_status"),
                "format": row.get("texture_type_name") or row.get("format_name"),
                "width": row.get("width"),
                "height": row.get("height"),
                "mipmap_count": row.get("mipmap_count"),
                "clut_id": row.get("clut_id"),
                "clut_name": object_name(row.get("clut_id")),
                "clut_resolved": row.get("clut_resolved"),
                "warnings": row.get("warnings") or [],
                "error": row.get("error"),
            }
        )

    payload = {
        "version": 1,
        "source": str(source),
        "generation": report.header.get("generation"),
        "header": report.header,
        "file_count": len(report.file_index),
        "object_count": len(report.object_lookup),
        "section_counts": section_counts,
        "selected_clump": diag["selected_clump"],
        "instances": diag["instances"],
        "submodels": diag["submodels"],
        "materials": materials,
        "textures": textures,
        "animations": diag["animations"],
        "summary": diag["summary"],
        "errors": list(report.errors),
        "warnings": list(report.warnings),
    }
    return payload


def render_compare_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Fragmenter CCSF Compare: {payload['source']}",
        f"Generation: {payload.get('generation')} | Files: {payload.get('file_count')} | Objects: {payload.get('object_count')}",
        "Section counts: " + ", ".join(f"{key}={value}" for key, value in sorted(payload["section_counts"].items())),
        "",
        "Selected Clump:",
    ]
    clump = payload["selected_clump"]
    lines.append(f"  {_id(clump.get('clump_id'))}: {clump.get('clump_name')} | nodes={clump.get('node_count')} ids={clump.get('node_ids')}")
    lines.extend(["", "Clump Model Instances:"])
    for instance in payload["instances"]:
        lines.append(
            f"  node {instance.get('clump_node_index')}: OBJ {_id(instance.get('object_id'))} {instance.get('object_name')} -> "
            f"MDL {_id(instance.get('model_id'))} {instance.get('model_name')} submodels={instance.get('submodels')}"
        )
    lines.extend(["", "Sub Models:"])
    for row in payload["submodels"]:
        lines.append(
            f"  {row.get('model_name')}[{row.get('submodel_index')}] part={_id(row.get('part_object_id'))} {row.get('part_object_name')} "
            f"type={row.get('actual_model_type')}/{row.get('masked_model_type')} {row.get('model_type_name')} parser={row.get('parser_mode')}"
        )
        lines.append(
            f"      {row.get('vertices')} Vertices, {row.get('faces')} Triangles, {row.get('uvs')} UVs | "
            f"Material {_id(row.get('mat_tex_id'))}: {row.get('mat_tex_name')}"
        )
        lines.append(
            f"      MAT {_id(row.get('material_id'))} {row.get('material_name')} -> TEX {_id(row.get('texture_id'))} {row.get('texture_name')} "
            f"decoded={row.get('texture_decoded')} CLUT {_id(row.get('clut_id'))} {row.get('clut_name')} resolved={row.get('clut_resolved')}"
        )
        if row.get("warnings"):
            lines.append("      WARN: " + "; ".join(str(value) for value in row["warnings"]))
    lines.extend(["", "Materials:"])
    for row in payload["materials"]:
        lines.append(
            f"  Material {_id(row['material_id'])}: {row['material_name']} -> Texture {_id(row.get('texture_id'))}: {row.get('texture_name')} "
            f"alpha={row.get('alpha')} texture_offset={row.get('texture_offset')} raw={row.get('texture_offset_raw')} status={row.get('status')}"
        )
    lines.extend(["", "Textures:"])
    for row in payload["textures"]:
        lines.append(
            f"  Texture {_id(row.get('texture_id'))}: {row.get('texture_name')} | {row.get('format')} {row.get('width')}x{row.get('height')} "
            f"mip={row.get('mipmap_count')} | CLUT {_id(row.get('clut_id'))}: {row.get('clut_name')} resolved={row.get('clut_resolved')} | status={row.get('status')}"
        )
        if row.get("error"):
            lines.append(f"      ERROR: {row['error']}")
        if row.get("warnings"):
            lines.append("      WARN: " + "; ".join(str(value) for value in row["warnings"]))
    lines.extend(["", "Animations:"])
    for row in payload["animations"]:
        lines.append(
            f"  Animation {_id(row.get('animation_id'))}: {row.get('animation_name')} | {row.get('frame_count')} Frames | {row.get('playback_name')} | "
            f"controllers={row.get('controller_count')} selected-clump-targets={row.get('selected_clump_target_count')} coverage={row.get('selected_clump_coverage', 0.0):.1%}"
        )
        for controller in row.get("controllers") or []:
            lines.append(
                f"      External {_id(controller.get('external_id'))} {controller.get('external_name')} -> Target {_id(controller.get('target_object_id'))} "
                f"{controller.get('target_object_name')} clump_node={controller.get('selected_clump_node_index')} tracks={controller.get('tracks')}"
            )
    if payload.get("errors"):
        lines.extend(["", "Decoder Errors:"] + [f"  {value}" for value in payload["errors"]])
    if payload.get("warnings"):
        lines.extend(["", "Decoder Warnings:"] + [f"  {value}" for value in payload["warnings"]])
    return "\n".join(lines) + "\n"


def write_compare_report(path: str | Path, output_dir: str | Path, *, animation_name: str | None = None, frame: int = 0) -> dict[str, Any]:
    payload = build_compare_report(path, animation_name=animation_name, frame=frame)
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "fragmenter_studioccs_compare.json"
    text_path = root / "fragmenter_studioccs_compare.txt"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(render_compare_text(payload), encoding="utf-8")
    return {"report_path": str(json_path), "text_report_path": str(text_path), "summary": payload["summary"], "selected_clump": payload["selected_clump"]}

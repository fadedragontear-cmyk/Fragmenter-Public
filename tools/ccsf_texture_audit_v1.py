#!/usr/bin/env python3
"""Read-only CCSF texture/material/UV audit for Fragmenter acceptance work."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as base
from ccsf_textured_scene_v4 import load_textured_scene


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _hex(value: int | None) -> str | None:
    return f"0x{value:X}" if isinstance(value, int) and value >= 0 else None


def audit_texture_links(path: str | Path, *, output_json: str | Path | None = None, output_text: str | Path | None = None) -> dict[str, Any]:
    source = Path(path).expanduser()
    scene = load_textured_scene(source)
    report = scene.context.report
    texture_rows = {
        int(row.get("object_id") or -1): row
        for row in scene.texture_rows
        if isinstance(row, dict) and isinstance(row.get("object_id"), int)
    }

    rows: list[dict[str, Any]] = []
    issue_counts: dict[str, int] = {}
    issue_triangles: dict[str, int] = {}

    def add_issue(issue: str, triangles: int) -> None:
        issue_counts[issue] = issue_counts.get(issue, 0) + 1
        issue_triangles[issue] = issue_triangles.get(issue, 0) + max(0, triangles)

    for record in report.records:
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if not model:
            continue
        model_id = _optional_int(record.get("object_id"))
        model_name = str(record.get("object_name") or model_id or "model")
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            mat_tex_id = _optional_int(submodel.get("mat_tex_id"))
            vertex_count = len(submodel.get("vertices") or [])
            uv_count = len(submodel.get("uvs") or [])
            triangle_count = len(submodel.get("faces") or [])
            entry = report.object_lookup.get(mat_tex_id) if mat_tex_id is not None else None
            entry_type = _optional_int((entry or {}).get("section_type")) if isinstance(entry, dict) else None
            material = scene.materials.get(mat_tex_id) if mat_tex_id is not None else None
            texture_id: int | None = None
            texture = None
            resolution = ""
            issues: list[str] = []

            if mat_tex_id is None or mat_tex_id < 0:
                resolution = "missing material/texture reference"
                issues.append(resolution)
            elif not isinstance(entry, dict):
                resolution = f"object {mat_tex_id} missing from object index"
                issues.append(resolution)
            elif entry_type == base.SECTION_TEXTURE:
                texture_id = mat_tex_id
                texture = scene.textures.get(texture_id)
                resolution = "direct TEX reference"
                if texture is None:
                    issues.append("direct TEX is not decoded")
            elif material is not None:
                texture_id = _optional_int(material.get("texture_id"))
                texture = scene.textures.get(texture_id) if texture_id is not None else None
                resolution = "MAT -> TEX reference"
                if texture_id is None:
                    issues.append("material has no texture ID")
                elif texture is None:
                    issues.append("MAT references undecoded TEX")
            else:
                resolution = f"object {mat_tex_id} is not a decoded MAT or TEX"
                issues.append(resolution)

            if vertex_count != uv_count:
                issues.append(f"UV/vertex count mismatch ({uv_count}/{vertex_count})")

            texture_row = texture_rows.get(texture_id) if texture_id is not None else None
            if texture_id is not None and texture_row is None:
                issues.append("referenced TEX has no texture audit row")

            for issue in issues:
                add_issue(issue, triangle_count)

            rows.append(
                {
                    "model_object_id": model_id,
                    "model_object_id_hex": _hex(model_id),
                    "model_object_name": model_name,
                    "model_type": model.get("model_type"),
                    "model_type_name": model.get("model_type_name"),
                    "submodel_index": submodel.get("index"),
                    "parser_mode": submodel.get("parser_mode"),
                    "mat_tex_id": mat_tex_id,
                    "mat_tex_id_hex": _hex(mat_tex_id),
                    "reference_object_name": (entry or {}).get("name") if isinstance(entry, dict) else None,
                    "reference_section_type": entry_type,
                    "reference_section_type_hex": _hex(entry_type),
                    "reference_section_name": base.type_name(entry_type) if entry_type is not None else None,
                    "material_texture_id": texture_id,
                    "material_texture_id_hex": _hex(texture_id),
                    "texture_object_name": (texture_row or {}).get("object_name") if isinstance(texture_row, dict) else None,
                    "texture_decode_status": (texture_row or {}).get("status") if isinstance(texture_row, dict) else None,
                    "texture_format": (texture_row or {}).get("format_name") or (texture_row or {}).get("texture_type_name") if isinstance(texture_row, dict) else None,
                    "texture_width": (texture_row or {}).get("width") if isinstance(texture_row, dict) else None,
                    "texture_height": (texture_row or {}).get("height") if isinstance(texture_row, dict) else None,
                    "texture_clut_id": (texture_row or {}).get("clut_id") if isinstance(texture_row, dict) else None,
                    "texture_clut_resolved": (texture_row or {}).get("clut_resolved") if isinstance(texture_row, dict) else None,
                    "vertex_count": vertex_count,
                    "uv_count": uv_count,
                    "triangle_count": triangle_count,
                    "resolution": resolution,
                    "issues": issues,
                }
            )

    payload = {
        "version": 1,
        "source": str(source),
        "generation": report.header.get("generation"),
        "scene_summary": dict(scene.summary),
        "summary": {
            "submodels": len(rows),
            "clean_submodels": sum(1 for row in rows if not row["issues"]),
            "problem_submodels": sum(1 for row in rows if row["issues"]),
            "texture_records": len(scene.texture_rows),
            "decoded_textures": len(scene.textures),
            "materials": len(scene.materials),
            "issue_counts": dict(sorted(issue_counts.items())),
            "issue_triangles": dict(sorted(issue_triangles.items())),
        },
        "materials": scene.material_rows,
        "textures": scene.texture_rows,
        "submodels": rows,
    }

    if output_json is not None:
        target = Path(output_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["report_path"] = str(target)
    if output_text is not None:
        target = Path(output_text)
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"CCSF Texture Audit: {source}",
            f"Generation: {payload['generation']}",
            f"Submodels: {payload['summary']['submodels']} | clean {payload['summary']['clean_submodels']} | problem {payload['summary']['problem_submodels']}",
            f"Textures: {payload['summary']['decoded_textures']}/{payload['summary']['texture_records']} decoded | materials {payload['summary']['materials']}",
            "",
            "Issue summary:",
        ]
        for issue, count in payload["summary"]["issue_counts"].items():
            lines.append(f"- {issue}: {count} submodel(s), {payload['summary']['issue_triangles'].get(issue, 0)} triangle(s)")
        lines.append("")
        lines.append("Submodels:")
        for row in rows:
            issues = "; ".join(row["issues"]) or "OK"
            lines.append(
                f"- {row['model_object_name']}[{row['submodel_index']}] "
                f"mat={row['mat_tex_id']} ({row['mat_tex_id_hex']}) {row['reference_object_name']} -> "
                f"tex={row['material_texture_id']} ({row['material_texture_id_hex']}) {row['texture_object_name']} "
                f"decode={row['texture_decode_status']} uv={row['uv_count']}/{row['vertex_count']} "
                f"tri={row['triangle_count']} | {issues}"
            )
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        payload["text_report_path"] = str(target)
    return payload

#!/usr/bin/env python3
"""Read-only library-wide CCS texture ownership and setup-record probe."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import ccsf_structure_decoder as base
from project_workspace_v1 import FragmenterProjectV1

REPORT_JSON = "ccsf_texture_library_probe_v1.json"
REPORT_TXT = "ccsf_texture_library_probe_v1.txt"
ASSET_SUFFIXES = {".ccs", ".ccsf", ".tmp"}


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _matching_files(root: Path, patterns: list[str] | tuple[str, ...] | None, max_assets: int) -> list[Path]:
    needles = [str(value).strip().lower() for value in (patterns or []) if str(value).strip()]
    rows = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in ASSET_SUFFIXES]
    if needles:
        rows = [path for path in rows if any(needle in path.name.lower() or needle in path.as_posix().lower() for needle in needles)]
    rows.sort(key=lambda path: path.as_posix().lower())
    return rows[:max_assets] if max_assets > 0 else rows


def inspect_asset(path: Path, root: Path) -> dict[str, Any]:
    report = base.decode(path)
    records_by_object = {
        int(record["object_id"]): record
        for record in report.records
        if isinstance(record, dict) and isinstance(record.get("object_id"), int)
    }
    texture_record_ids = {
        int(record["object_id"])
        for record in report.records
        if isinstance(record, dict)
        and int(record.get("masked_section_type") or -1) == base.SECTION_TEXTURE
        and isinstance(record.get("object_id"), int)
    }
    clut_record_ids = {
        int(record["object_id"])
        for record in report.records
        if isinstance(record, dict)
        and int(record.get("masked_section_type") or -1) == base.SECTION_CLUT
        and isinstance(record.get("object_id"), int)
    }
    material_refs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    material_count = 0
    for record in report.records:
        if not isinstance(record, dict) or int(record.get("masked_section_type") or -1) != base.SECTION_MATERIAL:
            continue
        material_count += 1
        material = record.get("material") or {}
        texture_id = _int(material.get("texture_object_id"))
        if texture_id is None:
            continue
        material_refs[texture_id].append(
            {
                "material_id": record.get("object_id"),
                "material_name": record.get("object_name"),
                "record_offset": record.get("offset"),
            }
        )

    textures: list[dict[str, Any]] = []
    cluts: list[dict[str, Any]] = []
    for object_id, entry in sorted(report.object_lookup.items()):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        section_type = _int(entry.get("section_type"))
        row = {
            "object_id": int(object_id),
            "object_name": name,
            "owning_file_id": entry.get("file_id"),
            "owning_file_name": entry.get("file_name"),
            "section_type": section_type,
            "section_type_name": base.type_name(section_type) if section_type is not None else None,
            "setup_record_offset": (records_by_object.get(int(object_id)) or {}).get("offset"),
        }
        if name.startswith("TEX_") or section_type == base.SECTION_TEXTURE:
            textures.append(
                {
                    **row,
                    "has_texture_setup_record": int(object_id) in texture_record_ids,
                    "referenced_by_materials": material_refs.get(int(object_id), []),
                    "material_reference_count": len(material_refs.get(int(object_id), [])),
                }
            )
        if name.startswith(("CLT_", "CLUT_")) or section_type == base.SECTION_CLUT:
            cluts.append({**row, "has_clut_setup_record": int(object_id) in clut_record_ids})

    unresolved_materials = []
    texture_ids = {int(row["object_id"]) for row in textures}
    for texture_id, materials in sorted(material_refs.items()):
        if texture_id not in texture_record_ids:
            unresolved_materials.append(
                {
                    "texture_id": texture_id,
                    "texture_name": str((report.object_lookup.get(texture_id) or {}).get("name") or ""),
                    "indexed": texture_id in texture_ids,
                    "materials": materials,
                }
            )

    return {
        "path": str(path),
        "relative_path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "generation": report.header.get("generation"),
        "file_index": report.file_index,
        "file_count": len(report.file_index),
        "object_count": len(report.object_lookup),
        "material_records": material_count,
        "texture_setup_records": len(texture_record_ids),
        "clut_setup_records": len(clut_record_ids),
        "indexed_textures": textures,
        "indexed_cluts": cluts,
        "indexed_texture_count": len(textures),
        "indexed_clut_count": len(cluts),
        "missing_texture_setup_count": sum(1 for row in textures if not row["has_texture_setup_record"]),
        "missing_clut_setup_count": sum(1 for row in cluts if not row["has_clut_setup_record"]),
        "unresolved_material_references": unresolved_materials,
        "errors": list(report.errors),
        "warnings": list(report.warnings),
    }


def run_texture_library_probe(
    project: FragmenterProjectV1,
    *,
    patterns: list[str] | tuple[str, ...] | None = None,
    max_assets: int = 0,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    root = project.workspace_path("extracted_ccs")
    files = _matching_files(root, patterns, max_assets)
    assets: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, path in enumerate(files, 1):
        try:
            assets.append(inspect_asset(path, root))
        except Exception as exc:
            failures.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
        if callback is not None and (index == len(files) or index % 25 == 0):
            callback({"kind": "texture_probe_progress", "current": index, "total": len(files), "detail": path.name})

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for asset in assets:
        for texture in asset["indexed_textures"]:
            by_name[str(texture["object_name"])].append(
                {
                    "asset": asset["relative_path"],
                    "object_id": texture["object_id"],
                    "owning_file_id": texture.get("owning_file_id"),
                    "owning_file_name": texture.get("owning_file_name"),
                    "has_texture_setup_record": texture["has_texture_setup_record"],
                    "material_reference_count": texture["material_reference_count"],
                }
            )
    for asset in assets:
        for texture in asset["indexed_textures"]:
            candidates = [row for row in by_name.get(str(texture["object_name"]), []) if row["has_texture_setup_record"] and row["asset"] != asset["relative_path"]]
            texture["cross_asset_setup_candidates"] = candidates

    missing = [
        {"asset": asset["relative_path"], **texture}
        for asset in assets
        for texture in asset["indexed_textures"]
        if not texture["has_texture_setup_record"]
    ]
    summary = {
        "version": 1,
        "workspace": project.workspace_dir,
        "patterns": list(patterns or []),
        "max_assets": max_assets,
        "assets_considered": len(files),
        "assets_scanned": len(assets),
        "assets_failed": len(failures),
        "assets_with_indexed_textures": sum(1 for row in assets if row["indexed_texture_count"]),
        "assets_with_texture_setup_records": sum(1 for row in assets if row["texture_setup_records"]),
        "assets_with_missing_texture_setup": sum(1 for row in assets if row["missing_texture_setup_count"]),
        "indexed_texture_objects": sum(row["indexed_texture_count"] for row in assets),
        "texture_setup_records": sum(row["texture_setup_records"] for row in assets),
        "indexed_textures_missing_setup": len(missing),
        "missing_with_cross_asset_setup_candidate": sum(1 for row in missing if row["cross_asset_setup_candidates"]),
        "unique_texture_names": len(by_name),
        "duplicate_texture_names": sum(1 for rows in by_name.values() if len(rows) > 1),
    }
    payload = {"summary": summary, "assets": assets, "missing_texture_setup": missing, "texture_name_index": dict(sorted(by_name.items())), "failures": failures}
    output = project.workspace_path("diagnostics") / "visual"
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    txt_path = output / REPORT_TXT
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    txt_path.write_text(render_text(payload), encoding="utf-8")
    return {**summary, "report_path": str(json_path), "text_report_path": str(txt_path)}


def render_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "Fragmenter CCS Texture Library Probe v1",
        "=======================================",
        f"Assets: considered={summary['assets_considered']} scanned={summary['assets_scanned']} failed={summary['assets_failed']}",
        f"Texture objects: indexed={summary['indexed_texture_objects']} setup_records={summary['texture_setup_records']} missing_setup={summary['indexed_textures_missing_setup']}",
        f"Missing textures with same-name setup in another CCS: {summary['missing_with_cross_asset_setup_candidate']}",
        "",
        "Assets with missing Texture setup records",
        "-----------------------------------------",
    ]
    rows = sorted((row for row in payload["assets"] if row["missing_texture_setup_count"]), key=lambda row: (-row["missing_texture_setup_count"], row["relative_path"]))
    for asset in rows:
        lines.append(f"- {asset['relative_path']}: indexed={asset['indexed_texture_count']} setup={asset['texture_setup_records']} missing={asset['missing_texture_setup_count']} size={asset['size']}")
        for texture in asset["indexed_textures"]:
            if texture["has_texture_setup_record"]:
                continue
            candidates = texture.get("cross_asset_setup_candidates") or []
            candidate_text = ", ".join(row["asset"] for row in candidates[:5]) or "none"
            lines.append(
                f"    {texture['object_id']} {texture['object_name']} owner={texture.get('owning_file_id')}:{texture.get('owning_file_name')} materials={texture['material_reference_count']} cross_asset={candidate_text}"
            )
    if payload["failures"]:
        lines.extend(["", "Failures", "--------"])
        lines.extend(f"- {row['path']}: {row['error']}" for row in payload["failures"])
    return "\n".join(lines) + "\n"

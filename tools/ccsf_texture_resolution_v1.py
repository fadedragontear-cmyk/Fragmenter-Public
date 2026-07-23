#!/usr/bin/env python3
"""Conservative local TEX/CLUT resolution matching StudioCCS ownership rules.

StudioCCS exposes every CLUT owned by a texture's indexed sub-file as an
alternate palette. Fragmenter still honors the texture's referenced CLUT first.
If that setup record is absent or malformed, it uses a fallback only when one
and only one compatible CLUT exists in the same indexed sub-file.
"""
from __future__ import annotations

from typing import Any

import ccsf_structure_decoder as base
import ccsf_texture_decoder_v2 as texture_v2


def _object_id(record: dict[str, Any]) -> int:
    return int(record.get("object_id") or 0)


def _file_id(report: Any, object_id: int) -> int | None:
    entry = report.object_lookup.get(int(object_id)) or {}
    try:
        return int(entry.get("file_id")) if entry.get("file_id") is not None else None
    except (TypeError, ValueError):
        return None


def _palette_compatible(texture_type: int, clut: dict[str, Any]) -> bool:
    count = int(clut.get("color_count") or len(clut.get("palette") or []))
    if texture_type == texture_v2.TEXTURE_I4:
        return count >= 16
    if texture_type == texture_v2.TEXTURE_I8:
        return count >= 256
    return True


def parse_cluts(data: bytes, report: Any) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    cluts: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for record in report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_CLUT:
            continue
        row = {
            "object_id": record.get("object_id"),
            "object_name": record.get("object_name"),
            "owning_file_id": _file_id(report, _object_id(record)),
        }
        try:
            parsed = texture_v2.parse_clut_record(data, record)
            parsed["owning_file_id"] = row["owning_file_id"]
            cluts[int(parsed["object_id"])] = parsed
            row.update({"status": "decoded", "color_count": parsed.get("color_count")})
        except Exception as exc:
            row.update({"status": "error", "error": str(exc)})
        rows.append(row)
    return cluts, rows


def resolve_clut_for_texture(
    report: Any,
    texture_record: dict[str, Any],
    texture: dict[str, Any],
    cluts: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    requested_id = int(texture.get("clut_id") or -1)
    exact = cluts.get(requested_id)
    evidence: dict[str, Any] = {
        "requested_clut_id": requested_id,
        "requested_clut_name": str((report.object_lookup.get(requested_id) or {}).get("name") or ""),
        "texture_file_id": _file_id(report, _object_id(texture_record)),
        "status": "missing",
        "compatible_same_file_candidates": [],
    }
    if exact is not None:
        evidence.update({"status": "exact", "resolved_clut_id": requested_id, "resolved_clut_name": exact.get("object_name")})
        return exact, evidence

    texture_type = int(texture.get("texture_type") or 0)
    if texture_type not in {texture_v2.TEXTURE_I4, texture_v2.TEXTURE_I8}:
        evidence["status"] = "not_required"
        return None, evidence

    file_id = evidence["texture_file_id"]
    candidates = [
        clut
        for clut in cluts.values()
        if clut.get("owning_file_id") == file_id and _palette_compatible(texture_type, clut)
    ]
    evidence["compatible_same_file_candidates"] = [
        {"object_id": row.get("object_id"), "object_name": row.get("object_name"), "color_count": row.get("color_count")}
        for row in candidates
    ]
    if len(candidates) == 1:
        selected = candidates[0]
        evidence.update(
            {
                "status": "unique_same_subfile_fallback",
                "resolved_clut_id": selected.get("object_id"),
                "resolved_clut_name": selected.get("object_name"),
            }
        )
        return selected, evidence
    evidence["status"] = "ambiguous_same_subfile" if candidates else "missing"
    return None, evidence


def parse_local_textures(context: Any) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    data = context.data
    report = context.report
    generation = str(report.header.get("generation") or "Unknown")
    cluts, _clut_rows = parse_cluts(data, report)
    textures: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []

    for record in report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_TEXTURE:
            continue
        row: dict[str, Any] = {
            "object_id": record.get("object_id"),
            "object_name": record.get("object_name"),
            "owning_file_id": _file_id(report, _object_id(record)),
        }
        try:
            parsed = texture_v2.parse_texture_record(data, record, generation)
            row.update(
                {
                    "texture_type": parsed.get("texture_type"),
                    "texture_type_name": parsed.get("texture_type_name"),
                    "width": parsed.get("width"),
                    "height": parsed.get("height"),
                    "clut_id": parsed.get("clut_id"),
                    "decode_status": parsed.get("status"),
                    "warnings": list(parsed.get("warnings") or []),
                }
            )
            if parsed.get("status") != "pixel_data_decoded":
                row["status"] = "unsupported_or_metadata_only"
            else:
                clut, clut_evidence = resolve_clut_for_texture(report, record, parsed, cluts)
                parsed["clut_resolution"] = clut_evidence
                parsed["clut_resolved"] = clut is not None
                parsed["clut_resolution_status"] = clut_evidence.get("status")
                parsed["resolved_clut_id"] = clut_evidence.get("resolved_clut_id")
                parsed["rgba"] = texture_v2.decode_rgba(parsed, clut)
                textures[int(parsed["object_id"])] = parsed
                row.update(
                    {
                        "status": "decoded_rgba",
                        "rgba_bytes": len(parsed["rgba"]),
                        "clut_resolved": clut is not None,
                        "clut_resolution": clut_evidence,
                        "resolved_clut_id": clut_evidence.get("resolved_clut_id"),
                    }
                )
        except Exception as exc:
            row.update({"status": "error", "error": str(exc)})
        rows.append(row)
    return textures, rows

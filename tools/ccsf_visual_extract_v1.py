#!/usr/bin/env python3
"""Fast public visual extraction using the lightweight CCSF record index."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as schema
from ccsf_animation_decoder_v1 import SECTION_ANIMATION, parse_animation_payload
from ccsf_record_index_v1 import index_file
from ccsf_scene_v1 import build_scene_graph, parse_clump_record, parse_object_record
from ccsf_texture_decoder_v1 import decode_rgba, parse_clut_record, parse_texture_record, write_rgba_png


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return cleaned or "asset"


def fast_visual_index(asset_path: str | Path) -> dict[str, Any]:
    return index_file(asset_path)


def extract_textures_fast(asset_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(asset_path).expanduser()
    raw = source.read_bytes()
    index = index_file(source)
    generation = str((index.get("header") or {}).get("generation") or "Unknown")
    records = index.get("records") if isinstance(index.get("records"), list) else []
    cluts: dict[int, dict[str, Any]] = {}
    clut_rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or int(record.get("masked_section_type") or 0) != schema.SECTION_CLUT:
            continue
        try:
            clut = parse_clut_record(raw, record)
            cluts[int(clut["object_id"])] = clut
            clut_rows.append({key: value for key, value in clut.items() if key != "palette"})
        except Exception as exc:
            clut_rows.append({"object_id": record.get("object_id"), "object_name": record.get("object_name"), "status": "error", "error": str(exc)})

    output_root = Path(output_dir).expanduser()
    textures: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or int(record.get("masked_section_type") or 0) != schema.SECTION_TEXTURE:
            continue
        try:
            texture = parse_texture_record(raw, record, generation)
            row = {key: value for key, value in texture.items() if key != "pixel_data"}
            clut = cluts.get(int(texture.get("clut_id") or -1))
            row["clut_name"] = clut.get("object_name") if clut else None
            if texture.get("status") == "pixel_data_decoded":
                rgba = decode_rgba(texture, clut)
                name = _safe_name(str(texture.get("object_name") or f"texture_{texture.get('object_id')}"))
                png = write_rgba_png(output_root / f"{name}.png", int(texture["width"]), int(texture["height"]), rgba)
                row.update({"status": "png_exported", "png_path": str(png), "rgba_bytes": len(rgba)})
            textures.append(row)
        except Exception as exc:
            textures.append({"object_id": record.get("object_id"), "object_name": record.get("object_name"), "status": "error", "error": str(exc)})
    report = {
        "version": 1,
        "parser": "ccsf_record_index_v1",
        "source": str(source),
        "generation": generation,
        "textures": textures,
        "cluts": clut_rows,
        "index_errors": list(index.get("errors") or []),
        "summary": {"texture_records": len(textures), "clut_records": len(clut_rows), "png_exported": sum(1 for row in textures if row.get("status") == "png_exported")},
    }
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "texture_extract_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def extract_animation_fast(asset_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(asset_path).expanduser()
    raw = source.read_bytes()
    index = index_file(source)
    generation = str((index.get("header") or {}).get("generation") or "Unknown")
    lookup = {int(row["id"]): row for row in index.get("object_index", []) if isinstance(row, dict) and row.get("id") is not None}
    animations: list[dict[str, Any]] = []
    for record in index.get("records", []):
        if not isinstance(record, dict) or int(record.get("masked_section_type") or 0) != SECTION_ANIMATION:
            continue
        row: dict[str, Any] = {"object_id": record.get("object_id"), "object_name": record.get("object_name"), "generation": generation}
        try:
            row.update(parse_animation_payload(raw, int(record["payload_start"]), int(record["payload_end"]), object_lookup=lookup, generation=generation))
        except Exception as exc:
            row.update({"metadata_status": "error", "playback_ready": False, "error": str(exc)})
        animations.append(row)
    report = {
        "version": 1,
        "parser": "ccsf_record_index_v1",
        "source": str(source),
        "generation": generation,
        "animations": animations,
        "index_errors": list(index.get("errors") or []),
        "summary": {"animation_records": len(animations), "metadata_parsed": sum(1 for row in animations if row.get("metadata_status") == "parsed"), "playback_ready": sum(1 for row in animations if row.get("playback_ready"))},
    }
    out = Path(output_dir).expanduser(); out.mkdir(parents=True, exist_ok=True)
    report_path = out / "animation_metadata.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def extract_scene_fast(asset_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(asset_path).expanduser()
    raw = source.read_bytes()
    index = index_file(source)
    generation = str((index.get("header") or {}).get("generation") or "Unknown")
    lookup = {int(row["id"]): row for row in index.get("object_index", []) if isinstance(row, dict) and row.get("id") is not None}
    objects: list[dict[str, Any]] = []
    clumps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for record in index.get("records", []):
        if not isinstance(record, dict):
            continue
        record_type = int(record.get("masked_section_type") or 0)
        try:
            if record_type == schema.SECTION_OBJECT:
                objects.append(parse_object_record(raw, record, generation))
            elif record_type == schema.SECTION_CLUMP:
                clumps.append(parse_clump_record(raw, record, generation))
        except Exception as exc:
            errors.append({"object_id": record.get("object_id"), "object_name": record.get("object_name"), "type": record_type, "error": str(exc)})
    graph = build_scene_graph(objects, clumps, lookup)
    report = {
        "version": 1,
        "parser": "ccsf_record_index_v1",
        "source": str(source),
        "generation": generation,
        "objects": objects,
        "clumps": clumps,
        "scene": graph,
        "errors": errors,
        "index_errors": list(index.get("errors") or []),
        "summary": {"objects": len(objects), "clumps": len(clumps), "nodes": graph["node_count"], "roots": graph["root_count"], "errors": len(errors), "assembly_status": graph["assembly_status"]},
    }
    out = Path(output_dir).expanduser(); out.mkdir(parents=True, exist_ok=True)
    report_path = out / "scene_metadata.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report

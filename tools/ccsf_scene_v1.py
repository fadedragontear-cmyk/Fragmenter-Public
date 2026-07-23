#!/usr/bin/env python3
"""StudioCCS-backed CCSF Object/Clump scene graph for Fragmenter 1.0.

Gen1 Object records provide parent/model/shadow relationships. Gen1 Clump records
provide node membership and ordering. They do not provide a static bind pose; pose
must come from animation/controller tracks. This module does not invent transforms.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

import ccsf_structure_decoder


def _need(data: bytes, start: int, size: int, end: int, label: str) -> None:
    if start < 0 or size < 0 or start + size > end or start + size > len(data):
        raise ValueError(f"{label} exceeds setup-record payload bounds")


def _i32(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 4, end, "int32")
    return struct.unpack_from("<i", data, offset)[0]


def parse_object_record(data: bytes, record: dict[str, Any], generation: str) -> dict[str, Any]:
    start = int(record.get("payload_start") or 0)
    end = int(record.get("payload_end") or 0)
    _need(data, start, 12, end, "Object payload")
    row = {
        "object_id": int(record.get("object_id") or 0),
        "object_name": str(record.get("object_name") or ""),
        "parent_object_id": _i32(data, start, end),
        "model_id": _i32(data, start + 4, end),
        "shadow_id": _i32(data, start + 8, end),
        "generation": generation,
        "payload_start": start,
        "payload_end": end,
        "parse_status": "parsed",
    }
    if generation != "Gen1":
        if end - start >= 16:
            row["generation_extra"] = struct.unpack_from("<I", data, start + 12)[0]
        else:
            row["parse_status"] = "partial_non_gen1"
    return row


def parse_clump_record(data: bytes, record: dict[str, Any], generation: str) -> dict[str, Any]:
    start = int(record.get("payload_start") or 0)
    end = int(record.get("payload_end") or 0)
    _need(data, start, 4, end, "Clump header")
    node_count = _i32(data, start, end)
    if node_count < 0 or node_count > 1_000_000:
        raise ValueError(f"invalid Clump node count: {node_count}")
    nodes_start = start + 4
    _need(data, nodes_start, node_count * 4, end, "Clump node IDs")
    node_ids = [_i32(data, nodes_start + index * 4, end) for index in range(node_count)]
    row: dict[str, Any] = {
        "object_id": int(record.get("object_id") or 0),
        "object_name": str(record.get("object_name") or ""),
        "node_count": node_count,
        "node_ids": node_ids,
        "generation": generation,
        "payload_start": start,
        "payload_end": end,
        "parse_status": "parsed_gen1" if generation == "Gen1" else "node_list_parsed_bind_pose_unparsed",
        "bind_pose_available": generation != "Gen1",
    }
    if generation == "Gen1":
        row["pose_source"] = "animation/controller tracks"
    else:
        row["pose_source"] = "non-Gen1 bind pose follows node IDs; not decoded in this pass"
    return row


def _name(lookup: dict[int, dict[str, Any]], object_id: int) -> str:
    row = lookup.get(object_id)
    return str(row.get("name") or "") if isinstance(row, dict) else ""


def _detect_parent_cycle(objects: dict[int, dict[str, Any]], start_id: int) -> list[int] | None:
    seen: list[int] = []
    current = start_id
    while current:
        if current in seen:
            index = seen.index(current)
            return seen[index:] + [current]
        seen.append(current)
        row = objects.get(current)
        if not row:
            return None
        current = int(row.get("parent_object_id") or 0)
    return None


def build_scene_graph(
    objects: list[dict[str, Any]],
    clumps: list[dict[str, Any]],
    lookup: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    object_by_id = {int(row["object_id"]): row for row in objects}
    memberships: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []
    for clump in clumps:
        clump_id = int(clump["object_id"])
        for node_index, object_id in enumerate(clump.get("node_ids") or []):
            object_id = int(object_id)
            if object_id in memberships:
                warnings.append(f"object {object_id} appears in multiple Clumps")
            memberships[object_id] = {
                "clump_id": clump_id,
                "clump_name": str(clump.get("object_name") or ""),
                "node_index": node_index,
            }

    nodes: list[dict[str, Any]] = []
    roots: list[int] = []
    for object_id in sorted(object_by_id):
        row = object_by_id[object_id]
        parent_id = int(row.get("parent_object_id") or 0)
        model_id = int(row.get("model_id") or 0)
        shadow_id = int(row.get("shadow_id") or 0)
        membership = memberships.get(object_id, {})
        node = {
            "object_id": object_id,
            "object_name": str(row.get("object_name") or _name(lookup, object_id)),
            "parent_object_id": parent_id,
            "parent_object_name": _name(lookup, parent_id) if parent_id else "",
            "model_id": model_id,
            "model_name": _name(lookup, model_id) if model_id else "",
            "shadow_id": shadow_id,
            "shadow_name": _name(lookup, shadow_id) if shadow_id else "",
            "clump_id": membership.get("clump_id"),
            "clump_name": membership.get("clump_name", ""),
            "node_index": membership.get("node_index"),
            "local_transform_status": "identity until pose/controller evaluation",
            "world_transform_status": "unresolved",
        }
        if parent_id == 0:
            roots.append(object_id)
        elif parent_id not in object_by_id:
            warnings.append(f"object {object_id} references missing parent {parent_id}")
        if model_id and model_id not in lookup:
            warnings.append(f"object {object_id} references missing model {model_id}")
        nodes.append(node)

    cycles: list[list[int]] = []
    seen_cycles: set[tuple[int, ...]] = set()
    for object_id in object_by_id:
        cycle = _detect_parent_cycle(object_by_id, object_id)
        if cycle:
            normalized = tuple(sorted(set(cycle)))
            if normalized not in seen_cycles:
                seen_cycles.add(normalized)
                cycles.append(cycle)
    if cycles:
        warnings.append(f"parent cycles detected: {cycles}")

    return {
        "nodes": nodes,
        "node_count": len(nodes),
        "roots": roots,
        "root_count": len(roots),
        "clumps": clumps,
        "clump_count": len(clumps),
        "cycles": cycles,
        "warnings": warnings,
        "assembly_status": "hierarchy_ready_pose_unresolved" if nodes else "no_object_hierarchy",
        "pose_status": "requires animation/controller track evaluation",
        "preview_modes": ["assembled", "selected_object", "raw_model"],
    }


def extract_scene_metadata(asset_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(asset_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    raw = source.read_bytes()
    structure = ccsf_structure_decoder.report_to_dict(ccsf_structure_decoder.decode(source))
    generation = str((structure.get("header") or {}).get("generation") or "Unknown")
    records = structure.get("records") if isinstance(structure.get("records"), list) else []
    lookup = {
        int(row["id"]): row
        for row in (structure.get("object_index") or [])
        if isinstance(row, dict) and row.get("id") is not None
    }

    objects: list[dict[str, Any]] = []
    clumps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        record_type = int(record.get("masked_section_type") or 0)
        try:
            if record_type == ccsf_structure_decoder.SECTION_OBJECT:
                objects.append(parse_object_record(raw, record, generation))
            elif record_type == ccsf_structure_decoder.SECTION_CLUMP:
                clumps.append(parse_clump_record(raw, record, generation))
        except Exception as exc:
            errors.append(
                {
                    "object_id": record.get("object_id"),
                    "object_name": record.get("object_name"),
                    "type": record_type,
                    "error": str(exc),
                }
            )

    graph = build_scene_graph(objects, clumps, lookup)
    report = {
        "version": 1,
        "source": str(source),
        "generation": generation,
        "objects": objects,
        "clumps": clumps,
        "scene": graph,
        "errors": errors,
        "summary": {
            "objects": len(objects),
            "clumps": len(clumps),
            "nodes": graph["node_count"],
            "roots": graph["root_count"],
            "errors": len(errors),
            "assembly_status": graph["assembly_status"],
        },
    }
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "scene_metadata.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract CCSF Object/Clump scene metadata")
    parser.add_argument("asset", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = extract_scene_metadata(args.asset, args.out)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

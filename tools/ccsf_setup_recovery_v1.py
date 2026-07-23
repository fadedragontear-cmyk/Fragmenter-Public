#!/usr/bin/env python3
"""Recover exact indexed MAT/TEX/CLUT records skipped by oversized Gen1 bounds.

Some Gen1 deformable-model section size fields extend beyond the bytes actually
consumed by StudioCCS's model reader. A generic size-based setup walker therefore
jumps over later material, texture, and palette setup records. Recovery is strict:
we only accept a 4-byte-aligned header whose masked section type and object ID
exactly match an indexed object with the corresponding MAT_/TEX_/CLT_ name.
"""
from __future__ import annotations

import copy
import struct
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as base

_PREFIX_TYPES = (
    ("MAT_", base.SECTION_MATERIAL),
    ("TEX_", base.SECTION_TEXTURE),
    ("CLT_", base.SECTION_CLUT),
    ("CLUT_", base.SECTION_CLUT),
)
_KNOWN_TEXTURE_TYPES = {0x00, 0x13, 0x14, 0x87, 0x89}
_CACHE: dict[tuple[str, int, int], list[dict[str, Any]]] = {}


def _expected_type(name: str) -> int | None:
    return next((section_type for prefix, section_type in _PREFIX_TYPES if name.startswith(prefix)), None)


def _outer_end(offset: int, raw_size: int) -> int:
    # StudioCCS reads type + size, then treats size - 1 words as the payload after
    # the object ID. Total record span is therefore 8 + size*4 bytes.
    return offset + 8 + raw_size * 4


def _validate_candidate(data: bytes, offset: int, section_type: int, object_id: int) -> dict[str, Any] | None:
    if offset < 0 or offset % 4 or offset + 12 > len(data):
        return None
    raw_type, raw_size, candidate_id = struct.unpack_from("<III", data, offset)
    if (raw_type & 0xFFFF) != section_type or candidate_id != object_id or raw_size < 1:
        return None
    end = _outer_end(offset, raw_size)
    if end > len(data):
        return None
    payload_start = offset + 12
    evidence: dict[str, Any] = {"outer_payload_end": end}

    if section_type == base.SECTION_MATERIAL:
        if payload_start + 12 > end:
            return None
        texture_id = struct.unpack_from("<i", data, payload_start)[0]
        evidence.update({"texture_id": texture_id, "actual_payload_end": payload_start + 12})
    elif section_type == base.SECTION_CLUT:
        if payload_start + 16 > end:
            return None
        color_count = struct.unpack_from("<i", data, payload_start + 12)[0]
        actual_end = payload_start + 16 + color_count * 4
        if color_count < 0 or color_count > 65536 or actual_end > len(data):
            return None
        evidence.update({"color_count": color_count, "actual_payload_end": actual_end})
    elif section_type == base.SECTION_TEXTURE:
        if payload_start + 24 > len(data):
            return None
        texture_type = data[payload_start + 9]
        width_code = data[payload_start + 12]
        height_code = data[payload_start + 13]
        if texture_type not in _KNOWN_TEXTURE_TYPES or width_code > 15 or height_code > 15:
            return None
        width, height = 1 << width_code, 1 << height_code
        size_value = struct.unpack_from("<i", data, payload_start + 20)[0]
        if size_value < 0:
            return None
        if texture_type == 0x14:
            required = (width * height + 1) // 2
            actual_end = payload_start + 24 + required
        elif texture_type == 0x13:
            required = width * height
            actual_end = payload_start + 24 + required
        elif texture_type == 0x00:
            required = width * height * 4
            actual_end = payload_start + 24 + required
        else:
            block_size = 8 if texture_type == 0x87 else 16
            required = ((width + 3) // 4) * ((height + 3) // 4) * block_size
            actual_end = payload_start + 0x40 + required
        if actual_end > len(data):
            return None
        evidence.update(
            {
                "texture_type": texture_type,
                "width": width,
                "height": height,
                "inner_size_value": size_value,
                "required_base_bytes": required,
                "actual_payload_end": actual_end,
                "outer_size_overlap_bytes": max(0, end - actual_end),
            }
        )
    else:
        return None

    return {
        "offset": offset,
        "raw_section_type": raw_type,
        "masked_section_type": section_type,
        "type_name": base.type_name(section_type),
        "raw_size_field": raw_size,
        "calculated_payload_size": max(0, (raw_size - 1) * 4),
        "object_id": object_id,
        "payload_start": payload_start,
        "payload_end": end,
        "parse_status": "recovered_indexed_setup_record",
        "warnings": [],
        "errors": [],
        "recovery": {
            "method": "exact indexed name + masked section type + object ID scan",
            **evidence,
        },
    }


def _scan(source: Path, data: bytes, report: Any) -> list[dict[str, Any]]:
    stat = source.stat()
    cache_key = (str(source.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    existing = {
        (int(record.get("masked_section_type") or 0), int(record.get("object_id") or -1))
        for record in report.records
        if isinstance(record, dict)
    }
    setup_start = int((report.setup or {}).get("offset") or 0)
    recovered: list[dict[str, Any]] = []

    for raw_object_id, entry in report.object_lookup.items():
        object_id = int(raw_object_id)
        name = str((entry or {}).get("name") or "")
        section_type = _expected_type(name)
        if section_type is None or (section_type, object_id) in existing:
            continue
        needle = struct.pack("<I", object_id)
        cursor = max(8, setup_start + 8)
        candidates: list[dict[str, Any]] = []
        while True:
            object_offset = data.find(needle, cursor)
            if object_offset < 0:
                break
            cursor = object_offset + 1
            record = _validate_candidate(data, object_offset - 8, section_type, object_id)
            if record is not None:
                candidates.append(record)
        if not candidates:
            continue
        # Prefer canonical 0xCCCCxxxx record headers and then the earliest exact hit.
        candidates.sort(
            key=lambda record: (
                0 if (int(record["raw_section_type"]) >> 16) == 0xCCCC else 1,
                int(record["offset"]),
            )
        )
        selected = candidates[0]
        selected.update(
            {
                "object_name": name,
                "owning_file_id": entry.get("file_id"),
                "owning_file_name": entry.get("file_name", ""),
            }
        )
        recovered.append(selected)

    recovered.sort(key=lambda record: int(record["offset"]))
    _CACHE[cache_key] = copy.deepcopy(recovered)
    return recovered


def recover_report(source: str | Path, data: bytes, report: Any) -> dict[str, Any]:
    """Augment one decoded report with exact recovered setup records."""
    path = Path(source).expanduser().resolve()
    recovered = _scan(path, data, report)
    existing = {
        (int(record.get("masked_section_type") or 0), int(record.get("object_id") or -1))
        for record in report.records
        if isinstance(record, dict)
    }
    added: list[dict[str, Any]] = []
    for template in recovered:
        key = (int(template["masked_section_type"]), int(template["object_id"]))
        if key in existing:
            continue
        record = copy.deepcopy(template)
        report.records.append(record)
        existing.add(key)
        added.append(record)
        lookup = report.object_lookup.get(int(record["object_id"]))
        if isinstance(lookup, dict):
            lookup["section_type"] = int(record["masked_section_type"])
            lookup["section_type_name"] = str(record["type_name"])
            lookup["section_offset"] = int(record["offset"]) - int((report.setup or {}).get("offset") or 0)
            lookup["absolute_offset"] = int(record["offset"])
            lookup["typed_setup_record"] = record
            lookup["recovered_indexed_setup_record"] = True
    if added:
        report.records.sort(key=lambda record: int(record.get("offset") or 0))
    summary = {
        "count": len(recovered),
        "added_this_report": len(added),
        "materials": sum(1 for row in recovered if int(row["masked_section_type"]) == base.SECTION_MATERIAL),
        "textures": sum(1 for row in recovered if int(row["masked_section_type"]) == base.SECTION_TEXTURE),
        "cluts": sum(1 for row in recovered if int(row["masked_section_type"]) == base.SECTION_CLUT),
        "objects": [str(row.get("object_name") or row.get("object_id")) for row in recovered],
    }
    report.setup["indexed_setup_recovery"] = summary
    return summary


def recover_context(context: Any) -> dict[str, Any]:
    return recover_report(context.source, context.data, context.report)


def clear_recovery_cache(source: str | Path | None = None) -> None:
    if source is None:
        _CACHE.clear()
        return
    resolved = str(Path(source).expanduser().resolve())
    for key in [key for key in _CACHE if key[0] == resolved]:
        _CACHE.pop(key, None)

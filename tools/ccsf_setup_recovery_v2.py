#!/usr/bin/env python3
"""Fast exact recovery of indexed MAT/TEX/CLUT setup records.

The v1 authority established the safe acceptance rules. This layer keeps those
validators but discovers canonical ``0xCCCCxxxx`` record headers in three C-level
``bytes.find`` passes instead of searching the whole file once per missing object.
It also accepts one observed Gen1 edge case: an exact indexed TEX at end-of-file
whose outer section size extends beyond EOF while its inner header and complete
base-level pixel payload remain bounded and valid.
"""
from __future__ import annotations

import copy
import struct
from pathlib import Path
from typing import Any

import ccsf_setup_recovery_v1 as v1
import ccsf_structure_decoder as base

_TARGET_TYPES = (base.SECTION_MATERIAL, base.SECTION_TEXTURE, base.SECTION_CLUT)
_MAX_EOF_OUTER_OVERSHOOT = 0x400
_BASE_VALIDATE = v1._validate_candidate


def _texture_base_bounds(data: bytes, payload_start: int) -> dict[str, Any] | None:
    if payload_start < 0 or payload_start + 24 > len(data):
        return None
    texture_type = data[payload_start + 9]
    width_code = data[payload_start + 12]
    height_code = data[payload_start + 13]
    if texture_type not in v1._KNOWN_TEXTURE_TYPES or width_code > 15 or height_code > 15:
        return None
    width, height = 1 << width_code, 1 << height_code
    size_value = struct.unpack_from("<i", data, payload_start + 20)[0]
    if size_value < 0:
        return None
    if texture_type == 0x14:
        required = (width * height + 1) // 2
        data_start = payload_start + 24
    elif texture_type == 0x13:
        required = width * height
        data_start = payload_start + 24
    elif texture_type == 0x00:
        required = width * height * 4
        data_start = payload_start + 24
    else:
        block_size = 8 if texture_type == 0x87 else 16
        required = ((width + 3) // 4) * ((height + 3) // 4) * block_size
        data_start = payload_start + 0x40
    actual_end = data_start + required
    if actual_end > len(data):
        return None
    return {
        "texture_type": texture_type,
        "width": width,
        "height": height,
        "inner_size_value": size_value,
        "required_base_bytes": required,
        "data_start": data_start,
        "actual_payload_end": actual_end,
    }


def _validate_candidate(data: bytes, offset: int, section_type: int, object_id: int) -> dict[str, Any] | None:
    accepted = _BASE_VALIDATE(data, offset, section_type, object_id)
    if accepted is not None:
        return accepted
    if section_type != base.SECTION_TEXTURE or offset < 0 or offset % 4 or offset + 12 > len(data):
        return None
    raw_type, raw_size, candidate_id = struct.unpack_from("<III", data, offset)
    if (raw_type & 0xFFFF) != section_type or candidate_id != object_id or raw_size < 1:
        return None
    claimed_end = v1._outer_end(offset, raw_size)
    if claimed_end <= len(data):
        return None
    overshoot = claimed_end - len(data)
    if overshoot > _MAX_EOF_OUTER_OVERSHOOT:
        return None
    payload_start = offset + 12
    evidence = _texture_base_bounds(data, payload_start)
    if evidence is None:
        return None
    bounded_end = max(int(evidence["actual_payload_end"]), len(data))
    return {
        "offset": offset,
        "raw_section_type": raw_type,
        "masked_section_type": section_type,
        "type_name": base.type_name(section_type),
        "raw_size_field": raw_size,
        "calculated_payload_size": max(0, bounded_end - payload_start),
        "object_id": object_id,
        "payload_start": payload_start,
        "payload_end": bounded_end,
        "parse_status": "recovered_indexed_setup_record",
        "warnings": [
            f"outer TEX size exceeds EOF by {overshoot} byte(s); complete inner base-level payload accepted"
        ],
        "errors": [],
        "recovery": {
            "method": "exact indexed EOF TEX + bounded inner Gen1 texture payload",
            "outer_payload_end": claimed_end,
            "outer_size_truncated_bytes": overshoot,
            **evidence,
        },
    }


def _canonical_offsets(
    data: bytes,
    start: int,
    expected: dict[tuple[int, int], tuple[str, dict[str, Any]]],
) -> dict[tuple[int, int], list[int]]:
    """Return aligned canonical header offsets for expected indexed objects."""
    found: dict[tuple[int, int], list[int]] = {}
    lower = max(0, int(start))
    for section_type in _TARGET_TYPES:
        marker = struct.pack("<I", 0xCCCC0000 | int(section_type))
        cursor = lower
        while True:
            offset = data.find(marker, cursor)
            if offset < 0:
                break
            cursor = offset + 4
            if offset % 4 or offset + 12 > len(data):
                continue
            object_id = struct.unpack_from("<I", data, offset + 8)[0]
            key = (int(section_type), int(object_id))
            if key in expected:
                found.setdefault(key, []).append(offset)
    return found


def _fallback_offsets(data: bytes, start: int, section_type: int, object_id: int) -> list[int]:
    """Find rare non-canonical headers by object ID, bounded by the validator."""
    needle = struct.pack("<I", int(object_id))
    cursor = max(8, int(start))
    offsets: list[int] = []
    while True:
        object_offset = data.find(needle, cursor)
        if object_offset < 0:
            break
        cursor = object_offset + 1
        header_offset = object_offset - 8
        if _validate_candidate(data, header_offset, int(section_type), int(object_id)) is not None:
            offsets.append(header_offset)
    return offsets


def _scan(source: Path, data: bytes, report: Any) -> list[dict[str, Any]]:
    stat = source.stat()
    cache_key = (str(source.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = v1._CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    existing = {
        (int(record.get("masked_section_type") or 0), int(record.get("object_id") or -1))
        for record in report.records
        if isinstance(record, dict)
    }
    expected: dict[tuple[int, int], tuple[str, dict[str, Any]]] = {}
    for raw_object_id, entry in report.object_lookup.items():
        object_id = int(raw_object_id)
        row = entry if isinstance(entry, dict) else {}
        name = str(row.get("name") or "")
        section_type = v1._expected_type(name)
        key = (int(section_type), object_id) if section_type is not None else None
        if key is not None and key not in existing:
            expected[key] = (name, row)

    setup_start = int((report.setup or {}).get("offset") or 0) + 8
    canonical = _canonical_offsets(data, setup_start, expected)
    recovered: list[dict[str, Any]] = []

    for (section_type, object_id), (name, entry) in expected.items():
        offsets = list(canonical.get((section_type, object_id), ()))
        if not offsets:
            offsets = _fallback_offsets(data, setup_start, section_type, object_id)
        candidates = [
            candidate
            for offset in offsets
            if (candidate := _validate_candidate(data, offset, section_type, object_id)) is not None
        ]
        if not candidates:
            continue
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
        selected.setdefault("recovery", {})["discovery"] = (
            "canonical header index" if int(selected["raw_section_type"]) >> 16 == 0xCCCC else "object-id fallback"
        )
        recovered.append(selected)

    recovered.sort(key=lambda record: int(record["offset"]))
    v1._CACHE[cache_key] = copy.deepcopy(recovered)
    return recovered


# Install optimized discovery beneath the already validated mutation/report API.
v1._scan = _scan

recover_report = v1.recover_report
recover_context = v1.recover_context
clear_recovery_cache = v1.clear_recovery_cache

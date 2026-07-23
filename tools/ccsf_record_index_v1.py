#!/usr/bin/env python3
"""Lightweight CCSF header/index/setup record enumeration.

This parser deliberately does not decode model payloads and does not allocate
per-read trace objects. It is the fast path for texture, animation, Object, Clump,
and other typed-record discovery in the public GUI.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as schema

HEADER_SIZE = 0x3C


def _need(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"{label} at 0x{offset:X} requires {size} bytes; file size is 0x{len(data):X}")


def _u32(data: bytes, offset: int) -> int:
    _need(data, offset, 4, "uint32")
    return struct.unpack_from("<I", data, offset)[0]


def _s16(data: bytes, offset: int) -> int:
    _need(data, offset, 2, "int16")
    return struct.unpack_from("<h", data, offset)[0]


def _cstring(data: bytes, offset: int, size: int) -> str:
    _need(data, offset, size, "fixed string")
    raw = data[offset : offset + size]
    raw = raw.split(b"\0", 1)[0]
    return raw.decode("cp1252", errors="replace")


def generation_name(version: int) -> str:
    if version >= schema.CCS_VERSION_THREE:
        return "Gen3"
    if version >= schema.CCS_VERSION_TWO:
        return "Gen2"
    return "Gen1"


def index_bytes(data: bytes, source: str = "<bytes>") -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    files: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    stream: dict[str, Any] = {}

    _need(data, 0, HEADER_SIZE, "CCSF header")
    raw_header_type = _u32(data, 0)
    header_type = raw_header_type & 0xFFFF
    raw_header_size = _u32(data, 4)
    magic = _u32(data, 8)
    version = _u32(data, 44)
    header = {
        "offset": 0,
        "raw_section_type": raw_header_type,
        "masked_section_type": header_type,
        "type_name": schema.type_name(header_type),
        "raw_size_field": raw_header_size,
        "magic": magic,
        "name": _cstring(data, 12, 0x20),
        "version": version,
        "generation": generation_name(version),
        "unk1": _u32(data, 48),
        "unk2": _u32(data, 52),
        "unk3": _u32(data, 56),
        "header_end_offset": HEADER_SIZE,
    }
    if header_type != schema.SECTION_HEADER:
        errors.append(f"Header section mismatch: 0x{header_type:04X}")
    if magic != schema.CCS_MAGIC:
        errors.append(f"Invalid CCS magic: 0x{magic:08X}")
    if errors:
        return {"version": 1, "source": source, "size": len(data), "header": header, "files": files, "objects": objects, "records": records, "stream": stream, "warnings": warnings, "errors": errors}

    cursor = HEADER_SIZE
    _need(data, cursor, 16, "CCSF index header")
    raw_index_type = _u32(data, cursor)
    index_type = raw_index_type & 0xFFFF
    index_size = _u32(data, cursor + 4)
    file_count = _u32(data, cursor + 8)
    object_count = _u32(data, cursor + 12)
    index_offset = cursor
    cursor += 16
    if index_type != schema.SECTION_INDEX:
        errors.append(f"Index section mismatch at 0x{index_offset:X}: 0x{index_type:04X}")
        return {"version": 1, "source": source, "size": len(data), "header": header, "files": files, "objects": objects, "records": records, "stream": stream, "warnings": warnings, "errors": errors}
    if file_count > 1_000_000 or object_count > 10_000_000:
        raise ValueError(f"implausible CCSF index counts: files={file_count}, objects={object_count}")

    _need(data, cursor, file_count * 0x20 + object_count * 0x20, "CCSF index tables")
    for file_id in range(file_count):
        entry_offset = cursor
        files.append({"id": file_id, "table_index": file_id, "offset": entry_offset, "name": _cstring(data, entry_offset, 0x20), "owned_object_ids": []})
        cursor += 0x20
    for object_id in range(object_count):
        entry_offset = cursor
        file_id = _s16(data, entry_offset + 0x1E)
        row = {
            "id": object_id,
            "table_index": object_id,
            "offset": entry_offset,
            "name": _cstring(data, entry_offset, 0x1E),
            "file_id": file_id,
            "file_name": files[file_id]["name"] if 0 <= file_id < len(files) else "",
            "section_type": None,
            "section_type_name": None,
            "section_offset": None,
            "absolute_offset": None,
        }
        objects.append(row)
        if 0 <= file_id < len(files):
            files[file_id]["owned_object_ids"].append(object_id)
        else:
            warnings.append(f"object {object_id} references missing file ID {file_id}")
        cursor += 0x20

    setup_offset = cursor
    _need(data, cursor, 8, "CCSF setup header")
    raw_setup_type = _u32(data, cursor)
    setup_type = raw_setup_type & 0xFFFF
    setup_size = _u32(data, cursor + 4)
    cursor += 8
    setup = {
        "offset": setup_offset,
        "raw_section_type": raw_setup_type,
        "masked_section_type": setup_type,
        "type_name": schema.type_name(setup_type),
        "raw_size_field": setup_size,
        "index_offset": index_offset,
        "index_raw_size_field": index_size,
    }
    if setup_type != schema.SECTION_SETUP:
        errors.append(f"Setup section mismatch at 0x{setup_offset:X}: 0x{setup_type:04X}")
        return {"version": 1, "source": source, "size": len(data), "header": header, "index": {"offset": index_offset, "raw_size_field": index_size, "file_count": file_count, "object_count": object_count}, "setup": setup, "files": files, "objects": objects, "records": records, "stream": stream, "warnings": warnings, "errors": errors}

    while cursor + 4 <= len(data):
        record_offset = cursor
        raw_type = _u32(data, cursor)
        record_type = raw_type & 0xFFFF
        if record_type == schema.SECTION_STREAM:
            if cursor + 12 <= len(data):
                stream = {
                    "offset": cursor,
                    "raw_section_type": raw_type,
                    "masked_section_type": record_type,
                    "type_name": schema.type_name(record_type),
                    "raw_size_field": _u32(data, cursor + 4),
                    "frame_count": _u32(data, cursor + 8),
                }
            else:
                errors.append("Stream section header is truncated")
            break
        if cursor + 12 > len(data):
            errors.append(f"Setup record header at 0x{cursor:X} is truncated")
            break
        raw_size = _u32(data, cursor + 4)
        object_id = _u32(data, cursor + 8)
        payload_words = int(raw_size) - 1
        payload_size = payload_words * 4
        payload_start = cursor + 12
        payload_end = payload_start + payload_size
        row: dict[str, Any] = {
            "offset": record_offset,
            "raw_section_type": raw_type,
            "masked_section_type": record_type,
            "type_name": schema.type_name(record_type),
            "raw_size_field": raw_size,
            "calculated_payload_size": payload_size,
            "object_id": object_id,
            "object_name": objects[object_id]["name"] if 0 <= object_id < len(objects) else "",
            "owning_file_id": objects[object_id]["file_id"] if 0 <= object_id < len(objects) else None,
            "owning_file_name": objects[object_id]["file_name"] if 0 <= object_id < len(objects) else "",
            "payload_start": payload_start,
            "payload_end": payload_end,
            "parse_status": "indexed_payload",
            "warnings": [],
            "errors": [],
        }
        if payload_words < 0:
            row["errors"].append("negative calculated payload size")
            row["parse_status"] = "size_error"
            records.append(row)
            break
        if payload_end > len(data):
            row["errors"].append(f"payload end 0x{payload_end:X} exceeds file end 0x{len(data):X}")
            row["parse_status"] = "truncated"
            records.append(row)
            break
        if not 0 <= object_id < len(objects):
            row["errors"].append(f"object ID {object_id} outside object table")
        else:
            objects[object_id].update({"section_type": record_type, "section_type_name": schema.type_name(record_type), "section_offset": record_offset - setup_offset, "absolute_offset": record_offset})
        if record_type == schema.SECTION_MATERIAL and payload_size >= 4:
            row["material"] = {"texture_object_id": _u32(data, payload_start)}
        records.append(row)
        cursor = payload_end

    typed_counts: dict[str, int] = {}
    for row in records:
        name = str(row["type_name"])
        typed_counts[name] = typed_counts.get(name, 0) + 1
    return {
        "version": 1,
        "source": source,
        "size": len(data),
        "header": header,
        "index": {"offset": index_offset, "raw_size_field": index_size, "file_count": file_count, "object_count": object_count},
        "setup": setup,
        "files": files,
        "objects": objects,
        "object_index": objects,
        "records": records,
        "stream": stream,
        "summary": {"file_count": len(files), "object_count": len(objects), "record_count": len(records), "typed_record_counts": typed_counts},
        "warnings": warnings,
        "errors": errors,
    }


def index_file(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    return index_bytes(source.read_bytes(), str(source))


def write_index(path: str | Path, output: str | Path) -> Path:
    report = index_file(path)
    target = Path(output).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target

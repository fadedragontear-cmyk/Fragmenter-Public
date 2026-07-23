#!/usr/bin/env python3
"""Decode top-level StudioCCS/CCSF structure without trusting payload types.

This intentionally mirrors the conservative section walking behavior used by
NCDyson/StudioCCS: header -> index -> setup records until stream -> stream
header.  Typed setup payloads are not deeply decoded here; their metadata and
bounded byte ranges are reported so unknown or partially understood records do
not abort inspection of the rest of the file.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# High-level sections from StudioCCS/libCCS/CCSFile.cs.
SECTION_HEADER = 0x0001
SECTION_INDEX = 0x0002
SECTION_SETUP = 0x0003
SECTION_STREAM = 0x0005

# Typed setup records requested for Fragmenter research reports.
SECTION_OBJECT = 0x0100
SECTION_MATERIAL = 0x0200
SECTION_TEXTURE = 0x0300
SECTION_CLUT = 0x0400
SECTION_MODEL = 0x0800
SECTION_CLUMP = 0x0900
SECTION_HITMESH = 0x0B00
SECTION_DUMMYPOS = 0x1300
SECTION_DUMMYPOSROT = 0x1400
SECTION_SHADOW = 0x1800
SECTION_PCM = 0x2200
SECTION_BINARYBLOB = 0x2400

CCS_MAGIC = 0x46534343  # b"CCSF" read as little-endian u32.
CCS_VERSION_TWO = 0x0120
CCS_VERSION_THREE = 0x0125


# StudioCCS/libCCS/CCSModel model type values.  Generation 1 rigid models
# are any model type below CCS_MODEL_DEFORMABLE.
CCS_MODEL_DEFORMABLE = 0x0004
CCS_MODEL_SHADOW = 0x0008
CCS_MODEL_MORPHTARGET = 0x0600
CCS_MODEL_DEFORMABLE_GEN2 = 0x1004
CCS_MODEL_RIGID_GEN2_NO_COLOR = 0x0200
CCS_MODEL_RIGID_GEN2_COLOR = 0x1000
CCS_MODEL_RIGID_GEN2_NO_COLOR2 = 0x1200
CCS_MODEL_MORPHTARGET_GEN2 = 0x0400


def is_rigid_model_type(model_type: int) -> bool:
    return model_type < CCS_MODEL_DEFORMABLE or model_type in {
        CCS_MODEL_RIGID_GEN2_NO_COLOR,
        CCS_MODEL_RIGID_GEN2_COLOR,
        CCS_MODEL_RIGID_GEN2_NO_COLOR2,
    }


def is_deformable_model_type(model_type: int) -> bool:
    return model_type in {CCS_MODEL_DEFORMABLE, CCS_MODEL_DEFORMABLE_GEN2}


def is_shadow_model_type(model_type: int) -> bool:
    return model_type == CCS_MODEL_SHADOW


def is_morph_target_model_type(model_type: int) -> bool:
    return model_type in {CCS_MODEL_MORPHTARGET, CCS_MODEL_MORPHTARGET_GEN2}


def model_type_name(model_type: int) -> str:
    if model_type < CCS_MODEL_DEFORMABLE:
        return "rigid"
    names = {
        CCS_MODEL_DEFORMABLE: "deformable",
        CCS_MODEL_SHADOW: "shadow",
        CCS_MODEL_MORPHTARGET: "morph_target",
        CCS_MODEL_DEFORMABLE_GEN2: "gen2_deformable",
        CCS_MODEL_RIGID_GEN2_NO_COLOR: "gen2_rigid_no_color",
        CCS_MODEL_RIGID_GEN2_COLOR: "gen2_rigid_color",
        CCS_MODEL_RIGID_GEN2_NO_COLOR2: "gen2_rigid_no_color2",
        CCS_MODEL_MORPHTARGET_GEN2: "gen2_morph_target",
    }
    return names.get(model_type, "unsupported_model_type")


def is_supported_model_type(model_type: int) -> bool:
    return model_type_name(model_type) != "unsupported_model_type"

SECTION_NAMES: dict[int, str] = {
    SECTION_HEADER: "Header",
    SECTION_INDEX: "Index",
    SECTION_SETUP: "Setup",
    SECTION_STREAM: "Stream",
    SECTION_OBJECT: "Object",
    SECTION_MATERIAL: "Material",
    SECTION_TEXTURE: "Texture",
    SECTION_CLUT: "CLUT",
    SECTION_MODEL: "Model",
    SECTION_CLUMP: "Clump",
    SECTION_HITMESH: "Hit Mesh",
    SECTION_DUMMYPOS: "Dummy(Position)",
    SECTION_DUMMYPOSROT: "Dummy(Position & Rotation)",
    SECTION_SHADOW: "Shadow",
    SECTION_PCM: "PCM Audio",
    SECTION_BINARYBLOB: "Binary Blob",
}


class DecodeError(Exception):
    """Raised when a bounded read cannot be satisfied."""


def c_string(raw: bytes) -> str:
    nul = raw.find(b"\0")
    if nul >= 0:
        raw = raw[:nul]
    return raw.decode("cp1252", errors="replace")


@dataclass(frozen=True)
class ReadTrace:
    op: str
    offset: int
    size: int
    section_start: int
    section_end: int
    value: Any = None


class BinaryReader:
    """Small bounded BinaryReader with absolute offsets and section context."""

    def __init__(self, data: bytes, *, start: int = 0, end: int | None = None, section_start: int | None = None, section_end: int | None = None):
        self._data = data
        self.start = start
        self.end = len(data) if end is None else end
        self.pos = start
        self.section_start = self.start if section_start is None else section_start
        self.section_end = self.end if section_end is None else section_end
        self.traces: list[ReadTrace] = []
        if not (0 <= self.start <= self.end <= len(data)):
            raise ValueError(f"invalid reader bounds {self.start}:{self.end} for {len(data)} bytes")

    def tell(self) -> int:
        return self.pos

    def remaining(self) -> int:
        return self.end - self.pos

    def _record(self, op: str, offset: int, size: int, value: Any) -> Any:
        self.traces.append(ReadTrace(op, offset, size, self.section_start, self.section_end, value))
        return value

    def _require(self, size: int, op: str) -> int:
        if size < 0:
            raise DecodeError(f"negative read size {size} for {op} at 0x{self.pos:X}")
        offset = self.pos
        if offset + size > self.end:
            raise DecodeError(
                f"{op} at 0x{offset:X} needs {size} byte(s), exceeds active section "
                f"0x{self.section_start:X}:0x{self.section_end:X} / bounds end 0x{self.end:X}"
            )
        self.pos += size
        return offset

    def read_bytes(self, size: int, op: str = "bytes") -> bytes:
        offset = self._require(size, op)
        return self._record(op, offset, size, self._data[offset:offset + size])

    def _unpack(self, fmt: str, size: int, op: str) -> Any:
        offset = self._require(size, op)
        value = struct.unpack(fmt, self._data[offset:offset + size])[0]
        return self._record(op, offset, size, value)

    def u8(self) -> int:
        return self._unpack("<B", 1, "u8")

    def s8(self) -> int:
        return self._unpack("<b", 1, "s8")

    def u16le(self) -> int:
        return self._unpack("<H", 2, "u16le")

    def s16le(self) -> int:
        return self._unpack("<h", 2, "s16le")

    def u32le(self) -> int:
        return self._unpack("<I", 4, "u32le")

    def s32le(self) -> int:
        return self._unpack("<i", 4, "s32le")

    def f32le(self) -> float:
        return self._unpack("<f", 4, "f32le")

    def fixed_string(self, size: int) -> str:
        return c_string(self.read_bytes(size, f"fixed_string[{size}]"))

    def align(self, alignment: int) -> int:
        if alignment <= 0:
            raise ValueError("alignment must be positive")
        new_pos = ((self.pos + alignment - 1) // alignment) * alignment
        skipped = new_pos - self.pos
        self.read_bytes(skipped, f"align[{alignment}]")
        return skipped

    def seek(self, offset: int) -> None:
        if not (self.start <= offset <= self.end):
            raise DecodeError(f"seek to 0x{offset:X} outside bounds 0x{self.start:X}:0x{self.end:X}")
        old = self.pos
        self.pos = offset
        self._record("seek", old, 0, offset)

    def bounded_slice(self, start: int, end: int) -> "BinaryReader":
        if not (self.start <= start <= end <= self.end):
            raise DecodeError(f"slice 0x{start:X}:0x{end:X} outside bounds 0x{self.start:X}:0x{self.end:X}")
        return BinaryReader(self._data, start=start, end=end, section_start=start, section_end=end)


@dataclass
class DecodeReport:
    input: str
    size: int
    header: dict[str, Any] = field(default_factory=dict)
    file_index: list[dict[str, Any]] = field(default_factory=list)
    object_index: list[dict[str, Any]] = field(default_factory=list)
    setup: dict[str, Any] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    stream: dict[str, Any] = field(default_factory=dict)
    object_lookup: dict[int, dict[str, Any]] = field(default_factory=dict)
    queries: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "asset"


def _default_decode_paths(asset_file: Path, out_dir: Path) -> dict[str, Path]:
    """Return canonical CCSF structure report paths for an asset.

    The research workflow expects one JSON report and one readable text report
    directly under workspace/reports, keyed by the sanitized asset stem.
    """
    asset = _safe_name(asset_file.stem)
    return {
        "report": out_dir / f"ccsf_structure_{asset}.json",
        "text_report": out_dir / f"ccsf_structure_{asset}.txt",
    }


ALLOWED_REPORT_STATUSES = {
    "structure_confirmed",
    "typed_record_found",
    "partial",
    "unsupported_model_type",
    "malformed",
    "failed",
}


def _record_status(rec: dict[str, Any]) -> str:
    """Normalize internal parser states to the small honest report vocabulary."""
    if rec.get("errors"):
        return "malformed"
    parse_status = rec.get("parse_status")
    if parse_status == "unsupported_model_type":
        return "unsupported_model_type"
    if parse_status in {"recognized_deformable_unparsed", "recognized_morph_target_unparsed"}:
        return "partial"
    if parse_status in {"truncated", "metadata_error_skipped", "size_error", "decode_error", "model_decode_error"}:
        return "malformed"
    if rec.get("masked_section_type") in SECTION_NAMES:
        return "typed_record_found"
    return "partial"


def _overall_status(report: DecodeReport) -> str:
    if report.errors:
        return "failed"
    if report.header and report.file_index and report.object_index and report.setup and report.stream:
        return "structure_confirmed"
    return "partial"


def _typed_record_counts(report: DecodeReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in report.records:
        key = str(rec.get("type_name") or type_name(int(rec.get("masked_section_type", 0))))
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_model_decode_reports(report: DecodeReport) -> list[dict[str, Any]]:
    """Build one decode report per decoded model submodel/payload."""
    rows: list[dict[str, Any]] = []
    for rec in report.records:
        if rec.get("masked_section_type") != SECTION_MODEL:
            continue
        model = rec.get("model") or {}
        submodels = model.get("submodels") or [None]
        for sub in submodels:
            sub = sub or {}
            parent_id = sub.get("parent_id")
            parent = _object_lookup(report, parent_id) if isinstance(parent_id, int) else None
            mat_tex_id = sub.get("mat_tex_id")
            material = _object_lookup(report, mat_tex_id) if isinstance(mat_tex_id, int) else None
            texture_id = (material or {}).get("material", {}).get("texture_object_id") if material else None
            warnings = list(model.get("warnings") or []) + list(sub.get("warnings") or []) + list(rec.get("warnings") or [])
            rows.append({
                "status": _record_status(rec),
                "model_object_id": rec.get("object_id"),
                "model_object_name": rec.get("object_name"),
                "model_type": model.get("model_type"),
                "model_type_name": model.get("model_type_name"),
                "submodel_index": sub.get("index"),
                "parent_id": parent_id,
                "parent_name": (parent or {}).get("name", ""),
                "material_texture_id": mat_tex_id,
                "texture_id": texture_id,
                "expected_vertex_count": sub.get("vertex_count"),
                "decoded_vertex_count": sub.get("decoded_vertex_count"),
                "triangle_count": sub.get("triangle_count"),
                "payload_start": sub.get("payload_start", rec.get("payload_start")),
                "payload_end": sub.get("payload_end", rec.get("payload_end")),
                "parser_mode": sub.get("parser_mode", model.get("parse_status")),
                "warnings": warnings,
            })
    return rows


def build_summary(report: DecodeReport, model_decode_reports: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [_record_status(rec) for rec in report.records]
    typed_counts = _typed_record_counts(report)
    return {
        "status": _overall_status(report),
        "ccsf_version": report.header.get("version"),
        "ccsf_generation": report.header.get("generation"),
        "file_count": len(report.file_index),
        "object_count": len(report.object_index),
        "typed_record_counts": typed_counts,
        "records_parsed": sum(1 for status in statuses if status in {"typed_record_found", "structure_confirmed"}),
        "records_partial": sum(1 for status in statuses if status in {"partial", "unsupported_model_type"}),
        "records_failed": sum(1 for status in statuses if status in {"malformed", "failed"}),
        "confirmed_models": sum(1 for rec in report.records if rec.get("masked_section_type") == SECTION_MODEL and rec.get("model")),
        "confirmed_submodels": sum(1 for row in model_decode_reports if row.get("submodel_index") is not None),
        "confirmed_geometry": sum(1 for row in model_decode_reports if (row.get("decoded_vertex_count") or 0) > 0 and (row.get("triangle_count") or 0) > 0 and row.get("parser_mode") == "structural_rigid_gen1"),
        "texture_records_found": typed_counts.get(type_name(SECTION_TEXTURE), 0),
        "clut_records_found": typed_counts.get(type_name(SECTION_CLUT), 0),
        "animation_records_found": sum(count for name, count in typed_counts.items() if "Animation" in name),
        "hit_records_found": typed_counts.get(type_name(SECTION_HITMESH), 0),
        "dmy_records_found": typed_counts.get(type_name(SECTION_DUMMYPOS), 0) + typed_counts.get(type_name(SECTION_DUMMYPOSROT), 0),
    }


def report_to_dict(report: DecodeReport) -> dict[str, Any]:
    data = dict(report.__dict__)
    for rec in data["records"]:
        status = _record_status(rec)
        rec["status"] = status
        rec["parse_status"] = status
        if isinstance(rec.get("model"), dict):
            rec["model"]["status"] = status
            rec["model"]["parse_status"] = status
    model_decode_reports = build_model_decode_reports(report)
    data["summary"] = build_summary(report, model_decode_reports)
    data["decode_status"] = data["summary"]["status"]
    data["model_decode_reports"] = model_decode_reports
    data["model_record_count"] = data["summary"]["typed_record_counts"].get(type_name(SECTION_MODEL), 0)
    data["model_record_message"] = "typed model record found" if data["model_record_count"] else "typed model record not found"
    data["objs_written"] = []
    return data


def render_text(report: DecodeReport) -> str:
    data = report_to_dict(report)
    summary = data["summary"]
    lines = [
        "CCSF Structure Decode",
        f"Input: {report.input}",
        f"Size: {report.size} bytes",
        f"Status: {summary['status']}",
        f"CCSF version: {summary.get('ccsf_version')} ({summary.get('ccsf_generation')})",
        f"Files: {summary['file_count']}",
        f"Objects: {summary['object_count']}",
        f"Setup records: {len(report.records)}",
        f"Records parsed: {summary['records_parsed']}",
        f"Records partial: {summary['records_partial']}",
        f"Records failed: {summary['records_failed']}",
        f"Confirmed models: {summary['confirmed_models']}",
        f"Confirmed submodels: {summary['confirmed_submodels']}",
        f"Confirmed geometry: {summary['confirmed_geometry']}",
        f"Texture records found: {summary['texture_records_found']}",
        f"CLUT records found: {summary['clut_records_found']}",
        f"Animation records found: {summary['animation_records_found']}",
        f"HIT records found: {summary['hit_records_found']}",
        f"DMY records found: {summary['dmy_records_found']}",
    ]
    if summary["typed_record_counts"]:
        lines.append("Typed record counts:")
        for name, count in sorted(summary["typed_record_counts"].items()):
            lines.append(f"- {name}: {count}")
    if report.header:
        lines.append(f"Header name: {report.header.get('name', '')}")
    if data["model_decode_reports"]:
        lines.append("Model decode reports:")
        for row in data["model_decode_reports"]:
            lines.append(
                f"- model={row.get('model_object_name') or row.get('model_object_id')} "
                f"type={row.get('model_type_name')} submodel={row.get('submodel_index')} "
                f"parent={row.get('parent_name') or row.get('parent_id')} mat_tex={row.get('material_texture_id')} "
                f"vertices={row.get('decoded_vertex_count')}/{row.get('expected_vertex_count')} "
                f"triangles={row.get('triangle_count')} payload=0x{int(row.get('payload_start') or 0):X}:0x{int(row.get('payload_end') or 0):X} "
                f"mode={row.get('parser_mode')} status={row.get('status')}"
            )
            for warning in row.get("warnings") or []:
                lines.append(f"  warning: {warning}")
    if report.records:
        lines.append("Records:")
        for rec in report.records[:100]:
            lines.append(
                f"- 0x{int(rec.get('offset', 0)):08X} {rec.get('type_name')} "
                f"object={rec.get('object_name') or rec.get('object_id')} status={_record_status(rec)}"
            )
        if len(report.records) > 100:
            lines.append(f"- ... {len(report.records) - 100} more")
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in report.errors)
    return "\n".join(lines)


def write_reports(report: DecodeReport, asset_file: Path, out_dir: Path = Path("workspace/reports"), *, report_path: Path | None = None, text_path: Path | None = None) -> tuple[Path, Path]:
    """Write JSON and text CCSF structure reports and return their paths."""
    defaults = _default_decode_paths(asset_file, out_dir)
    json_path = report_path or defaults["report"]
    readable_path = text_path or defaults["text_report"]
    data = report_to_dict(report)
    data["report_path"] = str(json_path)
    data["text_report_path"] = str(readable_path)
    text = render_text(report)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    readable_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    readable_path.write_text(text + "\n", encoding="utf-8")
    return json_path, readable_path


def type_name(masked: int) -> str:
    return SECTION_NAMES.get(masked, f"Unknown Object Type: 0x{masked:04X}")


def parse_header(br: BinaryReader, report: DecodeReport) -> None:
    off = br.tell()
    raw_type = br.u32le(); masked = raw_type & 0xFFFF
    raw_size = br.u32le(); magic = br.u32le()
    name = br.fixed_string(0x20)
    version = br.u32le(); unk1 = br.u32le(); unk2 = br.u32le(); unk3 = br.u32le()
    if masked != SECTION_HEADER:
        report.errors.append(f"Header section mismatch at 0x{off:X}: 0x{masked:04X}")
    if magic != CCS_MAGIC:
        report.errors.append(f"Invalid CCS magic at 0x{off + 8:X}: 0x{magic:08X}")
    generation = "Gen3" if version >= CCS_VERSION_THREE else "Gen2" if version >= CCS_VERSION_TWO else "Gen1"
    report.header = {"offset": off, "raw_section_type": raw_type, "masked_section_type": masked, "type_name": type_name(masked), "raw_size_field": raw_size, "magic": magic, "name": name, "version": version, "generation": generation, "unk1": unk1, "unk2": unk2, "unk3": unk3, "header_end_offset": br.tell()}


def _file_name(report: DecodeReport, file_id: int) -> str:
    return report.file_index[file_id]["name"] if 0 <= file_id < len(report.file_index) else ""


def _object_lookup(report: DecodeReport, object_id: int) -> dict[str, Any] | None:
    return report.object_lookup.get(object_id)


def find_object_by_name(report: DecodeReport, name: str) -> dict[str, Any] | None:
    """Return the StudioCCS index/setup lookup row for an object name."""
    return next((entry for entry in report.object_lookup.values() if entry.get("name") == name), None)


def objects_in_file(report: DecodeReport, file_id: int) -> list[dict[str, Any]]:
    """Return indexed objects owned by a StudioCCS sub-file ID."""
    return [entry for entry in report.object_lookup.values() if entry.get("file_id") == file_id]


def parse_index(br: BinaryReader, report: DecodeReport) -> None:
    """Parse the real StudioCCS index section layout.

    The index section begins with the section header and table counts, followed
    by compact fixed-width tables:

    * file table: char[0x20] FileName for each file; the file ID is the table
      index, not a stored field.
    * object table: char[0x1E] ObjectName + int16 FileID for each object; the
      object ID is the table index, and typed setup metadata is discovered later
      from setup records rather than stored in the index.
    """
    off = br.tell()
    raw_type = br.u32le()
    masked = raw_type & 0xFFFF
    raw_size = br.u32le()
    counts_off = br.tell()
    file_count = br.u32le()
    object_count = br.u32le()
    if masked != SECTION_INDEX:
        report.errors.append(f"Index section mismatch at 0x{off:X}: 0x{masked:04X}")
        return

    report.header["index_offset"] = off
    report.header["file_index_count"] = file_count
    report.header["object_index_count"] = object_count
    report.setup.update({
        "index_start_offset": off,
        "index_raw_size_field": raw_size,
        "index_counts_offset": counts_off,
    })

    file_table_start = br.tell()
    file_by_id: dict[int, dict[str, Any]] = {}
    for table_index in range(file_count):
        entry_off = br.tell()
        name = br.fixed_string(0x20)
        entry = {"table_index": table_index, "id": table_index, "offset": entry_off, "name": name, "owned_object_ids": []}
        report.file_index.append(entry)
        file_by_id[table_index] = entry
    file_table_end = br.tell()

    object_table_start = br.tell()
    for table_index in range(object_count):
        entry_off = br.tell()
        name = br.fixed_string(0x1E)
        file_id = br.s16le()
        entry = {
            "table_index": table_index,
            "id": table_index,
            "offset": entry_off,
            "name": name,
            "file_id": file_id,
            "file_name": file_by_id.get(file_id, {}).get("name", ""),
            "section_type": None,
            "section_type_name": None,
            "section_offset": None,
            "absolute_offset": None,
        }
        report.object_index.append(entry)
        report.object_lookup[table_index] = entry
        owner = file_by_id.get(file_id)
        if owner is not None:
            owner["owned_object_ids"].append(table_index)
        else:
            report.warnings.append(f"object table index {table_index} references missing file ID {file_id}")
    object_table_end = br.tell()

    actual_next_type = None
    if br.remaining() >= 4:
        actual_next_type = struct.unpack("<I", br._data[br.tell():br.tell() + 4])[0] & 0xFFFF
    report.setup.update({
        "header_end_offset": report.header.get("header_end_offset"),
        "file_table_start": file_table_start,
        "file_table_end": file_table_end,
        "object_table_start": object_table_start,
        "object_table_end": object_table_end,
        "calculated_index_end": off + 16 + (file_count * 0x20) + (object_count * 0x20),
        "actual_next_section_offset": br.tell(),
        "actual_next_section_type": actual_next_type,
    })

def _read_model_header(mbr: BinaryReader, report: DecodeReport, rec: dict[str, Any]) -> dict[str, Any]:
    """Read the StudioCCS CCSModel.Read header inside a setup record payload."""
    model: dict[str, Any] = {"warnings": [], "submodels": []}
    model["vertex_scale"] = mbr.f32le()
    actual_model_type = mbr.s16le()
    model_type = actual_model_type & 0xFFFE
    model.update({
        "actual_model_type": actual_model_type,
        "model_type": model_type,
        "model_type_name": model_type_name(model_type),
        "submodel_count": mbr.s16le(),
        "draw_flags": mbr.s16le(),
        "unk_flags": mbr.s16le(),
        "gif_lookup_related": mbr.s32le(),
        "generation_extra_fields": [],
        "generation": report.header.get("generation"),
    })
    generation = report.header.get("generation")
    if generation in {"Gen2", "Gen3"}:
        for _ in range(2):
            model["generation_extra_fields"].append({"offset": mbr.tell(), "value": mbr.f32le()})
    if not is_supported_model_type(model_type):
        model["parse_status"] = "unsupported_model_type"
        model["warnings"].append(f"unsupported model type 0x{model_type:04X}; payload not structurally guessed")
    return model


VTEX_SCALE = 0.0625 * 0.01
UV_SCALE = 1.0 / 256.0
COLOR_SCALE = 1.0 / 255.0


def _studioccs_alpha(raw_alpha: int) -> int:
    return 0xFF if raw_alpha >= 0x7F else raw_alpha << 1


def _decode_gen1_strip_faces(triangle_flags: list[int], skipped_candidates: list[dict[str, Any]] | None = None) -> list[list[int]]:
    """Reconstruct Gen1 StudioCCS rigid triangle strips from per-vertex flags."""
    faces: list[list[int]] = []
    last_flag = 1
    s_count = 0
    for index, tri_flag in enumerate(triangle_flags):
        if tri_flag == 0:
            if s_count % 2 == 0:
                face = [index, index - 1, index - 2]
            else:
                face = [index - 2, index - 1, index]
            if all(face_index >= 0 for face_index in face):
                faces.append(face)
            elif skipped_candidates is not None:
                skipped_candidates.append({
                    "index": index,
                    "triangle_flag": tri_flag,
                    "s_count": s_count,
                    "candidate_face": face,
                    "reason": "negative_index",
                })
            s_count += 1
            last_flag = tri_flag
        elif last_flag == 0:
            s_count = 0
            last_flag = tri_flag
    return faces


def _parse_rigid_submodels(mbr: BinaryReader, model: dict[str, Any]) -> None:
    count = max(0, int(model.get("submodel_count", 0)))
    vertex_scale = float(model.get("vertex_scale") or 0.0)
    position_scale = vertex_scale / 256.0
    for index in range(count):
        sub: dict[str, Any] = {"index": index, "warnings": []}
        header_offset = mbr.tell()
        if mbr.remaining() < 12:
            sub["warnings"].append("truncated rigid submodel header")
            model["submodels"].append(sub)
            break
        parent_id = mbr.s32le(); mat_tex_id = mbr.s32le(); vertex_count = mbr.s32le()
        payload_start = mbr.tell()
        sub.update({
            "parent_id": parent_id,
            "mat_tex_id": mat_tex_id,
            "vertex_count": vertex_count,
            "header_offset": header_offset,
            "payload_start": payload_start,
            "parser_mode": "structural_rigid_gen1",
            "vertex_scale": vertex_scale,
            "vtex_scale": VTEX_SCALE,
            "position_scale": position_scale,
            "vertices": [],
            "vertex_source_offsets": [],
            "normals": [],
            "normal_source_offsets": [],
            "triangle_flags": [],
            "faces": [],
            "skipped_face_candidates": [],
            "vertex_colors": [],
            "vertex_color_source_offsets": [],
            "uvs": [],
            "uv_source_offsets": [],
            "alignment_evidence": [],
            "has_uv": None,
            "has_color": None,
            "has_normal": True,
        })
        if vertex_count < 0:
            sub["warnings"].append("negative vertex count")
            sub["decoded_vertex_count"] = 0
            sub["triangle_count"] = 0
            sub["payload_end"] = mbr.tell()
            model["submodels"].append(sub)
            continue
        try:
            for _ in range(vertex_count):
                source_offset = mbr.tell()
                raw = [mbr.s16le(), mbr.s16le(), mbr.s16le()]
                position = [(component * VTEX_SCALE) * position_scale for component in raw]
                sub["vertices"].append({"position": position, "raw": raw, "source_offset": source_offset})
                sub["vertex_source_offsets"].append(source_offset)
            if mbr.tell() % 4 == 2:
                alignment_offset = mbr.tell()
                alignment_value = mbr.u16le()
                sub["alignment_evidence"].append({
                    "offset": alignment_offset,
                    "value": alignment_value,
                    "reason": "position_stream_modulo_4_eq_2",
                })
            for _ in range(vertex_count):
                source_offset = mbr.tell()
                record = mbr.read_bytes(4, "rigid_normal_triangle_record")
                normal = [
                    -record[0] * (1.0 / 64.0),
                    record[1] * (1.0 / 64.0),
                    record[2] * (1.0 / 64.0),
                ]
                triangle_flag = record[3]
                sub["normals"].append({
                    "normal": normal,
                    "triangle_flag": triangle_flag,
                    "source_offset": source_offset,
                    "raw": list(record),
                })
                sub["normal_source_offsets"].append(source_offset)
                sub["triangle_flags"].append(triangle_flag)
            sub["faces"] = _decode_gen1_strip_faces(sub["triangle_flags"], sub["skipped_face_candidates"])
            if model.get("generation") == "Gen1":
                for _ in range(vertex_count):
                    source_offset = mbr.tell()
                    record = mbr.read_bytes(4, "rigid_vertex_color_rgba")
                    raw_rgba = list(record)
                    normalized_alpha = _studioccs_alpha(raw_rgba[3])
                    color = [
                        raw_rgba[0] * COLOR_SCALE,
                        raw_rgba[1] * COLOR_SCALE,
                        raw_rgba[2] * COLOR_SCALE,
                        normalized_alpha * COLOR_SCALE,
                    ]
                    sub["vertex_colors"].append({
                        "color": color,
                        "source_offset": source_offset,
                        "raw": raw_rgba,
                        "normalized_alpha_byte": normalized_alpha,
                    })
                    sub["vertex_color_source_offsets"].append(source_offset)
                sub["has_color"] = True
                if not is_morph_target_model_type(int(model.get("model_type", 0))):
                    for _ in range(vertex_count):
                        source_offset = mbr.tell()
                        raw = [mbr.s16le(), mbr.s16le()]
                        uv = [raw[0] * UV_SCALE, raw[1] * UV_SCALE]
                        sub["uvs"].append({"uv": uv, "raw": raw, "source_offset": source_offset})
                        sub["uv_source_offsets"].append(source_offset)
                    sub["has_uv"] = True
            sub["decoded_vertex_count"] = len(sub["vertices"])
            sub["triangle_count"] = len(sub["faces"])
            sub["payload_end"] = mbr.tell()
        except DecodeError as exc:
            sub["warnings"].append(str(exc))
            sub["decoded_vertex_count"] = len(sub["vertices"])
            sub["triangle_count"] = len(sub["faces"])
            sub["payload_end"] = mbr.tell()
        model["submodels"].append(sub)


def _parse_shadow_submodels(mbr: BinaryReader, model: dict[str, Any]) -> None:
    count = max(0, int(model.get("submodel_count", 0)))
    vertex_scale = float(model.get("vertex_scale") or 0.0)
    position_scale = vertex_scale / 256.0
    for index in range(count):
        sub: dict[str, Any] = {"index": index, "warnings": []}
        header_offset = mbr.tell()
        if mbr.remaining() < 8:
            sub.update({"header_offset": header_offset, "payload_start": mbr.tell(), "payload_end": mbr.tell()})
            sub["warnings"].append("truncated shadow submodel header")
            model["submodels"].append(sub)
            break
        vertex_count = mbr.s32le()
        tri_vertex_count = mbr.s32le()
        triangle_count = tri_vertex_count // 3 if tri_vertex_count >= 0 else 0
        payload_start = mbr.tell()
        vertex_bytes = vertex_count * 6 if vertex_count >= 0 else 0
        position_end = payload_start + vertex_bytes
        alignment_bytes = 2 if position_end % 4 == 2 else 0
        face_bytes = triangle_count * 12 if tri_vertex_count >= 0 and tri_vertex_count % 3 == 0 else 0
        expected_payload_size = vertex_bytes + alignment_bytes + face_bytes
        sub.update({
            "vertex_count": vertex_count,
            "triangle_vertex_count": tri_vertex_count,
            "triangle_count": triangle_count,
            "header_offset": header_offset,
            "payload_start": payload_start,
            "parser_mode": "shadow_studioccs",
            "vertex_scale": vertex_scale,
            "vtex_scale": VTEX_SCALE,
            "position_scale": position_scale,
            "vertices": [],
            "vertex_source_offsets": [],
            "faces": [],
            "face_source_offsets": [],
            "alignment_evidence": [],
            "expected_payload_size": expected_payload_size,
            "expected_payload_end": payload_start + expected_payload_size,
            "payload_bounds_valid": payload_start + expected_payload_size <= mbr.end,
            "has_uv": False,
            "has_color": False,
            "has_normal": False,
        })
        if vertex_count < 0:
            sub["warnings"].append("negative shadow vertex count")
        if tri_vertex_count < 0:
            sub["warnings"].append("negative shadow triangle vertex count")
        elif tri_vertex_count % 3:
            sub["warnings"].append("shadow triangle vertex count is not divisible by 3")
        if not sub["payload_bounds_valid"]:
            sub["warnings"].append(
                f"shadow payload bounds exceed section: expected end 0x{sub['expected_payload_end']:X}, section end 0x{mbr.end:X}"
            )
        try:
            for _ in range(max(0, vertex_count)):
                source_offset = mbr.tell()
                raw = [mbr.s16le(), mbr.s16le(), mbr.s16le()]
                position = [(component * VTEX_SCALE) * position_scale for component in raw]
                sub["vertices"].append({"position": position, "raw": raw, "source_offset": source_offset})
                sub["vertex_source_offsets"].append(source_offset)
            if mbr.tell() % 4 == 2:
                alignment_offset = mbr.tell()
                alignment_value = mbr.s16le()
                sub["alignment_evidence"].append({
                    "offset": alignment_offset,
                    "value": alignment_value,
                    "reason": "shadow_position_stream_modulo_4_eq_2",
                })
            if tri_vertex_count >= 0 and tri_vertex_count % 3 == 0:
                for _ in range(triangle_count):
                    source_offset = mbr.tell()
                    face = [mbr.s32le(), mbr.s32le(), mbr.s32le()]
                    sub["faces"].append(face)
                    sub["face_source_offsets"].append(source_offset)
        except DecodeError as exc:
            sub["warnings"].append(str(exc))
        sub["decoded_vertex_count"] = len(sub["vertices"])
        sub["decoded_triangle_count"] = len(sub["faces"])
        sub["payload_end"] = mbr.tell()
        if sub["decoded_triangle_count"] != sub["triangle_count"]:
            sub["warnings"].append("decoded shadow triangle count does not match header triangle count")
        model["submodels"].append(sub)


def parse_model_payload(payload_reader: BinaryReader, report: DecodeReport, rec: dict[str, Any]) -> dict[str, Any]:
    model = _read_model_header(payload_reader, report, rec)
    model_type = model["model_type"]
    if model.get("parse_status") == "unsupported_model_type":
        return model
    if is_rigid_model_type(model_type):
        _parse_rigid_submodels(payload_reader, model)
        model["parse_status"] = "parsed_rigid_gen1"
    elif is_shadow_model_type(model_type):
        _parse_shadow_submodels(payload_reader, model)
        model["parse_status"] = "parsed_shadow"
    elif is_deformable_model_type(model_type):
        model["parse_status"] = "recognized_deformable_unparsed"
    elif is_morph_target_model_type(model_type):
        model["parse_status"] = "recognized_morph_target_unparsed"
    return model

def parse_setup_and_stream(br: BinaryReader, report: DecodeReport) -> None:
    setup_off = br.tell(); raw_type = br.u32le(); masked = raw_type & 0xFFFF; raw_size = br.u32le()
    report.setup.update({"offset": setup_off, "raw_section_type": raw_type, "masked_section_type": masked, "type_name": type_name(masked), "raw_size_field": raw_size})
    if masked != SECTION_SETUP:
        report.errors.append(f"Setup section mismatch at 0x{setup_off:X}: 0x{masked:04X}")
        return
    while br.remaining() >= 4:
        rec_off = br.tell(); rec_raw_type = br.u32le(); rec_masked = rec_raw_type & 0xFFFF
        if rec_masked == SECTION_STREAM:
            br.seek(rec_off)
            break
        rec: dict[str, Any] = {"offset": rec_off, "raw_section_type": rec_raw_type, "masked_section_type": rec_masked, "type_name": type_name(rec_masked), "warnings": [], "errors": []}
        try:
            rec_raw_size = br.u32le(); obj_id = br.u32le(); payload_words = rec_raw_size - 1; payload_size = payload_words * 4; payload_start = br.tell(); payload_end = payload_start + payload_size
            rec.update({"raw_size_field": rec_raw_size, "calculated_payload_size": payload_size, "object_id": obj_id, "object_name": "", "owning_file_id": None, "owning_file_name": "", "payload_start": payload_start, "payload_end": payload_end, "parse_status": "skipped"})
            obj = None
            lookup = None
            if 0 <= obj_id < len(report.object_index):
                obj = report.object_index[obj_id]
                lookup = report.object_lookup[obj_id]
                rec["object_name"] = obj["name"]; rec["owning_file_id"] = obj["file_id"]; rec["owning_file_name"] = obj["file_name"]
                lookup["section_type"] = rec_masked
                lookup["section_type_name"] = type_name(rec_masked)
                lookup["section_offset"] = rec_off - setup_off
                lookup["absolute_offset"] = rec_off
                lookup["typed_setup_record"] = rec
            else:
                rec["errors"].append(f"object ID {obj_id} outside object table index range 0..{len(report.object_index) - 1}")
                rec["parse_status"] = "metadata_error_skipped"
            if rec_masked == SECTION_MATERIAL and payload_size >= 4 and payload_end <= br.end:
                texture_object_id = struct.unpack("<I", br._data[payload_start:payload_start + 4])[0]
                rec["material"] = {"texture_object_id": texture_object_id, "texture_object": report.object_lookup.get(texture_object_id)}
                if lookup is not None:
                    lookup["material"] = rec["material"]
            if rec_masked == SECTION_MODEL and payload_size >= 16 and payload_end <= br.end:
                try:
                    payload_reader = br.bounded_slice(payload_start, payload_end)
                    rec["model"] = parse_model_payload(payload_reader, report, rec)
                    rec["parse_status"] = rec["model"].get("parse_status", "model_parsed")
                    if lookup is not None:
                        lookup["model"] = rec["model"]
                except DecodeError as exc:
                    rec["errors"].append(str(exc))
                    rec["parse_status"] = "model_decode_error"
            if rec_masked not in SECTION_NAMES:
                rec["warnings"].append("unknown setup record type; payload preserved by range and skipped")
                rec["parse_status"] = "unknown_skipped"
            elif rec.get("parse_status") == "skipped":
                rec["warnings"].append("typed setup decoder not implemented; payload preserved by range and skipped")
                rec["parse_status"] = "typed_payload_preserved"
            if payload_size < 0:
                rec["errors"].append("negative calculated payload size")
                rec["parse_status"] = "size_error"
                break
            if payload_end > br.end:
                rec["errors"].append(f"payload end 0x{payload_end:X} exceeds file end 0x{br.end:X}")
                rec["parse_status"] = "truncated"
                br.seek(br.end)
            else:
                br.seek(payload_end)
        except DecodeError as exc:
            rec.setdefault("errors", []).append(str(exc)); rec["parse_status"] = "decode_error"
        report.records.append(rec)
        if rec.get("parse_status") in {"size_error", "decode_error"}:
            break
    if br.remaining() >= 12:
        stream_off = br.tell(); stream_raw = br.u32le(); stream_masked = stream_raw & 0xFFFF; stream_size = br.u32le(); frame_count = br.u32le()
        report.stream = {"offset": stream_off, "raw_section_type": stream_raw, "masked_section_type": stream_masked, "type_name": type_name(stream_masked), "raw_size_field": stream_size, "frame_count": frame_count}
        if stream_masked != SECTION_STREAM:
            report.errors.append(f"Stream section mismatch at 0x{stream_off:X}: 0x{stream_masked:04X}")
    else:
        report.errors.append("Stream section header not present or truncated")


def populate_queries(report: DecodeReport) -> None:
    mdl = find_object_by_name(report, "MDL_caurbody1")
    mat_entries = [
        {"object_id": object_id, **entry}
        for object_id, entry in report.object_lookup.items()
        if str(entry.get("name", "")).startswith("MAT_")
    ]
    report.queries = {
        "MDL_caurbody1": mdl,
        "mat_object_ids": {entry["name"]: entry["object_id"] for entry in mat_entries},
        "materials": {entry["name"]: entry.get("material", {}) for entry in mat_entries},
        "object_file_ownership": {entry["name"]: entry["file_name"] for entry in report.object_lookup.values() if str(entry.get("name", "")).startswith(("OBJ_", "MDL_"))},
    }


def decode(path: Path) -> DecodeReport:
    data = path.read_bytes(); report = DecodeReport(input=str(path), size=len(data)); br = BinaryReader(data)
    try:
        parse_header(br, report)
        if not report.errors:
            parse_index(br, report)
            parse_setup_and_stream(br, report)
            populate_queries(report)
    except DecodeError as exc:
        report.errors.append(str(exc))
    return report



def build_aura_diagnostic_summary(path: Path) -> dict[str, Any]:
    """Decode the real aur1body fixture and return compact integration diagnostics."""
    report = decode(path)
    data = report_to_dict(report)
    mdl = find_object_by_name(report, "MDL_caurbody1")
    decoded_vertices = 0
    decoded_faces = 0
    if mdl is not None and isinstance(mdl.get("model"), dict):
        for sub in mdl["model"].get("submodels", []) or []:
            if isinstance(sub, dict):
                decoded_vertices += int(sub.get("decoded_vertex_count") or 0)
                decoded_faces += len(sub.get("faces") or [])
    return {
        "path": str(path),
        "files": data["summary"]["file_count"],
        "objects": data["summary"]["object_count"],
        "setup_records": len(report.records),
        "mdl_caurbody1_found": mdl is not None,
        "decoded_vertices": decoded_vertices,
        "decoded_faces": decoded_faces,
        "reference_vertices": 872,
        "reference_faces": 454,
        "vertices_match_reference": decoded_vertices == 872,
        "faces_match_reference": decoded_faces == 454,
    }


def render_aura_diagnostic(summary: dict[str, Any] | None, fixture_path: Path) -> str:
    lines = ["Aura real-file diagnostics"]
    if summary is None:
        lines.append(f"Status: skipped (fixture path missing: {fixture_path})")
        return "\n".join(lines)
    lines.extend([
        f"Status: ran ({summary['path']})",
        f"Files: {summary['files']}",
        f"Objects: {summary['objects']}",
        f"Setup records: {summary['setup_records']}",
        f"MDL_caurbody1 found: {summary['mdl_caurbody1_found']}",
        f"Decoded vertices: {summary['decoded_vertices']}",
        f"Decoded faces: {summary['decoded_faces']}",
        "Known reference: 872 vertices / 454 faces "
        f"(vertices match: {summary['vertices_match_reference']}; faces match: {summary['faces_match_reference']})",
    ])
    return "\n".join(lines)


def run_default_aura_diagnostic(root: Path | None = None) -> str:
    base = root if root is not None else Path.cwd()
    fixture = base / "workspace" / "extracted_ccs" / "aura" / "aur1body.tmp"
    return render_aura_diagnostic(build_aura_diagnostic_summary(fixture) if fixture.is_file() else None, fixture)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse CCS Structure records and report typed model metadata.")
    parser.add_argument("input", type=Path, help="Input .ccs/.ccsf file")
    parser.add_argument("--out-dir", default="workspace/reports", help="Directory for structure decode reports")
    parser.add_argument("--report", help="Optional JSON structure decode report path")
    parser.add_argument("--text-out", help="Optional readable structure decode report path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--real-fixture-diagnostics", action="store_true", help="Print aur1body real fixture diagnostics or an explicit skipped message")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = decode(args.input)
    report_path = Path(args.report) if args.report else None
    text_path = Path(args.text_out) if args.text_out else None
    written_report_path, written_text_path = write_reports(
        report,
        args.input,
        Path(args.out_dir),
        report_path=report_path,
        text_path=text_path,
    )
    data = report_to_dict(report)
    data["report_path"] = str(written_report_path)
    data["text_report_path"] = str(written_text_path)
    text = render_text(report)
    print(text if args.text_out or args.report else json.dumps(data, indent=2 if args.pretty else None, ensure_ascii=False))
    if args.real_fixture_diagnostics:
        print(run_default_aura_diagnostic(Path.cwd()))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

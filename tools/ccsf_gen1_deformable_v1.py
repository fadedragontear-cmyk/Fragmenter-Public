#!/usr/bin/env python3
"""Primary-source-backed Gen1 CCSF deformable model decoding.

Implements the Gen1 deformable branches documented in NCDyson/StudioCCS
CCSModel.ReadDeform_RigidSubModel and ReadDeform_DeformSubModel. This module
augments Fragmenter's conservative structure report without changing game data.
"""
from __future__ import annotations

import copy
import struct
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as base

WEIGHT_SCALE = 1.0 / 256.0


class DeformableDecodeError(ValueError):
    pass


def _need(data: bytes, offset: int, size: int, end: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > end or offset + size > len(data):
        raise DeformableDecodeError(
            f"{label} at 0x{offset:X} needs {size} byte(s), "
            f"outside payload end 0x{end:X}"
        )


def _i16(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 2, end, "int16")
    return struct.unpack_from("<h", data, offset)[0]


def _u16(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 2, end, "uint16")
    return struct.unpack_from("<H", data, offset)[0]


def _i32(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 4, end, "int32")
    return struct.unpack_from("<i", data, offset)[0]


def _position(data: bytes, offset: int, end: int, vertex_scale: float) -> tuple[list[float], list[int]]:
    _need(data, offset, 6, end, "Vec3Half")
    raw = [_i16(data, offset + index * 2, end) for index in range(3)]
    scale = (float(vertex_scale) / 256.0) * base.VTEX_SCALE
    return [component * scale for component in raw], raw


def _normal_and_flag(data: bytes, offset: int, end: int) -> tuple[list[float], int, list[int]]:
    _need(data, offset, 4, end, "normal/triangle record")
    record = data[offset : offset + 4]
    normal = [
        -record[0] * (1.0 / 64.0),
        record[1] * (1.0 / 64.0),
        record[2] * (1.0 / 64.0),
    ]
    return normal, int(record[3]), list(record)


def _uv(data: bytes, offset: int, end: int) -> tuple[list[float], list[int]]:
    _need(data, offset, 4, end, "UV")
    raw = [_i16(data, offset, end), _i16(data, offset + 2, end)]
    return [raw[0] * base.UV_SCALE, raw[1] * base.UV_SCALE], raw


def _faces(flags: list[int]) -> list[list[int]]:
    return base._decode_gen1_strip_faces(flags)


def _parse_single_weight_submodel(
    data: bytes,
    cursor: int,
    end: int,
    *,
    index: int,
    vertex_scale: float,
) -> tuple[dict[str, Any], int]:
    _need(data, cursor, 16, end, "deform-rigid submodel header")
    mat_tex_id = _i32(data, cursor, end)
    vertex_count = _i32(data, cursor + 4, end)
    unknown = _i32(data, cursor + 8, end)
    parent_id = _i32(data, cursor + 12, end)
    header_offset = cursor
    cursor += 16
    if vertex_count < 0 or vertex_count > 10_000_000:
        raise DeformableDecodeError(f"invalid deform-rigid vertex count: {vertex_count}")

    position_start = cursor
    vertices: list[dict[str, Any]] = []
    for vertex_index in range(vertex_count):
        source_offset = cursor
        position, raw = _position(data, cursor, end, vertex_scale)
        cursor += 6
        vertices.append(
            {
                "index": vertex_index,
                "position": position,
                "position2": [0.0, 0.0, 0.0],
                "raw": raw,
                "source_offset": source_offset,
                "bone_ids": [parent_id, 0],
                "weights": [1.0, 0.0],
            }
        )
    alignment_evidence: list[dict[str, Any]] = []
    if cursor % 4 == 2:
        _need(data, cursor, 2, end, "deform-rigid alignment")
        alignment_evidence.append({"offset": cursor, "value": _i16(data, cursor, end)})
        cursor += 2

    normal_start = cursor
    normals: list[dict[str, Any]] = []
    flags: list[int] = []
    for vertex_index in range(vertex_count):
        source_offset = cursor
        normal, flag, raw = _normal_and_flag(data, cursor, end)
        cursor += 4
        normals.append(
            {
                "index": vertex_index,
                "normal": normal,
                "triangle_flag": flag,
                "raw": raw,
                "source_offset": source_offset,
            }
        )
        flags.append(flag)

    uv_start = cursor
    uvs: list[dict[str, Any]] = []
    for vertex_index in range(vertex_count):
        source_offset = cursor
        value, raw = _uv(data, cursor, end)
        cursor += 4
        uvs.append({"index": vertex_index, "uv": value, "raw": raw, "source_offset": source_offset})

    faces = _faces(flags)
    return (
        {
            "index": index,
            "parser_mode": "studioccs_gen1_deform_rigid",
            "header_offset": header_offset,
            "payload_start": position_start,
            "payload_end": cursor,
            "mat_tex_id": mat_tex_id,
            "vertex_count": vertex_count,
            "decoded_vertex_count": len(vertices),
            "triangle_count": len(faces),
            "unknown_header_value": unknown,
            "parent_id": parent_id,
            "parent_id_kind": "clump_local_node_index",
            "vertices": vertices,
            "normals": normals,
            "triangle_flags": flags,
            "faces": faces,
            "uvs": uvs,
            "has_uv": True,
            "has_color": False,
            "has_normal": True,
            "alignment_evidence": alignment_evidence,
            "stream_offsets": {
                "positions": position_start,
                "normals_and_flags": normal_start,
                "uvs": uv_start,
            },
            "warnings": [],
        },
        cursor,
    )


def _parse_weighted_submodel(
    data: bytes,
    cursor: int,
    end: int,
    *,
    index: int,
    vertex_scale: float,
) -> tuple[dict[str, Any], int]:
    _need(data, cursor, 12, end, "deform-weighted submodel header")
    mat_tex_id = _i32(data, cursor, end)
    vertex_count = _i32(data, cursor + 4, end)
    weighted_count = _i32(data, cursor + 8, end)
    header_offset = cursor
    cursor += 12
    if vertex_count < 0 or vertex_count > 10_000_000:
        raise DeformableDecodeError(f"invalid deform-weighted vertex count: {vertex_count}")
    if weighted_count < 0 or weighted_count > 20_000_000:
        raise DeformableDecodeError(f"invalid deform weighted record count: {weighted_count}")

    vertex_base = cursor
    triangle_base = vertex_base + weighted_count * 8
    uv_base = triangle_base + weighted_count * 4
    payload_end = uv_base + vertex_count * 4
    _need(data, vertex_base, payload_end - vertex_base, end, "deform-weighted streams")

    vertices: list[dict[str, Any]] = []
    normals: list[dict[str, Any]] = []
    uvs: list[dict[str, Any]] = []
    flags: list[int] = []
    weighted_index = 0

    for vertex_index in range(vertex_count):
        source_index = weighted_index
        vertex_offset = vertex_base + source_index * 8
        triangle_offset = triangle_base + source_index * 4
        uv_offset = uv_base + vertex_index * 4

        position1, raw1 = _position(data, vertex_offset, end, vertex_scale)
        params1 = _u16(data, vertex_offset + 6, end)
        bone1 = params1 >> 10
        weight1 = (params1 & 0x1FF) * WEIGHT_SCALE
        dual_weight = ((params1 >> 9) & 0x1) == 0

        position2 = [0.0, 0.0, 0.0]
        raw2 = [0, 0, 0]
        params2 = 0
        bone2 = 0
        weight2 = 0.0
        source_offsets = [vertex_offset]

        if dual_weight:
            weighted_index += 1
            second_offset = vertex_base + weighted_index * 8
            position2, raw2 = _position(data, second_offset, end, vertex_scale)
            params2 = _u16(data, second_offset + 6, end)
            bone2 = params2 >> 10
            weight2 = (params2 & 0x1FF) * WEIGHT_SCALE
            source_offsets.append(second_offset)

        normal, flag, normal_raw = _normal_and_flag(data, triangle_offset, end)
        uv_value, uv_raw = _uv(data, uv_offset, end)
        flags.append(flag)
        vertices.append(
            {
                "index": vertex_index,
                "position": position1,
                "position2": position2,
                "raw": raw1,
                "raw2": raw2,
                "source_offsets": source_offsets,
                "vertex_params": [params1, params2],
                "bone_ids": [bone1, bone2],
                "bone_id_kind": "clump_local_node_index",
                "weights": [weight1, weight2],
                "dual_weight": dual_weight,
            }
        )
        normals.append(
            {
                "index": vertex_index,
                "normal": normal,
                "triangle_flag": flag,
                "raw": normal_raw,
                "source_offset": triangle_offset,
            }
        )
        uvs.append({"index": vertex_index, "uv": uv_value, "raw": uv_raw, "source_offset": uv_offset})
        weighted_index += 1

    faces = _faces(flags)
    warnings: list[str] = []
    if weighted_index != weighted_count:
        warnings.append(
            f"weighted source record count mismatch: header={weighted_count}, consumed={weighted_index}"
        )
    return (
        {
            "index": index,
            "parser_mode": "studioccs_gen1_deform_weighted",
            "header_offset": header_offset,
            "payload_start": vertex_base,
            "payload_end": payload_end,
            "mat_tex_id": mat_tex_id,
            "vertex_count": vertex_count,
            "decoded_vertex_count": len(vertices),
            "triangle_count": len(faces),
            "weighted_record_count": weighted_count,
            "weighted_records_consumed": weighted_index,
            "parent_id": None,
            "vertices": vertices,
            "normals": normals,
            "triangle_flags": flags,
            "faces": faces,
            "uvs": uvs,
            "has_uv": True,
            "has_color": False,
            "has_normal": True,
            "stream_offsets": {
                "weighted_positions": vertex_base,
                "normals_and_flags": triangle_base,
                "uvs": uv_base,
            },
            "warnings": warnings,
        },
        payload_end,
    )


def parse_gen1_deformable_model(
    data: bytes,
    record: dict[str, Any],
    model_header: dict[str, Any],
) -> dict[str, Any]:
    if str(model_header.get("generation") or "") != "Gen1":
        raise DeformableDecodeError("Gen1 deformable parser cannot decode non-Gen1 model")
    if int(model_header.get("model_type") or -1) != base.CCS_MODEL_DEFORMABLE:
        raise DeformableDecodeError("record is not a Gen1 deformable model")

    model = copy.deepcopy(model_header)
    model["submodels"] = []
    count = max(0, int(model.get("submodel_count") or 0))
    vertex_scale = float(model.get("vertex_scale") or 0.0)
    cursor = int(record.get("payload_start") or 0) + 16
    end = int(record.get("payload_end") or 0)
    warnings = list(model.get("warnings") or [])

    if count == 0:
        model.update({"parse_status": "parsed_deformable_gen1", "warnings": warnings})
        return model

    for index in range(max(0, count - 1)):
        submodel, cursor = _parse_single_weight_submodel(
            data,
            cursor,
            end,
            index=index,
            vertex_scale=vertex_scale,
        )
        model["submodels"].append(submodel)

    weighted, cursor = _parse_weighted_submodel(
        data,
        cursor,
        end,
        index=count - 1,
        vertex_scale=vertex_scale,
    )
    model["submodels"].append(weighted)
    if cursor < end:
        warnings.append(f"{end - cursor} unconsumed byte(s) remain in deformable model payload")
    elif cursor > end:
        warnings.append(f"deformable parser exceeded payload end by {cursor - end} byte(s)")
    model.update(
        {
            "parse_status": "parsed_deformable_gen1",
            "parser_mode": "studioccs_gen1_deformable",
            "warnings": warnings,
            "decoded_vertex_count": sum(int(row.get("decoded_vertex_count") or 0) for row in model["submodels"]),
            "triangle_count": sum(int(row.get("triangle_count") or 0) for row in model["submodels"]),
        }
    )
    return model


def decode_with_gen1_deformables(path: str | Path):
    source = Path(path).expanduser()
    data = source.read_bytes()
    report = base.decode(source)
    if str(report.header.get("generation") or "") != "Gen1":
        return report

    for record in report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_MODEL:
            continue
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if not model or int(model.get("model_type") or -1) != base.CCS_MODEL_DEFORMABLE:
            continue
        try:
            parsed = parse_gen1_deformable_model(data, record, model)
            record["model"] = parsed
            record["parse_status"] = parsed["parse_status"]
            lookup = report.object_lookup.get(int(record.get("object_id") or -1))
            if isinstance(lookup, dict):
                lookup["model"] = parsed
        except Exception as exc:
            record.setdefault("errors", []).append(f"Gen1 deformable decode failed: {type(exc).__name__}: {exc}")
            record["parse_status"] = "deformable_decode_error"
    return report


def deformable_summary(path: str | Path) -> dict[str, Any]:
    report = decode_with_gen1_deformables(path)
    rows = []
    for record in report.records:
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if not model or int(model.get("model_type") or -1) != base.CCS_MODEL_DEFORMABLE:
            continue
        rows.append(
            {
                "object_id": record.get("object_id"),
                "object_name": record.get("object_name"),
                "parse_status": model.get("parse_status"),
                "submodels": len(model.get("submodels") or []),
                "vertices": sum(int(row.get("decoded_vertex_count") or 0) for row in model.get("submodels") or []),
                "triangles": sum(int(row.get("triangle_count") or 0) for row in model.get("submodels") or []),
                "warnings": list(model.get("warnings") or []),
                "errors": list(record.get("errors") or []),
            }
        )
    return {"source": str(path), "generation": report.header.get("generation"), "models": rows}

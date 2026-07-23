#!/usr/bin/env python3
"""Gen1 CCSF animation track evaluation and clump pose matrices.

The binary layout follows StudioCCS CCSAnime, ObjectController, ControllerTracks,
CCSExt, CCSObject and CCSClump. The primary release use is applying a real first
frame pose to character/deformable geometry; no transform is invented when a
controller or clump relationship is absent.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as base
from ccsf_gen1_deformable_v1 import decode_with_gen1_deformables
from ccsf_scene_v1 import parse_clump_record, parse_object_record

SECTION_ANIMATION = 0x0700
SECTION_EXTERNAL = 0x0A00
ANIME_FRAME = 0xFF01
ANIME_OBJECT_CONTROLLER = 0x0102
PLAY_ONCE = -1
PLAY_REPEAT = -2
TRACK_NONE = 0
TRACK_FIXED = 1
TRACK_ANIMATED = 2

CCS_GLOBAL_SCALE = 0.0625 * 0.1
POSITION_SCALE = 1.6 * CCS_GLOBAL_SCALE


class PoseDecodeError(ValueError):
    pass


def _need(data: bytes, offset: int, size: int, end: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > end or offset + size > len(data):
        raise PoseDecodeError(f"{label} at 0x{offset:X} exceeds 0x{end:X}")


def _i32(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 4, end, "int32")
    return struct.unpack_from("<i", data, offset)[0]


def _u32(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 4, end, "uint32")
    return struct.unpack_from("<I", data, offset)[0]


def _f32(data: bytes, offset: int, end: int) -> float:
    _need(data, offset, 4, end, "float32")
    return struct.unpack_from("<f", data, offset)[0]


def _track_mode(params: int, track_id: int) -> int:
    return (int(params) >> (3 * int(track_id))) & 0x7


def _position_value(data: bytes, offset: int, end: int) -> tuple[list[float], int]:
    _need(data, offset, 12, end, "position track value")
    values = [_f32(data, offset + index * 4, end) * POSITION_SCALE for index in range(3)]
    return values, offset + 12


def _rotation_value(data: bytes, offset: int, end: int) -> tuple[list[float], int]:
    _need(data, offset, 12, end, "rotation track value")
    x = math.radians(_f32(data, offset, end))
    y = math.radians(_f32(data, offset + 4, end))
    z = math.radians(_f32(data, offset + 8, end))
    return [z, -y, x], offset + 12


def _scale_value(data: bytes, offset: int, end: int) -> tuple[list[float], int]:
    _need(data, offset, 12, end, "scale track value")
    return [_f32(data, offset + index * 4, end) for index in range(3)], offset + 12


def _float_value(data: bytes, offset: int, end: int) -> tuple[float, int]:
    return _f32(data, offset, end), offset + 4


def _parse_track(
    data: bytes,
    cursor: int,
    end: int,
    *,
    mode: int,
    name: str,
    reader,
    default: Any,
) -> tuple[dict[str, Any], int]:
    track: dict[str, Any] = {"name": name, "mode": mode, "keys": [], "default": default}
    if mode == TRACK_NONE:
        track["status"] = "none"
        return track, cursor
    if mode == TRACK_FIXED:
        value, cursor = reader(data, cursor, end)
        track.update({"status": "fixed", "fixed": value})
        return track, cursor
    if mode != TRACK_ANIMATED:
        raise PoseDecodeError(f"unsupported {name} track mode {mode}")

    key_count = _i32(data, cursor, end)
    cursor += 4
    if key_count < 0 or key_count > 1_000_000:
        raise PoseDecodeError(f"invalid {name} key count: {key_count}")
    keys: list[dict[str, Any]] = []
    for _ in range(key_count):
        frame = _i32(data, cursor, end)
        cursor += 4
        value, cursor = reader(data, cursor, end)
        if keys and int(keys[-1]["frame"]) == frame:
            keys.pop()
        keys.append({"frame": frame, "value": value})
    track.update({"status": "animated", "keys": keys, "key_count": len(keys)})
    return track, cursor


def _lerp_value(left: Any, right: Any, amount: float) -> Any:
    if isinstance(left, list) and isinstance(right, list):
        return [float(a) + (float(b) - float(a)) * amount for a, b in zip(left, right)]
    return float(left) + (float(right) - float(left)) * amount


def evaluate_track(track: dict[str, Any], frame: int, frame_count: int) -> Any:
    status = track.get("status")
    if status == "fixed":
        return track.get("fixed")
    keys = list(track.get("keys") or [])
    if status != "animated" or not keys:
        return track.get("default")
    if len(keys) == 1:
        return keys[0]["value"]

    current_index = 0
    for index, key in enumerate(keys):
        if int(key["frame"]) <= frame:
            current_index = index
        else:
            break
    current = keys[current_index]
    if current_index + 1 < len(keys):
        following = keys[current_index + 1]
        start = int(current["frame"])
        finish = int(following["frame"])
        span = max(1, finish - start)
        amount = max(0.0, min(1.0, (frame - start) / float(span)))
        return _lerp_value(current["value"], following["value"], amount)

    following = keys[0]
    start = int(current["frame"])
    finish = max(start + 1, int(frame_count))
    amount = max(0.0, min(1.0, (frame - start) / float(max(1, finish - start))))
    return _lerp_value(current["value"], following["value"], amount)


def parse_external_records(data: bytes, report) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for record in report.records:
        if int(record.get("masked_section_type") or 0) != SECTION_EXTERNAL:
            continue
        start = int(record.get("payload_start") or 0)
        end = int(record.get("payload_end") or 0)
        try:
            _need(data, start, 8, end, "External payload")
            object_id = int(record.get("object_id") or 0)
            rows[object_id] = {
                "object_id": object_id,
                "object_name": str(record.get("object_name") or ""),
                "referenced_parent_id": _i32(data, start, end),
                "referenced_object_id": _i32(data, start + 4, end),
            }
        except Exception as exc:
            rows[int(record.get("object_id") or 0)] = {
                "object_id": record.get("object_id"),
                "object_name": record.get("object_name"),
                "error": str(exc),
            }
    return rows


def parse_object_controller(
    data: bytes,
    start: int,
    end: int,
    *,
    frame_count: int,
    external_records: dict[int, dict[str, Any]],
    object_lookup: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    _need(data, start, 8, end, "ObjectController header")
    external_id = _i32(data, start, end)
    params = _i32(data, start + 4, end)
    cursor = start + 8
    position, cursor = _parse_track(data, cursor, end, mode=_track_mode(params, 0), name="position", reader=_position_value, default=[0.0, 0.0, 0.0])
    rotation, cursor = _parse_track(data, cursor, end, mode=_track_mode(params, 1), name="rotation", reader=_rotation_value, default=[0.0, 0.0, 0.0])
    scale, cursor = _parse_track(data, cursor, end, mode=_track_mode(params, 2), name="scale", reader=_scale_value, default=[1.0, 1.0, 1.0])
    alpha, cursor = _parse_track(data, cursor, end, mode=_track_mode(params, 3), name="alpha", reader=_float_value, default=1.0)

    external = external_records.get(external_id)
    target_id = external.get("referenced_object_id") if isinstance(external, dict) else None
    target = object_lookup.get(int(target_id)) if isinstance(target_id, int) else None
    return {
        "controller_type": ANIME_OBJECT_CONTROLLER,
        "external_id": external_id,
        "external_name": str((object_lookup.get(external_id) or {}).get("name") or ""),
        "target_object_id": target_id,
        "target_object_name": str(target.get("name") or "") if isinstance(target, dict) else "",
        "controller_params": params,
        "tracks": {"position": position, "rotation": rotation, "scale": scale, "alpha": alpha},
        "bytes_consumed": cursor - start,
        "payload_size": end - start,
        "payload_remainder": max(0, end - cursor),
        "frame_count": frame_count,
    }


def parse_animation_record(data: bytes, record: dict[str, Any], *, external_records: dict[int, dict[str, Any]], object_lookup: dict[int, dict[str, Any]]) -> dict[str, Any]:
    start = int(record.get("payload_start") or 0)
    end = int(record.get("payload_end") or 0)
    _need(data, start, 8, end, "Animation header")
    frame_count = _i32(data, start, end)
    rest_block_size = _i32(data, start + 4, end)
    cursor = start + 8
    frame_markers = [0]
    playback_type = 0
    controllers: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    warnings: list[str] = []

    while cursor + 8 <= end:
        block_offset = cursor
        raw_type = _u32(data, cursor, end)
        block_type = raw_type & 0xFFFF
        block_words = _i32(data, cursor + 4, end)
        cursor += 8
        if block_words < 0:
            warnings.append(f"negative animation block size at 0x{block_offset:X}")
            break
        payload_start = cursor
        payload_end = payload_start + block_words * 4
        if payload_end > end:
            warnings.append(f"animation block at 0x{block_offset:X} exceeds payload bounds")
            break

        block: dict[str, Any] = {"offset": block_offset, "type": block_type, "size_words": block_words, "payload_start": payload_start, "payload_end": payload_end}
        if block_type == ANIME_FRAME:
            if payload_end - payload_start >= 4:
                frame_number = _i32(data, payload_start, payload_end)
                block["frame_number"] = frame_number
                if frame_number in {PLAY_ONCE, PLAY_REPEAT}:
                    playback_type = frame_number
                    blocks.append(block)
                    cursor = payload_end
                    break
                frame_markers.append(frame_number)
        elif block_type == ANIME_OBJECT_CONTROLLER:
            try:
                controller = parse_object_controller(data, payload_start, payload_end, frame_count=frame_count, external_records=external_records, object_lookup=object_lookup)
                controllers.append(controller)
                block["controller_index"] = len(controllers) - 1
            except Exception as exc:
                block["error"] = f"{type(exc).__name__}: {exc}"
                warnings.append(f"object controller at 0x{block_offset:X}: {exc}")
        blocks.append(block)
        cursor = payload_end

    return {
        "object_id": record.get("object_id"),
        "object_name": str(record.get("object_name") or ""),
        "frame_count": frame_count,
        "rest_block_size": rest_block_size,
        "frame_markers": frame_markers,
        "playback_type": playback_type,
        "playback_name": "Play Once" if playback_type == PLAY_ONCE else "Repeat" if playback_type == PLAY_REPEAT else "Unknown",
        "controllers": controllers,
        "controller_count": len(controllers),
        "blocks": blocks,
        "warnings": warnings,
        "pose_ready": bool(controllers),
    }


def parse_gen1_animations(data: bytes, report) -> list[dict[str, Any]]:
    external_records = parse_external_records(data, report)
    rows: list[dict[str, Any]] = []
    for record in report.records:
        if int(record.get("masked_section_type") or 0) != SECTION_ANIMATION:
            continue
        try:
            rows.append(parse_animation_record(data, record, external_records=external_records, object_lookup=report.object_lookup))
        except Exception as exc:
            rows.append({"object_id": record.get("object_id"), "object_name": record.get("object_name"), "pose_ready": False, "error": f"{type(exc).__name__}: {exc}"})
    return rows


def select_pose_animation(animations: list[dict[str, Any]], preferred_name: str | None = None) -> dict[str, Any] | None:
    ready = [row for row in animations if row.get("pose_ready") and row.get("controllers")]
    if not ready:
        return None
    if preferred_name:
        needle = preferred_name.lower()
        matched = [row for row in ready if needle in str(row.get("object_name") or "").lower()]
        if matched:
            return max(matched, key=lambda row: int(row.get("controller_count") or 0))
    idle = [row for row in ready if "nut" in str(row.get("object_name") or "").lower()]
    if idle:
        return max(idle, key=lambda row: int(row.get("controller_count") or 0))
    return max(ready, key=lambda row: int(row.get("controller_count") or 0))


def identity_matrix() -> list[list[float]]:
    return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def matrix_multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [[sum(left[row][inner] * right[inner][column] for inner in range(4)) for column in range(4)] for row in range(4)]


def _quaternion_from_euler(rotation: list[float]) -> tuple[float, float, float, float]:
    x, y, z = (float(rotation[0]), float(rotation[1]), float(rotation[2]))
    cx, sx = math.cos(x * 0.5), math.sin(x * 0.5)
    cy, sy = math.cos(y * 0.5), math.sin(y * 0.5)
    cz, sz = math.cos(z * 0.5), math.sin(z * 0.5)
    return (sx * cy * cz - cx * sy * sz, cx * sy * cz + sx * cy * sz, cx * cy * sz - sx * sy * cz, cx * cy * cz + sx * sy * sz)


def pose_matrix(position: list[float], rotation: list[float], scale: list[float]) -> list[list[float]]:
    x, y, z, w = _quaternion_from_euler(rotation)
    rotation_matrix = [
        [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0.0],
        [2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0.0],
        [2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    scale_matrix = identity_matrix()
    scale_matrix[0][0], scale_matrix[1][1], scale_matrix[2][2] = (float(scale[0]), float(scale[1]), float(scale[2]))
    translation = identity_matrix()
    translation[3][0], translation[3][1], translation[3][2] = (float(position[0]), float(position[1]), float(position[2]))
    return matrix_multiply(matrix_multiply(scale_matrix, rotation_matrix), translation)


def transform_point(point: list[float] | tuple[float, float, float], matrix: list[list[float]]) -> tuple[float, float, float]:
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    return (
        x * matrix[0][0] + y * matrix[1][0] + z * matrix[2][0] + matrix[3][0],
        x * matrix[0][1] + y * matrix[1][1] + z * matrix[2][1] + matrix[3][1],
        x * matrix[0][2] + y * matrix[1][2] + z * matrix[2][2] + matrix[3][2],
    )


@dataclass
class Gen1PoseContext:
    source: Path
    data: bytes
    report: Any
    objects: dict[int, dict[str, Any]]
    clumps: list[dict[str, Any]]
    clump_by_object: dict[int, dict[str, Any]]
    animations: list[dict[str, Any]]
    selected_animation: dict[str, Any] | None
    frame: int
    local_poses: dict[int, dict[str, Any]]
    world_matrices: dict[int, list[list[float]]]
    warnings: list[str]


def build_pose_context(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> Gen1PoseContext:
    source = Path(path).expanduser()
    data = source.read_bytes()
    report = decode_with_gen1_deformables(source)
    generation = str(report.header.get("generation") or "")
    if generation != "Gen1":
        raise PoseDecodeError(f"Gen1 pose runtime does not support {generation or 'unknown generation'}")

    objects: dict[int, dict[str, Any]] = {}
    clumps: list[dict[str, Any]] = []
    warnings: list[str] = []
    for record in report.records:
        record_type = int(record.get("masked_section_type") or 0)
        try:
            if record_type == base.SECTION_OBJECT:
                row = parse_object_record(data, record, generation)
                objects[int(row["object_id"])] = row
            elif record_type == base.SECTION_CLUMP:
                clumps.append(parse_clump_record(data, record, generation))
        except Exception as exc:
            warnings.append(f"{record.get('object_name') or record.get('object_id')}: {exc}")

    clump_by_object: dict[int, dict[str, Any]] = {}
    for clump in clumps:
        for node_index, object_id in enumerate(clump.get("node_ids") or []):
            clump_by_object[int(object_id)] = {"clump": clump, "node_index": node_index}

    animations = parse_gen1_animations(data, report)
    selected = select_pose_animation(animations, animation_name)
    selected_frame = max(0, int(frame))
    local_poses: dict[int, dict[str, Any]] = {
        object_id: {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "alpha": 1.0, "source": "Gen1 identity pose"}
        for object_id in objects
    }
    if selected is not None:
        selected_frame %= max(1, int(selected.get("frame_count") or 1))
        for controller in selected.get("controllers") or []:
            target_id = controller.get("target_object_id")
            if not isinstance(target_id, int) or target_id not in local_poses:
                continue
            tracks = controller.get("tracks") or {}
            local_poses[target_id] = {
                "position": evaluate_track(tracks["position"], selected_frame, int(selected["frame_count"])),
                "rotation": evaluate_track(tracks["rotation"], selected_frame, int(selected["frame_count"])),
                "scale": evaluate_track(tracks["scale"], selected_frame, int(selected["frame_count"])),
                "alpha": evaluate_track(tracks["alpha"], selected_frame, int(selected["frame_count"])),
                "source": str(selected.get("object_name") or selected.get("object_id")),
            }

    local_matrices = {object_id: pose_matrix(list(pose["position"]), list(pose["rotation"]), list(pose["scale"])) for object_id, pose in local_poses.items()}
    world_matrices: dict[int, list[list[float]]] = {}
    visiting: set[int] = set()

    def resolve_world(object_id: int) -> list[list[float]]:
        if object_id in world_matrices:
            return world_matrices[object_id]
        if object_id in visiting:
            warnings.append(f"object parent cycle while resolving {object_id}")
            return identity_matrix()
        visiting.add(object_id)
        row = objects.get(object_id)
        local = local_matrices.get(object_id, identity_matrix())
        parent_id = int((row or {}).get("parent_object_id") or 0)
        world = matrix_multiply(local, resolve_world(parent_id)) if parent_id and parent_id in objects else local
        visiting.discard(object_id)
        world_matrices[object_id] = world
        return world

    for object_id in objects:
        resolve_world(object_id)

    return Gen1PoseContext(source=source, data=data, report=report, objects=objects, clumps=clumps, clump_by_object=clump_by_object, animations=animations, selected_animation=selected, frame=selected_frame, local_poses=local_poses, world_matrices=world_matrices, warnings=warnings)


def model_owner_object(context: Gen1PoseContext, model_id: int) -> int | None:
    for object_id, row in context.objects.items():
        if int(row.get("model_id") or 0) == int(model_id):
            return object_id
    return None


def clump_node_object(context: Gen1PoseContext, owner_object_id: int | None, node_index: int) -> int | None:
    if owner_object_id is None:
        return None
    membership = context.clump_by_object.get(owner_object_id)
    clump = membership.get("clump") if isinstance(membership, dict) else None
    nodes = clump.get("node_ids") if isinstance(clump, dict) else None
    if not isinstance(nodes, list) or not (0 <= int(node_index) < len(nodes)):
        return None
    return int(nodes[int(node_index)])


def transformed_submodel_positions(context: Gen1PoseContext, *, model_id: int, submodel: dict[str, Any]) -> list[tuple[float, float, float]]:
    owner_id = model_owner_object(context, model_id)
    parser_mode = str(submodel.get("parser_mode") or "")
    vertices = list(submodel.get("vertices") or [])
    output: list[tuple[float, float, float]] = []

    if parser_mode == "studioccs_gen1_deform_weighted":
        for vertex in vertices:
            bone_ids = list(vertex.get("bone_ids") or [0, 0])
            weights = list(vertex.get("weights") or [1.0, 0.0])
            positions = [vertex.get("position") or [0.0, 0.0, 0.0], vertex.get("position2") or [0.0, 0.0, 0.0]]
            total = [0.0, 0.0, 0.0]
            applied = False
            for index in range(2):
                weight = float(weights[index] if index < len(weights) else 0.0)
                if weight == 0.0:
                    continue
                node_index = int(bone_ids[index] if index < len(bone_ids) else 0)
                object_id = clump_node_object(context, owner_id, node_index)
                matrix = context.world_matrices.get(object_id, identity_matrix())
                transformed = transform_point(positions[index], matrix)
                total[0] += transformed[0] * weight
                total[1] += transformed[1] * weight
                total[2] += transformed[2] * weight
                applied = True
            output.append(tuple(total) if applied else tuple(float(v) for v in positions[0]))
        return output

    if parser_mode == "studioccs_gen1_deform_rigid":
        node_index = int(submodel.get("parent_id") or 0)
        object_id = clump_node_object(context, owner_id, node_index)
        matrix = context.world_matrices.get(object_id, identity_matrix())
    else:
        parent_id = submodel.get("parent_id")
        object_id = int(parent_id) if isinstance(parent_id, int) else owner_id
        matrix = context.world_matrices.get(object_id, identity_matrix())

    for vertex in vertices:
        point = vertex.get("position") if isinstance(vertex, dict) else vertex
        if isinstance(point, (list, tuple)) and len(point) >= 3:
            output.append(transform_point(point, matrix))
    return output


def pose_summary(context: Gen1PoseContext) -> dict[str, Any]:
    selected = context.selected_animation
    deformable = []
    for record in context.report.records:
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if model and int(model.get("model_type") or -1) == base.CCS_MODEL_DEFORMABLE:
            deformable.append({"model": record.get("object_name") or record.get("object_id"), "status": model.get("parse_status"), "submodels": len(model.get("submodels") or []), "vertices": sum(int(row.get("decoded_vertex_count") or 0) for row in model.get("submodels") or [])})
    return {
        "source": str(context.source),
        "selected_animation": (selected or {}).get("object_name"),
        "frame": context.frame,
        "animation_count": len(context.animations),
        "object_count": len(context.objects),
        "clump_count": len(context.clumps),
        "posed_object_count": sum(1 for row in context.local_poses.values() if row.get("source") != "Gen1 identity pose"),
        "deformable_models": deformable,
        "warnings": list(context.warnings),
    }

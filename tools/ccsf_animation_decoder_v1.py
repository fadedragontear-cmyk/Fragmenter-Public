#!/usr/bin/env python3
"""StudioCCS-backed CCSF animation metadata parser for Fragmenter 1.0.

This pass intentionally stops before playback. It confirms animation frame counts,
play mode, controller block types, controller target IDs/names, and packed track
modes. Controls must remain disabled until track payloads are parsed and evaluated.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

import ccsf_structure_decoder

SECTION_ANIMATION = 0x0700
ANIME_FRAME = 0xFF01
ANIME_OBJECT_KEYFRAME = 0x0101
ANIME_OBJECT_CONTROLLER = 0x0102
ANIME_MATERIAL_CONTROLLER = 0x0202
ANIME_LIGHT_AMBIENT_KEYFRAME = 0x0601
ANIME_LIGHT_DIRECTIONAL_CONTROLLER = 0x0603
ANIME_LIGHT_OMNI_CONTROLLER = 0x0609
ANIME_MORPH_KEYFRAME = 0x1901
PLAY_ONCE = -1
PLAY_REPEAT = -2

BLOCK_NAMES = {
    ANIME_FRAME: "frame",
    ANIME_OBJECT_KEYFRAME: "object_keyframe",
    ANIME_OBJECT_CONTROLLER: "object_controller",
    ANIME_MATERIAL_CONTROLLER: "material_controller",
    ANIME_LIGHT_AMBIENT_KEYFRAME: "ambient_light_keyframe",
    ANIME_LIGHT_DIRECTIONAL_CONTROLLER: "directional_light_controller",
    ANIME_LIGHT_OMNI_CONTROLLER: "omni_light_controller",
    ANIME_MORPH_KEYFRAME: "morph_keyframe",
}
TRACK_NAMES = {0: "none", 1: "fixed", 2: "animated"}


def _need(data: bytes, offset: int, size: int, end: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > end or offset + size > len(data):
        raise ValueError(f"{label} exceeds animation payload bounds")


def _i32(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 4, end, "int32")
    return struct.unpack_from("<i", data, offset)[0]


def _u32(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 4, end, "uint32")
    return struct.unpack_from("<I", data, offset)[0]


def track_mode(params: int, track_id: int) -> int:
    return (int(params) >> (3 * int(track_id))) & 0x7


def _track_rows(params: int, controller_type: int, generation: str) -> list[dict[str, Any]]:
    if controller_type == ANIME_OBJECT_CONTROLLER:
        definitions = [(0, "position"), (1, "rotation"), (2, "scale"), (3, "alpha")]
        if generation != "Gen1":
            definitions.insert(2, (8, "quaternion_rotation"))
    elif controller_type == ANIME_MATERIAL_CONTROLLER:
        definitions = [(0, "u_offset"), (1, "v_offset"), (2, "unknown_float_1"), (3, "unknown_float_2")]
    else:
        definitions = []
    return [
        {
            "track_id": track_id,
            "name": name,
            "mode": track_mode(params, track_id),
            "mode_name": TRACK_NAMES.get(track_mode(params, track_id), f"unknown_{track_mode(params, track_id)}"),
            "keyframe_count": None,
        }
        for track_id, name in definitions
    ]


def parse_animation_payload(
    data: bytes,
    start: int,
    end: int,
    *,
    object_lookup: dict[int, dict[str, Any]] | None = None,
    generation: str = "Unknown",
) -> dict[str, Any]:
    _need(data, start, 8, end, "animation header")
    frame_count = _i32(data, start, end)
    rest_block_size = _i32(data, start + 4, end)
    if frame_count < 0 or frame_count > 1_000_000:
        raise ValueError(f"invalid animation frame count: {frame_count}")
    cursor = start + 8
    frames = [0]
    blocks: list[dict[str, Any]] = []
    controllers: list[dict[str, Any]] = []
    playback_type = 0
    warnings: list[str] = []
    lookup = object_lookup or {}

    while cursor + 8 <= end:
        block_offset = cursor
        raw_type = _u32(data, cursor, end)
        block_type = raw_type & 0xFFFF
        block_words = _i32(data, cursor + 4, end)
        cursor += 8
        if block_words < 0:
            warnings.append(f"negative animation block size at 0x{block_offset:X}")
            break
        payload_size = block_words * 4
        payload_start = cursor
        payload_end = payload_start + payload_size
        if payload_end > end:
            warnings.append(f"animation block at 0x{block_offset:X} exceeds payload bounds")
            break
        block: dict[str, Any] = {
            "offset": block_offset,
            "raw_type": raw_type,
            "type": block_type,
            "type_name": BLOCK_NAMES.get(block_type, f"unknown_0x{block_type:04X}"),
            "size_words": block_words,
            "payload_start": payload_start,
            "payload_end": payload_end,
        }

        if block_type == ANIME_FRAME:
            if payload_size < 4:
                block["warning"] = "frame block is truncated"
            else:
                frame_number = _i32(data, payload_start, payload_end)
                block["frame_number"] = frame_number
                if frame_number in {PLAY_ONCE, PLAY_REPEAT}:
                    playback_type = frame_number
                    blocks.append(block)
                    cursor = payload_end
                    break
                frames.append(frame_number)
        elif block_type in {
            ANIME_OBJECT_CONTROLLER,
            ANIME_MATERIAL_CONTROLLER,
            ANIME_LIGHT_DIRECTIONAL_CONTROLLER,
            ANIME_LIGHT_OMNI_CONTROLLER,
        }:
            controller: dict[str, Any] = {
                "type": block_type,
                "type_name": BLOCK_NAMES.get(block_type, f"unknown_0x{block_type:04X}"),
                "offset": block_offset,
                "payload_size": payload_size,
                "parse_status": "header_only",
                "tracks": [],
            }
            if payload_size >= 8:
                object_id = _i32(data, payload_start, payload_end)
                params = _i32(data, payload_start + 4, payload_end)
                target = lookup.get(object_id) if isinstance(lookup, dict) else None
                controller.update(
                    {
                        "object_id": object_id,
                        "object_name": str(target.get("name") or "") if isinstance(target, dict) else "",
                        "controller_params": params,
                        "tracks": _track_rows(params, block_type, generation),
                    }
                )
            else:
                controller["warning"] = "controller payload is too small for target/params header"
            controllers.append(controller)
            block["controller_index"] = len(controllers) - 1
        blocks.append(block)
        cursor = payload_end

    playback_name = "Play Once" if playback_type == PLAY_ONCE else "Repeat" if playback_type == PLAY_REPEAT else "Unknown"
    return {
        "frame_count": frame_count,
        "rest_block_size": rest_block_size,
        "playback_type": playback_type,
        "playback_name": playback_name,
        "frames": frames,
        "frame_markers": len(frames),
        "controllers": controllers,
        "controller_count": len(controllers),
        "blocks": blocks,
        "warnings": warnings,
        "metadata_status": "parsed",
        "playback_ready": False,
        "playback_status": "Animation metadata/controllers parsed; track payload evaluation is not implemented.",
    }


def extract_animation_metadata(asset_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(asset_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    raw = source.read_bytes()
    decoded = ccsf_structure_decoder.decode(source)
    structure = ccsf_structure_decoder.report_to_dict(decoded)
    generation = str((structure.get("header") or {}).get("generation") or "Unknown")
    records = structure.get("records") if isinstance(structure.get("records"), list) else []
    lookup: dict[int, dict[str, Any]] = {}
    for entry in structure.get("object_index") or []:
        if isinstance(entry, dict) and entry.get("id") is not None:
            lookup[int(entry["id"])] = entry

    animations: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or int(record.get("masked_section_type") or 0) != SECTION_ANIMATION:
            continue
        row: dict[str, Any] = {
            "object_id": record.get("object_id"),
            "object_name": record.get("object_name"),
            "generation": generation,
        }
        try:
            row.update(
                parse_animation_payload(
                    raw,
                    int(record.get("payload_start") or 0),
                    int(record.get("payload_end") or 0),
                    object_lookup=lookup,
                    generation=generation,
                )
            )
        except Exception as exc:
            row.update({"metadata_status": "error", "playback_ready": False, "error": str(exc)})
        animations.append(row)

    report = {
        "version": 1,
        "source": str(source),
        "generation": generation,
        "animations": animations,
        "summary": {
            "animation_records": len(animations),
            "metadata_parsed": sum(1 for row in animations if row.get("metadata_status") == "parsed"),
            "playback_ready": sum(1 for row in animations if row.get("playback_ready")),
        },
    }
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "animation_metadata.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract CCSF animation metadata")
    parser.add_argument("asset", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = extract_animation_metadata(args.asset, args.out)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if not any(row.get("metadata_status") == "error" for row in report["animations"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

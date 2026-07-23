#!/usr/bin/env python3
"""Verified StudioCCS-backed Gen1 TEX/CLUT extraction for Fragmenter 1.0.

Primary reference:
- NCDyson/StudioCCS libCCS/CCSTexture.cs
- NCDyson/StudioCCS libCCS/CCSClut.cs
- NCDyson/StudioCCS libCCS/Util.cs

Only structurally validated I4, I8, and RGBA32 textures produce PNG output.
Unknown, truncated, DXT, and unsupported-generation records remain metadata only.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import zlib
from pathlib import Path
from typing import Any

import ccsf_structure_decoder

TEXTURE_I4 = 0x14
TEXTURE_I8 = 0x13
TEXTURE_RGBA32 = 0x00
TEXTURE_DXT1 = 0x87
TEXTURE_DXT5 = 0x89
TEXTURE_TYPES = {
    TEXTURE_I4: "I4",
    TEXTURE_I8: "I8",
    TEXTURE_RGBA32: "RGBA32",
    TEXTURE_DXT1: "DXT1",
    TEXTURE_DXT5: "DXT5",
}


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return cleaned or "texture"


def _need(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"{label} requires bytes 0x{offset:X}:0x{offset + size:X}, file size is 0x{len(data):X}")


def _i32(data: bytes, offset: int) -> int:
    _need(data, offset, 4, "int32")
    return struct.unpack_from("<i", data, offset)[0]


def _u8(data: bytes, offset: int) -> int:
    _need(data, offset, 1, "uint8")
    return data[offset]


def _alpha(raw: int) -> int:
    return 0xFF if raw >= 0x7F else raw * 2


def parse_clut_record(data: bytes, record: dict[str, Any]) -> dict[str, Any]:
    start = int(record.get("payload_start") or 0)
    end = int(record.get("payload_end") or 0)
    _need(data, start, 16, "CLUT header")
    blit_group = _i32(data, start)
    unknown_1 = _i32(data, start + 4)
    unknown_2 = _i32(data, start + 8)
    color_count = _i32(data, start + 12)
    if color_count < 0 or color_count > 65536:
        raise ValueError(f"invalid CLUT color count: {color_count}")
    palette_start = start + 16
    palette_size = color_count * 4
    if end and palette_start + palette_size > end:
        raise ValueError("CLUT palette exceeds setup-record payload bounds")
    _need(data, palette_start, palette_size, "CLUT palette")
    palette: list[tuple[int, int, int, int]] = []
    has_alpha = False
    for index in range(color_count):
        offset = palette_start + index * 4
        b, g, r, raw_a = data[offset : offset + 4]
        a = _alpha(raw_a)
        has_alpha = has_alpha or a != 0xFF
        palette.append((r, g, b, a))
    return {
        "object_id": int(record.get("object_id") or 0),
        "object_name": str(record.get("object_name") or ""),
        "blit_group": blit_group,
        "unknown_1": unknown_1,
        "unknown_2": unknown_2,
        "color_count": color_count,
        "palette_start": palette_start,
        "palette_end": palette_start + palette_size,
        "has_alpha": has_alpha,
        "palette": palette,
        "status": "decoded",
    }


def parse_texture_record(data: bytes, record: dict[str, Any], generation: str) -> dict[str, Any]:
    start = int(record.get("payload_start") or 0)
    end = int(record.get("payload_end") or 0)
    _need(data, start, 20, "Gen1 texture header")
    clut_id = _i32(data, start)
    blit_group = _i32(data, start + 4)
    flags = _u8(data, start + 8)
    texture_type = _u8(data, start + 9)
    mip_count = _u8(data, start + 10)
    unknown_byte = _u8(data, start + 11)
    width_code = _u8(data, start + 12)
    height_code = _u8(data, start + 13)
    unknown_short = struct.unpack_from("<h", data, start + 14)[0]

    result: dict[str, Any] = {
        "object_id": int(record.get("object_id") or 0),
        "object_name": str(record.get("object_name") or ""),
        "clut_id": clut_id,
        "blit_group": blit_group,
        "flags": flags,
        "texture_type": texture_type,
        "texture_type_name": TEXTURE_TYPES.get(texture_type, f"unknown_0x{texture_type:02X}"),
        "mip_count": mip_count,
        "unknown_byte": unknown_byte,
        "width_code": width_code,
        "height_code": height_code,
        "unknown_short": unknown_short,
        "generation": generation,
        "status": "metadata_only",
        "warnings": [],
    }
    if texture_type not in TEXTURE_TYPES:
        result["warnings"].append("unknown texture type")
        return result
    if generation != "Gen1":
        result["warnings"].append("only the StudioCCS Gen1 texture header is verified in this decoder")
        return result
    if width_code > 15 or height_code > 15:
        result["warnings"].append("invalid Gen1 power-of-two dimension exponent")
        return result

    width = 1 << width_code
    height = 1 << height_code
    result["width"] = width
    result["height"] = height
    result["generation_unknown"] = _i32(data, start + 16)
    size_field_offset = start + 20
    size_words = _i32(data, size_field_offset)
    result["texture_data_size_field"] = size_words
    if size_words < 0:
        result["warnings"].append("negative texture data size")
        return result

    data_start = size_field_offset + 4
    if texture_type in {TEXTURE_DXT1, TEXTURE_DXT5}:
        result["status"] = "recognized_dxt_unexported"
        result["warnings"].append("DXT extraction is not part of the verified PNG path")
        return result

    data_size = size_words * 4
    data_end = data_start + data_size
    result["data_start"] = data_start
    result["data_end"] = data_end
    result["data_size"] = data_size
    if end and data_end > end:
        result["warnings"].append("texture data exceeds setup-record payload bounds")
        return result
    try:
        _need(data, data_start, data_size, "texture pixels")
    except ValueError as exc:
        result["warnings"].append(str(exc))
        return result

    expected = width * height
    if texture_type == TEXTURE_I4:
        expected_bytes = (expected + 1) // 2
    elif texture_type == TEXTURE_I8:
        expected_bytes = expected
    else:
        expected_bytes = expected * 4
    result["expected_base_level_bytes"] = expected_bytes
    if data_size < expected_bytes:
        result["warnings"].append(
            f"texture data too small for {width}x{height} {result['texture_type_name']}: {data_size} < {expected_bytes}"
        )
        return result
    if data_size > expected_bytes:
        result["warnings"].append(f"base-level decode uses first {expected_bytes} of {data_size} bytes")
    result["pixel_data"] = data[data_start : data_start + expected_bytes]
    result["status"] = "pixel_data_decoded"
    return result


def decode_rgba(texture: dict[str, Any], clut: dict[str, Any] | None) -> bytes:
    width = int(texture.get("width") or 0)
    height = int(texture.get("height") or 0)
    pixel_count = width * height
    raw = texture.get("pixel_data")
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("texture has no validated pixel data")
    texture_type = int(texture.get("texture_type") or 0)
    rgba = bytearray()

    if texture_type in {TEXTURE_I4, TEXTURE_I8}:
        if not clut or clut.get("status") != "decoded":
            raise ValueError("indexed texture has no decoded CLUT")
        palette = clut.get("palette")
        if not isinstance(palette, list):
            raise ValueError("decoded CLUT has no palette")
        indices: list[int] = []
        if texture_type == TEXTURE_I4:
            for value in raw:
                indices.append(value & 0x0F)
                if len(indices) < pixel_count:
                    indices.append((value >> 4) & 0x0F)
        else:
            indices = list(raw[:pixel_count])
        if len(indices) < pixel_count:
            raise ValueError("indexed texture has fewer indices than pixels")
        for index in indices[:pixel_count]:
            if index >= len(palette):
                raise ValueError(f"texture index {index} exceeds CLUT size {len(palette)}")
            rgba.extend(palette[index])
    elif texture_type == TEXTURE_RGBA32:
        if len(raw) < pixel_count * 4:
            raise ValueError("RGBA32 texture payload is truncated")
        for offset in range(0, pixel_count * 4, 4):
            b, g, r, raw_a = raw[offset : offset + 4]
            rgba.extend((r, g, b, _alpha(raw_a)))
    else:
        raise ValueError(f"texture type {texture_type:#x} is not supported by PNG export")

    expected_rgba = pixel_count * 4
    if len(rgba) != expected_rgba:
        raise ValueError(f"decoded RGBA size mismatch: {len(rgba)} != {expected_rgba}")
    return bytes(rgba)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def write_rgba_png(path: str | Path, width: int, height: int, rgba: bytes) -> Path:
    target = Path(path)
    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    expected = width * height * 4
    if len(rgba) != expected:
        raise ValueError(f"PNG RGBA payload must be {expected} bytes, got {len(rgba)}")
    stride = width * 4
    scanlines = b"".join(b"\x00" + rgba[row * stride : (row + 1) * stride] for row in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(scanlines, 9)) + _png_chunk(b"IEND", b"")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return target


def _json_safe_texture(texture: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in texture.items() if key != "pixel_data"}


def _json_safe_clut(clut: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in clut.items() if key != "palette"}


def extract_textures(asset_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(asset_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    data = source.read_bytes()
    structure = ccsf_structure_decoder.report_to_dict(ccsf_structure_decoder.decode(source))
    generation = str((structure.get("header") or {}).get("generation") or "Unknown")
    records = structure.get("records") if isinstance(structure.get("records"), list) else []

    cluts: dict[int, dict[str, Any]] = {}
    clut_rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or int(record.get("masked_section_type") or 0) != ccsf_structure_decoder.SECTION_CLUT:
            continue
        try:
            clut = parse_clut_record(data, record)
            cluts[int(clut["object_id"])] = clut
            clut_rows.append(_json_safe_clut(clut))
        except Exception as exc:
            clut_rows.append({"object_id": record.get("object_id"), "object_name": record.get("object_name"), "status": "error", "error": str(exc)})

    output_root = Path(output_dir).expanduser()
    textures: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or int(record.get("masked_section_type") or 0) != ccsf_structure_decoder.SECTION_TEXTURE:
            continue
        try:
            texture = parse_texture_record(data, record, generation)
            row = _json_safe_texture(texture)
            clut = cluts.get(int(texture.get("clut_id") or -1))
            row["clut_name"] = clut.get("object_name") if clut else None
            if texture.get("status") == "pixel_data_decoded":
                rgba = decode_rgba(texture, clut)
                name = _safe_name(str(texture.get("object_name") or f"texture_{texture.get('object_id')}"))
                png_path = write_rgba_png(output_root / f"{name}.png", int(texture["width"]), int(texture["height"]), rgba)
                row["status"] = "png_exported"
                row["png_path"] = str(png_path)
                row["rgba_bytes"] = len(rgba)
            textures.append(row)
        except Exception as exc:
            textures.append({"object_id": record.get("object_id"), "object_name": record.get("object_name"), "status": "error", "error": str(exc)})

    report = {
        "version": 1,
        "source": str(source),
        "generation": generation,
        "textures": textures,
        "cluts": clut_rows,
        "summary": {
            "texture_records": len(textures),
            "clut_records": len(clut_rows),
            "png_exported": sum(1 for row in textures if row.get("status") == "png_exported"),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "texture_extract_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract verified Gen1 CCSF TEX/CLUT images")
    parser.add_argument("asset", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = extract_textures(args.asset, args.out)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if not any(row.get("status") == "error" for row in report["textures"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

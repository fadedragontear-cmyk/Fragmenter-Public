#!/usr/bin/env python3
"""Expanded read-only CCSF texture decode for Fragmenter.

Header walking follows StudioCCS ``CCSTexture.Read`` for Gen1 and Gen2/3-style
power-of-two/non-power-of-two layouts. Base-level DXT1/DXT5 (BC1/BC3) is decoded
to RGBA for PNG preview. Mip payloads remain ignored by the preview path.
"""
from __future__ import annotations

import struct
from typing import Any

import ccsf_texture_decoder_v1 as v1

TEXTURE_I4 = v1.TEXTURE_I4
TEXTURE_I8 = v1.TEXTURE_I8
TEXTURE_RGBA32 = v1.TEXTURE_RGBA32
TEXTURE_DXT1 = v1.TEXTURE_DXT1
TEXTURE_DXT5 = v1.TEXTURE_DXT5
TEXTURE_TYPES = v1.TEXTURE_TYPES


def _need(data: bytes, offset: int, size: int, end: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > end or offset + size > len(data):
        raise ValueError(f"{label} requires 0x{offset:X}:0x{offset + size:X}, bound is 0x{end:X}")


def _i16(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 2, end, "int16")
    return struct.unpack_from("<h", data, offset)[0]


def _i32(data: bytes, offset: int, end: int) -> int:
    _need(data, offset, 4, end, "int32")
    return struct.unpack_from("<i", data, offset)[0]


def parse_texture_record(data: bytes, record: dict[str, Any], generation: str) -> dict[str, Any]:
    start = int(record.get("payload_start") or 0)
    end = int(record.get("payload_end") or len(data))
    _need(data, start, 16, end, "texture header")
    clut_id = _i32(data, start, end)
    blit_group = _i32(data, start + 4, end)
    flags = data[start + 8]
    texture_type = data[start + 9]
    mip_count = data[start + 10]
    unknown_byte = data[start + 11]
    width_code = data[start + 12]
    height_code = data[start + 13]
    unknown_short = _i16(data, start + 14, end)
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

    cursor = start + 16
    non_power_of_two = False
    if generation == "Gen1":
        if width_code > 15 or height_code > 15:
            result["warnings"].append("invalid Gen1 power-of-two dimension exponent")
            return result
        width, height = 1 << width_code, 1 << height_code
        result["generation_unknown"] = _i32(data, cursor, end)
        cursor += 4
    else:
        if width_code == 0xFF or height_code == 0xFF:
            non_power_of_two = True
            if texture_type in {TEXTURE_DXT1, TEXTURE_DXT5}:
                result["warnings"].append("StudioCCS rejects non-power-of-two DXT textures")
                return result
            width = _i16(data, cursor, end)
            height = _i16(data, cursor + 2, end)
            cursor += 4
        else:
            if width_code > 15 or height_code > 15:
                result["warnings"].append("invalid power-of-two dimension exponent")
                return result
            width, height = 1 << width_code, 1 << height_code
            if texture_type in {TEXTURE_DXT1, TEXTURE_DXT5}:
                _need(data, cursor, 0x28, end, "Gen2 DXT dimension header")
                cursor += 0x10
                stated_width = _i16(data, cursor, end)
                stated_height = _i16(data, cursor + 2, end)
                cursor += 4
                result["secondary_dimensions"] = [stated_width, stated_height]
                if stated_width != width or stated_height != height:
                    result["warnings"].append(
                        f"secondary DXT dimensions differ: {stated_width}x{stated_height} vs {width}x{height}"
                    )
                cursor += 0x14
            else:
                result["generation_unknown"] = _i32(data, cursor, end)
                cursor += 4

    if width <= 0 or height <= 0:
        result["warnings"].append(f"invalid texture dimensions {width}x{height}")
        return result
    result.update({"width": width, "height": height, "non_power_of_two": non_power_of_two})

    size_field_offset = cursor
    size_value = _i32(data, cursor, end)
    cursor += 4
    result["texture_data_size_field"] = size_value
    result["texture_data_size_field_offset"] = size_field_offset
    if size_value < 0:
        result["warnings"].append("negative texture data size")
        return result

    if texture_type in {TEXTURE_DXT1, TEXTURE_DXT5}:
        data_size = size_value - 0x40
        cursor += 0x1C
        block_size = 8 if texture_type == TEXTURE_DXT1 else 16
        expected_bytes = ((width + 3) // 4) * ((height + 3) // 4) * block_size
    else:
        data_size = size_value * 4
        pixel_count = width * height
        expected_bytes = (pixel_count + 1) // 2 if texture_type == TEXTURE_I4 else pixel_count if texture_type == TEXTURE_I8 else pixel_count * 4

    result.update({"data_start": cursor, "data_size": data_size, "expected_base_level_bytes": expected_bytes})
    if data_size < expected_bytes:
        result["warnings"].append(
            f"texture data too small for {width}x{height} {result['texture_type_name']}: {data_size} < {expected_bytes}"
        )
        return result
    if data_size > expected_bytes:
        result["warnings"].append(f"base-level decode uses first {expected_bytes} of {data_size} bytes")
    try:
        _need(data, cursor, expected_bytes, end, "base texture pixels")
    except ValueError as exc:
        result["warnings"].append(str(exc))
        return result
    result["data_end"] = cursor + data_size
    result["pixel_data"] = data[cursor : cursor + expected_bytes]
    result["status"] = "pixel_data_decoded"
    return result


def _rgb565(value: int) -> tuple[int, int, int]:
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31


def _bc1_palette(c0: int, c1: int, *, force_four: bool) -> list[tuple[int, int, int, int]]:
    r0, g0, b0 = _rgb565(c0)
    r1, g1, b1 = _rgb565(c1)
    colors = [(r0, g0, b0, 255), (r1, g1, b1, 255)]
    if force_four or c0 > c1:
        colors.extend(
            [
                ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3, 255),
                ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3, 255),
            ]
        )
    else:
        colors.extend([((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2, 255), (0, 0, 0, 0)])
    return colors


def _alpha_palette(a0: int, a1: int) -> list[int]:
    values = [a0, a1]
    if a0 > a1:
        values.extend(((7 - i) * a0 + i * a1) // 7 for i in range(1, 7))
    else:
        values.extend(((5 - i) * a0 + i * a1) // 5 for i in range(1, 5))
        values.extend([0, 255])
    return values


def _decode_bc(texture: dict[str, Any]) -> bytes:
    width = int(texture["width"])
    height = int(texture["height"])
    texture_type = int(texture["texture_type"])
    raw = bytes(texture["pixel_data"])
    block_size = 8 if texture_type == TEXTURE_DXT1 else 16
    output = bytearray(width * height * 4)
    cursor = 0
    for block_y in range((height + 3) // 4):
        for block_x in range((width + 3) // 4):
            block = raw[cursor : cursor + block_size]
            cursor += block_size
            if len(block) != block_size:
                raise ValueError("truncated BC block")
            if texture_type == TEXTURE_DXT5:
                alpha_values = _alpha_palette(block[0], block[1])
                alpha_bits = int.from_bytes(block[2:8], "little")
                color = block[8:16]
            else:
                alpha_values = [255] * 8
                alpha_bits = 0
                color = block
            c0, c1, color_bits = struct.unpack_from("<HHI", color, 0)
            palette = _bc1_palette(c0, c1, force_four=texture_type == TEXTURE_DXT5)
            for pixel in range(16):
                x = block_x * 4 + (pixel % 4)
                y = block_y * 4 + (pixel // 4)
                if x >= width or y >= height:
                    continue
                rgba = list(palette[(color_bits >> (pixel * 2)) & 0x3])
                if texture_type == TEXTURE_DXT5:
                    rgba[3] = alpha_values[(alpha_bits >> (pixel * 3)) & 0x7]
                out = (y * width + x) * 4
                output[out : out + 4] = bytes(rgba)
    return bytes(output)


def decode_rgba(texture: dict[str, Any], clut: dict[str, Any] | None) -> bytes:
    texture_type = int(texture.get("texture_type") or 0)
    if texture_type in {TEXTURE_DXT1, TEXTURE_DXT5}:
        return _decode_bc(texture)
    return v1.decode_rgba(texture, clut)


parse_clut_record = v1.parse_clut_record
write_rgba_png = v1.write_rgba_png

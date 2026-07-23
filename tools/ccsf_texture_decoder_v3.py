#!/usr/bin/env python3
"""StudioCCS-compatible display transform for decoded Gen1 CCS textures.

Fragmenter's decoder produces a conventional top-down RGBA image. StudioCCS
uploads System.Drawing's bottom-up BGRA bitmap memory as RGBA, so the actual
StudioCCS viewport used by Fragment modders is vertically inverted and has red
and blue exchanged relative to that conventional image. Apply that transform at
one boundary so exported PNGs and software-rendered models agree.
"""
from __future__ import annotations

from typing import Any

import ccsf_texture_decoder_v2 as v2

_BASE_DECODE = v2.decode_rgba
_UNCOMPRESSED = {v2.TEXTURE_I4, v2.TEXTURE_I8, v2.TEXTURE_RGBA32}


def studioccs_display_rgba(rgba: bytes, width: int, height: int) -> bytes:
    """Return StudioCCS viewport orientation/channel order for top-down RGBA."""
    width = int(width)
    height = int(height)
    expected = width * height * 4
    if width <= 0 or height <= 0 or len(rgba) != expected:
        raise ValueError(f"invalid RGBA surface {width}x{height}: {len(rgba)} bytes")
    stride = width * 4
    output = bytearray(expected)
    for target_y in range(height):
        source_y = height - 1 - target_y
        source_row = source_y * stride
        target_row = target_y * stride
        for x in range(width):
            source = source_row + x * 4
            target = target_row + x * 4
            r, g, b, a = rgba[source : source + 4]
            output[target : target + 4] = bytes((b, g, r, a))
    return bytes(output)


def decode_rgba(texture: dict[str, Any], clut: dict[str, Any] | None) -> bytes:
    """Decode then normalize uncompressed Gen1 textures to StudioCCS display."""
    rgba = _BASE_DECODE(texture, clut)
    generation = str(texture.get("generation") or "")
    texture_type = int(texture.get("texture_type") or 0)
    if generation == "Gen1" and texture_type in _UNCOMPRESSED:
        rgba = studioccs_display_rgba(rgba, int(texture["width"]), int(texture["height"]))
        texture["display_transform"] = {
            "authority": "StudioCCS viewport / System.Drawing bottom-up BGRA upload",
            "vertical_flip": True,
            "swap_red_blue": True,
        }
    else:
        texture["display_transform"] = {
            "authority": "native decoded layout",
            "vertical_flip": False,
            "swap_red_blue": False,
        }
    return rgba

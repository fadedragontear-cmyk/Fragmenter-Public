#!/usr/bin/env python3
"""Public-facing Area Server file inspection for Fragmenter 1.0.

The old research tools remain useful, but their raw JSON/hex-first presentation is
not a suitable default. This module provides a stable view model for a future GUI:
Overview, Clean Text, Structure/Members, and Hex last.
"""
from __future__ import annotations

import gzip
import os
from pathlib import Path
from typing import Any

from binary_preview import (
    GZIP_MAGIC,
    ccsf_summary,
    detect_magic,
    safe_gzip_preview,
    strings_with_offsets,
    symbol_summary,
)
from project_workspace_v1 import sha256_file

DEFAULT_PREVIEW_CAP = 8 * 1024 * 1024
DEFAULT_DECOMPRESS_CAP = 512 * 1024 * 1024
DEFAULT_MAX_STRINGS = 1000
DEFAULT_HEX_BYTES = 256

_CLASS_LABELS = {
    "model_paths": "Model",
    "texture_paths": "Texture",
    "animation_paths": "Animation",
    "audio_paths": "Audio",
    "symbols": "Symbol",
    "paths": "Path",
    "unknown_strings": "Text",
}
_CLASS_PRIORITY = {
    "symbols": 0,
    "model_paths": 1,
    "texture_paths": 2,
    "animation_paths": 3,
    "audio_paths": 4,
    "paths": 5,
    "unknown_strings": 6,
}


def _read_bounded(path: Path, cap: int) -> tuple[bytes, bool]:
    if cap <= 0:
        raise ValueError("cap must be positive")
    with path.open("rb") as handle:
        data = handle.read(cap + 1)
    return data[:cap], len(data) > cap


def _hex_lines(data: bytes, width: int = 16) -> list[str]:
    lines: list[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hex_part = " ".join(f"{byte:02X}" for byte in chunk)
        text_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08X}  {hex_part:<{width * 3 - 1}}  {text_part}")
    return lines


def _useful_string(value: str) -> bool:
    text = value.strip()
    if len(text) < 4:
        return False
    if len(set(text)) == 1:
        return False
    if not any(ch.isalnum() for ch in text):
        return False
    return True


def _clean_entries(data: bytes, max_strings: int) -> list[dict[str, Any]]:
    entries = strings_with_offsets(data, cap=max_strings * 2)
    seen: set[tuple[str, str]] = set()
    cleaned: list[dict[str, Any]] = []
    for entry in entries:
        value = str(entry.get("string") or "").strip()
        kind = str(entry.get("class") or "unknown_strings")
        if not _useful_string(value):
            continue
        key = (kind, value)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(
            {
                "offset": int(entry.get("offset") or 0),
                "kind": kind,
                "label": _CLASS_LABELS.get(kind, "Text"),
                "text": value,
            }
        )
        if len(cleaned) >= max_strings:
            break
    cleaned.sort(key=lambda row: (_CLASS_PRIORITY.get(str(row["kind"]), 99), int(row["offset"]), str(row["text"]).lower()))
    return cleaned


def render_clean_text(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "No readable identifiers, paths, or text were found in the bounded preview.\n"
    lines = ["Readable identifiers and text", ""]
    current: str | None = None
    for entry in entries:
        label = str(entry["label"])
        if label != current:
            if current is not None:
                lines.append("")
            lines.append(f"[{label}]")
            current = label
        lines.append(f"0x{int(entry['offset']):08X}  {entry['text']}")
    return "\n".join(lines) + "\n"


def inspect_server_file(
    path: str | Path,
    *,
    preview_cap: int = DEFAULT_PREVIEW_CAP,
    max_strings: int = DEFAULT_MAX_STRINGS,
    hex_bytes: int = DEFAULT_HEX_BYTES,
) -> dict[str, Any]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    stat = source.stat()
    raw_preview, raw_truncated = _read_bounded(source, preview_cap)
    raw_magic = detect_magic(raw_preview[:4096])
    is_gzip = raw_preview.startswith(GZIP_MAGIC)
    warnings: list[str] = []
    layer_data = raw_preview
    layer_name = "source"
    decompressed_truncated = False

    if is_gzip:
        try:
            layer_data, decompressed_truncated = safe_gzip_preview(source, preview_cap)
            layer_name = "decompressed gzip preview"
            if decompressed_truncated:
                warnings.append(f"Decompressed preview capped at {preview_cap:,} bytes")
        except Exception as exc:
            warnings.append(f"Gzip preview failed: {exc}")
            layer_data = b""
            layer_name = "gzip preview unavailable"

    inner_magic = detect_magic(layer_data[:4096]) if layer_data else []
    strings = _clean_entries(layer_data, max_strings) if layer_data else []
    ccsf = ccsf_summary(layer_data) if layer_data else ccsf_summary(b"")
    symbols = symbol_summary(layer_data, max_list=250) if layer_data else {}

    structure: list[dict[str, Any]] = [
        {
            "kind": "file",
            "name": source.name,
            "path": str(source),
            "size": stat.st_size,
            "detected": [hit.get("type") for hit in raw_magic],
        }
    ]
    if is_gzip:
        structure.append(
            {
                "kind": "compression",
                "type": "gzip",
                "preview_bytes": len(layer_data),
                "preview_truncated": decompressed_truncated,
                "detected_inside": [hit.get("type") for hit in inner_magic],
            }
        )
    for offset in ccsf.get("fragment_core_CCSF_SIG_offsets", []):
        structure.append({"kind": "CCSF", "offset": int(offset), "source_layer": layer_name})
    for offset in ccsf.get("plain_CCSF_offsets", []):
        structure.append({"kind": "CCSF marker", "offset": int(offset), "source_layer": layer_name})

    return {
        "version": 1,
        "overview": {
            "name": source.name,
            "path": str(source),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": sha256_file(source),
            "is_gzip": is_gzip,
            "source_preview_bytes": len(raw_preview),
            "source_preview_truncated": raw_truncated,
            "content_layer": layer_name,
            "content_preview_bytes": len(layer_data),
            "content_preview_truncated": decompressed_truncated,
            "source_magic": raw_magic,
            "content_magic": inner_magic,
        },
        "clean_text": strings,
        "clean_text_rendered": render_clean_text(strings),
        "structure": structure,
        "symbols": symbols,
        "ccsf": ccsf,
        "hex_preview": {
            "source": "raw file header",
            "bytes": min(hex_bytes, len(raw_preview)),
            "lines": _hex_lines(raw_preview[:hex_bytes]),
        },
        "warnings": warnings,
    }


def export_decompressed(
    source: str | Path,
    destination: str | Path,
    *,
    max_output_bytes: int = DEFAULT_DECOMPRESS_CAP,
) -> dict[str, Any]:
    input_path = Path(source).expanduser()
    output_path = Path(destination).expanduser()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    with input_path.open("rb") as handle:
        if handle.read(2) != GZIP_MAGIC:
            raise ValueError(f"Not a gzip file: {input_path}")
    if max_output_bytes <= 0:
        raise ValueError("max_output_bytes must be positive")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.name + ".fragmenter_tmp")
    if temp.exists():
        temp.unlink()
    written = 0
    truncated = False
    try:
        with gzip.open(input_path, "rb") as source_handle, temp.open("wb") as output_handle:
            while written < max_output_bytes:
                chunk = source_handle.read(min(1024 * 1024, max_output_bytes - written))
                if not chunk:
                    break
                output_handle.write(chunk)
                written += len(chunk)
            if written >= max_output_bytes and source_handle.read(1):
                truncated = True
        if truncated:
            temp.unlink(missing_ok=True)
            raise ValueError(f"Decompressed output exceeds safety cap of {max_output_bytes:,} bytes")
        os.replace(temp, output_path)
    finally:
        if temp.exists():
            temp.unlink()
    return {
        "source": str(input_path),
        "destination": str(output_path),
        "bytes": written,
        "sha256": sha256_file(output_path),
    }

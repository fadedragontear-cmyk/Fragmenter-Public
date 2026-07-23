#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

MAX_SIGNATURE_BYTES = 64

MAGIC_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "PNG image", "image"),
    (b"\xff\xd8\xff", "JPEG image", "image"),
    (b"BM", "BMP image", "image"),
    (b"GIF87a", "GIF image", "image"),
    (b"GIF89a", "GIF image", "image"),
    (b"DDS ", "DDS texture", "image"),
    (b"II*\x00", "TIFF image (little-endian)", "image"),
    (b"MM\x00*", "TIFF image (big-endian)", "image"),
    (b"glTF", "GLB model", "model"),
    (b"Kaydara FBX Binary", "FBX model (binary)", "model"),
)

KNOWN_EXTENSIONS = {
    ".bmp": ("BMP image", "image"),
    ".dds": ("DDS texture", "image"),
    ".fbx": ("FBX model", "model"),
    ".gif": ("GIF image", "image"),
    ".glb": ("GLB model", "model"),
    ".gltf": ("glTF model", "model"),
    ".jpeg": ("JPEG image", "image"),
    ".jpg": ("JPEG image", "image"),
    ".mdl": ("Custom/legacy model container", "model"),
    ".obj": ("Wavefront OBJ model", "model"),
    ".png": ("PNG image", "image"),
    ".stl": ("STL model", "model"),
    ".tm2": ("PS2 TIM2 texture", "image"),
}

NATIVE_3D_EXTENSIONS = {".glb", ".gltf", ".obj", ".stl", ".fbx"}
NATIVE_3D_MAGIC = {b"glTF", b"Kaydara FBX Binary"}


def _format_signature(sig: bytes) -> str:
    if not sig:
        return "(empty)"
    return " ".join(f"{b:02X}" for b in sig)


def probe_model_asset(path: Path) -> dict[str, object]:
    target = Path(path)
    ext = target.suffix.lower()
    try:
        size = target.stat().st_size
        with target.open("rb") as f:
            sig = f.read(MAX_SIGNATURE_BYTES)
    except Exception:
        size = 0
        sig = b""

    detected_name = ""
    detected_kind = ""
    for magic, name, kind in MAGIC_SIGNATURES:
        if sig.startswith(magic):
            detected_name = name
            detected_kind = kind
            break

    ext_name = ""
    ext_kind = ""
    if ext in KNOWN_EXTENSIONS:
        ext_name, ext_kind = KNOWN_EXTENSIONS[ext]

    if detected_name:
        format_name = detected_name
        format_kind = detected_kind or ext_kind or "unknown"
        heuristic = "Magic bytes matched known signature."
        known = True
    elif ext_name:
        format_name = ext_name
        format_kind = ext_kind or "unknown"
        heuristic = "Extension matched known format; signature inconclusive."
        known = True
    else:
        format_name = "Unknown/custom format"
        format_kind = "unknown"
        heuristic = "No known extension or signature match."
        known = False

    native_3d_supported = bool(ext in NATIVE_3D_EXTENSIONS or any(sig.startswith(m) for m in NATIVE_3D_MAGIC))
    native_3d_reason = (
        "Feasible format for native 3D preview."
        if native_3d_supported
        else "Not a confirmed native 3D preview format."
    )

    return {
        "path": str(target),
        "extension": ext or "(none)",
        "size_bytes": size,
        "signature_hex": _format_signature(sig),
        "known": known,
        "format_name": format_name,
        "format_kind": format_kind,
        "heuristic": heuristic,
        "native_3d_supported": native_3d_supported,
        "native_3d_reason": native_3d_reason,
    }


def _render_text(result: dict[str, object]) -> str:
    supported = "yes" if result.get("native_3d_supported") else "no"
    return "\n".join(
        [
            f"Path: {result.get('path')}",
            f"Extension: {result.get('extension')}",
            f"Size: {result.get('size_bytes')} bytes",
            f"Signature: {result.get('signature_hex')}",
            f"Format guess: {result.get('format_name')}",
            f"Kind: {result.get('format_kind')}",
            f"Native 3D supported: {supported}",
            f"Reason: {result.get('native_3d_reason')}",
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe model/texture candidate assets for preview support.")
    ap.add_argument("path", help="Path to candidate asset")
    ap.add_argument("--out", help="Write JSON report to this path")
    ap.add_argument("--text-out", help="Write readable text report to this path")
    args = ap.parse_args()

    result = probe_model_asset(Path(args.path))
    print(_render_text(result))

    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.text_out:
        Path(args.text_out).write_text(_render_text(result) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

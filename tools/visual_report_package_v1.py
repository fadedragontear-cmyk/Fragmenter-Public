#!/usr/bin/env python3
"""Create a portable review package for one visual asset."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import ccsf_setup_recovery_v1
import ccsf_structure_decoder
from ccsf_asset_tree_v1 import inspect_ccsf_contents
from ccsf_texture_decoder_v2 import write_rgba_png

FULL_SOURCE_LIMIT = 64 * 1024 * 1024
HEADER_BYTES = 8 * 1024 * 1024


def _safe(value: str) -> str:
    text = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value))
    return text.strip("._")[:120] or "asset"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if key not in {"rgba", "pixel_data", "palette"}}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_json_safe(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _wireframe_evidence(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    vertices = list(payload.get("vertices") or [])
    faces = list(payload.get("faces") or [])
    bounds = None
    if vertices:
        axes = list(zip(*[tuple(float(value) for value in row[:3]) for row in vertices]))
        bounds = {"min": [min(axis) for axis in axes], "max": [max(axis) for axis in axes]}
    return {
        **{key: value for key, value in payload.items() if key not in {"vertices", "faces"}},
        "bounds": bounds,
        "vertex_sample": vertices[:256],
        "face_sample": faces[:256],
    }


def _export_scene_textures(scene: Any, root: Path) -> list[dict[str, Any]]:
    target = root / "decoded_textures"
    target.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    textures = getattr(scene, "textures", {})
    values = textures.values() if isinstance(textures, dict) else []
    seen: set[tuple[str, int, int]] = set()
    for index, texture in enumerate(values):
        if not isinstance(texture, dict):
            continue
        rgba = texture.get("rgba")
        width = int(texture.get("width") or 0)
        height = int(texture.get("height") or 0)
        if not isinstance(rgba, (bytes, bytearray)) or width <= 0 or height <= 0:
            continue
        name = str(texture.get("object_name") or texture.get("external_object_id") or texture.get("object_id") or f"texture_{index}")
        key = (name, width, height)
        if key in seen:
            continue
        seen.add(key)
        path = target / f"{index:04d}_{_safe(name)}.png"
        write_rgba_png(path, width, height, bytes(rgba))
        rows.append(
            {
                "name": name,
                "path": path.relative_to(root).as_posix(),
                "width": width,
                "height": height,
                "texture_type": texture.get("texture_type_name"),
                "display_transform": texture.get("display_transform"),
                "external_source": texture.get("external_source"),
                "clut_resolution": texture.get("clut_resolution"),
            }
        )
    _write_json(root / "decoded_texture_manifest.json", rows)
    return rows


def package_visual_report(
    project: Any,
    row: dict[str, Any],
    *,
    annotation: dict[str, Any] | None = None,
    wireframe_payload: dict[str, Any] | None = None,
    scene: Any = None,
    contents: dict[str, Any] | None = None,
    camera: dict[str, Any] | None = None,
    texture_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(row["absolute_path"]).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = project.workspace_path("visual_reports") / "flags" / f"{timestamp}_{_safe(row.get('name') or source.stem)}"
    root.mkdir(parents=True, exist_ok=False)

    stat = source.stat()
    source_info = {
        "path": str(source),
        "relative_path": row.get("relative_path"),
        "name": row.get("name"),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": _sha256(source),
        "full_source_included": stat.st_size <= FULL_SOURCE_LIMIT,
    }
    _write_json(root / "manifest.json", {"asset": row, "annotation": annotation or {}, "camera": camera or {}, "source": source_info})

    source_dir = root / "source"
    source_dir.mkdir()
    if stat.st_size <= FULL_SOURCE_LIMIT:
        shutil.copy2(source, source_dir / source.name)
    else:
        with source.open("rb") as handle:
            (source_dir / f"{source.name}.first_{HEADER_BYTES}_bytes.bin").write_bytes(handle.read(HEADER_BYTES))

    decoded_report = ccsf_structure_decoder.decode(source)
    source_bytes = source.read_bytes()
    recovery = ccsf_setup_recovery_v1.recover_report(source, source_bytes, decoded_report)
    structure = ccsf_structure_decoder.report_to_dict(decoded_report)
    _write_json(root / "ccsf_structure.json", structure)
    _write_json(root / "indexed_setup_recovery.json", recovery)
    _write_json(root / "ccsf_contents.json", contents if isinstance(contents, dict) else inspect_ccsf_contents(source))
    _write_json(root / "wireframe_evidence.json", _wireframe_evidence(wireframe_payload))

    decoded_texture_count = 0
    if scene is not None:
        _write_json(root / "scene_summary.json", getattr(scene, "summary", {}))
        _write_json(root / "texture_records.json", getattr(scene, "texture_rows", []))
        _write_json(root / "material_records.json", getattr(scene, "material_rows", []))
        _write_json(root / "unresolved_texture_mapping.json", getattr(scene, "unresolved", {}))
        triangles = []
        for triangle in list(getattr(scene, "triangles", []))[:256]:
            triangles.append({key: value for key, value in triangle.items() if key != "texture"})
        _write_json(root / "triangle_mapping_sample.json", triangles)
        decoded_texture_count = len(_export_scene_textures(scene, root))

    output_source = Path(texture_output_dir).expanduser() if texture_output_dir else None
    if output_source and output_source.is_dir():
        copied = root / "generated_preview_and_textures"
        shutil.copytree(output_source, copied, dirs_exist_ok=True)

    zip_path = root.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root.parent))
    return {
        "report_dir": str(root),
        "zip_path": str(zip_path),
        "source_included": source_info["full_source_included"],
        "decoded_textures": decoded_texture_count,
        "recovered_setup_records": int(recovery.get("count") or 0),
        "zip_size": zip_path.stat().st_size,
    }

#!/usr/bin/env python3
"""Texture-resolution hardening and non-destructive per-asset preview overrides."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as base
import ccsf_textured_scene_v3 as scene_core
import ccsf_textured_scene_v6 as v6

TexturedScene = v6.TexturedScene
render_textured_scene = v6.render_textured_scene
export_scene_textures = v6.export_scene_textures
scene_wireframe_payload = v6.scene_wireframe_payload
preview_pixel_step = v6.preview_pixel_step
auto_texture_eligibility = v6.auto_texture_eligibility
set_preferred_clump = v6.set_preferred_clump
preferred_clump_id = v6.preferred_clump_id

_PREVIEW_OVERRIDES: dict[str, dict[str, Any]] = {}


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _name_key(value: Any) -> str:
    text = str(value or "").lower()
    for prefix in ("tex_", "mat_", "clt_", "texture_", "material_"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return "".join(character for character in text if character.isalnum())


def _robust_resolve_texture(context, materials: dict[int, dict[str, Any]], textures: dict[int, dict[str, Any]], mat_tex_id: Any):
    """Resolve only evidence-backed direct IDs, MAT links, or exact normalized names."""
    object_id = _optional_int(mat_tex_id)
    if object_id is None or object_id < 0:
        return None, None, "missing material/texture reference"

    direct = textures.get(object_id)
    if direct is not None:
        return direct, None, "direct decoded TEX id"

    material = materials.get(object_id)
    if material is not None:
        texture_id = _optional_int(material.get("texture_id"))
        texture = textures.get(texture_id) if texture_id is not None else None
        if texture is not None:
            return texture, material, "MAT -> decoded TEX id"

    entry = context.report.object_lookup.get(object_id)
    if isinstance(entry, dict):
        section_type = _optional_int(entry.get("section_type"))
        if section_type == base.SECTION_TEXTURE:
            return None, None, "direct TEX record exists but is not decoded"
        if section_type == base.SECTION_MATERIAL and material is None:
            return None, None, "MAT record exists but did not parse"
        target_key = _name_key(entry.get("name") or entry.get("object_name"))
        if target_key:
            name_matches = [texture for texture in textures.values() if _name_key(texture.get("object_name")) == target_key]
            if len(name_matches) == 1:
                return name_matches[0], material, "exact normalized object-name TEX match"

    return None, material, f"object {object_id} is not a resolved MAT/TEX"


scene_core._resolve_texture = _robust_resolve_texture


def _key(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def set_preview_override(path: str | Path, profile: dict[str, Any] | None) -> None:
    key = _key(path)
    if profile:
        _PREVIEW_OVERRIDES[key] = dict(profile)
    else:
        _PREVIEW_OVERRIDES.pop(key, None)


def preview_override(path: str | Path) -> dict[str, Any] | None:
    value = _PREVIEW_OVERRIDES.get(_key(path))
    return dict(value) if value is not None else None


def clear_scene_cache(source: str | Path | None = None) -> None:
    v6.clear_scene_cache(source)


def _vector(value: Any, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return default
    rows = []
    for index, fallback in enumerate(default):
        try:
            rows.append(float(value[index]))
        except (TypeError, ValueError):
            rows.append(float(fallback))
    return rows[0], rows[1], rows[2]


def _transform_point(point: tuple[float, float, float], transform: dict[str, Any]) -> tuple[float, float, float]:
    scale_x, scale_y, scale_z = _vector(transform.get("scale"), (1.0, 1.0, 1.0))
    rot_x, rot_y, rot_z = (math.radians(value) for value in _vector(transform.get("rotation_degrees"), (0.0, 0.0, 0.0)))
    trans_x, trans_y, trans_z = _vector(transform.get("translation"), (0.0, 0.0, 0.0))
    x, y, z = point[0] * scale_x, point[1] * scale_y, point[2] * scale_z

    cos_x, sin_x = math.cos(rot_x), math.sin(rot_x)
    y, z = y * cos_x - z * sin_x, y * sin_x + z * cos_x
    cos_y, sin_y = math.cos(rot_y), math.sin(rot_y)
    x, z = x * cos_y + z * sin_y, -x * sin_y + z * cos_y
    cos_z, sin_z = math.cos(rot_z), math.sin(rot_z)
    x, y = x * cos_z - y * sin_z, x * sin_z + y * cos_z
    return x + trans_x, y + trans_y, z + trans_z


def _apply_override(scene: TexturedScene, profile: dict[str, Any] | None) -> TexturedScene:
    transform = profile.get("transform") if isinstance(profile, dict) and isinstance(profile.get("transform"), dict) else None
    if not transform:
        return scene
    scale = _vector(transform.get("scale"), (1.0, 1.0, 1.0))
    rotation = _vector(transform.get("rotation_degrees"), (0.0, 0.0, 0.0))
    translation = _vector(transform.get("translation"), (0.0, 0.0, 0.0))
    flip = bool(transform.get("flip_winding", False))
    identity = scale == (1.0, 1.0, 1.0) and rotation == (0.0, 0.0, 0.0) and translation == (0.0, 0.0, 0.0) and not flip
    if identity:
        return scene

    triangles: list[dict[str, Any]] = []
    for source_triangle in scene.triangles:
        triangle = dict(source_triangle)
        positions = tuple(_transform_point(tuple(position), transform) for position in source_triangle.get("positions") or ())
        uvs = source_triangle.get("uvs")
        if flip and len(positions) == 3:
            positions = (positions[0], positions[2], positions[1])
            if isinstance(uvs, tuple) and len(uvs) == 3:
                uvs = (uvs[0], uvs[2], uvs[1])
        triangle["positions"] = positions
        triangle["uvs"] = uvs
        triangles.append(triangle)

    summary = dict(scene.summary)
    summary["preview_override"] = {
        "scale": list(scale),
        "rotation_degrees": list(rotation),
        "translation": list(translation),
        "flip_winding": flip,
    }
    summary["preview_override_applied"] = True
    return TexturedScene(
        source=scene.source,
        context=scene.context,
        triangles=triangles,
        textures=scene.textures,
        texture_rows=scene.texture_rows,
        materials=scene.materials,
        material_rows=scene.material_rows,
        unresolved=scene.unresolved,
        summary=summary,
    )


def load_textured_scene(path: str | Path, *, animation_name: str | None = None, frame: int = 0) -> TexturedScene:
    base_scene = v6.load_textured_scene(path, animation_name=animation_name, frame=frame)
    return _apply_override(base_scene, preview_override(path))


def load_scene_bundle(path: str | Path, *, animation_name: str | None = None, frame: int = 0, face_cap: int = 30_000) -> dict[str, Any]:
    scene = load_textured_scene(path, animation_name=animation_name, frame=frame)
    wireframe = scene_wireframe_payload(scene, face_cap=max(1, int(face_cap)))
    wireframe["parser"] = "clump_scene_bundle_v7"
    return {"scene": scene, "wireframe": wireframe}


def load_posed_wireframe_payload(path: str | Path, *, animation_name: str | None = None, frame: int = 0, face_cap: int = 30_000) -> dict[str, Any]:
    return load_scene_bundle(path, animation_name=animation_name, frame=frame, face_cap=face_cap)["wireframe"]

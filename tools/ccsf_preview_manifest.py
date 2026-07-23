#!/usr/bin/env python3
"""Build a conservative preview manifest for CCSF-like assets."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ccsf_asset_inspector import inspect_ccsf_asset

RENDERER_STATUS = {
    "model_decode": "pending",
    "texture_decode": "pending",
    "clt_decode": "pending",
    "material_binding": "pending",
    "animation_decode": "pending",
    "assembled_preview": "pending",
}

CHARACTER_MAIN_TERMS = (
    "body", "kbody", "ch_kbody", "t0", "caurbody", "ca1", "ca2", "cb", "xph", "xpl",
)
ENVIRONMENT_MAIN_TERMS = (
    "bg", "bac", "town", "field", "mou", "clo", "flo", "obj", "oba", "dat",
)
BONE_OBJECT_TERMS = (
    "pelvis", "spine", "head", "arm", "hand", "thigh", "calf", "foot", "toe", "finger", "trall",
)


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _groups(payload: dict[str, Any]) -> dict[str, list[str]]:
    raw = payload.get("groups")
    if not isinstance(raw, dict):
        return {}
    return {str(key): _list(value) for key, value in raw.items()}


def _strip_prefix(value: str) -> str:
    return value.split("_", 1)[1] if "_" in value else value


def _suffix(value: str) -> str:
    stem = Path(_strip_prefix(value).replace("\\", "/")).stem.lower()
    return re.sub(r"[^a-z0-9]+", "_", stem).strip("_")


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    low = value.lower()
    return any(term in low for term in terms)


def _preferred(values: list[str], terms: tuple[str, ...]) -> list[str]:
    preferred = [value for value in values if _contains_any(value, terms)]
    return preferred + [value for value in values if value not in preferred]


def _texture_clt_pairs(textures: list[str], clts: list[str]) -> list[dict[str, str]]:
    clt_by_suffix = {_suffix(clt): clt for clt in clts}
    pairs: list[dict[str, str]] = []
    for tex in textures:
        clt = clt_by_suffix.get(_suffix(tex))
        if clt:
            pairs.append({"texture": tex, "clt": clt})
    return pairs


def _load_payload(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        loaded = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("groups"), dict):
            loaded.setdefault("file", str(p))
            return loaded
    return inspect_ccsf_asset(p)


def build_manifest(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Build a preview manifest from an asset path or inspected asset payload."""
    payload = _load_payload(source) if not isinstance(source, dict) else dict(source)
    groups = _groups(payload)
    bundle_type = str(payload.get("type") or "unknown")

    model_candidates = _list(groups.get("MDL"))
    shadow_model_candidates = [value for value in model_candidates if "shadow" in value.lower()]
    non_shadow_models = [value for value in model_candidates if value not in shadow_model_candidates]

    if bundle_type.startswith("character"):
        main_model_candidates = _preferred(non_shadow_models, CHARACTER_MAIN_TERMS)
    elif bundle_type == "environment/background":
        main_model_candidates = _preferred(non_shadow_models, ENVIRONMENT_MAIN_TERMS)
    else:
        main_model_candidates = non_shadow_models

    object_candidates = _list(groups.get("OBJ"))
    bone_or_hierarchy_candidates = [
        value for value in object_candidates if _contains_any(value, BONE_OBJECT_TERMS)
    ]
    if bundle_type.startswith("character"):
        object_candidates = _preferred(object_candidates, BONE_OBJECT_TERMS)

    texture_candidates = _list(groups.get("TEX"))
    clt_candidates = _list(groups.get("CLT"))
    animation_candidates = _list(groups.get("ANM"))

    notes: list[str] = []
    if not payload.get("is_ccsf", True):
        notes.append("Input was not identified as CCSF-like by the asset inspector.")
    if not model_candidates:
        notes.append("No MDL_* identifiers found; model decoding cannot start yet.")
    if texture_candidates and not clt_candidates:
        notes.append("TEX_* identifiers found without matching CLT_* palette identifiers.")
    if clt_candidates and not texture_candidates:
        notes.append("CLT_* identifiers found without matching TEX_* texture identifiers.")

    has_mdl = bool(model_candidates)
    has_tex = bool(texture_candidates)
    has_clt = bool(clt_candidates)
    has_anm = bool(animation_candidates)

    return {
        "source_file": str(payload.get("file") or ""),
        "asset_name": str(payload.get("name") or ""),
        "bundle_type": bundle_type,
        "variant": str(payload.get("variant") or ""),
        "readiness": str(payload.get("readiness") or ""),
        "source_refs": _list(payload.get("source_refs")),
        "model_candidates": model_candidates,
        "main_model_candidates": main_model_candidates,
        "shadow_model_candidates": shadow_model_candidates,
        "submodel_candidates": _list(groups.get("MPH")),
        "texture_candidates": texture_candidates,
        "clt_candidates": clt_candidates,
        "texture_clt_pairs": _texture_clt_pairs(texture_candidates, clt_candidates),
        "material_candidates": _list(groups.get("MAT")),
        "animation_candidates": animation_candidates,
        "object_candidates": object_candidates,
        "bone_or_hierarchy_candidates": bone_or_hierarchy_candidates,
        "component_candidates": _list(groups.get("CMP")),
        "bounding_box_candidates": _list(groups.get("BOX")),
        "marker_candidates": _list(groups.get("DMY")),
        "light_candidates": _list(groups.get("LGT")),
        "camera_candidates": _list(groups.get("CAM")),
        "renderer_status": dict(RENDERER_STATUS),
        "notes": notes,
        "can_attempt_static_preview": has_mdl and has_tex and has_clt,
        "can_attempt_animated_preview": has_mdl and has_tex and has_clt and has_anm,
    }


def _section(lines: list[str], title: str, values: Any) -> None:
    lines.append(f"{title}:")
    if isinstance(values, list):
        if not values:
            lines.append("  - none")
        for value in values:
            if isinstance(value, dict):
                lines.append("  - " + ", ".join(f"{k}: {v}" for k, v in value.items()))
            else:
                lines.append(f"  - {value}")
    elif isinstance(values, dict):
        for key, value in values.items():
            lines.append(f"  - {key}: {value}")
    else:
        lines.append(f"  - {values or 'none'}")


def format_text(manifest: dict[str, Any]) -> str:
    lines = [
        "CCSF Preview Manifest",
        f"Asset: {manifest.get('asset_name') or '(unnamed)'}",
        f"Type: {manifest.get('bundle_type') or 'unknown'}",
        f"Variant: {manifest.get('variant') or '-'}",
    ]
    _section(lines, "Main model candidates", manifest.get("main_model_candidates") or [])
    _section(lines, "Shadow model candidates", manifest.get("shadow_model_candidates") or [])
    _section(lines, "Texture/CLT pairs", manifest.get("texture_clt_pairs") or [])
    _section(lines, "Materials", manifest.get("material_candidates") or [])
    _section(lines, "Animations", manifest.get("animation_candidates") or [])
    _section(lines, "Renderer status", manifest.get("renderer_status") or {})
    return "\n".join(lines) + "\n"


def write_outputs(manifest: dict[str, Any], out: str | None, text_out: str | None) -> None:
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if text_out:
        p = Path(text_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(format_text(manifest), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a CCSF preview manifest from an asset or inspected JSON payload.")
    ap.add_argument("path")
    ap.add_argument("--out")
    ap.add_argument("--text-out")
    args = ap.parse_args(argv)

    manifest = build_manifest(args.path)
    write_outputs(manifest, args.out, args.text_out)
    if not args.out and not args.text_out:
        print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

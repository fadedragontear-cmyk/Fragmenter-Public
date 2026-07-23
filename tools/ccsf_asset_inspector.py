#!/usr/bin/env python3
"""Inspect extracted CCSF-like asset bundles."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PREFIXES = ("OBJ_", "MDL_", "MAT_", "TEX_", "CLT_", "ANM_", "CMP_", "BOX_", "MPH_", "DMY_", "HIT_", "LGT_", "CAM_")
VARIANT_KEYS = ("br", "gr", "pp", "rd", "yl", "bl")
SOURCE_EXTS = (".max", ".bmp")
PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{3,}")


def _decode(raw: bytes) -> str:
    return raw.decode("ascii", errors="ignore").strip("\x00 \t\r\n")


def find_ccsf_offset(data: bytes) -> int | None:
    for off in (0, 8):
        if data[off:off + 4] == b"CCSF":
            return off
    found = data.find(b"CCSF")
    return found if found >= 0 else None


def extract_strings(data: bytes) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in PRINTABLE_RE.finditer(data):
        value = _decode(match.group(0))
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def extract_ccsf_name(data: bytes, strings: list[str], offset: int | None) -> str:
    if offset is not None:
        tail = data[offset:offset + 96]
        m = re.match(rb"CCSF([A-Za-z0-9_.-]{0,48})", tail)
        if m:
            name = _decode(m.group(0))
            if name:
                return name
    for s in strings:
        if s.startswith("CCSF"):
            return s
    return ""


def source_refs(strings: list[str]) -> list[str]:
    refs = []
    for s in strings:
        low = s.lower()
        if any(low.endswith(ext) or ext in low for ext in SOURCE_EXTS):
            refs.append(s)
    return refs


def grouped_identifiers(strings: list[str]) -> dict[str, list[str]]:
    groups = {prefix[:-1]: [] for prefix in PREFIXES}
    for s in strings:
        for prefix in PREFIXES:
            if s.startswith(prefix) and s not in groups[prefix[:-1]]:
                groups[prefix[:-1]].append(s)
    return groups


def detect_variant_key(name: str, identifiers: list[str], source_path: Path | None = None) -> str:
    hay = " ".join([name, *(identifiers[:100]), source_path.stem if source_path else ""]).lower()
    for key in VARIANT_KEYS:
        if re.search(rf"(?:^|[_\W0-9]){re.escape(key)}(?:$|[_\W0-9])", hay) or re.search(rf"ca\d*{key}", hay):
            return key
    return ""


def _flatten_groups(groups: dict[str, list[str]]) -> list[str]:
    return [item for values in groups.values() for item in values]


def _has_any_term(values: list[str], terms: tuple[str, ...]) -> bool:
    return any(term in value.lower() for value in values for term in terms)


def _has_source_prefix(refs: list[str], prefix: str) -> bool:
    return any(ref.lower().replace("/", "\\").startswith(prefix) for ref in refs)


def _has_variant_suffix(value: str, variant: str) -> bool:
    low = Path(value.replace("\\", "/")).stem.lower()
    return bool(re.search(rf"(?:^|[_\W0-9]){re.escape(variant)}$", low) or re.search(rf"ca\d*{re.escape(variant)}$", low))


def _has_character_body_signals(name: str, groups: dict[str, list[str]], refs: list[str]) -> bool:
    counts = {k: len(v) for k, v in groups.items()}
    identifiers = _flatten_groups(groups)
    low_name = name.lower()
    character_name_terms = ("body", "caur", "ca2", "ch", "chr", "pc", "npc")
    character_id_terms = (
        "body", "shadow", "skeleton", "skel", "bone", "limb", "arm", "leg", "bbox",
        "weapon", "axe", "hand", "head", "pelvis", "spine",
    )
    source_terms = ("\\body",)
    return (
        _has_source_prefix(refs, "c\\")
        or _has_any_term(refs, source_terms)
        or any(term in low_name for term in character_name_terms)
        or _has_any_term(identifiers, character_name_terms + character_id_terms)
        or (counts.get("MDL", 0) > 0 and (counts.get("TEX", 0) > 0 or counts.get("CLT", 0) > 0) and counts.get("ANM", 0) > 0)
    )


def _has_character_color_variant_signals(name: str, groups: dict[str, list[str]], refs: list[str], variant: str) -> bool:
    if variant not in VARIANT_KEYS or not _has_character_body_signals(name, groups, refs):
        return False
    texture_ids = groups.get("TEX", [])
    return any(_has_variant_suffix(value, variant) for value in [*texture_ids, *refs])


def _has_environment_background_signals(name: str, groups: dict[str, list[str]], refs: list[str]) -> bool:
    counts = {k: len(v) for k, v in groups.items()}
    identifiers = _flatten_groups(groups)
    low_name = name.lower()
    haystack = [low_name, *(value.lower() for value in identifiers), *(ref.lower() for ref in refs)]
    ref_terms = ("town", "field", "stage", "map", "back", "background", "bg", "bac", "mou", "clo", "flo", "oba", "se")
    environment_id_terms = ("sr4", "sr5", "sfa", "sfb", "se2")
    strong_scene_name = low_name.startswith(("ccsftown", "ccsfbg", "ccsfsr4", "ccsfsr5", "ccsfsfa", "ccsfsfb", "ccsfse"))
    has_scene_ref = _has_source_prefix(refs, "s\\") or _has_source_prefix(refs, "s/")
    has_scene_ref = has_scene_ref and _has_any_term(refs, ref_terms + environment_id_terms)
    has_scene_id = _has_any_term(identifiers, environment_id_terms) and _has_texture_material_signals(groups, refs)
    has_scene_metadata = counts.get("LGT", 0) > 0 or counts.get("DMY", 0) >= 8 or counts.get("HIT", 0) > 0
    has_named_background = any(re.search(r"(?:^|[_\W])(bg|bac|back|background|town|field|stage|map|se\d*)(?:$|[_\W0-9])", value) for value in haystack)
    has_many_environment_meshes = (counts.get("OBJ", 0) >= 8 or counts.get("MDL", 0) >= 8) and _has_texture_material_signals(groups, refs)
    return bool(strong_scene_name or has_scene_ref or has_scene_id or has_scene_metadata or has_named_background or has_many_environment_meshes)


def _has_texture_material_signals(groups: dict[str, list[str]], refs: list[str]) -> bool:
    counts = {k: len(v) for k, v in groups.items()}
    return bool(counts.get("TEX", 0) or counts.get("CLT", 0) or counts.get("MAT", 0) or any(r.lower().endswith(".bmp") for r in refs))


def _normalized_bundle_name(name: str) -> str:
    low = name.lower()
    return low[4:] if low.startswith("ccsf") else low


def _has_name_pattern(name: str, prefixes: tuple[str, ...]) -> bool:
    normalized = _normalized_bundle_name(name)
    return any(normalized.startswith(prefix) for prefix in prefixes)


def _has_frontend_ui_signals(name: str, groups: dict[str, list[str]], refs: list[str]) -> bool:
    values = [_normalized_bundle_name(name), *[value.lower() for value in _flatten_groups(groups)], *[ref.lower() for ref in refs]]
    patterns = ("xwindow", "xwin")
    return any(any(pattern in value for pattern in patterns) for value in values)


def _has_frontend_system_signals(name: str, groups: dict[str, list[str]], refs: list[str]) -> bool:
    values = [_normalized_bundle_name(name), *[value.lower() for value in _flatten_groups(groups)], *[ref.lower() for ref in refs]]
    patterns = ("title", "dnaslogo")
    return any(any(pattern in value for pattern in patterns) for value in values)


def _has_dialogue_candidate_signals(name: str, groups: dict[str, list[str]], refs: list[str]) -> bool:
    values = [_normalized_bundle_name(name), *[value.lower() for value in _flatten_groups(groups)], *[ref.lower() for ref in refs]]
    patterns = ("xnote", "xdl")
    return any(any(pattern in value for pattern in patterns) for value in values)


def _needs_survey_review(name: str, groups: dict[str, list[str]], refs: list[str]) -> bool:
    prefixes = ("xddn", "xddwal", "xfa", "xfb")
    if _has_name_pattern(name, prefixes):
        return True
    values = [Path(value.replace("\\", "/")).stem.lower() for value in [*_flatten_groups(groups), *refs]]
    return any(any(value.startswith(prefix) for prefix in prefixes) for value in values)


def _has_field_stage_signals(name: str, groups: dict[str, list[str]], refs: list[str]) -> bool:
    counts = {k: len(v) for k, v in groups.items()}
    values = [_normalized_bundle_name(name), *[value.lower() for value in _flatten_groups(groups)], *[ref.lower().replace("\\", "/") for ref in refs]]
    has_cmp = counts.get("CMP", 0) > 0
    many_meshes = counts.get("OBJ", 0) >= 6 or counts.get("MDL", 0) >= 6
    many_textures = counts.get("TEX", 0) >= 6 or counts.get("CLT", 0) >= 6
    path_scene = any(value.startswith("s/") or re.search(r"(?:^|[/_\W])(field|stage|map|town|bg|se\d+)(?:$|[/_\W0-9])", value) for value in values)
    return bool((has_cmp and many_meshes and many_textures) or (path_scene and many_meshes and _has_texture_material_signals(groups, refs)))


def classify_bundle(name: str, groups: dict[str, list[str]], refs: list[str], variant: str) -> str:
    counts = {k: len(v) for k, v in groups.items()}
    has_model_or_texture = any(counts.get(key, 0) for key in ("MDL", "TEX", "CLT"))
    if counts.get("ANM", 0) and not has_model_or_texture:
        return "animation-only"

    has_mdl_obj_anm_with_materials = bool(
        counts.get("MDL", 0)
        and counts.get("OBJ", 0)
        and counts.get("ANM", 0)
        and (counts.get("TEX", 0) or counts.get("CLT", 0))
    )
    has_strong_character_body = has_mdl_obj_anm_with_materials or _has_character_body_signals(name, groups, refs)
    has_character_color_variant = _has_character_color_variant_signals(name, groups, refs, variant)

    if _has_frontend_system_signals(name, groups, refs):
        return "system/frontend"
    if has_character_color_variant:
        return "character/color variant"
    if _has_field_stage_signals(name, groups, refs):
        return "field/stage candidate"
    if has_strong_character_body:
        return "character/body"
    if _needs_survey_review(name, groups, refs):
        return "unknown-ccsf"
    if _has_environment_background_signals(name, groups, refs):
        return "environment/background"
    if _has_dialogue_candidate_signals(name, groups, refs):
        return "text/dialogue candidate"
    if _has_frontend_ui_signals(name, groups, refs):
        return "ui/frontend"
    if counts.get("ANM", 0) >= max(3, counts.get("MDL", 0) + counts.get("TEX", 0)):
        return "animation-heavy"
    if _has_texture_material_signals(groups, refs):
        if not counts.get("MDL", 0) and not counts.get("OBJ", 0):
            return "texture/material"
    return "unknown-ccsf"


def classify_tags(name: str, groups: dict[str, list[str]], refs: list[str], kind: str) -> list[str]:
    counts = {k: len(v) for k, v in groups.items()}
    identifiers = _flatten_groups(groups)
    tags: set[str] = set()
    if kind == "field/stage candidate" or _has_field_stage_signals(name, groups, refs):
        tags.add("field/stage candidate")
    if counts.get("HIT", 0):
        tags.add("collision/hitmap candidate")
        tags.add("contains collision/HIT resources")
    if counts.get("DMY", 0):
        tags.add("dummy/marker candidate")
        tags.add("contains dummy/marker resources")
    if any(value.startswith("ANM_") and any(term in value.lower() for term in ("light", "lgt", "lamp", "sun", "shadow", "controller", "ctrl")) for value in identifiers):
        tags.add("lighting animation candidate")
    if counts.get("OBJ", 0) >= 8 and counts.get("MDL", 0) <= 1 and counts.get("CMP", 0) >= 1:
        tags.add("field chunk assembly candidate")
    if kind in {"environment/background", "field/stage candidate"} or tags.intersection({"field/stage candidate", "field chunk assembly candidate"}):
        tags.add("scene assembly may require transforms/controllers")
        tags.add("StudioCCS visual scatter does not necessarily mean invalid asset")
    return sorted(tags)


def readiness(groups: dict[str, list[str]], ccsf_like: bool) -> str:
    if not ccsf_like:
        return "not-ccsf"

    components = []
    if groups.get("MDL") or groups.get("OBJ"):
        components.append("model")
    if groups.get("TEX"):
        components.append("texture")
    if groups.get("CLT"):
        components.append("clt")
    if groups.get("MAT") or groups.get("TEX") or groups.get("CLT"):
        components.append("materials")
    if groups.get("ANM"):
        components.append("animation")
    if groups.get("HIT"):
        components.append("collision")

    return "+".join(components) if components else "metadata-only"


def inspect_ccsf_asset(path: str | Path) -> dict[str, object]:
    p = Path(path)
    data = p.read_bytes()
    offset = find_ccsf_offset(data)
    strings = extract_strings(data)
    groups = grouped_identifiers(strings)
    flat_ids = [item for values in groups.values() for item in values]
    name = extract_ccsf_name(data, strings, offset) or p.stem
    refs = source_refs(strings)
    variant = detect_variant_key(name, flat_ids + refs, p)
    kind = classify_bundle(name, groups, refs, variant)
    counts = {k: len(v) for k, v in groups.items()}
    ccsf_like = offset is not None
    tags = classify_tags(name, groups, refs, kind)
    return {
        "file": str(p),
        "name": name,
        "size": len(data),
        "is_ccsf": ccsf_like,
        "ccsf_offset": offset,
        "type": kind,
        "variant": variant,
        "source_refs": refs,
        "groups": groups,
        "counts": counts,
        "readiness": readiness(groups, ccsf_like),
        "tags": tags,
    }


def format_report(result: dict[str, object]) -> str:
    lines = [
        f"CCSF Asset: {result.get('name') or '(unnamed)'}",
        f"File: {result.get('file')}",
        f"Size: {result.get('size')} bytes",
        f"CCSF offset: {result.get('ccsf_offset')}",
        f"Type: {result.get('type')}",
        f"Variant: {result.get('variant') or '-'}",
        f"Readiness: {result.get('readiness')}",
        f"Tags: {', '.join(result.get('tags') or []) or '-'}",
        "",
        "Source refs:",
    ]
    refs = result.get("source_refs") or []
    lines.extend(f"  - {ref}" for ref in refs) if refs else lines.append("  - none")
    lines.append("")
    lines.append("Grouped resources:")
    groups = result.get("groups") or {}
    counts = result.get("counts") or {}
    for key in [p[:-1] for p in PREFIXES]:
        values = groups.get(key, []) if isinstance(groups, dict) else []
        lines.append(f"  {key} ({counts.get(key, len(values)) if isinstance(counts, dict) else len(values)}):")
        lines.extend(f"    - {value}" for value in values[:200])
        if not values:
            lines.append("    - none")
    return "\n".join(lines) + "\n"


def write_outputs(result: dict[str, object], out: str | None, text_out: str | None) -> None:
    if out:
        p = Path(out); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if text_out:
        p = Path(text_out); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(format_report(result), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inspect one CCSF-like extracted asset.")
    ap.add_argument("path")
    ap.add_argument("--out")
    ap.add_argument("--text-out")
    args = ap.parse_args(argv)
    result = inspect_ccsf_asset(args.path)
    write_outputs(result, args.out, args.text_out)
    if not args.out and not args.text_out:
        print(format_report(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

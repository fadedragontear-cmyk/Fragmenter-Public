#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

from fragment_core import PREFIXES, get_section, parse_asset_paths, read_maybe_gzip, scan_ascii_strings
from resource_queries import derive_family_search_terms
CATEGORY = {
    "MDL_": "models",
    "TEX_": "textures",
    "MAT_": "materials",
    "DMY_": "markers",
    "ANM_": "animations",
    "CAM_": "cameras",
}


def normalize_symbol_stem(name: str) -> str:
    raw = name.lower().strip()
    for p in PREFIXES:
        if raw.startswith(p.lower()):
            raw = raw[len(p) :]
            break
    raw = re.sub(r"[^a-z0-9]+", "", raw)
    raw = re.sub(r"\d+$", "", raw)
    return raw


def stem_from_path(path: str) -> str:
    p = path.lower().replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    base = base.split(".", 1)[0]
    base = re.sub(r"[^a-z0-9]+", "", base)
    base = re.sub(r"\d+$", "", base)
    return base


def family_keys(stem: str) -> List[str]:
    if not stem:
        return []
    keys = {stem}
    if len(stem) >= 4:
        keys.add(stem[:4])
    if len(stem) >= 6:
        keys.add(stem[:6])
    return sorted(keys, key=len, reverse=True)


def build_relationship_map(section_id: str, symbols_by_prefix: Dict[str, List[str]], asset_paths: List[str]) -> Dict:
    families: Dict[str, Dict] = {}

    def ensure(fam: str) -> Dict:
        if fam not in families:
            families[fam] = {
                "family": fam,
                "models": [],
                "textures": [],
                "materials": [],
                "animations": [],
                "cameras": [],
                "markers": [],
                "asset_paths": [],
                "confidence": 0.0,
                "notes": [],
                "suggested_searches": [],
            }
        return families[fam]

    for pfx, items in symbols_by_prefix.items():
        cat = CATEGORY[pfx]
        for item in items:
            stem = normalize_symbol_stem(item)
            if not stem:
                continue
            fam = ensure(stem)
            fam[cat].append(item)

    for p in asset_paths:
        stem = stem_from_path(p)
        if not stem:
            continue
        target = None
        for key in family_keys(stem):
            if key in families:
                target = key
                break
        target = target or stem
        ensure(target)["asset_paths"].append(p)

    for fam in families.values():
        for k in ("models", "textures", "materials", "animations", "cameras", "markers", "asset_paths"):
            fam[k] = sorted(set(fam[k]))
        fam["suggested_searches"] = derive_family_search_terms(fam["family"], max_suggestions=10)

        score = 0.25
        categories = sum(1 for k in ("models", "textures", "materials", "animations", "cameras", "markers") if fam[k])
        if categories >= 2:
            score += 0.25
            fam["notes"].append("Multiple symbolic categories share this normalized stem.")
        if fam["asset_paths"]:
            score += 0.25
            fam["notes"].append("Matching asset path stem(s) found.")
        if fam["models"] and fam["textures"] and fam["asset_paths"]:
            score += 0.25
            fam["notes"].append("Model + texture + disc-like asset path alignment suggests strong relationship.")
        fam["confidence"] = round(min(1.0, score), 2)
        if not fam["notes"]:
            fam["notes"].append("Grouped by shared normalized stem.")

    families_list = sorted(families.values(), key=lambda x: (-x["confidence"], x["family"]))
    return {
        "section": section_id,
        "family_count": len(families_list),
        "families": families_list,
        "symbols": symbols_by_prefix,
        "asset_paths": asset_paths,
    }


def summarize_text(payload: Dict, max_families: int = 40, max_items_per_category: int = 5) -> str:
    lines = [f"Section: {payload.get('section')}", f"Families: {payload.get('family_count', 0)}", ""]
    families = payload.get("families", [])
    for fam in families[:max_families]:
        lines.append(f"- family: {fam['family']}  (confidence={fam['confidence']})")
        for cat in ("models", "textures", "materials", "animations", "cameras", "markers"):
            if fam.get(cat):
                shown = fam[cat][:max_items_per_category]
                suffix = ""
                if len(fam[cat]) > len(shown):
                    suffix = f" ... (+{len(fam[cat]) - len(shown)} more)"
                lines.append(f"    {cat}: {', '.join(shown)}{suffix}")
        if fam.get("asset_paths"):
            shown_paths = fam["asset_paths"][:max_items_per_category]
            suffix = ""
            if len(fam["asset_paths"]) > len(shown_paths):
                suffix = f" ... (+{len(fam['asset_paths']) - len(shown_paths)} more)"
            lines.append(f"    asset_paths: {', '.join(shown_paths)}{suffix}")
        if fam.get("notes"):
            lines.append(f"    notes: {' | '.join(fam['notes'])}")
    if len(families) > max_families:
        lines.append("")
        lines.append(f"... {len(families) - max_families} more families omitted from text summary.")
    return "\n".join(lines) + "\n"


def map_from_file(path: Path, section: str | None) -> Dict:
    blob, _gz = read_maybe_gzip(path)
    sec_id, sec_blob = get_section(blob, section)
    strings = scan_ascii_strings(sec_blob)
    by = {p: sorted(set(s for s in strings if s.startswith(p))) for p in PREFIXES}
    asset_paths = parse_asset_paths(sec_blob)
    return build_relationship_map(sec_id, by, asset_paths)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a Resource Relationship Mapper for a CCSF section.")
    ap.add_argument("path", type=Path, help=".bin/.dat or extracted .ccsf")
    ap.add_argument("--section", help="Section id when input is .bin/.dat")
    ap.add_argument("--out", type=Path, help="Output JSON path")
    ap.add_argument("--text-out", type=Path, help="Output readable text summary")
    ap.add_argument("--summary-families", type=int, default=40, help="Cap summary family rows")
    ap.add_argument("--summary-items", type=int, default=5, help="Cap listed items per category")
    args = ap.parse_args()

    payload = map_from_file(args.path, args.section)
    text = summarize_text(payload, max_families=max(1, args.summary_families), max_items_per_category=max(1, args.summary_items))
    print(text)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON: {args.out}")
    if args.text_out:
        args.text_out.parent.mkdir(parents=True, exist_ok=True)
        args.text_out.write_text(text, encoding="utf-8")
        print(f"Wrote text: {args.text_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

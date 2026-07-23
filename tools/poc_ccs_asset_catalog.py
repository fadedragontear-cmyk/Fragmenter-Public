#!/usr/bin/env python3
"""Build a proof-of-concept catalog of extracted CCS/CCSF asset hints."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from ccs_explain import explain_identifier
from fragmenter_identifiers import extract_identifiers_from_file

FOCUS_TERMS = {
    "town": ("town", "ccsftown"),
    "npc": ("npc", "mdl_", "obj_", "dmy_"),
    "shop": ("shop", "merchant", "dmy_merchant", "lgt_shop"),
    "skybox": ("sky", "sun", "clo", "sr4sun", "sr4clo", "bg", "cloud"),
}


def iter_inputs(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    pattern = "**/*" if recursive else "*"
    return sorted([p for p in path.glob(pattern) if p.is_file() and p.suffix.lower() not in {".json", ".txt"}], key=lambda p: str(p).lower())


def in_focus(name: str, focus: str) -> bool:
    if focus == "all":
        return True
    lower = name.lower()
    return any(term in lower for term in FOCUS_TERMS[focus])


def classify(name: str, category: str) -> set[str]:
    lower = name.lower()
    labels: set[str] = set()
    if name.startswith("CCSF"):
        labels.add("ccsf")
    if any(x in lower for x in ("sky", "sr4sun", "sr4clo", "cloud", "background", "bg")):
        labels.add("skybox_background")
    if any(x in lower for x in ("merchant", "dmy_gate", "lgt_shop")) or category == "dummy_marker":
        labels.add("merchant_gate_marker")
    if category in {"model", "model_or_scene"} or any(x in lower for x in ("npc", "mdl_", "obj_", ".max", ".obj")):
        labels.add("npc_model_candidate")
    if category in {"texture"} or lower.endswith((".tm2", ".tim2", ".bmp", ".png", ".jpg", ".jpeg")) or name.startswith("TEX_"):
        labels.add("texture_candidate")
    return labels


def add_line_section(lines: list[str], title: str, values: list[str]) -> None:
    lines.extend(["", title, "=" * len(title)])
    if values:
        lines.extend(values)
    else:
        lines.append("(none)")


def build_catalog(input_path: Path, recursive: bool, focus: str) -> dict[str, object]:
    files = iter_inputs(input_path, recursive)
    entries = []
    by_file: dict[str, list[dict[str, object]]] = {}
    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    warnings: list[str] = []
    for path in files:
        try:
            findings = extract_identifiers_from_file(path)
        except Exception as exc:
            warnings.append(f"{path}: scan failed: {exc}")
            continue
        kept = []
        for finding in findings:
            name = str(finding.get("name", ""))
            if not in_focus(name, focus):
                continue
            explanation = explain_identifier(name)
            labels = sorted(classify(name, str(finding.get("likely_category", ""))))
            row = {**finding, "explanation": explanation, "labels": labels}
            kept.append(row)
            entries.append(row)
            for label in labels:
                buckets[label].append(row)
            if explanation.get("confidence") == "low":
                warnings.append(f"Uncertain label: {name} in {path}")
        by_file[str(path)] = kept
    groups = defaultdict(list)
    for row in buckets.get("npc_model_candidate", []):
        base = Path(str(row["name"])).stem.lower().replace("mdl_", "").replace("obj_", "")
        groups[base].append(row)
    return {"input": str(input_path), "recursive": recursive, "focus": focus, "file_count": len(files), "entry_count": len(entries), "by_file": by_file, "detected_ccsf_names": sorted({str(e["name"]) for e in entries if str(e["name"]).startswith("CCSF")}), "buckets": buckets, "model_swap_candidate_groups": {k: v for k, v in groups.items() if len(v) > 1}, "warnings": warnings}


def write_txt(catalog: dict[str, object], out_txt: Path) -> None:
    by_file = catalog["by_file"]
    buckets = catalog["buckets"]
    lines = ["CCS Asset Catalog", f"Input: {catalog['input']}", f"Focus: {catalog['focus']}", f"Files scanned: {catalog['file_count']}", f"Findings: {catalog['entry_count']}"]
    add_line_section(lines, "Summary by file", [f"{p}: {len(rows)} finding(s)" for p, rows in sorted(by_file.items())])
    add_line_section(lines, "Detected CCSF names", list(catalog["detected_ccsf_names"]))
    for title, key in [("Likely skybox/background assets", "skybox_background"), ("Likely merchant/gate markers", "merchant_gate_marker"), ("Likely NPC/model candidates", "npc_model_candidate"), ("Likely texture candidates", "texture_candidate")]:
        add_line_section(lines, title, [f"{r['name']} ({r['source']} @ 0x{int(r['offset']):X})" for r in buckets.get(key, [])])
    groups = catalog["model_swap_candidate_groups"]
    add_line_section(lines, "Model swap candidate groups", [f"{k}: " + ", ".join(str(r["name"]) for r in v) for k, v in sorted(groups.items())])
    add_line_section(lines, "Warnings/uncertain labels", list(catalog["warnings"]))
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, dest="input_path")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--focus", choices=["all", "town", "npc", "shop", "skybox"], default="all")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    catalog = build_catalog(args.input_path, args.recursive, args.focus)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, indent=2, sort_keys=True, default=list), encoding="utf-8", newline="\n")
    txt = args.out.with_suffix(".txt")
    write_txt(catalog, txt)
    print(f"Wrote {args.out}")
    print(f"Wrote {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

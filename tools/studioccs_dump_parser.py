#!/usr/bin/env python3
"""Parse StudioCCS text dumps into structured JSON.

The StudioCCS text dumper has had a few output shapes over time.  This module
therefore uses tolerant line-oriented parsing instead of depending on one exact
format.  It extracts summary counts, typed CCS object/name tables, model and
submodel counts, texture formats, clump/model counts, hierarchy-like parent
relationships, animation controllers, and notable HIT_/DMY_ scene helpers.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

_OBJECT_PREFIXES = ("OBJ", "MDL", "MOR", "MSH", "MAT", "TEX", "CLT", "CMP", "ANM", "HIT", "DMY", "LGT", "CAM", "EFF", "BOX", "MPH")
_LIST_FIELDS = {"sub_files", "sub_objects", "materials", "textures", "clumps", "animation_controllers", "hit_objects", "dummy_objects", "object_hierarchy"}

_VERSION_RE = re.compile(r"\b(?:version|ccs\s*version|file\s*version)\b\s*[:=]?\s*([\w.+-]+)", re.I)
_COUNT_RE = re.compile(r"\b(file|object|sub[-_ ]?file|sub[-_ ]?object|material|texture|clump|model|sub[-_ ]?model|animation\s*controller|controller)s?\s*(?:count)?\s*[:=]\s*(\d+)\b", re.I)
_ENTRY_RE = re.compile(r"\b((?:" + "|".join(_OBJECT_PREFIXES) + r")_[A-Za-z0-9][A-Za-z0-9_.$-]*)\b")
_TYPE_NAME_RE = re.compile(r"^\s*(?:[-*]\s*)?(sub[-_ ]?file|sub[-_ ]?object|material|texture|clump|model|sub[-_ ]?model|animation\s*controller|controller)\s*(?:\[[^\]]+\]|#?\d+)?\s*[:=\-]\s*(.+)$", re.I)
_SIZE_RE = re.compile(r"\b(\d{1,5})\s*x\s*(\d{1,5})\b", re.I)
_BITS_RE = re.compile(r"\b(4|8|16|24|32)\s*(?:-|\s)?bit\b", re.I)
_PARENT_RE = re.compile(r"\bparent\b\s*[:=]\s*([A-Za-z0-9_.$-]+)", re.I)
_CHILD_RE = re.compile(r"\bchild\b\s*[:=]\s*([A-Za-z0-9_.$-]+)", re.I)
_ARROW_RE = re.compile(r"\b([A-Za-z0-9_.$-]+)\s*(?:->|=>)\s*([A-Za-z0-9_.$-]+)\b")
_MODEL_SUB_RE = re.compile(r"\bsub[-_ ]?models?\b\s*[:=]?\s*(\d+)\b", re.I)
_CLUMP_MODELS_RE = re.compile(r"\bmodels?\b\s*[:=]\s*(\d+)\b", re.I)


def _blank_result() -> dict[str, Any]:
    return {
        "version": None,
        "file_count": None,
        "object_count": None,
        "counts": {},
        "sub_files": [],
        "sub_objects": [],
        "materials": [],
        "textures": [],
        "clumps": [],
        "models": [],
        "model_count": None,
        "submodel_count": None,
        "animation_controllers": [],
        "hit_objects": [],
        "dummy_objects": [],
        "object_hierarchy": [],
    }


def _dedupe_append(items: list[Any], item: Any) -> None:
    if isinstance(item, dict) and "name" in item:
        for existing in items:
            if isinstance(existing, dict) and existing.get("name") == item["name"]:
                existing.update(item)
                return
    if item not in items:
        items.append(item)


def _name_from_tail(tail: str) -> str:
    match = _ENTRY_RE.search(tail)
    if match:
        return match.group(1)
    quoted = re.search(r"['\"]([^'\"]+)['\"]", tail)
    if quoted:
        return quoted.group(1).strip()
    return tail.strip().split()[0].strip(",;()[]") if tail.strip() else ""


def _texture_entry(name: str, line: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name}
    size = _SIZE_RE.search(line)
    if size:
        entry["width"] = int(size.group(1))
        entry["height"] = int(size.group(2))
    bits = _BITS_RE.search(line)
    if bits:
        entry["bits_per_pixel"] = int(bits.group(1))
    lower = line.lower()
    if "indexed" in lower or "palette" in lower or "paletted" in lower:
        entry["indexed"] = True
    if "rgba" in lower:
        entry["format"] = "RGBA"
    elif "indexed" in lower:
        entry["format"] = f"{entry.get('bits_per_pixel', '')}-bit indexed".strip()
    return entry


def parse_studioccs_dump(text: str) -> dict[str, Any]:
    """Parse StudioCCS text dump *text* and return a JSON-serializable dict."""
    result = _blank_result()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        version = _VERSION_RE.search(line)
        if version and result["version"] is None:
            result["version"] = version.group(1)

        for label, value in _COUNT_RE.findall(line):
            key = label.lower().replace(" ", "_").replace("-", "_")
            count = int(value)
            result["counts"][key] = count
            if key == "file":
                result["file_count"] = count
            elif key == "object":
                result["object_count"] = count
            elif key == "model" and re.search(r"\bmodel\s+count\b", line, re.I):
                result["model_count"] = count
            elif key == "sub_model" and re.search(r"\bsub[-_ ]?model\s+count\b", line, re.I):
                result["submodel_count"] = count

        typed = _TYPE_NAME_RE.match(line)
        if typed:
            kind = typed.group(1).lower().replace(" ", "_").replace("-", "_")
            name = _name_from_tail(typed.group(2))
            if name:
                if kind == "texture":
                    _dedupe_append(result["textures"], _texture_entry(name, line))
                elif kind in {"controller", "animation_controller"}:
                    _dedupe_append(result["animation_controllers"], {"name": name})
                elif kind == "sub_model":
                    _dedupe_append(result["models"], {"name": name, "kind": "submodel"})
                else:
                    field = f"{kind}s"
                    if field in _LIST_FIELDS:
                        _dedupe_append(result[field], {"name": name})

        names = _ENTRY_RE.findall(line)
        for name in names:
            prefix = name.split("_", 1)[0]
            if prefix == "HIT":
                _dedupe_append(result["hit_objects"], name)
            elif prefix == "DMY":
                _dedupe_append(result["dummy_objects"], name)
            elif prefix == "MAT":
                _dedupe_append(result["materials"], {"name": name})
            elif prefix in {"TEX", "CLT"} or "texture" in line.lower():
                _dedupe_append(result["textures"], _texture_entry(name, line))
            elif prefix == "CMP" or "clump" in line.lower():
                entry: dict[str, Any] = {"name": name}
                model_count = _CLUMP_MODELS_RE.search(line)
                if model_count:
                    entry["model_count"] = int(model_count.group(1))
                _dedupe_append(result["clumps"], entry)
            elif prefix == "MDL":
                entry = {"name": name}
                submodels = _MODEL_SUB_RE.search(line)
                if submodels:
                    entry["submodel_count"] = int(submodels.group(1))
                _dedupe_append(result["models"], entry)

        arrow = _ARROW_RE.search(line)
        if arrow:
            _dedupe_append(result["object_hierarchy"], {"parent": arrow.group(1), "child": arrow.group(2)})
        elif names:
            parent = _PARENT_RE.search(line)
            child = _CHILD_RE.search(line)
            if parent or child:
                _dedupe_append(result["object_hierarchy"], {"object": names[0], "parent": parent.group(1) if parent else None, "child": child.group(1) if child else None})

    if result["model_count"] is None and result["models"]:
        result["model_count"] = len([m for m in result["models"] if m.get("kind") != "submodel"])
    if result["submodel_count"] is None:
        total = sum(int(m.get("submodel_count", 0)) for m in result["models"])
        if total:
            result["submodel_count"] = total
    return result


def _read_input(path: str | None) -> str:
    if path in {None, "-"}:
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a StudioCCS text dump and emit JSON.")
    parser.add_argument("input", nargs="?", help="StudioCCS dump text file, or stdin when omitted/-")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args(list(argv) if argv is not None else None)

    parsed = parse_studioccs_dump(_read_input(args.input))
    json.dump(parsed, sys.stdout, indent=2 if args.pretty else None, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

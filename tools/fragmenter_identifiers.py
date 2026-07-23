#!/usr/bin/env python3
"""Identifier and asset-reference extraction for Fragmenter workbench scans."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

IDENTIFIER_PREFIXES = ("CCSF", "OBJ_", "MDL_", "TEX_", "MAT_", "DMY_", "ANM_", "LGT_", "CLT_", "BLT_", "CMP_", "HIT_")
PATH_EXTENSIONS = ("max", "bmp", "tm2", "tim2", "anm", "obj", "png", "jpg", "jpeg")
IDENTIFIER_RE = re.compile(rb"(?<![A-Za-z0-9_])(?:CCSF[A-Za-z0-9_]*|(?:OBJ|MDL|TEX|MAT|DMY|ANM|LGT|CLT|BLT|CMP|HIT)_[A-Za-z0-9_./-]+)")
PATH_RE = re.compile(rb"(?i)(?<![A-Za-z0-9_./\\-])(?:[A-Za-z0-9_.-]+[/\\])*[A-Za-z0-9_.-]+\.(?:max|bmp|tm2|tim2|anm|obj|png|jpg|jpeg)(?![A-Za-z0-9_])")


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip("\x00")


def _context(data: bytes, start: int, end: int, radius: int = 32) -> str:
    return _decode(data[max(0, start - radius):min(len(data), end + radius)]).replace("\x00", " ")


def likely_category(value: str) -> str:
    lower = value.lower()
    if value.startswith("CCSF") or lower.endswith(".cmp"):
        return "ccs_container"
    if value.startswith("OBJ_") or lower.endswith((".obj", ".max")):
        return "model_or_scene"
    if value.startswith("MDL_"):
        return "model"
    if value.startswith("TEX_") or lower.endswith((".bmp", ".tm2", ".tim2", ".png", ".jpg", ".jpeg")):
        return "texture"
    if value.startswith("MAT_"):
        return "material"
    if value.startswith("DMY_"):
        return "dummy_marker"
    if value.startswith("ANM_") or lower.endswith(".anm"):
        return "animation"
    if value.startswith("LGT_"):
        return "light"
    if value.startswith("CLT_"):
        return "collision_or_client"
    if value.startswith("BLT_"):
        return "built_asset"
    if value.startswith("CMP_"):
        return "compressed_or_component"
    if value.startswith("HIT_"):
        return "hit_collision"
    return "path_reference"


def extract_identifiers(data: bytes | str, source: str = "<memory>") -> list[dict[str, object]]:
    blob = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
    findings: dict[tuple[int, str], dict[str, object]] = {}
    for kind, pattern, confidence in (("identifier", IDENTIFIER_RE, "high"), ("path", PATH_RE, "medium")):
        for match in pattern.finditer(blob):
            text = _decode(match.group(0))
            key = (match.start(), text)
            findings[key] = {
                "offset": match.start(),
                "source": source,
                "name": text,
                "context": _context(blob, match.start(), match.end()),
                "confidence": confidence if kind == "path" or len(text) > 4 else "medium",
                "likely_category": likely_category(text),
            }
    return sorted(findings.values(), key=lambda row: (int(row["offset"]), str(row["name"])))


def extract_identifiers_from_file(path: str | Path) -> list[dict[str, object]]:
    p = Path(path)
    return extract_identifiers(p.read_bytes(), str(p))


def _main() -> None:
    parser = argparse.ArgumentParser(description="Extract Fragmenter identifiers and path-like asset references.")
    parser.add_argument("path")
    args = parser.parse_args()
    print(json.dumps(extract_identifiers_from_file(args.path), indent=2))


if __name__ == "__main__":
    _main()

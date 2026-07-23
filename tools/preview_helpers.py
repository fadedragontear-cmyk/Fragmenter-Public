#!/usr/bin/env python3
from __future__ import annotations

import shlex
from pathlib import Path

SYMBOL_PREFIXES = ("MDL_", "TEX_", "MAT_", "ANM_", "DMY_", "CAM_")
IMAGE_EXTS = {".png", ".bmp", ".jpg", ".jpeg", ".gif"}


def normalize_symbol(symbol: str) -> str:
    raw = (symbol or "").strip()
    upper = raw.upper()
    for pfx in SYMBOL_PREFIXES:
        if upper.startswith(pfx):
            return raw[len(pfx) :]
    return raw


def suggested_iso_queries(family: str, symbol: str, related_paths: list[str] | None = None) -> list[str]:
    queries: list[str] = []
    fam = (family or "").strip().lower()
    sym = normalize_symbol(symbol).strip().lower()
    if fam:
        queries.append(fam)
    if sym and sym not in queries:
        queries.append(sym)
    for p in related_paths or []:
        base = Path(str(p).replace("\\", "/")).name
        stem = base.split(".", 1)[0].strip().lower()
        if stem and stem not in queries:
            queries.append(stem)
    return queries[:12]


def build_viewer_command(target: Path, viewer_path: str, args_template: str) -> list[str]:
    base = (viewer_path or "").strip()
    if not base:
        return []
    cmd = [base]
    template = (args_template or "").strip()
    if template:
        replaced = template.replace("{path}", str(target))
        cmd.extend(shlex.split(replaced))
    else:
        cmd.append(str(target))
    return cmd


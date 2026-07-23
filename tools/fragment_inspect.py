#!/usr/bin/env python3
r"""
fragment_inspect.py - quick "what's inside?" inspector for .hack//frägment Area Server CCSF containers.

Works on:
  - town.bin (or other *.bin)  [gzipped]
  - extracted CCSF section files (*.ccsf) from fragment_unpack.py

It prints:
  - Embedded asset path list (e.g., s/r/4/tex/sr4clo1.bmp)
  - Named resources like TEX_*, MDL_*, MAT_*, DMY_* (markers you can target)
  - Quick counts and a few "high impact" texture suggestions for Fort Ouph (town04)

Usage (from your area server folder):
  py fragment_inspect.py data/town.bin --section CCSFtown04
  py fragment_inspect.py out_town/town_0XX_CCSFtown04.ccsf

Tip:
  Fort Ouph is CCSFtown04 / CCSFtown04d.
"""
from __future__ import annotations
import argparse
from pathlib import Path

from fragment_core import PREFIXES, get_section as get_named_section, parse_asset_paths, read_maybe_gzip, scan_ascii_strings

def summarize_prefix(strings, prefixes):
    out={}
    for pfx in prefixes:
        out[pfx] = sorted(set(s for s in strings if s.startswith(pfx)))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="town.bin (gz) OR an extracted .ccsf section file")
    ap.add_argument("--section", help="If input is a .bin, choose section name like CCSFtown04")
    ap.add_argument("--max-list", type=int, default=40, help="Max items to print per category")
    args = ap.parse_args()

    p = Path(args.path)
    blob, was_gz = read_maybe_gzip(p)

    if args.section:
        section = get_named_section(blob, args.section)[1]
        label = f"{p.name}::{args.section}"
    else:
        section = blob
        label = p.name

    strings = scan_ascii_strings(section, minlen=4)
    paths = parse_asset_paths(section)

    print("="*80)
    print(f"Inspect: {label}")
    print(f"Bytes: {len(section):,}")
    if args.section:
        print(f"Source gzipped: {'yes' if was_gz else 'no'}")
    print("="*80)

    if paths:
        print("\n[Asset path list] (usually file refs inside this section)")
        for s in paths[:args.max_list]:
            print(" ", s)
        if len(paths) > args.max_list:
            print(f"  ... ({len(paths)-args.max_list} more)")
    else:
        print("\n[Asset path list] none detected")

    by = summarize_prefix(strings, PREFIXES)

    for pfx in PREFIXES:
        items = by[pfx]
        if not items:
            continue
        print(f"\n[{pfx} names]  count={len(items)}")
        for s in items[:args.max_list]:
            print(" ", s)
        if len(items) > args.max_list:
            print(f"  ... ({len(items)-args.max_list} more)")

    # Fort Ouph helper hints
    if "CCSFtown04" in label:
        print("\n[Fort Ouph quick hits]")
        hi = [x for x in by["TEX_"] if x.lower().startswith("tex_sr4")]
        print(" Textures that are usually high-impact to reskin for a new vibe:")
        for s in hi[:30]:
            print("  ", s)
        print("\n Markers that smell like 'shops/interaction':")
        for m in sorted(set(x for x in by["DMY_"] if ("merchant" in x.lower() or "sav" in x.lower() or "wep" in x.lower() or "ite" in x.lower() or "mag" in x.lower() or x.lower()=="dmy_gate"))):
            print("  ", m)

if __name__ == "__main__":
    main()

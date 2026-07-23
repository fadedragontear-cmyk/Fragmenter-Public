#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from iso9660 import Iso9660, normalize_path

def main():
    ap = argparse.ArgumentParser(description="Extract one file from a PS2 ISO by internal path.")
    ap.add_argument("iso_path", type=Path)
    ap.add_argument("internal_path", type=str, help="e.g. s/r/4/tex/sr4bac1.bmp")
    ap.add_argument("--out", type=Path, required=True, help="output file path")
    args = ap.parse_args()

    internal_path = normalize_path(args.internal_path)
    iso = Iso9660(args.iso_path)
    ok = iso.extract(internal_path, args.out)
    if not ok:
        raise SystemExit(f"Not found in ISO: {internal_path}")
    print("Extracted:", args.out)

if __name__ == "__main__":
    main()

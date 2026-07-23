#!/usr/bin/env python3
r"""
Installs a patched .bin into the Area Server data folder, making a timestamped backup.

Usage:
  py tools/fragmenter_install.py town_patched.bin --data-dir "C:/.../data" --original-name town.bin
"""
from __future__ import annotations
import argparse, shutil, time
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patched_bin", type=Path)
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--original-name", required=True)
    args = ap.parse_args()

    data_dir = args.data_dir
    orig = data_dir / args.original_name
    patched = args.patched_bin

    if not data_dir.exists():
        raise SystemExit(f"Data dir not found: {data_dir}")
    if not orig.exists():
        raise SystemExit(f"Original file not found: {orig}")
    if not patched.exists():
        raise SystemExit(f"Patched file not found: {patched}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = data_dir / "_fragmenter_backups"
    backup_dir.mkdir(exist_ok=True)

    backup_path = backup_dir / f"{args.original_name}.{stamp}.bak"
    shutil.copy2(orig, backup_path)
    shutil.copy2(patched, orig)

    print("Backed up:", backup_path)
    print("Installed:", orig)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
areadata_diff.py
Binary diff helper for .hack//frägment Area Server save files:
  save/AreaData%02d.dat
  save/Areakif%02d.dat

Goal: you make ONE small edit in the Area Server map editor, then compare "before" vs "after".
This script prints:
  - changed ranges
  - nearby bytes
  - and tries to interpret changed 4-byte words as little-endian floats/ints.

Usage:
  py tools\areadata_diff.py before.dat after.dat --context 64

Tip:
  Start with a tiny change (move one NPC a little, or toggle one object).
"""
from __future__ import annotations
import argparse, struct, math
from pathlib import Path

def is_reasonable_float(f: float) -> bool:
    return math.isfinite(f) and abs(f) < 1e6 and not (abs(f) < 1e-12)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--context", type=int, default=48)
    ap.add_argument("--max", type=int, default=50, help="max change blocks")
    args = ap.parse_args()

    a = args.before.read_bytes()
    b = args.after.read_bytes()
    if len(a) != len(b):
        print(f"Size differs: before={len(a)} after={len(b)} (still diffing overlapping region)")
    n = min(len(a), len(b))

    # find change blocks
    changes=[]
    i=0
    while i<n:
        if a[i] != b[i]:
            start=i
            i+=1
            while i<n and a[i] != b[i]:
                i+=1
            end=i
            changes.append((start,end))
        else:
            i+=1

    # merge close blocks
    merged=[]
    for s,e in changes:
        if not merged or s - merged[-1][1] > 8:
            merged.append([s,e])
        else:
            merged[-1][1] = e
    merged = [(s,e) for s,e in merged]

    print(f"Found {len(merged)} changed block(s). Showing up to {args.max}.")
    for idx,(s,e) in enumerate(merged[:args.max], 1):
        cs = max(0, s-args.context)
        ce = min(n, e+args.context)
        print("\n" + "="*80)
        print(f"Block {idx}: offset 0x{s:08X}..0x{e:08X}  (len={e-s})")
        # show hex diff line-by-line (16 bytes)
        for off in range(cs, ce, 16):
            line_a = a[off:off+16]
            line_b = b[off:off+16]
            marker = "".join("^" if (off+j>=s and off+j<e and j < len(line_a) and j < len(line_b)) and line_a[j]!=line_b[j] else " " for j in range(16))
            ha = " ".join(f"{x:02X}" for x in line_a)
            hb = " ".join(f"{x:02X}" for x in line_b)
            print(f"{off:08X}  {ha:<47}  |  {hb:<47}")
            if marker.strip():
                print(f"          {marker}")

        # try interpret changed region as 4-byte words
        print("\nInterpretation guesses (little-endian 32-bit words within changed range):")
        shown=0
        for off in range(s - (s%4), e, 4):
            if off < 0 or off+4 > n: 
                continue
            wa = a[off:off+4]
            wb = b[off:off+4]
            if wa == wb:
                continue
            ia = struct.unpack("<I", wa)[0]
            ib = struct.unpack("<I", wb)[0]
            fa = struct.unpack("<f", wa)[0]
            fb = struct.unpack("<f", wb)[0]
            parts=[]
            parts.append(f"0x{off:08X}: {wa.hex().upper()} -> {wb.hex().upper()}")
            parts.append(f"u32 {ia} -> {ib}")
            if is_reasonable_float(fa) or is_reasonable_float(fb):
                parts.append(f"f32 {fa:.6g} -> {fb:.6g}")
            print("  " + " | ".join(parts))
            shown += 1
            if shown >= 20:
                break

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
r"""
shop_probe.py

Goal: help reverse-engineer shop inventory format inside save/AreaDataXX.dat and save/AreakifXX.dat.

This does NOT assume a known format. It uses BEFORE/AFTER pairs and looks for:
- changed ranges
- likely 16-bit little-endian "IDs" that changed
- patterns that look like small arrays/lists

Usage:
  py tools/shop_probe.py --before AreaData01_before.dat --after AreaData01_after.dat --out shop_probe_AreaData.json
  py tools/shop_probe.py --before Areakif01_before.dat  --after Areakif01_after.dat  --out shop_probe_Areakif.json
"""
from __future__ import annotations
import argparse, json, struct, hashlib
from pathlib import Path

def sha1(b: bytes) -> str:
    h=hashlib.sha1(); h.update(b); return h.hexdigest()

def diff_ranges(a: bytes, b: bytes, merge_gap=16):
    n=min(len(a), len(b))
    ranges=[]
    i=0
    while i<n:
        if a[i]==b[i]:
            i+=1; continue
        start=i
        while i<n and a[i]!=b[i]:
            i+=1
        ranges.append((start, i-start))
    merged=[]
    for s,l in ranges:
        if not merged:
            merged.append([s,l]); continue
        ps,pl=merged[-1]
        if s <= ps+pl+merge_gap:
            end=max(ps+pl, s+l)
            merged[-1][1]=end-ps
        else:
            merged.append([s,l])
    return [(s,l) for s,l in merged]

def iter_u16_le(data: bytes, off: int, ln: int):
    # yields (pos, value)
    end = off + ln
    pos = off
    while pos + 2 <= end:
        yield pos, struct.unpack_from("<H", data, pos)[0]
        pos += 2

def iter_u32_le(data: bytes, off: int, ln: int):
    end = off + ln
    pos = off
    while pos + 4 <= end:
        yield pos, struct.unpack_from("<I", data, pos)[0]
        pos += 4

def probe(before: bytes, after: bytes, ranges):
    changes=[]
    for off, ln in ranges:
        b0 = before[off:off+ln]
        b1 = after[off:off+ln]

        # u16 deltas
        u16=[]
        for pos, v0 in iter_u16_le(before, off, ln):
            v1 = struct.unpack_from("<H", after, pos)[0]
            if v0 != v1:
                u16.append({"pos": pos, "before": v0, "after": v1})
        # u32 deltas
        u32=[]
        for pos, v0 in iter_u32_le(before, off, ln):
            v1 = struct.unpack_from("<I", after, pos)[0]
            if v0 != v1:
                u32.append({"pos": pos, "before": v0, "after": v1})

        changes.append({
            "offset": off,
            "length": ln,
            "u16_changes": u16[:200],  # cap
            "u32_changes": u32[:120],
            "u16_change_count": len(u16),
            "u32_change_count": len(u32),
        })
    return changes

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--before", required=True, type=Path)
    ap.add_argument("--after", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args=ap.parse_args()

    before=args.before.read_bytes()
    after=args.after.read_bytes()

    ranges = diff_ranges(before, after)
    report={
        "before": str(args.before),
        "after": str(args.after),
        "before_sha1": sha1(before),
        "after_sha1": sha1(after),
        "len_before": len(before),
        "len_after": len(after),
        "changed_ranges": [{"offset": s, "length": l} for s,l in ranges],
        "changed_range_count": len(ranges),
        "bytes_changed_total": sum(l for _,l in ranges),
        "analysis": probe(before, after, ranges),
        "notes": [
            "For clean shop decoding: make ONE shop change between before/after.",
            "Look for a change block where many u16 values change (item IDs) but file length stays same.",
            "If only a few u16s change, you probably edited a single slot (ideal)."
        ]
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Wrote:", args.out.resolve())

if __name__=="__main__":
    main()

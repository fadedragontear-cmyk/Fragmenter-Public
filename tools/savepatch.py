#!/usr/bin/env python3
r"""
savepatch.py

Create and apply byte-level patches for AreaData/Areakif files.
Format-agnostic editor: record a change, then re-apply it safely.

Create:
  py tools/savepatch.py create --before AreaData01_before.dat --after AreaData01_after.dat --out patch.json

Apply:
  py tools/savepatch.py apply --patch patch.json --target AreaData01.dat

Default apply checks that target bytes match the "before" bytes at each range.
Use --force to apply even if mismatch (not recommended).
"""
from __future__ import annotations
import argparse, base64, json, hashlib
from pathlib import Path

def sha1(b: bytes) -> str:
    h=hashlib.sha1(); h.update(b); return h.hexdigest()

def diff_ranges(a: bytes, b: bytes):
    n=min(len(a), len(b))
    ranges=[]
    i=0
    while i<n:
        if a[i]==b[i]:
            i+=1
            continue
        start=i
        while i<n and a[i]!=b[i]:
            i+=1
        ranges.append((start, i-start))
    # We ignore resizing differences for safety.
    # Merge close ranges to reduce fragmentation.
    merged=[]
    for start, ln in ranges:
        if not merged:
            merged.append([start, ln]); continue
        ps, pl = merged[-1]
        if start <= ps+pl+16:
            end = max(ps+pl, start+ln)
            merged[-1][1] = end-ps
        else:
            merged.append([start, ln])
    return [(s,l) for s,l in merged]

def create_patch(before_path: Path, after_path: Path, out_path: Path):
    before=before_path.read_bytes()
    after=after_path.read_bytes()
    ranges = diff_ranges(before, after)
    safe=[(s,l) for s,l in ranges if s+l <= min(len(before), len(after))]
    patch={
        "version": 1,
        "before_file": before_path.name,
        "after_file": after_path.name,
        "before_sha1": sha1(before),
        "after_sha1": sha1(after),
        "length": len(before),
        "ranges": [],
    }
    for start, ln in safe:
        b0 = before[start:start+ln]
        b1 = after[start:start+ln]
        patch["ranges"].append({
            "offset": start,
            "length": ln,
            "before_b64": base64.b64encode(b0).decode("ascii"),
            "after_b64": base64.b64encode(b1).decode("ascii"),
        })
    out_path.write_text(json.dumps(patch, indent=2), encoding="utf-8")
    return patch

def apply_patch(patch_path: Path, target_path: Path, force: bool=False, backup: bool=True):
    patch=json.loads(patch_path.read_text(encoding="utf-8"))
    data=bytearray(target_path.read_bytes())
    if backup:
        bak = target_path.with_suffix(target_path.suffix + ".bak")
        bak.write_bytes(bytes(data))
    for r in patch["ranges"]:
        off=r["offset"]; ln=r["length"]
        b_before = base64.b64decode(r["before_b64"])
        b_after  = base64.b64decode(r["after_b64"])
        cur = bytes(data[off:off+ln])
        if (not force) and cur != b_before:
            raise SystemExit(f"Mismatch at 0x{off:X} len {ln}: target bytes differ from patch BEFORE bytes. Use --force to override.")
        data[off:off+ln] = b_after
    target_path.write_bytes(bytes(data))
    return True

def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest="cmd", required=True)

    c=sp.add_parser("create")
    c.add_argument("--before", required=True, type=Path)
    c.add_argument("--after", required=True, type=Path)
    c.add_argument("--out", required=True, type=Path)

    a=sp.add_parser("apply")
    a.add_argument("--patch", required=True, type=Path)
    a.add_argument("--target", required=True, type=Path)
    a.add_argument("--force", action="store_true")
    a.add_argument("--no-backup", action="store_true")

    args=ap.parse_args()
    if args.cmd=="create":
        p=create_patch(args.before, args.after, args.out)
        print("Wrote patch:", args.out.resolve())
        print("Ranges:", len(p["ranges"]))
    elif args.cmd=="apply":
        apply_patch(args.patch, args.target, force=args.force, backup=not args.no_backup)
        print("Patched:", args.target.resolve())

if __name__=="__main__":
    main()

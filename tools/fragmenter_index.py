#!/usr/bin/env python3
r"""
fragmenter_index.py

Creates a fast index of Area Server data files:
- detects gzip
- enumerates CCSF sections
- extracts summary metadata per section:
    * size, offsets
    * asset-path count (32-byte slots table heuristic)
    * counts of TEX_/MDL_/DMY_/MAT_/ANM_/CAM_ symbols
    * a few sample asset paths

Outputs JSON for use by Fragmenter GUI/CLI.

Usage:
  py tools\\\fragmenter_index.py r"C:\\\\\...\data" --out index.json
  py tools\\\fragmenter_index.py r"C:\\\\\...\data\\town.bin" --out town_index.json
"""
from __future__ import annotations
import argparse, struct, json, time, hashlib
from pathlib import Path

from fragment_core import PREFIXES, read_maybe_gzip, scan_ascii_strings, split_sections

def sha1_bytes(b: bytes) -> str:
    h = hashlib.sha1()
    h.update(b)
    return h.hexdigest()

def find_asset_paths(section: bytes):
    # Heuristic: locate a type=2 block with 0xCCCC and payload containing " s\\"
    best=None
    for i in range(0, len(section)-8):
        t, mark = struct.unpack_from("<HH", section, i)
        if t != 2 or mark != 0xCCCC:
            continue
        ln = struct.unpack_from("<I", section, i+4)[0]
        start = i + 8
        end = start + ln
        if end > len(section):
            continue
        payload = section[start:end]
        if b" s\\" in payload and (best is None or len(payload) > len(best)):
            best = payload
    if not best or len(best) < 0x24:
        return []

    try:
        count = struct.unpack_from("<I", best, 0)[0]
    except Exception:
        return []
    table_off = 0x20
    slot_size = 32
    if table_off + count*slot_size > len(best):
        count = (len(best) - table_off) // slot_size

    out=set()
    for i in range(count):
        slot = best[table_off + i*slot_size : table_off + (i+1)*slot_size]
        j=0
        while j < len(slot) and slot[j] == 0:
            j += 1
        s = slot[j:].split(b"\x00")[0].decode("ascii", errors="ignore")
        if s.startswith(" s\\"):
            out.add(s)
    return sorted(out)

def summarize_section(sec_bytes: bytes):
    strings = scan_ascii_strings(sec_bytes, minlen=4)
    by={p:set() for p in PREFIXES}
    for s in strings:
        for p in PREFIXES:
            if s.startswith(p):
                by[p].add(s)
    counts = {p: len(by[p]) for p in PREFIXES}
    paths = find_asset_paths(sec_bytes)
    return {
        "size": len(sec_bytes),
        "sha1": sha1_bytes(sec_bytes),
        "asset_paths_count": len(paths),
        "asset_paths_sample": paths[:12],
        "counts": counts,
        "tops": {p: sorted(list(by[p]))[:12] for p in PREFIXES if by[p]},
    }

def index_file(path: Path):
    raw = path.read_bytes()
    blob, gz = read_maybe_gzip(path)
    sections = split_sections(blob)
    file_info = {
        "file": str(path),
        "name": path.name,
        "gzip": gz,
        "raw_size": path.stat().st_size,
        "raw_sha1": sha1_bytes(raw),
        "decompressed_size": len(blob),
        "section_count": len(sections),
        "sections": [],
    }
    for idx, sid, off, end in sections:
        sec_bytes = blob[off:end]
        summary = summarize_section(sec_bytes)
        file_info["sections"].append({
            "index": idx,
            "id": sid,
            "offset": off,
            "end": end,
            **summary,
        })
    return file_info

def iter_targets(target: Path):
    if target.is_dir():
        yield from sorted(target.glob("*.bin"))
        yield from sorted(target.glob("*.dat"))
    else:
        yield target

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", type=Path, help="data folder OR a .bin/.dat file")
    ap.add_argument("--out", type=Path, default=Path("fragmenter_index.json"))
    args = ap.parse_args()

    out = {"created_utc": time.time(), "target": str(args.target), "files": []}
    for p in iter_targets(args.target):
        try:
            out["files"].append(index_file(p))
        except Exception as e:
            out["files"].append({"file": str(p), "name": p.name, "error": str(e)})

    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Wrote index:", args.out.resolve())

if __name__ == "__main__":
    main()

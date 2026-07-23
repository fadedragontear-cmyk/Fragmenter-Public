#!/usr/bin/env python3

import argparse
from pathlib import Path

from fragment_core import read_maybe_gzip, split_sections as split_ccsf

def ungzip(path: Path) -> bytes:
    data, _gz = read_maybe_gzip(path)
    return data

def extract_strings(seg: bytes, minlen: int = 8, limit: int = 50):
    out = []
    cur = bytearray()
    start = None
    for i, b in enumerate(seg):
        if 32 <= b < 127:
            if start is None:
                start = i
            cur.append(b)
        else:
            if start is not None and len(cur) >= minlen:
                out.append((start, cur.decode("ascii", errors="ignore")))
                if len(out) >= limit:
                    break
            cur.clear()
            start = None
    return out

def main():
    ap = argparse.ArgumentParser(description="Unpack .hack//fragment fan server .bin files (gzip -> CCSF sections).")
    ap.add_argument("input", type=Path, help="Input .bin/.dat file")
    ap.add_argument("--out", type=Path, default=Path("out_sections"), help="Output folder")
    ap.add_argument("--list", action="store_true", help="Only list sections (don’t write files)")
    ap.add_argument("--strings", action="store_true", help="Print some ASCII strings per section (quick sanity check)")
    args = ap.parse_args()

    blob = ungzip(args.input)
    sections = split_ccsf(blob)

    if not sections:
        print("No CCSF sections found. (File might be encrypted or a different format.)")
        return

    print(f"{args.input.name}: {len(sections)} CCSF section(s) found.")
    for idx, sec_id, off, end in sections:
        print(f"  [{idx:03d}] {sec_id:<16}  offset=0x{off:08X}  size={end-off}")

    if args.list:
        return

    args.out.mkdir(parents=True, exist_ok=True)
    for idx, sec_id, off, end in sections:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in sec_id)
        outpath = args.out / f"{args.input.stem}_{idx:03d}_{safe}.ccsf"
        outpath.write_bytes(blob[off:end])

        if args.strings:
            seg = blob[off:end]
            for pos, s in extract_strings(seg, minlen=10, limit=10):
                print(f"    0x{off+pos:08X}: {s}")

    print(f"Wrote {len(sections)} section file(s) to: {args.out.resolve()}")

if __name__ == "__main__":
    main()

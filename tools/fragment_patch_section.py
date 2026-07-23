#!/usr/bin/env python3
r"""
fragment_patch_section.py - patch a CCSF section inside a gzipped *.bin (like town.bin).

Example (Fort Ouph):
  1) Extract CCSFtown04 to a file, edit it with CCSF Asset Explorer, save as edited file.
  2) Patch it back in:

  py fragment_patch_section.py data/town.bin --section CCSFtown04 --replace out_town/CCSFtown04_edited.ccsf --out data/town_patched.bin

Then you can rename:
  data/town.bin -> town_backup.bin
  data/town_patched.bin -> town.bin

ALWAYS BACK UP FIRST.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

from fragment_core import read_maybe_gzip, split_sections, write_maybe_gzip

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin_path", help="Path to the .bin (usually gzipped), e.g. data\\town.bin")
    ap.add_argument("--section", required=True, help="Section name, e.g. CCSFtown04")
    ap.add_argument("--replace", required=True, help="Replacement CCSF section file (*.ccsf) produced by your editor")
    ap.add_argument("--out", required=True, help="Output patched .bin path")
    ap.add_argument("--report", type=Path, default=None, help="Optional path to write JSON summary")
    ap.add_argument("--dry-run", action="store_true", help="Compute summary only; do not write patched output.")
    args = ap.parse_args()

    bin_path = Path(args.bin_path)
    rep_path = Path(args.replace)
    out_path = Path(args.out)

    blob, was_gz = read_maybe_gzip(bin_path)
    rep = rep_path.read_bytes()

    if not rep.startswith(b"\x01\x00\xcc\xcc"):
        raise SystemExit("Replacement does not start with expected CCSF section header (01 00 CC CC). Did you pick the right file?")

    sections = split_sections(blob)
    match = [s for s in sections if s[1] == args.section]
    if not match:
        raise SystemExit(f"Section not found: {args.section}")

    idx, sid, off, end = match[0]
    existing_len = end - off
    replacement_len = len(rep)

    summary = {
        "operation": "patch_section",
        "dry_run": bool(args.dry_run),
        "input_bin": str(bin_path),
        "section": sid,
        "section_index": idx,
        "replacement_file": str(rep_path),
        "gzip": was_gz,
        "replacements": {
            "section_count": 1,
            "existing_section_bytes": existing_len,
            "replacement_section_bytes": replacement_len,
            "byte_delta": replacement_len - existing_len,
        },
        "output_bin": str(out_path),
        "would_write_output": not args.dry_run,
    }

    if not args.dry_run:
        patched = blob[:off] + rep + blob[end:]
        write_maybe_gzip(out_path, patched, was_gz)

    if args.report:
        args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()

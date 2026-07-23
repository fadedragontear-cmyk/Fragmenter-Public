#!/usr/bin/env python3
"""
fragment_reskin_section.py

Easy, safe-by-default change: reskin a town section by repointing its asset references.

Same-length replacements inside a CCSF section embedded in a .bin:
- \\r\\<from>\\  ->  \\r\\<to>\\
- optionally sr<from> -> sr<to>

Usage:
  py tools\\fragment_reskin_section.py data\\town.bin --section CCSFtown04 --from 4 --to 5 --out town_reskinned.bin --symbols
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

from fragment_core import read_maybe_gzip, split_sections, write_maybe_gzip

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('bin_path', type=Path)
    ap.add_argument('--section', required=True)
    ap.add_argument('--from', dest='from_id', required=True, type=int)
    ap.add_argument('--to', dest='to_id', required=True, type=int)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--symbols', action='store_true')
    ap.add_argument('--report', type=Path, default=None)
    ap.add_argument('--dry-run', action='store_true', help='Compute summary only; do not write patched output.')
    args=ap.parse_args()

    if not (0 <= args.from_id <= 9 and 0 <= args.to_id <= 9):
        raise SystemExit('Currently supports single-digit asset set numbers 0-9.')

    blob, was_gz = read_maybe_gzip(args.bin_path)
    sections = split_sections(blob)
    m = [s for s in sections if s[1] == args.section]
    if not m:
        raise SystemExit(f'Section not found: {args.section}')
    idx, sid, off, end = m[0]

    sec = bytearray(blob[off:end])
    before_len = len(sec)

    fd = str(args.from_id).encode('ascii')
    td = str(args.to_id).encode('ascii')

    pat_path = b'\\r\\' + fd + b'\\'
    rep_path = b'\\r\\' + td + b'\\'
    n_path = sec.count(pat_path)
    sec = sec.replace(pat_path, rep_path)

    n_sym = 0
    if args.symbols:
        pat_sym = b'sr' + fd
        rep_sym = b'sr' + td
        n_sym = sec.count(pat_sym)
        sec = sec.replace(pat_sym, rep_sym)

    if len(sec) != before_len:
        raise SystemExit('Internal error: section length changed. Aborting.')

    total_replacements = n_path + (n_sym if args.symbols else 0)
    summary = {
        'operation': 'reskin_section',
        'dry_run': bool(args.dry_run),
        'input_bin': str(args.bin_path),
        'section': sid,
        'section_index': idx,
        'section_len': before_len,
        'gzip': was_gz,
        'from': args.from_id,
        'to': args.to_id,
        'replacements': {
            'path_shard_count': n_path,
            'symbol_shard_count': n_sym if args.symbols else 0,
            'total': total_replacements,
        },
        'output_bin': str(args.out),
        'would_write_output': not args.dry_run,
        'notes': [
            'This repoints references only. Assets must exist on the client (ISO).',
            'If the server crashes, revert using your backup (Fragmenter install creates one).'
        ]
    }

    if not args.dry_run:
        patched = blob[:off] + bytes(sec) + blob[end:]
        write_maybe_gzip(args.out, patched, was_gz)

    if args.report:
        args.report.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()

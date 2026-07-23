#!/usr/bin/env python3
"""
Legacy compatibility wrapper for old fragment_iso.py commands.

Supported ISO implementation is now:
- tools/iso9660.py
- tools/iso_index.py
- tools/iso_extract.py

This wrapper keeps old command lines working while routing into the newer stack.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from iso9660 import Iso9660, normalize_path


def _warn_legacy() -> None:
    print("[LEGACY] fragment_iso.py is deprecated. Use iso_index.py / iso_extract.py.")


def cmd_index(iso_path: Path, out_path: Path) -> int:
    iso = Iso9660(iso_path).open()
    files = []
    for e in iso.iter_files():
        files.append({
            "path": e.path,
            "lba": e.lba,
            "size": e.size,
            "is_dir": bool(getattr(e, "is_dir", False)),
        })

    payload = {
        "iso": str(iso_path),
        "mode": iso.mode,
        "layout": {
            "sector_size": iso.sector_size,
            "data_offset": iso.data_offset,
            "lba_offset": getattr(iso, "lba_offset", 0),
        },
        "count": len(files),
        "files": files,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote ISO index ({len(files)} entries): {out_path}")
    return 0


def _normalize_requested_iso_path(internal_path: str) -> str:
    """Normalize legacy requested ISO paths before streaming extraction."""
    return normalize_path(internal_path)


def cmd_extract(iso_path: Path, internal_path: str, out_path: Path) -> int:
    normalized_path = _normalize_requested_iso_path(internal_path)
    iso = Iso9660(iso_path).open()
    ok = iso.extract(normalized_path, out_path)
    if not ok:
        raise SystemExit(f"Not found in ISO: {normalized_path}")
    print(f"Extracted: {normalized_path} -> {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_i = sub.add_parser("index", help="[legacy wrapper] build ISO file index")
    ap_i.add_argument("--iso", required=True, help="Path to PS2 ISO")
    ap_i.add_argument("--out", required=True, help="Output JSON")

    ap_e = sub.add_parser("extract", help="[legacy wrapper] extract file from ISO by path")
    ap_e.add_argument("--iso", required=True, help="Path to PS2 ISO")
    ap_e.add_argument("--file", required=True, help="File path inside ISO")
    ap_e.add_argument("--out", required=True, help="Output file path")
    ap_e.add_argument("--index", help="Ignored legacy index JSON path")

    args = ap.parse_args()
    _warn_legacy()

    if args.cmd == "index":
        return cmd_index(Path(args.iso), Path(args.out))
    if args.cmd == "extract":
        if args.index:
            print("[LEGACY] --index is ignored; extraction now streams through Iso9660")
        return cmd_extract(Path(args.iso), args.file, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

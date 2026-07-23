#!/usr/bin/env python3
"""Read-only, bounded ISO-side string scanner for client asset hints."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

KNOWN_TERMS = ["DATA.BIN", "CCSFtown04", "DMY_merchant", "sr4sun", "sr4clo", ".tm2", ".bmp", ".max"]
ASCII_RE = re.compile(rb"[ -~]{4,}")


def context(blob: bytes, start: int, end: int, radius: int = 48) -> str:
    return blob[max(0, start - radius):min(len(blob), end + radius)].decode("latin-1", errors="replace").replace("\x00", " ")


def probe(path: Path, max_bytes: int) -> dict[str, object]:
    size = path.stat().st_size
    limit = min(size, max_bytes)
    with path.open("rb") as f:
        data = f.read(limit)
    hits = []
    lower = data.lower()
    for term in KNOWN_TERMS:
        needle = term.lower().encode("latin-1")
        pos = 0
        while True:
            idx = lower.find(needle, pos)
            if idx == -1:
                break
            hits.append({"term": term, "offset": idx, "context": context(data, idx, idx + len(term))})
            pos = idx + 1
    strings = []
    for match in ASCII_RE.finditer(data):
        s = match.group(0).decode("latin-1", errors="replace")
        sl = s.lower()
        if any(t.lower().strip(".") in sl for t in KNOWN_TERMS) or sl.endswith((".tm2", ".bmp", ".max")) or "ccsf" in sl or "dmy_" in sl:
            strings.append({"offset": match.start(), "string": s[:240]})
    return {"path": str(path), "size": size, "scanned_bytes": limit, "read_only": True, "known_terms": KNOWN_TERMS, "hits": hits, "strings": strings[:1000], "truncated": size > limit}


def write_text_report(report: dict[str, object], path: Path) -> None:
    lines = [
        "ISO Client Probe",
        "================",
        f"Generated UTC: {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}",
        f"Input: {report.get('path')}",
        f"Size: {report.get('size')} bytes",
        f"Scanned bytes: {report.get('scanned_bytes')}",
        f"Read only: {report.get('read_only')}",
        f"Truncated: {report.get('truncated')}",
        "",
        "Known-term hits:",
    ]
    hits = report.get("hits") or []
    if hits:
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            lines.append(f"- {hit.get('term')} at {hit.get('offset')}: {hit.get('context')}")
    else:
        lines.append("- none")
    lines.extend(["", "Matching strings:"])
    strings = report.get("strings") or []
    if strings:
        for item in strings:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('offset')}: {item.get('string')}")
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--txt-out", type=Path, help="Text report path. Defaults to --out with a .txt suffix when --out is provided.")
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024, help="Maximum bytes to scan from the start of the ISO (default: 64 MiB)")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input file not found: {args.input}")
    report = probe(args.input, args.max_bytes)
    text = json.dumps(report, indent=2)
    txt_out = args.txt_out or (args.out.with_suffix(".txt") if args.out else None)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {args.out}")
    else:
        print(text)
    if txt_out:
        write_text_report(report, txt_out)
        print(f"Wrote {txt_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

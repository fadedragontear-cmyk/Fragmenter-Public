#!/usr/bin/env python3
"""Index extracted CCSF-like asset bundles."""
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Iterable

from ccsf_asset_inspector import PREFIXES, format_report, inspect_ccsf_asset

SCAN_EXTS = {".tmp", ".ccs", ".ccsf", ".bin"}
COUNT_COLS = ("MDL", "TEX", "CLT", "MAT", "ANM", "OBJ", "CMP", "DMY", "HIT")
DEFAULT_MAX_REPORT_ROWS = 200



def _matches_any(path: Path, patterns: Iterable[str], root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    name = path.name
    return any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern) for pattern in patterns)


def iter_candidates(folder: Path, includes: list[str] | None = None, excludes: list[str] | None = None):
    includes = includes or []
    excludes = excludes or []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_EXTS:
            continue
        if includes and not _matches_any(path, includes, folder):
            continue
        if excludes and _matches_any(path, excludes, folder):
            continue
        yield path


def readiness_flags(asset: dict[str, object]) -> str:
    groups = asset.get("groups") if isinstance(asset.get("groups"), dict) else {}
    if not asset.get("is_ccsf"):
        return "-"
    flags = []
    if groups.get("MDL") or groups.get("OBJ"):
        flags.append("M")
    if groups.get("TEX"):
        flags.append("T")
    if groups.get("CLT"):
        flags.append("C")
    if groups.get("MAT") or groups.get("TEX") or groups.get("CLT"):
        flags.append("MAT")
    if groups.get("ANM"):
        flags.append("A")
    if groups.get("HIT"):
        flags.append("HIT")
    return "/".join(flags) if flags else "metadata"


def index_folder(
    folder: str | Path,
    *,
    quiet: bool = False,
    limit: int | None = None,
    max_file_size: int | None = None,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
) -> dict[str, object]:
    root = Path(folder)
    candidates = list(iter_candidates(root, includes=includes, excludes=excludes))
    if limit is not None and limit < 0:
        raise ValueError("--limit must be non-negative")
    if max_file_size is not None and max_file_size < 0:
        raise ValueError("--max-file-size must be non-negative")

    assets = []
    skipped = 0
    scanned = 0
    limit_reached = False
    total = len(candidates)
    for idx, path in enumerate(candidates, start=1):
        if limit is not None and scanned >= limit:
            skipped += total - idx + 1
            limit_reached = True
            break
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        if max_file_size is not None and size is not None and size > max_file_size:
            skipped += 1
            if not quiet:
                print(f"Skipping {idx}/{total}: {path} ({size} bytes > {max_file_size})")
            continue

        scanned += 1
        if not quiet:
            print(f"Scanning {idx}/{total}: {path}")
        try:
            item = inspect_ccsf_asset(path)
        except OSError as exc:
            item = {"file": str(path), "name": path.stem, "size": size or 0, "is_ccsf": False, "error": str(exc), "counts": {}, "groups": {}, "type": "unknown", "variant": "", "readiness": "error"}
        if item.get("is_ccsf"):
            try:
                item["relative_file"] = str(Path(item["file"]).resolve().relative_to(root.resolve()))
            except ValueError:
                item["relative_file"] = str(path)
            assets.append(item)
            if not quiet:
                print(f"Found CCSF: {item.get('name')} {item.get('type')}")
    return {
        "folder": str(root),
        "asset_count": len(assets),
        "assets": assets,
        "files_considered": scanned,
        "files_skipped": skipped,
        "candidate_count": total,
        "limit_reached": limit_reached,
    }


def _limited_section(items, max_rows: int | None):
    items = list(items or [])
    if max_rows is None or max_rows < 0:
        return items, 0
    return items[:max_rows], max(0, len(items) - max_rows)


def format_index(index: dict[str, object], *, summary_only: bool = False, max_report_rows: int | None = DEFAULT_MAX_REPORT_ROWS) -> str:
    all_assets = list(index.get("assets") or [])
    assets, omitted_assets = _limited_section(all_assets, max_report_rows)
    lines = [f"CCSF Asset Index", f"Folder: {index.get('folder')}", f"Assets: {len(all_assets)}", f"Text row limit: {'unlimited' if max_report_rows is None or max_report_rows < 0 else max_report_rows}", ""]
    headers = ["CCSF name", "type", "variant", "file", "size", *COUNT_COLS, "ready"]
    widths = [24, 24, 8, 42, 10, 5, 5, 5, 5, 5, 5, 5, 5, 5, 16]
    def row(vals):
        return "  ".join(str(v)[:w].ljust(w) for v, w in zip(vals, widths)).rstrip()
    lines.append(row(headers))
    lines.append(row(["-" * w for w in widths]))
    for asset in assets:
        counts = asset.get("counts") or {}
        file_name = asset.get("relative_file") or asset.get("file")
        vals = [asset.get("name", ""), asset.get("type", ""), asset.get("variant", "") or "-", file_name, asset.get("size", 0)]
        vals.extend(counts.get(col, 0) for col in COUNT_COLS)
        vals.append(readiness_flags(asset))
        lines.append(row(vals))
    if omitted_assets:
        lines.append(f"... omitted {omitted_assets} additional asset rows; full data is available in JSON/JSONL output.")
    else:
        lines.append("Omitted asset rows: 0")
    if not summary_only:
        details, omitted_details = _limited_section(all_assets, max_report_rows)
        lines.append("")
        lines.append(f"Details (showing {len(details)} of {len(all_assets)}; omitted {omitted_details}):")
        for asset in details:
            lines.append("")
            lines.append(format_report(asset).rstrip())
    return "\n".join(lines) + "\n"


def write_index(index: dict[str, object], out: str | None, text_out: str | None, *, summary_only: bool = False, max_report_rows: int | None = DEFAULT_MAX_REPORT_ROWS, jsonl_out: str | None = None) -> tuple[Path, Path]:
    out_path = Path(out) if out else Path("ccsf_asset_index.json")
    text_path = Path(text_out) if text_out else Path("ccsf_asset_index.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    text_path.write_text(format_index(index, summary_only=summary_only, max_report_rows=max_report_rows), encoding="utf-8")
    if jsonl_out:
        jsonl_path = Path(jsonl_out)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for asset in index.get("assets") or []:
                fh.write(json.dumps(asset, ensure_ascii=False) + "\n")
    return out_path, text_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Recursively index extracted CCSF-like assets.")
    ap.add_argument("folder")
    ap.add_argument("--out")
    ap.add_argument("--text-out")
    ap.add_argument("--quiet", action="store_true", help="Suppress per-file progress output.")
    ap.add_argument("--summary-only", action="store_true", help="Write only the capped table to the text report; JSON remains complete.")
    ap.add_argument("--max-report-rows", type=int, default=DEFAULT_MAX_REPORT_ROWS, help="Maximum asset rows/details to show in the text report; use a negative value for unlimited.")
    ap.add_argument("--jsonl-out", help="Optionally write one physical asset per JSONL line for large indexes.")
    ap.add_argument("--limit", type=int, help="Maximum number of candidate files to scan.")
    ap.add_argument("--max-file-size", type=int, help="Skip candidate files larger than this many bytes.")
    ap.add_argument("--include", action="append", default=[], help="Only scan candidate paths matching this glob; repeatable.")
    ap.add_argument("--exclude", action="append", default=[], help="Skip candidate paths matching this glob; repeatable.")
    args = ap.parse_args(argv)
    index = index_folder(args.folder, quiet=args.quiet, limit=args.limit, max_file_size=args.max_file_size, includes=args.include, excludes=args.exclude)
    out_path, text_path = write_index(index, args.out, args.text_out, summary_only=args.summary_only, max_report_rows=args.max_report_rows, jsonl_out=args.jsonl_out)
    print(f"Files considered: {index['files_considered']}")
    print(f"Files skipped: {index['files_skipped']}")
    print(f"CCSF assets found: {index['asset_count']}")
    print(f"Output JSON: {out_path}")
    print(f"Output text: {text_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

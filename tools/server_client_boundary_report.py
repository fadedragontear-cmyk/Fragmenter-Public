#!/usr/bin/env python3
"""Build a metadata-only Area Server/client ISO boundary report.

The report compares conservative symbol/string evidence found in padded gzip
members from Area Server .bin files against evidence found in the client ISO.
It never writes or copies source binaries or decompressed member payloads; only
metadata reports are emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iso9660 import Iso9660, SECTOR_USER

WARNING = "Whole-member transplant 04d -> 04 crashed; do not recommend blind member swaps."
GZIP_MAGIC = b"\x1f\x8b"
PREFIXES = (b"CCSF", b"TEX_", b"MDL_", b"MAT_", b"DMY_", b"OBJ_", b"LGT_", b"ANM_", b"CAM_")
SPECIAL_FOCUS = (
    "town04.cmp",
    "town04d.cmp",
    "CCSFtown04",
    "CCSFtown04d",
    "sr4sun1",
    "sr4clo2",
)
TOWN04_MEMBER_LABELS = {
    8: "town04.cmp",
    9: "town04d.cmp",
}
QUICK_TARGETS = (
    "CCSFtown04",
    "CCSFtown04d",
    "town04",
    "town04d",
    "sr4sun1",
    "sr4clo2",
    "DMY_",
    "TEX_",
    "MAT_",
    "MDL_",
    "OBJ_",
    "shop",
    "SHOP",
    "npc",
    "NPC",
    "merchant",
    "gate",
    "warp",
    "event",
    "item",
    "equip",
)
MIN_STRING = 4
MAX_LOCATIONS_PER_SYMBOL = 50
MAX_RAW_HITS_PER_SYMBOL = 200

PATH_RE = re.compile(rb"(?i)(?:[a-z0-9_]+[\\/]){2,}[a-z0-9_.-]+\.(?:bmp|cmp|bin|dat|tex|mdl|tm2)")
TEXTY_RE = re.compile(rb"(?i)\b(?:shop|npc|event|text|talk|msg|town|quest|item|menu|name)[a-z0-9_.:/\\-]*")
PRINTABLE = set(range(0x20, 0x7F)) | {0x09}


def progress(message: str) -> None:
    print(message, flush=True)


@dataclass
class ScanState:
    server_symbols: dict[str, list[dict]]
    gzip_members: list[dict]
    server_file_count: int
    iso_symbols: dict[str, list[dict]]
    iso_file_count: int
    iso_layout: dict | None


@dataclass
class GzipMemberMeta:
    source_file: str
    member_index: int
    raw_start: int
    raw_end: int
    compressed_size: int
    decompressed_size: int
    sha1_compressed: str
    sha1_decompressed: str


def iter_printable_strings(blob: bytes, min_len: int = MIN_STRING) -> Iterable[tuple[str, int]]:
    start = None
    for idx, byte in enumerate(blob):
        if byte in PRINTABLE:
            if start is None:
                start = idx
        elif start is not None:
            if idx - start >= min_len:
                text = blob[start:idx].decode("ascii", "ignore").strip()
                if text:
                    yield text, start
            start = None
    if start is not None and len(blob) - start >= min_len:
        text = blob[start:].decode("ascii", "ignore").strip()
        if text:
            yield text, start


def normalize_symbol(text: str) -> str:
    return text.replace("\\", "/")


def is_interesting_string(text: str) -> bool:
    raw = text.encode("ascii", "ignore")
    normalized = normalize_symbol(text)
    if any(normalized.startswith(prefix.decode("ascii")) for prefix in PREFIXES):
        return True
    if "DMY" in text:
        return True
    if any(focus.lower() in normalized.lower() for focus in SPECIAL_FOCUS):
        return True
    if PATH_RE.fullmatch(raw) or PATH_RE.search(raw):
        return True
    return bool(TEXTY_RE.search(raw))


def add_location(locations: dict[str, list[dict]], symbol: str, location: dict) -> None:
    bucket = locations.setdefault(symbol, [])
    if len(bucket) < MAX_LOCATIONS_PER_SYMBOL:
        bucket.append(location)


def extract_symbols(blob: bytes) -> list[tuple[str, int, str]]:
    found: dict[tuple[str, int, str], None] = {}
    for prefix in PREFIXES:
        start = 0
        while True:
            off = blob.find(prefix, start)
            if off == -1:
                break
            end = off
            while end < len(blob) and blob[end] in PRINTABLE and end - off < 96:
                end += 1
            symbol = blob[off:end].decode("ascii", "ignore").strip()
            if symbol:
                found[(normalize_symbol(symbol), off, "prefix")] = None
            start = off + 1
    for regex, kind in ((PATH_RE, "path"), (TEXTY_RE, "text")):
        for match in regex.finditer(blob):
            symbol = match.group(0).decode("ascii", "ignore").strip()
            if symbol:
                found[(normalize_symbol(symbol), match.start(), kind)] = None
    for text, off in iter_printable_strings(blob):
        if is_interesting_string(text):
            found[(normalize_symbol(text), off, "string")] = None
    return list(found.keys())


def parse_gzip_members(raw: bytes, rel_source: str, server_symbols: dict[str, list[dict]]) -> list[GzipMemberMeta]:
    progress(f"Parsing gzip members from server file: {rel_source}")
    members: list[GzipMemberMeta] = []
    raw_offset = 0
    while raw_offset < len(raw):
        candidate_start = raw.find(GZIP_MAGIC, raw_offset)
        if candidate_start == -1:
            break
        obj = zlib.decompressobj(wbits=31)
        try:
            decompressed = obj.decompress(raw[candidate_start:])
            obj.flush()
        except zlib.error:
            raw_offset = candidate_start + 1
            continue
        if not obj.eof:
            raw_offset = candidate_start + 1
            continue
        consumed = len(raw) - candidate_start - len(obj.unused_data)
        if consumed <= 0:
            raw_offset = candidate_start + 1
            continue
        raw_end = candidate_start + consumed
        member_index = len(members)
        progress(f"Parsing gzip member {member_index} from server file: {rel_source}")
        compressed = raw[candidate_start:raw_end]
        meta = GzipMemberMeta(
            source_file=rel_source,
            member_index=member_index,
            raw_start=candidate_start,
            raw_end=raw_end,
            compressed_size=consumed,
            decompressed_size=len(decompressed),
            sha1_compressed=hashlib.sha1(compressed).hexdigest(),
            sha1_decompressed=hashlib.sha1(decompressed).hexdigest(),
        )
        members.append(meta)
        extracted_symbols = extract_symbols(decompressed)
        progress(f"Extracted {len(extracted_symbols)} symbols from server file: {rel_source} member {member_index}")
        for symbol, off, kind in extracted_symbols:
            add_location(server_symbols, symbol, {
                "source_file": rel_source,
                "member_index": member_index,
                "member_raw_start": candidate_start,
                "decompressed_offset": off,
                "kind": kind,
            })
        raw_offset = raw_end
    return members


def scan_server(server_data: Path, state: ScanState) -> None:
    progress(f"Scanning server data path: {server_data}")
    for path in sorted(server_data.rglob("*.bin")):
        if not path.is_file():
            continue
        state.server_file_count += 1
        rel = str(path.relative_to(server_data)).replace("\\", "/")
        progress(f"Scanning server file: {rel}")
        raw = path.read_bytes()
        state.gzip_members.extend(meta.__dict__ for meta in parse_gzip_members(raw, rel, state.server_symbols))


def is_town04_member_location(location: dict) -> bool:
    source_file = str(location.get("source_file", "")).replace("\\", "/")
    return (source_file == "town.bin" or source_file.endswith("/town.bin")) and location.get("member_index") in TOWN04_MEMBER_LABELS


def annotate_town04_member(location: dict) -> dict:
    member_index = location.get("member_index")
    if member_index not in TOWN04_MEMBER_LABELS:
        return location
    annotated = dict(location)
    annotated["member_label"] = TOWN04_MEMBER_LABELS[member_index]
    return annotated


def filter_town04_server_symbols(server_symbols: dict[str, list[dict]]) -> dict[str, list[dict]]:
    filtered: dict[str, list[dict]] = {}
    for symbol, locations in server_symbols.items():
        kept = [annotate_town04_member(location) for location in locations if is_town04_member_location(location)]
        if kept:
            filtered[symbol] = kept
    return filtered


def filter_town04_gzip_members(gzip_members: list[dict]) -> list[dict]:
    return [
        annotate_town04_member(member)
        for member in gzip_members
        if is_town04_member_location(member)
    ]


def read_iso_entry(iso: Iso9660, entry) -> bytes:
    with iso.iso_path.open("rb") as f:
        chunks = bytearray()
        remaining = entry.size
        cur_lba = entry.lba
        while remaining > 0:
            take = min(SECTOR_USER, remaining)
            chunk = iso._read_user(f, cur_lba, take)  # existing Iso9660 read helper; no extraction to disk
            if not chunk:
                break
            chunks.extend(chunk)
            remaining -= len(chunk)
            cur_lba += 1
        return bytes(chunks)


def has_any_target_bytes(data: bytes, symbols: Iterable[str]) -> bool:
    for symbol in symbols:
        slash = symbol.encode("ascii", "ignore")
        backslash = symbol.replace("/", "\\").encode("ascii", "ignore")
        if (slash and slash in data) or (backslash and backslash in data):
            return True
    return False


def quick_raw_symbols(extra_raw_symbols: Iterable[str] = ()) -> set[str]:
    raw_symbols = set(QUICK_TARGETS)
    focus_lower = tuple(focus.lower() for focus in SPECIAL_FOCUS)
    for symbol in extra_raw_symbols:
        if any(focus in symbol.lower() for focus in focus_lower):
            raw_symbols.add(symbol)
    return raw_symbols


def scan_raw_iso_offsets(iso_path: Path, symbols: Iterable[str], max_bytes: int | None = None) -> dict[str, list[int]]:
    needles = [(symbol, symbol.replace("/", "\\").encode("ascii", "ignore"), symbol.encode("ascii", "ignore")) for symbol in sorted(set(symbols))]
    hits: dict[str, list[int]] = {symbol: [] for symbol, _, _ in needles}
    overlap = 256
    base = 0
    iso_size = iso_path.stat().st_size
    total_size = min(iso_size, max_bytes) if max_bytes is not None else iso_size
    prev = b""
    with iso_path.open("rb") as f:
        while base < total_size:
            read_size = min(4 * 1024 * 1024, total_size - base)
            chunk = f.read(read_size)
            if not chunk:
                break
            progress(f"Scanning raw ISO offsets: {base + len(chunk)} / {total_size} bytes")
            blob = prev + chunk
            blob_base = base - len(prev)
            for symbol, backslash, slash in needles:
                if len(hits[symbol]) >= MAX_RAW_HITS_PER_SYMBOL:
                    continue
                for needle in {backslash, slash}:
                    if not needle:
                        continue
                    start = 0
                    while len(hits[symbol]) < MAX_RAW_HITS_PER_SYMBOL:
                        off = blob.find(needle, start)
                        if off == -1:
                            break
                        abs_off = blob_base + off
                        if abs_off >= 0:
                            hits[symbol].append(abs_off)
                        start = off + 1
            base += len(chunk)
            prev = blob[-overlap:]
    return {symbol: sorted(set(offsets)) for symbol, offsets in hits.items() if offsets}


def iso_entry_raw_extent_start(iso: Iso9660, entry) -> int:
    return (entry.lba + iso.lba_offset) * iso.sector_size + iso.data_offset


def scan_iso(iso_path: Path, state: ScanState, extra_raw_symbols: Iterable[str] = (), quick: bool = False, max_iso_bytes: int | None = None) -> None:
    progress(f"Scanning ISO path: {iso_path}")
    iso = Iso9660(iso_path).open()
    state.iso_layout = {"sector_size": iso.sector_size, "data_offset": iso.data_offset, "lba_offset": iso.lba_offset, "mode": iso.mode}
    for entry in iso.iter_files():
        raw_extent_start = iso_entry_raw_extent_start(iso, entry)
        if max_iso_bytes is not None and raw_extent_start >= max_iso_bytes:
            progress(f"Skipping ISO entry after byte limit: {entry.path}")
            continue
        state.iso_file_count += 1
        progress(f"Scanning ISO entry: {entry.path}")
        data = read_iso_entry(iso, entry)
        if quick and not has_any_target_bytes(data, QUICK_TARGETS):
            progress(f"Skipping ISO symbol extraction in quick mode: {entry.path}")
            continue
        for symbol, off, kind in extract_symbols(data):
            add_location(state.iso_symbols, symbol, {
                "path": entry.path,
                "lba": entry.lba,
                "file_offset": off,
                "kind": kind,
            })
    if quick:
        raw_scan_symbols = quick_raw_symbols(extra_raw_symbols)
    else:
        raw_scan_symbols = set(state.iso_symbols) | set(extra_raw_symbols)
    raw_hits = scan_raw_iso_offsets(iso_path, raw_scan_symbols, max_bytes=max_iso_bytes)
    for symbol, offsets in raw_hits.items():
        for off in offsets[:MAX_LOCATIONS_PER_SYMBOL]:
            add_location(state.iso_symbols, symbol, {"raw_iso_offset": off, "kind": "raw-offset"})


def category_for(server_locs: list[dict], iso_locs: list[dict]) -> str:
    if server_locs and iso_locs:
        return "shared"
    if server_locs:
        return "server-only"
    if iso_locs:
        return "client-only"
    return "unknown"



def build_report(
    *,
    server_data: Path,
    iso: Path | None,
    focus_town04: bool,
    server_symbols: dict[str, list[dict]],
    gzip_members: list[dict],
    server_file_count: int,
    iso_symbols: dict[str, list[dict]],
    iso_file_count: int,
    iso_layout: dict | None,
    metadata: dict | None = None,
) -> dict:
    rows = []
    for symbol in sorted(set(server_symbols) | set(iso_symbols), key=str.lower):
        server_locs = server_symbols.get(symbol, [])
        iso_locs = iso_symbols.get(symbol, [])
        rows.append({
            "symbol": symbol,
            "found_in_area_server": bool(server_locs),
            "server_locations": server_locs,
            "found_in_iso": bool(iso_locs),
            "iso_locations": iso_locs,
            "category": category_for(server_locs, iso_locs),
            "notes": "raw ISO offsets included where found; metadata only",
        })

    summary = {
        "area_server_bin_files_scanned": server_file_count,
        "gzip_members_found": len(gzip_members),
        "iso_files_scanned": iso_file_count,
        "symbols_area_server": len(server_symbols),
        "symbols_iso": len(iso_symbols),
        "comparison_rows": len(rows),
        "categories": {cat: sum(1 for row in rows if row["category"] == cat) for cat in ("shared", "server-only", "client-only", "unknown")},
        "focus_town04": focus_town04,
    }
    report_metadata = {"focus_town04": focus_town04}
    if metadata:
        report_metadata.update(metadata)
    return {
        "warning": WARNING,
        "metadata": report_metadata,
        "input_paths": {"server_data": str(server_data), "iso": str(iso)},
        "scan_summary": summary,
        "iso_layout": iso_layout,
        "gzip_members": gzip_members,
        "comparison_rows": rows,
    }


def write_reports(json_out: Path, txt_out: Path, report: dict) -> None:
    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_text_report(txt_out, report)


def write_text_report(path: Path, report: dict) -> None:
    rows = report["comparison_rows"]
    widths = {"symbol": 36, "category": 12, "server": 8, "iso": 8}
    with path.open("w", encoding="utf-8", newline="\n") as out:
        out.write(f"WARNING: {WARNING}\n\n")
        out.write(f"Server data: {report['input_paths']['server_data']}\n")
        out.write(f"ISO: {report['input_paths']['iso']}\n\n")
        out.write(f"{'Symbol':<{widths['symbol']}} {'Category':<{widths['category']}} {'Server':>{widths['server']}} {'ISO':>{widths['iso']}} Notes\n")
        out.write("-" * 96 + "\n")
        for row in rows:
            symbol = row["symbol"]
            if len(symbol) > widths["symbol"]:
                symbol = symbol[: widths["symbol"] - 1] + "…"
            out.write(f"{symbol:<{widths['symbol']}} {row['category']:<{widths['category']}} {str(row['found_in_area_server']):>{widths['server']}} {str(row['found_in_iso']):>{widths['iso']}} {row['notes']}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a metadata-only Area Server/client ISO boundary report.")
    parser.add_argument("--server-data", type=Path, required=True)
    parser.add_argument("--iso", type=Path, required=False)
    parser.add_argument("--server-only", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--focus-town04", action="store_true")
    parser.add_argument("--max-iso-bytes", type=int)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--txt-out", type=Path)
    args = parser.parse_args()
    if not args.server_only and not args.iso:
        parser.error("--iso is required unless --server-only is used")
    txt_out = args.txt_out or args.out.with_suffix(".txt")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    txt_out.parent.mkdir(parents=True, exist_ok=True)

    state = ScanState(
        server_symbols={},
        gzip_members=[],
        server_file_count=0,
        iso_symbols={},
        iso_file_count=0,
        iso_layout=None,
    )

    try:
        scan_server(args.server_data, state)
        if args.focus_town04:
            state.server_symbols = filter_town04_server_symbols(state.server_symbols)
            state.gzip_members = filter_town04_gzip_members(state.gzip_members)
        if not args.server_only:
            scan_iso(args.iso, state, state.server_symbols.keys(), quick=args.quick, max_iso_bytes=args.max_iso_bytes)

        report = build_report(
            server_data=args.server_data,
            iso=args.iso,
            focus_town04=args.focus_town04,
            server_symbols=state.server_symbols,
            gzip_members=state.gzip_members,
            server_file_count=state.server_file_count,
            iso_symbols=state.iso_symbols,
            iso_file_count=state.iso_file_count,
            iso_layout=state.iso_layout,
        )
        write_reports(args.out, txt_out, report)
        print("Done.", flush=True)
        return 0
    except KeyboardInterrupt:
        partial_report = build_report(
            server_data=args.server_data,
            iso=args.iso,
            focus_town04=args.focus_town04,
            server_symbols=state.server_symbols,
            gzip_members=state.gzip_members,
            server_file_count=state.server_file_count,
            iso_symbols=state.iso_symbols,
            iso_file_count=state.iso_file_count,
            iso_layout=state.iso_layout,
            metadata={"partial": True, "interrupted": True},
        )
        try:
            write_reports(args.out, txt_out, partial_report)
            print(f"Interrupted; partial reports written to {args.out} and {txt_out}", file=sys.stderr, flush=True)
        except OSError as exc:
            print(f"Interrupted; failed to write partial reports to {args.out} and {txt_out}: {exc}", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

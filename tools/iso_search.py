#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Iterable, List

from iso9660 import Iso9660, normalize_path


def norm_exts(raw: str | None) -> set[str]:
    if not raw:
        return set()
    out = set()
    for p in raw.split(","):
        p = p.strip().lower().lstrip(".")
        if p:
            out.add(p)
    return out


def path_ext(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()


def has_control_chars(path: str) -> bool:
    return any(ord(ch) < 32 for ch in path)


def has_recursive_alias_pattern(path: str) -> bool:
    segs = [s for s in normalize_path(path).split("/") if s]
    if len(segs) < 2:
        return False
    # Reject patterns like a/b/a/b or a/a/a that usually indicate recursive aliasing.
    max_window = min(4, len(segs) // 2)
    for window in range(1, max_window + 1):
        for i in range(0, len(segs) - (2 * window) + 1):
            if segs[i : i + window] == segs[i + window : i + (2 * window)]:
                return True
    return False


def search_iso(
    iso: Iso9660,
    queries: List[str],
    exts: set[str],
    prefix: str,
    limit: int,
    max_scan: int,
    on_progress: Callable[[int, int, str], None] | None = None,
    progress_every: int = 1000,
):
    q = [normalize_path(x) for x in queries if x]
    q = [x for x in q if x]
    pfx = normalize_path(prefix) if prefix else ""
    scanned = 0
    hits = 0
    for idx, e in enumerate(iso.iter_files(), 1):
        if max_scan > 0 and idx > max_scan:
            break
        scanned = idx
        p = normalize_path(e.path)
        if on_progress and progress_every > 0 and (scanned == 1 or scanned % progress_every == 0):
            on_progress(scanned, hits, p)
        if has_control_chars(p):
            continue
        if has_recursive_alias_pattern(p):
            continue
        if pfx and not p.startswith(pfx):
            continue
        if exts and path_ext(p) not in exts:
            continue
        if q and not any(x in p for x in q):
            continue
        hit = {"path": p, "size": e.size, "lba": e.lba}
        yield hit
        hits += 1
        if on_progress:
            on_progress(scanned, hits, p)
        if limit > 0 and hits >= limit:
            break


def gather_queries_from_section(path: Path) -> List[str]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    queries = set()

    for p in obj.get("asset_paths", []):
        p = normalize_path(p)
        if p:
            queries.add(p)
            parts = p.split("/")
            if len(parts) >= 4:
                queries.add("/".join(parts[:-1]))
            base = parts[-1].split(".", 1)[0] if parts else ""
            if base:
                queries.add(base)

    for fam in obj.get("families", []):
        stem = str(fam.get("family", "")).strip().lower()
        if stem:
            queries.add(stem)

    for pfx in ("MDL_", "TEX_", "MAT_", "ANM_", "CAM_", "DMY_"):
        for sym in obj.get("symbols", {}).get(pfx, []):
            s = sym.lower().replace(pfx.lower(), "", 1)
            if s:
                queries.add(s)

    return sorted(queries, key=len, reverse=True)


def write_ndjson_event(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def run_search_command(args, queries: List[str], section_queries: List[str] | None = None) -> tuple[list[dict], dict]:
    iso = Iso9660(args.iso).open()
    exts = norm_exts(args.extensions)
    hits: list[dict] = []
    stats = {"scanned": 0, "hits": 0, "current": ""}
    progress_every = max(1, int(getattr(args, "progress_every", 1000) or 1000))
    stream = bool(getattr(args, "stream_ndjson", False))

    def on_progress(scanned: int, hit_count: int, current: str) -> None:
        stats.update({"scanned": scanned, "hits": hit_count, "current": current})
        if stream:
            write_ndjson_event(
                {"event": "progress", "scanned": scanned, "hits": hit_count, "current": current}
            )

    for h in search_iso(
        iso,
        queries,
        exts,
        args.prefix or "",
        args.limit,
        args.max_scanned,
        on_progress=on_progress,
        progress_every=progress_every,
    ):
        hits.append(h)
        if stream:
            write_ndjson_event({"event": "hit", **h})

    stats["hits"] = len(hits)
    limit_reached = bool(args.limit > 0 and len(hits) >= args.limit)
    done = {
        "event": "done",
        "scanned": int(stats.get("scanned", 0)),
        "hits": len(hits),
        "limit_reached": limit_reached,
    }
    if iso.traversal_warnings:
        done["warnings"] = iso.traversal_warnings
    if section_queries is not None:
        done["queries"] = section_queries
    if stream:
        write_ndjson_event(done)
    return hits, {"done": done, "warnings": iso.traversal_warnings}


def cmd_isosearch(args) -> int:
    hits, meta = run_search_command(args, args.query)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        if args.ndjson:
            with args.out.open("w", encoding="utf-8", newline="\n") as f:
                for h in hits:
                    f.write(json.dumps(h, ensure_ascii=False) + "\n")
        else:
            payload = {"count": len(hits), "hits": hits, "limit_reached": meta["done"]["limit_reached"]}
            if meta["warnings"]:
                payload["warnings"] = meta["warnings"]
            args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not args.stream_ndjson:
        for h in hits:
            print(f"{h['path']}\t{h['size']}")
        print(f"Matches: {len(hits)}")
        if meta["done"]["limit_reached"]:
            print("Limit reached; narrow search or raise cap.")
    return 0


def cmd_isosearch_section(args) -> int:
    queries = gather_queries_from_section(args.section_file)
    if args.max_queries > 0:
        queries = queries[: args.max_queries]
    if args.query:
        queries.extend(args.query)

    hits, meta = run_search_command(args, queries, section_queries=queries)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "count": len(hits),
            "queries": queries,
            "hits": hits,
            "limit_reached": meta["done"]["limit_reached"],
        }
        if meta["warnings"]:
            payload["warnings"] = meta["warnings"]
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not args.stream_ndjson:
        for h in hits:
            print(f"{h['path']}\t{h['size']}")
        print(f"Queries used: {len(queries)}")
        print(f"Matches: {len(hits)}")
        if meta["done"]["limit_reached"]:
            print("Limit reached; narrow search or raise cap.")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="Stream-search an ISO without full indexing.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("isosearch", help="Search ISO by query/path fragments")
    s.add_argument("--iso", type=Path, required=True)
    s.add_argument("--query", action="append", required=True)
    s.add_argument("--extensions", help="Comma list, e.g. bmp,max,anm")
    s.add_argument("--prefix", default="", help="Path prefix filter")
    s.add_argument("--limit", type=int, default=200)
    s.add_argument("--max-scanned", type=int, default=25000)
    s.add_argument("--out", type=Path)
    s.add_argument("--ndjson", action="store_true")
    s.add_argument("--stream-ndjson", action="store_true", help="Emit progress/hit/done NDJSON events on stdout")
    s.add_argument("--progress-every", type=int, default=1000, help="Progress event cadence while streaming")

    ss = sub.add_parser("isosearch-section", help="Search ISO using resource-map hints")
    ss.add_argument("--iso", type=Path, required=True)
    ss.add_argument("--section-file", type=Path, required=True, help="resource_map.json")
    ss.add_argument("--query", action="append", help="extra query fragment(s)")
    ss.add_argument("--extensions")
    ss.add_argument("--prefix", default="")
    ss.add_argument("--max-queries", type=int, default=30)
    ss.add_argument("--limit", type=int, default=200)
    ss.add_argument("--max-scanned", type=int, default=25000)
    ss.add_argument("--out", type=Path)
    ss.add_argument("--stream-ndjson", action="store_true", help="Emit progress/hit/done NDJSON events on stdout")
    ss.add_argument("--progress-every", type=int, default=1000, help="Progress event cadence while streaming")

    args = ap.parse_args()
    if args.cmd == "isosearch":
        return cmd_isosearch(args)
    if args.cmd == "isosearch-section":
        return cmd_isosearch_section(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

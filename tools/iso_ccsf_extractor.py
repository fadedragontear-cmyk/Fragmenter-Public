#!/usr/bin/env python3
"""Extract embedded CCSF bundles from likely containers inside an ISO."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import html
import json
import re
import sys
import zlib
from urllib.parse import quote
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660, normalize_path
from fragment_core import CCSF_SIG
import binary_preview
import iso_asset_preview
import ccsf_asset_indexer
import ccsf_preview_manifest
import asset_library

PLAIN_CCSF = b"CCSF"
PRIORITY_PATHS = [
    "data/data.bin",
    "outside.bin",
    "stream/strcmn.bin",
    "data/fgmt.bin",
    "data/kfed.bin",
    "data/kfaed.bin",
]
CANDIDATE_EXTS = {".bin", ".dat", ".ccs", ".cmp", ".arc", ".pac"}
DEFAULT_MAX_SCAN_BYTES = 256 * 1024 * 1024
DEFAULT_EXTRACT_CAP = 32 * 1024 * 1024
DEFAULT_LIMIT = 200
DEFAULT_MAX_REPORT_ROWS = 200
DEFAULT_MAX_FAILED_ROWS = 200
SCAN_CHUNK = 1024 * 1024
OVERLAP = max(len(CCSF_SIG), 10) + 16

PROGRESS_EVENT_KEYS = (
    "stage",
    "current_container",
    "container_index",
    "container_total",
    "bytes_scanned",
    "gzip_offsets_seen",
    "gzip_valid_members",
    "false_positives_skipped",
    "ccsf_bundles_extracted",
    "assets_indexed",
)
ProgressCallback = Callable[[dict[str, Any]], None]


def _progress_event(
    stage: str,
    *,
    current_container: str = "",
    container_index: int = 0,
    container_total: int = 0,
    bytes_scanned: int = 0,
    gzip_offsets_seen: int = 0,
    gzip_valid_members: int = 0,
    false_positives_skipped: int = 0,
    ccsf_bundles_extracted: int = 0,
    assets_indexed: int = 0,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "current_container": current_container,
        "container_index": int(container_index or 0),
        "container_total": int(container_total or 0),
        "bytes_scanned": int(bytes_scanned or 0),
        "gzip_offsets_seen": int(gzip_offsets_seen or 0),
        "gzip_valid_members": int(gzip_valid_members or 0),
        "false_positives_skipped": int(false_positives_skipped or 0),
        "ccsf_bundles_extracted": int(ccsf_bundles_extracted or 0),
        "assets_indexed": int(assets_indexed or 0),
    }


def _emit_progress(callback: ProgressCallback | None, event: dict[str, Any]) -> dict[str, Any]:
    if callback is not None:
        callback(event)
    return event


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _safe_component(s: str, fallback: str = "item") -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s or "")).strip("._")
    return safe or fallback


def _safe_under(base: Path, *parts: str) -> Path:
    root = base.resolve()
    target = root.joinpath(*[_safe_component(p) for p in parts]).resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"unsafe output path: {target}")
    return target


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(Path(path).name, p) for p in patterns)


def _file_url(path: str | Path) -> str:
    """Return a file:// URL with shell/file-system characters safely escaped."""
    p = Path(path).expanduser()
    try:
        p = p.resolve()
    except OSError:
        p = p.absolute()
    return "file://" + quote(str(p), safe="/:")


def _asset_file(asset: dict[str, Any]) -> str:
    return str(asset.get("file") or asset.get("relative_file") or "")


def _asset_rows(assets: list[dict[str, Any]], predicate, limit: int = 20) -> list[dict[str, Any]]:
    return [asset for asset in assets if predicate(asset)][:limit]


def _manifest_summary(asset: dict[str, Any]) -> dict[str, Any]:
    """Build a compact dashboard summary from ccsf_preview_manifest."""
    manifest = ccsf_preview_manifest.build_manifest(asset)
    return {
        "asset_name": manifest.get("asset_name") or Path(_asset_file(asset)).stem,
        "bundle_type": manifest.get("bundle_type") or "unknown",
        "variant": manifest.get("variant") or "",
        "readiness": asset.get("readiness") or "",
        "can_attempt_static_preview": bool(manifest.get("can_attempt_static_preview")),
        "can_attempt_animated_preview": bool(manifest.get("can_attempt_animated_preview")),
        "main_model_candidates": (manifest.get("main_model_candidates") or [])[:5],
        "texture_clt_pairs": (manifest.get("texture_clt_pairs") or [])[:5],
        "animation_candidates": (manifest.get("animation_candidates") or [])[:5],
        "renderer_status": manifest.get("renderer_status") or {},
        "notes": manifest.get("notes") or [],
    }


def write_results_dashboard(
    report: dict[str, Any],
    asset_index: dict[str, Any] | None,
    dashboard_path: Path,
    library: dict[str, Any] | None = None,
) -> Path:
    """Write a static HTML summary for extracted/indexed CCSF assets.

    The dashboard uses logical assets from :mod:`asset_library` when available
    so duplicate physical files collapse into one row. Sections are capped to
    small samples and report how many matching assets were omitted.
    """
    asset_index = asset_index or {}
    physical_assets = list(asset_index.get("assets") or [])
    logical_library = library or {"asset_count": 0, "source_asset_count": len(physical_assets), "assets": []}
    logical_assets = list(logical_library.get("assets") or [])

    counts_by_type: dict[str, int] = {}
    for asset in logical_assets:
        typ = str(asset.get("type") or "unknown")
        counts_by_type[typ] = counts_by_type.get(typ, 0) + 1

    def esc(value: Any) -> str:
        return html.escape(str(value if value is not None else ""), quote=True)

    def logical_file(asset: dict[str, Any]) -> str:
        return str(asset.get("preferred_file") or "")

    def resource_counts(asset: dict[str, Any]) -> dict[str, int]:
        counts = asset.get("resource_counts") if isinstance(asset.get("resource_counts"), dict) else {}
        return {str(k): int(v or 0) for k, v in counts.items()}

    def is_character_body(asset: dict[str, Any]) -> bool:
        variant = str(asset.get("variant") or "").lower()
        return str(asset.get("type") or "").startswith("character") and variant in {"", "body", "main", "base", "normal"}

    def is_color_variant(asset: dict[str, Any]) -> bool:
        typ = str(asset.get("type") or "")
        variant = str(asset.get("variant") or "").lower()
        return typ.startswith("character") and bool(variant) and variant not in {"body", "main", "base", "normal"}

    def is_environment(asset: dict[str, Any]) -> bool:
        typ = str(asset.get("type") or "").lower()
        tags = {str(tag).lower() for tag in asset.get("tags") or []}
        name = str(asset.get("display_name") or "").lower()
        return typ == "environment/background" or "environment" in typ or "background" in typ or "stage" in tags or "env" in tags or "bg" in name

    def animation_weight(asset: dict[str, Any]) -> int:
        return resource_counts(asset).get("ANM", 0)

    def is_unknown(asset: dict[str, Any]) -> bool:
        typ = str(asset.get("type") or "unknown").lower()
        return typ in {"", "unknown"} or typ.startswith("unknown")

    def limited_rows(rows: list[dict[str, Any]], limit: int = 20) -> tuple[list[dict[str, Any]], int]:
        return rows[:limit], max(0, len(rows) - limit)

    character_body, character_body_omitted = limited_rows([a for a in logical_assets if is_character_body(a)])
    color_variants, color_variants_omitted = limited_rows([a for a in logical_assets if is_color_variant(a)])
    environments, environments_omitted = limited_rows([a for a in logical_assets if is_environment(a)])
    animation_heavy_all = sorted([a for a in logical_assets if animation_weight(a) > 0], key=lambda a: (-animation_weight(a), str(a.get("display_name") or "").lower()))
    animation_heavy, animation_heavy_omitted = limited_rows(animation_heavy_all)
    unknown_assets, unknown_assets_omitted = limited_rows([a for a in logical_assets if is_unknown(a)])

    sample_physical = physical_assets[:6]
    sample_manifests = [_manifest_summary(asset) for asset in sample_physical]

    def link_for(path: str, label: str | None = None, href: str | None = None) -> str:
        if not path and not href:
            return "-"
        target = href or _file_url(path)
        return f'<a href="{esc(target)}">{esc(label or path or href)}</a>'

    def logical_asset_table(title: str, rows: list[dict[str, Any]], omitted: int) -> str:
        body = []
        for asset in rows:
            counts = resource_counts(asset)
            active = ", ".join(f"{k}:{v}" for k, v in counts.items() if v) or "metadata"
            duplicate_count = len(asset.get("duplicate_files") or [])
            preferred = logical_file(asset)
            preferred_href = str(asset.get("preferred_file_href") or "")
            preferred_cell = link_for(preferred, href=preferred_href) if preferred_href else esc(preferred)
            body.append(
                "<tr>"
                f"<td>{esc(asset.get('display_name'))}</td>"
                f"<td>{esc(asset.get('type'))}</td>"
                f"<td>{esc(asset.get('variant') or '-')}</td>"
                f"<td>{esc(asset.get('readiness') or '-')}</td>"
                f"<td>{esc(active)}</td>"
                f"<td>{duplicate_count}</td>"
                f"<td>{preferred_cell}</td>"
                "</tr>"
            )
        if not body:
            body.append("<tr><td colspan=\"7\">No matching logical assets indexed.</td></tr>")
        omitted_note = f"<p class=\"omitted\">{omitted} additional matching assets omitted.</p>" if omitted else "<p class=\"omitted\">No additional matching assets omitted.</p>"
        return (
            f"<section><h2>{esc(title)}</h2>{omitted_note}<table><thead><tr>"
            "<th>Name</th><th>Type</th><th>Variant</th><th>Readiness</th><th>Resource counts</th><th>Duplicates</th><th>Preferred file</th>"
            "</tr></thead><tbody>" + "\n".join(body) + "</tbody></table></section>"
        )

    manifest_blocks = []
    for summary in sample_manifests:
        manifest_blocks.append(
            "<article class=\"manifest\">"
            f"<h3>{esc(summary['asset_name'])}</h3>"
            f"<p><strong>Type:</strong> {esc(summary['bundle_type'])} "
            f"<strong>Variant:</strong> {esc(summary['variant'] or '-')} "
            f"<strong>Readiness:</strong> {esc(summary['readiness'] or '-')}</p>"
            f"<p><strong>Preview flags:</strong> static={esc(summary['can_attempt_static_preview'])}, "
            f"animated={esc(summary['can_attempt_animated_preview'])}</p>"
            f"<pre>{esc(json.dumps(summary, indent=2))}</pre>"
            "</article>"
        )
    if not manifest_blocks:
        manifest_blocks.append("<p>No sample manifests available; run with --index-assets to populate dashboard asset sections.</p>")

    type_rows = "\n".join(
        f"<tr><td>{esc(asset_type)}</td><td>{count}</td></tr>"
        for asset_type, count in sorted(counts_by_type.items())
    ) or "<tr><td colspan=\"2\">No logical assets.</td></tr>"

    reports_dir = dashboard_path.parent
    asset_library_json = Path(str(report.get("asset_library_path") or reports_dir / "asset_library.json"))
    asset_library_txt = Path(str(report.get("asset_library_text_path") or reports_dir / "asset_library.txt"))
    asset_index_path = Path(str(report.get("asset_index_path") or reports_dir / "ccsf_asset_index.json"))
    confirmed_total = len(report.get("confirmed_ccsf_bundles") or [])
    logical_count = int(logical_library.get("asset_count") or len(logical_assets))
    physical_count = int(logical_library.get("source_asset_count") or len(physical_assets))
    duplicate_count = max(0, physical_count - logical_count)
    preferred_count = len([asset for asset in logical_assets if asset.get("preferred_file")])

    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_path.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>CCSF Asset Library Dashboard</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;line-height:1.4}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top}"
        "th{background:#f2f2f2}.cards{display:flex;gap:1rem;flex-wrap:wrap}.card{border:1px solid #ccc;padding:1rem;border-radius:.5rem;min-width:12rem}"
        "pre{background:#f7f7f7;padding:1rem;overflow:auto}.note{background:#fff7d6;padding:1rem;border-left:4px solid #d6a700}.omitted{color:#555}</style>"
        "</head><body>"
        "<h1>CCSF Asset Library Dashboard</h1>"
        f"<p>Generated at {esc(report.get('created_at'))} for ISO <code>{esc(report.get('iso_path'))}</code>.</p>"
        "<p class=\"note\">This dashboard uses logical assets from <code>tools/asset_library.py</code> by default, caps each asset section at 20 rows, "
        "and links to preferred files instead of embedding duplicate-heavy tables.</p>"
        "<div class=\"cards\">"
        f"<div class=\"card\"><h2>Logical assets</h2><p>{logical_count}</p></div>"
        f"<div class=\"card\"><h2>Physical files</h2><p>{physical_count}</p></div>"
        f"<div class=\"card\"><h2>Duplicates</h2><p>{duplicate_count}</p></div>"
        f"<div class=\"card\"><h2>Confirmed CCSF bundles</h2><p>{confirmed_total}</p></div>"
        "</div>"
        "<section><h2>Library links</h2><ul>"
        f"<li>{link_for(str(asset_library_json), 'asset_library.json')}</li>"
        f"<li>{link_for(str(asset_library_txt), 'asset_library.txt')}</li>"
        f"<li>{link_for(str(asset_index_path), 'ccsf_asset_index.json')}</li>"
        f"<li>{link_for(str(dashboard_path), 'asset_library_dashboard.html / ccsf_results_dashboard.html')}</li>"
        f"<li>{preferred_count} preferred file links are shown across capped sections below.</li>"
        "</ul></section>"
        "<section><h2>Counts by logical asset type</h2><table><thead><tr><th>Asset type</th><th>Count</th></tr></thead><tbody>"
        f"{type_rows}</tbody></table></section>"
        f"{logical_asset_table('First 20 top character bodies', character_body, character_body_omitted)}"
        f"{logical_asset_table('First 20 color variants', color_variants, color_variants_omitted)}"
        f"{logical_asset_table('First 20 environment assets', environments, environments_omitted)}"
        f"{logical_asset_table('First 20 animation-heavy assets', animation_heavy, animation_heavy_omitted)}"
        f"{logical_asset_table('First 20 unknown assets', unknown_assets, unknown_assets_omitted)}"
        "<section><h2>Sample preview manifest summaries</h2>"
        + "\n".join(manifest_blocks)
        + "</section></body></html>\n",
        encoding="utf-8",
    )
    return dashboard_path


def resolve_ccsf_offset(data: bytes, marker_offset: int) -> int | None:
    """Resolve a CCSF signature or plain ``CCSF`` marker to its payload offset."""
    if marker_offset < 0:
        return None
    if data[marker_offset:marker_offset + len(CCSF_SIG)] == CCSF_SIG:
        return marker_offset
    sig_offset = marker_offset - 8
    if sig_offset >= 0 and data[sig_offset:sig_offset + len(CCSF_SIG)] == CCSF_SIG:
        return sig_offset
    return None


def build_iso_index(iso_path: Path, index_path: Path, quiet: bool = False) -> dict[str, Any]:
    iso = Iso9660(iso_path).open()
    files = []
    for e in iso.iter_files():
        files.append({"path": e.path, "lba": e.lba, "size": e.size, "is_dir": bool(getattr(e, "is_dir", False))})
    payload = {"iso": str(iso_path), "mode": iso.mode, "layout": {"sector_size": iso.sector_size, "data_offset": iso.data_offset}, "count": len(files), "files": files}
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not quiet:
        print(f"Built ISO index: {index_path} ({len(files)} files)")
    return payload


def load_or_build_index(iso_path: Path, index_path: Path | None, build: bool, quiet: bool) -> tuple[dict[str, Any], Path | None]:
    if index_path and index_path.is_file():
        return iso_asset_preview.load_iso_index(index_path), index_path
    if not build:
        raise FileNotFoundError(f"ISO index missing; pass --build-index: {index_path}")
    out = index_path or Path("workspace/iso_index.json")
    return build_iso_index(iso_path, out, quiet=quiet), out


def select_containers(index: dict[str, Any], includes: list[str], excludes: list[str], explicit: list[str], limit: int | None) -> list[dict[str, Any]]:
    by_norm = {normalize_path(str(e.get("path", ""))).lower(): e for e in index.get("files", []) if not e.get("is_dir")}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    def add(e: dict[str, Any]):
        p = str(e.get("path", ""))
        n = normalize_path(p).lower()
        if not p or n in seen:
            return
        if includes and not _matches(n, includes):
            return
        if excludes and _matches(n, excludes):
            return
        seen.add(n); selected.append(e)
    for p in explicit:
        e = by_norm.get(normalize_path(p).lower())
        if e: add(e)
    for p in PRIORITY_PATHS:
        e = by_norm.get(p)
        if e: add(e)
    candidates = []
    for e in index.get("files", []):
        if e.get("is_dir"): continue
        path = str(e.get("path", ""))
        if Path(path).suffix.lower() in CANDIDATE_EXTS or iso_asset_preview.classify_iso_asset(e)["type_guess"] == "container_candidate":
            row = iso_asset_preview.classify_iso_asset(e); row["entry"] = e; candidates.append(row)
    for row in sorted(candidates, key=lambda r: (-int(r["score"]), str(r["path"]).lower())):
        add(row["entry"])
        if limit is not None and len(selected) >= limit: break
    return selected[:limit] if limit is not None else selected


def staging_path(workspace: Path, iso_path: str) -> Path:
    digest = hashlib.sha1(iso_path.encode("utf-8", "replace")).hexdigest()[:12]
    parts = [_safe_component(p) for p in re.split(r"[/\\]+", iso_path) if p and p not in (".", "..")]
    return _safe_under(workspace / "iso_ccsf_staging", digest, *(parts or ["container.bin"]))


def extract_container(iso: Iso9660, internal: str, out: Path, reuse: bool) -> None:
    if reuse and out.is_file():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    if not iso.extract(normalize_path(internal), out):
        raise FileNotFoundError(f"not found in ISO: {internal}")


def iter_file_hits(path: Path, max_scan_bytes: int | None):
    seen = set(); prev = b""
    for base, chunk in binary_preview.iter_chunks(path, chunk_size=SCAN_CHUNK, max_scan_bytes=max_scan_bytes):
        window = prev + chunk
        win_base = base - len(prev)
        for sig, kind in ((CCSF_SIG, "ccsf_signature"), (PLAIN_CCSF, "ccsf_marker"), (binary_preview.GZIP_MAGIC, "gzip")):
            start = 0
            while True:
                idx = window.find(sig, start)
                if idx < 0: break
                off = win_base + idx
                if kind == "ccsf_marker":
                    resolved = resolve_ccsf_offset(window, idx)
                    if resolved is None:
                        start = idx + 1; continue
                    off = win_base + resolved
                key = ("ccsf", off) if kind in {"ccsf_signature", "ccsf_marker"} else (kind, off)
                if off >= 0 and key not in seen:
                    seen.add(key); yield {"offset": off, "type": kind}
                start = idx + 1
        prev = window[-OVERLAP:]


def ccsf_name(data: bytes, fallback: str) -> str:
    name = None
    if data.startswith(CCSF_SIG):
        raw = data[8:128].split(b"\x00", 1)[0]
        if raw.startswith(b"CCSF") and len(raw) > 4:
            name = raw[4:].decode("ascii", "ignore")
        else:
            txt = raw.decode("ascii", "ignore")
            if txt.startswith("CCSF"):
                name = txt[4:] or txt
    return _safe_component(name or fallback, "ccsf")


def read_ccsf_payload(data: bytes, off: int, cap: int) -> bytes:
    resolved = resolve_ccsf_offset(data, off)
    if resolved is None:
        return b""
    off = resolved
    nxt = data.find(CCSF_SIG, off + len(CCSF_SIG))
    end = nxt if nxt >= 0 else min(len(data), off + cap)
    return data[off:end]


def read_ccsf_from_file(path: Path, off: int, cap: int) -> bytes:
    size = path.stat().st_size
    search = binary_preview._read_range(path, off, min(cap, size - off))
    return read_ccsf_payload(search, 0, cap)


def parse_gzip_header_at(path: Path, off: int, max_header_bytes: int = 65536) -> dict[str, Any] | None:
    """Return parsed gzip header metadata for a member at ``off``, or ``None``.

    The parser validates the fixed gzip header and fully walks the optional
    FEXTRA, FNAME, FCOMMENT, and FHCRC fields inside a bounded read so random
    1F 8B byte pairs are not treated as gzip members.
    """
    if off < 0 or max_header_bytes < 10:
        return None
    size = path.stat().st_size
    if off + 10 > size:
        return None
    data = binary_preview._read_range(path, off, min(max_header_bytes, size - off))
    if len(data) < 10 or data[:2] != binary_preview.GZIP_MAGIC:
        return None

    method = data[2]
    flags = data[3]
    if method != 8 or flags & 0xE0:
        return None

    pos = 10
    info: dict[str, Any] = {
        "offset": off,
        "method": method,
        "flags": flags,
        "mtime": int.from_bytes(data[4:8], "little"),
        "extra_flags": data[8],
        "os": data[9],
    }

    if flags & 0x04:  # FEXTRA
        if len(data) < pos + 2:
            return None
        xlen = int.from_bytes(data[pos:pos + 2], "little")
        pos += 2
        if len(data) < pos + xlen:
            return None
        info["extra_length"] = xlen
        pos += xlen

    if flags & 0x08:  # FNAME
        end = data.find(b"\x00", pos)
        if end < 0:
            return None
        info["original_filename"] = data[pos:end].decode("latin-1", errors="replace")
        pos = end + 1

    if flags & 0x10:  # FCOMMENT
        end = data.find(b"\x00", pos)
        if end < 0:
            return None
        info["comment"] = data[pos:end].decode("latin-1", errors="replace")
        pos = end + 1

    if flags & 0x02:  # FHCRC
        if len(data) < pos + 2:
            return None
        info["header_crc16"] = int.from_bytes(data[pos:pos + 2], "little")
        pos += 2

    info["header_length"] = pos
    return info


def probe_gzip_member(path: Path, off: int, max_probe_input: int = 65536, max_probe_output: int = 4096) -> dict[str, Any]:
    """Run a tiny bounded inflate probe for a gzip member at ``off``."""
    if max_probe_input <= 0 or max_probe_output < 0:
        return {"ok": False, "offset": off, "error": "invalid probe bounds"}
    try:
        header = parse_gzip_header_at(path, off, max_probe_input)
        if header is None:
            return {"ok": False, "offset": off, "error": "invalid or unparseable gzip header"}
        raw = binary_preview._read_range(path, off, min(max_probe_input, path.stat().st_size - off))
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = d.decompress(raw, max_probe_output)
        return {
            "ok": True,
            "offset": off,
            "header": header,
            "probe_input_bytes": len(raw),
            "probe_output_bytes": len(out),
            "probe_eof": bool(d.eof),
            "probe_truncated": bool(not d.eof and len(out) >= max_probe_output),
        }
    except Exception as exc:
        return {"ok": False, "offset": off, "error": str(exc)}


def gzip_from_file(path: Path, off: int, cap: int) -> tuple[bytes, bool]:
    raw = binary_preview._read_range(path, off, min(cap * 4, path.stat().st_size - off))
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(raw, cap)
    truncated = (not d.eof and len(out) >= cap)
    return out, truncated


def write_row(rows: list[dict[str, Any]], iso_path: Path, iso_internal: str, container: Path, offset: int, layer: str, out_dir: Path, payload: bytes, fallback: str, seen_sha: dict[str, str], seen_src: set[tuple[str,int,str]]):
    if not payload:
        return
    src_key = (str(container), offset, layer)
    sha = _sha1_bytes(payload) if payload else ""
    name = ccsf_name(payload, fallback)
    dup = sha in seen_sha
    status = "duplicate" if dup else "extracted"
    out_path = seen_sha.get(sha)
    if not dup:
        out_path_obj = _safe_under(out_dir, f"{name}.ccs")
        if out_path_obj.exists():
            out_path_obj = _safe_under(out_dir, f"{name}_{sha[:10]}.ccs")
        out_path_obj.parent.mkdir(parents=True, exist_ok=True)
        out_path_obj.write_bytes(payload)
        out_path = str(out_path_obj)
        seen_sha[sha] = out_path
    seen_src.add(src_key)
    rows.append({"source_iso_path": str(iso_path), "top_level_iso_file_path": iso_internal, "container_path": str(container), "source_offset": offset, "compression_layer": layer, "extracted_ccsf_path": out_path, "ccsf_name": name, "size": len(payload), "sha1": sha, "duplicate_status": "duplicate" if dup else "unique", "extraction_status": status, "error_warning": ""})


def _failed_gzip_candidate(iso_path: Path, iso_internal: str, container: Path, off: int, stage: str, error: str, probe: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "source_iso_path": str(iso_path),
        "top_level_iso_file_path": iso_internal,
        "container_path": str(container),
        "source_offset": off,
        "compression_layer": "gzip",
        "extraction_status": "failed_candidate",
        "failure_stage": stage,
        "error_warning": error,
    }
    if probe is not None:
        row["probe"] = probe
    return row


def scan_container(iso_path: Path, iso_internal: str, container: Path, out_dir: Path, max_scan_bytes: int | None, extract_cap: int, rows: list[dict[str, Any]], seen_sha: dict[str,str], seen_src: set[tuple[str,int,str]], quiet: bool, counters: dict[str, int], failed_gzip_candidates: list[dict[str, Any]], gzip_members: list[dict[str, Any]], skipped_gzip_members: list[dict[str, Any]], include_failed_candidates: bool, include_non_ccsf_gzip: bool, ccsf_only: bool, gzip_only: bool):
    for hit in iter_file_hits(container, max_scan_bytes):
        off = int(hit["offset"]); kind = str(hit["type"])
        try:
            if (str(container), off, kind) in seen_src: continue
            if gzip_only and kind != "gzip":
                continue
            if kind == "gzip":
                counters["gzip_offsets_seen"] += 1
                probe = probe_gzip_member(container, off)
                if not probe.get("ok"):
                    counters["gzip_false_positive_skipped"] += 1
                    failed = _failed_gzip_candidate(iso_path, iso_internal, container, off, "probe", str(probe.get("error", "gzip probe failed")), probe)
                    failed_gzip_candidates.append(failed)
                    if include_failed_candidates:
                        rows.append({**failed, "extracted_ccsf_path": None, "ccsf_name": "", "size": 0, "sha1": "", "duplicate_status": ""})
                    continue
                counters["gzip_valid_members"] += 1
                member = {
                    "source_iso_path": str(iso_path),
                    "top_level_iso_file_path": iso_internal,
                    "container_path": str(container),
                    "source_offset": off,
                    "compression_layer": "gzip",
                    "probe": probe,
                }
                gzip_members.append(member)
                data, truncated = gzip_from_file(container, off, extract_cap)
                member["decompressed_probe_truncated"] = bool(truncated)
                member["decompressed_bytes_read"] = len(data)
                if not data: continue
                ccsf_markers = sorted(
                    {
                        resolved
                        for marker in (
                            [m.start() for m in re.finditer(re.escape(CCSF_SIG), data)]
                            + [m.start() for m in re.finditer(re.escape(PLAIN_CCSF), data)]
                        )
                        for resolved in [resolve_ccsf_offset(data, marker)]
                        if resolved is not None
                    }
                )
                contains_ccsf = False
                for marker in ccsf_markers:
                    contains_ccsf = True
                    payload = read_ccsf_payload(data, marker, extract_cap)
                    if not payload:
                        continue
                    write_row(rows, iso_path, iso_internal, container, off + marker, "gzip", out_dir, payload, f"{Path(iso_internal).stem}_{off:08X}_{marker:08X}", seen_sha, seen_src)
                member["contains_ccsf"] = contains_ccsf
                if contains_ccsf:
                    counters["gzip_members_containing_ccsf"] += 1
                else:
                    skipped_gzip_members.append({**member, "skip_reason": "no_ccsf_signature"})
                    if include_non_ccsf_gzip and not ccsf_only:
                        rows.append({**member, "extracted_ccsf_path": None, "ccsf_name": "", "size": len(data), "sha1": "", "duplicate_status": "", "extraction_status": "valid_gzip_no_ccsf", "error_warning": ""})
            else:
                if gzip_only:
                    continue
                payload = read_ccsf_from_file(container, off, extract_cap)
                if payload.endswith(PLAIN_CCSF) and len(payload) == len(CCSF_SIG): continue
                if not payload:
                    continue
                write_row(rows, iso_path, iso_internal, container, off, "none", out_dir, payload, f"{Path(iso_internal).stem}_{off:08X}", seen_sha, seen_src)
        except Exception as exc:
            if kind == "gzip":
                counters["gzip_errors"] += 1
                failed = _failed_gzip_candidate(iso_path, iso_internal, container, off, "error", str(exc))
                failed_gzip_candidates.append(failed)
                if not include_failed_candidates:
                    continue
            rows.append({"source_iso_path": str(iso_path), "top_level_iso_file_path": iso_internal, "container_path": str(container), "source_offset": off, "compression_layer": kind, "extracted_ccsf_path": None, "ccsf_name": "", "size": 0, "sha1": "", "duplicate_status": "", "extraction_status": "error", "error_warning": str(exc)})


def format_text(report: dict[str, Any], summary_only: bool = False, max_report_rows: int | None = None, max_failed_rows: int | None = None, include_failed_candidates: bool = False, include_non_ccsf_gzip: bool = False) -> str:
    all_rows = list(report.get("confirmed_ccsf_bundles", []) or [])
    rows = all_rows
    omitted_confirmed = 0
    if max_report_rows is not None and max_report_rows >= 0:
        rows = all_rows[:max_report_rows]
        omitted_confirmed = max(0, len(all_rows) - len(rows))
    summary_keys = [
        "bytes_scanned",
        "gzip_offsets_seen",
        "gzip_valid_members",
        "gzip_false_positive_skipped",
        "gzip_errors",
        "gzip_members_containing_ccsf",
        "confirmed_ccsf_bundles_extracted",
        "duplicates_skipped",
        "ccsf_assets_indexed",
        "asset_index_path",
        "results_dashboard_path",
    ]
    lines = ["ISO CCSF Extraction Summary", f"ISO: {report.get('iso_path')}", ""]
    lines += ["Summary counters:"]
    lines += [f"- {key}: {report.get(key)}" for key in summary_keys]
    lines += ["", f"Confirmed CCSF bundles (showing {len(rows)} of {len(all_rows)}; omitted {omitted_confirmed}):"]
    header = ["status", "dup", "layer", "offset", "name", "size", "iso path", "output"]
    widths = [10, 9, 8, 10, 24, 10, 36, 42]
    def fmt(vals): return "  ".join(str(v)[:w].ljust(w) for v,w in zip(vals,widths)).rstrip()
    lines += [fmt(header), fmt(["-"*w for w in widths])]
    for r in rows:
        lines.append(fmt([r.get("extraction_status"), r.get("duplicate_status"), r.get("compression_layer"), f"{int(r.get('source_offset') or 0):08X}", r.get("ccsf_name"), r.get("size"), r.get("top_level_iso_file_path"), r.get("extracted_ccsf_path")]))
    all_top = sorted(report.get("containers", []), key=lambda r: int(r.get("ccsf_bundle_count", 0)), reverse=True)
    top_limit = 10 if max_report_rows is None or max_report_rows < 0 else min(10, max_report_rows)
    top = all_top[:top_limit]
    lines += ["", f"Top source containers (showing {len(top)} of {len(all_top)}; omitted {max(0, len(all_top) - len(top))}):"]
    for c in top:
        lines.append(f"- {c.get('path')} ({c.get('ccsf_bundle_count', 0)} CCSF bundles, {c.get('bytes_scanned', 0)} bytes scanned)")
    if not summary_only:
        if include_non_ccsf_gzip:
            all_skipped = list(report.get("skipped_gzip_members", []) or [])
            skipped = all_skipped
            if max_failed_rows is not None and max_failed_rows >= 0:
                skipped = all_skipped[:max_failed_rows]
            if skipped:
                lines += ["", f"Non-CCSF gzip members (showing {len(skipped)} of {len(all_skipped)}; omitted {max(0, len(all_skipped) - len(skipped))}):"]
                lines += [f"- {r.get('top_level_iso_file_path')} @ {int(r.get('source_offset') or 0):08X}: {r.get('skip_reason', 'no_ccsf_signature')}" for r in skipped]
        if include_failed_candidates:
            all_failed = list(report.get("failed_gzip_candidates", []) or [])
            failed = all_failed
            if max_failed_rows is not None and max_failed_rows >= 0:
                failed = all_failed[:max_failed_rows]
            if failed:
                lines += ["", f"Failed gzip candidates (showing {len(failed)} of {len(all_failed)}; omitted {max(0, len(all_failed) - len(failed))}):"]
                lines += [f"- {r.get('top_level_iso_file_path')} @ {int(r.get('source_offset') or 0):08X}: {r.get('error_warning')}" for r in failed]
        all_errs = [r for r in report.get("extractions", []) if r.get("error_warning") and (include_failed_candidates or r.get("extraction_status") != "failed_candidate")]
        errs = all_errs
        if max_failed_rows is not None and max_failed_rows >= 0:
            errs = all_errs[:max_failed_rows]
        if errs:
            lines += ["", f"Warnings/Errors (showing {len(errs)} of {len(all_errs)}; omitted {max(0, len(all_errs) - len(errs))}):"] + [f"- {r.get('top_level_iso_file_path')} @ {r.get('source_offset')}: {r.get('error_warning')}" for r in errs]
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace, progress_callback: ProgressCallback | None = None) -> dict[str, Any]:
    workspace = Path(args.workspace)
    reports = workspace / "reports"
    out_json = Path(args.out or reports / "iso_ccsf_extraction_index.json")
    text_out = Path(args.text_out or reports / "iso_ccsf_extraction_index.txt")
    index, index_path = load_or_build_index(Path(args.iso_path), Path(args.iso_index) if args.iso_index else None, args.build_index, args.quiet)
    legacy_limit = getattr(args, "limit", None)
    container_limit = legacy_limit if legacy_limit is not None else getattr(args, "container_limit", DEFAULT_LIMIT)
    containers = select_containers(index, args.include, args.exclude, args.container, container_limit)
    iso = Iso9660(Path(args.iso_path)).open()
    out_dir = workspace / "extracted_ccs"
    rows: list[dict[str, Any]] = []; seen_sha: dict[str,str] = {}; seen_src: set[tuple[str,int,str]] = set()
    failed_gzip_candidates: list[dict[str, Any]] = []
    gzip_members: list[dict[str, Any]] = []
    skipped_gzip_members: list[dict[str, Any]] = []
    gzip_counters = {"gzip_offsets_seen": 0, "gzip_valid_members": 0, "gzip_false_positive_skipped": 0, "gzip_errors": 0, "gzip_members_containing_ccsf": 0}
    container_rows: list[dict[str, Any]] = []
    ccsf_assets_indexed = 0
    bytes_scanned_total = 0
    _emit_progress(progress_callback, _progress_event("start", container_total=len(containers)))
    for i, entry in enumerate(containers, 1):
        internal = str(entry.get("path"))
        if not args.quiet: print(f"[{i}/{len(containers)}] {internal}")
        _emit_progress(progress_callback, _progress_event("container_start", current_container=internal, container_index=i, container_total=len(containers), bytes_scanned=bytes_scanned_total, gzip_offsets_seen=gzip_counters["gzip_offsets_seen"], gzip_valid_members=gzip_counters["gzip_valid_members"], false_positives_skipped=gzip_counters["gzip_false_positive_skipped"], ccsf_bundles_extracted=len([r for r in rows if r.get("extraction_status") == "extracted"]), assets_indexed=ccsf_assets_indexed))
        staged = staging_path(workspace, internal)
        before_rows = len(rows)
        scanned_bytes = 0
        try:
            extract_container(iso, internal, staged, args.reuse_existing)
            size = staged.stat().st_size
            scanned_bytes = min(size, args.max_scan_bytes) if args.max_scan_bytes is not None else size
            scan_container(Path(args.iso_path), internal, staged, out_dir, args.max_scan_bytes, args.extract_cap, rows, seen_sha, seen_src, args.quiet, gzip_counters, failed_gzip_candidates, gzip_members, skipped_gzip_members, getattr(args, "include_failed_candidates", False), getattr(args, "include_non_ccsf_gzip", False), getattr(args, "ccsf_only", False), getattr(args, "gzip_only", False))
        except Exception as exc:
            rows.append({"source_iso_path": str(args.iso_path), "top_level_iso_file_path": internal, "container_path": str(staged), "source_offset": 0, "compression_layer": "none", "extracted_ccsf_path": None, "ccsf_name": "", "size": 0, "sha1": "", "duplicate_status": "", "extraction_status": "error", "error_warning": str(exc)})
        bytes_scanned_total += int(scanned_bytes or 0)
        container_rows.append({**entry, "path": internal, "staged_path": str(staged), "bytes_scanned": scanned_bytes, "ccsf_bundle_count": len([r for r in rows[before_rows:] if r.get("extraction_status") in {"extracted", "duplicate"}])})
        _emit_progress(progress_callback, _progress_event("container_done", current_container=internal, container_index=i, container_total=len(containers), bytes_scanned=bytes_scanned_total, gzip_offsets_seen=gzip_counters["gzip_offsets_seen"], gzip_valid_members=gzip_counters["gzip_valid_members"], false_positives_skipped=gzip_counters["gzip_false_positive_skipped"], ccsf_bundles_extracted=len([r for r in rows if r.get("extraction_status") == "extracted"]), assets_indexed=ccsf_assets_indexed))
    asset_index_path = reports / "ccsf_asset_index.json"
    asset_library_path = reports / "asset_library.json"
    asset_library_text_path = reports / "asset_library.txt"
    dashboard_path = reports / "ccsf_results_dashboard.html"
    asset_dashboard_path = reports / "asset_library_dashboard.html"
    asset_index: dict[str, Any] | None = None
    logical_library: dict[str, Any] | None = None
    if args.index_assets:
        asset_index = ccsf_asset_indexer.index_folder(out_dir, quiet=args.quiet, limit=getattr(args, "asset_limit", None), includes=args.include, excludes=args.exclude)
        ccsf_assets_indexed = int(asset_index.get("asset_count", 0))
        ccsf_asset_indexer.write_index(asset_index, asset_index_path, reports / "ccsf_asset_index.txt", summary_only=args.summary_only, max_report_rows=getattr(args, "max_report_rows", DEFAULT_MAX_REPORT_ROWS), jsonl_out=getattr(args, "asset_index_jsonl", None))
        _emit_progress(progress_callback, _progress_event("assets_indexed", container_total=len(containers), bytes_scanned=bytes_scanned_total, gzip_offsets_seen=gzip_counters["gzip_offsets_seen"], gzip_valid_members=gzip_counters["gzip_valid_members"], false_positives_skipped=gzip_counters["gzip_false_positive_skipped"], ccsf_bundles_extracted=len([r for r in rows if r.get("extraction_status") == "extracted"]), assets_indexed=ccsf_assets_indexed))
    confirmed = [r for r in rows if r.get("extraction_status") == "extracted"]
    duplicates = [r for r in rows if r.get("duplicate_status") == "duplicate"]
    gzip_with_ccsf = [m for m in gzip_members if m.get("contains_ccsf")]
    valid_gzip_members = gzip_members if getattr(args, "include_non_ccsf_gzip", False) else gzip_with_ccsf
    report_rows = rows
    if getattr(args, "ccsf_only", False):
        report_rows = [r for r in report_rows if r.get("extraction_status") in {"extracted", "duplicate"}]
    confirmed_bundles = [r for r in rows if r.get("extraction_status") in {"extracted", "duplicate"}]
    report = {"created_at": _now(), "iso_path": str(args.iso_path), "iso_index": str(index_path) if index_path else None, "workspace": str(workspace), "containers_selected": len(containers), "containers_scanned": len(containers), "extraction_count": len(confirmed), "duplicate_count": len(duplicates), **gzip_counters, "bytes_scanned": sum(int(c.get("bytes_scanned", 0)) for c in container_rows), "confirmed_ccsf_bundles_extracted": len(confirmed), "duplicates_skipped": len(duplicates), "ccsf_assets_indexed": ccsf_assets_indexed, "asset_index_path": str(asset_index_path) if args.index_assets else None, "asset_library_path": str(asset_library_path) if args.index_assets else None, "asset_library_text_path": str(asset_library_text_path) if args.index_assets else None, "results_dashboard_path": str(dashboard_path), "asset_library_dashboard_path": str(asset_dashboard_path), "containers": container_rows, "valid_gzip_members": valid_gzip_members, "gzip_members_with_ccsf": gzip_with_ccsf, "confirmed_ccsf_bundles": confirmed_bundles, "duplicates": duplicates, "skipped_gzip_members": skipped_gzip_members, "failed_gzip_candidates": failed_gzip_candidates, "extractions": report_rows}
    if args.index_assets and asset_index is not None:
        logical_library = asset_library.build_asset_library(asset_index, report)
        asset_library.write_library(logical_library, asset_library_path, asset_library_text_path, max_report_rows=getattr(args, "max_report_rows", DEFAULT_MAX_REPORT_ROWS))
    write_results_dashboard(report, asset_index, dashboard_path, logical_library)
    if dashboard_path != asset_dashboard_path:
        asset_dashboard_path.write_text(dashboard_path.read_text(encoding="utf-8"), encoding="utf-8")
    _emit_progress(progress_callback, _progress_event("complete", container_total=len(containers), bytes_scanned=bytes_scanned_total, gzip_offsets_seen=gzip_counters["gzip_offsets_seen"], gzip_valid_members=gzip_counters["gzip_valid_members"], false_positives_skipped=gzip_counters["gzip_false_positive_skipped"], ccsf_bundles_extracted=len(confirmed), assets_indexed=ccsf_assets_indexed))
    out_json.parent.mkdir(parents=True, exist_ok=True); text_out.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    text_out.write_text(format_text(report, summary_only=args.summary_only, max_report_rows=getattr(args, "max_report_rows", DEFAULT_MAX_REPORT_ROWS), max_failed_rows=getattr(args, "max_failed_rows", DEFAULT_MAX_FAILED_ROWS), include_failed_candidates=getattr(args, "include_failed_candidates", False), include_non_ccsf_gzip=getattr(args, "include_non_ccsf_gzip", False)), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract CCSF bundles from likely ISO containers.")
    ap.add_argument("iso_path")
    ap.add_argument("--iso-index")
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--out")
    ap.add_argument("--text-out")
    ap.add_argument("--max-scan-bytes", type=int, default=DEFAULT_MAX_SCAN_BYTES)
    ap.add_argument("--extract-cap", type=int, default=DEFAULT_EXTRACT_CAP)
    ap.add_argument("--container-limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--asset-limit", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None, help="Deprecated backward-compatible alias for --container-limit (container selection only)")
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--container", action="append", default=[])
    ap.add_argument("--build-index", action="store_true")
    ap.add_argument("--reuse-existing", action="store_true")
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--index-assets", action="store_true")
    ap.add_argument("--include-failed-candidates", action="store_true", help="Include failed gzip probes in text output and extraction rows")
    ap.add_argument("--include-non-ccsf-gzip", action="store_true", help="Include valid gzip members that do not contain CCSF bundles in text and extraction rows")
    ap.add_argument("--ccsf-only", action="store_true", help="Only include confirmed CCSF bundle rows in extraction output")
    ap.add_argument("--gzip-only", action="store_true", help="Only scan gzip members; skip direct uncompressed CCSF hits")
    ap.add_argument("--max-report-rows", type=int, default=DEFAULT_MAX_REPORT_ROWS, help="Maximum rows to show per text-report section; use a negative value for unlimited")
    ap.add_argument("--asset-index-jsonl", help="Optionally write one physical indexed asset per JSONL line when --index-assets is used")
    ap.add_argument("--max-failed-rows", type=int, default=DEFAULT_MAX_FAILED_ROWS, help="Maximum failed/skipped gzip rows to show in the text report")
    ap.add_argument("--progress-jsonl", action="store_true", help="Emit machine-readable progress events as JSON Lines on stderr")
    args = ap.parse_args(argv)
    progress_callback = (lambda event: print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)) if args.progress_jsonl else None
    run(args, progress_callback=progress_callback)
    if not args.quiet:
        print(f"Output JSON: {args.out or Path(args.workspace) / 'reports' / 'iso_ccsf_extraction_index.json'}")
        print(f"Output text: {args.text_out or Path(args.workspace) / 'reports' / 'iso_ccsf_extraction_index.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

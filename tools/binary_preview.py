#!/usr/bin/env python3
"""Read-only binary preview and embedded-candidate scanner.

This tool is intentionally conservative: normal preview mode reads only enough bytes to
classify and summarize a file, gzip previews decompress with explicit caps, and scan
mode walks the input in chunks without inflating embedded gzip candidates unless the
caller asks for bounded extraction.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import struct
import zlib
from collections import defaultdict
from pathlib import Path
from typing import BinaryIO, Iterator
from fragment_core import CCSF_SIG, scan_ascii_strings

GZIP_MAGIC = b"\x1f\x8b"
PLAIN_CCSF = b"CCSF"
FIRST_BYTES = 64
DEFAULT_READ_CAP = 16 * 1024 * 1024
DEFAULT_GZIP_PREVIEW_CAP = 2 * 1024 * 1024
DEFAULT_SCAN_CHUNK = 1024 * 1024
DEFAULT_SCAN_OVERLAP = 4096
DEFAULT_STRING_SCAN_CAP = 8 * 1024 * 1024
DEFAULT_MAX_STRINGS = 250
DEFAULT_MAX_SYMBOLS = 250
DEFAULT_MAX_CANDIDATES = 500
DEFAULT_EXTRACT_CAP = 32 * 1024 * 1024
EXTRACT_ROOT = Path("workspace/extracted/preview_candidates")

SYMBOL_PREFIXES = ("TEX_", "MDL_", "MAT_", "ANM_", "CAM_", "DMY_")
PATH_EXTS = {
    ".bin",
    ".ccsf",
    ".dat",
    ".gz",
    ".img",
    ".iso",
    ".pak",
    ".tm2",
    ".pss",
    ".vag",
    ".wav",
    ".bmp",
    ".png",
}
MODEL_EXTS = {".mdl", ".max", ".obj", ".fbx", ".glb", ".gltf"}
TEXTURE_EXTS = {".tex", ".tm2", ".bmp", ".png", ".dds", ".jpg", ".jpeg"}
ANIMATION_EXTS = {".anm", ".mot", ".bvh"}
AUDIO_EXTS = {".vag", ".wav", ".adx", ".aif", ".aiff", ".mp3", ".ogg"}

MAGIC_SIGNATURES = (
    (0, GZIP_MAGIC, "gzip"),
    (0, CCSF_SIG, "CCSF container"),
    (8, PLAIN_CCSF, "CCSF marker"),
    (0, b"\x7fELF", "ELF executable"),
    (0, b"TIM2", "TIM2/TM2 texture"),
    (0, b"TM2", "TIM2/TM2 texture"),
    (0, b"\x00\x00\x01\xba", "PSS/MPEG-like stream"),
    (0, b"\x00\x00\x01\xb3", "PSS/MPEG-like stream"),
    (0, b"VAGp", "VAGp audio"),
    (0, b"RIFF", "RIFF/WAV"),
    (0, b"\x89PNG\r\n\x1a\n", "PNG image"),
    (0, b"BM", "BMP image"),
)
SCAN_SIGNATURES = (
    (GZIP_MAGIC, "gzip"),
    (CCSF_SIG, "CCSF container"),
    (PLAIN_CCSF, "CCSF marker"),
    (b"\x7fELF", "ELF executable"),
    (b"TIM2", "TIM2/TM2 texture"),
    (b"TM2", "TIM2/TM2 texture"),
    (b"\x00\x00\x01\xba", "PSS/MPEG-like stream"),
    (b"\x00\x00\x01\xb3", "PSS/MPEG-like stream"),
    (b"VAGp", "VAGp audio"),
    (b"RIFF", "RIFF/WAV"),
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"BM", "BMP image"),
)


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _sha1_stream(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_head(path: Path, size: int = FIRST_BYTES) -> bytes:
    """Return at most ``size`` leading bytes for metadata and magic detection."""
    if size < 0:
        raise ValueError("size must be non-negative")
    with path.open("rb") as f:
        return f.read(size)


def iter_chunks(
    path: Path,
    chunk_size: int = DEFAULT_SCAN_CHUNK,
    max_scan_bytes: int | None = None,
    *,
    start_offset: int = 0,
) -> Iterator[tuple[int, bytes]]:
    """Yield bounded ``(offset, chunk)`` pairs from ``path`` for streaming scans."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if max_scan_bytes is not None and max_scan_bytes < 0:
        raise ValueError("max_scan_bytes must be non-negative")
    if start_offset < 0:
        raise ValueError("start_offset must be non-negative")

    remaining = max_scan_bytes
    with path.open("rb") as f:
        f.seek(start_offset)
        offset = start_offset
        while remaining is None or remaining > 0:
            to_read = chunk_size if remaining is None else min(chunk_size, remaining)
            chunk = f.read(to_read)
            if not chunk:
                break
            yield offset, chunk
            offset += len(chunk)
            if remaining is not None:
                remaining -= len(chunk)


def _read_range(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as f:
        f.seek(offset)
        return f.read(size)


def parse_gzip_header(data: bytes) -> dict[str, object]:
    """Parse bounded gzip header bytes without decompressing payload data."""
    info: dict[str, object] = {"is_gzip": data.startswith(GZIP_MAGIC)}
    if len(data) < 10 or not info["is_gzip"]:
        return info

    method = data[2]
    flags = data[3]
    pos = 10
    info.update(
        {
            "method": method,
            "flags": flags,
            "mtime": struct.unpack_from("<I", data, 4)[0],
            "extra_flags": data[8],
            "os": data[9],
        }
    )

    if flags & 0x04:  # FEXTRA
        if len(data) < pos + 2:
            info["header_truncated"] = True
            return info
        xlen = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        if len(data) < pos + xlen:
            info["header_truncated"] = True
            return info
        info["extra_length"] = xlen
        pos += xlen

    original_name = None
    if flags & 0x08 and pos < len(data):  # FNAME
        end = data.find(b"\x00", pos)
        if end == -1:
            info["header_truncated"] = True
            return info
        original_name = data[pos:end].decode("latin-1", errors="replace")
        pos = end + 1

    comment = None
    if flags & 0x10 and pos < len(data):  # FCOMMENT
        end = data.find(b"\x00", pos)
        if end == -1:
            info["header_truncated"] = True
            return info
        comment = data[pos:end].decode("latin-1", errors="replace")
        pos = end + 1

    if flags & 0x02:  # FHCRC
        if len(data) < pos + 2:
            info["header_truncated"] = True
            return info
        pos += 2

    info["original_filename"] = original_name
    info["comment"] = comment
    info["header_length"] = pos
    return info


def estimate_gzip_size(path: Path) -> int | None:
    try:
        if path.stat().st_size < 4:
            return None
        with path.open("rb") as f:
            f.seek(-4, 2)
            return struct.unpack("<I", f.read(4))[0]
    except OSError:
        return None


def safe_gzip_preview(path_or_file: Path | BinaryIO, max_output_bytes: int = DEFAULT_GZIP_PREVIEW_CAP) -> tuple[bytes, bool]:
    """Return a bounded gzip decompression preview using streaming reads."""
    if max_output_bytes < 0:
        raise ValueError("max_output_bytes must be non-negative")

    close_file = False
    if isinstance(path_or_file, Path):
        raw: BinaryIO = path_or_file.open("rb")
        close_file = True
    else:
        raw = path_or_file

    out = bytearray()
    try:
        with gzip.GzipFile(fileobj=raw, mode="rb") as gz:
            while len(out) < max_output_bytes:
                chunk = gz.read(min(64 * 1024, max_output_bytes - len(out)))
                if not chunk:
                    return bytes(out), False
                out.extend(chunk)
            return bytes(out), bool(gz.read(1))
    finally:
        if close_file:
            raw.close()


def gzip_preview(path: Path, cap: int) -> tuple[dict[str, object], bytes, list[str]]:
    warnings: list[str] = []
    prefix = read_head(path, 4096)
    info = parse_gzip_header(prefix)
    info["decompressed_size_estimate"] = estimate_gzip_size(path)
    try:
        data, truncated = safe_gzip_preview(path, cap)
        if truncated:
            warnings.append(f"gzip decompression preview capped at {cap:,} bytes")
        info["preview_truncated"] = truncated
    except Exception as exc:  # Corrupt gzip is data, not a tool failure.
        data = b""
        warnings.append(f"gzip preview failed: {exc}")
    info["decompressed_preview_bytes"] = len(data)
    return info, data, warnings


def detect_magic(data: bytes) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for offset, magic, name in MAGIC_SIGNATURES:
        if len(data) >= offset + len(magic) and data[offset : offset + len(magic)] == magic:
            hits.append({"type": name, "offset": offset, "magic_hex": _hex(magic)})
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WAVE":
        hits.append({"type": "WAV audio", "offset": 0, "magic_hex": "52 49 46 46 ... 57 41 56 45"})
    return hits


def classify_string(s: str) -> str:
    low = s.lower().replace("\\", "/")
    suffix = Path(low).suffix
    is_path = "/" in low or "\\" in s or suffix in PATH_EXTS | MODEL_EXTS | TEXTURE_EXTS | ANIMATION_EXTS | AUDIO_EXTS
    if suffix in MODEL_EXTS or "/mdl/" in low or low.startswith("s/m/"):
        return "model_paths"
    if suffix in TEXTURE_EXTS or "/tex/" in low:
        return "texture_paths"
    if suffix in ANIMATION_EXTS or "/anm/" in low:
        return "animation_paths"
    if suffix in AUDIO_EXTS or "/snd/" in low or "/se/" in low or "/bgm/" in low:
        return "audio_paths"
    if any(s.startswith(p) for p in SYMBOL_PREFIXES):
        return "symbols"
    if is_path:
        return "paths"
    return "unknown_strings"


def strings_with_offsets(data: bytes, minlen: int = 4, cap: int = DEFAULT_MAX_STRINGS) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    start: int | None = None
    for i, b in enumerate(data):
        if 32 <= b < 127:
            if start is None:
                start = i
            continue
        if start is not None and i - start >= minlen:
            s = data[start:i].decode("ascii", errors="ignore")
            out.append({"offset": start, "string": s, "class": classify_string(s)})
            if len(out) >= cap:
                return out
        start = None
    if start is not None and len(data) - start >= minlen and len(out) < cap:
        s = data[start:].decode("ascii", errors="ignore")
        out.append({"offset": start, "string": s, "class": classify_string(s)})
    return out


def _bounded_ascii_strings(data: bytes, minlen: int = 4) -> list[str]:
    """Call fragment_core.scan_ascii_strings only for bounded in-memory buffers."""
    if len(data) > DEFAULT_STRING_SCAN_CAP:
        raise ValueError(f"scan_ascii_strings buffer exceeds {DEFAULT_STRING_SCAN_CAP:,} bytes")
    return scan_ascii_strings(data, minlen=minlen)


def scan_printable_strings_streaming(
    path: Path,
    *,
    minlen: int = 4,
    chunk_size: int = DEFAULT_SCAN_CHUNK,
    max_scan_bytes: int = DEFAULT_STRING_SCAN_CAP,
    cap: int = DEFAULT_MAX_STRINGS,
) -> list[dict[str, object]]:
    """Scan printable strings with bounded chunks and a carry-over printable run."""
    if max_scan_bytes < 0:
        raise ValueError("max_scan_bytes must be non-negative")
    out: list[dict[str, object]] = []
    run = bytearray()
    run_start: int | None = None

    def flush() -> bool:
        nonlocal run, run_start
        if run_start is not None and len(run) >= minlen:
            data = bytes(run)
            # Keep fragment_core.scan_ascii_strings usage strictly on this bounded run.
            for s in _bounded_ascii_strings(data, minlen=minlen):
                out.append({"offset": run_start, "string": s, "class": classify_string(s)})
                if len(out) >= cap:
                    return True
        run = bytearray()
        run_start = None
        return False

    for base, chunk in iter_chunks(path, chunk_size=chunk_size, max_scan_bytes=max_scan_bytes):
        for i, b in enumerate(chunk):
            if 32 <= b < 127:
                if run_start is None:
                    run_start = base + i
                run.append(b)
                continue
            if flush():
                return out
        if len(run) >= DEFAULT_STRING_SCAN_CAP:
            if flush():
                return out
    flush()
    return out


def summarize_string_entries(
    entries: list[dict[str, object]],
    scanned_bytes: int,
    max_paths: int | None = None,
) -> dict[str, object]:
    grouped: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    path_classes = {"model_paths", "texture_paths", "animation_paths", "audio_paths", "paths"}
    for ent in entries:
        cls = str(ent["class"])
        s = str(ent["string"])
        if max_paths is not None and cls in path_classes and len(grouped[cls]) >= max_paths:
            continue
        if s not in seen[cls]:
            grouped[cls].append(s)
            seen[cls].add(s)
    return {
        "scanned_bytes": scanned_bytes,
        "returned_count": len(entries),
        "classes": dict(grouped),
    }


def summarize_strings(data: bytes, max_strings: int, max_paths: int | None = None) -> dict[str, object]:
    entries = strings_with_offsets(data, cap=max_strings)
    return summarize_string_entries(entries, len(data), max_paths)


def extract_symbols(data: bytes) -> dict[str, list[str]]:
    """Return unique prefixed symbols found anywhere in printable byte runs."""
    found: dict[str, set[str]] = {pfx: set() for pfx in SYMBOL_PREFIXES}
    pattern = re.compile(rb"\b(" + b"|".join(re.escape(p.encode("ascii")) for p in SYMBOL_PREFIXES) + rb")[A-Za-z0-9_]+")
    for match in pattern.finditer(data):
        sym = match.group(0).decode("ascii", errors="ignore")
        for pfx in SYMBOL_PREFIXES:
            if sym.startswith(pfx):
                found[pfx].add(sym)
                break
    return {pfx: sorted(values) for pfx, values in found.items()}


def symbol_summary(data: bytes, max_list: int) -> dict[str, object]:
    result: dict[str, object] = {}
    by_prefix = extract_symbols(data)
    for pfx in SYMBOL_PREFIXES:
        values = by_prefix[pfx]
        result[pfx] = {"count": len(values), "items": values[:max_list]}
    return result


def ccsf_summary(data: bytes) -> dict[str, object]:
    offsets = []
    start = 0
    while True:
        idx = data.find(CCSF_SIG, start)
        if idx == -1:
            break
        offsets.append(idx)
        start = idx + 1
    plain_offsets = []
    start = 0
    while True:
        idx = data.find(PLAIN_CCSF, start)
        if idx == -1:
            break
        if idx not in {o + 8 for o in offsets}:
            plain_offsets.append(idx)
        start = idx + 1
    section_guesses = [f"fragment_core_CCSF_SIG:{off:08X}" for off in offsets[:100]]
    section_guesses.extend(f"plain_CCSF:{off:08X}" for off in plain_offsets[:100])
    return {
        "fragment_core_CCSF_SIG_count": len(offsets),
        "fragment_core_CCSF_SIG_offsets": offsets[:100],
        "plain_CCSF_count": len(plain_offsets),
        "plain_CCSF_offsets": plain_offsets[:100],
        "section_guesses": section_guesses,
    }


def _first_detected_type(hits: list[dict[str, object]], default: str = "unknown") -> str:
    return str(hits[0]["type"]) if hits else default


def _summarize_nonempty_symbol_prefixes(symbols: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for pfx, info in symbols.items():
        if not isinstance(info, dict):
            continue
        count = int(info.get("count") or 0)
        items = info.get("items") if isinstance(info.get("items"), list) else []
        if count or items:
            summary[pfx] = {"count": count, "sample": items[:10]}
    return summary


def _summarize_path_classes(strings: dict[str, object]) -> dict[str, object]:
    classes = strings.get("classes") if isinstance(strings.get("classes"), dict) else {}
    path_classes = ("model_paths", "texture_paths", "animation_paths", "audio_paths", "paths")
    return {
        cls: vals[:10]
        for cls, vals in classes.items()
        if cls in path_classes and isinstance(vals, list) and vals
    }


def build_preview_chain(
    path: Path,
    *,
    source_type: str,
    gzip_info: dict[str, object] | None,
    decompressed_type: str | None,
    ccsf: dict[str, object],
    symbols: dict[str, object],
    strings: dict[str, object],
) -> list[dict[str, object]]:
    """Build a structured source/layer/content preview chain for JSON consumers."""
    chain: list[dict[str, object]] = [
        {"kind": "source", "path": str(path), "detected_type": source_type},
    ]
    if gzip_info is not None:
        chain.append(
            {
                "kind": "compression_layer",
                "type": "gzip",
                "original_filename": gzip_info.get("original_filename"),
                "decompressed_size_estimate": gzip_info.get("decompressed_size_estimate"),
                "preview_bytes": gzip_info.get("decompressed_preview_bytes"),
                "preview_truncated": gzip_info.get("preview_truncated"),
            }
        )
        chain.append(
            {
                "kind": "decompressed_preview",
                "name": gzip_info.get("original_filename"),
                "detected_type": decompressed_type or "unknown",
            }
        )

    ccsf_counts = int(ccsf.get("fragment_core_CCSF_SIG_count") or 0) + int(
        ccsf.get("plain_CCSF_count") or 0
    )
    symbol_summary_data = _summarize_nonempty_symbol_prefixes(symbols)
    path_summary_data = _summarize_path_classes(strings)
    if ccsf_counts or symbol_summary_data or path_summary_data:
        chain.append(
            {
                "kind": "content_preview",
                "description": (
                    "CCSF section/symbol preview"
                    if ccsf_counts or symbol_summary_data
                    else "string/path preview"
                ),
                "ccsf_offsets": {
                    "fragment_core_CCSF_SIG_offsets": ccsf.get("fragment_core_CCSF_SIG_offsets", []),
                    "plain_CCSF_offsets": ccsf.get("plain_CCSF_offsets", []),
                },
                "section_guesses": ccsf.get("section_guesses", []),
                "symbols": symbol_summary_data,
                "paths": path_summary_data,
            }
        )
    return chain


def render_chain(chain: object) -> str | None:
    if not isinstance(chain, list) or not chain:
        return None
    parts: list[str] = []
    for ent in chain:
        if not isinstance(ent, dict):
            continue
        kind = ent.get("kind")
        if kind == "source":
            parts.append(Path(str(ent.get("path") or "<source>")).name)
        elif kind == "compression_layer":
            parts.append(str(ent.get("type") or "compressed"))
            original = ent.get("original_filename")
            if original:
                parts.append(str(original))
        elif kind == "decompressed_preview":
            if ent.get("name") and (not parts or parts[-1] != ent.get("name")):
                parts.append(str(ent.get("name")))
        elif kind == "content_preview":
            parts.append(str(ent.get("description") or "content preview"))
    return " -> ".join(parts) if parts else None


def extract_gzip_candidate(path: Path, offset: int, out_dir: Path, cap: int) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = _read_range(path, offset, cap * 4)
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = bytearray()
    truncated = False
    try:
        out.extend(d.decompress(raw, cap))
        if not d.eof and len(out) >= cap:
            truncated = True
    except Exception as exc:
        return {"ok": False, "offset": offset, "error": str(exc)}
    out_path = out_dir / f"{path.stem}_off_{offset:08X}.gunz"
    out_path.write_bytes(out)
    return {"ok": True, "type": "gzip", "offset": offset, "path": str(out_path), "bytes": len(out), "truncated": truncated}


def extract_ccsf_candidate(path: Path, offset: int, out_dir: Path, cap: int) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    size = path.stat().st_size
    next_offsets = []
    scan_start = offset + len(CCSF_SIG)
    prev = b""
    for base, chunk in iter_chunks(path, chunk_size=DEFAULT_SCAN_CHUNK, max_scan_bytes=cap, start_offset=scan_start):
        if base >= size:
            break
        window = prev + chunk
        idx = window.find(CCSF_SIG)
        if idx != -1:
            hit = base - len(prev) + idx
            if hit > offset:
                next_offsets.append(hit)
                break
        prev = window[-len(CCSF_SIG) :]
    end = next_offsets[0] if next_offsets else min(size, offset + cap)
    data = _read_range(path, offset, end - offset)
    out_path = out_dir / f"{path.stem}_off_{offset:08X}.ccsf"
    out_path.write_bytes(data)
    return {"ok": True, "type": "CCSF", "offset": offset, "path": str(out_path), "bytes": len(data), "truncated": end == offset + cap and end < size}


def preview(path: Path, args: argparse.Namespace) -> dict[str, object]:
    size = path.stat().st_size
    prefix = read_head(path, max(FIRST_BYTES, min(args.read_cap, 4096)))
    first64 = prefix[:FIRST_BYTES]
    warnings: list[str] = []
    detected = detect_magic(prefix)
    scan_bytes = read_head(path, min(size, args.read_cap, args.string_scan_cap))

    gz_info: dict[str, object] | None = None
    gz_decompressed_type: str | None = None
    if prefix.startswith(GZIP_MAGIC):
        gz_info, gz_data, gz_warnings = gzip_preview(path, args.gzip_preview_cap)
        warnings.extend(gz_warnings)
        if args.decompress_out:
            out_path = Path(args.decompress_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "rb") as gz, out_path.open("wb") as out:
                copied = 0
                while copied < args.extract_cap:
                    chunk = gz.read(min(64 * 1024, args.extract_cap - copied))
                    if not chunk:
                        break
                    out.write(chunk)
                    copied += len(chunk)
                if copied >= args.extract_cap and gz.read(1):
                    warnings.append(f"--decompress-out capped at {args.extract_cap:,} bytes")
            gz_info["decompress_out"] = str(out_path)
        if gz_data:
            scan_bytes = gz_data[: args.string_scan_cap]
            gz_detected = detect_magic(gz_data[:4096])
            gz_decompressed_type = _first_detected_type(gz_detected)
            gz_info["decompressed_detected_type"] = gz_decompressed_type
            gz_info["decompressed_magic_hits"] = gz_detected
            if gz_detected:
                detected.extend({**hit, "inside": "gzip_preview"} for hit in gz_detected)

    if prefix.startswith(GZIP_MAGIC):
        string_report = summarize_strings(scan_bytes, args.max_strings, args.max_paths)
    else:
        string_scan_bytes = min(size, args.read_cap, args.string_scan_cap)
        string_entries = scan_printable_strings_streaming(
            path,
            chunk_size=args.scan_chunk,
            max_scan_bytes=string_scan_bytes,
            cap=args.max_strings,
        )
        string_report = summarize_string_entries(string_entries, string_scan_bytes, args.max_paths)

    source_type = _first_detected_type(detected)
    ccsf_report = ccsf_summary(scan_bytes)
    if (
        gz_info is not None
        and (gz_decompressed_type is None or gz_decompressed_type == "unknown")
        and (
            int(ccsf_report.get("fragment_core_CCSF_SIG_count") or 0)
            or int(ccsf_report.get("plain_CCSF_count") or 0)
        )
    ):
        gz_decompressed_type = "CCSF section/symbol preview"
        gz_info["decompressed_detected_type"] = gz_decompressed_type
    symbols_report = symbol_summary(scan_bytes, args.max_symbols)
    report = {
        "path": str(path),
        "size": size,
        "sha1": _sha1_stream(path),
        "first_64_bytes_hex": _hex(first64),
        "detected_type": source_type,
        "magic_hits": detected,
        "warnings": warnings,
        "gzip": gz_info,
        "ccsf": ccsf_report,
        "symbols": symbols_report,
        "strings": string_report,
        "chain": build_preview_chain(
            path,
            source_type=source_type,
            gzip_info=gz_info,
            decompressed_type=gz_decompressed_type,
            ccsf=ccsf_report,
            symbols=symbols_report,
            strings=string_report,
        ),
    }
    if size > len(scan_bytes) and not prefix.startswith(GZIP_MAGIC):
        report["warnings"].append(f"content preview capped at {len(scan_bytes):,} of {size:,} bytes")
    return report


def nearby_strings(path: Path, offset: int, radius: int, cap: int) -> list[str]:
    start = max(0, offset - radius)
    data = _read_range(path, start, radius * 2)
    vals = strings_with_offsets(data, cap=cap)
    near = []
    for ent in vals:
        ent_start = start + int(ent["offset"])
        ent_end = ent_start + len(str(ent["string"]))
        if abs(ent_start - offset) <= radius or ent_start <= offset <= ent_end:
            near.append(str(ent["string"]))
    return near[:cap]


def scan_container(path: Path, args: argparse.Namespace) -> dict[str, object]:
    size = path.stat().st_size
    max_scan_bytes = min(size, args.max_scan_bytes) if args.max_scan_bytes is not None else size
    candidates: list[dict[str, object]] = []
    seen: set[tuple[int, str]] = set()
    max_magic = max(len(sig) for sig, _ in SCAN_SIGNATURES)
    overlap = max(args.scan_overlap, max_magic + 64)
    prev = b""
    for base, chunk in iter_chunks(path, chunk_size=args.scan_chunk, max_scan_bytes=max_scan_bytes):
        window = prev + chunk
        window_base = base - len(prev)
        for sig, kind in SCAN_SIGNATURES:
            start = 0
            while True:
                idx = window.find(sig, start)
                if idx == -1:
                    break
                abs_off = window_base + idx
                if 0 <= abs_off < max_scan_bytes and (abs_off, kind) not in seen:
                    candidates.append({"offset": abs_off, "type": kind, "magic_hex": _hex(sig)})
                    seen.add((abs_off, kind))
                    if len(candidates) >= args.max_candidates:
                        break
                start = idx + 1
            if len(candidates) >= args.max_candidates:
                break
        if len(candidates) >= args.max_candidates:
            break
        prev = window[-overlap:]

    for cand in candidates:
        cand["nearby_strings"] = nearby_strings(path, int(cand["offset"]), args.nearby_radius, args.nearby_strings)

    string_entries = scan_printable_strings_streaming(
        path,
        chunk_size=args.scan_chunk,
        max_scan_bytes=max_scan_bytes,
        cap=args.max_strings,
    )
    string_report = summarize_string_entries(string_entries, max_scan_bytes, args.max_paths)
    symbol_bytes = read_head(path, min(max_scan_bytes, args.string_scan_cap))

    extracted: list[dict[str, object]] = []
    if args.extract_candidates:
        out_dir = Path(args.extract_dir)
        extract_source = candidates
        if args.candidate_offset is not None:
            extract_source = [cand for cand in candidates if int(cand["offset"]) == args.candidate_offset]
            if not extract_source:
                extract_source = [{"offset": args.candidate_offset, "type": args.candidate_type or "gzip", "magic_hex": ""}]
        for cand in extract_source:
            kind = str(cand["type"])
            off = int(cand["offset"])
            if kind == "gzip":
                extracted.append(extract_gzip_candidate(path, off, out_dir, args.extract_cap))
            elif kind == "CCSF container":
                extracted.append(extract_ccsf_candidate(path, off, out_dir, args.extract_cap))
    return {
        "path": str(path),
        "size": size,
        "scan_chunk": args.scan_chunk,
        "scanned_bytes": max_scan_bytes,
        "candidate_count": len(candidates),
        "candidate_cap_hit": len(candidates) >= args.max_candidates,
        "candidates": candidates,
        "symbols": symbol_summary(symbol_bytes, args.max_symbols),
        "strings": string_report,
        "extracted": extracted,
    }


def render_text(report: dict[str, object]) -> str:
    lines = [
        f"Path: {report.get('path')}",
        f"Size: {report.get('size'):,} bytes",
    ]
    if "sha1" in report:
        lines.extend(
            [
                f"SHA1: {report.get('sha1')}",
                f"First 64 bytes: {report.get('first_64_bytes_hex')}",
                f"Detected type: {report.get('detected_type')}",
            ]
        )
        chain_text = render_chain(report.get("chain"))
        if chain_text:
            lines.append(f"Chain: {chain_text}")
        if report.get("warnings"):
            lines.append("Warnings:")
            lines.extend(f"  - {w}" for w in report["warnings"])  # type: ignore[index]
        lines.append("Magic hits:")
        for hit in report.get("magic_hits", []):  # type: ignore[assignment]
            lines.append(f"  - {hit}")
        if report.get("gzip"):
            lines.append(f"Gzip: {report['gzip']}")
        lines.append(f"CCSF: {report.get('ccsf')}")
        lines.append("Symbols:")
        for pfx, info in report.get("symbols", {}).items():  # type: ignore[union-attr]
            lines.append(f"  {pfx}: {info['count']} {info['items']}")
        lines.append("Strings:")
        for cls, vals in report.get("strings", {}).get("classes", {}).items():  # type: ignore[union-attr]
            lines.append(f"  {cls}: {vals}")
    else:
        lines.append(f"Candidate count: {report.get('candidate_count')}")
        for cand in report.get("candidates", []):  # type: ignore[assignment]
            lines.append(f"  - 0x{cand['offset']:08X} {cand['type']} nearby={cand.get('nearby_strings', [])}")
        if report.get("symbols"):
            lines.append("Symbols:")
            for pfx, info in report.get("symbols", {}).items():  # type: ignore[union-attr]
                lines.append(f"  {pfx}: {info.get('items', [])}")
        if report.get("strings"):
            lines.append("Strings:")
            for cls, vals in report.get("strings", {}).get("classes", {}).items():  # type: ignore[union-attr]
                lines.append(f"  {cls}: {vals}")
        if report.get("extracted"):
            lines.append("Extracted:")
            for ent in report.get("extracted", []):  # type: ignore[assignment]
                lines.append(f"  - {ent}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Read-only binary preview and embedded-candidate scanner.")
    ap.add_argument("path", help="Binary file to preview or scan")
    ap.add_argument("--json", action="store_true", help="Print JSON instead of text")
    ap.add_argument("--out", help="Write JSON report to this path")
    ap.add_argument("--text-out", help="Write rendered text report to this path")
    ap.add_argument("--scan", action="store_true", help="Scan as a container for embedded candidate files")
    ap.add_argument("--read-cap", type=int, default=DEFAULT_READ_CAP, help="Max bytes read for normal content preview")
    ap.add_argument("--string-scan-cap", type=int, default=DEFAULT_STRING_SCAN_CAP, help="Max bytes scanned for strings")
    ap.add_argument("--gzip-preview-cap", type=int, default=DEFAULT_GZIP_PREVIEW_CAP, help="Max decompressed gzip bytes used for preview")
    ap.add_argument("--decompress-out", help="Optional bounded gzip decompression output path")
    ap.add_argument("--extract-cap", type=int, default=DEFAULT_EXTRACT_CAP, help="Max bytes per decompression/extraction helper")
    ap.add_argument("--max-strings", type=int, default=DEFAULT_MAX_STRINGS, help="Max printable strings to return")
    ap.add_argument("--max-paths", type=int, default=None, help="Max path-like strings to list per path class")
    ap.add_argument("--max-symbols", type=int, default=DEFAULT_MAX_SYMBOLS, help="Max symbols to list per prefix")
    ap.add_argument("--scan-chunk", type=int, default=DEFAULT_SCAN_CHUNK, help="Chunk size for --scan")
    ap.add_argument("--max-scan-bytes", type=int, default=None, help="Max input bytes to scan in --scan mode")
    ap.add_argument("--scan-overlap", type=int, default=DEFAULT_SCAN_OVERLAP, help="Overlap bytes for --scan")
    ap.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES, help="Max embedded candidates in --scan")
    ap.add_argument("--nearby-radius", type=int, default=256, help="Bytes around a candidate used for nearby strings")
    ap.add_argument("--nearby-strings", type=int, default=8, help="Max nearby strings per candidate")
    ap.add_argument("--extract-candidates", action="store_true", help="Extract bounded gzip/CCSF candidates found by --scan")
    ap.add_argument("--candidate-offset", type=int, help="Extract only the candidate at this absolute offset")
    ap.add_argument("--candidate-type", help="Candidate type hint used with --candidate-offset")
    ap.add_argument("--extract-dir", default=str(EXTRACT_ROOT), help="Output dir for --extract-candidates")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()
    path = Path(args.path)
    if not path.is_file():
        raise SystemExit(f"Not a file: {path}")
    report = scan_container(path, args) if args.scan else preview(path, args)
    rendered_text = render_text(report)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.text_out:
        Path(args.text_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.text_out).write_text(rendered_text + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(rendered_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

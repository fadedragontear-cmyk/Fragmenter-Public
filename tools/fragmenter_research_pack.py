#!/usr/bin/env python3
"""Build safe Fragmenter research reports and shareable report packages.

This tool is intentionally conservative.  The ``safe-scan`` mode records metadata,
small bounded string samples, and structural clues from local Area Server / ISO
inputs without copying game binaries into the workspace.  The ``package-export``
mode creates a ZIP containing only report-style files from the workspace.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import os
import re
import stat
import struct
import time
import unicodedata
import zipfile
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from iso9660 import Iso9660

CCSF_SIG = b"\x01\x00\xcc\xcc\r\x00\x00\x00CCSF"
CONFIRMED = "confirmed"
PROBABLE = "probable"
INFERRED = "inferred"
UNKNOWN = "unknown"
README_FOR_CHATGPT_TEXT = "Analyze this package to identify likely root-town files, textures, materials, dummies/markers, NPC/location clues, and suggest the next safe modding experiments."
README_FOR_CHATGPT_NAME = "README_FOR_CHATGPT.txt"

TEXT_EXTENSIONS = {
    ".json",
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".log",
    ".html",
    ".htm",
}
BINARY_EXTENSIONS = {
    ".bin",
    ".dat",
    ".iso",
    ".img",
    ".ccs",
    ".ccsf",
    ".elf",
    ".exe",
    ".dll",
    ".pak",
    ".arc",
    ".bmp",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".wav",
    ".adx",
    ".pss",
    ".tm2",
    ".gz",
    ".zip",
    ".7z",
    ".rar",
}

CLUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("town.bin", re.compile(r"town\.bin", re.IGNORECASE)),
    ("CCSFtown04", re.compile(r"CCSFtown04", re.IGNORECASE)),
    ("Fort Ouph", re.compile(r"Fort\s+Ouph", re.IGNORECASE)),
    ("CCSF", re.compile(r"CCSF", re.IGNORECASE)),
    ("CCS", re.compile(r"\bCCS\b|\.ccs\b", re.IGNORECASE)),
    ("DATA.bin", re.compile(r"DATA\.bin", re.IGNORECASE)),
]
CATEGORY_PREFIXES = ("TEX_", "MDL_", "DMY_", "MAT_", "ANM_", "CAM_", "SND_", "EFF_")
ASSET_PATH_RE = re.compile(r"(?:^|\s)(s[\\/][A-Za-z0-9_./\\-]{2,80})")


@dataclass(frozen=True)
class ScanLimits:
    max_files_per_root: int = 20000
    max_bytes_for_full_hash: int = 64 * 1024 * 1024
    sample_bytes: int = 1024 * 1024
    string_sample_limit: int = 80
    strings_per_file: int = 40
    max_sections_per_file: int = 128
    max_iso_entries: int = 200000
    max_embedded_gzip_scan_bytes: int = 64 * 1024 * 1024
    max_embedded_gzip_candidates: int = 256
    max_embedded_gzip_decompressed_bytes: int = 1024 * 1024


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def is_probably_game_binary(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return True
    name = path.name.lower()
    return name in {"data.bin", "town.bin"} or name.endswith((".ccsf", ".ccs"))


def likely_extension(path: Path, header: bytes) -> dict[str, Any]:
    suffix = path.suffix.lower() or "(none)"
    magic = UNKNOWN
    if header.startswith(b"\x1f\x8b"):
        magic = "gzip"
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        magic = "png"
    elif header.startswith(b"BM"):
        magic = "bmp"
    elif header.startswith(b"\xff\xd8\xff"):
        magic = "jpeg"
    elif b"CD001" in header[:0x9000]:
        magic = "iso9660"
    elif CCSF_SIG in header or b"CCSF" in header[:4096]:
        magic = "ccsf-like"
    elif header.startswith(b"ELF") or header.startswith(b"\x7fELF"):
        magic = "elf-like"
    return {"path_extension": suffix, "magic_guess": magic}


def file_checksums(path: Path, size: int, limits: ScanLimits) -> dict[str, Any]:
    out: dict[str, Any] = {"algorithm_note": "Full SHA-256 is recorded only for files at or below max_bytes_for_full_hash."}
    if size <= limits.max_bytes_for_full_hash:
        h = hashlib.sha256()
        crc = 0
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
                crc = zlib.crc32(chunk, crc)
        out["sha256"] = h.hexdigest()
        out["crc32"] = f"{crc & 0xffffffff:08x}"
        out["confidence"] = CONFIRMED
        return out

    with path.open("rb") as fh:
        head = fh.read(limits.sample_bytes)
        if size > limits.sample_bytes:
            fh.seek(max(0, size - limits.sample_bytes))
            tail = fh.read(limits.sample_bytes)
        else:
            tail = b""
    sample = head + tail
    out.update(
        {
            "sha256_head_tail_sample": hashlib.sha256(sample).hexdigest(),
            "crc32_head_tail_sample": f"{zlib.crc32(sample) & 0xffffffff:08x}",
            "sampled_bytes": len(sample),
            "confidence": INFERRED,
        }
    )
    return out


def iter_ascii_strings(data: bytes, min_len: int = 4) -> Iterable[str]:
    cur = bytearray()
    for b in data:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= min_len:
                yield cur.decode("ascii", errors="ignore")
            cur.clear()
    if len(cur) >= min_len:
        yield cur.decode("ascii", errors="ignore")


def _is_cp932_lead_byte(b: int) -> bool:
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def _is_cp932_trail_byte(b: int) -> bool:
    return 0x40 <= b <= 0x7E or 0x80 <= b <= 0xFC


def _is_cp932_single_byte_text(b: int) -> bool:
    return 32 <= b < 127 or b in {0x09, 0x0A, 0x0D} or 0xA1 <= b <= 0xDF


def iter_cp932_strings(data: bytes, min_len: int = 4) -> Iterable[str]:
    """Yield defensive CP932 string candidates from bounded bytes.

    Candidate runs are limited to printable ASCII/control whitespace, half-width
    kana, and syntactically valid CP932 double-byte pairs.  Any unexpected or
    malformed byte terminates the current run; decoding still uses replacement
    so malformed input can never abort a scan.
    """
    cur = bytearray()
    char_count = 0
    idx = 0
    while idx < len(data):
        b = data[idx]
        if _is_cp932_single_byte_text(b):
            cur.append(b)
            char_count += 1
            idx += 1
            continue
        if _is_cp932_lead_byte(b) and idx + 1 < len(data) and _is_cp932_trail_byte(data[idx + 1]):
            cur.extend(data[idx : idx + 2])
            char_count += 1
            idx += 2
            continue
        if char_count >= min_len:
            yield cur.decode("cp932", errors="replace")
        cur.clear()
        char_count = 0
        idx += 1
    if char_count >= min_len:
        yield cur.decode("cp932", errors="replace")


def normalize_string_for_dedupe(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def dedupe_normalized_strings(strings: Iterable[str], limit: int | None = None, existing: set[str] | None = None) -> list[str]:
    samples: list[str] = []
    seen = set() if existing is None else existing
    for value in strings:
        normalized = normalize_string_for_dedupe(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        samples.append(value)
        if limit is not None and len(samples) >= limit:
            break
    return samples


def bounded_file_sample(path: Path, size: int, limits: ScanLimits) -> bytes:
    with path.open("rb") as fh:
        head = fh.read(limits.sample_bytes)
        if size > limits.sample_bytes * 2:
            fh.seek(max(0, size - limits.sample_bytes))
            return head + fh.read(limits.sample_bytes)
        if size > limits.sample_bytes:
            return head + fh.read(limits.sample_bytes)
        return head


def split_ccsf_sections(blob: bytes, max_sections: int) -> list[tuple[int, str, int, int]]:
    offsets: list[int] = []
    start = 0
    while len(offsets) < max_sections:
        idx = blob.find(CCSF_SIG, start)
        if idx < 0:
            break
        offsets.append(idx)
        start = idx + 1
    sections: list[tuple[int, str, int, int]] = []
    for i, off in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else len(blob)
        section_id = f"UNKNOWN_{i:03d}"
        if off + 16 <= len(blob):
            try:
                typ, mark, length = struct.unpack_from("<HHI", blob, off)
            except struct.error:
                typ, mark, length = 0, 0, 0
            if typ == 1 and mark == 0xCCCC and 0 <= length <= len(blob) - off - 8:
                raw = blob[off + 8 : off + 8 + length]
                section_id = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace") or section_id
        sections.append((i, section_id, off, end))
    return sections


def summarize_strings(strings: list[str], limit: int) -> dict[str, Any]:
    samples: list[str] = []
    seen: set[str] = set()
    prefix_counts = Counter()
    asset_paths: set[str] = set()
    clue_hits: dict[str, list[str]] = defaultdict(list)
    for s in strings:
        for prefix in CATEGORY_PREFIXES:
            if s.startswith(prefix):
                prefix_counts[prefix] += 1
        for match in ASSET_PATH_RE.finditer(s):
            asset_paths.add(match.group(1).replace("\\", "/").lower())
        for label, pattern in CLUE_PATTERNS:
            if pattern.search(s) and len(clue_hits[label]) < 8:
                clue_hits[label].append(s[:160])
        if len(samples) < limit and s not in seen:
            samples.append(s[:160])
            seen.add(s)
    return {
        "sample_count": len(samples),
        "samples": samples,
        "category_prefix_counts": dict(sorted(prefix_counts.items())),
        "asset_path_samples": sorted(asset_paths)[:limit],
        "clue_string_hits": dict(sorted(clue_hits.items())),
    }


def _parse_gzip_original_filename(header: bytes) -> str | None:
    """Return the gzip FNAME header field from bounded bytes, when present."""
    if len(header) < 10 or header[:2] != b"\x1f\x8b":
        return None
    flags = header[3]
    idx = 10
    if flags & 0x04:  # FEXTRA
        if idx + 2 > len(header):
            return None
        extra_len = int.from_bytes(header[idx : idx + 2], "little")
        idx += 2 + extra_len
    if flags & 0x08:  # FNAME
        end = header.find(b"\x00", idx)
        if end < 0:
            return None
        return header[idx:end].decode("latin-1", errors="replace")
    return None


def _gzip_highlight_labels(source_path: Path, original_name: str | None, strings: list[str], sections: list[dict[str, Any]]) -> list[str]:
    text = "\n".join([source_path.name, original_name or "", *strings, *(sec.get("id", "") for sec in sections)]).lower()
    labels: list[str] = []
    if source_path.name.lower() == "town.bin":
        labels.append("priority-source:town.bin")
    if "town04.cmp" in text or "ccsftown04" in text:
        labels.append("special-highlight:town04.cmp")
    if "town04d.cmp" in text or "ccsftown04d" in text:
        labels.append("special-highlight:town04d.cmp")
    return labels


def scan_embedded_gzip_members(path: Path, size: int, limits: ScanLimits) -> dict[str, Any]:
    """Bounded defensive scanner for gzip members embedded in .bin/.dat files."""
    if path.suffix.lower() not in {".bin", ".dat"} and path.name.lower() not in {"town.bin", "data.bin"}:
        return {"scanned": False, "reason": "not a .bin/.dat container", "members": [], "confidence": UNKNOWN}

    max_scan = min(size, limits.max_embedded_gzip_scan_bytes)
    members: list[dict[str, Any]] = []
    with path.open("rb") as fh:
        window = fh.read(max_scan)

    start = 0
    while len(members) < limits.max_embedded_gzip_candidates:
        off = window.find(b"\x1f\x8b", start)
        if off < 0:
            break
        start = off + 1
        record: dict[str, Any] = {
            "source_container_path": str(path),
            "offset": off,
            "gzip_original_filename": _parse_gzip_original_filename(window[off : off + 4096]),
            "confidence": UNKNOWN,
        }
        try:
            with path.open("rb") as raw:
                raw.seek(off)
                decomp = zlib.decompressobj(16 + zlib.MAX_WBITS)
                chunks: list[bytes] = []
                produced = 0
                capped = False
                compressed_end: int | None = None
                while not decomp.eof:
                    chunk = raw.read(64 * 1024)
                    if not chunk:
                        raise EOFError("gzip candidate ended before gzip stream footer")
                    out = decomp.decompress(chunk, max(0, limits.max_embedded_gzip_decompressed_bytes + 1 - produced))
                    if out:
                        chunks.append(out)
                        produced += len(out)
                    if decomp.eof:
                        compressed_end = raw.tell() - len(decomp.unused_data) - len(decomp.unconsumed_tail)
                        break
                    if produced > limits.max_embedded_gzip_decompressed_bytes:
                        capped = True
                        break
                sample = b"".join(chunks)
            capped = len(sample) > limits.max_embedded_gzip_decompressed_bytes
            if capped:
                sample = sample[: limits.max_embedded_gzip_decompressed_bytes]
            strings = dedupe_normalized_strings(
                [
                    *dedupe_normalized_strings(iter_ascii_strings(sample), limits.strings_per_file),
                    *dedupe_normalized_strings(iter_cp932_strings(sample), limits.strings_per_file),
                ],
                limits.strings_per_file * 2,
            )
            sections_raw = split_ccsf_sections(sample, limits.max_sections_per_file)
            sections = []
            for idx, sid, sec_off, sec_end in sections_raw:
                sec_summary = summarize_strings(dedupe_normalized_strings(iter_ascii_strings(sample[sec_off:sec_end]), 24), 12)
                sections.append(
                    {
                        "index": idx,
                        "id": sid,
                        "sample_offset": sec_off,
                        "sample_end": sec_end,
                        "sample_size": sec_end - sec_off,
                        "category_prefix_counts": sec_summary["category_prefix_counts"],
                        "asset_path_samples": sec_summary["asset_path_samples"][:12],
                        "clue_string_hits": sec_summary["clue_string_hits"],
                    }
                )
            summary = summarize_strings(strings, limits.string_sample_limit)
            record.update(
                {
                    "compressed_size": compressed_end - off if compressed_end is not None and compressed_end > off else None,
                    "decompressed_sample_size": len(sample),
                    "decompressed_sample_cap": limits.max_embedded_gzip_decompressed_bytes,
                    "decompressed_sample_capped": capped,
                    "strings": summary,
                    "ccsf_like": {
                        "signature_found_in_sample": bool(sections),
                        "section_count_in_sample": len(sections),
                        "sections": sections,
                    },
                    "highlight_labels": _gzip_highlight_labels(path, record["gzip_original_filename"], strings, sections),
                    "confidence": PROBABLE if sections or strings else INFERRED,
                }
            )
        except (OSError, EOFError, gzip.BadGzipFile, zlib.error, struct.error) as exc:
            record.update(
                {
                    "compressed_size": None,
                    "decompressed_sample_size": 0,
                    "decompressed_sample_cap": limits.max_embedded_gzip_decompressed_bytes,
                    "error": f"{type(exc).__name__}: {exc}",
                    "basis": "Magic bytes were present, but the candidate was not a readable bounded gzip member.",
                    "confidence": UNKNOWN,
                }
            )
        members.append(record)

    return {
        "scanned": True,
        "scan_bytes": max_scan,
        "candidate_count": len(members),
        "candidate_limit_reached": len(members) >= limits.max_embedded_gzip_candidates,
        "priority": "town.bin is explicitly prioritized/highlighted when it is the source container." if path.name.lower() == "town.bin" else None,
        "members": members,
        "confidence": PROBABLE if any(m.get("confidence") in {PROBABLE, CONFIRMED} for m in members) else UNKNOWN,
    }


def confidence_for_file_clue(label: str, path: Path, strings: list[str], sections: list[dict[str, Any]]) -> str:
    name = path.name.lower()
    if label == "town.bin" and name == "town.bin":
        return CONFIRMED
    if label == "DATA.bin" and name == "data.bin":
        return CONFIRMED
    if label == "CCSFtown04" and any(sec.get("id") == "CCSFtown04" for sec in sections):
        return CONFIRMED
    if any(label.lower() in s.lower() for s in strings):
        return PROBABLE
    if label.lower() in path.as_posix().lower():
        return PROBABLE
    return INFERRED


def scan_one_file(path: Path, root: Path, role: str, limits: ScanLimits) -> dict[str, Any]:
    st = path.stat()
    size = st.st_size
    sample = bounded_file_sample(path, size, limits)
    ascii_strings = dedupe_normalized_strings(iter_ascii_strings(sample), limits.strings_per_file)
    ascii_seen = {normalize_string_for_dedupe(s) for s in ascii_strings}
    cp932_strings = dedupe_normalized_strings(iter_cp932_strings(sample), limits.strings_per_file, ascii_seen)
    strings = dedupe_normalized_strings([*ascii_strings, *cp932_strings], limits.strings_per_file * 2)
    sections_raw = split_ccsf_sections(sample, limits.max_sections_per_file)
    sections: list[dict[str, Any]] = []
    for idx, sid, off, end in sections_raw:
        sec_bytes = sample[off:end]
        sec_ascii_strings = dedupe_normalized_strings(iter_ascii_strings(sec_bytes), limits.string_sample_limit)
        sec_ascii_seen = {normalize_string_for_dedupe(s) for s in sec_ascii_strings}
        sec_cp932_strings = dedupe_normalized_strings(iter_cp932_strings(sec_bytes), limits.string_sample_limit, sec_ascii_seen)
        sec_strings = dedupe_normalized_strings([*sec_ascii_strings, *sec_cp932_strings], limits.string_sample_limit * 2)
        sec_summary = summarize_strings(sec_strings, 12)
        sections.append(
            {
                "index": idx,
                "id": sid,
                "sample_offset": off,
                "sample_end": end,
                "sample_size": len(sec_bytes),
                "sha256_sample": hashlib.sha256(sec_bytes).hexdigest(),
                "category_prefix_counts": sec_summary["category_prefix_counts"],
                "asset_path_samples": sec_summary["asset_path_samples"][:12],
                "clue_string_hits": sec_summary["clue_string_hits"],
            }
        )
    string_summary = summarize_strings(strings, limits.string_sample_limit)
    string_summary["ascii_samples"] = [s[:160] for s in ascii_strings[: limits.string_sample_limit]]
    string_summary["cp932_samples"] = [s[:160] for s in cp932_strings[: limits.string_sample_limit]]
    string_summary["sources"] = {"ascii": len(ascii_strings), "cp932": len(cp932_strings)}
    clue_records = []
    combined_text = "\n".join([path.as_posix(), *strings, *(sec.get("id", "") for sec in sections)])
    for label, pattern in CLUE_PATTERNS:
        if pattern.search(combined_text):
            clue_records.append(
                {
                    "label": label,
                    "confidence": confidence_for_file_clue(label, path, strings, sections),
                    "basis": "Matched file path, bounded string sample, or CCSF-like section id. This is a clue unless the confidence is confirmed.",
                }
            )
    info = {
        "role": role,
        "path": str(path),
        "relative_path": safe_rel(path, root),
        "name": path.name,
        "size": size,
        "mtime_utc": _dt.datetime.fromtimestamp(st.st_mtime, _dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mode": stat.filemode(st.st_mode),
        "likely_extension": likely_extension(path, sample[:65536]),
        "checksums": file_checksums(path, size, limits),
        "strings": string_summary,
        "ccsf_like": {
            "signature_found_in_sample": bool(sections),
            "section_count_in_sample": len(sections),
            "sections": sections,
            "confidence": CONFIRMED if sections else UNKNOWN,
        },
        "embedded_cmp_members": scan_embedded_gzip_members(path, size, limits),
        "clues": clue_records,
        "copyright_safety": "Metadata and bounded string samples only; file bytes were not copied to the workspace.",
    }
    return info


def iter_files(root: Path, limits: ScanLimits) -> Iterable[Path]:
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "workspace", "node_modules"}]
        for filename in sorted(filenames):
            if count >= limits.max_files_per_root:
                return
            p = Path(dirpath) / filename
            if p.is_file():
                count += 1
                yield p


def scan_root(root: Path | None, role: str, limits: ScanLimits) -> dict[str, Any] | None:
    if root is None:
        return None
    root = root.expanduser().resolve()
    result: dict[str, Any] = {"role": role, "root": str(root), "exists": root.exists(), "files": [], "errors": []}
    if not root.exists():
        result["confidence"] = UNKNOWN
        result["errors"].append("Path does not exist.")
        return result
    if root.is_file():
        targets = [root]
        base = root.parent
    else:
        targets = list(iter_files(root, limits))
        base = root
    for p in targets:
        try:
            result["files"].append(scan_one_file(p, base, role, limits))
        except OSError as exc:
            result["errors"].append({"path": str(p), "error": str(exc)})
    result["file_count"] = len(result["files"])
    result["confidence"] = CONFIRMED if result["exists"] else UNKNOWN
    return result


def scan_iso(iso_path: Path | None, data_bin_path: Path | None, limits: ScanLimits) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": "iso",
        "path": str(iso_path) if iso_path is not None else None,
        "exists": False,
        "entries": [],
        "errors": [],
        "notes": [],
        "data_bin_relationships": [],
    }
    if iso_path is None:
        result["confidence"] = UNKNOWN
        result["notes"].append("ISO path not provided; bounded ISO search skipped.")
        if data_bin_path is None:
            result["notes"].append("DATA.bin path not provided; ISO/DATA.bin relationship check skipped.")
        else:
            result["notes"].append("DATA.bin path provided, but ISO/DATA.bin relationship check requires an ISO path and was skipped.")
        return result

    iso_path = iso_path.expanduser().resolve()
    result["path"] = str(iso_path)
    result["exists"] = iso_path.exists()
    if not iso_path.exists():
        result["confidence"] = UNKNOWN
        result["errors"].append("ISO path does not exist.")
        if data_bin_path is None:
            result["notes"].append("DATA.bin path not provided; ISO/DATA.bin relationship check skipped.")
        else:
            result["notes"].append("DATA.bin path provided, but ISO/DATA.bin relationship check requires a readable ISO listing and was skipped.")
        return result
    st = iso_path.stat()
    result["size"] = st.st_size
    result["mtime_utc"] = _dt.datetime.fromtimestamp(st.st_mtime, _dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result["checksums"] = file_checksums(iso_path, st.st_size, limits)
    try:
        iso = Iso9660(iso_path).open()
        result["layout"] = {
            "mode": iso.mode,
            "sector_size": iso.sector_size,
            "data_offset": iso.data_offset,
            "lba_offset": getattr(iso, "lba_offset", 0),
        }
        entries = []
        clue_entries = []
        for idx, entry in enumerate(iso.iter_files()):
            if idx >= limits.max_iso_entries:
                result["errors"].append(f"Stopped ISO listing at max_iso_entries={limits.max_iso_entries}.")
                break
            obj = {"path": entry.path, "size": entry.size, "lba": entry.lba, "is_dir": bool(entry.is_dir)}
            entries.append(obj)
            text = entry.path
            if any(pattern.search(text) for _label, pattern in CLUE_PATTERNS):
                clue_entries.append({**obj, "confidence": PROBABLE, "basis": "ISO directory entry path matched a known research clue."})
        result["entries"] = entries
        result["entry_count"] = len(entries)
        result["clue_entries"] = clue_entries[:200]
        result["confidence"] = CONFIRMED
    except Exception as exc:  # parsing user-supplied images should never abort the whole scan
        result["confidence"] = UNKNOWN
        result["errors"].append(f"ISO directory parse failed: {type(exc).__name__}: {exc}")
    if data_bin_path is not None:
        data_bin_path = data_bin_path.expanduser().resolve()
        rel: dict[str, Any] = {"data_bin_path": str(data_bin_path), "exists": data_bin_path.exists(), "confidence": UNKNOWN}
        if data_bin_path.exists():
            data_size = data_bin_path.stat().st_size
            rel["size"] = data_size
            rel["checksums"] = file_checksums(data_bin_path, data_size, limits)
            matches = [e for e in result.get("entries", []) if Path(e.get("path", "")).name.lower() == "data.bin"]
            same_size = [e for e in matches if e.get("size") == data_size]
            rel["iso_data_bin_entries"] = matches[:20]
            if same_size:
                rel["confidence"] = PROBABLE
                rel["basis"] = "External DATA.bin size matches an ISO directory entry named DATA.bin; bytes were not extracted from the ISO."
            elif matches:
                rel["confidence"] = INFERRED
                rel["basis"] = "ISO has DATA.bin-like entries, but size did not match the external DATA.bin."
            else:
                rel["basis"] = "No DATA.bin directory entry was found in the parsed ISO listing."
        result["data_bin_relationships"].append(rel)
    else:
        result["notes"].append("DATA.bin path not provided; ISO/DATA.bin relationship check skipped.")
    return result


def aggregate_findings(scan: dict[str, Any]) -> dict[str, Any]:
    findings: dict[str, Any] = {
        "confidence_policy": "confirmed/probable/inferred/unknown are evidence labels, not gameplay conclusions. Unverified matches are reported as clues.",
        "town_root_town_clues": [],
        "ccs_ccsf_summary": {"file_count": 0, "section_ids": Counter(), "category_prefix_counts": Counter()},
        "embedded_cmp_member_summary": {
            "container_count": 0,
            "candidate_count": 0,
            "valid_or_probable_count": 0,
            "invalid_or_unknown_count": 0,
            "town_bin_candidates": [],
            "special_highlights": [],
        },
        "extension_summary": Counter(),
        "uncertainty_notes": [],
    }
    for root in scan.get("roots", []):
        if not root:
            continue
        for f in root.get("files", []):
            ext = f.get("likely_extension", {}).get("path_extension", UNKNOWN)
            findings["extension_summary"][ext] += 1
            ccsf = f.get("ccsf_like", {})
            if ccsf.get("signature_found_in_sample"):
                findings["ccs_ccsf_summary"]["file_count"] += 1
                for sec in ccsf.get("sections", []):
                    findings["ccs_ccsf_summary"]["section_ids"][sec.get("id", UNKNOWN)] += 1
                    findings["ccs_ccsf_summary"]["category_prefix_counts"].update(sec.get("category_prefix_counts", {}))
            for clue in f.get("clues", []):
                findings["town_root_town_clues"].append({"file": f.get("relative_path"), **clue})
            embedded = f.get("embedded_cmp_members", {})
            if embedded.get("scanned") and embedded.get("candidate_count", 0):
                findings["embedded_cmp_member_summary"]["container_count"] += 1
                findings["embedded_cmp_member_summary"]["candidate_count"] += embedded.get("candidate_count", 0)
                for member in embedded.get("members", []):
                    confidence = member.get("confidence", UNKNOWN)
                    if confidence in {CONFIRMED, PROBABLE, INFERRED} and not member.get("error"):
                        findings["embedded_cmp_member_summary"]["valid_or_probable_count"] += 1
                    else:
                        findings["embedded_cmp_member_summary"]["invalid_or_unknown_count"] += 1
                    compact = {
                        "file": f.get("relative_path"),
                        "offset": member.get("offset"),
                        "gzip_original_filename": member.get("gzip_original_filename"),
                        "compressed_size": member.get("compressed_size"),
                        "decompressed_sample_size": member.get("decompressed_sample_size"),
                        "confidence": confidence,
                        "highlight_labels": member.get("highlight_labels", []),
                        "error": member.get("error"),
                    }
                    if f.get("name", "").lower() == "town.bin":
                        findings["embedded_cmp_member_summary"]["town_bin_candidates"].append(compact)
                    if member.get("highlight_labels"):
                        findings["embedded_cmp_member_summary"]["special_highlights"].append(compact)
    iso = scan.get("iso") or {}
    for entry in iso.get("clue_entries", []):
        findings["town_root_town_clues"].append(
            {"file": entry.get("path"), "label": "ISO path clue", "confidence": entry.get("confidence", PROBABLE), "basis": entry.get("basis")}
        )
    for note in iso.get("notes", []):
        findings["uncertainty_notes"].append(note)
    if not findings["town_root_town_clues"]:
        findings["uncertainty_notes"].append("No town.bin, CCSFtown04, Fort Ouph, CCS/CCSF, or DATA.bin clues were found in bounded metadata/string scans that were run.")
    findings["uncertainty_notes"].append("No finding is labeled as an NPC script; uncertain items are intentionally called clues.")
    findings["extension_summary"] = dict(sorted(findings["extension_summary"].items()))
    findings["ccs_ccsf_summary"]["section_ids"] = dict(findings["ccs_ccsf_summary"]["section_ids"].most_common(100))
    findings["ccs_ccsf_summary"]["category_prefix_counts"] = dict(sorted(findings["ccs_ccsf_summary"]["category_prefix_counts"].items()))
    findings["embedded_cmp_member_summary"]["town_bin_candidates"] = findings["embedded_cmp_member_summary"]["town_bin_candidates"][:100]
    findings["embedded_cmp_member_summary"]["special_highlights"] = findings["embedded_cmp_member_summary"]["special_highlights"][:100]
    return findings


def write_text_report(summary: dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("Fragmenter Safe Scan Report")
    lines.append("===========================")
    lines.append(f"Created UTC: {summary.get('created_utc')}")
    lines.append("")
    lines.append("Safety policy")
    lines.append("-------------")
    lines.append("This report records metadata, checksums, bounded strings, and structural clues only.")
    lines.append("It does not copy copyrighted game binaries into the workspace or package export.")
    lines.append("Uncertain discoveries are called clues. Nothing is labeled as an NPC script.")
    lines.append("")
    lines.append("Inputs")
    lines.append("------")
    for key, value in summary.get("inputs", {}).items():
        lines.append(f"- {key}: {value if value is not None else '(not provided)'}")
    lines.append("")
    iso = summary.get("iso", {})
    lines.append("Optional ISO/DATA scans")
    lines.append("-----------------------")
    if iso.get("exists"):
        lines.append(f"- [confirmed] ISO scan ran for {iso.get('path')} with {iso.get('entry_count', 0)} entries listed.")
    else:
        lines.append(f"- [unknown] ISO scan skipped or unavailable: {iso.get('path') or '(not provided)'}")
    relationships = iso.get("data_bin_relationships", [])
    if relationships:
        for rel in relationships:
            status = "available" if rel.get("exists") else "unavailable"
            lines.append(f"- [{rel.get('confidence', UNKNOWN)}] DATA.bin relationship check {status} for {rel.get('data_bin_path')}: {rel.get('basis', 'No relationship basis recorded.')}")
    else:
        lines.append("- [unknown] DATA.bin relationship check skipped because no DATA.bin path was provided or no ISO path was available.")
    for note in iso.get("notes", []):
        lines.append(f"- [unknown] {note}")
    lines.append("")
    findings = summary.get("findings", {})
    lines.append("Town / root-town clues")
    lines.append("----------------------")
    clues = findings.get("town_root_town_clues", [])
    if clues:
        for clue in clues[:300]:
            lines.append(f"- [{clue.get('confidence', UNKNOWN)}] {clue.get('label', 'clue')} in {clue.get('file')}: {clue.get('basis', '')}")
        if len(clues) > 300:
            lines.append(f"- ... {len(clues) - 300} additional clues omitted from text report; see JSON.")
    else:
        lines.append("- [unknown] No matching clues found in bounded scans.")
    lines.append("")
    lines.append("CCS/CCSF-like summary")
    lines.append("---------------------")
    ccs = findings.get("ccs_ccsf_summary", {})
    lines.append(f"Files with CCSF-like signatures in sample: {ccs.get('file_count', 0)}")
    lines.append("Top section ids:")
    for sid, count in list(ccs.get("section_ids", {}).items())[:40]:
        lines.append(f"- {sid}: {count}")
    lines.append("Category/object prefix counts:")
    for prefix, count in ccs.get("category_prefix_counts", {}).items():
        lines.append(f"- {prefix}: {count}")
    lines.append("")
    lines.append("Embedded CMP/gzip member summary")
    lines.append("--------------------------------")
    embedded = findings.get("embedded_cmp_member_summary", {})
    lines.append(f"Containers with gzip candidates: {embedded.get('container_count', 0)}")
    lines.append(f"Total gzip magic candidates: {embedded.get('candidate_count', 0)}")
    lines.append(f"Readable/probable candidates: {embedded.get('valid_or_probable_count', 0)}")
    lines.append(f"Invalid/unknown candidates: {embedded.get('invalid_or_unknown_count', 0)}")
    town_candidates = embedded.get("town_bin_candidates", [])
    if town_candidates:
        lines.append("Priority town.bin candidates:")
        for member in town_candidates[:40]:
            lines.append(
                f"- [{member.get('confidence', UNKNOWN)}] {member.get('file')} @ {member.get('offset')} "
                f"fname={member.get('gzip_original_filename') or '(none)'} "
                f"compressed={member.get('compressed_size') or '(unknown)'} sample={member.get('decompressed_sample_size', 0)}"
            )
    highlights = embedded.get("special_highlights", [])
    if highlights:
        lines.append("Special town04.cmp/town04d.cmp highlights:")
        for member in highlights[:40]:
            labels = ", ".join(member.get("highlight_labels", []))
            lines.append(
                f"- [{member.get('confidence', UNKNOWN)}] {labels} in {member.get('file')} @ {member.get('offset')} "
                f"fname={member.get('gzip_original_filename') or '(none)'}"
            )
    lines.append("")
    lines.append("Extension summary")
    lines.append("-----------------")
    for ext, count in findings.get("extension_summary", {}).items():
        lines.append(f"- {ext}: {count}")
    lines.append("")
    lines.append("Uncertainty notes")
    lines.append("-----------------")
    for note in findings.get("uncertainty_notes", []):
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run_safe_scan(args: argparse.Namespace) -> int:
    workspace = args.workspace.expanduser().resolve()
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    limits = ScanLimits(
        max_files_per_root=args.max_files_per_root,
        max_bytes_for_full_hash=args.max_bytes_for_full_hash,
        sample_bytes=args.sample_bytes,
        string_sample_limit=args.string_sample_limit,
        strings_per_file=args.strings_per_file,
        max_sections_per_file=args.max_sections_per_file,
        max_iso_entries=args.max_iso_entries,
        max_embedded_gzip_scan_bytes=args.max_embedded_gzip_scan_bytes,
        max_embedded_gzip_candidates=args.max_embedded_gzip_candidates,
        max_embedded_gzip_decompressed_bytes=args.max_embedded_gzip_decompressed_bytes,
    )
    inputs = {
        "area_server_root": str(args.area_server_root),
        "area_server_data": str(args.area_server_data),
        "save_folder": str(args.save_folder) if args.save_folder else None,
        "iso_path": str(args.iso_path) if args.iso_path else None,
        "data_bin_path": str(args.data_bin_path) if args.data_bin_path else None,
        "workspace": str(workspace),
    }
    scan: dict[str, Any] = {
        "schema": "fragmenter.safe_scan.v1",
        "created_utc": utc_now_iso(),
        "inputs": inputs,
        "limits": limits.__dict__,
        "copyright_safety": "No source game binary is copied. Reports contain metadata, hashes/checksums, bounded strings, and structural summaries only.",
        "roots": [],
    }
    scan["roots"].append(scan_root(args.area_server_root, "area_server_root", limits))
    scan["roots"].append(scan_root(args.area_server_data, "area_server_data", limits))
    if args.save_folder:
        scan["roots"].append(scan_root(args.save_folder, "save_folder", limits))
    scan["iso"] = scan_iso(args.iso_path, args.data_bin_path, limits)
    scan["findings"] = aggregate_findings(scan)

    json_path = reports / "fragmenter_scan_summary.json"
    txt_path = reports / "fragmenter_scan_report.txt"
    json_path.write_text(json.dumps(scan, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    write_text_report(scan, txt_path)
    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")
    return 0


def should_package(path: Path, workspace: Path) -> tuple[bool, str]:
    try:
        rel = path.resolve().relative_to(workspace.resolve())
    except ValueError:
        return False, "outside workspace"
    parts = set(rel.parts)
    if ".git" in parts or "__pycache__" in parts:
        return False, "ignored directory"
    suffix = path.suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return False, "binary extension blocked"
    if suffix not in TEXT_EXTENSIONS:
        return False, "not an allow-listed report/text extension"
    if path.stat().st_size > 16 * 1024 * 1024:
        return False, "text/report file too large for safe package"
    if is_probably_game_binary(path):
        return False, "game-binary-like path blocked"
    return True, "included"


def run_package_export(args: argparse.Namespace) -> int:
    workspace = args.workspace.expanduser().resolve()
    export_dir = workspace / "export"
    zip_out = getattr(args, "zip_out", None)
    if zip_out:
        out = zip_out.expanduser().resolve()
    else:
        stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        out = export_dir / f"fragmenter_upload_package_{stamp}.zip"
    export_dir.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    readme_path = export_dir / README_FOR_CHATGPT_NAME
    readme_path.write_text(README_FOR_CHATGPT_TEXT, encoding="utf-8", newline="\n")
    manifest: dict[str, Any] = {
        "schema": "fragmenter.package_export.v1",
        "created_utc": utc_now_iso(),
        "workspace": str(workspace),
        "safety_policy": "Only report/text extensions are included. Known game binary extensions and game-binary-like names are excluded.",
        "included": [],
        "excluded_count_by_reason": Counter(),
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(workspace):
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__"}]
            for filename in sorted(filenames):
                p = Path(dirpath) / filename
                if p.resolve() in {out, readme_path.resolve()}:
                    continue
                ok, reason = should_package(p, workspace)
                if not ok:
                    manifest["excluded_count_by_reason"][reason] += 1
                    continue
                rel = p.resolve().relative_to(workspace).as_posix()
                zf.write(p, rel)
                st = p.stat()
                manifest["included"].append({"path": rel, "size": st.st_size, "sha256": file_checksums(p, st.st_size, ScanLimits())["sha256"]})
        readme_stat = readme_path.stat()
        zf.write(readme_path, README_FOR_CHATGPT_NAME)
        manifest["included"].append(
            {
                "path": README_FOR_CHATGPT_NAME,
                "size": readme_stat.st_size,
                "sha256": file_checksums(readme_path, readme_stat.st_size, ScanLimits())["sha256"],
            }
        )
        manifest_bytes = json.dumps({**manifest, "excluded_count_by_reason": dict(manifest["excluded_count_by_reason"])}, indent=2).encode("utf-8")
        zf.writestr("package_manifest.json", manifest_bytes)
    print(f"Wrote {out}")
    print(f"Included {len(manifest['included'])} report/text files")
    return 0


def add_scan_arguments(scan: argparse.ArgumentParser) -> None:
    scan.add_argument("--area-server-root", "--server-root", dest="area_server_root", type=Path, required=True, help="Area Server root folder")
    scan.add_argument("--area-server-data", "--data-dir", dest="area_server_data", type=Path, required=True, help="Area Server data folder")
    scan.add_argument("--save-folder", type=Path, help="Optional Area Server save folder")
    scan.add_argument("--iso-path", "--iso", dest="iso_path", type=Path, help="Optional ISO path")
    scan.add_argument("--data-bin-path", "--data-bin", dest="data_bin_path", type=Path, help="Optional external DATA.bin path")
    scan.add_argument("--workspace", "--out", dest="workspace", type=Path, required=True, help="Workspace/output folder")
    scan.add_argument("--max-files-per-root", type=int, default=ScanLimits.max_files_per_root)
    scan.add_argument("--max-bytes-for-full-hash", type=int, default=ScanLimits.max_bytes_for_full_hash)
    scan.add_argument("--sample-bytes", type=int, default=ScanLimits.sample_bytes)
    scan.add_argument("--string-sample-limit", type=int, default=ScanLimits.string_sample_limit)
    scan.add_argument("--strings-per-file", type=int, default=ScanLimits.strings_per_file)
    scan.add_argument("--max-sections-per-file", type=int, default=ScanLimits.max_sections_per_file)
    scan.add_argument("--max-iso-entries", type=int, default=ScanLimits.max_iso_entries)
    scan.add_argument("--max-embedded-gzip-scan-bytes", type=int, default=ScanLimits.max_embedded_gzip_scan_bytes)
    scan.add_argument("--max-embedded-gzip-candidates", type=int, default=ScanLimits.max_embedded_gzip_candidates)
    scan.add_argument("--max-embedded-gzip-decompressed-bytes", type=int, default=ScanLimits.max_embedded_gzip_decompressed_bytes)
    scan.set_defaults(func=run_safe_scan)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create safe Fragmenter research reports and export report packages.",
        epilog=(
            "Examples:\n"
            "  py tools\\fragmenter_research_pack.py scan --server-root C:\\Fragmenter\\AreaServer "
            "--data-dir C:\\Fragmenter\\AreaServer\\data --iso D:\\Fragmenter.iso "
            "--data-bin C:\\Fragmenter\\AreaServer\\data\\DATA.bin --out C:\\Fragmenter\\workspace\n"
            "  py tools\\fragmenter_research_pack.py package --out C:\\Fragmenter\\workspace "
            "--zip-out C:\\Fragmenter\\fragmenter_research_pack.zip\n"
            "  py tools\\fragmenter_research_pack.py safe-scan --area-server-root C:\\Fragmenter\\AreaServer "
            "--area-server-data C:\\Fragmenter\\AreaServer\\data --iso-path D:\\Fragmenter.iso "
            "--workspace C:\\Fragmenter\\workspace\n"
            "  py tools\\fragmenter_research_pack.py package-export --workspace C:\\Fragmenter\\workspace "
            "--out C:\\Fragmenter\\fragmenter_research_pack.zip"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Safely scan local inputs and write workspace/reports scan outputs.")
    add_scan_arguments(scan)

    safe_scan = sub.add_parser("safe-scan", help="Backward-compatible alias for scan.")
    add_scan_arguments(safe_scan)

    package = sub.add_parser("package", help="Create a ZIP containing only safe report/text files from a workspace.")
    package.add_argument("--out", dest="workspace", type=Path, required=True, help="Workspace/output folder created by scan")
    package.add_argument("--zip-out", type=Path, help="Output ZIP path; defaults to workspace/export/fragmenter_upload_package_<UTC>.zip")
    package.set_defaults(func=run_package_export)

    package_export = sub.add_parser("package-export", help="Backward-compatible package command using --workspace and --out ZIP path.")
    package_export.add_argument("--workspace", type=Path, required=True, help="Workspace/output folder created by safe-scan")
    package_export.add_argument("--out", dest="zip_out", type=Path, help="Output ZIP path; defaults to workspace/export/fragmenter_upload_package_<UTC>.zip")
    package_export.set_defaults(func=run_package_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.time()
    rc = args.func(args)
    print(f"Done in {time.time() - started:.2f}s")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

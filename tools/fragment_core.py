#!/usr/bin/env python3
"""Shared CCSF container helpers for Fragmenter tools."""
from __future__ import annotations

import gzip
import struct
from pathlib import Path
from typing import List

CCSF_SIG = b"\x01\x00\xcc\xcc\r\x00\x00\x00CCSF"
PREFIXES = ("TEX_", "MDL_", "DMY_", "MAT_", "ANM_", "CAM_")


def read_maybe_gzip(path: Path) -> tuple[bytes, bool]:
    blob = path.read_bytes()
    if blob[:2] == b"\x1f\x8b":
        return gzip.decompress(blob), True
    return blob, False


def write_maybe_gzip(path: Path, blob: bytes, gzip_it: bool) -> None:
    path.write_bytes(gzip.compress(blob) if gzip_it else blob)


def split_sections(blob: bytes):
    offs = []
    start = 0
    while True:
        i = blob.find(CCSF_SIG, start)
        if i == -1:
            break
        offs.append(i)
        start = i + 1

    out = []
    for idx, off in enumerate(offs):
        end = offs[idx + 1] if idx + 1 < len(offs) else len(blob)
        sec_id = f"UNKNOWN_{idx:03d}"
        try:
            t, mark, ln = struct.unpack_from("<HHI", blob, off)
            if t == 1 and mark == 0xCCCC and off + 8 + ln <= len(blob):
                raw = blob[off + 8 : off + 8 + ln]
                sec_id = raw.split(b"\x00")[0].decode("ascii", errors="replace")
        except Exception:
            pass
        out.append((idx, sec_id, off, end))
    return out


def get_section(blob: bytes, section_name: str | None) -> tuple[str, bytes]:
    if not section_name:
        return "(raw)", blob
    for _idx, sid, off, end in split_sections(blob):
        if sid == section_name:
            return sid, blob[off:end]
    raise SystemExit(f"Section not found: {section_name}")


def scan_ascii_strings(data: bytes, minlen: int = 4) -> List[str]:
    out: List[str] = []
    cur: List[int] = []
    for b in data:
        if 32 <= b < 127:
            cur.append(b)
            continue
        if len(cur) >= minlen:
            out.append(bytes(cur).decode("ascii", errors="ignore"))
        cur = []
    if len(cur) >= minlen:
        out.append(bytes(cur).decode("ascii", errors="ignore"))
    return out


def normalize_asset_path(path: str) -> str:
    s = path.replace("\\", "/").strip()
    if s.startswith("s/"):
        return s.lower()
    if s.startswith(" s/"):
        return s[1:].lower()
    if s.startswith(" s"):
        return s[1:].replace("\\", "/").lower()
    return s.lower()


def parse_asset_paths(section: bytes) -> List[str]:
    hits = []
    for i in range(2, len(section) - 8, 2):
        if section[i : i + 2] != b"\xCC\xCC":
            continue
        t = struct.unpack_from("<H", section, i - 2)[0]
        if t != 2:
            continue
        ln = struct.unpack_from("<I", section, i + 2)[0]
        start = i - 2
        end = start + 8 + ln
        if end > len(section):
            continue
        payload = section[start + 8 : end]
        if b" s\\" in payload:
            hits.append(payload)
    if not hits:
        return []
    payload = max(hits, key=len)
    paths = set()
    for off in range(0, len(payload) - 32 + 1, 32):
        slot = payload[off : off + 32]
        if slot[:3] != b" s\\":
            continue
        s = slot.strip(b"\x00").decode("ascii", errors="ignore").strip()
        if s:
            paths.add(normalize_asset_path(s))
    return sorted(paths)

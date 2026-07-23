#!/usr/bin/env python3
"""
iso9660.py - minimal ISO9660/Joliet reader with support for common PS2 disc images.

Why this exists:
- PS2 images are usually "2048-byte user data sectors" (.iso)
- Some rips are "raw sectors" (e.g., 2352 bytes/sector) where the 2048 user bytes are inside the sector.
  If you treat those like 2048-byte sectors, your directory parsing explodes (hundreds of thousands of fake files).

This module detects common layouts and provides:
- list files (normalized paths)
- extract a file by internal path

It is intentionally small and dependency-free (not a full ISO stack).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
import sys

SECTOR_USER = 2048

# Common container sector sizes + offsets to the 2048 user-data payload.
# 2048: plain ISO image
# 2352: raw sectors (Mode1: 16 byte header; Mode2: 24 byte header/subheader)
# 2336: less common "raw" format (best-effort offsets)
CANDIDATE_LAYOUTS: List[Tuple[int, int]] = [
    (2048, 0),
    (2352, 16),
    (2352, 24),
    (2336, 0),
    (2336, 8),
]

def _u16le(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off+2], "little", signed=False)

def _u32le(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off+4], "little", signed=False)

def _strip_version(name: str) -> str:
    """Strip a trailing numeric ISO9660 version suffix from one path segment."""
    if ";" in name:
        head, tail = name.rsplit(";", 1)
        if tail.isdigit():
            return head
    return name

def _clean_iso_name(raw: str, *, is_special: bool = False) -> str:
    raw = raw.strip("\x00").strip()
    raw = _strip_version(raw)
    if raw in (".", ".."):
        return "" if is_special else raw
    if any(ord(ch) < 32 for ch in raw):
        return ""
    return raw


def _warn_iso(msg: str) -> None:
    print(f"[iso9660] {msg}", file=sys.stderr)


def _has_repeated_segment_chain(path: str) -> bool:
    segs = [s for s in normalize_path(path).split("/") if s]
    if len(segs) < 2:
        return False
    max_window = min(4, len(segs) // 2)
    for window in range(1, max_window + 1):
        if segs[-2 * window : -window] == segs[-window:]:
            return True
    return False

def normalize_path(p) -> str:
    """Normalize paths to a consistent lower-case, forward-slash form.

    Defensive: avoids hard crashes if a rip/layout is misdetected and yields malformed names.
    """
    if p is None:
        return ""
    if isinstance(p, bytes):
        try:
            p = p.decode("utf-8", "ignore")
        except Exception:
            p = p.decode("latin-1", "ignore")
    else:
        p = str(p)
    p = p.strip().strip("\x00").strip()
    if not p:
        return ""
    p = p.replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    if p.startswith("./"):
        p = p[2:]
    if p.startswith("/"):
        p = p[1:]
    p = "/".join(_strip_version(part) for part in p.split("/"))
    if len(p) > 4096:
        return ""
    try:
        return p.lower()
    except Exception:
        return ""

@dataclass
class IsoEntry:
    path: str
    lba: int
    size: int
    is_dir: bool = False

class Iso9660:
    def __init__(self, iso_path: Path):
        self.iso_path = Path(iso_path)
        self.sector_size = 2048
        self.data_offset = 0
        self.lba_offset = 0  # physical sector bias (e.g., pregap or data track start)
        self.block_size = SECTOR_USER  # ISO logical block size (almost always 2048)
        self._use_joliet = False
        self._root_lba = 0
        self._root_size = 0
        self._traversal_warnings: List[str] = []

    @property
    def mode(self) -> str:
        return "joliet" if self._use_joliet else "iso9660"

    def _read_user(self, f, lba: int, nbytes: int) -> bytes:
        """
        Read nbytes from ISO logical blocks starting at lba, returning only user-data bytes.
        Works for both 2048 (.iso) and raw-sector images (2352, 2336).
        """
        if nbytes <= 0:
            return b""
        # Fast path: plain 2048 sector layout
        if self.sector_size == SECTOR_USER and self.data_offset == 0:
            f.seek((lba + self.lba_offset) * SECTOR_USER)
            return f.read(nbytes)

        # Raw layout: stitch user payloads block-by-block
        out = bytearray()
        remaining = nbytes
        cur_lba = lba
        while remaining > 0:
            take = SECTOR_USER if remaining >= SECTOR_USER else remaining
            f.seek((cur_lba + self.lba_offset) * self.sector_size + self.data_offset)
            chunk = f.read(take)
            if len(chunk) != take:
                break
            out.extend(chunk)
            remaining -= take
            cur_lba += 1
        return bytes(out)


    def _detect_layout(self) -> Tuple[int, int, int]:
        """
        Detect (sector_size, data_offset, lba_offset) by locating the Primary Volume Descriptor (PVD).
        ISO9660 PVD is at logical block LBA 16 and begins with: 0x01 'CD001' 0x01.
        For raw rips (BIN), the image may include a pregap or earlier tracks; lba_offset accounts for that.
        """
        file_size = self.iso_path.stat().st_size

        def _is_pvd(vd: bytes) -> bool:
            return len(vd) >= SECTOR_USER and vd[0] == 0x01 and vd[1:6] == b"CD001" and vd[6] == 0x01

        def _looks_like_vd(vd: bytes) -> bool:
            return len(vd) >= 8 and vd[1:6] == b"CD001" and vd[6] == 0x01 and vd[0] in (0x00, 0x01, 0x02, 0x03, 0xFF)

        with self.iso_path.open("rb") as f:
            # Fast checks for common layouts + common pregap shift (150 sectors for CD rips)
            for sector_size, off in CANDIDATE_LAYOUTS:
                for lba_off in (0, 150, 300):
                    pos = (16 + lba_off) * sector_size + off
                    if pos < 0 or pos + SECTOR_USER > file_size:
                        continue
                    f.seek(pos)
                    vd = f.read(SECTOR_USER)
                    if _is_pvd(vd):
                        # verify next VD-ish sector if available (helps reject false positives)
                        f.seek((17 + lba_off) * sector_size + off)
                        vd2 = f.read(SECTOR_USER)
                        if _looks_like_vd(vd2) or True:
                            return sector_size, off, lba_off

            # Streaming scan for the PVD signature within the first N bytes.
            # We scan a larger window than before because multi-track BINs can place the data track later.
            scan_bytes = min(file_size, 512 * 1024 * 1024)  # 512MB cap
            chunk = 4 * 1024 * 1024
            overlap = 64
            sig = b"\x01CD001\x01"

            best = None  # (score, sector_size, off, lba_off)

            base = 0
            prev = b""
            while base < scan_bytes:
                f.seek(base)
                data = f.read(min(chunk, scan_bytes - base))
                if not data:
                    break
                blob = prev + data
                idx = 0
                while True:
                    j = blob.find(sig, idx)
                    if j == -1:
                        break
                    abs_pos = base - len(prev) + j  # file offset where sig begins
                    # Try to align this signature start to a candidate layout
                    for sector_size, off in CANDIDATE_LAYOUTS:
                        aligned = abs_pos - off
                        if aligned < 0:
                            continue
                        if aligned % sector_size != 0:
                            continue
                        file_lba = aligned // sector_size
                        lba_off = file_lba - 16  # because this hit looks like PVD at LBA16
                        # Reject absurd offsets (almost certainly false positives)
                        if lba_off < -5000 or lba_off > 5_000_000:
                            continue

                        # Verify by re-reading at computed (16 + lba_off)
                        pos = (16 + lba_off) * sector_size + off
                        if pos < 0 or pos + SECTOR_USER > file_size:
                            continue
                        f.seek(pos)
                        vd = f.read(SECTOR_USER)
                        if not _is_pvd(vd):
                            continue
                        # Bonus verification: next descriptor should also look like a VD
                        f.seek((17 + lba_off) * sector_size + off)
                        vd2 = f.read(SECTOR_USER)
                        ok2 = _looks_like_vd(vd2)

                        # Score: prefer small |lba_off|, and candidates with vd2 validation
                        score = abs(lba_off)
                        if not ok2:
                            score += 10_000  # penalize
                        if best is None or score < best[0]:
                            best = (score, sector_size, off, lba_off)

                    idx = j + 1

                # keep overlap for boundary matches
                prev = blob[-overlap:] if len(blob) >= overlap else blob
                base += len(data)

            if best is not None:
                _score, sector_size, off, lba_off = best
                return sector_size, off, lba_off

        raise ValueError("Could not detect ISO layout. PVD signature not found.")

    def open(self) -> "Iso9660":
        if not self.iso_path.exists():
            raise FileNotFoundError(self.iso_path)

        self.sector_size, self.data_offset, self.lba_offset = self._detect_layout()

        with self.iso_path.open("rb") as f:
            # Walk volume descriptors starting at LBA 16
            pvd = None
            joliet = None

            lba = 16
            for _ in range(256):  # hard cap for safety
                vd = self._read_user(f, lba, SECTOR_USER)
                if len(vd) < SECTOR_USER:
                    break
                vtype = vd[0]
                if vd[1:6] != b"CD001":
                    break
                if vtype == 0xFF:
                    break
                if vtype == 0x01:
                    pvd = vd
                elif vtype == 0x02:
                    # Joliet SVD uses escape sequence at 88-90: %/E, %/C, %/@
                    esc = vd[88:91]
                    if esc in (b"%/E", b"%/C", b"%/@"):
                        joliet = vd
                lba += 1

            chosen = joliet or pvd
            if chosen is None:
                raise ValueError("Not an ISO9660 image (no valid volume descriptor found).")

            self._use_joliet = (chosen is joliet)

            bs = _u16le(chosen, 128) or SECTOR_USER
            # Most discs are 2048 logical blocks. We only support 2048 right now.
            # If bs is weird, keep reading as 2048 but warn via sanity check.
            self.block_size = bs if bs else SECTOR_USER

            root = chosen[156:190]
            if len(root) < 34 or root[0] < 34:
                raise ValueError("Invalid root directory record.")
            self._root_lba = _u32le(root, 2)
            self._root_size = _u32le(root, 10)

            # Sanity checks (avoid runaway parsing on mis-detected images)
            file_size = self.iso_path.stat().st_size
            max_lba = file_size // max(1, self.sector_size)
            if not (0 < self._root_lba < max_lba):
                raise ValueError(f"Root LBA looks invalid: {self._root_lba} (max {max_lba})")
            if not (0 < self._root_size < 256 * 1024 * 1024):
                raise ValueError(f"Root dir size looks invalid: {self._root_size}")

        return self

    def _decode_name(self, b: bytes) -> str:
        if self._use_joliet:
            try:
                s = b.decode("utf-16be", errors="ignore")
            except Exception:
                s = b.decode("latin1", errors="ignore")
            s = s.replace("\x00", "")
            s = _strip_version(s)
            return _clean_iso_name(s)
        else:
            s = b.decode("ascii", errors="ignore")
            return _clean_iso_name(s)

    def _iter_dir_records(self, f, lba: int, size: int) -> Iterator[Tuple[str, int, int, bool]]:
        data = self._read_user(f, lba, size)
        off = 0
        # Directory records are packed into logical blocks, padded with 0s to the end of the block.
        while off < len(data):
            rec_len = data[off]
            if rec_len == 0:
                # advance to next block boundary
                bs = SECTOR_USER
                off = ((off // bs) + 1) * bs
                continue
            rec = data[off:off + rec_len]
            if len(rec) < 34:
                break
            extent = _u32le(rec, 2)
            dlen = _u32le(rec, 10)
            flags = rec[25]
            is_dir = bool(flags & 0x02)
            fid_len = rec[32]
            fid = rec[33:33 + fid_len]
            if fid_len == 1 and fid in (b"\x00", b"\x01"):
                off += rec_len
                continue
            if self._use_joliet:
                if fid_len % 2 != 0:
                    off += rec_len
                    continue
                malformed = False
                for i in range(0, fid_len, 2):
                    codepoint = int.from_bytes(fid[i:i + 2], "big", signed=False)
                    if codepoint < 32:
                        malformed = True
                        break
                if malformed:
                    off += rec_len
                    continue
            elif any(ch < 32 for ch in fid):
                off += rec_len
                continue
            name = self._decode_name(fid)
            yield (name, extent, dlen, is_dir)
            off += rec_len

    def iter_files(self) -> Iterator[IsoEntry]:
        # Ensure open has run
        if self._root_lba == 0:
            self.open()

        self._traversal_warnings = []
        with self.iso_path.open("rb") as f:
            max_depth = 64
            stack: List[Tuple[str, int, int, int]] = [("", self._root_lba, self._root_size, 0)]
            seen_dirs = set()  # (lba, size)
            yielded = 0  # guard against runaway parsing
            while stack:
                base, lba, size, depth = stack.pop()
                key = (lba, size)
                if key in seen_dirs:
                    msg = f"Loop guard blocked directory '{normalize_path(base)}' at ({lba},{size})."
                    self._traversal_warnings.append(msg)
                    _warn_iso(msg)
                    continue
                seen_dirs.add(key)

                # Guard against bogus sizes
                if size <= 0 or size > 256 * 1024 * 1024:
                    continue

                for name, extent, dlen, is_dir in self._iter_dir_records(f, lba, size):
                    if not name:
                        continue
                    # basic sanity
                    if extent <= 0:
                        continue
                    path = f"{base}/{name}" if base else name
                    path_norm = normalize_path(path)
                    if not path_norm:
                        continue
                    if _has_repeated_segment_chain(path_norm):
                        continue
                    if is_dir:
                        if depth + 1 > max_depth:
                            msg = f"Depth cap blocked directory '{path_norm}' at ({extent},{dlen})."
                            self._traversal_warnings.append(msg)
                            _warn_iso(msg)
                            continue
                        stack.append((path, extent, dlen, depth + 1))
                    else:
                        yielded += 1
                        if yielded > 200000:
                            raise ValueError("ISO parse runaway (>200k files). Layout likely misdetected; try a different rip or format.")
                        yield IsoEntry(path=path_norm, lba=extent, size=dlen, is_dir=False)

    @property
    def traversal_warnings(self) -> List[str]:
        return list(self._traversal_warnings)

    def build_index(self) -> Dict[str, IsoEntry]:
        idx: Dict[str, IsoEntry] = {}
        for e in self.iter_files():
            idx[e.path] = e
        return idx

    def extract(self, internal_path: str, out_path: Path) -> bool:
        internal_norm = normalize_path(internal_path)
        # Stream scan (avoid building a giant dict if user only wants one file)
        hit: Optional[IsoEntry] = None
        for e in self.iter_files():
            if e.path == internal_norm:
                hit = e
                break
        if hit is None:
            return False

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with self.iso_path.open("rb") as f, out_path.open("wb") as out:
            remaining = hit.size
            cur_lba = hit.lba
            while remaining > 0:
                take = SECTOR_USER if remaining >= SECTOR_USER else remaining
                chunk = self._read_user(f, cur_lba, take)
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
                cur_lba += 1
        return out_path.exists() and out_path.stat().st_size == hit.size

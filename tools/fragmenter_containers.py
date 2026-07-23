#!/usr/bin/env python3
"""Reusable helpers for padded gzip-member containers used by Fragmenter tools."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import struct
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path

GZIP_MAGIC = b"\x1f\x8b"


@dataclass
class GzipHeader:
    flags: int
    mtime: int
    os_byte: int
    original_filename: str | None
    has_extra: bool
    has_name: bool
    has_comment: bool
    has_header_crc: bool
    header_end: int


@dataclass
class GzipMember:
    index: int
    raw_start: int
    raw_end: int
    raw: bytes
    decompressed: bytes
    header: GzipHeader | None
    trailer_crc32: int | None
    trailer_isize: int | None
    full_decompressed_start: int
    next_member_start: int
    slot_end: int
    slot_size: int
    padding_after_size: int

    @property
    def raw_size(self) -> int:
        return self.raw_end - self.raw_start

    @property
    def gzip_original_filename(self) -> str | None:
        return self.header.original_filename if self.header else None

    @property
    def decompressed_size(self) -> int:
        return len(self.decompressed)

    @property
    def decompressed_sha1(self) -> str:
        return sha1_hex(self.decompressed)

    def metadata(self) -> dict[str, object]:
        return {
            "index": self.index,
            "raw_start": self.raw_start,
            "raw_end": self.raw_end,
            "raw_size": self.raw_size,
            "next_member_start": self.next_member_start,
            "slot_end": self.slot_end,
            "slot_size": self.slot_size,
            "gzip_original_filename": self.gzip_original_filename,
            "decompressed_size": self.decompressed_size,
            "decompressed_sha1": self.decompressed_sha1,
        }


def sha1_hex(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()


def parse_gzip_header(raw: bytes, base_offset: int = 0) -> GzipHeader | None:
    if len(raw) < 10 or raw[:2] != GZIP_MAGIC or raw[2] != 8:
        return None
    flags = raw[3]
    pos = 10
    original_filename = None
    try:
        if flags & 0x04:
            xlen = struct.unpack_from("<H", raw, pos)[0]
            pos += 2 + xlen
        if flags & 0x08:
            end = raw.index(0, pos)
            original_filename = raw[pos:end].decode("latin-1")
            pos = end + 1
        if flags & 0x10:
            end = raw.index(0, pos)
            pos = end + 1
        if flags & 0x02:
            pos += 2
    except (ValueError, struct.error):
        return None
    if pos > len(raw):
        return None
    return GzipHeader(flags, struct.unpack_from("<I", raw, 4)[0], raw[9], original_filename, bool(flags & 4), bool(flags & 8), bool(flags & 16), bool(flags & 2), base_offset + pos)


def parse_gzip_members(raw: bytes) -> list[GzipMember]:
    members: list[GzipMember] = []
    raw_offset = 0
    full_dec_offset = 0
    previous: GzipMember | None = None
    while raw_offset < len(raw):
        start = raw.find(GZIP_MAGIC, raw_offset)
        if start == -1:
            break
        obj = zlib.decompressobj(wbits=31)
        try:
            decompressed = obj.decompress(raw[start:])
            obj.flush()
        except zlib.error:
            raw_offset = start + 1
            continue
        if not obj.eof:
            raw_offset = start + 1
            continue
        consumed = len(raw) - start - len(obj.unused_data)
        end = start + consumed
        if previous is not None:
            previous.next_member_start = start
            previous.slot_end = start
            previous.slot_size = start - previous.raw_start
            previous.padding_after_size = start - previous.raw_end
        member_raw = raw[start:end]
        crc = isize = None
        if len(member_raw) >= 8:
            crc, isize = struct.unpack("<II", member_raw[-8:])
        members.append(GzipMember(len(members), start, end, member_raw, decompressed, parse_gzip_header(member_raw, start), crc, isize, full_dec_offset, len(raw), len(raw), len(raw) - start, len(raw) - end))
        previous = members[-1]
        raw_offset = end
        full_dec_offset += len(decompressed)
    return members


def detect_padded_gzip_container(raw: bytes) -> list[dict[str, object]]:
    return [member.metadata() for member in parse_gzip_members(raw)]


def read_members(path: str | Path) -> list[GzipMember]:
    return parse_gzip_members(Path(path).read_bytes())


def decompress_member(member: GzipMember, raw_output: str | Path | None = None, decompressed_output: str | Path | None = None) -> bytes:
    if raw_output is not None:
        Path(raw_output).parent.mkdir(parents=True, exist_ok=True)
        Path(raw_output).write_bytes(member.raw)
    if decompressed_output is not None:
        Path(decompressed_output).parent.mkdir(parents=True, exist_ok=True)
        Path(decompressed_output).write_bytes(member.decompressed)
    return member.decompressed


def gzip_recompress_with_metadata(payload: bytes, filename: str | None = None, mtime: int | None = None) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(filename=filename or "", mode="wb", fileobj=out, mtime=mtime) as gz:
        gz.write(payload)
    return out.getvalue()


def _main() -> None:
    parser = argparse.ArgumentParser(description="Inspect padded gzip-member containers.")
    parser.add_argument("path")
    parser.add_argument("--member", type=int)
    parser.add_argument("--raw-output")
    parser.add_argument("--decompressed-output")
    args = parser.parse_args()
    members = read_members(args.path)
    if args.member is None:
        print(json.dumps([m.metadata() for m in members], indent=2))
        return
    decompress_member(members[args.member], args.raw_output, args.decompressed_output)
    print(json.dumps(members[args.member].metadata(), indent=2))


if __name__ == "__main__":
    _main()

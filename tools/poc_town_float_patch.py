#!/usr/bin/env python3
"""Patch one float32 value inside one gzip member slot in Area Server town.bin.

This tool parses the concatenated/padded gzip-member layout first, mutates only a
selected member's decompressed payload, recompresses only that member, writes it
back into the original padded slot, and verifies every other member slot stayed
raw-identical.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

FLOAT_TOLERANCE = 0.0001


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
class PaddingRange:
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start


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
    padding_before: PaddingRange | None = None
    padding_after: PaddingRange | None = None

    @property
    def raw_size(self) -> int:
        return self.raw_end - self.raw_start


def sha1_hex(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()


def parse_gzip_header(raw: bytes, base_offset: int) -> GzipHeader | None:
    if len(raw) < 10 or raw[:2] != b"\x1f\x8b" or raw[2] != 8:
        return None
    flags = raw[3]
    mtime = struct.unpack_from("<I", raw, 4)[0]
    os_byte = raw[9]
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
    return GzipHeader(
        flags=flags,
        mtime=mtime,
        os_byte=os_byte,
        original_filename=original_filename,
        has_extra=bool(flags & 0x04),
        has_name=bool(flags & 0x08),
        has_comment=bool(flags & 0x10),
        has_header_crc=bool(flags & 0x02),
        header_end=base_offset + pos,
    )


def parse_gzip_members(raw: bytes) -> list[GzipMember]:
    members: list[GzipMember] = []
    raw_offset = 0
    full_dec_offset = 0
    previous_member: GzipMember | None = None
    previous_slot_end = 0

    while raw_offset < len(raw):
        candidate_start = raw.find(b"\x1f\x8b", raw_offset)
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
        padding_before = None
        if candidate_start > previous_slot_end:
            padding_before = PaddingRange(previous_slot_end, candidate_start)

        if previous_member is not None:
            previous_member.next_member_start = candidate_start
            previous_member.slot_end = candidate_start
            previous_member.slot_size = previous_member.slot_end - previous_member.raw_start
            previous_member.padding_after_size = candidate_start - previous_member.raw_end
            if previous_member.padding_after_size > 0:
                previous_member.padding_after = PaddingRange(previous_member.raw_end, candidate_start)

        member_raw = raw[candidate_start:raw_end]
        trailer_crc = trailer_isize = None
        if len(member_raw) >= 8:
            trailer_crc, trailer_isize = struct.unpack("<II", member_raw[-8:])
        member = GzipMember(
            index=len(members), raw_start=candidate_start, raw_end=raw_end, raw=member_raw,
            decompressed=decompressed, header=parse_gzip_header(member_raw, candidate_start),
            trailer_crc32=trailer_crc, trailer_isize=trailer_isize,
            full_decompressed_start=full_dec_offset, next_member_start=len(raw),
            slot_end=len(raw), slot_size=len(raw) - candidate_start,
            padding_after_size=len(raw) - raw_end, padding_before=padding_before,
        )
        members.append(member)
        previous_member = member
        previous_slot_end = raw_end
        raw_offset = raw_end
        full_dec_offset += len(decompressed)

    if previous_member is not None:
        previous_member.next_member_start = len(raw)
        previous_member.slot_end = len(raw)
        previous_member.slot_size = previous_member.slot_end - previous_member.raw_start
        previous_member.padding_after_size = len(raw) - previous_member.raw_end
        if previous_member.padding_after_size > 0:
            previous_member.padding_after = PaddingRange(previous_member.raw_end, len(raw))

    return members


def make_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.{stamp}.{counter}.bak")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def member_name(member: GzipMember) -> str:
    if member.header and member.header.original_filename is not None:
        return member.header.original_filename
    return "unavailable"


def gzip_recompress_with_metadata(payload: bytes, member: GzipMember) -> bytes:
    mtime = member.header.mtime if member.header else None
    filename = member.header.original_filename if member.header and member.header.original_filename else ""
    out = BytesIO()
    with gzip.GzipFile(filename=filename, mode="wb", fileobj=out, mtime=mtime) as gz:
        gz.write(payload)
    return out.getvalue()


def build_slot_payload(raw: bytes, member: GzipMember, recompressed: bytes) -> bytes:
    if len(recompressed) > member.slot_size:
        raise SystemExit(
            f"Recompressed selected member does not fit in its slot ({len(recompressed)} > {member.slot_size}); output not written"
        )
    remainder_size = member.slot_size - len(recompressed)
    original_padding = raw[member.raw_end:member.slot_end]
    if remainder_size == len(original_padding):
        return recompressed + original_padding
    if remainder_size == 0:
        return recompressed
    if original_padding and all(byte == 0 for byte in original_padding):
        return recompressed + (b"\x00" * remainder_size)
    if not original_padding:
        raise SystemExit("Recompressed member is smaller, but the original slot had no padding layout to preserve; output not written")
    raise SystemExit("Recompressed member changes non-zero/non-uniform padding layout; output not written")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patch one float32 inside one parsed town.bin gzip member slot.")
    parser.add_argument("--input", type=Path, required=True, help="Input town.bin path")
    parser.add_argument("--output", type=Path, help="Output path; required unless --in-place is passed")
    parser.add_argument("--member", type=int, required=True, help="Zero-based gzip member index")
    parser.add_argument("--offset", type=int, required=True, help="Decompressed byte offset within selected member")
    parser.add_argument("--expect-float", type=float, required=True, help="Expected float32 value at --offset")
    parser.add_argument("--new-float", type=float, required=True, help="Replacement float32 value")
    parser.add_argument("--endian", choices=("little", "big"), default="little", help="Float byte order (default: little)")
    parser.add_argument("--in-place", action="store_true", help="Modify --input after creating a timestamped backup")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if not args.input.exists() or not args.input.is_file():
        raise SystemExit(f"--input does not exist or is not a file: {args.input}")
    if args.in_place and args.output:
        raise SystemExit("Use either --in-place or --output, not both")
    if not args.in_place and args.output is None:
        raise SystemExit("--output is required unless --in-place is passed")
    if args.output and args.output.resolve() == args.input.resolve():
        raise SystemExit("Refusing to overwrite --input via --output; use --in-place")
    if args.offset < 0:
        raise SystemExit("--offset must be non-negative")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_args(args)
    raw = args.input.read_bytes()
    members = parse_gzip_members(raw)
    if args.member < 0 or args.member >= len(members):
        raise SystemExit(f"--member {args.member} is out of range; found {len(members)} member(s)")

    selected = members[args.member]
    if args.offset + 4 > len(selected.decompressed):
        raise SystemExit(
            f"--offset {args.offset} cannot read 4 bytes inside member {selected.index} decompressed size {len(selected.decompressed)}"
        )

    fmt = "<f" if args.endian == "little" else ">f"
    old_bytes = selected.decompressed[args.offset:args.offset + 4]
    actual = struct.unpack(fmt, old_bytes)[0]
    if abs(actual - args.expect_float) > FLOAT_TOLERANCE:
        raise SystemExit(
            f"Expected float mismatch at member {selected.index} offset {args.offset}: "
            f"actual {actual!r}, expected {args.expect_float!r}; output not written"
        )

    patched = bytearray(selected.decompressed)
    new_bytes = struct.pack(fmt, args.new_float)
    patched[args.offset:args.offset + 4] = new_bytes
    patched_bytes = bytes(patched)
    recompressed = gzip_recompress_with_metadata(patched_bytes, selected)
    slot_payload = build_slot_payload(raw, selected, recompressed)

    out_bytes = bytearray(raw)
    out_bytes[selected.raw_start:selected.slot_end] = slot_payload
    out = bytes(out_bytes)
    after = parse_gzip_members(out)
    if len(after) != len(members):
        raise SystemExit(f"Patched output has unexpected gzip member count ({len(after)} != {len(members)}); output not written")
    others_unchanged = all(
        raw[member.raw_start:member.slot_end] == out[member.raw_start:member.slot_end]
        for member in members
        if member.index != selected.index
    )
    if not others_unchanged:
        raise SystemExit("Internal error: non-selected member slot changed; output not written")
    if raw[:selected.raw_start] != out[:selected.raw_start] or raw[selected.slot_end:] != out[selected.slot_end:]:
        raise SystemExit("Internal error: bytes outside the selected member slot changed; output not written")

    output_path = args.input if args.in_place else args.output
    backup = make_backup(args.input) if args.in_place else None
    assert output_path is not None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(out)

    print("POC town float patch report")
    print(f"Input path: {args.input}")
    print(f"Output path: {output_path}")
    if backup:
        print(f"Backup path: {backup}")
    print(f"Input SHA1: {sha1_hex(raw)}")
    print(f"Output SHA1: {sha1_hex(out)}")
    print(f"Member index/name: {selected.index}/{member_name(selected)}")
    print(f"Offset: {args.offset}")
    print(f"Old float: {actual:.9g}")
    print(f"New float: {args.new_float:.9g}")
    print(f"Old bytes: {old_bytes.hex()}")
    print(f"New bytes: {new_bytes.hex()}")
    print(f"Selected member old decompressed SHA1: {sha1_hex(selected.decompressed)}")
    print(f"Selected member new decompressed SHA1: {sha1_hex(after[selected.index].decompressed)}")
    print(f"Selected member recompressed size: {len(recompressed)}")
    print(f"Selected member slot size: {selected.slot_size}")
    print(f"All other members unchanged: {'yes' if others_unchanged else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

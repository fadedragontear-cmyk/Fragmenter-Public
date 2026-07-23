#!/usr/bin/env python3
"""Probe marker-adjacent values inside one padded town.bin gzip member.

This is a read-only, standard-library-only CLI companion to
``poc_town_member_probe.py``.  It parses the same padded concatenated gzip
member container, decompresses one selected member for marker inspection, and
writes comparison-friendly text/JSON reports.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import string
import struct
import sys
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_TEXT_REPORT = Path("workspace/reports/town04_marker_probe.txt")
DEFAULT_JSON_REPORT = Path("workspace/reports/town04_marker_probe.json")
DEFAULT_WINDOW = 128
VALUE_WINDOW = 64
FLOAT_LIMIT = 100000.0


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


def find_occurrences(blob: bytes, needle: bytes) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = blob.find(needle, start)
        if offset == -1:
            return offsets
        offsets.append(offset)
        start = offset + 1


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
            index=len(members),
            raw_start=candidate_start,
            raw_end=raw_end,
            raw=member_raw,
            decompressed=decompressed,
            header=parse_gzip_header(member_raw, candidate_start),
            trailer_crc32=trailer_crc,
            trailer_isize=trailer_isize,
            full_decompressed_start=full_dec_offset,
            next_member_start=len(raw),
            slot_end=len(raw),
            slot_size=len(raw) - candidate_start,
            padding_after_size=len(raw) - raw_end,
            padding_before=padding_before,
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


def member_name(member: GzipMember) -> str:
    if member.header and member.header.original_filename is not None:
        return member.header.original_filename
    return "unavailable"


def printable_text(blob: bytes) -> str:
    printable = set(string.printable) - set("\x0b\x0c")
    return "".join(chr(byte) if chr(byte) in printable else "." for byte in blob)


def scalar_candidates(blob: bytes, center: int, radius: int = VALUE_WINDOW) -> dict[str, list[dict[str, Any]]]:
    start = max(0, center - radius)
    end = min(len(blob), center + radius)
    out: dict[str, list[dict[str, Any]]] = {"float32_le": [], "float32_be": [], "int16_le": [], "int16_be": [], "int32_le": [], "int32_be": []}
    for offset in range(start, end):
        if offset + 4 <= len(blob):
            for key, fmt in (("float32_le", "<f"), ("float32_be", ">f")):
                value = struct.unpack_from(fmt, blob, offset)[0]
                if math.isfinite(value) and abs(value) < FLOAT_LIMIT:
                    out[key].append({"offset": offset, "relative": offset - center, "value": value})
            for key, fmt in (("int32_le", "<i"), ("int32_be", ">i")):
                out[key].append({"offset": offset, "relative": offset - center, "value": struct.unpack_from(fmt, blob, offset)[0]})
        if offset + 2 <= len(blob):
            for key, fmt in (("int16_le", "<h"), ("int16_be", ">h")):
                out[key].append({"offset": offset, "relative": offset - center, "value": struct.unpack_from(fmt, blob, offset)[0]})
    return out


def float_triples(blob: bytes, center: int, radius: int = VALUE_WINDOW) -> list[dict[str, Any]]:
    start = max(0, center - radius)
    end = min(len(blob), center + radius)
    triples: list[dict[str, Any]] = []
    for endian, fmt in (("little", "<fff"), ("big", ">fff")):
        for offset in range(start, max(start, end - 11)):
            values = struct.unpack_from(fmt, blob, offset)
            if all(math.isfinite(value) and abs(value) < FLOAT_LIMIT for value in values):
                triples.append({"offset": offset, "relative": offset - center, "endian": endian, "values": list(values)})
    return triples


def occurrence_report(member: GzipMember, marker: str, offset: int) -> dict[str, Any]:
    blob = member.decompressed
    before = blob[max(0, offset - DEFAULT_WINDOW):offset]
    after = blob[offset + len(marker):min(len(blob), offset + len(marker) + DEFAULT_WINDOW)]
    return {
        "member_index": member.index,
        "gzip_original_filename": member_name(member),
        "marker_name": marker,
        "decompressed_offset": offset,
        "before_hex": before.hex(),
        "after_hex": after.hex(),
        "before_text": printable_text(before),
        "after_text": printable_text(after),
        "candidate_values": scalar_candidates(blob, offset),
        "coordinate_like_float_triples": float_triples(blob, offset),
    }


def analyze_member(member: GzipMember, markers: list[str]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for marker in markers:
        for offset in find_occurrences(member.decompressed, marker.encode("ascii")):
            reports.append(occurrence_report(member, marker, offset))
    return reports


def compare_members(left: GzipMember, right: GzipMember, markers: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for marker in markers:
        left_offsets = find_occurrences(left.decompressed, marker.encode("ascii"))
        right_offsets = find_occurrences(right.decompressed, marker.encode("ascii"))
        for i, left_offset in enumerate(left_offsets):
            right_offset = right_offsets[i] if i < len(right_offsets) else None
            rows.append({
                "marker_name": marker,
                "occurrence_ordinal": i,
                "left_member_index": left.index,
                "left_filename": member_name(left),
                "left_offset": left_offset,
                "right_member_index": right.index,
                "right_filename": member_name(right),
                "right_offset": right_offset,
                "offset_difference": None if right_offset is None else right_offset - left_offset,
                "left_nearby_float_triples": float_triples(left.decompressed, left_offset)[:20],
                "right_nearby_float_triples": [] if right_offset is None else float_triples(right.decompressed, right_offset)[:20],
            })
        for j in range(len(left_offsets), len(right_offsets)):
            rows.append({
                "marker_name": marker,
                "occurrence_ordinal": j,
                "left_member_index": left.index,
                "left_filename": member_name(left),
                "left_offset": None,
                "right_member_index": right.index,
                "right_filename": member_name(right),
                "right_offset": right_offsets[j],
                "offset_difference": None,
                "left_nearby_float_triples": [],
                "right_nearby_float_triples": float_triples(right.decompressed, right_offsets[j])[:20],
            })
    return rows


def build_report(input_path: Path, selected: GzipMember, members: list[GzipMember], markers: list[str]) -> dict[str, Any]:
    occurrences = analyze_member(selected, markers)
    comparison: list[dict[str, Any]] = []
    if selected.index in (8, 9) and len(members) > (9 if selected.index == 8 else 8):
        other = members[9 if selected.index == 8 else 8]
        comparison = compare_members(selected, other, markers)
    return {
        "input_path": str(input_path),
        "input_sha1": sha1_hex(input_path.read_bytes()),
        "member_count": len(members),
        "selected_member": {
            "index": selected.index,
            "gzip_original_filename": member_name(selected),
            "raw_start": selected.raw_start,
            "raw_end": selected.raw_end,
            "raw_size": selected.raw_size,
            "slot_end": selected.slot_end,
            "slot_size": selected.slot_size,
            "padding_after_size": selected.padding_after_size,
            "decompressed_size": len(selected.decompressed),
            "decompressed_sha1": sha1_hex(selected.decompressed),
            "header": None if selected.header is None else asdict(selected.header),
        },
        "markers": markers,
        "occurrences": occurrences,
        "town04_member_8_9_comparison": comparison,
    }


def write_text_report(report: dict[str, Any], path: Path) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        selected = report["selected_member"]
        print("POC town marker probe report")
        print(f"Input: {report['input_path']}")
        print(f"Input SHA1: {report['input_sha1']}")
        print(f"Gzip member count: {report['member_count']}")
        print(f"Selected member: {selected['index']} ({selected['gzip_original_filename']})")
        print(f"Selected decompressed size: {selected['decompressed_size']}")
        print(f"Markers: {', '.join(report['markers'])}")
        print(f"Occurrence count: {len(report['occurrences'])}")
        for occ in report["occurrences"]:
            print("\n--- occurrence ---")
            print(f"member={occ['member_index']} filename={occ['gzip_original_filename']} marker={occ['marker_name']} offset={occ['decompressed_offset']}")
            print(f"before_hex={occ['before_hex']}")
            print(f"after_hex={occ['after_hex']}")
            print(f"before_text={occ['before_text']}")
            print(f"after_text={occ['after_text']}")
            print("coordinate_like_float_triples(first 20)=")
            print(json.dumps(occ["coordinate_like_float_triples"][:20], indent=2))
            print("candidate_values(first 20 per type)=")
            print(json.dumps({k: v[:20] for k, v in occ["candidate_values"].items()}, indent=2))
        if report["town04_member_8_9_comparison"]:
            print("\nMember 8/9 comparison:")
            for row in report["town04_member_8_9_comparison"]:
                print(json.dumps(row, sort_keys=True))
    text = buf.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def parse_markers(value: str) -> list[str]:
    markers = [part.strip() for part in value.split(",") if part.strip()]
    if not markers:
        raise argparse.ArgumentTypeError("--markers must name at least one marker")
    for marker in markers:
        try:
            marker.encode("ascii")
        except UnicodeEncodeError as exc:
            raise argparse.ArgumentTypeError(f"marker must be ASCII: {marker!r}") from exc
    return markers


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Path to town.bin")
    parser.add_argument("--member", required=True, type=int, help="Exactly one gzip member index to analyze")
    parser.add_argument("--markers", required=True, type=parse_markers, help="Comma-separated marker names, e.g. DMY_gate,LGT_shop01,CCSFchgate")
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON_REPORT, help=f"JSON report path (default: {DEFAULT_JSON_REPORT})")
    parser.add_argument("--text-out", type=Path, default=DEFAULT_TEXT_REPORT, help=f"Text report path (default: {DEFAULT_TEXT_REPORT})")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    raw = args.input.read_bytes()
    members = parse_gzip_members(raw)
    if args.member < 0 or args.member >= len(members):
        raise SystemExit(f"--member {args.member} is out of range; parsed {len(members)} members")
    report = build_report(args.input, members[args.member], members, args.markers)
    text = write_text_report(report, args.text_out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(text, end="")
    print(f"\nWrote text report: {args.text_out}")
    print(f"Wrote JSON report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

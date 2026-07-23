#!/usr/bin/env python3
"""Inspect and cautiously patch gzip-member structure in Area Server town.bin.

This tool avoids blind full-file recompression.  It can copy raw bytes exactly,
walk concatenated gzip members, recompress members independently for diagnostics,
or patch one equal-length occurrence inside one selected member while copying all
other members byte-for-byte.
"""
from __future__ import annotations

import argparse
import binascii
import gzip
import hashlib
import shutil
import struct
import sys
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_SEARCH = "sr4sun1.bmp"
CCSF = b"CCSF"


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


def ascii_bytes(value: str, label: str) -> bytes:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SystemExit(f"{label} must be ASCII: {value!r}") from exc
    if not encoded:
        raise SystemExit(f"{label} must not be empty")
    return encoded


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

def full_decompressed(members: list[GzipMember]) -> bytes:
    return b"".join(member.decompressed for member in members)


def make_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.{stamp}.{counter}.bak")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def write_output(input_path: Path, output_path: Path | None, data: bytes, in_place: bool) -> tuple[Path, Path | None]:
    if in_place:
        backup = make_backup(input_path)
        input_path.write_bytes(data)
        return input_path, backup
    if output_path is None:
        raise SystemExit("Write mode requires --output unless --in-place is passed")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    return output_path, None


def gzip_recompress(payload: bytes) -> bytes:
    return gzip.compress(payload)


def gzip_recompress_with_metadata(payload: bytes, *, filename: str | None = None, mtime: int | None = None) -> bytes:
    out = bytearray()
    # gzip.GzipFile wants a file-like object; BytesIO is intentionally avoided here
    # to keep imports small by using the fileobj protocol implemented by bytearray via
    # a tiny local adapter.
    class _BytearrayWriter:
        def write(self, data: bytes) -> int:
            out.extend(data)
            return len(data)

    with gzip.GzipFile(filename=filename or "", mode="wb", fileobj=_BytearrayWriter(), mtime=mtime) as gz:
        gz.write(payload)
    return bytes(out)


def recompress_members_preserving_padding(raw: bytes, members: list[GzipMember]) -> bytes:
    pieces: list[bytes] = []
    raw_offset = 0
    for member in members:
        pieces.append(raw[raw_offset:member.raw_start])
        pieces.append(gzip_recompress(member.decompressed))
        raw_offset = member.raw_end
    pieces.append(raw[raw_offset:])
    return b"".join(pieces)


def recompress_members_in_slots(raw: bytes, members: list[GzipMember]) -> tuple[bytes, list[tuple[GzipMember, int, bool]]]:
    out = bytearray(raw)
    fit_statuses: list[tuple[GzipMember, int, bool]] = []
    for member in members:
        recompressed = gzip_recompress(member.decompressed)
        fits = len(recompressed) <= member.slot_size
        fit_statuses.append((member, len(recompressed), fits))
        if not fits:
            continue
        recompressed_end = member.raw_start + len(recompressed)
        out[member.raw_start:recompressed_end] = recompressed
        out[recompressed_end:member.slot_end] = b"\x00" * (member.slot_end - recompressed_end)
    return bytes(out), fit_statuses


def print_slot_fit_statuses(fit_statuses: list[tuple[GzipMember, int, bool]]) -> None:
    print("Per-member fit status:")
    headers = ["index", "raw_start", "slot_end", "slot_size", "recompressed_size", "fits"]
    rows = [
        [
            str(member.index),
            str(member.raw_start),
            str(member.slot_end),
            str(member.slot_size),
            str(recompressed_size),
            "yes" if fits else "no",
        ]
        for member, recompressed_size, fits in fit_statuses
    ]
    print(format_table(rows, headers))


def format_list(values: list[int]) -> str:
    return ",".join(str(value) for value in values) if values else "none"


def format_table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    header_line = " | ".join(header.ljust(widths[i]) for i, header in enumerate(headers))
    separator = "-+-".join("-" * width for width in widths)
    row_lines = [" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows]
    return "\n".join([header_line, separator, *row_lines])


def member_table_row(member: GzipMember, search: bytes) -> list[str]:
    ccsf_offsets = find_occurrences(member.decompressed, CCSF)
    search_offsets = find_occurrences(member.decompressed, search)
    full_offsets = [member.full_decompressed_start + offset for offset in search_offsets]
    first_ccsf = str(ccsf_offsets[0]) if ccsf_offsets else "none"
    original_filename = "unavailable"
    gzip_mtime = "unavailable"
    if member.header:
        if member.header.original_filename is not None:
            original_filename = member.header.original_filename
        gzip_mtime = str(member.header.mtime)
    return [
        str(member.index),
        str(member.raw_start),
        str(member.raw_end),
        str(member.raw_size),
        str(member.next_member_start),
        str(member.slot_end),
        str(member.slot_size),
        str(member.padding_after_size),
        sha1_hex(member.raw),
        str(len(member.decompressed)),
        sha1_hex(member.decompressed),
        original_filename,
        gzip_mtime,
        first_ccsf,
        format_list(ccsf_offsets),
        "yes" if search_offsets else "no",
        format_list(search_offsets),
        format_list(full_offsets),
    ]


def print_member(member: GzipMember, search: bytes) -> None:
    headers = [
        "index",
        "raw_start",
        "raw_end",
        "raw_size",
        "next_member_start",
        "slot_end",
        "slot_size",
        "padding_after_size",
        "raw SHA1",
        "decompressed size",
        "decompressed SHA1",
        "gzip original filename",
        "gzip mtime",
        "first CCSF marker",
        "all CCSF markers",
        "search string occurs",
        "occurrence offsets (member decompressed)",
        "occurrence offsets (logical full decompressed)",
    ]
    print(format_table([member_table_row(member, search)], headers))


def report_members(raw: bytes, members: list[GzipMember], search: bytes) -> None:
    print("POC town gzip member probe inspect report")
    print(f"Raw size: {len(raw)}")
    print(f"Raw SHA1: {sha1_hex(raw)}")
    full_dec = full_decompressed(members)
    print(f"Full decompressed size: {len(full_dec)}")
    print(f"Full decompressed SHA1: {sha1_hex(full_dec)}")
    print(f"Gzip member count: {len(members)}")
    if len(members) == 1:
        print("Only one gzip member is present.")
    else:
        print("Multiple gzip members are present.")
    print("Member table:")
    headers = [
        "index",
        "raw_start",
        "raw_end",
        "raw_size",
        "next_member_start",
        "slot_end",
        "slot_size",
        "padding_after_size",
        "raw SHA1",
        "decompressed size",
        "decompressed SHA1",
        "gzip original filename",
        "gzip mtime",
        "first CCSF marker",
        "all CCSF markers",
        "search string occurs",
        "occurrence offsets (member decompressed)",
        "occurrence offsets (logical full decompressed)",
    ]
    rows = [member_table_row(member, search) for member in members]
    print(format_table(rows, headers))
    print_transplant_direction_report(members)


def recompressed_transplant_size(donor: GzipMember, destination: GzipMember) -> int:
    filename = member_name(destination) if member_name(destination) != "unavailable" else None
    mtime = destination.header.mtime if destination.header else None
    return len(gzip_recompress_with_metadata(donor.decompressed, filename=filename, mtime=mtime))


def transplant_direction_rows(members: list[GzipMember]) -> list[list[str]]:
    rows: list[list[str]] = []
    for donor in members:
        for destination in members:
            if donor.index == destination.index:
                continue
            donor_recompressed_size = recompressed_transplant_size(donor, destination)
            fits = donor_recompressed_size <= destination.slot_size
            rows.append(
                [
                    str(donor.index),
                    member_name(donor),
                    str(destination.index),
                    member_name(destination),
                    str(donor_recompressed_size),
                    str(destination.slot_size),
                    "yes" if fits else "no",
                ]
            )
    return rows


def print_transplant_direction_report(members: list[GzipMember]) -> None:
    print("Compatible transplant directions:")
    headers = [
        "donor index",
        "donor gzip original filename",
        "destination index",
        "destination gzip original filename",
        "donor recompressed size",
        "destination slot size",
        "fits",
    ]
    rows = transplant_direction_rows(members)
    if not rows:
        print("none")
        return
    print(format_table(rows, headers))

def validate_common(args: argparse.Namespace) -> None:
    if args.in_place and args.output:
        raise SystemExit("Use either --in-place or --output, not both")
    if args.output and args.output.resolve() == args.input.resolve() and not args.in_place:
        raise SystemExit("Refusing to overwrite --input via --output; use --in-place")


def print_roundtrip_report(raw: bytes, out: bytes, members_before: list[GzipMember], members_after: list[GzipMember]) -> None:
    dec_before = full_decompressed(members_before)
    dec_after = full_decompressed(members_after)
    print(f"Original raw SHA1: {sha1_hex(raw)}")
    print(f"Output raw SHA1: {sha1_hex(out)}")
    print(f"Original logical decompressed SHA1: {sha1_hex(dec_before)}")
    print(f"Output logical decompressed SHA1: {sha1_hex(dec_after)}")
    print(f"Member count before: {len(members_before)}")
    print(f"Member count after: {len(members_after)}")
    print(f"Logical decompressed SHA1 matches: {'yes' if sha1_hex(dec_before) == sha1_hex(dec_after) else 'no'}")


def member_name(member: GzipMember) -> str:
    if member.header and member.header.original_filename is not None:
        return member.header.original_filename
    return "unavailable"


def changed_byte_range(before: bytes, after: bytes) -> str:
    if before == after:
        return "none"
    first = next(i for i, (old, new) in enumerate(zip(before, after)) if old != new)
    last = max(i for i in range(min(len(before), len(after))) if before[i] != after[i])
    if len(before) != len(after):
        last = max(last, len(before), len(after) - 1)
    return f"[{first}, {last + 1})"


def bytes_outside_range_unchanged(before: bytes, after: bytes, start: int, end: int) -> bool:
    return before[:start] == after[:start] and before[end:] == after[end:]


def print_transplant_report(
    raw: bytes,
    out: bytes,
    source: GzipMember,
    destination: GzipMember,
    recompressed_size: int,
    fits: bool,
    other_member_raw_sha1s_unchanged: bool,
) -> None:
    print("POC town transplant-member report")
    print(f"Source member index: {source.index}")
    print(f"Source member name: {member_name(source)}")
    print(f"Source member raw SHA1: {sha1_hex(source.raw)}")
    print(f"Source member decompressed SHA1: {sha1_hex(source.decompressed)}")
    print(f"Destination member index: {destination.index}")
    print(f"Destination member name: {member_name(destination)}")
    print(f"Destination member raw_start: {destination.raw_start}")
    print(f"Destination member slot_size: {destination.slot_size}")
    print(f"Recompressed size: {recompressed_size}")
    print(f"Fits: {'yes' if fits else 'no'}")
    print(f"Original full raw SHA1: {sha1_hex(raw)}")
    print(f"Output full raw SHA1: {sha1_hex(out)}")
    print(f"Changed bytes range: {changed_byte_range(raw, out)}")
    print(f"All other member raw SHA1s unchanged: {'yes' if other_member_raw_sha1s_unchanged else 'no'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose and cautiously patch town.bin gzip member structure.")
    parser.add_argument("--input", type=Path, required=True, help="Input town.bin path")
    parser.add_argument("--output", type=Path, help="Output path for write modes")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--inspect-members", action="store_true", help="Print gzip member breakdown")
    modes.add_argument("--copy-roundtrip", action="store_true", help="Copy original raw bytes exactly")
    modes.add_argument(
        "--member-roundtrip",
        action="store_true",
        help=(
            "UNSAFE for packed/aligned town.bin: recompresses members independently and "
            "collapses member layout and padding; prefer --slot-roundtrip"
        ),
    )
    modes.add_argument("--slot-roundtrip", action="store_true", help="Recompress each gzip member in place within its padded slot")
    modes.add_argument("--patch-one-member", action="store_true", help="Patch one occurrence inside one member")
    modes.add_argument("--transplant-member", action="store_true", help="Transplant one decompressed member payload into another padded member slot")
    modes.add_argument("--raw-search", action="store_true", help="Search raw compressed bytes")
    modes.add_argument("--raw-patch-one", action="store_true", help="Unsafe equal-length raw byte patch of one occurrence")
    parser.add_argument("--search", default=DEFAULT_SEARCH, help=f"ASCII search text. Default: {DEFAULT_SEARCH}")
    parser.add_argument("--member", type=int, help="Zero-based member index for --patch-one-member")
    parser.add_argument("--from-member", type=int, help="Zero-based source member index for --transplant-member")
    parser.add_argument("--to-member", type=int, help="Zero-based destination member index for --transplant-member")
    parser.add_argument("--occurrence", type=int, help="Zero-based occurrence index")
    parser.add_argument("--from", dest="from_text", help="ASCII source text for patch modes")
    parser.add_argument("--to", dest="to_text", help="ASCII replacement text for patch modes")
    parser.add_argument("--in-place", action="store_true", help="Modify --input after creating a timestamped backup")
    parser.add_argument(
        "--preserve-target-gzip-name",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Preserve destination member gzip FNAME metadata when available (default: true)",
    )
    parser.add_argument(
        "--preserve-target-mtime",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Preserve destination member gzip mtime metadata (default: true)",
    )
    parser.add_argument(
        "--allow-unsafe-member-roundtrip",
        action="store_true",
        help=(
            "Explicitly allow --member-roundtrip for non-container diagnostics; "
            "it collapses member layout and padding in packed/aligned town.bin"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_common(args)
    raw = args.input.read_bytes()

    if args.copy_roundtrip:
        out_path, backup = write_output(args.input, args.output, raw, args.in_place)
        written = out_path.read_bytes()
        print("POC town copy-roundtrip report")
        print(f"Output path: {out_path}")
        print(f"Input raw SHA1: {sha1_hex(raw)}")
        print(f"Output raw SHA1: {sha1_hex(written)}")
        print(f"Raw SHA1 matches: {'yes' if sha1_hex(raw) == sha1_hex(written) else 'no'}")
        if backup:
            print(f"Backup path: {backup}")
        return 0

    search = ascii_bytes(args.search, "--search")

    if args.raw_search or args.raw_patch_one:
        if args.raw_patch_one and args.from_text is None:
            raise SystemExit("--raw-patch-one requires --from TEXT")
        raw_offsets = find_occurrences(raw, search if args.raw_search else ascii_bytes(args.from_text, "--from"))
        print("POC town raw byte search report")
        print(f"Raw SHA1: {sha1_hex(raw)}")
        print(f"Raw occurrences: {len(raw_offsets)}")
        print(f"Raw offsets: {raw_offsets if raw_offsets else 'none'}")
        if args.raw_search:
            if raw_offsets:
                print("Raw occurrences can be patched with --raw-patch-one, but this is unsafe unless outside compressed data/header.")
            return 0
        if args.from_text is None or args.to_text is None:
            raise SystemExit("--raw-patch-one requires --from TEXT and --to TEXT")
        source = ascii_bytes(args.from_text, "--from")
        target = ascii_bytes(args.to_text, "--to")
        if len(source) != len(target):
            raise SystemExit(f"--from and --to must have equal byte length ({len(source)} != {len(target)})")
        if args.occurrence is None:
            raise SystemExit("--raw-patch-one requires --occurrence N")
        if args.occurrence < 0 or args.occurrence >= len(raw_offsets):
            raise SystemExit(f"--occurrence {args.occurrence} is out of range; found {len(raw_offsets)} raw occurrence(s)")
        offset = raw_offsets[args.occurrence]
        print("UNSAFE: raw patching may corrupt gzip CRC or compressed payload semantics unless the occurrence is outside compressed data/header.")
        out = raw[:offset] + target + raw[offset + len(source):]
        out_path, backup = write_output(args.input, args.output, out, args.in_place)
        print(f"Patched raw occurrence: {args.occurrence}")
        print(f"Raw patch offset: {offset}")
        print(f"Output path: {out_path}")
        print(f"Original raw SHA1: {sha1_hex(raw)}")
        print(f"Output raw SHA1: {sha1_hex(out)}")
        if backup:
            print(f"Backup path: {backup}")
        return 0

    members = parse_gzip_members(raw)

    if args.inspect_members:
        report_members(raw, members, search)
        return 0

    if args.transplant_member:
        if args.from_member is None or args.to_member is None:
            raise SystemExit("--transplant-member requires --from-member N and --to-member N")
        if args.from_member < 0 or args.from_member >= len(members):
            raise SystemExit(f"--from-member {args.from_member} is out of range; found {len(members)} member(s)")
        if args.to_member < 0 or args.to_member >= len(members):
            raise SystemExit(f"--to-member {args.to_member} is out of range; found {len(members)} member(s)")

        source = members[args.from_member]
        destination = members[args.to_member]
        filename = member_name(destination) if args.preserve_target_gzip_name and member_name(destination) != "unavailable" else None
        mtime = destination.header.mtime if args.preserve_target_mtime and destination.header else None
        recompressed = gzip_recompress_with_metadata(source.decompressed, filename=filename, mtime=mtime)
        fits = len(recompressed) <= destination.slot_size
        if not fits:
            print_transplant_report(raw, raw, source, destination, len(recompressed), fits, True)
            raise SystemExit(
                f"Recompressed source member does not fit in destination slot "
                f"({len(recompressed)} > {destination.slot_size}); output not written"
            )

        out_bytes = bytearray(raw)
        recompressed_end = destination.raw_start + len(recompressed)
        out_bytes[destination.raw_start:recompressed_end] = recompressed
        out_bytes[recompressed_end:destination.slot_end] = b"\x00" * (destination.slot_end - recompressed_end)
        out = bytes(out_bytes)
        after = parse_gzip_members(out)
        if len(after) != len(members):
            raise SystemExit(f"Transplanted output has unexpected gzip member count ({len(after)} != {len(members)}); output not written")
        other_member_raw_sha1s_unchanged = all(
            sha1_hex(member.raw) == sha1_hex(after[member.index].raw)
            for member in members
            if member.index != destination.index
        )
        if not other_member_raw_sha1s_unchanged:
            raise SystemExit("Internal error: non-destination member raw SHA1 changed; output not written")
        if not bytes_outside_range_unchanged(raw, out, destination.raw_start, destination.slot_end):
            raise SystemExit("Internal error: bytes outside the destination slot changed; output not written")

        out_path, backup = write_output(args.input, args.output, out, args.in_place)
        written = out_path.read_bytes()
        print_transplant_report(raw, written, source, destination, len(recompressed), fits, other_member_raw_sha1s_unchanged)
        print(f"Output path: {out_path}")
        if backup:
            print(f"Backup path: {backup}")
        return 0

    if args.member_roundtrip:
        if not args.allow_unsafe_member_roundtrip:
            raise SystemExit(
                "--member-roundtrip is unsafe for packed/aligned town.bin because it collapses "
                "member layout and padding. Use --slot-roundtrip instead, or pass "
                "--allow-unsafe-member-roundtrip only for non-container diagnostics."
            )
        out = recompress_members_preserving_padding(raw, members)
        after = parse_gzip_members(out)
        out_path, backup = write_output(args.input, args.output, out, args.in_place)
        print("POC town UNSAFE member-roundtrip report: collapses member layout and padding")
        print(f"Output path: {out_path}")
        print_roundtrip_report(raw, out, members, after)
        if backup:
            print(f"Backup path: {backup}")
        return 0

    if args.slot_roundtrip:
        out, fit_statuses = recompress_members_in_slots(raw, members)
        print("POC town slot-roundtrip report")
        print_slot_fit_statuses(fit_statuses)
        if not all(fits for _, _, fits in fit_statuses):
            raise SystemExit("One or more recompressed members do not fit in their original padded slots; output not written")
        out_path, backup = write_output(args.input, args.output, out, args.in_place)
        written = out_path.read_bytes()
        after = parse_gzip_members(written)
        print(f"Output path: {out_path}")
        print_roundtrip_report(raw, written, members, after)
        if backup:
            print(f"Backup path: {backup}")
        return 0

    if args.patch_one_member:
        if args.member is None or args.occurrence is None or args.from_text is None or args.to_text is None:
            raise SystemExit("--patch-one-member requires --member N, --occurrence N, --from TEXT, and --to TEXT")
        source = ascii_bytes(args.from_text, "--from")
        target = ascii_bytes(args.to_text, "--to")
        if len(source) != len(target):
            raise SystemExit(f"--from and --to must have equal byte length ({len(source)} != {len(target)})")
        if args.member < 0 or args.member >= len(members):
            raise SystemExit(f"--member {args.member} is out of range; found {len(members)} member(s)")
        selected = members[args.member]
        offsets = find_occurrences(selected.decompressed, source)
        if args.occurrence < 0 or args.occurrence >= len(offsets):
            raise SystemExit(f"--occurrence {args.occurrence} is out of range for member {args.member}; found {len(offsets)} occurrence(s)")
        dec_offset = offsets[args.occurrence]
        replacement_count = 1
        patched_dec = bytearray(selected.decompressed)
        patched_dec[dec_offset:dec_offset + len(source)] = target
        patched_dec_bytes = bytes(patched_dec)
        recompressed = gzip_recompress(patched_dec_bytes)
        if len(recompressed) > selected.slot_size:
            raise SystemExit(
                f"Recompressed selected member does not fit in its slot "
                f"({len(recompressed)} > {selected.slot_size}); output not written"
            )

        out_bytes = bytearray(raw)
        recompressed_end = selected.raw_start + len(recompressed)
        out_bytes[selected.raw_start:recompressed_end] = recompressed
        out_bytes[recompressed_end:selected.slot_end] = b"\x00" * (selected.slot_end - recompressed_end)
        out = bytes(out_bytes)
        after = parse_gzip_members(out)
        if len(after) != len(members):
            raise SystemExit(f"Patched output has unexpected gzip member count ({len(after)} != {len(members)}); output not written")
        unchanged_ok = all(
            raw[member.raw_start:member.slot_end] == out[member.raw_start:member.slot_end]
            for member in members
            if member.index != selected.index
        )
        if not unchanged_ok:
            raise SystemExit("Internal error: bytes outside the selected member slot changed; output not written")
        if replacement_count != 1:
            raise SystemExit(f"Replacement count must be exactly 1 ({replacement_count}); output not written")

        out_path, backup = write_output(args.input, args.output, out, args.in_place)
        print("POC town patch-one-member report")
        print(f"Output path: {out_path}")
        print(f"Selected member index: {selected.index}")
        print(f"Selected member FNAME: {selected.header.original_filename if selected.header and selected.header.original_filename is not None else 'unavailable'}")
        print(f"Selected member raw_start: {selected.raw_start}")
        print(f"Selected member raw_end: {selected.raw_end}")
        print(f"Selected member slot_end: {selected.slot_end}")
        print(f"Patched occurrence in member: {args.occurrence}")
        print(f"Member decompressed offset: {dec_offset}")
        print(f"Full decompressed offset: {selected.full_decompressed_start + dec_offset}")
        print(f"Source bytes: {source!r}")
        print(f"Target bytes: {target!r}")
        print(f"Replacement count: {replacement_count}")
        print(f"Only selected member decompressed: yes")
        print(f"Only selected member recompressed: yes")
        print(f"Unchanged members copied raw byte-for-byte: {'yes' if unchanged_ok else 'no'}")
        print(f"Old selected member decompressed SHA1: {sha1_hex(selected.decompressed)}")
        print(f"New selected member decompressed SHA1: {sha1_hex(after[selected.index].decompressed)}")
        print(f"Old full raw SHA1: {sha1_hex(raw)}")
        print(f"New full raw SHA1: {sha1_hex(out)}")
        print(f"Original selected member raw SHA1: {sha1_hex(selected.raw)}")
        print(f"Output selected member raw SHA1: {sha1_hex(after[selected.index].raw)}")
        if backup:
            print(f"Backup path: {backup}")
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

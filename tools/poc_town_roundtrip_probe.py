#!/usr/bin/env python3
"""
Inspect, round-trip, and carefully patch Area Server town.bin-like payloads.

The script treats gzip compression as a transport wrapper: all inspection and
patching is performed against decompressed bytes, then write modes re-apply gzip
when the input used gzip magic bytes.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_SEARCH = "sr4sun1.bmp"
SYMBOL_PREFIXES = (b"CCSF", b"TEX_", b"MDL_", b"MAT_", b"DMY_", b"OBJ_", b"LGT_", b"ANM_", b"CAM_")
CONTEXT_BYTES = 32


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


def read_input(path: Path) -> tuple[bytes, bytes, bool]:
    raw = path.read_bytes()
    is_gzip = raw[:2] == b"\x1f\x8b"
    decompressed = gzip.decompress(raw) if is_gzip else raw
    return raw, decompressed, is_gzip


def output_decompressed(raw_output: bytes, is_gzip: bool) -> bytes:
    return gzip.decompress(raw_output) if is_gzip else raw_output


def find_occurrences(blob: bytes, needle: bytes) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = blob.find(needle, start)
        if offset == -1:
            return offsets
        offsets.append(offset)
        start = offset + 1


def printable_context(blob: bytes) -> str:
    chars: list[str] = []
    for byte in blob:
        if 32 <= byte <= 126:
            chars.append(chr(byte))
        else:
            chars.append(".")
    return "".join(chars)


def nearest_previous(blob: bytes, offset: int, needles: tuple[bytes, ...]) -> tuple[bytes, int] | None:
    best_needle: bytes | None = None
    best_offset = -1
    haystack = blob[:offset]
    for needle in needles:
        found = haystack.rfind(needle)
        if found > best_offset:
            best_needle = needle
            best_offset = found
    if best_needle is None:
        return None
    return best_needle, best_offset


def print_occurrences(blob: bytes, search: bytes) -> None:
    offsets = find_occurrences(blob, search)
    print(f"Search bytes: {search.decode('ascii', errors='backslashreplace')!r}")
    print(f"Occurrences: {len(offsets)}")
    for index, offset in enumerate(offsets):
        before_start = max(0, offset - CONTEXT_BYTES)
        after_end = min(len(blob), offset + len(search) + CONTEXT_BYTES)
        before = printable_context(blob[before_start:offset])
        after = printable_context(blob[offset + len(search):after_end])
        ccsf = nearest_previous(blob, offset, (b"CCSF",))
        symbol = nearest_previous(blob, offset, SYMBOL_PREFIXES)
        ccsf_text = f"offset {ccsf[1]}" if ccsf else "not found"
        symbol_text = f"{symbol[0].decode('ascii')} at offset {symbol[1]}" if symbol else "not found"
        print(f"Occurrence {index}:")
        print(f"  Decompressed offset: {offset}")
        print(f"  32-byte before context: {before!r}")
        print(f"  32-byte after context: {after!r}")
        print(f"  Nearest previous CCSF marker: {ccsf_text}")
        print(f"  Nearest previous known symbol prefix: {symbol_text}")


def make_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.{stamp}.{counter}.bak")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def write_output(path: Path, data: bytes, in_place: bool) -> Path | None:
    backup = make_backup(path) if in_place else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return backup


def print_hash_report(raw_in: bytes, dec_in: bytes, raw_out: bytes, dec_out: bytes) -> None:
    print(f"Original raw SHA1: {sha1_hex(raw_in)}")
    print(f"Original decompressed SHA1: {sha1_hex(dec_in)}")
    print(f"Output raw SHA1: {sha1_hex(raw_out)}")
    print(f"Output decompressed SHA1: {sha1_hex(dec_out)}")
    print(f"Decompressed SHA1 matches: {'yes' if sha1_hex(dec_in) == sha1_hex(dec_out) else 'no'}")


def patch_one(blob: bytes, source: bytes, target: bytes, occurrence: int) -> tuple[bytes, int, int]:
    offsets = find_occurrences(blob, source)
    if occurrence < 0 or occurrence >= len(offsets):
        raise SystemExit(f"--occurrence {occurrence} is out of range; found {len(offsets)} occurrence(s)")
    offset = offsets[occurrence]
    return blob[:offset] + target + blob[offset + len(source):], 1, len(offsets)


def patch_all(blob: bytes, source: bytes, target: bytes) -> tuple[bytes, int, int]:
    count = blob.count(source)
    return blob.replace(source, target), count, count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect, round-trip, or patch town.bin payloads safely.")
    parser.add_argument("--input", type=Path, required=True, help="Input path.")
    parser.add_argument("--output", type=Path, help="Output path for write modes.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--inspect", action="store_true", help="Inspect without writing.")
    modes.add_argument("--roundtrip", action="store_true", help="Write an unchanged round-tripped copy.")
    modes.add_argument("--patch-one", action="store_true", help="Patch exactly one occurrence of --from.")
    modes.add_argument("--patch-all", action="store_true", help="Patch every occurrence of --from.")
    parser.add_argument("--search", default=DEFAULT_SEARCH, help=f"ASCII search text for --inspect. Default: {DEFAULT_SEARCH}")
    parser.add_argument("--occurrence", type=int, help="Zero-based occurrence index required by --patch-one.")
    parser.add_argument("--from", dest="from_text", help="ASCII source text required by patch modes.")
    parser.add_argument("--to", dest="to_text", help="ASCII target text required by patch modes.")
    parser.add_argument("--in-place", action="store_true", help="Write back to --input after creating a timestamped backup.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.in_place and args.output:
        raise SystemExit("Use either --in-place or --output, not both")
    if args.inspect:
        if args.output:
            raise SystemExit("--output is not used with --inspect")
        if args.in_place:
            raise SystemExit("--in-place is not used with --inspect")
    else:
        if not args.in_place and not args.output:
            raise SystemExit("Write modes require --output unless --in-place is passed")
        if args.output and args.output.resolve() == args.input.resolve():
            raise SystemExit("Refusing to overwrite --input via --output; use --in-place to modify the input")
    if args.patch_one or args.patch_all:
        if args.from_text is None or args.to_text is None:
            raise SystemExit("Patch modes require --from TEXT and --to TEXT")
        if args.patch_one and args.occurrence is None:
            raise SystemExit("--patch-one requires --occurrence N")
    elif args.occurrence is not None or args.from_text is not None or args.to_text is not None:
        raise SystemExit("--occurrence, --from, and --to are only valid with patch modes")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_args(args)

    raw, decompressed, is_gzip = read_input(args.input)

    if args.inspect:
        search = ascii_bytes(args.search, "--search")
        print("POC town roundtrip probe inspect report")
        print(f"Input path: {args.input}")
        print(f"Raw size: {len(raw)}")
        print(f"Raw SHA1: {sha1_hex(raw)}")
        print(f"Gzip detected: {'yes' if is_gzip else 'no'}")
        print(f"Decompressed size: {len(decompressed)}")
        print(f"Decompressed SHA1: {sha1_hex(decompressed)}")
        print_occurrences(decompressed, search)
        return 0

    output_path = args.input if args.in_place else args.output
    assert output_path is not None
    backup: Path | None = None

    if args.roundtrip:
        patched_decompressed = decompressed
        patch_count = 0
        total_found = 0
    else:
        source = ascii_bytes(args.from_text, "--from")
        target = ascii_bytes(args.to_text, "--to")
        if len(source) != len(target):
            raise SystemExit(f"--from and --to must have equal byte length ({len(source)} != {len(target)})")
        if args.patch_one:
            patched_decompressed, patch_count, total_found = patch_one(decompressed, source, target, args.occurrence)
        else:
            print("Unsafe: patches every occurrence and may crash the Area Server.", file=sys.stderr)
            patched_decompressed, patch_count, total_found = patch_all(decompressed, source, target)

    raw_output = gzip.compress(patched_decompressed) if is_gzip else patched_decompressed
    backup = write_output(output_path, raw_output, args.in_place)
    decompressed_output = output_decompressed(raw_output, is_gzip)

    print("POC town roundtrip probe write report")
    print(f"Input path: {args.input}")
    print(f"Output path: {output_path}")
    print(f"Gzip detected: {'yes' if is_gzip else 'no'}")
    if args.roundtrip:
        print("Mode: roundtrip")
    else:
        print(f"Mode: {'patch-one' if args.patch_one else 'patch-all'}")
        print(f"Found patch candidates: {total_found}")
        print(f"Patch count: {patch_count}")
    print_hash_report(raw, decompressed, raw_output, decompressed_output)
    if backup:
        print(f"Backup path: {backup}")
    if not args.in_place:
        print("Original input was not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

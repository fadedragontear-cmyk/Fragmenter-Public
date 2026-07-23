#!/usr/bin/env python3
"""
Minimal safe proof-of-concept texture-path swapper for Area Server town.bin.

Default replacement:
    sr4sun1.bmp -> sr4clo2.bmp

The replacement is equal-length ASCII, so decompressed binary size and offsets are
preserved.  If the input is gzip-compressed, patching happens in memory and the
output is gzip-compressed again.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_FROM = b"sr4sun1.bmp"
DEFAULT_TO = b"sr4clo2.bmp"
EXPECTED_REPLACEMENTS = 1


def parse_ascii(value: str, label: str) -> bytes:
    try:
        return value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SystemExit(f"{label} must be ASCII: {value!r}") from exc


def parse_swap(value: str) -> tuple[bytes, bytes]:
    if "=" not in value:
        raise SystemExit("--swap must use FROM=TO syntax")
    source, target = value.split("=", 1)
    return parse_ascii(source, "swap FROM"), parse_ascii(target, "swap TO")


def validate_equal_length(swaps: list[tuple[bytes, bytes]]) -> None:
    for source, target in swaps:
        if len(source) != len(target):
            raise SystemExit(
                "Replacement strings must have exactly the same byte length: "
                f"{source!r} is {len(source)} bytes, {target!r} is {len(target)} bytes"
            )
        if not source:
            raise SystemExit("Replacement source string must not be empty")


def read_maybe_gzip(path: Path) -> tuple[bytes, bool, bytes]:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw), True, raw
    return raw, False, raw


def sha1_hex(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()


def make_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.{stamp}.{counter}.bak")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def patch_blob(blob: bytes, swaps: list[tuple[bytes, bytes]]) -> tuple[bytes, list[int]]:
    patched = blob
    counts: list[int] = []
    for source, target in swaps:
        count = patched.count(source)
        counts.append(count)
        if count:
            patched = patched.replace(source, target)
    return patched, counts


def restore_backup(backup: Path, destination: Path) -> None:
    if not backup.exists():
        raise SystemExit(f"Backup path does not exist: {backup}")
    if not backup.is_file():
        raise SystemExit(f"Backup path is not a file: {backup}")
    if destination.exists():
        saved = make_backup(destination)
        print(f"Existing destination backed up before restore: {saved}")
    shutil.copy2(backup, destination)
    print(f"Restored backup: {backup}")
    print(f"Destination: {destination}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely swap equal-length ASCII texture filename strings in "
            ".hack//frägment Area Server data/town.bin."
        )
    )
    parser.add_argument("--input", type=Path, help="Input data/town.bin path.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Patched output path. Required unless --dry-run, --in-place, or --restore is used.",
    )
    parser.add_argument(
        "--from",
        dest="from_text",
        default=DEFAULT_FROM.decode("ascii"),
        help="ASCII source string to replace. Default: sr4sun1.bmp",
    )
    parser.add_argument(
        "--to",
        dest="to_text",
        default=DEFAULT_TO.decode("ascii"),
        help="ASCII target string. Default: sr4clo2.bmp",
    )
    parser.add_argument(
        "--swap",
        action="append",
        default=[],
        metavar="FROM=TO",
        help=(
            "Additional or alternative equal-length ASCII swap. May be repeated. "
            "When supplied, --from/--to are ignored."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing output.")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Patch --input directly after creating a timestamped backup.",
    )
    parser.add_argument(
        "--restore",
        type=Path,
        metavar="BACKUP",
        help="Restore BACKUP over --input. The current --input is backed up first if it exists.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.restore:
        if not args.input:
            raise SystemExit("--input is required with --restore")
        restore_backup(args.restore, args.input)
        return 0

    if not args.input:
        raise SystemExit("--input is required")
    if args.in_place and args.output:
        raise SystemExit("Use either --output or --in-place, not both")
    if not args.dry_run and not args.in_place and not args.output:
        raise SystemExit("--output is required unless --dry-run or --in-place is used")

    swaps = [parse_swap(item) for item in args.swap]
    if not swaps:
        swaps = [(parse_ascii(args.from_text, "--from"), parse_ascii(args.to_text, "--to"))]
    validate_equal_length(swaps)

    decompressed, was_gzip, original_file_bytes = read_maybe_gzip(args.input)
    patched_decompressed, counts = patch_blob(decompressed, swaps)
    total_count = sum(counts)

    if total_count == 0:
        print("No replacements found; no change was made.", file=sys.stderr)
        print(f"Input path: {args.input}")
        print(f"Gzip detected: {'yes' if was_gzip else 'no'}")
        for (source, target), count in zip(swaps, counts):
            print(f"Replacement: {source.decode('ascii')} -> {target.decode('ascii')} count={count}")
        print(f"Original SHA1: {sha1_hex(original_file_bytes)}")
        return 1

    if total_count > EXPECTED_REPLACEMENTS:
        print(
            f"WARNING: replacement count is {total_count}, expected about {EXPECTED_REPLACEMENTS}.",
            file=sys.stderr,
        )

    patched_file_bytes = gzip.compress(patched_decompressed) if was_gzip else patched_decompressed
    output_path = args.input if args.in_place else args.output
    backup_path: Path | None = None

    if not args.dry_run:
        if args.in_place:
            backup_path = make_backup(args.input)
        assert output_path is not None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(patched_file_bytes)

    print("POC town texture swap report")
    print(f"Input path: {args.input}")
    print(f"Output path: {output_path if output_path else '(dry run; no output written)'}")
    print(f"Gzip detected: {'yes' if was_gzip else 'no'}")
    print(f"Replacement count: {total_count}")
    for (source, target), count in zip(swaps, counts):
        print(f"  {source.decode('ascii')} -> {target.decode('ascii')}: {count}")
    print(f"Original SHA1: {sha1_hex(original_file_bytes)}")
    print(f"Patched SHA1: {sha1_hex(patched_file_bytes)}")
    if backup_path:
        print(f"Backup path: {backup_path}")
    if args.dry_run:
        print("Dry run: no output was written.")
    elif args.in_place:
        print("Restore: rerun with --restore BACKUP --input ORIGINAL_PATH, or copy the backup back manually.")
    else:
        print("Original input was not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

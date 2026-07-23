#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = ROOT / "assets" / "celdra"
FRAME_COUNT = 70
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def frame_names() -> list[str]:
    return [f"{index:02d}.png" for index in range(1, FRAME_COUNT + 1)]


def validate_png(path: Path) -> None:
    try:
        with path.open("rb") as fh:
            signature = fh.read(len(PNG_SIGNATURE))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if signature != PNG_SIGNATURE:
        raise ValueError(f"{path} is not a PNG file")


def sync_frames(source: Path, dest: Path, dry_run: bool = False) -> list[Path]:
    source = source.expanduser().resolve()
    dest = dest.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"source directory does not exist: {source}")

    missing = [name for name in frame_names() if not (source / name).is_file()]
    if missing:
        preview = ", ".join(missing[:8])
        suffix = "..." if len(missing) > 8 else ""
        raise ValueError(f"source is missing {len(missing)} Celdra frame(s): {preview}{suffix}")

    for name in frame_names():
        validate_png(source / name)

    copied: list[Path] = []
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
    for name in frame_names():
        target = dest / name
        copied.append(target)
        if not dry_run:
            shutil.copy2(source / name, target)
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy local Serenial Celdra PNG frames into assets/celdra without any network fetches."
    )
    parser.add_argument("source", type=Path, help="Directory containing 01.png through 70.png from serenial-assets")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help=f"Destination directory (default: {DEFAULT_DEST})")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print what would be copied")
    args = parser.parse_args(argv)

    try:
        copied = sync_frames(args.source, args.dest, dry_run=args.dry_run)
    except ValueError as exc:
        print(f"[celdra-sync] {exc}", file=sys.stderr)
        return 1

    action = "Validated" if args.dry_run else "Copied"
    print(f"[celdra-sync] {action} {len(copied)} frame(s) into {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

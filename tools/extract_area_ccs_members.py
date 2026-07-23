#!/usr/bin/env python3
"""Extract selected padded gzip CCS members from an Area Server container."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from fragmenter_containers import GzipMember, read_members
from fragmenter_identifiers import extract_identifiers


def safe_name(name: str | None, index: int) -> str:
    base = name or f"member_{index}.cmp"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(base).name).strip("._") or f"member_{index}.cmp"


def ccsf_name(payload: bytes) -> str | None:
    for row in extract_identifiers(payload):
        name = str(row.get("name", ""))
        if name.startswith("CCSF"):
            return name
    return None


def parse_member_list(text: str | None) -> set[int]:
    if not text:
        return set()
    indexes: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            indexes.add(int(part, 10))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid member index {part!r}") from exc
    return indexes


def ensure_writable(paths: list[Path], force: bool) -> None:
    existing = [p for p in paths if p.exists()]
    if existing and not force:
        joined = "\n".join(str(p) for p in existing)
        raise FileExistsError(f"Refusing to overwrite existing output; pass --force:\n{joined}")


def write_member(member: GzipMember, out_dir: Path, write_raw: bool, write_decompressed: bool, force: bool) -> dict[str, object]:
    name = safe_name(member.gzip_original_filename, member.index)
    stem = f"{member.index}_{name}"
    raw_path = out_dir / f"{stem}.raw.cmp"
    dec_path = out_dir / f"{stem}.decompressed.ccs"
    meta_path = out_dir / f"{stem}.metadata.json"
    targets = [meta_path]
    if write_raw:
        targets.append(raw_path)
    if write_decompressed:
        targets.append(dec_path)
    ensure_writable(targets, force)
    out_dir.mkdir(parents=True, exist_ok=True)

    detected_ccsf = ccsf_name(member.decompressed)
    metadata = member.metadata()
    metadata.update({
        "input_gzip_original_name": member.gzip_original_filename,
        "ccsf_name": detected_ccsf,
        "outputs": {
            "raw": str(raw_path) if write_raw else None,
            "decompressed": str(dec_path) if write_decompressed else None,
            "metadata": str(meta_path),
        },
    })
    if write_raw:
        raw_path.write_bytes(member.raw)
    if write_decompressed:
        dec_path.write_bytes(member.decompressed)
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return {"member": member, "gzip_name": name, "ccsf_name": detected_ccsf, "output": dec_path if write_decompressed else (raw_path if write_raw else meta_path)}


def print_table(rows: list[dict[str, object]]) -> None:
    headers = ["index", "gzip name", "raw_start", "raw_size", "slot_size", "decompressed_size", "CCSF name", "output path"]
    data = []
    for row in rows:
        m: GzipMember = row["member"]  # type: ignore[assignment]
        data.append([m.index, row["gzip_name"], m.raw_start, m.raw_size, m.slot_size, m.decompressed_size, row.get("ccsf_name") or "", row["output"]])
    widths = [len(h) for h in headers]
    for row in data:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(str(value)))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for row in data:
        print(fmt.format(*[str(v) for v in row]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--members", help="Comma-separated member indexes, e.g. 8,9,10")
    parser.add_argument("--all", action="store_true", help="Extract all members")
    parser.add_argument("--write-raw", action="store_true")
    parser.add_argument("--write-decompressed", action="store_true", default=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    members = read_members(args.input)
    wanted = set(range(len(members))) if args.all else parse_member_list(args.members)
    if not wanted:
        parser.error("pass --members or --all")
    missing = sorted(i for i in wanted if i < 0 or i >= len(members))
    if missing:
        parser.error(f"member indexes not found: {missing}; container has {len(members)} members")
    try:
        rows = [write_member(members[i], args.out_dir, args.write_raw, args.write_decompressed, args.force) for i in sorted(wanted)]
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Safe, layout-preserving patch engine for PlayStation 2 disc images.

The first version intentionally does not rebuild ISO9660/UDF structures.  It
copies the source image and changes bytes only inside existing file extents, so
the original boot sectors, directory records, file order, and LBAs remain
unchanged.

Manifest schema (version 1)::

    {
      "schema_version": 1,
      "source": {"sha256": "...", "size": 123},
      "operations": [
        {
          "id": "example",
          "type": "write_bytes",
          "path": "DATA/FILE.BIN",
          "offset": 16,
          "expected_hex": "01020304",
          "replacement_hex": "AABBCCDD"
        },
        {
          "id": "replacement",
          "type": "replace_file",
          "path": "DATA/OTHER.BIN",
          "source_file": "payloads/OTHER.BIN",
          "expected_sha256": "..."
        }
      ]
    }

Every operation is validated before the output image is copied. Replacement
files must be exactly the same logical size as the ISO entry in this version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660, IsoEntry, SECTOR_USER, normalize_path  # noqa: E402

SCHEMA_VERSION = 1
COPY_CHUNK = 1024 * 1024


class PatchError(RuntimeError):
    """Raised when a manifest or source image fails a safety check."""


@dataclass(frozen=True)
class PreparedOperation:
    operation_id: str
    operation_type: str
    internal_path: str
    entry: IsoEntry
    logical_offset: int
    length: int
    replacement: bytes | None = None
    replacement_file: Path | None = None

    @property
    def logical_end(self) -> int:
        return self.logical_offset + self.length


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(COPY_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_extent(image: BinaryIO, iso: Iso9660, entry: IsoEntry) -> str:
    digest = hashlib.sha256()
    position = 0
    while position < entry.size:
        take = min(COPY_CHUNK, entry.size - position)
        digest.update(read_extent_range(image, iso, entry, position, take))
        position += take
    return digest.hexdigest()


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PatchError(f"Could not read patch manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise PatchError("Patch manifest must contain a JSON object.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PatchError(f"Unsupported patch manifest schema: {payload.get('schema_version')!r}")
    if not isinstance(payload.get("source"), dict):
        raise PatchError("Patch manifest requires a source object.")
    if not isinstance(payload.get("operations"), list) or not payload["operations"]:
        raise PatchError("Patch manifest requires at least one operation.")
    return payload


def _parse_hex(value: Any, field: str) -> bytes:
    text = "".join(str(value or "").split())
    if not text:
        raise PatchError(f"{field} is required.")
    if len(text) % 2:
        raise PatchError(f"{field} must contain complete hexadecimal bytes.")
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise PatchError(f"{field} is not valid hexadecimal data.") from exc


def _physical_position(iso: Iso9660, entry: IsoEntry, logical_offset: int) -> tuple[int, int]:
    sector_delta, within_sector = divmod(logical_offset, SECTOR_USER)
    physical = (
        (entry.lba + sector_delta + iso.lba_offset) * iso.sector_size
        + iso.data_offset
        + within_sector
    )
    return physical, within_sector


def read_extent_range(
    image: BinaryIO,
    iso: Iso9660,
    entry: IsoEntry,
    logical_offset: int,
    length: int,
) -> bytes:
    if logical_offset < 0 or length < 0 or logical_offset + length > entry.size:
        raise PatchError(f"Read exceeds ISO extent for {entry.path}.")
    result = bytearray()
    position = logical_offset
    remaining = length
    while remaining:
        physical, within_sector = _physical_position(iso, entry, position)
        take = min(remaining, SECTOR_USER - within_sector)
        image.seek(physical)
        chunk = image.read(take)
        if len(chunk) != take:
            raise PatchError(f"Short read inside ISO extent for {entry.path}.")
        result.extend(chunk)
        position += take
        remaining -= take
    return bytes(result)


def write_extent_range(
    image: BinaryIO,
    iso: Iso9660,
    entry: IsoEntry,
    logical_offset: int,
    data: bytes,
) -> None:
    if logical_offset < 0 or logical_offset + len(data) > entry.size:
        raise PatchError(f"Write exceeds ISO extent for {entry.path}.")
    position = logical_offset
    consumed = 0
    while consumed < len(data):
        physical, within_sector = _physical_position(iso, entry, position)
        take = min(len(data) - consumed, SECTOR_USER - within_sector)
        image.seek(physical)
        image.write(data[consumed : consumed + take])
        position += take
        consumed += take


def _operation_id(raw: dict[str, Any], index: int) -> str:
    return str(raw.get("id") or f"operation-{index + 1}").strip() or f"operation-{index + 1}"


def _validate_source(source_iso: Path, source_spec: dict[str, Any]) -> dict[str, Any]:
    if not source_iso.is_file():
        raise PatchError(f"Source ISO does not exist: {source_iso}")
    expected_hash = str(source_spec.get("sha256") or "").strip().lower()
    if len(expected_hash) != 64 or any(ch not in "0123456789abcdef" for ch in expected_hash):
        raise PatchError("Manifest source.sha256 must contain a full SHA-256 hash.")
    actual_size = source_iso.stat().st_size
    if source_spec.get("size") is not None and int(source_spec["size"]) != actual_size:
        raise PatchError(
            f"Source ISO size mismatch: expected {int(source_spec['size'])}, found {actual_size}."
        )
    actual_hash = sha256_file(source_iso)
    if actual_hash.lower() != expected_hash:
        raise PatchError(
            "Source ISO SHA-256 mismatch. This patch only accepts the exact verified source image."
        )
    return {"path": str(source_iso), "size": actual_size, "sha256": actual_hash}


def _prepare_operations(
    source_iso: Path,
    iso: Iso9660,
    manifest_path: Path,
    operations: list[Any],
) -> list[PreparedOperation]:
    index = iso.build_index()
    prepared: list[PreparedOperation] = []
    with source_iso.open("rb") as image:
        for operation_index, raw in enumerate(operations):
            if not isinstance(raw, dict):
                raise PatchError(f"Operation {operation_index + 1} must be a JSON object.")
            operation_id = _operation_id(raw, operation_index)
            operation_type = str(raw.get("type") or "").strip()
            internal_path = normalize_path(raw.get("path"))
            if not internal_path:
                raise PatchError(f"{operation_id}: path is required.")
            entry = index.get(internal_path)
            if entry is None:
                raise PatchError(f"{operation_id}: ISO file was not found: {internal_path}")

            if operation_type == "write_bytes":
                try:
                    logical_offset = int(raw.get("offset"))
                except (TypeError, ValueError) as exc:
                    raise PatchError(f"{operation_id}: offset must be an integer.") from exc
                expected = _parse_hex(raw.get("expected_hex"), f"{operation_id}.expected_hex")
                replacement = _parse_hex(raw.get("replacement_hex"), f"{operation_id}.replacement_hex")
                if len(expected) != len(replacement):
                    raise PatchError(f"{operation_id}: expected and replacement byte lengths differ.")
                actual = read_extent_range(image, iso, entry, logical_offset, len(expected))
                if actual != expected:
                    raise PatchError(
                        f"{operation_id}: original bytes do not match at {internal_path}+0x{logical_offset:X}."
                    )
                prepared.append(
                    PreparedOperation(
                        operation_id,
                        operation_type,
                        internal_path,
                        entry,
                        logical_offset,
                        len(replacement),
                        replacement=replacement,
                    )
                )
                continue

            if operation_type == "replace_file":
                source_file_value = str(raw.get("source_file") or "").strip()
                if not source_file_value:
                    raise PatchError(f"{operation_id}: source_file is required.")
                replacement_file = Path(source_file_value)
                if not replacement_file.is_absolute():
                    replacement_file = manifest_path.parent / replacement_file
                replacement_file = replacement_file.resolve()
                if not replacement_file.is_file():
                    raise PatchError(f"{operation_id}: replacement file does not exist: {replacement_file}")
                replacement_size = replacement_file.stat().st_size
                if replacement_size != entry.size:
                    raise PatchError(
                        f"{operation_id}: replacement size {replacement_size} does not match "
                        f"the ISO file size {entry.size}; relocation is not implemented yet."
                    )
                expected_hash = str(raw.get("expected_sha256") or "").strip().lower()
                if len(expected_hash) != 64 or any(
                    ch not in "0123456789abcdef" for ch in expected_hash
                ):
                    raise PatchError(f"{operation_id}: expected_sha256 is required for replace_file.")
                original_hash = sha256_extent(image, iso, entry)
                if original_hash.lower() != expected_hash:
                    raise PatchError(f"{operation_id}: original ISO file hash does not match.")
                prepared.append(
                    PreparedOperation(
                        operation_id,
                        operation_type,
                        internal_path,
                        entry,
                        0,
                        entry.size,
                        replacement_file=replacement_file,
                    )
                )
                continue

            raise PatchError(f"{operation_id}: unsupported operation type: {operation_type!r}")

    _reject_overlaps(prepared)
    return prepared


def _reject_overlaps(operations: list[PreparedOperation]) -> None:
    by_path: dict[str, list[PreparedOperation]] = {}
    for operation in operations:
        by_path.setdefault(operation.internal_path, []).append(operation)
    for internal_path, rows in by_path.items():
        rows.sort(key=lambda row: (row.logical_offset, row.logical_end))
        for previous, current in zip(rows, rows[1:]):
            if current.logical_offset < previous.logical_end:
                raise PatchError(
                    f"Operations {previous.operation_id!r} and {current.operation_id!r} overlap in {internal_path}."
                )


def _apply_prepared(output_path: Path, iso: Iso9660, operations: list[PreparedOperation]) -> None:
    with output_path.open("r+b") as image:
        for operation in operations:
            if operation.operation_type == "write_bytes":
                assert operation.replacement is not None
                write_extent_range(
                    image,
                    iso,
                    operation.entry,
                    operation.logical_offset,
                    operation.replacement,
                )
                continue
            assert operation.replacement_file is not None
            logical_offset = 0
            with operation.replacement_file.open("rb") as replacement:
                while True:
                    chunk = replacement.read(COPY_CHUNK)
                    if not chunk:
                        break
                    write_extent_range(image, iso, operation.entry, logical_offset, chunk)
                    logical_offset += len(chunk)
        image.flush()
        os.fsync(image.fileno())


def _verify_output(output_path: Path, iso: Iso9660, operations: list[PreparedOperation]) -> None:
    with output_path.open("rb") as image:
        for operation in operations:
            if operation.operation_type == "write_bytes":
                assert operation.replacement is not None
                actual = read_extent_range(
                    image,
                    iso,
                    operation.entry,
                    operation.logical_offset,
                    operation.length,
                )
                if actual != operation.replacement:
                    raise PatchError(f"Output verification failed for {operation.operation_id}.")
            else:
                assert operation.replacement_file is not None
                expected_hash = sha256_file(operation.replacement_file)
                actual_hash = sha256_extent(image, iso, operation.entry)
                if actual_hash != expected_hash:
                    raise PatchError(f"Output verification failed for {operation.operation_id}.")


def apply_manifest(
    source_iso: str | Path,
    manifest_path: str | Path,
    output_iso: str | Path | None = None,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    source = Path(source_iso).expanduser().resolve()
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = load_manifest(manifest_file)
    source_report = _validate_source(source, manifest["source"])

    iso = Iso9660(source).open()
    if iso.sector_size != SECTOR_USER or iso.data_offset != 0:
        raise PatchError(
            "Layout-preserving writes currently accept only standard 2048-byte-sector ISO images. "
            "Raw BIN/2352 images require EDC/ECC regeneration and are intentionally refused."
        )
    operations = _prepare_operations(source, iso, manifest_file, manifest["operations"])
    operation_report = [
        {
            "id": operation.operation_id,
            "type": operation.operation_type,
            "path": operation.internal_path,
            "offset": operation.logical_offset,
            "length": operation.length,
            "status": "validated" if dry_run else "applied",
        }
        for operation in operations
    ]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "validated" if dry_run else "applied",
        "source": source_report,
        "iso_layout": {
            "sector_size": iso.sector_size,
            "data_offset": iso.data_offset,
            "lba_offset": iso.lba_offset,
            "filesystem": iso.mode,
        },
        "operations": operation_report,
        "output": None,
    }
    if dry_run:
        return report
    if output_iso is None:
        raise PatchError("An output ISO path is required unless --dry-run is used.")

    output = Path(output_iso).expanduser().resolve()
    if output == source:
        raise PatchError("Output ISO must not overwrite the source ISO.")
    if output.exists() and not overwrite:
        raise PatchError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.fragmenter.tmp")
    try:
        shutil.copy2(source, temporary)
        _apply_prepared(temporary, iso, operations)
        _verify_output(temporary, iso, operations)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    report["output"] = {
        "path": str(output),
        "size": output.stat().st_size,
        "sha256": sha256_file(output),
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply a verified, size-preserving patch manifest to a copy of a PS2 ISO."
    )
    parser.add_argument("source_iso", help="Exact original ISO required by the manifest")
    parser.add_argument("manifest", help="Fragmenter ISO patch manifest JSON")
    parser.add_argument("--out", help="Patched output ISO path")
    parser.add_argument("--dry-run", action="store_true", help="Validate without creating an output ISO")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output ISO")
    parser.add_argument("--report", help="Optional JSON report path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = apply_manifest(
            args.source_iso,
            args.manifest,
            args.out,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    except PatchError as exc:
        print(f"Patch refused: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

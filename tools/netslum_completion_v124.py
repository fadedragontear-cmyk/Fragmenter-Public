#!/usr/bin/env python3
"""Build and apply a local 3.8-preview to Netslum 4.0 completion pack.

The tool never modifies either reference ISO. A completion pack contains only
verified differing byte ranges, not complete game files. Applying a pack writes
to a temporary copy and publishes the requested output only after every target
file hash matches the known 4.0 reference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660, IsoEntry, SECTOR_USER, normalize_path  # noqa: E402
from iso_patch_engine import (  # noqa: E402
    COPY_CHUNK,
    read_extent_range,
    sha256_extent,
    write_extent_range,
)

SCHEMA = 1
MAX_PACK_PAYLOAD = 128 * 1024 * 1024
MERGE_EQUAL_GAP = 16
FINAL_VOLUME_LABEL = "FRAGMENT 4.0 ENGLISH"
VOLUME_DESCRIPTOR_START_LBA = 16
VOLUME_DESCRIPTOR_LIMIT = 64
VOLUME_IDENTIFIER_OFFSET = 40
VOLUME_IDENTIFIER_LENGTH = 32


class CompletionPackError(RuntimeError):
    """Raised when completion-pack creation or application is unsafe."""


Progress = Callable[[str], None]


def _encoded_volume_label(label: str) -> bytes:
    try:
        encoded = label.encode("ascii")
    except UnicodeEncodeError as exc:
        raise CompletionPackError("ISO volume label must contain ASCII characters only.") from exc
    if not encoded or len(encoded) > VOLUME_IDENTIFIER_LENGTH:
        raise CompletionPackError(
            f"ISO volume label must be 1-{VOLUME_IDENTIFIER_LENGTH} ASCII bytes."
        )
    return encoded.ljust(VOLUME_IDENTIFIER_LENGTH, b" ")


def _primary_volume_descriptor_offset(handle, iso: Any) -> int:
    for lba in range(VOLUME_DESCRIPTOR_START_LBA, VOLUME_DESCRIPTOR_LIMIT):
        physical = (
            (lba + int(getattr(iso, "lba_offset", 0))) * iso.sector_size
            + iso.data_offset
        )
        handle.seek(physical)
        header = handle.read(7)
        if len(header) != 7:
            break
        descriptor_type = header[0]
        if header[1:6] != b"CD001" or header[6] != 1:
            raise CompletionPackError(
                f"Invalid ISO9660 volume descriptor at logical block {lba}."
            )
        if descriptor_type == 1:
            return physical
        if descriptor_type == 255:
            break
    raise CompletionPackError("ISO has no readable primary volume descriptor.")


def read_iso_volume_label(handle, iso: Any) -> str:
    descriptor = _primary_volume_descriptor_offset(handle, iso)
    handle.seek(descriptor + VOLUME_IDENTIFIER_OFFSET)
    raw = handle.read(VOLUME_IDENTIFIER_LENGTH)
    if len(raw) != VOLUME_IDENTIFIER_LENGTH:
        raise CompletionPackError("ISO primary volume label is truncated.")
    return raw.decode("ascii", errors="replace").rstrip(" ")


def write_iso_volume_label(handle, iso: Any, label: str = FINAL_VOLUME_LABEL) -> None:
    encoded = _encoded_volume_label(label)
    descriptor = _primary_volume_descriptor_offset(handle, iso)
    handle.seek(descriptor + VOLUME_IDENTIFIER_OFFSET)
    handle.write(encoded)
    handle.flush()
    os.fsync(handle.fileno())
    if read_iso_volume_label(handle, iso) != label:
        raise CompletionPackError("ISO volume-label verification failed.")


def _notify(progress: Progress | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _entry_hash(handle, iso: Any, entry: IsoEntry) -> str:
    return sha256_extent(handle, iso, entry)


def _write_difference_payload(
    preview_handle,
    preview_iso: Any,
    preview_entry: IsoEntry,
    reference_handle,
    reference_iso: Any,
    reference_entry: IsoEntry,
    payload_path: Path,
) -> tuple[list[dict[str, int]], int, int]:
    if preview_entry.size != reference_entry.size:
        raise CompletionPackError(
            f"Cannot create an in-place completion for resized file {preview_entry.path}."
        )

    ranges: list[dict[str, int]] = []
    payload_offset = 0
    differing_bytes = 0
    position = 0
    run_start: int | None = None
    run_payload = bytearray()
    equal_gap = bytearray()

    def flush(payload_handle) -> None:
        nonlocal run_start, run_payload, equal_gap, payload_offset
        if run_start is None:
            return
        data = bytes(run_payload)
        payload_handle.write(data)
        ranges.append(
            {
                "offset": run_start,
                "length": len(data),
                "payload_offset": payload_offset,
            }
        )
        payload_offset += len(data)
        run_start = None
        run_payload = bytearray()
        equal_gap = bytearray()

    with payload_path.open("wb") as payload_handle:
        while position < preview_entry.size:
            take = min(COPY_CHUNK, preview_entry.size - position)
            before = read_extent_range(
                preview_handle, preview_iso, preview_entry, position, take
            )
            after = read_extent_range(
                reference_handle, reference_iso, reference_entry, position, take
            )
            if before == after:
                flush(payload_handle)
                position += take
                continue

            for delta, (old_byte, new_byte) in enumerate(zip(before, after)):
                absolute = position + delta
                if old_byte != new_byte:
                    differing_bytes += 1
                    if run_start is None:
                        run_start = absolute
                    if equal_gap:
                        run_payload.extend(equal_gap)
                        equal_gap.clear()
                    run_payload.append(new_byte)
                elif run_start is not None:
                    equal_gap.append(new_byte)
                    if len(equal_gap) > MERGE_EQUAL_GAP:
                        flush(payload_handle)
            position += take
        flush(payload_handle)

    size = payload_path.stat().st_size
    if size > MAX_PACK_PAYLOAD:
        raise CompletionPackError(
            f"Completion payload for {preview_entry.path} is too large "
            f"({size:,} bytes; cap {MAX_PACK_PAYLOAD:,})."
        )
    return ranges, differing_bytes, size


def build_completion_pack(
    preview_iso: str | Path,
    reference_iso: str | Path,
    pack_path: str | Path,
    *,
    iso_factory: Callable[[Path], Any] = Iso9660,
    progress: Progress | None = None,
) -> dict[str, Any]:
    preview_path = Path(preview_iso).expanduser().resolve()
    reference_path = Path(reference_iso).expanduser().resolve()
    destination = Path(pack_path).expanduser().resolve()
    if preview_path == reference_path:
        raise CompletionPackError("Choose different preview and 4.0 reference ISOs.")
    if destination in {preview_path, reference_path}:
        raise CompletionPackError("The completion pack must not overwrite either ISO.")
    if not preview_path.is_file() or not reference_path.is_file():
        raise CompletionPackError("Both comparison ISOs must exist.")

    try:
        preview = iso_factory(preview_path).open()
        reference = iso_factory(reference_path).open()
        preview_index = preview.build_index()
        reference_index = reference.build_index()
    except (OSError, ValueError) as exc:
        raise CompletionPackError(f"Could not read an ISO filesystem: {exc}") from exc

    if preview.sector_size != SECTOR_USER or preview.data_offset != 0:
        raise CompletionPackError(
            "The Fragmenter preview must be a standard 2048-byte-sector ISO; "
            "raw images require EDC/ECC regeneration."
        )

    if set(preview_index) != set(reference_index):
        missing = sorted(set(reference_index) - set(preview_index))
        extra = sorted(set(preview_index) - set(reference_index))
        raise CompletionPackError(
            "The ISO file sets differ; an in-place completion is unsafe "
            f"(missing={missing}, extra={extra})."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_pack = destination.with_name(
        f".{destination.name}.{os.getpid()}.fragmenter.tmp"
    )
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "tool": "Fragmenter V124 local Netslum 4.0 completion",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "kind": "Fragmenter English Preview",
            "name": preview_path.name,
            "image_size": preview_path.stat().st_size,
            "files": len(preview_index),
        },
        "reference": {
            "kind": "Known Netslum/Tellipatch 4.0",
            "name": reference_path.name,
            "image_size": reference_path.stat().st_size,
            "files": len(reference_index),
        },
        "files": [],
        "summary": {},
        "scope_note": (
            "The ZIP contains only differing byte ranges bound to exact source "
            "and target file hashes. It does not contain complete game files."
        ),
    }

    try:
        with tempfile.TemporaryDirectory(prefix="fragmenter-v124-") as folder:
            payload_root = Path(folder)
            prepared_payloads: list[tuple[Path, str]] = []
            total_differing = 0
            total_payload = 0

            with preview_path.open("rb") as preview_handle, reference_path.open(
                "rb"
            ) as reference_handle:
                paths = sorted(preview_index)
                for number, internal_path in enumerate(paths, start=1):
                    preview_entry = preview_index[internal_path]
                    reference_entry = reference_index[internal_path]
                    if preview_entry.size != reference_entry.size:
                        raise CompletionPackError(
                            f"File size differs for {internal_path}: "
                            f"{preview_entry.size:,} != {reference_entry.size:,}."
                        )
                    preview_hash = _entry_hash(
                        preview_handle, preview, preview_entry
                    )
                    reference_hash = _entry_hash(
                        reference_handle, reference, reference_entry
                    )
                    if preview_hash == reference_hash:
                        if number % 20 == 0 or number == len(paths):
                            _notify(
                                progress,
                                f"Compared {number:,}/{len(paths):,} files",
                            )
                        continue

                    payload_member = (
                        f"payload/{len(manifest['files']):02d}-"
                        + internal_path.replace("/", "_")
                        + ".bin"
                    )
                    payload_file = payload_root / Path(payload_member).name
                    ranges, differing, payload_size = _write_difference_payload(
                        preview_handle,
                        preview,
                        preview_entry,
                        reference_handle,
                        reference,
                        reference_entry,
                        payload_file,
                    )
                    if not ranges or payload_size <= 0:
                        raise CompletionPackError(
                            f"Changed file {internal_path} produced no byte ranges."
                        )
                    payload_hash = hashlib.sha256(
                        payload_file.read_bytes()
                    ).hexdigest()
                    manifest["files"].append(
                        {
                            "path": internal_path,
                            "size": preview_entry.size,
                            "source_sha256": preview_hash,
                            "target_sha256": reference_hash,
                            "payload_member": payload_member,
                            "payload_size": payload_size,
                            "payload_sha256": payload_hash,
                            "differing_bytes": differing,
                            "ranges": ranges,
                        }
                    )
                    prepared_payloads.append((payload_file, payload_member))
                    total_differing += differing
                    total_payload += payload_size
                    if total_payload > MAX_PACK_PAYLOAD:
                        raise CompletionPackError(
                            f"Combined completion payload exceeds {MAX_PACK_PAYLOAD:,} bytes."
                        )
                    _notify(
                        progress,
                        f"Mapped {internal_path}: {differing:,} differing bytes "
                        f"in {len(ranges):,} ranges",
                    )

            if not manifest["files"]:
                raise CompletionPackError(
                    "The preview already matches the 4.0 reference file contents."
                )
            manifest["summary"] = {
                "changed_files": len(manifest["files"]),
                "differing_bytes": total_differing,
                "payload_bytes": total_payload,
            }

            with zipfile.ZipFile(
                temporary_pack,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                )
                for payload_file, member in prepared_payloads:
                    archive.write(payload_file, member)

        os.replace(temporary_pack, destination)
    except Exception:
        temporary_pack.unlink(missing_ok=True)
        raise

    sidecar = destination.with_suffix(destination.suffix + ".manifest.json")
    sidecar_tmp = sidecar.with_name(f".{sidecar.name}.{os.getpid()}.tmp")
    try:
        sidecar_tmp.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(sidecar_tmp, sidecar)
    except Exception:
        sidecar_tmp.unlink(missing_ok=True)
        raise

    manifest["pack_path"] = str(destination)
    manifest["manifest_path"] = str(sidecar)
    return manifest


def _load_pack(pack_path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    try:
        with zipfile.ZipFile(pack_path) as archive:
            listed_names = archive.namelist()
            if len(listed_names) != len(set(listed_names)):
                raise CompletionPackError("Completion pack contains duplicate members.")
            names = set(listed_names)
            if "manifest.json" not in names:
                raise CompletionPackError("Completion pack has no manifest.json.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            records = manifest.get("files")
            if (
                manifest.get("schema") != SCHEMA
                or not isinstance(records, list)
                or not records
            ):
                raise CompletionPackError("Unsupported completion-pack manifest.")

            expected_names = {"manifest.json"}
            payloads: dict[str, bytes] = {}
            seen_paths: set[str] = set()
            total_payload = 0
            for record in records:
                if not isinstance(record, dict):
                    raise CompletionPackError("Completion file record is not an object.")
                internal_path = normalize_path(record.get("path"))
                if not internal_path or internal_path in seen_paths:
                    raise CompletionPackError("Completion pack has an empty or duplicate path.")
                seen_paths.add(internal_path)

                member = str(record.get("payload_member") or "")
                if (
                    not member.startswith("payload/")
                    or member.endswith("/")
                    or member in expected_names
                ):
                    raise CompletionPackError("Unsafe or duplicate payload member name.")
                expected_names.add(member)
                info = archive.getinfo(member)
                declared_size = int(record.get("payload_size", -1))
                if (
                    declared_size <= 0
                    or declared_size != info.file_size
                    or declared_size > MAX_PACK_PAYLOAD
                ):
                    raise CompletionPackError(
                        f"Invalid payload size for {internal_path}."
                    )
                total_payload += declared_size
                if total_payload > MAX_PACK_PAYLOAD:
                    raise CompletionPackError("Combined completion payload exceeds safety cap.")

                payload = archive.read(member)
                if (
                    len(payload) != declared_size
                    or hashlib.sha256(payload).hexdigest()
                    != record.get("payload_sha256")
                ):
                    raise CompletionPackError(
                        f"Payload integrity failed for {internal_path}."
                    )

                ranges = record.get("ranges")
                if not isinstance(ranges, list) or not ranges:
                    raise CompletionPackError(
                        f"Completion contains no byte ranges for {internal_path}."
                    )
                expected_payload_offset = 0
                previous_end = 0
                entry_size = int(record.get("size", -1))
                for item in ranges:
                    if not isinstance(item, dict):
                        raise CompletionPackError(
                            f"Invalid byte range for {internal_path}."
                        )
                    offset = int(item.get("offset", -1))
                    length = int(item.get("length", -1))
                    payload_offset = int(item.get("payload_offset", -1))
                    if (
                        entry_size < 0
                        or offset < previous_end
                        or length <= 0
                        or offset + length > entry_size
                        or payload_offset != expected_payload_offset
                        or payload_offset + length > len(payload)
                    ):
                        raise CompletionPackError(
                            f"Unsafe byte range in completion for {internal_path}."
                        )
                    previous_end = offset + length
                    expected_payload_offset += length
                if expected_payload_offset != len(payload):
                    raise CompletionPackError(
                        f"Unreferenced payload bytes for {internal_path}."
                    )
                payloads[member] = payload

            if names != expected_names:
                raise CompletionPackError(
                    "Completion pack contains missing or unexpected members."
                )
            return manifest, payloads
    except CompletionPackError:
        raise
    except (
        OSError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise CompletionPackError(f"Could not read completion pack: {exc}") from exc


def apply_completion_pack(
    preview_iso: str | Path,
    pack_path: str | Path,
    output_iso: str | Path,
    *,
    overwrite: bool = False,
    iso_factory: Callable[[Path], Any] = Iso9660,
    progress: Progress | None = None,
) -> dict[str, Any]:
    source = Path(preview_iso).expanduser().resolve()
    pack = Path(pack_path).expanduser().resolve()
    output = Path(output_iso).expanduser().resolve()
    if not source.is_file() or not pack.is_file():
        raise CompletionPackError("Preview ISO and completion pack must exist.")
    if output in {source, pack}:
        raise CompletionPackError("Output must be separate from the preview and pack.")
    if output.exists() and not overwrite:
        raise CompletionPackError(f"Output already exists: {output}")

    manifest, payloads = _load_pack(pack)
    expected_image_size = int(manifest.get("source", {}).get("image_size", -1))
    if source.stat().st_size != expected_image_size:
        raise CompletionPackError(
            "Preview image-size mismatch; use the exact Fragmenter preview "
            "that produced this completion pack."
        )
    try:
        iso = iso_factory(source).open()
        index = iso.build_index()
    except (OSError, ValueError) as exc:
        raise CompletionPackError(f"Could not read preview ISO: {exc}") from exc
    if iso.sector_size != SECTOR_USER or iso.data_offset != 0:
        raise CompletionPackError(
            "The Fragmenter preview must be a standard 2048-byte-sector ISO."
        )

    prepared: list[tuple[IsoEntry, dict[str, Any], bytes]] = []
    with source.open("rb") as handle:
        for record in manifest["files"]:
            internal_path = normalize_path(record.get("path"))
            entry = index.get(internal_path)
            if entry is None:
                raise CompletionPackError(f"Preview ISO is missing {internal_path}.")
            if entry.size != int(record.get("size", -1)):
                raise CompletionPackError(f"Preview size mismatch for {internal_path}.")
            actual_hash = _entry_hash(handle, iso, entry)
            if actual_hash != record.get("source_sha256"):
                raise CompletionPackError(
                    f"Preview hash mismatch for {internal_path}; use the exact "
                    "Fragmenter preview that produced this completion pack."
                )
            payload = payloads[str(record["payload_member"])]
            previous_end = 0
            for item in record.get("ranges", []):
                offset = int(item.get("offset", -1))
                length = int(item.get("length", -1))
                payload_offset = int(item.get("payload_offset", -1))
                if (
                    offset < previous_end
                    or length <= 0
                    or offset + length > entry.size
                    or payload_offset < 0
                    or payload_offset + length > len(payload)
                ):
                    raise CompletionPackError(
                        f"Unsafe byte range in completion for {internal_path}."
                    )
                previous_end = offset + length
            prepared.append((entry, record, payload))

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(
        f".{output.name}.{os.getpid()}.fragmenter-v124.tmp"
    )
    try:
        shutil.copy2(source, temporary)
        with temporary.open("r+b") as handle:
            for entry, record, payload in prepared:
                for item in record["ranges"]:
                    offset = int(item["offset"])
                    length = int(item["length"])
                    payload_offset = int(item["payload_offset"])
                    write_extent_range(
                        handle,
                        iso,
                        entry,
                        offset,
                        payload[payload_offset : payload_offset + length],
                    )
                handle.flush()
                os.fsync(handle.fileno())
                target_hash = _entry_hash(handle, iso, entry)
                if target_hash != record.get("target_sha256"):
                    raise CompletionPackError(
                        f"4.0 verification failed for {entry.path}."
                    )
                _notify(progress, f"Verified 4.0 target: {entry.path}")
            write_iso_volume_label(handle, iso)
            _notify(progress, f"Verified ISO volume label: {FINAL_VOLUME_LABEL}")
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "status": "applied",
        "output": str(output),
        "image_size": output.stat().st_size,
        "verified_files": [entry.path for entry, _record, _payload in prepared],
        "reference_image_size_note": manifest["reference"]["image_size"],
        "volume_label": FINAL_VOLUME_LABEL,
        "layout_note": (
            "The completed ISO preserves Fragmenter's original layout and may be "
            "smaller than an ImgBurn-rebuilt 4.0 image while containing identical "
            "logical files."
        ),
    }


def _wizard() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError as exc:
        raise CompletionPackError("Tkinter is required for the guided wizard.") from exc

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showinfo(
            "Fragmenter V124 local 4.0 completion",
            "Choose the Fragmenter preview that displays 3.8, then your known "
            "Netslum 4.0 ISO.\n\nThe references remain read-only. Fragmenter "
            "will create a local completion pack and a separate completed ISO.",
            parent=root,
        )
        preview_text = filedialog.askopenfilename(
            parent=root,
            title="Choose Fragmenter English Preview (3.8)",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if not preview_text:
            return 1
        reference_text = filedialog.askopenfilename(
            parent=root,
            title="Choose known Netslum/Tellipatch 4.0 ISO",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if not reference_text:
            return 1
        preview = Path(preview_text)
        default_pack = preview.with_suffix(
            preview.suffix + ".netslum-4.0-completion.zip"
        )
        pack_text = filedialog.asksaveasfilename(
            parent=root,
            title="Save local 4.0 completion pack",
            initialdir=str(default_pack.parent),
            initialfile=default_pack.name,
            defaultextension=".zip",
            filetypes=(("Fragmenter completion pack", "*.zip"), ("All files", "*.*")),
        )
        if not pack_text:
            return 1
        default_output = preview.with_name(
            preview.stem + "-Netslum-4.0" + preview.suffix
        )
        output_text = filedialog.asksaveasfilename(
            parent=root,
            title="Save completed Netslum 4.0 ISO",
            initialdir=str(default_output.parent),
            initialfile=default_output.name,
            defaultextension=".iso",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if not output_text:
            return 1

        pack = Path(pack_text)
        output = Path(output_text)
        if pack.exists() and not messagebox.askyesno(
            "Replace completion pack?",
            f"The local completion pack already exists:\n\n{pack}\n\nReplace it?",
            parent=root,
        ):
            return 1
        if output.exists() and not messagebox.askyesno(
            "Replace output?",
            f"The completed output already exists:\n\n{output}\n\n"
            "Replace it only after a successful verified completion?",
            parent=root,
        ):
            return 1

        print("Building local completion pack...", flush=True)
        manifest = build_completion_pack(
            preview,
            reference_text,
            pack,
            progress=lambda message: print(message, flush=True),
        )
        print("Applying and verifying completion...", flush=True)
        result = apply_completion_pack(
            preview,
            pack,
            output,
            overwrite=output.exists(),
            progress=lambda message: print(message, flush=True),
        )
        messagebox.showinfo(
            "Local Netslum 4.0 completion ready",
            f"Completed and verified {len(result['verified_files'])} changed files.\n\n"
            f"ISO: {result['output']}\n\n"
            f"Metadata manifest: {manifest['manifest_path']}",
            parent=root,
        )
        return 0
    finally:
        root.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("wizard")

    build = sub.add_parser("build")
    build.add_argument("preview_iso", type=Path)
    build.add_argument("reference_iso", type=Path)
    build.add_argument("pack_path", type=Path)

    apply = sub.add_parser("apply")
    apply.add_argument("preview_iso", type=Path)
    apply.add_argument("pack_path", type=Path)
    apply.add_argument("output_iso", type=Path)
    apply.add_argument("--overwrite", action="store_true")

    args = parser.parse_args(argv)
    command = args.command or "wizard"
    try:
        if command == "wizard":
            return _wizard()
        if command == "build":
            report = build_completion_pack(
                args.preview_iso,
                args.reference_iso,
                args.pack_path,
                progress=lambda message: print(message, flush=True),
            )
            print(json.dumps(report["summary"], indent=2))
            print(f"Manifest: {report['manifest_path']}")
            return 0
        if command == "apply":
            report = apply_completion_pack(
                args.preview_iso,
                args.pack_path,
                args.output_iso,
                overwrite=args.overwrite,
                progress=lambda message: print(message, flush=True),
            )
            print(json.dumps(report, indent=2))
            return 0
    except (OSError, CompletionPackError) as exc:
        print(f"V124 completion failed: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

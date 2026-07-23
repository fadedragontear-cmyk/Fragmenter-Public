#!/usr/bin/env python3
"""Compare a Fragmenter English Preview with a known Tellipatch/Netslum 4.0 ISO.

The comparison is read-only and filesystem-aware. It compares ISO file paths and
logical file contents rather than raw image offsets, so an ImgBurn/rebuilt ISO
can be compared with Fragmenter's layout-preserving output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660, IsoEntry  # noqa: E402
from iso_patch_engine import COPY_CHUNK, read_extent_range  # noqa: E402


class CompareIsoError(RuntimeError):
    """Raised when either comparison input or report destination is unsafe."""


Progress = Callable[[int, int, str], None]


def _hash_entry(handle, iso: Any, entry: IsoEntry) -> str:
    digest = hashlib.sha256()
    position = 0
    while position < entry.size:
        take = min(COPY_CHUNK, entry.size - position)
        chunk = read_extent_range(handle, iso, entry, position, take)
        if len(chunk) != take:
            raise CompareIsoError(f"Short read while hashing {entry.path}.")
        digest.update(chunk)
        position += take
    return digest.hexdigest()


def _entry_record(entry: IsoEntry, digest: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": entry.path,
        "size": entry.size,
        "lba": entry.lba,
    }
    if digest is not None:
        record["sha256"] = digest
    return record


def compare_fragment_isos(
    preview_iso: str | Path,
    reference_iso: str | Path,
    *,
    iso_factory: Callable[[Path], Any] = Iso9660,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Return a content-level comparison without modifying either image."""

    preview_path = Path(preview_iso).expanduser().resolve()
    reference_path = Path(reference_iso).expanduser().resolve()
    if preview_path == reference_path:
        raise CompareIsoError("Choose two different ISO files.")
    if not preview_path.is_file():
        raise CompareIsoError(f"Fragmenter preview ISO was not found: {preview_path}")
    if not reference_path.is_file():
        raise CompareIsoError(f"4.0 reference ISO was not found: {reference_path}")

    try:
        preview = iso_factory(preview_path).open()
        reference = iso_factory(reference_path).open()
        preview_index = preview.build_index()
        reference_index = reference.build_index()
    except CompareIsoError:
        raise
    except (OSError, ValueError) as exc:
        raise CompareIsoError(f"Could not read an ISO filesystem: {exc}") from exc

    preview_paths = set(preview_index)
    reference_paths = set(reference_index)
    common_paths = sorted(preview_paths & reference_paths)
    only_preview_paths = sorted(preview_paths - reference_paths)
    only_reference_paths = sorted(reference_paths - preview_paths)

    changed: list[dict[str, Any]] = []
    unchanged_count = 0
    total = len(common_paths)

    with preview_path.open("rb") as preview_handle, reference_path.open("rb") as reference_handle:
        for number, internal_path in enumerate(common_paths, start=1):
            preview_entry = preview_index[internal_path]
            reference_entry = reference_index[internal_path]
            preview_hash = _hash_entry(preview_handle, preview, preview_entry)
            reference_hash = _hash_entry(reference_handle, reference, reference_entry)
            if (
                preview_entry.size == reference_entry.size
                and preview_hash == reference_hash
            ):
                unchanged_count += 1
            else:
                changed.append(
                    {
                        "path": internal_path,
                        "preview": _entry_record(preview_entry, preview_hash),
                        "reference_4_0": _entry_record(reference_entry, reference_hash),
                    }
                )
            if progress is not None and (
                number == total or number % 25 == 0 or (changed and changed[-1]["path"] == internal_path)
            ):
                progress(number, total, internal_path)

    only_preview = [
        _entry_record(preview_index[path])
        for path in only_preview_paths
    ]
    only_reference = [
        _entry_record(reference_index[path])
        for path in only_reference_paths
    ]

    report = {
        "schema": 1,
        "tool": "Fragmenter V123 ISO content comparison",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "preview": {
            "path": str(preview_path),
            "image_size": preview_path.stat().st_size,
            "sector_size": preview.sector_size,
            "data_offset": preview.data_offset,
            "lba_offset": preview.lba_offset,
            "filesystem_mode": preview.mode,
            "files": len(preview_index),
        },
        "reference_4_0": {
            "path": str(reference_path),
            "image_size": reference_path.stat().st_size,
            "sector_size": reference.sector_size,
            "data_offset": reference.data_offset,
            "lba_offset": reference.lba_offset,
            "filesystem_mode": reference.mode,
            "files": len(reference_index),
        },
        "summary": {
            "unchanged": unchanged_count,
            "changed": len(changed),
            "only_in_preview": len(only_preview),
            "only_in_reference_4_0": len(only_reference),
        },
        "changed": changed,
        "only_in_preview": only_preview,
        "only_in_reference_4_0": only_reference,
        "scope_note": (
            "This report contains paths, sizes, LBAs, and SHA-256 hashes only. "
            "It does not contain extracted game data or patch bytes."
        ),
    }
    return report


def save_report(report: dict[str, Any], destination: str | Path) -> Path:
    path = Path(destination).expanduser().resolve()
    preview = Path(str(report["preview"]["path"])).resolve()
    reference = Path(str(report["reference_4_0"]["path"])).resolve()
    if path in {preview, reference}:
        raise CompareIsoError("The report must not overwrite either ISO.")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def _choose_paths() -> tuple[Path, Path, Path] | None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError as exc:
        raise CompareIsoError(
            "Tkinter is unavailable. Supply preview_iso, reference_iso, and --report."
        ) from exc

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showinfo(
            "Fragmenter V123 comparison",
            "Choose Fragmenter's working English Preview first, then your known 4.0 ISO.\n\n"
            "Both images are read-only. The report contains metadata and hashes only.",
            parent=root,
        )
        preview = filedialog.askopenfilename(
            parent=root,
            title="Choose Fragmenter English Preview (shows 3.8)",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if not preview:
            return None
        reference = filedialog.askopenfilename(
            parent=root,
            title="Choose known Tellipatch/Netslum 4.0 ISO",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if not reference:
            return None
        default_report = Path(preview).with_suffix(
            Path(preview).suffix + ".vs-netslum-4.0.json"
        )
        report = filedialog.asksaveasfilename(
            parent=root,
            title="Save Fragmenter comparison report",
            initialdir=str(default_report.parent),
            initialfile=default_report.name,
            defaultextension=".json",
            filetypes=(("JSON report", "*.json"), ("All files", "*.*")),
        )
        if not report:
            return None
        return Path(preview), Path(reference), Path(report)
    finally:
        root.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preview_iso", nargs="?", type=Path)
    parser.add_argument("reference_iso", nargs="?", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.preview_iso is None and args.reference_iso is None:
            selected = _choose_paths()
            if selected is None:
                print("Comparison cancelled.")
                return 1
            preview, reference, destination = selected
        elif args.preview_iso is None or args.reference_iso is None:
            parser.error("Supply both ISO paths, or neither to use file choosers.")
        else:
            preview = args.preview_iso
            reference = args.reference_iso
            destination = args.report or preview.with_suffix(
                preview.suffix + ".vs-netslum-4.0.json"
            )

        def show_progress(current: int, total: int, path: str) -> None:
            print(f"[{current:,}/{total:,}] {path}", flush=True)

        print("Comparing logical ISO files. This may take several minutes...", flush=True)
        report = compare_fragment_isos(
            preview,
            reference,
            progress=show_progress,
        )
        saved = save_report(report, destination)
        summary = report["summary"]
        print(
            "\nComparison complete. "
            f"Changed={summary['changed']}, "
            f"only-preview={summary['only_in_preview']}, "
            f"only-4.0={summary['only_in_reference_4_0']}.\n"
            f"Report: {saved}"
        )
    except (OSError, CompareIsoError) as exc:
        print(f"Comparison failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

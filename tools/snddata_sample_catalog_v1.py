#!/usr/bin/env python3
"""Finalize corrected SNDDATA samples into by-bank and flat comparison catalogs."""
from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path
from typing import Any


def _replace_path_parent(path_text: str, old_parent: Path, new_parent: Path) -> str:
    path = Path(str(path_text or ""))
    if not path_text:
        return ""
    try:
        relative = path.relative_to(old_parent)
    except ValueError:
        relative = Path(path.name)
    return str(new_parent / relative)


def _move_bank_directories(report: dict[str, Any], output_root: Path) -> None:
    by_bank = output_root / "by_bank"
    by_bank.mkdir(parents=True, exist_ok=True)
    moved: dict[str, Path] = {}
    for bank in report.get("banks") or []:
        if not isinstance(bank, dict) or not bank.get("samples"):
            continue
        sample = next((row for row in bank.get("samples") or [] if isinstance(row, dict) and row.get("metadata_path")), None)
        if not sample:
            continue
        old_parent = Path(str(sample["metadata_path"])).parent
        if old_parent.parent == by_bank:
            new_parent = old_parent
        else:
            key = str(old_parent)
            new_parent = moved.get(key) or (by_bank / old_parent.name)
            if key not in moved:
                if new_parent.exists():
                    shutil.rmtree(new_parent)
                if old_parent.exists():
                    old_parent.replace(new_parent)
                moved[key] = new_parent
        bank["output_dir"] = str(new_parent)
        for row in bank.get("samples") or []:
            if not isinstance(row, dict):
                continue
            for field in ("raw_path", "output_path", "metadata_path"):
                row[field] = _replace_path_parent(str(row.get(field) or ""), old_parent, new_parent)


def _link_or_copy(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def _span_key(row: dict[str, Any]) -> tuple[int, int]:
    start = int(row.get("source_offset") or 0)
    return start, start + int(row.get("raw_size") or 0)


def finalize_sample_catalog(
    report: dict[str, Any],
    output_root: str | Path,
    *,
    reports_root: str | Path | None = None,
) -> dict[str, Any]:
    """Assign stable flat indices to unique source spans and create comparison aliases."""
    output = Path(output_root)
    _move_bank_directories(report, output)
    rows = [row for row in report.get("samples") or [] if isinstance(row, dict)]
    rows.sort(key=lambda row: (_span_key(row), int(row.get("resource_offset") or 0), int(row.get("index") or 0)))
    bounded_rows = [
        row
        for row in rows
        if row.get("source_offset") is not None and int(row.get("raw_size") or 0) > 0
    ]

    unique: dict[tuple[int, int], dict[str, Any]] = {}
    aliases: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in bounded_rows:
        key = _span_key(row)
        unique.setdefault(key, row)
        aliases.setdefault(key, []).append(row)

    ordered = sorted(unique.items(), key=lambda item: item[0])
    flat_root = output / "flat"
    if flat_root.exists():
        shutil.rmtree(flat_root)
    flat_root.mkdir(parents=True, exist_ok=True)
    flat_rows: list[dict[str, Any]] = []
    link_modes: dict[str, int] = {}

    for flat_index, (span, canonical) in enumerate(ordered):
        bank = int(canonical.get("bank_ordinal") or 0)
        local = int(canonical.get("index") or 0)
        rate = int(canonical.get("sample_rate") or 0)
        stem = f"sample_{flat_index:04d}__bank_{bank:04d}_local_{local:04d}_{rate}hz"
        source_wav = Path(str(canonical.get("output_path") or ""))
        flat_wav = flat_root / f"{stem}.wav"
        link_mode = "missing"
        if source_wav.is_file() and not canonical.get("errors"):
            link_mode = _link_or_copy(source_wav, flat_wav)
            link_modes[link_mode] = link_modes.get(link_mode, 0) + 1
        alias_rows = aliases[span]
        for row in alias_rows:
            row["flat_index"] = flat_index
            row["flat_display_name"] = f"flat sample {flat_index:04d}"
            row["flat_output_path"] = str(flat_wav) if flat_wav.is_file() else ""
            row["source_span_start"] = span[0]
            row["source_span_end"] = span[1]
            row["source_span_alias_count"] = len(alias_rows)
        flat_row = {
            "flat_index": flat_index,
            "display_name": f"flat sample {flat_index:04d}",
            "source_span_start": span[0],
            "source_span_end": span[1],
            "source_span_size": span[1] - span[0],
            "bank_ordinal": bank,
            "resource_offset": int(canonical.get("resource_offset") or 0),
            "local_sample_index": local,
            "sample_rate": rate,
            "duration_estimate": canonical.get("duration_estimate"),
            "decode_status": canonical.get("decode_status"),
            "wav_path": str(flat_wav) if flat_wav.is_file() else "",
            "link_mode": link_mode,
            "aliases": [
                {
                    "bank_ordinal": int(row.get("bank_ordinal") or 0),
                    "resource_offset": int(row.get("resource_offset") or 0),
                    "local_sample_index": int(row.get("index") or 0),
                }
                for row in alias_rows
            ],
        }
        flat_rows.append(flat_row)

    for row in rows:
        metadata = Path(str(row.get("metadata_path") or ""))
        if metadata.parent.is_dir() and metadata.name:
            metadata.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    readme = output / "README.txt"
    readme.write_text(
        "Fragmenter corrected SNDDATA sample library\n"
        "\n"
        "by_bank/ keeps authoritative SCEIVagi bank-local identities used by game research.\n"
        "flat/ assigns one sequential comparison number to each unique source byte span.\n"
        "The flat number is intended for comparison with tools such as PSound; it is not\n"
        "claimed to be PSound's exact scan order until the counts and waveforms are audited.\n"
        "Flat WAVs are hard links when supported and copies otherwise.\n",
        encoding="utf-8",
    )

    summary = report.setdefault("summary", {})
    summary["bank_local_rows"] = len(rows)
    summary["flat_bounded_rows"] = len(bounded_rows)
    summary["flat_unbounded_rows"] = len(rows) - len(bounded_rows)
    summary["flat_unique_source_spans"] = len(flat_rows)
    summary["duplicate_stream_aliases"] = len(bounded_rows) - len(flat_rows)
    summary["flat_playable_wavs"] = sum(bool(row.get("wav_path")) for row in flat_rows)
    report["layout"] = {
        "version": 2,
        "root": str(output),
        "by_bank": str(output / "by_bank"),
        "flat": str(flat_root),
        "readme": str(readme),
        "flat_index_semantics": "unique corrected source byte span in ascending source order",
        "psound_mapping_status": "comparison index only; exact PSound numbering remains unconfirmed",
        "link_modes": link_modes,
    }
    report["flat_catalog"] = flat_rows

    reports = Path(reports_root) if reports_root is not None else None
    if reports is not None:
        reports.mkdir(parents=True, exist_ok=True)
        json_path = reports / "snddata_sample_flat_catalog.json"
        csv_path = reports / "snddata_sample_flat_catalog.csv"
        json_path.write_text(json.dumps({"summary": summary, "samples": flat_rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            fields = (
                "flat_index",
                "resource_offset",
                "bank_ordinal",
                "local_sample_index",
                "sample_rate",
                "duration_estimate",
                "source_span_start",
                "source_span_end",
                "source_span_size",
                "decode_status",
                "wav_path",
                "link_mode",
            )
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in flat_rows:
                writer.writerow({field: row.get(field) for field in fields})
        report["flat_catalog_report"] = str(json_path)
        report["flat_catalog_csv"] = str(csv_path)
    return report


if __name__ == "__main__":
    raise SystemExit("Used by snddata_sample_library_v3.")

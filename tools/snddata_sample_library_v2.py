#!/usr/bin/env python3
"""Friendly naming layer for the authoritative SNDDATA sample extractor."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable

import snddata_sample_library_v1 as v1
from project_workspace_v1 import FragmenterProjectV1

REPORT_NAME = "snddata_sample_library_v2.json"
CSV_NAME = "snddata_sample_library_v2.csv"


def project_paths(project: FragmenterProjectV1) -> tuple[Path, Path, Path, Path]:
    workspace = Path(project.workspace_dir).expanduser()
    source = workspace / "sound" / "source" / "data" / "snddata.bin"
    output = workspace / "sound" / "decoded" / "snddata" / "samples"
    reports = workspace / "sound" / "reports"
    return source, output, reports / REPORT_NAME, reports / CSV_NAME


def _friendly_layout(report: dict[str, Any], output_root: Path) -> dict[str, Any]:
    bank_ordinals = {
        int(bank.get("resource_offset") or 0): int(bank.get("ordinal") or index)
        for index, bank in enumerate(report.get("banks") or [], 1)
        if isinstance(bank, dict)
    }
    samples = [row for row in report.get("samples") or [] if isinstance(row, dict)]
    for row in samples:
        resource_offset = int(row.get("resource_offset") or 0)
        bank_ordinal = bank_ordinals.get(resource_offset, 0)
        sample_index = int(row.get("index") or 0)
        sample_rate = int(row.get("sample_rate") or 0)
        bank_dir = output_root / f"bank_{bank_ordinal:04d}_offset_{resource_offset:08X}"
        bank_dir.mkdir(parents=True, exist_ok=True)
        stem = f"bank_{bank_ordinal:04d}_sample_{sample_index:04d}_{sample_rate}hz"
        for key, suffix in (("raw_path", ".psadpcm"), ("output_path", ".wav"), ("metadata_path", ".json")):
            old_text = str(row.get(key) or "")
            if not old_text:
                continue
            old_path = Path(old_text)
            new_path = bank_dir / f"{stem}{suffix}"
            if old_path.is_file() and old_path.resolve() != new_path.resolve():
                if new_path.exists():
                    new_path.unlink()
                old_path.replace(new_path)
            row[key] = str(new_path)
        row["bank_ordinal"] = bank_ordinal
        row["display_name"] = f"SNDDATA bank {bank_ordinal:04d} · sample {sample_index:04d} · {sample_rate:,} Hz"
        metadata_text = str(row.get("metadata_path") or "").strip()
        if metadata_text:
            Path(metadata_text).write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for bank in report.get("banks") or []:
        if not isinstance(bank, dict):
            continue
        resource_offset = int(bank.get("resource_offset") or 0)
        bank_ordinal = int(bank.get("ordinal") or bank_ordinals.get(resource_offset, 0))
        bank["friendly_name"] = f"SNDDATA bank {bank_ordinal:04d} @ 0x{resource_offset:08X}"
        bank["output_dir"] = str(output_root / f"bank_{bank_ordinal:04d}_offset_{resource_offset:08X}")

    for folder in output_root.glob("resource_*"):
        if folder.is_dir():
            try:
                folder.rmdir()
            except OSError:
                pass
    report["version"] = 2
    report["naming"] = {
        "bank_directories": "bank_NNNN_offset_XXXXXXXX",
        "sample_files": "bank_NNNN_sample_NNNN_RATEhz",
        "classification": "names are identifiers only; musical/effect roles remain unclassified",
    }
    return report


def _write_reports(report: dict[str, Any], report_path: Path, csv_path: Path) -> None:
    report["report_path"] = str(report_path)
    report["csv_path"] = str(csv_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = (
        "bank_ordinal",
        "resource_offset",
        "index",
        "display_name",
        "sample_rate",
        "stream_offset",
        "raw_size",
        "payload_size",
        "duration_estimate",
        "decode_status",
        "output_path",
        "raw_path",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("samples") or []:
            if isinstance(row, dict):
                writer.writerow({key: row.get(key) for key in fields})


def extract_snddata_file(
    source: str | Path,
    output_root: str | Path,
    *,
    report_path: str | Path | None = None,
    csv_path: str | Path | None = None,
    clean: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    output = Path(output_root).expanduser()
    target_report = Path(report_path).expanduser() if report_path is not None else output.parent / REPORT_NAME
    target_csv = Path(csv_path).expanduser() if csv_path is not None else output.parent / CSV_NAME
    report = v1.extract_snddata_file(source, output, clean=clean, callback=callback)
    report = _friendly_layout(report, output)
    _write_reports(report, target_report, target_csv)
    return report


def extract_project_snddata_samples(
    project: FragmenterProjectV1,
    *,
    clean: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source, output, report, csv_report = project_paths(project)
    return extract_snddata_file(
        source,
        output,
        report_path=report,
        csv_path=csv_report,
        clean=clean,
        callback=callback,
    )

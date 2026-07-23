#!/usr/bin/env python3
"""Summarize current SNDDATA sample extraction health for the public audio UI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_sound_v1 import sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_sample_library_v3 import REPORT_NAME


def sample_library_health(project: FragmenterProjectV1) -> dict[str, Any]:
    report_path = sound_reports_root(project) / REPORT_NAME
    if not report_path.is_file():
        return {
            "status": "missing",
            "report_path": str(report_path),
            "rebuild_required": True,
            "warnings": ["Run Extract SNDDATA Samples to build the current catalog."],
        }
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid",
            "report_path": str(report_path),
            "rebuild_required": True,
            "warnings": [f"Sample report could not be read: {exc}"],
        }
    summary = report.get("summary") or {}
    layout = report.get("layout") or {}
    policy = report.get("sample_boundary_policy") or {}
    corrected_banks = [
        bank
        for bank in report.get("banks") or []
        if isinstance(bank, dict) and bool((bank.get("stream_boundary_model") or {}).get("applied"))
    ]
    progressive_banks = [
        bank
        for bank in corrected_banks
        if str((bank.get("stream_boundary_model") or {}).get("mode") or "")
        == "progressive_separator_drift"
    ]
    by_bank = Path(
        str(
            layout.get("by_bank")
            or sound_decoded_root(project) / "snddata" / "samples" / "by_bank"
        )
    )
    flat = Path(
        str(
            layout.get("flat")
            or sound_decoded_root(project) / "snddata" / "samples" / "flat"
        )
    )
    warnings: list[str] = []
    if int(policy.get("version") or 0) < 3:
        warnings.append(
            "The report predates per-entry progressive boundary correction; rebuild the sample library."
        )
    if not by_bank.is_dir():
        warnings.append("Corrected by-bank directory is missing.")
    if not flat.is_dir():
        warnings.append("Flat PSound-comparison directory is missing.")
    return {
        "status": "ready" if not warnings else "attention",
        "rebuild_required": bool(warnings),
        "report_path": str(report_path),
        "source_sha256": report.get("source_sha256"),
        "summary": summary,
        "boundary_policy": policy,
        "entry_corrected_banks": len(corrected_banks),
        "progressive_drift_banks": len(progressive_banks),
        "entry_corrected_samples": int(summary.get("entry_corrected_samples") or 0),
        "boundary_models": [
            {
                "resource_offset": bank.get("resource_offset"),
                "bank_ordinal": bank.get("ordinal"),
                **(bank.get("stream_boundary_model") or {}),
            }
            for bank in corrected_banks
        ],
        "paths": {
            "root": str(layout.get("root") or by_bank.parent),
            "by_bank": str(by_bank),
            "flat": str(flat),
            "flat_catalog_report": report.get("flat_catalog_report"),
            "flat_catalog_csv": report.get("flat_catalog_csv"),
        },
        "psound_comparison": {
            "reported_external_count": 974,
            "fragmenter_flat_unique_source_spans": int(
                summary.get("flat_unique_source_spans") or 0
            ),
            "difference": int(summary.get("flat_unique_source_spans") or 0) - 974,
            "status": (
                "comparison target supplied by user; exact numbering remains unconfirmed"
            ),
        },
        "warnings": warnings,
    }


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's audio UI.")

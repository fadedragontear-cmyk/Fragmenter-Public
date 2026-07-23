#!/usr/bin/env python3
"""Re-extract a Fragmenter project's SNDDATA library with corrected body and trim policies."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from compare_psound_to_latest_fragmenter_v1 import CORRECTED_TRIM_POLICY
from project_workspace_v1 import load_project
from snddata_sample_library_v3 import extract_project_snddata_samples

_ALLOWED_BODY_METHODS = {
    "unique_clean_bank_shift",
    "current_body_base_not_nested_sequence",
}


def summarize_trim_policy(report: dict[str, Any]) -> dict[str, int]:
    rows = [row for row in report.get("samples") or [] if isinstance(row, dict)]
    trim_rows = 0
    corrected_rows = 0
    separator_rows = 0
    internal_separator_blocks = 0
    ignored_flag_07_blocks = 0
    legacy_flag_07_rows = 0
    for row in rows:
        trim = row.get("trim")
        if not isinstance(trim, dict):
            continue
        trim_rows += 1
        if trim.get("policy") == CORRECTED_TRIM_POLICY:
            corrected_rows += 1
        if trim.get("terminator_kind") in {"007777_separator", "trailing_007777_separator"}:
            separator_rows += 1
        if trim.get("terminator_kind") == "adpcm_flag_07":
            legacy_flag_07_rows += 1
        try:
            internal_separator_blocks += int(trim.get("internal_007777_separator_count") or 0)
        except (TypeError, ValueError):
            pass
        try:
            ignored_flag_07_blocks += int(trim.get("ignored_adpcm_flag_07_count") or 0)
        except (TypeError, ValueError):
            pass
    return {
        "sample_rows": len(rows),
        "trim_rows": trim_rows,
        "corrected_trim_rows": corrected_rows,
        "separator_rows": separator_rows,
        "internal_separator_blocks": internal_separator_blocks,
        "ignored_flag_07_blocks": ignored_flag_07_blocks,
        "legacy_flag_07_rows": legacy_flag_07_rows,
    }


def summarize_body_resolution(report: dict[str, Any]) -> dict[str, int]:
    sample_banks = [
        bank
        for bank in report.get("banks") or []
        if isinstance(bank, dict) and int(bank.get("resource_type") or 0) == 2
    ]
    validated = 0
    shifted = 0
    unshifted = 0
    unresolved = 0

    for bank in sample_banks:
        candidates = [
            candidate
            for candidate in bank.get("body_candidates") or []
            if isinstance(candidate, dict)
        ]
        selected = candidates[0] if candidates else {}
        method = str(
            bank.get("body_resolution_method")
            or selected.get("resolution_method")
            or "unresolved"
        )
        resolution = bank.get("body_resolution") or selected.get("body_resolution")
        shift = int(bank.get("body_shift") or selected.get("body_shift") or 0)
        method_valid = method in _ALLOWED_BODY_METHODS
        evidence_valid = True
        if method == "unique_clean_bank_shift":
            evidence_valid = (
                isinstance(resolution, dict)
                and resolution.get("status") == "unique_clean_bank_shift"
                and int(resolution.get("fully_clean_candidate_count") or 0) == 1
                and int(resolution.get("selected_invalid_blocks") or 0) == 0
            )
        elif method == "current_body_base_not_nested_sequence":
            evidence_valid = (
                isinstance(resolution, dict)
                and resolution.get("status") == "current_body_base_not_nested_sequence"
                and shift == 0
            )

        if method_valid and evidence_valid:
            validated += 1
            shifted += int(method == "unique_clean_bank_shift" and shift > 0)
            unshifted += int(method == "current_body_base_not_nested_sequence")
        else:
            unresolved += 1

    return {
        "sample_program_banks": len(sample_banks),
        "validated_body_banks": validated,
        "shifted_body_banks": shifted,
        "unshifted_body_banks": unshifted,
        "unresolved_body_banks": unresolved,
    }


def validate_corrected_report(report: dict[str, Any]) -> dict[str, int]:
    summary = summarize_trim_policy(report)
    if summary["sample_rows"] <= 0:
        raise RuntimeError("Corrected SNDDATA extraction produced no sample rows.")
    if summary["trim_rows"] <= 0:
        raise RuntimeError("Corrected SNDDATA extraction produced no trim metadata rows.")
    if summary["corrected_trim_rows"] != summary["trim_rows"]:
        raise RuntimeError(
            f"SNDDATA extraction was not fully generated with trim policy {CORRECTED_TRIM_POLICY!r}: "
            f"{summary['corrected_trim_rows']}/{summary['trim_rows']} corrected rows."
        )
    if summary["legacy_flag_07_rows"]:
        raise RuntimeError(
            "Corrected SNDDATA extraction still reported legacy adpcm_flag_07 terminators: "
            f"{summary['legacy_flag_07_rows']}"
        )

    body = summarize_body_resolution(report)
    if body["sample_program_banks"]:
        if body["unresolved_body_banks"]:
            raise RuntimeError(
                "SNDDATA extraction contains unresolved body bases: "
                f"{body['unresolved_body_banks']}"
            )
        if body["validated_body_banks"] != body["sample_program_banks"]:
            raise RuntimeError(
                "SNDDATA body-base validation was incomplete: "
                f"{body['validated_body_banks']}/{body['sample_program_banks']} banks."
            )
    return {**summary, **body}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Fragmenter project folder or project.json path")
    parser.add_argument(
        "--keep-existing-output",
        action="store_true",
        help="Do not clean the decoded SNDDATA sample folder before extraction.",
    )
    args = parser.parse_args(argv)

    project_path = Path(args.project).expanduser().resolve()
    project = load_project(project_path)
    report = extract_project_snddata_samples(
        project,
        clean=not args.keep_existing_output,
    )
    summary = validate_corrected_report(report)

    report_path = Path(str(report.get("report_path") or "")).expanduser()
    extraction_summary = dict(report.get("summary") or {})
    print("Corrected SNDDATA extraction complete.")
    print(f"Project: {project.project_path}")
    print(f"Report: {report_path}")
    print(f"Sample rows: {summary['sample_rows']}")
    print(
        "Validated body bases: "
        f"{summary['validated_body_banks']}/{summary['sample_program_banks']}"
    )
    print(f"Shifted detached-body banks: {summary['shifted_body_banks']}")
    print(f"Unshifted inline-body banks: {summary['unshifted_body_banks']}")
    print(f"Corrected trim rows: {summary['corrected_trim_rows']}/{summary['trim_rows']}")
    print(f"Trailing separator rows: {summary['separator_rows']}")
    print(f"Retained internal exact separators: {summary['internal_separator_blocks']}")
    print(f"Retained legal 0x07 blocks: {summary['ignored_flag_07_blocks']}")
    print(f"Legacy flag-07 terminators: {summary['legacy_flag_07_rows']}")
    print(f"Decoded WAVs: {extraction_summary.get('decoded_wavs')}")
    print(f"Failed samples: {extraction_summary.get('failed_samples')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

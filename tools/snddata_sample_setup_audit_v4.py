#!/usr/bin/env python3
"""Finalize SNDDATA setup validation with explicit input provenance.

Version 4 keeps the version-3 structural and body-base checks, but removes
resolved investigation notes after a fully successful extraction. It also
records that nearby PSound exports, executables, and configuration files are
not inputs to this setup audit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import snddata_sample_setup_audit_v3 as v3
from compare_psound_to_latest_fragmenter_v1 import find_latest_fragmenter_report

REPORT_NAME = v3.REPORT_NAME
CSV_NAME = v3.CSV_NAME

UNRESOLVED_FIRST_ENTRY = (
    "The exact role and internal framing of the unresolved first-entry payloads "
    "in later banks."
)
UNRESOLVED_BODY_SHIFT = (
    "The consistent per-bank shift from the selected sequence-resource start "
    "to the actual sample ADPCM secondary body."
)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def finalize_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Make the human-readable decision match the computed audit gates."""
    summary = dict(payload.get("summary") or {})
    body_base_pass = payload.get("body_base_gate") == "pass"
    classification_gate = str(payload.get("classification_gate") or "fail")
    unresolved_rows = _int(summary.get("unresolved_entry_rows"))

    policy = dict(payload.get("classification_policy") or {})
    if body_base_pass and classification_gate == "pass":
        policy["current_decision"] = (
            "Classification permitted: all selected bank body bases begin at "
            "validated non-resource ADPCM data, and all catalog rows are clean "
            "audio candidates."
        )
    elif body_base_pass:
        policy["current_decision"] = (
            "Bank body bases are validated, but classification remains limited "
            "by other unresolved catalog rows."
        )
    else:
        policy["current_decision"] = (
            "Classification blocked for banks whose selected body base is a "
            "nested SCEI sequence resource."
        )
    payload["classification_policy"] = policy

    remaining: list[str] = []
    for value in payload.get("remaining_unknowns") or []:
        text = str(value)
        if body_base_pass and text == UNRESOLVED_BODY_SHIFT:
            continue
        if unresolved_rows == 0 and text == UNRESOLVED_FIRST_ENTRY:
            continue
        if text not in remaining:
            remaining.append(text)
    payload["remaining_unknowns"] = remaining

    payload["version"] = 4
    payload["input_scope"] = {
        "report_discovery": (
            "Searches only for canonical Fragmenter SNDDATA report filenames and "
            "requires the corrected trim policy."
        ),
        "authoritative_source": (
            "Reads the snddata.bin path recorded by the selected Fragmenter report "
            "and verifies its SHA-256 before validating spans."
        ),
        "external_psound_files": (
            "Nearby PSound WAV exports, PSound executables, and PSound.cfg are not "
            "read or used by this setup audit. They are inputs only to separate "
            "PSound comparison tools."
        ),
    }
    return payload


def audit_report(report_path: Path) -> dict[str, Any]:
    return finalize_report(v3.audit_report(report_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("search_root", nargs="?", default=str(Path.cwd().parent))
    parser.add_argument("--fragmenter-report")
    parser.add_argument(
        "--output",
        default=str(Path.cwd() / "diagnostics" / "snddata_sample_setup"),
    )
    args = parser.parse_args(argv)

    report_path = (
        Path(args.fragmenter_report).expanduser().resolve()
        if args.fragmenter_report
        else find_latest_fragmenter_report(args.search_root, require_corrected_trim=True)
    )
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_NAME
    csv_path = output / CSV_NAME

    payload = audit_report(report_path)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    v3.v2._write_csv(csv_path, payload["rows"])

    summary = payload["summary"]
    print(f"Fragmenter report: {report_path}")
    print(f"Source SHA-256 matches report: {payload.get('source_sha256_matches')}")
    print(f"Metadata/span gate: {payload['metadata_span_gate']}")
    print(f"Span-size gate: {payload['span_size_gate']}")
    print(f"Body-base gate: {payload['body_base_gate']}")
    print(f"Structural gate: {payload['structural_gate']}")
    print(f"Classification gate: {payload['classification_gate']}")
    print(
        "Body-base signatures: "
        f"{summary.get('body_base_signature_counts')}"
    )
    print(
        "Blocked banks/rows: "
        f"{summary.get('body_base_failure_banks')}/"
        f"{summary.get('body_base_blocked_rows')}"
    )
    print("PSound files used by this audit: none")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0 if payload["classification_gate"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())

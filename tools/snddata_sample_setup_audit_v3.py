#!/usr/bin/env python3
"""Validate SNDDATA setup while rejecting body bases that point at SCEI resources.

Version 2 correctly recognized that a HEAD secondary body may be detached from
its sample-program metadata resource. The unresolved-suffix probe then exposed
a stronger condition: every later selected body base begins with a complete
SCEI sequence-resource header (SCEIVers/SCEISequ/SCEIMidi), not sample ADPCM.

This audit preserves the proven SCEIVagi span-length checks, but blocks
classification until a consistent per-bank body-base shift is established.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

import snddata_sample_setup_audit_v2 as v2
from compare_psound_to_latest_fragmenter_v1 import find_latest_fragmenter_report

REPORT_NAME = v2.REPORT_NAME
CSV_NAME = v2.CSV_NAME

VERS_TAGS = (b"IECSsreV", b"SCEIVers")
SEQU_TAGS = (b"IECSuqeS", b"SCEISequ")
MIDI_TAGS = (b"IECSidiM", b"SCEIMidi")
SEQUENCE_TYPE = 1
BODY_BASE_ISSUE = (
    "selected HEAD secondary body base points at an SCEI sequence resource "
    "instead of sample ADPCM"
)


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def classify_body_base_signature(source: bytes, offset: int | None) -> dict[str, Any]:
    if offset is None or offset < 0 or offset + 16 > len(source):
        return {
            "status": "outside_source",
            "resource_type": None,
            "prefix_ascii": None,
        }

    prefix = source[offset : offset + 64]
    resource_type = struct.unpack_from("<H", source, offset + 14)[0]
    has_vers = prefix[:8] in VERS_TAGS
    has_sequ = len(prefix) >= 24 and prefix[16:24] in SEQU_TAGS
    has_midi = len(prefix) >= 56 and prefix[48:56] in MIDI_TAGS

    if has_vers and resource_type == SEQUENCE_TYPE and has_sequ and has_midi:
        status = "scei_sequence_resource_header"
    elif has_vers and resource_type == SEQUENCE_TYPE:
        status = "scei_sequence_resource_like"
    elif has_vers:
        status = "scei_resource_header_other"
    else:
        status = "not_scei_resource_header"

    return {
        "status": status,
        "resource_type": resource_type if has_vers else None,
        "has_scei_vers": has_vers,
        "has_scei_sequ": has_sequ,
        "has_scei_midi": has_midi,
        "prefix_ascii": "".join(
            chr(value) if 32 <= value < 127 else "." for value in prefix[:64]
        ),
        "prefix_hex": prefix[:64].hex(" "),
    }


def audit_report(report_path: Path) -> dict[str, Any]:
    payload = v2.audit_report(report_path)
    source_path = Path(str(payload["snddata_source"])).expanduser().resolve()
    source = source_path.read_bytes()

    bad_bank_ordinals: set[int] = set()
    signature_counts: dict[str, int] = {}

    for bank in payload.get("banks") or []:
        ordinal = _int(bank.get("bank_ordinal"))
        signature = classify_body_base_signature(source, _int(bank.get("body_base")))
        bank["body_base_signature"] = signature
        signature_status = str(signature["status"])
        signature_counts[signature_status] = signature_counts.get(signature_status, 0) + 1

        if signature_status in {
            "scei_sequence_resource_header",
            "scei_sequence_resource_like",
        }:
            issues = list(bank.get("issues") or [])
            if BODY_BASE_ISSUE not in issues:
                issues.append(BODY_BASE_ISSUE)
            bank["issues"] = issues
            bank["status"] = "fail_body_base"
            if ordinal is not None:
                bad_bank_ordinals.add(ordinal)

    blocked_rows = 0
    for row in payload.get("rows") or []:
        ordinal = _int(row.get("bank_ordinal"))
        if ordinal in bad_bank_ordinals:
            row["provisional_v2_status"] = row.get("status")
            row["provisional_v2_catalog_role"] = row.get("catalog_role")
            row["status"] = "blocked_body_base_unresolved"
            row["catalog_role"] = "blocked_body_base_unresolved"
            row["bank_body_base_status"] = "scei_sequence_resource_header"
            blocked_rows += 1
        else:
            row["bank_body_base_status"] = "validated_non_resource_start"

    metadata_span_gate = str(payload.get("structural_gate") or "fail")
    body_base_gate = "pass" if not bad_bank_ordinals else "fail"
    structural_gate = (
        "pass"
        if metadata_span_gate == "pass" and body_base_gate == "pass"
        else "fail_body_base"
        if metadata_span_gate == "pass"
        else "fail"
    )

    summary = dict(payload.get("summary") or {})
    summary.update(
        {
            "metadata_span_gate": metadata_span_gate,
            "body_base_gate": body_base_gate,
            "body_base_signature_counts": signature_counts,
            "body_base_failure_banks": len(bad_bank_ordinals),
            "body_base_blocked_rows": blocked_rows,
            "body_base_failure_bank_ordinals": sorted(bad_bank_ordinals),
        }
    )

    payload["version"] = 3
    payload["metadata_span_gate"] = metadata_span_gate
    payload["span_size_gate"] = (
        "pass_offsets_only" if metadata_span_gate == "pass" else "fail"
    )
    payload["body_base_gate"] = body_base_gate
    payload["structural_gate"] = structural_gate
    payload["size_gate"] = (
        "provisional_offsets_only" if body_base_gate == "fail" else payload.get("size_gate")
    )
    payload["classification_gate"] = "fail" if body_base_gate == "fail" else payload.get(
        "classification_gate"
    )
    payload["summary"] = summary
    payload["classification_policy"] = {
        **dict(payload.get("classification_policy") or {}),
        "body_base_requirement": (
            "A selected bank body base must not begin with another SCEI resource. "
            "All entries in a bank must validate under one consistent shifted base."
        ),
        "current_decision": (
            "Classification blocked for banks whose selected body base is a nested "
            "SCEI sequence resource."
        ),
    }
    payload["remaining_unknowns"] = [
        *list(payload.get("remaining_unknowns") or []),
        (
            "The consistent per-bank shift from the selected sequence-resource start "
            "to the actual sample ADPCM secondary body."
        ),
    ]
    return payload


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
    v2._write_csv(csv_path, payload["rows"])

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
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0 if payload["classification_gate"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())

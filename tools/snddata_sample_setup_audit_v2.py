#!/usr/bin/env python3
"""Validate SNDDATA sample sizes and separate clean audio from wrapped entries.

Version 2 corrects a false assumption in the first audit: Fragment sample-program
metadata and its HEAD secondary body do not have to occupy the same SCEIVers
resource span. A secondary body beginning at the metadata resource end is a
supported detached layout, not a bank failure.

The audit remains independent of PSound ordering. It validates SCEIVagi span
sizes, source bytes, v3 edge trimming, sample rates, and current decode results.
Rows containing non-ADPCM blocks remain in the catalog but are excluded from
ordinary audio classification until their wrapper/container role is understood.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import snddata_sample_setup_audit_v1 as v1
from compare_psound_to_latest_fragmenter_v1 import find_latest_fragmenter_report
from snddata_sample_trim_v3 import BLOCK_SIZE, trim_stream

REPORT_NAME = "snddata_sample_setup_audit.json"
CSV_NAME = "snddata_sample_setup_audit.csv"
LEGACY_EXTERNAL_BODY_ISSUE = "HEAD secondary body exceeds the containing resource"


def _int(value: Any) -> int | None:
    return v1._optional_int(value)


def _block_layout_stats(payload: bytes) -> dict[str, Any]:
    blocks = [
        payload[position : position + BLOCK_SIZE]
        for position in range(0, len(payload), BLOCK_SIZE)
    ]
    validity = [v1._valid_adpcm_block(block) for block in blocks]
    invalid_indices = [index for index, valid in enumerate(validity) if not valid]

    leading_invalid = 0
    for valid in validity:
        if valid:
            break
        leading_invalid += 1

    trailing_invalid = 0
    for valid in reversed(validity):
        if valid:
            break
        trailing_invalid += 1

    longest_start: int | None = None
    longest_length = 0
    run_start: int | None = None
    for index, valid in enumerate([*validity, False]):
        if valid and run_start is None:
            run_start = index
        elif not valid and run_start is not None:
            length = index - run_start
            if length > longest_length:
                longest_start = run_start
                longest_length = length
            run_start = None

    valid_count = len(blocks) - len(invalid_indices)
    return {
        "clean_adpcm_payload": not invalid_indices and bool(blocks),
        "valid_adpcm_ratio": round(valid_count / len(blocks), 6) if blocks else 0.0,
        "first_invalid_adpcm_block": invalid_indices[0] if invalid_indices else None,
        "last_invalid_adpcm_block": invalid_indices[-1] if invalid_indices else None,
        "leading_invalid_adpcm_blocks": leading_invalid,
        "trailing_invalid_adpcm_blocks": trailing_invalid,
        "longest_valid_adpcm_run_start": longest_start,
        "longest_valid_adpcm_run_blocks": longest_length,
    }


def _bank_layout(bank: dict[str, Any], source_size: int) -> tuple[str, int | None, list[str]]:
    body_base = _int(bank.get("body_base"))
    secondary_size = _int(bank.get("secondary_size"))
    resource_end = _int(bank.get("resource_end"))
    body_end = (
        body_base + secondary_size
        if body_base is not None and secondary_size is not None
        else None
    )
    notes: list[str] = []

    if body_base is None or secondary_size is None or resource_end is None:
        return "unknown", body_end, notes
    if body_end is not None and body_end > source_size:
        return "outside_source", body_end, notes
    if body_base == resource_end:
        notes.append(
            "HEAD secondary body begins at the metadata resource end; "
            "this detached layout is supported."
        )
        return "detached_at_resource_end", body_end, notes
    if body_base > resource_end:
        notes.append(
            "HEAD secondary body begins after the metadata resource end; "
            "this detached layout is supported when source bounds and rows validate."
        )
        return "detached_after_resource", body_end, notes
    if body_end is not None and body_end <= resource_end:
        return "inline_in_metadata_resource", body_end, notes
    notes.append(
        "HEAD secondary body crosses the metadata resource boundary; "
        "retain as a distinct layout for review."
    )
    return "crosses_metadata_resource_boundary", body_end, notes


def _catalog_role(row: dict[str, Any]) -> str:
    if row.get("status") == "invalid_setup":
        return "invalid_setup"
    if row.get("clean_adpcm_payload"):
        return "clean_audio_candidate"
    if _int(row.get("sample_index")) == 0:
        return "first_entry_container_or_placeholder_candidate"
    return "wrapped_or_non_audio_entry_candidate"


def audit_report(report_path: Path) -> dict[str, Any]:
    report_path = report_path.expanduser().resolve()
    payload = v1.audit_report(report_path)
    source_path = Path(str(payload["snddata_source"])).expanduser().resolve()
    source = source_path.read_bytes()

    row_status_counts: Counter[str] = Counter()
    catalog_role_counts: Counter[str] = Counter()
    nonplayable_index_counts: Counter[int] = Counter()

    for row in payload.get("rows") or []:
        source_offset = _int(row.get("source_offset"))
        raw_size = _int(row.get("raw_span_size"))
        encoded = b""
        if (
            source_offset is not None
            and raw_size is not None
            and raw_size > 0
            and 0 <= source_offset <= len(source) - raw_size
        ):
            raw = source[source_offset : source_offset + raw_size]
            encoded, _trim = trim_stream(raw)

        row.update(_block_layout_stats(encoded))
        row["catalog_role"] = _catalog_role(row)
        row["entry_position"] = (
            "first_in_bank" if _int(row.get("sample_index")) == 0 else "later_in_bank"
        )
        row_status_counts[str(row.get("status") or "unknown")] += 1
        catalog_role_counts[str(row["catalog_role"])] += 1
        if row.get("status") == "structurally_valid_nonplayable":
            sample_index = _int(row.get("sample_index"))
            if sample_index is not None:
                nonplayable_index_counts[sample_index] += 1

    bank_layout_counts: Counter[str] = Counter()
    for bank in payload.get("banks") or []:
        issues = [
            str(issue)
            for issue in bank.get("issues") or []
            if str(issue) != LEGACY_EXTERNAL_BODY_ISSUE
        ]
        layout, body_end, layout_notes = _bank_layout(bank, len(source))
        bank["issues"] = issues
        bank["layout"] = layout
        bank["secondary_body_end"] = body_end
        bank["layout_notes"] = layout_notes
        bank["span_coverage"] = (
            "complete"
            if _int(bank.get("first_stream_offset")) == 0
            and _int(bank.get("shared_stream_entry_count")) == 0
            else "review"
        )
        bank["status"] = (
            "pass"
            if not issues and _int(bank.get("invalid_setup_rows")) == 0
            else "fail"
        )
        bank_layout_counts[layout] += 1

    hard_error_count = sum(
        1 for row in payload.get("rows") or [] if row.get("status") == "invalid_setup"
    )
    failing_banks = sum(
        1 for bank in payload.get("banks") or [] if bank.get("status") == "fail"
    )
    report_sample_count = len(
        [row for row in v1._load_json(report_path).get("samples") or [] if isinstance(row, dict)]
    )
    structural_gate = (
        "pass"
        if payload.get("source_sha256_matches")
        and hard_error_count == 0
        and failing_banks == 0
        and len(payload.get("rows") or []) == report_sample_count
        else "fail"
    )

    clean_rows = catalog_role_counts.get("clean_audio_candidate", 0)
    unresolved_rows = (
        catalog_role_counts.get("first_entry_container_or_placeholder_candidate", 0)
        + catalog_role_counts.get("wrapped_or_non_audio_entry_candidate", 0)
    )
    classification_gate = (
        "pass"
        if structural_gate == "pass" and unresolved_rows == 0
        else "pass_clean_rows_only"
        if structural_gate == "pass" and clean_rows > 0
        else "fail"
    )

    payload["version"] = 2
    payload["structural_gate"] = structural_gate
    payload["size_gate"] = structural_gate
    payload["classification_gate"] = classification_gate
    payload["summary"] = {
        **dict(payload.get("summary") or {}),
        "passing_banks": len(payload.get("banks") or []) - failing_banks,
        "failing_banks": failing_banks,
        "row_status_counts": dict(row_status_counts),
        "catalog_role_counts": dict(catalog_role_counts),
        "bank_layout_counts": dict(bank_layout_counts),
        "hard_error_count": hard_error_count,
        "nonplayable_sample_index_counts": {
            str(index): count for index, count in sorted(nonplayable_index_counts.items())
        },
        "nonplayable_first_entry_rows": nonplayable_index_counts.get(0, 0),
        "clean_audio_rows": clean_rows,
        "unresolved_entry_rows": unresolved_rows,
    }
    payload["classification_policy"] = {
        **dict(payload.get("classification_policy") or {}),
        "eligible_catalog_role": "clean_audio_candidate",
        "excluded_catalog_roles": [
            "first_entry_container_or_placeholder_candidate",
            "wrapped_or_non_audio_entry_candidate",
            "invalid_setup",
        ],
        "detached_secondary_body_layout": (
            "Supported. Metadata resource bounds do not define HEAD secondary-body bounds; "
            "source bounds plus SCEIVagi span validation are authoritative."
        ),
    }
    payload["definitions"] = {
        **dict(payload.get("definitions") or {}),
        "clean_audio_candidate": (
            "A structurally valid retained payload in which every 16-byte block has a "
            "valid PlayStation ADPCM predictor and shift."
        ),
        "unresolved_entry": (
            "A structurally valid SCEIVagi span containing non-ADPCM blocks. Keep its "
            "authoritative raw span and encoded size, but do not classify it as ordinary "
            "audio until its wrapper/container role is resolved."
        ),
    }
    payload["remaining_unknowns"] = [
        *list(payload.get("remaining_unknowns") or []),
        "The exact role and internal framing of the unresolved first-entry payloads in later banks.",
    ]
    return payload


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = (
        "bank_ordinal",
        "resource_offset",
        "sample_index",
        "flat_index",
        "entry_position",
        "catalog_role",
        "sample_rate",
        "stream_offset",
        "source_offset",
        "raw_span_size",
        "encoded_payload_size",
        "structural_edge_bytes",
        "payload_block_count",
        "valid_adpcm_block_count",
        "invalid_adpcm_block_count",
        "valid_adpcm_ratio",
        "first_invalid_adpcm_block",
        "last_invalid_adpcm_block",
        "leading_invalid_adpcm_blocks",
        "trailing_invalid_adpcm_blocks",
        "longest_valid_adpcm_run_start",
        "longest_valid_adpcm_run_blocks",
        "flag_07_block_count",
        "first_flag_07_block",
        "decoder_stop_block_count",
        "reported_sample_count",
        "authoritative_span_frame_capacity",
        "decode_status",
        "wav_available",
        "status",
        "hard_issues",
        "notes",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writable = dict(row)
            writable["hard_issues"] = json.dumps(writable.get("hard_issues") or [])
            writable["notes"] = json.dumps(writable.get("notes") or [])
            writer.writerow({field: writable.get(field) for field in fields})


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
    if json_path.exists():
        json_path.unlink()
    if csv_path.exists():
        csv_path.unlink()

    payload = audit_report(report_path)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(csv_path, payload["rows"])

    summary = payload["summary"]
    print(f"Fragmenter report: {report_path}")
    print(f"SNDDATA source: {payload['snddata_source']}")
    print(f"Source SHA-256 matches report: {payload['source_sha256_matches']}")
    print(f"Structural gate: {payload['structural_gate']}")
    print(f"Size gate: {payload['size_gate']}")
    print(f"Classification gate: {payload['classification_gate']}")
    print(f"Sample rows: {summary['sample_rows']}")
    print(f"Banks: {summary['passing_banks']} pass, {summary['failing_banks']} fail")
    print(f"Bank layouts: {summary['bank_layout_counts']}")
    print(f"Rows: {summary['row_status_counts']}")
    print(f"Catalog roles: {summary['catalog_role_counts']}")
    print(f"Nonplayable sample indices: {summary['nonplayable_sample_index_counts']}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0 if payload["structural_gate"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Find a consistent SNDDATA secondary-body shift for each later sample bank.

The current later-bank body bases begin at nested SCEI sequence resources.
This evidence-only audit scans aligned shifts without changing stream offsets or
span lengths. A candidate is credible only when one shift makes the whole bank
look structurally like PS-ADPCM: sample edge blocks align and every retained
payload validates under the v3 trim policy.
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

from compare_psound_to_latest_fragmenter_v1 import find_latest_fragmenter_report
from snddata_sample_setup_audit_v2 import audit_report as audit_setup_v2
from snddata_sample_setup_audit_v3 import classify_body_base_signature
from snddata_sample_trim_v3 import BLOCK_SIZE, SEPARATOR, trim_stream

REPORT_NAME = "snddata_bank_body_shift_audit.json"
CSV_NAME = "snddata_bank_body_shift_audit.csv"
MAX_TOP_CANDIDATES = 24
PROBE_BLOCKS_PER_EDGE = 4
_COEF_COUNT = 5


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _valid_block(block: bytes) -> bool:
    return (
        len(block) == BLOCK_SIZE
        and (block[0] >> 4) < _COEF_COUNT
        and (block[0] & 0x0F) <= 12
    )


def _row_span(
    source: bytes,
    body_base: int,
    shift: int,
    row: dict[str, Any],
) -> bytes | None:
    stream_offset = _int(row.get("stream_offset"))
    raw_size = _int(row.get("raw_span_size"))
    if stream_offset is None or raw_size is None or raw_size <= 0:
        return None
    start = body_base + shift + stream_offset
    end = start + raw_size
    if start < 0 or end > len(source):
        return None
    return source[start:end]


def probe_shift(
    source: bytes,
    body_base: int,
    shift: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    leading_zero_rows = 0
    trailing_separator_rows = 0
    valid_probe_blocks = 0
    probe_blocks = 0
    out_of_bounds_rows = 0
    scei_header_rows = 0

    for row in rows:
        raw = _row_span(source, body_base, shift, row)
        if raw is None:
            out_of_bounds_rows += 1
            continue
        if raw[:8] in (b"IECSsreV", b"SCEIVers"):
            scei_header_rows += 1

        leading_zero = len(raw) >= BLOCK_SIZE and raw[:BLOCK_SIZE] == b"\x00" * BLOCK_SIZE
        trailing_separator = (
            len(raw) >= BLOCK_SIZE and raw[-BLOCK_SIZE:] == SEPARATOR
        )
        leading_zero_rows += int(leading_zero)
        trailing_separator_rows += int(trailing_separator)

        start = BLOCK_SIZE if leading_zero else 0
        end = len(raw) - BLOCK_SIZE if trailing_separator else len(raw)
        aligned_end = end - (end % BLOCK_SIZE)

        front_positions = list(
            range(start, min(aligned_end, start + PROBE_BLOCKS_PER_EDGE * BLOCK_SIZE), BLOCK_SIZE)
        )
        back_start = max(start, aligned_end - PROBE_BLOCKS_PER_EDGE * BLOCK_SIZE)
        back_positions = list(range(back_start, aligned_end, BLOCK_SIZE))
        positions = sorted(set(front_positions + back_positions))
        for position in positions:
            block = raw[position : position + BLOCK_SIZE]
            probe_blocks += 1
            valid_probe_blocks += int(_valid_block(block))

    edge_rows = leading_zero_rows + trailing_separator_rows
    return {
        "shift": shift,
        "corrected_body_base": body_base + shift,
        "row_count": len(rows),
        "leading_zero_rows": leading_zero_rows,
        "trailing_separator_rows": trailing_separator_rows,
        "edge_rows": edge_rows,
        "valid_probe_blocks": valid_probe_blocks,
        "probe_blocks": probe_blocks,
        "probe_valid_ratio": (
            round(valid_probe_blocks / probe_blocks, 6) if probe_blocks else 0.0
        ),
        "out_of_bounds_rows": out_of_bounds_rows,
        "scei_header_rows": scei_header_rows,
        "_screen_score": (
            -out_of_bounds_rows,
            edge_rows,
            valid_probe_blocks,
            leading_zero_rows,
            trailing_separator_rows,
            -scei_header_rows,
        ),
    }


def confirm_shift(
    source: bytes,
    body_base: int,
    shift: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    clean_rows = 0
    invalid_blocks = 0
    payload_blocks = 0
    empty_rows = 0
    trim_leading_zero_rows = 0
    trim_trailing_separator_rows = 0
    source_span_errors = 0

    for row in rows:
        raw = _row_span(source, body_base, shift, row)
        if raw is None:
            source_span_errors += 1
            continue
        payload, trim = trim_stream(raw)
        trim_leading_zero_rows += int(bool(trim.get("leading_zero_block")))
        trim_trailing_separator_rows += int(
            trim.get("terminator_kind") == "trailing_007777_separator"
        )
        blocks = [
            payload[position : position + BLOCK_SIZE]
            for position in range(0, len(payload), BLOCK_SIZE)
        ]
        if not blocks:
            empty_rows += 1
            continue
        row_invalid = sum(not _valid_block(block) for block in blocks)
        invalid_blocks += row_invalid
        payload_blocks += len(blocks)
        if row_invalid == 0:
            clean_rows += 1

    return {
        "shift": shift,
        "corrected_body_base": body_base + shift,
        "row_count": len(rows),
        "clean_rows": clean_rows,
        "invalid_blocks": invalid_blocks,
        "payload_blocks": payload_blocks,
        "full_valid_ratio": (
            round((payload_blocks - invalid_blocks) / payload_blocks, 8)
            if payload_blocks
            else 0.0
        ),
        "empty_rows": empty_rows,
        "trim_leading_zero_rows": trim_leading_zero_rows,
        "trim_trailing_separator_rows": trim_trailing_separator_rows,
        "source_span_errors": source_span_errors,
        "_confirm_score": (
            -source_span_errors,
            clean_rows,
            -invalid_blocks,
            trim_leading_zero_rows + trim_trailing_separator_rows,
            trim_leading_zero_rows,
            trim_trailing_separator_rows,
            -empty_rows,
        ),
    }


def scan_bank(
    source: bytes,
    bank: dict[str, Any],
    rows: list[dict[str, Any]],
    next_sample_resource_offset: int,
) -> dict[str, Any]:
    ordinal = _int(bank.get("bank_ordinal"))
    body_base = _int(bank.get("body_base"))
    secondary_size = _int(bank.get("secondary_size"))
    if body_base is None or secondary_size is None:
        return {
            "bank_ordinal": ordinal,
            "status": "missing_bank_geometry",
            "candidate_shifts": [],
        }

    signature = classify_body_base_signature(source, body_base)
    max_shift = next_sample_resource_offset - body_base - secondary_size
    max_shift_aligned = max_shift - (max_shift % BLOCK_SIZE) if max_shift >= 0 else -1

    sequence_primary_size = None
    if (
        signature.get("status") == "scei_sequence_resource_header"
        and body_base + 32 <= len(source)
    ):
        sequence_primary_size = struct.unpack_from("<I", source, body_base + 28)[0]

    if max_shift_aligned < 0:
        return {
            "bank_ordinal": ordinal,
            "status": "no_in_bounds_shift_window",
            "current_body_base": body_base,
            "secondary_size": secondary_size,
            "next_sample_resource_offset": next_sample_resource_offset,
            "max_shift": max_shift,
            "body_base_signature": signature,
            "sequence_primary_size": sequence_primary_size,
            "candidate_shifts": [],
        }

    screened = [
        probe_shift(source, body_base, shift, rows)
        for shift in range(0, max_shift_aligned + 1, BLOCK_SIZE)
    ]
    screened.sort(key=lambda item: item["_screen_score"], reverse=True)
    top = screened[:MAX_TOP_CANDIDATES]
    confirmed = []
    for item in top:
        confirmation = confirm_shift(source, body_base, int(item["shift"]), rows)
        confirmation["screen"] = {
            key: value for key, value in item.items() if not key.startswith("_")
        }
        confirmed.append(confirmation)
    confirmed.sort(key=lambda item: item["_confirm_score"], reverse=True)

    best_score = confirmed[0]["_confirm_score"] if confirmed else None
    best = [item for item in confirmed if item["_confirm_score"] == best_score]
    selected = best[0] if len(best) == 1 else None

    if not confirmed:
        status = "no_shift_candidates"
    elif len(best) > 1:
        status = "ambiguous_best_bank_shift"
    elif selected and selected["clean_rows"] == len(rows):
        status = "unique_clean_bank_shift"
    else:
        status = "unique_partial_bank_shift"

    clean_confirmations = [
        item for item in confirmed if item["clean_rows"] == len(rows)
    ]

    def public(item: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in item.items() if not key.startswith("_")}

    return {
        "bank_ordinal": ordinal,
        "status": status,
        "resource_offset": _int(bank.get("resource_offset")),
        "current_body_base": body_base,
        "secondary_size": secondary_size,
        "sample_row_count": len(rows),
        "next_sample_resource_offset": next_sample_resource_offset,
        "max_shift": max_shift,
        "max_shift_aligned": max_shift_aligned,
        "body_base_signature": signature,
        "sequence_primary_size": sequence_primary_size,
        "selected_shift": int(selected["shift"]) if selected else None,
        "corrected_body_base": (
            int(selected["corrected_body_base"]) if selected else None
        ),
        "selected_clean_rows": int(selected["clean_rows"]) if selected else None,
        "selected_invalid_blocks": (
            int(selected["invalid_blocks"]) if selected else None
        ),
        "fully_clean_candidate_count": len(clean_confirmations),
        "candidate_shifts": [public(item) for item in confirmed[:10]],
    }


def audit_report(report_path: Path) -> dict[str, Any]:
    setup = audit_setup_v2(report_path)
    source_path = Path(str(setup["snddata_source"])).expanduser().resolve()
    source = source_path.read_bytes()

    banks = sorted(
        [dict(bank) for bank in setup.get("banks") or []],
        key=lambda bank: int(bank.get("resource_offset") or 0),
    )
    rows_by_bank: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in setup.get("rows") or []:
        ordinal = _int(row.get("bank_ordinal"))
        if ordinal is not None:
            rows_by_bank[ordinal].append(dict(row))
    for bank_rows in rows_by_bank.values():
        bank_rows.sort(key=lambda row: int(row.get("sample_index") or 0))

    results: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for index, bank in enumerate(banks):
        ordinal = _int(bank.get("bank_ordinal"))
        body_base = _int(bank.get("body_base"))
        signature = classify_body_base_signature(source, body_base)
        if signature.get("status") not in {
            "scei_sequence_resource_header",
            "scei_sequence_resource_like",
        }:
            result = {
                "bank_ordinal": ordinal,
                "status": "current_body_base_not_nested_sequence",
                "resource_offset": _int(bank.get("resource_offset")),
                "current_body_base": body_base,
                "secondary_size": _int(bank.get("secondary_size")),
                "sample_row_count": len(rows_by_bank.get(ordinal or -1, [])),
                "body_base_signature": signature,
                "selected_shift": 0,
                "corrected_body_base": body_base,
                "selected_clean_rows": len(rows_by_bank.get(ordinal or -1, [])),
                "selected_invalid_blocks": 0,
                "fully_clean_candidate_count": 1,
                "candidate_shifts": [],
            }
        else:
            next_resource = (
                _int(banks[index + 1].get("resource_offset"))
                if index + 1 < len(banks)
                else len(source)
            )
            result = scan_bank(
                source,
                bank,
                rows_by_bank.get(ordinal or -1, []),
                int(next_resource),
            )
        results.append(result)
        status = str(result.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    clean_shift_banks = sum(
        result.get("status") in {
            "unique_clean_bank_shift",
            "current_body_base_not_nested_sequence",
        }
        for result in results
    )
    unresolved_banks = len(results) - clean_shift_banks
    return {
        "version": 1,
        "fragmenter_report": str(report_path),
        "snddata_source": str(source_path),
        "source_sha256_matches": setup.get("source_sha256_matches"),
        "scan_policy": {
            "shift_alignment": BLOCK_SIZE,
            "shift_window": (
                "From the current selected body base through the latest in-bounds "
                "base before the next sample-program metadata resource."
            ),
            "screening": (
                "Count leading zero blocks, trailing exact separators, and valid "
                "ADPCM blocks at both sample edges for every entry in the bank."
            ),
            "confirmation": (
                "Apply v3 edge trimming and validate every retained block for every "
                "sample under one shared bank shift."
            ),
            "modifies_extraction": False,
        },
        "summary": {
            "bank_count": len(results),
            "status_counts": status_counts,
            "clean_shift_banks": clean_shift_banks,
            "unresolved_banks": unresolved_banks,
            "classification_gate": (
                "pass_body_bases" if unresolved_banks == 0 else "fail"
            ),
        },
        "banks": results,
    }


def _write_csv(path: Path, banks: list[dict[str, Any]]) -> None:
    fields = (
        "bank_ordinal",
        "status",
        "resource_offset",
        "current_body_base",
        "secondary_size",
        "sample_row_count",
        "next_sample_resource_offset",
        "max_shift",
        "max_shift_aligned",
        "sequence_primary_size",
        "selected_shift",
        "corrected_body_base",
        "selected_clean_rows",
        "selected_invalid_blocks",
        "fully_clean_candidate_count",
        "body_base_signature_status",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for bank in banks:
            row = dict(bank)
            signature = row.get("body_base_signature") or {}
            row["body_base_signature_status"] = signature.get("status")
            writer.writerow({field: row.get(field) for field in fields})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("search_root", nargs="?", default=str(Path.cwd().parent))
    parser.add_argument("--fragmenter-report")
    parser.add_argument(
        "--output",
        default=str(Path.cwd() / "diagnostics" / "snddata_bank_body_shift"),
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
    _write_csv(csv_path, payload["banks"])

    summary = payload["summary"]
    print(f"Fragmenter report: {report_path}")
    print(f"Source SHA-256 matches report: {payload.get('source_sha256_matches')}")
    print(f"Banks: {summary['bank_count']}")
    print(f"Statuses: {summary['status_counts']}")
    print(f"Clean body-base banks: {summary['clean_shift_banks']}")
    print(f"Unresolved body-base banks: {summary['unresolved_banks']}")
    print(f"Classification gate: {summary['classification_gate']}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0 if summary["classification_gate"] == "pass_body_bases" else 1


if __name__ == "__main__":
    raise SystemExit(main())

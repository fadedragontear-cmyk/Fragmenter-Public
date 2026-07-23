#!/usr/bin/env python3
"""Validate SNDDATA sample boundaries and classification prerequisites.

This audit is intentionally independent of PSound ordering. It proves the layout
Fragmenter itself claims: SCEIVagi offsets define physical spans, the v3 trim policy
removes only structural edge blocks, and decoded playback length is reported as a
separate quantity from encoded payload size.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from compare_psound_to_latest_fragmenter_v1 import (
    CORRECTED_TRIM_POLICY,
    find_latest_fragmenter_report,
)
from snddata_sample_trim_v3 import BLOCK_SIZE, SEPARATOR, trim_stream

REPORT_NAME = "snddata_sample_setup_audit.json"
CSV_NAME = "snddata_sample_setup_audit.csv"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_path(value: Any, report_path: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = report_path.parent / path
    try:
        return path.resolve()
    except OSError:
        return path


def _valid_adpcm_block(block: bytes) -> bool:
    return (
        len(block) == BLOCK_SIZE
        and (block[0] >> 4) < 5
        and (block[0] & 0x0F) <= 12
    )


def _payload_stats(payload: bytes) -> dict[str, Any]:
    blocks = [payload[pos : pos + BLOCK_SIZE] for pos in range(0, len(payload), BLOCK_SIZE)]
    flag_07 = [index for index, block in enumerate(blocks) if len(block) == BLOCK_SIZE and block[1] == 0x07]
    exact_separators = [index for index, block in enumerate(blocks) if block == SEPARATOR]
    first_flag = flag_07[0] if flag_07 else None
    stop_blocks = first_flag if first_flag is not None else len(blocks)
    stop_prefix_valid = all(_valid_adpcm_block(block) for block in blocks[:stop_blocks])
    valid_blocks = sum(_valid_adpcm_block(block) for block in blocks)
    return {
        "payload_block_count": len(blocks),
        "valid_adpcm_block_count": valid_blocks,
        "invalid_adpcm_block_count": len(blocks) - valid_blocks,
        "flag_07_block_count": len(flag_07),
        "first_flag_07_block": first_flag,
        "exact_separator_block_count": len(exact_separators),
        "decoder_stop_block_count": stop_blocks,
        "decoder_stop_frame_count": stop_blocks * 28 if stop_prefix_valid else None,
        "authoritative_span_frame_capacity": len(blocks) * 28,
    }


def _trim_metadata_matches(recorded: Any, derived: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(recorded, dict):
        return ["missing trim metadata"]
    keys = (
        "policy",
        "leading_zero_block",
        "payload_skip",
        "terminator_offset",
        "terminator_kind",
        "internal_007777_separator_count",
        "ignored_adpcm_flag_07_count",
        "trimmed_tail_bytes",
        "unaligned_tail_bytes",
    )
    for key in keys:
        if recorded.get(key) != derived.get(key):
            issues.append(
                f"trim metadata {key}={recorded.get(key)!r} does not match derived {derived.get(key)!r}"
            )
    return issues


def audit_report(report_path: Path) -> dict[str, Any]:
    report_path = report_path.expanduser().resolve()
    report = _load_json(report_path)
    source_path = _resolve_path(report.get("source"), report_path)
    if source_path is None or not source_path.is_file():
        raise FileNotFoundError(f"SNDDATA source from report is unavailable: {source_path}")
    source = source_path.read_bytes()

    recorded_sha = str(report.get("source_sha256") or "").strip().lower()
    actual_sha = hashlib.sha256(source).hexdigest()
    source_sha_matches = not recorded_sha or recorded_sha == actual_sha

    rows: list[dict[str, Any]] = []
    banks_out: list[dict[str, Any]] = []
    row_status_counts: Counter[str] = Counter()
    hard_issue_counts: Counter[str] = Counter()
    total_report_samples = 0

    for bank in report.get("banks") or []:
        if not isinstance(bank, dict) or bank.get("resource_type") != 2:
            continue
        ordinal = _optional_int(bank.get("ordinal"))
        resource_offset = _optional_int(bank.get("resource_offset"))
        resource_end = _optional_int(bank.get("resource_end"))
        body_base = _optional_int(bank.get("body_base"))
        head = bank.get("head") if isinstance(bank.get("head"), dict) else {}
        vagi = bank.get("vagi") if isinstance(bank.get("vagi"), dict) else {}
        secondary_size = _optional_int(head.get("secondary_size"))
        declared_count = _optional_int(vagi.get("item_count"))
        samples = [row for row in bank.get("samples") or [] if isinstance(row, dict)]
        total_report_samples += len(samples)

        bank_issues: list[str] = []
        required = {
            "resource_offset": resource_offset,
            "resource_end": resource_end,
            "body_base": body_base,
            "secondary_size": secondary_size,
        }
        for name, value in required.items():
            if value is None:
                bank_issues.append(f"missing {name}")
        if declared_count is not None and declared_count != len(samples):
            bank_issues.append(
                f"SCEIVagi item_count {declared_count} does not match {len(samples)} sample rows"
            )

        offsets = sorted(
            {
                value
                for value in (_optional_int(row.get("stream_offset")) for row in samples)
                if value is not None
            }
        )
        next_offset = {
            value: offsets[index + 1] if index + 1 < len(offsets) else secondary_size
            for index, value in enumerate(offsets)
        }
        if offsets and offsets[0] < 0:
            bank_issues.append("negative first stream offset")
        if any(value % BLOCK_SIZE for value in offsets):
            bank_issues.append("one or more SCEIVagi stream offsets are not 16-byte aligned")
        if (
            body_base is not None
            and secondary_size is not None
            and resource_end is not None
            and body_base + secondary_size > resource_end
        ):
            bank_issues.append("HEAD secondary body exceeds the containing resource")
        if body_base is not None and secondary_size is not None and body_base + secondary_size > len(source):
            bank_issues.append("HEAD secondary body exceeds the SNDDATA source")

        duplicate_entries = len(samples) - len(offsets)
        bank_row_errors = 0
        ready_rows = 0
        nonplayable_rows = 0

        for sample in samples:
            stream_offset = _optional_int(sample.get("stream_offset"))
            sample_index = _optional_int(sample.get("index"))
            sample_rate = _optional_int(sample.get("sample_rate"))
            hard_issues: list[str] = []
            notes: list[str] = []

            expected_end = next_offset.get(stream_offset) if stream_offset is not None else None
            expected_raw_size = (
                expected_end - stream_offset
                if stream_offset is not None and expected_end is not None
                else None
            )
            expected_source_offset = (
                body_base + stream_offset
                if body_base is not None and stream_offset is not None
                else None
            )
            if stream_offset is None:
                hard_issues.append("missing stream_offset")
            elif stream_offset % BLOCK_SIZE:
                hard_issues.append("stream_offset is not 16-byte aligned")
            if expected_raw_size is None or expected_raw_size <= 0:
                hard_issues.append("non-positive or unresolved SCEIVagi span")
            elif expected_raw_size % BLOCK_SIZE:
                hard_issues.append("SCEIVagi span size is not 16-byte aligned")
            if sample_rate is None or not 4000 <= sample_rate <= 192000:
                hard_issues.append("missing or implausible sample_rate")

            recorded_source_offset = _optional_int(sample.get("source_offset"))
            recorded_raw_size = _optional_int(sample.get("raw_size"))
            recorded_payload_size = _optional_int(sample.get("payload_size"))
            if expected_source_offset is not None and recorded_source_offset != expected_source_offset:
                hard_issues.append(
                    f"source_offset {recorded_source_offset} does not equal body_base + stream_offset {expected_source_offset}"
                )
            if expected_raw_size is not None and recorded_raw_size != expected_raw_size:
                hard_issues.append(
                    f"raw_size {recorded_raw_size} does not equal next SCEIVagi boundary span {expected_raw_size}"
                )

            raw = b""
            derived_payload = b""
            derived_trim: dict[str, Any] = {}
            if (
                expected_source_offset is not None
                and expected_raw_size is not None
                and expected_raw_size > 0
                and 0 <= expected_source_offset <= len(source) - expected_raw_size
            ):
                raw = source[expected_source_offset : expected_source_offset + expected_raw_size]
                derived_payload, derived_trim = trim_stream(raw)
                if recorded_payload_size != len(derived_payload):
                    hard_issues.append(
                        f"payload_size {recorded_payload_size} does not equal v3-derived size {len(derived_payload)}"
                    )
                hard_issues.extend(_trim_metadata_matches(sample.get("trim"), derived_trim))
            else:
                hard_issues.append("sample span is outside the source")

            raw_path = _resolve_path(sample.get("raw_path"), report_path)
            if raw_path is None or not raw_path.is_file():
                notes.append("raw extraction file is unavailable")
            elif raw and raw_path.read_bytes() != raw:
                hard_issues.append("raw extraction file differs from authoritative source span")

            output_path = _resolve_path(sample.get("output_path"), report_path)
            wav_available = output_path is not None and output_path.is_file()
            decode_status = str(sample.get("decode_status") or "")
            decode_errors = [str(value) for value in sample.get("errors") or []]
            stats = _payload_stats(derived_payload)
            reported_sample_count = _optional_int(sample.get("sample_count"))
            expected_stop_frames = stats.get("decoder_stop_frame_count")
            if reported_sample_count is not None and expected_stop_frames is not None:
                if reported_sample_count != expected_stop_frames:
                    hard_issues.append(
                        f"sample_count {reported_sample_count} does not match current decoder frame count {expected_stop_frames}"
                    )

            if hard_issues:
                status = "invalid_setup"
                bank_row_errors += 1
                for issue in hard_issues:
                    hard_issue_counts[issue.split(":", 1)[0]] += 1
            elif wav_available and not decode_errors and decode_status.startswith("decoded"):
                status = "ready_for_classification"
                ready_rows += 1
            else:
                status = "structurally_valid_nonplayable"
                nonplayable_rows += 1
            row_status_counts[status] += 1

            rows.append(
                {
                    "bank_ordinal": ordinal,
                    "resource_offset": resource_offset,
                    "sample_index": sample_index,
                    "flat_index": sample.get("flat_index"),
                    "sample_rate": sample_rate,
                    "stream_offset": stream_offset,
                    "source_offset": recorded_source_offset,
                    "raw_span_size": recorded_raw_size,
                    "encoded_payload_size": recorded_payload_size,
                    "structural_edge_bytes": (
                        recorded_raw_size - recorded_payload_size
                        if recorded_raw_size is not None and recorded_payload_size is not None
                        else None
                    ),
                    "decode_status": decode_status,
                    "wav_available": wav_available,
                    "reported_sample_count": reported_sample_count,
                    **stats,
                    "status": status,
                    "hard_issues": hard_issues,
                    "notes": notes,
                }
            )

        bank_status = "pass" if not bank_issues and bank_row_errors == 0 else "fail"
        banks_out.append(
            {
                "bank_ordinal": ordinal,
                "resource_offset": resource_offset,
                "resource_end": resource_end,
                "body_base": body_base,
                "secondary_size": secondary_size,
                "declared_sample_count": declared_count,
                "sample_row_count": len(samples),
                "unique_stream_offset_count": len(offsets),
                "shared_stream_entry_count": duplicate_entries,
                "first_stream_offset": offsets[0] if offsets else None,
                "unreferenced_leading_body_bytes": offsets[0] if offsets else secondary_size,
                "ready_for_classification_rows": ready_rows,
                "structurally_valid_nonplayable_rows": nonplayable_rows,
                "invalid_setup_rows": bank_row_errors,
                "status": bank_status,
                "issues": bank_issues,
            }
        )

    hard_error_count = sum(1 for row in rows if row["status"] == "invalid_setup")
    structural_gate = (
        "pass"
        if source_sha_matches
        and hard_error_count == 0
        and total_report_samples == len(report.get("samples") or [])
        else "fail"
    )
    nonplayable_count = row_status_counts.get("structurally_valid_nonplayable", 0)
    classification_gate = (
        "pass"
        if structural_gate == "pass" and nonplayable_count == 0
        else "pass_with_nonplayable_rows"
        if structural_gate == "pass"
        else "fail"
    )

    return {
        "version": 1,
        "fragmenter_report": str(report_path),
        "snddata_source": str(source_path),
        "source_size": len(source),
        "source_sha256_recorded": recorded_sha or None,
        "source_sha256_actual": actual_sha,
        "source_sha256_matches": source_sha_matches,
        "trim_policy_required": CORRECTED_TRIM_POLICY,
        "structural_gate": structural_gate,
        "classification_gate": classification_gate,
        "summary": {
            "sample_rows": len(rows),
            "sample_program_banks": len(banks_out),
            "passing_banks": sum(bank["status"] == "pass" for bank in banks_out),
            "failing_banks": sum(bank["status"] == "fail" for bank in banks_out),
            "row_status_counts": dict(row_status_counts),
            "hard_error_count": hard_error_count,
            "hard_issue_counts": dict(hard_issue_counts),
        },
        "definitions": {
            "raw_span_size": "Bytes from one SCEIVagi stream offset to the next offset, or to HEAD secondary_size for the final stream.",
            "encoded_payload_size": "Raw span after only the v3 structural edge policy; this is the source-size authority for classification.",
            "reported_sample_count": "Frames emitted by the current decoder, which stops at the first flag-07 block.",
            "authoritative_span_frame_capacity": "Maximum one-pass PCM frames if every retained 16-byte block is decoded; not a proven gameplay loop duration.",
        },
        "classification_policy": {
            "size_authority": "encoded_payload_size",
            "rate_authority": "SCEIVagi sample_rate",
            "channels": 1,
            "codec": "PlayStation SPU ADPCM",
            "do_not_use_as_size_authority": [
                "PSound WAV frame count",
                "PSound equal numeric index",
                "loop-expanded playback duration",
            ],
            "nonplayable_rows": "Keep structurally valid rows in the catalog, but mark them unavailable/placeholder until decoder semantics are resolved.",
        },
        "remaining_unknowns": [
            "Gameplay loop start/end behavior encoded by flag-07 and related SPU ADPCM control flags.",
            "PSound catalog identity beyond independently PCM-confirmed anchors.",
            "Whether PSound exported one pass or an unrolled loop for each individual sample.",
        ],
        "banks": banks_out,
        "rows": rows,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = (
        "bank_ordinal",
        "resource_offset",
        "sample_index",
        "flat_index",
        "sample_rate",
        "stream_offset",
        "source_offset",
        "raw_span_size",
        "encoded_payload_size",
        "structural_edge_bytes",
        "payload_block_count",
        "valid_adpcm_block_count",
        "invalid_adpcm_block_count",
        "flag_07_block_count",
        "first_flag_07_block",
        "exact_separator_block_count",
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
    parser.add_argument("--output", default=str(Path.cwd() / "diagnostics" / "snddata_sample_setup"))
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
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, payload["rows"])

    summary = payload["summary"]
    print(f"Fragmenter report: {report_path}")
    print(f"SNDDATA source: {payload['snddata_source']}")
    print(f"Source SHA-256 matches report: {payload['source_sha256_matches']}")
    print(f"Structural gate: {payload['structural_gate']}")
    print(f"Classification gate: {payload['classification_gate']}")
    print(f"Sample rows: {summary['sample_rows']}")
    print(f"Banks: {summary['passing_banks']} pass, {summary['failing_banks']} fail")
    print(f"Rows: {summary['row_status_counts']}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0 if payload["structural_gate"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

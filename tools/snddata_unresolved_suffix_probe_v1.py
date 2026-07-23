#!/usr/bin/env python3
"""Probe structurally valid SNDDATA entries that contain mixed non-ADPCM prefixes.

This tool is evidence-only. It preserves each authoritative SCEIVagi span and v3
encoded payload size, then tests whether the bytes after the final invalid ADPCM
block form a clean suffix stream. Candidate suffixes are exported separately for
listening and PCM comparison; the source extraction report is never modified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from audio_decoder import decode_ps_adpcm_blocks, write_pcm_wav
from compare_psound_to_latest_fragmenter_v1 import find_latest_fragmenter_report
from snddata_sample_setup_audit_v2 import audit_report as audit_setup
from snddata_sample_trim_v3 import BLOCK_SIZE, trim_stream

REPORT_NAME = "snddata_unresolved_suffix_probe.json"
CSV_NAME = "snddata_unresolved_suffix_probe.csv"
MIN_RECOVERABLE_BLOCKS = 64
_COEFS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _valid_block(block: bytes) -> bool:
    return (
        len(block) == BLOCK_SIZE
        and (block[0] >> 4) < len(_COEFS)
        and (block[0] & 0x0F) <= 12
    )


def _ascii_preview(data: bytes, limit: int = 64) -> str:
    return "".join(chr(value) if 32 <= value < 127 else "." for value in data[:limit])


def _decode_authoritative(payload: bytes) -> tuple[list[int], list[str]]:
    """Decode every valid block without treating flag 0x07 as a hard stop."""
    errors: list[str] = []
    samples: list[int] = []
    hist1 = 0
    hist2 = 0
    for position in range(0, len(payload) - 15, BLOCK_SIZE):
        block = payload[position : position + BLOCK_SIZE]
        predictor = block[0] >> 4
        shift = block[0] & 0x0F
        if predictor >= len(_COEFS):
            errors.append(f"invalid predictor {predictor} at block {position // BLOCK_SIZE}")
            continue
        if shift > 12:
            errors.append(f"invalid shift {shift} at block {position // BLOCK_SIZE}")
            continue
        coef1, coef2 = _COEFS[predictor]
        for value in block[2:]:
            for nibble in (value & 0x0F, value >> 4):
                signed = nibble - 16 if nibble >= 8 else nibble
                sample = (signed << 12) >> shift
                sample += ((hist1 * coef1) + (hist2 * coef2) + 32) >> 6
                sample = max(-32768, min(32767, sample))
                samples.append(sample)
                hist2, hist1 = hist1, sample
    if not samples:
        errors.append("no PCM frames decoded")
    return samples, errors


def analyze_payload(payload: bytes) -> dict[str, Any]:
    blocks = [
        payload[position : position + BLOCK_SIZE]
        for position in range(0, len(payload), BLOCK_SIZE)
    ]
    invalid = [index for index, block in enumerate(blocks) if not _valid_block(block)]
    suffix_start = invalid[-1] + 1 if invalid else 0
    suffix = blocks[suffix_start:]
    suffix_clean = bool(suffix) and all(_valid_block(block) for block in suffix)
    suffix_blocks = len(suffix)
    if suffix_clean and suffix_blocks >= MIN_RECOVERABLE_BLOCKS:
        role = "recoverable_suffix_audio_candidate"
    elif suffix_clean and suffix_blocks:
        role = "short_valid_suffix_candidate"
    else:
        role = "no_valid_suffix"

    flag_counts = Counter(block[1] for block in suffix if len(block) == BLOCK_SIZE)
    candidate = b"".join(suffix) if suffix_clean else b""
    return {
        "candidate_role": role,
        "payload_block_count": len(blocks),
        "invalid_block_count": len(invalid),
        "first_invalid_block": invalid[0] if invalid else None,
        "last_invalid_block": invalid[-1] if invalid else None,
        "prefix_region_blocks": suffix_start,
        "prefix_region_bytes": suffix_start * BLOCK_SIZE,
        "candidate_start_block": suffix_start if suffix_clean else None,
        "candidate_start_byte": suffix_start * BLOCK_SIZE if suffix_clean else None,
        "candidate_block_count": suffix_blocks if suffix_clean else 0,
        "candidate_encoded_size": len(candidate),
        "candidate_frame_capacity": suffix_blocks * 28 if suffix_clean else 0,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest() if candidate else None,
        "candidate_flag_counts": {
            f"0x{flag:02X}": count for flag, count in sorted(flag_counts.items())
        },
        "prefix_hex": payload[:64].hex(" "),
        "prefix_ascii": _ascii_preview(payload),
        "candidate_first_block_hex": candidate[:BLOCK_SIZE].hex(" ") if candidate else None,
        "_candidate_bytes": candidate,
    }


def probe_report(report_path: Path, output: Path) -> dict[str, Any]:
    report_path = report_path.expanduser().resolve()
    setup = audit_setup(report_path)
    source_path = Path(str(setup["snddata_source"])).expanduser().resolve()
    source = source_path.read_bytes()

    raw_dir = output / "candidate_psadpcm"
    wav_dir = output / "candidate_wav"
    raw_dir.mkdir(parents=True, exist_ok=True)
    wav_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    index_counts: Counter[int] = Counter()

    for row in setup.get("rows") or []:
        if row.get("catalog_role") == "clean_audio_candidate":
            continue
        source_offset = _int(row.get("source_offset"))
        raw_size = _int(row.get("raw_span_size"))
        if (
            source_offset is None
            or raw_size is None
            or raw_size <= 0
            or not 0 <= source_offset <= len(source) - raw_size
        ):
            analysis = {
                "candidate_role": "invalid_source_span",
                "_candidate_bytes": b"",
            }
        else:
            raw = source[source_offset : source_offset + raw_size]
            encoded, _trim = trim_stream(raw)
            analysis = analyze_payload(encoded)

        candidate = analysis.pop("_candidate_bytes", b"")
        bank = _int(row.get("bank_ordinal"))
        sample = _int(row.get("sample_index"))
        flat = _int(row.get("flat_index"))
        stem = f"bank_{bank:03d}_sample_{sample:03d}_flat_{flat:04d}"

        candidate_raw_path: str | None = None
        candidate_wav_path: str | None = None
        stop_frames: int | None = None
        stop_errors: list[str] = []
        authoritative_frames: int | None = None
        authoritative_errors: list[str] = []
        if candidate:
            raw_path = raw_dir / f"{stem}.psadpcm"
            raw_path.write_bytes(candidate)
            candidate_raw_path = str(raw_path)
            stop_pcm, stop_errors = decode_ps_adpcm_blocks(candidate)
            stop_frames = len(stop_pcm)
            authoritative_pcm, authoritative_errors = _decode_authoritative(candidate)
            authoritative_frames = len(authoritative_pcm)
            rate = _int(row.get("sample_rate"))
            if rate and authoritative_pcm and not authoritative_errors:
                wav_path = wav_dir / f"{stem}.wav"
                write_pcm_wav(wav_path, authoritative_pcm, rate, 1)
                candidate_wav_path = str(wav_path)

        out_row = {
            "bank_ordinal": bank,
            "sample_index": sample,
            "flat_index": flat,
            "sample_rate": _int(row.get("sample_rate")),
            "authoritative_source_offset": source_offset,
            "authoritative_raw_span_size": raw_size,
            "authoritative_encoded_payload_size": _int(row.get("encoded_payload_size")),
            "original_catalog_role": row.get("catalog_role"),
            **analysis,
            "stop_policy_frame_count": stop_frames,
            "stop_policy_errors": stop_errors,
            "authoritative_policy_frame_count": authoritative_frames,
            "authoritative_policy_errors": authoritative_errors,
            "candidate_raw_path": candidate_raw_path,
            "candidate_wav_path": candidate_wav_path,
        }
        rows.append(out_row)
        role_counts[str(out_row["candidate_role"])] += 1
        if sample is not None:
            index_counts[sample] += 1

    return {
        "version": 1,
        "fragmenter_report": str(report_path),
        "snddata_source": str(source_path),
        "source_sha256_matches": setup.get("source_sha256_matches"),
        "structural_gate": setup.get("structural_gate"),
        "size_gate": setup.get("size_gate"),
        "setup_classification_gate": setup.get("classification_gate"),
        "probe_policy": {
            "authoritative_span": "Preserved exactly from SCEIVagi and the v3 trim report.",
            "candidate_boundary": "First block after the final invalid predictor/shift block.",
            "candidate_minimum_blocks": MIN_RECOVERABLE_BLOCKS,
            "decoder": "Diagnostic WAV decodes the full clean suffix and does not stop on flag 0x07.",
            "classification": "Candidates remain provisional until listening or PCM identity confirms them.",
        },
        "summary": {
            "unresolved_rows": len(rows),
            "candidate_role_counts": dict(role_counts),
            "sample_index_counts": {
                str(index): count for index, count in sorted(index_counts.items())
            },
            "candidate_wav_count": sum(bool(row.get("candidate_wav_path")) for row in rows),
        },
        "rows": rows,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = (
        "bank_ordinal",
        "sample_index",
        "flat_index",
        "sample_rate",
        "original_catalog_role",
        "candidate_role",
        "authoritative_source_offset",
        "authoritative_raw_span_size",
        "authoritative_encoded_payload_size",
        "payload_block_count",
        "invalid_block_count",
        "first_invalid_block",
        "last_invalid_block",
        "prefix_region_blocks",
        "prefix_region_bytes",
        "candidate_start_block",
        "candidate_start_byte",
        "candidate_block_count",
        "candidate_encoded_size",
        "candidate_frame_capacity",
        "stop_policy_frame_count",
        "authoritative_policy_frame_count",
        "candidate_sha256",
        "candidate_raw_path",
        "candidate_wav_path",
        "prefix_ascii",
        "prefix_hex",
        "candidate_first_block_hex",
        "candidate_flag_counts",
        "stop_policy_errors",
        "authoritative_policy_errors",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writable = dict(row)
            for key in (
                "candidate_flag_counts",
                "stop_policy_errors",
                "authoritative_policy_errors",
            ):
                writable[key] = json.dumps(writable.get(key), sort_keys=True)
            writer.writerow({field: writable.get(field) for field in fields})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("search_root", nargs="?", default=str(Path.cwd().parent))
    parser.add_argument("--fragmenter-report")
    parser.add_argument(
        "--output",
        default=str(Path.cwd() / "diagnostics" / "snddata_unresolved_suffix"),
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

    payload = probe_report(report_path, output)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(csv_path, payload["rows"])

    summary = payload["summary"]
    print(f"Fragmenter report: {report_path}")
    print(f"Structural gate: {payload['structural_gate']}")
    print(f"Size gate: {payload['size_gate']}")
    print(f"Unresolved rows: {summary['unresolved_rows']}")
    print(f"Candidate roles: {summary['candidate_role_counts']}")
    print(f"Candidate WAVs: {summary['candidate_wav_count']}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0 if payload["structural_gate"] == "pass" and payload["size_gate"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

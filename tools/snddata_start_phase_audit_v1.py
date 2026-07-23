#!/usr/bin/env python3
"""Audit SNDDATA sample-start phase against PSound PCM identity.

The wrapper-placement probe established that removing 32 bytes only from the
reported span cannot reproduce later-bank PSound starts. This probe tests the
upstream boundary hypothesis instead. For each monotonic raw-span anchor it
compares the current corrected start, the original logical SCEIVagi start, and
small aligned neighbours. Each start is tested with both terminal-flag and
source-span decoding semantics. No extraction files are modified.
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
import wave
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import audio_decoder
from psound_pcm_identity_v1 import PREFIX_FRAMES, _trend_hash
from snddata_wrapper_placement_audit_v1 import _load_json, _optional_int, _psound_paths

BLOCK_SIZE = 16
MAX_PREFIX_FRAMES = max(PREFIX_FRAMES)
METHOD_RANK = {"none": 0, "pcm_trend_prefix": 1, "exact_pcm_prefix": 2}


def _resolve_path(value: Any, base: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    candidates = [path]
    if not path.is_absolute():
        candidates.extend((base / path, base.parent / path))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved.is_file():
            return resolved
    return None


def _read_psound_prefix(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        if handle.getcomptype() != "NONE" or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise wave.Error(f"Expected mono 16-bit PCM WAV: {path}")
        return handle.readframes(MAX_PREFIX_FRAMES)


def _decode_prefix(payload: bytes, *, stop_on_flag_07: bool) -> tuple[bytes, list[str]]:
    errors: list[str] = []
    samples: list[int] = []
    hist1 = 0
    hist2 = 0
    coefficients = audio_decoder._VAG_COEFS
    for pos in range(0, len(payload) - 15, BLOCK_SIZE):
        block = payload[pos : pos + BLOCK_SIZE]
        predictor = block[0] >> 4
        shift = block[0] & 0x0F
        flags = block[1]
        if predictor >= len(coefficients):
            errors.append(f"invalid predictor {predictor} at +0x{pos:X}")
            continue
        if shift > 12:
            errors.append(f"invalid shift {shift} at +0x{pos:X}")
            continue
        if stop_on_flag_07 and flags == 0x07:
            break
        coef1, coef2 = coefficients[predictor]
        for encoded in block[2:]:
            for nibble in (encoded & 0x0F, encoded >> 4):
                signed = nibble - 16 if nibble >= 8 else nibble
                sample = (signed << 12) >> shift
                sample += ((hist1 * coef1) + (hist2 * coef2) + 32) >> 6
                sample = max(-32768, min(32767, sample))
                samples.append(sample)
                hist2, hist1 = hist1, sample
                if len(samples) >= MAX_PREFIX_FRAMES:
                    return struct.pack("<" + "h" * len(samples), *samples), errors
    if not samples:
        errors.append("no decodable PS ADPCM frames")
        return b"", errors
    return struct.pack("<" + "h" * len(samples), *samples), errors


def _match_prefix(candidate: bytes, target: bytes) -> tuple[str, int | None]:
    for frames in PREFIX_FRAMES:
        size = frames * 2
        if len(candidate) >= size and len(target) >= size and candidate[:size] == target[:size]:
            return "exact_pcm_prefix", frames
    for frames in PREFIX_FRAMES:
        size = frames * 2
        if len(candidate) < size or len(target) < size:
            continue
        left = _trend_hash(candidate[:size], 1, 2, frames)
        right = _trend_hash(target[:size], 1, 2, frames)
        if left and left == right:
            return "pcm_trend_prefix", frames
    return "none", None


def _report_context(report_path: Path) -> tuple[Path, bytes, dict[int, dict[str, Any]]]:
    report = _load_json(report_path)
    if not isinstance(report, dict):
        raise ValueError(f"Fragmenter report must contain an object: {report_path}")
    source_path = _resolve_path(report.get("source"), report_path.parent)
    if source_path is None:
        raise FileNotFoundError(f"SNDDATA source recorded by report is unavailable: {report.get('source')}")
    selected: dict[int, dict[str, Any]] = {}
    for row in report.get("samples") or []:
        if not isinstance(row, dict):
            continue
        flat_index = _optional_int(row.get("flat_index"))
        source_offset = _optional_int(row.get("source_offset"))
        if flat_index is None or source_offset is None:
            continue
        current = selected.get(flat_index)
        if current is None or (
            current.get("logical_stream_offset") is None
            and row.get("logical_stream_offset") is not None
        ):
            selected[flat_index] = dict(row)
    return source_path, source_path.read_bytes(), selected


def _candidate_starts(row: dict[str, Any]) -> list[dict[str, Any]]:
    current = _optional_int(row.get("source_offset"))
    body_base = _optional_int(row.get("body_base"))
    logical = _optional_int(row.get("logical_stream_offset"))
    starts: list[tuple[str, int]] = []
    if current is not None:
        starts.extend(
            [
                ("current_corrected", current),
                ("current_minus_32", current - 32),
                ("current_minus_16", current - 16),
                ("current_plus_16", current + 16),
                ("current_plus_32", current + 32),
            ]
        )
    if body_base is not None and logical is not None:
        logical_absolute = body_base + logical
        starts.extend(
            [
                ("logical_declared", logical_absolute),
                ("logical_minus_32", logical_absolute - 32),
                ("logical_minus_16", logical_absolute - 16),
                ("logical_plus_16", logical_absolute + 16),
                ("logical_plus_32", logical_absolute + 32),
            ]
        )
    unique: dict[int, str] = {}
    aliases: defaultdict[int, list[str]] = defaultdict(list)
    for name, offset in starts:
        if offset < 0:
            continue
        unique.setdefault(offset, name)
        aliases[offset].append(name)
    return [
        {"model": unique[offset], "aliases": aliases[offset], "absolute_offset": offset}
        for offset in sorted(unique)
    ]


def classify_start_phase(
    source: bytes,
    row: dict[str, Any],
    psound_pcm: bytes,
    encoded_payload_bytes: int,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    prefix_bytes = min(
        encoded_payload_bytes,
        ((MAX_PREFIX_FRAMES + 27) // 28 + 2) * BLOCK_SIZE,
    )
    for start in _candidate_starts(row):
        absolute = int(start["absolute_offset"])
        payload = source[absolute : absolute + prefix_bytes]
        payload = payload[: len(payload) - (len(payload) % BLOCK_SIZE)]
        for stop_on_flag_07 in (True, False):
            pcm, errors = _decode_prefix(payload, stop_on_flag_07=stop_on_flag_07)
            method, frames = _match_prefix(pcm, psound_pcm)
            score = (
                METHOD_RANK[method],
                int(frames or 0),
                -len(errors),
            )
            candidates.append(
                {
                    **start,
                    "decoder_policy": (
                        "stop_on_flag_07" if stop_on_flag_07 else "decode_authoritative_span"
                    ),
                    "payload_prefix_bytes": len(payload),
                    "decoded_prefix_frames": len(pcm) // 2,
                    "decode_error_count": len(errors),
                    "decode_errors": errors[:20],
                    "match_method": method,
                    "matched_prefix_frames": frames,
                    "score": list(score),
                }
            )
    best_score = max((tuple(item["score"]) for item in candidates), default=(0, 0, 0))
    best = [item for item in candidates if tuple(item["score"]) == best_score]
    if best_score[0] <= 0:
        status = "no_pcm_match"
        selected_model = None
        selected_policy = None
    else:
        distinct = {
            (int(item["absolute_offset"]), str(item["decoder_policy"]))
            for item in best
        }
        if len(distinct) == 1:
            status = "unique_best_phase"
            selected_model = str(best[0]["model"])
            selected_policy = str(best[0]["decoder_policy"])
        else:
            status = "ambiguous_best_phase"
            selected_model = None
            selected_policy = None
    return {
        "status": status,
        "selected_model": selected_model,
        "selected_decoder_policy": selected_policy,
        "best_score": list(best_score),
        "best_candidates": [
            {
                "model": item["model"],
                "aliases": item["aliases"],
                "absolute_offset": item["absolute_offset"],
                "decoder_policy": item["decoder_policy"],
            }
            for item in best
        ],
        "candidates": candidates,
    }


def audit(raw_audit_path: Path, manifest_path: Path) -> dict[str, Any]:
    raw_audit = _load_json(raw_audit_path)
    manifest = _load_json(manifest_path)
    if not isinstance(raw_audit, dict) or not isinstance(manifest, dict):
        raise ValueError("Raw-span audit and PSound manifest must contain JSON objects")
    report_text = str(manifest.get("fragmenter_report") or "").strip()
    if not report_text:
        raise ValueError(f"Manifest does not identify its Fragmenter report: {manifest_path}")
    report_path = Path(report_text).expanduser().resolve()
    source_path, source, report_rows = _report_context(report_path)
    psound_paths = _psound_paths(manifest, manifest_path)

    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    policy_counts: Counter[str] = Counter()
    relation_status: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for anchor in raw_audit.get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        p_index = _optional_int(anchor.get("psound_sequence_number"))
        f_index = _optional_int(anchor.get("fragmenter_flat_index"))
        p_size = _optional_int(anchor.get("psound_encoded_payload_bytes"))
        if p_index is None or f_index is None or p_size is None:
            continue
        report_row = report_rows.get(f_index)
        psound_path = psound_paths.get(p_index)
        relation = str(anchor.get("payload_relation") or "unknown")
        if report_row is None or psound_path is None:
            status = "missing_local_source"
            result = {
                "status": status,
                "selected_model": None,
                "selected_decoder_policy": None,
                "best_score": [0, 0, 0],
                "best_candidates": [],
                "candidates": [],
            }
        else:
            result = classify_start_phase(
                source,
                report_row,
                _read_psound_prefix(psound_path),
                p_size,
            )
            status = str(result["status"])
        status_counts[status] += 1
        relation_status[relation][status] += 1
        if result.get("selected_model"):
            model_counts[str(result["selected_model"])] += 1
        if result.get("selected_decoder_policy"):
            policy_counts[str(result["selected_decoder_policy"])] += 1
        rows.append(
            {
                **anchor,
                "status": status,
                "selected_model": result.get("selected_model"),
                "selected_decoder_policy": result.get("selected_decoder_policy"),
                "best_score": result.get("best_score"),
                "best_candidates": result.get("best_candidates"),
                "stream_boundary_mode": (report_row or {}).get("stream_boundary_mode"),
                "stream_boundary_shift": (report_row or {}).get("stream_boundary_shift"),
                "source_offset": (report_row or {}).get("source_offset"),
                "body_base": (report_row or {}).get("body_base"),
                "logical_stream_offset": (report_row or {}).get("logical_stream_offset"),
                "physical_stream_offset": (report_row or {}).get("physical_stream_offset"),
                "psound_path": str(psound_path or ""),
                "candidates": result.get("candidates"),
            }
        )

    return {
        "version": 1,
        "fragmenter_report": str(report_path),
        "snddata_source": str(source_path),
        "raw_span_audit": str(raw_audit_path),
        "psound_manifest": str(manifest_path),
        "anchor_count": len(rows),
        "status_counts": dict(status_counts),
        "selected_model_counts": dict(model_counts),
        "selected_decoder_policy_counts": dict(policy_counts),
        "relation_status_counts": {
            relation: dict(counts) for relation, counts in relation_status.items()
        },
        "interpretation": {
            "current_corrected": "The currently extracted physical start reproduces PSound.",
            "logical_declared": "The uncorrected SCEIVagi logical start reproduces PSound; the separator correction is suspect.",
            "neighbour": "A nearby aligned start reproduces PSound and identifies the remaining phase error.",
            "no_pcm_match": "None of the tested logical/current aligned phases reproduced PSound; expand the search or revisit the length-only pairing.",
            "scope": "Evidence-only audit. It does not modify extraction or claim authentic replacement serialization.",
        },
        "rows": rows,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = (
        "psound_sequence_number",
        "fragmenter_flat_index",
        "fragmenter_bank_ordinal",
        "fragmenter_sample_id",
        "payload_relation",
        "status",
        "selected_model",
        "selected_decoder_policy",
        "stream_boundary_mode",
        "stream_boundary_shift",
        "source_offset",
        "body_base",
        "logical_stream_offset",
        "physical_stream_offset",
        "best_score",
        "best_candidates",
        "psound_path",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writable = dict(row)
            for key in ("best_score", "best_candidates"):
                writable[key] = json.dumps(writable.get(key), sort_keys=True)
            writer.writerow({field: writable.get(field) for field in fields})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_span_audit")
    parser.add_argument("psound_manifest")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    raw_path = Path(args.raw_span_audit).expanduser().resolve()
    manifest_path = Path(args.psound_manifest).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else raw_path.parent
    payload = audit(raw_path, manifest_path)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "snddata_start_phase_audit.json"
    csv_path = output / "snddata_start_phase_audit.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, payload["rows"])

    print("SNDDATA start-phase audit:")
    print(f"  Anchors tested: {payload['anchor_count']}")
    print(f"  Status: {payload['status_counts']}")
    print(f"  Selected starts: {payload['selected_model_counts']}")
    print(f"  Decoder policies: {payload['selected_decoder_policy_counts']}")
    print(f"  Relation/status: {payload['relation_status_counts']}")
    print(f"  Audit JSON: {json_path}")
    print(f"  Audit CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Determine where the two structural PS-ADPCM blocks sit in wrapper-retaining spans.

The raw-span oracle proves that many Fragmenter SCEIVagi spans are exactly 32 bytes
longer than the block count PSound decoded. This probe does not assume those bytes
are always a leading wrapper. For each monotonic wrapper anchor it tests three
32-byte removal placements: leading 32, split 16+16, and trailing 32. Candidate
payloads are decoded and compared with the corresponding PSound PCM prefix.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import wave
from collections import Counter
from pathlib import Path
from typing import Any

import audio_decoder
from psound_pcm_identity_v1 import PREFIX_FRAMES, _trend_hash

BLOCK_SIZE = 16
PLACEMENTS: dict[str, tuple[int, int]] = {
    "leading_32": (32, 0),
    "split_16_16": (16, 16),
    "trailing_32": (0, 32),
}
METHOD_RANK = {
    "none": 0,
    "pcm_trend_prefix": 1,
    "exact_pcm_prefix": 2,
    "exact_full_pcm": 3,
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
    candidates = [path]
    if not path.is_absolute():
        candidates.extend((report_path.parent / path, report_path.parent.parent / path))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved.is_file():
            return resolved
    return None


def _report_rows(report_path: Path) -> dict[int, dict[str, Any]]:
    payload = _load_json(report_path)
    rows = payload.get("samples") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"Fragmenter report has no sample rows: {report_path}")
    selected: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        flat_index = _optional_int(row.get("flat_index"))
        if flat_index is None:
            continue
        raw_path = _resolve_path(row.get("raw_path"), report_path)
        if raw_path is None:
            continue
        selected.setdefault(flat_index, {**row, "resolved_raw_path": str(raw_path)})
    return selected


def _psound_paths(manifest: dict[str, Any], manifest_path: Path) -> dict[int, Path]:
    source_root_text = str(manifest.get("source_root") or "").strip()
    source_root = Path(source_root_text).expanduser() if source_root_text else manifest_path.parent
    output: dict[int, Path] = {}
    for row in manifest.get("files") or []:
        if not isinstance(row, dict):
            continue
        index = _optional_int(row.get("psound_sequence_number"))
        relative = str(row.get("relative_path") or "").strip()
        if index is None or not relative:
            continue
        path = Path(relative)
        if not path.is_absolute():
            path = source_root / path
        try:
            path = path.resolve()
        except OSError:
            pass
        if path.is_file():
            output[index] = path
    return output


def _read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        if handle.getcomptype() != "NONE" or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise wave.Error(f"Expected mono 16-bit PCM WAV: {path}")
        return handle.readframes(handle.getnframes())


def _decode_pcm(payload: bytes) -> tuple[bytes, list[str]]:
    samples, errors = audio_decoder.decode_ps_adpcm_blocks(payload)
    if not samples:
        return b"", list(errors)
    return struct.pack("<" + "h" * len(samples), *samples), list(errors)


def _match_pcm(candidate: bytes, target: bytes) -> dict[str, Any]:
    if candidate and candidate == target:
        return {"method": "exact_full_pcm", "matched_prefix_frames": len(target) // 2}
    for frames in PREFIX_FRAMES:
        size = frames * 2
        if len(candidate) >= size and len(target) >= size and candidate[:size] == target[:size]:
            return {"method": "exact_pcm_prefix", "matched_prefix_frames": frames}
    for frames in PREFIX_FRAMES:
        size = frames * 2
        if len(candidate) < size or len(target) < size:
            continue
        left = _trend_hash(candidate[:size], 1, 2, frames)
        right = _trend_hash(target[:size], 1, 2, frames)
        if left and left == right:
            return {"method": "pcm_trend_prefix", "matched_prefix_frames": frames}
    return {"method": "none", "matched_prefix_frames": None}


def classify_wrapper_placement(raw: bytes, psound_pcm: bytes) -> dict[str, Any]:
    """Score all supported 32-byte placements against one PSound PCM target."""
    candidates: list[dict[str, Any]] = []
    for name, (leading, trailing) in PLACEMENTS.items():
        end = len(raw) - trailing if trailing else len(raw)
        payload = raw[leading:end] if end >= leading else b""
        payload = payload[: len(payload) - (len(payload) % BLOCK_SIZE)]
        pcm, errors = _decode_pcm(payload)
        match = _match_pcm(pcm, psound_pcm)
        frames = int(match.get("matched_prefix_frames") or 0)
        score = (METHOD_RANK[str(match["method"])], frames, -len(errors))
        candidates.append({
            "placement": name,
            "leading_trim_bytes": leading,
            "trailing_trim_bytes": trailing,
            "payload_size": len(payload),
            "decoded_frames": len(pcm) // 2,
            "decode_errors": errors,
            "match_method": match["method"],
            "matched_prefix_frames": match["matched_prefix_frames"],
            "score": list(score),
        })

    best_score = max((tuple(row["score"]) for row in candidates), default=(0, 0, 0))
    best = [row for row in candidates if tuple(row["score"]) == best_score]
    if best_score[0] <= 0:
        status = "no_pcm_match"
        selected = None
    elif len(best) == 1:
        status = "unique_best_placement"
        selected = str(best[0]["placement"])
    else:
        status = "ambiguous_best_placement"
        selected = None
    return {
        "status": status,
        "selected_placement": selected,
        "best_score": list(best_score),
        "best_placements": [str(row["placement"]) for row in best],
        "candidates": candidates,
    }


def _signature_summary(counter: Counter[str], samples: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"sha256": digest, "count": count, "hex": samples.get(digest)}
        for digest, count in counter.most_common(20)
    ]


def audit(raw_audit_path: Path, manifest_path: Path) -> dict[str, Any]:
    raw_audit = _load_json(raw_audit_path)
    manifest = _load_json(manifest_path)
    if not isinstance(raw_audit, dict) or not isinstance(manifest, dict):
        raise ValueError("Raw-span audit and PSound manifest must both contain JSON objects")
    report_text = str(manifest.get("fragmenter_report") or "").strip()
    if not report_text:
        raise ValueError(f"Manifest does not identify its Fragmenter report: {manifest_path}")
    report_path = Path(report_text).expanduser().resolve()
    if not report_path.is_file():
        raise FileNotFoundError(report_path)

    fragmenter_rows = _report_rows(report_path)
    psound_paths = _psound_paths(manifest, manifest_path)
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    placement_counts: Counter[str] = Counter()
    prefix_counts: Counter[str] = Counter()
    suffix_counts: Counter[str] = Counter()
    prefix_samples: dict[str, str] = {}
    suffix_samples: dict[str, str] = {}

    for anchor in raw_audit.get("anchors") or []:
        if not isinstance(anchor, dict) or anchor.get("payload_relation") not in {
            "payload_retains_32_byte_wrapper",
            "payload_overlong_other",
        }:
            continue
        p_index = _optional_int(anchor.get("psound_sequence_number"))
        f_index = _optional_int(anchor.get("fragmenter_flat_index"))
        if p_index is None or f_index is None:
            continue
        fragmenter = fragmenter_rows.get(f_index)
        psound_path = psound_paths.get(p_index)
        if fragmenter is None or psound_path is None:
            rows.append({
                **anchor,
                "status": "missing_local_source",
                "selected_placement": None,
                "raw_path": str((fragmenter or {}).get("resolved_raw_path") or ""),
                "psound_path": str(psound_path or ""),
            })
            status_counts["missing_local_source"] += 1
            continue

        raw_path = Path(str(fragmenter["resolved_raw_path"]))
        raw = raw_path.read_bytes()
        psound_pcm = _read_pcm(psound_path)
        classification = classify_wrapper_placement(raw, psound_pcm)
        prefix = raw[:32]
        suffix = raw[-32:] if len(raw) >= 32 else raw
        prefix_digest = hashlib.sha256(prefix).hexdigest()
        suffix_digest = hashlib.sha256(suffix).hexdigest()
        prefix_counts[prefix_digest] += 1
        suffix_counts[suffix_digest] += 1
        prefix_samples.setdefault(prefix_digest, prefix.hex())
        suffix_samples.setdefault(suffix_digest, suffix.hex())
        status = str(classification["status"])
        selected = classification.get("selected_placement")
        status_counts[status] += 1
        if selected:
            placement_counts[str(selected)] += 1
        rows.append({
            **anchor,
            "status": status,
            "selected_placement": selected,
            "best_placements": classification["best_placements"],
            "best_score": classification["best_score"],
            "raw_path": str(raw_path),
            "psound_path": str(psound_path),
            "raw_prefix_32_hex": prefix.hex(),
            "raw_suffix_32_hex": suffix.hex(),
            "candidates": classification["candidates"],
        })

    return {
        "version": 1,
        "fragmenter_report": str(report_path),
        "raw_span_audit": str(raw_audit_path),
        "psound_manifest": str(manifest_path),
        "candidate_trim_total_bytes": 32,
        "placements_tested": {
            name: {"leading_trim_bytes": leading, "trailing_trim_bytes": trailing}
            for name, (leading, trailing) in PLACEMENTS.items()
        },
        "eligible_anchor_count": len(rows),
        "status_counts": dict(status_counts),
        "selected_placement_counts": dict(placement_counts),
        "top_raw_prefix_32_signatures": _signature_summary(prefix_counts, prefix_samples),
        "top_raw_suffix_32_signatures": _signature_summary(suffix_counts, suffix_samples),
        "interpretation": {
            "unique_best_placement": "One 32-byte placement reproduced the PSound PCM start more strongly than the alternatives.",
            "ambiguous_best_placement": "Multiple placements scored equally; do not modify extraction from this row alone.",
            "no_pcm_match": "None of the three placements reproduced the PSound PCM start with the current decoder.",
            "scope": "This is an evidence probe. It does not alter extracted payloads or claim a universal wrapper rule.",
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
        "selected_placement",
        "best_placements",
        "best_score",
        "raw_path",
        "psound_path",
        "raw_prefix_32_hex",
        "raw_suffix_32_hex",
        "candidates",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writable = dict(row)
            for key in ("best_placements", "best_score", "candidates"):
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
    json_path = output / "snddata_wrapper_placement_audit.json"
    csv_path = output / "snddata_wrapper_placement_audit.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, payload["rows"])

    print("SNDDATA wrapper-placement audit:")
    print(f"  Eligible wrapper/overlong anchors: {payload['eligible_anchor_count']}")
    print(f"  Status: {payload['status_counts']}")
    print(f"  Selected placements: {payload['selected_placement_counts']}")
    print(f"  Audit JSON: {json_path}")
    print(f"  Audit CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

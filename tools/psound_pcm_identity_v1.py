#!/usr/bin/env python3
"""Map PSound WAVs to Fragmenter WAVs by decoded PCM content, ignoring WAV sample-rate headers."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import wave
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from compare_psound_to_latest_fragmenter_v1 import find_latest_fragmenter_report

PSOUND_RE = re.compile(r"^SNDDATA_(\d+)\.WAV$", re.IGNORECASE)
PREFIX_FRAMES = (4096, 1024, 256, 64)


def _natural_key(text: str) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _trend_hash(raw: bytes, channels: int, sample_width: int, frames: int) -> str | None:
    if channels != 1 or sample_width != 2 or frames < 2:
        return None
    count = min(frames, len(raw) // 2)
    if count < 2:
        return None
    samples = struct.unpack("<" + "h" * count, raw[: count * 2])
    encoded = bytearray()
    previous = samples[0]
    for value in samples[1:]:
        delta = value - previous
        if delta > 2:
            encoded.append(2)
        elif delta < -2:
            encoded.append(0)
        else:
            encoded.append(1)
        previous = value
    return _sha256(bytes(encoded))


def wav_signature(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frame_count = handle.getnframes()
        sample_rate = handle.getframerate()
        compression = handle.getcomptype()
        if compression != "NONE":
            raise wave.Error(f"Compressed WAV is unsupported: {path} ({compression})")
        raw = handle.readframes(frame_count)
    bytes_per_frame = channels * sample_width
    result: dict[str, Any] = {
        "path": str(path),
        "channels": channels,
        "sample_width_bytes": sample_width,
        "frame_count": frame_count,
        "sample_rate": sample_rate,
        "pcm_size_bytes": len(raw),
        "full_pcm_sha256": _sha256(raw),
        "prefixes": {},
        "trends": {},
    }
    for frames in PREFIX_FRAMES:
        if frame_count < frames:
            continue
        prefix = raw[: frames * bytes_per_frame]
        result["prefixes"][str(frames)] = _sha256(prefix)
        trend = _trend_hash(prefix, channels, sample_width, frames)
        if trend:
            result["trends"][str(frames)] = trend
    return result


def _resolve_wav_path(row: dict[str, Any], report_path: Path) -> Path | None:
    candidates: list[Path] = []
    for field in ("flat_output_path", "wav_path", "output_path"):
        value = str(row.get(field) or "").strip()
        if not value:
            continue
        path = Path(value).expanduser()
        candidates.append(path)
        if not path.is_absolute():
            candidates.append(report_path.parent / path)
            candidates.append(report_path.parent.parent / path)
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved.is_file() and resolved.suffix.casefold() in {".wav", ".wave"}:
            return resolved
    return None


def load_fragmenter_wavs(report_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    source_rows = payload.get("flat_catalog") if isinstance(payload, dict) else None
    if not isinstance(source_rows, list) or not source_rows:
        source_rows = payload.get("samples") if isinstance(payload, dict) else None
    if not isinstance(source_rows, list):
        raise ValueError(f"Fragmenter report has no sample rows: {report_path}")

    selected: dict[int, dict[str, Any]] = {}
    unresolved: list[int] = []
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        flat_index = _optional_int(row.get("flat_index"))
        if flat_index is None or flat_index in selected:
            continue
        wav_path = _resolve_wav_path(row, report_path)
        if wav_path is None:
            unresolved.append(flat_index)
            continue
        selected[flat_index] = {
            "flat_index": flat_index,
            "bank_ordinal": _optional_int(row.get("bank_ordinal")),
            "sample_id": _optional_int(
                row.get("index")
                if row.get("index") is not None
                else row.get("sample_id")
                if row.get("sample_id") is not None
                else row.get("local_sample_index")
            ),
            "payload_size": _optional_int(row.get("payload_size") or row.get("source_span_size")),
            "wav_path": str(wav_path),
        }
    rows = [selected[index] for index in sorted(selected)]
    return rows, {
        "source_row_count": len(source_rows),
        "resolved_unique_flat_wavs": len(rows),
        "unresolved_unique_flat_indices": sorted(set(unresolved)),
    }


def load_psound_wavs(source: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(source.rglob("*.wav"), key=lambda item: _natural_key(item.relative_to(source).as_posix())):
        match = PSOUND_RE.fullmatch(path.name)
        if not match:
            continue
        rows.append({
            "psound_sequence_number": int(match.group(1)),
            "wav_path": str(path.resolve()),
        })
    return rows


def _append_index(index: dict[tuple[Any, ...], list[int]], key: tuple[Any, ...], flat_index: int) -> None:
    index.setdefault(key, []).append(flat_index)


def map_pcm_identity(psound_source: Path, report_path: Path, output: Path) -> dict[str, Any]:
    psound_rows = load_psound_wavs(psound_source)
    fragmenter_rows, resolution = load_fragmenter_wavs(report_path)
    if not psound_rows:
        raise FileNotFoundError(f"No numbered PSound WAVs found under: {psound_source}")
    if not fragmenter_rows:
        raise FileNotFoundError(
            f"No Fragmenter WAV paths from the report exist on this machine: {report_path}"
        )

    full_index: dict[tuple[Any, ...], list[int]] = {}
    prefix_index: dict[tuple[Any, ...], list[int]] = {}
    trend_index: dict[tuple[Any, ...], list[int]] = {}
    fragmenter_signatures: dict[int, dict[str, Any]] = {}
    signature_errors: list[dict[str, Any]] = []

    for row in fragmenter_rows:
        flat_index = int(row["flat_index"])
        path = Path(row["wav_path"])
        try:
            signature = wav_signature(path)
        except (OSError, EOFError, wave.Error) as exc:
            signature_errors.append({"side": "fragmenter", "flat_index": flat_index, "path": str(path), "error": str(exc)})
            continue
        fragmenter_signatures[flat_index] = signature
        shape = (signature["channels"], signature["sample_width_bytes"])
        _append_index(full_index, shape + (signature["frame_count"], signature["full_pcm_sha256"]), flat_index)
        for frames_text, digest in signature["prefixes"].items():
            _append_index(prefix_index, shape + (int(frames_text), digest), flat_index)
        for frames_text, digest in signature["trends"].items():
            _append_index(trend_index, shape + (int(frames_text), digest), flat_index)

    mappings: list[dict[str, Any]] = []
    for row in psound_rows:
        number = int(row["psound_sequence_number"])
        path = Path(row["wav_path"])
        try:
            signature = wav_signature(path)
        except (OSError, EOFError, wave.Error) as exc:
            signature_errors.append({"side": "psound", "psound_sequence_number": number, "path": str(path), "error": str(exc)})
            continue
        shape = (signature["channels"], signature["sample_width_bytes"])
        exact = full_index.get(shape + (signature["frame_count"], signature["full_pcm_sha256"]), [])
        method = "none"
        candidates = list(exact)
        matched_prefix_frames: int | None = None
        if candidates:
            method = "exact_full_pcm"
        else:
            for frames in PREFIX_FRAMES:
                digest = signature["prefixes"].get(str(frames))
                if not digest:
                    continue
                hits = prefix_index.get(shape + (frames, digest), [])
                if hits:
                    candidates = list(hits)
                    method = "exact_pcm_prefix"
                    matched_prefix_frames = frames
                    break
        if not candidates:
            for frames in PREFIX_FRAMES:
                digest = signature["trends"].get(str(frames))
                if not digest:
                    continue
                hits = trend_index.get(shape + (frames, digest), [])
                if hits:
                    candidates = list(hits)
                    method = "pcm_trend_prefix"
                    matched_prefix_frames = frames
                    break

        confidence = "none"
        if method == "exact_full_pcm":
            confidence = "very_high_unique" if len(candidates) == 1 else "high_ambiguous_duplicate"
        elif method == "exact_pcm_prefix":
            confidence = "high_unique_start_identity" if len(candidates) == 1 else "medium_ambiguous_start"
        elif method == "pcm_trend_prefix":
            confidence = "medium_unique_shape" if len(candidates) == 1 else "low_ambiguous_shape"

        mappings.append({
            "psound_sequence_number": number,
            "psound_path": str(path),
            "psound_frames": signature["frame_count"],
            "psound_export_rate": signature["sample_rate"],
            "match_method": method,
            "match_confidence": confidence,
            "matched_prefix_frames": matched_prefix_frames,
            "fragmenter_candidate_count": len(candidates),
            "fragmenter_flat_candidates": candidates,
            "unique_fragmenter_flat_index": candidates[0] if len(candidates) == 1 else None,
        })

    method_counts = Counter(row["match_method"] for row in mappings)
    unique_counts = Counter(
        row["match_method"]
        for row in mappings
        if row.get("unique_fragmenter_flat_index") is not None
    )
    reverse: dict[int, list[int]] = defaultdict(list)
    for row in mappings:
        for flat_index in row["fragmenter_flat_candidates"]:
            reverse[int(flat_index)].append(int(row["psound_sequence_number"]))

    sample_228 = next((row for row in mappings if row["psound_sequence_number"] == 228), None)
    flat_228 = {
        "fragmenter_flat_index": 228,
        "psound_candidates": reverse.get(228, []),
        "fragmenter_signature_available": 228 in fragmenter_signatures,
    }

    payload = {
        "version": 1,
        "psound_source": str(psound_source),
        "fragmenter_report": str(report_path),
        "psound_numbered_wavs": len(psound_rows),
        "fragmenter_resolution": resolution,
        "fragmenter_signatures": len(fragmenter_signatures),
        "signature_errors": signature_errors,
        "match_method_counts": dict(method_counts),
        "unique_match_method_counts": dict(unique_counts),
        "sample_0228_psound_to_fragmenter": sample_228,
        "sample_0228_fragmenter_to_psound": flat_228,
        "interpretation": {
            "exact_full_pcm": "Decoded PCM is identical despite WAV-header sample-rate differences.",
            "exact_pcm_prefix": "The sample start is identical; differing total lengths are direct boundary evidence.",
            "pcm_trend_prefix": "Waveform shape strongly suggests the same start but requires manual or source-offset confirmation.",
            "none": "No PCM identity was established; do not compare lengths by numeric index.",
        },
        "mappings": mappings,
    }

    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "psound_fragmenter_pcm_identity.json"
    csv_path = output / "psound_fragmenter_pcm_identity.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = (
        "psound_sequence_number",
        "psound_path",
        "psound_frames",
        "psound_export_rate",
        "match_method",
        "match_confidence",
        "matched_prefix_frames",
        "fragmenter_candidate_count",
        "fragmenter_flat_candidates",
        "unique_fragmenter_flat_index",
    )
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in mappings:
            writable = dict(row)
            writable["fragmenter_flat_candidates"] = json.dumps(row["fragmenter_flat_candidates"])
            writer.writerow({field: writable.get(field) for field in fields})
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("psound_source", nargs="?", default=r"C:\games\areaserver\FragmentModKit\PSound201")
    parser.add_argument("search_root", nargs="?", default=str(Path.cwd().parent))
    parser.add_argument("--fragmenter-report")
    parser.add_argument("--output", default=str(Path.cwd() / "diagnostics" / "psound_reference"))
    args = parser.parse_args(argv)

    report = (
        Path(args.fragmenter_report).expanduser().resolve()
        if args.fragmenter_report
        else find_latest_fragmenter_report(args.search_root)
    )
    if not report.is_file():
        raise FileNotFoundError(f"Fragmenter report is not a file: {report}")
    source = Path(args.psound_source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    payload = map_pcm_identity(source, report, output)
    print(f"Fragmenter report: {report}")
    print(f"PSound WAVs: {payload['psound_numbered_wavs']}")
    print(f"Fragmenter WAV signatures: {payload['fragmenter_signatures']}")
    print(f"Match methods: {payload['match_method_counts']}")
    print(f"Unique matches: {payload['unique_match_method_counts']}")
    print(f"PSound 0228: {payload.get('sample_0228_psound_to_fragmenter')}")
    print(f"Fragmenter flat 0228: {payload.get('sample_0228_fragmenter_to_psound')}")
    print(f"PCM identity JSON: {output / 'psound_fragmenter_pcm_identity.json'}")
    print(f"PCM identity CSV: {output / 'psound_fragmenter_pcm_identity.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create an evidence-oriented manifest of a PSound extraction directory.

The manifest records exact file sizes and container-reported audio lengths. It can
optionally compare PSound's explicit SNDDATA_NNNNN numbering against Fragmenter's
canonical flat sample report. The numbering comparison remains an evidence-backed
hypothesis until source-span and waveform agreement are audited.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import sys
import wave
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

AUDIO_EXTENSIONS = {
    ".wav", ".wave", ".vag", ".vb", ".raw", ".pcm", ".adpcm", ".psadpcm",
    ".ss2", ".ads", ".adx", ".xa", ".xai",
}
PS_ADPCM_BLOCK = 16
PS_ADPCM_SAMPLES_PER_BLOCK = 28
PSOUND_NUMBER_RE = re.compile(r"^SNDDATA_(\d+)\.WAV$", re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _natural_key(text: str) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text))


def _riff_chunks(data: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if len(data) < 12 or data[:4] not in {b"RIFF", b"RIFX"} or data[8:12] != b"WAVE":
        return result
    endian = ">" if data[:4] == b"RIFX" else "<"
    result["riff_endian"] = "big" if endian == ">" else "little"
    result["riff_declared_size"] = struct.unpack_from(endian + "I", data, 4)[0] + 8
    cursor = 12
    chunks: list[dict[str, Any]] = []
    while cursor + 8 <= len(data):
        chunk_id = data[cursor : cursor + 4].decode("latin-1", "replace")
        size = struct.unpack_from(endian + "I", data, cursor + 4)[0]
        start = cursor + 8
        end = min(len(data), start + size)
        chunks.append({"id": chunk_id, "offset": start, "declared_size": size, "available_size": max(0, end - start)})
        if chunk_id == "fmt " and end - start >= 16:
            values = struct.unpack_from(endian + "HHIIHH", data, start)
            result.update({
                "wav_format_tag": values[0],
                "wav_channels": values[1],
                "wav_sample_rate": values[2],
                "wav_byte_rate": values[3],
                "wav_block_align": values[4],
                "wav_bits_per_sample": values[5],
            })
        elif chunk_id == "data":
            result["wav_data_offset"] = start
            result["wav_data_size"] = max(0, end - start)
            result["wav_data_declared_size"] = size
        cursor = start + size + (size & 1)
    result["riff_chunks"] = chunks
    return result


def _inspect_wav(path: Path, data: bytes) -> dict[str, Any]:
    result = _riff_chunks(data)
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            frame_rate = handle.getframerate()
            frame_count = handle.getnframes()
            compression = handle.getcomptype()
            result.update({
                "audio_kind": "wav",
                "channels": channels,
                "sample_width_bytes": sample_width,
                "sample_rate": frame_rate,
                "frame_count": frame_count,
                "duration_seconds": frame_count / frame_rate if frame_rate else None,
                "wave_compression": compression,
            })
    except (wave.Error, EOFError):
        result.setdefault("audio_kind", "wav_unreadable_by_stdlib")
        data_size = int(result.get("wav_data_size") or 0)
        block_align = int(result.get("wav_block_align") or 0)
        sample_rate = int(result.get("wav_sample_rate") or 0)
        if block_align > 0:
            frames = data_size // block_align
            result["frame_count_estimate"] = frames
            result["duration_seconds_estimate"] = frames / sample_rate if sample_rate else None
    return result


def _inspect_vag(data: bytes) -> dict[str, Any]:
    if len(data) < 0x30 or data[:4] not in {b"VAGp", b"VAGi"}:
        return {}
    channel_size = struct.unpack_from(">I", data, 0x0C)[0]
    sample_rate = struct.unpack_from(">I", data, 0x10)[0]
    blocks = channel_size // PS_ADPCM_BLOCK
    return {
        "audio_kind": data[:4].decode("ascii", "replace"),
        "vag_version": struct.unpack_from(">I", data, 4)[0],
        "vag_channel_size": channel_size,
        "sample_rate": sample_rate,
        "ps_adpcm_blocks": blocks,
        "decoded_sample_count_estimate": blocks * PS_ADPCM_SAMPLES_PER_BLOCK,
        "duration_seconds_estimate": (
            blocks * PS_ADPCM_SAMPLES_PER_BLOCK / sample_rate if sample_rate else None
        ),
    }


def _inspect_ps_adpcm_blocks(data: bytes, *, start: int = 0) -> dict[str, Any]:
    usable = data[start : len(data) - ((len(data) - start) % PS_ADPCM_BLOCK)]
    block_count = len(usable) // PS_ADPCM_BLOCK
    if block_count <= 0:
        return {}
    valid = 0
    flags: Counter[int] = Counter()
    end_blocks: list[int] = []
    loop_start_blocks: list[int] = []
    for index in range(block_count):
        block = usable[index * 16 : index * 16 + 16]
        predictor = block[0] >> 4
        shift = block[0] & 0x0F
        if predictor < 5 and shift <= 12:
            valid += 1
        flag = block[1]
        flags[flag] += 1
        if flag & 0x01:
            end_blocks.append(index)
        if flag & 0x04:
            loop_start_blocks.append(index)
    ratio = valid / block_count
    return {
        "ps_adpcm_blocks": block_count,
        "ps_adpcm_valid_ratio": round(ratio, 8),
        "ps_adpcm_flag_counts": {f"0x{key:02X}": value for key, value in sorted(flags.items())},
        "ps_adpcm_first_end_block": end_blocks[0] if end_blocks else None,
        "ps_adpcm_last_end_block": end_blocks[-1] if end_blocks else None,
        "ps_adpcm_loop_start_blocks": loop_start_blocks[:64],
        "decoded_sample_count_estimate": block_count * PS_ADPCM_SAMPLES_PER_BLOCK,
    }


def parse_psound_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "path": str(path)}
    data = path.read_bytes()
    result: dict[str, Any] = {
        "exists": True,
        "path": str(path),
        "size_bytes": len(data),
        "hex": data.hex(),
        "sha256": _sha256(path),
    }
    if len(data) >= 41:
        result.update({
            "layout": "observed_41_byte_psound_config",
            "guid_bytes_le": str(__import__("uuid").UUID(bytes_le=data[:16])),
            "field_0x10_u32": struct.unpack_from("<I", data, 0x10)[0],
            "field_0x14_u32": struct.unpack_from("<I", data, 0x14)[0],
            "field_0x18_u32": struct.unpack_from("<I", data, 0x18)[0],
            "field_0x1c_u16": struct.unpack_from("<H", data, 0x1C)[0],
            "field_0x1e_u16": struct.unpack_from("<H", data, 0x1E)[0],
            "field_0x20_u32": struct.unpack_from("<I", data, 0x20)[0],
            "field_0x24_i32": struct.unpack_from("<i", data, 0x24)[0],
            "field_0x28_u8": data[0x28],
            "likely_global_rate_setting": struct.unpack_from("<I", data, 0x18)[0],
            "config_caution": (
                "Field meanings are undocumented. The 22050 value is treated as a likely "
                "global PSound setting, never as proof of source sample rate or length."
            ),
        })
    return result


def _annotate_psound_wav_block_oracle(row: dict[str, Any]) -> None:
    match = PSOUND_NUMBER_RE.fullmatch(str(row.get("name") or ""))
    if match:
        row["psound_sequence_number"] = int(match.group(1))
    frames = row.get("frame_count")
    if frames is None:
        frames = row.get("frame_count_estimate")
    try:
        frame_count = int(frames)
    except (TypeError, ValueError):
        return
    if frame_count <= 0 or frame_count % PS_ADPCM_SAMPLES_PER_BLOCK:
        row["ps_adpcm_block_inference_status"] = "frame_count_not_divisible_by_28"
        return
    blocks = frame_count // PS_ADPCM_SAMPLES_PER_BLOCK
    row.update({
        "ps_adpcm_block_inference_status": "exact_if_psound_export_is_standard_ps_adpcm",
        "psound_decoded_frames": frame_count,
        "psound_inferred_ps_adpcm_blocks": blocks,
        "psound_inferred_encoded_payload_bytes": blocks * PS_ADPCM_BLOCK,
        "psound_frames_per_ps_adpcm_block": PS_ADPCM_SAMPLES_PER_BLOCK,
        "psound_bytes_per_ps_adpcm_block": PS_ADPCM_BLOCK,
        "psound_block_inference_caution": (
            "This is the number of source ADPCM blocks PSound chose to decode, inferred from "
            "28 PCM frames per standard 16-byte PlayStation ADPCM block. It does not alone prove "
            "whether PSound included a terminal flag block."
        ),
    })


def inspect_file(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    row: dict[str, Any] = {
        "relative_path": path.relative_to(root).as_posix(),
        "name": path.name,
        "extension": path.suffix.casefold(),
        "size_bytes": len(data),
        "sha256": _sha256(path),
    }
    suffix = path.suffix.casefold()
    if suffix in {".wav", ".wave"} or data[:4] in {b"RIFF", b"RIFX"}:
        row.update(_inspect_wav(path, data))
        _annotate_psound_wav_block_oracle(row)
    vag = _inspect_vag(data)
    if vag:
        row.update(vag)
        row.update(_inspect_ps_adpcm_blocks(data, start=0x30))
    elif suffix in {".vag", ".vb", ".raw", ".adpcm", ".psadpcm"}:
        row.setdefault("audio_kind", "raw_or_headerless")
        row.update(_inspect_ps_adpcm_blocks(data))
    row["is_audio_candidate"] = bool(
        suffix in AUDIO_EXTENSIONS or row.get("audio_kind") or row.get("wav_sample_rate")
    )
    return row


def _load_fragmenter_rows(report_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    rows = [dict(row) for row in payload.get("samples") or [] if isinstance(row, dict)]
    return sorted(
        rows,
        key=lambda row: (
            int(row.get("flat_index") or 0),
            int(row.get("bank_ordinal") or 0),
            int(row.get("index") or row.get("sample_id") or row.get("local_sample_index") or 0),
        ),
    )


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _boundary_relation(fragmenter_payload: int | None, psound_payload: int | None) -> str:
    if fragmenter_payload is None or psound_payload is None:
        return "unavailable"
    delta = fragmenter_payload - psound_payload
    if delta == 0:
        return "exact_block_count_match"
    if delta == -PS_ADPCM_BLOCK:
        return "fragmenter_one_block_short_possible_terminal_exclusion"
    if delta == PS_ADPCM_BLOCK:
        return "fragmenter_one_block_long"
    if delta % PS_ADPCM_BLOCK == 0:
        return "divergent_whole_block_count"
    return "non_block_aligned_difference"


def compare_by_order(psound_rows: list[dict[str, Any]], fragmenter_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audio = [row for row in psound_rows if row.get("is_audio_candidate")]
    psound_by_index = {
        int(row["psound_sequence_number"]): row
        for row in audio
        if row.get("psound_sequence_number") is not None
    }
    fragmenter_by_index = {
        int(row["flat_index"]): row
        for row in fragmenter_rows
        if row.get("flat_index") is not None
    }
    if psound_by_index and fragmenter_by_index:
        indices = sorted(set(psound_by_index) | set(fragmenter_by_index))
        pairs = [(index, psound_by_index.get(index, {}), fragmenter_by_index.get(index, {})) for index in indices]
        alignment = "PSound SNDDATA_NNNNN number equals Fragmenter zero-based flat_index"
    else:
        count = max(len(audio), len(fragmenter_rows))
        pairs = [
            (
                ordinal,
                audio[ordinal] if ordinal < len(audio) else {},
                fragmenter_rows[ordinal] if ordinal < len(fragmenter_rows) else {},
            )
            for ordinal in range(count)
        ]
        alignment = "PSound natural filename order equals Fragmenter flat sample order"

    output: list[dict[str, Any]] = []
    for comparison_index, p, f in pairs:
        psound_export_rate = _optional_int(p.get("sample_rate") or p.get("wav_sample_rate"))
        psound_frames = _optional_int(p.get("psound_decoded_frames") or p.get("frame_count") or p.get("frame_count_estimate"))
        psound_blocks = _optional_int(p.get("psound_inferred_ps_adpcm_blocks"))
        psound_payload = _optional_int(p.get("psound_inferred_encoded_payload_bytes"))
        fragmenter_rate = _optional_int(f.get("sample_rate"))
        fragmenter_payload = _optional_int(f.get("payload_size"))
        fragmenter_sample_count = _optional_int(f.get("sample_count"))
        fragmenter_duration = _optional_float(f.get("duration_estimate"))

        normalized_psound_duration = (
            psound_frames / fragmenter_rate
            if psound_frames is not None and fragmenter_rate
            else None
        )
        payload_delta = (
            fragmenter_payload - psound_payload
            if fragmenter_payload is not None and psound_payload is not None
            else None
        )
        block_delta = (
            payload_delta // PS_ADPCM_BLOCK
            if payload_delta is not None and payload_delta % PS_ADPCM_BLOCK == 0
            else None
        )
        sample_count_delta = (
            fragmenter_sample_count - psound_frames
            if fragmenter_sample_count is not None and psound_frames is not None
            else None
        )
        normalized_duration_delta = (
            fragmenter_duration - normalized_psound_duration
            if fragmenter_duration is not None and normalized_psound_duration is not None
            else None
        )
        output.append({
            "comparison_index_zero_based": comparison_index,
            "alignment_hypothesis": alignment,
            "psound_path": p.get("relative_path"),
            "psound_sequence_number": p.get("psound_sequence_number"),
            "psound_export_rate": psound_export_rate,
            "psound_export_duration_seconds": p.get("duration_seconds") or p.get("duration_seconds_estimate"),
            "psound_frames": psound_frames,
            "psound_inferred_ps_adpcm_blocks": psound_blocks,
            "psound_inferred_encoded_payload_bytes": psound_payload,
            "fragmenter_flat_index": f.get("flat_index"),
            "fragmenter_bank_ordinal": f.get("bank_ordinal"),
            "fragmenter_sample_id": (
                f.get("index")
                if f.get("index") is not None
                else f.get("sample_id")
                if f.get("sample_id") is not None
                else f.get("local_sample_index")
            ),
            "fragmenter_rate": fragmenter_rate,
            "fragmenter_raw_size": f.get("raw_size"),
            "fragmenter_payload_size": fragmenter_payload,
            "fragmenter_sample_count": fragmenter_sample_count,
            "fragmenter_duration_seconds": fragmenter_duration,
            "psound_duration_at_fragmenter_rate": normalized_psound_duration,
            "payload_delta_fragmenter_minus_psound_bytes": payload_delta,
            "block_delta_fragmenter_minus_psound": block_delta,
            "sample_count_delta_fragmenter_minus_psound_frames": sample_count_delta,
            "duration_delta_fragmenter_minus_rate_normalized_psound": normalized_duration_delta,
            "boundary_relation": _boundary_relation(fragmenter_payload, psound_payload),
            "comparison_confidence": "strong_length_oracle_low_identity_confidence_until_order_is_audited",
        })
    return output


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })


def _sequence_summary(audio_rows: list[dict[str, Any]]) -> dict[str, Any]:
    numbers = [
        int(row["psound_sequence_number"])
        for row in audio_rows
        if row.get("psound_sequence_number") is not None
    ]
    counts = Counter(numbers)
    if not numbers:
        return {
            "recognized_numbered_wavs": 0,
            "continuous_zero_based": False,
            "missing_numbers": [],
            "duplicate_numbers": [],
        }
    minimum = min(numbers)
    maximum = max(numbers)
    missing = sorted(set(range(minimum, maximum + 1)) - set(numbers))
    duplicates = sorted(number for number, count in counts.items() if count > 1)
    return {
        "recognized_numbered_wavs": len(numbers),
        "minimum_number": minimum,
        "maximum_number": maximum,
        "missing_numbers": missing,
        "duplicate_numbers": duplicates,
        "continuous_zero_based": minimum == 0 and not missing and not duplicates and maximum + 1 == len(numbers),
    }


def build_manifest(source: Path, output: Path, fragmenter_report: Path | None = None) -> dict[str, Any]:
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    output.mkdir(parents=True, exist_ok=True)
    ignored = {output.resolve()}
    files = [
        path for path in source.rglob("*")
        if path.is_file() and not any(parent == path or parent in path.parents for parent in ignored)
    ]
    files.sort(key=lambda path: _natural_key(path.relative_to(source).as_posix()))
    rows = [inspect_file(path, source) for path in files]
    audio_rows = [row for row in rows if row.get("is_audio_candidate")]
    rates = Counter(int(row.get("sample_rate") or row.get("wav_sample_rate") or 0) for row in audio_rows)
    rates.pop(0, None)
    block_oracle_rows = [
        row for row in audio_rows
        if row.get("psound_inferred_encoded_payload_bytes") is not None
    ]
    cfg = source / "PSound.cfg"
    if not cfg.is_file():
        candidates = list(source.rglob("PSound.cfg"))
        cfg = candidates[0] if candidates else cfg
    payload: dict[str, Any] = {
        "version": 2,
        "source_root": str(source),
        "file_count": len(rows),
        "audio_candidate_count": len(audio_rows),
        "sample_rate_counts": {str(key): value for key, value in sorted(rates.items())},
        "psound_sequence": _sequence_summary(audio_rows),
        "ps_adpcm_block_oracle": {
            "eligible_wavs": len(block_oracle_rows),
            "total_inferred_blocks": sum(int(row["psound_inferred_ps_adpcm_blocks"]) for row in block_oracle_rows),
            "total_inferred_payload_bytes": sum(int(row["psound_inferred_encoded_payload_bytes"]) for row in block_oracle_rows),
            "rule": "28 decoded PCM frames correspond to one standard 16-byte PlayStation ADPCM block",
            "terminal_block_caution": "PSound may include or exclude a terminal flag block; comparison classifies one-block differences separately.",
        },
        "psound_config": parse_psound_config(cfg),
        "files": rows,
        "interpretation": {
            "exact_length_authority": (
                "For PSound WAVs whose frame count is divisible by 28, frame_count/28 is an exact count of the "
                "standard 16-byte PS-ADPCM blocks PSound chose to decode. The source encoded payload length is "
                "therefore inferred as frame_count/28*16, independent of PSound's forced export sample rate."
            ),
            "rate_caution": (
                "PSound exported every observed WAV at its configured rate. Export duration must not be compared "
                "directly with Fragmenter's source-rate duration; compare PCM frame count, inferred ADPCM blocks, "
                "or duration recalculated at Fragmenter's per-sample source rate."
            ),
            "not_proven": (
                "PSound filename identity, source bank identity, terminal-block inclusion, loop semantics, and exact "
                "SNDDATA routing are not proven by this manifest alone."
            ),
        },
    }
    if fragmenter_report is not None:
        fragmenter_report = fragmenter_report.expanduser().resolve()
        frag_rows = _load_fragmenter_rows(fragmenter_report)
        comparison = compare_by_order(rows, frag_rows)
        payload["fragmenter_report"] = str(fragmenter_report)
        payload["order_comparison_rows"] = len(comparison)
        payload["comparison_summary"] = dict(Counter(row["boundary_relation"] for row in comparison))
        _write_csv(output / "psound_vs_fragmenter_by_order.csv", comparison)
        (output / "psound_vs_fragmenter_by_order.json").write_text(
            json.dumps(comparison, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    (output / "psound_reference_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    _write_csv(output / "psound_reference_manifest.csv", rows)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=r"C:\games\areaserver\FragmentModKit\PSound201")
    parser.add_argument("--output", default=str(Path.cwd() / "diagnostics" / "psound_reference"))
    parser.add_argument("--fragmenter-report")
    args = parser.parse_args(argv)
    report = Path(args.fragmenter_report) if args.fragmenter_report else None
    payload = build_manifest(Path(args.source), Path(args.output), report)
    print(f"PSound files: {payload['file_count']}")
    print(f"Audio candidates: {payload['audio_candidate_count']}")
    print(f"Rates: {payload['sample_rate_counts']}")
    sequence = payload.get("psound_sequence") or {}
    print(
        "PSound sequence:",
        f"{sequence.get('minimum_number')}..{sequence.get('maximum_number')}",
        f"continuous={sequence.get('continuous_zero_based')}",
    )
    oracle = payload.get("ps_adpcm_block_oracle") or {}
    print(f"Block-length oracle WAVs: {oracle.get('eligible_wavs')}")
    print(f"Manifest: {Path(args.output).resolve() / 'psound_reference_manifest.json'}")
    if report is not None:
        print(f"Order comparison: {Path(args.output).resolve() / 'psound_vs_fragmenter_by_order.csv'}")
        print("CAUTION: sample identity is still a hypothesis, but frame/block length comparison is rate-independent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

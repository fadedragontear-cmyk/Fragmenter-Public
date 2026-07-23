#!/usr/bin/env python3
"""Authoritative read-only SNDDATA sample-bank extraction.

Fragment stores SCEI sample/program resources as a primary metadata region plus a
secondary body containing headerless PlayStation ADPCM streams. SCEIVagi indexes
the body; SCEISmpl is articulation metadata and is not treated as waveform data.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import audio_decoder
from project_workspace_v1 import FragmenterProjectV1

VERS_TAGS = (b"IECSsreV", b"SCEIVers")
HEAD_TAGS = (b"IECSdaeH", b"SCEIHead")
VAGI_TAGS = (b"IECSigaV", b"SCEIVagi")
SAMPLE_PROGRAM_TYPE = 2
SEQUENCE_TYPE = 1
REPORT_NAME = "snddata_sample_library_v1.json"
CSV_NAME = "snddata_sample_library_v1.csv"


@dataclass(slots=True)
class VagiEntry:
    index: int
    parameter_offset: int
    stream_offset: int
    sample_rate: int
    flags: int
    unknown: int

    def as_dict(self) -> dict[str, int]:
        return {
            "index": self.index,
            "parameter_offset": self.parameter_offset,
            "stream_offset": self.stream_offset,
            "sample_rate": self.sample_rate,
            "flags": self.flags,
            "unknown": self.unknown,
        }


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _align(value: int, amount: int) -> int:
    return (value + amount - 1) // amount * amount


def _tag_at(data: bytes, offset: int, tags: Iterable[bytes]) -> bool:
    return 0 <= offset <= len(data) - 8 and data[offset : offset + 8] in tuple(tags)


def _find_tag(data: bytes, tags: Iterable[bytes], start: int, end: int) -> int | None:
    hits = []
    for tag in tags:
        hit = data.find(tag, max(0, start), min(len(data), end))
        if hit >= 0:
            hits.append(hit)
    return min(hits) if hits else None


def resource_spans(data: bytes) -> list[tuple[int, int]]:
    offsets: set[int] = set()
    for tag in VERS_TAGS:
        cursor = 0
        while True:
            hit = data.find(tag, cursor)
            if hit < 0:
                break
            offsets.add(hit)
            cursor = hit + 1
    ordered = sorted(offsets)
    return [(offset, ordered[index + 1] if index + 1 < len(ordered) else len(data)) for index, offset in enumerate(ordered)]


def _resolve_section_offset(data: bytes, resource_start: int, head_offset: int, raw_value: int, tags: Iterable[bytes], bound: int) -> int | None:
    candidates = (resource_start + raw_value, head_offset + raw_value, raw_value)
    for candidate in candidates:
        if candidate < bound and _tag_at(data, candidate, tags):
            return candidate
    return None


def _parse_vagi(data: bytes, vagi_offset: int, resource_end: int, secondary_size: int) -> tuple[list[VagiEntry], dict[str, Any]]:
    if vagi_offset + 16 > resource_end:
        raise ValueError("SCEIVagi header is truncated")
    block_size = _u32(data, vagi_offset + 8)
    stored_max = _u32(data, vagi_offset + 12)
    count = stored_max + 1
    section_end = min(resource_end, vagi_offset + block_size)
    if block_size < 16 or section_end < vagi_offset + 16:
        raise ValueError(f"invalid SCEIVagi block size {block_size}")
    if not 0 < count <= 4096:
        raise ValueError(f"invalid SCEIVagi stored maximum index {stored_max}")
    table_start = vagi_offset + 16
    table_end = table_start + count * 4
    if table_end > section_end:
        raise ValueError("SCEIVagi offset table exceeds the section")

    raw_offsets = [_u32(data, table_start + index * 4) for index in range(count)]
    entries: list[VagiEntry] = []
    offset_modes: list[str] = []
    for index, raw_offset in enumerate(raw_offsets):
        candidates = (
            ("section_relative", vagi_offset + raw_offset),
            ("payload_relative", vagi_offset + 8 + raw_offset),
            ("absolute_file", raw_offset),
        )
        parameter_offset = None
        mode = ""
        for candidate_mode, candidate in candidates:
            if table_end <= candidate and candidate + 8 <= section_end:
                parameter_offset = candidate
                mode = candidate_mode
                break
        if parameter_offset is None:
            raise ValueError(f"SCEIVagi parameter {index} offset 0x{raw_offset:X} is outside the section")
        stream_offset = _u32(data, parameter_offset)
        sample_rate = _u16(data, parameter_offset + 4)
        flags = data[parameter_offset + 6]
        unknown = data[parameter_offset + 7]
        if stream_offset > secondary_size:
            raise ValueError(f"SCEIVagi stream {index} offset {stream_offset} exceeds secondary size {secondary_size}")
        if not 4000 <= sample_rate <= 192000:
            raise ValueError(f"SCEIVagi stream {index} has implausible sample rate {sample_rate}")
        entries.append(VagiEntry(index, parameter_offset, stream_offset, sample_rate, flags, unknown))
        offset_modes.append(mode)

    return entries, {
        "block_size": block_size,
        "stored_item_max_index": stored_max,
        "item_count": count,
        "table_start": table_start,
        "raw_parameter_offsets": raw_offsets,
        "parameter_offset_modes": offset_modes,
    }


def _valid_adpcm_ratio(raw: bytes) -> float:
    if len(raw) >= 16 and raw[:16] == b"\x00" * 16:
        raw = raw[16:]
    blocks = min(12, len(raw) // 16)
    if blocks <= 0:
        return 0.0
    valid = 0
    for index in range(blocks):
        block = raw[index * 16 : index * 16 + 16]
        predictor = block[0] >> 4
        shift = block[0] & 0x0F
        if predictor < 5 and shift <= 12:
            valid += 1
    return valid / blocks


def _body_candidates(data: bytes, resource_start: int, head_offset: int, resource_end: int, primary_size: int, secondary_size: int) -> list[int]:
    starts = {resource_start + primary_size, head_offset + primary_size}
    for base in tuple(starts):
        for alignment in (8, 16, 32, 64):
            starts.add(_align(base, alignment))
        cursor = base
        while cursor < min(resource_end, base + 0x1000) and data[cursor] == 0xFF:
            cursor += 1
        starts.add(cursor)
        for alignment in (8, 16, 32, 64):
            starts.add(_align(cursor, alignment))
    return sorted(candidate for candidate in starts if resource_start <= candidate <= resource_end and candidate + secondary_size <= len(data))


def _choose_body_base(data: bytes, resource_start: int, head_offset: int, resource_end: int, primary_size: int, secondary_size: int, entries: list[VagiEntry]) -> tuple[int, list[dict[str, Any]]]:
    offsets = sorted({entry.stream_offset for entry in entries})
    scored: list[dict[str, Any]] = []
    for candidate in _body_candidates(data, resource_start, head_offset, resource_end, primary_size, secondary_size):
        ratios: list[float] = []
        for entry in entries[: min(8, len(entries))]:
            next_offsets = [value for value in offsets if value > entry.stream_offset]
            stream_end = next_offsets[0] if next_offsets else secondary_size
            size = max(0, stream_end - entry.stream_offset)
            sample = data[candidate + entry.stream_offset : candidate + entry.stream_offset + min(size, 16 * 12)]
            ratios.append(_valid_adpcm_ratio(sample))
        within_resource = candidate + secondary_size <= resource_end
        ratio = sum(ratios) / len(ratios) if ratios else 0.0
        score = ratio + (0.25 if within_resource else 0.0)
        if candidate == resource_start + primary_size:
            score += 0.05
        scored.append({"body_base": candidate, "score": round(score, 6), "valid_adpcm_ratio": round(ratio, 6), "within_resource_bound": within_resource})
    if not scored:
        raise ValueError("no in-bounds secondary body candidate")
    scored.sort(key=lambda row: (-float(row["score"]), int(row["body_base"])))
    best = scored[0]
    if float(best["valid_adpcm_ratio"]) < 0.5:
        raise ValueError(f"no secondary body candidate contains convincing PS-ADPCM blocks; best={best}")
    return int(best["body_base"]), scored[:16]


def _trim_stream(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    leading_zero = len(raw) >= 16 and raw[:16] == b"\x00" * 16
    start = 16 if leading_zero else 0
    end = len(raw) - (len(raw) % 16)
    terminator_offset = None
    terminator_kind = None
    for offset in range(start, end, 16):
        block = raw[offset : offset + 16]
        if block == b"\x00\x07" + b"\x77" * 14:
            terminator_offset = offset
            terminator_kind = "007777_separator"
            end = offset
            break
        if len(block) == 16 and block[1] == 0x07:
            terminator_offset = offset
            terminator_kind = "adpcm_flag_07"
            end = offset
            break
    payload = raw[start:end]
    payload = payload[: len(payload) - (len(payload) % 16)]
    return payload, {
        "leading_zero_block": leading_zero,
        "payload_skip": start,
        "terminator_offset": terminator_offset,
        "terminator_kind": terminator_kind,
        "trimmed_tail_bytes": len(raw) - end,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_snddata_file(source: str | Path, output_root: str | Path, *, report_path: str | Path | None = None, csv_path: str | Path | None = None, clean: bool = True, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    data = source_path.read_bytes()
    output = Path(output_root).expanduser()
    if clean and output.is_dir():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    banks: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    spans = resource_spans(data)
    total = len(spans)
    for ordinal, (resource_start, resource_end) in enumerate(spans, 1):
        resource_type = _u16(data, resource_start + 14) if resource_start + 16 <= len(data) else None
        bank: dict[str, Any] = {
            "ordinal": ordinal,
            "resource_offset": resource_start,
            "resource_end": resource_end,
            "resource_type": resource_type,
            "resource_type_name": "sample_program" if resource_type == SAMPLE_PROGRAM_TYPE else "sequence" if resource_type == SEQUENCE_TYPE else "unknown",
            "status": "skipped",
            "errors": [],
        }
        if resource_type != SAMPLE_PROGRAM_TYPE:
            banks.append(bank)
            continue
        try:
            head_offset = _find_tag(data, HEAD_TAGS, resource_start + 16, resource_end)
            if head_offset is None or head_offset + 36 > resource_end:
                raise ValueError("SCEIHead was not found or is truncated")
            head_block_size = _u32(data, head_offset + 8)
            primary_size = _u32(data, head_offset + 12)
            secondary_size = _u32(data, head_offset + 16)
            vagi_raw_offset = _u32(data, head_offset + 32)
            if primary_size <= 0 or secondary_size <= 0:
                raise ValueError(f"invalid primary/secondary sizes {primary_size}/{secondary_size}")
            vagi_offset = _resolve_section_offset(data, resource_start, head_offset, vagi_raw_offset, VAGI_TAGS, resource_end)
            if vagi_offset is None:
                vagi_offset = _find_tag(data, VAGI_TAGS, resource_start, min(resource_end, resource_start + primary_size + 0x1000))
            if vagi_offset is None:
                raise ValueError(f"SCEIVagi was not resolved from HEAD value 0x{vagi_raw_offset:X}")
            entries, vagi_report = _parse_vagi(data, vagi_offset, resource_end, secondary_size)
            body_base, body_candidates = _choose_body_base(data, resource_start, head_offset, resource_end, primary_size, secondary_size, entries)
            bank_dir = output / f"resource_{resource_start:08X}"
            bank_dir.mkdir(parents=True, exist_ok=True)
            stream_offsets = sorted({entry.stream_offset for entry in entries})
            bank_samples: list[dict[str, Any]] = []
            for entry in entries:
                next_offsets = [value for value in stream_offsets if value > entry.stream_offset]
                stream_end = next_offsets[0] if next_offsets else secondary_size
                raw_size = stream_end - entry.stream_offset
                raw_start = body_base + entry.stream_offset
                raw_end = raw_start + raw_size
                if raw_size <= 0 or raw_start < 0 or raw_end > len(data):
                    row = {"resource_offset": resource_start, **entry.as_dict(), "decode_status": "invalid_stream_bounds", "errors": [f"stream bounds 0x{raw_start:X}:0x{raw_end:X} are invalid"]}
                    bank_samples.append(row)
                    sample_rows.append(row)
                    continue
                raw = data[raw_start:raw_end]
                payload, trim = _trim_stream(raw)
                stem = f"sample_{entry.index:04d}_{entry.sample_rate}hz"
                raw_file = bank_dir / f"{stem}.psadpcm"
                wav_file = bank_dir / f"{stem}.wav"
                metadata_file = bank_dir / f"{stem}.json"
                raw_file.write_bytes(raw)
                row = {
                    "resource_offset": resource_start,
                    "resource_type": resource_type,
                    **entry.as_dict(),
                    "body_base": body_base,
                    "source_offset": raw_start,
                    "raw_size": len(raw),
                    "payload_size": len(payload),
                    "raw_path": str(raw_file),
                    "output_path": str(wav_file),
                    "metadata_path": str(metadata_file),
                    "boundary_source": "SCEIVagi stream offsets into HEAD secondary data",
                    "trim": trim,
                    "channels": 1,
                    "decode_status": "pending",
                    "errors": [],
                }
                result = audio_decoder.decode_ps_adpcm_to_wav(payload, wav_file, entry.sample_rate, 1)
                if result.get("errors"):
                    row["decode_status"] = "failed_ps_adpcm_decode"
                    row["errors"] = list(result["errors"])
                else:
                    row.update({"decode_status": result.get("decode_status"), "sample_count": result.get("sample_count"), "duration_estimate": result.get("duration_estimate")})
                metadata_file.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                bank_samples.append(row)
                sample_rows.append(row)
            bank.update({
                "status": "decoded" if any(not row.get("errors") for row in bank_samples) else "failed",
                "head": {"offset": head_offset, "block_size": head_block_size, "primary_size": primary_size, "secondary_size": secondary_size, "vagi_offset_field": vagi_raw_offset},
                "vagi": {"offset": vagi_offset, **vagi_report},
                "body_base": body_base,
                "body_candidates": body_candidates,
                "samples": bank_samples,
            })
        except Exception as exc:
            bank["status"] = "error"
            bank["errors"].append(f"{type(exc).__name__}: {exc}")
        banks.append(bank)
        if callback is not None:
            callback({"kind": "snddata_sample_extract_progress", "current": ordinal, "total": total, "resource_offset": resource_start, "status": bank["status"]})

    summary = {
        "resources": len(spans),
        "sample_program_resources": sum(1 for row in banks if row.get("resource_type") == SAMPLE_PROGRAM_TYPE),
        "decoded_banks": sum(1 for row in banks if row.get("status") == "decoded"),
        "bank_errors": sum(1 for row in banks if row.get("status") == "error"),
        "sample_rows": len(sample_rows),
        "decoded_wavs": sum(1 for row in sample_rows if str(row.get("output_path") or "").lower().endswith(".wav") and not row.get("errors")),
        "failed_samples": sum(1 for row in sample_rows if row.get("errors")),
    }
    report = {
        "version": 1,
        "source": str(source_path),
        "source_size": len(data),
        "source_sha256": _sha256(source_path),
        "format_authority": {
            "sample_program_resource_type": SAMPLE_PROGRAM_TYPE,
            "sequence_resource_type": SEQUENCE_TYPE,
            "vagi_count_semantics": "stored maximum index plus one",
            "waveform_source": "HEAD secondary data indexed by SCEIVagi",
            "scei_smpl_role": "articulation/sample metadata; never treated as waveform bytes",
        },
        "output_root": str(output),
        "summary": summary,
        "banks": banks,
        "samples": sample_rows,
    }
    report_target = Path(report_path).expanduser() if report_path is not None else output.parent / REPORT_NAME
    csv_target = Path(csv_path).expanduser() if csv_path is not None else output.parent / CSV_NAME
    report_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with csv_target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("resource_offset", "index", "sample_rate", "stream_offset", "raw_size", "payload_size", "duration_estimate", "decode_status", "output_path", "raw_path"))
        writer.writeheader()
        for row in sample_rows:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})
    report["report_path"] = str(report_target)
    report["csv_path"] = str(csv_target)
    return report


def project_paths(project: FragmenterProjectV1) -> tuple[Path, Path, Path, Path]:
    workspace = Path(project.workspace_dir).expanduser()
    source = workspace / "sound" / "source" / "data" / "snddata.bin"
    output = workspace / "sound" / "decoded" / "snddata" / "samples"
    reports = workspace / "sound" / "reports"
    return source, output, reports / REPORT_NAME, reports / CSV_NAME


def extract_project_snddata_samples(project: FragmenterProjectV1, *, clean: bool = True, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    source, output, report, csv_report = project_paths(project)
    return extract_snddata_file(source, output, report_path=report, csv_path=csv_report, clean=clean, callback=callback)

#!/usr/bin/env python3
"""Inspect SCEI HD/BD sound-bank containers.

This parser is intentionally conservative.  It recognizes banks by the exact
little-endian section marker ``b"IECSsreV"`` (readable as ``SCEI / Vers``),
keeps every raw 8-byte section id in the report, and only promotes values that
look structurally plausible.
"""
from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

MAGIC = b"IECSsreV"
SECTION_NAMES = {
    b"IECSsreV": "SCEI / Vers",
    b"IECSdaeH": "SCEI / Head",
    b"IECSigaV": "SCEI / Vagi",
    b"IECSlpmS": "SCEI / Smpl",
    b"IECStesS": "SCEI / Sset",
    b"IECSgorP": "SCEI / Prog",
    b"IECSbteS": "SCEI / Setb",
}
KNOWN_IDS = set(SECTION_NAMES)


@dataclass(slots=True)
class Section:
    raw_id: bytes
    offset: int
    data_offset: int
    end_offset: int

    @property
    def size(self) -> int:
        return max(0, self.end_offset - self.data_offset)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_id_hex": self.raw_id.hex(),
            "raw_id_ascii": self.raw_id.decode("ascii", "replace"),
            "name": SECTION_NAMES.get(self.raw_id, "unknown"),
            "offset": self.offset,
            "data_offset": self.data_offset,
            "size": self.size,
            "end_offset": self.end_offset,
        }


@dataclass(slots=True)
class Bank:
    source: str
    offset: int
    hd_size: int
    bd_size: int | None
    sections: list[Section] = field(default_factory=list)
    vers: dict[str, Any] = field(default_factory=dict)
    head: dict[str, Any] = field(default_factory=dict)
    vagi: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        head_fields = {
            "head_parse_mode": self.head.get("head_parse_mode"),
            "hd_size": self.head.get("hd_size", self.hd_size),
            "bd_size": self.head.get("bd_size", self.bd_size),
            "prog_offset": self.head.get("prog_offset"),
            "sset_offset": self.head.get("sset_offset"),
            "smpl_offset": self.head.get("smpl_offset"),
            "vagi_offset": self.head.get("vagi_offset"),
            "setb_offset": self.head.get("setb_offset"),
            "validated_section_references": self.head.get("validated_section_references", []),
        }
        return {
            "source": self.source,
            "offset": self.offset,
            **head_fields,
            "sections": [s.as_dict() for s in self.sections],
            "vers": self.vers,
            "head": self.head,
            "vagi": self.vagi,
            "warnings": self.warnings,
        }


def _u32le(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _u32s(data: bytes, base: int, limit: int) -> Iterable[tuple[int, int]]:
    end = min(len(data), base + limit)
    for off in range(base, end - 3, 4):
        yield off, _u32le(data, off)


def _plausible_rate(v: int) -> bool:
    return 4000 <= v <= 192000


def _find_size_pair(data: bytes, base: int, file_size: int) -> tuple[int | None, int | None, dict[str, Any]]:
    """Find an HD/BD size pair near Vers without trusting fixed offsets."""
    candidates: list[dict[str, int]] = []
    for a_off, a in _u32s(data, base + 8, 0x100):
        if a < 8 or base + a > file_size:
            continue
        for b_off, b in _u32s(data, base + 8, 0x100):
            if a_off == b_off or b <= 0:
                continue
            if base + a + b <= file_size:
                score = 0
                if base + a + b == file_size:
                    score += 4
                if a % 16 == 0:
                    score += 1
                if b % 16 == 0:
                    score += 1
                candidates.append({"hd_size": a, "bd_size": b, "hd_size_field": a_off - base, "bd_size_field": b_off - base, "score": score})
    candidates.sort(key=lambda c: (-c["score"], c["hd_size_field"], c["bd_size_field"]))
    if not candidates:
        return None, None, {"size_candidates": []}
    best = candidates[0]
    return best["hd_size"], best["bd_size"], {"size_candidates": candidates[:8]}


def _sections(hd: bytes, bank_base: int = 0) -> list[Section]:
    starts = [(i, hd[i:i + 8]) for i in range(0, max(0, len(hd) - 7)) if hd[i:i + 8] in KNOWN_IDS]
    starts = sorted(dict(starts).items())
    out: list[Section] = []
    for idx, (off, raw) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(hd)
        out.append(Section(raw, bank_base + off, bank_base + off + 8, bank_base + end))
    return out


def _section_data(hd: bytes, sec: Section, bank_base: int) -> bytes:
    start = sec.data_offset - bank_base
    end = sec.end_offset - bank_base
    return hd[start:end]


HEAD_KNOWN_LAYOUT_FIELDS = (
    ("hd_size", 0x04, None),
    ("bd_size", 0x08, None),
    ("prog_offset", 0x0C, b"IECSgorP"),
    ("sset_offset", 0x10, b"IECStesS"),
    ("smpl_offset", 0x14, b"IECSlpmS"),
    ("vagi_offset", 0x18, b"IECSigaV"),
    ("setb_offset", 0x1C, b"IECSbteS"),
)


def _scan_head(data: bytes, section_offsets: dict[bytes, int], bank_base: int) -> dict[str, Any]:
    found: dict[str, list[dict[str, int | str]]] = {}
    for off, val in _u32s(data, 0, min(len(data), 0x400)):
        absolute = val
        relative = val + bank_base
        for raw, sec_off in section_offsets.items():
            if absolute == sec_off or relative == sec_off or val == sec_off - bank_base:
                found.setdefault(raw.decode("ascii", "replace"), []).append({"field_offset": off, "value": val, "name": SECTION_NAMES[raw]})
    stream_counts = [v for _o, v in _u32s(data, 0, min(len(data), 0x100)) if 0 < v < 4096]
    return {"section_offset_fields": found, "stream_count_candidates": stream_counts[:16]}


def _matching_section_reference(value: int, expected_raw: bytes, section_offsets: dict[bytes, int], bank_base: int) -> dict[str, Any] | None:
    sec_off = section_offsets.get(expected_raw)
    if sec_off is None:
        return None
    candidates = {
        "absolute": value,
        "bank_relative": bank_base + value,
    }
    for mode, absolute in candidates.items():
        if absolute == sec_off:
            return {
                "field": next(name for name, _off, raw in HEAD_KNOWN_LAYOUT_FIELDS if raw == expected_raw),
                "value": value,
                "target_raw_id_ascii": expected_raw.decode("ascii", "replace"),
                "target_name": SECTION_NAMES[expected_raw],
                "target_offset": sec_off,
                "reference_mode": mode,
                "valid": True,
            }
    return {
        "field": next(name for name, _off, raw in HEAD_KNOWN_LAYOUT_FIELDS if raw == expected_raw),
        "value": value,
        "target_raw_id_ascii": expected_raw.decode("ascii", "replace"),
        "target_name": SECTION_NAMES[expected_raw],
        "target_offset": sec_off,
        "reference_mode": "unmatched",
        "valid": False,
    }


def _parse_head(data: bytes, section_offsets: dict[bytes, int], hd_size: int, bank_base: int) -> dict[str, Any]:
    scanner_evidence = _scan_head(data, section_offsets, bank_base)
    if len(data) < 0x20:
        scanner_evidence["head_parse_mode"] = "scanner_fallback"
        scanner_evidence["known_layout_error"] = "Head payload is too small for known layout"
        return scanner_evidence

    result: dict[str, Any] = {"head_parse_mode": "known_layout", "validated_section_references": []}
    for name, off, expected_raw in HEAD_KNOWN_LAYOUT_FIELDS:
        result[name] = _u32le(data, off)
        if expected_raw is not None:
            validation = _matching_section_reference(result[name], expected_raw, section_offsets, bank_base)
            if validation is not None:
                result["validated_section_references"].append(validation)

    if result["hd_size"] != hd_size:
        result["hd_size_warning"] = f"Head hd_size {result['hd_size']} differs from parsed HD size {hd_size}"
    result["scanner_evidence"] = scanner_evidence
    return result


def parse_vagi_known_layout(data: bytes, bd_size: int | None) -> dict[str, Any]:
    """Parse the known compact Vagi HD/BD stream-info layout.

    *data* starts immediately after the ``IECSigaV`` marker.  The section
    metadata size lives at payload offset +0x00 (raw Vagi offset +0x08), the
    stream count lives at payload offset +0x04 (raw Vagi offset +0x0C), and
    the offset table begins at payload offset +0x08 (raw Vagi offset +0x10).
    Table entries are raw Vagi-section-relative offsets that include the
    8-byte marker, so they are converted to payload indexes before indexing
    *data*.  Offset table order is authoritative for stream indexes and
    stream-size calculation.
    """
    if len(data) < 0x08:
        raise ValueError("Vagi payload is too small for known layout header")

    section_metadata_size = _u32le(data, 0x00)
    count = _u32le(data, 0x04)
    if not (0 < count <= 4096):
        raise ValueError(f"known Vagi stream count is out of range: {count}")

    table_start = 0x08
    table_end = table_start + count * 4
    if table_end > len(data):
        raise ValueError("known Vagi offset table exceeds payload size")

    raw_offsets = [_u32le(data, table_start + i * 4) for i in range(count)]
    payload_offsets = [raw - 8 for raw in raw_offsets]
    evidence = {
        "raw_vagi_offset": 0,
        "payload_start_offset": 8,
        "count_field_raw_offset": 0x0C,
        "count_field_payload_offset": 0x04,
        "table_raw_offset": 0x10,
        "table_payload_offset": table_start,
        "raw_table_values": raw_offsets,
        "converted_payload_indexes": payload_offsets,
    }

    # Some banks contain one safely readable table word after the declared
    # stream count.  Keep stream_count authoritative, but report the extra
    # word when it looks like either an omitted stream entry or a sentinel.
    extra_entry_end = table_start + (count + 1) * 4
    if extra_entry_end <= len(data):
        extra_raw = _u32le(data, table_start + count * 4)
        extra_payload_offset = extra_raw - 8
        extra_diagnostic: dict[str, Any] = {
            "table_index": count,
            "raw_value": extra_raw,
            "converted_payload_offset": extra_payload_offset,
        }
        extra_entry_readable = 0 <= extra_payload_offset and extra_payload_offset + 8 <= len(data)
        if extra_raw != 0 and extra_entry_readable:
            extra_stream_offset = _u32le(data, extra_payload_offset)
            extra_diagnostic["stream_offset"] = extra_stream_offset
            extra_diagnostic["reason"] = (
                "nonzero table entry after declared count converts to an in-bounds Vagi payload offset; "
                "declared stream_count was left unchanged"
            )
            evidence["possible_extra_subsong"] = extra_diagnostic
        sentinel_reason = None
        if extra_raw == 0:
            sentinel_reason = "zero table entry after declared count may be a table terminator"
        elif extra_entry_readable:
            extra_stream_offset = extra_diagnostic.get("stream_offset", _u32le(data, extra_payload_offset))
            if bd_size is not None and extra_stream_offset == bd_size:
                sentinel_reason = "extra table entry points to a Vagi entry whose BD stream offset equals the BD end"
        elif extra_raw == 8 + len(data):
            sentinel_reason = "extra raw table value converts to the Vagi payload end"
        if sentinel_reason is not None:
            evidence["final_entry_sentinel"] = {
                "table_index": count,
                "raw_value": extra_raw,
                "converted_payload_offset": extra_payload_offset,
                "reason": sentinel_reason,
            }
            if "stream_offset" in extra_diagnostic:
                evidence["final_entry_sentinel"]["stream_offset"] = extra_diagnostic["stream_offset"]
    streams: list[dict[str, Any]] = []
    for idx, (raw_off, off) in enumerate(zip(raw_offsets, payload_offsets, strict=True)):
        if off < 0 or off >= len(data) or off + 8 > len(data):
            raise ValueError(f"known Vagi stream-info entry {idx} is outside payload bounds")

        stream_offset = _u32le(data, off + 0x00)
        sample_rate = struct.unpack_from("<H", data, off + 0x04)[0]
        flags = data[off + 0x06]
        unknown = data[off + 0x07]
        loop_flag = flags & 1

        if bd_size is not None and stream_offset > bd_size:
            raise ValueError(f"known Vagi stream offset {stream_offset} exceeds BD size {bd_size}")
        if not _plausible_rate(sample_rate):
            raise ValueError(f"known Vagi sample rate is implausible: {sample_rate}")
        streams.append({
            "index": idx,
            "vagi_entry_offset": off,
            "vagi_entry_raw_offset": raw_off,
            "vagi_entry_payload_offset": off,
            "stream_offset": stream_offset,
            "sample_rate": sample_rate,
            "flags": flags,
            "unknown": unknown,
            "loop_flag": loop_flag,
        })

    sorted_offsets = sorted(stream["stream_offset"] for stream in streams)
    for stream in streams:
        so = stream["stream_offset"]
        next_offsets = [value for value in sorted_offsets if value > so]
        end = next_offsets[0] if next_offsets else bd_size
        stream["calculated_stream_size"] = (end - so) if end is not None and end >= so else None

    return {
        "vagi_parse_mode": "known_hd_bd_layout",
        "section_metadata_size": section_metadata_size,
        "offset_table": raw_offsets,
        "offset_table_payload_indexes": payload_offsets,
        "stream_count": count,
        "evidence": evidence,
        "streams": streams,
    }


def _parse_vagi_heuristic(data: bytes, bd_size: int | None) -> dict[str, Any]:
    result: dict[str, Any] = {"offset_table": [], "streams": []}
    if len(data) < 4:
        return result
    count = _u32le(data, 0)
    table_start = 4 if 0 < count <= 4096 and 4 + count * 4 <= len(data) else 0
    max_entries = count if table_start else min(4096, len(data) // 4)
    offsets: list[int] = []
    for i in range(max_entries):
        val = _u32le(data, table_start + i * 4)
        if val >= len(data) or val % 4:
            if table_start:
                break
            if offsets:
                break
            continue
        offsets.append(val)
    # Keep only mostly monotonic unique offsets; this avoids treating arbitrary data as a table.
    offsets = sorted(dict.fromkeys(offsets))
    result["offset_table"] = offsets
    result["stream_count"] = len(offsets)
    bd_offsets: list[int] = []
    for idx, off in enumerate(offsets):
        entry = data[off:min(len(data), off + 0x80)]
        words = [v for _o, v in _u32s(entry, 0, len(entry))]
        # The common compact Vagi entry layout starts with BD stream offset,
        # sample rate, loop flag, and flags.  Fall back to a plausibility scan
        # when an entry variant does not fit that pattern.
        stream_off = words[0] if words and bd_size is not None and 0 <= words[0] < bd_size and words[0] % 16 == 0 else None
        if stream_off is None:
            stream_off = next((v for v in words if bd_size is not None and 0 <= v < bd_size and v % 16 == 0), None)
        if stream_off is not None:
            bd_offsets.append(stream_off)
        sample_rate = words[1] if len(words) > 1 and _plausible_rate(words[1]) else next((v for v in words if _plausible_rate(v)), None)
        loop_flag = words[2] if len(words) > 2 and words[2] in (0, 1) else None
        if loop_flag is None:
            loop_flag = next((v for v in words[1:] if v in (0, 1)), None)
        flags = words[3] if len(words) > 3 else None
        result["streams"].append({"index": idx, "vagi_entry_offset": off, "stream_offset": stream_off, "sample_rate": sample_rate, "flags": flags, "loop_flag": loop_flag})
    sorted_bd = sorted(v for v in bd_offsets if v is not None)
    for stream in result["streams"]:
        so = stream.get("stream_offset")
        if so is None:
            continue
        nexts = [v for v in sorted_bd if v > so]
        end = nexts[0] if nexts else bd_size
        stream["calculated_stream_size"] = (end - so) if end is not None and end >= so else None
    return result


def _parse_vagi(data: bytes, bd_size: int | None) -> dict[str, Any]:
    try:
        return parse_vagi_known_layout(data, bd_size)
    except ValueError as exc:
        result = _parse_vagi_heuristic(data, bd_size)
        result["vagi_parse_mode"] = "heuristic_fallback" if result.get("streams") else "failed"
        result["known_layout_error"] = str(exc)
        return result


def parse_bank(
    hd: bytes,
    source: str,
    bank_base: int = 0,
    bd_size: int | None = None,
    hd_size_hint: int | None = None,
    vers_info_hint: dict[str, Any] | None = None,
) -> Bank:
    hd_size = len(hd)
    guessed_hd, guessed_bd, vers_info = _find_size_pair(hd, 0, len(hd))
    if vers_info_hint is not None:
        vers_info = vers_info_hint
    if bd_size is None:
        bd_size = guessed_bd
    sections = _sections(hd, bank_base)
    bank = Bank(source, bank_base, hd_size_hint or guessed_hd or hd_size, bd_size, sections, vers=vers_info)
    if not hd.startswith(MAGIC):
        bank.warnings.append("bank slice does not start with exact IECSsreV magic")
    sec_offsets = {s.raw_id: s.offset for s in sections}
    for sec in sections:
        data = _section_data(hd, sec, bank_base)
        if sec.raw_id == b"IECSdaeH":
            bank.head = _parse_head(data, sec_offsets, bank.hd_size, bank_base)
            if bank.head.get("head_parse_mode") == "known_layout":
                parsed_hd_size = bank.head.get("hd_size")
                parsed_bd_size = bank.head.get("bd_size")
                if isinstance(parsed_hd_size, int) and parsed_hd_size > 0:
                    bank.hd_size = parsed_hd_size
                if isinstance(parsed_bd_size, int) and parsed_bd_size > 0:
                    bank.bd_size = parsed_bd_size
                    bd_size = parsed_bd_size
        elif sec.raw_id == b"IECSigaV":
            bank.vagi = _parse_vagi(data, bd_size)
    return bank


def discover(data: bytes, source: str) -> list[Bank]:
    banks: list[Bank] = []
    starts = [i for i in range(0, max(0, len(data) - 7)) if data[i:i + 8] == MAGIC]
    for idx, start in enumerate(starts):
        guessed_hd, guessed_bd, _info = _find_size_pair(data, start, len(data))
        end = start + guessed_hd if guessed_hd and start + guessed_hd <= len(data) else (starts[idx + 1] if idx + 1 < len(starts) else len(data))
        banks.append(parse_bank(data[start:end], source, start, guessed_bd, guessed_hd, _info))
    return banks


def load_inputs(path: Path) -> tuple[bytes, int | None, str]:
    data = path.read_bytes()
    if path.suffix.lower() == ".hd":
        bd = path.with_suffix(".bd")
        return data, bd.stat().st_size if bd.exists() else None, str(path)
    return data, None, str(path)



def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    return cleaned.strip("._") or "bank"


def _bank_name(bank: Bank, ordinal: int) -> str:
    return _safe_name(f"{Path(bank.source).stem}_0x{bank.offset:X}" if bank.offset else Path(bank.source).stem or f"bank_{ordinal:04d}")


def _raw_stream_path(decoded_root: Path, bank_name: str, stream_index: int) -> Path:
    return decoded_root / "audio" / "raw" / "scei" / bank_name / f"stream_{stream_index + 1:04d}.psadpcm"


def _wav_stream_path(decoded_root: Path, bank_name: str, stream_index: int) -> Path:
    return decoded_root / "audio" / "wav" / bank_name / f"stream_{stream_index + 1:04d}.wav"


def bank_body_for_path(path: Path, bank: Bank, container_data: bytes) -> bytes | None:
    """Return BD bytes for a parsed bank from a paired .bd or combined container."""
    if path.suffix.lower() == ".hd":
        bd_path = path.with_suffix(".bd")
        return bd_path.read_bytes() if bd_path.is_file() else None
    if bank.bd_size is None:
        return None
    start = bank.offset + bank.hd_size
    end = start + bank.bd_size
    if 0 <= start <= end <= len(container_data):
        return container_data[start:end]
    return None


def decode_bank_streams(bank: Bank, bd: bytes | None, decoded_root: Path, bank_name: str | None = None) -> list[dict[str, Any]]:
    """Decode parsed SCEI bank streams to WAV rows, preserving malformed raw streams."""
    import audio_decoder

    rows: list[dict[str, Any]] = []
    name = bank_name or _bank_name(bank, 1)
    streams = bank.vagi.get("streams") or []
    for stream in streams:
        idx = int(stream.get("index") or 0)
        row: dict[str, Any] = {
            "source_candidate": bank.source,
            "source_iso_path": bank.source,
            "detected_format": "scei_ps_adpcm_bank_stream",
            "confidence": "high",
            "decode_status": "failed",
            "bank_source": bank.source,
            "bank_offset": bank.offset,
            "stream_index": idx,
            "stream_offset": stream.get("stream_offset"),
            "stream_size": stream.get("calculated_stream_size"),
            "sample_rate": stream.get("sample_rate"),
            "channels": 1,
            "loop_flag": stream.get("loop_flag"),
            "output_path": None,
            "raw_path": None,
            "warnings": [],
            "errors": [],
            "next_action": "decode PS ADPCM bank stream to PCM WAV",
            "audio_purpose": audio_decoder.classify_audio_purpose(bank.source),
        }
        so = stream.get("stream_offset")
        size = stream.get("calculated_stream_size")
        rate = stream.get("sample_rate")
        if bd is None:
            row["errors"].append("BD/body data is unavailable")
        if not isinstance(so, int) or so < 0:
            row["errors"].append("stream offset is missing or invalid")
        if not isinstance(size, int) or size <= 0:
            row["errors"].append("stream size is missing or invalid")
        if not isinstance(rate, int) or not _plausible_rate(rate):
            row["errors"].append("sample rate is missing or implausible")
        body = b""
        if bd is not None and isinstance(so, int) and isinstance(size, int) and size > 0:
            end = so + size
            if so < 0 or end > len(bd) or end < so:
                row["errors"].append("stream bounds exceed available BD/body bytes")
            else:
                body = bd[so:end]
                raw = _raw_stream_path(decoded_root, name, idx)
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_bytes(body)
                row["raw_path"] = str(raw)
                if not body:
                    row["errors"].append("stream body is empty")
        if not row["errors"]:
            wav = _wav_stream_path(decoded_root, name, idx)
            result = audio_decoder.decode_ps_adpcm_to_wav(body, wav, int(rate), 1)
            if result.get("errors"):
                row["errors"].extend(result["errors"])
                row["decode_status"] = "failed_ps_adpcm_decode"
            else:
                row.update({"decode_status": result["decode_status"], "output_path": str(wav), "duration_estimate": result.get("duration_estimate")})
        elif row["raw_path"]:
            row["decode_status"] = "raw_preserved_malformed_scei_stream"
            row["next_action"] = "inspect preserved raw PS ADPCM stream"
        else:
            row["decode_status"] = "unavailable_malformed_scei_stream"
            row["next_action"] = "locate paired BD/body data or repair bank metadata"
        rows.append(row)
    return rows


def decode_scei_path(path: Path, decoded_root: Path) -> list[dict[str, Any]]:
    """Parse and decode all SCEI banks in *path* for media pipeline integration."""
    data, paired_bd_size, source = load_inputs(path)
    banks = [parse_bank(data, source, 0, paired_bd_size, len(data))] if data.startswith(MAGIC) and path.suffix.lower() == ".hd" else discover(data, source)
    rows: list[dict[str, Any]] = []
    for ordinal, bank in enumerate(banks, 1):
        rows.extend(decode_bank_streams(bank, bank_body_for_path(path, bank, data), decoded_root, _bank_name(bank, ordinal)))
    return rows


def bank_summary(bank: Bank, decoded_rows: list[dict[str, Any]] | None = None, *, pair_found: bool | None = None, inline_body_available: bool | None = None) -> dict[str, Any]:
    """Return compact report metrics for a parsed SCEI bank."""
    streams = bank.vagi.get("streams") or []
    valid = [
        st for st in streams
        if isinstance(st.get("stream_offset"), int)
        and isinstance(st.get("sample_rate"), int)
        and _plausible_rate(int(st.get("sample_rate")))
        and (st.get("calculated_stream_size") is None or isinstance(st.get("calculated_stream_size"), int))
    ]
    rows = decoded_rows or []
    decoded = sum(1 for r in rows if str(r.get("output_path") or "").lower().endswith(".wav") or str(r.get("decode_status") or "").startswith("decoded_"))
    failed = sum(1 for r in rows if r.get("errors") or "fail" in str(r.get("decode_status") or ""))
    out = {
        "source_iso_path": bank.source,
        "offset": bank.offset,
        "pair_found": pair_found,
        "inline_body_available": inline_body_available,
        "head_parse_mode": bank.head.get("head_parse_mode"),
        "vagi_parse_mode": bank.vagi.get("vagi_parse_mode"),
        "stream_count": bank.vagi.get("stream_count", len(streams)),
        "valid_stream_metadata_count": len(valid),
        "decoded_stream_count": decoded,
        "failed_stream_count": failed,
        "hd_size": bank.hd_size,
        "bd_size": bank.bd_size,
        "warnings": list(bank.warnings),
    }
    return {k: v for k, v in out.items() if v is not None}


def inspect_hd_bd_pair(hd_path: Path, decoded_root: Path | None = None, source_iso_path: str | None = None) -> dict[str, Any]:
    """Inspect an explicit .hd/.bd pair and optionally decode streams."""
    data, paired_bd_size, _source = load_inputs(hd_path)
    source = source_iso_path or str(hd_path)
    pair_found = hd_path.with_suffix(".bd").is_file()
    bank = parse_bank(data, source, 0, paired_bd_size, len(data))
    bd = bank_body_for_path(hd_path, bank, data)
    rows = decode_bank_streams(bank, bd, decoded_root, _bank_name(bank, 1)) if decoded_root is not None else []
    return {"path": source, "present": True, **bank_summary(bank, rows, pair_found=pair_found), "banks": [bank.as_dict()], "decoded_rows": rows}


def inspect_snddata(path: Path, decoded_root: Path | None = None, source_iso_path: str | None = None) -> dict[str, Any]:
    """Scan every IECSsreV offset independently; each bank gets its own inline-body status."""
    data = path.read_bytes()
    source = source_iso_path or str(path)
    offsets = [i for i in range(0, max(0, len(data) - 7)) if data[i:i + 8] == MAGIC]
    banks = []
    decoded_rows: list[dict[str, Any]] = []
    for ordinal, off in enumerate(offsets, 1):
        guessed_hd, guessed_bd, info = _find_size_pair(data, off, len(data))
        end = off + guessed_hd if guessed_hd and off + guessed_hd <= len(data) else (offsets[ordinal] if ordinal < len(offsets) else len(data))
        bank = parse_bank(data[off:end], source, off, guessed_bd, guessed_hd, info)
        body = bank_body_for_path(path, bank, data)
        inline_body_available = body is not None
        rows = decode_bank_streams(bank, body, decoded_root, _bank_name(bank, ordinal)) if decoded_root is not None else []
        decoded_rows.extend(rows)
        banks.append({**bank_summary(bank, rows, inline_body_available=inline_body_available), "bank": bank.as_dict()})
    return {"path": source, "present": True, "scei_offsets": offsets, "candidate_count": len(offsets), "banks": banks, "decoded_rows": decoded_rows}


def validate_gzip_header(data: bytes) -> bool:
    if len(data) < 10 or data[:2] != b"\x1f\x8b" or data[2] != 8:
        return False
    flags = data[3]
    if flags & 0xE0:
        return False
    pos = 10
    if flags & 4:
        if pos + 2 > len(data): return False
        xlen = struct.unpack_from("<H", data, pos)[0]; pos += 2 + xlen
    if flags & 8:
        end = data.find(b"\x00", pos)
        if end < 0: return False
        pos = end + 1
    if flags & 16:
        end = data.find(b"\x00", pos)
        if end < 0: return False
        pos = end + 1
    if flags & 2:
        pos += 2
    return pos <= len(data)


def signature_candidates(data: bytes) -> dict[str, Any]:
    sigs = {"SCEI": MAGIC, "VAG": b"VAGp", "VAB": b"VABp", "SShd": b"SShd", "SSbd": b"SSbd"}
    return {name: [i for i in range(0, max(0, len(data) - len(magic) + 1)) if data[i:i+len(magic)] == magic][:64] for name, magic in sigs.items()}


def inspect_bgm(path: Path, source_iso_path: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": source_iso_path or str(path),
        "present": True,
        "signature_hex": data[:16].hex(),
        "gzip_header_valid": validate_gzip_header(data),
        "detected_format": "gzip" if validate_gzip_header(data) else None,
        "candidates": signature_candidates(data),
    }

def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect SCEI HD/BD banks and embedded IECSsreV headers.")
    ap.add_argument("path", type=Path, help=".hd, combined .hbd/.bin, or larger .bin to scan")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a text summary")
    args = ap.parse_args()
    data, paired_bd_size, source = load_inputs(args.path)
    banks = [parse_bank(data, source, 0, paired_bd_size, len(data))] if data.startswith(MAGIC) and args.path.suffix.lower() == ".hd" else discover(data, source)
    payload = [b.as_dict() for b in banks]
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for bank in payload:
            print(f"{bank['source']} @ 0x{bank['offset']:X}: hd={bank['hd_size']} bd={bank['bd_size']} streams={bank.get('vagi', {}).get('stream_count', 0)}")
            for sec in bank["sections"]:
                print(f"  {sec['raw_id_ascii']} ({sec['name']}) @ 0x{sec['offset']:X} size={sec['size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

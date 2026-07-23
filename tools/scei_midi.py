#!/usr/bin/env python3
"""Conservative parser for SCEIMidi sequence blocks.

The parser records observed header/timing fields and decodes a useful subset of
MIDI-like event streams without discarding unknown bytes.  It is intentionally
report-oriented: JSON/TXT reports are always safe, while Standard MIDI output is
not produced unless a future converter can prove the stream is structurally
valid.
"""
from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STAT_CONFIRMED = "custom_midi_confirmed_events"
STAT_PARTIAL = "custom_midi_partial"
STAT_DESYNC = "custom_midi_desync"
STAT_UNSUPPORTED = "unsupported_event"
SUPPORTED = {0x80: "note_off", 0x90: "note_on", 0xB0: "control_change", 0xE0: "pitch_wheel"}


def _hex(b: bytes) -> str:
    return b.hex()


def _u16le(b: bytes, off: int) -> int | None:
    return struct.unpack_from("<H", b, off)[0] if off + 2 <= len(b) else None


def _u32le(b: bytes, off: int) -> int | None:
    return struct.unpack_from("<I", b, off)[0] if off + 4 <= len(b) else None


def read_vlq(data: bytes, off: int, limit: int) -> tuple[int, int, bytes, list[str]]:
    """Read a candidate MIDI VLQ; returns value, byte count, raw, warnings."""
    value = 0
    raw = bytearray()
    warnings: list[str] = []
    pos = off
    for i in range(4):
        if pos >= limit:
            warnings.append("truncated_vlq")
            break
        byte = data[pos]
        raw.append(byte)
        value = (value << 7) | (byte & 0x7F)
        pos += 1
        if not (byte & 0x80):
            return value, len(raw), bytes(raw), warnings
    else:
        if raw and raw[-1] & 0x80:
            warnings.append("vlq_continues_after_four_bytes")
    return value, len(raw), bytes(raw), warnings


def infer_tempo(raw: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {"raw": _hex(raw), "byte_order": None, "value": None, "bpm": None, "warnings": []}
    if len(raw) != 3:
        result["warnings"].append("tempo_field_truncated")
        return result
    candidates = {
        "big": int.from_bytes(raw, "big"),
        "little": int.from_bytes(raw, "little"),
    }
    plausible = {k: v for k, v in candidates.items() if 200_000 <= v <= 2_000_000}
    if len(plausible) == 1:
        order, value = next(iter(plausible.items()))
        result.update({"byte_order": order, "value": value, "bpm": round(60_000_000 / value, 6)})
    elif len(plausible) > 1:
        result["warnings"].append("tempo_byte_order_ambiguous")
    else:
        result["warnings"].append("tempo_not_plausible")
    result["candidates"] = candidates
    return result


@dataclass(slots=True)
class Event:
    offset: int
    raw_bytes: bytes
    delta_ticks: int
    absolute_ticks: int
    event_type: str
    channel: int | None = None
    values: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    status: str = STAT_CONFIRMED

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "raw_bytes": _hex(self.raw_bytes),
            "delta_ticks": self.delta_ticks,
            "absolute_ticks": self.absolute_ticks,
            "event_type": self.event_type,
            "channel": self.channel,
            "values": self.values,
            "warnings": self.warnings,
            "status": self.status,
        }


def parse_header(data: bytes) -> dict[str, Any]:
    return {
        "signature": data[:8].decode("ascii", "replace"),
        "signature_hex": _hex(data[:8]),
        "block_size": _u32le(data, 0x08),
        "raw_0c_0f": _hex(data[0x0C:0x10]),
        "raw_10_13": _hex(data[0x10:0x14]),
        "raw_14_17": _hex(data[0x14:0x18]),
    }


def parse_timing(data: bytes) -> dict[str, Any]:
    raw_tempo = data[0x1E:0x21]
    return {
        "ticks_per_quarter_note": {"offset": 0x18, "raw": _hex(data[0x18:0x1A]), "value": _u16le(data, 0x18)},
        "tempo_marker_fields": {"offset": 0x1A, "raw": _hex(data[0x1A:0x1E])},
        "tempo": infer_tempo(raw_tempo),
    }


def parse_events(data: bytes, start: int = 0x21, end: int | None = None) -> tuple[list[Event], list[str], str]:
    limit = min(end or len(data), len(data))
    pos = start
    abs_ticks = 0
    running: int | None = None
    events: list[Event] = []
    warnings: list[str] = []
    desync = False
    while pos < limit:
        event_off = pos
        delta, n, delta_raw, vlq_warnings = read_vlq(data, pos, limit)
        if n == 0:
            break
        pos += n
        abs_ticks += delta
        if pos >= limit:
            events.append(Event(event_off, delta_raw, delta, abs_ticks, "truncated", warnings=vlq_warnings + ["missing_status"], status=STAT_DESYNC))
            desync = True
            break
        first = data[pos]
        raw = bytearray(delta_raw)
        used_running = False
        if first == 0xFF:
            raw.append(first); pos += 1
            if pos >= limit:
                events.append(Event(event_off, bytes(raw), delta, abs_ticks, "ff_truncated", warnings=["missing_ff_type"], status=STAT_DESYNC)); desync=True; break
            ff_type = data[pos]; raw.append(ff_type); pos += 1
            if ff_type == 0x2F:
                if pos < limit:
                    raw.append(data[pos]); length = data[pos]; pos += 1
                    if length != 0:
                        take = min(length, limit - pos); raw.extend(data[pos:pos+take]); pos += take
                        warn = ["end_marker_nonzero_length"]
                    else:
                        warn = []
                else:
                    warn = ["end_marker_missing_length"]
                events.append(Event(event_off, bytes(raw), delta, abs_ticks, "end_of_track", warnings=vlq_warnings + warn))
                break
            payload = bytes(data[pos:limit])
            raw.extend(payload); pos = limit
            events.append(Event(event_off, bytes(raw), delta, abs_ticks, "unknown_ff_marker", values={"marker": ff_type}, warnings=vlq_warnings + ["unknown_ff_marker_preserved"], status=STAT_UNSUPPORTED))
            break
        if first & 0x80:
            status = first; raw.append(first); pos += 1; running = status
        elif running is not None:
            status = running; used_running = True
        else:
            raw.append(first); pos += 1
            events.append(Event(event_off, bytes(raw), delta, abs_ticks, "unsupported_raw", warnings=vlq_warnings + ["data_byte_without_running_status"], status=STAT_DESYNC))
            desync = True; continue
        kind = status & 0xF0
        if kind not in SUPPORTED:
            events.append(Event(event_off, bytes(raw), delta, abs_ticks, "unsupported_raw", channel=status & 0x0F, values={"status": status}, warnings=vlq_warnings + ["unsupported_status"], status=STAT_UNSUPPORTED))
            continue
        need = 2
        if pos + need > limit:
            raw.extend(data[pos:limit]); pos = limit; desync = True
            events.append(Event(event_off, bytes(raw), delta, abs_ticks, SUPPORTED[kind], channel=status & 0x0F, warnings=vlq_warnings + ["truncated_event"], status=STAT_DESYNC))
            break
        d1, d2 = data[pos], data[pos+1]; raw.extend([d1, d2]); pos += 2
        vals = {"data1": d1, "data2": d2}
        if kind in (0x80, 0x90): vals = {"note": d1, "velocity": d2}
        elif kind == 0xB0: vals = {"controller": d1, "value": d2}
        elif kind == 0xE0: vals = {"lsb": d1, "msb": d2, "value14": d1 | (d2 << 7)}
        ew = vlq_warnings + (["running_status"] if used_running else [])
        events.append(Event(event_off, bytes(raw), delta, abs_ticks, SUPPORTED[kind], channel=status & 0x0F, values=vals, warnings=ew))
    status = STAT_DESYNC if desync else (STAT_CONFIRMED if events and all(e.status == STAT_CONFIRMED for e in events) else STAT_PARTIAL)
    return events, warnings, status


def parse_scei_midi(data: bytes, source: str | None = None) -> dict[str, Any]:
    header = parse_header(data)
    block_size = header.get("block_size") or len(data)
    end = min(block_size, len(data)) if block_size >= 0x21 else len(data)
    events, warnings, status = parse_events(data, 0x21, end)
    if header["signature"] not in ("SCEIMidi", "IECSidiM"):
        warnings.append("unexpected_signature")
        status = STAT_PARTIAL if status == STAT_CONFIRMED else status
    return {"source": source, "parser_status": status, "header": header, "timing": parse_timing(data), "events": [e.as_dict() for e in events], "warnings": warnings, "midi_emitted": False, "midi_emit_reason": "conversion_not_structurally_validated"}


def write_reports(report: dict[str, Any], out_base: Path) -> tuple[Path, Path]:
    out_base.parent.mkdir(parents=True, exist_ok=True)
    json_path = out_base.with_suffix(".json")
    txt_path = out_base.with_suffix(".txt")
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [f"SCEIMidi report: {report.get('source')}", f"status: {report['parser_status']}", f"signature: {report['header']['signature']}", f"tpqn: {report['timing']['ticks_per_quarter_note']['value']}", "events:"]
    for e in report["events"]:
        lines.append(f"  @{e['offset']:08x} +{e['delta_ticks']} t={e['absolute_ticks']} {e['event_type']} ch={e['channel']} raw={e['raw_bytes']} warn={','.join(e['warnings'])}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, txt_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="output report base path; .json/.txt are written")
    ns = ap.parse_args()
    data = ns.input.read_bytes()
    report = parse_scei_midi(data, str(ns.input))
    base = ns.out or ns.input.with_suffix(".scei_midi")
    write_reports(report, base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

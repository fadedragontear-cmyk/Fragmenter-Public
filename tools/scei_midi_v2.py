#!/usr/bin/env python3
"""SCEIMidi parser v2 with complete basic channel-message widths.

The v1 parser omitted MIDI Program Change (0xC0) and assumed every channel message
carried two data bytes.  That discarded the strongest available sequence-to-program
routing evidence.  v2 preserves the conservative custom-stream framing while
parsing Program Change and Channel Pressure as one-data-byte channel messages.
"""
from __future__ import annotations

from typing import Any

import scei_midi as v1

STAT_CONFIRMED = v1.STAT_CONFIRMED
STAT_PARTIAL = v1.STAT_PARTIAL
STAT_DESYNC = v1.STAT_DESYNC
STAT_UNSUPPORTED = v1.STAT_UNSUPPORTED

CHANNEL_MESSAGES = {
    0x80: ("note_off", 2),
    0x90: ("note_on", 2),
    0xA0: ("poly_pressure", 2),
    0xB0: ("control_change", 2),
    0xC0: ("program_change", 1),
    0xD0: ("channel_pressure", 1),
    0xE0: ("pitch_wheel", 2),
}


def _values(kind: int, data: list[int]) -> dict[str, int]:
    if kind in (0x80, 0x90):
        return {"note": data[0], "velocity": data[1]}
    if kind == 0xA0:
        return {"note": data[0], "pressure": data[1]}
    if kind == 0xB0:
        return {"controller": data[0], "value": data[1]}
    if kind == 0xC0:
        return {"program": data[0], "program_index": data[0]}
    if kind == 0xD0:
        return {"pressure": data[0]}
    if kind == 0xE0:
        return {"lsb": data[0], "msb": data[1], "value14": data[0] | (data[1] << 7)}
    return {f"data{index + 1}": value for index, value in enumerate(data)}


def parse_events(data: bytes, start: int = 0x21, end: int | None = None) -> tuple[list[v1.Event], list[str], str]:
    limit = min(end or len(data), len(data))
    pos = start
    absolute_ticks = 0
    running: int | None = None
    events: list[v1.Event] = []
    warnings: list[str] = []
    desync = False

    while pos < limit:
        event_offset = pos
        delta, count, delta_raw, vlq_warnings = v1.read_vlq(data, pos, limit)
        if count == 0:
            break
        pos += count
        absolute_ticks += delta
        if pos >= limit:
            events.append(v1.Event(event_offset, delta_raw, delta, absolute_ticks, "truncated", warnings=vlq_warnings + ["missing_status"], status=STAT_DESYNC))
            desync = True
            break

        first = data[pos]
        raw = bytearray(delta_raw)
        used_running = False
        if first == 0xFF:
            raw.append(first)
            pos += 1
            if pos >= limit:
                events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "ff_truncated", warnings=["missing_ff_type"], status=STAT_DESYNC))
                desync = True
                break
            ff_type = data[pos]
            raw.append(ff_type)
            pos += 1
            if ff_type == 0x2F:
                if pos < limit:
                    length = data[pos]
                    raw.append(length)
                    pos += 1
                    take = min(length, limit - pos)
                    raw.extend(data[pos : pos + take])
                    pos += take
                    marker_warnings = ["end_marker_nonzero_length"] if length else []
                else:
                    marker_warnings = ["end_marker_missing_length"]
                events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "end_of_track", warnings=vlq_warnings + marker_warnings))
                break
            payload = bytes(data[pos:limit])
            raw.extend(payload)
            pos = limit
            events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "unknown_ff_marker", values={"marker": ff_type}, warnings=vlq_warnings + ["unknown_ff_marker_preserved"], status=STAT_UNSUPPORTED))
            break

        if first & 0x80:
            status = first
            raw.append(first)
            pos += 1
            running = status
        elif running is not None:
            status = running
            used_running = True
        else:
            raw.append(first)
            pos += 1
            events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "unsupported_raw", warnings=vlq_warnings + ["data_byte_without_running_status"], status=STAT_DESYNC))
            desync = True
            continue

        kind = status & 0xF0
        message = CHANNEL_MESSAGES.get(kind)
        if message is None:
            events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "unsupported_raw", channel=status & 0x0F, values={"status": status}, warnings=vlq_warnings + ["unsupported_status"], status=STAT_UNSUPPORTED))
            running = None if status >= 0xF0 else running
            continue
        event_type, data_width = message
        if pos + data_width > limit:
            raw.extend(data[pos:limit])
            pos = limit
            desync = True
            events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, event_type, channel=status & 0x0F, warnings=vlq_warnings + ["truncated_event"], status=STAT_DESYNC))
            break
        values_raw = list(data[pos : pos + data_width])
        raw.extend(values_raw)
        pos += data_width
        event_warnings = vlq_warnings + (["running_status"] if used_running else [])
        events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, event_type, channel=status & 0x0F, values=_values(kind, values_raw), warnings=event_warnings))

    status = STAT_DESYNC if desync else (STAT_CONFIRMED if events and all(event.status == STAT_CONFIRMED for event in events) else STAT_PARTIAL)
    return events, warnings, status


def attach_program_state(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate note events with the Program active on their MIDI channel."""
    channel_programs: dict[int, int] = {}
    output: list[dict[str, Any]] = []
    for raw in sorted(events, key=lambda row: (int(row.get("absolute_ticks") or 0), int(row.get("offset") or 0))):
        event = dict(raw)
        values = dict(event.get("values") or {})
        channel = event.get("channel")
        if event.get("event_type") == "program_change" and isinstance(channel, int):
            program = values.get("program")
            if isinstance(program, int):
                channel_programs[channel] = program
                event["active_program"] = program
        elif event.get("event_type") in {"note_on", "note_off", "poly_pressure", "control_change", "pitch_wheel", "channel_pressure"} and isinstance(channel, int):
            event["active_program"] = channel_programs.get(channel, 0)
            if event.get("event_type") == "note_on":
                event["program_index"] = channel_programs.get(channel, 0)
        output.append(event)
    return output


def parse_scei_midi(data: bytes, source: str | None = None) -> dict[str, Any]:
    header = v1.parse_header(data)
    block_size = header.get("block_size") or len(data)
    end = min(block_size, len(data)) if block_size >= 0x21 else len(data)
    events, warnings, status = parse_events(data, 0x21, end)
    if header["signature"] not in ("SCEIMidi", "IECSidiM"):
        warnings.append("unexpected_signature")
        status = STAT_PARTIAL if status == STAT_CONFIRMED else status
    event_rows = attach_program_state([event.as_dict() for event in events])
    program_changes = [row for row in event_rows if row.get("event_type") == "program_change"]
    channels = sorted({int(row["channel"]) for row in event_rows if isinstance(row.get("channel"), int)})
    programs_by_channel = {
        str(channel): sorted({int(row["values"]["program"]) for row in program_changes if row.get("channel") == channel and isinstance((row.get("values") or {}).get("program"), int)})
        for channel in channels
    }
    return {
        "version": 2,
        "source": source,
        "parser_status": status,
        "header": header,
        "timing": v1.parse_timing(data),
        "events": event_rows,
        "warnings": warnings,
        "program_change_count": len(program_changes),
        "programs_by_channel": programs_by_channel,
        "midi_emitted": False,
        "midi_emit_reason": "custom SCEI stream retained; renderer consumes parsed event state directly",
    }

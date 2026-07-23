#!/usr/bin/env python3
"""SCEIMidi parser v3 for the observed Fragment track framing.

The custom stream is MIDI-like, but it is not a Standard MIDI file.  Observed
track data begins with a six-byte preamble::

    FF 0A <track-length-byte> <name/null-byte> <tpqn-le16>

Earlier Fragmenter parsers started VLQ/delta parsing at the leading FF byte and
therefore desynchronized before the first note event.  V3 parses the preamble
first, then decodes bounded MIDI-like events until FF 2F end-of-track.

Unknown FF markers are preserved using MIDI-style length framing when possible;
they no longer consume the remainder of the section unconditionally.
"""
from __future__ import annotations

from typing import Any

import scei_midi as v1
import scei_midi_v2 as v2

STAT_CONFIRMED = v1.STAT_CONFIRMED
STAT_PARTIAL = v1.STAT_PARTIAL
STAT_DESYNC = v1.STAT_DESYNC
STAT_UNSUPPORTED = v1.STAT_UNSUPPORTED
TRACK_PREAMBLE = b"\xff\x0a"
CHANNEL_MESSAGES = v2.CHANNEL_MESSAGES


def _event_values(kind: int, data: list[int]) -> dict[str, int]:
    return v2._values(kind, data)


def parse_track_preamble(data: bytes, offset: int, limit: int) -> dict[str, Any] | None:
    if offset < 0 or offset + 6 > limit or data[offset : offset + 2] != TRACK_PREAMBLE:
        return None
    return {
        "offset": offset,
        "raw_bytes": data[offset : offset + 6].hex(),
        "marker": "FF0A",
        "track_length_byte": data[offset + 2],
        "track_length_low6": data[offset + 2] & 0x3F,
        "track_length_high2": data[offset + 2] >> 6,
        "name_or_null": data[offset + 3],
        "ticks_per_quarter_note": int.from_bytes(data[offset + 4 : offset + 6], "little"),
        "event_stream_offset": offset + 6,
    }


def _parse_meta_event(data: bytes, pos: int, limit: int, event_offset: int, delta_raw: bytes, delta: int, absolute_ticks: int, vlq_warnings: list[str]) -> tuple[v1.Event, int, bool]:
    raw = bytearray(delta_raw)
    raw.append(0xFF)
    pos += 1
    if pos >= limit:
        return v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "ff_truncated", warnings=vlq_warnings + ["missing_ff_type"], status=STAT_DESYNC), pos, True
    ff_type = data[pos]
    raw.append(ff_type)
    pos += 1
    if ff_type == 0x2F:
        if pos >= limit:
            return v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "end_of_track", warnings=vlq_warnings + ["end_marker_missing_length"], status=STAT_PARTIAL), pos, True
        length, count, length_raw, length_warnings = v1.read_vlq(data, pos, limit)
        raw.extend(length_raw)
        pos += count
        take = min(length, max(0, limit - pos))
        raw.extend(data[pos : pos + take])
        pos += take
        warnings = vlq_warnings + length_warnings
        if length:
            warnings.append("end_marker_nonzero_length")
        if take != length:
            warnings.append("end_marker_payload_truncated")
        return v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "end_of_track", values={"length": length}, warnings=warnings, status=STAT_CONFIRMED if not warnings else STAT_PARTIAL), pos, True

    length, count, length_raw, length_warnings = v1.read_vlq(data, pos, limit)
    if count == 0:
        return v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "meta_truncated", values={"marker": ff_type}, warnings=vlq_warnings + ["missing_meta_length"], status=STAT_DESYNC), pos, True
    raw.extend(length_raw)
    pos += count
    take = min(length, max(0, limit - pos))
    payload = data[pos : pos + take]
    raw.extend(payload)
    pos += take
    warnings = vlq_warnings + length_warnings
    if take != length:
        warnings.append("meta_payload_truncated")
    status = STAT_UNSUPPORTED if take == length else STAT_DESYNC
    return v1.Event(
        event_offset,
        bytes(raw),
        delta,
        absolute_ticks,
        "meta_event",
        values={"marker": ff_type, "length": length, "payload_hex": payload.hex()},
        warnings=warnings + ["meta_event_preserved"],
        status=status,
    ), pos, take != length


def parse_track_events(data: bytes, start: int, limit: int, *, track_index: int) -> tuple[list[dict[str, Any]], list[str], str, int]:
    pos = start
    absolute_ticks = 0
    running: int | None = None
    events: list[v1.Event] = []
    warnings: list[str] = []
    desync = False
    ended = False

    while pos < limit:
        event_offset = pos
        # Alignment/padding after a track is not an event stream.  Leave it for
        # the outer track scanner rather than turning FF padding into a giant VLQ.
        if data[pos : pos + 2] == TRACK_PREAMBLE:
            warnings.append("next_track_preamble_before_end_marker")
            break
        if data[pos] == 0xFF and all(value == 0xFF for value in data[pos : min(limit, pos + 8)]):
            break

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
        if first == 0xFF:
            event, pos, stop = _parse_meta_event(data, pos, limit, event_offset, delta_raw, delta, absolute_ticks, vlq_warnings)
            events.append(event)
            if event.event_type == "end_of_track":
                ended = True
            if stop:
                break
            continue

        raw = bytearray(delta_raw)
        used_running = False
        if first & 0x80:
            status_byte = first
            raw.append(first)
            pos += 1
            running = status_byte if status_byte < 0xF0 else None
        elif running is not None:
            status_byte = running
            used_running = True
        else:
            raw.append(first)
            pos += 1
            events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "unsupported_raw", warnings=vlq_warnings + ["data_byte_without_running_status"], status=STAT_DESYNC))
            desync = True
            continue

        kind = status_byte & 0xF0
        message = CHANNEL_MESSAGES.get(kind)
        if message is None:
            events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, "unsupported_raw", channel=status_byte & 0x0F, values={"status": status_byte}, warnings=vlq_warnings + ["unsupported_status"], status=STAT_UNSUPPORTED))
            continue
        event_type, data_width = message
        if pos + data_width > limit:
            raw.extend(data[pos:limit])
            pos = limit
            events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, event_type, channel=status_byte & 0x0F, warnings=vlq_warnings + ["truncated_event"], status=STAT_DESYNC))
            desync = True
            break
        values_raw = list(data[pos : pos + data_width])
        raw.extend(values_raw)
        pos += data_width
        event_warnings = vlq_warnings + (["running_status"] if used_running else [])
        events.append(v1.Event(event_offset, bytes(raw), delta, absolute_ticks, event_type, channel=status_byte & 0x0F, values=_event_values(kind, values_raw), warnings=event_warnings))

    event_rows = v2.attach_program_state([event.as_dict() for event in events])
    # V2 defaulted a channel with no observed C0 to Program 0.  Preserve the
    # event timeline, but remove that invented authority for forensic/routing use.
    channel_program_seen: dict[int, bool] = {}
    for event in event_rows:
        channel = event.get("channel")
        if event.get("event_type") == "program_change" and isinstance(channel, int):
            channel_program_seen[channel] = True
        elif event.get("event_type") == "note_on" and isinstance(channel, int) and not channel_program_seen.get(channel):
            event.pop("program_index", None)
            event.pop("active_program", None)
            event["program_state_source"] = "no_program_change_observed"
        elif isinstance(channel, int) and channel_program_seen.get(channel):
            event["program_state_source"] = "program_change"

    statuses = [event.get("status") for event in event_rows]
    if desync:
        parser_status = STAT_DESYNC
    elif event_rows and all(status == STAT_CONFIRMED for status in statuses):
        parser_status = STAT_CONFIRMED
    else:
        parser_status = STAT_PARTIAL
    if not ended:
        warnings.append("track_end_marker_not_observed")
    return event_rows, warnings, parser_status, pos


def _next_track_preamble(data: bytes, start: int, limit: int) -> int | None:
    hit = data.find(TRACK_PREAMBLE, max(0, start), limit)
    return hit if hit >= 0 else None


def parse_scei_midi(data: bytes, source: str | None = None) -> dict[str, Any]:
    header = v1.parse_header(data)
    block_size = int(header.get("block_size") or len(data))
    limit = min(block_size, len(data)) if block_size >= 0x21 else len(data)
    tracks: list[dict[str, Any]] = []
    warnings: list[str] = []
    cursor = 0x21
    track_index = 0

    while cursor < limit:
        preamble_offset = _next_track_preamble(data, cursor, limit)
        if preamble_offset is None:
            trailing = data[cursor:limit]
            if trailing and any(value != 0xFF for value in trailing):
                warnings.append(f"non_ff_trailing_bytes_without_track_preamble@0x{cursor:X}")
            break
        if preamble_offset > cursor:
            skipped = data[cursor:preamble_offset]
            if any(value != 0xFF for value in skipped):
                warnings.append(f"skipped_bytes_before_track_{track_index}@0x{cursor:X}:{skipped[:32].hex()}")
        preamble = parse_track_preamble(data, preamble_offset, limit)
        if preamble is None:
            warnings.append(f"truncated_track_preamble@0x{preamble_offset:X}")
            break
        events, track_warnings, status, end_offset = parse_track_events(data, int(preamble["event_stream_offset"]), limit, track_index=track_index)
        for event in events:
            event["track_index"] = track_index
        tracks.append(
            {
                "track_index": track_index,
                "preamble": preamble,
                "events": events,
                "event_count": len(events),
                "parser_status": status,
                "warnings": track_warnings,
                "end_offset": end_offset,
                "event_types": _counts(event.get("event_type") for event in events),
                "channels": sorted({int(event["channel"]) for event in events if isinstance(event.get("channel"), int)}),
            }
        )
        track_index += 1
        cursor = max(end_offset, preamble_offset + 6)
        next_hit = _next_track_preamble(data, cursor, limit)
        if next_hit is None:
            break
        cursor = next_hit

    event_rows = [event for track in tracks for event in track["events"]]
    program_changes = [event for event in event_rows if event.get("event_type") == "program_change"]
    channels = sorted({int(event["channel"]) for event in event_rows if isinstance(event.get("channel"), int)})
    note_channels = sorted({int(event["channel"]) for event in event_rows if event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0 and isinstance(event.get("channel"), int)})
    programs_by_channel = {
        str(channel): sorted({int((event.get("values") or {})["program"]) for event in program_changes if event.get("channel") == channel and isinstance((event.get("values") or {}).get("program"), int)})
        for channel in channels
    }
    status = STAT_DESYNC if any(track["parser_status"] == STAT_DESYNC for track in tracks) else STAT_CONFIRMED if tracks and all(track["parser_status"] == STAT_CONFIRMED for track in tracks) else STAT_PARTIAL
    if header["signature"] not in ("SCEIMidi", "IECSidiM"):
        warnings.append("unexpected_signature")
        status = STAT_PARTIAL if status == STAT_CONFIRMED else status
    return {
        "version": 3,
        "source": source,
        "parser_status": status,
        "header": header,
        "timing": v1.parse_timing(data),
        "tracks": tracks,
        "events": event_rows,
        "warnings": warnings,
        "track_count": len(tracks),
        "event_count": len(event_rows),
        "event_types": _counts(event.get("event_type") for event in event_rows),
        "program_change_count": len(program_changes),
        "programs_by_channel": programs_by_channel,
        "channels": channels,
        "note_channels": note_channels,
        "notes_without_program_change": sum(1 for event in event_rows if event.get("event_type") == "note_on" and event.get("program_state_source") == "no_program_change_observed"),
        "midi_emitted": False,
        "midi_emit_reason": "custom SCEI track framing retained; renderer consumes parsed event timeline directly",
    }


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts

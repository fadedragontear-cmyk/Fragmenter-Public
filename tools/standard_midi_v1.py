#!/usr/bin/env python3
"""Small standard-MIDI parser/writer used by Fragmenter's Original Sequencer.

The reader supports SMF format 0/1, running status, tempo events, Program Change,
Note On, and Note Off. SMPTE time division is intentionally rejected for the first
public pass so timing behavior stays explicit.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

DEFAULT_TEMPO_US = 500_000
DEFAULT_NOTE_SECONDS = 0.25


class MidiFormatError(ValueError):
    pass


def _vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise MidiFormatError("truncated variable-length quantity")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            return value, offset
    raise MidiFormatError("variable-length quantity exceeds four bytes")


def _encode_vlq(value: int) -> bytes:
    value = max(0, int(value))
    buffer = value & 0x7F
    output = bytearray([buffer])
    value >>= 7
    while value:
        buffer = (value & 0x7F) | 0x80
        output.insert(0, buffer)
        value >>= 7
    return bytes(output)


def _parse_track(data: bytes, track_index: int) -> dict[str, Any]:
    offset = 0
    absolute_ticks = 0
    running_status: int | None = None
    events: list[dict[str, Any]] = []
    name = ""

    while offset < len(data):
        delta, offset = _vlq(data, offset)
        absolute_ticks += delta
        if offset >= len(data):
            break

        lead = data[offset]
        if lead < 0x80:
            if running_status is None:
                raise MidiFormatError(f"track {track_index}: running status without prior status")
            status = running_status
        else:
            status = lead
            offset += 1
            if status < 0xF0:
                running_status = status

        if status == 0xFF:
            running_status = None
            if offset >= len(data):
                raise MidiFormatError("truncated meta event")
            meta_type = data[offset]
            offset += 1
            length, offset = _vlq(data, offset)
            payload = data[offset:offset + length]
            if len(payload) != length:
                raise MidiFormatError("truncated meta payload")
            offset += length
            row: dict[str, Any] = {
                "track_index": track_index,
                "absolute_ticks": absolute_ticks,
                "event_type": "meta",
                "meta_type": meta_type,
                "data_hex": payload.hex(),
            }
            if meta_type == 0x03:
                name = payload.decode("latin-1", "replace")
                row["track_name"] = name
            elif meta_type == 0x51 and len(payload) == 3:
                row["event_type"] = "tempo"
                row["tempo_us_per_quarter"] = int.from_bytes(payload, "big")
            elif meta_type == 0x2F:
                row["event_type"] = "end_of_track"
                events.append(row)
                break
            events.append(row)
            continue

        if status in {0xF0, 0xF7}:
            running_status = None
            length, offset = _vlq(data, offset)
            offset += length
            if offset > len(data):
                raise MidiFormatError("truncated SysEx payload")
            continue

        event_class = status >> 4
        channel = status & 0x0F
        data_length = 1 if event_class in {0xC, 0xD} else 2
        payload = data[offset:offset + data_length]
        if len(payload) != data_length:
            raise MidiFormatError("truncated channel event")
        offset += data_length

        row = {
            "track_index": track_index,
            "absolute_ticks": absolute_ticks,
            "channel": channel,
            "status": status,
            "data": list(payload),
        }
        if event_class == 0x8:
            row.update({"event_type": "note_off", "note": payload[0], "velocity": payload[1]})
        elif event_class == 0x9:
            row.update({
                "event_type": "note_off" if payload[1] == 0 else "note_on",
                "note": payload[0],
                "velocity": payload[1],
            })
        elif event_class == 0xC:
            row.update({"event_type": "program_change", "program": payload[0]})
        else:
            row["event_type"] = "channel_event"
        events.append(row)

    return {"track_index": track_index, "name": name, "events": events}


def _tempo_segments(events: list[dict[str, Any]], ticks_per_quarter: int) -> list[dict[str, Any]]:
    changes = sorted(
        (
            (int(event["absolute_ticks"]), int(event["tempo_us_per_quarter"]))
            for event in events
            if event.get("event_type") == "tempo"
        ),
        key=lambda item: item[0],
    )
    deduped: list[tuple[int, int]] = [(0, DEFAULT_TEMPO_US)]
    for tick, tempo in changes:
        if tick == deduped[-1][0]:
            deduped[-1] = (tick, tempo)
        else:
            deduped.append((tick, tempo))

    segments: list[dict[str, Any]] = []
    seconds = 0.0
    for index, (tick, tempo) in enumerate(deduped):
        if index:
            previous = deduped[index - 1]
            seconds += (tick - previous[0]) * previous[1] / 1_000_000.0 / ticks_per_quarter
        segments.append({"tick": tick, "tempo_us_per_quarter": tempo, "seconds": seconds})
    return segments


def _seconds_at_tick(tick: int, segments: list[dict[str, Any]], ticks_per_quarter: int) -> float:
    segment = segments[0]
    for candidate in segments[1:]:
        if int(candidate["tick"]) > tick:
            break
        segment = candidate
    return float(segment["seconds"]) + (
        tick - int(segment["tick"])
    ) * int(segment["tempo_us_per_quarter"]) / 1_000_000.0 / ticks_per_quarter


def parse_midi_bytes(data: bytes, source: str = "<memory>") -> dict[str, Any]:
    if len(data) < 14 or data[:4] != b"MThd":
        raise MidiFormatError("not a Standard MIDI File")
    header_size = struct.unpack_from(">I", data, 4)[0]
    if header_size < 6 or 8 + header_size > len(data):
        raise MidiFormatError("invalid MIDI header length")
    midi_format, track_count, division = struct.unpack_from(">HHH", data, 8)
    if division & 0x8000:
        raise MidiFormatError("SMPTE time division is not supported yet")
    ticks_per_quarter = int(division)
    if ticks_per_quarter <= 0:
        raise MidiFormatError("ticks-per-quarter must be positive")

    offset = 8 + header_size
    tracks: list[dict[str, Any]] = []
    for track_index in range(track_count):
        if offset + 8 > len(data) or data[offset:offset + 4] != b"MTrk":
            raise MidiFormatError(f"missing MTrk chunk {track_index}")
        size = struct.unpack_from(">I", data, offset + 4)[0]
        start = offset + 8
        end = start + size
        if end > len(data):
            raise MidiFormatError(f"truncated MTrk chunk {track_index}")
        tracks.append(_parse_track(data[start:end], track_index))
        offset = end

    events = sorted(
        (event for track in tracks for event in track["events"]),
        key=lambda event: (
            int(event.get("absolute_ticks") or 0),
            int(event.get("track_index") or 0),
            0 if event.get("event_type") == "program_change" else 1,
        ),
    )
    tempo_segments = _tempo_segments(events, ticks_per_quarter)
    programs = [0] * 16
    active: dict[tuple[int, int], list[dict[str, Any]]] = {}
    notes: list[dict[str, Any]] = []

    for event in events:
        kind = event.get("event_type")
        channel = int(event.get("channel") or 0)
        if kind == "program_change":
            programs[channel] = int(event.get("program") or 0)
            continue
        if kind == "note_on":
            key = (channel, int(event["note"]))
            active.setdefault(key, []).append(
                {
                    "track_index": int(event.get("track_index") or 0),
                    "channel": channel,
                    "note": int(event["note"]),
                    "velocity": int(event.get("velocity") or 1),
                    "program": programs[channel],
                    "start_tick": int(event["absolute_ticks"]),
                }
            )
            continue
        if kind != "note_off":
            continue
        key = (channel, int(event["note"]))
        queue = active.get(key) or []
        if not queue:
            continue
        note = queue.pop(0)
        note["end_tick"] = max(note["start_tick"] + 1, int(event["absolute_ticks"]))
        notes.append(note)

    final_tick = max((int(event.get("absolute_ticks") or 0) for event in events), default=0)
    for queue in active.values():
        for note in queue:
            note["end_tick"] = max(
                note["start_tick"] + max(1, ticks_per_quarter // 2),
                final_tick,
            )
            notes.append(note)

    for note in notes:
        start_seconds = _seconds_at_tick(note["start_tick"], tempo_segments, ticks_per_quarter)
        end_seconds = _seconds_at_tick(note["end_tick"], tempo_segments, ticks_per_quarter)
        note["start_seconds"] = start_seconds
        note["duration_seconds"] = max(DEFAULT_NOTE_SECONDS / 4.0, end_seconds - start_seconds)

    notes.sort(key=lambda row: (row["start_seconds"], row["channel"], row["note"]))
    channels: list[dict[str, Any]] = []
    for channel in sorted({int(note["channel"]) for note in notes}):
        subset = [note for note in notes if int(note["channel"]) == channel]
        programs_used = sorted({int(note["program"]) for note in subset})
        channels.append(
            {
                "channel": channel,
                "display_channel": channel + 1,
                "note_count": len(subset),
                "programs": programs_used,
                "lowest_note": min(int(note["note"]) for note in subset),
                "highest_note": max(int(note["note"]) for note in subset),
                "first_seconds": min(float(note["start_seconds"]) for note in subset),
                "last_seconds": max(
                    float(note["start_seconds"]) + float(note["duration_seconds"])
                    for note in subset
                ),
            }
        )

    duration = max(
        (
            float(note["start_seconds"]) + float(note["duration_seconds"])
            for note in notes
        ),
        default=0.0,
    )
    return {
        "source": source,
        "format": midi_format,
        "track_count": track_count,
        "ticks_per_quarter": ticks_per_quarter,
        "tracks": tracks,
        "tempo_segments": tempo_segments,
        "notes": notes,
        "channels": channels,
        "summary": {
            "tracks": track_count,
            "events": len(events),
            "notes": len(notes),
            "channels": len(channels),
            "duration_seconds": duration,
            "tempo_changes": len(tempo_segments),
        },
    }


def parse_midi_file(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    return parse_midi_bytes(source.read_bytes(), str(source))


def write_original_demo_midi(path: str | Path, *, ticks_per_quarter: int = 480) -> Path:
    """Write a small original progression for testing classified Fragment samples."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    events: list[tuple[int, bytes]] = []
    events.append((0, b"\xff\x51\x03" + (500_000).to_bytes(3, "big")))
    events.append((0, b"\xff\x03\x18Fragmenter Original Demo"))

    chords = (
        (48, 55, 60),
        (45, 52, 57),
        (41, 48, 53),
        (43, 50, 55),
    ) * 2
    melody = (72, 74, 76, 79, 76, 74, 71, 74) * 2
    timeline: list[tuple[int, bytes]] = []
    bar_ticks = ticks_per_quarter * 4
    for bar, chord in enumerate(chords):
        start = bar * bar_ticks
        end = start + bar_ticks - 30
        for note in chord:
            timeline.append((start, bytes([0x90, note, 78])))
            timeline.append((end, bytes([0x80, note, 0])))
        for step in range(2):
            note = melody[bar * 2 + step]
            note_start = start + step * ticks_per_quarter * 2
            timeline.append((note_start, bytes([0x91, note, 104])))
            timeline.append((note_start + ticks_per_quarter * 2 - 30, bytes([0x81, note, 0])))
    timeline.sort(key=lambda item: (item[0], 0 if item[1][0] & 0xF0 == 0x80 else 1))

    previous = 0
    track = bytearray()
    for tick, payload in [*events, *timeline]:
        delta = max(0, tick - previous)
        track.extend(_encode_vlq(delta))
        track.extend(payload)
        previous = tick
    track.extend(_encode_vlq(0))
    track.extend(b"\xff\x2f\x00")

    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ticks_per_quarter)
    body = b"MTrk" + struct.pack(">I", len(track)) + bytes(track)
    target.write_bytes(header + body)
    return target


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's Original Sequencer.")

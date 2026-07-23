#!/usr/bin/env python3
"""SCEIMidi v4: preserve v3 framing but stop routing authority at invalid data.

The Fragment stream is MIDI-like, not a Standard MIDI file.  Even so, the
channel-message interpretation used by v2/v3 requires 7-bit data bytes.  V4
therefore treats the first decoded channel value outside 0..127 as a hard
forensic boundary.  Events before that boundary remain available; the invalid
event and everything after it are excluded from Program/note routing.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import scei_midi_v3 as v3

STAT_CONFIRMED = v3.STAT_CONFIRMED
STAT_PARTIAL = v3.STAT_PARTIAL
STAT_DESYNC = v3.STAT_DESYNC
STAT_UNSUPPORTED = v3.STAT_UNSUPPORTED

_DATA_KEYS: dict[str, tuple[str, ...]] = {
    "note_off": ("note", "velocity"),
    "note_on": ("note", "velocity"),
    "poly_pressure": ("note", "pressure"),
    "control_change": ("controller", "value"),
    "program_change": ("program",),
    "channel_pressure": ("pressure",),
    "pitch_wheel": ("lsb", "msb"),
}


def _counts(values) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def invalid_channel_values(event: dict[str, Any]) -> list[dict[str, Any]]:
    keys = _DATA_KEYS.get(str(event.get("event_type") or ""), ())
    values = event.get("values") or {}
    rows: list[dict[str, Any]] = []
    for key in keys:
        value = values.get(key)
        if isinstance(value, int) and not 0 <= value <= 0x7F:
            rows.append({"field": key, "value": value, "hex": f"0x{value:02X}"})
    return rows


def _strict_track(track: dict[str, Any]) -> dict[str, Any]:
    source_events = [dict(event) for event in track.get("events") or [] if isinstance(event, dict)]
    first_invalid: dict[str, Any] | None = None
    trusted: list[dict[str, Any]] = []
    for index, event in enumerate(source_events):
        invalid = invalid_channel_values(event)
        if invalid:
            first_invalid = {
                "event_index": index,
                "offset": event.get("offset"),
                "absolute_ticks": event.get("absolute_ticks"),
                "event_type": event.get("event_type"),
                "channel": event.get("channel"),
                "raw_bytes": event.get("raw_bytes"),
                "values": event.get("values"),
                "invalid_values": invalid,
                "reason": "channel_message_data_byte_high_bit_set",
                "preceding_event": trusted[-1] if trusted else None,
            }
            break
        trusted.append(event)

    output = dict(track)
    output["events"] = trusted
    output["event_count"] = len(trusted)
    output["raw_event_count"] = len(source_events)
    output["discarded_event_count"] = len(source_events) - len(trusted)
    output["first_invalid_event"] = first_invalid
    output["strict_valid"] = first_invalid is None
    output["parser_status"] = STAT_DESYNC if first_invalid else track.get("parser_status")
    output["event_types"] = _counts(event.get("event_type") for event in trusted)
    output["channels"] = sorted({int(event["channel"]) for event in trusted if isinstance(event.get("channel"), int)})
    warnings = list(track.get("warnings") or [])
    if first_invalid:
        warnings.append(
            f"strict_high_bit_data_boundary@0x{int(first_invalid.get('offset') or 0):X}:"
            + ",".join(f"{row['field']}={row['value']}" for row in first_invalid["invalid_values"])
        )
    output["warnings"] = warnings
    return output


def parse_scei_midi(data: bytes, source: str | None = None) -> dict[str, Any]:
    raw = v3.parse_scei_midi(data, source)
    tracks = [_strict_track(track) for track in raw.get("tracks") or [] if isinstance(track, dict)]
    events = [event for track in tracks for event in track.get("events") or []]
    program_changes = [event for event in events if event.get("event_type") == "program_change"]
    channels = sorted({int(event["channel"]) for event in events if isinstance(event.get("channel"), int)})
    note_channels = sorted(
        {
            int(event["channel"])
            for event in events
            if event.get("event_type") == "note_on"
            and int((event.get("values") or {}).get("velocity") or 0) > 0
            and isinstance(event.get("channel"), int)
        }
    )
    programs_by_channel = {
        str(channel): sorted(
            {
                int((event.get("values") or {})["program"])
                for event in program_changes
                if event.get("channel") == channel and isinstance((event.get("values") or {}).get("program"), int)
            }
        )
        for channel in channels
    }
    invalid_tracks = [track for track in tracks if track.get("first_invalid_event")]
    warnings = list(raw.get("warnings") or [])
    if invalid_tracks:
        warnings.append(f"strict_validation_rejected_{len(invalid_tracks)}_track(s)")
    status = STAT_DESYNC if invalid_tracks else raw.get("parser_status")
    return {
        **raw,
        "version": 4,
        "parser_status": status,
        "tracks": tracks,
        "events": events,
        "event_count": len(events),
        "raw_event_count": sum(int(track.get("raw_event_count") or 0) for track in tracks),
        "discarded_event_count": sum(int(track.get("discarded_event_count") or 0) for track in tracks),
        "event_types": _counts(event.get("event_type") for event in events),
        "program_change_count": len(program_changes),
        "programs_by_channel": programs_by_channel,
        "channels": channels,
        "note_channels": note_channels,
        "notes_without_program_change": sum(
            1
            for event in events
            if event.get("event_type") == "note_on" and event.get("program_state_source") == "no_program_change_observed"
        ),
        "warnings": warnings,
        "strict_validation": {
            "tracks": len(tracks),
            "valid_tracks": len(tracks) - len(invalid_tracks),
            "invalid_tracks": len(invalid_tracks),
            "first_invalid_event": invalid_tracks[0].get("first_invalid_event") if invalid_tracks else None,
            "authority_rule": "Only events before the first channel data value outside 0..127 may influence routing.",
        },
    }

#!/usr/bin/env python3
"""Multi-part Standard MIDI renderer for classified Fragment sample instruments."""
from __future__ import annotations

import json
from array import array
from pathlib import Path
from typing import Any

import original_sequencer_v1 as v1
from project_sound_v1 import sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from standard_midi_v1 import parse_midi_file

REPORT_NAME = "original_sequencer_last_render_v2.json"


def part_key(track_index: int, channel: int) -> str:
    return f"track:{int(track_index)}:channel:{int(channel)}"


def parts_from_parsed(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for note in parsed.get("notes") or []:
        key = (int(note.get("track_index") or 0), int(note.get("channel") or 0))
        grouped.setdefault(key, []).append(note)
    output: list[dict[str, Any]] = []
    tracks = {
        int(row.get("track_index") or index): str(row.get("name") or "")
        for index, row in enumerate(parsed.get("tracks") or [])
        if isinstance(row, dict)
    }
    for (track, channel), notes in sorted(grouped.items()):
        output.append(
            {
                "key": part_key(track, channel),
                "track_index": track,
                "track_name": tracks.get(track) or f"Track {track + 1}",
                "channel": channel,
                "display_channel": channel + 1,
                "note_count": len(notes),
                "programs": sorted({int(note.get("program") or 0) for note in notes}),
                "lowest_note": min(int(note.get("note") or 0) for note in notes),
                "highest_note": max(int(note.get("note") or 0) for note in notes),
                "first_seconds": min(float(note.get("start_seconds") or 0.0) for note in notes),
                "last_seconds": max(
                    float(note.get("start_seconds") or 0.0)
                    + float(note.get("duration_seconds") or 0.0)
                    for note in notes
                ),
            }
        )
    return output


def _mapping_for_note(
    note: dict[str, Any], mappings: dict[str, Any]
) -> tuple[str, dict[str, Any] | None]:
    track = int(note.get("track_index") or 0)
    channel = int(note.get("channel") or 0)
    key = part_key(track, channel)
    mapping = mappings.get(key)
    if not isinstance(mapping, dict):
        key = str(channel)
        mapping = mappings.get(key)
    return key, mapping if isinstance(mapping, dict) else None


def render_notes(
    notes: list[dict[str, Any]],
    channel_mappings: dict[str, Any],
    *,
    master_gain: float = 0.8,
    tempo_scale: float = 1.0,
    max_seconds: float = v1.MAX_SECONDS,
    output_rate: int = v1.OUTPUT_RATE,
) -> tuple[array, dict[str, Any]]:
    tempo_scale = max(0.25, min(4.0, float(tempo_scale)))
    master_gain = max(0.0, min(2.0, float(master_gain)))
    max_frames = max(1, int(max_seconds * output_rate))
    loaded: dict[str, Any] = {}
    voices: list[dict[str, Any]] = []
    skipped_unmapped = 0
    skipped_disabled = 0
    skipped_muted = 0
    skipped_non_solo = 0
    skipped_after_limit = 0
    solo_active = any(
        isinstance(mapping, dict)
        and bool(mapping.get("solo"))
        and bool(mapping.get("enabled", True))
        and not bool(mapping.get("muted"))
        for mapping in channel_mappings.values()
    )

    for note in notes[: v1.MAX_NOTES]:
        mapping_key, mapping = _mapping_for_note(note, channel_mappings)
        if mapping is None or not mapping.get("output_path"):
            skipped_unmapped += 1
            continue
        if not bool(mapping.get("enabled", True)):
            skipped_disabled += 1
            continue
        if bool(mapping.get("muted")):
            skipped_muted += 1
            continue
        if solo_active and not bool(mapping.get("solo")):
            skipped_non_solo += 1
            continue
        sample_key = str(mapping.get("key") or mapping.get("output_path"))
        if sample_key not in loaded:
            loaded[sample_key] = v1._load_mapping_sample(mapping)
        sample = loaded[sample_key]
        start, end, ratio = v1._voice_bounds(
            note,
            sample,
            mapping,
            tempo_scale=tempo_scale,
            output_rate=output_rate,
        )
        if start >= max_frames:
            skipped_after_limit += 1
            continue
        end = min(end, max_frames)
        if end <= start:
            continue
        velocity = max(1, min(127, int(note.get("velocity") or 127))) / 127.0
        gain = (
            master_gain
            * float(mapping.get("gain") if mapping.get("gain") is not None else 1.0)
            * velocity
        )
        voices.append(
            {
                "start": start,
                "end": end,
                "ratio": ratio,
                "gain": gain,
                "pan": int(mapping.get("pan") if mapping.get("pan") is not None else 64),
                "sample": sample,
                "channel": int(note.get("channel") or 0),
                "track_index": int(note.get("track_index") or 0),
                "note": int(note.get("note") or 60),
                "mapping_key": mapping_key,
                "sample_key": sample_key,
            }
        )

    if not voices:
        raise v1.OriginalSequencerError(
            "No MIDI notes reached an enabled mapped sample. Check part mappings, mute, and solo states."
        )

    frame_count = max(voice["end"] for voice in voices)
    mix = array("f", [0.0]) * (frame_count * 2)
    peak = 0.0
    for voice in voices:
        sample = voice["sample"]
        left_gain, right_gain = v1._pan_gains(voice["pan"])
        for frame in range(voice["start"], voice["end"]):
            source = int(
                (frame - voice["start"])
                * voice["ratio"]
                * sample.sample_rate
                / output_rate
            )
            if source >= len(sample.pcm):
                break
            value = float(sample.pcm[source]) * voice["gain"]
            index = frame * 2
            left = mix[index] + value * left_gain
            right = mix[index + 1] + value * right_gain
            mix[index] = left
            mix[index + 1] = right
            peak = max(peak, abs(left), abs(right))

    scale = 1.0 / peak if peak > 1.0 else 1.0
    if scale != 1.0:
        for index in range(len(mix)):
            mix[index] *= scale

    metadata = {
        "voices": len(voices),
        "mapped_parts": sorted({voice["mapping_key"] for voice in voices}),
        "mapped_channels": sorted({voice["channel"] for voice in voices}),
        "mapped_tracks": sorted({voice["track_index"] for voice in voices}),
        "sample_assets": sorted({voice["sample_key"] for voice in voices}),
        "solo_active": solo_active,
        "skipped_unmapped_notes": skipped_unmapped,
        "skipped_disabled_notes": skipped_disabled,
        "skipped_muted_notes": skipped_muted,
        "skipped_non_solo_notes": skipped_non_solo,
        "skipped_after_time_limit": skipped_after_limit,
        "note_limit": v1.MAX_NOTES,
        "max_seconds": max_seconds,
        "output_rate": output_rate,
        "frames": frame_count,
        "duration_seconds": frame_count / float(output_rate),
        "peak_before_normalization": peak,
        "normalization_scale": scale,
        "tempo_scale": tempo_scale,
        "limitations": [
            "Pitched mode uses nearest-neighbor resampling and no looping.",
            "Pitched notes stop at Note Off or the end of the sample, whichever comes first.",
            "One-shot, Drum, and Texture modes ignore Note Off and play the available sample once.",
            "No ADSR envelope, velocity layers, round robin, or sustain pedal is implemented yet.",
        ],
    }
    return mix, metadata


def render_midi_project(
    project: FragmenterProjectV1,
    midi_path: str | Path,
    channel_mappings: dict[str, Any],
    *,
    master_gain: float = 0.8,
    tempo_scale: float = 1.0,
    output_name: str | None = None,
) -> dict[str, Any]:
    parsed = parse_midi_file(midi_path)
    mix, metadata = render_notes(
        parsed.get("notes") or [],
        channel_mappings,
        master_gain=master_gain,
        tempo_scale=tempo_scale,
    )
    source = Path(midi_path)
    safe_name = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in source.stem
    )
    target = (
        sound_decoded_root(project)
        / "original_sequencer"
        / (output_name or f"{safe_name}_fragment_samples.wav")
    )
    v1.write_stereo_wav(target, mix, v1.OUTPUT_RATE)
    report = {
        "status": "rendered_multitrack",
        "source_midi": str(source),
        "output_path": str(target),
        "midi_summary": parsed.get("summary") or {},
        "parts": parts_from_parsed(parsed),
        "channel_mappings": channel_mappings,
        "metadata": metadata,
    }
    report_path = sound_reports_root(project) / REPORT_NAME
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    report["report_path"] = str(report_path)
    return report


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's Original Sequencer.")

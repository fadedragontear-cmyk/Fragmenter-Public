#!/usr/bin/env python3
"""Render Standard MIDI notes with classified Fragment SNDDATA sample WAVs."""
from __future__ import annotations

import json
import math
import os
import wave
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import snddata_music_system_v3 as music_v3
from project_sound_v1 import sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from standard_midi_v1 import parse_midi_file

STATE_NAME = "original_sequencer_state_v1.json"
REPORT_NAME = "original_sequencer_last_render_v1.json"
MAX_SECONDS = 90.0
MAX_NOTES = 4096
OUTPUT_RATE = 44100


class OriginalSequencerError(RuntimeError):
    pass


def state_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / STATE_NAME


def load_state(project: FragmenterProjectV1) -> dict[str, Any]:
    path = state_path(project)
    if not path.is_file():
        return {"version": 1, "midi_path": "", "channel_mappings": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "midi_path": "", "channel_mappings": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "midi_path": "", "channel_mappings": {}}
    payload.setdefault("version", 1)
    payload.setdefault("channel_mappings", {})
    return payload


def save_state(
    project: FragmenterProjectV1,
    *,
    midi_path: str,
    channel_mappings: dict[str, Any],
) -> Path:
    path = state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "midi_path": str(midi_path),
        "channel_mappings": channel_mappings,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def _load_mapping_sample(mapping: dict[str, Any]) -> Any:
    path = Path(str(mapping.get("output_path") or ""))
    if not path.is_file():
        raise OriginalSequencerError(f"Mapped sample WAV is missing: {path}")
    sample_id = int(mapping.get("sample_id") or 0)
    return music_v3._load_wav(path, sample_id, int(mapping.get("sample_rate") or 0) or None)


def _pan_gains(pan: int) -> tuple[float, float]:
    x = max(0, min(127, int(pan))) / 127.0
    return math.cos(x * math.pi / 2.0), math.sin(x * math.pi / 2.0)


def _voice_bounds(
    note: dict[str, Any],
    sample: Any,
    mapping: dict[str, Any],
    *,
    tempo_scale: float,
    output_rate: int,
) -> tuple[int, int, float]:
    start_seconds = float(note.get("start_seconds") or 0.0) / tempo_scale
    start = max(0, int(round(start_seconds * output_rate)))
    mode = str(mapping.get("playback_mode") or "Pitched")
    root = int(mapping.get("root_note") if mapping.get("root_note") is not None else 60)
    transpose = int(mapping.get("transpose") or 0)
    ratio = 1.0
    if mode == "Pitched":
        ratio = 2.0 ** ((int(note.get("note") or 60) + transpose - root) / 12.0)
    sample_frames = max(
        1,
        int(math.ceil(len(sample.pcm) / max(1e-9, ratio) * output_rate / sample.sample_rate)),
    )
    if mode == "Pitched":
        gate_seconds = max(0.03, float(note.get("duration_seconds") or 0.25) / tempo_scale)
        length = min(sample_frames, max(1, int(round(gate_seconds * output_rate))))
    else:
        length = sample_frames
    return start, start + length, ratio


def render_notes(
    notes: list[dict[str, Any]],
    channel_mappings: dict[str, Any],
    *,
    master_gain: float = 0.8,
    tempo_scale: float = 1.0,
    max_seconds: float = MAX_SECONDS,
    output_rate: int = OUTPUT_RATE,
) -> tuple[array, dict[str, Any]]:
    tempo_scale = max(0.25, min(4.0, float(tempo_scale)))
    master_gain = max(0.0, min(2.0, float(master_gain)))
    max_frames = max(1, int(max_seconds * output_rate))
    loaded: dict[str, Any] = {}
    voices: list[dict[str, Any]] = []
    skipped_unmapped = 0
    skipped_after_limit = 0

    for note in notes[:MAX_NOTES]:
        channel = str(int(note.get("channel") or 0))
        mapping = channel_mappings.get(channel)
        if not isinstance(mapping, dict) or not mapping.get("output_path"):
            skipped_unmapped += 1
            continue
        key = str(mapping.get("key") or mapping.get("output_path"))
        if key not in loaded:
            loaded[key] = _load_mapping_sample(mapping)
        sample = loaded[key]
        start, end, ratio = _voice_bounds(
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
        gain = master_gain * float(mapping.get("gain") if mapping.get("gain") is not None else 1.0) * velocity
        pan = int(mapping.get("pan") if mapping.get("pan") is not None else 64)
        voices.append(
            {
                "start": start,
                "end": end,
                "ratio": ratio,
                "gain": gain,
                "pan": pan,
                "sample": sample,
                "channel": int(note.get("channel") or 0),
                "note": int(note.get("note") or 60),
                "mapping_key": key,
            }
        )

    if not voices:
        raise OriginalSequencerError(
            "No MIDI notes reached a mapped playable sample. Assign at least one MIDI channel."
        )

    frame_count = max(voice["end"] for voice in voices)
    mix = array("f", [0.0]) * (frame_count * 2)
    peak = 0.0

    for voice in voices:
        sample = voice["sample"]
        left_gain, right_gain = _pan_gains(voice["pan"])
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
        "mapped_channels": sorted({voice["channel"] for voice in voices}),
        "sample_assets": sorted({voice["mapping_key"] for voice in voices}),
        "skipped_unmapped_notes": skipped_unmapped,
        "skipped_after_time_limit": skipped_after_limit,
        "note_limit": MAX_NOTES,
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


def write_stereo_wav(path: str | Path, mix: array, sample_rate: int = OUTPUT_RATE) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    buffer = bytearray()
    for value in mix:
        sample = int(round(max(-1.0, min(1.0, float(value))) * 32767.0))
        buffer.extend(sample.to_bytes(2, "little", signed=True))
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(buffer))
    return target


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
    safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in source.stem)
    target = (
        sound_decoded_root(project)
        / "original_sequencer"
        / (output_name or f"{safe_name}_fragment_samples.wav")
    )
    write_stereo_wav(target, mix, OUTPUT_RATE)
    report = {
        "status": "rendered",
        "source_midi": str(source),
        "output_path": str(target),
        "midi_summary": parsed.get("summary") or {},
        "channel_mappings": channel_mappings,
        "metadata": metadata,
    }
    report_path = sound_reports_root(project) / REPORT_NAME
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's Original Sequencer.")

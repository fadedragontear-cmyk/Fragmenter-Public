#!/usr/bin/env python3
"""Offline five-layer WAV sampler for Fragment audio research."""
from __future__ import annotations

import json
import math
import os
import wave
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from original_sequencer_v1 import OUTPUT_RATE, write_stereo_wav
from project_sound_v1 import sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1

MAX_SLOTS = 5
MAX_SECONDS = 120.0
REPORT_NAME = "audio_layer_sampler_last_render_v1.json"


class LayerSamplerError(RuntimeError):
    """Raised when a sampler configuration cannot be rendered."""


def _load_mono_pcm16(path: str | Path) -> tuple[tuple[float, ...], int]:
    source = Path(path)
    if not source.is_file():
        raise LayerSamplerError(f"Sampler WAV is missing: {source}")
    with wave.open(str(source), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if channels != 1 or width != 2:
        raise LayerSamplerError(f"Sampler accepts mono 16-bit PCM WAVs: {source}")
    pcm = tuple(
        int.from_bytes(frames[offset : offset + 2], "little", signed=True) / 32768.0
        for offset in range(0, len(frames) - 1, 2)
    )
    if not pcm:
        raise LayerSamplerError(f"Sampler WAV has no PCM frames: {source}")
    return pcm, int(rate)


def _normalized_slot(raw: dict[str, Any], index: int) -> dict[str, Any]:
    path = Path(str(raw.get("path") or raw.get("output_path") or "")).expanduser()
    start_seconds = max(0.0, float(raw.get("start_seconds") or 0.0))
    gain = max(0.0, min(2.0, float(raw.get("gain") if raw.get("gain") is not None else 1.0)))
    pitch = max(-36.0, min(36.0, float(raw.get("pitch_semitones") or 0.0)))
    loop = bool(raw.get("loop"))
    loop_start = max(0.0, float(raw.get("loop_start_seconds") or 0.0))
    loop_end = max(0.0, float(raw.get("loop_end_seconds") or 0.0))
    return {
        "slot": index + 1,
        "path": str(path),
        "start_seconds": start_seconds,
        "gain": gain,
        "pitch_semitones": pitch,
        "pitch_ratio": 2.0 ** (pitch / 12.0),
        "loop": loop,
        "loop_start_seconds": loop_start,
        "loop_end_seconds": loop_end,
    }


def render_layers(
    slots: list[dict[str, Any]],
    *,
    duration_seconds: float = 12.0,
    master_gain: float = 0.8,
    output_rate: int = OUTPUT_RATE,
) -> tuple[array, dict[str, Any]]:
    """Render one to five mono WAV layers into a normalized stereo preview."""
    duration_seconds = max(0.1, min(MAX_SECONDS, float(duration_seconds)))
    master_gain = max(0.0, min(2.0, float(master_gain)))
    output_rate = max(8000, int(output_rate))
    active = [
        _normalized_slot(raw, index)
        for index, raw in enumerate(slots[:MAX_SLOTS])
        if isinstance(raw, dict) and bool(raw.get("enabled", True)) and str(raw.get("path") or raw.get("output_path") or "").strip()
    ]
    if not active:
        raise LayerSamplerError("Enable at least one sampler slot and choose a WAV.")

    frame_count = max(1, int(round(duration_seconds * output_rate)))
    mix = array("f", [0.0]) * (frame_count * 2)
    rendered_slots: list[dict[str, Any]] = []
    peak = 0.0
    center_gain = math.sqrt(0.5)

    for slot in active:
        pcm, source_rate = _load_mono_pcm16(slot["path"])
        start_frame = min(frame_count, int(round(slot["start_seconds"] * output_rate)))
        source_length = len(pcm)
        loop_start = min(source_length - 1, int(round(slot["loop_start_seconds"] * source_rate)))
        configured_loop_end = int(round(slot["loop_end_seconds"] * source_rate))
        loop_end = source_length if configured_loop_end <= 0 else min(source_length, configured_loop_end)
        if slot["loop"] and loop_end <= loop_start:
            raise LayerSamplerError(
                f"Slot {slot['slot']} loop end must be after loop start "
                f"({slot['loop_start_seconds']:.3f}s -> {slot['loop_end_seconds']:.3f}s)."
            )

        contributed = 0
        for output_frame in range(start_frame, frame_count):
            elapsed = output_frame - start_frame
            source_position = (
                elapsed
                * slot["pitch_ratio"]
                * source_rate
                / float(output_rate)
            )
            if slot["loop"]:
                if source_position >= loop_end:
                    source_position = loop_start + ((source_position - loop_start) % (loop_end - loop_start))
            elif source_position >= source_length:
                break
            source_index = min(source_length - 1, max(0, int(source_position)))
            value = pcm[source_index] * slot["gain"] * master_gain
            target = output_frame * 2
            left = mix[target] + value * center_gain
            right = mix[target + 1] + value * center_gain
            mix[target] = left
            mix[target + 1] = right
            peak = max(peak, abs(left), abs(right))
            contributed += 1

        rendered_slots.append(
            {
                **slot,
                "source_rate": source_rate,
                "source_frames": source_length,
                "source_duration_seconds": source_length / float(source_rate),
                "resolved_loop_start_seconds": loop_start / float(source_rate),
                "resolved_loop_end_seconds": loop_end / float(source_rate),
                "output_frames_contributed": contributed,
            }
        )

    scale = 1.0 / peak if peak > 1.0 else 1.0
    if scale != 1.0:
        for index in range(len(mix)):
            mix[index] *= scale

    metadata = {
        "slot_count": len(rendered_slots),
        "slots": rendered_slots,
        "duration_seconds": duration_seconds,
        "output_rate": output_rate,
        "frames": frame_count,
        "master_gain": master_gain,
        "peak_before_normalization": peak,
        "normalization_scale": scale,
        "limitations": [
            "This is an offline research preview, not live SPU2 emulation.",
            "Pitch uses nearest-neighbour resampling.",
            "Loop boundaries are measured in source-WAV seconds.",
            "No envelopes, filters, reverb, or game-authentic voice allocation are applied.",
        ],
    }
    return mix, metadata


def render_layer_sampler(
    project: FragmenterProjectV1,
    slots: list[dict[str, Any]],
    *,
    duration_seconds: float = 12.0,
    master_gain: float = 0.8,
    output_name: str = "layer_sampler_preview.wav",
) -> dict[str, Any]:
    mix, metadata = render_layers(
        slots,
        duration_seconds=duration_seconds,
        master_gain=master_gain,
    )
    target = sound_decoded_root(project) / "original_sequencer" / output_name
    write_stereo_wav(target, mix, OUTPUT_RATE)
    report = {
        "version": 1,
        "status": "rendered",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_path": str(target),
        "metadata": metadata,
    }
    report_path = sound_reports_root(project) / REPORT_NAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temp = report_path.with_name(report_path.name + ".tmp")
    temp.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temp, report_path)
    report["report_path"] = str(report_path)
    return report


if __name__ == "__main__":
    raise SystemExit("Use through Fragmenter's Layer Sampler.")

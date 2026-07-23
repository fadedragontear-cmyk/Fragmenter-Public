#!/usr/bin/env python3
"""Experimental SNDDATA sample renderer.

This module is intentionally explicit about its speculative parts.  It renders
parsed custom MIDI-like events, program dictionaries, slot dictionaries, and
already-decoded mono samples to stereo PCM WAV.  It is not a format claim: root
note fallback (MIDI note 60) and tempo-pitch fields are experimental mapping
inputs preserved in render metadata.
"""
from __future__ import annotations

import argparse
import json
import math
import wave
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT_NOTE_FALLBACK = 60
ROOT_NOTE_FALLBACK_EXPERIMENTAL = True
DEFAULT_MAX_VOICES = 48


def _value(v: Any, default: Any = None) -> Any:
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return default if v is None else v


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass(frozen=True, slots=True)
class DecodedSample:
    """Decoded mono sample input, normalized to -1..1 floats by the caller."""

    index: int
    pcm: tuple[float, ...]
    sample_rate: int = 44100
    root_note: int | None = None
    root_note_candidate: int | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any], index: int | None = None) -> "DecodedSample":
        raw = data.get("pcm", data.get("samples", data.get("data", ())))
        return cls(
            int(_value(data.get("index"), 0 if index is None else index)),
            tuple(float(x) for x in raw),
            int(_value(data.get("sample_rate"), 44100)),
            _optional_int(data.get("root_note")),
            _optional_int(data.get("root_note_candidate")),
        )


def _optional_int(v: Any) -> int | None:
    v = _value(v)
    return None if v is None else int(v)


@dataclass(frozen=True, slots=True)
class RenderParameters:
    """Live-updatable model used by the renderer."""

    master_gain: float = 1.0
    pan_mode: str = "equal_power"  # "equal_power" or "linear"
    max_voices: int = DEFAULT_MAX_VOICES

    def update(self, **changes: Any) -> "RenderParameters":
        updated = replace(self, **changes)
        if updated.pan_mode not in {"linear", "equal_power"}:
            raise ValueError("pan_mode must be 'linear' or 'equal_power'")
        if updated.max_voices < 1:
            raise ValueError("max_voices must be positive")
        return updated


@dataclass(slots=True)
class Voice:
    start_frame: int
    end_frame: int
    sample: DecodedSample
    gain: float
    pan: int
    ratio: float
    note: int
    sequence: int
    stolen: bool = False


@dataclass(slots=True)
class RenderResult:
    frames: list[tuple[float, float]]
    sample_rate: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def write_wav(self, path: Path) -> Path:
        """Write stereo 16-bit PCM WAV with peak normalization to prevent clipping."""
        path.parent.mkdir(parents=True, exist_ok=True)
        peak = max((max(abs(l), abs(r)) for l, r in self.frames), default=0.0)
        scale = 1.0 / peak if peak > 1.0 else 1.0
        with wave.open(str(path), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(self.sample_rate)
            buf = bytearray()
            for l, r in self.frames:
                for x in (l * scale, r * scale):
                    s = int(round(_clamp(x, -1.0, 1.0) * 32767.0))
                    buf.extend(s.to_bytes(2, "little", signed=True))
            out.writeframes(bytes(buf))
        self.metadata["wav_peak_before_clip_prevention"] = peak
        self.metadata["wav_clip_prevention_scale"] = scale
        return path


def pan_gains(pan: int, mode: str = "equal_power") -> tuple[float, float]:
    x = _clamp(int(pan), 0, 127) / 127.0
    if mode == "linear":
        return 1.0 - x, x
    if mode == "equal_power":
        return math.cos(x * math.pi / 2.0), math.sin(x * math.pi / 2.0)
    raise ValueError("unknown pan mode")


def seconds_for_ticks(ticks: int, tempo_us_per_qn: int = 500_000, ticks_per_quarter: int = 96) -> float:
    return ticks * (tempo_us_per_qn / 1_000_000.0) / ticks_per_quarter


def _tempo(report: dict[str, Any] | None) -> tuple[int, int]:
    timing = (report or {}).get("timing", {})
    tpqn = int(_value(timing.get("ticks_per_quarter_note", {}).get("value"), 96) or 96)
    tempo = int(_value(timing.get("tempo", {}).get("value"), 500_000) or 500_000)
    return tempo, tpqn


def choose_program(event: dict[str, Any], programs: Sequence[dict[str, Any]], mode: str = "auto", manual: dict[Any, int] | None = None) -> dict[str, Any] | None:
    if not programs:
        return None
    channel = event.get("channel")
    track = event.get("track_index", event.get("track"))
    key: Any = channel if channel is not None else track
    if mode in {"manual", "Manual"} and manual:
        idx = manual.get(key, manual.get(str(key), 0))
    elif mode in {"track_index", "Track Index → Program Index"}:
        idx = int(track or 0)
    elif mode in {"channel", "Channel → Program Index"}:
        idx = int(channel or 0)
    else:  # Auto / Evidence Based
        idx = _optional_int(event.get("program_index"))
        if idx is None:
            idx = _optional_int(event.get("program"))
        if idx is None:
            idx = int(channel if channel is not None and channel < len(programs) else 0)
    return programs[idx % len(programs)]


SAMPLE_REFERENCE_FIELDS = ("sample_index", "sample", "sample_id")


def _valid_slots(program: dict[str, Any]) -> list[dict[str, Any]]:
    slots = program.get("slots")
    if not slots:
        return [{}]
    return [slot for slot in slots if isinstance(slot, dict)]


def _slot_sample_reference(slot: dict[str, Any]) -> tuple[str | None, int | None]:
    for field_name in SAMPLE_REFERENCE_FIELDS:
        if field_name in slot:
            return field_name, _optional_int(slot.get(field_name))
    return None, None


def _sample_for_slot(slot: dict[str, Any], samples: dict[int, DecodedSample]) -> tuple[DecodedSample | None, dict[str, Any]]:
    field_name, idx = _slot_sample_reference(slot)
    evidence: dict[str, Any] = {"sample_reference_field": field_name, "sample_id": idx}
    if field_name is None:
        idx = min(samples) if samples else None
        evidence.update({"sample_id": idx, "sample_fallback_reason": "slot_sample_id_absent_partial_layout_experimental"})
    if idx is None:
        return None, evidence
    sample = samples.get(idx)
    if sample is None and field_name is not None:
        evidence["unresolved_sample_id"] = idx
    return sample, evidence


def _gain(program: dict[str, Any], slot: dict[str, Any], velocity: int, params: RenderParameters) -> float:
    mv = int(_value(program.get("master_volume"), 127)) / 127.0
    sv = int(_value(slot.get("volume"), _value(slot.get("slot_volume"), 127))) / 127.0
    return params.master_gain * mv * sv * (velocity / 127.0)


def _pitch_ratio(note: int, sample: DecodedSample, program: dict[str, Any], slot: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    root = sample.root_note if sample.root_note is not None else sample.root_note_candidate
    experimental = False
    if root is None:
        root = ROOT_NOTE_FALLBACK
        experimental = ROOT_NOTE_FALLBACK_EXPERIMENTAL
    cents = (int(_value(program.get("tempo_pitch"), 64)) - 64) + (int(_value(slot.get("tempo_pitch"), 64)) - 64)
    semis = (note - root) + cents / 64.0
    return 2.0 ** (semis / 12.0), {"root_note": root, "fallback_root_note_60_experimental": experimental, "tempo_pitch_cents_candidate": cents}


def render(events: Iterable[dict[str, Any]], programs: Sequence[dict[str, Any]], samples_in: Sequence[DecodedSample | dict[str, Any]], midi_report: dict[str, Any] | None = None, *, sample_rate: int = 44100, mapping_mode: str = "auto", manual_mapping: dict[Any, int] | None = None, params: RenderParameters | None = None) -> RenderResult:
    """Render note events. Voice stealing: when the active-voice cap is exceeded,
    steal the oldest currently sounding voice by truncating it at the new note's
    start frame.  This keeps timing deterministic and guarantees at least 48
    active voices with the default cap.
    """
    params = params or RenderParameters()
    sample_map = {s.index: s for s in (x if isinstance(x, DecodedSample) else DecodedSample.from_mapping(x, i) for i, x in enumerate(samples_in))}
    tempo, tpqn = _tempo(midi_report)
    voices: list[Voice] = []
    active: list[Voice] = []
    meta = {"voice_stealing_policy": "oldest active voice is truncated at the new voice start", "pitch_mappings": []}
    seq = 0
    for e in sorted(events, key=lambda ev: int(ev.get("absolute_ticks", 0))):
        if e.get("event_type") != "note_on" or int(e.get("values", {}).get("velocity", 0)) <= 0:
            continue
        start = int(round(seconds_for_ticks(int(e.get("absolute_ticks", 0)), tempo, tpqn) * sample_rate))
        active = [v for v in active if v.end_frame > start and not v.stolen]
        program = choose_program(e, programs, mapping_mode, manual_mapping) or {}
        note = int(e.get("values", {}).get("note", 60))
        velocity = int(e["values"]["velocity"])
        for slot_index, slot in enumerate(_valid_slots(program)):
            smp, sample_evidence = _sample_for_slot(slot, sample_map)
            sample_evidence.update({"program_index": programs.index(program) if program in programs else None, "slot_index": slot_index})
            if smp is None or not smp.pcm:
                meta["pitch_mappings"].append(sample_evidence)
                continue
            active = [v for v in active if v.end_frame > start and not v.stolen]
            if len(active) >= params.max_voices:
                victim = min(active, key=lambda v: (v.start_frame, v.sequence))
                victim.end_frame = start
                victim.stolen = True
                active.remove(victim)
            ratio, pmeta = _pitch_ratio(note, smp, program, slot)
            pmeta.update(sample_evidence)
            dur = max(1, int(math.ceil(len(smp.pcm) / ratio * sample_rate / smp.sample_rate)))
            v = Voice(start, start + dur, smp, _gain(program, slot, velocity, params), int(_value(slot.get("pan"), 64)), ratio, note, seq)
            voices.append(v); active.append(v); seq += 1; meta["pitch_mappings"].append(pmeta)
    nframes = max((v.end_frame for v in voices), default=0)
    frames = [(0.0, 0.0) for _ in range(nframes)]
    for v in voices:
        lg, rg = pan_gains(v.pan, params.pan_mode)
        for frame in range(v.start_frame, v.end_frame):
            src = int((frame - v.start_frame) * v.ratio * v.sample.sample_rate / sample_rate)
            if src >= len(v.sample.pcm):
                break
            l, r = frames[frame]
            x = v.sample.pcm[src] * v.gain
            frames[frame] = (l + x * lg, r + x * rg)
    return RenderResult(frames, sample_rate, meta)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("fixture", type=Path, help="JSON with events/programs/samples and optional midi_report")
    ap.add_argument("out", type=Path)
    ap.add_argument("--mapping-mode", default="auto")
    ap.add_argument("--pan-mode", default="equal_power", choices=["equal_power", "linear"])
    ns = ap.parse_args(argv)
    data = json.loads(ns.fixture.read_text(encoding="utf-8"))
    result = render(data["events"], data["programs"], data["samples"], data.get("midi_report"), mapping_mode=ns.mapping_mode, params=RenderParameters(pan_mode=ns.pan_mode))
    result.write_wav(ns.out)
    print(f"wrote {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

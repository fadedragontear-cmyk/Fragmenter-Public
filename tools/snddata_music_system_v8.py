#!/usr/bin/env python3
"""Render an audible SNDDATA timing proof without claiming Program/slot semantics.

This diagnostic deliberately bypasses Program-resource pairing and parsed slot sample
references. It chooses one known-good decoded sample, triggers it at every decoded
positive-velocity Note On time, and fixes the proof note to the sample root fallback.
A successful WAV proves the MIDI-like event timing, tempo conversion, PCM loading,
mixing, and WAV writing path. It does not prove instruments, Programs, slots, pitch,
or sequence-to-bank pairing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import snddata_music_system_v3 as music_v3
import snddata_music_system_v5 as v5
from project_sound_v1 import sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_player import DecodedSample, RenderParameters, render
from snddata_sample_bridge_v1 import normalized_sample_rows

MusicSystemError = v5.MusicSystemError
PROOF_EXCERPT_SECONDS = 0.25


def timing_proof_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep note timing/velocity while removing every unverified routing dependency."""
    output: list[dict[str, Any]] = []
    for event in events:
        values = event.get("values") or {}
        if event.get("event_type") != "note_on" or int(values.get("velocity") or 0) <= 0:
            continue
        output.append(
            {
                "absolute_ticks": int(event.get("absolute_ticks") or 0),
                "offset": int(event.get("offset") or 0),
                "track_index": int(event.get("track_index") or 0),
                "event_type": "note_on",
                "channel": 0,
                "program_index": 0,
                "values": {
                    "note": 60,
                    "velocity": int(values.get("velocity") or 127),
                },
            }
        )
    return output


def _row_priority(row: dict[str, Any], preferred_resource: int | None) -> tuple[int, int, float]:
    resource = int(row.get("resource_id") or -1)
    preferred = 1 if preferred_resource is not None and resource == int(preferred_resource) else 0
    try:
        duration = float(row.get("duration_estimate") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    moderate = 1 if 0.02 <= duration <= 2.0 else 0
    return preferred, moderate, min(max(duration, 0.0), 2.0)


def _proof_excerpt(sample: DecodedSample) -> tuple[DecodedSample | None, dict[str, Any]]:
    """Extract a short audible region so thousands of note hits remain manageable."""
    threshold = 1e-6
    first_audible = next((index for index, value in enumerate(sample.pcm) if abs(value) > threshold), None)
    if first_audible is None:
        return None, {"original_pcm_samples": len(sample.pcm), "reason": "sample_pcm_is_silent"}
    lead_in = max(1, int(sample.sample_rate * 0.01))
    start = max(0, first_audible - lead_in)
    max_values = max(1, int(sample.sample_rate * PROOF_EXCERPT_SECONDS))
    end = min(len(sample.pcm), start + max_values)
    excerpt = sample.pcm[start:end]
    if not excerpt:
        return None, {"original_pcm_samples": len(sample.pcm), "reason": "audible_excerpt_is_empty"}
    return (
        DecodedSample(sample.index, tuple(excerpt), sample.sample_rate, root_note=60),
        {
            "original_pcm_samples": len(sample.pcm),
            "proof_excerpt_start": start,
            "proof_excerpt_pcm_samples": len(excerpt),
            "proof_excerpt_seconds": len(excerpt) / float(sample.sample_rate),
        },
    )


def choose_timing_proof_sample(
    project: FragmenterProjectV1,
    preferred_resource: int | None = None,
) -> tuple[DecodedSample, dict[str, Any]]:
    """Load the first audible verified WAV, preferring the selected candidate bank."""
    rows = [
        row
        for row in normalized_sample_rows(project)
        if not row.get("errors")
        and Path(str(row.get("output_path") or "")).is_file()
        and Path(str(row.get("output_path") or "")).suffix.casefold() == ".wav"
    ]
    rows.sort(key=lambda row: _row_priority(row, preferred_resource), reverse=True)
    load_errors: list[str] = []
    silent_rows = 0
    for row in rows:
        path = Path(str(row.get("output_path") or ""))
        sample_id = int(row.get("sample_id") or 0)
        try:
            loaded = music_v3._load_wav(path, sample_id, int(row.get("sample_rate") or 0) or None)
        except Exception as exc:
            load_errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        if not loaded.pcm:
            continue
        sample, excerpt = _proof_excerpt(loaded)
        if sample is None:
            silent_rows += 1
            continue
        return sample, {**row, **excerpt}
    if rows and silent_rows:
        raise MusicSystemError(
            "Decoded WAV files exist but no audible PCM was found for the timing proof",
            missing=[f"silent decoded WAV rows checked: {silent_rows}"],
        )
    raise MusicSystemError(
        "No nonempty decoded WAV is available for an independent timing proof",
        missing=load_errors[:8] or ["at least one decoded mono 16-bit PCM sample"],
    )


def render_sequence_timing_proof(
    project: FragmenterProjectV1,
    sequence_id: str,
    *,
    preferred_resource_offset: int | None = None,
    master_gain: float = 1.0,
) -> dict[str, Any]:
    """Render rhythm/timing using one known-good sample and no Program/slot mapping."""
    sequence = v5.sequence_view_model(project, sequence_id)
    runtime = v5.load_runtime(project)
    midi_reports = v5._midi_reports(runtime, int(sequence["resource_offset"]))
    bounded_events, event_bounds = v5._bounded_preview_events(midi_reports)
    proof_events = timing_proof_events(bounded_events)
    if not proof_events:
        raise MusicSystemError(
            "The selected sequence has no decoded positive-velocity Note On events",
            missing=["decoded Note On timing"],
        )

    sample, sample_row = choose_timing_proof_sample(project, preferred_resource_offset)
    program = {
        "index": 0,
        "master_volume": 127,
        "tempo_pitch": 64,
        "slots": [
            {
                "sample_id": int(sample.index),
                "volume": 127,
                "pan": 64,
                "tempo_pitch": 64,
            }
        ],
    }
    result = render(
        proof_events,
        [program],
        [sample],
        midi_reports[0] if midi_reports else None,
        mapping_mode="auto",
        params=RenderParameters(master_gain=master_gain),
    )
    if not result.frames:
        raise MusicSystemError(
            "Timing-proof inputs were valid but the generic renderer produced no PCM frames",
            missing=[
                f"proof note events: {len(proof_events)}",
                f"sample PCM values: {len(sample.pcm)}",
                "generic renderer scheduling defect",
            ],
        )

    frame_bounds = v5._truncate_preview_frames(result)
    output = (
        sound_decoded_root(project)
        / "music_previews"
        / f"{sequence_id.replace('@', '_').replace('0x', '')}_timing_proof.wav"
    )
    result.metadata.update(
        {
            "sequence_id": sequence_id,
            "timing_proof": True,
            "confirmation_allowed": False,
            "program_resource_pairing_bypassed": True,
            "program_selection_bypassed": True,
            "slot_layout_bypassed": True,
            "sample_reference_bypassed": True,
            "pitch_interpretation_bypassed": True,
            "proof_note_fixed_to": 60,
            "proof_note_events": len(proof_events),
            "proof_sample": {
                "resource_offset": int(sample_row.get("resource_id") or 0),
                "sample_id": int(sample.index),
                "display_name": sample_row.get("display_name"),
                "output_path": sample_row.get("output_path"),
                "sample_rate": int(sample.sample_rate),
                "pcm_samples": len(sample.pcm),
                "original_pcm_samples": int(sample_row.get("original_pcm_samples") or len(sample.pcm)),
                "excerpt_start": int(sample_row.get("proof_excerpt_start") or 0),
                "excerpt_seconds": float(sample_row.get("proof_excerpt_seconds") or 0.0),
            },
            "preview_event_bounds": event_bounds,
            "preview_frame_bounds": frame_bounds,
            "interpretation": "Rhythm/timing and PCM pipeline proof only; instruments and routing are intentionally incorrect.",
        }
    )
    result.write_wav(output)
    report = {
        "status": "rendered_timing_proof",
        "output_path": str(output),
        "frames": len(result.frames),
        "sample_rate": result.sample_rate,
        "duration": len(result.frames) / float(result.sample_rate),
        "metadata": result.metadata,
    }
    report_path = sound_reports_root(project) / "music_preview_last_v8.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


if __name__ == "__main__":
    raise SystemExit("Use through the Fragmenter public GUI.")

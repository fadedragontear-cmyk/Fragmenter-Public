#!/usr/bin/env python3
"""Independent SNDDATA event/PCM proof with rebased or pulse-fallback scheduling."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import snddata_music_system_v5 as v5
import snddata_music_system_v8 as v8
from project_sound_v1 import sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_player import RenderParameters, render

MusicSystemError = v5.MusicSystemError
PULSE_SECONDS = 0.125


def _positive_notes(midi_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (
            event
            for report in midi_reports
            for event in report.get("events") or []
            if event.get("event_type") == "note_on"
            and int((event.get("values") or {}).get("velocity") or 0) > 0
        ),
        key=lambda event: (
            int(event.get("absolute_ticks") or 0),
            int(event.get("track_index") or 0),
            int(event.get("offset") or 0),
        ),
    )


def normalized_proof_events(
    midi_reports: list[dict[str, Any]],
    *,
    max_seconds: float = v5.PREVIEW_MAX_SECONDS,
    max_note_events: int = v5.PREVIEW_MAX_NOTE_EVENTS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return audible proof events even when the custom MIDI parser reports desynced ticks."""
    notes = _positive_notes(midi_reports)
    if not notes:
        return [], {
            "source_note_events": 0,
            "timing_mode": "none",
            "parser_statuses": [report.get("parser_status") for report in midi_reports],
        }

    timing = (midi_reports[0].get("timing") or {}) if midi_reports else {}
    tempo = int(((timing.get("tempo") or {}).get("value") or 500_000))
    tpqn = int(((timing.get("ticks_per_quarter_note") or {}).get("value") or 96))
    max_ticks = max(1, int(float(max_seconds) * 1_000_000.0 / max(1, tempo) * max(1, tpqn)))
    origin = min(int(event.get("absolute_ticks") or 0) for event in notes)
    relative_ticks = [max(0, int(event.get("absolute_ticks") or 0) - origin) for event in notes]
    parser_statuses = [str(report.get("parser_status") or "") for report in midi_reports]
    desynced = any("desync" in status.casefold() for status in parser_statuses)
    raw_in_window = sum(tick <= max_ticks for tick in relative_ticks)

    use_pulse_fallback = desynced or (len(notes) > 1 and raw_in_window < 2)
    if use_pulse_fallback:
        pulse_ticks = max(1, int(PULSE_SECONDS * 1_000_000.0 / max(1, tempo) * max(1, tpqn)))
        scheduled = [
            (event, index * pulse_ticks)
            for index, event in enumerate(notes[:max_note_events])
        ]
        timing_mode = "event_order_pulse_fallback"
    else:
        scheduled = [
            (event, tick)
            for event, tick in zip(notes, relative_ticks)
            if tick <= max_ticks
        ][:max_note_events]
        timing_mode = "rebased_raw_ticks"

    output: list[dict[str, Any]] = []
    for event, tick in scheduled:
        values = event.get("values") or {}
        output.append(
            {
                "absolute_ticks": int(tick),
                "offset": int(event.get("offset") or 0),
                "track_index": int(event.get("track_index") or 0),
                "event_type": "note_on",
                "channel": 0,
                "program_index": 0,
                "values": {
                    "note": 60,
                    "velocity": max(1, min(127, int(values.get("velocity") or 127))),
                },
            }
        )

    return output, {
        "source_note_events": len(notes),
        "proof_note_events": len(output),
        "timing_mode": timing_mode,
        "parser_statuses": parser_statuses,
        "raw_first_note_tick": origin,
        "raw_last_note_tick": max(int(event.get("absolute_ticks") or 0) for event in notes),
        "raw_notes_inside_60_second_window_after_rebase": raw_in_window,
        "pulse_seconds": PULSE_SECONDS if use_pulse_fallback else None,
        "tempo_us_per_quarter": tempo,
        "ticks_per_quarter": tpqn,
        "max_ticks": max_ticks,
        "timing_confirmable": not use_pulse_fallback,
    }


def render_sequence_event_proof(
    project: FragmenterProjectV1,
    sequence_id: str,
    *,
    preferred_resource_offset: int | None = None,
    master_gain: float = 1.0,
) -> dict[str, Any]:
    """Prove parsed Note On presence and PCM output without Program/slot assumptions."""
    sequence = v5.sequence_view_model(project, sequence_id)
    runtime = v5.load_runtime(project)
    midi_reports = v5._midi_reports(runtime, int(sequence["resource_offset"]))
    proof_events, event_evidence = normalized_proof_events(midi_reports)
    if not proof_events:
        raise MusicSystemError(
            "The selected sequence has no decoded positive-velocity Note On events",
            missing=[
                "decoded Note On events in the live parser",
                f"catalog note count: {int(sequence.get('note_on_count') or 0)}",
            ],
        )

    sample, sample_row = v8.choose_timing_proof_sample(project, preferred_resource_offset)
    program = {
        "index": 0,
        "master_volume": 127,
        "tempo_pitch": 64,
        "slots": [{"sample_id": int(sample.index), "volume": 127, "pan": 64, "tempo_pitch": 64}],
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
            "Event-proof inputs were supplied but the renderer produced no PCM frames",
            missing=[
                f"proof note events: {len(proof_events)}",
                f"proof sample PCM values: {len(sample.pcm)}",
                "generic renderer scheduling defect",
            ],
        )

    frame_bounds = v5._truncate_preview_frames(result)
    output = (
        sound_decoded_root(project)
        / "music_previews"
        / f"{sequence_id.replace('@', '_').replace('0x', '')}_event_proof.wav"
    )
    result.metadata.update(
        {
            "sequence_id": sequence_id,
            "event_pcm_proof": True,
            "confirmation_allowed": False,
            "program_resource_pairing_bypassed": True,
            "program_selection_bypassed": True,
            "slot_layout_bypassed": True,
            "sample_reference_bypassed": True,
            "pitch_interpretation_bypassed": True,
            "event_timing_evidence": event_evidence,
            "proof_sample": {
                "resource_offset": int(sample_row.get("resource_id") or 0),
                "sample_id": int(sample.index),
                "display_name": sample_row.get("display_name"),
                "output_path": sample_row.get("output_path"),
                "sample_rate": int(sample.sample_rate),
                "pcm_samples": len(sample.pcm),
                "original_pcm_samples": int(sample_row.get("original_pcm_samples") or len(sample.pcm)),
                "excerpt_seconds": float(sample_row.get("proof_excerpt_seconds") or 0.0),
            },
            "preview_frame_bounds": frame_bounds,
            "interpretation": (
                "PCM/event proof only. Rebased raw ticks are used when plausible; parser-desynced "
                "sequences use evenly spaced event-order pulses and do not prove original musical timing."
            ),
        }
    )
    result.write_wav(output)
    report = {
        "status": "rendered_event_pcm_proof",
        "output_path": str(output),
        "frames": len(result.frames),
        "sample_rate": result.sample_rate,
        "duration": len(result.frames) / float(result.sample_rate),
        "metadata": result.metadata,
    }
    report_path = sound_reports_root(project) / "music_preview_last_v9.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


if __name__ == "__main__":
    raise SystemExit("Use through the Fragmenter public GUI.")

#!/usr/bin/env python3
"""Experimental v6 audition path for present-but-undecodable SNDDATA samples.

This never invents Programs or absent sample records.  When a Program slot references
a sample entry that exists in the authoritative SCEIVagi inventory but failed PS-ADPCM
decoding, the caller may explicitly substitute a duration-matched silent PCM sample.
The generated preview is marked experimental and cannot establish a confirmed mapping.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import snddata_music_system_v3 as music_v3
import snddata_music_system_v5 as v5
from project_sound_v1 import sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_player import DecodedSample, RenderParameters, render
from snddata_sample_bridge_v1 import normalized_sample_rows, samples_for_resource

MusicSystemError = v5.MusicSystemError
CATALOG_NAME = v5.CATALOG_NAME
PREVIEW_MAX_SECONDS = v5.PREVIEW_MAX_SECONDS


def _failed_sample_index(project: FragmenterProjectV1, resource_offset: int) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for row in normalized_sample_rows(project):
        if int(row.get("resource_id") or -1) != int(resource_offset):
            continue
        sample_id = int(row.get("sample_id") or 0)
        status = str(row.get("decode_status") or "").casefold()
        failed = bool(row.get("errors")) or status.startswith("failed")
        if failed:
            rows[sample_id] = row
    return rows


def _synthetic_silence_sample(row: dict[str, Any], sample_id: int) -> tuple[DecodedSample, dict[str, Any]]:
    """Build silence matching the maximum duration implied by complete ADPCM blocks."""
    rate = int(row.get("sample_rate") or 44100)
    if rate <= 0 or rate > 192000:
        rate = 44100
    payload_size = max(0, int(row.get("payload_size") or 0))
    blocks = max(1, payload_size // 16)
    inferred_samples = max(1, blocks * 28)
    sample_count = min(inferred_samples, rate)  # Never invent more than one second.
    sample = DecodedSample(int(sample_id), (0.0,) * sample_count, rate)
    evidence = {
        "sample_id": int(sample_id),
        "sample_rate": rate,
        "payload_size": payload_size,
        "adpcm_blocks": blocks,
        "inferred_pcm_samples": inferred_samples,
        "synthetic_pcm_samples": sample_count,
        "duration_seconds": sample_count / float(rate),
        "source_metadata_path": row.get("metadata_path"),
        "source_decode_status": row.get("decode_status"),
        "source_errors": list(row.get("errors") or []),
        "policy": "silent placeholder for present-but-undecodable SCEIVagi entry",
    }
    return sample, evidence


def render_sequence_with_silent_placeholders(
    project: FragmenterProjectV1,
    sequence_id: str,
    *,
    program_resource_offset: int,
    routing_mode: str,
    master_gain: float = 1.0,
) -> dict[str, Any]:
    """Render a bounded preview while replacing only failed, present sample entries."""
    sequence = v5.sequence_view_model(project, sequence_id)
    mode = str(routing_mode or "")
    if mode not in {"program_change", "channel_as_program"}:
        raise MusicSystemError("Silent placeholders require an explicit public audition routing mode")
    hypothesis = next((row for row in sequence.get("routing_hypotheses") or [] if row.get("mode") == mode), None)
    if hypothesis is None:
        raise MusicSystemError(f"Routing hypothesis is unavailable: {mode}")
    required_programs = [int(value) for value in hypothesis.get("required_program_indexes") or []]
    if not required_programs:
        raise MusicSystemError("Selected routing hypothesis has no resolved Program indexes", missing=["resolved Program indexes"])

    candidates = [v5._compat_candidate(row) for row in hypothesis.get("candidates") or [] if isinstance(row, dict)]
    candidate = next(
        (row for row in candidates if int(row.get("resource_offset") or -1) == int(program_resource_offset)),
        None,
    )
    if candidate is None:
        raise MusicSystemError("Selected Program resource candidate is unavailable")
    missing_programs = [int(value) for value in candidate.get("missing_program_indexes") or []]
    if missing_programs:
        raise MusicSystemError(
            "Silent sample substitution cannot invent missing Program records",
            missing=[f"Program {value}" for value in missing_programs],
        )

    runtime = v5.load_runtime(project)
    group = next(
        (
            group
            for group in runtime.groups
            if int(group.offset) == int(program_resource_offset) and music_v3._programs(group)
        ),
        None,
    )
    if group is None:
        raise MusicSystemError("Selected Program resource disappeared from parsed runtime")
    programs = music_v3._programs(group)
    sample_map, sample_rows = samples_for_resource(project, int(group.offset))
    required_samples = {int(value) for value in candidate.get("required_sample_ids") or []}
    absent = sorted(required_samples - set(sample_map))
    failed_rows = _failed_sample_index(project, int(group.offset))
    placeholder_evidence: list[dict[str, Any]] = []
    unresolved: list[int] = []
    for sample_id in absent:
        row = failed_rows.get(sample_id)
        if row is None:
            unresolved.append(sample_id)
            continue
        placeholder, evidence = _synthetic_silence_sample(row, sample_id)
        sample_map[sample_id] = placeholder
        placeholder_evidence.append(evidence)
    if unresolved:
        raise MusicSystemError(
            "Some required samples are absent rather than present-but-undecodable; silence was not invented for them",
            missing=[f"sample {value:04d}" for value in unresolved],
        )

    midi_reports = v5._midi_reports(runtime, int(sequence["resource_offset"]))
    events, event_bounds = v5._bounded_preview_events(midi_reports)
    renderer_mode = "auto" if mode == "program_change" else "channel"
    result = render(
        events,
        programs,
        list(sample_map.values()),
        midi_reports[0] if midi_reports else None,
        mapping_mode=renderer_mode,
        params=RenderParameters(master_gain=master_gain),
    )
    if not result.frames:
        mappings = list(result.metadata.get("pitch_mappings") or [])
        unresolved_ids = sorted(
            {
                int(row["unresolved_sample_id"])
                for row in mappings
                if isinstance(row, dict) and isinstance(row.get("unresolved_sample_id"), int)
            }
        )
        raise MusicSystemError(
            "Program/sample inputs were supplied but no playable voices produced PCM frames",
            missing=[
                f"positive note events: {int(event_bounds.get('notes') or 0)}",
                f"slot attempts: {len(mappings)}",
                f"unresolved renderer sample IDs: {unresolved_ids}",
                "renderer Program/slot/note semantics",
            ],
        )

    frame_bounds = v5._truncate_preview_frames(result)
    output = (
        sound_decoded_root(project)
        / "music_previews"
        / f"{sequence_id.replace('@', '_').replace('0x', '')}_{mode}_program_{group.offset:X}_silent_gaps.wav"
    )
    result.metadata.update(
        {
            "sequence_id": sequence_id,
            "program_resource_offset": int(group.offset),
            "routing_mode": mode,
            "renderer_mapping_mode": renderer_mode,
            "required_program_indexes": required_programs,
            "required_sample_ids": sorted(required_samples),
            "decoded_sample_metadata_rows": len(sample_rows),
            "synthetic_silence_samples": placeholder_evidence,
            "synthetic_silence_count": len(placeholder_evidence),
            "experimental_preview": True,
            "confirmation_allowed": False,
            "catalog_path": str(v5.catalog_path(project)),
            "preview_event_bounds": event_bounds,
            "preview_frame_bounds": frame_bounds,
        }
    )
    result.write_wav(output)
    report = {
        "status": "rendered_with_silent_placeholders",
        "output_path": str(output),
        "frames": len(result.frames),
        "sample_rate": result.sample_rate,
        "duration": len(result.frames) / float(result.sample_rate),
        "metadata": result.metadata,
    }
    report_path = sound_reports_root(project) / "music_preview_last_v6.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


if __name__ == "__main__":
    raise SystemExit("Use through the Fragmenter public GUI.")

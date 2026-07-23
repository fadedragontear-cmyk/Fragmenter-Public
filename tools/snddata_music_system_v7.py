#!/usr/bin/env python3
"""Highly experimental SNDDATA proof renderer using same-bank sample aliases.

This path exists to produce audible proof-of-concept previews while the exact sample
and routing semantics remain under research. It never modifies game data and never
qualifies a mapping for confirmation. Failed sample entries receive duration-matched
silence; completely absent sample IDs may be aliased to the nearest decoded sample ID
from the selected Program resource. Missing Program records are still a hard stop.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import snddata_music_system_v3 as music_v3
import snddata_music_system_v5 as v5
from project_sound_v1 import sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_music_system_v6 import _failed_sample_index, _synthetic_silence_sample
from snddata_player import DecodedSample, RenderParameters, render
from snddata_sample_bridge_v1 import samples_for_resource

MusicSystemError = v5.MusicSystemError


def _nearest_sample_id(target: int, available: Iterable[int]) -> int | None:
    values = sorted({int(value) for value in available})
    return min(values, key=lambda value: (abs(value - int(target)), value)) if values else None


def _alias_sample(source: DecodedSample, target_id: int) -> DecodedSample:
    return DecodedSample(
        int(target_id),
        source.pcm,
        source.sample_rate,
        source.root_note,
        source.root_note_candidate,
    )


def supply_rough_samples(
    project: FragmenterProjectV1,
    resource_offset: int,
    required_sample_ids: Iterable[int],
) -> tuple[dict[int, DecodedSample], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load real samples and fill unresolved IDs using explicit experimental policy."""
    sample_map, sample_rows = samples_for_resource(project, int(resource_offset))
    real_ids = sorted(sample_map)
    failed_rows = _failed_sample_index(project, int(resource_offset))
    evidence: list[dict[str, Any]] = []
    unresolved: list[int] = []

    for sample_id in sorted({int(value) for value in required_sample_ids} - set(sample_map)):
        failed = failed_rows.get(sample_id)
        if failed is not None:
            placeholder, row = _synthetic_silence_sample(failed, sample_id)
            sample_map[sample_id] = placeholder
            evidence.append({"kind": "failed_sample_silence", **row})
            continue

        source_id = _nearest_sample_id(sample_id, real_ids)
        if source_id is None:
            unresolved.append(sample_id)
            continue
        source = sample_map[source_id]
        sample_map[sample_id] = _alias_sample(source, sample_id)
        evidence.append(
            {
                "kind": "nearest_same_bank_alias",
                "target_sample_id": sample_id,
                "source_sample_id": source_id,
                "distance": abs(source_id - sample_id),
                "source_sample_rate": source.sample_rate,
                "source_pcm_samples": len(source.pcm),
                "policy": "nearest decoded sample ID in selected Program resource; proof-of-concept only",
            }
        )

    if unresolved:
        raise MusicSystemError(
            "Selected Program resource has no decoded samples available for rough aliases",
            missing=[f"sample {value:04d}" for value in unresolved],
        )
    return sample_map, sample_rows, evidence


def render_sequence_rough_proof(
    project: FragmenterProjectV1,
    sequence_id: str,
    *,
    program_resource_offset: int,
    routing_mode: str,
    master_gain: float = 1.0,
) -> dict[str, Any]:
    """Render an audible, bounded, non-confirmable preview from partial evidence."""
    sequence = v5.sequence_view_model(project, sequence_id)
    mode = str(routing_mode or "")
    if mode not in {"program_change", "channel_as_program"}:
        raise MusicSystemError("Rough proof rendering requires an explicit public routing mode")
    hypothesis = next(
        (row for row in sequence.get("routing_hypotheses") or [] if isinstance(row, dict) and row.get("mode") == mode),
        None,
    )
    if hypothesis is None:
        raise MusicSystemError(f"Routing hypothesis is unavailable: {mode}")
    required_programs = [int(value) for value in hypothesis.get("required_program_indexes") or []]
    if not required_programs:
        raise MusicSystemError("Selected routing hypothesis has no resolved Program indexes")

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
            "Rough sample aliases cannot invent missing Program records",
            missing=[f"Program {value}" for value in missing_programs],
        )

    runtime = v5.load_runtime(project)
    group = next(
        (
            row
            for row in runtime.groups
            if int(row.offset) == int(program_resource_offset) and music_v3._programs(row)
        ),
        None,
    )
    if group is None:
        raise MusicSystemError("Selected Program resource disappeared from parsed runtime")
    programs = music_v3._programs(group)
    required_samples = {int(value) for value in candidate.get("required_sample_ids") or []}
    sample_map, sample_rows, alias_evidence = supply_rough_samples(project, int(group.offset), required_samples)

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
        raise MusicSystemError(
            "Rough aliases were supplied but the renderer still produced no PCM frames",
            missing=[
                f"positive note events: {int(event_bounds.get('notes') or 0)}",
                f"Program records: {len(programs)}",
                f"sample inputs: {len(sample_map)}",
                f"slot attempts: {len(mappings)}",
                "remaining renderer Program/slot/note semantics",
            ],
        )

    frame_bounds = v5._truncate_preview_frames(result)
    output = (
        sound_decoded_root(project)
        / "music_previews"
        / f"{sequence_id.replace('@', '_').replace('0x', '')}_{mode}_program_{group.offset:X}_rough_proof.wav"
    )
    result.metadata.update(
        {
            "sequence_id": sequence_id,
            "program_resource_offset": int(group.offset),
            "routing_mode": mode,
            "renderer_mapping_mode": renderer_mode,
            "required_program_indexes": required_programs,
            "required_sample_ids": sorted(required_samples),
            "real_decoded_sample_rows": len(sample_rows),
            "rough_sample_substitutions": alias_evidence,
            "rough_sample_substitution_count": len(alias_evidence),
            "experimental_preview": True,
            "rough_proof_of_concept": True,
            "confirmation_allowed": False,
            "warning": "Audible output may be musically incorrect because absent sample IDs were aliased within the same bank.",
            "catalog_path": str(v5.catalog_path(project)),
            "preview_event_bounds": event_bounds,
            "preview_frame_bounds": frame_bounds,
        }
    )
    result.write_wav(output)
    report = {
        "status": "rendered_rough_proof",
        "output_path": str(output),
        "frames": len(result.frames),
        "sample_rate": result.sample_rate,
        "duration": len(result.frames) / float(result.sample_rate),
        "metadata": result.metadata,
    }
    report_path = sound_reports_root(project) / "music_preview_last_v7.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


if __name__ == "__main__":
    raise SystemExit("Use through the Fragmenter public GUI.")
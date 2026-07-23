#!/usr/bin/env python3
"""Render bounded SNDDATA proof WAVs for evidence-backed routing hypotheses.

This is a diagnostic bridge, not a format claim. It only auditions hypotheses
whose required Program indexes and exact slot sample IDs are available in one
parsed SCEIProg/sample resource. Outputs are short, separately labelled WAVs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import scei_midi_v3
import snddata_forensics_v1
import snddata_music_system_v3 as music_v3
import snddata_parser
from project_sound_v1 import canonical_snddata_path, sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_player import RenderParameters, render

MANIFEST_NAME = "snddata_audition_matrix_v1.json"


def _sections(group: snddata_parser.ResourceGroup, tag: str) -> list[snddata_parser.Section]:
    return [section for section in group.sections if section.valid and snddata_parser.SECTION_TAGS.get(section.signature) == tag]


def _midi_reports(data: bytes, group: snddata_parser.ResourceGroup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in _sections(group, "SCEIMidi"):
        if section.end_offset is None:
            continue
        report = scei_midi_v3.parse_scei_midi(data[section.offset : section.end_offset], f"resource@0x{group.offset:X}/midi@0x{section.offset:X}")
        report["resource_offset"] = int(group.offset)
        report["section_offset"] = int(section.offset)
        rows.append(report)
    return rows


def _bounded_events(midi_reports: list[dict[str, Any]], *, max_seconds: float, max_note_events: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if not midi_reports:
        return [], None
    timing = midi_reports[0]
    tempo = int((((timing.get("timing") or {}).get("tempo") or {}).get("value") or 500_000))
    tpqn = int((((timing.get("timing") or {}).get("ticks_per_quarter_note") or {}).get("value") or 96))
    max_ticks = int(max_seconds * 1_000_000.0 / max(1, tempo) * max(1, tpqn))
    events = sorted((event for report in midi_reports for event in report.get("events") or []), key=lambda event: (int(event.get("absolute_ticks") or 0), int(event.get("track_index") or 0), int(event.get("offset") or 0)))
    output: list[dict[str, Any]] = []
    notes = 0
    for event in events:
        if int(event.get("absolute_ticks") or 0) > max_ticks:
            break
        output.append(event)
        if event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0:
            notes += 1
            if notes >= max_note_events:
                break
    return output, timing


def _truncate_render(result: Any, max_seconds: float) -> tuple[int, bool]:
    max_frames = max(1, int(float(max_seconds) * int(result.sample_rate)))
    original = len(result.frames)
    truncated = original > max_frames
    if truncated:
        result.frames = result.frames[:max_frames]
    result.metadata["diagnostic_output_frame_limit"] = max_frames
    result.metadata["diagnostic_original_frame_count"] = original
    result.metadata["diagnostic_output_truncated"] = truncated
    return original, truncated


def _sequence_group(groups: list[snddata_parser.ResourceGroup], offset: int) -> snddata_parser.ResourceGroup:
    group = next((group for group in groups if int(group.offset) == int(offset)), None)
    if group is None:
        raise KeyError(f"sequence resource@0x{offset:X}")
    return group


def _program_group(groups: list[snddata_parser.ResourceGroup], offset: int) -> snddata_parser.ResourceGroup:
    group = next((group for group in groups if int(group.offset) == int(offset) and music_v3._programs(group)), None)
    if group is None:
        raise KeyError(f"Program resource@0x{offset:X}")
    return group


def render_audition_matrix(
    project: FragmenterProjectV1,
    *,
    sequence_ids: list[str] | None = None,
    max_sequences: int = 12,
    max_candidates_per_hypothesis: int = 2,
    max_seconds: float = 20.0,
    max_note_events: int = 256,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source = canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(source)
    data = source.read_bytes()
    groups = snddata_parser.parse_blob(data, source.as_posix())
    forensic_payload = snddata_forensics_v1.build_forensics(project)
    wanted = set(sequence_ids or [])
    sequences = [
        row for row in forensic_payload["sequences"]
        if not wanted or str(row["sequence_id"]) in wanted
    ][: max(1, int(max_sequences))]
    output_root = sound_decoded_root(project) / "audition_matrix"
    output_root.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    total = len(sequences)

    for sequence_number, sequence in enumerate(sequences, 1):
        sequence_id = str(sequence["sequence_id"])
        sequence_group = _sequence_group(groups, int(sequence["resource_offset"]))
        midi_reports = _midi_reports(data, sequence_group)
        events, timing = _bounded_events(midi_reports, max_seconds=max_seconds, max_note_events=max_note_events)
        for hypothesis in sequence["routing_hypotheses"]:
            mode = str(hypothesis["mode"])
            if mode not in {"program_change", "channel_as_program"}:
                continue
            if mode == "program_change" and not hypothesis["required_program_indexes"]:
                continue
            renderer_mode = "auto" if mode == "program_change" else "channel"
            complete_candidates = [candidate for candidate in hypothesis["candidates"] if candidate.get("status") == "renderer_input_complete"][: max(1, int(max_candidates_per_hypothesis))]
            for candidate_index, candidate in enumerate(complete_candidates):
                program_offset = int(candidate["resource_offset"])
                program_group = _program_group(groups, program_offset)
                programs = music_v3._programs(program_group)
                samples, sample_rows = music_v3._samples_for_resource(project, program_offset)
                row: dict[str, Any] = {
                    "sequence_id": sequence_id,
                    "sequence_offset": int(sequence["resource_offset"]),
                    "hypothesis": mode,
                    "hypothesis_confidence": hypothesis["confidence"],
                    "renderer_mapping_mode": renderer_mode,
                    "candidate_rank": candidate_index,
                    "program_resource_offset": program_offset,
                    "required_program_indexes": candidate["required_program_indexes"],
                    "required_sample_ids": candidate["required_sample_ids"],
                    "available_sample_ids": sorted(samples),
                    "event_count": len(events),
                    "note_event_count": sum(1 for event in events if event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0),
                    "max_seconds_requested": max_seconds,
                    "max_note_events_requested": max_note_events,
                }
                try:
                    result = render(
                        events,
                        programs,
                        list(samples.values()),
                        timing,
                        mapping_mode=renderer_mode,
                        params=RenderParameters(master_gain=0.7),
                    )
                    if not result.frames:
                        row.update({"status": "no_pcm_frames", "first_wall": "renderer produced no voices from complete Program/slot/sample inputs", "renderer_metadata": result.metadata})
                    else:
                        original_frames, truncated = _truncate_render(result, max_seconds)
                        safe_sequence = sequence_id.replace("@", "_").replace("0x", "")
                        output = output_root / f"{safe_sequence}__{mode}__prog_{program_offset:X}__rank_{candidate_index}.wav"
                        result.write_wav(output)
                        row.update(
                            {
                                "status": "rendered",
                                "output_path": str(output),
                                "frames": len(result.frames),
                                "original_frames": original_frames,
                                "output_truncated": truncated,
                                "sample_rate": result.sample_rate,
                                "duration": len(result.frames) / float(result.sample_rate),
                                "renderer_metadata": result.metadata,
                                "sample_metadata_rows": len(sample_rows),
                            }
                        )
                except Exception as exc:
                    row.update({"status": "render_error", "error": f"{type(exc).__name__}: {exc}", "first_wall": "renderer exception after complete Program/slot/sample routing evidence"})
                outputs.append(row)
        if callback is not None:
            callback({"kind": "snddata_audition_progress", "current": sequence_number, "total": total, "outputs": len(outputs)})

    summary = {
        "version": 1,
        "source": str(source),
        "sequences_considered": len(sequences),
        "outputs": len(outputs),
        "rendered": sum(1 for row in outputs if row["status"] == "rendered"),
        "truncated_outputs": sum(1 for row in outputs if row.get("output_truncated")),
        "no_pcm_frames": sum(1 for row in outputs if row["status"] == "no_pcm_frames"),
        "render_errors": sum(1 for row in outputs if row["status"] == "render_error"),
        "hypotheses": sorted({str(row["hypothesis"]) for row in outputs}),
        "bounded": {"max_sequences": max_sequences, "max_candidates_per_hypothesis": max_candidates_per_hypothesis, "max_seconds": max_seconds, "max_note_events": max_note_events},
        "format_claim": "Diagnostic audition only. Channel->Program is an explicit hypothesis unless Program Change events are observed.",
    }
    payload = {"summary": summary, "outputs": outputs}
    manifest = sound_reports_root(project) / MANIFEST_NAME
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["manifest_path"] = str(manifest)
    summary["output_root"] = str(output_root)
    return summary

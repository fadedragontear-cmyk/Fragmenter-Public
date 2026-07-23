#!/usr/bin/env python3
"""SNDDATA music system v5 using observed FF0A tracks and explicit routing hypotheses."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import scei_midi_v3
import snddata_forensics_v1
import snddata_music_system_v3 as music_v3
import snddata_parser
from project_sound_v1 import canonical_snddata_path, sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_player import RenderParameters, render

MusicSystemError = music_v3.MusicSystemError
CATALOG_NAME = "snddata_music_system_v5.json"
SUMMARY_NAME = "snddata_pipeline_summary_v5.json"
PREVIEW_MAX_SECONDS = 60.0
PREVIEW_MAX_NOTE_EVENTS = 2048
_RUNTIME_CACHE: dict[tuple[str, int, int], "RuntimeV5"] = {}


@dataclass(slots=True)
class RuntimeV5:
    source: Path
    data: bytes
    groups: list[snddata_parser.ResourceGroup]


def _source_identity(source: Path) -> dict[str, Any]:
    stat = source.stat()
    return {"path": str(source.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _runtime_key(source: Path) -> tuple[str, int, int]:
    identity = _source_identity(source)
    return identity["path"], int(identity["size"]), int(identity["mtime_ns"])


def catalog_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / CATALOG_NAME


def summary_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / SUMMARY_NAME


def clear_runtime_cache() -> None:
    _RUNTIME_CACHE.clear()


def _preferred_hypothesis(sequence: dict[str, Any]) -> dict[str, Any] | None:
    hypotheses = [row for row in sequence.get("routing_hypotheses") or [] if isinstance(row, dict)]
    program_change = next((row for row in hypotheses if row.get("mode") == "program_change"), None)
    if program_change and program_change.get("required_program_indexes"):
        return program_change
    channel = next((row for row in hypotheses if row.get("mode") == "channel_as_program"), None)
    if channel and channel.get("required_program_indexes"):
        return channel
    return None


def _compat_candidate(row: dict[str, Any]) -> dict[str, Any]:
    status_map = {
        "renderer_input_complete": "renderable",
        "missing_decoded_samples": "missing_samples",
        "missing_program_indexes": "missing_programs",
    }
    return {
        **row,
        "resource_id": f"resource@0x{int(row['resource_offset']):X}",
        "program_count": int(row.get("program_count") or 0),
        "program_indexes_required": list(row.get("required_program_indexes") or []),
        "decoded_sample_count": int(row.get("decoded_sample_count") or 0),
        "status_detail": row.get("status"),
        "status": status_map.get(str(row.get("status")), str(row.get("status"))),
    }


def _catalog_sequence(sequence: dict[str, Any]) -> dict[str, Any]:
    preferred = _preferred_hypothesis(sequence)
    preferred_mode = str(preferred.get("mode")) if preferred else None
    candidates = [_compat_candidate(row) for row in (preferred.get("candidates") or [])] if preferred else []
    best = candidates[0] if candidates else None
    return {
        "sequence_id": sequence["sequence_id"],
        "resource_offset": int(sequence["resource_offset"]),
        "program_indexes": list(preferred.get("required_program_indexes") or []) if preferred else [],
        "program_change_count": int(sequence["midi_summary"]["program_changes"]),
        "note_on_count": int(sequence["midi_summary"]["notes"]),
        "track_count": int(sequence["midi_summary"]["tracks"]),
        "event_count": int(sequence["midi_summary"]["events"]),
        "note_channels": list(sequence["midi_summary"]["note_channels"]),
        "notes_without_program_change": int(sequence["midi_summary"]["notes_without_program_change"]),
        "routing_status": f"{preferred_mode or 'unresolved'}: {sequence['first_wall']}",
        "preferred_hypothesis": preferred_mode,
        "routing_hypotheses": sequence["routing_hypotheses"],
        "candidates": candidates,
        "best_candidate": best,
        "scei_sequ_program_resource_matches": sequence["scei_sequ_program_resource_matches"],
        "first_wall": sequence["first_wall"],
    }


def analyze_project_snddata(
    project: FragmenterProjectV1,
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source = canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(f"Canonical SNDDATA source is missing: {source}")
    data = source.read_bytes()
    groups = snddata_parser.parse_blob(data, source.as_posix())
    sample_rows = music_v3.ensure_canonical_samples(project, data, groups)
    forensic_payload = snddata_forensics_v1.build_forensics(project, callback=callback)
    forensic_json, forensic_txt = snddata_forensics_v1.write_forensics(project, forensic_payload)
    sequences = [_catalog_sequence(row) for row in forensic_payload["sequences"]]
    summary = {
        **forensic_payload["summary"],
        "version": 5,
        "source_identity": _source_identity(source),
        "decoded_sample_rows": sum(1 for row in sample_rows if not row.get("errors") and Path(str(row.get("output_path") or "")).is_file()),
        "preferred_program_change_sequences": sum(1 for row in sequences if row["preferred_hypothesis"] == "program_change"),
        "preferred_channel_as_program_sequences": sum(1 for row in sequences if row["preferred_hypothesis"] == "channel_as_program"),
        "preferred_renderable_candidates": sum(1 for row in sequences if isinstance(row.get("best_candidate"), dict) and row["best_candidate"].get("status") == "renderable"),
        "routing_policy": "Observed Program Change when present; otherwise explicit channel->Program hypothesis; no implicit Program 0 authority.",
        "forensics_json": str(forensic_json),
        "forensics_txt": str(forensic_txt),
    }
    payload = {"summary": summary, "sequences": sequences}
    target = catalog_path(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    summary_target = summary_path(project)
    summary_target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _RUNTIME_CACHE[_runtime_key(source)] = RuntimeV5(source, data, groups)
    return {**summary, "report_path": str(target), "summary_path": str(summary_target)}


def catalog_is_current(project: FragmenterProjectV1, payload: dict[str, Any] | None = None) -> bool:
    source = canonical_snddata_path(project)
    if not source.is_file():
        return False
    if payload is None:
        target = catalog_path(project)
        if not target.is_file():
            return False
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
    expected = ((payload.get("summary") or {}).get("source_identity") or {}) if isinstance(payload, dict) else {}
    return expected == _source_identity(source)


def load_catalog(project: FragmenterProjectV1) -> dict[str, Any]:
    target = catalog_path(project)
    if not target.is_file():
        raise FileNotFoundError(f"SNDDATA v5 music catalog is missing: {target}; use Rebuild Mixer Index or run diagnostics")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sequences"), list):
        raise ValueError(f"Invalid SNDDATA v5 music catalog: {target}")
    if not catalog_is_current(project, payload):
        raise RuntimeError("SNDDATA v5 music catalog is stale for the current canonical snddata.bin; rebuild the mixer index")
    return payload


def load_runtime(project: FragmenterProjectV1) -> RuntimeV5:
    source = canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(source)
    key = _runtime_key(source)
    cached = _RUNTIME_CACHE.get(key)
    if cached is not None:
        return cached
    data = source.read_bytes()
    runtime = RuntimeV5(source, data, snddata_parser.parse_blob(data, source.as_posix()))
    _RUNTIME_CACHE[key] = runtime
    return runtime


def sequence_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    payload = load_catalog(project)
    keys = ("sequence_id", "resource_offset", "program_indexes", "program_change_count", "note_on_count", "track_count", "event_count", "note_channels", "notes_without_program_change", "routing_status", "preferred_hypothesis")
    return [{key: row.get(key) for key in keys} | {"best_candidate": row.get("best_candidate")} for row in payload["sequences"] if isinstance(row, dict)]


def sequence_view_model(project: FragmenterProjectV1, sequence_id: str) -> dict[str, Any]:
    payload = load_catalog(project)
    sequence = next((row for row in payload["sequences"] if isinstance(row, dict) and row.get("sequence_id") == sequence_id), None)
    if sequence is None:
        raise KeyError(sequence_id)
    return {**sequence, "source": str(canonical_snddata_path(project)), "catalog_path": str(catalog_path(project))}


def _midi_reports(runtime: RuntimeV5, sequence_offset: int) -> list[dict[str, Any]]:
    group = next((group for group in runtime.groups if int(group.offset) == int(sequence_offset)), None)
    if group is None:
        raise MusicSystemError(f"Sequence resource is missing at 0x{sequence_offset:X}")
    rows: list[dict[str, Any]] = []
    for section in group.sections:
        if not section.valid or snddata_parser.SECTION_TAGS.get(section.signature) != "SCEIMidi" or section.end_offset is None:
            continue
        report = scei_midi_v3.parse_scei_midi(runtime.data[section.offset : section.end_offset], f"resource@0x{group.offset:X}/midi@0x{section.offset:X}")
        rows.append(report)
    return rows


def _bounded_preview_events(
    midi_reports: list[dict[str, Any]],
    *,
    max_seconds: float = PREVIEW_MAX_SECONDS,
    max_note_events: int = PREVIEW_MAX_NOTE_EVENTS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not midi_reports:
        return [], {"max_seconds": max_seconds, "max_note_events": max_note_events, "events": 0, "notes": 0, "truncated": False}
    timing = midi_reports[0].get("timing") or {}
    tempo = int(((timing.get("tempo") or {}).get("value") or 500_000))
    tpqn = int(((timing.get("ticks_per_quarter_note") or {}).get("value") or 96))
    max_ticks = int(float(max_seconds) * 1_000_000.0 / max(1, tempo) * max(1, tpqn))
    source_events = sorted(
        (event for report in midi_reports for event in report.get("events") or []),
        key=lambda event: (int(event.get("absolute_ticks") or 0), int(event.get("track_index") or 0), int(event.get("offset") or 0)),
    )
    output: list[dict[str, Any]] = []
    notes = 0
    truncated = False
    for event in source_events:
        if int(event.get("absolute_ticks") or 0) > max_ticks:
            truncated = True
            break
        output.append(event)
        if event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0:
            notes += 1
            if notes >= max_note_events:
                truncated = len(output) < len(source_events)
                break
    return output, {
        "max_seconds": max_seconds,
        "max_note_events": max_note_events,
        "max_ticks": max_ticks,
        "source_events": len(source_events),
        "events": len(output),
        "notes": notes,
        "truncated": truncated,
    }


def _truncate_preview_frames(result: Any, max_seconds: float = PREVIEW_MAX_SECONDS) -> dict[str, Any]:
    max_frames = max(1, int(float(max_seconds) * int(result.sample_rate)))
    original = len(result.frames)
    truncated = original > max_frames
    if truncated:
        result.frames = result.frames[:max_frames]
    return {"max_frames": max_frames, "original_frames": original, "output_frames": len(result.frames), "truncated": truncated}


def render_sequence(
    project: FragmenterProjectV1,
    sequence_id: str,
    *,
    program_resource_offset: int | None = None,
    routing_mode: str | None = None,
    master_gain: float = 1.0,
) -> dict[str, Any]:
    sequence = sequence_view_model(project, sequence_id)
    mode = routing_mode or sequence.get("preferred_hypothesis")
    if mode not in {"program_change", "channel_as_program"}:
        raise MusicSystemError("Sequence has no evidence-backed or explicit audition routing mode", missing=["observed Program Change or channel->Program hypothesis"])
    hypothesis = next((row for row in sequence["routing_hypotheses"] if row.get("mode") == mode), None)
    if hypothesis is None:
        raise MusicSystemError(f"Routing hypothesis is unavailable: {mode}")
    candidates = [_compat_candidate(row) for row in hypothesis.get("candidates") or []]
    if program_resource_offset is not None:
        candidate = next((row for row in candidates if int(row["resource_offset"]) == int(program_resource_offset)), None)
    else:
        candidate = next((row for row in candidates if row.get("status") == "renderable"), candidates[0] if candidates else None)
    if candidate is None:
        raise MusicSystemError("No Program resource candidate is available", missing=["SCEIProg resource"])
    if candidate.get("status") != "renderable":
        missing = [f"Program {value}" for value in candidate.get("missing_program_indexes") or []] + [f"sample {value}" for value in candidate.get("missing_sample_ids") or []]
        raise MusicSystemError(f"Selected candidate stops at {candidate.get('status_detail') or candidate.get('status')}", missing=missing or [str(candidate.get("status_detail") or candidate.get("status"))])

    runtime = load_runtime(project)
    group = next((group for group in runtime.groups if int(group.offset) == int(candidate["resource_offset"]) and music_v3._programs(group)), None)
    if group is None:
        raise MusicSystemError("Selected Program resource disappeared from parsed runtime")
    programs = music_v3._programs(group)
    samples, sample_rows = music_v3._samples_for_resource(project, group.offset)
    midi_reports = _midi_reports(runtime, int(sequence["resource_offset"]))
    events, event_bounds = _bounded_preview_events(midi_reports)
    renderer_mode = "auto" if mode == "program_change" else "channel"
    result = render(events, programs, list(samples.values()), midi_reports[0] if midi_reports else None, mapping_mode=renderer_mode, params=RenderParameters(master_gain=master_gain))
    if not result.frames:
        raise MusicSystemError("Program/slot/sample inputs resolved but renderer produced no PCM frames", missing=["renderer timing/pitch/voice semantics"])
    frame_bounds = _truncate_preview_frames(result)
    output = sound_decoded_root(project) / "music_previews" / f"{sequence_id.replace('@', '_').replace('0x', '')}_{mode}_program_{group.offset:X}.wav"
    result.metadata.update(
        {
            "sequence_id": sequence_id,
            "program_resource_offset": int(group.offset),
            "routing_mode": mode,
            "renderer_mapping_mode": renderer_mode,
            "required_program_indexes": hypothesis.get("required_program_indexes"),
            "candidate": candidate,
            "sample_metadata_rows": len(sample_rows),
            "program_zero_implicit": False,
            "catalog_path": str(catalog_path(project)),
            "preview_event_bounds": event_bounds,
            "preview_frame_bounds": frame_bounds,
        }
    )
    result.write_wav(output)
    report = {"status": "rendered", "output_path": str(output), "frames": len(result.frames), "sample_rate": result.sample_rate, "duration": len(result.frames) / float(result.sample_rate), "metadata": result.metadata}
    report_path = sound_reports_root(project) / "music_preview_last_v5.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report

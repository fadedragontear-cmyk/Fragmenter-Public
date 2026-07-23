#!/usr/bin/env python3
"""SNDDATA music runtime v3 using actual SCEIMidi Program Change state.

The resource pairing remains evidence-ranked because no primary format source has
been located for Fragment's SCEISequ/SCEIProg cross-resource relationship.  Once a
Program resource is selected, however, note routing uses parsed Program Change
messages and exact parsed slot sample IDs.  No sample-ID cycling/remap fallback is
used.
"""
from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import scei_midi_v2
import snddata_parser
from project_sound_v1 import canonical_snddata_path, sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_player import DecodedSample, RenderParameters, render


class MusicSystemError(RuntimeError):
    def __init__(self, message: str, *, missing: list[str] | None = None):
        super().__init__(message)
        self.missing = list(missing or [])


def _value(value: Any, default: Any = None) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return default if value is None else value


def _flatten_slot(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": int(_value(slot.get("index"), 0)),
        "sample_id": int(_value(slot.get("sample_id"), -1)),
        "slot_id": int(_value(slot.get("slot_id"), 0)),
        "volume": int(_value(slot.get("volume"), 127)),
        "pan": int(_value(slot.get("pan"), 64)),
        "tempo_pitch": int(_value(slot.get("tempo_pitch"), 64)),
        "raw_bytes": slot.get("raw_bytes"),
    }


def _flatten_program(program: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": int(_value(program.get("index"), 0)),
        "master_volume": int(_value(program.get("master_volume"), 127)),
        "tempo_pitch": int(_value(program.get("tempo_pitch"), 64)),
        "slots": [_flatten_slot(slot) for slot in program.get("slots") or [] if isinstance(slot, dict)],
        "raw": program,
    }


def _sections(group: snddata_parser.ResourceGroup, tag: str) -> list[snddata_parser.Section]:
    return [section for section in group.sections if snddata_parser.SECTION_TAGS.get(section.signature) == tag and section.valid]


def _programs(group: snddata_parser.ResourceGroup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in _sections(group, "SCEIProg"):
        parsed = section.evidence.get("scei_prog")
        if not isinstance(parsed, dict):
            continue
        rows.extend(_flatten_program(program) for program in parsed.get("programs") or [] if isinstance(program, dict) and not program.get("error"))
    return sorted(rows, key=lambda row: row["index"])


def _parse_midi_sections(data: bytes, group: snddata_parser.ResourceGroup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in _sections(group, "SCEIMidi"):
        if section.end_offset is None:
            continue
        block = data[section.offset : section.end_offset]
        parsed = scei_midi_v2.parse_scei_midi(block, f"resource@0x{group.offset:X}/midi@0x{section.offset:X}")
        parsed["resource_offset"] = group.offset
        parsed["section_offset"] = section.offset
        rows.append(parsed)
    return rows


def _load_wav(path: Path, sample_id: int, sample_rate_hint: int | None = None) -> DecodedSample:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if channels != 1 or width != 2:
        raise ValueError(f"decoded sample must be mono 16-bit PCM: {path}")
    pcm = tuple(int.from_bytes(frames[offset : offset + 2], "little", signed=True) / 32768.0 for offset in range(0, len(frames) - 1, 2))
    return DecodedSample(sample_id, pcm, sample_rate_hint or rate)


def _sample_metadata_root(project: FragmenterProjectV1) -> Path:
    return sound_decoded_root(project) / "snddata" / "samples"


def ensure_canonical_samples(project: FragmenterProjectV1, data: bytes, groups: list[snddata_parser.ResourceGroup]) -> list[dict[str, Any]]:
    root = _sample_metadata_root(project)
    root.mkdir(parents=True, exist_ok=True)
    return snddata_parser.extract_samples(data, groups, root)


def _sample_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metadata in sorted(_sample_metadata_root(project).rglob("sample_*.json")):
        try:
            row = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _samples_for_resource(project: FragmenterProjectV1, resource_offset: int) -> tuple[dict[int, DecodedSample], list[dict[str, Any]]]:
    rows = [row for row in _sample_rows(project) if int(row.get("resource_id") or -1) == int(resource_offset) and not row.get("errors")]
    samples: dict[int, DecodedSample] = {}
    valid_rows: list[dict[str, Any]] = []
    for row in rows:
        output = Path(str(row.get("output_path") or ""))
        sample_id = row.get("sample_id")
        if not isinstance(sample_id, int) or not output.is_file():
            continue
        try:
            samples[sample_id] = _load_wav(output, sample_id, int(row.get("sample_rate") or 0) or None)
            valid_rows.append(row)
        except Exception:
            continue
    return samples, valid_rows


def _program_indexes(midi_reports: list[dict[str, Any]]) -> list[int]:
    indexes = {
        int(event["program_index"])
        for report in midi_reports
        for event in report.get("events") or []
        if event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0 and isinstance(event.get("program_index"), int)
    }
    return sorted(indexes)


def _slot_sample_ids(programs: list[dict[str, Any]], program_indexes: list[int]) -> set[int]:
    by_index = {program["index"]: program for program in programs}
    values: set[int] = set()
    for index in program_indexes:
        program = by_index.get(index)
        if program is None:
            continue
        values.update(int(slot["sample_id"]) for slot in program.get("slots") or [] if int(slot.get("sample_id", -1)) >= 0)
    return values


def _candidate_row(project: FragmenterProjectV1, sequence_offset: int, group: snddata_parser.ResourceGroup, program_indexes: list[int]) -> dict[str, Any]:
    programs = _programs(group)
    by_index = {row["index"]: row for row in programs}
    missing_programs = [index for index in program_indexes if index not in by_index]
    samples, sample_rows = _samples_for_resource(project, group.offset)
    required_samples = _slot_sample_ids(programs, program_indexes)
    matched_samples = sorted(required_samples & set(samples))
    missing_samples = sorted(required_samples - set(samples))
    coverage = len(matched_samples) / len(required_samples) if required_samples else 0.0
    program_coverage = (len(program_indexes) - len(missing_programs)) / len(program_indexes) if program_indexes else 1.0
    distance = abs(int(sequence_offset) - int(group.offset))
    structured_samples = sum(1 for row in sample_rows if str(row.get("boundary_source") or "").startswith(("structured_", "validated_")))
    score = program_coverage * 1000.0 + coverage * 500.0 + min(structured_samples, 50) * 2.0 - min(distance / 1_000_000.0, 100.0)
    status = "renderable" if not missing_programs and bool(matched_samples) else "missing_samples" if not missing_programs else "missing_programs"
    return {
        "resource_offset": group.offset,
        "resource_id": f"resource@0x{group.offset:X}",
        "program_count": len(programs),
        "program_indexes_required": program_indexes,
        "missing_program_indexes": missing_programs,
        "required_sample_ids": sorted(required_samples),
        "matched_sample_ids": matched_samples,
        "missing_sample_ids": missing_samples,
        "decoded_sample_count": len(samples),
        "structured_sample_rows": structured_samples,
        "program_coverage": program_coverage,
        "sample_coverage": coverage,
        "offset_distance": distance,
        "score": round(score, 6),
        "status": status,
        "pairing_evidence": [
            "Program indexes come from parsed SCEIMidi Program Change state.",
            "Program resource pairing is ranked because SCEISequ cross-resource linking remains unresolved.",
            "Sample coverage uses exact parsed slot sample IDs; no remap fallback is applied.",
        ],
    }


@dataclass
class MusicRuntime:
    source: Path
    data: bytes
    groups: list[snddata_parser.ResourceGroup]
    sequences: list[dict[str, Any]]
    program_groups: dict[int, snddata_parser.ResourceGroup]


def load_music_runtime(project: FragmenterProjectV1, *, refresh_samples: bool = False) -> MusicRuntime:
    source = canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(f"Canonical SNDDATA source is missing: {source}; run RUN ALL sound extraction first")
    data = source.read_bytes()
    groups = snddata_parser.parse_blob(data, source.as_posix())
    if refresh_samples or not any(_sample_metadata_root(project).rglob("sample_*.json")):
        ensure_canonical_samples(project, data, groups)
    program_groups = {group.offset: group for group in groups if _programs(group)}
    sequences: list[dict[str, Any]] = []
    for group in groups:
        midi_reports = _parse_midi_sections(data, group)
        if not midi_reports:
            continue
        program_indexes = _program_indexes(midi_reports)
        note_count = sum(1 for report in midi_reports for event in report.get("events") or [] if event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0)
        program_changes = sum(int(report.get("program_change_count") or 0) for report in midi_reports)
        sequence_id = f"sequence@0x{group.offset:X}"
        candidates = sorted((_candidate_row(project, group.offset, candidate, program_indexes) for candidate in program_groups.values()), key=lambda row: (-row["score"], row["offset_distance"], row["resource_offset"]))
        sequences.append({"sequence_id": sequence_id, "resource_offset": group.offset, "midi_reports": midi_reports, "program_indexes": program_indexes, "program_change_count": program_changes, "note_on_count": note_count, "candidates": candidates, "best_candidate": candidates[0] if candidates else None, "routing_status": "program_changes_parsed" if program_changes else "no_program_change_events_observed"})
    return MusicRuntime(source, data, groups, sequences, program_groups)


def sequence_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    runtime = load_music_runtime(project)
    return [{key: row.get(key) for key in ("sequence_id", "resource_offset", "program_indexes", "program_change_count", "note_on_count", "routing_status")} | {"best_candidate": row.get("best_candidate")} for row in runtime.sequences]


def sequence_view_model(project: FragmenterProjectV1, sequence_id: str) -> dict[str, Any]:
    runtime = load_music_runtime(project)
    sequence = next((row for row in runtime.sequences if row["sequence_id"] == sequence_id), None)
    if sequence is None:
        raise KeyError(sequence_id)
    return {"sequence_id": sequence_id, "program_indexes": sequence["program_indexes"], "program_change_count": sequence["program_change_count"], "note_on_count": sequence["note_on_count"], "routing_status": sequence["routing_status"], "candidates": sequence["candidates"], "best_candidate": sequence["best_candidate"], "source": str(runtime.source)}


def render_sequence(project: FragmenterProjectV1, sequence_id: str, *, program_resource_offset: int | None = None, master_gain: float = 1.0) -> dict[str, Any]:
    runtime = load_music_runtime(project)
    sequence = next((row for row in runtime.sequences if row["sequence_id"] == sequence_id), None)
    if sequence is None:
        raise MusicSystemError(f"Unknown sequence: {sequence_id}")
    candidate = None
    if program_resource_offset is not None:
        candidate = next((row for row in sequence["candidates"] if int(row["resource_offset"]) == int(program_resource_offset)), None)
    else:
        candidate = sequence.get("best_candidate")
    if candidate is None:
        raise MusicSystemError("No Program resource candidate is available", missing=["SCEIProg resource"])
    if candidate["missing_program_indexes"]:
        raise MusicSystemError("Selected Program resource does not contain every Program referenced by the sequence", missing=[f"Program {index}" for index in candidate["missing_program_indexes"]])
    group = runtime.program_groups[int(candidate["resource_offset"])]
    programs = _programs(group)
    samples, _sample_rows_value = _samples_for_resource(project, group.offset)
    if not samples:
        raise MusicSystemError("Selected Program resource has no decoded samples", missing=[f"decoded samples for resource@0x{group.offset:X}"])
    missing_samples = list(candidate.get("missing_sample_ids") or [])
    if missing_samples:
        raise MusicSystemError("Parsed Program slots reference sample IDs that are not decoded in this resource", missing=[f"sample {index}" for index in missing_samples])

    events = [event for report in sequence["midi_reports"] for event in report.get("events") or []]
    result = render(events, programs, list(samples.values()), sequence["midi_reports"][0] if sequence["midi_reports"] else None, mapping_mode="auto", params=RenderParameters(master_gain=master_gain))
    if not result.frames:
        raise MusicSystemError("Sequence routed to Programs and samples but rendered no PCM frames", missing=["renderer slot/note routing semantics"])
    output = sound_decoded_root(project) / "music_previews" / f"{sequence_id.replace('@', '_').replace('0x', '')}_program_{group.offset:X}.wav"
    result.metadata.update({"sequence_id": sequence_id, "program_resource_offset": group.offset, "program_indexes": sequence["program_indexes"], "program_change_count": sequence["program_change_count"], "candidate": candidate, "routing_mode": "SCEIMidi Program Change -> Program index; evidence-ranked Program resource; exact slot sample IDs", "sample_remap_fallback": False})
    result.write_wav(output)
    report = {"status": "rendered", "output_path": str(output), "frames": len(result.frames), "sample_rate": result.sample_rate, "metadata": result.metadata}
    report_path = sound_reports_root(project) / "music_preview_last.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report

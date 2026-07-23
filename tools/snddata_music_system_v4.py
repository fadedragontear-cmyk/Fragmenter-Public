#!/usr/bin/env python3
"""Report-backed SNDDATA music system with bounded ranking work.

RUN ALL parses SNDDATA once, inventories decoded sample metadata once, ranks Program
resources without loading PCM, and writes the complete sequence/candidate catalog.
GUI list/selection operations consume that catalog. Binary parsing and PCM loading
are reserved for an actual render or explicit catalog rebuild.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import scei_midi_v2
import snddata_music_graph
import snddata_music_system_v3 as v3
import snddata_parser
from project_sound_v1 import canonical_snddata_path, sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_player import RenderParameters, render

MusicSystemError = v3.MusicSystemError
CATALOG_NAME = "snddata_music_system_v4.json"
SUMMARY_NAME = "snddata_pipeline_summary_v4.json"
_RUNTIME_CACHE: dict[tuple[str, int, int], v3.MusicRuntime] = {}


def _source_identity(source: Path) -> dict[str, Any]:
    stat = source.stat()
    return {"path": str(source.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _runtime_key(source: Path) -> tuple[str, int, int]:
    identity = _source_identity(source)
    return identity["path"], identity["size"], identity["mtime_ns"]


def catalog_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / CATALOG_NAME


def summary_path(project: FragmenterProjectV1) -> Path:
    return sound_reports_root(project) / SUMMARY_NAME


def clear_runtime_cache() -> None:
    _RUNTIME_CACHE.clear()


def _sample_inventory(project: FragmenterProjectV1) -> dict[int, dict[str, Any]]:
    inventory: dict[int, dict[str, Any]] = {}
    for metadata in sorted(v3._sample_metadata_root(project).rglob("sample_*.json")):
        try:
            row = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("errors"):
            continue
        resource_id = row.get("resource_id")
        sample_id = row.get("sample_id")
        output = Path(str(row.get("output_path") or ""))
        if not isinstance(resource_id, int) or not isinstance(sample_id, int) or not output.is_file():
            continue
        bucket = inventory.setdefault(resource_id, {"sample_ids": set(), "decoded_rows": 0, "structured_rows": 0})
        bucket["sample_ids"].add(sample_id)
        bucket["decoded_rows"] += 1
        if str(row.get("boundary_source") or "").startswith(("structured_", "validated_")):
            bucket["structured_rows"] += 1
    return inventory


def _candidate_row_fast(
    sequence_offset: int,
    group: snddata_parser.ResourceGroup,
    program_indexes: list[int],
    inventory: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    programs = v3._programs(group)
    by_index = {row["index"]: row for row in programs}
    missing_programs = [index for index in program_indexes if index not in by_index]
    required_samples = v3._slot_sample_ids(programs, program_indexes)
    sample_bucket = inventory.get(int(group.offset), {})
    available_samples = set(sample_bucket.get("sample_ids") or set())
    matched_samples = sorted(required_samples & available_samples)
    missing_samples = sorted(required_samples - available_samples)
    coverage = len(matched_samples) / len(required_samples) if required_samples else 0.0
    program_coverage = (len(program_indexes) - len(missing_programs)) / len(program_indexes) if program_indexes else 1.0
    distance = abs(int(sequence_offset) - int(group.offset))
    structured_samples = int(sample_bucket.get("structured_rows") or 0)
    score = program_coverage * 1000.0 + coverage * 500.0 + min(structured_samples, 50) * 2.0 - min(distance / 1_000_000.0, 100.0)
    status = "renderable" if not missing_programs and bool(matched_samples) and not missing_samples else "missing_samples" if not missing_programs else "missing_programs"
    return {
        "resource_offset": int(group.offset),
        "resource_id": f"resource@0x{group.offset:X}",
        "program_count": len(programs),
        "program_indexes_required": program_indexes,
        "missing_program_indexes": missing_programs,
        "required_sample_ids": sorted(required_samples),
        "matched_sample_ids": matched_samples,
        "missing_sample_ids": missing_samples,
        "decoded_sample_count": int(sample_bucket.get("decoded_rows") or 0),
        "structured_sample_rows": structured_samples,
        "program_coverage": program_coverage,
        "sample_coverage": coverage,
        "offset_distance": distance,
        "score": round(score, 6),
        "status": status,
        "pairing_evidence": [
            "Program indexes come from parsed SCEIMidi Program Change state.",
            "Program resource pairing remains evidence-ranked until the SCEISequ cross-resource link is proven.",
            "Sample coverage uses exact parsed slot sample IDs from one metadata inventory pass.",
            "PCM is not loaded during candidate ranking.",
            "No sample-ID remap or cycling fallback is applied.",
        ],
    }


def build_runtime_from_parsed(
    project: FragmenterProjectV1,
    source: Path,
    data: bytes,
    groups: list[snddata_parser.ResourceGroup],
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> v3.MusicRuntime:
    program_groups = {group.offset: group for group in groups if v3._programs(group)}
    inventory = _sample_inventory(project)
    sequences: list[dict[str, Any]] = []
    total = len(groups)
    for index, group in enumerate(groups, 1):
        midi_reports = v3._parse_midi_sections(data, group)
        if midi_reports:
            program_indexes = v3._program_indexes(midi_reports)
            note_count = sum(
                1
                for report in midi_reports
                for event in report.get("events") or []
                if event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0
            )
            program_changes = sum(int(report.get("program_change_count") or 0) for report in midi_reports)
            candidates = sorted(
                (_candidate_row_fast(group.offset, candidate, program_indexes, inventory) for candidate in program_groups.values()),
                key=lambda row: (-row["score"], row["offset_distance"], row["resource_offset"]),
            )
            sequences.append(
                {
                    "sequence_id": f"sequence@0x{group.offset:X}",
                    "resource_offset": int(group.offset),
                    "midi_reports": midi_reports,
                    "program_indexes": program_indexes,
                    "program_change_count": program_changes,
                    "note_on_count": note_count,
                    "candidates": candidates,
                    "best_candidate": candidates[0] if candidates else None,
                    "routing_status": "program_changes_parsed" if program_changes else "no_program_change_events_observed",
                }
            )
        if callback is not None and (index == total or index % 25 == 0):
            callback({"kind": "snddata_catalog_progress", "current": index, "total": total, "sequences": len(sequences)})
    return v3.MusicRuntime(source, data, groups, sequences, program_groups)


def _catalog_sequence(sequence: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence_id": sequence["sequence_id"],
        "resource_offset": sequence["resource_offset"],
        "program_indexes": sequence["program_indexes"],
        "program_change_count": sequence["program_change_count"],
        "note_on_count": sequence["note_on_count"],
        "routing_status": sequence["routing_status"],
        "candidates": sequence["candidates"],
        "best_candidate": sequence["best_candidate"],
    }


def _summary(runtime: v3.MusicRuntime, sample_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    sequences = [_catalog_sequence(row) for row in runtime.sequences]
    return {
        "version": 4,
        "source": str(runtime.source),
        "source_identity": _source_identity(runtime.source),
        "file_size": len(runtime.data),
        "resources": len(runtime.groups),
        "program_resources": len(runtime.program_groups),
        "sequences": len(sequences),
        "program_changes": sum(int(row["program_change_count"]) for row in sequences),
        "note_on_events": sum(int(row["note_on_count"]) for row in sequences),
        "decoded_sample_rows": sum(1 for row in (sample_rows or []) if not row.get("errors") and Path(str(row.get("output_path") or "")).is_file()),
        "sequences_with_program_changes": sum(1 for row in sequences if row["program_change_count"]),
        "best_candidates_renderable": sum(1 for row in sequences if isinstance(row.get("best_candidate"), dict) and row["best_candidate"].get("status") == "renderable"),
        "sample_remap_fallback": False,
        "program_routing": "SCEIMidi Program Change state",
        "program_resource_pairing": "evidence-ranked candidate until SCEISequ cross-resource field is proven",
        "catalog_mode": "report-backed; PCM excluded from ranking",
    }


def write_catalog(project: FragmenterProjectV1, runtime: v3.MusicRuntime, sample_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    summary = _summary(runtime, sample_rows)
    payload = {"summary": summary, "sequences": [_catalog_sequence(row) for row in runtime.sequences]}
    target = catalog_path(project)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    summary_target = summary_path(project)
    summary_target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        raise FileNotFoundError(f"SNDDATA music catalog is missing: {target}; run RUN ALL / Analyze SNDDATA Music System")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sequences"), list):
        raise ValueError(f"Invalid SNDDATA music catalog: {target}")
    if not catalog_is_current(project, payload):
        raise RuntimeError("SNDDATA music catalog is stale for the current canonical snddata.bin; run RUN ALL")
    return payload


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
    root = sound_reports_root(project)
    snddata_parser.write_reports(groups, root / "snddata_container_map.json", root / "snddata_container_map.txt")
    sample_rows = v3.ensure_canonical_samples(project, data, groups)
    graph = snddata_music_graph.build_graph(groups)
    snddata_music_graph.write_reports(graph, root / "snddata_music_graph_legacy.json", root / "snddata_music_graph_legacy.txt")
    runtime = build_runtime_from_parsed(project, source, data, groups, callback=callback)
    _RUNTIME_CACHE[_runtime_key(source)] = runtime
    return write_catalog(project, runtime, sample_rows)


def load_music_runtime(project: FragmenterProjectV1) -> v3.MusicRuntime:
    source = canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(f"Canonical SNDDATA source is missing: {source}; run RUN ALL sound extraction first")
    key = _runtime_key(source)
    cached = _RUNTIME_CACHE.get(key)
    if cached is not None:
        return cached
    data = source.read_bytes()
    groups = snddata_parser.parse_blob(data, source.as_posix())
    runtime = build_runtime_from_parsed(project, source, data, groups)
    _RUNTIME_CACHE[key] = runtime
    return runtime


def sequence_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    payload = load_catalog(project)
    return [
        {key: row.get(key) for key in ("sequence_id", "resource_offset", "program_indexes", "program_change_count", "note_on_count", "routing_status")}
        | {"best_candidate": row.get("best_candidate")}
        for row in payload["sequences"]
        if isinstance(row, dict)
    ]


def sequence_view_model(project: FragmenterProjectV1, sequence_id: str) -> dict[str, Any]:
    payload = load_catalog(project)
    sequence = next((row for row in payload["sequences"] if isinstance(row, dict) and row.get("sequence_id") == sequence_id), None)
    if sequence is None:
        raise KeyError(sequence_id)
    return {**sequence, "source": str(canonical_snddata_path(project)), "catalog_path": str(catalog_path(project))}


def render_sequence(project: FragmenterProjectV1, sequence_id: str, *, program_resource_offset: int | None = None, master_gain: float = 1.0) -> dict[str, Any]:
    runtime = load_music_runtime(project)
    sequence = next((row for row in runtime.sequences if row["sequence_id"] == sequence_id), None)
    if sequence is None:
        raise MusicSystemError(f"Unknown sequence: {sequence_id}")
    if program_resource_offset is not None:
        candidate = next((row for row in sequence["candidates"] if int(row["resource_offset"]) == int(program_resource_offset)), None)
    else:
        candidate = sequence.get("best_candidate")
    if candidate is None:
        raise MusicSystemError("No Program resource candidate is available", missing=["SCEIProg resource"])
    if candidate["missing_program_indexes"]:
        raise MusicSystemError("Selected Program resource does not contain every Program referenced by the sequence", missing=[f"Program {index}" for index in candidate["missing_program_indexes"]])
    group = runtime.program_groups[int(candidate["resource_offset"])]
    programs = v3._programs(group)
    samples, _sample_rows_value = v3._samples_for_resource(project, group.offset)
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
    result.metadata.update(
        {
            "sequence_id": sequence_id,
            "program_resource_offset": group.offset,
            "program_indexes": sequence["program_indexes"],
            "program_change_count": sequence["program_change_count"],
            "candidate": candidate,
            "routing_mode": "SCEIMidi Program Change -> Program index; evidence-ranked Program resource; exact slot sample IDs",
            "sample_remap_fallback": False,
            "catalog_path": str(catalog_path(project)),
        }
    )
    result.write_wav(output)
    report = {"status": "rendered", "output_path": str(output), "frames": len(result.frames), "sample_rate": result.sample_rate, "metadata": result.metadata}
    report_path = sound_reports_root(project) / "music_preview_last.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report

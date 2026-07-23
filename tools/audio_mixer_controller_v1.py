#!/usr/bin/env python3
"""Playable, project-bound SNDDATA mixer controller for Fragmenter 1.0.

This controller joins the conservative music graph to decoded sample WAV files.
Unresolved sequence/program relationships remain explicit until the user auditions
and saves a mapping. Game data is never modified.
"""
from __future__ import annotations

import json
import math
import re
import wave
from pathlib import Path
from typing import Any

from audio_mapping_controller_v1 import (
    load_project_mapping,
    project_mapping_resolver,
    resolve_project_snddata,
    save_project_mapping,
)
from project_preflight_v1 import resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1
from snddata_player import DecodedSample, RenderParameters, render


class NoRenderableMapping(RuntimeError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("No renderable Program/sequence/sample mapping is available: " + ", ".join(missing))


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def music_report_paths(project: FragmenterProjectV1) -> dict[str, Path]:
    reports = resolve_runtime_paths(project).reports
    return {
        "graph": reports / "snddata_music_graph.json",
        "container_map": reports / "snddata_container_map.json",
        "summary": reports / "snddata_pipeline_summary.json",
    }


def load_music_reports(project: FragmenterProjectV1) -> dict[str, Any]:
    paths = music_report_paths(project)
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing SNDDATA reports: " + ", ".join(missing))
    return {key: _load_json(path) for key, path in paths.items()}


def _nodes(graph: dict[str, Any], node_type: str) -> list[dict[str, Any]]:
    return [row for row in graph.get("nodes", []) if isinstance(row, dict) and row.get("type") == node_type]


def _node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("id")): row for row in graph.get("nodes", []) if isinstance(row, dict) and row.get("id")}


def _edges(graph: dict[str, Any], relationship: str) -> list[dict[str, Any]]:
    return [row for row in graph.get("confirmed_edges", []) if isinstance(row, dict) and row.get("relationship") == relationship]


def _resource_offset(resource_id: str) -> int | None:
    match = re.search(r":0x([0-9A-Fa-f]+)$", str(resource_id))
    return int(match.group(1), 16) if match else None


def _plain(value: Any, default: Any = None) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return default if value is None else value


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    values = event.get("values") if isinstance(event.get("values"), dict) else {}
    normalized_values = {key: _plain(value) for key, value in values.items()}
    row = dict(event)
    row["absolute_ticks"] = int(_plain(event.get("absolute_ticks"), 0) or 0)
    if event.get("channel") is not None:
        row["channel"] = int(_plain(event.get("channel"), 0) or 0)
    row["values"] = normalized_values
    return row


def _midi_for_sequence(graph: dict[str, Any], sequence_id: str) -> dict[str, Any] | None:
    nodes = _node_map(graph)
    edge = next((row for row in _edges(graph, "sequence_midi") if row.get("source") == sequence_id), None)
    if not edge:
        return None
    target = nodes.get(str(edge.get("target")))
    return target if isinstance(target, dict) else None


def _program_groups(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for node in _nodes(graph, "program"):
        resource = str(node.get("resource") or "")
        if resource:
            groups.setdefault(resource, []).append(node)
    for rows in groups.values():
        rows.sort(key=lambda row: int(_plain((row.get("parsed") or {}).get("index"), 0) or 0))
    return groups


def candidate_program_resources(project: FragmenterProjectV1, sequence_id: str) -> list[dict[str, Any]]:
    reports = load_music_reports(project)
    graph = reports["graph"]
    groups = _program_groups(graph)
    sequence_node = _node_map(graph).get(sequence_id)
    sequence_resource = str(sequence_node.get("resource") or "") if sequence_node else ""
    rows: list[dict[str, Any]] = []
    for resource, programs in groups.items():
        offset = _resource_offset(resource)
        slot_count = sum(len((node.get("parsed") or {}).get("slots") or []) for node in programs)
        sample_dir = _sample_root(project, resource)
        sample_wavs = list(sample_dir.glob("*.wav")) if sample_dir.is_dir() else []
        rows.append(
            {
                "resource_id": resource,
                "resource_offset": offset,
                "program_count": len(programs),
                "slot_count": slot_count,
                "decoded_sample_wavs": len(sample_wavs),
                "same_resource_as_sequence": resource == sequence_resource,
                "status": "candidate",
            }
        )
    rows.sort(key=lambda row: (not row["same_resource_as_sequence"], -row["decoded_sample_wavs"], row["resource_offset"] if row["resource_offset"] is not None else 1 << 60))
    return rows


def sequence_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    reports = load_music_reports(project)
    graph = reports["graph"]
    snddata = resolve_project_snddata(project)
    rows: list[dict[str, Any]] = []
    for sequence in _nodes(graph, "sequence"):
        sequence_id = str(sequence["id"])
        midi = _midi_for_sequence(graph, sequence_id)
        parsed = midi.get("parsed") if isinstance(midi, dict) and isinstance(midi.get("parsed"), dict) else {}
        events = parsed.get("events") if isinstance(parsed.get("events"), list) else []
        note_on = sum(1 for event in events if isinstance(event, dict) and event.get("event_type") == "note_on" and int(_plain((event.get("values") or {}).get("velocity"), 0) or 0) > 0)
        saved = load_project_mapping(project, snddata, sequence_id)
        rows.append(
            {
                "sequence_id": sequence_id,
                "label": str(sequence.get("label") or sequence_id),
                "resource_id": str(sequence.get("resource") or ""),
                "midi_id": str(midi.get("id") or "") if midi else "",
                "event_count": len(events),
                "note_on_count": note_on,
                "mapping_status": "saved" if saved else "program unresolved",
                "saved_mapping": saved,
                "playable_sequence": bool(midi and note_on),
            }
        )
    return rows


def sequence_resolver_view_model(project: FragmenterProjectV1, sequence_id: str, selected_program: str | None = None) -> dict[str, Any]:
    candidates = candidate_program_resources(project, sequence_id)
    model = project_mapping_resolver(
        project,
        None,
        sequence_id,
        [row["resource_id"] for row in candidates],
        selected_program=selected_program,
    )
    model["candidate_details"] = candidates
    model["sequence"] = next((row for row in sequence_rows(project) if row["sequence_id"] == sequence_id), None)
    return model


def _sample_root(project: FragmenterProjectV1, resource_id: str) -> Path:
    offset = _resource_offset(resource_id)
    name = f"resource_{offset}" if offset is not None else "resource_unknown"
    return resolve_runtime_paths(project).media_pipeline / "decoded" / "audio" / "snddata" / "samples" / name


def _decoded_sample(path: Path, sample_id: int) -> DecodedSample:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError(f"Decoded sample WAV must be 16-bit PCM: {path}")
    values = [int.from_bytes(raw[index : index + 2], "little", signed=True) / 32768.0 for index in range(0, len(raw), 2)]
    mono = values[::channels] if channels > 1 else values
    return DecodedSample(index=sample_id, pcm=tuple(mono), sample_rate=rate)


def _sample_id_from_name(path: Path) -> int | None:
    match = re.match(r"sample_(\d+)_", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def decoded_samples_for_resource(project: FragmenterProjectV1, resource_id: str) -> list[DecodedSample]:
    root = _sample_root(project, resource_id)
    samples: list[DecodedSample] = []
    if not root.is_dir():
        return samples
    for path in sorted(root.glob("sample_*_*.wav"), key=lambda item: item.name.lower()):
        sample_id = _sample_id_from_name(path)
        if sample_id is None:
            continue
        try:
            samples.append(_decoded_sample(path, sample_id))
        except Exception:
            continue
    return samples


def _program_payloads(graph: dict[str, Any], resource_id: str, program_index: int | None = None) -> list[dict[str, Any]]:
    rows = _program_groups(graph).get(resource_id, [])
    programs = [dict(row.get("parsed") or {}) for row in rows]
    if program_index is not None:
        programs = [program for program in programs if int(_plain(program.get("index"), -1)) == int(program_index)]
    return programs


def _safe_preview_name(sequence_id: str, resource_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{sequence_id}__{resource_id}").strip("._")
    return value[:180] or "snddata_preview"


def render_sequence_preview(
    project: FragmenterProjectV1,
    sequence_id: str,
    program_resource: str,
    *,
    program_index: int | None = None,
    master_gain: float = 1.0,
    pan_mode: str = "equal_power",
) -> dict[str, Any]:
    reports = load_music_reports(project)
    graph = reports["graph"]
    midi = _midi_for_sequence(graph, sequence_id)
    missing: list[str] = []
    if midi is None:
        missing.append("parsed sequence to MIDI edge")
        events: list[dict[str, Any]] = []
        midi_report: dict[str, Any] = {}
    else:
        parsed = midi.get("parsed") if isinstance(midi.get("parsed"), dict) else {}
        events = [_normalize_event(event) for event in parsed.get("events", []) if isinstance(event, dict)]
        midi_report = parsed
        if not any(event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0 for event in events):
            missing.append("parsed note-on events")
    programs = _program_payloads(graph, program_resource, program_index)
    if not programs:
        missing.append("selected Program resource")
    samples = decoded_samples_for_resource(project, program_resource)
    if not samples:
        missing.append("decoded sample WAVs for selected Program resource")
    if missing:
        raise NoRenderableMapping(missing)

    params = RenderParameters(master_gain=float(master_gain), pan_mode=pan_mode)
    result = render(events, programs, samples, midi_report, params=params)
    if not result.frames:
        raise NoRenderableMapping(["rendered audio frames; Program slots may not resolve decoded sample IDs"])
    paths = resolve_runtime_paths(project)
    preview_dir = paths.media_pipeline / "decoded" / "audio" / "snddata" / "previews"
    preview_path = preview_dir / f"{_safe_preview_name(sequence_id, program_resource)}.wav"
    result.write_wav(preview_path)
    metadata = {
        "version": 1,
        "snddata": str(resolve_project_snddata(project)),
        "sequence_id": sequence_id,
        "program_resource": program_resource,
        "program_index": program_index,
        "event_count": len(events),
        "program_count": len(programs),
        "sample_count": len(samples),
        "frame_count": len(result.frames),
        "sample_rate": result.sample_rate,
        "duration": len(result.frames) / result.sample_rate if result.sample_rate else 0,
        "master_gain": master_gain,
        "pan_mode": pan_mode,
        "renderer_metadata": result.metadata,
        "output_path": str(preview_path),
        "status": "experimental_preview_rendered",
        "writes_game_data": False,
    }
    metadata_path = preview_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metadata["metadata_path"] = str(metadata_path)
    return metadata


def use_sequence_mapping(
    project: FragmenterProjectV1,
    sequence_id: str,
    program_resource: str,
    *,
    program_index: int | None = None,
    status: str = "manual",
    notes: str = "",
) -> dict[str, Any]:
    return save_project_mapping(
        project,
        None,
        sequence_id,
        program_resource,
        program_index=program_index,
        status=status,
        notes=notes,
    )

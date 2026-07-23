#!/usr/bin/env python3
"""Responsive public mixer facade with cross-resource sample-bank matching.

The v1 controller is intentionally conservative, but its GUI list path hashes the
large SNDDATA file once per sequence and assumes Program and Sample resources share
one resource ID.  This facade keeps the evidence rules while loading reports and
source mappings once per refresh, then scores decoded sample banks against Program
slot sample IDs.  The preview remains experimental and never writes game data.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import audio_mixer_controller_v1 as v1
from audio_mapping_controller_v1 import resolve_project_snddata
from project_preflight_v1 import resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1
from snddata_mapping_store_v1 import load_store, mapping_store_path, source_fingerprint
from snddata_player import RenderParameters, _slot_sample_reference, render

# v1 uses this renderer helper conceptually but does not export it.  Bind it once
# so the compatibility facade can keep all slot parsing rules in one place.
v1._slot_sample_reference = _slot_sample_reference

NoRenderableMapping = v1.NoRenderableMapping

_REPORT_CACHE: dict[str, tuple[tuple[tuple[str, int, int], ...], dict[str, Any]]] = {}
_FINGERPRINT_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}


def _report_signature(project: FragmenterProjectV1) -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    for path in v1.music_report_paths(project).values():
        stat = path.stat()
        rows.append((str(path.resolve()), stat.st_size, stat.st_mtime_ns))
    return tuple(rows)


def load_music_reports_cached(project: FragmenterProjectV1) -> dict[str, Any]:
    key = str(Path(project.workspace_dir).resolve())
    signature = _report_signature(project)
    cached = _REPORT_CACHE.get(key)
    if cached and cached[0] == signature:
        return cached[1]
    reports = v1.load_music_reports(project)
    _REPORT_CACHE[key] = (signature, reports)
    return reports


def clear_music_cache(project: FragmenterProjectV1 | None = None) -> None:
    if project is None:
        _REPORT_CACHE.clear()
        _FINGERPRINT_CACHE.clear()
    else:
        key = str(Path(project.workspace_dir).resolve())
        _REPORT_CACHE.pop(key, None)
        try:
            source = resolve_project_snddata(project)
        except FileNotFoundError:
            # RUN ALL may legitimately finish without SNDDATA. Cache cleanup is
            # best-effort and must not turn a successful run into a Tk traceback.
            return
        _FINGERPRINT_CACHE.pop(str(source.resolve()), None)


def _source_fingerprint_cached(source: Path) -> dict[str, Any]:
    resolved = str(source.resolve())
    stat = source.stat()
    cached = _FINGERPRINT_CACHE.get(resolved)
    if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
        return cached[2]
    fingerprint = source_fingerprint(source)
    _FINGERPRINT_CACHE[resolved] = (stat.st_size, stat.st_mtime_ns, fingerprint)
    return fingerprint


def _mapping_records(project: FragmenterProjectV1, snddata: Path) -> dict[str, dict[str, Any]]:
    """Read all mappings after one exact-source fingerprint operation."""
    fingerprint = _source_fingerprint_cached(snddata)
    store = load_store(mapping_store_path(project))
    source = (store.get("sources") or {}).get(fingerprint["source_id"])
    mappings = source.get("mappings") if isinstance(source, dict) else None
    return {str(key): dict(value) for key, value in (mappings or {}).items() if isinstance(value, dict)}


def sequence_rows_fast(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    reports = load_music_reports_cached(project)
    graph = reports["graph"]
    mappings = _mapping_records(project, resolve_project_snddata(project))
    rows: list[dict[str, Any]] = []
    for sequence in v1._nodes(graph, "sequence"):
        sequence_id = str(sequence["id"])
        midi = v1._midi_for_sequence(graph, sequence_id)
        parsed = midi.get("parsed") if isinstance(midi, dict) and isinstance(midi.get("parsed"), dict) else {}
        events = parsed.get("events") if isinstance(parsed.get("events"), list) else []
        note_on = sum(
            1
            for event in events
            if isinstance(event, dict)
            and event.get("event_type") == "note_on"
            and int(v1._plain((event.get("values") or {}).get("velocity"), 0) or 0) > 0
        )
        saved = mappings.get(sequence_id)
        playable = bool(midi and note_on)
        if saved:
            status = "saved"
        elif playable:
            status = "playable / unresolved"
        elif midi:
            status = "no note events"
        else:
            status = "MIDI unresolved"
        rows.append(
            {
                "sequence_id": sequence_id,
                "label": str(sequence.get("label") or sequence_id),
                "resource_id": str(sequence.get("resource") or ""),
                "midi_id": str(midi.get("id") or "") if midi else "",
                "event_count": len(events),
                "note_on_count": note_on,
                "mapping_status": status,
                "saved_mapping": saved,
                "playable_sequence": playable,
            }
        )
    rows.sort(key=lambda row: (not row["playable_sequence"], row["mapping_status"] != "saved", row["sequence_id"]))
    return rows


def _required_sample_ids(programs: list[dict[str, Any]]) -> set[int]:
    required: set[int] = set()
    for program in programs:
        for slot in program.get("slots") or []:
            if not isinstance(slot, dict):
                continue
            _field, sample_id = v1._slot_sample_reference(slot)
            if sample_id is not None:
                required.add(int(sample_id))
    return required


def _sample_bank_rows(project: FragmenterProjectV1, graph: dict[str, Any]) -> list[dict[str, Any]]:
    root = resolve_runtime_paths(project).media_pipeline / "decoded" / "audio" / "snddata" / "samples"
    resource_by_offset: dict[int, str] = {}
    for node in v1._nodes(graph, "resource"):
        resource_id = str(node.get("id") or "")
        offset = v1._resource_offset(resource_id)
        if offset is not None:
            resource_by_offset[offset] = resource_id
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for folder in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name.lower()):
        match = re.fullmatch(r"resource_(\d+)", folder.name, re.IGNORECASE)
        if not match:
            continue
        offset = int(match.group(1))
        ids = {
            sample_id
            for sample_id in (v1._sample_id_from_name(path) for path in folder.glob("sample_*_*.wav"))
            if sample_id is not None
        }
        if not ids:
            continue
        rows.append(
            {
                "resource_id": resource_by_offset.get(offset, f"resource:unknown:0x{offset:X}"),
                "resource_offset": offset,
                "path": str(folder),
                "sample_ids": ids,
                "decoded_sample_wavs": len(ids),
            }
        )
    return rows


def choose_sample_bank(required_ids: set[int], banks: list[dict[str, Any]], preferred_resource: str = "") -> dict[str, Any] | None:
    if not banks:
        return None

    def score(bank: dict[str, Any]) -> tuple[float, int, int, int]:
        available = set(bank.get("sample_ids") or set())
        overlap = len(required_ids & available)
        coverage = overlap / len(required_ids) if required_ids else (1.0 if available else 0.0)
        preferred = 1 if bank.get("resource_id") == preferred_resource else 0
        return coverage, overlap, preferred, len(available)

    return max(banks, key=score)


def candidate_program_resources_fast(project: FragmenterProjectV1, sequence_id: str) -> list[dict[str, Any]]:
    reports = load_music_reports_cached(project)
    graph = reports["graph"]
    groups = v1._program_groups(graph)
    sequence_node = v1._node_map(graph).get(sequence_id)
    sequence_resource = str(sequence_node.get("resource") or "") if sequence_node else ""
    banks = _sample_bank_rows(project, graph)
    rows: list[dict[str, Any]] = []
    for resource, program_nodes in groups.items():
        programs = [dict(node.get("parsed") or {}) for node in program_nodes]
        required = _required_sample_ids(programs)
        bank = choose_sample_bank(required, banks, resource)
        available = set(bank.get("sample_ids") or set()) if bank else set()
        overlap = len(required & available)
        coverage = overlap / len(required) if required else (1.0 if available else 0.0)
        slot_count = sum(len(program.get("slots") or []) for program in programs)
        rows.append(
            {
                "resource_id": resource,
                "resource_offset": v1._resource_offset(resource),
                "program_count": len(programs),
                "slot_count": slot_count,
                "decoded_sample_wavs": int(bank.get("decoded_sample_wavs") or 0) if bank else 0,
                "sample_resource_id": str(bank.get("resource_id") or "") if bank else "",
                "sample_bank_path": str(bank.get("path") or "") if bank else "",
                "required_sample_ids": sorted(required),
                "sample_id_overlap": overlap,
                "sample_id_coverage": coverage,
                "same_resource_as_sequence": resource == sequence_resource,
                "same_resource_sample_bank": bool(bank and bank.get("resource_id") == resource),
                "renderable_candidate": bool(programs and bank and available),
                "status": "candidate",
            }
        )
    rows.sort(
        key=lambda row: (
            not row["renderable_candidate"],
            -float(row["sample_id_coverage"]),
            not row["same_resource_as_sequence"],
            -int(row["decoded_sample_wavs"]),
            row["resource_offset"] if row["resource_offset"] is not None else 1 << 60,
        )
    )
    return rows


def sequence_resolver_view_model_fast(project: FragmenterProjectV1, sequence_id: str) -> dict[str, Any]:
    candidates = candidate_program_resources_fast(project, sequence_id)
    sequence = next((row for row in sequence_rows_fast(project) if row["sequence_id"] == sequence_id), None)
    return {
        "sequence_id": sequence_id,
        "status": "resolved" if sequence and sequence.get("saved_mapping") else "program unresolved",
        "sequence": sequence,
        "candidate_details": candidates,
        "candidate_count": len(candidates),
        "renderable_candidate_count": sum(1 for row in candidates if row.get("renderable_candidate")),
        "writes_game_data": False,
    }


def _decoded_samples_from_bank(path: Path) -> list[Any]:
    samples = []
    if not path.is_dir():
        return samples
    for wav in sorted(path.glob("sample_*_*.wav"), key=lambda item: item.name.lower()):
        sample_id = v1._sample_id_from_name(wav)
        if sample_id is None:
            continue
        try:
            samples.append(v1._decoded_sample(wav, sample_id))
        except Exception:
            continue
    return samples


def remap_unresolved_slots(programs: list[dict[str, Any]], available_ids: list[int]) -> list[dict[str, Any]]:
    """Build an explicitly experimental fallback mapping for audition only."""
    if not available_ids:
        return programs
    remapped = copy.deepcopy(programs)
    for program_index, program in enumerate(remapped):
        slots = program.get("slots") or []
        for slot_index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                continue
            field, sample_id = v1._slot_sample_reference(slot)
            if sample_id in available_ids:
                continue
            chosen = available_ids[(program_index + slot_index) % len(available_ids)]
            slot[field or "sample_id"] = chosen
            slot["experimental_sample_remap"] = True
    return remapped


def render_sequence_preview_fast(
    project: FragmenterProjectV1,
    sequence_id: str,
    program_resource: str,
    *,
    sample_bank_path: str | Path | None = None,
    program_index: int | None = None,
    master_gain: float = 1.0,
    pan_mode: str = "equal_power",
) -> dict[str, Any]:
    reports = load_music_reports_cached(project)
    graph = reports["graph"]
    midi = v1._midi_for_sequence(graph, sequence_id)
    missing: list[str] = []
    if midi is None:
        missing.append("parsed sequence to MIDI edge")
        events: list[dict[str, Any]] = []
        midi_report: dict[str, Any] = {}
    else:
        parsed = midi.get("parsed") if isinstance(midi.get("parsed"), dict) else {}
        events = [v1._normalize_event(event) for event in parsed.get("events", []) if isinstance(event, dict)]
        midi_report = parsed
        if not any(event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0 for event in events):
            missing.append("parsed note-on events")
    programs = v1._program_payloads(graph, program_resource, program_index)
    if not programs:
        missing.append("selected Program resource")
    bank_path = Path(sample_bank_path).expanduser() if sample_bank_path else v1._sample_root(project, program_resource)
    samples = _decoded_samples_from_bank(bank_path)
    if not samples:
        missing.append("decoded sample WAVs for selected Program/sample bank")
    if missing:
        raise NoRenderableMapping(missing)

    params = RenderParameters(master_gain=float(master_gain), pan_mode=pan_mode)
    result = render(events, programs, samples, midi_report, params=params)
    experimental_remap = False
    if not result.frames:
        available_ids = sorted(sample.index for sample in samples)
        remapped = remap_unresolved_slots(programs, available_ids)
        result = render(events, remapped, samples, midi_report, params=params)
        experimental_remap = bool(result.frames)
    if not result.frames:
        raise NoRenderableMapping(["rendered audio frames; Program slots still do not resolve decoded sample IDs"])

    paths = resolve_runtime_paths(project)
    preview_dir = paths.media_pipeline / "decoded" / "audio" / "snddata" / "previews"
    preview_path = preview_dir / f"{v1._safe_preview_name(sequence_id, program_resource)}.wav"
    result.write_wav(preview_path)
    metadata = {
        "version": 2,
        "snddata": str(resolve_project_snddata(project)),
        "sequence_id": sequence_id,
        "program_resource": program_resource,
        "program_index": program_index,
        "sample_bank_path": str(bank_path),
        "event_count": len(events),
        "program_count": len(programs),
        "sample_count": len(samples),
        "frame_count": len(result.frames),
        "sample_rate": result.sample_rate,
        "duration": len(result.frames) / result.sample_rate if result.sample_rate else 0,
        "master_gain": master_gain,
        "pan_mode": pan_mode,
        "experimental_slot_remap": experimental_remap,
        "renderer_metadata": result.metadata,
        "output_path": str(preview_path),
        "status": "experimental_preview_rendered",
        "writes_game_data": False,
    }
    metadata_path = preview_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metadata["metadata_path"] = str(metadata_path)
    return metadata

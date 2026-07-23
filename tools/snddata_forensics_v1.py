#!/usr/bin/env python3
"""Forensic SNDDATA sequencing report for the Fragment public-release workbench.

This module compares routing hypotheses instead of promoting Standard MIDI rules to
format facts.  It consumes the observed FF0A SCEIMidi track framing, parsed
SCEIProg tables/slots, decoded sample metadata, and raw SCEISequ bytes.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import scei_midi_v3
import snddata_music_system_v3 as music_v3
import snddata_music_system_v4 as music_v4
import snddata_parser
from project_sound_v1 import canonical_snddata_path, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1

REPORT_JSON = "snddata_forensics_v1.json"
REPORT_TXT = "snddata_forensics_v1.txt"


def _tag(section: snddata_parser.Section) -> str:
    return snddata_parser.SECTION_TAGS.get(section.signature, "unknown")


def _sections(group: snddata_parser.ResourceGroup, tag: str) -> list[snddata_parser.Section]:
    return [section for section in group.sections if section.valid and _tag(section) == tag]


def _u32_words(data: bytes, start: int, end: int, *, max_words: int = 32) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    limit = min(end, start + max_words * 4)
    for offset in range(start, limit - 3, 4):
        raw = data[offset : offset + 4]
        rows.append({"absolute_offset": offset, "relative_offset": offset - start, "raw": raw.hex(), "u32le": struct.unpack_from("<I", raw)[0]})
    return rows


def _sample_inventory(project: FragmenterProjectV1) -> dict[int, dict[str, Any]]:
    inventory = music_v4._sample_inventory(project)
    return {
        int(resource): {
            "sample_ids": sorted(int(value) for value in bucket.get("sample_ids") or []),
            "decoded_rows": int(bucket.get("decoded_rows") or 0),
            "structured_rows": int(bucket.get("structured_rows") or 0),
        }
        for resource, bucket in inventory.items()
    }


def _program_resource_row(group: snddata_parser.ResourceGroup, inventory: dict[int, dict[str, Any]]) -> dict[str, Any]:
    programs = music_v3._programs(group)
    bucket = inventory.get(int(group.offset), {"sample_ids": [], "decoded_rows": 0, "structured_rows": 0})
    return {
        "resource_offset": int(group.offset),
        "resource_hex": f"0x{group.offset:X}",
        "classification": group.classification,
        "program_count": len(programs),
        "program_indexes": [int(program["index"]) for program in programs],
        "slot_count": sum(len(program.get("slots") or []) for program in programs),
        "slot_sample_ids": sorted({int(slot["sample_id"]) for program in programs for slot in program.get("slots") or [] if int(slot.get("sample_id", -1)) >= 0}),
        "decoded_sample_ids": list(bucket["sample_ids"]),
        "decoded_sample_count": int(bucket["decoded_rows"]),
        "structured_sample_rows": int(bucket["structured_rows"]),
        "programs": programs,
    }


def _sequ_evidence(data: bytes, group: snddata_parser.ResourceGroup, program_offsets: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset_set = set(program_offsets)
    for section in _sections(group, "SCEISequ"):
        end = int(section.end_offset or min(len(data), section.offset + int(section.block_size or 0)))
        words = _u32_words(data, section.offset + 8, end)
        for word in words:
            value = int(word["u32le"])
            matches: list[dict[str, Any]] = []
            if value in offset_set:
                matches.append({"kind": "absolute_program_resource_offset", "program_resource_offset": value})
            if group.offset + value in offset_set:
                matches.append({"kind": "resource_relative_program_offset", "program_resource_offset": group.offset + value})
            if section.offset + value in offset_set:
                matches.append({"kind": "section_relative_program_offset", "program_resource_offset": section.offset + value})
            if 0 <= value < len(program_offsets):
                matches.append({"kind": "program_resource_ordinal", "program_resource_offset": program_offsets[value]})
            word["program_resource_matches"] = matches
        rows.append(
            {
                "section_offset": int(section.offset),
                "section_hex": f"0x{section.offset:X}",
                "block_size": int(section.block_size or 0),
                "raw_prefix_hex": data[section.offset : min(end, section.offset + 96)].hex(),
                "u32_words": words,
                "matched_words": [word for word in words if word["program_resource_matches"]],
            }
        )
    return rows


def _midi_reports(data: bytes, group: snddata_parser.ResourceGroup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in _sections(group, "SCEIMidi"):
        if section.end_offset is None:
            continue
        parsed = scei_midi_v3.parse_scei_midi(data[section.offset : section.end_offset], f"resource@0x{group.offset:X}/midi@0x{section.offset:X}")
        parsed["resource_offset"] = int(group.offset)
        parsed["section_offset"] = int(section.offset)
        rows.append(parsed)
    return rows


def _note_events(midi_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for report in midi_reports
        for event in report.get("events") or []
        if event.get("event_type") == "note_on" and int((event.get("values") or {}).get("velocity") or 0) > 0
    ]


def _required_program_indexes(midi_reports: list[dict[str, Any]], mode: str) -> list[int]:
    notes = _note_events(midi_reports)
    if mode == "program_change":
        return sorted({int(event["program_index"]) for event in notes if isinstance(event.get("program_index"), int)})
    if mode == "channel_as_program":
        return sorted({int(event["channel"]) for event in notes if isinstance(event.get("channel"), int)})
    if mode == "program_zero":
        return [0] if notes else []
    raise ValueError(mode)


def _candidate(program_resource: dict[str, Any], required: list[int], sequence_offset: int) -> dict[str, Any]:
    by_index = {int(program["index"]): program for program in program_resource["programs"]}
    missing_programs = [index for index in required if index not in by_index]
    required_samples = sorted({int(slot["sample_id"]) for index in required for slot in (by_index.get(index) or {}).get("slots") or [] if int(slot.get("sample_id", -1)) >= 0})
    available = set(int(value) for value in program_resource["decoded_sample_ids"])
    matched = sorted(set(required_samples) & available)
    missing_samples = sorted(set(required_samples) - available)
    distance = abs(int(sequence_offset) - int(program_resource["resource_offset"]))
    if not required:
        status = "no_program_indexes_for_hypothesis"
    elif missing_programs:
        status = "missing_program_indexes"
    elif not required_samples:
        status = "programs_have_no_parsed_slot_samples"
    elif missing_samples:
        status = "missing_decoded_samples"
    else:
        status = "renderer_input_complete"
    return {
        "resource_offset": int(program_resource["resource_offset"]),
        "resource_hex": program_resource["resource_hex"],
        "distance": distance,
        "required_program_indexes": required,
        "missing_program_indexes": missing_programs,
        "required_sample_ids": required_samples,
        "matched_sample_ids": matched,
        "missing_sample_ids": missing_samples,
        "program_count": int(program_resource["program_count"]),
        "decoded_sample_count": int(program_resource["decoded_sample_count"]),
        "status": status,
        "score": (
            (10000 if not missing_programs and required else 0)
            + (5000 if required_samples and not missing_samples else 0)
            + len(matched) * 10
            + min(int(program_resource["structured_sample_rows"]), 100)
            - min(distance // 100_000, 1000)
        ),
    }


def _hypothesis_rows(program_resources: list[dict[str, Any]], midi_reports: list[dict[str, Any]], sequence_offset: int) -> list[dict[str, Any]]:
    program_changes = sum(int(report.get("program_change_count") or 0) for report in midi_reports)
    hypotheses = [
        ("program_change", "Observed MIDI Program Change state", "high" if program_changes else "unsupported_by_current_events"),
        ("channel_as_program", "MIDI channel number maps directly to SCEIProg index", "experimental"),
        ("program_zero", "Legacy implicit Program 0", "legacy_diagnostic_only"),
    ]
    rows: list[dict[str, Any]] = []
    for mode, label, confidence in hypotheses:
        required = _required_program_indexes(midi_reports, mode)
        candidates = sorted((_candidate(resource, required, sequence_offset) for resource in program_resources), key=lambda row: (-int(row["score"]), int(row["distance"]), int(row["resource_offset"])))
        best = candidates[0] if candidates else None
        wall = "no SCEIProg resources parsed" if not candidates else str(best["status"])
        rows.append(
            {
                "mode": mode,
                "label": label,
                "confidence": confidence,
                "required_program_indexes": required,
                "best_candidate": best,
                "candidates": candidates[:50],
                "first_wall": wall,
            }
        )
    return rows


def _nearest_programs(sequence_offset: int, program_offsets: list[int], limit: int = 8) -> dict[str, list[dict[str, int]]]:
    before = sorted((offset for offset in program_offsets if offset < sequence_offset), reverse=True)[:limit]
    after = sorted(offset for offset in program_offsets if offset > sequence_offset)[:limit]
    return {
        "preceding": [{"resource_offset": value, "distance": sequence_offset - value} for value in before],
        "following": [{"resource_offset": value, "distance": value - sequence_offset} for value in after],
    }


def build_forensics(
    project: FragmenterProjectV1,
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source = canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(f"Canonical SNDDATA source is missing: {source}")
    data = source.read_bytes()
    groups = snddata_parser.parse_blob(data, source.as_posix())
    inventory = _sample_inventory(project)
    program_resources = [_program_resource_row(group, inventory) for group in groups if music_v3._programs(group)]
    program_offsets = [int(row["resource_offset"]) for row in program_resources]
    sequences: list[dict[str, Any]] = []
    sequence_groups = [group for group in groups if _sections(group, "SCEIMidi") or _sections(group, "SCEISequ")]
    total = len(sequence_groups)

    for index, group in enumerate(sequence_groups, 1):
        midi_reports = _midi_reports(data, group)
        notes = _note_events(midi_reports)
        hypotheses = _hypothesis_rows(program_resources, midi_reports, int(group.offset))
        sequ = _sequ_evidence(data, group, program_offsets)
        matched_sequ_words = [word for section in sequ for word in section["matched_words"]]
        if not midi_reports:
            first_wall = "no valid SCEIMidi section in sequence resource"
        elif not any(int(report.get("track_count") or 0) for report in midi_reports):
            first_wall = "FF0A track preamble not parsed"
        elif not notes:
            first_wall = "track framing parsed but no positive-velocity Note On events decoded"
        else:
            complete = [row for row in hypotheses if isinstance(row.get("best_candidate"), dict) and row["best_candidate"].get("status") == "renderer_input_complete"]
            first_wall = "renderer audition required" if complete else "no routing hypothesis currently reaches complete Program/slot/sample input"
        sequences.append(
            {
                "sequence_id": f"sequence@0x{group.offset:X}",
                "resource_offset": int(group.offset),
                "resource_hex": f"0x{group.offset:X}",
                "classification": group.classification,
                "section_tags": [_tag(section) for section in group.sections if section.valid],
                "midi_reports": midi_reports,
                "midi_summary": {
                    "sections": len(midi_reports),
                    "tracks": sum(int(report.get("track_count") or 0) for report in midi_reports),
                    "events": sum(int(report.get("event_count") or 0) for report in midi_reports),
                    "notes": len(notes),
                    "program_changes": sum(int(report.get("program_change_count") or 0) for report in midi_reports),
                    "note_channels": sorted({int(event["channel"]) for event in notes if isinstance(event.get("channel"), int)}),
                    "notes_without_program_change": sum(int(report.get("notes_without_program_change") or 0) for report in midi_reports),
                    "parser_statuses": [report.get("parser_status") for report in midi_reports],
                    "event_types": _merge_counts(report.get("event_types") or {} for report in midi_reports),
                },
                "scei_sequ": sequ,
                "scei_sequ_program_resource_matches": matched_sequ_words,
                "nearest_program_resources": _nearest_programs(int(group.offset), program_offsets),
                "routing_hypotheses": hypotheses,
                "first_wall": first_wall,
            }
        )
        if callback is not None and (index == total or index % 10 == 0):
            callback({"kind": "snddata_forensics_progress", "current": index, "total": total})

    summary = {
        "version": 1,
        "source": str(source),
        "source_size": len(data),
        "resources": len(groups),
        "program_resources": len(program_resources),
        "sequence_resources": len(sequences),
        "sequences_with_tracks": sum(1 for row in sequences if int(row["midi_summary"]["tracks"]) > 0),
        "sequences_with_notes": sum(1 for row in sequences if int(row["midi_summary"]["notes"]) > 0),
        "sequences_with_program_changes": sum(1 for row in sequences if int(row["midi_summary"]["program_changes"]) > 0),
        "sequences_with_sequ_program_matches": sum(1 for row in sequences if row["scei_sequ_program_resource_matches"]),
        "program_change_complete_inputs": _complete_count(sequences, "program_change"),
        "channel_as_program_complete_inputs": _complete_count(sequences, "channel_as_program"),
        "program_zero_complete_inputs": _complete_count(sequences, "program_zero"),
        "parser_authority": "SCEIMidi FF0A track preamble + MIDI-like event timeline; SCEIProg table/header/slot fields; decoded sample metadata",
        "format_claims": [
            "Program Change routing is only authoritative when C0 events are actually observed.",
            "Channel->Program and Program 0 are explicit hypotheses, not format claims.",
            "SCEISequ words are preserved and tested as offset/index candidates; matches are evidence only.",
        ],
    }
    return {"summary": summary, "program_resources": program_resources, "sequences": sequences}


def _complete_count(sequences: list[dict[str, Any]], mode: str) -> int:
    count = 0
    for sequence in sequences:
        hypothesis = next((row for row in sequence["routing_hypotheses"] if row["mode"] == mode), None)
        if hypothesis and isinstance(hypothesis.get("best_candidate"), dict) and hypothesis["best_candidate"].get("status") == "renderer_input_complete":
            count += 1
    return count


def _merge_counts(values) -> dict[str, int]:
    output: dict[str, int] = {}
    for row in values:
        for key, value in row.items():
            output[str(key)] = output.get(str(key), 0) + int(value)
    return output


def write_forensics(project: FragmenterProjectV1, payload: dict[str, Any]) -> tuple[Path, Path]:
    root = sound_reports_root(project)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / REPORT_JSON
    txt_path = root / REPORT_TXT
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = payload["summary"]
    lines = [
        "Fragmenter SNDDATA Forensics v1",
        f"Source: {summary['source']}",
        f"Resources: {summary['resources']} | Program resources: {summary['program_resources']} | sequence resources: {summary['sequence_resources']}",
        f"Tracks parsed: {summary['sequences_with_tracks']} sequences | notes parsed: {summary['sequences_with_notes']} sequences | Program Change observed: {summary['sequences_with_program_changes']} sequences",
        f"Complete renderer inputs: Program Change {summary['program_change_complete_inputs']} | channel->Program {summary['channel_as_program_complete_inputs']} | Program 0 {summary['program_zero_complete_inputs']}",
        f"SCEISequ fields matching Program resources: {summary['sequences_with_sequ_program_matches']} sequences",
        "",
        "Sequences:",
    ]
    for sequence in payload["sequences"]:
        midi = sequence["midi_summary"]
        lines.append(
            f"- {sequence['sequence_id']} tracks={midi['tracks']} events={midi['events']} notes={midi['notes']} pc={midi['program_changes']} channels={midi['note_channels']} | WALL: {sequence['first_wall']}"
        )
        for hypothesis in sequence["routing_hypotheses"]:
            best = hypothesis.get("best_candidate") or {}
            lines.append(
                f"    {hypothesis['mode']}: programs={hypothesis['required_program_indexes']} -> {best.get('resource_hex', '-')} {best.get('status', hypothesis['first_wall'])} samples={best.get('matched_sample_ids', [])}/{best.get('required_sample_ids', [])} confidence={hypothesis['confidence']}"
            )
        for word in sequence["scei_sequ_program_resource_matches"][:8]:
            lines.append(f"    SCEISequ +0x{word['relative_offset']:X} value={word['u32le']} matches={word['program_resource_matches']}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, txt_path


def analyze_and_write(project: FragmenterProjectV1, *, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    payload = build_forensics(project, callback=callback)
    json_path, txt_path = write_forensics(project, payload)
    return {**payload["summary"], "report_path": str(json_path), "text_report_path": str(txt_path)}

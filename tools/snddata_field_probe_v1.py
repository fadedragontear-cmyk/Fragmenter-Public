#!/usr/bin/env python3
"""Read-only SNDDATA field semantics and PS-ADPCM density probe."""
from __future__ import annotations

import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import project_sound_v4 as project_sound
import scei_midi_v4
import snddata_music_system_v3 as music_v3
import snddata_parser
from project_workspace_v1 import FragmenterProjectV1

REPORT_JSON = "snddata_field_probe_v1.json"
REPORT_TXT = "snddata_field_probe_v1.txt"
PROBE_TAGS = ("SCEIHead", "SCEIVagi", "SCEISmpl", "SCEISset")


def _tag(section: snddata_parser.Section) -> str:
    return snddata_parser.SECTION_TAGS.get(section.signature, "unknown")


def _payload(data: bytes, section: snddata_parser.Section) -> bytes:
    start = section.offset + 0x10
    end = int(section.end_offset or start)
    return data[start:max(start, end)]


def _words(raw: bytes, width: int, limit: int = 64) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    end = min(len(raw), limit)
    for offset in range(0, end - width + 1, width):
        chunk = raw[offset : offset + width]
        rows.append({"offset": offset, "hex": chunk.hex(), f"u{width * 8}le": int.from_bytes(chunk, "little")})
    return rows


def adpcm_density(raw: bytes) -> dict[str, Any]:
    block_count = len(raw) // 16
    flags: Counter[int] = Counter()
    valid = 0
    likely_data = 0
    zero = 0
    terminators = 0
    invalid_examples: list[dict[str, Any]] = []
    for index in range(block_count):
        block = raw[index * 16 : index * 16 + 16]
        predictor = block[0] >> 4
        shift = block[0] & 0x0F
        flag = block[1]
        flags[flag] += 1
        if block == b"\x00" * 16:
            zero += 1
        if flag == 7:
            terminators += 1
        ok = predictor < 5 and shift <= 12
        if ok:
            valid += 1
            if block != b"\x00" * 16 and flag != 7:
                likely_data += 1
        elif len(invalid_examples) < 8:
            invalid_examples.append({"block_index": index, "offset": index * 16, "predictor": predictor, "shift": shift, "flag": flag, "hex": block.hex()})
    return {
        "payload_size": len(raw),
        "aligned_size": block_count * 16,
        "block_count": block_count,
        "valid_predictor_shift_blocks": valid,
        "valid_density": round(valid / block_count, 6) if block_count else 0.0,
        "likely_data_blocks": likely_data,
        "likely_data_density": round(likely_data / block_count, 6) if block_count else 0.0,
        "zero_blocks": zero,
        "terminator_flag_blocks": terminators,
        "flag_histogram": {str(key): value for key, value in sorted(flags.items())},
        "invalid_examples": invalid_examples,
    }


def _table_candidates(vagi: bytes, smpl_size: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for count_offset in (0, 4, 8, 12, 16, 20, 24, 28):
        if count_offset + 4 > len(vagi):
            continue
        count = struct.unpack_from("<I", vagi, count_offset)[0]
        if not 0 < count <= 4096:
            continue
        for stride in (8, 12, 16):
            table_start = count_offset + 4
            table_end = table_start + count * stride
            if table_end > len(vagi):
                continue
            valid = 0
            samples: list[dict[str, Any]] = []
            for index in range(count):
                offset = table_start + index * stride
                sample_offset = struct.unpack_from("<I", vagi, offset)[0]
                sample_size = struct.unpack_from("<I", vagi, offset + 4)[0]
                in_bounds = sample_size > 0 and sample_offset + sample_size <= smpl_size
                valid += int(in_bounds)
                if index < 8:
                    samples.append({"index": index, "offset": sample_offset, "size": sample_size, "in_bounds": in_bounds, "extra_hex": vagi[offset + 8 : offset + stride].hex()})
            candidates.append(
                {
                    "count_offset": count_offset,
                    "count": count,
                    "stride": stride,
                    "table_start": table_start,
                    "table_end": table_end,
                    "valid_entries": valid,
                    "coverage": round(valid / count, 6),
                    "sample_rows": samples,
                }
            )
    return sorted(candidates, key=lambda row: (-row["coverage"], -row["valid_entries"], row["count_offset"], row["stride"]))[:20]


def _sample_error_histogram(project: FragmenterProjectV1) -> dict[str, Any]:
    root = project_sound.sound_decoded_root(project) / "snddata" / "samples"
    errors: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    rows = 0
    for path in sorted(root.rglob("sample_*.json")) if root.is_dir() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors["invalid_metadata_json"] += 1
            continue
        if not isinstance(payload, dict):
            errors["metadata_not_object"] += 1
            continue
        rows += 1
        statuses[str(payload.get("decode_status") or "unknown")] += 1
        for error in payload.get("errors") or []:
            errors[str(error)] += 1
    return {"metadata_rows": rows, "decode_statuses": dict(statuses.most_common()), "errors": dict(errors.most_common())}


def _strict_midi_summary(data: bytes, groups: list[snddata_parser.ResourceGroup]) -> dict[str, Any]:
    sections = []
    first_invalid = []
    for group in groups:
        for section in group.sections:
            if not section.valid or _tag(section) != "SCEIMidi" or section.end_offset is None:
                continue
            report = scei_midi_v4.parse_scei_midi(data[section.offset : section.end_offset], f"resource@0x{group.offset:X}/midi@0x{section.offset:X}")
            invalid = (report.get("strict_validation") or {}).get("first_invalid_event")
            row = {
                "resource_offset": int(group.offset),
                "section_offset": int(section.offset),
                "tracks": int(report.get("track_count") or 0),
                "trusted_events": int(report.get("event_count") or 0),
                "raw_events": int(report.get("raw_event_count") or 0),
                "discarded_events": int(report.get("discarded_event_count") or 0),
                "program_changes": int(report.get("program_change_count") or 0),
                "strict_invalid_tracks": int((report.get("strict_validation") or {}).get("invalid_tracks") or 0),
                "first_invalid_event": invalid,
            }
            sections.append(row)
            if invalid:
                first_invalid.append(row)
    return {
        "sections": len(sections),
        "sections_with_invalid_high_bit_data": sum(1 for row in sections if row["strict_invalid_tracks"]),
        "trusted_events": sum(row["trusted_events"] for row in sections),
        "raw_events": sum(row["raw_events"] for row in sections),
        "discarded_events": sum(row["discarded_events"] for row in sections),
        "trusted_program_changes": sum(row["program_changes"] for row in sections),
        "first_invalid_sections": first_invalid[:50],
        "section_rows": sections,
    }


def build_field_probe(project: FragmenterProjectV1, *, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    source = project_sound.canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(f"Canonical SNDDATA source is missing: {source}")
    data = source.read_bytes()
    groups = snddata_parser.parse_blob(data, source.as_posix())
    banks: list[dict[str, Any]] = []
    program_groups = [group for group in groups if any(section.valid and _tag(section) == "SCEIProg" for section in group.sections)]
    total = len(program_groups)
    for index, group in enumerate(program_groups, 1):
        sections = {tag: next((section for section in group.sections if section.valid and _tag(section) == tag), None) for tag in PROBE_TAGS}
        payloads = {tag: _payload(data, section) if section is not None else b"" for tag, section in sections.items()}
        programs = music_v3._programs(group)
        slot_ids = sorted({int(slot["sample_id"]) for program in programs for slot in program.get("slots") or [] if int(slot.get("sample_id", -1)) >= 0})
        section_rows = {}
        for tag in PROBE_TAGS:
            section = sections[tag]
            raw = payloads[tag]
            section_rows[tag] = {
                "present": section is not None,
                "section_offset": int(section.offset) if section is not None else None,
                "block_size": int(section.block_size or 0) if section is not None else None,
                "payload_size": len(raw),
                "prefix_hex": raw[:128].hex(),
                "u16_words": _words(raw, 2),
                "u32_words": _words(raw, 4),
                "adpcm_density": adpcm_density(raw) if tag in {"SCEISmpl", "SCEISset"} else None,
            }
        banks.append(
            {
                "resource_offset": int(group.offset),
                "resource_hex": f"0x{group.offset:X}",
                "program_count": len(programs),
                "slot_count": sum(len(program.get("slots") or []) for program in programs),
                "slot_sample_ids": slot_ids,
                "max_slot_sample_id": max(slot_ids) if slot_ids else None,
                "sections": section_rows,
                "vagi_table_candidates": _table_candidates(payloads["SCEIVagi"], len(payloads["SCEISmpl"])),
            }
        )
        if callback is not None and (index == total or index % 10 == 0):
            callback({"kind": "snddata_field_probe_progress", "current": index, "total": total})

    ranked = sorted(
        banks,
        key=lambda row: (
            -int((row["sections"]["SCEISmpl"].get("payload_size") or 0)),
            -int(row["slot_count"]),
            int(row["resource_offset"]),
        ),
    )
    summary = {
        "version": 1,
        "source": str(source),
        "source_size": len(data),
        "resources": len(groups),
        "program_banks": len(banks),
        "banks_with_full_vagi_table_candidate": sum(1 for row in banks if row["vagi_table_candidates"] and row["vagi_table_candidates"][0]["coverage"] == 1.0),
        "banks_with_smpl_payload": sum(1 for row in banks if row["sections"]["SCEISmpl"]["payload_size"]),
        "banks_with_sset_payload": sum(1 for row in banks if row["sections"]["SCEISset"]["payload_size"]),
    }
    return {
        "summary": summary,
        "sample_error_histogram": _sample_error_histogram(project),
        "strict_midi": _strict_midi_summary(data, groups),
        "representative_banks": ranked[:12],
        "banks": banks,
    }


def write_field_probe(project: FragmenterProjectV1, *, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    payload = build_field_probe(project, callback=callback)
    root = project.workspace_path("diagnostics") / "audio"
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / REPORT_JSON
    txt_path = root / REPORT_TXT
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    txt_path.write_text(render_text(payload), encoding="utf-8")
    return {**payload["summary"], **{f"strict_midi_{key}": value for key, value in payload["strict_midi"].items() if key != "section_rows" and key != "first_invalid_sections"}, "report_path": str(json_path), "text_report_path": str(txt_path)}


def render_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    midi = payload["strict_midi"]
    errors = payload["sample_error_histogram"]
    lines = [
        "Fragmenter SNDDATA Field Probe v1",
        "=================================",
        f"Source: {summary['source']} ({summary['source_size']} bytes)",
        f"Resources: {summary['resources']} | Program banks: {summary['program_banks']}",
        f"Vagi full-table candidates: {summary['banks_with_full_vagi_table_candidate']}",
        "",
        "Strict SCEIMidi validation",
        "--------------------------",
        f"Sections: {midi['sections']} | invalid-high-bit sections: {midi['sections_with_invalid_high_bit_data']}",
        f"Events: trusted={midi['trusted_events']} raw={midi['raw_events']} discarded={midi['discarded_events']} trusted ProgramChange={midi['trusted_program_changes']}",
        "",
        "Sample decode failures",
        "----------------------",
        f"Metadata rows: {errors['metadata_rows']}",
    ]
    for message, count in list(errors["errors"].items())[:20]:
        lines.append(f"- {count}x {message}")
    lines.extend(["", "Representative banks", "--------------------"])
    for bank in payload["representative_banks"]:
        smpl = bank["sections"]["SCEISmpl"]
        sset = bank["sections"]["SCEISset"]
        smpl_density = (smpl.get("adpcm_density") or {}).get("likely_data_density")
        sset_density = (sset.get("adpcm_density") or {}).get("likely_data_density")
        best = bank["vagi_table_candidates"][0] if bank["vagi_table_candidates"] else None
        lines.append(
            f"- {bank['resource_hex']}: programs={bank['program_count']} slots={bank['slot_count']} sample_ids={bank['slot_sample_ids']} smpl={smpl['payload_size']} density={smpl_density} sset={sset['payload_size']} density={sset_density}"
        )
        if best:
            lines.append(f"    best Vagi table: count@+0x{best['count_offset']:X} count={best['count']} stride={best['stride']} coverage={best['coverage']}")
    lines.extend(["", "First strict MIDI boundaries", "----------------------------"])
    for row in midi["first_invalid_sections"][:20]:
        invalid = row.get("first_invalid_event") or {}
        lines.append(
            f"- resource=0x{row['resource_offset']:X} section=0x{row['section_offset']:X} event_offset={invalid.get('offset')} type={invalid.get('event_type')} values={invalid.get('invalid_values')}"
        )
    return "\n".join(lines) + "\n"

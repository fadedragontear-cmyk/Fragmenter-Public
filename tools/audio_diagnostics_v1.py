#!/usr/bin/env python3
"""Focused, read-only audio diagnostics for Fragmenter 1.0 projects.

This report is intentionally evidence-first.  It answers where the SNDDATA
pipeline loses known SCEI structures before we change parser or mixer logic.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import project_sound_v4 as project_sound
    import snddata_parser
    from project_workspace_v1 import FragmenterProjectV1, load_project
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import project_sound_v4 as project_sound
    import snddata_parser
    from project_workspace_v1 import FragmenterProjectV1, load_project

REPORT_JSON = "audio_diagnostics_v1.json"
REPORT_TXT = "audio_diagnostics_v1.txt"


def _u32le(data: bytes, off: int) -> int | None:
    if off < 0 or off + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, off)[0]


def _tag_rows(data: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signature, human_name in snddata_parser.SECTION_TAGS.items():
        start = 0
        while True:
            off = data.find(signature, start)
            if off < 0:
                break
            size = _u32le(data, off + 8)
            rows.append({
                "offset": off,
                "offset_hex": f"0x{off:X}",
                "signature": signature.decode("ascii", "replace"),
                "tag": human_name,
                "orientation": "reversed" if signature.startswith(b"IECS") else "forward",
                "size_field": size,
                "size_end": off + size if isinstance(size, int) else None,
                "size_plausible_file": bool(isinstance(size, int) and size >= 0x10 and off + size <= len(data)),
                "alignment_mod_8": off % 8,
                "alignment_mod_16": off % 16,
            })
            start = off + 1
    rows.sort(key=lambda row: (row["offset"], row["signature"]))
    return rows


def _parsed_section_rows(groups: list[snddata_parser.ResourceGroup]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        for section in group.sections:
            rows.append({
                "group_offset": group.offset,
                "group_offset_hex": f"0x{group.offset:X}",
                "offset": section.offset,
                "offset_hex": f"0x{section.offset:X}",
                "tag": snddata_parser.SECTION_TAGS.get(section.signature, "unknown"),
                "signature": section.signature.decode("ascii", "replace"),
                "valid": section.valid,
                "truncated": section.truncated,
                "block_size": section.block_size,
                "error": section.evidence.get("error"),
            })
    return rows


def _sample_inventory(project: FragmenterProjectV1) -> dict[str, Any]:
    root = project_sound.sound_decoded_root(project)
    metadata = sorted(root.rglob("sample_*.json")) if root.is_dir() else []
    wavs = sorted(root.rglob("*.wav")) if root.is_dir() else []
    good = 0
    bad_json = 0
    errors = 0
    missing_outputs = 0
    boundary_sources: Counter[str] = Counter()
    resource_ids: set[int] = set()
    sample_ids: set[int] = set()
    for path in metadata:
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            bad_json += 1
            continue
        if not isinstance(row, dict):
            bad_json += 1
            continue
        if row.get("errors"):
            errors += 1
            continue
        output = Path(str(row.get("output_path") or ""))
        if not output.is_file():
            missing_outputs += 1
            continue
        good += 1
        boundary_sources[str(row.get("boundary_source") or "unknown")] += 1
        if isinstance(row.get("resource_id"), int):
            resource_ids.add(row["resource_id"])
        if isinstance(row.get("sample_id"), int):
            sample_ids.add(row["sample_id"])
    return {
        "decoded_root": str(root),
        "metadata_rows": len(metadata),
        "good_metadata_rows": good,
        "metadata_json_errors": bad_json,
        "metadata_rows_with_errors": errors,
        "metadata_rows_missing_output": missing_outputs,
        "wav_files": len(wavs),
        "resource_ids_with_samples": len(resource_ids),
        "unique_sample_ids": len(sample_ids),
        "boundary_sources": dict(sorted(boundary_sources.items())),
    }


def _known_raw_streams(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    root = project_sound.sound_source_root(project)
    decoded = project_sound.sound_decoded_root(project)
    rows = []
    for relative in (Path("voice/bgm.bin"), Path("voice/food.bin")):
        source = root / relative
        wav_matches = sorted(decoded.rglob(relative.stem + ".wav")) if decoded.is_dir() else []
        rows.append({
            "relative_path": relative.as_posix(),
            "source": str(source),
            "source_exists": source.is_file(),
            "source_size": source.stat().st_size if source.is_file() else None,
            "preview_wavs": [str(path) for path in wav_matches],
            "preview_wav_count": len(wav_matches),
        })
    return rows


def build_audio_diagnostics(project: FragmenterProjectV1) -> dict[str, Any]:
    source = project_sound.canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(f"Canonical SNDDATA source is missing: {source}")
    data = source.read_bytes()
    tag_rows = _tag_rows(data)
    groups = snddata_parser.parse_blob(data, source.as_posix())
    parsed_rows = _parsed_section_rows(groups)

    raw_counts = Counter(row["tag"] for row in tag_rows)
    parsed_counts = Counter(row["tag"] for row in parsed_rows if row["valid"])
    comparison = []
    for tag in sorted(set(raw_counts) | set(parsed_counts)):
        raw = raw_counts[tag]
        parsed = parsed_counts[tag]
        comparison.append({
            "tag": tag,
            "raw_occurrences": raw,
            "parsed_valid_sections": parsed,
            "lost_occurrences": max(0, raw - parsed),
            "retention_ratio": round(parsed / raw, 6) if raw else None,
        })

    prog_sections = [section for group in groups for section in group.sections if snddata_parser.SECTION_TAGS.get(section.signature) == "SCEIProg"]
    midi_sections = [section for group in groups for section in group.sections if snddata_parser.SECTION_TAGS.get(section.signature) == "SCEIMidi"]
    programs = sum(len(((section.evidence.get("scei_prog") or {}).get("programs") or [])) for section in prog_sections)
    slots = sum(len(program.get("slots") or []) for section in prog_sections for program in ((section.evidence.get("scei_prog") or {}).get("programs") or []))
    midi_events = sum(len(((section.evidence.get("scei_midi") or {}).get("events") or [])) for section in midi_sections)

    likely_breaks = []
    for row in comparison:
        if row["raw_occurrences"] and row["parsed_valid_sections"] == 0 and row["tag"] in {"SCEIProg", "SCEIMidi", "SCEISmpl", "SCEISequ"}:
            likely_breaks.append(f"{row['tag']}: {row['raw_occurrences']} raw tag occurrence(s), zero valid parsed sections")
        elif row["lost_occurrences"] and row["tag"] in {"SCEIProg", "SCEIMidi", "SCEISmpl", "SCEISequ"}:
            likely_breaks.append(f"{row['tag']}: parser retains {row['parsed_valid_sections']} of {row['raw_occurrences']} raw occurrence(s)")
    if not likely_breaks and not programs:
        likely_breaks.append("SCEIProg sections are retained but no programs were decoded; inspect offset-table/body-offset semantics")
    if not likely_breaks and not midi_events:
        likely_breaks.append("SCEIMidi sections are retained but no events were decoded; inspect MIDI payload start and dynamic event framing")

    return {
        "version": 1,
        "source": str(source),
        "file_size": len(data),
        "summary": {
            "vers_candidates": len(snddata_parser.locate_vers_candidates(data)),
            "parsed_groups": len(groups),
            "valid_groups": sum(1 for group in groups if group.valid),
            "raw_known_tag_occurrences": len(tag_rows),
            "parsed_valid_sections": sum(1 for row in parsed_rows if row["valid"]),
            "program_sections": len(prog_sections),
            "programs": programs,
            "slots": slots,
            "midi_sections": len(midi_sections),
            "midi_events": midi_events,
        },
        "tag_comparison": comparison,
        "likely_parser_breaks": likely_breaks,
        "sample_inventory": _sample_inventory(project),
        "known_raw_streams": _known_raw_streams(project),
        "raw_tag_rows": tag_rows,
        "parsed_section_rows": parsed_rows,
    }


def render_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Fragmenter Audio Diagnostics v1",
        "================================",
        f"SNDDATA: {report['source']}",
        f"Size: {report['file_size']} bytes",
        "",
        "Parser funnel",
        "-------------",
        f"Vers candidates: {summary['vers_candidates']}",
        f"Parsed groups: {summary['parsed_groups']} ({summary['valid_groups']} valid)",
        f"Raw known tags: {summary['raw_known_tag_occurrences']}",
        f"Parsed valid sections: {summary['parsed_valid_sections']}",
        f"SCEIProg: {summary['program_sections']} sections / {summary['programs']} programs / {summary['slots']} slots",
        f"SCEIMidi: {summary['midi_sections']} sections / {summary['midi_events']} events",
        "",
        "Tag retention",
        "-------------",
    ]
    for row in report["tag_comparison"]:
        lines.append(f"{row['tag']}: raw={row['raw_occurrences']} parsed={row['parsed_valid_sections']} lost={row['lost_occurrences']}")
    lines.extend(["", "Likely parser breakpoints", "-------------------------"])
    lines.extend(f"- {item}" for item in report["likely_parser_breaks"] or ["No obvious tag-retention break; inspect decoded field semantics."])
    sample = report["sample_inventory"]
    lines.extend([
        "", "Decoded sample inventory", "------------------------",
        f"Metadata rows: {sample['metadata_rows']}",
        f"Good rows with WAV output: {sample['good_metadata_rows']}",
        f"WAV files under decoded root: {sample['wav_files']}",
        f"Resources with samples: {sample['resource_ids_with_samples']}",
        f"Unique sample IDs: {sample['unique_sample_ids']}",
        "", "Known raw streams", "-----------------",
    ])
    for row in report["known_raw_streams"]:
        lines.append(f"{row['relative_path']}: source={'yes' if row['source_exists'] else 'no'} size={row['source_size']} preview_wavs={row['preview_wav_count']}")
    return "\n".join(lines) + "\n"


def write_audio_diagnostics(project: FragmenterProjectV1) -> dict[str, Any]:
    report = build_audio_diagnostics(project)
    root = project.workspace_path("diagnostics") / "audio"
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / REPORT_JSON
    text_path = root / REPORT_TXT
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(render_text(report), encoding="utf-8")
    return {**report["summary"], "json_path": str(json_path), "text_path": str(text_path), "likely_parser_breaks": report["likely_parser_breaks"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write focused Fragmenter SNDDATA/audio diagnostics")
    parser.add_argument("project", help="Project directory or project.json")
    args = parser.parse_args(argv)
    result = write_audio_diagnostics(load_project(args.project))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

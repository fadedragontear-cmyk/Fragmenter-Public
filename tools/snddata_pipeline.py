#!/usr/bin/env python3
"""Run the complete SNDDATA music/audio evidence pipeline.

This command is intentionally report-oriented.  It parses SNDDATA resource
containers, writes the container map, extracts/decodes sample payloads, keeps
SCEIMidi parser evidence from the container parser, builds the conservative
music graph, and writes a compact pipeline summary.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import scei_midi
    import snddata_music_graph
    import snddata_parser
except ImportError:  # pragma: no cover - script execution from repo root
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import scei_midi
    import snddata_music_graph
    import snddata_parser


def _field_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _sections(groups: Iterable[snddata_parser.ResourceGroup], tag: str | None = None) -> list[snddata_parser.Section]:
    rows: list[snddata_parser.Section] = []
    for group in groups:
        for section in group.sections:
            if tag is None or snddata_parser.SECTION_TAGS.get(section.signature) == tag:
                rows.append(section)
    return rows


def _count_programs_and_slots(groups: Iterable[snddata_parser.ResourceGroup]) -> tuple[int, int]:
    program_count = 0
    slot_count = 0
    for section in _sections(groups, "SCEIProg"):
        parsed = section.evidence.get("scei_prog")
        if not isinstance(parsed, dict):
            continue
        programs = parsed.get("programs") or []
        if not isinstance(programs, list):
            continue
        program_count += len(programs)
        for program in programs:
            if isinstance(program, dict) and isinstance(program.get("slots"), list):
                slot_count += len(program["slots"])
    return program_count, slot_count


def _sample_rows_from_sections(groups: Iterable[snddata_parser.ResourceGroup]) -> int:
    total = 0
    for section in _sections(groups, "SCEISmpl"):
        evidence = section.evidence or {}
        samples = evidence.get("samples") or evidence.get("scei_smpl", {}).get("samples")
        if isinstance(samples, list):
            total += len(samples)
    return total


def _midi_stats(groups: Iterable[snddata_parser.ResourceGroup]) -> dict[str, int]:
    stats = {
        "midi_sections": 0,
        "midi_sections_confirmed": 0,
        "midi_sections_partial": 0,
        "midi_event_count": 0,
        "note_on_count": 0,
        "note_off_count": 0,
    }
    for section in _sections(groups, "SCEIMidi"):
        stats["midi_sections"] += 1
        parsed = section.evidence.get("scei_midi")
        if not isinstance(parsed, dict):
            stats["midi_sections_partial"] += 1
            continue
        status = parsed.get("parser_status")
        if status == scei_midi.STAT_CONFIRMED:
            stats["midi_sections_confirmed"] += 1
        else:
            stats["midi_sections_partial"] += 1
        events = parsed.get("events") or []
        if not isinstance(events, list):
            continue
        stats["midi_event_count"] += len(events)
        for event in events:
            if not isinstance(event, dict):
                continue
            event_type = event.get("event_type")
            velocity = _field_value((event.get("values") or {}).get("velocity")) if isinstance(event.get("values"), dict) else None
            if event_type == "note_on" and velocity != 0:
                stats["note_on_count"] += 1
            elif event_type == "note_off" or (event_type == "note_on" and velocity == 0):
                stats["note_off_count"] += 1
    return stats


def build_summary(source: Path, file_size: int, groups: list[snddata_parser.ResourceGroup], sample_rows: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, Any]:
    program_count, slot_count = _count_programs_and_slots(groups)
    midi = _midi_stats(groups)
    failed_samples = sum(1 for row in sample_rows if row.get("errors") or str(row.get("decode_status", "")).startswith("failed"))
    decoded_sample_wavs = sum(1 for row in sample_rows if not row.get("errors") and Path(str(row.get("output_path", ""))).is_file())
    summary: dict[str, Any] = {
        "source": str(source),
        "file_size": file_size,
        "resource_count": len(groups),
        "sample_program_resources": sum(1 for group in groups if group.classification == "sample_program_resource"),
        "sequence_resources": sum(1 for group in groups if group.classification == "sequence_resource"),
        "prog_sections": len(_sections(groups, "SCEIProg")),
        "program_count": program_count,
        "slot_count": slot_count,
        "smpl_sections": len(_sections(groups, "SCEISmpl")),
        "sample_rows": len(sample_rows) or _sample_rows_from_sections(groups),
        "decoded_sample_wavs": decoded_sample_wavs,
        "failed_samples": failed_samples,
        **midi,
        "graph_nodes": len(graph.get("nodes", [])),
        "confirmed_edges": len(graph.get("confirmed_edges", [])),
        "candidate_edges": len(graph.get("candidate_edges", [])),
        "unknown_mappings": len(graph.get("unknown_mappings", [])),
    }
    structure_count_keys = (
        "prog_sections",
        "smpl_sections",
        "midi_sections",
        "program_count",
        "sample_rows",
        "decoded_sample_wavs",
        "midi_event_count",
    )
    music_structure_resolved = any(int(summary.get(key, 0) or 0) > 0 for key in structure_count_keys)
    summary["music_structure_resolved"] = music_structure_resolved

    partial_reasons = []
    if summary["failed_samples"]:
        partial_reasons.append("failed_samples")
    if summary["midi_sections_partial"]:
        partial_reasons.append("midi_sections_partial")
    if summary["candidate_edges"] or summary["unknown_mappings"]:
        partial_reasons.append("partial_graph_mappings")
    if summary["resource_count"] > 0 and not music_structure_resolved:
        partial_reasons.append("No SCEIProg, SCEISmpl, or SCEIMidi sections were structurally parsed.")

    if summary["resource_count"] > 0 and not music_structure_resolved:
        summary["status"] = "Research / Structure unresolved"
    else:
        summary["status"] = "Partial" if partial_reasons else "Complete"
    summary["partial_reasons"] = partial_reasons
    return summary


def write_summary(summary: dict[str, Any], json_path: Path, txt_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = ["SNDDATA pipeline summary", "========================", ""]
    for key, value in summary.items():
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value) if value else "none"
        lines.append(f"{key}: {value}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pipeline(data_path: Path, workspace: Path) -> dict[str, Any]:
    data = data_path.read_bytes()
    groups = snddata_parser.parse_blob(data, data_path.as_posix())

    reports = workspace / "reports"
    snddata_parser.write_reports(
        groups,
        reports / "snddata_container_map.json",
        reports / "snddata_container_map.txt",
    )
    sample_rows = snddata_parser.extract_samples(
        data,
        groups,
        workspace / "media_pipeline" / "decoded" / "audio" / "snddata" / "samples",
    )
    graph = snddata_music_graph.build_graph(groups)
    snddata_music_graph.write_reports(
        graph,
        reports / "snddata_music_graph.json",
        reports / "snddata_music_graph.txt",
    )
    summary = build_summary(data_path, len(data), groups, sample_rows, graph)
    write_summary(
        summary,
        reports / "snddata_pipeline_summary.json",
        reports / "snddata_pipeline_summary.txt",
    )
    return summary



def render_cli_summary(summary: dict[str, Any]) -> str:
    """Return the compact SNDDATA diagnostic summary required by CLI runs."""
    graph_mappings = int(summary.get("confirmed_edges", 0) or 0) + int(summary.get("candidate_edges", 0) or 0) + int(summary.get("unknown_mappings", 0) or 0)
    lines = [
        "SNDDATA summary",
        f"resources: {summary.get('resource_count', 0)}",
        f"programs: {summary.get('program_count', 0)}",
        f"slots: {summary.get('slot_count', 0)}",
        f"samples: {summary.get('sample_rows', 0)}",
        f"decoded sample WAVs: {summary.get('decoded_sample_wavs', 0)}",
        f"MIDI sections: {summary.get('midi_sections', 0)}",
        f"events: {summary.get('midi_event_count', 0)}",
        f"graph mappings: {graph_mappings}",
    ]
    return "\n".join(lines)


def run_default_snddata_diagnostic(root: Path | None = None) -> str:
    base = root if root is not None else Path.cwd()
    fixture = base / "workspace" / "media_pipeline" / "extracted" / "top_level" / "data" / "snddata.bin"
    if not fixture.is_file():
        return f"SNDDATA real-file diagnostics\nStatus: skipped (fixture path missing: {fixture})"
    summary = run_pipeline(fixture, base / "workspace")
    return f"SNDDATA real-file diagnostics\nStatus: ran ({fixture})\n" + render_cli_summary(summary)

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data_path", type=Path, help="SNDDATA/container file to scan")
    ap.add_argument("--workspace", type=Path, default=Path("workspace"), help="workspace root for reports and decoded sample output")
    ap.add_argument("--real-fixture-diagnostics", action="store_true", help="Print default extracted snddata.bin diagnostics or an explicit skipped message")
    ns = ap.parse_args(argv)
    if not ns.data_path.is_file():
        print(f"SNDDATA input does not exist: {ns.data_path}", file=sys.stderr)
        return 2
    try:
        summary = run_pipeline(ns.data_path, ns.workspace)
    except Exception as exc:  # process/parser failure should be nonzero
        print(f"SNDDATA pipeline failed: {exc}", file=sys.stderr)
        return 1
    print(f"SNDDATA pipeline {summary['status']}: wrote reports under {ns.workspace / 'reports'}")
    print(render_cli_summary(summary))
    if ns.real_fixture_diagnostics:
        print(run_default_snddata_diagnostic(Path.cwd()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

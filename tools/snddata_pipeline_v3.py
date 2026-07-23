#!/usr/bin/env python3
"""Canonical project-sound SNDDATA analysis for Fragmenter public release."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import snddata_music_graph
import snddata_parser
from project_sound_v1 import canonical_snddata_path, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_music_system_v3 import ensure_canonical_samples, load_music_runtime


def analyze_project_snddata(project: FragmenterProjectV1) -> dict[str, Any]:
    source = canonical_snddata_path(project)
    if not source.is_file():
        raise FileNotFoundError(f"Canonical SNDDATA source is missing: {source}")
    data = source.read_bytes()
    groups = snddata_parser.parse_blob(data, source.as_posix())
    root = sound_reports_root(project)
    snddata_parser.write_reports(groups, root / "snddata_container_map.json", root / "snddata_container_map.txt")
    sample_rows = ensure_canonical_samples(project, data, groups)
    graph = snddata_music_graph.build_graph(groups)
    snddata_music_graph.write_reports(graph, root / "snddata_music_graph_legacy.json", root / "snddata_music_graph_legacy.txt")
    runtime = load_music_runtime(project)

    sequence_rows = []
    for sequence in runtime.sequences:
        best = sequence.get("best_candidate")
        sequence_rows.append(
            {
                "sequence_id": sequence["sequence_id"],
                "resource_offset": sequence["resource_offset"],
                "note_on_count": sequence["note_on_count"],
                "program_change_count": sequence["program_change_count"],
                "program_indexes": sequence["program_indexes"],
                "routing_status": sequence["routing_status"],
                "candidate_count": len(sequence["candidates"]),
                "best_candidate": best,
            }
        )
    summary = {
        "version": 3,
        "source": str(source),
        "file_size": len(data),
        "resources": len(groups),
        "program_resources": len(runtime.program_groups),
        "sequences": len(sequence_rows),
        "program_changes": sum(int(row["program_change_count"]) for row in sequence_rows),
        "note_on_events": sum(int(row["note_on_count"]) for row in sequence_rows),
        "decoded_sample_rows": sum(1 for row in sample_rows if not row.get("errors") and Path(str(row.get("output_path") or "")).is_file()),
        "sequences_with_program_changes": sum(1 for row in sequence_rows if row["program_change_count"]),
        "best_candidates_renderable": sum(1 for row in sequence_rows if isinstance(row.get("best_candidate"), dict) and row["best_candidate"].get("status") == "renderable"),
        "sample_remap_fallback": False,
        "program_routing": "SCEIMidi Program Change state",
        "program_resource_pairing": "evidence-ranked candidate until SCEISequ cross-resource field is proven",
    }
    report = {"summary": summary, "sequences": sequence_rows}
    path = root / "snddata_music_system_v3.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path = root / "snddata_pipeline_summary_v3.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**summary, "report_path": str(path), "summary_path": str(summary_path)}

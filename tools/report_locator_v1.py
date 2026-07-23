#!/usr/bin/env python3
"""Canonical report locator for the organized Fragmenter workspace."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_workspace_v1 import FragmenterProjectV1


@dataclass(frozen=True)
class ReportSpec:
    key: str
    relative_path: str
    label: str
    description: str


CANONICAL_REPORTS = (
    ReportSpec("project_status", "run_all/project_status.json", "Project Status", "Active source readiness and project identity."),
    ReportSpec("pipeline_last", "run_all/pipeline_last.json", "Latest Pipeline Run", "Complete report for the last full or individual pipeline execution."),
    ReportSpec("scan_summary", "run_all/scan_summary.txt", "Scan Summary", "Readable summary of the latest pipeline execution."),
    ReportSpec("workspace_layout", "run_all/workspace_layout.json", "Workspace Migration", "Non-destructive legacy-folder migration report."),
    ReportSpec("report_layout", "run_all/report_layout.json", "Report Migration", "Non-destructive report-group migration report."),
    ReportSpec("asset_library", "asset_library.json", "Asset Library", "Canonical CCSF model, texture, palette and animation catalog."),
    ReportSpec("texture_catalog", "visual/texture_catalog.json", "Texture Catalog", "Visual assets containing TEX or CLT records."),
    ReportSpec("animation_catalog", "visual/animation_catalog.json", "Animation Catalog", "Visual assets containing animation records."),
    ReportSpec("visual_classifications", "visual/classifications/visual_classifications_latest.json", "Visual Classifications", "Latest portable classification, notes, flags and camera ledger."),
    ReportSpec("sound_library", "audio/sound_library.json", "Sound Library", "Canonical source and decoded-audio catalog."),
    ReportSpec("sound_decode", "audio/sound_decode_report.json", "Direct Audio Decode", "BGM, FOOD, EFF and other direct-source decode results."),
    ReportSpec("snddata_samples", "audio/snddata_sample_library.json", "SNDDATA Samples", "Authoritative SCEIVagi-indexed sample-bank report."),
    ReportSpec("snddata_mixer", "audio/snddata_music_system_v5.json", "SNDDATA Mixer", "Sequences, routing hypotheses, Program resources and candidate evidence."),
    ReportSpec("server_index", "server/server_index.json", "Area Server Index", "Area Server file and readable-content catalog."),
    ReportSpec("server_saves", "server/server_save_index.json", "Server Save Index", "Read-only server-save metadata."),
    ReportSpec("memory_card", "server/memory_card_identity.json", "Memory Card Identity", "Whole-file memory-card identity used by backup and restore."),
    ReportSpec("diagnostics_summary", "diagnostics/summary.txt", "Diagnostics Summary", "Readable index of retained research diagnostics."),
)


def _file_row(path: Path, *, key: str, label: str, description: str) -> dict[str, Any]:
    exists = path.is_file()
    stat = path.stat() if exists else None
    return {
        "key": key,
        "label": label,
        "description": description,
        "path": str(path),
        "exists": exists,
        "size": stat.st_size if stat else None,
        "mtime_ns": stat.st_mtime_ns if stat else None,
    }


def canonical_report_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    reports = project.workspace_path("reports")
    return [
        _file_row(reports / Path(spec.relative_path), key=spec.key, label=spec.label, description=spec.description)
        for spec in CANONICAL_REPORTS
    ]


def diagnostic_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    diagnostics = project.workspace_path("diagnostics")
    if not diagnostics.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted((p for p in diagnostics.rglob("*") if p.is_file() and p.name != "summary.txt"), key=lambda p: str(p).lower()):
        stat = path.stat()
        rows.append(
            {
                "relative_path": path.relative_to(diagnostics).as_posix(),
                "path": str(path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return rows


def write_diagnostics_summary(project: FragmenterProjectV1) -> Path:
    rows = diagnostic_rows(project)
    target = project.workspace_path("diagnostics") / "summary.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Fragmenter Diagnostics Summary", f"Files: {len(rows)}", ""]
    if rows:
        lines.extend(f"{row['relative_path']}  ({row['size']:,} bytes)" for row in rows)
    else:
        lines.append("No retained diagnostic files.")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def report_locator_view_model(project: FragmenterProjectV1) -> dict[str, Any]:
    normal = canonical_report_rows(project)
    diagnostics = diagnostic_rows(project)
    return {
        "normal_reports": normal,
        "diagnostics": diagnostics,
        "normal_existing": sum(1 for row in normal if row["exists"]),
        "diagnostic_count": len(diagnostics),
        "report_groups": {
            "run_all": str(project.workspace_path("run_reports")),
            "visual": str(project.workspace_path("visual_reports")),
            "audio": str(project.workspace_path("audio_reports")),
            "server": str(project.workspace_path("server_reports")),
            "diagnostics": str(project.workspace_path("diagnostics")),
        },
        "cache_paths": {
            "iso": str(project.workspace_path("cache_iso")),
            "ccsf_structure": str(project.workspace_path("cache_ccsf_structure")),
            "snddata": str(project.workspace_path("cache_snddata")),
            "mappings": str(project.workspace_path("cache_mappings")),
        },
    }

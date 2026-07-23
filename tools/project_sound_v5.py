#!/usr/bin/env python3
"""Project sound v5: authoritative SNDDATA sample-library extraction."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import project_sound_v4 as v4
import snddata_music_system_v3 as music_v3
import snddata_parser
from iso9660 import normalize_path
from project_workspace_v1 import FragmenterProjectV1
from snddata_sample_library_v3 import extract_project_snddata_samples

EXTRA_EXACT_PATHS_V4 = v4.EXTRA_EXACT_PATHS_V4
RAW_PCM_EXACT_PATHS_V4 = v4.RAW_PCM_EXACT_PATHS_V4
RAW_PCM_SAMPLE_RATE = v4.RAW_PCM_SAMPLE_RATE
RAW_PCM_CHANNELS = v4.RAW_PCM_CHANNELS
RAW_PCM_SAMPLE_WIDTH = v4.RAW_PCM_SAMPLE_WIDTH
RAW_PCM_ENCODING = v4.RAW_PCM_ENCODING
RAW_PCM_REPORT = v4.RAW_PCM_REPORT

sound_root = v4.sound_root
sound_source_root = v4.sound_source_root
sound_decoded_root = v4.sound_decoded_root
sound_reports_root = v4.sound_reports_root
sound_work_root = v4.sound_work_root
canonical_snddata_path = v4.canonical_snddata_path
import_raw_pcm_source = v4.import_raw_pcm_source
discover_sound_sources = v4.discover_sound_sources


def _correct_resource_classification(sections, resource_type: int | None) -> str:
    tags = [snddata_parser.SECTION_TAGS.get(section.signature) for section in sections if section.valid]
    if resource_type == 2 and {"SCEIHead", "SCEIVagi"}.issubset(tags):
        return "sample_program_resource"
    if resource_type == 1 and ("SCEISequ" in tags or "SCEIMidi" in tags):
        return "sequence_resource"
    return snddata_parser.RESOURCE_TYPE_NAMES.get(resource_type, "unknown") or "unknown"


def _ensure_authoritative_samples(project: FragmenterProjectV1, _data: bytes, _groups) -> list[dict[str, Any]]:
    return list(extract_project_snddata_samples(project, clean=True).get("samples") or [])


snddata_parser.RESOURCE_TYPE_NAMES.clear()
snddata_parser.RESOURCE_TYPE_NAMES.update({1: "sequence", 2: "sample_program"})
snddata_parser._classify = _correct_resource_classification
music_v3.ensure_canonical_samples = _ensure_authoritative_samples
extract_project_sound_sources = v4.extract_project_sound_sources
import_project_raw_pcm_candidates = v4.import_project_raw_pcm_candidates


def decode_project_sound_sources(project: FragmenterProjectV1, *, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    report = v4.decode_project_sound_sources(project, callback=callback)
    samples = extract_project_snddata_samples(project, callback=callback)
    report["snddata_sample_library"] = samples
    report.setdefault("summary", {})["snddata_sample_wavs"] = int(samples["summary"]["decoded_wavs"])
    report.setdefault("summary", {})["snddata_sample_failures"] = int(samples["summary"]["failed_samples"])
    report.setdefault("actions", []).append(
        {
            "action": "extract_snddata_secondary_adpcm_library",
            "status": "complete" if not samples["summary"]["bank_errors"] else "partial",
            "summary": samples["summary"],
            "report_path": samples["report_path"],
            "csv_path": samples["csv_path"],
            "format_authority": samples["format_authority"],
        }
    )
    report_path = Path(str(report.get("report_path") or sound_reports_root(project) / v4.sound_v1.DECODE_REPORT_NAME))
    v4.sound_v1._atomic_json(report_path, {key: value for key, value in report.items() if key != "report_path"})
    report["report_path"] = str(report_path)
    return report


def _recategorize_snddata(row: dict[str, Any]) -> None:
    relative = normalize_path(str(row.get("relative_path") or ""))
    if relative.startswith("snddata/samples/") and str(row.get("path") or "").lower().endswith(".wav"):
        row["category"] = "SNDDATA Samples"
        row["status"] = "playable extracted PS-ADPCM sample"
        row["primary_action"] = "Play"
        row["provenance"] = "HEAD secondary body → SCEIVagi offset/rate"


def build_project_sound_library(project: FragmenterProjectV1, *, query: str = "", category: str = "All") -> dict[str, Any]:
    payload = v4.build_project_sound_library(project, query=query, category="All")
    all_items = [row for row in payload.get("items") or [] if isinstance(row, dict)]
    for row in all_items:
        _recategorize_snddata(row)
    categories = sorted({str(row.get("category") or "Other audio") for row in all_items})
    items = all_items if category == "All" else [row for row in all_items if row.get("category") == category]
    payload["version"] = 5
    payload["items"] = items
    payload["categories"] = categories
    summary = payload.setdefault("summary", {})
    summary.update(
        {
            "items": len(items),
            "source_files": sum(1 for row in items if row.get("kind") == "source"),
            "decoded_files": sum(1 for row in items if row.get("kind") == "decoded"),
            "playable_wavs": sum(1 for row in items if row.get("playable")),
            "snddata_sample_wavs": sum(1 for row in items if row.get("playable") and row.get("category") == "SNDDATA Samples"),
        }
    )
    v4.sound_v1._atomic_json(sound_reports_root(project) / v4.sound_v1.LIBRARY_NAME, payload)
    return payload


def analyze_or_extract_sound_item(project: FragmenterProjectV1, source_path: str | Path) -> dict[str, Any]:
    source_root_value = sound_source_root(project).resolve()
    source = Path(source_path).expanduser().resolve()
    try:
        relative = source.relative_to(source_root_value)
    except ValueError as exc:
        raise PermissionError(f"Sound action is limited to the active project source root: {source_root_value}") from exc
    if not source.is_file():
        raise FileNotFoundError(source)
    if normalize_path(relative.as_posix()) == "data/snddata.bin":
        samples = extract_project_snddata_samples(project)
        library = build_project_sound_library(project)
        return {
            "source": str(source),
            "relative_path": relative.as_posix(),
            "action": "extract_snddata_sample_library",
            "summary": samples["summary"],
            "format_authority": samples["format_authority"],
            "report_path": samples["report_path"],
            "csv_path": samples["csv_path"],
            "library_summary": library["summary"],
        }
    return v4.analyze_or_extract_sound_item(project, source)

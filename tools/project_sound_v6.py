#!/usr/bin/env python3
"""Project sound v6: cleaner public library names and hidden raw-PCM research rows."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import project_sound_v4 as sound_v4
import project_sound_v5 as v5
from iso9660 import normalize_path
from project_workspace_v1 import FragmenterProjectV1
from snddata_sample_library_v3 import extract_project_snddata_samples

EXTRA_EXACT_PATHS_V4 = v5.EXTRA_EXACT_PATHS_V4
RAW_PCM_EXACT_PATHS_V4 = v5.RAW_PCM_EXACT_PATHS_V4
RAW_PCM_SAMPLE_RATE = v5.RAW_PCM_SAMPLE_RATE
RAW_PCM_CHANNELS = v5.RAW_PCM_CHANNELS
RAW_PCM_SAMPLE_WIDTH = v5.RAW_PCM_SAMPLE_WIDTH
RAW_PCM_ENCODING = v5.RAW_PCM_ENCODING
RAW_PCM_REPORT = v5.RAW_PCM_REPORT

sound_root = v5.sound_root
sound_source_root = v5.sound_source_root
sound_decoded_root = v5.sound_decoded_root
sound_reports_root = v5.sound_reports_root
sound_work_root = v5.sound_work_root
canonical_snddata_path = v5.canonical_snddata_path
import_raw_pcm_source = v5.import_raw_pcm_source
discover_sound_sources = v5.discover_sound_sources
extract_project_sound_sources = v5.extract_project_sound_sources
import_project_raw_pcm_candidates = v5.import_project_raw_pcm_candidates

_SAMPLE_NAME = re.compile(
    r"(?:bank|resource)_(?P<bank>[0-9A-Fa-f]{1,8})(?:_offset_[0-9A-Fa-f]{1,8})?.*?sample_(?P<sample>\d+)_(?P<rate>\d+)hz",
    re.IGNORECASE,
)


def decode_project_sound_sources(project: FragmenterProjectV1, *, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    report = sound_v4.decode_project_sound_sources(project, callback=callback)
    samples = extract_project_snddata_samples(project, clean=True, callback=callback)
    report["snddata_sample_library"] = samples
    report.setdefault("summary", {})["snddata_sample_wavs"] = int(samples["summary"]["decoded_wavs"])
    report.setdefault("summary", {})["snddata_sample_failures"] = int(samples["summary"]["failed_samples"])
    return report


def _is_raw_pcm_preview(row: dict[str, Any]) -> bool:
    if row.get("raw_pcm_assumption"):
        return True
    action = str(row.get("primary_action") or "").lower()
    if action == "import raw pcm":
        return True
    combined = " ".join(
        str(row.get(key) or "")
        for key in ("status", "provenance", "relative_path", "path", "name")
    ).lower()
    return "raw pcm" in combined or "raw_pcm" in combined


def _usage_hint(duration: float) -> str:
    if duration <= 0:
        return "unclassified sample"
    if duration < 0.22:
        return "very short one-shot; instrument or effect candidate"
    if duration < 1.5:
        return "one-shot or musical-sting candidate"
    return "sustained note, phrase, ambience, or effect candidate"


def _friendly_snddata_row(row: dict[str, Any]) -> None:
    relative = normalize_path(str(row.get("relative_path") or ""))
    if not relative.startswith("snddata/samples/") or not str(row.get("path") or "").lower().endswith(".wav"):
        return
    match = _SAMPLE_NAME.search(relative)
    if match:
        bank_text = match.group("bank")
        sample_index = int(match.group("sample"))
        sample_rate = int(match.group("rate"))
        if any(character in "abcdefABCDEF" for character in bank_text) or len(bank_text) == 8:
            bank_label = f"0x{int(bank_text, 16):08X}"
        else:
            bank_label = f"{int(bank_text):04d}"
        display = f"SNDDATA bank {bank_label} · sample {sample_index:04d} · {sample_rate:,} Hz"
        row["name"] = display
        row["display_name"] = display
        row["sample_bank"] = bank_label
        row["sample_index"] = sample_index
        row["sample_rate"] = sample_rate
    wav = row.get("wav") if isinstance(row.get("wav"), dict) else {}
    duration = float(wav.get("duration") or row.get("duration_estimate") or 0.0)
    row["sequence_role"] = "unclassified"
    row["usage_hint"] = _usage_hint(duration)
    row["status"] = f"playable extracted PS-ADPCM sample; {row['usage_hint']}"


def build_project_sound_library(
    project: FragmenterProjectV1,
    *,
    query: str = "",
    category: str = "All",
    include_raw_pcm: bool = False,
) -> dict[str, Any]:
    payload = v5.build_project_sound_library(project, query=query, category="All")
    original = [row for row in payload.get("items") or [] if isinstance(row, dict)]
    for row in original:
        _friendly_snddata_row(row)
    hidden_raw_pcm = sum(1 for row in original if _is_raw_pcm_preview(row))
    visible = original if include_raw_pcm else [row for row in original if not _is_raw_pcm_preview(row)]
    categories = sorted({str(row.get("category") or "Other audio") for row in visible})
    items = visible if category == "All" else [row for row in visible if row.get("category") == category]
    payload["version"] = 6
    payload["items"] = items
    payload["categories"] = categories
    summary = payload.setdefault("summary", {})
    summary.update(
        {
            "items": len(items),
            "source_files": sum(1 for row in items if row.get("kind") == "source"),
            "decoded_files": sum(1 for row in items if row.get("kind") == "decoded"),
            "playable_wavs": sum(1 for row in items if row.get("playable")),
            "snddata_sample_wavs": sum(
                1 for row in items if row.get("playable") and row.get("category") == "SNDDATA Samples"
            ),
            "hidden_raw_pcm_rows": hidden_raw_pcm if not include_raw_pcm else 0,
        }
    )
    v5.v4.sound_v1._atomic_json(sound_reports_root(project) / v5.v4.sound_v1.LIBRARY_NAME, payload)
    return payload


def analyze_or_extract_sound_item(project: FragmenterProjectV1, source_path: str | Path) -> dict[str, Any]:
    source = Path(source_path).expanduser().resolve()
    source_root_value = sound_source_root(project).resolve()
    try:
        relative = source.relative_to(source_root_value)
    except ValueError:
        return v5.analyze_or_extract_sound_item(project, source_path)
    if normalize_path(relative.as_posix()) == "data/snddata.bin":
        samples = extract_project_snddata_samples(project, clean=True)
        library = build_project_sound_library(project)
        return {
            "source": str(source),
            "relative_path": relative.as_posix(),
            "action": "extract_snddata_sample_library_v3",
            "summary": samples["summary"],
            "naming": samples.get("naming"),
            "report_path": samples["report_path"],
            "csv_path": samples["csv_path"],
            "library_summary": library["summary"],
        }
    return v5.analyze_or_extract_sound_item(project, source_path)

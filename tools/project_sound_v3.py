#!/usr/bin/env python3
"""Project sound v3: explicit raw-PCM preview win for BGM/FOOD binary sources."""
from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any, Callable

import project_sound_v2 as v2
from iso9660 import normalize_path
from project_workspace_v1 import FragmenterProjectV1

RAW_PCM_SAMPLE_RATE = 44_100
RAW_PCM_CHANNELS = 1
RAW_PCM_SAMPLE_WIDTH = 2
RAW_PCM_ENCODING = "signed 16-bit PCM little-endian"
RAW_PCM_REPORT = "raw_pcm_imports_v1.json"

sound_root = v2.sound_root
sound_source_root = v2.sound_source_root
sound_decoded_root = v2.sound_decoded_root
sound_reports_root = v2.sound_reports_root
sound_work_root = v2.sound_work_root
canonical_snddata_path = v2.canonical_snddata_path
extract_project_sound_sources = v2.extract_project_sound_sources


def _raw_pcm_candidate(relative: str | Path, source: Path) -> bool:
    normalized = normalize_path(Path(relative).as_posix())
    if normalized == "data/snddata.bin" or source.suffix.lower() != ".bin":
        return False
    return v2._purpose(normalized) in {"BGM / Music", "FOOD stream"}


def _raw_pcm_output(project: FragmenterProjectV1, relative: Path) -> Path:
    return sound_decoded_root(project) / "raw_pcm" / relative.with_suffix(".wav")


def import_raw_pcm_source(
    project: FragmenterProjectV1,
    source: str | Path,
    relative: str | Path,
    *,
    sample_rate: int = RAW_PCM_SAMPLE_RATE,
    channels: int = RAW_PCM_CHANNELS,
    sample_width: int = RAW_PCM_SAMPLE_WIDTH,
) -> dict[str, Any]:
    source_path = Path(source)
    relative_path = Path(relative)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if sample_rate <= 0 or channels <= 0 or sample_width <= 0:
        raise ValueError("raw PCM settings must be positive")
    frame_size = channels * sample_width
    raw = source_path.read_bytes()
    usable = len(raw) - (len(raw) % frame_size)
    if usable <= 0:
        raise ValueError(f"raw PCM source has no complete {frame_size}-byte frame")
    output = _raw_pcm_output(project, relative_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(raw[:usable])
    frames = usable // frame_size
    return {
        "source": str(source_path),
        "relative_path": relative_path.as_posix(),
        "output_path": str(output),
        "status": "imported_raw_pcm_assumption",
        "verified_container_format": False,
        "assumption": {
            "encoding": RAW_PCM_ENCODING,
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_width": sample_width,
            "byte_offset": 0,
        },
        "source_bytes": len(raw),
        "pcm_bytes": usable,
        "discarded_tail_bytes": len(raw) - usable,
        "frames": frames,
        "duration": frames / float(sample_rate),
    }


def import_project_raw_pcm_candidates(
    project: FragmenterProjectV1,
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    root = sound_source_root(project)
    candidates: list[tuple[Path, Path]] = []
    for source in sorted((path for path in root.rglob("*.bin") if path.is_file()), key=lambda path: path.relative_to(root).as_posix()):
        relative = source.relative_to(root)
        if _raw_pcm_candidate(relative, source):
            candidates.append((source, relative))

    rows: list[dict[str, Any]] = []
    total = len(candidates)
    for index, (source, relative) in enumerate(candidates, 1):
        try:
            row = import_raw_pcm_source(project, source, relative)
        except Exception as exc:
            row = {
                "source": str(source),
                "relative_path": relative.as_posix(),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)
        if callback is not None:
            callback(
                {
                    "kind": "raw_pcm_import_progress",
                    "current": index,
                    "total": total,
                    "relative_path": relative.as_posix(),
                    "status": row.get("status"),
                }
            )

    report = {
        "version": 1,
        "assumption": {
            "encoding": RAW_PCM_ENCODING,
            "sample_rate": RAW_PCM_SAMPLE_RATE,
            "channels": RAW_PCM_CHANNELS,
            "sample_width": RAW_PCM_SAMPLE_WIDTH,
            "byte_offset": 0,
            "evidence": "User reproduced BGM/FOOD playback by importing the raw binaries with default raw-audio settings in Audacity.",
        },
        "items": rows,
        "summary": {
            "candidates": total,
            "imported": sum(1 for row in rows if row.get("status") == "imported_raw_pcm_assumption"),
            "errors": sum(1 for row in rows if row.get("status") == "error"),
        },
    }
    path = sound_reports_root(project) / RAW_PCM_REPORT
    v2.v1._atomic_json(path, report)
    report["report_path"] = str(path)
    return report


def decode_project_sound_sources(
    project: FragmenterProjectV1,
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    report = v2.decode_project_sound_sources(project, callback=callback)
    raw_pcm = import_project_raw_pcm_candidates(project, callback=callback)
    report["raw_pcm"] = raw_pcm
    report.setdefault("summary", {})["raw_pcm_previews"] = int(raw_pcm["summary"]["imported"])
    report.setdefault("actions", []).append(
        {
            "action": "import_bgm_food_raw_pcm",
            "status": "complete" if not raw_pcm["summary"]["errors"] else "partial",
            "summary": raw_pcm["summary"],
            "report_path": raw_pcm["report_path"],
            "verified_container_format": False,
        }
    )
    report_path = Path(str(report.get("report_path") or sound_reports_root(project) / v2.v1.DECODE_REPORT_NAME))
    v2.v1._atomic_json(report_path, {key: value for key, value in report.items() if key != "report_path"})
    report["report_path"] = str(report_path)
    return report


def build_project_sound_library(project: FragmenterProjectV1, *, query: str = "", category: str = "All") -> dict[str, Any]:
    payload = v2.build_project_sound_library(project, query=query, category=category)
    for row in payload.get("items") or []:
        if not isinstance(row, dict) or row.get("kind") != "source":
            continue
        path = Path(str(row.get("path") or ""))
        relative = Path(str(row.get("relative_path") or ""))
        if _raw_pcm_candidate(relative, path):
            row["supported_container"] = True
            row["primary_action"] = "Import Raw PCM"
            row["status"] = "raw PCM candidate; Audacity-default-style preview available"
            row["raw_pcm_assumption"] = {
                "encoding": RAW_PCM_ENCODING,
                "sample_rate": RAW_PCM_SAMPLE_RATE,
                "channels": RAW_PCM_CHANNELS,
                "byte_offset": 0,
            }
    payload.setdefault("summary", {})["raw_pcm_candidates"] = sum(
        1 for row in payload.get("items") or [] if isinstance(row, dict) and row.get("primary_action") == "Import Raw PCM"
    )
    v2.v1._atomic_json(sound_reports_root(project) / v2.v1.LIBRARY_NAME, payload)
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
    if _raw_pcm_candidate(relative, source):
        raw_pcm = import_raw_pcm_source(project, source, relative)
        container = v2.analyze_binary_container(project, source, relative)
        library = build_project_sound_library(project)
        return {
            "source": str(source),
            "relative_path": relative.as_posix(),
            "action": "import_raw_pcm_and_analyze_container",
            "raw_pcm": raw_pcm,
            "container_analysis": container,
            "library_summary": library["summary"],
        }
    return v2.analyze_or_extract_sound_item(project, source)

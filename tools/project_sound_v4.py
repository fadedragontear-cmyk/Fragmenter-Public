#!/usr/bin/env python3
"""Project sound v4: canonical voice/BGM and voice/FOOD raw PCM sources."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import project_sound_v1 as sound_v1
import project_sound_v2 as sound_v2
import project_sound_v3 as v3
from iso9660 import Iso9660, normalize_path
from project_preflight_v1 import require_ready_project
from project_workspace_v1 import FragmenterProjectV1

EXTRA_EXACT_PATHS_V4 = {
    *sound_v1.EXTRA_EXACT_PATHS,
    "voice/bgm.bin",
    "voice/food.bin",
}
RAW_PCM_EXACT_PATHS_V4 = {"voice/bgm.bin", "voice/food.bin"}

RAW_PCM_SAMPLE_RATE = v3.RAW_PCM_SAMPLE_RATE
RAW_PCM_CHANNELS = v3.RAW_PCM_CHANNELS
RAW_PCM_SAMPLE_WIDTH = v3.RAW_PCM_SAMPLE_WIDTH
RAW_PCM_ENCODING = v3.RAW_PCM_ENCODING
RAW_PCM_REPORT = v3.RAW_PCM_REPORT

sound_root = v3.sound_root
sound_source_root = v3.sound_source_root
sound_decoded_root = v3.sound_decoded_root
sound_reports_root = v3.sound_reports_root
sound_work_root = v3.sound_work_root
canonical_snddata_path = v3.canonical_snddata_path
import_raw_pcm_source = v3.import_raw_pcm_source


def discover_sound_sources(project: FragmenterProjectV1) -> dict[str, Any]:
    payload = sound_v1._load_iso_index(project)
    rows: list[dict[str, Any]] = []
    for item in payload.get("files") or []:
        if not isinstance(item, dict) or item.get("is_dir"):
            continue
        normalized = normalize_path(item.get("path"))
        if not normalized:
            continue
        if normalized.startswith(sound_v1.SOUND_PREFIX) or normalized in EXTRA_EXACT_PATHS_V4:
            rows.append(
                {
                    "iso_path": normalized,
                    "lba": int(item.get("lba") or 0),
                    "size": int(item.get("size") or 0),
                    "category": "sound_directory" if normalized.startswith(sound_v1.SOUND_PREFIX) else "known_audio_system_file",
                }
            )
    rows.sort(key=lambda row: row["iso_path"])
    return {
        "version": 4,
        "iso": str(require_ready_project(project).iso),
        "discovered_at": sound_v1._utc_iso(),
        "sources": rows,
        "summary": {
            "sources": len(rows),
            "sound_directory_files": sum(1 for row in rows if row["category"] == "sound_directory"),
            "known_audio_system_files": sum(1 for row in rows if row["category"] == "known_audio_system_file"),
            "snddata_found": any(row["iso_path"] == "data/snddata.bin" for row in rows),
            "eff_hd_found": any(row["iso_path"] == "netgui/eff.hd" for row in rows),
            "eff_bd_found": any(row["iso_path"] == "netgui/eff.bd" for row in rows),
            "bgm_found": any(row["iso_path"] == "voice/bgm.bin" for row in rows),
            "food_found": any(row["iso_path"] == "voice/food.bin" for row in rows),
        },
    }


def extract_project_sound_sources(
    project: FragmenterProjectV1,
    *,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    paths = require_ready_project(project)
    discovery = discover_sound_sources(project)
    source_root = sound_source_root(project)
    iso = Iso9660(paths.iso).open()
    results: list[dict[str, Any]] = []
    total = len(discovery["sources"])
    with paths.iso.open("rb") as iso_file:
        for index, row in enumerate(discovery["sources"], 1):
            target = source_root / Path(*row["iso_path"].split("/"))
            status = "reused" if reuse and target.is_file() and target.stat().st_size == int(row["size"]) else "extracted"
            error = None
            try:
                if status == "extracted":
                    sound_v1._extract_indexed_entry(iso, iso_file, row, target)
            except Exception as exc:
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
            result = {**row, "target": str(target), "status": status, "error": error}
            results.append(result)
            if callback is not None:
                callback({"kind": "sound_extract_progress", "current": index, "total": total, "iso_path": row["iso_path"], "status": status})

    manifest = {
        "version": 4,
        "created_at": sound_v1._utc_iso(),
        "iso": str(paths.iso),
        "source_root": str(source_root),
        "sources": results,
        "summary": {
            **discovery["summary"],
            "extracted": sum(1 for row in results if row["status"] == "extracted"),
            "reused": sum(1 for row in results if row["status"] == "reused"),
            "errors": sum(1 for row in results if row["status"] == "error"),
        },
    }
    manifest_path = sound_v1._atomic_json(sound_reports_root(project) / sound_v1.MANIFEST_NAME, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _raw_pcm_candidate(relative: str | Path, source: Path) -> bool:
    normalized = normalize_path(Path(relative).as_posix())
    if source.suffix.lower() != ".bin" or normalized == "data/snddata.bin":
        return False
    if normalized in RAW_PCM_EXACT_PATHS_V4:
        return True
    return v3._raw_pcm_candidate(relative, source)


def _category(relative: str | Path, fallback: str) -> str:
    normalized = normalize_path(Path(relative).as_posix())
    if normalized.endswith("voice/food.bin") or normalized.endswith("voice/food.wav"):
        return "FOOD stream"
    if normalized.endswith("voice/bgm.bin") or normalized.endswith("voice/bgm.wav"):
        return "BGM / Music"
    return fallback


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
        "version": 4,
        "assumption": {
            "encoding": RAW_PCM_ENCODING,
            "sample_rate": RAW_PCM_SAMPLE_RATE,
            "channels": RAW_PCM_CHANNELS,
            "sample_width": RAW_PCM_SAMPLE_WIDTH,
            "byte_offset": 0,
            "evidence": "User reproduced voice/bgm.bin and voice/food.bin by raw import in Audacity; Fragmenter preserves this as an explicit unverified PCM assumption.",
        },
        "items": rows,
        "summary": {
            "candidates": total,
            "imported": sum(1 for row in rows if row.get("status") == "imported_raw_pcm_assumption"),
            "errors": sum(1 for row in rows if row.get("status") == "error"),
        },
    }
    path = sound_reports_root(project) / RAW_PCM_REPORT
    sound_v1._atomic_json(path, report)
    report["report_path"] = str(path)
    return report


def decode_project_sound_sources(
    project: FragmenterProjectV1,
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    report = sound_v2.decode_project_sound_sources(project, callback=callback)
    raw_pcm = import_project_raw_pcm_candidates(project, callback=callback)
    report["raw_pcm"] = raw_pcm
    report.setdefault("summary", {})["raw_pcm_previews"] = int(raw_pcm["summary"]["imported"])
    report.setdefault("actions", []).append(
        {
            "action": "import_known_voice_bgm_food_raw_pcm",
            "status": "complete" if not raw_pcm["summary"]["errors"] else "partial",
            "summary": raw_pcm["summary"],
            "report_path": raw_pcm["report_path"],
            "verified_container_format": False,
        }
    )
    report_path = Path(str(report.get("report_path") or sound_reports_root(project) / sound_v1.DECODE_REPORT_NAME))
    sound_v1._atomic_json(report_path, {key: value for key, value in report.items() if key != "report_path"})
    report["report_path"] = str(report_path)
    return report


def build_project_sound_library(project: FragmenterProjectV1, *, query: str = "", category: str = "All") -> dict[str, Any]:
    payload = sound_v2.build_project_sound_library(project, query=query, category="All")
    all_items: list[dict[str, Any]] = []
    for row in payload.get("items") or []:
        if not isinstance(row, dict):
            continue
        row["category"] = _category(row.get("relative_path") or "", str(row.get("category") or "Other audio"))
        if row.get("kind") == "source":
            path = Path(str(row.get("path") or ""))
            relative = Path(str(row.get("relative_path") or ""))
            if _raw_pcm_candidate(relative, path):
                row["supported_container"] = True
                row["primary_action"] = "Import Raw PCM"
                row["status"] = "known BGM/FOOD raw PCM candidate; Audacity-default-style preview available"
                row["raw_pcm_assumption"] = {
                    "encoding": RAW_PCM_ENCODING,
                    "sample_rate": RAW_PCM_SAMPLE_RATE,
                    "channels": RAW_PCM_CHANNELS,
                    "byte_offset": 0,
                }
        all_items.append(row)

    categories = sorted({str(row.get("category") or "Other audio") for row in all_items})
    items = all_items if category == "All" else [row for row in all_items if row.get("category") == category]
    payload["version"] = 4
    payload["items"] = items
    payload["categories"] = categories
    summary = payload.setdefault("summary", {})
    summary.update(
        {
            "items": len(items),
            "source_files": sum(1 for row in items if row.get("kind") == "source"),
            "decoded_files": sum(1 for row in items if row.get("kind") == "decoded"),
            "playable_wavs": sum(1 for row in items if row.get("playable")),
            "supported_containers": sum(1 for row in items if row.get("supported_container")),
            "raw_pcm_candidates": sum(1 for row in items if row.get("primary_action") == "Import Raw PCM"),
        }
    )
    sound_v1._atomic_json(sound_reports_root(project) / sound_v1.LIBRARY_NAME, payload)
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
        container = sound_v2.analyze_binary_container(project, source, relative)
        library = build_project_sound_library(project)
        return {
            "source": str(source),
            "relative_path": relative.as_posix(),
            "action": "import_known_raw_pcm_and_analyze_container",
            "raw_pcm": raw_pcm,
            "container_analysis": container,
            "library_summary": library["summary"],
        }
    return sound_v2.analyze_or_extract_sound_item(project, source)

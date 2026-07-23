#!/usr/bin/env python3
"""Canonical direct-audio decode stage.

Direct streams, SOUND files, EFF.HD/BD, BGM and FOOD are decoded here. SNDDATA is
explicitly excluded because its sample extraction and sequencing have dedicated
pipeline stages and canonical outputs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import project_sound_v1 as v1
import project_sound_v4 as v4
import project_sound_v7 as v7
from iso9660 import normalize_path
from project_workspace_v1 import FragmenterProjectV1

sound_root = v7.sound_root
sound_source_root = v7.sound_source_root
sound_decoded_root = v7.sound_decoded_root
sound_reports_root = v7.sound_reports_root
sound_work_root = v7.sound_work_root
# V7 intentionally exposes only the public library surface. The canonical source
# path and ISO discovery helpers remain owned by the base project-sound layer.
canonical_snddata_path = v1.canonical_snddata_path
discover_sound_sources = v1.discover_sound_sources
extract_project_sound_sources = v7.extract_project_sound_sources
build_project_sound_library = v7.build_project_sound_library
analyze_or_extract_sound_item = v7.analyze_or_extract_sound_item


def decode_project_direct_sound_sources(
    project: FragmenterProjectV1,
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source_root = sound_source_root(project)
    decoded_root = sound_decoded_root(project)
    work_root = sound_work_root(project)
    all_files = sorted(
        (path for path in source_root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source_root).as_posix(),
    )
    files = [path for path in all_files if normalize_path(path.relative_to(source_root).as_posix()) != "data/snddata.bin"]
    rows: list[dict[str, Any]] = []
    total = len(files)
    for index, source in enumerate(files, 1):
        relative = source.relative_to(source_root)
        results = v1._decode_one_source(source, decoded_root, work_root, relative)
        rows.extend(results)
        if callback is not None:
            callback(
                {
                    "kind": "sound_decode_progress",
                    "current": index,
                    "total": total,
                    "relative_path": relative.as_posix(),
                    "actions": len(results),
                }
            )

    raw_pcm = v4.import_project_raw_pcm_candidates(project, callback=callback)
    rows.append(
        {
            "action": "import_known_voice_bgm_food_raw_pcm",
            "status": "complete" if not raw_pcm["summary"]["errors"] else "partial",
            "summary": raw_pcm["summary"],
            "report_path": raw_pcm["report_path"],
            "verified_container_format": False,
        }
    )
    decoded_wavs = sorted(path for path in decoded_root.rglob("*.wav") if path.is_file())
    report = {
        "version": 8,
        "created_at": v1._utc_iso(),
        "source_root": str(source_root),
        "decoded_root": str(decoded_root),
        "actions": rows,
        "raw_pcm": raw_pcm,
        "summary": {
            "source_files_seen": len(all_files),
            "direct_source_files": total,
            "snddata_sources_skipped": len(all_files) - total,
            "actions": len(rows),
            "decoded_wavs": len(decoded_wavs),
            "raw_pcm_previews": int(raw_pcm["summary"]["imported"]),
            "errors": sum(1 for row in rows if row.get("status") == "error"),
            "partial": sum(1 for row in rows if row.get("status") == "partial"),
        },
        "boundary": "SNDDATA is excluded from direct decode and handled only by snddata_samples and snddata_mixer.",
    }
    target = sound_reports_root(project) / v1.DECODE_REPORT_NAME
    v1._atomic_json(target, report)
    report["report_path"] = str(target)
    return report


# Public compatibility name for callers that intentionally select the direct stage.
decode_project_sound_sources = decode_project_direct_sound_sources

#!/usr/bin/env python3
"""Simple playable audio catalog for decoded Fragmenter project media.

This is intentionally separate from the experimental SNDDATA sequence mixer.  It
shows every WAV anywhere under the active media pipeline, including BGM/FOOD/EFF,
voice-like paths, decoded SNDDATA samples, and rendered sequence previews.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from project_preflight_v1 import resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1

PLAYABLE_EXTENSIONS = {".wav"}
CONTAINER_EXTENSIONS = {".bin", ".hd", ".bd", ".vag", ".vh", ".vb"}


def _category(relative: str, suffix: str) -> tuple[str, str]:
    low = relative.lower().replace("\\", "/")
    name = Path(low).name
    if "/previews/" in low or "preview" in name:
        return "Experimental sequence preview", "EXPERIMENTAL SEQUENCE RENDER"
    if "/snddata/samples/" in low or ("snddata" in low and suffix == ".wav"):
        return "SNDDATA decoded sample", "PS ADPCM DECODE"
    if "bgm" in low:
        return "BGM", "CONFIRMED WAV" if suffix == ".wav" else "SOURCE CONTAINER"
    if "voice" in low or "speech" in low or "dialog" in low:
        return "Voice", "CONFIRMED WAV" if suffix == ".wav" else "SOURCE CONTAINER"
    if "food" in low:
        return "FOOD stream", "CONFIRMED WAV" if suffix == ".wav" else "SOURCE CONTAINER"
    if "eff" in low or "effect" in low or "sfx" in low:
        return "Sound effect", "CONFIRMED WAV" if suffix == ".wav" else "SOURCE CONTAINER"
    if suffix == ".wav":
        return "Decoded WAV", "CONFIRMED WAV"
    if name == "snddata.bin":
        return "SNDDATA source", "SOURCE CONTAINER"
    return "Audio container", "SOURCE CONTAINER"


def _wav_metadata(path: Path) -> dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            return {
                "channels": handle.getnchannels(),
                "sample_width": handle.getsampwidth(),
                "sample_rate": rate,
                "frame_count": frames,
                "duration": frames / float(rate) if rate else 0.0,
                "wav_valid": True,
            }
    except Exception as exc:
        return {"wav_valid": False, "duration": 0.0, "error": str(exc)}


def discover_audio_library(project: FragmenterProjectV1, query: str = "", category: str = "All") -> dict[str, Any]:
    paths = resolve_runtime_paths(project)
    root = paths.media_pipeline
    needle = query.strip().lower()
    requested = category.strip() or "All"
    rows: list[dict[str, Any]] = []
    if root.is_dir():
        for path in sorted((candidate for candidate in root.rglob("*") if candidate.is_file()), key=lambda value: str(value).lower()):
            suffix = path.suffix.lower()
            if suffix not in PLAYABLE_EXTENSIONS and suffix not in CONTAINER_EXTENSIONS:
                continue
            relative = path.relative_to(root).as_posix()
            item_category, provenance = _category(relative, suffix)
            playable = suffix in PLAYABLE_EXTENSIONS
            metadata = _wav_metadata(path) if playable else {"duration": 0.0, "wav_valid": False}
            haystack = f"{path.name} {relative} {item_category} {provenance}".lower()
            if needle and not all(token in haystack for token in needle.split()):
                continue
            if requested != "All" and item_category != requested:
                continue
            stat = path.stat()
            rows.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "relative_path": relative,
                    "category": item_category,
                    "provenance": provenance,
                    "size": stat.st_size,
                    "playable": playable and bool(metadata.get("wav_valid")),
                    "status": "playable" if playable and metadata.get("wav_valid") else "invalid WAV" if playable else "source container",
                    **metadata,
                }
            )
    categories = sorted({row["category"] for row in rows})
    playable_rows = [row for row in rows if row["playable"]]
    return {
        "version": 1,
        "root": str(root),
        "items": rows,
        "categories": categories,
        "summary": {
            "items": len(rows),
            "playable_wavs": len(playable_rows),
            "source_containers": sum(1 for row in rows if not row["playable"]),
            "bgm_wavs": sum(1 for row in playable_rows if row["category"] == "BGM"),
            "voice_wavs": sum(1 for row in playable_rows if row["category"] == "Voice"),
            "effect_wavs": sum(1 for row in playable_rows if row["category"] == "Sound effect"),
            "snddata_samples": sum(1 for row in playable_rows if row["category"] == "SNDDATA decoded sample"),
        },
    }

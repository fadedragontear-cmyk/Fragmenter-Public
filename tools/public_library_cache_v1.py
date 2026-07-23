#!/usr/bin/env python3
"""Precompute public 3D, playable-audio, and SNDDATA list models.

RUN ALL owns this cache so opening a heavy tab does not begin the expensive first
classification/catalog pass. The cache contains metadata only; no game payloads.
Each section is written even when another section is unavailable, so an audio-only
repair can still prepare the playable library without requiring a completed CCSF run.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from project_sound_v7 import build_project_sound_library
from project_workspace_v1 import FragmenterProjectV1
from snddata_research_workbench_v1 import readiness, sequence_rows

CACHE_VERSION = 2


def cache_root(project: FragmenterProjectV1) -> Path:
    return Path(project.workspace_dir).expanduser() / "cache" / "public_lists_v104"


def cache_paths(project: FragmenterProjectV1) -> dict[str, Path]:
    root = cache_root(project)
    return {
        "visual": root / "visual_assets.json",
        "audio": root / "playable_audio.json",
        "sequences": root / "snddata_sequences.json",
        "summary": root / "summary.json",
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_jsonable(payload), indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _visual_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    # Import lazily: the pipeline can build metadata caches without constructing a
    # Tk application, while retaining the accepted visual classification rules.
    from fragmenter_public_gui_v3 import discover_visual_assets_v3

    return [dict(row) for row in discover_visual_assets_v3(project, query="", category="All", limit=100_000)]


def _playable_audio(project: FragmenterProjectV1) -> dict[str, Any]:
    model = build_project_sound_library(
        project,
        query="",
        category="All",
        include_pcm_research=False,
    )
    items = [
        dict(row)
        for row in model.get("items") or []
        if isinstance(row, dict)
        and bool(row.get("playable"))
        and str(row.get("path") or row.get("relative_path") or "").casefold().endswith(".wav")
    ]
    categories: list[str] = []
    for row in items:
        category = str(row.get("category") or "Other Playable")
        if category not in categories:
            categories.append(category)
    return {
        "version": CACHE_VERSION,
        "items": items,
        "categories": categories,
        "summary": {
            "playable_sounds": len(items),
            "categories": {name: sum(str(row.get("category") or "") == name for row in items) for name in categories},
            "raw_pcm_visible": 0,
            "source_containers_visible": 0,
        },
    }


def _capture(builder: Callable[[], Any], fallback: Any) -> tuple[Any, str]:
    try:
        return builder(), ""
    except Exception as exc:
        return fallback, f"{type(exc).__name__}: {exc}"


def build_public_library_cache(project: FragmenterProjectV1) -> dict[str, Any]:
    """Build every public metadata list and preserve useful partial results.

    Missing visual extraction must not prevent audio lists from being prepared, and a
    missing mixer catalog must not erase playable direct WAVs. Errors are explicit in
    the summary and in each cache file so the UI can explain the next required stage.
    """
    paths = cache_paths(project)
    generated = datetime.now(timezone.utc).isoformat()

    visual, visual_error = _capture(lambda: _visual_rows(project), [])
    audio, audio_error = _capture(
        lambda: _playable_audio(project),
        {
            "version": CACHE_VERSION,
            "items": [],
            "categories": [],
            "summary": {
                "playable_sounds": 0,
                "categories": {},
                "raw_pcm_visible": 0,
                "source_containers_visible": 0,
            },
        },
    )
    state, readiness_error = _capture(lambda: readiness(project), {})

    sequences: list[dict[str, Any]] = []
    sequence_error = readiness_error
    if not sequence_error and bool(state.get("catalog_exists")):
        sequences, sequence_error = _capture(
            lambda: [dict(row) for row in sequence_rows(project, query="", status_filter="All")],
            [],
        )
    elif not sequence_error:
        sequence_error = "Mixer catalog is not ready; run snddata_mixer before sequence research."

    errors = {
        key: value
        for key, value in {
            "visual": visual_error,
            "audio": audio_error,
            "readiness": readiness_error,
            "sequences": sequence_error,
        }.items()
        if value
    }

    _write_json(
        paths["visual"],
        {
            "version": CACHE_VERSION,
            "generated_at": generated,
            "ready": not visual_error,
            "error": visual_error,
            "items": visual,
        },
    )
    _write_json(
        paths["audio"],
        {
            "generated_at": generated,
            "ready": not audio_error,
            "error": audio_error,
            **audio,
        },
    )
    _write_json(
        paths["sequences"],
        {
            "version": CACHE_VERSION,
            "generated_at": generated,
            "ready": bool(state.get("catalog_exists")) and not sequence_error,
            "error": sequence_error,
            "items": sequences,
        },
    )

    summary = {
        "version": CACHE_VERSION,
        "generated_at": generated,
        "status": "complete" if not errors else "partial",
        "visual_assets": len(visual),
        "playable_sounds": len(audio.get("items") or []),
        "snddata_sequences": len(sequences),
        "snddata_readiness": state,
        "errors": errors,
        "writes_game_data": False,
        "paths": {key: str(path) for key, path in paths.items()},
    }
    _write_json(paths["summary"], summary)
    return summary


def load_cache(project: FragmenterProjectV1, name: str) -> dict[str, Any] | None:
    path = cache_paths(project).get(str(name))
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None

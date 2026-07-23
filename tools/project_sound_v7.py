#!/usr/bin/env python3
"""Public audio catalog grouping with raw-PCM research rows excluded by default."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import project_sound_v6 as v6
from iso9660 import normalize_path
from project_workspace_v1 import FragmenterProjectV1

sound_root = v6.sound_root
sound_source_root = v6.sound_source_root
sound_decoded_root = v6.sound_decoded_root
sound_reports_root = v6.sound_reports_root
sound_work_root = v6.sound_work_root
extract_project_sound_sources = v6.extract_project_sound_sources
decode_project_sound_sources = v6.decode_project_sound_sources
analyze_or_extract_sound_item = v6.analyze_or_extract_sound_item


def _normalized_fields(row: dict[str, Any]) -> str:
    return " ".join(
        normalize_path(str(row.get(key) or ""))
        for key in ("relative_path", "path", "name", "status", "provenance", "primary_action")
    ).lower()


def is_pcm_research_row(row: dict[str, Any]) -> bool:
    if row.get("raw_pcm_assumption"):
        return True
    combined = _normalized_fields(row)
    if any(token in combined for token in ("raw_pcm", "raw-pcm", "raw pcm", ".pcm", ".raw")):
        return True
    relative = normalize_path(str(row.get("relative_path") or "")).lower()
    # These are the two explicit Audacity-style raw imports created by the
    # research path. Keep them out of the normal playback catalog.
    if relative.endswith("voice/bgm.bin") or relative.endswith("voice/food.bin"):
        return True
    if relative.endswith("voice/bgm.wav") or relative.endswith("voice/food.wav"):
        return True
    return False


def _usage_group(row: dict[str, Any]) -> str:
    hint = str(row.get("usage_hint") or "").lower()
    if "very short" in hint:
        return "Short one-shots"
    if "sting" in hint:
        return "Stings / phrases"
    if "sustained" in hint:
        return "Sustained / ambience"
    return "Unclassified"


def _public_group(row: dict[str, Any]) -> str:
    category = str(row.get("category") or "").lower()
    if row.get("category") == "SNDDATA Samples":
        row["usage_group"] = _usage_group(row)
        return "SNDDATA Samples"
    if row.get("playable"):
        if "bgm" in category or "music" in category:
            return "BGM / Music"
        if "voice" in category:
            return "Voice"
        if "effect" in category or "sfx" in category:
            return "Sound Effects"
        return "Other Playable"
    if row.get("kind") == "source" or row.get("supported_container"):
        return "Source Containers"
    return "Other Audio"


def build_project_sound_library(
    project: FragmenterProjectV1,
    *,
    query: str = "",
    category: str = "All",
    include_pcm_research: bool = False,
) -> dict[str, Any]:
    payload = v6.build_project_sound_library(project, query=query, category="All", include_raw_pcm=True)
    original = [row for row in payload.get("items") or [] if isinstance(row, dict)]
    pcm_rows = [row for row in original if is_pcm_research_row(row)]
    visible = original if include_pcm_research else [row for row in original if not is_pcm_research_row(row)]
    for row in visible:
        row["category"] = _public_group(row)
    categories = [
        name
        for name in (
            "SNDDATA Samples",
            "BGM / Music",
            "Voice",
            "Sound Effects",
            "Other Playable",
            "Source Containers",
            "Other Audio",
        )
        if any(row.get("category") == name for row in visible)
    ]
    items = visible if category == "All" else [row for row in visible if row.get("category") == category]
    items.sort(
        key=lambda row: (
            categories.index(row["category"]) if row.get("category") in categories else 999,
            str(row.get("name") or "").lower(),
        )
    )
    payload["version"] = 7
    payload["items"] = items
    payload["categories"] = categories
    hidden_pcm = len(pcm_rows) if not include_pcm_research else 0
    summary = payload.setdefault("summary", {})
    summary.update(
        {
            "items": len(items),
            "playable_wavs": sum(1 for row in items if row.get("playable")),
            "snddata_sample_wavs": sum(
                1 for row in items if row.get("playable") and row.get("category") == "SNDDATA Samples"
            ),
            "pcm_research_rows_hidden": hidden_pcm,
            # Compatibility alias used by the inherited v12 status line.
            "hidden_raw_pcm_rows": hidden_pcm,
            "groups": {name: sum(1 for row in items if row.get("category") == name) for name in categories},
        }
    )
    v6.v5.v4.sound_v1._atomic_json(sound_reports_root(project) / v6.v5.v4.sound_v1.LIBRARY_NAME, payload)
    return payload

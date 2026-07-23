#!/usr/bin/env python3
"""Remove flat/by-bank SNDDATA aliases from the unified playable-audio catalog."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import audio_library_research_v1 as base

_ORIGINAL_MERGED = base.merged_audio_rows
_INSTALLED = False


def _identity(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    try:
        return str(path.resolve()).replace("\\", "/").casefold()
    except OSError:
        return str(path).replace("\\", "/").casefold()


def merged_audio_rows(project: Any) -> list[dict[str, Any]]:
    rows = [dict(row) for row in _ORIGINAL_MERGED(project)]
    sample_aliases: set[str] = set()
    for row in rows:
        if not row.get("is_snddata_sample"):
            continue
        for key in ("output_path", "flat_output_path"):
            identity = _identity(row.get(key))
            if identity:
                sample_aliases.add(identity)

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        identity = _identity(row.get("output_path"))
        if not row.get("is_snddata_sample") and identity in sample_aliases:
            # The public library exposes both by-bank and flat hardlinks. They are
            # one SNDDATA sample, not a second direct WAV classification target.
            continue
        stable = str(row.get("unified_key") or identity)
        if stable and stable in seen:
            continue
        if stable:
            seen.add(stable)
        output.append(row)
    return output


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    base.merged_audio_rows = merged_audio_rows
    # export_canonical_audio_research resolves merged_audio_rows from its module
    # globals at call time, so canonical JSON/CSV automatically use this policy.
    _INSTALLED = True

#!/usr/bin/env python3
"""Require the current boundary/catalog generation before reusing sample WAVs."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import snddata_music_system_v3 as music_v3
import snddata_sample_bridge_v1 as bridge

_INSTALLED = False


def ensure_corrected_samples(
    project,
    data: bytes,
    groups: list[Any],
) -> list[dict[str, Any]]:
    del groups
    report = bridge._sample_report(project)
    source_hash = hashlib.sha256(data).hexdigest()
    raw_rows = [row for row in report.get("samples") or [] if isinstance(row, dict)]
    usable = [row for row in raw_rows if not row.get("errors")]
    current = str(report.get("source_sha256") or "") == source_hash
    outputs_present = bool(usable) and all(
        Path(str(row.get("output_path") or "")).is_file() for row in usable
    )
    boundary_current = (
        int((report.get("sample_boundary_policy") or {}).get("version") or 0) >= 3
    )
    layout_current = int((report.get("layout") or {}).get("version") or 0) >= 2
    if current and outputs_present and boundary_current and layout_current:
        return raw_rows
    rebuilt = bridge.extract_project_snddata_samples(project, clean=True)
    return [row for row in rebuilt.get("samples") or [] if isinstance(row, dict)]


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    bridge.ensure_canonical_samples = ensure_corrected_samples
    music_v3.ensure_canonical_samples = ensure_corrected_samples
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Installed by the Fragmenter public launcher.")

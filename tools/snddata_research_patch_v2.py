#!/usr/bin/env python3
"""Correct public mixer readiness counts and normalize sample evidence labels.

The forensic catalog intentionally retains the legacy ``program_zero`` hypothesis,
but the public mixer cannot select or confirm that route. Counting those candidates
as normally renderable made sequences appear playable when Auto selected a different,
incomplete routing hypothesis. This patch also formats every sample identifier as a
four-digit ID so ``sample 12`` and ``sample 0012`` cannot appear to be different assets.
"""
from __future__ import annotations

from typing import Any

import snddata_research_workbench_v1 as workbench
from snddata_music_system_v5 import _compat_candidate

AUDITION_ROUTING_MODES = frozenset({"program_change", "channel_as_program"})
DIAGNOSTIC_ROUTING_MODES = frozenset({"program_zero"})
_ORIGINAL_CANDIDATE_ROWS = workbench.candidate_rows
_INSTALLED = False


def candidate_status_counts(sequence: dict[str, Any]) -> dict[str, int]:
    """Count only selectable routing modes as public renderable candidates."""
    audition_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    for hypothesis in sequence.get("routing_hypotheses") or []:
        if not isinstance(hypothesis, dict):
            continue
        mode = str(hypothesis.get("mode") or "")
        target = audition_rows if mode in AUDITION_ROUTING_MODES else diagnostic_rows
        target.extend(
            _compat_candidate(candidate)
            for candidate in hypothesis.get("candidates") or []
            if isinstance(candidate, dict)
        )
    return {
        "candidates": len(audition_rows),
        "renderable": sum(row.get("status") == "renderable" for row in audition_rows),
        "missing_programs": sum(row.get("status") == "missing_programs" for row in audition_rows),
        "missing_samples": sum(row.get("status") == "missing_samples" for row in audition_rows),
        "diagnostic_candidates": len(diagnostic_rows),
        "diagnostic_renderable": sum(row.get("status") == "renderable" for row in diagnostic_rows),
    }


def candidate_rows(
    project: Any,
    sequence_id: str,
    *,
    routing_mode: str = "Auto",
) -> dict[str, Any]:
    """Return the normal workbench model with canonical four-digit sample labels."""
    model = _ORIGINAL_CANDIDATE_ROWS(project, sequence_id, routing_mode=routing_mode)
    for row in model.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        missing_programs = [int(value) for value in row.get("missing_program_indexes") or []]
        missing_samples = [int(value) for value in row.get("missing_sample_ids") or []]
        row["required_sample_labels"] = [f"sample {int(value):04d}" for value in row.get("required_sample_ids") or []]
        row["missing_sample_labels"] = [f"sample {value:04d}" for value in missing_samples]
        row["missing_summary"] = ", ".join(
            [
                *(f"Program {value}" for value in missing_programs[:8]),
                *(f"sample {value:04d}" for value in missing_samples[:8]),
            ]
        )
    return model


def install() -> None:
    """Install corrected counts and labels before the GUI imports workbench helpers."""
    global _INSTALLED
    if _INSTALLED:
        return
    workbench._candidate_status_counts = candidate_status_counts
    workbench.candidate_rows = candidate_rows
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Installed by the Fragmenter public launcher.")
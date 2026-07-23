#!/usr/bin/env python3
"""Canonical-layout SNDDATA sample library with validated entry boundaries."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Callable

import snddata_sample_library_v2 as v2
from project_sound_v1 import canonical_snddata_path, sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_sample_body_v2 import install as install_body_patch
from snddata_sample_boundary_v2 import (
    annotate_report,
    install as install_boundary_patch,
    reset_boundary_evidence,
)
from snddata_sample_catalog_v1 import finalize_sample_catalog
from snddata_sample_trim_v3 import install as install_trim_patch

REPORT_NAME = "snddata_sample_library.json"
CSV_NAME = "snddata_sample_library.csv"


def project_paths(project: FragmenterProjectV1) -> tuple[Path, Path, Path, Path]:
    source = canonical_snddata_path(project)
    output = sound_decoded_root(project) / "snddata" / "samples"
    reports = sound_reports_root(project)
    return source, output, reports / REPORT_NAME, reports / CSV_NAME


def annotate_body_resolution(report: dict[str, Any]) -> dict[str, Any]:
    methods: Counter[str] = Counter()
    shifted_banks = 0
    unresolved_banks = 0
    sample_banks = 0

    for bank in report.get("banks") or []:
        if not isinstance(bank, dict) or int(bank.get("resource_type") or 0) != 2:
            continue
        sample_banks += 1
        candidates = [
            candidate
            for candidate in bank.get("body_candidates") or []
            if isinstance(candidate, dict)
        ]
        selected = candidates[0] if candidates else {}
        method = str(selected.get("resolution_method") or "unresolved")
        shift = int(selected.get("body_shift") or 0)
        resolution = selected.get("body_resolution")
        bank["body_resolution_method"] = method
        bank["body_shift"] = shift
        bank["body_resolution"] = resolution
        methods[method] += 1
        shifted_banks += int(method == "unique_clean_bank_shift" and shift > 0)
        unresolved_banks += int(
            method
            not in {
                "unique_clean_bank_shift",
                "current_body_base_not_nested_sequence",
            }
        )

    report["body_base_resolution"] = {
        "policy": (
            "Preserve SCEIVagi stream offsets and span lengths. When the legacy base "
            "points at a nested SCEI sequence resource, accept only one 16-byte-aligned "
            "shift that validates every retained ADPCM block in every bank entry."
        ),
        "sample_program_banks": sample_banks,
        "status_counts": dict(methods),
        "shifted_banks": shifted_banks,
        "unresolved_banks": unresolved_banks,
        "classification_gate": "pass" if sample_banks and unresolved_banks == 0 else "fail",
    }
    report.setdefault("format_authority", {})["secondary_body_base"] = (
        "Whole-bank validated base; nested sequence-resource starts are rejected."
    )
    return report


def extract_project_snddata_samples(
    project: FragmenterProjectV1,
    *,
    clean: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source, output, report_path, csv_report = project_paths(project)
    reset_boundary_evidence()
    install_boundary_patch()
    install_trim_patch()
    install_body_patch()
    report = v2.extract_snddata_file(
        source,
        output,
        report_path=report_path,
        csv_path=csv_report,
        clean=clean,
        callback=callback,
    )
    annotate_body_resolution(report)
    annotate_report(report)
    finalize_sample_catalog(report, output, reports_root=report_path.parent)
    # v2 writes once before the correction/catalog pass. Rewrite canonical reports after
    # every row has its body base, boundary model, flat index, and final by-bank path.
    v2._write_reports(report, report_path, csv_report)
    return report

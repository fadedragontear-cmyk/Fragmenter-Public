#!/usr/bin/env python3
"""Audit focused CCSF extraction for truncation and missing output evidence."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_preflight_v1 import resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1

CORE_CONTAINER_NAMES = {"data/data.bin", "data.bin"}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_iso_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip().lower()
    text = re.sub(r"^/+", "", text)
    text = re.sub(r";\d+$", "", text)
    return text


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def _resolve_extracted_output(paths, value: Any) -> tuple[Path, bool]:
    """Resolve current and pre-layout-v2 CCSF report paths.

    V39 may move ``workspace/extracted_ccs`` to ``workspace/extracted/ccsf`` after
    extraction. Older reports can therefore contain a valid historical absolute path
    even though the file now lives under the canonical root.
    """
    text = str(value or "").strip()
    candidate = Path(text) if text else Path()
    if text and not candidate.is_absolute():
        candidate = paths.workspace / candidate
    if text and candidate.is_file():
        return candidate, False

    normalized = text.replace("\\", "/")
    marker = "/extracted_ccs/"
    lower = normalized.casefold()
    index = lower.find(marker)
    if index >= 0:
        relative = normalized[index + len(marker) :]
        migrated = paths.extracted_ccs / Path(relative)
        if migrated.is_file():
            return migrated, True

    if normalized.casefold().startswith("extracted_ccs/"):
        migrated = paths.extracted_ccs / Path(normalized[len("extracted_ccs/") :])
        if migrated.is_file():
            return migrated, True

    return candidate, False


def audit_extraction(project: FragmenterProjectV1) -> dict[str, Any]:
    paths = resolve_runtime_paths(project)
    extraction_path = paths.reports / "iso_ccsf_extraction_index.json"
    library_path = paths.reports / "asset_library.json"
    index_path = paths.cache_iso / "iso_index.json"
    missing_reports = [str(path) for path in (extraction_path, library_path, index_path) if not path.is_file()]
    if missing_reports:
        raise FileNotFoundError("Missing extraction audit inputs: " + ", ".join(missing_reports))

    extraction = _load(extraction_path)
    library = _load(library_path)
    iso_index = _load(index_path)
    iso_sizes = {
        _normalize_iso_path(row.get("path")): int(row.get("size") or 0)
        for row in iso_index.get("files", [])
        if isinstance(row, dict) and not row.get("is_dir")
    }

    container_rows: list[dict[str, Any]] = []
    truncated: list[dict[str, Any]] = []
    for row in extraction.get("containers", []) or []:
        if not isinstance(row, dict):
            continue
        internal = str(row.get("path") or "").replace("\\", "/")
        normalized = _normalize_iso_path(internal)
        declared = iso_sizes.get(normalized, int(row.get("size") or 0))
        scanned = int(row.get("bytes_scanned") or 0)
        complete = bool(declared <= 0 or scanned >= declared)
        item = {
            "path": internal,
            "normalized_path": normalized,
            "declared_size": declared,
            "bytes_scanned": scanned,
            "complete": complete,
            "core_asset_container": normalized in CORE_CONTAINER_NAMES,
            "ccsf_bundle_count": int(row.get("ccsf_bundle_count") or 0),
        }
        container_rows.append(item)
        if not complete:
            truncated.append(item)

    physical_rows = extraction.get("confirmed_ccsf_bundles", []) or []
    missing_outputs: list[dict[str, Any]] = []
    migrated_paths_resolved = 0
    for row in physical_rows:
        if not isinstance(row, dict):
            continue
        value = str(row.get("extracted_ccsf_path") or "")
        candidate, migrated = _resolve_extracted_output(paths, value)
        if migrated:
            migrated_paths_resolved += 1
        if not value or not candidate.is_file():
            missing_outputs.append(
                {
                    "ccsf_name": row.get("ccsf_name"),
                    "reported_path": value,
                    "expected_path": str(candidate),
                    "source_offset": row.get("source_offset"),
                }
            )

    assets = [row for row in library.get("assets", []) if isinstance(row, dict)]
    name_values = [str(row.get("display_name") or "").lower() for row in assets]
    path_values = [str(row.get("preferred_file") or "").replace("\\", "/").lower() for row in assets]
    combined = list(zip(name_values, path_values))

    families = {
        "aura": sum(1 for name, path in combined if "aura" in name or "aura" in path or "caur" in name),
        "environment_field_bg": sum(1 for name, path in combined if any(term in f"{name} {path}" for term in ("field", "dungeon", "town", "background", "/bg", "sky"))),
        "weapons_cw": sum(1 for name, path in combined if Path(name).stem.startswith("cw") or Path(path).stem.startswith("cw")),
        "enemy_e648_e780": sum(1 for name, path in combined if _enemy_range(Path(name).stem) or _enemy_range(Path(path).stem)),
        "grunty": sum(1 for name, path in combined if "c_dog_bod" in f"{name} {path}" or "cdogbod" in f"{name} {path}"),
        "food": sum(1 for name, path in combined if "x_g_food" in f"{name} {path}" or "xgfood" in f"{name} {path}"),
    }

    core_rows = [row for row in container_rows if row["core_asset_container"]]
    blockers: list[str] = []
    warnings: list[str] = []
    if not core_rows:
        blockers.append("DATA/DATA.BIN was not present in the focused extraction container list")
    elif not all(row["complete"] for row in core_rows):
        blockers.append("DATA/DATA.BIN was only partially scanned")
    if missing_outputs:
        blockers.append(f"{len(missing_outputs)} indexed CCSF outputs are missing on disk")
    if migrated_paths_resolved:
        warnings.append(f"Recovered {migrated_paths_resolved} legacy extracted_ccs paths from the canonical extracted/ccsf folder")
    if not families["aura"]:
        warnings.append("No Aura/caur asset was found in the logical library")
    if not families["environment_field_bg"]:
        warnings.append("No field/background naming families were found")
    if not families["weapons_cw"]:
        warnings.append("No user-confirmed cw weapon assets were found")

    report = {
        "version": 2,
        "created_at": _utc_iso(),
        "status": "blocked" if blockers else "complete_with_warnings" if warnings else "complete",
        "source_reports": {
            "extraction": str(extraction_path),
            "asset_library": str(library_path),
            "iso_index": str(index_path),
        },
        "summary": {
            "containers_selected": int(extraction.get("containers_selected") or len(container_rows)),
            "containers_truncated": len(truncated),
            "confirmed_ccsf_bundles": len(physical_rows),
            "logical_assets": len(assets),
            "missing_output_files": len(missing_outputs),
            "legacy_paths_recovered": migrated_paths_resolved,
        },
        "family_counts": families,
        "containers": container_rows,
        "truncated_containers": truncated,
        "missing_outputs": missing_outputs[:500],
        "blockers": blockers,
        "warnings": warnings,
        "notes": [
            "Offline .hack naming ranges are audit hints, not proof of Fragment asset identity.",
            "A full DATA/DATA.BIN scan is required before absence is treated as meaningful.",
            "ISO9660 version suffixes such as ;1 are normalized before container comparison.",
            "Legacy extracted_ccs report paths are resolved against extracted/ccsf after workspace migration.",
        ],
    }
    report_path = _atomic(paths.reports / "extraction_audit.json", report)
    report["report_path"] = str(report_path)
    return report


def _enemy_range(value: str) -> bool:
    match = re.match(r"^e(\d{3})(?:[_-].*)?$", value.lower())
    return bool(match and 648 <= int(match.group(1)) <= 780)

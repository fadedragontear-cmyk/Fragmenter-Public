#!/usr/bin/env python3
"""Inventory x000-x999 assets across extracted files and asset-library metadata."""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

from project_workspace_v1 import FragmenterProjectV1

_X_STEM = re.compile(r"^x(\d{2,3})(?!\d)", re.IGNORECASE)
_X_TOKEN = re.compile(r"(?:^|[^A-Za-z0-9])x(\d{2,3})(?!\d)", re.IGNORECASE)
KNOWN_VISUAL_EXTENSIONS = {".tmp", ".ccs", ".ccsf", ".cmp", ".bin"}


def x_number_from_name(value: str) -> int | None:
    match = _X_STEM.match(Path(str(value or "")).stem)
    return int(match.group(1)) if match else None


def filesystem_x_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    root = project.workspace_path("extracted_ccs")
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        number = x_number_from_name(path.name)
        if number is None:
            continue
        stat = path.stat()
        rows.append(
            {
                "number": number,
                "name": path.name,
                "relative_path": path.relative_to(root).as_posix(),
                "absolute_path": str(path.resolve()),
                "size": stat.st_size,
                "extension": path.suffix.lower(),
                "known_visual_extension": path.suffix.lower() in KNOWN_VISUAL_EXTENSIONS,
            }
        )
    rows.sort(key=lambda row: (int(row["number"]), str(row["name"]).casefold(), str(row["relative_path"]).casefold()))
    return rows


def _numbers_from_value(value: Any) -> set[int]:
    values: list[str]
    if isinstance(value, (list, tuple, set)):
        values = [str(item) for item in value]
    else:
        values = [str(value or "")]
    result: set[int] = set()
    for text in values:
        for match in _X_TOKEN.finditer(text):
            result.add(int(match.group(1)))
    return result


def _asset_library_numbers(project: FragmenterProjectV1) -> tuple[set[int], list[dict[str, Any]]]:
    path = project.workspace_path("reports") / "asset_library.json"
    if not path.is_file():
        return set(), []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), []
    numbers: set[int] = set()
    evidence: list[dict[str, Any]] = []
    for asset in payload.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        values: list[Any] = [
            asset.get("display_name"),
            asset.get("name"),
            asset.get("preferred_file"),
            asset.get("relative_file"),
            asset.get("file"),
            *(asset.get("duplicate_files") or []),
            *(asset.get("identifiers") or []),
        ]
        found: set[int] = set()
        for value in values:
            found.update(_numbers_from_value(value))
        if found:
            numbers.update(found)
            evidence.append(
                {
                    "numbers": sorted(found),
                    "name": str(asset.get("display_name") or asset.get("name") or ""),
                    "preferred_file": str(asset.get("preferred_file") or asset.get("relative_file") or asset.get("file") or ""),
                    "type": str(asset.get("type") or ""),
                }
            )
    return numbers, evidence


def export_x_series_inventory(
    project: FragmenterProjectV1,
    browser_rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    files = filesystem_x_rows(project)
    browser_paths = {
        str(Path(str(row.get("absolute_path") or "")).expanduser().resolve())
        for row in browser_rows
        if row.get("absolute_path")
    }
    for row in files:
        row["visible_in_browser_snapshot"] = str(Path(row["absolute_path"]).resolve()) in browser_paths
    file_numbers = {int(row["number"]) for row in files}
    browser_numbers = {int(row["number"]) for row in files if row["visible_in_browser_snapshot"]}
    metadata_numbers, metadata_evidence = _asset_library_numbers(project)
    indexed_without_file = sorted(metadata_numbers - file_numbers)
    files_not_in_browser = [row for row in files if not row["visible_in_browser_snapshot"]]
    present = file_numbers | metadata_numbers
    missing = [number for number in range(1000) if number not in present]

    reports = project.workspace_path("reports") / "x_series_inventory"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = reports / "x_series_inventory_latest.json"
    csv_path = reports / "x_series_files_latest.csv"
    zip_path = reports / f"x_series_inventory_{stamp}.zip"
    payload = {
        "format": "Fragmenter x-series inventory v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "filesystem_file_count": len(files),
        "filesystem_numbers": sorted(file_numbers),
        "browser_snapshot_numbers": sorted(browser_numbers),
        "asset_library_numbers": sorted(metadata_numbers),
        "indexed_without_extracted_file": indexed_without_file,
        "filesystem_files_not_in_browser_snapshot": files_not_in_browser,
        "numbers_absent_from_files_and_asset_library": missing,
        "asset_library_evidence": metadata_evidence,
        "files": files,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = (
        "number",
        "name",
        "relative_path",
        "size",
        "extension",
        "known_visual_extension",
        "visible_in_browser_snapshot",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in files:
            writer.writerow({key: row.get(key) for key in fields})
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(json_path, json_path.name)
        archive.write(csv_path, csv_path.name)
    return {
        "filesystem_file_count": len(files),
        "file_number_count": len(file_numbers),
        "browser_number_count": len(browser_numbers),
        "asset_library_number_count": len(metadata_numbers),
        "indexed_without_file_count": len(indexed_without_file),
        "files_not_in_browser_count": len(files_not_in_browser),
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "zip_path": str(zip_path),
    }

#!/usr/bin/env python3
"""Portable export of user visual classifications, notes, flags, poses and views."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

from project_workspace_v1 import FragmenterProjectV1
from visual_asset_annotations_v1 import annotation_records


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _row_index(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        relative = str(row.get("relative_path") or "").replace("\\", "/").strip("/")
        if relative:
            indexed[relative] = dict(row)
    return indexed


def export_visual_classification_ledger(
    project: FragmenterProjectV1,
    rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    indexed = _row_index(rows)
    records = annotation_records(project)
    exported: list[dict[str, Any]] = []
    for asset_key, annotation in sorted(records.items(), key=lambda item: item[0].casefold()):
        automatic = indexed.get(asset_key, {})
        camera_saved = bool(annotation.get("camera_saved", False))
        exported.append(
            {
                "asset_key": asset_key,
                "name": str(automatic.get("name") or Path(asset_key).name),
                "size": int(automatic.get("size") or 0),
                "manual_category": str(annotation.get("category") or ""),
                "automatic_category": str(automatic.get("automatic_kind") or automatic.get("kind") or ""),
                "automatic_confidence": str(automatic.get("automatic_classification_confidence") or ""),
                "automatic_source": str(automatic.get("automatic_classification_source") or ""),
                "notes": str(annotation.get("notes") or ""),
                "flagged": bool(annotation.get("flagged", False)),
                "last_report": str(annotation.get("last_report") or ""),
                "default_animation": str(annotation.get("default_animation") or ""),
                "default_frame": max(0, int(annotation.get("default_frame") or 0)),
                "camera_saved": camera_saved,
                "camera_yaw": annotation.get("camera_yaw") if camera_saved else "",
                "camera_pitch": annotation.get("camera_pitch") if camera_saved else "",
                "camera_zoom": annotation.get("camera_zoom") if camera_saved else "",
                "camera_pan_x": annotation.get("camera_pan_x") if camera_saved else "",
                "camera_pan_y": annotation.get("camera_pan_y") if camera_saved else "",
                "camera_background": str(annotation.get("camera_background") or "") if camera_saved else "",
                "camera_basis": list(annotation.get("camera_basis") or []) if camera_saved else [],
            }
        )

    reports = project.workspace_path("reports") / "visual_classifications"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    json_path = reports / "visual_classifications_latest.json"
    csv_path = reports / "visual_classifications_latest.csv"
    zip_path = reports / f"visual_classifications_{stamp}.zip"
    payload = {
        "format": "Fragmenter visual classification ledger v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workspace": str(Path(project.workspace_dir).expanduser()),
        "record_count": len(exported),
        "records": exported,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = (
        "asset_key",
        "name",
        "size",
        "manual_category",
        "automatic_category",
        "automatic_confidence",
        "automatic_source",
        "notes",
        "flagged",
        "last_report",
        "default_animation",
        "default_frame",
        "camera_saved",
        "camera_yaw",
        "camera_pitch",
        "camera_zoom",
        "camera_pan_x",
        "camera_pan_y",
        "camera_background",
        "camera_basis",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in exported:
            csv_row = {key: row.get(key) for key in fields}
            csv_row["camera_basis"] = json.dumps(row.get("camera_basis") or [])
            writer.writerow(csv_row)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(json_path, json_path.name)
        archive.write(csv_path, csv_path.name)
    return {
        "record_count": len(exported),
        "notes_count": sum(bool(str(row.get("notes") or "").strip()) for row in exported),
        "camera_count": sum(bool(row.get("camera_saved")) for row in exported),
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "zip_path": str(zip_path),
    }

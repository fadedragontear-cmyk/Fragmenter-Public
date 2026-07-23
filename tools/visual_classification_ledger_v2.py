#!/usr/bin/env python3
"""Portable classification ledger including camera state and readable review notes."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

import visual_classification_ledger_v1 as base
from visual_asset_annotations_v1 import annotation_records


def _position(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return []
    try:
        return [float(component) for component in value]
    except (TypeError, ValueError):
        return []


def _review_notes_markdown(exported: list[dict[str, Any]], generated_at: str) -> str:
    notes = [row for row in exported if str(row.get("notes") or "").strip()]
    flagged = [row for row in exported if bool(row.get("flagged"))]
    categorized = [row for row in exported if str(row.get("manual_category") or "").strip()]
    lines = [
        "# Fragmenter visual review notes",
        "",
        f"Generated: {generated_at}",
        f"Records: {len(exported)}",
        f"Manual classifications: {len(categorized)}",
        f"Assets with notes: {len(notes)}",
        f"Flagged reports: {len(flagged)}",
        "",
        "This file is the human-readable companion to the JSON and CSV ledgers.",
        "",
    ]
    review_rows = [
        row
        for row in exported
        if str(row.get("notes") or "").strip() or bool(row.get("flagged"))
    ]
    if not review_rows:
        lines.extend(["No notes or flagged reports were recorded.", ""])
        return "\n".join(lines)
    for row in review_rows:
        lines.extend(
            [
                f"## {row.get('asset_key') or row.get('name') or 'Unknown asset'}",
                "",
                f"- Classification: {row.get('manual_category') or row.get('automatic_category') or 'Unclassified'}",
                f"- Flagged: {'yes' if row.get('flagged') else 'no'}",
            ]
        )
        if row.get("last_report"):
            lines.append(f"- Report: {row['last_report']}")
        note = str(row.get("notes") or "").strip()
        if note:
            lines.extend(["", "### Notes", "", note])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_visual_classification_ledger(project, rows: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    indexed = base._row_index(rows)
    records = annotation_records(project)
    exported: list[dict[str, Any]] = []
    for asset_key, annotation in sorted(records.items(), key=lambda item: item[0].casefold()):
        automatic = indexed.get(asset_key, {})
        camera_saved = bool(annotation.get("camera_saved", False))
        position = _position(annotation.get("camera_position")) if camera_saved else []
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
                "camera_position": position,
                "camera_position_x": position[0] if position else "",
                "camera_position_y": position[1] if position else "",
                "camera_position_z": position[2] if position else "",
            }
        )

    reports = project.workspace_path("visual_reports") / "classifications"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = base._stamp()
    json_path = reports / "visual_classifications_latest.json"
    csv_path = reports / "visual_classifications_latest.csv"
    notes_path = reports / "visual_review_notes_latest.md"
    zip_path = reports / f"visual_classifications_{stamp}.zip"
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    notes_count = sum(bool(str(row.get("notes") or "").strip()) for row in exported)
    flagged_count = sum(bool(row.get("flagged")) for row in exported)
    category_count = sum(bool(str(row.get("manual_category") or "").strip()) for row in exported)
    camera_count = sum(bool(row.get("camera_saved")) for row in exported)
    payload = {
        "format": "Fragmenter visual classification ledger v2",
        "generated_at": generated_at,
        "workspace": str(Path(project.workspace_dir).expanduser()),
        "record_count": len(exported),
        "manual_classification_count": category_count,
        "notes_count": notes_count,
        "flagged_count": flagged_count,
        "camera_count": camera_count,
        "records": exported,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    notes_path.write_text(_review_notes_markdown(exported, generated_at), encoding="utf-8")
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
        "camera_position",
        "camera_position_x",
        "camera_position_y",
        "camera_position_z",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in exported:
            csv_row = {key: row.get(key) for key in fields}
            csv_row["camera_basis"] = json.dumps(row.get("camera_basis") or [])
            csv_row["camera_position"] = json.dumps(row.get("camera_position") or [])
            writer.writerow(csv_row)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(json_path, json_path.name)
        archive.write(csv_path, csv_path.name)
        archive.write(notes_path, notes_path.name)
    return {
        "record_count": len(exported),
        "manual_classification_count": category_count,
        "notes_count": notes_count,
        "flagged_count": flagged_count,
        "camera_count": camera_count,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "notes_path": str(notes_path),
        "zip_path": str(zip_path),
    }


def install() -> None:
    base.export_visual_classification_ledger = export_visual_classification_ledger


install()

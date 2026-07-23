#!/usr/bin/env python3
"""Per-part Gen1 CCSF animation/puppetry inspection and export."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ccsf_gen1_pose_v6 as pose_v6


def _track_summary(track: dict[str, Any]) -> dict[str, Any]:
    keys = list(track.get("keys") or [])
    return {
        "status": str(track.get("status") or ""),
        "key_count": int(track.get("key_count") or len(keys)),
        "key_frames": [int(key.get("frame") or 0) for key in keys],
        "fixed": track.get("fixed"),
        "keys": [
            {"frame": int(key.get("frame") or 0), "value": key.get("value")}
            for key in keys
        ],
    }


def controller_catalog(parsed: Any) -> list[dict[str, Any]]:
    """Describe every object controller and the individual part it drives."""
    catalog: list[dict[str, Any]] = []
    for animation in parsed.animations:
        animation_name = str(animation.get("object_name") or animation.get("object_id") or "")
        for controller_index, controller in enumerate(animation.get("controllers") or []):
            target_id = controller.get("target_object_id")
            target = parsed.objects.get(target_id) if isinstance(target_id, int) else None
            parent_id = int((target or {}).get("parent_object_id") or 0)
            membership = parsed.clump_by_object.get(target_id) if isinstance(target_id, int) else None
            clump = membership.get("clump") if isinstance(membership, dict) else None
            tracks = controller.get("tracks") or {}
            catalog.append(
                {
                    "animation_id": animation.get("object_id"),
                    "animation_name": animation_name,
                    "frame_count": int(animation.get("frame_count") or 0),
                    "playback_name": animation.get("playback_name"),
                    "controller_index": controller_index,
                    "external_id": controller.get("external_id"),
                    "external_name": controller.get("external_name"),
                    "target_object_id": target_id,
                    "target_object_name": str(controller.get("target_object_name") or ""),
                    "parent_object_id": parent_id,
                    "parent_object_name": str((parsed.report.object_lookup.get(parent_id) or {}).get("name") or "") if parent_id else "",
                    "clump_id": int((clump or {}).get("object_id") or 0),
                    "clump_name": str((clump or {}).get("object_name") or ""),
                    "clump_node_index": membership.get("node_index") if isinstance(membership, dict) else None,
                    "model_id": int((target or {}).get("model_id") or 0),
                    "model_name": str((parsed.report.object_lookup.get(int((target or {}).get("model_id") or 0)) or {}).get("name") or ""),
                    "tracks": {
                        name: _track_summary(track)
                        for name, track in tracks.items()
                        if isinstance(track, dict)
                    },
                    "rotation_storage": "Euler float3, axis-fixed and converted to radians",
                    "rotation_pipeline": pose_v6.ROTATION_PIPELINE,
                }
            )
    return catalog


def build_puppetry_report(path: str | Path, *, frame: int = 0) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    parsed = pose_v6.load_pose_source(source)
    catalog = controller_catalog(parsed)
    animations: list[dict[str, Any]] = []
    for animation in parsed.animations:
        name = str(animation.get("object_name") or animation.get("object_id") or "")
        frame_count = max(1, int(animation.get("frame_count") or 1))
        selected_frame = max(0, int(frame)) % frame_count
        context = pose_v6.build_pose_context(source, animation_name=name, frame=selected_frame)
        animations.append(
            {
                "object_id": animation.get("object_id"),
                "object_name": name,
                "frame_count": int(animation.get("frame_count") or 0),
                "playback_name": animation.get("playback_name"),
                "pose_ready": bool(animation.get("pose_ready")),
                "controller_count": int(animation.get("controller_count") or 0),
                "evaluated_frame": selected_frame,
                "controlled_parts": pose_v6.puppetry_rows(context),
                "warnings": list(animation.get("warnings") or []),
            }
        )
    controlled_ids = {
        int(row["target_object_id"])
        for row in catalog
        if isinstance(row.get("target_object_id"), int)
    }
    return {
        "version": 1,
        "format": "Fragmenter Gen1 Euler axis-angle puppetry report",
        "source": str(source),
        "generation": str(parsed.report.header.get("generation") or "Unknown"),
        "rotation_storage": "Euler float3, axis-fixed and converted to radians",
        "rotation_pipeline": pose_v6.ROTATION_PIPELINE,
        "rotation_quaternion_used": False,
        "controller_catalog": catalog,
        "animations": animations,
        "warnings": list(parsed.warnings),
        "summary": {
            "animation_records": len(parsed.animations),
            "pose_ready_animations": sum(bool(row.get("pose_ready")) for row in parsed.animations),
            "controller_bindings": len(catalog),
            "controlled_objects": len(controlled_ids),
            "clumps_with_controllers": len({int(row["clump_id"]) for row in catalog if int(row.get("clump_id") or 0)}),
            "unresolved_controller_targets": sum(not isinstance(row.get("target_object_id"), int) for row in catalog),
            "playback_ready": sum(bool(row.get("pose_ready")) for row in parsed.animations),
        },
    }


def export_puppetry_report(path: str | Path, output_dir: str | Path, *, frame: int = 0) -> dict[str, Any]:
    report = build_puppetry_report(path, frame=frame)
    output = Path(output_dir).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "animation_puppetry.json"
    legacy_path = output / "animation_metadata.json"
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path.write_text(text, encoding="utf-8")
    # Keep the established filename so the existing Animation Metadata action opens
    # the complete puppetry report without requiring another GUI button.
    legacy_path.write_text(text, encoding="utf-8")
    report["report_path"] = str(report_path)
    report["legacy_report_path"] = str(legacy_path)
    return report

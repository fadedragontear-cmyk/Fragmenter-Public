#!/usr/bin/env python3
"""Canonical project catalog/report writers used by Fragmenter 1.0 RUN ALL."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_preflight_v1 import resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1, sha256_file
from server_explorer_controller_v1 import server_explorer_view_model


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def build_visual_catalogs(project: FragmenterProjectV1) -> dict[str, Any]:
    paths = resolve_runtime_paths(project)
    library_path = paths.reports / "asset_library.json"
    if not library_path.is_file():
        raise FileNotFoundError(library_path)
    library = _load_json(library_path)
    assets = library.get("assets") if isinstance(library.get("assets"), list) else []
    textures: list[dict[str, Any]] = []
    animations: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            continue
        counts = asset.get("resource_counts") if isinstance(asset.get("resource_counts"), dict) else {}
        file_value = str(asset.get("preferred_file") or asset.get("relative_file") or asset.get("file") or "")
        base = {
            "asset_index": index,
            "name": str(asset.get("display_name") or asset.get("name") or Path(file_value).stem),
            "type": str(asset.get("type") or "unknown"),
            "variant": str(asset.get("variant") or ""),
            "readiness": str(asset.get("readiness") or "unknown"),
            "file": file_value,
        }
        tex_count = int(counts.get("TEX", 0) or 0)
        clt_count = int(counts.get("CLT", 0) or 0)
        anm_count = int(counts.get("ANM", 0) or 0)
        if tex_count or clt_count:
            textures.append(
                {
                    **base,
                    "tex_count": tex_count,
                    "clt_count": clt_count,
                    "status": "inspect asset to enumerate TEX/CLT",
                    "decoded_png_count": 0,
                }
            )
        if anm_count:
            animations.append(
                {
                    **base,
                    "animation_count": anm_count,
                    "status": "inspect asset to parse animation metadata",
                    "playback_ready": False,
                }
            )
    texture_report = {
        "version": 1,
        "created_at": _utc_iso(),
        "asset_library": str(library_path),
        "assets": textures,
        "summary": {
            "texture_capable_assets": len(textures),
            "tex_records": sum(row["tex_count"] for row in textures),
            "clt_records": sum(row["clt_count"] for row in textures),
        },
    }
    animation_report = {
        "version": 1,
        "created_at": _utc_iso(),
        "asset_library": str(library_path),
        "assets": animations,
        "summary": {
            "animation_capable_assets": len(animations),
            "animation_records": sum(row["animation_count"] for row in animations),
            "playback_ready_assets": 0,
        },
    }
    visual_reports = project.workspace_path("visual_reports")
    texture_path = _atomic_json(visual_reports / "texture_catalog.json", texture_report)
    animation_path = _atomic_json(visual_reports / "animation_catalog.json", animation_report)
    return {
        "texture_catalog": str(texture_path),
        "animation_catalog": str(animation_path),
        "texture_assets": len(textures),
        "animation_assets": len(animations),
    }


def write_server_index(project: FragmenterProjectV1) -> Path:
    model = server_explorer_view_model(project)
    payload = {"version": 1, "created_at": _utc_iso(), **model}
    return _atomic_json(project.workspace_path("server_reports") / "server_index.json", payload)


def write_server_save_index(project: FragmenterProjectV1) -> Path:
    paths = resolve_runtime_paths(project)
    root = paths.server_saves
    rows: list[dict[str, Any]] = []
    if root.is_dir():
        for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p).lower()):
            stat = path.stat()
            rows.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "path": str(path),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
    payload = {
        "version": 1,
        "created_at": _utc_iso(),
        "root": str(root),
        "exists": root.is_dir(),
        "file_count": len(rows),
        "files": rows,
        "editing_supported": False,
    }
    return _atomic_json(project.workspace_path("server_reports") / "server_save_index.json", payload)


def write_memory_card_identity(project: FragmenterProjectV1) -> Path:
    paths = resolve_runtime_paths(project)
    card = paths.memory_card
    if not card.is_file():
        payload = {
            "version": 1,
            "created_at": _utc_iso(),
            "path": str(card),
            "exists": False,
            "editing_supported": False,
            "backup_mode": "whole_file",
        }
    else:
        stat = card.stat()
        payload = {
            "version": 1,
            "created_at": _utc_iso(),
            "path": str(card),
            "exists": True,
            "name": card.name,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": sha256_file(card),
            "editing_supported": False,
            "backup_mode": "whole_file",
        }
    return _atomic_json(project.workspace_path("server_reports") / "memory_card_identity.json", payload)


def write_audio_library(project: FragmenterProjectV1) -> Path:
    paths = resolve_runtime_paths(project)
    audio_reports = project.workspace_path("audio_reports")
    candidates = [
        audio_reports / "sound_decode_report.json",
        audio_reports / "audio_decode_report.json",
        paths.reports / "audio_decode_report.json",
        paths.media_pipeline / "reports" / "audio_decode_report.json",
        paths.media_pipeline / "reports" / "iso_media_decode.json",
    ]
    source_report = next((path for path in candidates if path.is_file()), None)
    decoded_wavs = (
        sorted((path for path in paths.extracted_audio.rglob("*.wav") if path.is_file()), key=lambda p: str(p).lower())
        if paths.extracted_audio.is_dir()
        else []
    )
    rows = []
    for path in decoded_wavs:
        stat = path.stat()
        rows.append(
            {
                "name": path.name,
                "path": str(path),
                "relative_path": path.relative_to(paths.extracted_audio).as_posix(),
                "type": "CONFIRMED WAV",
                "size": stat.st_size,
                "status": "playable",
            }
        )
    payload = {
        "version": 2,
        "created_at": _utc_iso(),
        "source_report": str(source_report) if source_report else None,
        "items": rows,
        "summary": {"confirmed_wavs": len(rows)},
    }
    return _atomic_json(audio_reports / "audio_library.json", payload)


def write_scan_summary(project: FragmenterProjectV1, stage_results: list[dict[str, Any]]) -> tuple[Path, Path]:
    paths = resolve_runtime_paths(project)
    payload = {
        "version": 2,
        "created_at": _utc_iso(),
        "workspace": str(paths.workspace),
        "project_file": str(paths.project_file),
        "stages": stage_results,
        "summary": {
            "complete": sum(1 for row in stage_results if row.get("status") == "complete"),
            "reused": sum(1 for row in stage_results if row.get("status") == "reused"),
            "failed": sum(1 for row in stage_results if row.get("status") == "failed"),
            "cancelled": sum(1 for row in stage_results if row.get("status") == "cancelled"),
        },
    }
    run_reports = project.workspace_path("run_reports")
    json_path = _atomic_json(run_reports / "scan_summary.json", payload)
    lines = ["Fragmenter RUN ALL Summary", "==========================", ""]
    for row in stage_results:
        lines.append(f"{row.get('label') or row.get('key')}: {row.get('status')}")
        message = str(row.get("message") or "").strip()
        if message:
            lines.append(f"  {message}")
    text_path = run_reports / "scan_summary.txt"
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, text_path

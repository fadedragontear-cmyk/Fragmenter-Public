#!/usr/bin/env python3
"""Non-destructive migration for Fragmenter report layout v2.

The workspace has one report root. This module moves older loose reports into
purpose-specific folders and repairs retained report references after legacy output
trees have been moved to their canonical locations.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_FILE_GROUPS: dict[str, tuple[str, ...]] = {
    "run_all": (
        "project_status.json",
        "project_status.txt",
        "scan_summary.json",
        "scan_summary.txt",
        "pipeline_last.json",
        "run_all_report.json",
    ),
    "visual": (
        "texture_catalog.json",
        "animation_catalog.json",
        "ccsf_asset_index.json",
        "ccsf_asset_index.txt",
        "ccsf_results_dashboard.html",
        "asset_library_dashboard.html",
    ),
    "audio": (
        "audio_library.json",
        "audio_decode_report.json",
        "sound_source_manifest.json",
        "sound_decode_report.json",
        "sound_library.json",
        "snddata_summary.json",
        "snddata_music_system_v5.json",
        "snddata_pipeline_summary_v5.json",
    ),
    "server": (
        "server_index.json",
        "server_save_index.json",
        "memory_card_identity.json",
    ),
}

TEXT_REPORT_SUFFIXES = {".json", ".jsonl", ".txt", ".csv", ".html", ".md"}
PATH_REWRITE_EXCLUDES = {"workspace_layout.json", "report_layout.json", "path_rewrite.json"}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _same_file(left: Path, right: Path) -> bool:
    return left.is_file() and right.is_file() and left.stat().st_size == right.stat().st_size and _sha256(left) == _sha256(right)


def _conflict_path(target: Path) -> Path:
    index = 1
    while True:
        candidate = target.with_name(f"{target.name}.legacy{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _move_file(source: Path, target: Path, group: str) -> dict[str, Any] | None:
    if not source.is_file() or source.resolve() == target.resolve():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if _same_file(source, target):
            source.unlink()
            return {"group": group, "source": str(source), "target": str(target), "status": "deduplicated"}
        conflict = _conflict_path(target)
        shutil.move(str(source), str(conflict))
        return {"group": group, "source": str(source), "target": str(conflict), "status": "preserved_conflict"}
    shutil.move(str(source), str(target))
    return {"group": group, "source": str(source), "target": str(target), "status": "moved"}


def _merge_directory(source: Path, target: Path, group: str, actions: list[dict[str, Any]]) -> None:
    if not source.is_dir() or source.resolve() == target.resolve():
        return
    for path in sorted((item for item in source.rglob("*") if item.is_file()), key=lambda item: item.relative_to(source).as_posix().casefold()):
        row = _move_file(path, target / path.relative_to(source), group)
        if row:
            actions.append(row)
    for path in sorted((item for item in source.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    try:
        source.rmdir()
    except OSError:
        pass


def _replacement_pairs(workspace: Path) -> list[tuple[str, str]]:
    roots = (
        (workspace / "extracted_ccs", workspace / "extracted" / "ccsf"),
        (workspace / "sound" / "source", workspace / "extracted" / "audio"),
        (workspace / "sound" / "decoded", workspace / "decoded" / "audio"),
        (workspace / "sound" / "work", workspace / "work" / "audio"),
        (workspace / "sound" / "reports", workspace / "reports" / "audio"),
        (workspace / "media_pipeline" / "decoded" / "textures", workspace / "decoded" / "textures"),
        (workspace / "media_pipeline" / "decoded" / "audio", workspace / "decoded" / "audio" / "legacy_media_pipeline"),
        (workspace / "reports" / "visual_flags", workspace / "reports" / "visual" / "flags"),
        (workspace / "reports" / "visual_classifications", workspace / "reports" / "visual" / "classifications"),
    )
    pairs: list[tuple[str, str]] = []
    for old, new in roots:
        old_text = str(old)
        new_text = str(new)
        pairs.extend(
            [
                (old_text, new_text),
                (old_text.replace("\\", "/"), new_text.replace("\\", "/")),
                (old_text.replace("\\", "\\\\"), new_text.replace("\\", "\\\\")),
            ]
        )
    pairs.extend(
        [
            ("extracted_ccs/", "extracted/ccsf/"),
            ("extracted_ccs\\", "extracted\\ccsf\\"),
            ("extracted_ccs\\\\", "extracted\\\\ccsf\\\\"),
            ("sound/source/", "extracted/audio/"),
            ("sound\\source\\", "extracted\\audio\\"),
            ("sound\\\\source\\\\", "extracted\\\\audio\\\\"),
            ("sound/decoded/", "decoded/audio/"),
            ("sound\\decoded\\", "decoded\\audio\\"),
            ("sound\\\\decoded\\\\", "decoded\\\\audio\\\\"),
            ("reports/visual_flags/", "reports/visual/flags/"),
            ("reports\\visual_flags\\", "reports\\visual\\flags\\"),
            ("reports\\\\visual_flags\\\\", "reports\\\\visual\\\\flags\\\\"),
            ("reports/visual_classifications/", "reports/visual/classifications/"),
            ("reports\\visual_classifications\\", "reports\\visual\\classifications\\"),
            ("reports\\\\visual_classifications\\\\", "reports\\\\visual\\\\classifications\\\\"),
        ]
    )
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return pairs


def rewrite_legacy_output_references(workspace_or_project: str | Path | Any) -> dict[str, Any]:
    """Rewrite stale legacy output paths inside retained text reports."""
    workspace = Path(workspace_or_project.workspace_dir).expanduser() if hasattr(workspace_or_project, "workspace_dir") else Path(workspace_or_project).expanduser()
    pairs = _replacement_pairs(workspace)
    roots = [workspace / "reports", workspace / "review"]
    changed: list[dict[str, Any]] = []
    scanned = 0
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: str(item).casefold()):
            if path.name in PATH_REWRITE_EXCLUDES or path.suffix.lower() not in TEXT_REPORT_SUFFIXES:
                continue
            scanned += 1
            try:
                original = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            updated = original
            replacements = 0
            for old, new in pairs:
                count = updated.count(old)
                if count:
                    updated = updated.replace(old, new)
                    replacements += count
            if updated == original:
                continue
            temp = path.with_name(path.name + ".tmp")
            temp.write_text(updated, encoding="utf-8")
            os.replace(temp, path)
            changed.append({"path": str(path), "replacements": replacements})
    return {
        "version": 1,
        "created_at": _utc_iso(),
        "workspace": str(workspace),
        "files_scanned": scanned,
        "files_changed": len(changed),
        "replacements": sum(row["replacements"] for row in changed),
        "changed_files": changed,
    }


def migrate_report_layout(workspace_or_project: str | Path | Any) -> dict[str, Any]:
    if hasattr(workspace_or_project, "workspace_dir"):
        workspace = Path(workspace_or_project.workspace_dir).expanduser()
    else:
        workspace = Path(workspace_or_project).expanduser()
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    actions: list[dict[str, Any]] = []

    for group, filenames in REPORT_FILE_GROUPS.items():
        target_root = reports / group
        target_root.mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            row = _move_file(reports / filename, target_root / filename, group)
            if row:
                actions.append(row)

    _merge_directory(reports / "visual_classifications", reports / "visual" / "classifications", "visual_classifications", actions)
    _merge_directory(reports / "visual_flags", reports / "visual" / "flags", "visual_flags", actions)

    for group in ("run_all", "visual", "audio", "server", "diagnostics"):
        (reports / group).mkdir(parents=True, exist_ok=True)

    path_rewrite = rewrite_legacy_output_references(workspace)
    rewrite_path = reports / "run_all" / "path_rewrite.json"
    rewrite_temp = rewrite_path.with_name(rewrite_path.name + ".tmp")
    rewrite_temp.write_text(json.dumps(path_rewrite, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(rewrite_temp, rewrite_path)

    payload = {
        "version": 1,
        "created_at": _utc_iso(),
        "workspace": str(workspace),
        "report_root": str(reports),
        "groups": ["run_all", "visual", "audio", "server", "diagnostics"],
        "actions": actions,
        "path_rewrite": {**path_rewrite, "report_path": str(rewrite_path)},
        "summary": {
            "actions": len(actions),
            "moved": sum(row["status"] == "moved" for row in actions),
            "deduplicated": sum(row["status"] == "deduplicated" for row in actions),
            "preserved_conflicts": sum(row["status"] == "preserved_conflict" for row in actions),
            "reference_files_rewritten": path_rewrite["files_changed"],
            "path_replacements": path_rewrite["replacements"],
        },
    }
    target = reports / "run_all" / "report_layout.json"
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    payload["report_path"] = str(target)
    return payload

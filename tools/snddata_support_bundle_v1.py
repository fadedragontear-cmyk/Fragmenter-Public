#!/usr/bin/env python3
"""Create a reports-only SNDDATA support bundle for remote review.

The bundle deliberately excludes ISO data, SNDDATA binaries, extracted ADPCM, WAVs,
and other large/generated media. It refreshes the readiness audit, then packages the
small reports needed to reproduce the current parser/extractor/reconstruction status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_workspace_v1 import FragmenterProjectV1, load_project
from snddata_reconstruction_readiness_v1 import audit_project, project_paths

BUNDLE_VERSION = 1
MAX_REPORT_BYTES = 32 * 1024 * 1024
LATEST_POINTER = "snddata_support_bundle_latest.json"

REPORT_NAMES = (
    "snddata_reconstruction_readiness_v1.json",
    "snddata_reconstruction_readiness_v1.txt",
    "snddata_sample_library.json",
    "snddata_sample_library.csv",
    "snddata_sample_flat_catalog.json",
    "snddata_sample_flat_catalog.csv",
    "snddata_music_system_v5.json",
    "snddata_pipeline_summary_v5.json",
    "music_preview_last_v5.json",
    "snddata_forensics_v1.json",
    "snddata_forensics_v1.txt",
    "snddata_noop_roundtrip_proof_v1.json",
    "snddata_noop_patch_manifest.json",
    "snddata_noop_patch_manifest.txt",
    "snddata_container_map.json",
    "snddata_container_map.txt",
    "snddata_music_graph.json",
    "snddata_music_graph.txt",
    "sound_source_manifest.json",
    "sound_decode_report.json",
    "sound_library.json",
)


def _utc_stamp() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z"), now.strftime("%Y%m%d_%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_reports(project: FragmenterProjectV1) -> list[Path]:
    paths = project_paths(project)
    reports = paths["reports"]
    candidates = [reports / name for name in REPORT_NAMES]

    # Keep compatibility with reports written by older pipeline layouts.
    workspace = Path(project.workspace_dir).expanduser()
    legacy_roots = (
        workspace / "reports",
        workspace / "reports" / "legacy_media_pipeline",
        workspace / "work" / "legacy_media_pipeline" / "reports",
    )
    for root in legacy_roots:
        for name in REPORT_NAMES:
            candidates.append(root / name)

    selected: dict[str, Path] = {}
    for path in candidates:
        if not path.is_file():
            continue
        key = path.name.casefold()
        current = selected.get(key)
        if current is None or path.stat().st_mtime_ns > current.stat().st_mtime_ns:
            selected[key] = path
    return [selected[key] for key in sorted(selected)]


def build_support_bundle(
    project: FragmenterProjectV1,
    *,
    parse_source: bool = True,
    max_report_bytes: int = MAX_REPORT_BYTES,
) -> dict[str, Any]:
    """Refresh the readiness audit and write a small, shareable ZIP."""
    audit = audit_project(project, parse_source=parse_source, write=True)
    paths = project_paths(project)
    reports = paths["reports"]
    reports.mkdir(parents=True, exist_ok=True)
    created_at, stamp = _utc_stamp()
    target = reports / f"fragmenter_snddata_support_{stamp}.zip"

    included: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    files = _candidate_reports(project)

    readme = (
        "Fragmenter SNDDATA support bundle\n"
        "=================================\n\n"
        "Send this ZIP back with a short note describing what you clicked, what you heard, "
        "and any visible error. The archive contains reports only. It does not contain the "
        "game ISO, snddata.bin, WAVs, extracted CCSF, memory cards, or server files.\n\n"
        "Primary report: reports/snddata_reconstruction_readiness_v1.txt\n"
    )

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("README_SEND_THIS_ZIP.txt", readme)
        for path in files:
            size = path.stat().st_size
            if size > int(max_report_bytes):
                skipped.append(
                    {
                        "path": str(path),
                        "reason": "report_exceeds_size_limit",
                        "size": size,
                        "limit": int(max_report_bytes),
                    }
                )
                continue
            arcname = f"reports/{path.name}"
            archive.write(path, arcname)
            included.append(
                {
                    "path": str(path),
                    "archive_path": arcname,
                    "size": size,
                    "sha256": _sha256(path),
                }
            )

        manifest = {
            "version": BUNDLE_VERSION,
            "created_at": created_at,
            "project_file_name": Path(project.project_path).name,
            "workspace_name": Path(project.workspace_dir).expanduser().name,
            "source": {
                "present": bool((audit.get("source") or {}).get("exists")),
                "size": int((audit.get("source") or {}).get("size") or 0),
                "sha256": str((audit.get("source") or {}).get("sha256") or ""),
            },
            "readiness": dict(audit.get("readiness") or {}),
            "included": included,
            "skipped": skipped,
            "privacy_scope": "reports_only_no_game_binaries_no_audio_media_no_extracted_ccsf",
        }
        archive.writestr(
            "support_bundle_manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )

    result = {
        "version": BUNDLE_VERSION,
        "created_at": created_at,
        "bundle_path": str(target),
        "bundle_size": target.stat().st_size,
        "included_reports": len(included),
        "skipped_reports": len(skipped),
        "readiness": dict(audit.get("readiness") or {}),
        "manifest": manifest,
    }
    pointer = reports / LATEST_POINTER
    pointer.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["pointer_path"] = str(pointer)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="Fragmenter project.json or workspace folder")
    parser.add_argument("--no-parse", action="store_true", help="Reuse reports without reparsing snddata.bin")
    args = parser.parse_args(argv)
    project = load_project(args.project)
    result = build_support_bundle(project, parse_source=not args.no_parse)
    print(result["bundle_path"])
    print(f"included reports: {result['included_reports']}")
    print(f"bundle bytes: {result['bundle_size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

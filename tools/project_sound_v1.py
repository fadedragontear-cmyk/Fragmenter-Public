#!/usr/bin/env python3
"""Canonical project-bound sound extraction and decode workspace.

All public audio now shares the project layout authority:
``extracted/audio`` stores ISO source files, ``decoded/audio`` stores WAVs,
``work/audio`` stores temporary data, and ``reports/audio`` stores reports.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import audio_decoder
import scei_hd_bd
from iso9660 import Iso9660, normalize_path
from project_preflight_v1 import require_ready_project
from project_workspace_v1 import FragmenterProjectV1

EXTRA_EXACT_PATHS = {"data/snddata.bin", "netgui/eff.hd", "netgui/eff.bd"}
SOUND_PREFIX = "sound/"
MANIFEST_NAME = "sound_source_manifest.json"
DECODE_REPORT_NAME = "sound_decode_report.json"
LIBRARY_NAME = "sound_library.json"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sound_root(project: FragmenterProjectV1) -> Path:
    """Return the canonical decoded-audio root retained for compatibility."""
    require_ready_project(project)
    root = project.workspace_path("extracted_audio")
    root.mkdir(parents=True, exist_ok=True)
    return root


def sound_source_root(project: FragmenterProjectV1) -> Path:
    require_ready_project(project)
    path = project.workspace_path("audio_source")
    path.mkdir(parents=True, exist_ok=True)
    return path


def sound_decoded_root(project: FragmenterProjectV1) -> Path:
    require_ready_project(project)
    path = project.workspace_path("extracted_audio")
    path.mkdir(parents=True, exist_ok=True)
    return path


def sound_reports_root(project: FragmenterProjectV1) -> Path:
    require_ready_project(project)
    path = project.workspace_path("audio_reports")
    path.mkdir(parents=True, exist_ok=True)
    return path


def sound_work_root(project: FragmenterProjectV1) -> Path:
    require_ready_project(project)
    path = project.workspace_path("audio_work")
    path.mkdir(parents=True, exist_ok=True)
    return path


def canonical_snddata_path(project: FragmenterProjectV1) -> Path:
    return sound_source_root(project) / "data" / "snddata.bin"


def _atomic_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def _load_iso_index(project: FragmenterProjectV1) -> dict[str, Any]:
    paths = require_ready_project(project)
    index = paths.cache_iso / "iso_index.json"
    if not index.is_file():
        raise FileNotFoundError(f"ISO index is missing: {index}; run Index ISO Filesystem first")
    payload = json.loads(index.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ValueError(f"Invalid ISO index: {index}")
    return payload


def discover_sound_sources(project: FragmenterProjectV1) -> dict[str, Any]:
    payload = _load_iso_index(project)
    rows: list[dict[str, Any]] = []
    for item in payload.get("files") or []:
        if not isinstance(item, dict) or item.get("is_dir"):
            continue
        normalized = normalize_path(item.get("path"))
        if not normalized:
            continue
        if normalized.startswith(SOUND_PREFIX) or normalized in EXTRA_EXACT_PATHS:
            rows.append(
                {
                    "iso_path": normalized,
                    "lba": int(item.get("lba") or 0),
                    "size": int(item.get("size") or 0),
                    "category": "sound_directory" if normalized.startswith(SOUND_PREFIX) else "known_audio_system_file",
                }
            )
    rows.sort(key=lambda row: row["iso_path"])
    return {
        "version": 1,
        "iso": str(require_ready_project(project).iso),
        "discovered_at": _utc_iso(),
        "sources": rows,
        "summary": {
            "sources": len(rows),
            "sound_directory_files": sum(1 for row in rows if row["category"] == "sound_directory"),
            "known_audio_system_files": sum(1 for row in rows if row["category"] == "known_audio_system_file"),
            "snddata_found": any(row["iso_path"] == "data/snddata.bin" for row in rows),
            "eff_hd_found": any(row["iso_path"] == "netgui/eff.hd" for row in rows),
            "eff_bd_found": any(row["iso_path"] == "netgui/eff.bd" for row in rows),
        },
    }


def _extract_indexed_entry(iso: Iso9660, iso_file, row: dict[str, Any], target: Path) -> None:
    remaining = int(row["size"])
    current_lba = int(row["lba"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    with temp.open("wb") as output:
        while remaining > 0:
            take = 2048 if remaining >= 2048 else remaining
            chunk = iso._read_user(iso_file, current_lba, take)
            if len(chunk) != take:
                raise IOError(f"short ISO read for {row['iso_path']} at LBA {current_lba}: expected {take}, got {len(chunk)}")
            output.write(chunk)
            remaining -= len(chunk)
            current_lba += 1
    if temp.stat().st_size != int(row["size"]):
        temp.unlink(missing_ok=True)
        raise IOError(f"extracted size mismatch for {row['iso_path']}")
    os.replace(temp, target)


def extract_project_sound_sources(
    project: FragmenterProjectV1,
    *,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    paths = require_ready_project(project)
    discovery = discover_sound_sources(project)
    source_root = sound_source_root(project)
    iso = Iso9660(paths.iso).open()
    results: list[dict[str, Any]] = []
    total = len(discovery["sources"])
    with paths.iso.open("rb") as iso_file:
        for index, row in enumerate(discovery["sources"], 1):
            target = source_root / Path(*row["iso_path"].split("/"))
            status = "reused" if reuse and target.is_file() and target.stat().st_size == int(row["size"]) else "extracted"
            error = None
            try:
                if status == "extracted":
                    _extract_indexed_entry(iso, iso_file, row, target)
            except Exception as exc:
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
            result = {**row, "target": str(target), "status": status, "error": error}
            results.append(result)
            if callback is not None:
                callback({"kind": "sound_extract_progress", "current": index, "total": total, "iso_path": row["iso_path"], "status": status})

    manifest = {
        "version": 1,
        "created_at": _utc_iso(),
        "iso": str(paths.iso),
        "source_root": str(source_root),
        "sources": results,
        "summary": {
            **discovery["summary"],
            "extracted": sum(1 for row in results if row["status"] == "extracted"),
            "reused": sum(1 for row in results if row["status"] == "reused"),
            "errors": sum(1 for row in results if row["status"] == "error"),
        },
    }
    manifest_path = _atomic_json(sound_reports_root(project) / MANIFEST_NAME, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _decode_gzip(source: Path, work_root: Path, decoded_root: Path, relative: Path) -> list[dict[str, Any]]:
    unpacked = work_root / "gzip" / relative.with_suffix("")
    unpacked.parent.mkdir(parents=True, exist_ok=True)
    try:
        unpacked.write_bytes(gzip.decompress(source.read_bytes()))
    except Exception as exc:
        return [{"source": str(source), "relative_path": relative.as_posix(), "action": "gzip_decompress", "status": "error", "error": f"{type(exc).__name__}: {exc}"}]
    nested = _decode_one_source(unpacked, decoded_root, work_root, relative.with_suffix(""), provenance="gzip_decompressed")
    return [{"source": str(source), "relative_path": relative.as_posix(), "action": "gzip_decompress", "status": "complete", "output": str(unpacked)}, *nested]


def _decode_one_source(source: Path, decoded_root: Path, work_root: Path, relative: Path, *, provenance: str = "iso_source") -> list[dict[str, Any]]:
    suffix = source.suffix.lower()
    data = source.read_bytes()
    base = {"source": str(source), "relative_path": relative.as_posix(), "provenance": provenance}
    if data[:2] == b"\x1f\x8b":
        return _decode_gzip(source, work_root, decoded_root, relative)
    if suffix == ".bd" and source.with_suffix(".hd").is_file():
        return [{**base, "action": "paired_bd", "status": "handled_by_hd_pair"}]
    if suffix == ".hd" and source.with_suffix(".bd").is_file():
        try:
            report = scei_hd_bd.inspect_hd_bd_pair(source, decoded_root=decoded_root / "scei", source_iso_path=relative.as_posix())
            return [{**base, "action": "decode_scei_hd_bd", "status": "complete", "summary": {key: report.get(key) for key in ("stream_count", "decoded_stream_count", "failed_stream_count", "pair_found")}, "decoded_rows": report.get("decoded_rows") or []}]
        except Exception as exc:
            return [{**base, "action": "decode_scei_hd_bd", "status": "error", "error": f"{type(exc).__name__}: {exc}"}]
    if normalize_path(relative.as_posix()) == "data/snddata.bin":
        try:
            report = scei_hd_bd.inspect_snddata(source, decoded_root=decoded_root / "snddata_banks", source_iso_path=relative.as_posix())
            return [{**base, "action": "decode_snddata_scei_banks", "status": "complete", "summary": {"candidate_count": report.get("candidate_count"), "decoded_rows": len(report.get("decoded_rows") or [])}, "decoded_rows": report.get("decoded_rows") or []}]
        except Exception as exc:
            return [{**base, "action": "decode_snddata_scei_banks", "status": "error", "error": f"{type(exc).__name__}: {exc}"}]
    if b"IECSsreV" in data or b"SCEIVers" in data:
        try:
            rows = scei_hd_bd.decode_scei_path(source, decoded_root / "scei")
            return [{**base, "action": "decode_scei_container", "status": "complete", "decoded_rows": rows, "decoded_wavs": sum(1 for row in rows if row.get("output_path"))}]
        except Exception as exc:
            return [{**base, "action": "decode_scei_container", "status": "error", "error": f"{type(exc).__name__}: {exc}"}]

    try:
        report = audio_decoder.decode_audio_candidate(source, decoded_root, metadata={"source_iso_path": relative.as_posix()})
        return [{**base, "action": "decode_audio_candidate", "status": "complete" if not report.get("errors") else "partial", "decode": report}]
    except Exception as exc:
        return [{**base, "action": "decode_audio_candidate", "status": "error", "error": f"{type(exc).__name__}: {exc}"}]


def decode_project_sound_sources(
    project: FragmenterProjectV1,
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source_root = sound_source_root(project)
    decoded_root = sound_decoded_root(project)
    work_root = sound_work_root(project)
    files = sorted((path for path in source_root.rglob("*") if path.is_file()), key=lambda path: path.relative_to(source_root).as_posix())
    rows: list[dict[str, Any]] = []
    total = len(files)
    for index, source in enumerate(files, 1):
        relative = source.relative_to(source_root)
        results = _decode_one_source(source, decoded_root, work_root, relative)
        rows.extend(results)
        if callback is not None:
            callback({"kind": "sound_decode_progress", "current": index, "total": total, "relative_path": relative.as_posix(), "actions": len(results)})
    decoded_wavs = sorted(path for path in decoded_root.rglob("*.wav") if path.is_file())
    report = {
        "version": 1,
        "created_at": _utc_iso(),
        "source_root": str(source_root),
        "decoded_root": str(decoded_root),
        "actions": rows,
        "summary": {
            "source_files": total,
            "actions": len(rows),
            "decoded_wavs": len(decoded_wavs),
            "errors": sum(1 for row in rows if row.get("status") == "error"),
            "partial": sum(1 for row in rows if row.get("status") == "partial"),
        },
    }
    path = _atomic_json(sound_reports_root(project) / DECODE_REPORT_NAME, report)
    report["report_path"] = str(path)
    return report


def _wav_metadata(path: Path) -> dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            return {"valid": True, "channels": handle.getnchannels(), "sample_width": handle.getsampwidth(), "sample_rate": rate, "frames": frames, "duration": frames / float(rate) if rate else 0.0}
    except Exception as exc:
        return {"valid": False, "error": str(exc), "duration": 0.0}


def _purpose(relative: str) -> str:
    low = relative.lower().replace("\\", "/")
    if "bgm" in low or "music" in low:
        return "BGM / Music"
    if "voice" in low or "talk" in low or "dialog" in low:
        return "Voice"
    if "food" in low:
        return "FOOD stream"
    if "eff" in low or "sfx" in low or "/se" in low:
        return "Sound effect"
    if "snddata" in low:
        return "SNDDATA"
    return "Other audio"


def build_project_sound_library(project: FragmenterProjectV1, *, query: str = "", category: str = "All") -> dict[str, Any]:
    root = sound_root(project)
    source = sound_source_root(project)
    decoded = sound_decoded_root(project)
    needle = query.strip().lower()
    rows: list[dict[str, Any]] = []

    for kind, scan_root in (("source", source), ("decoded", decoded)):
        for path in sorted((item for item in scan_root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(scan_root).as_posix()):
            relative = path.relative_to(scan_root).as_posix()
            purpose = _purpose(relative)
            if category != "All" and purpose != category:
                continue
            haystack = f"{relative} {purpose} {kind}".lower()
            if needle and not all(token in haystack for token in needle.split()):
                continue
            suffix = path.suffix.lower()
            wav = _wav_metadata(path) if suffix == ".wav" else None
            playable = bool(wav and wav.get("valid"))
            data_head = path.read_bytes()[:16] if not playable else b""
            supported_container = bool(
                kind == "source"
                and (
                    suffix in {".hd", ".bd", ".vag", ".wav", ".mid", ".midi"}
                    or data_head[:2] == b"\x1f\x8b"
                    or b"IECSsreV" in data_head
                    or normalize_path(relative) == "data/snddata.bin"
                )
            )
            rows.append(
                {
                    "kind": kind,
                    "name": path.name,
                    "path": str(path),
                    "relative_path": relative,
                    "category": purpose,
                    "size": path.stat().st_size,
                    "playable": playable,
                    "supported_container": supported_container,
                    "primary_action": "Play" if playable else "Analyze / Extract" if supported_container else "Inspect",
                    "status": "playable WAV" if playable else "supported source container" if supported_container else "source/decoded file",
                    "wav": wav,
                    "signature_hex": data_head.hex() if data_head else None,
                }
            )
    categories = sorted({row["category"] for row in rows})
    payload = {
        "version": 1,
        "root": str(root),
        "source_root": str(source),
        "decoded_root": str(decoded),
        "items": rows,
        "categories": categories,
        "summary": {
            "items": len(rows),
            "source_files": sum(1 for row in rows if row["kind"] == "source"),
            "decoded_files": sum(1 for row in rows if row["kind"] == "decoded"),
            "playable_wavs": sum(1 for row in rows if row["playable"]),
            "supported_containers": sum(1 for row in rows if row["supported_container"]),
        },
    }
    _atomic_json(sound_reports_root(project) / LIBRARY_NAME, payload)
    return payload


def analyze_or_extract_sound_item(project: FragmenterProjectV1, source_path: str | Path) -> dict[str, Any]:
    source_root = sound_source_root(project).resolve()
    candidate = Path(source_path).expanduser().resolve()
    try:
        candidate.relative_to(source_root)
    except ValueError as exc:
        raise PermissionError(f"Sound action is limited to the active project source root: {source_root}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    relative = candidate.relative_to(source_root)
    rows = _decode_one_source(candidate, sound_decoded_root(project), sound_work_root(project), relative)
    library = build_project_sound_library(project)
    return {"source": str(candidate), "relative_path": relative.as_posix(), "actions": rows, "library_summary": library["summary"]}

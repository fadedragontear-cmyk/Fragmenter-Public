#!/usr/bin/env python3
"""V2 project/sound library: actionable binary analysis and less metadata clutter."""
from __future__ import annotations

import gzip
import json
import struct
import wave
from pathlib import Path
from typing import Any

import audio_decoder
import project_sound_v1 as v1
from iso9660 import normalize_path
from project_workspace_v1 import FragmenterProjectV1

SIGNATURES = {
    "gzip": b"\x1f\x8b\x08",
    "scei_vers": b"IECSsreV",
    "scei_midi": b"IECSidiM",
    "vagp": b"VAGp",
    "riff_wave": b"RIFF",
    "midi": b"MThd",
    "sshd": b"SShd",
    "ssbd": b"SSbd",
}

sound_root = v1.sound_root
sound_source_root = v1.sound_source_root
sound_decoded_root = v1.sound_decoded_root
sound_reports_root = v1.sound_reports_root
sound_work_root = v1.sound_work_root
canonical_snddata_path = v1.canonical_snddata_path
extract_project_sound_sources = v1.extract_project_sound_sources
decode_project_sound_sources = v1.decode_project_sound_sources


def _wav_metadata(path: Path) -> dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            return {
                "valid": True,
                "channels": handle.getnchannels(),
                "sample_width": handle.getsampwidth(),
                "sample_rate": rate,
                "frames": frames,
                "duration": frames / float(rate) if rate else 0.0,
            }
    except Exception as exc:
        return {"valid": False, "error": str(exc), "duration": 0.0}


def _purpose(relative: str) -> str:
    return v1._purpose(relative)


def _source_action(relative: str, path: Path, head: bytes) -> tuple[bool, str, str]:
    normalized = normalize_path(relative)
    suffix = path.suffix.lower()
    if normalized == "data/snddata.bin":
        return True, "Open Music Index", "canonical SNDDATA music-system source"
    supported = bool(
        suffix in {".hd", ".bd", ".vag", ".wav", ".mid", ".midi"}
        or head[:2] == b"\x1f\x8b"
        or b"IECSsreV" in head
    )
    if supported:
        return True, "Analyze / Extract", "supported source container"
    if suffix == ".bin" or _purpose(relative) == "BGM / Music":
        return True, "Analyze Container", "binary audio candidate"
    return False, "Inspect", "source file"


def build_project_sound_library(project: FragmenterProjectV1, *, query: str = "", category: str = "All") -> dict[str, Any]:
    root = sound_root(project)
    source = sound_source_root(project)
    decoded = sound_decoded_root(project)
    needle = query.strip().lower()
    rows: list[dict[str, Any]] = []
    hidden_metadata = 0

    for kind, scan_root in (("source", source), ("decoded", decoded)):
        for path in sorted((item for item in scan_root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(scan_root).as_posix()):
            relative = path.relative_to(scan_root).as_posix()
            if kind == "decoded" and path.suffix.lower() == ".json":
                hidden_metadata += 1
                continue
            purpose = _purpose(relative)
            if category != "All" and purpose != category:
                continue
            haystack = f"{relative} {purpose} {kind}".lower()
            if needle and not all(token in haystack for token in needle.split()):
                continue
            wav = _wav_metadata(path) if path.suffix.lower() == ".wav" else None
            playable = bool(wav and wav.get("valid"))
            head = path.read_bytes()[:64] if not playable else b""
            if playable:
                supported_container, primary_action, status = False, "Play", "playable WAV"
            elif kind == "source":
                supported_container, primary_action, status = _source_action(relative, path, head)
            else:
                supported_container, primary_action, status = False, "Inspect", "decoded/raw file"
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
                    "primary_action": primary_action,
                    "status": status,
                    "wav": wav,
                    "signature_hex": head.hex() if head else None,
                }
            )
    categories = sorted({row["category"] for row in rows})
    payload = {
        "version": 2,
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
            "hidden_metadata_files": hidden_metadata,
        },
    }
    v1._atomic_json(sound_reports_root(project) / v1.LIBRARY_NAME, payload)
    return payload


def _signature_offsets(data: bytes, magic: bytes, limit: int = 128) -> list[int]:
    rows: list[int] = []
    cursor = 0
    while len(rows) < limit:
        hit = data.find(magic, cursor)
        if hit < 0:
            break
        rows.append(hit)
        cursor = hit + 1
    return rows


def _extract_embedded_candidates(project: FragmenterProjectV1, source: Path, relative: Path, data: bytes, signatures: dict[str, list[int]]) -> list[dict[str, Any]]:
    work = sound_work_root(project) / "embedded" / relative
    decoded = sound_decoded_root(project) / "embedded"
    rows: list[dict[str, Any]] = []

    for ordinal, offset in enumerate(signatures.get("riff_wave", [])[:32], 1):
        if offset + 12 > len(data) or data[offset + 8 : offset + 12] != b"WAVE":
            continue
        size = struct.unpack_from("<I", data, offset + 4)[0] + 8
        if size < 12 or offset + size > len(data):
            rows.append({"kind": "RIFF/WAVE", "offset": offset, "status": "invalid_bounds", "declared_size": size})
            continue
        candidate = work.parent / f"{work.stem}_riff_{ordinal:03d}.wav"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(data[offset : offset + size])
        report = audio_decoder.decode_audio_candidate(candidate, decoded, metadata={"source_iso_path": f"{relative.as_posix()}#riff@0x{offset:X}"})
        rows.append({"kind": "RIFF/WAVE", "offset": offset, "status": report.get("decode_status"), "candidate": str(candidate), "output_path": report.get("output_path"), "errors": report.get("errors")})

    for ordinal, offset in enumerate(signatures.get("vagp", [])[:64], 1):
        if offset + 0x30 > len(data):
            continue
        payload_size = int.from_bytes(data[offset + 0x0C : offset + 0x10], "big")
        available = len(data) - offset - 0x30
        if payload_size <= 0 or payload_size > available:
            payload_size = available
        payload_size -= payload_size % 16
        if payload_size <= 0:
            continue
        candidate = work.parent / f"{work.stem}_vag_{ordinal:03d}.vag"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(data[offset : offset + 0x30 + payload_size])
        report = audio_decoder.decode_audio_candidate(candidate, decoded, metadata={"source_iso_path": f"{relative.as_posix()}#vag@0x{offset:X}"})
        rows.append({"kind": "VAGp", "offset": offset, "status": report.get("decode_status"), "candidate": str(candidate), "output_path": report.get("output_path"), "errors": report.get("errors")})

    for ordinal, offset in enumerate(signatures.get("gzip", [])[:8], 1):
        try:
            unpacked = gzip.decompress(data[offset:])
        except Exception as exc:
            rows.append({"kind": "gzip", "offset": offset, "status": "decompress_failed", "error": str(exc)})
            continue
        candidate = work.parent / f"{work.stem}_gzip_{ordinal:03d}.bin"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(unpacked)
        nested = v1._decode_one_source(candidate, decoded, sound_work_root(project), Path(f"embedded/{candidate.name}"), provenance=f"embedded_gzip@0x{offset:X}")
        rows.append({"kind": "gzip", "offset": offset, "status": "decompressed", "candidate": str(candidate), "size": len(unpacked), "nested_actions": nested})
    return rows


def analyze_binary_container(project: FragmenterProjectV1, source: Path, relative: Path) -> dict[str, Any]:
    data = source.read_bytes()
    signatures = {name: _signature_offsets(data, magic) for name, magic in SIGNATURES.items()}
    embedded = _extract_embedded_candidates(project, source, relative, data, signatures)
    base_actions = v1._decode_one_source(source, sound_decoded_root(project), sound_work_root(project), relative)
    report = {
        "version": 2,
        "source": str(source),
        "relative_path": relative.as_posix(),
        "size": len(data),
        "head_hex": data[:64].hex(),
        "tail_hex": data[-64:].hex() if data else "",
        "signature_offsets": signatures,
        "base_decode_actions": base_actions,
        "embedded_candidates": embedded,
        "summary": {
            "signatures_found": sum(len(offsets) for offsets in signatures.values()),
            "embedded_attempts": len(embedded),
            "embedded_outputs": sum(1 for row in embedded if row.get("output_path") or row.get("status") in {"decompressed", "copied_validated_wav", "decoded_vagp_to_pcm_wav"}),
        },
    }
    target = sound_reports_root(project) / f"container_analysis_{relative.as_posix().replace('/', '_').replace('\\\\', '_')}.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(target)
    return report


def analyze_or_extract_sound_item(project: FragmenterProjectV1, source_path: str | Path) -> dict[str, Any]:
    source_root_value = sound_source_root(project).resolve()
    candidate = Path(source_path).expanduser().resolve()
    try:
        relative = candidate.relative_to(source_root_value)
    except ValueError as exc:
        raise PermissionError(f"Sound action is limited to the active project source root: {source_root_value}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    if normalize_path(relative.as_posix()) == "data/snddata.bin":
        from snddata_music_system_v4 import catalog_path, load_catalog

        payload = load_catalog(project)
        return {
            "source": str(candidate),
            "relative_path": relative.as_posix(),
            "action": "open_music_index",
            "catalog_path": str(catalog_path(project)),
            "summary": payload.get("summary"),
            "note": "SNDDATA is indexed by RUN ALL. Use the mixer for sequence/Program/sample routing; this action does not reparse 41 MB on the UI thread.",
        }
    if candidate.suffix.lower() == ".bin" or _purpose(relative.as_posix()) == "BGM / Music":
        result = analyze_binary_container(project, candidate, relative)
    else:
        rows = v1._decode_one_source(candidate, sound_decoded_root(project), sound_work_root(project), relative)
        result = {"source": str(candidate), "relative_path": relative.as_posix(), "actions": rows}
    library = build_project_sound_library(project)
    result["library_summary"] = library["summary"]
    return result

#!/usr/bin/env python3
"""Cached exact-name cross-file TEX/MAT/CLUT resolution for extracted CCSF assets.

Fragment CCS indexes can name a material, texture, or palette in one file while the
typed setup record is stored in another extracted CCS file. Resolution here is
strict: only exact indexed object names are accepted. No nearest-name, ordinal, or
visual similarity guesses are made.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import ccsf_structure_decoder as base
import ccsf_texture_decoder_v2 as texture_v2

ASSET_SUFFIXES = {".ccs", ".ccsf", ".tmp", ".bin"}
_FILE_CACHE: dict[str, dict[str, Any]] = {}
_CANDIDATE_CACHE: dict[tuple[str, str], list[Path]] = {}


def _root_for(source: Path) -> Path:
    resolved = source.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name.lower() == "extracted_ccs":
            return parent
    return resolved.parent


def clear_registry_cache(root: str | Path | None = None) -> None:
    if root is None:
        _FILE_CACHE.clear()
        _CANDIDATE_CACHE.clear()
        return
    key = str(Path(root).expanduser().resolve())
    for path in [path for path in _FILE_CACHE if path.startswith(key)]:
        _FILE_CACHE.pop(path, None)
    for cache_key in [cache_key for cache_key in _CANDIDATE_CACHE if cache_key[0] == key]:
        _CANDIDATE_CACHE.pop(cache_key, None)


def _probe_candidates(root: Path, object_name: str) -> list[Path]:
    report_path = root.parent / "diagnostics" / "visual" / "ccsf_texture_library_probe_v1.json"
    if not report_path.is_file():
        return []
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = (payload.get("texture_name_index") or {}).get(object_name) or []
    candidates: list[Path] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        relative = str(row.get("asset") or "").strip()
        if relative:
            candidate = root / Path(*relative.replace("\\", "/").split("/"))
            if candidate.is_file():
                candidates.append(candidate.resolve())
    return candidates


def _candidate_files(source: Path, object_name: str) -> list[Path]:
    root = _root_for(source)
    cache_key = (str(root.resolve()), object_name)
    cached = _CANDIDATE_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    ordered: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        key = str(resolved)
        if key in seen or not resolved.is_file() or resolved.suffix.lower() not in ASSET_SUFFIXES:
            return
        seen.add(key)
        ordered.append(resolved)

    for candidate in _probe_candidates(root, object_name):
        add(candidate)

    needle = object_name.encode("cp1252", errors="ignore")
    local_files = sorted(source.parent.glob("*"), key=lambda path: path.name.lower())
    all_files = sorted(root.rglob("*"), key=lambda path: path.as_posix().lower())
    for collection in (local_files, all_files):
        for candidate in collection:
            if not candidate.is_file() or candidate.suffix.lower() not in ASSET_SUFFIXES:
                continue
            try:
                data = candidate.read_bytes()
            except OSError:
                continue
            if needle and needle in data:
                add(candidate)

    _CANDIDATE_CACHE[cache_key] = ordered
    return list(ordered)


def _decode_file(path: Path) -> dict[str, Any]:
    resolved = str(path.resolve())
    cached = _FILE_CACHE.get(resolved)
    if cached is not None:
        return cached
    data = path.read_bytes()
    report = base.decode(path)
    generation = str(report.header.get("generation") or "Unknown")
    records_by_name: dict[str, list[dict[str, Any]]] = {}
    for record in report.records:
        name = str(record.get("object_name") or "")
        if name:
            records_by_name.setdefault(name, []).append(record)
    decoded = {
        "path": path,
        "data": data,
        "report": report,
        "generation": generation,
        "records_by_name": records_by_name,
        "cluts": {},
    }
    _FILE_CACHE[resolved] = decoded
    return decoded


def _local_clut(decoded: dict[str, Any], clut_id: int) -> dict[str, Any] | None:
    cluts = decoded["cluts"]
    if clut_id in cluts:
        return cluts[clut_id]
    for record in decoded["report"].records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_CLUT:
            continue
        if int(record.get("object_id") or -1) != int(clut_id):
            continue
        try:
            clut = texture_v2.parse_clut_record(decoded["data"], record)
        except Exception:
            return None
        cluts[clut_id] = clut
        return clut
    return None


def resolve_clut_by_name(source: str | Path, object_name: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    source_path = Path(source).expanduser().resolve()
    evidence: dict[str, Any] = {
        "requested_clut_name": object_name,
        "source": str(source_path),
        "candidates": [],
        "status": "not_found",
    }
    for candidate in _candidate_files(source_path, object_name):
        try:
            decoded = _decode_file(candidate)
        except Exception as exc:
            evidence["candidates"].append({"path": str(candidate), "status": "decode_error", "error": str(exc)})
            continue
        records = [
            record
            for record in decoded["records_by_name"].get(object_name, [])
            if int(record.get("masked_section_type") or 0) == base.SECTION_CLUT
        ]
        for record in records:
            try:
                clut = texture_v2.parse_clut_record(decoded["data"], record)
                clut["external_source"] = str(candidate)
                clut["external_object_id"] = int(record.get("object_id") or 0)
                clut["resolution_source"] = "exact CLUT object-name setup record in extracted CCS library"
            except Exception as exc:
                evidence["candidates"].append(
                    {"path": str(candidate), "object_id": record.get("object_id"), "status": "decode_error", "error": str(exc)}
                )
                continue
            evidence["candidates"].append({"path": str(candidate), "object_id": record.get("object_id"), "status": "decoded"})
            evidence.update({"status": "resolved", "resolved_path": str(candidate), "resolved_object_id": record.get("object_id")})
            return clut, evidence
    return None, evidence


def _decode_texture_record(decoded: dict[str, Any], record: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    try:
        texture = texture_v2.parse_texture_record(decoded["data"], record, decoded["generation"])
        if texture.get("status") != "pixel_data_decoded":
            return None, str(texture.get("warnings") or texture.get("status") or "texture metadata only")
        clut_id = int(texture.get("clut_id") or -1)
        clut = _local_clut(decoded, clut_id)
        clut_evidence = None
        indexed = int(texture.get("texture_type") or 0) in {texture_v2.TEXTURE_I4, texture_v2.TEXTURE_I8}
        if indexed and clut is None:
            entry = decoded["report"].object_lookup.get(clut_id) or {}
            clut_name = str(entry.get("name") or "")
            if clut_name:
                clut, clut_evidence = resolve_clut_by_name(decoded["path"], clut_name)
            if clut is None:
                return None, f"indexed texture CLUT {clut_id} {clut_name!r} is not decoded locally or externally"
        texture["rgba"] = texture_v2.decode_rgba(texture, clut)
        texture["clut_resolved"] = clut is not None
        texture["clut_external"] = bool(clut and clut.get("external_source"))
        texture["clut_external_source"] = (clut or {}).get("external_source")
        texture["clut_mapping_evidence"] = clut_evidence
        texture["external_source"] = str(decoded["path"])
        texture["external_object_id"] = int(record.get("object_id") or 0)
        texture["resolution_source"] = "exact object-name setup record in extracted CCS library"
        detail = "decoded with exact external CLUT" if texture["clut_external"] else "decoded"
        return texture, detail
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def resolve_texture_by_name(source: str | Path, object_name: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    source_path = Path(source).expanduser().resolve()
    evidence: dict[str, Any] = {
        "requested_name": object_name,
        "source": str(source_path),
        "candidates": [],
        "status": "not_found",
    }
    for candidate in _candidate_files(source_path, object_name):
        try:
            decoded = _decode_file(candidate)
        except Exception as exc:
            evidence["candidates"].append({"path": str(candidate), "status": "decode_error", "error": str(exc)})
            continue
        records = [
            record
            for record in decoded["records_by_name"].get(object_name, [])
            if int(record.get("masked_section_type") or 0) == base.SECTION_TEXTURE
        ]
        for record in records:
            texture, detail = _decode_texture_record(decoded, record)
            evidence["candidates"].append({"path": str(candidate), "object_id": record.get("object_id"), "status": detail})
            if texture is not None:
                evidence.update(
                    {
                        "status": "resolved",
                        "resolved_path": str(candidate),
                        "resolved_object_id": record.get("object_id"),
                        "clut_external_source": texture.get("clut_external_source"),
                    }
                )
                return texture, evidence
    return None, evidence


def resolve_material_texture_by_name(
    source: str | Path,
    material_name: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    source_path = Path(source).expanduser().resolve()
    evidence: dict[str, Any] = {
        "requested_material_name": material_name,
        "source": str(source_path),
        "candidates": [],
        "status": "not_found",
    }
    for candidate in _candidate_files(source_path, material_name):
        try:
            decoded = _decode_file(candidate)
        except Exception as exc:
            evidence["candidates"].append({"path": str(candidate), "status": "decode_error", "error": str(exc)})
            continue
        records = [
            record
            for record in decoded["records_by_name"].get(material_name, [])
            if int(record.get("masked_section_type") or 0) == base.SECTION_MATERIAL
        ]
        for record in records:
            start = int(record.get("payload_start") or 0)
            end = int(record.get("payload_end") or 0)
            if start < 0 or start + 12 > end or end > len(decoded["data"]):
                evidence["candidates"].append({"path": str(candidate), "status": "material_payload_truncated"})
                continue
            texture_id = struct.unpack_from("<i", decoded["data"], start)[0]
            alpha = struct.unpack_from("<f", decoded["data"], start + 4)[0]
            raw_u, raw_v = struct.unpack_from("<hh", decoded["data"], start + 8)
            material = {
                "object_id": int(record.get("object_id") or 0),
                "object_name": material_name,
                "texture_id": texture_id,
                "alpha": alpha,
                "texture_offset": [raw_u / 256.0, raw_v / 256.0],
                "texture_offset_raw": [raw_u, raw_v],
                "status": "parsed_external_exact_material",
                "external_source": str(candidate),
            }
            texture_entry = decoded["report"].object_lookup.get(texture_id) or {}
            texture_name = str(texture_entry.get("name") or "")
            texture = None
            detail = "texture name absent"
            if texture_name:
                local_records = [
                    row
                    for row in decoded["records_by_name"].get(texture_name, [])
                    if int(row.get("masked_section_type") or 0) == base.SECTION_TEXTURE
                ]
                for texture_record in local_records:
                    texture, detail = _decode_texture_record(decoded, texture_record)
                    if texture is not None:
                        break
                if texture is None:
                    texture, nested = resolve_texture_by_name(candidate, texture_name)
                    detail = nested.get("status") or detail
            evidence["candidates"].append(
                {
                    "path": str(candidate),
                    "material_object_id": record.get("object_id"),
                    "texture_id": texture_id,
                    "texture_name": texture_name,
                    "status": detail,
                }
            )
            if texture is not None:
                evidence.update(
                    {
                        "status": "resolved",
                        "resolved_path": str(candidate),
                        "resolved_material_id": record.get("object_id"),
                        "resolved_texture_name": texture_name,
                        "clut_external_source": texture.get("clut_external_source"),
                    }
                )
                return texture, material, evidence
    return None, None, evidence

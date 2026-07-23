#!/usr/bin/env python3
"""Shared identity-based CCSF structure cache for Fragmenter 1.0.

3D, Textures, and Animation must reuse the same structural decode. This module is
GUI-agnostic: callers provide the decoder and an optional report converter.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

CACHE_VERSION = 1


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def source_identity(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    stat = source.stat()
    return {"path": str(source), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def cache_key(
    path: str | Path,
    *,
    decoder_version: str,
    options: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    identity = source_identity(path)
    descriptor = {
        "cache_version": CACHE_VERSION,
        "source": identity,
        "decoder_version": str(decoder_version),
        "options": dict(options or {}),
    }
    digest = hashlib.sha256(_stable_json(descriptor).encode("utf-8")).hexdigest()
    return digest, descriptor


def cache_path(
    cache_root: str | Path,
    path: str | Path,
    *,
    decoder_version: str,
    options: dict[str, Any] | None = None,
) -> Path:
    key, _descriptor = cache_key(path, decoder_version=decoder_version, options=options)
    return Path(cache_root).expanduser() / key[:2] / f"{key}.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


@dataclass(frozen=True)
class CachedStructure:
    report: dict[str, Any]
    cache_hit: bool
    cache_path: Path
    descriptor: dict[str, Any]


def load_cached(
    cache_root: str | Path,
    path: str | Path,
    *,
    decoder_version: str,
    options: dict[str, Any] | None = None,
) -> CachedStructure | None:
    target = cache_path(cache_root, path, decoder_version=decoder_version, options=options)
    if not target.is_file():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    if int(payload.get("cache_version") or 0) != CACHE_VERSION:
        return None
    _key, descriptor = cache_key(path, decoder_version=decoder_version, options=options)
    if payload.get("descriptor") != descriptor:
        return None
    report = payload.get("report")
    if not isinstance(report, dict):
        return None
    return CachedStructure(report=dict(report), cache_hit=True, cache_path=target, descriptor=descriptor)


def get_or_decode(
    path: str | Path,
    cache_root: str | Path,
    *,
    decoder: Callable[[Path], Any],
    decoder_version: str,
    report_converter: Callable[[Any], dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
) -> CachedStructure:
    cached = load_cached(cache_root, path, decoder_version=decoder_version, options=options)
    if cached is not None:
        return cached
    source = Path(path).expanduser().resolve()
    decoded = decoder(source)
    report = report_converter(decoded) if report_converter else decoded
    if not isinstance(report, dict):
        raise TypeError("CCSF structure decoder/report converter must return a dict")
    target = cache_path(cache_root, source, decoder_version=decoder_version, options=options)
    _key, descriptor = cache_key(source, decoder_version=decoder_version, options=options)
    payload = {
        "cache_version": CACHE_VERSION,
        "created_at": _utc_iso(),
        "descriptor": descriptor,
        "report": report,
    }
    _atomic_write(target, payload)
    return CachedStructure(report=dict(report), cache_hit=False, cache_path=target, descriptor=descriptor)


def invalidate_source(cache_root: str | Path, path: str | Path) -> int:
    root = Path(cache_root).expanduser()
    source = str(Path(path).expanduser().resolve())
    removed = 0
    if not root.is_dir():
        return removed
    for candidate in root.rglob("*.json"):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        descriptor = payload.get("descriptor") if isinstance(payload, dict) else None
        identity = descriptor.get("source") if isinstance(descriptor, dict) else None
        if isinstance(identity, dict) and identity.get("path") == source:
            candidate.unlink()
            removed += 1
    return removed


def cache_summary(cache_root: str | Path) -> dict[str, Any]:
    root = Path(cache_root).expanduser()
    files = list(root.rglob("*.json")) if root.is_dir() else []
    total_bytes = sum(path.stat().st_size for path in files if path.is_file())
    return {"entries": len(files), "bytes": total_bytes, "path": str(root)}

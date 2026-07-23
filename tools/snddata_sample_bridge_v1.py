#!/usr/bin/env python3
"""Unify authoritative SNDDATA sample metadata for cataloging and rendering.

The sample-library extractor writes friendly ``bank_*_sample_*.json`` metadata with
``resource_offset``/``index`` keys. Older music code searched only
``sample_*.json`` and expected ``resource_id``/``sample_id``. This bridge accepts
both schemas, preserves sample zero, infers identifiers from friendly names when
metadata fields are absent, and installs the normalized view into the existing
v3/v4/v5 music pipeline without changing binary data.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import snddata_music_system_v3 as music_v3
import snddata_music_system_v4 as music_v4
from project_sound_v1 import canonical_snddata_path, sound_decoded_root, sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from snddata_sample_library_v3 import REPORT_NAME, extract_project_snddata_samples

_INSTALLED = False
_SAMPLE_NUMBER = re.compile(r"(?<![A-Za-z0-9])sample(?:[_\s-]+)(\d+)(?!\d)", re.IGNORECASE)
_OFFSET_PATH = re.compile(r"(?:^|[_-])offset[_-]?(?:0x)?([0-9a-f]+)(?:$|[_-])", re.IGNORECASE)
_RESOURCE_PATH = re.compile(r"(?:^|[_-])resource[_-]?(?:0x)?([0-9a-f]+)(?:$|[_-])", re.IGNORECASE)


def _integer(row: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            try:
                return int(text, 0)
            except ValueError:
                continue
    return None


def _sample_id_from_text(value: Any) -> int | None:
    match = _SAMPLE_NUMBER.search(str(value or ""))
    return int(match.group(1)) if match else None


def _resource_id_from_path(path: Path | None) -> int | None:
    if path is None:
        return None
    for part in reversed(path.parts):
        offset = _OFFSET_PATH.search(part)
        if offset:
            return int(offset.group(1), 16)
        resource = _RESOURCE_PATH.search(part)
        if resource:
            text = resource.group(1)
            # Friendly bank folders use hexadecimal offsets. Legacy resource folders
            # were normally decimal unless hexadecimal letters were present.
            base = 16 if any(char in "abcdefABCDEF" for char in text) else 10
            return int(text, base)
    return None


def _sample_id_from_paths(*paths: Path | None) -> int | None:
    for path in paths:
        if path is None:
            continue
        for value in (path.stem, path.name, path.as_posix()):
            sample_id = _sample_id_from_text(value)
            if sample_id is not None:
                return sample_id
    return None


def _metadata_root(project: FragmenterProjectV1) -> Path:
    return sound_decoded_root(project) / "snddata" / "samples"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sample_report(project: FragmenterProjectV1) -> dict[str, Any]:
    path = sound_reports_root(project) / REPORT_NAME
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {"samples": [], "report_path": str(path)}


def _canonical_display_name(row: dict[str, Any], sample_id: int) -> str:
    name = str(row.get("display_name") or "").strip()
    if not name:
        return f"sample {sample_id:04d}"
    return _SAMPLE_NUMBER.sub(lambda match: f"sample {int(match.group(1)):04d}", name)


def _normalize_row(raw: dict[str, Any], *, metadata_path: Path | None = None) -> dict[str, Any] | None:
    output_text = str(raw.get("output_path") or "").strip()
    output_path = Path(output_text).expanduser() if output_text else None
    metadata_hint = metadata_path
    if metadata_hint is None:
        metadata_text = str(raw.get("metadata_path") or "").strip()
        metadata_hint = Path(metadata_text).expanduser() if metadata_text else None

    resource_id = _integer(raw, "resource_id", "resource_offset")
    if resource_id is None:
        resource_id = _resource_id_from_path(metadata_hint) or _resource_id_from_path(output_path)

    sample_id = _integer(raw, "sample_id", "index")
    if sample_id is None:
        sample_id = _sample_id_from_text(raw.get("display_name"))
    if sample_id is None:
        sample_id = _sample_id_from_paths(metadata_hint, output_path)

    if resource_id is None or sample_id is None:
        return None

    row = {
        **raw,
        "resource_id": resource_id,
        "resource_offset": resource_id,
        "sample_id": sample_id,
        "index": sample_id,
        "display_name": _canonical_display_name(raw, sample_id),
        "output_path": output_text,
    }
    if metadata_hint is not None:
        row["metadata_path"] = str(metadata_hint)
    row["output_exists"] = bool(output_path and output_path.is_file())
    return row


def _row_score(row: dict[str, Any]) -> tuple[int, int, int, int]:
    boundary = str(row.get("boundary_source") or "")
    return (
        1 if row.get("output_exists") else 0,
        1 if not row.get("errors") else 0,
        1 if str(row.get("output_path") or "").casefold().endswith(".wav") else 0,
        1 if boundary.startswith(("structured_", "validated_", "SCEIVagi")) else 0,
    )


def normalized_sample_rows(project: FragmenterProjectV1) -> list[dict[str, Any]]:
    """Return one normalized row per resource/sample pair from metadata and report."""
    candidates: list[dict[str, Any]] = []
    root = _metadata_root(project)
    if root.is_dir():
        for metadata in sorted(root.rglob("*.json")):
            payload = _load_json(metadata)
            if not isinstance(payload, dict):
                continue
            row = _normalize_row(payload, metadata_path=metadata)
            if row is not None:
                candidates.append(row)
    for raw in _sample_report(project).get("samples") or []:
        if isinstance(raw, dict):
            row = _normalize_row(raw)
            if row is not None:
                candidates.append(row)

    selected: dict[tuple[int, int], dict[str, Any]] = {}
    for row in candidates:
        key = (int(row["resource_id"]), int(row["sample_id"]))
        current = selected.get(key)
        if current is None or _row_score(row) > _row_score(current):
            selected[key] = row
    return [selected[key] for key in sorted(selected)]


def ensure_canonical_samples(
    project: FragmenterProjectV1,
    data: bytes,
    groups: list[Any],
) -> list[dict[str, Any]]:
    """Reuse a current authoritative sample report or rebuild it once."""
    del groups  # The authoritative extractor parses the canonical source directly.
    report = _sample_report(project)
    source_hash = hashlib.sha256(data).hexdigest()
    raw_rows = [row for row in report.get("samples") or [] if isinstance(row, dict)]
    usable = [row for row in raw_rows if not row.get("errors")]
    current = str(report.get("source_sha256") or "") == source_hash
    outputs_present = bool(usable) and all(Path(str(row.get("output_path") or "")).is_file() for row in usable)
    if current and outputs_present:
        return raw_rows
    rebuilt = extract_project_snddata_samples(project, clean=True)
    return [row for row in rebuilt.get("samples") or [] if isinstance(row, dict)]


def samples_for_resource(
    project: FragmenterProjectV1,
    resource_offset: int,
) -> tuple[dict[int, Any], list[dict[str, Any]]]:
    """Load decoded PCM using either friendly or legacy metadata naming."""
    samples: dict[int, Any] = {}
    valid_rows: list[dict[str, Any]] = []
    for row in normalized_sample_rows(project):
        if int(row["resource_id"]) != int(resource_offset) or row.get("errors"):
            continue
        output = Path(str(row.get("output_path") or ""))
        sample_id = int(row["sample_id"])
        if not output.is_file() or output.suffix.casefold() != ".wav":
            continue
        try:
            samples[sample_id] = music_v3._load_wav(
                output,
                sample_id,
                int(row.get("sample_rate") or 0) or None,
            )
            valid_rows.append(row)
        except Exception as exc:
            failed = {**row, "load_error": f"{type(exc).__name__}: {exc}"}
            valid_rows.append(failed)
    return samples, valid_rows


def sample_inventory(project: FragmenterProjectV1) -> dict[int, dict[str, Any]]:
    inventory: dict[int, dict[str, Any]] = {}
    for row in normalized_sample_rows(project):
        output = Path(str(row.get("output_path") or ""))
        if row.get("errors") or not output.is_file() or output.suffix.casefold() != ".wav":
            continue
        resource_id = int(row["resource_id"])
        sample_id = int(row["sample_id"])
        bucket = inventory.setdefault(resource_id, {"sample_ids": set(), "decoded_rows": 0, "structured_rows": 0})
        bucket["sample_ids"].add(sample_id)
        bucket["decoded_rows"] += 1
        boundary = str(row.get("boundary_source") or "")
        if boundary.startswith(("structured_", "validated_", "SCEIVagi")):
            bucket["structured_rows"] += 1
    return inventory


def research_sample_rows(project: FragmenterProjectV1, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    resource_offset = int(candidate.get("resource_offset") or 0)
    required = {int(value) for value in candidate.get("required_sample_ids") or []}
    missing = {int(value) for value in candidate.get("missing_sample_ids") or []}
    by_index: dict[int, dict[str, Any]] = {}
    for raw in normalized_sample_rows(project):
        if int(raw["resource_id"]) != resource_offset:
            continue
        index = int(raw["sample_id"])
        if required and index not in required:
            continue
        path = Path(str(raw.get("output_path") or ""))
        playable = path.is_file() and path.suffix.casefold() == ".wav" and not raw.get("errors")
        by_index[index] = {
            **raw,
            "index": index,
            "sample_id": index,
            "display_name": _canonical_display_name(raw, index),
            "required": index in required,
            "missing": index in missing or not playable,
            "playable": playable,
        }
    if not required:
        return [by_index[index] for index in sorted(by_index)]
    return [
        by_index.get(
            index,
            {
                "resource_id": resource_offset,
                "resource_offset": resource_offset,
                "index": index,
                "sample_id": index,
                "display_name": f"sample {index:04d}",
                "sample_rate": 0,
                "duration_estimate": 0.0,
                "output_path": "",
                "required": True,
                "missing": True,
                "playable": False,
            },
        )
        for index in sorted(required)
    ]


def install() -> None:
    """Install normalized sample access before the GUI/pipeline imports consumers."""
    global _INSTALLED
    if _INSTALLED:
        return
    music_v3.ensure_canonical_samples = ensure_canonical_samples
    music_v3._sample_rows = normalized_sample_rows
    music_v3._samples_for_resource = samples_for_resource
    music_v4._sample_inventory = sample_inventory

    # Import after patching v3/v4 so the workbench and v5 forensic stack bind to the
    # normalized sample view from their first use.
    import snddata_research_workbench_v1 as workbench

    workbench.sample_rows = research_sample_rows
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("This module is installed by the Fragmenter public launcher.")
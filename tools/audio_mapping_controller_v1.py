#!/usr/bin/env python3
"""Project-bound controller for unresolved SNDDATA Program mappings."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from project_preflight_v1 import resolve_runtime_paths
from project_workspace_v1 import FragmenterProjectV1
from snddata_mapping_store_v1 import (
    get_mapping,
    list_mappings,
    mapping_store_path,
    next_candidate,
    remove_mapping,
    resolver_view_model,
    set_mapping,
)

KNOWN_SNDDATA_RELATIVE_PATHS = (
    Path("extracted/top_level/data/snddata.bin"),
    Path("extracted/DATA/SNDDATA.BIN"),
    Path("extracted/data/snddata.bin"),
)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def find_project_snddata(project: FragmenterProjectV1) -> Path | None:
    media = resolve_runtime_paths(project).media_pipeline
    for relative in KNOWN_SNDDATA_RELATIVE_PATHS:
        candidate = media / relative
        if candidate.is_file():
            return candidate.resolve()
    matches = sorted(
        (path for path in media.rglob("*") if path.is_file() and path.name.lower() == "snddata.bin"),
        key=lambda path: str(path).lower(),
    ) if media.is_dir() else []
    return matches[0].resolve() if matches else None


def resolve_project_snddata(project: FragmenterProjectV1, value: str | Path | None = None) -> Path:
    media = resolve_runtime_paths(project).media_pipeline
    if value is None or not str(value).strip():
        candidate = find_project_snddata(project)
        if candidate is None:
            raise FileNotFoundError(f"No SNDDATA.BIN found under active project media pipeline: {media}")
        return candidate
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = media / candidate
    candidate = candidate.resolve()
    if not _inside(candidate, media):
        raise ValueError(f"SNDDATA source is outside the active project media pipeline: {candidate}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    if candidate.name.lower() != "snddata.bin":
        raise ValueError(f"Expected SNDDATA.BIN, got: {candidate.name}")
    return candidate


def mapping_status_view_model(project: FragmenterProjectV1, snddata: str | Path | None = None) -> dict[str, Any]:
    source = resolve_project_snddata(project, snddata)
    store = mapping_store_path(project)
    rows = list_mappings(store, source)
    return {
        "snddata": str(source),
        "store": str(store),
        "mappings": rows,
        "mapping_count": len(rows),
        "writes_game_data": False,
    }


def save_project_mapping(
    project: FragmenterProjectV1,
    snddata: str | Path | None,
    sequence_id: str | int,
    program_resource: str | int,
    *,
    status: str = "manual",
    notes: str = "",
    program_index: int | None = None,
) -> dict[str, Any]:
    source = resolve_project_snddata(project, snddata)
    return set_mapping(
        mapping_store_path(project),
        source,
        sequence_id,
        program_resource,
        status=status,
        notes=notes,
        program_index=program_index,
    )


def load_project_mapping(
    project: FragmenterProjectV1,
    snddata: str | Path | None,
    sequence_id: str | int,
) -> dict[str, Any] | None:
    source = resolve_project_snddata(project, snddata)
    return get_mapping(mapping_store_path(project), source, sequence_id)


def remove_project_mapping(
    project: FragmenterProjectV1,
    snddata: str | Path | None,
    sequence_id: str | int,
) -> bool:
    source = resolve_project_snddata(project, snddata)
    return remove_mapping(mapping_store_path(project), source, sequence_id)


def project_mapping_resolver(
    project: FragmenterProjectV1,
    snddata: str | Path | None,
    sequence_id: str | int,
    candidates: Iterable[str | int],
    *,
    selected_program: str | int | None = None,
) -> dict[str, Any]:
    source = resolve_project_snddata(project, snddata)
    saved = get_mapping(mapping_store_path(project), source, sequence_id)
    model = resolver_view_model(
        sequence_id,
        candidates,
        selected_program=selected_program,
        saved_mapping=saved,
    )
    model.update(
        {
            "snddata": str(source),
            "store": str(mapping_store_path(project)),
            "writes_game_data": False,
            "next_program": next_candidate(model["candidates"], model["selected_program"]),
        }
    )
    return model

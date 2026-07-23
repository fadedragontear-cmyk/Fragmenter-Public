#!/usr/bin/env python3
"""StudioCCS-style clump -> object -> child-model preview traversal.

StudioCCS renders a CCSClump by iterating the clump NodeIDs and rendering each
CCSObject's ChildModel.  Fragmenter previously walked every decoded Model setup
record globally and inferred a model owner afterward.  This module keeps the
clump/object instance identity explicit so clump-local bone indexes and rigid
submodel parents are evaluated against the same clump that owns the model.
"""
from __future__ import annotations

from typing import Any, Iterator

import ccsf_structure_decoder as base


def model_records_by_id(context: Any) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for record in context.report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_MODEL:
            continue
        if not isinstance(record.get("model"), dict):
            continue
        rows[int(record.get("object_id") or 0)] = record
    return rows


def preview_clump_rows(context: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for clump in context.clumps:
        clump_id = int(clump.get("object_id") or 0)
        rows.append(
            {
                "clump_id": clump_id,
                "clump_name": str(clump.get("object_name") or (context.report.object_lookup.get(clump_id) or {}).get("name") or clump_id),
                "node_count": len(clump.get("node_ids") or []),
            }
        )
    return rows


def select_preview_clump(context: Any, preferred_clump_id: int | None = None) -> dict[str, Any] | None:
    clumps = list(context.clumps)
    if not clumps:
        return None
    if preferred_clump_id is not None:
        for clump in clumps:
            if int(clump.get("object_id") or 0) == int(preferred_clump_id):
                return clump
    # Character root/body clumps are normally the largest assembly.  Prefer a
    # trall/thrall-named clump only as a tie-breaker; node count remains primary.
    return max(
        clumps,
        key=lambda row: (
            len(row.get("node_ids") or []),
            1 if "trall" in str(row.get("object_name") or "").lower() or "thrall" in str(row.get("object_name") or "").lower() else 0,
        ),
    )


def iter_clump_model_instances(context: Any, preferred_clump_id: int | None = None) -> Iterator[dict[str, Any]]:
    models = model_records_by_id(context)
    selected = select_preview_clump(context, preferred_clump_id)
    if selected is not None:
        clump_id = int(selected.get("object_id") or 0)
        clump_name = str(selected.get("object_name") or (context.report.object_lookup.get(clump_id) or {}).get("name") or clump_id)
        for node_index, raw_object_id in enumerate(selected.get("node_ids") or []):
            object_id = int(raw_object_id)
            object_row = context.objects.get(object_id)
            if not isinstance(object_row, dict):
                continue
            model_id = int(object_row.get("model_id") or 0)
            record = models.get(model_id)
            if model_id == 0 or record is None:
                continue
            yield {
                "clump": selected,
                "clump_id": clump_id,
                "clump_name": clump_name,
                "node_index": node_index,
                "object_id": object_id,
                "object_name": str(object_row.get("object_name") or (context.report.object_lookup.get(object_id) or {}).get("name") or object_id),
                "object": object_row,
                "model_id": model_id,
                "model_name": str(record.get("object_name") or (context.report.object_lookup.get(model_id) or {}).get("name") or model_id),
                "model_record": record,
                "model": record["model"],
                "source": "selected_clump_node_object_model",
            }
        return

    # Conservative fallback for unusual files with Object records but no Clump.
    for object_id, object_row in context.objects.items():
        model_id = int(object_row.get("model_id") or 0)
        record = models.get(model_id)
        if model_id == 0 or record is None:
            continue
        yield {
            "clump": None,
            "clump_id": None,
            "clump_name": "",
            "node_index": None,
            "object_id": int(object_id),
            "object_name": str(object_row.get("object_name") or (context.report.object_lookup.get(int(object_id)) or {}).get("name") or object_id),
            "object": object_row,
            "model_id": model_id,
            "model_name": str(record.get("object_name") or (context.report.object_lookup.get(model_id) or {}).get("name") or model_id),
            "model_record": record,
            "model": record["model"],
            "source": "object_model_fallback_no_clump",
        }

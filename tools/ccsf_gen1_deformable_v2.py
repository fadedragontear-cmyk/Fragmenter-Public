#!/usr/bin/env python3
"""Tolerant, bounded Gen1 deformable-model decoding.

Two observed failure modes are handled without scanning for guessed geometry:

* A typed, indexed final Model record may claim an outer size slightly beyond EOF even
  though its inner Gen1 model header and submodel streams are complete.
* A later deformable submodel may use a variant that is not understood yet; previously
  that discarded every successfully decoded prefix submodel and left rigid accessories.

The decoder clamps only an exact typed EOF Model record, evaluates two bounded layouts,
keeps the normal StudioCCS layout when complete, and otherwise preserves the strongest
safely decoded prefix.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import ccsf_gen1_deformable_v1 as v1
import ccsf_structure_decoder as base


_LAYOUT_STANDARD = "single_prefix_weighted_tail"
_LAYOUT_ALL_SINGLE = "all_single_weight"
_MAX_MODEL_EOF_OVERSHOOT = 0x2000


def _layout_for_count(count: int, name: str) -> list[str]:
    count = max(0, int(count))
    if name == _LAYOUT_ALL_SINGLE:
        return ["single"] * count
    if count <= 0:
        return []
    return ["single"] * max(0, count - 1) + ["weighted"]


def _bounded_eof_model_header(
    data: bytes,
    report: Any,
    record: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Read a Gen1 deformable header only for an exact typed record overshooting EOF."""
    if int(record.get("masked_section_type") or 0) != base.SECTION_MODEL:
        return None, None
    start = int(record.get("payload_start") or -1)
    claimed_end = int(record.get("payload_end") or -1)
    if start < 0 or start + 16 > len(data) or claimed_end <= len(data):
        return None, None
    overshoot = claimed_end - len(data)
    if overshoot <= 0 or overshoot > _MAX_MODEL_EOF_OVERSHOOT:
        return None, None
    try:
        reader = base.BinaryReader(
            data,
            start=start,
            end=len(data),
            section_start=start,
            section_end=len(data),
        )
        model = base._read_model_header(reader, report, record)
    except Exception:
        return None, None
    if int(model.get("model_type") or -1) != base.CCS_MODEL_DEFORMABLE:
        return None, None
    return model, {
        "method": "exact typed indexed Model header + actual EOF bound",
        "claimed_payload_end": claimed_end,
        "bounded_payload_end": len(data),
        "outer_size_overshoot": overshoot,
        "original_errors": list(record.get("errors") or []),
    }


def _parse_layout_candidate(
    data: bytes,
    record: dict[str, Any],
    model_header: dict[str, Any],
    layout_name: str,
) -> dict[str, Any]:
    """Decode one exact, bounded layout candidate and preserve its valid prefix."""
    model = copy.deepcopy(model_header)
    model["submodels"] = []
    count = max(0, int(model.get("submodel_count") or 0))
    layout = _layout_for_count(count, layout_name)
    start = int(record.get("payload_start") or 0) + 16
    end = min(len(data), int(record.get("payload_end") or 0))
    cursor = start
    failures: list[dict[str, Any]] = []

    for index, kind in enumerate(layout):
        try:
            if kind == "weighted":
                submodel, cursor = v1._parse_weighted_submodel(
                    data,
                    cursor,
                    end,
                    index=index,
                    vertex_scale=float(model.get("vertex_scale") or 0.0),
                )
            else:
                submodel, cursor = v1._parse_single_weight_submodel(
                    data,
                    cursor,
                    end,
                    index=index,
                    vertex_scale=float(model.get("vertex_scale") or 0.0),
                )
            model["submodels"].append(submodel)
        except Exception as exc:
            failures.append(
                {
                    "submodel_index": index,
                    "layout_kind": kind,
                    "offset": cursor,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            break

    decoded = model["submodels"]
    vertices = sum(int(row.get("decoded_vertex_count") or 0) for row in decoded)
    triangles = sum(int(row.get("triangle_count") or 0) for row in decoded)
    complete = len(decoded) == len(layout) and not failures and cursor <= end
    unconsumed = max(0, end - cursor)
    overflow = max(0, cursor - end)
    expected_layout = layout_name == _LAYOUT_STANDARD
    exact_consumption = complete and unconsumed == 0 and overflow == 0

    # Completion and payload fit outrank raw geometry volume. The established layout
    # wins exact ties. A smaller bounded remainder wins between two complete layouts.
    score = (
        1 if exact_consumption else 0,
        1 if complete else 0,
        len(decoded),
        -overflow,
        -unconsumed,
        1 if expected_layout else 0,
        triangles,
        vertices,
    )
    return {
        "layout": layout_name,
        "model": model,
        "start": start,
        "end": end,
        "cursor": cursor,
        "complete": complete,
        "exact_consumption": exact_consumption,
        "decoded_submodels": len(decoded),
        "expected_submodels": len(layout),
        "vertices": vertices,
        "triangles": triangles,
        "unconsumed_bytes": unconsumed,
        "overflow_bytes": overflow,
        "failures": failures,
        "score": score,
    }


def _select_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    viable = [candidate for candidate in candidates if int(candidate.get("decoded_submodels") or 0) > 0]
    if not viable:
        details = "; ".join(
            f"{candidate.get('layout')}: {(candidate.get('failures') or [{}])[0].get('error', 'no geometry')}"
            for candidate in candidates
        )
        raise v1.DeformableDecodeError(details or "no bounded deformable layout decoded geometry")
    return max(viable, key=lambda candidate: tuple(candidate.get("score") or ()))


def parse_gen1_deformable_model(
    data: bytes,
    record: dict[str, Any],
    model_header: dict[str, Any],
) -> dict[str, Any]:
    if str(model_header.get("generation") or "") != "Gen1":
        raise v1.DeformableDecodeError("Gen1 deformable parser cannot decode non-Gen1 model")
    if int(model_header.get("model_type") or -1) != base.CCS_MODEL_DEFORMABLE:
        raise v1.DeformableDecodeError("record is not a Gen1 deformable model")

    count = max(0, int(model_header.get("submodel_count") or 0))
    if count == 0:
        model = copy.deepcopy(model_header)
        model.update(
            {
                "submodels": [],
                "parse_status": "parsed_deformable_gen1",
                "parser_mode": "studioccs_gen1_deformable_tolerant",
                "deformable_layout": _LAYOUT_STANDARD,
                "deformable_recovery": {"used": False, "reason": "empty model"},
                "decoded_vertex_count": 0,
                "triangle_count": 0,
            }
        )
        return model

    candidates = [
        _parse_layout_candidate(data, record, model_header, _LAYOUT_STANDARD),
        _parse_layout_candidate(data, record, model_header, _LAYOUT_ALL_SINGLE),
    ]
    selected = _select_candidate(candidates)
    model = selected["model"]
    selected_layout = str(selected["layout"])
    normal_complete = selected_layout == _LAYOUT_STANDARD and bool(selected["complete"])
    complete = bool(selected["complete"])
    status = (
        "parsed_deformable_gen1"
        if normal_complete
        else "parsed_deformable_gen1_recovered"
        if complete
        else "parsed_deformable_gen1_partial"
    )
    warnings = list(model.get("warnings") or [])
    if selected["unconsumed_bytes"]:
        warnings.append(f"{selected['unconsumed_bytes']} unconsumed byte(s) remain in deformable model payload")
    for failure in selected["failures"]:
        warnings.append(
            f"submodel {failure['submodel_index']} {failure['layout_kind']} decode stopped at "
            f"0x{int(failure['offset']):X}: {failure['error']}"
        )
    if not normal_complete:
        warnings.append(
            f"tolerant deformable recovery selected {selected_layout}: "
            f"{selected['decoded_submodels']}/{selected['expected_submodels']} submodels, "
            f"{selected['vertices']} vertices, {selected['triangles']} triangles"
        )

    model.update(
        {
            "parse_status": status,
            "parser_mode": "studioccs_gen1_deformable_tolerant",
            "deformable_layout": selected_layout,
            "warnings": warnings,
            "decoded_vertex_count": int(selected["vertices"]),
            "triangle_count": int(selected["triangles"]),
            "deformable_recovery": {
                "used": not normal_complete,
                "complete": complete,
                "selected_layout": selected_layout,
                "decoded_submodels": int(selected["decoded_submodels"]),
                "expected_submodels": int(selected["expected_submodels"]),
                "unconsumed_bytes": int(selected["unconsumed_bytes"]),
                "failures": list(selected["failures"]),
                "candidates": [
                    {
                        "layout": candidate["layout"],
                        "complete": bool(candidate["complete"]),
                        "exact_consumption": bool(candidate["exact_consumption"]),
                        "decoded_submodels": int(candidate["decoded_submodels"]),
                        "expected_submodels": int(candidate["expected_submodels"]),
                        "vertices": int(candidate["vertices"]),
                        "triangles": int(candidate["triangles"]),
                        "unconsumed_bytes": int(candidate["unconsumed_bytes"]),
                        "failures": list(candidate["failures"]),
                    }
                    for candidate in candidates
                ],
            },
        }
    )
    return model


def decode_with_gen1_deformables(path: str | Path):
    """Decode typed structure and retain safely recovered deformable geometry."""
    source = Path(path).expanduser()
    data = source.read_bytes()
    report = base.decode(source)
    if str(report.header.get("generation") or "") != "Gen1":
        return report

    recovered_models = 0
    partial_models = 0
    eof_clamped_models = 0
    for record in report.records:
        if int(record.get("masked_section_type") or 0) != base.SECTION_MODEL:
            continue
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        eof_recovery: dict[str, Any] | None = None
        if model is None:
            model, eof_recovery = _bounded_eof_model_header(data, report, record)
        if not model or int(model.get("model_type") or -1) != base.CCS_MODEL_DEFORMABLE:
            continue
        bounded_record = dict(record)
        if eof_recovery is not None:
            bounded_record["payload_end"] = len(data)
        try:
            parsed = parse_gen1_deformable_model(data, bounded_record, model)
            if eof_recovery is not None:
                recovery = dict(parsed.get("deformable_recovery") or {})
                recovery.update(eof_recovery)
                recovery["used"] = True
                recovery["eof_outer_size_recovered"] = True
                parsed["deformable_recovery"] = recovery
                parsed["parse_status"] = "parsed_deformable_gen1_recovered"
                parsed.setdefault("warnings", []).append(
                    f"outer Model size exceeded EOF by {eof_recovery['outer_size_overshoot']} byte(s); "
                    "inner header and bounded submodel streams were retained"
                )
                record["errors"] = []
                record.setdefault("warnings", []).extend(eof_recovery["original_errors"])
                record["eof_model_recovery"] = dict(eof_recovery)
                eof_clamped_models += 1
            record["model"] = parsed
            record["parse_status"] = parsed["parse_status"]
            recovery = parsed.get("deformable_recovery") or {}
            recovered_models += int(bool(recovery.get("used")))
            partial_models += int(parsed["parse_status"] == "parsed_deformable_gen1_partial")
            lookup = report.object_lookup.get(int(record.get("object_id") or -1))
            if isinstance(lookup, dict):
                lookup["model"] = parsed
        except Exception as exc:
            record.setdefault("errors", []).append(
                f"Gen1 tolerant deformable decode failed: {type(exc).__name__}: {exc}"
            )
            record["parse_status"] = "deformable_decode_error"

    report.setup.setdefault("deformable_recovery_v2", {})
    report.setup["deformable_recovery_v2"].update(
        {
            "recovered_models": recovered_models,
            "partial_models": partial_models,
            "eof_clamped_models": eof_clamped_models,
            "max_eof_overshoot": _MAX_MODEL_EOF_OVERSHOOT,
            "policy": (
                "exact typed EOF Model clamp, bounded standard layout, bounded all-single fallback, "
                "valid-prefix preservation"
            ),
        }
    )
    return report


def deformable_summary(path: str | Path) -> dict[str, Any]:
    report = decode_with_gen1_deformables(path)
    rows: list[dict[str, Any]] = []
    for record in report.records:
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if not model or int(model.get("model_type") or -1) != base.CCS_MODEL_DEFORMABLE:
            continue
        rows.append(
            {
                "object_id": record.get("object_id"),
                "object_name": record.get("object_name"),
                "parse_status": model.get("parse_status"),
                "layout": model.get("deformable_layout"),
                "submodels": len(model.get("submodels") or []),
                "vertices": int(model.get("decoded_vertex_count") or 0),
                "triangles": int(model.get("triangle_count") or 0),
                "recovery": dict(model.get("deformable_recovery") or {}),
                "warnings": list(model.get("warnings") or []),
                "errors": list(record.get("errors") or []),
            }
        )
    return {
        "source": str(path),
        "generation": report.header.get("generation"),
        "recovery": dict((report.setup or {}).get("deformable_recovery_v2") or {}),
        "models": rows,
    }

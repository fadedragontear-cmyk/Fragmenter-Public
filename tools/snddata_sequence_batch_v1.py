#!/usr/bin/env python3
"""Plan and render a bounded batch of evidence-backed SNDDATA sequence auditions.

The batch uses the authoritative corrected sample bridge before loading the music
catalog. It prioritizes observed Program Change routes, then explicit
channel-as-program hypotheses. Each sequence is attempted independently so one
renderer failure does not force another manual command cycle.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import snddata_sample_bridge_v1 as sample_bridge
import snddata_sample_generation_patch_v1 as sample_generation_patch

# Install the authoritative sample view before importing the v5 catalog/renderer.
sample_bridge.install()
sample_generation_patch.install()

import snddata_music_system_v5 as music_v5  # noqa: E402
from project_sound_v1 import sound_reports_root  # noqa: E402
from project_workspace_v1 import FragmenterProjectV1, load_project  # noqa: E402

REPORT_JSON = "snddata_sequence_batch_v1.json"
REPORT_TXT = "snddata_sequence_batch_v1.txt"
ROUTING_PRIORITY = {"program_change": 0, "channel_as_program": 1}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_renderable(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("status") or "") in {
        "renderable",
        "renderer_input_complete",
    }


def _note_bucket(note_count: int) -> tuple[int, int]:
    """Prefer representative, bounded sequences without requiring known duration."""
    if 4 <= note_count <= 128:
        return 0, abs(note_count - 48)
    if 129 <= note_count <= 512:
        return 1, note_count
    if 1 <= note_count <= 3:
        return 2, note_count
    return 3, note_count


def _route_rows(sequence: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for hypothesis in sequence.get("routing_hypotheses") or []:
        if not isinstance(hypothesis, dict):
            continue
        mode = str(hypothesis.get("mode") or "")
        if mode not in ROUTING_PRIORITY:
            continue
        for candidate in hypothesis.get("candidates") or []:
            if not isinstance(candidate, dict) or not _is_renderable(candidate):
                continue
            yield {
                "sequence_id": str(sequence.get("sequence_id") or ""),
                "sequence_offset": _int(sequence.get("resource_offset")),
                "routing_mode": mode,
                "routing_confidence": str(hypothesis.get("confidence") or ""),
                "routing_label": str(hypothesis.get("label") or ""),
                "program_resource_offset": _int(candidate.get("resource_offset")),
                "program_resource_hex": str(
                    candidate.get("resource_hex")
                    or f"0x{_int(candidate.get('resource_offset')):X}"
                ),
                "distance": _int(candidate.get("distance")),
                "note_on_count": _int(sequence.get("note_on_count")),
                "event_count": _int(sequence.get("event_count")),
                "track_count": _int(sequence.get("track_count")),
                "program_change_count": _int(sequence.get("program_change_count")),
                "required_program_indexes": list(
                    candidate.get("required_program_indexes") or []
                ),
                "required_sample_ids": list(candidate.get("required_sample_ids") or []),
                "matched_sample_ids": list(candidate.get("matched_sample_ids") or []),
                "candidate_status": str(candidate.get("status") or ""),
            }


def build_plan(
    catalog: dict[str, Any],
    *,
    limit: int = 10,
    per_program_resource_limit: int = 2,
) -> list[dict[str, Any]]:
    """Choose a diverse, deterministic audition batch from all renderable routes."""
    limit = max(1, int(limit))
    rows: list[dict[str, Any]] = []
    seen_sequences: set[str] = set()
    for sequence in catalog.get("sequences") or []:
        if not isinstance(sequence, dict):
            continue
        routes = sorted(
            _route_rows(sequence),
            key=lambda row: (
                ROUTING_PRIORITY[row["routing_mode"]],
                row["distance"],
                row["program_resource_offset"],
            ),
        )
        if not routes:
            continue
        # One explicit route per sequence. Prefer observed Program Change when it
        # is actually complete; otherwise use the best complete channel hypothesis.
        rows.append(routes[0])
        seen_sequences.add(routes[0]["sequence_id"])

    def rank(row: dict[str, Any]) -> tuple[Any, ...]:
        bucket, note_rank = _note_bucket(_int(row.get("note_on_count")))
        return (
            ROUTING_PRIORITY[str(row.get("routing_mode"))],
            bucket,
            note_rank,
            _int(row.get("distance")),
            _int(row.get("sequence_offset")),
            _int(row.get("program_resource_offset")),
        )

    ranked = sorted(rows, key=rank)
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    resource_counts: dict[int, int] = {}
    for row in ranked:
        resource = _int(row.get("program_resource_offset"))
        if resource_counts.get(resource, 0) >= max(1, per_program_resource_limit):
            deferred.append(row)
            continue
        selected.append(row)
        resource_counts[resource] = resource_counts.get(resource, 0) + 1
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        selected.extend(deferred[: limit - len(selected)])

    for index, row in enumerate(selected, 1):
        row["batch_index"] = index
        row["selection_reason"] = (
            "observed Program Change with complete Program/slot/sample inputs"
            if row["routing_mode"] == "program_change"
            else "explicit channel-as-program hypothesis with complete Program/slot/sample inputs"
        )
    return selected


def render_plan(
    project: FragmenterProjectV1,
    plan: list[dict[str, Any]],
    *,
    master_gain: float = 1.0,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in plan:
        result_row = dict(row)
        try:
            rendered = music_v5.render_sequence(
                project,
                row["sequence_id"],
                program_resource_offset=_int(row["program_resource_offset"]),
                routing_mode=str(row["routing_mode"]),
                master_gain=float(master_gain),
            )
            result_row.update(
                {
                    "status": "rendered",
                    "output_path": str(rendered.get("output_path") or ""),
                    "duration": rendered.get("duration"),
                    "frames": rendered.get("frames"),
                    "sample_rate": rendered.get("sample_rate"),
                    "error": "",
                    "missing": [],
                }
            )
        except Exception as exc:  # Each route is an independent experiment.
            result_row.update(
                {
                    "status": "failed",
                    "output_path": "",
                    "duration": None,
                    "frames": 0,
                    "sample_rate": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                    "missing": list(getattr(exc, "missing", []) or []),
                }
            )
        results.append(result_row)
    return results


def render_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "SNDDATA SEQUENCE AUDITION BATCH",
        "================================",
        f"Catalog: {payload.get('catalog_path')}",
        f"Planned: {summary.get('planned', 0)}",
        f"Rendered: {summary.get('rendered', 0)}",
        f"Failed: {summary.get('failed', 0)}",
        f"Program Change routes: {summary.get('program_change_routes', 0)}",
        f"Channel routes: {summary.get('channel_as_program_routes', 0)}",
        "",
    ]
    for row in payload.get("results") or []:
        lines.append(
            f"[{_int(row.get('batch_index')):02d}] {str(row.get('status') or '').upper():8} "
            f"{row.get('sequence_id')} -> {row.get('program_resource_hex')} "
            f"mode={row.get('routing_mode')} notes={row.get('note_on_count')}"
        )
        if row.get("output_path"):
            lines.append(f"     WAV: {row['output_path']}")
        if row.get("error"):
            lines.append(f"     Error: {row['error']}")
        if row.get("missing"):
            lines.append(f"     Missing: {', '.join(str(value) for value in row['missing'])}")
    lines.extend(
        [
            "",
            "Interpretation:",
            "- Rendered means the current parser, route, samples, and experimental renderer produced PCM.",
            "- It does not prove authentic root key, loops, envelopes, controllers, or original game timing.",
            "- Failed rows are retained so the next code change targets a named renderer wall.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_batch(
    project: FragmenterProjectV1,
    *,
    limit: int = 10,
    master_gain: float = 1.0,
    plan_only: bool = False,
    refresh_catalog: bool = True,
) -> dict[str, Any]:
    if refresh_catalog or not music_v5.catalog_is_current(project):
        music_v5.analyze_project_snddata(project)
    catalog = music_v5.load_catalog(project)
    plan = build_plan(catalog, limit=limit)
    results = [dict(row, status="planned") for row in plan]
    if not plan_only:
        results = render_plan(project, plan, master_gain=master_gain)

    payload = {
        "version": 1,
        "project": str(project.project_path),
        "catalog_path": str(music_v5.catalog_path(project)),
        "plan_only": bool(plan_only),
        "summary": {
            "planned": len(plan),
            "rendered": sum(row.get("status") == "rendered" for row in results),
            "failed": sum(row.get("status") == "failed" for row in results),
            "program_change_routes": sum(
                row.get("routing_mode") == "program_change" for row in plan
            ),
            "channel_as_program_routes": sum(
                row.get("routing_mode") == "channel_as_program" for row in plan
            ),
        },
        "results": results,
        "format_claim": (
            "Audition evidence only. A rendered WAV does not establish authentic instrument semantics."
        ),
    }
    reports = sound_reports_root(project)
    json_path = reports / REPORT_JSON
    txt_path = reports / REPORT_TXT
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    txt_path.write_text(render_report(payload), encoding="utf-8")
    payload["report_json"] = str(json_path)
    payload["report_txt"] = str(txt_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Path to project.json or the project workspace")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--master-gain", type=float, default=1.0)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-refresh", action="store_true")
    args = parser.parse_args(argv)

    result = run_batch(
        load_project(args.project),
        limit=args.limit,
        master_gain=args.master_gain,
        plan_only=args.plan_only,
        refresh_catalog=not args.no_refresh,
    )
    print(render_report(result), end="")
    print(f"Report JSON: {result['report_json']}")
    print(f"Report TXT: {result['report_txt']}")
    return 0 if result["summary"]["planned"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

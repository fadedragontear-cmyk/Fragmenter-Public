#!/usr/bin/env python3
"""Run the still-relevant SNDDATA research gates as one deterministic checkpoint.

This command replaces the manual one-probe-at-a-time loop. It refreshes the
current sample setup audit, PSound length/order comparison, decoded-PCM identity,
raw-span evidence, sequence catalog, and reconstruction-readiness report. It then
writes one compact decision report and a reports-only ZIP.

Retired exploratory probes (wrapper placement, start phase, and unresolved suffix
experiments) are intentionally excluded from the standard checkpoint. They remain
available for historical investigation but should not be rerun unless a regression
specifically points back to them.
"""
from __future__ import annotations

import argparse
import csv
import json
import zipfile
from pathlib import Path
from typing import Any, Iterable

import psound_alignment_audit_v1
import psound_fragmenter_raw_span_audit_v2
import psound_pcm_identity_v1
import snddata_music_system_v5
import snddata_reconstruction_readiness_v1
import snddata_sample_setup_audit_v4
from compare_psound_to_latest_fragmenter_v1 import find_latest_fragmenter_report
from project_workspace_v1 import load_project
from psound_reference_manifest_v1 import build_manifest

CHECKPOINT_VERSION = 1
SUMMARY_JSON = "snddata_research_checkpoint_v1.json"
SUMMARY_TXT = "snddata_research_checkpoint_v1.txt"
BUNDLE_ZIP = "snddata_research_checkpoint_v1.zip"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )
    return path


def _project_from_report(report_path: Path) -> Path | None:
    """Resolve <project>/project.json from <project>/reports/audio/<report>.json."""
    try:
        candidate = report_path.parents[2] / "project.json"
    except IndexError:
        return None
    return candidate if candidate.is_file() else None


def build_summary(
    *,
    fragmenter_report: Path,
    setup: dict[str, Any],
    psound_manifest: dict[str, Any],
    alignment: dict[str, Any],
    pcm_identity: dict[str, Any],
    raw_span: dict[str, Any],
    music_refresh: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
) -> dict[str, Any]:
    setup_summary = dict(setup.get("summary") or {})
    blocked_banks = _int(setup_summary.get("body_base_failure_banks"))
    blocked_rows = _int(setup_summary.get("body_base_blocked_rows"))
    sample_rows = len(setup.get("rows") or [])
    extraction_closed = bool(
        setup.get("source_sha256_matches")
        and setup.get("metadata_span_gate") == "pass"
        and setup.get("body_base_gate") == "pass"
        and setup.get("structural_gate") == "pass"
        and setup.get("classification_gate") == "pass"
        and sample_rows > 0
        and blocked_banks == 0
        and blocked_rows == 0
    )

    match_methods = {
        str(key): _int(value)
        for key, value in dict(pcm_identity.get("match_method_counts") or {}).items()
    }
    unique_methods = {
        str(key): _int(value)
        for key, value in dict(pcm_identity.get("unique_match_method_counts") or {}).items()
    }
    unique_pcm_matches = sum(unique_methods.values())

    music = dict((readiness or {}).get("music") or {})
    readiness_state = dict((readiness or {}).get("readiness") or {})
    refreshed_sequences = _int((music_refresh or {}).get("sequence_resources"))
    if not refreshed_sequences:
        refreshed_sequences = _int((music_refresh or {}).get("sequences"))
    sequence_count = _int(music.get("sequences")) or refreshed_sequences
    renderable = _int(music.get("renderable_candidates")) or _int(
        (music_refresh or {}).get("preferred_renderable_candidates")
    )
    preview_rendered = bool(music.get("last_preview_rendered"))

    if not extraction_closed:
        next_action = (
            "Stop sequence work and repair the extraction contradiction reported by the setup gate."
        )
    elif renderable > 0 and not preview_rendered:
        next_action = (
            "Render and listen to one representative fully covered sequence, then save the accepted "
            "sequence-to-program routing. Do not rerun sample setup."
        )
    elif renderable > 0:
        next_action = (
            "Compare the rendered sequence against in-game or emulator audio and resolve root-key, "
            "loop, envelope, note-off, and controller semantics."
        )
    else:
        next_action = (
            "Inspect the refreshed sequence/program/sample routing catalog; sample extraction is no longer "
            "the blocker."
        )

    return {
        "version": CHECKPOINT_VERSION,
        "fragmenter_report": str(fragmenter_report),
        "source_sha256_matches": bool(setup.get("source_sha256_matches")),
        "decisions": {
            "sample_extraction_phase_closed": extraction_closed,
            "rerun_sample_setup_only_when": [
                "canonical snddata.bin SHA-256 changes",
                "sample body resolver or trim policy changes",
                "a later gate reports a concrete sample-boundary regression",
            ],
            "standard_checkpoint_excludes": [
                "wrapper-placement probe",
                "start-phase probe",
                "unresolved-suffix probe",
            ],
            "next_action": next_action,
        },
        "sample_setup": {
            "sample_rows": sample_rows,
            "banks": len(setup.get("banks") or []),
            "metadata_span_gate": setup.get("metadata_span_gate"),
            "body_base_gate": setup.get("body_base_gate"),
            "structural_gate": setup.get("structural_gate"),
            "classification_gate": setup.get("classification_gate"),
            "blocked_banks": blocked_banks,
            "blocked_rows": blocked_rows,
            "remaining_unknowns": list(setup.get("remaining_unknowns") or []),
        },
        "psound_evidence": {
            "files_seen": _int(psound_manifest.get("file_count")),
            "audio_candidates": _int(psound_manifest.get("audio_candidate_count")),
            "same_index_identity_status": alignment.get(
                "same_index_identity_hypothesis_status"
            ),
            "monotonic_exact_payload_anchors": _int(
                alignment.get("monotonic_exact_payload_anchor_count")
            ),
            "pcm_match_methods": match_methods,
            "unique_pcm_match_methods": unique_methods,
            "unique_pcm_matches": unique_pcm_matches,
            "raw_span_anchors": _int(raw_span.get("raw_span_anchor_count")),
            "raw_span_coverage": raw_span.get(
                "raw_span_anchor_coverage_of_psound"
            ),
            "payload_relations": dict(
                raw_span.get("payload_relation_counts") or {}
            ),
            "loop_expansion_candidates": len(
                raw_span.get("psound_loop_expansion_candidates") or []
            ),
        },
        "sequence_reconstruction": {
            "catalog_refreshed": music_refresh is not None,
            "sequences": sequence_count,
            "renderable_candidates": renderable,
            "last_preview_rendered": preview_rendered,
            "playback_reconstruction": readiness_state.get(
                "playback_reconstruction", "not_evaluated"
            ),
            "binary_reconstruction": readiness_state.get(
                "binary_reconstruction", "not_evaluated"
            ),
            "missing_capabilities": list(
                (readiness or {}).get("missing_reconstruction_capabilities") or []
            ),
        },
    }


def render_summary(summary: dict[str, Any]) -> str:
    decisions = summary["decisions"]
    setup = summary["sample_setup"]
    psound = summary["psound_evidence"]
    sequence = summary["sequence_reconstruction"]
    lines = [
        "SNDDATA RESEARCH CHECKPOINT",
        "===========================",
        f"Fragmenter report: {summary['fragmenter_report']}",
        f"Source SHA-256 matches: {summary['source_sha256_matches']}",
        "",
        "Sample extraction",
        "-----------------",
        f"Closed: {decisions['sample_extraction_phase_closed']}",
        f"Rows/banks: {setup['sample_rows']} / {setup['banks']}",
        f"Gates: metadata={setup['metadata_span_gate']} body={setup['body_base_gate']} "
        f"structural={setup['structural_gate']} classification={setup['classification_gate']}",
        f"Blocked banks/rows: {setup['blocked_banks']} / {setup['blocked_rows']}",
        "",
        "PSound evidence",
        "---------------",
        f"Files/audio candidates: {psound['files_seen']} / {psound['audio_candidates']}",
        f"Equal-index identity: {psound['same_index_identity_status']}",
        f"Monotonic exact-length anchors: {psound['monotonic_exact_payload_anchors']}",
        f"Unique PCM matches: {psound['unique_pcm_matches']} {psound['unique_pcm_match_methods']}",
        f"Raw-span anchors/coverage: {psound['raw_span_anchors']} / {psound['raw_span_coverage']}",
        f"Payload relations: {psound['payload_relations']}",
        f"Loop-expansion candidates: {psound['loop_expansion_candidates']}",
        "",
        "Sequence reconstruction",
        "-----------------------",
        f"Catalog refreshed: {sequence['catalog_refreshed']}",
        f"Sequences/renderable candidates: {sequence['sequences']} / {sequence['renderable_candidates']}",
        f"Preview already rendered: {sequence['last_preview_rendered']}",
        f"Playback reconstruction: {sequence['playback_reconstruction']}",
        f"Binary reconstruction: {sequence['binary_reconstruction']}",
        "",
        "Decision",
        "--------",
        decisions["next_action"],
        "",
        "Rerun sample setup only when:",
    ]
    lines.extend(f"- {value}" for value in decisions["rerun_sample_setup_only_when"])
    lines.extend(["", "Retired from the standard checkpoint:"])
    lines.extend(f"- {value}" for value in decisions["standard_checkpoint_excludes"])
    return "\n".join(lines) + "\n"


def _bundle_reports(target: Path, files: Iterable[Path]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        seen: set[str] = set()
        for path in files:
            if not path.is_file() or path.suffix.casefold() not in {".json", ".csv", ".txt"}:
                continue
            arcname = path.name
            if arcname in seen:
                arcname = f"{path.parent.name}_{arcname}"
            seen.add(arcname)
            archive.write(path, arcname)
    return target


def run_checkpoint(
    *,
    psound_source: Path,
    search_root: Path,
    output: Path,
    project_path: Path | None = None,
    refresh_music: bool = True,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    report_path = find_latest_fragmenter_report(
        search_root, require_corrected_trim=True
    )

    setup_output = output / "sample_setup"
    setup = snddata_sample_setup_audit_v4.audit_report(report_path)
    setup_json = _write_json(
        setup_output / snddata_sample_setup_audit_v4.REPORT_NAME, setup
    )
    setup_csv = _write_csv(
        setup_output / snddata_sample_setup_audit_v4.CSV_NAME,
        [dict(row) for row in setup.get("rows") or [] if isinstance(row, dict)],
    )

    psound_output = output / "psound"
    psound_manifest = build_manifest(
        psound_source,
        psound_output,
        fragmenter_report=report_path,
    )
    comparison_json = psound_output / "psound_vs_fragmenter_by_order.json"
    comparison_rows = [
        dict(row)
        for row in _load_json(comparison_json)
        if isinstance(row, dict)
    ]

    alignment = psound_alignment_audit_v1.audit(comparison_rows)
    alignment_json = _write_json(
        psound_output / "psound_fragmenter_alignment_audit.json", alignment
    )
    alignment_csv = _write_csv(
        psound_output / "psound_fragmenter_exact_payload_anchors.csv",
        alignment.get("anchors") or [],
    )

    pcm_identity = psound_pcm_identity_v1.map_pcm_identity(
        psound_source, report_path, psound_output
    )
    raw_span = psound_fragmenter_raw_span_audit_v2.audit(
        comparison_rows, pcm_identity
    )
    raw_json = _write_json(
        psound_output / "psound_fragmenter_raw_span_audit.json", raw_span
    )
    raw_csv = _write_csv(
        psound_output / "psound_fragmenter_raw_span_anchors.csv",
        raw_span.get("anchors") or [],
    )

    resolved_project = project_path or _project_from_report(report_path)
    music_refresh: dict[str, Any] | None = None
    readiness: dict[str, Any] | None = None
    readiness_paths: list[Path] = []
    if resolved_project and resolved_project.is_file():
        project = load_project(resolved_project)
        if refresh_music:
            music_refresh = snddata_music_system_v5.analyze_project_snddata(project)
        readiness = snddata_reconstruction_readiness_v1.audit_project(
            project, write=True
        )
        project_reports = snddata_reconstruction_readiness_v1.project_paths(project)
        readiness_paths.extend(
            [
                project_reports["readiness_json"],
                project_reports["readiness_txt"],
                project_reports["music_catalog"],
                project_reports["music_preview"],
            ]
        )

    summary = build_summary(
        fragmenter_report=report_path,
        setup=setup,
        psound_manifest=psound_manifest,
        alignment=alignment,
        pcm_identity=pcm_identity,
        raw_span=raw_span,
        music_refresh=music_refresh,
        readiness=readiness,
    )
    summary["paths"] = {
        "output": str(output),
        "project": str(resolved_project) if resolved_project else None,
    }
    summary_json = _write_json(output / SUMMARY_JSON, summary)
    summary_txt = output / SUMMARY_TXT
    summary_txt.write_text(render_summary(summary), encoding="utf-8")

    bundle_candidates = [
        summary_json,
        summary_txt,
        setup_json,
        setup_csv,
        psound_output / "psound_reference_manifest.json",
        psound_output / "psound_reference_manifest.csv",
        comparison_json,
        psound_output / "psound_vs_fragmenter_by_order.csv",
        alignment_json,
        alignment_csv,
        psound_output / "psound_fragmenter_pcm_identity.json",
        psound_output / "psound_fragmenter_pcm_identity.csv",
        raw_json,
        raw_csv,
        *readiness_paths,
    ]
    bundle = _bundle_reports(output / BUNDLE_ZIP, bundle_candidates)
    summary["paths"].update(
        {
            "summary_json": str(summary_json),
            "summary_txt": str(summary_txt),
            "bundle_zip": str(bundle),
        }
    )
    _write_json(summary_json, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--psound-source",
        default=r"C:\games\areaserver\FragmentModKit\PSound201",
    )
    parser.add_argument("--search-root", default=str(Path.cwd().parent))
    parser.add_argument("--project")
    parser.add_argument(
        "--output",
        default=str(Path.cwd() / "diagnostics" / "snddata_research_checkpoint"),
    )
    parser.add_argument(
        "--skip-music-refresh",
        action="store_true",
        help="Keep the current sequence catalog instead of rebuilding it.",
    )
    args = parser.parse_args(argv)

    summary = run_checkpoint(
        psound_source=Path(args.psound_source).expanduser().resolve(),
        search_root=Path(args.search_root).expanduser().resolve(),
        output=Path(args.output).expanduser().resolve(),
        project_path=(
            Path(args.project).expanduser().resolve() if args.project else None
        ),
        refresh_music=not args.skip_music_refresh,
    )
    print(render_summary(summary), end="")
    print(f"Summary JSON: {summary['paths']['summary_json']}")
    print(f"Reports-only ZIP: {summary['paths']['bundle_zip']}")
    return 0 if summary["decisions"]["sample_extraction_phase_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

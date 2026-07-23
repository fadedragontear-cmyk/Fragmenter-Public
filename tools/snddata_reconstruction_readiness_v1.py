#!/usr/bin/env python3
"""Audit SNDDATA extraction, playback reconstruction, safe patching, and rebuild readiness.

This tool intentionally distinguishes three different goals:

* corrected sample extraction from the original SNDDATA;
* experimental music reconstruction to a preview WAV;
* binary reconstruction/reinsertion into a game-usable SNDDATA.

Only the first two are currently implemented. The existing editor can safely patch
validated one-byte SCEIProg fields in a same-size copy, but that is not a serializer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import snddata_parser
from project_workspace_v1 import FragmenterProjectV1, WORKSPACE_PATHS, load_project
from snddata_editor import SnddataEditor

REPORT_JSON = "snddata_reconstruction_readiness_v1.json"
REPORT_TXT = "snddata_reconstruction_readiness_v1.txt"
NOOP_PROOF_JSON = "snddata_noop_roundtrip_proof_v1.json"
SAMPLE_REPORT = "snddata_sample_library.json"
MUSIC_CATALOG = "snddata_music_system_v5.json"
MUSIC_PREVIEW = "music_preview_last_v5.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _workspace(project: FragmenterProjectV1, key: str) -> Path:
    return Path(project.workspace_dir).expanduser() / WORKSPACE_PATHS[key]


def project_paths(project: FragmenterProjectV1) -> dict[str, Path]:
    reports = _workspace(project, "audio_reports")
    return {
        "source": _workspace(project, "audio_source") / "data" / "snddata.bin",
        "samples": _workspace(project, "extracted_audio") / "snddata" / "samples",
        "reports": reports,
        "sample_report": reports / SAMPLE_REPORT,
        "music_catalog": reports / MUSIC_CATALOG,
        "music_preview": reports / MUSIC_PREVIEW,
        "noop_proof": reports / NOOP_PROOF_JSON,
        "readiness_json": reports / REPORT_JSON,
        "readiness_txt": reports / REPORT_TXT,
        "reconstruction_work": _workspace(project, "audio_work") / "reconstruction",
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _section_counts(groups: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for group in groups:
        for section in getattr(group, "sections", ()):
            tag = snddata_parser.SECTION_TAGS.get(getattr(section, "signature", b""), "unknown")
            counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items()))


def evaluate_sample_report(
    report: dict[str, Any],
    *,
    source_sha256: str = "",
    check_outputs: bool = True,
) -> dict[str, Any]:
    rows = [row for row in report.get("samples") or [] if isinstance(row, dict)]
    summary = dict(report.get("summary") or {})
    policy_version = int((report.get("sample_boundary_policy") or {}).get("version") or 0)
    layout_version = int((report.get("layout") or {}).get("version") or 0)
    report_sha256 = str(report.get("source_sha256") or "")
    source_current = bool(source_sha256 and report_sha256 == source_sha256)
    failed_rows = [row for row in rows if row.get("errors")]
    sample_zero_rows = [
        row
        for row in rows
        if int(row.get("index", row.get("sample_id", -1)) or 0) == 0
    ]
    sample_zero_failures = [row for row in sample_zero_rows if row.get("errors")]
    corrected_rows = [
        row
        for row in rows
        if "phase correction" in str(row.get("boundary_source") or "").casefold()
        or int(row.get("stream_phase_shift") or 0) > 0
    ]
    output_rows = [row for row in rows if str(row.get("output_path") or "")]
    outputs_present = (
        sum(
            Path(str(row.get("output_path") or "")).is_file()
            for row in output_rows
            if not row.get("errors")
        )
        if check_outputs
        else int(summary.get("decoded_wavs") or 0)
    )
    phase_evaluated = int(summary.get("phase_evaluated_banks") or 0)
    phase_corrected = int(summary.get("phase_corrected_banks") or 0)
    if not phase_evaluated:
        banks = [bank for bank in report.get("banks") or [] if isinstance(bank, dict)]
        phase_evaluated = sum(isinstance(bank.get("stream_phase"), dict) for bank in banks)
        phase_corrected = sum(
            bool((bank.get("stream_phase") or {}).get("applied")) for bank in banks
        )

    if not report:
        status = "missing"
    elif source_sha256 and not source_current:
        status = "stale_source"
    elif policy_version < 2 or layout_version < 2:
        status = "legacy_needs_regeneration"
    elif sample_zero_failures:
        status = "sample_zero_boundary_regression"
    elif failed_rows:
        status = "corrected_partial"
    else:
        status = "ready"

    if policy_version < 2 or layout_version < 2:
        half_offset = "not_regenerated_with_fix"
    elif sample_zero_failures:
        half_offset = "still_failing_sample_zero"
    elif phase_corrected > 0:
        half_offset = "verified_by_corrected_report"
    else:
        half_offset = "policy_active_no_shift_required_or_detected"

    return {
        "status": status,
        "half_offset_fix_status": half_offset,
        "report_source_sha256": report_sha256,
        "source_current": source_current,
        "sample_boundary_policy_version": policy_version,
        "layout_version": layout_version,
        "sample_rows": len(rows) or int(summary.get("sample_rows") or 0),
        "decoded_wavs": int(summary.get("decoded_wavs") or outputs_present),
        "outputs_present_now": outputs_present,
        "failed_samples": len(failed_rows) or int(summary.get("failed_samples") or 0),
        "sample_zero_rows": len(sample_zero_rows),
        "sample_zero_failures": len(sample_zero_failures),
        "phase_evaluated_banks": phase_evaluated,
        "phase_corrected_banks": phase_corrected,
        "phase_corrected_rows": len(corrected_rows),
        "flat_unique_source_spans": int(summary.get("flat_unique_source_spans") or 0),
        "flat_playable_wavs": int(summary.get("flat_playable_wavs") or 0),
    }


def evaluate_music_catalog(
    catalog: dict[str, Any],
    *,
    source: Path,
    preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preview = preview or {}
    summary = dict(catalog.get("summary") or {})
    sequences = [row for row in catalog.get("sequences") or [] if isinstance(row, dict)]
    identity = dict(summary.get("source_identity") or {})
    source_current = bool(
        source.is_file()
        and int(identity.get("size") or -1) == source.stat().st_size
        and int(identity.get("mtime_ns") or -1) == source.stat().st_mtime_ns
    )
    renderable = sum(
        bool(
            isinstance(row.get("best_candidate"), dict)
            and row["best_candidate"].get("status") == "renderable"
        )
        for row in sequences
    )
    rendered = (
        str(preview.get("status") or "").casefold() == "rendered"
        and bool(preview.get("output_path"))
    )
    if not catalog:
        status = "missing"
    elif not source_current:
        status = "stale_source"
    elif not sequences:
        status = "no_sequences"
    elif not renderable:
        status = "no_renderable_candidates"
    elif not rendered:
        status = "ready_for_audition"
    else:
        status = "audition_rendered"
    return {
        "status": status,
        "source_current": source_current,
        "version": int(summary.get("version") or 0),
        "sequences": len(sequences),
        "renderable_candidates": int(
            summary.get("preferred_renderable_candidates") or renderable
        ),
        "program_change_sequences": int(
            summary.get("preferred_program_change_sequences") or 0
        ),
        "channel_as_program_sequences": int(
            summary.get("preferred_channel_as_program_sequences") or 0
        ),
        "last_preview_rendered": rendered,
        "last_preview_output": str(preview.get("output_path") or ""),
        "last_preview_duration": preview.get("duration"),
    }


def discover_homebrew_harness(project: FragmenterProjectV1) -> dict[str, Any]:
    candidates: list[str] = []
    for key, value in dict(project.settings or {}).items():
        if any(
            term in str(key).casefold()
            for term in ("homebrew", "pcsx2", "elf", "test_iso")
        ) and value:
            candidates.append(f"setting:{key}={value}")
    roots = (
        _workspace(project, "source"),
        _workspace(project, "audio_work") / "homebrew",
        Path(project.workspace_dir).expanduser() / "homebrew",
    )
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in ("*.elf", "*homebrew*.iso", "*test*.iso", "*.pnach"):
            for path in sorted(root.rglob(pattern))[:32]:
                candidates.append(str(path))
    deduplicated = list(dict.fromkeys(candidates))
    return {
        "status": "located" if deduplicated else "not_registered",
        "candidates": deduplicated[:64],
        "note": "A located harness is evidence only; V92 does not boot or patch it automatically.",
    }


def _gate(
    gate_id: str,
    label: str,
    status: str,
    evidence: str,
    next_action: str = "",
) -> dict[str, str]:
    return {
        "id": gate_id,
        "label": label,
        "status": status,
        "evidence": evidence,
        "next_action": next_action,
    }


def audit_project(
    project: FragmenterProjectV1,
    *,
    parse_source: bool = True,
    write: bool = True,
) -> dict[str, Any]:
    paths = project_paths(project)
    source = paths["source"]
    source_info: dict[str, Any] = {
        "path": str(source),
        "exists": source.is_file(),
        "size": source.stat().st_size if source.is_file() else 0,
        "mtime_ns": source.stat().st_mtime_ns if source.is_file() else 0,
        "sha256": _sha256(source) if source.is_file() else "",
    }

    structure: dict[str, Any] = {
        "status": "missing_source" if not source.is_file() else "not_parsed",
        "resources": 0,
        "valid_resources": 0,
        "section_counts": {},
        "error": "",
    }
    editable_field_count = 0
    editable_error = ""
    if source.is_file() and parse_source:
        try:
            data = source.read_bytes()
            groups = snddata_parser.parse_blob(data, source.as_posix())
            counts = _section_counts(groups)
            structure.update(
                {
                    "status": "parsed" if groups else "no_resources",
                    "resources": len(groups),
                    "valid_resources": sum(
                        bool(getattr(group, "valid", False)) for group in groups
                    ),
                    "section_counts": counts,
                }
            )
            editor = SnddataEditor(source, data, groups)
            editable_field_count = len(editor.fields)
        except Exception as exc:
            structure["status"] = "parse_error"
            structure["error"] = f"{type(exc).__name__}: {exc}"
            editable_error = structure["error"]

    sample_report = _load_json(paths["sample_report"])
    samples = evaluate_sample_report(
        sample_report,
        source_sha256=str(source_info["sha256"]),
        check_outputs=True,
    )
    catalog = _load_json(paths["music_catalog"])
    preview = _load_json(paths["music_preview"])
    music = evaluate_music_catalog(catalog, source=source, preview=preview)
    noop = _load_json(paths["noop_proof"])
    noop_verified = bool(
        noop.get("byte_identical") and noop.get("section_boundaries_confirmed")
    )
    homebrew = discover_homebrew_harness(project)

    gates = [
        _gate(
            "source",
            "Canonical SNDDATA source",
            "pass" if source.is_file() else "block",
            str(source),
            "Run Prepare Known Audio to extract data/snddata.bin."
            if not source.is_file()
            else "",
        ),
        _gate(
            "structure",
            "Container/program/sequence parser",
            "pass"
            if structure["status"] == "parsed" and structure["resources"]
            else "block",
            f"resources={structure['resources']} sections={structure['section_counts']}",
            "Run the SNDDATA evidence pipeline and inspect parse errors."
            if structure["status"] != "parsed"
            else "",
        ),
        _gate(
            "sample_generation",
            "Corrected sample generation",
            "pass" if samples["status"] in {"ready", "corrected_partial"} else "block",
            f"status={samples['status']} policy=v{samples['sample_boundary_policy_version']} layout=v{samples['layout_version']}",
            "Regenerate corrected samples from the Reconstruction tab."
            if samples["status"] not in {"ready", "corrected_partial"}
            else "",
        ),
        _gate(
            "sample_zero",
            "Half-and-half/sample-zero boundary regression",
            "pass"
            if samples["half_offset_fix_status"]
            in {
                "verified_by_corrected_report",
                "policy_active_no_shift_required_or_detected",
            }
            and samples["sample_zero_failures"] == 0
            else "block",
            f"{samples['half_offset_fix_status']}; sample-zero failures={samples['sample_zero_failures']}",
            "Rebuild samples, then audition sample 0 from several phase-corrected banks."
            if samples["sample_zero_failures"]
            else "",
        ),
        _gate(
            "music_catalog",
            "Sequence/program/sample routing catalog",
            "pass"
            if music["renderable_candidates"] > 0 and music["source_current"]
            else "warn",
            f"sequences={music['sequences']} renderable={music['renderable_candidates']} status={music['status']}",
            "Rebuild Mixer Index and save reviewed routing mappings."
            if not music["renderable_candidates"]
            else "",
        ),
        _gate(
            "audition",
            "Renderer audition",
            "pass" if music["last_preview_rendered"] else "warn",
            music["last_preview_output"] or "No current rendered preview report.",
            "Render and listen to a fully covered sequence; record the accepted routing mode."
            if not music["last_preview_rendered"]
            else "",
        ),
        _gate(
            "safe_patch",
            "Same-size validated field patching",
            "pass" if noop_verified else "warn",
            f"editable fields={editable_field_count}; no-op proof={'verified' if noop_verified else 'not run'}",
            "Run Write no-op round-trip proof before any homebrew test."
            if not noop_verified
            else "",
        ),
        _gate(
            "full_serializer",
            "Full binary reconstruction serializer",
            "block",
            "No writer currently serializes SCEIHead/Vagi/Smpl/Prog/Midi plus secondary ADPCM bodies.",
            "Implement byte-identical no-op serializers before sample replacement or sequence insertion.",
        ),
        _gate(
            "homebrew",
            "Homebrew/PCSX2 validation harness",
            "pass" if homebrew["status"] == "located" else "warn",
            f"status={homebrew['status']} candidates={len(homebrew['candidates'])}",
            "Register the ELF/test ISO/PCSX2 path in project settings or the workspace homebrew folder."
            if homebrew["status"] != "located"
            else "",
        ),
    ]

    playback_ready = (
        samples["status"] in {"ready", "corrected_partial"}
        and samples["sample_zero_failures"] == 0
        and music["renderable_candidates"] > 0
    )
    report = {
        "version": 1,
        "created_at": _utc_now(),
        "project": str(project.project_path),
        "workspace": str(Path(project.workspace_dir).expanduser()),
        "source": source_info,
        "structure": structure,
        "samples": samples,
        "music": music,
        "editing": {
            "editable_field_count": editable_field_count,
            "error": editable_error,
            "safe_in_place_program_patch_available": editable_field_count > 0,
            "noop_roundtrip_proof": noop,
            "noop_roundtrip_verified": noop_verified,
            "full_resource_serializer_available": False,
            "ps_adpcm_encoder_available": False,
            "scei_midi_writer_available": False,
        },
        "homebrew": homebrew,
        "readiness": {
            "corrected_extraction": samples["status"] in {"ready", "corrected_partial"},
            "playback_reconstruction": "ready_for_audition" if playback_ready else "blocked",
            "safe_field_patching": "verified"
            if noop_verified
            else "available_needs_noop_proof",
            "binary_reconstruction": "not_implemented",
        },
        "gates": gates,
        "missing_reconstruction_capabilities": [
            "Evidence-backed sample reference/root-key/loop/envelope semantics for accurate music rendering.",
            "Reviewed sequence-to-program routing saved for representative tracks.",
            "PS2 ADPCM encoder that preserves frame flags, terminators, loop markers, and exact alignment.",
            "Serializers for SCEIHead, SCEIVagi, SCEISmpl, SCEIProg, and SCEIMidi.",
            "Offset/size relocation and resource-boundary writer with byte-identical no-op output.",
            "Homebrew or emulator smoke test that loads one minimally changed bank before ISO reinsertion.",
        ],
        "recommended_order": [
            "Regenerate the v2 corrected sample catalog and verify sample-zero failures drop to zero.",
            "Audition a fully covered sequence and save its accepted routing hypothesis.",
            "Run the no-op same-size patch proof and retain its hashes/manifest.",
            "Register the existing homebrew/PCSX2 harness in the project.",
            "Implement a byte-identical no-op resource serializer before encoding new audio.",
            "Add PS-ADPCM encoding and replace one same-size sample in the homebrew harness.",
            "Only then attempt size-changing banks, MIDI writing, or production ISO reinsertion.",
        ],
    }
    if write:
        write_report(project, report)
    return report


def render_report(report: dict[str, Any]) -> str:
    source = report.get("source") or {}
    samples = report.get("samples") or {}
    music = report.get("music") or {}
    readiness = report.get("readiness") or {}
    lines = [
        "SNDDATA Reconstruction Readiness",
        "================================",
        "",
        f"Source: {source.get('path')}",
        f"Source present: {source.get('exists')}",
        f"Corrected extraction: {readiness.get('corrected_extraction')}",
        f"Half/half offset status: {samples.get('half_offset_fix_status')}",
        f"Boundary policy/layout: v{samples.get('sample_boundary_policy_version', 0)} / v{samples.get('layout_version', 0)}",
        f"Samples: {samples.get('sample_rows', 0)} rows, {samples.get('decoded_wavs', 0)} decoded, {samples.get('failed_samples', 0)} failed",
        f"Sample-zero failures: {samples.get('sample_zero_failures', 0)}",
        f"Phase-corrected banks: {samples.get('phase_corrected_banks', 0)}",
        f"Music catalog: {music.get('sequences', 0)} sequences, {music.get('renderable_candidates', 0)} renderable candidates",
        f"Last preview rendered: {music.get('last_preview_rendered')}",
        f"Playback reconstruction: {readiness.get('playback_reconstruction')}",
        f"Safe field patching: {readiness.get('safe_field_patching')}",
        f"Binary reconstruction: {readiness.get('binary_reconstruction')}",
        "",
        "Gates",
        "-----",
    ]
    for gate in report.get("gates") or []:
        lines.append(
            f"[{str(gate.get('status') or '').upper():5}] {gate.get('label')}: {gate.get('evidence')}"
        )
        if gate.get("next_action"):
            lines.append(f"        Next: {gate['next_action']}")
    lines.extend(("", "Recommended order", "-----------------"))
    for index, step in enumerate(report.get("recommended_order") or [], 1):
        lines.append(f"{index}. {step}")
    lines.extend(
        (
            "",
            "Important",
            "---------",
            "A same-size patch proof is not a full SNDDATA reconstruction. Keep the original source immutable.",
        )
    )
    return "\n".join(lines) + "\n"


def write_report(
    project: FragmenterProjectV1,
    report: dict[str, Any],
) -> tuple[Path, Path]:
    paths = project_paths(project)
    paths["reports"].mkdir(parents=True, exist_ok=True)
    paths["readiness_json"].write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["readiness_txt"].write_text(render_report(report), encoding="utf-8")
    return paths["readiness_json"], paths["readiness_txt"]


def regenerate_corrected_samples(project: FragmenterProjectV1) -> dict[str, Any]:
    from snddata_sample_library_v3 import extract_project_snddata_samples

    return extract_project_snddata_samples(project, clean=True)


def write_noop_roundtrip_proof(project: FragmenterProjectV1) -> dict[str, Any]:
    paths = project_paths(project)
    source = paths["source"]
    if not source.is_file():
        raise FileNotFoundError(source)
    work = paths["reconstruction_work"]
    work.mkdir(parents=True, exist_ok=True)
    output = work / "snddata_noop_copy.bin"
    manifest_json = paths["reports"] / "snddata_noop_patch_manifest.json"
    manifest_txt = paths["reports"] / "snddata_noop_patch_manifest.txt"
    editor = SnddataEditor.from_file(source)
    editor.export_patched(output, manifest_json, manifest_txt)
    source_hash = _sha256(source)
    output_hash = _sha256(output)
    manifest = _load_json(manifest_json)
    proof = {
        "version": 1,
        "created_at": _utc_now(),
        "source": str(source),
        "output": str(output),
        "source_size": source.stat().st_size,
        "output_size": output.stat().st_size,
        "source_sha256": source_hash,
        "output_sha256": output_hash,
        "byte_identical": source_hash == output_hash
        and source.stat().st_size == output.stat().st_size,
        "editable_field_count": len(editor.fields),
        "applied_edit_count": int(manifest.get("applied_edit_count") or 0),
        "section_boundaries_confirmed": bool(
            manifest.get("section_boundaries_confirmed")
        ),
        "manifest_json": str(manifest_json),
        "manifest_txt": str(manifest_txt),
        "scope": "Exact-copy and parser-boundary proof for the safe patch path; not a reconstructed serialization.",
    }
    paths["reports"].mkdir(parents=True, exist_ok=True)
    paths["noop_proof"].write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "project",
        type=Path,
        help="Fragmenter project.json or workspace directory",
    )
    parser.add_argument(
        "--regenerate-samples",
        action="store_true",
        help="Rebuild the corrected v2 sample catalog first",
    )
    parser.add_argument(
        "--noop-proof",
        action="store_true",
        help="Write an exact-copy safe patch round-trip proof",
    )
    parser.add_argument(
        "--no-parse",
        action="store_true",
        help="Use reports only; skip reparsing the source",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero while playback reconstruction is blocked",
    )
    args = parser.parse_args(argv)
    project = load_project(args.project)
    if args.regenerate_samples:
        regenerate_corrected_samples(project)
    if args.noop_proof:
        write_noop_roundtrip_proof(project)
    report = audit_project(project, parse_source=not args.no_parse, write=True)
    print(render_report(report), end="")
    print(f"JSON: {project_paths(project)['readiness_json']}")
    print(f"Text: {project_paths(project)['readiness_txt']}")
    if (
        args.strict
        and report["readiness"]["playback_reconstruction"] == "blocked"
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

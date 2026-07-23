#!/usr/bin/env python3
"""Run Fragmenter visual/audio research diagnostics from the repository root."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from audio_diagnostics_v1 import write_audio_diagnostics  # noqa: E402
from ccsf_asset_diagnostics_v1 import build_research_bundle  # noqa: E402
from ccsf_studioccs_compare_v1 import write_compare_report  # noqa: E402
from ccsf_texture_library_probe_v1 import run_texture_library_probe  # noqa: E402
from morning_diagnostics_v1 import locate_assets, run_morning_diagnostics  # noqa: E402
from project_workspace_v1 import FragmenterProjectV1, load_project  # noqa: E402
from snddata_audition_matrix_v1 import render_audition_matrix  # noqa: E402
from snddata_field_probe_v1 import write_field_probe  # noqa: E402
from snddata_forensics_v1 import analyze_and_write as write_snddata_forensics  # noqa: E402
from snddata_music_system_v5 import analyze_project_snddata  # noqa: E402


def _print_progress(event: dict[str, Any]) -> None:
    kind = str(event.get("kind") or "progress")
    stage = str(event.get("stage") or "")
    status = str(event.get("status") or "")
    current = event.get("current")
    total = event.get("total")
    detail = event.get("detail") or event.get("asset") or ""
    parts = [value for value in (kind, stage, status) if value]
    if isinstance(current, int) and isinstance(total, int) and total:
        parts.append(f"{current}/{total}")
    if detail:
        parts.append(str(detail))
    print("[DIAGNOSTICS] " + " | ".join(parts), flush=True)


def _project(value: str) -> FragmenterProjectV1:
    return load_project(Path(value).expanduser())


def _resolve_asset(project: FragmenterProjectV1, value: str) -> Path:
    direct = Path(value).expanduser()
    if direct.is_file():
        return direct
    root = project.workspace_path("extracted_ccs")
    project_relative = root / value
    if project_relative.is_file():
        return project_relative
    matches = locate_assets(project, [value])
    if not matches:
        raise FileNotFoundError(f"No extracted CCSF asset matched: {value}")
    return Path(matches[0]["path"])


def _asset_output(project: FragmenterProjectV1, asset: Path) -> Path:
    root = project.workspace_path("asset_diagnostics")
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in asset.name).strip("._") or "asset"
    return root / safe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="project", help="Project directory or project.json; default: ./project")
    sub = parser.add_subparsers(dest="command", required=True)

    morning = sub.add_parser("morning", help="Run the complete visual/audio morning research bundle")
    morning.add_argument("--asset", action="append", dest="assets", help="Asset filename/path search pattern; may be repeated")
    morning.add_argument("--audition-sequences", type=int, default=12, help="Maximum sequences included in the bounded audition matrix")

    sub.add_parser("audio", help="Write the broad parser-funnel/audio inventory report")
    sub.add_parser("forensics", help="Write FF0A SCEIMidi/SCEIProg/SCEISequ routing forensics")

    audition = sub.add_parser("audition", help="Render bounded proof WAVs for complete routing hypotheses")
    audition.add_argument("--max-sequences", type=int, default=12)
    audition.add_argument("--max-candidates", type=int, default=2)
    audition.add_argument("--max-seconds", type=float, default=20.0)

    sub.add_parser("mixer-index", help="Rebuild the v5 SNDDATA mixer catalog")

    asset = sub.add_parser("asset", help="Generate diagnostic TXT/JSON plus provenance OBJ/MTL/PNG for one asset")
    asset.add_argument("asset", help="Absolute path, extracted_ccs-relative path, or filename substring")
    asset.add_argument("--animation", default=None)
    asset.add_argument("--frame", type=int, default=0)

    texture = sub.add_parser("texture-probe", help="Scan the extracted CCS library for indexed textures, setup ownership, and cross-asset candidates")
    texture.add_argument("--pattern", action="append", dest="patterns", help="Optional asset path/name filter; may be repeated")
    texture.add_argument("--max-assets", type=int, default=0, help="Bound the scan; 0 scans every matching CCS asset")

    sub.add_parser("audio-probe", help="Probe SCEIHead/Vagi/Smpl/Sset fields, ADPCM density, decode errors, and strict MIDI boundaries")

    probes = sub.add_parser("probes", help="Run both the library texture probe and the SNDDATA field probe")
    probes.add_argument("--pattern", action="append", dest="patterns", help="Optional CCS asset filter; may be repeated")
    probes.add_argument("--max-assets", type=int, default=0, help="Bound the texture scan; 0 scans every matching CCS asset")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = _project(args.project)

    if args.command == "morning":
        result = run_morning_diagnostics(
            project,
            asset_patterns=args.assets,
            audition_sequences=max(1, args.audition_sequences),
            callback=_print_progress,
        )
    elif args.command == "audio":
        result = write_audio_diagnostics(project)
    elif args.command == "forensics":
        result = write_snddata_forensics(project, callback=_print_progress)
    elif args.command == "audition":
        result = render_audition_matrix(
            project,
            max_sequences=max(1, args.max_sequences),
            max_candidates_per_hypothesis=max(1, args.max_candidates),
            max_seconds=max(1.0, args.max_seconds),
            callback=_print_progress,
        )
    elif args.command == "mixer-index":
        result = analyze_project_snddata(project, callback=_print_progress)
    elif args.command == "asset":
        source = _resolve_asset(project, args.asset)
        output = _asset_output(project, source)
        research = build_research_bundle(source, output, animation_name=args.animation, frame=max(0, args.frame))
        compare = write_compare_report(source, output, animation_name=args.animation, frame=max(0, args.frame))
        result = {
            "source": str(source),
            "output_dir": str(output),
            "asset_diagnostic_txt": research["diagnostics"]["text_report_path"],
            "asset_diagnostic_json": research["diagnostics"]["report_path"],
            "obj_path": research["obj"]["obj_path"],
            "mtl_path": research["obj"]["mtl_path"],
            "compare_txt": compare["text_report_path"],
            "compare_json": compare["report_path"],
        }
    elif args.command == "texture-probe":
        result = run_texture_library_probe(
            project,
            patterns=args.patterns,
            max_assets=max(0, args.max_assets),
            callback=_print_progress,
        )
    elif args.command == "audio-probe":
        result = write_field_probe(project, callback=_print_progress)
    elif args.command == "probes":
        result = {
            "texture_probe": run_texture_library_probe(
                project,
                patterns=args.patterns,
                max_assets=max(0, args.max_assets),
                callback=_print_progress,
            ),
            "audio_probe": write_field_probe(project, callback=_print_progress),
        }
    else:  # pragma: no cover
        raise AssertionError(args.command)

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

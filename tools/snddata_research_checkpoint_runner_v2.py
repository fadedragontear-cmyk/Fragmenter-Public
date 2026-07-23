#!/usr/bin/env python3
"""Run the consolidated SNDDATA checkpoint with authoritative sample bridging.

V2 installs the corrected sample bridge before importing the v1 checkpoint, then
plans and attempts a bounded batch of sequence auditions. The reports-only ZIP is
rewritten to include the updated decision summary and batch results.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

# Importing the batch installs the sample bridge and generation guard before the
# checkpoint imports the v5 music catalog.
import snddata_sequence_batch_v1 as sequence_batch
import snddata_research_checkpoint_v1 as checkpoint
from project_workspace_v1 import load_project


def _rewrite_bundle(
    bundle: Path,
    replacements: list[Path],
) -> None:
    replacement_by_name = {path.name: path for path in replacements if path.is_file()}
    temporary = bundle.with_name(bundle.name + ".tmp")
    with zipfile.ZipFile(bundle, "r") as source, zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for item in source.infolist():
            if item.filename in replacement_by_name:
                continue
            target.writestr(item, source.read(item.filename))
        for name, path in replacement_by_name.items():
            target.write(path, name)
    temporary.replace(bundle)


def _batch_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = dict(result.get("summary") or {})
    return {
        **summary,
        "report_json": str(result.get("report_json") or ""),
        "report_txt": str(result.get("report_txt") or ""),
        "plan_only": bool(result.get("plan_only")),
        "outputs": [
            str(row.get("output_path") or "")
            for row in result.get("results") or []
            if row.get("output_path")
        ],
        "failures": [
            {
                "sequence_id": row.get("sequence_id"),
                "routing_mode": row.get("routing_mode"),
                "error": row.get("error"),
                "missing": list(row.get("missing") or []),
            }
            for row in result.get("results") or []
            if row.get("status") == "failed"
        ],
    }


def run(
    *,
    psound_source: Path,
    search_root: Path,
    output: Path,
    project_path: Path,
    refresh_music: bool = True,
    audition_limit: int = 10,
    plan_only: bool = False,
    skip_auditions: bool = False,
) -> dict[str, Any]:
    summary = checkpoint.run_checkpoint(
        psound_source=psound_source,
        search_root=search_root,
        output=output,
        project_path=project_path,
        refresh_music=refresh_music,
    )

    batch_result: dict[str, Any] | None = None
    if (
        not skip_auditions
        and summary.get("decisions", {}).get("sample_extraction_phase_closed")
        and project_path.is_file()
    ):
        project = load_project(project_path)
        batch_result = sequence_batch.run_batch(
            project,
            limit=max(1, int(audition_limit)),
            plan_only=plan_only,
            refresh_catalog=False,
        )
        summary["sequence_audition_batch"] = _batch_summary(batch_result)
        batch_summary = summary["sequence_audition_batch"]
        if batch_summary.get("rendered"):
            summary["decisions"]["next_action"] = (
                "Listen to the rendered audition batch and identify the closest, wrong-instrument, "
                "wrong-pitch, wrong-timing, and silent examples. The next patch will target those named walls."
            )
        elif batch_summary.get("planned"):
            summary["decisions"]["next_action"] = (
                "The authoritative sample bridge produced complete routes, but the renderer failed them. "
                "Use the batch failure list as the next implementation target."
            )
        else:
            summary["decisions"]["next_action"] = (
                "The authoritative sample bridge is active, but no evidence-backed Program Change or "
                "channel route is complete. Inspect the refreshed routing report rather than sample extraction."
            )

        summary_json = Path(summary["paths"]["summary_json"])
        summary_txt = Path(summary["paths"]["summary_txt"])
        bundle = Path(summary["paths"]["bundle_zip"])
        summary_json.write_text(
            json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        text = checkpoint.render_summary(summary)
        text += "\n" + sequence_batch.render_report(batch_result)
        summary_txt.write_text(text, encoding="utf-8")
        _rewrite_bundle(
            bundle,
            [
                summary_json,
                summary_txt,
                Path(str(batch_result["report_json"])),
                Path(str(batch_result["report_txt"])),
            ],
        )

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--psound-source",
        default=r"C:\games\areaserver\FragmentModKit\PSound201",
    )
    parser.add_argument("--search-root", default=str(Path.cwd().parent))
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--output",
        default=str(Path.cwd() / "diagnostics" / "snddata_research_checkpoint"),
    )
    parser.add_argument("--audition-limit", type=int, default=10)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--skip-auditions", action="store_true")
    parser.add_argument("--skip-music-refresh", action="store_true")
    args = parser.parse_args(argv)

    summary = run(
        psound_source=Path(args.psound_source).expanduser().resolve(),
        search_root=Path(args.search_root).expanduser().resolve(),
        output=Path(args.output).expanduser().resolve(),
        project_path=Path(args.project).expanduser().resolve(),
        refresh_music=not args.skip_music_refresh,
        audition_limit=args.audition_limit,
        plan_only=args.plan_only,
        skip_auditions=args.skip_auditions,
    )
    print(checkpoint.render_summary(summary), end="")
    batch = summary.get("sequence_audition_batch") or {}
    if batch:
        print("Sequence audition batch:")
        print(f"  Planned: {batch.get('planned', 0)}")
        print(f"  Rendered: {batch.get('rendered', 0)}")
        print(f"  Failed: {batch.get('failed', 0)}")
        for output_path in batch.get("outputs") or []:
            print(f"  WAV: {output_path}")
    print(f"Summary JSON: {summary['paths']['summary_json']}")
    print(f"Reports-only ZIP: {summary['paths']['bundle_zip']}")
    return 0 if summary["decisions"]["sample_extraction_phase_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

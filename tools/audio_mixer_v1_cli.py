#!/usr/bin/env python3
"""Inspect, audition, render, and save Fragmenter 1.0 SNDDATA mappings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_mixer_controller_v1 import (
    NoRenderableMapping,
    render_sequence_preview,
    sequence_resolver_view_model,
    sequence_rows,
    use_sequence_mapping,
)
from project_setup_controller_v1 import load_setup_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sequences = sub.add_parser("sequences", help="List parsed sequences and mapping state")
    sequences.add_argument("project")

    resolver = sub.add_parser("resolver", help="Show Program-resource candidates for one sequence")
    resolver.add_argument("project")
    resolver.add_argument("sequence")
    resolver.add_argument("--selected")

    render = sub.add_parser("render", help="Render an experimental preview WAV")
    render.add_argument("project")
    render.add_argument("sequence")
    render.add_argument("program_resource")
    render.add_argument("--program-index", type=int)
    render.add_argument("--gain", type=float, default=1.0)
    render.add_argument("--pan-mode", choices=("equal_power", "linear"), default="equal_power")

    use = sub.add_parser("use-mapping", help="Persist an auditioned sequence/program mapping")
    use.add_argument("project")
    use.add_argument("sequence")
    use.add_argument("program_resource")
    use.add_argument("--program-index", type=int)
    use.add_argument("--status", choices=("manual", "confirmed"), default="manual")
    use.add_argument("--notes", default="")

    args = parser.parse_args(argv)
    project = load_setup_project(args.project)

    if args.command == "sequences":
        payload = {"sequences": sequence_rows(project), "writes_game_data": False}
    elif args.command == "resolver":
        payload = sequence_resolver_view_model(project, args.sequence, args.selected)
    elif args.command == "render":
        try:
            payload = render_sequence_preview(
                project,
                args.sequence,
                args.program_resource,
                program_index=args.program_index,
                master_gain=args.gain,
                pan_mode=args.pan_mode,
            )
        except NoRenderableMapping as exc:
            print(json.dumps({"status": "not_renderable", "missing": exc.missing, "message": str(exc)}, indent=2, sort_keys=True))
            return 2
    elif args.command == "use-mapping":
        payload = use_sequence_mapping(
            project,
            args.sequence,
            args.program_resource,
            program_index=args.program_index,
            status=args.status,
            notes=args.notes,
        )
    else:
        raise AssertionError(args.command)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

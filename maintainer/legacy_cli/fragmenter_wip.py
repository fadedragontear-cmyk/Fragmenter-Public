#!/usr/bin/env python3
"""Project-bound command surface for Fragmenter public-release development.

This entrypoint exercises the new 1.0 services without modifying the preserved
legacy GUI or main branch. It is intentionally non-destructive except for explicit
verified restore commands, which create pre-restore safety backups.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from audio_mapping_controller_v1 import (  # noqa: E402
    load_project_mapping,
    mapping_status_view_model,
    project_mapping_resolver,
    remove_project_mapping,
    save_project_mapping,
)
from backup_controller_v1 import (  # noqa: E402
    backup_memory_card,
    backup_server_saves,
    backup_view_model,
    restore_memory_card,
    restore_server_saves,
)
from project_preflight_v1 import build_preflight  # noqa: E402
from project_setup_controller_v1 import create_setup_project, load_setup_project, setup_view_model  # noqa: E402
from report_locator_v1 import report_locator_view_model, write_diagnostics_summary  # noqa: E402
from run_all_plan_v1 import build_deep_discovery_plan, build_run_all_plan  # noqa: E402
from server_explorer_controller_v1 import (  # noqa: E402
    export_project_server_file,
    inspect_project_server_file,
    server_explorer_view_model,
)
from visual_asset_controller_v1 import (  # noqa: E402
    extract_visual_animation,
    extract_visual_scene,
    extract_visual_textures,
    visual_asset_view_model,
)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))


def _project(value: str):
    return load_setup_project(value)


def _add_snddata_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--snddata", help="Path under the active project's media_pipeline; auto-detected when omitted")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fragmenter-wip", description="Fragmenter 1.0 project-bound development CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-project", help="Create a fresh Fragmenter 1.0 project")
    create.add_argument("workspace")
    create.add_argument("--iso", required=True)
    create.add_argument("--server-root", required=True)
    create.add_argument("--server-saves", required=True)
    create.add_argument("--memory-card", required=True)

    for name, help_text in (
        ("status", "Show Setup and active runtime paths"),
        ("run-all-plan", "Show the focused project-bound RUN ALL checklist"),
        ("deep-plan", "Show the explicit Deep Disc Discovery plan"),
        ("server-list", "List Area Server files in the active project"),
        ("backup-status", "Show save/memory-card backup status"),
        ("backup-server", "Back up the configured Area Server saves"),
        ("backup-card", "Back up the configured whole memory-card file"),
        ("reports", "Show canonical reports and diagnostics"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project")

    inspect_server = sub.add_parser("server-inspect", help="Inspect one active-project Area Server file")
    inspect_server.add_argument("project")
    inspect_server.add_argument("file")
    inspect_server.add_argument("--out")

    export_server = sub.add_parser("server-export", help="Export one gzip-compressed Area Server file")
    export_server.add_argument("project")
    export_server.add_argument("file")

    restore_server = sub.add_parser("restore-server", help="Restore a verified server-save backup")
    restore_server.add_argument("project")
    restore_server.add_argument("manifest")

    restore_card = sub.add_parser("restore-card", help="Restore a verified whole memory-card backup")
    restore_card.add_argument("project")
    restore_card.add_argument("manifest")

    for name, help_text in (
        ("visual-inspect", "Inspect/cache one extracted CCSF asset"),
        ("visual-textures", "Extract verified textures from one CCSF asset"),
        ("visual-animation", "Extract animation metadata from one CCSF asset"),
        ("visual-scene", "Extract Object/Clump scene metadata from one CCSF asset"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project")
        command.add_argument("asset")

    mapping_set = sub.add_parser("mapping-set", help="Persist a manual/confirmed Sequence to Program mapping")
    mapping_set.add_argument("project")
    mapping_set.add_argument("sequence")
    mapping_set.add_argument("program")
    _add_snddata_option(mapping_set)
    mapping_set.add_argument("--status", choices=("manual", "confirmed", "structural"), default="manual")
    mapping_set.add_argument("--notes", default="")
    mapping_set.add_argument("--program-index", type=int)

    for name in ("mapping-get", "mapping-remove"):
        command = sub.add_parser(name)
        command.add_argument("project")
        command.add_argument("sequence")
        _add_snddata_option(command)

    mapping_list = sub.add_parser("mapping-list")
    mapping_list.add_argument("project")
    _add_snddata_option(mapping_list)

    resolver = sub.add_parser("mapping-resolver", help="Build an unresolved Program candidate view model")
    resolver.add_argument("project")
    resolver.add_argument("sequence")
    _add_snddata_option(resolver)
    resolver.add_argument("--candidate", action="append", default=[])
    resolver.add_argument("--selected")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "create-project":
        project = create_setup_project(
            args.workspace,
            iso_path=args.iso,
            area_server_root=args.server_root,
            server_save_dir=args.server_saves,
            memory_card_path=args.memory_card,
        )
        _print(setup_view_model(project))
        return 0

    project = _project(args.project)

    if args.command == "status":
        payload = setup_view_model(project)
        payload["preflight"] = build_preflight(project)
        _print(payload)
        return 0 if payload["ready"] else 2
    if args.command == "run-all-plan":
        payload = build_run_all_plan(project)
        _print(payload)
        return 0 if payload["ready"] else 2
    if args.command == "deep-plan":
        payload = build_deep_discovery_plan(project)
        _print(payload)
        return 0 if payload["ready"] else 2
    if args.command == "server-list":
        _print(server_explorer_view_model(project))
        return 0
    if args.command == "server-inspect":
        payload = inspect_project_server_file(project, args.file)
        if args.out:
            target = Path(args.out).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")
            payload["written_report"] = str(target)
        _print(payload)
        return 0
    if args.command == "server-export":
        _print(export_project_server_file(project, args.file))
        return 0
    if args.command == "backup-status":
        _print(backup_view_model(project))
        return 0
    if args.command == "backup-server":
        _print(backup_server_saves(project))
        return 0
    if args.command == "backup-card":
        _print(backup_memory_card(project))
        return 0
    if args.command == "restore-server":
        _print(restore_server_saves(project, args.manifest))
        return 0
    if args.command == "restore-card":
        _print(restore_memory_card(project, args.manifest))
        return 0
    if args.command == "reports":
        write_diagnostics_summary(project)
        _print(report_locator_view_model(project))
        return 0
    if args.command == "visual-inspect":
        _print(visual_asset_view_model(project, args.asset))
        return 0
    if args.command == "visual-textures":
        _print(extract_visual_textures(project, args.asset))
        return 0
    if args.command == "visual-animation":
        _print(extract_visual_animation(project, args.asset))
        return 0
    if args.command == "visual-scene":
        _print(extract_visual_scene(project, args.asset))
        return 0
    if args.command == "mapping-set":
        _print(
            save_project_mapping(
                project,
                args.snddata,
                args.sequence,
                args.program,
                status=args.status,
                notes=args.notes,
                program_index=args.program_index,
            )
        )
        return 0
    if args.command == "mapping-get":
        payload = load_project_mapping(project, args.snddata, args.sequence)
        _print(payload)
        return 0 if payload is not None else 1
    if args.command == "mapping-remove":
        removed = remove_project_mapping(project, args.snddata, args.sequence)
        _print({"removed": removed})
        return 0 if removed else 1
    if args.command == "mapping-list":
        _print(mapping_status_view_model(project, args.snddata))
        return 0
    if args.command == "mapping-resolver":
        _print(
            project_mapping_resolver(
                project,
                args.snddata,
                args.sequence,
                args.candidate,
                selected_program=args.selected,
            )
        )
        return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

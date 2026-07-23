#!/usr/bin/env python3
"""CLI for creating and inspecting authoritative Fragmenter 1.0 projects."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_preflight_v1 import build_preflight, load_active_project
from project_workspace_v1 import create_project, render_project_status, write_project_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or inspect a Fragmenter 1.0 project")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a fresh authoritative Fragmenter 1.0 workspace")
    create.add_argument("workspace", type=Path)
    create.add_argument("--iso", required=True, type=Path)
    create.add_argument("--server-root", required=True, type=Path)
    create.add_argument("--server-saves", required=True, type=Path)
    create.add_argument("--memory-card", required=True, type=Path)

    status = sub.add_parser("status", help="Show readiness and canonical runtime paths")
    status.add_argument("project", type=Path, help="Project workspace or project.json")
    status.add_argument("--json", action="store_true", help="Print the full preflight payload as JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "create":
        project = create_project(
            args.workspace,
            iso_path=args.iso,
            area_server_root=args.server_root,
            server_save_dir=args.server_saves,
            memory_card_path=args.memory_card,
        )
        write_project_status(project)
        payload = build_preflight(project)
        print(f"Created Fragmenter 1.0 project: {project.project_path}")
        print(render_project_status({
            "project_version": payload["project_version"],
            "ready": payload["ready"],
            "checks": payload["checks"],
        }), end="")
        return 0 if payload["ready"] else 2

    project, _paths = load_active_project(args.project)
    payload = build_preflight(project)
    write_project_status(project)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_project_status({
            "project_version": payload["project_version"],
            "ready": payload["ready"],
            "checks": payload["checks"],
        }), end="")
        print("Canonical runtime paths")
        for name, value in payload["paths"].items():
            print(f"{name}: {value}")
    return 0 if payload["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

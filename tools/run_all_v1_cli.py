#!/usr/bin/env python3
"""Execute or inspect Fragmenter 1.0 RUN ALL for one active project."""
from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from project_setup_controller_v1 import load_setup_project  # noqa: E402
from run_all_executor_v1 import build_run_all_actions, execute_run_all  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Project workspace or project.json")
    parser.add_argument("--dry-run", action="store_true", help="Print the exact action graph without executing it")
    parser.add_argument("--no-reuse", action="store_true", help="Run every stage even when matching outputs are reusable")
    parser.add_argument("--events-jsonl", action="store_true", help="Write compact progress events to stderr")
    args = parser.parse_args(argv)

    project = load_setup_project(args.project)
    if args.dry_run:
        payload = {
            "version": 1,
            "origin": "RUN ALL",
            "workspace": project.workspace_dir,
            "actions": [action.to_dict() for action in build_run_all_actions(project)],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    def callback(event: dict) -> None:
        if args.events_jsonl:
            print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)
        elif event.get("kind") in {"start", "finish"}:
            label = event.get("label") or event.get("stage")
            status = f" — {event.get('status')}" if event.get("status") else ""
            print(f"[RUN ALL] {label}{status}", file=sys.stderr, flush=True)

    result = execute_run_all(
        project,
        reuse=not args.no_reuse,
        callback=callback,
        cancel_event=threading.Event(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" else 3 if result["status"] == "cancelled" else 2


if __name__ == "__main__":
    raise SystemExit(main())

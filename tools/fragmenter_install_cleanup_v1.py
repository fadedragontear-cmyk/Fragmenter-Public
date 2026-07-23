#!/usr/bin/env python3
"""Inventory Fragmenter installations and safely quarantine old project workspaces.

This tool never deletes files. It distinguishes Git/source checkouts from project
workspaces, archives the small human-created state from selected projects, then moves
those projects into a reversible _Fragmenter_Retired folder on the same drive.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_FILENAME = "project.json"
PROTECTED_RELATIVE_PATHS = (
    "project.json",
    "cache/mappings/snddata_mappings.json",
    "cache/mappings/snddata_research.json",
    "reports/audio/snddata_sample_classification_v1.json",
    "reports/audio/snddata_research_workspace_v1.json",
)
PROTECTED_DIRECTORIES = ("backups",)
SKIP_PARTS = {".git", "__pycache__", "_Fragmenter_Retired", "node_modules", ".venv", "venv"}


@dataclass(frozen=True)
class Candidate:
    path: Path
    kind: str
    size_bytes: int
    project_path: Path | None = None
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "project_path": str(self.project_path) if self.project_path else None,
            "updated_at": self.updated_at,
        }


def _path_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [name for name in dirs if name not in SKIP_PARTS]
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def _human_size(value: int) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024.0 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024.0
    return f"{amount:.1f} TiB"


def _project_updated_at(project_path: Path) -> str:
    try:
        payload = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("updated_at") or payload.get("created_at") or "")


def _is_checkout(path: Path) -> bool:
    return (
        (path / "START_FRAGMENTER_PUBLIC.bat").is_file()
        and (path / "fragmenter_public.py").is_file()
    ) or (path / ".git").is_dir()


def _is_inside_checkout(path: Path, checkout_roots: Iterable[Path]) -> bool:
    resolved = path.resolve()
    for root in checkout_roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def discover(root: Path, *, max_depth: int = 4) -> list[Candidate]:
    root = root.expanduser().resolve()
    checkouts: list[Path] = []
    projects: list[Path] = []

    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        try:
            depth = len(current_path.relative_to(root).parts)
        except ValueError:
            continue
        dirs[:] = [
            name for name in dirs
            if name not in SKIP_PARTS and depth < max_depth
        ]
        if _is_checkout(current_path):
            checkouts.append(current_path)
            # Project workspaces must live outside a checkout. Do not descend into
            # repository-generated caches or legacy workspace folders.
            dirs[:] = [name for name in dirs if name not in {"workspace", "diagnostics", "assets"}]
        if PROJECT_FILENAME in files:
            projects.append(current_path / PROJECT_FILENAME)

    rows: list[Candidate] = []
    for path in sorted(set(checkouts), key=lambda item: str(item).casefold()):
        rows.append(Candidate(path, "repository_checkout_keep", _path_size(path)))
    for project_path in sorted(set(projects), key=lambda item: str(item).casefold()):
        workspace = project_path.parent
        if _is_inside_checkout(workspace, checkouts):
            kind = "project_inside_checkout_review"
        else:
            kind = "project_workspace_quarantinable"
        rows.append(
            Candidate(
                workspace,
                kind,
                _path_size(workspace),
                project_path=project_path,
                updated_at=_project_updated_at(project_path),
            )
        )
    return rows


def protected_files(workspace: Path) -> list[Path]:
    workspace = workspace.resolve()
    files: list[Path] = []
    for relative in PROTECTED_RELATIVE_PATHS:
        candidate = workspace / relative
        if candidate.is_file():
            files.append(candidate)
    for relative in PROTECTED_DIRECTORIES:
        directory = workspace / relative
        if directory.is_dir():
            files.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(set(files), key=lambda item: item.relative_to(workspace).as_posix().casefold())


def archive_human_state(workspace: Path, archive_root: Path) -> Path:
    workspace = workspace.resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / f"{workspace.name}_human_state_{timestamp}.zip"
    index = 1
    while target.exists():
        target = archive_root / f"{workspace.name}_human_state_{timestamp}_{index}.zip"
        index += 1

    files = protected_files(workspace)
    manifest = {
        "version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "workspace": str(workspace),
        "protected_files": [path.relative_to(workspace).as_posix() for path in files],
        "notes": (
            "Human-created mappings, classifications, research notes, project metadata, "
            "and backups only. Generated extracted/decoded/work/cache/report bulk is omitted."
        ),
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cleanup_manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        for path in files:
            archive.write(path, f"workspace/{path.relative_to(workspace).as_posix()}")
    return target


def quarantine_workspace(workspace: Path, root: Path) -> tuple[Path, Path]:
    workspace = workspace.resolve()
    root = root.resolve()
    if _is_checkout(workspace):
        raise ValueError(f"Refusing to quarantine a repository checkout: {workspace}")
    project_path = workspace / PROJECT_FILENAME
    if not project_path.is_file():
        raise ValueError(f"Refusing to quarantine a folder without project.json: {workspace}")
    try:
        workspace.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Workspace is outside the managed root {root}: {workspace}") from exc

    retired_root = root / "_Fragmenter_Retired"
    archive_root = retired_root / "archives"
    archive = archive_human_state(workspace, archive_root)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination_root = retired_root / "projects" / timestamp
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / workspace.name
    index = 1
    while destination.exists():
        destination = destination_root / f"{workspace.name}_{index}"
        index += 1
    shutil.move(str(workspace), str(destination))
    return destination, archive


def write_report(root: Path, rows: list[Candidate], report_path: Path) -> Path:
    payload = {
        "version": 1,
        "root": str(root.resolve()),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "candidates": [row.as_dict() for row in rows],
        "policy": {
            "repository_checkouts": "keep; never quarantined",
            "project_workspaces": "may be archived and moved only after explicit selection",
            "external_sources": "not enumerated or modified",
            "deletion": "never performed",
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path


def _print_rows(rows: list[Candidate]) -> list[Candidate]:
    projects: list[Candidate] = []
    print("Fragmenter installation inventory")
    print("===============================")
    for row in rows:
        if row.kind.startswith("project_"):
            projects.append(row)
            number = len(projects)
            suffix = f" updated={row.updated_at}" if row.updated_at else ""
            print(f"[{number:02d}] PROJECT  {_human_size(row.size_bytes):>10}  {row.path}{suffix}")
        else:
            print(f"[--] KEEP     {_human_size(row.size_bytes):>10}  {row.path}")
    if not projects:
        print("No Fragmenter project workspaces were found.")
    return projects


def _selection(text: str, count: int) -> list[int]:
    values: set[int] = set()
    for part in str(text or "").replace(",", " ").split():
        value = int(part)
        if value < 1 or value > count:
            raise ValueError(f"Selection {value} is outside 1..{count}")
        values.add(value)
    return sorted(values)


def interactive(root: Path, rows: list[Candidate]) -> int:
    projects = _print_rows(rows)
    if not projects:
        return 0
    print()
    print("Enter project numbers to move into _Fragmenter_Retired, or press Enter to exit.")
    print("No repository checkout or external source folder can be selected.")
    choice = input("Selection: ").strip()
    if not choice:
        print("No changes made.")
        return 0
    indexes = _selection(choice, len(projects))
    print()
    for index in indexes:
        row = projects[index - 1]
        print(f"Selected: {row.path}")
    confirmation = input("Type QUARANTINE to archive and move these projects: ").strip()
    if confirmation != "QUARANTINE":
        print("Confirmation did not match. No changes made.")
        return 1

    for index in indexes:
        workspace = projects[index - 1].path
        destination, archive = quarantine_workspace(workspace, root)
        print(f"Moved:   {workspace}")
        print(f"To:      {destination}")
        print(f"Archive: {archive}")
    print("Nothing was deleted. Remove _Fragmenter_Retired manually only after the new install is accepted.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(Path.cwd().parent))
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--report")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    rows = discover(root, max_depth=max(1, int(args.max_depth)))
    report = Path(args.report).expanduser().resolve() if args.report else (
        root / "_Fragmenter_Retired" / "fragmenter_install_inventory.json"
    )
    write_report(root, rows, report)
    if args.non_interactive:
        _print_rows(rows)
        print(f"Report: {report}")
        return 0
    result = interactive(root, rows)
    print(f"Report: {report}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

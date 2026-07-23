#!/usr/bin/env python3
"""Choose the safest available Fragmenter ISO patch engine automatically."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT_DIR)).resolve()
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660, normalize_path  # noqa: E402
from iso_patch_engine import PatchError, apply_manifest, load_manifest  # noqa: E402

ENGINE_LAYOUT = "layout-preserving"
ENGINE_REBUILD = "udf-rebuild"


@dataclass(frozen=True)
class EngineSelection:
    engine: str
    reason: str
    resized_files: tuple[str, ...] = ()


def _replacement_path(manifest_path: Path, value: Any, operation_id: str) -> Path:
    source_value = str(value or "").strip()
    if not source_value:
        raise PatchError(f"{operation_id}: source_file is required.")
    candidate = Path(source_value)
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise PatchError(f"{operation_id}: replacement file does not exist: {candidate}")
    return candidate


def select_engine(source_iso: str | Path, manifest_path: str | Path) -> EngineSelection:
    """Select in-place patching unless at least one replacement changes size."""
    source = Path(source_iso).expanduser().resolve()
    manifest_file = Path(manifest_path).expanduser().resolve()
    if not source.is_file():
        raise PatchError(f"Source ISO does not exist: {source}")

    manifest = load_manifest(manifest_file)
    iso = Iso9660(source).open()
    index = iso.build_index()
    resized: list[str] = []

    for operation_index, raw in enumerate(manifest["operations"]):
        if not isinstance(raw, dict):
            raise PatchError(f"Operation {operation_index + 1} must be a JSON object.")
        operation_id = str(raw.get("id") or f"operation-{operation_index + 1}")
        operation_type = str(raw.get("type") or "").strip()
        internal_path = normalize_path(raw.get("path"))
        if not internal_path:
            raise PatchError(f"{operation_id}: path is required.")
        entry = index.get(internal_path)
        if entry is None:
            raise PatchError(f"{operation_id}: ISO file was not found: {internal_path}")

        if operation_type == "write_bytes":
            continue
        if operation_type != "replace_file":
            raise PatchError(f"{operation_id}: unsupported operation type: {operation_type!r}")

        replacement = _replacement_path(manifest_file, raw.get("source_file"), operation_id)
        if replacement.stat().st_size != entry.size:
            resized.append(internal_path)

    if resized:
        return EngineSelection(
            ENGINE_REBUILD,
            "One or more replacement files changed size and require a UDF rebuild.",
            tuple(resized),
        )
    return EngineSelection(
        ENGINE_LAYOUT,
        "All changes fit inside existing ISO file extents, so disc layout can be preserved.",
    )


def find_bridge(explicit: str | Path | None = None) -> Path:
    """Find the bundled self-contained bridge without requiring a .NET install."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    configured = os.environ.get("FRAGMENTER_ISO_BRIDGE", "").strip()
    if configured:
        candidates.append(Path(configured))

    candidates.extend(
        (
            BUNDLE_ROOT / "runtime" / "Fragmenter.IsoBridge.exe",
            ROOT_DIR / "runtime" / "Fragmenter.IsoBridge.exe",
            TOOLS_DIR / "iso_bridge" / "publish" / "win-x64" / "Fragmenter.IsoBridge.exe",
            TOOLS_DIR / "iso_bridge" / "Fragmenter.IsoBridge.exe",
            TOOLS_DIR / "iso_bridge" / "Fragmenter.IsoBridge",
        )
    )
    located = shutil.which("Fragmenter.IsoBridge.exe") or shutil.which("Fragmenter.IsoBridge")
    if located:
        candidates.append(Path(located))

    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file():
            return resolved
    raise PatchError(
        "This patch needs a full ISO rebuild, but the bundled Fragmenter ISO bridge "
        "was not found. Reinstall the complete Fragmenter release."
    )


def _bridge_error(completed: subprocess.CompletedProcess[str]) -> str:
    rendered = (completed.stderr or completed.stdout or "").strip()
    if rendered:
        try:
            payload = json.loads(rendered)
            if isinstance(payload, dict) and payload.get("error"):
                return str(payload["error"])
        except json.JSONDecodeError:
            pass
        return rendered
    return f"ISO bridge exited with code {completed.returncode}."


def _run_bridge(
    bridge: Path,
    source: Path,
    manifest: Path,
    output: Path,
) -> dict[str, Any]:
    completed = subprocess.run(
        (str(bridge), str(source), str(manifest), str(output)),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise PatchError(f"UDF rebuild refused: {_bridge_error(completed)}")
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PatchError("UDF rebuild finished without a valid JSON verification report.") from exc
    if not isinstance(report, dict) or report.get("status") != "applied":
        raise PatchError("UDF rebuild did not report a verified output.")
    if not output.is_file():
        raise PatchError("UDF rebuild reported success but did not create the output ISO.")
    return report


def _run_bridge_with_safe_overwrite(
    bridge: Path,
    source: Path,
    manifest: Path,
    output: Path,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    if output == source:
        raise PatchError("Output ISO must not overwrite the source ISO.")
    if output.exists() and not overwrite:
        raise PatchError(f"Output already exists: {output}")

    backup: Path | None = None
    if output.exists():
        backup = output.with_name(f".{output.name}.{uuid.uuid4().hex}.fragmenter.backup")
        os.replace(output, backup)
    try:
        report = _run_bridge(bridge, source, manifest, output)
    except Exception:
        if output.exists():
            output.unlink()
        if backup is not None and backup.exists():
            os.replace(backup, output)
        raise
    else:
        if backup is not None and backup.exists():
            backup.unlink()
        return report


def patch_iso(
    source_iso: str | Path,
    manifest_path: str | Path,
    output_iso: str | Path | None = None,
    *,
    bridge_path: str | Path | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Apply a patch with automatic layout-preserving/rebuild selection."""
    source = Path(source_iso).expanduser().resolve()
    manifest = Path(manifest_path).expanduser().resolve()
    selection = select_engine(source, manifest)

    if selection.engine == ENGINE_LAYOUT:
        report = apply_manifest(
            source,
            manifest,
            output_iso,
            dry_run=dry_run,
            overwrite=overwrite,
        )
        report["engine"] = selection.engine
        report["engine_reason"] = selection.reason
        return report

    bridge = find_bridge(bridge_path)
    if dry_run:
        return {
            "schema_version": 1,
            "status": "planned",
            "engine": selection.engine,
            "engine_reason": selection.reason,
            "resized_files": list(selection.resized_files),
            "bridge": str(bridge),
            "output": None,
        }
    if output_iso is None:
        raise PatchError("An output ISO path is required unless --dry-run is used.")

    output = Path(output_iso).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = _run_bridge_with_safe_overwrite(
        bridge,
        source,
        manifest,
        output,
        overwrite=overwrite,
    )
    report["engine"] = selection.engine
    report["engine_reason"] = selection.reason
    report["resized_files"] = list(selection.resized_files)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply a verified Fragmenter patch using the safest ISO engine automatically."
    )
    parser.add_argument("source_iso", help="Exact original ISO required by the patch")
    parser.add_argument("manifest", help="Fragmenter ISO patch manifest JSON")
    parser.add_argument("--out", help="Patched output ISO path")
    parser.add_argument("--bridge", help="Optional explicit Fragmenter.IsoBridge executable")
    parser.add_argument("--dry-run", action="store_true", help="Plan without creating an ISO")
    parser.add_argument("--overwrite", action="store_true", help="Safely replace an existing output ISO")
    parser.add_argument("--report", help="Optional JSON report path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = patch_iso(
            args.source_iso,
            args.manifest,
            args.out,
            bridge_path=args.bridge,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    except PatchError as exc:
        print(f"Patch refused: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

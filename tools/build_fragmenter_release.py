#!/usr/bin/env python3
"""Build the self-contained Windows Fragmenter release package."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

BRIDGE_NAME = "Fragmenter.IsoBridge.exe"
APP_NAME = "Fragmenter.exe"
PACKAGE_NAME = "Fragmenter-Windows-x64"
BRAND_PNG_NAME = "Fragmenter-Serenial.png"
BRAND_ICO_NAME = "Fragmenter.ico"
VISUAL_RUNTIME_MODULES = (
    "fragmenter_visual_runtime_v6",
    "ccsf_textured_scene_v9",
    "ccsf_textured_renderer_v5",
    "ccsf_wireframe_scene_v2",
    "ccsf_asset_tree_v2",
    "ccsf_visual_extract_v1",
    "visual_asset_controller_v1",
    "visual_asset_annotations_v3",
    "visual_asset_annotations_v4",
)


class ReleaseBuildError(RuntimeError):
    pass


def run_checked(command: Sequence[str], *, cwd: Path) -> None:
    rendered = subprocess.list2cmdline([str(part) for part in command])
    print(f"\n> {rendered}")
    completed = subprocess.run(tuple(map(str, command)), cwd=cwd, check=False)
    if completed.returncode:
        raise ReleaseBuildError(
            f"Command failed with exit code {completed.returncode}: {rendered}"
        )


def dotnet_publish_command(root: Path, dotnet: str) -> list[str]:
    return [
        dotnet,
        "publish",
        str(root / "tools" / "iso_bridge" / "Fragmenter.IsoBridge.csproj"),
        "-c",
        "Release",
        "-r",
        "win-x64",
        "--self-contained",
        "true",
        "-p:PublishSingleFile=true",
        "-p:DebugType=None",
        "-p:DebugSymbols=false",
        "-o",
        str(root / "build" / "iso_bridge" / "win-x64"),
    ]


def pyinstaller_command(root: Path, bridge: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name",
        "Fragmenter",
        "--icon",
        str(root / "assets" / "branding" / BRAND_ICO_NAME),
        "--paths",
        str(root / "tools"),
        "--hidden-import",
        "fragmenter_release_experience_v1",
        "--hidden-import",
        "fragmenter_public_gui_v127",
        "--hidden-import",
        "fragment_4_builder_v127",
        "--hidden-import",
        "fragmenter_public_gui_v126",
        "--hidden-import",
        "fragmenter_public_gui_v125",
        "--hidden-import",
        "fragmenter_public_gui_v122",
        "--hidden-import",
        "netslum_completion_v124",
        "--hidden-import",
        "tellipatch_resource_v122",
    ]
    for module in VISUAL_RUNTIME_MODULES:
        command.extend(("--hidden-import", module))
    command.extend(
        (
            "--add-binary",
            f"{bridge}{os.pathsep}runtime",
            "--add-data",
            f"{root / 'THIRD_PARTY_NOTICES.md'}{os.pathsep}.",
            "--add-data",
            f"{root / 'resources' / 'Fragment-Network.ps2.gz'}{os.pathsep}resources",
            "--add-data",
            f"{root / 'resources' / 'Tellipatch-gamelines.csv.gz'}{os.pathsep}resources",
            "--add-data",
            f"{root / 'resources' / 'game_setup'}{os.pathsep}resources/game_setup",
            "--distpath",
            str(root / "dist"),
            "--workpath",
            str(root / "build" / "pyinstaller"),
            "--specpath",
            str(root / "build"),
        )
    )
    assets = root / "assets"
    if assets.is_dir():
        command.extend(("--add-data", f"{assets}{os.pathsep}assets"))
    command.append(str(root / "fragmenter_public.py"))
    return command


def _clean_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _required_celdra_assets(root: Path) -> tuple[Path, ...]:
    celdra = root / "assets" / "celdra"
    manifest_path = celdra / "manifest.json"
    required: list[Path] = [manifest_path, celdra / "avatar" / "01.gif"]
    if not manifest_path.is_file():
        return tuple(required)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError(f"Invalid Celdra manifest: {manifest_path}: {exc}") from exc
    rows = manifest.get("emotes") if isinstance(manifest, dict) else None
    if not isinstance(rows, list):
        raise ReleaseBuildError(f"Celdra manifest has no emotes list: {manifest_path}")
    for row in rows:
        if not isinstance(row, dict) or not bool(row.get("enabled", True)):
            continue
        source = str(row.get("source") or "").strip()
        if source:
            required.append(celdra / source)
    return tuple(dict.fromkeys(required))


def _write_release_readme(path: Path) -> None:
    path.write_text(
        "Fragmenter 1.0 - Windows x64\n"
        "=================================================\n\n"
        "Run Fragmenter.exe. Python, .NET, ImgBurn, Tellipatch, and "
        "FragmentUpdater are not required at runtime.\n\n"
        "Project Setup defaults to a project folder beside Fragmenter.exe. ISO, "
        "Area Server, save, and memory-card paths are optional capabilities. Save "
        "Project stores the available paths and selected theme; Run All skips "
        "unavailable stages.\n\n"
        "The bundled 3D / Assets workspace uses the same in-process CCSF structure, "
        "wireframe, textured-scene, texture-export, camera, and puppetry runtime as "
        "the Python launcher.\n\n"
        "Game Setup contains the complete playable-game workflow:\n"
        "- Build and verify Fragment 4.0 English directly from the untouched Japanese ISO.\n"
        "- No Tellipatch installation, preview ISO, or reference 4.0 image is required.\n"
        "- Configure the PCSX2 keyboard and network with an automatic INI backup.\n"
        "- Install or inspect PCSX2 memory cards without overwriting existing cards.\n"
        "- Back up and restore project area-server saves and memory cards.\n"
        "- Use the completed ISO with the configured PCSX2 setup.\n\n"
        "The local 4.0 completion keeps both input ISOs read-only, uses temporary "
        "diagnostic material, and leaves only Fragment 4.0 English.iso after success. "
        "The final image keeps the original disc layout, labels the ISO volume "
        "FRAGMENT 4.0 ENGLISH, and verifies every changed logical file.\n\n"
        "Third-party credits and licenses are in THIRD_PARTY_NOTICES.md. They remain "
        "part of the application package and are not copied beside patched ISOs.\n",
        encoding="utf-8",
    )


def build_release(root: Path) -> dict[str, str | int]:
    root = root.resolve()
    required = (
        root / "fragmenter_public.py",
        root / "THIRD_PARTY_NOTICES.md",
        root / "tools" / "iso_patch_dispatcher.py",
        root / "tools" / "fragmenter_release_experience_v1.py",
        root / "tools" / "fragmenter_public_gui_v127.py",
        root / "tools" / "fragment_4_builder_v127.py",
        root / "tools" / "fragmenter_public_gui_v126.py",
        root / "tools" / "fragmenter_public_gui_v125.py",
        root / "tools" / "fragmenter_public_gui_v122.py",
        root / "tools" / "fragmenter_public_gui_v121.py",
        root / "tools" / "fragmenter_public_gui_v120.py",
        root / "tools" / "tellipatch_resource_v122.py",
        root / "tools" / "tellipatch_native.py",
        root / "tools" / "tellipatch_verify_v120.py",
        root / "tools" / "release_acceptance_v120.py",
        root / "tools" / "vcdiff_decoder.py",
        root / "tools" / "netslum_completion_v124.py",
        root / "tools" / "pcsx2_setup.py",
        *(root / "tools" / f"{module}.py" for module in VISUAL_RUNTIME_MODULES),
        root / "resources" / "Fragment-Network.ps2.gz",
        root / "resources" / "Tellipatch-gamelines.csv.gz",
        root / "resources" / "game_setup" / "Tellipatch-v3.8-patches.zip.rawpart1.b64",
        root / "resources" / "game_setup" / "Tellipatch-v3.8-patches.zip.rawpart2.b64",
        root / "resources" / "game_setup" / "Fragment-4.0-completion.zip.b64",
        root / "assets" / "branding" / BRAND_PNG_NAME,
        root / "assets" / "branding" / BRAND_ICO_NAME,
        root / "tools" / "iso_bridge" / "Fragmenter.IsoBridge.csproj",
        *_required_celdra_assets(root),
    )
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise ReleaseBuildError("Missing release files: " + ", ".join(missing))

    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise ReleaseBuildError(
            "The maintainer build requires the .NET 8 SDK to compile the bundled "
            "ISO bridge. End users do not need .NET."
        )
    if importlib.util.find_spec("PyInstaller") is None:
        raise ReleaseBuildError(
            "PyInstaller is missing. Run: py -3 -m pip install --upgrade pyinstaller"
        )

    bridge_build = root / "build" / "iso_bridge" / "win-x64"
    runtime = root / "runtime"
    dist = root / "dist"
    stage = dist / PACKAGE_NAME
    _clean_path(bridge_build)
    _clean_path(stage)
    bridge_build.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    dist.mkdir(parents=True, exist_ok=True)

    run_checked(dotnet_publish_command(root, dotnet), cwd=root)
    published_bridge = bridge_build / BRIDGE_NAME
    if not published_bridge.is_file():
        raise ReleaseBuildError(f".NET publish did not create {published_bridge}")
    bundled_bridge = runtime / BRIDGE_NAME
    shutil.copy2(published_bridge, bundled_bridge)

    run_checked(pyinstaller_command(root, bundled_bridge), cwd=root)
    app = dist / APP_NAME
    if not app.is_file() or app.stat().st_size == 0:
        raise ReleaseBuildError(f"PyInstaller did not create {app}")

    stage.mkdir(parents=True, exist_ok=True)
    shutil.copy2(app, stage / APP_NAME)
    shutil.copy2(root / "THIRD_PARTY_NOTICES.md", stage / "THIRD_PARTY_NOTICES.md")
    _write_release_readme(stage / "README.txt")

    archive_base = dist / PACKAGE_NAME
    archive = Path(shutil.make_archive(str(archive_base), "zip", root_dir=dist, base_dir=PACKAGE_NAME))
    report = {
        "status": "built",
        "application": str(stage / APP_NAME),
        "archive": str(archive),
        "bridge": str(bundled_bridge),
        "archive_size": archive.stat().st_size,
    }
    (dist / "fragmenter_release_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        report = build_release(root)
    except (OSError, ReleaseBuildError) as exc:
        print(f"\nRelease build failed: {exc}", file=sys.stderr)
        return 1
    print("\nRelease package ready:")
    print(report["archive"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

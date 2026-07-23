#!/usr/bin/env python3
"""Verified Tellipatch resource installation and resolution for V122."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import tempfile
import sys
import zipfile
from pathlib import Path
from typing import Any

import tellipatch_native as native

INSTALLER_SHELL_SHA256 = "044a4df8ec3d970cfd0bce5b57019708cf4f92110dc7ae9d746731aa7ca1332e"
PATCH_ARCHIVE_SHA256 = native.PATCH_RESOURCE_SHA256
DATA_ROOT_ENV = "FRAGMENTER_DATA_DIR"
PATCH_OVERRIDE_ENV = "FRAGMENTER_TELLIPATCH_PATCHES"

_ORIGINAL_READ_ASSETS = native._read_assets
_INSTALLED = False


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def data_root() -> Path:
    override = os.environ.get(DATA_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Fragmenter"
    return Path.home() / ".fragmenter"


def cached_patch_path() -> Path:
    return data_root() / "resources" / native.PATCH_RESOURCE


def bundled_game_setup_root() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        root = Path(__file__).resolve().parents[1]
    return root / "resources" / "game_setup"


def _materialize_bundled_patch_archive() -> Path:
    parts = (
        bundled_game_setup_root() / "Tellipatch-v3.8-patches.zip.rawpart1.b64",
        bundled_game_setup_root() / "Tellipatch-v3.8-patches.zip.rawpart2.b64",
    )
    if not all(path.is_file() for path in parts):
        raise native.TellipatchError("Bundled English patch resource is incomplete.")
    try:
        payload = b"".join(
            base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
            for path in parts
        )
    except (OSError, ValueError) as exc:
        raise native.TellipatchError(
            f"Bundled English patch resource could not be decoded: {exc}"
        ) from exc
    _validate_zip_payload(payload, source_label="Bundled English patch resource")
    target = cached_patch_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _validate_zip_payload(data: bytes, *, source_label: str) -> dict[str, Any]:
    digest = _sha256_bytes(data)
    if digest != PATCH_ARCHIVE_SHA256:
        raise native.TellipatchError(
            f"{source_label} is not the supported Tellipatch v3.8 patches.zip. "
            f"Expected SHA-256 {PATCH_ARCHIVE_SHA256}, found {digest}."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            expected = set(native.EXPECTED_PATCH_TARGETS)
            if names != expected:
                missing = sorted(expected - names)
                extra = sorted(names - expected)
                raise native.TellipatchError(
                    f"{source_label} has unexpected contents "
                    f"(missing={missing}, extra={extra})."
                )
            bad_member = archive.testzip()
            if bad_member is not None:
                raise native.TellipatchError(
                    f"{source_label} failed ZIP CRC validation at {bad_member}."
                )
    except zipfile.BadZipFile as exc:
        raise native.TellipatchError(f"{source_label} is not a readable ZIP archive: {exc}") from exc
    return {
        "sha256": digest,
        "size": len(data),
        "files": sorted(native.EXPECTED_PATCH_TARGETS),
    }


def validate_patch_archive(path: str | Path) -> dict[str, Any]:
    archive_path = Path(path).expanduser().resolve()
    if not archive_path.is_file():
        raise native.TellipatchError(f"Tellipatch patch archive was not found: {archive_path}")
    report = _validate_zip_payload(
        archive_path.read_bytes(),
        source_label=f"Patch archive {archive_path}",
    )
    report["path"] = str(archive_path)
    return report


def extract_patch_archive(source: str | Path) -> tuple[bytes, dict[str, Any]]:
    """Accept the exact patches.zip or find that exact payload inside an outer ZIP."""
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise native.TellipatchError(f"Selected Tellipatch file was not found: {source_path}")
    source_bytes = source_path.read_bytes()
    source_hash = _sha256_bytes(source_bytes)

    if source_hash == PATCH_ARCHIVE_SHA256:
        report = _validate_zip_payload(
            source_bytes,
            source_label=f"Patch archive {source_path}",
        )
        report.update(
            {
                "source_path": str(source_path),
                "source_kind": "direct-patches-zip",
                "source_sha256": source_hash,
            }
        )
        return source_bytes, report

    try:
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as outer:
            candidates = [
                name
                for name in outer.namelist()
                if Path(name).name.casefold() in {
                    "patches.zip",
                    native.PATCH_RESOURCE.casefold(),
                }
            ]
            for member in candidates:
                inner = outer.read(member)
                if _sha256_bytes(inner) != PATCH_ARCHIVE_SHA256:
                    continue
                report = _validate_zip_payload(
                    inner,
                    source_label=f"Nested patch archive {member} in {source_path}",
                )
                report.update(
                    {
                        "source_path": str(source_path),
                        "source_kind": "nested-patches-zip",
                        "source_sha256": source_hash,
                        "source_member": member,
                        "known_installer_shell": source_hash == INSTALLER_SHELL_SHA256,
                    }
                )
                return inner, report
    except (OSError, zipfile.BadZipFile) as exc:
        raise native.TellipatchError(
            f"Selected file is neither the official patches.zip nor a readable Tellipatch release ZIP: {exc}"
        ) from exc

    raise native.TellipatchError(
        "No exact Tellipatch v3.8 patches.zip was found in the selected file. "
        f"The required inner archive SHA-256 is {PATCH_ARCHIVE_SHA256}."
    )


def install_patch_source(
    source: str | Path,
    *,
    destination: str | Path | None = None,
) -> dict[str, Any]:
    payload, report = extract_patch_archive(source)
    target = Path(destination).expanduser().resolve() if destination else cached_patch_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=target.name + ".",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    installed = validate_patch_archive(target)
    report.update(
        {
            "installed_path": str(target),
            "installed_sha256": installed["sha256"],
            "installed_size": installed["size"],
        }
    )
    return report


def resolve_patch_archive() -> tuple[Path, dict[str, Any]]:
    candidates: list[tuple[str, Path]] = []
    override = os.environ.get(PATCH_OVERRIDE_ENV)
    if override:
        candidates.append(("environment override", Path(override).expanduser()))
    candidates.append(("installed cache", cached_patch_path()))
    bundled = Path(__file__).resolve().parents[1] / "resources" / native.PATCH_RESOURCE
    candidates.append(("bundled resource", bundled))

    rejected: list[str] = []
    for label, candidate in candidates:
        candidate = candidate.resolve()
        if not candidate.is_file():
            continue
        try:
            report = validate_patch_archive(candidate)
        except native.TellipatchError as exc:
            rejected.append(f"{label}: {exc}")
            continue
        report["source"] = label
        return candidate, report

    try:
        materialized = _materialize_bundled_patch_archive()
        report = validate_patch_archive(materialized)
        report["source"] = "bundled verified resource"
        return materialized, report
    except native.TellipatchError as exc:
        rejected.append(f"bundled resource: {exc}")

    detail = "\n".join(rejected)
    suffix = f"\nRejected candidates:\n{detail}" if detail else ""
    raise native.TellipatchError(
        "The verified bundled English patch resource is unavailable or damaged."
        + suffix
    )


def _read_assets_v122(
    patch_zip: str | Path | None,
    translation_csv_gz: str | Path | None,
):
    if patch_zip is None:
        patch_path, patch_report = resolve_patch_archive()
    else:
        patch_path = Path(patch_zip).expanduser().resolve()
        patch_report = validate_patch_archive(patch_path)
        patch_report["source"] = "explicit path"

    patches, csv_bytes, report = _ORIGINAL_READ_ASSETS(patch_path, translation_csv_gz)
    report["patch_archive_path"] = str(patch_path)
    report["patch_archive_source"] = patch_report["source"]
    report["patch_archive_sha256"] = patch_report["sha256"]
    report["resource_policy"] = "exact-official-sha256"
    return patches, csv_bytes, report


def install() -> None:
    """Install the verified V122 resolver once."""
    global _INSTALLED
    if _INSTALLED:
        return
    native._read_assets = _read_assets_v122
    _INSTALLED = True

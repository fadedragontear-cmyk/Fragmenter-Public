#!/usr/bin/env python3
"""One-step untouched Japanese ISO to verified Fragment 4.0 English builder."""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from netslum_completion_v124 import (
    FINAL_VOLUME_LABEL,
    CompletionPackError,
    _load_pack,
    apply_completion_pack,
)
from tellipatch_native import TellipatchError, build_english_iso
from tellipatch_resource_v122 import data_root, resolve_patch_archive

COMPLETION_RESOURCE = "Fragment-4.0-completion.zip"
COMPLETION_RESOURCE_SHA256 = (
    "46ee3644fca9023695a092ab829a16bd03a73dc252586130297e41731e792de1"
)
EXPECTED_COMPLETION_TARGETS = {
    "data/data.bin": "abbaff69f307182472ebeba19f41b6daf8373e5f24ab4452864abfcabe61cca1",
    "data/desktopf.prg": "3a09d57443d81494ee8437f80d72a7b83831352eba4ac0a2ce88bfee450514ee",
    "data/gcmnf.prg": "a18d377b663a2c5b0de87e5ebdbbedd71bb7a07bf502deac230d840817e6d969",
    "data/gcmno.prg": "c715fb2f5532c5a251498d404c6b497cd14660c5b8553fa72dd07f5bb4be2413",
    "data/matching.prg": "d6530a209eaa1ebbf46384655eb2470004637b222e12cc8730edf7a46312155a",
    "data/toppagef.prg": "ab29fdfcd1ac6496223662cd48f578ca6924f111e8b2d875bb3fb071a20e246d",
    "hack_00.elf": "3ccb5987d7b6b45d63eb1fa26b8d3b88bf8c8ec9eedf7179851bd567685164a7",
    "hack_01.elf": "cfe55a3187cbd755e0dad273fb356950b13eca7ea877abb1132da9264210a29a",
}
Progress = Callable[[str], None]


class Fragment4BuildError(RuntimeError):
    """Raised when the one-step 4.0 build cannot be verified safely."""


def _notify(progress: Progress | None, message: str) -> None:
    if progress is not None:
        progress(message)


def bundled_game_setup_root() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        root = Path(__file__).resolve().parents[1]
    return root / "resources" / "game_setup"


def cached_completion_path() -> Path:
    return data_root() / "resources" / COMPLETION_RESOURCE


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_completion_resource(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise Fragment4BuildError(f"4.0 completion resource was not found: {target}")
    digest = _sha256(target)
    if digest != COMPLETION_RESOURCE_SHA256:
        raise Fragment4BuildError(
            "4.0 completion resource integrity failed: "
            f"expected {COMPLETION_RESOURCE_SHA256}, found {digest}."
        )
    try:
        manifest, _payloads = _load_pack(target)
    except CompletionPackError as exc:
        raise Fragment4BuildError(f"4.0 completion resource is invalid: {exc}") from exc
    targets = {
        str(record.get("path")): str(record.get("target_sha256"))
        for record in manifest["files"]
    }
    if targets != EXPECTED_COMPLETION_TARGETS:
        raise Fragment4BuildError("4.0 completion target manifest is not the supported set.")
    return {
        "path": str(target),
        "sha256": digest,
        "size": target.stat().st_size,
        "targets": len(targets),
    }


def resolve_completion_resource() -> tuple[Path, dict[str, Any]]:
    cached = cached_completion_path()
    if cached.is_file():
        try:
            report = validate_completion_resource(cached)
            report["source"] = "materialized bundled resource"
            return cached, report
        except Fragment4BuildError:
            cached.unlink(missing_ok=True)

    encoded = bundled_game_setup_root() / (COMPLETION_RESOURCE + ".b64")
    if not encoded.is_file():
        raise Fragment4BuildError("Bundled 4.0 completion resource is missing.")
    try:
        payload = base64.b64decode(
            encoded.read_text(encoding="ascii").strip(),
            validate=True,
        )
    except (OSError, ValueError) as exc:
        raise Fragment4BuildError(
            f"Bundled 4.0 completion resource could not be decoded: {exc}"
        ) from exc
    if hashlib.sha256(payload).hexdigest() != COMPLETION_RESOURCE_SHA256:
        raise Fragment4BuildError("Bundled 4.0 completion resource integrity failed.")

    cached.parent.mkdir(parents=True, exist_ok=True)
    temporary = cached.with_name(f".{cached.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, cached)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    report = validate_completion_resource(cached)
    report["source"] = "bundled resource"
    return cached, report


def build_fragment_4_english(
    source_iso: str | Path,
    output_iso: str | Path,
    *,
    overwrite: bool = False,
    progress: Progress | None = None,
) -> dict[str, Any]:
    source = Path(source_iso).expanduser().resolve()
    output = Path(output_iso).expanduser().resolve()
    if not source.is_file():
        raise Fragment4BuildError(f"Untouched Japanese source ISO was not found: {source}")
    if source == output:
        raise Fragment4BuildError("Output ISO must be separate from the source ISO.")
    if output.exists() and not overwrite:
        raise Fragment4BuildError(f"Output already exists: {output}")

    try:
        patch_path, patch_report = resolve_patch_archive()
        completion_path, completion_report = resolve_completion_resource()
    except (TellipatchError, CompletionPackError) as exc:
        raise Fragment4BuildError(str(exc)) from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    preview = output.with_name(
        f".{output.name}.{uuid.uuid4().hex}.english-preview.tmp.iso"
    )
    try:
        _notify(progress, "Verifying untouched Japanese ISO and bundled resources")

        def english_progress(
            _phase: str,
            current: int,
            total: int,
            message: str,
        ) -> None:
            suffix = f" ({current:,}/{total:,})" if total > 1 else ""
            _notify(progress, "English translation: " + message + suffix)

        english_report = build_english_iso(
            source,
            preview,
            patch_zip=patch_path,
            progress=english_progress,
        )
        _notify(progress, "Applying the bundled Fragment 4.0 completion")
        completion_result = apply_completion_pack(
            preview,
            completion_path,
            output,
            overwrite=overwrite,
            progress=progress,
        )
    except Exception as exc:
        output.unlink(missing_ok=True)
        if isinstance(exc, Fragment4BuildError):
            raise
        raise Fragment4BuildError(str(exc)) from exc
    finally:
        preview.unlink(missing_ok=True)

    return {
        "status": "complete",
        "source": str(source),
        "output": str(output),
        "output_size": output.stat().st_size,
        "volume_label": completion_result["volume_label"],
        "verified_4_0_files": completion_result["verified_files"],
        "english_patch_sha256": patch_report["sha256"],
        "completion_sha256": completion_report["sha256"],
        "english_report": english_report,
        "layout_note": completion_result["layout_note"],
        "cleanup": "All intermediate preview and completion material was removed.",
    }

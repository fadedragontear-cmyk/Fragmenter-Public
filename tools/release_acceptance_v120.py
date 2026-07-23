#!/usr/bin/env python3
"""Create a conservative automated acceptance report for Fragmenter V120."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pcsx2_setup import (
    BUNDLED_CARD_RAW_SHA256,
    Pcsx2SetupError,
    configure_fragment_pcsx2,
    inspect_memory_card,
)
from tellipatch_native import ORIGINAL_ISO_MD5, TellipatchError
from tellipatch_verify_v120 import verify_english_iso

AcceptanceProgress = Callable[[str, int, int, str], None]


@dataclass(frozen=True)
class AcceptanceCheck:
    key: str
    label: str
    status: str
    detail: str


def _notify(
    progress: AcceptanceProgress | None,
    stage: str,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress is not None:
        progress(stage, current, total, message)


def _md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _missing(key: str, label: str, value: str | Path | None) -> AcceptanceCheck | None:
    if value is not None and str(value).strip():
        return None
    return AcceptanceCheck(key, label, "skip", "No path was supplied.")


def _resolved_optional(value: str | Path | None) -> Path | None:
    if value is None or not str(value).strip():
        return None
    return Path(value).expanduser().resolve()


def check_pcsx2_ini(path: str | Path) -> AcceptanceCheck:
    try:
        preview = configure_fragment_pcsx2(path, dry_run=True)
    except (OSError, Pcsx2SetupError) as exc:
        return AcceptanceCheck("pcsx2", "PCSX2 keyboard + network", "fail", str(exc))
    if preview.status == "already-configured":
        return AcceptanceCheck(
            "pcsx2",
            "PCSX2 keyboard + network",
            "pass",
            f"USB1={preview.keyboard_type}; Ethernet={preview.network_enabled}.",
        )
    return AcceptanceCheck(
        "pcsx2",
        "PCSX2 keyboard + network",
        "fail",
        "PCSX2.ini is readable but still needs the Fragment keyboard/network changes.",
    )


def check_memory_card(path: str | Path) -> AcceptanceCheck:
    try:
        info = inspect_memory_card(path)
    except (OSError, Pcsx2SetupError) as exc:
        return AcceptanceCheck("memory_card", "Fragment network memory card", "fail", str(exc))
    if info.sha256 != BUNDLED_CARD_RAW_SHA256:
        return AcceptanceCheck(
            "memory_card",
            "Fragment network memory card",
            "fail",
            "The selected card is a supported raw card, but it is not the included clean network card.",
        )
    return AcceptanceCheck(
        "memory_card",
        "Fragment network memory card",
        "pass",
        f"Exact included card verified ({info.size_mib} MiB; SHA-256 {info.sha256}).",
    )


def check_source_iso(path: str | Path) -> AcceptanceCheck:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        return AcceptanceCheck(
            "source_iso",
            "Untouched Japanese source ISO",
            "fail",
            f"File not found: {source}",
        )
    try:
        actual = _md5_file(source)
    except OSError as exc:
        return AcceptanceCheck("source_iso", "Untouched Japanese source ISO", "fail", str(exc))
    if actual.casefold() != ORIGINAL_ISO_MD5.casefold():
        return AcceptanceCheck(
            "source_iso",
            "Untouched Japanese source ISO",
            "fail",
            f"MD5 mismatch: expected {ORIGINAL_ISO_MD5}, found {actual}.",
        )
    return AcceptanceCheck(
        "source_iso",
        "Untouched Japanese source ISO",
        "pass",
        f"Supported original disc verified (MD5 {actual}).",
    )


def check_english_iso(
    source_iso: str | Path,
    output_iso: str | Path,
    *,
    source_already_verified: bool = False,
    progress: AcceptanceProgress | None = None,
) -> tuple[AcceptanceCheck, dict[str, Any] | None]:
    try:
        report = verify_english_iso(
            source_iso,
            output_iso,
            expected_md5=None if source_already_verified else ORIGINAL_ISO_MD5,
            progress=progress,
        )
    except (OSError, TellipatchError) as exc:
        return (
            AcceptanceCheck("english_iso", "English Phase 1+2 output ISO", "fail", str(exc)),
            None,
        )
    return (
        AcceptanceCheck(
            "english_iso",
            "English Phase 1+2 output ISO",
            "pass",
            (
                "All 7 binary targets and final translated text match, and no "
                "unexpected changes were found elsewhere in the ISO."
            ),
        ),
        report,
    )


def _write_report_atomic(destination: Path, report: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.fragmenter.tmp"
    )
    try:
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def run_acceptance(
    *,
    pcsx2_ini: str | Path | None = None,
    memory_card: str | Path | None = None,
    source_iso: str | Path | None = None,
    english_iso: str | Path | None = None,
    report_path: str | Path | None = None,
    progress: AcceptanceProgress | None = None,
) -> dict[str, Any]:
    checks: list[AcceptanceCheck] = []
    translation_report: dict[str, Any] | None = None

    _notify(progress, "acceptance", 0, 4, "Checking PCSX2 keyboard and network settings")
    missing_pcsx2 = _missing("pcsx2", "PCSX2 keyboard + network", pcsx2_ini)
    checks.append(missing_pcsx2 or check_pcsx2_ini(str(pcsx2_ini)))

    _notify(progress, "acceptance", 1, 4, "Checking the installed Fragment network card")
    missing_card = _missing("memory_card", "Fragment network memory card", memory_card)
    checks.append(missing_card or check_memory_card(str(memory_card)))

    _notify(progress, "acceptance", 2, 4, "Verifying the untouched Japanese source ISO")
    missing_source = _missing("source_iso", "Untouched Japanese source ISO", source_iso)
    source_check = missing_source or check_source_iso(str(source_iso))
    checks.append(source_check)

    missing_output = _missing("english_iso", "English Phase 1+2 output ISO", english_iso)
    if missing_output is not None:
        checks.append(missing_output)
    elif source_check.status != "pass":
        checks.append(
            AcceptanceCheck(
                "english_iso",
                "English Phase 1+2 output ISO",
                "skip",
                "The source ISO must pass verification before the output can be checked.",
            )
        )
    else:
        _notify(progress, "acceptance", 3, 4, "Verifying the complete English Phase 1+2 ISO")
        english_check, translation_report = check_english_iso(
            str(source_iso),
            str(english_iso),
            source_already_verified=True,
            progress=progress,
        )
        checks.append(english_check)

    destination = _resolved_optional(report_path)
    if destination is not None:
        protected = {
            path
            for path in (
                _resolved_optional(pcsx2_ini),
                _resolved_optional(memory_card),
                _resolved_optional(source_iso),
                _resolved_optional(english_iso),
            )
            if path is not None
        }
        if destination in protected:
            checks.append(
                AcceptanceCheck(
                    "report",
                    "Acceptance report destination",
                    "fail",
                    "The report path matches an input file. Choose a separate .json filename.",
                )
            )
            destination = None

    statuses = {item.status for item in checks}
    if "fail" in statuses:
        automated_status = "failed"
    elif "skip" in statuses:
        automated_status = "incomplete"
    else:
        automated_status = "passed"

    report: dict[str, Any] = {
        "schema": 1,
        "tool": "Fragmenter V120 automated acceptance",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "automated_status": automated_status,
        "checks": [asdict(item) for item in checks],
        "translation": translation_report,
        "manual_pcsx2_checks": [
            {"key": "boot", "status": "pending", "label": "Boot the English ISO in PCSX2"},
            {"key": "menus", "status": "pending", "label": "Check offline and online menus"},
            {"key": "network", "status": "pending", "label": "Confirm network login and server connection"},
            {"key": "text", "status": "pending", "label": "Inspect translated text and wrapping"},
            {"key": "gameplay", "status": "pending", "label": "Enter and play at least one area"},
        ],
        "scope_note": (
            "Automated acceptance covers PCSX2 settings, the included network card, "
            "the supported source ISO, and Tellipatch phases 1+2. The separate legacy "
            "visual-patcher phase is not included."
        ),
    }
    if destination is not None:
        report["report_path"] = str(destination)
        _notify(progress, "report", 0, 1, "Writing the acceptance report")
        _write_report_atomic(destination, report)
        _notify(progress, "report", 1, 1, "Acceptance report saved")

    _notify(progress, "acceptance", 4, 4, f"Automated acceptance {automated_status}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcsx2-ini", type=Path)
    parser.add_argument("--memory-card", type=Path)
    parser.add_argument("--source-iso", type=Path)
    parser.add_argument("--english-iso", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = run_acceptance(
        pcsx2_ini=args.pcsx2_ini,
        memory_card=args.memory_card,
        source_iso=args.source_iso,
        english_iso=args.english_iso,
        report_path=args.report,
    )
    print(json.dumps(report, indent=2))
    return {"passed": 0, "incomplete": 1, "failed": 2}[report["automated_status"]]


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only Area Server executable patch signature scanner.

This tool intentionally does not patch executables. It reports where known
original byte signatures and their replacement bytes appear so users can tell
whether an executable looks unpatched, already patched, or unmatched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIGNATURES = ROOT / "data" / "area_server_patch_signatures.json"
DEFAULT_JSON_OUT = ROOT / "workspace" / "reports" / "area_server_patch_scan.json"
DEFAULT_TEXT_OUT = ROOT / "workspace" / "reports" / "area_server_patch_scan.txt"
NO_PATCHING_NOTE = "No patching was performed; this scan is read-only and does not write patched executables."


def parse_hex_bytes(value: str) -> bytes:
    """Parse a space-separated hex byte signature."""
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"invalid hex byte pattern: {value!r}") from exc


def find_all(data: bytes, needle: bytes) -> list[int]:
    """Return every offset where needle appears in data, including overlaps."""
    if not needle:
        return []
    offsets: list[int] = []
    start = 0
    while True:
        offset = data.find(needle, start)
        if offset == -1:
            return offsets
        offsets.append(offset)
        start = offset + 1


def load_signatures(path: Path = DEFAULT_SIGNATURES) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    signatures = payload.get("signatures")
    if not isinstance(signatures, list):
        raise ValueError(f"signature file must contain a signatures list: {path}")
    return payload


def scan_binary(exe_path: Path, signatures_path: Path = DEFAULT_SIGNATURES) -> dict[str, Any]:
    signature_payload = load_signatures(signatures_path)
    data = exe_path.read_bytes()

    results: list[dict[str, Any]] = []
    missing: list[str] = []
    already_patched: list[dict[str, Any]] = []

    for raw_sig in signature_payload["signatures"]:
        name = str(raw_sig.get("name", "<unnamed>"))
        pattern = parse_hex_bytes(str(raw_sig.get("pattern", "")))
        replacement = parse_hex_bytes(str(raw_sig.get("replace", "")))
        pattern_offsets = find_all(data, pattern)
        replacement_offsets = find_all(data, replacement)

        record = {
            "name": name,
            "pattern": raw_sig.get("pattern", ""),
            "replace": raw_sig.get("replace", ""),
            "found_offsets": pattern_offsets,
            "already_patched_offsets": replacement_offsets,
            "missing": not pattern_offsets and not replacement_offsets,
        }
        results.append(record)

        if record["missing"]:
            missing.append(name)
        if replacement_offsets:
            already_patched.append({"name": name, "offsets": replacement_offsets})

    return {
        "areasrv_exe": str(exe_path),
        "signature_file": str(signatures_path),
        "binary_size": len(data),
        "safety_note": NO_PATCHING_NOTE,
        "signature_safety_notes": signature_payload.get("safety_notes", []),
        "signatures": results,
        "missing_signatures": missing,
        "already_patched": already_patched,
    }


def format_text_report(report: dict[str, Any]) -> str:
    lines = [
        "Area Server Patch Signature Scan",
        "================================",
        f"Executable: {report['areasrv_exe']}",
        f"Signature file: {report['signature_file']}",
        f"Binary size: {report['binary_size']} bytes",
        "",
        f"Safety: {report['safety_note']}",
        "",
        "Signatures:",
    ]
    for sig in report["signatures"]:
        found = ", ".join(hex(v) for v in sig["found_offsets"]) or "none"
        patched = ", ".join(hex(v) for v in sig["already_patched_offsets"]) or "none"
        status = "missing" if sig["missing"] else "found"
        if sig["already_patched_offsets"]:
            status = "already patched" if not sig["found_offsets"] else "found and already patched"
        lines.extend([
            f"- {sig['name']}: {status}",
            f"  original pattern offsets: {found}",
            f"  replacement/already-patched offsets: {patched}",
        ])
    lines.append("")
    lines.append("Missing signatures: " + (", ".join(report["missing_signatures"]) or "none"))
    if report["already_patched"]:
        patched = "; ".join(f"{item['name']} at {', '.join(hex(v) for v in item['offsets'])}" for item in report["already_patched"])
    else:
        patched = "none"
    lines.append("Already-patched offsets: " + patched)
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], out: Path, text_out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    text_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    text_out.write_text(format_text_report(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only scan for Area Server executable patch signatures")
    parser.add_argument("areasrv_exe", metavar="areasrv.exe")
    parser.add_argument("--out", default=str(DEFAULT_JSON_OUT), help="JSON report path")
    parser.add_argument("--text-out", default=str(DEFAULT_TEXT_OUT), help="Text report path")
    args = parser.parse_args()

    report = scan_binary(Path(args.areasrv_exe))
    write_report(report, Path(args.out), Path(args.text_out))
    print(f"Wrote {args.out}")
    print(f"Wrote {args.text_out}")
    print(NO_PATCHING_NOTE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

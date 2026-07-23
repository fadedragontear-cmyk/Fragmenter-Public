#!/usr/bin/env python3
"""Validate that PSound diagnostics reference one corrected SNDDATA extraction report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compare_psound_to_latest_fragmenter_v1 import _require_corrected_report


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unreadable diagnostic JSON: {path}: {exc}") from exc


def validate_context(output: str | Path, *, require_pcm: bool = False) -> dict[str, Any]:
    root = Path(output).expanduser().resolve()
    manifest_path = root / "psound_reference_manifest.json"
    comparison_path = root / "psound_vs_fragmenter_by_order.json"
    pcm_path = root / "psound_fragmenter_pcm_identity.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Missing current-run PSound manifest: {manifest_path}. "
            "Run COMPARE_PSOUND_TO_LATEST_FRAGMENTER.cmd first."
        )
    if not comparison_path.is_file():
        raise FileNotFoundError(
            f"Missing current-run comparison JSON: {comparison_path}. "
            "Run COMPARE_PSOUND_TO_LATEST_FRAGMENTER.cmd first."
        )

    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"PSound manifest must contain an object: {manifest_path}")
    report_text = str(manifest.get("fragmenter_report") or "").strip()
    if not report_text:
        raise ValueError(f"PSound manifest does not identify its Fragmenter report: {manifest_path}")
    report_path = Path(report_text).expanduser().resolve()
    if not report_path.is_file():
        raise FileNotFoundError(f"Fragmenter report recorded by PSound manifest is missing: {report_path}")

    report_summary = _require_corrected_report(report_path, allow_legacy_trim=False)

    pcm_report = None
    if require_pcm and not pcm_path.is_file():
        raise FileNotFoundError(
            f"Missing current-run PCM identity JSON: {pcm_path}. "
            "Run MAP_PSOUND_PCM_IDENTITY.cmd first."
        )
    if pcm_path.is_file():
        pcm = _load_json(pcm_path)
        if not isinstance(pcm, dict):
            raise ValueError(f"PCM identity JSON must contain an object: {pcm_path}")
        pcm_report_text = str(pcm.get("fragmenter_report") or "").strip()
        if not pcm_report_text:
            raise ValueError(f"PCM identity JSON does not identify its Fragmenter report: {pcm_path}")
        pcm_report = Path(pcm_report_text).expanduser().resolve()
        if pcm_report != report_path:
            raise ValueError(
                "PSound comparison and PCM identity files reference different Fragmenter reports: "
                f"{report_path} != {pcm_report}. Regenerate both diagnostics."
            )

    return {
        "output": str(root),
        "fragmenter_report": str(report_path),
        "corrected_trim_rows": int(report_summary.get("corrected_trim_rows") or 0),
        "trim_rows": int(report_summary.get("trim_rows") or 0),
        "legacy_flag_07_rows": int(report_summary.get("legacy_flag_07_rows") or 0),
        "pcm_identity_present": pcm_report is not None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default=str(Path.cwd() / "diagnostics" / "psound_reference"))
    parser.add_argument("--require-pcm", action="store_true")
    args = parser.parse_args(argv)

    summary = validate_context(args.output, require_pcm=args.require_pcm)
    print("PSound diagnostic context validated.")
    print(f"Fragmenter report: {summary['fragmenter_report']}")
    print(f"Corrected trim rows: {summary['corrected_trim_rows']}/{summary['trim_rows']}")
    print(f"Legacy flag-07 terminators: {summary['legacy_flag_07_rows']}")
    print(f"PCM identity present: {summary['pcm_identity_present']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

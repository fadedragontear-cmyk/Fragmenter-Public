#!/usr/bin/env python3
"""Find the newest corrected Fragmenter SNDDATA report and compare it with PSound."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from psound_reference_manifest_v1 import build_manifest

REPORT_NAMES = (
    "snddata_sample_library.json",
    "snddata_sample_library_v2.json",
    "snddata_sample_library_v1.json",
)
EXCLUDED_PARTS = {".git", "diagnostics", "__pycache__", ".fragmenter_state"}
CORRECTED_TRIM_POLICY = "sceivagi_span_trailing_separator_only_v3"


def _read_report_summary(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    samples = payload.get("samples") if isinstance(payload, dict) else None
    if not isinstance(samples, list) or not samples:
        return None
    rows = [row for row in samples if isinstance(row, dict)]
    if not rows:
        return None

    trim_rows = 0
    corrected_trim_rows = 0
    legacy_flag_07_rows = 0
    for row in rows:
        trim = row.get("trim")
        if not isinstance(trim, dict):
            continue
        trim_rows += 1
        if trim.get("policy") == CORRECTED_TRIM_POLICY:
            corrected_trim_rows += 1
        if trim.get("terminator_kind") == "adpcm_flag_07":
            legacy_flag_07_rows += 1

    return {
        "sample_rows": len(rows),
        "flat_rows": sum(row.get("flat_index") is not None for row in rows),
        "payload_rows": sum(row.get("payload_size") is not None for row in rows),
        "trim_rows": trim_rows,
        "corrected_trim_rows": corrected_trim_rows,
        "legacy_flag_07_rows": legacy_flag_07_rows,
    }


def _is_fully_corrected(summary: dict[str, Any]) -> bool:
    trim_rows = int(summary.get("trim_rows") or 0)
    corrected_rows = int(summary.get("corrected_trim_rows") or 0)
    legacy_rows = int(summary.get("legacy_flag_07_rows") or 0)
    return trim_rows > 0 and corrected_rows == trim_rows and legacy_rows == 0


def _is_excluded(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part.casefold() in EXCLUDED_PARTS for part in relative.parts[:-1])


def find_latest_fragmenter_report(
    search_root: str | Path,
    *,
    require_corrected_trim: bool = True,
) -> Path:
    root = Path(search_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Fragmenter report search root is not a directory: {root}")

    candidates: list[tuple[tuple[int, int, int, int, int], Path]] = []
    usable_reports = 0
    name_priority = {name.casefold(): len(REPORT_NAMES) - index for index, name in enumerate(REPORT_NAMES)}
    for name in REPORT_NAMES:
        for path in root.rglob(name):
            if not path.is_file() or _is_excluded(path, root):
                continue
            summary = _read_report_summary(path)
            if summary is None:
                continue
            usable_reports += 1
            corrected = int(_is_fully_corrected(summary))
            if not corrected and require_corrected_trim:
                continue
            try:
                modified_ns = path.stat().st_mtime_ns
            except OSError:
                continue
            score = (
                corrected,
                int(summary["flat_rows"] > 0),
                int(summary["payload_rows"] > 0),
                name_priority.get(path.name.casefold(), 0),
                modified_ns,
            )
            candidates.append((score, path.resolve()))

    if not candidates:
        searched = ", ".join(REPORT_NAMES)
        if require_corrected_trim and usable_reports:
            raise FileNotFoundError(
                f"Found {usable_reports} usable Fragmenter SNDDATA report(s) under {root}, "
                f"but none are fully generated with corrected trim policy {CORRECTED_TRIM_POLICY!r}. "
                "They are stale or mixed-generation extraction reports. Run REEXTRACT_SNDDATA_CORRECTED.cmd "
                "with the project folder, then retry the comparison."
            )
        raise FileNotFoundError(
            f"No usable Fragmenter SNDDATA sample report was found under {root}. "
            f"Searched for: {searched}. Run corrected SNDDATA sample extraction first."
        )
    candidates.sort(key=lambda item: (item[0], str(item[1]).casefold()), reverse=True)
    return candidates[0][1]


def _require_corrected_report(path: Path, *, allow_legacy_trim: bool) -> dict[str, Any]:
    summary = _read_report_summary(path)
    if summary is None:
        raise ValueError(f"Fragmenter report is not a usable sample-library JSON file: {path}")
    if not allow_legacy_trim and not _is_fully_corrected(summary):
        raise ValueError(
            f"Fragmenter report is stale or mixed-generation and is not fully generated with corrected trim policy "
            f"{CORRECTED_TRIM_POLICY!r}: {path}. "
            f"Corrected rows={summary['corrected_trim_rows']}/{summary['trim_rows']}; "
            f"legacy flag-07 rows={summary['legacy_flag_07_rows']}. "
            "Run REEXTRACT_SNDDATA_CORRECTED.cmd with the project folder before comparing it with PSound."
        )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=r"C:\games\areaserver\FragmentModKit\PSound201")
    parser.add_argument("search_root", nargs="?", default=str(Path.cwd().parent))
    parser.add_argument("--output", default=str(Path.cwd() / "diagnostics" / "psound_reference"))
    parser.add_argument("--fragmenter-report")
    parser.add_argument(
        "--allow-legacy-trim",
        action="store_true",
        help="Permit a pre-fix report for historical diagnostics. Corrected comparisons reject it by default.",
    )
    args = parser.parse_args(argv)

    if args.fragmenter_report:
        report = Path(args.fragmenter_report).expanduser().resolve()
        if not report.is_file():
            raise FileNotFoundError(f"Fragmenter report is not a file: {report}")
    else:
        report = find_latest_fragmenter_report(
            args.search_root,
            require_corrected_trim=not args.allow_legacy_trim,
        )
    report_summary = _require_corrected_report(report, allow_legacy_trim=args.allow_legacy_trim)

    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    payload = build_manifest(
        source,
        fragmenter_report=report,
        output=output,
    )
    rows = payload.get("order_comparison") or []

    print(f"Fragmenter report: {report}")
    print(
        "Trim policy rows: "
        f"{report_summary['corrected_trim_rows']}/{report_summary['trim_rows']} corrected; "
        f"legacy flag-07 terminators={report_summary['legacy_flag_07_rows']}"
    )
    print(f"PSound files: {payload['file_count']}")
    print(f"Audio candidates: {payload['audio_candidate_count']}")
    print(f"Equal-number comparison rows: {payload.get('order_comparison_rows', 0)}")
    print(f"Raw equal-number length summary (identity unverified): {payload.get('comparison_summary', {})}")
    print(f"Comparison CSV: {output / 'psound_vs_fragmenter_by_order.csv'}")
    print("NOTE: equal PSound and Fragmenter numbers are only a rejected ordering hypothesis until the alignment audit runs.")

    row = next(
        (
            item for item in rows
            if isinstance(item, dict) and item.get("comparison_index_zero_based") == 228
        ),
        None,
    ) if isinstance(rows, list) else None
    if row is None:
        print("Equal-number row 0228: no row was produced.")
    else:
        print("Equal-number row 0228 (not established sample identity):")
        for key in (
            "psound_path",
            "psound_frames",
            "psound_inferred_ps_adpcm_blocks",
            "psound_inferred_encoded_payload_bytes",
            "fragmenter_flat_index",
            "fragmenter_bank_ordinal",
            "fragmenter_sample_id",
            "fragmenter_rate",
            "fragmenter_payload_size",
            "fragmenter_sample_count",
            "payload_delta_fragmenter_minus_psound_bytes",
            "block_delta_fragmenter_minus_psound",
            "boundary_relation",
        ):
            print(f"  {key}: {row.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

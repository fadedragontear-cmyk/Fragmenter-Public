#!/usr/bin/env python3
"""Audit PSound/Fragmenter ordering without treating equal numeric indices as identity."""
from __future__ import annotations

import argparse
import csv
import json
from array import array
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Comparison JSON must contain a list: {path}")
    return [dict(row) for row in payload if isinstance(row, dict)]


def _sequences(rows: list[dict[str, Any]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    psound: dict[int, int] = {}
    fragmenter: dict[int, int] = {}
    for row in rows:
        p_index = _optional_int(row.get("psound_sequence_number"))
        p_size = _optional_int(row.get("psound_inferred_encoded_payload_bytes"))
        if p_index is not None and p_size is not None:
            psound[p_index] = p_size
        f_index = _optional_int(row.get("fragmenter_flat_index"))
        f_size = _optional_int(row.get("fragmenter_payload_size"))
        if f_index is not None and f_size is not None:
            fragmenter[f_index] = f_size
    return sorted(psound.items()), sorted(fragmenter.items())


def exact_payload_lcs(
    psound: list[tuple[int, int]],
    fragmenter: list[tuple[int, int]],
) -> list[tuple[int, int, int]]:
    """Return monotonic exact-payload anchors using a deterministic LCS."""
    p_values = [value for _, value in psound]
    f_values = [value for _, value in fragmenter]
    n, m = len(p_values), len(f_values)
    matrix = [array("H", [0]) * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        row = matrix[i]
        previous = matrix[i - 1]
        value = p_values[i - 1]
        for j in range(1, m + 1):
            if value == f_values[j - 1]:
                row[j] = previous[j - 1] + 1
            else:
                above = previous[j]
                left = row[j - 1]
                row[j] = above if above >= left else left

    anchors: list[tuple[int, int, int]] = []
    i, j = n, m
    while i and j:
        if p_values[i - 1] == f_values[j - 1] and matrix[i][j] == matrix[i - 1][j - 1] + 1:
            anchors.append((psound[i - 1][0], fragmenter[j - 1][0], p_values[i - 1]))
            i -= 1
            j -= 1
        elif matrix[i - 1][j] >= matrix[i][j - 1]:
            i -= 1
        else:
            j -= 1
    anchors.reverse()
    return anchors


def _contiguous_runs(anchors: list[tuple[int, int, int]]) -> list[dict[str, int]]:
    if not anchors:
        return []
    output: list[dict[str, int]] = []
    start = previous = anchors[0]
    for current in anchors[1:]:
        if current[0] == previous[0] + 1 and current[1] == previous[1] + 1:
            previous = current
            continue
        output.append({
            "psound_start": start[0],
            "psound_end": previous[0],
            "fragmenter_start": start[1],
            "fragmenter_end": previous[1],
            "length": previous[0] - start[0] + 1,
            "offset": start[1] - start[0],
        })
        start = previous = current
    output.append({
        "psound_start": start[0],
        "psound_end": previous[0],
        "fragmenter_start": start[1],
        "fragmenter_end": previous[1],
        "length": previous[0] - start[0] + 1,
        "offset": start[1] - start[0],
    })
    return output


def audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    psound, fragmenter = _sequences(rows)
    anchors = exact_payload_lcs(psound, fragmenter)
    p_map = dict(psound)
    f_map = dict(fragmenter)
    same_index_pairs = sorted(set(p_map) & set(f_map))
    same_index_exact = [index for index in same_index_pairs if p_map[index] == f_map[index]]

    fragmenter_rows = {
        int(row["fragmenter_flat_index"]): row
        for row in rows
        if _optional_int(row.get("fragmenter_flat_index")) is not None
    }
    banks: dict[int, list[int]] = defaultdict(list)
    for index, row in fragmenter_rows.items():
        bank = _optional_int(row.get("fragmenter_bank_ordinal"))
        if bank is not None:
            banks[bank].append(index)
    first_bank = min(banks) if banks else None
    first_bank_summary: dict[str, Any] = {}
    if first_bank is not None:
        bank_indices = sorted(banks[first_bank])
        bank_set = set(bank_indices)
        bank_anchors = [item for item in anchors if item[1] in bank_set]
        if bank_anchors:
            p_start = min(item[0] for item in bank_anchors)
            p_end = max(item[0] for item in bank_anchors)
            p_span = p_end - p_start + 1
            coverage = len(bank_anchors) / p_span if p_span else 0.0
            likely = p_start == 0 and coverage >= 0.90
            first_bank_summary = {
                "fragmenter_bank_ordinal": first_bank,
                "fragmenter_flat_start": bank_indices[0],
                "fragmenter_flat_end": bank_indices[-1],
                "fragmenter_row_count": len(bank_indices),
                "exact_monotonic_anchor_count": len(bank_anchors),
                "anchored_psound_start": p_start,
                "anchored_psound_end": p_end,
                "anchored_psound_span_count": p_span,
                "anchor_coverage_of_psound_span": round(coverage, 8),
                "likely_psound_bank_range": [p_start, p_end] if likely else None,
                "candidate_extra_fragmenter_rows": len(bank_indices) - p_span if likely else None,
                "candidate_nonexact_lengths_within_psound_span": p_span - len(bank_anchors) if likely else None,
                "inference_status": (
                    "strong_length_sequence_evidence_not_yet_pcm_identity"
                    if likely else "insufficient_for_bank_range_inference"
                ),
            }

    same_index_ratio = len(same_index_exact) / len(psound) if psound else 0.0
    status = "undetermined"
    if len(anchors) >= 20 and same_index_ratio < 0.05 and len(anchors) > len(same_index_exact) * 5:
        status = "rejected_by_monotonic_length_sequence_evidence"

    sample_228_row = next(
        (row for row in rows if _optional_int(row.get("comparison_index_zero_based")) == 228),
        None,
    )
    sample_228: dict[str, Any] = {
        "same_index_row": sample_228_row,
        "same_index_interpretation": (
            "not_a_boundary_result_because_equal_flat_numbers_are_not_identity"
            if sample_228_row else "missing"
        ),
    }
    if sample_228_row and first_bank_summary.get("likely_psound_bank_range"):
        bank = _optional_int(sample_228_row.get("fragmenter_bank_ordinal"))
        local = _optional_int(sample_228_row.get("fragmenter_sample_id"))
        sorted_banks = sorted(banks)
        if bank in sorted_banks and sorted_banks.index(bank) == 1 and local is not None:
            candidate_index = int(first_bank_summary["anchored_psound_end"]) + 1 + local
            candidate_size = p_map.get(candidate_index)
            fragmenter_size = _optional_int(sample_228_row.get("fragmenter_payload_size"))
            sample_228["next_bank_order_hypothesis"] = {
                "candidate_psound_sequence_number": candidate_index,
                "candidate_psound_payload_size": candidate_size,
                "fragmenter_payload_size": fragmenter_size,
                "payload_delta_fragmenter_minus_psound": (
                    fragmenter_size - candidate_size
                    if fragmenter_size is not None and candidate_size is not None else None
                ),
                "confidence": "provisional_until_pcm_prefix_or_source_offset_identity",
            }

    runs = _contiguous_runs(anchors)
    return {
        "version": 1,
        "psound_rows": len(psound),
        "fragmenter_rows": len(fragmenter),
        "row_count_difference_fragmenter_minus_psound": len(fragmenter) - len(psound),
        "same_index_exact_payload_matches": len(same_index_exact),
        "same_index_exact_indices": same_index_exact,
        "same_index_exact_ratio": round(same_index_ratio, 8),
        "same_index_identity_hypothesis_status": status,
        "monotonic_exact_payload_anchor_count": len(anchors),
        "exact_payload_multiset_overlap": sum((Counter(p_map.values()) & Counter(f_map.values())).values()),
        "longest_contiguous_exact_run": max(runs, key=lambda item: item["length"]) if runs else None,
        "contiguous_exact_runs": sorted(runs, key=lambda item: item["length"], reverse=True),
        "first_fragmenter_bank": first_bank_summary,
        "sample_0228": sample_228,
        "interpretation": {
            "what_this_proves": (
                "PSound numbering and Fragmenter flat_index cannot be compared directly. "
                "Monotonic exact-length anchors show inserted or false Fragmenter rows and changing index offsets."
            ),
            "what_this_does_not_prove": (
                "A length anchor alone does not prove sound identity. PCM-prefix or source-offset evidence is "
                "required before using PSound lengths to rewrite boundaries."
            ),
        },
        "anchors": [
            {
                "psound_sequence_number": p_index,
                "fragmenter_flat_index": f_index,
                "encoded_payload_bytes": size,
                "index_offset_fragmenter_minus_psound": f_index - p_index,
            }
            for p_index, f_index, size in anchors
        ],
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison_json")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    comparison = Path(args.comparison_json).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else comparison.parent
    payload = audit(_load_rows(comparison))
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "psound_fragmenter_alignment_audit.json"
    csv_path = output / "psound_fragmenter_exact_payload_anchors.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, payload["anchors"])

    print("Ordering audit:")
    print(f"  PSound rows: {payload['psound_rows']}")
    print(f"  Fragmenter rows: {payload['fragmenter_rows']}")
    print(f"  Same-index exact payload matches: {payload['same_index_exact_payload_matches']}")
    print(f"  Monotonic exact payload anchors: {payload['monotonic_exact_payload_anchor_count']}")
    print(f"  Same-index identity hypothesis: {payload['same_index_identity_hypothesis_status']}")
    first = payload.get("first_fragmenter_bank") or {}
    if first:
        print(
            "  First bank evidence:",
            f"PSound {first.get('anchored_psound_start')}..{first.get('anchored_psound_end')}",
            f"to Fragmenter {first.get('fragmenter_flat_start')}..{first.get('fragmenter_flat_end')};",
            f"candidate extra Fragmenter rows={first.get('candidate_extra_fragmenter_rows')}",
        )
    sample = (payload.get("sample_0228") or {}).get("next_bank_order_hypothesis") or {}
    if sample:
        print(
            "  Fragmenter flat 0228 provisional bank-order candidate:",
            f"PSound {sample.get('candidate_psound_sequence_number')}",
            f"delta={sample.get('payload_delta_fragmenter_minus_psound')} bytes",
        )
    print(f"  Audit JSON: {json_path}")
    print(f"  Anchor CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

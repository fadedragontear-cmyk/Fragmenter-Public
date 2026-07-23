#!/usr/bin/env python3
"""Audit PSound lengths against Fragmenter SCEIVagi raw spans.

The comparison deliberately does not equate numeric indices. It finds a monotonic
sequence where a Fragmenter raw span is exactly two PS-ADPCM blocks (32 bytes)
longer than the number of blocks PSound decoded. This exposes premature trim
results while preserving PSound loop expansion as a separate observation.
"""
from __future__ import annotations

import argparse
import csv
import json
from array import array
from collections import Counter
from pathlib import Path
from typing import Any, Callable


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sequences(rows: list[dict[str, Any]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    psound: dict[int, int] = {}
    fragmenter: dict[int, int] = {}
    for row in rows:
        p_index = _optional_int(row.get("psound_sequence_number"))
        p_size = _optional_int(row.get("psound_inferred_encoded_payload_bytes"))
        if p_index is not None and p_size is not None:
            psound[p_index] = p_size
        f_index = _optional_int(row.get("fragmenter_flat_index"))
        f_size = _optional_int(row.get("fragmenter_raw_size"))
        if f_index is not None and f_size is not None:
            fragmenter[f_index] = f_size
    return sorted(psound.items()), sorted(fragmenter.items())


def _lcs(
    left: list[tuple[int, int]],
    right: list[tuple[int, int]],
    matches: Callable[[int, int], bool],
) -> list[tuple[int, int, int, int]]:
    n, m = len(left), len(right)
    matrix = [array("H", [0]) * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        row = matrix[i]
        previous = matrix[i - 1]
        left_value = left[i - 1][1]
        for j in range(1, m + 1):
            if matches(left_value, right[j - 1][1]):
                row[j] = previous[j - 1] + 1
            else:
                above = previous[j]
                prior = row[j - 1]
                row[j] = above if above >= prior else prior

    anchors: list[tuple[int, int, int, int]] = []
    i, j = n, m
    while i and j:
        if matches(left[i - 1][1], right[j - 1][1]) and matrix[i][j] == matrix[i - 1][j - 1] + 1:
            anchors.append((left[i - 1][0], right[j - 1][0], left[i - 1][1], right[j - 1][1]))
            i -= 1
            j -= 1
        elif matrix[i - 1][j] >= matrix[i][j - 1]:
            i -= 1
        else:
            j -= 1
    anchors.reverse()
    return anchors


def _runs(anchors: list[dict[str, Any]]) -> list[dict[str, int]]:
    if not anchors:
        return []
    output: list[dict[str, int]] = []
    start = previous = anchors[0]
    for current in anchors[1:]:
        if (
            int(current["psound_sequence_number"]) == int(previous["psound_sequence_number"]) + 1
            and int(current["fragmenter_flat_index"]) == int(previous["fragmenter_flat_index"]) + 1
        ):
            previous = current
            continue
        output.append({
            "psound_start": int(start["psound_sequence_number"]),
            "psound_end": int(previous["psound_sequence_number"]),
            "fragmenter_start": int(start["fragmenter_flat_index"]),
            "fragmenter_end": int(previous["fragmenter_flat_index"]),
            "length": int(previous["psound_sequence_number"]) - int(start["psound_sequence_number"]) + 1,
            "offset": int(start["fragmenter_flat_index"]) - int(start["psound_sequence_number"]),
        })
        start = previous = current
    output.append({
        "psound_start": int(start["psound_sequence_number"]),
        "psound_end": int(previous["psound_sequence_number"]),
        "fragmenter_start": int(start["fragmenter_flat_index"]),
        "fragmenter_end": int(previous["fragmenter_flat_index"]),
        "length": int(previous["psound_sequence_number"]) - int(start["psound_sequence_number"]) + 1,
        "offset": int(start["fragmenter_flat_index"]) - int(start["psound_sequence_number"]),
    })
    return output


def _loop_candidates(
    pcm_payload: dict[str, Any] | None,
    psound_sizes: dict[int, int],
    fragmenter_rows: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(pcm_payload, dict):
        return []
    output: list[dict[str, Any]] = []
    for mapping in pcm_payload.get("mappings") or []:
        if not isinstance(mapping, dict):
            continue
        p_index = _optional_int(mapping.get("psound_sequence_number"))
        f_index = _optional_int(mapping.get("unique_fragmenter_flat_index"))
        if p_index is None or f_index is None:
            continue
        p_size = psound_sizes.get(p_index)
        f_size = _optional_int((fragmenter_rows.get(f_index) or {}).get("fragmenter_payload_size"))
        if p_size is None or f_size is None or p_size <= f_size or p_size % 16 or f_size % 16:
            continue
        p_blocks = p_size // 16
        f_blocks = f_size // 16
        repeat_count = None
        overlap_blocks = None
        for repeats in range(2, 9):
            overlap = repeats * f_blocks - p_blocks
            if overlap == repeats - 1:
                repeat_count = repeats
                overlap_blocks = overlap
                break
        if repeat_count is None:
            continue
        output.append({
            "psound_sequence_number": p_index,
            "fragmenter_flat_index": f_index,
            "match_method": mapping.get("match_method"),
            "match_confidence": mapping.get("match_confidence"),
            "fragmenter_source_blocks": f_blocks,
            "psound_export_blocks": p_blocks,
            "inferred_repeat_count": repeat_count,
            "overlap_blocks_removed_between_repeats": overlap_blocks,
            "interpretation": "PSound appears to have unrolled a looping source stream; do not use its export length as the source boundary.",
        })
    return output


def audit(comparison_rows: list[dict[str, Any]], pcm_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    psound, fragmenter = _sequences(comparison_rows)
    raw_anchors = _lcs(psound, fragmenter, lambda p_size, raw_size: raw_size - p_size == 32)
    psound_sizes = dict(psound)
    fragmenter_rows = {
        int(row["fragmenter_flat_index"]): row
        for row in comparison_rows
        if _optional_int(row.get("fragmenter_flat_index")) is not None
    }

    anchors: list[dict[str, Any]] = []
    relation_counts: Counter[str] = Counter()
    for p_index, f_index, p_size, raw_size in raw_anchors:
        row = fragmenter_rows.get(f_index) or {}
        payload_size = _optional_int(row.get("fragmenter_payload_size"))
        if payload_size == p_size:
            relation = "payload_already_matches_psound"
        elif payload_size == raw_size:
            relation = "payload_retains_32_byte_wrapper"
        elif payload_size is not None and payload_size < p_size:
            relation = "payload_prematurely_trimmed"
        elif payload_size is not None and payload_size > p_size:
            relation = "payload_overlong_other"
        else:
            relation = "payload_unavailable"
        relation_counts[relation] += 1
        anchors.append({
            "psound_sequence_number": p_index,
            "fragmenter_flat_index": f_index,
            "fragmenter_bank_ordinal": _optional_int(row.get("fragmenter_bank_ordinal")),
            "fragmenter_sample_id": _optional_int(row.get("fragmenter_sample_id")),
            "psound_encoded_payload_bytes": p_size,
            "fragmenter_raw_size": raw_size,
            "fragmenter_payload_size": payload_size,
            "raw_minus_psound_bytes": raw_size - p_size,
            "payload_minus_psound_bytes": payload_size - p_size if payload_size is not None else None,
            "index_offset_fragmenter_minus_psound": f_index - p_index,
            "payload_relation": relation,
        })

    runs = _runs(anchors)
    offsets = Counter(int(row["index_offset_fragmenter_minus_psound"]) for row in anchors)
    loops = _loop_candidates(pcm_payload, psound_sizes, fragmenter_rows)
    return {
        "version": 1,
        "oracle": "fragmenter_raw_size_minus_32_equals_psound_inferred_encoded_payload_bytes",
        "psound_rows": len(psound),
        "fragmenter_rows": len(fragmenter),
        "row_count_difference_fragmenter_minus_psound": len(fragmenter) - len(psound),
        "raw_span_anchor_count": len(anchors),
        "raw_span_anchor_coverage_of_psound": round(len(anchors) / len(psound), 8) if psound else 0.0,
        "payload_relation_counts": dict(relation_counts),
        "first_anchor": anchors[0] if anchors else None,
        "last_anchor": anchors[-1] if anchors else None,
        "final_index_offset": int(anchors[-1]["index_offset_fragmenter_minus_psound"]) if anchors else None,
        "most_common_index_offsets": [
            {"offset": offset, "count": count}
            for offset, count in offsets.most_common(20)
        ],
        "longest_contiguous_raw_span_run": max(runs, key=lambda row: row["length"]) if runs else None,
        "contiguous_raw_span_runs": sorted(runs, key=lambda row: row["length"], reverse=True),
        "psound_loop_expansion_candidates": loops,
        "interpretation": {
            "raw_span_oracle": "Two extra aligned blocks are structural framing in these monotonic matches; the raw SCEIVagi span is otherwise consistent with PSound.",
            "premature_trim": "The current payload ended before the PSound-supported source length, usually because a legal 0x07 loop-control block was treated as an unconditional terminator.",
            "loop_expansion": "A repeated PSound export is playback behavior, not evidence that the source stream should be lengthened.",
        },
        "anchors": anchors,
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
    parser.add_argument("--pcm-identity")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    comparison_path = Path(args.comparison_json).expanduser().resolve()
    rows = _load_json(comparison_path)
    if not isinstance(rows, list):
        raise ValueError(f"Comparison JSON must contain a list: {comparison_path}")
    pcm_payload = None
    if args.pcm_identity:
        pcm_payload = _load_json(Path(args.pcm_identity).expanduser().resolve())
    output = Path(args.output).expanduser().resolve() if args.output else comparison_path.parent
    payload = audit([dict(row) for row in rows if isinstance(row, dict)], pcm_payload)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "psound_fragmenter_raw_span_audit.json"
    csv_path = output / "psound_fragmenter_raw_span_anchors.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, payload["anchors"])

    print("Raw-span audit:")
    print(f"  Monotonic raw-span anchors: {payload['raw_span_anchor_count']}")
    print(f"  Coverage of PSound catalog: {payload['raw_span_anchor_coverage_of_psound']:.2%}")
    print(f"  Payload relations: {payload['payload_relation_counts']}")
    print(f"  Final Fragmenter/PSound index offset: {payload['final_index_offset']}")
    print(f"  PSound loop-expansion candidates: {len(payload['psound_loop_expansion_candidates'])}")
    print(f"  Audit JSON: {json_path}")
    print(f"  Anchor CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

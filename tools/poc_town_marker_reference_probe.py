#!/usr/bin/env python3
"""Probe DMY/shop marker table references inside one town.bin gzip member.

Read-only diagnostic: parses padded concatenated gzip members, decompresses only the
selected member(s), finds marker-name table entries, and searches nearby/reference
encodings that may point at records containing transform data.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import string
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

# Import the established padded gzip member parser from the town member probe.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from poc_town_member_probe import GzipMember, parse_gzip_members  # noqa: E402

DEFAULT_MARKERS = [
    "DMY_gate", "DMY_merchant1", "DMY_merchant2", "DMY_merchant3",
    "DMY_merchant4", "DMY_merchant5", "DMY_merchant6", "LGT_shop01",
    "LGT_shop02", "LGT_shop03", "LGT_shop04", "LGT_shop05", "CCSFchgate",
]
PRINTABLE = set(bytes(string.printable, "ascii")) - {0x0b, 0x0c}
RESOURCE_NAME_PREFIXES = ("TEX_", "MAT_", "MDL_", "OBJ_", "DMY_", "ANM_", "LGT_")
RESOURCE_NAME_PREFIX_BYTES = tuple(p.encode("ascii") for p in RESOURCE_NAME_PREFIXES)
HEADER_SIGNATURES = (b"CCSF",)
PRINTABLE_RUN_MIN_LEN = 32
PRINTABLE_RUN_MIN_RATIO = 0.85


@dataclass
class MarkerHit:
    name: str
    offset: int | None
    record_start: int | None
    inferred_index: int | None
    stride: int | None
    dmy_table_start: int | None
    prev_names: list[dict]
    next_names: list[dict]


@dataclass(frozen=True)
class RefPatternConfig:
    strict: bool = False
    include_low_indexes: bool = False
    exact_offset_only: bool = False
    dmy_table_start: int | None = None
    section_start: int | None = None


def is_aligned_reference(offset: int, ref_type: str) -> bool:
    """Return whether a reference hit is naturally aligned for its width."""
    if "_u16_" in ref_type:
        return offset % 2 == 0
    if "_u32_" in ref_type:
        return offset % 4 == 0
    return True


def find_all(blob: bytes, needle: bytes) -> list[int]:
    out = []
    pos = 0
    while True:
        hit = blob.find(needle, pos)
        if hit < 0:
            return out
        out.append(hit)
        pos = hit + 1


def c_string_at(blob: bytes, offset: int, limit: int = 64) -> str | None:
    if offset < 0 or offset >= len(blob):
        return None
    end = blob.find(b"\x00", offset, min(len(blob), offset + limit))
    if end < 0 or end == offset:
        return None
    raw = blob[offset:end]
    if all((0x20 <= b <= 0x7e) for b in raw):
        return raw.decode("ascii", "replace")
    return None


def detect_marker_name_table(blob: bytes, marker_offsets: dict[str, int | None]) -> dict | None:
    """Infer a fixed-stride marker-name table from known marker string offsets.

    Marker names in observed town members are stored as NUL-terminated ASCII
    strings at the start of fixed-width records.  Three adjacent observed names
    such as offsets 8300, 8332, and 8364 therefore imply a 32-byte table.
    """
    present = sorted((off, name) for name, off in marker_offsets.items() if off is not None)
    if len(present) < 2:
        return None

    diffs = [b[0] - a[0] for a, b in zip(present, present[1:]) if 16 <= b[0] - a[0] <= 128]
    if not diffs:
        return None

    # Prefer the observed 32-byte marker-name record size when present; otherwise
    # use the most common plausible spacing between known marker strings.
    stride = 32 if 32 in diffs else max(sorted(set(diffs)), key=diffs.count)
    if stride <= 0:
        return None

    table_start = min(off - ((off - present[0][0]) % stride) for off, _name in present)
    entries = []
    for off, name in present:
        record_start = off - ((off - table_start) % stride)
        entries.append({
            "name": name,
            "offset": off,
            "record_start": record_start,
            "index": (record_start - table_start) // stride,
        })

    table_end = max(entry["record_start"] for entry in entries) + stride
    if not (0 <= table_start < table_end <= len(blob)):
        return None

    return {
        "start": table_start,
        "end": table_end,
        "stride": stride,
        "entry_count": ((table_end - table_start) // stride),
        "names_found_count": len(entries),
        "names_found": entries,
    }


def ascii_prefixed_strings(blob: bytes, prefixes: tuple[bytes, ...] = RESOURCE_NAME_PREFIX_BYTES) -> list[dict]:
    """Return NUL-terminated printable strings that begin with a resource prefix."""
    hits = []
    seen = set()
    for prefix in prefixes:
        pos = 0
        while True:
            off = blob.find(prefix, pos)
            if off < 0:
                break
            pos = off + 1
            if off in seen:
                continue
            name = c_string_at(blob, off, limit=96)
            if not name or not name.startswith(RESOURCE_NAME_PREFIXES):
                continue
            seen.add(off)
            hits.append({"offset": off, "name": name, "prefix": name[:4]})
    return sorted(hits, key=lambda h: h["offset"])


def detect_resource_table_ranges(blob: bytes) -> list[dict]:
    """Infer likely resource/name tables from clustered prefixed ASCII names.

    Resource tables in these town members commonly appear as NUL-terminated
    ASCII identifiers either packed closely together or at the start of
    fixed-size records.  This heuristic groups nearby strings, then annotates
    groups that have repeated spacing as fixed-stride candidates.
    """
    hits = ascii_prefixed_strings(blob)
    if len(hits) < 2:
        return []

    ranges = []
    cluster: list[dict] = []

    def flush_cluster() -> None:
        if len(cluster) < 2:
            return
        offsets = [h["offset"] for h in cluster]
        diffs = [b - a for a, b in zip(offsets, offsets[1:])]
        plausible_diffs = [d for d in diffs if 4 <= d <= 256]
        common_stride = None
        fixed_stride_hits = 0
        if plausible_diffs:
            common_stride = max(sorted(set(plausible_diffs)), key=plausible_diffs.count)
            fixed_stride_hits = sum(1 for d in plausible_diffs if d == common_stride)
        starts = [h["offset"] for h in cluster]
        ends = [h["offset"] + len(h["name"]) + 1 for h in cluster]
        start = min(starts)
        end = max(ends)
        if common_stride and fixed_stride_hits >= max(1, len(cluster) - 2):
            # Expand end to cover the full final fixed-size entry rather than
            # only the visible string bytes.
            end = max(end, offsets[-1] + common_stride)
        ranges.append({
            "start": start,
            "end": min(end, len(blob)),
            "kind": "resource_name_table",
            "reason": "clustered NUL-terminated resource/name identifiers",
            "stride": common_stride if fixed_stride_hits >= 2 else None,
            "entry_count": len(cluster),
            "prefixes": sorted({h["prefix"] for h in cluster}),
            "strings": cluster.copy(),
            "confidence": "high" if len(cluster) >= 4 or fixed_stride_hits >= 2 else "medium",
        })

    for hit in hits:
        if not cluster:
            cluster = [hit]
            continue
        prev = cluster[-1]
        gap = hit["offset"] - prev["offset"]
        # Keep tightly packed names and common fixed-record spacings together.
        if gap <= 256:
            cluster.append(hit)
        else:
            flush_cluster()
            cluster = [hit]
    flush_cluster()

    # Merge overlapping/adjacent candidate ranges.
    merged: list[dict] = []
    for rng in sorted(ranges, key=lambda r: r["start"]):
        if merged and rng["start"] <= merged[-1]["end"] + 64:
            prev = merged[-1]
            prev["end"] = max(prev["end"], rng["end"])
            prev["entry_count"] += rng["entry_count"]
            prev["prefixes"] = sorted(set(prev["prefixes"]) | set(rng["prefixes"]))
            prev["strings"].extend(rng["strings"])
            if prev.get("stride") != rng.get("stride"):
                prev["stride"] = None
            if prev["confidence"] != "high":
                prev["confidence"] = rng["confidence"]
        else:
            merged.append(rng)
    return merged


def make_range(start: int, end: int, kind: str, reason: str, blob_len: int, **extra: object) -> dict:
    """Create the generic range model used for skipped/low-score areas."""
    return {
        "start": max(0, start),
        "end": min(end, blob_len),
        "kind": kind,
        "reason": reason,
        **extra,
    }


def detect_header_ranges(blob: bytes, scan_limit: int = 512) -> list[dict]:
    """Detect distinctive format/header signatures near the decompressed member start."""
    ranges = []
    limit = min(len(blob), scan_limit)
    for sig in HEADER_SIGNATURES:
        pos = blob.find(sig, 0, limit)
        if pos < 0:
            continue
        ranges.append(make_range(
            max(0, pos - 16),
            min(len(blob), pos + 128),
            "header",
            f"distinctive header signature {sig.decode('ascii', 'replace')!r} near member start",
            len(blob),
            signature=sig.decode("ascii", "replace"),
            signature_offset=pos,
            confidence="high" if pos < 128 else "medium",
        ))
    return ranges


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    return sum(1 for b in data if b in PRINTABLE or b == 0) / len(data)


def printable_run_features(data: bytes) -> dict:
    nul_count = data.count(0)
    slash_count = data.count(ord("/")) + data.count(ord("\\"))
    underscore_count = data.count(ord("_"))
    dot_count = data.count(ord("."))
    alpha_count = sum(1 for b in data if 65 <= b <= 90 or 97 <= b <= 122)
    return {
        "nul_count": nul_count,
        "slash_count": slash_count,
        "underscore_count": underscore_count,
        "dot_count": dot_count,
        "alpha_count": alpha_count,
        "sample": data[:96].decode("ascii", "replace").replace("\x00", "\\0"),
    }


def detect_printable_string_ranges(blob: bytes) -> list[dict]:
    """Find long mostly-printable ASCII regions that look path/name-table-like."""
    ranges = []
    start: int | None = None
    for i, b in enumerate(blob):
        is_printish = b in PRINTABLE or b == 0
        if is_printish and start is None:
            start = i
        elif not is_printish and start is not None:
            if i - start >= PRINTABLE_RUN_MIN_LEN:
                run = blob[start:i]
                ratio = printable_ratio(run)
                features = printable_run_features(run)
                path_like = features["slash_count"] > 0 or features["dot_count"] > 1
                name_table_like = features["nul_count"] >= 2 and (features["underscore_count"] > 0 or features["alpha_count"] >= 16)
                if ratio >= PRINTABLE_RUN_MIN_RATIO and (path_like or name_table_like):
                    reason = "long mostly-printable ASCII run"
                    if path_like:
                        reason += " with path-like separators/extensions"
                    if name_table_like:
                        reason += " with NUL-separated name-table-like strings"
                    ranges.append(make_range(start, i, "printable_string_region", reason, len(blob), confidence="medium", **features))
            start = None
    if start is not None and len(blob) - start >= PRINTABLE_RUN_MIN_LEN:
        run = blob[start:]
        ratio = printable_ratio(run)
        features = printable_run_features(run)
        path_like = features["slash_count"] > 0 or features["dot_count"] > 1
        name_table_like = features["nul_count"] >= 2 and (features["underscore_count"] > 0 or features["alpha_count"] >= 16)
        if ratio >= PRINTABLE_RUN_MIN_RATIO and (path_like or name_table_like):
            ranges.append(make_range(start, len(blob), "printable_string_region", "long mostly-printable ASCII run at EOF", len(blob), confidence="medium", **features))
    return ranges


def offset_in_range(offset: int, range_info: dict | None) -> bool:
    return bool(range_info and range_info["start"] <= offset < range_info["end"])


def offset_in_ranges(offset: int, ranges: list[dict]) -> dict | None:
    for range_info in ranges:
        if range_info["start"] <= offset < range_info["end"]:
            return range_info
    return None


def compact_range_for_skip(name: str, range_info: dict) -> dict:
    return {
        "name": name,
        "start": range_info["start"],
        "end": range_info["end"],
        "kind": range_info.get("kind", name),
        "reason": range_info.get("reason", name),
        "stride": range_info.get("stride"),
        "entry_count": range_info.get("entry_count"),
        "confidence": range_info.get("confidence"),
        "prefixes": range_info.get("prefixes", []),
    }


def classify_reference_type(ref_type: str) -> str:
    """Classify accepted reference patterns into report-facing buckets."""
    if ref_type.startswith(("marker_offset_", "record_start_")) or "_relative_to_" in ref_type:
        return "exact_offset"
    if ref_type.startswith("table_index_"):
        return "strict_index"
    return "other"


def reference_outside_excluded_tables(ref: dict, ranges: dict) -> bool:
    """Return whether a reference sits outside all low-signal excluded ranges."""
    offset = ref["offset"]
    return not (
        offset_in_range(offset, ranges.get("marker_name_table_range"))
        or offset_in_ranges(offset, ranges.get("resource_name_table_ranges", []))
        or offset_in_ranges(offset, ranges.get("header_ranges", []))
        or offset_in_ranges(offset, ranges.get("printable_string_ranges", []))
    )


def reference_excluded_ranges(ref: dict, ranges: dict) -> list[dict]:
    """Return compact excluded range descriptors that contain a reference offset."""
    offset = ref["offset"]
    excluded = []
    marker_range = ranges.get("marker_name_table_range")
    if offset_in_range(offset, marker_range):
        excluded.append(compact_range_for_skip("marker_name_table_range", marker_range))
    resource_range = offset_in_ranges(offset, ranges.get("resource_name_table_ranges", []))
    if resource_range:
        excluded.append(compact_range_for_skip("resource_name_table_range", resource_range))
    header_range = offset_in_ranges(offset, ranges.get("header_ranges", []))
    if header_range:
        excluded.append(compact_range_for_skip("header_range", header_range))
    printable_range = offset_in_ranges(offset, ranges.get("printable_string_ranges", []))
    if printable_range:
        excluded.append(compact_range_for_skip("printable_string_region", printable_range))
    return excluded


def annotate_reference_candidate(ref: dict, ranges: dict, hit: MarkerHit | dict, comparison: dict | None = None) -> None:
    """Attach score and patch-candidate metadata to a found reference hit."""
    ref["reference_class"] = classify_reference_type(ref["type"])
    excluded_ranges = reference_excluded_ranges(ref, ranges)
    ref["excluded_ranges"] = excluded_ranges
    ref["outside_excluded_tables"] = not excluded_ranges
    ref["score"], ref["score_reasons"] = score_reference(ref, ranges, hit, comparison)
    ref["is_patch_candidate"] = ref["outside_excluded_tables"] and ref["score"] > 0
    ref["candidate_quality"] = "candidate" if ref["is_patch_candidate"] else "low"
    if excluded_ranges:
        ref["candidate_note"] = "suppressed/non-candidate: inside " + ", ".join(r["kind"] for r in excluded_ranges)
    elif ref["score"] <= 0:
        ref["candidate_note"] = "non-candidate: score is not positive"
    else:
        ref["candidate_note"] = "possible real reference: outside excluded ranges with positive score"

def marker_notes(marker: dict) -> list[str]:
    """Build compact marker summary notes for suppressed/skipped/reference context."""
    notes: list[str] = []
    suppressed = marker.get("suppressed_low_index_reference_count", 0)
    suppressed_patterns = marker.get("suppressed_low_index_reference_patterns", 0)
    if suppressed or suppressed_patterns:
        notes.append(f"suppressed_low_index_hits={suppressed} patterns={suppressed_patterns}")
    skipped_parts = []
    skipped_map = [
        ("unaligned", "skipped_unaligned_reference_count"),
        ("marker_table", "skipped_marker_name_table_reference_count"),
        ("resource_table", "skipped_resource_name_table_reference_count"),
        ("header", "skipped_header_reference_count"),
        ("printable", "skipped_printable_string_reference_count"),
    ]
    for label, key in skipped_map:
        count = marker.get(key, 0)
        if count:
            skipped_parts.append(f"{label}={count}")
    if skipped_parts:
        notes.append("skipped_ranges:" + ",".join(skipped_parts))
    refs = marker.get("references", [])
    candidate_count = sum(1 for r in refs if r.get("is_patch_candidate"))
    non_candidate_count = len(refs) - candidate_count
    if candidate_count:
        notes.append(f"possible_real_refs={candidate_count}")
    else:
        notes.append("no_possible_real_refs")
    if non_candidate_count:
        notes.append(f"non_candidate_refs={non_candidate_count}")
    return notes


def score_reference(
    ref: dict,
    ranges: dict,
    hit: MarkerHit | dict,
    comparison: dict | None = None,
) -> tuple[int, list[str]]:
    """Score a candidate marker reference and explain the ranking signals.

    Higher scores are intended to put candidate references in binary/structural
    regions ahead of noisy hits in string/name/header tables or tiny inferred
    indexes.  The score is a ranking heuristic only; aggregate counts still
    report all accepted references.
    """
    score = 0
    reasons: list[str] = []
    offset = ref["offset"]
    ref_type = ref["type"]

    marker_name_table_range = ranges.get("marker_name_table_range")
    resource_name_table_ranges = ranges.get("resource_name_table_ranges", [])
    header_ranges = ranges.get("header_ranges", [])
    printable_string_ranges = ranges.get("printable_string_ranges", [])

    inside_marker_table = offset_in_range(offset, marker_name_table_range)
    inside_resource_table = bool(offset_in_ranges(offset, resource_name_table_ranges))
    inside_header = bool(offset_in_ranges(offset, header_ranges))
    inside_printable = bool(offset_in_ranges(offset, printable_string_ranges))
    inside_low_signal_table = inside_marker_table or inside_resource_table or inside_header or inside_printable

    if inside_low_signal_table:
        score -= 40
        kinds = []
        if inside_marker_table:
            kinds.append("marker-name table")
        if inside_resource_table:
            kinds.append("resource/name table")
        if inside_header:
            kinds.append("header")
        if inside_printable:
            kinds.append("printable string region")
        reasons.append("inside " + "/".join(kinds))
    else:
        score += 20
        reasons.append("outside string/name/resource/header tables")

    if is_aligned_reference(offset, ref_type):
        score += 12
        reasons.append("naturally aligned")
    else:
        score -= 18
        reasons.append("unaligned")

    triples = ref.get("plausible_float32_triples", [])
    if triples:
        score += min(30, 10 + len(triples) * 2)
        reasons.append(f"{len(triples)} plausible float32 triple(s) nearby")
    else:
        score -= 15
        reasons.append("no plausible binary float32 triples nearby")

    if ref_type.startswith("marker_offset_") or ref_type.startswith("record_start_"):
        score += 18
        reasons.append("direct marker_offset/record_start target")

    inferred_index = hit.get("inferred_index") if isinstance(hit, dict) else hit.inferred_index
    if ref_type.startswith("table_index_") and inferred_index is not None and 0 <= inferred_index <= 5:
        score -= 25
        reasons.append("low inferred table index")

    comparison_refs = (comparison or {}).get("references", [])
    if comparison_refs:
        same_type_refs = [r for r in comparison_refs if r.get("type") == ref_type]
        structural_refs = [r for r in comparison_refs if r.get("plausible_float32_triples")]
        if same_type_refs and structural_refs:
            score += 15
            reasons.append("comparable structural reference appears in compare-other-member")
        elif same_type_refs:
            score += 8
            reasons.append("same reference type appears in compare-other-member")

    return score, reasons



def infer_stride(blob: bytes, marker_offsets: dict[str, int | None], marker: str) -> MarkerHit:
    off = marker_offsets.get(marker)
    if off is None:
        return MarkerHit(marker, None, None, None, None, None, [], [])
    present = sorted((o, n) for n, o in marker_offsets.items() if o is not None)
    prevs = [{"name": n, "offset": o} for o, n in present if o < off][-3:]
    nexts = [{"name": n, "offset": o} for o, n in present if o > off][:3]
    diffs = [b[0] - a[0] for a, b in zip(present, present[1:]) if 16 <= b[0] - a[0] <= 64]
    stride = max(set(diffs), key=diffs.count) if diffs else 32
    # Prefer observed 32-ish fixed string records; align the table start to first known name.
    table_start = present[0][0] if present else off
    record_start = off - ((off - table_start) % stride) if stride else off
    inferred_index = (record_start - table_start) // stride if stride else None
    return MarkerHit(marker, off, record_start, inferred_index, stride, table_start, prevs, nexts)


def hexdump(data: bytes, base: int) -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if b in PRINTABLE and b not in b"\r\n\t" else "." for b in chunk)
        lines.append(f"{base+i:08x}  {hx:<47}  {asc}")
    return "\n".join(lines)


def printable_block(data: bytes) -> str:
    return "".join(chr(b) if b in PRINTABLE else "." for b in data)


def float_triples(blob: bytes, center: int, radius: int = 128) -> list[dict]:
    out = []
    start = max(0, center - radius) & ~3
    end = min(len(blob) - 12, center + radius)
    for pos in range(start, end + 1, 4):
        vals = struct.unpack_from("<fff", blob, pos)
        if not all(math.isfinite(v) for v in vals):
            continue
        if all(abs(v) < 1e-6 for v in vals):
            continue
        if all(abs(v) < 100000.0 for v in vals) and any(abs(v) >= 0.001 for v in vals):
            out.append({"offset": pos, "values": [round(v, 6) for v in vals]})
    return out[:24]


def u32_patterns(name: str, value: int) -> list[tuple[str, bytes]]:
    if not 0 <= value <= 0xffffffff:
        return []
    return [(f"{name}_u32_le", struct.pack("<I", value)), (f"{name}_u32_be", struct.pack(">I", value))]


def ref_patterns(
    hit: MarkerHit,
    exact_offset_only: bool,
    dmy_table_start: int | None = None,
    section_start: int | None = None,
    config: RefPatternConfig | None = None,
) -> tuple[list[tuple[str, bytes]], list[tuple[str, bytes]]]:
    pats: list[tuple[str, bytes]] = []
    suppressed_low_index_patterns: list[tuple[str, bytes]] = []
    if hit.offset is not None:
        pats += u32_patterns("marker_offset", hit.offset)
    if hit.record_start is not None:
        pats += u32_patterns("record_start", hit.record_start)

    # Exact-offset-only mode intentionally emits no table_index_* probes.
    if exact_offset_only:
        base = dmy_table_start if dmy_table_start is not None else hit.dmy_table_start
        if base is not None and hit.record_start is not None:
            pats += u32_patterns("record_start_relative_to_dmy_table", hit.record_start - base)
        if section_start is not None and hit.record_start is not None:
            pats += u32_patterns("record_start_relative_to_section", hit.record_start - section_start)
        return pats, suppressed_low_index_patterns

    if hit.inferred_index is not None and 0 <= hit.inferred_index <= 0xffffffff:
        idx = hit.inferred_index
        index_pats = []
        if idx <= 0xffff:
            index_pats += [("table_index_u16_le", struct.pack("<H", idx)), ("table_index_u16_be", struct.pack(">H", idx))]
        index_pats += [("table_index_u32_le", struct.pack("<I", idx)), ("table_index_u32_be", struct.pack(">I", idx))]
        if config and config.strict and idx < 16 and not config.include_low_indexes:
            suppressed_low_index_patterns = index_pats
        else:
            pats += index_pats
    return pats, suppressed_low_index_patterns


def analyze_member(member: GzipMember, marker_names: list[str], config: RefPatternConfig) -> dict:
    blob = member.decompressed
    marker_offsets = {}
    for name in marker_names:
        offsets = find_all(blob, name.encode("ascii"))
        marker_offsets[name] = offsets[0] if offsets else None
    marker_name_table_range = detect_marker_name_table(blob, marker_offsets)
    if marker_name_table_range:
        marker_name_table_range["kind"] = "marker_name_table"
        marker_name_table_range["reason"] = "fixed-stride marker-name records inferred from known marker offsets"
    resource_name_table_ranges = detect_resource_table_ranges(blob)
    header_ranges = detect_header_ranges(blob)
    printable_string_ranges = detect_printable_string_ranges(blob)
    generic_skipped_ranges = []
    if marker_name_table_range:
        generic_skipped_ranges.append(compact_range_for_skip("marker_name_table_range", marker_name_table_range))
    generic_skipped_ranges += [compact_range_for_skip("resource_name_table_range", r) for r in resource_name_table_ranges]
    generic_skipped_ranges += [compact_range_for_skip("header_range", r) for r in header_ranges]
    generic_skipped_ranges += [compact_range_for_skip("printable_string_region", r) for r in printable_string_ranges]
    hits = [infer_stride(blob, marker_offsets, name) for name in marker_names]
    markers = []
    for hit in hits:
        refs = []
        patterns, suppressed_low_index_patterns = ref_patterns(hit, config.exact_offset_only, config.dmy_table_start, config.section_start, config)
        suppressed_low_index_reference_count = 0
        unaligned_reference_count = 0
        marker_name_table_reference_count = 0
        resource_name_table_reference_count = 0
        header_reference_count = 0
        printable_string_reference_count = 0
        for _typ, pat in suppressed_low_index_patterns:
            suppressed_low_index_reference_count += sum(
                1
                for off in find_all(blob, pat)
                if off != hit.offset and not offset_in_range(off, marker_name_table_range)
                and not offset_in_ranges(off, resource_name_table_ranges)
                and not offset_in_ranges(off, header_ranges)
                and not offset_in_ranges(off, printable_string_ranges)
            )
        for typ, pat in patterns:
            for off in find_all(blob, pat):
                if off == hit.offset:  # skip the marker string bytes themselves for tiny index patterns etc.
                    continue
                if offset_in_range(off, marker_name_table_range):
                    marker_name_table_reference_count += 1
                if offset_in_ranges(off, resource_name_table_ranges):
                    resource_name_table_reference_count += 1
                if offset_in_ranges(off, header_ranges):
                    header_reference_count += 1
                if offset_in_ranges(off, printable_string_ranges):
                    printable_string_reference_count += 1
                if config.strict and not is_aligned_reference(off, typ):
                    unaligned_reference_count += 1
                    continue
                lo, hi = max(0, off - 128), min(len(blob), off + len(pat) + 128)
                refs.append({
                    "offset": off,
                    "type": typ,
                    "pattern_hex": pat.hex(),
                    "hex_context": hexdump(blob[lo:hi], lo),
                    "printable_context": printable_block(blob[lo:hi]),
                    "plausible_float32_triples": float_triples(blob, off),
                })
        score_ranges = {
            "marker_name_table_range": marker_name_table_range,
            "resource_name_table_ranges": resource_name_table_ranges,
            "header_ranges": header_ranges,
            "printable_string_ranges": printable_string_ranges,
        }
        for ref in refs:
            annotate_reference_candidate(ref, score_ranges, hit)
        refs.sort(key=lambda r: (not r["is_patch_candidate"], -r["score"], r["offset"], r["type"]))
        exact_offset_reference_count = sum(1 for r in refs if r.get("reference_class") == "exact_offset")
        strict_index_reference_count = sum(1 for r in refs if r.get("reference_class") == "strict_index")
        markers.append({
            "marker": hit.name,
            "marker_offset": hit.offset,
            "record_start": hit.record_start,
            "inferred_index": hit.inferred_index,
            "inferred_stride": hit.stride,
            "dmy_table_start": config.dmy_table_start if config.dmy_table_start is not None else hit.dmy_table_start,
            "section_start": config.section_start,
            "marker_name_table_range": marker_name_table_range,
            "resource_name_table_ranges": resource_name_table_ranges,
            "header_ranges": header_ranges,
            "printable_string_ranges": printable_string_ranges,
            "preceding_markers": hit.prev_names,
            "following_markers": hit.next_names,
            "references": refs,
            "reference_count": len(refs),
            "exact_offset_reference_count": exact_offset_reference_count,
            "strict_index_reference_count": strict_index_reference_count,
            "suppressed_low_index_reference_patterns": len(suppressed_low_index_patterns),
            "suppressed_low_index_reference_count": suppressed_low_index_reference_count,
            "skipped_unaligned_reference_count": unaligned_reference_count,
            "skipped_marker_name_table_reference_count": marker_name_table_reference_count,
            "skipped_resource_name_table_reference_count": resource_name_table_reference_count,
            "skipped_header_reference_count": header_reference_count,
            "skipped_printable_string_reference_count": printable_string_reference_count,
        })
    suppressed_low_index_references = sum(m["suppressed_low_index_reference_count"] for m in markers)
    skipped_unaligned_references = sum(m["skipped_unaligned_reference_count"] for m in markers)
    skipped_marker_name_table_references = sum(m["skipped_marker_name_table_reference_count"] for m in markers)
    skipped_resource_name_table_references = sum(m["skipped_resource_name_table_reference_count"] for m in markers)
    skipped_header_references = sum(m["skipped_header_reference_count"] for m in markers)
    skipped_printable_string_references = sum(m["skipped_printable_string_reference_count"] for m in markers)
    return {
        "member": member.index,
        "member_decompressed_size": len(blob),
        "strict": config.strict,
        "include_low_indexes": config.include_low_indexes,
        "exact_offset_only": config.exact_offset_only,
        "dmy_table_start": config.dmy_table_start,
        "section_start": config.section_start,
        "marker_name_table_range": marker_name_table_range,
        "resource_name_table_ranges": resource_name_table_ranges,
        "header_ranges": header_ranges,
        "printable_string_ranges": printable_string_ranges,
        "exact_offset_references": sum(m["exact_offset_reference_count"] for m in markers),
        "strict_index_references": sum(m["strict_index_reference_count"] for m in markers),
        "suppressed_low_index_references": suppressed_low_index_references,
        "skipped_unaligned_references": skipped_unaligned_references,
        "skipped_marker_name_table_references": skipped_marker_name_table_references,
        "skipped_resource_name_table_references": skipped_resource_name_table_references,
        "skipped_header_references": skipped_header_references,
        "skipped_printable_string_references": skipped_printable_string_references,
        "skipped_ranges": generic_skipped_ranges,
        "markers": markers,
    }


def add_comparison(report: dict, other: dict) -> None:
    other_by_name = {m["marker"]: m for m in other["markers"]}
    for m in report["markers"]:
        om = other_by_name.get(m["marker"])
        if not om:
            continue
        m["compare_other_member"] = {
            "member": other["member"],
            "marker_offset": om["marker_offset"],
            "inferred_index": om["inferred_index"],
            "reference_count": om["reference_count"],
            "exact_offset_reference_count": om.get("exact_offset_reference_count", 0),
            "strict_index_reference_count": om.get("strict_index_reference_count", 0),
            "strongest_reference_offsets": [r["offset"] for r in om["references"][:8]],
            "references": [
                {
                    "offset": r["offset"],
                    "type": r["type"],
                    "score": r.get("score"),
                    "plausible_float32_triples": r.get("plausible_float32_triples", []),
                }
                for r in om["references"][:20]
            ],
        }


def rescore_report_references(report: dict) -> None:
    ranges = {
        "marker_name_table_range": report.get("marker_name_table_range"),
        "resource_name_table_ranges": report.get("resource_name_table_ranges", []),
        "header_ranges": report.get("header_ranges", []),
        "printable_string_ranges": report.get("printable_string_ranges", []),
    }
    for marker in report["markers"]:
        comparison = marker.get("compare_other_member")
        for ref in marker["references"]:
            annotate_reference_candidate(ref, ranges, marker, comparison)
        marker["references"].sort(key=lambda r: (not r["is_patch_candidate"], -r["score"], r["offset"], r["type"]))


def summary_rows(markers: list[dict]) -> list[list[str]]:
    rows = []
    for m in markers:
        refs = [r for r in m["references"] if r.get("is_patch_candidate")]
        best_scored_refs = ",".join(
            f"{r['offset']}:{r['type']}:{r.get('reference_class', classify_reference_type(r['type']))}({r.get('score', 0)})"
            for r in refs[:8]
        )
        rows.append([
            m["marker"],
            str(m["marker_offset"]),
            str(m["inferred_index"]),
            str(m.get("exact_offset_reference_count", 0)),
            str(m.get("strict_index_reference_count", 0)),
            best_scored_refs,
            "; ".join(marker_notes(m)),
        ])
    return rows


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(c)) for w, c in zip(widths, row)]
    fmt = " | ".join("{:<" + str(w) + "}" for w in widths)
    return "\n".join([fmt.format(*headers), "-+-".join("-" * w for w in widths), *[fmt.format(*r) for r in rows]])


def write_reports(report: dict, out: Path) -> None:
    json_path = out if out.suffix.lower() == ".json" else out.with_suffix(".json")
    txt_path = json_path.with_suffix(".txt")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "Town marker reference probe",
        f"Input: {report['input']}",
        f"Member: {report['selected']['member']}",
        f"Top detailed references per marker in TXT: {report.get('top', 20)}",
        f"Strict mode: {report['selected'].get('strict', False)}",
        f"Exact-offset-only mode: {report['selected'].get('exact_offset_only', False)}",
        f"Exact offset references: {report['selected'].get('exact_offset_references', 0)}",
        f"Strict index references: {report['selected'].get('strict_index_references', 0)}",
    ]
    suppressed = report["selected"].get("suppressed_low_index_references", 0)
    if report["selected"].get("strict", False) and suppressed:
        lines.append(f"Suppressed {suppressed} low-index false-positive references.")
    skipped_unaligned = report["selected"].get("skipped_unaligned_references", 0)
    if report["selected"].get("strict", False) and skipped_unaligned:
        lines.append(f"Skipped {skipped_unaligned} unaligned references.")
    skipped_marker_table = report["selected"].get("skipped_marker_name_table_references", 0)
    if skipped_marker_table:
        lines.append(f"Labeled {skipped_marker_table} marker-name table hits as suppressed/non-candidate.")
    skipped_resource_table = report["selected"].get("skipped_resource_name_table_references", 0)
    if skipped_resource_table:
        lines.append(f"Labeled {skipped_resource_table} resource/name table hits as suppressed/non-candidate.")
    skipped_header = report["selected"].get("skipped_header_references", 0)
    if skipped_header:
        lines.append(f"Labeled {skipped_header} CCSF/header-area hits as suppressed/non-candidate.")
    skipped_printable = report["selected"].get("skipped_printable_string_references", 0)
    if skipped_printable:
        lines.append(f"Labeled {skipped_printable} printable string/path region hits as suppressed/non-candidate.")

    marker_name_table_range = report["selected"].get("marker_name_table_range")
    lines += ["", "=== Marker-name tables ===", "marker_name_table_range"]
    if marker_name_table_range:
        lines += [
            f"start={marker_name_table_range['start']} end={marker_name_table_range['end']} stride={marker_name_table_range['stride']} entry_count={marker_name_table_range['entry_count']} names_found_count={marker_name_table_range['names_found_count']}",
            "names_found=" + ", ".join(f"{e['index']}:{e['name']}@{e['offset']}" for e in marker_name_table_range["names_found"]),
        ]
    else:
        lines.append("None")

    resource_name_table_ranges = report["selected"].get("resource_name_table_ranges", [])
    lines += ["", "=== Resource/name tables ==="]
    if resource_name_table_ranges:
        for i, r in enumerate(resource_name_table_ranges):
            preview = ", ".join(f"{s['name']}@{s['offset']}" for s in r.get("strings", [])[:8])
            if len(r.get("strings", [])) > 8:
                preview += ", ..."
            lines += [
                f"range[{i}]: start={r['start']} end={r['end']} stride={r.get('stride')} entry_count={r.get('entry_count')} confidence={r.get('confidence')} prefixes={','.join(r.get('prefixes', []))}",
                f"strings={preview}",
            ]
    else:
        lines.append("None")

    header_ranges = report["selected"].get("header_ranges", [])
    lines += ["", "Detected header ranges"]
    if header_ranges:
        lines += [f"range[{i}]: start={r['start']} end={r['end']} kind={r.get('kind')} signature={r.get('signature')} signature_offset={r.get('signature_offset')} reason={r.get('reason')}" for i, r in enumerate(header_ranges)]
    else:
        lines.append("None")

    printable_string_ranges = report["selected"].get("printable_string_ranges", [])
    lines += ["", "Printable string regions"]
    if printable_string_ranges:
        lines += [f"range[{i}]: start={r['start']} end={r['end']} kind={r.get('kind')} confidence={r.get('confidence')} reason={r.get('reason')} sample={r.get('sample')}" for i, r in enumerate(printable_string_ranges)]
    else:
        lines.append("None")

    lines += ["", "Suppressed/low-score table ranges"]
    skipped_ranges = report["selected"].get("skipped_ranges", [])
    if skipped_ranges:
        lines += [f"{r['name']}: start={r['start']} end={r['end']} kind={r.get('kind')} reason={r.get('reason')} stride={r.get('stride')} entry_count={r.get('entry_count')} confidence={r.get('confidence')} prefixes={','.join(r.get('prefixes', []))}" for r in skipped_ranges]
    else:
        lines.append("None")

    lines += ["", "=== Possible real references (candidate hits only) ===", "Summary", table(["marker", "marker_offset", "inferred_index", "exact_offset_ref_count", "strict_index_ref_count", "best_candidate_refs", "notes"], summary_rows(report["selected"]["markers"])), ""]
    top = report.get("top", 20)
    for m in report["selected"]["markers"]:
        lines += [f"## {m['marker']}", f"marker_offset={m['marker_offset']} record_start={m['record_start']} inferred_index={m['inferred_index']} stride={m['inferred_stride']} dmy_table_start={m.get('dmy_table_start')} section_start={m.get('section_start')}", f"exact_offset_count={m.get('exact_offset_reference_count', 0)} strict_index_count={m.get('strict_index_reference_count', 0)}", f"notes={'; '.join(marker_notes(m))}", f"preceding={m['preceding_markers']} following={m['following_markers']}"]
        for r in m["references"][:top]:
            label = "possible real reference" if r.get("is_patch_candidate") else "suppressed/non-candidate"
            excluded = ",".join(e.get("kind", "excluded") for e in r.get("excluded_ranges", [])) or "none"
            lines += [f"### {label} offset={r['offset']} type={r['type']} class={r.get('reference_class', classify_reference_type(r['type']))} score={r.get('score', 0)} candidate_quality={r.get('candidate_quality')} is_patch_candidate={r.get('is_patch_candidate')} excluded_ranges={excluded}", f"candidate note: {r.get('candidate_note')}", f"score reasons: {', '.join(r.get('score_reasons', []))}", "hex:", r["hex_context"], "text:", r["printable_context"], f"float32 triples: {r['plausible_float32_triples']}"]
        if len(m["references"]) > top:
            lines.append(f"... omitted {len(m['references']) - top} lower-scored reference(s) from TXT details; JSON retains aggregate counts and full reference data.")
        lines.append("")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Find likely references to town marker-name table entries in one gzip member.")
    ap.add_argument("--input", required=True, type=Path, help="Path to town.bin")
    ap.add_argument("--member", required=True, type=int, help="Zero-based gzip member index to decompress and probe")
    ap.add_argument("--markers", default=",".join(DEFAULT_MARKERS), help="Comma-separated marker names")
    ap.add_argument("--out", required=True, type=Path, help="Output report path/stem; .json and .txt are written")
    ap.add_argument("--compare-other-member", type=int, help="Also decompress/probe another member and include comparison summary")
    ap.add_argument("--strict", action="store_true", help="Suppress noisy low table-index reference patterns and prioritize stronger references")
    ap.add_argument("--include-low-indexes", action="store_true", help="In strict mode, still include table_index_* patterns for inferred indexes below 16")
    ap.add_argument("--exact-offset-only", action="store_true", help="Only probe exact marker/record offsets and optional relative offsets; skip all table_index_* patterns")
    ap.add_argument("--dmy-table-start", type=lambda x: int(x, 0), help="Optional DMY table base offset for relative exact-offset probes (decimal or 0x-prefixed)")
    ap.add_argument("--section-start", type=lambda x: int(x, 0), help="Optional selected-section base offset for relative exact-offset probes (decimal or 0x-prefixed)")
    ap.add_argument("--top", type=int, default=20, help="Number of top-scored detailed references per marker to include in TXT output")
    args = ap.parse_args()

    marker_names = [m.strip() for m in args.markers.split(",") if m.strip()]
    raw = args.input.read_bytes()
    members = parse_gzip_members(raw)
    needed = [args.member] + ([] if args.compare_other_member is None else [args.compare_other_member])
    for idx in needed:
        if idx < 0 or idx >= len(members):
            raise SystemExit(f"member {idx} out of range; found {len(members)} gzip member(s)")
    config = RefPatternConfig(strict=args.strict, include_low_indexes=args.include_low_indexes, exact_offset_only=args.exact_offset_only, dmy_table_start=args.dmy_table_start, section_start=args.section_start)
    selected = analyze_member(members[args.member], marker_names, config)
    if args.top < 0:
        raise SystemExit("--top must be non-negative")
    report = {"input": str(args.input), "selected": selected, "top": args.top}
    if args.compare_other_member is not None:
        other = analyze_member(members[args.compare_other_member], marker_names, config)
        report["compare_other_member"] = other
        add_comparison(selected, other)
        rescore_report_references(selected)
    write_reports(report, args.out)


if __name__ == "__main__":
    main()

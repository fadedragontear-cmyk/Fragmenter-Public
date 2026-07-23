#!/usr/bin/env python3
"""Map SNDDATA-style SCEI resource containers.

The format appears in little-endian dumps with both readable tags (``SCEIVers``)
and byte-reversed tags (``IECSsreV``).  This parser treats a validated Vers
block as the boundary for one resource group and then walks child sections by
using each section's own uint32 little-endian block size at ``+0x08``.  Invalid
or truncated headers are preserved as evidence instead of being promoted to
independent resources.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import audio_decoder
    import scei_midi
except ImportError:  # pragma: no cover - script execution from repo root
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import audio_decoder
    import scei_midi

VERS_TAGS = (b"SCEIVers", b"IECSsreV")
SECTION_TAGS = {
    b"SCEIVers": "SCEIVers",
    b"IECSsreV": "SCEIVers",
    b"SCEIHead": "SCEIHead",
    b"IECSdaeH": "SCEIHead",
    b"SCEIVagi": "SCEIVagi",
    b"IECSigaV": "SCEIVagi",
    b"SCEISmpl": "SCEISmpl",
    b"IECSlpmS": "SCEISmpl",
    b"SCEISset": "SCEISset",
    b"IECStesS": "SCEISset",
    b"SCEIProg": "SCEIProg",
    b"IECSgorP": "SCEIProg",
    b"SCEISequ": "SCEISequ",
    b"IECSuqeS": "SCEISequ",
    b"SCEIMidi": "SCEIMidi",
    b"IECSidiM": "SCEIMidi",
}
KNOWN_TAGS = tuple(SECTION_TAGS)
KNOWN_CHILD_TAGS = tuple(tag for tag in SECTION_TAGS if tag not in VERS_TAGS)
RESOURCE_TYPE_NAMES = {1: "sample_program", 2: "sequence"}
REPORT_JSON = Path("workspace/reports/snddata_container_map.json")
REPORT_TXT = Path("workspace/reports/snddata_container_map.txt")
SNDDATA_SAMPLE_ROOT = Path("workspace/media_pipeline/decoded/audio/snddata/samples")


def _u32le(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _u16le(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _ascii(raw: bytes) -> str:
    return raw.decode("ascii", "replace")


@dataclass(slots=True)
class Section:
    signature: bytes
    offset: int
    block_size: int | None
    unknown_0c: int | None = None
    resource_type: int | None = None
    valid: bool = False
    truncated: bool = False
    end_offset: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def resource_type_name_candidate(self) -> str | None:
        return RESOURCE_TYPE_NAMES.get(self.resource_type)

    def as_dict(self) -> dict[str, Any]:
        return {
            "signature": _ascii(self.signature),
            "signature_hex": self.signature.hex(),
            "tag": SECTION_TAGS.get(self.signature, "unknown"),
            "offset": self.offset,
            "block_size": self.block_size,
            "unknown_0c": self.unknown_0c,
            "resource_type": self.resource_type,
            "resource_type_name_candidate": RESOURCE_TYPE_NAMES.get(self.resource_type),
            "valid": self.valid,
            "truncated": self.truncated,
            "end_offset": self.end_offset,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class ResourceGroup:
    source: str
    offset: int
    vers: Section
    sections: list[Section]
    classification: str
    valid: bool
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "offset": self.offset,
            "end_offset": self.vers.end_offset,
            "block_size": self.vers.block_size,
            "valid": self.valid,
            "classification": self.classification,
            "resource_type": self.vers.resource_type,
            "resource_type_name_candidate": RESOURCE_TYPE_NAMES.get(self.vers.resource_type),
            "vers": self.vers.as_dict(),
            "sections": [s.as_dict() for s in self.sections],
            "evidence": self.evidence,
        }


def _hex(raw: bytes) -> str:
    return raw.hex()


def _field_value(data: bytes, section_off: int, rel_off: int, size: int, value: int) -> dict[str, Any]:
    abs_off = section_off + rel_off
    return {
        "absolute_offset": abs_off,
        "section_relative_offset": rel_off,
        "raw_value": _hex(data[abs_off:abs_off + size]),
        "value": value,
    }


def _parse_scei_prog_slot(data: bytes, section_off: int, slot_abs: int, slot_size: int, slot_index: int) -> dict[str, Any]:
    """Parse one SCEIProg slot, exposing only fields present in ``slot_size``."""
    slot_rel = slot_abs - section_off
    raw_bytes = _hex(data[slot_abs:slot_abs + slot_size])
    slot: dict[str, Any] = {
        "index": slot_index,
        "absolute_offset": slot_abs,
        "section_relative_offset": slot_rel,
        "raw_bytes": raw_bytes,
        "unknown_bytes": raw_bytes,
    }

    def present(size_needed: int) -> bool:
        return slot_size >= size_needed

    if present(0x02):
        slot["sample_id"] = _field_value(data, section_off, slot_rel + 0x00, 2, _u16le(data, slot_abs + 0x00))
    if present(0x04):
        raw = data[slot_abs + 0x02:slot_abs + 0x04]
        slot["unknown_02"] = _field_value(data, section_off, slot_rel + 0x02, 2, _hex(raw))
    if present(0x05):
        slot["parameter_04"] = _field_value(data, section_off, slot_rel + 0x04, 1, data[slot_abs + 0x04])
    if present(0x06):
        slot["slot_id"] = _field_value(data, section_off, slot_rel + 0x05, 1, data[slot_abs + 0x05])
    if present(0x10):
        raw = data[slot_abs + 0x06:slot_abs + 0x10]
        slot["unknown_06_0f"] = _field_value(data, section_off, slot_rel + 0x06, 0x0A, _hex(raw))
    if present(0x11):
        slot["volume"] = _field_value(data, section_off, slot_rel + 0x10, 1, data[slot_abs + 0x10])
    if present(0x12):
        slot["pan"] = _field_value(data, section_off, slot_rel + 0x11, 1, data[slot_abs + 0x11])
    if present(0x13):
        slot["tempo_pitch"] = _field_value(data, section_off, slot_rel + 0x12, 1, data[slot_abs + 0x12])
    if present(0x14):
        slot["parameter_13"] = _field_value(data, section_off, slot_rel + 0x13, 1, data[slot_abs + 0x13])
    if slot_size > 0x14:
        trailing_size = slot_size - 0x14
        raw = data[slot_abs + 0x14:slot_abs + slot_size]
        slot["trailing_unknown_bytes"] = _field_value(data, section_off, slot_rel + 0x14, trailing_size, _hex(raw))

    return slot


def _parse_scei_prog(data: bytes, sec: Section) -> dict[str, Any]:
    """Parse the observed SCEIProg offset table and program records conservatively."""
    assert sec.block_size is not None
    section_off = sec.offset
    section_end = section_off + sec.block_size
    stored_value = _u32le(data, section_off + 0x0C)
    item_count = stored_value + 1
    table_off = section_off + 0x10
    table_size = item_count * 4
    result: dict[str, Any] = {
        "block_size": _field_value(data, section_off, 0x08, 4, sec.block_size),
        "stored_item_max_index": _field_value(data, section_off, 0x0C, 4, stored_value),
        "item_count_candidate": item_count,
        "offset_table": {"section_relative_offset": 0x10, "entry_size": 4, "valid": False, "entries": []},
        "programs": [],
    }
    if item_count <= 0 or table_off + table_size > section_end:
        result["offset_table"].update({
            "error": "offset_table_extends_past_section",
            "end_offset": table_off + table_size,
        })
        return result

    raw_offsets = [_u32le(data, table_off + i * 4) for i in range(item_count)]
    rel_valid = all(0x10 <= value < sec.block_size for value in raw_offsets)
    abs_valid = all(section_off <= value < section_end for value in raw_offsets)
    if rel_valid:
        base = "section_relative"
        rel_offsets = raw_offsets
    elif abs_valid:
        base = "absolute_file"
        rel_offsets = [value - section_off for value in raw_offsets]
    else:
        result["offset_table"].update({
            "error": "program_offsets_out_of_bounds",
            "raw_offsets": raw_offsets,
        })
        return result

    result["offset_table"].update({"valid": True, "base": base})
    for i, (raw, rel) in enumerate(zip(raw_offsets, rel_offsets)):
        result["offset_table"]["entries"].append(
            _field_value(data, section_off, 0x10 + i * 4, 4, raw)
            | {"resolved_section_relative_offset": rel, "resolved_absolute_offset": section_off + rel}
        )

    for index, rel in enumerate(rel_offsets):
        abs_off = section_off + rel
        next_rel_candidates = [candidate for candidate in rel_offsets if candidate > rel]
        program_end = section_off + (min(next_rel_candidates) if next_rel_candidates else sec.block_size)
        program: dict[str, Any] = {"index": index, "absolute_offset": abs_off, "section_relative_offset": rel}
        if abs_off + 0x0A > section_end:
            program["error"] = "program_header_truncated"
            result["programs"].append(program)
            continue
        body_offset = _u32le(data, abs_off)
        slot_count = data[abs_off + 0x04]
        slot_size = data[abs_off + 0x05]
        program.update({
            "body_offset": _field_value(data, section_off, rel, 4, body_offset),
            "slot_count": _field_value(data, section_off, rel + 0x04, 1, slot_count),
            "slot_size": _field_value(data, section_off, rel + 0x05, 1, slot_size),
            "master_volume": _field_value(data, section_off, rel + 0x06, 1, data[abs_off + 0x06]),
            "parameter_07": _field_value(data, section_off, rel + 0x07, 1, data[abs_off + 0x07]),
            "tempo_pitch": _field_value(data, section_off, rel + 0x08, 1, data[abs_off + 0x08]),
            "parameter_09": _field_value(data, section_off, rel + 0x09, 1, data[abs_off + 0x09]),
        })
        slots_start = abs_off + body_offset if 0 <= body_offset < program_end - abs_off else abs_off + 0x10
        header_unknown_end = min(slots_start, program_end)
        program["unknown_header_bytes"] = _hex(data[abs_off + 0x0A:header_unknown_end])
        slots = []
        if slot_size and slots_start + slot_count * slot_size <= section_end and slots_start + slot_count * slot_size <= program_end:
            for slot_index in range(slot_count):
                slot_abs = slots_start + slot_index * slot_size
                slots.append(_parse_scei_prog_slot(data, section_off, slot_abs, slot_size, slot_index))
        else:
            program["slot_error"] = "slots_extend_past_program_or_section"
        program["slots"] = slots
        pad_abs = slots_start + slot_count * slot_size
        observed_pad = data[pad_abs:pad_abs + 8] if pad_abs + 8 <= section_end else b""
        program["padding_after_slots"] = {
            "absolute_offset": pad_abs,
            "section_relative_offset": pad_abs - section_off,
            "size": len(observed_pad),
            "raw_bytes": _hex(observed_pad),
            "is_ff_8": observed_pad == b"\xff" * 8,
        }
        result["programs"].append(program)
    return result



def _u32le_or_none(data: bytes, off: int) -> int | None:
    return _u32le(data, off) if 0 <= off and off + 4 <= len(data) else None


def _u16le_or_none(data: bytes, off: int) -> int | None:
    return _u16le(data, off) if 0 <= off and off + 2 <= len(data) else None


def _all_known_tag_occurrences(data: bytes) -> list[tuple[int, bytes]]:
    occurrences: list[tuple[int, bytes]] = []
    for tag in KNOWN_TAGS:
        start = 0
        while True:
            hit = data.find(tag, start)
            if hit < 0:
                break
            occurrences.append((hit, tag))
            start = hit + 1
    return sorted(set(occurrences))


def build_known_tag_evidence(data: bytes) -> list[dict[str, Any]]:
    """Return file-wide evidence for every known SNDDATA tag occurrence."""
    vers_offsets = locate_vers_candidates(data)
    occurrences = _all_known_tag_occurrences(data)
    evidence: list[dict[str, Any]] = []
    for index, (hit, tag) in enumerate(occurrences):
        preceding = [candidate for candidate in vers_offsets if candidate <= hit]
        nearest_vers = preceding[-1] if preceding else None
        next_known = occurrences[index + 1] if index + 1 < len(occurrences) else None
        size_field_offset = hit + 0x08
        raw_size = _u32le_or_none(data, size_field_offset)
        evidence.append({
            "absolute_offset": hit,
            "tag": _ascii(tag),
            "tag_hex": tag.hex(),
            "human_name": SECTION_TAGS[tag],
            "nearest_preceding_vers_offset": nearest_vers,
            "distance_from_vers": hit - nearest_vers if nearest_vers is not None else None,
            "raw_size_field_at_tag_plus_0x08": raw_size,
            "raw_size_field_at_tag_plus_0x08_hex": (
                _hex(data[size_field_offset:size_field_offset + 4])
                if size_field_offset + 4 <= len(data)
                else None
            ),
            "next_known_tag": SECTION_TAGS[next_known[1]] if next_known else None,
            "next_known_tag_signature": _ascii(next_known[1]) if next_known else None,
            "next_known_tag_offset": next_known[0] if next_known else None,
            "distance_to_next_known_tag": next_known[0] - hit if next_known else None,
        })
    return evidence


def _next_8_byte_aligned_signatures(data: bytes, vers_off: int, start: int, limit: int, max_hits: int = 16) -> list[dict[str, Any]]:
    signatures: list[dict[str, Any]] = []
    off = ((start + 7) // 8) * 8
    while off + 8 <= limit and len(signatures) < max_hits:
        sig = data[off:off + 8]
        if sig in SECTION_TAGS:
            signatures.append({
                "absolute_offset": off,
                "distance_from_vers": off - vers_off,
                "signature": _ascii(sig),
                "signature_hex": sig.hex(),
                "human_name": SECTION_TAGS[sig],
            })
        off += 8
    return signatures


def build_vers_evidence(data: bytes, max_resources: int = 20) -> list[dict[str, Any]]:
    """Build bounded evidence rows for the first Vers candidates in a SNDDATA blob."""
    vers_offsets = locate_vers_candidates(data)
    known_tag_evidence = build_known_tag_evidence(data)
    rows: list[dict[str, Any]] = []
    for resource_index, off in enumerate(vers_offsets[:max_resources]):
        next_vers = next((candidate for candidate in vers_offsets if candidate > off), None)
        bound = next_vers if next_vers is not None else len(data)
        next_reversed_vers = data.find(b"IECSsreV", off + 1)
        rows.append({
            "resource_index": resource_index,
            "vers_offset": off,
            "first_64_bytes_hex": _hex(data[off:off + 64]),
            "vers_block_size_field_le": _u32le_or_none(data, off + 0x08),
            "vers_block_size_field_hex": (
                _hex(data[off + 0x08:off + 0x0C]) if off + 0x0C <= len(data) else None
            ),
            "type_field_at_0x0e": _u16le_or_none(data, off + 0x0E),
            "type_field_at_0x0e_hex": (
                _hex(data[off + 0x0E:off + 0x10]) if off + 0x10 <= len(data) else None
            ),
            "bytes_after_candidate_header_hex": _hex(data[off + 0x10:off + 0x50]),
            "next_8_byte_aligned_signatures": _next_8_byte_aligned_signatures(data, off, off + 0x10, bound),
            "distance_to_next_IECSsreV": (
                next_reversed_vers - off if next_reversed_vers >= 0 else None
            ),
            "bounded_region_end_offset": bound,
            "known_tags_in_bounded_region": [
                item for item in known_tag_evidence
                if off <= item["absolute_offset"] < bound
            ],
        })
    return rows

def locate_vers_candidates(data: bytes) -> list[int]:
    hits: list[int] = []
    for tag in VERS_TAGS:
        start = 0
        while True:
            off = data.find(tag, start)
            if off < 0:
                break
            hits.append(off)
            start = off + 1
    return sorted(set(hits))


def _find_known_tag_occurrences(data: bytes, vers_offsets: list[int], vers_off: int, limit: int) -> list[dict[str, Any]]:
    """Collect compact evidence for known child tags inside one Vers-bounded region."""
    occurrences: list[tuple[int, bytes]] = []
    for tag in KNOWN_CHILD_TAGS:
        start = vers_off
        while True:
            hit = data.find(tag, start, limit)
            if hit < 0:
                break
            occurrences.append((hit, tag))
            start = hit + 1
    occurrences.sort()
    evidence: list[dict[str, Any]] = []
    for index, (hit, tag) in enumerate(occurrences):
        preceding = [candidate for candidate in vers_offsets if candidate <= hit]
        nearest_vers = preceding[-1] if preceding else None
        next_known = occurrences[index + 1] if index + 1 < len(occurrences) else None
        size_field_offset = hit + 0x08
        raw_size = _u32le(data, size_field_offset) if size_field_offset + 4 <= len(data) else None
        evidence.append({
            "tag": SECTION_TAGS[tag],
            "signature": _ascii(tag),
            "signature_hex": tag.hex(),
            "absolute_offset": hit,
            "nearest_preceding_vers_offset": nearest_vers,
            "distance_from_vers": hit - nearest_vers if nearest_vers is not None else None,
            "raw_size_field_offset": size_field_offset,
            "raw_size_field": raw_size,
            "raw_size_field_hex": (
                _hex(data[size_field_offset:size_field_offset + 4])
                if size_field_offset + 4 <= len(data)
                else None
            ),
            "next_known_tag": SECTION_TAGS[next_known[1]] if next_known else None,
            "next_known_tag_offset": next_known[0] if next_known else None,
            "distance_to_next_known_tag": next_known[0] - hit if next_known else None,
        })
    return evidence


def _walk_evidence_sections(data: bytes, occurrences: list[dict[str, Any]], limit: int) -> list[Section]:
    """Derive child sections from repeated tag/size patterns found by anchor scan.

    Known child tags may appear after padding or metadata, so this intentionally
    does not require the first child to start at Vers+0x10.  Each candidate is
    validated independently against the next known tag and the Vers-bounded
    resource limit because observed size fields do not all necessarily share
    identical semantics.
    """
    sections: list[Section] = []
    for occurrence in occurrences:
        off = occurrence["absolute_offset"]
        next_off = occurrence.get("next_known_tag_offset") or limit
        if off + 0x10 > limit:
            sec = _parse_section(data, off, limit)
            sections.append(sec)
            break
        size = occurrence.get("raw_size_field")
        if not isinstance(size, int) or size < 0x10:
            sec = _parse_section(data, off, limit)
            sections.append(sec)
            break
        end = off + size
        occurrence["candidate_end_offset"] = end
        occurrence["candidate_end_valid"] = end <= limit and end <= next_off
        if not occurrence["candidate_end_valid"]:
            occurrence["candidate_end_error"] = "extends_past_next_known_tag_or_resource_bound"
            sec = _parse_section(data, off, limit)
            sections.append(sec)
            break
        sec = _parse_section(data, off, limit)
        sec.evidence["anchor_scan"] = {
            "distance_from_vers": occurrence.get("distance_from_vers"),
            "next_known_tag": occurrence.get("next_known_tag"),
            "distance_to_next_known_tag": occurrence.get("distance_to_next_known_tag"),
        }
        if sec.valid:
            sections.append(sec)
    return sections


def _parse_section(data: bytes, off: int, limit: int) -> Section:
    sig = data[off:off + 8]
    sec = Section(sig, off, None)
    if off + 0x10 > len(data) or off + 0x10 > limit:
        sec.truncated = True
        sec.evidence["error"] = "truncated_header"
        sec.end_offset = min(len(data), limit)
        return sec
    size = _u32le(data, off + 0x08)
    sec.block_size = size
    sec.unknown_0c = _u16le(data, off + 0x0C)
    sec.resource_type = _u16le(data, off + 0x0E)
    end = off + size
    sec.end_offset = end
    if size < 0x10:
        sec.evidence["error"] = "block_size_smaller_than_header"
    elif end > len(data):
        sec.truncated = True
        sec.evidence["error"] = "block_extends_past_file"
        sec.evidence["available_bytes"] = max(0, len(data) - off)
    elif end > limit:
        sec.truncated = True
        sec.evidence["error"] = "block_extends_past_parent_bound"
        sec.evidence["parent_limit"] = limit
    elif sig not in SECTION_TAGS:
        sec.evidence["error"] = "unrecognized_signature"
    else:
        sec.valid = True
        tag = SECTION_TAGS.get(sig)
        if tag == "SCEIProg":
            sec.evidence["scei_prog"] = _parse_scei_prog(data, sec)
        elif tag == "SCEIMidi":
            section_bytes = data[off:end]
            sec.evidence["scei_midi"] = scei_midi.parse_scei_midi(section_bytes, f"section@0x{off:X}")
    return sec


def walk_sections(data: bytes, start: int, limit: int) -> list[Section]:
    sections: list[Section] = []
    root = _parse_section(data, start, len(data))
    sections.append(root)
    if not root.valid:
        return sections
    off = start + 0x10
    while off < limit:
        if off + 8 > len(data):
            break
        if data[off:off + 8] not in SECTION_TAGS:
            break
        sec = _parse_section(data, off, limit)
        sections.append(sec)
        if not sec.valid or not sec.block_size:
            break
        off += sec.block_size
    return sections


def _classify(sections: list[Section], rtype: int | None) -> str:
    tags = [SECTION_TAGS.get(s.signature) for s in sections if s.valid]
    if rtype == 1 and {"SCEIHead", "SCEIVagi"}.issubset(tags) and ("SCEISmpl" in tags or "SCEIProg" in tags or "SCEISset" in tags):
        return "sample_program_resource"
    if rtype == 2 and ("SCEISequ" in tags or "SCEIMidi" in tags):
        return "sequence_resource"
    return RESOURCE_TYPE_NAMES.get(rtype, "unknown") or "unknown"


def parse_blob(data: bytes, source: str = "<memory>") -> list[ResourceGroup]:
    groups: list[ResourceGroup] = []
    vers_offsets = locate_vers_candidates(data)
    consumed: list[tuple[int, int]] = []
    for off in vers_offsets:
        if any(start < off < end for start, end in consumed):
            continue
        vers_unbounded = _parse_section(data, off, len(data))
        containing_end = (
            vers_unbounded.end_offset
            if vers_unbounded.valid and vers_unbounded.end_offset is not None
            else None
        )
        next_hits = [h for h in vers_offsets if h > off and (containing_end is None or h >= containing_end)]
        # Evidence scanning is bounded by the next non-contained Vers anchor, not
        # by child placement assumptions such as Vers+0x10.
        limit = next_hits[0] if next_hits else len(data)
        vers = _parse_section(data, off, limit)
        vers.evidence["bounded_to"] = limit
        known_tag_occurrences = _find_known_tag_occurrences(data, vers_offsets, off, limit)
        evidence_sections = _walk_evidence_sections(data, known_tag_occurrences, limit)

        if evidence_sections:
            sections = [vers, *evidence_sections]
            walk_source = "known_tag_anchor_scan"
        else:
            # Compatibility path for the original strict contiguous walker.  This
            # can preserve legacy output, but a lone Vers hit is not treated as
            # evidence that the resource was successfully understood.
            sections = walk_sections(data, off, limit)
            walk_source = "strict_contiguous_fallback"

        understood = any(s.valid and s.offset != off for s in sections)
        classification = _classify(sections, vers.resource_type) if understood else "unknown"
        groups.append(ResourceGroup(
            source,
            off,
            vers,
            sections,
            classification,
            understood,
            {
                "walk_limit": limit,
                "walk_source": walk_source,
                "known_tag_occurrences": known_tag_occurrences,
                "understood_from_child_sections": understood,
            },
        ))
        if vers_unbounded.valid and vers_unbounded.end_offset is not None:
            consumed.append((off, vers_unbounded.end_offset))
    return groups


def _is_zero_block(block: bytes) -> bool:
    return len(block) == 16 and block == b"\x00" * 16


def _is_terminator_block(block: bytes) -> bool:
    return len(block) == 16 and (block[1] == 0x07 or block == b"\x00\x07" + b"\x77" * 14)


def _plausible_rate(value: int) -> bool:
    return 4000 <= value <= 96000


def _section_payload(sec: Section) -> tuple[int, int]:
    start = sec.offset + 0x10
    end = sec.end_offset if sec.end_offset is not None else start
    return start, max(start, end)


def _parse_vagi_sample_entries(data: bytes, group: ResourceGroup, smpl_size: int) -> list[dict[str, Any]]:
    """Parse conservative Vagi entries as structured sample boundaries.

    The SNDDATA variant is still being mapped, so this accepts only entries
    whose offsets/sizes fit inside SCEISmpl.  Supported layouts are a count
    followed by 12-byte ``offset,size,rate`` records or 8-byte ``offset,size``
    records.  This deliberately takes priority over separator scans.
    """
    vagi = next((s for s in group.sections if SECTION_TAGS.get(s.signature) == "SCEIVagi" and s.valid), None)
    if vagi is None:
        return []
    start, end = _section_payload(vagi)
    payload = data[start:end]
    if len(payload) < 4:
        return []
    count = _u32le(payload, 0)
    if count <= 0 or count > 4096:
        return []
    for stride in (12, 8):
        if 4 + count * stride > len(payload):
            continue
        entries: list[dict[str, Any]] = []
        ok = True
        for i in range(count):
            off = 4 + i * stride
            sample_off = _u32le(payload, off)
            sample_size = _u32le(payload, off + 4)
            rate = _u32le(payload, off + 8) if stride >= 12 else None
            if sample_size <= 0 or sample_off + sample_size > smpl_size:
                ok = False
                break
            entries.append({
                "sample_id": i,
                "source_offset": sample_off,
                "payload_size": sample_size,
                "sample_rate": rate if isinstance(rate, int) and _plausible_rate(rate) else None,
                "sample_rate_field_evidence": {
                    "source": "SCEIVagi",
                    "absolute_offset": start + off + 8 if stride >= 12 else None,
                    "raw_value": payload[off + 8:off + 12].hex() if stride >= 12 else None,
                    "value": rate,
                } if stride >= 12 else None,
                "boundary_source": "structured_vagi_smpl_offsets_sizes",
            })
        if ok:
            return entries
    return []


def _validated_metadata_sample_entries(group: ResourceGroup, smpl_size: int) -> list[dict[str, Any]]:
    """Accept caller-supplied sample metadata only after bounds validation."""
    raw_entries = group.evidence.get("sample_metadata") or group.evidence.get("samples") or []
    if not isinstance(raw_entries, list):
        return []
    entries: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            return []
        sample_off = raw.get("source_offset", raw.get("offset"))
        sample_size = raw.get("payload_size", raw.get("size"))
        rate = raw.get("sample_rate", raw.get("rate"))
        if not isinstance(sample_off, int) or not isinstance(sample_size, int):
            return []
        if sample_off < 0 or sample_size <= 0 or sample_off + sample_size > smpl_size:
            return []
        entries.append({
            "sample_id": raw.get("sample_id", i),
            "source_offset": sample_off,
            "payload_size": sample_size,
            "sample_rate": rate if isinstance(rate, int) and _plausible_rate(rate) else None,
            "sample_rate_field_evidence": raw.get("sample_rate_field_evidence"),
            "boundary_source": "validated_sample_metadata",
        })
    return entries


def _trim_sample_payload(sample: bytes) -> tuple[int, bytes, list[str]]:
    evidence: list[str] = []
    skip = 0
    if len(sample) >= 16 and _is_zero_block(sample[:16]):
        skip = 16
        evidence.append("leading_zero_block")
    end = len(sample)
    for pos in range(skip, len(sample) - 15, 16):
        block = sample[pos:pos + 16]
        if _is_terminator_block(block):
            end = pos
            evidence.append("terminator_block" if block[1] == 0x07 else "007777_separator")
            break
    return skip, sample[skip:end], evidence


def _separator_samples(smpl: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    cursor = 0
    for pos in range(0, len(smpl) - 15, 16):
        block = smpl[pos:pos + 16]
        if block == b"\x00\x07" + b"\x77" * 14:
            if pos > cursor:
                entries.append({
                    "sample_id": len(entries),
                    "source_offset": cursor,
                    "payload_size": pos - cursor,
                    "sample_rate": None,
                    "sample_rate_field_evidence": None,
                    "boundary_source": "terminator_separator_evidence",
                })
            cursor = pos + 16
        elif _is_zero_block(block) and pos > cursor:
            entries.append({
                "sample_id": len(entries),
                "source_offset": cursor,
                "payload_size": pos - cursor,
                "sample_rate": None,
                "sample_rate_field_evidence": None,
                "boundary_source": "terminator_separator_evidence",
            })
            cursor = pos
    if cursor < len(smpl):
        entries.append({
            "sample_id": len(entries),
            "source_offset": cursor,
            "payload_size": len(smpl) - cursor,
            "sample_rate": None,
            "sample_rate_field_evidence": None,
            "boundary_source": "terminator_separator_evidence",
        })
    return entries


def _sentinel_samples(smpl: bytes) -> list[dict[str, Any]]:
    size = len(smpl) - (len(smpl) % 16)
    return [{
        "sample_id": 0,
        "source_offset": 0,
        "payload_size": size,
        "sample_rate": None,
        "sample_rate_field_evidence": None,
        "boundary_source": "experimental_sentinel_scan",
    }] if size else []


def extract_samples_for_group(data: bytes, group: ResourceGroup, sample_root: Path = SNDDATA_SAMPLE_ROOT, default_rate: int = 22050) -> list[dict[str, Any]]:
    smpl = next((s for s in group.sections if SECTION_TAGS.get(s.signature) == "SCEISmpl" and s.valid), None)
    if smpl is None:
        return []
    smpl_start, smpl_end = _section_payload(smpl)
    smpl_payload = data[smpl_start:smpl_end]
    entries = _parse_vagi_sample_entries(data, group, len(smpl_payload))
    if not entries:
        entries = _validated_metadata_sample_entries(group, len(smpl_payload))
    if not entries:
        entries = _separator_samples(smpl_payload)
    if not entries:
        entries = _sentinel_samples(smpl_payload)

    resource_id = len(str(group.offset)) and group.offset
    out_dir = sample_root / f"resource_{resource_id}"
    rows: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries):
        sample_id = int(entry.get("sample_id") if isinstance(entry.get("sample_id"), int) else idx)
        rel = int(entry["source_offset"])
        raw_size = int(entry["payload_size"])
        raw = smpl_payload[rel:rel + raw_size]
        skip, payload, boundary_evidence = _trim_sample_payload(raw)
        rate = int(entry.get("sample_rate") or default_rate)
        wav = out_dir / f"sample_{sample_id}_{rate}hz.wav"
        row: dict[str, Any] = {
            "resource_id": resource_id,
            "sample_id": sample_id,
            "source_offset": smpl_start + rel,
            "payload_offset": smpl_start + rel + skip,
            "payload_size": len(payload),
            "raw_source_size": raw_size,
            "sample_rate": rate,
            "sample_rate_field_evidence": entry.get("sample_rate_field_evidence"),
            "block_count": len(payload) // 16,
            "channels": 1,
            "channel_evidence": "mono_default_no_metadata_proves_otherwise",
            "boundary_source": entry.get("boundary_source"),
            "boundary_evidence": boundary_evidence,
            "decode_status": "pending",
            "output_path": str(wav),
            "metadata_path": str(wav.with_suffix(".json")),
            "errors": [],
        }
        result = audio_decoder.decode_ps_adpcm_to_wav(payload, wav, rate, 1)
        if result.get("errors"):
            row["decode_status"] = "failed_ps_adpcm_decode"
            row["errors"] = result["errors"]
        else:
            row.update({"decode_status": result.get("decode_status"), "sample_count": result.get("sample_count"), "duration_estimate": result.get("duration_estimate")})
        wav.with_suffix(".json").parent.mkdir(parents=True, exist_ok=True)
        wav.with_suffix(".json").write_text(json.dumps(row, indent=2), encoding="utf-8")
        rows.append(row)
    return rows


def extract_samples(data: bytes, groups: Iterable[ResourceGroup], sample_root: Path = SNDDATA_SAMPLE_ROOT, default_rate: int = 22050) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        rows.extend(extract_samples_for_group(data, group, sample_root, default_rate))
    return rows


def write_reports(
    groups: Iterable[ResourceGroup],
    json_path: Path = REPORT_JSON,
    txt_path: Path = REPORT_TXT,
    evidence_by_source: dict[str, dict[str, Any]] | None = None,
) -> None:
    rows = [g.as_dict() for g in groups]
    evidence_by_source = evidence_by_source or {}
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"resources": rows, "vers_evidence_by_source": evidence_by_source}, indent=2), encoding="utf-8")
    lines = ["SNDDATA container map", "=====================", ""]
    if evidence_by_source:
        lines.extend(["Vers evidence", "-------------"])
        for source, source_evidence in evidence_by_source.items():
            lines.append(f"{source}:")
            vers_rows = source_evidence.get("vers_candidates", [])
            lines.append(f"  vers_candidates_recorded={len(vers_rows)} known_tag_occurrences={len(source_evidence.get('known_tag_occurrences', []))}")
            for row in vers_rows:
                lines.append(
                    f"  - resource_index={row['resource_index']} vers_offset=0x{row['vers_offset']:X} "
                    f"size_field={row['vers_block_size_field_le']} type={row['type_field_at_0x0e']} "
                    f"distance_to_next_IECSsreV={row['distance_to_next_IECSsreV']} "
                    f"known_tags_in_bound={len(row['known_tags_in_bounded_region'])}"
                )
                if row["next_8_byte_aligned_signatures"]:
                    sigs = ", ".join(
                        f"{sig['human_name']}@0x{sig['absolute_offset']:X}"
                        for sig in row["next_8_byte_aligned_signatures"]
                    )
                    lines.append(f"    aligned_known_signatures: {sigs}")
        lines.append("")
    for g in rows:
        lines.append(f"{g['source']} @ 0x{g['offset']:X}: {g['classification']} size={g['vers']['block_size']} valid={g['valid']}")
        for s in g["sections"]:
            lines.append(f"  - 0x{s['offset']:X} {s['tag']} size={s['block_size']} valid={s['valid']} truncated={s['truncated']}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_paths(paths: Iterable[Path]) -> list[ResourceGroup]:
    groups: list[ResourceGroup] = []
    for path in paths:
        if path.is_file():
            groups.extend(parse_blob(path.read_bytes(), path.as_posix()))
    return groups


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", type=Path, help="Files to scan")
    ap.add_argument("--json", type=Path, default=REPORT_JSON)
    ap.add_argument("--txt", type=Path, default=REPORT_TXT)
    ap.add_argument("--extract-samples", action="store_true", help="Decode SCEISmpl PS ADPCM samples to WAV files")
    ap.add_argument("--sample-root", type=Path, default=SNDDATA_SAMPLE_ROOT)
    ap.add_argument("--default-rate", type=int, default=22050)
    ns = ap.parse_args(argv)
    groups: list[ResourceGroup] = []
    sample_rows: list[dict[str, Any]] = []
    evidence_by_source: dict[str, dict[str, Any]] = {}
    for path in ns.paths:
        if path.is_file():
            data = path.read_bytes()
            source = path.as_posix()
            path_groups = parse_blob(data, source)
            groups.extend(path_groups)
            evidence_by_source[source] = {
                "vers_candidates": build_vers_evidence(data),
                "known_tag_occurrences": build_known_tag_evidence(data),
            }
            if ns.extract_samples:
                sample_rows.extend(extract_samples(data, path_groups, ns.sample_root, ns.default_rate))
    write_reports(groups, ns.json, ns.txt, evidence_by_source)
    print(f"wrote {len(groups)} groups to {ns.json} and {ns.txt}")
    if ns.extract_samples:
        print(f"decoded {len(sample_rows)} SNDDATA sample rows under {ns.sample_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

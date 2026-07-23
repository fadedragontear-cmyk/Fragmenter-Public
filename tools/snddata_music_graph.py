#!/usr/bin/env python3
"""Build a conservative music relationship graph from parsed SNDDATA resources.

The graph only promotes relationships to confirmed edges when a parsed field
explicitly carries the relationship.  Ambiguous relationships are retained as
candidate edges with a confidence and reason instead of being forced into the
confirmed adjacency.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import snddata_parser

REPORT_JSON = Path("workspace/reports/snddata_music_graph.json")
REPORT_TXT = Path("workspace/reports/snddata_music_graph.txt")

NODE_TYPES = {
    "resource",
    "program",
    "program_slot",
    "sample",
    "sequence",
    "midi_resource",
    "midi_track",
    "midi_channel",
}


def _field_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _first_present(mapping: dict[str, Any], names: Iterable[str]) -> tuple[str, Any] | tuple[None, None]:
    for name in names:
        if name in mapping and _field_value(mapping[name]) is not None:
            return name, _field_value(mapping[name])
    return None, None


def _section_id(resource_id: str, tag: str, offset: int) -> str:
    return f"{resource_id}:{tag}@0x{offset:X}"


def _add_node(nodes: dict[str, dict[str, Any]], node_id: str, node_type: str, label: str, **attrs: Any) -> None:
    if node_type not in NODE_TYPES:
        raise ValueError(f"unknown node type {node_type!r}")
    nodes.setdefault(node_id, {"id": node_id, "type": node_type, "label": label, **attrs})


def _edge(source: str, target: str, rel: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"source": source, "target": target, "relationship": rel, "evidence": evidence}


def _candidate(source: str, target: str | None, rel: str, confidence: float, reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "relationship": rel,
        "confidence": confidence,
        "reason": reason,
        "evidence": evidence,
    }


def _sample_nodes_from_section(nodes: dict[str, dict[str, Any]], resource_id: str, section: dict[str, Any]) -> list[str]:
    evidence = section.get("evidence", {})
    parsed_samples = evidence.get("samples") or evidence.get("scei_smpl", {}).get("samples") or []
    sample_ids: list[str] = []
    if isinstance(parsed_samples, list) and parsed_samples:
        for i, sample in enumerate(parsed_samples):
            sample_index = _field_value(sample.get("index", i)) if isinstance(sample, dict) else i
            node_id = f"{resource_id}:sample:{sample_index}"
            _add_node(nodes, node_id, "sample", f"sample {sample_index}", resource=resource_id, parsed=sample)
            sample_ids.append(node_id)
    else:
        node_id = _section_id(resource_id, "sample", section["offset"])
        _add_node(nodes, node_id, "sample", "sample section", resource=resource_id, section=section)
        sample_ids.append(node_id)
    return sample_ids


def build_graph(groups: Iterable[Any]) -> dict[str, Any]:
    """Return a conservative graph for parser ResourceGroup objects or dicts."""
    rows = [g.as_dict() if hasattr(g, "as_dict") else g for g in groups]
    nodes: dict[str, dict[str, Any]] = {}
    confirmed_edges: list[dict[str, Any]] = []
    candidate_edges: list[dict[str, Any]] = []
    unknown_mappings: list[dict[str, Any]] = []

    for r_index, group in enumerate(rows):
        resource_id = f"resource:{r_index}:0x{group['offset']:X}"
        _add_node(nodes, resource_id, "resource", f"{group.get('source', '<memory>')} @ 0x{group['offset']:X}", parsed=group)

        samples: list[str] = []
        sequences: list[str] = []
        midis: list[str] = []
        for section in group.get("sections", []):
            tag = section.get("tag")
            if tag == "SCEISmpl":
                samples.extend(_sample_nodes_from_section(nodes, resource_id, section))
            elif tag == "SCEISequ":
                seq_id = _section_id(resource_id, "sequence", section["offset"])
                _add_node(nodes, seq_id, "sequence", "sequence", resource=resource_id, section=section)
                sequences.append(seq_id)
            elif tag == "SCEIMidi":
                evidence = section.get("evidence", {})
                parsed_midi = evidence.get("scei_midi")
                if not isinstance(parsed_midi, dict):
                    continue
                midi_id = _section_id(resource_id, "midi", section["offset"])
                _add_node(nodes, midi_id, "midi_resource", "MIDI resource", resource=resource_id, section=section, parsed=parsed_midi)
                midis.append(midi_id)

                events = parsed_midi.get("events") or []
                parsed_events = [event for event in events if isinstance(event, dict)]
                if parsed_events:
                    _add_node(nodes, f"{midi_id}:track:0", "midi_track", "midi track 0", resource=resource_id, parsed={"events": parsed_events})
                channels = sorted({event.get("channel") for event in parsed_events if event.get("channel") is not None})
                for idx in channels:
                    channel_events = [event for event in parsed_events if event.get("channel") == idx]
                    _add_node(nodes, f"{midi_id}:channel:{idx}", "midi_channel", f"midi channel {idx}", resource=resource_id, parsed={"channel": idx, "events": channel_events})

        for section in group.get("sections", []):
            if section.get("tag") != "SCEIProg":
                continue
            parsed = section.get("evidence", {}).get("scei_prog", {})
            for program in parsed.get("programs", []):
                p_index = program.get("index")
                program_id = f"{resource_id}:program:{p_index}"
                _add_node(nodes, program_id, "program", f"program {p_index}", resource=resource_id, parsed=program)
                for slot in program.get("slots", []):
                    s_index = slot.get("index")
                    slot_id = f"{program_id}:slot:{s_index}"
                    _add_node(nodes, slot_id, "program_slot", f"program {p_index} slot {s_index}", resource=resource_id, parsed=slot)
                    confirmed_edges.append(_edge(program_id, slot_id, "program_slot", {"fields": ["program.slots"], "program_index": p_index, "slot_index": s_index}))

                    field, sample_index = _first_present(slot, ("sample_index", "sample_id", "sample_number", "sample"))
                    if field is not None:
                        sample_id = f"{resource_id}:sample:{sample_index}"
                        if sample_id in samples:
                            confirmed_edges.append(_edge(slot_id, sample_id, "slot_sample", {"field": field, "value": sample_index}))
                        elif samples:
                            candidate_edges.append(_candidate(slot_id, None, "slot_sample", 0.5, "parsed sample reference field has no matching parsed sample node", {"field": field, "value": sample_index, "available_sample_nodes": samples, "slot_raw_bytes": slot.get("raw_bytes")}))
                        else:
                            unknown_mappings.append({"source": slot_id, "relationship": "slot_sample", "reason": "parsed sample reference field but no parsed samples available", "evidence": {"field": field, "value": sample_index, "slot_raw_bytes": slot.get("raw_bytes")}})
                    elif samples:
                        candidate_edges.append(_candidate(slot_id, None, "slot_sample", 0.25, "program slot bytes are parsed, but no parsed sample reference field is known", {"available_sample_nodes": samples, "slot_raw_bytes": slot.get("raw_bytes")}))
                    else:
                        unknown_mappings.append({"source": slot_id, "relationship": "slot_sample", "reason": "no parsed sample reference field and no parsed samples available", "evidence": {"slot_raw_bytes": slot.get("raw_bytes")}})

        for seq_id in sequences:
            if midis:
                for midi_id in midis:
                    confirmed_edges.append(_edge(seq_id, midi_id, "sequence_midi", {"fields": ["SCEISequ section", "SCEIMidi section"], "reason": "sequence and midi sections are parsed in the same resource"}))
            else:
                candidate_edges.append(_candidate(seq_id, None, "sequence_midi", 0.4, "sequence section parsed without an accompanying midi section", {}))

    return {"nodes": list(nodes.values()), "confirmed_edges": confirmed_edges, "candidate_edges": candidate_edges, "unknown_mappings": unknown_mappings}


def write_reports(graph: dict[str, Any], json_path: Path = REPORT_JSON, txt_path: Path = REPORT_TXT) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    lines = ["SNDDATA music graph", "===================", "", f"nodes: {len(graph['nodes'])}", f"confirmed_edges: {len(graph['confirmed_edges'])}", f"candidate_edges: {len(graph['candidate_edges'])}", f"unknown_mappings: {len(graph['unknown_mappings'])}", ""]
    for edge in graph["confirmed_edges"]:
        lines.append(f"CONFIRMED {edge['relationship']}: {edge['source']} -> {edge['target']}")
    for edge in graph["candidate_edges"]:
        lines.append(f"CANDIDATE {edge['relationship']} ({edge['confidence']:.2f}): {edge['source']} -> {edge['target']} because {edge['reason']}")
    for unknown in graph["unknown_mappings"]:
        lines.append(f"UNKNOWN {unknown['relationship']}: {unknown['source']} because {unknown['reason']}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", type=Path, help="SNDDATA/container files to scan")
    ap.add_argument("--json", type=Path, default=REPORT_JSON)
    ap.add_argument("--txt", type=Path, default=REPORT_TXT)
    ns = ap.parse_args(argv)
    graph = build_graph(snddata_parser.parse_paths(ns.paths))
    write_reports(graph, ns.json, ns.txt)
    print(f"wrote music graph to {ns.json} and {ns.txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

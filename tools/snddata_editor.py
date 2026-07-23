#!/usr/bin/env python3
"""Editable SNDDATA model layer for validated v1 program and slot fields."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import snddata_parser as sp

DEFAULT_EXPORT_PATH = Path("workspace/music_edits/snddata_modified.bin")
DEFAULT_MANIFEST_JSON = Path("workspace/reports/snddata_edit_manifest.json")
DEFAULT_MANIFEST_TXT = Path("workspace/reports/snddata_edit_manifest.txt")

PROGRAM_FIELDS: dict[str, int] = {
    "master_volume": 0x06,
    "parameter_07": 0x07,
    "tempo_pitch": 0x08,
    "parameter_09": 0x09,
}

SLOT_FIELDS: dict[str, int] = {
    "parameter_04": 0x04,
    "volume": 0x10,
    "pan": 0x11,
    "tempo_pitch": 0x12,
    "parameter_13": 0x13,
}


@dataclass(frozen=True, slots=True)
class EditableField:
    resource: int
    section: str
    program: int
    slot: int | None
    field: str
    absolute_offset: int
    original_raw_value: bytes

    def key(self) -> tuple[int, str, int, int | None, str]:
        return (self.resource, self.section, self.program, self.slot, self.field)

    def as_dict(self, current_raw_value: bytes | None = None) -> dict[str, Any]:
        row = {
            "resource": self.resource,
            "section": self.section,
            "program": self.program,
            "slot": self.slot,
            "field": self.field,
            "absolute_offset": self.absolute_offset,
            "original_raw_value": self.original_raw_value.hex(),
        }
        if current_raw_value is not None:
            row["current_raw_value"] = current_raw_value.hex()
        return row


@dataclass(frozen=True, slots=True)
class EditRecord:
    resource: int
    section: str
    program: int
    slot: int | None
    field: str
    absolute_offset: int
    old_raw_value: bytes
    new_raw_value: bytes

    @classmethod
    def from_field(cls, field: EditableField, old: bytes, new: bytes) -> "EditRecord":
        return cls(field.resource, field.section, field.program, field.slot, field.field, field.absolute_offset, old, new)

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "section": self.section,
            "program": self.program,
            "slot": self.slot,
            "field": self.field,
            "absolute_offset": self.absolute_offset,
            "old_raw_value": self.old_raw_value.hex(),
            "new_raw_value": self.new_raw_value.hex(),
        }


class SnddataEditor:
    """In-memory editor that only patches known validated one-byte SNDDATA fields."""

    def __init__(self, source_path: Path, data: bytes, groups: list[sp.ResourceGroup]):
        self.source_path = Path(source_path)
        self._original = bytes(data)
        self.groups = groups
        self.fields = self._discover_fields()
        self._values = {key: field.original_raw_value for key, field in self.fields.items()}
        self._undo: list[EditRecord] = []
        self._redo: list[EditRecord] = []

    @classmethod
    def from_file(cls, source_path: Path) -> "SnddataEditor":
        data = Path(source_path).read_bytes()
        return cls(Path(source_path), data, sp.parse_blob(data, Path(source_path).as_posix()))

    @property
    def edits(self) -> list[EditRecord]:
        return list(self._undo)

    def get_raw(self, resource: int, program: int, field: str, slot: int | None = None, section: str = "SCEIProg") -> bytes:
        editable = self._field(resource, section, program, slot, field)
        return self._values[editable.key()]

    def set_raw(self, resource: int, program: int, field: str, value: int | bytes, slot: int | None = None, section: str = "SCEIProg") -> EditRecord:
        editable = self._field(resource, section, program, slot, field)
        new = self._coerce_raw(value)
        key = editable.key()
        old = self._values[key]
        record = EditRecord.from_field(editable, old, new)
        if old != new:
            self._values[key] = new
            self._undo.append(record)
            self._redo.clear()
        return record

    def undo(self) -> EditRecord | None:
        if not self._undo:
            return None
        record = self._undo.pop()
        self._values[(record.resource, record.section, record.program, record.slot, record.field)] = record.old_raw_value
        self._redo.append(record)
        return record

    def redo(self) -> EditRecord | None:
        if not self._redo:
            return None
        record = self._redo.pop()
        self._values[(record.resource, record.section, record.program, record.slot, record.field)] = record.new_raw_value
        self._undo.append(record)
        return record

    def reset_selected(self, resource: int, program: int, field: str, slot: int | None = None, section: str = "SCEIProg") -> EditRecord:
        editable = self._field(resource, section, program, slot, field)
        return self.set_raw(resource, program, field, editable.original_raw_value, slot, section)

    def reset_all(self) -> None:
        for key, editable in self.fields.items():
            self._values[key] = editable.original_raw_value
        self._undo.clear()
        self._redo.clear()

    def export_patched(self, output_path: Path = DEFAULT_EXPORT_PATH, manifest_json: Path = DEFAULT_MANIFEST_JSON, manifest_txt: Path = DEFAULT_MANIFEST_TXT) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.source_path, output_path)
        patched = bytearray(output_path.read_bytes())
        applied: list[EditRecord] = []
        for key, editable in sorted(self.fields.items(), key=lambda item: item[1].absolute_offset):
            current = self._values[key]
            if current == editable.original_raw_value:
                continue
            off = editable.absolute_offset
            if patched[off:off + 1] != editable.original_raw_value:
                raise ValueError(f"original byte mismatch at 0x{off:X}")
            patched[off:off + 1] = current
            applied.append(EditRecord.from_field(editable, editable.original_raw_value, current))
        output_path.write_bytes(patched)
        if output_path.stat().st_size != len(self._original):
            raise ValueError("patched SNDDATA size changed")
        reparsed = sp.parse_blob(output_path.read_bytes(), output_path.as_posix())
        self._confirm_boundaries(reparsed)
        self.write_manifest(manifest_json, manifest_txt, output_path, applied, reparsed)
        return output_path

    def write_manifest(self, json_path: Path = DEFAULT_MANIFEST_JSON, txt_path: Path = DEFAULT_MANIFEST_TXT, output_path: Path | None = None, applied: list[EditRecord] | None = None, reparsed: list[sp.ResourceGroup] | None = None) -> None:
        applied = self._current_applied_records() if applied is None else applied
        json_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source_path": self.source_path.as_posix(),
            "output_path": output_path.as_posix() if output_path else None,
            "output_size": output_path.stat().st_size if output_path and output_path.exists() else None,
            "editable_field_count": len(self.fields),
            "applied_edit_count": len(applied),
            "section_boundaries_confirmed": reparsed is not None,
            "edits": [record.as_dict() for record in applied],
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        lines = ["SNDDATA edit manifest", "=====================", "", f"Source: {payload['source_path']}", f"Output: {payload['output_path']}", f"Applied edits: {len(applied)}"]
        for record in applied:
            lines.append(f"- resource={record.resource} section={record.section} program={record.program} slot={record.slot} field={record.field} offset=0x{record.absolute_offset:X} {record.old_raw_value.hex()}->{record.new_raw_value.hex()}")
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _discover_fields(self) -> dict[tuple[int, str, int, int | None, str], EditableField]:
        fields: dict[tuple[int, str, int, int | None, str], EditableField] = {}
        for resource_index, group in enumerate(self.groups):
            for sec in group.sections:
                if sp.SECTION_TAGS.get(sec.signature) != "SCEIProg" or not sec.valid:
                    continue
                parsed = sec.evidence.get("scei_prog", {})
                for program in parsed.get("programs", []):
                    program_index = int(program["index"])
                    for name in PROGRAM_FIELDS:
                        meta = program.get(name)
                        if isinstance(meta, dict):
                            self._add_field(fields, resource_index, "SCEIProg", program_index, None, name, int(meta["absolute_offset"]))
                    for slot in program.get("slots", []):
                        slot_index = int(slot["index"])
                        slot_abs = int(slot["absolute_offset"])
                        slot_size = len(bytes.fromhex(slot.get("raw_bytes", "")))
                        for name, rel in SLOT_FIELDS.items():
                            meta = slot.get(name)
                            if isinstance(meta, dict) and "absolute_offset" in meta:
                                self._add_field(fields, resource_index, "SCEIProg", program_index, slot_index, name, int(meta["absolute_offset"]))
                            elif rel < slot_size:
                                self._add_field(fields, resource_index, "SCEIProg", program_index, slot_index, name, slot_abs + rel)
        return fields

    def _add_field(self, fields: dict, resource: int, section: str, program: int, slot: int | None, field: str, off: int) -> None:
        editable = EditableField(resource, section, program, slot, field, off, self._original[off:off + 1])
        fields[editable.key()] = editable

    def _field(self, resource: int, section: str, program: int, slot: int | None, field: str) -> EditableField:
        key = (resource, section, program, slot, field)
        if key not in self.fields:
            raise KeyError(f"unknown or unsafe SNDDATA edit field: {key}")
        return self.fields[key]

    @staticmethod
    def _coerce_raw(value: int | bytes) -> bytes:
        if isinstance(value, int):
            if not 0 <= value <= 0xFF:
                raise ValueError("SNDDATA v1 editable fields are one byte")
            return bytes([value])
        if len(value) != 1:
            raise ValueError("SNDDATA v1 editable fields are one byte")
        return bytes(value)

    def _current_applied_records(self) -> list[EditRecord]:
        return [EditRecord.from_field(editable, editable.original_raw_value, self._values[key]) for key, editable in self.fields.items() if self._values[key] != editable.original_raw_value]

    def _confirm_boundaries(self, reparsed: list[sp.ResourceGroup]) -> None:
        original = [(g.offset, [(s.offset, s.block_size, s.end_offset, s.valid) for s in g.sections]) for g in self.groups]
        new = [(g.offset, [(s.offset, s.block_size, s.end_offset, s.valid) for s in g.sections]) for g in reparsed]
        if original != new:
            raise ValueError("reparsed section boundaries changed")

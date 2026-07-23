#!/usr/bin/env python3
"""Compile a FragmentUpdater-style XLSX workbook into an offline patch manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660, IsoEntry, SECTOR_USER, normalize_path  # noqa: E402
from iso_patch_engine import PatchError, read_extent_range, sha256_file  # noqa: E402
from simple_xlsx import XlsxError, data_rows, read_workbook  # noqa: E402

FILE_LIVE_OFFSETS = {
    "SLPS_255.27": 0x0FFF00,
    "HACK_01.ELF": 0x0FFF00,
    "HACK_00.ELF": 0x0FFF00,
    "GCMNF.PRG": 0x537600,
    "GCMNO.PRG": 0x78CB80,
    "DESKTOPF.PRG": 0x537600,
    "TOPPAGEF.PRG": 0x537600,
    "MATCHING.PRG": 0x78CB80,
    "DATA.BIN": 0,
}
NONE_FILE = "NONE"


class TranslationCompileError(PatchError):
    pass


@dataclass(frozen=True)
class FileTarget:
    workbook_name: str
    internal_path: str
    live_offset: int
    entry: IsoEntry


@dataclass(frozen=True)
class PatchDefinition:
    name: str
    data_sheet: str
    text_sheet: str
    offline_file: str
    online_file: str
    offline_base: int
    online_base: int
    offline_string_base: int
    online_string_base: int
    object_read_length: int
    object_count: int
    string_byte_limit: int
    pointer_offsets: tuple[int, ...]


class PatchAccumulator:
    def __init__(self, targets: dict[str, FileTarget]) -> None:
        self.targets = targets
        self._bytes: dict[str, dict[int, int]] = {}
        self._sources: dict[tuple[str, int], str] = {}

    def write(self, file_name: str, offset: int, data: bytes, source: str) -> None:
        if file_name == NONE_FILE:
            return
        target = self.targets[file_name]
        if offset < 0 or offset + len(data) > target.entry.size:
            raise TranslationCompileError(
                f"{source}: write exceeds {file_name} at 0x{offset:X} "
                f"(length 0x{len(data):X}, file size 0x{target.entry.size:X})."
            )
        pending = self._bytes.setdefault(file_name, {})
        for delta, value in enumerate(data):
            position = offset + delta
            previous = pending.get(position)
            if previous is not None and previous != value:
                prior_source = self._sources.get((file_name, position), "another patch")
                raise TranslationCompileError(
                    f"{source}: conflicting write in {file_name} at 0x{position:X}; "
                    f"already written by {prior_source}."
                )
            pending[position] = value
            self._sources[(file_name, position)] = source

    def ranges(self) -> list[tuple[FileTarget, int, bytes]]:
        result: list[tuple[FileTarget, int, bytes]] = []
        for file_name in sorted(self._bytes):
            positions = sorted(self._bytes[file_name])
            if not positions:
                continue
            start = positions[0]
            previous = start
            values = bytearray((self._bytes[file_name][start],))
            for position in positions[1:]:
                if position == previous + 1:
                    values.append(self._bytes[file_name][position])
                else:
                    result.append((self.targets[file_name], start, bytes(values)))
                    start = position
                    values = bytearray((self._bytes[file_name][position],))
                previous = position
            result.append((self.targets[file_name], start, bytes(values)))
        return result


def _hex(value: str, field: str) -> int:
    text = str(value or "").strip()
    if not text:
        raise TranslationCompileError(f"{field} is required.")
    try:
        return int(text, 16)
    except ValueError as exc:
        raise TranslationCompileError(f"{field} is not hexadecimal: {text!r}") from exc


def _decimal(value: str, field: str) -> int:
    text = str(value or "").strip()
    try:
        return int(text, 10)
    except ValueError as exc:
        raise TranslationCompileError(f"{field} is not an integer: {text!r}") from exc


def _definitions(workbook: dict[str, list[list[str]]]) -> list[PatchDefinition]:
    definitions: list[PatchDefinition] = []
    for sheet_name in ("Patches", "IMG Patches"):
        if sheet_name not in workbook:
            continue
        for row_index, row in enumerate(data_rows(workbook, sheet_name), start=2):
            if len(row) < 12:
                raise TranslationCompileError(
                    f"{sheet_name} row {row_index} needs at least 12 columns."
                )
            offline_file = row[3].strip().upper()
            online_file = row[4].strip().upper()
            for field_name, file_name in (
                ("offline file", offline_file),
                ("online file", online_file),
            ):
                if file_name != NONE_FILE and file_name not in FILE_LIVE_OFFSETS:
                    raise TranslationCompileError(
                        f"{sheet_name} row {row_index} has unknown {field_name}: {file_name}"
                    )
            definitions.append(
                PatchDefinition(
                    name=row[0].strip() or f"{sheet_name}-{row_index}",
                    data_sheet=row[1].strip(),
                    text_sheet=row[2].strip(),
                    offline_file=offline_file,
                    online_file=online_file,
                    offline_base=_hex(row[5], f"{sheet_name} row {row_index} offline base"),
                    online_base=_hex(row[6], f"{sheet_name} row {row_index} online base"),
                    offline_string_base=_hex(
                        row[7], f"{sheet_name} row {row_index} offline string base"
                    ),
                    online_string_base=_hex(
                        row[8], f"{sheet_name} row {row_index} online string base"
                    ),
                    object_read_length=_hex(
                        row[9], f"{sheet_name} row {row_index} object length"
                    ),
                    object_count=_decimal(
                        row[10], f"{sheet_name} row {row_index} object count"
                    ),
                    string_byte_limit=_hex(
                        row[11], f"{sheet_name} row {row_index} string limit"
                    ),
                    pointer_offsets=tuple(
                        _hex(value, f"{sheet_name} row {row_index} pointer offset")
                        for value in row[12:]
                    ),
                )
            )
    if not definitions:
        raise TranslationCompileError("Workbook has no Patches or IMG Patches definitions.")
    return definitions


def _resolve_targets(index: dict[str, IsoEntry], definitions: list[PatchDefinition]) -> dict[str, FileTarget]:
    required = {
        file_name
        for definition in definitions
        for file_name in (definition.offline_file, definition.online_file)
        if file_name != NONE_FILE
    }
    by_basename: dict[str, list[IsoEntry]] = {}
    for internal_path, entry in index.items():
        basename = Path(internal_path).name.upper()
        by_basename.setdefault(basename, []).append(entry)

    targets: dict[str, FileTarget] = {}
    for file_name in sorted(required):
        matches = by_basename.get(file_name, [])
        if not matches:
            raise TranslationCompileError(f"Required ISO file was not found: {file_name}")
        if len(matches) > 1:
            paths = ", ".join(sorted(entry.path for entry in matches))
            raise TranslationCompileError(f"ISO file name is ambiguous for {file_name}: {paths}")
        entry = matches[0]
        targets[file_name] = FileTarget(
            file_name,
            normalize_path(entry.path),
            FILE_LIVE_OFFSETS[file_name],
            entry,
        )
    return targets


def _encode_cp932(text: str, source: str) -> bytes:
    try:
        return text.encode("cp932")
    except UnicodeEncodeError as exc:
        raise TranslationCompileError(
            f"{source}: text contains a character unavailable in CP932: {exc.object[exc.start:exc.end]!r}"
        ) from exc


def _text_values(
    workbook: dict[str, list[list[str]]],
    sheet_name: str,
) -> list[tuple[int, str]]:
    values: list[tuple[int, str]] = []
    seen: set[int] = set()
    try:
        rows = data_rows(workbook, sheet_name)
    except XlsxError as exc:
        raise TranslationCompileError(str(exc)) from exc
    for row_index, row in enumerate(rows, start=2):
        original_offset = _hex(row[0], f"{sheet_name} row {row_index} text offset")
        if original_offset in seen:
            raise TranslationCompileError(
                f"{sheet_name} row {row_index} duplicates text offset 0x{original_offset:X}."
            )
        seen.add(original_offset)
        text = row[2] if len(row) >= 3 else row[1] if len(row) >= 2 else "\n"
        values.append((original_offset, text))
    return values


def _data_values(
    workbook: dict[str, list[list[str]]],
    sheet_name: str,
) -> list[tuple[int, list[int]]]:
    values: list[tuple[int, list[int]]] = []
    try:
        rows = data_rows(workbook, sheet_name)
    except XlsxError as exc:
        raise TranslationCompileError(str(exc)) from exc
    for row_index, row in enumerate(rows, start=2):
        object_offset = _hex(row[0], f"{sheet_name} row {row_index} object offset")
        pointers: list[int] = []
        for column, value in enumerate(row[1:], start=2):
            pointers.append(
                -1 if value.strip() == "-1" else _hex(value, f"{sheet_name} row {row_index} column {column}")
            )
        values.append((object_offset, pointers))
    return values


def _apply_definition(
    definition: PatchDefinition,
    workbook: dict[str, list[list[str]]],
    targets: dict[str, FileTarget],
    accumulator: PatchAccumulator,
    text_pointer_cache: dict[str, dict[int, int]],
) -> None:
    offset_pairs: dict[int, int] = {}
    if definition.text_sheet != "None":
        cached = text_pointer_cache.get(definition.text_sheet)
        if cached is not None:
            offset_pairs = cached
        else:
            new_offset = 0
            for original_offset, text in _text_values(workbook, definition.text_sheet):
                if not definition.pointer_offsets:
                    new_offset = original_offset
                if original_offset in offset_pairs:
                    raise TranslationCompileError(
                        f"{definition.name}: duplicate text pointer 0x{original_offset:X}."
                    )
                offset_pairs[original_offset] = new_offset
                transformed = text.replace("\n", "\0").replace(chr(96), "\n")
                encoded = _encode_cp932(transformed, definition.name)
                advance = len(_encode_cp932(text, definition.name))
                accumulator.write(
                    definition.offline_file,
                    definition.offline_string_base + new_offset,
                    encoded,
                    f"{definition.name} text",
                )
                accumulator.write(
                    definition.online_file,
                    definition.online_string_base + new_offset,
                    encoded,
                    f"{definition.name} text",
                )
                new_offset += advance
                if new_offset > definition.string_byte_limit:
                    raise TranslationCompileError(
                        f"{definition.name}: translated strings exceed the declared "
                        f"0x{definition.string_byte_limit:X}-byte region."
                    )
            text_pointer_cache[definition.text_sheet] = offset_pairs

    if definition.data_sheet == "None":
        return

    for object_offset, pointers in _data_values(workbook, definition.data_sheet):
        for index, pointer in enumerate(pointers):
            if pointer == -1:
                continue
            if not offset_pairs:
                offline_value = online_value = pointer
                offline_offset = definition.offline_base + object_offset + index * 4
                online_offset = definition.online_base + object_offset + index * 4
            else:
                if index >= len(definition.pointer_offsets):
                    raise TranslationCompileError(
                        f"{definition.name}: data row has more pointers than its patch definition."
                    )
                if pointer not in offset_pairs:
                    raise TranslationCompileError(
                        f"{definition.name}: pointer 0x{pointer:X} is missing from "
                        f"text sheet {definition.text_sheet}."
                    )
                relative = offset_pairs[pointer]
                offline_target = targets.get(definition.offline_file)
                online_target = targets.get(definition.online_file)
                offline_live = offline_target.live_offset if offline_target else 0
                online_live = online_target.live_offset if online_target else 0
                offline_value = definition.offline_string_base + offline_live + relative
                online_value = definition.online_string_base + online_live + relative
                patch_offset = definition.pointer_offsets[index]
                offline_offset = definition.offline_base + object_offset + patch_offset
                online_offset = definition.online_base + object_offset + patch_offset

            accumulator.write(
                definition.offline_file,
                offline_offset,
                int(offline_value).to_bytes(4, "little", signed=False),
                f"{definition.name} data",
            )
            accumulator.write(
                definition.online_file,
                online_offset,
                int(online_value).to_bytes(4, "little", signed=False),
                f"{definition.name} data",
            )


def _operations(
    source: Path,
    iso: Iso9660,
    accumulator: PatchAccumulator,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    with source.open("rb") as image:
        for index, (target, offset, replacement) in enumerate(accumulator.ranges(), start=1):
            expected = read_extent_range(image, iso, target.entry, offset, len(replacement))
            operations.append(
                {
                    "id": f"translation-{index:05d}",
                    "type": "write_bytes",
                    "path": target.internal_path,
                    "offset": offset,
                    "expected_hex": expected.hex().upper(),
                    "replacement_hex": replacement.hex().upper(),
                }
            )
    if not operations:
        raise TranslationCompileError("Workbook produced no patch operations.")
    return operations


def compile_translation_pack(
    source_iso: str | Path,
    workbook_path: str | Path,
    output_manifest: str | Path,
    *,
    pack_name: str = ".hack//frägment English Translation",
    pack_version: str = "workbook-export",
) -> dict[str, Any]:
    source = Path(source_iso).expanduser().resolve()
    workbook_file = Path(workbook_path).expanduser().resolve()
    output = Path(output_manifest).expanduser().resolve()
    if not source.is_file():
        raise TranslationCompileError(f"Source ISO does not exist: {source}")
    if output == source or output == workbook_file:
        raise TranslationCompileError("Output manifest must be a separate file.")

    try:
        workbook = read_workbook(workbook_file)
    except XlsxError as exc:
        raise TranslationCompileError(str(exc)) from exc
    definitions = _definitions(workbook)

    iso = Iso9660(source).open()
    if iso.sector_size != SECTOR_USER or iso.data_offset != 0:
        raise TranslationCompileError(
            "Translation pack compilation currently accepts standard 2048-byte-sector ISO images."
        )
    targets = _resolve_targets(iso.build_index(), definitions)
    accumulator = PatchAccumulator(targets)
    text_pointer_cache: dict[str, dict[int, int]] = {}
    for definition in definitions:
        _apply_definition(
            definition,
            workbook,
            targets,
            accumulator,
            text_pointer_cache,
        )

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "patch": {
            "name": pack_name,
            "version": pack_version,
            "format": "fragmenter-offline-translation",
            "credits": [
                "Vi Ness / Finzenku",
                "tellipatch translation contributors",
                "Netslum community",
            ],
            "workbook_sha256": sha256_file(workbook_file),
        },
        "source": {
            "sha256": sha256_file(source),
            "size": source.stat().st_size,
        },
        "operations": _operations(source, iso, accumulator),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile an exported Fragment translation XLSX into an offline patch manifest."
    )
    parser.add_argument("source_iso", help="Exact original ISO used to verify expected bytes")
    parser.add_argument("workbook", help="Exported translation workbook (.xlsx)")
    parser.add_argument("--out", required=True, help="Output Fragmenter patch manifest JSON")
    parser.add_argument("--name", default=".hack//frägment English Translation")
    parser.add_argument("--version", default="workbook-export")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = compile_translation_pack(
            args.source_iso,
            args.workbook,
            args.out,
            pack_name=args.name,
            pack_version=args.version,
        )
    except TranslationCompileError as exc:
        print(f"Translation pack refused: {exc}", file=sys.stderr)
        return 2
    print(
        f"Wrote {len(manifest['operations'])} verified operations to {Path(args.out).resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

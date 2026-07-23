#!/usr/bin/env python3
"""Small dependency-free XLSX reader for Fragmenter translation workbooks."""

from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MAX_WORKBOOK_BYTES = 100 * 1024 * 1024
MAX_CELLS = 2_000_000
_CELL_REF = re.compile(r"^([A-Za-z]+)")


class XlsxError(RuntimeError):
    pass


def _xml(archive: zipfile.ZipFile, member: str) -> ET.Element:
    try:
        info = archive.getinfo(member)
    except KeyError as exc:
        raise XlsxError(f"Workbook member is missing: {member}") from exc
    if info.file_size > MAX_WORKBOOK_BYTES:
        raise XlsxError(f"Workbook member is unexpectedly large: {member}")
    try:
        return ET.fromstring(archive.read(info))
    except ET.ParseError as exc:
        raise XlsxError(f"Workbook XML is malformed: {member}") from exc


def _column_index(reference: str) -> int:
    match = _CELL_REF.match(reference or "")
    if match is None:
        raise XlsxError(f"Cell reference is invalid: {reference!r}")
    value = 0
    for character in match.group(1).upper():
        value = value * 26 + (ord(character) - ord("A") + 1)
    return value - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _xml(archive, "xl/sharedStrings.xml")
    return [
        "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value_node = cell.find(f"{{{MAIN_NS}}}v")
    value = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "s":
        try:
            return shared[int(value)]
        except (ValueError, IndexError) as exc:
            raise XlsxError(f"Shared-string index is invalid: {value!r}") from exc
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value


def _sheet_rows(
    archive: zipfile.ZipFile,
    member: str,
    shared: list[str],
    *,
    cell_budget: list[int],
) -> list[list[str]]:
    root = _xml(archive, member)
    parsed: list[list[str]] = []
    rows = root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row")
    for excel_row in rows:
        cells: dict[int, str] = {}
        for cell in excel_row.findall(f"{{{MAIN_NS}}}c"):
            cell_budget[0] += 1
            if cell_budget[0] > MAX_CELLS:
                raise XlsxError("Workbook contains too many cells.")
            index = _column_index(cell.get("r", ""))
            cells[index] = _cell_value(cell, shared)
        if not cells or 0 not in cells:
            parsed.append([])
            continue
        values: list[str] = []
        index = 0
        while index in cells:
            values.append(cells[index])
            index += 1
        parsed.append(values)
    return parsed


def read_workbook(path: str | Path) -> dict[str, list[list[str]]]:
    """Return workbook sheets as ordered string rows, including header rows."""
    workbook_path = Path(path).expanduser().resolve()
    if not workbook_path.is_file():
        raise XlsxError(f"Workbook does not exist: {workbook_path}")
    if workbook_path.stat().st_size > MAX_WORKBOOK_BYTES:
        raise XlsxError("Workbook is unexpectedly large.")

    try:
        archive = zipfile.ZipFile(workbook_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise XlsxError(f"Could not open XLSX workbook: {exc}") from exc

    with archive:
        workbook = _xml(archive, "xl/workbook.xml")
        relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
        relation_targets = {
            relation.get("Id", ""): relation.get("Target", "")
            for relation in relationships.findall(f"{{{REL_NS}}}Relationship")
        }
        shared = _shared_strings(archive)
        sheets: dict[str, list[list[str]]] = {}
        cell_budget = [0]
        for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
            name = sheet.get("name", "").strip()
            relation_id = sheet.get(f"{{{DOC_REL_NS}}}id", "")
            target = relation_targets.get(relation_id, "")
            if not name or not target:
                raise XlsxError("Workbook contains a sheet without a valid relationship.")
            if target.startswith("/"):
                member = target.lstrip("/")
            else:
                member = posixpath.normpath(posixpath.join("xl", target))
            sheets[name] = _sheet_rows(
                archive,
                member,
                shared,
                cell_budget=cell_budget,
            )
        return sheets


def data_rows(workbook: dict[str, list[list[str]]], sheet_name: str) -> list[list[str]]:
    """Match FragmentUpdater semantics: skip header, stop at first blank first cell."""
    if sheet_name not in workbook:
        raise XlsxError(f"Workbook sheet was not found: {sheet_name}")
    rows = workbook[sheet_name]
    result: list[list[str]] = []
    for row in rows[1:]:
        if not row:
            break
        result.append(row)
    return result

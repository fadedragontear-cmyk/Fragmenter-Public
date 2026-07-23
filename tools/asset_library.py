#!/usr/bin/env python3
"""Build a compact logical asset library from a CCSF asset index."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

COUNT_COLS = ("MDL", "TEX", "CLT", "MAT", "ANM", "OBJ", "CMP", "BOX", "MPH", "DMY", "HIT", "LGT", "CAM")
HASH_SUFFIX_RE = re.compile(r"(?:[_-]?[0-9a-f]{8,40})$", re.IGNORECASE)
DEFAULT_MAX_REPORT_ROWS = 200



def _as_path(value: object) -> Path | None:
    if isinstance(value, str) and value:
        return Path(value)
    return None


def _index_folder_from(index_path_or_folder: Path | None) -> Path | None:
    if not index_path_or_folder:
        return None
    return index_path_or_folder.parent if index_path_or_folder.suffix else index_path_or_folder


def _workspace_root_from(index_path_or_folder: Path | None) -> Path | None:
    folder = _index_folder_from(index_path_or_folder)
    if folder and folder.name == "reports":
        return folder.parent
    return None


def _likely_extracted_ccs_folders(workspace_root: Path | None) -> list[Path]:
    if not workspace_root:
        return []
    return [workspace_root / "extracted_ccs"]


def _existing(path: Path | None) -> Path | None:
    return path if path and path.exists() else None


def _resolve_by_basename(base: Path, name: str) -> Path | None:
    if not base.is_dir() or not name:
        return None
    matches = [path for path in base.rglob(name) if path.is_file()]
    return matches[0] if len(matches) == 1 else None


def resolve_asset_file(
    asset: dict[str, Any],
    index_path_or_folder: Path | None,
    workspace_root: Path | None = None,
    extracted_ccs_folders: list[Path] | None = None,
) -> Path | None:
    """Resolve an indexed asset file without changing its display label."""
    index_folder = _index_folder_from(index_path_or_folder)
    workspace_root = workspace_root or _workspace_root_from(index_path_or_folder)
    extracted_ccs_folders = extracted_ccs_folders or _likely_extracted_ccs_folders(workspace_root)
    candidates = [_as_path(asset.get("file")), _as_path(asset.get("relative_file"))]

    for raw in candidates:
        if raw and raw.is_absolute() and raw.exists():
            return raw
    for raw in candidates:
        if not raw or raw.is_absolute():
            continue
        for base in ([index_folder] if index_folder else []):
            resolved = _existing(base / raw)
            if resolved:
                return resolved
    for raw in candidates:
        if not raw or raw.is_absolute():
            continue
        for base in ([workspace_root] if workspace_root else []):
            resolved = _existing(base / raw)
            if resolved:
                return resolved
    for raw in candidates:
        if not raw or raw.is_absolute():
            continue
        for base in extracted_ccs_folders:
            resolved = _existing(base / raw)
            if resolved:
                return resolved
    for raw in candidates:
        if not raw:
            continue
        for base in extracted_ccs_folders:
            resolved = _resolve_by_basename(base, raw.name)
            if resolved:
                return resolved
    return candidates[0] or candidates[1]


def _resolve_file(asset: dict[str, Any], index_folder: Path | None) -> Path | None:
    return resolve_asset_file(asset, index_folder)


def _file_href(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.resolve().as_uri()


def _sha1(path: Path | None, asset: dict[str, Any]) -> str:
    existing = asset.get("sha1")
    if isinstance(existing, str) and existing:
        return existing
    if not path or not path.is_file():
        return ""
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean_stem(path: str) -> str:
    stem = Path(path).stem
    return HASH_SUFFIX_RE.sub("", stem).strip("_-. ").lower()


def _logical_name(name: str) -> str:
    name = HASH_SUFFIX_RE.sub("", name).strip("_-. ")
    return name or "(unnamed)"


def _counts(asset: dict[str, Any]) -> dict[str, int]:
    counts = asset.get("counts") if isinstance(asset.get("counts"), dict) else {}
    groups = asset.get("groups") if isinstance(asset.get("groups"), dict) else {}
    out: dict[str, int] = {}
    for key in COUNT_COLS:
        value = counts.get(key)
        if isinstance(value, int):
            out[key] = value
        else:
            group = groups.get(key)
            out[key] = len(group) if isinstance(group, list) else 0
    return out


def _resource_counts_key(counts: dict[str, int]) -> tuple[tuple[str, int], ...]:
    return tuple((key, counts.get(key, 0)) for key in COUNT_COLS)


def _asset_key(asset: dict[str, Any], sha1: str, counts: dict[str, int]) -> tuple[Any, ...]:
    name = _logical_name(str(asset.get("name") or "")).lower()
    typ = str(asset.get("type") or "unknown")
    variant = str(asset.get("variant") or "")
    size = int(asset.get("size") or 0)
    # SHA1 is included when available, but assets with the same logical metadata
    # still group when no hash can be determined.
    return (name, sha1 or None, size, typ, variant, _resource_counts_key(counts))


def _file_label(asset: dict[str, Any]) -> str:
    return str(asset.get("relative_file") or asset.get("file") or "")


def _is_iso_extracted(label: str) -> bool:
    return Path(label).suffix.lower() == ".ccs"


def _preferred_sort_key(label: str, resolved: Path | None = None) -> tuple[int, int, int, int, str]:
    clean_len = len(_clean_stem(label)) or len(Path(label).stem)
    hash_penalty = 1 if HASH_SUFFIX_RE.search(Path(label).stem) else 0
    tmp_penalty = 1 if Path(label).suffix.lower() == ".tmp" else 0
    exists_penalty = 0 if resolved and resolved.exists() else 1
    ccs_priority = 0 if _is_iso_extracted(label) and resolved and resolved.exists() else 1
    # Lower is better: existing file, existing ISO-extracted .ccs, clean short name, non-hash duplicate.
    return (exists_penalty, ccs_priority, clean_len, hash_penalty + tmp_penalty, label.lower())


def _source_lookup(extraction_report: dict[str, Any] | None) -> dict[str, dict[str, set[str]]]:
    lookup: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"containers": set(), "sources": set()})
    if not extraction_report:
        return lookup
    for row in extraction_report.get("confirmed_ccsf_bundles", []) or extraction_report.get("extractions", []) or []:
        if not isinstance(row, dict):
            continue
        keys = [str(row.get("extracted_ccsf_path") or ""), Path(str(row.get("extracted_ccsf_path") or "")).name]
        for key in keys:
            if not key:
                continue
            if row.get("top_level_iso_file_path"):
                lookup[key]["containers"].add(str(row["top_level_iso_file_path"]))
            if row.get("source_iso_path"):
                lookup[key]["sources"].add(str(row["source_iso_path"]))
    return lookup


def _tags(asset: dict[str, Any], counts: dict[str, int], duplicate_count: int) -> list[str]:
    tags = {str(asset.get("type") or "unknown")}
    variant = str(asset.get("variant") or "")
    if variant:
        tags.add(f"variant:{variant}")
    for key, count in counts.items():
        if count:
            tags.add(key.lower())
    if duplicate_count:
        tags.add("duplicate")
    readiness = str(asset.get("readiness") or "")
    if readiness:
        tags.add(f"ready:{readiness}")
    return sorted(tags)


def build_asset_library(index: dict[str, Any], extraction_report: dict[str, Any] | None = None, index_path: Path | None = None) -> dict[str, Any]:
    """Group indexed CCSF entries into logical assets."""
    index_folder = index_path or _as_path(index.get("folder"))
    source_map = _source_lookup(extraction_report)
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    enriched: list[dict[str, Any]] = []
    for asset in index.get("assets", []) or []:
        if not isinstance(asset, dict):
            continue
        path = _resolve_file(asset, index_folder)
        sha1 = _sha1(path, asset)
        counts = _counts(asset)
        item = {**asset, "_label": _file_label(asset), "_resolved": path, "_sha1": sha1, "_counts": counts}
        enriched.append(item)
        grouped[_asset_key(asset, sha1, counts)].append(item)

    logical_assets = []
    for items in grouped.values():
        preferred = min(items, key=lambda item: _preferred_sort_key(item["_label"], item.get("_resolved")))
        label_paths = {item["_label"]: item.get("_resolved") for item in items if item["_label"]}
        labels = sorted(label_paths, key=lambda label: _preferred_sort_key(label, label_paths.get(label)))
        duplicate_files = [label for label in labels if label != preferred["_label"]]
        containers: set[str] = set()
        sources: set[str] = set()
        for item in items:
            for key in (item["_label"], str(Path(item["_label"]).name)):
                containers.update(source_map.get(key, {}).get("containers", set()))
                sources.update(source_map.get(key, {}).get("sources", set()))
        counts = preferred["_counts"]
        logical_assets.append({
            "display_name": _logical_name(str(preferred.get("name") or Path(preferred["_label"]).stem)),
            "type": preferred.get("type") or "unknown",
            "variant": preferred.get("variant") or "",
            "preferred_file": preferred["_label"],
            "preferred_file_href": _file_href(preferred.get("_resolved")),
            "duplicate_files": duplicate_files,
            "source_count": len(items),
            "size": int(preferred.get("size") or 0),
            "readiness": preferred.get("readiness") or "",
            "resource_counts": counts,
            "source_containers": sorted(containers),
            "source_isos": sorted(sources),
            "tags": _tags(preferred, counts, len(duplicate_files)),
        })
    logical_assets.sort(key=lambda item: (str(item["display_name"]).lower(), str(item["variant"]), str(item["preferred_file"]).lower()))
    return {"asset_count": len(logical_assets), "source_asset_count": len(enriched), "assets": logical_assets}


def _limited_section(items, max_rows: int | None) -> tuple[list[Any], int]:
    rows = list(items or [])
    if max_rows is None or max_rows < 0:
        return rows, 0
    return rows[:max_rows], max(0, len(rows) - max_rows)


def format_library(library: dict[str, Any], max_report_rows: int | None = DEFAULT_MAX_REPORT_ROWS) -> str:
    assets = list(library.get("assets") or [])
    shown_assets, omitted_assets = _limited_section(assets, max_report_rows)
    lines = ["CCSF Asset Library", f"Logical assets: {library.get('asset_count', 0)}", f"Indexed sources: {library.get('source_asset_count', 0)}", f"Text row limit: {'unlimited' if max_report_rows is None or max_report_rows < 0 else max_report_rows}", f"Logical asset rows omitted: {omitted_assets}", ""]
    for asset in shown_assets:
        counts = asset.get("resource_counts") or {}
        active = ", ".join(f"{k}:{v}" for k, v in counts.items() if v) or "metadata"
        variant = asset.get("variant") or "-"
        dup = f" (+{len(asset.get('duplicate_files') or [])} dup)" if asset.get("duplicate_files") else ""
        lines.append(f"- {asset.get('display_name')} [{asset.get('type')}; variant {variant}; {active}] {asset.get('preferred_file')}{dup}")
    if omitted_assets:
        lines.append(f"... omitted {omitted_assets} additional logical asset rows; full data is available in JSON output.")
    return "\n".join(lines) + "\n"


def _load_optional(path: Path | None) -> dict[str, Any] | None:
    if path and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def write_library(library: dict[str, Any], out: Path, text_out: Path, *, max_report_rows: int | None = DEFAULT_MAX_REPORT_ROWS) -> tuple[Path, Path]:
    out.parent.mkdir(parents=True, exist_ok=True)
    text_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(library, indent=2), encoding="utf-8")
    text_out.write_text(format_library(library, max_report_rows=max_report_rows), encoding="utf-8")
    return out, text_out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Group CCSF asset index entries into a logical asset library.")
    ap.add_argument("--index", default="workspace/reports/ccsf_asset_index.json")
    ap.add_argument("--extraction-report", default="workspace/reports/iso_ccsf_extraction_index.json")
    ap.add_argument("--out", default="workspace/reports/asset_library.json")
    ap.add_argument("--text-out", default="workspace/reports/asset_library.txt")
    ap.add_argument("--max-report-rows", type=int, default=DEFAULT_MAX_REPORT_ROWS, help="Maximum logical asset rows to show in the text report; use a negative value for unlimited.")
    args = ap.parse_args(argv)
    index = json.loads(Path(args.index).read_text(encoding="utf-8"))
    extraction_report = _load_optional(Path(args.extraction_report))
    library = build_asset_library(index, extraction_report, Path(args.index))
    out, text = write_library(library, Path(args.out), Path(args.text_out), max_report_rows=args.max_report_rows)
    print(f"Logical assets: {library['asset_count']}")
    print(f"Output JSON: {out}")
    print(f"Output text: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

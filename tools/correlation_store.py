#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_STORE = Path("fragmenter_correlations.json")
STATUSES = ("unreviewed", "probable", "confirmed", "rejected")
PROTECTED_STATUSES = {"confirmed", "rejected"}

FAMILY_FIELDS = (
    "models",
    "textures",
    "materials",
    "animations",
    "cameras",
    "markers",
    "asset_paths",
    "suggested_searches",
    "notes",
)


PREFIX_FAMILY_FIELDS = {
    "MDL_": ("preview_models", "models"),
    "TEX_": ("preview_textures", "textures"),
    "MAT_": ("preview_materials", "materials"),
    "ANM_": ("preview_animations", "animations"),
    "CAM_": ("preview_cameras", "cameras"),
    "DMY_": ("preview_markers", "markers"),
}

PATH_CLASS_FAMILIES = {
    "model_paths": "preview_model_paths",
    "texture_paths": "preview_texture_paths",
    "animation_paths": "preview_animation_paths",
    "audio_paths": "preview_audio_paths",
    "paths": "preview_embedded_paths",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_store() -> dict[str, Any]:
    now = utc_now()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "statuses": list(STATUSES),
        "sections": {},
    }


def backup_malformed(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.{stamp}.{counter}.bak")
        counter += 1
    shutil.move(str(path), str(backup))
    return backup


def load_store(path: Path) -> tuple[dict[str, Any], Path | None]:
    if not path.exists():
        return empty_store(), None
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
    except json.JSONDecodeError:
        backup = backup_malformed(path)
        return empty_store(), backup
    if not isinstance(obj, dict):
        backup = backup_malformed(path)
        return empty_store(), backup

    obj.setdefault("version", 1)
    obj.setdefault("created_at", utc_now())
    obj.setdefault("statuses", list(STATUSES))
    obj.setdefault("sections", {})
    if not isinstance(obj["sections"], dict):
        obj["sections"] = {}
    obj["updated_at"] = obj.get("updated_at") or utc_now()
    return obj, None


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = utc_now()
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent or Path(".")))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def section_entry(store: dict[str, Any], section: str) -> dict[str, Any]:
    sections = store.setdefault("sections", {})
    sec = sections.setdefault(
        section,
        {
            "section": section,
            "created_at": utc_now(),
            "families": {},
            "symbols": {},
            "asset_paths": [],
        },
    )
    sec.setdefault("families", {})
    return sec


def family_entry(store: dict[str, Any], section: str, family: str) -> dict[str, Any]:
    sec = section_entry(store, section)
    fams = sec.setdefault("families", {})
    fam = fams.setdefault(
        family,
        {
            "family": family,
            "created_at": utc_now(),
            "confidence": 0.0,
            "hits": [],
        },
    )
    fam.setdefault("hits", [])
    return fam


def sorted_unique(items: Iterable[Any]) -> list[Any]:
    return sorted({x for x in items if x not in (None, "")})


def import_resource_map(store: dict[str, Any], map_path: Path) -> dict[str, int | str]:
    with map_path.open("r", encoding="utf-8") as f:
        resource_map = json.load(f)
    section = str(resource_map.get("section") or "unknown")
    sec = section_entry(store, section)
    sec["imported_from"] = str(map_path)
    sec["last_imported_at"] = utc_now()
    sec["symbols"] = resource_map.get("symbols", {}) if isinstance(resource_map.get("symbols"), dict) else {}
    sec["asset_paths"] = sorted_unique(resource_map.get("asset_paths", []))

    added = 0
    updated = 0
    for src_fam in resource_map.get("families", []):
        if not isinstance(src_fam, dict):
            continue
        name = str(src_fam.get("family") or "").strip()
        if not name:
            continue
        fams = sec.setdefault("families", {})
        existed = name in fams
        fam = family_entry(store, section, name)
        hits = fam.get("hits", [])
        fam["family"] = name
        fam["confidence"] = src_fam.get("confidence", fam.get("confidence", 0.0))
        fam["last_imported_at"] = utc_now()
        for key in FAMILY_FIELDS:
            value = src_fam.get(key, [])
            fam[key] = sorted_unique(value) if isinstance(value, list) else value
        fam["hits"] = hits
        for src_hit in src_fam.get("hits", []):
            if not isinstance(src_hit, dict) or not src_hit.get("path"):
                continue
            hit = find_hit(fam, str(src_hit["path"]))
            if hit is None:
                new_hit = dict(src_hit)
                if new_hit.get("status") not in STATUSES:
                    new_hit["status"] = "unreviewed"
                new_hit.setdefault("added_at", utc_now())
                fam["hits"].append(new_hit)
            elif hit.get("status") not in PROTECTED_STATUSES:
                current_status = hit.get("status", "unreviewed")
                hit.update(src_hit)
                incoming_status = src_hit.get("status", current_status)
                hit["status"] = incoming_status if incoming_status in STATUSES else current_status
                hit["updated_at"] = utc_now()
        if existed:
            updated += 1
        else:
            added += 1
    sec["family_count"] = len(sec.get("families", {}))
    return {"section": section, "families_added": added, "families_updated": updated}


def _coerce_iterable(value: Iterable[Any] | Any | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    return list(value)


def _merge_unique(existing: Iterable[Any] | Any | None, incoming: Iterable[Any] | Any | None) -> list[Any]:
    values = []
    for item in _coerce_iterable(existing) + _coerce_iterable(incoming):
        text = str(item).strip()
        if text and text not in values:
            values.append(text)
    return sorted(values)


def _preview_section_name(preview: dict[str, Any], section_hint: str | None = None) -> str:
    hint = str(section_hint or "").strip()
    if hint:
        return hint
    source = str(preview.get("path") or "").strip()
    if source:
        return Path(source).stem or "binary_preview"
    return "binary_preview"


def _preview_section_guesses(preview: dict[str, Any], section: str) -> list[str]:
    guesses = [section]
    source = str(preview.get("path") or "").strip()
    if source:
        guesses.append(Path(source).stem)
    gz = preview.get("gzip") if isinstance(preview.get("gzip"), dict) else {}
    original = str((gz or {}).get("original_filename") or "").strip()
    if original:
        guesses.append(Path(original).stem)
    ccsf = preview.get("ccsf") if isinstance(preview.get("ccsf"), dict) else {}
    for key in ("fragment_core_CCSF_SIG_offsets", "plain_CCSF_offsets"):
        vals = (ccsf or {}).get(key) or []
        if isinstance(vals, list):
            guesses.extend(f"{key}:{int(v):08X}" for v in vals if isinstance(v, int))
    return sorted_unique(guesses)


def _add_preview_hit(fam: dict[str, Any], hit_path: str, *, source: str, preview_path: str) -> bool:
    hit = find_hit(fam, hit_path)
    if hit is None:
        fam.setdefault("hits", []).append(
            {
                "path": hit_path,
                "status": "unreviewed",
                "source": source,
                "preview_path": preview_path,
                "added_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        return True
    # Importing preview data never promotes or demotes user-reviewed decisions.
    if hit.get("status") not in STATUSES:
        hit["status"] = "unreviewed"
    hit["source"] = hit.get("source") or source
    hit["preview_path"] = hit.get("preview_path") or preview_path
    hit["updated_at"] = utc_now()
    return False


def import_binary_preview(store: dict[str, Any], preview_path: Path, section_hint: str | None = None) -> dict[str, int | str]:
    with preview_path.open("r", encoding="utf-8") as f:
        preview = json.load(f)
    if not isinstance(preview, dict):
        raise ValueError("Binary preview JSON must contain an object")

    section = _preview_section_name(preview, section_hint)
    preview_source = str(preview.get("path") or preview_path)
    sec = section_entry(store, section)
    sec["last_preview_imported_at"] = utc_now()
    sec["preview_imported_from"] = str(preview_path)
    sec["preview_source_path"] = preview_source
    sec["preview_sha1"] = preview.get("sha1")
    sec["preview_size"] = preview.get("size")
    sec["preview_detected_type"] = preview.get("detected_type")
    sec["section_guesses"] = _preview_section_guesses(preview, section)

    strings = preview.get("strings") if isinstance(preview.get("strings"), dict) else {}
    classes = (strings or {}).get("classes") if isinstance((strings or {}).get("classes"), dict) else {}
    embedded_paths: list[str] = []
    for key in PATH_CLASS_FAMILIES:
        vals = (classes or {}).get(key) or []
        if isinstance(vals, list):
            embedded_paths.extend(str(v) for v in vals)
    sec["asset_paths"] = _merge_unique(sec.get("asset_paths"), embedded_paths)

    families_added = 0
    families_updated = 0
    hits_added = 0

    symbols = preview.get("symbols") if isinstance(preview.get("symbols"), dict) else {}
    sec_symbols = sec.setdefault("symbols", {})
    for pfx, (family_name, field_name) in PREFIX_FAMILY_FIELDS.items():
        info = (symbols or {}).get(pfx) if isinstance((symbols or {}).get(pfx), dict) else {}
        items = [str(x) for x in (info or {}).get("items") or []]
        if not items:
            continue
        existed = family_name in sec.setdefault("families", {})
        fam = family_entry(store, section, family_name)
        fam["confidence"] = max(float(fam.get("confidence", 0.0) or 0.0), 0.25)
        fam["last_preview_imported_at"] = utc_now()
        fam[field_name] = _merge_unique(fam.get(field_name), items)
        fam["suggested_searches"] = _merge_unique(fam.get("suggested_searches"), items[:25])
        sec_symbols[pfx] = {"count": info.get("count", len(items)), "items": _merge_unique((sec_symbols.get(pfx) or {}).get("items") if isinstance(sec_symbols.get(pfx), dict) else [], items)}
        families_updated += 1 if existed else 0
        families_added += 0 if existed else 1

    for cls, family_name in PATH_CLASS_FAMILIES.items():
        vals = (classes or {}).get(cls) or []
        paths = [str(v) for v in vals] if isinstance(vals, list) else []
        if not paths:
            continue
        existed = family_name in sec.setdefault("families", {})
        fam = family_entry(store, section, family_name)
        fam["confidence"] = max(float(fam.get("confidence", 0.0) or 0.0), 0.35)
        fam["last_preview_imported_at"] = utc_now()
        fam["asset_paths"] = _merge_unique(fam.get("asset_paths"), paths)
        fam["suggested_searches"] = _merge_unique(fam.get("suggested_searches"), paths[:25])
        for path in paths:
            if _add_preview_hit(fam, path, source=cls, preview_path=preview_source):
                hits_added += 1
        families_updated += 1 if existed else 0
        families_added += 0 if existed else 1

    unknown_strings = (classes or {}).get("unknown_strings") or []
    if isinstance(unknown_strings, list) and unknown_strings:
        family_name = "preview_strings"
        existed = family_name in sec.setdefault("families", {})
        fam = family_entry(store, section, family_name)
        fam["confidence"] = max(float(fam.get("confidence", 0.0) or 0.0), 0.1)
        fam["last_preview_imported_at"] = utc_now()
        fam["suggested_searches"] = _merge_unique(fam.get("suggested_searches"), [str(v) for v in unknown_strings[:50]])
        families_updated += 1 if existed else 0
        families_added += 0 if existed else 1

    sec["family_count"] = len(sec.get("families", {}))
    return {
        "section": section,
        "families_added": families_added,
        "families_updated": families_updated,
        "hits_added": hits_added,
        "embedded_paths": len(sorted_unique(embedded_paths)),
    }


def find_hit(fam: dict[str, Any], path: str) -> dict[str, Any] | None:
    for hit in fam.setdefault("hits", []):
        if hit.get("path") == path:
            return hit
    return None


def add_iso_hit(
    store: dict[str, Any],
    section: str,
    family: str,
    hit_path: str,
    size: int | None = None,
    status: str = "unreviewed",
    notes: str | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"Invalid status {status!r}; expected one of: {', '.join(STATUSES)}")
    fam = family_entry(store, section, family)
    hit = find_hit(fam, hit_path)
    if hit is None:
        hit = {"path": hit_path, "status": status, "added_at": utc_now()}
        fam.setdefault("hits", []).append(hit)
    elif hit.get("status") not in PROTECTED_STATUSES:
        hit["status"] = status
    if size is not None:
        hit["size"] = size
    if notes:
        hit["notes"] = notes
    hit["updated_at"] = utc_now()
    return hit


def set_hit_status(store: dict[str, Any], section: str, family: str, hit_path: str, status: str, notes: str | None = None) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"Invalid status {status!r}; expected one of: {', '.join(STATUSES)}")
    fam = family_entry(store, section, family)
    hit = find_hit(fam, hit_path)
    if hit is None:
        hit = {"path": hit_path, "added_at": utc_now()}
        fam.setdefault("hits", []).append(hit)
    hit["status"] = status
    if notes:
        hit["notes"] = notes
    hit["updated_at"] = utc_now()
    return hit


def generate_report(store: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Fragmenter Correlation Report")
    lines.append(f"Generated: {utc_now()}")
    lines.append(f"Store updated: {store.get('updated_at', 'unknown')}")
    lines.append("")
    sections = store.get("sections", {})
    if not sections:
        lines.append("No manual correlations recorded yet.")
        return "\n".join(lines) + "\n"

    totals = {status: 0 for status in STATUSES}
    for sec_name in sorted(sections):
        sec = sections[sec_name]
        families = sec.get("families", {})
        lines.append(f"Section: {sec_name}")
        lines.append(f"Families: {len(families)}")
        for fam_name in sorted(families):
            fam = families[fam_name]
            hits = fam.get("hits", [])
            by_status = {status: 0 for status in STATUSES}
            for hit in hits:
                hit_status = hit.get("status", "unreviewed")
                if hit_status not in by_status:
                    hit_status = "unreviewed"
                by_status[hit_status] += 1
                totals[hit_status] += 1
            summary = ", ".join(f"{status}={by_status[status]}" for status in STATUSES if by_status[status]) or "no hits"
            confidence = fam.get("confidence", 0.0)
            lines.append(f"  - Family: {fam_name} (confidence={confidence}; {summary})")
            searches = fam.get("suggested_searches") or []
            if searches:
                lines.append(f"    Suggested searches: {', '.join(map(str, searches[:8]))}")
            for hit in sorted(hits, key=lambda h: (str(h.get("status", "")), str(h.get("path", "")))):
                status = hit.get("status", "unreviewed")
                size = hit.get("size")
                size_part = f" size={size}" if size is not None else ""
                lines.append(f"    [{status}] {hit.get('path', '<missing path>')}{size_part}")
                if hit.get("notes"):
                    lines.append(f"      notes: {hit['notes']}")
        lines.append("")
    lines.append("Totals: " + ", ".join(f"{status}={totals[status]}" for status in STATUSES))
    return "\n".join(lines) + "\n"


def load_for_write(path: Path) -> dict[str, Any]:
    store, backup = load_store(path)
    if backup:
        print(f"Malformed JSON backed up to: {backup}")
    return store


def cmd_init(args: argparse.Namespace) -> int:
    store, backup = load_store(args.store)
    if backup:
        print(f"Malformed JSON backed up to: {backup}")
    atomic_write_json(args.store, store)
    print(f"Initialized correlation store: {args.store}")
    return 0


def cmd_import_map(args: argparse.Namespace) -> int:
    store = load_for_write(args.store)
    summary = import_resource_map(store, args.map)
    atomic_write_json(args.store, store)
    print(
        f"Imported {args.map} into {args.store}: section={summary['section']} "
        f"added={summary['families_added']} updated={summary['families_updated']}"
    )
    return 0


def cmd_add_hit(args: argparse.Namespace) -> int:
    store = load_for_write(args.store)
    hit = add_iso_hit(store, args.section, args.family, args.path, args.size, args.status, args.notes)
    atomic_write_json(args.store, store)
    print(f"Added/updated hit: {hit['path']} [{hit['status']}]")
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    store = load_for_write(args.store)
    hit = set_hit_status(store, args.section, args.family, args.path, args.status, args.notes)
    atomic_write_json(args.store, store)
    print(f"Set hit status: {hit['path']} [{hit['status']}]")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store, backup = load_store(args.store)
    if backup:
        print(f"Malformed JSON backed up to: {backup}")
    report = generate_report(store)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8", newline="\n")
        print(f"Wrote report: {args.out}")
    else:
        print(report, end="")
    return 0


def add_store_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE, help="Correlation JSON store path")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Manage Fragmenter section/family ISO correlation reviews.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="Create or normalize the correlation JSON store")
    add_store_arg(p)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("import-map", help="Import families from resource_map.json")
    p.add_argument("--map", type=Path, default=Path("resource_map.json"), help="Resource map JSON path")
    add_store_arg(p)
    p.set_defaults(func=cmd_import_map)

    p = sub.add_parser("add-hit", help="Add an ISO search hit to a section/family")
    p.add_argument("--section", required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--path", required=True, help="Internal ISO path for the hit")
    p.add_argument("--size", type=int)
    p.add_argument("--status", choices=STATUSES, default="unreviewed")
    p.add_argument("--notes")
    add_store_arg(p)
    p.set_defaults(func=cmd_add_hit)

    p = sub.add_parser("set-status", help="Set review status for an ISO hit")
    p.add_argument("--section", required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--path", required=True, help="Internal ISO path for the hit")
    p.add_argument("--status", choices=STATUSES, required=True)
    p.add_argument("--notes")
    add_store_arg(p)
    p.set_defaults(func=cmd_set_status)

    p = sub.add_parser("report", help="Generate a readable correlation report")
    p.add_argument("--out", type=Path)
    add_store_arg(p)
    p.set_defaults(func=cmd_report)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

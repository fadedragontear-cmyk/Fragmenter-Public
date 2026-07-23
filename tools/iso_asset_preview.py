#!/usr/bin/env python3
"""ISO 3D asset candidate scoring and preview report helpers."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
import binary_preview

HIGH_3D_EXTENSIONS = {".obj", ".mdl", ".mds", ".pmx", ".pmd", ".fbx", ".glb", ".gltf", ".stl"}
EXECUTABLE_EXTENSIONS = {".irx", ".elf", ".prg"}
VIDEO_EXTENSIONS = {".pss", ".mpeg", ".mpg"}
AUDIO_ARCHIVE_EXTENSIONS = {".adx", ".ads", ".aif", ".aiff", ".at3", ".bd", ".hd", ".msb", ".seq", ".vab", ".vag", ".vb", ".wav"}
MEDIUM_CONTAINER_EXTENSIONS = {".bin", ".ccs", ".cmp", ".dat", ".arc", ".pac"}
NEGATIVE_EXTENSIONS = {
    ".aif", ".aiff", ".at3", ".au", ".flac", ".m4a", ".mid", ".midi", ".mp3", ".ogg", ".wav", ".wma",
    ".bmp", ".dds", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".tga", ".tif", ".tiff", ".tm2", ".webp",
    ".asc", ".cfg", ".csv", ".htm", ".html", ".ini", ".json", ".log", ".md", ".nfo", ".rtf", ".srt", ".tsv", ".txt", ".xml", ".yaml", ".yml",
}
MODEL_HINTS = ("model", "mesh", "character", "char", "chr", "enemy", "mob", "npc", "player", "weapon", "armor", "field", "stage", "map", "town", "dungeon", "object", "obj", "parts")
CONTAINER_HINTS = ("asset", "archive", "pack", "resource", "res", "data", "ccs", "cmp")
NEGATIVE_HINTS = ("sound", "audio", "voice", "music", "movie", "video", "text", "font", "texture", "image", "icon", "splash", "manual")
AUDIO_PATH_HINTS = ("/voice/", "/bgm", "snddata", "sound", "audio", "music", "voice", "bgm")
FORCED_CONTAINER_PATHS = {
    "data/data.bin",
    "outside.bin",
    "stream/strcmn.bin",
    "data/icon.bin",
    "data/fgmt.bin",
    "data/kfaed.bin",
    "data/kfed.bin",
}


def _normalised_iso_path(path: str) -> str:
    return path.replace("\\", "/").lower().strip("/")


def _is_audio_archive_candidate(path: str, ext: str) -> bool:
    text = f"/{_normalised_iso_path(path)}"
    name = PurePosixPath(text).name
    return ext in AUDIO_ARCHIVE_EXTENSIONS or any(hint in text or hint in name for hint in AUDIO_PATH_HINTS)


def _is_forced_container_candidate(path: str) -> bool:
    text = _normalised_iso_path(path)
    return text in FORCED_CONTAINER_PATHS or any(text.endswith(f"/{forced}") for forced in FORCED_CONTAINER_PATHS)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _entry_path(entry: dict[str, Any]) -> str:
    return str(entry.get("path") or entry.get("name") or entry.get("iso_path") or "")


def _entry_size(entry: dict[str, Any]) -> int:
    try:
        return max(0, int(entry.get("size", entry.get("size_bytes", 0)) or 0))
    except (TypeError, ValueError):
        return 0


def _entry_lba(entry: dict[str, Any]) -> int | None:
    try:
        return int(entry["lba"]) if entry.get("lba") is not None else None
    except (TypeError, ValueError):
        return None


def _extension(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).suffix.lower()


def load_iso_index(index_path: str | Path) -> dict[str, Any]:
    """Load and lightly validate the JSON payload written by tools/iso_index.py."""
    path = Path(index_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"ISO index must be a JSON object: {path}")
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError(f"ISO index is missing a files list: {path}")
    return payload


def score_3d_candidate(entry: dict[str, Any]) -> dict[str, Any]:
    """Score an ISO index entry as a probable 3D model/container candidate."""
    reasons: list[str] = []
    path = _entry_path(entry)
    ext = _extension(path)
    size = _entry_size(entry)
    text = path.lower()
    score = 0

    if entry.get("is_dir"):
        score -= 100
        reasons.append("-100: directory entries cannot be previewed as 3D assets")

    forced_container = _is_forced_container_candidate(path)
    audio_archive = _is_audio_archive_candidate(path, ext)

    if ext in EXECUTABLE_EXTENSIONS:
        score -= 80
        reasons.append(f"-80: executable extension {ext} is treated as non-preview/non-3D by default")
    elif ext in VIDEO_EXTENSIONS:
        score -= 70
        reasons.append(f"-70: cutscene/video extension {ext} is not a model/container preview target")
    elif forced_container:
        score += 35
        reasons.append("+35: known bulk data path should be scanned as a container")
    elif audio_archive:
        score -= 55
        reasons.append("-55: path/name or extension suggests an audio archive/non-model asset")
    elif ext in HIGH_3D_EXTENSIONS:
        score += 70
        reasons.append(f"+70: high-confidence 3D model extension {ext}")
    elif ext in MEDIUM_CONTAINER_EXTENSIONS:
        score += 30
        reasons.append(f"+30: container/native candidate extension {ext}")
    elif ext in NEGATIVE_EXTENSIONS:
        score -= 60
        reasons.append(f"-60: obvious non-model extension {ext}")
    elif ext:
        score += 5
        reasons.append(f"+5: unknown binary-like extension {ext} kept as a weak candidate")
    else:
        score -= 5
        reasons.append("-5: missing extension makes format identification harder")

    model_hits = [hint for hint in MODEL_HINTS if hint in text]
    if model_hits:
        score += min(25, 8 * len(model_hits))
        reasons.append(f"+{min(25, 8 * len(model_hits))}: path/name contains 3D hints: {', '.join(model_hits[:5])}")
    container_hits = [hint for hint in CONTAINER_HINTS if hint in text]
    if container_hits and (ext in MEDIUM_CONTAINER_EXTENSIONS or forced_container):
        score += min(15, 5 * len(container_hits))
        reasons.append(f"+{min(15, 5 * len(container_hits))}: container path/name hints: {', '.join(container_hits[:5])}")
    negative_hits = [hint for hint in NEGATIVE_HINTS if hint in text]
    if negative_hits:
        score -= min(35, 10 * len(negative_hits))
        reasons.append(f"-{min(35, 10 * len(negative_hits))}: path/name suggests non-model data: {', '.join(negative_hits[:5])}")

    if size <= 0:
        score -= 45
        reasons.append("-45: empty or missing size")
    elif size < 128:
        score -= 25
        reasons.append(f"-25: very small file ({size} bytes) is unlikely to contain model data")
    elif size < 4096:
        score -= 8
        reasons.append(f"-8: small file ({size} bytes) is a weak 3D candidate")
    elif size <= 64 * 1024 * 1024:
        score += 10
        reasons.append(f"+10: plausible asset size ({size} bytes)")
    else:
        score -= 10
        reasons.append(f"-10: very large file ({size} bytes) is more likely a bulk archive/image")

    return {"score": score, "reasons": reasons}


def _confidence(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 35:
        return "medium"
    if score > 0:
        return "low"
    return "negative"


def _type_guess(ext: str, score: int, path: str = "") -> str:
    if ext in EXECUTABLE_EXTENSIONS:
        return "executable"
    if ext in VIDEO_EXTENSIONS:
        return "cutscene_video_candidate"
    if _is_forced_container_candidate(path):
        return "container_candidate"
    if _is_audio_archive_candidate(path, ext):
        return "audio_archive_candidate"
    if ext in MEDIUM_CONTAINER_EXTENSIONS:
        return "container_candidate"
    if ext in HIGH_3D_EXTENSIONS:
        return "model"
    if ext in NEGATIVE_EXTENSIONS:
        return "non_model"
    return "unknown_candidate" if score > 0 else "unknown"


def _next_action(type_guess: str) -> str:
    if type_guess == "model":
        return "Preview 3D"
    if type_guess == "container_candidate":
        return "Scan Inside Container"
    return "Metadata/Text-Hex"


def classify_iso_asset(entry: dict[str, Any]) -> dict[str, Any]:
    scored = score_3d_candidate(entry)
    path = _entry_path(entry)
    ext = _extension(path)
    score = int(scored["score"])
    type_guess = _type_guess(ext, score, path)
    return {
        "path": path,
        "extension": ext or "(none)",
        "size": _entry_size(entry),
        "lba": _entry_lba(entry),
        "score": score,
        "confidence": _confidence(score),
        "type_guess": type_guess,
        "next_action": _next_action(type_guess),
        "reasons": list(scored["reasons"]),
    }


def list_3d_candidates(index_payload: dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Classify and filter ISO files by extension, size, text, type guess, and confidence."""
    filters = filters or {}
    def _set_filter(*names: str) -> set[str]:
        for name in names:
            if name in filters and filters[name] is not None:
                value = filters[name]
                if isinstance(value, (str, bytes)):
                    return {str(value)}
                return {str(v) for v in value}
        return set()

    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in _set_filter("extensions", "extension")}
    type_guesses = _set_filter("type_guesses", "type_guess")
    confidences = _set_filter("confidences", "confidence")
    text = str(filters.get("text", filters.get("query", ""))).lower()
    min_size = filters.get("min_size")
    max_size = filters.get("max_size")
    rows = []
    for entry in index_payload.get("files", []):
        row = classify_iso_asset(entry)
        if exts and row["extension"] not in exts: continue
        if min_size is not None and row["size"] < int(min_size): continue
        if max_size is not None and row["size"] > int(max_size): continue
        if text and text not in row["path"].lower(): continue
        if type_guesses and row["type_guess"] not in type_guesses: continue
        if confidences and row["confidence"] not in confidences: continue
        rows.append(row)
    return sorted(rows, key=lambda r: (-int(r["score"]), str(r["path"]).lower()))


def safe_preview_output_path(workspace: str | Path, iso_internal_path: str) -> Path:
    """Return a traversal-safe extraction path under workspace/iso_preview/.

    ISO entries are expected to use POSIX-style relative paths.  If an entry
    contains traversal, absolute-path syntax, Windows drive prefixes, empty
    path components, alternate separators, or characters that need
    sanitization, the recognizable sanitized path is placed below a stable
    SHA1 directory so it cannot collide with a clean ISO path.
    """
    raw = str(iso_internal_path or "")
    split_parts = raw.split("/")
    has_empty_component = any(part == "" for part in split_parts)
    has_alternate_separator = "\\" in raw
    has_absolute_path = raw.startswith("/") or PureWindowsPath(raw).is_absolute()
    has_windows_drive = PureWindowsPath(raw).drive != ""
    has_traversal = any(part in (".", "..") for part in split_parts)
    unsafe = (
        not raw
        or has_empty_component
        or has_alternate_separator
        or has_absolute_path
        or has_windows_drive
        or has_traversal
    )

    recognizable_parts = [part for part in re.split(r"[/\\]+", raw) if part not in ("", ".", "..")]
    safe_parts = [re.sub(r"[^A-Za-z0-9._-]+", "_", part).strip("._") or "_" for part in recognizable_parts]
    sanitization_changed = safe_parts != recognizable_parts
    if unsafe or sanitization_changed or not safe_parts:
        digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
        safe_parts = [f"unsafe_{digest}", *(safe_parts or ["entry"])]
    base = (Path(workspace).expanduser() / "iso_preview").resolve()
    target = (base.joinpath(*safe_parts)).resolve()
    if target != base and base not in target.parents:
        digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
        target = (base / f"unsafe_{digest}" / (safe_parts[-1] if safe_parts else "entry")).resolve()
    if target == base or (base not in target.parents):
        raise ValueError(f"Unsafe ISO preview output path: {iso_internal_path!r}")
    return target


def _safe_path_component(value: str, *, fallback: str = "_") -> str:
    """Return a readable single path component with unsafe characters replaced."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("._")
    return safe or fallback


def _embedded_candidate_type(candidate: dict[str, Any]) -> str:
    raw = str(candidate.get("type") or candidate.get("kind") or "unknown").lower()
    if "ccsf" in raw:
        return "ccsf"
    if "tim2" in raw or "tm2" in raw:
        return "tim2"
    if "gzip" in raw or raw == "gz":
        return "gzip"
    return _safe_path_component(raw, fallback="unknown").lower()


def safe_embedded_preview_output_dir(workspace: str | Path, container_path: str | Path) -> Path:
    """Return a traversal-safe embedded-preview directory for a container.

    The base is always ``workspace/upload_package/iso_preview_embedded/``.
    Container directories keep a readable sanitized stem and append a stable
    SHA1 prefix from the full container path so similarly named containers do
    not collide.
    """
    raw = str(container_path or "")
    base = (Path(workspace).expanduser() / "upload_package" / "iso_preview_embedded").resolve()
    stem = _safe_path_component(Path(raw).stem, fallback="container")
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
    target = (base / f"{stem}_{digest}").resolve()
    if target == base or base not in target.parents:
        raise ValueError(f"Unsafe embedded preview output directory: {container_path!r}")
    return target


def safe_embedded_candidate_output_path(
    workspace: str | Path,
    container_path: str | Path,
    candidate: dict[str, Any],
) -> Path:
    """Return a safe embedded candidate output path using offset and type.

    Filenames are deterministic and readable, e.g. ``00001234_gzip.bin`` or
    ``0000ABCD_ccsf.bin``.
    """
    try:
        offset = max(0, int(candidate.get("offset", 0) or 0))
    except (TypeError, ValueError):
        offset = 0
    type_name = _embedded_candidate_type(candidate)
    target = (safe_embedded_preview_output_dir(workspace, container_path) / f"{offset:08X}_{type_name}.bin").resolve()
    base = (Path(workspace).expanduser() / "upload_package" / "iso_preview_embedded").resolve()
    if target == base or base not in target.parents:
        raise ValueError(f"Unsafe embedded preview output path: {container_path!r}")
    return target


def _sha1_file(path: str | Path | None) -> str | None:
    if not path:
        return None
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        return None
    h = hashlib.sha1()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _report_entry_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("iso_path") or ""),
        str(row.get("internal_iso_path") or row.get("path") or ""),
        "" if row.get("lba") is None else str(row.get("lba")),
    )


def _normalise_embedded_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return a stable embedded-candidate record for JSON/text reports."""
    extracted = candidate.get("extracted") if isinstance(candidate.get("extracted"), dict) else {}
    probe = candidate.get("probe") if isinstance(candidate.get("probe"), dict) else {}
    try:
        offset = int(candidate.get("offset", 0) or 0)
    except (TypeError, ValueError):
        offset = 0
    nearby = candidate.get("nearby_strings") if isinstance(candidate.get("nearby_strings"), list) else []
    extracted_path = candidate.get("extracted_path") or extracted.get("path")
    extracted_sha1 = candidate.get("extracted_sha1") or extracted.get("sha1") or _sha1_file(extracted_path)
    preview_status = (
        candidate.get("preview_status")
        or candidate.get("preview_result")
        or ("extracted" if extracted_path else "candidate")
    )
    probe_summary = candidate.get("probe_summary")
    if probe_summary is None and probe:
        probe_summary = {
            key: probe.get(key)
            for key in ("detected_type", "format_name", "size", "sha1", "warnings", "chain")
            if key in probe
        }
    normalised = {
        "offset": offset,
        "type": str(candidate.get("type") or candidate.get("kind") or "unknown"),
        "magic": str(candidate.get("magic") or candidate.get("magic_hex") or ""),
        "nearby_strings": [str(value) for value in nearby],
        "likely_role": str(candidate.get("likely_role") or "unknown"),
        "extracted_path": str(extracted_path) if extracted_path else None,
        "extracted_sha1": extracted_sha1,
        "preview_status": str(preview_status),
    }
    if probe_summary:
        normalised["probe_summary"] = probe_summary
    return normalised

def _normalise_report_entry(entry: dict[str, Any]) -> dict[str, Any]:
    source = classify_iso_asset(entry) if "confidence" not in entry else dict(entry)
    probe = dict(source.get("probe") or {})
    extracted_path = source.get("extracted_path")
    signature = source.get("signature_bytes") or probe.get("signature_hex") or None
    guessed = source.get("guessed_format") or probe.get("format_name") or source.get("type_guess") or "Unknown/custom format"
    preview_result = source.get("preview_result") or source.get("preview_status") or ("extracted" if extracted_path else "candidate")
    reasons = source.get("reason_strings", source.get("reasons", [])) or []
    if isinstance(reasons, (str, bytes)):
        reasons = [str(reasons)]
    embedded_summary = source.get("embedded_candidate_summary") if isinstance(source.get("embedded_candidate_summary"), dict) else {}
    embedded_candidates_source = source.get("embedded_candidates")
    if not isinstance(embedded_candidates_source, list):
        embedded_candidates_source = (
            embedded_summary.get("embedded_candidates")
            if isinstance(embedded_summary.get("embedded_candidates"), list)
            else []
        )
    embedded_candidates = [
        _normalise_embedded_candidate(candidate)
        for candidate in embedded_candidates_source
        if isinstance(candidate, dict)
    ]

    preview_candidate = source.get("embedded_candidate_preview") if isinstance(source.get("embedded_candidate_preview"), dict) else {}
    if preview_candidate:
        normalised_preview = _normalise_embedded_candidate(preview_candidate)
        preview_offset = normalised_preview.get("offset")
        for index, candidate in enumerate(embedded_candidates):
            if candidate.get("offset") == preview_offset and candidate.get("type") == normalised_preview.get("type"):
                merged = dict(candidate)
                merged.update({key: value for key, value in normalised_preview.items() if value not in (None, "", [])})
                embedded_candidates[index] = merged
                break
        else:
            embedded_candidates.append(normalised_preview)

    scan_inside_container = source.get("scan_inside_container")
    if scan_inside_container is None:
        scan_inside_container = bool(embedded_summary) or bool(embedded_candidates)
    embedded_candidate_count = source.get("embedded_candidate_count")
    if embedded_candidate_count is None:
        embedded_candidate_count = embedded_summary.get(
            "embedded_count",
            embedded_summary.get("candidate_count", len(embedded_candidates)),
        )
    try:
        embedded_candidate_count = int(embedded_candidate_count or 0)
    except (TypeError, ValueError):
        embedded_candidate_count = len(embedded_candidates)

    normalised = {
        "iso_path": str(source.get("iso_path") or ""),
        "internal_iso_path": str(source.get("internal_iso_path") or source.get("path") or ""),
        "lba": _entry_lba(source),
        "size": _entry_size(source),
        "extracted_path": str(extracted_path) if extracted_path else None,
        "extracted_sha1": source.get("extracted_sha1") or _sha1_file(extracted_path),
        "signature_bytes": signature,
        "guessed_format": guessed,
        "preview_result": preview_result,
        "confidence": str(source.get("confidence") or "unknown"),
        "reason_strings": [str(reason) for reason in reasons],
        "timestamp": str(source.get("timestamp") or source.get("reported_at") or _utc_now_iso()),
        "scan_inside_container": bool(scan_inside_container),
        "embedded_candidate_count": embedded_candidate_count,
        "embedded_candidates": embedded_candidates,
        "embedded_report_updated_at": (
            str(source.get("embedded_report_updated_at") or source.get("timestamp") or source.get("reported_at") or _utc_now_iso())
            if bool(scan_inside_container) or embedded_candidates
            else None
        ),
    }
    if embedded_summary:
        summary_copy = dict(embedded_summary)
        summary_copy["embedded_candidates"] = embedded_candidates
        summary_copy["embedded_count"] = embedded_candidate_count
        normalised["embedded_candidate_summary"] = summary_copy
    return normalised


def build_iso_preview_summary(
    entry: dict[str, Any],
    extracted_path: str | Path | None = None,
    probe: dict[str, Any] | None = None,
    *,
    iso_path: str | Path | None = None,
    preview_result: str | None = None,
) -> dict[str, Any]:
    summary = classify_iso_asset(entry) if "confidence" not in entry else dict(entry)
    if iso_path is not None:
        summary["iso_path"] = str(iso_path)
    summary.update({
        "internal_iso_path": str(summary.get("internal_iso_path") or summary.get("path") or ""),
        "extracted_path": str(extracted_path) if extracted_path is not None else summary.get("extracted_path"),
        "probe": probe or summary.get("probe") or {},
        "preview_result": preview_result or summary.get("preview_result") or ("extracted" if extracted_path else "candidate"),
        "timestamp": _utc_now_iso(),
    })
    return _normalise_report_entry(summary)


def _bounded_int(value: int | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _extracted_by_offset(extracted: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_offset: dict[int, dict[str, Any]] = {}
    for row in extracted:
        try:
            offset = int(row.get("offset"))
        except (TypeError, ValueError):
            continue
        by_offset[offset] = row
    return by_offset


def classify_embedded_candidate(container_path: str | Path, candidate: dict[str, Any]) -> dict[str, Any]:
    """Normalize a binary_preview embedded candidate and assign a likely asset role."""
    type_name = str(candidate.get("type") or candidate.get("kind") or "unknown")
    magic_hex = str(candidate.get("magic_hex") or candidate.get("magic") or "")
    nearby = candidate.get("nearby_strings") if isinstance(candidate.get("nearby_strings"), list) else []
    nearby_strings = [str(value) for value in nearby]
    text = " ".join([type_name, magic_hex, *nearby_strings]).lower()

    if "ccsf" in text:
        likely_role = "container"
        normalized_type = "CCSF"
    elif "tim2" in text or "tm2" in text or "png" in text or "bmp" in text:
        likely_role = "texture"
        normalized_type = type_name
    elif "gzip" in text:
        likely_role = "compressed container"
        normalized_type = type_name
    elif "pss" in text or "mpeg" in text or "00 00 01 ba" in text or "00 00 01 b3" in text:
        likely_role = "cutscene/video"
        normalized_type = type_name
    elif "vag" in text or "wav" in text or "riff" in text:
        likely_role = "audio"
        normalized_type = type_name
    elif any(hint in text for hint in ("anim", "motion")):
        likely_role = "animation"
        normalized_type = type_name
    elif any(hint in text for hint in ("model", "mesh", "obj", "stage", "field", "chr", "npc")):
        likely_role = "model-ish"
        normalized_type = type_name
    else:
        likely_role = "unknown"
        normalized_type = type_name

    extracted = candidate.get("extracted") if isinstance(candidate.get("extracted"), dict) else {}
    extracted_path = candidate.get("extracted_path") or extracted.get("path")
    try:
        offset = int(candidate.get("offset", 0) or 0)
    except (TypeError, ValueError):
        offset = 0
    return {
        "container_path": str(container_path),
        "offset": offset,
        "type": normalized_type,
        "magic": magic_hex,
        "nearby_strings": nearby_strings,
        "likely_role": likely_role,
        "extracted_path": str(extracted_path) if extracted_path else None,
        "extracted_sha1": candidate.get("extracted_sha1") or extracted.get("sha1") or _sha1_file(extracted_path),
        "preview_status": "extracted" if extracted_path else "candidate",
    }


def scan_extracted_container_for_preview(
    path: str | Path,
    workspace: str | Path,
    max_scan_bytes: int,
    extract_cap: int,
) -> dict[str, Any]:
    """Run binary_preview.scan_container with conservative ISO-preview bounds."""
    scan_path = Path(path)
    extract_dir = safe_embedded_preview_output_dir(workspace, scan_path)
    args = argparse.Namespace(
        max_scan_bytes=_bounded_int(max_scan_bytes, 16 * 1024 * 1024, 0, 256 * 1024 * 1024),
        extract_cap=_bounded_int(extract_cap, 8 * 1024 * 1024, 0, 64 * 1024 * 1024),
        scan_chunk=_bounded_int(binary_preview.DEFAULT_SCAN_CHUNK, binary_preview.DEFAULT_SCAN_CHUNK, 64 * 1024, 4 * 1024 * 1024),
        scan_overlap=_bounded_int(binary_preview.DEFAULT_SCAN_OVERLAP, binary_preview.DEFAULT_SCAN_OVERLAP, 256, 64 * 1024),
        max_candidates=200,
        nearby_radius=512,
        nearby_strings=12,
        max_strings=250,
        max_paths=100,
        string_scan_cap=min(_bounded_int(max_scan_bytes, 16 * 1024 * 1024, 0, 64 * 1024 * 1024), binary_preview.DEFAULT_STRING_SCAN_CAP),
        max_symbols=100,
        extract_candidates=True,
        extract_dir=str(extract_dir),
        candidate_offset=None,
        candidate_type=None,
    )
    report = binary_preview.scan_container(scan_path, args)
    extracted_records = [dict(row) for row in report.get("extracted", []) if isinstance(row, dict)]
    for row in extracted_records:
        source_path = Path(str(row.get("path") or ""))
        if not source_path.is_file():
            continue
        safe_path = safe_embedded_candidate_output_path(workspace, scan_path, row)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() != safe_path:
            source_path.replace(safe_path)
        row["path"] = str(safe_path)
    extracted_offsets = _extracted_by_offset(extracted_records)
    embedded_candidates = []
    for candidate in report.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        normalized_candidate = dict(candidate)
        try:
            offset = int(normalized_candidate.get("offset", 0) or 0)
        except (TypeError, ValueError):
            offset = 0
        if offset in extracted_offsets:
            normalized_candidate["extracted"] = extracted_offsets[offset]
            normalized_candidate["extracted_path"] = extracted_offsets[offset].get("path")
        embedded_candidates.append(classify_embedded_candidate(scan_path, normalized_candidate))

    return {
        "container_path": str(report.get("path") or scan_path),
        "scanned_bytes": int(report.get("scanned_bytes") or 0),
        "candidate_count": int(report.get("candidate_count") or 0),
        "candidate_cap_hit": bool(report.get("candidate_cap_hit")),
        "symbols": report.get("symbols") if isinstance(report.get("symbols"), dict) else {},
        "strings": report.get("strings") if isinstance(report.get("strings"), dict) else {},
        "extracted": extracted_records,
        "embedded_candidates": embedded_candidates,
    }


def build_embedded_candidate_summary(
    iso_candidate: dict[str, Any],
    extracted_container_path: str | Path | None,
    scan_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a metadata-only ISO preview entry with embedded-candidate scan results."""
    base = build_iso_preview_summary(
        iso_candidate,
        extracted_path=extracted_container_path,
        preview_result="embedded_scan_complete" if scan_result else "embedded_scan_unavailable",
    )
    embedded = scan_result.get("embedded_candidates", []) if isinstance(scan_result, dict) else []
    base["scan_inside_container"] = True
    base["embedded_candidate_count"] = len(embedded)
    base["embedded_candidates"] = [dict(row) for row in embedded if isinstance(row, dict)]
    base["embedded_report_updated_at"] = _utc_now_iso()
    base["embedded_candidate_summary"] = {
        "iso_candidate": {
            "internal_iso_path": base.get("internal_iso_path"),
            "lba": base.get("lba"),
            "size": base.get("size"),
            "confidence": base.get("confidence"),
            "type_guess": iso_candidate.get("type_guess"),
        },
        "extracted_container_path": str(extracted_container_path) if extracted_container_path else None,
        "scan_status": "complete" if scan_result else "unavailable",
        "embedded_count": len(embedded),
        "embedded_candidates": [dict(row) for row in embedded if isinstance(row, dict)],
    }
    if isinstance(scan_result, dict):
        base["embedded_candidate_summary"].update({
            "scanned_bytes": int(scan_result.get("scanned_bytes") or 0),
            "candidate_count": int(scan_result.get("candidate_count") or 0),
            "candidate_cap_hit": bool(scan_result.get("candidate_cap_hit")),
        })
    return base


def _text_report(report: dict[str, Any]) -> str:
    lines = ["ISO 3D Preview Report", f"Updated: {report.get('updated_at')}", f"Entries: {len(report.get('entries', []))}", ""]
    for row in report.get("entries", []):
        lines.append(f"- {row.get('internal_iso_path')} [{row.get('confidence')}] size={row.get('size')} lba={row.get('lba')}")
        lines.append(f"  * ISO: {row.get('iso_path') or '(unknown)'}")
        lines.append(f"  * extracted: {row.get('extracted_path') or '(not extracted)'}")
        lines.append(f"  * extracted SHA1: {row.get('extracted_sha1') or '(unavailable)'}")
        lines.append(f"  * signature bytes: {row.get('signature_bytes') or '(unavailable)'}")
        lines.append(f"  * guessed format: {row.get('guessed_format') or '(unknown)'}")
        lines.append(f"  * preview result: {row.get('preview_result') or '(unknown)'}")
        lines.append(f"  * timestamp: {row.get('timestamp')}")
        for reason in row.get("reason_strings", []):
            lines.append(f"  * reason: {reason}")
        embedded = row.get("embedded_candidate_summary") if isinstance(row.get("embedded_candidate_summary"), dict) else {}
        candidates = [cand for cand in row.get("embedded_candidates", []) if isinstance(cand, dict)]
        if not candidates and embedded:
            candidates = [cand for cand in embedded.get("embedded_candidates", []) if isinstance(cand, dict)]
        if row.get("scan_inside_container") or embedded or candidates:
            lines.append(f"  * scan inside container: {row.get('scan_inside_container')}")
            lines.append(f"  * embedded report updated: {row.get('embedded_report_updated_at') or '(unknown)'}")
            if embedded:
                lines.append(f"  * embedded scan status: {embedded.get('scan_status') or '(unknown)'}")
                lines.append(f"  * embedded scanned bytes: {embedded.get('scanned_bytes', 0)}")
            lines.append(f"  * embedded candidates: {row.get('embedded_candidate_count', len(candidates))}")
            if candidates:
                lines.append("  * embedded candidate summary:")
                for cand in candidates[:50]:
                    try:
                        offset = int(cand.get("offset", 0) or 0)
                    except (TypeError, ValueError):
                        offset = 0
                    lines.append(
                        f"    - offset=0x{offset:08X} type={cand.get('type') or 'unknown'} "
                        f"magic={cand.get('magic') or '(unavailable)'} role={cand.get('likely_role') or 'unknown'} "
                        f"preview={cand.get('preview_status') or 'candidate'}"
                    )
                    if cand.get("extracted_path"):
                        lines.append(f"      extracted: {cand.get('extracted_path')}")
                    if cand.get("extracted_sha1"):
                        lines.append(f"      extracted SHA1: {cand.get('extracted_sha1')}")
                    nearby = cand.get("nearby_strings") if isinstance(cand.get("nearby_strings"), list) else []
                    if nearby:
                        lines.append(f"      nearby strings: {', '.join(str(value) for value in nearby[:5])}")
                    if cand.get("probe_summary"):
                        lines.append(f"      probe summary: {cand.get('probe_summary')}")
                if len(candidates) > 50:
                    lines.append(f"    - ... {len(candidates) - 50} more candidate(s)")
            else:
                lines.append("  * no embedded signatures found in scanned range")
    return "\n".join(lines).rstrip() + "\n"


def write_iso_preview_report(workspace: str | Path, entries: list[dict[str, Any]] | dict[str, Any], *, append: bool = True) -> dict[str, Path]:
    """Write deterministic ISO 3D preview JSON and text reports under workspace/reports/."""
    reports = Path(workspace).expanduser() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / "iso_3d_preview_report.json"
    txt_path = reports / "iso_3d_preview_report.txt"
    new_entries = entries if isinstance(entries, list) else [entries]
    if append and json_path.is_file():
        try:
            report = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {"entries": []}
        if not isinstance(report, dict):
            report = {"entries": []}
    else:
        report = {"entries": []}

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in report.get("entries", []):
        if isinstance(row, dict):
            normalised = _normalise_report_entry(row)
            by_key[_report_entry_key(normalised)] = normalised
    for row in new_entries:
        normalised = _normalise_report_entry(row)
        by_key[_report_entry_key(normalised)] = normalised

    report["entries"] = [by_key[key] for key in sorted(by_key, key=lambda k: (k[0].lower(), k[1].lower(), k[2]))]
    report["updated_at"] = _utc_now_iso()
    report["entry_count"] = len(report["entries"])
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    txt_path.write_text(_text_report(report), encoding="utf-8", newline="\n")
    return {"json": json_path, "text": txt_path}

def grouped_candidates_text(candidates: list[dict[str, Any]], *, index_path: str | Path, limit: int) -> str:
    """Build a stable, human-readable candidate summary grouped by confidence."""
    lines = [
        "ISO 3D Candidate Summary",
        f"Index: {index_path}",
        f"Limit: {limit}",
        f"Candidates: {len(candidates)}",
        "",
    ]
    for confidence in ("high", "medium", "low", "negative"):
        group = [row for row in candidates if row.get("confidence") == confidence]
        lines.append(f"{confidence.upper()} ({len(group)})")
        if not group:
            lines.append("  (none)")
        for row in group:
            lines.append(
                f"  - {row.get('path')} "
                f"[{row.get('type_guess')}] score={row.get('score')} "
                f"size={row.get('size')} lba={row.get('lba')} "
                f"next={row.get('next_action')}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="List likely 3D asset candidates from a JSON ISO index.")
    ap.add_argument("--index", required=True, help="Path to JSON index written by iso_index.py")
    ap.add_argument("--out", required=True, help="Output JSON candidate list")
    ap.add_argument("--text-out", help="Optional readable grouped text summary")
    ap.add_argument("--limit", type=int, default=500, help="Maximum candidates to write")
    args = ap.parse_args()

    if args.limit < 0:
        ap.error("--limit must be non-negative")

    payload = load_iso_index(args.index)
    candidates = list_3d_candidates(payload)[: args.limit]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.text_out:
        text_path = Path(args.text_out)
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(
            grouped_candidates_text(candidates, index_path=args.index, limit=args.limit),
            encoding="utf-8",
            newline="\n",
        )

    print(f"Wrote {len(candidates)} ISO 3D candidates to {out_path}")
    if args.text_out:
        print(f"Wrote ISO 3D candidate summary to {args.text_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

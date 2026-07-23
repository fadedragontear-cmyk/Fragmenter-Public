#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import hashlib
import importlib.util
import json
import os
import subprocess
import threading
import platform
import zipfile
import sys
import queue
import time
import re
import shlex
import shutil
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox, simpledialog

from model_preview_probe import probe_model_asset
from iso_asset_preview import build_embedded_candidate_summary, build_iso_preview_summary, list_3d_candidates, safe_preview_output_path, scan_extracted_container_for_preview, write_iso_preview_report
from preview_3d import Mesh, create_mesh_viewer, create_obj_viewer
from preview_helpers import IMAGE_EXTS, suggested_iso_queries
from preview_texture import (
    SUPPORTED_EXTENSIONS as TEXTURE_PREVIEW_EXTENSIONS,
    extract_metadata as extract_texture_metadata,
    metadata_text as texture_metadata_text,
    render_texture_window,
)
from resource_queries import derive_family_search_terms
from ccs_explain import explain_identifier
from ccsf_asset_indexer import format_index as format_ccsf_asset_index, index_folder as index_ccsf_asset_folder
from asset_library import build_asset_library, format_library as format_ccsf_asset_library
from audio_playback import AudioPlaybackEngine
import audio_decoder
from ccsf_preview_manifest import build_manifest as build_ccsf_preview_manifest, format_text as format_ccsf_preview_manifest_text
from correlation_store import (
    STATUSES as CORRELATION_STATUSES,
    atomic_write_json,
    add_iso_hit,
    find_hit,
    generate_report,
    import_resource_map,
    import_binary_preview,
    load_store,
    set_hit_status,
)
from fragment_core import split_sections
from fragmenter_containers import read_members
from fragmenter_project import (
    FragmenterProjectState,
    add_safe_note_to_current_patch_plan,
    inspect_area_server_root,
    inspect_iso,
    list_extracted_assets,
    list_reports,
)
import ccsf_structure_decoder
from raw_audio_probe import ENCODINGS, SAMPLE_RATES, RawInterpretation, analyze_raw_audio, export_wav, generate_region_map, probe_candidates, write_region_reports
from snddata_editor import SnddataEditor
from viewer_plugins import (
    DEFAULT_ARGS_TEMPLATE,
    LEGACY_VIEWER_NAME,
    ViewerConfig,
    build_viewer_command,
    load_settings,
    parse_extensions,
    update_settings_with_viewers,
    viewers_from_settings,
)

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
PY = sys.executable
APP_SETTINGS_PATH = ROOT / "fragmenter_gui_settings.json"
WORKSPACE = ROOT / "workspace"
TMP_WORKSPACE = WORKSPACE / "tmp"
REPORTS_WORKSPACE = WORKSPACE / "reports"
CELDRA_FRAME_DIR = ROOT / "assets" / "celdra"
APP_TITLE = "Fragmenter v0.9.24"
FRAGMENT_STRINGS_SHEETS = {
    "Patches": ("Patches",),
    "Boss": ("Boss", "BossText"),
    "Guild": ("Guild", "GuildText"),
    "ShopDialogue": ("ShopDialogue", "ShopDialogueText"),
    "CharacterName": ("CharacterName", "CharacterNameText"),
    "Item": ("Item", "ItemText"),
    "Equipment": ("Equipment", "EquipmentText"),
    "Skill": ("Skill", "SkillText"),
}
FRAGMENT_STRINGS_CLIENT_IDS = ("EQUIPSHOP", "ITEMSHOP", "MAGICSHOP", "FAIRYSHOP", "RECORDER", "BREEDER")
FRAGMENT_STRINGS_ROOT_TOWN_CROSSLINKS = {
    "sr4wep1": ("EQUIPSHOP",),
    "sr4ite1": ("ITEMSHOP",),
    "sr4mag1": ("MAGICSHOP",),
    "sr4sav1": ("RECORDER",),
    "sr4fai1": ("FAIRYSHOP", "BREEDER"),
}



WORKFLOW_PAGE_LABELS = (
    "Setup / Scan",
    "3D Asset Viewer",
    "Textures / Images",
    "Audio",
    "Server Tools",
    "More",
)

MORE_PAGE_LABELS = (
    "Asset Library",
    "Reports",
    "Settings / Legacy",
)

PREPARATION_STEP_STATES = (
    "Queued",
    "Running",
    "Reused",
    "Updated",
    "Extracted",
    "Decoded",
    "Partial",
    "Failed",
    "Skipped",
    "Cancelled",
)

FULL_DISC_PREPARATION_STEPS = (
    "Workspace Check",
    "Reuse / Extract CCSF Library",
    "Rebuild Asset Library if CCSF Changed",
    "Extract Known Media Targets",
    "Decode Known EFF Sound Bank",
    "Reuse BGM / FOOD Maps",
    "Focused SNDDATA Structural Analysis",
    "Refresh 3D and Audio Views",
)

DEEP_DISC_DISCOVERY_STEPS = (
    "Survey ISO Assets",
    "Full Inventory Refresh",
    "Extract Media Candidates",
    "Decode / Prepare Images",
    "Scan / Decode Audio",
    "Analyze SNDDATA Music",
    "Refresh Reports / Setup Checklist",
)

RUN_ALL_CONFIRMATION_TEXT = (
    "Runs focused known-target preparation only: workspace check, CCSF reuse/extraction, conditional asset library "
    "refresh, direct known media extraction, known EFF decode, BGM/FOOD map reuse, SNDDATA analysis, and view refresh."
)

DEEP_DISC_DISCOVERY_CONFIRMATION_TEXT = (
    "Runs explicit deep disc discovery: --scan-all-bytes inventory, gzip discovery, embedded signature discovery, "
    "unknown container survey, and full inventory refresh. This can take significantly longer than RUN ALL."
)

KNOWN_MEDIA_TARGETS = (
    "DATA/SNDDATA.BIN",
    "VOICE/BGM.BIN",
    "VOICE/FOOD.BIN",
    "NETGUI/EFF.HD",
    "NETGUI/EFF.BD",
)

PROJECT_SETTINGS_KEYS = (
    "iso_path",
    "area_server_root_path",
    "workspace_path",
    "data_folder_path",
    "save_folder_path",
)

CCSF_ASSET_SELECTION_DETAIL_DELAY_MS = 0
CCSF_ASSET_SELECTION_BUILDS_MANIFEST = False


def load_ccsf_asset_library_data(path: Path) -> dict:
    """Load an asset_library.json-like file for headless tests and GUI flows."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ccsf_asset_matches_query(asset: dict, query: str) -> bool:
    """Return whether an asset matches the 3D Asset Viewer free-text query."""
    tokens = query.strip().lower().split()
    if not tokens:
        return True
    haystack = " ".join(
        str(asset.get(key) or "")
        for key in ("display_name", "name", "type", "variant", "readiness", "preferred_file", "relative_file", "file")
    ).lower()
    return all(token in haystack for token in tokens)


def filter_ccsf_assets_for_viewer(library: dict, query: str = "") -> list[dict]:
    """Filter asset_library.json-like data using the viewer's free-text search rules."""
    return [asset for asset in list((library or {}).get("assets") or []) if ccsf_asset_matches_query(asset, query)]


def build_ccsf_model_decode_command(asset_file: Path, workspace: Path, py: str = PY, root: Path = ROOT) -> tuple[list[str], Path, Path, Path]:
    """Build the default CCS structure parse command without requiring a display-backed app."""
    asset_file = Path(asset_file)
    workspace = Path(workspace)
    out_dir = workspace / "model_previews"
    reports_dir = workspace / "reports"
    report = reports_dir / f"{asset_file.stem}_model_decode.json"
    text_report = reports_dir / f"{asset_file.stem}_model_decode.txt"
    return (
        [
            py,
            str(Path(root) / "fragmenter.py"),
            "decode-ccsf-model",
            str(asset_file),
            "--out-dir",
            str(out_dir),
            "--report",
            str(report),
            "--text-out",
            str(text_report),
        ],
        out_dir,
        report,
        text_report,
    )


def discover_model_preview_objs(workspace: Path, stem: str) -> list[Path]:
    """Discover OBJ files below workspace/model_previews/<stem>/obj."""
    obj_dir = Path(workspace) / "model_previews" / stem / "obj"
    return sorted(obj_dir.glob("*.obj")) if obj_dir.is_dir() else []


def collect_structural_rigid_gen1_submodels(report: dict) -> list[dict]:
    """Return confirmed structural rigid submodels that contain previewable geometry."""
    meshes: list[dict] = []
    for rec in (report or {}).get("records") or []:
        model = rec.get("model") if isinstance(rec, dict) else None
        if not isinstance(model, dict):
            continue
        model_name = str(rec.get("object_name") or model.get("model_object_name") or "")
        for sub in model.get("submodels") or []:
            if not isinstance(sub, dict):
                continue
            vertices = sub.get("vertices") or []
            faces = sub.get("faces") or []
            if sub.get("parser_mode") != "structural_rigid_gen1" or not vertices or not faces:
                continue
            meshes.append({"record": rec, "model": model, "submodel": sub, "model_object_name": model_name})
    return meshes


def choose_structural_preview_submodel(report: dict) -> dict | None:
    """Choose the best confirmed structural mesh for the 3D Asset Viewer."""
    candidates = collect_structural_rigid_gen1_submodels(report)
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.get("model_object_name") == "MDL_caurbody1":
            return candidate
    for candidate in candidates:
        name = str(candidate.get("model_object_name") or "").lower()
        if "shadow" not in name:
            return candidate
    return candidates[0]


def _mesh_preview_numeric_vector(value: object, minimum_length: int) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) < minimum_length:
        return None
    values: list[float] = []
    for component in value[:minimum_length]:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            return None
        values.append(float(component))
    return tuple(values)


def _mesh_preview_extract_vector(
    entry: object,
    *,
    dict_key: str,
    minimum_length: int,
    label: str,
    index: int,
    warnings: list[str],
) -> tuple[float, ...] | None:
    value = entry.get(dict_key) if isinstance(entry, dict) else entry
    vector = _mesh_preview_numeric_vector(value, minimum_length)
    if vector is None:
        warnings.append(f"Skipped invalid {label} entry {index}: expected {minimum_length}+ numeric values")
    return vector


def _mesh_preview_vertex(entry: object, index: int, warnings: list[str]) -> tuple[float, float, float] | None:
    vector = _mesh_preview_extract_vector(entry, dict_key="position", minimum_length=3, label="vertex", index=index, warnings=warnings)
    return vector if vector is None else (vector[0], vector[1], vector[2])


def _mesh_preview_normal(entry: object, index: int, warnings: list[str]) -> tuple[float, float, float] | None:
    vector = _mesh_preview_extract_vector(entry, dict_key="normal", minimum_length=3, label="normal", index=index, warnings=warnings)
    return vector if vector is None else (vector[0], vector[1], vector[2])


def _mesh_preview_uv(entry: object, index: int, warnings: list[str]) -> tuple[float, float] | None:
    vector = _mesh_preview_extract_vector(entry, dict_key="uv", minimum_length=2, label="uv", index=index, warnings=warnings)
    return vector if vector is None else (vector[0], vector[1])


def _mesh_preview_color(entry: object, index: int, warnings: list[str]) -> tuple[float, float, float, float] | None:
    vector = _mesh_preview_extract_vector(entry, dict_key="color", minimum_length=4, label="vertex color", index=index, warnings=warnings)
    return vector if vector is None else (vector[0], vector[1], vector[2], vector[3])


def mesh_from_structural_preview_submodel(candidate: dict | None) -> Mesh:
    """Build a Mesh from one confirmed structural submodel candidate."""
    if not candidate:
        return Mesh(source_metadata={"source_format": "ccsf_structure_decoder", "warnings": ["No structurally confirmed mesh decoded."], "errors": []})
    sub = candidate["submodel"]
    warnings = list(sub.get("warnings") or [])
    vertices = [
        vertex
        for index, entry in enumerate(sub.get("vertices") or [])
        if (vertex := _mesh_preview_vertex(entry, index, warnings)) is not None
    ]
    normals = [
        normal
        for index, entry in enumerate(sub.get("normals") or [])
        if (normal := _mesh_preview_normal(entry, index, warnings)) is not None
    ]
    uvs = [
        uv
        for index, entry in enumerate(sub.get("uvs") or [])
        if (uv := _mesh_preview_uv(entry, index, warnings)) is not None
    ]
    vertex_colors = [
        color
        for index, entry in enumerate(sub.get("vertex_colors") or [])
        if (color := _mesh_preview_color(entry, index, warnings)) is not None
    ]
    faces = [[int(i) for i in face[:3]] for face in (sub.get("faces") or []) if len(face) >= 3]
    return Mesh(
        vertices=vertices,
        faces=faces,
        normals=normals,
        uvs=uvs,
        vertex_colors=vertex_colors,
        material_id=sub.get("mat_tex_id"),
        source_metadata={
            "source_format": "ccsf_structure_decoder",
            "names": [candidate.get("model_object_name") or "structural submodel"],
            "warnings": warnings,
            "errors": [],
            "parser_mode": sub.get("parser_mode"),
            "submodel_index": sub.get("index"),
        },
    )



AUDIO_REPORT_RELATIVE_PATHS = (
    Path("reports/iso_audio_inventory.json"),
    Path("reports/iso_audio_decode_report.json"),
    Path("media_pipeline/reports/iso_audio_inventory.json"),
    Path("media_pipeline/reports/iso_audio_decode_report.json"),
)
AUDIO_DECODED_WAV_STATUSES = {
    "copied_validated_wav",
    "decoded_ps_adpcm_to_pcm_wav",
    "decoded_vagp_to_pcm_wav",
}
AUDIO_RAW_PENDING_STATUSES = {
    "copied_container",
    "copied_midi",
    "decode_pending_raw_only",
    "identified_sound_bank_raw_only",
    "needs_inspection",
    "raw_dumped_unknown_audio_like",
    "raw_preserved_malformed_scei_stream",
    "unavailable_malformed_scei_stream",
}
AUDIO_FAILED_STATUSES = {"failed", "failed_ps_adpcm_decode"}
AUDIO_INFO_BANK_STATUSES = {"scei_bank_found"}
AUDIO_WARNING_STATUSES = {"raw_preserved_malformed_scei_stream", "unavailable_malformed_scei_stream"}
AUDIO_RECOGNIZED_STATUSES = (
    AUDIO_DECODED_WAV_STATUSES
    | AUDIO_RAW_PENDING_STATUSES
    | AUDIO_FAILED_STATUSES
    | AUDIO_INFO_BANK_STATUSES
)


def _audio_report_rows(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        for key in ("rows", "entries", "items", "files", "candidates"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _audio_row_status(row: dict) -> str:
    return str(row.get("decode_status") or row.get("status") or "").strip().lower()


def _audio_row_path(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _audio_row_name(row: dict, path_text: str) -> str:
    bank_name = row.get("bank_name") or row.get("bank")
    stream_index = row.get("stream_index")
    if bank_name and stream_index not in (None, ""):
        return f"{bank_name} stream {stream_index}"
    return str(row.get("name") or row.get("source_iso_path") or row.get("iso_path") or row.get("path") or Path(path_text).name or "audio entry")


def _audio_existing_path(path_text: str, root: Path) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text).expanduser()
    candidates = [path] if path.is_absolute() else [root / path, path]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _audio_display_path(path_text: str, root: Path) -> str:
    path = _audio_existing_path(path_text, root)
    return str(path) if path else path_text


def _audio_duration_text(value: object) -> str:
    if value in (None, ""):
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:.2f}s"
    return str(value)


def _audio_common_fields(row: dict | None, root: Path, fallback_path: str = "") -> dict[str, str]:
    row = row or {}
    out_path = _audio_display_path(_audio_row_path(row, "output_path", "decoded_path"), root)
    raw_path = _audio_display_path(_audio_row_path(row, "raw_path", "source_candidate", "extracted_path", "path"), root)
    return {
        "bank_type": str(row.get("bank_type") or row.get("bank_source_type") or row.get("detected_bank_type") or "—"),
        "bank_name": str(row.get("bank_name") or row.get("bank") or Path(str(row.get("bank_source") or raw_path or fallback_path)).stem or "—"),
        "stream_index": str(row.get("stream_index") if row.get("stream_index") not in (None, "") else "—"),
        "sample_rate": str(row.get("sample_rate") or "—"),
        "loop_flag": str(row.get("loop_flag") if row.get("loop_flag") not in (None, "") else "—"),
        "duration": _audio_duration_text(row.get("duration") or row.get("duration_estimate")),
        "output_path": out_path,
        "raw_path": raw_path,
        "decode_status": _audio_row_status(row) or "not decoded",
    }


def _audio_status_warning(status: str) -> str:
    if status == "raw_preserved_malformed_scei_stream":
        return "Malformed SCEI stream preserved as raw audio for inspection"
    if status == "unavailable_malformed_scei_stream":
        return "Malformed SCEI stream could not be extracted; inspect source bank"
    return status


def _audio_messages(row: dict) -> list[str]:
    messages: list[str] = []
    for key in ("warning", "warnings", "error", "errors", "decode_error"):
        value = row.get(key)
        if not value:
            continue
        if isinstance(value, list):
            messages.extend(str(item) for item in value if item)
        else:
            messages.append(str(value))
    return messages


def _audio_gui_payload(row: dict[str, object], payload_path: Path | str) -> dict[str, object]:
    payload = dict(row)
    payload["payload_path"] = str(payload_path)
    return payload


def _audio_selected_report_row(payload: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    report_row = payload.get("report_row")
    if isinstance(report_row, dict) and report_row:
        details = dict(report_row)
        details.setdefault("gui_row", {key: value for key, value in payload.items() if key != "report_row"})
        return details
    return dict(payload)


def format_audio_decode_details(payload: dict[str, object] | None) -> str:
    """Return pretty JSON for one selected audio row, never the whole report."""
    row = _audio_selected_report_row(payload)
    return json.dumps(row, indent=2, sort_keys=True, ensure_ascii=False) if row else "Select an audio row to see decode details."


def audio_source_field_values(payload: dict[str, object] | None) -> dict[str, str]:
    row = _audio_selected_report_row(payload)
    offset = row.get("offset") if row.get("offset") not in (None, "") else row.get("stream_offset")
    return {
        "Source ISO path": str(row.get("source_iso_path") or row.get("iso_path") or "—"),
        "Offset": str(offset if offset not in (None, "") else "—"),
        "Raw path": str(row.get("raw_path") or row.get("source_candidate") or row.get("extracted_path") or row.get("path") or "—"),
        "Decoded output path": str(row.get("output_path") or row.get("decoded_path") or "—"),
    }


def _audio_payload_existing_path(payload: dict[str, object] | None, keys: tuple[str, ...]) -> Path | None:
    row = _audio_selected_report_row(payload)
    gui_row = row.get("gui_row") if isinstance(row.get("gui_row"), dict) else {}
    for source in (row, gui_row):
        for key in keys:
            value = source.get(key)
            if value and str(value) != "—":
                path = Path(str(value)).expanduser()
                if path.exists():
                    return path
    return None


def load_audio_report_sources(workspace: Path | str) -> dict[str, list[dict[str, object]]]:
    """Load ISO audio inventory/decode reports and merge them with audio output folders.

    Returns GUI-ready row dictionaries grouped into decoded_wavs, raw_pending, and
    failed_warnings. The helper is pure with respect to GUI state so tests can feed
    synthetic report JSON and folders without constructing Tk widgets.
    """
    root = Path(workspace)
    decoded: list[dict[str, object]] = []
    raw: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    seen_decoded: set[tuple[str, str]] = set()
    seen_raw: set[tuple[str, str]] = set()
    seen_failed: set[tuple[str, str]] = set()

    def add_decoded(path_text: str, row: dict | None = None) -> None:
        key = (path_text, _audio_row_status(row or {}))
        if key in seen_decoded:
            return
        seen_decoded.add(key)
        p = Path(path_text) if path_text else Path("")
        common = _audio_common_fields(row, root, path_text)
        decoded.append({
            "name": _audio_row_name(row or {}, path_text) if row else p.name,
            "format": str((row or {}).get("detected_format") or (row or {}).get("format") or "WAV"),
            "channels": str((row or {}).get("channels") or "—"),
            "size": "",
            "source_path": path_text,
            "payload_path": common["output_path"] or path_text,
            **common,
            "report_row": dict(row or {}),
        })

    def add_raw(path_text: str, row: dict | None = None) -> None:
        key = (path_text, _audio_row_status(row or {}))
        if key in seen_raw:
            return
        seen_raw.add(key)
        common = _audio_common_fields(row, root, path_text)
        raw.append({
            "name": _audio_row_name(row or {}, path_text) if row else Path(path_text).name,
            "detected_format": str((row or {}).get("detected_format") or (row or {}).get("format") or Path(path_text).suffix.lower().lstrip(".").upper() or "unknown"),
            "confidence": str((row or {}).get("confidence") or "pending"),
            "next_action": str((row or {}).get("next_action") or "run Decode audio"),
            "source_path": path_text,
            "payload_path": common["raw_path"] or path_text,
            **common,
            "report_row": dict(row or {}),
        })

    def add_failed(path_text: str, row: dict, message: str) -> None:
        key = (path_text, message)
        if key in seen_failed:
            return
        seen_failed.add(key)
        common = _audio_common_fields(row, root, path_text)
        failed.append({
            "name": _audio_row_name(row, path_text),
            "format": str(row.get("detected_format") or row.get("format") or "unknown"),
            "message": message,
            "path": path_text,
            "payload_path": common["raw_path"] or common["output_path"] or path_text,
            **common,
            "report_row": dict(row or {}),
        })

    for rel in AUDIO_REPORT_RELATIVE_PATHS:
        path = root / rel
        if not path.exists():
            continue
        try:
            rows = _audio_report_rows(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            add_failed(str(path), {"name": path.name, "detected_format": "JSON"}, f"Could not read report: {exc}")
            continue
        for row in rows:
            status = _audio_row_status(row)
            out_path = _audio_row_path(row, "output_path", "decoded_path")
            raw_path = _audio_row_path(row, "raw_path", "source_candidate", "extracted_path", "path")
            row_path = raw_path or out_path or _audio_row_path(row, "source_iso_path", "iso_path", "path")
            messages = _audio_messages(row)
            existing_out = _audio_existing_path(out_path, root)
            if status not in AUDIO_INFO_BANK_STATUSES and (
                status in AUDIO_DECODED_WAV_STATUSES
                or (existing_out and existing_out.suffix.lower() == ".wav")
            ):
                add_decoded(str(existing_out) if existing_out else out_path or raw_path, row)
            if (
                status in AUDIO_RAW_PENDING_STATUSES
                or status in AUDIO_INFO_BANK_STATUSES
                or (raw_path and Path(raw_path).suffix.lower() == ".bin")
            ):
                add_raw(row_path, row)
            if status in AUDIO_WARNING_STATUSES and not messages:
                messages.append(_audio_status_warning(status))
            if status in AUDIO_FAILED_STATUSES or messages:
                add_failed(row_path, row, "; ".join(messages) if messages else status or "failed")

    for folder in (root / "media_pipeline/decoded/audio/wav",):
        if folder.exists():
            for path in sorted(folder.rglob("*.wav")):
                add_decoded(str(path))
    for folder in (root / "media_pipeline/decoded/audio/raw", root / "media_pipeline/extracted/embedded/audio"):
        if folder.exists():
            for path in sorted(p for p in folder.rglob("*") if p.is_file()):
                add_raw(str(path))
    return {"decoded_wavs": decoded, "raw_pending": raw, "failed_warnings": failed}


def _audio_report_int(payload: dict, *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _audio_row_identity(row: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", "—"):
            return str(value)
    report_row = row.get("report_row")
    if isinstance(report_row, dict):
        for key in keys:
            value = report_row.get(key)
            if value not in (None, "", "—"):
                return str(value)
    return ""


def audio_report_completion_summary(workspace: Path | str, buckets: dict[str, list[dict[str, object]]] | None = None) -> dict[str, int | None]:
    """Compute Audio Workbench completion counts from report buckets and report metadata."""
    root = Path(workspace)
    buckets = buckets if buckets is not None else load_audio_report_sources(root)
    all_rows = [row for rows in buckets.values() for row in rows]
    banks = {
        bank
        for bank in (_audio_row_identity(row, "bank_name", "bank", "bank_source", "source_iso_path", "iso_path") for row in all_rows)
        if bank and not bank.startswith("No ")
    }
    streams = {
        f"{_audio_row_identity(row, 'bank_name', 'bank', 'source_iso_path', 'iso_path')}:{_audio_row_identity(row, 'stream_index', 'stream_offset', 'offset', 'raw_path', 'output_path', 'source_path')}"
        for row in all_rows
        if _audio_row_identity(row, "stream_index", "stream_offset", "offset", "raw_path", "output_path", "source_path")
        and not str(row.get("name") or "").startswith("No ")
    }
    inspected_containers: int | None = None
    metadata_banks: int | None = None
    metadata_streams: int | None = None
    for rel in AUDIO_REPORT_RELATIVE_PATHS:
        path = root / rel
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        inspected_value = _audio_report_int(payload, "inspected_container_count", "containers_inspected", "inspected_containers", "container_count")
        bank_value = _audio_report_int(payload, "banks_found", "bank_count", "banks")
        stream_value = _audio_report_int(payload, "streams_found", "stream_count", "streams")
        inspected_containers = inspected_value if inspected_value is not None else inspected_containers
        metadata_banks = bank_value if bank_value is not None else metadata_banks
        metadata_streams = stream_value if stream_value is not None else metadata_streams
    return {
        "banks_found": metadata_banks if metadata_banks is not None else len(banks),
        "streams_found": metadata_streams if metadata_streams is not None else len(streams),
        "decoded_wavs": len([row for row in buckets.get("decoded_wavs", []) if not str(row.get("name") or "").startswith("No ")]),
        "raw_pending": len([row for row in buckets.get("raw_pending", []) if not str(row.get("name") or "").startswith("No ")]),
        "failures": len([row for row in buckets.get("failed_warnings", []) if not str(row.get("name") or "").startswith("No ")]),
        "inspected_containers": inspected_containers,
    }


def format_audio_completion_status(summary: dict[str, int | None]) -> str:
    parts = [
        f"{summary.get('banks_found') or 0} banks",
        f"{summary.get('streams_found') or 0} streams",
        f"{summary.get('decoded_wavs') or 0} WAVs",
        f"{summary.get('raw_pending') or 0} raw/pending",
    ]
    inspected = summary.get("inspected_containers")
    if inspected is not None:
        parts.append(f"{inspected} containers inspected")
    parts.append(f"{summary.get('failures') or 0} failures")
    return f"Audio decode complete — {', '.join(parts)}."


SETUP_CHECKLIST_SPECS = (
    ("iso_path_set", "ISO path set", "iso_path", "file"),
    ("area_server_root_set", "Area Server root set", "area_server_root", "dir"),
    ("workspace_exists", "Workspace exists", ".", "dir"),
    ("extracted_ccs_exists", "extracted_ccs exists", "extracted_ccs", "dir"),
    ("iso_ccsf_extraction_index_txt", "iso_ccsf_extraction_index.txt exists", "reports/iso_ccsf_extraction_index.txt", "file"),
    ("ccsf_asset_index_json", "ccsf_asset_index.json exists", "reports/ccsf_asset_index.json", "file"),
    ("asset_library_json", "asset_library.json exists", "reports/asset_library.json", "file"),
    ("asset_library_dashboard_html", "asset_library_dashboard.html exists", "reports/asset_library_dashboard.html", "file"),
    ("iso_asset_survey_json", "iso_asset_survey.json exists", "reports/iso_asset_survey.json", "file"),
    ("asset_survey_dashboard_html", "asset_survey_dashboard.html exists", "reports/asset_survey_dashboard.html", "file"),
    ("model_previews_exists", "model_previews folder exists", "model_previews", "dir"),
    ("iso_media_inventory_json", "iso_media_inventory.json exists", "reports/iso_media_inventory.json", "file"),
    ("iso_audio_inventory_json", "iso_audio_inventory.json exists", "reports/iso_audio_inventory.json", "file"),
    ("iso_audio_decode_report_json", "iso_audio_decode_report.json exists", "reports/iso_audio_decode_report.json", "file"),
    ("iso_audio_wav_folder", "decoded audio WAV folder exists", "media_pipeline/decoded/audio/wav", "dir"),
    ("iso_media_dashboard_html", "iso_media_dashboard.html exists", "reports/iso_media_dashboard.html", "file"),
    ("iso_audio_dashboard_html", "iso_audio_dashboard.html exists", "reports/iso_audio_dashboard.html", "file"),
)


PREPARATION_ACTION_NAMES = (
    "Build / Refresh Asset Library",
    "Survey ISO Assets",
    "Scan / Decode Audio",
    "Analyze SNDDATA Music",
    "Load Asset Library for Viewer",
    "Open Reports Folder",
    "Open Extracted CCSF Folder",
    "Open Model Output Folder",
)


CCSF_FIELD_ASSET_WARNING = "Large field assets may render as scattered chunks until transform/clump assembly is implemented."


def ccsf_asset_counts(asset: dict) -> dict:
    """Return normalized CCSF resource counts from logical or scan metadata."""
    raw = dict(asset.get("resource_counts") or asset.get("counts") or {})
    fallback_keys = {
        "HIT": ("hit_count", "hits"),
        "DMY": ("dmy_count", "dummy_count", "dummies"),
        "OBJ": ("object_count", "objects"),
        "TEX": ("texture_count", "textures"),
        "CMP": ("clump_count", "clumps"),
    }
    for prefix, keys in fallback_keys.items():
        if raw.get(prefix) is not None or raw.get(f"{prefix}_") is not None:
            continue
        for key in keys:
            value = asset.get(key)
            if isinstance(value, (list, tuple, set, dict)):
                raw[prefix] = len(value)
                break
            if value is not None:
                raw[prefix] = value
                break
    normalized = {}
    for key, value in raw.items():
        label = str(key).rstrip("_").upper()
        try:
            normalized[label] = int(value or 0)
        except (TypeError, ValueError):
            normalized[label] = value
    return normalized


def _ccsf_int_count(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def ccsf_asset_structure_tags(asset: dict, counts: dict | None = None) -> list[str]:
    """Return detail-panel tags inferred from CCSF structure/scan metadata."""
    counts = counts or ccsf_asset_counts(asset)
    existing = [str(value) for value in (asset.get("tags") or [])]
    scan_kind = " ".join(
        str(asset.get(key) or "")
        for key in ("type", "classification", "scan_classification", "asset_classification")
    )
    many_resources = any(
        _ccsf_int_count(counts.get(key)) >= limit
        for key, limit in (("CMP", 2), ("CLP", 2), ("CLUMP", 2), ("OBJ", 6), ("MDL", 6), ("TEX", 6))
    )
    is_field_stage = (
        "field/stage" in scan_kind.lower()
        or "field/stage candidate" in " ".join(existing).lower()
        or many_resources
    )
    tags = list(existing)
    if is_field_stage and "field/stage candidate" not in tags:
        tags.append("field/stage candidate")
    return tags

CCSF_VIEWER_DEFAULT_COLUMNS = ("type", "variant", "MDL", "TEX", "CLT", "ANM", "OBJ")


def setup_checklist_rows(workspace: Path, iso_path: str = "", area_server_root: str = "") -> list[dict[str, object]]:
    """Return Setup / Scan checklist rows without creating any Tk widgets."""
    workspace = Path(workspace).expanduser()
    special = {
        "iso_path": Path(iso_path).expanduser() if iso_path else None,
        "area_server_root": Path(area_server_root).expanduser() if area_server_root else None,
    }
    rows: list[dict[str, object]] = []
    for key, label, rel, kind in SETUP_CHECKLIST_SPECS:
        path = special.get(rel) if rel in special else workspace / rel
        exists = bool(path and (path.is_dir() if kind == "dir" else path.is_file()))
        rows.append({"key": key, "label": label, "path": str(path or ""), "ok": exists, "kind": kind})
    return rows


def preparation_action_names() -> tuple[str, ...]:
    """Return Setup / Scan preparation actions in display order."""
    return PREPARATION_ACTION_NAMES


def more_page_labels() -> tuple[str, ...]:
    """Return labels shown in the nested More notebook."""
    return MORE_PAGE_LABELS


def full_disc_preparation_steps() -> tuple[str, ...]:
    """Return Full Disc Preparation steps in sequential execution order."""
    return FULL_DISC_PREPARATION_STEPS


def deep_disc_discovery_steps() -> tuple[str, ...]:
    """Return explicit Deep Disc Discovery steps in sequential execution order."""
    return DEEP_DISC_DISCOVERY_STEPS


def preparation_step_states() -> tuple[str, ...]:
    """Return allowed sequential Full Disc Preparation step states."""
    return PREPARATION_STEP_STATES


def ccsf_viewer_default_columns() -> tuple[str, ...]:
    """Return default 3D Asset Viewer tree columns."""
    return CCSF_VIEWER_DEFAULT_COLUMNS


def coalesce_progress_messages(messages: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop excessive raw debug JSON progress messages, keeping the latest burst item."""
    coalesced_messages: list[tuple[str, str]] = []
    latest_debug_json: tuple[str, str] | None = None
    skipped_debug_json = 0
    for level, text in messages:
        stripped = (text or "").strip()
        is_debug_json = level == "debug" and (stripped.startswith("{") or stripped.startswith("[{"))
        if is_debug_json:
            if latest_debug_json is not None:
                skipped_debug_json += 1
            latest_debug_json = (level, text)
            continue
        if latest_debug_json is not None:
            if skipped_debug_json:
                coalesced_messages.append(("debug", f"[debug] coalesced {skipped_debug_json} raw JSON progress line(s)\n"))
            coalesced_messages.append(latest_debug_json)
            latest_debug_json = None
            skipped_debug_json = 0
        coalesced_messages.append((level, text))
    if latest_debug_json is not None:
        if skipped_debug_json:
            coalesced_messages.append(("debug", f"[debug] coalesced {skipped_debug_json} raw JSON progress line(s)\n"))
        coalesced_messages.append(latest_debug_json)
    return coalesced_messages


def workflow_page_labels() -> tuple[str, ...]:
    """Return the top-level workflow page labels in display order."""
    return WORKFLOW_PAGE_LABELS


def project_settings_payload(
    *,
    iso_path: str = "",
    area_server_root_path: str = "",
    workspace_path: str = "",
    data_folder_path: str = "",
    save_folder_path: str = "",
    saved_at: str | None = None,
) -> dict[str, str]:
    """Build the pure project-settings payload shared by GUI save/load paths."""
    payload = {
        "iso_path": str(iso_path or ""),
        "area_server_root_path": str(area_server_root_path or ""),
        "workspace_path": str(workspace_path or ""),
        "data_folder_path": str(data_folder_path or ""),
        "save_folder_path": str(save_folder_path or ""),
    }
    if saved_at is not None:
        payload["saved_at"] = str(saved_at)
    return payload


def save_project_settings_json(path: str | Path, payload: dict[str, object]) -> Path:
    """Write project settings JSON without requiring any Tk state."""
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    serializable = {key: str(payload.get(key, "") or "") for key in PROJECT_SETTINGS_KEYS}
    if payload.get("saved_at") is not None:
        serializable["saved_at"] = str(payload["saved_at"])
    out.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    return out


def load_project_settings_json(path: str | Path) -> dict[str, str]:
    """Load project settings JSON without creating a Tk root."""
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Project settings JSON must contain an object at the top level.")
    return {key: str(data.get(key, "") or "") for key in (*PROJECT_SETTINGS_KEYS, "saved_at") if key in data or key in PROJECT_SETTINGS_KEYS}


def expected_report_keys() -> tuple[str, ...]:
    """Return expected workflow report file keys used by report discovery."""
    return tuple(EXPECTED_REPORT_NAMES)


def ccsf_asset_selection_policy() -> dict[str, object]:
    """Describe the pure asset-selection behavior for headless tests."""
    return {
        "detail_work_scheduled": True,
        "detail_delay_ms": CCSF_ASSET_SELECTION_DETAIL_DELAY_MS,
        "builds_manifest_on_selection": CCSF_ASSET_SELECTION_BUILDS_MANIFEST,
    }

GUI_TOOL_STATUSES = ("active", "experimental", "legacy", "hidden")

GUI_TOOL_REGISTRY: dict[str, dict[str, str]] = {
    "iso_asset_survey": {
        "display_name": "ISO Asset Survey",
        "command": "_build_iso_asset_survey_tab",
        "category": "ISO Tools",
        "status": "active",
        "description": "Primary read-only ISO survey workflow that writes the canonical iso_asset_survey reports and dashboard.",
        "replacement": "Use ISO Tools → Asset Survey.",
    },
    "iso_3d_preview": {
        "display_name": "Raw ISO 3D candidate view",
        "command": "_build_iso_3d_preview_tab",
        "category": "Legacy ISO candidate views",
        "status": "experimental",
        "description": "Raw candidate table for model/container guesses. It overlaps the ISO Asset Survey and can produce noisy low-confidence rows.",
        "replacement": "Prefer ISO Tools → Asset Survey, then use Asset Library previews after ISO → CCSF extraction.",
    },
    "workbench_smoke": {
        "display_name": "Workbench smoke test",
        "command": "workbench_smoke_test.py",
        "category": "Diagnostics",
        "status": "experimental",
        "description": "Developer diagnostic launcher for checking the workbench command path.",
        "replacement": "Use only when diagnosing GUI launcher issues.",
    },
    "iso_client_probe": {
        "display_name": "ISO Client Probe",
        "command": "poc_iso_client_probe.py",
        "category": "Old report launchers",
        "status": "legacy",
        "description": "Older standalone ISO probe that predates the consolidated ISO Asset Survey workflow.",
        "replacement": "Use ISO Tools → Asset Survey.",
    },
    "server_text_probe": {
        "display_name": "Server Text Probe",
        "command": "poc_server_text_shop_probe.py",
        "category": "Advanced research launchers",
        "status": "experimental",
        "description": "Specialized shop/text scan for targeted research; not needed for the normal extraction and preview workflow.",
        "replacement": "Run Quick Scan or Area Server Tools first; use this only for focused text research.",
    },
    "boundary_correlation_report": {
        "display_name": "Boundary/Correlation report",
        "command": "server_client_boundary_report.py",
        "category": "Advanced research launchers",
        "status": "experimental",
        "description": "Advanced correlation report generator for client/server boundary research.",
        "replacement": "Use Reports for generated summaries; run this only when boundary correlation is the current research task.",
    },
    "fragmenter_safe_scan": {
        "display_name": "Fragmenter Safe Scan",
        "command": "fragmenter_research_pack.py scan",
        "category": "Advanced research launchers",
        "status": "experimental",
        "description": "Broad metadata scan used by research pack reports; useful but not part of the immediate asset preview workflow.",
        "replacement": "Use Quick Scan from the workbench source bar for routine checks.",
    },
    "root_town_summary": {
        "display_name": "Root Town Summary / proof panels",
        "command": "internal write_root_town_summary",
        "category": "Root Town",
        "status": "legacy",
        "description": "Read-only Root Town proof/summary panels for town04-related identifiers; retained until Root Town actions become actionable.",
        "replacement": "Root Town remains available under Area Server Tools; use the Settings copy for legacy report generation.",
    },
    "export_research_bundle": {
        "display_name": "Export Research Bundle",
        "command": "fragmenter_research_pack.py package",
        "category": "Advanced research launchers",
        "status": "experimental",
        "description": "Packages generated research outputs for sharing; not required for primary preview workflows.",
        "replacement": "Use only after reports/assets have been generated and need to be bundled.",
    },
    "extract_common_town_assets": {
        "display_name": "Extract Common Town Assets",
        "command": "extract_area_ccs_members.py",
        "category": "Area Server Tools",
        "status": "active",
        "description": "Primary helper for extracting common town CCS members from Area Server data.",
        "replacement": "Available from the workbench source bar.",
    },
    "catalog_extracted_assets": {
        "display_name": "Catalog Extracted Assets",
        "command": "poc_ccs_asset_catalog.py",
        "category": "Asset Library",
        "status": "active",
        "description": "Catalogs extracted CCS assets for Asset Library review.",
        "replacement": "Available from the workbench source bar and Asset Library flow.",
    },
}

ROOT_TOWN_PROOF_TARGETS = (
    {
        "display_id": "CCSFtown04 / town04.cmp",
        "copy_search_id": "CCSFtown04",
        "family_label": "Primary target",
        "identifiers": ("CCSFtown04", "town04.cmp"),
        "confidence": "high",
        "category": "Root Town map container",
    },
    {
        "display_id": "sr4wep1",
        "copy_search_id": "sr4wep1",
        "family_label": "Weapon Shop",
        "identifiers": ("sr4wep1",),
        "confidence": "medium",
        "category": "shop family",
    },
    {
        "display_id": "sr4ite1",
        "copy_search_id": "sr4ite1",
        "family_label": "Item Shop",
        "identifiers": ("sr4ite1",),
        "confidence": "medium",
        "category": "shop family",
    },
    {
        "display_id": "sr4mag1",
        "copy_search_id": "sr4mag1",
        "family_label": "Magic Shop",
        "identifiers": ("sr4mag1",),
        "confidence": "medium",
        "category": "shop family",
    },
    {
        "display_id": "sr4sav1",
        "copy_search_id": "sr4sav1",
        "family_label": "Recorder / Save",
        "identifiers": ("sr4sav1",),
        "confidence": "medium",
        "category": "shop family",
    },
    {
        "display_id": "sr4fai1",
        "copy_search_id": "sr4fai1",
        "family_label": "Elf’s Haven / Storage",
        "identifiers": ("sr4fai1",),
        "confidence": "medium",
        "category": "shop family",
    },
    {
        "display_id": "sr4sun1",
        "copy_search_id": "sr4sun1",
        "family_label": "sky/sun candidate",
        "identifiers": ("sr4sun1",),
        "confidence": "medium",
        "category": "sky/background",
    },
    {
        "display_id": "sr4clo1 / sr4clo2",
        "copy_search_id": "sr4clo1",
        "family_label": "cloud/background candidates",
        "identifiers": ("sr4clo1", "sr4clo2"),
        "confidence": "medium",
        "category": "sky/background",
    },
    {
        "display_id": "BLT_bg",
        "copy_search_id": "BLT_bg",
        "family_label": "background label candidate",
        "identifiers": ("BLT_bg",),
        "confidence": "medium",
        "category": "sky/background",
    },
)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def import_fragment_strings_workbook(workbook_path: Path, workspace: Path) -> dict[str, object]:
    """Summarize a Fragment Strings workbook into workspace/reports.

    The parser intentionally collects lightweight metadata and a few sample rows
    only; it does not transform or patch client/server strings.
    """
    if importlib.util.find_spec("openpyxl") is None:
        return {
            "ok": False,
            "reason": "missing_openpyxl",
            "message": (
                "The optional Python package 'openpyxl' is required to import "
                "Fragment Strings.xlsx. Install it in this environment and try again."
            ),
        }

    openpyxl = importlib.import_module("openpyxl")
    workbook_path = Path(workbook_path).expanduser()
    workspace = Path(workspace).expanduser()
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    sheet_names = list(wb.sheetnames)

    def clean(value: object) -> str:
        return "" if value is None else str(value).strip()

    sheet_summaries: dict[str, dict[str, object]] = {}
    alias_lookup = {alias: canonical for canonical, aliases in FRAGMENT_STRINGS_SHEETS.items() for alias in aliases}
    for sheet_name in sheet_names:
        canonical = alias_lookup.get(sheet_name)
        if not canonical:
            continue
        ws = wb[sheet_name]
        rows = ws.iter_rows(values_only=True)
        header = [clean(value) for value in next(rows, ())]
        non_empty_rows = 0
        samples: list[list[str]] = []
        found_client_ids: set[str] = set()
        for row in rows:
            values = [clean(value) for value in row]
            if not any(values):
                continue
            non_empty_rows += 1
            joined = " ".join(values).upper()
            for client_id in FRAGMENT_STRINGS_CLIENT_IDS:
                if client_id in joined:
                    found_client_ids.add(client_id)
            if len(samples) < 5:
                samples.append(values[:8])
        sheet_summaries[canonical] = {
            "sheet_name": sheet_name,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "header": header[:12],
            "non_empty_data_rows": non_empty_rows,
            "sample_rows": samples,
            "known_client_ids": sorted(found_client_ids),
        }

    crosslinks = {}
    available_client_ids = {
        client_id
        for summary in sheet_summaries.values()
        for client_id in summary.get("known_client_ids", [])
    }
    for stem, client_ids in FRAGMENT_STRINGS_ROOT_TOWN_CROSSLINKS.items():
        matches = [client_id for client_id in client_ids if client_id in available_client_ids]
        if matches:
            crosslinks[stem] = {"client_ids": matches, "note": "Matched known client/shop IDs in workbook summaries."}

    payload = {
        "schema": "fragmenter.fragment_strings_summary.v1",
        "source_workbook": str(workbook_path),
        "generated_utc": _utc_timestamp(),
        "sheet_names": sheet_names,
        "expected_sheet_aliases": FRAGMENT_STRINGS_SHEETS,
        "known_client_shop_ids": FRAGMENT_STRINGS_CLIENT_IDS,
        "summaries": sheet_summaries,
        "root_town_crosslinks": crosslinks,
        "output_reports": {
            "json": str(reports / "fragment_strings_summary.json"),
            "text": str(reports / "fragment_strings_summary.txt"),
        },
    }
    json_path = reports / "fragment_strings_summary.json"
    txt_path = reports / "fragment_strings_summary.txt"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    lines = [
        "Fragment Strings Workbook Summary",
        f"Source: {workbook_path}",
        f"Generated UTC: {payload['generated_utc']}",
        "",
        "Workbook sheets:",
        *[f"- {name}" for name in sheet_names],
        "",
        "Expected text groups:",
    ]
    for canonical, aliases in FRAGMENT_STRINGS_SHEETS.items():
        summary = sheet_summaries.get(canonical)
        if summary:
            client_ids = ", ".join(summary["known_client_ids"]) or "none found"
            lines.append(f"- {canonical} ({summary['sheet_name']}): {summary['non_empty_data_rows']} data rows; client IDs: {client_ids}")
        else:
            lines.append(f"- {canonical} ({'/'.join(aliases)}): not present")
    lines.extend(["", "Known client/shop IDs:", "- " + ", ".join(FRAGMENT_STRINGS_CLIENT_IDS), "", "Root Town crosslinks:"])
    if crosslinks:
        for stem, link in crosslinks.items():
            lines.append(f"- {stem}: {', '.join(link['client_ids'])}")
    else:
        lines.append("- none available from imported summaries")
    lines.extend(["", f"JSON report: {json_path}", f"Text report: {txt_path}"])
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"ok": True, "json_path": json_path, "txt_path": txt_path, "payload": payload}


def _launcher_workspace_snapshot(workspace: Path) -> dict[str, float]:
    """Return a lightweight mtime snapshot for files under launcher output folders."""
    snapshot: dict[str, float] = {}
    for rel in ("reports", "extracted_ccs", "bundles", "logs", "patch_plans"):
        root = workspace / rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    snapshot[str(path)] = path.stat().st_mtime
                except OSError:
                    pass
    return snapshot


def _launcher_generated_paths(workspace: Path, before: dict[str, float], expected: Path) -> list[str]:
    """List files created or modified by a launcher, preserving the expected path."""
    generated: list[str] = []
    after = _launcher_workspace_snapshot(workspace)
    for path, mtime in sorted(after.items()):
        if path not in before or before[path] != mtime:
            generated.append(path)
    if expected.exists():
        expected_str = str(expected)
        if expected.is_file() and expected_str not in generated:
            generated.insert(0, expected_str)
        elif expected.is_dir():
            for path in sorted(expected.rglob("*")):
                if path.is_file():
                    path_str = str(path)
                    if path_str not in generated:
                        generated.append(path_str)
    return generated


def _load_optional_pillow():
    """Return optional Pillow modules for sprite scaling, or (None, None)."""
    if (
        importlib.util.find_spec("PIL")
        and importlib.util.find_spec("PIL.Image")
        and importlib.util.find_spec("PIL.ImageTk")
    ):
        return importlib.import_module("PIL.Image"), importlib.import_module("PIL.ImageTk")
    return None, None


PIL_IMAGE, PIL_IMAGE_TK = _load_optional_pillow()


def normalize_theme_name(name: str) -> str:
    normalized = (name or "").strip()
    if normalized == "Dark Blue":
        return "Serenial Blue"
    if normalized == "Serenial Blue":
        return normalized
    if normalized == "Hack Green":
        return normalized
    return "Hack Green"


MAX_CONSOLE_LINES = 2000
MAX_CONSOLE_CHARS = 250000
CONSOLE_TRIM_LINE_BATCH = 250
CONSOLE_TRIM_CHAR_BATCH = 25000
MAX_RESULT_HIERARCHY_ROWS = 1200
LARGE_REPORT_THRESHOLD_BYTES = 256 * 1024
REPORT_INITIAL_PREVIEW_BYTES = 128 * 1024
REPORT_SEARCH_READ_BYTES = 256 * 1024
REPORT_SUMMARY_SCAN_BYTES = 512 * 1024
REPORT_FULL_LOAD_CHUNK_BYTES = 64 * 1024
REPORT_FULL_LOAD_APPEND_DELAY_MS = 15
EXPECTED_REPORT_NAMES = [
    "iso_ccsf_extraction_index.txt",
    "iso_ccsf_extraction_index.json",
    "ccsf_asset_index.txt",
    "ccsf_asset_index.json",
    "asset_library.txt",
    "asset_library.json",
    "asset_library_dashboard.html",
    "iso_asset_survey.txt",
    "iso_asset_survey.json",
    "asset_survey_dashboard.html",
    "area_server_patch_scan.txt",
    "area_server_patch_scan.json",
    "fragment_strings_summary.txt",
    "fragment_strings_summary.json",
    "iso_media_inventory.json",
    "iso_media_inventory.txt",
    "iso_media_dashboard.html",
    "iso_audio_inventory.json",
    "iso_audio_inventory.txt",
    "iso_audio_dashboard.html",
    "iso_audio_decode_report.json",
    "iso_audio_decode_report.txt",
    "iso_texture_inventory.json",
    "iso_texture_inventory.txt",
    "iso_texture_dashboard.html",
    "iso_model_inventory.json",
    "iso_model_inventory.txt",
    "iso_unknown_inventory.json",
    "iso_unknown_inventory.txt",
]


def discover_expected_report_files(workspace: Path) -> list[dict[str, object]]:
    """Discover expected reports in the active workspace reports directory.

    The helper intentionally performs only filesystem metadata reads. Report
    contents are not loaded here so large report files cannot stall GUI startup.
    """
    reports_dir = Path(workspace).expanduser() / "reports"
    rows: list[dict[str, object]] = []
    for name in EXPECTED_REPORT_NAMES:
        path = (reports_dir / name).resolve()
        exists = path.is_file()
        size = 0
        modified = ""
        modified_timestamp = None
        if exists:
            try:
                stat_result = path.stat()
                size = stat_result.st_size
                modified_timestamp = stat_result.st_mtime
                modified = datetime.fromtimestamp(stat_result.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                exists = False
        rows.append(
            {
                "display_name": name,
                "path": path,
                "exists": exists,
                "size": size,
                "modified": modified or "—",
                "modified_timestamp": modified_timestamp,
                "type": path.suffix.lower().lstrip(".") or "(none)",
            }
        )
    return rows


def _trim_console_text(console: tk.Text) -> None:
    """Keep the Tk console bounded by dropping oldest content in chunks."""
    try:
        end_index = console.index("end-1c")
        line_count = int(end_index.split(".", 1)[0])
    except (tk.TclError, ValueError):
        return

    if line_count > MAX_CONSOLE_LINES:
        extra_lines = line_count - MAX_CONSOLE_LINES
        delete_lines = min(line_count - 1, max(extra_lines, CONSOLE_TRIM_LINE_BATCH))
        if delete_lines > 0:
            console.delete("1.0", f"{delete_lines + 1}.0")

    try:
        counted = console.count("1.0", "end-1c", "chars")
        char_count = int(counted[0]) if counted else 0
    except (tk.TclError, TypeError, ValueError):
        return

    if char_count > MAX_CONSOLE_CHARS:
        extra_chars = char_count - MAX_CONSOLE_CHARS
        delete_chars = max(extra_chars, CONSOLE_TRIM_CHAR_BATCH)
        console.delete("1.0", f"1.0+{delete_chars}c")


def console_write(console: tk.Text, text: str) -> None:
    """Append text to a console widget, enforce caps, and keep newest output visible."""
    console.insert("end", text)
    _trim_console_text(console)
    console.see("end")


def _bind_wraplength(label: ttk.Label, container: tk.Widget, padding: int = 32, min_width: int = 240) -> ttk.Label:
    """Keep a label's wraplength aligned with its container's available width."""

    def update_wrap(evt=None):
        width = evt.width if evt is not None else container.winfo_width()
        if width <= 1:
            width = container.winfo_reqwidth()
        label.configure(wraplength=max(min_width, width - padding))

    container.bind("<Configure>", update_wrap, add="+")
    label.after_idle(update_wrap)
    return label


def run_workbench_command(cmd: list[str], cwd: Path = ROOT, timeout: float | None = None) -> dict[str, object]:
    """Run a short workbench command without Tk dependencies and report completion state.

    This helper is intentionally small and synchronous so smoke tests can verify
    runner semantics in headless CI without creating a display-backed Tk root.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(cwd),
    )
    cancelled = False
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        cancelled = True
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
    return {
        "cmd": list(cmd),
        "returncode": proc.returncode,
        "finished": not cancelled and proc.returncode is not None,
        "cancelled": cancelled,
        "output": output or "",
    }


class Runner:
    """Run a subprocess in a background thread; stream output into a mode-filtered Tk console."""
    def __init__(self, tk_root: tk.Tk, output: tk.Text, write_console=None):
        self.root = tk_root
        self.output = output
        self.write_console = write_console or (lambda text, level="normal": console_write(self.output, text))
        self.q: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._proc_lock = threading.Lock()
        self.active_proc: subprocess.Popen[str] | None = None
        self.active_name: str = ""
        self._poll()

    def _poll(self):
        messages = []
        try:
            while True:
                messages.append(self.q.get_nowait())
        except queue.Empty:
            pass
        if messages:
            coalesced_messages = coalesce_progress_messages(messages)
            for level, text in coalesced_messages:
                self.write_console(text, level=level)
        self.root.after(80, self._poll)

    def run(self, cmd: list[str], cwd: Path = ROOT, on_done=None, on_line=None):
        with self._proc_lock:
            if self.active_proc is not None:
                self.q.put(("normal", f"[busy] Another task is already running: {self.active_name}\n"))
                return False
            self.active_name = Path(cmd[1]).name if len(cmd) > 1 else Path(cmd[0]).name
        self.q.put(("normal", "\n> " + " ".join(cmd) + "\n"))

        def worker():
            try:
                p = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(cwd),
                )
                with self._proc_lock:
                    self.active_proc = p
                assert p.stdout is not None
                for line in p.stdout:
                    level, sanitized = self._sanitize_line(line)
                    self.q.put((level, sanitized))
                    if on_line:
                        self.root.after(0, lambda s=line: on_line(s))
                p.wait()
                self.q.put(("normal", f"\n[exit {p.returncode}]\n"))
                if on_done:
                    self.root.after(0, lambda: on_done(p.returncode))
            except Exception as e:
                self.q.put(("normal", f"\n[error] {e}\n"))
                if on_done:
                    self.root.after(0, lambda: on_done(1))
            finally:
                with self._proc_lock:
                    self.active_proc = None
                    self.active_name = ""

        threading.Thread(target=worker, daemon=True).start()
        return True

    def cancel(self):
        with self._proc_lock:
            p = self.active_proc
        if p is None:
            self.q.put(("normal", "[cancel] No active task.\n"))
            return False
        try:
            p.terminate()
            self.q.put(("normal", "[cancel] Terminate requested.\n"))
        except Exception as e:
            self.q.put(("normal", f"[cancel] Failed to terminate: {e}\n"))
            return False
        return True

    def is_busy(self) -> bool:
        with self._proc_lock:
            return self.active_proc is not None

    def _sanitize_line(self, line: str) -> tuple[str, str]:
        s = line.rstrip("\n")
        stripped = s.strip()
        level = "debug" if stripped.startswith("{") or stripped.startswith("[{") else "verbose"
        if len(s) > 1200:
            s = s[:1200] + f"... [truncated {len(s) - 1200} chars]"
        return level, s + "\n"


class ScrollableFrame(ttk.Frame):
    """A ttk Frame with a vertical scrollbar so controls never wander off-screen."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse wheel scrolling is registered only while the pointer is over
        # this scrollable frame, so other tabs/widgets keep their native wheel
        # behavior.
        self._wheel_bind_ids: dict[str, str] = {}
        for widget in (self.canvas, self.inner):
            widget.bind("<Enter>", self._register_mousewheel)
            widget.bind("<Leave>", self._unregister_mousewheel_if_outside)

    def _on_inner_configure(self, _evt=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync_inner_height()

    def _on_canvas_configure(self, evt):
        self.canvas.itemconfig(self.inner_id, width=evt.width)
        self._sync_inner_height(evt.height)

    def _sync_inner_height(self, canvas_height: int | None = None):
        """Let packed/gridded children expand to the viewport without losing scrolling."""
        if canvas_height is None:
            canvas_height = self.canvas.winfo_height()
        requested_height = self.inner.winfo_reqheight()
        self.canvas.itemconfig(self.inner_id, height=max(requested_height, canvas_height))

    def _register_mousewheel(self, _evt=None):
        """Activate wheel bindings while the pointer is over this frame."""
        if self._wheel_bind_ids:
            return
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            bind_id = self.canvas.bind_all(sequence, self._on_mousewheel, add="+")
            if bind_id:
                self._wheel_bind_ids[sequence] = bind_id

    def _unregister_mousewheel_if_outside(self, _evt=None):
        """Deactivate wheel bindings after the pointer leaves this frame."""
        self.after_idle(self._unregister_mousewheel_if_pointer_outside)

    def _unregister_mousewheel_if_pointer_outside(self):
        if not self._pointer_inside():
            self._unregister_mousewheel()

    def _unregister_mousewheel(self):
        root = self.canvas._root()
        for sequence, bind_id in list(self._wheel_bind_ids.items()):
            root._unbind(("bind", "all", sequence), bind_id)
        self._wheel_bind_ids.clear()

    def _pointer_inside(self) -> bool:
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            left = self.winfo_rootx()
            top = self.winfo_rooty()
            right = left + self.winfo_width()
            bottom = top + self.winfo_height()
        except tk.TclError:
            return False
        return left <= x < right and top <= y < bottom

    def _event_in_native_scroller(self, widget: tk.Widget) -> bool:
        """Let nested widgets with native wheel behavior handle their own scroll."""
        native_scroll_classes = {"Text", "Listbox", "Treeview"}
        current: tk.Widget | None = widget
        while current is not None:
            try:
                if current.winfo_class() in native_scroll_classes:
                    return True
                if current == self.inner or current == self.canvas:
                    return False
                parent_name = current.winfo_parent()
                current = current.nametowidget(parent_name) if parent_name else None
            except (KeyError, tk.TclError):
                return False
        return False

    def _on_mousewheel(self, evt):
        if not self._pointer_inside():
            self._unregister_mousewheel()
            return None
        if self._event_in_native_scroller(evt.widget):
            return None

        if getattr(evt, "state", 0) & 0x0001:
            return None

        try:
            if getattr(evt, "num", None) == 4:
                delta = -1
            elif getattr(evt, "num", None) == 5:
                delta = 1
            else:
                delta = int(-1 * (evt.delta / 120))
            if delta:
                self.canvas.yview_scroll(delta, "units")
        except Exception:
            pass
        return None


class ActionBar(ttk.Frame):
    """A small responsive row that wraps child controls into multiple rows."""
    def __init__(self, parent, columns_at_width=None, item_padx=4, item_pady=3):
        super().__init__(parent)
        self._items: list[tk.Widget] = []
        self._columns_at_width = columns_at_width or [(900, 6), (700, 4), (480, 3)]
        self._item_padx = item_padx
        self._item_pady = item_pady
        self.bind("<Configure>", self._on_configure)

    def add_button(self, **kwargs):
        button = ttk.Button(self, **kwargs)
        self.add_widget(button)
        return button

    def add_widget(self, widget):
        self._items.append(widget)
        self._layout_items()
        return widget

    def _on_configure(self, _evt=None):
        self._layout_items()

    def _columns_for_width(self) -> int:
        actual_width = self.winfo_width()
        width = actual_width if actual_width > 1 else max(self.winfo_reqwidth(), 1)
        for min_width, columns in sorted(self._columns_at_width, reverse=True):
            if width >= min_width:
                return max(1, columns)
        return 2 if width >= 320 else 1

    def _layout_items(self):
        if not self._items:
            return
        columns = self._columns_for_width()
        for index, widget in enumerate(self._items):
            widget.grid(
                row=index // columns,
                column=index % columns,
                sticky="w",
                padx=(0 if index % columns == 0 else self._item_padx, self._item_padx),
                pady=self._item_pady,
            )
        for col in range(columns):
            self.grid_columnconfigure(col, weight=0)


class ActionSection(ttk.Labelframe):
    """Reusable titled action area with help text, responsive actions, status, and outputs."""

    def __init__(
        self,
        parent,
        title: str,
        description: str = "",
        *,
        status_variable: tk.Variable | None = None,
        progress_variable: tk.Variable | None = None,
        progress_text_variable: tk.Variable | None = None,
        include_progress: bool = False,
        output_buttons: list[dict] | None = None,
        columns_at_width=None,
    ):
        super().__init__(parent, text=title)
        self.grid_columnconfigure(0, weight=1)
        row = 0
        if description:
            self.description_label = ttk.Label(self, text=description, justify="left")
            self.description_label.grid(row=row, column=0, sticky="ew", padx=8, pady=(6, 4))
            _bind_wraplength(self.description_label, self, padding=24)
            row += 1
        self.action_bar = ActionBar(self, columns_at_width=columns_at_width)
        self.action_bar.grid(row=row, column=0, sticky="ew", padx=6, pady=(2, 4))
        row += 1
        self.status_label = None
        if status_variable is not None:
            self.status_label = ttk.Label(self, textvariable=status_variable, justify="left")
            self.status_label.grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 4))
            _bind_wraplength(self.status_label, self, padding=24)
            row += 1
        self.progress_frame = None
        self.progress_bar = None
        if include_progress or progress_variable is not None:
            self.progress_frame = ttk.Frame(self)
            self.progress_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 6))
            self.progress_frame.grid_columnconfigure(0, weight=1)
            self.progress_bar = ttk.Progressbar(self.progress_frame, maximum=100.0, variable=progress_variable, mode="determinate")
            self.progress_bar.grid(row=0, column=0, sticky="ew")
            if progress_text_variable is not None:
                ttk.Label(self.progress_frame, textvariable=progress_text_variable, width=14, anchor="e").grid(row=0, column=1, sticky="e", padx=(8, 0))
            row += 1
        self.output_bar = None
        if output_buttons:
            self.output_bar = ActionBar(self, columns_at_width=columns_at_width)
            self.output_bar.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 6))
            for spec in output_buttons:
                self.output_bar.add_button(**spec)
            row += 1
        self.next_row = row

    def add_content(self, widget: tk.Widget, **grid_kwargs):
        row = grid_kwargs.pop("row", self.next_row)
        widget.grid(row=row, column=0, sticky="ew", **grid_kwargs)
        self.next_row = max(self.next_row, row + 1)
        return widget

    def add_button(self, **kwargs):
        return self.action_bar.add_button(**kwargs)

    def add_buttons(self, button_specs: list[dict]) -> list[ttk.Button]:
        buttons = []
        for spec in button_specs:
            buttons.append(self.add_button(**spec))
        return buttons


class CeldraSprite(ttk.Frame):
    """Small local-only animated Celdra brand sprite."""

    FRAME_COUNT = 70

    def __init__(
        self,
        parent,
        frame_dir: Path,
        running_var: tk.BooleanVar,
        theme_getter=None,
        display_size: int = 112,
        delay_ms: int = 90,
    ):
        super().__init__(parent)
        self.frame_dir = frame_dir
        self.running_var = running_var
        self.theme_getter = theme_getter
        self.display_size = display_size
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._frame_index = 0
        self._raw_frames: list[tk.PhotoImage] = []
        self._frames: list[tk.PhotoImage] = []
        self._fallback_text = tk.StringVar(value="Celdra assets\nunavailable")

        self.image_label = tk.Label(self, bd=0, highlightthickness=0)
        self.fallback_label = ttk.Label(self, textvariable=self._fallback_text, justify="center")

        self._load_frames()
        self._show_current_mode()
        self.running_var.trace_add("write", lambda *_args: self._on_running_changed())
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.apply_theme()
        if self._frames and self.running_var.get():
            self._schedule_next()

    def _expected_frame_paths(self) -> list[Path]:
        return [self.frame_dir / f"{index:02d}.png" for index in range(1, self.FRAME_COUNT + 1)]

    def _load_frames(self) -> None:
        missing = [path.name for path in self._expected_frame_paths() if not path.exists()]
        if missing:
            self._fallback_text.set(f"Celdra assets\nmissing {len(missing)}/70")
            return

        loaded: list[tk.PhotoImage] = []
        for path in self._expected_frame_paths():
            try:
                loaded.append(tk.PhotoImage(file=str(path)))
            except tk.TclError:
                self._fallback_text.set(f"Celdra assets\ninvalid frame {path.name}")
                self._raw_frames = []
                self._frames = []
                return
        self._raw_frames = loaded
        self._frames = self._resize_frames(loaded, self.display_size)

    def _resize_frames(self, frames: list[tk.PhotoImage], size: int) -> list[tk.PhotoImage]:
        if not frames:
            return []
        size = max(32, int(size))
        if PIL_IMAGE and PIL_IMAGE_TK:
            resized: list[tk.PhotoImage] = []
            for path in self._expected_frame_paths():
                image = PIL_IMAGE.open(path).convert("RGBA")
                image.thumbnail((size, size), PIL_IMAGE.Resampling.LANCZOS)
                resized.append(PIL_IMAGE_TK.PhotoImage(image))
            return resized
        return frames

    def _show_current_mode(self) -> None:
        self.image_label.pack_forget()
        self.fallback_label.pack_forget()
        if self._frames:
            self.image_label.pack(fill="both", expand=True)
            self._show_frame()
        else:
            self.fallback_label.pack(fill="both", expand=True, padx=4, pady=4)

    def _show_frame(self) -> None:
        if not self._frames:
            return
        frame = self._frames[self._frame_index % len(self._frames)]
        self.image_label.configure(image=frame)

    def _schedule_next(self) -> None:
        self._cancel_after()
        if self._frames and self.running_var.get():
            self._after_id = self.after(self.delay_ms, self._advance)

    def _advance(self) -> None:
        self._after_id = None
        if not self._frames or not self.running_var.get():
            return
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self._show_frame()
        self._schedule_next()

    def _cancel_after(self) -> None:
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _on_running_changed(self) -> None:
        if self.running_var.get():
            self._schedule_next()
        else:
            self._cancel_after()

    def _on_destroy(self, _evt=None) -> None:
        self._cancel_after()

    def set_display_size(self, size: int) -> None:
        size = max(32, int(size))
        if size == self.display_size:
            return
        self.display_size = size
        if self._raw_frames and PIL_IMAGE and PIL_IMAGE_TK:
            self._frames = self._resize_frames(self._raw_frames, self.display_size)
            self._frame_index %= len(self._frames)
            self._show_current_mode()

    def set_visible(self, visible: bool) -> None:
        if visible:
            self._schedule_next()
        else:
            self._cancel_after()

    def apply_theme(self) -> None:
        palette = self.theme_getter() if self.theme_getter else {}
        bg = palette.get("bg", "#07110b")
        muted = palette.get("muted", "#9fb3a7")
        self.configure(style="TFrame")
        self.image_label.configure(bg=bg)
        self.fallback_label.configure(foreground=muted)


class FragmenterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(1100, 760)

        # Theme selection must exist before building header UI
        self.theme_name = tk.StringVar(value="Hack Green")
        self.celdra_animation_enabled = tk.BooleanVar(value=True)

        # Fonts + theme
        self._init_fonts()
        self._init_theme_system()
        # Ensure theme palette exists before building tabs
        self._theme = self.THEMES.get(self.theme_name.get(), next(iter(self.THEMES.values())))

        # ----- State -----
        self.project_root = tk.StringVar(value="")
        self.data_dir = tk.StringVar(value="")
        self.save_dir = tk.StringVar(value="")
        self.index_path = tk.StringVar(value=str(ROOT / "fragmenter_index.json"))
        self.index = None

        # Metadata-only export settings used by the normal, non-destructive GUI.
        # Legacy Easy Mods and advanced patch/install/reskin state lives in
        # tools.fragmenter_gui_legacy and is not initialized by normal startup.
        self.workspace_output_dir = tk.StringVar(value=str(WORKSPACE / "upload_package"))
        self.export_include_index = tk.BooleanVar(value=True)
        self.export_include_correlations = tk.BooleanVar(value=True)
        self.export_include_iso_index = tk.BooleanVar(value=False)
        self.export_include_binary_previews = tk.BooleanVar(value=True)
        self.research_bundle_include_full_paths = tk.BooleanVar(value=False)
        self.research_bundle_include_ccs_metadata_only = tk.BooleanVar(value=True)
        self.research_bundle_include_raw_assets = tk.BooleanVar(value=False)
        self.research_bundle_include_command_log = tk.BooleanVar(value=True)
        self.last_research_bundle_path: Path | None = None
        # ISO Explorer (read-only)
        self.iso_path = tk.StringVar(value="")
        self.data_bin_path = tk.StringVar(value="")
        self.iso_index_path = tk.StringVar(value=str(ROOT / "iso_index.json"))
        self.iso_extract_dir = tk.StringVar(value=str(ROOT / "iso_extract"))
        self.iso_status = tk.StringVar(value="Idle.")
        self.iso_index = None   # dict: norm_path -> entry
        self.iso_rows = []      # list of resolved rows
        self.iso_index_payload: dict | None = None
        self.iso_3d_candidates: list[dict] = []
        self.iso_3d_candidate_by_iid: dict[str, dict] = {}
        self.iso_3d_selected: dict | None = None
        self.iso_3d_embedded_candidates: list[dict] = []
        self.iso_3d_embedded_by_iid: dict[str, dict] = {}
        self.iso_3d_embedded_selected: dict | None = None
        self.iso_3d_search = tk.StringVar(value="")
        self.iso_3d_type_filter = tk.StringVar(value="(all)")
        self.iso_3d_min_size = tk.StringVar(value="")
        self.iso_3d_max_size = tk.StringVar(value="")
        self.iso_3d_show_low_confidence = tk.BooleanVar(value=False)
        self.ccsf_model_asset_path = tk.StringVar(value="")
        self.ccsf_viewer_asset_library_path = tk.StringVar(value=str(WORKSPACE / "reports" / "asset_library.json"))
        self.ccsf_viewer_extracted_folder = tk.StringVar(value=str(WORKSPACE / "extracted_ccs"))
        self.ccsf_viewer_asset_by_iid: dict[str, dict] = {}
        self.model_asset_filter_after_id: str | None = None
        self.model_asset_filter_display_limit = 500
        self.ccsf_viewer_selected_obj = tk.StringVar(value="")
        self.ccsf_viewer_report_path = tk.StringVar(value="Report path: none")
        self.ccsf_viewer_obj_summary = tk.StringVar(value="Selected OBJ: none")
        self.ccsf_model_decode_status = tk.StringVar(value="CCSF model decoder idle.")
        self.ccsf_model_decode_obj_paths: list[Path] = []
        self.ccsf_model_decode_report_path: Path | None = None
        self.ccsf_model_decode_output_dir: Path | None = None
        self.textures_images_decoded_png_by_key: dict[tuple[str, str], Path] = {}
        self.ccsf_structure_report: dict | None = None
        self.ccsf_structure_tree_by_iid: dict[str, dict] = {}
        self.iso_progress = tk.DoubleVar(value=0.0)
        self.iso_progress_text = tk.StringVar(value="")
        self.iso_current = tk.StringVar(value="")
        self.resource_map_path = tk.StringVar(value=str(ROOT / "resource_map.json"))
        self.correlation_store_path = tk.StringVar(value=str(ROOT / "fragmenter_correlations.json"))
        self.workflow_status_text = tk.StringVar(value="Workflow Status: select a SECTION first.")
        self.correlation_selected_hit_status = tk.StringVar(value="Selected hit status: none")
        self.current_resource_map: dict | None = None
        self.resource_map_context_bin: str | None = None
        self.resource_map_context_section: str | None = None
        self.resource_family_display_limit = 100
        self.resource_family_page_size = 100

        # ISO lightweight search
        self.iso_search_query = tk.StringVar(value="")
        self.iso_search_ext = tk.StringVar(value="")
        self.iso_search_prefix = tk.StringVar(value="")
        self.iso_search_limit = tk.IntVar(value=200)
        self.iso_search_max_scan = tk.IntVar(value=25000)
        self.iso_search_results = []
        self.iso_container_scan_cache: dict[str, dict] = {}
        self.iso_container_string_results: list[dict] = []
        self.console_mode = tk.StringVar(value="Normal")
        self.console_expanded = tk.BooleanVar(value=False)
        self.iso_batch_advanced = tk.BooleanVar(value=False)
        self.iso_batch_max_files = tk.IntVar(value=25)
        self.run_status = tk.StringVar(value="idle")
        self.resource_preview_items = 50
        self.resource_model_symbols: list[str] = []
        self.resource_related_assets: list[str] = []
        self.resource_suggested_searches: list[str] = []
        self.selected_family: dict | None = None
        self.selected_model_symbol = ""
        self.native_3d_preview_feasible = tk.BooleanVar(value=False)
        self.native_3d_preview_status = tk.StringVar(value="Select an extracted asset to evaluate native 3D preview feasibility.")
        self.area_crypto_input_path = tk.StringVar(value="")
        self.area_crypto_output_path = tk.StringVar(value=str(WORKSPACE / "area_server_crypto_out.bin"))
        self.area_encrypt_key_from_path = tk.StringVar(value="")
        self.area_encrypt_filekey_hex = tk.StringVar(value="")
        self.area_patch_exe_path = tk.StringVar(value="")
        self.area_server_tools_status = tk.StringVar(value="Area Server tools are idle.")

        # Preview / Container Inspector
        self.inspector_path = tk.StringVar(value="")
        self.inspector_status = tk.StringVar(value="Select a local binary file to inspect.")
        self.inspector_extract_dir = tk.StringVar(value=str(ROOT / "workspace" / "extracted" / "preview_candidates"))
        self.inspector_max_scan_mb = tk.IntVar(value=256)
        self.inspector_latest_preview: dict | None = None
        self.inspector_latest_preview_json: Path | None = None
        self.inspector_latest_scan: dict | None = None
        self.inspector_candidates: list[dict] = []
        self.text_hex_path: Path | None = None
        self.text_hex_data = b""
        self.text_hex_last_find = -1
        self.text_hex_offset = tk.StringVar(value="0")
        self.text_hex_length = tk.StringVar(value="4096")
        self.text_hex_encoding = tk.StringVar(value="UTF-8")
        self.text_hex_find = tk.StringVar(value="")
        self.text_hex_show_raw_anyway = tk.BooleanVar(value=False)
        self.text_hex_confidence = tk.StringVar(value="Confidence: low")
        self.project_tree_payloads: dict[str, dict] = {}
        self.ccsf_assets_folder = tk.StringVar(value=str(WORKSPACE / "extracted_ccs"))
        self.ccsf_selected_asset_path = tk.StringVar(value="")
        self.ccsf_asset_index: dict | None = None
        self.ccsf_asset_library: dict | None = None
        self.ccsf_asset_by_iid: dict[str, dict] = {}
        self.ccsf_asset_selection_generation = 0
        self.ccsf_manifest_payload: dict | None = None
        self.ccsf_manifest_progress = tk.DoubleVar(value=0.0)
        self.ccsf_manifest_progress_text = tk.StringVar(value="Idle")
        self.ccsf_manifest_worker_token = 0
        self.ccsf_filter_search = tk.StringVar(value="")
        self.ccsf_filter_type = tk.StringVar(value="All")
        self.ccsf_filter_variant = tk.StringVar(value="All")
        self.ccsf_filter_readiness = tk.StringVar(value="All")
        self.ccsf_filter_character_body = tk.BooleanVar(value=False)
        self.ccsf_filter_character_color_variant = tk.BooleanVar(value=False)
        self.ccsf_filter_environment_background = tk.BooleanVar(value=False)
        self.ccsf_filter_has_animation = tk.BooleanVar(value=False)
        self.ccsf_filter_has_texture_clt = tk.BooleanVar(value=False)
        self.ccsf_view_mode = tk.StringVar(value="logical")
        self.ccsf_show_physical_files = tk.BooleanVar(value=False)
        self.ccsf_show_duplicates = tk.BooleanVar(value=False)
        self.ccsf_show_unknown = tk.BooleanVar(value=False)
        self.ccsf_show_media_candidates = tk.BooleanVar(value=False)
        self.ccsf_filter_summary = tk.StringVar(value="Loading asset_library.json when available.")
        self.ccsf_scan_active = False
        self.ccsf_scan_queue: queue.Queue[tuple[str, object]] | None = None
        self.ccsf_scan_controls: list[tk.Widget] = []

        # ISO -> CCSF extraction workflow
        self.iso_ccsf_status = tk.StringVar(value="Idle. Choose an ISO, then build/load an index.")
        self.iso_ccsf_index_status = tk.StringVar(value="Index: not loaded")
        self.iso_ccsf_selected_containers = tk.StringVar(value="Selected top-level containers: none")
        self.iso_ccsf_scan_progress = tk.StringVar(value="Scan progress: idle")
        self.iso_ccsf_progress = tk.DoubleVar(value=0.0)
        self.iso_ccsf_progress_text = tk.StringVar(value="0% (0/0)")
        self.iso_ccsf_current_stage = tk.StringVar(value="Stage: idle")
        self.iso_ccsf_current_container = tk.StringVar(value="Current container: none")
        self.iso_ccsf_containers_scanned = tk.StringVar(value="Containers scanned: 0")
        self.iso_ccsf_bytes_scanned = tk.StringVar(value="Bytes scanned: 0")
        self.iso_ccsf_gzip_offsets_seen = tk.StringVar(value="Gzip offsets seen: 0")
        self.iso_ccsf_valid_gzip_members = tk.StringVar(value="Valid gzip members: 0")
        self.iso_ccsf_false_positives_skipped = tk.StringVar(value="False positives skipped: 0")
        self.iso_ccsf_bundles_found = tk.StringVar(value="CCSF bundles found: 0")
        self.iso_ccsf_duplicates_skipped = tk.StringVar(value="Duplicates skipped: 0")
        self.iso_ccsf_assets_indexed = tk.StringVar(value="Assets indexed: 0")
        self.iso_ccsf_errors_warnings = tk.StringVar(value="Errors/warnings: 0")
        self.iso_ccsf_output_paths = tk.StringVar(value="Output paths: not generated")
        self.iso_ccsf_report: dict | None = None
        self.iso_ccsf_bundle_by_iid: dict[str, dict] = {}
        self.iso_ccsf_manifest_payload: dict | None = None
        self.iso_ccsf_job_active = False
        self.iso_ccsf_cancel_requested = False
        self.iso_ccsf_cancel_event: threading.Event | None = None
        self.iso_ccsf_cancel_buttons: list[ttk.Button] = []

        # Setup / Scan workflow cards
        self.setup_asset_library_status = tk.StringVar(value="Idle. Build or refresh from extracted_ccs.")
        self.setup_asset_library_progress = tk.DoubleVar(value=0.0)
        self.setup_asset_library_progress_text = tk.StringVar(value="Idle")
        self.setup_survey_status = tk.StringVar(value="Idle. Survey ISO assets without extraction.")
        self.setup_survey_progress = tk.DoubleVar(value=0.0)
        self.setup_survey_progress_text = tk.StringVar(value="Idle")
        self.setup_media_pipeline_status = tk.StringVar(value="Idle. Run ISO media inventory, extraction, or audio decode.")
        self.setup_media_pipeline_progress = tk.DoubleVar(value=0.0)
        self.setup_media_pipeline_progress_text = tk.StringVar(value="Idle")
        self.audio_pipeline_status = tk.StringVar(value="Audio pipeline idle.")
        self.audio_playback_engine = AudioPlaybackEngine()
        self.audio_playback_status = tk.StringVar(value=self._audio_playback_capability_text())
        self.audio_primary_action_label = tk.StringVar(value="Primary Action")
        self.audio_pipeline_progress = tk.DoubleVar(value=0.0)
        self.audio_pipeline_progress_text = tk.StringVar(value="Idle")
        self.audio_pipeline_job_active = False
        self.audio_busy_action = tk.StringVar(value="Idle")
        self.audio_busy_cancel = threading.Event()
        self.audio_action_buttons: list[ttk.Button] = []
        self.raw_audio_source = tk.StringVar(value="")
        self.audio_library_container = tk.StringVar(value="")
        self.audio_library_manual_rows: list[dict[str, object]] = []
        self.raw_audio_encoding = tk.StringVar(value="s16le")
        self.raw_audio_channels = tk.IntVar(value=1)
        self.raw_audio_sample_rate = tk.IntVar(value=22050)
        self.raw_audio_start_offset = tk.StringVar(value="0")
        self.raw_audio_length = tk.StringVar(value="")
        self.raw_audio_end_offset = tk.StringVar(value="")
        self.raw_audio_probe_status = tk.StringVar(value="Raw audio probe idle.")
        self.raw_audio_latest_candidates: list[dict[str, object]] = []
        self.raw_audio_latest_region_map: dict[str, object] | None = None
        self.audio_stream_region_payloads: dict[str, dict[str, object]] = {}
        self.audio_stream_region_temp_wav: Path | None = None
        self.quick_report_locator_status = tk.StringVar(value="Click Refresh to locate existing reports.")
        self.quick_report_locator_rows: dict[str, tk.StringVar] = {}
        self.setup_checklist_status = self.quick_report_locator_status
        self.setup_checklist_rows: dict[str, tk.StringVar] = {}
        self.setup_preparation_status_vars: dict[str, tk.StringVar] = {}
        self.full_disc_preparation_status = tk.StringVar(value="Idle. RUN ALL executes steps sequentially.")
        self.full_disc_preparation_active = False
        self.full_disc_preparation_cancel_requested = False
        self.full_disc_step_vars: dict[str, tk.StringVar] = {}
        self.full_disc_preparation_results: list[dict[str, object]] = []

        self.external_viewer_path = tk.StringVar(value="")
        self.external_viewer_args = tk.StringVar(value=DEFAULT_ARGS_TEMPLATE)
        self.viewer_name = tk.StringVar(value=LEGACY_VIEWER_NAME)
        self.viewer_executable = tk.StringVar(value="")
        self.viewer_args = tk.StringVar(value=DEFAULT_ARGS_TEMPLATE)
        self.viewer_extensions = tk.StringVar(value="")
        self.viewer_enabled = tk.BooleanVar(value=True)
        self.viewer_choice = tk.StringVar(value="")
        self.external_viewers: list[ViewerConfig] = []
        self._app_settings_payload: dict = {}
        self._load_app_settings()
        self.research_launcher_buttons: dict[str, ttk.Button] = {}
        self.research_launchers: dict[str, dict[str, object]] = {}
        self.research_launcher_state: dict[str, dict[str, object]] = {}
        self.research_launcher_running = False
        self.latest_research_output: Path | None = None
        self.expected_report_tree: ttk.Treeview | None = None
        self.expected_report_payloads: dict[str, dict[str, object]] = {}
        self.expected_report_generate_button: ttk.Button | None = None
        self.root_town_tree: ttk.Treeview | None = None
        self.root_town_payloads: dict[str, dict[str, object]] = {}

        # ----- Workbench layout -----
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0, minsize=48)
        self.grid_columnconfigure(0, weight=1)

        self._build_workbench_title_status_strip()
        self._build_workbench_main_area()
        self._build_workbench_console()

        self.runner = Runner(self, self.console, write_console=self._console_write)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.apply_theme(self.theme_name.get())
        self._update_title_status_strip()
        self.after(150, self.load_index)
        self.after(250, self.refresh_project_tree)
        self.after(350, self.load_default_ccsf_asset_library)
        self.after(450, self.refresh_audio_wav_list)


    def _build_workbench_source_bar(self) -> None:
        """Build the top Workbench source/action bar."""
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        bar.grid_columnconfigure(0, weight=1)
        self._build_path_row(bar, "ISO", self.iso_path, browse_command=self.pick_iso, open_command=lambda: self._open_existing_variable_path(self.iso_path)).grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self._build_path_row(bar, "Area Server root", self.project_root, browse_command=self.pick_project, open_command=lambda: self._open_existing_variable_path(self.project_root)).grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self._build_path_row(bar, "Workspace", self.workspace_output_dir, browse_command=self.pick_workspace_output_dir, open_command=lambda: self._open_existing_variable_path(self.workspace_output_dir)).grid(row=2, column=0, sticky="ew")
        actions = ActionBar(bar, columns_at_width=[(1250, 7), (900, 4), (620, 3)])
        actions.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for text, command in [
            ("Load Project", self.load_project), ("Save Project", self.save_project),
            ("Quick Scan", self.quick_scan), ("Extract Common Town Assets", self.extract_common_town_assets),
            ("Catalog Extracted Assets", self.catalog_extracted_assets),
            ("Import Fragment Strings Workbook", self.import_fragment_strings_workbook_action),
            ("Open Report Folder", self.open_report_folder),
        ]:
            actions.add_button(text=text, style="Accent.TButton" if text == "Quick Scan" else "TButton", command=command)

    def _build_workbench_title_status_strip(self) -> None:
        """Build the compact Workbench title/status strip."""
        row = ttk.Frame(self)
        row.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        row.grid_columnconfigure(4, weight=1)
        self.title_status_vars = {
            "title": tk.StringVar(value=APP_TITLE),
            "safe": tk.StringVar(value="Safe Mode ON"),
            "job": tk.StringVar(value="idle"),
            "project": tk.StringVar(value="No project loaded"),
        }
        ttk.Label(row, textvariable=self.title_status_vars["title"], font=self.FONT_H2).grid(row=0, column=0, sticky="w", padx=(0, 10))
        for idx, key in enumerate(("safe", "job", "project"), start=1):
            ttk.Label(row, textvariable=self.title_status_vars[key], style="Chip.TLabel").grid(row=0, column=idx, sticky="w", padx=(0, 8))
        self.run_status.trace_add("write", lambda *_args: self._update_title_status_strip())

    def _build_workbench_main_area(self) -> None:
        """Build the primary workbench page tabs.

        The workbench shell intentionally owns only the top-level tab bar. Asset
        trees, inspectors, Celdra branding, and legacy controls are built by the
        pages that need them rather than being permanently visible beside every
        workflow.
        """
        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        self.research_launchers = self._research_launcher_metadata()
        self.page_frames: dict[str, ttk.Frame] = {}
        self.page_var = tk.StringVar(value="Setup / Scan")
        self.page_notebook = ttk.Notebook(body)
        self.page_notebook.grid(row=0, column=0, sticky="nsew")

        for label, builder in self._workbench_page_registry():
            frame = ttk.Frame(self.page_notebook)
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_columnconfigure(0, weight=1)
            self.page_frames[label] = frame
            self.page_notebook.add(frame, text=label)
            builder(frame)

        self.page_notebook.bind("<<NotebookTabChanged>>", self._on_workbench_page_changed)
        self.page_notebook.select(self.page_frames["Setup / Scan"])
        self._show_page("Setup / Scan")
        self.after_idle(lambda: self._show_page("Setup / Scan"))

    def _workbench_page_registry(self) -> tuple[tuple[str, object], ...]:
        """Return primary workbench pages in display order."""
        builders = (
            self._build_setup_scan_page,
            self._build_3d_asset_viewer_page,
            self._build_textures_images_page,
            self._build_audio_page,
            self._build_server_tools_page,
            self._build_more_page,
        )
        return tuple(zip(workflow_page_labels(), builders))


    def _build_textures_images_page(self, parent: ttk.Frame) -> None:
        """Build the Textures / Images two-pane workflow."""
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        ttk.Label(parent, text="Textures / Images", font=("TkDefaultFont", 14, "bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        split = ttk.Panedwindow(parent, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        left = ttk.Labelframe(split, text="Texture assets")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        toolbar = ttk.Frame(left)
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ttk.Button(toolbar, text="Refresh", command=self.refresh_textures_images_assets).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Load Asset Library", command=self.load_textures_images_asset_library).pack(side="left", padx=(0, 6))
        self.textures_images_status = tk.StringVar(value="Refresh to list TEX/CLT resources from asset_library.json and structure reports.")
        ttk.Label(toolbar, textvariable=self.textures_images_status).pack(side="left", fill="x", expand=True)
        cols = ("Asset", "TEX", "CLT", "Dimensions", "Format", "Status")
        self.textures_images_tree = ttk.Treeview(left, columns=cols, show="headings", height=18, selectmode="browse")
        widths = {"Asset": 180, "TEX": 160, "CLT": 160, "Dimensions": 100, "Format": 90, "Status": 160}
        for col in cols:
            self.textures_images_tree.heading(col, text=col)
            self.textures_images_tree.column(col, width=widths[col], stretch=(col in {"Asset", "Status"}))
        self.textures_images_tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        self.textures_images_tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.textures_images_tree.yview)
        self.textures_images_tree_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 8))
        self.textures_images_tree.configure(yscrollcommand=self.textures_images_tree_scroll.set)
        self.textures_images_tree.bind("<<TreeviewSelect>>", self.on_textures_images_select)
        self.textures_images_rows: dict[str, dict] = {}
        split.add(left, weight=3)

        right = ttk.Labelframe(split, text="Selected texture")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        actions = ttk.Frame(right)
        actions.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        for text, command in (
            ("Decode Selected Texture", self.decode_selected_texture_image),
            ("Export PNG", self.export_selected_texture_png),
            ("Open Source Asset", self.open_selected_texture_source_asset),
            ("Copy Source Path", self.copy_selected_texture_source_path),
        ):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 6))
        preview = ttk.Frame(right)
        preview.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        preview.grid_rowconfigure(0, weight=1)
        preview.grid_columnconfigure(0, weight=1)
        self.textures_images_preview_label = tk.Label(preview, text="No decoded PNG selected.", anchor="center", bg=self._theme["text_bg"], fg=self._theme["text_fg"])
        self.textures_images_preview_label.grid(row=0, column=0, sticky="nsew")
        self.textures_images_details = tk.Text(right, wrap="word", height=10, bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.textures_images_details.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        self._replace_text(self.textures_images_details, "Select a texture row to inspect TEX/CLT identifiers, palette info, and source paths.\n", readonly=True)
        self.textures_images_photo = None
        self.textures_images_decoded_png_by_key: dict[tuple[str, str], Path] = {}
        split.add(right, weight=2)
        self.after_idle(self.refresh_textures_images_assets)

    def load_textures_images_asset_library(self) -> None:
        self.load_ccsf_viewer_asset_library()
        self.after(50, self.refresh_textures_images_assets)

    def _texture_source_path_for_asset(self, asset: dict) -> Path:
        return self._ccsf_resolved_preferred_path(asset)

    def _texture_records_from_structure(self, asset: dict) -> tuple[list[dict], list[dict], dict | None]:
        path = self._texture_source_path_for_asset(asset)
        if not path.is_file():
            return [], [], None
        try:
            report = ccsf_structure_decoder.report_to_dict(ccsf_structure_decoder.decode(path))
        except Exception:
            return [], [], None
        records = list(report.get("records") or [])
        textures = [r for r in records if r.get("type_name") == "Texture"]
        palettes = [r for r in records if r.get("type_name") == "CLUT"]
        return textures, palettes, report

    def _texture_row_status(self, row: dict) -> str:
        key = (str(row.get("source_path") or ""), str(row.get("tex") or ""))
        png = getattr(self, "textures_images_decoded_png_by_key", {}).get(key)
        if png and png.is_file():
            return "Decoded PNG ready"
        if row.get("decode_note"):
            return str(row["decode_note"])
        return "TEX/CLT listed; decode pending"

    def refresh_textures_images_assets(self) -> None:
        tree = getattr(self, "textures_images_tree", None)
        if tree is None:
            return
        self.textures_images_rows = {}
        for iid in tree.get_children():
            tree.delete(iid)
        assets = list((self.ccsf_asset_library or {}).get("assets") or [])
        if not assets:
            path = Path(self.ccsf_viewer_asset_library_path.get().strip() or WORKSPACE / "reports" / "asset_library.json").expanduser()
            if path.is_file():
                try:
                    self.ccsf_asset_library = json.loads(path.read_text(encoding="utf-8"))
                    assets = list((self.ccsf_asset_library or {}).get("assets") or [])
                except Exception as exc:
                    self.textures_images_status.set(f"Could not load asset library: {exc}")
        shown = 0
        for index, asset in enumerate(assets):
            counts = self._ccsf_counts(asset)
            if int(counts.get("TEX", 0) or 0) <= 0 and int(counts.get("CLT", 0) or 0) <= 0:
                continue
            textures, palettes, _report = self._texture_records_from_structure(asset)
            if textures or palettes:
                count = max(len(textures), len(palettes), 1)
                for n in range(count):
                    tex = textures[n] if n < len(textures) else (textures[0] if textures else {})
                    clt = palettes[n] if n < len(palettes) else (palettes[0] if palettes else {})
                    row = {
                        "asset": asset,
                        "asset_name": self._ccsf_name(asset),
                        "tex": tex.get("object_name") or "",
                        "clt": clt.get("object_name") or "",
                        "tex_record": tex,
                        "clt_record": clt,
                        "source_path": str(self._texture_source_path_for_asset(asset)),
                    }
                    iid = f"texture_asset_{index}_{n}"
                    tree.insert("", "end", iid=iid, values=(row["asset_name"], row["tex"], row["clt"], "", "CCSF", self._texture_row_status(row)))
                    self.textures_images_rows[iid] = row
                    shown += 1
            else:
                row = {
                    "asset": asset,
                    "asset_name": self._ccsf_name(asset),
                    "tex": f"{counts.get('TEX', 0)} TEX",
                    "clt": f"{counts.get('CLT', 0)} CLT",
                    "source_path": str(self._texture_source_path_for_asset(asset)),
                    "decode_note": "Structure report unavailable",
                }
                iid = f"texture_asset_{index}"
                tree.insert("", "end", iid=iid, values=(row["asset_name"], row["tex"], row["clt"], "", "CCSF", self._texture_row_status(row)))
                self.textures_images_rows[iid] = row
                shown += 1
        self.textures_images_status.set(f"Showing {shown} texture-capable asset row(s).")

    def _selected_texture_image_row(self) -> dict | None:
        tree = getattr(self, "textures_images_tree", None)
        if tree is None or not tree.selection():
            return None
        return self.textures_images_rows.get(tree.selection()[0])

    def on_textures_images_select(self, _event=None) -> None:
        row = self._selected_texture_image_row()
        if not row:
            return
        source = Path(str(row.get("source_path") or ""))
        key = (str(source), str(row.get("tex") or ""))
        png = getattr(self, "textures_images_decoded_png_by_key", {}).get(key)
        lines = [
            "Texture Info",
            "============",
            f"Asset: {row.get('asset_name')}",
            f"TEX: {row.get('tex') or 'none'}",
            f"Format: CCSF Texture",
            f"Dimensions: not decoded" if not png else f"Decoded PNG: {png}",
            "",
            "Palette Info",
            "============",
            f"CLT: {row.get('clt') or 'none'}",
            "",
            "Source Path",
            "===========",
            str(source),
            "",
            "Status",
            "======",
            self._texture_row_status(row),
        ]
        self._replace_text(self.textures_images_details, "\n".join(lines) + "\n", readonly=True)
        if png and png.is_file():
            self._show_textures_images_png(png)
        else:
            self.textures_images_preview_label.configure(image="", text="No decoded PNG available.\nDecode requires real TEX pixels and CLT palette data.")
            self.textures_images_photo = None

    def _show_textures_images_png(self, path: Path) -> None:
        if not (PIL_IMAGE and PIL_IMAGE_TK):
            self.textures_images_preview_label.configure(image="", text=f"Decoded PNG:\n{path}")
            return
        image = PIL_IMAGE.open(path).convert("RGBA")
        image.thumbnail((420, 420), PIL_IMAGE.Resampling.LANCZOS)
        self.textures_images_photo = PIL_IMAGE_TK.PhotoImage(image)
        self.textures_images_preview_label.configure(image=self.textures_images_photo, text="")

    def _register_decoded_texture_png(self, source: Path, tex_name: str, png_path: Path) -> bool:
        """Record a verified decoded PNG for texture UI and 3D preview metadata."""
        if not png_path.is_file() or png_path.suffix.lower() != ".png":
            return False
        key = (str(source), tex_name)
        self.textures_images_decoded_png_by_key[key] = png_path
        selected_mesh = getattr(self, "ccsf_viewer_current_mesh", None)
        if selected_mesh is not None:
            texture_map = selected_mesh.source_metadata.setdefault("texture_png_paths", {})
            texture_map[tex_name] = str(png_path)
            selected_mesh.source_metadata["texture_source_path"] = str(source)
        return True

    def _decoded_texture_pngs_for_source(self, source: Path) -> dict[str, str]:
        return {
            tex_name: str(path)
            for (registered_source, tex_name), path in getattr(self, "textures_images_decoded_png_by_key", {}).items()
            if registered_source == str(source) and path.is_file()
        }

    def decode_selected_texture_image(self) -> None:
        row = self._selected_texture_image_row()
        if not row:
            return messagebox.showinfo("Textures / Images", "Select a texture row first.")
        source = Path(str(row.get("source_path") or ""))
        tex_name = str(row.get("tex") or "")
        clt_name = str(row.get("clt") or "")
        message = (
            "No PNG was produced. Fragmenter can list the real TEX/CLT records in this CCSF asset, "
            "but this build does not yet have a verified TEX pixel + CLT palette raster decoder for the selected record.\n\n"
            f"TEX: {tex_name or 'none'}\nCLT: {clt_name or 'none'}\nSource: {source}"
        )
        row["decode_note"] = "Decode unavailable; no fake PNG created"
        self.on_textures_images_select()
        messagebox.showinfo("Decode Selected Texture", message)

    def export_selected_texture_png(self) -> None:
        row = self._selected_texture_image_row()
        if not row:
            return messagebox.showinfo("Textures / Images", "Select a decoded texture row first.")
        source = Path(str(row.get("source_path") or ""))
        key = (str(source), str(row.get("tex") or ""))
        png = getattr(self, "textures_images_decoded_png_by_key", {}).get(key)
        if not (png and png.is_file()):
            return messagebox.showinfo("Export PNG", "No real decoded PNG is available for this TEX/CLT row.")
        dest = filedialog.asksaveasfilename(title="Export decoded PNG", defaultextension=".png", filetypes=[("PNG", "*.png")], initialfile=png.name)
        if dest:
            shutil.copy2(png, dest)

    def open_selected_texture_source_asset(self) -> None:
        row = self._selected_texture_image_row()
        if row:
            self._open_path_with_platform(Path(str(row.get("source_path") or "")))

    def copy_selected_texture_source_path(self) -> None:
        row = self._selected_texture_image_row()
        if row:
            self._copy_path_to_clipboard(Path(str(row.get("source_path") or "")))

    def _build_more_page(self, parent: ttk.Frame) -> None:
        """Build nested notebook for lower-frequency pages."""
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        self.more_notebook = ttk.Notebook(parent)
        self.more_notebook.grid(row=0, column=0, sticky="nsew")
        builders = (self._build_asset_library_page, self._build_reports_page, self._build_settings_legacy_page)
        self.more_page_frames = {}
        for label, builder in zip(more_page_labels(), builders):
            frame = ttk.Frame(self.more_notebook)
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_columnconfigure(0, weight=1)
            self.more_page_frames[label] = frame
            self.more_notebook.add(frame, text=label)
            builder(frame)

    def _build_setup_scan_page(self, parent: ttk.Frame) -> None:
        """Build the startup setup/scan page with project paths and scan context."""
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        scroll = ScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew")
        content = scroll.inner
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        setup = ttk.Labelframe(content, text="Setup / Scan")
        setup.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 6))
        setup.grid_columnconfigure(0, weight=1)

        actions = ActionBar(setup, columns_at_width=[(1250, 6), (900, 4), (620, 2)])
        actions.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 8))
        for text, command, style in (
            ("Load Project", self.load_project, "TButton"),
            ("Save Project", self.save_project, "TButton"),
        ):
            actions.add_button(text=text, command=command, style=style)

        path_specs = (
            ("ISO path", self.iso_path, self.pick_iso),
            ("Area Server root path", self.project_root, self.pick_project),
            ("Workspace path", self.workspace_output_dir, self.pick_workspace_output_dir),
            ("Optional Data folder path", self.data_dir, self.pick_data),
            ("Optional Save folder path", self.save_dir, self.pick_save),
        )
        for row, (label, variable, browse_command) in enumerate(path_specs, start=1):
            self._build_path_row(
                setup,
                label,
                variable,
                browse_command=browse_command,
                open_command=lambda v=variable: self._open_existing_variable_path(v),
            ).grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 6))

        full_disc = ttk.Labelframe(content, text="Full Disc Preparation")
        full_disc.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        full_disc.grid_columnconfigure(1, weight=1)
        ttk.Label(full_disc, text=RUN_ALL_CONFIRMATION_TEXT, wraplength=920, justify="left").grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=(8, 6))
        ttk.Button(full_disc, text="RUN ALL", command=self.run_full_disc_preparation, style="Accent.TButton").grid(row=1, column=0, sticky="w", padx=(10, 6), pady=(0, 8))
        ttk.Button(full_disc, text="DEEP DISC DISCOVERY", command=self.run_deep_disc_discovery).grid(row=1, column=1, sticky="w", padx=(0, 6), pady=(0, 8))
        ttk.Button(full_disc, text="Cancel All", command=self.cancel_full_disc_preparation).grid(row=1, column=2, sticky="w", padx=(0, 6), pady=(0, 8))
        ttk.Label(full_disc, textvariable=self.full_disc_preparation_status).grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=(0, 8))
        for r, step in enumerate(full_disc_preparation_steps(), start=2):
            var = tk.StringVar(value="Queued")
            self.full_disc_step_vars[step] = var
            ttk.Label(full_disc, text=step).grid(row=r, column=0, sticky="w", padx=(10, 6), pady=1)
            ttk.Label(full_disc, textvariable=var).grid(row=r, column=1, columnspan=3, sticky="ew", pady=1)

        workflow = ttk.Frame(content)
        workflow.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        workflow.grid_columnconfigure(0, weight=1)
        workflow.grid_columnconfigure(1, weight=1)
        workflow.grid_rowconfigure(0, weight=1)
        workflow.grid_rowconfigure(1, weight=1)
        self._build_setup_workflow_cards(workflow)

    def _build_setup_workflow_cards(self, parent: ttk.Frame) -> None:
        """Build the primary scan/report workflow cards for the setup page."""
        iso_card = ActionSection(
            parent,
            "ISO → CCSF Extraction",
            "Extract confirmed CCSF bundles from the selected ISO into extracted_ccs and write extraction/index reports.",
            status_variable=self.iso_ccsf_status,
            progress_variable=self.iso_ccsf_progress,
            progress_text_variable=self.iso_ccsf_progress_text,
            include_progress=True,
            output_buttons=[
                {"text": "Open extracted_ccs", "command": self.open_iso_ccsf_output_folder},
                {"text": "Open index TXT", "command": lambda: self._open_report_name("iso_ccsf_extraction_index.txt")},
                {"text": "Open index JSON", "command": lambda: self._open_report_name("iso_ccsf_extraction_index.json")},
                {"text": "Open dashboard", "command": self.open_ccsf_results_dashboard},
            ],
            columns_at_width=[(700, 3), (520, 2)],
        )
        iso_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        run_button = iso_card.add_button(text="Run", command=self.extract_iso_ccsf_library, style="Accent.TButton")
        cancel_button = iso_card.add_button(text="Cancel", command=self.cancel_iso_ccsf_job)
        self.iso_ccsf_cancel_button = cancel_button
        self.iso_ccsf_cancel_buttons.append(cancel_button)
        self._set_iso_ccsf_cancel_state()
        counters = ttk.Frame(iso_card)
        counters.grid_columnconfigure(1, weight=1)
        for r, (label, var) in enumerate((
            ("Bytes scanned", self.iso_ccsf_bytes_scanned),
            ("Containers scanned", self.iso_ccsf_containers_scanned),
            ("Gzip valid", self.iso_ccsf_valid_gzip_members),
            ("False positives skipped", self.iso_ccsf_false_positives_skipped),
            ("CCSF bundles found", self.iso_ccsf_bundles_found),
            ("Assets indexed", self.iso_ccsf_assets_indexed),
        )):
            ttk.Label(counters, text=f"{label}:").grid(row=r, column=0, sticky="w", padx=(0, 6), pady=1)
            ttk.Label(counters, textvariable=var, justify="left").grid(row=r, column=1, sticky="ew", pady=1)
        iso_card.add_content(counters, padx=8, pady=(0, 8))

        right_side = ttk.Frame(parent)
        right_side.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))
        right_side.grid_columnconfigure(0, weight=1)
        right_side.grid_rowconfigure(0, weight=1)

        prep = ttk.Labelframe(right_side, text="Preparation Actions")
        prep.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        prep.grid_columnconfigure(1, weight=1)
        prep_actions = (
            ("Build / Refresh Asset Library", "Run", self.run_setup_asset_library_refresh, self.setup_asset_library_progress_text, lambda: self._open_report_name("asset_library_dashboard.html")),
            ("Survey ISO Assets", "Run", self.run_setup_iso_asset_survey, self.setup_survey_progress_text, lambda: self._open_report_name("asset_survey_dashboard.html")),
            ("Scan / Decode Audio", "Run", self.run_setup_scan_decode_audio, self.setup_media_pipeline_progress_text, lambda: self._open_report_name("iso_audio_dashboard.html")),
            ("Analyze SNDDATA Music", "Run", self.run_setup_analyze_snddata_music, tk.StringVar(value="Ready when SNDDATA inputs exist"), lambda: self._open_report_name("snddata_pipeline_summary.txt")),
            ("Load Asset Library for Viewer", "Run", self.load_ccsf_viewer_asset_library, tk.StringVar(value="Ready when asset_library.json exists"), None),
            ("Open Reports Folder", "Open", self.open_report_folder, tk.StringVar(value="workspace/reports"), None),
            ("Open Extracted CCSF Folder", "Open", self.open_iso_ccsf_output_folder, tk.StringVar(value="workspace/extracted_ccs"), None),
            ("Open Model Output Folder", "Open", self.open_ccsf_model_output_folder, tk.StringVar(value="workspace/model_previews"), None),
        )
        for r, (name, button_text, command, status_var, open_command) in enumerate(prep_actions):
            self.setup_preparation_status_vars[name] = status_var
            ttk.Label(prep, text=name).grid(row=r, column=0, sticky="w", padx=(8, 6), pady=3)
            ttk.Label(prep, textvariable=status_var).grid(row=r, column=1, sticky="ew", pady=3)
            ttk.Button(prep, text=button_text, command=command, width=7).grid(row=r, column=2, sticky="e", padx=(6, 2), pady=2)
            if open_command is not None:
                ttk.Button(prep, text="Open", command=open_command, width=7).grid(row=r, column=3, sticky="e", padx=(2, 8), pady=2)

        media = ActionSection(
            right_side,
            "Whole ISO Media Pipeline",
            "Run compact media inventory, extraction, and audio decode tasks in the background.",
            status_variable=self.setup_media_pipeline_status,
            progress_variable=self.setup_media_pipeline_progress,
            progress_text_variable=self.setup_media_pipeline_progress_text,
            include_progress=True,
            columns_at_width=[(700, 3), (520, 2)],
        )
        media.grid(row=1, column=0, sticky="ew")
        self.setup_media_pipeline_progress_bar = media.progress_bar
        for text, mode in (
            ("Inventory", "inventory"),
            ("Extract", "extract"),
            ("Decode Audio", "decode"),
            ("Run Media Pipeline", "all"),
        ):
            media.add_button(text=text, command=lambda m=mode: self.run_setup_media_pipeline(m), style="Accent.TButton" if mode == "all" else "TButton")
        media.add_button(text="Open Media Dashboard", command=lambda: self._open_report_name("iso_media_dashboard.html"))
        media.add_button(text="Open Audio Dashboard", command=lambda: self._open_report_name("iso_audio_dashboard.html"))
        media.add_button(text="Open Media Output Folder", command=self.open_setup_media_output_folder)

        locator = ttk.Labelframe(parent, text="Setup Checklist / Quick Report Locator")
        locator.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        locator.grid_columnconfigure(1, weight=1)
        ttk.Label(locator, textvariable=self.quick_report_locator_status, justify="left").grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(8, 4))
        for r, spec in enumerate(SETUP_CHECKLIST_SPECS, start=1):
            key, label, _rel, _kind = spec
            var = tk.StringVar(value="❌ unchecked")
            self.setup_checklist_rows[key] = var
            ttk.Label(locator, text=label).grid(row=r, column=0, sticky="w", padx=(8, 6), pady=1)
            ttk.Label(locator, textvariable=var).grid(row=r, column=1, sticky="ew", pady=1)
        bar = ActionBar(locator, columns_at_width=[(700, 3), (520, 2)])
        bar.grid(row=len(SETUP_CHECKLIST_SPECS) + 1, column=0, columnspan=3, sticky="ew", padx=6, pady=(6, 8))
        bar.add_button(text="Refresh checklist", command=self.refresh_quick_report_locator)
        bar.add_button(text="Open Reports Folder", command=self.open_report_folder)
        bar.add_button(text="Open Workspace", command=lambda: self._open_folder_path(self._active_workspace_root()))

        reserved = ttk.Labelframe(parent, text="Reserved")
        reserved.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(reserved, text="Reserved for future branding / project status.", justify="center").grid(row=0, column=0, sticky="nsew", padx=12, pady=24)
        self.after_idle(self.refresh_quick_report_locator)

    def _build_asset_tree_panel(self, parent: ttk.Frame) -> None:
        self.tree = ttk.Treeview(parent, columns=("type", "gzip", "sections", "size", "paths", "TEX", "MDL", "DMY", "MAT", "ANM"), height=18)
        self.tree.heading("#0", text="Name / Section")
        for col, text in [("type","Type"),("gzip","GZip"),("sections","Secs"),("size","Size"),("paths","Paths"),("TEX","TEX"),("MDL","MDL"),("DMY","DMY"),("MAT","MAT"),("ANM","ANM")]:
            self.tree.heading(col, text=text)
        self.tree.column("#0", width=260)
        for col, width, anchor in [("type",58,"center"),("gzip",44,"center"),("sections",55,"e"),("size",85,"e"),("paths",55,"e"),("TEX",48,"e"),("MDL",48,"e"),("DMY",48,"e"),("MAT",48,"e"),("ANM",48,"e")]:
            self.tree.column(col, width=width, anchor=anchor, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
        yscroll = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns", padx=(0,8), pady=8)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<ButtonRelease-1>", self._schedule_on_select)
        self.tree.bind("<KeyRelease>", self._schedule_on_select)
        self.tree.tag_configure("binrow", background=self._theme["row_bin_bg"], foreground=self._theme["fg"])
        self.tree.tag_configure("secrow", background=self._theme["row_sec_bg"], foreground=self._theme["fg"])

    def _build_selection_inspector_panel(self, parent: ttk.Frame, row: int = 0) -> None:
        inspector = ttk.Labelframe(parent, text="Inspector")
        inspector.grid(row=row, column=0, sticky="nsew", pady=(0,8))
        inspector.grid_columnconfigure(0, weight=1)
        self.resource_preview_message = tk.StringVar(value="Select an asset or run a scan to inspect metadata.")
        ttk.Label(inspector, textvariable=self.resource_preview_message, justify="left", wraplength=260).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.selection_inspector = tk.Text(inspector, height=16, width=34, wrap="word", bg=self._theme["text_bg"], fg=self._theme["text_fg"], relief="flat")
        self.selection_inspector.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0,8))
        self._replace_text(self.selection_inspector, "Select an asset tree item, identifier, report hit, or member node.\n", readonly=True)
        self.inspector_action_frame = ttk.Frame(inspector)
        self.inspector_action_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0,8))
        for col in range(2):
            self.inspector_action_frame.grid_columnconfigure(col, weight=1)
        self.inspector_action_buttons: dict[str, ttk.Button] = {}
        for i, action in enumerate((
            "Preview Texture", "Preview 3D", "Open Text/Hex", "Export Raw",
            "Extract Member", "Run Catalog", "Add to Patch Plan", "Open Containing Folder",
        )):
            btn = ttk.Button(self.inspector_action_frame, text=action, command=lambda a=action: self._run_safe_action(a))
            btn.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0 if i % 2 == 0 else 4, 0), pady=2)
            self.inspector_action_buttons[action] = btn
        self.inspector_action_hint = tk.StringVar(value="")
        ttk.Label(inspector, textvariable=self.inspector_action_hint, justify="left", wraplength=260).grid(row=3, column=0, sticky="ew", padx=8, pady=(0,8))

    def _build_3d_asset_viewer_page(self, parent: ttk.Frame) -> None:
        """Build the focused CCSF 3D search/select/preview workbench."""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=0)

        filters = ttk.Frame(parent)
        filters.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 6))
        filters.grid_columnconfigure(1, weight=1)
        ttk.Label(filters, text="Search", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(filters, textvariable=self.ccsf_filter_search).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(filters, text="Type").grid(row=0, column=2, sticky="w", padx=(0, 4))
        self.ccsf_viewer_type_filter_combo = ttk.Combobox(filters, textvariable=self.ccsf_filter_type, values=("All",), state="readonly", width=16)
        self.ccsf_viewer_type_filter_combo.grid(row=0, column=3, sticky="ew", padx=(0, 8))
        ttk.Label(filters, text="Model-ready").grid(row=0, column=4, sticky="w", padx=(0, 4))
        self.ccsf_viewer_readiness_filter_combo = ttk.Combobox(filters, textvariable=self.ccsf_filter_readiness, values=("All", "model-ready"), state="readonly", width=14)
        self.ccsf_viewer_readiness_filter_combo.grid(row=0, column=5, sticky="ew", padx=(0, 8))
        ttk.Button(filters, text="Refresh / Load Asset Library", command=self.load_ccsf_viewer_asset_library).grid(row=0, column=6, sticky="e", padx=(0, 8))
        ttk.Label(filters, textvariable=self.ccsf_filter_summary).grid(row=0, column=7, sticky="e")
        for var in (self.ccsf_filter_search, self.ccsf_filter_type, self.ccsf_filter_readiness):
            var.trace_add("write", lambda *_args: self.schedule_ccsf_viewer_asset_list_refresh())

        source = ttk.Labelframe(parent, text="Source settings")
        source.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        source.grid_columnconfigure(0, weight=1)
        self._build_path_row(source, "Asset library JSON", self.ccsf_viewer_asset_library_path, browse_command=self.pick_ccsf_viewer_asset_library, open_command=lambda: self._open_existing_variable_path(self.ccsf_viewer_asset_library_path), browse_text="Choose file").grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 3))
        self._build_path_row(source, "Extracted CCSF folder", self.ccsf_viewer_extracted_folder, browse_command=self.pick_ccsf_viewer_extracted_folder, open_command=lambda: self._open_existing_variable_path(self.ccsf_viewer_extracted_folder), browse_text="Choose folder").grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

        middle = ttk.Panedwindow(parent, orient="horizontal")
        middle.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        table_frame = ttk.Labelframe(middle, text="Assets")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        cols = ccsf_viewer_default_columns()
        self.ccsf_viewer_assets_tree = ttk.Treeview(table_frame, columns=cols, show="tree headings", height=14)
        self.ccsf_viewer_assets_tree.heading("#0", text="Display name")
        self.ccsf_viewer_assets_tree.column("#0", width=210, stretch=True)
        for col, width in (("type", 115), ("variant", 80), ("MDL", 45), ("TEX", 45), ("CLT", 45), ("ANM", 45), ("OBJ", 45)):
            self.ccsf_viewer_assets_tree.heading(col, text=col)
            self.ccsf_viewer_assets_tree.column(col, width=width, stretch=False, anchor="e" if col.isupper() else "w")
        self.ccsf_viewer_assets_tree.grid(row=0, column=0, sticky="nsew")
        viewer_tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.ccsf_viewer_assets_tree.yview)
        viewer_tree_scroll.grid(row=0, column=1, sticky="ns")
        self.ccsf_viewer_assets_tree.configure(yscrollcommand=viewer_tree_scroll.set)
        self.ccsf_viewer_assets_tree.bind("<<TreeviewSelect>>", self.on_ccsf_viewer_asset_select)
        middle.add(table_frame, weight=2)

        preview = ttk.Labelframe(middle, text="3D Preview")
        preview.grid_rowconfigure(0, weight=1)
        preview.grid_columnconfigure(0, weight=1)
        self.ccsf_viewer_tabs = ttk.Notebook(preview)
        self.ccsf_viewer_tabs.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.ccsf_preview_tab = ttk.Frame(self.ccsf_viewer_tabs)
        self.ccsf_info_tab = ttk.Frame(self.ccsf_viewer_tabs)
        self.ccsf_decode_tab = ttk.Frame(self.ccsf_viewer_tabs)
        self.ccsf_actions_tab = ttk.Frame(self.ccsf_viewer_tabs)
        for frame, label in ((self.ccsf_preview_tab, "Preview"), (self.ccsf_info_tab, "Asset Info"), (self.ccsf_decode_tab, "Decode Report"), (self.ccsf_actions_tab, "Actions")):
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)
            self.ccsf_viewer_tabs.add(frame, text=label)
        self.ccsf_preview_placeholder = ttk.Label(self.ccsf_preview_tab, text="Select an asset, run Decode Selected Model, then select an OBJ if one is produced.", anchor="center", justify="center")
        self.ccsf_preview_placeholder.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.ccsf_viewer_details = tk.Text(self.ccsf_info_tab, height=8, wrap="word", bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.ccsf_viewer_details.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        details_scroll = ttk.Scrollbar(self.ccsf_info_tab, orient="vertical", command=self.ccsf_viewer_details.yview)
        details_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.ccsf_viewer_details.configure(yscrollcommand=details_scroll.set)
        info_buttons = ttk.Frame(self.ccsf_info_tab); info_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        for text, cmd in (("Copy Asset Path", self.copy_ccsf_viewer_asset_path), ("Open Asset File", self.open_ccsf_viewer_asset_file), ("Open Containing Folder", self.open_ccsf_viewer_containing_folder)):
            ttk.Button(info_buttons, text=text, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Label(self.ccsf_decode_tab, textvariable=self.ccsf_model_decode_status).grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        ttk.Label(self.ccsf_decode_tab, textvariable=self.ccsf_viewer_report_path).grid(row=1, column=0, sticky="ew", padx=8, pady=2)
        self.ccsf_viewer_obj_list = tk.Listbox(self.ccsf_decode_tab, height=4, exportselection=False)
        self.ccsf_viewer_obj_list.grid(row=2, column=0, sticky="ew", padx=(8, 0), pady=2)
        obj_scroll = ttk.Scrollbar(self.ccsf_decode_tab, orient="vertical", command=self.ccsf_viewer_obj_list.yview)
        obj_scroll.grid(row=2, column=1, sticky="ns", padx=(0, 8), pady=2)
        self.ccsf_viewer_obj_list.configure(yscrollcommand=obj_scroll.set)
        self.ccsf_viewer_obj_list.bind("<<ListboxSelect>>", self.on_ccsf_viewer_obj_select)
        ttk.Label(self.ccsf_decode_tab, textvariable=self.ccsf_viewer_obj_summary).grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=2)
        self.ccsf_structure_tree = ttk.Treeview(self.ccsf_decode_tab, columns=("kind", "count", "offset", "bounds"), show="tree headings", height=8)
        self.ccsf_structure_tree.heading("#0", text="CCSF hierarchy")
        for col, width in (("kind", 120), ("count", 70), ("offset", 110), ("bounds", 220)):
            self.ccsf_structure_tree.heading(col, text=col)
            self.ccsf_structure_tree.column(col, width=width, stretch=(col == "bounds"))
        self.ccsf_structure_tree.grid(row=4, column=0, sticky="nsew", padx=(8, 0), pady=(2, 4))
        tree_scroll = ttk.Scrollbar(self.ccsf_decode_tab, orient="vertical", command=self.ccsf_structure_tree.yview)
        tree_scroll.grid(row=4, column=1, sticky="ns", padx=(0, 8), pady=(2, 4))
        self.ccsf_structure_tree.configure(yscrollcommand=tree_scroll.set)
        self.ccsf_structure_tree.bind("<<TreeviewSelect>>", self.on_ccsf_structure_tree_select)
        self.ccsf_model_decode_report_text = tk.Text(self.ccsf_decode_tab, height=8, wrap="word", bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.ccsf_model_decode_report_text.grid(row=5, column=0, sticky="nsew", padx=(8, 0), pady=(2, 8))
        report_scroll = ttk.Scrollbar(self.ccsf_decode_tab, orient="vertical", command=self.ccsf_model_decode_report_text.yview)
        report_scroll.grid(row=5, column=1, sticky="ns", padx=(0, 8), pady=(2, 8))
        self.ccsf_model_decode_report_text.configure(yscrollcommand=report_scroll.set)
        self.ccsf_decode_tab.grid_rowconfigure(4, weight=1)
        self.ccsf_decode_tab.grid_rowconfigure(5, weight=1)
        actions = (("Parse CCS Structure", self.run_ccsf_viewer_model_decoder), ("Decode Selected Model", self.run_ccsf_viewer_model_decoder), ("Export Confirmed OBJ", self.open_ccsf_model_generated_obj), ("Open Structure Report", self.open_ccsf_structure_report), ("Open Model Output Folder", self.open_ccsf_model_output_folder), ("Legacy Heuristic Diagnostics", self.run_ccsf_legacy_heuristic_diagnostics), ("Copy Asset Path", self.copy_ccsf_viewer_asset_path), ("Open Asset File", self.open_ccsf_viewer_asset_file), ("Open Containing Folder", self.open_ccsf_viewer_containing_folder))
        for i, (text, cmd) in enumerate(actions):
            state = "disabled" if text == "Export Confirmed OBJ" else "normal"
            btn = ttk.Button(self.ccsf_actions_tab, text=text, command=cmd, state=state)
            btn.grid(row=i, column=0, sticky="ew", padx=12, pady=4)
            if text == "Export Confirmed OBJ": self.ccsf_viewer_open_obj_button = btn
        middle.add(preview, weight=3)

        bottom = ttk.Panedwindow(parent, orient="horizontal")
        bottom.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        reserved = ttk.Labelframe(bottom, text="Reserved")
        ttk.Label(reserved, text="Reserved for branding / future functionality.").grid(row=0, column=0, sticky="ew", padx=12, pady=16)
        anim = ttk.Labelframe(bottom, text="Animation / Playback Controls")
        for i, text in enumerate(("Play", "Pause")):
            ttk.Button(anim, text=text, state="disabled").grid(row=0, column=i, padx=6, pady=8)
        ttk.Scale(anim, from_=0, to=100, state="disabled").grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Combobox(anim, values=("Animation selector",), state="disabled", width=20).grid(row=0, column=3, padx=6)
        ttk.Label(anim, text="Animation decode not implemented yet.").grid(row=1, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 8))
        anim.grid_columnconfigure(2, weight=1)
        bottom.add(reserved, weight=1); bottom.add(anim, weight=1)
        self._replace_text(self.ccsf_viewer_details, "Load asset_library.json to select a CCSF asset.\n", readonly=True)
        self._replace_text(self.ccsf_model_decode_report_text, "CCS structure parse output will appear here.\n", readonly=True)
        self.load_ccsf_viewer_asset_library(silent=True)

    def pick_ccsf_viewer_asset_library(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose CCSF asset_library.json",
            initialdir=str(Path(self.ccsf_viewer_asset_library_path.get()).expanduser().parent),
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.ccsf_viewer_asset_library_path.set(path)

    def pick_ccsf_viewer_extracted_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose extracted CCSF folder", initialdir=self.ccsf_viewer_extracted_folder.get())
        if folder:
            self.ccsf_viewer_extracted_folder.set(folder)
            self.ccsf_assets_folder.set(folder)
            self.schedule_ccsf_viewer_asset_list_refresh(delay_ms=0)

    def load_ccsf_viewer_asset_library(self, silent: bool = False) -> None:
        path = Path(self.ccsf_viewer_asset_library_path.get().strip() or WORKSPACE / "reports" / "asset_library.json").expanduser()
        if not path.exists():
            if not silent:
                messagebox.showinfo("Asset library", f"Asset library not found:\n{path}")
            return
        try:
            self.ccsf_asset_library = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.ccsf_filter_summary.set(f"Could not load asset library: {exc}")
            if not silent:
                messagebox.showerror("Asset library", f"Could not load:\n{path}\n\n{exc}")
            return
        self.ccsf_view_mode.set("logical")
        self.ccsf_assets_folder.set(self.ccsf_viewer_extracted_folder.get())
        self._update_ccsf_viewer_filter_choices()
        self.schedule_ccsf_viewer_asset_list_refresh(delay_ms=0)

    def _update_ccsf_viewer_filter_choices(self) -> None:
        assets = list((self.ccsf_asset_library or {}).get("assets") or [])
        types = sorted({str(asset.get("type") or "unknown") for asset in assets})
        readiness = sorted({str(asset.get("readiness") or "unknown") for asset in assets})
        if hasattr(self, "ccsf_viewer_type_filter_combo"):
            self.ccsf_viewer_type_filter_combo.configure(values=("All", *types))
        if hasattr(self, "ccsf_viewer_readiness_filter_combo"):
            self.ccsf_viewer_readiness_filter_combo.configure(values=("All", "model-ready", *readiness))

    def _ccsf_viewer_selected_asset(self) -> dict | None:
        tree = getattr(self, "ccsf_viewer_assets_tree", None)
        if tree is None:
            return None
        selection = tree.selection()
        return self.ccsf_viewer_asset_by_iid.get(selection[0]) if selection else None

    def _ccsf_viewer_asset_matches_filters(self, asset: dict) -> bool:
        asset_type = str(asset.get("type") or "unknown")
        readiness = str(asset.get("readiness") or "unknown")
        if self.ccsf_filter_type.get() != "All" and asset_type != self.ccsf_filter_type.get():
            return False
        readiness_filter = self.ccsf_filter_readiness.get()
        if readiness_filter == "model-ready":
            counts = self._ccsf_counts(asset)
            if int(counts.get("MDL", 0) or 0) <= 0 and "model" not in readiness.lower():
                return False
        elif readiness_filter != "All" and readiness != readiness_filter:
            return False
        query = self.ccsf_filter_search.get().strip().lower()
        if query:
            return ccsf_asset_matches_query(asset, query)
        return True

    def schedule_ccsf_viewer_asset_list_refresh(self, delay_ms: int = 180) -> None:
        """Debounce refreshes for the dedicated 3D Asset Viewer filter controls."""
        after_id = getattr(self, "model_asset_filter_after_id", None)
        if after_id:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
            self.model_asset_filter_after_id = None
        self.model_asset_filter_after_id = self.after(delay_ms, self.refresh_ccsf_viewer_asset_list)

    def refresh_ccsf_viewer_asset_list(self) -> None:
        self.model_asset_filter_after_id = None
        tree = getattr(self, "ccsf_viewer_assets_tree", None)
        if tree is None:
            return
        self._update_ccsf_viewer_filter_choices()
        self.ccsf_assets_folder.set(self.ccsf_viewer_extracted_folder.get())
        assets = list((self.ccsf_asset_library or {}).get("assets") or [])
        self.ccsf_viewer_asset_by_iid = {}
        for iid in tree.get_children():
            tree.delete(iid)
        shown = 0
        matched = 0
        limit = int(getattr(self, "model_asset_filter_display_limit", 500) or 500)
        for n, asset in enumerate(assets):
            if not self._ccsf_viewer_asset_matches_filters(asset):
                continue
            matched += 1
            if shown >= limit:
                continue
            counts = self._ccsf_counts(asset)
            iid = f"ccsf_viewer_asset_{n}"
            tree.insert("", "end", iid=iid, text=self._ccsf_name(asset), values=(asset.get("type", ""), asset.get("variant") or "-", counts.get("MDL", 0), counts.get("TEX", 0), counts.get("CLT", 0), counts.get("ANM", 0), counts.get("OBJ", 0)))
            self.ccsf_viewer_asset_by_iid[iid] = asset
            shown += 1
        self.ccsf_filter_summary.set(f"Showing {shown} of {matched} matching assets")

    def _ccsf_viewer_preferred_path_from_metadata(self, asset: dict) -> Path:
        label = self._ccsf_file(asset)
        path = Path(label).expanduser()
        if path.is_absolute():
            return path
        folder = Path(self.ccsf_viewer_extracted_folder.get().strip() or WORKSPACE / "extracted_ccs").expanduser()
        return folder / label

    def _ccsf_viewer_prepare_selected_asset(self) -> dict | None:
        asset = self._ccsf_viewer_selected_asset()
        if not asset:
            messagebox.showinfo("CCSF 3D asset", "Select an asset first.")
            return None
        path = self._ccsf_resolved_preferred_path(asset)
        self.ccsf_model_asset_path.set(str(path))
        return asset

    def on_ccsf_viewer_asset_select(self, _event=None) -> None:
        asset = self._ccsf_viewer_selected_asset()
        if not asset:
            return
        metadata_path = self._ccsf_viewer_preferred_path_from_metadata(asset)
        self.ccsf_selected_asset_path.set(str(metadata_path))
        self.ccsf_model_asset_path.set(str(metadata_path))
        self.ccsf_model_decode_obj_paths = []
        self.ccsf_structure_report = None
        self._populate_ccsf_structure_tree(None)
        if hasattr(self, "ccsf_model_open_obj_button"):
            self.ccsf_model_open_obj_button.configure(state="disabled")
        if hasattr(self, "ccsf_viewer_open_obj_button"):
            self.ccsf_viewer_open_obj_button.configure(state="disabled")
        if hasattr(self, "ccsf_viewer_obj_list"):
            self.ccsf_viewer_obj_list.delete(0, "end")
        self.ccsf_viewer_report_path.set("Report path: none")
        self.ccsf_viewer_obj_summary.set("Selected OBJ: none")
        self._replace_text(self.ccsf_viewer_details, self._format_ccsf_asset_details(asset), readonly=True)

    def copy_ccsf_viewer_asset_path(self) -> None:
        asset = self._ccsf_viewer_prepare_selected_asset()
        if asset:
            self._copy_path_to_clipboard(self._ccsf_resolved_preferred_path(asset))

    def open_ccsf_viewer_asset_file(self) -> None:
        asset = self._ccsf_viewer_prepare_selected_asset()
        if asset:
            path = self._ccsf_resolved_preferred_path(asset)
            if path.exists():
                self._open_path_with_platform(path)
            else:
                messagebox.showinfo("Asset file", f"Asset file not found:\n{path}")

    def open_ccsf_viewer_containing_folder(self) -> None:
        asset = self._ccsf_viewer_prepare_selected_asset()
        if asset:
            self._open_folder_path(self._ccsf_resolved_preferred_path(asset).parent)

    def build_ccsf_viewer_preview_manifest(self) -> None:
        if self._ccsf_viewer_prepare_selected_asset():
            self.build_ccsf_model_preview_manifest()

    def run_ccsf_viewer_model_decoder(self) -> None:
        if self._ccsf_viewer_prepare_selected_asset():
            self.run_ccsf_model_decoder()

    def _ccsf_record_bounds_text(self, rec: dict) -> str:
        start = rec.get("payload_start")
        end = rec.get("payload_end")
        if isinstance(start, int) and isinstance(end, int):
            return f"0x{start:X}:0x{end:X}"
        return ""

    def _populate_ccsf_structure_tree(self, report: dict | None) -> None:
        tree = getattr(self, "ccsf_structure_tree", None)
        if tree is None:
            return
        self.ccsf_structure_tree_by_iid = {}
        for iid in tree.get_children():
            tree.delete(iid)
        if not report:
            tree.insert("", "end", text="CCSF", values=("unparsed", "", "", ""))
            return
        records = list(report.get("records") or [])
        root = tree.insert("", "end", text="CCSF", values=("root", "", f"size {report.get('size', 0)}", ""))
        header = report.get("header") or {}
        tree.insert(root, "end", text=f"Header: {header.get('name') or '-'}", values=("Header", "", f"0x{int(header.get('offset') or 0):X}", f"version 0x{int(header.get('version') or 0):04X} {header.get('generation') or ''}"))
        subfiles = tree.insert(root, "end", text="Sub Files", values=("IndexFile", len(report.get("file_index") or []), "", ""))
        for entry in report.get("file_index") or []:
            tree.insert(subfiles, "end", text=entry.get("name") or f"file {entry.get('id')}", values=("Sub File", len(entry.get("owned_object_ids") or []), f"id {entry.get('id')}", ""))
        objects = tree.insert(root, "end", text="Objects", values=("IndexObject", len(report.get("object_index") or []), "", ""))
        for entry in (report.get("object_index") or [])[:250]:
            tree.insert(objects, "end", text=entry.get("name") or f"object {entry.get('id')}", values=(entry.get("section_type_name") or "", "", f"0x{int(entry.get('section_offset') or 0):X}", entry.get("file_name") or ""))
        categories = [
            ("Clumps", {"Clump"}),
            ("Models", {"Model"}),
            ("Materials", {"Material"}),
            ("Textures", {"Texture", "CLUT"}),
            ("Animations", {"Animation", "PCM Audio"}),
            ("Collision", {"Hit Mesh"}),
            ("Dummies", {"Dummy(Position)", "Dummy(Position & Rotation)"}),
        ]
        for label, names in categories:
            subset = [rec for rec in records if rec.get("type_name") in names]
            parent = tree.insert(root, "end", text=label, values=("Section", len(subset), "", ""))
            for rec in subset:
                iid = tree.insert(parent, "end", text=rec.get("object_name") or f"object {rec.get('object_id')}", values=(rec.get("type_name") or "", rec.get("parse_status") or "", f"0x{int(rec.get('offset') or 0):X}", self._ccsf_record_bounds_text(rec)))
                self.ccsf_structure_tree_by_iid[iid] = rec
                model = rec.get("model") if isinstance(rec.get("model"), dict) else None
                for sub in (model or {}).get("submodels") or []:
                    tree.insert(iid, "end", text=f"Submodel {sub.get('index')}", values=("Submodel", sub.get("vertex_count", ""), f"0x{int(sub.get('payload_start') or 0):X}" if sub.get("payload_start") is not None else "", f"0x{int(sub.get('payload_end') or 0):X}" if sub.get("payload_end") is not None else ""))
        tree.item(root, open=True)

    def on_ccsf_structure_tree_select(self, _event=None) -> None:
        tree = getattr(self, "ccsf_structure_tree", None)
        if tree is None or not tree.selection():
            return
        rec = self.ccsf_structure_tree_by_iid.get(tree.selection()[0])
        if rec:
            self._replace_text(self._ccsf_model_report_text_widget(), self._format_ccsf_selected_model_report(rec, getattr(self, "ccsf_structure_report", {}) or {}), readonly=True)

    def on_ccsf_viewer_obj_select(self, _event=None) -> None:
        selection = self.ccsf_viewer_obj_list.curselection() if hasattr(self, "ccsf_viewer_obj_list") else ()
        if not selection:
            return
        path = Path(self.ccsf_viewer_obj_list.get(selection[0]))
        summary = f"Selected OBJ: {path.name}"
        if path.exists():
            try:
                summary += f" ({path.stat().st_size:,} bytes)"
            except OSError:
                pass
        self.ccsf_viewer_obj_summary.set(summary)
        self._load_ccsf_viewer_obj_preview(path)

    def _load_ccsf_viewer_obj_preview(self, path: Path) -> None:
        """Embed the existing OBJ canvas viewer in the 3D Viewer preview tab."""
        frame = getattr(self, "ccsf_preview_tab", None)
        if frame is None:
            self._load_obj_3d_preview(path, select=False)
            return
        for child in frame.winfo_children():
            child.destroy()
        self.ccsf_viewer_current_mesh = None
        ttk.Label(frame, text="Source: OBJ file", anchor="w").grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        mesh, viewer = create_obj_viewer(frame, path)
        if viewer is None:
            ttk.Label(frame, text=f"Selected OBJ: {path}\n\n{mesh.summary()}", justify="left").grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        else:
            viewer.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        if hasattr(self, "ccsf_viewer_tabs"):
            self.ccsf_viewer_tabs.select(self.ccsf_preview_tab)

    def _ccsf_model_report_text_widget(self):
        return getattr(self, "ccsf_model_decode_report_text", getattr(self, "iso_3d_detail", None))

    def _build_server_tools_page(self, parent: ttk.Frame) -> None:
        nb = ttk.Notebook(parent)
        nb.grid(row=0, column=0, sticky="nsew")

        iso_tools = ttk.Frame(nb)
        nb.add(iso_tools, text="ISO Tools")
        self._build_iso_tools_page(iso_tools)

        area_tools = ttk.Frame(nb)
        nb.add(area_tools, text="Area Server Tools")
        self._build_area_server_tools_page(area_tools)

    def _build_navigation_shell(self, parent: ttk.Frame) -> None:
        """Deprecated: primary workbench navigation now lives in page_notebook."""
        ttk.Label(parent, text="Navigation moved to the top workbench tabs.").grid(row=0, column=0, sticky="w", padx=8, pady=8)

    def _on_workbench_page_changed(self, _event: tk.Event | None = None) -> None:
        if not hasattr(self, "page_notebook"):
            return
        selected = self.page_notebook.select()
        if not selected:
            return
        label = self.page_notebook.tab(selected, "text")
        if hasattr(self, "page_var"):
            self.page_var.set(label)

    def _show_page(self, name: str) -> None:
        if hasattr(self, "page_notebook") and name in getattr(self, "page_frames", {}):
            self.page_notebook.select(self.page_frames[name])
            if hasattr(self, "page_var"):
                self.page_var.set(name)
            return
        if hasattr(self, "page_var"):
            self.page_var.set(name)

    def _build_home_page(self, parent: ttk.Frame) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        self.nb = ttk.Notebook(parent)
        self.nb.grid(row=0, column=0, sticky="nsew")
        self.preview_tabs = {}
        self.preview_tab_frames = {}
        for title in ("Overview", "Texture", "3D"):
            tab = ttk.Frame(self.nb); tab.grid_rowconfigure(0, weight=1); tab.grid_columnconfigure(0, weight=1)
            self.preview_tab_frames[title] = tab
            text = tk.Text(tab, wrap="word", height=10, bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
            text.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
            scroll = ttk.Scrollbar(tab, orient="vertical", command=text.yview); scroll.grid(row=0, column=1, sticky="ns", padx=(0,8), pady=8)
            text.configure(yscrollcommand=scroll.set); self.preview_tabs[title] = text; self.nb.add(tab, text=title)
        self._build_text_hex_tab()
        title = "Report"
        tab = ttk.Frame(self.nb); tab.grid_rowconfigure(0, weight=1); tab.grid_columnconfigure(0, weight=1)
        self.preview_tab_frames[title] = tab
        text = tk.Text(tab, wrap="word", height=10, bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        text.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=text.yview); scroll.grid(row=0, column=1, sticky="ns", padx=(0,8), pady=8)
        text.configure(yscrollcommand=scroll.set); self.preview_tabs[title] = text; self.nb.add(tab, text=title)
        self.detail = self.preview_tabs["Overview"]
        for title, msg in {"Texture":"Texture preview will appear here after selecting/extracting texture assets.\n", "3D":self.native_3d_preview_status.get()+"\n", "Text / Hex":"Text/hex preview will appear here for selected local binaries.\n", "Report":"Run Quick Scan or open a report to populate this tab.\n"}.items():
            self._replace_text(self.preview_tabs[title], msg, readonly=True)

    def _build_asset_library_page(self, parent: ttk.Frame) -> None:
        self._build_ccsf_assets_tab(parent)

    def _build_iso_tools_page(self, parent: ttk.Frame) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        nb = ttk.Notebook(parent)
        nb.grid(row=0, column=0, sticky="nsew")

        index_search = ttk.Frame(nb)
        nb.add(index_search, text="Index / Search / Containers")
        self._build_iso_index_search_tab(index_search)

        iso_ccsf = ttk.Frame(nb)
        nb.add(iso_ccsf, text="ISO → CCSF")
        self._build_iso_ccsf_tab(iso_ccsf)

        survey = ttk.Frame(nb)
        nb.add(survey, text="Asset Survey")
        self._build_iso_asset_survey_tab(survey)


    def _build_iso_index_search_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(4, weight=1)
        paths = ttk.LabelFrame(parent, text="ISO index/search controls")
        paths.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        paths.grid_columnconfigure(0, weight=1)
        self._build_path_row(paths, "ISO", self.iso_path, browse_command=self.pick_iso, open_command=lambda: self._open_existing_variable_path(self.iso_path)).grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 3))
        self._build_path_row(paths, "ISO index", self.iso_index_path, browse_command=self.pick_iso_index_out, open_command=lambda: self._open_existing_variable_path(self.iso_index_path)).grid(row=1, column=0, sticky="ew", padx=8, pady=(3, 6))

        controls = ActionSection(parent, "Index and search", "Build/load the ISO index, search top-level ISO paths, and extract or preview selected hits using the existing subprocess Runner.", status_variable=self.iso_status, progress_variable=self.iso_progress, progress_text_variable=self.iso_progress_text, include_progress=True, output_buttons=[{"text": "Open Extract Folder", "command": self.open_iso_extract_dir}, {"text": "Open Index", "command": self.open_iso_index_file}], columns_at_width=[(900, 5), (620, 3)])
        controls.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self.iso_progress_bar = controls.progress_bar
        for text, command in (("Build/Refresh ISO Index", self.build_iso_index), ("Load ISO Index", self.load_iso_index), ("Search ISO", self.run_iso_search), ("Search from Section", self.run_iso_search_from_section), ("Likely Model Search", self.extract_likely_model_files), ("Extract Selected", self.extract_iso_search_selected), ("Preview Selected", self.preview_iso_selected_file)):
            controls.add_button(text=text, command=command)

        filters = ttk.LabelFrame(parent, text="Search filters")
        filters.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        for col in (1, 3, 5, 7):
            filters.grid_columnconfigure(col, weight=1)
        ttk.Label(filters, text="Query").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=4)
        ttk.Entry(filters, textvariable=self.iso_search_query).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(filters, text="Extensions").grid(row=0, column=2, sticky="w", padx=(8, 4), pady=4)
        ttk.Entry(filters, textvariable=self.iso_search_ext, width=18).grid(row=0, column=3, sticky="ew", pady=4)
        ttk.Label(filters, text="Prefix").grid(row=0, column=4, sticky="w", padx=(8, 4), pady=4)
        ttk.Entry(filters, textvariable=self.iso_search_prefix, width=18).grid(row=0, column=5, sticky="ew", pady=4)
        ttk.Label(filters, text="Limit").grid(row=0, column=6, sticky="w", padx=(8, 4), pady=4)
        ttk.Spinbox(filters, from_=1, to=10000, textvariable=self.iso_search_limit, width=8).grid(row=0, column=7, sticky="ew", padx=(0, 8), pady=4)
        ttk.Label(filters, text="Max scan").grid(row=1, column=0, sticky="w", padx=(8, 4), pady=(0, 6))
        ttk.Spinbox(filters, from_=100, to=10000000, increment=1000, textvariable=self.iso_search_max_scan, width=10).grid(row=1, column=1, sticky="w", pady=(0, 6))
        ttk.Checkbutton(filters, text="Advanced: enable batch extraction", variable=self.iso_batch_advanced, command=self._toggle_iso_advanced_batch).grid(row=1, column=2, columnspan=2, sticky="w", padx=(8, 4), pady=(0, 6))
        self.iso_advanced_batch_frame = ttk.Frame(filters)
        self.iso_advanced_batch_frame.grid(row=1, column=4, columnspan=4, sticky="ew", pady=(0, 6))
        ttk.Label(self.iso_advanced_batch_frame, text="Batch cap").pack(side="left")
        ttk.Spinbox(self.iso_advanced_batch_frame, from_=1, to=10000, textvariable=self.iso_batch_max_files, width=8).pack(side="left", padx=(4, 0))
        self._toggle_iso_advanced_batch()

        self.iso_nohit_actions = ttk.Frame(parent)
        self.iso_nohit_actions.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
        self.iso_nohit_actions.grid_remove()

        split = ttk.PanedWindow(parent, orient="vertical")
        split.grid(row=4, column=0, sticky="nsew", padx=8, pady=(4, 8))
        search_frame = ttk.LabelFrame(split, text="ISO search hits")
        search_frame.grid_rowconfigure(0, weight=1); search_frame.grid_columnconfigure(0, weight=1)
        self.iso_search_tree = ttk.Treeview(search_frame, columns=("status", "size", "path"), show="headings", height=9)
        for col, width in (("status", 130), ("size", 90), ("path", 700)):
            self.iso_search_tree.heading(col, text=col); self.iso_search_tree.column(col, width=width, anchor="e" if col == "size" else "w", stretch=col == "path")
        self.iso_search_tree.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(search_frame, orient="vertical", command=self.iso_search_tree.yview).grid(row=0, column=1, sticky="ns")
        split.add(search_frame, weight=3)
        container_frame = ttk.LabelFrame(split, text="Container scan/search tools")
        container_frame.grid_rowconfigure(1, weight=1); container_frame.grid_columnconfigure(0, weight=1)
        actions = ttk.Frame(container_frame); actions.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        for text, command in (("Scan Selected Container", self.scan_iso_selected_container), ("Search Cached Container Strings", self.search_iso_container_strings), ("Extract then Preview Selected", self.extract_then_preview_iso_selected_file)):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 6))
        self.iso_container_string_text = tk.Text(container_frame, height=6, wrap="word", bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.iso_container_string_text.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=(0, 6))
        ttk.Scrollbar(container_frame, orient="vertical", command=self.iso_container_string_text.yview).grid(row=1, column=1, sticky="ns", pady=(0, 6))
        split.add(container_frame, weight=1)

    def _build_iso_asset_survey_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)
        controls = ActionSection(parent, "ISO asset survey actions", "Run the conservative ISO asset survey and open the generated reports/dashboard from the active workspace.", status_variable=self.iso_status, columns_at_width=[(900, 4), (620, 2)])
        controls.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        controls.add_content(self._build_path_row(controls, "ISO", self.iso_path, browse_command=self.pick_iso, open_command=lambda: self._open_existing_variable_path(self.iso_path)), padx=8, pady=(0, 6))
        for text, command in (("Run ISO Asset Survey", self.run_iso_asset_survey), ("Open Survey Text", lambda: self._open_report_name("iso_asset_survey.txt")), ("Open Survey JSON", lambda: self._open_report_name("iso_asset_survey.json")), ("Open Survey Dashboard", lambda: self._open_report_name("asset_survey_dashboard.html"))):
            controls.add_button(text=text, command=command)
        self.iso_asset_survey_text = tk.Text(parent, height=18, wrap="word", bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.iso_asset_survey_text.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._replace_text(self.iso_asset_survey_text, "Run ISO Asset Survey to write workspace/reports/iso_asset_survey.* and asset_survey_dashboard.html.\n", readonly=True)

    def _build_area_server_tools_page(self, parent: ttk.Frame) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        nb = ttk.Notebook(parent)
        nb.grid(row=0, column=0, sticky="nsew")

        scan_tab = ScrollableFrame(nb)
        nb.add(scan_tab, text="Scan / Identify")
        self._build_area_server_scan_identify_tab(scan_tab.inner)

        dangerous_tab = ScrollableFrame(nb)
        nb.add(dangerous_tab, text="Decrypt / Encrypt (dangerous)")
        self._build_area_server_crypto_tab(dangerous_tab.inner)

        root_town_tab = ttk.Frame(nb)
        nb.add(root_town_tab, text="Root Town")
        self._build_root_town_tab(root_town_tab)

        parser_tab = ScrollableFrame(nb)
        nb.add(parser_tab, text="Room / Gimmick Parser")
        self._build_area_server_placeholder_tab(
            parser_tab.inner,
            "Future room/gimmick parser placeholder",
            "Reserved for future read-only room, gimmick, marker, and transition parsers. No parser action is wired for this pass.",
        )

        events_tab = ScrollableFrame(nb)
        nb.add(events_tab, text="Events / Snapshots")
        self._build_area_server_placeholder_tab(
            events_tab.inner,
            "Future event/snapshot tools placeholder",
            "Reserved for future event and snapshot comparison tools. No event/snapshot action is wired for this pass.",
        )

    def _build_area_server_scan_identify_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        self._build_load_files_tab(parent)
        tools = self._card(parent, "Scan-only Area Server CLI tools")
        tools.grid(row=1, column=0, sticky="ew", padx=2, pady=(10, 2))
        tools.grid_columnconfigure(0, weight=1)
        self._muted_help(
            tools,
            "These controls only identify encrypted files or scan the Area Server executable for patch candidates. They do not decrypt, encrypt, or patch files.",
            row=0,
        )
        self._path_picker_row(tools, "file for area-identify-encrypted", self.area_crypto_input_path, self.pick_area_crypto_input).grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        self._path_picker_row(tools, "areasrv.exe for scan-area-server-patches", self.area_patch_exe_path, self.pick_area_patch_exe).grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        actions = ActionSection(
            tools,
            "Scan-only operations",
            "Runs area-identify-encrypted and scan-area-server-patches. Patch scanner output is report-only for this pass.",
            status_variable=self.area_server_tools_status,
            output_buttons=[{"text": "Open Workspace", "command": self.open_workspace_output_dir}],
            columns_at_width=[(760, 4), (520, 2)],
        )
        actions.grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 10))
        for spec in (
            {"text": "Identify Encrypted", "command": self.run_area_identify_encrypted},
            {"text": "Scan Patch Candidates", "command": self.run_area_patch_scan},
            {"text": "Auto Detect", "command": self.auto_detect_load_paths},
            {"text": "Open Reports", "command": lambda: self._open_folder_path(self._selected_workspace() / "reports")},
        ):
            actions.add_button(**spec)

    def _build_area_server_crypto_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        warning = self._card(parent, "Dangerous operations: decrypt / encrypt")
        warning.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        warning.grid_columnconfigure(0, weight=1)
        self._muted_help(
            warning,
            "Decrypt and encrypt write new output files. They never replace originals from this GUI, but review paths carefully and keep backups.",
            row=0,
        )
        self._path_picker_row(warning, "input file", self.area_crypto_input_path, self.pick_area_crypto_input).grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        self._path_picker_row(warning, "output file", self.area_crypto_output_path, self.pick_area_crypto_output).grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        self._path_picker_row(warning, "encrypt key-from file", self.area_encrypt_key_from_path, self.pick_area_encrypt_key_from).grid(row=3, column=0, sticky="ew", padx=10, pady=4)
        key_row = ttk.Frame(warning)
        key_row.grid_columnconfigure(1, weight=1)
        ttk.Label(key_row, text="encrypt filekey hex", foreground=self._theme.get("muted", "#9fb3a7")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(key_row, textvariable=self.area_encrypt_filekey_hex).grid(row=0, column=1, sticky="ew")
        key_row.grid(row=4, column=0, sticky="ew", padx=10, pady=4)
        actions = ActionSection(
            warning,
            "Write-output operations",
            "area-decrypt requires an encrypted input and output path. area-encrypt requires a plain input, output path, and either key-from file or filekey hex.",
            status_variable=self.area_server_tools_status,
            output_buttons=[{"text": "Open Output Folder", "command": self.open_area_crypto_output_folder}],
            columns_at_width=[(700, 3), (520, 2)],
        )
        actions.grid(row=5, column=0, sticky="ew", padx=10, pady=(4, 10))
        actions.add_button(text="Decrypt to Output", command=self.run_area_decrypt)
        actions.add_button(text="Encrypt to Output", command=self.run_area_encrypt)
        actions.add_button(text="Identify Input First", command=self.run_area_identify_encrypted)

    def _build_area_server_placeholder_tab(self, parent: ttk.Frame, title: str, message: str) -> None:
        parent.grid_columnconfigure(0, weight=1)
        card = self._card(parent, title)
        card.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        card.grid_columnconfigure(0, weight=1)
        self._muted_help(card, message, row=0)

    def _build_reports_page(self, parent: ttk.Frame) -> None:
        self._build_reports_tab(parent)

    def _build_audio_page(self, parent: ttk.Frame) -> None:
        """Build a compact audio workbench for decoded, pending, and failed ISO audio outputs."""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=0)

        strip = ttk.Frame(parent)
        strip.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        strip.grid_columnconfigure(0, weight=1)
        strip.grid_columnconfigure(1, weight=1)
        ttk.Label(strip, textvariable=self.iso_path, width=42).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(strip, textvariable=self.workspace_output_dir, width=38).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        actions = ttk.Frame(strip)
        actions.grid(row=0, column=2, sticky="e")
        self.audio_action_buttons = []
        for text, command, primary in (
            ("Prepare Known Audio", self.prepare_known_audio, True),
            ("Refresh Library", self.refresh_audio_reports, True),
        ):
            button = ttk.Button(actions, text=text, command=command)
            button.pack(side="left", padx=(0, 4))
            if primary:
                self.audio_action_buttons.append(button)
        self.audio_cancel_button = ttk.Button(actions, text="Cancel Active Task", command=self.cancel_audio_pipeline, state="disabled")
        self.audio_cancel_button.pack(side="left", padx=(0, 4))
        ttk.Button(actions, text="Open Output Folder", command=self.open_setup_media_output_folder).pack(side="left", padx=(8, 4))

        split = ttk.Panedwindow(parent, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        left = ttk.Frame(split)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.audio_candidates_notebook = ttk.Notebook(left)
        self.audio_candidates_notebook.grid(row=0, column=0, sticky="nsew")
        self._build_audio_music_system_tab(self.audio_candidates_notebook)
        self.audio_library_tree = self._build_audio_library_tab(self.audio_candidates_notebook)
        research_notebook = self._build_audio_research_tab(self.audio_candidates_notebook)
        self._build_audio_research_discovery_pipeline_tabs(research_notebook)
        self._build_raw_audio_lab_tab(research_notebook)
        self._build_audio_stream_regions_tab(research_notebook)
        self._build_audio_placeholder_category(research_notebook, "Sound Banks", "Detected sound-bank containers, paired header/body files, and bank metadata are listed here.")
        self.audio_raw_tree = self._audio_tree_tab(
            research_notebook,
            "Pending / Warnings",
            ("bank_type", "bank_name", "stream_index", "sample_rate", "loop_flag", "duration", "output_path", "raw_path", "decode_status"),
            ("bank type", "bank name", "stream", "sample rate", "loop", "duration", "output path", "raw path", "decode status"),
        )
        self.audio_failed_tree = self.audio_raw_tree
        self.audio_wav_tree = self.audio_library_tree
        self.audio_snddata_samples_tree = None
        self.audio_candidates_notebook.select(0)
        split.add(left, weight=3)

        right = ttk.Frame(split)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.audio_details_notebook = ttk.Notebook(right)
        self.audio_details_notebook.grid(row=0, column=0, sticky="nsew")
        self._build_audio_playback_tab(self.audio_details_notebook)
        self._build_audio_decode_details_tab(self.audio_details_notebook)
        self._build_audio_source_tab(self.audio_details_notebook)
        split.add(right, weight=2)

        bottom = ttk.Frame(parent)
        bottom.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=2)
        bottom.grid_columnconfigure(2, weight=1)
        ttk.Label(bottom, textvariable=self.audio_pipeline_status).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(bottom, textvariable=self.audio_busy_action).grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.audio_pipeline_progress_bar = ttk.Progressbar(bottom, maximum=100.0, variable=self.audio_pipeline_progress, mode="determinate", length=220)
        self.audio_pipeline_progress_bar.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(bottom, textvariable=self.audio_pipeline_progress_text, anchor="e").grid(row=0, column=2, sticky="e")
        self.audio_wav_payloads = {}
        self.audio_raw_payloads = {}
        self.audio_failed_payloads = {}
        self.audio_library_payloads = {}


    def _build_raw_audio_lab_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(4, weight=1)
        notebook.add(tab, text="Raw Audio Lab")
        self._path_picker_row(tab, "Source", self.raw_audio_source, self.select_raw_audio_source).grid(row=0, column=0, columnspan=4, sticky="ew", padx=8, pady=(8, 4))
        controls = ttk.Frame(tab)
        controls.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8, pady=4)
        for label, var, values, width in (
            ("Encoding", self.raw_audio_encoding, ENCODINGS, 10),
            ("Channels", self.raw_audio_channels, (1, 2), 5),
            ("Sample rate", self.raw_audio_sample_rate, SAMPLE_RATES, 8),
        ):
            ttk.Label(controls, text=label).pack(side="left", padx=(0, 2))
            ttk.Combobox(controls, textvariable=var, values=values, width=width, state="readonly").pack(side="left", padx=(0, 8))
        for label, var in (("Offset", self.raw_audio_start_offset), ("Length", self.raw_audio_length), ("End", self.raw_audio_end_offset)):
            ttk.Label(controls, text=label).pack(side="left", padx=(0, 2))
            ttk.Entry(controls, textvariable=var, width=10).pack(side="left", padx=(0, 8))
        actions = ttk.Frame(tab)
        actions.grid(row=2, column=0, columnspan=4, sticky="w", padx=8, pady=4)
        for text, command in (
            ("Auto Probe", self.auto_probe_raw_audio),
            ("Preview", self.preview_raw_audio),
            ("Export WAV Preview", self.export_raw_audio_wav_preview),
            ("Find Audio Regions", self.find_raw_audio_regions),
            ("Analyze Container", self.analyze_raw_audio_container),
        ):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 4))
        ttk.Label(tab, textvariable=self.raw_audio_probe_status).grid(row=3, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 4))
        self.raw_audio_probe_text = tk.Text(tab, height=14, wrap="word")
        self.raw_audio_probe_text.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=8, pady=(0, 8))


    def _build_audio_stream_regions_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=3)
        tab.grid_rowconfigure(2, weight=2)
        notebook.add(tab, text="Stream Regions")
        actions = ttk.Frame(tab)
        actions.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        for text, command in (
            ("Find Regions", self.find_raw_audio_regions),
            ("Play Region", self.play_stream_region),
            ("Stop", self.stop_audio_playback),
            ("Export WAV", self.export_stream_region_wav),
            ("Open Source", self.open_stream_region_source),
            ("Copy Start Offset", self.copy_stream_region_start_offset),
        ):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 4))
        columns = ("region", "start", "end", "size", "duration", "encoding", "channels", "sample_rate", "confidence", "boundary_source")
        self.audio_stream_regions_tree = ttk.Treeview(tab, columns=columns, show="headings", height=10)
        for column, heading, width in (
            ("region", "Region", 110),
            ("start", "Start Offset", 100),
            ("end", "End Offset", 100),
            ("size", "Size", 90),
            ("duration", "Estimated Duration", 130),
            ("encoding", "Encoding", 90),
            ("channels", "Channels", 80),
            ("sample_rate", "Sample Rate", 95),
            ("confidence", "Confidence", 90),
            ("boundary_source", "Boundary Source", 220),
        ):
            self.audio_stream_regions_tree.heading(column, text=heading)
            self.audio_stream_regions_tree.column(column, width=width, stretch=column in {"region", "boundary_source"})
        self.audio_stream_regions_tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.audio_stream_regions_tree.yview)
        scroll.grid(row=1, column=1, sticky="ns", pady=(0, 4))
        self.audio_stream_regions_tree.configure(yscrollcommand=scroll.set)
        self.audio_stream_regions_tree.bind("<<TreeviewSelect>>", self._on_stream_region_select)
        self.audio_stream_regions_tree.bind("<Double-1>", self.play_stream_region)

        details = ttk.LabelFrame(tab, text="Research Details / Raw JSON / Evidence")
        details.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=(0, 8))
        details.grid_columnconfigure(0, weight=1)
        details.grid_rowconfigure(0, weight=1)
        self.audio_stream_regions_text = tk.Text(details, height=8, wrap="word")
        self.audio_stream_regions_text.grid(row=0, column=0, sticky="nsew")
        details_scroll = ttk.Scrollbar(details, orient="vertical", command=self.audio_stream_regions_text.yview)
        details_scroll.grid(row=0, column=1, sticky="ns")
        self.audio_stream_regions_text.configure(yscrollcommand=details_scroll.set)
        self._replace_text(self.audio_stream_regions_text, "Use Find Regions to map offset-table-backed stream regions.\n", readonly=False)

    def _build_audio_placeholder_category(self, notebook: ttk.Notebook, label: str, message: str) -> None:
        frame = ttk.Frame(notebook)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        ttk.Label(frame, text=message, wraplength=420, justify="left").grid(row=0, column=0, sticky="nw", padx=8, pady=8)
        notebook.add(frame, text=label)

    def _build_audio_research_tab(self, notebook: ttk.Notebook) -> ttk.Notebook:
        tab = ttk.Frame(notebook)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        research = ttk.Notebook(tab)
        research.grid(row=0, column=0, sticky="nsew")
        notebook.add(tab, text="Research")
        return research


    def _build_audio_research_discovery_pipeline_tabs(self, notebook: ttk.Notebook) -> None:
        """Build secondary audio discovery and pipeline controls under Research."""
        discovery = ttk.Frame(notebook)
        discovery.grid_columnconfigure(0, weight=1)
        discovery_actions = ActionSection(
            discovery,
            "Audio Discovery",
            "Broad ISO audio discovery actions live here so the primary Audio toolbar stays focused on known audio preparation and library refresh.",
            status_variable=self.audio_pipeline_status,
            progress_variable=self.audio_pipeline_progress,
            progress_text_variable=self.audio_pipeline_progress_text,
            include_progress=True,
            columns_at_width=[(900, 4), (640, 2)],
        )
        discovery_actions.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        for text, command in (
            ("Inventory", self.run_audio_media_inventory),
            ("Rescan Audio Inventory", self.rescan_audio_inventory),
            ("Audio Dashboard", lambda: self._open_report_name("iso_audio_dashboard.html")),
        ):
            button = discovery_actions.add_button(text=text, command=command)
            self.audio_action_buttons.append(button)
        notebook.add(discovery, text="Discovery")

        pipeline = ttk.Frame(notebook)
        pipeline.grid_columnconfigure(0, weight=1)
        pipeline_actions = ActionSection(
            pipeline,
            "Audio Pipeline",
            "Run extraction/decode pipeline actions. The broad pipeline action is named as a pipeline because it can include ISO inventory/extraction work.",
            status_variable=self.audio_pipeline_status,
            progress_variable=self.audio_pipeline_progress,
            progress_text_variable=self.audio_pipeline_progress_text,
            include_progress=True,
            output_buttons=[{"text": "Open Output Folder", "command": self.open_setup_media_output_folder}],
            columns_at_width=[(900, 4), (640, 2)],
        )
        pipeline_actions.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        for text, command in (
            ("Extract Audio", self.run_audio_candidate_extract),
            ("Decode Audio", self.run_audio_decode),
            ("Run Audio Pipeline", self.run_audio_pipeline_all),
            ("Audio Dashboard", lambda: self._open_report_name("iso_audio_dashboard.html")),
        ):
            button = pipeline_actions.add_button(text=text, command=command)
            self.audio_action_buttons.append(button)
        notebook.add(pipeline, text="Pipeline")

    def _build_audio_library_tab(self, notebook: ttk.Notebook) -> ttk.Treeview:
        frame = ttk.Frame(notebook)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        picker_bar = ttk.Frame(frame)
        picker_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 2))
        picker_bar.grid_columnconfigure(1, weight=1)
        ttk.Label(picker_bar, text="Audio / Container:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(picker_bar, textvariable=self.audio_library_container).grid(row=0, column=1, sticky="ew", padx=(0, 4))
        ttk.Button(picker_bar, text="Browse", command=self.browse_audio_library_container).grid(row=0, column=2, sticky="e", padx=(0, 4))
        ttk.Button(picker_bar, text="Open", command=self.open_audio_library_container).grid(row=0, column=3, sticky="e")

        action_bar = ttk.Frame(frame)
        action_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=(2, 2))
        ttk.Button(action_bar, text="Add to Library", command=self.add_audio_library_manual_file).pack(side="left", padx=(0, 4))
        ttk.Button(action_bar, text="Analyze Selected File", command=self.analyze_selected_audio_library_file).pack(side="left", padx=(0, 4))
        ttk.Button(action_bar, textvariable=self.audio_primary_action_label, command=self.run_selected_audio_primary_action).pack(side="left", padx=(0, 4))
        ttk.Button(action_bar, text="Stop", command=self.stop_audio_playback).pack(side="left", padx=(0, 4))
        ttk.Button(action_bar, text="Open Source", command=self.open_selected_audio_source).pack(side="left", padx=(0, 4))
        ttk.Button(action_bar, text="Open Output", command=self.open_selected_audio_output).pack(side="left", padx=(0, 4))
        ttk.Button(action_bar, text="Copy Path", command=self.copy_selected_audio_path).pack(side="left", padx=(0, 4))
        ttk.Button(action_bar, text="Send to Research", command=self.send_selected_audio_to_research).pack(side="left", padx=(0, 4))
        columns = ("source", "type", "confidence", "duration", "sample_rate", "output")
        tree = ttk.Treeview(frame, columns=columns, show="tree headings", height=13)
        tree.heading("#0", text="Name")
        tree.column("#0", width=180, stretch=True)
        for column, heading in zip(columns, ("Source", "Type", "Confidence", "Duration", "Sample Rate", "Output")):
            tree.heading(column, text=heading)
            tree.column(column, width=260 if column == "output" else 120, stretch=column in {"source", "output"})
        tree.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        tree.tag_configure("confirmed_wav", foreground="#4ade80")
        tree.tag_configure("ps_adpcm", foreground="#93c5fd")
        tree.tag_configure("raw_pcm", foreground="#fbbf24")
        tree.tag_configure("sequence_render", foreground="#f0abfc")
        tree.bind("<<TreeviewSelect>>", self._on_audio_tree_select)
        tree.bind("<Double-1>", self.run_selected_audio_primary_action)
        notebook.add(frame, text="Audio Library")
        return tree

    def _build_audio_music_system_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        notebook.add(tab, text="Music Mixer")

        transport = ttk.LabelFrame(tab, text="Transport")
        transport.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
        self.audio_music_position = tk.StringVar(value="0:00.000")
        self.audio_music_duration = tk.StringVar(value="0:00.000")
        self.audio_music_tempo = tk.DoubleVar(value=120.0)
        self.audio_music_master_gain = tk.DoubleVar(value=1.0)
        self.audio_music_loop = tk.BooleanVar(value=False)
        self.audio_music_source_label = tk.StringVar(value="Experimental SNDDATA editor — source: not loaded")
        self.audio_music_mapping_status = tk.StringVar(value="Mapping: unresolved")
        self.audio_music_sequence_choice = tk.StringVar(value="")
        self.audio_music_sequence_choices = {}
        self.audio_music_editor = None
        self.audio_music_sample_payloads = {}
        self.audio_music_editable_widgets = []

        for column in range(8):
            transport.grid_columnconfigure(column, weight=1 if column in {1, 3, 5} else 0)

        ttk.Label(transport, textvariable=self.audio_music_mapping_status).grid(row=0, column=0, columnspan=8, sticky="w", padx=(6, 6), pady=(6, 3))

        self.audio_music_play_button = ttk.Button(transport, text="Play", command=self.play_audio_music_preview)
        self.audio_music_play_button.grid(row=1, column=0, sticky="w", padx=(6, 4), pady=3)
        if self.audio_playback_engine.supports_pause:
            ttk.Button(transport, text="Pause", command=self.pause_audio_music_preview).grid(row=1, column=1, sticky="w", padx=(0, 4), pady=3)
        ttk.Button(transport, text="Stop", command=self.stop_audio_music_preview).grid(row=1, column=2, sticky="w", padx=(0, 4), pady=3)
        loop_widget = ttk.Checkbutton(transport, text="Loop", variable=self.audio_music_loop, command=self.refresh_audio_music_preview)
        loop_widget.grid(row=1, column=3, sticky="w", padx=(0, 4), pady=3)
        self.audio_music_editable_widgets.append(loop_widget)

        ttk.Label(transport, textvariable=self.audio_music_source_label).grid(row=2, column=0, columnspan=3, sticky="ew", padx=(6, 10), pady=3)
        ttk.Label(transport, text="Position").grid(row=2, column=3, sticky="e", padx=(0, 2), pady=3)
        ttk.Entry(transport, textvariable=self.audio_music_position, width=10).grid(row=2, column=4, sticky="w", padx=(0, 10), pady=3)
        ttk.Label(transport, text="Duration").grid(row=2, column=5, sticky="e", padx=(0, 2), pady=3)
        ttk.Entry(transport, textvariable=self.audio_music_duration, width=10).grid(row=2, column=6, sticky="w", padx=(0, 6), pady=3)

        ttk.Label(transport, text="Master Gain").grid(row=3, column=0, sticky="w", padx=(6, 4), pady=3)
        master_scale = ttk.Scale(transport, from_=0.0, to=2.0, variable=self.audio_music_master_gain, command=lambda _value: self.refresh_audio_music_preview())
        master_scale.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(0, 4), pady=3)
        master_entry = ttk.Entry(transport, textvariable=self.audio_music_master_gain, width=7)
        master_entry.grid(row=3, column=3, sticky="w", padx=(0, 12), pady=3)
        ttk.Label(transport, text="Tempo").grid(row=3, column=4, sticky="e", padx=(0, 4), pady=3)
        tempo_scale = ttk.Scale(transport, from_=40.0, to=240.0, variable=self.audio_music_tempo, command=lambda _value: self.refresh_audio_music_preview())
        tempo_scale.grid(row=3, column=5, sticky="ew", padx=(0, 4), pady=3)
        tempo_entry = ttk.Entry(transport, textvariable=self.audio_music_tempo, width=7)
        tempo_entry.grid(row=3, column=6, sticky="w", padx=(0, 6), pady=3)
        self.audio_music_editable_widgets.extend([master_scale, master_entry, tempo_scale, tempo_entry])

        self.audio_music_export_button = ttk.Button(transport, text="Export Patched SNDDATA", command=self.export_patched_snddata)
        self.audio_music_export_button.grid(row=4, column=0, columnspan=2, sticky="w", padx=(6, 4), pady=(3, 6))
        ttk.Button(transport, text="Undo", command=self.undo_audio_music_edit).grid(row=4, column=2, sticky="w", padx=(0, 4), pady=(3, 6))
        ttk.Button(transport, text="Redo", command=self.redo_audio_music_edit).grid(row=4, column=3, sticky="w", padx=(0, 4), pady=(3, 6))
        ttk.Button(transport, text="Refresh Preview", command=self.refresh_audio_music_preview).grid(row=4, column=4, sticky="w", padx=(0, 6), pady=(3, 6))

        split = ttk.Panedwindow(tab, orient="vertical")
        split.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

        top = ttk.Frame(split)
        top.grid_columnconfigure(1, weight=1)
        top.grid_rowconfigure(1, weight=1)
        ttk.Label(top, text="Playable sequence / MIDI").grid(row=0, column=0, sticky="w", padx=(0, 4), pady=(0, 4))
        self.audio_music_sequence_combo = ttk.Combobox(top, textvariable=self.audio_music_sequence_choice, values=(), width=90, state="readonly")
        self.audio_music_sequence_combo.grid(row=0, column=1, sticky="ew", padx=(0, 4), pady=(0, 4))
        self.audio_music_sequence_combo.bind("<<ComboboxSelected>>", self._on_audio_music_sequence_choice)
        self.audio_music_sequence_combo.bind("<KeyRelease>", self._on_audio_music_sequence_search)
        self.audio_music_snddata_tree = ttk.Treeview(top, columns=("kind", "summary"), show="tree headings", height=9)
        self.audio_music_snddata_tree.heading("#0", text="SNDDATA tree")
        self.audio_music_snddata_tree.heading("kind", text="kind")
        self.audio_music_snddata_tree.heading("summary", text="summary")
        self.audio_music_snddata_tree.grid(row=1, column=0, columnspan=2, sticky="nsew")
        for node in (
            ("sample_program_resources", "Sample / Program Resources", "group", ""),
            ("programs", "Programs", "resources", "program records"),
            ("slots", "Slots", "resources", "program slot mappings"),
            ("samples", "Samples", "resources", "decoded/linked sample data"),
            ("sequence_resources", "Sequence Resources", "group", ""),
            ("midi_tracks_channels_events", "Midi tracks/channels/events", "sequence", "tracks, channels, note/control events"),
        ):
            self.audio_music_snddata_tree.insert("", "end", iid=node[0], text=node[1], values=node[2:])
        split.add(top, weight=1)

        middle = ttk.Frame(split)
        middle.grid_columnconfigure(0, weight=1)
        middle.grid_rowconfigure(0, weight=1)
        mixer_columns = ("mute", "solo", "track_channel", "program", "slot_sample_summary", "volume", "pan", "pitch", "activity")
        self.audio_music_mixer_tree = ttk.Treeview(middle, columns=mixer_columns, show="headings", height=7)
        for column in mixer_columns:
            self.audio_music_mixer_tree.heading(column, text=column.replace("_", " "))
            self.audio_music_mixer_tree.column(column, width=118 if column == "slot_sample_summary" else 76, stretch=column == "slot_sample_summary")
        self.audio_music_mixer_tree.grid(row=0, column=0, sticky="nsew")
        split.add(middle, weight=1)

        bottom = ttk.Frame(split)
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)
        editor = ttk.LabelFrame(bottom, text="Program / Slot Inspector Editor")
        editor.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.audio_music_editor_fields = {}
        for row, label in enumerate(("Program", "Slot", "Sample", "Volume", "Pan", "Pitch / Tempo", "Track / Channel", "Mapping")):
            ttk.Label(editor, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            var = tk.StringVar(value="")
            self.audio_music_editor_fields[label] = var
            entry = ttk.Entry(editor, textvariable=var, width=18)
            entry.grid(row=row, column=1, sticky="ew", padx=6, pady=2)
            entry.bind("<Return>", lambda _event: self.refresh_audio_music_preview())
            self.audio_music_editable_widgets.append(entry)
        raw = ttk.LabelFrame(bottom, text="Unknown / Raw Fields")
        raw.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.audio_music_raw_field_tree = ttk.Treeview(raw, columns=("field", "value"), show="headings", height=8)
        self.audio_music_raw_field_tree.heading("field", text="field")
        self.audio_music_raw_field_tree.heading("value", text="value")
        self.audio_music_raw_field_tree.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        split.add(bottom, weight=1)
        self._set_audio_music_editor_enabled(False)

    def _build_audio_snddata_samples_tab(self, notebook: ttk.Notebook) -> ttk.Treeview:
        frame = ttk.Frame(notebook)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        columns = ("resource", "sample_id", "sample_rate", "duration", "boundary_source", "status", "output_path")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=13)
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=240 if column == "output_path" else 110, stretch=column == "output_path")
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        tree.bind("<<TreeviewSelect>>", self._on_audio_tree_select)
        tree.bind("<Double-1>", self.run_selected_audio_primary_action)
        notebook.add(frame, text="Samples")
        return tree

    def _audio_tree_tab(self, notebook: ttk.Notebook, label: str, columns: tuple[str, ...], headings: tuple[str, ...]) -> ttk.Treeview:
        frame = ttk.Frame(notebook)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=columns, show="tree headings", height=13)
        tree.heading("#0", text="name")
        tree.column("#0", width=150, stretch=True)
        wide_columns = {"source_path", "output_path", "raw_path"}
        for column, heading in zip(columns, headings):
            tree.heading(column, text=heading)
            tree.column(column, width=240 if column in wide_columns else 92, stretch=column in wide_columns)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        tree.bind("<<TreeviewSelect>>", self._on_audio_tree_select)
        notebook.add(frame, text=label)
        return tree

    def _build_audio_playback_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        tab.grid_columnconfigure(1, weight=1)
        notebook.add(tab, text="Playback")
        self.audio_selected_file = tk.StringVar(value="No audio file selected")
        ttk.Label(tab, text="Selected file").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        ttk.Label(tab, textvariable=self.audio_selected_file, wraplength=360).grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 2))
        buttons = ttk.Frame(tab)
        buttons.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Button(buttons, textvariable=self.audio_primary_action_label, command=self.run_selected_audio_primary_action).pack(side="left", padx=(0, 4))
        if self.audio_playback_engine.supports_pause:
            ttk.Button(buttons, text="Pause", command=self.pause_audio_playback).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="Stop", command=self.stop_audio_playback).pack(side="left")
        ttk.Label(tab, textvariable=self.audio_playback_status, justify="left").grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 2))
        self.audio_metadata_text = tk.Text(tab, height=9, wrap="word")
        self.audio_metadata_text.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=8, pady=(4, 8))

    def _build_audio_decode_details_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        notebook.add(tab, text="Decode Details")
        self.audio_decode_details_text = tk.Text(tab, height=14, wrap="word")
        self.audio_decode_details_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _build_audio_source_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        tab.grid_columnconfigure(1, weight=1)
        notebook.add(tab, text="Source")
        self.audio_source_fields = {}
        for row, label in enumerate(("Source ISO path", "Offset", "Raw path", "Decoded output path")):
            ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=3)
            var = tk.StringVar(value="—")
            self.audio_source_fields[label] = var
            ttk.Label(tab, textvariable=var, wraplength=360).grid(row=row, column=1, sticky="ew", padx=8, pady=3)
        buttons = ttk.Frame(tab)
        buttons.grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 0))
        ttk.Button(buttons, text="Open Source", command=self.open_selected_audio_source).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="Open Output", command=self.open_selected_audio_output).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="Copy Source Path", command=self.copy_selected_audio_path).pack(side="left")

    def _build_settings_legacy_page(self, parent: ttk.Frame) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        nb = ttk.Notebook(parent)
        nb.grid(row=0, column=0, sticky="nsew")

        legacy = ScrollableFrame(nb)
        nb.add(legacy, text="Legacy / Experimental Tools")
        self._build_registry_legacy_tools_tab(legacy.inner)

        launcher_diag = ttk.Frame(nb)
        nb.add(launcher_diag, text="Launcher Diagnostics")
        self._build_launcher_diagnostics_tab(launcher_diag)

        celdra_tab = ttk.Frame(nb)
        nb.add(celdra_tab, text="Celdra")
        self._build_celdra_settings_tab(celdra_tab)

    def _build_celdra_settings_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        card = ttk.Labelframe(parent, text="Celdra")
        card.grid(row=0, column=0, sticky="nw", padx=8, pady=8)
        self.celdra_sprite = CeldraSprite(card, CELDRA_FRAME_DIR, self.celdra_animation_enabled, theme_getter=lambda: self._theme, display_size=96)
        self.celdra_sprite.grid(row=0, column=0, padx=8, pady=8)
        ttk.Checkbutton(card, text="Animate", variable=self.celdra_animation_enabled).grid(row=1, column=0, sticky="w", padx=8, pady=(0,8))

    def _registry_tool(self, tool_id: str) -> dict[str, str]:
        return GUI_TOOL_REGISTRY.get(tool_id, {
            "display_name": tool_id.replace("_", " ").title(),
            "command": tool_id,
            "category": "Uncategorized",
            "status": "experimental",
            "description": "Registered dynamically by the GUI.",
            "replacement": "Use only when this workflow is needed.",
        })

    def _legacy_registry_entries(self) -> list[tuple[str, dict[str, str]]]:
        rows = [
            (tool_id, spec)
            for tool_id, spec in GUI_TOOL_REGISTRY.items()
            if spec.get("status") in {"legacy", "experimental"}
        ]
        return sorted(rows, key=lambda item: (item[1].get("category", ""), item[1].get("status", ""), item[1].get("display_name", item[0])))

    def _build_registry_legacy_tools_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        self._muted_help(
            parent,
            "Legacy and experimental tools are intentionally kept out of primary workflow pages. "
            "Each entry shows its status and the newer workflow to prefer when one exists.",
            row=0,
        )

        if not self.research_launchers:
            self.research_launchers = self._research_launcher_metadata()
        self.research_launcher_buttons = {}

        grouped: dict[str, list[tuple[str, dict[str, str]]]] = {}
        for tool_id, spec in self._legacy_registry_entries():
            grouped.setdefault(spec.get("category", "Other"), []).append((tool_id, spec))

        row = 1
        patch_card = self._card(parent, "Patch Package / Legacy Packaging")
        patch_card.grid(row=row, column=0, sticky="ew", padx=2, pady=(8, 2))
        patch_card.grid_columnconfigure(0, weight=1)
        self._muted_help(
            patch_card,
            "Build or preview the legacy patch package from the current workspace metadata.",
            row=0,
        )
        patch_actions, _ = self._wrapped_button_row(
            patch_card,
            [
                {"text": "Build Patch Package", "command": self.build_patch_package},
                {"text": "Preview Only", "command": self.preview_patch_package},
            ],
            columns_at_width=[(640, 2)],
        )
        patch_actions.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        row += 1

        imports_card = self._card(parent, "Legacy data imports")
        imports_card.grid(row=row, column=0, sticky="ew", padx=2, pady=(8, 2))
        imports_card.grid_columnconfigure(0, weight=1)
        self._muted_help(
            imports_card,
            "Import legacy research workbooks and generate normalized workspace reports.",
            row=0,
        )
        import_actions, _ = self._wrapped_button_row(
            imports_card,
            [
                {"text": "Import Fragment Strings Workbook", "command": self.import_fragment_strings_workbook_action},
            ],
            columns_at_width=[(640, 1)],
        )
        import_actions.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        row += 1

        for category, entries in grouped.items():
            card = self._card(parent, category)
            card.grid(row=row, column=0, sticky="ew", padx=2, pady=(8, 2))
            card.grid_columnconfigure(0, weight=1)
            for idx, (tool_id, spec) in enumerate(entries):
                self._build_registry_tool_row(card, tool_id, spec).grid(row=idx, column=0, sticky="ew", padx=8, pady=(8 if idx == 0 else 4, 4))
            row += 1

        tools, _ = self._wrapped_button_row(
            parent,
            [
                {"text": "Copy Latest Command", "command": self.copy_latest_launcher_command},
                {"text": "Open Latest Output Folder", "command": self.open_latest_launcher_output_folder},
                {"text": "Open Latest Report", "command": self.open_latest_launcher_report},
                {"text": "Run Again", "command": self.run_latest_research_launcher},
            ],
            columns_at_width=[(900, 4), (640, 2)],
        )
        tools.grid(row=row, column=0, sticky="ew", padx=8, pady=(10, 8))
        self._build_legacy_inspector_tools(parent, row + 1)

    def _build_registry_tool_row(self, parent: ttk.Frame, tool_id: str, spec: dict[str, str]) -> ttk.Frame:
        row = ttk.Frame(parent)
        row.grid_columnconfigure(1, weight=1)
        badge = f"[{spec.get('status', 'experimental').upper()}]"
        ttk.Label(row, text=badge, font=self._font(9, "bold"), foreground=self._theme.get("accent", "#7dd3fc")).grid(row=0, column=0, sticky="nw", padx=(0, 8))
        text = f"{spec.get('display_name', tool_id)}\n{spec.get('description', '')}\nPrefer: {spec.get('replacement', 'No newer workflow specified.')}"
        ttk.Label(row, text=text, justify="left", wraplength=760).grid(row=0, column=1, sticky="ew")
        command = self._registry_tool_command(tool_id, spec)
        if command is not None:
            button = ttk.Button(row, text="Open / Run", command=command)
            button.grid(row=0, column=2, sticky="ne", padx=(8, 0))
            if tool_id in self.research_launchers:
                self.research_launcher_buttons[tool_id] = button
        return row

    def _registry_tool_command(self, tool_id: str, spec: dict[str, str]):
        if tool_id in self.research_launchers:
            return lambda lid=tool_id: self.run_research_launcher(lid)
        if tool_id == "iso_3d_preview":
            return lambda: self._open_registry_tool_window(tool_id, spec)
        if tool_id == "root_town_summary":
            return lambda: self._show_page("Server Tools")
        return None

    def _open_registry_tool_window(self, tool_id: str, spec: dict[str, str]) -> None:
        window = tk.Toplevel(self)
        window.title(f"{spec.get('display_name', tool_id)} ({spec.get('status', 'experimental')})")
        window.geometry("1000x720")
        frame = ttk.Frame(window)
        frame.pack(fill="both", expand=True)
        if tool_id == "iso_3d_preview":
            nb = ttk.Notebook(frame)
            nb.pack(fill="both", expand=True)
            self._build_iso_3d_preview_tab(nb, title="Raw ISO 3D candidate view [EXPERIMENTAL]")

    def _build_legacy_inspector_tools(self, parent: ttk.Frame, row: int) -> None:
        card = self._card(parent, "Legacy inspector helpers")
        card.grid(row=row, column=0, sticky="ew", padx=2, pady=8)
        card.grid_columnconfigure(0, weight=1)
        self._path_picker_row(card, "Inspector file", self.inspector_path, self.select_inspector_file).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        extra, _ = self._wrapped_button_row(card, [
            {"text": "Preview selected file", "command": self.preview_inspector_file},
            {"text": "Scan selected container", "command": self.scan_inspector_container},
            {"text": "Extract/decompress candidate", "command": self.extract_inspector_candidate},
            {"text": "Build ISO Index", "command": self.build_iso_index},
            {"text": "Resolve ISO references", "command": self.resolve_iso_from_selection},
        ], columns_at_width=[(900, 5), (640, 3)])
        extra.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        output_frame = ttk.Frame(card)
        output_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        output_frame.grid_columnconfigure(0, weight=1)
        self.inspector_output = tk.Text(
            output_frame,
            wrap="none",
            height=10,
            bg=self._theme["text_bg"],
            fg=self._theme["text_fg"],
            insertbackground=self._theme["text_fg"],
        )
        self.inspector_output.grid(row=0, column=0, sticky="ew")
        out_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.inspector_output.yview)
        out_scroll.grid(row=0, column=1, sticky="ns")
        self.inspector_output.configure(yscrollcommand=out_scroll.set)
        self._replace_text(self.inspector_output, "Select an inspector file, then preview or scan it from this legacy helper.\n", readonly=True)

        self.inspector_candidate_tree = ttk.Treeview(card, columns=("offset", "type", "nearby"), show="headings", height=4)
        for col, heading in (("offset", "Offset"), ("type", "Type"), ("nearby", "Nearby strings")):
            self.inspector_candidate_tree.heading(col, text=heading)
        self.inspector_candidate_tree.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))

    def _ccsf_text_tab(self, notebook: ttk.Notebook, title: str, height: int) -> tk.Text:
        frame = ttk.Frame(notebook)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        text = tk.Text(frame, wrap="word", height=height, bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)
        notebook.add(frame, text=title)
        return text

    def _default_ccsf_report_path(self, name: str) -> Path:
        candidates = [
            self._active_workspace_root() / "reports" / name,
            self._iso_ccsf_workspace() / "reports" / name,
            REPORTS_WORKSPACE / name,
        ]
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    def load_default_ccsf_asset_library(self) -> None:
        path = self._default_ccsf_report_path("asset_library.json")
        if not path.exists():
            return
        try:
            self.ccsf_asset_library = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.ccsf_filter_summary.set(f"Could not load asset_library.json: {exc}")
            return
        self.ccsf_view_mode.set("logical")
        self._update_ccsf_filter_choices()
        self._refresh_ccsf_assets_tree()
        self._replace_text(self.ccsf_assets_details, f"Loaded logical asset library:\n{path}\n", readonly=True)
        self._replace_text(self.ccsf_assets_manifest, format_ccsf_asset_library(self.ccsf_asset_library), readonly=True)
        self._refresh_ccsf_survey_tabs()

    def _build_ccsf_assets_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)
        bar = ttk.Frame(parent)
        bar.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        bar.grid_columnconfigure(0, weight=1)
        ttk.Label(parent, text="Asset Library", font=("TkDefaultFont", 14, "bold")).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 0))
        folder_row = self._build_path_row(bar, "Library folder", self.ccsf_assets_folder, browse_command=self.pick_ccsf_assets_folder, open_command=lambda: self._open_existing_variable_path(self.ccsf_assets_folder), browse_text="Choose folder")
        folder_row.grid(row=0, column=0, sticky="ew")
        self.ccsf_assets_folder_entry = next(child for child in folder_row.winfo_children() if isinstance(child, ttk.Entry))
        self.ccsf_assets_choose_button = next(child for child in folder_row.winfo_children() if isinstance(child, ttk.Button) and child.cget("text") == "Choose folder")
        self.ccsf_assets_scan_button = ttk.Button(bar, text="Refresh Library", command=self.scan_ccsf_assets_folder)
        self.ccsf_assets_scan_button.grid(row=0, column=1, padx=(8, 0))
        self.ccsf_scan_controls = [self.ccsf_assets_folder_entry, self.ccsf_assets_choose_button, self.ccsf_assets_scan_button]

        filters = ttk.Frame(parent)
        filters.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        for col in (1, 3, 5, 7):
            filters.grid_columnconfigure(col, weight=1)
        ttk.Label(filters, text="Search").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.ccsf_filter_search, width=18).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Label(filters, text="Type").grid(row=0, column=2, sticky="w")
        self.ccsf_type_filter_combo = ttk.Combobox(filters, textvariable=self.ccsf_filter_type, values=("All",), state="readonly", width=18)
        self.ccsf_type_filter_combo.grid(row=0, column=3, sticky="ew", padx=(4, 8))
        ttk.Label(filters, text="Variant").grid(row=0, column=4, sticky="w")
        self.ccsf_variant_filter_combo = ttk.Combobox(filters, textvariable=self.ccsf_filter_variant, values=("All",), state="readonly", width=12)
        self.ccsf_variant_filter_combo.grid(row=0, column=5, sticky="ew", padx=(4, 8))
        ttk.Label(filters, text="Readiness").grid(row=0, column=6, sticky="w")
        self.ccsf_readiness_filter_combo = ttk.Combobox(filters, textvariable=self.ccsf_filter_readiness, values=("All",), state="readonly", width=14)
        self.ccsf_readiness_filter_combo.grid(row=0, column=7, sticky="ew", padx=(4, 0))
        view_controls = ttk.Frame(filters)
        view_controls.grid(row=1, column=0, columnspan=8, sticky="ew", pady=(6, 0))
        ttk.Label(view_controls, text="View:").pack(side="left", padx=(0, 4))
        ttk.Radiobutton(view_controls, text="Logical assets", variable=self.ccsf_view_mode, value="logical", command=self._sync_ccsf_view_toggle).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(view_controls, text="show physical files", variable=self.ccsf_show_physical_files, command=self._toggle_ccsf_physical_files).pack(side="left", padx=(0, 12))
        for label, var in (
            ("show duplicates", self.ccsf_show_duplicates),
            ("show unknown", self.ccsf_show_unknown),
            ("show media candidates", self.ccsf_show_media_candidates),
            ("character/body", self.ccsf_filter_character_body),
            ("character/color variant", self.ccsf_filter_character_color_variant),
            ("environment/background", self.ccsf_filter_environment_background),
            ("has animation", self.ccsf_filter_has_animation),
            ("has texture+CLT", self.ccsf_filter_has_texture_clt),
        ):
            ttk.Checkbutton(view_controls, text=label, variable=var, command=self._refresh_ccsf_assets_tree).pack(side="left", padx=(0, 8))
        ttk.Label(filters, textvariable=self.ccsf_filter_summary).grid(row=2, column=0, columnspan=8, sticky="e", pady=(6, 0))
        for var in (self.ccsf_filter_search, self.ccsf_filter_type, self.ccsf_filter_variant, self.ccsf_filter_readiness, self.ccsf_view_mode):
            var.trace_add("write", lambda *_args: self._refresh_ccsf_assets_tree())

        panes = ttk.Panedwindow(parent, orient="horizontal")
        panes.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))
        table_frame = ttk.Frame(panes)
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        cols = ("type", "variant", "file", "size", "MDL", "TEX", "CLT", "MAT", "ANM", "OBJ", "readiness")
        self.ccsf_assets_tree = ttk.Treeview(table_frame, columns=cols, show="tree headings", height=12)
        self.ccsf_assets_tree.heading("#0", text="CCSF name")
        self.ccsf_assets_tree.column("#0", width=150, stretch=True)
        for col, width in (("type", 150), ("variant", 60), ("file", 230), ("size", 80), ("MDL", 45), ("TEX", 45), ("CLT", 45), ("MAT", 45), ("ANM", 45), ("OBJ", 45), ("readiness", 120)):
            self.ccsf_assets_tree.heading(col, text=col)
            self.ccsf_assets_tree.column(col, width=width, anchor="e" if col in {"size", "MDL", "TEX", "CLT", "MAT", "ANM", "OBJ"} else "w", stretch=col in {"type", "file", "readiness"})
        self.ccsf_assets_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.ccsf_assets_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.ccsf_assets_tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.ccsf_assets_tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.ccsf_assets_tree.bind("<<TreeviewSelect>>", self.on_ccsf_asset_select)
        panes.add(table_frame, weight=3)

        details = ttk.Frame(panes)
        details.grid_rowconfigure(0, weight=1)
        details.grid_columnconfigure(0, weight=1)
        self.ccsf_assets_notebook = ttk.Notebook(details)
        self.ccsf_assets_notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        self.ccsf_assets_details = self._ccsf_text_tab(self.ccsf_assets_notebook, "Details", 12)
        self.ccsf_assets_manifest = self._ccsf_text_tab(self.ccsf_assets_notebook, "Manifest", 10)
        self.ccsf_audio_survey = self._ccsf_text_tab(self.ccsf_assets_notebook, "Audio Survey", 10)
        self.ccsf_dialogue_survey = self._ccsf_text_tab(self.ccsf_assets_notebook, "Dialogue/Text Survey", 10)
        self.ccsf_script_survey = self._ccsf_text_tab(self.ccsf_assets_notebook, "Script/Logic Survey", 10)
        self._build_path_row(
            details,
            "Selected asset path",
            self.ccsf_selected_asset_path,
            open_command=lambda: self._open_existing_variable_path(self.ccsf_selected_asset_path),
        ).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        actions = ActionSection(
            details,
            "Asset Library Build / Refresh",
            "Build preview manifests from the selected CCSF asset library and open generated dashboards or preferred files.",
            status_variable=self.ccsf_filter_summary,
            progress_variable=self.ccsf_manifest_progress,
            progress_text_variable=self.ccsf_manifest_progress_text,
            include_progress=True,
            output_buttons=[
                {"text": "Open Results Dashboard", "command": self.open_ccsf_results_dashboard},
                {"text": "Open Asset Survey Dashboard", "command": self.open_ccsf_asset_survey_dashboard},
                {"text": "Open Selected File", "command": self.open_selected_ccsf_preferred_file},
                {"text": "Copy Selected Path", "command": self.copy_selected_ccsf_path},
                {"text": "Open Containing Folder", "command": self.open_selected_ccsf_containing_folder},
            ],
            columns_at_width=[(760, 4), (520, 2)],
        )
        actions.grid(row=2, column=0, sticky="ew")
        self.ccsf_manifest_progress_bar = actions.progress_bar
        for text, command in (
            ("Build Manifest for Selected Asset", self.build_ccsf_preview_manifest),
            ("Copy Manifest", self.copy_ccsf_manifest),
            ("Save Manifest", self.save_ccsf_manifest),
            ("Preview Asset", self.preview_ccsf_asset),
        ):
            actions.add_button(text=text, command=command)
        panes.add(details, weight=2)
        self.ccsf_selected_asset_path.set("")
        self._replace_text(self.ccsf_assets_details, "Choose an extracted CCS folder, then scan.\n", readonly=True)
        self._replace_text(self.ccsf_assets_manifest, "Manifest is built only when Build Manifest is clicked.\n", readonly=True)


    def _build_iso_ccsf_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_rowconfigure(3, weight=1)
        controls = ActionSection(
            parent,
            "ISO Extraction / ISO → CCSF",
            "Choose a PS2 ISO, build or load its index, then extract confirmed CCSF bundles into the active workspace.",
            status_variable=self.iso_ccsf_status,
            progress_variable=self.iso_ccsf_progress,
            progress_text_variable=self.iso_ccsf_progress_text,
            include_progress=True,
            output_buttons=[
                {"text": "Open Extracted CCSF Folder", "command": self.open_iso_ccsf_output_folder},
                {"text": "Open Asset Index", "command": self.open_iso_ccsf_asset_index},
                {"text": "Open CCSF Asset Browser", "command": self.open_ccsf_asset_browser},
            ],
            columns_at_width=[(900, 4), (620, 2)],
        )
        controls.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        controls.add_content(self._build_path_row(controls, "ISO", self.iso_path, browse_command=self.pick_iso, open_command=lambda: self._open_existing_variable_path(self.iso_path)), padx=8, pady=(0, 6))
        for text, command in (
            ("Choose ISO", self.pick_iso),
            ("Build/Load ISO Index", self.build_or_load_iso_ccsf_index),
            ("Extract CCSF Library", self.extract_iso_ccsf_library),
            ("Cancel ISO CCSF", self.cancel_iso_ccsf_job),
            ("Index Extracted CCSF Assets", self.index_extracted_iso_ccsf_assets),
        ):
            button = controls.add_button(text=text, command=command)
            if text == "Cancel ISO CCSF":
                self.iso_ccsf_cancel_button = button
                self.iso_ccsf_cancel_buttons.append(button)
                button.configure(state="disabled")

        status = ttk.LabelFrame(parent, text="ISO-to-CCSF Workflow Details")
        status.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        status.grid_columnconfigure(1, weight=1)
        rows = [
            ("Workflow", self.iso_ccsf_status),
            ("ISO path", self.iso_path),
            ("Index status", self.iso_ccsf_index_status),
            ("Selected top-level containers", self.iso_ccsf_selected_containers),
            ("Scan progress", self.iso_ccsf_scan_progress),
            ("Current stage", self.iso_ccsf_current_stage),
            ("Current container", self.iso_ccsf_current_container),
            ("Containers scanned", self.iso_ccsf_containers_scanned),
            ("Bytes scanned", self.iso_ccsf_bytes_scanned),
            ("Gzip offsets seen", self.iso_ccsf_gzip_offsets_seen),
            ("Valid gzip members", self.iso_ccsf_valid_gzip_members),
            ("False positives skipped", self.iso_ccsf_false_positives_skipped),
            ("CCSF bundles found", self.iso_ccsf_bundles_found),
            ("Duplicates skipped", self.iso_ccsf_duplicates_skipped),
            ("Assets indexed", self.iso_ccsf_assets_indexed),
            ("Extraction errors/warnings", self.iso_ccsf_errors_warnings),
            ("Output paths", self.iso_ccsf_output_paths),
        ]
        for r, (label, var) in enumerate(rows):
            ttk.Label(status, text=f"{label}:").grid(row=r, column=0, sticky="nw", padx=(8, 6), pady=2)
            ttk.Label(status, textvariable=var, wraplength=760, justify="left").grid(row=r, column=1, sticky="ew", pady=2)
        self.iso_ccsf_progress_bar = controls.progress_bar

        results = ttk.LabelFrame(parent, text="Extracted CCSF Results")
        results.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        results.grid_rowconfigure(1, weight=1)
        results.grid_columnconfigure(0, weight=1)
        actions = ttk.Frame(results)
        actions.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        for text, command in (
            ("Open Extracted CCSF Folder", self.open_iso_ccsf_output_folder),
            ("Open Asset Index", self.open_iso_ccsf_asset_index),
            ("Open First Character/Body", lambda: self.open_first_iso_ccsf_asset("character/body")),
            ("Open First Environment/Background", lambda: self.open_first_iso_ccsf_asset("environment/background")),
            ("Open First Character/Color Variant", lambda: self.open_first_iso_ccsf_asset("character/color variant")),
            ("Build Manifest for Selected", self.build_iso_ccsf_manifest_for_selected),
        ):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 6), pady=(0, 4))
        cols = ("status", "duplicate", "layer", "size", "sha1", "path")
        self.iso_ccsf_results_tree = ttk.Treeview(results, columns=cols, show="tree headings", height=7)
        self.iso_ccsf_results_tree.heading("#0", text="CCSF name")
        self.iso_ccsf_results_tree.column("#0", width=170, stretch=True)
        for col, width in (("status", 90), ("duplicate", 80), ("layer", 80), ("size", 80), ("sha1", 130), ("path", 360)):
            self.iso_ccsf_results_tree.heading(col, text=col)
            self.iso_ccsf_results_tree.column(col, width=width, anchor="e" if col == "size" else "w", stretch=col == "path")
        self.iso_ccsf_results_tree.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        scroll = ttk.Scrollbar(results, orient="vertical", command=self.iso_ccsf_results_tree.yview)
        scroll.grid(row=1, column=1, sticky="ns", pady=(0, 6))
        self.iso_ccsf_results_tree.configure(yscrollcommand=scroll.set)
        self.iso_ccsf_results_tree.bind("<<TreeviewSelect>>", self.on_iso_ccsf_bundle_select)

        raw = ttk.LabelFrame(parent, text="Raw JSON/progress (Debug console mode only)")
        raw.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))
        raw.grid_rowconfigure(0, weight=1)
        raw.grid_columnconfigure(0, weight=1)
        self.iso_ccsf_raw_frame = raw
        self.iso_ccsf_details = tk.Text(raw, wrap="word", height=10, bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.iso_ccsf_details.grid(row=0, column=0, sticky="nsew")
        raw_scroll = ttk.Scrollbar(raw, orient="vertical", command=self.iso_ccsf_details.yview)
        raw_scroll.grid(row=0, column=1, sticky="ns")
        self.iso_ccsf_details.configure(yscrollcommand=raw_scroll.set)
        self._replace_text(self.iso_ccsf_details, "This panel runs tools/iso_ccsf_extractor.py in the configured workspace. Confirmed bundles populate the results table.\n", readonly=True)
        self.console_mode.trace_add("write", lambda *_args: self._sync_iso_ccsf_details_visibility())
        self._sync_iso_ccsf_details_visibility()

    def _iso_ccsf_workspace(self) -> Path:
        workspace = self._ensure_research_workspace()
        (workspace / "reports").mkdir(parents=True, exist_ok=True)
        return workspace

    def _iso_ccsf_index_path(self) -> Path:
        return self._iso_ccsf_workspace() / "reports" / "iso_ccsf_iso_index.json"

    def build_or_load_iso_ccsf_index(self) -> None:
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing ISO", "Choose an ISO first.")
        index_path = self._iso_ccsf_index_path()
        self.iso_index_path.set(str(index_path))
        if index_path.exists():
            self.load_iso_index()
            self.iso_ccsf_index_status.set(f"Index: loaded {index_path}")
            self.iso_ccsf_status.set("ISO index loaded.")
            return
        self.iso_ccsf_index_status.set("Index: building in workspace reports folder")
        self._console_write(f"[ISO→CCSF] Building ISO index in workspace: {index_path}\n")
        self.build_iso_index()

    def extract_iso_ccsf_library(self) -> None:
        if self.iso_ccsf_job_active:
            return messagebox.showwarning("Busy", "An ISO CCSF extraction/indexing job is already running.")
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing ISO", "Choose an ISO first.")
        workspace = self._iso_ccsf_workspace()
        index_path = self._iso_ccsf_index_path()
        out_json = workspace / "reports" / "iso_ccsf_extraction_index.json"
        out_txt = workspace / "reports" / "iso_ccsf_extraction_index.txt"
        cmd = [PY, str(TOOLS / "iso_ccsf_extractor.py"), iso, "--workspace", str(workspace), "--iso-index", str(index_path), "--build-index", "--out", str(out_json), "--text-out", str(out_txt), "--reuse-existing", "--index-assets", "--progress-jsonl"]
        self.iso_ccsf_job_active = True
        self.iso_ccsf_cancel_requested = False
        self.iso_ccsf_cancel_event = None
        self._set_iso_ccsf_cancel_state()
        self.iso_ccsf_status.set("Extraction running.")
        self.iso_ccsf_scan_progress.set("Scan progress: starting")
        self.iso_ccsf_current_stage.set("Stage: starting")
        self.iso_ccsf_current_container.set("Current container: none")
        self.iso_ccsf_progress.set(0.0)
        self.iso_ccsf_progress_text.set("0% (0/0)")
        self.iso_ccsf_bytes_scanned.set("Bytes scanned: 0")
        self.iso_ccsf_gzip_offsets_seen.set("Gzip offsets seen: 0")
        self.iso_ccsf_output_paths.set(f"JSON: {out_json}\nText: {out_txt}\nAssets: {workspace / 'extracted_ccs'}")
        self._replace_text(self.iso_ccsf_details, f"Command: {self._format_command(cmd)}\nWorkspace: {workspace}\n", readonly=True)

        latest_progress_lock = threading.Lock()
        latest_event: dict | None = None
        latest_progress_state = {"done": 0, "total": 0, "containers": []}
        progress_callback_scheduled = False

        def copy_progress_state(progress: dict) -> dict:
            copied = dict(progress)
            copied["containers"] = list(progress.get("containers") or [])
            return copied

        def consume_latest_progress_event() -> bool:
            nonlocal latest_event, latest_progress_state
            with latest_progress_lock:
                event = latest_event
                latest_event = None
                progress = copy_progress_state(latest_progress_state)
            if event is None:
                return False
            self._handle_iso_ccsf_progress_event(event, progress)
            with latest_progress_lock:
                latest_progress_state = copy_progress_state(progress)
            return True

        def schedule_progress_callback() -> None:
            nonlocal progress_callback_scheduled
            if progress_callback_scheduled:
                return
            progress_callback_scheduled = True

            def drain_latest_progress_event() -> None:
                nonlocal progress_callback_scheduled
                progress_callback_scheduled = False
                consume_latest_progress_event()
                if self.iso_ccsf_job_active:
                    schedule_progress_callback()

            self.after(150, drain_latest_progress_event)

        def on_line(line: str) -> None:
            nonlocal latest_event
            s = (line or "").strip()
            if not s.startswith("{"):
                return
            try:
                event = json.loads(s)
            except Exception:
                return
            if not isinstance(event, dict):
                return
            with latest_progress_lock:
                latest_event = event

        def on_done(rc: int) -> None:
            consume_latest_progress_event()
            self._finish_iso_ccsf_extraction(rc, out_json, out_txt, workspace)

        started = self._run_task(cmd, on_done=on_done, on_line=on_line, label="iso ccsf extraction")
        if started:
            schedule_progress_callback()
        else:
            self.iso_ccsf_job_active = False
            self._set_iso_ccsf_cancel_state()

    def _set_iso_ccsf_cancel_state(self) -> None:
        enabled = self.iso_ccsf_job_active and not self.iso_ccsf_cancel_requested
        buttons = list(getattr(self, "iso_ccsf_cancel_buttons", []))
        if hasattr(self, "iso_ccsf_cancel_button") and self.iso_ccsf_cancel_button not in buttons:
            buttons.append(self.iso_ccsf_cancel_button)
        for button in buttons:
            try:
                button.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass

    def cancel_iso_ccsf_job(self) -> None:
        if not self.iso_ccsf_job_active:
            self.iso_ccsf_status.set("No active ISO CCSF job to cancel.")
            self._set_iso_ccsf_cancel_state()
            return
        self.iso_ccsf_cancel_requested = True
        self.iso_ccsf_status.set("Cancellation requested; stopping ISO CCSF subprocess.")
        self.iso_ccsf_current_stage.set("Stage: cancelling")
        self.runner.cancel()
        self._set_iso_ccsf_cancel_state()

    def _handle_iso_ccsf_progress_event(self, event: object, progress: dict) -> None:
        if not isinstance(event, dict):
            return
        stage = str(event.get("stage") or "progress")
        current = str(event.get("current_container") or "")
        done = int(event.get("container_index") or progress.get("done") or 0)
        total = int(event.get("container_total") or progress.get("total") or 0)
        progress["done"] = done
        progress["total"] = total
        progress["bytes_scanned"] = int(event.get("bytes_scanned") or progress.get("bytes_scanned") or 0)
        progress["gzip_offsets_seen"] = int(event.get("gzip_offsets_seen") or progress.get("gzip_offsets_seen") or 0)
        if current and (not progress["containers"] or progress["containers"][-1] != current):
            progress["containers"].append(current)
        label = f"Scan progress: {done}/{total}" if total else "Scan progress: starting"
        if current:
            label += f" ({current})"
        if stage in {"complete", "assets_indexed"}:
            label += f" — {stage.replace('_', ' ')}"
        self.iso_ccsf_scan_progress.set(label)
        pct = (done / total * 100.0) if total else 0.0
        self.iso_ccsf_progress.set(pct)
        self.iso_ccsf_progress_text.set(f"{pct:.1f}% ({done}/{total})" if total else "0% (0/0)")
        self.iso_ccsf_current_stage.set(f"Stage: {stage.replace('_', ' ')}")
        self.iso_ccsf_current_container.set(f"Current container: {current or 'none'}")
        self.iso_ccsf_containers_scanned.set(f"Containers scanned: {done}")
        self.iso_ccsf_bytes_scanned.set(f"Bytes scanned: {progress['bytes_scanned']:,}")
        self.iso_ccsf_gzip_offsets_seen.set(f"Gzip offsets seen: {progress['gzip_offsets_seen']:,}")
        self.iso_ccsf_valid_gzip_members.set(f"Valid gzip members: {event.get('gzip_valid_members', 0)}")
        self.iso_ccsf_false_positives_skipped.set(f"False positives skipped: {event.get('false_positives_skipped', 0)}")
        self.iso_ccsf_bundles_found.set(f"CCSF bundles found: {event.get('ccsf_bundles_extracted', 0)}")
        self.iso_ccsf_assets_indexed.set(f"Assets indexed: {event.get('assets_indexed', 0)}")
        shown = progress["containers"][-8:]
        suffix = "" if len(progress["containers"]) <= 8 else f"\n… {len(progress['containers']) - 8} earlier"
        self.iso_ccsf_selected_containers.set("Selected top-level containers:\n" + "\n".join(shown) + suffix)

    def _write_iso_ccsf_cancelled_report(self, workspace: Path, out_json: Path, out_txt: Path, progress: dict) -> None:
        report = {"created_at": _utc_timestamp(), "iso_path": self.iso_path.get().strip(), "workspace": str(workspace), "status": "cancelled", "containers_scanned": progress.get("done", 0), "containers_selected": progress.get("total", 0), "bytes_scanned": progress.get("bytes_scanned", 0), "gzip_offsets_seen": progress.get("gzip_offsets_seen", 0), "extractions": []}
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        out_txt.write_text("ISO CCSF extraction cancelled. Partial staged files may remain in workspace/iso_ccsf_staging.\n", encoding="utf-8")

    def _finish_iso_ccsf_extraction(self, rc: int, out_json: Path, out_txt: Path, workspace: Path) -> None:
        report = None
        if out_json.exists():
            try:
                report = json.loads(out_json.read_text(encoding="utf-8"))
            except Exception as exc:
                self._console_write(f"[ISO→CCSF] Could not read report: {exc}\n")
        self.iso_ccsf_job_active = False
        self.iso_ccsf_cancel_requested = False
        self.iso_ccsf_cancel_event = None
        self._set_iso_ccsf_cancel_state()
        self.iso_ccsf_report = report
        rows = (report or {}).get("extractions") or []
        errors = [r for r in rows if r.get("error_warning") or r.get("extraction_status") == "error"]
        extracted = len([r for r in rows if r.get("extraction_status") == "extracted"])
        dupes = len([r for r in rows if r.get("duplicate_status") == "duplicate"])
        selected = int((report or {}).get('containers_selected', 0) or 0)
        scanned = int((report or {}).get('containers_scanned', 0) or 0)
        pct = (scanned / selected * 100.0) if selected else (100.0 if rc == 0 else self.iso_ccsf_progress.get())
        self.iso_ccsf_progress.set(pct)
        self.iso_ccsf_progress_text.set(f"{pct:.1f}% ({scanned}/{selected})" if selected else ("100%" if rc == 0 else self.iso_ccsf_progress_text.get()))
        self.iso_ccsf_current_stage.set(f"Stage: {'cancelled' if rc == -15 else ('complete' if rc == 0 else 'failed')}")
        self.iso_ccsf_current_container.set("Current container: none")
        self.iso_ccsf_containers_scanned.set(f"Containers scanned: {scanned}")
        self.iso_ccsf_bytes_scanned.set(f"Bytes scanned: {int((report or {}).get('bytes_scanned', 0) or 0):,}")
        self.iso_ccsf_gzip_offsets_seen.set(f"Gzip offsets seen: {int((report or {}).get('gzip_offsets_seen', 0) or 0):,}")
        self.iso_ccsf_valid_gzip_members.set(f"Valid gzip members: {(report or {}).get('gzip_valid_members', 0)}")
        self.iso_ccsf_false_positives_skipped.set(f"False positives skipped: {(report or {}).get('gzip_false_positive_skipped', 0)}")
        self.iso_ccsf_bundles_found.set(f"CCSF bundles found: {len((report or {}).get('confirmed_ccsf_bundles') or []) or extracted}")
        self.iso_ccsf_duplicates_skipped.set(f"Duplicates skipped: {(report or {}).get('duplicates_skipped', dupes)}")
        self.iso_ccsf_assets_indexed.set(f"Assets indexed: {(report or {}).get('ccsf_assets_indexed', 0)}")
        self.iso_ccsf_errors_warnings.set(f"Errors/warnings: {len(errors)}")
        self.iso_ccsf_output_paths.set(f"JSON: {out_json}\nText: {out_txt}\nAssets: {workspace / 'extracted_ccs'}")
        status = "cancelled" if rc == -15 or (report or {}).get("status") == "cancelled" else ("complete" if rc == 0 else "failed")
        self.iso_ccsf_status.set(f"Extraction {status}.")
        if status == "complete":
            self.ccsf_assets_folder.set(str(workspace / "extracted_ccs"))
            self.iso_ccsf_scan_progress.set(f"Scan progress: complete ({(report or {}).get('containers_scanned', 0)} containers)")
        text = out_txt.read_text(encoding="utf-8", errors="replace") if out_txt.exists() else f"Extraction {status}; no text report generated."
        self._refresh_iso_ccsf_results_tree()
        self._replace_text(self.iso_ccsf_details, text, readonly=True)
        self.refresh_project_tree()
        self.refresh_quick_report_locator()
        if status == "complete":
            self.ccsf_viewer_extracted_folder.set(str(workspace / "extracted_ccs"))
            self.ccsf_viewer_asset_library_path.set(str(workspace / "reports" / "asset_library.json"))
            self.load_ccsf_viewer_asset_library(silent=True)

    def _refresh_iso_ccsf_results_tree(self) -> None:
        if not hasattr(self, "iso_ccsf_results_tree"):
            return
        self.iso_ccsf_bundle_by_iid = {}
        for iid in self.iso_ccsf_results_tree.get_children():
            self.iso_ccsf_results_tree.delete(iid)
        bundles = (self.iso_ccsf_report or {}).get("confirmed_ccsf_bundles") or []
        for idx, row in enumerate(bundles):
            iid = f"iso_ccsf_bundle_{idx}"
            values = (
                row.get("extraction_status", ""),
                row.get("duplicate_status", ""),
                row.get("compression_layer", ""),
                row.get("size", 0),
                str(row.get("sha1") or "")[:12],
                row.get("extracted_ccsf_path") or row.get("container_path") or "",
            )
            self.iso_ccsf_results_tree.insert("", "end", iid=iid, text=row.get("ccsf_name") or Path(str(row.get("extracted_ccsf_path", ""))).stem, values=values)
            self.iso_ccsf_bundle_by_iid[iid] = row

    def _selected_iso_ccsf_bundle(self) -> dict | None:
        if not hasattr(self, "iso_ccsf_results_tree"):
            return None
        selection = self.iso_ccsf_results_tree.selection()
        return self.iso_ccsf_bundle_by_iid.get(selection[0]) if selection else None

    def on_iso_ccsf_bundle_select(self, _event=None) -> None:
        row = self._selected_iso_ccsf_bundle()
        if not row:
            return
        lines = ["Selected confirmed CCSF bundle"]
        for key in ("ccsf_name", "extracted_ccsf_path", "top_level_iso_file_path", "container_path", "source_offset", "compression_layer", "size", "sha1", "duplicate_status", "extraction_status", "error_warning"):
            lines.append(f"{key}: {row.get(key) or ''}")
        self._replace_text(self.iso_ccsf_details, "\n".join(lines) + "\n", readonly=True)

    def open_iso_ccsf_output_folder(self) -> None:
        folder = self._iso_ccsf_workspace() / "extracted_ccs"
        self._open_folder_path(folder)

    def open_iso_ccsf_asset_index(self) -> None:
        report_path = (self.iso_ccsf_report or {}).get("asset_index_path")
        path = Path(report_path) if report_path else self._iso_ccsf_workspace() / "reports" / "ccsf_asset_index.json"
        if not path.exists():
            return messagebox.showinfo("CCSF asset index", f"Asset index not found:\n{path}\n\nRun Index Extracted CCSF Assets first.")
        self._open_path_with_platform(path)

    def _load_iso_ccsf_asset_index(self) -> dict | None:
        path = Path((self.iso_ccsf_report or {}).get("asset_index_path") or self._iso_ccsf_workspace() / "reports" / "ccsf_asset_index.json")
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                messagebox.showerror("CCSF asset index", f"Could not read asset index:\n{path}\n\n{exc}")
                return None
        folder = self._iso_ccsf_workspace() / "extracted_ccs"
        if folder.exists():
            return index_ccsf_asset_folder(folder, quiet=True)
        return None

    def _first_iso_ccsf_asset(self, asset_type: str) -> dict | None:
        index = self._load_iso_ccsf_asset_index()
        for asset in (index or {}).get("assets") or []:
            if asset.get("type") == asset_type:
                return asset
        return None

    def open_first_iso_ccsf_asset(self, asset_type: str) -> None:
        asset = self._first_iso_ccsf_asset(asset_type)
        if not asset:
            return messagebox.showinfo("CCSF asset", f"No indexed asset found for type: {asset_type}")
        path = Path(str(asset.get("file") or ""))
        if not path.exists():
            return messagebox.showinfo("CCSF asset", f"Asset file not found:\n{path}")
        self._open_path_with_platform(path)

    def build_iso_ccsf_manifest_for_selected(self) -> None:
        row = self._selected_iso_ccsf_bundle()
        if not row:
            return messagebox.showinfo("CCSF preview manifest", "Select a confirmed CCSF bundle first.")
        path = Path(str(row.get("extracted_ccsf_path") or ""))
        if not path.exists():
            return messagebox.showinfo("CCSF preview manifest", f"Extracted CCSF file not found:\n{path}")
        manifest = build_ccsf_preview_manifest(path)
        self.iso_ccsf_manifest_payload = manifest
        self._replace_text(self.iso_ccsf_details, format_ccsf_preview_manifest_text(manifest), readonly=True)

    def index_extracted_iso_ccsf_assets(self) -> None:
        self.ccsf_assets_folder.set(str(self._iso_ccsf_workspace() / "extracted_ccs"))
        self.scan_ccsf_assets_folder()

    def open_ccsf_asset_browser(self) -> None:
        self.ccsf_assets_folder.set(str(self._iso_ccsf_workspace() / "extracted_ccs"))
        # Select the existing CCSF Assets tab so users can index/browse immediately.
        for tab_id in self.nb.tabs():
            if self.nb.tab(tab_id, "text") == "CCSF Assets":
                self.nb.select(tab_id)
                break

    def pick_ccsf_assets_folder(self) -> None:
        path = filedialog.askdirectory(initialdir=self.ccsf_assets_folder.get() or str(WORKSPACE))
        if path:
            self.ccsf_assets_folder.set(path)

    def _set_ccsf_scan_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in getattr(self, "ccsf_scan_controls", []):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass

    def scan_ccsf_assets_folder(self) -> None:
        if self.ccsf_scan_active:
            self.ccsf_filter_summary.set("CCSF asset scan is already running.")
            return
        folder = Path(self.ccsf_assets_folder.get().strip() or WORKSPACE / "extracted_ccs").expanduser()
        if not folder.exists():
            return messagebox.showerror("CCSF Assets", f"Folder does not exist:\n{folder}")

        events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.ccsf_scan_queue = events
        self.ccsf_scan_active = True
        self._set_ccsf_scan_controls_enabled(False)
        self.ccsf_filter_summary.set(f"Scanning {folder}…")
        self._replace_text(self.ccsf_assets_details, f"Scanning CCSF assets in:\n{folder}\n", readonly=True)
        self._replace_text(self.ccsf_assets_manifest, "Manifest is built only when Build Manifest is clicked.\n", readonly=True)

        def worker() -> None:
            try:
                events.put(("progress", f"Indexing CCSF assets in {folder}"))
                index = index_ccsf_asset_folder(folder)
            except Exception as exc:
                events.put(("error", exc))
            else:
                events.put(("result", index))

        def poll_events() -> None:
            keep_polling = self.ccsf_scan_active
            try:
                while True:
                    kind, payload = events.get_nowait()
                    if kind == "progress":
                        self.ccsf_filter_summary.set(str(payload))
                    elif kind == "error":
                        self.ccsf_scan_active = False
                        self.ccsf_scan_queue = None
                        self._set_ccsf_scan_controls_enabled(True)
                        self.ccsf_filter_summary.set("Scan failed.")
                        self._replace_text(self.ccsf_assets_details, f"Scan failed:\n{payload}\n", readonly=True)
                        keep_polling = False
                        messagebox.showerror("CCSF Assets", f"Scan failed:\n{payload}")
                    elif kind == "result":
                        index = payload
                        self.ccsf_asset_index = index
                        try:
                            self.ccsf_asset_library = build_asset_library(index)
                        except Exception:
                            self.ccsf_asset_library = None
                        self._update_ccsf_filter_choices()
                        self._refresh_ccsf_assets_tree()
                        reports = self._active_workspace_root() / "reports"
                        reports.mkdir(parents=True, exist_ok=True)
                        (reports / "ccsf_asset_index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
                        (reports / "ccsf_asset_index.txt").write_text(format_ccsf_asset_index(index), encoding="utf-8")
                        if self.ccsf_asset_library:
                            (reports / "asset_library.json").write_text(json.dumps(self.ccsf_asset_library, indent=2), encoding="utf-8")
                            (reports / "asset_library.txt").write_text(format_ccsf_asset_library(self.ccsf_asset_library), encoding="utf-8")
                        self._replace_text(self.ccsf_assets_details, f"Scanned {index.get('asset_count', 0)} CCSF asset(s). Reports written to:\n{reports}\n", readonly=True)
                        self._replace_text(self.ccsf_assets_manifest, "Manifest is built only when Build Manifest is clicked.\n", readonly=True)
                        self._refresh_ccsf_survey_tabs()
                        self.ccsf_scan_active = False
                        self.ccsf_scan_queue = None
                        self._set_ccsf_scan_controls_enabled(True)
                        keep_polling = False
            except queue.Empty:
                pass
            if keep_polling:
                self.after(100, poll_events)

        threading.Thread(target=worker, daemon=True, name="ccsf-asset-indexer").start()
        self.after(100, poll_events)

    def _sync_ccsf_view_toggle(self) -> None:
        if hasattr(self, "ccsf_show_physical_files"):
            self.ccsf_show_physical_files.set(self.ccsf_view_mode.get() == "physical")
        self._refresh_ccsf_assets_tree()

    def _toggle_ccsf_physical_files(self) -> None:
        self.ccsf_view_mode.set("physical" if self.ccsf_show_physical_files.get() else "logical")
        self._refresh_ccsf_assets_tree()

    def _ccsf_current_assets(self) -> list[dict]:
        if self.ccsf_view_mode.get() == "physical":
            return list((self.ccsf_asset_index or {}).get("assets") or [])
        return list((self.ccsf_asset_library or {}).get("assets") or [])

    def _ccsf_counts(self, asset: dict) -> dict:
        return ccsf_asset_counts(asset)

    def _ccsf_name(self, asset: dict) -> str:
        return str(asset.get("display_name") or asset.get("name") or Path(str(asset.get("preferred_file") or asset.get("file") or "")).stem)

    def _ccsf_file(self, asset: dict) -> str:
        return str(asset.get("preferred_file") or asset.get("relative_file") or asset.get("file") or "")

    def _update_ccsf_filter_choices(self) -> None:
        assets = self._ccsf_current_assets()
        types = sorted({str(asset.get("type") or "unknown") for asset in assets})
        variants = sorted({str(asset.get("variant") or "-") for asset in assets})
        readiness = sorted({str(asset.get("readiness") or "unknown") for asset in assets})
        self.ccsf_type_filter_combo.configure(values=("All", *types))
        self.ccsf_variant_filter_combo.configure(values=("All", *variants))
        self.ccsf_readiness_filter_combo.configure(values=("All", *readiness))

    def _ccsf_selected_asset(self) -> dict | None:
        selection = self.ccsf_assets_tree.selection()
        return self.ccsf_asset_by_iid.get(selection[0]) if selection else None

    def _ccsf_asset_matches_filters(self, asset: dict) -> bool:
        counts = self._ccsf_counts(asset)
        asset_type = str(asset.get("type") or "unknown")
        variant = str(asset.get("variant") or "-")
        readiness = str(asset.get("readiness") or "unknown")
        duplicate_files = asset.get("duplicate_files") or []
        tags = " ".join(str(t) for t in (asset.get("tags") or []))
        is_unknown = asset_type.lower().startswith("unknown") or asset_type.lower() in {"", "unknown"}
        media_haystack = " ".join([self._ccsf_name(asset), self._ccsf_file(asset), asset_type, tags]).lower()
        is_media = any(token in media_haystack for token in ("audio", "sound", "voice", "dialog", "dialogue", "text", "script", "logic", "movie", "video", "media"))
        if duplicate_files and not self.ccsf_show_duplicates.get():
            return False
        if is_unknown and not self.ccsf_show_unknown.get():
            return False
        if is_media and not self.ccsf_show_media_candidates.get():
            return False
        if self.ccsf_filter_type.get() != "All" and asset_type != self.ccsf_filter_type.get():
            return False
        if self.ccsf_filter_variant.get() != "All" and variant != self.ccsf_filter_variant.get():
            return False
        if self.ccsf_filter_readiness.get() != "All" and readiness != self.ccsf_filter_readiness.get():
            return False
        required_types = []
        if self.ccsf_filter_character_body.get():
            required_types.append("character/body")
        if self.ccsf_filter_character_color_variant.get():
            required_types.append("character/color variant")
        if self.ccsf_filter_environment_background.get():
            required_types.append("environment/background")
        if required_types and asset_type not in required_types:
            return False
        if self.ccsf_filter_has_animation.get() and int(counts.get("ANM", 0) or 0) <= 0:
            return False
        if self.ccsf_filter_has_texture_clt.get() and not (int(counts.get("TEX", 0) or 0) > 0 and int(counts.get("CLT", 0) or 0) > 0):
            return False
        query = self.ccsf_filter_search.get().strip().lower()
        if query:
            haystack = " ".join(str(asset.get(key) or "") for key in ("display_name", "name", "type", "variant", "readiness", "preferred_file", "relative_file", "file")).lower()
            haystack += " " + " ".join(str(x) for x in duplicate_files).lower()
            return all(token in haystack for token in query.split())
        return True

    def _refresh_ccsf_assets_tree(self) -> None:
        if not hasattr(self, "ccsf_assets_tree"):
            return
        self._update_ccsf_filter_choices()
        assets = self._ccsf_current_assets()
        self.ccsf_asset_by_iid = {}
        for iid in self.ccsf_assets_tree.get_children():
            self.ccsf_assets_tree.delete(iid)
        shown = 0
        for n, asset in enumerate(assets):
            if not self._ccsf_asset_matches_filters(asset):
                continue
            counts = self._ccsf_counts(asset)
            iid = f"ccsf_asset_{n}"
            values = (asset.get("type", ""), asset.get("variant") or "-", self._ccsf_file(asset), asset.get("size", 0), counts.get("MDL", 0), counts.get("TEX", 0), counts.get("CLT", 0), counts.get("MAT", 0), counts.get("ANM", 0), counts.get("OBJ", 0), asset.get("readiness", ""))
            self.ccsf_assets_tree.insert("", "end", iid=iid, text=self._ccsf_name(asset), values=values)
            self.ccsf_asset_by_iid[iid] = asset
            shown += 1
        total = len(assets)
        source = "logical" if self.ccsf_view_mode.get() != "physical" else "physical"
        self.ccsf_filter_summary.set(f"Showing {shown} of {total} {source} asset(s).")
        self._refresh_ccsf_survey_tabs()

    def _format_ccsf_asset_details(self, asset: dict, manifest: dict | None = None) -> str:
        counts = self._ccsf_counts(asset)
        report = getattr(self, "ccsf_structure_report", None) or {}
        typed_counts: dict[str, int] = {}
        if isinstance(report, dict):
            for rec in report.get("records") or []:
                name = str(rec.get("type_name") or f"0x{int(rec.get('masked_section_type', 0)):04X}")
                typed_counts[name] = typed_counts.get(name, 0) + 1
        duplicate_files = asset.get("duplicate_files") or []
        source_containers = asset.get("source_containers") or []
        tags = ccsf_asset_structure_tags(asset, counts)
        structure_notes = []
        if counts.get("HIT") is not None and _ccsf_int_count(counts.get("HIT")) > 0:
            structure_notes.append(f"HIT resources: {counts.get('HIT')}")
        if counts.get("DMY") is not None and _ccsf_int_count(counts.get("DMY")) > 0:
            structure_notes.append(f"DMY resources: {counts.get('DMY')}")
        if "field/stage candidate" in tags:
            structure_notes.append("field/stage candidate")
            structure_notes.append(CCSF_FIELD_ASSET_WARNING)
        lines = [
            "Selected Asset Details",
            "======================",
            f"Display name: {self._ccsf_name(asset)}",
            f"Type: {asset.get('type') or 'unknown'}",
            f"Variant: {asset.get('variant') or '-'}",
            f"Preferred file: {self._ccsf_file(asset)}",
            f"Readiness: {asset.get('readiness') or 'unknown'}",
            "Resource counts: " + (", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) if counts else "none"),
            "Structure header/version: " + (f"{(report.get('header') or {}).get('name') or '-'} / 0x{int((report.get('header') or {}).get('version') or 0):04X} ({(report.get('header') or {}).get('generation') or '-'})" if report else "not parsed"),
            "File count: " + (str(len(report.get("file_index") or [])) if report else "not parsed"),
            "Object count: " + (str(len(report.get("object_index") or [])) if report else "not parsed"),
            "Typed section counts: " + (", ".join(f"{k}: {v}" for k, v in sorted(typed_counts.items())) if typed_counts else "not parsed"),
            "Tags: " + (", ".join(str(value) for value in tags) if tags else "none"),
            "Structure notes: " + ("; ".join(structure_notes) if structure_notes else "none"),
            "",
            f"Duplicate files ({len(duplicate_files)}):",
            *(f"  - {value}" for value in duplicate_files),
            "",
            f"Source containers ({len(source_containers)}):",
            *(f"  - {value}" for value in source_containers),
        ]
        groups = asset.get("groups") or {}
        if groups:
            lines.extend(["", "Grouped resources:"])
            for key, values in groups.items():
                lines.append(f"{key} ({len(values)}):")
                lines.extend(f"  - {value}" for value in values)
        if manifest:
            pair_count = len(manifest.get("texture_clt_pairs") or [])
            renderer_status = manifest.get("renderer_status") or {}
            lines.extend([
                "",
                "Manifest summary:",
                f"  Asset name: {manifest.get('asset_name') or self._ccsf_name(asset)}",
                f"  Main model candidates: {len(manifest.get('main_model_candidates') or [])}",
                f"  Texture/CLT pairs: {pair_count}",
                f"  Animation candidates: {len(manifest.get('animation_candidates') or [])}",
                f"  Static preview: {manifest.get('can_attempt_static_preview')}",
                f"  Animated preview: {manifest.get('can_attempt_animated_preview')}",
                "  Renderer status: " + (", ".join(f"{k}={v}" for k, v in renderer_status.items()) if renderer_status else "none"),
            ])
        return "\n".join(lines) + "\n"

    def on_ccsf_asset_select(self, _event=None) -> None:
        asset = self._ccsf_selected_asset()
        self.ccsf_asset_selection_generation += 1
        self.ccsf_manifest_worker_token += 1
        generation = self.ccsf_asset_selection_generation
        bar = getattr(self, "ccsf_manifest_progress_bar", None)
        if bar is not None:
            try:
                bar.stop()
                bar.configure(mode="determinate", maximum=100.0)
            except tk.TclError:
                pass
        self.ccsf_manifest_progress.set(0.0)
        self.ccsf_manifest_progress_text.set("Idle")
        if not asset:
            self.ccsf_selected_asset_path.set("")
            return

        self.ccsf_selected_asset_path.set(str(self._ccsf_resolved_preferred_path(asset)))

        def render_selected_asset_details() -> None:
            if generation != self.ccsf_asset_selection_generation:
                return
            self.ccsf_manifest_payload = None
            self._replace_text(self.ccsf_assets_details, self._format_ccsf_asset_details(asset), readonly=True)
            self._replace_text(self.ccsf_assets_manifest, "Manifest is built only when Build Manifest is clicked.\n", readonly=True)

        self.after(CCSF_ASSET_SELECTION_DETAIL_DELAY_MS, render_selected_asset_details)

    def _ccsf_resolved_preferred_path(self, asset: dict) -> Path:
        label = self._ccsf_file(asset)
        path = Path(label).expanduser()
        if path.exists():
            return path
        folder = Path(self.ccsf_assets_folder.get().strip() or WORKSPACE / "extracted_ccs").expanduser()
        return folder / label

    def _ccsf_manifest_source(self, asset: dict) -> dict | Path:
        if asset.get("groups") or asset.get("file"):
            return asset
        return self._ccsf_resolved_preferred_path(asset)

    def _refresh_ccsf_survey_tabs(self) -> None:
        if not hasattr(self, "ccsf_audio_survey"):
            return
        assets = [a for a in self._ccsf_current_assets() if self._ccsf_asset_matches_filters(a)]
        def rows(title: str, tokens: tuple[str, ...]) -> str:
            out = [title, ""]
            matched = []
            for asset in assets:
                hay = " ".join([self._ccsf_name(asset), self._ccsf_file(asset), str(asset.get("type") or ""), " ".join(str(t) for t in asset.get("tags") or [])]).lower()
                if any(token in hay for token in tokens):
                    matched.append(asset)
            for asset in matched[:200]:
                counts = self._ccsf_counts(asset)
                active = ", ".join(f"{k}:{v}" for k, v in counts.items() if v) or "metadata"
                out.append(f"- {self._ccsf_name(asset)} [{asset.get('type') or 'unknown'}; {active}] -> {self._ccsf_file(asset)}")
            if not matched:
                out.append("No matching candidates in the current filtered view.")
            elif len(matched) > 200:
                out.append(f"... omitted {len(matched) - 200} additional candidates.")
            return "\n".join(out) + "\n"
        self._replace_text(self.ccsf_audio_survey, rows("Audio survey candidates", ("audio", "sound", "voice", "se", "bgm", "adx", "wav")), readonly=True)
        self._replace_text(self.ccsf_dialogue_survey, rows("Dialogue/text survey candidates", ("dialog", "dialogue", "text", "font", "msg", "string", "subtitle")), readonly=True)
        self._replace_text(self.ccsf_script_survey, rows("Script/logic survey candidates", ("script", "logic", "event", "quest", "ai", "lua", "bytecode")), readonly=True)


    def _console_mode_verbose(self) -> bool:
        return self._console_mode_name() in {"verbose", "debug"}

    def _console_mode_debug(self) -> bool:
        return self._console_mode_name() == "debug"

    def _console_mode_name(self) -> str:
        return str(getattr(self, "console_mode", tk.StringVar(value="Normal")).get()).strip().lower()

    def _sync_iso_ccsf_details_visibility(self) -> None:
        frame = getattr(self, "iso_ccsf_raw_frame", None)
        if frame is None:
            return
        if self._console_mode_debug():
            frame.grid()
        else:
            frame.grid_remove()

    def _open_report_name(self, name: str) -> None:
        path = self._default_ccsf_report_path(name)
        if not path.exists():
            return messagebox.showinfo("Report not found", f"Report not found:\n{path}")
        self._open_path_with_platform(path)

    def refresh_quick_report_locator(self) -> None:
        """Refresh Setup / Scan checklist rows without scanning or parsing reports."""
        if getattr(self, "setup_checklist_rows", None):
            rows = setup_checklist_rows(self._active_workspace_root(), self.iso_path.get().strip(), self.project_root.get().strip())
            ok_count = 0
            for row in rows:
                ok_count += 1 if row["ok"] else 0
                var = self.setup_checklist_rows.get(str(row["key"]))
                if var is not None:
                    icon = "✅" if row["ok"] else "❌"
                    var.set(f"{icon} {row['path'] or 'not set'}")
            self.quick_report_locator_status.set(f"Checklist ready: {ok_count}/{len(rows)} item(s) complete.")
            return

        """Locate expected workflow reports without scanning or parsing them."""
        reports_dir = self._active_workspace_root() / "reports"
        found = 0
        total = len(getattr(self, "quick_report_locator_rows", {}))
        for name, var in getattr(self, "quick_report_locator_rows", {}).items():
            path = reports_dir / name
            if path.exists():
                found += 1
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                var.set(f"exists ({size:,} bytes)")
            else:
                var.set("missing")
        self.quick_report_locator_status.set(f"Located {found}/{total} expected report(s) in {reports_dir}")

    def _start_setup_indeterminate_progress(self, attr: str, text_var: tk.StringVar, message: str) -> None:
        bar = getattr(self, attr, None)
        text_var.set(message)
        if bar is not None:
            try:
                bar.configure(mode="indeterminate")
                bar.start(12)
            except tk.TclError:
                pass

    def _stop_setup_indeterminate_progress(self, attr: str, progress_var: tk.DoubleVar, text_var: tk.StringVar, ok: bool) -> None:
        bar = getattr(self, attr, None)
        if bar is not None:
            try:
                bar.stop()
                bar.configure(mode="determinate")
            except tk.TclError:
                pass
        progress_var.set(100.0 if ok else 0.0)
        text_var.set("Complete" if ok else "Failed")

    def run_setup_asset_library_refresh(self) -> None:
        """Kick off the existing threaded CCSF asset scan from the setup card."""
        if self.ccsf_scan_active:
            self.setup_asset_library_status.set("Asset library scan is already running.")
            return
        self.ccsf_assets_folder.set(str(self._iso_ccsf_workspace() / "extracted_ccs"))
        self.setup_asset_library_status.set("Building asset library from extracted_ccs.")
        self._start_setup_indeterminate_progress("setup_asset_library_progress_bar", self.setup_asset_library_progress_text, "Running")
        self.scan_ccsf_assets_folder()
        self.after(250, self._poll_setup_asset_library_refresh)

    def _poll_setup_asset_library_refresh(self) -> None:
        if self.ccsf_scan_active:
            self.setup_asset_library_status.set(self.ccsf_filter_summary.get())
            self.after(250, self._poll_setup_asset_library_refresh)
            return
        ok = (self._active_workspace_root() / "reports" / "asset_library.json").exists()
        self._stop_setup_indeterminate_progress("setup_asset_library_progress_bar", self.setup_asset_library_progress, self.setup_asset_library_progress_text, ok)
        self.setup_asset_library_status.set("Asset library refreshed." if ok else "Asset library refresh did not produce asset_library.json.")
        self.refresh_quick_report_locator()
        if ok:
            self.ccsf_viewer_asset_library_path.set(str(self._active_workspace_root() / "reports" / "asset_library.json"))
            self.ccsf_viewer_extracted_folder.set(str(self._active_workspace_root() / "extracted_ccs"))
            self.load_ccsf_viewer_asset_library(silent=True)



    def _disc_preparation_summary_paths(self, workspace: Path | str | None = None) -> tuple[Path, Path]:
        reports = Path(workspace or self._active_workspace_root()) / "reports"
        return reports / "disc_preparation_summary.json", reports / "disc_preparation_summary.txt"

    def _preparation_state_path(self, workspace: Path | str | None = None) -> Path:
        return Path(workspace or self._active_workspace_root()) / "reports" / "disc_preparation_cache_state.json"

    def _load_preparation_state(self, workspace: Path | str | None = None) -> dict:
        path = self._preparation_state_path(workspace)
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_preparation_state(self, state: dict, workspace: Path | str | None = None) -> None:
        path = self._preparation_state_path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, state)

    def _source_identity(self, path: Path | str | None) -> dict:
        if not path:
            return {}
        target = Path(path).expanduser()
        if not target.is_file():
            return {"path": str(target), "exists": False}
        stat = target.stat()
        digest = hashlib.sha256()
        with target.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"path": str(target.resolve()), "exists": True, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest.hexdigest()}

    def _ccsf_extracted_state(self, workspace: Path) -> dict:
        report = workspace / "reports" / "iso_ccsf_extraction_index.json"
        if report.is_file():
            return self._source_identity(report)
        root = workspace / "extracted_ccs"
        if not root.is_dir():
            return {"exists": False}
        rows = []
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            try:
                st = path.stat()
            except OSError:
                continue
            rows.append(f"{path.relative_to(root).as_posix()}:{st.st_size}:{st.st_mtime_ns}")
        return {"exists": True, "digest": hashlib.sha256("\n".join(rows).encode()).hexdigest(), "files": len(rows)}

    def _known_media_source_state(self, workspace: Path) -> dict:
        extraction_rows: dict[str, dict] = {}
        for report_path in (
            workspace / "reports" / "iso_media_extraction.json",
            workspace / "media_pipeline" / "reports" / "iso_media_extraction.json",
        ):
            if not report_path.is_file():
                continue
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for row in (payload.get("files") if isinstance(payload, dict) else payload) or []:
                if isinstance(row, dict):
                    key = str(row.get("source_iso_path") or row.get("iso_path") or "").replace("\\", "/").upper()
                    if key:
                        extraction_rows[key] = row
        rows = {}
        for internal in KNOWN_MEDIA_TARGETS:
            path = workspace / "media_pipeline" / "extracted" / "top_level" / Path(internal.lower())
            row = extraction_rows.get(internal.replace("\\", "/").upper(), {})
            rows[internal] = {
                "iso_identity": self._source_identity(self.iso_path.get().strip()),
                "internal_path": internal,
                "lba": row.get("lba"),
                "size": row.get("size"),
                "cache_key": row.get("cache_key"),
                "source_hash": self._source_identity(path),
            }
        return rows

    def _write_disc_preparation_summary(self, *, status: str | None = None) -> None:
        workspace = self._active_workspace_root()
        json_path, txt_path = self._disc_preparation_summary_paths(workspace)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        steps = []
        step_names = list(full_disc_preparation_steps())
        for step in deep_disc_discovery_steps():
            if step not in step_names and step in self.full_disc_step_vars:
                step_names.append(step)
        for step in step_names:
            steps.append({"name": step, "state": self.full_disc_step_vars.get(step, tk.StringVar(value="Skipped")).get()})
        payload = {
            "generated_at": _utc_timestamp(),
            "status": status or ("cancelled" if self.full_disc_preparation_cancel_requested else "complete"),
            "workspace": str(workspace),
            "steps": steps,
            "results": list(getattr(self, "full_disc_preparation_results", []) or []),
        }
        atomic_write_json(json_path, payload)
        lines = ["Disc preparation summary", "========================", "", f"Status: {payload['status']}", f"Workspace: {workspace}", ""]
        lines.extend(f"- {row['name']}: {row['state']}" for row in steps)
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def cancel_full_disc_preparation(self) -> None:
        """Request cancellation for RUN ALL and stop any active child task."""
        self.full_disc_preparation_cancel_requested = True
        self.full_disc_preparation_status.set("Cancel All requested; current step will stop before the next queued step.")
        self.cancel_active_task()
        self.cancel_iso_ccsf_job()
        for step, var in self.full_disc_step_vars.items():
            if var.get() == "Queued":
                var.set("Cancelled")


    def _resolve_extracted_snddata_path(self, workspace: Path | str | None = None) -> Path | None:
        """Return the extracted DATA/SNDDATA.BIN path if one is available."""
        workspace_path = Path(workspace or self._active_workspace_root())

        for report_path in (
            workspace_path / "reports" / "iso_media_extraction.json",
            workspace_path / "media_pipeline" / "reports" / "iso_media_extraction.json",
        ):
            if not report_path.is_file():
                continue
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows = payload.get("files") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                source = str(row.get("source_iso_path") or "").replace("\\", "/").lower()
                if source != "data/snddata.bin":
                    continue
                output = row.get("output_path") or row.get("extracted_path") or row.get("raw_path")
                if not output:
                    continue
                path = Path(str(output)).expanduser()
                if not path.is_absolute():
                    path = workspace_path / path
                if path.is_file():
                    return path

        fallback = workspace_path / "media_pipeline" / "extracted" / "top_level" / "data" / "snddata.bin"
        if fallback.is_file():
            return fallback

        # Future GUI versions may expose a manually selected SNDDATA path.  Accept
        # common attribute names without requiring the state to exist today.
        for attr in ("snddata_path", "manual_snddata_path", "audio_music_snddata_path"):
            value = getattr(self, attr, None)
            if hasattr(value, "get"):
                value = value.get()
            if value:
                path = Path(str(value)).expanduser()
                if path.is_file():
                    return path
        return None

    def _full_disc_step_command(self, step: str, workspace: Path) -> list[str] | None:
        iso = self.iso_path.get().strip()
        if step == "Survey ISO Assets":
            return [PY, str(TOOLS / "iso_asset_survey.py"), iso, str(workspace)]
        if step == "Full Inventory Refresh":
            return self._build_audio_media_pipeline_command(iso, workspace, "inventory", rescan_inventory=True, deep_discovery=True)
        if step == "Extract Media Candidates":
            return self._build_audio_media_pipeline_command(iso, workspace, "extract", deep_discovery=True)
        if step == "Scan / Decode Audio":
            return self._build_audio_media_pipeline_command(iso, workspace, "decode")
        if step == "Extract Known Media Targets":
            return self._build_audio_media_pipeline_command(iso, workspace, "extract", focused_known_targets=True)
        if step == "Decode Known EFF Sound Bank":
            return [PY, str(TOOLS / "focused_audio_steps.py"), "decode-eff-bank", "--workspace", str(workspace)]
        if step == "Reuse BGM / FOOD Maps":
            return [PY, str(TOOLS / "focused_audio_steps.py"), "map-bgm-food", "--workspace", str(workspace)]
        if step == "Analyze SNDDATA Music":
            snddata = self._resolve_extracted_snddata_path(workspace)
            return [PY, str(TOOLS / "snddata_pipeline.py"), str(snddata), "--workspace", str(workspace)] if snddata else None
        if step == "Focused SNDDATA Structural Analysis":
            snddata = self._resolve_extracted_snddata_path(workspace)
            return [PY, str(TOOLS / "snddata_pipeline.py"), str(snddata), "--workspace", str(workspace)] if snddata else None
        return None

    def _run_full_disc_step(self, index: int, steps: tuple[str, ...], workspace: Path) -> None:
        if index >= len(steps) or self.full_disc_preparation_cancel_requested:
            if self.full_disc_preparation_cancel_requested:
                for step in steps[index:]:
                    self.full_disc_step_vars[step].set("Cancelled")
                self.full_disc_preparation_status.set("Full Disc Preparation cancelled.")
                self._write_disc_preparation_summary(status="cancelled")
            else:
                self.full_disc_preparation_status.set("Full Disc Preparation complete.")
                self._write_disc_preparation_summary(status="complete")
            self.full_disc_preparation_active = False
            self.refresh_quick_report_locator()
            return
        step = steps[index]
        var = self.full_disc_step_vars[step]
        var.set("Running")
        self.full_disc_preparation_status.set(f"Running: {step}")

        def finish(state: str, details: str = "") -> None:
            var.set(state)
            self.full_disc_preparation_results.append({"name": step, "state": state, "details": details})
            self._write_disc_preparation_summary(status="running")
            self.after(50, lambda: self._run_full_disc_step(index + 1, steps, workspace))

        if step == "Workspace Check":
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "reports").mkdir(parents=True, exist_ok=True)
            if not self.iso_path.get().strip():
                return finish("Failed", "Missing ISO path")
            return finish("Reused" if (workspace / "reports").is_dir() else "Updated", "Workspace and reports folder are available.")
        if step in {"Extract CCSF bundles", "Reuse / Extract CCSF Library"}:
            if not self.iso_path.get().strip():
                return finish("Skipped", "Missing ISO path")
            state = self._load_preparation_state(workspace)
            before = self._ccsf_extracted_state(workspace)
            self.extract_iso_ccsf_library()
            def poll_extract() -> None:
                if self.full_disc_preparation_cancel_requested:
                    return finish("Cancelled", "Cancel All requested")
                if getattr(self, "iso_ccsf_job_active", False):
                    self.after(250, poll_extract)
                else:
                    after = self._ccsf_extracted_state(workspace)
                    state["ccsf_extracted_state"] = after
                    self._save_preparation_state(state, workspace)
                    if not after.get("exists"):
                        finish("Partial", "CCSF extraction did not produce the expected index.")
                    elif before == after:
                        finish("Reused", "Existing CCSF extraction state was unchanged.")
                    else:
                        finish("Extracted", "CCSF extraction state changed.")
            return self.after(250, poll_extract)
        if step in {"Build / Refresh Asset Library", "Rebuild Asset Library if CCSF Changed"}:
            state = self._load_preparation_state(workspace)
            ccsf_state = self._ccsf_extracted_state(workspace)
            if step == "Rebuild Asset Library if CCSF Changed" and state.get("asset_library_ccsf_state") == ccsf_state and (workspace / "reports" / "asset_library.json").exists():
                return finish("Reused", "Asset library cache key matched ISO identity/internal path/size/LBA state from the CCSF extraction.")
            self.ccsf_assets_folder.set(str(workspace / "extracted_ccs"))
            self.scan_ccsf_assets_folder()
            def poll_library() -> None:
                if self.full_disc_preparation_cancel_requested:
                    return finish("Cancelled", "Cancel All requested")
                if getattr(self, "ccsf_scan_active", False):
                    self.after(250, poll_library)
                else:
                    if (workspace / "reports" / "asset_library.json").exists():
                        state["asset_library_ccsf_state"] = ccsf_state
                        self._save_preparation_state(state, workspace)
                        finish("Updated", "Asset library refresh finished.")
                    else:
                        finish("Partial", "Asset library refresh did not produce asset_library.json.")
            return self.after(250, poll_library)
        if step == "Decode / Prepare Images":
            return finish("Skipped", "No dedicated image batch decoder is configured; texture previews use generated candidates.")
        if step in {"Refresh Asset Library for Viewer", "Refresh 3D and Audio Views"}:
            self.load_ccsf_viewer_asset_library(silent=True)
            self.refresh_audio_reports()
            self.refresh_project_tree()
            self.refresh_quick_report_locator()
            return finish("Updated" if (workspace / "reports" / "asset_library.json").exists() else "Partial", "3D and Audio views refreshed.")
        if step == "Refresh Reports / Setup Checklist":
            self.refresh_project_tree(); self.refresh_quick_report_locator()
            return finish("Updated", "Reports and checklist refreshed.")
        cmd = self._full_disc_step_command(step, workspace)
        if not cmd:
            if step == "Analyze SNDDATA Music":
                return finish("Partial", "DATA/SNDDATA.BIN has not been extracted.")
            return finish("Skipped", "No command configured.")
        def done(rc: int) -> None:
            if self.full_disc_preparation_cancel_requested or rc == -15:
                finish("Cancelled", f"exit code {rc}")
            elif rc == 0:
                if step in {"Analyze SNDDATA Music", "Focused SNDDATA Structural Analysis"}:
                    self.refresh_audio_music_system_reports()
                if step == "Extract Known Media Targets":
                    state = self._load_preparation_state(workspace)
                    media_state = self._known_media_source_state(workspace)
                    previous = state.get("known_media_source_state")
                    state["known_media_source_state"] = media_state
                    self._save_preparation_state(state, workspace)
                    finish("Reused" if previous == media_state else "Extracted", "Known media targets prepared with source-hash cache state.")
                elif step == "Decode Known EFF Sound Bank":
                    finish("Decoded", "Known EFF HD/BD bank decode attempted.")
                elif step == "Reuse BGM / FOOD Maps":
                    finish("Reused", "BGM/FOOD maps reused when extracted source identity was unchanged.")
                elif step == "Focused SNDDATA Structural Analysis":
                    finish("Updated", "Focused SNDDATA structural reports refreshed.")
                else:
                    finish("Updated", "exit code 0")
            else:
                finish("Failed", f"exit code {rc}")
        if not self._run_task(cmd, on_done=done, label=f"disc preparation: {step}"):
            finish("Failed", "Could not start task")

    def run_full_disc_preparation(self) -> None:
        """Run focused known-target disc preparation steps sequentially."""
        if self.full_disc_preparation_active or self.runner.is_busy() or self.ccsf_scan_active or self.audio_pipeline_job_active or self.iso_ccsf_job_active:
            return messagebox.showwarning("Busy", "A whole-disc scan or preparation task is already running. Cancel it before starting RUN ALL.")
        if not messagebox.askokcancel("RUN ALL", RUN_ALL_CONFIRMATION_TEXT):
            return
        workspace = self._ensure_research_workspace()
        self.full_disc_preparation_active = True
        self.full_disc_preparation_cancel_requested = False
        self.full_disc_preparation_results = []
        for step in full_disc_preparation_steps():
            self.full_disc_step_vars[step].set("Queued")
        self._write_disc_preparation_summary(status="queued")
        self._run_full_disc_step(0, full_disc_preparation_steps(), workspace)

    def run_deep_disc_discovery(self) -> None:
        """Run explicit full-disc discovery steps that intentionally scan broadly."""
        if self.full_disc_preparation_active or self.runner.is_busy() or self.ccsf_scan_active or self.audio_pipeline_job_active or self.iso_ccsf_job_active:
            return messagebox.showwarning("Busy", "A whole-disc scan or preparation task is already running. Cancel it before starting DEEP DISC DISCOVERY.")
        if not messagebox.askokcancel("DEEP DISC DISCOVERY", DEEP_DISC_DISCOVERY_CONFIRMATION_TEXT):
            return
        workspace = self._ensure_research_workspace()
        self.full_disc_preparation_active = True
        self.full_disc_preparation_cancel_requested = False
        self.full_disc_preparation_results = []
        for step in full_disc_preparation_steps():
            self.full_disc_step_vars[step].set("Skipped")
        for step in deep_disc_discovery_steps():
            self.full_disc_step_vars.setdefault(step, tk.StringVar(value="Queued")).set("Queued")
        self._write_disc_preparation_summary(status="queued_deep_discovery")
        self._run_full_disc_step(0, deep_disc_discovery_steps(), workspace)

    def run_setup_scan_decode_audio(self) -> None:
        """Run setup action for Scan / Decode Audio."""
        self.run_setup_media_pipeline("decode")

    def run_setup_analyze_snddata_music(self) -> None:
        """Run setup action for Analyze SNDDATA Music and open resulting reports."""
        workspace = self._ensure_research_workspace()
        candidate = self._resolve_extracted_snddata_path(workspace)
        if not candidate:
            message = "DATA/SNDDATA.BIN has not been extracted."
            self.setup_media_pipeline_status.set(f"SNDDATA Music analysis failed: {message}")
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set(message)
            return messagebox.showerror("Missing SNDDATA", message)
        cmd = [PY, str(TOOLS / "snddata_pipeline.py"), str(candidate), "--workspace", str(workspace)]
        if getattr(self, "audio_pipeline_job_active", False) or self.runner.is_busy():
            return messagebox.showwarning("Busy", "An audio task is already running. Cancel it before starting SNDDATA analysis.")
        self._set_audio_busy_state(True, "Analyze SNDDATA Music", indeterminate=True)
        self.setup_media_pipeline_status.set("Analyzing SNDDATA Music.")
        def done(rc: int) -> None:
            self._set_audio_busy_state(False)
            self.setup_media_pipeline_status.set("SNDDATA Music analysis complete." if rc == 0 else "SNDDATA Music analysis failed; see console.")
            if rc == 0:
                self.refresh_audio_music_system_reports()
            self.refresh_quick_report_locator()
        if not self._run_task(cmd, on_done=done, label="Analyze SNDDATA Music"):
            self._set_audio_busy_state(False)

    def _build_audio_media_pipeline_command(self, iso: str, workspace: Path | str, mode: str, progress_jsonl: Path | None = None, *, rescan_inventory: bool = False, focused_known_targets: bool = False, deep_discovery: bool = False) -> list[str]:
        cmd = [PY, str(ROOT / "fragmenter.py"), "media-pipeline-iso", iso, "--workspace", str(workspace), "--mode", mode]
        if deep_discovery and mode in {"inventory", "extract", "all"}:
            cmd.append("--scan-all-bytes")
        if mode in {"extract", "all"}:
            cmd.extend(["--extract-bucket", "audio_or_music_candidate"])
        if mode in {"decode", "all"}:
            cmd.append("--decode-audio")
        if focused_known_targets and mode in {"inventory", "extract", "all"}:
            cmd.append("--known-media-targets")
            cmd.append("--hash")
        elif mode in {"extract", "all"}:
            cmd.append("--hash")
        if progress_jsonl is not None:
            cmd.extend(["--progress-jsonl", str(progress_jsonl)])
        if rescan_inventory:
            cmd.append("--rescan-inventory")
        return cmd

    def _set_audio_pipeline_phase(self, phase: str, percent: float | None = None) -> None:
        phase_percents = {
            "scanning ISO": 8.0,
            "inventory complete": 22.0,
            "extracting candidates": 34.0,
            "pairing HD/BD banks": 48.0,
            "inspecting audio containers": 58.0,
            "parsing SCEI banks": 68.0,
            "decoding bank streams": 78.0,
            "writing reports": 92.0,
            "complete": 100.0,
            "failed": 0.0,
            "cancelled": 0.0,
        }
        value = phase_percents.get(phase, 0.0) if percent is None else percent
        self.audio_pipeline_progress.set(value)
        self.audio_pipeline_status.set(f"Audio pipeline: {phase}.")
        self.audio_pipeline_progress_text.set(self._audio_pipeline_counts_text(prefix=f"{value:.0f}%"))

    def _audio_pipeline_phase_from_line(self, line: str) -> str | None:
        text = line.lower()
        phase_markers = (
            ("scanning ISO", ("scan", "iso")),
            ("inventory complete", ("inventory", "complete")),
            ("extracting candidates", ("extract", "candidate")),
            ("pairing HD/BD banks", ("pair", "bank")),
            ("inspecting audio containers", ("inspect", "audio")),
            ("parsing SCEI banks", ("scei", "bank")),
            ("decoding bank streams", ("decod", "stream")),
            ("writing reports", ("writ", "report")),
        )
        for phase, tokens in phase_markers:
            if all(token in text for token in tokens):
                return phase
        return None

    def _audio_pipeline_counts_text(self, *, prefix: str = "") -> str:
        event = getattr(self, "audio_pipeline_latest_event", {}) or {}
        event_counts = []
        for label, key in (
            ("candidates", "candidates_found"),
            ("extracted", "extracted_count"),
            ("banks", "banks_found"),
            ("streams", "streams_found"),
            ("WAV", "decoded_wavs"),
            ("raw", "raw_pending"),
            ("fail", "failures"),
        ):
            if key in event:
                event_counts.append(f"{label}: {event[key]}")
        if event_counts:
            return f"{prefix} · {' | '.join(event_counts)}" if prefix else " | ".join(event_counts)
        buckets = (
            ("WAV", getattr(self, "audio_wav_payloads", {})),
            ("raw", getattr(self, "audio_raw_payloads", {})),
            ("warn", getattr(self, "audio_failed_payloads", {})),
        )
        counts = " | ".join(f"{label}: {len(payloads)}" for label, payloads in buckets)
        return f"{prefix} · {counts}" if prefix else counts

    def _audio_pipeline_progress_path(self, workspace: Path | str, mode: str) -> Path:
        return Path(workspace) / "tmp" / f"audio_pipeline_{mode}_progress.jsonl"

    def _coalesced_audio_progress_events(self, progress_path: Path) -> list[dict]:
        offset = int(getattr(self, "audio_pipeline_progress_offset", 0) or 0)
        if not progress_path.exists():
            return []
        events: list[dict] = []
        with progress_path.open("r", encoding="utf-8") as fh:
            fh.seek(offset)
            for line in fh:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    events.append(payload)
            self.audio_pipeline_progress_offset = fh.tell()
        if len(events) <= 8:
            return events
        return [events[0], *events[-7:]]

    def _audio_pipeline_phase_from_event(self, event: dict) -> str:
        stage = str(event.get("stage") or "").replace("_", " ")
        stage_map = {
            "inventory start": "scanning ISO",
            "inventory scan": "scanning ISO",
            "inventory complete": "inventory complete",
            "extract start": "extracting candidates",
            "extract candidate": "extracting candidates",
            "extract complete": "extracting candidates",
            "audio decode start": "inspecting audio containers",
            "audio decode candidate": "decoding bank streams",
            "audio decode candidate complete": "decoding bank streams",
            "audio decode complete": "writing reports",
            "reports start": "writing reports",
            "reports complete": "writing reports",
            "complete": "complete",
        }
        return stage_map.get(stage, stage or "running")

    def _apply_audio_pipeline_event(self, event: dict) -> None:
        self.audio_pipeline_latest_event = event
        total = int(event.get("total") or 0)
        current = int(event.get("current_index") or 0)
        stage = str(event.get("stage") or "")
        percent = None
        if total > 0 and current > 0:
            stage_floor = 8.0 if stage.startswith("inventory") else 34.0 if stage.startswith("extract") else 58.0 if stage.startswith("audio_decode") else 90.0
            stage_span = 18.0 if stage.startswith("inventory") else 20.0 if stage.startswith("extract") else 30.0 if stage.startswith("audio_decode") else 8.0
            percent = min(99.0, stage_floor + (min(current, total) / total) * stage_span)
        elif stage == "complete":
            percent = 100.0
        self._set_audio_pipeline_phase(self._audio_pipeline_phase_from_event(event), percent)
        current_path = str(event.get("current_path") or "")
        if current_path:
            self.audio_pipeline_status.set(f"{self.audio_pipeline_status.get()} {Path(current_path).name}")

    def _poll_audio_pipeline_progress(self, progress_path: Path) -> None:
        if not getattr(self, "audio_pipeline_job_active", False):
            return
        for event in self._coalesced_audio_progress_events(progress_path):
            self._apply_audio_pipeline_event(event)
        self.after(200, lambda p=progress_path: self._poll_audio_pipeline_progress(p))

    def _set_audio_busy_state(self, active: bool, action: str = "Idle", *, indeterminate: bool = False, progress: float | None = None) -> None:
        self.audio_pipeline_job_active = active
        self.audio_busy_action.set(action if active else "Idle")
        if progress is not None:
            self.audio_pipeline_progress.set(progress)
        bar = getattr(self, "audio_pipeline_progress_bar", None)
        if bar is not None:
            try:
                bar.stop()
                bar.configure(mode="indeterminate" if indeterminate and active else "determinate")
                if indeterminate and active:
                    bar.start(80)
            except tk.TclError:
                pass
        state = "disabled" if active else "normal"
        for button in getattr(self, "audio_action_buttons", []):
            try:
                button.configure(state=state)
            except tk.TclError:
                pass
        cancel_button = getattr(self, "audio_cancel_button", None)
        if cancel_button is not None:
            try:
                cancel_button.configure(state="normal" if active else "disabled")
            except tk.TclError:
                pass
        if active:
            self.audio_busy_cancel.clear()

    def _run_audio_worker(self, action: str, work, done, *, progress_text: str = "Working…") -> bool:
        runner = self.__dict__.get("runner")
        runner_busy = bool(runner and runner.is_busy())
        if getattr(self, "audio_pipeline_job_active", False) or runner_busy:
            messagebox.showwarning("Busy", "An audio task is already running. Cancel it before starting another audio action.")
            return False
        self._set_audio_busy_state(True, action, indeterminate=True)
        self.audio_pipeline_status.set(action)
        self.audio_pipeline_progress_text.set(progress_text)

        def worker() -> None:
            try:
                result = work(self.audio_busy_cancel)
                self.after(0, lambda: done(result, None))
            except Exception as exc:
                self.after(0, lambda e=exc: done(None, e))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _finish_audio_worker(self, status: str, *, refresh: str | None = None) -> None:
        self._set_audio_busy_state(False)
        self.audio_pipeline_status.set(status)
        if refresh == "reports":
            self.refresh_project_tree()
            self.refresh_quick_report_locator()
        self.audio_pipeline_progress_text.set(self._audio_pipeline_counts_text())

    def _run_audio_media_pipeline_mode(self, mode: str, *, rescan_inventory: bool = False, focused_known_targets: bool = False, action_label: str | None = None) -> None:
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing ISO", "Choose an ISO first.")
        workspace = self._ensure_research_workspace()
        mode_labels = {"inventory": "Inventory", "extract": "Extract audio", "decode": "Decode audio", "all": "Run audio pipeline"}
        if action_label:
            mode_labels = {**mode_labels, mode: action_label}
        progress_jsonl = self._audio_pipeline_progress_path(workspace, mode)
        self.audio_pipeline_progress_offset = 0
        self.audio_pipeline_latest_event = {}
        try:
            progress_jsonl.parent.mkdir(parents=True, exist_ok=True)
            progress_jsonl.write_text("", encoding="utf-8")
        except OSError:
            pass
        cmd = self._build_audio_media_pipeline_command(iso, workspace, mode, progress_jsonl, rescan_inventory=rescan_inventory, focused_known_targets=focused_known_targets)
        start_phase = "decoding bank streams" if mode == "decode" else "scanning ISO"
        if getattr(self, "audio_pipeline_job_active", False) or self.runner.is_busy():
            return messagebox.showwarning("Busy", "An audio task is already running. Cancel it before starting another audio action.")
        self._set_audio_busy_state(True, mode_labels.get(mode, mode), indeterminate=False, progress=0.0)
        self.audio_pipeline_status.set(f"{mode_labels.get(mode, mode)} running.")
        self._set_audio_pipeline_phase(start_phase)
        self._poll_audio_pipeline_progress(progress_jsonl)
        if getattr(self, "audio_pipeline_progress_bar", None) is not None:
            try:
                self.audio_pipeline_progress_bar.stop()
                self.audio_pipeline_progress_bar.configure(mode="determinate")
            except tk.TclError:
                pass

        def _line(line: str) -> None:
            phase = self._audio_pipeline_phase_from_line(line)
            if phase:
                self._set_audio_pipeline_phase(phase)

        def _done(rc: int) -> None:
            ok = rc == 0
            self._set_audio_busy_state(False)
            if getattr(self, "audio_pipeline_progress_bar", None) is not None:
                try:
                    self.audio_pipeline_progress_bar.stop()
                    self.audio_pipeline_progress_bar.configure(mode="determinate")
                except tk.TclError:
                    pass
            if rc == -15:
                self._set_audio_pipeline_phase("cancelled")
            elif ok:
                for event in self._coalesced_audio_progress_events(progress_jsonl):
                    self._apply_audio_pipeline_event(event)
                self.audio_pipeline_progress.set(100.0)
                self.audio_pipeline_status.set("Audio pipeline complete; refreshing affected Audio reports.")
                self.audio_pipeline_progress_text.set(self._audio_pipeline_counts_text(prefix="100%"))
                self.refresh_audio_reports()
            else:
                self._set_audio_pipeline_phase("failed")
                self.refresh_audio_reports()
            self.iso_status.set(self.audio_pipeline_status.get())

        if not self._run_task(cmd, on_done=_done, on_line=_line, label=f"audio media pipeline {mode}"):
            self._set_audio_busy_state(False)
            if getattr(self, "audio_pipeline_progress_bar", None) is not None:
                try:
                    self.audio_pipeline_progress_bar.stop()
                    self.audio_pipeline_progress_bar.configure(mode="determinate")
                except tk.TclError:
                    pass
            self._set_audio_pipeline_phase("failed")

    def run_audio_media_inventory(self) -> None:
        self._run_audio_media_pipeline_mode("inventory")

    def run_audio_candidate_extract(self) -> None:
        self._run_audio_media_pipeline_mode("extract")

    def rescan_audio_inventory(self) -> None:
        self._run_audio_media_pipeline_mode("inventory", rescan_inventory=True)

    def run_audio_decode(self) -> None:
        self._run_audio_media_pipeline_mode("decode")

    def prepare_known_audio(self) -> None:
        self._run_audio_media_pipeline_mode("extract", focused_known_targets=True, action_label="Prepare Known Audio")

    def run_audio_pipeline_all(self) -> None:
        self._run_audio_media_pipeline_mode("all", action_label="Run Audio Pipeline")

    def run_setup_media_pipeline(self, mode: str) -> None:
        # Delegates to the audio command builder for "media-pipeline-iso" and self._run_task(cmd).
        self._run_audio_media_pipeline_mode(mode)

    def open_setup_media_output_folder(self) -> None:
        self._open_folder_path(self._active_workspace_root() / "media_pipeline")

    def _audio_decoded_wav_folder(self) -> Path:
        return self._active_workspace_root() / "media_pipeline" / "decoded" / "audio" / "wav"

    def _audio_raw_folder(self) -> Path:
        return self._active_workspace_root() / "media_pipeline" / "decoded" / "audio" / "raw"

    def open_audio_decoded_wav_folder(self) -> None:
        self._open_folder_path(self._audio_decoded_wav_folder())

    def open_audio_raw_folder(self) -> None:
        candidates = [self._audio_raw_folder(), self._active_workspace_root() / "media_pipeline" / "extracted" / "embedded" / "audio"]
        folder = next((path for path in candidates if path.exists()), candidates[0])
        self._open_folder_path(folder)

    def refresh_audio_wav_list(self) -> None:
        self.refresh_audio_candidate_tables()
        self.refresh_audio_music_system_reports()

    def _audio_wav_metadata(self, path: Path) -> dict[str, str]:
        try:
            with wave.open(str(path), "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate()
                duration = frames / rate if rate else 0
                return {
                    "duration": f"{duration:.2f}s",
                    "sample_rate": f"{rate} Hz",
                    "channels": str(handle.getnchannels()),
                    "sample_width": f"{handle.getsampwidth() * 8}-bit",
                }
        except Exception as exc:
            return {"duration": "—", "sample_rate": "—", "channels": "—", "sample_width": f"unreadable: {exc}"}

    def _refresh_audio_raw_and_failed_lists(self) -> None:
        # Kept for older call sites; the unified table refresh now populates all
        # Audio Workbench buckets from reports and filesystem outputs together.
        self.refresh_audio_candidate_tables()

    def _audio_decode_warning_rows(self, report: Path) -> list[dict[str, str]]:
        if not report.exists():
            return []
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
        except Exception as exc:
            return [{"name": report.name, "format": "JSON", "message": f"Could not read report: {exc}", "path": str(report)}]
        rows = payload.get("entries", payload if isinstance(payload, list) else [])
        out = []
        for entry in rows if isinstance(rows, list) else []:
            if not isinstance(entry, dict):
                continue
            message = entry.get("error") or entry.get("warning") or entry.get("decode_error") or entry.get("status")
            status = str(entry.get("status", "")).lower()
            if message and any(token in status + str(message).lower() for token in ("fail", "warn", "error")):
                path_text = str(entry.get("source_path") or entry.get("path") or entry.get("raw_path") or "")
                out.append({
                    "name": Path(path_text).name or str(entry.get("name") or "audio entry"),
                    "format": str(entry.get("detected_format") or entry.get("format") or "unknown"),
                    "message": str(message),
                    "path": path_text,
                })
        return out

    def _selected_audio_wav_path(self) -> Path | None:
        preferred = None
        notebook = getattr(self, "audio_candidates_notebook", None)
        if notebook is not None:
            try:
                selected_tab = notebook.nametowidget(notebook.select())
            except tk.TclError:
                selected_tab = None
            for tree in (getattr(self, "audio_snddata_samples_tree", None), getattr(self, "audio_wav_tree", None), getattr(self, "audio_raw_tree", None), getattr(self, "audio_failed_tree", None)):
                if tree is not None and getattr(tree, "master", None) is selected_tab:
                    preferred = tree
                    break
        payload = self._selected_audio_payload(preferred)
        if isinstance(payload, dict):
            path = payload.get("payload_path") or payload.get("output_path")
            return Path(str(path)) if path else None
        return None

    def _audio_playback_capability_text(self) -> str:
        engine = self.audio_playback_engine
        caps = engine.capabilities
        lines = [f"Playback backend: {engine.backend_name}"]
        lines.append("Pause: available" if engine.supports_pause else "Pause: unavailable")
        if not caps.get("gain"):
            lines.append("Gain: unavailable")
        if not caps.get("position"):
            lines.append("Position: unavailable")
        if not caps.get("seek"):
            lines.append("Seek: unavailable")
        return "\n".join(lines)

    def preview_selected_audio_wav(self, _event: object | None = None) -> None:
        path = self._selected_audio_wav_path()
        if not path or not path.is_file() or path.suffix.lower() != ".wav":
            return messagebox.showinfo("Audio preview", "Select an existing decoded .wav file first.")
        self._play_audio_wav_path(path)

    def _play_audio_wav_path(self, path: Path) -> None:
        try:
            self.audio_playback_engine.load(path)
            self.audio_playback_engine.play()
            self.audio_playback_status.set(f"{self._audio_playback_capability_text()}\nPlaying: {path.name}")
            self.setup_media_pipeline_status.set(f"Playing audio preview in Fragmenter: {path.name}")
        except Exception as exc:
            messagebox.showerror("Audio preview failed", f"Could not play audio in Fragmenter:\n{path}\n\n{exc}")

    def _selected_audio_primary_action(self, payload: dict[str, object] | None = None) -> str:
        payload = payload if payload is not None else self._selected_audio_payload()
        if not isinstance(payload, dict):
            return "Primary Action"
        row = _audio_selected_report_row(payload)
        status = str(payload.get("decode_status") or payload.get("status") or row.get("status") or "").lower()
        fmt = str(payload.get("format") or payload.get("detected_format") or row.get("format") or row.get("detected_format") or "").lower()
        provenance = str(payload.get("library_provenance") or "").lower()
        message = " ".join(str(payload.get(key) or row.get(key) or "") for key in ("error", "errors", "warning", "warnings", "decode_error", "message")).lower()
        output_path = _audio_payload_existing_path(payload, ("output_path", "decoded_path", "payload_path"))
        payload_path = Path(str(payload.get("payload_path"))) if payload.get("payload_path") else None
        path_suffix = (payload_path.suffix.lower() if payload_path else "")
        has_wav = bool(output_path and output_path.is_file() and output_path.suffix.lower() == ".wav")
        if has_wav:
            return "Play Experimental Preview" if "sequence" in provenance or "sequence" in status or "midi" in status or "sequence" in fmt else "Play"
        if "sequence" in provenance or "sequence" in status or "midi" in status or "sequence" in fmt:
            return "Play Experimental Preview"
        if "ps_adpcm" in status or "adpcm" in status or "vag" in status or "scei" in status or "ps_adpcm" in fmt or "adpcm" in fmt:
            return "Decode & Play"
        source_text = " ".join(str(payload.get(key) or row.get(key) or "") for key in ("name", "bank_name", "source_iso_path", "iso_path", "raw_path", "payload_path")).lower()
        if "bgm" in source_text or "food" in source_text:
            return "Analyze Regions"
        if any(token in status + " " + message for token in ("failed", "error", "unavailable")):
            return "View Error"
        if path_suffix in {".bin", ".raw", ".dat", ".bd", ".hd"} or "raw" in provenance or "raw" in status or "pcm" in status:
            return "Preview Raw"
        return "Open in Research"

    def run_selected_audio_primary_action(self, _event: object | None = None) -> None:
        payload = self._selected_audio_payload(getattr(_event, "widget", None) if isinstance(getattr(_event, "widget", None), ttk.Treeview) else None)
        action = self._selected_audio_primary_action(payload)
        self.audio_primary_action_label.set(action)
        if action in {"Play", "Play Experimental Preview"}:
            path = _audio_payload_existing_path(payload, ("output_path", "decoded_path", "payload_path"))
            if path and path.is_file() and path.suffix.lower() == ".wav":
                return self._play_audio_wav_path(path)
            return messagebox.showinfo("Audio preview", "No playable WAV preview exists for the selected row yet.")
        if action == "Decode & Play":
            self.run_audio_decode()
            self.audio_playback_status.set(f"{self._audio_playback_capability_text()}\nDecode requested; refresh or rerun the primary action when the WAV appears.")
            return
        if action == "Preview Raw":
            return self.preview_raw_audio()
        if action == "Analyze Regions":
            return self.find_raw_audio_regions()
        if action == "View Error":
            notebook = getattr(self, "audio_details_notebook", None)
            if notebook is not None:
                try:
                    notebook.select(self.audio_decode_details_text.master)
                except tk.TclError:
                    pass
            return
        return self.send_selected_audio_to_research()

    def pause_audio_playback(self) -> None:
        try:
            self.audio_playback_engine.pause()
            self.audio_playback_status.set(f"{self._audio_playback_capability_text()}\nPaused")
        except NotImplementedError as exc:
            messagebox.showinfo("Audio pause unavailable", str(exc))
        except Exception as exc:
            messagebox.showerror("Audio pause failed", str(exc))

    def stop_audio_playback(self) -> None:
        self.audio_playback_engine.stop()
        self.audio_playback_status.set(f"{self._audio_playback_capability_text()}\nStopped")
        self.setup_media_pipeline_status.set("Audio playback stopped in Fragmenter.")

    def _set_audio_music_editor_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in getattr(self, "audio_music_editable_widgets", []):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        button = getattr(self, "audio_music_export_button", None)
        if button is not None:
            try:
                button.configure(state=state)
            except tk.TclError:
                pass

    def _snddata_unresolved_status_text(self, summary: dict[str, object] | None = None, container: dict[str, object] | None = None) -> str:
        summary = summary or {}
        container = container or {}
        resources = container.get("resources") if isinstance(container.get("resources"), list) else []
        resource_count = summary.get("resource_count")
        if resource_count in (None, "", "—"):
            resource_count = len(resources) or 229
        def as_int(value: object) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0
        program_count = as_int(summary.get("program_count"))
        sample_count = as_int(summary.get("sample_rows") or summary.get("sample_count"))
        midi_count = as_int(summary.get("midi_event_count") or summary.get("midi_events") or summary.get("midi_tracks"))
        return (
            f"SNDDATA detected: {resource_count} Vers resources. Music structure not yet resolved. "
            f"{program_count} Programs / {sample_count} Samples / {midi_count} MIDI sections parsed."
        )

    def _load_snddata_json_reports(self, workspace: Path | str | None = None) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        reports = Path(workspace) / "reports" if workspace is not None else self._active_workspace_root() / "reports"
        def read(name: str) -> dict[str, object]:
            path = reports / name
            if not path.is_file():
                return {}
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
            return payload if isinstance(payload, dict) else {}
        return read("snddata_container_map.json"), read("snddata_music_graph.json"), read("snddata_pipeline_summary.json")

    def _snddata_sample_rows(self, workspace: Path | str | None = None) -> list[dict[str, object]]:
        root = (Path(workspace) if workspace is not None else self._active_workspace_root()) / "media_pipeline" / "decoded" / "audio" / "snddata" / "samples"
        rows: list[dict[str, object]] = []
        for meta in sorted(root.glob("resource_*/sample_*.json")):
            try:
                row = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def _audio_music_value(self, value: object, default: object = "—") -> object:
        if isinstance(value, dict) and "value" in value:
            return value.get("value", default)
        return default if value is None else value

    def _audio_music_resource_sort_key(self, resource_id: str) -> tuple[int, int, str]:
        match = re.search(r"resource:(\d+):0x([0-9A-Fa-f]+)", resource_id)
        if not match:
            return (10**9, 0, resource_id)
        return (int(match.group(1)), int(match.group(2), 16), resource_id)

    def _audio_music_sequence_display(self, payload: dict[str, object]) -> str:
        return (
            f"{payload.get('resource_id', '—')} | offset 0x{int(payload.get('offset') or 0):X} | "
            f"events {payload.get('midi_event_count', 0)} | channels {payload.get('channels_text', '—')} | "
            f"note-on {payload.get('note_on_count', 0)} | program {payload.get('mapped_program_resource', 'Unresolved')}"
        )

    def _collect_audio_music_sequence_payloads(self, nodes: list[object], edges: list[object]) -> list[dict[str, object]]:
        node_by_id = {str(n.get("id")): n for n in nodes if isinstance(n, dict)}
        programs_by_resource: dict[str, list[dict[str, object]]] = {}
        for node in node_by_id.values():
            if node.get("type") == "program":
                programs_by_resource.setdefault(str(node.get("resource", "")), []).append(node)
        midi_by_id = {str(n.get("id")): n for n in node_by_id.values() if n.get("type") == "midi_resource"}
        sequence_to_midi: dict[str, list[str]] = {}
        for edge in edges:
            if isinstance(edge, dict) and edge.get("relationship") == "sequence_midi":
                sequence_to_midi.setdefault(str(edge.get("source")), []).append(str(edge.get("target")))
        payloads: list[dict[str, object]] = []
        seen: set[str] = set()
        for node in node_by_id.values():
            ntype = str(node.get("type", ""))
            midi_nodes: list[dict[str, object]] = []
            if ntype == "midi_resource":
                midi_nodes = [node]
            elif ntype == "sequence":
                midi_nodes = [midi_by_id[mid] for mid in sequence_to_midi.get(str(node.get("id")), []) if mid in midi_by_id]
            else:
                continue
            for midi_node in midi_nodes:
                key = f"{node.get('id')}->{midi_node.get('id')}"
                if key in seen:
                    continue
                seen.add(key)
                parsed = midi_node.get("parsed") if isinstance(midi_node.get("parsed"), dict) else {}
                events = [e for e in parsed.get("events", []) if isinstance(e, dict)] if isinstance(parsed.get("events"), list) else []
                if not events:
                    continue
                channels = sorted({int(e["channel"]) for e in events if isinstance(e.get("channel"), int)})
                note_on_count = sum(1 for e in events if str(e.get("event_type", "")).lower() == "note_on" and int(e.get("velocity") or 0) > 0)
                resource_id = str(midi_node.get("resource") or node.get("resource") or "")
                program_nodes = sorted(programs_by_resource.get(resource_id, []), key=lambda n: str(n.get("id")))
                mapped_program = str(program_nodes[0].get("id")) if program_nodes else "Unresolved"
                section = midi_node.get("section") if isinstance(midi_node.get("section"), dict) else {}
                offset = int(section.get("offset") or 0)
                payloads.append({
                    "iid": "",
                    "node_id": str(node.get("id")),
                    "midi_node_id": str(midi_node.get("id")),
                    "name": str(node.get("label") or midi_node.get("label") or midi_node.get("id")),
                    "safe_name": re.sub(r"[^A-Za-z0-9_.-]+", "_", str(midi_node.get("id"))).strip("_") or "snddata_preview",
                    "resource_id": resource_id,
                    "resource_index": self._audio_music_resource_sort_key(resource_id)[0],
                    "offset": offset,
                    "midi_event_count": len(events),
                    "channels": channels,
                    "channels_text": ",".join(str(c) for c in channels) if channels else "—",
                    "note_on_count": note_on_count,
                    "mapped_program_resource": mapped_program,
                    "program_nodes": program_nodes,
                    "midi_report": parsed,
                    "events": events,
                })
        return sorted(payloads, key=lambda p: (self._audio_music_resource_sort_key(str(p.get("resource_id", ""))), int(p.get("offset") or 0), str(p.get("node_id"))))

    def _populate_audio_music_tree(self, container: dict[str, object], graph: dict[str, object], summary: dict[str, object]) -> None:
        tree = getattr(self, "audio_music_snddata_tree", None)
        mixer = getattr(self, "audio_music_mixer_tree", None)
        raw_tree = getattr(self, "audio_music_raw_field_tree", None)
        if not tree or not mixer or not raw_tree:
            return
        tree.delete(*tree.get_children())
        mixer.delete(*mixer.get_children())
        raw_tree.delete(*raw_tree.get_children())
        resources = container.get("resources") if isinstance(container.get("resources"), list) else []
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        edges = graph.get("confirmed_edges") if isinstance(graph.get("confirmed_edges"), list) else []
        roots = {
            "resources": tree.insert("", "end", text="SNDDATA resource tree", values=("resources", f"{len(resources)} resources")),
            "programs": tree.insert("", "end", text="Programs", values=("programs", str(summary.get("program_count", "—")))),
            "slots": tree.insert("", "end", text="Slots", values=("slots", str(summary.get("slot_count", "—")))),
            "samples": tree.insert("", "end", text="Samples", values=("samples", str(summary.get("sample_rows", "—")))),
            "seq": tree.insert("", "end", text="Sequence resources", values=("sequence", str(summary.get("sequence_resources", "—")))),
            "midi": tree.insert("", "end", text="MIDI event/track data", values=("midi", f"tracks={summary.get('midi_tracks', '—')} events={summary.get('midi_events', summary.get('midi_event_count', '—'))}")),
        }
        for idx, res in enumerate(resources):
            if not isinstance(res, dict):
                continue
            rid = f"resource {idx} @ 0x{int(res.get('offset', 0)):X}" if isinstance(res.get("offset"), int) else f"resource {idx}"
            parent = tree.insert(roots["resources"], "end", text=rid, values=(str(res.get("classification", "resource")), f"sections={len(res.get('sections') or [])} valid={res.get('valid')}"))
            for sec in res.get("sections") or []:
                if isinstance(sec, dict):
                    tree.insert(parent, "end", text=str(sec.get("tag", "section")), values=("section", f"0x{int(sec.get('offset', 0)):X} size={sec.get('block_size')} valid={sec.get('valid')}"))
        node_iids: dict[str, str] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            ntype = str(node.get("type", ""))
            if ntype == "program":
                parent = roots["programs"]
            elif ntype == "program_slot":
                parent = roots["slots"]
            elif ntype == "sample":
                parent = roots["samples"]
            elif ntype == "sequence":
                parent = roots["seq"]
            elif ntype.startswith("midi"):
                parent = roots["midi"]
            else:
                parent = ""
            if parent:
                node_iids[str(node.get("id"))] = tree.insert(parent, "end", text=str(node.get("label", node.get("id"))), values=(ntype, str(node.get("id", ""))))
        payloads = self._collect_audio_music_sequence_payloads(nodes, edges)
        sequence_choices = [self._audio_music_sequence_display(p) for p in payloads]
        sequence_lookup = dict(zip(sequence_choices, payloads))
        for display, payload in sequence_lookup.items():
            payload["display"] = display
            payload["iid"] = node_iids.get(str(payload.get("node_id"))) or node_iids.get(str(payload.get("midi_node_id"))) or ""
        combo = getattr(self, "audio_music_sequence_combo", None)
        if combo is not None:
            combo.configure(values=sequence_choices, state="readonly" if sequence_choices else "disabled")
        self.audio_music_sequence_choices = sequence_lookup
        self.audio_music_all_sequence_displays = sequence_choices
        if sequence_choices:
            self.audio_music_sequence_choice.set(sequence_choices[0])
            self._on_audio_music_sequence_choice()
        else:
            self.audio_music_sequence_choice.set("")
            if hasattr(self, "audio_music_mapping_status"):
                self.audio_music_mapping_status.set("SNDDATA structure detected, but no playable sequence has been reconstructed.")
            if hasattr(self, "audio_music_play_button"):
                self.audio_music_play_button.configure(state="disabled")
            for var in getattr(self, "audio_music_editor_fields", {}).values():
                var.set("")
        for key in ("source", "status", "resource_count", "program_count", "slot_count", "sample_rows", "decoded_sample_wavs", "midi_event_count", "confirmed_edges", "candidate_edges", "unknown_mappings"):
            if key in summary:
                raw_tree.insert("", "end", values=(key, summary[key]))
        raw_tree.insert("", "end", values=("graph_confirmed_edges", len(edges)))

    def refresh_audio_music_system_reports(self) -> None:
        workspace = self._active_workspace_root()
        def work(_cancel: threading.Event):
            container, graph, summary = self._load_snddata_json_reports(workspace)
            sample_rows = self._snddata_sample_rows(workspace)
            snddata = self._resolve_extracted_snddata_path(workspace)
            editor = None
            editor_error = ""
            if snddata and snddata.is_file():
                try:
                    editor = SnddataEditor.from_file(snddata)
                except Exception as exc:
                    editor_error = str(exc)
            return container, graph, summary, sample_rows, snddata, editor, editor_error

        def done(result, exc):
            if exc:
                self._finish_audio_worker(f"SNDDATA refresh failed: {exc}")
                return
            container, graph, summary, sample_rows, snddata, editor, editor_error = result
            if editor_error:
                self.audio_pipeline_status.set(f"SNDDATA editor unavailable: {editor_error}")
            self._populate_audio_music_tree(container, graph, summary)
            sample_tree = getattr(self, "audio_snddata_samples_tree", None)
            if sample_tree is not None:
                sample_tree.delete(*sample_tree.get_children())
                self.audio_music_sample_payloads = {}
                def insert_sample_chunk(start: int = 0) -> None:
                    for row in sample_rows[start:start + 150]:
                        output = str(row.get("output_path") or "")
                        duration = row.get("duration_estimate") or row.get("duration") or "—"
                        iid = sample_tree.insert("", "end", values=(row.get("resource_id", "—"), row.get("sample_id", "—"), row.get("sample_rate", "—"), duration, row.get("boundary_source", "—"), row.get("decode_status", row.get("status", "—")), output))
                        payload = dict(row)
                        payload["payload_path"] = output
                        payload["name"] = f"SNDDATA sample {row.get('sample_id', '—')}"
                        self.audio_music_sample_payloads[iid] = payload
                    if start + 150 < len(sample_rows):
                        self.after(1, lambda: insert_sample_chunk(start + 150))
                    elif not sample_tree.get_children():
                        sample_tree.insert("", "end", values=("—", "—", "—", "—", "—", "no decoded SNDDATA WAV rows", str(workspace / "media_pipeline" / "decoded" / "audio" / "snddata" / "samples")))
                insert_sample_chunk()
            self.audio_music_editor = editor
            has_real_music = bool(summary.get("program_count") or summary.get("sample_rows") or summary.get("midi_event_count") or summary.get("midi_events"))
            if editor is not None and has_real_music:
                self.audio_music_source_label.set(f"Experimental SNDDATA editor — source: {editor.source_path}")
                self._set_audio_music_editor_enabled(True)
            else:
                self.audio_music_source_label.set(self._snddata_unresolved_status_text(summary, container) if snddata else "Experimental SNDDATA editor — source: not loaded")
                self._set_audio_music_editor_enabled(False)
            self._finish_audio_worker("SNDDATA music reports refreshed.")

        self._run_audio_worker("Refresh SNDDATA Music", work, done, progress_text="Loading SNDDATA reports off the Tk thread…")

    def undo_audio_music_edit(self) -> None:
        if hasattr(self, "audio_pipeline_status"):
            self.audio_pipeline_status.set("Music editor undo is not available yet.")

    def redo_audio_music_edit(self) -> None:
        if hasattr(self, "audio_pipeline_status"):
            self.audio_pipeline_status.set("Music editor redo is not available yet.")

    def export_patched_snddata(self) -> None:
        editor = getattr(self, "audio_music_editor", None)
        if editor is None:
            return messagebox.showinfo("Export Patched SNDDATA", "Create/load a real SNDDATA editor first.")
        out = self._active_workspace_root() / "music_edits" / "snddata_modified.bin"
        try:
            editor.export_patched(out, self._active_workspace_root() / "reports" / "snddata_edit_manifest.json", self._active_workspace_root() / "reports" / "snddata_edit_manifest.txt")
        except Exception as exc:
            return messagebox.showerror("Export Patched SNDDATA", str(exc))
        self.audio_pipeline_status.set(f"Exported patched SNDDATA: {out}")
        self.refresh_quick_report_locator()

    def refresh_audio_music_preview(self) -> None:
        """Apply experimental SNDDATA edit-model changes and refresh the rendered preview when possible."""
        snddata = self._resolve_extracted_snddata_path()
        if not snddata:
            status = "DATA/SNDDATA.BIN has not been extracted."
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set(status)
            return
        model = getattr(self, "audio_music_edit_model", {})
        model.update({
            "snddata_path": str(snddata),
            "tempo": getattr(self, "audio_music_tempo", tk.DoubleVar(value=120.0)).get(),
            "master_gain": getattr(self, "audio_music_master_gain", tk.DoubleVar(value=1.0)).get(),
            "loop": getattr(self, "audio_music_loop", tk.BooleanVar(value=False)).get(),
            "editor_fields": {key: var.get() for key, var in getattr(self, "audio_music_editor_fields", {}).items()},
            "preview_refresh_mode": "immediate_or_refresh_preview_fallback",
        })
        self.audio_music_edit_model = model
        status = "Music System preview refreshed (experimental player/edit model)."
        if hasattr(self, "audio_pipeline_status"):
            self.audio_pipeline_status.set(status)

    def play_audio_music_preview(self) -> None:
        if not self.audio_playback_engine.capabilities.get("play"):
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set("Playback unavailable")
            return messagebox.showinfo("Music preview", "Playback unavailable")
        selection = self._selected_audio_music_sequence()
        if selection is None:
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set("Mapping unresolved")
            return messagebox.showinfo("Music preview", "Select an explicit sequence or MIDI node first.")
        snddata = self._resolve_extracted_snddata_path()
        if not snddata:
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set("Mapping unresolved")
            return messagebox.showinfo("Music preview", "Mapping unresolved: DATA/SNDDATA.BIN has not been extracted.")
        if hasattr(self, "audio_pipeline_status"):
            self.audio_pipeline_status.set("Rendering preview…")
        try:
            fixture = self._write_audio_music_preview_fixture(selection)
            if fixture is None:
                if hasattr(self, "audio_pipeline_status"):
                    self.audio_pipeline_status.set("Mapping unresolved")
                return messagebox.showinfo("Music preview", "Mapping unresolved: no renderable sequence/program/sample mapping is available.")
            out = self._active_workspace_root() / "media_pipeline" / "decoded" / "audio" / "snddata" / "previews" / f"{selection['safe_name']}.wav"
            cmd = [PY, str(TOOLS / "snddata_player.py"), str(fixture), str(out)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            if not out.is_file():
                raise FileNotFoundError(out)
            self.audio_playback_engine.set_loop(self.audio_music_loop.get())
            if self.audio_playback_engine.capabilities.get("gain") and hasattr(self.audio_playback_engine, "set_gain"):
                self.audio_playback_engine.set_gain(float(self.audio_music_master_gain.get()))
            self.audio_playback_engine.load(out)
            self.audio_playback_engine.play()
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set(f"Playing {selection['name']}")
        except Exception as exc:
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set("Playback unavailable")
            messagebox.showerror("Music preview failed", f"Playback unavailable:\n{exc}")

    def pause_audio_music_preview(self) -> None:
        if not self.audio_playback_engine.supports_pause:
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set("Playback unavailable")
            return
        try:
            self.audio_playback_engine.pause()
            if hasattr(self, "audio_pipeline_status"):
                self.audio_pipeline_status.set("Paused")
        except Exception as exc:
            messagebox.showerror("Music pause failed", str(exc))

    def stop_audio_music_preview(self) -> None:
        self.audio_playback_engine.stop()
        if hasattr(self, "audio_pipeline_status"):
            self.audio_pipeline_status.set("Stopped")

    def _on_audio_music_sequence_search(self, event=None) -> None:
        combo = getattr(self, "audio_music_sequence_combo", None)
        if combo is None:
            return
        displays = list(getattr(self, "audio_music_all_sequence_displays", []))
        char = getattr(event, "char", "") if event is not None else ""
        if not char or not char.isprintable():
            combo.configure(values=displays)
            return
        query = (getattr(self, "_audio_music_sequence_search_text", "") + char).lower()
        self._audio_music_sequence_search_text = query
        self.after(900, lambda: setattr(self, "_audio_music_sequence_search_text", ""))
        filtered = [display for display in displays if query in display.lower()]
        combo.configure(values=filtered or displays)
        if filtered:
            self.audio_music_sequence_choice.set(filtered[0])
            self._on_audio_music_sequence_choice()

    def _on_audio_music_sequence_choice(self, _event=None) -> None:
        selection = getattr(self, "audio_music_sequence_choices", {}).get(self.audio_music_sequence_choice.get())
        tree = getattr(self, "audio_music_snddata_tree", None)
        if selection and tree is not None and selection.get("iid"):
            tree.selection_set(selection["iid"])
            tree.see(selection["iid"])
        self._populate_audio_music_selection_details(selection)

    def _populate_audio_music_selection_details(self, selection: dict[str, object] | None) -> None:
        mixer = getattr(self, "audio_music_mixer_tree", None)
        raw_tree = getattr(self, "audio_music_raw_field_tree", None)
        if mixer is not None:
            mixer.delete(*mixer.get_children())
        if not selection:
            if hasattr(self, "audio_music_play_button"):
                self.audio_music_play_button.configure(state="disabled")
            return
        programs = [p for p in selection.get("program_nodes", []) if isinstance(p, dict)] if isinstance(selection.get("program_nodes"), list) else []
        events = [e for e in selection.get("events", []) if isinstance(e, dict)] if isinstance(selection.get("events"), list) else []
        channels = selection.get("channels") if isinstance(selection.get("channels"), list) else []
        if mixer is not None:
            for channel in channels or ["—"]:
                channel_events = [e for e in events if e.get("channel") == channel]
                note_on = sum(1 for e in channel_events if str(e.get("event_type", "")).lower() == "note_on" and int(e.get("velocity") or 0) > 0)
                program = programs[int(channel) % len(programs)] if programs and isinstance(channel, int) else (programs[0] if programs else {})
                parsed = program.get("parsed") if isinstance(program.get("parsed"), dict) else {}
                slots = parsed.get("slots") if isinstance(parsed.get("slots"), list) else []
                slot = slots[0] if slots and isinstance(slots[0], dict) else {}
                sample = self._audio_music_value(slot.get("sample_index", slot.get("sample_id", "—"))) if slot else "—"
                mixer.insert("", "end", values=("off", "off", f"channel {channel}", program.get("id", "Unresolved"), f"sample {sample}; note-on {note_on}", self._audio_music_value(slot.get("volume", "—")), self._audio_music_value(slot.get("pan", "—")), self._audio_music_value(slot.get("tempo_pitch", parsed.get("tempo_pitch", "—"))), "ready"))
        fields = getattr(self, "audio_music_editor_fields", {})
        first_program = programs[0] if programs else {}
        parsed_program = first_program.get("parsed") if isinstance(first_program.get("parsed"), dict) else {}
        first_slot = (parsed_program.get("slots") or [{}])[0] if isinstance(parsed_program.get("slots"), list) and parsed_program.get("slots") else {}
        values = {
            "Program": first_program.get("id", "Unresolved"),
            "Slot": self._audio_music_value(first_slot.get("index", "—")) if isinstance(first_slot, dict) else "—",
            "Sample": self._audio_music_value(first_slot.get("sample_index", first_slot.get("sample_id", "—"))) if isinstance(first_slot, dict) else "—",
            "Volume": self._audio_music_value(first_slot.get("volume", parsed_program.get("master_volume", "—"))) if isinstance(first_slot, dict) else "—",
            "Pan": self._audio_music_value(first_slot.get("pan", "—")) if isinstance(first_slot, dict) else "—",
            "Pitch / Tempo": self._audio_music_value(first_slot.get("tempo_pitch", parsed_program.get("tempo_pitch", "—"))) if isinstance(first_slot, dict) else "—",
            "Track / Channel": selection.get("channels_text", "—"),
            "Mapping": selection.get("mapped_program_resource", "Unresolved"),
        }
        for key, var in fields.items():
            var.set(str(values.get(key, "")))
        if raw_tree is not None:
            for key in ("resource_id", "offset", "midi_event_count", "channels_text", "note_on_count", "mapped_program_resource"):
                raw_tree.insert("", "end", values=(f"selected_{key}", selection.get(key, "—")))
        if hasattr(self, "audio_music_mapping_status"):
            self.audio_music_mapping_status.set(f"Mapping: {selection.get('mapped_program_resource', 'Unresolved')}")
        if hasattr(self, "audio_music_play_button"):
            self.audio_music_play_button.configure(state="normal")
        self.audio_music_active_preview_source = selection

    def _selected_audio_music_sequence(self) -> dict[str, str] | None:
        combo_selection = getattr(self, "audio_music_sequence_choices", {}).get(getattr(self, "audio_music_sequence_choice", tk.StringVar(value="")).get())
        if combo_selection:
            return combo_selection
        active = getattr(self, "audio_music_active_preview_source", None)
        if isinstance(active, dict):
            return active
        tree = getattr(self, "audio_music_snddata_tree", None)
        if tree is None or not tree.selection():
            return None
        iid = tree.selection()[0]
        values = tree.item(iid, "values")
        kind = str(values[0] if values else "").lower()
        if "sequence" not in kind and "midi" not in kind:
            return None
        name = str(tree.item(iid, "text") or iid)
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "snddata_preview"
        return {"iid": str(iid), "name": name, "safe_name": safe}

    def _write_audio_music_preview_fixture(self, selection: dict[str, object]) -> Path | None:
        programs = [p.get("parsed") for p in selection.get("program_nodes", []) if isinstance(p, dict) and isinstance(p.get("parsed"), dict)] if isinstance(selection.get("program_nodes"), list) else []
        events = [e for e in selection.get("events", []) if isinstance(e, dict)] if isinstance(selection.get("events"), list) else []
        midi_report = selection.get("midi_report") if isinstance(selection.get("midi_report"), dict) else None
        if not programs:
            editor = getattr(self, "audio_music_editor", None)
            if editor is None:
                snddata = self._resolve_extracted_snddata_path()
                if not snddata:
                    return None
                editor = SnddataEditor.from_file(snddata)
            resource_index = selection.get("resource_index")
            for group in editor.groups:
                if resource_index not in (None, 10**9) and getattr(group, "index", None) != resource_index:
                    continue
                for sec in group.sections:
                    parsed_prog = sec.evidence.get("scei_prog")
                    if isinstance(parsed_prog, dict):
                        programs.extend(p for p in parsed_prog.get("programs", []) if isinstance(p, dict))
                    if not events:
                        parsed_midi = sec.evidence.get("scei_midi")
                        if isinstance(parsed_midi, dict) and int(sec.offset) == int(selection.get("offset") or -1):
                            midi_report = parsed_midi
                            section_events = parsed_midi.get("events")
                            events = [e for e in section_events if isinstance(e, dict)] if isinstance(section_events, list) else []
        samples = self._audio_music_preview_samples()
        if not events or not programs or not samples:
            return None
        fixture = self._active_workspace_root() / "media_pipeline" / "decoded" / "audio" / "snddata" / "previews" / f"{selection['safe_name']}.json"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        payload = {"events": events, "programs": programs, "samples": samples, "midi_report": midi_report or {}, "selection": selection}
        fixture.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return fixture

    def _audio_music_preview_samples(self) -> list[dict[str, object]]:
        rows = self._snddata_sample_rows()
        samples: list[dict[str, object]] = []
        for index, row in enumerate(rows):
            path = Path(str(row.get("output_path") or ""))
            if not path.is_file() or path.suffix.lower() != ".wav":
                continue
            try:
                with wave.open(str(path), "rb") as wav:
                    channels = wav.getnchannels()
                    width = wav.getsampwidth()
                    rate = wav.getframerate()
                    raw = wav.readframes(wav.getnframes())
                if width != 2:
                    continue
                vals = [int.from_bytes(raw[i:i + 2], "little", signed=True) / 32768.0 for i in range(0, len(raw), 2)]
                pcm = vals[::channels] if channels > 1 else vals
                samples.append({"index": int(row.get("sample_id", index)), "sample_rate": rate, "pcm": pcm})
            except Exception:
                continue
        return samples

    def _selected_audio_payload_path(self) -> Path | None:
        payload = self._selected_audio_payload()
        if isinstance(payload, dict):
            path = payload.get("payload_path")
            return Path(str(path)) if path else None
        return None

    def _selected_audio_payload(self, preferred_tree: ttk.Treeview | None = None) -> dict[str, object] | None:
        tree_payloads = (
            (getattr(self, "audio_library_tree", None), getattr(self, "audio_library_payloads", {})),
            (getattr(self, "audio_wav_tree", None), getattr(self, "audio_wav_payloads", {})),
            (getattr(self, "audio_raw_tree", None), getattr(self, "audio_raw_payloads", {})),
            (getattr(self, "audio_failed_tree", None), getattr(self, "audio_failed_payloads", {})),
            (getattr(self, "audio_snddata_samples_tree", None), getattr(self, "audio_music_sample_payloads", {})),
        )
        ordered = list(tree_payloads)
        if preferred_tree is not None:
            ordered.sort(key=lambda item: 0 if item[0] is preferred_tree else 1)
        for tree, payloads in ordered:
            if tree and tree.selection():
                payload = payloads.get(tree.selection()[0])
                return payload if isinstance(payload, dict) else None
        return None

    def _on_audio_tree_select(self, _event: object | None = None) -> None:
        preferred_tree = getattr(_event, "widget", None)
        payload = self._selected_audio_payload(preferred_tree if isinstance(preferred_tree, ttk.Treeview) else None)
        path = Path(str(payload.get("payload_path"))) if payload and payload.get("payload_path") else None
        if not path:
            return
        self.audio_selected_file.set(str(path))
        meta = self._audio_wav_metadata(path) if path.suffix.lower() == ".wav" and path.is_file() else {"duration": "—", "sample_rate": "—", "channels": "—", "sample_width": "—"}
        text = f"File: {path.name}\nFormat: {path.suffix.lower().lstrip('.') or 'unknown'}\nDuration: {meta['duration']}\nSample rate: {meta['sample_rate']}\nChannels: {meta['channels']}\nSample width: {meta['sample_width']}\n"
        self._replace_text(self.audio_metadata_text, text, readonly=False)
        self._replace_text(self.audio_decode_details_text, format_audio_decode_details(payload), readonly=False)
        for label, value in audio_source_field_values(payload).items():
            self.audio_source_fields[label].set(value)
        self.audio_primary_action_label.set(self._selected_audio_primary_action(payload))


    def select_raw_audio_source(self) -> None:
        path = filedialog.askopenfilename(title="Select raw audio/container file", initialdir=str(ROOT))
        if path:
            self.raw_audio_source.set(path)
            self.raw_audio_probe_status.set(f"Selected: {path}")

    def _raw_audio_int(self, value: str, default: int | None = None) -> int | None:
        text = str(value or "").strip()
        if not text:
            return default
        return int(text, 0)

    def _raw_audio_source_path(self) -> Path | None:
        raw = self.raw_audio_source.get().strip() or str(self._selected_audio_payload_path() or "")
        if not raw:
            messagebox.showinfo("Raw audio probe", "Select a raw audio source first.")
            return None
        path = Path(raw).expanduser()
        if not path.is_file():
            messagebox.showinfo("Raw audio probe", f"Source file does not exist: {path}")
            return None
        self.raw_audio_source.set(str(path))
        return path

    def _raw_audio_interpretation(self) -> RawInterpretation:
        return RawInterpretation(
            self.raw_audio_encoding.get(),
            int(self.raw_audio_channels.get()),
            int(self.raw_audio_sample_rate.get()),
            self._raw_audio_int(self.raw_audio_start_offset.get(), 0) or 0,
            self._raw_audio_int(self.raw_audio_length.get(), None),
            self._raw_audio_int(self.raw_audio_end_offset.get(), None),
        )

    def _show_raw_audio_result(self, payload: object, status: str) -> None:
        self.raw_audio_probe_status.set(status)
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        self._replace_text(self.raw_audio_probe_text, text, readonly=False)

    def _run_raw_audio_file_worker(self, action: str, path: Path, func, on_success) -> None:
        interp = self._raw_audio_interpretation()
        start = self._raw_audio_int(self.raw_audio_start_offset.get(), 0) or 0
        length = self._raw_audio_int(self.raw_audio_length.get(), None)
        end = self._raw_audio_int(self.raw_audio_end_offset.get(), None)
        workspace = self._active_workspace_root()

        def work(cancel: threading.Event):
            if cancel.is_set():
                return {"cancelled": True}
            data = path.read_bytes()
            if cancel.is_set():
                return {"cancelled": True}
            return func(data, interp, start, length, end, workspace)

        def done(result, exc):
            if exc:
                self._finish_audio_worker(f"{action} failed: {exc}")
                return messagebox.showerror(action, str(exc))
            if isinstance(result, dict) and result.get("cancelled"):
                self._finish_audio_worker(f"{action} cancelled.")
                return
            on_success(result)
            self._finish_audio_worker(f"{action} complete.")

        self._run_audio_worker(action, work, done, progress_text="Reading/analyzing raw audio off the Tk thread…")

    def auto_probe_raw_audio(self) -> None:
        path = self._raw_audio_source_path()
        if not path:
            return
        def work(data, _interp, start, length, end, _workspace):
            return probe_candidates(data, start, length, end)
        def done(candidates):
            self.raw_audio_latest_candidates = candidates
            best = next((c for c in candidates if not c.get("rejected")), candidates[0] if candidates else None)
            if best:
                interp = best["interpretation"]
                self.raw_audio_encoding.set(str(interp["encoding"]))
                self.raw_audio_channels.set(int(interp["channels"]))
                self.raw_audio_sample_rate.set(int(interp["sample_rate"]))
            self._show_raw_audio_result({"source": str(path), "candidates": candidates[:12]}, f"Auto probe complete: {len(candidates)} raw_interpretation_candidate rows ranked.")
        self._run_raw_audio_file_worker("Auto Probe Raw Audio", path, work, done)

    def preview_raw_audio(self) -> None:
        path = self._raw_audio_source_path()
        if not path:
            return
        self._run_raw_audio_file_worker("Preview Raw Audio", path, lambda data, interp, *_: analyze_raw_audio(data, interp), lambda result: self._show_raw_audio_result({"source": str(path), "candidate": result}, "Preview metrics refreshed for selected raw interpretation."))

    def export_raw_audio_wav_preview(self) -> None:
        path = self._raw_audio_source_path()
        if not path:
            return
        out = self._active_workspace_root() / "media_pipeline" / "decoded" / "audio" / "wav" / f"{path.stem}_raw_preview.wav"
        self._run_raw_audio_file_worker("Export WAV Preview", path, lambda data, interp, _s, _l, _e, _w: (export_wav(data, interp, out), out)[1], lambda result: (self._show_raw_audio_result({"source": str(path), "output_path": str(result), "interpretation": self._raw_audio_interpretation().__dict__}, f"Exported WAV preview: {result}"), self.refresh_audio_candidate_tables()))

    def find_raw_audio_regions(self) -> None:
        path = self._raw_audio_source_path()
        if not path:
            return
        def work(data, interp, _s, _l, _e, workspace):
            json_path, txt_path, region_map = write_region_reports(data, path, interp, workspace / "reports")
            return json_path, txt_path, region_map
        def done(result):
            json_path, txt_path, region_map = result
            self.raw_audio_latest_region_map = region_map
            payload = region_map | {"json_path": str(json_path), "text_path": str(txt_path)}
            self._show_raw_audio_result(payload, f"Find Audio Regions complete: {len(region_map.get('regions', []))} likely regions; wrote {json_path.name}.")
            self._populate_audio_stream_regions(payload)
        self._run_raw_audio_file_worker("Find Audio Regions", path, work, done)

    def _populate_audio_stream_regions(self, payload: dict[str, object]) -> None:
        if not hasattr(self, "audio_stream_regions_tree"):
            if hasattr(self, "audio_stream_regions_text"):
                self._replace_text(self.audio_stream_regions_text, json.dumps(payload, indent=2, sort_keys=True), readonly=False)
            return
        tree = self.audio_stream_regions_tree
        tree.delete(*tree.get_children())
        self.audio_stream_region_payloads.clear()
        regions = payload.get("regions") or []
        for index, region in enumerate(regions if isinstance(regions, list) else []):
            if not isinstance(region, dict):
                continue
            interp = region.get("raw_interpretation") if isinstance(region.get("raw_interpretation"), dict) else {}
            evidence = region.get("boundary_evidence") or []
            boundary_source = ", ".join(str(item) for item in evidence) if isinstance(evidence, list) else str(evidence)
            duration = region.get("duration")
            confidence = region.get("confidence")
            iid = f"stream_region_{index}"
            values = (
                str(region.get("region_id") or iid),
                self._format_offset_value(region.get("start")),
                self._format_offset_value(region.get("end")),
                self._format_int_value(region.get("size")),
                f"{float(duration):.3f}s" if isinstance(duration, (int, float)) else "",
                str(interp.get("encoding") or ""),
                str(interp.get("channels") or ""),
                str(interp.get("sample_rate") or ""),
                f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "",
                boundary_source,
            )
            tree.insert("", "end", iid=iid, values=values)
            self.audio_stream_region_payloads[iid] = region
        if tree.get_children():
            first = tree.get_children()[0]
            tree.selection_set(first)
            tree.focus(first)
            self._on_stream_region_select()
        elif hasattr(self, "audio_stream_regions_text"):
            self._replace_text(self.audio_stream_regions_text, json.dumps(payload, indent=2, sort_keys=True), readonly=False)

    @staticmethod
    def _format_offset_value(value: object) -> str:
        return f"0x{int(value):X}" if isinstance(value, int) else str(value or "")

    @staticmethod
    def _format_int_value(value: object) -> str:
        return f"{int(value):,}" if isinstance(value, int) else str(value or "")

    def _on_stream_region_select(self, _event: object | None = None) -> None:
        region = self._selected_stream_region()
        payload: object = region if region is not None else (self.raw_audio_latest_region_map or {})
        if hasattr(self, "audio_stream_regions_text"):
            self._replace_text(self.audio_stream_regions_text, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), readonly=False)

    def _selected_stream_region(self) -> dict[str, object] | None:
        tree = getattr(self, "audio_stream_regions_tree", None)
        if tree is not None:
            selected = tree.selection()
            if selected:
                payload = self.audio_stream_region_payloads.get(selected[0])
                if payload is not None:
                    return payload
        if not self.raw_audio_latest_region_map:
            return None
        regions = (self.raw_audio_latest_region_map or {}).get("regions") or []
        return regions[0] if regions else None

    def _stream_region_interpretation(self, region: dict[str, object]) -> RawInterpretation:
        interp = dict(region.get("raw_interpretation") or {})
        interp["start_offset"] = int(region["start"])
        interp["length"] = int(region["size"])
        interp["end_offset"] = int(region.get("end") or (int(region["start"]) + int(region["size"])))
        return RawInterpretation(**interp)

    def play_stream_region(self, _event: object | None = None) -> None:
        path = self._raw_audio_source_path()
        region = self._selected_stream_region()
        if not path or not region:
            messagebox.showinfo("Stream Regions", "Select a region first. Run Find Regions if the table is empty.")
            return
        region_id = str(region.get("region_id") or "region")
        temp_path = Path(tempfile.gettempdir()) / f"fragmenter_{path.stem}_{region_id}.wav"
        interp = self._stream_region_interpretation(region)
        def done(result):
            try:
                self.audio_stream_region_temp_wav = Path(result)
                self.audio_playback_engine.load(result)
                self.audio_playback_engine.play()
                self.audio_playback_status.set(f"{self._audio_playback_capability_text()}\nPlaying stream region: {region_id}")
                self._show_raw_audio_result({"region": region, "temporary_wav": str(result)}, f"Playing stream region: {region_id}.")
            except Exception as exc:
                messagebox.showerror("Play Region failed", str(exc))
        self._run_raw_audio_file_worker("Play Region", path, lambda data, _i, *_: (export_wav(data, interp, temp_path), temp_path)[1], done)

    def open_stream_region_source(self) -> None:
        path = self._raw_audio_source_path()
        if path:
            self._open_path_with_platform(path)

    def copy_stream_region_start_offset(self) -> None:
        region = self._selected_stream_region()
        if not region:
            return messagebox.showinfo("Stream Regions", "Select a region first.")
        self._copy_text_to_clipboard(str(region.get("start", "")))
        self.raw_audio_probe_status.set(f"Copied start offset for {region.get('region_id')}: {region.get('start')}")

    def preview_stream_region(self) -> None:
        region = self._selected_stream_region()
        if not region:
            messagebox.showinfo("Stream Regions", "No region candidate is available. Run Find Regions first.")
            return
        interp = self._stream_region_interpretation(region)
        path = self._raw_audio_source_path()
        if not path:
            return
        self._run_raw_audio_file_worker("Preview Region", path, lambda data, _i, *_: analyze_raw_audio(data, interp), lambda result: self._show_raw_audio_result({"region": region, "analysis": result}, f"Preview Region: {region.get('region_id')}."))

    def export_stream_region_wav(self) -> None:
        path = self._raw_audio_source_path()
        region = self._selected_stream_region()
        if not path or not region:
            return
        interp = self._stream_region_interpretation(region)
        out = self._active_workspace_root() / "media_pipeline" / "decoded" / "audio" / "wav" / f"{path.stem}_{region.get('region_id', 'region')}.wav"
        self._run_raw_audio_file_worker("Export Region WAV", path, lambda data, _i, _s, _l, _e, _w: (export_wav(data, interp, out), out)[1], lambda result: (self._show_raw_audio_result({"region": region, "output_path": str(result)}, f"Export Region WAV: {result}"), self.refresh_audio_candidate_tables()))

    def analyze_raw_audio_container(self) -> None:
        path = self._raw_audio_source_path()
        if not path:
            return
        def work(data, _interp, start, length, end, _workspace):
            effective_length = length if length is not None else min(len(data), 262144)
            candidates = probe_candidates(data, start, effective_length, end)[:20]
            return {"source": str(path), "size": len(data), "analysis": "container byte-range raw PCM probe", "candidates": candidates}
        self._run_raw_audio_file_worker("Analyze Container", path, work, lambda payload: self._show_raw_audio_result(payload, "Analyze Container complete."))

    def cancel_audio_pipeline(self) -> None:
        self.audio_busy_cancel.set()
        cancelled = self.runner.cancel()
        if cancelled or getattr(self, "audio_pipeline_job_active", False):
            self.run_status.set("cancelled")
            self._set_audio_busy_state(False)
            self._set_audio_pipeline_phase("cancelled")

    def refresh_audio_reports(self) -> None:
        workspace = self._active_workspace_root()
        def work(_cancel: threading.Event):
            return load_audio_report_sources(workspace)
        def done(buckets, exc):
            if exc:
                self._finish_audio_worker(f"Audio report refresh failed: {exc}")
                return
            self.refresh_project_tree()
            self.refresh_quick_report_locator()
            self.refresh_audio_candidate_tables(select_best=True, buckets=buckets)
            summary = audio_report_completion_summary(workspace, buckets)
            self.audio_pipeline_progress.set(100.0)
            self._finish_audio_worker(format_audio_completion_status(summary))
        self._run_audio_worker("Refresh Audio Reports", work, done, progress_text="Loading audio reports off the Tk thread…")


    def _audio_library_file_path(self) -> Path | None:
        raw = self.audio_library_container.get().strip()
        if not raw:
            selected = self._selected_audio_payload_path()
            if selected:
                raw = str(selected)
                self.audio_library_container.set(raw)
        if not raw:
            messagebox.showinfo("Audio Library", "Choose an audio/container file first.")
            return None
        path = Path(raw).expanduser()
        if not path.is_file():
            messagebox.showinfo("Audio Library", f"Audio/container file does not exist: {path}")
            return None
        self.audio_library_container.set(str(path))
        return path

    def browse_audio_library_container(self) -> None:
        filetypes = [
            ("Audio/container candidates", "*.wav *.bin *.hd *.bd *.vag *.vh *.vb *.vab *.adx *.aif *.aiff *.aifc *.mid *.midi *.seq *.pcm *.adp *.adpcm *.snd *.bgm *.bnk"),
            ("All files", "*"),
        ]
        path = filedialog.askopenfilename(title="Select audio/container file", initialdir=str(ROOT), filetypes=filetypes)
        if path:
            self.audio_library_container.set(path)
            self.raw_audio_source.set(path)
            self.audio_pipeline_status.set(f"Selected manual audio/container: {Path(path).name}")

    def open_audio_library_container(self) -> None:
        path = self._audio_library_file_path()
        if path:
            self._open_path_with_platform(path)

    def _manual_audio_library_row(self, path: Path, report: dict[str, object] | None = None) -> dict[str, object]:
        data = path.read_bytes()[:262144]
        guess = audio_decoder.identify_audio_format(data, str(path))
        row: dict[str, object] = {
            "name": path.name,
            "source_path": str(path),
            "source_candidate": str(path),
            "source_iso_path": str(path),
            "detected_format": guess.detected_format,
            "format": guess.detected_format,
            "confidence": guess.confidence,
            "sample_rate": guess.sample_rate or "—",
            "duration": f"{guess.duration_estimate:.2f}s" if guess.duration_estimate else "—",
            "decode_status": "manual_added",
            "warnings": list(guess.warnings),
            "errors": list(guess.errors),
            "next_action": guess.next_action,
            "payload_path": str(path),
            "manual_source": True,
        }
        if report:
            row.update(report)
            row["report_row"] = dict(report)
            row["payload_path"] = str(report.get("output_path") or report.get("raw_path") or path)
            row["source_path"] = str(path)
            row["source_candidate"] = str(path)
        return row

    def add_audio_library_manual_file(self) -> None:
        path = self._audio_library_file_path()
        if not path:
            return
        self.audio_library_manual_rows = [r for r in self.audio_library_manual_rows if str(r.get("source_path")) != str(path)]
        self.audio_library_manual_rows.append(self._manual_audio_library_row(path))
        self.refresh_audio_candidate_tables()
        self.audio_pipeline_status.set(f"Added manual Audio Library row: {path.name}")

    def analyze_selected_audio_library_file(self) -> None:
        path = self._audio_library_file_path()
        if not path:
            return
        self.raw_audio_source.set(str(path))
        out_root = self._active_workspace_root() / "media_pipeline" / "decoded"
        def work(cancel: threading.Event):
            if cancel.is_set():
                return {"cancelled": True}
            report = audio_decoder.decode_audio_candidate(path, out_root, {"source_iso_path": str(path), "manual_source": True})
            data = path.read_bytes()
            report["raw_probe_candidates"] = probe_candidates(data, 0, min(len(data), 262144), None)[:12]
            return report
        def done(result, exc):
            if exc:
                self._finish_audio_worker(f"Analyze Selected File failed: {exc}")
                return messagebox.showerror("Analyze Selected File", str(exc))
            if isinstance(result, dict) and result.get("cancelled"):
                self._finish_audio_worker("Analyze Selected File cancelled.")
                return
            self.audio_library_manual_rows = [r for r in self.audio_library_manual_rows if str(r.get("source_path")) != str(path)]
            self.audio_library_manual_rows.append(self._manual_audio_library_row(path, result if isinstance(result, dict) else None))
            self.refresh_audio_candidate_tables()
            self._show_raw_audio_result(result, f"Analyze Selected File complete: {path.name}")
            self._finish_audio_worker("Analyze Selected File complete.")
        self._run_audio_worker("Analyze Selected File", work, done, progress_text="Decoding/analyzing selected audio file off the Tk thread…")

    def _audio_library_provenance(self, row: dict[str, object], bucket: str) -> tuple[str, str, str]:
        status = str(row.get("decode_status") or row.get("status") or "").lower()
        fmt = str(row.get("format") or row.get("detected_format") or "").lower()
        output = str(row.get("output_path") or row.get("payload_path") or "")
        if "sequence" in status or "midi" in status or "sequence" in fmt or "midi" in fmt:
            return "EXPERIMENTAL SEQUENCE RENDER", "experimental", "sequence_render"
        if "ps_adpcm" in status or "adpcm" in status or "vag" in status:
            return "PS ADPCM DECODE", "decoded", "ps_adpcm"
        if bucket == "decoded_wavs" or output.lower().endswith(".wav"):
            return "CONFIRMED WAV", "confirmed", "confirmed_wav"
        return "RAW PCM INTERPRETATION", str(row.get("confidence") or "needs review"), "raw_pcm"

    def refresh_audio_candidate_tables(self, *, select_best: bool = False, buckets: dict[str, list[dict[str, object]]] | None = None) -> dict[str, list[dict[str, object]]]:
        library_tree = getattr(self, "audio_library_tree", None)
        raw_tree = getattr(self, "audio_raw_tree", None)
        failed_tree = getattr(self, "audio_failed_tree", None)
        if not library_tree or not raw_tree or not failed_tree:
            return {"decoded_wavs": [], "raw_pending": [], "failed_warnings": []}
        for tree in {library_tree, raw_tree, failed_tree}:
            tree.delete(*tree.get_children())
        self.audio_wav_payloads = {}
        self.audio_raw_payloads = {}
        self.audio_failed_payloads = {}
        self.audio_library_payloads = {}
        buckets = buckets if buckets is not None else load_audio_report_sources(self._active_workspace_root())

        library_rows = []
        for row in getattr(self, "audio_library_manual_rows", []):
            path = Path(str(row.get("payload_path") or row.get("source_path") or ""))
            meta = self._audio_wav_metadata(path) if path.is_file() and path.suffix.lower() == ".wav" else {"duration": row.get("duration") or row.get("duration_estimate") or "—", "sample_rate": row.get("sample_rate") or "—"}
            output = row.get("output_path") or row.get("raw_path") or row.get("payload_path") or row.get("source_path") or "—"
            library_rows.append(("manual", row, path, "Manual", str(row.get("detected_format") or row.get("format") or "audio candidate").upper(), str(row.get("confidence") or "manual"), meta, output, "raw_pcm"))
        for bucket_name in ("decoded_wavs", "raw_pending", "failed_warnings"):
            for row in buckets[bucket_name]:
                path = Path(row["payload_path"]) if row.get("payload_path") else Path(row.get("source_path") or "")
                meta = self._audio_wav_metadata(path) if path.is_file() and path.suffix.lower() == ".wav" else {"duration": row.get("duration") or "—", "sample_rate": row.get("sample_rate") or "—"}
                provenance, confidence, tag = self._audio_library_provenance(row, bucket_name)
                source = row.get("bank_name") or row.get("source_path") or row.get("raw_path") or "—"
                output = row.get("output_path") or row.get("payload_path") or row.get("raw_path") or "—"
                library_rows.append((bucket_name, row, path, source, provenance, confidence, meta, output, tag))

        def insert_library_chunk(start: int = 0) -> None:
            for item in library_rows[start:start + 150]:
                bucket_name, row, path, source, provenance, confidence, meta, output, tag = item
                iid = library_tree.insert("", "end", text=row.get("name") or "audio entry", values=(source, provenance, confidence, meta["duration"], meta["sample_rate"], output), tags=(tag,))
                payload = _audio_gui_payload(row, path)
                payload["library_bucket"] = bucket_name
                payload["library_provenance"] = provenance
                self.audio_library_payloads[iid] = payload
                if bucket_name == "decoded_wavs":
                    self.audio_wav_payloads[iid] = payload
            if start + 150 < len(library_rows):
                self.after(1, lambda: insert_library_chunk(start + 150))
        insert_library_chunk()

        if not library_rows:
            folder = self._audio_decoded_wav_folder()
            iid = library_tree.insert("", "end", text="No audio library entries found", values=("—", "RAW PCM INTERPRETATION", "pending", "—", "—", str(folder)), tags=("raw_pcm",))
            self.audio_library_payloads[iid] = _audio_gui_payload({"name": "No audio library entries found", "output_path": str(folder)}, folder)

        report = self._active_workspace_root() / "reports" / "iso_audio_decode_report.json"
        warning_rows = [("binrow", row, Path(row["payload_path"]) if row.get("payload_path") else Path(row["source_path"]), self.audio_raw_payloads) for row in buckets["raw_pending"]]
        warning_rows.extend(("secrow", row, Path(row["payload_path"]) if row.get("payload_path") else report, self.audio_failed_payloads) for row in buckets["failed_warnings"])
        def insert_warning_chunk(start: int = 0) -> None:
            for tag, row, path, payloads in warning_rows[start:start + 150]:
                iid = raw_tree.insert("", "end", text=row["name"], values=(row["bank_type"], row["bank_name"], row["stream_index"], row["sample_rate"], row["loop_flag"], row["duration"], row["output_path"], row["raw_path"], row["decode_status"]), tags=(tag,))
                payloads[iid] = _audio_gui_payload(row, path)
            if start + 150 < len(warning_rows):
                self.after(1, lambda: insert_warning_chunk(start + 150))
        insert_warning_chunk()
        if not buckets["raw_pending"] and not buckets["failed_warnings"]:
            folder = self._audio_raw_folder()
            iid = raw_tree.insert("", "end", text="No pending audio warnings found", values=("—", "—", "—", "—", "—", "—", "—", str(folder), "—"), tags=("secrow",))
            self.audio_raw_payloads[iid] = _audio_gui_payload({"name": "No pending audio warnings found", "raw_path": str(folder)}, folder)
        if select_best:
            self._select_best_audio_row(buckets)
        return buckets

    def _select_best_audio_row(self, buckets: dict[str, list[dict[str, object]]]) -> None:
        choices = (
            ("decoded_wavs", getattr(self, "audio_wav_tree", None), getattr(self, "audio_wav_payloads", {})),
            ("raw_pending", getattr(self, "audio_raw_tree", None), getattr(self, "audio_raw_payloads", {})),
            ("failed_warnings", getattr(self, "audio_failed_tree", None), getattr(self, "audio_failed_payloads", {})),
        )
        preferred = choices[0] if buckets.get("decoded_wavs") else choices[1]
        for _bucket_name, tree, _payloads in choices:
            if tree:
                tree.selection_remove(tree.selection())
        tree = preferred[1]
        if not tree:
            return
        children = list(tree.get_children())
        first = next((iid for iid in children if not str(tree.item(iid, "text") or "").startswith("No ")), children[0] if children else None)
        if not first:
            return
        notebook = getattr(self, "audio_candidates_notebook", None)
        if notebook is not None:
            try:
                notebook.select(tree.master)
            except tk.TclError:
                pass
        tree.selection_set(first)
        tree.focus(first)
        tree.see(first)
        self._on_audio_tree_select(type("_AudioSelectionEvent", (), {"widget": tree})())

    def open_selected_audio_source(self) -> None:
        path = _audio_payload_existing_path(self._selected_audio_payload(), ("raw_path", "source_candidate", "extracted_path", "path", "payload_path"))
        if path and path.exists():
            self._open_path_with_platform(path)

    def open_selected_audio_output(self) -> None:
        path = _audio_payload_existing_path(self._selected_audio_payload(), ("output_path", "decoded_path", "payload_path"))
        if path and path.exists():
            self._open_path_with_platform(path if path.is_file() else path)

    def copy_selected_audio_path(self) -> None:
        path = self._selected_audio_payload_path()
        if path:
            self._copy_path_to_clipboard(path)

    def copy_selected_audio_source_path(self) -> None:
        self.copy_selected_audio_path()

    def send_selected_audio_to_research(self) -> None:
        payload = self._selected_audio_payload()
        path = _audio_payload_existing_path(payload, ("raw_path", "source_candidate", "extracted_path", "path", "payload_path", "output_path", "decoded_path"))
        if not path:
            return messagebox.showinfo("Audio Research", "Select an audio row with an existing source or output path first.")
        self.raw_audio_source.set(str(path))
        self.audio_pipeline_status.set(f"Sent audio source to Research / Raw Audio Lab: {path.name}")
        notebook = getattr(self, "audio_candidates_notebook", None)
        if notebook is not None:
            try:
                for tab_id in notebook.tabs():
                    if notebook.tab(tab_id, "text") == "Research":
                        notebook.select(tab_id)
                        break
            except tk.TclError:
                pass
        self._copy_path_to_clipboard(path)

    def run_setup_iso_asset_survey(self) -> None:
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing ISO", "Choose an ISO first.")
        workspace = self._ensure_research_workspace()
        cmd = [PY, str(TOOLS / "iso_asset_survey.py"), iso, str(workspace)]
        self.setup_survey_status.set("ISO asset survey running.")
        self._start_setup_indeterminate_progress("setup_survey_progress_bar", self.setup_survey_progress_text, "Running")

        def _done(rc: int) -> None:
            ok = rc == 0 and (workspace / "reports" / "iso_asset_survey.json").exists()
            self._stop_setup_indeterminate_progress("setup_survey_progress_bar", self.setup_survey_progress, self.setup_survey_progress_text, ok)
            self.setup_survey_status.set(
                f"ISO asset survey complete: {workspace / 'reports' / 'iso_asset_survey.txt'}"
                if ok
                else "ISO asset survey failed; see console."
            )
            self.iso_status.set(self.setup_survey_status.get())
            self.refresh_project_tree()
            self.refresh_quick_report_locator()
            self.load_ccsf_viewer_asset_library(silent=True)

        if not self._run_task(cmd, on_done=_done, label="iso asset survey"):
            self._stop_setup_indeterminate_progress("setup_survey_progress_bar", self.setup_survey_progress, self.setup_survey_progress_text, False)

    def run_iso_asset_survey(self) -> None:
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing ISO", "Choose an ISO first.")
        workspace = self._ensure_research_workspace()
        cmd = [PY, str(TOOLS / "iso_asset_survey.py"), iso, str(workspace)]
        self.iso_status.set("ISO asset survey running.")

        def _done(rc: int) -> None:
            txt = workspace / "reports" / "iso_asset_survey.txt"
            if rc != 0:
                self.iso_status.set("ISO asset survey failed; see console.")
                return
            self.iso_status.set(f"ISO asset survey complete: {txt}")
            if hasattr(self, "iso_asset_survey_text"):
                preview = txt.read_text(encoding="utf-8", errors="replace") if txt.exists() else "Survey completed; text report was not found.\n"
                self._replace_text(self.iso_asset_survey_text, preview, readonly=True)
            self.refresh_project_tree()

        self._run_task(cmd, on_done=_done, label="iso asset survey")

    def open_ccsf_results_dashboard(self) -> None:
        path = self._default_ccsf_report_path("ccsf_results_dashboard.html")
        if not path.exists():
            return messagebox.showinfo("Results dashboard", f"Dashboard not found:\n{path}")
        self._open_path_with_platform(path)

    def open_ccsf_asset_survey_dashboard(self) -> None:
        path = self._default_ccsf_report_path("asset_library_dashboard.html")
        if not path.exists():
            return messagebox.showinfo("Asset survey dashboard", f"Dashboard not found:\n{path}")
        self._open_path_with_platform(path)

    def open_selected_ccsf_preferred_file(self) -> None:
        asset = self._ccsf_selected_asset()
        if not asset:
            return messagebox.showinfo("Preferred file", "Select an asset first.")
        path = self._ccsf_resolved_preferred_path(asset)
        if not path.exists():
            return messagebox.showinfo("Preferred file", f"Preferred file not found:\n{path}")
        self._open_path_with_platform(path)

    def copy_selected_ccsf_path(self) -> None:
        asset = self._ccsf_selected_asset()
        if not asset:
            return messagebox.showinfo("Copy selected path", "Select an asset first.")
        self._copy_path_to_clipboard(self._ccsf_resolved_preferred_path(asset))

    def open_selected_ccsf_containing_folder(self) -> None:
        asset = self._ccsf_selected_asset()
        if not asset:
            return messagebox.showinfo("Open containing folder", "Select an asset first.")
        path = self._ccsf_resolved_preferred_path(asset)
        folder = path if path.is_dir() else path.parent
        if not folder.exists():
            return messagebox.showinfo("Containing folder", f"Folder not found:\n{folder}")
        self._open_folder_path(folder)

    def build_ccsf_preview_manifest(self) -> None:
        asset = self._ccsf_selected_asset()
        if not asset:
            return messagebox.showinfo("CCSF Preview Manifest", "Select an asset first.")

        source = self._ccsf_manifest_source(asset)
        generation = self.ccsf_asset_selection_generation
        self.ccsf_manifest_worker_token += 1
        token = self.ccsf_manifest_worker_token
        self.ccsf_manifest_payload = None
        self.ccsf_filter_summary.set("Building preview manifest...")
        self.ccsf_manifest_progress.set(0.0)
        self.ccsf_manifest_progress_text.set("Building")
        bar = getattr(self, "ccsf_manifest_progress_bar", None)
        if bar is not None:
            try:
                bar.configure(mode="indeterminate")
                bar.start(12)
            except tk.TclError:
                pass
        self._replace_text(self.ccsf_assets_manifest, "Building preview manifest...\n", readonly=True)

        def finish_progress(ok: bool) -> None:
            if bar is not None:
                try:
                    bar.stop()
                    bar.configure(mode="determinate", maximum=100.0)
                except tk.TclError:
                    pass
            self.ccsf_manifest_progress.set(100.0 if ok else 0.0)
            self.ccsf_manifest_progress_text.set("Complete" if ok else "Failed")

        def apply_result(manifest: dict) -> None:
            if token != self.ccsf_manifest_worker_token or generation != self.ccsf_asset_selection_generation:
                return
            current_asset = self._ccsf_selected_asset()
            if current_asset is not asset:
                return
            self.ccsf_manifest_payload = manifest
            self._replace_text(self.ccsf_assets_manifest, format_ccsf_preview_manifest_text(manifest), readonly=True)
            self._replace_text(self.ccsf_assets_details, self._format_ccsf_asset_details(asset, manifest), readonly=True)
            finish_progress(True)
            self.ccsf_filter_summary.set("Preview manifest built.")

        def apply_error(exc: Exception) -> None:
            if token != self.ccsf_manifest_worker_token or generation != self.ccsf_asset_selection_generation:
                return
            finish_progress(False)
            self.ccsf_filter_summary.set("Preview manifest build failed.")
            self._replace_text(self.ccsf_assets_manifest, f"Manifest build failed:\n{exc}\n", readonly=True)
            messagebox.showerror("CCSF Preview Manifest", f"Manifest build failed:\n{exc}")

        def worker() -> None:
            try:
                manifest = build_ccsf_preview_manifest(source)
            except Exception as exc:
                self.after(0, lambda exc=exc: apply_error(exc))
            else:
                self.after(0, lambda manifest=manifest: apply_result(manifest))

        threading.Thread(target=worker, daemon=True, name="ccsf-preview-manifest").start()

    def copy_ccsf_manifest(self) -> None:
        text = self.ccsf_assets_manifest.get("1.0", "end-1c")
        if not text.strip():
            if self.ccsf_manifest_payload:
                text = json.dumps(self.ccsf_manifest_payload, indent=2)
            else:
                return messagebox.showinfo("Copy Manifest", "No manifest text to copy.")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.resource_preview_message.set("Copied CCSF manifest to clipboard.")

    def save_ccsf_manifest(self) -> None:
        if not self.ccsf_manifest_payload:
            asset = self._ccsf_selected_asset()
            if asset:
                self.ccsf_manifest_payload = build_ccsf_preview_manifest(self._ccsf_manifest_source(asset))
            else:
                return messagebox.showinfo("Save Manifest", "Select an asset first.")
        reports = self._active_workspace_root() / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        name = self.ccsf_manifest_payload.get("asset_name") or "ccsf_asset"
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("_") or "ccsf_asset"
        out = filedialog.asksaveasfilename(
            title="Save CCSF preview manifest as",
            initialdir=str(reports),
            initialfile=f"{safe_name}_preview_manifest.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if not out:
            return
        path = Path(out)
        text = format_ccsf_preview_manifest_text(self.ccsf_manifest_payload) if path.suffix.lower() == ".txt" else json.dumps(self.ccsf_manifest_payload, indent=2)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        messagebox.showinfo("Save Manifest", f"Wrote:\n{path}")

    def preview_ccsf_asset(self) -> None:
        asset = self._ccsf_selected_asset()
        if not asset:
            return messagebox.showinfo("Preview Asset", "Select an asset first.")
        manifest = build_ccsf_preview_manifest(self._ccsf_manifest_source(asset))
        self.ccsf_manifest_payload = manifest
        pair = (manifest.get("texture_clt_pairs") or [{}])[0] if manifest.get("texture_clt_pairs") else {}
        renderer_status = manifest.get("renderer_status") or {}
        pending = [f"{key}: {value}" for key, value in renderer_status.items() if value in {"missing", "pending"}]
        lines = [
            "CCSF Asset Preview Plan (metadata-only; no fake rendering)",
            f"Asset: {manifest.get('asset_name') or '(unnamed)'}",
            f"Main model candidate: {(manifest.get('main_model_candidates') or ['none'])[0]}",
            f"TEX/CLT pair: texture={pair.get('texture', 'none')} clt={pair.get('clt', 'none')}",
            f"Animation candidate: {(manifest.get('animation_candidates') or ['none'])[0]}",
            "Missing/pending decoder stages:",
            *(f"  - {item}" for item in (pending or ["none"])),
            f"can_attempt_static_preview: {manifest.get('can_attempt_static_preview')}",
            f"can_attempt_animated_preview: {manifest.get('can_attempt_animated_preview')}",
        ]
        self._replace_text(self.ccsf_assets_manifest, "\n".join(lines) + "\n", readonly=True)

    def _ccsf_manifest_draft(self, index: dict) -> str:
        lines = ["# CCSF Asset Manifest Draft", "assets:"]
        for asset in index.get("assets") or []:
            lines.extend([
                f"  - name: {asset.get('name')}",
                f"    file: {asset.get('relative_file') or asset.get('file')}",
                f"    type: {asset.get('type')}",
                f"    variant: {asset.get('variant') or ''}",
                f"    readiness: {asset.get('readiness')}",
            ])
        return "\n".join(lines) + "\n"

    def _build_workbench_console(self) -> None:
        self.console_wrap = ttk.Frame(self, height=48)
        self.console_wrap.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        self.console_wrap.grid_propagate(False)
        self.console_wrap.grid_rowconfigure(1, weight=1)
        self.console_wrap.grid_columnconfigure(0, weight=1)
        top = ttk.Frame(self.console_wrap)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        top.grid_columnconfigure(1, weight=1)
        ttk.Label(top, text="Console", font=self.FONT_H2).grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.run_status, foreground=self._theme.get("muted", "#9fb3a7")).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(top, text="Console mode").grid(row=0, column=2, padx=(8, 4))
        ttk.Combobox(top, textvariable=self.console_mode, values=("Normal", "Verbose", "Debug"), state="readonly", width=9).grid(row=0, column=3)
        self.console_toggle_button = ttk.Button(top, text="Show Console", command=self._toggle_workbench_console)
        self.console_toggle_button.grid(row=0, column=4, padx=(8, 0))
        ttk.Button(top, text="Clear", command=lambda: self.console.delete("1.0", "end")).grid(row=0, column=5, padx=(8, 0))
        ttk.Button(top, text="Cancel", command=self.cancel_active_task).grid(row=0, column=6, padx=(8, 0))
        self.console = tk.Text(self.console_wrap, height=4, wrap="none", bg="#07110b", fg="#b8ffd8", insertbackground="#b8ffd8")
        self.console.grid(row=1, column=0, sticky="nsew")
        self.console_scroll = ttk.Scrollbar(self.console_wrap, orient="vertical", command=self.console.yview)
        self.console_scroll.grid(row=1, column=1, sticky="ns")
        self.console.configure(yscrollcommand=self.console_scroll.set)
        self.console_mode.trace_add("write", lambda *_args: self._sync_console_mode())
        self._sync_workbench_console_visibility()

    def _toggle_workbench_console(self) -> None:
        self.console_expanded.set(not self.console_expanded.get())
        self._sync_workbench_console_visibility()

    def _sync_workbench_console_visibility(self) -> None:
        expanded = bool(self.console_expanded.get())
        height = 140 if expanded else 48
        self.console_wrap.configure(height=height)
        self.grid_rowconfigure(2, minsize=height)
        self.console_toggle_button.configure(text="Hide Console" if expanded else "Show Console")
        if expanded:
            self.console.grid()
            self.console_scroll.grid()
        else:
            self.console.grid_remove()
            self.console_scroll.grid_remove()

    def _sync_console_mode(self) -> None:
        self._sync_iso_ccsf_details_visibility()

    def _build_text_hex_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        self.preview_tab_frames["Text / Hex"] = tab
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 0))
        for col in (1, 3, 7):
            controls.grid_columnconfigure(col, weight=1)
        ttk.Label(controls, text="Offset").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.text_hex_offset, width=12).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Label(controls, text="Length").grid(row=0, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self.text_hex_length, width=12).grid(row=0, column=3, sticky="ew", padx=(4, 8))
        ttk.Label(controls, text="Encoding").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.text_hex_encoding,
            values=("ASCII", "CP932", "UTF-8", "raw"),
            state="readonly",
            width=8,
        ).grid(row=0, column=5, sticky="ew", padx=(4, 8))
        ttk.Button(controls, text="Render", command=self.render_text_hex_tab).grid(row=0, column=6, padx=(0, 8))
        ttk.Label(controls, textvariable=self.text_hex_confidence).grid(row=0, column=7, sticky="w")
        ttk.Label(controls, text="Find").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(controls, textvariable=self.text_hex_find).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(4, 8), pady=(6, 0))
        ttk.Button(controls, text="Find Next", command=self.find_next_text_hex).grid(row=1, column=4, padx=(0, 8), pady=(6, 0))
        ttk.Checkbutton(controls, text="Show raw anyway", variable=self.text_hex_show_raw_anyway, command=self.render_text_hex_tab).grid(row=1, column=5, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(controls, text="Copy text", command=self.copy_text_hex_decoded_text).grid(row=1, column=7, sticky="w", pady=(6, 0))
        self.text_hex_output = tk.Text(tab, wrap="none", height=10, bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.text_hex_output.grid(row=1, column=0, sticky="nsew", padx=(8,0), pady=8)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.text_hex_output.yview)
        scroll.grid(row=1, column=1, sticky="ns", padx=(0,8), pady=8)
        self.text_hex_output.configure(yscrollcommand=scroll.set)
        self.preview_tabs["Text / Hex"] = self.text_hex_output
        self.nb.add(tab, text="Text / Hex")

    def _build_iso_3d_preview_tab(self, notebook: ttk.Notebook | None = None, title: str = "ISO 3D Preview") -> None:
        notebook = notebook or self.nb
        tab = ttk.Frame(notebook)
        tab.grid_rowconfigure(4, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        self.preview_tab_frames["ISO 3D Preview"] = tab

        paths = ttk.Labelframe(tab, text="ISO 3D Preview")
        paths.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        paths.grid_columnconfigure(0, weight=1)
        self._build_path_row(paths, "ISO path", self.iso_path, browse_command=self.pick_iso, open_command=lambda: self._open_existing_variable_path(self.iso_path)).grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 3))
        self._build_path_row(paths, "ISO index path", self.iso_index_path, browse_command=self.pick_iso_index_out, open_command=lambda: self._open_existing_variable_path(self.iso_index_path)).grid(row=1, column=0, sticky="ew", padx=8, pady=(3, 6))

        controls = ActionSection(
            tab,
            "ISO Survey",
            "Build or load the ISO index, survey candidate assets, and extract selected files for preview without changing source data.",
            status_variable=self.iso_status,
            progress_variable=self.iso_progress,
            progress_text_variable=self.iso_progress_text,
            include_progress=True,
            output_buttons=[{"text": "Open Extracted Folder", "command": self.open_iso_3d_extracted_folder}],
            columns_at_width=[(900, 4), (620, 2)],
        )
        controls.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self.iso_progress_bar = controls.progress_bar
        buttons = [
            ("Build/Refresh ISO Index", self.build_iso_index),
            ("Load ISO Index", self.load_iso_index),
            ("Extract for Preview", self.extract_iso_3d_selected_for_preview),
            ("Preview 3D", self.preview_iso_3d_selected),
            ("Open Text/Hex", self.open_iso_3d_selected_text_hex),
            ("Scan Inside Container", self.scan_iso_3d_selected_container),
            ("Extract Embedded Candidate", self.extract_iso_3d_embedded_selected),
            ("Preview Embedded Candidate", self.preview_iso_3d_embedded_selected),
        ]
        for text, cmd in buttons:
            controls.add_button(text=text, command=cmd)

        filters = ttk.Frame(tab)
        filters.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        for col in (1, 3, 5, 7):
            filters.grid_columnconfigure(col, weight=1)
        ttk.Label(filters, text="Search").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.iso_3d_search).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Label(filters, text="Candidate type").grid(row=0, column=2, sticky="w")
        ttk.Combobox(filters, textvariable=self.iso_3d_type_filter, values=("(all)", "model", "container_candidate", "cutscene_video_candidate", "audio_archive_candidate", "executable", "unknown_candidate", "unknown", "non_model"), state="readonly", width=18).grid(row=0, column=3, sticky="ew", padx=(4, 8))
        ttk.Label(filters, text="Min size").grid(row=0, column=4, sticky="w")
        ttk.Entry(filters, textvariable=self.iso_3d_min_size, width=10).grid(row=0, column=5, sticky="ew", padx=(4, 8))
        ttk.Label(filters, text="Max size").grid(row=0, column=6, sticky="w")
        ttk.Entry(filters, textvariable=self.iso_3d_max_size, width=10).grid(row=0, column=7, sticky="ew", padx=(4, 8))
        ttk.Checkbutton(filters, text="Show low-confidence candidates", variable=self.iso_3d_show_low_confidence, command=self.refresh_iso_3d_candidates).grid(row=0, column=8, sticky="w")
        for var in (self.iso_3d_search, self.iso_3d_type_filter, self.iso_3d_min_size, self.iso_3d_max_size):
            var.trace_add("write", lambda *_: self.refresh_iso_3d_candidates())

        ccsf = ttk.Labelframe(tab, text="CCSF asset structure parse/export")
        ccsf.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
        ccsf.grid_columnconfigure(0, weight=1)
        self._build_path_row(
            ccsf,
            "Extracted asset file",
            self.ccsf_model_asset_path,
            browse_command=self.pick_ccsf_model_asset_file,
            open_command=lambda: self._open_existing_variable_path(self.ccsf_model_asset_path),
            browse_text="Choose file",
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 3))
        model_buttons = ttk.Frame(ccsf)
        model_buttons.grid(row=1, column=0, sticky="ew", padx=8, pady=(3, 6))
        for text, command in (
            ("Build Preview Manifest", self.build_ccsf_model_preview_manifest),
            ("Parse CCS Structure", self.run_ccsf_model_decoder),
            ("Open Model Output Folder", self.open_ccsf_model_output_folder),
        ):
            ttk.Button(model_buttons, text=text, command=command).pack(side="left", padx=(0, 6))
        self.ccsf_model_open_obj_button = ttk.Button(model_buttons, text="Export Confirmed OBJ", command=self.open_ccsf_model_generated_obj, state="disabled")
        self.ccsf_model_open_obj_button.pack(side="left", padx=(0, 6))
        ttk.Label(ccsf, textvariable=self.ccsf_model_decode_status).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 6))

        split = ttk.Panedwindow(tab, orient="vertical")
        split.grid(row=4, column=0, sticky="nsew", padx=8, pady=(4, 8))
        table_frame = ttk.Frame(split)
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        columns = ("score", "path", "extension", "size", "lba", "reason", "extracted", "preview")
        self.iso_3d_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)
        headings = {"score": "score/confidence", "path": "path", "extension": "extension", "size": "size", "lba": "LBA", "reason": "reason", "extracted": "extracted yes/no", "preview": "preview status"}
        widths = {"score": 120, "path": 360, "extension": 80, "size": 90, "lba": 80, "reason": 320, "extracted": 120, "preview": 140}
        for col in columns:
            self.iso_3d_tree.heading(col, text=headings[col])
            self.iso_3d_tree.column(col, width=widths[col], stretch=(col in {"path", "reason"}))
        self.iso_3d_tree.grid(row=0, column=0, sticky="nsew")
        iso_3d_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.iso_3d_tree.yview)
        iso_3d_scroll.grid(row=0, column=1, sticky="ns")
        self.iso_3d_tree.configure(yscrollcommand=iso_3d_scroll.set)
        self.iso_3d_tree.bind("<<TreeviewSelect>>", self.on_iso_3d_candidate_selected)
        split.add(table_frame, weight=3)

        embedded_frame = ttk.Labelframe(split, text="Embedded candidates inside selected container")
        embedded_frame.grid_rowconfigure(0, weight=1)
        embedded_frame.grid_columnconfigure(0, weight=1)
        embedded_columns = ("offset", "type", "magic", "nearby", "role", "extracted", "preview")
        self.iso_3d_embedded_tree = ttk.Treeview(embedded_frame, columns=embedded_columns, show="headings", height=6)
        embedded_headings = {"offset": "offset", "type": "type", "magic": "magic", "nearby": "nearby strings", "role": "likely role", "extracted": "extracted yes/no", "preview": "preview status"}
        embedded_widths = {"offset": 100, "type": 130, "magic": 120, "nearby": 360, "role": 180, "extracted": 120, "preview": 160}
        for col in embedded_columns:
            self.iso_3d_embedded_tree.heading(col, text=embedded_headings[col])
            self.iso_3d_embedded_tree.column(col, width=embedded_widths[col], stretch=(col in {"nearby", "role"}))
        self.iso_3d_embedded_tree.grid(row=0, column=0, sticky="nsew")
        embedded_scroll = ttk.Scrollbar(embedded_frame, orient="vertical", command=self.iso_3d_embedded_tree.yview)
        embedded_scroll.grid(row=0, column=1, sticky="ns")
        self.iso_3d_embedded_tree.configure(yscrollcommand=embedded_scroll.set)
        self.iso_3d_embedded_tree.bind("<<TreeviewSelect>>", self.on_iso_3d_embedded_candidate_selected)
        split.add(embedded_frame, weight=2)

        detail_frame = ttk.Frame(split)
        detail_frame.grid_rowconfigure(0, weight=1)
        detail_frame.grid_columnconfigure(0, weight=1)
        self.iso_3d_detail = tk.Text(detail_frame, wrap="word", height=8, bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.iso_3d_detail.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(detail_frame, orient="vertical", command=self.iso_3d_detail.yview).grid(row=0, column=1, sticky="ns")
        split.add(detail_frame, weight=1)
        self._replace_text(self.iso_3d_detail, "Load an ISO index to list 3D model candidates.\n", readonly=True)
        self.preview_tabs["ISO 3D Preview"] = self.iso_3d_detail
        notebook.add(tab, text=title)

    def _ccsf_model_selected_asset_file(self) -> Path | None:
        raw = self.ccsf_model_asset_path.get().strip()
        if not raw:
            messagebox.showinfo("CCSF model decode", "Choose an extracted asset file first.")
            return None
        path = Path(raw).expanduser()
        if not path.exists() or not path.is_file():
            messagebox.showinfo("CCSF model decode", f"Asset file not found:\n{path}")
            return None
        return path

    def pick_ccsf_model_asset_file(self) -> None:
        initial = self.ccsf_model_asset_path.get().strip() or self.ccsf_selected_asset_path.get().strip() or str(self._iso_ccsf_workspace() / "extracted_ccs")
        path = filedialog.askopenfilename(
            title="Choose extracted CCSF asset file",
            initialdir=str(Path(initial).expanduser().parent if Path(initial).expanduser().suffix else Path(initial).expanduser()),
            filetypes=[("CCSF / CCS assets", "*.ccs *.ccsf *.bin *.dat"), ("All files", "*.*")],
        )
        if path:
            self.ccsf_model_asset_path.set(path)
            self.ccsf_model_decode_obj_paths = []
            self.ccsf_model_decode_report_path = None
            self.ccsf_model_decode_status.set("Asset selected. Build a manifest or parse CCS Structure when ready.")
            if hasattr(self, "ccsf_model_open_obj_button"):
                self.ccsf_model_open_obj_button.configure(state="disabled")
            if hasattr(self, "ccsf_viewer_open_obj_button"):
                self.ccsf_viewer_open_obj_button.configure(state="disabled")

    def build_ccsf_model_preview_manifest(self) -> None:
        asset_file = self._ccsf_model_selected_asset_file()
        if not asset_file:
            return
        self.ccsf_model_decode_status.set("Building CCSF preview manifest…")
        self._replace_text(self._ccsf_model_report_text_widget(), f"Building preview manifest for:\n{asset_file}\n", readonly=True)

        def worker() -> None:
            try:
                manifest = build_ccsf_preview_manifest(asset_file)
                text = format_ccsf_preview_manifest_text(manifest)
            except Exception as exc:
                self.after(0, lambda exc=exc: self._finish_ccsf_model_manifest_error(exc))
            else:
                self.after(0, lambda manifest=manifest, text=text: self._finish_ccsf_model_manifest(manifest, text))

        threading.Thread(target=worker, daemon=True, name="ccsf-model-manifest").start()

    def _finish_ccsf_model_manifest(self, manifest: dict, text: str) -> None:
        self.ccsf_manifest_payload = manifest
        self.ccsf_model_decode_status.set("Preview manifest built. Decode was not run automatically.")
        self._replace_text(self._ccsf_model_report_text_widget(), text, readonly=True)

    def _finish_ccsf_model_manifest_error(self, exc: Exception) -> None:
        self.ccsf_model_decode_status.set("Preview manifest build failed.")
        self._replace_text(self._ccsf_model_report_text_widget(), f"CCSF preview manifest failed:\n{exc}\n", readonly=True)
        messagebox.showerror("CCSF preview manifest", f"Manifest build failed:\n{exc}")

    def _ccsf_model_output_dir_for(self, asset_file: Path) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", asset_file.stem).strip("_") or "asset"
        return self._active_workspace_root() / "model_previews" / safe_name

    def _build_ccsf_model_decode_command(self, asset_file: Path) -> tuple[list[str], Path, Path, Path]:
        workspace = self._active_workspace_root()
        return build_ccsf_model_decode_command(asset_file, workspace)

    def _format_ccsf_selected_model_report(self, rec: dict, report: dict) -> str:
        lines = [
            "Selected Model/Submodel Parse Details",
            "====================================",
            f"Object: {rec.get('object_name') or rec.get('object_id')}",
            f"Type: {rec.get('type_name')} ({rec.get('parse_status')})",
            f"Record offset: 0x{int(rec.get('offset') or 0):X}",
            f"Payload bounds: {self._ccsf_record_bounds_text(rec) or 'unknown'}",
            f"Raw size field: {rec.get('raw_size_field')}",
            f"Calculated payload bytes: {rec.get('calculated_payload_size')}",
        ]
        model = rec.get("model") if isinstance(rec.get("model"), dict) else {}
        if model:
            lines.extend([
                "",
                "Model header:",
                f"  vertex_scale: {model.get('vertex_scale')}",
                f"  model_type: 0x{int(model.get('model_type') or 0):04X} ({model.get('model_type_name')})",
                f"  submodel_count: {model.get('submodel_count')}",
                f"  draw_flags: {model.get('draw_flags')}",
                f"  unk_flags: {model.get('unk_flags')}",
            ])
            for sub in model.get("submodels") or []:
                lines.extend([
                    "",
                    f"Submodel {sub.get('index')}:",
                    f"  parent_id: {sub.get('parent_id')}",
                    f"  mat_tex_id: {sub.get('mat_tex_id')}",
                    f"  vertex_count field: {sub.get('vertex_count')}",
                    f"  decoded_vertex_count: {sub.get('decoded_vertex_count')}",
                    f"  triangle_count: {sub.get('triangle_count')}",
                    f"  payload_start: 0x{int(sub.get('payload_start') or 0):X}" if sub.get("payload_start") is not None else "  payload_start: unknown",
                    f"  payload_end: 0x{int(sub.get('payload_end') or 0):X}" if sub.get("payload_end") is not None else "  payload_end: unknown",
                    f"  parser_mode: {sub.get('parser_mode')}",
                ])
                if sub.get("expected_fixture_count") is not None or sub.get("parsed_fixture_count") is not None:
                    lines.append(f"  expected-vs-parsed fixtures: {sub.get('expected_fixture_count')} vs {sub.get('parsed_fixture_count')}")
                for warning in sub.get("warnings") or []:
                    lines.append(f"  warning: {warning}")
        lines.extend(["", "Warnings:"])
        warnings = list(rec.get("warnings") or []) + list((model or {}).get("warnings") or []) + list(report.get("warnings") or [])
        lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- none")
        lines.extend(["", "Errors:"])
        errors = list(rec.get("errors") or []) + list(report.get("errors") or [])
        lines.extend(f"- {error}" for error in errors) if errors else lines.append("- none")
        return "\n".join(lines) + "\n"

    def run_ccsf_model_decoder(self) -> None:
        asset_file = self._ccsf_model_selected_asset_file()
        if not asset_file:
            return
        _cmd, out_dir, report, text_report = self._build_ccsf_model_decode_command(asset_file)
        out_dir.mkdir(parents=True, exist_ok=True)
        report.parent.mkdir(parents=True, exist_ok=True)
        self.ccsf_model_decode_output_dir = out_dir
        self.ccsf_model_decode_report_path = report
        self.ccsf_structure_report = None
        self.ccsf_model_decode_obj_paths = []
        self.ccsf_viewer_current_mesh = None
        self._populate_ccsf_structure_tree(None)
        if hasattr(self, "ccsf_model_open_obj_button"):
            self.ccsf_model_open_obj_button.configure(state="disabled")
        if hasattr(self, "ccsf_viewer_open_obj_button"):
            self.ccsf_viewer_open_obj_button.configure(state="disabled")
        if hasattr(self, "ccsf_viewer_obj_list"):
            self.ccsf_viewer_obj_list.delete(0, "end")
        if hasattr(self, "ccsf_viewer_obj_summary"):
            self.ccsf_viewer_obj_summary.set("Source: No geometry")
        if hasattr(self, "ccsf_viewer_report_path"):
            self.ccsf_viewer_report_path.set("Report path: none")
        self._show_ccsf_viewer_preview_message("Source: No geometry\n\nParsing CCS Structure…")
        self.ccsf_model_decode_status.set("Parsing CCS Structure…")
        self._replace_text(self._ccsf_model_report_text_widget(), f"Parsing CCS Structure for:\n{asset_file}\n\nOutput folder:\n{out_dir}\n", readonly=True)
        try:
            decoded = ccsf_structure_decoder.decode(asset_file)
            report_data = ccsf_structure_decoder.report_to_dict(decoded)
            report.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
            text_report.write_text(ccsf_structure_decoder.render_text(decoded) + "\n", encoding="utf-8")
        except Exception as exc:
            self.ccsf_model_decode_status.set(f"Parse failed: {exc}")
            self._replace_text(self._ccsf_model_report_text_widget(), f"CCS Structure parse failed:\n{exc}\n", readonly=True)
            self._show_ccsf_viewer_preview_message("Source: No geometry\n\nNo structurally confirmed mesh decoded.")
            return
        self._finish_ccsf_model_decode(0, report, text_report, asset_file)

    def _finish_ccsf_model_decode(self, rc: int, report_path: Path, text_report_path: Path, asset_file: Path) -> None:
        report: dict = {}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception as exc:
                report = {"warnings": [f"Could not read JSON report: {exc}"]}
        if not report:
            try:
                report = ccsf_structure_decoder.report_to_dict(ccsf_structure_decoder.decode(asset_file))
            except Exception as exc:
                report = {"warnings": [f"Could not run in-memory structure decoder fallback: {exc}"]}
        self.ccsf_structure_report = report
        self._populate_ccsf_structure_tree(report)
        obj_paths = [Path(str(path)) for path in (report.get("objs_written") or []) if Path(str(path)).is_file()]
        self.ccsf_model_decode_obj_paths = obj_paths
        open_obj_state = "normal" if obj_paths else "disabled"
        if hasattr(self, "ccsf_model_open_obj_button"):
            self.ccsf_model_open_obj_button.configure(state=open_obj_state)
        if hasattr(self, "ccsf_viewer_open_obj_button"):
            self.ccsf_viewer_open_obj_button.configure(state=open_obj_state)
        text = text_report_path.read_text(encoding="utf-8", errors="replace") if text_report_path.exists() else ""
        lines = [
            "CCS Structure parse completed." if rc == 0 else f"CCS Structure parse failed (exit {rc}).",
            "",
            text.strip() or "No text report was written.",
            "",
            "Generated OBJ paths:",
            *(f"- {path}" for path in obj_paths),
        ]
        if not obj_paths:
            lines.append("- none")
        warnings = report.get("warnings") or []
        if warnings:
            lines.extend(["", "Warnings:", *(f"- {warning}" for warning in warnings)])
        message = report.get("model_record_message") or ("typed model record not found" if not obj_paths else "typed model record found")
        self.ccsf_model_decode_status.set(f"Parse {'complete' if rc == 0 else 'failed'}; {message}.")
        if hasattr(self, "ccsf_viewer_report_path"):
            self.ccsf_viewer_report_path.set(f"Report path: {report_path}")
        if hasattr(self, "ccsf_viewer_obj_list"):
            self.ccsf_viewer_obj_list.delete(0, "end")
            for path in obj_paths:
                self.ccsf_viewer_obj_list.insert("end", str(path))
            if obj_paths:
                self.ccsf_viewer_obj_list.selection_set(0)
                self._load_ccsf_viewer_obj_preview(obj_paths[0])
            else:
                self._load_ccsf_viewer_structure_preview(report)
        if hasattr(self, "ccsf_viewer_obj_summary"):
            if obj_paths:
                self.ccsf_viewer_obj_summary.set(f"Source: OBJ file ({len(obj_paths)} generated)")
            elif choose_structural_preview_submodel(report):
                self.ccsf_viewer_obj_summary.set("Source: Confirmed CCSF structure")
            else:
                self.ccsf_viewer_obj_summary.set("Source: No geometry")
        self._replace_text(self._ccsf_model_report_text_widget(), "\n".join(lines) + "\n", readonly=True)
        asset = self._ccsf_viewer_selected_asset()
        if asset and hasattr(self, "ccsf_viewer_details"):
            self._replace_text(self.ccsf_viewer_details, self._format_ccsf_asset_details(asset), readonly=True)

    def _load_ccsf_viewer_structure_preview(self, report: dict) -> None:
        frame = getattr(self, "ccsf_preview_tab", None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        candidate = choose_structural_preview_submodel(report)
        model_object_name = (candidate or {}).get("model_object_name") or "structural submodel"
        try:
            mesh = mesh_from_structural_preview_submodel(candidate)
        except Exception as exc:
            self.ccsf_viewer_current_mesh = None
            ttk.Label(
                frame,
                text=(
                    "Source: CCSF structure\n"
                    f"Model: {model_object_name}\n"
                    f"Conversion exception: {type(exc).__name__}: {exc}"
                ),
                justify="left",
                ).grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
            return
        source_text = self.ccsf_model_asset_path.get().strip()
        source_path = Path(source_text).expanduser() if source_text else None
        decoded_texture_map = self._decoded_texture_pngs_for_source(source_path) if source_path else {}
        if decoded_texture_map:
            mesh.source_metadata["texture_png_paths"] = decoded_texture_map
            mesh.source_metadata["texture_source_path"] = str(source_path)
        self.ccsf_viewer_current_mesh = mesh if mesh.vertex_count and mesh.face_count else None
        if mesh.vertex_count and mesh.face_count:
            summary = (
                f"Model: {model_object_name}\n"
                f"Vertices: {mesh.vertex_count}\n"
                f"Faces: {mesh.face_count}\n"
                "Source: Confirmed CCSF structure\n"
                f"Decoded texture PNGs associated: {len(decoded_texture_map)}"
            )
            ttk.Label(frame, text=summary, justify="left", anchor="w").grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
            try:
                _mesh, viewer = create_mesh_viewer(frame, mesh)
            except Exception as exc:
                ttk.Label(
                    frame,
                    text=f"{summary}\nRendering exception: {exc}",
                    justify="left",
                ).grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
                return
            if viewer is not None:
                viewer.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
                return
        ttk.Label(
            frame,
            text=(
                "Source: No geometry\n\n"
                "No structurally confirmed mesh decoded.\n\n"
                + mesh.summary()
                + "\nTexture note: TEX/CLT resources are listed only; textured preview is not claimed until TEX/CLT pixels are decoded."
            ),
            justify="left",
        ).grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    def _show_ccsf_viewer_preview_message(self, message: str) -> None:
        frame = getattr(self, "ccsf_preview_tab", None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        ttk.Label(frame, text=message, justify="left").grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    def open_ccsf_model_generated_obj(self) -> None:
        paths = [path for path in self.ccsf_model_decode_obj_paths if path.exists()]
        if not paths:
            return messagebox.showinfo("Open generated OBJ", "No generated OBJ is available yet. Decode Selected Model first.")
        self._load_obj_3d_preview(paths[0], select=True)

    def open_ccsf_structure_report(self) -> None:
        path = self.ccsf_model_decode_report_path
        if path and path.exists():
            self._open_path_with_platform(path)
        else:
            messagebox.showinfo("Open Structure Report", "No structure report is available yet. Run Parse CCS Structure first.")

    def run_ccsf_legacy_heuristic_diagnostics(self) -> None:
        asset_file = self._ccsf_model_selected_asset_file()
        if not asset_file:
            return
        cmd, out_dir, report, text_report = self._build_ccsf_model_decode_command(asset_file)
        cmd.append("--legacy-heuristic-diagnostics")
        self.ccsf_model_decode_output_dir = out_dir
        self.ccsf_model_decode_report_path = report
        self.ccsf_model_decode_status.set("Running legacy heuristic diagnostics…")
        if hasattr(self, "ccsf_viewer_obj_summary"):
            self.ccsf_viewer_obj_summary.set("Source: Legacy heuristic diagnostics")
        self._show_ccsf_viewer_preview_message("Source: Legacy heuristic diagnostics\n\nRunning legacy heuristic diagnostics…")
        self._replace_text(self._ccsf_model_report_text_widget(), f"Running legacy heuristic diagnostics for:\n{asset_file}\n", readonly=True)
        def _done(rc: int) -> None:
            self._finish_ccsf_model_decode(rc, report, text_report, asset_file)
            if hasattr(self, "ccsf_viewer_obj_summary"):
                self.ccsf_viewer_obj_summary.set("Source: Legacy heuristic diagnostics")
        if not self._run_task(cmd, on_done=_done, label="Legacy Heuristic Diagnostics"):
            self.ccsf_model_decode_status.set("Legacy Heuristic Diagnostics did not start; another task is active.")

    def open_ccsf_model_output_folder(self) -> None:
        folder = self.ccsf_model_decode_output_dir
        if folder is None:
            raw = self.ccsf_model_asset_path.get().strip()
            folder = self._ccsf_model_output_dir_for(Path(raw).expanduser()) if raw else self._active_workspace_root() / "model_previews"
        self._open_folder_path(folder)

    def _build_root_town_tab(self, tab: ttk.Frame) -> None:
        tab.grid_rowconfigure(3, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        intro = (
            "Structured Root Town metadata for town04/town04d/town05, shop families, "
            "merchant/gate/light markers, and sky/background identifiers. "
            "Use Generate Summary to write workspace/reports/root_town_summary.*."
        )
        self._muted_help(tab, intro, row=0)
        self.root_town_source_text = tk.StringVar(value="Source: built-in metadata (no root_town_summary report discovered)")
        ttk.Label(tab, textvariable=self.root_town_source_text, font=self._font(10, "bold")).grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 0))
        self._build_root_town_proof_panel(tab).grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 0))
        columns = ("family", "relationship", "appearance", "offset", "confidence", "crosslink")
        self.root_town_tree = ttk.Treeview(tab, columns=columns, show="tree headings", height=14)
        self.root_town_tree.heading("#0", text="Identifier")
        headings = {
            "family": "Family",
            "relationship": "Object / model / position relationship",
            "appearance": "File/member appearance",
            "offset": "Offset",
            "confidence": "Confidence",
            "crosslink": "Workbook/client crosslink",
        }
        for col, label in headings.items():
            self.root_town_tree.heading(col, text=label)
        self.root_town_tree.column("#0", width=145)
        self.root_town_tree.column("family", width=115, stretch=False)
        self.root_town_tree.column("relationship", width=260)
        self.root_town_tree.column("appearance", width=190)
        self.root_town_tree.column("offset", width=90, stretch=False)
        self.root_town_tree.column("confidence", width=105, stretch=False)
        self.root_town_tree.column("crosslink", width=175)
        self.root_town_tree.grid(row=3, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.root_town_tree.yview)
        scroll.grid(row=3, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.root_town_tree.configure(yscrollcommand=scroll.set)
        self.root_town_tree.bind("<<TreeviewSelect>>", self.on_root_town_select)
        actions, _ = self._wrapped_button_row(
            tab,
            [
                {"text": "Copy Identifier", "command": self.copy_root_town_identifier},
                {"text": "Search Reports", "command": self.search_root_town_reports},
                {"text": "Add to Research Bundle", "command": self.add_root_town_to_research_bundle},
                {"text": "Add to Patch Plan", "command": self.add_root_town_to_patch_plan},
                {"text": "Generate Summary", "command": self.generate_root_town_summary_from_tab},
                {"text": "Refresh", "command": self.refresh_root_town_tab},
            ],
            columns_at_width=[(900, 5), (640, 3)],
        )
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        detail_frame = ttk.Frame(tab)
        detail_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        detail_frame.grid_rowconfigure(0, weight=1)
        detail_frame.grid_columnconfigure(0, weight=1)
        self.root_town_detail = tk.Text(
            detail_frame,
            height=8,
            wrap="word",
            bg=self._theme["text_bg"],
            fg=self._theme["text_fg"],
            insertbackground=self._theme["text_fg"],
        )
        self.root_town_detail.grid(row=0, column=0, sticky="ew")
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.root_town_detail.yview)
        detail_scroll.grid(row=0, column=1, sticky="ns")
        self.root_town_detail.configure(yscrollcommand=detail_scroll.set)
        self.refresh_root_town_tab()

    def _root_town_proof_rows(self) -> list[dict[str, object]]:
        return [
            {
                "label": target["display_id"],
                "display_id": target["display_id"],
                "copy_search_id": target["copy_search_id"],
                "identifiers": list(target["identifiers"]),
                "role": target["family_label"],
                "family_label": target["family_label"],
                "confidence": target["confidence"],
                "category": target["category"],
            }
            for target in ROOT_TOWN_PROOF_TARGETS
        ]

    def _build_root_town_proof_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        panel = ttk.LabelFrame(parent, text="Root Town proof dashboard (read-only research)")
        panel.grid_columnconfigure(0, weight=1)
        ttk.Label(
            panel,
            text=(
                "Pinned target: CCSFtown04 / town04.cmp. Rows below explain known identifiers "
                "and derive ISO search terms; no inventory or price data is assumed."
            ),
            wraplength=1050,
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 4))

        outer = ttk.Frame(panel)
        outer.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        outer.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(outer, height=210, highlightthickness=1, highlightbackground=self._theme.get("border", "#999999"))
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="ew")
        scroll.grid(row=0, column=1, sticky="ns")

        def _configure_inner(_evt=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _configure_canvas(evt) -> None:
            canvas.itemconfigure(inner_id, width=evt.width)

        inner.bind("<Configure>", _configure_inner)
        canvas.bind("<Configure>", _configure_canvas)
        self.root_town_proof_payloads = []
        for idx, item in enumerate(self._root_town_proof_rows()):
            self._add_root_town_proof_card(inner, item, idx)
        return panel

    def _root_town_proof_payload(self, item: dict[str, object]) -> dict[str, object]:
        identifiers = [str(v) for v in item.get("identifiers", []) if str(v).strip()]
        explanations = {identifier: explain_identifier(identifier) for identifier in identifiers}
        terms: list[str] = []
        for identifier in [str(item.get("copy_search_id") or "").strip(), *identifiers]:
            if not identifier:
                continue
            for term in derive_family_search_terms(identifier):
                if term not in terms:
                    terms.append(term)
        return {**item, "identifiers": identifiers, "explanations": explanations, "terms": terms}

    def _add_root_town_proof_card(self, parent: ttk.Frame, item: dict[str, object], row: int) -> None:
        payload = self._root_town_proof_payload(item)
        self.root_town_proof_payloads.append(payload)
        frame = ttk.Frame(parent, padding=(6, 5))
        frame.grid(row=row, column=0, sticky="ew", padx=2, pady=2)
        frame.grid_columnconfigure(1, weight=1)
        label = str(payload.get("label", ""))
        role = str(payload.get("role", ""))
        confidence = str(payload.get("confidence") or "")
        category = str(payload.get("category") or "")
        identifiers = payload["identifiers"]
        explanations = payload["explanations"]
        summaries = []
        warnings = []
        for identifier in identifiers:
            explanation = explanations.get(identifier, {})
            summaries.append(f"{identifier}: {explanation.get('summary', 'No summary available')}")
            warnings.extend(str(w) for w in explanation.get("warnings", []) if w)
        terms = ", ".join(payload["terms"]) or "(none)"
        ttk.Label(frame, text=label, font=self._font(10, "bold"), width=24).grid(row=0, column=0, rowspan=2, sticky="nw")
        ttk.Label(frame, text=f"{role} ({category}, {confidence}) — {'; '.join(summaries)}", wraplength=650).grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Label(frame, text=f"Search terms: {terms}\nWarnings: {'; '.join(warnings) if warnings else 'No identifier-specific warnings.'}", wraplength=650).grid(row=1, column=1, sticky="ew", padx=(6, 6))
        buttons = ttk.Frame(frame)
        buttons.grid(row=0, column=2, rowspan=2, sticky="ne")
        ttk.Button(buttons, text="Copy ID", command=lambda p=payload: self.copy_root_town_proof_id(p)).grid(row=0, column=0, padx=2, pady=1)
        ttk.Button(buttons, text="Explain", command=lambda p=payload: self.explain_root_town_proof(p)).grid(row=0, column=1, padx=2, pady=1)
        ttk.Button(buttons, text="Search ISO", command=lambda p=payload: self.search_root_town_proof_iso(p)).grid(row=1, column=0, padx=2, pady=1)
        ttk.Button(buttons, text="Add to Patch Plan", command=lambda p=payload: self.add_root_town_to_patch_plan(p)).grid(row=1, column=1, padx=2, pady=1)

    def _root_town_proof_detail_text(self, payload: dict[str, object]) -> str:
        lines = [
            f"{payload.get('label')} — {payload.get('role')}",
            f"Canonical copy/search ID: {payload.get('copy_search_id')}",
            f"Category: {payload.get('category')}",
            f"Panel confidence: {payload.get('confidence')}",
            "",
            "This is read-only research metadata; inventory and price data are not inferred from these identifiers.",
            "",
        ]
        for identifier, explanation in payload.get("explanations", {}).items():
            lines.extend([f"Identifier: {identifier}", f"Category: {explanation.get('category')}", f"Confidence: {explanation.get('confidence')}", f"Summary: {explanation.get('summary')}"])
            notes = explanation.get("notes") or []
            warnings = explanation.get("warnings") or []
            if notes:
                lines.append("Notes: " + "; ".join(str(v) for v in notes))
            if warnings:
                lines.append("Warnings: " + "; ".join(str(v) for v in warnings))
            lines.append("")
        lines.append("Derived ISO search terms: " + (", ".join(payload.get("terms") or []) or "(none)"))
        return "\n".join(lines) + "\n"

    def copy_root_town_proof_id(self, payload: dict[str, object]) -> None:
        canonical = str(payload.get("copy_search_id") or (payload.get("identifiers") or [payload.get("label", "")])[0])
        self.clipboard_clear(); self.clipboard_append(canonical); self.update()
        self.resource_preview_message.set(f"Copied {canonical}")

    def explain_root_town_proof(self, payload: dict[str, object]) -> None:
        text = self._root_town_proof_detail_text(payload)
        if getattr(self, "root_town_detail", None):
            self._replace_text(self.root_town_detail, text, readonly=True)
        else:
            messagebox.showinfo("Root Town explanation", text)

    def _focus_iso_search_area(self) -> None:
        """Select the ISO search area when it is present in the current GUI."""
        nb = getattr(self, "nb", None)
        if nb is not None:
            tab_iso = getattr(self, "tab_iso", None)
            try:
                if tab_iso is not None:
                    nb.select(tab_iso)
                else:
                    for tab_id in nb.tabs():
                        if "iso" in str(nb.tab(tab_id, "text")).lower():
                            nb.select(tab_id)
                            break
            except Exception:
                pass
        widget = getattr(self, "iso_search_tree", None) or getattr(self, "iso_tree", None)
        if widget is not None:
            try:
                widget.focus_set()
            except Exception:
                pass

    def search_iso_for_root_town_family(self, identifier: str) -> None:
        """Derive Root Town family terms, fill ISO search, and run it when an ISO is selected."""
        raw_identifier = str(identifier or "").strip()
        identifiers = [part.strip() for part in re.split(r"\s*/\s*|[,;\n]+", raw_identifier) if part.strip()]
        if not identifiers and raw_identifier:
            identifiers = [raw_identifier]

        terms: list[str] = []
        for item in identifiers:
            for term in derive_family_search_terms(item):
                clean = str(term).strip()
                if clean and clean not in terms:
                    terms.append(clean)

        if not terms:
            return messagebox.showinfo(
                "Root Town ISO Search",
                "No derived search terms are available for this identifier.",
            )

        self.iso_search_query.set(",".join(terms[:30]))
        self._focus_iso_search_area()
        iso = self.iso_path.get().strip() if hasattr(self, "iso_path") else ""
        if not iso:
            self.iso_status.set("Choose a PS2 ISO before running the Root Town ISO search.")
            return messagebox.showinfo(
                "Root Town ISO Search",
                "Choose a PS2 ISO first, then use Search ISO again for this Root Town family.",
            )
        self.run_iso_search()

    def add_root_town_to_patch_plan(self, row: dict | None = None) -> None:
        row = row or self._selected_root_town_row()
        if not row:
            return messagebox.showinfo("Root Town", "Select a Root Town row first.")

        identifiers = [str(value).strip() for value in row.get("identifiers", []) if str(value).strip()]
        canonical = str(row.get("copy_search_id") or row.get("identifier") or row.get("label") or "").strip()
        if not canonical and identifiers:
            canonical = identifiers[0]
        primary_candidates = " ".join([canonical, *identifiers, str(row.get("display_id") or ""), str(row.get("label") or "")]).lower()
        file_text = "town04.cmp" if "ccsftown04" in primary_candidates or "town04.cmp" in primary_candidates else canonical or "root_town_proof_panel"

        state = FragmenterProjectState(
            iso_path=self.iso_path.get().strip() or None,
            area_server_root=self.project_root.get().strip() or None,
            workspace_dir=self.workspace_output_dir.get().strip() or str(WORKSPACE),
        )
        description = (
            "Root Town proof-panel research note only; no inventory data is known "
            "and no destructive patching is performed."
        )
        try:
            plan_path, action_record = add_safe_note_to_current_patch_plan(
                state,
                source="root_town_proof_panel",
                file=file_text,
                description=description,
            )
        except Exception as exc:
            return messagebox.showerror("Patch Plan", f"Could not update patch plan: {exc}")
        self._console_write(
            f"[patch-plan] Added {action_record['action_id']} to {plan_path} "
            f"from Root Town proof panel for {file_text} (research note only; no destructive patching).\n"
        )
        self.refresh_project_tree()
        messagebox.showinfo("Patch Plan", f"Added Root Town note-only research metadata {action_record['action_id']} to:\n{plan_path}")

    def add_root_town_proof_to_patch_plan(self, payload: dict[str, object]) -> None:
        self.add_root_town_to_patch_plan(payload)

    def _root_town_metadata_rows(self) -> list[dict[str, str]]:
        def row(identifier, family, relationship, appearance, offset, confidence, semantic):
            return {
                "identifier": identifier,
                "family": family,
                "relationship": relationship,
                "appearance": appearance,
                "offset": offset,
                "confidence": confidence,
                "semantic": semantic,
                "crosslink": "",
            }

        rows = [
            row("CCSFtown04 / town04.cmp", "Primary target", "CMP member containing CCSF root-town objects and model references.", "Expected in data/town.bin extracted CMP members.", "", "high", "Primary Root Town map candidate; use as the baseline for shop/marker/background correlation."),
            row("town04d.cmp / CCSFtown04d", "root town container", "Variant/day or detail CMP member paired with town04.", "Expected in data/town.bin extracted CMP members.", "", "high", "Companion Root Town candidate likely sharing positions, markers, or visual layers with town04."),
            row("town05.cmp / CCSFtown05", "town container", "Adjacent town CMP/CCSF candidate for comparison and disambiguation.", "May appear in town.bin or related town package scans.", "", "medium", "Comparison target to prevent town04-only assumptions from leaking into neighboring town metadata."),
        ]
        proof_targets_by_display_id = {str(target["display_id"]): target for target in ROOT_TOWN_PROOF_TARGETS}
        for stem in ("sr4wep1", "sr4ite1", "sr4mag1", "sr4sav1", "sr4fai1"):
            target = proof_targets_by_display_id[stem]
            label = str(target["family_label"])
            rows.append(row(stem, label, "Shop-family resource stem linking object/model assets to likely interior/service positions.", "Look for matching TEX_/MDL_/MAT_ members and path samples.", "", str(target["confidence"]), f"Semantic shop anchor for the Root Town {label}; correlate against DMY_merchant markers and client text/workbook labels."))
        rows.append(row("DMY_gate", "generic marker", "Dummy/position marker for a gate, boundary, or transition trigger.", "Expected as DMY member inside town04/town04d CCSF sections when imported.", "", "medium", "Town navigation/transition marker for locating Root Town exits or gated interactions."))
        for idx in range(1, 7):
            rows.append(row(f"DMY_merchant{idx}", "generic marker", "Dummy/position marker for merchant NPC or service interaction point.", "Expected as DMY member inside town04/town04d CCSF sections when imported.", "", "medium", "Merchant placement marker; pair with shop-family stems to identify storefront/service locations."))
        for idx in range(1, 6):
            rows.append(row(f"LGT_shop{idx:02d}", "light marker", "Light object associated with shop-front illumination or interior service space.", "Expected as LGT/light-like member or referenced symbol when imported.", "", "medium", "Shop lighting cue; helps separate functional shop clusters from generic background props."))
        for identifier, semantic in (
            ("sr4sun1", "Sun/sky lighting identifier for Root Town atmosphere."),
            ("sr4clo1 / sr4clo2", "Grouped cloud/background layer identifiers; generate explanations and search terms for both sr4clo1 and sr4clo2."),
            ("BLT_bg", "Background/blit asset bucket for town backdrop rendering."),
            ("CLT_*", "Color lookup/table family used by background or texture presentation."),
            ("TEX_*", "Texture members for Root Town objects, shops, sky, and background surfaces."),
            ("MDL_*", "Model members for Root Town geometry, props, and shop assets."),
            ("MAT_*", "Material members linking textures to models and rendered surfaces."),
        ):
            target = proof_targets_by_display_id.get(identifier)
            family = str(target["family_label"]) if target else ("sky/background" if identifier not in ("TEX_*", "MDL_*", "MAT_*") else "asset prefix")
            confidence = str(target["confidence"]) if target else "medium"
            rows.append(row(identifier, family, "Identifier/prefix relationship to render resources rather than gameplay positions.", "Search CCSF sections, asset samples, and client reports for concrete members.", "", confidence, semantic))
        return self._augment_root_town_rows(rows)

    def _augment_root_town_rows(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        highlights = self._root_town_highlights_from_scan()
        workbook_crosslinks: dict[str, object] = {}
        fragment_strings_summary = self._find_report_path("fragment_strings_summary.json")
        if fragment_strings_summary and fragment_strings_summary.exists():
            try:
                payload = json.loads(fragment_strings_summary.read_text(encoding="utf-8"))
                raw_crosslinks = payload.get("root_town_crosslinks", {})
                if isinstance(raw_crosslinks, dict):
                    workbook_crosslinks = raw_crosslinks
            except Exception:
                workbook_crosslinks = {}
        for row in rows:
            ident = row["identifier"].split(" / ", 1)[0]
            workbook_link = workbook_crosslinks.get(ident)
            if isinstance(workbook_link, dict):
                client_ids = workbook_link.get("client_ids") or []
                if client_ids:
                    row["crosslink"] = "Fragment Strings: " + ", ".join(str(client_id) for client_id in client_ids)
                    if row["confidence"] == "medium":
                        row["confidence"] = "high"
            needles = [ident.lower().replace("*", "")]
            if " / " in row["identifier"]:
                needles.append(row["identifier"].split(" / ", 1)[1].lower())
            hits = []
            offsets = []
            for hit in highlights:
                haystack = " ".join([str(hit.get("section", "")), str(hit.get("source", "")), " ".join(hit.get("samples") or [])]).lower()
                if any(needle and needle in haystack for needle in needles):
                    hits.append(f"{hit.get('source', '(source)')}:{hit.get('section', '(section)')}")
                    if hit.get("offset"):
                        offsets.append(str(hit["offset"]))
            if hits:
                scan_link = "; ".join(hits[:2])
                row["crosslink"] = f"{row['crosslink']}; {scan_link}" if row["crosslink"] else scan_link
                row["offset"] = ", ".join(offsets[:2]) if offsets else row["offset"]
                if row["confidence"] == "medium":
                    row["confidence"] = "high"
        return rows

    def _discover_root_town_summary_reports(self) -> dict[str, object]:
        matches: list[Path] = []
        for root in self._report_search_roots():
            for name in ("root_town_summary.json", "root_town_summary.txt"):
                path = root / name
                if path.exists():
                    matches.append(path)
        newest = max(matches, key=lambda path: path.stat().st_mtime) if matches else None
        json_matches = [path for path in matches if path.name == "root_town_summary.json"]
        newest_json = max(json_matches, key=lambda path: path.stat().st_mtime) if json_matches else None
        return {"matches": matches, "newest": newest, "json": newest_json}

    @staticmethod
    def _root_town_row_key(row: dict[str, object]) -> str:
        return str(row.get("identifier", "")).split(" / ", 1)[0].strip().lower()

    def _normalize_root_town_report_row(self, raw: object) -> dict[str, str] | None:
        if not isinstance(raw, dict):
            return None
        identifier = str(raw.get("identifier") or raw.get("name") or "").strip()
        if not identifier:
            return None
        return {
            "identifier": identifier,
            "family": str(raw.get("family") or raw.get("category") or "report row"),
            "relationship": str(raw.get("relationship") or raw.get("description") or raw.get("semantic") or "Discovered in root_town_summary.json."),
            "appearance": str(raw.get("appearance") or raw.get("source") or raw.get("samples") or "Reported by summary JSON."),
            "offset": str(raw.get("offset") or ""),
            "confidence": str(raw.get("confidence") or "reported"),
            "semantic": str(raw.get("semantic") or raw.get("relationship") or "Imported from root_town_summary.json."),
            "crosslink": str(raw.get("crosslink") or raw.get("workbook_crosslink") or ""),
        }

    def _root_town_rows_from_summary_json(self, path: Path | None) -> list[dict[str, str]]:
        if not path:
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        candidates: list[object] = []
        if isinstance(payload, dict):
            for key in ("rows", "metadata_rows", "dashboard_rows", "highlight_rows"):
                value = payload.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
        elif isinstance(payload, list):
            candidates.extend(payload)
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw in candidates:
            row = self._normalize_root_town_report_row(raw)
            if not row:
                continue
            key = self._root_town_row_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        return rows

    def _root_town_dashboard_rows(self) -> tuple[list[dict[str, str]], Path | None, Path | None]:
        discovered = self._discover_root_town_summary_reports()
        source = discovered.get("newest") if isinstance(discovered.get("newest"), Path) else None
        json_source = discovered.get("json") if isinstance(discovered.get("json"), Path) else None
        pinned = self._root_town_metadata_rows()
        report_rows = self._root_town_rows_from_summary_json(json_source)
        report_by_key = {self._root_town_row_key(row): row for row in report_rows}
        merged: list[dict[str, str]] = []
        pinned_keys: set[str] = set()
        for pinned_row in pinned:
            key = self._root_town_row_key(pinned_row)
            pinned_keys.add(key)
            report_row = report_by_key.get(key)
            if report_row:
                merged.append({**pinned_row, **report_row, "identifier": pinned_row["identifier"]})
            else:
                merged.append(pinned_row)
        for row in report_rows:
            if self._root_town_row_key(row) not in pinned_keys:
                merged.append(row)
        return merged, source, json_source

    def refresh_root_town_tab(self) -> None:
        tree = getattr(self, "root_town_tree", None)
        if not tree:
            return
        tree.delete(*tree.get_children())
        self.root_town_payloads = {}
        rows, source, json_source = self._root_town_dashboard_rows()
        source_label = getattr(self, "root_town_source_text", None)
        if source_label is not None:
            if source:
                suffix = f" (dashboard rows loaded from {json_source})" if json_source else " (text summary discovered; using built-in metadata)"
                source_label.set(f"Source: {source}{suffix}")
            else:
                source_label.set("Source: built-in metadata (no root_town_summary report discovered)")
        for row in rows:
            iid = tree.insert("", "end", text=row["identifier"], values=(row["family"], row["relationship"], row["appearance"], row["offset"] or "n/a", row["confidence"], row["crosslink"] or "not imported"))
            self.root_town_payloads[iid] = row
        if getattr(self, "root_town_detail", None):
            self._replace_text(self.root_town_detail, "Select a Root Town row for secondary detail exploration. Pinned mappings are visible above without selection.\n", readonly=True)

    def _selected_root_town_row(self) -> dict[str, str] | None:
        tree = getattr(self, "root_town_tree", None)
        if not tree or not tree.selection():
            return None
        return self.root_town_payloads.get(tree.selection()[0])

    def on_root_town_select(self, _evt=None) -> None:
        row = self._selected_root_town_row()
        if not row:
            return
        text = "\n".join(f"{label}: {row.get(key) or 'n/a'}" for label, key in (
            ("Identifier", "identifier"), ("Family", "family"), ("Relationship", "relationship"),
            ("Appearance", "appearance"), ("Offset", "offset"), ("Confidence", "confidence"),
            ("Semantic explanation", "semantic"), ("Workbook/client crosslink", "crosslink"),
        )) + "\n"
        self._replace_text(self.root_town_detail, text, readonly=True)

    def copy_root_town_identifier(self) -> None:
        row = self._selected_root_town_row()
        if not row:
            return messagebox.showinfo("Root Town", "Select a Root Town row first.")
        self.clipboard_clear(); self.clipboard_append(row["identifier"]); self.update()
        self.resource_preview_message.set(f"Copied {row['identifier']}")

    def search_root_town_reports(self) -> None:
        row = self._selected_root_town_row()
        if not row:
            return messagebox.showinfo("Root Town", "Select a Root Town row first.")
        needle = row["identifier"].split(" / ", 1)[0].replace("*", "").lower()
        report_roots = self._report_search_roots()
        widget = self.preview_tabs["Report"]
        self._replace_text(
            widget,
            f"Searching reports for {row['identifier']}...\n"
            f"Per-file scan cap: {self._format_bytes(REPORT_SEARCH_READ_BYTES)}\n",
            readonly=False,
        )
        self.nb.select(widget.master)
        token = object()
        self._root_town_search_token = token
        q: "queue.Queue[str | tuple[str, list[str]]]" = queue.Queue()

        def worker() -> None:
            matches: list[str] = []
            paths = []
            seen_paths: set[str] = set()
            for reports in report_roots:
                if not reports.exists():
                    continue
                for candidate in sorted(reports.glob("*")):
                    key = str(candidate)
                    if candidate.is_file() and key not in seen_paths:
                        seen_paths.add(key)
                        paths.append(candidate)
            searchable = [p for p in paths if p.suffix.lower() in {".txt", ".json", ".csv", ".md"}]
            total = len(searchable)
            for idx, path in enumerate(searchable, 1):
                try:
                    with path.open("rb") as fh:
                        data = fh.read(REPORT_SEARCH_READ_BYTES)
                except OSError as exc:
                    q.put(f"[{idx}/{total}] skipped {path.name}: {exc}\n")
                    continue
                if needle and needle in data.decode("utf-8", errors="replace").lower():
                    matches.append(str(path))
                    q.put(f"[{idx}/{total}] match: {path.name}\n")
                elif idx == 1 or idx == total or idx % 10 == 0:
                    q.put(f"[{idx}/{total}] scanned {path.name}\n")
            q.put(("done", matches))

        def poll() -> None:
            if getattr(self, "_root_town_search_token", None) is not token:
                return
            done = False
            try:
                while True:
                    item = q.get_nowait()
                    if isinstance(item, tuple):
                        _, matches = item
                        widget.insert("end", "\nReport matches for {0}\n{1}\n".format(row["identifier"], "\n".join(matches) if matches else "(none found)"))
                        done = True
                    else:
                        widget.insert("end", item)
                    widget.see("end")
            except queue.Empty:
                pass
            if done:
                try:
                    widget.configure(state="disabled")
                except tk.TclError:
                    pass
                self.resource_preview_message.set(f"Report search complete: {len(matches)} matches")
            else:
                self.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def add_root_town_to_research_bundle(self) -> None:
        row = self._selected_root_town_row()
        if not row:
            return messagebox.showinfo("Root Town", "Select a Root Town row first.")
        bundle_dir = self._selected_workspace() / "bundles"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        manifest = bundle_dir / "root_town_research_bundle.json"
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {"schema": "fragmenter.root_town_research_bundle.v1", "items": []}
        except Exception:
            payload = {"schema": "fragmenter.root_town_research_bundle.v1", "items": []}
        items = payload.setdefault("items", [])
        if not any(item.get("identifier") == row["identifier"] for item in items if isinstance(item, dict)):
            items.append({**row, "added_utc": _utc_timestamp()})
        payload["updated_utc"] = _utc_timestamp()
        manifest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        self.resource_preview_message.set(f"Added {row['identifier']} to {manifest.name}")

    def generate_root_town_summary_from_tab(self) -> None:
        txt_path, json_path = self._write_root_town_summary()
        self.refresh_expected_reports_panel()
        self._replace_text(self.preview_tabs["Report"], txt_path.read_text(encoding="utf-8", errors="replace"), readonly=True)
        self.nb.select(self.preview_tabs["Report"].master)
        self.resource_preview_message.set(f"Generated {txt_path.name} and {json_path.name}")

    def _build_advanced_research_tab(self, f: ttk.Frame) -> None:
        f.grid_columnconfigure(0, weight=1)
        self._muted_help(f, "Advanced probes and script launchers are kept here so normal users land on previews first. Report status is available from the primary Expected Reports tab. Launchers validate inputs, write into the selected workspace, and publish status in the Report tab.", row=0)
        if not self.research_launchers:
            self.research_launchers = self._research_launcher_metadata()
        card = self._card(f, "Research launchers"); card.grid(row=1, column=0, sticky="ew", padx=2, pady=8); card.grid_columnconfigure(0, weight=1)
        actions = ActionBar(card, columns_at_width=[(900,4),(640,3)]); actions.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.research_launcher_buttons = {}
        for launcher_id, launcher in self.research_launchers.items():
            button = actions.add_button(text=str(launcher["name"]), command=lambda lid=launcher_id: self.run_research_launcher(lid))
            self.research_launcher_buttons[launcher_id] = button
        launcher_tools, _ = self._wrapped_button_row(
            card,
            [
                {"text": "Copy Command", "command": self.copy_latest_launcher_command},
                {"text": "Open Output Folder", "command": self.open_latest_launcher_output_folder},
                {"text": "Open Latest Report", "command": self.open_latest_launcher_report},
                {"text": "Run Again", "command": self.run_latest_research_launcher},
            ],
            columns_at_width=[(900, 4), (640, 2)],
        )
        launcher_tools.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self._path_picker_row(card, "Inspector file", self.inspector_path, self.select_inspector_file).grid(row=2, column=0, sticky="ew", padx=8, pady=(0,8))
        extra, _ = self._wrapped_button_row(card, [{"text":"Preview selected file","command":self.preview_inspector_file},{"text":"Scan selected container","command":self.scan_inspector_container},{"text":"Extract/decompress candidate","command":self.extract_inspector_candidate},{"text":"Build ISO Index","command":self.build_iso_index},{"text":"Resolve ISO references","command":self.resolve_iso_from_selection}], columns_at_width=[(900,5),(640,3)])
        extra.grid(row=3, column=0, sticky="ew", padx=8, pady=(0,8))
        self.inspector_output = self.preview_tabs["Text / Hex"]
        self.inspector_candidate_tree = ttk.Treeview(card, columns=("offset","type","nearby"), show="headings", height=4)
        for col, heading in (("offset","Offset"),("type","Type"),("nearby","Nearby strings")):
            self.inspector_candidate_tree.heading(col, text=heading)
        self.inspector_candidate_tree.grid(row=4, column=0, sticky="ew", padx=8, pady=(0,8))

    def _build_launcher_diagnostics_tab(self, f: ttk.Frame) -> None:
        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(0, weight=1)
        controls, _ = self._wrapped_button_row(
            f,
            [
                {"text": "Refresh Diagnostics", "command": self._refresh_launcher_diagnostics},
                {"text": "Copy Latest Launcher Command", "command": self.copy_latest_launcher_command},
                {"text": "Open Latest Launcher Output Folder", "command": self.open_latest_launcher_output_folder},
                {"text": "Open Latest Launcher Report", "command": self.open_latest_launcher_report},
            ],
            columns_at_width=[(1100, 4), (760, 2)],
        )
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 0))
        self.launcher_diagnostics = tk.Text(f, height=12, wrap="none", bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.launcher_diagnostics.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=8)
        diag_scroll = ttk.Scrollbar(f, orient="vertical", command=self.launcher_diagnostics.yview)
        diag_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.launcher_diagnostics.configure(yscrollcommand=diag_scroll.set)
        for var in (self.workspace_output_dir, self.project_root, self.data_dir, self.iso_path):
            var.trace_add("write", lambda *_args: self._refresh_launcher_diagnostics())
        self._refresh_launcher_diagnostics()

    def _build_reports_tab(self, f: ttk.Frame) -> None:
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(3, weight=1)
        self.expected_reports_workspace_text = tk.StringVar(value="")
        self.expected_report_selected_path = tk.StringVar(value="")
        self.reports_preview_lines = tk.IntVar(value=80)
        ttk.Label(
            f,
            textvariable=self.expected_reports_workspace_text,
            justify="left",
            wraplength=720,
            foreground=self._theme.get("muted", "#9fb3a7"),
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        self._build_path_row(
            f,
            "Selected report path",
            self.expected_report_selected_path,
            open_command=self.open_selected_expected_report,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 4))
        self._build_reports_page_builder(f).grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._build_expected_reports_panel(f).grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        self._refresh_reports_workspace_label()
        self.workspace_output_dir.trace_add("write", lambda *_args: self._refresh_reports_workspace_label())
        self.workspace_output_dir.trace_add("write", lambda *_args: self.refresh_reports_page_builder())

    def _build_reports_page_builder(self, parent: tk.Widget) -> ttk.Frame:
        panel = self._card(parent, "Reports")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        toolbar = ttk.Frame(panel)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        ttk.Label(toolbar, text="Preview lines:").pack(side="left")
        ttk.Spinbox(toolbar, from_=1, to=1000, textvariable=self.reports_preview_lines, width=6).pack(side="left", padx=(4, 12))
        for text, command in (
            ("Refresh", self.refresh_reports_page_builder),
            ("Open Report Folder", self.open_report_folder),
            ("Open Results Dashboard", self.open_ccsf_results_dashboard),
            ("Open Asset Survey Dashboard", self.open_ccsf_asset_survey_dashboard),
            ("Open", self.open_selected_report_page_row),
            ("Open Folder", self.open_selected_report_page_folder),
            ("Copy Path", self.copy_selected_report_page_path),
            ("Preview first N lines", self.preview_selected_report_page_row),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=(0, 6))

        columns = ("exists", "size", "modified", "type", "path")
        self.reports_page_tree = ttk.Treeview(panel, columns=columns, show="tree headings", height=10)
        self.reports_page_tree.heading("#0", text="Display name")
        for col, label in (("exists", "Exists"), ("size", "Size"), ("modified", "Modified"), ("type", "Type"), ("path", "Absolute path")):
            self.reports_page_tree.heading(col, text=label)
        self.reports_page_tree.column("#0", width=230)
        self.reports_page_tree.column("exists", width=70, anchor="center", stretch=False)
        self.reports_page_tree.column("size", width=90, anchor="e", stretch=False)
        self.reports_page_tree.column("modified", width=145, stretch=False)
        self.reports_page_tree.column("type", width=70, anchor="center", stretch=False)
        self.reports_page_tree.column("path", width=420)
        self.reports_page_tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.reports_page_tree.yview)
        scroll.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 8))
        self.reports_page_tree.configure(yscrollcommand=scroll.set)
        self.reports_page_tree.bind("<<TreeviewSelect>>", self.on_reports_page_select)

        preview_frame = self._card(panel, "Preview")
        preview_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=(0, 8))
        preview_frame.grid_columnconfigure(0, weight=1)
        self.reports_page_preview = tk.Text(preview_frame, height=8, wrap="none", bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.reports_page_preview.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        preview_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.reports_page_preview.yview)
        preview_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.reports_page_preview.configure(yscrollcommand=preview_scroll.set)
        self._replace_text(self.reports_page_preview, "Select a report and use Preview first N lines. Large reports are not loaded automatically.\n", readonly=True)
        self.refresh_reports_page_builder()
        return panel

    def _refresh_reports_workspace_label(self) -> None:
        label = getattr(self, "expected_reports_workspace_text", None)
        if label:
            searched = "\n".join(f"- {root}" for root in self._report_search_roots())
            label.set(
                f"Active workspace: {self._active_workspace_root()}\n"
                "Expected report discovery searches these directories in priority order. "
                "upload_package/reports is included as a legacy/sub-workspace location for older exports; "
                "new reports are written under the active workspace unless a tool explicitly overrides them.\n"
                f"{searched}"
            )

    def refresh_reports_page_builder(self) -> None:
        tree = getattr(self, "reports_page_tree", None)
        if not tree:
            return
        tree.delete(*tree.get_children())
        self.reports_page_payloads = {}
        for row in discover_expected_report_files(self._active_workspace_root()):
            tags = ("binrow",) if row["exists"] else ("secrow",)
            iid = tree.insert(
                "",
                "end",
                text=str(row["display_name"]),
                values=(
                    "yes" if row["exists"] else "no",
                    self._format_bytes(int(row["size"])) if row["exists"] else "—",
                    row["modified"],
                    row["type"],
                    str(row["path"]),
                ),
                tags=tags,
            )
            self.reports_page_payloads[iid] = row

    def _selected_reports_page_row(self) -> dict[str, object] | None:
        tree = getattr(self, "reports_page_tree", None)
        if not tree:
            return None
        selection = tree.selection()
        return self.reports_page_payloads.get(selection[0]) if selection else None

    def on_reports_page_select(self, _evt=None) -> None:
        row = self._selected_reports_page_row()
        if not row:
            return
        path = Path(row["path"])
        self.expected_report_selected_path.set(str(path))
        status = "ready" if row["exists"] else "missing"
        self._replace_text(
            self.reports_page_preview,
            "\n".join(
                [
                    f"Report: {row['display_name']}",
                    f"Status: {status}",
                    f"Path: {path}",
                    f"Type: {row['type']}",
                    f"Size: {self._format_bytes(int(row['size'])) if row['exists'] else '—'}",
                    f"Modified: {row['modified']}",
                    "",
                    "Use Preview first N lines to read a bounded prefix without loading the full report.",
                ]
            )
            + "\n",
            readonly=True,
        )

    def open_selected_report_page_row(self) -> None:
        row = self._selected_reports_page_row()
        if not row:
            return messagebox.showinfo("Reports", "Select a report first.")
        path = Path(row["path"])
        if not path.exists():
            return messagebox.showinfo("Reports", f"Missing report:\n{path}")
        self._open_path_with_platform(path)

    def open_selected_report_page_folder(self) -> None:
        row = self._selected_reports_page_row()
        path = Path(row["path"]) if row else self._active_workspace_root() / "reports"
        folder = path if path.is_dir() else path.parent
        folder.mkdir(parents=True, exist_ok=True)
        self._open_folder_path(folder)

    def copy_selected_report_page_path(self) -> None:
        row = self._selected_reports_page_row()
        if not row:
            return messagebox.showinfo("Reports", "Select a report first.")
        self._copy_path_to_clipboard(Path(row["path"]))

    def preview_selected_report_page_row(self) -> None:
        row = self._selected_reports_page_row()
        if not row:
            return messagebox.showinfo("Reports", "Select a report first.")
        path = Path(row["path"])
        if not path.exists():
            return messagebox.showinfo("Reports", f"Missing report:\n{path}")
        try:
            line_limit = max(1, int(self.reports_preview_lines.get() or 1))
        except (tk.TclError, ValueError):
            line_limit = 80
            self.reports_preview_lines.set(line_limit)
        byte_limit = min(REPORT_INITIAL_PREVIEW_BYTES, max(4096, line_limit * 4096))
        lines: list[str] = []
        loaded = 0
        truncated = False
        try:
            with path.open("rb") as fh:
                for raw_line in fh:
                    if len(lines) >= line_limit or loaded >= byte_limit:
                        truncated = True
                        break
                    loaded += len(raw_line)
                    if loaded > byte_limit:
                        raw_line = raw_line[: max(0, len(raw_line) - (loaded - byte_limit))]
                        truncated = True
                    lines.append(raw_line.decode("utf-8", errors="replace"))
                    if truncated:
                        break
        except Exception as exc:
            self._replace_text(self.reports_page_preview, f"Could not preview report: {exc}\n", readonly=True)
            return
        header = [
            f"Preview: {path.name}",
            f"Path: {path}",
            f"Limit: first {line_limit} line(s), up to {self._format_bytes(byte_limit)}",
            "",
        ]
        if truncated:
            lines.append(f"\n... [preview truncated after {len(lines)} line(s) / {self._format_bytes(loaded)}]\n")
        self._replace_text(self.reports_page_preview, "\n".join(header) + "".join(lines), readonly=True)

    def _build_expected_reports_panel(self, parent: tk.Widget) -> ttk.Frame:
        panel = self._card(parent, "Expected Reports")
        panel.grid_columnconfigure(0, weight=1)
        self.expected_report_tree = ttk.Treeview(
            panel,
            columns=("status", "modified", "source", "tool", "inputs"),
            show="tree headings",
            height=8,
        )
        self.expected_report_tree.heading("#0", text="Report name")
        for col, text in (("status", "Status"), ("modified", "Modified"), ("source", "Source directory"), ("tool", "Generating tool"), ("inputs", "Required inputs")):
            self.expected_report_tree.heading(col, text=text)
        self.expected_report_tree.column("#0", width=210)
        self.expected_report_tree.column("status", width=82, anchor="center", stretch=False)
        self.expected_report_tree.column("modified", width=140, stretch=False)
        self.expected_report_tree.column("source", width=220)
        self.expected_report_tree.column("tool", width=180)
        self.expected_report_tree.column("inputs", width=260)
        self.expected_report_tree.grid(row=0, column=0, sticky="ew", padx=(8, 0), pady=8)
        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.expected_report_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.expected_report_tree.configure(yscrollcommand=scroll.set)
        self.expected_report_tree.bind("<<TreeviewSelect>>", self.on_expected_report_select)
        actions = ActionSection(
            panel,
            "Report Discovery / Open Actions",
            "Discover expected reports in workspace report folders, generate missing reports, open selected output, or export a research bundle.",
            status_variable=self.expected_report_selected_path,
            output_buttons=[
                {"text": "Open", "command": self.open_selected_expected_report},
                {"text": "Open folder", "command": self.open_selected_expected_report_folder},
                {"text": "Open Bundle Folder", "command": self.open_research_bundle_folder},
            ],
            columns_at_width=[(1100, 6), (780, 3)],
        )
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        for spec in [
            {"text": "Generate", "command": self.generate_selected_expected_report, "attr": "expected_report_generate_button"},
            {"text": "Show Command", "command": self.show_selected_expected_report_command},
            {"text": "Copy path", "command": self.copy_selected_expected_report_path},
            {"text": "Refresh", "command": self.refresh_expected_reports_panel},
            {"text": "Export Research Bundle", "style": "Accent.TButton", "command": self.export_research_bundle_for_chatgpt},
            {"text": "Copy Bundle Path", "command": self.copy_research_bundle_path},
        ]:
            attr = spec.pop("attr", None)
            button = actions.add_button(**spec)
            if attr:
                setattr(self, attr, button)
        bundle_status = self._card(panel, "Research Bundle Status")
        bundle_status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8)); bundle_status.grid_columnconfigure(0, weight=1)
        self.research_bundle_status = tk.Text(bundle_status, height=8, wrap="word", bg=self._theme["text_bg"], fg=self._theme["text_fg"], insertbackground=self._theme["text_fg"])
        self.research_bundle_status.grid(row=0, column=0, sticky="ew", padx=(8, 0), pady=8)
        bundle_scroll = ttk.Scrollbar(bundle_status, orient="vertical", command=self.research_bundle_status.yview)
        bundle_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.research_bundle_status.configure(yscrollcommand=bundle_scroll.set)
        self._replace_text(self.research_bundle_status, "No research bundle exported yet. Use Export Research Bundle to create a timestamped zip.\n", readonly=True)
        self._update_expected_report_action_state()
        self.refresh_expected_reports_panel()
        return panel

    def refresh_expected_reports_panel(self) -> None:
        tree = getattr(self, "expected_report_tree", None)
        if not tree:
            return
        tree.delete(*tree.get_children())
        self.expected_report_payloads = {}
        for row in self._expected_report_rows():
            tags = ("binrow",) if row.get("status") == "Ready" else ("secrow",)
            iid = tree.insert(
                "",
                "end",
                text=str(row["name"]),
                values=(row["status"], row["modified"], row.get("source_dir", "—"), row["tool"], row["required_inputs"]),
                tags=tags,
            )
            self.expected_report_payloads[iid] = row
        self._update_expected_report_action_state()

    def _selected_expected_report(self) -> dict[str, object] | None:
        tree = getattr(self, "expected_report_tree", None)
        if not tree:
            return None
        selection = tree.selection()
        return self.expected_report_payloads.get(selection[0]) if selection else None

    def on_expected_report_select(self, _evt=None) -> None:
        row = self._selected_expected_report()
        if not row:
            self._update_expected_report_action_state()
            return
        missing = row.get("missing_inputs") or []
        self._update_expected_report_action_state(row)
        text = [
            f"Report: {row.get('name')}",
            f"Status: {row.get('status')}",
            f"Path: {row.get('path')}",
            f"Source directory: {row.get('source_dir')}",
            f"All matches: {len(row.get('all_matches') or [])}",
            *[f"- {match}" for match in (row.get("all_matches") or [])],
            f"Generating tool: {row.get('tool')}",
            f"Required inputs: {row.get('required_inputs')}",
        ]
        if row.get("status") == "Missing":
            text.append("\nThis expected report is missing. Use Generate to run the listed launcher.")
            text.append("Absent required inputs:" if missing else "All launcher inputs appear present.")
            text.extend(f"- {item}" for item in missing)
        self._replace_text(self.selection_inspector, "\n".join(text) + "\n", readonly=True)
        self.resource_preview_message.set(f"Expected report: {row.get('name')} ({row.get('status')})")

    def generate_selected_expected_report(self) -> None:
        row = self._selected_expected_report()
        if not row:
            return messagebox.showinfo("Expected Reports", "Select a report first.")
        missing = row.get("missing_inputs") or []
        if missing:
            self._update_expected_report_action_state(row)
            return messagebox.showerror("Missing inputs", "\n".join(str(item) for item in missing))
        launcher_id = str(row.get("launcher_id") or "")
        if launcher_id == "fragment_strings_import":
            return self.import_fragment_strings_workbook_action()
        if launcher_id == "root_town_summary":
            txt_path, json_path = self._write_root_town_summary()
            scan_summary = self._write_fragmenter_scan_summary()
            self.refresh_project_tree()
            self.refresh_expected_reports_panel()
            self._replace_text(self.preview_tabs["Report"], txt_path.read_text(encoding="utf-8", errors="replace"), readonly=True)
            self.nb.select(self.preview_tabs["Report"].master)
            self.resource_preview_message.set(f"Generated {txt_path.name}, {json_path.name}, and {scan_summary.name}")
            return
        if launcher_id in self.research_launchers:
            self.run_research_launcher(launcher_id)

    def _update_expected_report_action_state(self, row: dict[str, object] | None = None) -> None:
        button = getattr(self, "expected_report_generate_button", None)
        if not button:
            return
        if row is None:
            row = self._selected_expected_report()
        missing = (row or {}).get("missing_inputs") or []
        launcher_id = str((row or {}).get("launcher_id") or "")
        can_generate = launcher_id == "fragment_strings_import" or launcher_id in self.research_launchers
        enabled = bool(row) and can_generate and not missing and not self.research_launcher_running
        button.configure(state=("normal" if enabled else "disabled"))

    def show_selected_expected_report_command(self) -> None:
        row = self._selected_expected_report()
        if not row:
            return messagebox.showinfo("Expected Reports", "Select a report first.")
        launcher = self.research_launchers.get(str(row.get("launcher_id") or ""), {})
        if str(row.get("launcher_id") or "") == "fragment_strings_import":
            command = "GUI action: prompts for Fragment Strings.xlsx, then writes workspace/reports/fragment_strings_summary.{json,txt}"
        else:
            command = self._format_command(launcher["command"](self._selected_workspace())) if launcher else "(no command available)"
        self._replace_text(self.preview_tabs["Report"], command + "\n", readonly=True)
        self.nb.select(self.preview_tabs["Report"].master)

    def open_selected_expected_report(self) -> None:
        row = self._selected_expected_report()
        if not row:
            return messagebox.showinfo("Expected Reports", "Select a report first.")
        path = Path(row.get("path"))
        if not path.exists():
            self.on_expected_report_select()
            return messagebox.showinfo("Expected Reports", f"Missing report:\n{path}")
        target = self.preview_tabs["Text / Hex"] if path.suffix.lower() == ".json" else self.preview_tabs["Report"]
        self._show_bounded_report_preview(path, target, source_dir=Path(row.get("source_dir") or path.parent))

    def open_selected_expected_report_folder(self) -> None:
        row = self._selected_expected_report()
        path = Path(row.get("path")) if row else (self._active_workspace_root() / "reports")
        folder = path if path.is_dir() else path.parent
        folder.mkdir(parents=True, exist_ok=True)
        self._open_folder_path(folder)

    def copy_selected_expected_report_path(self) -> None:
        row = self._selected_expected_report()
        if not row:
            return messagebox.showinfo("Expected Reports", "Select a report first.")
        self._copy_path_to_clipboard(Path(row.get("path")))

    def _active_job_status_text(self) -> str:
        runner = getattr(self, "runner", None)
        if runner and runner.is_busy():
            active_name = getattr(runner, "active_name", "") or "task"
            return f"running: {active_name}"
        if getattr(self, "research_launcher_running", False):
            return self.run_status.get().strip() or "running: launcher"
        return self.run_status.get().strip() or "idle"

    def _current_project_display_name(self) -> str:
        project_path = (getattr(self, "_app_settings_payload", {}) or {}).get("last_project_json_path", "")
        if isinstance(project_path, str) and project_path.strip():
            return Path(project_path).expanduser().name
        return "No project loaded"

    def _update_title_status_strip(self) -> None:
        if not hasattr(self, "title_status_vars"):
            return
        self.title_status_vars["title"].set(APP_TITLE)
        self.title_status_vars["safe"].set("Safe Mode ON")
        self.title_status_vars["job"].set(self._active_job_status_text())
        self.title_status_vars["project"].set(self._current_project_display_name())

    def _project_payload(self, saved_at: str | None = None) -> dict[str, str]:
        return {
            "iso_path": self.iso_path.get(),
            "project_root": self.project_root.get(),
            "data_dir": self.data_dir.get(),
            "save_dir": self.save_dir.get(),
            "workspace_output_dir": self.workspace_output_dir.get(),
            "index_path": self.index_path.get(),
            "saved_at": saved_at or datetime.now(timezone.utc).isoformat(),
        }

    def _apply_project_payload(self, data: dict[str, object]) -> None:
        self.iso_path.set(str(data.get("iso_path", "") or ""))
        self.project_root.set(str(data.get("project_root", "") or ""))
        self.data_dir.set(str(data.get("data_dir", "") or ""))
        self.save_dir.set(str(data.get("save_dir", "") or ""))
        self.workspace_output_dir.set(str(data.get("workspace_output_dir", self.workspace_output_dir.get()) or self.workspace_output_dir.get()))
        self.index_path.set(str(data.get("index_path", self.index_path.get()) or self.index_path.get()))

    def _load_project_file(self, path: str | Path) -> dict[str, object]:
        project_path = Path(path).expanduser()
        data = json.loads(project_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Project JSON must contain an object at the top level.")
        self._apply_project_payload(data)
        return data

    def _update_project_settings(self, project_path: Path | str | None = None, saved_at: str | None = None) -> None:
        payload = dict(getattr(self, "_app_settings_payload", {}) or {})
        if project_path is not None:
            payload["last_project_json_path"] = str(Path(project_path).expanduser())
        payload["iso_path"] = self.iso_path.get().strip()
        payload["area_server_root_path"] = self.project_root.get().strip()
        payload["workspace_path"] = self.workspace_output_dir.get().strip()
        payload["data_folder_path"] = self.data_dir.get().strip()
        payload["save_folder_path"] = self.save_dir.get().strip()
        payload["saved_at"] = saved_at or datetime.now(timezone.utc).isoformat()
        self._app_settings_payload = payload
        self._save_app_settings()

    def load_project(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Fragmenter project",
            filetypes=[("Fragmenter project", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._load_project_file(path)
        except Exception as exc:
            return messagebox.showerror("Load Project", f"Could not load project:\n{exc}")
        self._update_project_settings(path)
        self._update_title_status_strip()
        self.load_index()
        self.refresh_project_tree()

    def save_project(self) -> None:
        workspace = Path(self.workspace_output_dir.get().strip() or WORKSPACE).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)
        out = workspace / "fragmenter_project.json"
        saved_at = datetime.now(timezone.utc).isoformat()
        atomic_write_json(out, self._project_payload(saved_at=saved_at))
        self._update_project_settings(out, saved_at=saved_at)
        self._console_write(f"[project] Saved {out}\n")
        self._update_title_status_strip()
        self.refresh_project_tree()

    def quick_scan(self) -> None:
        self.run_scan(); self._update_title_status_strip(); self.refresh_project_tree(quick_probe_iso=True)

    def extract_common_town_assets(self) -> None:
        server = Path(self.project_root.get().strip()).expanduser() if self.project_root.get().strip() else None
        if not server:
            return messagebox.showerror("Missing", "Pick your Area Server root first.")
        town_bin = server / "data" / "town.bin"
        if not town_bin.is_file():
            return messagebox.showerror("Missing town.bin", f"Could not find:\n{town_bin}")
        workspace = Path(self.workspace_output_dir.get().strip() or WORKSPACE).expanduser()
        out_dir = workspace / "extracted_ccs" / "town"
        cmd = [
            PY, str(TOOLS / "extract_area_ccs_members.py"),
            "--input", str(town_bin),
            "--out-dir", str(out_dir),
            "--members", "8,9,10",
            "--write-raw",
            "--write-decompressed",
        ]

        def _done(rc: int) -> None:
            if rc == 0:
                self.refresh_project_tree()
                self.resource_preview_message.set(f"Extracted common town assets to {out_dir}")

        self._run_task(cmd, on_done=_done, label="extract common town assets")

    def catalog_extracted_assets(self) -> None:
        workspace = Path(self.workspace_output_dir.get().strip() or WORKSPACE).expanduser()
        input_dir = workspace / "extracted_ccs"
        out = workspace / "reports" / "town_ccs_asset_catalog.json"
        cmd = [
            PY, str(TOOLS / "poc_ccs_asset_catalog.py"),
            "--input", str(input_dir),
            "--recursive",
            "--focus", "all",
            "--out", str(out),
        ]

        def _done(rc: int) -> None:
            if rc == 0:
                self._write_fragmenter_scan_summary(workspace)
                self.refresh_project_tree()
                txt = out.with_suffix(".txt")
                if txt.is_file():
                    self._replace_text(self.preview_tabs["Report"], txt.read_text(encoding="utf-8", errors="replace"), readonly=True)
                    self.nb.select(self.preview_tabs["Report"].master)
                    self.resource_preview_message.set(f"Report opened: {txt.name}")
                elif out.is_file():
                    self._replace_text(self.preview_tabs["Text / Hex"], out.read_text(encoding="utf-8", errors="replace"), readonly=True)
                    self.nb.select(self.preview_tabs["Text / Hex"].master)
                    self.resource_preview_message.set(f"Report opened: {out.name}")

        self._run_task(cmd, on_done=_done, label="catalog extracted assets")

    def open_report_folder(self) -> None:
        path = Path(self.workspace_output_dir.get().strip() or WORKSPACE) / "reports"; path.mkdir(parents=True, exist_ok=True)
        try: os.startfile(str(path))
        except Exception: messagebox.showinfo("Report folder", str(path))

    def import_fragment_strings_workbook_action(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Fragment Strings.xlsx",
            filetypes=[("Excel workbooks", "*.xlsx"), ("All files", "*.*")],
            initialfile="Fragment Strings.xlsx",
        )
        if not path:
            return
        result = import_fragment_strings_workbook(Path(path), self._ensure_research_workspace())
        if not result.get("ok"):
            message = str(result.get("message") or "Could not import Fragment Strings workbook.")
            self._console_write(f"[fragment strings] {message}\n")
            return messagebox.showinfo("Import Fragment Strings Workbook", message)
        txt_path = Path(result["txt_path"])
        json_path = Path(result["json_path"])
        self.latest_research_output = txt_path
        self._replace_text(self.preview_tabs["Report"], txt_path.read_text(encoding="utf-8", errors="replace"), readonly=True)
        self.nb.select(self.preview_tabs["Report"].master)
        self.resource_preview_message.set(f"Imported Fragment Strings workbook: {txt_path.name}, {json_path.name}")
        self._console_write(f"[fragment strings] Wrote {txt_path}\n[fragment strings] Wrote {json_path}\n")
        self.refresh_expected_reports_panel()
        self.refresh_project_tree()
        messagebox.showinfo("Import Fragment Strings Workbook", f"Wrote:\n{txt_path}\n{json_path}")

    def _build_iso(self) -> None:
        """Compatibility hook for smoke tests; ISO controls are built in the main workbench layout."""
        return None

    def stage_mod_plan(self) -> None:
        """Create a safe note-only patch plan from the current workbench state."""
        state = FragmenterProjectState.default(".")
        state.workspace_dir = self.workspace_output_dir.get().strip() or str(WORKSPACE)
        state.reports_dir = str(Path(state.workspace_dir) / "reports")
        state.extracted_assets_dir = str(Path(state.workspace_dir) / "extracted_ccs")
        try:
            state.iso_path = self.iso_path.get().strip() or None
        except Exception:
            state.iso_path = None
        try:
            state.area_server_root = self.server_root.get().strip() or None
        except Exception:
            state.area_server_root = None
        plan_path, _action = add_safe_note_to_current_patch_plan(
            state,
            source="gui",
            file=None,
            description="Safe staged workbench plan placeholder; review correlations before building any derived output.",
        )
        self._console_write(f"[plan] Staged safe mod plan metadata: {plan_path}\n")
        self.refresh_project_tree()

    def preview_patch_package(self) -> None:
        self._console_write("[preview] Patch package preview is metadata-only in safe mode.\n"); self.build_upload_package()

    def build_patch_package(self) -> None:
        message = "Patch builder is not fully implemented yet. Current pass supports read-only analysis and safe exports."
        self._console_write(f"[package] {message}\n")
        messagebox.showinfo("Build Patch Package", message)
        self.build_upload_package()

    def _active_workspace_root(self) -> Path:
        """Return the workspace root selected for new GUI output."""
        return Path(self.workspace_output_dir.get().strip() or WORKSPACE).expanduser()

    def _selected_workspace(self) -> Path:
        """Backward-compatible alias for the active workspace root."""
        return self._active_workspace_root()

    def _ensure_research_workspace(self) -> Path:
        workspace = self._active_workspace_root()
        for rel in ("reports", "extracted_ccs", "bundles", "logs", "patch_plans"):
            (workspace / rel).mkdir(parents=True, exist_ok=True)
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def _research_launcher_metadata(self) -> dict[str, dict[str, object]]:
        def server_data() -> Path:
            data = self.data_dir.get().strip()
            return Path(data).expanduser() if data else Path(self.project_root.get().strip()).expanduser() / "data"

        def town_bin() -> Path:
            return Path(self.project_root.get().strip()).expanduser() / "data" / "town.bin"

        return {
            "workbench_smoke": {
                "name": "Workbench smoke test",
                "script": "workbench_smoke_test.py",
                "required": [],
                "expected": lambda ws: ws / "reports" / "workbench_smoke_test.txt",
                "expected_required": False,
                "expected_optional_message": "Succeeded, no report generated.",
                "command": lambda ws: [sys.executable, str(TOOLS / "workbench_smoke_test.py")],
            },
            "extract_common_town_assets": {
                "name": "Extract Common Town Assets",
                "script": "extract_area_ccs_members.py",
                "required": [("Area Server town.bin", town_bin)],
                "expected": lambda ws: ws / "extracted_ccs" / "town",
                "expected_required": True,
                "command": lambda ws: [sys.executable, str(TOOLS / "extract_area_ccs_members.py"), "--input", str(town_bin()), "--out-dir", str(ws / "extracted_ccs" / "town"), "--members", "8,9,10", "--write-raw", "--write-decompressed", "--force"],
            },
            "catalog_extracted_assets": {
                "name": "Catalog Extracted Assets",
                "script": "poc_ccs_asset_catalog.py",
                "required": [("Extracted CCS folder", lambda: self._selected_workspace() / "extracted_ccs")],
                "expected": lambda ws: ws / "reports" / "town_ccs_asset_catalog.txt",
                "expected_required": True,
                "command": lambda ws: [sys.executable, str(TOOLS / "poc_ccs_asset_catalog.py"), "--input", str(ws / "extracted_ccs"), "--recursive", "--focus", "all", "--out", str(ws / "reports" / "town_ccs_asset_catalog.json")],
            },
            "iso_client_probe": {
                "name": "ISO Client Probe",
                "script": "poc_iso_client_probe.py",
                "required": [("ISO path", lambda: Path(self.iso_path.get().strip()).expanduser())],
                "expected": lambda ws: ws / "reports" / "iso_client_probe.json",
                "expected_required": True,
                "command": lambda ws: [sys.executable, str(TOOLS / "poc_iso_client_probe.py"), "--input", str(Path(self.iso_path.get().strip()).expanduser()), "--out", str(ws / "reports" / "iso_client_probe.json"), "--txt-out", str(ws / "reports" / "iso_client_probe.txt")],
            },
            "server_text_probe": {
                "name": "Server Text Probe",
                "script": "poc_server_text_shop_probe.py",
                "required": [("Area Server root", lambda: Path(self.project_root.get().strip()).expanduser())],
                "expected": lambda ws: ws / "reports" / "server_text_shop_probe.json",
                "expected_required": True,
                "command": lambda ws: [sys.executable, str(TOOLS / "poc_server_text_shop_probe.py"), "--server-root", str(Path(self.project_root.get().strip()).expanduser()), "--out", str(ws / "reports" / "server_text_shop_probe.json"), "--quick"],
            },
            "boundary_correlation_report": {
                "name": "Boundary/Correlation report",
                "script": "server_client_boundary_report.py",
                "required": [("Area Server data", server_data)],
                "expected": lambda ws: ws / "reports" / "correlation_report.txt",
                "expected_required": True,
                "command": lambda ws: [sys.executable, str(TOOLS / "server_client_boundary_report.py"), "--server-data", str(server_data()), *(["--iso", str(Path(self.iso_path.get().strip()).expanduser())] if self.iso_path.get().strip() else ["--server-only"]), "--quick", "--out", str(ws / "reports" / "correlation_report.json"), "--txt-out", str(ws / "reports" / "correlation_report.txt")],
            },
            "fragmenter_safe_scan": {
                "name": "Fragmenter Safe Scan",
                "script": "fragmenter_research_pack.py",
                "required": [("Area Server root", lambda: Path(self.project_root.get().strip()).expanduser()), ("Area Server data", server_data)],
                "expected": lambda ws: ws / "reports" / "fragmenter_scan_summary.json",
                "expected_required": True,
                "command": lambda ws: [sys.executable, str(TOOLS / "fragmenter_research_pack.py"), "scan", "--area-server-root", str(Path(self.project_root.get().strip()).expanduser()), "--area-server-data", str(server_data()), "--workspace", str(ws), *( ["--iso-path", str(Path(self.iso_path.get().strip()).expanduser())] if self.iso_path.get().strip() else [] )],
            },
            "root_town_summary": {
                "name": "Root Town Summary",
                "script": "fragmenter_research_pack.py",
                "required": [("Fragmenter scan summary", lambda: self._selected_workspace() / "reports" / "fragmenter_scan_summary.json")],
                "expected": lambda ws: ws / "reports" / "root_town_summary.txt",
                "expected_required": True,
                "command": lambda ws: ["internal", "write_root_town_summary", "--scan-summary", str(ws / "reports" / "fragmenter_scan_summary.json"), "--txt-out", str(ws / "reports" / "root_town_summary.txt"), "--json-out", str(ws / "reports" / "root_town_summary.json")],
            },
            "export_research_bundle": {
                "name": "Export Research Bundle",
                "script": "fragmenter_research_pack.py",
                "required": [("Workspace reports folder", lambda: self._selected_workspace() / "reports")],
                "expected": lambda ws: ws / "bundles",
                "expected_required": True,
                "command": lambda ws: [sys.executable, str(TOOLS / "fragmenter_research_pack.py"), "package", "--out", str(ws), "--zip-out", str(ws / "bundles" / f"fragmenter_research_bundle_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip")],
            },
        }

    def _expected_report_registry(self) -> list[dict[str, object]]:
        """Report files the workbench expects to track even before they exist."""
        def entry(filename: str, launcher_id: str, required_note: str | None = None) -> dict[str, object]:
            launcher = self.research_launchers.get(launcher_id, {})
            return {
                "name": filename,
                "path": lambda ws, name=filename: ws / "reports" / name,
                "launcher_id": launcher_id,
                "tool": launcher.get("name", launcher_id),
                "required_note": required_note,
            }

        return [
            entry("town_ccs_asset_catalog.txt", "catalog_extracted_assets"),
            entry("town_ccs_asset_catalog.json", "catalog_extracted_assets"),
            entry("iso_client_probe.txt", "iso_client_probe"),
            entry("iso_client_probe.json", "iso_client_probe"),
            entry("server_text_shop_probe.txt", "server_text_probe"),
            entry("server_text_shop_probe.json", "server_text_probe"),
            entry("fragmenter_scan_summary.json", "fragmenter_safe_scan"),
            entry("correlation_report.txt", "boundary_correlation_report"),
            entry("correlation_report.json", "boundary_correlation_report"),
            entry("root_town_summary.txt", "root_town_summary", "Requires fragmenter_scan_summary.json; regenerate the safe scan first if absent."),
            entry("root_town_summary.json", "root_town_summary", "Requires fragmenter_scan_summary.json; regenerate the safe scan first if absent."),
            entry("fragment_strings_summary.txt", "fragment_strings_import"),
            entry("fragment_strings_summary.json", "fragment_strings_import"),
        ]

    def _report_search_roots(self) -> list[Path]:
        """Directories checked for expected reports, ordered by discovery priority."""
        workspace = self._active_workspace_root()
        roots = [
            workspace / "reports",
            workspace / "upload_package" / "reports",
            WORKSPACE / "reports",
            WORKSPACE / "upload_package" / "reports",
        ]
        unique_roots: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root)
            if key in seen:
                continue
            seen.add(key)
            unique_roots.append(root)
        return unique_roots

    def _find_report_path(self, filename: str) -> Path | None:
        """Return the newest matching report from shared discovery roots."""
        matches = [root / filename for root in self._report_search_roots() if (root / filename).exists()]
        return max(matches, key=lambda match: match.stat().st_mtime) if matches else None

    def _expected_report_rows(self) -> list[dict[str, object]]:
        workspace = self._active_workspace_root()
        search_roots = self._report_search_roots()
        rows: list[dict[str, object]] = []
        for spec in self._expected_report_registry():
            expected_name = str(spec.get("name", ""))
            all_matches = [root / expected_name for root in search_roots if (root / expected_name).exists()]
            path = max(all_matches, key=lambda match: match.stat().st_mtime) if all_matches else spec["path"](workspace)
            launcher = self.research_launchers.get(str(spec.get("launcher_id", "")), {})
            missing = self._launcher_missing_inputs(launcher) if launcher else []
            if spec.get("required_note") and not all_matches:
                missing = list(missing) + [str(spec["required_note"])]
            modified = ""
            size = None
            if all_matches:
                try:
                    stat = path.stat()
                    size = stat.st_size
                    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                except OSError:
                    pass
            rows.append({
                **spec,
                "path": path,
                "source_dir": str(path.parent) if all_matches else "—",
                "all_matches": all_matches,
                "status": "Ready" if all_matches else "Missing",
                "modified": modified or "—",
                "size": size,
                "missing_inputs": missing,
                "required_inputs": "; ".join(label for label, _ in launcher.get("required", [])) or "(none)",
            })
        return rows

    def _launcher_missing_inputs(self, launcher: dict[str, object]) -> list[str]:
        missing = []
        for label, getter in launcher.get("required", []):
            try:
                path = getter()
            except Exception:
                path = None
            path_obj = Path(path) if path else None
            if not path_obj or str(path_obj) in {"", "."} or not path_obj.exists():
                missing.append(f"{label}: {path or '(unset)'}")
        return missing

    def _launcher_output_excerpt(self, value: object, limit: int = 4000) -> tuple[int, str]:
        text = str(value or "")
        if not text:
            return 0, "(empty)"
        if len(text) <= limit:
            return len(text), text
        omitted = len(text) - limit
        return len(text), f"{text[:limit]}\n... [truncated {omitted} chars]"

    def _launcher_required_input_paths(self, launcher: dict[str, object]) -> list[str]:
        paths = []
        for label, getter in launcher.get("required", []):
            try:
                path = getter()
            except Exception as exc:
                paths.append(f"{label}: <error: {exc}>")
                continue
            paths.append(f"{label}: {path or '(unset)'}")
        return paths

    def _refresh_launcher_diagnostics(self) -> None:
        if not hasattr(self, "launcher_diagnostics"):
            return
        lines = [
            "Launcher Diagnostics",
            f"  selected workspace: {self._selected_workspace()}",
            f"  active workspace root: {self._active_workspace_root()}",
            f"  ISO path: {self.iso_path.get() or '(unset)'}",
            f"  Area Server root: {self.project_root.get() or '(unset)'}",
            f"  data dir: {self.data_dir.get() or '(unset)'}",
            f"  latest launcher id: {getattr(self, 'latest_research_launcher_id', '(none)')}",
            f"  latest launcher output/report: {self.latest_research_output or '(none)'}",
            "",
        ]
        for launcher_id, launcher in self.research_launchers.items():
            script_path = TOOLS / str(launcher["script"])
            state = self.research_launcher_state.get(launcher_id, {})
            missing = self._launcher_missing_inputs(launcher)
            button = self.research_launcher_buttons.get(launcher_id)
            if button:
                button.configure(state=("disabled" if self.research_launcher_running or missing or not script_path.exists() else "normal"))
            reqs = "; ".join(missing) if missing else "all present"
            generated = state.get("generated_output_paths") or []
            generated_text = "\n".join(f"    - {path}" for path in generated) if generated else "    (none)"
            input_paths = "\n".join(f"    - {path}" for path in self._launcher_required_input_paths(launcher)) or "    (none)"
            stdout_len, stdout_excerpt = self._launcher_output_excerpt(state.get("stdout", ""))
            stderr_len, stderr_excerpt = self._launcher_output_excerpt(state.get("stderr", ""))
            lines.append(
                f"{launcher['name']} ({launcher_id})\n"
                f"  script path: {script_path}\n"
                f"  script exists: {'yes' if script_path.exists() else 'no'}\n"
                f"  required project inputs: {reqs}\n"
                f"  required input paths:\n{input_paths}\n"
                f"  expected required: {launcher.get('expected_required', True)}\n"
                f"  exact command: {state.get('command', '(not run)')}\n"
                f"  exact command argv: {state.get('command_list', '(not run)')}\n"
                f"  cwd: {state.get('cwd', '(not run)')}\n"
                f"  started_at: {state.get('started_at', '(not run)')}\n"
                f"  ended_at: {state.get('ended_at', '(not run)')}\n"
                f"  elapsed_seconds: {state.get('elapsed_seconds', '(not run)')}\n"
                f"  exit code: {state.get('exit_code', '(not run)')}\n"
                f"  expected output path: {state.get('expected_path', '(not run)')}\n"
                f"  generated output paths:\n{generated_text}\n"
                f"  interpreted status: {state.get('interpreted_status', '(not run)')}\n"
                f"  interpreted message: {state.get('interpreted_message', '(not run)')}\n"
                f"  stdout chars: {stdout_len}\n"
                f"  stdout excerpt:\n{stdout_excerpt}\n"
                f"  stderr chars: {stderr_len}\n"
                f"  stderr excerpt:\n{stderr_excerpt}\n"
                f"  report path: {state.get('report', '(none)')}\n"
                f"  last result JSON: {state.get('last_result_json', '(not run)')}\n"
            )
        self._replace_text(self.launcher_diagnostics, "\n".join(lines), readonly=True)

    def _format_command(self, cmd: list[str]) -> str:
        return " ".join(shlex.quote(str(part)) for part in cmd)

    def _interpret_research_launcher_status(self, launcher: dict[str, object], exit_code: int, expected: Path) -> tuple[str, str]:
        expected_present = expected.exists()
        expected_required = bool(launcher.get("expected_required", True))
        if exit_code != 0:
            return "failed", "Command failed."
        if expected_present:
            return "success", "Succeeded."
        if expected_required:
            return "warning", "Command succeeded but expected report missing."
        return "success", str(launcher.get("expected_optional_message") or "Succeeded, no report generated.")

    def run_research_launcher(self, launcher_id: str) -> None:
        launcher = self.research_launchers[launcher_id]
        if launcher_id == "export_research_bundle":
            self.export_research_bundle_for_chatgpt()
            return
        script_path = TOOLS / str(launcher["script"])
        if not script_path.exists():
            self._refresh_launcher_diagnostics()
            return messagebox.showerror("Missing script", f"Could not find {script_path}")
        missing = self._launcher_missing_inputs(launcher)
        if missing:
            self._refresh_launcher_diagnostics()
            return messagebox.showerror("Missing inputs", "\n".join(missing))
        if self.runner.is_busy() or self.research_launcher_running:
            return messagebox.showwarning("Busy", "A task is already running. Cancel it first if needed.")

        workspace = self._ensure_research_workspace()
        expected = launcher["expected"](workspace)
        cmd = launcher["command"](workspace)
        command_text = self._format_command(cmd)
        if cmd and str(cmd[0]) == "internal" and launcher_id == "root_town_summary":
            started_at = _utc_timestamp()
            txt_path, json_path = self._write_root_town_summary()
            scan_summary = self._write_fragmenter_scan_summary(workspace)
            ended_at = _utc_timestamp()
            generated_paths = [str(txt_path), str(json_path), str(scan_summary)]
            report_text = (
                f"Launcher: {launcher['name']}\nCommand: {command_text}\nCWD: {ROOT}\n"
                f"Required inputs: {'; '.join(label for label, _ in launcher.get('required', [])) or '(none)'}\n"
                f"Expected output path: {expected}\nStarted: {started_at}\n"
                f"Ended: {ended_at}\nExit code: 0\nElapsed seconds: 0.000\n"
                f"Expected path: {expected}\n"
                "Generated output paths:\n"
                + "".join(f"- {path}\n" for path in generated_paths)
                + "Final interpreted status: success\n"
                + "Final interpreted message: Succeeded.\n"
                + "\n[stdout]\n--------\n"
                + f"Wrote {txt_path}\nWrote {json_path}\nWrote {scan_summary}\n"
                + "\n[stderr]\n--------\n(empty)\n"
                + "\n[report]\n--------\n"
                + txt_path.read_text(encoding="utf-8", errors="replace")
            )
            self.latest_research_launcher_id = launcher_id
            self.latest_research_output = txt_path
            state = self.research_launcher_state.setdefault(launcher_id, {})
            state.update({
                "command": command_text,
                "command_list": list(cmd),
                "cwd": str(ROOT),
                "started_at": started_at,
                "ended_at": ended_at,
                "elapsed_seconds": 0,
                "stdout": f"Wrote {txt_path}\nWrote {json_path}\nWrote {scan_summary}\n",
                "stderr": "",
                "exit_code": 0,
                "expected_path": str(expected),
                "generated_output_paths": generated_paths,
                "interpreted_status": "success",
                "interpreted_message": "Succeeded.",
                "report": str(txt_path),
            })
            self._replace_text(self.preview_tabs["Report"], report_text, readonly=True)
            self.nb.select(self.preview_tabs["Report"].master)
            self._refresh_launcher_diagnostics()
            self.refresh_project_tree()
            return
        self.latest_research_launcher_id = launcher_id
        self.latest_research_output = Path(expected)
        started_at = _utc_timestamp()
        before_snapshot = _launcher_workspace_snapshot(workspace)
        state = self.research_launcher_state.setdefault(launcher_id, {})
        state.update(
            {
                "command": command_text,
                "command_list": list(cmd),
                "cwd": str(ROOT),
                "started_at": started_at,
                "ended_at": "(running)",
                "elapsed_seconds": "(running)",
                "stdout": "",
                "stderr": "",
                "exit_code": "(running)",
                "expected_path": str(expected),
                "generated_output_paths": [],
                "interpreted_status": "(running)",
                "interpreted_message": "(running)",
            }
        )
        started = time.time()
        header = (
            f"Launcher: {launcher['name']}\nCommand: {command_text}\nCWD: {ROOT}\n"
            f"Required inputs: {'; '.join(label for label, _ in launcher.get('required', [])) or '(none)'}\n"
            f"Expected output path: {expected}\nStarted: {started_at}\n\n"
        )
        self._replace_text(self.preview_tabs["Report"], header, readonly=True)
        self.nb.select(self.preview_tabs["Report"].master)
        self.research_launcher_running = True
        self.run_status.set(f"running: {launcher['name']}")
        self._refresh_launcher_diagnostics()
        self._update_expected_report_action_state()

        def worker() -> None:
            failure_log = None
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(ROOT),
                )
                stdout, stderr = proc.communicate()
                returncode = proc.returncode
            except Exception as exc:
                returncode = 1
                stdout = ""
                stderr = f"{type(exc).__name__}: {exc}\n"
            ended_at = _utc_timestamp()
            elapsed = time.time() - started
            generated_paths = _launcher_generated_paths(workspace, before_snapshot, Path(expected))
            interpreted_status, interpreted_message = self._interpret_research_launcher_status(launcher, int(returncode), Path(expected))
            result = {
                "started_at": started_at,
                "ended_at": ended_at,
                "elapsed_seconds": round(elapsed, 3),
                "stdout": stdout or "",
                "stderr": stderr or "",
                "exit_code": returncode,
                "command_list": list(cmd),
                "cwd": str(ROOT),
                "expected_path": str(expected),
                "generated_output_paths": generated_paths,
                "interpreted_status": interpreted_status,
                "interpreted_message": interpreted_message,
            }
            report_text = (
                header
                + f"Ended: {ended_at}\nExit code: {returncode}\nElapsed seconds: {elapsed:.3f}\n"
                + f"Expected path: {expected}\n"
                + "Generated output paths:\n"
                + ("".join(f"- {path}\n" for path in generated_paths) or "(none)\n")
                + f"Final interpreted status: {interpreted_status}\n"
                + f"Final interpreted message: {interpreted_message}\n"
                + "\n[stdout]\n--------\n" + (stdout or "(empty)\n")
                + "\n[stderr]\n--------\n" + (stderr or "(empty)\n")
            )
            if returncode != 0 or interpreted_status == "warning":
                safe_tool = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(launcher["name"])).strip("_").lower()
                log_kind = "failure" if returncode != 0 else "warning"
                failure_log = workspace / "logs" / f"{safe_tool}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{log_kind}.txt"
                failure_log.parent.mkdir(parents=True, exist_ok=True)
                failure_log.write_text(report_text + "\n\nLauncher result JSON:\n" + json.dumps(result, indent=2), encoding="utf-8", newline="\n")
                report_text += f"\nLauncher log: {failure_log}\n"
            self.after(0, lambda: self._finish_research_launcher(launcher_id, result, Path(expected), report_text, failure_log))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_research_launcher(self, launcher_id: str, result: dict[str, object], expected: Path, report_text: str, failure_log: Path | None) -> None:
        self.research_launcher_running = False
        rc = int(result.get("exit_code") or 1)
        launcher = self.research_launchers.get(launcher_id, {})
        interpreted_status, interpreted_message = self._interpret_research_launcher_status(launcher, rc, expected)
        result["expected_path"] = str(expected)
        result["interpreted_status"] = interpreted_status
        result["interpreted_message"] = interpreted_message
        self.run_status.set("done" if interpreted_status == "success" else interpreted_status)
        state = self.research_launcher_state.setdefault(launcher_id, {})
        state.update(result)
        state["command"] = self._format_command([str(part) for part in result.get("command_list", [])])
        state["report"] = str(expected if expected.exists() else (failure_log or "(none)"))
        state["last_result_json"] = json.dumps(result, indent=2)
        self.latest_research_output = expected if expected.exists() else failure_log
        self._replace_text(self.preview_tabs["Report"], report_text, readonly=True)
        self._refresh_launcher_diagnostics()
        self.refresh_expected_reports_panel()
        self._update_expected_report_action_state()
        self.refresh_project_tree()

    def copy_latest_launcher_command(self) -> None:
        state = self.research_launcher_state.get(getattr(self, "latest_research_launcher_id", ""), {})
        command = str(state.get("command", ""))
        if command:
            self.clipboard_clear(); self.clipboard_append(command); self.update(); self.run_status.set("launcher command copied")

    def open_latest_launcher_output_folder(self) -> None:
        target = self.latest_research_output or (self._active_workspace_root() / "reports")
        folder = target if target.is_dir() else target.parent
        try: os.startfile(str(folder))
        except Exception: messagebox.showinfo("Output folder", str(folder))

    def open_latest_launcher_report(self) -> None:
        path = self.latest_research_output
        if not path or not path.exists():
            return messagebox.showinfo("Latest report", "No launcher report has been generated yet.")
        if path.is_dir():
            return self.open_latest_launcher_output_folder()
        self._replace_text(self.preview_tabs["Report"], path.read_text(encoding="utf-8", errors="replace"), readonly=True)
        self.nb.select(self.preview_tabs["Report"].master)

    def run_latest_research_launcher(self) -> None:
        launcher_id = getattr(self, "latest_research_launcher_id", "")
        if launcher_id:
            self.run_research_launcher(launcher_id)

    def run_research_script(self, script: str) -> None:
        path = TOOLS / script
        if not path.exists(): return messagebox.showerror("Missing script", f"Could not find {path}")
        self._run_task([sys.executable, str(path)], label=script)

    def _assert_normal_notebook_tabs(self) -> None:
        """Verify normal startup exposes only non-destructive workflow tabs."""
        expected = ["Load Files", "View Results", "Export Package"]
        visible = [self.nb.tab(tab_id, "text") for tab_id in self.nb.tabs()]
        assert visible == expected, f"Unexpected normal GUI tabs: {visible!r}"

    def _console_write(self, text: str, level: str = "normal") -> None:
        mode = self._console_mode_name() if hasattr(self, "console_mode") else "normal"
        level = (level or "normal").lower()
        if level == "debug" and mode != "debug":
            return
        if level == "verbose" and mode not in {"verbose", "debug"}:
            return
        console_write(self.console, text)

    def copy_log_to_clipboard(self) -> None:
        """Copy the current console contents to the system clipboard."""
        self.clipboard_clear()
        self.clipboard_append(self.console.get("1.0", "end-1c"))
        self.update()
        self.run_status.set("log copied")

    def _replace_text(self, widget: tk.Text, text: str, append: bool = False, readonly: bool = False) -> None:
        """Safely update a Text widget that may be configured read-only."""
        try:
            widget.configure(state="normal")
        except tk.TclError:
            pass
        if not append:
            widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.see("end")
        if readonly:
            try:
                widget.configure(state="disabled")
            except tk.TclError:
                pass

    def _reset_3d_tab_text(self) -> tk.Text:
        """Restore the 3D tab to a simple read-only text preview."""
        frame = self.preview_tab_frames["3D"]
        for child in frame.winfo_children():
            child.destroy()
        text = tk.Text(
            frame,
            wrap="word",
            height=10,
            bg=self._theme["text_bg"],
            fg=self._theme["text_fg"],
            insertbackground=self._theme["text_fg"],
        )
        text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        text.configure(yscrollcommand=scroll.set)
        self.preview_tabs["3D"] = text
        return text

    def _show_3d_message(self, message: str, *, select: bool = False) -> None:
        text = self._reset_3d_tab_text()
        self._replace_text(text, message, readonly=True)
        if select:
            self.nb.select(self.preview_tab_frames["3D"])

    def _load_obj_3d_preview(self, path: Path, *, select: bool = True) -> None:
        frame = self.preview_tab_frames["3D"]
        for child in frame.winfo_children():
            child.destroy()
        mesh, viewer = create_obj_viewer(frame, path)
        if viewer is None:
            self._show_3d_message(
                f"Could not load OBJ preview for {path.name}.\n\n{mesh.summary()}",
                select=select,
            )
            return
        viewer.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.preview_tabs["3D"] = viewer.canvas
        self.native_3d_preview_status.set(f"Loaded OBJ preview: {path.name}")
        if select:
            self.nb.select(frame)

    def _managed_temp_path(self, name: str) -> Path:
        """Return a GUI-managed temporary output path under workspace/tmp/."""
        TMP_WORKSPACE.mkdir(parents=True, exist_ok=True)
        return TMP_WORKSPACE / name

    def _prepare_temp_output(self, path: Path) -> int:
        """Delete the expected temp output before starting a subprocess."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        return time.time_ns()

    def _temp_output_created_by_run(self, path: Path, started_at_ns: int) -> bool:
        """Confirm a temp file exists and was written after this run started."""
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        return path.is_file() and stat.st_size > 0 and stat.st_mtime_ns >= started_at_ns

    # ---------- Theme/fonts ----------
    def _font(self, size: int = 10, weight: str = "normal", **kwargs) -> tkfont.Font:
        return tkfont.Font(family=self.font_family, size=size, weight=weight, **kwargs)

    def _init_fonts(self):
        self.font_family = "Segoe UI"
        # Robust for font families with spaces (e.g., "Segoe UI")
        try:
            for name in (
                "TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont",
            ):
                fnt = tkfont.nametofont(name)
                fnt.configure(family=self.font_family)
            tkfont.nametofont("TkDefaultFont").configure(size=10)
            tkfont.nametofont("TkTextFont").configure(size=10)
        except Exception:
            pass

        self.FONT_TITLE = self._font(size=18, weight="bold")
        self.FONT_H2 = self._font(size=11, weight="bold")

    def _init_theme_system(self):
        # Palettes: we can tune these later to match .hack UI even closer
        self.THEMES = {
            "Hack Green": {
                "bg": "#0b0f0c",
                "fg": "#d6ffe7",
                "panel": "#0f1712",
                "accent": "#00ff99",
                "border": "#1f3b2b",
                "grid1": "#19f39a",
                "grid2": "#163427",
                "text_bg": "#07110b",
                "text_fg": "#b8ffd8",
                "sel_bg": "#0e3b28",
                "sel_fg": "#eafff5",
                "muted": "#9fb3a7",
                "row_bin_bg": "#0e1511",
                "row_sec_bg": "#0a120e",
            },
            "Serenial Blue": {
                "bg": "#161a20",
                "fg": "#e7eaf0",
                "panel": "#1d2330",
                "accent": "#2c78ff",
                "border": "#2a3242",
                "grid1": "#3a78ff",
                "grid2": "#22304a",
                "text_bg": "#0f1217",
                "text_fg": "#dbe2f2",
                "sel_bg": "#2a3a5d",
                "sel_fg": "#ffffff",
                "muted": "#aab3c5",
                "row_bin_bg": "#1a202c",
                "row_sec_bg": "#141a24",
            },
        }

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

    def apply_theme(self, name: str):
        name = normalize_theme_name(name)
        if name not in self.THEMES:
            name = "Hack Green"
        self.theme_name.set(name)
        p = self.THEMES[name]
        self._theme = p

        bg = p["bg"]; fg = p["fg"]; panel = p["panel"]; accent = p["accent"]; border = p["border"]
        muted = p["muted"]

        style = ttk.Style(self)
        # Base
        self.configure(bg=bg)
        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg, bordercolor=border)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TCheckbutton", background=bg, foreground=fg)

        # Notebook
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=[12, 8], background=panel, foreground=fg)
        style.map(
            "TNotebook.Tab",
            background=[("selected", accent), ("active", panel)],
            foreground=[("selected", ("#00150c" if name == "Hack Green" else "#ffffff")), ("active", fg)],
        )

        # Buttons
        style.configure("TButton", background=panel, foreground=fg, bordercolor=border)
        style.map("TButton", background=[("active", panel)])
        style.configure("Accent.TButton", background=accent, foreground=("black" if name == "Hack Green" else "white"))
        style.map("Accent.TButton", background=[("active", accent)])
        style.configure("Chip.TLabel", background=panel, foreground=fg, padding=[10, 4], relief="solid", borderwidth=1)

        # Treeview (contrast fix)
        style.configure("Treeview",
                        background=bg,
                        fieldbackground=bg,
                        foreground=fg,
                        rowheight=24,
                        bordercolor=border)
        style.map("Treeview",
                  background=[("selected", p["sel_bg"])],
                  foreground=[("selected", p["sel_fg"])])

        style.configure("Treeview.Heading",
                        background=panel,
                        foreground=fg,
                        relief="flat")
        style.map("Treeview.Heading",
                  background=[("active", panel)],
                  foreground=[("active", fg)])

        # Entry / Combobox / Spinbox readability (including disabled/readonly)
        style.configure("TEntry", fieldbackground=panel, background=panel, foreground=fg, insertcolor=fg)
        style.map(
            "TEntry",
            fieldbackground=[("disabled", bg), ("readonly", panel)],
            foreground=[("disabled", muted), ("readonly", fg)],
        )
        style.configure("TCombobox", fieldbackground=panel, background=panel, foreground=fg, insertcolor=fg)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", panel), ("disabled", bg)],
            foreground=[("readonly", fg), ("disabled", muted)],
            selectbackground=[("readonly", panel)],
            selectforeground=[("readonly", fg)],
        )
        style.configure("TSpinbox", fieldbackground=panel, background=panel, foreground=fg, arrowsize=14)
        style.map(
            "TSpinbox",
            fieldbackground=[("readonly", panel), ("disabled", bg)],
            foreground=[("readonly", fg), ("disabled", muted)],
        )

        # Progressbar and scales
        style.configure("TProgressbar", troughcolor=bg, background=accent, bordercolor=border, lightcolor=accent, darkcolor=accent)

        # Scrollbar
        style.configure("TScrollbar", background=panel, troughcolor=bg, bordercolor=border)

        self.option_add("*TButton.Padding", 7)
        # Safety net for widgets that can ignore ttk colors on some Windows builds
        self.option_add("*Entry.background", panel)
        self.option_add("*Entry.foreground", fg)
        self.option_add("*Entry.insertBackground", fg)
        self.option_add("*Spinbox.background", panel)
        self.option_add("*Spinbox.foreground", fg)
        self.option_add("*Spinbox.disabledForeground", muted)
        self.option_add("*Listbox.background", panel)
        self.option_add("*Listbox.foreground", fg)

        # Update specific widgets we created
        if hasattr(self, "subhead"):
            self.subhead.configure(foreground=muted)
        if hasattr(self, "console"):
            self.console.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["text_fg"])
        if hasattr(self, "detail"):
            self.detail.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["text_fg"])
        if hasattr(self, "resource_detail"):
            self.resource_detail.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["text_fg"])
        if hasattr(self, "resource_family_list"):
            self.resource_family_list.configure(bg=p["panel"], fg=p["fg"], selectbackground=p["sel_bg"], selectforeground=p["sel_fg"])

        # Tree tags if tree exists
        if hasattr(self, "tree"):
            try:
                self.tree.tag_configure("binrow", background=p["row_bin_bg"], foreground=fg)
                self.tree.tag_configure("secrow", background=p["row_sec_bg"], foreground=fg)
            except Exception:
                pass

        if hasattr(self, "header_canvas"):
            self._redraw_header_grid()
        if hasattr(self, "celdra_sprite"):
            self.celdra_sprite.apply_theme()
        if hasattr(self, "title_status_vars"):
            self._update_title_status_strip()

    def _redraw_header_grid(self):
        """Cosmetic HUD/grid in header."""
        if not hasattr(self, "header_canvas"):
            return
        p = getattr(self, "_theme", None)
        if not p:
            return
        c = self.header_canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())

        c.configure(bg=p["bg"])

        # Grid
        spacing = 18
        for x in range(0, w + 1, spacing):
            c.create_line(x, 0, x, h, fill=p["grid2"], width=1)
        for y in range(0, h + 1, spacing):
            c.create_line(0, y, w, y, fill=p["grid2"], width=1)

        # HUD corners
        pad = 9
        accent = p["grid1"]
        c.create_line(pad, pad, pad + 42, pad, fill=accent, width=2)
        c.create_line(pad, pad, pad, pad + 18, fill=accent, width=2)

        c.create_line(w - pad, pad, w - pad - 42, pad, fill=accent, width=2)
        c.create_line(w - pad, pad, w - pad, pad + 18, fill=accent, width=2)

        c.create_line(pad, h - pad, pad + 42, h - pad, fill=accent, width=2)
        c.create_line(pad, h - pad, pad, h - pad - 18, fill=accent, width=2)

        c.create_line(w - pad, h - pad, w - pad - 42, h - pad, fill=accent, width=2)
        c.create_line(w - pad, h - pad, w - pad, h - pad - 18, fill=accent, width=2)

    def _layout_celdra_branding(self, evt=None):
        """Keep Celdra branding compact so it never covers header controls."""
        if not hasattr(self, "celdra_sprite"):
            return
        width = evt.width if evt is not None else self.winfo_width()
        if width < 820:
            self.celdra_sprite.pack_forget()
            self.celdra_sprite.set_visible(False)
            return
        if not self.celdra_sprite.winfo_ismapped():
            pack_options = {"side": "right", "padx": (0, 8), "pady": 3}
            if hasattr(self, "header_right"):
                pack_options["before"] = self.header_right
            self.celdra_sprite.pack(**pack_options)
        size = 96 if width < 1020 else 112
        self.celdra_sprite.set_display_size(size)
        self.celdra_sprite.set_visible(True)

    def _section(self, parent, title):
        """Create a consistent titled container for a section/card."""
        frame = ttk.Labelframe(parent, text=title)
        frame.grid_columnconfigure(0, weight=1)
        return frame

    def _card(self, parent, title):
        return self._section(parent, title)

    def _muted_help(self, parent, text, row=None, columnspan=None):
        """Create muted help text whose wraplength follows the parent width."""
        label = ttk.Label(
            parent,
            text=text,
            foreground=self._theme.get("muted", "#9fb3a7"),
            justify="left",
        )
        _bind_wraplength(label, parent, padding=30)

        if row is None:
            label.pack(anchor="w", fill="x")
        else:
            span = columnspan if columnspan is not None else 1
            label.grid(row=row, column=0, columnspan=span, sticky="ew", padx=10, pady=(0, 8))
        return label

    def _build_path_row(
        self,
        parent,
        label,
        variable,
        browse_command=None,
        open_command=None,
        copy_command=None,
        status_variable=None,
        browse_text="Browse",
    ):
        """Build a reusable, window-friendly path row.

        The entry column is the only expanding column, so long paths remain
        selectable/copyable without forcing fixed-width controls to dominate
        the layout.
        """
        row = ttk.Frame(parent)
        row.grid_columnconfigure(1, weight=1)
        ttk.Label(row, text=label, foreground=self._theme.get("muted", "#9fb3a7")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(row, textvariable=variable).grid(row=0, column=1, sticky="ew")
        button_col = 2
        if browse_command is not None:
            ttk.Button(row, text=browse_text, command=browse_command).grid(row=0, column=button_col, sticky="w", padx=(8, 0))
            button_col += 1
        if open_command is not None:
            ttk.Button(row, text="Open", command=open_command).grid(row=0, column=button_col, sticky="w", padx=(8, 0))
            button_col += 1
        if copy_command is None:
            copy_command = lambda v=variable: self._copy_text_to_clipboard(v.get().strip())
        ttk.Button(row, text="Copy", command=copy_command).grid(row=0, column=button_col, sticky="w", padx=(8, 0))
        if status_variable is not None:
            ttk.Label(
                row,
                textvariable=status_variable,
                foreground=self._theme.get("muted", "#9fb3a7"),
                justify="left",
            ).grid(row=1, column=1, columnspan=max(1, button_col), sticky="ew", pady=(2, 0))
        return row

    def _path_picker_row(self, parent, label, variable, browse_command, open_command=None, browse_text="Browse"):
        """Build a reusable label/entry/browse/open/copy row."""
        return self._build_path_row(parent, label, variable, browse_command, open_command, browse_text=browse_text)

    def _wrapped_button_row(self, parent, button_specs, columns_at_width=None):
        """Create a responsive action row from button specs while preserving commands/text."""
        bar = ActionBar(parent, columns_at_width=columns_at_width)
        buttons = []
        for spec in button_specs:
            kwargs = dict(spec)
            attr = kwargs.pop("attr", None)
            button = bar.add_button(**kwargs)
            if attr:
                setattr(self, attr, button)
            buttons.append(button)
        return bar, buttons

    # ---------- UI builders ----------
    def _build_load_files_tab(self, f: ttk.Frame):
        """Build the simplified file-loading workflow tab."""
        f.grid_columnconfigure(0, weight=1)

        source = self._card(f, "Source paths")
        source.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        source.grid_columnconfigure(0, weight=1)
        self._muted_help(
            source,
            "Choose the local Area Server files to scan. All actions here are read-only except writing Fragmenter metadata into the selected workspace/output folder.",
            row=0,
        )
        self._path_picker_row(source, "Area Server root folder", self.project_root, self.pick_project).grid(
            row=1, column=0, sticky="ew", padx=10, pady=4
        )
        self._path_picker_row(source, "Area Server data folder", self.data_dir, self.pick_data).grid(
            row=2, column=0, sticky="ew", padx=10, pady=4
        )
        self._path_picker_row(source, "optional save folder", self.save_dir, self.pick_save).grid(
            row=3, column=0, sticky="ew", padx=10, pady=4
        )
        self._path_picker_row(source, "ISO path", self.iso_path, self.pick_iso).grid(
            row=4, column=0, sticky="ew", padx=10, pady=4
        )
        self._path_picker_row(source, "optional DATA.bin path", self.data_bin_path, self.pick_data_bin).grid(
            row=5, column=0, sticky="ew", padx=10, pady=4
        )
        self._path_picker_row(source, "workspace/output folder", self.workspace_output_dir, self.pick_workspace_output_dir, self.open_workspace_output_dir).grid(
            row=6, column=0, sticky="ew", padx=10, pady=(4, 10)
        )

        actions = ActionSection(
            source,
            "Area Server Crypto Actions / Patch Scanner",
            "Read-only scanner for Area Server metadata, crypto-relevant file evidence, and patch-planning reports; generated outputs stay in the workspace/output folder.",
            columns_at_width=[(520, 3)],
        )
        actions.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 12))
        for spec in (
            {"text": "Auto Detect", "command": self.auto_detect_load_paths},
            {"text": "Run Safe Scan", "style": "Accent.TButton", "command": self.run_scan},
            {"text": "Clear", "command": self.reset_load_files_form},
        ):
            actions.add_button(**spec)

    def _build_view_results_tab(self, f: ttk.Frame):
        """Build the grid-based read-only results browser."""
        f.grid_columnconfigure(0, weight=0, minsize=230)
        f.grid_columnconfigure(1, weight=1)
        f.grid_rowconfigure(0, weight=1)

        categories = [
            "Overview",
            "Area Server Files",
            "BIN Containers",
            "CMP Members",
            "CCS / CCSF Payloads",
            "Likely Root Town Assets",
            "Dummies / Markers",
            "Textures",
            "Models",
            "Materials",
            "Animations",
            "Lights",
            "Asset Paths",
            "Unknowns / Warnings",
        ]

        cat_card = self._card(f, "Result categories")
        cat_card.grid(row=0, column=0, sticky="ns", padx=(2, 10), pady=2)
        cat_card.grid_propagate(False)
        cat_card.configure(width=230)
        cat_card.grid_rowconfigure(0, weight=1)
        cat_card.grid_columnconfigure(0, weight=1)
        self.result_category_list = tk.Listbox(cat_card, height=14, exportselection=False)
        self.result_category_list.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        cat_scroll = ttk.Scrollbar(cat_card, orient="vertical", command=self.result_category_list.yview)
        self.result_category_list.configure(yscrollcommand=cat_scroll.set)
        cat_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        for category in categories:
            self.result_category_list.insert("end", category)
        self.result_category_list.selection_set(0)
        self.result_category_list.bind("<<ListboxSelect>>", self.on_result_category_select)

        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 2), pady=2)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        summary_row = ttk.Frame(right)
        summary_row.grid(row=0, column=0, sticky="ew")
        summary_row.grid_columnconfigure(0, weight=1)
        summary_row.grid_columnconfigure(1, weight=1)

        category_card = self._card(summary_row, "Category browser")
        category_card.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        category_card.grid_rowconfigure(0, weight=1)
        category_card.grid_columnconfigure(0, weight=1)
        self.result_category_table = ttk.Treeview(category_card, show="headings", selectmode="browse", height=8)
        self.result_category_table.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        category_scroll = ttk.Scrollbar(category_card, orient="vertical", command=self.result_category_table.yview)
        self.result_category_table.configure(yscrollcommand=category_scroll.set)
        category_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.result_category_table.bind("<<TreeviewSelect>>", self.on_result_table_select)
        self._result_table_payloads: dict[str, dict] = {}

        detail_card = self._card(summary_row, "Selected item metadata")
        detail_card.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        detail_card.grid_rowconfigure(0, weight=1)
        detail_card.grid_columnconfigure(0, weight=1)
        self.detail = tk.Text(
            detail_card,
            wrap="word",
            height=8,
            bg=self._theme["text_bg"],
            fg=self._theme["text_fg"],
            insertbackground=self._theme["text_fg"],
        )
        self.detail.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        detail_scroll = ttk.Scrollbar(detail_card, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.detail.configure(state="disabled")

        tree_card = self._card(right, "Read-only scan results")
        tree_card.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        tree_card.grid_rowconfigure(0, weight=1)
        tree_card.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_card,
            columns=("type", "gzip", "sections", "size", "paths", "TEX", "MDL", "DMY", "MAT", "ANM"),
        )
        self.tree.heading("#0", text="Name / Section")
        for col, text in [
            ("type", "Type"),
            ("gzip", "GZip"),
            ("sections", "Secs"),
            ("size", "Size"),
            ("paths", "Paths"),
            ("TEX", "TEX"),
            ("MDL", "MDL"),
            ("DMY", "DMY"),
            ("MAT", "MAT"),
            ("ANM", "ANM"),
        ]:
            self.tree.heading(col, text=text)
        self.tree.column("#0", width=340)
        for col, width, anchor in [
            ("type", 60, "center"),
            ("gzip", 40, "center"),
            ("sections", 60, "e"),
            ("size", 95, "e"),
            ("paths", 60, "e"),
            ("TEX", 55, "e"),
            ("MDL", 55, "e"),
            ("DMY", 55, "e"),
            ("MAT", 55, "e"),
            ("ANM", 55, "e"),
        ]:
            self.tree.column(col, width=width, anchor=anchor)
        yscroll = ttk.Scrollbar(tree_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        yscroll.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<ButtonRelease-1>", self._schedule_on_select)
        self.tree.bind("<KeyRelease>", self._schedule_on_select)
        self.tree.tag_configure("binrow", background=self._theme["row_bin_bg"], foreground=self._theme["fg"])
        self.tree.tag_configure("secrow", background=self._theme["row_sec_bg"], foreground=self._theme["fg"])
        self.on_result_category_select()

    def _build_export_package_tab(self, f: ttk.Frame):
        """Build the metadata-only export workflow tab."""
        f.grid_columnconfigure(0, weight=1)
        card = self._card(f, "Metadata-only upload package")
        card.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        card.grid_columnconfigure(0, weight=1)
        self._muted_help(
            card,
            "This package intentionally exports metadata only: indexes, summaries, correlation notes, and optional preview reports. It does not build patches, installers, reskins, player-economy changes, or memory-hacking payloads.",
            row=0,
        )
        options = ttk.Frame(card)
        options.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        ttk.Checkbutton(options, text="Include Area Server index metadata", variable=self.export_include_index).pack(anchor="w")
        ttk.Checkbutton(options, text="Include correlation report metadata", variable=self.export_include_correlations).pack(anchor="w")
        ttk.Checkbutton(options, text="Include ISO index metadata when available", variable=self.export_include_iso_index).pack(anchor="w")
        ttk.Checkbutton(options, text="Include binary preview metadata when available", variable=self.export_include_binary_previews).pack(anchor="w")
        ttk.Separator(options, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(options, text="ChatGPT research bundle options").pack(anchor="w")
        ttk.Checkbutton(options, text="Include local full paths (off by default)", variable=self.research_bundle_include_full_paths).pack(anchor="w")
        ttk.Checkbutton(options, text="Include extracted CCS metadata only", variable=self.research_bundle_include_ccs_metadata_only).pack(anchor="w")
        ttk.Checkbutton(options, text="Include raw/decompressed assets (UNSAFE: local-only; may include game bytes and personal data)", variable=self.research_bundle_include_raw_assets).pack(anchor="w")
        ttk.Checkbutton(options, text="Include terminal command log", variable=self.research_bundle_include_command_log).pack(anchor="w")
        self._path_picker_row(card, "Package output folder", self.workspace_output_dir, self.pick_workspace_output_dir, self.open_workspace_output_dir).grid(
            row=2, column=0, sticky="ew", padx=10, pady=(6, 10)
        )
        actions, _ = self._wrapped_button_row(
            card,
            [
                {"text": "Build Upload Package", "style": "Accent.TButton", "command": self.build_upload_package},
                {"text": "Export Research Bundle", "command": self.export_research_bundle_for_chatgpt},
                {"text": "Open Package Folder", "command": self.open_workspace_output_dir},
                {"text": "Open Bundle Folder", "command": self.open_research_bundle_folder},
                {"text": "Copy Bundle Path", "command": self.copy_research_bundle_path},
            ],
            columns_at_width=[(900, 5), (520, 2)],
        )
        actions.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 12))
        status = self._card(f, "Package status")
        status.grid(row=1, column=0, sticky="nsew", padx=2, pady=(10, 2))
        self.export_package_status = tk.Text(
            status,
            wrap="word",
            height=12,
            bg=self._theme["text_bg"],
            fg=self._theme["text_fg"],
            insertbackground=self._theme["text_fg"],
        )
        self.export_package_status.pack(fill="both", expand=True, padx=8, pady=8)
        self._replace_text(self.export_package_status, "Ready to build a metadata-only upload package.\n", append=False, readonly=True)

    # ---------- Legacy UI builders (kept for future reuse; not added to the normal Notebook) ----------




    # ---------- Simplified workflow actions ----------
    def pick_workspace_output_dir(self):
        p = filedialog.askdirectory(title="Select workspace/output folder")
        if p:
            self.workspace_output_dir.set(p)
            self._update_title_status_strip()

    def open_workspace_output_dir(self):
        path = Path(self.workspace_output_dir.get().strip() or (WORKSPACE / "upload_package"))
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))
        except Exception:
            messagebox.showinfo("Workspace/output folder", str(path))

    def auto_detect_load_paths(self):
        candidates: list[Path] = []
        for raw in (self.project_root.get().strip(), self.data_dir.get().strip(), str(ROOT), str(Path.cwd())):
            if raw:
                base = Path(raw).expanduser()
                candidates.extend([base, *base.parents])
        seen: set[Path] = set()
        detected_root: Path | None = None
        detected_data: Path | None = None
        for base in candidates:
            try:
                resolved = base.resolve()
            except Exception:
                resolved = base
            if resolved in seen:
                continue
            seen.add(resolved)
            data = resolved if resolved.name.lower() == "data" and resolved.is_dir() else resolved / "data"
            if data.is_dir():
                detected_root = data.parent
                detected_data = data
                self.project_root.set(str(detected_root))
                self.data_dir.set(str(detected_data))
                save = detected_root / "save"
                if save.is_dir():
                    self.save_dir.set(str(save))
                break

        search_roots = [p for p in (detected_data, detected_root, ROOT) if p is not None]
        if not self.data_bin_path.get().strip():
            for root in search_roots:
                for candidate in (root / "DATA.bin", root / "data" / "DATA.bin", root / "DATA.BIN"):
                    if candidate.is_file():
                        self.data_bin_path.set(str(candidate))
                        break
                if self.data_bin_path.get().strip():
                    break

        workspace = Path(self.workspace_output_dir.get().strip() or (WORKSPACE / "upload_package")).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)
        self.workspace_output_dir.set(str(workspace))
        self.index_path.set(str(workspace / "fragmenter_index.json"))
        if not self.iso_index_path.get().strip():
            self.iso_index_path.set(str(workspace / "iso_index.json"))
        if not self.iso_extract_dir.get().strip():
            self.iso_extract_dir.set(str(workspace / "iso_extract"))
        messagebox.showinfo("Auto Detect", "Auto Detect completed. Review paths before running the safe scan.")

    def run_scan(self):
        """Run the read-only Area Server metadata scan used by the simplified UI."""
        workspace = Path(self.workspace_output_dir.get().strip() or (WORKSPACE / "upload_package")).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)
        self.workspace_output_dir.set(str(workspace))
        self.index_path.set(str(workspace / "fragmenter_index.json"))
        self.build_index()

    def reset_load_files_form(self):
        self.project_root.set("")
        self.data_dir.set("")
        self.save_dir.set("")
        self.iso_path.set("")
        self.data_bin_path.set("")
        self.index_path.set(str(ROOT / "fragmenter_index.json"))
        self.iso_index_path.set(str(ROOT / "iso_index.json"))
        self.iso_extract_dir.set(str(ROOT / "iso_extract"))
        self.workspace_output_dir.set(str(WORKSPACE / "upload_package"))
        if hasattr(self, "tree"):
            self.tree.delete(*self.tree.get_children())
        if hasattr(self, "detail"):
            self._replace_text(self.detail, "Select a BIN or SECTION to see details.\n", readonly=True)
        if hasattr(self, "result_category_table"):
            self.on_result_category_select()

    def pick_area_crypto_input(self) -> None:
        path = filedialog.askopenfilename(title="Choose Area Server crypto input", filetypes=[("All files", "*.*")])
        if path:
            self.area_crypto_input_path.set(path)

    def pick_area_crypto_output(self) -> None:
        path = filedialog.asksaveasfilename(title="Choose Area Server crypto output", initialfile=Path(self.area_crypto_output_path.get() or "area_server_crypto_out.bin").name, filetypes=[("All files", "*.*")])
        if path:
            self.area_crypto_output_path.set(path)

    def pick_area_encrypt_key_from(self) -> None:
        path = filedialog.askopenfilename(title="Choose encrypted file to copy key metadata from", filetypes=[("All files", "*.*")])
        if path:
            self.area_encrypt_key_from_path.set(path)

    def pick_area_patch_exe(self) -> None:
        initial = self._default_area_server_exe()
        path = filedialog.askopenfilename(
            title="Choose Area Server executable",
            initialdir=str(initial.parent) if initial else None,
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.area_patch_exe_path.set(path)

    def _default_area_server_exe(self) -> Path | None:
        if self.area_patch_exe_path.get().strip():
            return Path(self.area_patch_exe_path.get().strip()).expanduser()
        root = Path(self.project_root.get().strip()).expanduser() if self.project_root.get().strip() else None
        if not root:
            return None
        for name in ("areasrv.exe", "AreaServer.exe", "area_server.exe"):
            candidate = root / name
            if candidate.is_file():
                self.area_patch_exe_path.set(str(candidate))
                return candidate
        matches = sorted(root.glob("*.exe"))
        if matches:
            self.area_patch_exe_path.set(str(matches[0]))
            return matches[0]
        return root / "areasrv.exe"

    def _ensure_area_tool_path(self, variable: tk.StringVar, label: str, must_exist: bool = True) -> Path | None:
        raw = variable.get().strip()
        if not raw:
            messagebox.showerror("Missing input", f"Choose {label} first.")
            return None
        path = Path(raw).expanduser()
        if must_exist and not path.exists():
            messagebox.showerror("Missing input", f"Could not find {label}:\n{path}")
            return None
        return path

    def _area_report_paths(self, stem: str) -> tuple[Path, Path]:
        reports = self._selected_workspace() / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        return reports / f"{stem}.json", reports / f"{stem}.txt"

    def run_area_identify_encrypted(self) -> None:
        input_path = self._ensure_area_tool_path(self.area_crypto_input_path, "the input file")
        if input_path is None:
            return
        self.area_server_tools_status.set("Running area-identify-encrypted.")
        self._run_task([PY, str(ROOT / "fragmenter.py"), "area-identify-encrypted", str(input_path)], label="area-identify-encrypted")

    def run_area_decrypt(self) -> None:
        input_path = self._ensure_area_tool_path(self.area_crypto_input_path, "the encrypted input file")
        output_path = self._ensure_area_tool_path(self.area_crypto_output_path, "the output file", must_exist=False)
        if input_path is None or output_path is None:
            return
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.area_server_tools_status.set("Running area-decrypt; writing a new output file.")
        self._run_task([PY, str(ROOT / "fragmenter.py"), "area-decrypt", str(input_path), "--out", str(output_path)], label="area-decrypt")

    def run_area_encrypt(self) -> None:
        input_path = self._ensure_area_tool_path(self.area_crypto_input_path, "the plain input file")
        output_path = self._ensure_area_tool_path(self.area_crypto_output_path, "the output file", must_exist=False)
        if input_path is None or output_path is None:
            return
        cmd = [PY, str(ROOT / "fragmenter.py"), "area-encrypt", str(input_path), "--out", str(output_path)]
        key_from = self.area_encrypt_key_from_path.get().strip()
        filekey_hex = self.area_encrypt_filekey_hex.get().strip()
        if key_from:
            key_path = self._ensure_area_tool_path(self.area_encrypt_key_from_path, "the key-from file")
            if key_path is None:
                return
            cmd.extend(["--key-from", str(key_path)])
        elif filekey_hex:
            cmd.extend(["--filekey-hex", filekey_hex])
        else:
            return messagebox.showerror("Missing key", "Provide either an encrypt key-from file or a filekey hex value.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.area_server_tools_status.set("Running area-encrypt; writing a new output file.")
        self._run_task(cmd, label="area-encrypt")

    def run_area_patch_scan(self) -> None:
        exe = self._default_area_server_exe()
        if exe is not None:
            self.area_patch_exe_path.set(str(exe))
        exe_path = self._ensure_area_tool_path(self.area_patch_exe_path, "areasrv.exe")
        if exe_path is None:
            return
        out_json, out_text = self._area_report_paths("area_server_patch_scan")
        cmd = [PY, str(ROOT / "fragmenter.py"), "scan-area-server-patches", str(exe_path), "--out", str(out_json), "--text-out", str(out_text)]

        def _done(rc: int) -> None:
            if rc == 0:
                self.area_server_tools_status.set(f"Patch scan report written to {out_text}")
                if out_text.exists() and "Report" in self.preview_tabs:
                    self._replace_text(self.preview_tabs["Report"], out_text.read_text(encoding="utf-8", errors="replace"), readonly=True)
                    self.nb.select(self.preview_tabs["Report"].master)
                self.refresh_expected_reports_panel()

        self.area_server_tools_status.set("Running scan-area-server-patches in scan-only mode.")
        self._run_task(cmd, on_done=_done, label="scan-area-server-patches")

    def open_area_crypto_output_folder(self) -> None:
        path = Path(self.area_crypto_output_path.get().strip() or self._selected_workspace()).expanduser()
        self._open_folder_path(path if path.is_dir() else path.parent)

    def on_result_category_select(self, _evt=None):
        if not hasattr(self, "result_category_list") or not hasattr(self, "result_category_table"):
            return
        sel = self.result_category_list.curselection()
        category = self.result_category_list.get(sel[0]) if sel else "Overview"
        self._populate_result_table(category)

    def on_result_table_select(self, _evt=None):
        if not hasattr(self, "result_category_table") or not hasattr(self, "detail"):
            return
        selection = self.result_category_table.selection()
        if not selection:
            return
        payload = self._result_table_payloads.get(selection[0], {})
        self._replace_text(self.detail, self._truncate_blob(json.dumps(payload, indent=2)), readonly=True)
        self._update_selection_inspector(payload)

    def _result_table_columns(self, category: str) -> list[tuple[str, str, int, str]]:
        if category == "Area Server Files":
            return [("path", "Path", 280, "w"), ("type", "Type", 80, "center"), ("size", "Size", 90, "e"), ("sections", "Sections", 80, "e"), ("confidence", "Confidence", 90, "center")]
        if category == "CCS / CCSF Payloads":
            return [("section_id", "Section ID", 120, "w"), ("source_file", "Source file", 220, "w"), ("TEX", "TEX", 55, "e"), ("MDL", "MDL", 55, "e"), ("DMY", "DMY", 55, "e"), ("MAT", "MAT", 55, "e"), ("ANM", "ANM", 55, "e")]
        if category == "Asset Paths":
            return [("path", "Path", 300, "w"), ("stem", "Stem", 150, "w"), ("type", "Type", 90, "center"), ("source_section", "Source section", 180, "w")]
        return [("name", "Name", 180, "w"), ("source", "Source", 240, "w"), ("confidence", "Confidence", 90, "center"), ("notes", "Notes", 260, "w")]

    def _count_symbols(self, section: dict, prefix: str) -> int:
        counts = section.get("counts", {}) or {}
        total = 0
        for key, value in counts.items():
            if str(key).upper().startswith(prefix.upper()):
                try:
                    total += int(value)
                except (TypeError, ValueError):
                    total += 1
        return total

    def _asset_type_from_path(self, value: str) -> str:
        suffix = Path(value).suffix.lower().lstrip(".")
        if suffix:
            return suffix.upper()
        lower = value.lower()
        for token in ("tex", "mdl", "dmy", "mat", "anm", "ccs", "ccsf"):
            if token in lower:
                return token.upper()
        return "unknown"

    def _result_table_rows(self, category: str) -> list[dict]:
        files = (self.index or {}).get("files", []) if isinstance(self.index, dict) else []
        if category == "Overview":
            sections = [s for f in files for s in f.get("sections", [])]
            warnings = [f for f in files if "error" in f]
            return [{"name": "Index summary", "source": self.index_path.get() or "(index not set)", "confidence": "high" if files or sections else "pending scan", "notes": f"files={len(files)}; sections={len(sections)}; warnings={len(warnings)}"}]
        if category == "Area Server Files":
            return [
                {
                    "path": f.get("file", f.get("name", "(unknown path)")),
                    "type": "ERR" if "error" in f else "BIN",
                    "size": f.get("raw_size") or f.get("decompressed_size") or "",
                    "sections": f.get("section_count", len(f.get("sections", []) or [])),
                    "confidence": "low" if "error" in f else "high",
                    "_payload": f,
                }
                for f in files
            ]
        if category == "CCS / CCSF Payloads":
            rows = []
            for file_info in files:
                for section in file_info.get("sections", []) or []:
                    if not self._result_section_matches(section, "ccs", "ccsf"):
                        continue
                    rows.append({
                        "section_id": section.get("id", "(section)"),
                        "source_file": file_info.get("name", file_info.get("file", "(unknown)")),
                        "TEX": self._count_symbols(section, "TEX"),
                        "MDL": self._count_symbols(section, "MDL"),
                        "DMY": self._count_symbols(section, "DMY"),
                        "MAT": self._count_symbols(section, "MAT"),
                        "ANM": self._count_symbols(section, "ANM"),
                        "_payload": {"file": file_info, "section": section},
                    })
            return rows
        if category == "Asset Paths":
            rows = []
            for file_info in files:
                for section in file_info.get("sections", []) or []:
                    paths = section.get("asset_paths") or section.get("asset_paths_sample") or []
                    for value in paths:
                        text = str(value)
                        rows.append({"path": text, "stem": Path(text).stem, "type": self._asset_type_from_path(text), "source_section": f"{file_info.get('name', '(unknown)')}:{section.get('id', '(section)')}", "_payload": {"path": text, "file": file_info, "section": section}})
            return rows
        if category in {"BIN Containers", "Unknowns / Warnings"}:
            source = [f for f in files if ("error" in f) == (category == "Unknowns / Warnings")]
            return [{"name": f.get("name", "(unknown)"), "source": f.get("file", "(unknown path)"), "confidence": "low" if "error" in f else "high", "notes": f.get("error") or f"gzip={'yes' if f.get('gzip') else 'no'}; sections={f.get('section_count', 0)}; size={f.get('decompressed_size', 0)}", "_payload": f} for f in source]
        section_categories = {
            "CMP Members": ("cmp",),
            "Likely Root Town Assets": ("root", "town", "fortouph", "fort_ouph", "sr04", "ccsftown"),
            "Dummies / Markers": ("dmy", "dummy", "marker"),
            "Textures": ("tex", "texture"),
            "Models": ("mdl", "model", "submodel", "clump", "clp", "obj", "object", "hit", "collision", "collider", "mesh"),
            "Materials": ("mat", "material"),
            "Animations": ("anm", "anim", "animation"),
            "Lights": ("lit", "light"),
        }
        if category in section_categories:
            items, _total = self._section_result_items(category, *section_categories[category])
            return [{"name": i.get("name", ""), "source": i.get("source", ""), "confidence": i.get("confidence", ""), "notes": i.get("notes", ""), "_payload": i} for i in items]
        return []

    def _populate_result_table(self, category: str):
        table = self.result_category_table
        columns = self._result_table_columns(category)
        col_ids = [col for col, _heading, _width, _anchor in columns]
        table.delete(*table.get_children())
        table.configure(columns=col_ids)
        self._result_table_payloads = {}
        for col, heading, width, anchor in columns:
            table.heading(col, text=heading)
            table.column(col, width=width, anchor=anchor, stretch=(col in {"path", "source", "source_file", "notes", "name"}))
        rows = self._result_table_rows(category)
        if not rows:
            empty = {col: "" for col in col_ids}
            empty[col_ids[0]] = self._result_empty_message(category).strip().replace("\n", " ")
            rows = [empty]
        for idx, row in enumerate(rows):
            payload = row.get("_payload", row)
            iid = table.insert("", "end", values=[row.get(col, "") for col in col_ids])
            self._result_table_payloads[iid] = {k: v for k, v in payload.items()} if isinstance(payload, dict) else {"value": payload}
        children = table.get_children()
        if children:
            table.selection_set(children[0])
            table.focus(children[0])
            self.on_result_table_select()

    def _section_count(self, sections: list[dict], *needles: str) -> int:
        total = 0
        lowered = tuple(n.lower() for n in needles)
        for section in sections:
            counts = section.get("counts", {}) or {}
            tops = section.get("tops", {}) or {}
            for key, value in counts.items():
                if any(n in str(key).lower() for n in lowered):
                    try:
                        total += int(value)
                    except (TypeError, ValueError):
                        total += 1
            for key, values in tops.items():
                if any(n in str(key).lower() for n in lowered):
                    total += len(values) if isinstance(values, list) else 1
        return total

    def _result_empty_message(self, category: str) -> str:
        return f"{category}: no items found yet.\nRun a safe scan or load an index, then reselect this category.\n"

    def _section_related_strings(self, section: dict, limit: int = 12) -> list[str]:
        related: list[str] = []
        for value in section.get("asset_paths_sample", []) or []:
            related.append(str(value))
        for values in (section.get("tops", {}) or {}).values():
            if isinstance(values, list):
                related.extend(str(v) for v in values)
        seen: set[str] = set()
        out: list[str] = []
        for value in related:
            if value and value not in seen:
                seen.add(value)
                out.append(value)
            if len(out) >= limit:
                break
        return out

    def _result_section_matches(self, section: dict, *needles: str) -> bool:
        haystack = " ".join(
            [
                str(section.get("id", "")),
                " ".join(str(v) for v in self._section_related_strings(section, limit=40)),
                " ".join(str(k) for k in (section.get("counts", {}) or {}).keys()),
            ]
        ).lower()
        return any(needle.lower() in haystack for needle in needles)

    def _result_town_linkage(self, file_info: dict, section: dict) -> str:
        name = str(file_info.get("name") or file_info.get("file") or "")
        section_id = str(section.get("id", ""))
        related = " ".join(self._section_related_strings(section, limit=40))
        haystack = f"{name} {section_id} {related}".lower()
        if any(token in haystack for token in ("town", "root", "fortouph", "fort_ouph", "sr04", "ccsftown")):
            return "linked candidate (town/root clue present)"
        return "not identified"

    def _format_result_items(self, category: str, items: list[dict], total_count: int | None = None) -> str:
        count = len(items) if total_count is None else total_count
        if not items and count <= 0:
            return self._result_empty_message(category)
        lines = [f"{category}", "=" * len(category), f"Count: {count}", ""]
        for idx, item in enumerate(items[:60], 1):
            lines.append(f"{idx}. {item.get('name', '(unnamed)')}")
            lines.append(f"   Source: {item.get('source', '(unknown)')}")
            lines.append(f"   Confidence: {item.get('confidence', 'unknown')}")
            lines.append(f"   Notes: {item.get('notes', 'No notes available.')}")
            related = item.get("related") or []
            lines.append("   Related strings/stems: " + (", ".join(map(str, related[:12])) if related else "none found yet"))
            lines.append(f"   Town candidate linkage: {item.get('town_linkage', 'not identified')}")
        if len(items) > 60:
            lines.append(f"\n... {len(items) - 60} more item(s) not shown.")
        return "\n".join(lines) + "\n"

    def _section_result_items(self, category: str, *needles: str) -> tuple[list[dict], int]:
        files = (self.index or {}).get("files", []) if isinstance(self.index, dict) else []
        items: list[dict] = []
        total = 0
        for file_info in files:
            for section in file_info.get("sections", []) or []:
                if not self._result_section_matches(section, *needles):
                    continue
                section_total = self._section_count([section], *needles)
                total += section_total or 1
                related = self._section_related_strings(section)
                items.append(
                    {
                        "name": section.get("id", "(section)"),
                        "source": f"{file_info.get('name', '(unknown file)')} @ {section.get('offset', '?')}-{section.get('end', '?')}",
                        "confidence": "high" if section_total else "medium",
                        "notes": (
                            f"size={section.get('size', 0)} bytes; "
                            f"asset paths={section.get('asset_paths_count', 0)}; "
                            f"matching symbols/strings={section_total or 'clue-only'}"
                        ),
                        "related": related,
                        "town_linkage": self._result_town_linkage(file_info, section),
                    }
                )
        return items, total


    def _root_town_highlights_from_scan(self) -> list[dict]:
        """Return normalized root-town highlight rows from the loaded index and scan summary."""
        target_prefixes = ("TEX_", "MDL_", "DMY_", "MAT_", "ANM_")
        sample_stems = ("sr4bac1", "sr4town1", "sr4tre1", "sr4clo1", "sr4clo2")

        def norm_text(value) -> str:
            return str(value or "")

        def prefix_counts_from_section(section: dict) -> dict[str, int]:
            counts = {prefix.rstrip("_"): 0 for prefix in target_prefixes}
            raw_counts = section.get("counts", {}) or section.get("category_prefix_counts", {}) or {}
            for prefix in target_prefixes:
                short = prefix.rstrip("_")
                for key in (prefix, short):
                    if key in raw_counts:
                        try:
                            counts[short] += int(raw_counts.get(key) or 0)
                        except (TypeError, ValueError):
                            pass
                tops = (section.get("tops", {}) or {}).get(prefix) or (section.get("tops", {}) or {}).get(short)
                if not counts[short] and isinstance(tops, list):
                    counts[short] = len(tops)
            return counts

        def related_samples(section: dict) -> list[str]:
            values: list[str] = []
            for key in ("asset_paths_sample", "asset_path_samples", "asset_paths", "samples"):
                raw = section.get(key)
                if isinstance(raw, list):
                    values.extend(norm_text(v) for v in raw)
            for values_list in (section.get("tops", {}) or {}).values():
                if isinstance(values_list, list):
                    values.extend(norm_text(v) for v in values_list)
            selected: list[str] = []
            seen: set[str] = set()
            lower_values = [(v, v.lower()) for v in values if v]
            for stem in sample_stems:
                for value, lower in lower_values:
                    if stem in lower and value not in seen:
                        selected.append(value)
                        seen.add(value)
                        break
            for value, _lower in lower_values:
                if value not in seen:
                    selected.append(value)
                    seen.add(value)
                if len(selected) >= 8:
                    break
            return selected

        rows: list[dict] = []
        seen_keys: set[tuple[str, str, str]] = set()

        files = (self.index or {}).get("files", []) if isinstance(self.index, dict) else []
        for file_info in files:
            name = norm_text(file_info.get("name") or file_info.get("file"))
            file_path = norm_text(file_info.get("file") or name)
            file_haystack = f"{name} {file_path}".lower()
            for section in file_info.get("sections", []) or []:
                section_id = norm_text(section.get("id") or "(section)")
                samples = related_samples(section)
                haystack = " ".join([file_haystack, section_id.lower(), " ".join(samples).lower()])
                detected = (
                    "data/town.bin" in haystack
                    or "town.bin" in file_haystack
                    or "town04.cmp" in haystack
                    or "town04d.cmp" in haystack
                    or "ccsftown04" in haystack
                    or "ccsftown04d" in haystack
                )
                if not detected:
                    continue
                key = (file_path, section_id, norm_text(section.get("offset")))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                counts = prefix_counts_from_section(section)
                metadata_target = any(token in haystack for token in ("town04.cmp", "town04d.cmp", "ccsftown04", "ccsftown04d"))
                rows.append({
                    "section": section_id,
                    "source": file_path,
                    "counts": counts,
                    "confidence": "confirmed metadata target" if metadata_target else "probable town.bin candidate",
                    "samples": samples,
                })

        summary_path = self._find_report_path("fragmenter_scan_summary.json") or (
            self._active_workspace_root() / "reports" / "fragmenter_scan_summary.json"
        )
        if summary_path.exists():
            try:
                scan = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                scan = {}
            for clue in ((scan.get("findings") or {}).get("embedded_cmp_member_summary") or {}).get("town_bin_candidates", []):
                source = norm_text(clue.get("file") or "data/town.bin")
                name = norm_text(clue.get("gzip_original_filename") or clue.get("highlight_labels") or "town.bin member")
                haystack = f"{source} {name}".lower()
                if not any(t in haystack for t in ("town.bin", "town04.cmp", "town04d.cmp", "ccsftown04", "ccsftown04d")):
                    continue
                key = (source, name, norm_text(clue.get("offset")))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append({
                    "section": name,
                    "source": source,
                    "counts": {prefix: 0 for prefix in ("TEX", "MDL", "DMY", "MAT", "ANM")},
                    "confidence": "confirmed metadata target" if any(t in haystack for t in ("town04.cmp", "town04d.cmp", "ccsftown04", "ccsftown04d")) else norm_text(clue.get("confidence") or "probable town.bin candidate"),
                    "samples": [],
                })
        return rows

    def _format_root_town_highlights_table(self, rows: list[dict]) -> str:
        if not rows:
            return self._result_empty_message("Likely Root Town Assets")
        lines = ["Likely Root Town Assets", "=======================", f"Count: {len(rows)}", ""]
        lines.append("Section | Source | TEX | MDL | DMY | MAT | ANM | Confidence | Sample asset paths")
        lines.append("--- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---")
        for row in rows[:80]:
            counts = row.get("counts", {}) or {}
            samples = ", ".join(row.get("samples") or []) or "(none captured)"
            lines.append(
                f"{row.get('section', '(section)')} | {row.get('source', '(unknown)')} | "
                f"{counts.get('TEX', 0)} | {counts.get('MDL', 0)} | {counts.get('DMY', 0)} | "
                f"{counts.get('MAT', 0)} | {counts.get('ANM', 0)} | {row.get('confidence', 'unknown')} | {samples}"
            )
        if len(rows) > 80:
            lines.append(f"\n... {len(rows) - 80} more row(s) not shown.")
        return "\n".join(lines) + "\n"

    def _format_root_town_metadata_table(self, metadata_rows: list[dict], highlight_rows: list[dict]) -> str:
        lines = [
            "Root Town Structured Metadata",
            "=============================",
            f"Metadata rows: {len(metadata_rows)}",
            f"Imported highlight rows: {len(highlight_rows)}",
            "",
            "Identifier | Family | Relationship | Appearance | Offset | Confidence | Semantic explanation | Workbook/client crosslink",
            "--- | --- | --- | --- | --- | --- | --- | ---",
        ]
        for row in metadata_rows:
            lines.append(
                " | ".join(
                    str(row.get(key) or ("not imported" if key == "crosslink" else "n/a")).replace("\n", " ")
                    for key in ("identifier", "family", "relationship", "appearance", "offset", "confidence", "semantic", "crosslink")
                )
            )
        lines.extend(["", self._format_root_town_highlights_table(highlight_rows).rstrip()])
        return "\n".join(lines) + "\n"

    def _result_category_summary(self, category: str) -> str:
        files = (self.index or {}).get("files", []) if isinstance(self.index, dict) else []
        sections = [s for f in files for s in f.get("sections", [])]
        warnings = [f for f in files if "error" in f]
        section_categories = {
            "CMP Members": ("cmp",),
            "CCS / CCSF Payloads": ("ccs", "ccsf"),
            "Likely Root Town Assets": ("root", "town", "fortouph", "fort_ouph", "sr04", "ccsftown"),
            "Dummies / Markers": ("dmy", "dummy", "marker"),
            "Textures": ("tex", "texture"),
            "Models": ("mdl", "model", "submodel", "clump", "clp", "obj", "object", "hit", "collision", "collider", "mesh"),
            "Materials": ("mat", "material"),
            "Animations": ("anm", "anim", "animation"),
            "Lights": ("lit", "light"),
            "Asset Paths": ("asset", "path", "npc", "script", "location", "loc", "event", "quest"),
        }
        root_town_rows = self._root_town_highlights_from_scan()
        overview_town_lines = [
            "",
            "ROOT TOWN HIGHLIGHTS",
            "====================",
            "data/town.bin: " + ("detected" if any("town.bin" in str(r.get("source", "")).lower() for r in root_town_rows) else "not detected yet"),
            "CCSFtown04: " + ("detected" if any("ccsftown04" == str(r.get("section", "")).lower() or "town04.cmp" in (" ".join(r.get("samples") or []) + " " + str(r.get("source", ""))).lower() for r in root_town_rows) else "not detected yet"),
            "CCSFtown04d: " + ("detected" if any("ccsftown04d" == str(r.get("section", "")).lower() or "town04d.cmp" in (" ".join(r.get("samples") or []) + " " + str(r.get("source", ""))).lower() for r in root_town_rows) else "not detected yet"),
            f"Highlighted town sections: {len(root_town_rows)}",
        ]
        summaries = {
            "Overview": (
                f"Area Server root folder: {self.project_root.get() or '(not set)'}\n"
                f"Area Server data folder: {self.data_dir.get() or '(not set)'}\n"
                f"Workspace/output folder: {self.workspace_output_dir.get() or '(not set)'}\n"
                f"Indexed Area Server files: {len(files)}\n"
                f"Indexed CCS/CCSF sections: {len(sections)}\n"
                f"Unknowns / warnings: {len(warnings)}\n"
                f"Source: {self.index_path.get() or '(index not set)'}\n"
                f"Confidence: {'high' if files or sections else 'pending scan'}\n"
                "Notes: Select a category for item-level source, confidence, related strings/stems, and town candidate linkage.\n"
                "Related strings/stems: overview\n"
                "Town candidate linkage: see Likely Root Town Assets.\n"
                + "\n".join(overview_town_lines) + "\n"
            ),
            "Area Server Files": self._format_result_items(
                "Area Server Files",
                [
                    {
                        "name": f.get("name", "(unknown)"),
                        "source": f.get("file", "(unknown path)"),
                        "confidence": "high" if "error" not in f else "low",
                        "notes": (
                            f"root={self.project_root.get() or '(not set)'}; "
                            f"data={self.data_dir.get() or '(not set)'}; "
                            f"save={self.save_dir.get() or '(optional / not set)'}"
                        ),
                        "related": [Path(str(f.get("name", ""))).stem],
                        "town_linkage": "linked candidate (town/root filename)" if any(t in str(f.get("name", "")).lower() for t in ("town", "root")) else "not identified",
                    }
                    for f in files
                ],
            ),
            "BIN Containers": self._format_result_items(
                "BIN Containers",
                [
                    {
                        "name": f.get("name", "(unknown)"),
                        "source": f.get("file", "(unknown path)"),
                        "confidence": "high" if "error" not in f else "low",
                        "notes": (
                            f"gzip={'yes' if f.get('gzip') else 'no'}; "
                            f"sections={f.get('section_count', 0)}; "
                            f"raw size={f.get('raw_size', 0)}; decompressed size={f.get('decompressed_size', 0)}"
                        ),
                        "related": [Path(str(f.get("name", ""))).stem],
                        "town_linkage": "linked candidate (town/root filename)" if any(t in str(f.get("name", "")).lower() for t in ("town", "root")) else "not identified",
                    }
                    for f in files
                    if "error" not in f
                ],
            ),
            "Unknowns / Warnings": self._format_result_items(
                "Unknowns / Warnings",
                [
                    {
                        "name": f.get("name", "(unknown)"),
                        "source": f.get("file", "(unknown path)"),
                        "confidence": "high",
                        "notes": f.get("error", "Warning recorded by indexer."),
                        "related": [Path(str(f.get("name", ""))).stem],
                        "town_linkage": "linked candidate (town/root filename)" if any(t in str(f.get("name", "")).lower() for t in ("town", "root")) else "not identified",
                    }
                    for f in warnings
                ],
            ),
        }
        if category == "Likely Root Town Assets":
            return self._format_root_town_highlights_table(root_town_rows)
        if category in section_categories:
            items, total = self._section_result_items(category, *section_categories[category])
            return self._format_result_items(category, items, total)
        return summaries.get(category, "No summary available for this category.\n")

    def _safe_bundle_value(self, value: object, include_full_paths: bool) -> object:
        """Return a bundle-safe representation that avoids personal paths by default."""
        if isinstance(value, Path):
            value = str(value)
        if isinstance(value, str):
            expanded = value.strip()
            if not expanded:
                return expanded
            if include_full_paths:
                return expanded
            path = Path(expanded)
            if path.is_absolute() or "/" in expanded or "\\" in expanded:
                return path.name or "(path omitted)"
            return expanded
        if isinstance(value, list):
            return [self._safe_bundle_value(item, include_full_paths) for item in value]
        if isinstance(value, dict):
            return {str(key): self._safe_bundle_value(item, include_full_paths) for key, item in value.items()}
        return value

    def _safe_bundle_text(self, text: str, include_full_paths: bool) -> str:
        if include_full_paths:
            return text

        def redact(match: re.Match[str]) -> str:
            raw = match.group(0).rstrip(".,;:)")
            suffix = match.group(0)[len(raw):]
            return (Path(raw).name or "(path omitted)") + suffix

        return re.sub(r"(?<![A-Za-z0-9_])(?:/[^\s,;:)]+)+", redact, text)

    def _research_bundle_git_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=3,
            )
        except Exception:
            return None
        commit = result.stdout.strip()
        return commit if result.returncode == 0 and commit else None

    def _research_bundle_launcher_rollup(self, include_full_paths: bool) -> tuple[list[dict], list[dict], list[dict]]:
        commands: list[dict] = []
        failed: list[dict] = []
        successful: list[dict] = []
        for launcher_id, state in sorted(self.research_launcher_state.items()):
            if not state:
                continue
            command_list = state.get("command_list") or []
            entry = {
                "launcher_id": launcher_id,
                "name": self.research_launchers.get(launcher_id, {}).get("name", launcher_id),
                "command": self._safe_bundle_value(command_list, include_full_paths),
                "cwd": self._safe_bundle_value(state.get("cwd", ""), include_full_paths),
                "started_at": state.get("started_at"),
                "ended_at": state.get("ended_at"),
                "exit_code": state.get("exit_code"),
            }
            commands.append(entry)
            try:
                exit_code = int(state.get("exit_code"))
            except (TypeError, ValueError):
                continue
            target = successful if exit_code == 0 else failed
            target.append(
                {
                    "launcher_id": launcher_id,
                    "name": entry["name"],
                    "exit_code": exit_code,
                    "generated_output_paths": self._safe_bundle_value(state.get("generated_output_paths", []), include_full_paths),
                    "report": self._safe_bundle_value(state.get("report", ""), include_full_paths),
                }
            )
        return commands, failed, successful

    def _write_chatgpt_research_bundle_files(self, bundle_stage: Path, manifest: dict, include_command_log: bool, workspace: Path) -> None:
        (bundle_stage / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        txt_path, json_path = self._write_root_town_summary(workspace)
        (bundle_stage / "root_town_summary.txt").write_text(txt_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8", newline="\n")
        (bundle_stage / "root_town_summary.json").write_text(json_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8", newline="\n")
        diagnostics = ""
        if hasattr(self, "launcher_diagnostics"):
            diagnostics = self.launcher_diagnostics.get("1.0", "end-1c")
        if not diagnostics.strip():
            diagnostics = json.dumps(self._safe_bundle_value(self.research_launcher_state, False), indent=2, ensure_ascii=False)
        diagnostics = self._safe_bundle_text(diagnostics, bool(manifest.get("options", {}).get("include_local_full_paths")))
        (bundle_stage / "launcher_diagnostics.txt").write_text(diagnostics, encoding="utf-8", newline="\n")
        readme = [
            "Fragmenter Research Bundle for ChatGPT",
            "======================================",
            "",
            "This bundle is intended for safe research discussion. By default it contains text/JSON metadata, generated summaries, and diagnostics only.",
            "It should not contain ISO bytes, raw game asset bytes, decompressed CCS payloads, secrets, or personal full paths unless you explicitly enabled unsafe/local-only options.",
            "",
            "Start with manifest.json, root_town_summary.txt, and the files under reports/.",
        ]
        (bundle_stage / "chatgpt_readme.txt").write_text("\n".join(readme) + "\n", encoding="utf-8", newline="\n")
        if include_command_log:
            lines = ["Terminal command log", "====================", ""]
            for command in manifest.get("commands_run", []):
                lines.append(f"- {command.get('name')}: {command.get('command')} (exit={command.get('exit_code')})")
            (bundle_stage / "command_log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def _display_research_bundle_result(self, result: dict[str, object]) -> None:
        lines = [
            "Research Bundle Export",
            "======================",
            f"Status: {result.get('status')}",
            f"Destination folder: {result.get('destination_folder')}",
            f"Bundle filename: {result.get('bundle_filename')}",
            f"Bundle path: {result.get('bundle_path')}",
            "",
            "Included files:",
        ]
        included = result.get("included_files") or []
        lines.extend(f"- {item}" for item in included)
        if not included:
            lines.append("- none")
        lines.extend(["", "Skipped files:"])
        skipped = result.get("skipped_files") or []
        lines.extend(f"- {item}" for item in skipped)
        if not skipped:
            lines.append("- none")
        lines.extend(["", "Errors:"])
        errors = result.get("errors") or []
        lines.extend(f"- {item}" for item in errors)
        if not errors:
            lines.append("- none")
        text = "\n".join(str(line) for line in lines) + "\n"
        for attr in ("research_bundle_status", "export_package_status"):
            widget = getattr(self, attr, None)
            if widget:
                self._replace_text(widget, text, append=(attr == "export_package_status"), readonly=True)
        self.resource_preview_message.set(f"Research bundle export: {result.get('status')} — {result.get('bundle_path')}")

    def _write_research_bundle_failure_log(self, workspace: Path, zip_path: Path, exc: Exception, included: list[str], skipped: list[str]) -> Path:
        logs_dir = workspace / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"research_bundle_export_error_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
        payload = {
            "timestamp_utc": _utc_timestamp(),
            "destination_folder": str(zip_path.parent),
            "bundle_filename": zip_path.name,
            "bundle_path": str(zip_path),
            "included_files": included,
            "skipped_files": skipped,
            "error": repr(exc),
        }
        log_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return log_path

    def export_research_bundle_for_chatgpt(self) -> None:
        include_full_paths = bool(self.research_bundle_include_full_paths.get())
        include_raw_assets = bool(self.research_bundle_include_raw_assets.get())
        include_command_log = bool(self.research_bundle_include_command_log.get())
        if include_raw_assets and not messagebox.askyesno(
            "Unsafe local-only export",
            "Raw/decompressed assets may include copyrighted game bytes and local data. Only use this for local/private analysis. Continue?",
        ):
            return

        workspace = self._ensure_research_workspace()
        bundle_dir = workspace / "bundles"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        zip_path = bundle_dir / f"fragmenter_research_bundle_{timestamp}.zip"
        stage = workspace / "tmp" / f"fragmenter_research_bundle_{timestamp}"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, exist_ok=True)

        reports_dir = workspace / "reports"
        logs_dir = workspace / "logs"
        generated_reports: list[str] = []
        missing_reports: list[str] = []
        included_files: list[str] = []
        skipped_files: list[str] = []
        errors: list[str] = []
        for spec in self._expected_report_registry():
            path = spec["path"](workspace)
            if path.exists():
                generated_reports.append(path.name)
            else:
                missing_reports.append(str(spec.get("name", "(unknown report)")))
                skipped_files.append(f"missing expected report: {spec.get('name', '(unknown report)')}")
        commands, failed, successful = self._research_bundle_launcher_rollup(include_full_paths)
        manifest = {
            "schema": "fragmenter.chatgpt_research_bundle.v1",
            "timestamp_utc": _utc_timestamp(),
            "git_commit": self._research_bundle_git_commit(),
            "python_version": sys.version,
            "os": platform.platform(),
            "iso": {"basename": Path(self.iso_path.get().strip()).name} if self.iso_path.get().strip() else None,
            "area_server": (
                {
                    "basename": Path(self.project_root.get().strip()).name,
                    "path": self._safe_bundle_value(self.project_root.get().strip(), include_full_paths),
                }
                if include_full_paths and self.project_root.get().strip()
                else None
            ),
            "options": {
                "include_local_full_paths": include_full_paths,
                "include_extracted_ccs_metadata_only": bool(self.research_bundle_include_ccs_metadata_only.get()),
                "include_raw_decompressed_assets": include_raw_assets,
                "include_terminal_command_log": include_command_log,
            },
            "generated_report_list": sorted(set(generated_reports)),
            "missing_report_list": sorted(set(missing_reports)),
            "commands_run": commands,
            "failed_launchers": failed,
            "successful_launchers": successful,
            "safety_notes": [
                "Default export excludes ISO bytes, raw game asset bytes, decompressed CCS payloads, personal paths, and secrets.",
                "Only workspace/reports/*.txt, workspace/reports/*.json, workspace/logs/*.txt, workspace/fragmenter_project.json, and generated bundle metadata are included by default.",
            ],
        }
        try:
            self._write_chatgpt_research_bundle_files(stage, manifest, include_command_log, workspace)

            for source_dir, subdir in ((reports_dir, "reports"), (logs_dir, "logs")):
                if not source_dir.exists():
                    skipped_files.append(f"missing folder: {source_dir}")
                    continue
                for path in sorted(source_dir.glob("*.txt")) + sorted(source_dir.glob("*.json")):
                    target = stage / subdir / path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8", newline="\n")
            project_json = workspace / "fragmenter_project.json"
            if project_json.exists():
                (stage / "fragmenter_project.json").write_text(project_json.read_text(encoding="utf-8", errors="replace"), encoding="utf-8", newline="\n")
            else:
                skipped_files.append(f"missing project metadata: {project_json.name}")
            if include_raw_assets:
                extracted = workspace / "extracted_ccs"
                if extracted.exists():
                    for path in sorted(extracted.rglob("*")):
                        if path.is_file():
                            target = stage / "UNSAFE_raw_decompressed_assets" / path.relative_to(extracted)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(path.read_bytes())
                else:
                    skipped_files.append(f"missing raw asset folder: {extracted}")
            else:
                skipped_files.append("raw/decompressed assets disabled")

            included_files = [path.relative_to(stage).as_posix() for path in sorted(stage.rglob("*")) if path.is_file()]
            if not included_files:
                raise RuntimeError("No files were staged for the research bundle.")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for path in sorted(stage.rglob("*")):
                    if path.is_file():
                        zf.write(path, path.relative_to(stage).as_posix())
            if not zip_path.exists() or zip_path.stat().st_size <= 0:
                raise RuntimeError("Zip creation completed without producing a non-empty bundle.")
            self.last_research_bundle_path = zip_path
            result = {
                "status": "success",
                "destination_folder": str(bundle_dir),
                "bundle_filename": zip_path.name,
                "bundle_path": str(zip_path),
                "included_files": included_files,
                "skipped_files": skipped_files,
                "errors": errors,
            }
            self._display_research_bundle_result(result)
            messagebox.showinfo("Research bundle", f"Exported research bundle:\n{zip_path}")
        except Exception as exc:
            errors.append(repr(exc))
            log_path = self._write_research_bundle_failure_log(workspace, zip_path, exc, included_files, skipped_files)
            errors.append(f"failure log: {log_path}")
            result = {
                "status": "failed",
                "destination_folder": str(bundle_dir),
                "bundle_filename": zip_path.name,
                "bundle_path": str(zip_path),
                "included_files": included_files,
                "skipped_files": skipped_files,
                "errors": errors,
            }
            self._display_research_bundle_result(result)
            messagebox.showerror("Research bundle export failed", f"{exc}\n\nFailure log:\n{log_path}")

    def open_research_bundle_folder(self) -> None:
        path = self._selected_workspace() / "bundles"
        path.mkdir(parents=True, exist_ok=True)
        self._open_path_with_platform(path)

    def copy_research_bundle_path(self) -> None:
        path = self.last_research_bundle_path
        if path is None or not path.exists():
            bundle_dir = self._selected_workspace() / "bundles"
            candidates = sorted(bundle_dir.glob("fragmenter_research_bundle_*.zip"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
            path = candidates[0] if candidates else None
        if path is None:
            messagebox.showwarning("Research bundle", "No generated research bundle was found. Use Export Research Bundle first.")
            return
        self.last_research_bundle_path = path
        self._copy_path_to_clipboard(path)

    def _legacy_open_research_bundle_folder(self) -> None:
        path = WORKSPACE / "bundles"
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))
        except Exception:
            messagebox.showinfo("Bundle folder", str(path))

    def build_upload_package(self):
        workspace = Path(self.workspace_output_dir.get().strip() or (WORKSPACE / "upload_package")).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)
        manifest = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "metadata_only": True,
            "area_server_root": self.project_root.get().strip(),
            "data_dir": self.data_dir.get().strip(),
            "save_dir": self.save_dir.get().strip(),
            "iso_path": self.iso_path.get().strip(),
            "data_bin_path": self.data_bin_path.get().strip(),
            "included": {},
            "notes": [
                "This package contains metadata only.",
                "No ISO, DATA.bin, .bin, .cmp, CCS/CCSF binaries, saves, or large binary assets are included.",
                "No patch, install, reskin, player-economy, or memory-hacking payloads are included.",
                "Final ZIP contents are filtered by tools/fragmenter_research_pack.py should_package().",
            ],
        }
        if self.export_include_index.get():
            if self.index is None and Path(self.index_path.get()).exists():
                try:
                    self.index = json.loads(Path(self.index_path.get()).read_text(encoding="utf-8"))
                except Exception:
                    self.index = None
            manifest["included"]["area_server_index"] = bool(self.index)
            if self.index:
                (workspace / "area_server_index.metadata.json").write_text(json.dumps(self.index, indent=2), encoding="utf-8", newline="\n")
        if self.export_include_correlations.get():
            report = self._write_correlation_report(workspace / "correlation_report.metadata.txt")
            manifest["included"]["correlation_report"] = str(report.name)
        if self.export_include_iso_index.get():
            iso_index = Path(self.iso_index_path.get().strip())
            if iso_index.exists():
                (workspace / "iso_index.metadata.json").write_text(iso_index.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
                manifest["included"]["iso_index"] = "iso_index.metadata.json"
            else:
                manifest["included"]["iso_index"] = False
        if self.export_include_binary_previews.get():
            preview = self._latest_binary_preview_json_path()
            if preview and preview.exists():
                (workspace / "binary_preview.metadata.json").write_text(preview.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
                manifest["included"]["binary_preview"] = "binary_preview.metadata.json"
            else:
                manifest["included"]["binary_preview"] = False
        manifest_path = workspace / "upload_package_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")

        package_cmd = [PY, str(ROOT / "fragmenter.py"), "package", "--out", str(workspace)]
        if not (ROOT / "fragmenter.py").exists():
            package_cmd = [PY, str(TOOLS / "fragmenter_research_pack.py"), "package", "--out", str(workspace)]

        zip_paths: list[str] = []

        def _on_line(line: str):
            match = re.search(r"Wrote\s+(.+fragmenter_upload_package_[^\s]+\.zip)", line.strip())
            if match:
                zip_paths.append(match.group(1))

        def _done(rc: int):
            if rc != 0:
                msg = f"Package export failed or was cancelled; metadata files remain in workspace:\n{workspace}\n"
                self._replace_text(self.export_package_status, "\n" + msg, append=True, readonly=True)
                messagebox.showerror("Upload package", msg)
                return
            zip_path = zip_paths[-1] if zip_paths else str(max((workspace / "export").glob("fragmenter_upload_package_*.zip"), key=lambda p: p.stat().st_mtime, default=workspace / "export" / "fragmenter_upload_package_<timestamp>.zip"))
            msg = f"Built metadata-only upload package ZIP:\n{zip_path}\n\nWorkspace metadata prepared under:\n{workspace}\n"
            self._replace_text(self.export_package_status, "\n" + msg, append=True, readonly=True)
            messagebox.showinfo("Upload package", msg)

        status = (
            "Preparing metadata under selected workspace and running safe package export:\n"
            f"Workspace: {workspace}\n"
            f"Manifest: {manifest_path}\n"
            f"Command: {' '.join(package_cmd)}\n"
        )
        if hasattr(self, "export_package_status"):
            self._replace_text(self.export_package_status, "\n" + status, append=True, readonly=True)
        self._run_task(package_cmd, on_done=_done, on_line=_on_line, label="safe package export")

    # ---------- Pickers ----------
    def pick_project(self):
        p = filedialog.askdirectory(title="Select Area Server folder")
        if not p:
            return
        self.project_root.set(p)
        self._update_title_status_strip()
        data = Path(p) / "data"
        if data.exists():
            self.data_dir.set(str(data))
        save = Path(p) / "save"
        if save.exists():
            self.save_dir.set(str(save))
        self.refresh_project_tree()

    def pick_data(self):
        p = filedialog.askdirectory(title="Select data folder")
        if p:
            self.data_dir.set(p)

    def pick_save(self):
        p = filedialog.askdirectory(title="Select save folder")
        if p:
            self.save_dir.set(p)

    def pick_data_bin(self):
        p = filedialog.askopenfilename(
            title="Select DATA.bin",
            filetypes=[("DATA.bin", "DATA.bin"), ("BIN files", "*.bin"), ("All files", "*.*")],
        )
        if p:
            self.data_bin_path.set(p)

    def pick_index_out(self):
        p = filedialog.asksaveasfilename(
            title="Index output JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if p:
            self.index_path.set(p)

    def pick_unpack_out(self):
        p = filedialog.askdirectory(title="Select unpack output folder")
        if p:
            self.unpack_out.set(p)




    # ---------- Index actions ----------
    def build_index(self):
        data = self.data_dir.get().strip()
        if not data:
            return messagebox.showerror("Missing", "Select a data folder first.")
        out = self.index_path.get().strip() or str(ROOT / "fragmenter_index.json")
        self.index_path.set(out)
        cmd = [PY, str(TOOLS / "fragmenter_index.py"), data, "--out", out]
        self._run_task(cmd, on_done=lambda rc: self.load_index() if rc == 0 else None)

    def load_index(self):
        p = Path(self.index_path.get())
        if not p.exists():
            return
        try:
            self.index = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return messagebox.showerror("Index error", str(e))
        self.refresh_tree()
        if hasattr(self, "result_category_table"):
            self.on_result_category_select()
        self.refresh_root_town_tab()

    def refresh_tree(self):
        if not hasattr(self, "tree"):
            return
        self.refresh_project_tree()

    def _tree_values(self, kind: str, size: int | None = None) -> tuple:
        return (kind, "", "", "" if size is None else size, "", "", "", "", "", "")

    def _insert_project_file(self, parent: str, entry: dict, kind: str = "FILE") -> str:
        iid = self.tree.insert(parent, "end", text=entry.get("name", "(file)"), values=self._tree_values(kind, entry.get("size")), tags=("binrow",))
        self.project_tree_payloads[iid] = {"kind": kind.lower(), "path": entry.get("path"), "entry": entry}
        return iid

    def _insert_area_server_containers(self, parent: str, area: dict) -> None:
        for entry in area.get("data_files", []):
            path = Path(entry.get("path", ""))
            if not path.is_file():
                continue
            node = self._insert_project_file(parent, entry, "DATA")
            try:
                members = read_members(path)
            except Exception:
                members = []
            if not members:
                continue
            self.tree.set(node, "gzip", "Y")
            for member in members:
                label = f"[{member.index}] {member.gzip_original_filename or 'gzip member'}"
                child = self.tree.insert(node, "end", text=label, values=("GZIP", "", "", member.decompressed_size, "", "", "", "", "", ""), tags=("secrow",))
                self.project_tree_payloads[child] = {"kind": "gzip_member", "name": member.gzip_original_filename or "gzip member", "path": str(path), "member": member.metadata()}
            if path.name.lower() == "town.bin":
                known = {
                    8: "[8] town04.cmp / CCSFtown04",
                    9: "[9] town04d.cmp / CCSFtown04d",
                    10: "[10] town05.cmp",
                }
                detected = {member.index for member in members}
                for index, label in known.items():
                    if index in detected:
                        child = self.tree.insert(node, "end", text=label, values=("KNOWN", "", "", "", "", "", "", "", "", ""), tags=("secrow",))
                        self.project_tree_payloads[child] = {"kind": "known_town_member", "name": label.split("] ", 1)[-1].split(" / ", 1)[0], "path": str(path), "member_index": index}

    def refresh_project_tree(self, quick_probe_iso: bool = False, compute_iso_sha1: bool = False):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        self.project_tree_payloads = {}

        project = self.tree.insert("", "end", text="Project", values=self._tree_values("ROOT"), tags=("binrow",))
        self.project_tree_payloads[project] = {"kind": "project"}
        self.tree.insert(project, "end", text=f"Workspace: {self.workspace_output_dir.get().strip() or WORKSPACE}", values=self._tree_values("INFO"), tags=("secrow",))

        iso_node = self.tree.insert("", "end", text="ISO", values=self._tree_values("ROOT"), tags=("binrow",))
        iso_path = self.iso_path.get().strip()
        if iso_path:
            iso = inspect_iso(iso_path, compute_sha1=compute_iso_sha1, quick_probe=quick_probe_iso)
            label = Path(iso_path).name if iso.get("exists") else f"{Path(iso_path).name} (missing)"
            child = self.tree.insert(iso_node, "end", text=label, values=self._tree_values("ISO", iso.get("size")), tags=("secrow",))
            self.project_tree_payloads[child] = {"kind": "iso", "iso": iso, "path": iso_path}
            for term, offset in (iso.get("quick_probe_hits") or {}).items():
                hit = self.tree.insert(child, "end", text=f"{term} @ 0x{offset:08X}", values=self._tree_values("HIT"), tags=("secrow",))
                self.project_tree_payloads[hit] = {"kind": "iso_hit", "name": term, "path": iso_path, "offset": offset, "source_file": Path(iso_path).name}

        area_node = self.tree.insert("", "end", text="Area Server", values=self._tree_values("ROOT"), tags=("binrow",))
        root = self.project_root.get().strip()
        if root:
            area = inspect_area_server_root(root)
            self.project_tree_payloads[area_node] = {"kind": "area_server", "area": area}
            if area.get("data_dir_exists"):
                self.data_dir.set(area.get("data_dir", ""))
            if area.get("area_server_exe"):
                self._insert_project_file(area_node, area["area_server_exe"], "EXE")
            for entry in area.get("root_files", []):
                self._insert_project_file(area_node, entry, "ROOT")
            key_node = self.tree.insert(area_node, "end", text="Key data files", values=self._tree_values("GROUP"), tags=("binrow",))
            for entry in area.get("key_data_files", []):
                self._insert_project_file(key_node, entry, "KEY")
            data_node = self.tree.insert(area_node, "end", text="data/*.bin and data/*.dat", values=self._tree_values("GROUP"), tags=("binrow",))
            self._insert_area_server_containers(data_node, area)

        extracted_node = self.tree.insert("", "end", text="Extracted CCS/CMP", values=self._tree_values("ROOT"), tags=("binrow",))
        for entry in list_extracted_assets(self.workspace_output_dir.get().strip() or WORKSPACE):
            self._insert_project_file(extracted_node, entry, self._asset_type_from_path(entry.get("name", "")))

        reports_node = self.tree.insert("", "end", text="Reports", values=self._tree_values("ROOT"), tags=("binrow",))
        expected_names = set()
        for row in self._expected_report_rows():
            expected_names.add(str(row["name"]))
            label = str(row["name"]) if row["status"] == "Ready" else f"{row['name']} (Missing)"
            iid = self.tree.insert(reports_node, "end", text=label, values=self._tree_values(str(row["status"]).upper(), row.get("size")), tags=("secrow",))
            self.project_tree_payloads[iid] = {"kind": "expected_report", **row}
        for entry in list_reports(self.workspace_output_dir.get().strip() or WORKSPACE):
            if entry.get("name") in expected_names:
                continue
            self._insert_project_file(reports_node, entry, "REPORT")

        plans_node = self.tree.insert("", "end", text="Patch Plans", values=self._tree_values("ROOT"), tags=("binrow",))
        plans_dir = Path(self.workspace_output_dir.get().strip() or WORKSPACE).expanduser() / "patch_plans"
        if plans_dir.is_dir():
            for path in sorted(plans_dir.glob("*.json"), key=lambda p: p.name.lower()):
                self._insert_project_file(plans_node, {"name": path.name, "path": str(path), "size": path.stat().st_size}, "PLAN")

        for item in self.tree.get_children("")[:6]:
            self.tree.item(item, open=True)
        self.refresh_expected_reports_panel()

    def refresh_index_tree_legacy(self):
        """Legacy scan-index hierarchy retained for older workflows."""
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        if not self.index:
            return

        inserted_rows = 0
        truncated = False
        for f in self.index.get("files", []):
            if inserted_rows >= MAX_RESULT_HIERARCHY_ROWS:
                truncated = True
                break
            if "error" in f:
                self.tree.insert("", "end", text=f.get("name", "(error)"),
                                 values=("ERR", "", "", "", "", "", "", "", "", ""),
                                 tags=("binrow",))
                inserted_rows += 1
                continue

            node = self.tree.insert(
                "",
                "end",
                text=f["name"],
                values=(
                    "BIN",
                    "Y" if f.get("gzip") else "N",
                    f.get("section_count", 0),
                    f.get("decompressed_size", 0),
                    "", "", "", "", "", "",
                ),
                tags=("binrow",),
            )
            inserted_rows += 1

            for s in f.get("sections", []):
                if inserted_rows >= MAX_RESULT_HIERARCHY_ROWS:
                    truncated = True
                    break
                c = s.get("counts", {})
                self.tree.insert(
                    node,
                    "end",
                    text=s.get("id", "(section)"),
                    values=(
                        "SEC",
                        "",
                        "",
                        s.get("size", 0),
                        s.get("asset_paths_count", 0),
                        c.get("TEX_", 0),
                        c.get("MDL_", 0),
                        c.get("DMY_", 0),
                        c.get("MAT_", 0),
                        c.get("ANM_", 0),
                    ),
                    tags=("secrow",),
                )
                inserted_rows += 1

        if truncated:
            self.tree.insert(
                "",
                "end",
                text=f"Hierarchy preview capped at {MAX_RESULT_HIERARCHY_ROWS} rows; use the category browser for complete results.",
                values=("INFO", "", "", "", "", "", "", ""),
                tags=("binrow",),
            )

        for item in self.tree.get_children("")[:3]:
            self.tree.item(item, open=True)

    def resolve_selected(self):
        if not hasattr(self, "tree"):
            return None
        sel = self.tree.selection()
        if not sel:
            return None
        item = sel[0]
        payload = getattr(self, "project_tree_payloads", {}).get(item)
        if payload:
            return ("project_item", payload, None)
        if not self.index:
            return None
        vals = self.tree.item(item, "values")
        name = self.tree.item(item, "text")
        if not vals:
            return None

        if vals[0] == "BIN":
            for f in self.index.get("files", []):
                if f.get("name") == name:
                    return ("bin", f, None)

        if vals[0] == "SEC":
            parent = self.tree.parent(item)
            bin_name = self.tree.item(parent, "text")
            for f in self.index.get("files", []):
                if f.get("name") != bin_name:
                    continue
                for s in f.get("sections", []):
                    if s.get("id") == name:
                        return ("sec", f, s)

        return None

    def _set_widget_enabled(self, widget, enabled: bool):
        if not widget:
            return
        if enabled:
            widget.state(["!disabled"])
        else:
            widget.state(["disabled"])

    def _schedule_on_select(self, _evt=None):
        self.after_idle(self.on_select)

    def _selected_tree_payload(self) -> dict:
        res = self.resolve_selected()
        if not res:
            return {}
        kind, file_obj, section_obj = res
        if kind == "project_item":
            return dict(file_obj or {})
        payload = dict(section_obj or file_obj or {})
        payload.setdefault("kind", kind)
        if isinstance(file_obj, dict):
            payload.setdefault("source_file", file_obj.get("name") or file_obj.get("path") or file_obj.get("file"))
            payload.setdefault("file", file_obj.get("path") or file_obj.get("file"))
        return payload

    def _identifier_for_explanation(self, payload: dict) -> str:
        candidates = []
        for key in ("name", "id", "path", "file", "source_file"):
            value = payload.get(key)
            if value:
                candidates.append(Path(str(value)).name)
                candidates.append(str(value))
        candidates.extend(self._nearby_identifiers_for_payload(payload))
        for candidate in candidates:
            text = str(candidate).strip()
            if not text:
                continue
            leaf = Path(text).name
            if leaf:
                return leaf
            return text
        return str(payload.get("kind") or "selection")

    def _selection_path(self, payload: dict) -> Path | None:
        path = self._payload_file_path(payload)
        if path is not None:
            return path
        entry = payload.get("entry")
        if isinstance(entry, dict):
            return self._payload_file_path(entry)
        return None

    def _selection_inspector_fields(self, payload: dict) -> tuple[str, dict[str, str], dict[str, bool | str]]:
        name = self._identifier_for_explanation(payload)
        info = explain_identifier(name)
        path = self._selection_path(payload)
        member = payload.get("member") if isinstance(payload.get("member"), dict) else {}
        offset = payload.get("offset") or payload.get("raw_start") or member.get("raw_start") or payload.get("member_index")
        if offset is not None and isinstance(offset, int):
            offset_text = f"0x{offset:X}"
        else:
            offset_text = "" if offset is None else str(offset)
        warnings = list(info.get("warnings") or [])
        notes = list(info.get("notes") or [])
        fields = {
            "Name": name,
            "Type": str(info.get("category") or payload.get("kind") or payload.get("type") or "unknown"),
            "Source": str(payload.get("source_file") or payload.get("path") or payload.get("file") or payload.get("kind") or ""),
            "Offset/member/file": offset_text or (path.name if path else ""),
            "SHA1 when available": str(payload.get("sha1") or ((payload.get("entry") or {}).get("sha1") if isinstance(payload.get("entry"), dict) else "")),
            "Confidence": str(info.get("confidence") or payload.get("confidence") or ""),
            "Explanation": str(info.get("summary") or ""),
            "Modding notes": "\n".join(f"• {note}" for note in notes) or "• Inspect/export only until the actual owning container is known.",
            "Safe actions": "",
            "Warnings": "\n".join(f"• {warning}" for warning in warnings) or "• No specific warning registered; preserve backups and work from exported copies.",
        }
        suffix = path.suffix.lower() if path else ""
        has_member = payload.get("kind") in {"gzip_member", "known_town_member"} or bool(member)
        actions: dict[str, bool | str] = {
            "Preview Texture": path is not None and suffix in TEXTURE_PREVIEW_EXTENSIONS,
            "Preview 3D": path is not None and suffix == ".obj",
            "Open Text/Hex": path is not None,
            "Export Raw": path is not None,
            "Extract Member": has_member or (path is not None and suffix in {".bin", ".dat", ".cmp"}),
            "Run Catalog": True,
            "Add to Patch Plan": path is not None or bool(name),
            "Open Containing Folder": path is not None,
        }
        labels = []
        for action, state in actions.items():
            labels.append(f"• {action}: {'available' if state is True else state if isinstance(state, str) else 'disabled: not applicable for this selection'}")
        fields["Safe actions"] = "\n".join(labels)
        return name, fields, actions

    def _update_selection_inspector(self, payload: dict | None) -> None:
        if not hasattr(self, "selection_inspector"):
            return
        if not payload:
            self._replace_text(self.selection_inspector, "Select an asset tree item, identifier, report hit, or member node.\n", readonly=True)
            self._configure_safe_action_buttons({})
            return
        _name, fields, actions = self._selection_inspector_fields(payload)
        lines = []
        for key, value in fields.items():
            lines.append(f"{key}\n{'-' * len(key)}\n{value or '(none)'}\n")
        self._replace_text(self.selection_inspector, "\n".join(lines), readonly=True)
        self._configure_safe_action_buttons(actions)

    def _configure_safe_action_buttons(self, actions: dict[str, bool | str]) -> None:
        disabled = []
        for action, btn in getattr(self, "inspector_action_buttons", {}).items():
            state = actions.get(action, False)
            self._set_widget_enabled(btn, state is True)
            if state is not True:
                disabled.append(f"{action}: {state if isinstance(state, str) else 'not applicable'}")
        if hasattr(self, "inspector_action_hint"):
            self.inspector_action_hint.set("Disabled actions: " + "; ".join(disabled[:4]) if disabled else "All displayed safe actions are available.")

    def _run_safe_action(self, action: str) -> None:
        payload = self._selected_tree_payload()
        path = self._selection_path(payload)
        if action == "Run Catalog":
            return self.catalog_extracted_assets()
        if action == "Open Containing Folder" and path:
            return self._open_folder_path(path.parent)
        if action == "Open Text/Hex" and path:
            self.set_text_hex_source(path, select=True)
            return
        if action == "Preview Texture" and path:
            return self._show_image_preview(path)
        if action == "Preview 3D" and path:
            return self._load_obj_3d_preview(path)
        if action == "Export Raw" and path:
            target = filedialog.asksaveasfilename(title="Export raw selection as", initialfile=path.name, initialdir=str(WORKSPACE))
            if target:
                Path(target).write_bytes(path.read_bytes())
            return
        if action == "Extract Member":
            if path:
                self.inspector_path.set(str(path))
                return self.extract_inspector_candidate()
        if action == "Add to Patch Plan":
            return self._add_selection_to_patch_plan(payload, path)
        messagebox.showinfo(action, "This action is disabled or not implemented for the current selection.")

    def _add_selection_to_patch_plan(self, payload: dict | None, path: Path | None) -> None:
        """Record a note-only patch-plan action; never modify original sources."""
        payload = payload or {}
        member = payload.get("member_index") or payload.get("member")
        if isinstance(member, dict):
            member = member.get("index") or member.get("name")
        offset = payload.get("offset") or payload.get("raw_start")
        file_text = str(path) if path else str(payload.get("file") or payload.get("source_file") or payload.get("name") or "")
        state = FragmenterProjectState(
            iso_path=self.iso_path.get().strip() or None,
            area_server_root=self.project_root.get().strip() or None,
            workspace_dir=self.workspace_output_dir.get().strip() or str(WORKSPACE),
        )
        description = (
            "Note-only safe action for read-only analysis/export. "
            "Unknown or destructive patching remains disabled; originals are not modified."
        )
        try:
            plan_path, action_record = add_safe_note_to_current_patch_plan(
                state, source=str(payload.get("kind") or "gui"), file=file_text or None, member=member, offset=offset, description=description
            )
        except Exception as exc:
            return messagebox.showerror("Patch Plan", f"Could not update patch plan: {exc}")
        self._console_write(f"[patch-plan] Added {action_record['action_id']} to {plan_path} (note-only; no originals modified).\n")
        self.refresh_project_tree()
        messagebox.showinfo("Patch Plan", f"Added note-only action {action_record['action_id']} to:\n{plan_path}")

    def _update_explore_action_state(self, selection_kind, file_obj, section_obj):
        _ = file_obj
        has_section_paths = bool((section_obj or {}).get("asset_paths") or (section_obj or {}).get("asset_paths_sample"))
        has_section_dmy = bool((section_obj or {}).get("tops", {}).get("DMY_", []))
        has_resource_map = bool(self.current_resource_map)

        bin_actions = [getattr(self, "btn_unpack_bin", None)]
        section_actions = [
            getattr(self, "btn_inspect_section", None),
            getattr(self, "btn_map_section", None),
            getattr(self, "btn_extract_likely_model_files", None),
            getattr(self, "btn_open_related_external", None),
            getattr(self, "btn_open_related_folder", None),
            getattr(self, "btn_preview_related_asset", None),
        ]

        for btn in bin_actions:
            self._set_widget_enabled(btn, selection_kind == "bin")

        for btn in section_actions:
            self._set_widget_enabled(btn, selection_kind == "sec")

        self._set_widget_enabled(getattr(self, "btn_export_asset_paths", None), selection_kind == "sec" and has_section_paths)
        self._set_widget_enabled(getattr(self, "btn_export_dmy_markers", None), selection_kind == "sec" and has_section_dmy)
        self._set_widget_enabled(getattr(self, "resource_show_more_btn", None), selection_kind == "sec" and has_resource_map)

        if selection_kind == "bin":
            if hasattr(self, "explore_action_hint"):
                self.explore_action_hint.set("BIN selected: select a child SECTION first.")
        elif selection_kind == "sec":
            if hasattr(self, "explore_action_hint"):
                self.explore_action_hint.set("SECTION selected: inspect/map resources, browse related assets, or export available data.")
        else:
            if hasattr(self, "explore_action_hint"):
                self.explore_action_hint.set("No selection: choose a BIN or SECTION to enable actions.")

    def on_select(self, _evt=None):
        res = self.resolve_selected()
        if not res:
            self._replace_text(self.detail, "Select a BIN or SECTION to see details.\n", readonly=True)
            self._update_selection_inspector(None)
            if hasattr(self, "resource_browser_status"):
                self._set_resource_browser_status(self._resource_status_for_selection(None, None, None))
            self._update_explore_action_state(None, None, None)
            self.update_workflow_status()
            return
        kind, f, s = res
        if kind == "project_item":
            self._handle_project_tree_selection(f)
            self._update_selection_inspector(f)
            self._update_explore_action_state(None, None, None)
            self.update_workflow_status()
            return
        if kind == "bin":
            if hasattr(self, "resource_browser_status"):
                self._set_resource_browser_status(self._resource_status_for_selection(kind, f, s))
            payload = json.dumps({k: v for k, v in f.items() if k != "sections"}, indent=2)
        else:
            if hasattr(self, "resource_browser_status"):
                self._set_resource_browser_status(self._resource_status_for_selection(kind, f, s))
            payload = json.dumps(s, indent=2)
        self._replace_text(self.detail, self._truncate_blob(payload), readonly=True)
        self._update_selection_inspector(s if kind == "sec" else f)
        self._update_text_hex_tab_for_selection(kind, f, s)
        self._update_texture_tab_for_selection(kind, f, s)
        self._update_3d_tab_for_selection(kind, f, s)
        self._update_explore_action_state(kind, f, s)
        self.update_workflow_status()


    def _nearby_identifiers_for_payload(self, payload: dict | None) -> list[str]:
        if not isinstance(payload, dict):
            return []
        keys = ("name", "path", "asset_paths", "asset_paths_sample", "texture_paths", "model_paths", "symbols", "unknown_strings")
        out: list[str] = []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, list):
                out.extend(str(x) for x in value[:20])
            elif isinstance(value, dict):
                for sub in value.values():
                    if isinstance(sub, list):
                        out.extend(str(x) for x in sub[:10])
        dedup: list[str] = []
        for item in out:
            if item and item not in dedup:
                dedup.append(item)
        return dedup

    def _payload_file_path(self, payload: dict | None) -> Path | None:
        if not isinstance(payload, dict):
            return None
        for key in ("path", "file", "source_file"):
            value = payload.get(key)
            if value:
                candidate = Path(str(value)).expanduser()
                if candidate.is_file():
                    return candidate
        return None

    def _formatted_json_with_raw_fallback(self, path: Path) -> str:
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            formatted = json.dumps(json.loads(raw), indent=2, sort_keys=True, ensure_ascii=False)
        except Exception as exc:
            return f"Formatted JSON unavailable: {exc}\n\nRaw fallback\n============\n{raw}"
        return f"Formatted JSON\n==============\n{formatted}\n\nRaw fallback\n============\n{raw}"

    def _update_text_hex_tab_for_selection(self, kind, file_obj, section_obj) -> None:
        path = self._payload_file_path(section_obj if kind == "sec" else file_obj) or self._payload_file_path(file_obj)
        if path is None:
            return
        offset = 0
        length = None
        if kind == "sec" and isinstance(section_obj, dict):
            offset = self._parse_text_hex_int(str(section_obj.get("offset", 0)), 0)
            size_value = section_obj.get("size") or section_obj.get("length")
            if size_value is not None:
                length = min(self._parse_text_hex_int(str(size_value), 4096), 64 * 1024)
        try:
            self.set_text_hex_source(path, offset=offset, length=length, select=False)
        except Exception as exc:
            self._replace_text(self.preview_tabs["Text / Hex"], f"Text / Hex preview unavailable: {exc}\n", readonly=True)

    def _update_texture_tab_for_selection(self, kind, file_obj, section_obj) -> None:
        payload = section_obj if kind == "sec" else file_obj
        identifiers = self._nearby_identifiers_for_payload(payload)
        path = None
        if isinstance(payload, dict):
            path_text = payload.get("path") or payload.get("file")
            if path_text:
                candidate = Path(str(path_text)).expanduser()
                if candidate.is_file():
                    path = candidate
        if path is not None:
            try:
                meta = extract_texture_metadata(path)
                unsupported = path.suffix.lower() not in TEXTURE_PREVIEW_EXTENSIONS or meta.get("dimensions") is None
                self._replace_text(self.preview_tabs["Texture"], texture_metadata_text(meta, identifiers, unsupported=unsupported), readonly=True)
                return
            except Exception as exc:
                self._replace_text(self.preview_tabs["Texture"], f"Texture metadata unavailable: {exc}\n", readonly=True)
                return
        if identifiers:
            text = (
                "No built-in decoder for this texture yet.\n\n"
                "This selection appears to contain texture identifiers or references, but no decoded texture file is selected.\n\n"
                "CCS note: .bmp strings inside CCS may be references, not embedded bitmap pixels.\n"
                "CCS note: Selecting TEX_sr4sun1 or sr4sun1.bmp may not preview pixels until the actual texture block is decoded/exported.\n\n"
                "Nearby identifiers:\n" + "\n".join(f"  - {x}" for x in identifiers[:25]) + "\n"
            )
            self._replace_text(self.preview_tabs["Texture"], text, readonly=True)

    def _update_3d_tab_for_selection(self, kind, file_obj, section_obj) -> None:
        payload = section_obj if kind == "sec" else file_obj
        identifiers = self._nearby_identifiers_for_payload(payload)
        path = None
        if isinstance(payload, dict):
            path_text = payload.get("path") or payload.get("file")
            if path_text:
                candidate = Path(str(path_text)).expanduser()
                if candidate.is_file():
                    path = candidate
        if path is not None and path.suffix.lower() == ".obj":
            self._load_obj_3d_preview(path, select=False)
            return
        model_identifiers = [x for x in identifiers if Path(str(x)).suffix.lower() == ".obj" or str(x).startswith(("MDL_", "OBJ_"))]
        if model_identifiers:
            self._show_3d_message(
                "No decoded mesh yet. Export OBJ or implement CCS model decode for this block.\n\n"
                "Nearby model identifiers:\n" + "\n".join(f"  - {x}" for x in model_identifiers[:25]) + "\n"
            )

    def _format_bytes(self, size: int) -> str:
        units = ["B", "KiB", "MiB", "GiB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
            value /= 1024
        return f"{size} B"

    def _open_path_with_platform(self, path: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Open failed", f"Could not open:\n{path}\n\n{exc}")

    def _copy_text_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.resource_preview_message.set(f"Copied path: {text}" if text else "Copied empty path.")

    def _copy_path_to_clipboard(self, path: Path) -> None:
        self._copy_text_to_clipboard(str(path))

    def _open_existing_variable_path(self, variable: tk.StringVar) -> None:
        text = variable.get().strip()
        if not text:
            return messagebox.showinfo("Open path", "No path is selected.")
        path = Path(text).expanduser()
        if not path.exists():
            return messagebox.showinfo("Open path", f"Path not found:\n{path}")
        self._open_path_with_platform(path)

    def _summarize_large_report(self, path: Path, stat_result: os.stat_result) -> str:
        line_count = 0
        headers: list[str] = []
        identifier_counts: dict[str, int] = {}
        identifier_re = re.compile(r"\b(?:[A-Z]{2,}_[A-Za-z0-9_./-]+|[A-Za-z0-9_.-]+\.(?:ccs|bmp|png|obj|bin|iso|json|txt))\b")
        header_re = re.compile(r"^\s*(?:#{1,6}\s+|={3,}\s*$|-{3,}\s*$|\[[^\]]+\]\s*$|[A-Z][A-Za-z0-9 _./:-]{2,80}:\s*$)")
        scanned = 0
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(64 * 1024), b""):
                line_count += chunk.count(b"\n")
                if scanned < REPORT_SUMMARY_SCAN_BYTES:
                    take = chunk[: REPORT_SUMMARY_SCAN_BYTES - scanned]
                    scanned += len(take)
                    text = take.decode("utf-8", errors="replace")
                    for line in text.splitlines():
                        stripped = line.strip()
                        if stripped and len(headers) < 12 and header_re.match(stripped):
                            headers.append(stripped[:140])
                        if len(identifier_counts) < 5000:
                            for match in identifier_re.findall(line):
                                identifier_counts[match] = identifier_counts.get(match, 0) + 1
                elif scanned >= REPORT_SUMMARY_SCAN_BYTES:
                    continue
        if stat_result.st_size and line_count == 0:
            line_count = 1
        modified = datetime.fromtimestamp(stat_result.st_mtime).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        top_ids = sorted(identifier_counts.items(), key=lambda item: (-item[1], item[0]))[:12]
        lines = [
            "Large report summary",
            "====================",
            f"Path: {path}",
            f"Size: {self._format_bytes(stat_result.st_size)} ({stat_result.st_size:,} bytes)",
            f"Approximate line count: {line_count:,}",
            f"Modified: {modified}",
            f"Summary scan: first {self._format_bytes(min(scanned, stat_result.st_size))}",
            "",
            "First useful section headers:",
        ]
        lines.extend(f"- {header}" for header in headers) if headers else lines.append("- None found in the summary scan.")
        lines.extend(["", "Top identifier hits from summary scan:"])
        lines.extend(f"- {identifier}: {count}" for identifier, count in top_ids) if top_ids else lines.append("- None found cheaply.")
        lines.extend(["", "Use the actions below to load the complete report only when needed."])
        return "\n".join(lines) + "\n"


    def _read_report_prefix(self, path: Path, limit: int = REPORT_INITIAL_PREVIEW_BYTES) -> tuple[str, bool, int]:
        with path.open("rb") as fh:
            data = fh.read(limit + 1)
        truncated = len(data) > limit
        if truncated:
            data = data[:limit]
        return data.decode("utf-8", errors="replace"), truncated, len(data)

    def _report_metadata_text(self, path: Path, stat_result: os.stat_result, source_dir: Path | None = None) -> str:
        modified = datetime.fromtimestamp(stat_result.st_mtime).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        return "\n".join([
            "Report preview",
            "==============",
            f"Path: {path}",
            f"Size: {self._format_bytes(stat_result.st_size)} ({stat_result.st_size:,} bytes)",
            f"Modified: {modified}",
            f"Source directory: {source_dir or path.parent}",
            f"Initial preview cap: {self._format_bytes(REPORT_INITIAL_PREVIEW_BYTES)}",
            "",
        ])

    def _show_bounded_report_preview(self, path: Path, widget: tk.Text, source_dir: Path | None = None) -> None:
        try:
            stat_result = path.stat()
            prefix, truncated, loaded = self._read_report_prefix(path)
        except Exception as exc:
            self._replace_text(widget, f"Could not open report: {exc}\n", readonly=True)
            self.nb.select(widget.master)
            return
        self._replace_text(widget, self._report_metadata_text(path, stat_result, source_dir), readonly=False)
        if path.suffix.lower() == ".json":
            widget.insert("end", "JSON prefix (not fully formatted to keep the UI responsive)\n")
            widget.insert("end", "======================================================\n")
        else:
            widget.insert("end", "Initial content preview\n=======================\n")
        widget.insert("end", prefix)
        if truncated:
            widget.insert("end", f"\n\n... [preview stopped after {self._format_bytes(loaded)} of {self._format_bytes(stat_result.st_size)}]\n")
            actions = ttk.Frame(widget)
            ttk.Button(actions, text="Load more", command=lambda p=path, w=widget, offset=loaded: self._append_report_chunk(p, w, offset)).pack(side="left", padx=(0, 8))
            ttk.Button(actions, text="Open Full Report", command=lambda p=path: self._load_full_report_async(p)).pack(side="left", padx=(0, 8))
            if path.suffix.lower() == ".json":
                ttk.Button(actions, text="Format full JSON", command=lambda p=path: self._format_full_json_async(p)).pack(side="left", padx=(0, 8))
            ttk.Button(actions, text="Copy Path", command=lambda p=path: self._copy_path_to_clipboard(p)).pack(side="left")
            widget.window_create("end", window=actions)
            widget.insert("end", "\n")
        elif path.suffix.lower() == ".json":
            actions = ttk.Frame(widget)
            ttk.Button(actions, text="Format JSON", command=lambda p=path: self._format_full_json_async(p)).pack(side="left", padx=(0, 8))
            ttk.Button(actions, text="Copy Path", command=lambda p=path: self._copy_path_to_clipboard(p)).pack(side="left")
            widget.insert("end", "\n")
            widget.window_create("end", window=actions)
            widget.insert("end", "\n")
        try:
            widget.configure(state="disabled")
        except tk.TclError:
            pass
        self.nb.select(widget.master)
        self.resource_preview_message.set(f"Report preview loaded: {path.name}")

    def _append_report_chunk(self, path: Path, widget: tk.Text, offset: int) -> None:
        try:
            stat_result = path.stat()
            with path.open("rb") as fh:
                fh.seek(offset)
                data = fh.read(REPORT_INITIAL_PREVIEW_BYTES + 1)
        except Exception as exc:
            self._replace_text(widget, f"\nCould not load more: {exc}\n", append=True, readonly=True)
            return
        truncated = len(data) > REPORT_INITIAL_PREVIEW_BYTES
        chunk = data[:REPORT_INITIAL_PREVIEW_BYTES].decode("utf-8", errors="replace")
        try:
            widget.configure(state="normal")
        except tk.TclError:
            pass
        widget.insert("end", f"\n--- next chunk at byte {offset:,} ---\n")
        widget.insert("end", chunk)
        next_offset = offset + min(len(data), REPORT_INITIAL_PREVIEW_BYTES)
        if truncated and next_offset < stat_result.st_size:
            actions = ttk.Frame(widget)
            ttk.Button(actions, text="Load more", command=lambda p=path, w=widget, o=next_offset: self._append_report_chunk(p, w, o)).pack(side="left", padx=(0, 8))
            ttk.Button(actions, text="Open Full Report", command=lambda p=path: self._load_full_report_async(p)).pack(side="left")
            widget.insert("end", "\n")
            widget.window_create("end", window=actions)
            widget.insert("end", "\n")
        try:
            widget.configure(state="disabled")
        except tk.TclError:
            pass
        widget.see("end")

    def _format_full_json_async(self, path: Path) -> None:
        widget = self.preview_tabs["Text / Hex"]
        token = object()
        self._json_format_token = token
        self._replace_text(widget, f"Formatting JSON in background: {path}\n", readonly=False)
        self.nb.select(widget.master)
        q: "queue.Queue[str]" = queue.Queue()

        def worker() -> None:
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                q.put("Formatted JSON\n==============\n" + json.dumps(json.loads(raw), indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            except Exception as exc:
                q.put(f"Formatted JSON unavailable: {exc}\n")

        def finish() -> None:
            if getattr(self, "_json_format_token", None) is not token:
                return
            try:
                text = q.get_nowait()
            except queue.Empty:
                self.after(100, finish)
                return
            self._replace_text(widget, text, readonly=True)
            self.resource_preview_message.set(f"JSON formatting complete: {path.name}")

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, finish)

    def _show_large_report_summary(self, path: Path, stat_result: os.stat_result) -> None:
        widget = self.preview_tabs["Report"]
        self._replace_text(widget, self._summarize_large_report(path, stat_result), readonly=False)
        actions = ttk.Frame(widget)
        ttk.Button(actions, text="Open Full Report", command=lambda p=path: self._load_full_report_async(p)).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Copy Path", command=lambda p=path: self._copy_path_to_clipboard(p)).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Open Containing Folder", command=lambda p=path: self._open_path_with_platform(p.parent)).pack(side="left")
        widget.window_create("end", window=actions)
        widget.insert("end", "\n")
        try:
            widget.configure(state="disabled")
        except tk.TclError:
            pass
        self.nb.select(widget.master)
        self.resource_preview_message.set(f"Large report summarized: {path.name}")

    def _load_full_report_async(self, path: Path) -> None:
        widget = self.preview_tabs["Report"]
        token = object()
        self._report_load_token = token
        try:
            widget.configure(state="normal")
        except tk.TclError:
            pass
        widget.delete("1.0", "end")
        widget.insert("end", f"Loading full report in chunks: {path}\n\n")
        self.nb.select(widget.master)
        self.resource_preview_message.set(f"Loading full report: {path.name}")
        try:
            fh = path.open("r", encoding="utf-8", errors="replace")
        except Exception as exc:
            self._replace_text(widget, f"Could not open report: {exc}\n", readonly=True)
            return

        def append_next() -> None:
            if getattr(self, "_report_load_token", None) is not token:
                fh.close()
                return
            try:
                chunk = fh.read(REPORT_FULL_LOAD_CHUNK_BYTES)
            except Exception as exc:
                fh.close()
                self._replace_text(widget, f"\nRead failed: {exc}\n", append=True, readonly=True)
                return
            if not chunk:
                fh.close()
                try:
                    widget.configure(state="disabled")
                except tk.TclError:
                    pass
                self.resource_preview_message.set(f"Full report loaded: {path.name}")
                return
            widget.insert("end", chunk)
            widget.see("end")
            self.after(REPORT_FULL_LOAD_APPEND_DELAY_MS, append_next)

        self.after(0, append_next)

    def _handle_project_tree_selection(self, payload: dict) -> None:
        kind = payload.get("kind")
        path_text = payload.get("path")
        path = Path(path_text).expanduser() if path_text else None
        if kind == "expected_report":
            missing = payload.get("missing_inputs") or []
            lines = [
                f"Expected report: {payload.get('name')}",
                f"Status: {payload.get('status')}",
                f"Path: {path}",
                f"Generating launcher: {payload.get('tool')}",
                f"Required inputs: {payload.get('required_inputs')}",
            ]
            if path and path.is_file():
                lines.append("Report exists. Use the Open button in Expected Reports or select a real report row to view it.")
            else:
                lines.append("\nMissing: this expected report has not been generated yet.")
                lines.append("Absent required inputs:" if missing else "All launcher inputs appear present.")
                lines.extend(f"- {item}" for item in missing)
            self._replace_text(self.selection_inspector, "\n".join(lines) + "\n", readonly=True)
            self.resource_preview_message.set(f"Expected report: {payload.get('name')} ({payload.get('status')})")
            return
        if kind == "report" and path and path.suffix.lower() in {".txt", ".json"} and path.is_file():
            stat_result = path.stat()
            widget = self.preview_tabs["Text / Hex"] if path.suffix.lower() == ".json" else self.preview_tabs["Report"]
            if stat_result.st_size > LARGE_REPORT_THRESHOLD_BYTES:
                text = self._report_metadata_text(path, stat_result, source_dir=path.parent)
                text += "Large report selected. Use the Expected Reports Open button or select a smaller file to preview content.\n"
                self._replace_text(widget, text, readonly=True)
                self.nb.select(widget.master)
                self.resource_preview_message.set(f"Large report metadata only: {path.name}")
            else:
                self._show_bounded_report_preview(path, widget, source_dir=path.parent)
            return
        if path and path.is_file() and path.stat().st_size <= 1024 * 1024 and path.suffix.lower() in {".json", ".txt", ".ini"}:
            self._replace_text(self.preview_tabs["Text / Hex"], path.read_text(encoding="utf-8", errors="replace"), readonly=True)
            self.nb.select(self.preview_tabs["Text / Hex"].master)
        if path and path.is_file():
            if path.suffix.lower() == ".obj":
                self._load_obj_3d_preview(path)
                self.resource_preview_message.set(f"OBJ preview opened: {path.name}")
                return
            try:
                meta = extract_texture_metadata(path)
                unsupported = path.suffix.lower() not in TEXTURE_PREVIEW_EXTENSIONS or meta.get("dimensions") is None
                self._replace_text(self.preview_tabs["Texture"], texture_metadata_text(meta, self._nearby_identifiers_for_payload(payload), unsupported=unsupported), readonly=True)
                if path.suffix.lower() in TEXTURE_PREVIEW_EXTENSIONS:
                    self.nb.select(self.preview_tabs["Texture"].master)
            except Exception:
                pass
        self._replace_text(self.detail, self._truncate_blob(json.dumps(payload, indent=2, default=str)), readonly=True)
        self.resource_preview_message.set(f"Selected {kind or 'item'}: {Path(path_text).name if path_text else 'metadata'}")

    def _truncate_blob(self, text: str, limit: int = 12000) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n\n... [truncated {len(text) - limit} chars]"

    # ---------- Explore actions ----------
    def inspect_selected(self):
        res = self.resolve_selected()
        if not res or res[0] != "sec":
            return messagebox.showerror("Select section", "Select a SECTION first.")
        _, f, s = res
        cmd = [PY, str(TOOLS / "fragment_inspect.py"), f["file"], "--section", s["id"]]
        self._run_task(cmd)

    def unpack_selected(self):
        res = self.resolve_selected()
        if not res:
            return messagebox.showerror("Select file", "Select a BIN file first.")
        kind, f, _ = res
        if kind != "bin":
            return messagebox.showerror("Select file", "Select a BIN file first.")
        out = self.unpack_out.get().strip() or str(ROOT / "out_sections")
        cmd = [PY, str(TOOLS / "fragment_unpack.py"), f["file"], "--out", out]
        self._run_task(cmd)

    def export_asset_paths(self):
        res = self.resolve_selected()
        if not res or res[0] != "sec":
            return messagebox.showerror("Select section", "Select a SECTION first.")
        _, _f, s = res
        paths = s.get("asset_paths", None) or s.get("asset_paths_sample", [])
        if not paths:
            return messagebox.showinfo("No paths", "No asset paths recorded for this section.")
        out = filedialog.asksaveasfilename(
            title="Save asset paths as",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not out:
            return
        Path(out).write_text("\n".join(paths), encoding="utf-8")
        messagebox.showinfo("Saved", f"Wrote:\n{out}")

    def export_dmy_markers(self):
        res = self.resolve_selected()
        if not res or res[0] != "sec":
            return messagebox.showerror("Select section", "Select a SECTION first.")
        _, _f, s = res
        dmys = s.get("tops", {}).get("DMY_", [])
        out = filedialog.asksaveasfilename(
            title="Save DMY markers as",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not out:
            return
        Path(out).write_text("\n".join(dmys), encoding="utf-8")
        messagebox.showinfo("Saved", f"Wrote:\n{out}")

    def map_selected_section(self):
        res = self.resolve_selected()
        if not res:
            return messagebox.showerror("Select section", "Select a SECTION first.")
        if res[0] == "bin":
            return messagebox.showerror("Select section", "Select a child SECTION first.")
        if res[0] != "sec":
            return messagebox.showerror("Select section", "Select a SECTION first.")
        _, f, s = res
        suggested = ROOT / f"resource_map_{Path(f['name']).stem}_{s['id']}.json"
        out = filedialog.asksaveasfilename(
            title="Save resource map JSON as",
            initialfile=suggested.name,
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not out:
            return
        txt = str(Path(out).with_suffix(".txt"))
        cmd = [
            PY, str(TOOLS / "resource_mapper.py"),
            f["file"], "--section", s["id"],
            "--out", out, "--text-out", txt,
            "--summary-families", "30",
            "--summary-items", "5",
        ]
        self._run_task(cmd, on_done=lambda rc: self._show_resource_map_preview(Path(out)) if rc == 0 else None, label="resource map")

    # ---------- Fort Ouph helpers ----------
    def _find_child_by_text(self, parent, text: str):
        for child in self.tree.get_children(parent):
            if self.tree.item(child, "text") == text:
                return child
        return None



    # ---------- Reskin ----------
    def _run_json_command(self, cmd: list[str], label: str) -> dict | None:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            messagebox.showerror("Failed", f"{label} failed to start:\n{exc}")
            return None
        if proc.returncode != 0:
            stderr = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
            messagebox.showerror("Failed", f"{label} failed:\n{stderr.strip()}")
            return None
        try:
            return json.loads(proc.stdout)
        except Exception:
            messagebox.showerror("Failed", f"{label} returned invalid JSON:\n{proc.stdout.strip()}")
            return None






















    # ---------- Advanced patch ----------








    def _load_app_settings(self):
        payload = load_settings(APP_SETTINGS_PATH)
        self._app_settings_payload = payload
        self.external_viewers = viewers_from_settings(payload)
        if self.external_viewers:
            self._select_viewer(self.external_viewers[0].normalized_name())
        else:
            self._set_viewer_fields(ViewerConfig(name=LEGACY_VIEWER_NAME))
        map_path = payload.get("last_resource_map_path", "") if isinstance(payload, dict) else ""
        if isinstance(map_path, str) and map_path.strip():
            self.resource_map_path.set(map_path.strip())
        theme_name = payload.get("theme_name", "") if isinstance(payload, dict) else ""
        self.theme_name.set(normalize_theme_name(theme_name))

        # Restore the last saved paths before startup refreshes are scheduled.
        # A valid project JSON takes precedence because it is the workspace source
        # of truth; otherwise fall back to direct path values from settings.
        project_path = payload.get("last_project_json_path", "") if isinstance(payload, dict) else ""
        if isinstance(project_path, str) and project_path.strip():
            candidate = Path(project_path).expanduser()
            if candidate.is_file():
                try:
                    self._load_project_file(candidate)
                    return
                except Exception:
                    pass
        for key, var in (
            ("iso_path", self.iso_path),
            ("area_server_root_path", self.project_root),
            ("workspace_path", self.workspace_output_dir),
            ("data_folder_path", self.data_dir),
            ("save_folder_path", self.save_dir),
        ):
            value = payload.get(key, "") if isinstance(payload, dict) else ""
            if isinstance(value, str) and value.strip():
                var.set(value.strip())

    def _save_app_settings(self):
        payload = dict(getattr(self, "_app_settings_payload", {}) or {})
        payload = update_settings_with_viewers(payload, self.external_viewers)
        payload["last_resource_map_path"] = self.resource_map_path.get().strip()
        payload["theme_name"] = normalize_theme_name(self.theme_name.get())
        payload["iso_path"] = self.iso_path.get().strip()
        payload["area_server_root_path"] = self.project_root.get().strip()
        payload["workspace_path"] = self.workspace_output_dir.get().strip()
        payload["data_folder_path"] = self.data_dir.get().strip()
        payload["save_folder_path"] = self.save_dir.get().strip()
        APP_SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._app_settings_payload = payload

    def _viewer_display_names(self) -> list[str]:
        return [viewer.normalized_name() for viewer in self.external_viewers]

    def _set_viewer_fields(self, viewer: ViewerConfig):
        self.viewer_name.set(viewer.normalized_name())
        self.viewer_executable.set((viewer.executable or "").strip())
        self.viewer_args.set((viewer.args or "").strip() or DEFAULT_ARGS_TEMPLATE)
        self.viewer_extensions.set(", ".join(viewer.normalized_extensions()))
        self.viewer_enabled.set(bool(viewer.enabled))
        self.viewer_choice.set(viewer.normalized_name())
        # Legacy StringVars stay populated for older code paths and settings compatibility.
        self.external_viewer_path.set((viewer.executable or "").strip())
        self.external_viewer_args.set((viewer.args or "").strip() or DEFAULT_ARGS_TEMPLATE)

    def _refresh_viewer_combo(self):
        names = self._viewer_display_names()
        if hasattr(self, "viewer_combo"):
            self.viewer_combo.configure(values=names)
        current = self.viewer_choice.get().strip()
        if names and current not in names:
            self._select_viewer(names[0])

    def _select_viewer(self, name: str | None = None):
        wanted = (name or self.viewer_choice.get()).strip()
        for viewer in self.external_viewers:
            if viewer.normalized_name() == wanted:
                self._set_viewer_fields(viewer)
                return viewer
        if self.external_viewers:
            viewer = self.external_viewers[0]
            self._set_viewer_fields(viewer)
            return viewer
        viewer = ViewerConfig(name=wanted or LEGACY_VIEWER_NAME)
        self._set_viewer_fields(viewer)
        return None

    def on_viewer_choice_changed(self, _evt=None):
        self._select_viewer()

    def _viewer_from_fields(self) -> ViewerConfig:
        return ViewerConfig(
            name=self.viewer_name.get().strip() or LEGACY_VIEWER_NAME,
            executable=self.viewer_executable.get().strip(),
            args=self.viewer_args.get().strip() or DEFAULT_ARGS_TEMPLATE,
            extensions=parse_extensions(self.viewer_extensions.get()),
            enabled=bool(self.viewer_enabled.get()),
        )

    def save_viewer_config(self):
        viewer = self._viewer_from_fields()
        name = viewer.normalized_name()
        replaced = False
        for idx, existing in enumerate(self.external_viewers):
            if existing.normalized_name() == name:
                self.external_viewers[idx] = viewer
                replaced = True
                break
        if not replaced:
            self.external_viewers.append(viewer)
        self._set_viewer_fields(viewer)
        self._refresh_viewer_combo()
        self._save_app_settings()
        messagebox.showinfo("Viewer saved", f"Saved external viewer: {name}")

    def _selected_viewer_config(self) -> ViewerConfig | None:
        name = self.viewer_choice.get().strip() or self.viewer_name.get().strip()
        for viewer in self.external_viewers:
            if viewer.normalized_name() == name:
                return viewer
        return self._viewer_from_fields() if self.viewer_executable.get().strip() else None

    def _on_close(self):
        try:
            self._save_app_settings()
        except Exception:
            pass
        self.destroy()

    # ---------- Misc ----------
    def _open_folder_path(self, folder: Path):
        if not folder.exists():
            messagebox.showinfo("Folder", str(folder))
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception:
            messagebox.showinfo("Folder", str(folder))

    def _backup_dir(self) -> Path | None:
        data = self.data_dir.get().strip()
        if not data:
            messagebox.showerror("Missing", "Set Data folder in Setup first.")
            return None
        return Path(data) / "_fragmenter_backups"


    def _backup_target_name(self) -> str:
        ctx = getattr(self, "latest_patch_context", None) or {}
        source_name = str(ctx.get("source_bin_name", "") or "").strip()
        if source_name:
            return source_name
        res = self.resolve_selected()
        if res and res[0] == "bin":
            return str(res[1].get("name", "") or "").strip()
        if res and res[0] == "sec":
            return str(res[1].get("name", "") or Path(res[1].get("file", "")).name).strip()
        return ""



    def open_project_folder(self):
        p = self.project_root.get().strip() or str(ROOT)
        try:
            import os
            os.startfile(p)
        except Exception:
            messagebox.showinfo("Folder", p)

    def show_help(self):
        messagebox.showinfo(
            "How to use Fragmenter",
            "1) Load Files: pick your Area Server folder and scan for supported metadata.\n"
            "2) View Results: review discovered sections, summaries, and read-only reports.\n"
            "3) Export Package: build a metadata-only upload package.\n\n"
            "The normal GUI does not create patch, install, reskin, player-economy, or memory-hacking actions.",
        )

    # ---------- Preview / Container Inspector ----------

    def select_inspector_file(self):
        path = filedialog.askopenfilename(title="Select local binary file", initialdir=str(ROOT))
        if path:
            self.inspector_path.set(path)
            self.inspector_status.set(f"Selected: {path}")

    def _inspector_selected_path(self) -> Path | None:
        raw = self.inspector_path.get().strip()
        if not raw:
            messagebox.showinfo("Select file", "Select a local binary file first.")
            return None
        path = Path(raw)
        if not path.is_file():
            messagebox.showerror("Not a file", f"Not a file: {path}")
            return None
        return path

    def _inspector_temp(self, suffix: str) -> Path:
        return self._managed_temp_path(f"inspector_{time.time_ns()}{suffix}")

    def _first_256_hexdump(self, path: Path) -> str:
        with path.open("rb") as f:
            data = f.read(256)
        lines = []
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{off:08X}  {hex_part:<47}  |{ascii_part}|")
        return "\n".join(lines) if lines else "(empty file)"

    def _parse_text_hex_int(self, value: str, default: int) -> int:
        value = (value or "").strip()
        if not value:
            return default
        try:
            return max(0, int(value, 0))
        except ValueError:
            return default

    def _hexdump_with_ascii(self, data: bytes, base_offset: int = 0, limit: int = 8192) -> str:
        shown = data[:limit]
        lines = ["Hex dump", "========", "Offset    00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F  ASCII"]
        for off in range(0, len(shown), 16):
            chunk = shown[off:off + 16]
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{base_offset + off:08X}  {hex_part:<47}  |{ascii_part}|")
        if len(data) > limit:
            lines.append(f"... [hex dump truncated {len(data) - limit} bytes]")
        return "\n".join(lines)

    def _decode_text_hex_bytes(self, data: bytes, requested: str) -> tuple[str, str, bool]:
        if not data:
            return "", "low", True
        nul_ratio = data.count(0) / len(data)
        control = sum(1 for b in data if b < 32 and b not in (9, 10, 13))
        printable_ascii = sum(1 for b in data if b in (9, 10, 13) or 32 <= b < 127)
        printable_ratio = printable_ascii / len(data)
        encodings = {
            "ASCII": ["ascii"],
            "CP932": ["cp932"],
            "UTF-8": ["utf-8", "cp932"],
            "raw": [],
        }.get(requested, ["utf-8", "cp932"])
        if requested == "raw":
            raw_text = data.decode("latin-1", errors="replace")
            return raw_text, "low", False
        best_text = ""
        best_score = -1.0
        for enc in encodings:
            try:
                text = data.decode(enc)
                replacements = 0
            except UnicodeDecodeError:
                text = data.decode(enc, errors="replace")
                replacements = text.count("\ufffd")
            visible = sum(1 for ch in text if ch.isprintable() or ch in "\t\r\n")
            score = (visible / max(1, len(text))) - (replacements / max(1, len(text))) - (nul_ratio * 1.5)
            if score > best_score:
                best_score = score
                best_text = text
        plausible = nul_ratio < 0.08 and control / len(data) < 0.20 and (printable_ratio > 0.55 or best_score > 0.70)
        if best_score > 0.92 and printable_ratio > 0.75:
            confidence = "high"
        elif best_score > 0.72 and printable_ratio > 0.45:
            confidence = "medium"
        else:
            confidence = "low"
        return best_text, confidence, plausible

    def set_text_hex_source(self, path: Path, *, offset: int = 0, length: int | None = None, select: bool = True) -> None:
        self.text_hex_path = path
        with path.open("rb") as handle:
            if length is None:
                handle.seek(offset)
                data = handle.read(64 * 1024)
            else:
                handle.seek(offset)
                data = handle.read(max(0, length))
        self.text_hex_data = data
        self.text_hex_offset.set(hex(offset))
        self.text_hex_length.set(str(len(data)))
        self.text_hex_last_find = -1
        self.render_text_hex_tab()
        if select:
            self.nb.select(self.preview_tab_frames["Text / Hex"])

    def render_text_hex_tab(self) -> None:
        base = self._parse_text_hex_int(self.text_hex_offset.get(), 0)
        length = self._parse_text_hex_int(self.text_hex_length.get(), len(self.text_hex_data) or 4096)
        if self.text_hex_path and self.text_hex_path.is_file():
            try:
                with self.text_hex_path.open("rb") as handle:
                    handle.seek(base)
                    self.text_hex_data = handle.read(length)
            except Exception as exc:
                self._replace_text(self.text_hex_output, f"Could not read Text / Hex source: {exc}\n", readonly=True)
                return
        view = self.text_hex_data[:length]
        decoded, confidence, plausible = self._decode_text_hex_bytes(view, self.text_hex_encoding.get())
        self.text_hex_confidence.set(f"Confidence: {confidence}")
        parts = []
        source = f"Source: {self.text_hex_path}" if self.text_hex_path else "Source: none"
        parts.append(source)
        parts.append(f"Range: offset=0x{base:X}, length={len(view)} bytes, encoding={self.text_hex_encoding.get()}")
        parts.append("")
        parts.append(self._hexdump_with_ascii(view, base))
        parts.append("")
        parts.append("Decoded text")
        parts.append("============")
        if plausible or self.text_hex_show_raw_anyway.get() or self.text_hex_encoding.get() == "raw":
            parts.append(decoded if decoded else "(no decoded text)")
        else:
            parts.append("[suppressed: selected bytes look binary; enable Show raw anyway to view decoded garbage]")
        self._replace_text(self.text_hex_output, "\n".join(parts) + "\n", readonly=True)

    def copy_text_hex_decoded_text(self) -> None:
        text = self.text_hex_output.get("1.0", "end-1c")
        marker = "Decoded text\n============\n"
        if marker in text:
            text = text.split(marker, 1)[1]
        self.clipboard_clear()
        self.clipboard_append(text)
        self.resource_preview_message.set("Copied decoded Text / Hex content to clipboard.")

    def find_next_text_hex(self) -> None:
        query = self.text_hex_find.get()
        if not query:
            return
        start = self.text_hex_last_find + 1
        haystack = self.text_hex_output.get("1.0", "end-1c")
        idx = haystack.lower().find(query.lower(), start)
        if idx < 0 and start > 0:
            idx = haystack.lower().find(query.lower(), 0)
        if idx < 0:
            self.resource_preview_message.set(f"Find: {query!r} not found.")
            return
        self.text_hex_last_find = idx
        self.text_hex_output.tag_remove("find", "1.0", "end")
        begin = f"1.0+{idx}c"
        end = f"{begin}+{len(query)}c"
        self.text_hex_output.tag_add("find", begin, end)
        self.text_hex_output.tag_configure("find", background="#5b5b00", foreground="#ffffff")
        self.text_hex_output.see(begin)

    def _set_inspector_output(self, text: str):
        self._replace_text(self.inspector_output, text, readonly=True)
        self.inspector_output.see("1.0")

    def _render_inspector_preview(self, report: dict, text_report: str, path: Path) -> str:
        lines = ["Preview / Container Inspector", "=" * 31, ""]
        lines.append(f"Detected type: {report.get('detected_type', 'unknown')}")
        gz = report.get("gzip") or {}
        lines.append(f"Gzip info: {gz if gz else 'not gzip'}")
        lines.append(f"Original gzip filename: {gz.get('original_filename') if gz else None}")
        lines.append(f"CCSF offsets/section guesses: {report.get('ccsf', {})}")
        lines.append("Symbol counts:")
        for pfx, info in (report.get("symbols") or {}).items():
            lines.append(f"  {pfx}: {info.get('count', 0)}")
        classes = (report.get("strings") or {}).get("classes") or {}
        embedded_paths = []
        for key in ("model_paths", "texture_paths", "animation_paths", "audio_paths", "paths"):
            embedded_paths.extend(classes.get(key, []))
        lines.append("Embedded paths:")
        lines.extend(f"  - {item}" for item in embedded_paths[:80])
        if not embedded_paths:
            lines.append("  (none found in bounded preview)")
        top_strings = []
        for vals in classes.values():
            top_strings.extend(vals)
        lines.append("Top strings:")
        lines.extend(f"  - {item}" for item in top_strings[:80])
        if not top_strings:
            lines.append("  (none found in bounded preview)")
        lines.append("Magic hits/candidate embedded files:")
        for hit in report.get("magic_hits") or []:
            lines.append(f"  - offset=0x{int(hit.get('offset', 0)):08X} type={hit.get('type')} inside={hit.get('inside', 'file')}")
        if not report.get("magic_hits"):
            lines.append("  (none)")
        lines.extend(["", "First 256-byte hexdump:", self._first_256_hexdump(path), "", "Raw tool summary:", text_report.strip()])
        return "\n".join(lines) + "\n"

    def _load_json_report(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def preview_inspector_file(self):
        path = self._inspector_selected_path()
        if path is None:
            return
        out_json = self._inspector_temp("_preview.json")
        out_text = self._inspector_temp("_preview.txt")
        cmd = [PY, str(ROOT / "fragmenter.py"), "previewbin", str(path), "--out", str(out_json), "--text-out", str(out_text), "--max-strings", "250", "--max-paths", "100", "--max-symbols", "250"]

        def _done(rc: int):
            if rc != 0:
                self.inspector_status.set("Preview failed; see console.")
                return
            report = self._load_json_report(out_json)
            text_report = out_text.read_text(encoding="utf-8") if out_text.exists() else ""
            self.inspector_latest_preview = report
            self.inspector_latest_preview_json = out_json
            self._set_inspector_output(self._render_inspector_preview(report, text_report, path))
            self._populate_inspector_candidates(report.get("magic_hits") or [])
            self.inspector_status.set("Preview complete. Extraction still requires explicit request.")

        self._run_task(cmd, on_done=_done, label="binary preview")

    def _populate_inspector_candidates(self, candidates: list[dict]):
        self.inspector_candidates = candidates
        self.inspector_candidate_tree.delete(*self.inspector_candidate_tree.get_children())
        for i, cand in enumerate(candidates):
            offset = int(cand.get("offset", 0))
            nearby = cand.get("nearby_strings") or []
            if isinstance(nearby, list):
                nearby_text = "; ".join(str(x) for x in nearby[:4])
            else:
                nearby_text = str(nearby)
            self.inspector_candidate_tree.insert("", "end", iid=str(i), values=(f"0x{offset:08X}", cand.get("type", "unknown"), nearby_text))

    def scan_inspector_container(self):
        path = self._inspector_selected_path()
        if path is None:
            return
        if not messagebox.askokcancel("Packed container scan", "This is a packed container. Scan is read-only and may take time."):
            return
        out_json = self._inspector_temp("_scan.json")
        out_text = self._inspector_temp("_scan.txt")
        max_scan = max(1, int(self.inspector_max_scan_mb.get())) * 1024 * 1024
        cmd = [PY, str(ROOT / "fragmenter.py"), "scancontainer", str(path), "--out", str(out_json), "--text-out", str(out_text), "--max-results", "500", "--max-scan-bytes", str(max_scan)]

        def _done(rc: int):
            if rc != 0:
                self.inspector_status.set("Scan failed or was cancelled; see console.")
                return
            report = self._load_json_report(out_json)
            text_report = out_text.read_text(encoding="utf-8") if out_text.exists() else ""
            self.inspector_latest_scan = report
            self._populate_inspector_candidates(report.get("candidates") or [])
            lines = [
                "Container scan complete.",
                f"Detected type: scan report for {report.get('path')}",
                f"Scanned bytes: {report.get('scanned_bytes'):,}",
                f"Magic hits/candidate embedded files: {report.get('candidate_count')}",
                "",
                "Candidates:",
            ]
            for cand in report.get("candidates") or []:
                lines.append(f"  - offset=0x{int(cand.get('offset', 0)):08X} type={cand.get('type')} nearby={cand.get('nearby_strings', [])}")
            lines.extend(["", "First 256-byte hexdump:", self._first_256_hexdump(path), "", "Raw tool summary:", text_report.strip()])
            self._set_inspector_output("\n".join(lines) + "\n")
            self.inspector_status.set("Scan complete. Select a candidate and click extract/decompress if needed.")

        self._run_task(cmd, on_done=_done, label="container scan")

    def extract_inspector_candidate(self):
        path = self._inspector_selected_path()
        if path is None:
            return
        sel = self.inspector_candidate_tree.selection()
        if not sel:
            if (self.inspector_latest_preview or {}).get("gzip"):
                return self.decompress_inspector_file(path)
            messagebox.showinfo("Select candidate", "Select a gzip or CCSF candidate from the inspector list first.")
            return
        cand = self.inspector_candidates[int(sel[0])]
        kind = str(cand.get("type", ""))
        if kind not in {"gzip", "CCSF container"}:
            if not messagebox.askyesno("Unsupported candidate", f"Only gzip and CCSF candidates can be extracted safely. Try anyway as gzip?\n\nSelected type: {kind}"):
                return
            kind = "gzip"
        out_json = self._inspector_temp("_extract.json")
        out_text = self._inspector_temp("_extract.txt")
        out_dir = Path(self.inspector_extract_dir.get().strip() or str(ROOT / "workspace" / "extracted" / "preview_candidates"))
        cmd = [
            PY, str(ROOT / "fragmenter.py"), "scancontainer", str(path), "--out", str(out_json), "--text-out", str(out_text),
            "--max-results", "500", "--max-scan-bytes", str(min(path.stat().st_size, int(cand.get("offset", 0)) + 4096)),
            "--extract-candidates", "--extract-dir", str(out_dir), "--candidate-offset", str(int(cand.get("offset", 0))), "--candidate-type", kind,
        ]

        def _done(rc: int):
            if rc != 0:
                self.inspector_status.set("Extraction failed or was cancelled; see console.")
                return
            report = self._load_json_report(out_json)
            text_report = out_text.read_text(encoding="utf-8") if out_text.exists() else ""
            extracted = report.get("extracted") or []
            self._set_inspector_output("Explicit extraction/decompression result:\n" + json.dumps(extracted, indent=2) + "\n\n" + text_report)
            self.inspector_status.set(f"Extraction complete: {extracted[0].get('path') if extracted else 'no extractable candidate'}")

        self._run_task(cmd, on_done=_done, label="candidate extraction")

    def decompress_inspector_file(self, path: Path):
        out_dir = Path(self.inspector_extract_dir.get().strip() or str(ROOT / "workspace" / "extracted" / "preview_candidates"))
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{path.stem}.gunz"
        out_json = self._inspector_temp("_decompress.json")
        out_text = self._inspector_temp("_decompress.txt")
        cmd = [PY, str(ROOT / "fragmenter.py"), "previewbin", str(path), "--out", str(out_json), "--text-out", str(out_text), "--decompress-out", str(out_path)]

        def _done(rc: int):
            if rc != 0:
                self.inspector_status.set("Decompression failed or was cancelled; see console.")
                return
            report = self._load_json_report(out_json)
            text_report = out_text.read_text(encoding="utf-8") if out_text.exists() else ""
            self._set_inspector_output("Explicit gzip decompression result:\n" + json.dumps(report.get("gzip") or {}, indent=2) + "\n\n" + text_report)
            self.inspector_status.set(f"Decompressed to: {out_path}")

        self._run_task(cmd, on_done=_done, label="gzip decompression")

    def _run_task(self, cmd: list[str], on_done=None, on_line=None, label: str = "running"):
        if self.runner.is_busy():
            messagebox.showwarning("Busy", "A task is already running. Cancel it first if needed.")
            return False
        self.run_status.set(f"running: {label}")

        def _wrapped_done(rc: int):
            if rc == 0:
                self.run_status.set("done")
            elif rc == -15:
                self.run_status.set("cancelled")
            else:
                self.run_status.set("failed")
            if on_done:
                on_done(rc)

        started = self.runner.run(cmd, on_done=_wrapped_done, on_line=on_line)
        if not started:
            self.run_status.set("busy")
        return started

    def cancel_active_task(self):
        if self.runner.cancel():
            self.run_status.set("cancelled")

    def clear_resource_browser(self):
        self.current_resource_map = None
        self.resource_map_context_bin = None
        self.resource_map_context_section = None
        self.resource_family_display_limit = self.resource_family_page_size
        self.selected_family = None
        self.selected_model_symbol = ""
        self.resource_model_symbols = []
        self.resource_related_assets = []
        self.resource_suggested_searches = []
        if hasattr(self, "resource_family_list"):
            self.resource_family_list.delete(0, "end")
        if hasattr(self, "resource_model_list"):
            self.resource_model_list.delete(0, "end")
        if hasattr(self, "resource_related_list"):
            self.resource_related_list.delete(0, "end")
        if hasattr(self, "resource_detail"):
            self.resource_detail.delete("1.0", "end")
            self.resource_detail.insert("end", "No family selected.\n")
        if hasattr(self, "resource_preview_message"):
            self.resource_preview_message.set("")
        if hasattr(self, "native_3d_preview_feasible"):
            self.native_3d_preview_feasible.set(False)
        if hasattr(self, "native_preview_switch"):
            self.native_preview_switch.state(["disabled"])
        if hasattr(self, "native_3d_preview_status"):
            self.native_3d_preview_status.set("Select an extracted asset to evaluate native 3D preview feasibility.")
        if hasattr(self, "resource_family_count"):
            self.resource_family_count.set("0 / 0 shown")
        if hasattr(self, "resource_browser_status"):
            self._set_resource_browser_status("No resource map loaded.")
        if hasattr(self, "resource_show_more_btn"):
            self.resource_show_more_btn.state(["disabled"])
        self._render_suggested_search_actions()

    def _render_resource_family_list(self):
        if not hasattr(self, "resource_family_list"):
            return
        families = (self.current_resource_map or {}).get("families", [])
        total = len(families)
        shown = min(total, int(self.resource_family_display_limit))
        self.resource_family_list.delete(0, "end")
        for fam in families[:shown]:
            self.resource_family_list.insert("end", fam.get("family", "?"))
        self.resource_family_count.set(f"{shown} / {total} shown")
        if shown < total:
            self.resource_show_more_btn.state(["!disabled"])
        else:
            self.resource_show_more_btn.state(["disabled"])

    def show_more_resource_families(self):
        self.resource_family_display_limit += self.resource_family_page_size
        self._render_resource_family_list()

    def on_resource_family_select(self, _evt=None):
        if not self.current_resource_map:
            return
        sel = self.resource_family_list.curselection()
        if not sel:
            return
        idx = sel[0]
        families = self.current_resource_map.get("families", [])
        if idx >= len(families):
            return
        fam = families[idx]
        self.selected_family = fam
        self.resource_model_symbols = list(fam.get("models", []) or [])
        self.selected_model_symbol = self.resource_model_symbols[0] if self.resource_model_symbols else ""
        self._render_resource_model_list()
        self._render_family_related_assets()
        self.resource_preview_message.set("")
        self._render_family_metadata()
        self.update_workflow_status()
        self._refresh_iso_search_correlation_statuses()

    def _render_resource_model_list(self):
        if not hasattr(self, "resource_model_list"):
            return
        self.resource_model_list.delete(0, "end")
        for sym in self.resource_model_symbols:
            self.resource_model_list.insert("end", sym)
        if self.resource_model_symbols:
            self.resource_model_list.selection_set(0)

    def _render_family_related_assets(self):
        fam = self.selected_family or {}
        assets = []
        for cat in ("textures", "materials", "animations", "asset_paths"):
            assets.extend(fam.get(cat, []) or [])
        dedup = []
        for a in assets:
            if a not in dedup:
                dedup.append(a)
        self.resource_related_assets = dedup
        if hasattr(self, "resource_related_list"):
            self.resource_related_list.delete(0, "end")
            for item in dedup:
                self.resource_related_list.insert("end", item)
        self._update_related_asset_probe()

    def _family_search_suggestions(self, fam: dict) -> list[str]:
        raw = fam.get("suggested_searches", []) or []
        suggestions: list[str] = []
        for item in raw:
            q = str(item).strip().lower()
            if q and q not in suggestions:
                suggestions.append(q)
        if not suggestions:
            suggestions = derive_family_search_terms(str(fam.get("family", "")), max_suggestions=10)
        return suggestions[:10]

    def _render_suggested_search_actions(self):
        if not hasattr(self, "resource_suggestions_actions"):
            return
        for w in self.resource_suggestions_actions.winfo_children():
            w.destroy()
        if not self.resource_suggested_searches:
            ttk.Label(
                self.resource_suggestions_actions,
                text="Select a family to populate one-click ISO search queries.",
                foreground=self._theme["muted"],
            ).pack(anchor="w")
            return
        quick = ActionBar(self.resource_suggestions_actions, columns_at_width=[(760, 3), (520, 2)])
        quick.pack(fill="x")
        for query in self.resource_suggested_searches:
            quick.add_button(
                text=f"Send “{query}” to ISO Search",
                command=lambda q=query: self.send_family_query_to_iso_search(q),
            )

    def send_family_query_to_iso_search(self, query: str):
        q = (query or "").strip()
        if not q:
            return
        self.iso_search_query.set(q)
        self.iso_status.set(f"ISO query set from family suggestion: {q}")
        if hasattr(self, "nb"):
            self.nb.select(self.tab_iso)

    def _render_family_metadata(self):
        fam = self.selected_family or {}
        symbol = self.selected_model_symbol or "(none)"
        self.resource_suggested_searches = self._family_search_suggestions(fam)
        self._render_suggested_search_actions()
        lines = [
            f"Family: {fam.get('family', '?')}",
            f"Confidence: {fam.get('confidence', 0)}",
            f"Selected model symbol: {symbol}",
        ]
        if self.resource_suggested_searches:
            lines.append("\nSuggested ISO queries:")
            lines.extend([f"  - {q}" for q in self.resource_suggested_searches])
        notes = fam.get("notes", []) or []
        if notes:
            lines.append("Notes:")
            lines.extend([f"  • {n}" for n in notes[: self.resource_preview_items]])
            more_notes = len(notes) - min(len(notes), self.resource_preview_items)
            if more_notes > 0:
                lines.append(f"  (+{more_notes} more)")
        for cat in ("models", "textures", "materials", "animations", "cameras", "markers", "asset_paths"):
            vals = fam.get(cat, []) or []
            if not vals:
                continue
            shown = vals[: self.resource_preview_items]
            lines.append(f"\n{cat}:")
            lines.extend([f"  - {v}" for v in shown])
            extra = len(vals) - len(shown)
            if extra > 0:
                lines.append(f"  (+{extra} more)")
        self.resource_detail.delete("1.0", "end")
        self.resource_detail.insert("end", "\n".join(lines) + "\n")

    def on_resource_model_select(self, _evt=None):
        sel = self.resource_model_list.curselection()
        if not sel or not self.resource_model_symbols:
            return
        idx = sel[0]
        if idx < len(self.resource_model_symbols):
            self.selected_model_symbol = self.resource_model_symbols[idx]
            self._render_family_metadata()
            if self.selected_model_symbol.startswith(("MDL_", "OBJ_")):
                self._show_3d_message(
                    "No decoded mesh yet. Export OBJ or implement CCS model decode for this block.\n\n"
                    f"Selected identifier: {self.selected_model_symbol}\n",
                    select=True,
                )

    def _selected_related_asset_path(self) -> Path | None:
        sel = self.resource_related_list.curselection() if hasattr(self, "resource_related_list") else ()
        if not sel:
            return None
        idx = sel[0]
        if idx >= len(self.resource_related_assets):
            return None
        internal = self.resource_related_assets[idx]
        if "/" in internal or "\\" in internal:
            return self._iso_output_path(internal)
        return None

    def on_related_asset_select(self, _evt=None):
        self._update_related_asset_probe()

    def _update_related_asset_probe(self):
        out = self._selected_related_asset_path()
        if out is None:
            self.resource_preview_message.set("")
            self.native_3d_preview_feasible.set(False)
            if hasattr(self, "native_preview_switch"):
                self.native_preview_switch.state(["disabled"])
            self.native_3d_preview_status.set("Select an extracted asset to evaluate native 3D preview feasibility.")
            return
        if not out.exists():
            self.resource_preview_message.set(f"Asset not extracted yet: {out.name}")
            self.native_3d_preview_feasible.set(False)
            if hasattr(self, "native_preview_switch"):
                self.native_preview_switch.state(["disabled"])
            self.native_3d_preview_status.set("Native 3D preview feasibility unavailable until asset is extracted.")
            return
        if out.suffix.lower() == ".obj":
            self._load_obj_3d_preview(out, select=False)
            self.resource_preview_message.set(f"OBJ preview ready: {out.name}")
            self.native_3d_preview_feasible.set(True)
            if hasattr(self, "native_preview_switch"):
                self.native_preview_switch.state(["!disabled"])
            return
        probe = probe_model_asset(out)
        self.resource_preview_message.set(self._format_probe_metadata(probe))
        native_ok = bool(probe.get("native_3d_supported"))
        self.native_3d_preview_feasible.set(native_ok)
        if native_ok:
            if hasattr(self, "native_preview_switch"):
                self.native_preview_switch.state(["!disabled"])
            self.native_3d_preview_status.set(
                "Feasible format detected. Native in-app 3D renderer is planned for a later phase; use external viewer today."
            )
        else:
            if hasattr(self, "native_preview_switch"):
                self.native_preview_switch.state(["disabled"])
            self.native_3d_preview_status.set(f"Native 3D preview disabled: {probe.get('native_3d_reason', 'Unsupported format.')}")

    def _format_probe_metadata(self, probe: dict[str, object]) -> str:
        return (
            f"Path: {probe.get('path', '')}\n"
            f"Extension: {probe.get('extension', '(none)')}\n"
            f"Size: {probe.get('size_bytes', 0)} bytes\n"
            f"Signature: {probe.get('signature_hex', '(empty)')}\n"
            f"Format guess: {probe.get('format_name', 'Unknown/custom format')}\n"
            f"Heuristic: {probe.get('heuristic', '')}"
        )

    def _show_resource_map_preview(self, path: Path):
        selection = self.resolve_selected()
        resolved = path.expanduser().resolve()
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception as e:
            self._console_write(f"[resource-map] Preview failed: {e}\n")
            return
        self.resource_map_path.set(str(resolved))
        try:
            self._save_app_settings()
        except Exception:
            pass
        self.current_resource_map = payload if isinstance(payload, dict) else {}
        if selection and selection[0] == "sec":
            _kind, selected_file, selected_section = selection
            self.resource_map_context_bin = selected_file.get("name", "?")
            self.resource_map_context_section = selected_section.get("id", "?")
        else:
            self.resource_map_context_bin = None
            self.resource_map_context_section = self.current_resource_map.get("section")
        self.resource_family_display_limit = self.resource_family_page_size
        fams = len(self.current_resource_map.get("families", []))
        sec = self.current_resource_map.get("section", "?")
        map_context = self._mapped_context_text()
        if fams == 0:
            self._set_resource_browser_status(
                "No resource families detected for this SECTION. "
                "Try another SECTION and/or run Inspect SECTION to confirm symbol presence. "
                f"{map_context}"
            )
        else:
            self._set_resource_browser_status(
                f"Loaded map for section {sec} with {fams} families. {map_context}. Path: {resolved}"
            )
        self._console_write(f"[resource-map] Loaded preview from: {resolved}\n")
        self._render_resource_family_list()
        self.resource_detail.delete("1.0", "end")
        if fams == 0:
            lines = [
                f"Section: {sec}",
                f"Families detected: {fams}",
                "",
                "No resource families were detected in this section.",
                "",
                "Likely causes:",
                "  • Selected section has sparse/no MDL_/TEX_/MAT_/ANM_/DMY_/CAM_ strings.",
                "  • A non-content/system section was chosen.",
                "  • Asset paths are unavailable in this section.",
                "",
                "Try this (one-click):",
                "  • Select another SECTION, then click Map selected section.",
                "  • Click Inspect SECTION to confirm symbol presence.",
            ]
            self.resource_detail.insert("end", "\n".join(lines) + "\n")
        else:
            self.resource_detail.insert("end", "Select a family on the left to view details.\n")
        self.update_workflow_status()

    def _set_resource_browser_status(self, message: str):
        base = (message or "").strip()
        map_path = self.resource_map_path.get().strip()
        if map_path and map_path not in base:
            base = f"{base} (Last map: {map_path})"
        self.resource_browser_status.set(base or "No resource map loaded.")

    def _mapped_context_text(self) -> str:
        if self.resource_map_context_bin and self.resource_map_context_section:
            return f"Map context: BIN {self.resource_map_context_bin} / SECTION {self.resource_map_context_section}"
        if self.resource_map_context_section:
            return f"Map context: SECTION {self.resource_map_context_section}"
        return "Map context: unknown selection"

    def _resource_status_for_selection(self, kind, file_obj, section_obj) -> str:
        if kind == "bin":
            selected_bin = (file_obj or {}).get("name", "?")
            base = f"BIN {selected_bin} selected. Select a child SECTION first."
            if self.current_resource_map:
                return f"{base} Current selection differs from loaded {self._mapped_context_text().lower()}."
            return base
        if kind == "sec":
            selected_bin = (file_obj or {}).get("name", "?")
            selected_section = (section_obj or {}).get("id", "?")
            if self.current_resource_map:
                mapped_bin = self.resource_map_context_bin
                mapped_section = self.resource_map_context_section
                if mapped_section == selected_section and (not mapped_bin or mapped_bin == selected_bin):
                    return (
                        f"SECTION {selected_section} (BIN {selected_bin}) selected. "
                        "Next: Map Resources or browse loaded families."
                    )
                return (
                    f"SECTION {selected_section} (BIN {selected_bin}) selected. Next: Map Resources. "
                    f"Loaded map is for {self._mapped_context_text().replace('Map context: ', '')}."
                )
            return f"SECTION {selected_section} (BIN {selected_bin}) selected. Next: Map Resources."
        if self.current_resource_map:
            return (
                "No selection. Select a BIN or SECTION to see details. "
                f"Loaded map is for {self._mapped_context_text().replace('Map context: ', '')}."
            )
        return "No selection. Select a BIN or SECTION to see details."

    def open_resource_map_file(self):
        p = self.resource_map_path.get().strip()
        if not p:
            return messagebox.showinfo("No map", "No resource map path is available yet.")
        map_path = Path(p).expanduser()
        if not map_path.exists():
            return messagebox.showinfo("Missing map", f"Map file not found:\n{map_path}")
        try:
            os.startfile(str(map_path))
        except Exception:
            messagebox.showinfo("Map file", str(map_path))

    def open_resource_map_folder(self):
        p = self.resource_map_path.get().strip()
        if not p:
            return messagebox.showinfo("No map", "No resource map path is available yet.")
        folder = Path(p).expanduser().parent
        if not folder.exists():
            return messagebox.showinfo("Missing folder", f"Folder not found:\n{folder}")
        try:
            os.startfile(str(folder))
        except Exception:
            messagebox.showinfo("Folder", str(folder))


    # ---------- Correlation workflow ----------
    def _correlation_store_file(self) -> Path:
        raw = self.correlation_store_path.get().strip() or str(ROOT / "fragmenter_correlations.json")
        return Path(raw).expanduser()

    def _load_correlations(self) -> dict:
        store, backup = load_store(self._correlation_store_file())
        if backup:
            self._console_write(f"[correlations] Malformed store backed up to: {backup}\n")
        return store

    def _save_correlations(self, store: dict) -> None:
        atomic_write_json(self._correlation_store_file(), store)

    def _selected_section_context(self) -> tuple[str, str]:
        res = self.resolve_selected()
        if res and res[0] == "sec":
            return str(res[1].get("name", "")), str(res[2].get("id", ""))
        if self.resource_map_context_section:
            return str(self.resource_map_context_bin or ""), str(self.resource_map_context_section)
        if self.current_resource_map:
            return "", str(self.current_resource_map.get("section", ""))
        return "", ""

    def _selected_family_name(self) -> str:
        fam = self.selected_family or {}
        return str(fam.get("family", "")).strip() if isinstance(fam, dict) else ""

    def _correlation_family(self, store: dict, section: str, family: str) -> dict | None:
        return (((store.get("sections") or {}).get(section) or {}).get("families") or {}).get(family)

    def _correlation_counts(self, section: str | None = None, family: str | None = None) -> dict[str, int]:
        counts = {status: 0 for status in CORRELATION_STATUSES}
        section = section or self._selected_section_context()[1]
        family = family if family is not None else self._selected_family_name()
        if not section or not family:
            return counts
        fam = self._correlation_family(self._load_correlations(), section, family)
        for hit in (fam or {}).get("hits", []) or []:
            status = hit.get("status", "unreviewed")
            if status not in counts:
                status = "unreviewed"
            counts[status] += 1
        return counts

    def _correlation_status_for_hit(self, path: str, section: str | None = None, family: str | None = None) -> str:
        section = section or self._selected_section_context()[1]
        family = family if family is not None else self._selected_family_name()
        if not path or not section or not family:
            return "unreviewed"
        fam = self._correlation_family(self._load_correlations(), section, family)
        hit = find_hit(fam or {}, path) if fam else None
        status = (hit or {}).get("status", "unreviewed")
        return status if status in CORRELATION_STATUSES else "unreviewed"

    def update_workflow_status(self):
        selected_bin, selected_section = self._selected_section_context()
        family = self._selected_family_name()
        map_status = "loaded" if self.current_resource_map else "not loaded"
        iso_status = "selected" if self.iso_path.get().strip() else "not selected"
        hit_count = len(self.iso_search_results or [])
        counts = self._correlation_counts(selected_section, family)
        if not selected_section:
            next_action = "Select a SECTION first."
        elif not self.current_resource_map:
            next_action = "Click Map Resources for this section."
        elif not self.iso_path.get().strip():
            next_action = "Pick an ISO, then Search from selected SECTION."
        elif hit_count and not counts.get("confirmed"):
            next_action = "Review ISO hits and mark probable/confirmed/rejected."
        elif counts.get("confirmed"):
            next_action = "Confirmed correlations exist. You can now stage a safe mod plan."
        else:
            next_action = "Pick an ISO, then Search from selected SECTION."
        text = (
            f"Selected BIN: {selected_bin or '(none)'}\n"
            f"Selected SECTION: {selected_section or '(none)'}\n"
            f"Loaded resource map: {map_status}\n"
            f"Selected resource family: {family or '(none)'}\n"
            f"ISO: {iso_status}\n"
            f"ISO search hits: {hit_count}\n"
            f"Correlation store: {self._correlation_store_file()}\n"
            f"Current section/family counts: confirmed={counts.get('confirmed', 0)}, probable={counts.get('probable', 0)}, rejected={counts.get('rejected', 0)}\n"
            f"Next recommended action: {next_action}"
        )
        if hasattr(self, "workflow_status_text"):
            self.workflow_status_text.set(text)
        return text

    def _latest_binary_preview_json_path(self) -> Path | None:
        if self.inspector_latest_preview_json and self.inspector_latest_preview_json.exists():
            return self.inspector_latest_preview_json
        candidate = self._inspector_temp("_manual_preview_import.json")
        report = self.inspector_latest_preview
        if isinstance(report, dict) and report:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
            self.inspector_latest_preview_json = candidate
            return candidate
        return None

    def _preview_discovered_queries(self, report: dict | None = None, limit: int = 80) -> list[str]:
        report = report or self.inspector_latest_preview or {}
        queries: list[str] = []

        def add(value):
            text = str(value).strip()
            if len(text) >= 3 and text not in queries:
                queries.append(text)

        symbols = report.get("symbols") if isinstance(report.get("symbols"), dict) else {}
        for info in (symbols or {}).values():
            if isinstance(info, dict):
                for item in info.get("items") or []:
                    add(item)
        strings = report.get("strings") if isinstance(report.get("strings"), dict) else {}
        classes = (strings or {}).get("classes") if isinstance((strings or {}).get("classes"), dict) else {}
        priority = ("model_paths", "texture_paths", "animation_paths", "audio_paths", "paths", "symbols", "unknown_strings")
        for key in priority:
            vals = (classes or {}).get(key) or []
            if isinstance(vals, list):
                for item in vals:
                    add(item)
                    stem = Path(str(item).replace("\\", "/")).stem
                    add(stem)
        gz = report.get("gzip") if isinstance(report.get("gzip"), dict) else {}
        if gz:
            add(gz.get("original_filename"))
        return queries[:limit]

    def import_preview_symbols_into_correlations(self):
        preview_json = self._latest_binary_preview_json_path()
        if preview_json is None:
            return messagebox.showinfo("No preview", "Run a binary preview first, then import its symbols and paths into correlations.")
        _bin, section_hint = self._selected_section_context()
        store = self._load_correlations()
        try:
            summary = import_binary_preview(store, preview_json, section_hint or None)
            self._save_correlations(store)
        except Exception as exc:
            return messagebox.showerror("Preview import failed", str(exc))
        self._console_write(
            f"[correlations] Imported binary preview into {self._correlation_store_file()}: "
            f"section={summary.get('section')} added={summary.get('families_added')} "
            f"updated={summary.get('families_updated')} hits_added={summary.get('hits_added')} "
            f"embedded_paths={summary.get('embedded_paths')}\n"
        )
        self.update_workflow_status()
        messagebox.showinfo(
            "Imported",
            "Binary preview symbols, section guesses, and embedded paths were imported as unreviewed correlation candidates.",
        )

    def search_iso_containers_for_preview_strings(self):
        terms = self._preview_discovered_queries()
        if not terms:
            return messagebox.showinfo("No preview strings", "Run a binary preview first; no preview-discovered strings or paths are available yet.")
        previous = self.iso_search_query.get()
        self.iso_search_query.set(",".join(terms[:30]))
        try:
            self.search_iso_container_strings(update_status=True)
        finally:
            self.iso_search_query.set(previous)
        hits = len(self.iso_container_string_results or [])
        self._console_write(
            f"[ISO] Preview string/container search used {min(len(terms), 30)} query terms against "
            f"{len(self.iso_container_scan_cache)} cached container scan(s); hits={hits}.\n"
        )
        if not self.iso_container_scan_cache:
            messagebox.showinfo(
                "No scanned containers",
                "No cached container scan results are available. Scan likely ISO containers first; this action searches scan strings/candidates, not ISO filenames.",
            )

    def import_resource_map_into_correlations(self):
        map_path = Path(self.resource_map_path.get().strip() or "").expanduser()
        if not map_path.exists():
            return messagebox.showinfo("No map", "Create or load a resource map first.")
        store = self._load_correlations()
        try:
            summary = import_resource_map(store, map_path)
            self._save_correlations(store)
        except Exception as exc:
            return messagebox.showerror("Correlation import failed", str(exc))
        self._console_write(
            f"[correlations] Imported map into {self._correlation_store_file()}: "
            f"section={summary.get('section')} added={summary.get('families_added')} updated={summary.get('families_updated')}\n"
        )
        self.update_workflow_status()
        messagebox.showinfo("Imported", "Resource map imported into correlations without overwriting confirmed/rejected decisions.")

    def _selected_iso_search_hit(self) -> dict | None:
        sel = self.iso_search_tree.selection() if hasattr(self, "iso_search_tree") else ()
        if not sel:
            return None
        vals = self.iso_search_tree.item(sel[0], "values")
        if len(vals) >= 3:
            status, size, path = vals[0], vals[1], vals[2]
        elif len(vals) >= 2:
            status, size, path = "unreviewed", vals[0], vals[1]
        else:
            return None
        try:
            size = int(size)
        except Exception:
            size = None
        return {"status": str(status), "size": size, "path": str(path)}

    def on_iso_search_hit_select(self, _evt=None):
        hit = self._selected_iso_search_hit()
        if not hit:
            self.correlation_selected_hit_status.set("Selected hit status: none")
            return
        status = self._correlation_status_for_hit(hit.get("path", ""))
        self.correlation_selected_hit_status.set(f"Selected hit status: {status}")

    def _refresh_iso_search_correlation_statuses(self):
        if not hasattr(self, "iso_search_tree"):
            return
        rows = list(self.iso_search_tree.get_children())
        for idx, item in enumerate(rows):
            vals = self.iso_search_tree.item(item, "values")
            path = str(vals[2] if len(vals) >= 3 else vals[1] if len(vals) >= 2 else "")
            status = self._correlation_status_for_hit(path)
            size = vals[1] if len(vals) >= 3 else vals[0] if vals else ""
            self.iso_search_tree.item(item, values=(status, size, path))
            if idx < len(self.iso_search_results):
                self.iso_search_results[idx]["correlation_status"] = status
        self.on_iso_search_hit_select()
        self.update_workflow_status()

    def mark_selected_correlation_hit(self, status: str, notes: str | None = None):
        if status not in CORRELATION_STATUSES:
            return messagebox.showerror("Invalid status", status)
        hit = self._selected_iso_search_hit()
        if not hit:
            return messagebox.showerror("Select hit", "Select an ISO search hit first.")
        _bin, section = self._selected_section_context()
        family = self._selected_family_name()
        if not section or not family:
            return messagebox.showerror("Missing context", "Select a SECTION and resource family before marking correlations.")
        store = self._load_correlations()
        set_hit_status(store, section, family, hit["path"], status, notes)
        if hit.get("size") is not None:
            add_iso_hit(store, section, family, hit["path"], hit.get("size"), status, notes)
        self._save_correlations(store)
        self._console_write(f"[correlations] {section}/{family}: {hit['path']} -> {status}\n")
        self._refresh_iso_search_correlation_statuses()

    def add_edit_correlation_note(self):
        hit = self._selected_iso_search_hit()
        if not hit:
            return messagebox.showerror("Select hit", "Select an ISO search hit first.")
        note = simpledialog.askstring("Correlation note", "Note for selected ISO hit:")
        if note is None:
            return
        status = self._correlation_status_for_hit(hit["path"])
        self.mark_selected_correlation_hit(status, note)

    def _correlation_scan_summary_path(self) -> Path | None:
        candidates: list[Path] = []
        try:
            workspace_value = self.workspace_output_dir.get().strip()
        except Exception:
            workspace_value = ""
        if workspace_value:
            candidates.append(Path(workspace_value) / "reports" / "fragmenter_scan_summary.json")
        candidates.append(REPORTS_WORKSPACE / "fragmenter_scan_summary.json")
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _load_correlation_scan_summary(self) -> tuple[dict | None, Path | None, str | None]:
        summary_path = self._correlation_scan_summary_path()
        if summary_path is None:
            return None, None, None
        try:
            scan = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return None, summary_path, f"Could not read scan summary: {type(exc).__name__}: {exc}"
        if not isinstance(scan, dict):
            return None, summary_path, "Scan summary was not a JSON object."
        return scan, summary_path, None

    @staticmethod
    def _scan_section_counts(section: dict) -> dict[str, int]:
        raw_counts = section.get("category_prefix_counts") or section.get("prefix_counts") or {}
        return {prefix: int(raw_counts.get(prefix, raw_counts.get(f"{prefix}_", 0)) or 0) for prefix in ("TEX", "MDL", "DMY", "MAT", "ANM")}

    @staticmethod
    def _scan_asset_samples(section: dict) -> list[str]:
        samples: list[str] = []
        for key in ("asset_path_samples", "asset_paths_sample", "asset_paths"):
            value = section.get(key)
            if isinstance(value, list):
                samples.extend(str(item) for item in value if item)
        seen: set[str] = set()
        deduped: list[str] = []
        for sample in samples:
            if sample not in seen:
                seen.add(sample)
                deduped.append(sample)
        return deduped

    def _format_automatic_scan_correlations(self, scan: dict | None, summary_path: Path | None, error: str | None = None) -> str:
        lines: list[str] = ["", "Automatic Scan Correlations", "==========================="]
        if summary_path is not None:
            lines.append(f"Source: {summary_path}")
        lines.append("Safety: metadata-only/text-only summary; no source game bytes are embedded.")
        if error:
            lines.append(error)
            return "\n".join(lines) + "\n"
        if not scan:
            lines.append("No automatic scan summary found at workspace/reports/fragmenter_scan_summary.json.")
            return "\n".join(lines) + "\n"

        findings = scan.get("findings") if isinstance(scan.get("findings"), dict) else {}
        embedded = findings.get("embedded_cmp_member_summary") if isinstance(findings.get("embedded_cmp_member_summary"), dict) else {}

        lines.extend(["", "Root town candidates:"])
        root_candidates: list[dict] = []
        for clue in findings.get("town_root_town_clues", []) or []:
            if isinstance(clue, dict):
                root_candidates.append({"file": clue.get("file"), "label": clue.get("label"), "confidence": clue.get("confidence"), "basis": clue.get("basis")})
        for member in embedded.get("town_bin_candidates", []) or []:
            if isinstance(member, dict):
                root_candidates.append({"file": member.get("file") or "data/town.bin", "label": member.get("gzip_original_filename") or "town.bin gzip member", "confidence": member.get("confidence"), "offset": member.get("offset")})
        for member in embedded.get("special_highlights", []) or []:
            if isinstance(member, dict):
                root_candidates.append({"file": member.get("file") or "data/town.bin", "label": ", ".join(member.get("highlight_labels") or []) or member.get("gzip_original_filename"), "confidence": member.get("confidence"), "offset": member.get("offset")})
        required_tokens = ("data/town.bin", "CCSFtown04", "CCSFtown04d")
        existing_text = "\n".join(str(c) for c in root_candidates).lower()
        for token in required_tokens:
            if token.lower() not in existing_text:
                root_candidates.append({"file": "data/town.bin" if token == "data/town.bin" else "(not detected in scan summary)", "label": token, "confidence": "not detected"})
        seen_candidates: set[tuple[str, str, str]] = set()
        for candidate in root_candidates[:80]:
            key = (str(candidate.get("file")), str(candidate.get("label")), str(candidate.get("offset", "")))
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            offset = f" offset={candidate.get('offset')}" if candidate.get("offset") is not None else ""
            lines.append(f"- [{candidate.get('confidence', 'unknown')}] {candidate.get('file', '(unknown)')} -> {candidate.get('label', '(clue)')}{offset}")

        lines.extend(["", "town04/town04d section counts:", "Section | Source | TEX | MDL | DMY | MAT | ANM | Asset path samples", "--- | --- | ---: | ---: | ---: | ---: | ---: | ---"])
        section_rows: list[tuple[str, str, dict[str, int], list[str]]] = []
        for root in scan.get("roots", []) or []:
            if not isinstance(root, dict):
                continue
            for file_info in root.get("files", []) or []:
                if not isinstance(file_info, dict):
                    continue
                source = str(file_info.get("relative_path") or file_info.get("path") or "(unknown)")
                ccsf = file_info.get("ccsf_like") if isinstance(file_info.get("ccsf_like"), dict) else {}
                for section in ccsf.get("sections", []) or []:
                    if not isinstance(section, dict):
                        continue
                    section_id = str(section.get("id") or "")
                    haystack = f"{source} {section_id} {' '.join(self._scan_asset_samples(section))}".lower()
                    if any(token in haystack for token in ("ccsftown04", "ccsftown04d", "town04", "town04d")):
                        section_rows.append((section_id or "(section)", source, self._scan_section_counts(section), self._scan_asset_samples(section)))
        if not section_rows:
            lines.append("(No town04/town04d CCSF section count rows found.)")
        for section_id, source, counts, samples in section_rows[:80]:
            lines.append(f"{section_id} | {source} | {counts['TEX']} | {counts['MDL']} | {counts['DMY']} | {counts['MAT']} | {counts['ANM']} | {', '.join(samples[:8]) or '(none)'}")

        target_stems = ("sr4bac1", "sr4town1", "sr4tre1", "sr4clo1", "sr4clo2")
        lines.extend(["", "Asset path/stem correlations:"])
        found_by_stem: dict[str, list[str]] = {stem: [] for stem in target_stems}
        for root in scan.get("roots", []) or []:
            if not isinstance(root, dict):
                continue
            for file_info in root.get("files", []) or []:
                if not isinstance(file_info, dict):
                    continue
                source = str(file_info.get("relative_path") or file_info.get("path") or "(unknown)")
                ccsf = file_info.get("ccsf_like") if isinstance(file_info.get("ccsf_like"), dict) else {}
                for section in ccsf.get("sections", []) or []:
                    if not isinstance(section, dict):
                        continue
                    for sample in self._scan_asset_samples(section):
                        lower = sample.lower()
                        for stem in target_stems:
                            if stem in lower:
                                found_by_stem[stem].append(f"{source}:{section.get('id', '(section)')} -> {sample}")
        for stem in target_stems:
            hits = sorted(set(found_by_stem[stem]))
            if hits:
                lines.append(f"- {stem}:")
                lines.extend(f"  - {hit}" for hit in hits[:20])
        if not any(found_by_stem.values()):
            lines.append("(No target stems found in scan summary asset path samples.)")
        generated = scan.get("generated_summary") if isinstance(scan.get("generated_summary"), dict) else {}
        shop_mappings = generated.get("root_town_shop_mappings") if isinstance(generated.get("root_town_shop_mappings"), list) else []
        sky_mappings = generated.get("sky_background_mappings") if isinstance(generated.get("sky_background_mappings"), list) else []
        if shop_mappings:
            lines.extend(["", "Known root-town shop families:"])
            for row in shop_mappings:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"- {row.get('stem', '(unknown)')}: {row.get('label', '(shop)')} "
                    f"[{row.get('confidence', 'unknown')}] — {row.get('semantic', '')}"
                )
        if sky_mappings:
            lines.extend(["", "Known sky/background mappings:"])
            for row in sky_mappings:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"- {row.get('identifier', '(unknown)')}: {row.get('semantic', '')} "
                    f"[{row.get('confidence', 'unknown')}]"
                )
        return "\n".join(lines) + "\n"

    def _catalog_report_summary(self, reports: Path) -> dict[str, object]:
        json_path = reports / "town_ccs_asset_catalog.json"
        txt_path = reports / "town_ccs_asset_catalog.txt"
        summary: dict[str, object] = {
            "json_present": json_path.exists(),
            "txt_present": txt_path.exists(),
            "json_path": str(json_path),
            "txt_path": str(txt_path),
            "counts": {},
        }
        if json_path.exists():
            try:
                catalog = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as exc:
                summary["error"] = f"{type(exc).__name__}: {exc}"
            else:
                buckets = catalog.get("buckets") if isinstance(catalog.get("buckets"), dict) else {}
                summary["counts"] = {
                    "files_scanned": int(catalog.get("file_count") or 0),
                    "entries": int(catalog.get("entry_count") or 0),
                    "detected_ccsf_names": len(catalog.get("detected_ccsf_names") or []),
                    "skybox_background": len(buckets.get("skybox_background") or []),
                    "merchant_gate_marker": len(buckets.get("merchant_gate_marker") or []),
                    "npc_model_candidate": len(buckets.get("npc_model_candidate") or []),
                    "texture_candidate": len(buckets.get("texture_candidate") or []),
                    "warnings": len(catalog.get("warnings") or []),
                }
        return summary

    def _extracted_town_members_summary(self, workspace: Path) -> dict[str, object]:
        town_dir = workspace / "extracted_ccs" / "town"
        members: list[dict[str, object]] = []
        if town_dir.exists():
            for path in sorted(town_dir.rglob("*")):
                if path.is_file():
                    try:
                        size = path.stat().st_size
                    except OSError:
                        size = None
                    members.append({"path": str(path.relative_to(workspace)), "name": path.name, "size": size})
        return {"directory": str(town_dir), "present": town_dir.exists(), "count": len(members), "members": members[:200]}

    def _root_town_shop_mappings(self) -> list[dict[str, str]]:
        labels = {
            str(target["display_id"]): str(target["family_label"])
            for target in ROOT_TOWN_PROOF_TARGETS
            if str(target["category"]) == "shop family"
        }
        rows = []
        by_id = {str(row.get("identifier", "")).split(" / ", 1)[0]: row for row in self._root_town_metadata_rows()}
        for stem, label in labels.items():
            row = by_id.get(stem, {})
            rows.append({
                "stem": stem,
                "label": label,
                "family": str(row.get("family") or "shop family"),
                "confidence": str(row.get("confidence") or "medium"),
                "semantic": str(row.get("semantic") or ""),
                "crosslink": str(row.get("crosslink") or ""),
            })
        return rows

    def _sky_background_mappings(self) -> list[dict[str, str]]:
        targets = {"sr4sun1", "sr4clo1 / sr4clo2", "BLT_bg", "CLT_*", "TEX_*", "MDL_*", "MAT_*"}
        rows = []
        for row in self._root_town_metadata_rows():
            identifier = str(row.get("identifier") or "")
            if identifier in targets:
                rows.append({
                    "identifier": identifier,
                    "family": str(row.get("family") or ""),
                    "confidence": str(row.get("confidence") or "medium"),
                    "semantic": str(row.get("semantic") or ""),
                    "crosslink": str(row.get("crosslink") or ""),
                })
        return rows

    def _manual_correlation_summary(self) -> dict[str, object]:
        store = self._load_correlations()
        totals = {status: 0 for status in CORRELATION_STATUSES}
        section_count = 0
        family_count = 0
        for section in (store.get("sections") or {}).values():
            section_count += 1
            for family in (section.get("families") or {}).values():
                family_count += 1
                for hit in family.get("hits") or []:
                    status = hit.get("status") if hit.get("status") in totals else "unreviewed"
                    totals[status] += 1
        return {"store_path": str(self._correlation_store_file()), "sections": section_count, "families": family_count, "hits_by_status": totals}

    def _write_fragmenter_scan_summary(self, workspace: Path | None = None) -> Path:
        workspace = workspace or self._selected_workspace()
        reports = workspace / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        expected_rows = self._expected_report_rows()
        existing: dict[str, object] = {}
        out = reports / "fragmenter_scan_summary.json"
        if out.exists():
            try:
                existing = json.loads(out.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        payload = dict(existing) if isinstance(existing, dict) else {}
        payload.update({
            "schema": "fragmenter.metadata_scan_summary.v1",
            "created_utc": _utc_timestamp(),
            "safety": "metadata-only summary; no source game bytes are embedded",
            "generated_summary": {
                "extracted_town_members": self._extracted_town_members_summary(workspace),
                "catalog_report": self._catalog_report_summary(reports),
                "root_town_shop_mappings": self._root_town_shop_mappings(),
                "sky_background_mappings": self._sky_background_mappings(),
                "iso_probe_results": self._optional_json_report_summary(reports / "iso_client_probe.json"),
                "missing_expected_reports": [str(row.get("name")) for row in expected_rows if row.get("status") == "Missing"],
                "manual_correlations": self._manual_correlation_summary(),
            },
        })
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        return out

    @staticmethod
    def _optional_json_report_summary(path: Path) -> dict[str, object]:
        if not path.exists():
            return {"present": False, "path": str(path)}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"present": True, "path": str(path), "error": f"{type(exc).__name__}: {exc}"}
        return {
            "present": True,
            "path": str(path),
            "top_level_keys": sorted(data.keys()) if isinstance(data, dict) else [],
            "record_count": len(data) if isinstance(data, list) else None,
        }

    def _write_root_town_summary(self, workspace: Path | None = None) -> tuple[Path, Path]:
        reports = (workspace or self._selected_workspace()) / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        rows = self._root_town_highlights_from_scan()
        metadata_rows = self._root_town_metadata_rows()
        payload = {
            "schema": "fragmenter.root_town_summary.v1",
            "created_utc": _utc_timestamp(),
            "source_scan_summary": str(reports / "fragmenter_scan_summary.json"),
            "metadata_row_count": len(metadata_rows),
            "highlight_row_count": len(rows),
            "metadata_rows": metadata_rows,
            "highlight_rows": rows,
            "rows": metadata_rows,
        }
        json_path = reports / "root_town_summary.json"
        txt_path = reports / "root_town_summary.txt"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        txt_path.write_text(self._format_root_town_metadata_table(metadata_rows, rows), encoding="utf-8", newline="\n")
        return txt_path, json_path

    def _write_correlation_report(self, out: Path | None = None) -> Path:
        REPORTS_WORKSPACE.mkdir(parents=True, exist_ok=True)
        out = out or REPORTS_WORKSPACE / f"correlation_report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        self._write_fragmenter_scan_summary(out.parent.parent if out.parent.name == "reports" else self._selected_workspace())
        scan, summary_path, error = self._load_correlation_scan_summary()
        store = self._load_correlations()
        report = generate_report(store)
        report += self._format_automatic_scan_correlations(scan, summary_path, error)
        out.write_text(report, encoding="utf-8", newline="\n")
        json_out = out.with_suffix(".json")
        json_out.write_text(
            json.dumps(
                {
                    "schema": "fragmenter.correlation_report.v1",
                    "created_utc": _utc_timestamp(),
                    "text_report": str(out),
                    "scan_summary": str(summary_path) if summary_path else None,
                    "manual_correlations": self._manual_correlation_summary(),
                    "automatic_summary": (scan or {}).get("generated_summary") if isinstance(scan, dict) else None,
                    "store": store,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
            newline="\n",
        )
        return out

    def open_correlation_report(self):
        out = self._write_correlation_report()
        try:
            os.startfile(str(out))
        except Exception:
            messagebox.showinfo("Correlation Report", str(out))

    def export_correlation_report(self):
        out = filedialog.asksaveasfilename(
            title="Export correlation report",
            initialfile="fragmenter_correlation_report.txt",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not out:
            return
        written = self._write_correlation_report(Path(out))
        messagebox.showinfo("Exported", f"Wrote correlation report:\n{written}")

    def _warn_if_no_confirmed_correlations(self) -> bool:
        _bin, section = self._selected_section_context()
        if not section:
            return True
        store = self._load_correlations()
        sec = (store.get("sections") or {}).get(section) or {}
        confirmed = 0
        for fam in (sec.get("families") or {}).values():
            for hit in fam.get("hits", []) or []:
                if hit.get("status") == "confirmed":
                    confirmed += 1
        if confirmed:
            return True
        return bool(messagebox.askyesno(
            "No confirmed correlations",
            "No confirmed correlations exist for this section yet. Continue anyway?",
        ))



    # ---------- ISO Explorer ----------
    def _norm_iso_path(self, p: str) -> str:
        if not p:
            return ""
        p = str(p).strip()
        p = p.strip()
        p = p.lstrip("/\\")
        p = p.replace("\\", "/")
        while "//" in p:
            p = p.replace("//", "/")
        p = p.lower()
        if ";" in p:
            p = p.split(";", 1)[0]
        return p


    def _toggle_iso_advanced_batch(self):
        frame = getattr(self, "iso_advanced_batch_frame", None)
        if frame is None:
            return
        if self.iso_batch_advanced.get():
            frame.grid()
        else:
            frame.grid_remove()

    def _confirm_batch_extraction(
        self,
        paths: list[str],
        sizes: list[int],
        mode_label: str,
    ) -> bool:
        if not self.iso_batch_advanced.get():
            messagebox.showinfo(
                "Advanced mode required",
                "Batch extraction is hidden by default.\n"
                "Enable “Advanced: enable batch extraction” to continue.",
            )
            return False
        cap = max(1, int(self.iso_batch_max_files.get()))
        hit_count = len(paths)
        if hit_count > cap:
            messagebox.showwarning(
                "Batch cap exceeded",
                f"{mode_label} has {hit_count} file(s), but the current advanced cap is {cap}.\n"
                "Increase the cap in Advanced settings if you intentionally want more.",
            )
            return False
        est_bytes = sum(max(0, int(s)) for s in sizes)
        msg = (
            f"Mode: {mode_label}\n"
            f"Files: {hit_count}\n"
            f"Estimated total bytes: {est_bytes:,}\n\n"
            "Batch extraction can take a while. You can stop it with the global Stop/Cancel button.\n\n"
            "Continue?"
        )
        return bool(messagebox.askokcancel("Confirm batch extraction", msg))

    def _parse_iso_queries(self) -> list[str]:
        raw = self.iso_search_query.get().strip()
        parts = [x.strip() for x in re.split(r"[,;\n]+", raw) if x.strip()]
        return parts

    def _render_iso_search_results(
        self,
        hits: list[dict],
        status_prefix: str = "ISO search",
        context: dict | None = None,
    ):
        self.iso_search_results = hits
        self.iso_search_tree.delete(*self.iso_search_tree.get_children())
        for h in hits:
            self.iso_search_tree.insert("", "end", values=(h.get("correlation_status") or self._correlation_status_for_hit(h.get("path", "")), h.get("size", 0), h.get("path", "")))
        ctx = context or {}
        q_terms = ctx.get("queries") or []
        q_text = ", ".join(str(q) for q in q_terms) if q_terms else "(none)"
        ex_text = str(ctx.get("extensions") or "(none)")
        prefix_text = str(ctx.get("prefix") or "(none)")
        max_scanned = str(ctx.get("max_scanned") or "(unspecified)")
        limit = str(ctx.get("limit") or "(unspecified)")
        self._render_iso_nohit_actions(hits, ctx)

        if hits:
            self.iso_status.set(f"{status_prefix}: {len(hits)} match(es)")
            self._console_write(f"[ISO] {status_prefix}: {len(hits)} matches\n")
        else:
            msg = (
                f"{status_prefix}: 0 match(es). "
                f"queries=[{q_text}] extensions=[{ex_text}] prefix=[{prefix_text}] "
                f"max-scanned={max_scanned} limit={limit}"
            )
            suggestions = (
                "Suggestions: remove extension filter; increase max scanned; broaden query terms; "
                "try section-driven search."
            )
            symbol_note = (
                "Note: MDL_/TEX_ symbol strings may not appear directly in filenames, "
                "so direct symbol search can fail unless those symbols are represented "
                "in path/file names."
            )
            self.iso_status.set(msg)
            self._console_write(f"[ISO] {msg}\n[ISO] {suggestions}\n[ISO] {symbol_note}\n")
            if hasattr(self, "detail"):
                self._replace_text(self.detail, f"{msg}\n{suggestions}\n{symbol_note}\n", readonly=True)
        self.console.see("end")

    def _warning_summary(self, warnings: list[str] | None) -> str:
        if not warnings:
            return ""
        unique = []
        for w in warnings:
            s = str(w).strip()
            if s and s not in unique:
                unique.append(s)
        if not unique:
            return ""
        return f"{len(unique)} traversal warning(s)"

    def _run_iso_query_suggestion(self, query: str):
        q = (query or "").strip()
        if not q:
            return
        self.iso_search_query.set(q)
        self.iso_status.set(f"ISO query set from selected family suggestion: {q}. Running search…")
        self.run_iso_search()

    def _render_iso_nohit_actions(self, hits: list[dict], context: dict):
        frame = getattr(self, "iso_nohit_actions", None)
        if frame is None:
            return
        for w in frame.winfo_children():
            w.destroy()
        if hits:
            frame.grid_remove()
            return
        frame.grid()

        selected_family = context.get("selected_family") or self.selected_family
        family_name = ""
        if isinstance(selected_family, dict):
            family_name = str(selected_family.get("family", "")).strip()
        suggestions = context.get("family_suggestions") or []
        if not suggestions and isinstance(selected_family, dict):
            suggestions = self._family_search_suggestions(selected_family)
        dedup: list[str] = []
        for item in suggestions:
            q = str(item).strip()
            if q and q not in dedup:
                dedup.append(q)
        if family_name:
            ttk.Label(
                frame,
                text=f"Try these from selected family ({family_name}):",
                foreground=self._theme.get("muted", "#9fb3a7"),
            ).pack(anchor="w", pady=(0, 4))
            if not dedup:
                ttk.Label(
                    frame,
                    text="No suggested family queries are available yet. Return to Resource Browser and reselect the family.",
                    foreground=self._theme.get("muted", "#9fb3a7"),
                ).pack(anchor="w")
                return
            quick = ActionBar(frame, columns_at_width=[(700, 3), (420, 2)])
            quick.pack(fill="x")
            for query in dedup[:6]:
                quick.add_button(
                    text=f"Use “{query}”",
                    command=lambda q=query: self._run_iso_query_suggestion(q),
                )
            return
        ttk.Label(
            frame,
            text="No family selected. Map/select a family first for higher-signal query generation, then rerun search.",
            foreground=self._theme.get("warn", "#ffcc66"),
        ).pack(anchor="w")

    def _bounded_iso_result_cap(self, limit: int) -> int:
        # GUI tables must remain bounded even if the CLI is configured with
        # --limit 0 (unlimited). Keep the existing 200-row conservative cap.
        return max(1, limit if limit > 0 else 200)

    def _begin_streaming_iso_results(self, status_prefix: str, context: dict, row_cap: int):
        self.iso_search_results = []
        self.iso_search_tree.delete(*self.iso_search_tree.get_children())
        nohit_frame = getattr(self, "iso_nohit_actions", None)
        if nohit_frame is not None:
            for widget in nohit_frame.winfo_children():
                widget.destroy()
            nohit_frame.grid_remove()
        state = {
            "pending": [],
            "flushing": False,
            "scanned": 0,
            "hits": 0,
            "current": "",
            "limit_reached": False,
            "done": False,
            "warnings": [],
        }
        self.iso_status.set(f"{status_prefix}: searching…")
        self._console_write(f"[ISO] {status_prefix}: streaming results (cap {row_cap})\n")
        self.console.see("end")

        def flush():
            state["flushing"] = False
            batch = state["pending"]
            state["pending"] = []
            for h in batch:
                if len(self.iso_search_results) >= row_cap:
                    continue
                self.iso_search_results.append(h)
                self.iso_search_tree.insert("", "end", values=(h.get("correlation_status") or self._correlation_status_for_hit(h.get("path", "")), h.get("size", 0), h.get("path", "")))
            scanned = int(state.get("scanned") or 0)
            hits = int(state.get("hits") or len(self.iso_search_results))
            visible = len(self.iso_search_results)
            cap_note = f"; showing first {row_cap}" if visible >= row_cap and hits > visible else ""
            if state.get("done"):
                if state.get("limit_reached"):
                    self.iso_status.set(
                        f"{status_prefix}: {visible} match(es) shown; limit reached; narrow search or raise cap"
                    )
                else:
                    self.iso_status.set(f"{status_prefix}: {visible} match(es) shown{cap_note}; scanned {scanned}")
                self._render_iso_nohit_actions(self.iso_search_results, context)
            else:
                current = str(state.get("current") or "")
                self.iso_status.set(
                    f"{status_prefix}: scanned {scanned}; hits {hits}; shown {visible}/{row_cap}; current {current}"
                )

        def schedule_flush():
            if not state["flushing"]:
                state["flushing"] = True
                self.after(75, flush)

        def on_line(line: str):
            s = (line or "").strip()
            if not s.startswith("{"):
                return
            try:
                evt = json.loads(s)
            except Exception:
                return
            if not isinstance(evt, dict):
                return
            kind = evt.get("event")
            if kind == "progress":
                state["scanned"] = int(evt.get("scanned") or state["scanned"] or 0)
                state["hits"] = int(evt.get("hits") or state["hits"] or 0)
                state["current"] = str(evt.get("current") or "")
                schedule_flush()
            elif kind == "hit":
                state["hits"] = max(
                    int(state.get("hits") or 0),
                    len(self.iso_search_results) + len(state["pending"]) + 1,
                )
                if len(self.iso_search_results) + len(state["pending"]) < row_cap:
                    state["pending"].append(evt)
                if len(state["pending"]) >= 25:
                    flush()
                else:
                    schedule_flush()
            elif kind == "done":
                state["done"] = True
                state["scanned"] = int(evt.get("scanned") or state["scanned"] or 0)
                state["hits"] = int(evt.get("hits") or state["hits"] or 0)
                state["limit_reached"] = bool(evt.get("limit_reached"))
                warnings = evt.get("warnings")
                if isinstance(warnings, list):
                    state["warnings"] = warnings
                raw_queries = evt.get("queries")
                if isinstance(raw_queries, list) and raw_queries:
                    context["queries"] = [str(q) for q in raw_queries]
                flush()

        def on_done(rc: int):
            state["done"] = True
            flush()
            if rc != 0:
                self.iso_status.set(f"{status_prefix} failed. See console.")
                return
            summary = self._warning_summary(state.get("warnings") or [])
            if summary:
                current = self.iso_status.get().strip() or status_prefix
                self.iso_status.set(f"{current} ({summary})")
                self._console_write(f"[ISO] {summary}\n")
                for w in state["warnings"][:5]:
                    self._console_write(f"[ISO][warn] {w}\n")
                if len(state["warnings"]) > 5:
                    self._console_write(f"[ISO][warn] ... {len(state['warnings']) - 5} more warning(s)\n")
            self._console_write(f"[ISO] {status_prefix}: {len(self.iso_search_results)} visible match(es)\n")
            self.console.see("end")

        return on_line, on_done

    def run_iso_search(self):
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your PS2 ISO first.")
        queries = self._parse_iso_queries()
        if not queries:
            return messagebox.showerror("Missing", "Enter at least one query.")
        limit = int(self.iso_search_limit.get())
        max_scanned = int(self.iso_search_max_scan.get())
        prefix = self.iso_search_prefix.get().strip()
        ex = self.iso_search_ext.get().strip()
        context = {
            "queries": list(queries),
            "extensions": ex,
            "prefix": prefix,
            "max_scanned": max_scanned,
            "limit": limit,
            "selected_family": self.selected_family,
            "family_suggestions": list(self.resource_suggested_searches),
        }
        cmd = [
            PY, str(TOOLS / "iso_search.py"), "isosearch",
            "--iso", iso,
            "--limit", str(limit),
            "--max-scanned", str(max_scanned),
        ]
        for q in queries:
            cmd += ["--query", q]
        if prefix:
            cmd += ["--prefix", prefix]
        if ex:
            cmd += ["--extensions", ex]

        cmd += ["--stream-ndjson", "--progress-every", "500"]
        on_line, on_done = self._begin_streaming_iso_results(
            "ISO search", context, self._bounded_iso_result_cap(limit)
        )
        self._run_task(cmd, on_done=on_done, on_line=on_line, label="iso search")

    def run_iso_search_from_section(self):
        res = self.resolve_selected()
        if not res or res[0] != "sec":
            return messagebox.showerror("Select section", "Select a SECTION first.")
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your PS2 ISO first.")
        _, f, s = res
        map_path = self._managed_temp_path("resource_map_section_search.json")
        try:
            map_started_at_ns = self._prepare_temp_output(map_path)
        except OSError as exc:
            return messagebox.showerror("Temp output error", f"Could not reset temporary resource map:\n{map_path}\n\n{exc}")
        map_cmd = [
            PY, str(TOOLS / "resource_mapper.py"),
            f["file"], "--section", s["id"], "--out", str(map_path),
            "--summary-families", "20",
            "--summary-items", "4",
        ]

        def _after_map(rc):
            if rc != 0:
                self.iso_status.set("Resource map generation failed.")
                return
            if not self._temp_output_created_by_run(map_path, map_started_at_ns):
                self.iso_status.set("Resource map generation did not create a current temp output.")
                return
            limit = int(self.iso_search_limit.get())
            max_scanned = int(self.iso_search_max_scan.get())
            prefix = self.iso_search_prefix.get().strip()
            ex = self.iso_search_ext.get().strip()
            context = {
                "queries": ["<section-driven terms>"],
                "extensions": ex,
                "prefix": prefix,
                "max_scanned": max_scanned,
                "limit": limit,
                "selected_family": self.selected_family,
                "family_suggestions": list(self.resource_suggested_searches),
            }
            cmd = [
                PY, str(TOOLS / "iso_search.py"), "isosearch-section",
                "--iso", iso,
                "--section-file", str(map_path),
                "--limit", str(limit),
                "--max-scanned", str(max_scanned),
            ]
            if prefix:
                cmd += ["--prefix", prefix]
            if ex:
                cmd += ["--extensions", ex]

            cmd += ["--stream-ndjson", "--progress-every", "500"]
            on_line, on_done = self._begin_streaming_iso_results(
                "ISO section-search", context, self._bounded_iso_result_cap(limit)
            )
            self._run_task(cmd, on_done=on_done, on_line=on_line, label="iso section search")

        self._run_task(map_cmd, on_done=_after_map, label="resource map")

    def run_iso_show_first_paths(self):
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your PS2 ISO first.")
        context = {
            "queries": ["/"],
            "extensions": "(none)",
            "prefix": self.iso_search_prefix.get().strip(),
            "max_scanned": int(self.iso_search_max_scan.get()),
            "limit": 50,
            "selected_family": self.selected_family,
            "family_suggestions": list(self.resource_suggested_searches),
        }
        cmd = [
            PY, str(TOOLS / "iso_search.py"), "isosearch",
            "--iso", iso,
            "--query", "/",
            "--limit", "50",
            "--max-scanned", str(int(self.iso_search_max_scan.get())),
            "--stream-ndjson",
            "--progress-every", "500",
        ]
        prefix = self.iso_search_prefix.get().strip()
        if prefix:
            cmd += ["--prefix", prefix]

        on_line, on_done = self._begin_streaming_iso_results("ISO path preview", context, 50)
        self._run_task(cmd, on_done=on_done, on_line=on_line, label="iso path preview")

    def clear_iso_search_filters(self):
        self.iso_search_query.set("")
        self.iso_search_ext.set("")
        self.iso_search_prefix.set("")
        self.iso_search_limit.set(200)
        self.iso_search_max_scan.set(25000)
        self.iso_status.set("ISO search filters reset to defaults.")

    def _parse_optional_size_filter(self, value: str) -> int | None:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return None
        return max(0, int(text, 0))

    def _iso_3d_extracted_path(self, internal: str) -> Path:
        return safe_preview_output_path(self._selected_workspace(), internal)

    def _iso_3d_embedded_output_dir(self, internal: str) -> Path:
        stem = Path(str(internal or "container")).stem or "container"
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "container"
        digest = hashlib.sha1(str(internal or safe_stem).encode("utf-8", errors="replace")).hexdigest()[:10]
        return self._selected_workspace() / "upload_package" / "iso_preview_embedded" / f"{safe_stem}_{digest}"

    def _iso_3d_selected_row(self) -> dict | None:
        tree = getattr(self, "iso_3d_tree", None)
        if tree is None:
            return None
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Select", "Select an ISO 3D candidate first.")
            return None
        return self.iso_3d_candidate_by_iid.get(sel[0])

    def _iso_3d_embedded_selected_row(self) -> dict | None:
        tree = getattr(self, "iso_3d_embedded_tree", None)
        if tree is None:
            return None
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Select", "Select an embedded ISO 3D candidate first.")
            return None
        return self.iso_3d_embedded_by_iid.get(sel[0])

    def _clear_iso_3d_embedded_candidates(self) -> None:
        self.iso_3d_embedded_candidates = []
        self.iso_3d_embedded_by_iid = {}
        self.iso_3d_embedded_selected = None
        tree = getattr(self, "iso_3d_embedded_tree", None)
        if tree is not None:
            tree.delete(*tree.get_children())

    def _iso_3d_embedded_extract_path(self, cand: dict) -> Path | None:
        path = cand.get("extracted_path")
        return Path(path) if path else None

    def _iso_3d_embedded_likely_role(self, cand: dict) -> str:
        kind = str(cand.get("type") or "").lower()
        magic = str(cand.get("magic") or cand.get("signature") or "").lower()
        nearby = " ".join(str(x) for x in (cand.get("nearby_strings") or [])).lower()
        text = f"{kind} {magic} {nearby}"
        if any(token in text for token in ("mdl", "model", ".obj", ".fbx", ".gltf", ".glb", ".stl", "mesh")):
            return "model/mesh"
        if any(token in text for token in ("tex", "texture", ".bmp", ".png", ".tm2", ".dds", "tim2")):
            return "texture/material"
        if any(token in text for token in ("anim", "motion", "bone", "skel")):
            return "animation/skeleton"
        if "gzip" in text:
            return "compressed payload"
        if "ccsf" in text or "container" in text:
            return "nested container"
        return "unknown embedded asset"

    def _iso_3d_embedded_preview_status(self, cand: dict) -> str:
        explicit = cand.get("preview_status")
        if explicit:
            return str(explicit)
        out = self._iso_3d_embedded_extract_path(cand)
        if not out or not out.exists():
            return "not extracted"
        suffix = out.suffix.lower()
        if suffix == ".obj":
            return "OBJ ready"
        if suffix in {".glb", ".gltf", ".stl", ".fbx"}:
            return "hook prepared"
        if suffix in IMAGE_EXTS or suffix in TEXTURE_PREVIEW_EXTENSIONS:
            return "texture preview ready"
        return "metadata only"

    def _populate_iso_3d_embedded_candidates(self, candidates: list[dict]) -> None:
        tree = getattr(self, "iso_3d_embedded_tree", None)
        if tree is None:
            return
        self.iso_3d_embedded_candidates = candidates
        self.iso_3d_embedded_by_iid = {}
        self.iso_3d_embedded_selected = None
        tree.delete(*tree.get_children())
        for i, cand in enumerate(candidates):
            offset = int(cand.get("offset", 0))
            nearby = cand.get("nearby_strings") or []
            nearby_text = "; ".join(str(x) for x in nearby[:4]) if isinstance(nearby, list) else str(nearby)
            magic = cand.get("magic") or cand.get("signature") or cand.get("signature_hex") or ""
            extracted = self._iso_3d_embedded_extract_path(cand)
            iid = str(i)
            tree.insert("", "end", iid=iid, values=(
                f"0x{offset:08X}",
                cand.get("type", "unknown"),
                magic,
                nearby_text,
                self._iso_3d_embedded_likely_role(cand),
                "yes" if extracted and extracted.exists() else "no",
                self._iso_3d_embedded_preview_status(cand),
            ))
            self.iso_3d_embedded_by_iid[iid] = cand

    def _refresh_iso_3d_embedded_for_selected_container(self) -> None:
        row = self.iso_3d_selected
        if not row:
            self._clear_iso_3d_embedded_candidates()
            return
        internal = str(row.get("path") or "")
        cached = self.iso_container_scan_cache.get(internal)
        if not cached:
            self._clear_iso_3d_embedded_candidates()
            return
        report = cached.get("report") or {}
        candidates = list(report.get("embedded_candidates") or report.get("candidates") or report.get("magic_hits") or [])
        self._populate_iso_3d_embedded_candidates(candidates)

    def refresh_iso_3d_candidates(self) -> None:
        tree = getattr(self, "iso_3d_tree", None)
        if tree is None:
            return
        if not self.iso_index_payload:
            tree.delete(*tree.get_children())
            self._clear_iso_3d_embedded_candidates()
            self._replace_text(self.iso_3d_detail, "Load an ISO index to list 3D model candidates.\n", readonly=True)
            return
        filters: dict[str, object] = {"query": self.iso_3d_search.get().strip()}
        type_filter = self.iso_3d_type_filter.get().strip()
        if type_filter and type_filter != "(all)":
            filters["type_guess"] = type_filter
        try:
            min_size = self._parse_optional_size_filter(self.iso_3d_min_size.get())
            max_size = self._parse_optional_size_filter(self.iso_3d_max_size.get())
        except ValueError:
            self.iso_status.set("ISO 3D filters: min/max size must be integers.")
            return
        if min_size is not None:
            filters["min_size"] = min_size
        if max_size is not None:
            filters["max_size"] = max_size
        if not self.iso_3d_show_low_confidence.get():
            filters["confidence"] = {"high", "medium"}
        rows = list_3d_candidates(self.iso_index_payload, filters)
        self.iso_3d_candidates = rows
        self.iso_3d_candidate_by_iid = {}
        self.iso_3d_selected = None
        self._clear_iso_3d_embedded_candidates()
        tree.delete(*tree.get_children())
        for row in rows:
            internal = str(row.get("path") or "")
            out = self._iso_3d_extracted_path(internal) if internal else None
            extracted = bool(out and out.exists())
            ext = str(row.get("extension") or "")
            type_guess = str(row.get("type_guess") or "")
            if type_guess == "container_candidate":
                preview = "needs container scan" if extracted else "not extracted; needs container scan"
            else:
                preview = "OBJ ready" if extracted and ext == ".obj" else ("hook prepared" if extracted and ext in {".glb", ".gltf", ".stl", ".fbx"} else ("metadata only" if extracted else "not extracted"))
            reason = "; ".join(str(r) for r in (row.get("reasons") or [])[:2])
            iid = tree.insert("", "end", values=(
                f"{row.get('score')} / {row.get('confidence')}",
                internal,
                ext,
                row.get("size", 0),
                "" if row.get("lba") is None else row.get("lba"),
                reason,
                "yes" if extracted else "no",
                preview,
            ))
            self.iso_3d_candidate_by_iid[iid] = row
        self.iso_status.set(f"ISO 3D Preview: {len(rows)} candidate(s)")

    def on_iso_3d_candidate_selected(self, _event=None) -> None:
        row = self._iso_3d_selected_row()
        if not row:
            self._clear_iso_3d_embedded_candidates()
            return
        self.iso_3d_selected = row
        self._refresh_iso_3d_embedded_for_selected_container()
        internal = str(row.get("path") or "")
        out = self._iso_3d_extracted_path(internal)
        extracted = out.exists()
        probe = probe_model_asset(out) if extracted else {}
        if extracted and probe:
            self._write_iso_3d_preview_report(row, out, probe, self._iso_3d_preview_result(out, probe))
        signature = probe.get("signature_hex") or "(available after extraction)"
        guessed = probe.get("format_name") or row.get("type_guess") or "Unknown/custom format"
        preview_status = "not extracted"
        if row.get("type_guess") == "container_candidate":
            preview_status = "needs container scan" if extracted else "not extracted; needs container scan"
        elif extracted and out.suffix.lower() == ".obj":
            preview_status = "OBJ can be rendered by the built-in previewer"
        elif extracted and out.suffix.lower() in {".glb", ".gltf", ".stl", ".fbx"}:
            preview_status = "preview hook prepared; built-in renderer is OBJ-only"
        elif extracted:
            preview_status = "metadata only; use Text/Hex or external tooling"
        lines = [
            f"ISO internal path: {internal}",
            f"Size: {row.get('size', 0)} bytes",
            f"LBA: {row.get('lba')}",
            f"Extension: {row.get('extension')}",
            f"Signature: {signature}",
            f"Guessed format: {guessed}",
            f"Preview status: {preview_status}",
            f"Next action: {'Extract for Preview' if not extracted else row.get('next_action', 'Metadata/Text-Hex')}",
            f"Extraction status: {'extracted' if extracted else 'not extracted'}",
            f"Extraction path: {out}",
            "",
            "Reasons:",
            *[f"- {reason}" for reason in (row.get("reasons") or ["(none)"])],
        ]
        if extracted and probe:
            lines.extend(["", "Detected metadata:", self._format_probe_metadata(probe)])
        elif not extracted:
            lines.extend(["", "Next action: use Extract for Preview to copy this ISO file into the preview workspace."])
        elif row.get("type_guess") == "container_candidate":
            lines.extend(["", "Next action: needs container scan; use Scan Inside Container to inspect embedded assets."])
        else:
            lines.extend(["", "Next actions: Open Text/Hex, inspect signature/reasons, or open the extracted folder."])
        self._replace_text(self._ccsf_model_report_text_widget(), "\n".join(lines) + "\n", readonly=True)
        if not extracted:
            self._show_3d_message("ISO 3D candidate is not extracted yet.\n\nUse “Extract for Preview” in the ISO 3D Preview tab to prepare metadata/probing and OBJ preview.\n", select=False)
        elif out.suffix.lower() == ".obj":
            self._load_obj_3d_preview(out, select=False)
        else:
            self._show_3d_message(f"{self._format_probe_metadata(probe)}\n\n{preview_status}\n", select=False)

    def _iso_3d_preview_result(self, out: Path, probe: dict | None = None) -> str:
        if not out.exists():
            return "not extracted"
        suffix = out.suffix.lower()
        if suffix == ".obj":
            return "OBJ can be rendered by the built-in previewer"
        if suffix in {".glb", ".gltf", ".stl", ".fbx"}:
            return "preview hook prepared; built-in renderer is OBJ-only"
        if probe and probe.get("native_3d_supported"):
            return "native 3D format detected; external viewer recommended"
        return "metadata only; use Text/Hex or external tooling"

    def _write_iso_3d_preview_report(self, row: dict, out: Path | None = None, probe: dict | None = None, preview_result: str | None = None) -> None:
        try:
            report_entry = build_iso_preview_summary(
                row,
                extracted_path=out if out and out.exists() else None,
                probe=probe or {},
                iso_path=self.iso_path.get().strip(),
                preview_result=preview_result or (self._iso_3d_preview_result(out, probe) if out else "not extracted"),
            )
            paths = write_iso_preview_report(self._selected_workspace(), report_entry, append=True)
            self._console_write(f"[ISO 3D Preview] Report updated: {paths['json']}\n")
        except Exception as exc:
            self._console_write(f"[ISO 3D Preview] Report write failed: {exc}\n")

    def extract_iso_3d_selected_for_preview(self) -> None:
        row = self._iso_3d_selected_row()
        if not row:
            return
        internal = str(row.get("path") or "")

        def _done(_out: Path) -> None:
            probe = probe_model_asset(_out)
            self._write_iso_3d_preview_report(row, _out, probe, self._iso_3d_preview_result(_out, probe))
            self.refresh_iso_3d_candidates()
            for iid, candidate in self.iso_3d_candidate_by_iid.items():
                if str(candidate.get("path") or "") == internal:
                    self.iso_3d_tree.selection_set(iid)
                    self.iso_3d_tree.focus(iid)
                    self.iso_3d_tree.see(iid)
                    break
            self.on_iso_3d_candidate_selected()

        self._ensure_iso_entry_extracted(internal, _done, force=True, label="iso 3d extract for preview", iso_3d_preview=True)

    def preview_iso_3d_selected(self) -> None:
        row = self._iso_3d_selected_row()
        if not row:
            return
        out = self._iso_3d_extracted_path(str(row.get("path") or ""))
        if not out.exists():
            self.on_iso_3d_candidate_selected()
            return
        probe = probe_model_asset(out)
        self._write_iso_3d_preview_report(row, out, probe, self._iso_3d_preview_result(out, probe))
        if out.suffix.lower() == ".obj":
            self._load_obj_3d_preview(out, select=True)
        else:
            msg = self._format_probe_metadata(probe)
            if out.suffix.lower() in {".glb", ".gltf", ".stl", ".fbx"}:
                msg += "\n\nPreview hook prepared; built-in renderer is OBJ-only."
            self._show_3d_message(msg + "\n", select=True)

    def on_iso_3d_embedded_candidate_selected(self, _event=None) -> None:
        tree = getattr(self, "iso_3d_embedded_tree", None)
        if tree is None:
            return
        sel = tree.selection()
        if not sel:
            self.iso_3d_embedded_selected = None
            return
        self.iso_3d_embedded_selected = self.iso_3d_embedded_by_iid.get(sel[0])

    def scan_iso_3d_selected_container(self) -> None:
        row = self._iso_3d_selected_row()
        if not row:
            return
        internal = str(row.get("path") or "")
        out = self._iso_3d_extracted_path(internal)

        if not out.exists():
            if not messagebox.askyesno(
                "Extract for Preview required",
                "This ISO 3D container must be extracted before scanning inside it.\n\nRun Extract for Preview now?",
            ):
                self._replace_text(
                    self.iso_3d_detail,
                    "Extract for Preview is required before scanning inside this ISO 3D container.\n",
                    readonly=True,
                )
                return

        def _scan(path: Path) -> None:
            max_scan_mb = int(self.inspector_max_scan_mb.get()) if hasattr(self, "inspector_max_scan_mb") else 64
            max_scan = max(1, max_scan_mb) * 1024 * 1024
            extract_cap = min(max_scan, 8 * 1024 * 1024)
            embedded_dir = self._iso_3d_embedded_output_dir(internal)
            workspace = self._selected_workspace()
            self.iso_status.set("ISO 3D embedded scan running...")
            self.run_status.set("running: iso 3d embedded scan")

            def _worker() -> None:
                try:
                    report = scan_extracted_container_for_preview(path, embedded_dir, max_scan, extract_cap)
                    report_entry = build_embedded_candidate_summary(row, path, report)
                    paths = write_iso_preview_report(workspace, report_entry, append=True)
                except Exception as exc:
                    self.after(0, lambda: (
                        self.run_status.set("failed"),
                        self.iso_status.set("ISO 3D embedded scan failed; see console."),
                        self._console_write(f"[ISO 3D Preview] Embedded scan failed: {exc}\n"),
                    ))
                    return

                def _done() -> None:
                    candidates = list(report.get("embedded_candidates") or [])
                    self._cache_iso_container_scan(internal, path, report)
                    self._populate_iso_3d_embedded_candidates(candidates)
                    if candidates:
                        lines = [
                            "ISO 3D embedded container scan complete.",
                            f"Container: {internal}",
                            f"Extracted path: {path}",
                            f"Embedded output directory: {embedded_dir}",
                            f"Scanned bytes: {report.get('scanned_bytes', 0):,}",
                            f"Embedded candidates: {len(candidates)}",
                            f"Report JSON: {paths['json']}",
                            f"Report text: {paths['text']}",
                            "",
                            "Embedded candidate summary:",
                        ]
                        for cand in candidates[:50]:
                            lines.append(
                                f"- offset=0x{int(cand.get('offset', 0) or 0):08X} "
                                f"type={cand.get('type', 'unknown')} role={cand.get('likely_role') or self._iso_3d_embedded_likely_role(cand)} "
                                f"preview={cand.get('preview_status') or self._iso_3d_embedded_preview_status(cand)}"
                            )
                        if len(candidates) > 50:
                            lines.append(f"... {len(candidates) - 50} more candidate(s)")
                    else:
                        lines = [
                            "ISO 3D embedded container scan complete.",
                            f"Container: {internal}",
                            f"Extracted path: {path}",
                            f"Embedded output directory: {embedded_dir}",
                            f"Scanned bytes: {report.get('scanned_bytes', 0):,}",
                            "no embedded signatures found in scanned range",
                            f"Report JSON: {paths['json']}",
                            f"Report text: {paths['text']}",
                        ]
                    self._replace_text(self._ccsf_model_report_text_widget(), "\n".join(lines) + "\n", readonly=True)
                    self.iso_status.set(f"ISO 3D embedded scan complete: {len(candidates)} candidate(s)")
                    self.run_status.set("done")

                self.after(0, _done)

            threading.Thread(target=_worker, daemon=True).start()

        self._ensure_iso_entry_extracted(internal, _scan, label="iso 3d extract for embedded scan", iso_3d_preview=True)

    def extract_iso_3d_embedded_selected(self) -> None:
        row = self._iso_3d_selected_row()
        cand = self._iso_3d_embedded_selected_row()
        if not row or not cand:
            return
        internal = str(row.get("path") or "")
        cached = self.iso_container_scan_cache.get(internal)
        path = Path(cached["path"]) if cached and cached.get("path") else self._iso_3d_extracted_path(internal)
        if not path.exists():
            return messagebox.showinfo("Not scanned", "Scan inside this ISO 3D container before extracting embedded candidates.")
        kind = str(cand.get("type", ""))
        if kind not in {"gzip", "CCSF container"}:
            if not messagebox.askyesno("Unsupported candidate", f"Only gzip and CCSF candidates can be extracted safely. Try anyway as gzip?\n\nSelected type: {kind}"):
                return
            kind = "gzip"
        out_json = self._inspector_temp("_iso_3d_embedded_extract.json")
        out_text = self._inspector_temp("_iso_3d_embedded_extract.txt")
        out_dir = Path(self.inspector_extract_dir.get().strip() or str(ROOT / "workspace" / "extracted" / "preview_candidates"))
        offset = int(cand.get("offset", 0))
        cmd = [
            PY, str(ROOT / "fragmenter.py"), "scancontainer", str(path),
            "--out", str(out_json), "--text-out", str(out_text),
            "--max-results", "500", "--max-scan-bytes", str(min(path.stat().st_size, offset + 4096)),
            "--extract-candidates", "--extract-dir", str(out_dir),
            "--candidate-offset", str(offset), "--candidate-type", kind,
        ]

        def _done(rc: int) -> None:
            if rc != 0:
                self.iso_status.set("ISO 3D embedded extraction failed or was cancelled; see console.")
                return
            report = self._load_json_report(out_json)
            text_report = out_text.read_text(encoding="utf-8") if out_text.exists() else ""
            extracted = report.get("extracted") or []
            if extracted and extracted[0].get("path"):
                cand["extracted_path"] = extracted[0]["path"]
            self._populate_iso_3d_embedded_candidates(self.iso_3d_embedded_candidates)
            self._replace_text(self.iso_3d_detail, "ISO 3D embedded extraction result:\n" + json.dumps(extracted, indent=2) + "\n\n" + text_report, readonly=True)
            self.iso_status.set(f"ISO 3D embedded extraction complete: {extracted[0].get('path') if extracted else 'no extractable candidate'}")

        self._run_task(cmd, on_done=_done, label="iso 3d embedded extraction")

    def _write_iso_3d_embedded_preview_report(
        self,
        row: dict,
        cand: dict,
        out: Path | None,
        probe: dict[str, object] | None,
        preview_result: str,
    ) -> None:
        internal = str(row.get("path") or "")
        cached = self.iso_container_scan_cache.get(internal) or {}
        scan_report = dict(cached.get("report") or {})
        candidates = list(scan_report.get("embedded_candidates") or self.iso_3d_embedded_candidates or [])
        scan_report["embedded_candidates"] = candidates
        report_entry = build_embedded_candidate_summary(row, cached.get("path") or self._iso_3d_extracted_path(internal), scan_report)
        report_entry["preview_result"] = "embedded_candidate_preview"
        report_entry["embedded_candidate_preview"] = {
            "offset": cand.get("offset"),
            "type": cand.get("type"),
            "likely_role": cand.get("likely_role") or self._iso_3d_embedded_likely_role(cand),
            "extracted_path": str(out) if out else None,
            "preview_status": cand.get("preview_status") or self._iso_3d_embedded_preview_status(cand),
            "preview_result": preview_result,
            "probe": probe or {},
        }
        try:
            paths = write_iso_preview_report(self._selected_workspace(), report_entry, append=True)
            self._console_write(f"[ISO 3D Preview] Embedded preview report updated: {paths['json']}\n")
        except Exception as exc:
            self._console_write(f"[ISO 3D Preview] Embedded preview report write failed: {exc}\n")

    def preview_iso_3d_embedded_selected(self) -> None:
        row = self._iso_3d_selected_row()
        cand = self._iso_3d_embedded_selected_row()
        if not row or not cand:
            return
        out = self._iso_3d_embedded_extract_path(cand)
        if not out or not out.exists():
            self.iso_status.set("Extracting embedded candidate before preview...")
            self.extract_iso_3d_embedded_selected()
            return messagebox.showinfo(
                "Extracting embedded candidate",
                "This embedded candidate has not been extracted yet. Extraction has been started; preview it again after extraction completes.",
            )

        probe = probe_model_asset(out)
        suffix = out.suffix.lower()
        msg = self._format_probe_metadata(probe)
        if suffix == ".obj":
            cand["preview_status"] = "OBJ preview opened"
            self._load_obj_3d_preview(out, select=True)
            preview_result = "OBJ can be rendered by the built-in previewer"
        elif suffix in IMAGE_EXTS or suffix in TEXTURE_PREVIEW_EXTENSIONS or suffix in {".png", ".bmp", ".tm2", ".tim2"}:
            try:
                texture_meta = self._show_image_preview(out)
                meta = texture_meta or extract_texture_metadata(out)
                unsupported = suffix not in TEXTURE_PREVIEW_EXTENSIONS or meta.get("dimensions") is None
                self._replace_text(self.preview_tabs["Texture"], texture_metadata_text(meta, [], unsupported=unsupported), readonly=True)
                self.nb.select(self.preview_tabs["Texture"].master)
                cand["preview_status"] = "texture preview opened"
                preview_result = "texture metadata/preview opened"
            except Exception as exc:
                cand["preview_status"] = "texture metadata only"
                preview_result = f"texture preview unavailable: {exc}"
                self._show_3d_message(f"{msg}\n\nTexture preview unavailable: {exc}\n", select=True)
        else:
            cand["preview_status"] = "metadata/Text-Hex opened"
            preview_result = "metadata only; opened in Text/Hex"
            self.set_text_hex_source(out, select=True)
            self._show_3d_message(msg + "\n\nEmbedded candidate opened in Text/Hex for inspection.\n", select=False)

        self._write_iso_3d_embedded_preview_report(row, cand, out, probe, preview_result)
        self._populate_iso_3d_embedded_candidates(self.iso_3d_embedded_candidates)

    def open_iso_3d_selected_text_hex(self) -> None:
        row = self._iso_3d_selected_row()
        if not row:
            return
        out = self._iso_3d_extracted_path(str(row.get("path") or ""))
        if not out.exists():
            return messagebox.showinfo("Not extracted", "Extract this ISO candidate before opening Text/Hex.")
        self.set_text_hex_source(out, select=True)

    def open_iso_3d_extracted_folder(self) -> None:
        row = self._iso_3d_selected_row()
        folder = self._iso_3d_extracted_path(str(row.get("path") or "")).parent if row else Path(self.iso_extract_dir.get().strip() or ".")
        self._open_folder_path(folder)

    def _selected_iso_entry(self) -> dict | None:
        """Return the selected top-level ISO file entry from search or resolved trees."""
        candidates = []
        for attr, source in (("iso_search_tree", "search"), ("iso_tree", "resolved")):
            tree = getattr(self, attr, None)
            if tree is None:
                continue
            sel = tree.selection()
            if not sel:
                continue
            vals = tree.item(sel[0], "values")
            if not vals:
                continue
            if source == "search":
                path = str(vals[2] if len(vals) >= 3 else vals[1] if len(vals) >= 2 else "")
                size = vals[1] if len(vals) >= 3 else vals[0] if vals else 0
                found = True
            else:
                found = str(vals[0]) == "YES"
                size = vals[1] if len(vals) >= 2 else 0
                path = str(vals[2] if len(vals) >= 3 else "")
            try:
                size_int = int(size)
            except Exception:
                size_int = 0
            if path:
                candidates.append({"path": path, "size": size_int, "found": found, "source": source})
        if not candidates:
            messagebox.showerror("Select", "Select an ISO file entry from Search hits or Resolved references first.")
            return None
        focused = self.focus_get()
        for cand in candidates:
            tree = getattr(self, "iso_search_tree" if cand["source"] == "search" else "iso_tree", None)
            if focused is tree:
                return cand
        return candidates[0]

    def _ensure_iso_entry_extracted(self, internal: str, on_ready, *, force: bool = False, label: str = "iso extract selected", iso_3d_preview: bool = False):
        iso = self.iso_path.get().strip()
        if not iso:
            messagebox.showerror("Missing", "Pick your ISO first.")
            return False
        out = self._iso_3d_extracted_path(internal) if iso_3d_preview else self._iso_output_path(internal)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and not force:
            on_ready(out)
            return True

        cmd = [PY, str(TOOLS / "iso_extract.py"), iso, internal, "--out", str(out)]
        self.iso_status.set(f"Extracting {internal} before next action. Stop/Cancel is available while running.")

        def _done(rc: int):
            if rc != 0:
                self.iso_status.set("Extraction failed or was cancelled; see console.")
                return
            if not out.exists():
                self.iso_status.set(f"Extraction finished but output is missing: {out}")
                return
            on_ready(out)

        return self._run_task(cmd, on_done=_done, label=label)

    def _preview_iso_extracted_path_with_binary_preview(self, path: Path):
        out_json = self._inspector_temp("_iso_preview.json")
        out_text = self._inspector_temp("_iso_preview.txt")
        cmd = [
            PY, str(ROOT / "fragmenter.py"), "previewbin", str(path),
            "--out", str(out_json), "--text-out", str(out_text),
            "--max-strings", "500", "--max-paths", "200", "--max-symbols", "500",
        ]

        def _done(rc: int):
            if rc != 0:
                self.iso_status.set("Binary preview failed; see console.")
                return
            report = self._load_json_report(out_json)
            text_report = out_text.read_text(encoding="utf-8") if out_text.exists() else ""
            self.inspector_path.set(str(path))
            self.inspector_latest_preview = report
            self.inspector_latest_preview_json = out_json
            self._set_inspector_output(self._render_inspector_preview(report, text_report, path))
            self._populate_inspector_candidates(report.get("magic_hits") or [])
            self.nb.select(self.tab_inspector)
            self.iso_status.set(f"Preview complete via binary_preview.py: {path}")

        self._run_task(cmd, on_done=_done, label="binary preview")

    def preview_iso_selected_file(self):
        entry = self._selected_iso_entry()
        if not entry:
            return
        if not entry.get("found", True):
            return messagebox.showerror("Not found", "That path was not found in the ISO index.")
        self._ensure_iso_entry_extracted(
            entry["path"],
            self._preview_iso_extracted_path_with_binary_preview,
            label="iso extract for preview",
        )

    def extract_then_preview_iso_selected_file(self):
        entry = self._selected_iso_entry()
        if not entry:
            return
        if not entry.get("found", True):
            return messagebox.showerror("Not found", "That path was not found in the ISO index.")
        self._ensure_iso_entry_extracted(
            entry["path"],
            self._preview_iso_extracted_path_with_binary_preview,
            force=True,
            label="iso extract then preview",
        )

    def _cache_iso_container_scan(self, internal: str, path: Path, report: dict):
        self.iso_container_scan_cache[internal] = {"path": str(path), "report": report, "scanned_at": time.time()}
        self.search_iso_container_strings(update_status=False)

    def scan_iso_selected_container(self):
        entry = self._selected_iso_entry()
        if not entry:
            return
        if not entry.get("found", True):
            return messagebox.showerror("Not found", "That path was not found in the ISO index.")

        def _scan(path: Path):
            out_json = self._inspector_temp("_iso_scan.json")
            out_text = self._inspector_temp("_iso_scan.txt")
            max_scan = max(1, int(self.inspector_max_scan_mb.get())) * 1024 * 1024
            cmd = [
                PY, str(ROOT / "fragmenter.py"), "scancontainer", str(path),
                "--out", str(out_json), "--text-out", str(out_text),
                "--max-results", "500", "--max-scan-bytes", str(max_scan),
                "--max-strings", "5000", "--max-paths", "1000", "--max-symbols", "1000",
            ]

            def _done(rc: int):
                if rc != 0:
                    self.iso_status.set("Container scan failed or was cancelled; see console.")
                    return
                report = self._load_json_report(out_json)
                text_report = out_text.read_text(encoding="utf-8") if out_text.exists() else ""
                self.inspector_path.set(str(path))
                self.inspector_latest_scan = report
                self._populate_inspector_candidates(report.get("candidates") or [])
                self._set_inspector_output("ISO container scan complete.\n" + text_report + "\n")
                self._cache_iso_container_scan(entry["path"], path, report)
                self.nb.select(self.tab_inspector)
                self.iso_status.set(f"Container scan complete; cached strings for {entry['path']}")

            self._run_task(cmd, on_done=_done, label="iso container scan")

        self._ensure_iso_entry_extracted(entry["path"], _scan, label="iso extract for container scan")

    def _iso_container_search_terms(self) -> list[str]:
        terms = self._parse_iso_queries()
        if not terms:
            terms = ["TEX_", "MDL_", ".bmp", ".max", ".mdl", ".tm2"]
        return terms

    def _strings_from_container_report(self, report: dict) -> list[str]:
        out: list[str] = []
        for pfx_info in (report.get("symbols") or {}).values():
            if isinstance(pfx_info, dict):
                out.extend(str(x) for x in pfx_info.get("items") or [])
        classes = (report.get("strings") or {}).get("classes") or {}
        if isinstance(classes, dict):
            for vals in classes.values():
                if isinstance(vals, list):
                    out.extend(str(x) for x in vals)
        for cand in report.get("candidates") or []:
            nearby = cand.get("nearby_strings") or []
            if isinstance(nearby, list):
                out.extend(str(x) for x in nearby)
        dedup: list[str] = []
        for item in out:
            if item and item not in dedup:
                dedup.append(item)
        return dedup

    def search_iso_container_strings(self, update_status: bool = True):
        terms = self._iso_container_search_terms()
        terms_lower = [t.lower() for t in terms]
        matches: list[dict] = []
        for internal, cached in self.iso_container_scan_cache.items():
            report = cached.get("report") or {}
            for value in self._strings_from_container_report(report):
                low = value.lower()
                if any(term in low for term in terms_lower):
                    matches.append({"container": internal, "path": cached.get("path"), "string": value})
        self.iso_container_string_results = matches
        widget = getattr(self, "iso_container_string_text", None)
        if widget is not None:
            widget.delete("1.0", "end")
            if matches:
                for hit in matches[:500]:
                    widget.insert("end", f"{hit['container']} :: {hit['string']}\n")
            else:
                widget.insert("end", f"No cached container-string hits for: {', '.join(terms)}\nScan selected containers first, or broaden the query.\n")
            widget.see("1.0")
        if update_status:
            self.iso_status.set(f"Container string search: {len(matches)} hit(s) for {', '.join(terms)}")

    def extract_iso_search_selected(self):
        sel = self.iso_search_tree.selection()
        if not sel:
            return messagebox.showerror("Select", "Select a search hit first.")
        vals = self.iso_search_tree.item(sel[0], "values")
        if not vals:
            return
        internal = str(vals[2] if len(vals) >= 3 else vals[1])
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your ISO first.")
        out = self._iso_output_path(internal)
        cmd = [PY, str(TOOLS / "iso_extract.py"), iso, internal, "--out", str(out)]
        self.iso_status.set("Single-hit extraction queued. Stop/Cancel is available while running.")
        self._run_task(cmd, label="iso extract selected")

    def extract_likely_model_files(self):
        if not self.selected_family:
            return messagebox.showinfo("No family", "Select a family first.")
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your PS2 ISO first.")
        queries = suggested_iso_queries(
            self.selected_family.get("family", ""),
            self.selected_model_symbol,
            self.resource_related_assets,
        )
        for q in self._family_search_suggestions(self.selected_family or {}):
            if q not in queries:
                queries.append(q)
        queries = queries[:10]
        if not queries:
            return messagebox.showinfo("No queries", "No query terms could be generated.")
        out_json = self._managed_temp_path("iso_model_search.json")
        try:
            out_started_at_ns = self._prepare_temp_output(out_json)
        except OSError as exc:
            return messagebox.showerror("Temp output error", f"Could not reset temporary ISO search output:\n{out_json}\n\n{exc}")
        cmd = [
            PY, str(TOOLS / "iso_search.py"), "isosearch",
            "--iso", iso,
            "--limit", str(int(self.iso_search_limit.get())),
            "--max-scanned", str(int(self.iso_search_max_scan.get())),
            "--extensions", self.iso_search_ext.get().strip() or "max,mdl,mat,anm,bmp,png,jpg,jpeg",
            "--out", str(out_json),
        ]
        for q in queries:
            cmd += ["--query", q]
        context = {
            "queries": list(queries),
            "extensions": self.iso_search_ext.get().strip() or "max,mdl,mat,anm,bmp,png,jpg,jpeg",
            "prefix": self.iso_search_prefix.get().strip(),
            "max_scanned": int(self.iso_search_max_scan.get()),
            "limit": int(self.iso_search_limit.get()),
            "selected_family": self.selected_family,
            "family_suggestions": list(self.resource_suggested_searches),
        }

        def _done(rc):
            if rc != 0:
                self.iso_status.set("Likely-model search failed.")
                return
            if not self._temp_output_created_by_run(out_json, out_started_at_ns):
                self.iso_status.set("Likely-model search did not create a current temp output.")
                return
            try:
                payload = json.loads(out_json.read_text(encoding="utf-8"))
                hits = payload.get("hits", []) if isinstance(payload, dict) else []
            except Exception:
                hits = []
            self._render_iso_search_results(hits, "Likely model search", context)

        self._run_task(cmd, on_done=_done, label="iso likely model search")

    def preview_iso_search_selected(self):
        self.preview_iso_selected_file()

    def preview_related_asset(self):
        out = self._selected_related_asset_path()
        if out is None:
            return messagebox.showinfo("No asset", "Select a related asset path first.")
        if not out.exists():
            self.resource_preview_message.set(f"Asset not extracted yet: {out.name}")
            return
        self.preview_file_with_fallback(out)

    def preview_file_with_fallback(self, out: Path):
        probe = probe_model_asset(out)
        meta = self._format_probe_metadata(probe)
        ext = out.suffix.lower()
        if ext in IMAGE_EXTS or ext in TEXTURE_PREVIEW_EXTENSIONS:
            texture_meta = self._show_image_preview(out)
            self._replace_text(self.preview_tabs["Texture"], texture_metadata_text(texture_meta or extract_texture_metadata(out), self._strings_from_container_report(getattr(self, "inspector_latest_scan", {}) or {}), unsupported=False), readonly=True)
            self.resource_preview_message.set(meta)
            self._update_related_asset_probe()
            return
        msg = (
            "Preview unsupported for this format (metadata shown).\n"
            f"{meta}\n"
            "Use Open in external viewer or Open containing folder."
        )
        self.resource_preview_message.set(msg)
        messagebox.showinfo("Preview not supported", msg)

    def open_related_in_external_viewer(self):
        out = self._selected_related_asset_path()
        if out is None:
            return messagebox.showinfo("No asset", "Select a related asset path first.")
        if not out.exists():
            return messagebox.showinfo("Not extracted", f"Selected asset does not exist yet:\n{out}")

        viewer = self._selected_viewer_config()
        if viewer is None or not viewer.executable.strip():
            return messagebox.showerror("Viewer not configured", "Save or select an external viewer executable first. Fragmenter does not require any viewer to be installed.")
        if not viewer.enabled:
            return messagebox.showinfo("Viewer disabled", f"Enable the selected viewer before launching:\n{viewer.normalized_name()}")

        executable = Path(viewer.executable).expanduser()
        if not executable.exists():
            return messagebox.showerror("Viewer executable missing", f"Executable not found:\n{executable}")
        viewer.executable = str(executable)

        cmd, appended_path = build_viewer_command(out, viewer)
        if appended_path:
            messagebox.showwarning(
                "Path appended",
                'The args template does not include "{path}". Fragmenter will append the selected asset path automatically for this launch.',
            )
        try:
            subprocess.Popen(cmd, cwd=str(ROOT))
            if viewer.normalized_name() not in self._viewer_display_names():
                self.external_viewers.append(viewer)
                self._refresh_viewer_combo()
            self._save_app_settings()
        except Exception as e:
            messagebox.showerror("Viewer error", str(e))

    def open_related_containing_folder(self):
        out = self._selected_related_asset_path()
        if out is None:
            return messagebox.showinfo("No asset", "Select a related asset path first.")
        folder = out.parent
        if not folder.exists():
            return messagebox.showinfo("Missing folder", f"Folder not found:\n{folder}")
        try:
            os.startfile(str(folder))
        except Exception:
            messagebox.showinfo("Folder", str(folder))

    def _show_image_preview(self, path: Path):
        identifiers = self._strings_from_container_report(getattr(self, "inspector_latest_scan", {}) or {})
        return render_texture_window(self, path, nearby_identifiers=identifiers)

    def extract_iso_search_all(self):
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your ISO first.")
        if not self.iso_search_results:
            return messagebox.showinfo("None", "No search hits to extract.")
        hits = [h for h in self.iso_search_results if h.get("path")]
        paths = [h.get("path", "") for h in hits]
        sizes = [int(h.get("size", 0) or 0) for h in hits]
        if not self._confirm_batch_extraction(paths, sizes, "Search hits batch extraction"):
            return
        self.iso_status.set(
            f"Batch extraction queued ({len(paths)} files, est {sum(sizes):,} bytes). Stop/Cancel is available."
        )
        self._run_extract_queue(iso, paths, label="iso extract search hits")

    def pick_iso(self):
        p = filedialog.askopenfilename(title="Select PS2 ISO", filetypes=[("ISO files", "*.iso"), ("All files", "*.*")])
        if p:
            self.iso_path.set(p)
            self._update_title_status_strip()
            self.refresh_project_tree()

    def pick_iso_index_out(self):
        p = filedialog.asksaveasfilename(title="Save ISO index JSON as", defaultextension=".json", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if p:
            self.iso_index_path.set(p)

    def pick_iso_extract_dir(self):
        p = filedialog.askdirectory(title="Select extract folder")
        if p:
            self.iso_extract_dir.set(p)

    def pick_external_viewer(self):
        p = filedialog.askopenfilename(title="Select viewer executable", filetypes=[("All files", "*.*")])
        if p:
            self.viewer_executable.set(p)
            self.external_viewer_path.set(p)

    def open_iso_extract_dir(self):
        p = self.iso_extract_dir.get().strip()
        if not p:
            return
        try:
            import os
            os.startfile(p)
        except Exception:
            messagebox.showinfo("Extract folder", p)

    def open_iso_index_file(self):
        p = self.iso_index_path.get().strip()
        if not p:
            return
        try:
            import os
            os.startfile(p)
        except Exception:
            messagebox.showinfo("Index file", p)


    def build_iso_index(self):
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your PS2 ISO first.")
        out = self.iso_index_path.get().strip() or str(ROOT / "iso_index.json")
        self.iso_index_path.set(out)

        # Reset progress UI
        self.iso_progress.set(0.0)
        self.iso_progress_text.set("")
        self.iso_current.set("")
        try:
            self.iso_progress_bar.configure(mode="indeterminate")
            self.iso_progress_bar.start(10)
        except Exception:
            pass

        self.iso_status.set("Indexing ISO... (counting files)")
        cmd = [PY, str(TOOLS / "iso_index.py"), iso, "--out", out]

        total_holder = {"total": None}

        def on_line(line: str):
            s = (line or "").strip()
            if not s.startswith("[ISO_INDEX]"):
                return
            # Formats:
            # [ISO_INDEX] PHASE <text>
            # [ISO_INDEX] TOTAL <n>
            # [ISO_INDEX] PROGRESS <done> <total> <path>
            parts = s.split(" ", 2)
            if len(parts) < 3:
                return
            kind = parts[1]
            rest = parts[2]

            if kind == "PHASE":
                self.iso_status.set(rest)
                return

            if kind == "TOTAL":
                try:
                    total = int(rest.strip())
                except Exception:
                    total = None
                total_holder["total"] = total
                if total and total > 0:
                    # Switch to determinate
                    try:
                        self.iso_progress_bar.stop()
                        self.iso_progress_bar.configure(mode="determinate", maximum=100.0)
                    except Exception:
                        pass
                    self.iso_progress.set(0.0)
                    self.iso_progress_text.set(f"0% (0/{total})")
                    self.iso_status.set("Indexing ISO... (building index)")
                return

            if kind == "PROGRESS":
                # rest: "<done> <total> <path>"
                try:
                    done_str, remain = rest.split(" ", 1)
                    total_str, path = remain.split(" ", 1)
                    done = int(done_str); total = int(total_str)
                except Exception:
                    return
                if total <= 0:
                    return
                pct = (done / total) * 100.0
                self.iso_progress.set(pct)
                self.iso_progress_text.set(f"{pct:.1f}% ({done}/{total})")
                self.iso_current.set(path)
                return

        def _done(rc):
            try:
                self.iso_progress_bar.stop()
                self.iso_progress_bar.configure(mode="determinate", maximum=100.0)
            except Exception:
                pass

            outp = Path(out)
            if rc == 0 and outp.exists() and outp.stat().st_size > 0:
                self.iso_progress.set(100.0)
                t = total_holder.get("total")
                if t:
                    self.iso_progress_text.set(f"100% ({t}/{t})")
                else:
                    self.iso_progress_text.set("100%")
                self.iso_current.set("")
                self.iso_status.set(f"Done. Wrote: {outp.name} ({outp.stat().st_size} bytes)")
                self.load_iso_index()
            else:
                self.iso_status.set("Index failed. See console output.")

        self._run_task(cmd, on_done=_done, on_line=on_line)

    def load_iso_index(self):
        p = Path(self.iso_index_path.get().strip())
        if not p.exists():
            return messagebox.showerror("Missing", "ISO index JSON not found. Build it first.")
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            files = payload.get("files", [])
            self.iso_index_payload = payload if isinstance(payload, dict) else None
            self.iso_index = {self._norm_iso_path(e.get("path","")): e for e in files if isinstance(e, dict) and e.get("path")}
            self.refresh_iso_3d_candidates()
            self.iso_status.set(f"Loaded ISO index: {len(self.iso_index)} files")
            if hasattr(self, "iso_ccsf_index_status") and str(p) == str(self._iso_ccsf_index_path()):
                self.iso_ccsf_index_status.set(f"Index: loaded {len(self.iso_index)} files from {p}")
            self._console_write(f"[ISO] Loaded index: {len(self.iso_index)} files\n")
            self.console.see("end")
        except Exception as e:
            return messagebox.showerror("ISO index error", str(e))

    def resolve_iso_from_selection(self):
        if self.iso_index is None:
            self.load_iso_index()
            if self.iso_index is None:
                return
        res = self.resolve_selected()
        if not res or res[0] != "sec":
            return messagebox.showerror("Select section", "Select a SECTION first (e.g., town.bin → CCSFtown04).")
        _, _f, s = res
        raw_paths = s.get("asset_paths_sample") if isinstance(s.get("asset_paths_sample"), list) else []
        if not raw_paths:
            return messagebox.showinfo("No paths", "This section has no recorded asset path samples.")

        normed = []
        for pth in raw_paths:
            np = self._norm_iso_path(pth)
            if np and np not in normed:
                normed.append(np)

        self.iso_rows = []
        for np in normed:
            hit = self.iso_index.get(np) if self.iso_index else None
            self.iso_rows.append({"path": np, "found": bool(hit), "size": (hit.get("size",0) if hit else 0)})

        self.iso_tree.delete(*self.iso_tree.get_children())
        for r in self.iso_rows:
            self.iso_tree.insert("", "end", values=("YES" if r["found"] else "NO", r["size"], r["path"]))
        found = sum(1 for r in self.iso_rows if r["found"])
        self.iso_status.set(f"Resolved {found}/{len(self.iso_rows)} sample paths")
        self._console_write(f"[ISO] Resolved {found}/{len(self.iso_rows)} referenced sample paths\n")
        self.console.see("end")

    def _iso_output_path(self, internal_path: str) -> Path:
        base = Path(self.iso_extract_dir.get().strip() or str(ROOT / "iso_extract"))
        rel = Path(*internal_path.split("/"))
        out = base / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        return out

    def extract_iso_selected(self):
        if self.iso_index is None:
            self.load_iso_index()
            if self.iso_index is None:
                return
        sel = self.iso_tree.selection()
        if not sel:
            return messagebox.showerror("Select", "Select a row first.")
        vals = self.iso_tree.item(sel[0], "values")
        if not vals or vals[0] != "YES":
            return messagebox.showerror("Not found", "That path was not found in the ISO index.")
        internal = vals[2]
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your ISO first.")
        out = self._iso_output_path(internal)
        cmd = [PY, str(TOOLS / "iso_extract.py"), iso, internal, "--out", str(out)]
        self.iso_status.set("Single-file extraction queued. Stop/Cancel is available while running.")
        self._run_task(cmd)

    def extract_iso_all_found(self):
        if self.iso_index is None:
            self.load_iso_index()
            if self.iso_index is None:
                return
        iso = self.iso_path.get().strip()
        if not iso:
            return messagebox.showerror("Missing", "Pick your ISO first.")
        found = [r for r in self.iso_rows if r.get("found")]
        if not found:
            return messagebox.showinfo("None found", "No referenced sample paths were found.")
        paths = [r["path"] for r in found if r.get("path")]
        sizes = [int(r.get("size", 0) or 0) for r in found if r.get("path")]
        if not self._confirm_batch_extraction(paths, sizes, "Resolved hits batch extraction"):
            return
        self.iso_status.set(
            f"Batch extraction queued ({len(paths)} files, est {sum(sizes):,} bytes). Stop/Cancel is available."
        )
        self._run_extract_queue(iso, paths, label="iso extract resolved hits")

    def _run_extract_queue(self, iso: str, paths: list[str], label: str = "iso extract queue"):
        if not paths:
            return
        remaining = list(paths)

        def _next(_rc: int = 0):
            if not remaining:
                self.iso_status.set(f"Done extracting {len(paths)} file(s).")
                return
            pth = remaining.pop(0)
            done = len(paths) - len(remaining)
            self.iso_status.set(
                f"Batch extraction running ({done}/{len(paths)}): {pth} | Stop/Cancel is available."
            )
            out = self._iso_output_path(pth)
            cmd = [PY, str(TOOLS / "iso_extract.py"), iso, pth, "--out", str(out)]
            self._run_task(cmd, on_done=_next, label=label)

        _next(0)



if __name__ == "__main__":
    FragmenterApp().mainloop()

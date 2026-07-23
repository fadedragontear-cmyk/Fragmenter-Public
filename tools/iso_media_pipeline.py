#!/usr/bin/env python3
"""ISO media inventory/extract/decode pipeline.

This orchestrates the conservative ISO helpers into a workspace layout intended
for media-oriented review:

* ``media_pipeline/extracted`` for copied/extracted source candidates
* ``media_pipeline/decoded`` for decoder diagnostics/artifacts
* ``media_pipeline/reports`` plus mirrored summaries in ``reports``

The pipeline is deliberately conservative.  It does not write to or reuse the
legacy ``workspace/extracted_ccs`` location unless the caller explicitly points
``--workspace`` at a directory whose media pipeline extraction target resolves
there.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660  # noqa: E402
import iso_asset_survey  # noqa: E402
import iso_ccsf_extractor  # noqa: E402
import ccsf_structure_decoder  # noqa: E402
import ccsf_model_decoder  # noqa: E402
import preview_texture  # noqa: E402
import audio_decoder  # noqa: E402
import scei_hd_bd  # noqa: E402

DEFAULT_MAX_READ_BYTES = 8 * 1024 * 1024
DEFAULT_EMBEDDED_READ_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_EMBEDDED_PER_FILE = 50
DEFAULT_MAX_OUTPUT_MB = 1024
EXPLICIT_AUDIO_ISO_PATHS = ("netgui/eff.hd", "netgui/eff.bd", "data/snddata.bin", "voice/bgm.bin", "voice/food.bin")
TEXTURE_EXTENSIONS = {".tim", ".tm2", ".tim2", ".tex", ".clt", ".png", ".bmp", ".jpg", ".jpeg"}
TEXTURE_HINT_RE = re.compile(r"(?i)(?:\b(?:TEX_|CLT_)[A-Z0-9_./\\-]*|[A-Z0-9_./\\-]*(?:texture|tex|clut|palette|pal|bitmap|\.tim2?|\.tm2|\.png|\.bmp|\.jpe?g)[A-Z0-9_./\\-]*)")

DEFAULT_BUCKETS = {
    "audio_or_music_candidate",
    "texture_palette_bundle",
    "ccsf_model_bundle",
    "movie_or_stream_candidate",
    "unknown_container",
}

EXTRACTED_EMBEDDED_DIRS = {
    "audio_or_music_candidate": "audio",
    "texture_palette_bundle": "textures",
    "ccsf_model_bundle": "ccsf",
    "movie_or_stream_candidate": "movies",
    "dialogue_or_text_candidate": "text",
    "unknown_container": "unknown",
    "unknown_binary": "unknown",
}

REQUIRED_OUTPUT_DIRS = (
    ("extracted", "top_level"),
    ("extracted", "embedded", "audio"),
    ("extracted", "embedded", "textures"),
    ("extracted", "embedded", "ccsf"),
    ("extracted", "embedded", "movies"),
    ("extracted", "embedded", "text"),
    ("extracted", "embedded", "unknown"),
    ("decoded", "audio", "wav"),
    ("decoded", "audio", "raw"),
    ("decoded", "audio", "failed"),
    ("decoded", "textures", "png"),
    ("decoded", "textures", "raw"),
    ("decoded", "textures", "failed"),
    ("decoded", "models", "obj"),
    ("decoded", "models", "raw"),
    ("decoded", "models", "failed"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_rel(path: str) -> Path:
    """Return a relative, traversal-free path for ISO paths or embedded names."""
    parts = []
    for part in PurePosixPath(str(path).replace("\\", "/")).parts:
        if part in ("", ".", "..", "/") or part.endswith(":"):
            continue
        cleaned = "".join(ch if ch not in "<>:\"|?*" and ord(ch) >= 32 else "_" for ch in part)
        if cleaned:
            parts.append(cleaned)
    return Path(*parts) if parts else Path("unnamed.bin")


def safe_output_path(root: Path, *parts: str | Path) -> Path:
    """Join path parts under root and reject paths that would escape it."""
    root_resolved = root.resolve()
    out = root.joinpath(*(safe_rel(str(p)) for p in parts)).resolve()
    if out != root_resolved and root_resolved not in out.parents:
        raise ValueError(f"unsafe output path escaped workspace: {out}")
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dirs(workspace: Path) -> dict[str, Path]:
    root = workspace / "media_pipeline"
    return {
        "root": root,
        "extracted": root / "extracted",
        "decoded": root / "decoded",
        "reports": root / "reports",
        "mirror_reports": workspace / "reports",
    }


def ensure_dirs(paths: dict[str, Path]) -> None:
    for key in ("extracted", "decoded", "reports", "mirror_reports"):
        paths[key].mkdir(parents=True, exist_ok=True)
    for rel in REQUIRED_OUTPUT_DIRS:
        (paths["root"].joinpath(*rel)).mkdir(parents=True, exist_ok=True)


def mirror_report(src: Path, mirror_dir: Path) -> Path:
    mirror_dir.mkdir(parents=True, exist_ok=True)
    dst = mirror_dir / src.name
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    return dst


def write_json_report(report: dict[str, Any], paths: dict[str, Path], name: str) -> Path:
    out = paths["reports"] / name
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mirror_report(out, paths["mirror_reports"])
    return out



def manifest_path(paths: dict[str, Path]) -> Path:
    return paths["reports"] / "container_scan_manifest.json"

def iso_identity(iso_path: str | Path) -> dict[str, Any]:
    p = Path(iso_path)
    try:
        st = p.stat()
        return {"path": str(p), "resolved_path": str(p.expanduser().resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    except OSError:
        return {"path": str(p), "resolved_path": str(p)}

def load_container_scan_manifest(paths: dict[str, Path], iso_path: str | Path | None = None) -> dict[str, Any]:
    out = manifest_path(paths)
    if out.is_file():
        try:
            payload = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    else:
        payload = {}
    if not isinstance(payload, dict) or payload.get("schema") != "fragmenter.container_scan_manifest.v1":
        payload = {"schema": "fragmenter.container_scan_manifest.v1", "created_at": utc_now(), "iso_identity": iso_identity(iso_path) if iso_path else None, "entries": {}}
    payload.setdefault("entries", {})
    return payload

def write_container_scan_manifest(manifest: dict[str, Any], paths: dict[str, Path]) -> Path:
    manifest["updated_at"] = utc_now()
    out = manifest_path(paths)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mirror_report(out, paths["mirror_reports"])
    return out

def cache_key(iso_path: str | Path, internal: str, lba: Any, size: Any, sha256: str | None = None, *, offset: Any = None) -> str:
    parts = [str(iso_identity(iso_path).get("resolved_path") or iso_path), _fold_iso_path(internal), str(lba if lba is not None else ""), str(size if size is not None else "")]
    if offset is not None:
        parts.append(f"off={offset}")
    if sha256:
        parts.append(f"sha256={sha256}")
    return hashlib.sha256("|".join(parts).encode("utf-8", "surrogateescape")).hexdigest()

def scan_evidence(path: str, data: bytes, row: dict[str, Any] | None = None) -> dict[str, Any]:
    nearby = iso_asset_survey.nearby_strings(data)
    signatures = iso_asset_survey.scan_embedded_signatures(data, min(len(data), DEFAULT_EMBEDDED_READ_BYTES), DEFAULT_MAX_EMBEDDED_PER_FILE)
    return {
        "gzip": [{k: v for k, v in h.items() if k != "sample"} for h in signatures if h.get("signature") == "gzip"],
        "ccsf": bool(b"CCSF" in data),
        "scei": {"present": data.startswith(scei_hd_bd.MAGIC), "signature_hex": data[:16].hex()} if data.startswith(scei_hd_bd.MAGIC) else None,
        "vag_vab": [{k: v for k, v in h.items() if k != "sample"} for h in signatures if h.get("signature") in {"VAGp", "IECSsreV"}],
        "riff_wave": scan_embedded_waves(data),
        "mpeg_audio": [{k: v for k, v in r.items() if k != "frames"} for r in scan_validated_mpeg_audio_regions(data)],
        "tim_tim2": texture_candidate_info(path, data, nearby) if (data.startswith(b"TIM2") or data[:4] == b"\x10\x00\x00\x00" or PurePosixPath(path).suffix.lower() in {".tim", ".tm2", ".tim2"}) else None,
        "images": image_header_info(data) or ({"format":"gif","decode_status":"pass-through"} if data.startswith((b"GIF87a", b"GIF89a")) else {"format":"pnm","decode_status":"pass-through"} if re.match(br"P[1-6]\s", data[:8]) else None),
        "text_hints": nearby[:20],
        "unknown_region": str((row or {}).get("bucket") or "").startswith("unknown"),
    }


def inventory_report_paths(paths: dict[str, Path]) -> list[Path]:
    return [
        paths["reports"] / "iso_media_inventory.json",
        paths["mirror_reports"] / "iso_media_inventory.json",
    ]


def _same_iso_path(stored: Any, selected: Any) -> bool:
    if not stored or not selected:
        return False
    stored_text = str(stored)
    selected_text = str(selected)
    if stored_text == selected_text:
        return True
    try:
        return Path(stored_text).expanduser().resolve() == Path(selected_text).expanduser().resolve()
    except OSError:
        return False


def inventory_schema_readable(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("summary"), dict)
        and isinstance(payload.get("candidates"), list)
    )


def load_existing_inventory(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any] | None:
    if getattr(args, "rescan_inventory", False):
        return None
    for report_path in inventory_report_paths(paths):
        if not report_path.is_file():
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if inventory_schema_readable(payload) and _same_iso_path(payload.get("iso_path"), getattr(args, "iso_path", None)):
            return payload
    return None


def inventory_entries(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for raw in inventory.get("candidates", []) or []:
        if not isinstance(raw, dict):
            continue
        row = iso_asset_survey.normalize_candidate_row(raw)
        if row.get("source") != "top_level":
            continue
        path = str(row.get("path") or row.get("iso_path") or "")
        if not path or path in entries:
            continue
        entries[path] = {
            "path": path,
            "size": int(row.get("size") or 0),
            "lba": row.get("lba"),
            "is_dir": False,
        }
    return entries


PROGRESS_EVENT_FIELDS = {
    "stage",
    "current_path",
    "current_index",
    "total",
    "candidates_found",
    "extracted_count",
    "banks_found",
    "streams_found",
    "decoded_wavs",
    "raw_pending",
    "failures",
}


def _json_scalar(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def emit_progress(args: argparse.Namespace, stage: str, **fields: Any) -> None:
    """Append one compact JSON progress event, if --progress-jsonl is enabled."""
    progress_path = getattr(args, "progress_jsonl", None)
    if not progress_path:
        return
    event = {"stage": stage}
    for key, value in fields.items():
        if key in PROGRESS_EVENT_FIELDS and value is not None:
            event[key] = _json_scalar(value)
    out = Path(progress_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def image_header_info(data: bytes) -> dict[str, Any] | None:
    """Return cheap metadata for real pass-through image headers."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return {"format": "png", "dimensions": [int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")], "decode_status": "pass-through"}
    if data.startswith(b"BM") and len(data) >= 26:
        return {"format": "bmp", "dimensions": [int.from_bytes(data[18:22], "little", signed=True), abs(int.from_bytes(data[22:26], "little", signed=True))], "decode_status": "pass-through"}
    if data.startswith(b"\xff\xd8\xff"):
        dims = jpeg_dimensions(data)
        return {"format": "jpeg", "dimensions": list(dims) if dims else None, "decode_status": "pass-through"}
    return None


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while i + 9 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            return None
        marker = data[i]
        i += 1
        if marker in {0xD8, 0xD9}:
            continue
        if i + 2 > len(data):
            return None
        seg_len = int.from_bytes(data[i:i + 2], "big")
        if seg_len < 2 or i + seg_len > len(data):
            return None
        if marker in sof and seg_len >= 7:
            return int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 3:i + 5], "big")
        i += seg_len
    return None


def tim_header_info(data: bytes, ext: str) -> dict[str, Any] | None:
    if data.startswith(b"TIM2"):
        return {"format": "tim2", "decode_status": "decode pending", "palette_hints": ["TIM2/PS2 texture candidate; palette/CLUT may be embedded"]}
    if data[:4] == b"\x10\x00\x00\x00" or ext == ".tim":
        flags = int.from_bytes(data[4:8], "little") if len(data) >= 8 else None
        hints = ["PlayStation TIM texture candidate"]
        if flags is not None and (flags & 0x8):
            hints.append("TIM CLUT/palette flag present")
        return {"format": "tim", "decode_status": "decode pending", "palette_hints": hints}
    if ext in {".tm2", ".tim2"}:
        return {"format": "tim2", "decode_status": "decode pending", "palette_hints": ["TIM2/PS2 texture candidate by extension"]}
    return None


def texture_string_hints(path: str, nearby: list[str]) -> list[str]:
    hints: list[str] = []
    for value in [path, *nearby]:
        for match in TEXTURE_HINT_RE.findall(value or ""):
            cleaned = match.strip(". ,;:\t\r\n")
            if cleaned and cleaned not in hints:
                hints.append(cleaned)
                if len(hints) >= 20:
                    return hints
    return hints


def texture_candidate_info(path: str, data: bytes, nearby: list[str]) -> dict[str, Any] | None:
    ext = PurePosixPath(path.replace("\\", "/")).suffix.lower()
    image = image_header_info(data)
    tim = tim_header_info(data, ext)
    hints = texture_string_hints(path, nearby)
    reasons: list[str] = []
    info = image or tim
    if ext in TEXTURE_EXTENSIONS:
        reasons.append(f"texture extension {ext}")
    if image:
        reasons.append(f"real {image['format'].upper()} header")
    if tim:
        reasons.append(f"{tim['format'].upper()} candidate by magic/extension")
    if any(h.startswith(("TEX_", "CLT_")) for h in hints):
        reasons.append("TEX_/CLT_ hint")
    elif hints:
        reasons.append("texture-like path/name/string hint")
    if not reasons:
        return None
    out = {"format": (info or {}).get("format", "unknown"), "dimensions": (info or {}).get("dimensions"), "decode_status": (info or {}).get("decode_status", "candidate only"), "palette_hints": (info or {}).get("palette_hints", []), "texture_hints": hints, "reasons": reasons}
    if out["format"] == "unknown" and any("palette" in h.lower() or h.startswith("CLT_") for h in hints):
        out["palette_hints"] = ["palette/CLT string hint present"]
    return out


def scan_embedded_waves(data: bytes) -> list[dict[str, Any]]:
    """Return validated embedded RIFF/WAVE ranges found anywhere in *data*."""
    rows: list[dict[str, Any]] = []
    pos = 0
    while True:
        offset = data.find(b"RIFF", pos)
        if offset < 0:
            break
        pos = offset + 4
        if offset + 12 > len(data):
            continue
        riff_size = int.from_bytes(data[offset + 4:offset + 8], "little")
        end = offset + 8 + riff_size
        if riff_size < 4 or end > len(data) or data[offset + 8:offset + 12] != b"WAVE":
            continue
        limit = end
        chunk_pos = offset + 12
        fmt: dict[str, Any] | None = None
        data_chunk: dict[str, int] | None = None
        valid = True
        while chunk_pos + 8 <= limit:
            chunk_id = data[chunk_pos:chunk_pos + 4]
            chunk_size = int.from_bytes(data[chunk_pos + 4:chunk_pos + 8], "little")
            chunk_start = chunk_pos + 8
            chunk_end = chunk_start + chunk_size
            if chunk_end > limit:
                valid = False
                break
            if chunk_id == b"fmt ":
                if chunk_size < 16:
                    valid = False
                    break
                audio_format = int.from_bytes(data[chunk_start:chunk_start + 2], "little")
                channels = int.from_bytes(data[chunk_start + 2:chunk_start + 4], "little")
                sample_rate = int.from_bytes(data[chunk_start + 4:chunk_start + 8], "little")
                byte_rate = int.from_bytes(data[chunk_start + 8:chunk_start + 12], "little")
                block_align = int.from_bytes(data[chunk_start + 12:chunk_start + 14], "little")
                bits_per_sample = int.from_bytes(data[chunk_start + 14:chunk_start + 16], "little")
                bytes_per_sample = max(1, (bits_per_sample + 7) // 8)
                expected_align = channels * bytes_per_sample
                if (audio_format not in {1, 3, 0xFFFE} or channels < 1 or channels > 8 or sample_rate < 8000
                        or sample_rate > 192000 or bits_per_sample not in {8, 16, 24, 32}
                        or block_align != expected_align or byte_rate != sample_rate * block_align):
                    valid = False
                    break
                fmt = {
                    "audio_format": audio_format,
                    "channels": channels,
                    "sample_rate": sample_rate,
                    "byte_rate": byte_rate,
                    "block_align": block_align,
                    "bits_per_sample": bits_per_sample,
                }
            elif chunk_id == b"data":
                if chunk_size <= 0:
                    valid = False
                    break
                data_chunk = {"data_offset": chunk_start - offset, "data_size": chunk_size}
            chunk_pos = chunk_end + (chunk_size & 1)
        if not (valid and fmt and data_chunk):
            continue
        rows.append({
            "offset": offset,
            "end_offset": end,
            "size": end - offset,
            "riff_size": riff_size,
            "duration_estimate": data_chunk["data_size"] / fmt["byte_rate"] if fmt.get("byte_rate") else None,
            **fmt,
            **data_chunk,
        })
    return rows



_MPEG_VERSIONS = {0b00: "2.5", 0b10: "2", 0b11: "1"}
_MPEG_LAYERS = {0b01: "III", 0b10: "II", 0b11: "I"}
_MPEG_SAMPLE_RATES = {
    "1": (44100, 48000, 32000),
    "2": (22050, 24000, 16000),
    "2.5": (11025, 12000, 8000),
}
_MPEG_BITRATES = {
    ("1", "I"): (0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448),
    ("1", "II"): (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384),
    ("1", "III"): (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
    ("2", "I"): (0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256),
    ("2", "II"): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
    ("2", "III"): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
    ("2.5", "I"): (0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256),
    ("2.5", "II"): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
    ("2.5", "III"): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
}
_MPEG_CHANNEL_MODES = {0b00: "stereo", 0b01: "joint_stereo", 0b10: "dual_channel", 0b11: "mono"}


def _mpeg_audio_frame_header(data: bytes, offset: int) -> dict[str, Any] | None:
    if offset + 4 > len(data):
        return None
    header = int.from_bytes(data[offset:offset + 4], "big")
    if (header >> 21) & 0x7FF != 0x7FF:
        return None
    version = _MPEG_VERSIONS.get((header >> 19) & 0x3)
    layer = _MPEG_LAYERS.get((header >> 17) & 0x3)
    bitrate_index = (header >> 12) & 0xF
    sample_index = (header >> 10) & 0x3
    padding = (header >> 9) & 0x1
    channel_mode_bits = (header >> 6) & 0x3
    if not version or not layer or bitrate_index in {0, 0xF} or sample_index == 0x3:
        return None
    sample_rate = _MPEG_SAMPLE_RATES[version][sample_index]
    bitrate_kbps = _MPEG_BITRATES[(version, layer)][bitrate_index]
    if bitrate_kbps <= 0:
        return None
    bitrate = bitrate_kbps * 1000
    if layer == "I":
        frame_length = ((12 * bitrate // sample_rate) + padding) * 4
    elif layer == "III" and version != "1":
        frame_length = 72 * bitrate // sample_rate + padding
    else:
        frame_length = 144 * bitrate // sample_rate + padding
    if frame_length < 4 or offset + frame_length > len(data):
        return None
    channel_mode = _MPEG_CHANNEL_MODES[channel_mode_bits]
    return {
        "offset": offset,
        "end_offset": offset + frame_length,
        "frame_length": frame_length,
        "version": version,
        "layer": layer,
        "sample_rate": sample_rate,
        "channel_mode": channel_mode,
        "channels": 1 if channel_mode == "mono" else 2,
        "bitrate_kbps": bitrate_kbps,
    }


def scan_validated_mpeg_audio_regions(data: bytes, *, min_frames: int = 2) -> list[dict[str, Any]]:
    """Return bounded MPEG audio frame chains validated by consecutive headers."""
    rows: list[dict[str, Any]] = []
    pos = 0
    while pos + 4 <= len(data):
        sync = data.find(b"\xff", pos)
        if sync < 0 or sync + 4 > len(data):
            break
        first = _mpeg_audio_frame_header(data, sync)
        if not first:
            pos = sync + 1
            continue
        chain = [first]
        cursor = int(first["end_offset"])
        consistent = (first["version"], first["layer"], first["sample_rate"], first["channel_mode"])
        while cursor + 4 <= len(data):
            nxt = _mpeg_audio_frame_header(data, cursor)
            if not nxt:
                break
            if (nxt["version"], nxt["layer"], nxt["sample_rate"], nxt["channel_mode"]) != consistent:
                break
            chain.append(nxt)
            cursor = int(nxt["end_offset"])
        if len(chain) >= min_frames:
            rows.append({
                "offset": first["offset"],
                "end_offset": chain[-1]["end_offset"],
                "size": int(chain[-1]["end_offset"]) - int(first["offset"]),
                "frame_count": len(chain),
                "version": first["version"],
                "layer": first["layer"],
                "sample_rate": first["sample_rate"],
                "channel_mode": first["channel_mode"],
                "channels": first["channels"],
                "first_bitrate_kbps": first["bitrate_kbps"],
                "duration_estimate": sum(384 if first["layer"] == "I" else 1152 if first["version"] == "1" or first["layer"] == "II" else 576 for _ in chain) / first["sample_rate"],
                "validation_status": "validated_mpeg_audio_region",
                "frames": chain,
            })
            pos = int(chain[-1]["end_offset"])
        else:
            pos = sync + 1
    return rows


def extract_embedded_waves(path: Path, source_iso_path: str, out_dir: Path) -> list[dict[str, Any]]:
    data = path.read_bytes()
    rows = []
    for index, wav in enumerate(scan_embedded_waves(data)):
        stem = safe_rel(source_iso_path).as_posix().replace("/", "__")
        out = safe_output_path(out_dir, f"{stem}__0x{int(wav['offset']):X}.wav")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data[int(wav["offset"]):int(wav["end_offset"])])
        rows.append({
            "source_candidate": str(path),
            "source_iso_path": source_iso_path,
            "offset": wav["offset"],
            "end_offset": wav["end_offset"],
            "source_region_offset": wav["offset"],
            "source_region_end_offset": wav["end_offset"],
            "source_region_size": wav["size"],
            "embedded_index": index,
            "detected_format": "embedded_wav",
            "decode_status": "extracted_embedded_wav",
            "output_path": str(out),
            "sample_rate": wav["sample_rate"],
            "channels": wav["channels"],
            "duration_estimate": wav["duration_estimate"],
            "bits_per_sample": wav["bits_per_sample"],
            "block_align": wav["block_align"],
            "audio_purpose": audio_decoder.classify_audio_purpose(source_iso_path),
        })
    return rows



def extract_validated_mpeg_audio_regions(path: Path, source_iso_path: str, out_dir: Path) -> list[dict[str, Any]]:
    data = path.read_bytes()
    rows = []
    for index, region in enumerate(scan_validated_mpeg_audio_regions(data)):
        stem = safe_rel(source_iso_path).as_posix().replace("/", "__")
        suffix = ".mp3" if region["layer"] == "III" else ".mpa"
        out = safe_output_path(out_dir, f"{stem}__0x{int(region['offset']):X}{suffix}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data[int(region["offset"]):int(region["end_offset"])])
        rows.append({
            "source_candidate": str(path),
            "source_iso_path": source_iso_path,
            "offset": region["offset"],
            "end_offset": region["end_offset"],
            "source_region_offset": region["offset"],
            "source_region_end_offset": region["end_offset"],
            "source_region_size": region["size"],
            "embedded_index": index,
            "detected_format": "mpeg_audio",
            "decode_status": "extracted_validated_mpeg_audio_region",
            "validation_status": "validated_mpeg_audio_region",
            "output_path": str(out),
            "frame_count": region["frame_count"],
            "mpeg_version": region["version"],
            "mpeg_layer": region["layer"],
            "sample_rate": region["sample_rate"],
            "channels": region["channels"],
            "channel_mode": region["channel_mode"],
            "duration_estimate": region["duration_estimate"],
            "audio_purpose": audio_decoder.classify_audio_purpose(source_iso_path),
        })
    return rows


def read_first_bytes_hex(data: bytes, limit: int = 32) -> str:
    return data[:limit].hex()


def recommended_action(row: dict[str, Any]) -> str:
    if row.get("suggested_next_action"):
        return str(row["suggested_next_action"])
    bucket = str(row.get("bucket") or "")
    source = str(row.get("source") or "")
    if source == "embedded":
        return "extract embedded candidate" if bucket != "unknown_binary" else "inspect nearby container bytes"
    if bucket == "audio_or_music_candidate":
        return "extract and run audio decoder"
    if bucket == "texture_palette_bundle":
        return "extract and inspect texture metadata/preview"
    if bucket in {"ccsf_model_bundle", "character_model_bundle", "environment_bundle", "animation_bundle"}:
        return "extract and run model/bundle decoder"
    if bucket == "movie_or_stream_candidate":
        return "extract raw stream for external media inspection"
    if bucket.startswith("unknown"):
        return "inspect strings/signatures and preserve raw dump"
    return "review candidate"


def rel_link(target: str | Path | None, from_dir: Path) -> str | None:
    if not target:
        return None
    target_path = Path(target)
    try:
        if target_path.is_absolute() or target_path.exists():
            return Path(os.path.relpath(target_path.resolve(), from_dir.resolve())).as_posix()
    except Exception:
        pass
    return str(target)


def limited_rows(rows: list[dict[str, Any]], limit: int = 1000) -> tuple[list[dict[str, Any]], int]:
    return rows[:limit], max(0, len(rows) - limit)


def write_text_report(title: str, report: dict[str, Any], rows: list[dict[str, Any]], out: Path) -> None:
    lines = [title, "=" * len(title), f"Generated: {report.get('created_at')}", f"ISO: {report.get('iso_path')}", ""]
    summary = report.get("summary") or {}
    if summary:
        lines.append("Summary:")
        for key, value in summary.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
    explicit_audio = report.get("explicit_audio_path_summary") or {}
    if explicit_audio:
        lines.append("Explicit audio path summary:")
        for path, info in explicit_audio.items():
            lines.append(f"  {path}: {info}")
        lines.append("")
    sections = report.get("sections") or []
    if sections:
        lines.append("Sections:")
        for section in sections:
            lines.append(f"  {section.get('title')}: {section.get('count', 0)}")
            if section.get("reason"):
                lines.append(f"    reason: {section.get('reason')}")
        lines.append("")
    for i, r in enumerate(rows, 1):
        loc = r.get("iso_path") or r.get("parent_iso_path") or r.get("source_iso_path") or r.get("path") or r.get("source_candidate")
        if r.get("offset") is not None:
            loc = f"{loc} @0x{int(r['offset']):X}"
        lines.append(f"{i}. [{r.get('bucket') or r.get('guessed_type')}] {loc}")
        for key in ("size", "lba", "extension", "first_bytes_hex", "sha256", "reasons", "sample_strings", "printable_density", "embedded_candidate_count", "recommended_action", "signature", "estimated_size", "format", "dimensions", "palette_hints", "nearby_names_strings", "extracted_path", "nearby_strings", "suggested_action", "decode_status", "output_path", "raw_path", "duration_estimate", "sample_rate", "channels", "audio_purpose", "warnings", "errors"):
            if r.get(key) not in (None, "", []):
                value = "; ".join(map(str, r[key])) if isinstance(r[key], list) else r[key]
                lines.append(f"   {key}: {value}")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def write_dashboard(title: str, report_files: list[str], rows: list[dict[str, Any]], out: Path, reports_dir: Path) -> None:
    shown, omitted = limited_rows(rows)
    links = "".join(f"<li><a href='{html.escape(name)}'>{html.escape(name)}</a></li>" for name in report_files)
    keys = ["bucket", "iso_path", "source_iso_path", "parent_iso_path", "offset", "size", "lba", "extension", "format", "dimensions", "palette_hints", "signature", "sha256", "extracted_path", "output_path", "raw_path", "decode_status", "duration_estimate", "sample_rate", "channels", "audio_purpose", "warnings", "errors", "recommended_action", "suggested_action", "reasons"]
    header = "".join(f"<th>{html.escape(k)}</th>" for k in keys)
    body = []
    for r in shown:
        cells = []
        for k in keys:
            v = r.get(k)
            if k in {"extracted_path", "output_path", "raw_path"} and v:
                href = rel_link(v, reports_dir)
                text = Path(str(v)).name
                cells.append(f"<td><a href='{html.escape(href or str(v))}'>{html.escape(text)}</a></td>")
            else:
                if isinstance(v, list):
                    v = "; ".join(map(str, v[:6]))
                cells.append(f"<td>{html.escape('' if v is None else str(v))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    doc = f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title><style>body{{font-family:sans-serif}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:4px;vertical-align:top}}th{{background:#eee}}</style><h1>{html.escape(title)}</h1><ul>{links}</ul><p>Showing {len(shown)} of {len(rows)} rows; omitted {omitted}. Links are relative to this reports directory.</p><table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"
    out.write_text(doc, encoding="utf-8")


CONFIRMED_PLAYABLE_AUDIO_STATUSES = {
    "copied_validated_wav",
    "decoded_ps_adpcm_to_pcm_wav",
    "decoded_vagp_to_pcm_wav",
}

EXPERIMENTAL_SEQUENCE_RENDER_STATUS = "experimental_sequence_render"
RAW_INTERPRETATION_PREVIEW_STATUS = "raw_interpretation_preview"


def audio_decode_section_label(row: dict[str, Any]) -> str:
    explicit = row.get("report_section")
    if explicit:
        return str(explicit)
    status = str(row.get("decode_status") or "")
    fmt = str(row.get("detected_format") or row.get("format") or row.get("guessed_type") or "")
    if row.get("errors") or "fail" in status or "invalid" in fmt:
        return "Failures"
    if status == EXPERIMENTAL_SEQUENCE_RENDER_STATUS:
        return "Experimental sequence renders"
    if status == RAW_INTERPRETATION_PREVIEW_STATUS:
        return "Raw interpretation previews"
    if status in CONFIRMED_PLAYABLE_AUDIO_STATUSES and not row.get("errors"):
        return "Decoded playable audio"
    if fmt == "scei_ps_adpcm_bank_stream":
        return "Bank streams"
    if fmt == "scei_sound_bank" or fmt == "vab_sound_bank" or "sound_bank" in status:
        return "Sony HD/BD banks"
    if row.get("output_path") and status not in {"planned", "pending", EXPERIMENTAL_SEQUENCE_RENDER_STATUS, RAW_INTERPRETATION_PREVIEW_STATUS}:
        return "Decoded playable audio"
    if fmt == "gzip" or row.get("gzip_eof") is not None:
        return "Valid gzip members"
    return "Unknown audio containers"


def write_audio_decode_dashboard(title: str, report_files: list[str], rows: list[dict[str, Any]], out: Path, reports_dir: Path, report: dict[str, Any] | None = None) -> None:
    labels = [
        "Decoded playable audio",
        "Sony HD/BD banks",
        "Bank streams",
        "Valid gzip members",
        "Rejected gzip magic matches",
        "Experimental sequence renders",
        "Raw interpretation previews",
        "Unknown audio containers",
        "Failures",
    ]
    keys = ["source_iso_path", "offset", "detected_format", "decode_status", "duration_estimate", "sample_rate", "channels", "audio_purpose", "raw_path", "output_path", "warnings", "errors", "next_action"]
    links = "".join(f"<li><a href='{html.escape(name)}'>{html.escape(name)}</a></li>" for name in report_files)
    summary_items = ""
    if report and report.get("summary"):
        summary_items = "".join(f"<li><b>{html.escape(str(k))}</b>: {html.escape(str(v))}</li>" for k, v in report["summary"].items())
        summary_items = f"<h2>Summary</h2><ul>{summary_items}</ul>"
    explicit_items = ""
    if report and report.get("explicit_audio_path_summary"):
        items = "".join(f"<li><b>{html.escape(str(k))}</b>: {html.escape(str(v))}</li>" for k, v in report["explicit_audio_path_summary"].items())
        explicit_items = f"<h2>Explicit audio path summary</h2><ul>{items}</ul>"
    sections = []
    for label in labels:
        grouped = [r for r in rows if audio_decode_section_label(r) == label]
        header = "".join(f"<th>{html.escape(k)}</th>" for k in keys)
        body = []
        for r in grouped:
            cells = []
            for k in keys:
                v = r.get(k)
                if k in {"output_path", "raw_path"} and v:
                    href = rel_link(v, reports_dir)
                    cells.append(f"<td><a href='{html.escape(href or str(v))}'>{html.escape(Path(str(v)).name)}</a></td>")
                else:
                    if isinstance(v, list):
                        v = "; ".join(map(str, v))
                    cells.append(f"<td>{html.escape('' if v is None else str(v))}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        sections.append(f"<h2>{html.escape(label)} ({len(grouped)})</h2><table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>")
    doc = f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title><style>body{{font-family:sans-serif}}table{{border-collapse:collapse;width:100%;margin-bottom:1rem}}td,th{{border:1px solid #ccc;padding:4px;vertical-align:top}}th{{background:#eee}}</style><h1>{html.escape(title)}</h1><ul>{links}</ul>{summary_items}{explicit_items}{''.join(sections)}"
    out.write_text(doc, encoding="utf-8")


def inventory_rows(inventory: dict[str, Any], extraction: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    extracted_by_iso = {r.get("source_iso_path"): r for r in (extraction or {}).get("files", []) if r.get("status") == "extracted"}
    top_rows: list[dict[str, Any]] = []
    embedded_rows: list[dict[str, Any]] = []
    for r in inventory.get("candidates", []):
        if r.get("source") == "embedded":
            embedded_rows.append({
                "parent_iso_path": r.get("parent_iso_path") or r.get("path"),
                "offset": r.get("offset"),
                "signature": r.get("signature") or r.get("magic_signature") or "; ".join((r.get("reasons") or [])[:1]),
                "guessed_type": r.get("guessed_type") or r.get("bucket"),
                "bucket": r.get("bucket"),
                "estimated_size": r.get("estimated_size") or r.get("size"),
                "extracted_path": r.get("extracted_path"),
                "nearby_strings": r.get("nearby_strings") or r.get("sample_strings"),
                "suggested_action": r.get("suggested_action") or recommended_action(r),
            })
            continue
        out = extracted_by_iso.get(r.get("path")) or {}
        top_rows.append({
            "iso_path": r.get("iso_path") or r.get("path"),
            "size": r.get("size"),
            "lba": r.get("lba"),
            "extension": r.get("extension"),
            "first_bytes_hex": r.get("first_bytes_hex"),
            "sha256": r.get("sha256") or out.get("sha256"),
            "bucket": r.get("bucket"),
            "reasons": r.get("reasons"),
            "sample_strings": r.get("sample_strings"),
            "printable_density": r.get("printable_density"),
            "embedded_candidate_count": r.get("embedded_candidate_count", 0),
            "recommended_action": r.get("recommended_action") or recommended_action(r),
            "extracted_path": out.get("output_path"),
        })
    return top_rows, embedded_rows


def write_inventory_suite(name: str, title: str, report: dict[str, Any], rows: list[dict[str, Any]], paths: dict[str, Path], *, dashboard: bool = True) -> None:
    json_path = write_json_report(report | {"rows": rows}, paths, f"{name}.json")
    txt_path = paths["reports"] / f"{name}.txt"
    write_text_report(title, report, rows, txt_path)
    mirror_report(txt_path, paths["mirror_reports"])
    if dashboard:
        html_path = paths["reports"] / f"{name.replace('_inventory', '_dashboard').replace('_report', '_dashboard')}.html"
        if name == "iso_audio_decode_report":
            write_audio_decode_dashboard(title, [json_path.name, txt_path.name], rows, html_path, paths["reports"], report)
        else:
            write_dashboard(title, [json_path.name, txt_path.name], rows, html_path, paths["reports"])
        mirror_report(html_path, paths["mirror_reports"])



def texture_diagnostic_rows(inventory: dict[str, Any], extraction: dict[str, Any] | None = None, decodes: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    extracted_top = {r.get("source_iso_path"): r for r in (extraction or {}).get("files", []) if r.get("status") == "extracted"}
    extracted_emb = {(r.get("parent_iso_path"), r.get("offset")): r for r in (extraction or {}).get("files", []) if r.get("status") == "extracted"}
    decode_by_input: dict[str, dict[str, Any]] = {}
    for section in (decodes or {}).get("decodes", []):
        if section.get("type") == "textures":
            for item in section.get("items") or []:
                if item.get("input"):
                    decode_by_input[str(item["input"])] = item
    rows: list[dict[str, Any]] = []
    for cand in inventory.get("candidates", []):
        tex = cand.get("texture_candidate")
        if not tex and cand.get("bucket") != "texture_palette_bundle":
            continue
        source = cand.get("source")
        extracted = extracted_emb.get((cand.get("parent_iso_path") or cand.get("path"), cand.get("offset"))) if source == "embedded" else extracted_top.get(cand.get("path") or cand.get("iso_path"))
        raw_path = extracted.get("output_path") if extracted else cand.get("extracted_path")
        decode_item = decode_by_input.get(str(raw_path)) if raw_path else None
        meta = (decode_item or {}).get("metadata") or {}
        rows.append({
            "source": source,
            "source_iso_path": cand.get("iso_path") or cand.get("path") or cand.get("parent_iso_path"),
            "parent_iso_path": cand.get("parent_iso_path"),
            "offset": cand.get("offset"),
            "bucket": cand.get("bucket"),
            "format": (tex or {}).get("format") or cand.get("signature"),
            "dimensions": meta.get("dimensions") or (tex or {}).get("dimensions"),
            "palette_hints": (tex or {}).get("palette_hints"),
            "nearby_names_strings": (tex or {}).get("texture_hints") or cand.get("nearby_strings") or cand.get("sample_strings"),
            "reasons": (tex or {}).get("reasons") or cand.get("reasons"),
            "raw_path": raw_path,
            "output_path": (decode_item or {}).get("output_path"),
            "decode_status": (decode_item or {}).get("decode_status") or (tex or {}).get("decode_status") or "decode pending",
        })
    return rows


def _is_decoded_wav(row: dict[str, Any]) -> bool:
    status = str(row.get("decode_status") or "")
    return status in CONFIRMED_PLAYABLE_AUDIO_STATUSES and not row.get("errors")


def _no_wav_reason(rows: list[dict[str, Any]]) -> str:
    text = " ".join(
        " ".join(map(str, [
            r.get("detected_format"),
            r.get("decode_status"),
            r.get("next_action"),
            *(r.get("warnings") or []),
            *(r.get("errors") or []),
        ]))
        for r in rows
    ).lower()
    if "unsupported" in text or "unknown_audio_like" in text or "cri_adx_like" in text:
        return "unsupported container"
    if "bounds" in text or "offset" in text or "size is missing" in text:
        return "invalid stream bounds"
    if "bd/body" in text or "paired bd" in text or "body data is unavailable" in text:
        return "missing paired BD body"
    if "raw" in text or "pending" in text:
        return "pending raw diagnostics"
    return "no supported decoded WAV streams were identified"


def audio_decode_report_payload(
    inventory: dict[str, Any],
    extraction: dict[str, Any] | None,
    decodes: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build enriched audio decode rows and summary counters for required reports."""
    decode_rows: list[dict[str, Any]] = []
    explicit_summary: dict[str, Any] = {}
    for section in (decodes or {}).get("decodes", []):
        if section.get("type") == "audio":
            decode_rows.extend(section.get("items") or [])
        elif section.get("type") == "explicit_audio_path_summary":
            explicit_summary = section.get("items") or {}

    extracted_audio_rows = [
        r for r in (extraction or {}).get("files", [])
        if r.get("bucket") == "audio_or_music_candidate"
    ]
    skipped_audio = [r for r in extracted_audio_rows if r.get("status") not in {"extracted", "planned"}]

    valid_gzip_rows: list[dict[str, Any]] = []
    rejected_gzip_rows: list[dict[str, Any]] = []
    for cand in inventory.get("candidates", []):
        signature = str(cand.get("signature") or cand.get("signature_reason") or "").lower()
        magic = str(cand.get("signature_magic_hex") or "")
        is_gzip = "gzip" in signature or magic.startswith("1f8b") or cand.get("gzip_eof") is not None
        if not is_gzip:
            continue
        row = {
            "source_iso_path": cand.get("parent_iso_path") or cand.get("iso_path") or cand.get("path"),
            "offset": cand.get("offset"),
            "detected_format": "gzip",
            "decode_status": cand.get("validation_status") or ("valid_gzip_member" if cand.get("signature_valid", True) else "rejected_gzip_magic_match"),
            "warnings": [cand.get("validation_error")] if cand.get("validation_error") else [],
            "gzip_eof": cand.get("gzip_eof"),
            "raw_path": cand.get("extracted_path"),
        }
        if cand.get("signature_valid", True):
            row["report_section"] = "Valid gzip members"
            valid_gzip_rows.append(row)
        else:
            row["report_section"] = "Rejected gzip magic matches"
            rejected_gzip_rows.append(row)

    bank_keys = {
        (r.get("bank_source") or r.get("source_iso_path") or r.get("source_candidate"), r.get("bank_offset"))
        for r in decode_rows
        if str(r.get("detected_format") or "") == "scei_ps_adpcm_bank_stream"
    }
    bank_rows = [
        {
            "source_iso_path": source,
            "offset": offset,
            "detected_format": "scei_sound_bank",
            "decode_status": "scei_bank_found",
            "report_section": "Sony HD/BD banks",
            "next_action": "review decoded bank streams",
        }
        for source, offset in sorted(bank_keys, key=lambda item: (str(item[0]), int(item[1] or 0)))
    ]

    for r in decode_rows:
        r.setdefault("report_section", audio_decode_section_label(r))

    all_rows = [*decode_rows, *bank_rows, *valid_gzip_rows, *rejected_gzip_rows]
    counts = Counter(audio_decode_section_label(r) for r in all_rows)
    decoded_wavs = sum(1 for r in all_rows if _is_decoded_wav(r))
    experimental_sequence_renders = sum(1 for r in all_rows if str(r.get("decode_status") or "") == EXPERIMENTAL_SEQUENCE_RENDER_STATUS)
    raw_interpretation_previews = sum(1 for r in all_rows if str(r.get("decode_status") or "") == RAW_INTERPRETATION_PREVIEW_STATUS)
    raw_pending = sum(1 for r in all_rows if audio_decode_section_label(r) not in {"Valid gzip members", "Rejected gzip magic matches"} and (r.get("raw_path") or "pending" in str(r.get("decode_status") or "")))
    failures = counts.get("Failures", 0)
    extracted_audio_count = len(extracted_audio_rows)
    summary = {
        "rows": len(all_rows),
        "explicit_audio_paths_inspected": len(explicit_summary),
        "extracted_audio_candidates_inspected": extracted_audio_count,
        "files_skipped": len(skipped_audio),
        "valid_gzip_members": len(valid_gzip_rows),
        "rejected_gzip_magic_matches": len(rejected_gzip_rows),
        "scei_hd_bd_banks_found": len(bank_rows),
        "scei_streams_found": sum(1 for r in all_rows if str(r.get("detected_format") or "") == "scei_ps_adpcm_bank_stream"),
        "decoded_wavs": decoded_wavs,
        "experimental_sequence_renders": experimental_sequence_renders,
        "raw_interpretation_previews": raw_interpretation_previews,
        "raw_pending_streams": raw_pending,
        "failures": failures,
    }
    if decoded_wavs == 0 and extracted_audio_count:
        summary["no_decoded_wav_reason"] = _no_wav_reason(decode_rows)
    labels = ["Decoded playable audio", "Sony HD/BD banks", "Bank streams", "Valid gzip members", "Rejected gzip magic matches", "Experimental sequence renders", "Raw interpretation previews", "Unknown audio containers", "Failures"]
    sections = [{"title": label, "count": counts.get(label, 0)} for label in labels]
    return all_rows, {"summary": summary, "sections": sections, "explicit_audio_path_summary": explicit_summary}


def write_required_reports(inventory: dict[str, Any], paths: dict[str, Path], extraction: dict[str, Any] | None = None, decodes: dict[str, Any] | None = None) -> None:
    top_rows, embedded_rows = inventory_rows(inventory, extraction)
    base = {"created_at": utc_now(), "iso_path": inventory.get("iso_path"), "summary": inventory.get("summary", {})}
    all_rows = top_rows + embedded_rows
    write_inventory_suite("iso_media_inventory", "ISO Media Inventory", base, all_rows, paths)
    audio_rows = [r for r in all_rows if r.get("bucket") == "audio_or_music_candidate" or "audio" in str(r.get("recommended_action") or r.get("suggested_action") or "")]
    texture_rows = texture_diagnostic_rows(inventory, extraction, decodes)
    model_rows = [r for r in all_rows if r.get("bucket") in {"ccsf_model_bundle", "character_model_bundle", "environment_bundle", "animation_bundle"}]
    unknown_rows = [r for r in all_rows if str(r.get("bucket") or "").startswith("unknown")]
    write_inventory_suite("iso_audio_inventory", "ISO Audio Inventory", base | {"summary": {"rows": len(audio_rows)}}, audio_rows, paths)
    write_inventory_suite("iso_texture_inventory", "ISO Texture Inventory", base | {"summary": {"rows": len(texture_rows)}}, texture_rows, paths)
    write_inventory_suite("iso_model_inventory", "ISO Model Inventory", base | {"summary": {"rows": len(model_rows)}}, model_rows, paths, dashboard=False)
    write_inventory_suite("iso_unknown_inventory", "ISO Unknown Inventory", base | {"summary": {"rows": len(unknown_rows)}}, unknown_rows, paths, dashboard=False)

    audio_decode_rows, audio_payload = audio_decode_report_payload(inventory, extraction, decodes)
    decode_report = {"created_at": utc_now(), "iso_path": inventory.get("iso_path")} | audio_payload
    write_inventory_suite("iso_audio_decode_report", "ISO Audio Decode Report", decode_report, audio_decode_rows, paths)


def build_inventory(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
    payload, iso = iso_asset_survey.load_or_build_index(Path(args.iso_path), None)
    candidates: list[dict[str, Any]] = []
    max_read = None if args.scan_all_bytes else args.max_read_bytes
    files = [e for e in payload.get("files", []) if not e.get("is_dir")]
    manifest = load_container_scan_manifest(paths, args.iso_path)
    entries_cache = manifest.setdefault("entries", {})
    manifest["iso_identity"] = iso_identity(args.iso_path)
    emit_progress(args, "inventory_start", total=len(files), candidates_found=0)
    with Path(args.iso_path).open("rb") as fh:
        for index, e in enumerate(files, start=1):
            path = str(e.get("path") or "")
            key = cache_key(args.iso_path, path, e.get("lba"), e.get("size"))
            cached = entries_cache.get(key)
            emit_progress(args, "inventory_scan", current_path=path, current_index=index, total=len(files), candidates_found=len(candidates))
            if cached and isinstance(cached.get("candidates"), list):
                candidates.extend(iso_asset_survey.normalize_candidate_row(r) for r in cached.get("candidates", []))
                continue
            read_cap = int(e.get("size") or 0) if max_read is None else int(max_read)
            data = iso_asset_survey.read_iso_entry(iso, fh, e, read_cap)
            row = iso_asset_survey.classify_blob(path, int(e.get("size") or len(data)), data, "top_level")
            nearby = iso_asset_survey.nearby_strings(data)
            tex_info = texture_candidate_info(path, data, nearby)
            entry_candidates_start = len(candidates)
            if _fold_iso_path(path) in set(EXPLICIT_AUDIO_ISO_PATHS):
                row["bucket"] = "audio_or_music_candidate"
                row.setdefault("reasons", []).append("explicit audio ISO path")
            row.update({
                "iso_path": path,
                "lba": e.get("lba"),
                "first_bytes_hex": read_first_bytes_hex(data),
                "embedded_candidate_count": 0,
                "recommended_action": recommended_action(row),
            })
            if tex_info:
                row["texture_candidate"] = tex_info
                row["texture_decode_status"] = tex_info.get("decode_status")
                row.setdefault("sample_strings", nearby)
                if row.get("bucket") in {"unknown_binary", "unknown_container"}:
                    row["recommended_action"] = "extract raw texture-like candidate"
            if args.hash:
                row["sha256"] = hashlib.sha256(data).hexdigest()
                row["sha256_bytes"] = len(data)
                row["sha256_complete"] = len(data) == int(e.get("size") or len(data))
            candidates.append(iso_asset_survey.normalize_candidate_row(row))
            embedded = iso_asset_survey.scan_embedded_signatures(
                data,
                args.embedded_read_bytes,
                max(0, int(args.max_embedded_per_file)),
            )
            row["embedded_candidate_count"] = len(embedded)
            if b"CCSF" in data:
                ccsf_hints = [h for h in texture_string_hints(path, iso_asset_survey.strings(data)) if h.startswith(("TEX_", "CLT_"))]
                for hint in ccsf_hints[:20]:
                    try:
                        hint_offset = data.index(hint.encode("ascii", "ignore"))
                    except ValueError:
                        hint_offset = None
                    candidates.append(iso_asset_survey.normalize_candidate_row({
                        "source": "embedded",
                        "path": path,
                        "parent_iso_path": path,
                        "offset": hint_offset,
                        "bucket": "texture_palette_bundle",
                        "guessed_type": "ccsf_texture_hint",
                        "signature": "CCSF TEX_/CLT_ string hint",
                        "estimated_size": 0,
                        "size": 0,
                        "nearby_strings": iso_asset_survey.nearby_strings(data, hint_offset),
                        "suggested_action": "inspect CCSF texture section",
                        "suggested_next_action": "inspect CCSF texture section",
                        "reasons": ["TEX_/CLT_ hint inside CCSF bundle"],
                        "texture_candidate": {"format": "ccsf_texture_hint", "dimensions": None, "decode_status": "decode pending", "palette_hints": ["CLT_ hint present"] if hint.startswith("CLT_") else [], "texture_hints": ccsf_hints, "reasons": ["TEX_/CLT_ hint inside CCSF bundle"]},
                        "texture_decode_status": "decode pending",
                    }))
            for hit in embedded:
                if not hit.get("signature_valid", True):
                    candidates.append(iso_asset_survey.normalize_candidate_row({
                        "source": "embedded",
                        "path": path,
                        "parent_iso_path": path,
                        "offset": int(hit["offset"]),
                        "bucket": "unknown_binary",
                        "label": "rejected_embedded_signature",
                        "signature": hit["signature"],
                        "signature_magic_hex": hit["signature_magic_hex"],
                        "signature_reason": hit["signature_reason"],
                        "guessed_type": "rejected_embedded_signature",
                        "estimated_size": 0,
                        "size": 0,
                        "first_bytes_hex": "",
                        "nearby_strings": hit["nearby_strings"],
                        "suggested_action": "diagnostic only",
                        "suggested_next_action": "diagnostic only",
                        "signature_valid": False,
                        "validation_status": hit.get("validation_status"),
                        "validation_error": hit.get("validation_error"),
                        "compressed_size": hit.get("compressed_size"),
                        "decompressed_size": hit.get("decompressed_size"),
                        "gzip_original_filename": hit.get("gzip_original_filename"),
                        "gzip_eof": hit.get("gzip_eof"),
                        "reasons": [f"rejected {hit['signature']} signature: {hit.get('validation_status') or 'invalid'}"],
                    }))
                    continue
                sample = hit["sample"]
                erow = iso_asset_survey.classify_blob(
                    path,
                    len(sample),
                    sample,
                    "embedded",
                    int(hit["offset"]),
                    hit.get("gzip_original_filename"),
                )
                tex_info = texture_candidate_info(path, sample, hit["nearby_strings"])
                erow.update({
                    "parent_iso_path": path,
                    "signature": hit["signature"],
                    "signature_magic_hex": hit["signature_magic_hex"],
                    "signature_reason": hit["signature_reason"],
                    "guessed_type": erow.get("bucket") or hit["signature_bucket"],
                    "estimated_size": len(sample),
                    "first_bytes_hex": read_first_bytes_hex(sample),
                    "nearby_strings": hit["nearby_strings"],
                    "suggested_action": hit["suggested_action"],
                    "suggested_next_action": hit["suggested_action"],
                    "signature_valid": hit.get("signature_valid", True),
                    "validation_status": hit.get("validation_status"),
                    "validation_error": hit.get("validation_error"),
                    "compressed_size": hit.get("compressed_size"),
                    "decompressed_size": hit.get("decompressed_size"),
                    "gzip_eof": hit.get("gzip_eof"),
                })
                if tex_info:
                    erow["texture_candidate"] = tex_info
                    erow["texture_decode_status"] = tex_info.get("decode_status")
                candidates.append(iso_asset_survey.normalize_candidate_row(erow))
            entry_rows = candidates[entry_candidates_start:]
            entries_cache[key] = {
                "cache_key": key,
                "iso_path": str(args.iso_path),
                "internal_iso_path": path,
                "lba": e.get("lba"),
                "file_size": int(e.get("size") or 0),
                "sha256": hashlib.sha256(data).hexdigest() if len(data) == int(e.get("size") or len(data)) else None,
                "sha256_bytes": len(data),
                "evidence": scan_evidence(path, data, row),
                "candidates": entry_rows,
            }
    candidates = [iso_asset_survey.normalize_candidate_row(row) for row in candidates]
    write_container_scan_manifest(manifest, paths)
    counts = Counter(r["bucket"] for r in candidates)
    report = {
        "created_at": utc_now(),
        "iso_path": str(args.iso_path),
        "workspace": str(args.workspace),
        "mode": "inventory",
        "scan_all_bytes": bool(args.scan_all_bytes),
        "summary": {"top_level_files": len(payload.get("files", [])), "total_candidates": len(candidates), "bucket_counts": dict(counts)},
        "candidates": candidates,
    }
    iso_asset_survey.write_reports(report | {"generated_at": report["created_at"], "index_path": None, "bucket_order": list(iso_asset_survey.BUCKETS)}, paths["reports"], max_report_rows=500)
    for p in (paths["reports"] / "iso_asset_survey.json", paths["reports"] / "iso_asset_survey.txt", paths["reports"] / "asset_survey_dashboard.html"):
        if p.exists(): mirror_report(p, paths["mirror_reports"])
    write_json_report(report, paths, "iso_media_inventory.json")
    emit_progress(args, "inventory_complete", total=len(files), candidates_found=len(candidates))
    return report



def build_known_media_inventory(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
    """Build a lightweight inventory for required known media paths only.

    This uses the ISO filesystem index metadata (path/LBA/size) and intentionally
    skips embedded signature/byte discovery used by the full inventory scan.
    """
    payload, _iso = iso_asset_survey.load_or_build_index(Path(args.iso_path), None)
    target_order = {p: i for i, p in enumerate(EXPLICIT_AUDIO_ISO_PATHS)}
    candidates: list[dict[str, Any]] = []
    files = [e for e in payload.get("files", []) if not e.get("is_dir")]
    for e in files:
        path = str(e.get("path") or "")
        folded = _fold_iso_path(path)
        if folded not in target_order:
            continue
        row = {
            "source": "top_level",
            "path": path,
            "iso_path": path,
            "bucket": "audio_or_music_candidate",
            "size": int(e.get("size") or 0),
            "lba": e.get("lba"),
            "extension": PurePosixPath(path.replace("\\", "/")).suffix.lower(),
            "recommended_action": "extract and run audio decoder",
            "reasons": ["explicit known media ISO path"],
        }
        candidates.append(iso_asset_survey.normalize_candidate_row(row))
    candidates.sort(key=lambda row: target_order.get(_fold_iso_path(str(row.get("path") or row.get("iso_path") or "")), 999))
    counts = Counter(r["bucket"] for r in candidates)
    report = {
        "created_at": utc_now(),
        "iso_path": str(args.iso_path),
        "workspace": str(args.workspace),
        "mode": "known_media_inventory",
        "scan_all_bytes": False,
        "summary": {"top_level_files": len(files), "total_candidates": len(candidates), "bucket_counts": dict(counts), "known_media_targets": list(EXPLICIT_AUDIO_ISO_PATHS)},
        "candidates": candidates,
    }
    write_json_report(report, paths, "iso_media_inventory.json")
    return report


def inventory_has_known_media_targets(inventory: dict[str, Any]) -> bool:
    paths = {_fold_iso_path(str(row.get("path") or row.get("iso_path") or "")) for row in inventory.get("candidates", []) if isinstance(row, dict)}
    return set(EXPLICIT_AUDIO_ISO_PATHS).issubset(paths)

def selected_buckets(args: argparse.Namespace) -> set[str]:
    return set(args.extract_bucket or DEFAULT_BUCKETS)


def output_budget_bytes(args: argparse.Namespace) -> int:
    return max(0, int(args.max_output_mb)) * 1024 * 1024


def embedded_dir_for_bucket(bucket: str | None) -> str:
    return EXTRACTED_EMBEDDED_DIRS.get(str(bucket or ""), "unknown")


def embedded_suffix(cand: dict[str, Any]) -> str:
    bucket = str(cand.get("bucket") or cand.get("guessed_type") or "")
    signature = str(cand.get("signature") or "").lower()
    if bucket == "ccsf_model_bundle":
        return ".ccs"
    if bucket == "texture_palette_bundle":
        if "png" in signature:
            return ".png"
        if "jpeg" in signature:
            return ".jpg"
        if "tim" in signature:
            return ".tm2"
        return ".tex.bin"
    if bucket == "audio_or_music_candidate":
        if "riff" in signature or "wave" in signature:
            return ".wav"
        if "vag" in signature:
            return ".vag"
        if "midi" in signature:
            return ".mid"
        return ".audio.bin"
    if bucket == "movie_or_stream_candidate":
        return ".stream.bin"
    return ".bin"


def extract_candidates(args: argparse.Namespace, inventory: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    buckets = selected_buckets(args)
    iso = Iso9660(Path(args.iso_path)).open()
    read_iso = iso
    entries = inventory_entries(inventory)
    entry_paths_by_folded = {path.replace("\\", "/").lower(): path for path in entries}
    seen_top_paths: set[str] = set()
    paired_top_paths: dict[str, dict[str, Any]] = {}
    seen_embedded: set[tuple[str, int, str]] = set()
    rows: list[dict[str, Any]] = []
    written = 0
    budget = output_budget_bytes(args)
    extractable = [c for c in inventory.get("candidates", []) if iso_asset_survey.normalize_candidate_row(c).get("bucket") in buckets]
    emit_progress(args, "extract_start", total=len(extractable), candidates_found=len(extractable), extracted_count=0)

    def reserve(size: int, row: dict[str, Any]) -> bool:
        nonlocal written
        if written + max(0, size) > budget:
            row["status"] = "skipped_budget"
            return False
        return True

    def sibling_iso_path(internal: str, suffix: str) -> str | None:
        posix = PurePosixPath(internal.replace("\\", "/"))
        sibling = posix.with_suffix(suffix).as_posix().lower()
        return entry_paths_by_folded.get(sibling)

    def extract_top_level_file(internal: str, out: Path, row: dict[str, Any]) -> bool:
        nonlocal written
        if not args.dry_run:
            out.parent.mkdir(parents=True, exist_ok=True)
            ok = iso.extract(internal, out)
            row["status"] = "extracted" if ok else "error"
            if ok:
                actual = out.stat().st_size
                written += actual
                row["bytes_written"] = actual
                if args.hash:
                    row["sha256"] = sha256_file(out)
                    row["cache_key"] = cache_key(args.iso_path, internal, entries.get(internal, {}).get("lba"), entries.get(internal, {}).get("size", actual), row["sha256"])
            return ok
        return True

    with Path(args.iso_path).open("rb") as fh:
        for current_index, raw_cand in enumerate(extractable, start=1):
            cand = iso_asset_survey.normalize_candidate_row(raw_cand)
            bucket = cand.get("bucket")
            source = cand.get("source")
            current_path = str(cand.get("path") or cand.get("iso_path") or cand.get("parent_iso_path") or "")
            emit_progress(args, "extract_candidate", current_path=current_path, current_index=current_index, total=len(extractable), candidates_found=len(extractable), extracted_count=sum(1 for r in rows if r.get("status") in {"extracted", "planned", "paired_already_extracted"}))
            if source == "top_level":
                internal = str(cand.get("path") or cand.get("iso_path") or "")
                if not internal:
                    continue
                if internal in seen_top_paths:
                    paired = paired_top_paths.get(internal)
                    if paired:
                        rows.append({
                            "source": "top_level",
                            "source_iso_path": internal,
                            "bucket": bucket,
                            "size": int(cand.get("size") or paired.get("size") or 0),
                            "output_path": paired.get("output_path"),
                            "status": "paired_already_extracted",
                            "paired_audio_role": "body",
                            "paired_header_path": paired.get("paired_header_path"),
                            "paired_source_iso_path": paired.get("paired_source_iso_path"),
                        })
                    continue
                seen_top_paths.add(internal)
                size = int(cand.get("size") or 0)
                out = safe_output_path(paths["extracted"] / "top_level", internal)
                row = {"source": "top_level", "source_iso_path": internal, "bucket": bucket, "size": size, "output_path": str(out), "status": "planned" if args.dry_run else "extracted"}
                if not reserve(size, row):
                    rows.append(row)
                    continue
                extract_top_level_file(internal, out, row)

                if PurePosixPath(internal.replace("\\", "/")).suffix.lower() == ".hd":
                    bd_internal = sibling_iso_path(internal, ".bd")
                    bd_entry = entries.get(bd_internal or "")
                    if bd_internal and bd_entry and bd_internal not in seen_top_paths:
                        bd_out = out.with_suffix(".bd")
                        bd_size = int(bd_entry.get("size") or 0)
                        bd_row = {
                            "source": "top_level",
                            "source_iso_path": bd_internal,
                            "bucket": bucket,
                            "size": bd_size,
                            "output_path": str(bd_out),
                            "status": "planned" if args.dry_run else "extracted",
                            "paired_audio_role": "body",
                            "paired_header_path": str(out),
                            "paired_source_iso_path": internal,
                        }
                        row["paired_audio_role"] = "header"
                        row["paired_body_path"] = str(bd_out)
                        row["paired_source_iso_path"] = bd_internal
                        if reserve(bd_size, bd_row):
                            extract_top_level_file(bd_internal, bd_out, bd_row)
                        seen_top_paths.add(bd_internal)
                        paired_top_paths[bd_internal] = bd_row | {"paired_header_path": str(out), "paired_source_iso_path": internal}
                        rows.append(bd_row)
                rows.append(row)
            elif source == "embedded":
                parent = str(cand.get("parent_iso_path") or cand.get("path") or "")
                offset = int(cand.get("offset") or 0)
                key = (parent, offset, str(bucket))
                if not parent or key in seen_embedded:
                    continue
                seen_embedded.add(key)
                entry = entries.get(parent)
                sample_size = int(cand.get("estimated_size") or cand.get("size") or 0)
                if sample_size <= 0:
                    rows.append({"source": "embedded", "parent_iso_path": parent, "offset": cand.get("offset"), "bucket": bucket, "size": 0, "status": "diagnostic_only"})
                    continue
                read_size = min(int(args.embedded_read_bytes), sample_size)
                rel_name = safe_rel(parent)
                stem = rel_name.as_posix().replace("/", "__")
                out_name = f"{stem}__0x{offset:X}{embedded_suffix(cand)}"
                out = safe_output_path(paths["extracted"] / "embedded" / embedded_dir_for_bucket(str(bucket)), out_name)
                row = {"source": "embedded", "parent_iso_path": parent, "offset": offset, "bucket": bucket, "size": read_size, "output_path": str(out), "status": "planned" if args.dry_run else "extracted"}
                if entry is None:
                    row["status"] = "missing_parent"
                    rows.append(row)
                    continue
                if not reserve(read_size, row):
                    rows.append(row)
                    continue
                if not args.dry_run:
                    data = iso_asset_survey.read_iso_entry(read_iso, fh, entry, offset + read_size)[offset:offset + read_size]
                    if not data:
                        row["status"] = "empty"
                    else:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(data)
                        written += len(data)
                        row["bytes_written"] = len(data)
                        if args.hash:
                            row["sha256"] = hashlib.sha256(data).hexdigest()
                            row["cache_key"] = cache_key(args.iso_path, parent, entry.get("lba"), entry.get("size"), row["sha256"], offset=offset)
                rows.append(row)
    extracted_count = sum(1 for r in rows if r.get("status") in {"extracted", "planned", "paired_already_extracted"})
    emit_progress(args, "extract_complete", total=len(extractable), candidates_found=len(extractable), extracted_count=extracted_count)
    return {"created_at": utc_now(), "selected_buckets": sorted(buckets), "bytes_written": written, "files": rows}

def extract_ccsf(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any] | None:
    if args.dry_run:
        return {"status": "dry_run", "note": "CCSF extractor not run"}
    ns = argparse.Namespace(
        iso_path=str(args.iso_path), iso_index=None, workspace=str(paths["root"]),
        out=str(paths["reports"] / "iso_media_ccsf_extraction_index.json"),
        text_out=str(paths["reports"] / "iso_media_ccsf_extraction_index.txt"),
        max_scan_bytes=args.max_read_bytes if not args.scan_all_bytes else None,
        extract_cap=args.embedded_read_bytes, container_limit=None, asset_limit=None, limit=None,
        include=[], exclude=[], container=[], build_index=False, reuse_existing=False,
        summary_only=False, quiet=True, index_assets=True, include_failed_candidates=False,
        include_non_ccsf_gzip=False, ccsf_only=True, gzip_only=False, max_report_rows=500,
        asset_index_jsonl=None, max_failed_rows=200,
    )
    report = iso_ccsf_extractor.run(ns)
    legacy_out = paths["root"] / "extracted_ccs"
    target = paths["extracted"] / "ccsf"
    if legacy_out.exists():
        if target.exists(): shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_out), str(target))
        old_root = str(legacy_out)
        new_root = str(target)
        for section in ("confirmed_ccsf_bundles", "duplicates", "extractions"):
            for row in report.get(section, []) or []:
                old = str(row.get("extracted_ccsf_path") or "")
                if old:
                    row["extracted_ccsf_path"] = old.replace(old_root, new_root)
        (paths["reports"] / "iso_media_ccsf_extraction_index.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (paths["reports"] / "iso_media_ccsf_extraction_index.txt").write_text(iso_ccsf_extractor.format_text(report, max_report_rows=500, max_failed_rows=200), encoding="utf-8")
    for p in (paths["reports"] / "iso_media_ccsf_extraction_index.json", paths["reports"] / "iso_media_ccsf_extraction_index.txt"):
        if p.exists(): mirror_report(p, paths["mirror_reports"])
    return report



def prepare_texture_candidate(raw: Path, decoded_root: Path) -> dict[str, Any]:
    data = raw.read_bytes()[:1024 * 1024]
    nearby = iso_asset_survey.nearby_strings(data)
    info = texture_candidate_info(raw.name, data, nearby) or {"format": "unknown", "decode_status": "candidate only"}
    meta = preview_texture.extract_metadata(raw)
    row: dict[str, Any] = {"input": str(raw), "metadata": meta, "nearby_names_strings": nearby, "palette_hints": info.get("palette_hints"), "format": info.get("format")}
    if info.get("decode_status") == "pass-through":
        row.update({"decode_status": "pass-through", "output_path": str(raw)})
        return row
    if info.get("format") in {"tim", "tim2"}:
        out = safe_output_path(decoded_root / "textures" / "raw", raw.name + ".raw")
        out.parent.mkdir(parents=True, exist_ok=True)
        if raw.resolve() != out.resolve():
            shutil.copy2(raw, out)
        row.update({"decode_status": "decode pending", "raw_path": str(out), "note": "TIM/TIM2 decoding is not implemented here; preserved raw bytes instead of writing a fake PNG."})
        return row
    row.update({"decode_status": "candidate only", "raw_path": str(raw)})
    return row


def load_extraction_rows(paths: dict[str, Path]) -> list[dict[str, Any]]:
    """Load the most recent pipeline extraction rows, if present."""
    candidates = [
        paths["reports"] / "iso_media_extraction.json",
        paths["mirror_reports"] / "iso_media_extraction.json",
    ]
    for report_path in candidates:
        if not report_path.is_file():
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        files = payload.get("files")
        return files if isinstance(files, list) else []
    return []


def resolve_workspace_path(value: str | Path | None, paths: dict[str, Path]) -> Path | None:
    """Resolve extraction metadata paths without allowing workspace-relative ambiguity."""
    if not value:
        return None
    raw = Path(value)
    if raw.is_absolute():
        return raw
    workspace = paths["root"].parent
    for base in (workspace, paths["root"], paths["extracted"]):
        candidate = (base / raw).resolve()
        if candidate.exists():
            return candidate
    return (workspace / raw).resolve()



def _fold_iso_path(value: str | Path | None) -> str:
    return str(value or "").replace("\\", "/").lower().strip("/")


def _explicit_audio_source_map(paths: dict[str, Path]) -> dict[str, tuple[Path, dict[str, Any]]]:
    """Return extracted files for explicit audio diagnostics, keyed by folded ISO path."""
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    for row in load_extraction_rows(paths):
        raw = resolve_workspace_path(row.get("output_path") or row.get("extracted_path"), paths)
        source = _fold_iso_path(row.get("source_iso_path") or row.get("iso_path") or row.get("path"))
        if raw and raw.is_file() and source:
            found[source] = (raw, audio_candidate_metadata(row, raw))
    # Fallback to deterministic extracted/top_level locations for these required paths.
    for iso_path in EXPLICIT_AUDIO_ISO_PATHS:
        folded = _fold_iso_path(iso_path)
        raw = safe_output_path(paths["extracted"] / "top_level", iso_path)
        if raw.is_file():
            found.setdefault(folded, (raw, {"source_iso_path": iso_path, "bucket": "audio_or_music_candidate", "extraction_output_path": str(raw)}))
    return found


def cached_top_level_evidence(paths: dict[str, Path], iso_path: str | Path | None, internal: str) -> dict[str, Any] | None:
    manifest = load_container_scan_manifest(paths, iso_path)
    wanted = _fold_iso_path(internal)
    for entry in (manifest.get("entries") or {}).values():
        if isinstance(entry, dict) and _fold_iso_path(entry.get("internal_iso_path")) == wanted:
            evidence = entry.get("evidence")
            return evidence if isinstance(evidence, dict) else None
    return None


def add_explicit_audio_decode_candidates(candidates: list[tuple[Path, dict[str, Any]]], paths: dict[str, Path]) -> list[tuple[Path, dict[str, Any]]]:
    collected = {raw.resolve(): meta for raw, meta in candidates}
    for raw, meta in _explicit_audio_source_map(paths).values():
        collected.setdefault(raw.resolve(), meta)
    return sorted(collected.items(), key=lambda item: str(item[0]))


def inspect_explicit_audio_paths(paths: dict[str, Path], audio_rows: list[dict[str, Any]] | None = None, *, decode_streams: bool = False) -> dict[str, Any]:
    source_map = _explicit_audio_source_map(paths)
    by_source_rows: dict[str, list[dict[str, Any]]] = {}
    for row in audio_rows or []:
        for key in (row.get("source_iso_path"), row.get("bank_source"), row.get("extraction_output_path"), row.get("source_candidate")):
            folded = _fold_iso_path(key)
            if folded:
                by_source_rows.setdefault(folded, []).append(row)
    out: dict[str, Any] = {}
    eff = source_map.get("netgui/eff.hd")
    if eff:
        raw, meta = eff
        item = scei_hd_bd.inspect_hd_bd_pair(raw, paths["decoded"] if decode_streams else None, "netgui/eff.hd")
        rows = by_source_rows.get("netgui/eff.hd") or by_source_rows.get(_fold_iso_path(raw)) or item.pop("decoded_rows", [])
        item.update(scei_hd_bd.bank_summary(scei_hd_bd.parse_bank(raw.read_bytes(), "netgui/eff.hd", 0, raw.with_suffix(".bd").stat().st_size if raw.with_suffix(".bd").is_file() else None, raw.stat().st_size), rows, pair_found=raw.with_suffix(".bd").is_file()))
        out["netgui/eff.hd"] = item
    else:
        out["netgui/eff.hd"] = {"path": "netgui/eff.hd", "present": False, "pair_found": False}
    out["netgui/eff.bd"] = {"path": "netgui/eff.bd", "present": "netgui/eff.bd" in source_map, "pair_found": bool(eff and eff[0].with_suffix(".bd").is_file())}
    snd = source_map.get("data/snddata.bin")
    if snd:
        out["data/snddata.bin"] = scei_hd_bd.inspect_snddata(snd[0], paths["decoded"] if decode_streams else None, "data/snddata.bin")
    else:
        cached = cached_top_level_evidence(paths, None, "data/snddata.bin")
        scei = (cached or {}).get("scei") if cached else None
        out["data/snddata.bin"] = {"path": "data/snddata.bin", "present": False, "cached_scei_evidence": scei, "detail_source": "container_scan_manifest" if scei else None}
    for iso_path in ("voice/bgm.bin", "voice/food.bin"):
        raw_info = source_map.get(iso_path)
        out[iso_path] = inspect_raw_explicit_audio_container(raw_info[0], iso_path) if raw_info else {"path": iso_path, "present": False}
    return out


def inspect_raw_explicit_audio_container(path: Path, source_iso_path: str) -> dict[str, Any]:
    """Inspect explicit raw audio containers without promoting hints to confirmed codecs."""
    data = path.read_bytes()
    probe = audio_decoder.identify_audio_format(data, source_iso_path)
    embedded_hits = iso_asset_survey.scan_embedded_signatures(
        data,
        min(len(data), DEFAULT_EMBEDDED_READ_BYTES),
        DEFAULT_MAX_EMBEDDED_PER_FILE,
    )
    embedded_waves = scan_embedded_waves(data)
    validated_mpeg_audio_regions = scan_validated_mpeg_audio_regions(data)
    return {
        "path": source_iso_path,
        "present": True,
        "signature_hex": data[:16].hex(),
        "raw_audio_probe": {
            "detected_format": probe.detected_format,
            "confidence": probe.confidence,
            "warnings": list(probe.warnings),
            "errors": list(probe.errors),
            "next_action": probe.next_action,
        },
        "gzip_header_valid": scei_hd_bd.validate_gzip_header(data),
        "embedded_scan": [
            {
                "offset": hit.get("offset"),
                "signature": hit.get("signature"),
                "signature_bucket": hit.get("signature_bucket"),
                "signature_valid": hit.get("signature_valid", True),
                "validation_status": hit.get("validation_status"),
            }
            for hit in embedded_hits
            if hit.get("signature") in {"RIFF", "WAVE", "MPEG program stream", "MPEG video"}
        ],
        "embedded_waves": embedded_waves,
        "validated_mpeg_audio_regions": [
            {k: v for k, v in region.items() if k != "frames"}
            for region in validated_mpeg_audio_regions
        ],
        "candidates": scei_hd_bd.signature_candidates(data),
    }

def audio_candidate_metadata(row: dict[str, Any], raw: Path) -> dict[str, Any]:
    """Build the metadata passed through to the audio decoder for reports."""
    source_iso_path = row.get("source_iso_path") or row.get("iso_path") or row.get("path")
    parent_iso_path = row.get("parent_iso_path")
    if not source_iso_path:
        source_iso_path = parent_iso_path or str(raw)
    meta = {
        "source_iso_path": source_iso_path,
        "parent_iso_path": parent_iso_path,
        "offset": row.get("offset"),
        "bucket": row.get("bucket"),
        "extraction_output_path": row.get("output_path") or row.get("extracted_path") or str(raw),
    }
    return {k: v for k, v in meta.items() if v is not None}


def collect_audio_decode_candidates(paths: dict[str, Path]) -> list[tuple[Path, dict[str, Any]]]:
    """Collect audio candidates from extraction metadata plus audio-like files."""
    collected: dict[Path, dict[str, Any]] = {}

    def add(raw: Path | None, metadata: dict[str, Any]) -> None:
        if raw is None or not raw.is_file():
            return
        resolved = raw.resolve()
        collected.setdefault(resolved, metadata)

    for row in load_extraction_rows(paths):
        if row.get("status") != "extracted":
            continue
        raw = resolve_workspace_path(row.get("output_path") or row.get("extracted_path"), paths)
        if row.get("bucket") == "audio_or_music_candidate":
            add(
                raw,
                audio_candidate_metadata(
                    row,
                    raw or Path(str(row.get("output_path") or row.get("extracted_path") or "")),
                ),
            )

    embedded_audio = paths["extracted"] / "embedded" / "audio"
    if embedded_audio.exists():
        for raw in sorted(embedded_audio.rglob("*")):
            if raw.is_file():
                rel = raw.relative_to(paths["extracted"])
                add(
                    raw,
                    {
                        "source_iso_path": str(rel),
                        "bucket": "audio_or_music_candidate",
                        "extraction_output_path": str(raw),
                    },
                )

    for raw in sorted(paths["extracted"].rglob("*")):
        if raw.is_file() and raw.suffix.lower() in iso_asset_survey.AUDIO_EXTENSIONS:
            rel = raw.relative_to(paths["extracted"])
            add(raw, {"source_iso_path": str(rel), "extraction_output_path": str(raw)})

    return sorted(collected.items(), key=lambda item: str(item[0]))


def audio_progress_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    decoded_wavs = 0
    raw_pending = 0
    failures = 0
    banks_found = 0
    streams_found = 0
    for row in rows:
        status = str(row.get("decode_status") or row.get("status") or "")
        if status in {"copied_validated_wav", "decoded_ps_adpcm_to_pcm_wav", "decoded_vagp_to_pcm_wav"} or str(row.get("output_path") or "").lower().endswith(".wav"):
            decoded_wavs += 1
        if status in {"copied_container", "copied_midi", "decode_pending_raw_only", "identified_sound_bank_raw_only", "needs_inspection", "raw_dumped_unknown_audio_like", "raw_preserved_malformed_scei_stream", "unavailable_malformed_scei_stream"}:
            raw_pending += 1
        if "failed" in status or row.get("errors"):
            failures += 1
        if status == "scei_bank_found" or row.get("bank_name") or row.get("bank_type"):
            banks_found += 1
        if row.get("stream_index") is not None or row.get("stream_count") is not None:
            streams_found += 1
    return {
        "decoded_wavs": decoded_wavs,
        "raw_pending": raw_pending,
        "failures": failures,
        "banks_found": banks_found,
        "streams_found": streams_found,
    }


def decode(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if args.no_decode:
        return {"created_at": utc_now(), "status": "skipped", "reason": "--no-decode", "decodes": rows}
    if args.decode_models:
        model_assets = sorted((paths["extracted"] / "embedded" / "ccsf").glob("*.ccs"))
        model_assets.extend(sorted((paths["extracted"] / "top_level").rglob("*.ccs")))
        model_assets.extend(sorted((paths["extracted"] / "top_level").rglob("*.ccsf")))
        for asset in model_assets:
            if args.dry_run:
                rows.append({"input": str(asset), "type": "model", "status": "planned"}); continue
            if getattr(args, "legacy_model_diagnostics", False):
                report = ccsf_model_decoder.decode_model(asset, paths["decoded"] / "models")
                rows.append({"input": str(asset), "type": "model", "decoder": "legacy_heuristic_diagnostics", "status": report.get("decode_status"), "report": report.get("report_path")})
            else:
                struct_report = ccsf_structure_decoder.decode(asset)
                report = ccsf_structure_decoder.report_to_dict(struct_report)
                defaults = ccsf_structure_decoder._default_decode_paths(asset, paths["decoded"] / "models")
                defaults["asset_out_dir"].mkdir(parents=True, exist_ok=True)
                defaults["report"].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                defaults["text_report"].write_text(ccsf_structure_decoder.render_text(struct_report) + "\n", encoding="utf-8")
                rows.append({"input": str(asset), "type": "model", "decoder": "ccsf_structure_decoder", "status": report.get("decode_status"), "message": report.get("model_record_message"), "report": str(defaults["report"])})
    if args.decode_textures:
        tex_rows = []
        for raw in sorted((paths["extracted"]).rglob("*")):
            if not raw.is_file():
                continue
            head = raw.read_bytes()[:64]
            if raw.suffix.lower() in TEXTURE_EXTENSIONS or image_header_info(head) or tim_header_info(head, raw.suffix.lower()):
                if args.dry_run:
                    tex_rows.append({"input": str(raw), "decode_status": "planned"})
                else:
                    tex_rows.append(prepare_texture_candidate(raw, paths["decoded"]))
        rows.append({"type": "textures", "status": "complete", "items": tex_rows})
    if args.decode_audio:
        audio_rows = []
        candidates = add_explicit_audio_decode_candidates(collect_audio_decode_candidates(paths), paths)
        emit_progress(args, "audio_decode_start", total=len(candidates), **audio_progress_counts(audio_rows))
        for current_index, (raw, metadata) in enumerate(candidates, start=1):
            emit_progress(args, "audio_decode_candidate", current_path=raw, current_index=current_index, total=len(candidates), **audio_progress_counts(audio_rows))
            source_iso_path = str(metadata.get("source_iso_path") or raw)
            if _fold_iso_path(source_iso_path) in {"voice/bgm.bin", "voice/food.bin"}:
                subdir = "voice_bgm" if _fold_iso_path(source_iso_path) == "voice/bgm.bin" else "voice_food"
                wav_rows = [] if args.dry_run else extract_embedded_waves(raw, source_iso_path, paths["decoded"] / "audio" / "wav" / subdir)
                mpeg_rows = [] if args.dry_run else extract_validated_mpeg_audio_regions(raw, source_iso_path, paths["decoded"] / "audio" / "mpeg" / subdir)
                for extracted_row in [*wav_rows, *mpeg_rows]:
                    for key in ("parent_iso_path", "bucket", "extraction_output_path"):
                        if metadata.get(key) is not None:
                            extracted_row[key] = metadata[key]
                    audio_rows.append(extracted_row)
                if wav_rows or mpeg_rows:
                    emit_progress(args, "audio_decode_candidate_complete", current_path=raw, current_index=current_index, total=len(candidates), **audio_progress_counts(audio_rows))
                    continue
            if args.dry_run:
                with raw.open("rb") as fh:
                    guess = audio_decoder.identify_audio_format(fh.read(4096), str(metadata.get("source_iso_path") or raw))
                audio_rows.append({
                    "source_candidate": str(raw),
                    "source_iso_path": metadata.get("source_iso_path") or str(raw),
                    "parent_iso_path": metadata.get("parent_iso_path"),
                    "offset": metadata.get("offset", 0),
                    "bucket": metadata.get("bucket"),
                    "extraction_output_path": metadata.get("extraction_output_path"),
                    "detected_format": guess.detected_format,
                    "confidence": guess.confidence,
                    "decode_status": "planned",
                    "output_path": None,
                    "raw_path": None,
                    "sample_rate": guess.sample_rate,
                    "channels": guess.channels,
                    "duration_estimate": guess.duration_estimate,
                    "warnings": list(guess.warnings),
                    "errors": list(guess.errors),
                    "next_action": guess.next_action,
                    "audio_purpose": audio_decoder.classify_audio_purpose(str(metadata.get("source_iso_path") or raw)),
                })
                emit_progress(args, "audio_decode_candidate_complete", current_path=raw, current_index=current_index, total=len(candidates), **audio_progress_counts(audio_rows))
                continue
            head = raw.read_bytes()[:8]
            if head == scei_hd_bd.MAGIC:
                scei_rows = scei_hd_bd.decode_scei_path(raw, paths["decoded"])
                for decoded in scei_rows:
                    for key in ("parent_iso_path", "bucket", "extraction_output_path"):
                        if metadata.get(key) is not None:
                            decoded[key] = metadata[key]
                    decoded.setdefault("source_candidate", str(raw))
                    decoded["source_iso_path"] = metadata.get("source_iso_path") or decoded.get("source_iso_path") or str(raw)
                    audio_rows.append(decoded)
                if not scei_rows:
                    decoded = audio_decoder.decode_audio_candidate(raw, paths["decoded"], metadata)
                    for key in ("parent_iso_path", "bucket", "extraction_output_path"):
                        if metadata.get(key) is not None:
                            decoded[key] = metadata[key]
                    audio_rows.append(decoded)
                emit_progress(args, "audio_decode_candidate_complete", current_path=raw, current_index=current_index, total=len(candidates), **audio_progress_counts(audio_rows))
                continue
            decoded = audio_decoder.decode_audio_candidate(raw, paths["decoded"], metadata)
            for key in ("parent_iso_path", "bucket", "extraction_output_path"):
                if metadata.get(key) is not None:
                    decoded[key] = metadata[key]
            audio_rows.append(decoded)
            emit_progress(args, "audio_decode_candidate_complete", current_path=raw, current_index=current_index, total=len(candidates), **audio_progress_counts(audio_rows))
        explicit_summary = inspect_explicit_audio_paths(paths, audio_rows)
        rows.append({"type": "explicit_audio_path_summary", "status": "complete", "items": explicit_summary})
        rows.append({"type": "audio", "status": "complete", "items": audio_rows})
        emit_progress(args, "audio_decode_complete", total=len(candidates), **audio_progress_counts(audio_rows))
    return {"created_at": utc_now(), "status": "complete", "decodes": rows}


def run(args: argparse.Namespace) -> dict[str, Any]:
    paths = dirs(Path(args.workspace))
    if getattr(args, "progress_jsonl", None):
        progress_path = Path(args.progress_jsonl)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text("", encoding="utf-8")
    emit_progress(args, "start")
    if args.clean and paths["root"].exists() and not args.dry_run:
        shutil.rmtree(paths["root"])
    ensure_dirs(paths)
    summary: dict[str, Any] = {"created_at": utc_now(), "iso_path": str(args.iso_path), "workspace": str(args.workspace), "mode": args.mode, "paths": {k: str(v) for k, v in paths.items()}, "steps": {}}
    inventory = None
    top = None
    dec = None
    if args.mode in {"inventory", "all"}:
        inventory = build_inventory(args, paths)
        summary["steps"]["inventory"] = {"candidate_count": inventory["summary"]["total_candidates"], "bucket_counts": inventory["summary"]["bucket_counts"]}
    elif args.mode == "extract":
        inventory = load_existing_inventory(args, paths)
        if getattr(args, "known_media_targets", False) and (inventory is None or not inventory_has_known_media_targets(inventory)):
            inventory = build_known_media_inventory(args, paths)
            summary["steps"]["inventory"] = {"known_media_targets": True, "candidate_count": inventory["summary"]["total_candidates"], "bucket_counts": inventory["summary"].get("bucket_counts", {})}
        elif inventory is None:
            inventory = build_inventory(args, paths)
            summary["steps"]["inventory"] = {"candidate_count": inventory["summary"]["total_candidates"], "bucket_counts": inventory["summary"].get("bucket_counts", {})}
        else:
            summary["steps"]["inventory"] = {"reused": True, "candidate_count": inventory.get("summary", {}).get("total_candidates", len(inventory.get("candidates", [])))}
    if args.mode in {"extract", "all"}:
        top = extract_candidates(args, inventory, paths)
        summary["steps"]["extract"] = {"candidates": top}
        write_json_report(top, paths, "iso_media_extraction.json")
    if args.mode in {"decode", "all"}:
        dec = decode(args, paths)
        summary["steps"]["decode"] = dec
        write_json_report(dec, paths, "iso_media_decode.json")
    if inventory is not None:
        emit_progress(args, "reports_start")
        write_required_reports(inventory, paths, top, dec)
        emit_progress(args, "reports_complete")
    write_json_report(summary, paths, "iso_media_pipeline_summary.json")
    emit_progress(args, "complete")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run ISO media inventory/extract/decode pipeline.")
    ap.add_argument("iso_path")
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--mode", choices=("inventory", "extract", "decode", "all"), default="all")
    ap.add_argument("--scan-all-bytes", action="store_true")
    ap.add_argument("--max-read-bytes", type=int, default=DEFAULT_MAX_READ_BYTES)
    ap.add_argument("--embedded-read-bytes", type=int, default=DEFAULT_EMBEDDED_READ_BYTES)
    ap.add_argument("--max-embedded-per-file", type=int, default=DEFAULT_MAX_EMBEDDED_PER_FILE)
    ap.add_argument("--extract-bucket", action="append", default=[])
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-output-mb", type=int, default=DEFAULT_MAX_OUTPUT_MB)
    ap.add_argument("--no-decode", action="store_true")
    ap.add_argument("--decode-audio", action="store_true")
    ap.add_argument("--decode-textures", action="store_true")
    ap.add_argument("--decode-models", action="store_true", help="Parse CCS Structure for extracted model assets")
    ap.add_argument("--legacy-model-diagnostics", action="store_true", help="With --decode-models, run the legacy heuristic float scanner instead of the structure parser")
    ap.add_argument("--hash", action="store_true", help="Compute SHA256 for inventory samples and extracted files.")
    ap.add_argument("--known-media-targets", action="store_true", help="Extract explicit known media targets from ISO filesystem metadata without embedded byte discovery.")
    ap.add_argument("--progress-jsonl", help="Append compact JSONL progress events to this path.")
    ap.add_argument("--rescan-inventory", action="store_true", help="Ignore an existing matching iso_media_inventory.json and rescan the ISO before extraction.")
    args = ap.parse_args(argv)
    if args.mode in {"decode", "all"} and not (args.decode_audio or args.decode_textures or args.decode_models or args.no_decode):
        args.decode_models = True
    summary = run(args)
    print(f"Wrote {Path(args.workspace) / 'media_pipeline' / 'reports' / 'iso_media_pipeline_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

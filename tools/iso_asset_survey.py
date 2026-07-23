#!/usr/bin/env python3
"""Conservative ISO asset survey.

Classifies top-level ISO files and lightweight embedded candidates into broad,
non-confirming asset buckets.  The survey intentionally favors "candidate" and
"unknown" language unless a known signature/magic byte sequence is present.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from iso9660 import Iso9660  # noqa: E402
from fragment_core import CCSF_SIG  # noqa: E402
from fragmenter_containers import parse_gzip_header  # noqa: E402

BUCKETS = (
    "ccsf_model_bundle", "character_model_bundle", "environment_bundle", "animation_bundle",
    "texture_palette_bundle", "audio_or_music_candidate", "movie_or_stream_candidate",
    "dialogue_or_text_candidate", "ui_or_font_candidate", "script_or_logic_candidate",
    "save_or_config_candidate", "network_or_system_candidate", "unknown_container", "unknown_binary",
)

EXT_BUCKETS = {
    ".ccs": "ccsf_model_bundle", ".ccsf": "ccsf_model_bundle",
    ".mdl": "character_model_bundle", ".mds": "character_model_bundle", ".obj": "character_model_bundle",
    ".anm": "animation_bundle", ".mot": "animation_bundle", ".mtn": "animation_bundle", ".cam": "animation_bundle",
    ".tm2": "texture_palette_bundle", ".tim2": "texture_palette_bundle", ".tim": "texture_palette_bundle",
    ".bmp": "texture_palette_bundle", ".png": "texture_palette_bundle", ".jpg": "texture_palette_bundle", ".tga": "texture_palette_bundle",
    ".vag": "audio_or_music_candidate", ".vab": "audio_or_music_candidate", ".vb": "audio_or_music_candidate", ".vh": "audio_or_music_candidate", ".adx": "audio_or_music_candidate", ".wav": "audio_or_music_candidate", ".aif": "audio_or_music_candidate", ".aiff": "audio_or_music_candidate", ".seq": "audio_or_music_candidate", ".mid": "audio_or_music_candidate", ".midi": "audio_or_music_candidate", ".hd": "audio_or_music_candidate", ".bd": "audio_or_music_candidate", ".hbd": "audio_or_music_candidate", ".ss2": "audio_or_music_candidate", ".svag": "audio_or_music_candidate", ".bnk": "audio_or_music_candidate", ".snd": "audio_or_music_candidate", ".bgm": "audio_or_music_candidate",
    ".pss": "movie_or_stream_candidate", ".mpeg": "movie_or_stream_candidate", ".mpg": "movie_or_stream_candidate", ".str": "movie_or_stream_candidate", ".ipu": "movie_or_stream_candidate",
    ".txt": "dialogue_or_text_candidate", ".msg": "dialogue_or_text_candidate", ".sub": "dialogue_or_text_candidate", ".srt": "dialogue_or_text_candidate",
    ".fnt": "ui_or_font_candidate", ".font": "ui_or_font_candidate",
    ".lua": "script_or_logic_candidate", ".py": "script_or_logic_candidate", ".scr": "script_or_logic_candidate", ".evt": "script_or_logic_candidate",
    ".ini": "save_or_config_candidate", ".cfg": "save_or_config_candidate", ".cnf": "save_or_config_candidate", ".sav": "save_or_config_candidate",
    ".irx": "network_or_system_candidate", ".elf": "network_or_system_candidate", ".img": "unknown_container", ".bin": "unknown_container", ".dat": "unknown_container", ".pac": "unknown_container", ".arc": "unknown_container", ".cmp": "unknown_container",
}

STRONG_EXTENSION_BUCKETS = {
    e: bucket
    for e, bucket in EXT_BUCKETS.items()
    if bucket in {
        "audio_or_music_candidate",
        "movie_or_stream_candidate",
        "texture_palette_bundle",
    }
}

SIGNATURES = [
    {"magic": b"\x01\x00\xcc\xcc\r\x00\x00\x00CCSF", "name": "CCSF full signature", "bucket": "ccsf_model_bundle", "reason": "CCSF container signature", "suggested_action": "extract raw candidate"},
    {"magic": b"CCSF", "name": "CCSF marker", "bucket": "ccsf_model_bundle", "reason": "CCSF marker", "suggested_action": "extract raw candidate"},
    {"magic": b"\x1f\x8b", "name": "gzip", "bucket": "unknown_container", "reason": "gzip signature", "suggested_action": "extract raw candidate"},
    {"magic": b"TIM2", "name": "TIM2", "bucket": "texture_palette_bundle", "reason": "TIM2 texture signature", "suggested_action": "extract raw candidate"},
    {"magic": b"\x10\x00\x00\x00", "name": "PlayStation TIM magic candidate", "bucket": "texture_palette_bundle", "reason": "PlayStation TIM magic candidate", "suggested_action": "diagnostic only"},
    {"magic": b"VAGp", "name": "VAGp", "bucket": "audio_or_music_candidate", "reason": "VAG audio signature", "suggested_action": "attempt audio decode"},
    {"magic": b"VABp", "name": "VABp", "bucket": "audio_or_music_candidate", "reason": "VAB sound bank header", "suggested_action": "attempt audio decode"},
    {"magic": b"IECSsreV", "name": "IECSsreV", "bucket": "audio_or_music_candidate", "reason": "SCEI HD/BD sound bank header", "suggested_action": "attempt audio decode"},
    {"magic": b"SShd", "name": "SShd", "bucket": "audio_or_music_candidate", "reason": "Sony sound header signature", "suggested_action": "attempt audio decode"},
    {"magic": b"SSbd", "name": "SSbd", "bucket": "audio_or_music_candidate", "reason": "Sony sound body marker", "suggested_action": "attempt audio decode"},
    {"magic": b"RIFF", "name": "RIFF", "bucket": "audio_or_music_candidate", "reason": "RIFF signature", "suggested_action": "attempt audio decode"},
    {"magic": b"WAVE", "name": "WAVE", "bucket": "audio_or_music_candidate", "reason": "WAVE format marker", "suggested_action": "attempt audio decode"},
    {"magic": b"MThd", "name": "MThd", "bucket": "audio_or_music_candidate", "reason": "MIDI header", "suggested_action": "attempt audio decode"},
    {"magic": b"FORM", "name": "FORM", "bucket": "audio_or_music_candidate", "reason": "AIFF/AIFF-C FORM header", "suggested_action": "attempt audio decode"},
    {"magic": b"AIFF", "name": "AIFF", "bucket": "audio_or_music_candidate", "reason": "AIFF marker", "suggested_action": "attempt audio decode"},
    {"magic": b"AIFC", "name": "AIFC", "bucket": "audio_or_music_candidate", "reason": "AIFF-C marker", "suggested_action": "attempt audio decode"},
    {"magic": b"CRI", "name": "CRI", "bucket": "audio_or_music_candidate", "reason": "CRI middleware marker (possible ADX/stream audio)", "suggested_action": "attempt audio decode"},
    {"magic": b"ADX", "name": "ADX/CRI-like", "bucket": "audio_or_music_candidate", "reason": "ADX/CRI-like marker", "suggested_action": "attempt audio decode"},
    {"magic": b"(c)CRI", "name": "ADX copyright marker", "bucket": "audio_or_music_candidate", "reason": "CRI ADX copyright marker", "suggested_action": "attempt audio decode"},
    {"magic": b"\x00\x00\x01\xba", "name": "MPEG program stream", "bucket": "movie_or_stream_candidate", "reason": "MPEG program stream signature", "suggested_action": "extract raw candidate"},
    {"magic": b"\x00\x00\x01\xb3", "name": "MPEG video", "bucket": "movie_or_stream_candidate", "reason": "MPEG video signature", "suggested_action": "extract raw candidate"},
    {"magic": b"\x7fELF", "name": "ELF", "bucket": "network_or_system_candidate", "reason": "ELF executable signature", "suggested_action": "diagnostic only"},
    {"magic": b"\x89PNG\r\n\x1a\n", "name": "PNG", "bucket": "texture_palette_bundle", "reason": "PNG signature", "suggested_action": "extract raw candidate"},
    {"magic": b"\xff\xd8\xff", "name": "JPEG", "bucket": "texture_palette_bundle", "reason": "JPEG signature", "suggested_action": "extract raw candidate"},
]
MAGICS = [(row["magic"], row["bucket"], row["reason"]) for row in SIGNATURES]
PRINT_RE = re.compile(rb"[\x20-\x7e]{4,}")
DIALOGUE_RE = re.compile(r"\b(yes|no|hello|thanks|quest|mission|talk|shop|buy|sell|item|you|your|player)\b", re.I)
SCRIPT_TERMS = ("script", "event", "trigger", "function", "state", "flag", "opcode")
CONTROL_TERMS = ("module", "driver", "iop", "sce", "system", "network", "socket", "tcp", "udp", "dns")
CCSF_PREFIXES = ("OBJ_", "MDL_", "MAT_", "TEX_", "CLT_", "ANM_", "CMP_", "BOX_", "MPH_", "DMY_", "HIT_", "LGT_", "CAM_")
DEFAULT_MAX_REPORT_ROWS = 500


AUDIO_EXTENSIONS = {
    ".vag", ".vab", ".vb", ".vh", ".adx", ".wav", ".wave", ".aif", ".aiff",
    ".aifc", ".seq", ".mid", ".midi", ".ss2", ".svag", ".pcm", ".adp", ".adpcm",
    ".at3", ".aa3", ".mus", ".bgm", ".snd", ".sfx", ".bnk", ".hd", ".bd",
}
AUDIO_NAME_TERMS = (
    "sound", "audio", "bgm", "music", "voice", "voices", "vocal", "se", "sfx", "snd",
    "song", "jingle", "ambience", "ambient", "stream", "strm", "adx", "vag", "vab",
    "adpcm", "pcm", "sample", "bank",
)
AUDIO_MAGIC_SIGNATURES = [
    (b"RIFF", "RIFF container header (possible WAVE audio)"),
    (b"WAVE", "WAVE format marker"),
    (b"VAGp", "VAG ADPCM header"),
    (b"VABp", "VAB sound bank header"),
    (b"IECSsreV", "SCEI HD/BD sound bank header"),
    (b"MThd", "MIDI header"),
    (b"FORM", "AIFF/AIFF-C FORM header"),
    (b"AIFF", "AIFF marker"),
    (b"AIFC", "AIFF-C marker"),
    (b"SShd", "Sony sound header"),
    (b"SSbd", "Sony sound body marker"),
    (b"CRI", "CRI middleware marker (possible ADX/stream audio)"),
]
AUDIO_PATH_HINT_RE = re.compile(
    r"(?i)(?:[A-Z0-9_./\\-]+(?:\.(?:vag|vab|vb|vh|adx|wav|wave|aif|aiff|aifc|seq|mid|midi|ss2|pcm|adp|adpcm|mus|bgm|snd|sfx|bnk|hd|bd))|[A-Z0-9_./\\-]*(?:sound|audio|bgm|music|voice|sfx|snd|adx|vag|vab|adpcm|pcm|stream|strm)[A-Z0-9_./\\-]*)"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ext(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).suffix.lower()


def strings(data: bytes, limit: int = 80) -> list[str]:
    out, seen = [], set()
    for m in PRINT_RE.finditer(data):
        s = m.group(0).decode("ascii", "ignore").strip()
        if s and s not in seen:
            seen.add(s); out.append(s)
            if len(out) >= limit: break
    return out


def density(data: bytes) -> float:
    if not data: return 0.0
    return sum(1 for b in data if b in (9, 10, 13) or 32 <= b < 127) / len(data)


def nearby_strings(data: bytes, offset: int | None = None, radius: int = 512, limit: int = 12) -> list[str]:
    if offset is None:
        window = data[: min(len(data), radius * 2)]
    else:
        start = max(0, offset - radius)
        window = data[start: min(len(data), offset + radius)]
    return strings(window, limit)


def audio_magic_signature(data: bytes) -> str | None:
    search_limit = min(len(data), 4096)
    for magic, description in AUDIO_MAGIC_SIGNATURES:
        if data.startswith(magic):
            return description
        off = data.find(magic, 0, search_limit)
        if off >= 0 and magic in {b"WAVE", b"AIFF", b"AIFC", b"CRI"}:
            return f"{description} at +0x{off:X}"
    return None


def embedded_audio_hints(path: str, strs: list[str], gzip_name: str | None = None) -> list[str]:
    hints: list[str] = []
    for value in (path, gzip_name or ""):
        if not value:
            continue
        low = value.lower().replace("\\", "/")
        if ext(value) in AUDIO_EXTENSIONS or any(term in low for term in AUDIO_NAME_TERMS):
            hints.append(value)
    for s in strs:
        for match in AUDIO_PATH_HINT_RE.findall(s):
            cleaned = match.strip(". ,;:\t\r\n")
            if cleaned and cleaned not in hints:
                hints.append(cleaned)
                if len(hints) >= 10:
                    return hints
    return hints


def suggested_audio_action(reason: str | None, magic_signature: str | None, source: str) -> str | None:
    if magic_signature:
        return "identify format"
    if reason and ("extension" in reason or "path/name" in reason or "container path/name" in reason):
        return "extract raw candidate" if source == "embedded" else "identify format"
    if reason:
        return "attempt decode later"
    return None


def audio_candidate_metadata(path: str, data: bytes, source: str, offset: int | None, gzip_name: str | None, strs: list[str]) -> dict[str, Any]:
    candidate_path = gzip_name or path
    e = ext(candidate_path)
    low = candidate_path.lower().replace("\\", "/")
    magic = audio_magic_signature(data)
    hints = embedded_audio_hints(path, strs, gzip_name)
    reason = None
    if e in AUDIO_EXTENSIONS:
        reason = f"common audio extension {e}"
    elif any(term in low for term in AUDIO_NAME_TERMS):
        reason = "stream-like or audio/music path/name"
    elif magic:
        reason = "audio/music magic signature"
    elif hints:
        reason = "embedded container path/name hint"
    return {
        "source_iso_path": path,
        "container": path if source == "embedded" else None,
        "detected_reason": reason,
        "magic_signature": magic,
        "nearby_strings": nearby_strings(data, 0 if offset is not None else None),
        "embedded_container_hints": hints,
        "suggested_next_action": suggested_audio_action(reason, magic, source),
    }



def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a candidate row with stable presentation fields.

    Candidate producers may emit diagnostic rows with partial metadata.  This
    helper keeps those diagnostics visible while providing the common schema
    expected by summaries, report writers, inventory JSON, and extraction
    selection.
    """
    out = dict(row or {})
    estimated = out.get("estimated_size")
    size = out.get("size")
    if size is None:
        size = estimated if estimated is not None else 0
    if estimated is None:
        estimated = size
    out["size"] = _coerce_int(size, 0)
    out["estimated_size"] = _coerce_int(estimated, out["size"])
    out["source"] = str(out.get("source") or "unknown")
    out["path"] = str(out.get("path") or "")
    out["bucket"] = str(out.get("bucket") or "unknown_binary")
    out["label"] = str(out.get("label") or out["bucket"])
    reasons = out.get("reasons")
    if reasons is None:
        out["reasons"] = []
    elif isinstance(reasons, list):
        out["reasons"] = [str(reason) for reason in reasons]
    else:
        out["reasons"] = [str(reasons)]
    for key in ("signature_valid", "suggested_action", "suggested_next_action"):
        out.setdefault(key, None)
    return out

def ccsf_groups(strs: list[str]) -> dict[str, int]:
    counts = {p[:-1]: 0 for p in CCSF_PREFIXES}
    for s in strs:
        for p in CCSF_PREFIXES:
            if s.startswith(p): counts[p[:-1]] += 1
    return {k: v for k, v in counts.items() if v}


def detect_magic(data: bytes) -> tuple[str | None, str | None]:
    for magic, bucket, reason in MAGICS:
        if data.startswith(magic) or (magic in (CCSF_SIG, b"CCSF", b"TIM2") and data.find(magic, 0, min(len(data), 1024 * 1024)) >= 0):
            return bucket, reason
    return None, None


def path_bucket(path: str) -> tuple[str | None, str | None]:
    low = path.lower().replace("\\", "/")
    e = ext(path)
    if e in STRONG_EXTENSION_BUCKETS:
        return STRONG_EXTENSION_BUCKETS[e], f"extension {e}"
    if any(t in low for t in ("/char", "/chr", "player", "enemy", "npc", "weapon", "body")):
        return "character_model_bundle", "path/name has character model term"
    if any(t in low for t in ("sound", "audio", "bgm", "music", "voice", "/se/", "sfx", "snd", "strm", "adpcm", "pcm", "song")):
        return "audio_or_music_candidate", "path/name has audio/music term"
    if any(t in low for t in ("/map", "/field", "town", "dungeon", "stage", "environment", "bg")):
        return "environment_bundle", "path/name has environment term"
    if any(t in low for t in ("movie", "video", "stream", "cutscene")):
        return "movie_or_stream_candidate", "path/name has movie/stream term"
    if any(t in low for t in ("dialog", "message", "text", "lang", "subtitle")):
        return "dialogue_or_text_candidate", "path/name has dialogue/text term"
    if any(t in low for t in ("font", "menu", "icon", "ui", "hud")):
        return "ui_or_font_candidate", "path/name has ui/font term"
    if any(t in low for t in SCRIPT_TERMS):
        return "script_or_logic_candidate", "path/name has script/control term"
    if any(t in low for t in ("save", "config", "option", "setting")):
        return "save_or_config_candidate", "path/name has save/config term"
    if any(t in low for t in CONTROL_TERMS):
        return "network_or_system_candidate", "path/name has system/network term"
    if e in EXT_BUCKETS:
        return EXT_BUCKETS[e], f"extension {e}"
    return None, None


def refine_from_strings(current: str, strs: list[str], path: str, reasons: list[str]) -> str:
    joined = "\n".join(strs[:200])
    groups = ccsf_groups(strs)
    if groups:
        reasons.append("known CCSF groups: " + ", ".join(f"{k}={v}" for k, v in groups.items()))
        if groups.get("ANM", 0) >= max(3, groups.get("MDL", 0) + groups.get("TEX", 0)):
            return "animation_bundle"
        if groups.get("TEX") or groups.get("CLT") or groups.get("MAT"):
            if not groups.get("MDL") and not groups.get("OBJ"):
                return "texture_palette_bundle"
        low_joined = joined.lower().replace("\\", "/")
        if groups.get("HIT"):
            reasons.append("contains collision/HIT resources")
        if groups.get("DMY"):
            reasons.append("contains dummy/marker resources")
        if groups.get("ANM") and any(s.startswith("ANM_") and any(term in s.lower() for term in ("light", "lgt", "lamp", "sun", "shadow", "controller", "ctrl")) for s in strs):
            reasons.append("lighting animation candidate")
        field_stage = bool(groups.get("CMP") and (groups.get("OBJ", 0) >= 6 or groups.get("MDL", 0) >= 6) and groups.get("TEX", 0) >= 6)
        env_path = any(t in low_joined for t in ("town", "field", "stage", "map", "s/", "bg_", "se2"))
        if field_stage:
            reasons.append("field/stage candidate")
            reasons.append("scene assembly may require transforms/controllers")
            reasons.append("StudioCCS visual scatter does not necessarily mean invalid asset")
            return "environment_bundle"
        if groups.get("LGT") or groups.get("DMY", 0) >= 8 or groups.get("HIT") or env_path:
            if env_path or groups.get("LGT") or groups.get("DMY", 0) >= 8:
                reasons.append("field/stage candidate")
            return "environment_bundle"
        if groups.get("MDL") or groups.get("OBJ"):
            return "character_model_bundle"
        return "ccsf_model_bundle"
    if len(strs) >= 3 and density(joined.encode("ascii", "ignore")) > 0.85 and DIALOGUE_RE.search(joined):
        reasons.append("printable strings include repeated dialogue-like terms")
        return "dialogue_or_text_candidate"
    low = joined.lower()
    if any(t in low for t in ("font", "menu", "icon", "ui", "hud", "window", "title", "frontend")):
        reasons.append("strings include ui/frontend terms")
        return "ui_or_font_candidate"
    if any(t in low for t in SCRIPT_TERMS):
        reasons.append("strings include script/control terms")
        return "script_or_logic_candidate"
    if any(t in low for t in CONTROL_TERMS):
        reasons.append("strings include system/network terms")
        return "network_or_system_candidate"
    return current


def classify_blob(path: str, size: int, data: bytes, source: str, offset: int | None = None, gzip_name: str | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    bucket, why = detect_magic(data)
    signature_detected = bool(why)
    if why: reasons.append(why)
    pb, pwhy = path_bucket(gzip_name or path)
    if bucket is None and pb:
        bucket = pb; reasons.append(pwhy or "path/name signal")
    strs = strings(data)
    d = density(data[: min(len(data), 65536)])
    if (not bucket or bucket == "unknown_container") and d > 0.70 and len(strs) >= 1:
        if DIALOGUE_RE.search("\n".join(strs[:200])) or len(strs) >= 6:
            bucket = "dialogue_or_text_candidate"; reasons.append(f"high printable string density ({d:.2f})")
    bucket = refine_from_strings(bucket or "unknown_binary", strs, path, reasons)
    if bucket == "unknown_binary" and ext(path) in {".bin", ".dat", ".arc", ".pac", ".cmp"}:
        bucket = "unknown_container"; reasons.append("generic container-like extension")
    audio_meta = audio_candidate_metadata(path, data, source, offset, gzip_name, strs)
    if bucket != "audio_or_music_candidate" and audio_meta["detected_reason"] and (bucket.startswith("unknown") or audio_meta["magic_signature"]):
        bucket = "audio_or_music_candidate"
        reasons.append(audio_meta["detected_reason"])
    if bucket == "audio_or_music_candidate" and audio_meta["detected_reason"] and audio_meta["detected_reason"] not in reasons:
        reasons.append(audio_meta["detected_reason"])
    row = {
        "source": source, "path": path, "offset": offset, "gzip_original_filename": gzip_name,
        "source_iso_path": path, "container": path if source == "embedded" else None,
        "size": size, "bucket": bucket, "label": bucket if signature_detected else (bucket if bucket.startswith("unknown") or bucket.endswith("_candidate") else f"{bucket}_candidate"),
        "signature_detected": signature_detected, "extension": ext(gzip_name or path) or "(none)",
        "printable_density": round(density(data[: min(len(data), 65536)]), 4), "sample_strings": strs[:20], "reasons": reasons or ["no conservative signal beyond binary presence"],
        "detected_reason": None, "magic_signature": None, "nearby_strings": [], "suggested_next_action": None,
    }
    if bucket == "audio_or_music_candidate":
        row.update(audio_meta)
        row["suggested_next_action"] = row["suggested_next_action"] or "attempt decode later"
    return row


def read_iso_entry(iso: Iso9660, fh, entry: dict[str, Any], max_bytes: int) -> bytes:
    size = int(entry.get("size") or 0)
    lba = int(entry.get("lba") or 0)
    return iso._read_user(fh, lba, min(size, max_bytes))


def load_or_build_index(iso_path: Path, index_path: Path | None) -> tuple[dict[str, Any], Iso9660]:
    iso = Iso9660(iso_path).open()
    if index_path:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        payload = {"iso": str(iso_path), "mode": iso.mode, "layout": {"sector_size": iso.sector_size, "data_offset": iso.data_offset}, "files": [e.__dict__ for e in iso.iter_files()]}
        payload["count"] = len(payload["files"])
    return payload, iso


def scan_embedded_signatures(data: bytes, limit: int, max_hits: int = 50) -> list[dict[str, Any]]:
    if max_hits <= 0 or limit <= 0:
        return []

    def gzip_validation(sample: bytes, off: int) -> dict[str, Any]:
        hdr = parse_gzip_header(sample, off)
        meta: dict[str, Any] = {
            "gzip_original_filename": hdr.original_filename if hdr else None,
            "signature_valid": False,
            "validation_status": "rejected",
            "validation_error": None,
            "compressed_size": None,
            "decompressed_size": 0,
            "gzip_eof": False,
            "sample": b"",
        }
        if hdr is None:
            meta["validation_error"] = "invalid gzip header"
            return meta
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        chunks: list[bytes] = []
        captured = 0
        total = 0
        pos = 0
        try:
            while pos < len(sample) and not decompressor.eof:
                chunk = sample[pos: min(len(sample), pos + 65536)]
                pos += len(chunk)
                decoded = decompressor.decompress(chunk)
                total += len(decoded)
                if captured < limit:
                    captured_piece = decoded[: limit - captured]
                    chunks.append(captured_piece)
                    captured += len(captured_piece)
            tail = decompressor.flush()
            total += len(tail)
            if captured < limit:
                captured_piece = tail[: limit - captured]
                chunks.append(captured_piece)
                captured += len(captured_piece)
        except zlib.error as exc:
            meta["validation_error"] = str(exc)
            return meta
        meta["gzip_eof"] = decompressor.eof
        meta["decompressed_size"] = total
        if not decompressor.eof:
            meta["validation_status"] = "truncated"
            meta["validation_error"] = "gzip stream did not reach end-of-member within scanned bytes"
            meta["compressed_size"] = len(sample)
            return meta
        meta["signature_valid"] = True
        meta["validation_status"] = "valid"
        meta["compressed_size"] = len(sample) - len(decompressor.unused_data)
        meta["sample"] = b"".join(chunks)[:limit]
        return meta

    found: list[dict[str, Any]] = []
    seen: set[tuple[int, bytes]] = set()
    for sigrow in SIGNATURES:
        sig = sigrow["magic"]
        start = 1
        while True:
            off = data.find(sig, start)
            if off < 0:
                break
            key = (off, sig)
            if key not in seen:
                name = None
                sample = data[off: min(len(data), off + limit)]
                validation: dict[str, Any] = {
                    "signature_valid": True,
                    "validation_status": "valid",
                    "validation_error": None,
                    "compressed_size": None,
                    "decompressed_size": None,
                    "gzip_eof": None,
                }
                if sig == b"\x1f\x8b":
                    validation = gzip_validation(sample, off)
                    name = validation["gzip_original_filename"]
                    sample = validation["sample"]
                found.append({
                    "offset": off,
                    "sample": sample[:limit],
                    "gzip_original_filename": name,
                    "signature": sigrow["name"],
                    "signature_magic_hex": sig.hex(),
                    "signature_reason": sigrow["reason"],
                    "signature_bucket": sigrow["bucket"],
                    "nearby_strings": nearby_strings(data, off),
                    "suggested_action": sigrow["suggested_action"],
                    **validation,
                })
                seen.add(key)
            start = off + 1
            if len(found) >= max_hits:
                return sorted(found, key=lambda row: row["offset"])
    return sorted(found, key=lambda row: row["offset"])


def embedded_candidates(path: str, data: bytes, limit: int) -> list[tuple[int, bytes, str | None]]:
    return [
        (row["offset"], row["sample"], row.get("gzip_original_filename"))
        for row in scan_embedded_signatures(data, limit, 50)
        if row.get("signature_valid", True)
    ]


def _limited_section(items, max_rows: int | None) -> tuple[list[Any], int]:
    rows = list(items or [])
    if max_rows is None or max_rows < 0:
        return rows, 0
    return rows[:max_rows], max(0, len(rows) - max_rows)


def write_reports(report: dict[str, Any], reports_dir: Path, *, max_report_rows: int | None = DEFAULT_MAX_REPORT_ROWS) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    candidates = [normalize_candidate_row(row) for row in report.get("candidates", [])]
    report["candidates"] = candidates
    (reports_dir / "iso_asset_survey.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shown_candidates, omitted_candidates = _limited_section(candidates, max_report_rows)
    row_limit_label = "unlimited" if max_report_rows is None or max_report_rows < 0 else str(max_report_rows)
    lines = ["ISO Asset Survey", "================", f"ISO: {report['iso_path']}", f"Generated: {report['generated_at']}", f"Text row limit: {row_limit_label}", "", "Bucket counts:"]
    for b in BUCKETS:
        lines.append(f"  {b}: {report['summary']['bucket_counts'].get(b, 0)}")
    lines += ["", "CCS scene notes:", "  - field/stage candidate", "  - contains collision/HIT resources", "  - contains dummy/marker resources", "  - scene assembly may require transforms/controllers", "  - StudioCCS visual scatter does not necessarily mean invalid asset", "", f"Candidates (showing {len(shown_candidates)} of {len(candidates)}; omitted {omitted_candidates}):"]
    for r in shown_candidates:
        size = _coerce_int(r.get("size", r.get("estimated_size", 0)), 0)
        reasons = list(r.get("reasons") or [])
        path = str(r.get("path") or "")
        bucket = str(r.get("bucket") or "unknown_binary")
        offset = r.get("offset")
        loc = path + (f" @0x{_coerce_int(offset):08X}" if offset is not None else "")
        lines.append(f"- [{bucket}] {loc} ({size} bytes): {'; '.join(map(str, reasons[:3]))}")
    (reports_dir / "iso_asset_survey.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    row_html = []
    for r in shown_candidates:
        size = _coerce_int(r.get("size", r.get("estimated_size", 0)), 0)
        reasons = list(r.get("reasons") or [])
        source = str(r.get("source") or "unknown")
        path = str(r.get("path") or "")
        bucket = str(r.get("bucket") or "unknown_binary")
        offset = r.get("offset")
        offset_text = "" if offset is None else hex(_coerce_int(offset))
        row_html.append(f"<tr><td>{html.escape(bucket)}</td><td>{html.escape(source)}</td><td>{html.escape(path)}</td><td>{html.escape(offset_text)}</td><td>{size}</td><td>{html.escape('; '.join(map(str, reasons[:4])))}</td></tr>")
    rows = "\n".join(row_html)
    counts = "".join(f"<li><b>{html.escape(k)}</b>: {v}</li>" for k, v in report["summary"]["bucket_counts"].items())
    scene_notes = "".join(f"<li>{html.escape(note)}</li>" for note in ("field/stage candidate", "contains collision/HIT resources", "contains dummy/marker resources", "scene assembly may require transforms/controllers", "StudioCCS visual scatter does not necessarily mean invalid asset"))
    html_doc = f"<!doctype html><meta charset='utf-8'><title>ISO Asset Survey</title><style>body{{font-family:sans-serif}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:4px;vertical-align:top}}th{{background:#eee}}</style><h1>ISO Asset Survey</h1><p>{html.escape(report['iso_path'])}</p><p>Showing {len(shown_candidates)} of {len(candidates)} candidates; omitted {omitted_candidates}. Full data is available in JSON.</p><h2>CCS scene notes</h2><ul>{scene_notes}</ul><ul>{counts}</ul><table><thead><tr><th>Bucket</th><th>Source</th><th>Path</th><th>Offset</th><th>Size</th><th>Reasons</th></tr></thead><tbody>{rows}</tbody></table>"
    (reports_dir / "asset_survey_dashboard.html").write_text(html_doc, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Conservatively survey top-level and embedded ISO asset candidates.")
    ap.add_argument("iso_path", type=Path)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--index", "--iso-index", dest="index", type=Path, help="Optional JSON index from tools/iso_index.py")
    ap.add_argument("--max-read-bytes", type=int, default=8 * 1024 * 1024)
    ap.add_argument("--embedded-read-bytes", type=int, default=2 * 1024 * 1024)
    ap.add_argument("--max-report-rows", type=int, default=DEFAULT_MAX_REPORT_ROWS, help="Maximum candidate rows to show in TXT/HTML reports; use a negative value for unlimited.")
    args = ap.parse_args(argv)
    payload, iso = load_or_build_index(args.iso_path, args.index)
    candidates = []
    with args.iso_path.open("rb") as fh:
        for e in payload.get("files", []):
            if e.get("is_dir"): continue
            data = read_iso_entry(iso, fh, e, args.max_read_bytes)
            path = str(e.get("path") or "")
            row = classify_blob(path, int(e.get("size") or len(data)), data, "top_level")
            candidates.append(normalize_candidate_row(row))
            if row["bucket"] in {"unknown_container", "ccsf_model_bundle"} or row["signature_detected"]:
                for off, sample, gzname in embedded_candidates(path, data, args.embedded_read_bytes):
                    candidates.append(normalize_candidate_row(classify_blob(path, len(sample), sample, "embedded", off, gzname)))
    candidates = [normalize_candidate_row(row) for row in candidates]
    counts = Counter(r["bucket"] for r in candidates)
    report = {"generated_at": utc_now(), "iso_path": str(args.iso_path), "workspace": str(args.workspace), "index_path": str(args.index) if args.index else None, "bucket_order": list(BUCKETS), "summary": {"total_candidates": len(candidates), "top_level_files": len(payload.get("files", [])), "bucket_counts": dict(counts)}, "candidates": candidates}
    write_reports(report, args.workspace / "reports", max_report_rows=args.max_report_rows)
    print(f"Wrote {args.workspace / 'reports' / 'iso_asset_survey.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Conservative audio candidate identification and decoding helpers.

The helpers in this module are intended for ``iso_media_pipeline.py``.  They
only emit WAV files when the source is already a validated WAVE file or when a
VAGp stream has a valid header and can be decoded with the built-in PS ADPCM
decoder.  Other audio-looking formats are copied or dumped as raw diagnostics so
callers do not receive misleading partial decodes.
"""
from __future__ import annotations

import shutil
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


@dataclass(slots=True)
class AudioGuess:
    detected_format: str
    confidence: str
    offset: int = 0
    sample_rate: int | None = None
    channels: int | None = None
    duration_estimate: float | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    next_action: str = "inspect manually"
    details: dict[str, Any] = field(default_factory=dict)


_AUDIO_EXTS = {".vag", ".vab", ".vh", ".vb", ".wav", ".wave", ".aif", ".aiff", ".aifc", ".adx", ".mid", ".midi", ".seq", ".pcm", ".adp", ".adpcm"}
_AUDIO_TERMS = ("sound", "audio", "voice", "music", "bgm", "sfx", "snd", "adx", "vag", "adpcm", "pcm", "stream")
_MUSIC_PURPOSE_TERMS = {"bgm", "music", "song", "jingle", "stream"}
_VOICE_PURPOSE_TERMS = {"voice", "vocal", "talk"}
_SFX_PURPOSE_TERMS = {"se", "sfx", "sound", "effect"}
_VAG_COEFS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


def _path_terms(source_name: str) -> list[str]:
    normalized = str(source_name).replace("\\", "/").lower()
    terms: list[str] = []
    for part in PurePosixPath(normalized).parts:
        stem = Path(part).stem if "." in part else part
        terms.extend(t for t in stem.replace("-", "_").split("_") if t)
        terms.extend(t for t in stem.replace("_", "-").split("-") if t)
    return terms


def classify_audio_purpose(source_name: str) -> str:
    """Classify likely audio purpose from path/name terms without reading bytes."""
    terms = set(_path_terms(source_name))
    if terms & _MUSIC_PURPOSE_TERMS:
        return "likely_music"
    if terms & _VOICE_PURPOSE_TERMS:
        return "likely_voice"
    if terms & _SFX_PURPOSE_TERMS:
        return "likely_sfx"
    return "unknown"


def _safe_rel(name: str) -> Path:
    parts = [p for p in PurePosixPath(str(name).replace("\\", "/")).parts if p not in ("", ".", "..")]
    return Path(*parts) if parts else Path("unnamed.bin")


def _read_be32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _wav_info(data: bytes) -> tuple[bool, dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    info: dict[str, Any] = {}
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False, info, warnings, ["missing RIFF/WAVE header"]
    riff_size = struct.unpack_from("<I", data, 4)[0]
    if riff_size + 8 > len(data):
        errors.append("RIFF size exceeds available bytes")
    elif riff_size + 8 < len(data):
        warnings.append("trailing bytes after RIFF payload")
    pos = 12
    saw_fmt = False
    saw_data = False
    data_size = 0
    while pos + 8 <= min(len(data), riff_size + 8):
        chunk_id = data[pos:pos + 4]
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
        chunk_start = pos + 8
        chunk_end = chunk_start + chunk_size
        if chunk_end > len(data):
            errors.append(f"chunk {chunk_id!r} exceeds available bytes")
            break
        if chunk_id == b"fmt ":
            saw_fmt = True
            if chunk_size < 16:
                errors.append("fmt chunk is shorter than 16 bytes")
            else:
                audio_format, channels, sample_rate, _byte_rate, block_align, bits = struct.unpack_from("<HHIIHH", data, chunk_start)
                info.update({"audio_format": audio_format, "channels": channels, "sample_rate": sample_rate, "bits_per_sample": bits, "block_align": block_align})
                if channels <= 0 or sample_rate <= 0:
                    errors.append("fmt chunk has invalid channel count or sample rate")
                if audio_format != 1:
                    warnings.append(f"WAVE format tag {audio_format} is not PCM")
        elif chunk_id == b"data":
            saw_data = True
            data_size += chunk_size
        pos = chunk_end + (chunk_size & 1)
    if not saw_fmt:
        errors.append("missing fmt chunk")
    if not saw_data:
        errors.append("missing data chunk")
    if data_size and info.get("sample_rate") and info.get("channels") and info.get("bits_per_sample"):
        bytes_per_second = info["sample_rate"] * info["channels"] * max(1, info["bits_per_sample"] // 8)
        info["duration_estimate"] = data_size / bytes_per_second if bytes_per_second else None
    return not errors and saw_fmt and saw_data, info, warnings, errors


def _parse_vag(data: bytes) -> tuple[bool, dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    if len(data) < 0x30 or data[:4] != b"VAGp":
        return False, {}, warnings, ["missing VAGp header"]
    data_size = _read_be32(data, 0x0C)
    sample_rate = _read_be32(data, 0x10)
    name = data[0x20:0x30].split(b"\0", 1)[0].decode("ascii", "replace")
    if sample_rate <= 0 or sample_rate > 192000:
        errors.append(f"implausible VAGp sample rate {sample_rate}")
    available = max(0, len(data) - 0x30)
    if data_size == 0 or data_size > available:
        warnings.append("VAGp data size is zero or exceeds file size; using available payload")
        data_size = available
    if data_size % 16:
        warnings.append("VAGp ADPCM payload is not aligned to 16-byte blocks; truncating partial block")
        data_size -= data_size % 16
    if data_size <= 0:
        errors.append("no complete VAGp ADPCM blocks")
    info = {"sample_rate": sample_rate, "channels": 1, "data_offset": 0x30, "data_size": data_size, "name": name, "duration_estimate": (data_size // 16 * 28 / sample_rate) if sample_rate and data_size else None}
    return not errors, info, warnings, errors


def identify_audio_format(data: bytes, source_name: str = "") -> AudioGuess:
    name = source_name.lower()
    suffix = Path(name).suffix.lower()
    if data.startswith(b"RIFF"):
        ok, info, warnings, errors = _wav_info(data)
        return AudioGuess("wav" if ok else "riff_wave_invalid", "high" if ok else "medium", sample_rate=info.get("sample_rate"), channels=info.get("channels"), duration_estimate=info.get("duration_estimate"), warnings=warnings, errors=errors, next_action="copy validated WAVE" if ok else "inspect or repair RIFF/WAVE", details=info)
    if data.startswith(b"VAGp"):
        ok, info, warnings, errors = _parse_vag(data)
        return AudioGuess("vagp" if ok else "vagp_invalid", "high" if ok else "medium", sample_rate=info.get("sample_rate"), channels=1, duration_estimate=info.get("duration_estimate"), warnings=warnings, errors=errors, next_action="decode PS ADPCM to PCM WAV" if ok else "inspect VAGp header", details=info)
    if data.startswith(b"IECSsreV"):
        return AudioGuess("scei_sound_bank", "high", warnings=["SCEI HD/BD sound bank; decoded by media pipeline bank integration"], next_action="split and decode SCEI bank streams")
    if data.startswith(b"VABp") or suffix == ".vab":
        return AudioGuess("vab_sound_bank", "high" if data.startswith(b"VABp") else "medium", warnings=["VAB/VH/VB is a PlayStation sound bank; not a single stream"], next_action="split VH/VB bank with a dedicated VAB extractor")
    if suffix in {".vh", ".vb"}:
        return AudioGuess("vab_sound_bank", "medium", warnings=["VH/VB sound bank component; full bank decode is not attempted"], next_action="pair VH header with VB body and extract samples")
    if data.startswith(b"MThd"):
        return AudioGuess("midi", "high", next_action="copy MIDI sequence")
    if data.startswith(b"FORM") and data[8:12] in {b"AIFF", b"AIFC"}:
        return AudioGuess(data[8:12].decode("ascii").lower(), "high", next_action="copy AIFF/AIFC for external playback")
    if data.startswith(b"CRI") or suffix == ".adx" or b"(c)CRI" in data[:128]:
        return AudioGuess("cri_adx_like", "medium", warnings=["CRI/ADX-like stream detected, but no ADX decoder is implemented"], next_action="decode pending: use a real ADX/CRI decoder")
    if suffix in _AUDIO_EXTS or any(term in name for term in _AUDIO_TERMS):
        return AudioGuess("unknown_audio_like", "low", warnings=["audio-like extension or name but no supported header"], next_action="preserve raw bytes and inspect codec/header")
    return AudioGuess("unknown", "low", warnings=["no supported audio signature detected"], next_action="not an audio decode candidate")


def write_pcm_wav(path: Path, samples: Sequence[int], sample_rate: int, channels: int = 1) -> None:
    if sample_rate <= 0 or channels <= 0:
        raise ValueError("sample_rate and channels must be positive")
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for sample in samples:
        frames.extend(struct.pack("<h", max(-32768, min(32767, int(sample)))))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))


def decode_ps_adpcm_blocks(payload: bytes) -> tuple[list[int], list[str]]:
    """Decode mono PlayStation ADPCM blocks and return samples plus validation errors."""
    errors: list[str] = []
    if not payload:
        return [], ["empty PS ADPCM payload"]
    if len(payload) % 16:
        errors.append("PS ADPCM payload is not aligned to 16-byte blocks")
    samples: list[int] = []
    hist1 = 0
    hist2 = 0
    decoded_blocks = 0
    for pos in range(0, len(payload) - 15, 16):
        block = payload[pos:pos + 16]
        pred_shift = block[0]
        flags = block[1]
        predictor = pred_shift >> 4
        shift = pred_shift & 0x0F
        if predictor >= len(_VAG_COEFS):
            errors.append(f"invalid PS ADPCM predictor {predictor} at block 0x{pos:X}")
            continue
        if shift > 12:
            errors.append(f"invalid PS ADPCM shift {shift} at block 0x{pos:X}")
            continue
        if flags == 0x07:
            break
        coef1, coef2 = _VAG_COEFS[predictor]
        decoded_blocks += 1
        for b in block[2:]:
            for nibble in (b & 0x0F, b >> 4):
                signed = nibble - 16 if nibble >= 8 else nibble
                sample = (signed << 12) >> shift
                sample += ((hist1 * coef1) + (hist2 * coef2) + 32) >> 6
                sample = max(-32768, min(32767, sample))
                samples.append(sample)
                hist2, hist1 = hist1, sample
    if decoded_blocks == 0 or not samples:
        errors.append("no decodable PS ADPCM blocks")
    return samples, errors


def _decode_vag_blocks(payload: bytes) -> list[int]:
    samples, _errors = decode_ps_adpcm_blocks(payload)
    return samples


def decode_ps_adpcm_to_wav(payload: bytes, wav_path: Path, sample_rate: int, channels: int = 1) -> dict[str, Any]:
    """Validate/decode raw mono PS ADPCM payload to PCM WAV."""
    errors: list[str] = []
    if sample_rate <= 0 or sample_rate > 192000:
        errors.append(f"implausible sample rate {sample_rate}")
    if channels != 1:
        errors.append(f"unsupported PS ADPCM channel count {channels}")
    samples, decode_errors = decode_ps_adpcm_blocks(payload)
    errors.extend(decode_errors)
    if errors:
        return {"decode_status": "failed", "errors": errors, "sample_count": len(samples)}
    write_pcm_wav(wav_path, samples, sample_rate, channels)
    return {"decode_status": "decoded_ps_adpcm_to_pcm_wav", "errors": [], "sample_count": len(samples), "duration_estimate": len(samples) / sample_rate}


def _base_report(source_path: Path, metadata: dict[str, Any] | None, guess: AudioGuess) -> dict[str, Any]:
    meta = metadata or {}
    return {"source_candidate": str(source_path), "source_iso_path": meta.get("source_iso_path") or meta.get("path") or str(source_path), "offset": meta.get("offset", guess.offset), "detected_format": guess.detected_format, "confidence": guess.confidence, "decode_status": "pending", "output_path": None, "raw_path": None, "sample_rate": guess.sample_rate, "channels": guess.channels, "duration_estimate": guess.duration_estimate, "warnings": list(guess.warnings), "errors": list(guess.errors), "next_action": guess.next_action, "audio_purpose": classify_audio_purpose(str(meta.get("source_iso_path") or meta.get("path") or source_path))}


def decode_audio_candidate(source_path: Path, out_root: Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    data = source_path.read_bytes()
    guess = identify_audio_format(data, str((metadata or {}).get("source_iso_path") or source_path))
    report = _base_report(source_path, metadata, guess)
    rel = _safe_rel(str((metadata or {}).get("source_iso_path") or source_path.name))
    stem = rel.with_suffix("")

    if guess.detected_format == "wav":
        out = out_root / "audio" / "wav" / rel.with_suffix(".wav")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, out)
        report.update({"decode_status": "copied_validated_wav", "output_path": str(out)})
    elif guess.detected_format == "vagp":
        info = guess.details
        payload = data[int(info["data_offset"]): int(info["data_offset"]) + int(info["data_size"])]
        samples = _decode_vag_blocks(payload)
        out = out_root / "audio" / "wav" / stem.with_suffix(".wav")
        write_pcm_wav(out, samples, int(info["sample_rate"]), 1)
        report.update({"decode_status": "decoded_vagp_to_pcm_wav", "output_path": str(out), "duration_estimate": (len(samples) / int(info["sample_rate"])) if info.get("sample_rate") else None})
    elif guess.detected_format == "midi":
        out = out_root / "audio" / "midi" / rel.with_suffix(".mid")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, out)
        report.update({"decode_status": "copied_midi", "output_path": str(out)})
    elif guess.detected_format in {"aiff", "aifc"}:
        out = out_root / "audio" / "aiff" / rel.with_suffix(".aifc" if guess.detected_format == "aifc" else ".aiff")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, out)
        report.update({"decode_status": "copied_container", "output_path": str(out)})
    else:
        raw = out_root / "audio" / "raw" / rel
        raw.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, raw)
        status = "identified_sound_bank_raw_only" if guess.detected_format == "vab_sound_bank" else "decode_pending_raw_only" if guess.detected_format == "cri_adx_like" else "raw_dumped_unknown_audio_like"
        report.update({"decode_status": status, "raw_path": str(raw)})
    return report

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ENCODINGS = ("u8", "s8", "s16le", "s16be")
CHANNELS = (1, 2)
SAMPLE_RATES = (8000, 11025, 16000, 22050, 24000, 32000, 37800, 44100, 48000)

OFFSET_TABLE_WIDTHS = (("u16le", 2, "little"), ("u16be", 2, "big"), ("u32le", 4, "little"), ("u32be", 4, "big"))
OFFSET_TABLE_SCALES = (1, 2, 4, 16, 0x800)

@dataclass(frozen=True)
class OffsetTableCandidate:
    kind: str
    offset: int
    entry_type: str
    entry_count: int
    table_size: int
    scale: int
    offsets: tuple[int, ...]
    score: float
    evidence: tuple[str, ...]

    @property
    def end_offset(self) -> int:
        return self.offset + self.table_size


def _read_uint(data: bytes, off: int, size: int, byteorder: str) -> int | None:
    if off < 0 or off + size > len(data):
        return None
    return int.from_bytes(data[off:off + size], byteorder, signed=False)


def _aligned(value: int, alignment: int = 2) -> bool:
    return value % alignment == 0


def _validate_offsets(offsets: list[int], data_size: int, table_end: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if len(offsets) < 2:
        reasons.append("fewer than two offsets")
    if any(o < table_end for o in offsets) or any(o >= data_size for o in offsets[:-1]) or offsets[-1] > data_size:
        reasons.append("offset outside payload range")
    if any(a >= b for a, b in zip(offsets, offsets[1:])):
        reasons.append("offsets are not strictly monotonic")
    if any(not _aligned(o, 2) for o in offsets):
        reasons.append("offsets are not 2-byte aligned")
    if offsets and offsets[-1] < data_size and data_size - offsets[-1] < 16:
        reasons.append("last region is too small")
    if any((b - a) < 16 for a, b in zip(offsets, offsets[1:])):
        reasons.append("region span is too small")
    return not reasons, reasons


def analyze_offset_tables(data: bytes, *, max_scan: int = 0x4000, max_entries: int = 512) -> list[dict]:
    """Find plausible count+offset-table and raw offset-table layouts."""
    candidates: list[OffsetTableCandidate] = []
    size = len(data)
    scan_limit = min(size, max_scan)
    for base in range(0, scan_limit):
        for entry_type, width, byteorder in OFFSET_TABLE_WIDTHS:
            count = _read_uint(data, base, width, byteorder)
            layouts = []
            if count and 2 <= count <= max_entries:
                layouts.append(("count_plus_table", base + width, int(count), width))
            # Table without count: infer lengths from first offset / entry width.
            first = _read_uint(data, base, width, byteorder)
            if first:
                for scale in OFFSET_TABLE_SCALES:
                    scaled_first = int(first) * scale
                    inferred = (scaled_first - base) // width
                    if 2 <= inferred <= max_entries:
                        layouts.append(("table", base, inferred, 0))
            for kind, table_start, entry_count, prefix in layouts:
                table_size = prefix + entry_count * width
                table_end = base + table_size
                if table_start + entry_count * width > size or table_end > size:
                    continue
                raw = [_read_uint(data, table_start + i * width, width, byteorder) for i in range(entry_count)]
                if any(v is None for v in raw):
                    continue
                for scale in OFFSET_TABLE_SCALES:
                    offsets = [int(v) * scale for v in raw if v is not None]
                    ok, reasons = _validate_offsets(offsets, size, table_end)
                    if not ok:
                        continue
                    evidence = [kind, entry_type, f"scale={scale}", "monotonic", "in-range", "aligned"]
                    span = offsets[-1] - offsets[0]
                    score = min(1.0, 0.35 + 0.1 * len(offsets) + 0.25 * min(span / max(size, 1), 1.0) + (0.1 if base <= 0x40 else 0.0) + (0.08 if kind == "count_plus_table" else 0.0))
                    candidates.append(OffsetTableCandidate(kind, base, entry_type, entry_count, table_size, scale, tuple(offsets), score, tuple(evidence)))
    uniq: dict[tuple, OffsetTableCandidate] = {}
    for c in candidates:
        key = (c.kind, c.offset, c.entry_type, c.scale, c.offsets)
        if key not in uniq or c.score > uniq[key].score:
            uniq[key] = c
    return [asdict(c) | {"end_offset": c.end_offset} for c in sorted(uniq.values(), key=lambda c: (-c.score, c.offset, c.entry_type))]


def rolling_audio_metrics(data: bytes, interp: RawInterpretation, *, window_ms: int = 50) -> list[dict]:
    channels = decode_pcm(data, interp)
    samples = _flatten(channels)
    win = max(1, int(interp.sample_rate * window_ms / 1000) * max(1, interp.channels))
    rows: list[dict] = []
    prev_rms: float | None = None
    for sample_start in range(0, len(samples), win):
        seg = samples[sample_start:sample_start + win]
        if not seg:
            continue
        mean = sum(seg) / len(seg)
        var = sum((v - mean) ** 2 for v in seg) / len(seg)
        rms = math.sqrt(sum(v * v for v in seg) / len(seg))
        rows.append({"sample_start": sample_start, "sample_end": sample_start + len(seg), "byte_start": interp.start_offset + sample_start * interp.bytes_per_sample, "rms": rms, "variance": var, "dc_offset": mean, "silence": rms <= 0.01, "energy_discontinuity": 0.0 if prev_rms is None else abs(rms - prev_rms)})
        prev_rms = rms
    return rows


def generate_region_map(data: bytes, interp: RawInterpretation | None = None, *, source: str | None = None) -> dict:
    tables = analyze_offset_tables(data)
    selected = tables[0] if tables else None
    if interp is None:
        start = (selected["end_offset"] if selected else 0)
        probes = probe_candidates(data, start, None, None)
        best = next((c for c in probes if not c.get("rejected")), probes[0] if probes else None)
        interp = RawInterpretation(**best["interpretation"]) if best else RawInterpretation("s16le", 1, 22050, start)
    metrics = rolling_audio_metrics(data, interp)
    bounds = list(selected["offsets"]) if selected else [interp.start_offset]
    if bounds[-1] < len(data):
        bounds.append(len(data))
    regions = []
    for i, (start, end) in enumerate(zip(bounds, bounds[1:])):
        if end <= start:
            continue
        duration = (end - start) / max(1, interp.frame_size * interp.sample_rate)
        near = [m for m in metrics if start <= m["byte_start"] < end]
        boundary_evidence = list(selected["evidence"]) if selected else ["rolling-energy"]
        if near and (near[0]["silence"] or near[-1]["silence"]):
            boundary_evidence.append("near-silence-boundary")
        if near and max(m["energy_discontinuity"] for m in near) > 0.08:
            boundary_evidence.append("energy-discontinuity")
        confidence = min(1.0, (selected["score"] if selected else 0.35) + (0.1 if "energy-discontinuity" in boundary_evidence else 0.0))
        regions.append({"region_id": f"region_{i:03d}", "start": start, "end": end, "size": end - start, "duration": duration, "boundary_evidence": boundary_evidence, "raw_interpretation": asdict(interp), "confidence": confidence})
    return {"source": source, "size": len(data), "selected_offset_table": selected, "offset_table_candidates": tables[:20], "rolling_metrics": metrics, "regions": regions}


def write_region_reports(data: bytes, source: Path, interp: RawInterpretation | None = None, out_dir: Path = Path("workspace/reports")) -> tuple[Path, Path, dict]:
    report = generate_region_map(data, interp, source=str(source))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem.lower()
    prefix = "bgm" if "bgm" in stem else "food" if "food" in stem else stem
    json_path = out_dir / f"{prefix}_region_map.json"
    txt_path = out_dir / f"{prefix}_region_map.txt"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    lines = [f"Region map: {source}", f"regions: {len(report['regions'])}", ""]
    for r in report["regions"]:
        lines.append(f"{r['region_id']} start={r['start']} end={r['end']} size={r['size']} duration={r['duration']:.3f}s confidence={r['confidence']:.2f} evidence={','.join(r['boundary_evidence'])}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, txt_path, report

ENCODING_LABELS = {
    "u8": "unsigned 8-bit PCM",
    "s8": "signed 8-bit PCM",
    "s16le": "signed 16-bit LE PCM",
    "s16be": "signed 16-bit BE PCM",
}

@dataclass(frozen=True)
class RawInterpretation:
    encoding: str
    channels: int
    sample_rate: int
    start_offset: int = 0
    length: int | None = None
    end_offset: int | None = None

    @property
    def bytes_per_sample(self) -> int:
        return 1 if self.encoding in {"u8", "s8"} else 2

    @property
    def frame_size(self) -> int:
        return self.bytes_per_sample * self.channels


def _slice(data: bytes, start_offset: int = 0, length: int | None = None, end_offset: int | None = None) -> bytes:
    start = max(0, int(start_offset or 0))
    end = len(data) if end_offset in (None, "") else max(start, min(len(data), int(end_offset)))
    if length not in (None, ""):
        end = min(end, start + max(0, int(length)))
    return data[start:end]


def decode_pcm(data: bytes, interp: RawInterpretation) -> list[list[float]]:
    chunk = _slice(data, interp.start_offset, interp.length, interp.end_offset)
    usable = len(chunk) - (len(chunk) % interp.frame_size)
    chunk = chunk[:usable]
    channels = [[] for _ in range(interp.channels)]
    step = interp.bytes_per_sample
    for frame in range(0, len(chunk), interp.frame_size):
        for ch in range(interp.channels):
            off = frame + ch * step
            if interp.encoding == "u8":
                value = (chunk[off] - 128) / 128.0
            elif interp.encoding == "s8":
                b = chunk[off]
                value = (b - 256 if b > 127 else b) / 128.0
            elif interp.encoding == "s16le":
                value = int.from_bytes(chunk[off:off+2], "little", signed=True) / 32768.0
            elif interp.encoding == "s16be":
                value = int.from_bytes(chunk[off:off+2], "big", signed=True) / 32768.0
            else:
                raise ValueError(f"unsupported encoding: {interp.encoding}")
            channels[ch].append(max(-1.0, min(1.0, value)))
    return channels


def _flatten(channels: list[list[float]]) -> list[float]:
    return [v for ch in channels for v in ch]


def _zero_crossing_rate(samples: list[float]) -> float:
    if len(samples) < 2:
        return 0.0
    crossings = 0
    prev = samples[0]
    for cur in samples[1:]:
        if (prev < 0 <= cur) or (prev >= 0 > cur):
            crossings += 1
        if cur != 0:
            prev = cur
    return crossings / (len(samples) - 1)


def _near_silence_windows(samples: list[float], sample_rate: int, threshold: float = 0.01, window_ms: int = 50) -> list[dict]:
    win = max(1, int(sample_rate * window_ms / 1000))
    out = []
    for start in range(0, len(samples), win):
        seg = samples[start:start+win]
        if seg and math.sqrt(sum(v*v for v in seg) / len(seg)) <= threshold:
            out.append({"start_sample": start, "end_sample": start + len(seg), "duration_seconds": len(seg) / sample_rate})
    return out


def _long_constant_runs(samples: list[float], min_run: int = 128) -> list[dict]:
    out = []
    if not samples:
        return out
    start = 0
    prev = samples[0]
    for i, cur in enumerate(samples[1:], 1):
        if cur != prev:
            if i - start >= min_run:
                out.append({"start_sample": start, "end_sample": i, "length": i - start, "value": prev})
            start = i
            prev = cur
    if len(samples) - start >= min_run:
        out.append({"start_sample": start, "end_sample": len(samples), "length": len(samples) - start, "value": prev})
    return out


def _stereo_correlation(channels: list[list[float]]) -> float | None:
    if len(channels) != 2 or not channels[0] or not channels[1]:
        return None
    n = min(len(channels[0]), len(channels[1]))
    a, b = channels[0][:n], channels[1][:n]
    ma, mb = sum(a)/n, sum(b)/n
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x-ma)**2 for x in a)); db = math.sqrt(sum((y-mb)**2 for y in b))
    return None if da == 0 or db == 0 else num / (da * db)


def analyze_raw_audio(data: bytes, interp: RawInterpretation) -> dict:
    channels = decode_pcm(data, interp)
    samples = _flatten(channels)
    if not samples:
        metrics = {"sample_count": 0, "min": None, "max": None, "mean": None, "dc_offset": None, "rms": 0.0, "zero_crossing_rate": 0.0, "clipping_percentage": 0.0, "dynamic_range": 0.0, "near_silence_windows": [], "long_constant_runs": [], "stereo_correlation": None}
    else:
        mean = sum(samples) / len(samples)
        rms = math.sqrt(sum(v*v for v in samples) / len(samples))
        mn, mx = min(samples), max(samples)
        clips = sum(1 for v in samples if abs(v) >= 0.999)
        metrics = {"sample_count": len(samples), "duration_seconds": len(channels[0]) / interp.sample_rate if channels and channels[0] else 0.0, "min": mn, "max": mx, "mean": mean, "dc_offset": mean, "rms": rms, "zero_crossing_rate": _zero_crossing_rate(samples), "clipping_percentage": clips * 100.0 / len(samples), "dynamic_range": mx - mn, "near_silence_windows": _near_silence_windows(samples, interp.sample_rate), "long_constant_runs": _long_constant_runs(samples), "stereo_correlation": _stereo_correlation(channels)}
    rejected, reasons = is_degenerate(metrics)
    score = _score(metrics, rejected)
    return {"kind": "raw_interpretation_candidate", "interpretation": asdict(interp), "encoding_label": ENCODING_LABELS[interp.encoding], "metrics": metrics, "score": score, "rejected": rejected, "reject_reasons": reasons}


def is_degenerate(metrics: dict) -> tuple[bool, list[str]]:
    reasons = []
    if metrics.get("sample_count", 0) < 128: reasons.append("too few samples")
    if (metrics.get("dynamic_range") or 0) < 0.02: reasons.append("very low dynamic range")
    if (metrics.get("rms") or 0) < 0.005: reasons.append("near silent")
    if abs(metrics.get("dc_offset") or 0) > 0.75: reasons.append("large DC offset")
    if (metrics.get("clipping_percentage") or 0) > 35: reasons.append("excessive clipping")
    if metrics.get("long_constant_runs") and max(r["length"] for r in metrics["long_constant_runs"]) > max(256, metrics.get("sample_count", 0) * 0.25): reasons.append("long constant run")
    return bool(reasons), reasons


def _score(metrics: dict, rejected: bool) -> float:
    if rejected: return 0.0
    zcr = metrics.get("zero_crossing_rate") or 0
    rms = metrics.get("rms") or 0
    dr = metrics.get("dynamic_range") or 0
    dc = abs(metrics.get("dc_offset") or 0)
    clip = metrics.get("clipping_percentage") or 0
    return max(0.0, min(1.0, 0.35*min(dr/1.2,1)+0.30*min(rms/0.35,1)+0.20*(1-min(abs(zcr-0.12)/0.12,1))+0.15*(1-min(dc/0.35,1))-min(clip/100,0.25)))


def probe_candidates(data: bytes, start_offset: int = 0, length: int | None = None, end_offset: int | None = None) -> list[dict]:
    candidates = [analyze_raw_audio(data, RawInterpretation(e, c, r, start_offset, length, end_offset)) for e in ENCODINGS for c in CHANNELS for r in SAMPLE_RATES]
    return sorted(candidates, key=lambda row: (row["rejected"], -row["score"], row["interpretation"]["encoding"], row["interpretation"]["channels"], row["interpretation"]["sample_rate"]))


def export_wav(data: bytes, interp: RawInterpretation, out_path: Path) -> None:
    channels = decode_pcm(data, interp)
    n = min((len(ch) for ch in channels), default=0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(interp.channels); wf.setsampwidth(2); wf.setframerate(interp.sample_rate)
        frames = bytearray()
        for i in range(n):
            for ch in range(interp.channels):
                frames.extend(int(max(-1, min(1, channels[ch][i])) * 32767).to_bytes(2, "little", signed=True))
        wf.writeframes(bytes(frames))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Probe headerless/raw PCM audio interpretations.")
    p.add_argument("source", type=Path); p.add_argument("--encoding", choices=ENCODINGS); p.add_argument("--channels", type=int, choices=CHANNELS); p.add_argument("--sample-rate", type=int, choices=SAMPLE_RATES)
    p.add_argument("--start-offset", type=int, default=0); p.add_argument("--length", type=int); p.add_argument("--end-offset", type=int); p.add_argument("--export-wav", type=Path); p.add_argument("--json", type=Path); p.add_argument("--region-map", action="store_true"); p.add_argument("--reports-dir", type=Path, default=Path("workspace/reports"))
    ns = p.parse_args(argv); data = ns.source.read_bytes()
    if ns.region_map:
        interp = RawInterpretation(ns.encoding, ns.channels, ns.sample_rate, ns.start_offset, ns.length, ns.end_offset) if ns.encoding and ns.channels and ns.sample_rate else None
        json_path, txt_path, result = write_region_reports(data, ns.source, interp, ns.reports_dir)
        result = result | {"json_path": str(json_path), "text_path": str(txt_path)}
    elif ns.encoding and ns.channels and ns.sample_rate:
        result = analyze_raw_audio(data, RawInterpretation(ns.encoding, ns.channels, ns.sample_rate, ns.start_offset, ns.length, ns.end_offset))
        if ns.export_wav: export_wav(data, RawInterpretation(ns.encoding, ns.channels, ns.sample_rate, ns.start_offset, ns.length, ns.end_offset), ns.export_wav)
    else:
        result = {"source": str(ns.source), "candidates": probe_candidates(data, ns.start_offset, ns.length, ns.end_offset)[:20]}
    text = json.dumps(result, indent=2)
    if ns.json: ns.json.write_text(text, encoding="utf-8")
    print(text); return 0
if __name__ == "__main__": raise SystemExit(main())

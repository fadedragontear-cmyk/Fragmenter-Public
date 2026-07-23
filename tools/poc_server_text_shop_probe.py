#!/usr/bin/env python3
"""Scan and exact-length patch Area Server text candidates.

The scanner is intentionally conservative: it reports byte-exact string
candidates and context only. Patch mode only performs exact-length replacements
against either raw file bytes or a selected padded gzip member slot.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import struct
import zlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable

MIN_TEXT_LEN = 3
RANK_TERMS = (
    "shop", "merchant", "gate", "chaos", "item", "weapon", "armor", "magic",
    "save", "npc", "event", "talk", "buy", "sell",
)
ASCII_PRINTABLE = set(range(0x20, 0x7F))
PADDING = {0x00, 0x20}
CP932_CANDIDATE_DELIMITERS = set(range(0x00, 0x20)) | {0x7F}
CP932_CANDIDATE_MAX_RUN_BYTES = 512
CP932_CANDIDATE_CLEANUP_BYTES = 4
QUICK_FILES = (
    "data/text.bin",
    "data/event.bin",
    "data/menu.bin",
    "data/OnlineEvent.dat",
    "data/town.bin",
)
DEFAULT_MAX_BYTES_PER_FILE = 8_000_000
DEFAULT_MAX_STRINGS_PER_FILE = 1_000
DEFAULT_MAX_MEMBERS = 100
NOISY_RESOURCE_PREFIXES = (
    "TEX_", "MAT_", "MDL_", "OBJ_", "DMY_", "ANM_", "LGT_", "CLT_", "BLT_", "CMP_", "HIT_", "CCSF",
)
ASSET_EXTENSIONS = (".max", ".bmp", ".tm2")
RESOURCEISH_LABEL_RE = re.compile(r"^[A-Z]{2,6}_[A-Za-z0-9_]*\d*[A-Za-z0-9_]*$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")
SENTENCE_PUNCTUATION = (".", ",", "!", "?", "。", "、", "！", "？")
PRIORITY_TEXT_FILES = (
    "data/text.bin",
    "data/OnlineEvent.dat",
    "data/event.bin",
)
DEFAULT_NEARBY_SENTENCE_WINDOW_BYTES = 256


@dataclass
class GzipHeader:
    flags: int
    mtime: int
    os_byte: int
    original_filename: str | None
    has_extra: bool
    has_name: bool
    has_comment: bool
    has_header_crc: bool
    header_end: int


@dataclass
class PaddingRange:
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass
class GzipMember:
    index: int
    raw_start: int
    raw_end: int
    raw: bytes
    decompressed: bytes
    header: GzipHeader | None
    trailer_crc32: int | None
    trailer_isize: int | None
    full_decompressed_start: int
    next_member_start: int
    slot_end: int
    slot_size: int
    padding_after_size: int
    padding_before: PaddingRange | None = None
    padding_after: PaddingRange | None = None

    @property
    def raw_size(self) -> int:
        return self.raw_end - self.raw_start


def sha1_hex(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()


def parse_gzip_header(raw: bytes, base_offset: int) -> GzipHeader | None:
    if len(raw) < 10 or raw[:2] != b"\x1f\x8b" or raw[2] != 8:
        return None
    flags = raw[3]
    mtime = struct.unpack_from("<I", raw, 4)[0]
    os_byte = raw[9]
    pos = 10
    original_filename = None
    try:
        if flags & 0x04:
            xlen = struct.unpack_from("<H", raw, pos)[0]
            pos += 2 + xlen
        if flags & 0x08:
            end = raw.index(0, pos)
            original_filename = raw[pos:end].decode("latin-1")
            pos = end + 1
        if flags & 0x10:
            end = raw.index(0, pos)
            pos = end + 1
        if flags & 0x02:
            pos += 2
    except (ValueError, struct.error):
        return None
    if pos > len(raw):
        return None
    return GzipHeader(flags, mtime, os_byte, original_filename, bool(flags & 4), bool(flags & 8), bool(flags & 16), bool(flags & 2), base_offset + pos)


def parse_gzip_members(raw: bytes) -> list[GzipMember]:
    members: list[GzipMember] = []
    raw_offset = 0
    full_dec_offset = 0
    previous_member: GzipMember | None = None
    previous_slot_end = 0
    while raw_offset < len(raw):
        candidate_start = raw.find(b"\x1f\x8b", raw_offset)
        if candidate_start == -1:
            break
        obj = zlib.decompressobj(wbits=31)
        try:
            decompressed = obj.decompress(raw[candidate_start:])
            obj.flush()
        except zlib.error:
            raw_offset = candidate_start + 1
            continue
        if not obj.eof:
            raw_offset = candidate_start + 1
            continue
        consumed = len(raw) - candidate_start - len(obj.unused_data)
        if consumed <= 0:
            raw_offset = candidate_start + 1
            continue
        raw_end = candidate_start + consumed
        padding_before = PaddingRange(previous_slot_end, candidate_start) if candidate_start > previous_slot_end else None
        if previous_member is not None:
            previous_member.next_member_start = candidate_start
            previous_member.slot_end = candidate_start
            previous_member.slot_size = candidate_start - previous_member.raw_start
            previous_member.padding_after_size = candidate_start - previous_member.raw_end
            if previous_member.padding_after_size > 0:
                previous_member.padding_after = PaddingRange(previous_member.raw_end, candidate_start)
        member_raw = raw[candidate_start:raw_end]
        trailer_crc = trailer_isize = None
        if len(member_raw) >= 8:
            trailer_crc, trailer_isize = struct.unpack("<II", member_raw[-8:])
        member = GzipMember(len(members), candidate_start, raw_end, member_raw, decompressed,
                            parse_gzip_header(member_raw, candidate_start), trailer_crc, trailer_isize,
                            full_dec_offset, len(raw), len(raw), len(raw) - candidate_start,
                            len(raw) - raw_end, padding_before)
        members.append(member)
        previous_member = member
        previous_slot_end = raw_end
        raw_offset = raw_end
        full_dec_offset += len(decompressed)
    if previous_member is not None:
        previous_member.next_member_start = len(raw)
        previous_member.slot_end = len(raw)
        previous_member.slot_size = len(raw) - previous_member.raw_start
        previous_member.padding_after_size = len(raw) - previous_member.raw_end
        if previous_member.padding_after_size > 0:
            previous_member.padding_after = PaddingRange(previous_member.raw_end, len(raw))
    return members


def member_name(member: GzipMember) -> str:
    return member.header.original_filename if member.header and member.header.original_filename is not None else "unavailable"


def gzip_recompress_with_metadata(payload: bytes, member: GzipMember) -> bytes:
    mtime = member.header.mtime if member.header else None
    filename = member.header.original_filename if member.header and member.header.original_filename else ""
    out = BytesIO()
    with gzip.GzipFile(filename=filename, mode="wb", fileobj=out, mtime=mtime) as gz:
        gz.write(payload)
    return out.getvalue()


def build_slot_payload(raw: bytes, member: GzipMember, recompressed: bytes) -> bytes:
    if len(recompressed) > member.slot_size:
        raise SystemExit(f"Recompressed selected member does not fit in its slot ({len(recompressed)} > {member.slot_size}); output not written")
    remainder_size = member.slot_size - len(recompressed)
    original_padding = raw[member.raw_end:member.slot_end]
    if remainder_size == len(original_padding):
        return recompressed + original_padding
    if remainder_size == 0:
        return recompressed
    if original_padding and all(byte == 0 for byte in original_padding):
        return recompressed + (b"\x00" * remainder_size)
    if not original_padding:
        raise SystemExit("Recompressed member is smaller, but the original slot had no padding layout to preserve; output not written")
    raise SystemExit("Recompressed member changes non-zero/non-uniform padding layout; output not written")


def parse_file_allowlist(root: Path, files_arg: str) -> list[Path]:
    files: list[Path] = []
    for item in files_arg.split(","):
        name = item.strip().replace("\\", "/")
        if not name:
            continue
        path = Path(name)
        files.append(path if path.is_absolute() else root / path)
    return files


def normalize_scan_path(path: Path) -> Path:
    return path.resolve(strict=False)


def target_files(root: Path, args: argparse.Namespace) -> list[Path]:
    if args.files:
        files = parse_file_allowlist(root, args.files)
    elif args.quick:
        files = [root / rel for rel in QUICK_FILES]
    else:
        data = root / "data"
        files = []
        for pat in ("*.bin", "*.dat"):
            files.extend(sorted(data.glob(pat)))
    exe = normalize_scan_path(root / "AREA SERVER.exe")
    normalized_files = [normalize_scan_path(p) for p in files]
    if args.include_exe and exe not in normalized_files:
        normalized_files.insert(0, exe)
    seen: set[Path] = set()
    out: list[Path] = []
    for p in normalized_files:
        if p.is_file() and p not in seen:
            seen.add(p)
            out.append(p)
        elif not p.is_file():
            print(f"Skipping missing file: {p}", flush=True)
    return out


def clean_context(blob: bytes, max_context_bytes: int = 64) -> str:
    if max_context_bytes < 0:
        max_context_bytes = 0
    bounded = blob[:max_context_bytes]
    text = bounded.decode("cp932", errors="replace")
    return CONTROL_CHARS_RE.sub(".", text)


def nearby_hex(blob: bytes, start: int, end: int, radius: int = 32) -> str:
    return blob[max(0, start - radius):min(len(blob), end + radius)].hex(" ")


def has_japanese(text: str) -> bool:
    return any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in text)


def normalized_path_text(file_path: Path | str) -> str:
    return str(file_path).replace("\\", "/")


def is_priority_text_file(file_path: Path | str) -> str | None:
    path_text = normalized_path_text(file_path)
    for suffix in PRIORITY_TEXT_FILES:
        if path_text.endswith(suffix):
            return Path(suffix).name
    return None


def starts_with_resource_prefix(text: str) -> bool:
    return text.strip().upper().startswith(NOISY_RESOURCE_PREFIXES)


def mostly_uppercase_underscore_digits(text: str) -> bool:
    meaningful_chars = [ch for ch in text.strip() if not ch.isspace()]
    if not meaningful_chars:
        return False
    resourceish_count = sum(ch.isupper() or ch.isdigit() or ch == "_" for ch in meaningful_chars)
    return resourceish_count / len(meaningful_chars) >= 0.75


def is_all_caps_asset_style_identifier(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped and mostly_uppercase_underscore_digits(stripped) and ("_" in stripped or stripped.isupper()))


def is_sentence_like(text: str) -> bool:
    return bool(text.strip()) and (has_japanese(text) or any(punct in text for punct in SENTENCE_PUNCTUATION))


def rank_candidate(
    text: str,
    context: str,
    file_path: Path | str,
    source: str | None = None,
    member_index: int | None = None,
    nearby_candidates: Iterable[dict] | None = None,
) -> tuple[int, list[str]]:
    hay = f"{text} {context}".lower()
    score = 0
    reasons: list[str] = []
    for term in RANK_TERMS:
        if term in hay:
            score += 10
            reasons.append(f"keyword:{term}")
    if has_japanese(text):
        score += 18
        reasons.append("japanese-text")
    elif has_japanese(context):
        score += 8
        reasons.append("japanese-context")
    if " " in text:
        score += 5
        reasons.append("contains-spaces")
    if any(punct in text for punct in SENTENCE_PUNCTUATION):
        score += 8
        reasons.append("sentence-punctuation")
    priority_name = is_priority_text_file(file_path)
    if priority_name is not None:
        score += 12
        reasons.append(f"priority-file:{priority_name}")
    if len(text) >= 8:
        score += 2
        reasons.append("length>=8")

    if looks_like_asset_identifier(text, include_assets=False):
        score -= 15
        reasons.append("penalty:asset-identifier")
    if "/" in text or "\\" in text:
        score -= 8
        reasons.append("penalty:path-separator")
    if starts_with_resource_prefix(text):
        score -= 12
        reasons.append("penalty:asset-prefix")
    if mostly_uppercase_underscore_digits(text):
        score -= 8
        reasons.append("penalty:mostly-uppercase-underscore-digits")
    if is_all_caps_asset_style_identifier(text):
        score -= 6
        reasons.append("penalty:all-caps-asset-style")
    return score, reasons


def boost_nearby_sentence_like_candidates(candidates: list[dict], window_bytes: int) -> None:
    if window_bytes <= 0:
        return
    grouped: dict[tuple[str, str, int | None], list[dict]] = {}
    for candidate in candidates:
        key = (candidate.get("file_path", ""), candidate.get("source", ""), candidate.get("member_index"))
        grouped.setdefault(key, []).append(candidate)
    for group in grouped.values():
        group.sort(key=lambda candidate: candidate.get("offset", 0))
        sentence_like_indexes = [
            index for index, candidate in enumerate(group)
            if is_sentence_like(candidate.get("decoded_text", ""))
        ]
        boosted: set[int] = set()
        for left, right in zip(sentence_like_indexes, sentence_like_indexes[1:]):
            left_candidate = group[left]
            right_candidate = group[right]
            if right_candidate.get("offset", 0) - left_candidate.get("offset", 0) <= window_bytes:
                boosted.add(left)
                boosted.add(right)
        for index in boosted:
            candidate = group[index]
            reasons = candidate.setdefault("rank_reasons", [])
            if "nearby-sentence-like-string" not in reasons:
                candidate["rank"] = candidate.get("rank", 0) + 6
                reasons.append("nearby-sentence-like-string")


def add_candidate(out: list[dict], file_path: Path, source: str, blob: bytes, start: int, end: int, text: str, enc: str, member: GzipMember | None = None, max_context_bytes: int = 64, focus: str | None = None, only_visible_text: bool = False, include_assets: bool = False) -> None:
    text = text.strip("\x00 ")
    if len(text) < MIN_TEXT_LEN:
        return
    visible_text_only = only_visible_text or focus == "shop"
    if visible_text_only and looks_like_asset_identifier(text, include_assets=include_assets):
        return
    radius = max(0, max_context_bytes // 2)
    ctx_bytes = blob[max(0, start - radius):min(len(blob), end + radius)]
    context = clean_context(ctx_bytes, max_context_bytes)
    rank, reasons = rank_candidate(text, context, file_path, source, member.index if member else None)
    out.append({
        "file_path": str(file_path), "source": source,
        "member_index": member.index if member else None, "member_name": member_name(member) if member else None,
        "offset": start, "byte_length": end - start, "decoded_text": text, "encoding_guess": enc,
        "nearby_printable_context": context, "nearby_hex": nearby_hex(blob, start, end),
        "rank": rank, "rank_reasons": reasons,
        "safe_replacement_constraints": {
            "exact_byte_length_required": end - start,
            "ascii_only_replacement_safe": all(ord(ch) < 128 for ch in text),
            "cp932_replacement_possible": True,
        },
    })


def ascii_runs(blob: bytes) -> Iterable[tuple[int, int]]:
    i = 0
    while i < len(blob):
        if blob[i] in ASCII_PRINTABLE:
            s = i
            while i < len(blob) and blob[i] in ASCII_PRINTABLE:
                i += 1
            if i - s >= MIN_TEXT_LEN:
                yield s, i
        i += 1


def is_noisy_resource_name(text: str) -> bool:
    return looks_like_asset_identifier(text, include_assets=False)


def looks_like_asset_identifier(text: str, include_assets: bool = False) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    upper = stripped.upper()
    if any(upper.startswith(prefix) for prefix in NOISY_RESOURCE_PREFIXES):
        return True
    lower = stripped.lower()
    if any(ext in lower for ext in ASSET_EXTENSIONS):
        return True
    if not include_assets and "\\" in stripped:
        return True

    resource_chars = sum(ch.isupper() or ch.isdigit() or ch == "_" for ch in stripped)
    meaningful_chars = sum(not ch.isspace() for ch in stripped)
    if meaningful_chars and resource_chars / meaningful_chars >= 0.75 and "_" in stripped:
        return True
    if RESOURCEISH_LABEL_RE.fullmatch(stripped):
        return True
    return False


def is_cp932_lead_byte(byte: int) -> bool:
    return 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC


def printable_text_len(text: str) -> int:
    return sum(1 for ch in text if ch.isprintable())


def cp932_candidate_runs(blob: bytes) -> Iterable[tuple[int, int, str]]:
    """Yield bounded CP932 candidates without brute-forcing every byte offset."""
    i = 0
    while i < len(blob):
        while i < len(blob) and blob[i] in CP932_CANDIDATE_DELIMITERS:
            i += 1
        segment_start = i
        while i < len(blob) and blob[i] not in CP932_CANDIDATE_DELIMITERS:
            i += 1
        segment_end = i
        chunk_start = segment_start
        while chunk_start < segment_end:
            chunk_end = min(segment_end, chunk_start + CP932_CANDIDATE_MAX_RUN_BYTES)
            if chunk_end < segment_end and is_cp932_lead_byte(blob[chunk_end - 1]):
                chunk_end -= 1
            if chunk_end <= chunk_start:
                chunk_end = min(segment_end, chunk_start + CP932_CANDIDATE_MAX_RUN_BYTES)
            stripped_start = chunk_start
            stripped_end = chunk_end
            while stripped_start < stripped_end and blob[stripped_start] in PADDING:
                stripped_start += 1
            while stripped_end > stripped_start and blob[stripped_end - 1] in PADDING:
                stripped_end -= 1
            if stripped_end > stripped_start:
                text = None
                decoded_end = stripped_end
                for trim in range(0, min(CP932_CANDIDATE_CLEANUP_BYTES, stripped_end - stripped_start) + 1):
                    try:
                        decoded_end = stripped_end - trim
                        text = blob[stripped_start:decoded_end].decode("cp932")
                        break
                    except UnicodeDecodeError:
                        continue
                if text is not None and printable_text_len(text) >= MIN_TEXT_LEN and all(ch.isprintable() for ch in text):
                    yield stripped_start, decoded_end, text
            chunk_start = chunk_end


def cp932_runs(blob: bytes) -> Iterable[tuple[int, int, str]]:
    i = 0
    while i < len(blob):
        best_end = i
        best_text = ""
        j = i
        while j < len(blob) and blob[j] not in PADDING:
            try:
                text = blob[i:j + 1].decode("cp932")
            except UnicodeDecodeError:
                break
            if all(ch.isprintable() for ch in text):
                best_end, best_text = j + 1, text
            j += 1
        if len(best_text) >= MIN_TEXT_LEN and best_end > i:
            yield i, best_end, best_text
            i = best_end
        else:
            i += 1


def scan_blob(file_path: Path, source: str, blob: bytes, member: GzipMember | None = None, *, max_strings: int | None = None, max_context_bytes: int = 64, cp932_candidates_only: bool = False, cp932_deep_scan: bool = False, focus: str | None = None, only_visible_text: bool = False, include_assets: bool = False) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[int, int, str]] = set()
    for s, e in ascii_runs(blob):
        key = (s, e, "ascii")
        if key not in seen:
            seen.add(key); add_candidate(found, file_path, source, blob, s, e, blob[s:e].decode("ascii"), "ascii", member, max_context_bytes, focus, only_visible_text, include_assets)
            if max_strings is not None and len(found) >= max_strings:
                print(f"Limit reached for {file_path} {source}: max strings {max_strings}", flush=True)
                return found
        # fixed-width padded / null-terminated variants share the same meaningful span.
        if e < len(blob) and blob[e] in PADDING:
            add_candidate(found, file_path, source, blob, s, e + 1, blob[s:e].decode("ascii"), "ascii-padded-or-null", member, max_context_bytes, focus, only_visible_text, include_assets)
            if max_strings is not None and len(found) >= max_strings:
                print(f"Limit reached for {file_path} {source}: max strings {max_strings}", flush=True)
                return found
    if cp932_candidates_only:
        cp932_iter = cp932_candidate_runs(blob)
    elif cp932_deep_scan:
        cp932_iter = cp932_runs(blob)
    else:
        return found
    for s, e, text in cp932_iter:
        key = (s, e, "cp932")
        if key not in seen:
            seen.add(key); add_candidate(found, file_path, source, blob, s, e, text, "cp932", member, max_context_bytes, focus, only_visible_text, include_assets)
            if max_strings is not None and len(found) >= max_strings:
                print(f"Limit reached for {file_path} {source}: max strings {max_strings}", flush=True)
                return found
        if e < len(blob) and blob[e] in PADDING:
            add_candidate(found, file_path, source, blob, s, e + 1, text, "cp932-padded-or-null", member, max_context_bytes, focus, only_visible_text, include_assets)
            if max_strings is not None and len(found) >= max_strings:
                print(f"Limit reached for {file_path} {source}: max strings {max_strings}", flush=True)
                return found
    return found


def summarize(candidates: list[dict]) -> dict:
    sections = {"likely_dialogue_strings": [], "likely_npc_merchant_labels": [], "likely_shop_menu_labels": [], "likely_event_strings": [], "likely_item_shop_table_neighborhoods": []}
    for c in sorted(candidates, key=lambda x: (-x["rank"], x["file_path"], x["offset"])):
        hay = f'{c["decoded_text"]} {c["nearby_printable_context"]}'.lower()
        slim = {k: c[k] for k in ("file_path", "source", "member_index", "member_name", "offset", "byte_length", "decoded_text", "encoding_guess", "rank", "rank_reasons")}
        if any(t in hay for t in ("talk", "dialog", "message")) or has_japanese(c["decoded_text"]):
            sections["likely_dialogue_strings"].append(slim)
        if any(t in hay for t in ("npc", "merchant")):
            sections["likely_npc_merchant_labels"].append(slim)
        if any(t in hay for t in ("shop", "buy", "sell")):
            sections["likely_shop_menu_labels"].append(slim)
        if "event" in hay or "gate" in hay or "chaos" in hay:
            sections["likely_event_strings"].append(slim)
        if any(t in hay for t in ("item", "weapon", "armor", "magic", "shop", "buy", "sell")):
            sections["likely_item_shop_table_neighborhoods"].append({k: c[k] for k in ("file_path", "source", "member_index", "member_name", "offset", "byte_length", "nearby_printable_context", "nearby_hex", "rank", "rank_reasons")})
    return {k: v[:200] for k, v in sections.items()}


def truncate_for_scan(blob: bytes, limit: int | None, label: str) -> bytes:
    if limit is not None and limit >= 0 and len(blob) > limit:
        print(f"Limit reached for {label}: max bytes {limit} of {len(blob)}", flush=True)
        return blob[:limit]
    return blob


def candidate_sort_key(candidate: dict) -> tuple:
    member_index = candidate.get("member_index")
    safe_member_index = -1 if member_index is None else member_index
    return (
        -candidate.get("rank", 0),
        candidate.get("file_path", ""),
        candidate.get("source", ""),
        safe_member_index,
        candidate.get("offset", 0),
    )


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected true or false, got {value!r}")


def effective_rank_threshold(args: argparse.Namespace) -> int | None:
    thresholds = [value for value in (args.min_rank, args.exclude_rank_below) if value is not None]
    return max(thresholds) if thresholds else None


def filter_candidates_by_rank(candidates: list[dict], threshold: int | None) -> list[dict]:
    if threshold is None:
        return candidates
    return [candidate for candidate in candidates if candidate["rank"] >= threshold]


def filter_candidates_by_visible_text(candidates: list[dict], args: argparse.Namespace) -> list[dict]:
    visible_text_only = args.only_visible_text or args.focus == "shop"
    if not visible_text_only:
        return candidates
    return [
        candidate for candidate in candidates
        if not looks_like_asset_identifier(candidate.get("decoded_text", ""), include_assets=args.include_assets)
    ]


def finalize_candidates(candidates: list[dict], args: argparse.Namespace) -> list[dict]:
    finalized = filter_candidates_by_visible_text(candidates, args)
    boost_nearby_sentence_like_candidates(finalized, args.nearby_sentence_window_bytes)
    finalized = filter_candidates_by_rank(finalized, effective_rank_threshold(args))
    return sorted(finalized, key=candidate_sort_key)


def build_report(root: Path, files: list[Path], member_summaries: list[dict], candidates: list[dict], rank_threshold: int | None = None, nearby_sentence_window_bytes: int = DEFAULT_NEARBY_SENTENCE_WINDOW_BYTES) -> dict:
    return {
        "server_root": str(root),
        "scan_options": {
            "rank_threshold": rank_threshold,
            "nearby_sentence_window_bytes": nearby_sentence_window_bytes,
        },
        "files_scanned": [str(p) for p in files],
        "gzip_members": member_summaries,
        "candidate_count": len(candidates),
        "sections": summarize(candidates),
        "candidates": sorted(candidates, key=candidate_sort_key),
    }


def write_report(args: argparse.Namespace, root: Path, files: list[Path], member_summaries: list[dict], candidates: list[dict]) -> None:
    report = build_report(root, files, member_summaries, candidates, effective_rank_threshold(args), args.nearby_sentence_window_bytes)
    report["candidates"] = sorted(report["candidates"], key=candidate_sort_key)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    txt = args.out.with_suffix(".txt")
    lines = ["Area Server text/shop probe", f"server_root: {root}", f"files_scanned: {len(files)}", f"candidate_count: {len(candidates)}", ""]
    dump_top = max(args.dump_top, 0)
    summary_only = args.summary_only if args.summary_only is not None else dump_top <= 0
    if summary_only:
        for name, entries in report["sections"].items():
            lines.append(name.replace("_", " ").title())
            for e in entries[:50]:
                lines.append(f"- {e['file_path']} {e['source']} member={e.get('member_index')} off={e['offset']} len={e['byte_length']} rank={e['rank']} text={e.get('decoded_text', '<context-only>')!r}")
            lines.append("")
    if dump_top > 0:
        lines.append(f"Detailed Candidates (top {dump_top} per file/member)")
        counts_by_group: dict[tuple[str, str, int | None, str | None], int] = {}
        for c in report["candidates"]:
            group_key = (c.get("file_path", ""), c.get("source", ""), c.get("member_index"), c.get("member_name"))
            if counts_by_group.get(group_key, 0) >= dump_top:
                continue
            counts_by_group[group_key] = counts_by_group.get(group_key, 0) + 1
            member = f"{c.get('member_index')}:{c.get('member_name')}"
            lines.append(
                f"file={c.get('file_path')}\t"
                f"source={c.get('source')}\t"
                f"member={member}\t"
                f"off={c.get('offset')}\t"
                f"len={c.get('byte_length')}\t"
                f"enc={c.get('encoding_guess')}\t"
                f"rank={c.get('rank')}\t"
                f"text={c.get('decoded_text')!r}\t"
                f"context={c.get('nearby_printable_context')!r}"
            )
        lines.append("")
    txt.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote JSON: {args.out}", flush=True)
    print(f"Wrote TXT: {txt}", flush=True)


def run_scan(args: argparse.Namespace) -> int:
    root = args.server_root
    candidates: list[dict] = []
    files = target_files(root, args)
    member_summaries: list[dict] = []
    cp932_deep_scan = not args.no_cp932_deep_scan
    try:
        for path in files:
            print(f"Scanning file: {path}", flush=True)
            raw = truncate_for_scan(path.read_bytes(), args.max_bytes_per_file, str(path))
            before = len(candidates)
            candidates.extend(scan_blob(
                path, "raw", raw,
                max_strings=args.max_strings_per_file,
                max_context_bytes=args.max_context_bytes,
                cp932_candidates_only=args.cp932_candidates_only,
                cp932_deep_scan=cp932_deep_scan,
                focus=args.focus,
                only_visible_text=args.only_visible_text,
                include_assets=args.include_assets,
            ))
            print(f"File candidates: {path}: {len(candidates) - before}", flush=True)
            if path.suffix.lower() == ".bin":
                members = parse_gzip_members(raw)
                if args.max_members is not None and len(members) > args.max_members:
                    print(f"Limit reached for {path}: max gzip members {args.max_members} of {len(members)}", flush=True)
                    members = members[:args.max_members]
                for m in members:
                    print(f"Scanning gzip member: {path} member={m.index} name={member_name(m)}", flush=True)
                    payload = truncate_for_scan(m.decompressed, args.max_bytes_per_file, f"{path} member={m.index}")
                    member_summaries.append({"file_path": str(path), "index": m.index, "name": member_name(m), "raw_start": m.raw_start, "raw_end": m.raw_end, "slot_end": m.slot_end, "slot_size": m.slot_size, "decompressed_size": len(m.decompressed), "scanned_size": len(payload)})
                    member_before = len(candidates)
                    candidates.extend(scan_blob(
                        path, "member", payload, m,
                        max_strings=args.max_strings_per_file,
                        max_context_bytes=args.max_context_bytes,
                        cp932_candidates_only=args.cp932_candidates_only,
                        cp932_deep_scan=cp932_deep_scan,
                        focus=args.focus,
                        only_visible_text=args.only_visible_text,
                        include_assets=args.include_assets,
                    ))
                    print(f"Member candidates: {path} member={m.index}: {len(candidates) - member_before}", flush=True)
    except KeyboardInterrupt:
        if candidates:
            finalized_candidates = finalize_candidates(candidates, args)
            write_report(args, root, files, member_summaries, finalized_candidates)
            print("Interrupted; partial report written", flush=True)
            return 130
        print("Interrupted; no candidates found", flush=True)
        return 130
    finalized_candidates = finalize_candidates(candidates, args)
    write_report(args, root, files, member_summaries, finalized_candidates)
    return 0


def encode_patch_text(text: str, encoding: str | None) -> bytes:
    enc = encoding or ("ascii" if text.isascii() else "cp932")
    if enc.startswith("ascii"):
        return text.encode("ascii")
    return text.encode("cp932")


def run_patch(args: argparse.Namespace) -> int:
    raw = args.patch_file.read_bytes()
    enc = args.encoding
    old = encode_patch_text(args.old_text, enc)
    new = encode_patch_text(args.new_text, enc)
    if len(old) != len(new):
        raise SystemExit(f"Encoded old/new byte lengths differ ({len(old)} != {len(new)}); output not written")
    if args.output.resolve() == args.patch_file.resolve():
        raise SystemExit("Refusing to overwrite --patch-file; write to a separate --output")
    if args.patch_source == "raw":
        if raw[args.offset:args.offset + len(old)] != old:
            raise SystemExit("Old bytes do not match raw file at requested offset; output not written")
        out = bytearray(raw); out[args.offset:args.offset + len(old)] = new; out_bytes = bytes(out)
    else:
        members = parse_gzip_members(raw)
        if args.member is None or args.member < 0 or args.member >= len(members):
            raise SystemExit(f"--member is required and must be in range for member patch; found {len(members)} member(s)")
        m = members[args.member]
        if m.decompressed[args.offset:args.offset + len(old)] != old:
            raise SystemExit("Old bytes do not match decompressed member at requested offset; output not written")
        patched = bytearray(m.decompressed); patched[args.offset:args.offset + len(old)] = new
        recompressed = gzip_recompress_with_metadata(bytes(patched), m)
        slot_payload = build_slot_payload(raw, m, recompressed)
        out = bytearray(raw); out[m.raw_start:m.slot_end] = slot_payload; out_bytes = bytes(out)
        after = parse_gzip_members(out_bytes)
        if len(after) != len(members):
            raise SystemExit("Patched output has unexpected gzip member count; output not written")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out_bytes)
    print("Area Server text exact-length patch report")
    print(f"Input path: {args.patch_file}")
    print(f"Output path: {args.output}")
    print(f"Input SHA1: {sha1_hex(raw)}")
    print(f"Output SHA1: {sha1_hex(out_bytes)}")
    print(f"Patch source: {args.patch_source}")
    print(f"Member: {args.member if args.patch_source == 'member' else 'n/a'}")
    print(f"Offset: {args.offset}")
    print(f"Old bytes: {old.hex()}")
    print(f"New bytes: {new.hex()}")
    print(f"Old text SHA1: {sha1_hex(old)}")
    print(f"New text SHA1: {sha1_hex(new)}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scan or exact-length patch Area Server text candidates.")
    p.add_argument("--server-root", type=Path, help="Area Server root for scan mode")
    p.add_argument("--out", type=Path, help="JSON report output path for scan mode")
    p.add_argument("--patch-file", type=Path, help="File to patch in exact-length patch mode")
    p.add_argument("--patch-source", choices=("raw", "member"), help="Patch raw bytes or selected gzip member payload")
    p.add_argument("--member", type=int, help="Zero-based gzip member index for member patch mode")
    p.add_argument("--offset", type=int, help="Offset within raw file or decompressed member")
    p.add_argument("--old-text", help="Expected old text")
    p.add_argument("--new-text", help="Replacement text of identical encoded byte length")
    p.add_argument("--output", type=Path, help="Patched copy output path")
    p.add_argument("--encoding", choices=("ascii", "cp932"), help="Explicit patch text encoding")
    p.add_argument("--quick", action="store_true", help="Scan only the known small text/event/menu data files")
    p.add_argument("--files", help="Comma-separated allowlist of files to scan, relative to --server-root unless absolute")
    p.add_argument("--skip-exe", action="store_true", default=True, help="Skip AREA SERVER.exe (default)")
    p.add_argument("--include-exe", action="store_true", help="Explicitly include AREA SERVER.exe")
    p.add_argument("--max-bytes-per-file", type=int, default=DEFAULT_MAX_BYTES_PER_FILE, help="Maximum bytes scanned per raw file or gzip member")
    p.add_argument("--max-strings-per-file", type=int, default=DEFAULT_MAX_STRINGS_PER_FILE, help="Maximum candidates collected per raw file or gzip member")
    p.add_argument("--max-members", type=int, default=DEFAULT_MAX_MEMBERS, help="Maximum gzip members scanned per file")
    p.add_argument("--max-context-bytes", type=int, default=64, help="Maximum context bytes decoded around each candidate")
    p.add_argument("--no-cp932-deep-scan", action="store_true", default=True, help="Avoid expensive CP932 brute-force scanning (default)")
    p.add_argument("--cp932-candidates-only", action="store_true", help="Enable bounded CP932 candidate decoding without exhaustive offset scanning")
    p.add_argument("--cp932-deep-scan", dest="no_cp932_deep_scan", action="store_false", help="Enable exhaustive CP932 scan")
    p.add_argument("--only-visible-text", action="store_true", help="Suppress resource/asset identifier candidates from scan output")
    p.add_argument("--include-assets", action="store_true", help="Do not classify backslash-containing paths as asset identifiers for visible-text filtering")
    p.add_argument("--focus", choices=("shop",), help="Backward-compatible alias for visible-text filtering in shop scans")
    p.add_argument("--dump-top", type=int, default=0, help="Write top N detailed candidates per file/member grouping to the TXT report")
    p.add_argument("--summary-only", type=parse_bool, nargs="?", const=True, default=None, help="Write categorized summary sections to the TXT report; accepts true/false. Defaults to true unless --dump-top N is supplied with N > 0")
    p.add_argument("--min-rank", type=int, default=None, help="Minimum rank required for candidates included in scan reports")
    p.add_argument("--exclude-rank-below", type=int, default=None, help="Exclude candidates with rank below this threshold")
    p.add_argument("--nearby-sentence-window-bytes", type=int, default=DEFAULT_NEARBY_SENTENCE_WINDOW_BYTES, help="Byte window for boosting sentence-like candidates near another sentence-like candidate; set 0 to disable")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    patching = args.patch_file is not None or args.patch_source is not None
    if patching:
        required = (args.patch_file, args.patch_source, args.offset, args.old_text, args.new_text, args.output)
        if any(v is None for v in required):
            raise SystemExit("Patch mode requires --patch-file --patch-source --offset --old-text --new-text --output")
        return run_patch(args)
    if args.cp932_candidates_only and not args.no_cp932_deep_scan:
        raise SystemExit("Use either --cp932-candidates-only or --cp932-deep-scan, not both")
    if args.server_root is None or args.out is None:
        raise SystemExit("Scan mode requires --server-root and --out")
    return run_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Legacy heuristic diagnostics for CCSF model payload research.

This legacy scanner starts from manifest-provided MDL identifiers and searches
nearby bytes for plausible float triplets.  Normal CCS structure decoding now
lives in ccsf_structure_decoder.py; keep this module for explicit legacy
heuristic diagnostics only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Iterable

from ccsf_preview_manifest import build_manifest

MAX_ASSET_READ_BYTES = 128 * 1024 * 1024
REGION_PREFIX_BYTES = 4096
REGION_SUFFIX_BYTES = 64 * 1024
MAX_REGION_BYTES = 256 * 1024
IDENTIFIER_WINDOW_BYTES = 512
MIN_VERTEX_COUNT = 3
MAX_VERTEX_COUNT = 200_000
MIN_FACE_COUNT = 1
OBJ_CONFIDENCE_THRESHOLD = 0.82
POINT_CLOUD_CONFIDENCE_THRESHOLD = 0.72
SMALL_REPEATED_VERTEX_COUNT = 32
SMALL_REPEATED_FACE_COUNT = 64
IDENTIFIER_RE = re.compile(
    rb"(?:MDL|MPH|OBJ|TEX|CLT|MAT|ANM|CMP|BOX|DMY|LGT|CAM)_[A-Za-z0-9_./\\-]{1,96}"
)


def _read_bounded(
    path: Path, max_bytes: int = MAX_ASSET_READ_BYTES
) -> tuple[bytes, list[str]]:
    """Read at most max_bytes + 1 from an asset so oversized files are detected."""
    warnings: list[str] = []
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        warnings.append(
            f"Asset read was truncated to {max_bytes} bytes for bounded diagnostics."
        )
        data = data[:max_bytes]
    return data, warnings


def _hex_preview(data: bytes, length: int) -> str:
    return " ".join(f"{byte:02X}" for byte in data[:length])


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "candidate"


def _default_decode_paths(asset_file: Path, out_dir: Path) -> dict[str, Path]:
    """Return the default per-asset decode output paths."""
    asset_stem = _safe_name(asset_file.stem)
    asset_out_dir = out_dir / asset_stem
    return {
        "asset_out_dir": asset_out_dir,
        "report": asset_out_dir / "model_decode_report.json",
        "text_report": asset_out_dir / "model_decode_report.txt",
        "manifest": asset_out_dir / "manifest.json",
        "raw_dir": asset_out_dir / "raw_candidates",
        "obj_dir": asset_out_dir / "obj",
    }


def _encoded_identifier(identifier: str) -> bytes:
    return identifier.encode("ascii", errors="ignore")


def _find_all(data: bytes, needle: bytes) -> list[int]:
    if not needle:
        return []
    offsets: list[int] = []
    start = 0
    while True:
        found = data.find(needle, start)
        if found < 0:
            return offsets
        offsets.append(found)
        start = found + 1


def _candidate_range(offset: int, size: int) -> tuple[int, int]:
    start = max(0, offset - REGION_PREFIX_BYTES)
    end = min(size, offset + REGION_SUFFIX_BYTES)
    if end - start > MAX_REGION_BYTES:
        end = min(size, start + MAX_REGION_BYTES)
    return start, end


def _nearby_identifiers(
    data: bytes, start: int, end: int
) -> list[dict[str, int | str]]:
    window_start = max(0, start - IDENTIFIER_WINDOW_BYTES)
    window_end = min(len(data), end + IDENTIFIER_WINDOW_BYTES)
    found: list[dict[str, int | str]] = []
    for match in IDENTIFIER_RE.finditer(data[window_start:window_end]):
        raw = match.group(0)
        found.append(
            {
                "identifier": raw.decode("ascii", errors="replace"),
                "offset": window_start + match.start(),
            }
        )
    return found


def plausible_xyz(x: float, y: float, z: float) -> bool:
    """Return True for finite, moderately bounded model-space coordinates."""
    if not all(math.isfinite(value) for value in (x, y, z)):
        return False
    magnitude = max(abs(x), abs(y), abs(z))
    return 1.0e-5 <= magnitude <= 1.0e5


def scan_float32_xyz_triplets(
    blob: bytes, base_offset: int = 0
) -> list[dict[str, Any]]:
    """Scan aligned float32 XYZ triplet runs and return plausible vertex runs."""
    runs: list[dict[str, Any]] = []
    limit = len(blob) - 12
    for alignment in range(4):
        current: list[tuple[float, float, float]] = []
        current_offset: int | None = None
        pos = alignment
        while pos <= limit:
            x, y, z = struct.unpack_from("<fff", blob, pos)
            if plausible_xyz(x, y, z):
                if current_offset is None:
                    current_offset = pos
                current.append((x, y, z))
            else:
                if len(current) >= MIN_VERTEX_COUNT and current_offset is not None:
                    runs.append(
                        {
                            "offset": base_offset + current_offset,
                            "stride": 12,
                            "vertices": current,
                        }
                    )
                current = []
                current_offset = None
            pos += 12
        if len(current) >= MIN_VERTEX_COUNT and current_offset is not None:
            runs.append(
                {
                    "offset": base_offset + current_offset,
                    "stride": 12,
                    "vertices": current,
                }
            )
    runs.sort(key=lambda run: len(run["vertices"]), reverse=True)
    return runs[:8]


def probe_index_buffers(
    blob: bytes, vertex_count: int, base_offset: int = 0
) -> list[dict[str, Any]]:
    """Probe conservative u16/u32 triangle index-buffer candidates."""
    probes: list[dict[str, Any]] = []
    for width in (2, 4):
        max_pos = len(blob) - (width * 3)
        for alignment in range(width):
            pos = alignment
            while pos <= max_pos:
                faces: list[tuple[int, int, int]] = []
                run_start = pos
                while pos <= max_pos:
                    values = struct.unpack_from(
                        "<HHH" if width == 2 else "<III", blob, pos
                    )
                    if len(set(values)) == 3 and all(
                        0 <= value < vertex_count for value in values
                    ):
                        faces.append((int(values[0]), int(values[1]), int(values[2])))
                        pos += width * 3
                    else:
                        break
                if len(faces) >= MIN_FACE_COUNT:
                    probes.append(
                        {
                            "offset": base_offset + run_start,
                            "index_width": width * 8,
                            "faces": faces,
                        }
                    )
                pos = max(pos + width, run_start + width)
    probes.sort(key=lambda probe: len(probe["faces"]), reverse=True)
    return probes[:8]


def geometry_confidence(
    vertex_run: dict[str, Any] | None, index_probe: dict[str, Any] | None
) -> float:
    """Score decoded geometry evidence, favoring direct vertices plus faces."""
    if not vertex_run:
        return 0.0
    vertices = vertex_run.get("vertices") or []
    vertex_count = len(vertices)
    score = 0.25 if vertex_count >= MIN_VERTEX_COUNT else 0.0
    if vertex_count >= 16:
        score += 0.2
    if vertex_count >= 64:
        score += 0.1
    if vertex_count <= MAX_VERTEX_COUNT:
        score += 0.1
    if index_probe:
        face_count = len(index_probe.get("faces") or [])
        if face_count >= MIN_FACE_COUNT:
            score += 0.25
        if face_count >= max(1, vertex_count // 4):
            score += 0.1
    xs, ys, zs = zip(*vertices) if vertices else ((), (), ())
    if (
        vertices
        and len({round(value, 4) for value in xs}) > 1
        and len({round(value, 4) for value in ys}) > 1
    ):
        score += 0.1
    return min(score, 1.0)


def _geometry_signature(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
) -> dict[str, Any]:
    """Return stable hashes and basic dimensions for decoded triangle geometry."""
    xs, ys, zs = zip(*vertices)
    bounding_box = {
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
    }
    rounded_vertices = [[round(coord, 5) for coord in vertex] for vertex in vertices]
    coord_payload = json.dumps(
        rounded_vertices, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    face_payload = json.dumps(faces, separators=(",", ":")).encode("utf-8")
    coord_hash = hashlib.sha256(coord_payload).hexdigest()
    face_hash = hashlib.sha256(face_payload).hexdigest()
    combined_payload = json.dumps(
        {
            "vertex_count": len(vertices),
            "face_count": len(faces),
            "bounding_box": [
                [round(value, 5) for value in bounding_box["min"]],
                [round(value, 5) for value in bounding_box["max"]],
            ],
            "rounded_coordinate_hash": coord_hash,
            "face_index_hash": face_hash,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "vertex_count": len(vertices),
        "face_count": len(faces),
        "bounding_box": bounding_box,
        "rounded_coordinate_hash": coord_hash,
        "face_index_hash": face_hash,
        "geometry_hash": hashlib.sha256(combined_payload).hexdigest(),
    }


def _is_repeated_small_geometry(
    signature: dict[str, Any], duplicate_count: int
) -> bool:
    return (
        duplicate_count > 1
        and signature.get("vertex_count", 0) <= SMALL_REPEATED_VERTEX_COUNT
        and signature.get("face_count", 0) <= SMALL_REPEATED_FACE_COUNT
    )


def _write_obj(
    path: Path,
    vertices: Iterable[tuple[float, float, float]],
    faces: Iterable[tuple[int, int, int]] = (),
) -> None:
    lines = ["# decoded from CCSF asset bytes"]
    for x, y, z in vertices:
        lines.append(f"v {x:.8g} {y:.8g} {z:.8g}")
    for a, b, c in faces:
        lines.append(f"f {a + 1} {b + 1} {c + 1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def decode_model(
    asset_file: Path,
    out_dir: Path,
    *,
    include_diagnostic_objs: bool = False,
    include_small_objs: bool = False,
    max_objs: int | None = None,
) -> dict[str, Any]:
    data, warnings = _read_bounded(asset_file)
    paths = _default_decode_paths(asset_file, out_dir)
    raw_dir = paths["raw_dir"]
    obj_dir = paths["obj_dir"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    obj_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(asset_file)
    manifest_path = paths["manifest"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    identifiers = list(
        dict.fromkeys(
            (manifest.get("main_model_candidates") or [])
            + (manifest.get("model_candidates") or [])
        )
    )
    candidates: list[dict[str, Any]] = []
    objs_written: list[str] = []
    notes: list[str] = list(manifest.get("notes") or [])
    diagnostics_written = [str(manifest_path)]

    for identifier in identifiers:
        encoded = _encoded_identifier(str(identifier))
        occurrences = _find_all(data, encoded)
        if not occurrences:
            candidates.append(
                {
                    "identifier": identifier,
                    "occurrences": 0,
                    "confidence": 0.0,
                    "rejection_reasons": ["identifier_not_found"],
                    "notes": ["identifier not found in bounded asset bytes"],
                }
            )
            continue
        for occurrence_index, offset in enumerate(occurrences):
            start, end = _candidate_range(offset, len(data))
            region = data[start:end]
            safe_identifier = _safe_name(str(identifier))
            raw_path = raw_dir / (
                f"{len(candidates):03d}_offset-0x{offset:08X}_name-{safe_identifier}.bin"
            )
            raw_path.write_bytes(region)
            diagnostics_written.append(str(raw_path))
            vertex_runs = scan_float32_xyz_triplets(region, start)
            best_vertex = vertex_runs[0] if vertex_runs else None
            index_probes = (
                probe_index_buffers(region, len(best_vertex["vertices"]), start)
                if best_vertex
                else []
            )
            best_index = index_probes[0] if index_probes else None
            confidence = geometry_confidence(best_vertex, best_index)
            geometry_signature = None
            if best_vertex and best_index:
                geometry_signature = _geometry_signature(
                    best_vertex["vertices"], best_index["faces"]
                )
            candidate: dict[str, Any] = {
                "identifier": identifier,
                "occurrence_index": occurrence_index,
                "offset": offset,
                "estimated_range": {"start": start, "end": end, "size": end - start},
                "nearby_identifiers": _nearby_identifiers(data, start, end),
                "first_64_bytes_hex": _hex_preview(region, 64),
                "first_128_bytes_hex": _hex_preview(region, 128),
                "candidate_sizes": {
                    "encoded_identifier": len(encoded),
                    "raw_region": len(region),
                    "asset_bytes_read": len(data),
                },
                "float32_xyz_runs": [
                    {
                        "offset": run["offset"],
                        "stride": run["stride"],
                        "vertex_count": len(run["vertices"]),
                    }
                    for run in vertex_runs
                ],
                "index_buffer_probes": [
                    {
                        "offset": probe["offset"],
                        "index_width": probe["index_width"],
                        "face_count": len(probe["faces"]),
                    }
                    for probe in index_probes
                ],
                "geometry_signature": geometry_signature,
                "confidence": confidence,
                "raw_candidate_path": str(raw_path),
                "rejection_reasons": [],
                "exported_diagnostic_obj_paths": [],
            }
            if best_vertex:
                candidate["_decoded_vertices"] = best_vertex["vertices"]
            if best_index:
                candidate["_decoded_faces"] = best_index["faces"]
            candidates.append(candidate)

    geometry_groups: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        signature = candidate.get("geometry_signature")
        if not signature:
            continue
        geometry_hash = signature["geometry_hash"]
        group = geometry_groups.setdefault(
            geometry_hash,
            {"geometry_hash": geometry_hash, "candidate_indexes": [], **signature},
        )
        group["candidate_indexes"].append(index)

    for group in geometry_groups.values():
        group["duplicate_count"] = len(group["candidate_indexes"])

    exported_obj_count = 0
    diagnostic_proxy_exported = False
    confirmed_mesh_count = 0
    for index, candidate in enumerate(candidates):
        reasons = candidate["rejection_reasons"]
        signature = candidate.get("geometry_signature")
        vertices = candidate.pop("_decoded_vertices", None)
        faces = candidate.pop("_decoded_faces", None)
        if signature:
            group = geometry_groups[signature["geometry_hash"]]
            duplicate_count = group["duplicate_count"]
            candidate["geometry_duplicate_count"] = duplicate_count
            if index != group["candidate_indexes"][0]:
                reasons.append("duplicate_geometry")
            if not include_small_objs and _is_repeated_small_geometry(
                signature, duplicate_count
            ):
                reasons.append("repeated_small_geometry")
        if not vertices:
            reasons.append("no_vertices_decoded")
        if not faces:
            reasons.append("no_faces_decoded")
        if candidate["confidence"] < OBJ_CONFIDENCE_THRESHOLD:
            reasons.append("below_obj_confidence_threshold")

        can_export = max_objs is None or exported_obj_count < max_objs
        if vertices and faces and not reasons and can_export:
            obj_path = (
                obj_dir
                / f"{exported_obj_count:03d}_{_safe_name(str(candidate['identifier']))}.obj"
            )
            _write_obj(obj_path, vertices, faces)
            objs_written.append(str(obj_path))
            candidate["obj_path"] = str(obj_path)
            exported_obj_count += 1
            confirmed_mesh_count += 1
        elif (
            vertices
            and include_diagnostic_objs
            and not diagnostic_proxy_exported
            and can_export
        ):
            obj_path = (
                obj_dir
                / f"{exported_obj_count:03d}_{_safe_name(str(candidate['identifier']))}_diagnostic.obj"
            )
            _write_obj(obj_path, vertices, faces or ())
            objs_written.append(str(obj_path))
            candidate["exported_diagnostic_obj_paths"].append(str(obj_path))
            diagnostic_proxy_exported = True
            exported_obj_count += 1
        elif (
            vertices
            and (faces or candidate["confidence"] >= POINT_CLOUD_CONFIDENCE_THRESHOLD)
            and not can_export
        ):
            reasons.append("max_objs_reached")

    unique_geometry_groups = list(geometry_groups.values())
    exported_diagnostic_obj_paths = [
        path
        for candidate in candidates
        for path in (candidate.get("exported_diagnostic_obj_paths") or [])
    ]
    if not identifiers:
        notes.append("Manifest did not contain MDL identifiers to examine.")
    if not objs_written:
        notes.append(
            "No geometry decoded with sufficient confidence; no placeholder OBJ files emitted."
        )
    if confirmed_mesh_count == 0:
        notes.append("No confirmed character mesh decoded yet")
    decode_status = "geometry_decoded" if confirmed_mesh_count else "diagnostics_only"
    report_path = paths["report"]
    text_report_path = paths["text_report"]
    diagnostics_written.extend([str(report_path), str(text_report_path)])

    report: dict[str, Any] = {
        "asset_file": str(asset_file),
        "asset_name": manifest.get("asset_name") or asset_file.stem,
        "report_path": str(report_path),
        "manifest_path": str(manifest_path),
        "text_report_path": str(text_report_path),
        "raw_candidates_dir": str(raw_dir),
        "obj_dir": str(obj_dir),
        "asset_size_bytes_read": len(data),
        "sha256_bounded_read": hashlib.sha256(data).hexdigest(),
        "candidates_examined": candidates,
        "unique_geometry_groups": unique_geometry_groups,
        "confirmed_mesh_count": confirmed_mesh_count,
        "objs_written": objs_written,
        "exported_diagnostic_obj_paths": exported_diagnostic_obj_paths,
        "diagnostics_written": diagnostics_written,
        "decode_status": decode_status,
        "notes": notes,
        "warnings": warnings,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    text_report_path.write_text(_render_text(report) + "\n", encoding="utf-8")
    return report


def _render_text(report: dict[str, Any]) -> str:
    lines = [
        "CCSF Model Decode Report",
        "========================",
        f"Asset file: {report['asset_file']}",
        f"Asset name: {report['asset_name']}",
        f"Manifest path: {report['manifest_path']}",
        f"Decode status: {report['decode_status']}",
        f"Candidates examined: {len(report.get('candidates_examined') or [])}",
        f"Unique geometry groups: {len(report.get('unique_geometry_groups') or [])}",
        f"Confirmed mesh count: {report.get('confirmed_mesh_count', 0)}",
        f"OBJ files written: {len(report.get('objs_written') or [])}",
        f"Diagnostic OBJ files written: {len(report.get('exported_diagnostic_obj_paths') or [])}",
    ]
    geometry_groups = report.get("unique_geometry_groups") or []
    if geometry_groups:
        lines.append("Geometry groups:")
        for group in geometry_groups:
            lines.append(
                "- "
                f"{group['geometry_hash']}: "
                f"vertices={group['vertex_count']}, "
                f"faces={group['face_count']}, "
                f"duplicates={group.get('duplicate_count', 1)}"
            )
    rejected = [
        candidate
        for candidate in report.get("candidates_examined", [])
        if candidate.get("rejection_reasons")
    ]
    if rejected:
        lines.append("Candidate rejection reasons:")
        for candidate in rejected:
            label = candidate.get("identifier", "<unknown>")
            offset = candidate.get("offset")
            offset_text = f" at 0x{offset:08X}" if isinstance(offset, int) else ""
            lines.append(
                f"- {label}{offset_text}: {', '.join(candidate['rejection_reasons'])}"
            )
    diagnostic_paths = report.get("exported_diagnostic_obj_paths") or []
    if diagnostic_paths:
        lines.append("Exported diagnostic OBJ paths:")
        lines.extend(f"- {path}" for path in diagnostic_paths)
    lines.append("Notes:")
    lines.extend(f"- {note}" for note in report.get("notes", []))
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Legacy heuristic diagnostics for CCSF model payload research (float scanner; not the default CCS structure parser)."
    )
    ap.add_argument("asset_file", help="Path to the CCSF model asset to decode")
    ap.add_argument(
        "--out-dir",
        default="workspace/model_previews",
        help="Directory for legacy heuristic diagnostics and optional preview artifacts",
    )
    ap.add_argument("--report", help="Optional JSON decode report path")
    ap.add_argument("--text-out", help="Optional readable legacy heuristic diagnostics report path")
    ap.add_argument(
        "--include-diagnostic-objs",
        action="store_true",
        help="Allow writing one diagnostic proxy OBJ for rejected or point-cloud geometry.",
    )
    ap.add_argument(
        "--include-small-objs",
        action="store_true",
        help="Allow repeated small geometry groups to be exported instead of rejected.",
    )
    ap.add_argument(
        "--max-objs",
        type=int,
        help="Maximum number of OBJ files to write, including diagnostics",
    )
    args = ap.parse_args()
    if args.max_objs is not None and args.max_objs < 0:
        ap.error("--max-objs must be greater than or equal to 0")

    report = decode_model(
        Path(args.asset_file),
        Path(args.out_dir),
        include_diagnostic_objs=args.include_diagnostic_objs,
        include_small_objs=args.include_small_objs,
        max_objs=args.max_objs,
    )
    text = _render_text(report)
    print(text)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    if args.text_out:
        Path(args.text_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.text_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

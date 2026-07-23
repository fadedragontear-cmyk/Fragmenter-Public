#!/usr/bin/env python3
"""
Fragmenter - .hack//frägment Area Server toolkit.

CLI entrypoint for safe scan/package workflows plus legacy index/unpack/inspect/map/search/extract/patch/install/makepatch/applypatch/shopprobe/reskin/areadiff/correlations.
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
PY = sys.executable

def run_tool(script: str, args: list[str]) -> int:
    p = TOOLS / script
    if not p.exists():
        raise SystemExit(f"Missing tool: {p}")
    return subprocess.call([PY, str(p)] + args, cwd=str(ROOT))

def main() -> int:
    ap = argparse.ArgumentParser(prog="fragmenter", description="Fragmenter: frägment Area Server toolkit")
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("gui", help="Launch GUI")

    p = sp.add_parser("index", help="Index a data folder or a .bin/.dat into JSON")
    p.add_argument("target")
    p.add_argument("--out", default="fragmenter_index.json")

    p = sp.add_parser("scan", help="Read-only safe metadata scan/report workflow (does not copy or modify game binaries)")
    p.add_argument("--server-root", required=True, help="Area Server root folder")
    p.add_argument("--data-dir", required=True, help="Area Server data folder")
    p.add_argument("--save-folder", help="Optional Area Server save folder")
    p.add_argument("--iso", help="Optional ISO path for read-only directory metadata")
    p.add_argument("--data-bin", help="Optional external DATA.bin path for metadata relationship checks")
    p.add_argument("--out", required=True, help="Workspace/output folder for read-only reports")

    p = sp.add_parser("package", help="Read-only safe report package workflow (exports report/text files only)")
    p.add_argument("--out", required=True, help="Workspace/output folder created by scan")
    p.add_argument("--zip-out", help="Output ZIP path; defaults under workspace/export")

    p = sp.add_parser("export-package", help="Read-only safe report package workflow alias (exports report/text files only)")
    p.add_argument("--out", required=True, help="Workspace/output folder created by scan")
    p.add_argument("--zip-out", help="Output ZIP path; defaults under workspace/export")

    p = sp.add_parser("unpack", help="Unpack a .bin/.dat (gzip -> CCSF sections)")
    p.add_argument("input")
    p.add_argument("--out", default="out_sections")
    p.add_argument("--strings", action="store_true")
    p.add_argument("--list", action="store_true")

    p = sp.add_parser("inspect", help="Inspect a .bin section or a .ccsf file")
    p.add_argument("path")
    p.add_argument("--section")
    p.add_argument("--max-list", type=int, default=40)

    p = sp.add_parser("mapresources", help="Build resource relationships for a CCSF section")
    p.add_argument("path")
    p.add_argument("--section")
    p.add_argument("--out")
    p.add_argument("--text-out")

    p = sp.add_parser("inspect-ccsf-asset", help="Inspect one extracted CCSF-like asset bundle")
    p.add_argument("path")
    p.add_argument("--out")
    p.add_argument("--text-out")

    p = sp.add_parser("build-ccsf-preview-manifest", help="Build a preview manifest for a CCSF-like asset bundle")
    p.add_argument("path")
    p.add_argument("--out")
    p.add_argument("--text-out")

    p = sp.add_parser("decode-ccsf-model", help="Parse CCS Structure for a model asset (default); use --legacy-heuristic-diagnostics for old float scanner")
    p.add_argument("asset_file")
    p.add_argument("--out-dir", default="workspace/model_previews")
    p.add_argument("--report")
    p.add_argument("--text-out")
    p.add_argument("--legacy-heuristic-diagnostics", action="store_true", help="Run the legacy heuristic float-scanner diagnostics instead of the structure parser")
    p.add_argument("--real-fixture-diagnostics", action="store_true", help="Print aur1body real fixture diagnostics or explicit skip status")

    p = sp.add_parser("index-ccsf-assets", help="Recursively index extracted CCSF-like assets")
    p.add_argument("folder")
    p.add_argument("--out")
    p.add_argument("--text-out")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--summary-only", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--max-file-size", type=int)
    p.add_argument("--include", action="append", default=[])
    p.add_argument("--exclude", action="append", default=[])

    p = sp.add_parser("isosearch", help="Search ISO by path/name fragments (no full index required)")
    p.add_argument("--iso", required=True)
    p.add_argument("--query", action="append", required=True)
    p.add_argument("--extensions")
    p.add_argument("--prefix", default="")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--max-scanned", type=int, default=25000)
    p.add_argument("--out")
    p.add_argument("--ndjson", action="store_true")

    p = sp.add_parser("isosearch-section", help="Search ISO using resource map hints")
    p.add_argument("--iso", required=True)
    p.add_argument("--section-file", required=True)
    p.add_argument("--query", action="append")
    p.add_argument("--extensions")
    p.add_argument("--prefix", default="")
    p.add_argument("--max-queries", type=int, default=30)
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--max-scanned", type=int, default=25000)
    p.add_argument("--out")

    p = sp.add_parser("isoextract", help="Extract one file from an ISO by internal path")
    p.add_argument("iso")
    p.add_argument("--file", dest="internal_path", required=True)
    p.add_argument("--out", required=True)


    p = sp.add_parser("extract-ccsf-from-iso", help="Extract embedded CCSF bundles from likely ISO containers")
    p.add_argument("iso_path")
    p.add_argument("--workspace", default="workspace")
    p.add_argument("--iso-index")
    p.add_argument("--out")
    p.add_argument("--text-out")
    p.add_argument("--max-scan-bytes", type=int)
    p.add_argument("--extract-cap", type=int)
    p.add_argument("--container-limit", type=int)
    p.add_argument("--asset-limit", type=int)
    p.add_argument("--limit", type=int, help="Backward-compatible alias for --container-limit")
    p.add_argument("--build-index", action="store_true")
    p.add_argument("--reuse-existing", action="store_true")
    p.add_argument("--summary-only", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--include", action="append", default=[])
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--container", action="append", default=[])
    p.add_argument("--index-assets", action="store_true")
    p.add_argument("--include-failed-candidates", action="store_true")
    p.add_argument("--include-non-ccsf-gzip", action="store_true")
    p.add_argument("--ccsf-only", action="store_true")
    p.add_argument("--gzip-only", action="store_true")
    p.add_argument("--max-report-rows", type=int)
    p.add_argument("--max-failed-rows", type=int)

    p = sp.add_parser("media-pipeline-iso", help="Run ISO media inventory/extract/decode pipeline")
    p.add_argument("iso_path")
    p.add_argument("--workspace", default="workspace")
    p.add_argument("--mode", choices=("inventory", "extract", "decode", "all"), default="all")
    p.add_argument("--scan-all-bytes", action="store_true")
    p.add_argument("--max-read-bytes", type=int)
    p.add_argument("--embedded-read-bytes", type=int)
    p.add_argument("--max-embedded-per-file", type=int)
    p.add_argument("--extract-bucket", action="append", default=[])
    p.add_argument("--clean", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-output-mb", type=int)
    p.add_argument("--no-decode", action="store_true")
    p.add_argument("--decode-audio", action="store_true")
    p.add_argument("--decode-textures", action="store_true")
    p.add_argument("--decode-models", action="store_true")
    p.add_argument("--legacy-model-diagnostics", action="store_true")
    p.add_argument("--hash", action="store_true")
    p.add_argument("--known-media-targets", action="store_true")
    p.add_argument("--progress-jsonl")


    p = sp.add_parser("analyze-snddata", help="Run SNDDATA music/audio diagnostics")
    p.add_argument("data_path")
    p.add_argument("--workspace", default="workspace")
    p.add_argument("--real-fixture-diagnostics", action="store_true", help="Print default extracted snddata.bin diagnostics or explicit skip status")


    p = sp.add_parser("build-asset-library", help="Build a combined asset library report")
    p.add_argument("--index")
    p.add_argument("--extraction-report")
    p.add_argument("--out")
    p.add_argument("--text-out")
    p.add_argument("--max-report-rows", type=int)

    p = sp.add_parser("survey-iso-assets", help="Survey ISO assets into broad candidate buckets")
    p.add_argument("iso_path")
    p.add_argument("--workspace", default="workspace")
    p.add_argument("--index")
    p.add_argument("--max-report-rows", type=int)

    p = sp.add_parser("area-identify-encrypted", help="Identify encrypted Area Server data")
    p.add_argument("file")

    p = sp.add_parser("area-decrypt", help="Decrypt encrypted Area Server data")
    p.add_argument("file")
    p.add_argument("--out", required=True)

    p = sp.add_parser("area-encrypt", help="Encrypt plain Area Server data")
    p.add_argument("plain_file")
    key_group = p.add_mutually_exclusive_group(required=True)
    key_group.add_argument("--key-from")
    key_group.add_argument("--filekey-hex")
    p.add_argument("--out", required=True)

    p = sp.add_parser("scan-area-server-patches", help="Scan Area Server executable for patch candidates")
    p.add_argument("areasrv_exe", metavar="areasrv.exe")
    p.add_argument("--out")
    p.add_argument("--text-out")

    p = sp.add_parser("iso3d-candidates", help="List likely 3D asset candidates from an ISO index")
    p.add_argument("--index", required=True, help="Path to JSON index written by iso_index.py")
    p.add_argument("--out", required=True, help="Output JSON candidate list")
    p.add_argument("--text-out", help="Optional readable grouped text summary")
    p.add_argument("--limit", type=int, default=500, help="Maximum candidates to write")

    p = sp.add_parser("patch", help="Patch a CCSF section back into a .bin (writes a new output file)")
    p.add_argument("bin_path")
    p.add_argument("--section", required=True)
    p.add_argument("--replace", required=True)
    p.add_argument("--out", required=True)

    p = sp.add_parser("install", help="Install a patched bin into a data folder (timestamped backup)")
    p.add_argument("patched_bin")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--original-name", required=True)

    p = sp.add_parser("makepatch", help="Create a byte patch from BEFORE/AFTER save files")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--out", required=True)

    p = sp.add_parser("applypatch", help="Apply a byte patch to a target save file")
    p.add_argument("--patch", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--force", action="store_true")


    p = sp.add_parser("shopprobe", help="Probe BEFORE/AFTER save pair and report likely u16/u32 changes (for shop decoding)")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--out", required=True)

    p = sp.add_parser("reskin", help="Reskin a CCSF section by repointing asset references (safe string replacements)")
    p.add_argument("bin_path")
    p.add_argument("--section", required=True)
    p.add_argument("--from", dest="from_id", required=True)
    p.add_argument("--to", dest="to_id", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--symbols", action="store_true")

    p = sp.add_parser("areadiff", help="Diff AreaData/Areakif before/after edits")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--context", type=int, default=48)

    p = sp.add_parser("modelprobe", help="Probe model/texture candidate asset for preview support")
    p.add_argument("path")
    p.add_argument("--out")
    p.add_argument("--text-out")

    p = sp.add_parser("previewbin", help="Preview a binary file with conservative bounded reads")
    p.add_argument("path")
    p.add_argument("--out")
    p.add_argument("--text-out")
    p.add_argument("--max-strings", type=int)
    p.add_argument("--max-paths", type=int)
    p.add_argument("--max-symbols", type=int)
    p.add_argument("--decompress-out")

    p = sp.add_parser("scancontainer", help="Scan a binary container for embedded file candidates")
    p.add_argument("path")
    p.add_argument("--out")
    p.add_argument("--text-out")
    p.add_argument("--max-results", type=int)
    p.add_argument("--max-scan-bytes", type=int)
    p.add_argument("--chunk-size", type=int)
    p.add_argument("--max-strings", type=int)
    p.add_argument("--max-paths", type=int)
    p.add_argument("--max-symbols", type=int)
    p.add_argument("--extract-candidates", action="store_true")
    p.add_argument("--extract-dir")
    p.add_argument("--extract-cap", type=int)
    p.add_argument("--candidate-offset", type=int)
    p.add_argument("--candidate-type")

    p = sp.add_parser("correlations-init", help="Create or normalize the ISO correlation review store")
    p.add_argument("--store", default="fragmenter_correlations.json")

    p = sp.add_parser("correlations-import-map", help="Import section/family records from resource_map.json")
    p.add_argument("--map", default="resource_map.json")
    p.add_argument("--store", default="fragmenter_correlations.json")

    p = sp.add_parser("correlations-add-hit", help="Add an ISO hit to a section/family correlation")
    p.add_argument("--section", required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--size", type=int)
    p.add_argument("--status", choices=("unreviewed", "probable", "confirmed", "rejected"), default="unreviewed")
    p.add_argument("--notes")
    p.add_argument("--store", default="fragmenter_correlations.json")

    p = sp.add_parser("correlations-set-status", help="Set review status for an ISO correlation hit")
    p.add_argument("--section", required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--status", choices=("unreviewed", "probable", "confirmed", "rejected"), required=True)
    p.add_argument("--notes")
    p.add_argument("--store", default="fragmenter_correlations.json")

    p = sp.add_parser("correlations-report", help="Generate a readable ISO correlation report")
    p.add_argument("--store", default="fragmenter_correlations.json")
    p.add_argument("--out")

    args = ap.parse_args()

    if args.cmd == "gui":
        return run_tool("fragmenter_gui.py", [])

    if args.cmd == "index":
        return run_tool("fragmenter_index.py", [args.target, "--out", args.out])

    if args.cmd == "scan":
        tool_args = ["scan", "--server-root", args.server_root, "--data-dir", args.data_dir, "--out", args.out]
        if args.save_folder:
            tool_args += ["--save-folder", args.save_folder]
        if args.iso:
            tool_args += ["--iso", args.iso]
        if args.data_bin:
            tool_args += ["--data-bin", args.data_bin]
        return run_tool("fragmenter_research_pack.py", tool_args)

    if args.cmd in {"package", "export-package"}:
        tool_args = ["package", "--out", args.out]
        if args.zip_out:
            tool_args += ["--zip-out", args.zip_out]
        return run_tool("fragmenter_research_pack.py", tool_args)

    if args.cmd == "unpack":
        tool_args = [args.input, "--out", args.out]
        if args.strings: tool_args.append("--strings")
        if args.list: tool_args.append("--list")
        return run_tool("fragment_unpack.py", tool_args)

    if args.cmd == "inspect":
        tool_args = [args.path, "--max-list", str(args.max_list)]
        if args.section: tool_args += ["--section", args.section]
        return run_tool("fragment_inspect.py", tool_args)

    if args.cmd == "mapresources":
        tool_args = [args.path]
        if args.section: tool_args += ["--section", args.section]
        if args.out: tool_args += ["--out", args.out]
        if args.text_out: tool_args += ["--text-out", args.text_out]
        return run_tool("resource_mapper.py", tool_args)

    if args.cmd == "inspect-ccsf-asset":
        tool_args = [args.path]
        if args.out: tool_args += ["--out", args.out]
        if args.text_out: tool_args += ["--text-out", args.text_out]
        return run_tool("ccsf_asset_inspector.py", tool_args)

    if args.cmd == "build-ccsf-preview-manifest":
        tool_args = [args.path]
        if args.out: tool_args += ["--out", args.out]
        if args.text_out: tool_args += ["--text-out", args.text_out]
        return run_tool("ccsf_preview_manifest.py", tool_args)

    if args.cmd == "decode-ccsf-model":
        tool_args = [args.asset_file, "--out-dir", args.out_dir]
        if args.report: tool_args += ["--report", args.report]
        if args.text_out: tool_args += ["--text-out", args.text_out]
        if getattr(args, "real_fixture_diagnostics", False): tool_args.append("--real-fixture-diagnostics")
        if getattr(args, "legacy_heuristic_diagnostics", False):
            return run_tool("ccsf_model_decoder.py", tool_args)
        return run_tool("ccsf_structure_decoder.py", tool_args)

    if args.cmd == "index-ccsf-assets":
        tool_args = [args.folder]
        if args.out: tool_args += ["--out", args.out]
        if args.text_out: tool_args += ["--text-out", args.text_out]
        if args.quiet: tool_args.append("--quiet")
        if args.summary_only: tool_args.append("--summary-only")
        if args.limit is not None: tool_args += ["--limit", str(args.limit)]
        if args.max_file_size is not None: tool_args += ["--max-file-size", str(args.max_file_size)]
        for pattern in args.include: tool_args += ["--include", pattern]
        for pattern in args.exclude: tool_args += ["--exclude", pattern]
        return run_tool("ccsf_asset_indexer.py", tool_args)

    if args.cmd == "isosearch":
        tool_args = ["isosearch", "--iso", args.iso]
        for q in args.query: tool_args += ["--query", q]
        if args.extensions: tool_args += ["--extensions", args.extensions]
        if args.prefix: tool_args += ["--prefix", args.prefix]
        tool_args += ["--limit", str(args.limit), "--max-scanned", str(args.max_scanned)]
        if args.out: tool_args += ["--out", args.out]
        if args.ndjson: tool_args.append("--ndjson")
        return run_tool("iso_search.py", tool_args)

    if args.cmd == "isosearch-section":
        tool_args = ["isosearch-section", "--iso", args.iso, "--section-file", args.section_file]
        if args.query:
            for q in args.query: tool_args += ["--query", q]
        if args.extensions: tool_args += ["--extensions", args.extensions]
        if args.prefix: tool_args += ["--prefix", args.prefix]
        tool_args += ["--max-queries", str(args.max_queries), "--limit", str(args.limit), "--max-scanned", str(args.max_scanned)]
        if args.out: tool_args += ["--out", args.out]
        return run_tool("iso_search.py", tool_args)

    if args.cmd == "isoextract":
        return run_tool("iso_extract.py", [args.iso, args.internal_path, "--out", args.out])


    if args.cmd == "extract-ccsf-from-iso":
        tool_args = [args.iso_path, "--workspace", args.workspace]
        if args.iso_index: tool_args += ["--iso-index", args.iso_index]
        if args.out: tool_args += ["--out", args.out]
        if args.text_out: tool_args += ["--text-out", args.text_out]
        if args.max_scan_bytes is not None: tool_args += ["--max-scan-bytes", str(args.max_scan_bytes)]
        if args.extract_cap is not None: tool_args += ["--extract-cap", str(args.extract_cap)]
        if args.container_limit is not None:
            tool_args += ["--container-limit", str(args.container_limit)]
        elif args.limit is not None:
            tool_args += ["--container-limit", str(args.limit)]
        if args.asset_limit is not None: tool_args += ["--asset-limit", str(args.asset_limit)]
        if args.build_index: tool_args.append("--build-index")
        if args.reuse_existing: tool_args.append("--reuse-existing")
        if args.summary_only: tool_args.append("--summary-only")
        if args.quiet: tool_args.append("--quiet")
        if args.index_assets: tool_args.append("--index-assets")
        if args.include_failed_candidates: tool_args.append("--include-failed-candidates")
        if args.include_non_ccsf_gzip: tool_args.append("--include-non-ccsf-gzip")
        if args.ccsf_only: tool_args.append("--ccsf-only")
        if args.gzip_only: tool_args.append("--gzip-only")
        if args.max_report_rows is not None: tool_args += ["--max-report-rows", str(args.max_report_rows)]
        if args.max_failed_rows is not None: tool_args += ["--max-failed-rows", str(args.max_failed_rows)]
        for pattern in args.include: tool_args += ["--include", pattern]
        for pattern in args.exclude: tool_args += ["--exclude", pattern]
        for container in args.container: tool_args += ["--container", container]
        return run_tool("iso_ccsf_extractor.py", tool_args)


    if args.cmd == "media-pipeline-iso":
        tool_args = [args.iso_path, "--workspace", args.workspace, "--mode", args.mode]
        if args.scan_all_bytes: tool_args.append("--scan-all-bytes")
        if args.max_read_bytes is not None: tool_args += ["--max-read-bytes", str(args.max_read_bytes)]
        if args.embedded_read_bytes is not None: tool_args += ["--embedded-read-bytes", str(args.embedded_read_bytes)]
        if args.max_embedded_per_file is not None: tool_args += ["--max-embedded-per-file", str(args.max_embedded_per_file)]
        for bucket in args.extract_bucket: tool_args += ["--extract-bucket", bucket]
        if args.clean: tool_args.append("--clean")
        if args.dry_run: tool_args.append("--dry-run")
        if args.max_output_mb is not None: tool_args += ["--max-output-mb", str(args.max_output_mb)]
        if args.no_decode: tool_args.append("--no-decode")
        if args.decode_audio: tool_args.append("--decode-audio")
        if args.decode_textures: tool_args.append("--decode-textures")
        if args.decode_models: tool_args.append("--decode-models")
        if getattr(args, "legacy_model_diagnostics", False): tool_args.append("--legacy-model-diagnostics")
        if args.hash: tool_args.append("--hash")
        if getattr(args, "known_media_targets", False): tool_args.append("--known-media-targets")
        if args.progress_jsonl: tool_args += ["--progress-jsonl", args.progress_jsonl]
        return run_tool("iso_media_pipeline.py", tool_args)

    if args.cmd == "analyze-snddata":
        tool_args = [args.data_path, "--workspace", args.workspace]
        if getattr(args, "real_fixture_diagnostics", False): tool_args.append("--real-fixture-diagnostics")
        return run_tool("snddata_pipeline.py", tool_args)

    if args.cmd == "build-asset-library":
        tool_args = []
        if args.index: tool_args += ["--index", args.index]
        if args.extraction_report: tool_args += ["--extraction-report", args.extraction_report]
        if args.out: tool_args += ["--out", args.out]
        if args.text_out: tool_args += ["--text-out", args.text_out]
        if args.max_report_rows is not None: tool_args += ["--max-report-rows", str(args.max_report_rows)]
        return run_tool("asset_library.py", tool_args)

    if args.cmd == "survey-iso-assets":
        tool_args = [args.iso_path, args.workspace]
        if args.index: tool_args += ["--index", args.index]
        if args.max_report_rows is not None: tool_args += ["--max-report-rows", str(args.max_report_rows)]
        return run_tool("iso_asset_survey.py", tool_args)

    if args.cmd == "area-identify-encrypted":
        return run_tool("area_crypto.py", ["identify", args.file])

    if args.cmd == "area-decrypt":
        return run_tool("area_crypto.py", ["decrypt", args.file, "--out", args.out])

    if args.cmd == "area-encrypt":
        tool_args = ["encrypt", args.plain_file, "--out", args.out]
        if args.key_from:
            tool_args += ["--key-from", args.key_from]
        if args.filekey_hex:
            tool_args += ["--filekey-hex", args.filekey_hex]
        return run_tool("area_crypto.py", tool_args)

    if args.cmd == "scan-area-server-patches":
        tool_args = [args.areasrv_exe]
        if args.out: tool_args += ["--out", args.out]
        if args.text_out: tool_args += ["--text-out", args.text_out]
        return run_tool("area_server_patcher.py", tool_args)

    if args.cmd == "iso3d-candidates":
        tool_args = ["--index", args.index, "--out", args.out, "--limit", str(args.limit)]
        if args.text_out:
            tool_args += ["--text-out", args.text_out]
        return run_tool("iso_asset_preview.py", tool_args)

    if args.cmd == "patch":
        return run_tool("fragment_patch_section.py", [args.bin_path, "--section", args.section, "--replace", args.replace, "--out", args.out])

    if args.cmd == "install":
        return run_tool("fragmenter_install.py", [args.patched_bin, "--data-dir", args.data_dir, "--original-name", args.original_name])

    if args.cmd == "makepatch":
        return run_tool("savepatch.py", ["create", "--before", args.before, "--after", args.after, "--out", args.out])

    if args.cmd == "applypatch":
        tool_args = ["apply", "--patch", args.patch, "--target", args.target]
        if args.force: tool_args.append("--force")
        return run_tool("savepatch.py", tool_args)


    if args.cmd == "shopprobe":
        return run_tool("shop_probe.py", ["--before", args.before, "--after", args.after, "--out", args.out])

    if args.cmd == "reskin":
        tool_args = [args.bin_path, "--section", args.section, "--from", str(args.from_id), "--to", str(args.to_id), "--out", args.out]
        if args.symbols: tool_args.append("--symbols")
        return run_tool("fragment_reskin_section.py", tool_args)

    if args.cmd == "areadiff":
        return run_tool("areadata_diff.py", [args.before, args.after, "--context", str(args.context)])

    if args.cmd == "modelprobe":
        tool_args = [args.path]
        if args.out:
            tool_args += ["--out", args.out]
        if args.text_out:
            tool_args += ["--text-out", args.text_out]
        return run_tool("model_preview_probe.py", tool_args)

    if args.cmd == "previewbin":
        tool_args = [args.path]
        if args.out:
            tool_args += ["--out", args.out]
        if args.text_out:
            tool_args += ["--text-out", args.text_out]
        if args.max_strings is not None:
            tool_args += ["--max-strings", str(args.max_strings)]
        if args.max_paths is not None:
            tool_args += ["--max-paths", str(args.max_paths)]
        if args.max_symbols is not None:
            tool_args += ["--max-symbols", str(args.max_symbols)]
        if args.decompress_out:
            tool_args += ["--decompress-out", args.decompress_out]
        return run_tool("binary_preview.py", tool_args)

    if args.cmd == "scancontainer":
        tool_args = [args.path, "--scan"]
        if args.out:
            tool_args += ["--out", args.out]
        if args.text_out:
            tool_args += ["--text-out", args.text_out]
        if args.max_results is not None:
            tool_args += ["--max-candidates", str(args.max_results)]
        if args.max_scan_bytes is not None:
            tool_args += ["--max-scan-bytes", str(args.max_scan_bytes)]
        if args.chunk_size is not None:
            tool_args += ["--scan-chunk", str(args.chunk_size)]
        if args.max_strings is not None:
            tool_args += ["--max-strings", str(args.max_strings)]
        if args.max_paths is not None:
            tool_args += ["--max-paths", str(args.max_paths)]
        if args.max_symbols is not None:
            tool_args += ["--max-symbols", str(args.max_symbols)]
        if args.extract_candidates:
            tool_args.append("--extract-candidates")
        if args.extract_dir:
            tool_args += ["--extract-dir", args.extract_dir]
        if args.extract_cap is not None:
            tool_args += ["--extract-cap", str(args.extract_cap)]
        if args.candidate_offset is not None:
            tool_args += ["--candidate-offset", str(args.candidate_offset)]
        if args.candidate_type:
            tool_args += ["--candidate-type", args.candidate_type]
        return run_tool("binary_preview.py", tool_args)

    if args.cmd == "correlations-init":
        return run_tool("correlation_store.py", ["init", "--store", args.store])

    if args.cmd == "correlations-import-map":
        return run_tool("correlation_store.py", ["import-map", "--map", args.map, "--store", args.store])

    if args.cmd == "correlations-add-hit":
        tool_args = ["add-hit", "--section", args.section, "--family", args.family, "--path", args.path, "--status", args.status, "--store", args.store]
        if args.size is not None:
            tool_args += ["--size", str(args.size)]
        if args.notes:
            tool_args += ["--notes", args.notes]
        return run_tool("correlation_store.py", tool_args)

    if args.cmd == "correlations-set-status":
        tool_args = ["set-status", "--section", args.section, "--family", args.family, "--path", args.path, "--status", args.status, "--store", args.store]
        if args.notes:
            tool_args += ["--notes", args.notes]
        return run_tool("correlation_store.py", tool_args)

    if args.cmd == "correlations-report":
        tool_args = ["report", "--store", args.store]
        if args.out:
            tool_args += ["--out", args.out]
        return run_tool("correlation_store.py", tool_args)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())

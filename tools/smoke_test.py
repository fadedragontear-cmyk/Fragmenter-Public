# Fragmenter smoke test
# - compile-check active tools/*.py
# - import fragmenter_gui.py safely
# - verify ISO methods exist
# - verify Runner.run supports on_line streaming + cancellation
# - verify ISO lightweight defaults stay conservative

from __future__ import annotations

import gzip
import inspect
import importlib.util
import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

def load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod

def main() -> int:
    try:
        # Compile-check active tools only; legacy snapshots live outside tools/.
        for p in TOOLS.glob("*.py"):
            py_compile.compile(str(p), doraise=True)

        # Verify shared Fragmenter core helpers import and key tools use them
        fragment_core = load_module_from_path("fragment_core", TOOLS / "fragment_core.py")
        for name in (
            "CCSF_SIG",
            "PREFIXES",
            "read_maybe_gzip",
            "write_maybe_gzip",
            "split_sections",
            "get_section",
            "scan_ascii_strings",
            "parse_asset_paths",
            "normalize_asset_path",
        ):
            if not hasattr(fragment_core, name):
                print(f"[SMOKE] fragment_core.py missing {name}")
                return 24

        resource_mapper_src = (TOOLS / "resource_mapper.py").read_text(encoding="utf-8")
        if "from fragment_core import" not in resource_mapper_src:
            print("[SMOKE] resource_mapper.py should import shared helpers from fragment_core")
            return 25
        fragment_inspect_src = (TOOLS / "fragment_inspect.py").read_text(encoding="utf-8")
        if "from fragment_core import" not in fragment_inspect_src:
            print("[SMOKE] fragment_inspect.py should import shared helpers from fragment_core")
            return 26

        # Verify binary preview helpers import and handle tiny gzip/CCSF-like samples.
        binary_preview_path = TOOLS / "binary_preview.py"
        binary_preview = load_module_from_path("binary_preview", binary_preview_path)
        for name in (
            "parse_gzip_header",
            "detect_magic",
            "preview",
            "scan_container",
            "symbol_summary",
            "scan_printable_strings_streaming",
            "iter_chunks",
        ):
            if not hasattr(binary_preview, name):
                print(f"[SMOKE] binary_preview.py missing {name}")
                return 38

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            original_name = "tiny_original.ccsf"
            gzip_sample = tdir / "tiny_sample.gz"
            with gzip_sample.open("wb") as raw_gzip:
                with gzip.GzipFile(filename=original_name, mode="wb", fileobj=raw_gzip) as gz:
                    gz.write(fragment_core.CCSF_SIG + b"TEX_gzip\x00")
            gzip_head = binary_preview.read_head(gzip_sample, 256)
            gzip_info = binary_preview.parse_gzip_header(gzip_head)
            if not gzip_info.get("is_gzip") or gzip_info.get("original_filename") != original_name:
                print("[SMOKE] binary_preview.py failed gzip detection/original filename parsing")
                return 39
            if not any(hit.get("type") == "gzip" for hit in binary_preview.detect_magic(gzip_head)):
                print("[SMOKE] binary_preview.py detect_magic missed gzip sample")
                return 40

            ccsf_sample = tdir / "tiny_ccsf.bin"
            ccsf_sample.write_bytes(
                fragment_core.CCSF_SIG
                + b"\x00TEX_foo\x00MDL_bar\x00MAT_mat\x00ANM_walk\x00CAM_main\x00DMY_dummy\x00"
            )
            ccsf_data = ccsf_sample.read_bytes()
            symbol_counts = binary_preview.symbol_summary(ccsf_data, 10)
            for pfx in ("TEX_", "MDL_", "MAT_", "ANM_", "CAM_", "DMY_"):
                if symbol_counts.get(pfx, {}).get("count") != 1:
                    print(f"[SMOKE] binary_preview.py symbol count mismatch for {pfx}: {symbol_counts.get(pfx)}")
                    return 41

            preview_json = tdir / "preview.json"
            preview_text = tdir / "preview.txt"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "fragmenter.py"),
                    "previewbin",
                    str(ccsf_sample),
                    "--out",
                    str(preview_json),
                    "--text-out",
                    str(preview_text),
                    "--max-symbols",
                    "10",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print("[SMOKE] fragmenter.py previewbin failed:", proc.stderr.strip() or proc.stdout.strip())
                return 42
            if not preview_json.exists() or not preview_text.exists():
                print("[SMOKE] fragmenter.py previewbin did not write JSON/text outputs")
                return 43
            preview_report = json.loads(preview_json.read_text(encoding="utf-8"))
            if preview_report.get("symbols", {}).get("TEX_", {}).get("count") != 1:
                print("[SMOKE] fragmenter.py previewbin JSON missing expected TEX_ symbol count")
                return 44

            container_sample = tdir / "tiny_container.bin"
            container_sample.write_bytes(
                b"prefix"
                + b"\x1f\x8b"
                + b"middle"
                + fragment_core.CCSF_SIG
                + b"more"
                + b"TIM2"
                + b"tail"
                + b"RIFF"
                + b"\x00\x00\x00\x00WAVE"
            )
            scan_json = tdir / "scan.json"
            scan_text = tdir / "scan.txt"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "fragmenter.py"),
                    "scancontainer",
                    str(container_sample),
                    "--out",
                    str(scan_json),
                    "--text-out",
                    str(scan_text),
                    "--max-results",
                    "10",
                    "--max-scan-bytes",
                    "256",
                    "--chunk-size",
                    "16",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print("[SMOKE] fragmenter.py scancontainer failed:", proc.stderr.strip() or proc.stdout.strip())
                return 45
            if not scan_json.exists() or not scan_text.exists():
                print("[SMOKE] fragmenter.py scancontainer did not write JSON/text outputs")
                return 46
            scan_report = json.loads(scan_json.read_text(encoding="utf-8"))
            scan_types = {cand.get("type") for cand in scan_report.get("candidates", [])}
            for expected in ("gzip", "CCSF container", "TIM2/TM2 texture", "RIFF/WAV"):
                if expected not in scan_types:
                    print(f"[SMOKE] fragmenter.py scancontainer missed embedded signature: {expected}; got {sorted(scan_types)}")
                    return 47

            bounded_scan_sample = tdir / "bounded_large.bin"
            with bounded_scan_sample.open("wb") as f:
                f.truncate(2 * 1024 * 1024)
                f.seek(1024 * 1024)
                f.write(b"TIM2")
            bounded_json = tdir / "bounded_scan.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "fragmenter.py"),
                    "scancontainer",
                    str(bounded_scan_sample),
                    "--out",
                    str(bounded_json),
                    "--max-results",
                    "10",
                    "--max-scan-bytes",
                    "64",
                    "--chunk-size",
                    "16",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print("[SMOKE] bounded fragmenter.py scancontainer failed:", proc.stderr.strip() or proc.stdout.strip())
                return 48
            bounded_report = json.loads(bounded_json.read_text(encoding="utf-8"))
            if bounded_report.get("scanned_bytes") != 64:
                print("[SMOKE] scancontainer should honor --max-scan-bytes without full-file scanning")
                return 49
            if any(cand.get("offset") == 1024 * 1024 for cand in bounded_report.get("candidates", [])):
                print("[SMOKE] scancontainer scanned beyond --max-scan-bytes")
                return 50

        binary_preview_src = binary_preview_path.read_text(encoding="utf-8")
        scan_src = inspect.getsource(binary_preview.scan_container)
        if ".read_bytes(" in binary_preview_src:
            print("[SMOKE] binary_preview.py should not use Path.read_bytes for scanner/preview paths")
            return 51
        if "iter_chunks(" not in scan_src or "scan_printable_strings_streaming" not in scan_src:
            print("[SMOKE] scan_container should use chunked scanning/string streaming")
            return 52

        # Verify CLI command is wired in fragmenter.py
        fragmenter_src = (ROOT / "fragmenter.py").read_text(encoding="utf-8")
        if 'add_parser("modelprobe"' not in fragmenter_src:
            print("[SMOKE] fragmenter.py missing modelprobe subcommand")
            return 12
        if 'run_tool("model_preview_probe.py"' not in fragmenter_src:
            print("[SMOKE] fragmenter.py modelprobe does not route to model_preview_probe.py")
            return 13

        # Verify probe can run headless against a tiny file
        probe_path = TOOLS / "model_preview_probe.py"
        probe_src = probe_path.read_text(encoding="utf-8")
        if "tkinter" in probe_src:
            print("[SMOKE] model_preview_probe.py should not require GUI imports")
            return 14

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            sample = tdir / "sample.bin"
            sample.write_bytes(b"Kaydara FBX Binary\x00\x1a\x00")
            json_out = tdir / "probe.json"
            text_out = tdir / "probe.txt"
            proc = subprocess.run(
                [sys.executable, str(probe_path), str(sample), "--out", str(json_out), "--text-out", str(text_out)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print("[SMOKE] model_preview_probe CLI failed:", proc.stderr.strip() or proc.stdout.strip())
                return 15
            if not json_out.exists() or not text_out.exists():
                print("[SMOKE] model_preview_probe CLI did not write outputs")
                return 16

        gui_path = TOOLS / "fragmenter_gui.py"
        gui = load_module_from_path("fragmenter_gui", gui_path)

        if not hasattr(gui, "FragmenterApp"):
            print("[SMOKE] Missing FragmenterApp in fragmenter_gui.py")
            return 2

        App = gui.FragmenterApp
        required = [
            "_build_iso",
            "build_iso_index",
            "load_iso_index",
            "resolve_iso_from_selection",
            "update_workflow_status",
            "import_resource_map_into_correlations",
            "mark_selected_correlation_hit",
            "add_edit_correlation_note",
            "open_correlation_report",
            "export_correlation_report",
            "_warn_if_no_confirmed_correlations",
            "stage_mod_plan",
        ]
        missing = [m for m in required if not hasattr(App, m)]
        if missing:
            print("[SMOKE] Missing FragmenterApp methods:", ", ".join(missing))
            return 3

        inspector_required = [
            "_build_inspector",
            "select_inspector_file",
            "preview_inspector_file",
            "scan_inspector_container",
            "extract_inspector_candidate",
            "decompress_inspector_file",
            "_populate_inspector_candidates",
            "_set_inspector_output",
            "_inspector_selected_path",
            "_inspector_temp",
            "import_preview_symbols_into_correlations",
            "_latest_binary_preview_json_path",
            "search_iso_containers_for_preview_strings",
            "scan_iso_selected_container",
            "search_iso_container_strings",
        ]
        missing_inspector = [m for m in inspector_required if not hasattr(App, m)]
        if missing_inspector:
            print("[SMOKE] Missing FragmenterApp Container Inspector methods/actions:", ", ".join(missing_inspector))
            return 53


        # Verify correlation workflow helpers are wired into the GUI and use the store module directly.
        correlation_store = load_module_from_path("correlation_store", TOOLS / "correlation_store.py")
        for name in ("load_store", "import_resource_map", "set_hit_status", "generate_report"):
            if not hasattr(correlation_store, name):
                print(f"[SMOKE] correlation_store.py missing {name}")
                return 34
        gui_src = gui_path.read_text(encoding="utf-8")
        for marker in (
            "Workflow Status",
            "Mark Probable",
            "Mark Confirmed",
            "Mark Rejected",
            "Add/Edit Note",
            "Open Correlation Report",
            "Export Correlation Report",
            "Import Map into Correlations",
            "staged_mod_plan_",
            "No confirmed correlations exist for this section yet. Continue anyway?",
        ):
            if marker not in gui_src:
                print(f"[SMOKE] fragmenter_gui.py missing correlation workflow marker: {marker}")
                return 35
        for marker in (
            "Preview / Container Inspector",
            "Preview selected file",
            "Scan selected container",
            "Import preview symbols into correlations",
            "Search ISO containers for these strings",
            "Extract/decompress selected preview candidate",
            "previewbin",
            "scancontainer",
        ):
            if marker not in gui_src:
                print(f"[SMOKE] fragmenter_gui.py missing Container Inspector action marker: {marker}")
                return 54
        iso_build_src = inspect.getsource(App._build_iso)
        if 'columns=("status", "size", "path")' not in iso_build_src:
            print("[SMOKE] ISO search results should show a correlation status column")
            return 36
        stage_src = inspect.getsource(App.stage_mod_plan)
        if "fragment_patch_section.py" in stage_src or "fragment_reskin_section.py" in stage_src:
            print("[SMOKE] staged mod plan must not patch or reskin files")
            return 37

        # Verify GUI still targets the supported ISO index tool path
        build_iso_src = inspect.getsource(App.build_iso_index)
        if "iso_index.py" not in build_iso_src:
            print("[SMOKE] build_iso_index no longer routes through tools/iso_index.py")
            return 6

        # Verify Runner.run signature + cancel support
        if not hasattr(gui, "Runner"):
            print("[SMOKE] Missing Runner in fragmenter_gui.py")
            return 4
        Runner = gui.Runner
        sig = inspect.signature(Runner.run)
        if "on_line" not in sig.parameters:
            print("[SMOKE] Runner.run missing 'on_line' parameter")
            return 5
        if not hasattr(Runner, "cancel"):
            print("[SMOKE] Runner missing cancel()")
            return 8
        if not (hasattr(gui, "MAX_CONSOLE_LINES") or hasattr(gui, "MAX_CONSOLE_CHARS")):
            print("[SMOKE] fragmenter_gui.py missing console cap constant")
            return 21
        if not hasattr(App, "_console_write"):
            print("[SMOKE] FragmenterApp missing _console_write helper")
            return 22
        poll_src = inspect.getsource(Runner._poll)
        if "console_write" not in poll_src and "_trim_console_text" not in poll_src:
            print("[SMOKE] Runner._poll should enforce console caps after queued output")
            return 23

        # Verify conservative ISO search defaults in GUI
        init_src = inspect.getsource(App.__init__)
        if "iso_search_limit = tk.IntVar(value=200)" not in init_src:
            print("[SMOKE] GUI default iso_search_limit should be 200")
            return 9
        if "iso_search_max_scan = tk.IntVar(value=25000)" not in init_src:
            print("[SMOKE] GUI default iso_search_max_scan should be 25000")
            return 10


        # Verify ISO path normalization handles ISO9660 version suffixes centrally.
        from iso9660 import normalize_path
        if normalize_path("S/R/4/TEX/SR4BAC1.BMP;1") != "s/r/4/tex/sr4bac1.bmp":
            print("[SMOKE] iso9660.normalize_path should strip numeric ISO9660 version suffixes")
            return 32
        if normalize_path("DATA/ODD;NAME.BIN") != "data/odd;name.bin":
            print("[SMOKE] iso9660.normalize_path should preserve non-version semicolon names")
            return 33

        # Verify CLI ISO search defaults and streaming support stay stable
        iso_search_path = TOOLS / "iso_search.py"
        iso_search = load_module_from_path("iso_search", iso_search_path)
        iso_src = iso_search_path.read_text(encoding="utf-8")
        parser_src = inspect.getsource(iso_search.main)
        if 'add_argument("--limit", type=int, default=200)' not in parser_src:
            print("[SMOKE] iso_search.py default --limit should be 200")
            return 17
        if 'add_argument("--max-scanned", type=int, default=25000)' not in parser_src:
            print("[SMOKE] iso_search.py default --max-scanned should be 25000")
            return 18
        if "--stream-ndjson" not in parser_src or '"event": "progress"' not in iso_src or '"event": "hit"' not in iso_src or '"event": "done"' not in iso_src:
            print("[SMOKE] iso_search.py missing streaming/progress NDJSON support")
            return 19
        if "list(search_iso" in iso_src:
            print("[SMOKE] iso_search.py should iterate search_iso directly, not list(search_iso(...))")
            return 20

        # Verify targeted ISO search workflows remain lightweight and avoid full indexing path.
        # Full indexing is allowed only through explicit advanced/manual ISO Explorer controls
        # such as build_iso_index above.
        targeted_iso_search_methods = [
            "run_iso_search",
            "run_iso_search_from_section",
            "run_iso_show_first_paths",
        ]
        targeted_iso_search_methods.extend(
            name
            for name, member in inspect.getmembers(App, predicate=inspect.isfunction)
            if "iso" in name.lower()
            and "search" in name.lower()
            and "correlat" in name.lower()
            and name not in targeted_iso_search_methods
        )
        for method_name in targeted_iso_search_methods:
            if not hasattr(App, method_name):
                print(f"[SMOKE] Missing FragmenterApp targeted ISO search method: {method_name}")
                return 11
            method_src = inspect.getsource(getattr(App, method_name))
            if "iso_index.py" in method_src:
                print(f"[SMOKE] {method_name} should not call iso_index.py")
                return 11

        # Verify legacy helper stays a thin compatibility wrapper over iso9660.py
        legacy_path = TOOLS / "fragment_iso.py"
        legacy_src = legacy_path.read_text(encoding="utf-8")
        if "LEGACY" not in legacy_src and "deprecated" not in legacy_src.lower():
            print("[SMOKE] tools/fragment_iso.py should be marked legacy/deprecated")
            return 7
        if "from iso9660 import" not in legacy_src or "Iso9660" not in legacy_src or ".extract(" not in legacy_src:
            print("[SMOKE] fragment_iso.py extract should route through tools/iso9660.py")
            return 27

        legacy_mod = load_module_from_path("fragment_iso_legacy", legacy_path)
        normalized_legacy_path = legacy_mod._normalize_requested_iso_path(r"/DATA\SAMPLE.BIN;1")
        if normalized_legacy_path != "data/sample.bin":
            print("[SMOKE] fragment_iso.py should normalize requested ISO paths before extraction")
            return 31

        duplicate_parser_markers = (
            "CD001",
            "CANDIDATE_LAYOUTS",
            "SECTOR_USER",
            "def _read_user",
            "def _detect_layout",
            "def _iter_dir_records",
            "def _u32le",
        )
        found_parser_markers = [marker for marker in duplicate_parser_markers if marker in legacy_src]
        if found_parser_markers:
            print("[SMOKE] fragment_iso.py appears to duplicate ISO parser logic:", ", ".join(found_parser_markers))
            return 28

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(legacy_path),
                    "extract",
                    "--iso",
                    str(tdir / "missing.iso"),
                    "--file",
                    "DATA\\SAMPLE.BIN;1",
                    "--out",
                    str(tdir / "sample.bin"),
                    "--index",
                    str(tdir / "old-index.json"),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            combined = f"{proc.stdout}\n{proc.stderr}"
            if proc.returncode == 2 or "unrecognized arguments" in combined:
                print("[SMOKE] fragment_iso.py extract --index failed argparse parsing:", combined.strip())
                return 29
            if "[LEGACY] --index is ignored" not in combined:
                print("[SMOKE] fragment_iso.py extract --index should print an ignored warning")
                return 30

        print("[SMOKE] OK")
        return 0

    except Exception as e:
        print("[SMOKE] FAIL:", e)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Headless/lightweight smoke checks for Fragmenter workbench helpers."""
from __future__ import annotations

import ast
import gzip
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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _literal_tuple_from_function_assignment(source: str, function_name: str, variable_name: str) -> tuple[str, ...]:
    """Return a string tuple assigned in a function without building Tk widgets."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            for child in ast.walk(node):
                if not isinstance(child, ast.Assign):
                    continue
                if not any(isinstance(target, ast.Name) and target.id == variable_name for target in child.targets):
                    continue
                value = ast.literal_eval(child.value)
                if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
                    raise RuntimeError(f"{function_name}.{variable_name} is not a literal tuple[str, ...]")
                return value
    raise RuntimeError(f"Cannot find {variable_name!r} assignment in {function_name}()")


def _function_references_attribute(source: str, function_name: str, attribute_name: str) -> bool:
    """Return whether a function body references a named attribute."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return any(isinstance(child, ast.Attribute) and child.attr == attribute_name for child in ast.walk(node))
    raise RuntimeError(f"Cannot find function {function_name}()")

def make_gzip(payload: bytes, filename: str) -> bytes:
    import io
    out = io.BytesIO()
    with gzip.GzipFile(filename=filename, mode="wb", fileobj=out, mtime=0) as gz:
        gz.write(payload)
    return out.getvalue()


def main() -> int:
    py_compile.compile(str(ROOT / "fragmenter.py"), doraise=True)
    fragmenter_src = (ROOT / "fragmenter.py").read_text(encoding="utf-8")
    if 'add_parser("gui"' not in fragmenter_src or 'run_tool("fragmenter_gui.py"' not in fragmenter_src:
        print("[WORKBENCH_SMOKE] fragmenter.py gui entrypoint is not wired")
        return 101
    if 'add_parser("iso3d-candidates"' not in fragmenter_src:
        print("[WORKBENCH_SMOKE] fragmenter.py iso3d-candidates command is not registered")
        return 118
    extract_help = subprocess.run(
        [sys.executable, str(ROOT / "fragmenter.py"), "extract-ccsf-from-iso", "--help"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if extract_help.returncode != 0:
        print(f"[WORKBENCH_SMOKE] extract-ccsf-from-iso help failed: {extract_help.stdout}")
        return 133
    if "--ccsf-only" not in extract_help.stdout or "--asset-limit" not in extract_help.stdout:
        print("[WORKBENCH_SMOKE] extract-ccsf-from-iso help is missing --ccsf-only or --asset-limit")
        return 134

    fragmenter_help = subprocess.run(
        [sys.executable, str(ROOT / "fragmenter.py"), "--help"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if fragmenter_help.returncode != 0:
        print(f"[WORKBENCH_SMOKE] fragmenter.py --help failed: {fragmenter_help.stdout}")
        return 135
    required_help_commands = {
        "build-asset-library",
        "survey-iso-assets",
        "area-identify-encrypted",
        "area-decrypt",
        "area-encrypt",
        "scan-area-server-patches",
    }
    missing_help_commands = sorted(command for command in required_help_commands if command not in fragmenter_help.stdout)
    if missing_help_commands:
        print(f"[WORKBENCH_SMOKE] fragmenter.py --help missing commands: {missing_help_commands}")
        return 136

    project = load_module("fragmenter_project", TOOLS / "fragmenter_project.py")
    containers = load_module("fragmenter_containers", TOOLS / "fragmenter_containers.py")
    identifiers = load_module("fragmenter_identifiers", TOOLS / "fragmenter_identifiers.py")
    explain = load_module("ccs_explain", TOOLS / "ccs_explain.py")
    queries = load_module("resource_queries", TOOLS / "resource_queries.py")
    preview_3d = load_module("preview_3d", TOOLS / "preview_3d.py")
    preview_texture = load_module("preview_texture", TOOLS / "preview_texture.py")
    iso_asset_preview = load_module("iso_asset_preview", TOOLS / "iso_asset_preview.py")
    asset_library = load_module("asset_library", TOOLS / "asset_library.py")
    load_module("iso_asset_survey", TOOLS / "iso_asset_survey.py")
    area_crypto = load_module("area_crypto", TOOLS / "area_crypto.py")
    area_server_patcher = load_module("area_server_patcher", TOOLS / "area_server_patcher.py")
    gui = load_module("fragmenter_gui", TOOLS / "fragmenter_gui.py")
    gui_src = (TOOLS / "fragmenter_gui.py").read_text(encoding="utf-8")

    if not hasattr(gui.FragmenterApp, "_font") or not callable(gui.FragmenterApp._font):
        print("[WORKBENCH_SMOKE] FragmenterApp._font is missing after GUI import")
        return 125

    if _function_references_attribute(gui_src, "_build_legacy_inspector_tools", "preview_tabs"):
        print("[WORKBENCH_SMOKE] legacy inspector helper must not reference preview_tabs")
        return 151
    legacy_helper_source = gui_src[gui_src.find("def _build_legacy_inspector_tools"):gui_src.find("def _ccsf_text_tab")]
    if "tk.Text" not in legacy_helper_source or "self.inspector_output" not in legacy_helper_source or "self.inspector_candidate_tree" not in legacy_helper_source:
        print("[WORKBENCH_SMOKE] legacy inspector helper must build a local inspector output before its candidate tree")
        return 152

    for class_name in ("ActionBar", "ActionSection"):
        if not hasattr(gui, class_name) or not callable(getattr(gui, class_name)):
            print(f"[WORKBENCH_SMOKE] reusable action helper constructor is missing/import-unsafe: {class_name}")
            return 141
    if not hasattr(gui.FragmenterApp, "_build_path_row") or not callable(gui.FragmenterApp._build_path_row):
        print("[WORKBENCH_SMOKE] reusable path row helper constructor is missing/import-unsafe")
        return 142

    registry = getattr(gui, "GUI_TOOL_REGISTRY", None)
    allowed_statuses = set(getattr(gui, "GUI_TOOL_STATUSES", ()))
    if not isinstance(registry, dict) or not registry:
        print("[WORKBENCH_SMOKE] GUI tool registry is missing or empty")
        return 143
    if allowed_statuses != {"active", "experimental", "legacy", "hidden"}:
        print(f"[WORKBENCH_SMOKE] GUI tool status allowlist is unexpected: {sorted(allowed_statuses)}")
        return 144
    bad_commands = sorted(tool_id for tool_id, spec in registry.items() if not isinstance(spec, dict) or not str(spec.get("command") or "").strip())
    if bad_commands:
        print(f"[WORKBENCH_SMOKE] GUI tool registry has empty command names: {bad_commands}")
        return 145
    bad_statuses = sorted(tool_id for tool_id, spec in registry.items() if not isinstance(spec, dict) or spec.get("status") not in allowed_statuses)
    if bad_statuses:
        print(f"[WORKBENCH_SMOKE] GUI tool registry has unsupported statuses: {bad_statuses}")
        return 146

    if hasattr(gui, "workflow_page_labels") and callable(gui.workflow_page_labels):
        top_nav_labels = tuple(gui.workflow_page_labels())
    else:
        top_nav_labels = _literal_tuple_from_function_assignment(gui_src, "_build_navigation_shell", "labels")
    duplicate_nav_labels = sorted({label for label in top_nav_labels if top_nav_labels.count(label) > 1})
    if duplicate_nav_labels:
        print(f"[WORKBENCH_SMOKE] duplicate top-level navigation labels: {duplicate_nav_labels}")
        return 147

    for name in (
        "_refresh_iso_ccsf_results_tree",
        "open_iso_ccsf_asset_index",
        "open_first_iso_ccsf_asset",
        "build_iso_ccsf_manifest_for_selected",
    ):
        if not hasattr(gui.FragmenterApp, name) or not callable(getattr(gui.FragmenterApp, name)):
            print(f"[WORKBENCH_SMOKE] FragmenterApp missing ISO CCSF GUI helper: {name}")
            return 130
    if 'get("confirmed_ccsf_bundles")' not in gui_src or 'failed_gzip_candidates' in gui_src[gui_src.find("def _refresh_iso_ccsf_results_tree"):gui_src.find("def index_extracted_iso_ccsf_assets")]:
        print("[WORKBENCH_SMOKE] ISO CCSF results table should use confirmed_ccsf_bundles, not failed gzip rows")
        return 131

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = project.initialize_workspace(root)
        workspace = Path(state.workspace_dir)
        for name in project.WORKSPACE_DIR_NAMES:
            if not (workspace / name).is_dir():
                print(f"[WORKBENCH_SMOKE] missing workspace directory: {name}")
                return 102
        state.iso_path = str(root / "sample.iso")
        saved = project.save_project(state)
        loaded = project.load_project(saved)
        if loaded.to_dict() != state.to_dict() or saved.name != project.PROJECT_STATE_FILENAME:
            print("[WORKBENCH_SMOKE] project state did not round-trip")
            return 103
        if project.list_reports(workspace) != [] or not (workspace / "reports").is_dir():
            print("[WORKBENCH_SMOKE] reports folder behavior is unexpected")
            return 104
        expected_report_names = list(getattr(gui, "EXPECTED_REPORT_NAMES", ()))
        if not expected_report_names:
            print("[WORKBENCH_SMOKE] GUI expected report name list is missing or empty")
            return 148
        discovered_report_names = [str(row.get("display_name")) for row in gui.discover_expected_report_files(workspace)]
        if discovered_report_names != expected_report_names:
            print(f"[WORKBENCH_SMOKE] GUI expected report discovery returned unexpected names: {discovered_report_names}")
            return 149
        for report_name in expected_report_names[:2]:
            (workspace / "reports" / report_name).write_text("smoke\n", encoding="utf-8")
        discovered_reports = gui.discover_expected_report_files(workspace)
        existing_report_names = [str(row.get("display_name")) for row in discovered_reports if row.get("exists")]
        if existing_report_names != expected_report_names[:2]:
            print(f"[WORKBENCH_SMOKE] GUI report discovery did not identify existing reports: {existing_report_names}")
            return 150

        raw = make_gzip(b"first", "one.bin") + b"\0\0PAD" + make_gzip(b"second", "two.bin") + b"\xff\0"
        members = containers.parse_gzip_members(raw)
        if len(members) != 2 or [m.decompressed for m in members] != [b"first", b"second"]:
            print("[WORKBENCH_SMOKE] padded gzip members did not parse/decompress")
            return 105
        if members[0].padding_after_size <= 0 or members[1].gzip_original_filename != "two.bin":
            print("[WORKBENCH_SMOKE] padded gzip metadata is incomplete")
            return 106

        sample_blob = b"CCSFtown04\0DMY_merchant1\0LGT_shop01\0textures/sr4sun1.bmp\0"
        found = {row["name"] for row in identifiers.extract_identifiers(sample_blob)}
        for expected in {"CCSFtown04", "DMY_merchant1", "LGT_shop01", "textures/sr4sun1.bmp"}:
            if expected not in found:
                print(f"[WORKBENCH_SMOKE] missing identifier: {expected}; got {sorted(found)}")
                return 107

        required_identifiers = [
            "town04.cmp",
            "CCSFtown04",
            "sr4wep1",
            "sr4ite1",
            "sr4mag1",
            "sr4sav1",
            "sr4fai1",
            "sr4sun1",
            "sr4clo1",
            "sr4clo2",
            "BLT_bg",
        ]
        shop_or_service_identifiers = {"sr4wep1", "sr4ite1", "sr4mag1", "sr4sav1", "sr4fai1"}
        resource_family_identifiers = set(required_identifiers) - {"town04.cmp"}
        for identifier in required_identifiers:
            explanation = explain.explain_identifier(identifier)
            summary = str(explanation.get("summary") or "").strip()
            category = str(explanation.get("category") or "").strip()
            confidence = str(explanation.get("confidence") or "").strip()
            if not summary:
                print(f"[WORKBENCH_SMOKE] missing explanation summary for {identifier}: {explanation}")
                return 108
            if not category or not confidence:
                print(f"[WORKBENCH_SMOKE] missing explanation category/confidence for {identifier}: {explanation}")
                return 109
            if identifier in resource_family_identifiers and not queries.derive_family_search_terms(identifier):
                print(f"[WORKBENCH_SMOKE] missing family search terms for {identifier}")
                return 110
            if identifier in shop_or_service_identifiers:
                warning_text = "\n".join(str(w) for w in explanation.get("warnings", [])).lower()
                if "inventory" not in warning_text:
                    print(f"[WORKBENCH_SMOKE] shop/service warning lacks inventory guard for {identifier}: {explanation}")
                    return 111


        synthetic_library_index = {
            "assets": [
                {
                    "name": "hero_01234567",
                    "type": "model",
                    "variant": "field",
                    "relative_file": "hero.ccs",
                    "size": 32,
                    "sha1": "0" * 40,
                    "counts": {"MDL": 1, "TEX": 2},
                    "readiness": "previewable",
                },
                {
                    "name": "hero_89abcdef",
                    "type": "model",
                    "variant": "field",
                    "relative_file": "hero_duplicate.tmp",
                    "size": 32,
                    "sha1": "0" * 40,
                    "counts": {"MDL": 1, "TEX": 2},
                    "readiness": "previewable",
                },
            ]
        }
        synthetic_extraction_report = {
            "confirmed_ccsf_bundles": [
                {
                    "extracted_ccsf_path": "hero.ccs",
                    "top_level_iso_file_path": "DATA/ASSETS.BIN",
                    "source_iso_path": "synthetic.iso",
                }
            ]
        }
        synthetic_library = asset_library.build_asset_library(synthetic_library_index, synthetic_extraction_report)
        if synthetic_library.get("asset_count") != 1 or synthetic_library.get("source_asset_count") != 2:
            print(f"[WORKBENCH_SMOKE] synthetic asset library counts are unexpected: {synthetic_library}")
            return 137
        synthetic_asset = synthetic_library["assets"][0]
        if (
            synthetic_asset.get("display_name") != "hero"
            or synthetic_asset.get("source_containers") != ["DATA/ASSETS.BIN"]
            or "duplicate" not in synthetic_asset.get("tags", [])
        ):
            print(f"[WORKBENCH_SMOKE] synthetic asset library grouping is unexpected: {synthetic_asset}")
            return 138

        fixed_filekey = bytes(range(area_crypto.FILEKEY_SIZE))
        plain_payload = b"synthetic area payload\0with text"
        old_load_area_key = area_crypto.load_area_key
        area_crypto.load_area_key = lambda path=area_crypto.AREA_CRYPTO_JSON: bytes(range(area_crypto.AREAKEY_SIZE))
        try:
            cipher_payload = area_crypto.encrypt_payload(fixed_filekey, plain_payload)
            decrypted_payload = area_crypto.decrypt_payload(fixed_filekey, cipher_payload)
        finally:
            area_crypto.load_area_key = old_load_area_key
        if decrypted_payload != plain_payload or cipher_payload == plain_payload:
            print("[WORKBENCH_SMOKE] synthetic area crypto roundtrip failed")
            return 139

        synthetic_exe = root / "areasrv.exe"
        synthetic_signatures = root / "area_server_patch_signatures.json"
        synthetic_pattern = b"\x10\x20\x30\x40"
        synthetic_replacement = b"\xAA\xBB\xCC\xDD"
        synthetic_exe.write_bytes(b"prefix" + synthetic_pattern + b"middle" + synthetic_replacement + b"suffix")
        synthetic_signatures.write_text(
            json.dumps({
                "safety_notes": ["synthetic smoke signature"],
                "signatures": [
                    {"name": "smoke_patch", "pattern": synthetic_pattern.hex(" "), "replace": synthetic_replacement.hex(" ")},
                ],
            }),
            encoding="utf-8",
        )
        patch_report = area_server_patcher.scan_binary(synthetic_exe, synthetic_signatures)
        patch_sig = patch_report["signatures"][0]
        if (
            patch_sig.get("found_offsets") != [6]
            or patch_sig.get("already_patched_offsets") != [16]
            or patch_report.get("missing_signatures")
        ):
            print(f"[WORKBENCH_SMOKE] synthetic Area Server patch scan failed: {patch_report}")
            return 140

        sample_index = {
            "files": [
                {"path": "models/hero_preview.obj", "size": 8192, "lba": 10},
                {"path": "native/field_character.mdl", "size": 16384, "lba": 11},
                {"path": "containers/model_assets.bin", "size": 32768, "lba": 12},
                {"path": "custom/stage_resource.ccs", "size": 65536, "lba": 13},
                {"path": "audio/voice_line.wav", "size": 65536, "lba": 14},
                {"path": "docs/readme.txt", "size": 8192, "lba": 15},
            ]
        }
        candidates = {row["path"]: row for row in iso_asset_preview.list_3d_candidates(sample_index)}

        for executable_path in ("module/loader.irx", "system/main.elf", "system/boot.prg"):
            row = iso_asset_preview.classify_iso_asset({"path": executable_path, "size": 65536})
            reasons = "\n".join(row["reasons"]).lower()
            if row["type_guess"] != "executable" or row["next_action"] != "Metadata/Text-Hex" or row["score"] >= 0 or "non-preview" not in reasons:
                print(f"[WORKBENCH_SMOKE] executable did not classify as non-preview metadata: {row}")
                return 126

        pss_row = iso_asset_preview.classify_iso_asset({"path": "movies/intro.pss", "size": 65536})
        pss_reasons = "\n".join(pss_row["reasons"]).lower()
        if pss_row["type_guess"] != "cutscene_video_candidate" or "cutscene" not in pss_reasons or "video" not in pss_reasons:
            print(f"[WORKBENCH_SMOKE] PSS did not classify as cutscene/video: {pss_row}")
            return 127

        for audio_path in ("stream/voice/hero.adx", "audio/bgm001.bin", "data/snddata.cmp"):
            row = iso_asset_preview.classify_iso_asset({"path": audio_path, "size": 65536})
            if row["type_guess"] != "audio_archive_candidate" or row["score"] >= 0:
                print(f"[WORKBENCH_SMOKE] audio/archive path did not classify as audio/archive: {row}")
                return 128

        for container_path in ("assets/chunk.bin", "assets/chunk.dat", "assets/chunk.ccs", "assets/chunk.cmp"):
            row = iso_asset_preview.classify_iso_asset({"path": container_path, "size": 65536})
            if row["next_action"] != "Scan Inside Container":
                print(f"[WORKBENCH_SMOKE] container candidate lacks scan action: {row}")
                return 129

        obj_candidate = candidates["models/hero_preview.obj"]
        obj_reasons = "\n".join(obj_candidate["reasons"]).lower()
        if obj_candidate["confidence"] != "high" or "model" not in obj_reasons:
            print(f"[WORKBENCH_SMOKE] OBJ candidate did not score as high-confidence preview/model: {obj_candidate}")
            return 119

        for candidate_path, expected_terms in {
            "native/field_character.mdl": ("model",),
            "containers/model_assets.bin": ("container",),
            "custom/stage_resource.ccs": ("container", "native"),
        }.items():
            row = candidates[candidate_path]
            reasons = "\n".join(row["reasons"]).lower()
            if row["type_guess"] not in {"model", "container_candidate", "unknown_candidate"} or row["score"] <= 0:
                print(f"[WORKBENCH_SMOKE] {candidate_path} was not classified as a useful candidate: {row}")
                return 120
            if not any(term in reasons for term in expected_terms):
                print(f"[WORKBENCH_SMOKE] {candidate_path} lacks useful native/custom/container reasons: {row}")
                return 121

        audio_score = candidates["audio/voice_line.wav"]["score"]
        text_score = candidates["docs/readme.txt"]["score"]
        weakest_candidate_score = min(
            candidates["native/field_character.mdl"]["score"],
            candidates["containers/model_assets.bin"]["score"],
            candidates["custom/stage_resource.ccs"]["score"],
        )
        if audio_score >= weakest_candidate_score or text_score >= weakest_candidate_score:
            print(f"[WORKBENCH_SMOKE] obvious audio/text scores are too high: audio={audio_score}, text={text_score}, candidate={weakest_candidate_score}")
            return 122

        embedded_blob = (
            b"pad0"
            + b"CCSF" + b"town04\0" + b"A" * 16
            + b"TIM2" + b"texture.tm2\0" + b"B" * 16
            + b"TM2" + b"texture2.tm2\0" + b"C" * 16
            + make_gzip(b"inside", "inside.bin")
        )
        embedded_container = root / "embedded_container.bin"
        embedded_container.write_bytes(embedded_blob)
        embedded_workspace = root / "embedded_workspace"
        embedded_scan = iso_asset_preview.scan_extracted_container_for_preview(
            embedded_container,
            embedded_workspace,
            max_scan_bytes=4096,
            extract_cap=1024,
        )
        embedded_candidates = embedded_scan.get("embedded_candidates", [])
        embedded_magic = {str(row.get("magic", "")).upper() for row in embedded_candidates}
        required_magic = {"43 43 53 46", "54 49 4D 32", "54 4D 32", "1F 8B"}
        if not required_magic.issubset(embedded_magic):
            print(f"[WORKBENCH_SMOKE] embedded CCSF/TIM2/TM2/gzip signatures were not detected: {embedded_candidates}")
            return 130
        embedded_base = (embedded_workspace / "upload_package" / "iso_preview_embedded").resolve()
        for row in embedded_scan.get("extracted", []):
            extracted_path = Path(str(row.get("path") or "")).resolve()
            if embedded_base not in extracted_path.parents:
                print(f"[WORKBENCH_SMOKE] embedded extraction escaped preview directory: {extracted_path}")
                return 131
        for row in embedded_candidates:
            extracted_path = row.get("extracted_path")
            if extracted_path and embedded_base not in Path(str(extracted_path)).resolve().parents:
                print(f"[WORKBENCH_SMOKE] embedded candidate path escaped preview directory: {extracted_path}")
                return 132

        preview_base = (root / "preview_workspace" / "iso_preview").resolve()
        for unsafe_path in ("../evil.obj", "/absolute.obj", "dir/../../evil.obj"):
            safe_path = iso_asset_preview.safe_preview_output_path(root / "preview_workspace", unsafe_path)
            if preview_base not in safe_path.parents or "unsafe_" not in safe_path.relative_to(preview_base).parts[0]:
                print(f"[WORKBENCH_SMOKE] unsafe preview path was not contained/sanitized: {unsafe_path!r} -> {safe_path}")
                return 123

        dmy_warnings = "\n".join(explain.explain_identifier("DMY_merchant1")["warnings"]).lower()
        lgt_warnings = "\n".join(explain.explain_identifier("LGT_shop01")["warnings"]).lower()
        if "visible npc" not in dmy_warnings or "inventory" not in dmy_warnings:
            print("[WORKBENCH_SMOKE] DMY_merchant1 warning is not specific enough")
            return 112
        if "shop inventory" not in lgt_warnings:
            print("[WORKBENCH_SMOKE] LGT_shop01 warning is not specific enough")
            return 113

        obj = root / "tiny.obj"
        obj.write_text("o tri\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
        mesh = preview_3d.parse_obj(obj)
        if mesh.vertex_count != 3 or mesh.face_count != 1 or mesh.faces[0] != [0, 1, 2]:
            print("[WORKBENCH_SMOKE] OBJ parser failed tiny mesh")
            return 114
        if mesh.bounds != ((0.0, 0.0, 0.0), (1.0, 1.0, 0.0)):
            print(f"[WORKBENCH_SMOKE] OBJ parser did not populate bounds: {mesh.bounds}")
            return 124
        if not isinstance(mesh, preview_3d.Mesh) or mesh.source_metadata.get("source_format") != "obj":
            print(f"[WORKBENCH_SMOKE] OBJ parser did not return generic Mesh metadata: {mesh}")
            return 133

        decoded_mesh = preview_3d.mesh_from_structure_decoder_output({
            "input": "synthetic.ccs",
            "records": [{
                "model": {
                    "submodels": [{
                        "vertices": [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                        "faces": [(0, 1, 2)],
                    }]
                }
            }],
        })
        if decoded_mesh.vertex_count != 3 or decoded_mesh.face_count != 1 or decoded_mesh.faces[0] != [0, 1, 2]:
            print(f"[WORKBENCH_SMOKE] structure decoder Mesh conversion failed: {decoded_mesh}")
            return 134
        if decoded_mesh.source_metadata.get("source_format") != "ccsf_structure_decoder":
            print(f"[WORKBENCH_SMOKE] structure decoder Mesh metadata missing: {decoded_mesh.source_metadata}")
            return 135

        bmp = root / "tiny.bmp"
        bmp.write_bytes(b"BM" + b"\0" * 16 + (2).to_bytes(4, "little", signed=True) + (3).to_bytes(4, "little", signed=True) + b"\0" * 32)
        old_optional = preview_texture._optional_pillow
        preview_texture._optional_pillow = lambda: (None, None)
        try:
            meta = preview_texture.extract_metadata(bmp)
        finally:
            preview_texture._optional_pillow = old_optional
        if meta.get("pillow_available") or meta.get("dimensions") != (2, 3):
            print(f"[WORKBENCH_SMOKE] texture fallback metadata failed: {meta}")
            return 115

        ok = gui.run_workbench_command([sys.executable, "-c", "print('done')"], cwd=root, timeout=5)
        cancelled = gui.run_workbench_command([sys.executable, "-c", "import time; time.sleep(5)"], cwd=root, timeout=0.1)
        if not ok.get("finished") or ok.get("cancelled") or "done" not in str(ok.get("output")):
            print(f"[WORKBENCH_SMOKE] GUI runner finish state failed: {ok}")
            return 116
        if not cancelled.get("cancelled") or cancelled.get("finished"):
            print(f"[WORKBENCH_SMOKE] GUI runner cancel state failed: {cancelled}")
            return 117

    print("[WORKBENCH_SMOKE] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

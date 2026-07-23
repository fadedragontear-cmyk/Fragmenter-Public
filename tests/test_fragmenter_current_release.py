from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_fragmenter_release
import fragment_4_builder_v127
import fragmenter_public_gui_v126
import fragmenter_public_gui_v127
import tellipatch_resource_v122


def test_current_public_root_and_launcher_contract() -> None:
    required = (
        "START_FRAGMENTER_PUBLIC.bat",
        "THIRD_PARTY_NOTICES.md",
        "fragmenter_public.py",
    )
    for name in required:
        assert (ROOT / name).is_file(), name

    for obsolete in (
        "fragmenter.py",
        "fragmenter_diagnostics.py",
        "fragmenter_wip.py",
        "run_fragmenter.bat",
    ):
        assert not (ROOT / obsolete).exists(), obsolete

    for retained in (
        "maintainer/legacy_cli/fragmenter.py",
        "maintainer/legacy_cli/fragmenter_diagnostics.py",
        "maintainer/legacy_cli/fragmenter_wip.py",
        "maintainer/BUILD_WINDOWS_RELEASE.cmd",
    ):
        assert (ROOT / retained).is_file(), retained

    launcher = (ROOT / "fragmenter_public.py").read_text(encoding="utf-8")
    assert "from fragmenter_public_gui_v127 import main" in launcher
    assert "GUI_MODULES" not in launcher


def test_current_gui_title_and_theme_completion_hooks() -> None:
    assert issubclass(
        fragmenter_public_gui_v127.PublicFragmenterAppV127,
        fragmenter_public_gui_v126.PublicFragmenterAppV126,
    )
    title_source = inspect.getsource(
        fragmenter_public_gui_v127.PublicFragmenterAppV127.__init__
    )
    assert 'self.title("Fragmenter 1.0")' in title_source
    assert "Serenial Edition" not in title_source

    for method in (
        fragmenter_public_gui_v126.PublicFragmenterAppV126._refresh_all,
        fragmenter_public_gui_v126.PublicFragmenterAppV126._run_all_done,
    ):
        assert "after_idle(self._apply_project_theme_v126)" in inspect.getsource(method)


def test_release_builder_uses_serenial_icon_and_current_entrypoint() -> None:
    icon = ROOT / "assets" / "branding" / build_fragmenter_release.BRAND_ICO_NAME
    assert icon.is_file()
    assert icon.read_bytes().startswith(b"\x00\x00\x01\x00")

    command = build_fragmenter_release.pyinstaller_command(
        ROOT,
        ROOT / "runtime" / build_fragmenter_release.BRIDGE_NAME,
    )
    assert "--icon" in command
    assert str(icon) in command
    assert "fragmenter_public_gui_v127" in command
    assert str(ROOT / "fragmenter_public.py") in command
    assert any("resources/game_setup" in value.replace("\\", "/") for value in command)


def test_bundled_game_resources_materialize_exactly(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FRAGMENTER_DATA_DIR", str(tmp_path / "data"))
    patch_path, patch_report = tellipatch_resource_v122.resolve_patch_archive()
    completion_path, completion_report = (
        fragment_4_builder_v127.resolve_completion_resource()
    )

    assert patch_path.stat().st_size == 994_064
    assert patch_report["sha256"] == (
        "9ae767029f7c1c724ceaaf62882fd36f10e34e254d70e26761b747558c7b9eb9"
    )
    assert completion_path.stat().st_size == 288_070
    assert completion_report["sha256"] == (
        "46ee3644fca9023695a092ab829a16bd03a73dc252586130297e41731e792de1"
    )


def test_one_step_build_keeps_source_and_removes_intermediate(tmp_path, monkeypatch) -> None:
    source = tmp_path / "Japanese.iso"
    output = tmp_path / "Fragment 4.0 English.iso"
    patch = tmp_path / "patches.zip"
    completion = tmp_path / "completion.zip"
    source.write_bytes(b"SOURCE")
    patch.write_bytes(b"PATCH")
    completion.write_bytes(b"COMPLETE")

    monkeypatch.setattr(
        fragment_4_builder_v127,
        "resolve_patch_archive",
        lambda: (patch, {"sha256": "patch-hash"}),
    )
    monkeypatch.setattr(
        fragment_4_builder_v127,
        "resolve_completion_resource",
        lambda: (completion, {"sha256": "completion-hash"}),
    )

    def fake_english(src, preview, **_kwargs):
        assert Path(src) == source
        Path(preview).write_bytes(b"PREVIEW")
        return {"status": "complete"}

    def fake_completion(preview, resource, destination, **_kwargs):
        assert Path(preview).read_bytes() == b"PREVIEW"
        assert Path(resource) == completion
        Path(destination).write_bytes(b"FINAL40")
        return {
            "volume_label": "FRAGMENT 4.0 ENGLISH",
            "verified_files": list(range(8)),
            "layout_note": "preserved",
        }

    monkeypatch.setattr(fragment_4_builder_v127, "build_english_iso", fake_english)
    monkeypatch.setattr(
        fragment_4_builder_v127,
        "apply_completion_pack",
        fake_completion,
    )

    result = fragment_4_builder_v127.build_fragment_4_english(source, output)

    assert source.read_bytes() == b"SOURCE"
    assert output.read_bytes() == b"FINAL40"
    assert result["volume_label"] == "FRAGMENT 4.0 ENGLISH"
    assert len(result["verified_4_0_files"]) == 8
    assert not list(tmp_path.glob(".*.english-preview.tmp.iso"))

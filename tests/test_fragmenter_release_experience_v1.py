from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import fragmenter_public_gui_v54 as gui_v54
import fragmenter_release_experience_v1 as release


def test_source_release_roots_find_celdra_assets() -> None:
    assert release.application_root() == ROOT
    assert release.bundled_data_root() == ROOT
    assert release.celdra_asset_root() == ROOT / "assets" / "celdra"
    assert (release.celdra_asset_root() / "manifest.json").is_file()
    assert (
        release.celdra_asset_root() / "avatar" / "1000032852-removebg6.png"
    ).is_file()
    assert (release.celdra_asset_root() / "avatar" / "01.gif").is_file()


def test_frozen_release_uses_meipass_for_assets_and_exe_root_for_projects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    install_root = tmp_path / "Fragmenter"
    executable = install_root / "Fragmenter.exe"
    bundle_root = tmp_path / "_MEI12345"
    install_root.mkdir()
    bundle_root.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert release.application_root() == install_root.resolve()
    assert release.bundled_data_root() == bundle_root.resolve()
    assert release.celdra_asset_root() == bundle_root.resolve() / "assets" / "celdra"
    assert release.default_project_workspace() == install_root.resolve() / "project"


def test_missing_wink_does_not_stop_intro_schedule(monkeypatch) -> None:
    scheduled: list[tuple[int, object]] = []
    console: list[str] = []

    class Stub:
        _celdra_user_name_v58 = "Fade"

        def _set_stage_position_v87(self, *_args) -> None:
            pass

        def _load_takeover_reaction_v58(self, _name: str) -> bool:
            return False

        def _append_console_v49(self, text: str) -> None:
            console.append(text)

        def _expand_for_celdra_intro_v99(self) -> None:
            pass

        def _scaled_runtime_ms_v88(self, value: int) -> int:
            return value

        def _redraw_celdra_avatar_v50(self) -> None:
            pass

        def _remember_after_v49(self, delay: int, callback) -> None:
            scheduled.append((delay, callback))

        def _show_speech_bubble_v58(self, _text: str) -> None:
            pass

        def _finish_tavern_intro_v99(self) -> None:
            pass

        def _start_placeholder_runtime_v70(self) -> None:
            pass

    monkeypatch.setattr(
        gui_v54.PublicFragmenterAppV54,
        "_animate_stage_fraction_v54",
        lambda *_args, **_kwargs: None,
    )

    release._takeover_wink_release(Stub())

    assert len(scheduled) == 7
    assert scheduled[-1][0] == release.gui_v99.INTRO_TAVERN_GATE_MS
    assert any("INTRO CONTINUING" in line for line in console)


def test_launcher_installs_release_experience() -> None:
    launcher = (ROOT / "fragmenter_public.py").read_text(encoding="utf-8")
    assert "fragmenter_release_experience_v1" in launcher
    assert "install_release_experience()" in launcher

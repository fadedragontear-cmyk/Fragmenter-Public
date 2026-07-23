from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_fragmenter_release
import fragmenter_public_gui_v2 as gui_v2
import fragmenter_public_gui_v16 as gui_v16
import fragmenter_public_gui_v54 as gui_v54
import fragmenter_release_experience_v1 as release
import fragmenter_visual_runtime_v6 as visual_runtime_v6


def test_source_release_roots_find_celdra_assets() -> None:
    assert release.application_root() == ROOT
    assert release.bundled_data_root() == ROOT
    assert release.celdra_asset_root() == ROOT / "assets" / "celdra"
    assert release.branding_image_path() == ROOT / "assets" / "branding" / "Fragmenter-Serenial.png"
    assert (release.celdra_asset_root() / "manifest.json").is_file()
    assert (
        release.celdra_asset_root() / "avatar" / "1000032852-removebg6.png"
    ).is_file()
    assert (release.celdra_asset_root() / "avatar" / "01.gif").is_file()
    assert release.branding_image_path().is_file()


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
    assert release.branding_image_path() == bundle_root.resolve() / "assets" / "branding" / "Fragmenter-Serenial.png"
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


def test_real_hatch_retires_pixel_egg_before_asset_swap(monkeypatch) -> None:
    observed: list[bool] = []

    class Stub:
        _fragmenter_celdra_egg_retired_v1 = False

    monkeypatch.setattr(
        release,
        "_ORIGINAL_V63_BEGIN_HATCH_GIF",
        lambda instance: observed.append(instance._fragmenter_celdra_egg_retired_v1),
    )
    stub = Stub()
    release._begin_hatch_gif_release(stub)

    assert stub._fragmenter_celdra_egg_retired_v1 is True
    assert observed == [True]


def test_post_hatch_missing_frame_uses_non_egg_fallback() -> None:
    class Stub:
        _fragmenter_celdra_egg_retired_v1 = False
        celdra_current_external_v50 = None

    stub = Stub()
    assert release._should_use_post_hatch_fallback(stub) is False
    stub._fragmenter_celdra_egg_retired_v1 = True
    assert release._should_use_post_hatch_fallback(stub) is True
    stub.celdra_current_external_v50 = object()
    assert release._should_use_post_hatch_fallback(stub) is False


def test_release_builder_requires_and_bundles_celdra_assets() -> None:
    required = build_fragmenter_release._required_celdra_assets(ROOT)
    assert required
    assert all(path.is_file() for path in required)
    assert ROOT / "assets" / "celdra" / "manifest.json" in required
    assert ROOT / "assets" / "celdra" / "avatar" / "01.gif" in required

    command = build_fragmenter_release.pyinstaller_command(
        ROOT,
        ROOT / "runtime" / build_fragmenter_release.BRIDGE_NAME,
    )
    assert "fragmenter_release_experience_v1" in command
    assert any(
        value.endswith(f"assets{build_fragmenter_release.os.pathsep}assets")
        for value in command
    )


def test_release_builder_pins_active_visual_runtime() -> None:
    command = build_fragmenter_release.pyinstaller_command(
        ROOT,
        ROOT / "runtime" / build_fragmenter_release.BRIDGE_NAME,
    )
    for module in build_fragmenter_release.VISUAL_RUNTIME_MODULES:
        assert module in command
        assert (TOOLS / f"{module}.py").is_file()

    assert visual_runtime_v6.scene_v9.render_textured_scene is visual_runtime_v6.renderer_v5.render_textured_scene
    assert visual_runtime_v6.visual_controller_v1.extract_animation_fast is visual_runtime_v6.puppetry_v1.export_puppetry_report


def test_visual_preview_execution_is_in_process_for_source_and_exe() -> None:
    worker_source = inspect.getsource(gui_v2.PublicFragmenterAppV2._local_worker)
    responsive_source = inspect.getsource(gui_v16.PublicFragmenterAppV16._render_progressive)
    camera_source = inspect.getsource(gui_v16.PublicFragmenterAppV16._start_camera_interactive_render)

    assert "threading.Thread" in worker_source
    assert "subprocess" not in worker_source
    assert "scene_v9.render_textured_scene" in responsive_source
    assert "scene_v9.render_textured_scene" in camera_source


def test_launcher_installs_release_experience_for_both_launch_modes() -> None:
    launcher = (ROOT / "fragmenter_public.py").read_text(encoding="utf-8")
    assert "fragmenter_release_experience_v1" in launcher
    assert "install_release_experience()" in launcher
    assert "if getattr(sys, 'frozen'" not in launcher

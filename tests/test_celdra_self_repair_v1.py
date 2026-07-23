from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_fragmenter_release
import celdra_containment_override_v1 as containment
import operation_dragonegg_v1 as dragonegg


def test_whiteout_cues_use_the_existing_dramatic_line_fade() -> None:
    faded: list[str] = []
    plain: list[str] = []

    class Stub:
        _celdra_whiteout_active_v89 = True
        _operation_dragonegg_cues_v1: set[str] = set()
        _operation_dragonegg_baby_frames_v1 = []
        _operation_dragonegg_baby_load_attempted_v1 = False
        _operation_dragonegg_baby_log_v1 = False
        _operation_dragonegg_restore_requested_v1 = False
        _fragmenter_celdra_egg_retired_v1 = True

        def _append_whiteout_celdra_line_v89(self, text: str) -> None:
            faded.append(text)

        def _append_console_v49(self, text: str) -> None:
            plain.append(text)

    stub = Stub()
    dragonegg._emit_energy_cue(
        stub,
        "initialized",
        "[CELDRA] INITIALIZED",
        whiteout=True,
    )
    dragonegg._emit_energy_cue(
        stub,
        "online",
        "[CELDRA] ONLINE",
        whiteout=True,
    )

    assert faded == ["INITIALIZED", "ONLINE"]
    assert plain == []


def test_online_schedules_baby_release_console_restore_and_watchdog() -> None:
    releases: list[int] = []
    scheduled: list[tuple[int, object]] = []
    restores: list[str] = []

    class Stub:
        _operation_dragonegg_restore_requested_v1 = False
        _operation_dragonegg_cues_v1: set[str] = set()
        _operation_dragonegg_baby_frames_v1 = []
        _operation_dragonegg_baby_load_attempted_v1 = False
        _operation_dragonegg_baby_log_v1 = False
        _fragmenter_celdra_egg_retired_v1 = True
        _celdra_whiteout_active_v89 = True

        def _schedule_hatch_release_v91(self, delay: int) -> None:
            releases.append(delay)

        def _scaled_runtime_ms_v88(self, value: int) -> int:
            return value

        def _remember_after_v49(self, delay: int, callback) -> None:
            scheduled.append((delay, callback))

        def _start_console_restore_v89(self) -> None:
            restores.append("fade")

        def _restore_console_palette_v89(self) -> None:
            restores.append("hard")

    stub = Stub()
    dragonegg._request_console_and_hatch_release(stub)

    assert releases == [1_250]
    assert [delay for delay, _callback in scheduled] == [850, 6_000]
    scheduled[0][1]()
    assert restores == ["fade"]
    scheduled[1][1]()
    assert restores == ["fade", "hard"]


def test_canonical_baby_uses_the_inherited_hidden_whiteout_release() -> None:
    source = inspect.getsource(dragonegg._begin_hatch_gif_final)
    assert "_ORIGINAL_BEGIN_HATCH_GIF(self)" in source
    assert "_play_external_sequence_v50" not in source


def test_packaged_state_is_owned_by_the_extracted_release() -> None:
    launcher = (ROOT / "fragmenter_public.py").read_text(encoding="utf-8")
    assert 'Path(sys.executable).resolve().parent if bool(getattr(sys, "frozen", False))' in launcher
    assert '"FRAGMENTER_STATE_ROOT"' in launcher
    assert 'APPLICATION_ROOT / ".fragmenter_state"' in launcher


def test_secret_tab_gate_refuses_incomplete_collection(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(containment, "load_memory", lambda: {"stable": ["BYTE"]})
    monkeypatch.setattr(containment, "collection_complete", lambda _state: False)
    monkeypatch.setattr(containment, "_ORIGINAL_SYNC_TAB", lambda _self: calls.append("open"))

    class Stub:
        notebook = None
        _celdra_unlock_frame_v109 = None
        tabs: dict[str, object] = {}

        def _stop_gremlin_gallery_v112(self) -> None:
            calls.append("stop")

    containment._sync_secret_celdra_tab(Stub())
    assert "open" not in calls


def test_secret_tab_gate_opens_only_after_real_nine_of_nine(monkeypatch) -> None:
    calls: list[str] = []
    complete = {"stable": list(containment.KNOWN_GREMLINS)}
    monkeypatch.setattr(containment, "load_memory", lambda: complete)
    monkeypatch.setattr(containment, "collection_complete", lambda state: state is complete)
    monkeypatch.setattr(containment, "_ORIGINAL_SYNC_TAB", lambda _self: calls.append("open"))

    class Stub:
        pass

    containment._sync_secret_celdra_tab(Stub())
    assert calls == ["open"]


def test_opening_scene_is_a_roster_not_persistent_stable(monkeypatch) -> None:
    console: list[str] = []

    def original(instance) -> None:
        instance._celdra_internal_show_v101 = True
        instance._celdra_middle_mode_v101 = "stable"

    monkeypatch.setattr(containment, "_ORIGINAL_START_SHOW", original)

    class Stub:
        _celdra_internal_show_v101 = False
        _celdra_middle_mode_v101 = ""
        _celdra_containment_intro_notice_v1 = False

        def _update_middle_header_v101(self) -> None:
            pass

        def _append_console_v49(self, text: str) -> None:
            console.append(text)

    stub = Stub()
    containment._start_directed_gremlin_show(stub)
    assert stub._celdra_middle_mode_v101 == "roster"
    assert any("INTRODUCTION QUEUE" in line for line in console)
    assert any("SECRET MENU" in line for line in console)


def test_completed_gallery_uses_live_vector_gremlins_not_generated_files() -> None:
    source = inspect.getsource(containment._build_live_celdra_gallery)
    assert "draw_gremlin" in source
    assert "PhotoImage" not in source
    assert "gremlins/v112" not in source


def test_release_pins_celdras_containment_override() -> None:
    command = build_fragmenter_release.pyinstaller_command(
        ROOT,
        ROOT / "runtime" / build_fragmenter_release.BRIDGE_NAME,
    )
    assert "celdra_containment_override_v1" in command
    assert (
        ROOT / "tools" / "celdra_containment_override_v1.py"
        in build_fragmenter_release._required_runtime_modules(ROOT)
    )


def test_launcher_installs_containment_after_dragonegg_before_main() -> None:
    launcher = (ROOT / "fragmenter_public.py").read_text(encoding="utf-8")
    dragonegg_at = launcher.index("install_operation_dragonegg()")
    containment_at = launcher.index("install_celdra_containment_override()")
    main_at = launcher.index("from fragmenter_public_gui_v127 import main")
    assert dragonegg_at < containment_at < main_at

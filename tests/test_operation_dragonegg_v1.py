from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_fragmenter_release
import operation_dragonegg_v1 as dragonegg


class FakeCanvas:
    def __init__(self) -> None:
        self.deleted = 0
        self.configured: dict[str, object] = {}
        self.images: list[object] = []

    def delete(self, _value: str) -> None:
        self.deleted += 1

    def configure(self, **kwargs) -> None:
        self.configured.update(kwargs)

    def create_image(self, _x: int, _y: int, *, image, anchor: str) -> None:
        assert anchor == "center"
        self.images.append(image)

    def winfo_width(self) -> int:
        return 640

    def winfo_height(self) -> int:
        return 420


class RedrawStub:
    def __init__(self) -> None:
        self._fragmenter_celdra_egg_retired_v1 = True
        self._operation_dragonegg_cues_v1 = set()
        self._operation_dragonegg_baby_frames_v1 = []
        self._operation_dragonegg_baby_load_attempted_v1 = False
        self._operation_dragonegg_baby_log_v1 = False
        self._celdra_energy_active_v63 = False
        self._celdra_takeover_active_v58 = False
        self.celdra_current_external_v50 = None
        self.celdra_avatar_canvas_v50 = FakeCanvas()
        self.energy_draws = 0
        self.whiteout_draws = 0

    def _draw_energy_wave_v63(self, _canvas, _width: int, _height: int) -> None:
        self.energy_draws += 1

    def _draw_whiteout_v63(self, _canvas, _width: int, _height: int) -> None:
        self.whiteout_draws += 1


def test_final_cut_cues_complete_before_baby_reveal_and_fade() -> None:
    assert dragonegg.WHITEOUT_COMMIT_STEP < dragonegg.INITIALIZED_STEP
    assert dragonegg.INITIALIZED_STEP < dragonegg.ONLINE_STEP
    assert dragonegg.ONLINE_STEP < dragonegg.BABY_HANDOFF_STEP
    assert dragonegg.BABY_HANDOFF_STEP < dragonegg.WHITEOUT_FADE_STEP


def test_late_timeline_cues_are_suppressed(monkeypatch) -> None:
    forwarded: list[object] = []
    monkeypatch.setattr(
        dragonegg,
        "_ORIGINAL_EMIT_TIMELINE",
        lambda _instance, event: forwarded.append(event),
    )
    stub = SimpleNamespace()

    for speaker, text in (
        ("CELDRA", "INITIALIZED"),
        ("CELDRA", "ONLINE"),
        ("BRAIN", "...OKAY. THAT WAS A LOT."),
    ):
        dragonegg._emit_timeline_event_final(
            stub,
            SimpleNamespace(action="console", speaker=speaker, text=text),
        )
    assert forwarded == []

    control = SimpleNamespace(action="console", speaker="CORE", text="CONTROL")
    dragonegg._emit_timeline_event_final(stub, control)
    assert forwarded == [control]


def test_energy_tick_emits_each_final_cut_cue_once(monkeypatch) -> None:
    lines: list[str] = []
    handed_off: list[bool] = []

    class Stub:
        _operation_dragonegg_cues_v1 = set()
        _operation_dragonegg_baby_frames_v1 = []
        _operation_dragonegg_baby_load_attempted_v1 = False
        _operation_dragonegg_baby_log_v1 = False
        _fragmenter_celdra_egg_retired_v1 = False
        _celdra_avatar_after_v49 = None
        _celdra_energy_gif_started_v63 = False
        celdra_current_pixel_v50 = object()
        celdra_current_external_v50 = None

        def _append_console_v49(self, text: str) -> None:
            lines.append(text)

    stub = Stub()
    monkeypatch.setattr(dragonegg, "_ORIGINAL_TICK_ENERGY", lambda _instance: None)
    monkeypatch.setattr(
        dragonegg,
        "_begin_hatch_gif_final",
        lambda instance: handed_off.append(True),
    )

    for step in (
        dragonegg.INITIALIZED_STEP,
        dragonegg.INITIALIZED_STEP,
        dragonegg.ONLINE_STEP,
        dragonegg.BRAIN_REACTION_STEP,
        dragonegg.BABY_HANDOFF_STEP,
    ):
        stub._celdra_energy_step_v63 = step
        dragonegg._tick_energy_hatch_final(stub)

    assert lines == [
        "[CELDRA] INITIALIZED",
        "[CELDRA] ONLINE",
        "[BRAIN] ...OKAY. THAT WAS A LOT.",
    ]
    assert handed_off == [True]


def test_post_hatch_blank_uses_serenial_logo_not_original_egg(monkeypatch) -> None:
    original_calls: list[bool] = []
    logo = object()
    monkeypatch.setattr(dragonegg, "_ORIGINAL_REDRAW", lambda _instance: original_calls.append(True))
    monkeypatch.setattr(dragonegg.release_experience, "_fallback_logo", lambda _instance: logo)

    stub = RedrawStub()
    dragonegg._redraw_celdra_final(stub)

    assert original_calls == []
    assert stub.celdra_avatar_canvas_v50.images == [logo]
    assert stub.celdra_avatar_canvas_v50.configured["background"] == "#05070b"


def test_explosion_blank_stays_black_until_baby_is_installed(monkeypatch) -> None:
    monkeypatch.setattr(
        dragonegg.release_experience,
        "_fallback_logo",
        lambda _instance: (_ for _ in ()).throw(AssertionError("logo flashed during whiteout")),
    )
    stub = RedrawStub()
    stub._celdra_energy_active_v63 = True

    dragonegg._redraw_celdra_final(stub)

    assert stub.celdra_avatar_canvas_v50.images == []
    assert stub.energy_draws == 1
    assert stub.whiteout_draws == 1


def test_post_hatch_external_frame_is_drawn_directly() -> None:
    stub = RedrawStub()
    frame = object()
    stub.celdra_current_external_v50 = frame

    dragonegg._redraw_celdra_final(stub)

    assert stub.celdra_avatar_canvas_v50.images == [frame]


def test_exact_baby_asset_and_release_packaging_are_pinned() -> None:
    baby = ROOT / "assets" / "celdra" / dragonegg.BABY_DRAGON_RELATIVE
    assert baby.is_file()
    assert dragonegg.BABY_DRAGON_RELATIVE.as_posix() == "avatar/01.gif"

    command = build_fragmenter_release.pyinstaller_command(
        ROOT,
        ROOT / "runtime" / build_fragmenter_release.BRIDGE_NAME,
    )
    assert "operation_dragonegg_v1" in command
    assert ROOT / "tools" / "operation_dragonegg_v1.py" in build_fragmenter_release._required_runtime_modules(ROOT)


def test_launcher_installs_final_cut_after_release_path_policy() -> None:
    launcher = (ROOT / "fragmenter_public.py").read_text(encoding="utf-8")
    release_at = launcher.index("install_release_experience()")
    dragonegg_at = launcher.index("install_operation_dragonegg()")
    gui_at = launcher.index("from fragmenter_public_gui_v127 import main")
    assert release_at < dragonegg_at < gui_at


def test_final_redraw_source_never_delegates_post_hatch_without_dragongirl() -> None:
    source = inspect.getsource(dragonegg._redraw_celdra_final)
    assert "if not bool(self._fragmenter_celdra_egg_retired_v1)" in source
    assert "if takeover and external is not None" in source
    assert "_draw_post_hatch_fallback" in source

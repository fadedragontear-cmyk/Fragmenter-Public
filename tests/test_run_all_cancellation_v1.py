from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_all_cancellation_v1 as cancellation
import run_all_cancel_ui_v1 as cancel_ui


def test_cancel_failure_is_normalized_and_persisted(tmp_path: Path) -> None:
    report_path = tmp_path / "pipeline_last.json"
    report = {
        "status": "failed",
        "report_path": str(report_path),
        "results": [
            {
                "key": "ccsf_extract",
                "status": "failed",
                "message": "RunAllCancellation: Cancellation requested by operator.",
            }
        ],
    }
    event = threading.Event()
    event.set()

    normalized = cancellation._normalize_cancelled_report(report, event)

    assert normalized["status"] == "cancelled"
    assert normalized["results"][0]["status"] == "cancelled"
    assert normalized["cancellation"]["completed_stages_preserved"] is True
    assert normalized["cancellation"]["active_stage_marked_complete"] is False
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "cancelled"


def test_finish_callback_reports_cancelled_instead_of_failed() -> None:
    rows: list[dict[str, object]] = []
    event = threading.Event()
    event.set()
    callback = cancellation._callback_with_cancellation(rows.append, event)
    assert callback is not None

    callback(
        {
            "kind": "finish",
            "stage": "ccsf_extract",
            "status": "failed",
            "error": "RunAllCancellation: Cancellation requested by operator.",
        }
    )

    assert rows[0]["status"] == "cancelled"
    assert rows[0]["error"] == "Cancellation completed."


def test_chunk_scanner_honors_active_cancel_before_reading() -> None:
    previous = getattr(cancellation._ACTIVE, "cancel_event", None)
    event = threading.Event()
    event.set()
    cancellation._ACTIVE.cancel_event = event
    try:
        with pytest.raises(cancellation.RunAllCancellation):
            next(cancellation._iter_chunks_cancellable(Path("does-not-exist.bin")))
    finally:
        if previous is None:
            delattr(cancellation._ACTIVE, "cancel_event")
        else:
            cancellation._ACTIVE.cancel_event = previous


def test_cancel_button_sets_event_updates_ui_and_gets_celdra_ack(monkeypatch) -> None:
    logs: list[str] = []
    console: list[str] = []
    poses: list[tuple[str, str]] = []

    class Variable:
        value = ""

        def set(self, value: str) -> None:
            self.value = value

    class Button:
        state = "normal"

        def configure(self, *, state: str) -> None:
            self.state = state

    class Tree:
        status = "running"

        def get_children(self, _parent: str):
            return ("ccsf_extract",)

        def set(self, _item: str, column: str, value: str | None = None):
            assert column == "status"
            if value is None:
                return self.status
            self.status = value
            return value

    class Stub:
        task_active = True
        cancel_event = threading.Event()
        current_task_label = Variable()
        cancel_button = Button()
        run_tree = Tree()

        def _append_log(self, text: str) -> None:
            logs.append(text)

        def _append_console_v49(self, text: str) -> None:
            console.append(text)

        def _runtime_pose_v70(self, pose: str, text: str) -> None:
            poses.append((pose, text))

    monkeypatch.setattr(
        cancel_ui,
        "_ORIGINAL_CANCEL",
        lambda instance: instance.cancel_event.set(),
    )

    stub = Stub()
    cancel_ui._cancel_task_cancellable(stub)

    assert stub.cancel_event.is_set()
    assert stub.current_task_label.value.startswith("Stopping")
    assert stub.cancel_button.state == "disabled"
    assert stub.run_tree.status == "cancelling"
    assert any("Cancellation requested" in row for row in logs)
    assert any("CANCELLATION REQUEST" in row for row in console)
    assert poses and poses[0][0] == "confused"


def test_cancel_completion_is_acknowledged(monkeypatch) -> None:
    logs: list[str] = []
    console: list[str] = []

    class Stub:
        def _append_log(self, text: str) -> None:
            logs.append(text)

        def _append_console_v49(self, text: str) -> None:
            console.append(text)

        def _runtime_pose_v70(self, _pose: str, _text: str) -> None:
            pass

    monkeypatch.setattr(cancel_ui, "_ORIGINAL_RUN_ALL_DONE", lambda *_args: None)
    cancel_ui._run_all_done_cancellable(Stub(), {"status": "cancelled"}, None)

    assert any("RUN ALL cancelled" in row for row in logs)
    assert any("CANCELLATION COMPLETE" in row for row in console)


def test_launcher_installs_core_and_ui_cancellation() -> None:
    launcher = (ROOT / "fragmenter_public.py").read_text(encoding="utf-8")
    assert "install_run_all_cancellation()" in launcher
    assert "install_run_all_cancel_ui()" in launcher

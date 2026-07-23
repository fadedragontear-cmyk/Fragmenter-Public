#!/usr/bin/env python3
"""Cooperative cancellation for in-process and packaged RUN ALL stages.

The Windows one-file build executes its longest CCSF stages inside Fragmenter rather
than in a child process.  A threading.Event alone therefore cannot terminate them.
This policy installs cancellation checks at the shared pipeline, progress, file-chunk,
and asset-iteration boundaries while preserving completed-stage reuse state.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

import binary_preview
import ccsf_asset_indexer
import run_all_executor_v8 as executor_v8
import run_all_executor_v9 as executor_v9


class RunAllCancellation(RuntimeError):
    """Raised cooperatively inside the RUN ALL worker thread."""


_INSTALLED = False
_ACTIVE = threading.local()
_ORIGINAL_EXECUTE_PIPELINE = executor_v8.execute_pipeline_v8
_ORIGINAL_INTERNAL = executor_v8._run_internal_v8
_ORIGINAL_PROGRESS_BRIDGE = executor_v8._progress_bridge
_ORIGINAL_CCSF_PROGRESS = executor_v9._ccsf_progress_v9
_ORIGINAL_ITER_CHUNKS = binary_preview.iter_chunks
_ORIGINAL_ITER_CANDIDATES = ccsf_asset_indexer.iter_candidates
_CANCEL_MESSAGE = "Cancellation requested by operator."


def _active_cancel_event() -> Any:
    return getattr(_ACTIVE, "cancel_event", None)


def cancellation_requested(event: Any = None) -> bool:
    selected = event if event is not None else _active_cancel_event()
    try:
        return bool(selected is not None and selected.is_set())
    except (AttributeError, TypeError):
        return False


def _raise_if_cancelled() -> None:
    if cancellation_requested():
        raise RunAllCancellation(_CANCEL_MESSAGE)


def _cancel_failure(value: Any) -> bool:
    text = str(value or "")
    return "RunAllCancellation" in text or _CANCEL_MESSAGE in text


def _callback_with_cancellation(
    callback: Callable[[dict[str, Any]], None] | None,
    cancel_event: Any,
) -> Callable[[dict[str, Any]], None] | None:
    if callback is None:
        return None

    def emit(event: dict[str, Any]) -> None:
        payload = dict(event)
        if (
            cancellation_requested(cancel_event)
            and str(payload.get("kind") or "") == "finish"
            and str(payload.get("status") or "") == "failed"
            and _cancel_failure(payload.get("error") or payload.get("message"))
        ):
            payload["status"] = "cancelled"
            payload["error"] = "Cancellation completed."
            payload["message"] = "Cancellation completed."
        callback(payload)

    return emit


def _rewrite_report(report: dict[str, Any]) -> None:
    value = str(report.get("report_path") or "").strip()
    if not value:
        return
    target = Path(value)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    except OSError:
        # Cancellation must still return control to the GUI if report persistence fails.
        pass


def _normalize_cancelled_report(report: dict[str, Any], cancel_event: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        return report
    rows = report.get("results") if isinstance(report.get("results"), list) else []
    changed = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "") == "failed" and _cancel_failure(row.get("message")):
            row["status"] = "cancelled"
            row["message"] = "Cancellation completed during the active stage."
            changed = True
    cancelled = any(
        isinstance(row, dict) and str(row.get("status") or "") == "cancelled"
        for row in rows
    )
    if cancelled or (cancellation_requested(cancel_event) and changed):
        report["status"] = "cancelled"
        report["cancellation"] = {
            "requested": True,
            "acknowledged": True,
            "completed_stages_preserved": True,
            "active_stage_marked_complete": False,
        }
        changed = True
    if changed:
        _rewrite_report(report)
    return report


def execute_pipeline_cancellable(
    project: Any,
    *,
    stage_keys: Iterable[str] | None = None,
    reuse: bool = True,
    callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: Any = None,
    subprocess_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    previous = getattr(_ACTIVE, "cancel_event", None)
    _ACTIVE.cancel_event = cancel_event
    wrapped_callback = _callback_with_cancellation(callback, cancel_event)
    try:
        report = _ORIGINAL_EXECUTE_PIPELINE(
            project,
            stage_keys=stage_keys,
            reuse=reuse,
            callback=wrapped_callback,
            cancel_event=cancel_event,
            subprocess_runner=subprocess_runner,
        )
    finally:
        if previous is None:
            try:
                delattr(_ACTIVE, "cancel_event")
            except AttributeError:
                pass
        else:
            _ACTIVE.cancel_event = previous
    return _normalize_cancelled_report(report, cancel_event)


def _run_internal_cancellable(action: Any, project: Any, callback: Any) -> dict[str, Any]:
    _raise_if_cancelled()
    payload = _ORIGINAL_INTERNAL(action, project, callback)
    _raise_if_cancelled()
    return payload


def _progress_bridge_cancellable(callback: Any, stage: str):
    emit_original = _ORIGINAL_PROGRESS_BRIDGE(callback, stage)

    def emit(payload: dict[str, Any]) -> None:
        _raise_if_cancelled()
        emit_original(payload)
        _raise_if_cancelled()

    return emit


def _ccsf_progress_cancellable(callback: Any, stage: str):
    emit_original = _ORIGINAL_CCSF_PROGRESS(callback, stage)

    def emit(payload: dict[str, Any]) -> None:
        _raise_if_cancelled()
        emit_original(payload)
        _raise_if_cancelled()

    return emit


def _iter_chunks_cancellable(*args: Any, **kwargs: Any):
    _raise_if_cancelled()
    for item in _ORIGINAL_ITER_CHUNKS(*args, **kwargs):
        _raise_if_cancelled()
        yield item
    _raise_if_cancelled()


def _iter_candidates_cancellable(*args: Any, **kwargs: Any):
    _raise_if_cancelled()
    for item in _ORIGINAL_ITER_CANDIDATES(*args, **kwargs):
        _raise_if_cancelled()
        yield item
    _raise_if_cancelled()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # execute_run_all_v8/v9 resolve execute_pipeline_v8 by module global at runtime.
    executor_v8.execute_pipeline_v8 = execute_pipeline_cancellable

    # RUN ALL v9 installed its internal dispatcher into the v8 module. Patch both
    # names so direct tests and future imports observe the same cooperative checks.
    executor_v8._run_internal_v8 = _run_internal_cancellable
    executor_v9._run_internal_v9 = _run_internal_cancellable

    executor_v8._progress_bridge = _progress_bridge_cancellable
    executor_v9._ccsf_progress_v9 = _ccsf_progress_cancellable

    # The CCSF scanner reads one MiB chunks. This gives the packaged extraction stage
    # a frequent cancellation boundary without corrupting the currently written file.
    binary_preview.iter_chunks = _iter_chunks_cancellable
    ccsf_asset_indexer.iter_candidates = _iter_candidates_cancellable
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Import and install this module from fragmenter_public.py.")

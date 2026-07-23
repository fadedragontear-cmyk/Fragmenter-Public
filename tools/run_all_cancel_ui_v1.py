#!/usr/bin/env python3
"""RUN ALL cancellation presentation shared by source and frozen builds."""
from __future__ import annotations

import tkinter as tk
from typing import Any

import fragmenter_public_gui_v127 as gui_v127


_INSTALLED = False
_ORIGINAL_CANCEL = gui_v127.PublicFragmenterAppV127._cancel_task
_ORIGINAL_RUN_ALL_DONE = gui_v127.PublicFragmenterAppV127._run_all_done


def _append_console(self: Any, text: str) -> None:
    callback = getattr(self, "_append_console_v49", None)
    if callable(callback):
        try:
            callback(text)
        except Exception:
            # Presentation must never interfere with the cancellation signal.
            pass


def _show_celdra_acknowledgement(self: Any, *, complete: bool) -> None:
    if complete:
        text = (
            "Cancelled. Completed stages are still usable, and the interrupted stage "
            "was not marked complete. You can restart RUN ALL when ready."
        )
        pose = "unenthused"
        _append_console(self, "[CORE] RUN ALL CANCELLATION COMPLETE")
        _append_console(
            self,
            "[BRAIN] STOPPED. I KEPT THE FINISHED WORK AND LEFT THE ACTIVE STAGE INCOMPLETE.",
        )
    else:
        text = (
            "Cancellation received. I am stopping the active stage safely. Keep "
            "Fragmenter open for a moment while the worker exits."
        )
        pose = "confused"
        _append_console(self, "[CORE] OPERATOR CANCELLATION REQUEST RECEIVED")
        _append_console(
            self,
            "[BRAIN] OKAY. STOPPING THE CURRENT JOB SAFELY. DON'T CLOSE ME YET.",
        )

    runtime_pose = getattr(self, "_runtime_pose_v70", None)
    if callable(runtime_pose):
        try:
            runtime_pose(pose, text)
        except Exception:
            pass

    # Draw the same message directly as well. A missing reaction image can make the
    # runtime pose return without showing its bubble, but cancellation still needs a
    # visible Celdra acknowledgement.
    bubble = getattr(self, "_show_speech_bubble_v58", None)
    if callable(bubble):
        try:
            bubble(text)
        except Exception:
            pass


def _mark_active_stage_cancelling(self: Any) -> None:
    tree = getattr(self, "run_tree", None)
    if tree is None:
        return
    try:
        for item in tree.get_children(""):
            if str(tree.set(item, "status") or "").casefold() == "running":
                tree.set(item, "status", "cancelling")
    except (AttributeError, tk.TclError):
        pass


def _cancel_task_cancellable(self: Any) -> None:
    if not bool(getattr(self, "task_active", False)):
        return
    event = getattr(self, "cancel_event", None)
    try:
        already_requested = bool(event is not None and event.is_set())
    except AttributeError:
        already_requested = False
    if already_requested:
        return

    _ORIGINAL_CANCEL(self)
    try:
        self.current_task_label.set("Stopping current stage safely…")
    except (AttributeError, tk.TclError):
        pass
    try:
        self.cancel_button.configure(state="disabled")
    except (AttributeError, tk.TclError):
        pass
    append_log = getattr(self, "_append_log", None)
    if callable(append_log):
        append_log(
            "Cancellation requested. Fragmenter is stopping the active stage safely; "
            "completed stages will remain reusable."
        )
    _mark_active_stage_cancelling(self)
    _show_celdra_acknowledgement(self, complete=False)


def _run_all_done_cancellable(self: Any, result: Any, error: Exception | None) -> None:
    _ORIGINAL_RUN_ALL_DONE(self, result, error)
    status = str(result.get("status") or "") if isinstance(result, dict) else ""
    cancelled_error = error is not None and "RunAllCancellation" in type(error).__name__
    if status != "cancelled" and not cancelled_error:
        return

    append_log = getattr(self, "_append_log", None)
    if callable(append_log):
        append_log(
            "RUN ALL cancelled. Completed stages remain reusable; the interrupted "
            "stage was not marked complete."
        )
    _show_celdra_acknowledgement(self, complete=True)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    gui_v127.PublicFragmenterAppV127._cancel_task = _cancel_task_cancellable
    gui_v127.PublicFragmenterAppV127._run_all_done = _run_all_done_cancellable
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Import and install this module from fragmenter_public.py.")

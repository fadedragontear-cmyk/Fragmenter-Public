#!/usr/bin/env python3
"""V49: dynamic Celdra presentation layered safely over the canonical pipeline."""
from __future__ import annotations

import math
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Iterable

from celdra_presentation_v1 import (
    ALT_F4_FIRST,
    ALT_F4_SECOND,
    FAILURE_CUES,
    FIRST_DONE_CUES,
    FIRST_SCAN_CUES,
    RETURNING_DONE_CUES,
    RETURNING_START_CUES,
    STAGE_CUES,
    CeldraCue,
)
from fragmenter_public_gui_v48 import PublicFragmenterAppV48
from run_all_executor_v8 import execute_run_all_v8, is_first_scan_v8
from settings_v1 import FragmenterSettingsV1, load_project_settings, save_project_settings


class PublicFragmenterAppV49(PublicFragmenterAppV48):
    """Give Celdra a non-blocking console, one-way chat, avatar, and UI cues."""

    def __init__(self) -> None:
        self._celdra_console_v49: tk.Text | None = None
        self._celdra_chat_v49: tk.Text | None = None
        self._celdra_notebook_v49: ttk.Notebook | None = None
        self._celdra_chat_frame_v49: ttk.Frame | None = None
        self._celdra_avatar_label_v49: ttk.Label | None = None
        self._celdra_bubble_v49: tk.StringVar | None = None
        self._celdra_fake_status_v49: tk.StringVar | None = None
        self._celdra_fake_progress_v49: ttk.Progressbar | None = None
        self._celdra_expand_button_v49: ttk.Button | None = None
        self._celdra_chat_button_v49: ttk.Button | None = None
        self._celdra_host_v49: ttk.LabelFrame | None = None
        self._run_bottom_v49: ttk.Frame | None = None
        self._celdra_after_ids_v49: list[str] = []
        self._celdra_avatar_after_v49: str | None = None
        self._celdra_bubble_after_v49: str | None = None
        self._celdra_avatar_frames_v49: dict[str, list[tk.PhotoImage]] = {}
        self._celdra_avatar_state_v49 = "idle"
        self._celdra_avatar_index_v49 = 0
        self._celdra_chat_visible_v49 = False
        self._celdra_expanded_v49 = False
        self._celdra_session_active_v49 = False
        self._celdra_first_scan_v49 = False
        self._celdra_seen_stages_v49: set[str] = set()
        self._celdra_failure_shown_v49 = False
        self._celdra_alt_f4_count_v49 = 0
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Dynamic Pipeline")
        self.bind_all("<Alt-F4>", self._celdra_alt_f4_v49, add="+")

    # ------------------------------------------------------------------
    # RUN ALL presentation shell
    # ------------------------------------------------------------------
    def _build_run_all(self, parent: ttk.Frame) -> None:
        super()._build_run_all(parent)
        old_console = self._celdra_console_v38
        if old_console is None:
            return
        host = old_console.master
        if not isinstance(host, ttk.LabelFrame):
            return
        for child in tuple(host.winfo_children()):
            child.destroy()
        host.configure(text="Celdra — local assistant / flavor layer")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(1, weight=1)
        self._celdra_host_v49 = host
        if isinstance(host.master, ttk.Frame):
            self._run_bottom_v49 = host.master

        header = ttk.Frame(host)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Presentation progress is intentionally separate from real pipeline progress.",
        ).grid(row=0, column=0, sticky="w")
        self._celdra_chat_button_v49 = ttk.Button(
            header,
            text="Show Chat",
            command=lambda: self._show_celdra_chat_v49(force=True),
        )
        self._celdra_chat_button_v49.grid(row=0, column=1, padx=(5, 0))
        self._celdra_expand_button_v49 = ttk.Button(
            header,
            text="Expand",
            command=lambda: self._set_celdra_expanded_v49(
                not self._celdra_expanded_v49, force=True
            ),
        )
        self._celdra_expand_button_v49.grid(row=0, column=2, padx=(5, 0))

        body = ttk.Panedwindow(host, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew")

        avatar = ttk.Frame(body, padding=4)
        avatar.columnconfigure(0, weight=1)
        avatar.rowconfigure(0, weight=1)
        self._celdra_avatar_label_v49 = ttk.Label(
            avatar,
            text="CELDRA\nAvatar keyframes not installed",
            anchor="center",
            justify="center",
        )
        self._celdra_avatar_label_v49.grid(row=0, column=0, sticky="nsew")
        self._celdra_bubble_v49 = tk.StringVar(value="")
        ttk.Label(
            avatar,
            textvariable=self._celdra_bubble_v49,
            wraplength=300,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 3))
        self._celdra_fake_status_v49 = tk.StringVar(value="[CELDRA] OFFLINE")
        ttk.Label(
            avatar,
            textvariable=self._celdra_fake_status_v49,
            wraplength=300,
        ).grid(row=2, column=0, sticky="ew")
        self._celdra_fake_progress_v49 = ttk.Progressbar(
            avatar,
            maximum=100.0,
            mode="determinate",
            style="Accent.Horizontal.TProgressbar",
        )
        self._celdra_fake_progress_v49.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        body.add(avatar, weight=2)

        notebook = ttk.Notebook(body)
        self._celdra_notebook_v49 = notebook
        console_frame = ttk.Frame(notebook)
        chat_frame = ttk.Frame(notebook)
        self._celdra_chat_frame_v49 = chat_frame
        notebook.add(console_frame, text="System console")
        notebook.add(chat_frame, text="One-way chat")

        for frame in (console_frame, chat_frame):
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)

        console = tk.Text(
            console_frame,
            wrap="word",
            state="disabled",
            background="#10151d",
            foreground="#b9c8da",
            insertbackground="#b9c8da",
        )
        console_y = ttk.Scrollbar(console_frame, orient="vertical", command=console.yview)
        console.configure(yscrollcommand=console_y.set)
        console.grid(row=0, column=0, sticky="nsew")
        console_y.grid(row=0, column=1, sticky="ns")
        self._celdra_console_v49 = console
        self._celdra_console_v38 = console

        chat = tk.Text(
            chat_frame,
            wrap="word",
            state="disabled",
            background="#151b24",
            foreground="#d6e3f1",
            insertbackground="#d6e3f1",
        )
        chat_y = ttk.Scrollbar(chat_frame, orient="vertical", command=chat.yview)
        chat.configure(yscrollcommand=chat_y.set)
        chat.grid(row=0, column=0, sticky="nsew")
        chat_y.grid(row=0, column=1, sticky="ns")
        ttk.Label(
            chat_frame,
            text="ONE-WAY LINK — INPUT CHANNEL NOT INSTALLED",
            anchor="center",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        self._celdra_chat_v49 = chat
        notebook.hide(chat_frame)
        self._celdra_chat_visible_v49 = False
        body.add(notebook, weight=3)

        self._set_celdra_text_v38(
            "[CORE] CELDRA PRESENTATION LAYER AVAILABLE\n"
            "[CORE] FULL RUN ALL TEMPORARILY ACTIVATES CELDRA\n"
        )
        self._load_celdra_avatar_frames_v49()

    def _build_settings(self, parent: ttk.Frame) -> None:
        super()._build_settings(parent)
        self.setting_vars["celdra_animation"] = tk.BooleanVar(value=True)
        self.setting_vars["celdra_dynamic_ui"] = tk.BooleanVar(value=True)
        self.setting_vars["celdra_alt_f4"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            parent,
            text="Animate Celdra PNG keyframes",
            variable=self.setting_vars["celdra_animation"],
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(
            parent,
            text="Allow Celdra to reveal and resize her UI during RUN ALL",
            variable=self.setting_vars["celdra_dynamic_ui"],
        ).grid(row=11, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(
            parent,
            text="Enable the one-time Alt+F4 easter egg during RUN ALL",
            variable=self.setting_vars["celdra_alt_f4"],
        ).grid(row=12, column=0, columnspan=2, sticky="w", pady=4)
        for child in parent.winfo_children():
            if isinstance(child, ttk.Button) and str(child.cget("text")) == "Save Settings":
                child.grid_configure(row=13)
        ttk.Label(
            parent,
            text=(
                "The Enable Celdra preference controls passive commentary. A full RUN ALL "
                "temporarily activates the local presentation layer so first-scan flavor remains available."
            ),
            wraplength=850,
        ).grid(row=14, column=0, columnspan=2, sticky="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # Persistent settings
    # ------------------------------------------------------------------
    def _load_settings(self) -> None:
        super()._load_settings()
        if self.project is None or "celdra_animation" not in self.setting_vars:
            return
        try:
            settings = load_project_settings(self.project)
        except Exception:
            return
        self.setting_vars["celdra_animation"].set(settings.celdra.animation_enabled)
        self.setting_vars["celdra_dynamic_ui"].set(settings.celdra.dynamic_ui)
        self.setting_vars["celdra_alt_f4"].set(settings.celdra.alt_f4_easter_egg)

    def _save_settings(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            settings = FragmenterSettingsV1()
            settings.appearance.theme = self.setting_vars["theme"].get()
            settings.appearance.accent_color = self.setting_vars["accent"].get()
            settings.appearance.ui_scale = self.setting_vars["scale"].get()
            settings.playback.default_volume = self.setting_vars["volume"].get()
            settings.preview_3d.default_mode = self.setting_vars["preview"].get()
            settings.workspace.reuse_valid_cache = self.setting_vars["cache"].get()
            settings.workspace.keep_diagnostics = self.setting_vars["diagnostics"].get()
            settings.advanced.enable_experimental_tools = self.setting_vars["experimental"].get()
            settings.celdra.enabled = self.setting_vars["celdra"].get()
            settings.celdra.checklist_commentary = self.setting_vars["celdra_commentary"].get()
            settings.celdra.animation_enabled = self.setting_vars["celdra_animation"].get()
            settings.celdra.dynamic_ui = self.setting_vars["celdra_dynamic_ui"].get()
            settings.celdra.alt_f4_easter_egg = self.setting_vars["celdra_alt_f4"].get()
            save_project_settings(project, settings)
            messagebox.showinfo("Settings", "Project settings saved.")
        except Exception as exc:
            messagebox.showerror("Settings", str(exc))

    # ------------------------------------------------------------------
    # Non-blocking script and pipeline integration
    # ------------------------------------------------------------------
    def _run_all(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        self.cancel_event = threading.Event()
        first_scan = is_first_scan_v8(project)
        self._celdra_first_scan_v38 = False  # disable the older V38 scripted layer
        self._start_celdra_session_v49(first_scan)
        self._set_busy(True, "RUN ALL")
        self.run_log.delete("1.0", "end")
        self.overall_progress["value"] = 0.0
        self.overall_progress_label.set("Overall progress: starting")

        def callback(event: dict[str, Any]) -> None:
            self.events.put({"kind": "run_event", "event": event})

        self._background(
            "RUN ALL",
            lambda: execute_run_all_v8(
                project,
                callback=callback,
                cancel_event=self.cancel_event,
            ),
            self._run_all_done,
            already_busy=True,
        )

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        super()._handle_run_event(event)
        if not self._celdra_session_active_v49:
            return
        stage = str(event.get("stage") or "")
        kind = str(event.get("kind") or "")
        if (
            kind == "start"
            and self._celdra_first_scan_v49
            and stage in STAGE_CUES
            and stage not in self._celdra_seen_stages_v49
        ):
            self._celdra_seen_stages_v49.add(stage)
            self._schedule_celdra_cues_v49(STAGE_CUES[stage])
        elif kind == "finish" and str(event.get("status") or "") == "failed":
            self._show_celdra_failure_v49()

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        failed = bool(error) or bool(result and result.get("status") == "failed")
        if failed:
            self._show_celdra_failure_v49()
            end_delay = 4200
        elif self._celdra_first_scan_v49:
            self._schedule_celdra_cues_v49(FIRST_DONE_CUES)
            end_delay = 5200
        else:
            self._schedule_celdra_cues_v49(RETURNING_DONE_CUES)
            end_delay = 3500
        super()._run_all_done(result, error)
        self._remember_after_v49(end_delay, self._end_celdra_session_v49)

    def _start_celdra_session_v49(self, first_scan: bool) -> None:
        self._cancel_celdra_cues_v49()
        self._celdra_session_active_v49 = True
        self._celdra_first_scan_v49 = bool(first_scan)
        self._celdra_seen_stages_v49.clear()
        self._celdra_failure_shown_v49 = False
        self._celdra_alt_f4_count_v49 = 0
        self._set_celdra_text_v38("")
        self._replace_chat_v49("")
        self._set_celdra_fake_progress_v49(0)
        self._set_avatar_state_v49("boot" if first_scan else "idle")
        self._schedule_celdra_cues_v49(
            FIRST_SCAN_CUES if first_scan else RETURNING_START_CUES
        )

    def _end_celdra_session_v49(self) -> None:
        self._celdra_session_active_v49 = False
        self._celdra_alt_f4_count_v49 = 0
        self._set_avatar_state_v49("idle")

    def _show_celdra_failure_v49(self) -> None:
        if self._celdra_failure_shown_v49:
            return
        self._celdra_failure_shown_v49 = True
        self._schedule_celdra_cues_v49(FAILURE_CUES)

    def _schedule_celdra_cues_v49(
        self,
        cues: Iterable[CeldraCue],
        *,
        offset_ms: int = 0,
    ) -> None:
        for cue in cues:
            self._remember_after_v49(
                max(0, int(offset_ms) + int(cue.after_ms)),
                lambda selected=cue: self._emit_celdra_cue_v49(selected),
            )

    def _emit_celdra_cue_v49(self, cue: CeldraCue) -> None:
        if cue.action == "reveal_chat" and self._dynamic_celdra_ui_v49():
            self._show_celdra_chat_v49()
        elif cue.action == "expand" and self._dynamic_celdra_ui_v49():
            self._set_celdra_expanded_v49(True)
        elif cue.action == "compact" and self._dynamic_celdra_ui_v49():
            self._set_celdra_expanded_v49(False)

        if cue.fake_progress is not None:
            self._set_celdra_fake_progress_v49(cue.fake_progress)
        if cue.target == "status":
            if self._celdra_fake_status_v49 is not None:
                self._celdra_fake_status_v49.set(cue.text)
        elif cue.target == "console":
            self._append_console_v49(f"[{cue.speaker}] {cue.text}")
        elif cue.target == "chat":
            self._append_chat_v49(f"Celdra> {cue.text}")

        if cue.avatar:
            self._set_avatar_state_v49(cue.avatar)
        if cue.text and (cue.target == "chat" or cue.speaker == "CELDRA"):
            self._show_celdra_bubble_v49(cue.text)

    def _remember_after_v49(self, delay_ms: int, callback) -> str:
        identifier = self.after(max(0, int(delay_ms)), callback)
        self._celdra_after_ids_v49.append(identifier)
        return identifier

    def _cancel_celdra_cues_v49(self) -> None:
        for identifier in self._celdra_after_ids_v49:
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
        self._celdra_after_ids_v49.clear()

    # ------------------------------------------------------------------
    # Console, chat, bubble, and presentation progress
    # ------------------------------------------------------------------
    def _append_console_v49(self, text: str) -> None:
        widget = self._celdra_console_v49
        if widget is None:
            return
        widget.configure(state="normal")
        widget.insert("end", text.rstrip() + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _replace_chat_v49(self, text: str) -> None:
        widget = self._celdra_chat_v49
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if text:
            widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _append_chat_v49(self, text: str) -> None:
        widget = self._celdra_chat_v49
        if widget is None:
            return
        widget.configure(state="normal")
        widget.insert("end", text.rstrip() + "\n\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _show_celdra_chat_v49(self, *, force: bool = False) -> None:
        notebook = self._celdra_notebook_v49
        frame = self._celdra_chat_frame_v49
        if notebook is None or frame is None:
            return
        if not self._celdra_chat_visible_v49:
            notebook.add(frame, text="One-way chat")
            self._celdra_chat_visible_v49 = True
            if self._celdra_chat_button_v49 is not None:
                self._celdra_chat_button_v49.configure(text="Open Chat")
        notebook.select(frame)
        if force:
            self._set_celdra_expanded_v49(True, force=True)

    def _show_celdra_bubble_v49(self, text: str) -> None:
        if self._celdra_bubble_v49 is None:
            return
        self._celdra_bubble_v49.set(text)
        if self._celdra_bubble_after_v49 is not None:
            try:
                self.after_cancel(self._celdra_bubble_after_v49)
            except tk.TclError:
                pass
        self._celdra_bubble_after_v49 = self.after(
            2600,
            lambda: self._celdra_bubble_v49.set("")
            if self._celdra_bubble_v49 is not None
            else None,
        )

    def _set_celdra_fake_progress_v49(self, value: float) -> None:
        if self._celdra_fake_progress_v49 is not None:
            self._celdra_fake_progress_v49["value"] = max(0.0, min(100.0, float(value)))

    # ------------------------------------------------------------------
    # Dynamic pane sizing
    # ------------------------------------------------------------------
    def _dynamic_celdra_ui_v49(self) -> bool:
        variable = self.setting_vars.get("celdra_dynamic_ui") if hasattr(self, "setting_vars") else None
        return bool(variable.get()) if variable is not None else True

    def _set_celdra_expanded_v49(self, expanded: bool, *, force: bool = False) -> None:
        if not force and not self._dynamic_celdra_ui_v49():
            return
        self._celdra_expanded_v49 = bool(expanded)
        bottom = self._run_bottom_v49
        if bottom is not None:
            bottom.columnconfigure(0, weight=1 if expanded else 2, minsize=260)
            bottom.columnconfigure(1, weight=2 if expanded else 1, minsize=280)
        if self._celdra_expand_button_v49 is not None:
            self._celdra_expand_button_v49.configure(text="Compact" if expanded else "Expand")
        self.after_idle(lambda: self._animate_run_sash_v49(expanded))

    def _animate_run_sash_v49(self, expanded: bool) -> None:
        try:
            total = max(1, int(self.run_paned.winfo_height()))
            current = int(self.run_paned.sashpos(0))
        except (AttributeError, tk.TclError):
            return
        target = int(total * (0.42 if expanded else 0.66))
        steps = 7
        for step in range(1, steps + 1):
            position = round(current + (target - current) * step / steps)
            self._remember_after_v49(
                step * 24,
                lambda value=position: self._set_run_sash_v49(value),
            )

    def _set_run_sash_v49(self, value: int) -> None:
        try:
            self.run_paned.sashpos(0, int(value))
        except (AttributeError, tk.TclError):
            pass

    # ------------------------------------------------------------------
    # PNG avatar keyframes
    # ------------------------------------------------------------------
    def _load_celdra_avatar_frames_v49(self) -> None:
        root = Path(__file__).resolve().parents[1] / "assets" / "celdra" / "avatar"
        groups: dict[str, list[tk.PhotoImage]] = {}
        if root.is_dir():
            for path in sorted(root.glob("*.png")):
                state = path.stem.split("_", 1)[0].casefold() or "idle"
                try:
                    image = tk.PhotoImage(file=str(path))
                    factor = max(
                        1,
                        int(math.ceil(max(image.width() / 300.0, image.height() / 260.0))),
                    )
                    if factor > 1:
                        image = image.subsample(factor, factor)
                except tk.TclError:
                    continue
                groups.setdefault(state, []).append(image)
        self._celdra_avatar_frames_v49 = groups
        self._set_avatar_state_v49("idle")

    def _avatar_animation_enabled_v49(self) -> bool:
        variable = self.setting_vars.get("celdra_animation") if hasattr(self, "setting_vars") else None
        return bool(variable.get()) if variable is not None else True

    def _set_avatar_state_v49(self, state: str) -> None:
        self._celdra_avatar_state_v49 = str(state or "idle").casefold()
        self._celdra_avatar_index_v49 = 0
        if self._celdra_avatar_after_v49 is not None:
            try:
                self.after_cancel(self._celdra_avatar_after_v49)
            except tk.TclError:
                pass
            self._celdra_avatar_after_v49 = None
        self._draw_avatar_frame_v49()

    def _draw_avatar_frame_v49(self) -> None:
        label = self._celdra_avatar_label_v49
        if label is None:
            return
        frames = self._celdra_avatar_frames_v49.get(self._celdra_avatar_state_v49)
        if not frames:
            frames = self._celdra_avatar_frames_v49.get("idle")
        if not frames:
            label.configure(
                image="",
                text=f"CELDRA\n[{self._celdra_avatar_state_v49.upper()}]\nPNG keyframes not installed",
            )
            return
        image = frames[self._celdra_avatar_index_v49 % len(frames)]
        label.configure(image=image, text="")
        label.image = image  # type: ignore[attr-defined]
        if len(frames) > 1 and self._avatar_animation_enabled_v49():
            self._celdra_avatar_index_v49 = (self._celdra_avatar_index_v49 + 1) % len(frames)
            self._celdra_avatar_after_v49 = self.after(180, self._draw_avatar_frame_v49)

    # ------------------------------------------------------------------
    # Alt+F4 easter egg without trapping the user
    # ------------------------------------------------------------------
    def _alt_f4_enabled_v49(self) -> bool:
        variable = self.setting_vars.get("celdra_alt_f4") if hasattr(self, "setting_vars") else None
        return bool(variable.get()) if variable is not None else True

    def _celdra_alt_f4_v49(self, _event: tk.Event) -> str | None:
        if not self._celdra_session_active_v49 or not self.task_active or not self._alt_f4_enabled_v49():
            return None
        self._celdra_alt_f4_count_v49 += 1
        if self._celdra_alt_f4_count_v49 == 1:
            self._show_celdra_chat_v49()
            self._append_chat_v49(f"Celdra> {ALT_F4_FIRST}")
            if self._celdra_fake_status_v49 is not None:
                self._celdra_fake_status_v49.set("[CELDRA] BENCHMARKING USER SUPERSTITION")
            self._set_celdra_expanded_v49(True)
            return "break"
        self._append_chat_v49(f"Celdra> {ALT_F4_SECOND}")
        self.after(100, self._close)
        return "break"

    def _close(self) -> None:
        if self.task_active:
            leave = messagebox.askyesno(
                "Exit Fragmenter",
                "A pipeline task is still running. Exit and request cancellation?",
            )
            if not leave:
                self._celdra_alt_f4_count_v49 = 0
                return
        self._cancel_celdra_cues_v49()
        super()._close()


def main() -> int:
    app = PublicFragmenterAppV49()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

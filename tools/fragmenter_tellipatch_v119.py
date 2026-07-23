#!/usr/bin/env python3
"""V119 GUI for the native Tellipatch phase 1+2 English ISO builder."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tellipatch_native import TellipatchError, build_english_iso, prepare_translation


class FragmenterTellipatchMixinV119:
    def __init__(self) -> None:
        self._english_window_v119: tk.Toplevel | None = None
        self._english_events_v119: queue.Queue = queue.Queue()
        self._english_busy_v119 = False
        super().__init__()
        self.after_idle(self._install_english_menu_v119)

    def _install_english_menu_v119(self) -> None:
        tools_menu = self._find_tools_menu_v118()
        label = "Build Included English ISO..."
        try:
            end = tools_menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(tools_menu.entrycget(index, "label")) == label:
                    return
        except (ValueError, tk.TclError):
            pass
        tools_menu.add_command(label=label, command=self._open_english_builder_v119)

    def _open_english_builder_v119(self) -> None:
        existing = self._english_window_v119
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self)
        self._english_window_v119 = window
        window.title("Fragmenter - Included English ISO")
        window.geometry("780x560")
        window.minsize(700, 500)
        window.protocol("WM_DELETE_WINDOW", self._close_english_builder_v119)
        self._english_source_v119 = tk.StringVar()
        self._english_output_v119 = tk.StringVar()
        self._english_status_v119 = tk.StringVar(
            value="Choose your untouched Japanese .hack//Fragment ISO, then analyze it."
        )
        self._english_progress_v119 = tk.DoubleVar(value=0)

        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="Create an English-playable ISO",
            font=("TkDefaultFont", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Fragmenter applies the included Tellipatch v3.8 XDelta files and the "
                "live English game-line sheet itself. No Python, XDelta, ImgBurn, "
                "Tellipatch, or FragmentUpdater install is needed in the packaged app."
            ),
            wraplength=730,
            justify="left",
        ).pack(fill="x", pady=(4, 12))

        paths = ttk.Frame(outer)
        paths.pack(fill="x")
        paths.columnconfigure(1, weight=1)
        ttk.Label(paths, text="Original ISO").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(paths, textvariable=self._english_source_v119).grid(
            row=0, column=1, sticky="ew", padx=(12, 8), pady=4
        )
        ttk.Button(paths, text="Browse...", command=self._browse_english_source_v119).grid(
            row=0, column=2, pady=4
        )
        ttk.Label(paths, text="New output ISO").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(paths, textvariable=self._english_output_v119).grid(
            row=1, column=1, sticky="ew", padx=(12, 8), pady=4
        )
        ttk.Button(paths, text="Browse...", command=self._browse_english_output_v119).grid(
            row=1, column=2, pady=4
        )

        scope = ttk.LabelFrame(outer, text="Included translation scope", padding=12)
        scope.pack(fill="x", pady=(14, 10))
        ttk.Label(
            scope,
            text=(
                "Included now: all 7 v3.8 binary patches and all 5,768 translated CSV "
                "rows (CP932, original field sizes, verified writes).\n"
                "Not included yet: Tellipatch's separate legacy visual-patcher phase. "
                "This build is therefore labeled Phase 1+2 Preview and does not pretend "
                "the visual pass ran."
            ),
            wraplength=690,
            justify="left",
        ).pack(fill="x")

        status = ttk.LabelFrame(outer, text="Status", padding=12)
        status.pack(fill="both", expand=True)
        ttk.Label(
            status,
            textvariable=self._english_status_v119,
            wraplength=690,
            justify="left",
            anchor="nw",
        ).pack(fill="both", expand=True)
        self._english_bar_v119 = ttk.Progressbar(
            status,
            variable=self._english_progress_v119,
            maximum=100,
        )
        self._english_bar_v119.pack(fill="x", pady=(12, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(12, 0))
        self._english_analyze_button_v119 = ttk.Button(
            actions, text="Analyze Only", command=lambda: self._start_english_job_v119("analyze")
        )
        self._english_analyze_button_v119.pack(side="left")
        self._english_build_button_v119 = ttk.Button(
            actions, text="Build English ISO", command=lambda: self._start_english_job_v119("build")
        )
        self._english_build_button_v119.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Close", command=self._close_english_builder_v119).pack(side="right")

    def _browse_english_source_v119(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._english_window_v119,
            title="Choose untouched Japanese .hack//Fragment ISO",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if not selected:
            return
        source = Path(selected)
        self._english_source_v119.set(str(source))
        if not self._english_output_v119.get().strip():
            self._english_output_v119.set(str(source.with_name(source.stem + "-English-Preview.iso")))

    def _browse_english_output_v119(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self._english_window_v119,
            title="Choose a new English ISO",
            defaultextension=".iso",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if selected:
            self._english_output_v119.set(selected)

    def _set_english_busy_v119(self, busy: bool) -> None:
        self._english_busy_v119 = busy
        state = "disabled" if busy else "normal"
        self._english_analyze_button_v119.configure(state=state)
        self._english_build_button_v119.configure(state=state)

    def _start_english_job_v119(self, mode: str) -> None:
        if self._english_busy_v119:
            return
        source = self._english_source_v119.get().strip()
        output = self._english_output_v119.get().strip()
        if not source:
            messagebox.showerror("English ISO", "Choose the original ISO first.", parent=self._english_window_v119)
            return
        overwrite = False
        if mode == "build":
            if not output:
                messagebox.showerror("English ISO", "Choose a separate output ISO.", parent=self._english_window_v119)
                return
            if Path(output).expanduser().resolve() == Path(source).expanduser().resolve():
                messagebox.showerror("English ISO", "The output must not overwrite the original ISO.", parent=self._english_window_v119)
                return
            if Path(output).exists():
                overwrite = messagebox.askyesno(
                    "Replace output ISO?",
                    f"This output already exists:\n\n{output}\n\nReplace it only after a complete verified build?",
                    parent=self._english_window_v119,
                )
                if not overwrite:
                    return
        self._set_english_busy_v119(True)
        self._english_progress_v119.set(0)
        self._english_status_v119.set("Starting verification...")

        def progress(stage: str, current: int, total: int, message: str) -> None:
            self._english_events_v119.put(("progress", stage, current, total, message))

        def worker() -> None:
            try:
                if mode == "analyze":
                    _iso, _patches, _writes, report = prepare_translation(source, progress=progress)
                else:
                    report = build_english_iso(source, output, overwrite=overwrite, progress=progress)
                self._english_events_v119.put(("done", mode, report))
            except (OSError, TellipatchError) as exc:
                self._english_events_v119.put(("error", str(exc)))
            except Exception as exc:
                self._english_events_v119.put(("error", f"Unexpected build failure: {exc}"))

        threading.Thread(target=worker, name="FragmenterEnglishIso", daemon=True).start()
        self.after(100, self._poll_english_events_v119)

    def _poll_english_events_v119(self) -> None:
        while True:
            try:
                event = self._english_events_v119.get_nowait()
            except queue.Empty:
                break
            if event[0] == "progress":
                _kind, _stage, current, total, message = event
                percent = (float(current) / max(1, int(total))) * 100.0
                self._english_progress_v119.set(percent)
                self._english_status_v119.set(str(message))
            elif event[0] == "error":
                self._set_english_busy_v119(False)
                self._english_status_v119.set(str(event[1]))
                messagebox.showerror("English ISO refused", str(event[1]), parent=self._english_window_v119)
            elif event[0] == "done":
                _kind, mode, report = event
                self._set_english_busy_v119(False)
                self._english_progress_v119.set(100)
                if mode == "analyze":
                    summary = (
                        "Ready. The original ISO, 7 binary patches, and "
                        f"{report['translated_rows']:,} translated lines all passed validation.\n\n"
                        "No output file was created. The separate legacy visual pass remains excluded."
                    )
                    title = "Original ISO is supported"
                else:
                    summary = (
                        "English Phase 1+2 Preview created and verified:\n\n"
                        f"{report['output']['path']}\n\nSHA-256: {report['output']['sha256']}\n\n"
                        "Keep the original ISO. The separate legacy visual pass remains excluded."
                    )
                    title = "English ISO ready"
                self._english_status_v119.set(summary)
                messagebox.showinfo(title, summary, parent=self._english_window_v119)
        if self._english_busy_v119:
            self.after(100, self._poll_english_events_v119)

    def _close_english_builder_v119(self) -> None:
        if self._english_busy_v119:
            messagebox.showwarning(
                "Build in progress",
                "Wait for the current verification/build to finish before closing this window.",
                parent=self._english_window_v119,
            )
            return
        window = self._english_window_v119
        self._english_window_v119 = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

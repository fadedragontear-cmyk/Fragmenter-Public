#!/usr/bin/env python3
"""V127 streamlined one-step Fragment 4.0 English game-image workflow."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from fragment_4_builder_v127 import build_fragment_4_english
from fragmenter_public_gui_v120 import acceptance_window_geometry_v120
from fragmenter_public_gui_v126 import PublicFragmenterAppV126

BUILD_MENU_LABEL_V127 = "Build Fragment 4.0 English..."
REMOVED_GAME_SETUP_LABELS_V127 = (
    "Install Translation Resource",
    "Create English Preview",
    "Complete Netslum 4.0",
    "Verify Game Setup",
)
_REMOVED_MENU_TERMS_V127 = (
    "Create English Preview",
    "Build Included English ISO",
    "Complete Netslum 4.0",
    "Verify Fragment Setup",
)


class PublicFragmenterAppV127(PublicFragmenterAppV126):
    """Expose only the final raw-disc-to-4.0 transaction."""

    def __init__(self) -> None:
        self._fragment4_window_v127: tk.Toplevel | None = None
        self._fragment4_busy_v127 = False
        self._fragment4_events_v127: queue.Queue[tuple[str, Any]] = queue.Queue()
        super().__init__()
        self.title("Fragmenter 1.0")
        self.after_idle(self._install_v127_tools_menu)

    def _build_game_setup_v125(self, parent: ttk.Frame) -> None:
        super()._build_game_setup_v125(parent)
        setup_notebook = next(
            (
                child
                for child in parent.winfo_children()
                if isinstance(child, ttk.Notebook)
            ),
            None,
        )
        if setup_notebook is None or not setup_notebook.tabs():
            return
        image_tab = self.nametowidget(setup_notebook.tabs()[0])
        for child in image_tab.winfo_children():
            child.destroy()
        image_tab.columnconfigure(0, weight=1)
        self._game_action_v125(
            image_tab,
            0,
            "Build Fragment 4.0 English",
            (
                "Create the complete verified 4.0 English ISO directly from the "
                "untouched Japanese disc. No Tellipatch install, preview ISO, "
                "verification window, or reference 4.0 ISO is required."
            ),
            self._open_fragment4_builder_v127,
        )
        ttk.Label(
            image_tab,
            text=(
                "Fragmenter verifies the original-disc MD5, bundled English patches, "
                "translated text, eight 4.0 completion targets, and final ISO volume "
                "label before publishing Fragment 4.0 English.iso."
            ),
            wraplength=650,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _install_v125_tools_menu(self) -> None:
        # V125 schedules this method by name. Route that callback directly to
        # the final V127 menu instead of re-adding the old reference-ISO action.
        self._install_v127_tools_menu()

    def _install_v127_tools_menu(self) -> None:
        tools_menu = self._find_tools_menu_v118()
        try:
            end = tools_menu.index("end")
            for index in reversed(range((int(end) + 1) if end is not None else 0)):
                label = str(tools_menu.entrycget(index, "label"))
                if any(term in label for term in _REMOVED_MENU_TERMS_V127):
                    tools_menu.delete(index)
            end = tools_menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(tools_menu.entrycget(index, "label")) == BUILD_MENU_LABEL_V127:
                    return
        except (ValueError, tk.TclError):
            pass
        tools_menu.add_command(
            label=BUILD_MENU_LABEL_V127,
            command=self._open_fragment4_builder_v127,
        )

    def _open_fragment4_builder_v127(self) -> None:
        existing = self._fragment4_window_v127
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_force()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self)
        self._fragment4_window_v127 = window
        window.title("Fragmenter - Build Fragment 4.0 English")
        geometry, minimum = acceptance_window_geometry_v120(
            window.winfo_screenwidth(),
            window.winfo_screenheight(),
        )
        window.geometry(geometry)
        window.minsize(*minimum)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", self._close_fragment4_v127)
        self._apply_window_brand_v125(window)

        self._fragment4_source_v127 = tk.StringVar()
        self._fragment4_output_v127 = tk.StringVar()
        self._fragment4_status_v127 = tk.StringVar(
            value="Choose the untouched Japanese .hack//Fragment ISO."
        )
        project = self.project
        if project is not None and project.sources.iso_path:
            candidate = Path(project.sources.iso_path).expanduser()
            if candidate.is_file():
                self._fragment4_source_v127.set(str(candidate))
                self._fragment4_output_v127.set(
                    str(candidate.with_name("Fragment 4.0 English.iso"))
                )

        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="Build Fragment 4.0 English",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "One read-only source, one separate finished ISO. Fragmenter performs "
                "the English translation and the complete 4.0 update as one verified "
                "transaction, then removes every intermediate file."
            ),
            wraplength=810,
            justify="left",
        ).pack(fill="x", pady=(4, 12))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        rows = (
            (
                "Untouched Japanese ISO",
                self._fragment4_source_v127,
                self._browse_fragment4_source_v127,
                "Choose source...",
            ),
            (
                "Finished output ISO",
                self._fragment4_output_v127,
                self._browse_fragment4_output_v127,
                "Save output...",
            ),
        )
        for row, (label, variable, command, button_label) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(form, textvariable=variable).grid(
                row=row, column=1, sticky="ew", padx=(10, 8), pady=5
            )
            ttk.Button(form, text=button_label, command=command).grid(
                row=row, column=2, sticky="e", pady=5
            )

        status = ttk.LabelFrame(outer, text="Status", padding=10)
        status.pack(fill="both", expand=True, pady=(13, 10))
        ttk.Label(
            status,
            textvariable=self._fragment4_status_v127,
            wraplength=790,
            justify="left",
            anchor="nw",
        ).pack(fill="both", expand=True)
        self._fragment4_progress_v127 = ttk.Progressbar(
            status,
            mode="indeterminate",
        )
        self._fragment4_progress_v127.pack(fill="x", pady=(10, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        self._fragment4_run_v127 = ttk.Button(
            buttons,
            text="Build + Verify Fragment 4.0 English",
            command=self._start_fragment4_v127,
        )
        self._fragment4_run_v127.pack(side="right")
        ttk.Button(
            buttons,
            text="Close",
            command=self._close_fragment4_v127,
        ).pack(side="right", padx=(0, 8))

    def _browse_fragment4_source_v127(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._fragment4_window_v127,
            title="Choose untouched Japanese .hack//Fragment ISO",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if not selected:
            return
        self._fragment4_source_v127.set(selected)
        if not self._fragment4_output_v127.get().strip():
            self._fragment4_output_v127.set(
                str(Path(selected).with_name("Fragment 4.0 English.iso"))
            )

    def _browse_fragment4_output_v127(self) -> None:
        source = self._fragment4_source_v127.get().strip()
        initial_dir = str(Path(source).parent) if source else ""
        selected = filedialog.asksaveasfilename(
            parent=self._fragment4_window_v127,
            title="Save verified Fragment 4.0 English ISO",
            initialdir=initial_dir or None,
            initialfile="Fragment 4.0 English.iso",
            defaultextension=".iso",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if selected:
            self._fragment4_output_v127.set(selected)

    def _start_fragment4_v127(self) -> None:
        if self._fragment4_busy_v127:
            return
        source_text = self._fragment4_source_v127.get().strip()
        output_text = self._fragment4_output_v127.get().strip()
        if not source_text or not output_text:
            messagebox.showerror(
                "Missing path",
                "Choose the untouched Japanese source and a separate output ISO.",
                parent=self._fragment4_window_v127,
            )
            return
        source = Path(source_text).expanduser()
        output = Path(output_text).expanduser()
        if source.resolve() == output.resolve():
            messagebox.showerror(
                "Unsafe output",
                "The finished output must be separate from the untouched source ISO.",
                parent=self._fragment4_window_v127,
            )
            return
        if output.exists() and not messagebox.askyesno(
            "Replace finished ISO?",
            f"{output}\n\nalready exists. Replace it after a new verified build?",
            parent=self._fragment4_window_v127,
        ):
            return

        self._fragment4_busy_v127 = True
        self._fragment4_run_v127.configure(state="disabled")
        self._fragment4_progress_v127.start(12)
        self._fragment4_status_v127.set(
            "Starting the complete English 4.0 transaction. The source remains read-only."
        )

        def notify(message: str) -> None:
            self._fragment4_events_v127.put(("progress", message))

        def worker() -> None:
            try:
                result = build_fragment_4_english(
                    source,
                    output,
                    overwrite=output.exists(),
                    progress=notify,
                )
                self._fragment4_events_v127.put(("done", result))
            except Exception as exc:
                self._fragment4_events_v127.put(("error", str(exc)))

        threading.Thread(
            target=worker,
            name="Fragmenter-V127-Fragment-4-English",
            daemon=True,
        ).start()
        self.after(100, self._drain_fragment4_v127)

    def _drain_fragment4_v127(self) -> None:
        finished = False
        while True:
            try:
                kind, payload = self._fragment4_events_v127.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self._fragment4_status_v127.set(str(payload))
            elif kind == "done":
                finished = True
                message = (
                    "Fragment 4.0 English completed and verified.\n\n"
                    f"ISO: {payload['output']}\n"
                    f"Volume label: {payload['volume_label']}\n"
                    f"Verified 4.0 files: {len(payload['verified_4_0_files'])}\n\n"
                    "All intermediate files were removed."
                )
                self._fragment4_status_v127.set(message)
                messagebox.showinfo(
                    "Fragment 4.0 English ready",
                    message,
                    parent=self._fragment4_window_v127,
                )
            elif kind == "error":
                finished = True
                self._fragment4_status_v127.set(f"Build refused: {payload}")
                messagebox.showerror(
                    "Fragment 4.0 English build refused",
                    str(payload),
                    parent=self._fragment4_window_v127,
                )

        if finished:
            self._fragment4_busy_v127 = False
            self._fragment4_progress_v127.stop()
            self._fragment4_run_v127.configure(state="normal")
            self.after_idle(self._apply_project_theme_v126)
        elif self._fragment4_busy_v127:
            self.after(100, self._drain_fragment4_v127)

    def _close_fragment4_v127(self) -> None:
        if self._fragment4_busy_v127:
            messagebox.showinfo(
                "Build active",
                "Wait for the verified ISO transaction to finish.",
                parent=self._fragment4_window_v127,
            )
            return
        window = self._fragment4_window_v127
        self._fragment4_window_v127 = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass


def main() -> int:
    app = PublicFragmenterAppV127()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

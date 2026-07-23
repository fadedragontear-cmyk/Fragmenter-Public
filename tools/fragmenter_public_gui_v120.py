#!/usr/bin/env python3
"""V120 automated setup and English ISO acceptance workflow."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from fragmenter_public_gui_v119 import PublicFragmenterAppV119
from pcsx2_setup import discover_pcsx2_ini
from release_acceptance_v120 import run_acceptance

ACCEPTANCE_MENU_LABEL = "Verify Fragment Setup..."
ACCEPTANCE_SETUP_BUTTON_LABEL = "Verify PCSX2 + English ISO..."


def _bounded_geometry_v120(
    screen_width: int,
    screen_height: int,
    *,
    preferred_width: int,
    preferred_height: int,
    width_margin: int,
    height_margin: int,
    floor_width: int,
    floor_height: int,
    minimum_width: int,
    minimum_height: int,
) -> tuple[str, tuple[int, int]]:
    width = min(
        screen_width,
        max(floor_width, min(preferred_width, screen_width - width_margin)),
    )
    height = min(
        screen_height,
        max(floor_height, min(preferred_height, screen_height - height_margin)),
    )
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    return (
        f"{width}x{height}+{x}+{y}",
        (min(minimum_width, width), min(minimum_height, height)),
    )


def main_window_geometry_v120(
    screen_width: int,
    screen_height: int,
) -> tuple[str, tuple[int, int]]:
    """Fit the inherited 1280x820 main window inside the current display."""
    return _bounded_geometry_v120(
        screen_width,
        screen_height,
        preferred_width=1280,
        preferred_height=820,
        width_margin=40,
        height_margin=80,
        floor_width=820,
        floor_height=560,
        minimum_width=900,
        minimum_height=600,
    )


def acceptance_window_geometry_v120(
    screen_width: int,
    screen_height: int,
) -> tuple[str, tuple[int, int]]:
    """Return a centered verifier window that stays inside the display."""
    return _bounded_geometry_v120(
        screen_width,
        screen_height,
        preferred_width=880,
        preferred_height=680,
        width_margin=80,
        height_margin=100,
        floor_width=600,
        floor_height=460,
        minimum_width=680,
        minimum_height=500,
    )


class FragmenterAcceptanceMixinV120:
    def __init__(self) -> None:
        self._acceptance_window_v120: tk.Toplevel | None = None
        self._acceptance_events_v120: queue.Queue = queue.Queue()
        self._acceptance_busy_v120 = False
        super().__init__()
        self.after_idle(self._install_acceptance_entrypoints_v120)

    def _install_acceptance_entrypoints_v120(self) -> None:
        self._install_acceptance_menu_v120()
        self._install_acceptance_setup_button_v120()

    def _install_acceptance_menu_v120(self) -> None:
        tools_menu = self._find_tools_menu_v118()
        try:
            end = tools_menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(tools_menu.entrycget(index, "label")) == ACCEPTANCE_MENU_LABEL:
                    return
        except (ValueError, tk.TclError):
            pass
        tools_menu.add_separator()
        tools_menu.add_command(
            label=ACCEPTANCE_MENU_LABEL,
            command=self._open_acceptance_v120,
        )

    def _install_acceptance_setup_button_v120(self) -> None:
        setup_tab = getattr(self, "tabs", {}).get("Setup")
        if setup_tab is None:
            return
        for child in setup_tab.winfo_children():
            try:
                if str(child.cget("text")) == ACCEPTANCE_SETUP_BUTTON_LABEL:
                    return
            except (tk.TclError, AttributeError):
                continue
        button = ttk.Button(
            setup_tab,
            text=ACCEPTANCE_SETUP_BUTTON_LABEL,
            command=self._open_acceptance_v120,
        )
        button.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(10, 0),
        )

    def _open_acceptance_v120(self) -> None:
        existing = self._acceptance_window_v120
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
        self._acceptance_window_v120 = window
        window.title("Fragmenter - Verify Fragment Setup")
        geometry, minimum = acceptance_window_geometry_v120(
            window.winfo_screenwidth(),
            window.winfo_screenheight(),
        )
        window.geometry(geometry)
        window.minsize(*minimum)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", self._close_acceptance_v120)

        self._acceptance_pcsx2_v120 = tk.StringVar()
        self._acceptance_card_v120 = tk.StringVar()
        self._acceptance_source_v120 = tk.StringVar()
        self._acceptance_output_v120 = tk.StringVar()
        self._acceptance_report_v120 = tk.StringVar()

        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="Verify the complete Fragment setup",
            font=("TkDefaultFont", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "This performs read-only checks for PCSX2 keyboard/network settings, the exact "
                "included network card, the supported original disc, every included English "
                "phase 1+2 patch byte, and any unexpected changes elsewhere in the ISO."
            ),
            wraplength=820,
            justify="left",
        ).pack(fill="x", pady=(4, 14))

        paths = ttk.Frame(outer)
        paths.pack(fill="x")
        paths.columnconfigure(1, weight=1)
        rows = (
            ("PCSX2.ini", self._acceptance_pcsx2_v120, self._browse_acceptance_pcsx2_v120),
            ("Fragment-Network.ps2", self._acceptance_card_v120, self._browse_acceptance_card_v120),
            ("Untouched Japanese ISO", self._acceptance_source_v120, self._browse_acceptance_source_v120),
            ("English Phase 1+2 ISO", self._acceptance_output_v120, self._browse_acceptance_output_v120),
            ("Acceptance report", self._acceptance_report_v120, self._browse_acceptance_report_v120),
        )
        for row, (label, variable, command) in enumerate(rows):
            ttk.Label(paths, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(paths, textvariable=variable).grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(12, 8),
                pady=4,
            )
            ttk.Button(paths, text="Browse...", command=command).grid(
                row=row,
                column=2,
                sticky="e",
                pady=4,
            )

        status = ttk.LabelFrame(outer, text="Automated acceptance", padding=12)
        status.pack(fill="both", expand=True, pady=(14, 0))
        status.columnconfigure(0, weight=1)
        status.rowconfigure(0, weight=1)
        self._acceptance_status_text_v120 = tk.Text(
            status,
            height=11,
            wrap="word",
            state="disabled",
            borderwidth=0,
            highlightthickness=0,
        )
        status_scroll = ttk.Scrollbar(
            status,
            orient="vertical",
            command=self._acceptance_status_text_v120.yview,
        )
        self._acceptance_status_text_v120.configure(yscrollcommand=status_scroll.set)
        self._acceptance_status_text_v120.grid(row=0, column=0, sticky="nsew")
        status_scroll.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self._acceptance_bar_v120 = ttk.Progressbar(status, mode="determinate", maximum=100)
        self._acceptance_bar_v120.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(12, 0),
        )

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(12, 0))
        self._acceptance_run_button_v120 = ttk.Button(
            actions,
            text="Run Acceptance Check",
            command=self._start_acceptance_v120,
        )
        self._acceptance_run_button_v120.pack(side="left")
        ttk.Button(actions, text="Close", command=self._close_acceptance_v120).pack(side="right")

        self._set_acceptance_status_v120(
            "Choose the PCSX2 settings, installed network card, untouched Japanese ISO, "
            "and English Phase 1+2 output. The acceptance check does not modify them."
        )
        self._autodetect_acceptance_v120()
        window.after_idle(window.focus_force)

    def _set_acceptance_status_v120(self, text: str) -> None:
        widget = self._acceptance_status_text_v120
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")
        widget.yview_moveto(0.0)

    def _autodetect_acceptance_v120(self) -> None:
        found = discover_pcsx2_ini()
        if not found:
            return
        ini = found[0]
        self._acceptance_pcsx2_v120.set(str(ini))
        root = ini.parent.parent if ini.parent.name.casefold() == "inis" else ini.parent
        card = root / "memcards" / "Fragment-Network.ps2"
        if card.is_file():
            self._acceptance_card_v120.set(str(card))

    def _browse_acceptance_pcsx2_v120(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._acceptance_window_v120,
            title="Choose PCSX2.ini",
            filetypes=(("PCSX2 settings", "*.ini"), ("All files", "*.*")),
        )
        if selected:
            self._acceptance_pcsx2_v120.set(selected)
            ini = Path(selected)
            root = ini.parent.parent if ini.parent.name.casefold() == "inis" else ini.parent
            card = root / "memcards" / "Fragment-Network.ps2"
            if card.is_file():
                self._acceptance_card_v120.set(str(card))

    def _browse_acceptance_card_v120(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._acceptance_window_v120,
            title="Choose Fragment-Network.ps2",
            filetypes=(("PCSX2 memory cards", "*.ps2"), ("All files", "*.*")),
        )
        if selected:
            self._acceptance_card_v120.set(selected)

    def _browse_acceptance_source_v120(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._acceptance_window_v120,
            title="Choose untouched Japanese .hack//Fragment ISO",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if selected:
            self._acceptance_source_v120.set(selected)

    def _browse_acceptance_output_v120(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._acceptance_window_v120,
            title="Choose English Phase 1+2 ISO",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if selected:
            self._acceptance_output_v120.set(selected)
            if not self._acceptance_report_v120.get().strip():
                output = Path(selected)
                self._acceptance_report_v120.set(
                    str(output.with_suffix(output.suffix + ".fragmenter-acceptance.json"))
                )

    def _browse_acceptance_report_v120(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self._acceptance_window_v120,
            title="Save Fragmenter acceptance report",
            defaultextension=".json",
            filetypes=(("JSON report", "*.json"), ("All files", "*.*")),
        )
        if selected:
            self._acceptance_report_v120.set(selected)

    def _set_acceptance_busy_v120(self, busy: bool) -> None:
        self._acceptance_busy_v120 = busy
        self._acceptance_run_button_v120.configure(state="disabled" if busy else "normal")

    def _start_acceptance_v120(self) -> None:
        if self._acceptance_busy_v120:
            return
        values = {
            "pcsx2_ini": self._acceptance_pcsx2_v120.get().strip() or None,
            "memory_card": self._acceptance_card_v120.get().strip() or None,
            "source_iso": self._acceptance_source_v120.get().strip() or None,
            "english_iso": self._acceptance_output_v120.get().strip() or None,
            "report_path": self._acceptance_report_v120.get().strip() or None,
        }
        self._set_acceptance_busy_v120(True)
        self._acceptance_bar_v120.configure(mode="indeterminate", value=0)
        self._acceptance_bar_v120.start(12)
        self._set_acceptance_status_v120("Starting read-only acceptance checks...")

        def progress(stage: str, current: int, total: int, message: str) -> None:
            self._acceptance_events_v120.put(
                ("progress", stage, current, total, message)
            )

        def worker() -> None:
            try:
                report = run_acceptance(**values, progress=progress)
                self._acceptance_events_v120.put(("done", report))
            except Exception as exc:
                self._acceptance_events_v120.put(("error", str(exc)))

        threading.Thread(target=worker, name="FragmenterAcceptanceV120", daemon=True).start()
        self.after(100, self._poll_acceptance_v120)

    def _poll_acceptance_v120(self) -> None:
        while True:
            try:
                event = self._acceptance_events_v120.get_nowait()
            except queue.Empty:
                break
            if event[0] == "progress":
                _kind, _stage, current, total, message = event
                detail = str(message)
                if int(total) > 1:
                    detail += f"\n\nProgress: {int(current):,} / {int(total):,}"
                self._set_acceptance_status_v120(detail)
            elif event[0] == "error":
                self._set_acceptance_busy_v120(False)
                self._acceptance_bar_v120.stop()
                self._acceptance_bar_v120.configure(mode="determinate", value=0)
                self._set_acceptance_status_v120(str(event[1]))
                messagebox.showerror(
                    "Fragment setup verification failed",
                    str(event[1]),
                    parent=self._acceptance_window_v120,
                )
            elif event[0] == "done":
                report = event[1]
                self._set_acceptance_busy_v120(False)
                self._acceptance_bar_v120.stop()
                status = str(report["automated_status"])
                self._acceptance_bar_v120.configure(
                    mode="determinate",
                    value=100 if status == "passed" else 65,
                )
                lines = [f"Automated status: {status.upper()}", ""]
                for check in report["checks"]:
                    lines.append(
                        f"[{str(check['status']).upper()}] {check['label']}: {check['detail']}"
                    )
                lines.extend(
                    (
                        "",
                        "Manual PCSX2 boot, menu, network-login, text-wrapping, and gameplay checks remain pending.",
                    )
                )
                if report.get("report_path"):
                    lines.extend(("", f"Report: {report['report_path']}"))
                summary = "\n".join(lines)
                self._set_acceptance_status_v120(summary)
                if status == "passed":
                    messagebox.showinfo(
                        "Automated acceptance passed",
                        summary,
                        parent=self._acceptance_window_v120,
                    )
                else:
                    messagebox.showwarning(
                        "Automated acceptance needs attention",
                        summary,
                        parent=self._acceptance_window_v120,
                    )
        if self._acceptance_busy_v120:
            self.after(100, self._poll_acceptance_v120)

    def _close_acceptance_v120(self) -> None:
        if self._acceptance_busy_v120:
            messagebox.showwarning(
                "Verification in progress",
                "Wait for the current read-only verification to finish before closing.",
                parent=self._acceptance_window_v120,
            )
            return
        window = self._acceptance_window_v120
        self._acceptance_window_v120 = None
        if window is not None:
            try:
                self._acceptance_bar_v120.stop()
                window.destroy()
            except tk.TclError:
                pass


class PublicFragmenterAppV120(
    FragmenterAcceptanceMixinV120,
    PublicFragmenterAppV119,
):
    def __init__(self) -> None:
        super().__init__()
        geometry, minimum = main_window_geometry_v120(
            self.winfo_screenwidth(),
            self.winfo_screenheight(),
        )
        self.geometry(geometry)
        self.minsize(*minimum)
        self.title("Fragmenter 1.0 - Setup Acceptance Experimental V120")


def main() -> int:
    app = PublicFragmenterAppV120()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

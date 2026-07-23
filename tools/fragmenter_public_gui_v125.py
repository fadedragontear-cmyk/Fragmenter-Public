#!/usr/bin/env python3
"""V125 dedicated Game Setup workspace and Serenial application branding."""

from __future__ import annotations

import queue
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from fragmenter_public_gui_v120 import acceptance_window_geometry_v120
from fragmenter_public_gui_v122 import PublicFragmenterAppV122
from netslum_completion_v124 import apply_completion_pack, build_completion_pack

GAME_SETUP_TAB_V125 = "Game Setup"
PROJECT_SETUP_TAB_V125 = "Project Setup"
GAME_SETUP_ACTIONS_V125 = (
    "Install Translation Resource",
    "Create English Preview",
    "Complete Netslum 4.0",
    "Verify Game Setup",
    "Configure Keyboard + Network",
    "Install / Inspect Memory Card",
)
BRAND_PNG_V125 = "Fragmenter-Serenial.png"
BRAND_ICO_V125 = "Fragmenter.ico"
NETSLUM_MENU_LABEL_V125 = "Complete Netslum 4.0..."


def data_root_v125() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def brand_asset_v125(filename: str) -> Path:
    return data_root_v125() / "assets" / "branding" / filename


def _walk_widgets_v125(widget: tk.Misc):
    yield widget
    for child in widget.winfo_children():
        yield from _walk_widgets_v125(child)


class PublicFragmenterAppV125(PublicFragmenterAppV122):
    """Separate project authoring from safe game/emulator preparation."""

    def __init__(self) -> None:
        self._legacy_backups_tab_v125: ttk.Frame | None = None
        self._brand_master_v125: tk.PhotoImage | None = None
        self._brand_header_v125: tk.PhotoImage | None = None
        self._completion_window_v125: tk.Toplevel | None = None
        self._completion_events_v125: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._completion_busy_v125 = False
        super().__init__()
        self.title("Fragmenter 1.0 - Serenial Edition")
        self._apply_window_brand_v125(self)
        self.after_idle(self._install_v125_tools_menu)

    # ------------------------------------------------------------------
    # Serenial identity
    # ------------------------------------------------------------------
    def _load_brand_images_v125(self) -> None:
        if self._brand_master_v125 is not None:
            return
        path = brand_asset_v125(BRAND_PNG_V125)
        if not path.is_file():
            return
        try:
            self._brand_master_v125 = tk.PhotoImage(file=str(path))
            self._brand_header_v125 = self._brand_master_v125.subsample(4, 4)
        except tk.TclError:
            self._brand_master_v125 = None
            self._brand_header_v125 = None

    def _apply_window_brand_v125(self, window: tk.Misc) -> None:
        self._load_brand_images_v125()
        if self._brand_master_v125 is None:
            return
        try:
            window.iconphoto(True, self._brand_master_v125)
        except tk.TclError:
            pass

    def _build_header(self) -> None:
        self._load_brand_images_v125()
        frame = tk.Frame(self, bg="#071522", padx=12, pady=8)
        frame.pack(fill="x")

        if self._brand_header_v125 is not None:
            tk.Label(
                frame,
                image=self._brand_header_v125,
                bg="#071522",
                borderwidth=0,
            ).pack(side="left", padx=(0, 10))

        identity = tk.Frame(frame, bg="#071522")
        identity.pack(side="left", fill="y")
        tk.Label(
            identity,
            text="Fragmenter",
            bg="#071522",
            fg="#67dcff",
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor="w")
        tk.Label(
            identity,
            text=".hack//Fragment research, preservation, and setup toolkit",
            bg="#071522",
            fg="#b7cddd",
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        tk.Label(
            frame,
            textvariable=self.project_label,
            bg="#071522",
            fg="#dcebf5",
            font=("Segoe UI", 9),
        ).pack(side="left", padx=22)
        tk.Label(
            frame,
            textvariable=self.current_task_label,
            bg="#071522",
            fg="#8cdff7",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Tab ownership
    # ------------------------------------------------------------------
    def _build_backups(self, parent: ttk.Frame) -> None:
        # The inherited tab builder reaches this before Game Setup exists.
        # Defer the real backup UI, then forget the empty legacy tab.
        self._legacy_backups_tab_v125 = parent

    def _build_tabs(self) -> None:
        super()._build_tabs()

        project_tab = self.tabs["Setup"]
        self.notebook.tab(project_tab, text=PROJECT_SETUP_TAB_V125)

        game_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.insert(1, game_tab, text=GAME_SETUP_TAB_V125)
        self.tabs[GAME_SETUP_TAB_V125] = game_tab
        self._build_game_setup_v125(game_tab)

        legacy = self.tabs.pop("Backups", self._legacy_backups_tab_v125)
        if legacy is not None:
            try:
                self.notebook.forget(legacy)
            except tk.TclError:
                pass

    def _install_acceptance_entrypoints_v120(self) -> None:
        # V122's four-button panel belonged to Project Setup. Game Setup owns
        # those actions now, while the Tools-menu verifier remains available.
        self._install_acceptance_menu_v120()

    def _build_game_setup_v125(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        hero = tk.Frame(parent, bg="#0b2235", padx=14, pady=10)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        tk.Label(
            hero,
            text="Game Setup",
            bg="#0b2235",
            fg="#70ddff",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            hero,
            text=(
                "Prepare a verified English/Netslum 4.0 image, configure PCSX2, "
                "install or inspect memory cards, and protect server saves."
            ),
            bg="#0b2235",
            fg="#d3e6f2",
            justify="left",
            wraplength=1050,
        ).pack(anchor="w", pady=(2, 0))

        setup_sections = ttk.Notebook(parent)
        setup_sections.grid(row=1, column=0, sticky="nsew", pady=(0, 9))
        iso_card = ttk.Frame(setup_sections, padding=11)
        pcsx2_card = ttk.Frame(setup_sections, padding=11)
        setup_sections.add(iso_card, text="Game Image")
        setup_sections.add(pcsx2_card, text="PCSX2 + Memory Card")
        iso_card.columnconfigure(0, weight=1)
        self._game_action_v125(
            iso_card,
            0,
            "Install Translation Resource",
            "Verify and cache the official Tellipatch patch archive.",
            self._install_translation_resource_v122,
        )
        self._game_action_v125(
            iso_card,
            1,
            "Create English Preview",
            "Build the native phase 1+2 preview from the untouched Japanese ISO.",
            self._open_verified_english_builder_v122,
        )
        self._game_action_v125(
            iso_card,
            2,
            "Complete Netslum 4.0",
            "Use your known 4.0 image locally to complete and verify the eight changed files.",
            self._open_completion_v125,
        )
        self._game_action_v125(
            iso_card,
            3,
            "Verify Game Setup",
            "Check PCSX2, the network card, source image, and completed output.",
            self._open_acceptance_v120,
        )

        pcsx2_card.columnconfigure(0, weight=1)
        self._game_action_v125(
            pcsx2_card,
            0,
            "Configure Keyboard + Network",
            "Enable the Konami USB keyboard and Ethernet in a backed-up PCSX2.ini transaction.",
            self._open_pcsx2_helper_v118,
        )
        self._game_action_v125(
            pcsx2_card,
            1,
            "Install / Inspect Memory Card",
            "Install the clean Fragment network card or inspect and copy another raw PCSX2 card.",
            self._open_memory_card_helper_v125,
        )
        ttk.Label(
            pcsx2_card,
            text=(
                "Fragmenter never overwrites an installed card. PCSX2 settings are "
                "backed up beside PCSX2.ini before changes are written."
            ),
            wraplength=500,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(10, 0))

        backup_card = ttk.LabelFrame(
            parent,
            text="Backup and recovery - area server saves and project memory card",
            padding=10,
        )
        backup_card.grid(row=2, column=0, sticky="nsew")
        backup_card.columnconfigure(0, weight=1)
        backup_card.rowconfigure(1, weight=1)
        ttk.Label(
            backup_card,
            text=(
                "These are the existing manifest-verified project backups. Select a "
                "server-save or memory-card backup below to restore it; Fragmenter "
                "first protects the current destination."
            ),
            wraplength=1050,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 7))

        backup_surface = ttk.Frame(backup_card)
        backup_surface.grid(row=1, column=0, sticky="nsew")
        # No intermediate GUI revision overrides this legacy builder.
        super()._build_backups(backup_surface)

    def _game_action_v125(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        description: str,
        command: Callable[[], None],
    ) -> None:
        line = ttk.Frame(parent)
        line.grid(row=row, column=0, sticky="ew", pady=(0, 7))
        line.columnconfigure(1, weight=1)
        ttk.Button(line, text=label, command=command, width=29).grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        ttk.Label(
            line,
            text=description,
            wraplength=300,
            justify="left",
        ).grid(row=0, column=1, sticky="ew")

    def _open_memory_card_helper_v125(self) -> None:
        self._open_pcsx2_helper_v118()

        def select_card() -> None:
            window = getattr(self, "_pcsx2_window_v118", None)
            if window is None:
                return
            for widget in _walk_widgets_v125(window):
                if isinstance(widget, ttk.Notebook):
                    try:
                        if len(widget.tabs()) > 1:
                            widget.select(1)
                    except tk.TclError:
                        pass
                    return

        self.after_idle(select_card)

    def _install_v125_tools_menu(self) -> None:
        tools_menu = self._find_tools_menu_v118()
        try:
            end = tools_menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(tools_menu.entrycget(index, "label")) == NETSLUM_MENU_LABEL_V125:
                    return
        except (ValueError, tk.TclError):
            pass
        tools_menu.add_command(
            label=NETSLUM_MENU_LABEL_V125,
            command=self._open_completion_v125,
        )

    # ------------------------------------------------------------------
    # Responsive local 4.0 completion dialog
    # ------------------------------------------------------------------
    def _open_completion_v125(self) -> None:
        existing = self._completion_window_v125
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
        self._completion_window_v125 = window
        window.title("Fragmenter - Complete Netslum 4.0")
        geometry, minimum = acceptance_window_geometry_v120(
            window.winfo_screenwidth(),
            window.winfo_screenheight(),
        )
        window.geometry(geometry)
        window.minsize(*minimum)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", self._close_completion_v125)
        self._apply_window_brand_v125(window)

        self._completion_preview_v125 = tk.StringVar()
        self._completion_reference_v125 = tk.StringVar()
        self._completion_output_v125 = tk.StringVar()
        self._completion_status_v125 = tk.StringVar(
            value="Choose the Fragmenter preview that displays 3.8 and your known working Netslum 4.0 ISO."
        )

        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="Complete the verified Netslum 4.0 image",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Both inputs remain read-only. Fragmenter derives only the changed byte "
                "ranges, writes a separate copy, and publishes it only after every target "
                "file matches the known 4.0 reference."
            ),
            wraplength=810,
            justify="left",
        ).pack(fill="x", pady=(4, 12))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        rows = (
            (
                "Fragmenter preview (3.8)",
                self._completion_preview_v125,
                self._browse_completion_preview_v125,
                "Choose preview...",
            ),
            (
                "Known Netslum 4.0 ISO",
                self._completion_reference_v125,
                lambda: self._browse_completion_file_v125(
                    self._completion_reference_v125, "Choose known Netslum 4.0 ISO"
                ),
                "Choose reference...",
            ),
            (
                "Completed output ISO",
                self._completion_output_v125,
                self._browse_completion_output_v125,
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
            textvariable=self._completion_status_v125,
            wraplength=790,
            justify="left",
            anchor="nw",
        ).pack(fill="both", expand=True)
        self._completion_progress_v125 = ttk.Progressbar(status, mode="indeterminate")
        self._completion_progress_v125.pack(fill="x", pady=(10, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        self._completion_run_v125 = ttk.Button(
            buttons,
            text="Build + Verify Separate 4.0 ISO",
            command=self._start_completion_v125,
        )
        self._completion_run_v125.pack(side="right")
        ttk.Button(
            buttons,
            text="Close",
            command=self._close_completion_v125,
        ).pack(side="right", padx=(0, 8))

    def _browse_completion_file_v125(self, variable: tk.StringVar, title: str) -> None:
        selected = filedialog.askopenfilename(
            parent=self._completion_window_v125,
            title=title,
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if selected:
            variable.set(selected)

    def _browse_completion_preview_v125(self) -> None:
        self._browse_completion_file_v125(
            self._completion_preview_v125,
            "Choose Fragmenter English Preview (displays 3.8)",
        )
        value = self._completion_preview_v125.get().strip()
        if not value:
            return
        preview = Path(value)
        if not self._completion_output_v125.get().strip():
            self._completion_output_v125.set(
                str(preview.with_name("Fragment 4.0 English.iso"))
            )

    def _browse_completion_output_v125(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self._completion_window_v125,
            title="Save separate completed Netslum 4.0 ISO",
            defaultextension=".iso",
            filetypes=(("PlayStation 2 ISO", "*.iso"), ("All files", "*.*")),
        )
        if selected:
            self._completion_output_v125.set(selected)

    def _start_completion_v125(self) -> None:
        if self._completion_busy_v125:
            return
        preview = Path(self._completion_preview_v125.get().strip()).expanduser()
        reference = Path(self._completion_reference_v125.get().strip()).expanduser()
        output = Path(self._completion_output_v125.get().strip()).expanduser()
        if not all(str(path) not in {"", "."} for path in (preview, reference, output)):
            messagebox.showerror(
                "Missing path",
                "Choose both input ISOs and a separate output ISO.",
                parent=self._completion_window_v125,
            )
            return
        if output.exists() and not messagebox.askyesno(
            "Replace completed ISO?",
            f"{output}\n\nalready exists. Replace it only after a successful verified transaction?",
            parent=self._completion_window_v125,
        ):
            return

        self._completion_busy_v125 = True
        self._completion_run_v125.configure(state="disabled")
        self._completion_progress_v125.start(12)
        self._completion_status_v125.set(
            "Comparing logical files. DATA.BIN is large, so this stage can take a while."
        )

        def notify(message: str) -> None:
            self._completion_events_v125.put(("progress", message))

        def worker() -> None:
            try:
                with tempfile.TemporaryDirectory(
                    prefix="fragmenter-v125-completion-"
                ) as folder:
                    pack = Path(folder) / "completion.zip"
                    build_completion_pack(
                        preview,
                        reference,
                        pack,
                        progress=notify,
                    )
                    result = apply_completion_pack(
                        preview,
                        pack,
                        output,
                        overwrite=output.exists(),
                        progress=notify,
                    )
                self._completion_events_v125.put(("done", {"result": result}))
            except Exception as exc:
                self._completion_events_v125.put(("error", str(exc)))

        threading.Thread(
            target=worker,
            name="Fragmenter-V125-Netslum-Completion",
            daemon=True,
        ).start()
        self.after(100, self._drain_completion_v125)

    def _drain_completion_v125(self) -> None:
        finished = False
        while True:
            try:
                kind, payload = self._completion_events_v125.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self._completion_status_v125.set(str(payload))
            elif kind == "done":
                finished = True
                result = payload["result"]
                message = (
                    f"Completed and verified {len(result['verified_files'])} changed files.\n\n"
                    f"ISO: {result['output']}\n"
                    f"Volume label: {result['volume_label']}\n\n"
                    "Temporary completion data was removed."
                )
                self._completion_status_v125.set(message)
                messagebox.showinfo(
                    "Netslum 4.0 completion ready",
                    message,
                    parent=self._completion_window_v125,
                )
            elif kind == "error":
                finished = True
                self._completion_status_v125.set(f"Completion refused: {payload}")
                messagebox.showerror(
                    "Netslum 4.0 completion refused",
                    str(payload),
                    parent=self._completion_window_v125,
                )

        if finished:
            self._completion_busy_v125 = False
            self._completion_progress_v125.stop()
            self._completion_run_v125.configure(state="normal")
        elif self._completion_busy_v125:
            self.after(100, self._drain_completion_v125)

    def _close_completion_v125(self) -> None:
        if self._completion_busy_v125:
            messagebox.showinfo(
                "Completion active",
                "Wait for the verified completion transaction to finish.",
                parent=self._completion_window_v125,
            )
            return
        window = self._completion_window_v125
        self._completion_window_v125 = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass


def main() -> int:
    app = PublicFragmenterAppV125()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

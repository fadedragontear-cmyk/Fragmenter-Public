#!/usr/bin/env python3
"""V118 PCSX2 keyboard, network, and memory-card setup window."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pcsx2_setup import (
    BUNDLED_CARD_RAW_SHA256,
    Pcsx2SetupError,
    configure_fragment_pcsx2,
    discover_pcsx2_ini,
    inspect_keyboard_config,
    inspect_memory_card,
    install_bundled_memory_card,
    install_memory_card,
)


class FragmenterPcsx2HelperMixinV118:
    """Add an isolated PCSX2 quality-of-life helper to the Tools menu."""

    def __init__(self) -> None:
        self._pcsx2_window_v118: tk.Toplevel | None = None
        super().__init__()
        self.after_idle(self._install_pcsx2_menu_v118)

    def _find_tools_menu_v118(self) -> tk.Menu:
        try:
            menu_name = str(self.cget("menu") or "")
            menu = self.nametowidget(menu_name) if menu_name else None
        except (KeyError, tk.TclError):
            menu = None
        if not isinstance(menu, tk.Menu):
            menu = tk.Menu(self)
            self.configure(menu=menu)
        try:
            end = menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(menu.type(index)) != "cascade":
                    continue
                if str(menu.entrycget(index, "label")).strip().casefold() != "tools":
                    continue
                candidate = self.nametowidget(str(menu.entrycget(index, "menu")))
                if isinstance(candidate, tk.Menu):
                    return candidate
        except (KeyError, ValueError, tk.TclError):
            pass
        tools_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Tools", menu=tools_menu)
        return tools_menu

    def _install_pcsx2_menu_v118(self) -> None:
        tools_menu = self._find_tools_menu_v118()
        label = "Set Up PCSX2 for Fragment..."
        try:
            end = tools_menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(tools_menu.entrycget(index, "label")) == label:
                    return
        except (ValueError, tk.TclError):
            pass
        tools_menu.add_command(label=label, command=self._open_pcsx2_helper_v118)

    def _open_pcsx2_helper_v118(self) -> None:
        existing = self._pcsx2_window_v118
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
        self._pcsx2_window_v118 = window
        window.title("Fragmenter - PCSX2 Setup")
        window.geometry("760x520")
        window.minsize(680, 470)
        window.protocol("WM_DELETE_WINDOW", self._close_pcsx2_helper_v118)

        self._pcsx2_ini_var_v118 = tk.StringVar()
        self._pcsx2_status_var_v118 = tk.StringVar(
            value="Choose PCSX2.ini, then analyze it before making changes."
        )
        self._card_source_var_v118 = tk.StringVar()
        self._memcards_folder_var_v118 = tk.StringVar()
        self._card_name_var_v118 = tk.StringVar(value="Fragment-Network.ps2")
        self._card_status_var_v118 = tk.StringVar(
            value=(
                "Included clean 8 MiB card: network configuration only.\n"
                f"SHA-256: {BUNDLED_CARD_RAW_SHA256}\n\n"
                "Choose the PCSX2 memcards folder, then install the included card."
            )
        )

        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="Make PCSX2 ready for .hack//Fragment",
            font=("TkDefaultFont", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "The helper changes only the Fragment USB keyboard and Ethernet switch. "
                "All controller bindings and other emulator settings remain untouched."
            ),
            wraplength=700,
            justify="left",
        ).pack(fill="x", pady=(4, 14))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        settings_tab = ttk.Frame(notebook, padding=14)
        card_tab = ttk.Frame(notebook, padding=14)
        notebook.add(settings_tab, text="Keyboard + Network")
        notebook.add(card_tab, text="Memory Card")
        self._build_pcsx2_settings_tab_v118(settings_tab)
        self._build_memory_card_tab_v118(card_tab)

        ttk.Button(outer, text="Close", command=self._close_pcsx2_helper_v118).pack(
            anchor="e", pady=(12, 0)
        )
        self._autodetect_pcsx2_v118()

    def _build_pcsx2_settings_tab_v118(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="PCSX2.ini").grid(row=0, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self._pcsx2_ini_var_v118).grid(
            row=0, column=1, sticky="ew", padx=(12, 8)
        )
        ttk.Button(tab, text="Browse...", command=self._browse_pcsx2_ini_v118).grid(
            row=0, column=2, sticky="e"
        )
        ttk.Label(
            tab,
            text=(
                "Close PCSX2 before applying. Fragmenter will set [USB1] Type=hidkbd "
                "and [DEV9/Eth] EthEnable=true in one backed-up transaction."
            ),
            wraplength=650,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(14, 10))
        status = ttk.LabelFrame(tab, text="Status", padding=12)
        status.grid(row=2, column=0, columnspan=3, sticky="nsew")
        tab.rowconfigure(2, weight=1)
        ttk.Label(
            status,
            textvariable=self._pcsx2_status_var_v118,
            wraplength=620,
            justify="left",
            anchor="nw",
        ).pack(fill="both", expand=True)
        actions = ttk.Frame(tab)
        actions.grid(row=3, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Analyze", command=self._analyze_pcsx2_v118).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(
            actions,
            text="Enable Keyboard + Network",
            command=self._configure_pcsx2_v118,
        ).pack(side="left")

    def _build_memory_card_tab_v118(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        rows = (
            ("External .ps2 card", self._card_source_var_v118, self._browse_card_v118),
            ("PCSX2 memcards folder", self._memcards_folder_var_v118, self._browse_memcards_v118),
        )
        for row, (label, variable, command) in enumerate(rows):
            ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(tab, textvariable=variable).grid(
                row=row, column=1, sticky="ew", padx=(12, 8), pady=4
            )
            ttk.Button(tab, text="Browse...", command=command).grid(
                row=row, column=2, sticky="e", pady=4
            )
        ttk.Label(tab, text="Installed name").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self._card_name_var_v118).grid(
            row=2, column=1, sticky="ew", padx=(12, 8), pady=4
        )
        status = ttk.LabelFrame(tab, text="Card inspection", padding=12)
        status.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        tab.rowconfigure(3, weight=1)
        ttk.Label(
            status,
            textvariable=self._card_status_var_v118,
            wraplength=620,
            justify="left",
            anchor="nw",
        ).pack(fill="both", expand=True)
        actions = ttk.Frame(tab)
        actions.grid(row=4, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(
            actions,
            text="Install Included Network Card",
            command=self._install_included_card_v118,
        ).pack(side="left", padx=(0, 16))
        ttk.Button(actions, text="Inspect Card", command=self._inspect_card_v118).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Install Copy", command=self._install_card_v118).pack(
            side="left"
        )

    def _autodetect_pcsx2_v118(self) -> None:
        found = discover_pcsx2_ini()
        if not found:
            return
        self._pcsx2_ini_var_v118.set(str(found[0]))
        self._derive_memcards_folder_v118(found[0])
        self._analyze_pcsx2_v118()

    def _derive_memcards_folder_v118(self, ini_path: Path) -> None:
        parent = ini_path.parent
        root = parent.parent if parent.name.casefold() == "inis" else parent
        candidate = root / "memcards"
        if candidate.is_dir():
            self._memcards_folder_var_v118.set(str(candidate))

    def _browse_pcsx2_ini_v118(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._pcsx2_window_v118,
            title="Choose PCSX2.ini",
            filetypes=(("PCSX2 settings", "*.ini"), ("All files", "*.*")),
        )
        if selected:
            self._pcsx2_ini_var_v118.set(selected)
            self._derive_memcards_folder_v118(Path(selected))
            self._analyze_pcsx2_v118()

    def _analyze_pcsx2_v118(self) -> None:
        value = self._pcsx2_ini_var_v118.get().strip()
        if not value:
            self._pcsx2_status_var_v118.set("Choose PCSX2.ini first.")
            return
        try:
            status = inspect_keyboard_config(value)
            preview = configure_fragment_pcsx2(value, dry_run=True)
        except Pcsx2SetupError as exc:
            self._pcsx2_status_var_v118.set(f"Cannot use this file: {exc}")
            return
        current_keyboard = status.current_type or "not set"
        current_network = preview.previous_network_enabled or "not set"
        ready = preview.status == "already-configured"
        self._pcsx2_status_var_v118.set(
            f"USB Port 1: {current_keyboard}\n"
            f"Ethernet enabled: {current_network}\n\n"
            + ("PCSX2 is ready for Fragment." if ready else "Changes are available; no file has been modified yet.")
        )

    def _configure_pcsx2_v118(self) -> None:
        value = self._pcsx2_ini_var_v118.get().strip()
        if not value:
            messagebox.showerror("PCSX2 Setup", "Choose PCSX2.ini first.", parent=self._pcsx2_window_v118)
            return
        if not messagebox.askyesno(
            "Enable Fragment settings?",
            "Close PCSX2 before continuing.\n\nFragmenter will enable the Konami USB keyboard and Ethernet, and save a backup beside PCSX2.ini. Continue?",
            parent=self._pcsx2_window_v118,
        ):
            return
        try:
            report = configure_fragment_pcsx2(value)
        except Pcsx2SetupError as exc:
            messagebox.showerror("PCSX2 Setup", str(exc), parent=self._pcsx2_window_v118)
            return
        if report.status == "already-configured":
            message = "PCSX2 was already ready for Fragment; nothing was changed."
        else:
            message = (
                "PCSX2 keyboard and Ethernet are enabled.\n\n"
                f"Backup: {report.backup_path}\n\nRestart PCSX2 before launching the game."
            )
        self._pcsx2_status_var_v118.set(message)
        messagebox.showinfo("PCSX2 Setup", message, parent=self._pcsx2_window_v118)

    def _browse_card_v118(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._pcsx2_window_v118,
            title="Choose a PCSX2 memory card",
            filetypes=(("PCSX2 memory cards", "*.ps2"), ("All files", "*.*")),
        )
        if selected:
            self._card_source_var_v118.set(selected)
            self._inspect_card_v118()

    def _browse_memcards_v118(self) -> None:
        selected = filedialog.askdirectory(
            parent=self._pcsx2_window_v118,
            title="Choose the PCSX2 memcards folder",
        )
        if selected:
            self._memcards_folder_var_v118.set(selected)

    def _inspect_card_v118(self) -> None:
        value = self._card_source_var_v118.get().strip()
        if not value:
            self._card_status_var_v118.set("Choose a raw .ps2 memory card first.")
            return
        try:
            info = inspect_memory_card(value)
        except Pcsx2SetupError as exc:
            self._card_status_var_v118.set(f"Cannot use this card: {exc}")
            return
        size_label = f"{info.size_mib} MiB" if info.size_mib is not None else f"{info.size:,} bytes"
        verdict = "Supported PCSX2 raw-card size." if info.supported_raw_size else "Unsupported raw-card size; installation will be refused."
        self._card_status_var_v118.set(
            f"Size: {size_label}\nSHA-256: {info.sha256}\n\n{verdict}\n"
            "Fragmenter does not change the source card or automatically select a PCSX2 slot."
        )

    def _install_card_v118(self) -> None:
        source = self._card_source_var_v118.get().strip()
        folder = self._memcards_folder_var_v118.get().strip()
        name = self._card_name_var_v118.get().strip() or "Fragment-Network.ps2"
        try:
            report = install_memory_card(source, folder, destination_name=name)
        except Pcsx2SetupError as exc:
            messagebox.showerror("Install Memory Card", str(exc), parent=self._pcsx2_window_v118)
            return
        message = (
            f"Memory card copied and verified:\n\n{report.destination_path}\n\n"
            "Open PCSX2 Memory Card settings and select this card for Port 1."
        )
        self._card_status_var_v118.set(message)
        messagebox.showinfo("Memory card installed", message, parent=self._pcsx2_window_v118)

    def _install_included_card_v118(self) -> None:
        folder = self._memcards_folder_var_v118.get().strip()
        name = self._card_name_var_v118.get().strip() or "Fragment-Network.ps2"
        if not folder:
            messagebox.showerror(
                "Install Network Card",
                "Choose the PCSX2 memcards folder first.",
                parent=self._pcsx2_window_v118,
            )
            return
        try:
            report = install_bundled_memory_card(
                folder,
                destination_name=name,
            )
        except Pcsx2SetupError as exc:
            messagebox.showerror(
                "Install Network Card", str(exc), parent=self._pcsx2_window_v118
            )
            return
        message = (
            f"Clean network card installed and verified:\n\n{report.destination_path}\n\n"
            "Open PCSX2 Memory Card settings and select this card for Port 1. "
            "Your existing cards were not changed."
        )
        self._card_status_var_v118.set(message)
        messagebox.showinfo(
            "Network card installed", message, parent=self._pcsx2_window_v118
        )

    def _close_pcsx2_helper_v118(self) -> None:
        window = self._pcsx2_window_v118
        self._pcsx2_window_v118 = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

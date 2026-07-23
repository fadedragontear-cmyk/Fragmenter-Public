#!/usr/bin/env python3
"""Fragmenter 1.0 public-release GUI shell.

This is intentionally separate from ``fragmenter_gui.py`` while the public
workflows stabilize. Every enabled action calls a project-bound service; there are
no replacement/editing controls and no fake transport buttons.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from audio_mixer_controller_v1 import (
    NoRenderableMapping,
    render_sequence_preview,
    sequence_resolver_view_model,
    sequence_rows,
    use_sequence_mapping,
)
from audio_playback import AudioPlaybackEngine
from backup_controller_v1 import (
    backup_memory_card,
    backup_server_saves,
    backup_view_model,
    restore_memory_card,
    restore_server_saves,
)
from project_setup_controller_v1 import create_setup_project, load_setup_project, setup_view_model
from project_workspace_v1 import FragmenterProjectV1
from report_locator_v1 import report_locator_view_model, write_diagnostics_summary
from run_all_executor_v1 import execute_run_all
from run_all_plan_v1 import build_run_all_plan, celdra_line
from server_explorer_controller_v1 import (
    export_project_server_file,
    inspect_project_server_file,
    server_explorer_view_model,
)
from settings_v1 import FragmenterSettingsV1, load_project_settings, save_project_settings
from visual_asset_controller_v1 import (
    extract_visual_animation,
    extract_visual_scene,
    extract_visual_textures,
    visual_asset_view_model,
)

APP_TITLE = "Fragmenter 1.0"
PUBLIC_TABS = ("Setup", "RUN ALL", "3D / Assets", "Audio", "Server Explorer", "Backups", "Reports", "Settings")


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str)


def _open_path(path: str | Path) -> None:
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(target)
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(target)])


def _replace_text(widget: tk.Text, text: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    widget.configure(state="disabled")


class PublicFragmenterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x820")
        self.minsize(980, 680)
        self.project: FragmenterProjectV1 | None = None
        self.playback = AudioPlaybackEngine()
        self.task_active = False
        self.cancel_event = threading.Event()
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.current_task_label = tk.StringVar(value="Idle")
        self.project_label = tk.StringVar(value="No active project")
        self.status_label = tk.StringVar(value="Create or load a Fragmenter 1.0 project.")
        self._build_header()
        self._build_tabs()
        self.after(100, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_header(self) -> None:
        frame = ttk.Frame(self, padding=(10, 8))
        frame.pack(fill="x")
        ttk.Label(frame, text="Fragmenter", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(frame, textvariable=self.project_label).pack(side="left", padx=18)
        ttk.Label(frame, textvariable=self.current_task_label).pack(side="right")

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tabs: dict[str, ttk.Frame] = {}
        builders = {
            "Setup": self._build_setup,
            "RUN ALL": self._build_run_all,
            "3D / Assets": self._build_visual,
            "Audio": self._build_audio,
            "Server Explorer": self._build_server,
            "Backups": self._build_backups,
            "Reports": self._build_reports,
            "Settings": self._build_settings,
        }
        for label in PUBLIC_TABS:
            frame = ttk.Frame(self.notebook, padding=8)
            self.notebook.add(frame, text=label)
            self.tabs[label] = frame
            builders[label](frame)

    def _build_setup(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self.setup_vars = {
            "iso": tk.StringVar(),
            "server": tk.StringVar(),
            "saves": tk.StringVar(),
            "card": tk.StringVar(),
            "workspace": tk.StringVar(),
        }
        rows = (
            ("Game ISO", "iso", self._pick_iso),
            ("Area Server root", "server", self._pick_server),
            ("Server saves", "saves", self._pick_saves),
            ("Memory card", "card", self._pick_card),
            ("Project workspace", "workspace", self._pick_workspace),
        )
        for row, (label, key, picker) in enumerate(rows):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(parent, textvariable=self.setup_vars[key]).grid(row=row, column=1, sticky="ew", pady=4)
            ttk.Button(parent, text="Browse", command=picker).grid(row=row, column=2, padx=(8, 0), pady=4)
        actions = ttk.Frame(parent)
        actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        ttk.Button(actions, text="Create Fresh Project", command=self._create_project).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Load Project", command=self._load_project_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Refresh Status", command=self._refresh_setup).pack(side="left")
        self.setup_tree = ttk.Treeview(parent, columns=("status", "path"), show="headings", height=7)
        self.setup_tree.heading("status", text="Status")
        self.setup_tree.heading("path", text="Source")
        self.setup_tree.column("status", width=130, stretch=False)
        self.setup_tree.column("path", width=850, stretch=True)
        self.setup_tree.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(4, 8))
        parent.rowconfigure(6, weight=1)
        ttk.Label(parent, textvariable=self.status_label, wraplength=1000).grid(row=7, column=0, columnspan=3, sticky="ew")

    def _build_run_all(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=2)
        parent.rowconfigure(2, weight=1)
        buttons = ttk.Frame(parent)
        buttons.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.run_button = ttk.Button(buttons, text="RUN ALL", command=self._run_all)
        self.run_button.pack(side="left", padx=(0, 6))
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self._cancel_task, state="disabled")
        self.cancel_button.pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Refresh Plan", command=self._refresh_run_plan).pack(side="left")
        self.run_tree = ttk.Treeview(parent, columns=("status", "description"), show="tree headings")
        self.run_tree.heading("#0", text="Stage")
        self.run_tree.heading("status", text="Status")
        self.run_tree.heading("description", text="Description")
        self.run_tree.column("#0", width=220, stretch=False)
        self.run_tree.column("status", width=110, stretch=False)
        self.run_tree.column("description", width=800, stretch=True)
        self.run_tree.grid(row=1, column=0, sticky="nsew")
        self.run_log = tk.Text(parent, height=10, wrap="word")
        self.run_log.grid(row=2, column=0, sticky="nsew", pady=(6, 0))

    def _build_visual(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.visual_search = tk.StringVar()
        ttk.Label(controls, text="Search").pack(side="left")
        ttk.Entry(controls, textvariable=self.visual_search, width=35).pack(side="left", padx=6)
        ttk.Button(controls, text="Refresh", command=self._refresh_visual_assets).pack(side="left")
        for label, command in (
            ("Inspect Structure", self._visual_inspect),
            ("Extract Textures", self._visual_textures),
            ("Scene Metadata", self._visual_scene),
            ("Animation Metadata", self._visual_animation),
        ):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=(6, 0))
        self.visual_tree = ttk.Treeview(parent, columns=("path",), show="tree headings")
        self.visual_tree.heading("#0", text="Asset")
        self.visual_tree.heading("path", text="Project-relative path")
        self.visual_tree.column("#0", width=220)
        self.visual_tree.column("path", width=420, stretch=True)
        self.visual_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.visual_details = tk.Text(parent, wrap="word")
        self.visual_details.grid(row=1, column=1, sticky="nsew")
        self.visual_payloads: dict[str, str] = {}
        self.visual_search.trace_add("write", lambda *_: self._refresh_visual_assets())

    def _build_audio(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(controls, text="Refresh Sequences", command=self._refresh_audio_sequences).pack(side="left")
        ttk.Button(controls, text="Render & Play", command=self._audio_render_play).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Use This Mapping", command=self._audio_use_mapping).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Stop", command=self._audio_stop).pack(side="left", padx=(6, 0))
        self.pause_button = ttk.Button(controls, text="Pause", command=self._audio_pause, state="normal" if self.playback.supports_pause else "disabled")
        self.pause_button.pack(side="left", padx=(6, 0))
        self.resume_button = ttk.Button(controls, text="Resume", command=self._audio_resume, state="normal" if self.playback.supports_pause else "disabled")
        self.resume_button.pack(side="left", padx=(6, 0))
        ttk.Label(controls, text=f"Backend: {self.playback.backend_name}").pack(side="right")
        self.audio_gain = tk.DoubleVar(value=1.0)
        ttk.Label(controls, text="Gain").pack(side="left", padx=(16, 4))
        ttk.Scale(controls, from_=0.0, to=1.0, variable=self.audio_gain, length=140).pack(side="left")
        self.sequence_tree = ttk.Treeview(parent, columns=("events", "mapping"), show="tree headings")
        self.sequence_tree.heading("#0", text="Sequence")
        self.sequence_tree.heading("events", text="Note events")
        self.sequence_tree.heading("mapping", text="Mapping")
        self.sequence_tree.column("#0", width=390)
        self.sequence_tree.column("events", width=90, stretch=False)
        self.sequence_tree.column("mapping", width=150, stretch=False)
        self.sequence_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.sequence_tree.bind("<<TreeviewSelect>>", lambda _e: self._refresh_audio_candidates())
        right = ttk.Frame(parent)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.program_tree = ttk.Treeview(right, columns=("programs", "slots", "samples"), show="tree headings")
        self.program_tree.heading("#0", text="Candidate Program resource")
        for key, label in (("programs", "Programs"), ("slots", "Slots"), ("samples", "Sample WAVs")):
            self.program_tree.heading(key, text=label)
            self.program_tree.column(key, width=90, stretch=False)
        self.program_tree.grid(row=0, column=0, sticky="nsew")
        self.audio_details = tk.Text(right, height=10, wrap="word")
        self.audio_details.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.sequence_payloads: dict[str, dict[str, Any]] = {}
        self.program_payloads: dict[str, dict[str, Any]] = {}

    def _build_server(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(controls, text="Refresh", command=self._refresh_server).pack(side="left")
        ttk.Button(controls, text="Inspect", command=self._inspect_server).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Export Decompressed", command=self._export_server).pack(side="left", padx=(6, 0))
        self.server_tree = ttk.Treeview(parent, columns=("size", "compression", "path"), show="headings")
        for key, label, width in (("size", "Size", 100), ("compression", "Compression", 110), ("path", "Path", 350)):
            self.server_tree.heading(key, text=label)
            self.server_tree.column(key, width=width, stretch=key == "path")
        self.server_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.server_payloads: dict[str, str] = {}
        details = ttk.Notebook(parent)
        details.grid(row=1, column=1, sticky="nsew")
        self.server_texts: dict[str, tk.Text] = {}
        for label in ("Overview", "Clean Text", "Structure / Members", "Hex"):
            frame = ttk.Frame(details)
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            text = tk.Text(frame, wrap="none" if label == "Hex" else "word")
            text.grid(row=0, column=0, sticky="nsew")
            details.add(frame, text=label)
            self.server_texts[label] = text

    def _build_backups(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(controls, text="Refresh", command=self._refresh_backups).pack(side="left")
        ttk.Button(controls, text="Back Up Server Saves", command=self._backup_server).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Back Up Memory Card", command=self._backup_card).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Restore Selected", command=self._restore_backup).pack(side="left", padx=(6, 0))
        self.server_backup_tree = ttk.Treeview(parent, columns=("manifest",), show="tree headings")
        self.server_backup_tree.heading("#0", text="Server-save backup")
        self.server_backup_tree.heading("manifest", text="Manifest")
        self.server_backup_tree.column("#0", width=220)
        self.server_backup_tree.column("manifest", width=450, stretch=True)
        self.server_backup_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.card_backup_tree = ttk.Treeview(parent, columns=("manifest",), show="tree headings")
        self.card_backup_tree.heading("#0", text="Memory-card backup")
        self.card_backup_tree.heading("manifest", text="Manifest")
        self.card_backup_tree.column("#0", width=220)
        self.card_backup_tree.column("manifest", width=450, stretch=True)
        self.card_backup_tree.grid(row=1, column=1, sticky="nsew")

    def _build_reports(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(controls, text="Refresh", command=self._refresh_reports).pack(side="left")
        ttk.Button(controls, text="Open Selected", command=self._open_report).pack(side="left", padx=(6, 0))
        self.report_tree = ttk.Treeview(parent, columns=("status", "path"), show="tree headings")
        self.report_tree.heading("#0", text="Report")
        self.report_tree.heading("status", text="Status")
        self.report_tree.heading("path", text="Path")
        self.report_tree.column("#0", width=220)
        self.report_tree.column("status", width=100, stretch=False)
        self.report_tree.column("path", width=750, stretch=True)
        self.report_tree.grid(row=1, column=0, sticky="nsew")
        self.report_payloads: dict[str, str] = {}

    def _build_settings(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self.setting_vars = {
            "theme": tk.StringVar(value="system"),
            "accent": tk.StringVar(value="#4F7CAC"),
            "scale": tk.DoubleVar(value=1.0),
            "volume": tk.DoubleVar(value=1.0),
            "preview": tk.StringVar(value="assembled"),
            "cache": tk.BooleanVar(value=True),
            "diagnostics": tk.BooleanVar(value=True),
            "experimental": tk.BooleanVar(value=False),
            "celdra": tk.BooleanVar(value=False),
            "celdra_commentary": tk.BooleanVar(value=False),
        }
        ttk.Label(parent, text="Theme").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.setting_vars["theme"], values=("system", "light", "dark"), state="readonly").grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Accent color").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.setting_vars["accent"]).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="UI scale").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Scale(parent, from_=0.75, to=2.0, variable=self.setting_vars["scale"]).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Default volume").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Scale(parent, from_=0.0, to=2.0, variable=self.setting_vars["volume"]).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Default 3D mode").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.setting_vars["preview"], values=("assembled", "selected_object", "raw_model"), state="readonly").grid(row=4, column=1, sticky="ew", pady=4)
        checks = (
            ("Reuse valid cache", "cache"),
            ("Keep diagnostics", "diagnostics"),
            ("Enable experimental tools", "experimental"),
            ("Enable Celdra", "celdra"),
            ("Enable Celdra checklist commentary", "celdra_commentary"),
        )
        for index, (label, key) in enumerate(checks, start=5):
            ttk.Checkbutton(parent, text=label, variable=self.setting_vars[key]).grid(row=index, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Button(parent, text="Save Settings", command=self._save_settings).grid(row=10, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _pick_iso(self) -> None:
        value = filedialog.askopenfilename(title="Select game ISO", filetypes=(("ISO images", "*.iso"), ("All files", "*.*")))
        if value: self.setup_vars["iso"].set(value)

    def _pick_server(self) -> None:
        value = filedialog.askdirectory(title="Select Area Server root")
        if value: self.setup_vars["server"].set(value)

    def _pick_saves(self) -> None:
        value = filedialog.askdirectory(title="Select Area Server save folder")
        if value: self.setup_vars["saves"].set(value)

    def _pick_card(self) -> None:
        value = filedialog.askopenfilename(title="Select whole memory-card file", filetypes=(("PCSX2 memory cards", "*.ps2 *.bin"), ("All files", "*.*")))
        if value: self.setup_vars["card"].set(value)

    def _pick_workspace(self) -> None:
        value = filedialog.askdirectory(title="Choose an empty Fragmenter project folder")
        if value: self.setup_vars["workspace"].set(value)

    def _create_project(self) -> None:
        try:
            self.project = create_setup_project(
                self.setup_vars["workspace"].get(),
                iso_path=self.setup_vars["iso"].get(),
                area_server_root=self.setup_vars["server"].get(),
                server_save_dir=self.setup_vars["saves"].get(),
                memory_card_path=self.setup_vars["card"].get(),
            )
            self._project_loaded()
        except Exception as exc:
            messagebox.showerror("Create Project", str(exc))

    def _load_project_dialog(self) -> None:
        value = filedialog.askopenfilename(title="Load Fragmenter project.json", filetypes=(("Fragmenter project", "project.json"), ("JSON", "*.json")))
        if not value: return
        try:
            self.project = load_setup_project(value)
            self._project_loaded()
        except Exception as exc:
            messagebox.showerror("Load Project", str(exc))

    def _project_loaded(self) -> None:
        assert self.project is not None
        self.project_label.set(str(self.project.project_path))
        self.setup_vars["iso"].set(self.project.sources.iso_path)
        self.setup_vars["server"].set(self.project.sources.area_server_root)
        self.setup_vars["saves"].set(self.project.sources.server_save_dir)
        self.setup_vars["card"].set(self.project.sources.memory_card_path)
        self.setup_vars["workspace"].set(self.project.workspace_dir)
        self._refresh_all()

    def _require_project(self) -> FragmenterProjectV1 | None:
        if self.project is None:
            messagebox.showinfo(APP_TITLE, "Create or load a Fragmenter 1.0 project first.")
        return self.project

    def _refresh_all(self) -> None:
        self._refresh_setup(); self._refresh_run_plan(); self._refresh_visual_assets()
        self._refresh_audio_sequences(); self._refresh_server(); self._refresh_backups(); self._refresh_reports(); self._load_settings()

    def _refresh_setup(self) -> None:
        self.setup_tree.delete(*self.setup_tree.get_children())
        if self.project is None: return
        model = setup_view_model(self.project)
        for row in model["rows"]:
            self.setup_tree.insert("", "end", values=(row["status"], row["path"]), tags=("ok" if row["ok"] else "missing",))
        self.setup_tree.tag_configure("ok", foreground="#147a36")
        self.setup_tree.tag_configure("missing", foreground="#a62020")
        self.status_label.set("Project ready." if model["ready"] else "Missing or invalid: " + ", ".join(model["blockers"]))

    def _refresh_run_plan(self) -> None:
        self.run_tree.delete(*self.run_tree.get_children())
        project = self._require_project()
        if project is None: return
        try:
            plan = build_run_all_plan(project)
        except Exception as exc:
            self._append_log(str(exc)); return
        for stage in plan["stages"]:
            self.run_tree.insert("", "end", iid=stage["key"], text=stage["label"], values=(stage["status"], stage["description"]))

    def _run_all(self) -> None:
        project = self._require_project()
        if project is None or self.task_active: return
        self.cancel_event = threading.Event()
        self._set_busy(True, "RUN ALL")
        self.run_log.delete("1.0", "end")
        def callback(event: dict[str, Any]) -> None: self.events.put({"kind": "run_event", "event": event})
        def work() -> Any: return execute_run_all(project, callback=callback, cancel_event=self.cancel_event)
        self._background("RUN ALL", work, self._run_all_done, already_busy=True)

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        self._set_busy(False)
        if error:
            self._append_log(f"RUN ALL failed: {error}"); return
        self._append_log(f"RUN ALL status: {result['status']}")
        for row in result["results"]:
            iid = row["key"]
            if self.run_tree.exists(iid): self.run_tree.set(iid, "status", row["status"])
        self._refresh_all()

    def _cancel_task(self) -> None:
        self.cancel_event.set()
        self.current_task_label.set("Cancellation requested")

    def _append_log(self, text: str) -> None:
        self.run_log.insert("end", text.rstrip() + "\n")
        self.run_log.see("end")

    def _refresh_visual_assets(self) -> None:
        self.visual_tree.delete(*self.visual_tree.get_children()); self.visual_payloads.clear()
        project = self.project
        if project is None: return
        root = project.workspace_path("extracted_ccs")
        query = self.visual_search.get().strip().lower()
        files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p).lower()) if root.is_dir() else []
        for index, path in enumerate(files[:5000]):
            relative = path.relative_to(root).as_posix()
            if query and query not in relative.lower(): continue
            iid = f"asset_{index}"
            self.visual_tree.insert("", "end", iid=iid, text=path.name, values=(relative,))
            self.visual_payloads[iid] = relative

    def _selected_visual(self) -> str | None:
        selected = self.visual_tree.selection()
        return self.visual_payloads.get(selected[0]) if selected else None

    def _visual_action(self, label: str, function: Callable[[FragmenterProjectV1, str], Any]) -> None:
        project = self._require_project(); asset = self._selected_visual()
        if project is None: return
        if not asset: messagebox.showinfo(label, "Select an extracted CCSF asset first."); return
        self._background(label, lambda: function(project, asset), lambda result, error: self._show_result(self.visual_details, label, result, error))

    def _visual_inspect(self) -> None: self._visual_action("Inspect Structure", visual_asset_view_model)
    def _visual_textures(self) -> None: self._visual_action("Extract Textures", extract_visual_textures)
    def _visual_scene(self) -> None: self._visual_action("Scene Metadata", extract_visual_scene)
    def _visual_animation(self) -> None: self._visual_action("Animation Metadata", extract_visual_animation)

    def _refresh_audio_sequences(self) -> None:
        self.sequence_tree.delete(*self.sequence_tree.get_children()); self.program_tree.delete(*self.program_tree.get_children())
        self.sequence_payloads.clear(); self.program_payloads.clear()
        project = self.project
        if project is None: return
        try: rows = sequence_rows(project)
        except Exception as exc:
            _replace_text(self.audio_details, f"Music reports are not ready: {exc}\nRun focused RUN ALL/SNDDATA preparation first.")
            return
        for index, row in enumerate(rows):
            iid = f"sequence_{index}"
            self.sequence_tree.insert("", "end", iid=iid, text=row["sequence_id"], values=(row["note_on_count"], row["mapping_status"]))
            self.sequence_payloads[iid] = row

    def _selected_sequence(self) -> dict[str, Any] | None:
        selected = self.sequence_tree.selection()
        return self.sequence_payloads.get(selected[0]) if selected else None

    def _selected_program(self) -> dict[str, Any] | None:
        selected = self.program_tree.selection()
        return self.program_payloads.get(selected[0]) if selected else None

    def _refresh_audio_candidates(self) -> None:
        self.program_tree.delete(*self.program_tree.get_children()); self.program_payloads.clear()
        project = self.project; sequence = self._selected_sequence()
        if project is None or sequence is None: return
        try: model = sequence_resolver_view_model(project, sequence["sequence_id"])
        except Exception as exc: _replace_text(self.audio_details, str(exc)); return
        for index, row in enumerate(model["candidate_details"]):
            iid = f"program_{index}"
            self.program_tree.insert("", "end", iid=iid, text=row["resource_id"], values=(row["program_count"], row["slot_count"], row["decoded_sample_wavs"]))
            self.program_payloads[iid] = row
        _replace_text(self.audio_details, _json_text(model))
        if self.program_tree.get_children():
            first = self.program_tree.get_children()[0]; self.program_tree.selection_set(first); self.program_tree.focus(first)

    def _audio_render_play(self) -> None:
        project = self._require_project(); sequence = self._selected_sequence(); program = self._selected_program()
        if project is None: return
        if sequence is None or program is None: messagebox.showinfo("Music Mixer", "Select a sequence and candidate Program resource."); return
        def work() -> Any: return render_sequence_preview(project, sequence["sequence_id"], program["resource_id"], master_gain=self.audio_gain.get())
        def done(result: Any, error: Exception | None) -> None:
            if error:
                if isinstance(error, NoRenderableMapping): _replace_text(self.audio_details, _json_text({"status": "not_renderable", "missing": error.missing}))
                else: messagebox.showerror("Render Preview", str(error))
                return
            try:
                self.playback.load(result["output_path"]); self.playback.set_gain(self.audio_gain.get()); self.playback.play()
                _replace_text(self.audio_details, _json_text(result))
            except Exception as exc: messagebox.showerror("Playback", str(exc))
        self._background("Render Music Preview", work, done)

    def _audio_use_mapping(self) -> None:
        project = self._require_project(); sequence = self._selected_sequence(); program = self._selected_program()
        if project is None: return
        if sequence is None or program is None: messagebox.showinfo("Music Mixer", "Select a sequence and candidate Program resource."); return
        try:
            result = use_sequence_mapping(project, sequence["sequence_id"], program["resource_id"], notes="Selected in Fragmenter public GUI")
            _replace_text(self.audio_details, _json_text(result)); self._refresh_audio_sequences()
        except Exception as exc: messagebox.showerror("Use Mapping", str(exc))

    def _audio_stop(self) -> None:
        try: self.playback.stop()
        except Exception as exc: messagebox.showerror("Stop", str(exc))
    def _audio_pause(self) -> None:
        try: self.playback.pause()
        except Exception as exc: messagebox.showerror("Pause", str(exc))
    def _audio_resume(self) -> None:
        try: self.playback.resume()
        except Exception as exc: messagebox.showerror("Resume", str(exc))

    def _refresh_server(self) -> None:
        self.server_tree.delete(*self.server_tree.get_children()); self.server_payloads.clear()
        project = self.project
        if project is None: return
        try: model = server_explorer_view_model(project)
        except Exception as exc: messagebox.showerror("Server Explorer", str(exc)); return
        for index, row in enumerate(model["files"]):
            iid = f"server_{index}"
            self.server_tree.insert("", "end", iid=iid, values=(f"{row['size']:,}", row["compression"], row["relative_path"]))
            self.server_payloads[iid] = row["relative_path"]

    def _selected_server(self) -> str | None:
        selected = self.server_tree.selection()
        return self.server_payloads.get(selected[0]) if selected else None

    def _inspect_server(self) -> None:
        project = self._require_project(); value = self._selected_server()
        if project is None: return
        if not value: messagebox.showinfo("Server Explorer", "Select a server file."); return
        def done(result: Any, error: Exception | None) -> None:
            if error: messagebox.showerror("Inspect Server File", str(error)); return
            _replace_text(self.server_texts["Overview"], _json_text(result["overview"]))
            _replace_text(self.server_texts["Clean Text"], result["clean_text_rendered"])
            _replace_text(self.server_texts["Structure / Members"], _json_text(result["structure"]))
            _replace_text(self.server_texts["Hex"], "\n".join(result["hex_preview"]["lines"]))
        self._background("Inspect Server File", lambda: inspect_project_server_file(project, value), done)

    def _export_server(self) -> None:
        project = self._require_project(); value = self._selected_server()
        if project is None: return
        if not value: messagebox.showinfo("Server Explorer", "Select a gzip-compressed server file."); return
        self._background("Export Decompressed", lambda: export_project_server_file(project, value), lambda result, error: self._result_dialog("Export Decompressed", result, error))

    def _refresh_backups(self) -> None:
        self.server_backup_tree.delete(*self.server_backup_tree.get_children()); self.card_backup_tree.delete(*self.card_backup_tree.get_children())
        project = self.project
        if project is None: return
        try: model = backup_view_model(project)
        except Exception as exc: messagebox.showerror("Backups", str(exc)); return
        for index, path in enumerate(model["server_save_backups"]): self.server_backup_tree.insert("", "end", iid=f"sb_{index}", text=Path(path).parent.name, values=(path,))
        for index, path in enumerate(model["memory_card_backups"]): self.card_backup_tree.insert("", "end", iid=f"cb_{index}", text=Path(path).parent.name, values=(path,))

    def _backup_server(self) -> None:
        project = self._require_project()
        if project: self._background("Back Up Server Saves", lambda: backup_server_saves(project), lambda result, error: self._backup_done("Server-save backup", result, error))
    def _backup_card(self) -> None:
        project = self._require_project()
        if project: self._background("Back Up Memory Card", lambda: backup_memory_card(project), lambda result, error: self._backup_done("Memory-card backup", result, error))
    def _backup_done(self, label: str, result: Any, error: Exception | None) -> None:
        self._result_dialog(label, result, error); self._refresh_backups()

    def _restore_backup(self) -> None:
        project = self._require_project()
        if project is None: return
        server_sel = self.server_backup_tree.selection(); card_sel = self.card_backup_tree.selection()
        if server_sel:
            manifest = self.server_backup_tree.item(server_sel[0], "values")[0]; function = restore_server_saves; label = "Restore Server Saves"
        elif card_sel:
            manifest = self.card_backup_tree.item(card_sel[0], "values")[0]; function = restore_memory_card; label = "Restore Memory Card"
        else:
            messagebox.showinfo("Restore", "Select a server-save or memory-card backup."); return
        if not messagebox.askyesno(label, "Fragmenter will first back up the current destination, then restore the selected verified backup. Continue?"): return
        self._background(label, lambda: function(project, manifest), lambda result, error: self._backup_done(label, result, error))

    def _refresh_reports(self) -> None:
        self.report_tree.delete(*self.report_tree.get_children()); self.report_payloads.clear()
        project = self.project
        if project is None: return
        try:
            write_diagnostics_summary(project); model = report_locator_view_model(project)
        except Exception as exc: messagebox.showerror("Reports", str(exc)); return
        for index, row in enumerate(model["normal_reports"]):
            iid = f"report_{index}"
            self.report_tree.insert("", "end", iid=iid, text=row["label"], values=("Ready" if row["exists"] else "Not generated", row["path"]))
            self.report_payloads[iid] = row["path"]

    def _open_report(self) -> None:
        selected = self.report_tree.selection()
        if not selected: messagebox.showinfo("Reports", "Select a report."); return
        try: _open_path(self.report_payloads[selected[0]])
        except Exception as exc: messagebox.showerror("Open Report", str(exc))

    def _load_settings(self) -> None:
        project = self.project
        if project is None: return
        try: settings = load_project_settings(project)
        except Exception as exc: messagebox.showerror("Settings", str(exc)); return
        self.setting_vars["theme"].set(settings.appearance.theme)
        self.setting_vars["accent"].set(settings.appearance.accent_color)
        self.setting_vars["scale"].set(settings.appearance.ui_scale)
        self.setting_vars["volume"].set(settings.playback.default_volume)
        self.setting_vars["preview"].set(settings.preview_3d.default_mode)
        self.setting_vars["cache"].set(settings.workspace.reuse_valid_cache)
        self.setting_vars["diagnostics"].set(settings.workspace.keep_diagnostics)
        self.setting_vars["experimental"].set(settings.advanced.enable_experimental_tools)
        self.setting_vars["celdra"].set(settings.celdra.enabled)
        self.setting_vars["celdra_commentary"].set(settings.celdra.checklist_commentary)

    def _save_settings(self) -> None:
        project = self._require_project()
        if project is None: return
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
            save_project_settings(project, settings)
            messagebox.showinfo("Settings", "Project settings saved.")
        except Exception as exc: messagebox.showerror("Settings", str(exc))

    def _background(self, label: str, work: Callable[[], Any], done: Callable[[Any, Exception | None], None], *, already_busy: bool = False) -> None:
        if self.task_active and not already_busy:
            messagebox.showwarning(APP_TITLE, "Another task is already running."); return
        if not already_busy: self._set_busy(True, label)
        def runner() -> None:
            try: result, error = work(), None
            except Exception as exc: result, error = None, exc
            self.events.put({"kind": "done", "label": label, "result": result, "error": error, "callback": done})
        threading.Thread(target=runner, daemon=True, name=f"fragmenter-{label}").start()

    def _set_busy(self, active: bool, label: str = "Idle") -> None:
        self.task_active = active
        self.current_task_label.set(label if active else "Idle")
        self.run_button.configure(state="disabled" if active else "normal")
        self.cancel_button.configure(state="normal" if active else "disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                item = self.events.get_nowait()
                if item["kind"] == "run_event": self._handle_run_event(item["event"])
                elif item["kind"] == "done":
                    if item["label"] != "RUN ALL": self._set_busy(False)
                    item["callback"](item["result"], item["error"])
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        stage = str(event.get("stage") or "")
        kind = event.get("kind")
        if kind == "start":
            if self.run_tree.exists(stage): self.run_tree.set(stage, "status", "running")
            line = celdra_line({"celdra_lines": [event.get("label") or stage]})
            self._append_log(line or f"Starting {event.get('label') or stage}")
        elif kind == "finish":
            if self.run_tree.exists(stage): self.run_tree.set(stage, "status", event.get("status") or "complete")
        elif kind == "output": self._append_log(str(event.get("line") or ""))

    def _show_result(self, widget: tk.Text, label: str, result: Any, error: Exception | None) -> None:
        _replace_text(widget, f"{label} failed: {error}" if error else _json_text(result))

    def _result_dialog(self, label: str, result: Any, error: Exception | None) -> None:
        if error: messagebox.showerror(label, str(error))
        else: messagebox.showinfo(label, _json_text(result)[:4000])

    def _close(self) -> None:
        try: self.cancel_event.set(); self.playback.stop()
        finally: self.destroy()


def main() -> int:
    PublicFragmenterApp().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

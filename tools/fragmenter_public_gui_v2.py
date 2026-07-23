#!/usr/bin/env python3
"""Second public GUI acceptance pass.

This layer subclasses the isolated v1 shell so the preserved GUI and the first WIP
checkpoint remain available.  It restores a real wireframe preview, removes the
visual-list truncation bug, moves expensive audio/report work off the Tk thread,
and adds useful progress and runtime settings behavior.
"""
from __future__ import annotations

import json
import math
import os
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

import ccsf_structure_decoder
from audio_mixer_controller_v2 import (
    NoRenderableMapping,
    clear_music_cache,
    render_sequence_preview_fast,
    sequence_resolver_view_model_fast,
    sequence_rows_fast,
)
from fragmenter_public_gui import (
    APP_TITLE,
    PublicFragmenterApp,
    _json_text,
    _replace_text,
)
from project_setup_controller_v1 import create_setup_project, load_setup_project
from project_workspace_v1 import FragmenterProjectV1
from run_all_plan_v1 import build_run_all_plan
from settings_v1 import FragmenterSettingsV1, load_project_settings, save_project_settings

LIKELY_VISUAL_EXTENSIONS = {".tmp", ".ccs", ".ccsf", ".cmp", ".bin"}
DEFAULT_PROJECT_NAME = "Default Project"
MAX_VISUAL_ROWS = 30000
MAX_WIREFRAME_FACES = 16000


def default_project_folder() -> Path:
    documents = Path.home() / "Documents"
    base = documents if documents.exists() else Path.home()
    return base / "Fragmenter Projects" / DEFAULT_PROJECT_NAME


def _candidate_path(root: Path, workspace: Path, value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    candidates = [path] if path.is_absolute() else [root / path, workspace / path]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root.resolve())
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def discover_visual_assets(project: FragmenterProjectV1, query: str = "", limit: int = MAX_VISUAL_ROWS) -> list[dict[str, Any]]:
    """Return project CCSF assets without applying the old cap before filtering."""
    root = project.workspace_path("extracted_ccs")
    workspace = Path(project.workspace_dir)
    if not root.is_dir():
        return []
    indexed: dict[Path, dict[str, Any]] = {}
    library_path = project.workspace_path("reports") / "asset_library.json"
    if library_path.is_file():
        try:
            library = json.loads(library_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            library = {}
        for asset in library.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            values: list[Any] = [asset.get("preferred_file"), asset.get("relative_file"), asset.get("file")]
            values.extend(asset.get("duplicate_files") or [])
            for value in values:
                path = _candidate_path(root, workspace, value)
                if path is None:
                    continue
                indexed.setdefault(
                    path,
                    {
                        "path": path,
                        "name": str(asset.get("display_name") or asset.get("name") or path.name),
                        "kind": str(asset.get("type") or "CCSF asset"),
                        "source": "asset library",
                    },
                )
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in LIKELY_VISUAL_EXTENSIONS:
            continue
        indexed.setdefault(path.resolve(), {"path": path.resolve(), "name": path.name, "kind": "CCSF file", "source": "filesystem"})
    needle = query.strip().lower()
    rows: list[dict[str, Any]] = []
    for path, metadata in indexed.items():
        relative = path.relative_to(root.resolve()).as_posix()
        haystack = f"{metadata['name']} {metadata['kind']} {relative}".lower()
        if needle and not all(token in haystack for token in needle.split()):
            continue
        stat = path.stat()
        rows.append(
            {
                "name": metadata["name"],
                "kind": metadata["kind"],
                "relative_path": relative,
                "absolute_path": str(path),
                "size": stat.st_size,
                "source": metadata["source"],
            }
        )
    rows.sort(key=lambda row: (str(row["kind"]).lower(), str(row["name"]).lower(), str(row["relative_path"]).lower()))
    return rows[: max(1, int(limit))]


def build_wireframe_payload(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    report = ccsf_structure_decoder.decode(source)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    model_names: list[str] = []
    for record in report.records:
        model = record.get("model") if isinstance(record.get("model"), dict) else None
        if not model:
            continue
        model_names.append(str(record.get("object_name") or record.get("object_id") or "model"))
        for submodel in model.get("submodels") or []:
            if not isinstance(submodel, dict):
                continue
            base = len(vertices)
            for raw in submodel.get("vertices") or []:
                value = raw.get("position") if isinstance(raw, dict) else raw
                if isinstance(value, (list, tuple)) and len(value) >= 3:
                    vertices.append((float(value[0]), float(value[1]), float(value[2])))
            for raw_face in submodel.get("faces") or []:
                if not isinstance(raw_face, (list, tuple)) or len(raw_face) < 3:
                    continue
                face = (base + int(raw_face[0]), base + int(raw_face[1]), base + int(raw_face[2]))
                if all(0 <= index < len(vertices) for index in face):
                    faces.append(face)
    original_face_count = len(faces)
    if len(faces) > MAX_WIREFRAME_FACES:
        step = max(1, math.ceil(len(faces) / MAX_WIREFRAME_FACES))
        faces = faces[::step]
    return {
        "source": str(source),
        "vertices": vertices,
        "faces": faces,
        "vertex_count": len(vertices),
        "face_count": original_face_count,
        "displayed_face_count": len(faces),
        "models": model_names,
        "errors": list(report.errors),
        "warnings": list(report.warnings),
    }


def parse_progress_line(line: str) -> float | None:
    text = str(line or "").strip()
    match = re.search(r"\bPROGRESS\s+(\d+)\s+(\d+)\b", text)
    if match and int(match.group(2)) > 0:
        return min(100.0, int(match.group(1)) * 100.0 / int(match.group(2)))
    match = re.search(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%", text)
    if match:
        return min(100.0, float(match.group(1)))
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        for current_key, total_key in (("current_index", "total"), ("container_index", "container_total")):
            current = int(payload.get(current_key) or 0)
            total = int(payload.get(total_key) or 0)
            if current > 0 and total > 0:
                return min(100.0, current * 100.0 / total)
    return None


class PublicFragmenterAppV2(PublicFragmenterApp):
    def __init__(self) -> None:
        self._visual_generation = 0
        self._audio_generation = 0
        self._candidate_generation = 0
        self._wireframe_generation = 0
        self._wireframe_payload: dict[str, Any] | None = None
        self._wire_yaw = -0.55
        self._wire_pitch = 0.35
        self._wire_zoom = 1.0
        self._wire_drag: tuple[int, int] | None = None
        self._stage_order: list[str] = []
        self._stage_bars: dict[str, ttk.Progressbar] = {}
        self._stage_values: dict[str, float] = {}
        self._base_tk_scaling = 1.0
        super().__init__()
        try:
            self._base_tk_scaling = float(self.tk.call("tk", "scaling"))
        except Exception:
            self._base_tk_scaling = 1.0
        if not self.setup_vars["workspace"].get():
            self.setup_vars["workspace"].set(str(default_project_folder()))
        self._apply_runtime_palette("system", "#4F7CAC", 1.0)
        self.after(50, self._load_default_project_if_present)

    def _build_header(self) -> None:
        self.header_frame = tk.Frame(self, bg="#315F86", padx=12, pady=8)
        self.header_frame.pack(fill="x")
        self.header_title = tk.Label(self.header_frame, text="Fragmenter", bg="#315F86", fg="white", font=("Segoe UI", 18, "bold"))
        self.header_title.pack(side="left")
        self.header_project = tk.Label(self.header_frame, textvariable=self.project_label, bg="#315F86", fg="#EAF4FF")
        self.header_project.pack(side="left", padx=18)
        self.header_task = tk.Label(self.header_frame, textvariable=self.current_task_label, bg="#315F86", fg="white")
        self.header_task.pack(side="right")

    def _build_setup(self, parent: ttk.Frame) -> None:
        super()._build_setup(parent)
        ttk.Label(
            parent,
            text="A default project folder is supplied automatically. Existing project.json files are loaded instead of overwritten.",
            wraplength=1000,
        ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _build_run_all(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        buttons = ttk.Frame(parent)
        buttons.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.run_button = ttk.Button(buttons, text="RUN ALL", command=self._run_all, style="Accent.TButton")
        self.run_button.pack(side="left", padx=(0, 6))
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self._cancel_task, state="disabled")
        self.cancel_button.pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Refresh Plan", command=self._refresh_run_plan).pack(side="left")
        ttk.Label(buttons, text="Extract CCSF Library can take several minutes on the first run.").pack(side="right")

        self.run_paned = ttk.Panedwindow(parent, orient="vertical")
        self.run_paned.grid(row=2, column=0, sticky="nsew")
        top = ttk.Frame(self.run_paned)
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)
        top.rowconfigure(0, weight=1)
        self.run_tree = ttk.Treeview(top, columns=("status", "description"), show="tree headings")
        self.run_tree.heading("#0", text="Stage")
        self.run_tree.heading("status", text="Status")
        self.run_tree.heading("description", text="Description")
        self.run_tree.column("#0", width=210, stretch=False)
        self.run_tree.column("status", width=100, stretch=False)
        self.run_tree.column("description", width=520, stretch=True)
        self.run_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        progress_box = ttk.LabelFrame(top, text="Function progress", padding=6)
        progress_box.grid(row=0, column=1, sticky="nsew")
        progress_box.columnconfigure(1, weight=1)
        self.stage_progress_frame = progress_box
        self.run_paned.add(top, weight=3)

        console = ttk.Frame(self.run_paned)
        console.columnconfigure(0, weight=1)
        console.rowconfigure(2, weight=1)
        self.overall_progress_label = tk.StringVar(value="Overall progress: idle")
        ttk.Label(console, textvariable=self.overall_progress_label).grid(row=0, column=0, sticky="w")
        self.overall_progress = ttk.Progressbar(console, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar")
        self.overall_progress.grid(row=1, column=0, sticky="ew", pady=(3, 5))
        log_frame = ttk.Frame(console)
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.run_log = tk.Text(log_frame, height=9, wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.run_log.yview)
        self.run_log.configure(yscrollcommand=scrollbar.set)
        self.run_log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.run_paned.add(console, weight=1)

    def _build_visual(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=3)
        parent.rowconfigure(2, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.visual_search = tk.StringVar()
        ttk.Label(controls, text="Search").pack(side="left")
        ttk.Entry(controls, textvariable=self.visual_search, width=32).pack(side="left", padx=6)
        ttk.Button(controls, text="Refresh", command=self._refresh_visual_assets).pack(side="left")
        ttk.Button(controls, text="Load Wireframe", command=self._wireframe_load, style="Accent.TButton").pack(side="left", padx=(6, 0))
        for label, command in (
            ("Inspect Structure", self._visual_inspect),
            ("Extract Textures", self._visual_textures),
            ("Scene Metadata", self._visual_scene),
            ("Animation Metadata", self._visual_animation),
        ):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=(6, 0))
        self.visual_status = tk.StringVar(value="No project loaded")
        ttk.Label(parent, textvariable=self.visual_status).grid(row=1, column=0, sticky="w")
        self.visual_progress = ttk.Progressbar(parent, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar")
        self.visual_progress.grid(row=1, column=1, sticky="ew", pady=(0, 4))
        self.visual_tree = ttk.Treeview(parent, columns=("kind", "size", "path"), show="tree headings")
        self.visual_tree.heading("#0", text="Asset")
        self.visual_tree.heading("kind", text="Type")
        self.visual_tree.heading("size", text="Size")
        self.visual_tree.heading("path", text="Project-relative path")
        self.visual_tree.column("#0", width=210)
        self.visual_tree.column("kind", width=150)
        self.visual_tree.column("size", width=90, stretch=False)
        self.visual_tree.column("path", width=360, stretch=True)
        self.visual_tree.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
        self.visual_tree.bind("<<TreeviewSelect>>", lambda _event: self._schedule_wireframe_load())
        self.visual_tree.bind("<Double-1>", lambda _event: self._wireframe_load())

        right = ttk.Panedwindow(parent, orient="vertical")
        right.grid(row=2, column=1, sticky="nsew")
        preview_frame = ttk.LabelFrame(right, text="Wireframe preview")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.visual_canvas = tk.Canvas(preview_frame, background="#101820", highlightthickness=0)
        self.visual_canvas.grid(row=0, column=0, sticky="nsew")
        self.visual_canvas.bind("<Configure>", lambda _event: self._draw_wireframe())
        self.visual_canvas.bind("<ButtonPress-1>", self._wire_start_drag)
        self.visual_canvas.bind("<B1-Motion>", self._wire_drag_motion)
        self.visual_canvas.bind("<ButtonRelease-1>", lambda _event: setattr(self, "_wire_drag", None))
        self.visual_canvas.bind("<MouseWheel>", self._wire_mousewheel)
        self.visual_canvas.create_text(20, 20, anchor="nw", fill="#BFD7EA", text="Select an asset to decode its wireframe.")
        right.add(preview_frame, weight=3)
        detail_frame = ttk.Frame(right)
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        self.visual_details = tk.Text(detail_frame, height=10, wrap="word")
        self.visual_details.grid(row=0, column=0, sticky="nsew")
        right.add(detail_frame, weight=1)
        self.visual_payloads: dict[str, dict[str, Any]] = {}
        self._visual_search_after: str | None = None
        self.visual_search.trace_add("write", lambda *_: self._debounce_visual_refresh())

    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        parent.rowconfigure(1, weight=1)
        self.audio_status = tk.StringVar(value="Music reports have not been loaded.")
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        status_frame.columnconfigure(1, weight=1)
        ttk.Label(status_frame, textvariable=self.audio_status).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.audio_progress = ttk.Progressbar(status_frame, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar")
        self.audio_progress.grid(row=0, column=1, sticky="ew")

    def _build_settings(self, parent: ttk.Frame) -> None:
        super()._build_settings(parent)
        self.setting_vars["default_workspace"] = tk.StringVar(value=str(default_project_folder().parent))
        ttk.Label(parent, text="Default project root").grid(row=11, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.setting_vars["default_workspace"]).grid(row=11, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Theme, accent, UI scale, playback gain and loop mode apply immediately when settings are saved.", wraplength=900).grid(row=12, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _load_default_project_if_present(self) -> None:
        if self.project is not None:
            return
        project_file = default_project_folder() / "project.json"
        if not project_file.is_file():
            return
        try:
            self.project = load_setup_project(project_file)
            self._project_loaded()
            self.status_label.set(f"Loaded default project: {project_file}")
        except Exception as exc:
            self.status_label.set(f"Default project exists but could not be loaded: {exc}")

    def _pick_workspace(self) -> None:
        initial = Path(self.setup_vars["workspace"].get() or default_project_folder()).parent
        value = filedialog.askdirectory(title="Choose Fragmenter project folder", initialdir=str(initial))
        if value:
            self.setup_vars["workspace"].set(value)

    def _create_project(self) -> None:
        workspace_text = self.setup_vars["workspace"].get().strip() or str(default_project_folder())
        workspace = Path(workspace_text).expanduser()
        self.setup_vars["workspace"].set(str(workspace))
        try:
            workspace.parent.mkdir(parents=True, exist_ok=True)
            if (workspace / "project.json").is_file():
                self.project = load_setup_project(workspace / "project.json")
            else:
                workspace.mkdir(parents=True, exist_ok=True)
                self.project = create_setup_project(
                    workspace,
                    iso_path=self.setup_vars["iso"].get(),
                    area_server_root=self.setup_vars["server"].get(),
                    server_save_dir=self.setup_vars["saves"].get(),
                    memory_card_path=self.setup_vars["card"].get(),
                )
            self._project_loaded()
        except Exception as exc:
            messagebox.showerror("Create Project", str(exc))

    def _refresh_all(self) -> None:
        self._refresh_setup()
        self._refresh_run_plan()
        self._refresh_visual_assets()
        self._refresh_audio_sequences()
        self._refresh_server()
        self._refresh_backups()
        self._refresh_reports()
        self._load_settings()

    def _local_worker(self, label: str, work: Callable[[], Any], done: Callable[[Any, Exception | None], None]) -> None:
        def runner() -> None:
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, exc
            self.events.put({"kind": "local_done", "label": label, "result": result, "error": error, "callback": done})
        threading.Thread(target=runner, daemon=True, name=f"fragmenter-local-{label}").start()

    def _drain_events(self) -> None:
        try:
            while True:
                item = self.events.get_nowait()
                if item["kind"] == "run_event":
                    self._handle_run_event(item["event"])
                elif item["kind"] == "done":
                    if item["label"] != "RUN ALL":
                        self._set_busy(False)
                    item["callback"](item["result"], item["error"])
                elif item["kind"] == "local_done":
                    item["callback"](item["result"], item["error"])
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _refresh_run_plan(self) -> None:
        self.run_tree.delete(*self.run_tree.get_children())
        for child in self.stage_progress_frame.winfo_children():
            child.destroy()
        self._stage_bars.clear()
        self._stage_values.clear()
        self._stage_order.clear()
        project = self.project
        if project is None:
            return
        try:
            plan = build_run_all_plan(project)
        except Exception as exc:
            self._append_log(str(exc))
            return
        for row_index, stage in enumerate(plan["stages"]):
            description = stage["description"]
            if stage["key"] == "ccsf_extract":
                description += " First extraction may take several minutes."
            self.run_tree.insert("", "end", iid=stage["key"], text=stage["label"], values=(stage["status"], description))
            ttk.Label(self.stage_progress_frame, text=stage["label"]).grid(row=row_index, column=0, sticky="w", padx=(0, 6), pady=2)
            bar = ttk.Progressbar(self.stage_progress_frame, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar", length=180)
            bar.grid(row=row_index, column=1, sticky="ew", pady=2)
            self._stage_bars[stage["key"]] = bar
            self._stage_values[stage["key"]] = 0.0
            self._stage_order.append(stage["key"])
        self.overall_progress["value"] = 0.0
        self.overall_progress_label.set("Overall progress: ready")

    def _run_all(self) -> None:
        self.overall_progress["value"] = 0.0
        self.overall_progress_label.set("Overall progress: starting")
        super()._run_all()

    def _set_stage_progress(self, stage: str, value: float, status: str | None = None) -> None:
        bar = self._stage_bars.get(stage)
        if bar is not None:
            try:
                bar.stop()
                bar.configure(mode="determinate")
                bar["value"] = max(0.0, min(100.0, value))
            except tk.TclError:
                pass
        self._stage_values[stage] = max(0.0, min(100.0, value))
        if status and self.run_tree.exists(stage):
            self.run_tree.set(stage, "status", status)
        if self._stage_order:
            total = sum(self._stage_values.get(key, 0.0) for key in self._stage_order) / len(self._stage_order)
            self.overall_progress["value"] = total
            self.overall_progress_label.set(f"Overall progress: {total:.0f}%")

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        stage = str(event.get("stage") or "")
        kind = event.get("kind")
        if kind == "start":
            if self.run_tree.exists(stage):
                self.run_tree.set(stage, "status", "running")
            bar = self._stage_bars.get(stage)
            if bar is not None:
                bar.configure(mode="indeterminate")
                bar.start(70)
            label = str(event.get("label") or stage)
            self._append_log(f"Starting {label}")
            if stage == "ccsf_extract":
                self._append_log("Extract CCSF Library may take several minutes on the first run. Existing verified output will be reused on later runs.")
        elif kind == "finish":
            status = str(event.get("status") or "complete")
            self._set_stage_progress(stage, 100.0 if status in {"complete", "reused"} else self._stage_values.get(stage, 0.0), status)
            if event.get("error"):
                self._append_log(str(event["error"]))
        elif kind == "output":
            line = str(event.get("line") or "")
            self._append_log(line)
            value = parse_progress_line(line)
            if value is not None:
                self._set_stage_progress(stage, value, "running")

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        super()._run_all_done(result, error)
        if error:
            self.overall_progress_label.set("Overall progress: failed")
        elif result:
            status = str(result.get("status") or "complete")
            if status == "complete":
                self.overall_progress["value"] = 100.0
            self.overall_progress_label.set(f"Overall progress: {status}")
            clear_music_cache(self.project)

    def _debounce_visual_refresh(self) -> None:
        if self._visual_search_after is not None:
            try:
                self.after_cancel(self._visual_search_after)
            except tk.TclError:
                pass
        self._visual_search_after = self.after(220, self._refresh_visual_assets)

    def _refresh_visual_assets(self) -> None:
        project = self.project
        self._visual_generation += 1
        generation = self._visual_generation
        self.visual_tree.delete(*self.visual_tree.get_children())
        self.visual_payloads.clear()
        if project is None:
            return
        self.visual_status.set("Scanning extracted CCSF library…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)
        query = self.visual_search.get()

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._visual_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            self.visual_progress["value"] = 100.0 if not error else 0.0
            if error:
                self.visual_status.set(f"Asset scan failed: {error}")
                return
            for index, row in enumerate(rows):
                iid = f"asset_{index}"
                self.visual_tree.insert("", "end", iid=iid, text=row["name"], values=(row["kind"], f"{row['size']:,}", row["relative_path"]))
                self.visual_payloads[iid] = row
            self.visual_status.set(f"Showing {len(rows):,} extracted visual assets. Search is applied before the display cap.")
        self._local_worker("visual-index", lambda: discover_visual_assets(project, query), done)

    def _selected_visual(self) -> str | None:
        selected = self.visual_tree.selection()
        row = self.visual_payloads.get(selected[0]) if selected else None
        return str(row.get("relative_path")) if row else None

    def _selected_visual_row(self) -> dict[str, Any] | None:
        selected = self.visual_tree.selection()
        return self.visual_payloads.get(selected[0]) if selected else None

    def _schedule_wireframe_load(self) -> None:
        self._wireframe_generation += 1
        generation = self._wireframe_generation
        self.after(260, lambda: self._wireframe_load(generation=generation))

    def _wireframe_load(self, generation: int | None = None) -> None:
        row = self._selected_visual_row()
        if row is None:
            return
        if generation is not None and generation != self._wireframe_generation:
            return
        self._wireframe_generation += 1
        active_generation = self._wireframe_generation
        self.visual_status.set(f"Decoding wireframe: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def done(payload: Any, error: Exception | None) -> None:
            if active_generation != self._wireframe_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Wireframe failed: {error}")
                _replace_text(self.visual_details, f"Wireframe decode failed:\n{error}")
                return
            self.visual_progress["value"] = 100.0
            self._wireframe_payload = payload
            self._wire_yaw, self._wire_pitch, self._wire_zoom = -0.55, 0.35, 1.0
            self._draw_wireframe()
            self.visual_status.set(f"Wireframe ready: {payload['vertex_count']:,} vertices / {payload['face_count']:,} faces")
            _replace_text(self.visual_details, _json_text({key: value for key, value in payload.items() if key not in {"vertices", "faces"}}))
        self._local_worker("wireframe", lambda: build_wireframe_payload(row["absolute_path"]), done)

    def _draw_wireframe(self) -> None:
        canvas = getattr(self, "visual_canvas", None)
        payload = self._wireframe_payload
        if canvas is None:
            return
        canvas.delete("all")
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        if not payload or not payload.get("vertices") or not payload.get("faces"):
            canvas.create_text(20, 20, anchor="nw", fill="#BFD7EA", text="Select an asset to decode its wireframe.")
            return
        cy, sy = math.cos(self._wire_yaw), math.sin(self._wire_yaw)
        cp, sp = math.cos(self._wire_pitch), math.sin(self._wire_pitch)
        projected: list[tuple[float, float, float]] = []
        for x, y, z in payload["vertices"]:
            rx = cy * x + sy * z
            rz = -sy * x + cy * z
            ry = cp * y - sp * rz
            depth = sp * y + cp * rz
            projected.append((rx, ry, depth))
        min_x = min(value[0] for value in projected)
        max_x = max(value[0] for value in projected)
        min_y = min(value[1] for value in projected)
        max_y = max(value[1] for value in projected)
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)
        scale = min((width - 50) / span_x, (height - 50) / span_y) * self._wire_zoom
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        screen = [((x - center_x) * scale + width / 2.0, height / 2.0 - (y - center_y) * scale, depth) for x, y, depth in projected]
        line_color = "#77C8FF"
        for a, b, c in payload["faces"]:
            points = (screen[a], screen[b], screen[c])
            canvas.create_line(points[0][0], points[0][1], points[1][0], points[1][1], points[2][0], points[2][1], points[0][0], points[0][1], fill=line_color, width=1)
        canvas.create_text(10, 10, anchor="nw", fill="#EAF4FF", text=f"{payload['vertex_count']:,} vertices | {payload['face_count']:,} faces | drag to rotate | wheel to zoom")

    def _wire_start_drag(self, event: tk.Event) -> None:
        self._wire_drag = (event.x, event.y)

    def _wire_drag_motion(self, event: tk.Event) -> None:
        if self._wire_drag is None:
            return
        old_x, old_y = self._wire_drag
        self._wire_yaw += (event.x - old_x) * 0.01
        self._wire_pitch += (event.y - old_y) * 0.01
        self._wire_drag = (event.x, event.y)
        self._draw_wireframe()

    def _wire_mousewheel(self, event: tk.Event) -> None:
        self._wire_zoom = max(0.15, min(8.0, self._wire_zoom * (1.12 if event.delta > 0 else 0.89)))
        self._draw_wireframe()

    def _refresh_audio_sequences(self) -> None:
        project = self.project
        self._audio_generation += 1
        generation = self._audio_generation
        self.sequence_tree.delete(*self.sequence_tree.get_children())
        self.program_tree.delete(*self.program_tree.get_children())
        self.sequence_payloads.clear()
        self.program_payloads.clear()
        if project is None:
            return
        self.audio_status.set("Loading sequence reports off the UI thread…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._audio_generation:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Music reports are not ready: {error}")
                _replace_text(self.audio_details, f"Music reports are not ready: {error}\nRun RUN ALL/SNDDATA preparation first.")
                return
            self.audio_progress["value"] = 100.0
            for index, row in enumerate(rows):
                iid = f"sequence_{index}"
                self.sequence_tree.insert("", "end", iid=iid, text=row["sequence_id"], values=(row["note_on_count"], row["mapping_status"]))
                self.sequence_payloads[iid] = row
            playable = sum(1 for row in rows if row.get("playable_sequence"))
            self.audio_status.set(f"Loaded {len(rows)} sequences; {playable} contain parsed note events. Select one to resolve its Program/sample bank.")
            first = next((iid for iid, row in self.sequence_payloads.items() if row.get("playable_sequence")), None)
            if first:
                self.sequence_tree.selection_set(first)
                self.sequence_tree.focus(first)
                self._refresh_audio_candidates()
        self._local_worker("audio-sequences", lambda: sequence_rows_fast(project), done)

    def _refresh_audio_candidates(self) -> None:
        project = self.project
        sequence = self._selected_sequence()
        self._candidate_generation += 1
        generation = self._candidate_generation
        self.program_tree.delete(*self.program_tree.get_children())
        self.program_payloads.clear()
        if project is None or sequence is None:
            return
        self.audio_status.set(f"Resolving Program and sample-bank candidates for {sequence['sequence_id']}…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._candidate_generation:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Resolver failed: {error}")
                _replace_text(self.audio_details, str(error))
                return
            self.audio_progress["value"] = 100.0
            for index, row in enumerate(model["candidate_details"]):
                iid = f"program_{index}"
                self.program_tree.insert("", "end", iid=iid, text=row["resource_id"], values=(row["program_count"], row["slot_count"], row["decoded_sample_wavs"]))
                self.program_payloads[iid] = row
            _replace_text(self.audio_details, _json_text(model))
            renderable = [iid for iid, row in self.program_payloads.items() if row.get("renderable_candidate")]
            selected = renderable[0] if renderable else (next(iter(self.program_payloads), None))
            if selected:
                self.program_tree.selection_set(selected)
                self.program_tree.focus(selected)
            self.audio_status.set(f"{model['candidate_count']} Program candidates; {model['renderable_candidate_count']} have a decoded sample bank.")
        self._local_worker("audio-candidates", lambda: sequence_resolver_view_model_fast(project, sequence["sequence_id"]), done)

    def _audio_render_play(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence()
        program = self._selected_program()
        if project is None:
            return
        if sequence is None or program is None:
            messagebox.showinfo("Music Mixer", "Select a playable sequence and candidate Program resource.")
            return
        self.audio_status.set("Rendering preview off the UI thread…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def work() -> Any:
            return render_sequence_preview_fast(
                project,
                sequence["sequence_id"],
                program["resource_id"],
                sample_bank_path=program.get("sample_bank_path"),
                master_gain=self.audio_gain.get(),
            )

        def done(result: Any, error: Exception | None) -> None:
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                if isinstance(error, NoRenderableMapping):
                    payload = {"status": "not_renderable", "missing": error.missing, "candidate": program}
                    _replace_text(self.audio_details, _json_text(payload))
                    self.audio_status.set("Preview not renderable: " + "; ".join(error.missing))
                else:
                    self.audio_status.set(f"Render failed: {error}")
                    messagebox.showerror("Render Preview", str(error))
                return
            try:
                self.playback.load(result["output_path"])
                self.playback.set_gain(min(1.0, self.audio_gain.get()))
                self.playback.play()
                self.audio_progress["value"] = 100.0
                suffix = " (experimental slot remap used)" if result.get("experimental_slot_remap") else ""
                self.audio_status.set(f"Playing {Path(result['output_path']).name}{suffix}")
                _replace_text(self.audio_details, _json_text(result))
            except Exception as exc:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Playback failed: {exc}")
                messagebox.showerror("Playback", str(exc))
        self._background("Render Music Preview", work, done)

    def _backup_done(self, label: str, result: Any, error: Exception | None) -> None:
        if error:
            messagebox.showerror(label, str(error))
        elif isinstance(result, dict) and result.get("backup_dir"):
            noun = "Server backup" if "Server" in label or "server" in label else "Memory card backup"
            messagebox.showinfo(label, f"{noun} saved at:\n{result['backup_dir']}")
        else:
            messagebox.showinfo(label, "Operation completed successfully.")
        self._refresh_backups()

    def _load_settings(self) -> None:
        project = self.project
        if project is None:
            return
        try:
            settings = load_project_settings(project)
        except Exception as exc:
            messagebox.showerror("Settings", str(exc))
            return
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
        self.setting_vars["default_workspace"].set(settings.workspace.default_workspace_root or str(default_project_folder().parent))
        self._apply_settings_runtime(settings)

    def _save_settings(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            current = load_project_settings(project)
            settings = FragmenterSettingsV1.from_dict(current.to_dict())
            settings.appearance.theme = self.setting_vars["theme"].get()
            settings.appearance.accent_color = self.setting_vars["accent"].get()
            settings.appearance.ui_scale = self.setting_vars["scale"].get()
            settings.playback.default_volume = self.setting_vars["volume"].get()
            settings.preview_3d.default_mode = self.setting_vars["preview"].get()
            settings.workspace.default_workspace_root = self.setting_vars["default_workspace"].get().strip()
            settings.workspace.reuse_valid_cache = self.setting_vars["cache"].get()
            settings.workspace.keep_diagnostics = self.setting_vars["diagnostics"].get()
            settings.advanced.enable_experimental_tools = self.setting_vars["experimental"].get()
            settings.celdra.enabled = self.setting_vars["celdra"].get()
            settings.celdra.checklist_commentary = self.setting_vars["celdra_commentary"].get()
            save_project_settings(project, settings)
            self._apply_settings_runtime(settings)
            messagebox.showinfo("Settings", "Project settings saved and applied.")
        except Exception as exc:
            messagebox.showerror("Settings", str(exc))

    def _apply_settings_runtime(self, settings: FragmenterSettingsV1) -> None:
        self._apply_runtime_palette(settings.appearance.theme, settings.appearance.accent_color, settings.appearance.ui_scale)
        self.audio_gain.set(settings.playback.default_volume)
        self.playback.set_gain(min(1.0, settings.playback.default_volume))
        self.playback.set_loop(settings.playback.loop_previews)

    def _apply_runtime_palette(self, theme: str, accent: str, scale: float) -> None:
        dark = theme == "dark"
        background = "#20252B" if dark else "#EEF2F6"
        field = "#151A1F" if dark else "#FFFFFF"
        foreground = "#F3F6F9" if dark else "#17212B"
        accent = str(accent or "#4F7CAC")
        self.configure(background=background)
        style = ttk.Style(self)
        style.configure("TFrame", background=background)
        style.configure("TLabelframe", background=background, foreground=foreground)
        style.configure("TLabelframe.Label", background=background, foreground=foreground)
        style.configure("TLabel", background=background, foreground=foreground)
        style.configure("TCheckbutton", background=background, foreground=foreground)
        style.configure("Treeview", background=field, fieldbackground=field, foreground=foreground, rowheight=24)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", accent)], foreground=[("selected", "#FFFFFF")])
        style.configure("Accent.Horizontal.TProgressbar", background=accent, troughcolor=field)
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        try:
            self.tk.call("tk", "scaling", self._base_tk_scaling * float(scale))
        except Exception:
            pass
        for widget in (getattr(self, "run_log", None), getattr(self, "visual_details", None), getattr(self, "audio_details", None)):
            if widget is not None:
                widget.configure(background=field, foreground=foreground, insertbackground=foreground)
        canvas = getattr(self, "visual_canvas", None)
        if canvas is not None:
            canvas.configure(background="#0C141C" if dark else "#101820")
        if hasattr(self, "header_frame"):
            self.header_frame.configure(bg=accent)
            self.header_title.configure(bg=accent)
            self.header_project.configure(bg=accent)
            self.header_task.configure(bg=accent)


def main() -> int:
    PublicFragmenterAppV2().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

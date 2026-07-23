#!/usr/bin/env python3
"""Third public GUI acceptance pass.

This layer keeps the validated v2 shell recoverable while integrating the first
real-user corrections from the second acceptance pass:

* evidence-based visual categories instead of forcing scene/weapon assets into
  ``character/body``;
* full focused DATA.BIN extraction through RUN ALL v2 plus an extraction audit;
* actual TEX/CLUT PNG display and a UV-mapped software textured snapshot;
* a simple BGM/voice/effect WAV library separate from the experimental SNDDATA
  sequence resolver.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from asset_classifier_v2 import CATEGORY_ORDER, category_sort_key, classify_visual_asset
from ccsf_textured_preview_v1 import build_textured_preview
from extraction_audit_v1 import audit_extraction
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v2 import (
    MAX_VISUAL_ROWS,
    PublicFragmenterAppV2,
    _candidate_path,
    discover_visual_assets,
)
from run_all_executor_v2 import execute_run_all_v2
from simple_audio_library_v1 import discover_audio_library

AUDIO_CATEGORIES = (
    "All",
    "BGM",
    "Voice",
    "FOOD stream",
    "Sound effect",
    "Decoded WAV",
    "SNDDATA decoded sample",
    "Experimental sequence preview",
    "Audio container",
    "SNDDATA source",
)


def _safe_folder(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return cleaned[:160] or "asset"


def _asset_metadata_by_path(project) -> dict[str, dict[str, Any]]:
    root = project.workspace_path("extracted_ccs")
    workspace = Path(project.workspace_dir)
    library_path = project.workspace_path("reports") / "asset_library.json"
    if not library_path.is_file():
        return {}
    try:
        payload = json.loads(library_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for asset in payload.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        candidates: list[Any] = [asset.get("preferred_file"), asset.get("relative_file"), asset.get("file")]
        candidates.extend(asset.get("duplicate_files") or [])
        for value in candidates:
            resolved = _candidate_path(root, workspace, value)
            if resolved is not None:
                rows[str(resolved.resolve())] = asset
    return rows


def discover_visual_assets_v3(project, query: str = "", category: str = "All", limit: int = MAX_VISUAL_ROWS) -> list[dict[str, Any]]:
    metadata = _asset_metadata_by_path(project)
    rows = discover_visual_assets(project, query=query, limit=limit)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        asset = metadata.get(str(Path(row["absolute_path"]).resolve()), {})
        classification = classify_visual_asset(
            name=str(row.get("name") or ""),
            relative_path=str(row.get("relative_path") or ""),
            existing_kind=str(asset.get("type") or row.get("kind") or ""),
            resource_counts=asset.get("resource_counts") if isinstance(asset.get("resource_counts"), dict) else None,
            identifiers=list(asset.get("identifiers") or []),
        )
        item = {
            **row,
            "legacy_kind": str(asset.get("type") or row.get("kind") or ""),
            "kind": classification["category"],
            "classification_confidence": classification["confidence"],
            "classification_evidence": classification["evidence"],
            "classification_source": classification["classification_source"],
            "resource_counts": dict(asset.get("resource_counts") or {}),
        }
        if category != "All" and item["kind"] != category:
            continue
        enriched.append(item)
    enriched.sort(
        key=lambda item: (
            category_sort_key(str(item["kind"])),
            str(item["name"]).lower(),
            str(item["relative_path"]).lower(),
        )
    )
    return enriched[: max(1, int(limit))]


class PublicFragmenterAppV3(PublicFragmenterAppV2):
    def __init__(self) -> None:
        self._simple_audio_generation = 0
        self._simple_audio_search_after: str | None = None
        self._simple_audio_rows: dict[str, dict[str, Any]] = {}
        self._texture_photo: tk.PhotoImage | None = None
        super().__init__()

    def _build_visual(self, parent: ttk.Frame) -> None:
        super()._build_visual(parent)
        extras = ttk.Frame(parent)
        extras.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(extras, text="Category").pack(side="left")
        self.visual_category = tk.StringVar(value="All")
        self.visual_category_combo = ttk.Combobox(
            extras,
            textvariable=self.visual_category,
            values=("All", *CATEGORY_ORDER),
            state="readonly",
            width=34,
        )
        self.visual_category_combo.pack(side="left", padx=(6, 12))
        self.visual_category_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_visual_assets())
        ttk.Button(extras, text="Wireframe", command=self._wireframe_load).pack(side="left")
        ttk.Button(extras, text="Textured Snapshot", command=self._visual_textured_snapshot, style="Accent.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(extras, text="Audit Extraction", command=self._visual_audit_extraction).pack(side="left", padx=(6, 0))
        ttk.Button(extras, text="Open Texture Output", command=self._open_texture_output).pack(side="left", padx=(6, 0))
        ttk.Label(
            extras,
            text="Offline-game filename ranges are shown as confidence-labelled hints; Fragment-specific unknowns remain unknown.",
        ).pack(side="right")

    def _build_audio(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")
        library = ttk.Frame(notebook, padding=6)
        mixer = ttk.Frame(notebook, padding=6)
        notebook.add(library, text="Audio Library")
        notebook.add(mixer, text="SNDDATA Mixer (experimental)")
        super()._build_audio(mixer)
        self._build_simple_audio_library(library)

    def _build_simple_audio_library(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(controls, text="Search").pack(side="left")
        self.simple_audio_query = tk.StringVar()
        ttk.Entry(controls, textvariable=self.simple_audio_query, width=32).pack(side="left", padx=(6, 10))
        ttk.Label(controls, text="Category").pack(side="left")
        self.simple_audio_category = tk.StringVar(value="All")
        category = ttk.Combobox(controls, textvariable=self.simple_audio_category, values=AUDIO_CATEGORIES, state="readonly", width=28)
        category.pack(side="left", padx=(6, 10))
        category.bind("<<ComboboxSelected>>", lambda _event: self._refresh_simple_audio())
        ttk.Button(controls, text="Refresh", command=self._refresh_simple_audio).pack(side="left")
        ttk.Button(controls, text="Play", command=self._play_simple_audio, style="Accent.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Stop", command=self._audio_stop).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Open Folder", command=self._open_simple_audio_folder).pack(side="left", padx=(6, 0))
        self.simple_audio_status = tk.StringVar(value="No project loaded")
        ttk.Label(controls, textvariable=self.simple_audio_status).pack(side="right")

        self.simple_audio_tree = ttk.Treeview(
            parent,
            columns=("category", "duration", "status", "size", "path"),
            show="tree headings",
        )
        self.simple_audio_tree.heading("#0", text="Audio")
        for key, label, width in (
            ("category", "Category", 180),
            ("duration", "Duration", 90),
            ("status", "Status", 110),
            ("size", "Size", 100),
            ("path", "Project-relative path", 520),
        ):
            self.simple_audio_tree.heading(key, text=label)
            self.simple_audio_tree.column(key, width=width, stretch=key == "path")
        self.simple_audio_tree.column("#0", width=240)
        self.simple_audio_tree.grid(row=1, column=0, sticky="nsew")
        self.simple_audio_tree.bind("<Double-1>", lambda _event: self._play_simple_audio())
        self.simple_audio_query.trace_add("write", lambda *_: self._debounce_simple_audio())

    def _refresh_all(self) -> None:
        super()._refresh_all()
        self._refresh_simple_audio()

    def _refresh_run_plan(self) -> None:
        super()._refresh_run_plan()
        if self.project is None or self.run_tree.exists("extraction_audit"):
            return
        children = list(self.run_tree.get_children())
        try:
            index = children.index("asset_library") + 1
        except ValueError:
            index = len(children)
        self.run_tree.insert(
            "",
            index,
            iid="extraction_audit",
            text="Audit CCSF Extraction",
            values=("pending", "Verify DATA/DATA.BIN was fully scanned and indexed outputs exist."),
        )
        row_index = len(self._stage_order)
        ttk.Label(self.stage_progress_frame, text="Audit CCSF Extraction").grid(row=row_index, column=0, sticky="w", padx=(0, 6), pady=2)
        bar = ttk.Progressbar(self.stage_progress_frame, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar", length=180)
        bar.grid(row=row_index, column=1, sticky="ew", pady=2)
        self._stage_bars["extraction_audit"] = bar
        self._stage_values["extraction_audit"] = 0.0
        self._stage_order.insert(index, "extraction_audit")

    def _run_all(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        self.cancel_event = threading.Event()
        self._set_busy(True, "RUN ALL")
        self.run_log.delete("1.0", "end")
        self.overall_progress["value"] = 0.0
        self.overall_progress_label.set("Overall progress: starting")

        def callback(event: dict[str, Any]) -> None:
            self.events.put({"kind": "run_event", "event": event})

        def work() -> Any:
            return execute_run_all_v2(project, callback=callback, cancel_event=self.cancel_event)

        self._background("RUN ALL", work, self._run_all_done, already_busy=True)

    def _refresh_visual_assets(self) -> None:
        project = self.project
        self._visual_generation += 1
        generation = self._visual_generation
        self.visual_tree.delete(*self.visual_tree.get_children())
        self.visual_payloads.clear()
        if project is None:
            return
        self.visual_status.set("Classifying extracted CCSF library…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)
        query = self.visual_search.get()
        category = self.visual_category.get() if hasattr(self, "visual_category") else "All"

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._visual_generation:
                return
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            self.visual_progress["value"] = 100.0 if not error else 0.0
            if error:
                self.visual_status.set(f"Asset classification failed: {error}")
                return
            for index, row in enumerate(rows):
                iid = f"asset_{index}"
                confidence = str(row.get("classification_confidence") or "")
                kind = f"{row['kind']} ({confidence})" if confidence else row["kind"]
                self.visual_tree.insert("", "end", iid=iid, text=row["name"], values=(kind, f"{row['size']:,}", row["relative_path"]))
                self.visual_payloads[iid] = row
            self.visual_status.set(f"Showing {len(rows):,} assets in {category}. Categories are evidence-labelled, not assumed proof.")

        self._local_worker("visual-classification", lambda: discover_visual_assets_v3(project, query, category), done)

    def _wireframe_load(self, generation: int | None = None) -> None:
        self._texture_photo = None
        super()._wireframe_load(generation=generation)

    def _visual_textures(self) -> None:
        self._visual_textured_snapshot()

    def _visual_textured_snapshot(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None:
            return
        if row is None:
            messagebox.showinfo("Textured Snapshot", "Select an extracted CCSF asset first.")
            return
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"]))
        self.visual_status.set(f"Extracting and applying textures: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)

        def work() -> Any:
            return build_textured_preview(row["absolute_path"], output)

        def done(result: Any, error: Exception | None) -> None:
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Textured preview failed: {error}")
                _replace_text(self.visual_details, f"Textured preview failed:\n{error}")
                return
            self.visual_progress["value"] = 100.0
            _replace_text(self.visual_details, _json_text(result))
            display = result.get("display_path")
            if display:
                try:
                    self._show_png_on_visual_canvas(Path(display))
                except Exception as exc:
                    self.visual_status.set(f"Textures extracted, but PNG display failed: {exc}")
                    return
            summary = result.get("summary") or {}
            self.visual_status.set(
                f"Texture result: {summary.get('png_exported', 0)} PNG; "
                f"{summary.get('mapped_faces', 0)} mapped faces; {summary.get('unmapped_faces', 0)} unmapped faces."
            )

        self._local_worker("textured-preview", work, done)

    def _show_png_on_visual_canvas(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        photo = tk.PhotoImage(file=str(path))
        canvas_width = max(1, self.visual_canvas.winfo_width() - 20)
        canvas_height = max(1, self.visual_canvas.winfo_height() - 20)
        factor = max(1, math.ceil(max(photo.width() / canvas_width, photo.height() / canvas_height)))
        if factor > 1:
            photo = photo.subsample(factor, factor)
        self._texture_photo = photo
        self.visual_canvas.delete("all")
        self.visual_canvas.create_image(
            self.visual_canvas.winfo_width() / 2,
            self.visual_canvas.winfo_height() / 2,
            image=photo,
            anchor="center",
        )
        self.visual_canvas.create_text(10, 10, anchor="nw", fill="#EAF4FF", text=f"{path.name} | extracted TEX/CLUT preview")

    def _visual_audit_extraction(self) -> None:
        project = self._require_project()
        if project is None:
            return
        self.visual_status.set("Auditing CCSF extraction completeness…")

        def done(result: Any, error: Exception | None) -> None:
            if error:
                self.visual_status.set(f"Extraction audit failed: {error}")
                _replace_text(self.visual_details, str(error))
                return
            _replace_text(self.visual_details, _json_text(result))
            self.visual_status.set(f"Extraction audit: {result.get('status')} — {result.get('report_path')}")

        self._local_worker("extraction-audit", lambda: audit_extraction(project), done)

    def _open_texture_output(self) -> None:
        project = self._require_project()
        if project is None:
            return
        folder = project.workspace_path("texture_outputs")
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # type: ignore[attr-defined]

    def _debounce_simple_audio(self) -> None:
        if self._simple_audio_search_after is not None:
            try:
                self.after_cancel(self._simple_audio_search_after)
            except tk.TclError:
                pass
        self._simple_audio_search_after = self.after(220, self._refresh_simple_audio)

    def _refresh_simple_audio(self) -> None:
        project = self.project
        if not hasattr(self, "simple_audio_tree"):
            return
        self._simple_audio_generation += 1
        generation = self._simple_audio_generation
        self.simple_audio_tree.delete(*self.simple_audio_tree.get_children())
        self._simple_audio_rows.clear()
        if project is None:
            self.simple_audio_status.set("No project loaded")
            return
        query = self.simple_audio_query.get()
        category = self.simple_audio_category.get()
        self.simple_audio_status.set("Scanning decoded audio off the UI thread…")

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._simple_audio_generation:
                return
            if error:
                self.simple_audio_status.set(f"Audio scan failed: {error}")
                return
            for index, row in enumerate(model["items"]):
                iid = f"simple_audio_{index}"
                duration = f"{float(row.get('duration') or 0):.2f}s" if row.get("playable") else "—"
                self.simple_audio_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=row["name"],
                    values=(row["category"], duration, row["status"], f"{row['size']:,}", row["relative_path"]),
                )
                self._simple_audio_rows[iid] = row
            summary = model["summary"]
            self.simple_audio_status.set(
                f"{summary['playable_wavs']} playable WAVs; BGM {summary['bgm_wavs']}; "
                f"voice {summary['voice_wavs']}; effects {summary['effect_wavs']}; SNDDATA samples {summary['snddata_samples']}."
            )

        self._local_worker("simple-audio-library", lambda: discover_audio_library(project, query=query, category=category), done)

    def _selected_simple_audio(self) -> dict[str, Any] | None:
        selected = self.simple_audio_tree.selection()
        return self._simple_audio_rows.get(selected[0]) if selected else None

    def _play_simple_audio(self) -> None:
        row = self._selected_simple_audio()
        if row is None:
            messagebox.showinfo("Audio Library", "Select a decoded WAV first.")
            return
        if not row.get("playable"):
            messagebox.showinfo("Audio Library", f"{row['name']} is a source container, not a decoded WAV yet.")
            return
        try:
            self.playback.load(row["path"])
            self.playback.set_gain(min(1.0, self.audio_gain.get()))
            self.playback.play()
            self.simple_audio_status.set(f"Playing {row['category']}: {row['name']}")
        except Exception as exc:
            messagebox.showerror("Audio Library", str(exc))

    def _open_simple_audio_folder(self) -> None:
        row = self._selected_simple_audio()
        project = self._require_project()
        if project is None:
            return
        folder = Path(row["path"]).parent if row else project.workspace_path("media_pipeline")
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # type: ignore[attr-defined]


def main() -> int:
    PublicFragmenterAppV3().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

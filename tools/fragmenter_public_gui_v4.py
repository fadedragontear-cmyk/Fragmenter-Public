#!/usr/bin/env python3
"""Fourth public GUI acceptance pass: posed 3D and canonical project sound."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import fragmenter_public_gui_v2 as gui_v2
from asset_classifier_v2 import category_sort_key
from ccsf_textured_scene_v3 import export_scene_textures, load_textured_scene, render_textured_scene
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v3 import PublicFragmenterAppV3, _safe_folder, discover_visual_assets_v3
from project_sound_v1 import analyze_or_extract_sound_item, build_project_sound_library, sound_root
from run_all_executor_v3 import build_run_all_actions_v3, execute_run_all_v3
from snddata_music_system_v3 import MusicSystemError, render_sequence, sequence_rows, sequence_view_model

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEFAULT_PROJECT = REPOSITORY_ROOT / "project"


def default_project_folder() -> Path:
    return LOCAL_DEFAULT_PROJECT


# V2 owns Setup and Settings path resolution and resolves this global at runtime.
# Patch the compatibility module before any App instance is constructed.
gui_v2.default_project_folder = default_project_folder


class PublicFragmenterAppV4(PublicFragmenterAppV3):
    def __init__(self) -> None:
        self._preview_mode = "wireframe"
        self._textured_scene = None
        self._textured_scene_row: dict[str, Any] | None = None
        self._textured_render_after: str | None = None
        self._textured_render_generation = 0
        self._sound_category_combo: ttk.Combobox | None = None
        super().__init__()
        if self.project is None:
            self.setup_vars["workspace"].set(str(LOCAL_DEFAULT_PROJECT))

    def _build_visual(self, parent: ttk.Frame) -> None:
        super()._build_visual(parent)
        try:
            for child in parent.winfo_children():
                if isinstance(child, ttk.Frame):
                    for widget in child.winfo_children():
                        if isinstance(widget, ttk.Button) and str(widget.cget("text")) == "Textured Snapshot":
                            widget.configure(text="Textured Preview", command=self._visual_textured_snapshot)
        except tk.TclError:
            pass

    def _build_simple_audio_library(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(controls, text="Search").pack(side="left")
        self.simple_audio_query = tk.StringVar()
        ttk.Entry(controls, textvariable=self.simple_audio_query, width=30).pack(side="left", padx=(6, 10))
        ttk.Label(controls, text="Category").pack(side="left")
        self.simple_audio_category = tk.StringVar(value="All")
        self._sound_category_combo = ttk.Combobox(controls, textvariable=self.simple_audio_category, values=("All",), state="readonly", width=24)
        self._sound_category_combo.pack(side="left", padx=(6, 10))
        self._sound_category_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_simple_audio())
        ttk.Button(controls, text="Refresh", command=self._refresh_simple_audio).pack(side="left")
        self.simple_audio_primary = ttk.Button(controls, text="Primary Action", command=self._simple_audio_primary_action, style="Accent.TButton")
        self.simple_audio_primary.pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Stop", command=self._audio_stop).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Open Folder", command=self._open_simple_audio_folder).pack(side="left", padx=(6, 0))
        self.simple_audio_status = tk.StringVar(value="No project loaded")
        ttk.Label(controls, textvariable=self.simple_audio_status).pack(side="right")

        paned = ttk.Panedwindow(parent, orient="vertical")
        paned.grid(row=1, column=0, sticky="nsew")
        tree_frame = ttk.Frame(paned)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.simple_audio_tree = ttk.Treeview(tree_frame, columns=("kind", "category", "duration", "action", "size", "path"), show="tree headings")
        self.simple_audio_tree.heading("#0", text="Audio")
        for key, label, width in (("kind", "Kind", 80), ("category", "Category", 150), ("duration", "Duration", 80), ("action", "Action", 130), ("size", "Size", 90), ("path", "project/sound relative path", 480)):
            self.simple_audio_tree.heading(key, text=label)
            self.simple_audio_tree.column(key, width=width, stretch=key == "path")
        self.simple_audio_tree.column("#0", width=230)
        self.simple_audio_tree.grid(row=0, column=0, sticky="nsew")
        self.simple_audio_tree.bind("<<TreeviewSelect>>", lambda _event: self._sound_selection_changed())
        self.simple_audio_tree.bind("<Double-1>", lambda _event: self._simple_audio_primary_action())
        paned.add(tree_frame, weight=4)
        details_frame = ttk.Frame(paned)
        details_frame.rowconfigure(0, weight=1)
        details_frame.columnconfigure(0, weight=1)
        self.simple_audio_details = tk.Text(details_frame, height=7, wrap="word")
        self.simple_audio_details.grid(row=0, column=0, sticky="nsew")
        paned.add(details_frame, weight=1)
        self.simple_audio_query.trace_add("write", lambda *_: self._debounce_simple_audio())

    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        for widget in parent.winfo_children():
            self._retitle_mapping_buttons(widget)
        self.sequence_tree.heading("mapping", text="Program routing")
        self.program_tree.heading("slots", text="Required samples")
        self.program_tree.heading("samples", text="Decoded samples")

    def _retitle_mapping_buttons(self, widget: tk.Misc) -> None:
        try:
            if isinstance(widget, ttk.Button) and str(widget.cget("text")) == "Use This Mapping":
                widget.configure(text="Use Selected Candidate", command=self._audio_use_mapping)
            for child in widget.winfo_children():
                self._retitle_mapping_buttons(child)
        except tk.TclError:
            return

    def _refresh_run_plan(self) -> None:
        if not hasattr(self, "run_tree"):
            return
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
            actions = build_run_all_actions_v3(project)
        except Exception as exc:
            self._append_log(str(exc))
            return
        descriptions = {
            "ccsf_extract": "Full focused CCSF extraction. First run can take a long time.",
            "extraction_audit": "Verify DATA/DATA.BIN coverage and indexed output files.",
            "sound_extract": "Extract every ISO sound/* file plus SNDDATA and NETGUI EFF banks into project/sound/source.",
            "sound_decode": "Decode validated project sound containers and streams into project/sound/decoded.",
            "snddata_v3": "Parse SCEIMidi Program Change state and rank SCEIProg/sample-resource evidence.",
        }
        for row_index, action in enumerate(actions):
            description = descriptions.get(action.key, action.label)
            self.run_tree.insert("", "end", iid=action.key, text=action.label, values=("pending", description))
            ttk.Label(self.stage_progress_frame, text=action.label).grid(row=row_index, column=0, sticky="w", padx=(0, 6), pady=2)
            bar = ttk.Progressbar(self.stage_progress_frame, maximum=100.0, mode="determinate", style="Accent.Horizontal.TProgressbar", length=180)
            bar.grid(row=row_index, column=1, sticky="ew", pady=2)
            self._stage_bars[action.key] = bar
            self._stage_values[action.key] = 0.0
            self._stage_order.append(action.key)
        self.overall_progress["value"] = 0.0
        self.overall_progress_label.set("Overall progress: ready")

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
        self._background("RUN ALL", lambda: execute_run_all_v3(project, callback=callback, cancel_event=self.cancel_event), self._run_all_done, already_busy=True)

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        super()._handle_run_event(event)
        if event.get("kind") == "progress":
            stage = str(event.get("stage") or "")
            percent = event.get("percent")
            if isinstance(percent, (int, float)):
                self._set_stage_progress(stage, float(percent), "running")
            detail = str(event.get("detail") or "")
            if detail:
                self.current_task_label.set(detail)

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
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(str(row["kind"]), []).append(row)
            asset_index = 0
            for group_index, kind in enumerate(sorted(grouped, key=category_sort_key)):
                category_iid = f"category_{group_index}"
                children = grouped[kind]
                self.visual_tree.insert("", "end", iid=category_iid, text=kind, values=(f"{len(children):,} assets", "", ""), open=bool(query.strip()) or category != "All")
                for row in children:
                    iid = f"asset_{asset_index}"
                    asset_index += 1
                    confidence = str(row.get("classification_confidence") or "")
                    self.visual_tree.insert(category_iid, "end", iid=iid, text=row["name"], values=(confidence, f"{row['size']:,}", row["relative_path"]))
                    self.visual_payloads[iid] = row
            self.visual_status.set(f"Showing {len(rows):,} assets in {len(grouped):,} collapsible categories. Search is applied before grouping.")

        self._local_worker("visual-classification-v4", lambda: discover_visual_assets_v3(project, query, category), done)

    def _wireframe_load(self, generation: int | None = None) -> None:
        self._preview_mode = "wireframe"
        self._textured_scene = None
        self._textured_scene_row = None
        self._textured_render_generation += 1
        super()._wireframe_load(generation=generation)

    def _draw_wireframe(self) -> None:
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render()
            return
        super()._draw_wireframe()

    def _visual_textures(self) -> None:
        self._visual_textured_snapshot()

    def _visual_textured_snapshot(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None:
            return
        if row is None:
            messagebox.showinfo("Textured Preview", "Select an extracted CCSF asset first.")
            return
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"]))
        self.visual_status.set(f"Decoding model, pose, materials and textures: {row['name']}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)
        active_row = dict(row)

        def work() -> Any:
            scene = load_textured_scene(row["absolute_path"], frame=0)
            textures = export_scene_textures(scene, output / "textures")
            render = render_textured_scene(scene, output / "textured_preview.png", yaw=self._wire_yaw, pitch=self._wire_pitch, zoom=self._wire_zoom, width=max(320, self.visual_canvas.winfo_width()), height=max(240, self.visual_canvas.winfo_height()))
            return {"scene": scene, "textures": textures, "render": render}

        def done(result: Any, error: Exception | None) -> None:
            self.visual_progress.stop()
            self.visual_progress.configure(mode="determinate")
            if error:
                self.visual_progress["value"] = 0.0
                self.visual_status.set(f"Textured preview failed: {error}")
                _replace_text(self.visual_details, f"Textured preview failed:\n{error}")
                return
            self.visual_progress["value"] = 100.0
            self._preview_mode = "textured"
            self._textured_scene = result["scene"]
            self._textured_scene_row = active_row
            self._show_png_on_visual_canvas(Path(result["render"]["output_path"]))
            summary = dict(result["scene"].summary)
            _replace_text(self.visual_details, _json_text({"scene": summary, "texture_export": result["textures"], "render": {key: value for key, value in result["render"].items() if key != "scene_summary"}}))
            self.visual_status.set(f"Textured scene: {summary.get('textured_triangles', 0):,} textured / {summary.get('unresolved_triangles', 0):,} unresolved triangles; pose {summary.get('selected_animation') or 'none'} frame {summary.get('frame', 0)}.")

        self._local_worker("textured-scene-v4", work, done)

    def _schedule_textured_render(self) -> None:
        if self._textured_scene is None or self._textured_scene_row is None:
            return
        if self._textured_render_after is not None:
            try:
                self.after_cancel(self._textured_render_after)
            except tk.TclError:
                pass
        self._textured_render_after = self.after(90, self._start_textured_render)

    def _start_textured_render(self) -> None:
        scene = self._textured_scene
        row = self._textured_scene_row
        project = self.project
        if scene is None or row is None or project is None or self._preview_mode != "textured":
            return
        self._textured_render_generation += 1
        generation = self._textured_render_generation
        yaw, pitch, zoom = self._wire_yaw, self._wire_pitch, self._wire_zoom
        width, height = max(320, self.visual_canvas.winfo_width()), max(240, self.visual_canvas.winfo_height())
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview.png"
        self.visual_status.set("Rerendering textured view…")

        def done(result: Any, error: Exception | None) -> None:
            if generation != self._textured_render_generation or self._preview_mode != "textured":
                return
            if error:
                self.visual_status.set(f"Textured rerender failed: {error}")
                return
            try:
                self._show_png_on_visual_canvas(Path(result["output_path"]))
                self.visual_status.set(f"Textured view | yaw {yaw:.2f} pitch {pitch:.2f} zoom {zoom:.2f} | {result['textured_faces']:,} textured / {result['unresolved_faces']:,} unresolved")
            except Exception as exc:
                self.visual_status.set(f"Textured PNG display failed: {exc}")

        self._local_worker("textured-rerender-v4", lambda: render_textured_scene(scene, output, yaw=yaw, pitch=pitch, zoom=zoom, width=width, height=height), done)

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
        self.simple_audio_status.set("Reading active project/sound only…")

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._simple_audio_generation:
                return
            if error:
                self.simple_audio_status.set(f"Sound library failed: {error}")
                return
            categories = ("All", *model.get("categories", []))
            if self._sound_category_combo is not None:
                self._sound_category_combo.configure(values=categories)
            for index, row in enumerate(model["items"]):
                iid = f"simple_audio_{index}"
                wav = row.get("wav") or {}
                duration = f"{float(wav.get('duration') or 0):.2f}s" if row.get("playable") else "—"
                self.simple_audio_tree.insert("", "end", iid=iid, text=row["name"], values=(row["kind"], row["category"], duration, row["primary_action"], f"{row['size']:,}", row["relative_path"]))
                self._simple_audio_rows[iid] = row
            summary = model["summary"]
            self.simple_audio_status.set(f"project/sound: {summary['source_files']} source files; {summary['playable_wavs']} playable WAVs; {summary['supported_containers']} actionable containers.")

        self._local_worker("project-sound-library", lambda: build_project_sound_library(project, query=query, category=category), done)

    def _sound_selection_changed(self) -> None:
        row = self._selected_simple_audio()
        if row is None:
            self.simple_audio_primary.configure(text="Primary Action")
            return
        self.simple_audio_primary.configure(text=row["primary_action"])
        _replace_text(self.simple_audio_details, _json_text(row))

    def _simple_audio_primary_action(self) -> None:
        project = self._require_project()
        row = self._selected_simple_audio()
        if project is None:
            return
        if row is None:
            messagebox.showinfo("Audio Library", "Select an audio item first.")
            return
        if row.get("playable"):
            try:
                self.playback.load(row["path"])
                self.playback.set_gain(min(1.0, self.audio_gain.get()))
                self.playback.play()
                self.simple_audio_status.set(f"Playing {row['category']}: {row['name']}")
            except Exception as exc:
                messagebox.showerror("Audio Library", str(exc))
            return
        if not row.get("supported_container"):
            _replace_text(self.simple_audio_details, _json_text(row))
            self.simple_audio_status.set(f"No verified decoder for {row['name']}; signature and source path shown below.")
            return
        self.simple_audio_status.set(f"Analyzing / extracting {row['relative_path']}…")
        def done(result: Any, error: Exception | None) -> None:
            if error:
                self.simple_audio_status.set(f"Audio action failed: {error}")
                _replace_text(self.simple_audio_details, str(error))
                return
            _replace_text(self.simple_audio_details, _json_text(result))
            self.simple_audio_status.set(f"Audio action complete: {row['name']}")
            self._refresh_simple_audio()
        self._local_worker("sound-primary-action", lambda: analyze_or_extract_sound_item(project, row["path"]), done)

    def _play_simple_audio(self) -> None:
        self._simple_audio_primary_action()

    def _open_simple_audio_folder(self) -> None:
        row = self._selected_simple_audio()
        project = self._require_project()
        if project is None:
            return
        folder = Path(row["path"]).parent if row else sound_root(project)
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # type: ignore[attr-defined]

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
        self.audio_status.set("Parsing SCEIMidi Program Change state off the UI thread…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._audio_generation:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Music system is not ready: {error}")
                _replace_text(self.audio_details, str(error))
                return
            self.audio_progress["value"] = 100.0
            for index, row in enumerate(rows):
                iid = f"sequence_{index}"
                routing = f"{row['program_change_count']} changes / {row['routing_status']}"
                self.sequence_tree.insert("", "end", iid=iid, text=row["sequence_id"], values=(row["note_on_count"], routing))
                self.sequence_payloads[iid] = row
            routed = sum(1 for row in rows if row.get("program_change_count"))
            self.audio_status.set(f"Loaded {len(rows)} sequence resources; {routed} contain Program Change routing. No sample-remap fallback is enabled.")
            first = next(iter(self.sequence_payloads), None)
            if first:
                self.sequence_tree.selection_set(first)
                self.sequence_tree.focus(first)
                self._refresh_audio_candidates()
        self._local_worker("music-system-v3-sequences", lambda: sequence_rows(project), done)

    def _refresh_audio_candidates(self) -> None:
        project = self.project
        sequence = self._selected_sequence()
        self._candidate_generation += 1
        generation = self._candidate_generation
        self.program_tree.delete(*self.program_tree.get_children())
        self.program_payloads.clear()
        if project is None or sequence is None:
            return
        self.audio_status.set(f"Ranking Program resources for {sequence['sequence_id']} using Program indexes {sequence.get('program_indexes')}…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._candidate_generation:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Program resolver failed: {error}")
                _replace_text(self.audio_details, str(error))
                return
            self.audio_progress["value"] = 100.0
            for index, row in enumerate(model["candidates"]):
                iid = f"program_{index}"
                self.program_tree.insert("", "end", iid=iid, text=row["resource_id"], values=(row["program_count"], len(row["required_sample_ids"]), row["decoded_sample_count"]))
                self.program_payloads[iid] = row
            _replace_text(self.audio_details, _json_text(model))
            best = next((iid for iid, row in self.program_payloads.items() if row.get("status") == "renderable"), next(iter(self.program_payloads), None))
            if best:
                self.program_tree.selection_set(best)
                self.program_tree.focus(best)
            renderable = sum(1 for row in model["candidates"] if row.get("status") == "renderable")
            self.audio_status.set(f"{len(model['candidates'])} Program-resource candidates; {renderable} fully cover parsed Program indexes and slot sample IDs.")
        self._local_worker("music-system-v3-candidates", lambda: sequence_view_model(project, sequence["sequence_id"]), done)

    def _audio_render_play(self) -> None:
        project = self._require_project()
        sequence = self._selected_sequence()
        candidate = self._selected_program()
        if project is None:
            return
        if sequence is None:
            messagebox.showinfo("Music Mixer", "Select a sequence first.")
            return
        resource_offset = int(candidate["resource_offset"]) if candidate is not None else None
        self.audio_status.set("Routing Program Change events and rendering decoded samples…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(result: Any, error: Exception | None) -> None:
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                if isinstance(error, MusicSystemError):
                    payload = {"status": "not_renderable", "error": str(error), "missing": error.missing, "sequence": sequence, "candidate": candidate, "sample_remap_fallback": False}
                    _replace_text(self.audio_details, _json_text(payload))
                    self.audio_status.set(str(error))
                else:
                    messagebox.showerror("Music Mixer", str(error))
                return
            self.audio_progress["value"] = 100.0
            try:
                self.playback.load(result["output_path"])
                self.playback.set_gain(min(1.0, self.audio_gain.get()))
                self.playback.play()
                _replace_text(self.audio_details, _json_text(result))
                self.audio_status.set(f"Playing Program-Change routed preview: {Path(result['output_path']).name}")
            except Exception as exc:
                messagebox.showerror("Playback", str(exc))
        self._local_worker("music-system-v3-render", lambda: render_sequence(project, sequence["sequence_id"], program_resource_offset=resource_offset, master_gain=self.audio_gain.get()), done)

    def _audio_use_mapping(self) -> None:
        sequence = self._selected_sequence()
        candidate = self._selected_program()
        if sequence is None or candidate is None:
            messagebox.showinfo("Music Mixer", "Select a sequence and Program-resource candidate.")
            return
        _replace_text(self.audio_details, _json_text({"selection": {"sequence_id": sequence["sequence_id"], "program_resource": candidate["resource_id"]}, "note": "Selected for this audition only. SNDDATA is not modified and no sample IDs are remapped.", "candidate_evidence": candidate}))
        self.audio_status.set(f"Audition candidate selected: {candidate['resource_id']}")


def main() -> int:
    PublicFragmenterAppV4().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

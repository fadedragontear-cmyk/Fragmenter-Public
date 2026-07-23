#!/usr/bin/env python3
"""Fifth public GUI acceptance pass: internal CCSF tree, animation and fast mixer catalog."""
from __future__ import annotations

import math
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from ccsf_asset_tree_v1 import inspect_ccsf_contents
from ccsf_textured_scene_v4 import (
    export_scene_textures,
    load_posed_wireframe_payload,
    load_textured_scene,
    render_textured_scene,
)
from fragmenter_public_gui import _json_text, _replace_text
from fragmenter_public_gui_v4 import PublicFragmenterAppV4, _safe_folder
from project_sound_v2 import analyze_or_extract_sound_item, build_project_sound_library, sound_root
from run_all_executor_v4 import build_run_all_actions_v4, execute_run_all_v4
from snddata_music_system_v4 import MusicSystemError, clear_runtime_cache, render_sequence, sequence_rows, sequence_view_model


class PublicFragmenterAppV5(PublicFragmenterAppV4):
    def __init__(self) -> None:
        self._ccsf_tree_generation = 0
        self._ccsf_tree_payloads: dict[str, dict[str, Any]] = {}
        self._ccsf_contents_model: dict[str, Any] | None = None
        self._animation_rows_by_name: dict[str, dict[str, Any]] = {}
        self._animation_playing = False
        self._animation_tick_after: str | None = None
        self._animation_frame_job = False
        self._animation_pending_frame: int | None = None
        self._animation_frame_generation = 0
        self._textured_render_busy = False
        self._textured_render_pending = False
        super().__init__()

    # ------------------------------------------------------------------
    # Visual browser / internal CCSF contents
    # ------------------------------------------------------------------
    def _build_visual(self, parent: ttk.Frame) -> None:
        super()._build_visual(parent)

        details_parent = self.visual_details.master
        self.visual_details.grid_remove()
        details_notebook = ttk.Notebook(details_parent)
        details_notebook.grid(row=0, column=0, sticky="nsew")
        details_tab = ttk.Frame(details_notebook)
        contents_tab = ttk.Frame(details_notebook)
        details_notebook.add(details_tab, text="Details")
        details_notebook.add(contents_tab, text="CCSF Contents")
        details_tab.rowconfigure(0, weight=1)
        details_tab.columnconfigure(0, weight=1)
        self.visual_details = tk.Text(details_tab, height=10, wrap="word")
        self.visual_details.grid(row=0, column=0, sticky="nsew")

        contents_tab.rowconfigure(0, weight=1)
        contents_tab.columnconfigure(0, weight=1)
        self.ccsf_contents_tree = ttk.Treeview(contents_tab, columns=("kind",), show="tree headings")
        self.ccsf_contents_tree.heading("#0", text="CCSF file contents")
        self.ccsf_contents_tree.heading("kind", text="Kind")
        self.ccsf_contents_tree.column("#0", width=620, stretch=True)
        self.ccsf_contents_tree.column("kind", width=160, stretch=False)
        contents_scroll = ttk.Scrollbar(contents_tab, orient="vertical", command=self.ccsf_contents_tree.yview)
        self.ccsf_contents_tree.configure(yscrollcommand=contents_scroll.set)
        self.ccsf_contents_tree.grid(row=0, column=0, sticky="nsew")
        contents_scroll.grid(row=0, column=1, sticky="ns")
        self.ccsf_contents_tree.bind("<<TreeviewSelect>>", lambda _event: self._ccsf_contents_selected())

        animation_bar = ttk.LabelFrame(parent, text="Animation / pose preview", padding=5)
        animation_bar.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(animation_bar, text="Animation").pack(side="left")
        self.animation_name = tk.StringVar(value="")
        self.animation_combo = ttk.Combobox(animation_bar, textvariable=self.animation_name, values=(), state="readonly", width=28)
        self.animation_combo.pack(side="left", padx=(6, 10))
        self.animation_combo.bind("<<ComboboxSelected>>", lambda _event: self._animation_selected())
        ttk.Label(animation_bar, text="Frame").pack(side="left")
        self.animation_frame = tk.IntVar(value=0)
        self.animation_frame_scale = ttk.Scale(animation_bar, from_=0, to=0, orient="horizontal", length=220, command=self._animation_scale_changed)
        self.animation_frame_scale.pack(side="left", padx=(6, 6))
        self.animation_frame_scale.bind("<ButtonRelease-1>", lambda _event: self._apply_animation_frame())
        self.animation_frame_label = tk.StringVar(value="0 / 0")
        ttk.Label(animation_bar, textvariable=self.animation_frame_label, width=12).pack(side="left")
        ttk.Button(animation_bar, text="Apply Frame", command=self._apply_animation_frame).pack(side="left", padx=(4, 0))
        self.animation_play_button = ttk.Button(animation_bar, text="Play", command=self._toggle_animation_play, style="Accent.TButton")
        self.animation_play_button.pack(side="left", padx=(6, 12))
        ttk.Label(animation_bar, text="Camera").pack(side="left")
        for label, command in (
            ("Front", self._camera_front),
            ("Side", self._camera_side),
            ("Top", self._camera_top),
            ("Reset", self._camera_reset),
        ):
            ttk.Button(animation_bar, text=label, command=command).pack(side="left", padx=(4, 0))

        self.visual_tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected_ccsf_contents(), add="+")
        self.visual_canvas.bind("<ButtonRelease-1>", self._wire_release_drag)

    def _clear_ccsf_contents(self) -> None:
        self._ccsf_tree_payloads.clear()
        self._ccsf_contents_model = None
        if hasattr(self, "ccsf_contents_tree"):
            self.ccsf_contents_tree.delete(*self.ccsf_contents_tree.get_children())
        self._animation_rows_by_name.clear()
        if hasattr(self, "animation_combo"):
            self.animation_combo.configure(values=())
            self.animation_name.set("")
            self.animation_frame_scale.configure(from_=0, to=0)
            self.animation_frame_scale.set(0)
            self.animation_frame.set(0)
            self.animation_frame_label.set("0 / 0")

    def _load_selected_ccsf_contents(self) -> None:
        row = self._selected_visual_row()
        self._stop_animation()
        self._ccsf_tree_generation += 1
        generation = self._ccsf_tree_generation
        self._clear_ccsf_contents()
        if row is None:
            return
        self.visual_status.set(f"Reading internal CCSF tree: {row['name']}…")

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._ccsf_tree_generation:
                return
            if error:
                self.visual_status.set(f"CCSF contents failed: {error}")
                return
            self._ccsf_contents_model = model
            self._populate_ccsf_contents(model)
            animations = [item for item in model.get("animations") or [] if isinstance(item, dict) and item.get("pose_ready")]
            self._animation_rows_by_name = {str(item.get("object_name") or item.get("object_id")): item for item in animations}
            names = tuple(self._animation_rows_by_name)
            self.animation_combo.configure(values=names)
            if names:
                preferred = next((name for name in names if "nut" in name.lower()), names[0])
                self.animation_name.set(preferred)
                self._configure_animation_range()
            summary = model.get("summary") or {}
            self.visual_status.set(
                f"CCSF tree ready: {summary.get('clumps', 0)} clumps, {summary.get('materials', 0)} materials, "
                f"{summary.get('textures', 0)} textures, {summary.get('animations', 0)} animations."
            )

        self._local_worker("ccsf-contents-v5", lambda: inspect_ccsf_contents(row["absolute_path"]), done)

    def _populate_ccsf_contents(self, model: dict[str, Any]) -> None:
        self.ccsf_contents_tree.delete(*self.ccsf_contents_tree.get_children())
        self._ccsf_tree_payloads.clear()
        counter = 0

        def add(parent_iid: str, node: dict[str, Any], depth: int = 0) -> None:
            nonlocal counter
            iid = f"ccsf_node_{counter}"
            counter += 1
            self.ccsf_contents_tree.insert(
                parent_iid,
                "end",
                iid=iid,
                text=str(node.get("label") or ""),
                values=(str(node.get("kind") or ""),),
                open=depth == 0,
            )
            self._ccsf_tree_payloads[iid] = node
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    add(iid, child, depth + 1)

        for group in model.get("groups") or []:
            if isinstance(group, dict):
                add("", group)

    def _ccsf_contents_selected(self) -> None:
        selected = self.ccsf_contents_tree.selection()
        node = self._ccsf_tree_payloads.get(selected[0]) if selected else None
        if node is not None:
            _replace_text(self.visual_details, _json_text({"label": node.get("label"), "kind": node.get("kind"), "details": node.get("details") or {}}))

    # ------------------------------------------------------------------
    # Animation and camera
    # ------------------------------------------------------------------
    def _animation_scale_changed(self, value: str) -> None:
        frame = max(0, int(round(float(value))))
        self.animation_frame.set(frame)
        self._update_animation_frame_label(frame)

    def _animation_row(self) -> dict[str, Any] | None:
        return self._animation_rows_by_name.get(self.animation_name.get())

    def _configure_animation_range(self) -> None:
        row = self._animation_row()
        frame_count = max(1, int((row or {}).get("frame_count") or 1))
        self.animation_frame_scale.configure(from_=0, to=max(0, frame_count - 1))
        self.animation_frame_scale.set(0)
        self.animation_frame.set(0)
        self._update_animation_frame_label(0)

    def _update_animation_frame_label(self, frame: int | None = None) -> None:
        row = self._animation_row()
        frame_count = max(1, int((row or {}).get("frame_count") or 1))
        value = self.animation_frame.get() if frame is None else int(frame)
        self.animation_frame_label.set(f"{value} / {max(0, frame_count - 1)}")

    def _animation_selected(self) -> None:
        self._stop_animation()
        self._configure_animation_range()
        self._request_animation_frame(0)

    def _apply_animation_frame(self) -> None:
        self._stop_animation()
        frame = max(0, int(round(float(self.animation_frame_scale.get()))))
        self.animation_frame.set(frame)
        self._request_animation_frame(frame)

    def _request_animation_frame(self, frame: int) -> None:
        row = self._selected_visual_row()
        animation = self._animation_row()
        if row is None or animation is None:
            return
        frame_count = max(1, int(animation.get("frame_count") or 1))
        frame = int(frame) % frame_count
        self.animation_frame.set(frame)
        self.animation_frame_scale.set(frame)
        self._update_animation_frame_label(frame)
        if self._animation_frame_job:
            self._animation_pending_frame = frame
            return

        self._animation_frame_job = True
        self._animation_frame_generation += 1
        generation = self._animation_frame_generation
        source = str(row["absolute_path"])
        animation_name = self.animation_name.get()
        self.visual_status.set(f"Evaluating {animation_name} frame {frame}/{frame_count - 1}…")

        def done(payload: Any, error: Exception | None) -> None:
            self._animation_frame_job = False
            if generation != self._animation_frame_generation:
                return
            if error:
                self.visual_status.set(f"Animation frame failed: {error}")
                self._stop_animation()
                return
            self._preview_mode = "wireframe"
            self._textured_scene = None
            self._textured_scene_row = None
            self._wireframe_payload = payload
            self._draw_wireframe()
            self.visual_status.set(
                f"Animation wireframe: {payload.get('selected_animation') or animation_name} frame {payload.get('frame', frame)} | "
                f"{payload.get('vertex_count', 0):,} vertices / {payload.get('face_count', 0):,} faces. "
                "Textured Preview renders this current frame."
            )
            _replace_text(self.visual_details, _json_text({key: value for key, value in payload.items() if key not in {"vertices", "faces"}}))
            pending = self._animation_pending_frame
            self._animation_pending_frame = None
            if pending is not None and pending != frame:
                self._request_animation_frame(pending)
            elif self._animation_playing:
                self._schedule_animation_tick()

        self._local_worker(
            "animation-frame-v5",
            lambda: load_posed_wireframe_payload(source, animation_name=animation_name, frame=frame),
            done,
        )

    def _toggle_animation_play(self) -> None:
        if self._animation_row() is None:
            messagebox.showinfo("Animation", "Select an asset with a parsed animation first.")
            return
        if self._animation_playing:
            self._stop_animation()
            return
        self._animation_playing = True
        self.animation_play_button.configure(text="Pause")
        self._preview_mode = "wireframe"
        self._schedule_animation_tick(delay=0)

    def _schedule_animation_tick(self, delay: int = 100) -> None:
        if not self._animation_playing:
            return
        if self._animation_tick_after is not None:
            try:
                self.after_cancel(self._animation_tick_after)
            except tk.TclError:
                pass
        self._animation_tick_after = self.after(max(0, int(delay)), self._animation_tick)

    def _animation_tick(self) -> None:
        self._animation_tick_after = None
        if not self._animation_playing or self._animation_frame_job:
            return
        row = self._animation_row()
        frame_count = max(1, int((row or {}).get("frame_count") or 1))
        self._request_animation_frame((self.animation_frame.get() + 1) % frame_count)

    def _stop_animation(self) -> None:
        self._animation_playing = False
        if hasattr(self, "animation_play_button"):
            self.animation_play_button.configure(text="Play")
        if self._animation_tick_after is not None:
            try:
                self.after_cancel(self._animation_tick_after)
            except tk.TclError:
                pass
            self._animation_tick_after = None
        self._animation_pending_frame = None

    def _set_camera(self, yaw: float, pitch: float, zoom: float | None = None) -> None:
        self._wire_yaw = float(yaw)
        self._wire_pitch = float(pitch)
        if zoom is not None:
            self._wire_zoom = float(zoom)
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render(delay=20)
        else:
            self._draw_wireframe()

    def _camera_front(self) -> None:
        self._set_camera(0.0, 0.0, 1.0)

    def _camera_side(self) -> None:
        self._set_camera(math.pi / 2.0, 0.0, 1.0)

    def _camera_top(self) -> None:
        self._set_camera(0.0, -math.pi / 2.0, 1.0)

    def _camera_reset(self) -> None:
        self._set_camera(-0.55, 0.35, 1.0)

    # ------------------------------------------------------------------
    # Textured scene: render current pose, never rasterize every mouse move
    # ------------------------------------------------------------------
    def _draw_wireframe(self) -> None:
        if getattr(self, "_preview_mode", "wireframe") == "textured" and getattr(self, "_textured_scene", None) is not None:
            return
        super()._draw_wireframe()

    def _wire_drag_motion(self, event: tk.Event) -> None:
        if self._wire_drag is None:
            return
        old_x, old_y = self._wire_drag
        self._wire_yaw += (event.x - old_x) * 0.01
        self._wire_pitch += (event.y - old_y) * 0.01
        self._wire_drag = (event.x, event.y)
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self.visual_status.set(f"Camera moving | yaw {self._wire_yaw:.2f} pitch {self._wire_pitch:.2f} | release to rerender texture")
        else:
            super()._draw_wireframe()

    def _wire_release_drag(self, _event: tk.Event) -> None:
        self._wire_drag = None
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self._schedule_textured_render(delay=20)

    def _wire_mousewheel(self, event: tk.Event) -> None:
        self._wire_zoom = max(0.15, min(8.0, self._wire_zoom * (1.12 if event.delta > 0 else 0.89)))
        if self._preview_mode == "textured" and self._textured_scene is not None:
            self.visual_status.set(f"Camera zoom {self._wire_zoom:.2f} | waiting to rerender texture…")
            self._schedule_textured_render(delay=320)
        else:
            super()._draw_wireframe()

    def _schedule_textured_render(self, delay: int = 320) -> None:
        if self._textured_scene is None or self._textured_scene_row is None:
            return
        if self._textured_render_after is not None:
            try:
                self.after_cancel(self._textured_render_after)
            except tk.TclError:
                pass
        self._textured_render_after = self.after(max(0, int(delay)), self._start_textured_render_v5)

    def _start_textured_render_v5(self) -> None:
        self._textured_render_after = None
        scene = self._textured_scene
        row = self._textured_scene_row
        project = self.project
        if scene is None or row is None or project is None or self._preview_mode != "textured":
            return
        if self._textured_render_busy:
            self._textured_render_pending = True
            return
        self._textured_render_busy = True
        self._textured_render_pending = False
        self._textured_render_generation += 1
        generation = self._textured_render_generation
        yaw, pitch, zoom = self._wire_yaw, self._wire_pitch, self._wire_zoom
        width, height = max(320, self.visual_canvas.winfo_width()), max(240, self.visual_canvas.winfo_height())
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"])) / "textured_preview.png"
        self.visual_status.set("Rendering settled textured view…")

        def done(result: Any, error: Exception | None) -> None:
            self._textured_render_busy = False
            if generation == self._textured_render_generation and self._preview_mode == "textured":
                if error:
                    self.visual_status.set(f"Textured rerender failed: {error}")
                else:
                    try:
                        self._show_png_on_visual_canvas(Path(result["output_path"]))
                        self.visual_status.set(
                            f"Textured view | yaw {yaw:.2f} pitch {pitch:.2f} zoom {zoom:.2f} | "
                            f"{result['textured_faces']:,} textured / {result['unresolved_faces']:,} unresolved"
                        )
                    except Exception as exc:
                        self.visual_status.set(f"Textured PNG display failed: {exc}")
            if self._textured_render_pending and self._preview_mode == "textured":
                self._textured_render_pending = False
                self._schedule_textured_render(delay=20)

        self._local_worker(
            "textured-rerender-v5",
            lambda: render_textured_scene(scene, output, yaw=yaw, pitch=pitch, zoom=zoom, width=width, height=height),
            done,
        )

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
        self._stop_animation()
        animation = self.animation_name.get().strip() or None
        frame = max(0, int(self.animation_frame.get()))
        output = project.workspace_path("texture_outputs") / _safe_folder(str(row["relative_path"]))
        self.visual_status.set(f"Decoding current pose and textures: {row['name']} / {animation or 'default pose'} frame {frame}…")
        self.visual_progress.configure(mode="indeterminate")
        self.visual_progress.start(60)
        active_row = dict(row)

        def work() -> Any:
            scene = load_textured_scene(row["absolute_path"], animation_name=animation, frame=frame)
            textures = export_scene_textures(scene, output / "textures")
            render = render_textured_scene(
                scene,
                output / "textured_preview.png",
                yaw=self._wire_yaw,
                pitch=self._wire_pitch,
                zoom=self._wire_zoom,
                width=max(320, self.visual_canvas.winfo_width()),
                height=max(240, self.visual_canvas.winfo_height()),
            )
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
            _replace_text(
                self.visual_details,
                _json_text(
                    {
                        "scene": summary,
                        "texture_export": result["textures"],
                        "texture_records": result["scene"].texture_rows,
                        "render": {key: value for key, value in result["render"].items() if key != "scene_summary"},
                    }
                ),
            )
            self.visual_status.set(
                f"Textured pose: {summary.get('textured_triangles', 0):,} textured / {summary.get('unresolved_triangles', 0):,} unresolved; "
                f"{summary.get('decoded_textures', 0):,}/{summary.get('texture_records', 0):,} texture records decoded; "
                f"{summary.get('selected_animation') or 'none'} frame {summary.get('frame', 0)}."
            )

        self._local_worker("textured-scene-v5", work, done)

    # ------------------------------------------------------------------
    # RUN ALL v4 and report-backed mixer
    # ------------------------------------------------------------------
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
            actions = build_run_all_actions_v4(project)
        except Exception as exc:
            self._append_log(str(exc))
            return
        descriptions = {
            "ccsf_extract": "Full focused CCSF extraction. First run can take a long time.",
            "extraction_audit": "Verify DATA/DATA.BIN coverage and indexed output files.",
            "sound_extract": "Extract ISO sound/* plus SNDDATA and NETGUI EFF banks into project/sound/source.",
            "sound_decode": "Decode validated project sound containers and streams into project/sound/decoded.",
            "snddata_v4": "Parse SNDDATA once and write the sequence / Program / exact sample coverage catalog used by the mixer.",
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

        self._background("RUN ALL", lambda: execute_run_all_v4(project, callback=callback, cancel_event=self.cancel_event), self._run_all_done, already_busy=True)

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        super()._run_all_done(result, error)
        clear_runtime_cache()
        if not error and result and str(result.get("status") or "") == "complete":
            self._refresh_simple_audio()
            self._refresh_audio_sequences()

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
        self.simple_audio_status.set("Reading active project/sound catalog…")

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._simple_audio_generation:
                return
            if error:
                self.simple_audio_status.set(f"Sound library failed: {error}")
                return
            categories = ("All", *model.get("categories", []))
            if self._sound_category_combo is not None:
                self._sound_category_combo.configure(values=categories)
            for index, item in enumerate(model["items"]):
                iid = f"simple_audio_{index}"
                wav = item.get("wav") or {}
                duration = f"{float(wav.get('duration') or 0):.2f}s" if item.get("playable") else "—"
                self.simple_audio_tree.insert("", "end", iid=iid, text=item["name"], values=(item["kind"], item["category"], duration, item["primary_action"], f"{item['size']:,}", item["relative_path"]))
                self._simple_audio_rows[iid] = item
            summary = model["summary"]
            self.simple_audio_status.set(
                f"project/sound: {summary['source_files']} source files; {summary['playable_wavs']} playable WAVs; "
                f"{summary['supported_containers']} actionable containers; {summary.get('hidden_metadata_files', 0)} metadata JSON hidden."
            )

        self._local_worker("project-sound-library-v2", lambda: build_project_sound_library(project, query=query, category=category), done)

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
            self.simple_audio_status.set(f"No verified decoder for {row['name']}; source evidence is shown below.")
            return
        self.simple_audio_status.set(f"{row['primary_action']}: {row['relative_path']}…")

        def done(result: Any, error: Exception | None) -> None:
            if error:
                self.simple_audio_status.set(f"Audio action failed: {error}")
                _replace_text(self.simple_audio_details, str(error))
                return
            _replace_text(self.simple_audio_details, _json_text(result))
            self.simple_audio_status.set(f"Audio action complete: {row['name']}")
            self._refresh_simple_audio()

        self._local_worker("sound-primary-action-v2", lambda: analyze_or_extract_sound_item(project, row["path"]), done)

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
        self.audio_status.set("Loading RUN ALL SNDDATA music catalog…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._audio_generation:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Music catalog is not ready: {error}")
                _replace_text(self.audio_details, f"{error}\nRun RUN ALL / Index SNDDATA Music System first.")
                return
            self.audio_progress["value"] = 100.0
            for index, item in enumerate(rows):
                iid = f"sequence_{index}"
                routing = f"{item['program_change_count']} changes / {item['routing_status']}"
                self.sequence_tree.insert("", "end", iid=iid, text=item["sequence_id"], values=(item["note_on_count"], routing))
                self.sequence_payloads[iid] = item
            routed = sum(1 for item in rows if item.get("program_change_count"))
            self.audio_status.set(f"Catalog loaded: {len(rows)} sequences; {routed} contain Program Change routing. Selection no longer reparses SNDDATA.")
            first = next((iid for iid, item in self.sequence_payloads.items() if item.get("program_change_count")), next(iter(self.sequence_payloads), None))
            if first:
                self.sequence_tree.selection_set(first)
                self.sequence_tree.focus(first)
                self._refresh_audio_candidates()

        self._local_worker("music-catalog-v4-sequences", lambda: sequence_rows(project), done)

    def _refresh_audio_candidates(self) -> None:
        project = self.project
        sequence = self._selected_sequence()
        self._candidate_generation += 1
        generation = self._candidate_generation
        self.program_tree.delete(*self.program_tree.get_children())
        self.program_payloads.clear()
        if project is None or sequence is None:
            return
        self.audio_status.set(f"Loading ranked Program candidates for {sequence['sequence_id']} from catalog…")

        def done(model: Any, error: Exception | None) -> None:
            if generation != self._candidate_generation:
                return
            if error:
                self.audio_status.set(f"Program catalog failed: {error}")
                _replace_text(self.audio_details, str(error))
                return
            for index, item in enumerate(model["candidates"]):
                iid = f"program_{index}"
                self.program_tree.insert("", "end", iid=iid, text=item["resource_id"], values=(item["program_count"], len(item["required_sample_ids"]), item["decoded_sample_count"]))
                self.program_payloads[iid] = item
            _replace_text(self.audio_details, _json_text(model))
            best = next((iid for iid, item in self.program_payloads.items() if item.get("status") == "renderable"), next(iter(self.program_payloads), None))
            if best:
                self.program_tree.selection_set(best)
                self.program_tree.focus(best)
            renderable = sum(1 for item in model["candidates"] if item.get("status") == "renderable")
            self.audio_status.set(f"{len(model['candidates'])} cached Program candidates; {renderable} fully cover referenced Programs and exact slot sample IDs.")

        self._local_worker("music-catalog-v4-candidates", lambda: sequence_view_model(project, sequence["sequence_id"]), done)

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
        self.audio_status.set("Rendering selected Program-Change route; first render may hydrate the binary runtime once…")
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

        self._local_worker("music-system-v4-render", lambda: render_sequence(project, sequence["sequence_id"], program_resource_offset=resource_offset, master_gain=self.audio_gain.get()), done)


def main() -> int:
    PublicFragmenterAppV5().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

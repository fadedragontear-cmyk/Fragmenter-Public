#!/usr/bin/env python3
"""Eleventh public GUI pass: sample-library extraction and per-asset preview profiles."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import ccsf_texture_audit_v1 as texture_audit_v1
import ccsf_textured_scene_v7 as scene_v7
import fragmenter_public_gui_v5 as gui_v5
import fragmenter_public_gui_v7 as gui_v7
import fragmenter_public_gui_v8 as gui_v8
from asset_preview_profiles_v1 import DEFAULT_PROFILE, delete_profile, load_profile, save_profile
from fragmenter_public_gui_v10 import PublicFragmenterAppV10
from project_sound_v5 import analyze_or_extract_sound_item, build_project_sound_library
from run_all_executor_v7 import build_run_all_actions_v7, execute_run_all_v7
from snddata_sample_library_v1 import extract_project_snddata_samples

# Preserve the validated GUI lifecycle while replacing only its backend authorities.
gui_v5.load_textured_scene = scene_v7.load_textured_scene
gui_v5.load_posed_wireframe_payload = scene_v7.load_posed_wireframe_payload
gui_v5.render_textured_scene = scene_v7.render_textured_scene
gui_v5.export_scene_textures = scene_v7.export_scene_textures
gui_v5.build_project_sound_library = build_project_sound_library
gui_v5.analyze_or_extract_sound_item = analyze_or_extract_sound_item
gui_v5.build_run_all_actions_v4 = build_run_all_actions_v7
gui_v5.execute_run_all_v4 = execute_run_all_v7
gui_v7.scene_v5 = scene_v7
gui_v8.scene_v6 = scene_v7
gui_v8.load_clump_wireframe_payload = scene_v7.load_posed_wireframe_payload
texture_audit_v1.load_textured_scene = scene_v7.load_textured_scene


class PublicFragmenterAppV11(PublicFragmenterAppV10):
    """Expose PSound-style sample extraction and reversible model-specific preview fixes."""

    def __init__(self) -> None:
        self.snddata_extract_status: tk.StringVar | None = None
        self.preview_profile_status: tk.StringVar | None = None
        self.profile_scale: list[tk.DoubleVar] = []
        self.profile_rotation: list[tk.DoubleVar] = []
        self.profile_translation: list[tk.DoubleVar] = []
        self.profile_flip_winding: tk.BooleanVar | None = None
        super().__init__()

    def _build_audio(self, parent: ttk.Frame) -> None:
        super()._build_audio(parent)
        sample_tools = ttk.LabelFrame(parent, text="Extracted sample library", padding=6)
        sample_tools.grid(row=99, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.snddata_extract_status = tk.StringVar(
            value="SNDDATA samples are extracted from HEAD secondary data using SCEIVagi offsets and sample rates."
        )
        ttk.Button(
            sample_tools,
            text="Extract / Rebuild SNDDATA Samples",
            command=self._extract_snddata_sample_library,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(sample_tools, text="Refresh Audio Library", command=self._refresh_simple_audio).pack(side="left", padx=(6, 0))
        ttk.Label(sample_tools, textvariable=self.snddata_extract_status, wraplength=840).pack(side="left", padx=(12, 0), fill="x", expand=True)

    def _extract_snddata_sample_library(self) -> None:
        project = self._require_project()
        if project is None:
            return
        if self.snddata_extract_status is not None:
            self.snddata_extract_status.set("Rebuilding SNDDATA sample banks and WAV library…")

        def done(result: Any, error: Exception | None) -> None:
            if error:
                if self.snddata_extract_status is not None:
                    self.snddata_extract_status.set(f"SNDDATA extraction failed: {error}")
                messagebox.showerror("SNDDATA Samples", str(error))
                return
            summary = result["summary"]
            if self.snddata_extract_status is not None:
                self.snddata_extract_status.set(
                    f"Extracted {summary['decoded_wavs']} playable WAVs from {summary['decoded_banks']} banks; "
                    f"{summary['failed_samples']} sample failures."
                )
            self._refresh_simple_audio()
            self._refresh_reports()

        self._local_worker(
            "snddata-sample-library-v1",
            lambda: extract_project_snddata_samples(project, clean=True),
            done,
        )

    def _build_visual(self, parent: ttk.Frame) -> None:
        super()._build_visual(parent)
        profile = ttk.LabelFrame(parent, text="Per-asset preview adjustment", padding=6)
        profile.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.profile_scale = [tk.DoubleVar(value=1.0) for _ in range(3)]
        self.profile_rotation = [tk.DoubleVar(value=0.0) for _ in range(3)]
        self.profile_translation = [tk.DoubleVar(value=0.0) for _ in range(3)]
        self.profile_flip_winding = tk.BooleanVar(value=False)
        self.preview_profile_status = tk.StringVar(value="No saved adjustment loaded")

        def vector_controls(row: int, label: str, values: list[tk.DoubleVar], increment: float) -> None:
            ttk.Label(profile, text=label).grid(row=row, column=0, sticky="w", padx=(0, 5))
            for index, axis in enumerate("XYZ"):
                ttk.Label(profile, text=axis).grid(row=row, column=1 + index * 2, sticky="e")
                ttk.Spinbox(
                    profile,
                    from_=-10000.0,
                    to=10000.0,
                    increment=increment,
                    textvariable=values[index],
                    width=9,
                ).grid(row=row, column=2 + index * 2, padx=(2, 7), sticky="w")

        vector_controls(0, "Scale", self.profile_scale, 0.05)
        vector_controls(1, "Rotate °", self.profile_rotation, 5.0)
        vector_controls(2, "Translate", self.profile_translation, 0.1)
        ttk.Checkbutton(profile, text="Flip triangle winding", variable=self.profile_flip_winding).grid(row=0, column=7, sticky="w", padx=(8, 0))
        ttk.Button(profile, text="Apply", command=self._apply_preview_profile, style="Accent.TButton").grid(row=1, column=7, sticky="ew", padx=(8, 0))
        ttk.Button(profile, text="Save for Asset", command=self._save_preview_profile).grid(row=2, column=7, sticky="ew", padx=(8, 0))
        ttk.Button(profile, text="Reset Saved", command=self._reset_preview_profile).grid(row=2, column=8, sticky="ew", padx=(6, 0))
        ttk.Label(profile, textvariable=self.preview_profile_status, wraplength=420).grid(row=0, column=8, rowspan=2, sticky="w", padx=(10, 0))

    def _populate_ccsf_contents(self, model: dict[str, Any]) -> None:
        super()._populate_ccsf_contents(model)
        self.after_idle(self._load_selected_preview_profile)

    def _set_profile_controls(self, profile: dict[str, Any]) -> None:
        transform = profile.get("transform") or {}
        for variables, values in (
            (self.profile_scale, transform.get("scale") or [1.0, 1.0, 1.0]),
            (self.profile_rotation, transform.get("rotation_degrees") or [0.0, 0.0, 0.0]),
            (self.profile_translation, transform.get("translation") or [0.0, 0.0, 0.0]),
        ):
            for variable, value in zip(variables, values):
                variable.set(float(value))
        if self.profile_flip_winding is not None:
            self.profile_flip_winding.set(bool(transform.get("flip_winding", False)))

    def _current_profile(self) -> dict[str, Any]:
        row = self._selected_visual_row()
        clump_id = self._preview_clumps_by_label.get(self.preview_clump_name.get()) if hasattr(self, "preview_clump_name") else None
        return {
            "clump_id": clump_id,
            "animation": self.animation_name.get().strip() if hasattr(self, "animation_name") else "",
            "frame": max(0, int(self.animation_frame.get())) if hasattr(self, "animation_frame") else 0,
            "camera": {
                "yaw": float(self._wire_yaw),
                "pitch": float(self._wire_pitch),
                "zoom": float(self._wire_zoom),
                "pan_x": float(self._wire_pan_x),
                "pan_y": float(self._wire_pan_y),
            },
            "transform": {
                "scale": [variable.get() for variable in self.profile_scale],
                "rotation_degrees": [variable.get() for variable in self.profile_rotation],
                "translation": [variable.get() for variable in self.profile_translation],
                "flip_winding": bool(self.profile_flip_winding.get()) if self.profile_flip_winding is not None else False,
            },
            "source": row.get("absolute_path") if row else None,
        }

    def _load_selected_preview_profile(self) -> None:
        project = self.project
        row = self._selected_visual_row()
        if project is None or row is None or not self.profile_scale:
            return
        profile = load_profile(project, row["absolute_path"])
        self._set_profile_controls(profile)
        self._install_profile(row, profile, reload_scene=True)
        if self.preview_profile_status is not None:
            self.preview_profile_status.set(
                "Loaded and applied the saved/default adjustment for this asset."
            )

    def _install_profile(self, row: dict[str, Any], profile: dict[str, Any], *, reload_scene: bool) -> None:
        scene_v7.set_preview_override(row["absolute_path"], profile)
        clump_id = profile.get("clump_id")
        if clump_id is not None:
            scene_v7.set_preferred_clump(row["absolute_path"], int(clump_id))
            for label, candidate in self._preview_clumps_by_label.items():
                if int(candidate) == int(clump_id):
                    self.preview_clump_name.set(label)
                    break
        camera = profile.get("camera") or {}
        self._wire_yaw = float(camera.get("yaw", -0.55))
        self._wire_pitch = float(camera.get("pitch", 0.35))
        self._wire_zoom = float(camera.get("zoom", 1.25))
        self._wire_pan_x = float(camera.get("pan_x", 0.0))
        self._wire_pan_y = float(camera.get("pan_y", 0.0))
        self._sync_zoom_control()
        animation = str(profile.get("animation") or "")
        if animation and animation in self._animation_rows_by_name:
            self.animation_name.set(animation)
            self._configure_animation_range()
            frame_count = max(1, int(self._animation_rows_by_name[animation].get("frame_count") or 1))
            frame = min(max(0, int(profile.get("frame") or 0)), frame_count - 1)
            self.animation_frame.set(frame)
            self.animation_frame_scale.set(frame)
            self._update_animation_frame_label(frame)
        if reload_scene:
            scene_v7.clear_scene_cache(row["absolute_path"])
            self._stop_animation()
            self._wireframe_load(allow_auto_texture=True)

    def _apply_preview_profile(self) -> None:
        row = self._selected_visual_row()
        if row is None:
            messagebox.showinfo("Preview Adjustment", "Select an asset first.")
            return
        profile = self._current_profile()
        self._install_profile(row, profile, reload_scene=True)
        if self.preview_profile_status is not None:
            self.preview_profile_status.set("Applied non-destructive preview adjustment to this asset.")

    def _save_preview_profile(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None or row is None:
            return
        profile = save_profile(project, row["absolute_path"], self._current_profile())
        self._install_profile(row, profile, reload_scene=True)
        if self.preview_profile_status is not None:
            self.preview_profile_status.set("Saved in project.json for this extracted asset.")

    def _reset_preview_profile(self) -> None:
        project = self._require_project()
        row = self._selected_visual_row()
        if project is None or row is None:
            return
        delete_profile(project, row["absolute_path"])
        profile = dict(DEFAULT_PROFILE)
        self._set_profile_controls(profile)
        scene_v7.set_preferred_clump(row["absolute_path"], None)
        self._install_profile(row, profile, reload_scene=True)
        if self.preview_profile_status is not None:
            self.preview_profile_status.set("Saved adjustment removed; source-backed defaults restored.")


def main() -> int:
    app = PublicFragmenterAppV11()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

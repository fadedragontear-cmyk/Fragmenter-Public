#!/usr/bin/env python3
"""Thirty-fourth public GUI pass: Euler experiments and conservative review assists."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

import camera_orbit_v1 as camera_orbit
import ccsf_gen1_pose_v7 as pose_v7
import ccsf_textured_scene_v9 as scene_v9
from fragmenter_public_gui_v33 import PublicFragmenterAppV33
from visual_review_assist_v1 import suggest_project_camera


class PublicFragmenterAppV34(PublicFragmenterAppV33):
    """Expose session-only Euler tests and suggest reviewed sibling camera views."""

    def __init__(self) -> None:
        self._euler_map_v34: tk.StringVar | None = None
        self._euler_order_v34: tk.StringVar | None = None
        self._euler_signs_v34: tk.StringVar | None = None
        self._euler_parent_v34: tk.StringVar | None = None
        self._euler_widgets_v34: list[tk.Misc] = []
        self._camera_suggestion_source_v34: str | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Euler Puppetry / Assisted Visual Review")

    # ------------------------------------------------------------------
    # Compact clump + Euler tester strip.
    # M = source-component map, O = axis application order, +/- = local-axis signs,
    # H = hierarchy multiplication order. Tester choices are session-only.
    # ------------------------------------------------------------------
    def _compact_animation_controls_v32(self) -> None:
        super()._compact_animation_controls_v32()
        combo = getattr(self, "animation_combo", None)
        bar = combo.master if combo is not None else None
        if bar is None:
            return

        for column in range(12):
            bar.columnconfigure(column, weight=0)
        bar.columnconfigure(1, weight=1)
        bar.columnconfigure(3, weight=3)

        if self._euler_map_v34 is None:
            profile = pose_v7.euler_test_profile()
            self._euler_map_v34 = tk.StringVar(master=self, value=profile["component_map"])
            self._euler_order_v34 = tk.StringVar(master=self, value=profile["order"])
            self._euler_signs_v34 = tk.StringVar(master=self, value=profile["signs"])
            parent = "L×P" if profile["parent_mode"] == "LXP" else "P×L"
            self._euler_parent_v34 = tk.StringVar(master=self, value=parent)

        pose_label = None
        apply_frame = None
        textured_toggle = None
        for child in bar.winfo_children():
            try:
                text = str(child.cget("text"))
            except tk.TclError:
                continue
            if isinstance(child, ttk.Label) and text in {"Pose / Animation", "Animation"}:
                pose_label = child
            elif isinstance(child, ttk.Button) and text in {"Apply", "Apply Frame"}:
                apply_frame = child
            elif isinstance(child, ttk.Checkbutton) and text in {"Textured playback", "Textured"}:
                textured_toggle = child

        if self._preview_clump_label_v33 is not None:
            self._preview_clump_label_v33.configure(text="Clump")
            self._preview_clump_label_v33.grid_configure(row=0, column=0, sticky="w")
        self.preview_clump_combo.configure(width=18)
        self.preview_clump_combo.grid_configure(row=0, column=1, columnspan=2, sticky="ew", padx=(5, 5))
        if self._preview_clump_reload_v33 is not None:
            self._preview_clump_reload_v33.grid_configure(row=0, column=3, padx=(0, 7))

        if not self._euler_widgets_v34:
            label = ttk.Label(bar, text="Euler M/O/±/H")
            map_combo = ttk.Combobox(
                bar,
                textvariable=self._euler_map_v34,
                values=tuple(pose_v7.euler_test.MAPS),
                state="readonly",
                width=4,
            )
            order_combo = ttk.Combobox(
                bar,
                textvariable=self._euler_order_v34,
                values=tuple(pose_v7.euler_test.ORDERS),
                state="readonly",
                width=4,
            )
            signs_combo = ttk.Combobox(
                bar,
                textvariable=self._euler_signs_v34,
                values=tuple(pose_v7.euler_test.SIGNS),
                state="readonly",
                width=4,
            )
            parent_combo = ttk.Combobox(
                bar,
                textvariable=self._euler_parent_v34,
                values=("L×P", "P×L"),
                state="readonly",
                width=4,
            )
            apply_button = ttk.Button(bar, text="Apply", command=self._apply_euler_profile_v34)
            studio_button = ttk.Button(bar, text="Studio", command=self._studio_euler_profile_v34)
            reset_button = ttk.Button(bar, text="Reset", command=self._reset_euler_profile_v34)
            self._euler_widgets_v34 = [
                label,
                map_combo,
                order_combo,
                signs_combo,
                parent_combo,
                apply_button,
                studio_button,
                reset_button,
            ]
        label, map_combo, order_combo, signs_combo, parent_combo, apply_button, studio_button, reset_button = self._euler_widgets_v34
        label.grid(row=0, column=4, sticky="e", padx=(0, 4))
        map_combo.grid(row=0, column=5, padx=1)
        order_combo.grid(row=0, column=6, padx=1)
        signs_combo.grid(row=0, column=7, padx=1)
        parent_combo.grid(row=0, column=8, padx=1)
        apply_button.grid(row=0, column=9, padx=(4, 1))
        studio_button.grid(row=0, column=10, padx=1)
        reset_button.grid(row=0, column=11, padx=(1, 0))

        if pose_label is not None:
            pose_label.configure(text="Animation")
            pose_label.grid_configure(row=1, column=0, sticky="w", pady=(3, 0))
        self.animation_combo.grid_configure(row=1, column=1, columnspan=2, sticky="ew", padx=(5, 7), pady=(3, 0))
        self.animation_frame_scale.grid_configure(row=1, column=3, columnspan=5, sticky="ew", padx=(0, 6), pady=(3, 0))
        if apply_frame is not None:
            apply_frame.grid_configure(row=1, column=8, padx=(2, 0), pady=(3, 0))
        self.animation_play_button.grid_configure(row=1, column=9, padx=(4, 0), pady=(3, 0))
        if textured_toggle is not None:
            textured_toggle.configure(text="Textured")
            textured_toggle.grid_configure(row=1, column=10, columnspan=2, padx=(8, 0), pady=(3, 0), sticky="w")

    def _current_euler_profile_v34(self) -> dict[str, str]:
        parent = self._euler_parent_v34.get() if self._euler_parent_v34 is not None else "L×P"
        return {
            "component_map": self._euler_map_v34.get() if self._euler_map_v34 is not None else "XYZ",
            "order": self._euler_order_v34.get() if self._euler_order_v34 is not None else "XYZ",
            "signs": self._euler_signs_v34.get() if self._euler_signs_v34 is not None else "+++",
            "parent_mode": "LXP" if parent == "L×P" else "PXL",
        }

    def _apply_euler_profile_v34(self) -> None:
        profile = self._current_euler_profile_v34()
        pose_v7.set_euler_test_profile(**profile)
        self._rerender_euler_profile_v34("Euler test")

    def _studio_euler_profile_v34(self) -> None:
        profile = pose_v7.studio_ccs_euler_test_profile()
        if self._euler_map_v34 is not None:
            self._euler_map_v34.set(profile["component_map"])
            self._euler_order_v34.set(profile["order"])
            self._euler_signs_v34.set(profile["signs"])
            self._euler_parent_v34.set("L×P")
        self._rerender_euler_profile_v34("StudioCCS Z/-Y/X test")

    def _reset_euler_profile_v34(self) -> None:
        profile = pose_v7.reset_euler_test_profile()
        if self._euler_map_v34 is not None:
            self._euler_map_v34.set(profile["component_map"])
            self._euler_order_v34.set(profile["order"])
            self._euler_signs_v34.set(profile["signs"])
            self._euler_parent_v34.set("L×P")
        self._rerender_euler_profile_v34("Euler test reset")

    def _rerender_euler_profile_v34(self, label: str) -> None:
        row = self._selected_visual_row()
        if row is None:
            self.visual_status.set(f"{label}: select an asset first.")
            return
        source = Path(row["absolute_path"]).resolve()
        self._stop_animation()
        scene_v9.clear_scene_cache(source)
        animation = self.animation_name.get().strip() or pose_v7.INITIAL_POSE_NAME
        frame = max(0, int(self.animation_frame.get()))
        profile = pose_v7.euler_test_profile()
        self.visual_status.set(
            f"{label}: map {profile['component_map']}, order {profile['order']}, signs {profile['signs']}, "
            f"chain {profile['parent_mode']}; rebuilding {animation} frame {frame}."
        )
        if animation != pose_v7.INITIAL_POSE_NAME:
            self.after_idle(lambda value=frame: self._request_animation_frame(value))
        else:
            self.after_idle(lambda: self._wireframe_load(allow_auto_texture=True))

    # ------------------------------------------------------------------
    # Reviewed sibling cameras are applied only when the current asset has no saved
    # view. The suggestion remains unsaved until Save Pose / Position is clicked.
    # ------------------------------------------------------------------
    def _build_camera_view_section_v32(self, parent: ttk.Frame) -> None:
        super()._build_camera_view_section_v32(parent)
        for child in parent.winfo_children():
            if not isinstance(child, ttk.LabelFrame):
                continue
            for descendant in child.winfo_children():
                if not isinstance(descendant, ttk.Frame):
                    continue
                texts = []
                for item in descendant.winfo_children():
                    try:
                        texts.append(str(item.cget("text")))
                    except tk.TclError:
                        pass
                if "Save Pose / Position" in texts:
                    ttk.Button(descendant, text="Family View", command=self._apply_family_camera_v34).pack(
                        side="left", padx=(6, 0)
                    )
                    return

    def _camera_suggestion_v34(self) -> dict[str, Any] | None:
        project = self.project
        row = self._selected_visual_row()
        if project is None or row is None:
            return None
        return suggest_project_camera(project, row["absolute_path"])

    def _set_camera_suggestion_v34(self, suggestion: dict[str, Any]) -> None:
        background = str(suggestion.get("background") or "Dark Gray")
        if self.preview_background_var is not None and background in self.BACKGROUNDS:
            self.preview_background_var.set(background)
            self._preview_background_changed_v25(render=False)
        self._set_basis_v29(camera_orbit.basis_from_flat(suggestion.get("basis")), sync_panel=False)
        self._set_position_v30(tuple(suggestion["position"]), sync_panel=False)
        self._wire_zoom = float(suggestion.get("zoom") or 1.0)
        self._wire_pan_x = float(suggestion.get("pan_x") or 0.0)
        self._wire_pan_y = float(suggestion.get("pan_y") or 0.0)
        self._sync_zoom_control()
        self._sync_renderer_camera_v30()
        self._sync_camera_panel_v29()
        self._draw_wireframe()
        self._camera_suggestion_source_v34 = str(suggestion.get("source_asset_key") or "")

    def _apply_saved_camera_v27(self, annotation: dict[str, Any]) -> None:
        if isinstance(annotation.get("camera"), dict):
            self._camera_suggestion_source_v34 = None
            super()._apply_saved_camera_v27(annotation)
            return
        suggestion = self._camera_suggestion_v34()
        if suggestion is None:
            self._camera_suggestion_source_v34 = None
            super()._apply_saved_camera_v27(annotation)
            return
        self._set_camera_suggestion_v34(suggestion)
        source = suggestion.get("source_asset_key")
        self.after(
            120,
            lambda: self.visual_status.set(
                f"Suggested unsaved family camera from {source}. Review it, then use Save Pose / Position to retain it."
            ),
        )

    def _apply_family_camera_v34(self) -> None:
        suggestion = self._camera_suggestion_v34()
        if suggestion is None:
            self.visual_status.set("No reviewed sibling camera is available for this asset family.")
            return
        self._set_camera_suggestion_v34(suggestion)
        self.visual_status.set(
            f"Applied unsaved family camera from {suggestion['source_asset_key']}. Save only after reviewing it."
        )
        self._finish_discrete_camera_change_v27()


def main() -> int:
    app = PublicFragmenterAppV34()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

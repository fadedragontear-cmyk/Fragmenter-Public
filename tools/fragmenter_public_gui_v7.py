#!/usr/bin/env python3
"""Seventh public GUI pass: clump-authoritative 3D instances and real BGM/FOOD source reachability."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import ccsf_texture_audit_v1 as texture_audit_v1
import ccsf_textured_scene_v5 as scene_v5
import fragmenter_public_gui_v5 as gui_v5
from fragmenter_public_gui_v6 import PublicFragmenterAppV6
from project_sound_v4 import analyze_or_extract_sound_item, build_project_sound_library
from run_all_executor_v6 import build_run_all_actions_v6, execute_run_all_v6

# V5 owns the preview/playback method bodies and resolves these imported globals at
# call time. Swap only their backend authorities; the validated GUI behavior stays
# recoverable in the previous layers.
gui_v5.load_textured_scene = scene_v5.load_textured_scene
gui_v5.load_posed_wireframe_payload = scene_v5.load_posed_wireframe_payload
gui_v5.render_textured_scene = scene_v5.render_textured_scene
gui_v5.export_scene_textures = scene_v5.export_scene_textures
gui_v5.build_project_sound_library = build_project_sound_library
gui_v5.analyze_or_extract_sound_item = analyze_or_extract_sound_item
gui_v5.build_run_all_actions_v4 = build_run_all_actions_v6
gui_v5.execute_run_all_v4 = execute_run_all_v6

# Texture audit should report the exact selected/default clump-backed scene summary.
texture_audit_v1.load_textured_scene = scene_v5.load_textured_scene


class PublicFragmenterAppV7(PublicFragmenterAppV6):
    def __init__(self) -> None:
        self._preview_clumps_by_label: dict[str, int] = {}
        self.preview_clump_combo: ttk.Combobox | None = None
        super().__init__()

    def _build_visual(self, parent: ttk.Frame) -> None:
        super()._build_visual(parent)
        self.preview_clump_name = tk.StringVar(value="")
        self.preview_clump_status = tk.StringVar(value="No clump selected")
        clump_bar = ttk.LabelFrame(parent, text="Scene assembly", padding=5)
        clump_bar.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(clump_bar, text="Preview Clump").pack(side="left")
        self.preview_clump_combo = ttk.Combobox(
            clump_bar,
            textvariable=self.preview_clump_name,
            values=(),
            state="readonly",
            width=48,
        )
        self.preview_clump_combo.pack(side="left", padx=(6, 10))
        self.preview_clump_combo.bind("<<ComboboxSelected>>", lambda _event: self._preview_clump_selected())
        ttk.Label(
            clump_bar,
            text="StudioCCS-style CMP → node OBJ → ChildModel traversal; largest clump is the default.",
        ).pack(side="left")
        ttk.Label(clump_bar, textvariable=self.preview_clump_status).pack(side="right")

    def _clear_ccsf_contents(self) -> None:
        super()._clear_ccsf_contents()
        self._preview_clumps_by_label.clear()
        if hasattr(self, "preview_clump_name"):
            self.preview_clump_name.set("")
        if hasattr(self, "preview_clump_status"):
            self.preview_clump_status.set("No clump selected")
        if self.preview_clump_combo is not None:
            self.preview_clump_combo.configure(values=())

    @staticmethod
    def _clump_choice_key(row: dict[str, Any]) -> tuple[int, int]:
        name = str(row.get("clump_name") or "").lower()
        return int(row.get("node_count") or 0), 1 if "trall" in name or "thrall" in name else 0

    def _populate_ccsf_contents(self, model: dict[str, Any]) -> None:
        super()._populate_ccsf_contents(model)
        rows: list[dict[str, Any]] = []
        for group in model.get("groups") or []:
            if not isinstance(group, dict):
                continue
            for child in group.get("children") or []:
                if not isinstance(child, dict) or child.get("kind") != "clump":
                    continue
                details = child.get("details") if isinstance(child.get("details"), dict) else {}
                clump_id = int(details.get("clump_id") or 0)
                rows.append(
                    {
                        "clump_id": clump_id,
                        "clump_name": str(child.get("label") or clump_id).split(": ", 1)[-1],
                        "node_count": int(details.get("node_count") or 0),
                    }
                )

        self._preview_clumps_by_label.clear()
        labels: list[str] = []
        by_id: dict[int, str] = {}
        for row in rows:
            label = f"0x{int(row['clump_id']):X} {row['clump_name']} ({int(row['node_count'])} nodes)"
            labels.append(label)
            self._preview_clumps_by_label[label] = int(row["clump_id"])
            by_id[int(row["clump_id"])] = label
        if self.preview_clump_combo is not None:
            self.preview_clump_combo.configure(values=tuple(labels))
        if not rows:
            self.preview_clump_name.set("")
            self.preview_clump_status.set("No Clump records")
            return

        selected = max(rows, key=self._clump_choice_key)
        selected_id = int(selected["clump_id"])
        selected_label = by_id[selected_id]
        self.preview_clump_name.set(selected_label)
        self.preview_clump_status.set(f"Default 0x{selected_id:X}; {selected['node_count']} nodes")
        visual_row = self._selected_visual_row()
        if visual_row is not None:
            scene_v5.set_preferred_clump(visual_row["absolute_path"], selected_id)

    def _preview_clump_selected(self) -> None:
        row = self._selected_visual_row()
        label = self.preview_clump_name.get()
        clump_id = self._preview_clumps_by_label.get(label)
        if row is None or clump_id is None:
            return
        scene_v5.set_preferred_clump(row["absolute_path"], clump_id)
        self.preview_clump_status.set(f"Selected 0x{clump_id:X}; reloading clump instances")
        self._stop_animation()
        self._wireframe_load()


def main() -> int:
    app = PublicFragmenterAppV7()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

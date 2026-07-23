#!/usr/bin/env python3
"""V107 acceptance repairs for Run All, Gremlin introductions, and moved projects."""
from __future__ import annotations

import tkinter as tk
from typing import Any

from celdra_gremlin_art_v2 import draw_gremlin
from fragmenter_gremlin_scene_v106 import _OffsetCanvasProxyV106


class FragmenterAcceptanceRepairMixinV107:
    """Repair the three failures found in the first real V106 Windows run."""

    def __init__(self) -> None:
        self._run_progress_host_v107: tk.Misc | None = None
        super().__init__()
        self.after_idle(self._repair_run_progress_v107)

    # ------------------------------------------------------------------
    # V89 installed a scroll body in the original progress frame. V104 then
    # replaced that frame with its notebook/scroll host, leaving V89 pointing
    # at a destroyed widget. Adopt the final V104 body as the one authority.
    # ------------------------------------------------------------------
    def _adopt_run_progress_host_v107(self) -> bool:
        host = getattr(self, "stage_progress_frame", None)
        if host is None:
            return False
        try:
            if not host.winfo_exists():
                return False
        except (AttributeError, tk.TclError):
            return False

        self._run_progress_host_v107 = host
        self._stage_progress_body_v89 = host
        parent = getattr(host, "master", None)
        self._stage_progress_canvas_v89 = parent if isinstance(parent, tk.Canvas) else None
        self._stage_progress_window_v89 = None
        try:
            host.columnconfigure(0, weight=0)
            host.columnconfigure(1, weight=1)
            host.columnconfigure(2, weight=0)
        except tk.TclError:
            return False
        return True

    def _repair_run_progress_v107(self) -> None:
        if getattr(self, "project", None) is None:
            return
        if not self._adopt_run_progress_host_v107():
            return
        try:
            self._refresh_run_plan()
        except (AttributeError, tk.TclError) as exc:
            try:
                self._append_log(f"RUN ALL progress repair failed: {exc}")
            except (AttributeError, tk.TclError):
                pass

    def _build_run_all(self, parent) -> None:
        super()._build_run_all(parent)
        self.after_idle(self._repair_run_progress_v107)

    def _project_loaded(self) -> None:
        super()._project_loaded()
        self.after_idle(self._repair_run_progress_v107)
        project = getattr(self, "project", None)
        settings = getattr(project, "settings", {}) if project is not None else {}
        moved_from = str(settings.get("workspace_rebased_from") or "").strip() if isinstance(settings, dict) else ""
        if moved_from:
            self.status_label.set(
                "Project loaded. Its recorded workspace path was repaired from "
                f"{moved_from} to {project.workspace_dir}."
            )

    def _refresh_run_plan(self) -> None:
        self._adopt_run_progress_host_v107()
        super()._refresh_run_plan()
        host = self._run_progress_host_v107
        if host is not None:
            try:
                host.update_idletasks()
                canvas = self._stage_progress_canvas_v89
                if isinstance(canvas, tk.Canvas):
                    canvas.configure(scrollregion=canvas.bbox("all"))
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # V106 intentionally represents one Gremlin-sized region with a proxy over
    # the shared scene canvas. V103's renderer accepted only literal tk.Canvas
    # objects, so the introduction callbacks created records but drew nothing.
    # Render shared items directly through the proxy; external visitors continue
    # through the inherited literal-canvas path.
    # ------------------------------------------------------------------
    def _draw_personality_hatchling_v96(self, item: dict[str, Any], frame: Any) -> None:
        if not bool(item.get("shared_v106")):
            super()._draw_personality_hatchling_v96(item, frame)
            return

        canvas = getattr(self, "_gremlin_shared_canvas_v106", None)
        if not isinstance(canvas, tk.Canvas):
            return
        tag = str(item.get("tag_v106") or "")
        if not tag:
            return
        personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
        x = float(item.get("x") or 0.0)
        y = float(item.get("y") or 0.0)
        proxy = _OffsetCanvasProxyV106(
            canvas,
            tag=tag,
            x=x + float(item.get("art_offset_x") or 0.0),
            y=y + float(item.get("art_offset_y") or 0.0),
            width=int(item.get("art_width") or item.get("width") or 82),
            height=int(item.get("art_height") or item.get("height") or 88),
        )
        proxy.delete("all")
        draw_gremlin(
            proxy,
            personality,
            width=int(item.get("art_width") or item.get("width") or 82),
            height=int(item.get("art_height") or item.get("height") or 88),
            phase=int(item.get("phase") or item.get("frame") or 0),
            mood=str(item.get("mood") or "idle"),
            compact=bool(item.get("compact")),
            show_name=True,
        )
        item["drawn_x_v106"] = x
        item["drawn_y_v106"] = y
        item["drawn_mood_v106"] = str(item.get("mood") or "idle")

    def _introduce_internal_gremlin_v101(self, personality: dict[str, Any], index: int) -> None:
        super()._introduce_internal_gremlin_v101(personality, index)
        name = str(personality.get("name") or "").upper()
        item = getattr(self, "_celdra_middle_items_v101", {}).get(name)
        if isinstance(item, dict):
            self._draw_personality_hatchling_v96(item, None)

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V107"
            metadata["run_all_progress_host"] = "v104_final_scroll_body"
            metadata["gremlin_shared_proxy_rendering"] = True
            metadata["moved_project_workspace_repair"] = True
        return payload

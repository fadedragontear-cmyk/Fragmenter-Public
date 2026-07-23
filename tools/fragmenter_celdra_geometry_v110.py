#!/usr/bin/env python3
"""Final geometry authority for V110's Shy reveal and grounded residents."""
from __future__ import annotations

import tkinter as tk
from typing import Any


class FragmenterCeldraGeometryMixinV110:
    """Apply clipping-safe final coordinates after the broader V110 polish layer."""

    def _begin_shy_reveal_v64(self) -> None:
        self._hide_legacy_stagepieces_v110(hide_bubble=True)
        self._celdra_runtime_bubble_side_v87 = "above"
        self._celdra_runtime_stage_v87 = "center"
        self._celdra_external_offset_x_v65 = 0
        if not self._load_takeover_reaction_v58("shy"):
            return
        canvas = getattr(self, "celdra_avatar_canvas_v50", None)
        canvas_height = canvas.winfo_height() if canvas is not None else 420
        # Positive Y moves the centered image downward. Keep enough headroom for
        # the top bubble without pushing the 150% portrait through the lower edge.
        self._celdra_shy_rest_offset_v64 = max(54, min(76, canvas_height // 6))
        self._celdra_external_offset_y_v58 = max(330, canvas_height + 90)
        self._animate_stage_fraction_v54(0.50, 1_650)
        self._redraw_celdra_avatar_v50()
        if not self._v110_shy_core_announced:
            self._v110_shy_core_announced = True
            self._append_console_v49(
                "[CORE] SHY DRAGONGIRL CHANNEL STABLE // SPEECH LANE RESERVED ABOVE AVATAR"
            )
        self._remember_after_v49(260, self._start_shy_creep_v58)

    def _spawn_breakout_v108(self) -> None:
        super()._spawn_breakout_v108()
        # Departure targeting reads the live overlay dimensions immediately after
        # creation. Force one geometry pass so wide windows do not report 1x1.
        holder = getattr(self, "_gremlin_breakout_window_v108", None)
        canvas = getattr(self, "_gremlin_breakout_canvas_v108", None)
        try:
            if isinstance(holder, tk.Toplevel):
                holder.update_idletasks()
            if isinstance(canvas, tk.Canvas):
                canvas.update_idletasks()
        except tk.TclError:
            pass

    def _stable_position_v103(
        self,
        name: str,
        item: dict[str, Any],
        phase: int,
        width: int,
        height: int,
        iw: int,
        ih: int,
    ) -> tuple[float, float, bool]:
        folded = str(name or "").upper()
        left, top = 3.0, 3.0
        right = max(left, width - iw - 3.0)
        bottom = max(top, height - ih - 3.0)
        if folded == "CACHE":
            return left + 2.0, bottom, True
        if folded == "PATCH":
            cache = getattr(self, "_celdra_middle_items_v101", {}).get("CACHE")
            cache_width = int(cache.get("width") or 76) if isinstance(cache, dict) else 76
            # PATCH sits immediately beside CACHE on the lower-left floor. The
            # clamp preserves that pairing in the narrowest supported stable.
            return min(right, left + cache_width + 7.0), bottom, True
        return super()._stable_position_v103(folded, item, phase, width, height, iw, ih)

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["v110_geometry_authority"] = {
                "shy_rest_offset": "54_to_76_pixels",
                "grounded_pair": ["CACHE", "PATCH"],
                "departure_overlay_layout": "resolved_before_targeting",
            }
        return payload

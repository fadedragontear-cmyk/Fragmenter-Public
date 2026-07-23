#!/usr/bin/env python3
"""Single-pass Celdra dialogue wrapping and V103 cleanup hooks."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Any

from celdra_gremlin_memory_v1 import KNOWN_GREMLINS


class DragoneggSpeechMixinV103:
    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = getattr(self, "_celdra_speech_canvas_v63", None)
        if bubble is None: return
        cleaned = " ".join(str(text or "").split())
        self._remember_ambient_source_v88(cleaned)
        side, long_text = str(getattr(self, "_celdra_runtime_bubble_side_v87", "left")), len(cleaned) >= 150
        if self._celdra_yell_mode_v101 or long_text or side == "above": relx, rely, relwidth = .025, .018, .95
        elif side == "right": relx, rely, relwidth = .455, .055, .535
        else: relx, rely, relwidth = .010, .055, .535
        bubble.place(relx=relx, rely=rely, anchor="nw", relwidth=relwidth, height=120)
        bubble.update_idletasks()
        width = max(210, bubble.winfo_width())
        font = tkfont.Font(family="Consolas" if self._celdra_yell_mode_v101 else "Segoe UI",
                           size=12 if self._celdra_yell_mode_v101 else 10,
                           weight="bold" if self._celdra_yell_mode_v101 else "normal")
        line_count = len(self._balanced_lines_v101(cleaned, font, max(120, width-34)))
        required = 48 + line_count * max(18, font.metrics("linespace")+4)
        canvas = self.celdra_avatar_canvas_v50
        available = canvas.winfo_height() if canvas is not None else 420
        if required > available - 12:
            self._set_sash_fraction_v50(self.run_paned, .23)
            self.update_idletasks()
            available = canvas.winfo_height() if canvas is not None else max(available, required+12)
        height = max(108, min(max(required, 140), max(140, available-8), 430))
        bubble.place_configure(height=height); bubble.update_idletasks()
        width = max(210, bubble.winfo_width()); bubble.delete("all")
        if self._celdra_yell_mode_v101:
            points = [3,16,18,3,width-24,3,width-4,18,width-10,height-18,width-28,height-5,26,height-5,4,height-22]
            bubble.create_polygon(*points, fill=self.YELL_BACKGROUND, outline=self.YELL_BORDER, width=4)
            bubble.create_line(16,12,width-18,12,fill="#ff9aa6",width=2,dash=(10,4))
            bubble.create_text(width/2,height/2,text=cleaned.upper(),width=max(120,width-34),
                               fill="#ffffff",font=font,justify="center",anchor="center")
        else:
            self._draw_bubble_style_v81(bubble, (2,2,width-4,height-8), "Angular HUD", cleaned)
        try: bubble.tkraise()
        except (AttributeError, tk.TclError): pass

    def _prepare_first_run_surface_v51(self) -> None:
        self._destroy_internal_chaos_v103(); self._cancel_stable_status_v103()
        super()._prepare_first_run_surface_v51()

    def _cancel_celdra_cues_v49(self) -> None:
        self._destroy_internal_chaos_v103(); self._cancel_stable_status_v103()
        super()._cancel_celdra_cues_v49()

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V103"
            metadata["egg_first_startup"] = True
            metadata["main_gremlin_bounds"] = "run_all_tab_inside_fragmenter"
            metadata["individual_gremlin_bounds"] = "external_window_allowed"
            metadata["stable_status_gags"] = True
            metadata["stable_resident_motion"] = list(KNOWN_GREMLINS)
            metadata["dialogue_newline_policy"] = "single_tk_word_wrap"
        return payload

#!/usr/bin/env python3
"""V67: robust old-school cursor edits for disabled Tk text widgets."""
from __future__ import annotations

import tkinter as tk

from fragmenter_public_gui_v66 import PublicFragmenterAppV66


class PublicFragmenterAppV67(PublicFragmenterAppV66):
    """Unlock the conversational Text widget for every cursor mutation."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Maximum Corruption Presentation")

    @staticmethod
    def _remove_typewriter_cursor_v67(widget: tk.Text) -> bool:
        try:
            widget.configure(state="normal")
            ranges = widget.tag_ranges("v66_cursor")
            if len(ranges) >= 2:
                widget.delete(ranges[0], ranges[1])
            widget.tag_remove("v66_cursor", "1.0", "end")
            widget.configure(state="disabled")
            return True
        except tk.TclError:
            try:
                widget.configure(state="disabled")
            except tk.TclError:
                pass
            return False

    def _start_next_typewriter_v66(self) -> None:
        if not self._celdra_type_queue_v66:
            self._celdra_type_active_v66 = False
            return
        widget = self._celdra_chat_v49
        if widget is None:
            self._celdra_type_queue_v66.clear()
            self._celdra_type_active_v66 = False
            return

        self._celdra_type_active_v66 = True
        message, blink_count = self._celdra_type_queue_v66.pop(0)
        index = 0

        def finish_message() -> None:
            self._remove_typewriter_cursor_v67(widget)
            try:
                widget.configure(state="normal")
                widget.insert("end-1c", "\n\n")
                widget.see("end")
                widget.configure(state="disabled")
            except tk.TclError:
                self._celdra_type_active_v66 = False
                return
            self._celdra_type_active_v66 = False
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            self._celdra_type_after_v66 = self.after(
                max(20, round(120 * speed)),
                self._start_next_typewriter_v66,
            )

        def blink(toggle: int = 0) -> None:
            self._celdra_type_after_v66 = None
            visible = toggle % 2 == 0
            self._remove_typewriter_cursor_v67(widget)
            if visible:
                try:
                    widget.configure(state="normal")
                    widget.insert("end-1c", "_", "v66_cursor")
                    widget.tag_configure(
                        "v66_cursor",
                        foreground="#a9dcff",
                        font=("Consolas", 11, "bold"),
                    )
                    widget.see("end")
                    widget.configure(state="disabled")
                except tk.TclError:
                    self._celdra_type_active_v66 = False
                    return
            if toggle + 1 >= blink_count * 2:
                finish_message()
                return
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            self._celdra_type_after_v66 = self.after(
                max(70, round(220 * speed)),
                lambda: blink(toggle + 1),
            )

        def type_tick() -> None:
            nonlocal index
            self._celdra_type_after_v66 = None
            if index >= len(message):
                blink(0)
                return
            character = message[index]
            index += 1
            try:
                widget.configure(state="normal")
                widget.insert("end-1c", character)
                widget.see("end")
                widget.configure(state="disabled")
            except tk.TclError:
                self._celdra_type_active_v66 = False
                return
            speed = max(0.01, float(self._celdra_timeline_speed_v51))
            base = max(4, round(22 * speed))
            pause = max(5, round(72 * speed)) if character in ".!?" else 0
            self._celdra_type_after_v66 = self.after(base + pause, type_tick)

        type_tick()

    def _cancel_typewriter_v64(self) -> None:
        widget = self._celdra_chat_v49
        if widget is not None:
            self._remove_typewriter_cursor_v67(widget)
        super()._cancel_typewriter_v64()


def main() -> int:
    app = PublicFragmenterAppV67()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V113: consolidated RUN ALL layout and unified audio library/classifier."""
from __future__ import annotations

from fragmenter_layout_audio_v113 import FragmenterLayoutAudioMixinV113
from fragmenter_public_gui_v112 import PublicFragmenterAppV112
from snddata_sample_classification_v1 import available_categories, create_category


class PublicFragmenterAppV113(
    FragmenterLayoutAudioMixinV113,
    PublicFragmenterAppV112,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Consolidated Workspace V113")

    def _build_research_mixer_v40(self, parent) -> None:
        super()._build_research_mixer_v40(parent)
        self._audio_research_page_v98 = parent
        self._audio_sequence_search_entry_v98 = self._find_audio_search_entry_v98(parent)
        self._install_audio_shortcuts_v98()

    def _tab_changed_v40(self, event=None) -> None:
        super()._tab_changed_v40(event)
        if self.project is None or self._selected_tab_label_v40() != "Audio":
            return
        notebook = getattr(self, "audio_subnotebook_v47", None)
        if notebook is None:
            return
        try:
            label = str(notebook.tab(notebook.select(), "text"))
        except Exception:
            return
        if label == "Audio Library / Classifier":
            self.after_idle(self._refresh_audio_library_v113)

    def _ensure_audio_category_v113(self, category: str) -> None:
        project = self._require_project()
        if project is None or not str(category or "").strip():
            return
        if category not in available_categories(project):
            create_category(project, category)

    def _save_row_metadata_v113(self, row, *, preserve_label: bool) -> None:
        self._ensure_audio_category_v113(self._audio_library_category_v113.get())
        super()._save_row_metadata_v113(row, preserve_label=preserve_label)

    def _send_audio_category_v113(self, category: str) -> None:
        try:
            self._ensure_audio_category_v113(category)
        except Exception as exc:
            from tkinter import messagebox

            messagebox.showerror("Send to category", str(exc))
            return
        super()._send_audio_category_v113(category)

    def _initialize_audio_celdra_v98(self) -> None:
        # The dedicated mixer guide was removed in V113. Keep inherited callbacks
        # harmless instead of loading invisible pose artwork and tutorial state.
        self._audio_celdra_initialized_v98 = True

    def _audio_celdra_say_v98(self, title: str, body: str, pose: str = "smile") -> None:
        del title, body, pose


def main() -> int:
    app = PublicFragmenterAppV113()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

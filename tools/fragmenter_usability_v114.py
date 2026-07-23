#!/usr/bin/env python3
"""V114 usability pass for grouped audio, honest mixer evidence, and RUN ALL geometry."""
from __future__ import annotations

import tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from audio_library_research_v1 import merged_audio_rows


class FragmenterUsabilityMixinV114:
    """Keep the operator's place and stop diagnostic renders posing as mappings."""

    _AUDIO_HEADINGS_V114 = {
        "#0": "Audio",
        "type": "Type",
        "category": "Category",
        "rate": "Rate",
        "duration": "Duration",
        "usable": "Usability",
        "path": "Decoded path",
    }

    def __init__(self) -> None:
        self._audio_sort_column_v114 = "#0"
        self._audio_sort_reverse_v114 = False
        self._audio_category_nodes_v114: dict[str, str] = {}
        self._audio_open_categories_v114: set[str] = set()
        self._audio_pending_view_v114: float | None = None
        self._audio_suppress_follow_v114 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Consolidated Workspace V114")

    # ------------------------------------------------------------------
    # RUN ALL: guarantee direct-run visibility and reduce the Celdra footprint.
    # ------------------------------------------------------------------
    def _apply_default_celdra_layout_v50(self) -> None:
        super()._apply_default_celdra_layout_v50()
        # The left stage pane receives about 64% of the row. This moves the complete
        # Celdra panel right and reduces its width by roughly 28% from V113's 50/50.
        self._set_sash_fraction_v50(getattr(self, "run_bottom_split_v50", None), 0.64)
        self._set_sash_fraction_v50(getattr(self, "run_top_split_v50", None), 0.64)
        self.after_idle(self._apply_middle_layout_v101)

    def _apply_middle_layout_v101(self) -> None:
        pane = getattr(self, "celdra_visual_split_v50", None)
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        if pane is None or frame is None or bool(getattr(self, "_celdra_middle_hidden_v103", False)):
            return
        try:
            self.update_idletasks()
            panes = tuple(pane.panes())
            if len(panes) < 3:
                return
            width = max(520, int(pane.winfo_width()))
            # V113 reserved ~34% for the gremlin stable and ~30% for comms.
            # Reduce both by about one quarter while preserving minimum utility.
            stable_width = max(175, min(245, round(width * 0.255)))
            console_width = max(185, min(235, round(width * 0.225)))
            avatar_width = max(150, width - stable_width - console_width)
            if avatar_width + stable_width + console_width > width:
                stable_width = max(160, width - avatar_width - console_width)
            pane.sashpos(0, avatar_width)
            pane.sashpos(1, avatar_width + stable_width)
            self._stable_layout_applied_v112 = True
            self._stable_layout_signature_v112 = (round(width / 40) * 40, len(panes))
            wrap = max(145, stable_width - 18)
            for child in frame.winfo_children():
                if isinstance(child, (tk.Label, ttk.Label)):
                    try:
                        child.configure(wraplength=wrap, justify="left")
                    except tk.TclError:
                        pass
            status = getattr(self, "_stable_status_label_v109", None)
            if isinstance(status, tk.Label):
                status.configure(wraplength=wrap, justify="left", anchor="w", font=("Consolas", 7))
        except (AttributeError, tk.TclError):
            pass

    def _refresh_run_plan(self) -> None:
        super()._refresh_run_plan()
        frame = getattr(self, "stage_progress_frame", None)
        if frame is None:
            return
        try:
            frame.columnconfigure(0, weight=0)
            frame.columnconfigure(1, weight=0)
            frame.columnconfigure(2, weight=1)
            for row_index, key in enumerate(getattr(self, "_stage_order", ())):
                labels = [
                    widget
                    for widget in frame.grid_slaves(row=row_index)
                    if isinstance(widget, ttk.Label)
                ]
                button = getattr(self, "_stage_run_buttons_v38", {}).get(key)
                bar = getattr(self, "_stage_bars", {}).get(key)
                if button is not None:
                    button.grid_configure(row=row_index, column=0, sticky="w", padx=(0, 6), pady=2)
                if labels:
                    labels[0].configure(width=27, anchor="w")
                    labels[0].grid_configure(row=row_index, column=1, sticky="w", padx=(0, 6), pady=2)
                if bar is not None:
                    bar.configure(length=90)
                    bar.grid_configure(row=row_index, column=2, sticky="ew", pady=2)
        except (AttributeError, tk.TclError):
            pass

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        super()._run_all_done(result, error)
        failures: list[str] = []
        if error is not None:
            failures.append(f"{type(error).__name__}: {error}")
        if isinstance(result, dict):
            for row in result.get("results") or []:
                if not isinstance(row, dict) or str(row.get("status") or "") != "failed":
                    continue
                failures.append(
                    f"{row.get('label') or row.get('key') or 'stage'}: "
                    f"{row.get('message') or row.get('error') or 'failed'}"
                )
        if not failures:
            return
        report_path = str((result or {}).get("report_path") or "") if isinstance(result, dict) else ""
        lines = ["RUN ALL FAILURE SUMMARY", *failures]
        if report_path:
            lines.append(f"Report: {report_path}")
        try:
            self._append_log("\n" + "\n".join(lines) + "\n")
            self.overall_progress_label.set("Overall progress: failed - see final failure summary")
        except (AttributeError, tk.TclError):
            pass

    # ------------------------------------------------------------------
    # Audio Library: category parents, header sorting, and stable viewport.
    # ------------------------------------------------------------------
    def _build_audio_library_classifier_v113(self, parent: ttk.Frame) -> None:
        super()._build_audio_library_classifier_v113(parent)
        tree = getattr(self, "_audio_library_tree_v113", None)
        if tree is None:
            return
        for column, label in self._AUDIO_HEADINGS_V114.items():
            tree.heading(
                column,
                text=label,
                command=lambda selected=column: self._sort_audio_library_v114(selected),
            )
        tree.tag_configure("category_v114", font=("Segoe UI", 9, "bold"))
        self._update_audio_headings_v114()

    def _update_audio_headings_v114(self) -> None:
        tree = getattr(self, "_audio_library_tree_v113", None)
        if tree is None:
            return
        for column, label in self._AUDIO_HEADINGS_V114.items():
            suffix = ""
            if column == self._audio_sort_column_v114:
                suffix = " ▼" if self._audio_sort_reverse_v114 else " ▲"
            try:
                tree.heading(
                    column,
                    text=label + suffix,
                    command=lambda selected=column: self._sort_audio_library_v114(selected),
                )
            except tk.TclError:
                pass

    def _sort_audio_library_v114(self, column: str) -> None:
        if column == self._audio_sort_column_v114:
            self._audio_sort_reverse_v114 = not self._audio_sort_reverse_v114
        else:
            self._audio_sort_column_v114 = column
            self._audio_sort_reverse_v114 = False
        self._update_audio_headings_v114()
        self._refresh_audio_library_v113()

    @staticmethod
    def _audio_value_v114(row: dict[str, Any], column: str) -> Any:
        if column == "duration":
            return float(row.get("duration_estimate") or 0.0)
        if column == "rate":
            return int(row.get("sample_rate") or 0)
        if column == "type":
            return str(row.get("item_type") or "").casefold()
        if column == "category":
            return str(row.get("category") or "").casefold()
        if column == "usable":
            return str(row.get("usability") or "").casefold()
        if column == "path":
            return str(row.get("output_path") or "").casefold()
        return str(row.get("name") or "").casefold()

    def _capture_audio_tree_state_v114(self) -> tuple[set[str], float]:
        tree = getattr(self, "_audio_library_tree_v113", None)
        if tree is None:
            return set(), 0.0
        for iid, category in tuple(self._audio_category_nodes_v114.items()):
            try:
                if bool(tree.item(iid, "open")):
                    self._audio_open_categories_v114.add(category)
                else:
                    self._audio_open_categories_v114.discard(category)
            except tk.TclError:
                pass
        selected = {
            str(getattr(self, "_audio_library_rows_v113", {}).get(iid, {}).get("unified_key") or "")
            for iid in tree.selection()
        }
        try:
            view = float(tree.yview()[0])
        except (IndexError, tk.TclError):
            view = 0.0
        return {value for value in selected if value}, view

    def _refresh_audio_library_v113(self) -> None:
        project = getattr(self, "project", None)
        tree = getattr(self, "_audio_library_tree_v113", None)
        if project is None or tree is None:
            status = getattr(self, "_audio_library_status_v113", None)
            if status is not None:
                status.set("No project loaded")
            return

        selected_keys, current_view = self._capture_audio_tree_state_v114()
        preserve_selection = not self._audio_suppress_follow_v114
        self._audio_suppress_follow_v114 = False
        view = self._audio_pending_view_v114
        self._audio_pending_view_v114 = None
        if view is None:
            view = current_view

        self._audio_library_generation_v113 += 1
        generation = self._audio_library_generation_v113
        query = (
            self._audio_library_search_v113.get().strip().casefold()
            if self._audio_library_search_v113 is not None
            else ""
        )
        category_filter = (
            self._audio_library_category_filter_v113.get()
            if self._audio_library_category_filter_v113 is not None
            else "All"
        )
        item_type = (
            self._audio_library_type_filter_v113.get()
            if self._audio_library_type_filter_v113 is not None
            else "All"
        )
        if self._audio_library_status_v113 is not None:
            self._audio_library_status_v113.set("Loading grouped playable audio inventory…")

        def work() -> list[dict[str, Any]]:
            output: list[dict[str, Any]] = []
            for row in merged_audio_rows(project):
                haystack = " ".join(
                    str(row.get(key) or "")
                    for key in ("name", "category", "item_type", "output_path", "tags", "notes")
                ).casefold()
                if query and query not in haystack:
                    continue
                if category_filter != "All" and str(row.get("category") or "") != category_filter:
                    continue
                if item_type != "All" and str(row.get("item_type") or "") != item_type:
                    continue
                output.append(dict(row))
            return output

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._audio_library_generation_v113:
                return
            tree.delete(*tree.get_children())
            self._audio_library_rows_v113.clear()
            self._audio_category_nodes_v114.clear()
            if error:
                if self._audio_library_status_v113 is not None:
                    self._audio_library_status_v113.set(f"Audio inventory failed: {error}")
                return

            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows or []:
                grouped[str(row.get("category") or "Unclassified")].append(row)
            categories = sorted(grouped, key=str.casefold, reverse=(
                self._audio_sort_column_v114 == "category" and self._audio_sort_reverse_v114
            ))
            if category_filter != "All":
                self._audio_open_categories_v114.add(category_filter)
            if not self._audio_open_categories_v114 and categories:
                self._audio_open_categories_v114.add(categories[0])

            restored: list[str] = []
            row_serial = 0
            for category_index, category in enumerate(categories):
                parent_iid = f"audio_category_v114_{category_index}"
                tree.insert(
                    "",
                    "end",
                    iid=parent_iid,
                    text=f"{category} ({len(grouped[category]):,})",
                    values=("", category, "", "", "", ""),
                    open=category in self._audio_open_categories_v114,
                    tags=("category_v114",),
                )
                self._audio_category_nodes_v114[parent_iid] = category
                children = sorted(
                    grouped[category],
                    key=lambda row: (
                        self._audio_value_v114(row, self._audio_sort_column_v114),
                        str(row.get("name") or "").casefold(),
                        str(row.get("output_path") or "").casefold(),
                    ),
                    reverse=self._audio_sort_reverse_v114,
                )
                for row in children:
                    iid = f"audio_v114_{row_serial}"
                    row_serial += 1
                    rate = int(row.get("sample_rate") or 0)
                    duration = float(row.get("duration_estimate") or 0.0)
                    usability = str(row.get("usability") or "Unreviewed")
                    tree.insert(
                        parent_iid,
                        "end",
                        iid=iid,
                        text=str(row.get("name") or Path(str(row.get("output_path") or "audio.wav")).name),
                        values=(
                            str(row.get("item_type") or ""),
                            category,
                            f"{rate:,} Hz" if rate else "—",
                            f"{duration:.3f}s",
                            usability,
                            str(row.get("output_path") or ""),
                        ),
                        tags=(usability,),
                    )
                    self._audio_library_rows_v113[iid] = row
                    if preserve_selection and str(row.get("unified_key") or "") in selected_keys:
                        restored.append(iid)

            self._sync_audio_categories_v113(list(rows or []))
            if restored:
                tree.selection_set(restored)
                tree.focus(restored[0])
            elif preserve_selection and tree.get_children(""):
                first_parent = tree.get_children("")[0]
                first_children = tree.get_children(first_parent)
                if first_children:
                    tree.selection_set(first_children[0])
                    tree.focus(first_children[0])
            try:
                tree.yview_moveto(max(0.0, min(1.0, float(view))))
            except (TypeError, ValueError, tk.TclError):
                pass
            self._audio_library_selected_v113()
            if self._audio_library_status_v113 is not None:
                samples = sum(str(row.get("item_type")) == "SNDDATA Sample" for row in rows or [])
                direct = len(rows or []) - samples
                self._audio_library_status_v113.set(
                    f"{len(rows or []):,} unique playable rows in {len(categories):,} collapsible categories: "
                    f"{samples:,} SNDDATA samples, {direct:,} other WAVs."
                )

        self._local_worker("grouped-audio-library-v114", work, done)

    def _audio_library_double_click_v113(self, event: tk.Event) -> str:
        tree = getattr(self, "_audio_library_tree_v113", None)
        if tree is None:
            return "break"
        iid = tree.identify_row(event.y)
        category = self._audio_category_nodes_v114.get(iid)
        if category is not None:
            opened = not bool(tree.item(iid, "open"))
            tree.item(iid, open=opened)
            if opened:
                self._audio_open_categories_v114.add(category)
            else:
                self._audio_open_categories_v114.discard(category)
            return "break"
        return super()._audio_library_double_click_v113(event)

    def _audio_library_context_menu_v113(self, event: tk.Event) -> str:
        tree = getattr(self, "_audio_library_tree_v113", None)
        if tree is None:
            return "break"
        iid = tree.identify_row(event.y)
        category = self._audio_category_nodes_v114.get(iid)
        if category is None:
            return super()._audio_library_context_menu_v113(event)
        menu = tk.Menu(self, tearoff=False)
        opened = bool(tree.item(iid, "open"))
        menu.add_command(
            label="Collapse Category" if opened else "Expand Category",
            command=lambda: tree.item(iid, open=not opened),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _prepare_audio_move_v114(self) -> None:
        tree = getattr(self, "_audio_library_tree_v113", None)
        if tree is not None:
            try:
                self._audio_pending_view_v114 = float(tree.yview()[0])
            except (IndexError, tk.TclError):
                self._audio_pending_view_v114 = 0.0
        self._audio_suppress_follow_v114 = True

    def _send_audio_category_v113(self, category: str) -> None:
        self._prepare_audio_move_v114()
        super()._send_audio_category_v113(category)

    def _save_audio_metadata_v113(self) -> None:
        self._prepare_audio_move_v114()
        super()._save_audio_metadata_v113()

    # ------------------------------------------------------------------
    # Mixer: explain the real task and prevent false-positive canonization.
    # ------------------------------------------------------------------
    @staticmethod
    def _descendants_v114(widget: tk.Misc):
        for child in widget.winfo_children():
            yield child
            yield from FragmenterUsabilityMixinV114._descendants_v114(child)

    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        super()._build_research_mixer_v40(parent)
        for child in tuple(parent.winfo_children()):
            try:
                info = child.grid_info()
                if info:
                    child.grid_configure(row=int(info.get("row") or 0) + 1)
            except (TypeError, ValueError, tk.TclError):
                pass
        parent.rowconfigure(2, weight=0)
        parent.rowconfigure(3, weight=1)
        guide = ttk.LabelFrame(parent, text="What this page can currently prove", padding=(7, 5))
        guide.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        guide.columnconfigure(0, weight=1)
        ttk.Label(
            guide,
            text=(
                "Select a sequence to inspect decoded note timing and candidate Program banks. "
                "\"Missing Programs\" usually means the routing interpretation does not fit the parsed bank; "
                "it does not mean the WAV catalog is absent. A green renderer-complete row only has enough "
                "inputs for a diagnostic preview. It is not authentic music until compared with the game or emulator."
            ),
            wraplength=1180,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            guide,
            text=(
                "Recommended order: rebuild the mixer index after this update, inspect short strict parses first, "
                "play required samples, then render only as a diagnostic. Plausible/Confirm are disabled for now."
            ),
            wraplength=1180,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(3, 0))

        for child in self._descendants_v114(parent):
            if not isinstance(child, ttk.Button):
                continue
            try:
                text = str(child.cget("text"))
            except tk.TclError:
                continue
            if text == "Plausible":
                child.configure(text="Plausible (disabled)", state="disabled")
            elif text == "Confirm Mapping":
                child.configure(text="Confirm (disabled)", state="disabled")
        if getattr(self, "audio_readiness_v40", None) is not None:
            self.audio_readiness_v40.set(
                "Diagnostic mixer only. Rebuild the index to apply strict 7-bit event validation."
            )

    def _review_candidate_v40(self, status: str) -> None:
        if status in {"plausible", "confirmed"}:
            messagebox.showinfo(
                "SNDDATA diagnostic preview",
                "This renderer is not yet authoritative enough to mark a mapping plausible or confirmed. "
                "Use the notes field while auditioning, or reject a clearly incorrect candidate. "
                "Confirmation will return after an emulator/game comparison path exists.",
            )
            return
        super()._review_candidate_v40(status)

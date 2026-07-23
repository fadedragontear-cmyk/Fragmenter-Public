#!/usr/bin/env python3
"""V48: corrected sample boundaries, PSound comparison IDs, and explicit multitrack mixing."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import fragmenter_public_gui_v47 as gui_v47
from fragmenter_public_gui import _json_text, _open_path, _replace_text
from fragmenter_public_gui_v47 import PublicFragmenterAppV47
from original_sequencer_v1 import save_state as save_sequencer_state
from original_sequencer_v2 import parts_from_parsed, render_midi_project
from snddata_sample_classification_v1 import classified_sample_rows
from snddata_sample_health_v1 import sample_library_health

# V47's inherited render callback resolves this module global at runtime. Replace it
# before the class is instantiated so all mapped MIDI parts mix through v2.
gui_v47.render_midi_project = render_midi_project


class PublicFragmenterAppV48(PublicFragmenterAppV47):
    """Keep the three audio workspaces synchronized around corrected sample metadata."""

    def __init__(self) -> None:
        self.sequencer_part_enabled_v48: tk.BooleanVar | None = None
        self.sequencer_part_muted_v48: tk.BooleanVar | None = None
        self.sequencer_part_solo_v48: tk.BooleanVar | None = None
        self.classifier_boundary_v48: tk.StringVar | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Corrected Samples + Multitrack Sequencer")

    # ------------------------------------------------------------------
    # Research Mixer: boundary/catalog diagnostics stay beside sequence research.
    # ------------------------------------------------------------------
    def _build_research_mixer_v40(self, parent: ttk.Frame) -> None:
        super()._build_research_mixer_v40(parent)
        controls = next(
            (child for child in parent.winfo_children() if isinstance(child, ttk.Frame)),
            None,
        )
        if controls is None:
            return
        ttk.Button(
            controls,
            text="Sample Boundary Audit",
            command=self._show_sample_boundary_audit_v48,
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            controls,
            text="Open Corrected Samples",
            command=self._open_corrected_samples_v48,
        ).pack(side="right", padx=(6, 0))

    def _show_sample_boundary_audit_v48(self) -> None:
        project = self._require_project()
        if project is None:
            return
        health = sample_library_health(project)
        _replace_text(self.audio_details, _json_text(health))
        if self.audio_research_tabs_v46 is not None:
            self.audio_research_tabs_v46.select(0)
        summary = health.get("summary") or {}
        self.audio_status.set(
            "Sample boundary audit: "
            f"{int(summary.get('phase_corrected_banks') or 0)} corrected banks, "
            f"{int(summary.get('flat_unique_source_spans') or 0)} flat unique spans, "
            f"{int(summary.get('duplicate_stream_aliases') or 0)} bank aliases."
        )

    def _open_corrected_samples_v48(self) -> None:
        project = self._require_project()
        if project is None:
            return
        health = sample_library_health(project)
        root = Path(str((health.get("paths") or {}).get("root") or ""))
        if not root.is_dir():
            messagebox.showinfo(
                "Corrected SNDDATA samples",
                "The corrected sample library is not present yet. Run Extract SNDDATA Samples on the Audio Pipeline tab.",
            )
            return
        _open_path(root)

    # ------------------------------------------------------------------
    # Sample Classifier: expose flat comparison IDs and boundary provenance.
    # ------------------------------------------------------------------
    def _build_sample_classifier_v47(self, parent: ttk.Frame) -> None:
        super()._build_sample_classifier_v47(parent)
        tree = self.classifier_tree_v47
        current = tuple(tree.cget("columns"))
        tree.configure(columns=("flat", *current))
        tree.heading(
            "flat",
            text="Flat / PSound compare",
            command=lambda: self._sort_tree_v46(tree, "flat", True),
        )
        tree.column("flat", width=110, stretch=False)

        editor = self._find_label_frame_v48(parent, "Classification / instrument metadata")
        if editor is not None:
            self.classifier_boundary_v48 = tk.StringVar(
                value="Boundary and flat-index metadata appears after selecting a sample."
            )
            ttk.Label(
                editor,
                textvariable=self.classifier_boundary_v48,
                wraplength=460,
            ).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(7, 0))

    def _refresh_sample_classifier_v47(self) -> None:
        project = self.project
        if project is None or not hasattr(self, "classifier_tree_v47"):
            return
        query = self.classifier_search_v47.get()
        category = self.classifier_category_filter_v47.get()
        usability = self.classifier_usability_filter_v47.get()
        self.classifier_status_v47.set("Loading corrected normalized sample inventory…")

        def done(rows: Any, error: Exception | None) -> None:
            if error:
                self.classifier_status_v47.set(f"Sample classifier failed: {error}")
                return
            tree = self.classifier_tree_v47
            tree.delete(*tree.get_children())
            self.classifier_rows_v47.clear()
            for index, row in enumerate(rows):
                iid = f"classifier_{index}"
                resource = int(row.get("resource_offset") or 0)
                sample_id = int(row.get("sample_id") or 0)
                flat = row.get("flat_index")
                flat_text = f"{int(flat):04d}" if flat is not None else "—"
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=str(row.get("classification_label") or row.get("display_name")),
                    values=(
                        flat_text,
                        f"0x{resource:X}",
                        f"{sample_id:04d}",
                        f"{int(row.get('sample_rate') or 0):,}",
                        f"{float(row.get('duration_estimate') or 0.0):.3f}s",
                        row.get("category"),
                        row.get("playback_mode"),
                        row.get("root_note"),
                        row.get("usability"),
                    ),
                    tags=(str(row.get("usability") or "Unreviewed"),),
                )
                self.classifier_rows_v47[iid] = row
            tree.tag_configure("Usable", foreground="#147a36")
            tree.tag_configure("Questionable", foreground="#a05a00")
            tree.tag_configure("Reject", foreground="#9b1c1c")
            flat_count = sum(row.get("flat_index") is not None for row in rows)
            self.classifier_status_v47.set(
                f"{len(rows)} bank-local sample assets shown; {flat_count} have flat comparison IDs."
            )

        self._local_worker(
            "snddata-sample-classifier-v48",
            lambda: classified_sample_rows(
                project,
                query=query,
                category=category,
                usability=usability,
            ),
            done,
        )

    def _classifier_selected_v47(self) -> None:
        super()._classifier_selected_v47()
        row = self._selected_classifier_row_v47()
        if row is None or self.classifier_boundary_v48 is None:
            return
        flat = row.get("flat_index")
        phase = int(row.get("stream_phase_shift") or 0)
        aliases = int(row.get("source_span_alias_count") or 1)
        source_start = int(row.get("source_span_start") or row.get("source_offset") or 0)
        source_end = int(
            row.get("source_span_end")
            or source_start + int(row.get("raw_size") or 0)
        )
        text = (
            f"Flat comparison ID: {int(flat):04d}"
            if flat is not None
            else "Flat comparison ID: unavailable; rebuild corrected samples."
        )
        self.classifier_boundary_v48.set(
            text
            + f"  •  source 0x{source_start:X}–0x{source_end:X}"
            + f"  •  phase +0x{phase:X}"
            + f"  •  {aliases} bank-local reference{'s' if aliases != 1 else ''}"
        )

    # ------------------------------------------------------------------
    # Original Sequencer: each MIDI track/channel part is independently mapped.
    # ------------------------------------------------------------------
    def _build_original_sequencer_v47(self, parent: ttk.Frame) -> None:
        self.sequencer_part_enabled_v48 = tk.BooleanVar(value=True)
        self.sequencer_part_muted_v48 = tk.BooleanVar(value=False)
        self.sequencer_part_solo_v48 = tk.BooleanVar(value=False)
        super()._build_original_sequencer_v47(parent)

        tree = self.sequencer_channel_tree_v47
        tree.configure(columns=("track", "notes", "programs", "range", "state", "sample"))
        for key, label, width, stretch in (
            ("track", "MIDI track", 170, True),
            ("notes", "Notes", 60, False),
            ("programs", "Programs", 90, False),
            ("range", "Range", 75, False),
            ("state", "Mix", 70, False),
            ("sample", "Assigned classified instrument", 300, True),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=stretch)
        tree.heading("#0", text="Part")
        tree.column("#0", width=90, stretch=False)

        mapping = self._find_label_frame_v48(parent, "Selected channel sample mapping")
        if mapping is not None:
            state = ttk.LabelFrame(mapping, text="Multitrack state", padding=5)
            state.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(7, 0))
            ttk.Checkbutton(
                state,
                text="Enabled",
                variable=self.sequencer_part_enabled_v48,
            ).pack(side="left")
            ttk.Checkbutton(
                state,
                text="Mute",
                variable=self.sequencer_part_muted_v48,
            ).pack(side="left", padx=(8, 0))
            ttk.Checkbutton(
                state,
                text="Solo",
                variable=self.sequencer_part_solo_v48,
            ).pack(side="left", padx=(8, 0))
            ttk.Button(
                state,
                text="Clear All Solo/Mute",
                command=self._clear_multitrack_states_v48,
            ).pack(side="right")

        for button in self._descendants_v48(parent, ttk.Button):
            try:
                text = str(button.cget("text"))
            except tk.TclError:
                continue
            if text == "Render & Play":
                button.configure(text="Render & Play All Active Parts")
            elif text == "Auto-map Unassigned":
                button.configure(text="Auto-map Unassigned Parts")

    def _populate_sequencer_channels_v47(self) -> None:
        tree = self.sequencer_channel_tree_v47
        tree.delete(*tree.get_children())
        self.sequencer_channel_rows_v47.clear()
        for row in parts_from_parsed(self.sequencer_parsed_v47 or {}):
            key = str(row["key"])
            iid = key.replace(":", "_")
            mapping = self.sequencer_channel_mappings_v47.get(key) or {}
            if not mapping:
                mapping = self.sequencer_channel_mappings_v47.get(str(row["channel"])) or {}
            if not bool(mapping.get("enabled", True)):
                state = "Off"
            elif bool(mapping.get("muted")):
                state = "Mute"
            elif bool(mapping.get("solo")):
                state = "Solo"
            else:
                state = "Active"
            tree.insert(
                "",
                "end",
                iid=iid,
                text=f"T{int(row['track_index']) + 1} / C{int(row['channel']) + 1}",
                values=(
                    row.get("track_name"),
                    row.get("note_count"),
                    ", ".join(str(value) for value in row.get("programs") or []) or "—",
                    f"{row.get('lowest_note')}–{row.get('highest_note')}",
                    state,
                    mapping.get("label") or "Unassigned",
                ),
            )
            self.sequencer_channel_rows_v47[iid] = row
        first = next(iter(self.sequencer_channel_rows_v47), None)
        if first:
            tree.selection_set(first)
            tree.focus(first)
            self._sequencer_channel_selected_v47()

    def _selected_part_v48(self) -> dict[str, Any] | None:
        selected = self.sequencer_channel_tree_v47.selection()
        return self.sequencer_channel_rows_v47.get(selected[0]) if selected else None

    def _selected_sequencer_channel_v47(self) -> int | None:
        part = self._selected_part_v48()
        return int(part.get("channel") or 0) if part is not None else None

    def _selected_mapping_key_v48(self) -> str | None:
        part = self._selected_part_v48()
        return str(part.get("key")) if part is not None else None

    def _sequencer_channel_selected_v47(self) -> None:
        part = self._selected_part_v48()
        if part is None:
            return
        key = str(part["key"])
        mapping = self.sequencer_channel_mappings_v47.get(key) or {}
        if not mapping:
            mapping = self.sequencer_channel_mappings_v47.get(str(part["channel"])) or {}
        choice = ""
        sample_key = str(mapping.get("key") or "")
        for label, row in self.sequencer_sample_choices_v47.items():
            if str(row.get("key") or "") == sample_key:
                choice = label
                break
        self.sequencer_sample_choice_v47.set(choice)
        self.sequencer_mode_v47.set(str(mapping.get("playback_mode") or "Pitched"))
        self.sequencer_root_v47.set(
            int(mapping.get("root_note") if mapping.get("root_note") is not None else 60)
        )
        self.sequencer_transpose_v47.set(int(mapping.get("transpose") or 0))
        self.sequencer_channel_gain_v47.set(
            float(mapping.get("gain") if mapping.get("gain") is not None else 1.0)
        )
        self.sequencer_pan_v47.set(
            int(mapping.get("pan") if mapping.get("pan") is not None else 64)
        )
        if self.sequencer_part_enabled_v48 is not None:
            self.sequencer_part_enabled_v48.set(bool(mapping.get("enabled", True)))
        if self.sequencer_part_muted_v48 is not None:
            self.sequencer_part_muted_v48.set(bool(mapping.get("muted")))
        if self.sequencer_part_solo_v48 is not None:
            self.sequencer_part_solo_v48.set(bool(mapping.get("solo")))

    def _mapping_from_sample_v47(self, row: dict[str, Any]) -> dict[str, Any]:
        mapping = super()._mapping_from_sample_v47(row)
        mapping.update(
            {
                "enabled": bool(
                    self.sequencer_part_enabled_v48.get()
                    if self.sequencer_part_enabled_v48 is not None
                    else True
                ),
                "muted": bool(
                    self.sequencer_part_muted_v48.get()
                    if self.sequencer_part_muted_v48 is not None
                    else False
                ),
                "solo": bool(
                    self.sequencer_part_solo_v48.get()
                    if self.sequencer_part_solo_v48 is not None
                    else False
                ),
            }
        )
        return mapping

    def _save_channel_mapping_v47(self) -> None:
        project = self._require_project()
        key = self._selected_mapping_key_v48()
        row = self.sequencer_sample_choices_v47.get(self.sequencer_sample_choice_v47.get())
        if project is None or key is None or row is None:
            messagebox.showinfo(
                "Original Sequencer",
                "Select a MIDI track/channel part and a classified sample first.",
            )
            return
        self.sequencer_channel_mappings_v47[key] = self._mapping_from_sample_v47(row)
        save_sequencer_state(
            project,
            midi_path=self.sequencer_midi_path_v47.get(),
            channel_mappings=self.sequencer_channel_mappings_v47,
        )
        self._populate_sequencer_channels_v47()
        self.sequencer_status_v47.set(
            f"Mapped {key} to {row.get('classification_label')}; all active parts render together."
        )

    def _auto_map_channels_v47(self) -> None:
        project = self._require_project()
        parsed = self.sequencer_parsed_v47 or {}
        if project is None or not parsed:
            return
        rows = list(self.sequencer_sample_choices_v47.values())
        if not rows:
            messagebox.showinfo(
                "Original Sequencer",
                "Classify at least one playable sample first.",
            )
            return
        melodic = next(
            (
                row
                for row in rows
                if row.get("playback_mode") == "Pitched"
                and row.get("usability") in {"Usable", "Unreviewed"}
            ),
            rows[0],
        )
        drum = next(
            (
                row
                for row in rows
                if row.get("playback_mode") == "Drum"
                or row.get("category") == "Percussion"
            ),
            melodic,
        )
        for part in parts_from_parsed(parsed):
            key = str(part["key"])
            if key in self.sequencer_channel_mappings_v47:
                continue
            row = drum if int(part["channel"]) == 9 else melodic
            self.sequencer_channel_mappings_v47[key] = {
                "key": row.get("key"),
                "resource_offset": int(row.get("resource_offset") or 0),
                "sample_id": int(row.get("sample_id") or 0),
                "flat_index": row.get("flat_index"),
                "label": str(
                    row.get("classification_label") or row.get("display_name") or ""
                ),
                "output_path": str(row.get("output_path") or ""),
                "sample_rate": int(row.get("sample_rate") or 0),
                "playback_mode": (
                    "Drum"
                    if int(part["channel"]) == 9
                    else str(row.get("playback_mode") or "Pitched")
                ),
                "root_note": int(row.get("root_note") or 60),
                "transpose": 0,
                "gain": 1.0,
                "pan": 64,
                "enabled": True,
                "muted": False,
                "solo": False,
            }
        save_sequencer_state(
            project,
            midi_path=self.sequencer_midi_path_v47.get(),
            channel_mappings=self.sequencer_channel_mappings_v47,
        )
        self._populate_sequencer_channels_v47()
        self.sequencer_status_v47.set(
            "Auto-mapped every unassigned MIDI track/channel part. All active parts render simultaneously."
        )

    def _play_assigned_sample_v47(self) -> None:
        key = self._selected_mapping_key_v48()
        mapping = self.sequencer_channel_mappings_v47.get(key or "")
        path = Path(str((mapping or {}).get("output_path") or ""))
        if not path.is_file():
            return
        try:
            self.playback.load(path)
            self.playback.play()
        except Exception as exc:
            messagebox.showerror("Original Sequencer", str(exc))

    def _clear_multitrack_states_v48(self) -> None:
        project = self._require_project()
        if project is None:
            return
        for mapping in self.sequencer_channel_mappings_v47.values():
            if isinstance(mapping, dict):
                mapping["enabled"] = True
                mapping["muted"] = False
                mapping["solo"] = False
        save_sequencer_state(
            project,
            midi_path=self.sequencer_midi_path_v47.get(),
            channel_mappings=self.sequencer_channel_mappings_v47,
        )
        self._populate_sequencer_channels_v47()
        self.sequencer_status_v47.set("All mapped MIDI parts enabled; mute and solo cleared.")

    # ------------------------------------------------------------------
    # Small widget helpers.
    # ------------------------------------------------------------------
    def _find_label_frame_v48(
        self, widget: tk.Misc, text: str
    ) -> ttk.LabelFrame | None:
        for child in widget.winfo_children():
            if isinstance(child, ttk.LabelFrame):
                try:
                    if str(child.cget("text")) == text:
                        return child
                except tk.TclError:
                    pass
            found = self._find_label_frame_v48(child, text)
            if found is not None:
                return found
        return None

    def _descendants_v48(self, widget: tk.Misc, kind: type) -> list[Any]:
        output: list[Any] = []
        for child in widget.winfo_children():
            if isinstance(child, kind):
                output.append(child)
            output.extend(self._descendants_v48(child, kind))
        return output


def main() -> int:
    app = PublicFragmenterAppV48()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

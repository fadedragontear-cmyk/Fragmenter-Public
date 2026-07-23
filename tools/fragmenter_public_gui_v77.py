#!/usr/bin/env python3
"""V77: scroll-safe authoring tabs, reusable pose presets, and real-viewport previews."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from celdra_authoring_project_v1 import normalize_event, normalize_events
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v76 import PublicFragmenterAppV76


class PublicFragmenterAppV77(PublicFragmenterAppV76):
    """Keep authoring controls reachable and preview them on the production surface."""

    def __init__(self) -> None:
        self._celdra_pose_presets_v77: list[dict[str, Any]] = []
        self._celdra_preset_rows_v77: dict[str, dict[str, Any]] = {}
        self._celdra_preset_tree_v77: ttk.Treeview | None = None
        self._celdra_preset_name_v77: tk.StringVar | None = None
        self._celdra_preset_time_v77: tk.IntVar | None = None
        self._celdra_preset_move_v77: tk.IntVar | None = None
        self._celdra_preset_sequence_v77: tk.StringVar | None = None
        self._celdra_preset_serial_v77 = 0
        self._celdra_main_preview_refs_v77: list[tk.PhotoImage] = []
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Authoring Workspace")

    # ------------------------------------------------------------------
    # Strict text-only corruption. Remove every inherited glitch decoration.
    # ------------------------------------------------------------------
    def _draw_egg_glitch_v61(self, canvas: tk.Canvas, width: int, height: int) -> None:
        level = int(getattr(self, "_celdra_glitch_level_v61", 0) or 0)
        if level <= 0:
            return
        phase = int(getattr(self, "_celdra_glitch_phase_v61", 0) or 0)
        alarm = bool(getattr(self, "_celdra_instability_red_v70", False))
        tag = "v77_plain_floating_text"

        known_tags = (
            "v61_glitch",
            "v63_glitch",
            "v64_text_glitch",
            "v66_corrupt_field",
            "v68_green_corruption_bg",
            "v70_white_corruption_haze",
            "v74_text_only_corruption",
            tag,
        )
        for old_tag in known_tags:
            try:
                canvas.delete(old_tag)
            except tk.TclError:
                pass
        try:
            for item in canvas.find_all():
                tags = " ".join(canvas.gettags(item)).casefold()
                if any(token in tags for token in ("glitch", "corrupt", "haze", "signal_node", "orbit")):
                    canvas.delete(item)
        except tk.TclError:
            pass

        terms = (
            "AURA",
            "INFECTION",
            "MUTATION",
            "QUARANTINE",
            "SERENIAL",
            "CELDRA",
            "FRAGMENT",
            "CCSF",
        )
        green = ("#06371f", "#07512a", "#096b36", "#0d8644", "#13a754", "#25c96b")
        red = ("#4b070d", "#681016", "#86151e", "#a91d29", "#d12b38", "#f24d58")
        palette = red if alarm else green
        density = 10 + level * 9
        usable_width = max(90, width - 34)
        usable_height = max(90, height - 104)

        for slot in range(density):
            term = terms[(slot * 5 + phase // 3 + level) % len(terms)]
            binary = "".join(f"{ord(character):08b}" for character in term)
            mode = (slot + phase) % 6
            if mode == 0:
                text = term
            elif mode == 1:
                text = term[::-1]
            elif mode == 2:
                start = (phase * 7 + slot * 11) % max(1, len(binary))
                text = (binary[start:] + binary[:start])[: 12 + level * 7]
            elif mode == 3:
                text = f"{term[: max(1, len(term) - level)]}//{(phase * 29 + slot * 17) & 0xFF:02X}"
            elif mode == 4:
                replacements = "01?/\\ΔΞ#"
                text = "".join(
                    character
                    if (index + slot + phase) % max(2, 6 - level)
                    else replacements[(index + slot + phase) % len(replacements)]
                    for index, character in enumerate(term)
                )
            else:
                text = " ".join(f"{ord(character):02X}" for character in term)

            x = 17 + ((slot * 101 + phase * (3 + slot % 7)) % usable_width)
            y = 50 + ((slot * 67 + phase * (4 + slot % 9)) % usable_height)
            size = 7 + ((slot * 3 + phase + level) % (4 + level))
            try:
                canvas.create_text(
                    x,
                    y,
                    text=text,
                    anchor="center",
                    fill=palette[(slot + phase) % len(palette)],
                    font=("Fixedsys", size),
                    tags=tag,
                )
            except tk.TclError:
                continue
        try:
            canvas.tag_lower(tag)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Scroll hosts keep every authoring control reachable at any DPI.
    # ------------------------------------------------------------------
    def _scroll_host_v77(self, parent: ttk.Frame, *, row: int) -> ttk.Frame:
        parent.rowconfigure(row, weight=1)
        parent.columnconfigure(0, weight=1)
        canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0, background="#10151d")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=row, column=0, sticky="nsew")
        scrollbar.grid(row=row, column=1, sticky="ns")
        body = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def update_region(_event: tk.Event | None = None) -> None:
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except tk.TclError:
                pass

        def fit_width(event: tk.Event) -> None:
            try:
                canvas.itemconfigure(window_id, width=max(1, int(event.width)))
                update_region()
            except tk.TclError:
                pass

        def wheel(event: tk.Event) -> str:
            try:
                delta = -1 if int(event.delta) > 0 else 1
                canvas.yview_scroll(delta * 3, "units")
            except (AttributeError, tk.TclError, ValueError):
                pass
            return "break"

        body.bind("<Configure>", update_region)
        canvas.bind("<Configure>", fit_width)
        canvas.bind("<MouseWheel>", wheel)
        body.bind("<MouseWheel>", wheel)
        return body

    # ------------------------------------------------------------------
    # Preview / Poses: fixed actions, scrollable editor, reusable presets.
    # ------------------------------------------------------------------
    def _build_author_preview_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        for label, command in (
            ("Render here", self._preview_pose_embedded_v74),
            ("Preview current in main viewport", self._preview_current_in_main_v77),
            ("Play editable timeline here", self._play_author_timeline_v74),
            ("Play canonical timeline in main viewport (20×)", self._preview_canonical_main_v77),
            ("Preview egg corruption / climax in main", self._preview_egg_main_v77),
        ):
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 4))

        body = self._scroll_host_v77(parent, row=1)
        super()._build_author_preview_tab_v74(body)
        preset_box = ttk.LabelFrame(body, text="Reusable pose + dialogue presets", padding=6)
        preset_box.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._build_pose_presets_v77(preset_box)

    def _build_pose_presets_v77(self, parent: ttk.LabelFrame) -> None:
        parent.columnconfigure(0, weight=1)
        form = ttk.Frame(parent)
        form.grid(row=0, column=0, sticky="ew")
        self._celdra_preset_name_v77 = tk.StringVar(value="Celdra beat")
        self._celdra_preset_time_v77 = tk.IntVar(value=0)
        self._celdra_preset_move_v77 = tk.IntVar(value=650)
        self._celdra_preset_sequence_v77 = tk.StringVar(value="main")
        for column, (label, variable, width) in enumerate(
            (
                ("Preset name", self._celdra_preset_name_v77, 22),
                ("At ms", self._celdra_preset_time_v77, 10),
                ("Move ms", self._celdra_preset_move_v77, 10),
                ("Sequence", self._celdra_preset_sequence_v77, 14),
            )
        ):
            box = ttk.Frame(form)
            box.grid(row=0, column=column, sticky="ew", padx=(0, 5))
            ttk.Label(box, text=label).pack(anchor="w")
            ttk.Entry(box, textvariable=variable, width=width).pack(fill="x")
            form.columnconfigure(column, weight=2 if column == 0 else 1)

        tree = ttk.Treeview(
            parent,
            columns=("name", "asset", "scale", "time", "sequence", "text"),
            show="headings",
            height=5,
            selectmode="browse",
        )
        for key, heading, width in (
            ("name", "Preset", 150),
            ("asset", "Pose / asset", 110),
            ("scale", "Scale", 55),
            ("time", "At ms", 70),
            ("sequence", "Sequence", 85),
            ("text", "Dialogue", 330),
        ):
            tree.heading(key, text=heading)
            tree.column(key, width=width, stretch=key in {"name", "text"})
        tree.grid(row=1, column=0, sticky="ew", pady=6)
        tree.bind("<<TreeviewSelect>>", self._load_selected_preset_v77)
        self._celdra_preset_tree_v77 = tree

        buttons = ttk.Frame(parent)
        buttons.grid(row=2, column=0, sticky="ew")
        for label, command in (
            ("Save current as preset", self._save_pose_preset_v77),
            ("Update selected", self._update_pose_preset_v77),
            ("Delete", self._delete_pose_preset_v77),
            ("Load into editor", self._load_selected_preset_v77),
            ("Preview selected here", self._preview_selected_preset_here_v77),
            ("Preview selected in main", self._preview_selected_preset_main_v77),
            ("Insert selected into timeline", self._insert_selected_preset_v77),
        ):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=(0, 4))

    def _preset_snapshot_v77(self) -> dict[str, Any]:
        data = dict(self._preview_values_v74())
        self._celdra_preset_serial_v77 += 1
        return {
            "id": f"preset-{self._celdra_preset_serial_v77:04d}",
            "name": self._celdra_preset_name_v77.get().strip() if self._celdra_preset_name_v77 else "Celdra beat",
            "at_ms": self._bubble_setting_v72(self._celdra_preset_time_v77, 0),
            "move_ms": self._bubble_setting_v72(self._celdra_preset_move_v77, 650),
            "sequence": self._celdra_preset_sequence_v77.get().strip() if self._celdra_preset_sequence_v77 else "main",
            **data,
        }

    def _selected_preset_id_v77(self) -> str:
        tree = self._celdra_preset_tree_v77
        if tree is None:
            return ""
        selected = tree.selection()
        return str(selected[0]) if selected else ""

    def _selected_preset_v77(self) -> dict[str, Any] | None:
        return self._celdra_preset_rows_v77.get(self._selected_preset_id_v77())

    def _refresh_presets_v77(self, *, select_id: str = "") -> None:
        tree = self._celdra_preset_tree_v77
        if tree is None:
            return
        tree.delete(*tree.get_children())
        self._celdra_preset_rows_v77.clear()
        for row in self._celdra_pose_presets_v77:
            identifier = str(row.get("id") or "")
            if not identifier:
                continue
            tree.insert(
                "",
                "end",
                iid=identifier,
                values=(
                    row.get("name"),
                    row.get("asset"),
                    f"{row.get('scale', 100)}%",
                    row.get("at_ms", 0),
                    row.get("sequence", "main"),
                    str(row.get("text") or "").replace("\n", " ")[:120],
                ),
            )
            self._celdra_preset_rows_v77[identifier] = row
        if select_id and tree.exists(select_id):
            tree.selection_set(select_id)
            tree.see(select_id)

    def _save_pose_preset_v77(self) -> None:
        row = self._preset_snapshot_v77()
        self._celdra_pose_presets_v77.append(row)
        self._refresh_presets_v77(select_id=row["id"])

    def _update_pose_preset_v77(self) -> None:
        selected = self._selected_preset_id_v77()
        if not selected:
            self._save_pose_preset_v77()
            return
        replacement = self._preset_snapshot_v77()
        replacement["id"] = selected
        for index, row in enumerate(self._celdra_pose_presets_v77):
            if str(row.get("id")) == selected:
                self._celdra_pose_presets_v77[index] = replacement
                break
        self._refresh_presets_v77(select_id=selected)

    def _delete_pose_preset_v77(self) -> None:
        selected = self._selected_preset_id_v77()
        if not selected:
            return
        self._celdra_pose_presets_v77 = [
            row for row in self._celdra_pose_presets_v77 if str(row.get("id")) != selected
        ]
        self._refresh_presets_v77()

    def _apply_preset_to_editor_v77(self, row: dict[str, Any]) -> None:
        mappings = (
            (self._celdra_studio_pose_v72, row.get("asset", "shy")),
            (self._celdra_studio_x_v72, row.get("x", 0)),
            (self._celdra_studio_y_v72, row.get("y", 0)),
            (self._celdra_studio_scale_v72, row.get("scale", 100)),
            (self._celdra_studio_stage_v72, row.get("window_percent", 56)),
            (self._celdra_studio_bubble_style_v72, row.get("bubble_style", "Rounded blue")),
            (self._celdra_studio_bubble_x_v72, row.get("bubble_x", 4)),
            (self._celdra_studio_bubble_y_v72, row.get("bubble_y", 3)),
            (self._celdra_studio_bubble_w_v72, row.get("bubble_width", 52)),
            (self._celdra_preset_name_v77, row.get("name", "Celdra beat")),
            (self._celdra_preset_time_v77, row.get("at_ms", 0)),
            (self._celdra_preset_move_v77, row.get("move_ms", 650)),
            (self._celdra_preset_sequence_v77, row.get("sequence", "main")),
        )
        for variable, value in mappings:
            if variable is not None:
                variable.set(value)
        if self._celdra_studio_text_v72 is not None:
            self._celdra_studio_text_v72.delete("1.0", "end")
            self._celdra_studio_text_v72.insert("1.0", str(row.get("text") or ""))

    def _load_selected_preset_v77(self, _event: tk.Event | None = None) -> None:
        row = self._selected_preset_v77()
        if row is not None:
            self._apply_preset_to_editor_v77(row)

    def _preview_selected_preset_here_v77(self) -> None:
        row = self._selected_preset_v77()
        if row is None:
            return
        self._apply_preset_to_editor_v77(row)
        self._render_author_preview_v74(row)

    def _preview_selected_preset_main_v77(self) -> None:
        row = self._selected_preset_v77()
        if row is None:
            return
        self._apply_preset_to_editor_v77(row)
        self._preview_values_in_main_v77(row)

    def _insert_selected_preset_v77(self) -> None:
        row = self._selected_preset_v77()
        if row is None:
            row = self._preset_snapshot_v77()
        self._celdra_author_event_serial_v74 += 1
        base_id = f"preset-event-{self._celdra_author_event_serial_v74:04d}"
        common = {
            "sequence": row.get("sequence", "main"),
            "asset": row.get("asset", ""),
            "x": row.get("x", 0),
            "y": row.get("y", 0),
            "scale": row.get("scale", 100),
            "window_percent": row.get("window_percent", 56),
            "bubble_style": row.get("bubble_style", "Rounded blue"),
            "bubble_x": row.get("bubble_x", 4),
            "bubble_y": row.get("bubble_y", 3),
            "bubble_width": row.get("bubble_width", 52),
            "notes": f"Imported from pose preset: {row.get('name', '')}",
        }
        pose_event = normalize_event(
            {
                "id": f"{base_id}-a-pose",
                "at_ms": row.get("at_ms", 0),
                "duration_ms": row.get("move_ms", 650),
                "action": "pose",
                **common,
            },
            self._celdra_author_event_serial_v74,
        )
        events = [pose_event]
        if str(row.get("text") or "").strip():
            bubble_event = normalize_event(
                {
                    "id": f"{base_id}-b-dialogue",
                    "at_ms": int(row.get("at_ms", 0)) + max(1, int(row.get("move_ms", 650))),
                    "action": "bubble",
                    "speaker": "CELDRA",
                    "text": row.get("text", ""),
                    **common,
                },
                self._celdra_author_event_serial_v74 + 1,
            )
            events.append(bubble_event)
        self._celdra_author_events_v74 = normalize_events([*self._celdra_author_events_v74, *events])
        self._refresh_author_event_tree_v74()

    # ------------------------------------------------------------------
    # Timeline: keep full preview actions visible above the editor.
    # ------------------------------------------------------------------
    def _build_author_timeline_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        bar = ttk.Frame(parent)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        for label, command in (
            ("Play editable timeline here", self._play_author_timeline_v74),
            ("Preview selected in main viewport", self._preview_selected_event_main_v77),
            ("Play canonical timeline in main viewport (20×)", self._preview_canonical_main_v77),
            ("Preview egg corruption / climax in main", self._preview_egg_main_v77),
        ):
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=(0, 4))
        body = ttk.Frame(parent)
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        super()._build_author_timeline_tab_v74(body)

    # ------------------------------------------------------------------
    # Crop tab: fixed save/preview bar and scrollable full classifier.
    # ------------------------------------------------------------------
    def _build_author_crop_tab_v74(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        for label, command in (
            ("Save crop + PNG", self._save_crop_and_png_v74),
            ("Save manifest only", self._save_emote_definition_v52),
            ("Preview crop here", self._show_emote_in_celdra_v52),
            ("Preview crop in main viewport", self._preview_crop_main_v77),
            ("Export all crop PNGs", self._export_all_emotes_v52),
        ):
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 4))
        body = self._scroll_host_v77(parent, row=1)
        super()._build_author_crop_tab_v74(body)

    # ------------------------------------------------------------------
    # Real RUN ALL viewport previews.
    # ------------------------------------------------------------------
    def _prepare_main_preview_v77(self) -> None:
        self._select_run_all_tab_v50()
        self._celdra_test_mode_v58 = True
        self._celdra_session_active_v49 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._slide_chat_v54(show=False, duration_ms=220)
        self._hide_speech_bubble_v58()

    def _preview_values_in_main_v77(self, values: dict[str, Any]) -> None:
        self._prepare_main_preview_v77()
        asset = str(values.get("asset") or "shy")
        scale = max(10, min(500, int(values.get("scale") or 100)))
        self._celdra_external_offset_x_v65 = int(values.get("x") or 0)
        self._celdra_external_offset_y_v58 = int(values.get("y") or 0)
        generated = tuple(getattr(self, "GENERATED_PREVIEW_PHASES", ()))
        if asset.casefold() in generated:
            self._celdra_takeover_active_v58 = False
            self.celdra_current_external_v50 = None
            self._set_avatar_phase_v51(asset.casefold())
        else:
            display = self._preview_photo_for_asset_v74(asset, scale)
            if display is not None:
                self._celdra_main_preview_refs_v77 = [display]
                self._celdra_takeover_active_v58 = True
                self.celdra_current_pixel_v50 = None
                self.celdra_current_external_v50 = display
        fraction = max(0.10, min(0.99, int(values.get("window_percent") or 56) / 100.0))
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, fraction, 320)
        self._show_avatar_v51()
        self.after_idle(self._redraw_celdra_avatar_v50)
        text = str(values.get("text") or "")
        if text:
            self._show_speech_bubble_v58(text)

    def _preview_current_in_main_v77(self) -> None:
        self._preview_values_in_main_v77(self._preview_values_v74())

    def _preview_crop_main_v77(self) -> None:
        cropped = self._preview_emote_crop_v52()
        if cropped is None:
            return
        scale = max(10, min(500, self._bubble_setting_v72(self._celdra_studio_scale_v72, 100)))
        try:
            display = self._scale_photo_percent_v74(cropped, scale)
        except tk.TclError:
            return
        self._prepare_main_preview_v77()
        self._celdra_main_preview_refs_v77 = [cropped, display]
        self._celdra_takeover_active_v58 = True
        self._celdra_external_offset_x_v65 = self._bubble_setting_v72(self._celdra_studio_x_v72, 0)
        self._celdra_external_offset_y_v58 = self._bubble_setting_v72(self._celdra_studio_y_v72, 0)
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = display
        fraction = max(0.10, min(0.99, self._bubble_setting_v72(self._celdra_studio_stage_v72, 56) / 100.0))
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, fraction, 320)
        self._show_avatar_v51()
        self.after_idle(self._redraw_celdra_avatar_v50)
        text = self._studio_text_value_v72()
        if text:
            self._show_speech_bubble_v58(text)

    def _preview_selected_event_main_v77(self) -> None:
        row = self._celdra_author_event_rows_v74.get(self._selected_author_event_id_v74())
        if row is None:
            return
        action = str(row.get("action") or "")
        if action in {"pose", "avatar", "asset", "chat", "bubble"}:
            values = dict(row)
            if action not in {"chat", "bubble"}:
                values["text"] = ""
            self._preview_values_in_main_v77(values)
            return
        self._prepare_main_preview_v77()
        if action in {"console", "ascii", "status"}:
            speaker = str(row.get("speaker") or "CORE")
            self._append_console_v49(f"[{speaker}] {row.get('text') or ''}")
        elif action == "show_avatar":
            self._show_avatar_v51()
        elif action == "hide_avatar":
            self._hide_avatar_v51()
        elif action == "window":
            fraction = max(0.10, min(0.99, int(row.get("window_percent") or 56) / 100.0))
            PublicFragmenterAppV54._animate_stage_fraction_v54(self, fraction, 320)
        elif action == "egg_glitch":
            self._set_avatar_phase_v51("egg_wait")
            self._show_avatar_v51()
            self._set_egg_glitch_v61(4)
        elif action == "energy_hatch":
            self._set_avatar_phase_v51("crack_two")
            self._show_avatar_v51()
            self._start_energy_hatch_v63()

    def _preview_canonical_main_v77(self) -> None:
        self._start_timeline_test_v51(0.05)

    def _preview_egg_main_v77(self) -> None:
        self._select_run_all_tab_v50()
        self._cancel_celdra_cues_v49()
        self._cancel_progress_animation_v51()
        self._celdra_test_mode_v58 = True
        self._celdra_session_active_v49 = True
        self._celdra_first_scan_v51 = True
        self._celdra_timeline_started_v51 = False
        self._celdra_instability_red_v70 = False
        self._prepare_first_run_surface_v51()
        self._show_avatar_v51()
        self._set_avatar_phase_v51("egg_wait")
        self._set_egg_glitch_v61(0)
        self._remember_after_v49(500, lambda: self._set_egg_glitch_v61(1))
        self._remember_after_v49(1_100, lambda: self._set_egg_glitch_v61(2))
        self._remember_after_v49(1_700, self._preview_instability_v77)
        self._remember_after_v49(2_250, lambda: self._set_egg_glitch_v61(4))
        self._remember_after_v49(2_900, self._start_energy_hatch_v63)

    def _preview_instability_v77(self) -> None:
        self._celdra_instability_red_v70 = True
        self._append_console_v49("[CORE] SHELL SIGNAL INSTABILITY DETECTED.")
        self._set_egg_glitch_v61(3)
        self._redraw_celdra_avatar_v50()

    # ------------------------------------------------------------------
    # Persist presets in the same authoring JSON and ZIP bundle.
    # ------------------------------------------------------------------
    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        payload["pose_dialogue_presets"] = [dict(row) for row in self._celdra_pose_presets_v77]
        return payload

    def _apply_author_project_payload_v74(self, payload: dict[str, Any]) -> None:
        super()._apply_author_project_payload_v74(payload)
        presets = payload.get("pose_dialogue_presets")
        self._celdra_pose_presets_v77 = [dict(row) for row in presets if isinstance(row, dict)] if isinstance(presets, list) else []
        self._celdra_preset_serial_v77 = max(
            self._celdra_preset_serial_v77,
            len(self._celdra_pose_presets_v77),
        )
        self._refresh_presets_v77()


def main() -> int:
    app = PublicFragmenterAppV77()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

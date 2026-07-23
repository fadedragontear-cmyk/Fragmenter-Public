#!/usr/bin/env python3
"""Legacy/developer-only Fragmenter GUI builders and destructive actions.

This module is intentionally not imported by the normal GUI startup path.
It preserves experimental Easy Mods, advanced patch/install, and related legacy
UI hooks for explicit developer-only use.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from fragment_core import split_sections
from fragmenter_gui import ROOT, TOOLS, PY, WORKSPACE, REPORTS_WORKSPACE, _bind_wraplength


def _build_setup(self, f: ttk.Frame):
    card = self._card(f, "Step 1: Choose your Area Server folder")
    card.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

    ttk.Label(card, text="Area Server folder (contains data/ and save/)", foreground=self._theme["muted"]).grid(
        row=0, column=0, sticky="w", padx=10, pady=(10, 4)
    )
    row = ttk.Frame(card)
    row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
    ttk.Entry(row, textvariable=self.project_root).pack(side="left", fill="x", expand=True)
    ttk.Button(row, text="Browse", command=self.pick_project).pack(side="left", padx=8)

    grid = ttk.Frame(card)
    grid.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
    grid.grid_columnconfigure(1, weight=1)

    def line(r, label, var, cmd):
        ttk.Label(grid, text=label, width=16, foreground=self._theme["muted"]).grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=var).grid(row=r, column=1, sticky="ew", pady=4)
        ttk.Button(grid, text="Browse", command=cmd).grid(row=r, column=2, sticky="w", padx=8, pady=4)

    line(0, "Data folder", self.data_dir, self.pick_data)
    line(1, "Save folder", self.save_dir, self.pick_save)
    line(2, "Index file", self.index_path, self.pick_index_out)

    actions, _ = self._wrapped_button_row(
        card,
        [
            {"text": "Build/Refresh Index", "style": "Accent.TButton", "command": self.build_index},
            {"text": "Load Index", "command": self.load_index},
        ],
        columns_at_width=[(420, 2)],
    )
    actions.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 12))

    self._muted_help(
        f,
        "Next: Explore to browse sections. Use Easy Mods only if you understand the experimental risk.",
        row=1,
    )

    f.grid_columnconfigure(0, weight=1)


def _build_explore(self, parent: ttk.Frame):
    pw = ttk.Panedwindow(parent, orient="horizontal")
    pw.pack(fill="both", expand=True, padx=8, pady=8)

    left = ttk.Frame(pw)
    right = ttk.Frame(pw)
    pw.add(left, weight=2)
    pw.add(right, weight=3)

    top = ttk.Frame(left)
    top.pack(fill="x", padx=6, pady=(6, 4))
    ttk.Label(top, text="Catalog", font=self.FONT_H2).pack(side="left")
    ttk.Button(top, text="Refresh", command=self.load_index).pack(side="right")

    cols = ("type", "gzip", "sections", "size", "paths", "TEX", "MDL", "DMY")
    self.tree = ttk.Treeview(left, columns=cols, show="tree headings", height=22)
    self.tree.heading("#0", text="Name")
    for c, h in [
        ("type", "Type"), ("gzip", "GZ"), ("sections", "#Sec"), ("size", "Size"),
        ("paths", "Paths"), ("TEX", "TEX"), ("MDL", "MDL"), ("DMY", "DMY"),
    ]:
        self.tree.heading(c, text=h)

    self.tree.column("#0", width=340)
    for c, w, a in [
        ("type", 60, "center"),
        ("gzip", 40, "center"),
        ("sections", 60, "e"),
        ("size", 95, "e"),
        ("paths", 60, "e"),
        ("TEX", 55, "e"),
        ("MDL", 55, "e"),
        ("DMY", 55, "e"),
    ]:
        self.tree.column(c, width=w, anchor=a)

    yscroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
    self.tree.configure(yscrollcommand=yscroll.set)
    self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
    yscroll.pack(side="left", fill="y", padx=(0, 6), pady=6)

    self.tree.bind("<<TreeviewSelect>>", self.on_select)
    self.tree.bind("<ButtonRelease-1>", self._schedule_on_select)
    self.tree.bind("<KeyRelease>", self._schedule_on_select)

    # Tag styling for readability
    self.tree.tag_configure("binrow", background=self._theme["row_bin_bg"], foreground=self._theme["fg"])
    self.tree.tag_configure("secrow", background=self._theme["row_sec_bg"], foreground=self._theme["fg"])

    # Right: details + actions
    rtop = ttk.Frame(right)
    rtop.pack(fill="x", padx=6, pady=(6, 2))
    ttk.Label(rtop, text="Details", font=self.FONT_H2).pack(side="left")

    self.detail = tk.Text(
        right,
        wrap="word",
        height=14,
        bg=self._theme["text_bg"],
        fg=self._theme["text_fg"],
        insertbackground=self._theme["text_fg"],
    )
    self.detail.pack(fill="both", expand=True, padx=6, pady=(0, 8))

    rb = ttk.Labelframe(right, text="Resource Browser")
    rb.pack(fill="both", expand=True, padx=6, pady=(0, 8))
    rb.grid_columnconfigure(0, weight=2)
    rb.grid_columnconfigure(1, weight=3)
    rb.grid_rowconfigure(1, weight=1)

    rb_head = ttk.Frame(rb)
    rb_head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
    self.resource_browser_status = tk.StringVar(value="No resource map loaded.")
    ttk.Label(rb_head, textvariable=self.resource_browser_status, foreground=self._theme["muted"]).pack(side="left")
    rb_head_actions, _ = self._wrapped_button_row(
        rb_head,
        [
            {"text": "Open map", "command": self.open_resource_map_file},
            {"text": "Import Map into Correlations", "command": self.import_resource_map_into_correlations, "attr": "btn_import_map_correlations"},
            {"text": "Open folder", "command": self.open_resource_map_folder},
            {"text": "Clear", "command": self.clear_resource_browser},
        ],
        columns_at_width=[(760, 4), (520, 2)],
    )
    rb_head_actions.pack(side="right", fill="x")
    self._set_resource_browser_status("No resource map loaded.")

    left_panel = ttk.Frame(rb)
    left_panel.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=(0, 8))
    left_panel.grid_columnconfigure(0, weight=1)
    left_panel.grid_rowconfigure(0, weight=1)

    self.resource_family_list = tk.Listbox(left_panel, exportselection=False)
    fam_scroll = ttk.Scrollbar(left_panel, orient="vertical", command=self.resource_family_list.yview)
    self.resource_family_list.configure(yscrollcommand=fam_scroll.set)
    self.resource_family_list.grid(row=0, column=0, sticky="nsew")
    fam_scroll.grid(row=0, column=1, sticky="ns")
    self.resource_family_list.bind("<<ListboxSelect>>", self.on_resource_family_select)

    fam_pager = ttk.Frame(left_panel)
    fam_pager.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    self.resource_family_count = tk.StringVar(value="0 / 0 shown")
    ttk.Label(fam_pager, textvariable=self.resource_family_count, foreground=self._theme["muted"]).pack(side="left")
    self.resource_show_more_btn = ttk.Button(fam_pager, text="Show more", command=self.show_more_resource_families)
    self.resource_show_more_btn.pack(side="right")

    right_panel = ttk.Frame(rb)
    right_panel.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=(0, 8))
    right_panel.grid_columnconfigure(0, weight=1)
    right_panel.grid_rowconfigure(0, weight=1)

    self.resource_detail = tk.Text(
        right_panel,
        wrap="word",
        height=12,
        bg=self._theme["text_bg"],
        fg=self._theme["text_fg"],
        insertbackground=self._theme["text_fg"],
    )
    self.resource_detail.grid(row=0, column=0, sticky="nsew")
    rb_scroll = ttk.Scrollbar(right_panel, orient="vertical", command=self.resource_detail.yview)
    self.resource_detail.configure(yscrollcommand=rb_scroll.set)
    rb_scroll.grid(row=0, column=1, sticky="ns")

    suggestions = ttk.Labelframe(right_panel, text="Suggested ISO Searches")
    suggestions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    self.resource_suggestions_actions = ttk.Frame(suggestions)
    self.resource_suggestions_actions.pack(fill="x", padx=8, pady=8)

    meta = ttk.Labelframe(right_panel, text="Family Models")
    meta.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    meta.grid_columnconfigure(0, weight=1)
    self.resource_model_list = tk.Listbox(meta, height=5, exportselection=False)
    self.resource_model_list.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    self.resource_model_list.bind("<<ListboxSelect>>", self.on_resource_model_select)

    rel = ttk.Labelframe(right_panel, text="Related Assets")
    rel.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    rel.grid_columnconfigure(0, weight=1)
    self.resource_related_list = tk.Listbox(rel, height=6, exportselection=False)
    self.resource_related_list.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    self.resource_related_list.bind("<Double-1>", lambda _e: self.preview_related_asset())
    self.resource_related_list.bind("<<ListboxSelect>>", self.on_related_asset_select)

    rel_actions, _ = self._wrapped_button_row(
        rel,
        [
            {"text": "Extract likely model files", "command": self.extract_likely_model_files, "attr": "btn_extract_likely_model_files"},
            {"text": "Open in external viewer", "command": self.open_related_in_external_viewer, "attr": "btn_open_related_external"},
            {"text": "Open containing folder", "command": self.open_related_containing_folder, "attr": "btn_open_related_folder"},
            {"text": "Preview selected asset", "command": self.preview_related_asset, "attr": "btn_preview_related_asset"},
        ],
        columns_at_width=[(760, 4), (520, 2)],
    )
    rel_actions.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

    rel_phase = ttk.Frame(rel)
    rel_phase.grid(row=2, column=0, sticky="w", padx=8, pady=(0, 4))
    self.native_preview_switch = ttk.Checkbutton(
        rel_phase,
        text="Native 3D preview feasibility",
        variable=self.native_3d_preview_feasible,
        state="disabled",
    )
    self.native_preview_switch.pack(side="left")

    native_status_label = ttk.Label(
        rel,
        textvariable=self.native_3d_preview_status,
        foreground=self._theme["muted"],
        justify="left",
    )
    native_status_label.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
    _bind_wraplength(native_status_label, rel, padding=32)

    self.resource_preview_message = tk.StringVar(value="")
    resource_preview_label = ttk.Label(
        rel,
        textvariable=self.resource_preview_message,
        foreground=self._theme["muted"],
        justify="left",
    )
    resource_preview_label.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
    _bind_wraplength(resource_preview_label, rel, padding=32)

    workflow = ttk.Labelframe(right, text="Workflow Status")
    workflow.pack(fill="x", padx=6, pady=(0, 8))
    workflow.grid_columnconfigure(0, weight=1)
    workflow_label = ttk.Label(workflow, textvariable=self.workflow_status_text, foreground=self._theme["muted"], justify="left")
    workflow_label.pack(anchor="w", fill="x", padx=8, pady=8)
    _bind_wraplength(workflow_label, workflow, padding=32)

    act = ttk.Labelframe(right, text="Actions")
    act.pack(fill="x", padx=6, pady=(0, 6))
    self.explore_action_hint = tk.StringVar(value="Select a BIN or SECTION row to enable actions.")
    ttk.Label(act, textvariable=self.explore_action_hint, foreground=self._theme["muted"]).pack(anchor="w", padx=8, pady=(8, 0))

    row, _ = self._wrapped_button_row(
        act,
        [
            {"text": "Inspect SECTION", "command": self.inspect_selected, "attr": "btn_inspect_section"},
            {"text": "Unpack BIN", "command": self.unpack_selected, "attr": "btn_unpack_bin"},
            {"text": "Export Asset Paths", "command": self.export_asset_paths, "attr": "btn_export_asset_paths"},
            {"text": "Export DMY Markers", "command": self.export_dmy_markers, "attr": "btn_export_dmy_markers"},
            {"text": "Map selected section", "command": self.map_selected_section, "attr": "btn_map_section"},
        ],
        columns_at_width=[(860, 5), (640, 3), (420, 2)],
    )
    row.pack(fill="x", padx=8, pady=8)

    outrow = ttk.Frame(right)
    outrow.pack(fill="x", padx=6, pady=(0, 10))
    ttk.Label(outrow, text="Unpack output:", foreground=self._theme["muted"]).pack(side="left")
    ttk.Entry(outrow, textvariable=self.unpack_out).pack(side="left", fill="x", expand=True, padx=8)
    ttk.Button(outrow, text="Browse", command=self.pick_unpack_out).pack(side="left")
    self._update_explore_action_state(None, None, None)


def _build_easy(self, f: ttk.Frame):
    easy_help_label = ttk.Label(
        f,
        text=(
            "Easy Mods (EXPERIMENTAL / can break game): Fort Ouph presets (Town04).\n"
            "Experimental: use after confirming correlations.\n"
            "This does not yet know whether your selected replacement is safe.\n"
            "Recommended: use Explore + ISO Explorer + Correlations first.\n"
            "These repoint references—no new models are created."
        ),
        foreground=self._theme["muted"],
        justify="left",
    )
    easy_help_label.grid(row=0, column=0, sticky="ew", pady=(2, 12))
    _bind_wraplength(easy_help_label, f, padding=32)

    card = ttk.Labelframe(f, text="Fort Ouph (Town04) — One-click Reskin")
    card.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
    card.grid_columnconfigure(1, weight=1)

    ttk.Button(
        card,
        text="Select Fort Ouph section (town.bin → CCSFtown04)",
        style="Accent.TButton",
        command=self.select_fort_ouph_section,
    ).grid(row=0, column=0, padx=10, pady=(10, 6), sticky="w")

    preset_row, _ = self._wrapped_button_row(
        card,
        [
            {"text": "Preset: 5 (recommended)", "command": lambda: self.apply_preset_fort_ouph(5)},
            {"text": "Preset: 6", "command": lambda: self.apply_preset_fort_ouph(6)},
            {"text": "Preset: 7", "command": lambda: self.apply_preset_fort_ouph(7)},
            {"text": "Preset: 8", "command": lambda: self.apply_preset_fort_ouph(8)},
        ],
        columns_at_width=[(700, 4), (420, 2)],
    )
    preset_row.grid(row=1, column=0, columnspan=2, padx=10, pady=6, sticky="ew")

    ctrl = ttk.Frame(card)
    ctrl.grid(row=2, column=0, columnspan=2, padx=10, pady=(6, 10), sticky="ew")
    ctrl.grid_columnconfigure(1, weight=1)

    ttk.Label(ctrl, text="From:", foreground=self._theme["muted"]).grid(row=0, column=0, sticky="w")
    ttk.Spinbox(ctrl, from_=0, to=9, textvariable=self.reskin_from, width=6).grid(row=0, column=1, sticky="w")
    ttk.Label(ctrl, text="To:", foreground=self._theme["muted"]).grid(row=0, column=2, sticky="w", padx=(16, 0))
    ttk.Spinbox(ctrl, from_=0, to=9, textvariable=self.reskin_to, width=6).grid(row=0, column=3, sticky="w")

    ttk.Checkbutton(
        ctrl,
        text="Also replace srX symbols (sr4 → srY)",
        variable=self.reskin_symbols,
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

    ttk.Label(ctrl, text="Output .bin:", foreground=self._theme["muted"]).grid(row=2, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(ctrl, textvariable=self.reskin_out).grid(row=2, column=1, columnspan=2, sticky="ew", pady=(8, 0), padx=(8, 8))
    ttk.Button(ctrl, text="Browse", command=self.pick_reskin_out).grid(row=2, column=3, sticky="w", pady=(8, 0))

    context_box = ttk.Labelframe(card, text="Selected context (review before staging)")
    context_box.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
    context_box.grid_columnconfigure(0, weight=1)
    self.easy_context_text = tk.Text(context_box, height=9, wrap="word", bg=self._theme["panel"], fg=self._theme["fg"], insertbackground=self._theme["fg"])
    self.easy_context_text.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    self.easy_context_text.insert("end", "Select a SECTION to preview the Easy Mod context.\n")
    self.easy_context_text.configure(state="disabled")

    buttons, _ = self._wrapped_button_row(
        card,
        [
            {"text": "Generate Easy Mod Plan", "style": "Accent.TButton", "command": self.generate_easy_mod_plan},
            {"text": "Reskin SECTION", "command": self.reskin_selected},
            {"text": "Quick: Reskin + Install (generate plan first)", "command": self.quick_reskin_install_selected, "attr": "quick_reskin_btn"},
            {"text": "Expert Override: acknowledge risk", "style": "Accent.TButton", "command": self.enable_quick_reskin_flow},
        ],
        columns_at_width=[(980, 4), (640, 2)],
    )
    buttons.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 12), sticky="ew")
    self.quick_reskin_btn.state(["disabled"])

    plan_row = ttk.Frame(card)
    plan_row.grid(row=5, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
    ttk.Label(plan_row, text="Staged plan:", foreground=self._theme["muted"]).pack(side="left")
    plan_path_label = ttk.Label(plan_row, textvariable=self.easy_mod_plan_path, foreground=self._theme["muted"], justify="left")
    plan_path_label.pack(side="left", padx=(8, 0), fill="x", expand=True)
    _bind_wraplength(plan_path_label, plan_row, padding=32)

    restore = ttk.Labelframe(f, text="Restore backup instructions")
    restore.grid(row=2, column=0, sticky="ew", padx=2, pady=(12, 0))
    restore.grid_columnconfigure(0, weight=1)
    self.easy_restore_text = tk.Text(restore, height=5, wrap="word", bg=self._theme["panel"], fg=self._theme["fg"], insertbackground=self._theme["fg"])
    self.easy_restore_text.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    self.easy_restore_text.insert("end", self._restore_backup_instructions("town.bin") + "\n")
    self.easy_restore_text.configure(state="disabled")

    f.grid_columnconfigure(0, weight=1)
    self._render_easy_mod_context()


def _build_advanced(self, f: ttk.Frame):
    advanced_help_label = ttk.Label(
        f,
        text=("Advanced (EXPERIMENTAL): patch a modified .ccsf section back into a BIN, then install.\n"
              "Experimental: use after confirming correlations. This does not yet know whether your selected replacement is safe.\n"
              "Recommended: use Explore + ISO Explorer + Correlations first."),
        foreground=self._theme["muted"],
        justify="left",
    )
    advanced_help_label.grid(row=0, column=0, sticky="ew", pady=(2, 12))
    _bind_wraplength(advanced_help_label, f, padding=32)

    card = ttk.Labelframe(f, text="Patch CCSF section into BIN")
    card.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
    card.grid_columnconfigure(0, weight=1)

    ttk.Label(card, text="Replacement .ccsf", foreground=self._theme["muted"]).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
    replacement_help_label = ttk.Label(
        card,
        text="Pick the modified CCSF section file that will replace the selected section.",
        foreground=self._theme["muted"],
        justify="left",
    )
    replacement_help_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
    _bind_wraplength(replacement_help_label, card, padding=32)
    row = ttk.Frame(card)
    row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
    ttk.Entry(row, textvariable=self.patch_replace).pack(side="left", fill="x", expand=True)
    ttk.Button(row, text="Browse", command=self.pick_patch_replace).pack(side="left", padx=8)

    ttk.Label(card, text="Output patched BIN", foreground=self._theme["muted"]).grid(row=3, column=0, sticky="w", padx=10, pady=(0, 4))
    patch_output_help_label = ttk.Label(
        card,
        text="This writes a patched BIN file to disk first; review/test this output before install.",
        foreground=self._theme["muted"],
        justify="left",
    )
    patch_output_help_label.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 4))
    _bind_wraplength(patch_output_help_label, card, padding=32)
    row2 = ttk.Frame(card)
    row2.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 10))
    ttk.Entry(row2, textvariable=self.patch_out).pack(side="left", fill="x", expand=True)
    ttk.Button(row2, text="Browse", command=self.pick_patch_out).pack(side="left", padx=8)

    patch_plan_help_label = ttk.Label(
        card,
        text=(
            "Patch Plan Preview is required before patching. It verifies the selected section, replacement file, "
            "output path, size delta, section-id mismatch warning, and recovery instructions."
        ),
        foreground=self._theme["muted"],
        justify="left",
    )
    patch_plan_help_label.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 8))
    _bind_wraplength(patch_plan_help_label, card, padding=32)

    btns, _ = self._wrapped_button_row(
        card,
        [
            {"text": "Patch Plan Preview", "command": self.preview_patch_plan},
            {"text": "Patch CCSF section into BIN", "command": self.patch_selected},
        ],
        columns_at_width=[(520, 2)],
    )
    btns.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 12))

    install_card = ttk.Labelframe(f, text="Install patched BIN")
    install_card.grid(row=2, column=0, sticky="ew", padx=2, pady=(12, 2))
    install_card.grid_columnconfigure(0, weight=1)
    install_help_label = ttk.Label(
        install_card,
        text=(
            "Install is locked until this session has a Patch Plan Preview, the patched output exists, "
            "and you type-confirm the original BIN target. A timestamped backup is created first."
        ),
        foreground=self._theme["muted"],
        justify="left",
    )
    install_help_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 8))
    _bind_wraplength(install_help_label, install_card, padding=32)
    ttk.Button(install_card, text="Install patched BIN", style="Accent.TButton", command=self.install_patched).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 12))

    backup_card = ttk.Labelframe(f, text="Backup/Restore")
    backup_card.grid(row=3, column=0, sticky="ew", padx=2, pady=(12, 2))
    backup_card.grid_columnconfigure(0, weight=1)
    backup_help_label = ttk.Label(
        backup_card,
        text="Backups are stored in data/_fragmenter_backups. Restore by closing the server and copying the newest matching .bak over the original BIN.",
        foreground=self._theme["muted"],
        justify="left",
    )
    backup_help_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 8))
    _bind_wraplength(backup_help_label, backup_card, padding=32)
    backup_btns, _ = self._wrapped_button_row(
        backup_card,
        [
            {"text": "Open backups folder", "command": self.open_backups_folder},
            {"text": "Show latest backup restore command", "command": self.show_latest_backup_restore_command},
        ],
        columns_at_width=[(620, 2)],
    )
    backup_btns.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 12))

    f.grid_columnconfigure(0, weight=1)


def pick_patch_replace(self):
    p = filedialog.askopenfilename(
        title="Select replacement .ccsf",
        filetypes=[("CCSF", "*.ccsf"), ("All files", "*.*")],
    )
    if p:
        self.patch_replace.set(p)


def pick_patch_out(self):
    p = filedialog.asksaveasfilename(
        title="Save patched bin as",
        defaultextension=".bin",
        filetypes=[("BIN", "*.bin"), ("All files", "*.*")],
    )
    if p:
        self.patch_out.set(p)


def pick_reskin_out(self):
    p = filedialog.asksaveasfilename(
        title="Save reskinned bin as",
        defaultextension=".bin",
        filetypes=[("BIN", "*.bin"), ("All files", "*.*")],
    )
    if p:
        self.reskin_out.set(p)


def select_fort_ouph_section(self):
    if not hasattr(self, "tree"):
        return messagebox.showerror("Not ready", "Build the index first in Setup.")
    town_item = None
    for item in self.tree.get_children(""):
        if self.tree.item(item, "text").lower() == "town.bin":
            town_item = item
            break
    if not town_item:
        return messagebox.showerror("Not found", "Couldn't find town.bin. Build the index and check your data folder.")

    self.tree.item(town_item, open=True)
    sec_item = self._find_child_by_text(town_item, "CCSFtown04")
    if not sec_item:
        return messagebox.showerror("Not found", "Couldn't find CCSFtown04 under town.bin.")

    self.tree.selection_set(sec_item)
    self.tree.see(sec_item)
    self.on_select()


def apply_preset_fort_ouph(self, to_set: int):
    self.reskin_from.set(4)
    self.reskin_to.set(int(to_set))
    self.reskin_symbols.set(True)
    self.reskin_out.set(str(ROOT / f"town_FortOuph_to_assetset{int(to_set)}.bin"))
    self.latest_easy_mod_plan = None
    self.easy_mod_plan_path.set("No current Easy Mod plan; generate a new plan for this preset.")
    self._update_quick_reskin_state()
    try:
        self.select_fort_ouph_section()
    except Exception:
        pass


def _planned_backup_hint(self, target_name: str) -> str:
    data = self.data_dir.get().strip()
    if not data:
        return "(set Data folder in Setup to preview backup path)"
    backup_dir = Path(data) / "_fragmenter_backups"
    return str(backup_dir / f"{target_name}.<YYYYmmdd_HHMMSS>.bak")


def _confirm_preflight(self, title: str, lines: list[str]) -> bool:
    body = "\n".join(lines)
    return bool(messagebox.askokcancel(title, body))


def _restore_backup_instructions(self, target_name: str) -> str:
    return (
        f"Restore if needed: close server, copy latest {target_name}*.bak from data/_fragmenter_backups "
        f"over data/{target_name}, then relaunch."
    )


def _invalidate_easy_mod_plan(self):
    if not hasattr(self, "latest_easy_mod_plan"):
        return
    self.latest_easy_mod_plan = None
    self.latest_easy_mod_dry_run = None
    if hasattr(self, "easy_mod_plan_path"):
        self.easy_mod_plan_path.set("No current Easy Mod plan; generate a new plan for these settings.")
    if hasattr(self, "quick_reskin_enabled"):
        self.quick_reskin_enabled.set(False)
    self._update_quick_reskin_state()
    self._render_easy_mod_context()


def _set_text_widget(self, widget_name: str, text: str):
    widget = getattr(self, widget_name, None)
    if widget is None:
        return
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("end", text)
    widget.configure(state="disabled")


def _current_easy_selection(self):
    res = self.resolve_selected()
    if res and res[0] == "sec":
        return res
    return None


def _current_easy_target_name(self) -> str:
    sel = self._current_easy_selection()
    if sel:
        _kind, f, _s = sel
        return str(f.get("name") or Path(f.get("file", "town.bin")).name or "town.bin")
    plan = self.latest_easy_mod_plan or {}
    return str(plan.get("target_bin") or "town.bin")


def _easy_mod_signature(self, f: dict, s: dict) -> dict[str, object]:
    return {
        "source_bin": str(f.get("file", "")),
        "target_bin": str(f.get("name") or Path(f.get("file", "")).name),
        "section": str(s.get("id", "")),
        "from": int(self.reskin_from.get()),
        "to": int(self.reskin_to.get()),
        "symbols": bool(self.reskin_symbols.get()),
        "out": self.reskin_out.get().strip(),
        "family": str((self.selected_family or {}).get("family", "")),
    }


def _load_correlation_section(self, section: str) -> tuple[dict, str | None]:
    path = ROOT / "fragmenter_correlations.json"
    if not path.exists():
        return {}, "No correlation store found (fragmenter_correlations.json)."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"Correlation store could not be read: {exc}"
    sections = payload.get("sections", {}) if isinstance(payload, dict) else {}
    sec = sections.get(section, {}) if isinstance(sections, dict) else {}
    return (sec if isinstance(sec, dict) else {}), None


def _correlation_lines_for_context(self, section: str, family_name: str = "", limit: int = 12) -> tuple[list[str], bool, bool]:
    sec, warning = self._load_correlation_section(section)
    lines: list[str] = []
    has_confirmed = False
    has_probable = False
    if warning:
        lines.append(warning)
        return lines, has_confirmed, has_probable
    families = sec.get("families", {}) if isinstance(sec, dict) else {}
    if not isinstance(families, dict) or not families:
        lines.append("No confirmed/probable correlations recorded for this section.")
        return lines, has_confirmed, has_probable
    wanted = {family_name} if family_name else set(families.keys())
    shown = 0
    for fam_name in sorted(wanted):
        fam = families.get(fam_name, {})
        if not isinstance(fam, dict):
            continue
        hits = fam.get("hits", []) or []
        for hit in hits:
            status = str(hit.get("status", "unreviewed"))
            if status not in {"confirmed", "probable"}:
                continue
            has_confirmed = has_confirmed or status == "confirmed"
            has_probable = has_probable or status == "probable"
            path = hit.get("path", "<missing path>")
            size = f" size={hit.get('size')}" if hit.get("size") is not None else ""
            lines.append(f"[{status}] family={fam_name} path={path}{size}")
            shown += 1
            if shown >= limit:
                lines.append(f"(+ more correlations not shown; open fragmenter_correlations.json for full list)")
                return lines, has_confirmed, has_probable
    if not lines:
        scope = f"family {family_name}" if family_name else "this section"
        lines.append(f"No confirmed/probable correlations recorded for {scope}.")
    return lines, has_confirmed, has_probable


def _replacement_reference_lines(self) -> list[str]:
    from_id = int(self.reskin_from.get())
    to_id = int(self.reskin_to.get())
    lines = [
        f"Asset set replacement: {from_id} -> {to_id}",
        f"Path reference: \\r\\{from_id}\\ -> \\r\\{to_id}\\",
    ]
    if self.reskin_symbols.get():
        lines.append(f"Symbol stem: sr{from_id} -> sr{to_id}")
    fam = self.selected_family or {}
    refs = []
    for cat in ("models", "textures", "materials", "animations", "asset_paths"):
        refs.extend(fam.get(cat, []) or [])
    if refs:
        lines.append("Selected family replacement references:")
        lines.extend([f"  - {item}" for item in refs[:8]])
        if len(refs) > 8:
            lines.append(f"  (+{len(refs) - 8} more)")
    else:
        lines.append("Selected family replacement references: none selected/mapped.")
    return lines


def _render_easy_mod_context(self):
    sel = self._current_easy_selection()
    if not sel:
        self._set_text_widget("easy_context_text", "Select a SECTION in Explore or use the Fort Ouph button before staging an Easy Mod plan.\n")
        self._set_text_widget("easy_restore_text", self._restore_backup_instructions("town.bin") + "\n")
        return
    _kind, f, s = sel
    section = str(s.get("id", "?"))
    family_name = str((self.selected_family or {}).get("family", ""))
    corr_lines, has_confirmed, has_probable = self._correlation_lines_for_context(section, family_name, limit=6)
    target_name = str(f.get("name") or Path(f.get("file", "town.bin")).name)
    lines = [
        f"Current section: {section}",
        f"Current family: {family_name or '(none selected)'}",
        f"Confirmed/probable correlations available: confirmed={'yes' if has_confirmed else 'no'}, probable={'yes' if has_probable else 'no'}",
        f"Target BIN: {target_name}",
        "Replacement asset set / references:",
    ]
    lines.extend([f"  {line}" for line in self._replacement_reference_lines()])
    lines.append("Confirmed/probable correlation details:")
    lines.extend([f"  {line}" for line in corr_lines])
    self._set_text_widget("easy_context_text", "\n".join(lines) + "\n")
    self._set_text_widget("easy_restore_text", self._restore_backup_instructions(target_name) + "\n")


def _easy_plan_is_current(self) -> bool:
    sel = self._current_easy_selection()
    if not sel or not self.latest_easy_mod_plan:
        return False
    _kind, f, s = sel
    return self.latest_easy_mod_plan.get("signature") == self._easy_mod_signature(f, s)


def _update_quick_reskin_state(self):
    if not hasattr(self, "quick_reskin_btn"):
        return
    if self.quick_reskin_enabled.get() and self._easy_plan_is_current():
        self.quick_reskin_btn.config(text="Quick: Reskin + Install")
        self.quick_reskin_btn.state(["!disabled"])
    else:
        self.quick_reskin_btn.config(text="Quick: Reskin + Install (generate plan first)")
        self.quick_reskin_btn.state(["disabled"])


def _write_easy_mod_plan(self, plan: dict) -> Path:
    REPORTS_WORKSPACE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPORTS_WORKSPACE / f"easy_mod_plan_{stamp}.txt"
    lines = [
        "Fragmenter Easy Mod Plan",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"Source BIN: {plan['source_bin']}",
        f"Target BIN: {plan['target_bin']}",
        f"Section: {plan['section']}",
        f"Current family: {plan['family'] or '(none selected)'}",
        f"From asset id/stem: {plan['from_asset']} / {plan['from_stem']}",
        f"To asset id/stem: {plan['to_asset']} / {plan['to_stem']}",
        f"Replacement count from dry-run: {plan['replacement_count']}",
        f"Patched output BIN: {plan['output_bin']}",
        f"Backup path: {plan['backup_path']}",
        "",
        "Replacement references:",
    ]
    lines.extend([f"  - {line}" for line in plan["replacement_references"]])
    lines.extend(["", "Confirmed/probable correlations for section/family:"])
    lines.extend([f"  - {line}" for line in plan["correlations"]])
    lines.extend(["", "Warnings:"])
    lines.extend([f"  - {line}" for line in plan["warnings"]])
    lines.extend(["", "Restore instructions:", f"  {plan['restore_instructions']}", ""])
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def generate_easy_mod_plan(self):
    sel = self._current_easy_selection()
    if not sel:
        return messagebox.showerror("Select section", "Select a SECTION first (e.g., CCSFtown04).")
    _kind, f, s = sel
    out = self.reskin_out.get().strip()
    if not out:
        return messagebox.showerror("Missing", "Pick an output .bin path.")
    cmd = [
        PY, str(TOOLS / "fragment_reskin_section.py"),
        f["file"],
        "--section", s["id"],
        "--from", str(int(self.reskin_from.get())),
        "--to", str(int(self.reskin_to.get())),
        "--out", out,
        "--dry-run",
    ]
    if self.reskin_symbols.get():
        cmd.append("--symbols")
    summary = self._run_json_command(cmd, "Generate Easy Mod plan dry-run")
    if not summary:
        return
    section = str(summary.get("section", s.get("id", "?")))
    family_name = str((self.selected_family or {}).get("family", ""))
    corr_lines, has_confirmed, has_probable = self._correlation_lines_for_context(section, family_name, limit=50)
    target_name = str(f.get("name") or Path(f.get("file", "town.bin")).name)
    warnings = []
    if not has_confirmed:
        warnings.append("No confirmed correlations are recorded for this section/family; proceed only after manual review.")
    if not has_probable and not has_confirmed:
        warnings.append("No probable correlations are recorded for this section/family.")
    if int(summary.get("replacements", {}).get("total", 0)) == 0:
        warnings.append("Dry-run found zero replacements; install would likely make no useful change.")
    plan = {
        "signature": self._easy_mod_signature(f, s),
        "source_bin": str(summary.get("input_bin", f.get("file", ""))),
        "target_bin": target_name,
        "section": section,
        "family": family_name,
        "from_asset": int(self.reskin_from.get()),
        "to_asset": int(self.reskin_to.get()),
        "from_stem": f"sr{int(self.reskin_from.get())}",
        "to_stem": f"sr{int(self.reskin_to.get())}",
        "replacement_count": int(summary.get("replacements", {}).get("total", 0)),
        "output_bin": str(summary.get("output_bin", out)),
        "backup_path": self._planned_backup_hint(target_name),
        "restore_instructions": self._restore_backup_instructions(target_name),
        "replacement_references": self._replacement_reference_lines(),
        "correlations": corr_lines,
        "warnings": warnings or ["No staged warnings."],
    }
    plan_path = self._write_easy_mod_plan(plan)
    plan["plan_path"] = str(plan_path)
    self.latest_easy_mod_plan = plan
    self.latest_easy_mod_dry_run = summary
    self.easy_mod_plan_path.set(str(plan_path))
    self._update_quick_reskin_state()
    self._render_easy_mod_context()
    messagebox.showinfo("Easy Mod plan generated", f"Wrote staged plan:\n{plan_path}\n\nDry-run remains mandatory and will run again before install.")


def enable_quick_reskin_flow(self):
    if not self._easy_plan_is_current():
        self.quick_reskin_enabled.set(False)
        self._update_quick_reskin_state()
        return messagebox.showwarning(
            "Generate plan first",
            "Generate an Easy Mod plan for the current section/from/to/output before enabling the expert quick install override.",
        )
    ok = messagebox.askokcancel(
        "Enable quick install flow?",
        (
            "Quick: Reskin + Install is EXPERIMENTAL and can break game files.\n\n"
            f"A staged plan exists:\n{self.latest_easy_mod_plan.get('plan_path', '(unknown)')}\n\n"
            "Dry-run will still run again before any install, and install will create a backup.\n"
            "You acknowledge the warnings in the staged plan and know how to restore the backup.\n"
            "Click OK to enable the quick button for this session."
        ),
    )
    if not ok:
        return
    self.quick_reskin_enabled.set(True)
    self._update_quick_reskin_state()


def reskin_selected(self):
    res = self.resolve_selected()
    if not res or res[0] != "sec":
        return messagebox.showerror("Select section", "Select a SECTION first (e.g., CCSFtown04).")

    if not self._warn_if_no_confirmed_correlations():
        return
    _, f, s = res
    target_name = str(f.get("name") or Path(f.get("file", "town.bin")).name)
    out = self.reskin_out.get().strip()
    if not out:
        return messagebox.showerror("Missing", "Pick an output .bin path.")
    cmd = [
        PY, str(TOOLS / "fragment_reskin_section.py"),
        f["file"],
        "--section", s["id"],
        "--from", str(int(self.reskin_from.get())),
        "--to", str(int(self.reskin_to.get())),
        "--out", out,
        "--dry-run",
    ]
    if self.reskin_symbols.get():
        cmd.append("--symbols")
    summary = self._run_json_command(cmd, "Reskin dry-run")
    if not summary:
        return
    ok = self._confirm_preflight(
        "Confirm reskin",
        [
            "RESKIN PREFLIGHT (dry-run completed):",
            f"Replacement count: {summary.get('replacements', {}).get('total', 0)}",
            f"Target file: {target_name}",
            f"Selected section: {summary.get('section', s['id'])}",
            f"Input file: {summary.get('input_bin', f['file'])}",
            f"Output path: {summary.get('output_bin', out)}",
            f"Backup path: {self._planned_backup_hint(target_name)}",
            self._restore_backup_instructions(target_name),
            "",
            "Click OK to execute non-dry-run reskin.",
        ],
    )
    if not ok:
        return
    run_cmd = [c for c in cmd if c != "--dry-run"]
    self._run_task(run_cmd)


def quick_reskin_install_selected(self):
    if not self.quick_reskin_enabled.get():
        return messagebox.showwarning(
            "Quick flow disabled",
            "Quick install is disabled by default. Generate an Easy Mod plan, then click the expert acknowledgement first.",
        )
    if not self._easy_plan_is_current():
        self.quick_reskin_enabled.set(False)
        self._update_quick_reskin_state()
        return messagebox.showwarning(
            "Plan required",
            "Generate a fresh Easy Mod plan for the current section/from/to/output before Quick: Reskin + Install can run.",
        )
    res = self.resolve_selected()
    if not res or res[0] != "sec":
        return messagebox.showerror("Select section", "Use the Fort Ouph button first, then try again.")

    if not self._warn_if_no_confirmed_correlations():
        return
    _, f, s = res
    target_name = str(f.get("name") or Path(f.get("file", "town.bin")).name)
    out = self.reskin_out.get().strip()
    if not out:
        return messagebox.showerror("Missing", "Pick an output .bin path.")
    cmd = [
        PY, str(TOOLS / "fragment_reskin_section.py"),
        f["file"],
        "--section", s["id"],
        "--from", str(int(self.reskin_from.get())),
        "--to", str(int(self.reskin_to.get())),
        "--out", out,
        "--dry-run",
    ]
    if self.reskin_symbols.get():
        cmd.append("--symbols")
    summary = self._run_json_command(cmd, "Reskin dry-run")
    if not summary:
        return
    ok = self._confirm_preflight(
        "Confirm quick reskin",
        [
            "QUICK RESKIN PREFLIGHT (dry-run completed):",
            f"Replacement count: {summary.get('replacements', {}).get('total', 0)}",
            f"Target file: {target_name}",
            f"Selected section: {summary.get('section', s['id'])}",
            f"Input file: {summary.get('input_bin', f['file'])}",
            f"Output path: {summary.get('output_bin', out)}",
            f"Backup path: {self._planned_backup_hint(target_name)}",
            self._restore_backup_instructions(target_name),
            "",
            "Click OK to execute non-dry-run reskin.",
        ],
    )
    if not ok:
        return

    def after_reskin(rc):
        if rc == 0:
            self.install_reskinned()

    run_cmd = [c for c in cmd if c != "--dry-run"]
    self._run_task(run_cmd, on_done=after_reskin)


def install_reskinned(self):
    if not self._warn_if_no_confirmed_correlations():
        return
    out = self.reskin_out.get().strip()
    if not out or not Path(out).exists():
        return messagebox.showerror("Missing", "Reskin output .bin not found. Run reskin first.")

    data = self.data_dir.get().strip()
    if not data:
        return messagebox.showerror("Missing", "Set Data folder in Setup first.")

    target_name = self._current_easy_target_name()
    ok = self._confirm_preflight(
        "Confirm install",
        [
            "INSTALL PREFLIGHT:",
            "Replacement count: (already applied in reskin step)",
            f"Target file: {target_name}",
            "Selected section: (n/a for install)",
            f"Input file: {out}",
            f"Output path: {Path(data) / target_name}",
            f"Backup path: {self._planned_backup_hint(target_name)}",
            self._restore_backup_instructions(target_name),
            "",
            "Click OK to install now.",
        ],
    )
    if not ok:
        return
    cmd = [PY, str(TOOLS / "fragmenter_install.py"), out, "--data-dir", data, "--original-name", target_name]
    self._run_task(cmd)


def _invalidate_patch_plan(self):
    if not hasattr(self, "latest_patch_context"):
        return
    self.latest_patch_context = None


def _selected_patch_plan_inputs(self) -> tuple[dict, dict, str, str] | None:
    res = self.resolve_selected()
    if not res or res[0] != "sec":
        messagebox.showerror("Select section", "Select a SECTION first.")
        return None
    _kind, f, s = res
    rep = self.patch_replace.get().strip()
    out = self.patch_out.get().strip()
    if not rep or not out:
        messagebox.showerror("Missing", "Pick replacement .ccsf and output patched BIN first.")
        return None
    if not Path(rep).exists():
        messagebox.showerror("Missing", "Replacement CCSF file not found.")
        return None
    return f, s, rep, out


def _replacement_section_id(self, replacement_path: str) -> str:
    try:
        sections = split_sections(Path(replacement_path).read_bytes())
    except Exception as exc:
        return f"(unreadable: {exc})"
    if not sections:
        return "(no CCSF section id found)"
    return str(sections[0][1] or "(unknown)")


def _current_patch_matches_plan(self, ctx: dict) -> bool:
    res = self.resolve_selected()
    if not res or res[0] != "sec":
        return False
    _kind, f, s = res
    return (
        str(ctx.get("source_bin_path", "")) == str(f.get("file", ""))
        and str(ctx.get("section", "")) == str(s.get("id", ""))
        and str(ctx.get("replacement_file", "")) == self.patch_replace.get().strip()
        and str(ctx.get("output_bin", "")) == self.patch_out.get().strip()
    )


def _format_patch_plan_lines(self, ctx: dict) -> list[str]:
    delta = ctx.get("byte_delta", 0)
    delta_label = f"{delta:+}" if isinstance(delta, int) else str(delta)
    lines = [
        "PATCH PLAN PREVIEW (required before patching):",
        f"Source BIN: {ctx.get('source_bin_name', '')}",
        f"Source BIN path: {ctx.get('source_bin_path', '')}",
        f"Selected section: {ctx.get('section', '')}",
        f"Selected section exists: {'yes' if ctx.get('section_exists') else 'no'}",
        f"Replacement CCSF file: {ctx.get('replacement_file', '')}",
        f"Replacement section id: {ctx.get('replacement_section_id', '')}",
        f"Output patched BIN: {ctx.get('output_bin', '')}",
        "Size comparison:",
        f"  Current section bytes: {ctx.get('existing_section_bytes', '(unknown)')}",
        f"  Replacement section bytes: {ctx.get('replacement_section_bytes', '(unknown)')}",
        f"  Delta bytes: {delta_label}",
    ]
    if ctx.get("replacement_id_mismatch"):
        lines.extend([
            "",
            "WARNING: replacement section id does not match the selected section.",
            "Only continue if you intentionally chose a cross-section replacement and understand the risk.",
        ])
    lines.extend([
        "",
        "Backup/restore instructions:",
        f"  Backup path on install: {ctx.get('backup_path', '')}",
        f"  {ctx.get('restore_instructions', '')}",
        "",
        "No install happens during patching. Patching only stages the output BIN above.",
    ])
    return lines


def preview_patch_plan(self):
    inputs = self._selected_patch_plan_inputs()
    if not inputs:
        return
    if not self._warn_if_no_confirmed_correlations():
        return
    f, s, rep, out = inputs
    cmd = [
        PY, str(TOOLS / "fragment_patch_section.py"),
        f["file"], "--section", s["id"], "--replace", rep, "--out", out, "--dry-run"
    ]
    summary = self._run_json_command(cmd, "Patch Plan Preview")
    if not summary:
        return
    source_bin_path = str(summary.get("input_bin", f["file"]))
    source_bin_name = Path(source_bin_path).name or f.get("name", "")
    section_id = str(summary.get("section", s["id"]))
    replacement_section_id = self._replacement_section_id(rep)
    replacements = summary.get("replacements", {}) if isinstance(summary.get("replacements"), dict) else {}
    section_exists = bool(summary.get("section")) and int(replacements.get("section_count", 0) or 0) > 0
    ctx = {
        "source_bin_path": source_bin_path,
        "source_bin_name": source_bin_name,
        "section": section_id,
        "replacement_file": rep,
        "replacement_section_id": replacement_section_id,
        "replacement_id_mismatch": replacement_section_id not in ("", "(unknown)") and replacement_section_id != section_id,
        "output_bin": str(summary.get("output_bin", out)),
        "existing_section_bytes": replacements.get("existing_section_bytes", "(unknown)"),
        "replacement_section_bytes": replacements.get("replacement_section_bytes", "(unknown)"),
        "byte_delta": replacements.get("byte_delta", "(unknown)"),
        "section_exists": section_exists,
        "backup_path": self._planned_backup_hint(source_bin_name),
        "restore_instructions": self._restore_backup_instructions(source_bin_name),
    }
    ok = self._confirm_preflight(
        "Patch Plan Preview",
        self._format_patch_plan_lines(ctx) + ["", "Click OK after reviewing this plan. Patch is now unlocked for this exact selection."],
    )
    self.latest_patch_context = ctx if ok else None


def patch_selected(self):
    ctx = self.latest_patch_context
    if not ctx:
        return messagebox.showerror(
            "Patch Plan Preview required",
            "Click Patch Plan Preview first. Patching is locked until this session has a reviewed plan.",
        )
    if not self._current_patch_matches_plan(ctx):
        return messagebox.showerror(
            "Patch Plan Preview stale",
            "The selected section, replacement CCSF, or output BIN changed. Generate a fresh Patch Plan Preview before patching.",
        )
    if not ctx.get("section_exists"):
        return messagebox.showerror("Section missing", "The Patch Plan Preview says the selected section does not exist.")
    if not self._warn_if_no_confirmed_correlations():
        return

    cmd = [
        PY, str(TOOLS / "fragment_patch_section.py"),
        ctx["source_bin_path"], "--section", ctx["section"],
        "--replace", ctx["replacement_file"], "--out", ctx["output_bin"]
    ]
    ok = self._confirm_preflight(
        "Confirm patch staged output",
        self._format_patch_plan_lines(ctx) + [
            "",
            "Click OK to write the staged patched BIN now.",
            "Install remains locked until this output exists and you confirm the original BIN target.",
        ],
    )
    if not ok:
        return
    self._run_task(cmd)


def install_patched(self):
    ctx = self.latest_patch_context
    if not ctx:
        return messagebox.showerror(
            "Patch Plan Preview required",
            "Install is locked until this session has a Patch Plan Preview for the exact patched output.",
        )
    if str(ctx.get("output_bin", "")) != self.patch_out.get().strip():
        return messagebox.showerror(
            "Patch Plan Preview stale",
            "The output patched BIN path changed. Generate a fresh Patch Plan Preview before install.",
        )
    out = str(ctx.get("output_bin", "")).strip()
    if not out or not Path(out).exists():
        return messagebox.showerror("Missing", "Patched output BIN does not exist. Run Patch CCSF section into BIN first.")
    data = self.data_dir.get().strip()
    if not data:
        return messagebox.showerror("Missing", "Set Data folder in Setup first.")
    if not self._warn_if_no_confirmed_correlations():
        return

    source_name = (ctx.get("source_bin_name", "") or "").strip()
    source_path = (ctx.get("source_bin_path", "") or "").strip()
    section = (ctx.get("section", "") or "(unknown)").strip()
    if not source_name:
        source_name = Path(source_path).name if source_path else ""
    if not source_name:
        return messagebox.showerror("Missing patch context", "Could not determine source BIN name from the Patch Plan Preview.")

    res = self.resolve_selected()
    if res and res[0] == "bin":
        selected_target = str(res[1].get("name", "") or "").strip()
        if selected_target and selected_target != source_name:
            return messagebox.showerror(
                "Wrong target selected",
                f"The Patch Plan Preview source is '{source_name}', but the selected BIN is '{selected_target}'. Select the original source BIN or clear the selection before install.",
            )

    typed = simpledialog.askstring(
        "Confirm original BIN target",
        (
            f"Type the original BIN name exactly to install over it:\n\n"
            f"{source_name}\n\n"
            "A timestamped backup will be created first."
        ),
        parent=self,
    )
    if typed != source_name:
        return messagebox.showerror("Target not confirmed", "Install cancelled because the original BIN name was not typed exactly.")

    ok = self._confirm_preflight(
        "Confirm install patched BIN",
        [
            "INSTALL PREFLIGHT:",
            "Patch Plan Preview: generated this session",
            "Patched output exists: yes",
            f"Target original BIN confirmed: {source_name}",
            f"Affected source BIN: {source_name}",
            f"Source BIN path: {source_path or '(unknown)'}",
            f"Affected section: {section}",
            f"Input patched BIN: {out}",
            f"Output path: {Path(data) / source_name}",
            f"Backup path: {self._planned_backup_hint(source_name)}",
            self._restore_backup_instructions(source_name),
            "",
            "WARNING: This installs the staged patched BIN over the original target.",
            "Click OK to install now.",
        ],
    )
    if not ok:
        return
    cmd = [PY, str(TOOLS / "fragmenter_install.py"), out, "--data-dir", data, "--original-name", source_name]
    self._run_task(cmd)


def open_backups_folder(self):
    backup_dir = self._backup_dir()
    if backup_dir is None:
        return
    backup_dir.mkdir(exist_ok=True)
    self._open_folder_path(backup_dir)


def show_latest_backup_restore_command(self):
    backup_dir = self._backup_dir()
    if backup_dir is None:
        return
    target_name = self._backup_target_name()
    if not target_name:
        return messagebox.showerror("Select target", "Select a BIN/SECTION or generate a Patch Plan Preview first so Fragmenter knows which original BIN to restore.")
    backups = sorted(backup_dir.glob(f"{target_name}.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        return messagebox.showinfo("No backup found", f"No backups found for {target_name} in {backup_dir}.")
    latest = backups[0]
    target = Path(self.data_dir.get().strip()) / target_name
    command = (
        f'{PY} -c "import shutil, pathlib; '
        f'shutil.copy2(pathlib.Path(r\'{latest}\'), pathlib.Path(r\'{target}\'))"'
    )
    messagebox.showinfo(
        "Latest backup restore command",
        (
            "Close the Area Server before restoring. Latest matching backup:\n"
            f"{latest}\n\n"
            "Restore command:\n"
            f"{command}"
        ),
    )


def _build_inspector(self, f):
    f.grid_columnconfigure(0, weight=1)
    f.grid_rowconfigure(2, weight=1)

    title = ttk.Frame(f)
    title.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
    ttk.Label(title, text="Preview / Container Inspector", font=self.FONT_H2).pack(side="left")
    ttk.Label(
        title,
        text="  Read-only preview and explicit bounded extraction for packed binaries.",
        foreground=self._theme.get("muted", "#9fb3a7"),
    ).pack(side="left")

    controls = ttk.Labelframe(f, text="Local binary")
    controls.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
    controls.grid_columnconfigure(1, weight=1)
    ttk.Label(controls, text="Selected file").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
    ttk.Entry(controls, textvariable=self.inspector_path).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(8, 4))
    ttk.Button(controls, text="Select local binary file", command=self.select_inspector_file).grid(row=0, column=2, padx=(0, 8), pady=(8, 4))

    ttk.Label(controls, text="Scan cap (MiB)").grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
    ttk.Spinbox(controls, from_=1, to=8192, increment=64, textvariable=self.inspector_max_scan_mb, width=8).grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 8))

    inspector_actions, _ = self._wrapped_button_row(
        controls,
        [
            {"text": "Preview selected file", "style": "Accent.TButton", "command": self.preview_inspector_file},
            {"text": "Scan selected container", "command": self.scan_inspector_container},
            {"text": "Import preview symbols into correlations", "command": self.import_preview_symbols_into_correlations},
            {"text": "Search ISO containers for these strings", "command": self.search_iso_containers_for_preview_strings},
        ],
        columns_at_width=[(980, 4), (640, 2)],
    )
    inspector_actions.grid(row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 8))

    ttk.Label(controls, text="Extract dir").grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))
    ttk.Entry(controls, textvariable=self.inspector_extract_dir).grid(row=3, column=1, sticky="ew", padx=(0, 8), pady=(0, 8))
    extract_actions, _ = self._wrapped_button_row(
        controls,
        [{"text": "Extract/decompress selected preview candidate", "command": self.extract_inspector_candidate}],
    )
    extract_actions.grid(row=3, column=2, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 8))
    inspector_status_label = ttk.Label(
        controls,
        textvariable=self.inspector_status,
        foreground=self._theme.get("muted", "#9fb3a7"),
        justify="left",
    )
    inspector_status_label.grid(row=4, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 8))
    _bind_wraplength(inspector_status_label, controls, padding=32)

    body = ttk.Panedwindow(f, orient="horizontal")
    body.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

    output_frame = ttk.Labelframe(body, text="Preview details")
    output_frame.grid_columnconfigure(0, weight=1)
    output_frame.grid_rowconfigure(0, weight=1)
    self.inspector_output = tk.Text(output_frame, wrap="none", height=24, bg="#07110b", fg="#b8ffd8", insertbackground="#b8ffd8")
    self.inspector_output.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
    out_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.inspector_output.yview)
    out_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
    self.inspector_output.configure(yscrollcommand=out_scroll.set)
    body.add(output_frame, weight=3)

    candidates_frame = ttk.Labelframe(body, text="Magic hits / candidate embedded files")
    candidates_frame.grid_columnconfigure(0, weight=1)
    candidates_frame.grid_rowconfigure(0, weight=1)
    self.inspector_candidate_tree = ttk.Treeview(candidates_frame, columns=("offset", "type", "nearby"), show="headings", height=12)
    self.inspector_candidate_tree.heading("offset", text="Offset")
    self.inspector_candidate_tree.heading("type", text="Type")
    self.inspector_candidate_tree.heading("nearby", text="Nearby strings")
    self.inspector_candidate_tree.column("offset", width=110, anchor="w")
    self.inspector_candidate_tree.column("type", width=150, anchor="w")
    self.inspector_candidate_tree.column("nearby", width=360, anchor="w")
    self.inspector_candidate_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
    cand_scroll = ttk.Scrollbar(candidates_frame, orient="vertical", command=self.inspector_candidate_tree.yview)
    cand_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
    self.inspector_candidate_tree.configure(yscrollcommand=cand_scroll.set)
    body.add(candidates_frame, weight=2)


def stage_mod_plan(self):
    _bin, section = self._selected_section_context()
    family = self._selected_family_name()
    if not section or not family:
        return messagebox.showerror("Missing context", "Select a SECTION and resource family first.")
    store = self._load_correlations()
    fam = self._correlation_family(store, section, family) or {}
    hits = [h for h in fam.get("hits", []) or [] if h.get("status") in {"confirmed", "probable"}]
    REPORTS_WORKSPACE.mkdir(parents=True, exist_ok=True)
    safe_section = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in section) or "section"
    out = REPORTS_WORKSPACE / f"staged_mod_plan_{safe_section}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
    symbols = []
    for key in ("models", "textures", "materials", "animations", "cameras", "markers"):
        symbols.extend(str(x) for x in (fam.get(key) or []))
    asset_paths = list(fam.get("asset_paths") or ((store.get("sections") or {}).get(section) or {}).get("asset_paths") or [])
    lines = [
        "Fragmenter Staged Mod Plan",
        f"Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}",
        f"Selected section: {section}",
        f"Selected resource family: {family}",
        "",
        "Confirmed/probable ISO hits:",
    ]
    if hits:
        for h in hits:
            note = f" — notes: {h.get('notes')}" if h.get("notes") else ""
            lines.append(f"  - [{h.get('status')}] {h.get('path')} size={h.get('size', '(unknown)')}{note}")
    else:
        lines.append("  (none yet; confirm or mark probable ISO hits before patching)")
    lines.extend(["", "Server symbols:"])
    lines.extend([f"  - {x}" for x in symbols[:200]] or ["  (none recorded)"])
    lines.extend(["", "Server asset paths:"])
    lines.extend([f"  - {x}" for x in asset_paths[:200]] or ["  (none recorded)"])
    notes = fam.get("notes") or []
    lines.extend(["", "Notes:"])
    lines.extend([f"  - {x}" for x in notes[:100]] or ["  (none recorded)"])
    lines.extend([
        "",
        "Suggested next action:",
        "  Review this plan, extract candidate assets for optional external preview, then use Easy Mods/Advanced only if you accept the experimental risk.",
        "  This PR stages a readable plan only and does not patch files.",
    ])
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    self._console_write(f"[stage] Wrote staged mod plan: {out}\n")
    self.update_workflow_status()
    messagebox.showinfo("Staged Mod Plan", f"Wrote staged plan:\n{out}")


def _build_iso(self, f: ttk.Frame):
    f.grid_columnconfigure(0, weight=1)
    f.grid_rowconfigure(5, weight=1)
    f.grid_rowconfigure(6, weight=1)

    iso_help_label = ttk.Label(
        f,
        text="ISO Explorer (read-only): Use lightweight ISO search first; full index is optional/heavy.\n"
             "Search/extract does NOT modify your ISO.",
        foreground=self._theme.get("muted", "#9fb3a7"),
        justify="left",
    )
    iso_help_label.grid(row=0, column=0, sticky="ew", pady=(2, 10))
    _bind_wraplength(iso_help_label, f, padding=32)

    card = ttk.Labelframe(f, text="ISO Setup")
    card.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
    card.grid_columnconfigure(0, weight=1)

    r = ttk.Frame(card); r.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
    r.grid_columnconfigure(0, weight=1)
    ttk.Entry(r, textvariable=self.iso_path).grid(row=0, column=0, sticky="ew")
    ttk.Button(r, text="Browse ISO", command=self.pick_iso).grid(row=0, column=1, padx=(8,0))

    r2 = ttk.Frame(card); r2.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
    r2.grid_columnconfigure(0, weight=1)
    ttk.Entry(r2, textvariable=self.iso_index_path).grid(row=0, column=0, sticky="ew")
    ttk.Button(r2, text="Index JSON...", command=self.pick_iso_index_out).grid(row=0, column=1, padx=(8,0))
    ttk.Button(r2, text="Open", command=self.open_iso_index_file).grid(row=0, column=2, padx=(8,0))

    r3 = ttk.Frame(card); r3.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
    r3.grid_columnconfigure(0, weight=1)
    ttk.Entry(r3, textvariable=self.iso_extract_dir).grid(row=0, column=0, sticky="ew")
    ttk.Button(r3, text="Extract folder...", command=self.pick_iso_extract_dir).grid(row=0, column=1, padx=(8,0))
    ttk.Button(r3, text="Open", command=self.open_iso_extract_dir).grid(row=0, column=2, padx=(8,0))

    viewer = ttk.Labelframe(card, text="External Viewer / Optional 3D Preview")
    viewer.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
    viewer.grid_columnconfigure(1, weight=1)
    ttk.Label(viewer, text="Selected viewer").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
    self.viewer_combo = ttk.Combobox(viewer, textvariable=self.viewer_choice, values=self._viewer_display_names(), state="readonly")
    self.viewer_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(8, 4))
    self.viewer_combo.bind("<<ComboboxSelected>>", self.on_viewer_choice_changed)
    ttk.Button(viewer, text="Launch selected asset", command=self.open_related_in_external_viewer).grid(row=0, column=2, padx=(0, 8), pady=(8, 4))

    ttk.Label(viewer, text="Viewer name").grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))
    ttk.Entry(viewer, textvariable=self.viewer_name).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 4))

    ttk.Label(viewer, text="Executable path").grid(row=2, column=0, sticky="w", padx=8, pady=(0, 4))
    ttk.Entry(viewer, textvariable=self.viewer_executable).grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(0, 4))
    ttk.Button(viewer, text="Browse", command=self.pick_external_viewer).grid(row=2, column=2, padx=(0, 8), pady=(0, 4))

    ttk.Label(viewer, text="Args template ({path})").grid(row=3, column=0, sticky="w", padx=8, pady=(0, 4))
    ttk.Entry(viewer, textvariable=self.viewer_args).grid(row=3, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 4))

    ttk.Label(viewer, text="Extensions").grid(row=4, column=0, sticky="w", padx=8, pady=(0, 4))
    ttk.Entry(viewer, textvariable=self.viewer_extensions).grid(row=4, column=1, sticky="ew", padx=(0, 8), pady=(0, 4))
    ttk.Checkbutton(viewer, text="Enabled", variable=self.viewer_enabled).grid(row=4, column=2, sticky="w", padx=(0, 8), pady=(0, 4))

    ttk.Button(viewer, text="Save viewer", command=self.save_viewer_config).grid(row=5, column=2, sticky="e", padx=(0, 8), pady=(0, 8))
    viewer_help_label = ttk.Label(
        viewer,
        text=(
            "Fragmenter does not decode all .hack formats yet. Extract an asset first, then optionally open it in "
            "Blender/Noesis/another viewer if that tool supports the format.\n"
            "Use comma-separated extensions this viewer should handle, e.g. .obj,.fbx,.gltf or * for all. "
            "Include {path} where the extracted file should be inserted; if omitted Fragmenter appends the path with a warning."
        ),
        foreground=self._theme.get("muted", "#9fb3a7"),
        justify="left",
    )
    viewer_help_label.grid(row=6, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 8))
    _bind_wraplength(viewer_help_label, viewer, padding=32)
    self._refresh_viewer_combo()

    act, _ = self._wrapped_button_row(
        card,
        [
            {"text": "Build ISO Index (heavy/optional)", "style": "Accent.TButton", "command": self.build_iso_index},
            {"text": "Load ISO Index", "command": self.load_iso_index},
            {"text": "Resolve from selected SECTION", "command": self.resolve_iso_from_selection},
        ],
        columns_at_width=[(760, 3), (480, 2)],
    )
    act.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))

    workflow = ttk.Labelframe(f, text="Workflow Status")
    workflow.grid(row=2, column=0, sticky="ew", padx=2, pady=(8, 2))
    workflow.grid_columnconfigure(0, weight=1)
    iso_workflow_text = ttk.Frame(workflow)
    iso_workflow_text.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    iso_workflow_text.grid_columnconfigure(0, weight=1)
    iso_workflow_label = ttk.Label(
        iso_workflow_text,
        textvariable=self.workflow_status_text,
        foreground=self._theme.get("muted", "#9fb3a7"),
        justify="left",
    )
    iso_workflow_label.grid(row=0, column=0, sticky="ew")
    _bind_wraplength(iso_workflow_label, iso_workflow_text, padding=16)
    ttk.Button(workflow, text="Stage Mod Plan", command=self.stage_mod_plan).grid(row=0, column=1, sticky="e", padx=8, pady=8)

    stat = ttk.Frame(f); stat.grid(row=3, column=0, sticky="ew", padx=2, pady=(8, 2))
    stat.grid_columnconfigure(0, weight=1)
    iso_status_label = ttk.Label(stat, textvariable=self.iso_status, foreground=self._theme.get("muted", "#9fb3a7"), justify="left")
    iso_status_label.grid(row=0, column=0, sticky="ew")
    _bind_wraplength(iso_status_label, stat, padding=32)

    # Progress (ISO indexing)
    prog = ttk.Frame(f); prog.grid(row=4, column=0, sticky="ew", padx=2, pady=(0, 4))
    prog.grid_columnconfigure(0, weight=1)
    self.iso_progress_bar = ttk.Progressbar(prog, mode="determinate", maximum=100.0, variable=self.iso_progress)
    self.iso_progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    ttk.Label(prog, textvariable=self.iso_progress_text, foreground=self._theme.get("muted", "#9fb3a7")).grid(row=0, column=1, sticky="e")
    iso_current_label = ttk.Label(prog, textvariable=self.iso_current, foreground=self._theme.get("muted", "#9fb3a7"), justify="left")
    iso_current_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4,0))
    _bind_wraplength(iso_current_label, prog, padding=32)

    search = ttk.Labelframe(f, text="Search ISO (lightweight, no full index)")
    search.grid(row=5, column=0, sticky="ew", padx=2, pady=(8, 2))
    search.grid_columnconfigure(1, weight=1)

    ttk.Label(
        search,
        text="NOTE: ISO path search scans file names/paths; use container-string scan/search after extracting a selected container.",
        font=self.FONT_H2,
        foreground=self._theme.get("warn", "#ffcc66"),
    ).grid(row=0, column=0, columnspan=8, sticky="w", padx=8, pady=(8, 2))
    ttk.Label(
        search,
        text="Diagnostic/path-only operations: use these to inspect candidate ISO paths before extraction.",
        foreground=self._theme.get("muted", "#9fb3a7"),
    ).grid(row=1, column=0, columnspan=8, sticky="w", padx=8, pady=(0, 4))

    ttk.Label(search, text="Query (comma separated)").grid(row=2, column=0, sticky="w", padx=8, pady=(8, 4))
    ttk.Entry(search, textvariable=self.iso_search_query).grid(row=2, column=1, sticky="ew", padx=8, pady=(8, 4))
    ttk.Label(search, text="Extensions").grid(row=2, column=2, sticky="w", padx=8, pady=(8, 4))
    ttk.Entry(search, textvariable=self.iso_search_ext, width=20).grid(row=2, column=3, sticky="w", padx=(0, 8), pady=(8, 4))
    ttk.Label(search, text="Prefix").grid(row=2, column=4, sticky="w", padx=(4, 4), pady=(8, 4))
    ttk.Entry(search, textvariable=self.iso_search_prefix, width=18).grid(row=2, column=5, sticky="w", padx=(0, 8), pady=(8, 4))
    ttk.Label(search, text="Limit").grid(row=2, column=6, sticky="w", padx=(4, 4), pady=(8, 4))
    ttk.Spinbox(search, from_=1, to=2000, textvariable=self.iso_search_limit, width=7).grid(row=2, column=7, sticky="w", padx=(0, 8), pady=(8, 4))
    ttk.Label(search, text="Max scan").grid(row=3, column=0, sticky="w", padx=8, pady=(0, 4))
    ttk.Spinbox(search, from_=1000, to=500000, increment=1000, textvariable=self.iso_search_max_scan, width=10).grid(row=3, column=1, sticky="w", padx=8, pady=(0, 4))

    b, _ = self._wrapped_button_row(
        search,
        [
            {"text": "Search ISO paths", "style": "Accent.TButton", "command": self.run_iso_search},
            {"text": "Search paths from selected SECTION", "command": self.run_iso_search_from_section},
            {"text": "Show first 50 ISO paths (diagnostic)", "command": self.run_iso_show_first_paths},
            {"text": "Clear filters", "command": self.clear_iso_search_filters},
            {"text": "Extract selected hit", "command": self.extract_iso_search_selected},
            {"text": "Preview selected file", "command": self.preview_iso_selected_file},
            {"text": "Scan selected container", "command": self.scan_iso_selected_container},
            {"text": "Extract then preview", "command": self.extract_then_preview_iso_selected_file},
            {"text": "Search container strings", "command": self.search_iso_container_strings},
            {"text": "Search preview strings in containers", "command": self.search_iso_containers_for_preview_strings},
        ],
        columns_at_width=[(1100, 5), (820, 4), (560, 2)],
    )
    b.grid(row=4, column=0, columnspan=8, sticky="ew", padx=8, pady=(2, 10))

    adv_toggle = ttk.Frame(search)
    adv_toggle.grid(row=5, column=0, columnspan=8, sticky="w", padx=8, pady=(0, 6))
    ttk.Checkbutton(
        adv_toggle,
        text="Advanced: enable batch extraction",
        variable=self.iso_batch_advanced,
        command=self._toggle_iso_advanced_batch,
    ).pack(side="left")

    self.iso_advanced_batch_frame = ActionBar(search, columns_at_width=[(760, 4), (520, 2)])
    self.iso_advanced_batch_frame.grid(row=6, column=0, columnspan=8, sticky="ew", padx=8, pady=(0, 10))
    self.iso_advanced_batch_frame.add_widget(ttk.Label(self.iso_advanced_batch_frame, text="Batch max files (default safety cap)"))
    self.iso_advanced_batch_frame.add_widget(ttk.Spinbox(
        self.iso_advanced_batch_frame,
        from_=1,
        to=1000,
        textvariable=self.iso_batch_max_files,
        width=7,
    ))
    self.iso_advanced_batch_frame.add_button(
        text="Extract ALL hits",
        command=self.extract_iso_search_all,
    )
    self.iso_advanced_batch_frame.add_button(
        text="Extract ALL found",
        command=self.extract_iso_all_found,
    )
    self._toggle_iso_advanced_batch()

    sres = ttk.Labelframe(f, text="Search hits")
    sres.grid(row=6, column=0, sticky="nsew", padx=2, pady=(8, 2))
    sres.grid_columnconfigure(0, weight=1)
    sres.grid_rowconfigure(0, weight=1)

    self.iso_search_tree = ttk.Treeview(sres, columns=("status", "size", "path"), show="headings", height=10)
    self.iso_search_tree.heading("status", text="Correlation")
    self.iso_search_tree.heading("size", text="Size")
    self.iso_search_tree.heading("path", text="ISO path")
    self.iso_search_tree.column("status", width=110, anchor="center")
    self.iso_search_tree.column("size", width=110, anchor="e")
    self.iso_search_tree.column("path", width=700, anchor="w")
    self.iso_search_tree.bind("<<TreeviewSelect>>", self.on_iso_search_hit_select)
    sy = ttk.Scrollbar(sres, orient="vertical", command=self.iso_search_tree.yview)
    self.iso_search_tree.configure(yscrollcommand=sy.set)
    self.iso_search_tree.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
    sy.grid(row=0, column=1, sticky="ns", padx=(0,8), pady=8)
    self.iso_nohit_actions = ttk.Frame(sres)
    self.iso_nohit_actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
    self.iso_nohit_actions.grid_remove()

    corr = ttk.Labelframe(sres, text="Correlations")
    corr.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
    corr.grid_columnconfigure(0, weight=1)
    ttk.Label(corr, textvariable=self.correlation_selected_hit_status, foreground=self._theme.get("muted", "#9fb3a7")).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
    corr_actions, _ = self._wrapped_button_row(
        corr,
        [
            {"text": "Mark Probable", "command": lambda: self.mark_selected_correlation_hit("probable")},
            {"text": "Mark Confirmed", "command": lambda: self.mark_selected_correlation_hit("confirmed")},
            {"text": "Mark Rejected", "command": lambda: self.mark_selected_correlation_hit("rejected")},
            {"text": "Add/Edit Note", "command": self.add_edit_correlation_note},
            {"text": "Open Correlation Report", "command": self.open_correlation_report},
            {"text": "Export Correlation Report", "command": self.export_correlation_report},
        ],
        columns_at_width=[(900, 6), (620, 3), (420, 2)],
    )
    corr_actions.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

    string_frame = ttk.Labelframe(f, text="Container string hits (from scanned/extracted containers)")
    string_frame.grid(row=7, column=0, sticky="nsew", padx=2, pady=(8, 2))
    string_frame.grid_columnconfigure(0, weight=1)
    string_frame.grid_rowconfigure(0, weight=1)
    self.iso_container_string_text = tk.Text(
        string_frame,
        wrap="none",
        height=6,
        bg="#07110b",
        fg="#b8ffd8",
        insertbackground="#b8ffd8",
    )
    self.iso_container_string_text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
    string_scroll = ttk.Scrollbar(string_frame, orient="vertical", command=self.iso_container_string_text.yview)
    string_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
    self.iso_container_string_text.configure(yscrollcommand=string_scroll.set)

    res = ttk.Labelframe(f, text="Resolved references (from section path samples)")
    res.grid(row=8, column=0, sticky="nsew", padx=2, pady=(8, 2))
    res.grid_columnconfigure(0, weight=1)
    res.grid_rowconfigure(0, weight=1)

    cols = ("found", "size", "path")
    self.iso_tree = ttk.Treeview(res, columns=cols, show="headings")
    self.iso_tree.heading("found", text="Found")
    self.iso_tree.heading("size", text="Size")
    self.iso_tree.heading("path", text="ISO path (normalized)")
    self.iso_tree.column("found", width=70, anchor="center")
    self.iso_tree.column("size", width=90, anchor="e")
    self.iso_tree.column("path", width=760, anchor="w")
    y = ttk.Scrollbar(res, orient="vertical", command=self.iso_tree.yview)
    self.iso_tree.configure(yscrollcommand=y.set)
    self.iso_tree.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
    y.grid(row=0, column=1, sticky="ns", padx=(0,8), pady=8)

    btns, _ = self._wrapped_button_row(
        f,
        [
            {"text": "Extract selected", "style": "Accent.TButton", "command": self.extract_iso_selected},
            {"text": "Preview selected file", "command": self.preview_iso_selected_file},
            {"text": "Scan selected container", "command": self.scan_iso_selected_container},
            {"text": "Extract then preview", "command": self.extract_then_preview_iso_selected_file},
        ],
        columns_at_width=[(780, 4), (520, 2)],
    )
    btns.grid(row=9, column=0, sticky="ew", padx=2, pady=(8, 0))


def install_legacy_gui_features(app_cls):
    """Attach legacy GUI builders/actions to ``app_cls`` explicitly."""
    for _name, _value in globals().items():
        if callable(_value) and not _name.startswith("__") and _name != "install_legacy_gui_features":
            setattr(app_cls, _name, _value)
    return app_cls

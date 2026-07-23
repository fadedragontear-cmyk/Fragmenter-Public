#!/usr/bin/env python3
"""V126 first-time project setup, optional sources, and project themes."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from fragmenter_public_gui_v125 import (
    BRAND_PNG_V125,
    PublicFragmenterAppV125,
)
from project_setup_controller_v1 import create_setup_project, setup_view_model
from project_workspace_v1 import save_project, write_project_status

PROJECT_THEME_KEY_V126 = "ui_theme_v126"
PROJECT_THEMES_V126 = {
    "Serenial Blue": {
        "background": "#071522",
        "panel": "#0b2235",
        "field": "#102b40",
        "foreground": "#dcebf5",
        "muted": "#9eb8c8",
        "accent": "#67dcff",
        "select": "#17698a",
    },
    "Hack Green": {
        "background": "#06130c",
        "panel": "#0b2417",
        "field": "#103321",
        "foreground": "#d8f5e4",
        "muted": "#9bc8ad",
        "accent": "#52f29a",
        "select": "#17653c",
    },
    "Twilight Violet": {
        "background": "#130d20",
        "panel": "#211438",
        "field": "#2d1c49",
        "foreground": "#eee6ff",
        "muted": "#b9a8d2",
        "accent": "#c18cff",
        "select": "#65418e",
    },
    "Warm Amber": {
        "background": "#1c1408",
        "panel": "#30220d",
        "field": "#443016",
        "foreground": "#fff0d2",
        "muted": "#d0b78a",
        "accent": "#ffbd52",
        "select": "#8a5b16",
    },
}


class PublicFragmenterAppV126(PublicFragmenterAppV125):
    """Make Project Setup useful before every optional source is known."""

    def __init__(self) -> None:
        # Tk variables cannot exist until the inherited Tk root is initialized.
        self._project_theme_name_v126 = "Serenial Blue"
        super().__init__()
        self.title("Fragmenter 1.0")
        self._apply_project_theme_v126()

    def _palette_v126(self) -> dict[str, str]:
        variable = getattr(self, "project_theme_v126", None)
        selected = (
            variable.get()
            if variable is not None
            else self._project_theme_name_v126
        )
        return PROJECT_THEMES_V126.get(
            selected,
            PROJECT_THEMES_V126["Serenial Blue"],
        )

    def _build_header(self) -> None:
        self._load_brand_images_v125()
        palette = self._palette_v126()
        self._header_frame_v126 = tk.Frame(
            self, bg=palette["background"], padx=12, pady=8
        )
        self._header_frame_v126.pack(fill="x")

        if self._brand_header_v125 is not None:
            self._header_image_v126 = tk.Label(
                self._header_frame_v126,
                image=self._brand_header_v125,
                bg=palette["background"],
                borderwidth=0,
            )
            self._header_image_v126.pack(side="left", padx=(0, 10))

        self._header_identity_v126 = tk.Frame(
            self._header_frame_v126, bg=palette["background"]
        )
        self._header_identity_v126.pack(side="left", fill="y")
        self._header_title_v126 = tk.Label(
            self._header_identity_v126,
            text="Fragmenter",
            bg=palette["background"],
            fg=palette["accent"],
            font=("Segoe UI", 19, "bold"),
        )
        self._header_title_v126.pack(anchor="w")
        self._header_subtitle_v126 = tk.Label(
            self._header_identity_v126,
            text=".hack//Fragment research, preservation, and setup toolkit",
            bg=palette["background"],
            fg=palette["muted"],
            font=("Segoe UI", 9),
        )
        self._header_subtitle_v126.pack(anchor="w")

        self._header_project_v126 = tk.Label(
            self._header_frame_v126,
            textvariable=self.project_label,
            bg=palette["background"],
            fg=palette["foreground"],
            font=("Segoe UI", 9),
        )
        self._header_project_v126.pack(side="left", padx=22)
        self._header_task_v126 = tk.Label(
            self._header_frame_v126,
            textvariable=self.current_task_label,
            bg=palette["background"],
            fg=palette["accent"],
            font=("Segoe UI", 9, "bold"),
        )
        self._header_task_v126.pack(side="right")

    def _build_setup(self, parent: ttk.Frame) -> None:
        self.project_theme_v126 = tk.StringVar(
            master=self,
            value=self._project_theme_name_v126,
        )
        super()._build_setup(parent)
        theme_box = ttk.LabelFrame(
            parent,
            text="Project appearance and persistence",
            padding=10,
        )
        theme_box.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )
        theme_box.columnconfigure(1, weight=1)
        ttk.Label(theme_box, text="Theme").grid(row=0, column=0, sticky="w")
        selector = ttk.Combobox(
            theme_box,
            textvariable=self.project_theme_v126,
            values=tuple(PROJECT_THEMES_V126),
            state="readonly",
        )
        selector.grid(row=0, column=1, sticky="ew", padx=(10, 8))
        selector.bind("<<ComboboxSelected>>", self._preview_project_theme_v126)
        ttk.Button(
            theme_box,
            text="Save Project",
            command=self._save_project_v126,
        ).grid(row=0, column=2, sticky="e")
        ttk.Label(
            theme_box,
            text=(
                "Only Project workspace is required. ISO, Area Server, server saves, "
                "and memory card are optional; their tools and Run All stages are "
                "used when available and skipped otherwise."
            ),
            wraplength=920,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    def _build_settings(self, parent: ttk.Frame) -> None:
        super()._build_settings(parent)
        # Project Setup owns the applied, project-scoped theme. Hide the older
        # inert appearance selector so first-time users see one authority.
        for child in parent.winfo_children():
            try:
                if isinstance(child, ttk.Label) and str(child.cget("text")) == "Theme":
                    info = child.grid_info()
                    child.grid_remove()
                    for sibling in parent.grid_slaves(
                        row=int(info.get("row", 0)),
                        column=1,
                    ):
                        sibling.grid_remove()
                    break
            except (tk.TclError, ValueError):
                continue

    def _create_project(self) -> None:
        workspace = self.setup_vars["workspace"].get().strip()
        if not workspace:
            messagebox.showerror(
                "Create Project",
                "Choose an empty Project workspace folder. All other sources are optional.",
                parent=self,
            )
            return
        try:
            self.project = create_setup_project(
                workspace,
                iso_path=self.setup_vars["iso"].get().strip(),
                area_server_root=self.setup_vars["server"].get().strip(),
                server_save_dir=self.setup_vars["saves"].get().strip(),
                memory_card_path=self.setup_vars["card"].get().strip(),
            )
            self.project.settings[PROJECT_THEME_KEY_V126] = (
                self.project_theme_v126.get()
            )
            save_project(self.project)
            self._project_loaded()
        except Exception as exc:
            messagebox.showerror("Create Project", str(exc), parent=self)

    def _project_loaded(self) -> None:
        project = self.project
        if project is not None:
            selected = str(
                project.settings.get(PROJECT_THEME_KEY_V126) or "Serenial Blue"
            )
            if selected in PROJECT_THEMES_V126:
                self.project_theme_v126.set(selected)
        super()._project_loaded()
        self._apply_project_theme_v126()

    def _save_project_v126(self) -> None:
        project = self._require_project()
        if project is None:
            return
        try:
            project.sources.iso_path = self.setup_vars["iso"].get().strip()
            project.sources.area_server_root = self.setup_vars["server"].get().strip()
            project.sources.server_save_dir = self.setup_vars["saves"].get().strip()
            project.sources.memory_card_path = self.setup_vars["card"].get().strip()
            project.settings[PROJECT_THEME_KEY_V126] = self.project_theme_v126.get()
            project.refresh_source_snapshot()
            save_project(project)
            write_project_status(project)
            self._refresh_all()
            self.after_idle(self._apply_project_theme_v126)
            messagebox.showinfo(
                "Project saved",
                "Project paths and theme were saved. Missing optional sources will be skipped.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Save Project", str(exc), parent=self)

    def _preview_project_theme_v126(self, _event: Any = None) -> None:
        self._apply_project_theme_v126()

    def _apply_project_theme_v126(self) -> None:
        palette = self._palette_v126()
        self.configure(bg=palette["background"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            ".",
            background=palette["panel"],
            foreground=palette["foreground"],
            fieldbackground=palette["field"],
            troughcolor=palette["background"],
            bordercolor=palette["select"],
            lightcolor=palette["select"],
            darkcolor=palette["background"],
        )
        style.configure("TFrame", background=palette["panel"])
        style.configure("TLabel", background=palette["panel"], foreground=palette["foreground"])
        style.configure("TLabelframe", background=palette["panel"], foreground=palette["accent"])
        style.configure("TLabelframe.Label", background=palette["panel"], foreground=palette["accent"])
        style.configure("TButton", background=palette["field"], foreground=palette["foreground"])
        style.map(
            "TButton",
            background=[("active", palette["select"])],
            foreground=[("active", palette["foreground"])],
        )
        style.configure("TNotebook", background=palette["background"])
        style.configure(
            "TNotebook.Tab",
            background=palette["field"],
            foreground=palette["foreground"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", palette["select"])],
            foreground=[("selected", palette["foreground"])],
        )
        style.configure(
            "Treeview",
            background=palette["field"],
            fieldbackground=palette["field"],
            foreground=palette["foreground"],
        )
        style.map(
            "Treeview",
            background=[("selected", palette["select"])],
            foreground=[("selected", palette["foreground"])],
        )

        for name in (
            "_header_frame_v126",
            "_header_identity_v126",
            "_header_image_v126",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(bg=palette["background"])
        for name, foreground in (
            ("_header_title_v126", palette["accent"]),
            ("_header_subtitle_v126", palette["muted"]),
            ("_header_project_v126", palette["foreground"]),
            ("_header_task_v126", palette["accent"]),
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(bg=palette["background"], fg=foreground)

        for widget in self.winfo_children():
            self._theme_children_v126(widget, palette)

    def _theme_children_v126(
        self, widget: tk.Misc, palette: dict[str, str]
    ) -> None:
        if isinstance(widget, tk.Text):
            widget.configure(
                bg=palette["field"],
                fg=palette["foreground"],
                insertbackground=palette["accent"],
                selectbackground=palette["select"],
            )
        elif isinstance(widget, tk.Listbox):
            widget.configure(
                bg=palette["field"],
                fg=palette["foreground"],
                selectbackground=palette["select"],
            )
        elif isinstance(widget, tk.Label):
            try:
                text = str(widget.cget("text"))
                if text == "Game Setup":
                    widget.master.configure(bg=palette["panel"])
                    widget.configure(bg=palette["panel"], fg=palette["accent"])
                elif widget.master is not None and str(widget.master.cget("bg")) in {
                    "#0b2235",
                    PROJECT_THEMES_V126["Serenial Blue"]["panel"],
                    PROJECT_THEMES_V126["Hack Green"]["panel"],
                    PROJECT_THEMES_V126["Twilight Violet"]["panel"],
                    PROJECT_THEMES_V126["Warm Amber"]["panel"],
                }:
                    widget.master.configure(bg=palette["panel"])
                    widget.configure(bg=palette["panel"], fg=palette["muted"])
            except (tk.TclError, AttributeError):
                pass
        for child in widget.winfo_children():
            self._theme_children_v126(child, palette)

    def _refresh_setup(self) -> None:
        self.setup_tree.delete(*self.setup_tree.get_children())
        if self.project is None:
            return
        model = setup_view_model(self.project)
        available: list[str] = []
        for row in model["rows"]:
            if row["ok"]:
                tag = "ok"
                if row["key"] != "workspace":
                    available.append(row["label"])
            elif "optional" in row["status"].lower():
                tag = "optional"
            else:
                tag = "invalid"
            self.setup_tree.insert(
                "",
                "end",
                values=(row["status"], row["path"]),
                tags=(tag,),
            )
        self.setup_tree.tag_configure("ok", foreground="#2c9f55")
        self.setup_tree.tag_configure("optional", foreground="#b98a2d")
        self.setup_tree.tag_configure("invalid", foreground="#d05252")
        if model.get("warnings"):
            self.status_label.set(
                "Project saved; configured paths need attention: "
                + ", ".join(model["warnings"])
            )
        elif available:
            self.status_label.set(
                "Project ready. Available sources: " + ", ".join(available)
            )
        else:
            self.status_label.set(
                "Project ready. No optional sources configured; Run All will skip source-dependent stages."
            )

    def _refresh_server(self) -> None:
        self.server_tree.delete(*self.server_tree.get_children())
        self.server_payloads.clear()
        project = self.project
        if project is None:
            return
        root = (
            Path(project.sources.area_server_root).expanduser()
            if project.sources.area_server_root
            else None
        )
        if not root or not root.is_dir() or not (root / "data").is_dir():
            for widget in self.server_texts.values():
                try:
                    widget.configure(state="normal")
                    widget.delete("1.0", "end")
                    widget.insert(
                        "1.0",
                        "Area Server is not configured for this project. "
                        "Add it in Project Setup and choose Save Project.",
                    )
                    widget.configure(state="disabled")
                except tk.TclError:
                    pass
            return
        super()._refresh_server()

    def _backup_server(self) -> None:
        project = self._require_project()
        if project is None:
            return
        path = (
            Path(project.sources.server_save_dir).expanduser()
            if project.sources.server_save_dir
            else None
        )
        if not path or not path.is_dir():
            messagebox.showinfo(
                "Back Up Server Saves",
                "No usable server-save folder is configured. This optional action was skipped.",
                parent=self,
            )
            return
        super()._backup_server()

    def _backup_card(self) -> None:
        project = self._require_project()
        if project is None:
            return
        path = (
            Path(project.sources.memory_card_path).expanduser()
            if project.sources.memory_card_path
            else None
        )
        if not path or not path.is_file():
            messagebox.showinfo(
                "Back Up Memory Card",
                "No usable memory-card file is configured. This optional action was skipped.",
                parent=self,
            )
            return
        super()._backup_card()

    def _refresh_all(self) -> None:
        super()._refresh_all()
        # Several inherited refresh paths load older appearance settings. The
        # project-scoped V126 palette is the final authority after every refresh.
        self.after_idle(self._apply_project_theme_v126)

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        super()._run_all_done(result, error)
        # RUN ALL finishes by refreshing every tab, which used to repaint with
        # the inherited theme. Reassert the saved project palette afterward.
        self.after_idle(self._apply_project_theme_v126)

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        super()._handle_run_event(event)
        if event.get("kind") == "finish" and event.get("status") == "skipped":
            self._append_log(str(event.get("message") or "Stage skipped."))


def main() -> int:
    app = PublicFragmenterAppV126()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

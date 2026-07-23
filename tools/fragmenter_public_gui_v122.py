#!/usr/bin/env python3
"""V122 adds verified Tellipatch resource installation to guided setup."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tellipatch_native import TellipatchError
from tellipatch_resource_v122 import (
    PATCH_ARCHIVE_SHA256,
    install as install_resource_resolver,
    install_patch_source,
    resolve_patch_archive,
)
from fragmenter_public_gui_v121 import PublicFragmenterAppV121

SETUP_WORKFLOW_TITLE_V122 = "Fragment setup - run these steps in order"
SETUP_WORKFLOW_BUTTONS_V122 = (
    "1. Configure PCSX2",
    "2. Install Translation Resource",
    "3. Create English Preview",
    "4. Verify Setup",
)
ENGLISH_MENU_LABEL_V122 = "Create English Preview..."


class PublicFragmenterAppV122(PublicFragmenterAppV121):
    """Require an exact verified translation resource before ISO analysis/build."""

    def _install_english_menu_v119(self) -> None:
        tools_menu = self._find_tools_menu_v118()
        try:
            end = tools_menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(tools_menu.entrycget(index, "label")) == ENGLISH_MENU_LABEL_V122:
                    return
        except (ValueError, tk.TclError):
            pass
        tools_menu.add_command(
            label=ENGLISH_MENU_LABEL_V122,
            command=self._open_verified_english_builder_v122,
        )

    def _install_acceptance_entrypoints_v120(self) -> None:
        self._install_acceptance_menu_v120()
        self._install_setup_workflow_v122()

    def _install_setup_workflow_v122(self) -> None:
        setup_tab = getattr(self, "tabs", {}).get("Setup")
        if setup_tab is None:
            return

        for child in setup_tab.winfo_children():
            try:
                if str(child.cget("text")) == SETUP_WORKFLOW_TITLE_V122:
                    return
            except (tk.TclError, AttributeError):
                continue

        workflow = ttk.LabelFrame(
            setup_tab,
            text=SETUP_WORKFLOW_TITLE_V122,
            padding=10,
        )
        workflow.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )
        workflow.columnconfigure(0, weight=1)

        ttk.Label(
            workflow,
            text=(
                "Install the translation resource once from the original Tellipatch release ZIP "
                "or the exact official patches.zip. Fragmenter verifies the inner archive SHA-256 "
                f"({PATCH_ARCHIVE_SHA256}) before caching it. Then use the untouched Japanese "
                "source to create a separate -English-Preview.iso."
            ),
            wraplength=760,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        commands = (
            self._open_pcsx2_helper_v118,
            self._install_translation_resource_v122,
            self._open_verified_english_builder_v122,
            self._open_acceptance_v120,
        )
        for row, (label, command) in enumerate(
            zip(SETUP_WORKFLOW_BUTTONS_V122, commands),
            start=1,
        ):
            ttk.Button(workflow, text=label, command=command).grid(
                row=row,
                column=0,
                sticky="ew",
                pady=(0, 5 if row < len(SETUP_WORKFLOW_BUTTONS_V122) else 0),
            )

    def _install_translation_resource_v122(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Choose original Tellipatch release ZIP or patches.zip",
            filetypes=(("ZIP archives", "*.zip"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            report = install_patch_source(selected)
        except (OSError, TellipatchError) as exc:
            messagebox.showerror(
                "Translation resource refused",
                str(exc),
                parent=self,
            )
            return

        source_note = report.get("source_member") or report.get("source_path")
        messagebox.showinfo(
            "Translation resource installed",
            "The exact Tellipatch v3.8 patch archive was verified and cached.\n\n"
            f"Source: {source_note}\n"
            f"Installed: {report['installed_path']}\n"
            f"SHA-256: {report['installed_sha256']}",
            parent=self,
        )

    def _open_verified_english_builder_v122(self) -> None:
        try:
            resolve_patch_archive()
        except TellipatchError as exc:
            messagebox.showerror(
                "Translation resource required",
                str(exc),
                parent=self,
            )
            return
        self._open_english_builder_v119()

    def __init__(self) -> None:
        install_resource_resolver()
        super().__init__()
        self.title("Fragmenter 1.0 - Verified Setup Experimental V122")


def main() -> int:
    app = PublicFragmenterAppV122()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

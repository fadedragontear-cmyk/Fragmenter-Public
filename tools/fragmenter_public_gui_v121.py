#!/usr/bin/env python3
"""V121 exposes the complete setup workflow on the Setup tab."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from fragmenter_public_gui_v120 import PublicFragmenterAppV120

SETUP_WORKFLOW_TITLE = "Fragment setup - run these steps in order"
SETUP_WORKFLOW_BUTTONS = (
    "1. Configure PCSX2",
    "2. Create English Preview",
    "3. Verify Setup",
)


class PublicFragmenterAppV121(PublicFragmenterAppV120):
    """Expose all prerequisites beside the final verification action."""

    def _install_acceptance_entrypoints_v120(self) -> None:
        self._install_acceptance_menu_v120()
        self._install_setup_workflow_v121()

    def _install_setup_workflow_v121(self) -> None:
        setup_tab = getattr(self, "tabs", {}).get("Setup")
        if setup_tab is None:
            return

        for child in setup_tab.winfo_children():
            try:
                if str(child.cget("text")) == SETUP_WORKFLOW_TITLE:
                    return
            except (tk.TclError, AttributeError):
                continue

        workflow = ttk.LabelFrame(
            setup_tab,
            text=SETUP_WORKFLOW_TITLE,
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
                "Use the untouched Japanese source in step 2. Fragmenter creates a new "
                "-English-Preview.iso. Do not choose an existing translated image as the "
                "new output."
            ),
            wraplength=760,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        commands = (
            self._open_pcsx2_helper_v118,
            self._open_english_builder_v119,
            self._open_acceptance_v120,
        )
        for row, (label, command) in enumerate(zip(SETUP_WORKFLOW_BUTTONS, commands), start=1):
            ttk.Button(workflow, text=label, command=command).grid(
                row=row,
                column=0,
                sticky="ew",
                pady=(0, 5 if row < 3 else 0),
            )

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 - Guided Setup Experimental V121")


def main() -> int:
    app = PublicFragmenterAppV121()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

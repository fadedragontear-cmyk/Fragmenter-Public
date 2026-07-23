#!/usr/bin/env python3
"""V92: SNDDATA reconstruction readiness and corrected-sample verification workspace."""
from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from fragmenter_public_gui_v91 import PublicFragmenterAppV91
from snddata_reconstruction_readiness_v1 import (
    audit_project,
    project_paths,
    regenerate_corrected_samples,
    render_report,
    write_noop_roundtrip_proof,
)


class PublicFragmenterAppV92(PublicFragmenterAppV91):
    """Add a truthful extraction/playback/rebuild preflight without changing Celdra production."""

    def __init__(self) -> None:
        self._snddata_readiness_status_v92: tk.StringVar | None = None
        self._snddata_readiness_text_v92: tk.Text | None = None
        self._snddata_readiness_buttons_v92: list[ttk.Button] = []
        self._snddata_readiness_job_v92 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Operation Dragonegg + SNDDATA Readiness V92")

    def _build_audio_research_discovery_pipeline_tabs(
        self,
        notebook: ttk.Notebook,
    ) -> None:
        super()._build_audio_research_discovery_pipeline_tabs(notebook)
        tab = ttk.Frame(notebook, padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)

        ttk.Label(
            tab,
            text="SNDDATA reconstruction readiness",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            tab,
            text=(
                "Separates corrected sample extraction, experimental WAV reconstruction, "
                "safe same-size field patching, and the still-missing full binary serializer."
            ),
            wraplength=1050,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 7))

        actions = ttk.LabelFrame(tab, text="Evidence and preparation", padding=7)
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        actions.columnconfigure(5, weight=1)
        commands = (
            ("Audit current project", self._audit_snddata_readiness_v92),
            ("Regenerate corrected samples", self._regenerate_snddata_samples_v92),
            ("Write no-op round-trip proof", self._write_snddata_noop_proof_v92),
            ("Open audio reports", self._open_snddata_reports_v92),
            ("Copy CLI command", self._copy_snddata_cli_v92),
        )
        for column, (label, command) in enumerate(commands):
            button = ttk.Button(actions, text=label, command=command)
            button.grid(row=0, column=column, sticky="w", padx=(0, 5))
            self._snddata_readiness_buttons_v92.append(button)
        self._snddata_readiness_status_v92 = tk.StringVar(
            value="Run the audit first. Legacy sample reports will be marked for regeneration."
        )
        ttk.Label(
            actions,
            textvariable=self._snddata_readiness_status_v92,
            anchor="w",
            wraplength=650,
        ).grid(row=1, column=0, columnspan=6, sticky="ew", pady=(7, 0))

        report_frame = ttk.LabelFrame(tab, text="Readiness report", padding=4)
        report_frame.grid(row=3, column=0, sticky="nsew")
        report_frame.columnconfigure(0, weight=1)
        report_frame.rowconfigure(0, weight=1)
        text = tk.Text(
            report_frame,
            wrap="word",
            state="disabled",
            background="#10151d",
            foreground="#d6e3f1",
            insertbackground="#d6e3f1",
            font=("Consolas", 9),
            padx=8,
            pady=7,
        )
        scroll = ttk.Scrollbar(report_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._snddata_readiness_text_v92 = text
        self._set_snddata_report_text_v92(
            "No audit has been run in this session.\n\n"
            "The July research bundles were useful routing evidence, but reports without "
            "sample_boundary_policy v2 and layout v2 must be regenerated before the "
            "half/half sample-offset fix can be considered verified.\n"
        )
        notebook.add(tab, text="Reconstruction")

    def _project_for_snddata_v92(self):
        project = getattr(self, "project", None)
        if project is None:
            messagebox.showerror(
                "SNDDATA readiness",
                "Open or create a Fragmenter project first.",
                parent=self,
            )
        return project

    def _set_snddata_report_text_v92(self, value: str) -> None:
        widget = self._snddata_readiness_text_v92
        if widget is None:
            return
        try:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", str(value or ""))
            widget.see("1.0")
            widget.configure(state="disabled")
        except tk.TclError:
            pass

    def _set_snddata_job_state_v92(self, active: bool, status: str) -> None:
        self._snddata_readiness_job_v92 = bool(active)
        for button in self._snddata_readiness_buttons_v92:
            try:
                button.configure(state="disabled" if active else "normal")
            except tk.TclError:
                pass
        if self._snddata_readiness_status_v92 is not None:
            self._snddata_readiness_status_v92.set(status)

    def _run_snddata_job_v92(
        self,
        label: str,
        worker: Callable[[], dict[str, Any]],
    ) -> None:
        if self._snddata_readiness_job_v92:
            messagebox.showwarning(
                "SNDDATA readiness",
                "A reconstruction-readiness task is already active.",
                parent=self,
            )
            return
        self._set_snddata_job_state_v92(True, label)
        self._set_snddata_report_text_v92(
            label
            + "\n\nThis can take several minutes for the full corrected sample catalog."
        )

        def run() -> None:
            try:
                result = worker()
                error = None
            except Exception as exc:
                result = {}
                error = f"{type(exc).__name__}: {exc}"
            try:
                self.after(0, lambda: self._finish_snddata_job_v92(result, error))
            except tk.TclError:
                pass

        threading.Thread(
            target=run,
            name="fragmenter-snddata-readiness",
            daemon=True,
        ).start()

    def _finish_snddata_job_v92(
        self,
        report: dict[str, Any],
        error: str | None,
    ) -> None:
        if error:
            self._set_snddata_job_state_v92(False, f"Failed: {error}")
            self._set_snddata_report_text_v92(
                f"SNDDATA readiness task failed\n\n{error}\n"
            )
            return
        text = render_report(report)
        status = str(
            (report.get("readiness") or {}).get("playback_reconstruction")
            or "unknown"
        )
        self._set_snddata_job_state_v92(
            False,
            f"Audit complete: playback reconstruction {status}.",
        )
        self._set_snddata_report_text_v92(text)

    def _audit_snddata_readiness_v92(self) -> None:
        project = self._project_for_snddata_v92()
        if project is None:
            return
        self._run_snddata_job_v92(
            "Auditing current SNDDATA reports and source structure...",
            lambda: audit_project(project, parse_source=True, write=True),
        )

    def _regenerate_snddata_samples_v92(self) -> None:
        project = self._project_for_snddata_v92()
        if project is None:
            return
        if not messagebox.askyesno(
            "Regenerate corrected samples",
            "Rebuild the canonical SNDDATA sample library with boundary policy v2?\n\n"
            "This deletes and recreates generated sample outputs only. The original snddata.bin is not modified.",
            parent=self,
        ):
            return

        def worker() -> dict[str, Any]:
            regenerate_corrected_samples(project)
            return audit_project(project, parse_source=True, write=True)

        self._run_snddata_job_v92(
            "Regenerating corrected samples, flat catalog, and readiness report...",
            worker,
        )

    def _write_snddata_noop_proof_v92(self) -> None:
        project = self._project_for_snddata_v92()
        if project is None:
            return

        def worker() -> dict[str, Any]:
            write_noop_roundtrip_proof(project)
            return audit_project(project, parse_source=True, write=True)

        self._run_snddata_job_v92(
            "Writing an exact-copy no-op patch proof and reparsing its boundaries...",
            worker,
        )

    def _open_snddata_reports_v92(self) -> None:
        project = self._project_for_snddata_v92()
        if project is None:
            return
        folder = project_paths(project)["reports"]
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror("Open audio reports", str(exc), parent=self)

    def _copy_snddata_cli_v92(self) -> None:
        project = self._project_for_snddata_v92()
        if project is None:
            return
        project_path = Path(project.project_path)
        command = (
            f'python tools\\snddata_reconstruction_readiness_v1.py "{project_path}" '
            "--regenerate-samples --noop-proof"
        )
        try:
            self.clipboard_clear()
            self.clipboard_append(command)
            self.update_idletasks()
        except tk.TclError:
            return
        if self._snddata_readiness_status_v92 is not None:
            self._snddata_readiness_status_v92.set(
                "Copied the full corrected-sample + no-op proof command."
            )


def main() -> int:
    app = PublicFragmenterAppV92()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

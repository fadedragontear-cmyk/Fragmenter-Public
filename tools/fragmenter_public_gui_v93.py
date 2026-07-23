#!/usr/bin/env python3
"""V93: polished SNDDATA verification dashboard and reports-only support export."""
from __future__ import annotations

import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from fragmenter_public_gui_v91 import PublicFragmenterAppV91
from fragmenter_public_gui_v92 import PublicFragmenterAppV92
from snddata_reconstruction_readiness_v1 import (
    audit_project,
    project_paths,
    regenerate_corrected_samples,
    render_report,
    write_noop_roundtrip_proof,
)
from snddata_support_bundle_v1 import build_support_bundle


class PublicFragmenterAppV93(PublicFragmenterAppV92):
    """Keep V91 production behavior while simplifying the audio verification workflow."""

    def __init__(self) -> None:
        self._snddata_cards_v93: dict[str, tk.Label] = {}
        self._snddata_bundle_path_v93: tk.StringVar | None = None
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Operation Dragonegg + Audio Verification V93")

    def _build_audio_research_discovery_pipeline_tabs(self, notebook: ttk.Notebook) -> None:
        # Bypass the dense V92 tab and retain the established V91 Discovery/Pipeline tabs.
        PublicFragmenterAppV91._build_audio_research_discovery_pipeline_tabs(self, notebook)

        tab = ttk.Frame(notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(4, weight=1)

        ttk.Label(
            tab,
            text="SNDDATA verification",
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            tab,
            text=(
                "Use this page after a fresh clone. It verifies the corrected sample extractor, "
                "keeps the original SNDDATA immutable, and creates one small ZIP containing the "
                "reports needed for review."
            ),
            wraplength=1080,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 9))

        cards = ttk.Frame(tab)
        cards.grid(row=2, column=0, sticky="ew", pady=(0, 9))
        for column in range(4):
            cards.columnconfigure(column, weight=1, uniform="snddata-v93")
        for column, (key, title, detail) in enumerate(
            (
                ("source", "1  Source", "Canonical snddata.bin"),
                ("samples", "2  Samples", "Boundary policy v2"),
                ("audition", "3  Audition", "Music preview evidence"),
                ("rebuild", "4  Rebuild", "Binary serializer status"),
            )
        ):
            holder = ttk.Frame(cards, padding=2)
            holder.grid(row=0, column=column, sticky="nsew", padx=(0, 7 if column < 3 else 0))
            label = tk.Label(
                holder,
                text=f"{title}\nNOT CHECKED\n{detail}",
                justify="left",
                anchor="nw",
                padx=10,
                pady=8,
                background="#26313d",
                foreground="#ecf2f8",
                font=("Segoe UI", 9, "bold"),
                relief="flat",
            )
            label.pack(fill="both", expand=True)
            self._snddata_cards_v93[key] = label

        workflow = ttk.LabelFrame(tab, text="Verification workflow", padding=8)
        workflow.grid(row=3, column=0, sticky="ew", pady=(0, 9))
        workflow.columnconfigure(6, weight=1)
        controls = (
            ("Audit", self._audit_snddata_readiness_v92),
            ("Rebuild corrected samples", self._regenerate_snddata_samples_v92),
            ("Write no-op proof", self._write_snddata_noop_proof_v92),
            ("Create support ZIP", self._create_snddata_support_bundle_v93),
            ("Run full verification", self._run_full_snddata_verification_v93),
            ("Open reports", self._open_snddata_reports_v93),
        )
        for column, (label, command) in enumerate(controls):
            button = ttk.Button(workflow, text=label, command=command)
            button.grid(row=0, column=column, sticky="w", padx=(0, 5))
            self._snddata_readiness_buttons_v92.append(button)

        self._snddata_readiness_status_v92 = tk.StringVar(
            value="Start with Audit, or use Run full verification for the complete safe sequence."
        )
        ttk.Label(
            workflow,
            textvariable=self._snddata_readiness_status_v92,
            anchor="w",
            wraplength=1000,
        ).grid(row=1, column=0, columnspan=7, sticky="ew", pady=(8, 0))

        self._snddata_bundle_path_v93 = tk.StringVar(value="Support ZIP: not created")
        ttk.Label(
            workflow,
            textvariable=self._snddata_bundle_path_v93,
            anchor="w",
            wraplength=1000,
        ).grid(row=2, column=0, columnspan=7, sticky="ew", pady=(3, 0))

        report_frame = ttk.LabelFrame(tab, text="Detailed readiness report", padding=4)
        report_frame.grid(row=4, column=0, sticky="nsew")
        report_frame.columnconfigure(0, weight=1)
        report_frame.rowconfigure(0, weight=1)
        text = tk.Text(
            report_frame,
            wrap="word",
            state="disabled",
            background="#0f151c",
            foreground="#d7e2ed",
            insertbackground="#d7e2ed",
            font=("Consolas", 9),
            padx=9,
            pady=8,
        )
        scroll = ttk.Scrollbar(report_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._snddata_readiness_text_v92 = text
        self._set_snddata_report_text_v92(
            "No audit has been run in this fresh session.\n\n"
            "Run full verification performs these safe operations:\n"
            "  1. Audit the current reports and canonical source.\n"
            "  2. Regenerate corrected samples only when the report is stale, legacy, or failing sample zero.\n"
            "  3. Write an exact-copy no-op proof.\n"
            "  4. Refresh the audit and create a reports-only support ZIP.\n\n"
            "The canonical snddata.bin is never modified.\n"
        )
        notebook.add(tab, text="Verification")

    @staticmethod
    def _card_colors_v93(state: str) -> tuple[str, str]:
        return {
            "pass": ("#163c2c", "#dff7e8"),
            "warn": ("#493b16", "#fff0b8"),
            "block": ("#4a2024", "#ffe1e4"),
            "info": ("#26313d", "#ecf2f8"),
        }.get(state, ("#26313d", "#ecf2f8"))

    def _set_card_v93(self, key: str, title: str, state: str, detail: str) -> None:
        label = self._snddata_cards_v93.get(key)
        if label is None:
            return
        background, foreground = self._card_colors_v93(state)
        try:
            label.configure(
                text=f"{title}\n{state.upper()}\n{detail}",
                background=background,
                foreground=foreground,
            )
        except tk.TclError:
            pass

    def _update_snddata_cards_v93(self, report: dict[str, Any]) -> None:
        source = report.get("source") or {}
        samples = report.get("samples") or {}
        music = report.get("music") or {}
        readiness = report.get("readiness") or {}

        self._set_card_v93(
            "source",
            "1  Source",
            "pass" if source.get("exists") else "block",
            f"{int(source.get('size') or 0):,} bytes" if source.get("exists") else "Run Prepare Known Audio",
        )
        sample_pass = bool(
            readiness.get("corrected_extraction")
            and int(samples.get("sample_zero_failures") or 0) == 0
        )
        self._set_card_v93(
            "samples",
            "2  Samples",
            "pass" if sample_pass else "block",
            (
                f"v{samples.get('sample_boundary_policy_version', 0)}/v{samples.get('layout_version', 0)}; "
                f"zero failures={samples.get('sample_zero_failures', 0)}"
            ),
        )
        preview = bool(music.get("last_preview_rendered"))
        self._set_card_v93(
            "audition",
            "3  Audition",
            "pass" if preview else "warn",
            (
                "Preview rendered"
                if preview
                else f"{music.get('renderable_candidates', 0)} renderable candidates"
            ),
        )
        self._set_card_v93(
            "rebuild",
            "4  Rebuild",
            "block",
            str(readiness.get("binary_reconstruction") or "not implemented"),
        )

    def _finish_snddata_job_v92(
        self,
        report: dict[str, Any],
        error: str | None,
    ) -> None:
        if error:
            super()._finish_snddata_job_v92(report, error)
            return
        self._update_snddata_cards_v93(report)
        bundle = report.get("support_bundle") or {}
        body = render_report(report)
        if bundle:
            bundle_path = str(bundle.get("bundle_path") or "")
            body += (
                "\nSupport bundle\n"
                "--------------\n"
                f"Path: {bundle_path}\n"
                f"Included reports: {bundle.get('included_reports', 0)}\n"
                f"Size: {int(bundle.get('bundle_size') or 0):,} bytes\n"
            )
            if self._snddata_bundle_path_v93 is not None:
                self._snddata_bundle_path_v93.set(f"Support ZIP: {bundle_path}")
        status = str((report.get("readiness") or {}).get("playback_reconstruction") or "unknown")
        self._set_snddata_job_state_v92(False, f"Verification complete: playback reconstruction {status}.")
        self._set_snddata_report_text_v92(body)

    def _thread_status_v93(self, text: str) -> None:
        try:
            self.after(
                0,
                lambda: self._snddata_readiness_status_v92.set(text)
                if self._snddata_readiness_status_v92 is not None
                else None,
            )
        except tk.TclError:
            pass

    def _create_snddata_support_bundle_v93(self) -> None:
        project = self._project_for_snddata_v92()
        if project is None:
            return

        def worker() -> dict[str, Any]:
            bundle = build_support_bundle(project, parse_source=True)
            report = audit_project(project, parse_source=False, write=True)
            report["support_bundle"] = bundle
            return report

        self._run_snddata_job_v92("Refreshing the audit and creating a reports-only support ZIP...", worker)

    def _run_full_snddata_verification_v93(self) -> None:
        project = self._project_for_snddata_v92()
        if project is None:
            return
        if not messagebox.askyesno(
            "Run full SNDDATA verification",
            "Run the safe verification sequence?\n\n"
            "Generated samples may be deleted and rebuilt when the current report is legacy, stale, "
            "or still fails sample zero. The original snddata.bin is never modified.",
            parent=self,
        ):
            return

        def worker() -> dict[str, Any]:
            self._thread_status_v93("Step 1/4: auditing source, reports, and parser structure...")
            report = audit_project(project, parse_source=True, write=True)
            samples = report.get("samples") or {}
            needs_samples = (
                samples.get("status") not in {"ready", "corrected_partial"}
                or int(samples.get("sample_zero_failures") or 0) > 0
                or int(samples.get("sample_boundary_policy_version") or 0) < 2
                or int(samples.get("layout_version") or 0) < 2
            )
            if needs_samples:
                self._thread_status_v93("Step 2/4: rebuilding corrected sample and flat catalogs...")
                regenerate_corrected_samples(project)
            else:
                self._thread_status_v93("Step 2/4: corrected samples are current; regeneration skipped.")

            self._thread_status_v93("Step 3/4: writing exact-copy no-op proof...")
            write_noop_roundtrip_proof(project)

            self._thread_status_v93("Step 4/4: refreshing reports and creating support ZIP...")
            bundle = build_support_bundle(project, parse_source=True)
            final = audit_project(project, parse_source=False, write=True)
            final["support_bundle"] = bundle
            final["verification"] = {
                "sample_regeneration_performed": bool(needs_samples),
                "noop_proof_performed": True,
                "support_bundle_created": True,
            }
            return final

        self._run_snddata_job_v92("Starting the four-step SNDDATA verification...", worker)

    def _open_snddata_reports_v93(self) -> None:
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


def main() -> int:
    app = PublicFragmenterAppV93()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V111 audio usability, automation, and progressive-boundary presentation."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any

from celdra_audio_automation_v1 import analyze_audio_workspace
from fragmenter_public_gui import _json_text, _open_path, _replace_text
from snddata_research_workbench_v1 import readiness
from snddata_sample_classification_v1 import (
    available_categories,
    create_category,
    send_to_category,
)
from snddata_sample_health_v1 import sample_library_health


class FragmenterAudioAssistMixinV111:
    """Make classification immediate and automate safe audio evidence processing."""

    def __init__(self) -> None:
        self.classifier_quick_category_v111: tk.StringVar | None = None
        self.classifier_quick_status_v111: tk.StringVar | None = None
        self.classifier_quick_combo_v111: ttk.Combobox | None = None
        self._celdra_audio_status_v111: tk.StringVar | None = None
        self._celdra_audio_pending_v111 = False
        self._celdra_audio_last_report_v111: Path | None = None
        super().__init__()
        self.after_idle(self._sync_classifier_categories_v111)

    # ------------------------------------------------------------------
    # Sample Classifier: project-local categories and rapid assignment.
    # ------------------------------------------------------------------
    def _build_sample_classifier_v47(self, parent: ttk.Frame) -> None:
        super()._build_sample_classifier_v47(parent)
        quick = ttk.LabelFrame(parent, text="Quick classification", padding=(7, 5))
        quick.grid(row=2, column=0, sticky="ew", pady=(7, 0))
        quick.columnconfigure(7, weight=1)
        ttk.Label(quick, text="Send selected to").grid(row=0, column=0, sticky="w")
        self.classifier_quick_category_v111 = tk.StringVar(value="Effect")
        combo = ttk.Combobox(
            quick,
            textvariable=self.classifier_quick_category_v111,
            values=(),
            state="readonly",
            width=20,
        )
        combo.grid(row=0, column=1, sticky="w", padx=(5, 7))
        self.classifier_quick_combo_v111 = combo
        ttk.Button(
            quick,
            text="Send Selected",
            command=self._quick_send_category_v111,
            style="Accent.TButton",
        ).grid(row=0, column=2, padx=(0, 5))
        ttk.Button(
            quick,
            text="Send + Next",
            command=lambda: self._quick_send_category_v111(advance=True),
        ).grid(row=0, column=3, padx=(0, 5))
        ttk.Button(
            quick,
            text="Play + Next",
            command=self._quick_play_next_v111,
        ).grid(row=0, column=4, padx=(0, 12))
        ttk.Button(
            quick,
            text="Create Category",
            command=self._create_classifier_category_v111,
        ).grid(row=0, column=5, padx=(0, 5))
        ttk.Button(
            quick,
            text="Create + Send",
            command=lambda: self._create_classifier_category_v111(assign=True),
        ).grid(row=0, column=6)
        self.classifier_quick_status_v111 = tk.StringVar(
            value="Select a sample, choose a category, then send it without reopening the full editor."
        )
        ttk.Label(
            quick,
            textvariable=self.classifier_quick_status_v111,
            anchor="e",
        ).grid(row=0, column=7, sticky="ew", padx=(12, 0))
        self.after_idle(self._sync_classifier_categories_v111)

    @staticmethod
    def _descendants_v111(widget: tk.Misc):
        for child in widget.winfo_children():
            yield child
            yield from FragmenterAudioAssistMixinV111._descendants_v111(child)

    def _sync_classifier_categories_v111(self) -> tuple[str, ...]:
        project = getattr(self, "project", None)
        if project is None:
            categories = (
                "Unclassified",
                "Instrument",
                "Percussion",
                "Voice",
                "Ambience",
                "Effect",
                "Interface",
                "Unknown",
            )
        else:
            try:
                categories = available_categories(project)
            except Exception:
                categories = (
                    "Unclassified",
                    "Instrument",
                    "Percussion",
                    "Voice",
                    "Ambience",
                    "Effect",
                    "Interface",
                    "Unknown",
                )
        combo = self.classifier_quick_combo_v111
        if combo is not None:
            combo.configure(values=categories)
        variable = self.classifier_quick_category_v111
        if variable is not None and variable.get() not in categories:
            variable.set("Effect" if "Effect" in categories else categories[0])

        tab = getattr(self, "sample_classifier_tab_v47", None)
        if tab is not None:
            filter_var = getattr(self, "classifier_category_filter_v47", None)
            editor_var = getattr(self, "classifier_category_v47", None)
            for child in self._descendants_v111(tab):
                if not isinstance(child, ttk.Combobox):
                    continue
                try:
                    textvariable = str(child.cget("textvariable"))
                    if filter_var is not None and textvariable == str(filter_var):
                        child.configure(values=("All", *categories))
                    elif editor_var is not None and textvariable == str(editor_var):
                        child.configure(values=categories)
                except tk.TclError:
                    continue
        return tuple(categories)

    def _refresh_sample_classifier_v47(self) -> None:
        self._sync_classifier_categories_v111()
        super()._refresh_sample_classifier_v47()

    def _create_classifier_category_v111(self, *, assign: bool = False) -> None:
        project = self._require_project()
        if project is None:
            return
        name = simpledialog.askstring(
            "Create sample category",
            "New project-local category name:",
            parent=self,
        )
        if name is None:
            return
        try:
            created = create_category(project, name)
        except Exception as exc:
            messagebox.showerror("Create sample category", str(exc))
            return
        self._sync_classifier_categories_v111()
        if self.classifier_quick_category_v111 is not None:
            self.classifier_quick_category_v111.set(created)
        if self.classifier_quick_status_v111 is not None:
            self.classifier_quick_status_v111.set(f"Category ready: {created}")
        if assign:
            self._quick_send_category_v111()

    def _quick_send_category_v111(self, *, advance: bool = False) -> None:
        project = self._require_project()
        row = self._selected_classifier_row_v47()
        category = (
            self.classifier_quick_category_v111.get()
            if self.classifier_quick_category_v111 is not None
            else "Unclassified"
        )
        if project is None or row is None:
            messagebox.showinfo("Sample Classifier", "Select a decoded sample first.")
            return
        try:
            saved = send_to_category(
                project,
                int(row.get("resource_offset") or 0),
                int(row.get("sample_id") or 0),
                category,
                source_snapshot=row,
            )
        except Exception as exc:
            messagebox.showerror("Sample Classifier", str(exc))
            return
        selected = self.classifier_tree_v47.selection()
        if selected:
            iid = selected[0]
            row.update(
                {
                    "category": saved.get("category"),
                    "classified": True,
                    "classification_label": saved.get("label"),
                    "playback_mode": saved.get("playback_mode"),
                    "root_note": saved.get("root_note"),
                    "usability": saved.get("usability"),
                }
            )
            try:
                self.classifier_tree_v47.item(iid, text=str(saved.get("label") or row.get("display_name") or "sample"))
                self.classifier_tree_v47.set(iid, "category", str(saved.get("category") or category))
                self.classifier_tree_v47.set(iid, "mode", str(saved.get("playback_mode") or ""))
                self.classifier_tree_v47.set(iid, "root", str(saved.get("root_note") or 60))
                self.classifier_tree_v47.set(iid, "usable", str(saved.get("usability") or "Unreviewed"))
            except tk.TclError:
                pass
        if getattr(self, "classifier_category_v47", None) is not None:
            self.classifier_category_v47.set(str(saved.get("category") or category))
        if self.classifier_quick_status_v111 is not None:
            self.classifier_quick_status_v111.set(
                f"Sent sample {int(row.get('sample_id') or 0):04d} to {saved.get('category')}."
            )
        self._refresh_sequencer_sample_choices_v47()
        if advance:
            self._classifier_move_v111(1, play=False)

    def _classifier_move_v111(self, delta: int, *, play: bool) -> None:
        tree = getattr(self, "classifier_tree_v47", None)
        if tree is None:
            return
        rows = list(tree.get_children(""))
        if not rows:
            return
        selected = tree.selection()
        current = rows.index(selected[0]) if selected and selected[0] in rows else -1
        target = rows[(current + int(delta)) % len(rows)]
        tree.selection_set(target)
        tree.focus(target)
        tree.see(target)
        self._classifier_selected_v47()
        if play:
            self._play_classifier_sample_v47()

    def _quick_play_next_v111(self) -> None:
        self._classifier_move_v111(1, play=True)

    # ------------------------------------------------------------------
    # Celdra mode: prepare only stale/missing stages, then process reports.
    # ------------------------------------------------------------------
    def _build_audio_pipeline_v38(self, parent: ttk.Frame) -> None:
        super()._build_audio_pipeline_v38(parent)
        frame = ttk.LabelFrame(parent, text="Celdra mode - automated audio evidence processing", padding=7)
        frame.grid(row=4, column=0, sticky="ew", pady=(7, 0))
        frame.columnconfigure(3, weight=1)
        ttk.Button(
            frame,
            text="Prepare Missing + Analyze",
            command=self._celdra_prepare_analyze_v111,
            style="Accent.TButton",
        ).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(
            frame,
            text="Analyze Existing Reports",
            command=self._run_celdra_analysis_v111,
        ).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(
            frame,
            text="Open Celdra Report",
            command=self._open_celdra_audio_report_v111,
        ).grid(row=0, column=2, padx=(0, 10))
        self._celdra_audio_status_v111 = tk.StringVar(
            value=(
                "Celdra mode runs deterministic project stages and report analysis. "
                "It never confirms mappings or writes game data."
            )
        )
        ttk.Label(
            frame,
            textvariable=self._celdra_audio_status_v111,
            wraplength=700,
            justify="left",
        ).grid(row=0, column=3, sticky="ew")

    def _audio_stages_needed_v111(self) -> tuple[str, ...]:
        project = getattr(self, "project", None)
        if project is None:
            return ()
        state = readiness(project)
        health = sample_library_health(project)
        stages: list[str] = []
        if not state.get("snddata_exists"):
            stages.extend(("sound_extract", "sound_decode"))
        sample_stale = not state.get("sample_report_exists") or bool(health.get("rebuild_required"))
        if sample_stale:
            stages.append("snddata_samples")
        if not state.get("catalog_exists") or sample_stale:
            stages.append("snddata_mixer")
        return tuple(dict.fromkeys(stages))

    def _prepare_audio_research_v104(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        stages = self._audio_stages_needed_v111()
        if stages:
            self._run_audio_work_v38(stages, "Prepare Audio Research")
            if hasattr(self, "_audio_celdra_say_v98"):
                self._audio_celdra_say_v98(
                    "Preparing current audio evidence",
                    (
                        "Running: " + ", ".join(stages) + ". The sample stage is forced when the report "
                        "predates progressive boundary policy v3, and the mixer is rebuilt after sample changes."
                    ),
                    "excited",
                )
            return
        super()._prepare_audio_research_v104()

    def _celdra_prepare_analyze_v111(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        stages = self._audio_stages_needed_v111()
        if stages:
            self._celdra_audio_pending_v111 = True
            if self._celdra_audio_status_v111 is not None:
                self._celdra_audio_status_v111.set(
                    "Preparing " + ", ".join(stages) + "; analysis will run when those stages finish."
                )
            self._run_audio_work_v38(stages, "Celdra Audio Mode")
            return
        self._run_celdra_analysis_v111()

    def _audio_pipeline_done_v38(self, result: Any, error: Exception | None) -> None:
        super()._audio_pipeline_done_v38(result, error)
        if not self._celdra_audio_pending_v111:
            return
        self._celdra_audio_pending_v111 = False
        if error is not None:
            if self._celdra_audio_status_v111 is not None:
                self._celdra_audio_status_v111.set(f"Celdra preparation failed: {error}")
            return
        self.after_idle(self._run_celdra_analysis_v111)

    def _run_celdra_analysis_v111(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        if self._celdra_audio_status_v111 is not None:
            self._celdra_audio_status_v111.set("Celdra is consolidating sample, classifier, and mixer reports…")

        def done(payload: Any, error: Exception | None) -> None:
            if error is not None:
                if self._celdra_audio_status_v111 is not None:
                    self._celdra_audio_status_v111.set(f"Celdra analysis failed: {error}")
                return
            report = Path(str(payload.get("report_markdown") or ""))
            self._celdra_audio_last_report_v111 = report if report.is_file() else None
            actions = payload.get("next_actions") or []
            first = actions[0] if actions and isinstance(actions[0], dict) else {}
            status = (
                f"Analysis written. Boundary policy v{int((payload.get('sample_boundary') or {}).get('policy_version') or 0)}; "
                f"{int((payload.get('sample_boundary') or {}).get('progressive_drift_banks') or 0)} progressive bank(s). "
                f"Next: {first.get('action') or 'review report'}."
            )
            if self._celdra_audio_status_v111 is not None:
                self._celdra_audio_status_v111.set(status)
            if getattr(self, "audio_pipeline_details_v38", None) is not None:
                _replace_text(self.audio_pipeline_details_v38, _json_text(payload))
            if hasattr(self, "_audio_celdra_say_v98"):
                self._audio_celdra_say_v98(
                    "Automated report processing complete",
                    status + " I did not accept any routing hypothesis or alter the game data.",
                    "suspicious" if first.get("action") == "snddata_samples" else "smile",
                )
            self._sync_classifier_categories_v111()
            self._refresh_reports()

        self._local_worker(
            "celdra-audio-analysis-v111",
            lambda: analyze_audio_workspace(project),
            done,
        )

    def _open_celdra_audio_report_v111(self) -> None:
        project = self._require_project()
        if project is None:
            return
        target = self._celdra_audio_last_report_v111
        if target is None or not target.is_file():
            try:
                payload = analyze_audio_workspace(project)
                target = Path(str(payload.get("report_markdown") or ""))
                self._celdra_audio_last_report_v111 = target if target.is_file() else None
            except Exception as exc:
                messagebox.showerror("Celdra audio report", str(exc))
                return
        try:
            _open_path(target)
        except Exception as exc:
            messagebox.showerror("Celdra audio report", str(exc))

    def _refresh_audio_pipeline_status_v104(self) -> None:
        super()._refresh_audio_pipeline_status_v104()
        project = getattr(self, "project", None)
        variable = getattr(self, "audio_pipeline_status_v38", None)
        if project is None or variable is None:
            return
        try:
            health = sample_library_health(project)
            summary = health.get("summary") or {}
            current = str(variable.get() or "")
            variable.set(
                current
                + f" Boundary v{int((health.get('boundary_policy') or {}).get('version') or 0)}; "
                + f"progressive banks {int(summary.get('progressive_drift_banks') or 0)}."
            )
        except Exception:
            pass

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V111"
            metadata["sample_boundary_policy"] = "v3_constant_or_progressive_per_entry"
            metadata["sample_classifier_quick_assign"] = True
            metadata["sample_classifier_custom_categories"] = True
            metadata["celdra_audio_mode"] = {
                "automates": ["missing_or_stale_audio_stages", "report_consolidation", "next_action_ranking"],
                "accepts_mappings": False,
                "writes_game_data": False,
            }
        return payload

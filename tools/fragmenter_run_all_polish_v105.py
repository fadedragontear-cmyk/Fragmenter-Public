#!/usr/bin/env python3
"""V105 Run All integrity, prepared-list consumption, and Celdra lifecycle polish."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Any

from fragmenter_public_gui import _replace_text
from fragmenter_public_gui_v40 import PublicFragmenterAppV40
from project_sound_v1 import canonical_snddata_path, sound_reports_root
from public_library_cache_v1 import load_cache
from run_all_integrity_v1 import validate_run_all_contract
from snddata_research_workbench_v1 import readiness


class FragmenterRunAllPolishMixinV105:
    """Close lifecycle gaps without replacing the accepted V104 workspaces."""

    def __init__(self) -> None:
        self._run_all_integrity_v105: dict[str, Any] = {}
        self._prepared_sequence_cache_valid_v105 = True
        self._run_stage_active_v105 = ""
        self._celdra_starting_first_scan_v105 = False
        super().__init__()

    # ------------------------------------------------------------------
    # Full-pipeline integrity and visible real-stage tracking.
    # ------------------------------------------------------------------
    def _run_all(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        try:
            report = validate_run_all_contract(project)
        except Exception as exc:
            messagebox.showerror("RUN ALL integrity", f"Pipeline contract check failed:\n\n{exc}")
            return
        self._run_all_integrity_v105 = report
        if not report.get("ok"):
            detail = "\n".join(f"• {value}" for value in report.get("errors") or [])
            messagebox.showerror(
                "RUN ALL integrity",
                "The visible plan and executable pipeline do not agree. RUN ALL was not started.\n\n" + detail,
            )
            return
        self._prepared_sequence_cache_valid_v105 = True
        super()._run_all()
        self._append_console_v49(
            f"[CORE] RUN ALL CONTRACT VERIFIED // {int(report.get('stage_count') or 0)} STAGES // FINAL: {report.get('final_stage')}"
        )
        for warning in report.get("warnings") or []:
            self._append_console_v49(f"[CORE] PIPELINE WARNING // {warning}")

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        super()._handle_run_event(event)
        if not bool(getattr(self, "_celdra_session_active_v49", False)):
            return
        stage = str(event.get("stage") or "")
        label = str(event.get("label") or stage or "pipeline stage")
        kind = str(event.get("kind") or "")
        if kind == "start":
            self._run_stage_active_v105 = stage
            self._append_console_v49(f"[PIPELINE] START // {label} // {stage}")
        elif kind == "finish":
            status = str(event.get("status") or "complete")
            self._append_console_v49(f"[PIPELINE] FINISH // {label} // {status.upper()}")
            if status == "failed":
                error = str(event.get("error") or "No error detail was supplied.")
                self._append_console_v49(f"[PIPELINE] ERROR // {error}")
                self._audio_celdra_say_v98(
                    "Run All stage failed",
                    f"{label} failed. The exact pipeline error was preserved in the console: {error}",
                    "sad",
                )
            elif stage == "public_lists":
                summary = load_cache(self.project, "summary") if self.project is not None else None
                errors = (summary or {}).get("errors") or {}
                if errors:
                    self._append_console_v49(
                        "[CORE] PUBLIC LISTS PARTIAL // "
                        + " // ".join(f"{key}: {value}" for key, value in errors.items())
                    )
                else:
                    self._append_console_v49(
                        "[CORE] PUBLIC LISTS READY // 3D ASSETS + PLAYABLE WAVS + SNDDATA SEQUENCES"
                    )

    # ------------------------------------------------------------------
    # Audio-only preparation now includes every dependency and the cache.
    # ------------------------------------------------------------------
    def _audio_workspace_stages_v105(self) -> tuple[str, ...]:
        project = self._require_project()
        if project is None:
            return ()
        reports = sound_reports_root(project)
        state = readiness(project)
        stages: list[str] = []

        source_missing = not (reports / "sound_source_manifest.json").is_file() or not canonical_snddata_path(project).is_file()
        decode_missing = not (reports / "sound_decode_report.json").is_file()
        samples_missing = not bool(state.get("sample_report_exists"))
        mixer_missing = not bool(state.get("catalog_exists"))

        if source_missing:
            stages.append("sound_extract")
            decode_missing = True
            samples_missing = True
            mixer_missing = True
        if decode_missing:
            stages.append("sound_decode")
        if samples_missing:
            stages.append("snddata_samples")
            mixer_missing = True
        if mixer_missing:
            stages.append("snddata_mixer")

        # This final stage is cheap relative to extraction and is what makes the
        # first Audio/3D click immediate. The cache builder is partial-safe, so an
        # audio-only repair does not require a completed visual extraction.
        stages.append("public_lists")
        return tuple(dict.fromkeys(stages))

    def _prepare_audio_research_v104(self) -> None:
        project = self._require_project()
        if project is None or self.task_active:
            return
        stages = self._audio_workspace_stages_v105()
        if not stages:
            return
        self._prepared_sequence_cache_valid_v105 = True
        self._run_audio_work_v38(stages, "Prepare Complete Audio Workspace")
        self._audio_celdra_say_v98(
            "Preparing the complete audio workspace",
            "One operation now covers missing source extraction, direct playable decoding, corrected SNDDATA samples, the mixer index, and the prepared public lists. Raw PCM and containers remain outside the normal library.",
            "excited",
        )

    def _audio_pipeline_done_v38(self, result: Any, error: Exception | None) -> None:
        complete = not error and isinstance(result, dict) and str(result.get("status") or "") == "complete"
        self._prepared_sequence_cache_valid_v105 = complete
        super()._audio_pipeline_done_v38(result, error)
        if complete:
            summary = load_cache(self.project, "summary") if self.project is not None else None
            errors = (summary or {}).get("errors") or {}
            if errors:
                self._audio_celdra_say_v98(
                    "Audio prepared; some lists remain partial",
                    "The audio stages completed, but the public-list summary still reports: "
                    + "; ".join(f"{key}: {value}" for key, value in errors.items()),
                    "suspicious",
                )
            else:
                self._audio_celdra_say_v98(
                    "Audio workspace ready",
                    "Playable WAVs, corrected samples, the sequence catalog, and the prepared lists are ready. Choose a sequence marked Ready and inspect its best non-rejected Program candidate.",
                    "smile",
                )

    # ------------------------------------------------------------------
    # Consume the sequence cache that RUN ALL already paid to build.
    # ------------------------------------------------------------------
    @staticmethod
    def _filter_prepared_sequences_v105(
        rows: list[dict[str, Any]],
        query: str,
        status_filter: str,
    ) -> list[dict[str, Any]]:
        needle = str(query or "").strip().casefold()
        selected_filter = str(status_filter or "All")
        output: list[dict[str, Any]] = []
        for row in rows:
            haystack = " ".join(
                str(row.get(key) or "")
                for key in (
                    "sequence_id",
                    "preferred_hypothesis",
                    "reviewed_routing_mode",
                    "routing_status",
                    "first_wall",
                )
            ).casefold()
            saved = row.get("saved_mapping") or {}
            haystack += " " + str(saved.get("program_resource") or "").casefold()
            if needle and needle not in haystack:
                continue
            if selected_filter == "Renderable" and int(row.get("renderable") or 0) <= 0:
                continue
            if selected_filter == "Needs research" and (saved or int(row.get("review_count") or 0)):
                continue
            if selected_filter == "Saved mapping" and not saved:
                continue
            if selected_filter == "Reviewed" and int(row.get("review_count") or 0) <= 0:
                continue
            output.append(dict(row))
        return output

    def _refresh_audio_sequences(self, preselect: str | None = None) -> None:
        project = getattr(self, "project", None)
        cache = load_cache(project, "sequences") if project is not None and self._prepared_sequence_cache_valid_v105 else None
        if not cache or not bool(cache.get("ready")):
            PublicFragmenterAppV40._refresh_audio_sequences(self, preselect)
            return

        self._mixer_sequence_generation_v40 += 1
        generation = self._mixer_sequence_generation_v40
        self.sequence_tree.delete(*self.sequence_tree.get_children())
        self.program_tree.delete(*self.program_tree.get_children())
        self.audio_sample_tree_v40.delete(*self.audio_sample_tree_v40.get_children())
        self._mixer_sequence_rows_v40.clear()
        self._mixer_candidate_rows_v40.clear()
        self._mixer_sample_rows_v40.clear()
        query = self.audio_sequence_search_v40.get() if self.audio_sequence_search_v40 is not None else ""
        status_filter = self.audio_sequence_filter_v40.get() if self.audio_sequence_filter_v40 is not None else "All"
        self.audio_status.set("Loading the prepared RUN ALL sequence list…")
        self.audio_progress.configure(mode="indeterminate")
        self.audio_progress.start(60)

        def work() -> list[dict[str, Any]]:
            rows = [dict(row) for row in cache.get("items") or [] if isinstance(row, dict)]
            return self._filter_prepared_sequences_v105(rows, query, status_filter)

        def done(rows: Any, error: Exception | None) -> None:
            if generation != self._mixer_sequence_generation_v40:
                return
            self.audio_progress.stop()
            self.audio_progress.configure(mode="determinate")
            if error:
                self.audio_progress["value"] = 0.0
                self.audio_status.set(f"Prepared sequence list failed: {error}")
                return
            self.audio_progress["value"] = 100.0
            selected_iid = None
            for index, row in enumerate(rows):
                iid = f"sequence_{index}"
                saved = row.get("saved_mapping") or {}
                reviewed = int(row.get("review_count") or 0)
                review_text = str(saved.get("status") or "")
                if reviewed:
                    review_text = f"{review_text or 'reviewed'} ({reviewed})"
                routing = str(row.get("preferred_hypothesis") or "unresolved")
                self.sequence_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=str(row.get("sequence_id") or "sequence"),
                    values=(
                        int(row.get("note_on_count") or 0),
                        int(row.get("track_count") or 0),
                        routing,
                        int(row.get("renderable") or 0),
                        review_text,
                    ),
                )
                self._mixer_sequence_rows_v40[iid] = row
                if preselect and str(row.get("sequence_id") or "") == preselect:
                    selected_iid = iid
            selected_iid = selected_iid or next(iter(self._mixer_sequence_rows_v40), None)
            if selected_iid:
                self.sequence_tree.selection_set(selected_iid)
                self.sequence_tree.focus(selected_iid)
                self.sequence_tree.see(selected_iid)
                self._refresh_audio_candidates()
            else:
                _replace_text(self.audio_details, "No prepared sequences match the current search/filter.")
            renderable = sum(int(row.get("renderable") or 0) > 0 for row in rows)
            saved_count = sum(bool(row.get("saved_mapping")) for row in rows)
            self.audio_status.set(
                f"Prepared list: {len(rows)} sequences shown; {renderable} have a renderer-complete candidate; {saved_count} saved mappings."
            )

        self._local_worker("prepared-snddata-sequences-v105", work, done)

    def _review_candidate_v40(self, status: str) -> None:
        self._prepared_sequence_cache_valid_v105 = False
        super()._review_candidate_v40(status)

    def _clear_candidate_review_v40(self) -> None:
        self._prepared_sequence_cache_valid_v105 = False
        super()._clear_candidate_review_v40()

    def _rebuild_mixer_index_v40(self) -> None:
        self._prepared_sequence_cache_valid_v105 = False
        super()._rebuild_mixer_index_v40()

    # ------------------------------------------------------------------
    # Celdra scene ownership and safe restoration on every early exit.
    # ------------------------------------------------------------------
    def _first_scan_egg_lock_v105(self) -> bool:
        return bool(self._celdra_starting_first_scan_v105) or bool(
            getattr(self, "_celdra_session_active_v49", False)
            and getattr(self, "_celdra_first_scan_v49", False)
            and not getattr(self, "_celdra_intro_gate_open_v99", False)
        )

    def _hide_middle_for_egg_v105(self) -> None:
        frame = getattr(self, "_celdra_middle_frame_v101", None)
        pane = getattr(self, "celdra_visual_split_v50", None)
        self._cancel_middle_animation_v101()
        if frame is None or pane is None:
            return
        try:
            if str(frame) in tuple(str(value) for value in pane.panes()):
                pane.forget(frame)
            self._celdra_middle_hidden_v103 = True
        except (AttributeError, tk.TclError):
            pass

    def _install_gremlin_stable_v101(self) -> None:
        if not bool(getattr(self, "_celdra_stable_reveal_v103", False)):
            return
        if bool(getattr(self, "_celdra_middle_hidden_v103", False)):
            self._show_middle_after_chaos_v103("stable")
        super()._install_gremlin_stable_v101()

    def _cancel_internal_show_v101(self) -> None:
        egg_lock = self._first_scan_egg_lock_v105()
        self._destroy_internal_chaos_v103()
        if egg_lock:
            self._celdra_stable_reveal_v103 = False
            super()._cancel_internal_show_v101()
            self._hide_middle_for_egg_v105()
            return

        hidden = bool(getattr(self, "_celdra_middle_hidden_v103", False))
        if hidden:
            mode = "stable" if self._stable_names_v101() else "attention"
            self._show_middle_after_chaos_v103(mode)
        super()._cancel_internal_show_v101()
        if self._stable_names_v101():
            self._celdra_stable_reveal_v103 = True
            self._show_middle_after_chaos_v103("stable")
            self._install_gremlin_stable_v101()
        elif getattr(self, "_celdra_middle_frame_v101", None) is None:
            self._celdra_middle_hidden_v103 = False

    def _start_celdra_session_v49(self, first_scan: bool) -> None:
        self._celdra_starting_first_scan_v105 = bool(first_scan)
        if first_scan:
            self._celdra_stable_reveal_v103 = False
        try:
            super()._start_celdra_session_v49(first_scan)
        finally:
            self._celdra_starting_first_scan_v105 = False
        if first_scan:
            self._hide_middle_for_egg_v105()
        elif self._stable_names_v101():
            self._celdra_stable_reveal_v103 = True
            self.after_idle(self._install_gremlin_stable_v101)
        self._append_console_v49(
            "[CORE] CELDRA DIRECTOR V105 // REAL PIPELINE EVENTS AUTHORITATIVE // PRESENTATION TIMERS NON-BLOCKING"
        )

    def _end_celdra_session_v49(self) -> None:
        super()._end_celdra_session_v49()
        if (
            self._stable_names_v101()
            and not self._first_scan_egg_lock_v105()
            and bool(getattr(self, "_celdra_intro_gate_open_v99", False) or not getattr(self, "_celdra_first_scan_v49", False))
        ):
            self._celdra_stable_reveal_v103 = True
            self.after_idle(self._install_gremlin_stable_v101)

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        complete = not error and isinstance(result, dict) and str(result.get("status") or "") == "complete"
        self._prepared_sequence_cache_valid_v105 = complete
        super()._run_all_done(result, error)
        if complete:
            summary = load_cache(self.project, "summary") if self.project is not None else None
            if summary:
                self._append_console_v49(
                    f"[CORE] PREPARED LIST SUMMARY // {int(summary.get('visual_assets') or 0)} VISUAL // "
                    f"{int(summary.get('playable_sounds') or 0)} PLAYABLE WAV // "
                    f"{int(summary.get('snddata_sequences') or 0)} SEQUENCES // {str(summary.get('status') or '').upper()}"
                )

    def _completion_text_v87(self) -> str:
        base = super()._completion_text_v87()
        project = getattr(self, "project", None)
        summary = load_cache(project, "summary") if project is not None else None
        if not summary:
            return base
        return (
            base
            + f" Prepared lists contain {int(summary.get('visual_assets') or 0):,} visual assets, "
            + f"{int(summary.get('playable_sounds') or 0):,} playable sounds, and "
            + f"{int(summary.get('snddata_sequences') or 0):,} SNDDATA sequences."
        )

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V105"
            metadata["run_all_contract_audit"] = True
            metadata["public_lists_final_stage"] = True
            metadata["prepared_sequence_cache_consumed"] = True
            metadata["audio_prepare_includes_public_lists"] = True
            metadata["celdra_chaos_early_exit_restores_middle_pane"] = True
            metadata["celdra_egg_first_cleanup_lock"] = True
            metadata["celdra_real_stage_tracking"] = True
        return payload

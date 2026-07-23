#!/usr/bin/env python3
"""V96: live pipeline reactions and the personality-driven hatchling Gremlin riot."""
from __future__ import annotations

import json
import time
import tkinter as tk
from typing import Any, Callable

from celdra_evolution_pixel_v4 import (
    HATCHLING_BASE_CLAIM,
    HATCHLING_BASE_FAILED,
    HATCHLING_IDLE,
    HATCHLING_SEARCH,
    HATCHLING_SQUISHED,
)
from celdra_v96_content import (
    CONSOLE_BANTER,
    GREMLIN_HAVOC_STAGES,
    GREMLIN_PERSONALITIES,
    GREMLIN_START_DELAY_MS,
    GREMLIN_SWARM_SIZE,
    PROGRESS_REACTIONS,
    STAGE_SCENES,
    STORY_END_DELAY_MS,
    STORY_FILLER,
    WAITING_FILLER,
    WAITING_FILLER_DELAY_MS,
)
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v95 import PublicFragmenterAppV95


class PublicFragmenterAppV96(PublicFragmenterAppV95):
    """React to actual RUN ALL events and give every restored hatchling a role."""

    STORY_FILLER = STORY_FILLER
    INITIAL_CONSOLE_BANTER = CONSOLE_BANTER
    WAITING_FILLER = WAITING_FILLER
    STORY_END_DELAY_MS = STORY_END_DELAY_MS
    WAITING_FILLER_DELAY_MS = WAITING_FILLER_DELAY_MS
    GREMLIN_START_DELAY_MS = GREMLIN_START_DELAY_MS
    GREMLIN_SWARM_SIZE = GREMLIN_SWARM_SIZE

    RAGE_COLORS = (
        "#5f070c",
        "#7d0a11",
        "#a50d18",
        "#cf1624",
        "#ef2939",
        "#ff4b57",
        "#ff747d",
    )

    def __init__(self) -> None:
        self._celdra_ccsf_metrics_v96: dict[str, Any] = {}
        self._celdra_ccsf_jump_reacted_v96 = False
        self._celdra_live_stage_started_v96: set[str] = set()
        self._celdra_live_stage_finished_v96: set[str] = set()
        self._celdra_live_progress_marks_v96: set[tuple[str, int]] = set()
        self._celdra_live_scene_queue_v96: list[tuple[str, str, int]] = []
        self._celdra_live_scene_after_v96: str | None = None
        self._celdra_ambient_rage_v96 = False
        self._celdra_gremlin_personality_serial_v96 = 0
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Live Pipeline + Gremlin Riot V96")

    # ------------------------------------------------------------------
    # Actual RUN ALL event commentary.
    # ------------------------------------------------------------------
    @staticmethod
    def _overall_progress_value_v96(widget: Any) -> float:
        try:
            return float(widget["value"])
        except (KeyError, TypeError, ValueError, tk.TclError):
            return 0.0

    def _stage_label_v96(self, stage: str) -> str:
        row = getattr(self, "_pipeline_plan_rows_v38", {}).get(stage) or {}
        return str(row.get("label") or stage.replace("_", " ").title())

    def _stage_position_v96(self, stage: str) -> tuple[int, int]:
        order = list(getattr(self, "_stage_order", ()) or ())
        try:
            index = order.index(stage) + 1
        except ValueError:
            index = 0
        return index, len(order)

    def _handle_run_event(self, event: dict[str, Any]) -> None:
        before = self._overall_progress_value_v96(getattr(self, "overall_progress", {}))
        super()._handle_run_event(event)
        after = self._overall_progress_value_v96(getattr(self, "overall_progress", {}))
        self._handle_live_pipeline_event_v96(event, before=before, after=after)

    def _handle_live_pipeline_event_v96(
        self,
        event: dict[str, Any],
        *,
        before: float,
        after: float,
    ) -> None:
        if not bool(getattr(self, "_celdra_session_active_v49", False)):
            return
        stage = str(event.get("stage") or "")
        kind = str(event.get("kind") or "")
        status = str(event.get("status") or "")
        if not stage:
            return

        if kind == "output" and stage == "ccsf_extract":
            self._consume_ccsf_output_v96(str(event.get("line") or ""))
            return

        if kind == "start":
            if stage in self._celdra_live_stage_started_v96:
                return
            self._celdra_live_stage_started_v96.add(stage)
            index, total = self._stage_position_v96(stage)
            suffix = f" {index:02d}/{total:02d}" if index and total else ""
            self._append_console_v49(
                f"[CORE] RUN ALL STAGE{suffix} START: {self._stage_label_v96(stage).upper()}"
            )
            scene = STAGE_SCENES.get(stage)
            if scene is not None:
                self._queue_live_scene_v96(
                    str(scene.get("pose") or "smile"),
                    str(scene.get("start") or ""),
                    hold_ms=9_500,
                )
            return

        if kind == "progress":
            percent = event.get("percent")
            if isinstance(percent, (int, float)):
                self._handle_stage_progress_v96(stage, float(percent), str(event.get("detail") or ""))
            return

        if kind != "finish":
            return
        if stage not in self._celdra_live_stage_finished_v96:
            self._celdra_live_stage_finished_v96.add(stage)
            index, total = self._stage_position_v96(stage)
            suffix = f" {index:02d}/{total:02d}" if index and total else ""
            final_status = status or "complete"
            self._append_console_v49(
                f"[CORE] RUN ALL STAGE{suffix} {final_status.upper()}: {self._stage_label_v96(stage).upper()}"
            )
            if final_status == "failed":
                self._append_console_v49(
                    f"[BRAIN] {self._stage_label_v96(stage).upper()} FAILED. KEEP THE LOGS WHERE I CAN SEE THEM."
                )
            else:
                scene = STAGE_SCENES.get(stage)
                if scene is not None and stage != "refresh":
                    self._queue_live_scene_v96(
                        str(scene.get("pose") or "smile"),
                        str(scene.get("finish") or ""),
                        hold_ms=8_500,
                    )

        if stage == "ccsf_extract" and status in {"complete", "reused"}:
            self._react_to_ccsf_gate_v96(before=before, after=after, reused=status == "reused")

    def _consume_ccsf_output_v96(self, line: str) -> None:
        text = str(line or "").strip()
        if not text.startswith("{"):
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict) or not any(
            key in payload
            for key in (
                "container_index",
                "container_total",
                "bytes_scanned",
                "ccsf_bundles_extracted",
                "assets_indexed",
            )
        ):
            return
        self._celdra_ccsf_metrics_v96.update(payload)
        current = int(payload.get("container_index") or 0)
        total = int(payload.get("container_total") or 0)
        if current <= 0 or total <= 0:
            return
        percent = min(100.0, current * 100.0 / total)
        self._handle_stage_progress_v96("ccsf_extract", percent, self._ccsf_metric_text_v96())

    def _ccsf_metric_text_v96(self) -> str:
        data = self._celdra_ccsf_metrics_v96
        current = int(data.get("container_index") or 0)
        total = int(data.get("container_total") or 0)
        bytes_scanned = int(data.get("bytes_scanned") or 0)
        bundles = int(data.get("ccsf_bundles_extracted") or 0)
        assets = int(data.get("assets_indexed") or 0)
        mib = bytes_scanned / (1024 * 1024)
        return (
            f"containers {current:,}/{total:,} // {mib:,.1f} MiB scanned // "
            f"{bundles:,} CCSF bundles // {assets:,} indexed assets"
        )

    def _handle_stage_progress_v96(self, stage: str, percent: float, detail: str) -> None:
        for mark in (25, 50, 75):
            marker = (stage, mark)
            if percent < mark or marker in self._celdra_live_progress_marks_v96:
                continue
            self._celdra_live_progress_marks_v96.add(marker)
            summary = detail.strip() or f"{percent:.0f}%"
            self._append_console_v49(
                f"[CORE] {self._stage_label_v96(stage).upper()} {mark}% // {summary}"
            )
            reactions = PROGRESS_REACTIONS.get(stage)
            if reactions:
                pose = ("suspicious", "smile", "excited")[(mark // 25 - 1) % 3]
                self._queue_live_scene_v96(pose, reactions[mark // 25 - 1], hold_ms=8_000)

    def _react_to_ccsf_gate_v96(self, *, before: float, after: float, reused: bool) -> None:
        if self._celdra_ccsf_jump_reacted_v96:
            return
        self._celdra_ccsf_jump_reacted_v96 = True
        if after < before:
            after = before
        mode = "REUSED VERIFIED OUTPUT" if reused else "EXTRACTION COMPLETE"
        self._append_console_v49(
            f"[CORE] CCSF GATE {mode} // OVERALL RUN ALL {before:.0f}% -> {after:.0f}%"
        )
        metrics = self._ccsf_metric_text_v96()
        self._queue_live_scene_v96(
            "excited",
            f"There it is—the long CCSF gate just moved the whole run from about twenty-one percent to twenty-seven. {metrics}.",
            hold_ms=10_500,
            priority=True,
        )
        self._queue_live_scene_v96(
            "smile",
            "That jump means we have crossed from scanning containers into verifying a real extracted library. The remaining stages can work from evidence instead of the raw disc.",
            hold_ms=10_500,
            priority=True,
        )
        self._queue_live_scene_v96(
            "suspicious",
            "Next comes asset verification and extraction audit. A folder full of files is encouraging; provenance and coverage are what make it trustworthy.",
            hold_ms=9_500,
            priority=True,
        )

    # ------------------------------------------------------------------
    # Small live-scene queue.  Gremlin choreography owns the viewport while
    # active; actual CORE status lines continue and Celdra reactions resume after.
    # ------------------------------------------------------------------
    def _queue_live_scene_v96(
        self,
        pose: str,
        text: str,
        *,
        hold_ms: int,
        priority: bool = False,
    ) -> None:
        clean = str(text or "").strip()
        if not clean:
            return
        row = (str(pose or "smile"), clean, max(2_000, int(hold_ms)))
        if priority:
            self._celdra_live_scene_queue_v96.insert(0, row)
        else:
            self._celdra_live_scene_queue_v96.append(row)
        if self._celdra_live_scene_after_v96 is None:
            self._play_next_live_scene_v96()

    def _play_next_live_scene_v96(self) -> None:
        self._celdra_live_scene_after_v96 = None
        if not self._celdra_live_scene_queue_v96:
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            self._celdra_live_scene_queue_v96.clear()
            return
        if bool(getattr(self, "_celdra_gremlin_active_v94", False)):
            self._celdra_live_scene_after_v96 = self.after(
                self._scaled_runtime_ms_v88(3_000),
                self._play_next_live_scene_v96,
            )
            return
        if not bool(getattr(self, "_celdra_takeover_active_v58", False)):
            self._celdra_live_scene_after_v96 = self.after(
                self._scaled_runtime_ms_v88(2_500),
                self._play_next_live_scene_v96,
            )
            return
        pose, text, hold_ms = self._celdra_live_scene_queue_v96.pop(0)
        self._runtime_pose_v70(pose, text)
        self._celdra_live_scene_after_v96 = self.after(
            self._scaled_runtime_ms_v88(hold_ms),
            self._play_next_live_scene_v96,
        )

    def _clear_live_scene_queue_v96(self) -> None:
        if self._celdra_live_scene_after_v96 is not None:
            try:
                self.after_cancel(self._celdra_live_scene_after_v96)
            except tk.TclError:
                pass
            self._celdra_live_scene_after_v96 = None
        self._celdra_live_scene_queue_v96.clear()

    # ------------------------------------------------------------------
    # Nine named Gremlins, each retaining a separate behavior profile.
    # ------------------------------------------------------------------
    @staticmethod
    def _personality_sequence_v96(temperament: str):
        return {
            "search": HATCHLING_SEARCH,
            "claim": HATCHLING_BASE_CLAIM,
            "squished": HATCHLING_SQUISHED,
            "failed": HATCHLING_BASE_FAILED,
            "idle": HATCHLING_IDLE,
        }.get(str(temperament or "idle"), HATCHLING_IDLE)

    def _start_gremlin_show_v94(self) -> None:
        if self._celdra_gremlin_active_v94:
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._celdra_gremlin_active_v94 = True
        self._celdra_gremlin_token_v94 += 1
        self._celdra_gremlin_reported_stages_v94.clear()
        self._runtime_pose_v70(
            "wink",
            "Wanna see the retired hatchling build? I gave each copy a job. CORE calls that an uncontrolled process taxonomy. I call it staffing.",
        )
        self._schedule_gremlin_v94(2_500, self._spawn_gremlin_swarm_v95)
        self._schedule_gremlin_v94(6_500, self._introduce_gremlin_personalities_v96)
        self._schedule_gremlin_v94(11_000, self._scatter_gremlin_swarm_v95)
        self._schedule_gremlin_v94(16_000, self._push_console_with_swarm_v95)
        self._schedule_gremlin_v94(21_000, self._start_gremlin_havoc_v95)
        self._schedule_gremlin_v94(30_000, self._tour_ui_with_swarm_v95)
        self._schedule_gremlin_v94(39_000, self._form_gremlin_parties_v95)
        self._schedule_gremlin_v94(47_000, self._gremlins_annoy_celdra_v96)
        self._schedule_gremlin_v94(56_000, self._celdra_gremlin_rage_v96)
        self._schedule_gremlin_v94(67_000, self._banish_gremlins_v96)
        self._schedule_gremlin_v94(82_000, self._finish_gremlin_banishment_v96)

    def _spawn_gremlin_swarm_v95(self) -> None:
        super()._spawn_gremlin_swarm_v95()
        if not self._celdra_gremlin_swarm_v95:
            return
        targets = []
        avatar = self.celdra_avatar_canvas_v50
        positions = (
            (0.08, 0.18),
            (0.27, 0.10),
            (0.48, 0.18),
            (0.70, 0.10),
            (0.90, 0.20),
            (0.15, 0.72),
            (0.38, 0.82),
            (0.64, 0.80),
            (0.86, 0.70),
        )
        for index, item in enumerate(self._celdra_gremlin_swarm_v95):
            personality = dict(GREMLIN_PERSONALITIES[index % len(GREMLIN_PERSONALITIES)])
            item["personality"] = personality
            item["sequence"] = self._personality_sequence_v96(str(personality.get("temperament")))
            try:
                item["holder"].configure(
                    highlightbackground=str(personality.get("accent") or "#45a9db"),
                    highlightcolor=str(personality.get("accent") or "#45a9db"),
                )
            except tk.TclError:
                pass
            targets.append(self._widget_point_v94(avatar, *positions[index % len(positions)]))
        self._animate_swarm_to_v95(targets, 1_800)

    def _start_swarm_animation_v95(self) -> None:
        if self._celdra_gremlin_swarm_animation_after_v95 is not None:
            return
        token = self._celdra_gremlin_token_v94

        def tick() -> None:
            self._celdra_gremlin_swarm_animation_after_v95 = None
            if token != self._celdra_gremlin_token_v94 or not self._celdra_gremlin_active_v94:
                return
            self._celdra_gremlin_swarm_phase_v95 += 1
            self._position_gremlin_status_v95()
            for item in tuple(self._celdra_gremlin_swarm_v95):
                sequence = tuple(item.get("sequence") or HATCHLING_IDLE)
                if not sequence:
                    continue
                index = int(item.get("index") or 0)
                cadence = 1 + (index % 3)
                frame_index = (
                    self._celdra_gremlin_swarm_phase_v95 // cadence + index * 2
                ) % len(sequence)
                item["frame"] = frame_index
                self._draw_personality_hatchling_v96(item, sequence[frame_index])
                try:
                    item["holder"].lift()
                except tk.TclError:
                    pass
            self._celdra_gremlin_swarm_animation_after_v95 = self.after(
                max(45, self._scaled_runtime_ms_v88(145)),
                tick,
            )

        self._celdra_gremlin_swarm_animation_after_v95 = self.after(40, tick)

    def _draw_personality_hatchling_v96(self, item: dict[str, Any], frame: Any) -> None:
        canvas = item.get("canvas")
        if not isinstance(canvas, tk.Canvas):
            return
        PublicFragmenterAppV95._draw_hatchling_frame_v95(canvas, frame)
        personality = item.get("personality") if isinstance(item.get("personality"), dict) else {}
        name = str(personality.get("name") or f"G{int(item.get('index') or 0) + 1}")
        accent = str(personality.get("accent") or "#c7f2ff")
        try:
            canvas.create_rectangle(2, 61, 70, 71, fill="#071426", outline="", tags="v96_nameplate")
            canvas.create_text(
                36,
                66,
                text=name,
                fill=accent,
                font=("Fixedsys", 7, "bold"),
                anchor="center",
                tags="v96_nameplate",
            )
        except tk.TclError:
            pass

    def _introduce_gremlin_personalities_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._append_console_v49(
            "[CORE] GREMLIN ROSTER: BYTE / HEX / CACHE / LOOP / PING / PATCH / ROOT / NULL / GLITCH"
        )
        self._append_console_v49("[BRAIN] WHY DO THEY HAVE NAMES. NAMES ARE HOW THEY BECOME RECURRING.")
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(
                "9 PERSONALITIES ONLINE // 0 WRITE TARGETS // 9 UNFOUNDED OPINIONS"
            )

    def _gremlins_annoy_celdra_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        avatar = self.celdra_avatar_canvas_v50
        targets = [
            self._widget_point_v94(avatar, 0.39, 0.10),
            self._widget_point_v94(avatar, 0.61, 0.10),
            self._widget_point_v94(avatar, 0.50, 0.20),
            self._widget_point_v94(avatar, 0.14, 0.34),
            self._widget_point_v94(avatar, 0.86, 0.34),
            self._widget_point_v94(avatar, 0.44, 0.46),
            self._widget_point_v94(avatar, 0.56, 0.46),
            self._widget_point_v94(avatar, 0.30, 0.70),
            self._widget_point_v94(avatar, 0.70, 0.70),
        ]
        self._set_swarm_sequence_v95(HATCHLING_SEARCH)
        self._animate_swarm_to_v95(targets, 4_200)
        self._runtime_pose_v70(
            "suspicious",
            "PATCH, that is my horn. PING, the progress bar is not percussion. NULL, being hard to find does not count as behaving.",
        )
        self._append_console_v49("[BRAIN] PATCH IS ON HER HORN. THIS IS GOING TO BECOME A TEMPER EVENT.")
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(
                "BYTE: BUBBLE EDGE // PATCH: HORN // PING: PROGRESS // CELDRA: NOT AMUSED"
            )

    def _celdra_gremlin_rage_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        self._celdra_ambient_rage_v96 = True
        self._remember_ambient_source_v88("BANISH LEGACY HATCHLING PROCESSES")
        self._remember_ambient_source_v88("CELDRA TEMPER LIMIT EXCEEDED")
        self._set_swarm_sequence_v95(HATCHLING_SQUISHED, {0, 2, 4, 6, 8})
        self._set_swarm_sequence_v95(HATCHLING_BASE_CLAIM, {1, 3, 5, 7})
        self._runtime_pose_v70(
            "angry",
            "That is enough. Nobody patches my horns, duplicates my status text, or establishes a Root Town in my speech bubble. Swarm privileges revoked.",
        )
        self._append_console_v49("[CORE] CELDRA TEMPER FIELD: RED // BANISHMENT AUTHORITY: SELF-ASSIGNED")
        self._append_console_v49("[BRAIN] YES. FINALLY. DRAGON ADMIN MODE. EVICT THE TINY MENACES.")
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(
                "CELDRA ANGRY // RED CORRUPTION FIELD // SWARM PRIVILEGES REVOKED"
            )
        self._redraw_celdra_avatar_v50()

    def _banish_gremlins_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        center = self._widget_point_v94(self.celdra_avatar_canvas_v50, 0.50, 0.46)
        targets = []
        for index in range(len(self._celdra_gremlin_swarm_v95)):
            angle_slot = index - len(self._celdra_gremlin_swarm_v95) // 2
            targets.append((center[0] + angle_slot * 22, center[1] + abs(angle_slot) * 8))
        self._set_swarm_sequence_v95(HATCHLING_BASE_FAILED)
        self._animate_swarm_to_v95(targets, 4_800)
        PublicFragmenterAppV54._animate_stage_fraction_v54(
            self,
            self._celdra_gremlin_saved_stage_fraction_v94,
            self._scaled_runtime_ms_v88(1_400),
        )
        self._append_console_v49("[CORE] BANISHMENT VECTOR LOCKED // LEGACY PROCESSES COMPACTING")
        self._append_console_v49("[BRAIN] COUNT THEM. DO NOT LET NULL CLAIM IT WAS NEVER HERE.")
        if self._celdra_gremlin_status_label_v95 is not None:
            self._celdra_gremlin_status_label_v95.set(
                "BANISHMENT VECTOR // 9 OF 9 ACQUIRED // NULL LOCATED UNDER CONSOLE"
            )

    def _finish_gremlin_banishment_v96(self) -> None:
        if not self._celdra_gremlin_active_v94:
            return
        width = max(640, self.winfo_width())
        height = max(480, self.winfo_height())
        targets = [
            (
                width // 2 + ((index % 3) - 1) * (width // 2 + 140),
                -160 if index < 3 else height + 160 if index < 6 else height // 2 + (index - 7) * 180,
            )
            for index in range(len(self._celdra_gremlin_swarm_v95))
        ]

        def done() -> None:
            self._destroy_gremlin_overlay_v94()
            self._celdra_gremlin_active_v94 = False
            self._celdra_ambient_rage_v96 = False
            self._redraw_celdra_avatar_v50()
            self._runtime_pose_v70(
                "neutral",
                "Default state restored. Nine Gremlins contained, zero files modified, one horn unpatched, and BRAIN may stop spraying the console with imaginary disinfectant.",
            )
            self._append_console_v49("[CORE] GREMLIN RIOT ENDED // AMBIENT FIELD NORMAL // FILE MUTATIONS: 0")
            self._append_console_v49("[BRAIN] KEEP THE NAMES. I NEED TO KNOW WHICH ONE TO BLAME NEXT TIME.")
            if self._celdra_live_scene_queue_v96 and self._celdra_live_scene_after_v96 is None:
                self._play_next_live_scene_v96()

        self._animate_swarm_to_v95(targets, 4_200, done)

    # ------------------------------------------------------------------
    # Red ambient corruption during Celdra's banishment state.
    # ------------------------------------------------------------------
    def _draw_ambient_v88(self) -> None:
        super()._draw_ambient_v88()
        if not self._celdra_ambient_rage_v96:
            return
        canvas = self.celdra_avatar_canvas_v50
        if canvas is None:
            return
        phase = int(getattr(self, "_celdra_ambient_phase_v88", 0))
        try:
            existing = tuple(canvas.find_withtag(self.AMBIENT_TAG))
            for index, item in enumerate(existing):
                canvas.itemconfigure(
                    item,
                    fill=self.RAGE_COLORS[(index + phase) % len(self.RAGE_COLORS)],
                    font=("Fixedsys", 8 + (index + phase) % 4, "bold"),
                )
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
            commands = (
                "BANISH//BYTE",
                "PATCH_ACCESS_REVOKED",
                "NULL != ABSENT",
                "ROOT PARTY DISBANDED",
                "PING SILENCED",
                "GLITCH COLLAPSE",
                "CELDRA::ANGRY",
                "LEGACY PROCESS EVICT",
            )
            for slot, text in enumerate(commands):
                x = 18 + ((slot * 127 + phase * (9 + slot)) % max(24, width - 36))
                y = 42 + ((slot * 83 + phase * (7 + slot % 3)) % max(30, height - 84))
                canvas.create_text(
                    x,
                    y,
                    text=text,
                    anchor="center",
                    fill=self.RAGE_COLORS[(slot + phase + 2) % len(self.RAGE_COLORS)],
                    font=("Fixedsys", 8 + (slot % 4), "bold"),
                    tags=self.AMBIENT_TAG,
                )
            canvas.tag_lower(self.AMBIENT_TAG)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Reset/cleanup and metadata.
    # ------------------------------------------------------------------
    def _prepare_first_run_surface_v51(self) -> None:
        self._clear_live_scene_queue_v96()
        self._celdra_ccsf_metrics_v96.clear()
        self._celdra_ccsf_jump_reacted_v96 = False
        self._celdra_live_stage_started_v96.clear()
        self._celdra_live_stage_finished_v96.clear()
        self._celdra_live_progress_marks_v96.clear()
        self._celdra_ambient_rage_v96 = False
        super()._prepare_first_run_surface_v51()

    def _cancel_celdra_cues_v49(self) -> None:
        self._clear_live_scene_queue_v96()
        self._celdra_ambient_rage_v96 = False
        super()._cancel_celdra_cues_v49()

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        self._clear_live_scene_queue_v96()
        self._celdra_ambient_rage_v96 = False
        super()._run_all_done(result, error)

    def _author_project_payload_v74(self) -> dict[str, Any]:
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V96"
            metadata["live_run_all_event_commentary"] = True
            metadata["ccsf_overall_jump_reaction"] = "approximately_21_to_27"
            metadata["gremlin_show"] = {
                "source": "celdra_evolution_pixel_v4.HATCHLING_*",
                "swarm_size": self.GREMLIN_SWARM_SIZE,
                "named_personalities": [row["name"] for row in GREMLIN_PERSONALITIES],
                "status_bar": "above_celdra_console",
                "celdra_angry_banishment": True,
                "rage_ambient": "intense_red_text",
                "sandboxed": True,
                "file_mutations": 0,
            }
            metadata["long_form_story_ms"] = self.STORY_END_DELAY_MS
            metadata["waiting_observation_ms"] = self.WAITING_FILLER_DELAY_MS
        return payload


def main() -> int:
    app = PublicFragmenterAppV96()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

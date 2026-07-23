#!/usr/bin/env python3
"""V87: canonize Celdra's dragongirl staging and finish the persistent runtime."""
from __future__ import annotations

import math
import tkinter as tk
from typing import Any

from celdra_authoring_post_breakpoint_v1 import (
    BUBBLE_GEOMETRY,
    DRAGONGIRL_BUBBLE_STYLE,
    DRAGONGIRL_SCALE,
    DRAGONGIRL_Y,
    STAGE_X,
    extend_with_post_breakpoint,
)
from celdra_authoring_project_v1 import normalize_event, normalize_events
from fragmenter_public_gui_v54 import PublicFragmenterAppV54
from fragmenter_public_gui_v86 import PublicFragmenterAppV86


HATCH_GIF_REVEAL_MS = 167_224
HATCH_GIF_HIDE_MS = 180_000

PRE_BREAKPOINT_DRAGONGIRL_ROWS: tuple[dict[str, Any], ...] = (
    {
        "id": "dragongirl-shy-dialogue",
        "at_ms": 527_500,
        "duration_ms": 0,
        "sequence": "main",
        "action": "bubble",
        "speaker": "CELDRA",
        "asset": "shy",
        "text": "Test, Test, check check. Can you hear me?",
        "x": STAGE_X["center"],
        "y": DRAGONGIRL_Y,
        "scale": DRAGONGIRL_SCALE,
        "window_percent": 50,
        "layout_override": False,
        "bubble_style": DRAGONGIRL_BUBBLE_STYLE,
        **BUBBLE_GEOMETRY["above"],
        "notes": "One-time Shy bubble above the centered avatar.",
    },
    {
        "id": "dragongirl-confused-pose",
        "at_ms": 532_500,
        "duration_ms": 650,
        "sequence": "main",
        "action": "pose",
        "speaker": "CELDRA",
        "asset": "confused",
        "text": "",
        "x": STAGE_X["left"],
        "y": DRAGONGIRL_Y,
        "scale": DRAGONGIRL_SCALE,
        "window_percent": 50,
        "layout_override": True,
        "bubble_style": DRAGONGIRL_BUBBLE_STYLE,
        **BUBBLE_GEOMETRY["right"],
        "notes": "First side-stage pose after the one-time Shy reveal.",
    },
    {
        "id": "dragongirl-confused-dialogue",
        "at_ms": 533_150,
        "duration_ms": 0,
        "sequence": "main",
        "action": "bubble",
        "speaker": "CELDRA",
        "asset": "confused",
        "text": "Well, can you?",
        "x": STAGE_X["left"],
        "y": DRAGONGIRL_Y,
        "scale": DRAGONGIRL_SCALE,
        "window_percent": 50,
        "layout_override": False,
        "bubble_style": DRAGONGIRL_BUBBLE_STYLE,
        **BUBBLE_GEOMETRY["right"],
    },
    {
        "id": "dragongirl-console-return",
        "at_ms": 536_500,
        "duration_ms": 820,
        "sequence": "main",
        "action": "window",
        "speaker": "CORE",
        "asset": "",
        "text": "CONSOLE RETURNS BEFORE THE WINK INTRODUCTION",
        "window_percent": 32,
        "window_height_percent": 100,
        "window_y_percent": 0,
        "layout_override": True,
        "notes": "Mirrors the callback-driven console return in the takeover sequence.",
    },
)


class PublicFragmenterAppV87(PublicFragmenterAppV86):
    """Use the approved 150% three-position staging from the dragongirl reveal onward."""

    POSE_STAGE = {
        "confused": ("left", "right"),
        "suspicious": ("right", "left"),
        "unenthused": ("left", "right"),
        "smile": ("right", "left"),
        "yawn": ("left", "right"),
        "excited": ("right", "left"),
        "shocked": ("left", "right"),
        "laugh": ("right", "left"),
        "wink": ("left", "right"),
        "sad": ("left", "right"),
        "cool": ("right", "left"),
        "neutral": ("right", "left"),
        "default": ("right", "left"),
    }
    INITIAL_FILLER = (
        (
            5_200,
            "suspicious",
            "The console says everything is under control. The console has also lied to me several times today.",
        ),
        (
            10_400,
            "unenthused",
            "No catastrophic file corruption yet. Fragmenter continues to exceed the lowest possible expectations.",
        ),
        (
            15_600,
            "smile",
            "I found the progress bars. They are very persuasive. I understand why humans trust rectangles now.",
        ),
        (
            20_800,
            "yawn",
            "This extraction has been on the same percentage long enough to qualify as interior decoration.",
        ),
        (
            26_000,
            "excited",
            "Wait. Something moved. Either the pipeline advanced or the progress bar developed free will.",
        ),
        (
            31_200,
            "shocked",
            "That filename should not be doing that. I am adding it to the list of things we will call intentional.",
        ),
        (
            36_400,
            "laugh",
            "False alarm. It was a progress-bar repaint. Very dramatic work from a rectangle.",
        ),
        (
            41_600,
            "wink",
            "I'll keep watch from here. This is supervision, not squatting, and that distinction is legally important.",
        ),
    )
    WAITING_FILLER = (
        (
            "smile",
            "Still running. Good. I needed time to decide which part of this interface belongs to me now.",
        ),
        (
            "yawn",
            "The extractor and I are in a staring contest. It has not blinked once.",
        ),
        (
            "suspicious",
            "That status changed and then changed back. I am recording it as movement.",
        ),
        (
            "wink",
            "I am counting continued supervision as measurable progress.",
        ),
    )

    def __init__(self) -> None:
        self._celdra_runtime_bubble_side_v87 = "above"
        self._celdra_runtime_stage_v87 = "center"
        self._celdra_runtime_current_pose_v87 = "shy"
        self._celdra_runtime_wait_index_v87 = 0
        self._celdra_pipeline_failed_v87 = False
        self._celdra_hatch_gif_latched_v87 = False
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Canonical Runtime V87")
        self._apply_dragongirl_authoring_profile_v87()
        self.after_idle(self._refresh_author_event_tree_v74)

    # ------------------------------------------------------------------
    # Keep the editable timeline synchronized with the canonical staging.
    # ------------------------------------------------------------------
    def _ensure_complete_author_events_v84(self) -> None:
        super()._ensure_complete_author_events_v84()
        self._apply_dragongirl_authoring_profile_v87()

    def _apply_author_project_payload_v74(self, payload: dict[str, Any]) -> None:
        super()._apply_author_project_payload_v74(payload)
        self._apply_dragongirl_authoring_profile_v87()
        self._refresh_author_event_tree_v74()

    def _reset_canonical_events_v74(self) -> None:
        super()._reset_canonical_events_v74()
        self._apply_dragongirl_authoring_profile_v87()
        self._refresh_author_event_tree_v74()

    def _apply_dragongirl_authoring_profile_v87(self) -> None:
        rows = extend_with_post_breakpoint(getattr(self, "_celdra_author_events_v74", ()))
        generated = {
            str(row.get("id") or ""): normalize_event(dict(row), index)
            for index, row in enumerate(PRE_BREAKPOINT_DRAGONGIRL_ROWS)
        }
        result: list[dict[str, Any]] = []
        for row in rows:
            event_id = str(row.get("id") or "")
            if event_id in generated:
                continue
            current = dict(row)
            if (
                str(current.get("action") or "").casefold() in {"pose", "avatar", "avatar_takeover"}
                and str(current.get("asset") or "").casefold() == "shy"
                and 506_000 <= int(current.get("at_ms") or 0) <= 542_000
            ):
                current.update(
                    {
                        "x": STAGE_X["center"],
                        "y": DRAGONGIRL_Y,
                        "scale": DRAGONGIRL_SCALE,
                        "bubble_style": DRAGONGIRL_BUBBLE_STYLE,
                        **BUBBLE_GEOMETRY["above"],
                    }
                )
            result.append(current)
        result.extend(generated.values())
        self._celdra_author_events_v74 = normalize_events(result)
        self._celdra_author_event_serial_v74 = max(
            int(getattr(self, "_celdra_author_event_serial_v74", 0)),
            len(self._celdra_author_events_v74),
        )

    def _author_project_payload_v74(self) -> dict[str, Any]:
        self._apply_dragongirl_authoring_profile_v87()
        payload = super()._author_project_payload_v74()
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["gui_version"] = "V87"
            metadata["canonical_dragongirl_staging"] = {
                "scale": DRAGONGIRL_SCALE,
                "avatar_y": DRAGONGIRL_Y,
                "stage_x": dict(STAGE_X),
                "bubble_style": DRAGONGIRL_BUBBLE_STYLE,
            }
            metadata["hatch_gif_latched_until_hide"] = True
        return payload

    # ------------------------------------------------------------------
    # Load the manifest crop at the same 150% scale used by the preview.
    # ------------------------------------------------------------------
    def _load_takeover_reaction_v58(self, name: str) -> bool:
        self._reload_manifest_emotes_v56()
        row = self._celdra_manifest_emotes_v56.get(str(name or "").casefold())
        if row is None:
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION MISSING: {name}")
            return False
        source = self.celdra_asset_root_v50 / str(row.get("source") or "")
        if not source.is_file():
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION SOURCE MISSING: {source}")
            return False
        try:
            image = tk.PhotoImage(file=str(source))
            crop = row.get("crop") if isinstance(row.get("crop"), dict) else {}
            cropped = self._crop_photo_v52(
                image,
                {
                    "x": int(crop.get("x") or 0),
                    "y": int(crop.get("y") or 0),
                    "width": int(crop.get("width") or 1),
                    "height": int(crop.get("height") or 1),
                },
            )
            display = cropped.zoom(3, 3).subsample(2, 2)
        except (tk.TclError, OSError, ValueError) as exc:
            self._append_console_v49(f"[CORE] CLASSIFIED REACTION LOAD FAILED: {exc}")
            return False
        self._celdra_manifest_source_v56 = image
        self._celdra_manifest_crop_v56 = cropped
        self._celdra_manifest_display_v56 = display
        self.celdra_current_pixel_v50 = None
        self.celdra_current_external_v50 = display
        self._celdra_stage_phase_v54 = "dragongirl"
        self._celdra_runtime_current_pose_v87 = str(name or "").casefold()
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set(
                f"{cropped.width()}x{cropped.height()} -> {display.width()}x{display.height()} "
                f"at 150% - {str(row.get('pose') or name).upper()}"
            )
        self._redraw_celdra_avatar_v50()
        return True

    def _set_stage_position_v87(self, stage: str, bubble_side: str) -> None:
        self._celdra_runtime_stage_v87 = stage
        self._celdra_runtime_bubble_side_v87 = bubble_side
        self._celdra_external_offset_x_v65 = STAGE_X[stage]
        self._celdra_external_offset_y_v58 = DRAGONGIRL_Y

    # ------------------------------------------------------------------
    # One-time Shy reveal centered; later poses alternate side stages.
    # ------------------------------------------------------------------
    def _begin_shy_reveal_v64(self) -> None:
        canvas = self.celdra_avatar_canvas_v50
        canvas_height = canvas.winfo_height() if canvas is not None else 420
        self._celdra_runtime_bubble_side_v87 = "above"
        self._celdra_runtime_stage_v87 = "center"
        self._celdra_external_offset_x_v65 = STAGE_X["center"]
        if not self._load_takeover_reaction_v58("shy"):
            return
        self._celdra_shy_rest_offset_v64 = DRAGONGIRL_Y
        self._celdra_external_offset_y_v58 = max(320, canvas_height + 90)
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.50, 1_650)
        self._redraw_celdra_avatar_v50()
        self._remember_after_v49(260, self._start_shy_creep_v58)

    def _takeover_confused_v58(self) -> None:
        self._set_stage_position_v87("left", "right")
        if not self._load_takeover_reaction_v58("confused"):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.50, 650)
        self._redraw_celdra_avatar_v50()
        self._show_speech_bubble_v58("Well, can you?")

    def _takeover_wink_v58(self) -> None:
        self._set_stage_position_v87("right", "left")
        if not self._load_takeover_reaction_v58("wink"):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.64, 1_100)
        self._redraw_celdra_avatar_v50()
        name = self._celdra_user_name_v58 or "noname"
        self._remember_after_v49(
            1_150,
            lambda: self._show_speech_bubble_v58(
                "Alright, Operation Dragonegg is a go!\n"
                f"Like I said, my name is Celdra. Nice to meet you, {name}."
            ),
        )
        self._remember_after_v49(7_000, self._start_placeholder_runtime_v70)

    # ------------------------------------------------------------------
    # Angular HUD production bubbles: above Shy, opposite the side-stage poses.
    # ------------------------------------------------------------------
    def _show_speech_bubble_v58(self, text: str) -> None:
        bubble = self._celdra_speech_canvas_v63
        if bubble is None:
            return
        side = self._celdra_runtime_bubble_side_v87
        if side == "above":
            relx, rely, relwidth, chars = 0.08, 0.025, 0.84, 58
        elif side == "right":
            relx, rely, relwidth, chars = 0.505, 0.18, 0.47, 32
        else:
            relx, rely, relwidth, chars = 0.025, 0.18, 0.47, 32
        line_total = 0
        for paragraph in str(text or "").splitlines() or [""]:
            line_total += max(1, math.ceil(max(1, len(paragraph)) / chars))
        height = max(88, min(220, 46 + line_total * 21))
        bubble.place(relx=relx, rely=rely, anchor="nw", relwidth=relwidth, height=height)
        bubble.update_idletasks()
        width = max(150, bubble.winfo_width())
        bubble.delete("all")
        self._draw_bubble_style_v81(
            bubble,
            (2, 2, width - 4, height - 8),
            DRAGONGIRL_BUBBLE_STYLE,
            str(text or ""),
        )
        try:
            bubble.tkraise()
        except (AttributeError, tk.TclError):
            try:
                bubble.tk.call("raise", bubble._w)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Longer filler sequence, recurring wait loop, and a Cool wrap-up.
    # ------------------------------------------------------------------
    def _runtime_pose_v70(self, pose: str, text: str) -> None:
        folded = str(pose or "neutral").casefold()
        if (
            self._celdra_pipeline_success_v70
            and self._celdra_placeholder_started_v70
            and folded != "cool"
        ):
            folded = "cool"
            text = self._completion_text_v87()
        stage, bubble_side = self.POSE_STAGE.get(folded, ("right", "left"))
        self._celdra_takeover_active_v58 = True
        self._celdra_stage_avatar_visible_v54 = True
        self._celdra_stage_dialogue_visible_v54 = False
        self._slide_chat_v54(show=False, duration_ms=320)
        self._set_stage_position_v87(stage, bubble_side)
        if not self._load_takeover_reaction_v58(folded):
            return
        PublicFragmenterAppV54._animate_stage_fraction_v54(self, 0.56, 650)
        self.after_idle(self._redraw_celdra_avatar_v50)
        self._show_speech_bubble_v58(text)

    def _start_placeholder_runtime_v70(self) -> None:
        if self._celdra_placeholder_started_v70:
            return
        self._celdra_placeholder_started_v70 = True
        self._hide_speech_bubble_v58()
        self._runtime_pose_v70("confused", self._assessment_text_v70())
        if self._celdra_pipeline_success_v70:
            self._show_completion_cool_v70()
            return
        for delay, pose, text in self.INITIAL_FILLER:
            self._remember_after_v49(
                delay,
                lambda selected_pose=pose, selected_text=text: self._runtime_filler_pose_v87(
                    selected_pose,
                    selected_text,
                ),
            )
        self._remember_after_v49(46_800, self._runtime_wait_or_complete_v87)

    def _runtime_filler_pose_v87(self, pose: str, text: str) -> None:
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_failed_v87:
            return
        self._runtime_pose_v70(pose, text)

    def _runtime_wait_or_complete_v87(self) -> None:
        if bool(getattr(self, "_celdra_test_mode_v58", False)):
            self._runtime_pose_v70(
                "cool",
                "Test sequence complete. The poses fit, the bubbles stayed in their lanes, "
                "and nothing caught fire where you could see it.",
            )
            return
        if self._celdra_pipeline_failed_v87:
            self._runtime_pose_v70(
                "sad",
                "RUN ALL failed. I am leaving the evidence visible and judging the responsible subsystem quietly.",
            )
            return
        if self._celdra_pipeline_success_v70 or self._celdra_pipeline_finished_v51:
            if self._celdra_runtime_current_pose_v87 != "cool":
                self._show_completion_cool_v70()
            return
        pose, text = self.WAITING_FILLER[
            self._celdra_runtime_wait_index_v87 % len(self.WAITING_FILLER)
        ]
        self._celdra_runtime_wait_index_v87 += 1
        self._runtime_pose_v70(pose, text)
        self._remember_after_v49(7_000, self._runtime_wait_or_complete_v87)

    @staticmethod
    def _completion_text_v87() -> str:
        return (
            "RUN ALL complete. CCSF extracted, outputs indexed, and the console survived "
            "my supervision. I'll stay here in Cool mode."
        )

    def _show_completion_cool_v70(self) -> None:
        self._runtime_pose_v70("cool", self._completion_text_v87())
        if self._celdra_stage_detail_v54 is not None:
            self._celdra_stage_detail_v54.set("RUN ALL COMPLETE - CELDRA COOL MODE")

    def _run_all_done(self, result: Any, error: Exception | None) -> None:
        self._celdra_pipeline_failed_v87 = bool(error) or bool(
            result and result.get("status") == "failed"
        )
        super()._run_all_done(result, error)

    # ------------------------------------------------------------------
    # Prevent the egg loop from replacing the installed hatch GIF.
    # ------------------------------------------------------------------
    def _begin_hatch_gif_v63(self) -> None:
        super()._begin_hatch_gif_v63()
        self._celdra_hatch_gif_latched_v87 = self.celdra_current_external_v50 is not None
        if self._celdra_hatch_gif_latched_v87:
            self.celdra_current_pixel_v50 = None

    def _redraw_celdra_avatar_v50(self) -> None:
        if (
            self._celdra_hatch_gif_latched_v87
            and bool(getattr(self, "_celdra_energy_gif_started_v63", False))
            and not bool(getattr(self, "_celdra_takeover_active_v58", False))
            and bool(getattr(self, "_celdra_stage_avatar_visible_v54", False))
            and self.celdra_current_external_v50 is None
        ):
            frames = self._load_hatch_gif_v63()
            if frames:
                index = int(getattr(self, "_celdra_avatar_index_v49", 0)) % len(frames)
                self.celdra_current_pixel_v50 = None
                self.celdra_current_external_v50 = frames[index]
        super()._redraw_celdra_avatar_v50()

    def _hide_avatar_v51(self) -> None:
        self._celdra_hatch_gif_latched_v87 = False
        super()._hide_avatar_v51()

    def _start_avatar_takeover_v58(self) -> None:
        self._celdra_hatch_gif_latched_v87 = False
        super()._start_avatar_takeover_v58()

    def _timeline_state_at_v84(self, target_ms: float) -> tuple[dict[str, Any], str]:
        state, active_id = super()._timeline_state_at_v84(target_ms)
        if HATCH_GIF_REVEAL_MS <= float(target_ms) < HATCH_GIF_HIDE_MS:
            state["asset"] = "hatch_gif"
            state["visible"] = True
        return state, active_id

    def _prepare_first_run_surface_v51(self) -> None:
        self._celdra_runtime_bubble_side_v87 = "above"
        self._celdra_runtime_stage_v87 = "center"
        self._celdra_runtime_current_pose_v87 = "shy"
        self._celdra_runtime_wait_index_v87 = 0
        self._celdra_pipeline_failed_v87 = False
        self._celdra_hatch_gif_latched_v87 = False
        super()._prepare_first_run_surface_v51()


def main() -> int:
    app = PublicFragmenterAppV87()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

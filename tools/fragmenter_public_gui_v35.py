#!/usr/bin/env python3
"""Thirty-fifth public GUI pass: confirmed defaults and lower-cost interaction."""
from __future__ import annotations

import math
from typing import Any

import camera_orbit_v1 as camera_orbit
import ccsf_gen1_pose_v7 as pose_v7
from fragmenter_public_gui_v34 import PublicFragmenterAppV34
import fragmenter_review_defaults_v1 as review_defaults


class PublicFragmenterAppV35(PublicFragmenterAppV34):
    """Use the reviewed upright view and reduce Tk wireframe work while navigating."""

    INTERACTIVE_FACE_LIMIT = 700
    SETTLED_FACE_LIMIT = 3000

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Recovered Models / Faster 3D Review")

    # ------------------------------------------------------------------
    # Universal camera fallback confirmed from ca1ab_bl.
    # Saved per-asset cameras remain authoritative, followed by reviewed family views.
    # ------------------------------------------------------------------
    def _apply_reference_camera_v35(self, *, draw: bool = True) -> None:
        if self.preview_background_var is not None:
            self.preview_background_var.set(review_defaults.CAMERA_BACKGROUND)
            self._preview_background_changed_v25(render=False)
        self._wire_yaw = review_defaults.CAMERA_YAW
        self._wire_pitch = review_defaults.CAMERA_PITCH
        self._wire_zoom = review_defaults.CAMERA_ZOOM
        self._wire_pan_x = review_defaults.CAMERA_PAN_X
        self._wire_pan_y = review_defaults.CAMERA_PAN_Y
        self._set_basis_v29(
            camera_orbit.basis_from_flat(review_defaults.CAMERA_BASIS),
            sync_panel=False,
        )
        self._set_position_v30(review_defaults.CAMERA_POSITION, sync_panel=False)
        self._sync_zoom_control()
        self._sync_renderer_camera_v30()
        self._sync_camera_panel_v29()
        if draw:
            self._draw_interactive_wireframe()

    def _apply_saved_camera_v27(self, annotation: dict[str, Any]) -> None:
        if isinstance(annotation.get("camera"), dict):
            super()._apply_saved_camera_v27(annotation)
            return
        if self._camera_suggestion_v34() is not None:
            super()._apply_saved_camera_v27(annotation)
            return
        self._camera_suggestion_source_v34 = None
        self._apply_reference_camera_v35()
        self.after(
            120,
            lambda: self.visual_status.set(
                f"Using confirmed upright unsaved default from {review_defaults.CAMERA_SOURCE}. "
                "Save Pose / Position only after reviewing this asset."
            ),
        )

    def _reset_camera_pose_v33(self) -> None:
        self._stop_animation()
        self._apply_reference_camera_v35(draw=False)
        if hasattr(self, "animation_name"):
            self.animation_name.set(pose_v7.INITIAL_POSE_NAME)
            self._configure_animation_range()
            self.animation_frame.set(0)
            self.animation_frame_scale.set(0)
            self._update_animation_frame_label(0)
        self._draw_interactive_wireframe()
        self.visual_status.set(
            f"Reset to confirmed {review_defaults.CAMERA_SOURCE} upright camera and Initial Pose. "
            "Use Save Pose / Position to retain it for this asset."
        )
        self.after_idle(lambda: self._wireframe_load(allow_auto_texture=True))

    # ------------------------------------------------------------------
    # Tk Canvas line creation is a major interaction cost. Keep the complete geometry
    # in the scene/renderer, but use a smaller deterministic face sample only while the
    # user is orbiting, panning or inspecting the wireframe.
    # ------------------------------------------------------------------
    def _interactive_geometry(self) -> dict[str, Any] | None:
        payload = self._wireframe_payload
        if not payload or not payload.get("vertices") or not payload.get("faces"):
            return None
        vertices = payload["vertices"]
        faces = payload["faces"]
        key = (id(payload), len(vertices), len(faces), self.INTERACTIVE_FACE_LIMIT, self.SETTLED_FACE_LIMIT)
        if self._interactive_geometry_cache.get("key") == key:
            return self._interactive_geometry_cache

        iterator = iter(vertices)
        first = next(iterator, None)
        if first is None:
            return None
        min_x = max_x = float(first[0])
        min_y = max_y = float(first[1])
        min_z = max_z = float(first[2])
        for row in iterator:
            x, y, z = float(row[0]), float(row[1]), float(row[2])
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            min_z, max_z = min(min_z, z), max(max_z, z)
        corners = [
            (x, y, z)
            for x in (min_x, max_x)
            for y in (min_y, max_y)
            for z in (min_z, max_z)
        ]

        samples: dict[int, tuple[list[Any], list[int]]] = {}
        for inherited_key, actual_limit in (
            (1200, self.INTERACTIVE_FACE_LIMIT),
            (6000, self.SETTLED_FACE_LIMIT),
        ):
            step = max(1, math.ceil(len(faces) / max(1, actual_limit)))
            selected = list(faces[::step])
            indices = sorted(
                {
                    int(index)
                    for face in selected
                    if isinstance(face, (list, tuple)) and len(face) >= 3
                    for index in face[:3]
                    if 0 <= int(index) < len(vertices)
                }
            )
            samples[inherited_key] = (selected, indices)

        self._interactive_geometry_cache = {
            "key": key,
            "vertices": vertices,
            "faces_total": len(faces),
            "corners": corners,
            "samples": samples,
            "interaction_face_limit": self.INTERACTIVE_FACE_LIMIT,
            "settled_face_limit": self.SETTLED_FACE_LIMIT,
        }
        return self._interactive_geometry_cache


def main() -> int:
    app = PublicFragmenterAppV35()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

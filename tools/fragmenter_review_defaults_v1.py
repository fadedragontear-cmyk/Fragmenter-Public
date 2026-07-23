#!/usr/bin/env python3
"""Confirmed universal 3D review defaults.

The reference camera comes from the user-reviewed ca1ab_bl report generated on
2026-07-15 after confirming head-up, feet-down alignment with the accepted Euler
profile.  It is used only when an asset has neither a saved camera nor a reviewed
family-camera suggestion.
"""
from __future__ import annotations

EULER_COMPONENT_MAP = "ZYX"
EULER_ORDER = "ZYX"
EULER_SIGNS = "+-+"
EULER_PARENT_MODE = "LXP"

CAMERA_SOURCE = "20260715_182629_CCSFca1ab_bl"
CAMERA_YAW = -1.7532813461364638
CAMERA_PITCH = 1.4518540307469696
CAMERA_ZOOM = 1.25
CAMERA_PAN_X = 0.0
CAMERA_PAN_Y = 0.0
CAMERA_BACKGROUND = "Dark Gray"
CAMERA_BASIS = (
    -0.9930679944048407,
    0.1163445848455104,
    -0.016730094616386824,
    -0.01410651994168529,
    0.023337052153046055,
    0.9996281249004257,
    0.11669175028202405,
    0.9929347005588696,
    -0.021534062370716322,
)
CAMERA_POSITION = (
    -0.35007525084607255,
    -2.9788041016766096,
    0.06460218711215328,
)

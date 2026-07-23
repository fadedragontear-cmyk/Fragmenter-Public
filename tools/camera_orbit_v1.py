#!/usr/bin/env python3
"""Small camera-basis helpers for viewport-relative orbit controls."""
from __future__ import annotations

import math
from typing import Iterable

Vec3 = tuple[float, float, float]
Basis = tuple[Vec3, Vec3, Vec3]  # camera right, camera up, camera forward


def _dot(left: Vec3, right: Vec3) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _length(value: Vec3) -> float:
    return math.sqrt(max(0.0, _dot(value, value)))


def _normalize(value: Vec3, fallback: Vec3) -> Vec3:
    magnitude = _length(value)
    if magnitude <= 1e-12:
        return fallback
    return (value[0] / magnitude, value[1] / magnitude, value[2] / magnitude)


def _scale(value: Vec3, amount: float) -> Vec3:
    return value[0] * amount, value[1] * amount, value[2] * amount


def _add(*values: Vec3) -> Vec3:
    return (
        sum(value[0] for value in values),
        sum(value[1] for value in values),
        sum(value[2] for value in values),
    )


def rotate_vector(value: Vec3, axis: Vec3, angle: float) -> Vec3:
    """Rotate one vector around a normalized axis using Rodrigues' formula."""
    axis = _normalize(axis, (0.0, 1.0, 0.0))
    cosine = math.cos(float(angle))
    sine = math.sin(float(angle))
    return _add(
        _scale(value, cosine),
        _scale(_cross(axis, value), sine),
        _scale(axis, _dot(axis, value) * (1.0 - cosine)),
    )


def orthonormalize(basis: Basis) -> Basis:
    right = _normalize(tuple(float(value) for value in basis[0]), (1.0, 0.0, 0.0))
    up_seed = tuple(float(value) for value in basis[1])
    up = _normalize(
        _add(up_seed, _scale(right, -_dot(up_seed, right))),
        (0.0, 1.0, 0.0),
    )
    forward = _normalize(_cross(right, up), (0.0, 0.0, 1.0))
    up = _normalize(_cross(forward, right), (0.0, 1.0, 0.0))
    return right, up, forward


def basis_from_yaw_pitch(yaw: float, pitch: float) -> Basis:
    cy, sy = math.cos(float(yaw)), math.sin(float(yaw))
    cp, sp = math.cos(float(pitch)), math.sin(float(pitch))
    return orthonormalize(
        (
            (cy, 0.0, sy),
            (sp * sy, cp, -sp * cy),
            (-cp * sy, sp, cp * cy),
        )
    )


def flatten_basis(basis: Basis) -> tuple[float, ...]:
    value = orthonormalize(basis)
    return tuple(component for axis in value for component in axis)


def basis_from_flat(values: Iterable[float] | None, *, fallback_yaw: float = -0.55, fallback_pitch: float = 0.35) -> Basis:
    raw = [float(value) for value in (values or ())]
    if len(raw) != 9 or not all(math.isfinite(value) for value in raw):
        return basis_from_yaw_pitch(fallback_yaw, fallback_pitch)
    return orthonormalize(
        (
            (raw[0], raw[1], raw[2]),
            (raw[3], raw[4], raw[5]),
            (raw[6], raw[7], raw[8]),
        )
    )


def orbit_camera_relative(basis: Basis, *, horizontal: float = 0.0, vertical: float = 0.0) -> Basis:
    """Orbit around the viewport's current up/right axes.

    Horizontal motion rotates around the current camera-up direction. Vertical
    motion rotates around the current camera-right direction. The second rotation
    therefore uses the already-updated right axis and remains relative to the view.
    """
    right, up, forward = orthonormalize(basis)
    if horizontal:
        right = rotate_vector(right, up, float(horizontal))
        forward = rotate_vector(forward, up, float(horizontal))
    if vertical:
        up = rotate_vector(up, right, float(vertical))
        forward = rotate_vector(forward, right, float(vertical))
    return orthonormalize((right, up, forward))


def project(position: Iterable[float], basis: Basis) -> tuple[float, float, float]:
    x, y, z = (float(value) for value in position)
    point = (x, y, z)
    right, up, forward = orthonormalize(basis)
    return _dot(right, point), _dot(up, point), _dot(forward, point)


def heading_elevation(basis: Basis) -> tuple[float, float]:
    """Return readable heading/elevation degrees from the camera forward vector."""
    _right, _up, forward = orthonormalize(basis)
    heading = math.degrees(math.atan2(-forward[0], forward[2]))
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, forward[1]))))
    return heading, elevation


def basis_from_heading_elevation(heading_degrees: float, elevation_degrees: float) -> Basis:
    return basis_from_yaw_pitch(math.radians(float(heading_degrees)), math.radians(float(elevation_degrees)))

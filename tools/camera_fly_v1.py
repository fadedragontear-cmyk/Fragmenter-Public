#!/usr/bin/env python3
"""Normalized free-fly camera position and perspective projection helpers."""
from __future__ import annotations

import math
from typing import Iterable

import camera_orbit_v1 as camera_orbit

Vec3 = tuple[float, float, float]
Basis = camera_orbit.Basis


def _vec3(value: Iterable[float], fallback: Vec3 = (0.0, 0.0, 0.0)) -> Vec3:
    rows = [float(component) for component in value]
    if len(rows) != 3 or not all(math.isfinite(component) for component in rows):
        return fallback
    return rows[0], rows[1], rows[2]


def add(left: Vec3, right: Vec3) -> Vec3:
    return left[0] + right[0], left[1] + right[1], left[2] + right[2]


def subtract(left: Vec3, right: Vec3) -> Vec3:
    return left[0] - right[0], left[1] - right[1], left[2] - right[2]


def scale(value: Vec3, amount: float) -> Vec3:
    return value[0] * amount, value[1] * amount, value[2] * amount


def dot(left: Vec3, right: Vec3) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def length(value: Vec3) -> float:
    return math.sqrt(max(0.0, dot(value, value)))


def normalize_position(value: Iterable[float] | None, fallback: Vec3 = (0.0, 0.0, -3.0)) -> Vec3:
    if value is None:
        return fallback
    return _vec3(value, fallback)


def default_position(basis: Basis, distance: float = 3.0) -> Vec3:
    """Place the camera behind the scene center while looking along its forward axis."""
    _right, _up, forward = camera_orbit.orthonormalize(basis)
    return scale(forward, -abs(float(distance)))


def move_position(
    position: Iterable[float],
    basis: Basis,
    *,
    forward: float = 0.0,
    strafe: float = 0.0,
    vertical: float = 0.0,
) -> Vec3:
    """Move a normalized camera position along its current local axes."""
    current = normalize_position(position)
    right, up, view_forward = camera_orbit.orthonormalize(basis)
    return add(
        current,
        add(
            scale(view_forward, float(forward)),
            add(scale(right, float(strafe)), scale(up, float(vertical))),
        ),
    )


def orbit_around_origin(
    position: Iterable[float],
    basis: Basis,
    *,
    horizontal: float = 0.0,
    vertical: float = 0.0,
) -> tuple[Vec3, Basis]:
    """Orbit camera position and orientation around the normalized scene center."""
    current = normalize_position(position)
    right, up, view_forward = camera_orbit.orthonormalize(basis)
    if horizontal:
        angle = float(horizontal)
        current = camera_orbit.rotate_vector(current, up, angle)
        right = camera_orbit.rotate_vector(right, up, angle)
        view_forward = camera_orbit.rotate_vector(view_forward, up, angle)
    if vertical:
        angle = float(vertical)
        current = camera_orbit.rotate_vector(current, right, angle)
        up = camera_orbit.rotate_vector(up, right, angle)
        view_forward = camera_orbit.rotate_vector(view_forward, right, angle)
    return current, camera_orbit.orthonormalize((right, up, view_forward))


def scene_center_radius(points: Iterable[Iterable[float]]) -> tuple[Vec3, float]:
    minimum = [float("inf"), float("inf"), float("inf")]
    maximum = [float("-inf"), float("-inf"), float("-inf")]
    count = 0
    for row in points:
        value = _vec3(row)
        for axis in range(3):
            minimum[axis] = min(minimum[axis], value[axis])
            maximum[axis] = max(maximum[axis], value[axis])
        count += 1
    if not count:
        return (0.0, 0.0, 0.0), 1.0
    center = tuple((minimum[axis] + maximum[axis]) * 0.5 for axis in range(3))
    half = tuple((maximum[axis] - minimum[axis]) * 0.5 for axis in range(3))
    radius = max(length(half), max(half), 1e-6)
    return center, radius


def world_position(scene_center: Vec3, scene_radius: float, normalized_position: Iterable[float]) -> Vec3:
    return add(scene_center, scale(normalize_position(normalized_position), max(float(scene_radius), 1e-6)))


def camera_coordinates(point: Iterable[float], basis: Basis, camera_world: Vec3) -> Vec3:
    relative = subtract(_vec3(point), camera_world)
    right, up, forward = camera_orbit.orthonormalize(basis)
    return dot(right, relative), dot(up, relative), dot(forward, relative)


def perspective_project(
    point: Iterable[float],
    basis: Basis,
    camera_world: Vec3,
    *,
    focal_length: float,
    screen_center_x: float,
    screen_center_y: float,
    near_plane: float,
) -> tuple[float, float, float] | None:
    x, y, depth = camera_coordinates(point, basis, camera_world)
    if depth <= max(float(near_plane), 1e-9):
        return None
    return (
        float(screen_center_x) + (x / depth) * float(focal_length),
        float(screen_center_y) - (y / depth) * float(focal_length),
        depth,
    )

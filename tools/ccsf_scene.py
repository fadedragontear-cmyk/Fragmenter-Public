#!/usr/bin/env python3
"""Scene graph assembly helpers for decoded CCSF/CMP/OBJ/MDL data.

The structural decoder intentionally preserves raw model-space vertices.  This
module builds a lightweight preview scene on top of that decoded data: it keeps
CCSF/CMP/OBJ/MDL identifiers, computes local/world matrices, and offers mesh
views for assembled-scene, selected-object, and raw-model-space previews.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, sin
from typing import Any, Iterable, Literal

Vec3 = tuple[float, float, float]
Mat4 = tuple[tuple[float, float, float, float], ...]
SceneViewMode = Literal["assembled_scene", "selected_object", "raw_model_space"]

# StudioCCS builds object bind transforms as scale, then Z/Y/X Euler rotations,
# then translation.  Keep this centralized so callers do not accidentally fall
# back to a guessed XYZ rotation order.
STUDIOCCS_TRANSFORM_ORDER = ("scale", "rotate_z", "rotate_y", "rotate_x", "translate")


def identity_matrix() -> Mat4:
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def multiply_matrix(a: Mat4, b: Mat4) -> Mat4:
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)) for r in range(4))  # type: ignore[return-value]


def transform_point(matrix: Mat4, point: Iterable[float]) -> Vec3:
    x, y, z = [float(v) for v in list(point)[:3]]
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def _scale_matrix(scale: Vec3) -> Mat4:
    sx, sy, sz = scale
    return ((sx, 0.0, 0.0, 0.0), (0.0, sy, 0.0, 0.0), (0.0, 0.0, sz, 0.0), (0.0, 0.0, 0.0, 1.0))


def _translation_matrix(pos: Vec3) -> Mat4:
    x, y, z = pos
    return ((1.0, 0.0, 0.0, x), (0.0, 1.0, 0.0, y), (0.0, 0.0, 1.0, z), (0.0, 0.0, 0.0, 1.0))


def _rotation_x(a: float) -> Mat4:
    c, s = cos(a), sin(a)
    return ((1.0, 0.0, 0.0, 0.0), (0.0, c, -s, 0.0), (0.0, s, c, 0.0), (0.0, 0.0, 0.0, 1.0))


def _rotation_y(a: float) -> Mat4:
    c, s = cos(a), sin(a)
    return ((c, 0.0, s, 0.0), (0.0, 1.0, 0.0, 0.0), (-s, 0.0, c, 0.0), (0.0, 0.0, 0.0, 1.0))


def _rotation_z(a: float) -> Mat4:
    c, s = cos(a), sin(a)
    return ((c, -s, 0.0, 0.0), (s, c, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def compose_studioccs_transform(position: Vec3 = (0.0, 0.0, 0.0), rotation: Vec3 = (0.0, 0.0, 0.0), scale: Vec3 = (1.0, 1.0, 1.0)) -> Mat4:
    """Compose a local transform using StudioCCS' CCSObject order: S * Rz * Ry * Rx * T."""
    rx, ry, rz = rotation
    matrix = identity_matrix()
    for part in STUDIOCCS_TRANSFORM_ORDER:
        next_matrix = {
            "scale": _scale_matrix(scale),
            "rotate_z": _rotation_z(rz),
            "rotate_y": _rotation_y(ry),
            "rotate_x": _rotation_x(rx),
            "translate": _translation_matrix(position),
        }[part]
        matrix = multiply_matrix(next_matrix, matrix)
    return matrix


def _vec3(value: Any, default: Vec3) -> Vec3:
    if isinstance(value, dict):
        value = [value.get("x", default[0]), value.get("y", default[1]), value.get("z", default[2])]
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    return default


def _matrix(value: Any) -> Mat4 | None:
    if isinstance(value, (list, tuple)) and len(value) == 16:
        nums = [float(v) for v in value]
        return tuple(tuple(nums[r * 4:(r + 1) * 4]) for r in range(4))  # type: ignore[return-value]
    if isinstance(value, (list, tuple)) and len(value) == 4 and all(isinstance(row, (list, tuple)) and len(row) == 4 for row in value):
        return tuple(tuple(float(v) for v in row) for row in value)  # type: ignore[return-value]
    return None


def transform_from_record(record: dict[str, Any] | None) -> Mat4:
    if not isinstance(record, dict):
        return identity_matrix()
    for key in ("local_transform", "transform", "matrix", "bind_matrix"):
        parsed = _matrix(record.get(key))
        if parsed is not None:
            return parsed
    bind = record.get("bind_pose") if isinstance(record.get("bind_pose"), dict) else record
    return compose_studioccs_transform(
        _vec3(bind.get("position") or bind.get("translation"), (0.0, 0.0, 0.0)),
        _vec3(bind.get("rotation"), (0.0, 0.0, 0.0)),
        _vec3(bind.get("scale"), (1.0, 1.0, 1.0)),
    )


@dataclass
class SceneMeshInstance:
    """A preview mesh attached to a scene node without mutating decoder vertices."""
    model_id: int | str | None
    model_name: str = ""
    submodel_index: int | None = None
    object_id: int | str | None = None
    object_name: str = ""
    material_id: int | str | None = None
    material_name: str = ""
    texture_id: int | str | None = None
    texture_name: str = ""
    raw_vertices: list[Vec3] = field(default_factory=list)
    faces: list[list[int]] = field(default_factory=list)
    node: "SceneNode | None" = field(default=None, repr=False)
    source: dict[str, Any] = field(default_factory=dict)

    def vertices_for_view(self, mode: SceneViewMode = "assembled_scene") -> list[Vec3]:
        if mode == "raw_model_space" or self.node is None:
            return list(self.raw_vertices)
        matrix = self.node.world_transform if mode == "assembled_scene" else self.node.local_transform
        return [transform_point(matrix, vertex) for vertex in self.raw_vertices]


@dataclass
class SceneNode:
    id: int | str | None
    name: str
    kind: str = "node"
    local_transform: Mat4 = field(default_factory=identity_matrix)
    world_transform: Mat4 = field(default_factory=identity_matrix)
    identifiers: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    parent: "SceneNode | None" = field(default=None, repr=False)
    children: list["SceneNode"] = field(default_factory=list)
    mesh_instances: list[SceneMeshInstance] = field(default_factory=list)

    def add_child(self, child: "SceneNode") -> "SceneNode":
        child.parent = self
        self.children.append(child)
        return child

    def add_mesh_instance(self, instance: SceneMeshInstance) -> SceneMeshInstance:
        instance.node = self
        self.mesh_instances.append(instance)
        return instance

    def compute_world_transform(self, parent_world: Mat4 | None = None) -> None:
        self.world_transform = multiply_matrix(parent_world or identity_matrix(), self.local_transform)
        for child in self.children:
            child.compute_world_transform(self.world_transform)

    def walk(self) -> Iterable["SceneNode"]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class Scene:
    root: SceneNode = field(default_factory=lambda: SceneNode(id="root", name="CCSF Scene", kind="CCSF"))
    nodes_by_id: dict[Any, SceneNode] = field(default_factory=dict)
    nodes_by_name: dict[str, SceneNode] = field(default_factory=dict)
    mesh_instances: list[SceneMeshInstance] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_decoded(cls, decoded: Any) -> "Scene":
        data = decoded.__dict__ if hasattr(decoded, "__dict__") else (decoded or {})
        scene = cls()
        scene.root.name = str((data.get("header") or {}).get("name") or data.get("input") or "CCSF Scene") if isinstance(data, dict) else "CCSF Scene"
        if not isinstance(data, dict):
            scene.warnings.append("decoded scene input is not a mapping")
            return scene
        objects = data.get("object_lookup") or {entry.get("id", i): entry for i, entry in enumerate(data.get("object_index") or []) if isinstance(entry, dict)}
        for oid, entry in objects.items():
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or oid)
            prefix = name.split("_", 1)[0].upper()
            if prefix not in {"CMP", "OBJ", "MDL"}:
                continue
            node = SceneNode(id=entry.get("id", oid), name=name, kind=prefix, local_transform=transform_from_record(entry), identifiers={"object_id": entry.get("id", oid), "file_id": entry.get("file_id"), "file_name": entry.get("file_name")}, source=entry)
            scene.nodes_by_id[node.id] = node
            scene.nodes_by_name[name] = node
        for node in list(scene.nodes_by_id.values()):
            parent_id = node.source.get("parent_id") if "parent_id" in node.source else node.source.get("parent")
            parent = scene.nodes_by_id.get(parent_id) if parent_id is not None else None
            (parent or scene.root).add_child(node)
        for node in list(scene.nodes_by_id.values()):
            if node.kind == "MDL" and isinstance(node.source.get("model"), dict):
                scene._attach_model_meshes(node, node.source["model"], objects)
        for rec in data.get("records") or []:
            if isinstance(rec, dict) and isinstance(rec.get("model"), dict) and rec.get("object_name") not in scene.nodes_by_name:
                node = scene.root.add_child(SceneNode(id=rec.get("object_id"), name=str(rec.get("object_name") or rec.get("object_id")), kind="MDL", source=rec))
                scene._attach_model_meshes(node, rec["model"], objects)
        scene.root.compute_world_transform()
        return scene

    def _attach_model_meshes(self, node: SceneNode, model: dict[str, Any], objects: dict[Any, Any] | None = None) -> None:
        for sub in model.get("submodels") or []:
            if not isinstance(sub, dict):
                continue
            raw_vertices = [_vertex_position(v) for v in sub.get("vertices") or []]
            raw_vertices = [v for v in raw_vertices if v is not None]
            mat_id = sub.get("mat_tex_id")
            material = (objects or {}).get(mat_id) if mat_id is not None else None
            tex_id = ((material or {}).get("material") or {}).get("texture_object_id") if isinstance(material, dict) else None
            texture = (objects or {}).get(tex_id) if tex_id is not None else None
            inst = SceneMeshInstance(model_id=node.id, model_name=node.name, submodel_index=sub.get("index"), object_id=sub.get("parent_id") if "parent_id" in sub else node.id, object_name=node.name, material_id=mat_id, material_name=str((material or {}).get("name", "")) if isinstance(material, dict) else "", texture_id=tex_id, texture_name=str((texture or {}).get("name", "")) if isinstance(texture, dict) else "", raw_vertices=raw_vertices, faces=[list(map(int, f)) for f in sub.get("faces") or [] if len(f) >= 3], source=sub)
            node.add_mesh_instance(inst)
            self.mesh_instances.append(inst)

    def meshes_for_view(self, mode: SceneViewMode = "assembled_scene", selected: str | int | SceneNode | None = None) -> list[SceneMeshInstance]:
        if selected is None or mode == "assembled_scene":
            return list(self.mesh_instances)
        node = selected if isinstance(selected, SceneNode) else self.nodes_by_id.get(selected) or self.nodes_by_name.get(str(selected))
        if node is None:
            return []
        return [mesh for child in node.walk() for mesh in child.mesh_instances]

    def preview_vertices(self, mode: SceneViewMode = "assembled_scene", selected: str | int | SceneNode | None = None) -> list[Vec3]:
        vertices: list[Vec3] = []
        for mesh in self.meshes_for_view(mode, selected):
            vertices.extend(mesh.vertices_for_view(mode))
        return vertices


def _vertex_position(value: Any) -> Vec3 | None:
    if isinstance(value, dict):
        value = value.get("position") or value.get("vertex") or value.get("xyz")
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    return None


def build_scene(decoded: Any) -> Scene:
    return Scene.from_decoded(decoded)

#!/usr/bin/env python3
"""Small generic mesh previewer for Fragmenter."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, sin
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import ttk

MAX_RENDER_EDGES = 20000
MAX_RENDER_POINTS = MAX_RENDER_EDGES
MAX_RENDER_TRIANGLES = 12000

Vec3 = tuple[float, float, float]
Color = tuple[int, int, int]


def _bounds(vertices: list[Vec3]) -> tuple[Vec3, Vec3] | None:
    if not vertices:
        return None
    xs, ys, zs = zip(*vertices)
    return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


@dataclass
class Mesh:
    vertices: list[Vec3] = field(default_factory=list)
    faces: list[list[int]] = field(default_factory=list)
    normals: list[Vec3] = field(default_factory=list)
    uvs: list[tuple[float, float]] = field(default_factory=list)
    vertex_colors: list[Color] = field(default_factory=list)
    material_id: int | str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def vertex_count(self) -> int: return len(self.vertices)
    @property
    def face_count(self) -> int: return len(self.faces)
    @property
    def names(self) -> list[str]: return list(self.source_metadata.get("names") or [])
    @property
    def warnings(self) -> list[str]: return self.source_metadata.setdefault("warnings", [])
    @property
    def errors(self) -> list[str]: return self.source_metadata.setdefault("errors", [])
    @property
    def bounds(self) -> tuple[Vec3, Vec3] | None: return _bounds(self.vertices)

    def edges(self, cap: int = MAX_RENDER_EDGES) -> tuple[list[tuple[int, int]], bool]:
        seen: set[tuple[int, int]] = set(); out: list[tuple[int, int]] = []
        capped = False
        for face in self.faces:
            if len(face) < 2: continue
            for a, b in zip(face, face[1:] + face[:1]):
                edge = (a, b) if a < b else (b, a)
                if edge in seen: continue
                seen.add(edge); out.append(edge)
                if len(out) >= cap:
                    capped = True; return out, capped
        return out, capped

    def summary(self) -> str:
        lines = [f"Vertices: {self.vertex_count}", f"Faces: {self.face_count}"]
        lines.append("Objects/groups: " + (", ".join(self.names) if self.names else "(none)"))
        if self.material_id is not None:
            lines.append(f"Material: {self.material_id}")
        if self.bounds:
            lo, hi = self.bounds
            lines.append(f"Bounds min: ({lo[0]:.6g}, {lo[1]:.6g}, {lo[2]:.6g})")
            lines.append(f"Bounds max: ({hi[0]:.6g}, {hi[1]:.6g}, {hi[2]:.6g})")
        if self.warnings:
            lines += ["", "Warnings:", *[f"- {w}" for w in self.warnings[:20]]]
            if len(self.warnings) > 20: lines.append(f"- ... {len(self.warnings) - 20} more")
        if self.errors:
            lines += ["", "Errors:", *[f"- {e}" for e in self.errors[:20]]]
        return "\n".join(lines) + "\n"

ObjMesh = Mesh


def parse_obj(path: str | Path) -> Mesh:
    mesh = Mesh(source_metadata={"source_format": "obj", "path": str(path), "names": [], "warnings": [], "errors": []}); path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        mesh.errors.append(f"Could not read OBJ file: {exc}"); return mesh
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith('#'): continue
        parts = line.split(); tag = parts[0]
        try:
            if tag == 'v':
                if len(parts) < 4: raise ValueError("vertex requires x y z")
                mesh.vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                if len(parts) >= 7:
                    mesh.vertex_colors.append(tuple(max(0, min(255, int(float(p) * (255 if float(p) <= 1 else 1)))) for p in parts[4:7]))
            elif tag == 'vn' and len(parts) >= 4:
                mesh.normals.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif tag == 'vt' and len(parts) >= 3:
                mesh.uvs.append((float(parts[1]), float(parts[2])))
            elif tag == 'usemtl' and len(parts) >= 2:
                mesh.material_id = " ".join(parts[1:])
            elif tag == 'f':
                face: list[int] = []
                for item in parts[1:]:
                    tok = item.split('/')[0]
                    if not tok: raise ValueError(f"empty vertex index in {item!r}")
                    idx = int(tok)
                    idx = len(mesh.vertices) + idx if idx < 0 else idx - 1
                    if idx < 0 or idx >= len(mesh.vertices): raise ValueError(f"vertex index {tok} out of range")
                    face.append(idx)
                if len(face) < 2: raise ValueError("face requires at least two vertices")
                mesh.faces.append(face)
            elif tag in {'o', 'g'}:
                name = " ".join(parts[1:]).strip() or f"(unnamed {tag} line {lineno})"
                if name not in mesh.source_metadata["names"]: mesh.source_metadata["names"].append(name)
        except ValueError as exc:
            mesh.warnings.append(f"line {lineno}: {exc}")
    if not mesh.vertices and not mesh.errors:
        mesh.errors.append("OBJ file contains no vertices.")
    if not mesh.faces and not mesh.errors:
        mesh.warnings.append("OBJ file contains no faces; only vertices/bounds can be shown.")
    return mesh


def mesh_from_structure_decoder_output(output: Any) -> Mesh:
    """Build a viewer-compatible Mesh from decoded structure/model output."""
    data = output.__dict__ if hasattr(output, "__dict__") else output
    metadata = {"source_format": "ccsf_structure_decoder", "warnings": [], "errors": []}
    vertices: list[Vec3] = []
    faces: list[list[int]] = []
    def add_model(model: dict[str, Any]) -> None:
        for sub in model.get("submodels") or []:
            base = len(vertices)
            for v in sub.get("vertices") or []:
                if len(v) >= 3: vertices.append((float(v[0]), float(v[1]), float(v[2])))
            for f in sub.get("faces") or []:
                if len(f) >= 3: faces.append([base + int(i) for i in f])
    for rec in data.get("records", []) if isinstance(data, dict) else []:
        model = rec.get("model")
        if isinstance(model, dict): add_model(model)
    if isinstance(data, dict):
        for entry in (data.get("object_lookup") or {}).values():
            model = entry.get("model") if isinstance(entry, dict) else None
            if isinstance(model, dict): add_model(model)
        metadata["input"] = data.get("input")
    if not vertices:
        metadata["warnings"].append("structure decoder output did not include decoded vertex arrays")
    return Mesh(vertices=vertices, faces=faces, source_metadata=metadata)


def mesh_from_scene(scene: Any, mode: str = "assembled_scene", selected: Any = None) -> Mesh:
    """Build a viewer Mesh from a ccsf_scene.Scene without mutating raw vertices."""
    metadata = {"source_format": "ccsf_scene", "view_mode": mode, "warnings": [], "errors": [], "names": []}
    vertices: list[Vec3] = []
    faces: list[list[int]] = []
    try:
        meshes = scene.meshes_for_view(mode, selected)
    except AttributeError:
        metadata["errors"].append("scene object does not provide meshes_for_view")
        return Mesh(source_metadata=metadata)
    for inst in meshes:
        base = len(vertices)
        name = getattr(inst, "object_name", "") or getattr(inst, "model_name", "")
        if name and name not in metadata["names"]:
            metadata["names"].append(name)
        vertices.extend(inst.vertices_for_view(mode))
        for face in getattr(inst, "faces", []) or []:
            if len(face) >= 3:
                faces.append([base + int(i) for i in face])
    return Mesh(vertices=vertices, faces=faces, source_metadata=metadata)


class MeshCanvasViewer(ttk.Frame):
    def __init__(self, master, mesh: Mesh, *, edge_cap: int = MAX_RENDER_EDGES, point_cap: int = MAX_RENDER_POINTS, triangle_cap: int = MAX_RENDER_TRIANGLES):
        super().__init__(master); self.mesh=mesh; self.edge_cap=edge_cap; self.point_cap=point_cap; self.triangle_cap=triangle_cap
        self.rx=-0.5; self.ry=0.7; self.zoom=1.0; self.pan=[0.0,0.0]
        self.show_bounds=tk.BooleanVar(value=True); self.show_wireframe=tk.BooleanVar(value=True); self.show_points=tk.BooleanVar(value=True); self.show_filled=tk.BooleanVar(value=True)
        self._last=None
        bar=ttk.Frame(self); bar.grid(row=0,column=0,sticky='ew'); bar.grid_columnconfigure(6, weight=1)
        ttk.Button(bar,text='Reset view',command=self.reset_view).grid(row=0,column=0,padx=4,pady=4)
        ttk.Checkbutton(bar,text='Filled',variable=self.show_filled,command=self.render).grid(row=0,column=1,padx=4)
        ttk.Checkbutton(bar,text='Wire',variable=self.show_wireframe,command=self.render).grid(row=0,column=2,padx=4)
        ttk.Checkbutton(bar,text='Points',variable=self.show_points,command=self.render).grid(row=0,column=3,padx=4)
        ttk.Checkbutton(bar,text='Bounds',variable=self.show_bounds,command=self.render).grid(row=0,column=4,padx=4)
        self.status=tk.StringVar(value=mesh.summary().split('\n')[0]); ttk.Label(bar,textvariable=self.status).grid(row=0,column=5,sticky='w')
        self.canvas=tk.Canvas(self,bg='#101418',highlightthickness=0); self.canvas.grid(row=1,column=0,sticky='nsew')
        self.grid_rowconfigure(1,weight=1); self.grid_columnconfigure(0,weight=1)
        self.canvas.bind('<Configure>', lambda e:self.render()); self.canvas.bind('<ButtonPress-1>', self._press); self.canvas.bind('<B1-Motion>', self._drag_left)
        self.canvas.bind('<ButtonPress-3>', self._press); self.canvas.bind('<B3-Motion>', self._drag_pan); self.canvas.bind('<MouseWheel>', self._wheel); self.canvas.bind('<Button-4>', lambda e:self._zoom(1.1)); self.canvas.bind('<Button-5>', lambda e:self._zoom(0.9))
        self.render()
    def reset_view(self): self.rx=-0.5; self.ry=0.7; self.zoom=1.0; self.pan=[0.0,0.0]; self.render()
    def _press(self,e): self._last=(e.x,e.y)
    def _drag_left(self,e):
        if e.state & 0x0001: return self._drag_pan(e)
        lx,ly=self._last or (e.x,e.y); self.ry+=(e.x-lx)*0.01; self.rx+=(e.y-ly)*0.01; self._last=(e.x,e.y); self.render()
    def _drag_pan(self,e):
        lx,ly=self._last or (e.x,e.y); self.pan[0]+=e.x-lx; self.pan[1]+=e.y-ly; self._last=(e.x,e.y); self.render()
    def _wheel(self,e): self._zoom(1.1 if e.delta>0 else 0.9)
    def _zoom(self,f): self.zoom=max(0.05,min(100,self.zoom*f)); self.render()
    def _transform(self, p):
        x,y,z=p; cy,sy=cos(self.ry),sin(self.ry); cx,sx=cos(self.rx),sin(self.rx)
        x,z=x*cy+z*sy,-x*sy+z*cy; y,z=y*cx-z*sx,y*sx+z*cx
        return x,y,z
    def _project_transformed(self, p):
        x,y,_=p; w=max(1,self.canvas.winfo_width()); h=max(1,self.canvas.winfo_height()); scale=self._base_scale()*self.zoom
        return (w/2+self.pan[0]+x*scale, h/2+self.pan[1]-y*scale)
    def _project(self, p): return self._project_transformed(self._transform(p))
    def _centered_vertices(self):
        if not self.mesh.bounds: return self.mesh.vertices
        lo,hi=self.mesh.bounds; c=tuple((lo[i]+hi[i])/2 for i in range(3))
        return [(x-c[0],y-c[1],z-c[2]) for x,y,z in self.mesh.vertices]
    def _base_scale(self):
        if not self.mesh.bounds: return 1
        lo,hi=self.mesh.bounds; span=max(hi[i]-lo[i] for i in range(3)) or 1
        return min(max(1,self.canvas.winfo_width()), max(1,self.canvas.winfo_height()))*0.42/span
    def _face_color(self, face):
        colors=[self.mesh.vertex_colors[i] for i in face if i < len(self.mesh.vertex_colors)]
        if not colors: return '#4c566a'
        avg=tuple(int(sum(c[i] for c in colors)/len(colors)) for i in range(3))
        return '#%02x%02x%02x' % avg
    def render(self):
        c=self.canvas; c.delete('all'); verts=self._centered_vertices(); transformed=[self._transform(v) for v in verts]; pts=[self._project_transformed(v) for v in transformed]
        w,h=max(1,c.winfo_width()),max(1,c.winfo_height()); cx,cy=w/2+self.pan[0],h/2+self.pan[1]
        c.create_line(cx,cy,cx+50*self.zoom,cy,fill='#f05',arrow='last'); c.create_text(cx+58*self.zoom,cy,text='X',fill='#f8a')
        c.create_line(cx,cy,cx,cy-50*self.zoom,fill='#5f5',arrow='last'); c.create_text(cx,cy-58*self.zoom,text='Y',fill='#afa')
        triangle_count=0; triangles_capped=False
        if self.show_filled.get():
            tris=[]
            for face in self.mesh.faces:
                if len(face) < 3: continue
                for i in range(1, len(face)-1):
                    tri=[face[0], face[i], face[i+1]]
                    if all(0 <= idx < len(pts) for idx in tri):
                        z=sum(transformed[idx][2] for idx in tri)/3; tris.append((z, tri))
            triangles_capped=len(tris)>self.triangle_cap
            for _, tri in sorted(tris, reverse=True)[:self.triangle_cap]:
                triangle_count+=1; flat=[coord for idx in tri for coord in pts[idx]]
                c.create_polygon(*flat, fill=self._face_color(tri), outline='')
        edges,capped=self.mesh.edges(self.edge_cap)
        if self.show_wireframe.get():
            for a,b in edges:
                if a < len(pts) and b < len(pts): c.create_line(*pts[a],*pts[b],fill='#d8dee9')
        point_count=0; points_capped=len(pts) > self.point_cap
        if self.show_points.get():
            point_count=min(len(pts), self.point_cap)
            for x,y in pts[:point_count]: c.create_oval(x-2,y-2,x+2,y+2,fill='#ebcb8b',outline='')
        if self.show_bounds.get() and self.mesh.bounds: self._draw_bounds(c)
        status=f"{self.mesh.vertex_count} vertices, {self.mesh.face_count} faces, {triangle_count} triangles, {len(edges)} edges, {point_count} points"
        caps=[]
        if capped: caps.append(f"edges capped at {self.edge_cap}")
        if points_capped: caps.append(f"points capped at {self.point_cap}")
        if triangles_capped: caps.append(f"triangles capped at {self.triangle_cap}")
        if caps: status += " (" + ", ".join(caps) + ")"
        if self.mesh.vertex_count and not self.mesh.face_count: status += "; point cloud only; no faces decoded"
        self.status.set(status)
    def _draw_bounds(self,c):
        lo,hi=self.mesh.bounds; cx=[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,(lo[2]+hi[2])/2]
        corners=[(x-cx[0],y-cx[1],z-cx[2]) for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
        pts=[self._project(p) for p in corners]
        for a,b in [(0,1),(0,2),(0,4),(3,1),(3,2),(3,7),(5,1),(5,4),(5,7),(6,2),(6,4),(6,7)]: c.create_line(*pts[a],*pts[b],fill='#88c0d0',dash=(3,3))

ObjCanvasViewer = MeshCanvasViewer


def create_mesh_viewer(master, mesh: Mesh) -> tuple[Mesh, MeshCanvasViewer | None]:
    if mesh.errors: return mesh, None
    return mesh, MeshCanvasViewer(master, mesh)


def create_obj_viewer(master, path: str | Path) -> tuple[Mesh, MeshCanvasViewer | None]:
    return create_mesh_viewer(master, parse_obj(path))

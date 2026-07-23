#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk, messagebox

SUPPORTED_EXTENSIONS = {".png", ".bmp", ".jpg", ".jpeg", ".gif"}


def _optional_pillow():
    try:
        from PIL import Image, ImageTk  # type: ignore
        return Image, ImageTk
    except Exception:
        return None, None


def _native_dimensions(path: Path, ext: str) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()[:64]
        if ext == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if ext == ".gif" and data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
            return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
        if ext == ".bmp" and data.startswith(b"BM") and len(data) >= 26:
            return int.from_bytes(data[18:22], "little", signed=True), abs(int.from_bytes(data[22:26], "little", signed=True))
        if ext in {".jpg", ".jpeg"}:
            with path.open("rb") as fh:
                if fh.read(2) != b"\xff\xd8":
                    return None
                while True:
                    marker_start = fh.read(1)
                    if not marker_start:
                        return None
                    if marker_start != b"\xff":
                        continue
                    marker = fh.read(1)
                    while marker == b"\xff":
                        marker = fh.read(1)
                    if marker in {b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf"}:
                        seg = fh.read(7)
                        if len(seg) < 7:
                            return None
                        return int.from_bytes(seg[3:5], "big"), int.from_bytes(seg[1:3], "big")
                    if marker in {b"\xd8", b"\xd9"}:
                        continue
                    length_bytes = fh.read(2)
                    if len(length_bytes) < 2:
                        return None
                    length = int.from_bytes(length_bytes, "big")
                    fh.seek(max(0, length - 2), 1)
    except Exception:
        return None
    return None


def sha1_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_texture_type(path: Path) -> str:
    ext = path.suffix.lower()
    guessed = None
    try:
        head = path.read_bytes()[:16]
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            guessed = "png"
        elif head.startswith((b"GIF87a", b"GIF89a")):
            guessed = "gif"
        elif head.startswith(b"BM"):
            guessed = "bmp"
        elif head.startswith(b"\xff\xd8\xff"):
            guessed = "jpg/jpeg"
    except Exception:
        guessed = None
    if guessed:
        return guessed
    return {
        ".png": "png (by extension)",
        ".bmp": "bmp (by extension)",
        ".jpg": "jpg/jpeg (by extension)",
        ".jpeg": "jpg/jpeg (by extension)",
        ".gif": "gif (by extension)",
        ".tm2": "PlayStation 2 TIM2 candidate",
        ".txd": "texture dictionary candidate",
    }.get(ext, "unknown")


def extract_metadata(path: Path) -> dict[str, Any]:
    path = Path(path)
    stat = path.stat()
    meta: dict[str, Any] = {
        "path": str(path),
        "file_size": stat.st_size,
        "sha1": sha1_file(path),
        "extension": path.suffix.lower() or "(none)",
        "guessed_type": guess_texture_type(path),
        "dimensions": None,
        "mode": None,
        "palette": None,
        "frames": None,
        "pillow_available": False,
    }

    Image, _ImageTk = _optional_pillow()
    if Image is not None:
        meta["pillow_available"] = True
        try:
            with Image.open(path) as img:
                meta["dimensions"] = (img.width, img.height)
                meta["mode"] = img.mode
                meta["palette"] = "yes" if img.getpalette() else "no"
                meta["frames"] = getattr(img, "n_frames", 1)
        except Exception as exc:
            meta["decode_error"] = str(exc)
            return meta

    if meta["dimensions"] is None:
        native_dims = _native_dimensions(path, str(meta["extension"]))
        if native_dims:
            meta["dimensions"] = native_dims

    if meta["dimensions"] is None and meta["extension"] in {".png", ".gif"}:
        try:
            img = tk.PhotoImage(file=str(path))
            meta["dimensions"] = (img.width(), img.height())
            meta["frames"] = 1
        except Exception as exc:
            meta.setdefault("decode_error", str(exc))

    return meta


def likely_format_hints(path: Path, guessed_type: str | None = None) -> list[str]:
    ext = path.suffix.lower()
    hints: list[str] = []
    if ext in {".tm2", ".tim2"}:
        hints.append("TIM2/PS2 texture candidate; export/decode the texture block before previewing.")
    if ext in {".ccs", ".bin"}:
        hints.append("Container-like file; texture pixels may be inside a section rather than at file offset 0.")
    if ext == ".bmp" or (guessed_type or "").lower().startswith("bmp"):
        hints.append("BMP filenames inside CCS may be references instead of embedded bitmap pixels.")
    if ext not in SUPPORTED_EXTENSIONS:
        hints.append("Try exporting raw data, then open it in a specialized viewer if this is a proprietary console texture.")
    hints.append("CCS note: .bmp strings inside CCS may be references, not embedded bitmap pixels.")
    hints.append("CCS note: Selecting TEX_sr4sun1 or sr4sun1.bmp may not preview pixels until the actual texture block is decoded/exported.")
    return hints


def metadata_text(meta: dict[str, Any], nearby_identifiers: list[str] | None = None, unsupported: bool = False) -> str:
    dims = meta.get("dimensions")
    dims_text = f"{dims[0]}x{dims[1]}" if isinstance(dims, tuple) else "not decoded"
    lines = []
    if unsupported:
        lines.append("No built-in decoder for this texture yet.")
        lines.append("")
    lines.extend([
        "Texture metadata:",
        f"  Path: {meta.get('path')}",
        f"  File size: {int(meta.get('file_size') or 0):,} bytes",
        f"  SHA1: {meta.get('sha1')}",
        f"  Extension: {meta.get('extension')}",
        f"  Guessed type: {meta.get('guessed_type')}",
        f"  Dimensions: {dims_text}",
        f"  Pillow available: {meta.get('pillow_available')}",
    ])
    if meta.get("mode") is not None:
        lines.append(f"  Mode: {meta.get('mode')}")
    if meta.get("palette") is not None:
        lines.append(f"  Palette: {meta.get('palette')}")
    if meta.get("frames") is not None:
        lines.append(f"  Frames: {meta.get('frames')}")
    if meta.get("decode_error"):
        lines.append(f"  Decode note: {meta.get('decode_error')}")
    if nearby_identifiers:
        lines.append("")
        lines.append("Nearby identifiers:")
        lines.extend(f"  - {x}" for x in nearby_identifiers[:25])
    hints = likely_format_hints(Path(str(meta.get("path"))), str(meta.get("guessed_type") or ""))
    if hints:
        lines.append("")
        lines.append("Likely format hints:")
        lines.extend(f"  - {x}" for x in hints)
    lines.append("")
    lines.append("Actions: use Raw Export/Open in external viewer or Open containing folder if preview is unavailable.")
    return "\n".join(lines) + "\n"


def render_texture_window(parent: tk.Misc, path: Path, nearby_identifiers: list[str] | None = None) -> dict[str, Any]:
    path = Path(path)
    meta = extract_metadata(path)
    top = tk.Toplevel(parent)
    top.title(f"Texture Preview: {path.name}")
    top.geometry("900x680")
    toolbar = ttk.Frame(top); toolbar.pack(fill="x", padx=8, pady=(8, 4))
    body = ttk.Frame(top); body.pack(fill="both", expand=True, padx=8, pady=4)
    status = ttk.Label(top, text=""); status.pack(fill="x", padx=8, pady=(4, 8))
    canvas = tk.Canvas(body, bg="#000000", highlightthickness=0); canvas.pack(fill="both", expand=True)
    fit = tk.BooleanVar(value=True)

    def open_folder():
        try:
            os.startfile(str(path.parent))
        except Exception:
            messagebox.showinfo("Containing folder", str(path.parent))

    ttk.Button(toolbar, text="Fit", command=lambda: (fit.set(True), render())).pack(side="left")
    ttk.Button(toolbar, text="Actual Size", command=lambda: (fit.set(False), render())).pack(side="left", padx=(6, 0))
    ttk.Button(toolbar, text="Open Folder", command=open_folder).pack(side="left", padx=(14, 0))

    image_obj = None
    pillow_src = None
    Image, ImageTk = _optional_pillow()
    ext = path.suffix.lower()
    try:
        if ext in {".png", ".gif"}:
            image_obj = tk.PhotoImage(file=str(path))
        elif Image is not None and ext in SUPPORTED_EXTENSIONS:
            pillow_src = Image.open(path)
            if getattr(pillow_src, "is_animated", False):
                pillow_src.seek(0)
            pillow_src.load()
    except Exception as exc:
        meta["decode_error"] = str(exc)

    if image_obj is None and pillow_src is None:
        canvas.destroy()
        text = tk.Text(body, wrap="word", bg="#111111", fg="#eeeeee")
        text.pack(fill="both", expand=True)
        text.insert("1.0", metadata_text(meta, nearby_identifiers, unsupported=True))
        text.configure(state="disabled")
        status.configure(text=f"Metadata only: {path}")
        return meta

    def render(_evt=None):
        nonlocal image_obj
        canvas.delete("all")
        if pillow_src is not None and ImageTk is not None:
            cw, ch = max(1, canvas.winfo_width() - 16), max(1, canvas.winfo_height() - 16)
            scale = min(cw / pillow_src.width, ch / pillow_src.height) if fit.get() else 1.0
            tw, th = max(1, int(pillow_src.width * scale)), max(1, int(pillow_src.height * scale))
            resampling = getattr(Image, "Resampling", Image)
            resized = pillow_src.resize((tw, th), resampling.LANCZOS if (tw, th) != pillow_src.size else resampling.NEAREST)
            image_obj = ImageTk.PhotoImage(resized)
        x = max(8, (canvas.winfo_width() - image_obj.width()) // 2)
        y = max(8, (canvas.winfo_height() - image_obj.height()) // 2)
        canvas.create_image(x, y, image=image_obj, anchor="nw")
        canvas.image = image_obj
        dims = meta.get("dimensions")
        dims_text = f"{dims[0]}x{dims[1]}" if isinstance(dims, tuple) else "metadata only"
        status.configure(text=f"{path.name} | {dims_text} | {path}")

    canvas.bind("<Configure>", render)
    render()
    return meta

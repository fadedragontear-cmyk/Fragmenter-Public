#!/usr/bin/env python3
"""V117 one-window ISO patch builder for the experimental patcher branch."""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from iso_patch_dispatcher import PatchError, patch_iso, select_engine


class FragmenterIsoBuilderMixinV117:
    """Add an isolated verified-ISO builder without changing RUN ALL."""

    def __init__(self) -> None:
        self._iso_builder_window_v117: tk.Toplevel | None = None
        self._iso_builder_queue_v117: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._iso_builder_running_v117 = False
        super().__init__()
        self.after_idle(self._install_iso_builder_menu_v117)

    def _install_iso_builder_menu_v117(self) -> None:
        try:
            menu_name = str(self.cget("menu") or "")
            menu = self.nametowidget(menu_name) if menu_name else None
        except (KeyError, tk.TclError):
            menu = None
        if not isinstance(menu, tk.Menu):
            menu = tk.Menu(self)
            self.configure(menu=menu)

        tools_menu: tk.Menu | None = None
        try:
            end = menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(menu.type(index)) != "cascade":
                    continue
                if str(menu.entrycget(index, "label")).strip().lower() != "tools":
                    continue
                candidate = self.nametowidget(str(menu.entrycget(index, "menu")))
                if isinstance(candidate, tk.Menu):
                    tools_menu = candidate
                    break
        except (KeyError, ValueError, tk.TclError):
            tools_menu = None

        if tools_menu is None:
            tools_menu = tk.Menu(menu, tearoff=False)
            menu.add_cascade(label="Tools", menu=tools_menu)

        try:
            end = tools_menu.index("end")
            for index in range((int(end) + 1) if end is not None else 0):
                if str(tools_menu.entrycget(index, "label")) == "Build Patched ISO...":
                    return
        except (ValueError, tk.TclError):
            pass
        tools_menu.add_command(label="Build Patched ISO...", command=self._open_iso_builder_v117)

    @staticmethod
    def _default_iso_output_v117(source_value: str) -> str:
        source = Path(source_value).expanduser()
        if not source_value.strip():
            return ""
        suffix = source.suffix if source.suffix else ".iso"
        return str(source.with_name(f"{source.stem} (patched){suffix}"))

    @staticmethod
    def _patch_summary_v117(manifest_path: Path) -> str:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PatchError(f"Could not read patch pack information: {exc}") from exc
        patch = payload.get("patch") if isinstance(payload, dict) else None
        if not isinstance(patch, dict):
            return f"Patch pack: {manifest_path.name}"
        name = str(patch.get("name") or manifest_path.stem)
        version = str(patch.get("version") or "").strip()
        credits = patch.get("credits")
        credit_text = ", ".join(str(value) for value in credits) if isinstance(credits, list) else ""
        summary = f"Patch pack: {name}"
        if version:
            summary += f" ({version})"
        if credit_text:
            summary += f"\nCredits: {credit_text}"
        return summary

    def _open_iso_builder_v117(self) -> None:
        existing = self._iso_builder_window_v117
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_force()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self)
        self._iso_builder_window_v117 = window
        window.title("Fragmenter - Build Patched ISO")
        window.geometry("760x430")
        window.minsize(680, 390)
        window.protocol("WM_DELETE_WINDOW", self._close_iso_builder_v117)

        self._iso_source_var_v117 = tk.StringVar()
        self._iso_manifest_var_v117 = tk.StringVar()
        self._iso_output_var_v117 = tk.StringVar()
        self._iso_status_var_v117 = tk.StringVar(
            value="Choose an original ISO and a Fragmenter patch pack."
        )

        outer = ttk.Frame(window, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)

        ttk.Label(
            outer,
            text="Build a patched game ISO",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            outer,
            text=(
                "Fragmenter verifies the original disc, chooses the safest engine, "
                "and always writes a separate output ISO."
            ),
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 18))

        self._iso_builder_row_v117(
            outer,
            2,
            "Original ISO",
            self._iso_source_var_v117,
            self._browse_iso_source_v117,
        )
        self._iso_builder_row_v117(
            outer,
            3,
            "Patch pack",
            self._iso_manifest_var_v117,
            self._browse_iso_manifest_v117,
        )
        self._iso_builder_row_v117(
            outer,
            4,
            "Output ISO",
            self._iso_output_var_v117,
            self._browse_iso_output_v117,
        )

        status_box = ttk.LabelFrame(outer, text="Plan", padding=12)
        status_box.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(18, 12))
        status_box.columnconfigure(0, weight=1)
        outer.rowconfigure(5, weight=1)
        ttk.Label(
            status_box,
            textvariable=self._iso_status_var_v117,
            wraplength=680,
            justify="left",
            anchor="nw",
        ).grid(row=0, column=0, sticky="nsew")

        self._iso_progress_v117 = ttk.Progressbar(status_box, mode="indeterminate")
        self._iso_progress_v117.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=6, column=0, columnspan=3, sticky="e")
        self._iso_analyze_button_v117 = ttk.Button(
            actions,
            text="Analyze",
            command=self._analyze_iso_patch_v117,
        )
        self._iso_analyze_button_v117.pack(side="left", padx=(0, 8))
        self._iso_build_button_v117 = ttk.Button(
            actions,
            text="Build Patched ISO",
            command=self._build_patched_iso_v117,
        )
        self._iso_build_button_v117.pack(side="left")
        ttk.Button(actions, text="Close", command=self._close_iso_builder_v117).pack(
            side="left", padx=(8, 0)
        )

    def _iso_builder_row_v117(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", padx=(12, 8), pady=5
        )
        ttk.Button(parent, text="Browse...", command=command).grid(
            row=row, column=2, sticky="e", pady=5
        )

    def _browse_iso_source_v117(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._iso_builder_window_v117,
            title="Choose the original game ISO",
            filetypes=(("ISO images", "*.iso"), ("All files", "*.*")),
        )
        if not selected:
            return
        self._iso_source_var_v117.set(selected)
        if not self._iso_output_var_v117.get().strip():
            self._iso_output_var_v117.set(self._default_iso_output_v117(selected))

    def _browse_iso_manifest_v117(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self._iso_builder_window_v117,
            title="Choose a Fragmenter patch pack",
            filetypes=(("Fragmenter patch manifests", "*.json"), ("All files", "*.*")),
        )
        if selected:
            self._iso_manifest_var_v117.set(selected)
            try:
                self._iso_status_var_v117.set(
                    self._patch_summary_v117(Path(selected))
                    + "\n\nChoose Analyze to verify the required ISO and patching method."
                )
            except Exception as exc:
                self._iso_status_var_v117.set(f"Cannot read patch pack: {exc}")

    def _browse_iso_output_v117(self) -> None:
        initial = self._iso_output_var_v117.get().strip()
        selected = filedialog.asksaveasfilename(
            parent=self._iso_builder_window_v117,
            title="Save patched ISO",
            defaultextension=".iso",
            initialfile=Path(initial).name if initial else "dotHack Fragment (patched).iso",
            initialdir=str(Path(initial).parent) if initial else None,
            filetypes=(("ISO images", "*.iso"), ("All files", "*.*")),
        )
        if selected:
            self._iso_output_var_v117.set(selected)

    def _iso_builder_paths_v117(self) -> tuple[Path, Path, Path]:
        source_value = self._iso_source_var_v117.get().strip()
        manifest_value = self._iso_manifest_var_v117.get().strip()
        output_value = self._iso_output_var_v117.get().strip()
        if not source_value or not manifest_value or not output_value:
            raise PatchError("Choose the original ISO, patch pack, and output ISO.")
        return (
            Path(source_value).expanduser().resolve(),
            Path(manifest_value).expanduser().resolve(),
            Path(output_value).expanduser().resolve(),
        )

    def _analyze_iso_patch_v117(self) -> None:
        try:
            source, manifest, _output = self._iso_builder_paths_v117()
            patch_summary = self._patch_summary_v117(manifest)
            selection = select_engine(source, manifest)
        except Exception as exc:
            self._iso_status_var_v117.set(f"Cannot build: {exc}")
            return

        if selection.resized_files:
            details = "\n".join(f"  - {path}" for path in selection.resized_files)
            self._iso_status_var_v117.set(
                f"{patch_summary}\n\nEngine: full UDF rebuild\n"
                f"{selection.reason}\nResized files:\n{details}"
            )
        else:
            self._iso_status_var_v117.set(
                f"{patch_summary}\n\nEngine: layout-preserving patch\n{selection.reason}"
            )

    def _build_patched_iso_v117(self) -> None:
        if self._iso_builder_running_v117:
            return
        try:
            source, manifest, output = self._iso_builder_paths_v117()
            if source == output:
                raise PatchError("Output ISO must not overwrite the original ISO.")
        except Exception as exc:
            messagebox.showerror("Build Patched ISO", str(exc), parent=self._iso_builder_window_v117)
            return

        overwrite = output.exists()
        if overwrite and not messagebox.askyesno(
            "Replace output ISO?",
            f"This output already exists:\n\n{output}\n\nReplace it safely?",
            parent=self._iso_builder_window_v117,
        ):
            return

        self._iso_builder_running_v117 = True
        self._iso_analyze_button_v117.configure(state="disabled")
        self._iso_build_button_v117.configure(state="disabled")
        self._iso_status_var_v117.set(
            "Verifying the original ISO and building a separate patched image..."
        )
        self._iso_progress_v117.start(12)

        worker = threading.Thread(
            target=self._iso_builder_worker_v117,
            args=(source, manifest, output, overwrite),
            daemon=True,
        )
        worker.start()
        self.after(100, self._poll_iso_builder_v117)

    def _iso_builder_worker_v117(
        self,
        source: Path,
        manifest: Path,
        output: Path,
        overwrite: bool,
    ) -> None:
        try:
            report = patch_iso(source, manifest, output, overwrite=overwrite)
        except Exception as exc:
            self._iso_builder_queue_v117.put(("error", str(exc)))
        else:
            self._iso_builder_queue_v117.put(("success", report))

    def _poll_iso_builder_v117(self) -> None:
        try:
            outcome, payload = self._iso_builder_queue_v117.get_nowait()
        except queue.Empty:
            if self._iso_builder_running_v117:
                self.after(100, self._poll_iso_builder_v117)
            return

        self._iso_builder_running_v117 = False
        self._iso_progress_v117.stop()
        self._iso_analyze_button_v117.configure(state="normal")
        self._iso_build_button_v117.configure(state="normal")

        if outcome == "error":
            self._iso_status_var_v117.set(f"Build refused: {payload}")
            messagebox.showerror(
                "Build Patched ISO",
                str(payload),
                parent=self._iso_builder_window_v117,
            )
            return

        report = payload if isinstance(payload, dict) else {}
        engine = str(report.get("engine") or "verified patch engine")
        output_report = report.get("output") if isinstance(report.get("output"), dict) else {}
        digest = str(output_report.get("sha256") or "")
        digest_line = f"\nSHA-256: {digest}" if digest else ""
        output_path = str(output_report.get("path") or self._iso_output_var_v117.get())
        message = f"Patched ISO created with {engine}.\n\n{output_path}{digest_line}"
        self._iso_status_var_v117.set(message)
        messagebox.showinfo("Build complete", message, parent=self._iso_builder_window_v117)

    def _close_iso_builder_v117(self) -> None:
        if self._iso_builder_running_v117:
            messagebox.showinfo(
                "Build in progress",
                "Wait for the ISO build to finish before closing this window.",
                parent=self._iso_builder_window_v117,
            )
            return
        window = self._iso_builder_window_v117
        self._iso_builder_window_v117 = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

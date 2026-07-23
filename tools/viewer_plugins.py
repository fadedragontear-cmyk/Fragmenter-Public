#!/usr/bin/env python3
from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_ARGS_TEMPLATE = "{path}"
LEGACY_VIEWER_NAME = "Default external viewer"


@dataclass
class ViewerConfig:
    """External asset viewer configuration persisted in fragmenter_gui_settings.json."""

    name: str = ""
    executable: str = ""
    args: str = DEFAULT_ARGS_TEMPLATE
    extensions: list[str] = field(default_factory=list)
    enabled: bool = True

    def normalized_name(self) -> str:
        return (self.name or "").strip() or LEGACY_VIEWER_NAME

    def normalized_extensions(self) -> list[str]:
        seen: set[str] = set()
        values: list[str] = []
        for ext in self.extensions:
            value = normalize_extension(ext)
            if value and value not in seen:
                seen.add(value)
                values.append(value)
        return values

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["name"] = self.normalized_name()
        payload["executable"] = (self.executable or "").strip()
        payload["args"] = (self.args or "").strip() or DEFAULT_ARGS_TEMPLATE
        payload["extensions"] = self.normalized_extensions()
        payload["enabled"] = bool(self.enabled)
        return payload


def normalize_extension(ext: str) -> str:
    value = str(ext or "").strip().lower()
    if not value:
        return ""
    return value if value.startswith(".") else f".{value}"


def parse_extensions(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    else:
        raw_items = [str(v) for v in value]
    extensions: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        ext = normalize_extension(item)
        if ext and ext not in seen:
            seen.add(ext)
            extensions.append(ext)
    return extensions


def _viewer_from_payload(payload: dict[str, Any], fallback_name: str = LEGACY_VIEWER_NAME) -> ViewerConfig | None:
    executable = str(payload.get("executable", payload.get("path", "")) or "").strip()
    args = str(payload.get("args", payload.get("args_template", DEFAULT_ARGS_TEMPLATE)) or DEFAULT_ARGS_TEMPLATE).strip()
    name = str(payload.get("name", fallback_name) or fallback_name).strip()
    enabled = bool(payload.get("enabled", True))
    extensions = parse_extensions(payload.get("extensions", []))
    if not executable and not name:
        return None
    return ViewerConfig(name=name or fallback_name, executable=executable, args=args or DEFAULT_ARGS_TEMPLATE, extensions=extensions, enabled=enabled)


def viewers_from_settings(settings: dict[str, Any]) -> list[ViewerConfig]:
    """Load new external_viewers plus legacy external viewer settings."""
    viewers: list[ViewerConfig] = []
    if isinstance(settings.get("external_viewers"), list):
        for idx, item in enumerate(settings["external_viewers"], start=1):
            if isinstance(item, dict):
                viewer = _viewer_from_payload(item, fallback_name=f"Viewer {idx}")
                if viewer:
                    viewers.append(viewer)

    # Backward compatibility with earlier settings layouts.
    legacy_payloads: list[dict[str, Any]] = []
    if isinstance(settings.get("external_viewer"), dict):
        legacy_payloads.append(settings["external_viewer"])
    if settings.get("external_viewer_path") or settings.get("external_viewer_args"):
        legacy_payloads.append(
            {
                "name": LEGACY_VIEWER_NAME,
                "executable": settings.get("external_viewer_path", ""),
                "args": settings.get("external_viewer_args", DEFAULT_ARGS_TEMPLATE),
            }
        )

    existing_names = {viewer.normalized_name() for viewer in viewers}
    for payload in legacy_payloads:
        viewer = _viewer_from_payload(payload)
        if viewer and viewer.executable and viewer.normalized_name() not in existing_names:
            viewers.append(viewer)
            existing_names.add(viewer.normalized_name())
    return viewers


def update_settings_with_viewers(settings: dict[str, Any], viewers: list[ViewerConfig]) -> dict[str, Any]:
    settings = dict(settings)
    settings["external_viewers"] = [viewer.to_json() for viewer in viewers]
    first = viewers[0] if viewers else ViewerConfig(name=LEGACY_VIEWER_NAME)
    # Preserve legacy keys for older Fragmenter builds/users.
    settings["external_viewer_path"] = (first.executable or "").strip()
    settings["external_viewer_args"] = (first.args or "").strip() or DEFAULT_ARGS_TEMPLATE
    settings["external_viewer"] = {
        "path": settings["external_viewer_path"],
        "args_template": settings["external_viewer_args"],
    }
    return settings


def build_viewer_command(target: Path, viewer: ViewerConfig, append_path_if_missing: bool = True) -> tuple[list[str], bool]:
    """Return argv and whether the target path had to be appended automatically."""
    executable = (viewer.executable or "").strip()
    if not executable:
        return [], False
    template = (viewer.args or "").strip()
    appended = False
    if not template:
        args = [str(target)]
        appended = True
    elif "{path}" in template:
        args = shlex.split(template.replace("{path}", str(target)))
    else:
        args = shlex.split(template)
        if append_path_if_missing:
            args.append(str(target))
            appended = True
    return [executable, *args], appended


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}

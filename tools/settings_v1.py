#!/usr/bin/env python3
"""Validated public settings model for Fragmenter 1.0."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from project_workspace_v1 import FragmenterProjectV1, save_project

SETTINGS_VERSION = 1
THEMES = {"system", "light", "dark"}
PREVIEW_MODES = {"assembled", "selected_object", "raw_model"}


def _hex_color(value: str) -> str:
    text = str(value or "").strip()
    if len(text) != 7 or not text.startswith("#"):
        raise ValueError("accent_color must be a #RRGGBB value")
    try:
        int(text[1:], 16)
    except ValueError as exc:
        raise ValueError("accent_color must be a #RRGGBB value") from exc
    return text.upper()


def _bounded_float(value: Any, low: float, high: float, name: str) -> float:
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return number


@dataclass
class AppearanceSettings:
    theme: str = "system"
    accent_color: str = "#4F7CAC"
    ui_scale: float = 1.0

    def validate(self) -> None:
        if self.theme not in THEMES:
            raise ValueError(f"Unsupported theme: {self.theme}")
        self.accent_color = _hex_color(self.accent_color)
        self.ui_scale = _bounded_float(self.ui_scale, 0.75, 2.0, "ui_scale")


@dataclass
class WorkspaceSettings:
    default_workspace_root: str = ""
    reuse_valid_cache: bool = True
    open_outputs_after_extraction: bool = False
    keep_diagnostics: bool = True


@dataclass
class PlaybackSettings:
    preferred_backend: str = "auto"
    default_volume: float = 1.0
    loop_previews: bool = False

    def validate(self) -> None:
        self.preferred_backend = str(self.preferred_backend or "auto").strip() or "auto"
        self.default_volume = _bounded_float(self.default_volume, 0.0, 2.0, "default_volume")


@dataclass
class Preview3DSettings:
    default_mode: str = "assembled"
    show_axes: bool = True
    show_origins: bool = False
    loop_animation: bool = True

    def validate(self) -> None:
        if self.default_mode not in PREVIEW_MODES:
            raise ValueError(f"Unsupported 3D preview mode: {self.default_mode}")


@dataclass
class AdvancedSettings:
    console_mode: bool = False
    enable_experimental_tools: bool = False


@dataclass
class CeldraSettings:
    enabled: bool = False
    animation_enabled: bool = True
    checklist_commentary: bool = False
    dynamic_ui: bool = True
    alt_f4_easter_egg: bool = True


@dataclass
class FragmenterSettingsV1:
    version: int = SETTINGS_VERSION
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    workspace: WorkspaceSettings = field(default_factory=WorkspaceSettings)
    playback: PlaybackSettings = field(default_factory=PlaybackSettings)
    preview_3d: Preview3DSettings = field(default_factory=Preview3DSettings)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    celdra: CeldraSettings = field(default_factory=CeldraSettings)

    def validate(self) -> None:
        if int(self.version) != SETTINGS_VERSION:
            raise ValueError(f"Unsupported settings version: {self.version}")
        self.appearance.validate()
        self.playback.validate()
        self.preview_3d.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FragmenterSettingsV1":
        data = payload if isinstance(payload, dict) else {}
        version = int(data.get("version") or SETTINGS_VERSION)
        settings = cls(
            version=version,
            appearance=AppearanceSettings(**_known(data.get("appearance"), AppearanceSettings)),
            workspace=WorkspaceSettings(**_known(data.get("workspace"), WorkspaceSettings)),
            playback=PlaybackSettings(**_known(data.get("playback"), PlaybackSettings)),
            preview_3d=Preview3DSettings(**_known(data.get("preview_3d"), Preview3DSettings)),
            advanced=AdvancedSettings(**_known(data.get("advanced"), AdvancedSettings)),
            celdra=CeldraSettings(**_known(data.get("celdra"), CeldraSettings)),
        )
        settings.validate()
        return settings


def _known(payload: Any, model: type) -> dict[str, Any]:
    values = payload if isinstance(payload, dict) else {}
    return {key: values[key] for key in model.__dataclass_fields__ if key in values}


def load_project_settings(project: FragmenterProjectV1) -> FragmenterSettingsV1:
    return FragmenterSettingsV1.from_dict(project.settings)


def save_project_settings(project: FragmenterProjectV1, settings: FragmenterSettingsV1) -> FragmenterProjectV1:
    project.settings = settings.to_dict()
    save_project(project)
    return project


def settings_view_model(settings: FragmenterSettingsV1) -> dict[str, Any]:
    settings.validate()
    return {
        "sections": [
            {"key": "appearance", "label": "Appearance", "values": asdict(settings.appearance)},
            {"key": "workspace", "label": "Workspace", "values": asdict(settings.workspace)},
            {"key": "playback", "label": "Playback", "values": asdict(settings.playback)},
            {"key": "preview_3d", "label": "3D Preview", "values": asdict(settings.preview_3d)},
            {"key": "advanced", "label": "Advanced", "values": asdict(settings.advanced)},
            {"key": "celdra", "label": "Celdra", "values": asdict(settings.celdra)},
        ]
    }

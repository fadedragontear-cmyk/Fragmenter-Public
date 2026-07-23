#!/usr/bin/env python3
"""Install strict SCEIMidi routing authority without replacing preserved raw reports."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import scei_midi_v4
import snddata_forensics_v1
import snddata_music_system_v5 as music_v5

PARSER_REVISION = "scei_midi_v4_strict_7bit"
_ORIGINAL_ANALYZE = music_v5.analyze_project_snddata
_ORIGINAL_CURRENT = music_v5.catalog_is_current
_INSTALLED = False


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _stamp_reports(project: Any) -> None:
    catalog_path = music_v5.catalog_path(project)
    summary_path = music_v5.summary_path(project)
    catalog: dict[str, Any] = {}
    if catalog_path.is_file():
        try:
            value = json.loads(catalog_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                catalog = value
        except (OSError, json.JSONDecodeError):
            catalog = {}
    summary = catalog.setdefault("summary", {}) if catalog else {}
    if not isinstance(summary, dict):
        summary = {}
        catalog["summary"] = summary
    summary.update(
        {
            "parser_revision": PARSER_REVISION,
            "routing_authority": (
                "Only events before the first channel-message data value outside 0..127 "
                "may influence notes or Program routing."
            ),
            "renderer_claim": (
                "Renderer-complete means only that current diagnostic inputs exist; "
                "it is not proof of authentic music."
            ),
        }
    )
    if catalog:
        _atomic_json(catalog_path, catalog)
    if summary_path.is_file():
        try:
            value = json.loads(summary_path.read_text(encoding="utf-8"))
            standalone = value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            standalone = {}
        standalone.update(summary)
        _atomic_json(summary_path, standalone)


def analyze_project_snddata(
    project: Any,
    *,
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    result = _ORIGINAL_ANALYZE(project, callback=callback)
    _stamp_reports(project)
    return {
        **result,
        "parser_revision": PARSER_REVISION,
        "confirmation_allowed": False,
    }


def catalog_is_current(project: Any, payload: dict[str, Any] | None = None) -> bool:
    if payload is None:
        target = music_v5.catalog_path(project)
        if not target.is_file():
            return False
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
            payload = value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return False
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict) or summary.get("parser_revision") != PARSER_REVISION:
        return False
    return _ORIGINAL_CURRENT(project, payload)


def _strict_readiness(
    project: Any,
    original: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    """Expose a present-but-pre-strict catalog as stale rather than ready."""
    state = dict(original(project))
    target = Path(str(state.get("catalog") or music_v5.catalog_path(project)))
    file_exists = target.is_file()
    current = bool(file_exists and catalog_is_current(project))
    state.update(
        {
            "catalog_file_exists": file_exists,
            "catalog_exists": current,
            "catalog_stale": bool(file_exists and not current),
            "parser_revision": PARSER_REVISION,
            "catalog_readiness_reason": (
                "current strict 7-bit catalog"
                if current
                else "mixer catalog must be rebuilt for strict 7-bit routing"
                if file_exists
                else "mixer catalog is missing"
            ),
        }
    )
    return state


def _strict_reviewed_routing(rows: list[dict[str, Any]]) -> str:
    """Do not let a merely plausible legacy audition steer Auto routing."""
    row = next(
        (
            item
            for item in rows
            if isinstance(item, dict)
            and item.get("status") == "confirmed"
            and item.get("routing_mode")
        ),
        None,
    )
    return str(row["routing_mode"]) if row else ""


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    snddata_forensics_v1.scei_midi_v3 = scei_midi_v4
    music_v5.scei_midi_v3 = scei_midi_v4
    music_v5.analyze_project_snddata = analyze_project_snddata
    music_v5.catalog_is_current = catalog_is_current

    # Patch the readable workbench before GUI/cache modules bind its functions.
    import snddata_research_workbench_v1 as workbench

    original_readiness = workbench.readiness

    def readiness(project: Any) -> dict[str, Any]:
        return _strict_readiness(project, original_readiness)

    workbench.readiness = readiness
    workbench._reviewed_routing = _strict_reviewed_routing
    workbench.FILTERS = (
        "All",
        "Renderable",
        "Needs research",
        "Saved mapping",
        "Reviewed",
    )
    _INSTALLED = True

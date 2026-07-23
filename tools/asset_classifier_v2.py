#!/usr/bin/env python3
"""Evidence-based CCSF asset classification for the public Fragmenter browser.

The original offline .hack naming notes are useful heuristics, not authoritative
Fragment format documentation. Directly observed Fragment naming and size families
are treated as stronger evidence and can override a broad legacy scene label.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


CATEGORY_ORDER = (
    "Environment / Field",
    "Skybox / Background",
    "Wallpaper",
    "Profile Picture / Portrait",
    "Monster / Boss",
    "Eight Phases candidate",
    "Grunty",
    "Food",
    "Weapon",
    "Object / Prop",
    "Character / NPC",
    "Summon / Statue / Entity candidate",
    "X-Series / Unclassified",
    "Animation-only",
    "Texture / Material",
    "UI / System",
    "Unknown CCSF",
)


def _text(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).replace("\\", "/").lower()


def _stem_tokens(name: str, relative_path: str) -> tuple[str, str, str]:
    stem = Path(name or relative_path).stem.lower()
    relative = relative_path.replace("\\", "/").lower()
    compact = re.sub(r"[^a-z0-9]+", "", stem)
    return stem, relative, compact


def _result(category: str, confidence: str, evidence: list[str], *, source: str = "Fragmenter heuristic") -> dict[str, Any]:
    return {
        "category": category,
        "confidence": confidence,
        "evidence": evidence,
        "classification_source": source,
    }


def x_family_number(name: str, relative_path: str = "") -> int | None:
    """Return the leading x-family number while allowing descriptive suffixes."""
    _stem, _relative, compact = _stem_tokens(name, relative_path)
    match = re.match(r"^x(\d{2,3})(?!\d)", compact)
    return int(match.group(1)) if match else None


def classify_visual_asset(
    *,
    name: str,
    relative_path: str,
    existing_kind: str = "",
    resource_counts: dict[str, Any] | None = None,
    identifiers: list[str] | None = None,
    size: int | None = None,
) -> dict[str, Any]:
    """Classify one visual asset with direct Fragment evidence taking priority."""
    counts = {str(key).upper(): int(value or 0) for key, value in (resource_counts or {}).items()}
    identifiers = [str(value) for value in (identifiers or [])]
    stem, relative, compact = _stem_tokens(name, relative_path)
    hay = _text(name, relative_path, existing_kind, *identifiers)
    old_kind = str(existing_kind or "").lower()
    byte_size = max(0, int(size or 0))

    if "system/frontend" in old_kind or "ui/frontend" in old_kind:
        return _result("UI / System", "high", [f"existing structural category: {existing_kind}"])
    if "animation-only" in old_kind or (counts.get("ANM", 0) and not any(counts.get(key, 0) for key in ("MDL", "OBJ", "TEX", "CLT"))):
        return _result("Animation-only", "high", ["ANM records without model/texture records"])
    if "texture/material" in old_kind or ((counts.get("TEX", 0) or counts.get("CLT", 0)) and not counts.get("MDL", 0) and not counts.get("OBJ", 0)):
        return _result("Texture / Material", "high", ["texture/palette records without model geometry"])

    # User-reviewed Fragment families. These rules only affect automatic categories;
    # manual classifications, notes, flags and saved views remain authoritative.
    if compact.startswith("xdl_load") or compact.startswith("xdl_log") or compact in {"xdlload", "xdllog"}:
        return _result("UI / System", "high", ["xdl login/loading screen family"], source="user-confirmed visual review")
    if compact.startswith("xgbbox"):
        return _result("Object / Prop", "high", ["xgbbox chest/container family"], source="user-confirmed visual review")
    if compact.startswith("xgfood") or "x_g_food" in hay:
        return _result("Food", "high", ["x_g_food naming family"], source="user-confirmed naming heuristic")
    if re.match(r"^xgs(?:[a-z]+bod1|ymbol|virus\d*|water\d*)$", compact):
        return _result(
            "Summon / Statue / Entity candidate",
            "high",
            ["xgs special entity/statue family"],
            source="user-confirmed visual review",
        )
    if compact.startswith("xddwal"):
        return _result("Wallpaper", "high", ["xddwal wallpaper naming family"], source="user-confirmed naming heuristic")
    if compact.startswith("xp") and byte_size == 18112:
        return _result(
            "Profile Picture / Portrait",
            "high",
            ["xp prefix with observed 18,112-byte portrait size"],
            source="user-confirmed naming/size heuristic",
        )
    if compact.startswith("cdogbod"):
        return _result("Grunty", "high", ["c_dog_bod naming family"], source="user-confirmed naming heuristic")
    if compact.startswith("cwdhsw"):
        return _result("Weapon", "high", ["cwdhsw weapon family"], source="user-confirmed visual review")
    if re.match(r"^cts[2-9]\d*$", compact):
        return _result("Monster / Boss", "high", ["reviewed cts2+ monster family"], source="user-confirmed visual review")
    if compact.startswith("ctw"):
        return _result("Character / NPC", "high", ["reviewed ctw character family"], source="user-confirmed visual review")
    if re.match(r"^cw(?:[_-]?\d|[a-z])", stem) or "/cw" in relative:
        return _result("Weapon", "high", ["cw weapon prefix"], source="user-confirmed naming heuristic")
    if stem.startswith("hst") or any(value.lower().startswith(("mdl_hst", "obj_hst", "tex_hst")) for value in identifiers):
        return _result("Weapon", "medium", ["hst staff/resource prefix from offline-game notes"], source="offline-series heuristic")
    if compact.startswith("ct"):
        return _result(
            "Character / NPC",
            "medium",
            ["ct character naming family"],
            source="user-confirmed naming heuristic",
        )

    x_number = x_family_number(name, relative_path)
    if x_number is not None and 11 <= x_number <= 81:
        return _result(
            "Eight Phases candidate",
            "low",
            [f"offline x11-x81 boss range with optional suffix: x{x_number}"],
            source="offline-series heuristic",
        )
    if x_number is not None and 100 <= x_number <= 706:
        return _result(
            "Summon / Statue / Entity candidate",
            "low",
            [f"offline x100-x706 entity range with optional suffix: x{x_number}"],
            source="offline-series heuristic",
        )
    if x_number is not None:
        return _result(
            "X-Series / Unclassified",
            "low",
            [f"x-family filename x{x_number:03d}; role not yet confirmed"],
            source="Fragment filename inventory",
        )
    if "aura" in hay or "caur" in hay:
        return _result("Character / NPC", "high", ["Aura/caur naming signal"])

    environment_terms = ("field", "dungeon", "town", "stage", "map", "room", "floor")
    background_terms = ("sky", "skybox", "background", "back", "_bg", "/bg", "bg_")
    if "field/stage" in old_kind or "environment/background" in old_kind:
        category = "Skybox / Background" if any(term in hay for term in background_terms) else "Environment / Field"
        return _result(category, "high", [f"existing structural category: {existing_kind}"])
    if any(term in hay for term in environment_terms) or re.search(r"(?:^|[/_.-])s(?:r|f|e)\d", hay):
        return _result("Environment / Field", "medium", ["field/stage/town naming or scene-path signal"])
    if any(term in hay for term in background_terms) or stem.startswith("bg"):
        return _result("Skybox / Background", "medium", ["background/skybox naming signal"])

    match = re.match(r"^e(\d{3})(?!\d)", compact)
    if match and 648 <= int(match.group(1)) <= 780:
        return _result("Monster / Boss", "medium", [f"offline enemy range e{match.group(1)}"], source="offline-series heuristic")

    if re.search(r"(?:^|[/_.-])(npc|pc|char|character)(?:$|[/_.-])", hay):
        return _result("Character / NPC", "medium", ["character/NPC naming signal"])
    if "character" in old_kind:
        return _result(
            "Character / NPC",
            "low",
            [f"legacy classifier result retained without filename confirmation: {existing_kind}"],
        )
    if counts.get("MDL", 0) or counts.get("OBJ", 0):
        return _result("Unknown CCSF", "low", ["contains model geometry but no reliable category signal"])
    return _result("Unknown CCSF", "low", ["no reliable naming or structural category signal"])


def category_sort_key(category: str) -> int:
    try:
        return CATEGORY_ORDER.index(category)
    except ValueError:
        return len(CATEGORY_ORDER)

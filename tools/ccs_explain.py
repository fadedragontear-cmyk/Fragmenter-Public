#!/usr/bin/env python3
"""Human-readable explanations for common CCS/CCSF workbench identifiers."""
from __future__ import annotations

import argparse
import json


KNOWN_PREFIXES = ("OBJ_", "MDL_", "DMY_", "CMP_", "TEX_", "MAT_", "CLT_")
ROOT_TOWN_SHOPS = {
    "sr4wep1": "Weapon Shop family",
    "sr4ite1": "Item Shop family",
    "sr4mag1": "Magic Shop family",
    "sr4sav1": "Recorder / Save shop family",
    "sr4fai1": "Elf's Haven / storage shop family",
}


def _normalize_identifier(raw: str) -> tuple[str | None, str, list[str]]:
    """Strip common CCS label prefixes and service-location suffixes."""
    prefix = None
    normalized = raw
    suffixes: list[str] = []

    for known_prefix in KNOWN_PREFIXES:
        if normalized.upper().startswith(known_prefix):
            prefix = known_prefix[:-1].upper()
            normalized = normalized[len(known_prefix) :]
            break

    while True:
        lower_normalized = normalized.lower()
        if lower_normalized.endswith("pos"):
            suffixes.append("pos")
            normalized = normalized[:-3]
            continue

        stripped_numbered_suffix = False
        for numbered_suffix in ("_1", "_2"):
            if lower_normalized.endswith(numbered_suffix):
                suffixes.append(numbered_suffix)
                normalized = normalized[: -len(numbered_suffix)]
                stripped_numbered_suffix = True
                break
        if not stripped_numbered_suffix:
            break

    return prefix, normalized.lower(), suffixes


def _shop_note(prefix: str | None, family: str, suffixes: list[str]) -> str:
    if prefix == "OBJ":
        return f"Object entry for {family}; likely a root-town service/shop family label."
    if prefix == "MDL":
        return f"Model entry for {family}; likely renderable service/shop-family geometry, not inventory data."
    if prefix == "DMY" and "pos" in suffixes:
        return f"Position/dummy marker for {family}; use as placement metadata and do not assume inventory."
    if prefix == "CMP":
        return f"Component/container-ish label for {family}; exact function is uncertain, so do not assume inventory."
    return f"{family}; likely root-town shop/service family, not a complete inventory table by itself."


def explain_identifier(name: str) -> dict[str, object]:
    raw = name.strip()
    lower = raw.lower()
    prefix, normalized, suffixes = _normalize_identifier(raw)
    notes: list[str] = []
    warnings: list[str] = []
    category = "unknown"
    confidence = "medium"

    if normalized in ROOT_TOWN_SHOPS:
        family = ROOT_TOWN_SHOPS[normalized]
        category = "root_town_shop"
        confidence = "likely/high"
        notes.append(_shop_note(prefix, family, suffixes))
        if prefix in {"OBJ", "MDL", "DMY", "CMP"} or suffixes:
            detected_suffixes = ", ".join(suffixes) or "none"
            notes.append(
                f"Normalized identifier: {normalized}; detected prefix: "
                f"{prefix or 'none'}; detected suffixes: {detected_suffixes}."
            )
        warnings.append("Likely identifies a shop/service asset family; do not assume inventory or price data from this label alone.")
    elif lower.startswith("dmy_merchant"):
        category = "dummy_marker"
        notes.append("Likely merchant dummy/marker used as a placement or helper anchor rather than renderable geometry.")
        warnings.append("Probably not the visible NPC model or inventory table by itself.")
        warnings.append("Changing merchant dummy names or transforms may affect NPC/shop placement.")
    elif lower == "dmy_gate":
        category = "dummy_marker"
        notes.append("Likely Chaos Gate/gate-related marker for a transition, door, spawn, or navigation anchor.")
        warnings.append("Treat as logic-sensitive metadata, not decorative art.")
    elif lower.startswith("lgt_shop"):
        category = "light"
        notes.append("Shop light marker or light asset used by shop/town scenes.")
        warnings.append("Do not assume this is shop inventory; LGT_ identifiers are usually lighting-related.")
        warnings.append("Lighting edits can change scene readability and may expose missing assets.")
    elif normalized == "sr4sun1":
        category = "background_candidate"
        confidence = "likely"
        if prefix == "MDL":
            notes.append("Model/geometry entry for sun/sky/background element candidate.")
        else:
            notes.append("Sun/sky/background candidate seen in town probes; likely visual/background-related.")
    elif normalized in {"sr4clo1", "sr4clo2"}:
        category = "background_candidate"
        confidence = "likely"
        if prefix == "MDL":
            notes.append("Model/geometry entry for cloud/background element candidate.")
        else:
            notes.append("Cloud/background candidate seen in town probes; likely visual/background-related.")
    elif lower == "blt_bg":
        category = "background_label"
        confidence = "likely"
        notes.append("Background-related label candidate; exact renderer or bundle role is uncertain.")
    elif prefix == "CLT" and normalized.startswith("sr4"):
        category = "background_label"
        confidence = "candidate"
        notes.append("Likely texture/material/color lookup/background-related label; exact CLT function is uncertain.")
    elif prefix == "TEX" and normalized.startswith("sr4"):
        category = "texture"
        confidence = "likely"
        notes.append("Texture entry for SR4 town/background/service asset family; inspect neighboring labels before assigning exact use.")
    elif prefix == "MAT" and normalized.startswith("sr4"):
        category = "material"
        confidence = "likely"
        notes.append("Material entry for SR4 town/background/service asset family; exact shader/material role is candidate-level until verified.")
    elif prefix == "OBJ" and normalized.startswith("sr4"):
        category = "root_town_shop"
        confidence = "candidate"
        notes.append("Object entry for SR4 service/shop-family candidate; family is not in the root-town shop mapping table, so do not assume inventory.")
    elif prefix == "MDL" and normalized.startswith("sr4"):
        category = "model"
        confidence = "candidate"
        notes.append("Model entry for SR4 service/shop/background-family candidate; exact function is uncertain.")
    elif prefix == "DMY" and normalized.startswith("sr4") and "pos" in suffixes:
        category = "dummy_marker"
        confidence = "candidate"
        notes.append("Position/dummy marker for SR4 service/shop-family candidate; use as placement metadata and do not assume inventory.")
    elif prefix == "CMP" and normalized.startswith("sr4"):
        category = "component_or_container_label"
        confidence = "candidate"
        notes.append("Component/container-ish SR4 label; exact function is uncertain, so do not assume inventory.")
    elif lower == "data.bin":
        category = "packed_asset_archive"
        notes.append("Likely client packed asset archive when found on the ISO; Area Server DATA.bin-like files can also be packed bundles.")
        warnings.append("Use read-only safe mode unless you are deliberately creating a patch plan.")
    elif lower == "town04.cmp":
        category = "compressed_ccs_member"
        notes.append("Area Server town.bin member 8 / root town payload; commonly identified as CCSFtown04.")
        warnings.append("Do not assume a .cmp can be blindly recompressed into the original slot.")
    elif lower.endswith(".cmp") or lower == ".cmp":
        category = "compressed_ccs_member"
        notes.append("Compressed CCS/CCSF member file commonly embedded in Area Server data.")
        warnings.append("Do not assume a .cmp can be blindly recompressed into the original slot.")
    elif "padded gzip" in lower or "gzip member" in lower:
        category = "container_layout"
        notes.append("Padded gzip members are independently compressed members separated by slot padding/alignment.")
        warnings.append("Preserve raw_start, raw_end, slot_end, and padding when patching.")
    elif "area server" in lower:
        category = "area_server_file"
        notes.append("Area Server files drive server-side town/area behavior and may contain gzip members or CCSF payloads.")
        warnings.append("Keep originals untouched and write proposed edits to workspace patch plans.")
    elif "iso client" in lower or "iso asset" in lower:
        category = "iso_client_asset"
        notes.append("ISO client assets are read by the game client from the disc image.")
        warnings.append("Do not confuse client art assets with Area Server logic/data files.")
    elif "patch plan" in lower:
        category = "patch_plan"
        notes.append("Patch plans are workbench instructions/records for proposed changes, not source assets.")
    elif "read-only safe mode" in lower or "safe mode" in lower:
        category = "safety"
        notes.append("Read-only safe mode allows inspection and reporting while blocking direct source modifications.")
        warnings.append("Disable only when you have backups and intend to write derived outputs.")
    else:
        confidence = "low"
        notes.append("No specific explanation is registered; use identifier extraction context and nearby asset names.")

    return {"name": name, "category": category, "confidence": confidence, "summary": notes[0], "notes": notes, "warnings": warnings}


def _main() -> None:
    parser = argparse.ArgumentParser(description="Explain CCS/CCSF workbench identifiers.")
    parser.add_argument("name")
    args = parser.parse_args()
    print(json.dumps(explain_identifier(args.name), indent=2))


if __name__ == "__main__":
    _main()

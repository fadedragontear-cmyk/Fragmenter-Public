#!/usr/bin/env python3
"""External exact-name texture registry with conservative CLUT recovery."""
from __future__ import annotations

from typing import Any

import ccsf_texture_decoder_v2 as texture_v2
import ccsf_texture_registry_v1 as v1
import ccsf_texture_resolution_v1 as resolution_v1

resolve_clut_by_name = v1.resolve_clut_by_name
resolve_texture_by_name = v1.resolve_texture_by_name
resolve_material_texture_by_name = v1.resolve_material_texture_by_name
clear_registry_cache = v1.clear_registry_cache


def _decode_texture_record(decoded: dict[str, Any], record: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    try:
        texture = texture_v2.parse_texture_record(decoded["data"], record, decoded["generation"])
        if texture.get("status") != "pixel_data_decoded":
            return None, str(texture.get("warnings") or texture.get("status") or "texture metadata only")

        cluts = decoded["cluts"]
        # Populate the cache once so exact and same-subfile candidates share the
        # same parsed CLUT objects.
        for candidate_record in decoded["report"].records:
            if int(candidate_record.get("masked_section_type") or 0) != 0x0400:
                continue
            candidate_id = int(candidate_record.get("object_id") or -1)
            if candidate_id in cluts:
                continue
            try:
                parsed_clut = texture_v2.parse_clut_record(decoded["data"], candidate_record)
                entry = decoded["report"].object_lookup.get(candidate_id) or {}
                parsed_clut["owning_file_id"] = entry.get("file_id")
                cluts[candidate_id] = parsed_clut
            except Exception:
                continue

        clut, clut_evidence = resolution_v1.resolve_clut_for_texture(
            decoded["report"],
            record,
            texture,
            cluts,
        )
        indexed = int(texture.get("texture_type") or 0) in {texture_v2.TEXTURE_I4, texture_v2.TEXTURE_I8}
        external_clut_evidence = None
        if indexed and clut is None:
            clut_id = int(texture.get("clut_id") or -1)
            entry = decoded["report"].object_lookup.get(clut_id) or {}
            clut_name = str(entry.get("name") or "")
            if clut_name:
                clut, external_clut_evidence = v1.resolve_clut_by_name(decoded["path"], clut_name)
            if clut is None:
                return None, f"indexed texture CLUT {clut_id} {clut_name!r} is not decoded locally or externally"

        texture["rgba"] = texture_v2.decode_rgba(texture, clut)
        texture["clut_resolved"] = clut is not None
        texture["clut_resolution"] = clut_evidence
        texture["clut_resolution_status"] = clut_evidence.get("status")
        texture["resolved_clut_id"] = (clut or {}).get("object_id")
        texture["clut_external"] = bool(clut and clut.get("external_source"))
        texture["clut_external_source"] = (clut or {}).get("external_source")
        texture["clut_mapping_evidence"] = external_clut_evidence
        texture["external_source"] = str(decoded["path"])
        texture["external_object_id"] = int(record.get("object_id") or 0)
        texture["resolution_source"] = "exact texture setup record with exact or unique compatible CLUT"
        if texture["clut_external"]:
            detail = "decoded with exact external CLUT"
        elif clut_evidence.get("status") == "unique_same_subfile_fallback":
            detail = "decoded with unique compatible same-subfile CLUT"
        else:
            detail = "decoded"
        return texture, detail
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def install() -> None:
    """Install the enhanced decoder into v1's exact-name resolver functions."""
    v1._decode_texture_record = _decode_texture_record

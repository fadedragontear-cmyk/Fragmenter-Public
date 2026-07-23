#!/usr/bin/env python3
"""Add per-animation object puppetry bindings to the StudioCCS-style contents tree."""
from __future__ import annotations

from typing import Any

import ccsf_asset_tree_v1 as base
import ccsf_gen1_pose_v6 as pose_v6
import ccsf_puppetry_v1 as puppetry_v1

_BASE_INSPECT = base.inspect_ccsf_contents


def _puppetry_group(parsed: Any) -> dict[str, Any]:
    catalog = puppetry_v1.controller_catalog(parsed)
    by_animation: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in catalog:
        key = (int(row.get("animation_id") or 0), str(row.get("animation_name") or ""))
        by_animation.setdefault(key, []).append(row)

    animations: list[dict[str, Any]] = []
    for (animation_id, animation_name), controllers in by_animation.items():
        part_nodes: list[dict[str, Any]] = []
        for row in controllers:
            track_details = {
                name: {
                    "status": track.get("status"),
                    "key_count": track.get("key_count"),
                    "key_frames": list(track.get("key_frames") or []),
                    "fixed": track.get("fixed"),
                    "keys": list(track.get("keys") or []),
                }
                for name, track in (row.get("tracks") or {}).items()
                if isinstance(track, dict)
            }
            target_id = int(row.get("target_object_id") or 0)
            target_name = str(row.get("target_object_name") or "")
            node_index = row.get("clump_node_index")
            label = f"Part 0x{target_id:X}: {target_name or '<unnamed>'}"
            if node_index is not None:
                label += f" — clump node {node_index}"
            part_nodes.append(
                base._node(
                    label,
                    "puppet_part",
                    {
                        "target_object_id": target_id,
                        "target_object_name": target_name,
                        "parent_object_id": row.get("parent_object_id"),
                        "parent_object_name": row.get("parent_object_name"),
                        "clump_id": row.get("clump_id"),
                        "clump_name": row.get("clump_name"),
                        "clump_node_index": node_index,
                        "model_id": row.get("model_id"),
                        "model_name": row.get("model_name"),
                        "external_id": row.get("external_id"),
                        "external_name": row.get("external_name"),
                        "tracks": track_details,
                        "rotation_storage": row.get("rotation_storage"),
                        "rotation_pipeline": row.get("rotation_pipeline"),
                    },
                )
            )
        animations.append(
            base._node(
                f"Animation 0x{animation_id:X}: {animation_name} — {len(part_nodes)} controlled parts",
                "puppetry_animation",
                {
                    "animation_id": animation_id,
                    "animation_name": animation_name,
                    "controlled_parts": len(part_nodes),
                    "rotation_pipeline": pose_v6.ROTATION_PIPELINE,
                    "quaternion_used": False,
                },
                part_nodes,
            )
        )
    return base._node(
        f"Puppetry ({len(catalog)} controller bindings / {len(animations)} animations)",
        "group",
        {
            "controller_bindings": len(catalog),
            "controlled_objects": len(
                {
                    int(row["target_object_id"])
                    for row in catalog
                    if isinstance(row.get("target_object_id"), int)
                }
            ),
            "rotation_pipeline": pose_v6.ROTATION_PIPELINE,
            "quaternion_used": False,
        },
        animations,
    )


def inspect_ccsf_contents(path) -> dict[str, Any]:
    model = _BASE_INSPECT(path)
    parsed = pose_v6.load_pose_source(path)
    puppetry = _puppetry_group(parsed)
    groups = list(model.get("groups") or [])
    # Keep scene/clump structure first, then show the animation-to-part bindings.
    groups.insert(1 if groups else 0, puppetry)
    model["groups"] = groups
    catalog = puppetry_v1.controller_catalog(parsed)
    summary = dict(model.get("summary") or {})
    summary.update(
        {
            "puppetry_bindings": len(catalog),
            "controlled_objects": len(
                {
                    int(row["target_object_id"])
                    for row in catalog
                    if isinstance(row.get("target_object_id"), int)
                }
            ),
            "rotation_pipeline": pose_v6.ROTATION_PIPELINE,
            "rotation_quaternion_used": False,
        }
    )
    model["summary"] = summary
    model["puppetry"] = catalog
    return model


def install() -> None:
    base.pose_v2 = pose_v6
    base.inspect_ccsf_contents = inspect_ccsf_contents


install()

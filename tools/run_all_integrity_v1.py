#!/usr/bin/env python3
"""Runtime contract checks for Fragmenter's patched RUN ALL pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from project_workspace_v1 import FragmenterProjectV1
from run_all_executor_v8 import build_run_all_actions_v8
from run_all_plan_v2 import build_run_all_plan_v2

REQUIRED_ORDER = (
    "project_check",
    "workspace_layout",
    "iso_index",
    "ccsf_extract",
    "asset_library",
    "extraction_audit",
    "visual_catalogs",
    "sound_extract",
    "sound_decode",
    "snddata_samples",
    "snddata_mixer",
    "server_index",
    "server_saves",
    "memory_card",
    "refresh",
    "public_lists",
)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen and value not in output:
            output.append(value)
        seen.add(value)
    return output


def validate_run_all_contract(project: FragmenterProjectV1) -> dict[str, Any]:
    """Compare the visible plan with the executable actions and workspace policy."""
    plan = build_run_all_plan_v2(project)
    actions = build_run_all_actions_v8(project)
    plan_keys = [str(row.get("key") or "") for row in plan.get("stages") or []]
    action_keys = [str(row.key) for row in actions]
    workspace = Path(project.workspace_dir).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for label, values in (("plan", plan_keys), ("executor", action_keys)):
        duplicate = _duplicates(values)
        if duplicate:
            errors.append(f"Duplicate {label} stage keys: {', '.join(duplicate)}")

    if plan_keys != action_keys:
        errors.append(
            "Visible plan and executable action order differ. "
            f"Plan={plan_keys}; executor={action_keys}"
        )

    missing = [key for key in REQUIRED_ORDER if key not in action_keys]
    if missing:
        errors.append("Required RUN ALL stages are missing: " + ", ".join(missing))
    elif tuple(action_keys) != REQUIRED_ORDER:
        warnings.append("RUN ALL contains the required stages but the canonical order changed.")

    escaped_outputs: list[str] = []
    for action in actions:
        for raw in action.outputs:
            resolved = Path(raw).expanduser().resolve()
            if resolved != workspace and workspace not in resolved.parents:
                escaped_outputs.append(f"{action.key}: {resolved}")
    if escaped_outputs:
        errors.append("RUN ALL outputs escape the project workspace: " + "; ".join(escaped_outputs))

    if action_keys and action_keys[-1] != "public_lists":
        errors.append("Prepare Public Lists must be the final RUN ALL action.")

    return {
        "version": 1,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "plan_keys": plan_keys,
        "action_keys": action_keys,
        "workspace": str(workspace),
        "stage_count": len(action_keys),
        "final_stage": action_keys[-1] if action_keys else "",
        "writes_game_data": False,
    }


if __name__ == "__main__":
    raise SystemExit("Use validate_run_all_contract(project) from the Fragmenter GUI or tests.")

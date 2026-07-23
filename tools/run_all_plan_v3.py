#!/usr/bin/env python3
"""Extend the canonical RUN ALL plan with final public-list preparation."""
from __future__ import annotations

from pathlib import Path

import run_all_plan_v2 as v2
from project_sound_v1 import sound_reports_root
from project_workspace_v1 import FragmenterProjectV1
from public_library_cache_v1 import cache_paths

_ORIGINAL_STAGES = v2.stages_for_project
_INSTALLED = False


def stages_for_project_v3(project: FragmenterProjectV1) -> list[v2.RunStageV2]:
    stages = list(_ORIGINAL_STAGES(project))
    paths = cache_paths(project)
    workspace = Path(project.workspace_dir).expanduser()
    stage = v2.RunStageV2(
        "public_lists",
        "Prepare Public Lists",
        "Precompute the 3D asset browser, playable Audio Library, and sortable SNDDATA sequence list after the canonical catalogs are refreshed.",
        (
            str(workspace / "reports" / "asset_library.json"),
            str(sound_reports_root(project) / "sound_library.json"),
            str(sound_reports_root(project) / "snddata_music_system_v5.json"),
        ),
        tuple(str(path) for path in paths.values()),
        (
            "The evidence catalogs are refreshed. I am preparing the visible lists now so the first tab click stays a tab click.",
            "Sorting the 3D assets, playable WAVs, and SNDDATA sequence evidence into their final workspaces.",
        ),
    )
    refresh_index = next((index for index, row in enumerate(stages) if row.key == "refresh"), len(stages) - 1)
    stages.insert(min(len(stages), refresh_index + 1), stage)
    return stages


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    v2.stages_for_project = stages_for_project_v3
    _INSTALLED = True

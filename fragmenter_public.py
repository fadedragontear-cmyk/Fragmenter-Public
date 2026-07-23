#!/usr/bin/env python3
"""Launch Fragmenter 1.0."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# Install runtime policy patches before the current GUI binds imported functions.
from audio_library_alias_patch_v1 import install as install_audio_alias_policy  # noqa: E402
from snddata_strict_routing_patch_v1 import install as install_strict_snddata_routing  # noqa: E402

install_audio_alias_policy()
install_strict_snddata_routing()

from audio_mixer_cache_safety_v1 import install as install_audio_cache_safety  # noqa: E402
from run_all_executor_v9 import install as install_run_all_executor_v9  # noqa: E402
from run_all_plan_v3 import install as install_run_all_plan_v3  # noqa: E402
from snddata_event_window_patch_v1 import install as install_event_window_patch  # noqa: E402
from snddata_sample_generation_patch_v1 import (  # noqa: E402
    install as install_sample_generation_patch,
)
from tellipatch_resource_v122 import install as install_tellipatch_resource  # noqa: E402

install_audio_cache_safety()
install_event_window_patch()
install_sample_generation_patch()
install_run_all_plan_v3()
install_run_all_executor_v9()

from run_all_cancellation_v1 import install as install_run_all_cancellation  # noqa: E402

install_run_all_cancellation()
install_tellipatch_resource()

import fragmenter_visual_runtime_v6  # noqa: E402,F401
import visual_asset_annotations_v3  # noqa: E402,F401
import visual_asset_annotations_v4  # noqa: E402,F401
from fragmenter_release_experience_v1 import (  # noqa: E402
    install as install_release_experience,
)

install_release_experience()

from fragmenter_public_gui_v127 import main  # noqa: E402
from run_all_cancel_ui_v1 import install as install_run_all_cancel_ui  # noqa: E402

install_run_all_cancel_ui()


if __name__ == "__main__":
    raise SystemExit(main())

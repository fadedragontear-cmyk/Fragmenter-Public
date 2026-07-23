#!/usr/bin/env python3
"""V106: restored Run All progress and a dormant shared-canvas Gremlin scene."""
from __future__ import annotations

from fragmenter_gremlin_scene_v106 import FragmenterGremlinSceneMixinV106
from fragmenter_public_gui_v105 import PublicFragmenterAppV105


class PublicFragmenterAppV106(
    FragmenterGremlinSceneMixinV106,
    PublicFragmenterAppV105,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Gremlin Scene Repair V106")


def main() -> int:
    app = PublicFragmenterAppV106()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

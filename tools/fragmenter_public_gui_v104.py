#!/usr/bin/env python3
"""V104: prepared RUN ALL lists and a focused audio research workspace."""
from __future__ import annotations

from fragmenter_audio_workspace_v104 import FragmenterAudioWorkspaceMixinV104
from fragmenter_public_gui_v103 import PublicFragmenterAppV103


class PublicFragmenterAppV104(
    FragmenterAudioWorkspaceMixinV104,
    PublicFragmenterAppV103,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Run All Audio Research Workspace V104")


def main() -> int:
    app = PublicFragmenterAppV104()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

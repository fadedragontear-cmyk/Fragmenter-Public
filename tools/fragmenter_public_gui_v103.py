#!/usr/bin/env python3
"""V103: egg-first Dragonegg startup and repaired Gremlin runtime."""
from __future__ import annotations

from celdra_dragonegg_chaos_v103 import DragoneggChaosMixinV103
from celdra_dragonegg_speech_v103 import DragoneggSpeechMixinV103
from celdra_dragonegg_stable_v103 import DragoneggStableMixinV103
from fragmenter_public_gui_v102 import PublicFragmenterAppV102


class PublicFragmenterAppV103(
    DragoneggStableMixinV103,
    DragoneggChaosMixinV103,
    DragoneggSpeechMixinV103,
    PublicFragmenterAppV102,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Operation Dragonegg Gremlin Runtime V103")


def main() -> int:
    app = PublicFragmenterAppV103()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

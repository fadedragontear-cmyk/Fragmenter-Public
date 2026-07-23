#!/usr/bin/env python3
"""V115: runtime audio evidence, layer sampler, and conservative layout repair."""
from __future__ import annotations

from fragmenter_public_gui_v114 import PublicFragmenterAppV114
from fragmenter_runtime_audio_v115 import FragmenterRuntimeAudioMixinV115


class PublicFragmenterAppV115(
    FragmenterRuntimeAudioMixinV115,
    PublicFragmenterAppV114,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Runtime Audio Research V115")


def main() -> int:
    app = PublicFragmenterAppV115()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

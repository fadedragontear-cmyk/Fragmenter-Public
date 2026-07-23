#!/usr/bin/env python3
"""V111: quick sample classification, Celdra audio mode, and boundary policy v3."""
from __future__ import annotations

from fragmenter_audio_assist_v111 import FragmenterAudioAssistMixinV111
from fragmenter_public_gui_v110 import PublicFragmenterAppV110


class PublicFragmenterAppV111(
    FragmenterAudioAssistMixinV111,
    PublicFragmenterAppV110,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Audio Analyst V111")


def main() -> int:
    app = PublicFragmenterAppV111()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

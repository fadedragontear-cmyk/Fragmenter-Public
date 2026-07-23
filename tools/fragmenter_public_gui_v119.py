#!/usr/bin/env python3
"""V119 experimental native English ISO builder and PCSX2 setup."""
from __future__ import annotations

from fragmenter_public_gui_v118 import PublicFragmenterAppV118
from fragmenter_tellipatch_v119 import FragmenterTellipatchMixinV119


class PublicFragmenterAppV119(
    FragmenterTellipatchMixinV119,
    PublicFragmenterAppV118,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 - English ISO + Setup Experimental V119")


def main() -> int:
    app = PublicFragmenterAppV119()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

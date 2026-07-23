#!/usr/bin/env python3
"""V118 experimental PCSX2 setup and ISO patch builder."""
from __future__ import annotations

from fragmenter_pcsx2_helper_v118 import FragmenterPcsx2HelperMixinV118
from fragmenter_public_gui_v117 import PublicFragmenterAppV117


class PublicFragmenterAppV118(
    FragmenterPcsx2HelperMixinV118,
    PublicFragmenterAppV117,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 - Setup + ISO Patcher Experimental V118")


def main() -> int:
    app = PublicFragmenterAppV118()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

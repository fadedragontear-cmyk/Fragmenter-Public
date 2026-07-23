#!/usr/bin/env python3
"""V117 experimental integrated ISO patch builder."""
from __future__ import annotations

from fragmenter_iso_builder_v117 import FragmenterIsoBuilderMixinV117
from fragmenter_public_gui_v116 import PublicFragmenterAppV116


class PublicFragmenterAppV117(
    FragmenterIsoBuilderMixinV117,
    PublicFragmenterAppV116,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 - ISO Patcher Experimental V117")


def main() -> int:
    app = PublicFragmenterAppV117()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

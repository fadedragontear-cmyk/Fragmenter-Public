#!/usr/bin/env python3
"""V114: grouped audio library, strict mixer guidance, and RUN ALL geometry."""
from __future__ import annotations

from fragmenter_public_gui_v113 import PublicFragmenterAppV113
from fragmenter_usability_v114 import FragmenterUsabilityMixinV114


class PublicFragmenterAppV114(
    FragmenterUsabilityMixinV114,
    PublicFragmenterAppV113,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Consolidated Workspace V114")


def main() -> int:
    app = PublicFragmenterAppV114()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

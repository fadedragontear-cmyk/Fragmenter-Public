#!/usr/bin/env python3
"""V116: public-release audio surface and Gremlin-stage visibility."""
from __future__ import annotations

from fragmenter_public_gui_v115 import PublicFragmenterAppV115
from fragmenter_public_surface_v116 import FragmenterPublicSurfaceMixinV116


class PublicFragmenterAppV116(
    FragmenterPublicSurfaceMixinV116,
    PublicFragmenterAppV115,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 - Public Release Candidate V116")


def main() -> int:
    app = PublicFragmenterAppV116()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

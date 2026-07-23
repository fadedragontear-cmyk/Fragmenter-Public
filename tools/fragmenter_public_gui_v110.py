#!/usr/bin/env python3
"""V110: final Celdra and Gremlin presentation polish."""
from __future__ import annotations

from fragmenter_celdra_cleanup_v110 import FragmenterCeldraCleanupMixinV110
from fragmenter_celdra_geometry_v110 import FragmenterCeldraGeometryMixinV110
from fragmenter_celdra_polish_v110 import FragmenterCeldraPolishMixinV110
from fragmenter_public_gui_v109 import PublicFragmenterAppV109


class PublicFragmenterAppV110(
    FragmenterCeldraCleanupMixinV110,
    FragmenterCeldraGeometryMixinV110,
    FragmenterCeldraPolishMixinV110,
    PublicFragmenterAppV109,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Celdra Presentation Polish V110")


def main() -> int:
    app = PublicFragmenterAppV110()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

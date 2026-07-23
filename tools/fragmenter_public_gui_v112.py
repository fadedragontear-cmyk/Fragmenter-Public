#!/usr/bin/env python3
"""V112: true fresh-install Gremlin progression and completed Celdra gallery."""
from __future__ import annotations

from celdra_gremlin_gallery_v112 import materialize_gremlin_gallery_v112
from fragmenter_gremlin_acceptance_v112 import FragmenterGremlinAcceptanceMixinV112
from fragmenter_public_gui_v111 import PublicFragmenterAppV111

materialize_gremlin_gallery_v112()


class PublicFragmenterAppV112(
    FragmenterGremlinAcceptanceMixinV112,
    PublicFragmenterAppV111,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Gremlin Acceptance Repair V112")


def main() -> int:
    app = PublicFragmenterAppV112()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

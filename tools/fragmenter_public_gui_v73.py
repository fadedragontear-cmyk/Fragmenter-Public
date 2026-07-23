#!/usr/bin/env python3
"""V73: keep post-Shy poses aligned with the studio's editable endpoint."""
from __future__ import annotations

from fragmenter_public_gui_v72 import PublicFragmenterAppV72


class PublicFragmenterAppV73(PublicFragmenterAppV72):
    """Carry the manual Shy end position into Confused and Wink callbacks."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP — Celdra Timeline Studio")

    def _begin_shy_reveal_v64(self) -> None:
        self._celdra_shy_rest_offset_v64 = self._shy_value_v72(
            self._celdra_shy_end_y_v72,
            0,
        )
        super()._begin_shy_reveal_v64()


def main() -> int:
    app = PublicFragmenterAppV73()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

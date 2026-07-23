#!/usr/bin/env python3
"""V108: visible Run All progress and restored Gremlin breakout presentation."""
from __future__ import annotations

from fragmenter_public_gui_v107 import PublicFragmenterAppV107
from fragmenter_sequence_repair_v108 import FragmenterSequenceRepairMixinV108


class PublicFragmenterAppV108(
    FragmenterSequenceRepairMixinV108,
    PublicFragmenterAppV107,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Run All Presentation Repair V108")


def main() -> int:
    app = PublicFragmenterAppV108()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

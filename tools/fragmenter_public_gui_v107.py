#!/usr/bin/env python3
"""V107: visible Run All progress, restored Gremlin introductions, and path repair."""
from __future__ import annotations

from fragmenter_acceptance_repair_v107 import FragmenterAcceptanceRepairMixinV107
from fragmenter_public_gui_v106 import PublicFragmenterAppV106


class PublicFragmenterAppV107(
    FragmenterAcceptanceRepairMixinV107,
    PublicFragmenterAppV106,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Acceptance Repair V107")


def main() -> int:
    app = PublicFragmenterAppV107()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

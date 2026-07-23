#!/usr/bin/env python3
"""V105: audited RUN ALL, prepared sequence lists, and resilient Celdra theatre."""
from __future__ import annotations

from fragmenter_public_gui_v104 import PublicFragmenterAppV104
from fragmenter_run_all_polish_v105 import FragmenterRunAllPolishMixinV105


class PublicFragmenterAppV105(
    FragmenterRunAllPolishMixinV105,
    PublicFragmenterAppV104,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Run All Director V105")


def main() -> int:
    app = PublicFragmenterAppV105()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

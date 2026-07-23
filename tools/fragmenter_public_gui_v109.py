#!/usr/bin/env python3
"""V109: collectible Gremlin encounters and the 9/9 Celdra unlock."""
from __future__ import annotations

from fragmenter_collection_migration_v109 import FragmenterCollectionMigrationMixinV109
from fragmenter_stable_status_v109 import FragmenterStableStatusMixinV109
from fragmenter_collection_gate_v109 import FragmenterCollectionGateMixinV109
from fragmenter_collection_resume_v109 import FragmenterCollectionResumeMixinV109
from fragmenter_collection_runtime_v109 import FragmenterGremlinCollectionMixinV109
from fragmenter_public_gui_v108 import PublicFragmenterAppV108


class PublicFragmenterAppV109(
    FragmenterCollectionMigrationMixinV109,
    FragmenterStableStatusMixinV109,
    FragmenterCollectionGateMixinV109,
    FragmenterCollectionResumeMixinV109,
    FragmenterGremlinCollectionMixinV109,
    PublicFragmenterAppV108,
):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fragmenter 1.0 WIP - Gremlin Collection Runtime V109")


def main() -> int:
    app = PublicFragmenterAppV109()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

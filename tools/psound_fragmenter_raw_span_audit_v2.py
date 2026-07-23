#!/usr/bin/env python3
"""Raw-span audit v2 with monotonic-offset filtering for PCM loop candidates."""
from __future__ import annotations

from typing import Any

import psound_fragmenter_raw_span_audit_v1 as v1

_ORIGINAL_LOOP_CANDIDATES = v1._loop_candidates


def _filtered_loop_candidates(
    pcm_payload: dict[str, Any] | None,
    psound_sizes: dict[int, int],
    fragmenter_rows: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = _ORIGINAL_LOOP_CANDIDATES(pcm_payload, psound_sizes, fragmenter_rows)
    # Fragmenter has slightly more catalog rows than PSound, so a valid monotonic
    # identity can drift forward by that difference. Large negative offsets are
    # repeated-silence/prefix collisions, not credible sample identities.
    maximum_offset = max(0, len(fragmenter_rows) - len(psound_sizes)) + 4
    return [
        row
        for row in candidates
        if 0
        <= int(row["fragmenter_flat_index"]) - int(row["psound_sequence_number"])
        <= maximum_offset
    ]


v1._loop_candidates = _filtered_loop_candidates

audit = v1.audit
main = v1.main


if __name__ == "__main__":
    raise SystemExit(main())

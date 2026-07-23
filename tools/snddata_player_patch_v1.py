#!/usr/bin/env python3
"""Correct Program selection for sparse parsed SCEIProg tables.

The base renderer historically treated a requested Program number as a list position.
That only works when parsed Program indexes are contiguous and start at zero. Fragment
resources may expose sparse Program tables, so a note requesting Program 15 must select
the row whose parsed ``index`` is 15, not ``programs[15 % len(programs)]``.
"""
from __future__ import annotations

from typing import Any, Sequence

import snddata_player as player

_INSTALLED = False


def _value(value: Any, default: Any = None) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return default if value is None else value


def _optional_int(value: Any) -> int | None:
    value = _value(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def choose_program_by_index(
    event: dict[str, Any],
    programs: Sequence[dict[str, Any]],
    mode: str = "auto",
    manual: dict[Any, int] | None = None,
) -> dict[str, Any] | None:
    """Resolve a requested Program against parsed Program indexes first."""
    if not programs:
        return None
    channel = event.get("channel")
    track = event.get("track_index", event.get("track"))
    key: Any = channel if channel is not None else track
    if mode in {"manual", "Manual"} and manual:
        requested = _optional_int(manual.get(key, manual.get(str(key), 0)))
    elif mode in {"track_index", "Track Index → Program Index"}:
        requested = _optional_int(track) or 0
    elif mode in {"channel", "Channel → Program Index"}:
        requested = _optional_int(channel) or 0
    else:
        requested = _optional_int(event.get("program_index"))
        if requested is None:
            requested = _optional_int(event.get("program"))
        if requested is None:
            requested = _optional_int(channel) or 0

    by_index: dict[int, dict[str, Any]] = {}
    explicit_indexes = False
    for position, program in enumerate(programs):
        index = _optional_int(program.get("index"))
        if index is not None:
            explicit_indexes = True
            by_index[index] = program
        else:
            by_index.setdefault(position, program)
    if requested in by_index:
        return by_index[requested]

    # Positional wrapping remains only for old fixtures without parsed indexes.
    if not explicit_indexes:
        return programs[int(requested) % len(programs)]
    return None


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    player.choose_program = choose_program_by_index
    _INSTALLED = True


if __name__ == "__main__":
    raise SystemExit("Installed by the Fragmenter public launcher.")

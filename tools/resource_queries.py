#!/usr/bin/env python3
from __future__ import annotations

import re


def derive_family_search_terms(stem: str, max_suggestions: int = 10) -> list[str]:
    raw = (stem or "").strip().lower()
    if not raw:
        return []
    normalized = re.sub(r"[^a-z0-9]+", "", raw)
    if not normalized:
        return []

    suggestions: list[str] = []

    def _add(value: str):
        value = (value or "").strip().lower()
        if not value or value in suggestions:
            return
        if len(suggestions) < max(1, int(max_suggestions)):
            suggestions.append(value)

    _add(normalized)

    prefix_match = re.match(r"^([a-z]+\d+)", normalized)
    if prefix_match:
        _add(prefix_match.group(1))

    trailing_alpha = re.search(r"([a-z]+)$", normalized)
    if trailing_alpha:
        _add(trailing_alpha.group(1))

    sr_match = re.match(r"^sr(\d+)", normalized)
    if sr_match:
        _add(f"s/r/{sr_match.group(1)}")

    return suggestions[: max(1, int(max_suggestions))]

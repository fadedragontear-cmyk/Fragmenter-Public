#!/usr/bin/env python3
"""Make the Celdra tab unlock exactly at 9/9 and open the Discord invite directly."""
from __future__ import annotations

import webbrowser
from tkinter import messagebox

from celdra_gremlin_collection_v109 import (
    SERENIAL_DISCORD_INVITE_V109,
    SERENIAL_DISCORD_REDIRECT_V109,
)
from celdra_gremlin_memory_v2 import collection_complete


class FragmenterCollectionGateMixinV109:
    """Reveal the tab at 9/9 while leaving reward-dialogue persistence independent."""

    def _schedule_collection_reward_v101(self) -> None:
        if collection_complete(self._celdra_gremlin_memory_v99):
            self._sync_celdra_tab_v109()
        super()._schedule_collection_reward_v101()

    def _sync_celdra_tab_v109(self) -> None:
        if not collection_complete(self._celdra_gremlin_memory_v99):
            super()._sync_celdra_tab_v109()
            return
        # The tab builder originally waited for the reward dialogue to finish.
        # Temporarily satisfy that presentation-only gate so 9/9 is authoritative;
        # do not save or otherwise mark the reward dialogue as seen here.
        original = bool(
            self._celdra_gremlin_memory_v99.get("collection_reward_seen")
        )
        self._celdra_gremlin_memory_v99["collection_reward_seen"] = True
        try:
            super()._sync_celdra_tab_v109()
        finally:
            self._celdra_gremlin_memory_v99["collection_reward_seen"] = original

    def _open_serenial_discord_v109(self) -> None:
        """Open the actual Discord invite first; use the maintained site as fallback."""
        opened = False
        try:
            opened = bool(webbrowser.open(SERENIAL_DISCORD_INVITE_V109, new=2))
            if not opened:
                opened = bool(
                    webbrowser.open(SERENIAL_DISCORD_REDIRECT_V109, new=2)
                )
        except Exception:
            opened = False
        if opened:
            status = getattr(self, "_celdra_unlock_status_v109", None)
            if status is not None:
                status.set("Serenial Tavern Discord opened in your default browser.")
            return
        messagebox.showerror(
            "Open Serenial Tavern",
            "Fragmenter could not open the browser. Visit https://www.serenial.ca manually.",
        )

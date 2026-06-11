"""Sliding-window mass join detection."""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict


class MassJoinTracker:
    """Track join rates per guild to detect raid waves."""

    def __init__(self) -> None:
        self._joins: Dict[int, Deque[float]] = {}

    def record_join(self, guild_id: int) -> int:
        """Record a join and return the current count within the window."""
        now = time.time()
        if guild_id not in self._joins:
            self._joins[guild_id] = deque()
        queue = self._joins[guild_id]
        queue.append(now)
        return len(queue)

    def prune_and_count(self, guild_id: int, window_seconds: int) -> int:
        """Remove expired timestamps and return count in the active window."""
        now = time.time()
        queue = self._joins.setdefault(guild_id, deque())
        while queue and now - queue[0] > window_seconds:
            queue.popleft()
        return len(queue)

    def is_mass_join(self, guild_id: int, threshold: int, window_seconds: int) -> bool:
        return self.prune_and_count(guild_id, window_seconds) >= threshold

    def effective_threshold(self, base_threshold: int, mass_join_active: bool) -> int:
        """During mass joins, require a higher score to reduce false positives."""
        if mass_join_active:
            return base_threshold + 1
        return base_threshold

"""
OXY Keys — Thread-safe multi-provider API key manager with rotation and cooldown.

Three strategies:
  - sequential: cycle through keys in order (A→B→C→A→B→C)
  - random:     pick a random active key each time
  - least-used: pick the active key used least so far

Features:
  - Strategy enum for type safety and validation
  - Thread-safe rotation using threading.Lock
  - Reactive rate-limit (HTTP 429) cooldown tracking
"""

from __future__ import annotations

import random
import threading
import time
from collections import Counter
from enum import Enum


class Strategy(str, Enum):
    SEQUENTIAL = "sequential"
    RANDOM = "random"
    LEAST_USED = "least-used"


class KeyManager:
    """Thread-safe API key rotation manager with rate-limit cooldown."""

    def __init__(self, keys: list[str], strategy: str | Strategy = Strategy.SEQUENTIAL):
        self._lock = threading.Lock()
        self.keys = [k for k in keys if k.strip()]
        self.strategy = Strategy(strategy) if isinstance(strategy, str) else strategy
        self._index = 0
        self._usage: Counter[str] = Counter()
        self._cooldowns: dict[str, float] = {}  # key -> cooldown expiration timestamp

    @property
    def count(self) -> int:
        with self._lock:
            return len(self.keys)

    @property
    def is_active(self) -> bool:
        with self._lock:
            return len(self.keys) > 1

    def mark_cooldown(self, key: str, cooldown_seconds: float = 60.0):
        """Mark an API key as rate-limited until cooldown_seconds elapsed."""
        with self._lock:
            self._cooldowns[key] = time.time() + cooldown_seconds

    def is_cooling_down(self, key: str) -> bool:
        """Return True if the key is currently cooling down from a rate limit."""
        with self._lock:
            exp = self._cooldowns.get(key, 0.0)
            return time.time() < exp

    def get_available_keys(self) -> list[str]:
        """Return list of keys currently not in cooldown."""
        now = time.time()
        return [k for k in self.keys if now >= self._cooldowns.get(k, 0.0)]

    def next_key(self) -> str:
        """Get the next active API key, skipping keys in active cooldown."""
        with self._lock:
            if not self.keys:
                raise ValueError("No API keys available")

            now = time.time()
            # Clean up expired cooldowns
            for k in list(self._cooldowns.keys()):
                if now >= self._cooldowns[k]:
                    del self._cooldowns[k]

            available = [k for k in self.keys if k not in self._cooldowns]

            # If all keys are in cooldown, pick the one expiring earliest
            if not available:
                candidate_pool = sorted(self.keys, key=lambda k: self._cooldowns.get(k, 0.0))
                key = candidate_pool[0]
            else:
                if len(available) == 1:
                    key = available[0]
                elif self.strategy == Strategy.RANDOM:
                    key = random.choice(available)
                elif self.strategy == Strategy.LEAST_USED:
                    key = min(available, key=lambda k: self._usage[k])
                else:  # sequential
                    # Pick next available key matching or after current index
                    key = available[self._index % len(available)]
                    self._index += 1

            self._usage[key] += 1
            return key

    def add_key(self, key: str):
        """Add a key to the pool."""
        key = key.strip()
        if not key:
            return
        with self._lock:
            if key not in self.keys:
                self.keys.append(key)

    def remove_key(self, index: int) -> bool:
        """Remove a key by index. Returns True if removed."""
        with self._lock:
            if 0 <= index < len(self.keys):
                removed = self.keys.pop(index)
                self._cooldowns.pop(removed, None)
                return True
            return False

    def stats(self) -> list[dict]:
        """Return usage and cooldown stats per key."""
        now = time.time()
        with self._lock:
            res = []
            for i, k in enumerate(self.keys):
                cooldown_remaining = max(0.0, self._cooldowns.get(k, 0.0) - now)
                res.append({
                    "index": i,
                    "key_preview": k[:6] + "..." + k[-4:] if len(k) > 14 else "****",
                    "uses": self._usage[k],
                    "cooldown_remaining": round(cooldown_remaining, 1),
                    "is_cooldown": cooldown_remaining > 0,
                })
            return res

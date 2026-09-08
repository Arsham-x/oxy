"""
OXY Keys — Round-robin API key manager.

Three strategies:
  - sequential: cycle through keys in order (A→B→C→A→B→C)
  - random:     pick a random key each time
  - least-used: pick the key used least so far
"""

from __future__ import annotations

import random
from collections import Counter


class KeyManager:
    """Manages multiple API keys with rotation strategies."""

    def __init__(self, keys: list[str], strategy: str = "sequential"):
        self.keys = [k for k in keys if k.strip()]
        self.strategy = strategy
        self._index = 0
        self._usage: Counter[str] = Counter()

    @property
    def count(self) -> int:
        return len(self.keys)

    @property
    def is_active(self) -> bool:
        return self.count > 1

    def next_key(self) -> str:
        """Get the next API key based on the active strategy."""
        if not self.keys:
            raise ValueError("No API keys available")

        if self.count == 1:
            key = self.keys[0]
        elif self.strategy == "random":
            key = random.choice(self.keys)
        elif self.strategy == "least-used":
            key = min(self.keys, key=lambda k: self._usage[k])
        else:  # sequential
            key = self.keys[self._index % self.count]
            self._index += 1

        self._usage[key] += 1
        return key

    def add_key(self, key: str):
        """Add a key to the pool."""
        key = key.strip()
        if key and key not in self.keys:
            self.keys.append(key)

    def remove_key(self, index: int) -> bool:
        """Remove a key by index. Returns True if removed."""
        if 0 <= index < len(self.keys):
            self.keys.pop(index)
            return True
        return False

    def stats(self) -> list[dict]:
        """Return usage stats per key."""
        return [
            {
                "index": i,
                "key_preview": k[:6] + "..." + k[-4:] if len(k) > 14 else "****",
                "uses": self._usage[k],
            }
            for i, k in enumerate(self.keys)
        ]

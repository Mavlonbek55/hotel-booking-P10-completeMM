"""Redis cache-aside implementation for free-room searches."""
from __future__ import annotations

import json


class AvailabilityCache:
    def __init__(self, client, ttl_seconds: int = 30) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds

    def key(self, check_in: str, check_out: str) -> str:
        self.client.set("availability:version", "1", nx=True)
        version = self.client.get("availability:version")
        if isinstance(version, bytes):
            version = version.decode()
        return f"availability:v{version}:{check_in}:{check_out}"

    def get(self, key: str):
        value = self.client.get(key)
        return None if value is None else json.loads(value)

    def set(self, key: str, value) -> None:
        self.client.setex(key, self.ttl_seconds, json.dumps(value))

    def invalidate(self) -> None:
        self.client.incr("availability:version")

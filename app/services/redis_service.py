from __future__ import annotations

import json
from typing import Any, Optional

try:
    import redis.asyncio as redis_async
except Exception:  # pragma: no cover - optional dependency
    redis_async = None


class RedisService:
    def __init__(self, url: str, enabled: bool = False):
        self.url = url
        self.enabled = enabled
        self.client = None
        self._last_error = None

    async def connect(self):
        if not self.enabled or redis_async is None:
            return None
        if self.client is not None:
            return self.client
        try:
            self.client = redis_async.from_url(self.url, decode_responses=True)
            await self.client.ping()
        except Exception as exc:
            self._last_error = exc
            await self.close()
        return self.client

    def status(self):
        if not self.enabled:
            return "disabled"
        if self.client is not None:
            return "connected"
        if self._last_error is not None:
            return "unavailable"
        return "disconnected"

    async def close(self):
        if self.client is not None:
            await self.client.close()
        self.client = None

    async def cache_json(self, key: str, payload: Any, ttl_seconds: Optional[int] = None):
        client = await self.connect()
        if client is None:
            return False
        value = json.dumps(payload, ensure_ascii=False)
        if ttl_seconds:
            await client.set(key, value, ex=ttl_seconds)
        else:
            await client.set(key, value)
        return True

    async def get_json(self, key: str):
        client = await self.connect()
        if client is None:
            return None
        raw = await client.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return raw

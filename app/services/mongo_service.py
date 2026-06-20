from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:  # pragma: no cover - optional dependency
    AsyncIOMotorClient = None


class MongoService:
    def __init__(self, uri: str, database_name: str, enabled: bool = False):
        self.uri = uri
        self.database_name = database_name
        self.enabled = enabled
        self.client = None
        self.db = None
        self._last_error = None

    async def connect(self):
        if not self.enabled or AsyncIOMotorClient is None:
            return None
        if self.db is not None:
            return self.db
        try:
            self.client = AsyncIOMotorClient(self.uri, serverSelectionTimeoutMS=2000)
            await self.client.admin.command("ping")
            self.db = self.client[self.database_name]
        except Exception as exc:
            self._last_error = exc
            await self.close()
        return self.db

    def status(self):
        if not self.enabled:
            return "disabled"
        if self.db is not None:
            return "connected"
        if self._last_error is not None:
            return "unavailable"
        return "disconnected"

    async def close(self):
        if self.client is not None:
            self.client.close()
        self.client = None
        self.db = None

    async def replace_recipes(self, recipes: Iterable[Any], collection_name: str = "recipes"):
        database = await self.connect()
        if database is None:
            return 0
        collection = database[collection_name]
        await collection.delete_many({})
        payload = []
        for recipe in recipes:
            if hasattr(recipe, "model_dump"):
                payload.append(recipe.model_dump(mode="json"))
            elif isinstance(recipe, dict):
                payload.append(dict(recipe))
        if payload:
            await collection.insert_many(payload)
        return len(payload)

    async def get_recipes(self, collection_name: str = "recipes"):
        database = await self.connect()
        if database is None:
            return []
        documents = []
        async for document in database[collection_name].find({}):
            documents.append(document)
        return documents

import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

_client: AsyncIOMotorClient | None = None


def init_client() -> None:
    global _client
    uri = os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true")
    _client = AsyncIOMotorClient(uri)


def close_client() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


def get_recipes() -> AsyncIOMotorCollection:
    db_name = os.getenv("MONGO_DB", "potatohub")
    return _client[db_name]["recipes"]


def doc_to_recipe(doc: dict) -> dict:
    stats = doc.get("stats") or {"views": 0, "saved": 0}
    views = int(stats.get("views") or 0)
    saved = int(stats.get("saved") or 0)
    score = round(views * 0.5 + saved * 5, 2)
    prep = int(doc.get("prep_time_min") or 0)
    cook = int(doc.get("cook_time_min") or 0)
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title") or "",
        "description": doc.get("description") or "",
        "category": doc.get("category_potato") or "GENERAL",
        "difficulty": doc.get("difficulty") or "",
        "cooking_time": prep + cook,
        "ingredients": doc.get("ingredients") or [],
        "instructions": doc.get("instructions") or [],
        "image_url": doc.get("image_url"),
        "source_name": doc.get("source") or "cookpad_pe",
        "source_url": doc.get("source_url") or "",
        "tags": doc.get("tags") or [],
        "stats": {"views": views, "saved": saved},
        "score": score,
        "created_at": doc.get("created_at") or doc.get("scraped_at"),
        "updated_at": doc.get("updated_at"),
    }

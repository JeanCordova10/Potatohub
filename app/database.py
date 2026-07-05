from __future__ import annotations

import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import TEXT, ASCENDING, DESCENDING, UpdateOne

from app.security import hash_password, normalize_email
from app.semantic_search import (
    SEMANTIC_VERSION,
    build_recipe_search_fields,
    canonicalize_category,
    canonicalize_difficulty,
    clean_human_text,
)

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


def get_db() -> AsyncIOMotorDatabase:
    db_name = os.getenv("MONGO_DB", "potatohub")
    return _client[db_name]


def get_recipes() -> AsyncIOMotorCollection:
    return get_db()["recipes"]


def get_users() -> AsyncIOMotorCollection:
    return get_db()["users"]


def get_user_recipe_states() -> AsyncIOMotorCollection:
    return get_db()["user_recipe_states"]


def get_user_events() -> AsyncIOMotorCollection:
    return get_db()["user_events"]


async def _ensure_index(
    collection: AsyncIOMotorCollection,
    keys: list[tuple[str, int]],
    *,
    unique: bool = False,
) -> None:
    target_key = tuple(keys)
    existing = await collection.index_information()
    for spec in existing.values():
        current_key = tuple(spec.get("key") or [])
        if current_key != target_key:
            continue
        if unique and not bool(spec.get("unique")):
            continue
        return
    await collection.create_index(keys, unique=unique)


async def ensure_indexes() -> None:
    await _ensure_index(get_recipes(), [("category_potato", ASCENDING)])
    await _ensure_index(get_recipes(), [("difficulty", ASCENDING)])
    await _ensure_index(get_recipes(), [("source", ASCENDING)])
    await _ensure_index(get_recipes(), [("category_canonical", ASCENDING)])
    await _ensure_index(get_recipes(), [("difficulty_canonical", ASCENDING)])
    await _ensure_index(get_recipes(), [("search_terms", ASCENDING)])
    await _ensure_index(get_recipes(), [("title_terms", ASCENDING)])
    await _ensure_index(get_recipes(), [("ingredient_terms", ASCENDING)])
    await _ensure_index(
        get_recipes(),
        [("stats.views", DESCENDING), ("stats.saved", DESCENDING), ("stats.cooked", DESCENDING)],
    )

    await _ensure_index(get_users(), [("email", ASCENDING)], unique=True)
    await _ensure_index(get_users(), [("status", ASCENDING)])
    await _ensure_index(get_users(), [("source", ASCENDING)])

    await _ensure_index(get_user_recipe_states(), [("user_id", ASCENDING), ("recipe_id", ASCENDING)], unique=True)
    await _ensure_index(get_user_recipe_states(), [("saved", ASCENDING), ("cooked", ASCENDING)])
    await _ensure_index(get_user_recipe_states(), [("last_action_at", DESCENDING)])

    await _ensure_index(get_user_events(), [("user_id", ASCENDING), ("created_at", DESCENDING)])
    await _ensure_index(get_user_events(), [("recipe_id", ASCENDING), ("created_at", DESCENDING)])
    await _ensure_index(get_user_events(), [("action", ASCENDING), ("created_at", DESCENDING)])


async def ensure_demo_user() -> dict:
    email = normalize_email("demo@potatohub.local")
    now = datetime.now(timezone.utc)
    existing = await get_users().find_one({"_id": email})
    doc = build_user_document(
        name="Demo Cook",
        email=email,
        password_hash=hash_password("potato123"),
        source="demo_auth",
        preferred_categories=["general", "plato principal", "desayuno"],
        favorite_difficulty="easy",
        experience_level="intermediate",
        household_size=2,
        city="Lima",
    )
    if existing:
        doc["created_at"] = existing.get("created_at") or now
        doc["last_login_at"] = existing.get("last_login_at") or now
        await get_users().update_one({"_id": email}, {"$set": doc}, upsert=True)
        return await get_users().find_one({"_id": email})

    doc["created_at"] = now
    doc["updated_at"] = now
    doc["last_login_at"] = now
    await get_users().insert_one(doc)
    return doc


async def get_user_by_email(email: str) -> dict | None:
    normalized = normalize_email(email)
    if not normalized:
        return None
    return await get_users().find_one({"_id": normalized, "deleted_at": None})


async def get_user_by_id(user_id: str) -> dict | None:
    normalized = normalize_email(user_id)
    if not normalized:
        return None
    return await get_users().find_one({"_id": normalized, "deleted_at": None})


def build_user_document(
    *,
    name: str,
    email: str,
    password_hash: str,
    source: str,
    preferred_categories: list[str] | None = None,
    favorite_difficulty: str = "easy",
    experience_level: str = "beginner",
    household_size: int = 1,
    city: str = "Lima",
) -> dict:
    normalized_email = normalize_email(email)
    categories = [canonicalize_category(item) for item in (preferred_categories or []) if str(item).strip()]
    favorite_difficulty = canonicalize_difficulty(favorite_difficulty)
    now = datetime.now(timezone.utc)
    return {
        "_id": normalized_email,
        "user_id": normalized_email,
        "name": (name or "").strip() or "PotatoHub User",
        "email": normalized_email,
        "password_hash": password_hash,
        "status": "active",
        "role": "user",
        "source": source,
        "is_seeded": False,
        "profile": {
            "experience_level": experience_level,
            "household_size": household_size,
            "city": city,
            "preferred_categories": categories,
            "favorite_difficulty": favorite_difficulty,
        },
        "preferences": {
            "preferred_categories": categories,
            "difficulty": favorite_difficulty,
            "newsletter": False,
            "cooking_days": [],
        },
        "seed_persona": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "last_login_at": now,
    }


def user_to_public(doc: dict) -> dict:
    profile = doc.get("profile") or {}
    preferences = doc.get("preferences") or {}
    return {
        "id": str(doc.get("user_id") or doc.get("_id") or ""),
        "email": str(doc.get("email") or doc.get("_id") or ""),
        "name": str(doc.get("name") or "PotatoHub User"),
        "status": str(doc.get("status") or "active"),
        "role": str(doc.get("role") or "user"),
        "source": str(doc.get("source") or ""),
        "profile": {
            "experience_level": str(profile.get("experience_level") or ""),
            "household_size": int(profile.get("household_size") or 0),
            "city": str(profile.get("city") or ""),
            "preferred_categories": [str(item) for item in profile.get("preferred_categories") or []],
            "favorite_difficulty": str(profile.get("favorite_difficulty") or ""),
        },
        "preferences": {
            "preferred_categories": [str(item) for item in preferences.get("preferred_categories") or []],
            "difficulty": str(preferences.get("difficulty") or ""),
            "newsletter": bool(preferences.get("newsletter") or False),
            "cooking_days": [str(item) for item in preferences.get("cooking_days") or []],
        },
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "last_login_at": doc.get("last_login_at"),
    }


def compute_recipe_score(stats: dict | None) -> float:
    payload = stats or {}
    views = int(payload.get("views") or 0)
    saved = int(payload.get("saved") or 0)
    cooked = int(payload.get("cooked") or 0)
    return round(views * 0.5 + saved * 5 + cooked * 8, 2)


def get_interaction_log() -> AsyncIOMotorCollection:
    db_name = os.getenv("MONGO_DB", "potatohub")
    return _client[db_name]["interaction_log"]


async def init_indexes() -> None:
    col = get_recipes()
    await col.create_index([("title", TEXT), ("ingredients", TEXT)], name="text_search")
    await col.create_index([("category_potato", ASCENDING)])
    await col.create_index([("difficulty", ASCENDING)])


async def backfill_recipe_search_fields(batch_size: int = 250) -> int:
    collection = get_recipes()
    cursor = collection.find(
        {
            "$or": [
                {"search_semantic_version": {"$exists": False}},
                {"search_semantic_version": {"$ne": SEMANTIC_VERSION}},
                {"search_terms": {"$exists": False}},
                {"category_canonical": {"$exists": False}},
                {"difficulty_canonical": {"$exists": False}},
            ]
        }
    )

    operations: list[UpdateOne] = []
    updated = 0
    async for doc in cursor:
        payload = build_recipe_search_fields(doc)
        payload["search_semantic_version"] = SEMANTIC_VERSION
        payload["search_normalized_at"] = datetime.now(timezone.utc)
        operations.append(UpdateOne({"_id": doc["_id"]}, {"$set": payload}))
        if len(operations) >= batch_size:
            result = await collection.bulk_write(operations, ordered=False)
            updated += int(result.modified_count or 0) + int(result.upserted_count or 0)
            operations = []

    if operations:
        result = await collection.bulk_write(operations, ordered=False)
        updated += int(result.modified_count or 0) + int(result.upserted_count or 0)
    return updated


def doc_to_recipe(doc: dict) -> dict:
    stats = doc.get("stats") or {"views": 0, "saved": 0, "cooked": 0}
    views = int(stats.get("views") or 0)
    saved = int(stats.get("saved") or 0)
    cooked = int(stats.get("cooked") or 0)
    prep = int(doc.get("prep_time_min") or 0)
    cook = int(doc.get("cook_time_min") or 0)
    title = clean_human_text(doc.get("title") or "")
    description = clean_human_text(doc.get("description") or "")
    ingredients = [clean_human_text(item) for item in doc.get("ingredients") or [] if clean_human_text(item)]
    instructions = [clean_human_text(item) for item in doc.get("instructions") or [] if clean_human_text(item)]
    category = clean_human_text(doc.get("category_canonical") or doc.get("category_potato") or doc.get("category") or "general")
    difficulty = clean_human_text(doc.get("difficulty_canonical") or doc.get("difficulty") or "")
    return {
        "id": str(doc["_id"]),
        "title": title,
        "description": description,
        "category": category or "general",
        "difficulty": difficulty,
        "cooking_time": prep + cook,
        "ingredients": ingredients,
        "instructions": instructions,
        "image_url": doc.get("image_url"),
        "source_name": doc.get("source") or "cookpad_pe",
        "source_url": doc.get("source_url") or "",
        "tags": [clean_human_text(item) for item in doc.get("tags") or [] if clean_human_text(item)],
        "stats": {"views": views, "saved": saved, "cooked": cooked},
        "score": compute_recipe_score(stats),
        "created_at": doc.get("created_at") or doc.get("scraped_at"),
        "updated_at": doc.get("updated_at"),
    }

from __future__ import annotations

import re
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status

from app import database
from app.auth_context import current_user_from_request
from app.database import compute_recipe_score, doc_to_recipe, get_recipes
from app.models import (
    InteractionRequest,
    InteractionResponse,
    Recipe,
    RecommendationsResponse,
    RefreshResponse,
    SearchResponse,
)


router = APIRouter()


def _normalize_mode(mode: str) -> str:
    normalized = (mode or "hybrid").strip().lower()
    if normalized not in {"hybrid", "ingredients", "type"}:
        return "hybrid"
    return normalized


def _blank_similarity() -> dict:
    return {
        "graph_score": 0.0,
        "content_score": 0.0,
        "audience_score": 0.0,
        "personalized_score": 0.0,
        "shared_ingredients": 0,
        "peer_count": 0,
        "profile_overlap": 0,
        "same_category": False,
        "same_difficulty": False,
    }


def _merge_ranked_rows(sources: list[tuple[str, float, list[dict]]], limit: int) -> list[dict]:
    combined: dict[str, dict] = {}
    for source_name, weight, rows in sources:
        for row in rows:
            recipe_id = str(row.get("id") or "")
            if not recipe_id:
                continue
            entry = combined.setdefault(
                recipe_id,
                {
                    "id": recipe_id,
                    "score": 0.0,
                    "similarity": _blank_similarity(),
                    "reasons": [],
                },
            )
            base_score = float(row.get("ranking") or 0.0)
            weighted_score = round(base_score * weight, 4)
            entry["score"] += weighted_score

            similarity = entry["similarity"]
            if source_name == "content":
                similarity["content_score"] += weighted_score
                similarity["shared_ingredients"] = max(similarity["shared_ingredients"], int(row.get("shared_ingredients") or 0))
                similarity["same_category"] = similarity["same_category"] or bool(row.get("same_category") or False)
                similarity["same_difficulty"] = similarity["same_difficulty"] or bool(row.get("same_difficulty") or False)
                entry["reasons"].append("Coincide con ingredientes, categoria o dificultad de la receta base.")
            elif source_name == "audience":
                similarity["audience_score"] += weighted_score
                similarity["peer_count"] = max(similarity["peer_count"], int(row.get("peer_count") or 0))
                similarity["shared_ingredients"] = max(similarity["shared_ingredients"], int(row.get("shared_ingredients") or 0))
                similarity["same_category"] = similarity["same_category"] or bool(row.get("same_category") or False)
                entry["reasons"].append("Usuarios que guardaron o cocinaron esta receta tambien eligieron esta.")
            elif source_name == "personalized":
                similarity["personalized_score"] += weighted_score
                similarity["peer_count"] = max(similarity["peer_count"], int(row.get("peer_count") or 0))
                similarity["profile_overlap"] = max(similarity["profile_overlap"], int(row.get("profile_overlap") or 0))
                similarity["shared_ingredients"] = max(similarity["shared_ingredients"], int(row.get("shared_ingredients") or 0))
                similarity["same_category"] = similarity["same_category"] or bool(row.get("same_category") or False)
                similarity["same_difficulty"] = similarity["same_difficulty"] or bool(row.get("same_difficulty") or False)
                entry["reasons"].append("Usuarios con gustos y perfil parecidos al tuyo la prefieren.")

    merged = []
    for entry in combined.values():
        similarity = entry["similarity"]
        similarity["graph_score"] = round(
            similarity["content_score"] + similarity["audience_score"] + similarity["personalized_score"],
            2,
        )
        entry["score"] = round(entry["score"], 4)
        entry["reason"] = " ".join(dict.fromkeys(entry["reasons"]))
        merged.append(entry)

    merged.sort(
        key=lambda item: (
            item["score"],
            item["similarity"]["personalized_score"],
            item["similarity"]["audience_score"],
            item["similarity"]["content_score"],
        ),
        reverse=True,
    )
    return merged[:limit]


async def _sync_recipe_to_graph(request: Request, recipe_doc: dict) -> None:
    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    if neo4j_service is None:
        return
    try:
        await neo4j_service.write_recipe(doc_to_recipe(recipe_doc))
    except Exception:
        return


async def _fetch_recipes_by_ids(ids: list[str], metadata: dict[str, dict] | None = None) -> list[Recipe]:
    if not ids:
        return []
    docs = await get_recipes().find({"_id": {"$in": ids}}).to_list(length=len(ids))
    index = {str(doc["_id"]): doc for doc in docs}
    results = []
    for recipe_id in ids:
        doc = index.get(str(recipe_id))
        if not doc:
            continue
        payload = doc_to_recipe(doc)
        meta = (metadata or {}).get(str(recipe_id)) or {}
        if meta:
            payload["similarity"] = meta.get("similarity") or None
            payload["recommendation_reason"] = meta.get("reason") or ""
        results.append(Recipe(**payload))
    return results


async def _mongo_recommendations_fallback(anchor: dict, recipe_id: str, mode: str, limit: int) -> list[Recipe]:
    ingredients = anchor.get("ingredients") or []
    keywords = list(
        {
            word.lower()
            for ingredient in ingredients
            for word in re.split(r"\W+", ingredient)
            if len(word) > 3
        }
    )[:15]

    category = anchor.get("category_potato", "GENERAL")
    base_filter: dict = {"_id": {"$ne": recipe_id}}
    if mode == "ingredients" and keywords:
        pattern = re.compile("|".join(map(re.escape, keywords)), re.IGNORECASE)
        query = {**base_filter, "ingredients": {"$elemMatch": {"$regex": pattern}}}
    else:
        clauses = [{"category_potato": category}]
        if keywords:
            pattern = re.compile("|".join(map(re.escape, keywords)), re.IGNORECASE)
            clauses.append({"ingredients": {"$elemMatch": {"$regex": pattern}}})
        query = {**base_filter, "$or": clauses}

    docs = await get_recipes().find(query).limit(limit).to_list(length=limit)
    results = []
    for doc in docs:
        payload = doc_to_recipe(doc)
        payload["recommendation_reason"] = "Fallback MongoDB por categoria o ingredientes compartidos."
        results.append(Recipe(**payload))
    return results


async def _record_mongo_interaction(recipe_doc: dict, user: dict | None, action: str) -> dict:
    now = datetime.now(timezone.utc)
    recipes = database.get_recipes()
    recipe_id = str(recipe_doc["_id"])

    if action == "view":
        await recipes.update_one(
            {"_id": recipe_id},
            {"$inc": {"stats.views": 1}, "$set": {"updated_at": now}},
        )
    else:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login required to save or mark recipes as cooked",
            )

        states = database.get_user_recipe_states()
        state_filter = {"user_id": user["user_id"], "recipe_id": recipe_id}
        existing_state = await states.find_one(state_filter)
        state_update = {
            "$set": {
                "user_id": user["user_id"],
                "recipe_id": recipe_id,
                "last_action": action,
                "last_action_at": now,
                "updated_at": now,
                "source": "app_auth",
            },
            "$setOnInsert": {
                "_id": f"{user['user_id']}::{recipe_id}",
                "created_at": now,
                "viewed_count": 0,
                "saved": False,
                "saved_at": None,
                "cooked": False,
                "cooked_at": None,
            },
        }
        recipe_increments = {}

        if action == "save":
            already_saved = bool(existing_state and existing_state.get("saved"))
            state_update["$set"]["saved"] = True
            state_update["$set"]["saved_at"] = (existing_state.get("saved_at") if existing_state else None) or now
            if not already_saved:
                recipe_increments["stats.saved"] = 1
        elif action == "cook":
            already_cooked = bool(existing_state and existing_state.get("cooked"))
            state_update["$set"]["cooked"] = True
            state_update["$set"]["cooked_at"] = (existing_state.get("cooked_at") if existing_state else None) or now
            if not already_cooked:
                recipe_increments["stats.cooked"] = 1

        await states.update_one(state_filter, state_update, upsert=True)
        recipe_update = {"$set": {"updated_at": now}}
        if recipe_increments:
            recipe_update["$inc"] = recipe_increments
        await recipes.update_one({"_id": recipe_id}, recipe_update)

    if user is not None:
        event_doc = {
            "_id": f"{user['user_id']}::{recipe_id}::{action}::{uuid4().hex}",
            "user_id": user["user_id"],
            "recipe_id": recipe_id,
            "action": action,
            "source": "app_auth",
            "created_at": now,
        }
        await database.get_user_events().insert_one(event_doc)

        if action == "view":
            await database.get_user_recipe_states().update_one(
                {"user_id": user["user_id"], "recipe_id": recipe_id},
                {
                    "$inc": {"viewed_count": 1},
                    "$set": {
                        "user_id": user["user_id"],
                        "recipe_id": recipe_id,
                        "last_action": "view",
                        "last_action_at": now,
                        "updated_at": now,
                        "source": "app_auth",
                    },
                    "$setOnInsert": {
                        "_id": f"{user['user_id']}::{recipe_id}",
                        "created_at": now,
                        "saved": False,
                        "saved_at": None,
                        "cooked": False,
                        "cooked_at": None,
                    },
                },
                upsert=True,
            )

    return await recipes.find_one({"_id": recipe_id})


async def _best_effort_sync_interaction(request: Request, user: dict | None, recipe_doc: dict, action: str) -> None:
    if user is None:
        return
    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    if neo4j_service is None:
        return
    try:
        await neo4j_service.record_interaction(user, doc_to_recipe(recipe_doc), action)
    except Exception:
        return


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(request: Request):
    count = await get_recipes().count_documents({})
    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    if neo4j_service is not None:
        docs = await get_recipes().find({}).to_list(length=None)
        if docs:
            try:
                await neo4j_service.write_recipes([doc_to_recipe(doc) for doc in docs])
            except Exception:
                pass
    return RefreshResponse(
        success=True,
        stored=count,
        sources=["cookpad_pe"],
        scraped=0,
        fallback_used=False,
    )


<<<<<<< HEAD
=======
@router.get("/filters")
async def filters():
    col = get_recipes()
    categories = sorted([item for item in await col.distinct("category_potato") if item])
    difficulties = sorted([item for item in await col.distinct("difficulty") if item])
    sources = sorted([item for item in await col.distinct("source") if item])
    return {
        "categories": categories,
        "difficulties": difficulties,
        "sources": sources,
    }


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = "*",
    category: str = "",
    difficulty: str = "",
    page: int = Query(0, ge=0),
    size: int = Query(6, ge=1, le=50),
):
    col = get_recipes()
    filters_query: dict = {}

    if q and q != "*":
        pattern = re.compile(re.escape(q), re.IGNORECASE)
        filters_query["$or"] = [
            {"title": {"$regex": pattern}},
            {"ingredients": {"$elemMatch": {"$regex": pattern}}},
        ]

    if category:
        filters_query["category_potato"] = re.compile(f"^{re.escape(category)}$", re.IGNORECASE)

    if difficulty:
        filters_query["difficulty"] = re.compile(f"^{re.escape(difficulty)}$", re.IGNORECASE)

    total = await col.count_documents(filters_query)
    docs = await col.find(filters_query).skip(page * size).limit(size).to_list(length=size)
    results = [Recipe(**doc_to_recipe(doc)) for doc in docs]
    return SearchResponse(total=total, page=page, size=size, results=results)


@router.get("/ranking/{period}")
async def ranking(request: Request, period: str, limit: int = Query(10, ge=1, le=50)):
    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    rows = await neo4j_service.ranking(period, limit) if neo4j_service is not None else []
    ids = [row["id"] for row in rows]

    if ids:
        results = await _fetch_recipes_by_ids(ids)
        return {"period": period, "source": "neo4j", "results": [item.model_dump() for item in results]}

    pipeline = [
        {
            "$addFields": {
                "computed_score": {
                    "$add": [
                        {"$multiply": [{"$ifNull": ["$stats.views", 0]}, 0.5]},
                        {"$multiply": [{"$ifNull": ["$stats.saved", 0]}, 5.0]},
                        {"$multiply": [{"$ifNull": ["$stats.cooked", 0]}, 8.0]},
                    ]
                }
            }
        },
        {"$sort": {"computed_score": -1}},
        {"$limit": limit},
    ]
    docs = await get_recipes().aggregate(pipeline).to_list(length=limit)
    results = [Recipe(**doc_to_recipe(doc)) for doc in docs]
    return {"period": period, "source": "mongodb_fallback", "results": [item.model_dump() for item in results]}


@router.get("/{recipe_id}", response_model=Recipe)
async def get_recipe(request: Request, recipe_id: str):
    doc = await get_recipes().find_one({"_id": recipe_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    await _sync_recipe_to_graph(request, doc)
    return Recipe(**doc_to_recipe(doc))


@router.post("/{recipe_id}/interact", response_model=InteractionResponse)
async def interact(request: Request, recipe_id: str, payload: InteractionRequest):
    action = (payload.action or "").strip().lower()
    if action not in {"view", "save", "cook"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="action must be 'view', 'save' or 'cook'")

    recipe_doc = await get_recipes().find_one({"_id": recipe_id})
    if not recipe_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")

    user = await current_user_from_request(request)
    updated_doc = await _record_mongo_interaction(recipe_doc, user, action)
    await _best_effort_sync_interaction(request, user, updated_doc, action)

    stats = updated_doc.get("stats") or {}
    user_id = user["user_id"] if user else "anonymous"
    return InteractionResponse(
        success=True,
        recipe_id=recipe_id,
        action=action,
        user_id=user_id,
        views=int(stats.get("views") or 0),
        saved=int(stats.get("saved") or 0),
        cooked=int(stats.get("cooked") or 0),
        score=compute_recipe_score(stats),
    )


@router.get("/{recipe_id}/recommendations", response_model=RecommendationsResponse)
async def recommendations(
    request: Request,
    recipe_id: str,
    limit: int = Query(6, ge=1, le=24),
    mode: str = Query("hybrid", pattern="^(hybrid|ingredients|type)$"),
):
    anchor = await get_recipes().find_one({"_id": recipe_id})
    if not anchor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")

    await _sync_recipe_to_graph(request, anchor)
    mode = _normalize_mode(mode)
    current_user = await current_user_from_request(request)
    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    merged_rows: list[dict] = []

    if neo4j_service is not None:
        content_rows = await neo4j_service.recommend_by_content(recipe_id, limit=limit * 2, mode=mode)
        audience_rows = await neo4j_service.recommend_from_anchor_audience(recipe_id, limit=limit * 2) if mode == "hybrid" else []
        personalized_rows = []
        if mode == "hybrid" and current_user is not None:
            personalized_rows = await neo4j_service.recommend_for_user_from_recipe(
                current_user["user_id"],
                recipe_id,
                limit=limit * 2,
            )

        sources = [("content", 1.0, content_rows)]
        if audience_rows:
            sources.append(("audience", 1.1, audience_rows))
        if personalized_rows:
            sources.append(("personalized", 1.35, personalized_rows))
        merged_rows = _merge_ranked_rows(sources, limit=limit)

    if merged_rows:
        ids = [row["id"] for row in merged_rows]
        metadata = {row["id"]: {"similarity": row["similarity"], "reason": row["reason"]} for row in merged_rows}
        results = await _fetch_recipes_by_ids(ids, metadata=metadata)
        if results:
            return RecommendationsResponse(recipe_id=recipe_id, mode=mode, results=results)

    fallback_results = await _mongo_recommendations_fallback(anchor, recipe_id, mode, limit)
    return RecommendationsResponse(recipe_id=recipe_id, mode=mode, results=fallback_results)

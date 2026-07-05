import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Request
from app.database import get_recipes, doc_to_recipe, get_interaction_log
from app.limiter import limiter
from app.neo4j_db import get_driver
from app.models import (
    Recipe,
    SearchResponse,
    InteractionRequest,
    InteractionResponse,
    RecommendationsResponse,
    RefreshResponse,
)

router = APIRouter()

# ── helpers Neo4j ─────────────────────────────────────────────────────────────

async def _neo4j_record_interaction(recipe_id: str, user_id: str, action: str) -> None:
    rel = "VIEWED" if action == "view" else "SAVED"
    async with get_driver().session() as s:
        await s.execute_write(
            lambda tx: tx.run(
                f"""
                MERGE (u:User {{id: $uid}})
                MERGE (r:Recipe {{id: $rid}})
                CREATE (u)-[:{rel} {{timestamp: datetime()}}]->(r)
                """,
                uid=user_id,
                rid=recipe_id,
            )
        )


async def _neo4j_ranking(period: str, limit: int) -> list[str]:
    """Devuelve recipe_ids ordenados por score desde Neo4j. Retorna [] si no hay datos."""
    days = {"week": 7, "month": 30, "all": 36500}.get(period, 30)
    async with get_driver().session() as s:
        result = await s.run(
            """
            MATCH (r:Recipe)<-[i:VIEWED|SAVED]-()
            WHERE i.timestamp >= datetime() - duration({days: $days})
            WITH r,
                 sum(CASE WHEN type(i) = 'VIEWED' THEN 0.5 ELSE 5.0 END) AS score
            ORDER BY score DESC
            LIMIT $limit
            RETURN r.id AS id
            """,
            days=days,
            limit=limit,
        )
        records = await result.data()
    return [r["id"] for r in records]


async def _neo4j_collab(recipe_id: str, limit: int) -> list[str]:
    """Filtrado colaborativo: usuarios que guardaron esta receta tambien guardaron..."""
    async with get_driver().session() as s:
        result = await s.run(
            """
            MATCH (r:Recipe {id: $rid})<-[:SAVED]-(u:User)-[:SAVED]->(r2:Recipe)
            WHERE r2.id <> $rid
            WITH r2, count(DISTINCT u) AS shared
            ORDER BY shared DESC
            LIMIT $limit
            RETURN r2.id AS id
            """,
            rid=recipe_id,
            limit=limit,
        )
        records = await result.data()
    return [r["id"] for r in records]


async def _neo4j_similar_category(recipe_id: str, category: str, limit: int) -> list[str]:
    """Recetas de la misma categoria en el grafo."""
    async with get_driver().session() as s:
        result = await s.run(
            """
            MATCH (r2:Recipe {category: $cat})
            WHERE r2.id <> $rid
            WITH r2 ORDER BY rand()
            LIMIT $limit
            RETURN r2.id AS id
            """,
            cat=category,
            rid=recipe_id,
            limit=limit,
        )
        records = await result.data()
    return [r["id"] for r in records]


async def _fetch_recipes_by_ids(ids: list[str]) -> list[Recipe]:
    if not ids:
        return []
    col = get_recipes()
    docs = await col.find({"_id": {"$in": ids}}).to_list(len(ids))
    index = {d["_id"]: d for d in docs}
    return [Recipe(**doc_to_recipe(index[i])) for i in ids if i in index]


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=RefreshResponse)
async def refresh():
    count = await get_recipes().count_documents({})
    return RefreshResponse(
        success=True,
        stored=count,
        sources=["cookpad_pe"],
        scraped=0,
        fallback_used=False,
    )



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
    filters: dict = {}

    if q and q != "*":
        pattern = re.compile(re.escape(q), re.IGNORECASE)
        filters["$or"] = [
            {"title": {"$regex": pattern}},
            {"ingredients": {"$elemMatch": {"$regex": pattern}}},
        ]

    if category:
        filters["category_potato"] = re.compile(f"^{re.escape(category)}$", re.IGNORECASE)

    if difficulty:
        filters["difficulty"] = re.compile(f"^{re.escape(difficulty)}$", re.IGNORECASE)

    total = await col.count_documents(filters)
    docs = await col.find(filters).skip(page * size).limit(size).to_list(size)
    results = [Recipe(**doc_to_recipe(d)) for d in docs]

    return SearchResponse(total=total, page=page, size=size, results=results)


# /ranking/{period} debe ir ANTES de /{recipe_id}
@router.get("/ranking/{period}")
async def ranking(
    period: str,
    limit: int = Query(10, ge=1, le=50),
):
    ids = await _neo4j_ranking(period, limit)

    if ids:
        results = await _fetch_recipes_by_ids(ids)
        return {"period": period, "source": "neo4j", "results": [r.model_dump() for r in results]}

    # Fallback MongoDB cuando aun no hay interacciones en el grafo
    col = get_recipes()
    pipeline = [
        {
            "$addFields": {
                "computed_score": {
                    "$add": [
                        {"$multiply": [{"$ifNull": ["$stats.views", 0]}, 0.5]},
                        {"$multiply": [{"$ifNull": ["$stats.saved", 0]}, 5.0]},
                    ]
                }
            }
        },
        {"$sort": {"computed_score": -1}},
        {"$limit": limit},
    ]
    docs = await col.aggregate(pipeline).to_list(limit)
    results = [Recipe(**doc_to_recipe(d)) for d in docs]
    return {"period": period, "source": "mongodb_fallback", "results": [r.model_dump() for r in results]}


@router.get("/{recipe_id}", response_model=Recipe)
async def get_recipe(recipe_id: str):
    doc = await get_recipes().find_one({"_id": recipe_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return Recipe(**doc_to_recipe(doc))


@router.post("/{recipe_id}/interact", response_model=InteractionResponse)
@limiter.limit("30/minute")
async def interact(recipe_id: str, payload: InteractionRequest, request: Request):
    col = get_recipes()
    if not await col.find_one({"_id": recipe_id}):
        raise HTTPException(status_code=404, detail="Recipe not found")

    if payload.action not in ("view", "save"):
        raise HTTPException(status_code=400, detail="action must be 'view' or 'save'")

    # MongoDB: contadores atomicos
    field = "stats.views" if payload.action == "view" else "stats.saved"
    await col.update_one(
        {"_id": recipe_id},
        {"$inc": {field: 1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )

    # Neo4j: relacion VIEWED o SAVED con timestamp
    await _neo4j_record_interaction(recipe_id, payload.user_id, payload.action)

    # MongoDB: log inmutable de interacciones
    await get_interaction_log().insert_one({
        "userId":    payload.user_id,
        "recipeId":  recipe_id,
        "type":      "VIEWED" if payload.action == "view" else "SAVED",
        "timestamp": datetime.now(timezone.utc),
    })

    doc = await col.find_one({"_id": recipe_id})
    stats = doc.get("stats") or {}
    views = int(stats.get("views") or 0)
    saved = int(stats.get("saved") or 0)
    score = round(views * 0.5 + saved * 5, 2)

    return InteractionResponse(
        success=True,
        recipe_id=recipe_id,
        action=payload.action,
        views=views,
        saved=saved,
        score=score,
    )


@router.get("/{recipe_id}/recommendations", response_model=RecommendationsResponse)
async def recommendations(
    recipe_id: str,
    limit: int = Query(6, ge=1, le=24),
    mode: str = Query("hybrid"),
):
    col = get_recipes()
    anchor = await col.find_one({"_id": recipe_id})
    if not anchor:
        raise HTTPException(status_code=404, detail="Recipe not found")

    category = anchor.get("category_potato", "GENERAL")
    ids: list[str] = []

    if mode == "type":
        ids = await _neo4j_similar_category(recipe_id, category, limit)

    elif mode == "hybrid":
        # Filtrado colaborativo primero
        ids = await _neo4j_collab(recipe_id, limit)
        # Complementa con misma categoria si hacen falta
        if len(ids) < limit:
            cat_ids = await _neo4j_similar_category(recipe_id, category, limit)
            for cid in cat_ids:
                if cid not in ids:
                    ids.append(cid)
                if len(ids) >= limit:
                    break

    # Fallback MongoDB: ingredientes compartidos
    if not ids:
        ingredients = anchor.get("ingredients") or []
        keywords = list({
            word.lower()
            for ing in ingredients
            for word in re.split(r"\W+", ing)
            if len(word) > 3
        })[:15]

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

        docs = await col.find(query).limit(limit).to_list(limit)
        results = [Recipe(**doc_to_recipe(d)) for d in docs]
        return RecommendationsResponse(recipe_id=recipe_id, mode=mode, results=results)

    results = await _fetch_recipes_by_ids(ids[:limit])
    return RecommendationsResponse(recipe_id=recipe_id, mode=mode, results=results)

import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from app.database import get_recipes, doc_to_recipe
from app.models import (
    Recipe,
    SearchResponse,
    InteractionRequest,
    InteractionResponse,
    RecommendationsResponse,
    RefreshResponse,
)

router = APIRouter()


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


# /ranking/{period} debe ir ANTES de /{recipe_id} para que FastAPI no confunda "ranking" con un ID
@router.get("/ranking/{period}")
async def ranking(
    period: str,
    limit: int = Query(10, ge=1, le=50),
):
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
    return {"period": period, "results": [r.model_dump() for r in results]}


@router.get("/{recipe_id}", response_model=Recipe)
async def get_recipe(recipe_id: str):
    doc = await get_recipes().find_one({"_id": recipe_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return Recipe(**doc_to_recipe(doc))


@router.post("/{recipe_id}/interact", response_model=InteractionResponse)
async def interact(recipe_id: str, payload: InteractionRequest):
    col = get_recipes()
    if not await col.find_one({"_id": recipe_id}):
        raise HTTPException(status_code=404, detail="Recipe not found")

    if payload.action not in ("view", "save"):
        raise HTTPException(status_code=400, detail="action must be 'view' or 'save'")

    field = "stats.views" if payload.action == "view" else "stats.saved"
    await col.update_one(
        {"_id": recipe_id},
        {"$inc": {field: 1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )

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
    ingredients = anchor.get("ingredients") or []

    # Palabras clave de ingredientes (más de 3 chars, sin stopwords cortas)
    keywords = list({
        word.lower()
        for ing in ingredients
        for word in re.split(r"\W+", ing)
        if len(word) > 3
    })[:15]

    base_filter: dict = {"_id": {"$ne": recipe_id}}

    if mode == "type":
        query = {**base_filter, "category_potato": category}
    elif mode == "ingredients" and keywords:
        pattern = re.compile("|".join(map(re.escape, keywords)), re.IGNORECASE)
        query = {**base_filter, "ingredients": {"$elemMatch": {"$regex": pattern}}}
    else:  # hybrid
        clauses = [{"category_potato": category}]
        if keywords:
            pattern = re.compile("|".join(map(re.escape, keywords)), re.IGNORECASE)
            clauses.append({"ingredients": {"$elemMatch": {"$regex": pattern}}})
        query = {**base_filter, "$or": clauses}

    docs = await col.find(query).limit(limit).to_list(limit)
    results = [Recipe(**doc_to_recipe(d)) for d in docs]

    return RecommendationsResponse(recipe_id=recipe_id, mode=mode, results=results)

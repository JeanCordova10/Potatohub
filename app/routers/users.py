from fastapi import APIRouter, Query, Request

from app import database
from app.auth_context import require_current_user
from app.database import doc_to_recipe
from app.models import Recipe, UserLibraryResponse, UserRecommendationsResponse


router = APIRouter()


@router.get("/me/library", response_model=UserLibraryResponse)
async def my_library(request: Request):
    user = await require_current_user(request)

    states = await database.get_user_recipe_states().find(
        {"user_id": user["user_id"], "$or": [{"saved": True}, {"cooked": True}]}
    ).sort("updated_at", -1).to_list(length=None)

    recipe_ids = [state["recipe_id"] for state in states]
    docs = await database.get_recipes().find({"_id": {"$in": recipe_ids}}).to_list(length=len(recipe_ids))
    doc_index = {str(doc["_id"]): doc for doc in docs}

    saved_results = []
    cooked_results = []
    for state in states:
        doc = doc_index.get(str(state["recipe_id"]))
        if not doc:
            continue
        recipe = Recipe(**doc_to_recipe(doc))
        if state.get("saved"):
            saved_results.append(recipe)
        if state.get("cooked"):
            cooked_results.append(recipe)

    return UserLibraryResponse(user_id=user["user_id"], saved=saved_results, cooked=cooked_results)


@router.get("/me/recommendations", response_model=UserRecommendationsResponse)
async def my_recommendations(
    request: Request,
    limit: int = Query(6, ge=1, le=24),
):
    user = await require_current_user(request)
    neo4j_service = getattr(request.app.state, "neo4j_service", None)

    rows = []
    if neo4j_service is not None:
        rows = await neo4j_service.recommend_by_own_history(user["user_id"], limit=limit)

    if rows:
        recipe_ids = [row["id"] for row in rows]
        docs = await database.get_recipes().find({"_id": {"$in": recipe_ids}}).to_list(length=len(recipe_ids))
        doc_index = {str(doc["_id"]): doc for doc in docs}
        results = []
        for row in rows:
            doc = doc_index.get(str(row["id"]))
            if not doc:
                continue
            payload = doc_to_recipe(doc)
            payload["recommendation_reason"] = "Se parece a recetas que ya guardaste o cocinaste."
            payload["similarity"] = {
                "graph_score": round(float(row.get("ranking") or 0.0), 2),
                "content_score": round(float(row.get("ranking") or 0.0), 2),
                "shared_ingredients": int(row.get("shared_ingredients") or 0),
                "shared_title_terms": int(row.get("shared_title_terms") or 0),
                "same_category": bool(row.get("same_category") or False),
                "same_difficulty": bool(row.get("same_difficulty") or False),
            }
            results.append(Recipe(**payload))
            if len(results) >= limit:
                break
        if results:
            return UserRecommendationsResponse(user_id=user["user_id"], results=results)

    states = await database.get_user_recipe_states().find({"user_id": user["user_id"]}).to_list(length=None)
    seen_ids = [state["recipe_id"] for state in states]
    history_ids = [state["recipe_id"] for state in states if state.get("saved") or state.get("cooked")]

    history_docs = (
        await database.get_recipes().find({"_id": {"$in": history_ids}}).to_list(length=len(history_ids))
        if history_ids
        else []
    )
    categories = sorted({doc["category_canonical"] for doc in history_docs if doc.get("category_canonical")})
    ingredient_terms = sorted({term for doc in history_docs for term in (doc.get("ingredient_terms") or [])})

    query = {"_id": {"$nin": seen_ids}}
    clauses = []
    if ingredient_terms:
        clauses.append({"ingredient_terms": {"$in": ingredient_terms}})
    if categories:
        clauses.append({"category_canonical": {"$in": categories}})
    if clauses:
        query["$or"] = clauses

    docs = await database.get_recipes().find(query).limit(limit).to_list(length=limit)
    reason = "Sugerencia basada en lo que ya guardaste o cocinaste."
    if not docs and clauses:
        docs = await database.get_recipes().find({"_id": {"$nin": seen_ids}}).limit(limit).to_list(length=limit)
        reason = "Sugerencia para que sigas explorando el catalogo."

    results = []
    for doc in docs:
        payload = doc_to_recipe(doc)
        payload["recommendation_reason"] = reason
        results.append(Recipe(**payload))
    return UserRecommendationsResponse(user_id=user["user_id"], results=results)

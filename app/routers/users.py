from fastapi import APIRouter, Query, Request

from app import database
from app.auth_context import require_current_user
from app.database import doc_to_recipe
from app.models import Recipe, UserRecommendationsResponse
from app.semantic_search import canonicalize_category, canonicalize_difficulty


router = APIRouter()


@router.get("/me/recommendations", response_model=UserRecommendationsResponse)
async def my_recommendations(
    request: Request,
    limit: int = Query(6, ge=1, le=24),
):
    user = await require_current_user(request)
    neo4j_service = getattr(request.app.state, "neo4j_service", None)

    rows = []
    if neo4j_service is not None:
        rows = await neo4j_service.recommend_for_user(user["user_id"], limit=limit)

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
            payload["recommendation_reason"] = "Usuarios con perfil similar guardaron o cocinaron esta receta."
            payload["similarity"] = {
                "graph_score": round(float(row.get("ranking") or 0.0), 2),
                "personalized_score": round(float(row.get("ranking") or 0.0), 2),
                "peer_count": int(row.get("peer_count") or 0),
                "profile_overlap": int(row.get("profile_overlap") or 0),
                "shared_ingredients": int(row.get("shared_ingredients") or 0),
            }
            results.append(Recipe(**payload))
            if len(results) >= limit:
                break
        if results:
            return UserRecommendationsResponse(user_id=user["user_id"], results=results)

    states = await database.get_user_recipe_states().find({"user_id": user["user_id"]}).to_list(length=None)
    seen_ids = [state["recipe_id"] for state in states]
    preferred_categories = user.get("preferences", {}).get("preferred_categories") or user.get("profile", {}).get("preferred_categories") or []
    difficulty = user.get("preferences", {}).get("difficulty") or user.get("profile", {}).get("favorite_difficulty") or ""
    preferred_categories = [canonicalize_category(item) for item in preferred_categories if str(item).strip()]
    difficulty = canonicalize_difficulty(difficulty) if difficulty else ""

    query = {"_id": {"$nin": seen_ids}}
    clauses = []
    if preferred_categories:
        clauses.append({"category_canonical": {"$in": preferred_categories}})
    if difficulty:
        clauses.append({"difficulty_canonical": difficulty})
    if clauses:
        query["$or"] = clauses

    docs = await database.get_recipes().find(query).limit(limit).to_list(length=limit)
    results = []
    for doc in docs:
        payload = doc_to_recipe(doc)
        payload["recommendation_reason"] = "Sugerencia basada en tus categorias y dificultad favoritas."
        results.append(Recipe(**payload))
    return UserRecommendationsResponse(user_id=user["user_id"], results=results)

import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status

from app import database
from app.auth_context import current_user_from_request
from app.database import compute_recipe_score, doc_to_recipe, get_interaction_log, get_recipes
from app.limiter import limiter
from app.models import (
    InteractionRequest,
    InteractionResponse,
    Recipe,
    RecommendationsResponse,
    RefreshResponse,
    SearchResponse,
)
from app.semantic_search import (
    build_query_signals,
    build_recipe_search_fields,
    canonicalize_category,
    canonicalize_difficulty,
    clean_human_text,
    extract_ingredient_terms,
    extract_title_terms,
    expand_semantic_terms,
    normalize_text,
    tokenize_text,
)


router = APIRouter()


def _normalize_text(value: str) -> str:
    return normalize_text(value)


def _tokenize_text(value: str) -> list[str]:
    return tokenize_text(value)


def _ordered_unique(tokens: list[str], limit: int) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        results.append(token)
        if len(results) >= limit:
            break
    return results


def _extract_title_terms(title: str) -> list[str]:
    return extract_title_terms(title)


def _extract_ingredient_terms(ingredients: list[str]) -> list[str]:
    return extract_ingredient_terms(ingredients)


def _normalize_mode(mode: str) -> str:
    normalized = (mode or "hybrid").strip().lower()
    if normalized == "type":
        return "category"
    if normalized not in {"hybrid", "ingredients", "category", "title"}:
        return "hybrid"
    return normalized


def _blank_similarity() -> dict:
    return {
        "graph_score": 0.0,
        "content_score": 0.0,
        "audience_score": 0.0,
        "personalized_score": 0.0,
        "shared_ingredients": 0,
        "shared_title_terms": 0,
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
                similarity["shared_title_terms"] = max(similarity["shared_title_terms"], int(row.get("shared_title_terms") or 0))
                similarity["same_category"] = similarity["same_category"] or bool(row.get("same_category") or False)
                similarity["same_difficulty"] = similarity["same_difficulty"] or bool(row.get("same_difficulty") or False)
                entry["reasons"].append("Coincide con ingredientes, categoria o palabras clave del titulo de la receta base.")
            elif source_name == "audience":
                similarity["audience_score"] += weighted_score
                similarity["peer_count"] = max(similarity["peer_count"], int(row.get("peer_count") or 0))
                similarity["shared_ingredients"] = max(similarity["shared_ingredients"], int(row.get("shared_ingredients") or 0))
                similarity["shared_title_terms"] = max(similarity["shared_title_terms"], int(row.get("shared_title_terms") or 0))
                similarity["same_category"] = similarity["same_category"] or bool(row.get("same_category") or False)
                similarity["same_difficulty"] = similarity["same_difficulty"] or bool(row.get("same_difficulty") or False)
                entry["reasons"].append("Usuarios que guardaron o cocinaron esta receta tambien eligieron esta.")
            elif source_name == "personalized":
                similarity["personalized_score"] += weighted_score
                similarity["peer_count"] = max(similarity["peer_count"], int(row.get("peer_count") or 0))
                similarity["profile_overlap"] = max(similarity["profile_overlap"], int(row.get("profile_overlap") or 0))
                similarity["shared_ingredients"] = max(similarity["shared_ingredients"], int(row.get("shared_ingredients") or 0))
                similarity["shared_title_terms"] = max(similarity["shared_title_terms"], int(row.get("shared_title_terms") or 0))
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


async def _fetch_recipes_by_ids(ids: list[str], metadata: Optional[dict[str, dict]] = None) -> list[Recipe]:
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


def _recipe_similarity_signals(doc: dict) -> dict:
    semantic = build_recipe_search_fields(doc)
    return {
        "category": semantic["category_canonical"],
        "difficulty": semantic["difficulty_canonical"],
        "ingredient_terms": set(semantic["ingredient_terms"]),
        "title_terms": set(semantic["title_terms"]),
    }


def _score_recommendation_candidate(anchor_signals: dict, candidate_doc: dict, mode: str) -> tuple[float, dict, str]:
    candidate_signals = _recipe_similarity_signals(candidate_doc)
    shared_ingredients = len(anchor_signals["ingredient_terms"] & candidate_signals["ingredient_terms"])
    shared_title_terms = len(anchor_signals["title_terms"] & candidate_signals["title_terms"])
    same_category = bool(anchor_signals["category"] and candidate_signals["category"] == anchor_signals["category"])
    same_difficulty = bool(anchor_signals["difficulty"] and candidate_signals["difficulty"] == anchor_signals["difficulty"])

    if mode == "ingredients":
        ranking = (shared_ingredients * 3.0) + (shared_title_terms * 0.55) + (0.9 if same_category else 0.0) + (0.2 if same_difficulty else 0.0)
        reason = "Fallback MongoDB por ingredientes parecidos."
    elif mode == "category":
        ranking = (4.5 if same_category else 0.0) + (shared_ingredients * 1.2) + (shared_title_terms * 1.0) + (0.4 if same_difficulty else 0.0)
        reason = "Fallback MongoDB por categoria relacionada."
    elif mode == "title":
        ranking = (shared_title_terms * 3.5) + (shared_ingredients * 1.0) + (1.5 if same_category else 0.0) + (0.2 if same_difficulty else 0.0)
        reason = "Fallback MongoDB por palabras similares en el titulo."
    else:
        ranking = (shared_ingredients * 2.2) + (shared_title_terms * 1.8) + (2.8 if same_category else 0.0) + (0.4 if same_difficulty else 0.0)
        reason = "Fallback MongoDB por ingredientes, categoria y titulo relacionados."

    ranking += float(compute_recipe_score(candidate_doc.get("stats") or {})) * 0.08
    similarity = {
        "graph_score": 0.0,
        "content_score": round(ranking, 2),
        "audience_score": 0.0,
        "personalized_score": 0.0,
        "shared_ingredients": shared_ingredients,
        "shared_title_terms": shared_title_terms,
        "peer_count": 0,
        "profile_overlap": 0,
        "same_category": same_category,
        "same_difficulty": same_difficulty,
    }
    return ranking, similarity, reason


def _expand_query_terms(tokens: list[str]) -> set[str]:
    return set(expand_semantic_terms(tokens))


def _query_similarity_signals(query: str) -> dict:
    return build_query_signals(query)


def _recipe_discovery_signals(doc: dict) -> dict:
    semantic = build_recipe_search_fields(doc)
    return {
        "normalized_title": semantic["title_canonical"],
        "title_terms": set(semantic["title_terms"]),
        "normalized_ingredients": " ".join(semantic["ingredients_canonical"]),
        "ingredient_terms": set(semantic["ingredient_terms"]),
        "normalized_category": semantic["category_canonical"],
        "category_terms": set(_tokenize_text(semantic["category_canonical"])),
        "normalized_difficulty": semantic["difficulty_canonical"],
        "search_text_canonical": semantic["search_text_canonical"],
    }


def _score_query_recipe_candidate(query_signals: dict, candidate_doc: dict, mode: str) -> tuple[float, dict, str]:
    candidate_signals = _recipe_discovery_signals(candidate_doc)
    query_terms = query_signals["query_terms"]
    normalized_query = query_signals["normalized_query"]

    title_hits = len(query_terms & candidate_signals["title_terms"])
    ingredient_hits = len(query_terms & candidate_signals["ingredient_terms"])
    category_hits = len(query_terms & candidate_signals["category_terms"])

    exact_title = bool(normalized_query and normalized_query in candidate_signals["normalized_title"])
    exact_ingredients = bool(normalized_query and normalized_query in candidate_signals["normalized_ingredients"])
    exact_category = bool(
        query_signals.get("category_canonical")
        and query_signals["category_canonical"] == candidate_signals["normalized_category"]
    ) or bool(normalized_query and normalized_query in candidate_signals["normalized_category"])
    exact_search_text = bool(normalized_query and normalized_query in candidate_signals["search_text_canonical"])
    same_difficulty = bool(
        query_signals.get("difficulty_canonical")
        and query_signals["difficulty_canonical"] == candidate_signals["normalized_difficulty"]
    )

    if mode == "ingredients":
        ranking = (ingredient_hits * 3.2) + (4.0 if exact_ingredients else 0.0) + (title_hits * 0.55) + (category_hits * 0.9)
        matched = ingredient_hits > 0 or exact_ingredients
        reason = "Coincide con tu busqueda en ingredientes."
    elif mode == "category":
        ranking = (category_hits * 4.8) + (4.0 if exact_category else 0.0) + (title_hits * 1.0) + (ingredient_hits * 1.0) + (0.3 if same_difficulty else 0.0)
        matched = category_hits > 0 or exact_category
        reason = "Coincide con tu busqueda de categoria."
    elif mode == "title":
        ranking = (title_hits * 3.7) + (4.0 if exact_title else 0.0) + (ingredient_hits * 0.5) + (category_hits * 0.75)
        matched = title_hits > 0 or exact_title
        reason = "Coincide con tu busqueda por palabras del titulo."
    else:
        ranking = (
            (title_hits * 2.0)
            + (ingredient_hits * 2.2)
            + (category_hits * 2.8)
            + (3.0 if exact_title else 0.0)
            + (2.5 if exact_ingredients else 0.0)
            + (2.0 if exact_category else 0.0)
            + (1.8 if exact_search_text else 0.0)
            + (0.5 if same_difficulty else 0.0)
        )
        matched = title_hits > 0 or ingredient_hits > 0 or category_hits > 0 or exact_title or exact_ingredients or exact_category
        reason = "Coincide con tu busqueda en titulo, ingredientes o categoria."

    ranking += float(compute_recipe_score(candidate_doc.get("stats") or {})) * 0.06
    similarity = {
        "graph_score": 0.0,
        "content_score": round(ranking, 2),
        "audience_score": 0.0,
        "personalized_score": 0.0,
        "shared_ingredients": ingredient_hits,
        "shared_title_terms": title_hits,
        "peer_count": 0,
        "profile_overlap": 0,
        "same_category": category_hits > 0 or exact_category,
        "same_difficulty": same_difficulty,
    }
    if not matched:
        return 0.0, similarity, reason
    return ranking, similarity, reason


def _semantic_candidate_filter(query_signals: dict, mode: str, exclude_recipe_id: str = "") -> dict:
    base_filter: dict = {}
    if exclude_recipe_id:
        base_filter["_id"] = {"$ne": exclude_recipe_id}

    query_terms = sorted(query_signals["query_terms"])
    normalized_query = query_signals["normalized_query"]
    category_canonical = query_signals.get("category_canonical") or ""
    difficulty_canonical = query_signals.get("difficulty_canonical") or ""

    clauses: list[dict] = []
    if mode in {"hybrid", "ingredients"} and query_terms:
        clauses.append({"ingredient_terms": {"$in": query_terms}})
    if mode in {"hybrid", "title"} and query_terms:
        clauses.append({"title_terms": {"$in": query_terms}})
    if mode == "hybrid" and query_terms:
        clauses.append({"search_terms": {"$in": query_terms}})
    if mode in {"hybrid", "category"} and category_canonical:
        clauses.append({"category_canonical": category_canonical})
    if mode == "hybrid" and difficulty_canonical:
        clauses.append({"difficulty_canonical": difficulty_canonical})
    if normalized_query:
        clauses.append({"search_text_canonical": {"$regex": re.escape(normalized_query)}})

    if not clauses:
        return base_filter
    return {**base_filter, "$or": clauses}


async def _fetch_semantic_candidate_docs(
    query: str,
    mode: str,
    *,
    exclude_recipe_id: str = "",
    limit: int = 120,
) -> list[dict]:
    query_signals = _query_similarity_signals(query)
    semantic_filter = _semantic_candidate_filter(query_signals, mode, exclude_recipe_id=exclude_recipe_id)
    docs = await get_recipes().find(semantic_filter).limit(limit).to_list(length=limit)
    if docs:
        return docs

    raw_query = clean_human_text(query)
    if not raw_query:
        return []
    raw_pattern = re.compile(re.escape(raw_query), re.IGNORECASE)
    fallback_filter: dict = {"_id": {"$ne": exclude_recipe_id}} if exclude_recipe_id else {}
    if mode == "ingredients":
        fallback_filter["ingredients"] = {"$elemMatch": {"$regex": raw_pattern}}
    elif mode == "category":
        fallback_filter["$or"] = [
            {"category_potato": {"$regex": raw_pattern}},
            {"category": {"$regex": raw_pattern}},
        ]
    elif mode == "title":
        fallback_filter["title"] = {"$regex": raw_pattern}
    else:
        fallback_filter["$or"] = [
            {"title": {"$regex": raw_pattern}},
            {"ingredients": {"$elemMatch": {"$regex": raw_pattern}}},
            {"description": {"$regex": raw_pattern}},
            {"category_potato": {"$regex": raw_pattern}},
        ]
    return await get_recipes().find(fallback_filter).limit(limit).to_list(length=limit)


async def _rank_query_matches(
    query: str,
    mode: str,
    exclude_recipe_id: str = "",
    candidate_docs: Optional[list[dict]] = None,
) -> list[tuple[float, str, dict, str, dict]]:
    query_signals = _query_similarity_signals(query)
    if not query_signals["query_terms"] and not query_signals["normalized_query"]:
        return []

    docs = candidate_docs if candidate_docs is not None else await get_recipes().find({}).to_list(length=None)
    ranked: list[tuple[float, str, dict, str, dict]] = []
    for doc in docs:
        recipe_id = str(doc.get("_id") or "")
        if not recipe_id or recipe_id == exclude_recipe_id:
            continue
        ranking, similarity, reason = _score_query_recipe_candidate(query_signals, doc, mode)
        if ranking <= 0:
            continue
        ranked.append((ranking, recipe_id, similarity, reason, doc))

    ranked.sort(
        key=lambda item: (
            item[0],
            item[2]["shared_title_terms"],
            item[2]["shared_ingredients"],
            item[2]["same_category"],
        ),
        reverse=True,
    )
    return ranked


async def _query_recommendations_fallback(query: str, mode: str, limit: int, exclude_recipe_id: str = "") -> list[Recipe]:
    ranked = await _rank_query_matches(query, mode, exclude_recipe_id=exclude_recipe_id)
    metadata = {
        recipe_id: {
            "similarity": similarity,
            "reason": reason,
        }
        for _, recipe_id, similarity, reason, _ in ranked[:limit]
        if recipe_id
    }
    ids = [recipe_id for _, recipe_id, _, _, _ in ranked[:limit] if recipe_id]
    return await _fetch_recipes_by_ids(ids, metadata=metadata)


async def _query_recommendations_graph_first(request: Request, query: str, mode: str, limit: int) -> list[Recipe]:
    candidate_docs = await _fetch_semantic_candidate_docs(query, mode, limit=max(limit * 20, 120))
    ranked = await _rank_query_matches(query, mode, candidate_docs=candidate_docs)
    if not ranked:
        ranked = await _rank_query_matches(query, mode)
    if not ranked:
        return []

    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    if neo4j_service is None:
        metadata = {
            recipe_id: {"similarity": similarity, "reason": reason}
            for _, recipe_id, similarity, reason, _ in ranked[:limit]
            if recipe_id
        }
        ids = [recipe_id for _, recipe_id, _, _, _ in ranked[:limit] if recipe_id]
        return await _fetch_recipes_by_ids(ids, metadata=metadata)

    candidate_index = {
        recipe_id: {
            "ranking": ranking,
            "similarity": similarity,
            "reason": reason,
        }
        for ranking, recipe_id, similarity, reason, _ in ranked
        if recipe_id
    }
    candidate_ids = [recipe_id for _, recipe_id, _, _, _ in ranked[: max(limit * 6, 24)] if recipe_id]
    graph_rows = await neo4j_service.recommend_for_query(query, candidate_ids=candidate_ids, limit=max(limit * 3, 18), mode=mode)

    ordered_ids: list[str] = []
    metadata: dict[str, dict] = {}
    for row in graph_rows:
        recipe_id = str(row.get("id") or "")
        base = candidate_index.get(recipe_id)
        if not recipe_id or base is None:
            continue
        similarity = dict(base["similarity"])
        similarity["graph_score"] = round(float(row.get("ranking") or 0.0), 2)
        similarity["content_score"] = round(max(float(similarity["content_score"] or 0.0), float(row.get("ranking") or 0.0)), 2)
        similarity["shared_ingredients"] = max(similarity["shared_ingredients"], int(row.get("shared_ingredients") or 0))
        similarity["shared_title_terms"] = max(similarity["shared_title_terms"], int(row.get("shared_title_terms") or 0))
        similarity["same_category"] = similarity["same_category"] or bool(row.get("same_category") or False)
        similarity["same_difficulty"] = similarity["same_difficulty"] or bool(row.get("same_difficulty") or False)
        metadata[recipe_id] = {
            "similarity": similarity,
            "reason": "Coincide con tu consulta y Neo4j priorizo recetas relacionadas por ingredientes, categoria o titulo.",
        }
        ordered_ids.append(recipe_id)

    for _, recipe_id, similarity, reason, _ in ranked:
        if not recipe_id or recipe_id in metadata:
            continue
        metadata[recipe_id] = {"similarity": similarity, "reason": reason}
        ordered_ids.append(recipe_id)

    return await _fetch_recipes_by_ids(ordered_ids[:limit], metadata=metadata)


async def _mongo_recommendations_fallback(anchor: dict, recipe_id: str, mode: str, limit: int) -> list[Recipe]:
    anchor_signals = _recipe_similarity_signals(anchor)
    semantic = build_recipe_search_fields(anchor)
    ingredient_terms = sorted(anchor_signals["ingredient_terms"])
    title_terms = sorted(anchor_signals["title_terms"])
    category = semantic["category_canonical"]
    difficulty = semantic["difficulty_canonical"]

    base_filter: dict = {"_id": {"$ne": recipe_id}}
    clauses: list[dict] = []

    if ingredient_terms:
        clauses.append({"ingredient_terms": {"$in": ingredient_terms}})
    if title_terms:
        clauses.append({"title_terms": {"$in": title_terms}})
    if category:
        clauses.append({"category_canonical": category})
    if difficulty and mode == "hybrid":
        clauses.append({"difficulty_canonical": difficulty})

    if mode == "ingredients" and ingredient_terms:
        query = {**base_filter, "ingredient_terms": {"$in": ingredient_terms}}
    elif mode == "category" and category:
        query = {**base_filter, "category_canonical": category}
    elif mode == "title" and title_terms:
        query = {**base_filter, "title_terms": {"$in": title_terms}}
    elif clauses:
        query = {**base_filter, "$or": clauses}
    else:
        query = base_filter

    candidate_pool = max(limit * 20, 80)
    docs = await get_recipes().find(query).limit(candidate_pool).to_list(length=candidate_pool)
    ranked: list[tuple[float, str, dict, dict]] = []

    for doc in docs:
        ranking, similarity, reason = _score_recommendation_candidate(anchor_signals, doc, mode)
        if mode == "ingredients" and similarity["shared_ingredients"] <= 0:
            continue
        if mode == "category" and not similarity["same_category"]:
            continue
        if mode == "title" and similarity["shared_title_terms"] <= 0:
            continue
        if mode == "hybrid" and similarity["shared_ingredients"] <= 0 and similarity["shared_title_terms"] <= 0 and not similarity["same_category"]:
            continue
        ranked.append((ranking, str(doc.get("_id") or ""), similarity, {"reason": reason}))

    ranked.sort(
        key=lambda item: (
            item[0],
            item[2]["shared_ingredients"],
            item[2]["shared_title_terms"],
            item[2]["same_category"],
        ),
        reverse=True,
    )

    metadata = {
        recipe_key: {
            "similarity": similarity,
            "reason": extra["reason"],
        }
        for _, recipe_key, similarity, extra in ranked[:limit]
        if recipe_key
    }
    ids = [recipe_key for _, recipe_key, _, _ in ranked[:limit] if recipe_key]
    return await _fetch_recipes_by_ids(ids, metadata=metadata)


async def _record_mongo_interaction(recipe_doc: dict, user: Optional[dict], action: str) -> dict:
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
            state_update["$setOnInsert"].pop("saved", None)
            state_update["$setOnInsert"].pop("saved_at", None)
            if not already_saved:
                recipe_increments["stats.saved"] = 1
        elif action == "cook":
            already_cooked = bool(existing_state and existing_state.get("cooked"))
            state_update["$set"]["cooked"] = True
            state_update["$set"]["cooked_at"] = (existing_state.get("cooked_at") if existing_state else None) or now
            state_update["$setOnInsert"].pop("cooked", None)
            state_update["$setOnInsert"].pop("cooked_at", None)
            if not already_cooked:
                recipe_increments["stats.cooked"] = 1
        elif action == "unsave":
            was_saved = bool(existing_state and existing_state.get("saved"))
            state_update["$set"]["saved"] = False
            state_update["$set"]["saved_at"] = None
            state_update["$setOnInsert"].pop("saved", None)
            state_update["$setOnInsert"].pop("saved_at", None)
            if was_saved:
                recipe_increments["stats.saved"] = -1
        elif action == "uncook":
            was_cooked = bool(existing_state and existing_state.get("cooked"))
            state_update["$set"]["cooked"] = False
            state_update["$set"]["cooked_at"] = None
            state_update["$setOnInsert"].pop("cooked", None)
            state_update["$setOnInsert"].pop("cooked_at", None)
            if was_cooked:
                recipe_increments["stats.cooked"] = -1

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


async def _best_effort_sync_interaction(request: Request, user: Optional[dict], recipe_doc: dict, action: str) -> None:
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
    await database.backfill_recipe_search_fields()
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


@router.get("/filters")
async def filters():
    col = get_recipes()
    categories = sorted([item for item in await col.distinct("category_canonical") if item])
    difficulties = sorted([item for item in await col.distinct("difficulty_canonical") if item])
    if not categories:
        categories = sorted([item for item in await col.distinct("category_potato") if item])
    if not difficulties:
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
    category_canonical = canonicalize_category(category) if category else ""
    difficulty_canonical = canonicalize_difficulty(difficulty) if difficulty else ""

    if q and q != "*":
        candidate_docs = await _fetch_semantic_candidate_docs(q, "hybrid", limit=500)
        ranked = await _rank_query_matches(q, "hybrid", candidate_docs=candidate_docs)
        if not ranked:
            ranked = await _rank_query_matches(q, "hybrid")

        if category_canonical or difficulty_canonical:
            filtered_ranked = []
            for entry in ranked:
                doc = entry[4]
                semantic = build_recipe_search_fields(doc)
                if category_canonical and semantic["category_canonical"] != category_canonical:
                    continue
                if difficulty_canonical and semantic["difficulty_canonical"] != difficulty_canonical:
                    continue
                filtered_ranked.append(entry)
            ranked = filtered_ranked

        total = len(ranked)
        start = page * size
        page_rows = ranked[start : start + size]
        metadata = {
            recipe_id: {"similarity": similarity, "reason": reason}
            for _, recipe_id, similarity, reason, _ in page_rows
            if recipe_id
        }
        ids = [recipe_id for _, recipe_id, _, _, _ in page_rows if recipe_id]
        results = await _fetch_recipes_by_ids(ids, metadata=metadata)
        return SearchResponse(total=total, page=page, size=size, results=results)

    filters_query: dict = {}
    if category_canonical:
        filters_query["category_canonical"] = category_canonical
    elif category:
        filters_query["category_potato"] = re.compile(f"^{re.escape(category)}$", re.IGNORECASE)

    if difficulty_canonical:
        filters_query["difficulty_canonical"] = difficulty_canonical
    elif difficulty:
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


@router.get("/community/{period}")
async def community_ranking(request: Request, period: str, limit: int = Query(6, ge=1, le=50)):
    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    current_user = await current_user_from_request(request)
    exclude_user_id = current_user["user_id"] if current_user else None

    if neo4j_service is not None and current_user is not None:
        peer_rows = await neo4j_service.recommend_for_user(current_user["user_id"], limit=limit)
        peer_ids = [row["id"] for row in peer_rows]
        if peer_ids:
            results = await _fetch_recipes_by_ids(peer_ids)
            return {"period": period, "source": "neo4j_peers", "results": [item.model_dump() for item in results]}

    if neo4j_service is not None:
        rows = await neo4j_service.community_ranking(period, limit, exclude_user_id=exclude_user_id)
        ids = [row["id"] for row in rows]
        if ids:
            results = await _fetch_recipes_by_ids(ids)
            return {"period": period, "source": "neo4j", "results": [item.model_dump() for item in results]}
        if exclude_user_id:
            # Neo4j gave a definitive answer excluding the current user; the Mongo
            # fallback below can't exclude anyone (stats are global counters), so
            # falling back here would silently reintroduce the user's own activity.
            return {"period": period, "source": "neo4j", "results": []}

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


async def _recommend_from_anchor(
    request: Request,
    anchor: dict,
    recipe_id: str,
    limit: int,
    mode: str,
) -> RecommendationsResponse:
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


@router.get("/recommendations/discover", response_model=RecommendationsResponse)
async def discover_recommendations(
    request: Request,
    q: str = Query(..., min_length=2),
    limit: int = Query(6, ge=1, le=24),
    mode: str = Query("hybrid", pattern="^(hybrid|ingredients|category|title|type)$"),
):
    query = (q or "").strip()
    normalized_mode = _normalize_mode(mode)

    direct_anchor = await get_recipes().find_one({"_id": query})
    if direct_anchor:
        return await _recommend_from_anchor(request, direct_anchor, str(direct_anchor["_id"]), limit, normalized_mode)

    graph_first_results = await _query_recommendations_graph_first(request, query, normalized_mode, limit)
    if graph_first_results:
        return RecommendationsResponse(recipe_id="", mode=normalized_mode, results=graph_first_results)

    fallback_results = await _query_recommendations_fallback(query, normalized_mode, limit)
    return RecommendationsResponse(recipe_id="", mode=normalized_mode, results=fallback_results)


@router.get("/{recipe_id}", response_model=Recipe)
async def get_recipe(request: Request, recipe_id: str):
    doc = await get_recipes().find_one({"_id": recipe_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    await _sync_recipe_to_graph(request, doc)
    return Recipe(**doc_to_recipe(doc))


@router.post("/{recipe_id}/interact", response_model=InteractionResponse)
@limiter.limit("30/minute")
async def interact(request: Request, recipe_id: str, payload: InteractionRequest):
    action = (payload.action or "").strip().lower()
    if action not in {"view", "save", "cook", "unsave", "uncook"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action must be 'view', 'save', 'cook', 'unsave' or 'uncook'",
        )

    recipe_doc = await get_recipes().find_one({"_id": recipe_id})
    if not recipe_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")

    user = await current_user_from_request(request)
    updated_doc = await _record_mongo_interaction(recipe_doc, user, action)
    await _best_effort_sync_interaction(request, user, updated_doc, action)

    if user is None:
        await get_interaction_log().insert_one({
            "userId":    payload.user_id or "anonymous",
            "recipeId":  recipe_id,
            "type":      "VIEWED" if action == "view" else action.upper(),
            "timestamp": datetime.now(timezone.utc),
        })

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
    mode: str = Query("hybrid", pattern="^(hybrid|ingredients|category|title|type)$"),
):
    anchor = await get_recipes().find_one({"_id": recipe_id})
    if not anchor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    return await _recommend_from_anchor(request, anchor, recipe_id, limit, mode)

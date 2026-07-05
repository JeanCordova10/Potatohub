from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

try:
    from neo4j import AsyncGraphDatabase
except Exception:  # pragma: no cover - optional dependency
    AsyncGraphDatabase = None


class Neo4jService:
    def __init__(self, uri: str, user: str, password: str, enabled: bool = False):
        self.uri = uri
        self.user = user
        self.password = password
        self.enabled = enabled
        self.driver = None
        self._last_error = None
        self._schema_initialized = False

    async def connect(self):
        if not self.enabled or AsyncGraphDatabase is None:
            return None
        if self.driver is not None:
            return self.driver
        try:
            self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
            await self.driver.verify_connectivity()
            await self._ensure_schema()
        except Exception as exc:
            self._last_error = exc
            await self.close()
        return self.driver

    def status(self):
        if not self.enabled:
            return "disabled"
        if self.driver is not None:
            return "connected"
        if self._last_error is not None:
            return "unavailable"
        return "disconnected"

    async def close(self):
        if self.driver is not None:
            await self.driver.close()
        self.driver = None
        self._schema_initialized = False

    async def write_recipe(self, recipe: Any):
        return await self.write_recipes([recipe])

    async def write_user(self, user: dict):
        return await self.write_users([user])

    async def write_recipes(self, recipes: Iterable[Any]):
        driver = await self.connect()
        if driver is None:
            return 0

        cypher = """
        MERGE (r:Recipe {id: $id})
        SET r.title = $title,
            r.description = $description,
            r.category = $category,
            r.difficulty = $difficulty,
            r.cooking_time = $cooking_time,
            r.score = $score,
            r.image_url = $image_url,
            r.source_name = $source_name,
            r.source_url = $source_url,
            r.updated_at = datetime($updated_at)
        SET r.created_at = coalesce(r.created_at, datetime($created_at))
        WITH r, $category_key AS category_key, $difficulty_key AS difficulty_key, $ingredients AS ingredients
        OPTIONAL MATCH (r)-[existing_category:IN_CATEGORY]->(:Category)
        DELETE existing_category
        WITH r, difficulty_key, ingredients, category_key
        MERGE (category:Category {name: category_key})
        MERGE (r)-[:IN_CATEGORY]->(category)
        WITH r, difficulty_key, ingredients
        OPTIONAL MATCH (r)-[existing_difficulty:HAS_DIFFICULTY]->(:Difficulty)
        DELETE existing_difficulty
        WITH r, ingredients, difficulty_key
        MERGE (difficulty:Difficulty {name: difficulty_key})
        MERGE (r)-[:HAS_DIFFICULTY]->(difficulty)
        WITH r, ingredients
        OPTIONAL MATCH (r)-[existing_use:USES]->(:Ingredient)
        DELETE existing_use
        WITH r, CASE WHEN size(ingredients) = 0 THEN [NULL] ELSE ingredients END AS ingredients
        UNWIND ingredients AS ingredient
        WITH r, ingredient WHERE ingredient IS NOT NULL
        MERGE (i:Ingredient {name: ingredient})
        MERGE (r)-[:USES]->(i)
        """

        written = 0
        async with driver.session() as session:
            for recipe in recipes:
                payload = _recipe_payload(recipe)
                if payload is None:
                    continue
                result = await session.run(cypher, **payload)
                await result.consume()
                written += 1
        return written

    async def write_users(self, users: Iterable[dict]):
        driver = await self.connect()
        if driver is None:
            return 0

        cypher = """
        MERGE (u:User {id: $id})
        SET u.name = $name,
            u.email = $email,
            u.status = $status,
            u.role = $role,
            u.source = $source,
            u.seed_persona = $seed_persona,
            u.preferred_categories = $preferred_categories,
            u.favorite_difficulty = $favorite_difficulty,
            u.experience_level = $experience_level,
            u.household_size = $household_size,
            u.city = $city,
            u.updated_at = datetime($updated_at),
            u.last_login_at = datetime($last_login_at)
        SET u.created_at = coalesce(u.created_at, datetime($created_at))
        """

        written = 0
        async with driver.session() as session:
            for user in users:
                payload = _user_payload(user)
                if payload is None:
                    continue
                result = await session.run(cypher, **payload)
                await result.consume()
                written += 1
        return written

    async def record_interaction(self, user: dict, recipe: Any, action: str, occurred_at: datetime | None = None):
        driver = await self.connect()
        if driver is None or not user:
            return False

        occurred_at = occurred_at or datetime.now(timezone.utc)
        recipe_payload = _recipe_payload(recipe)
        if recipe_payload is not None:
            await self.write_recipe(recipe_payload)
        await self.write_user(user)

        cypher_by_action = {
            "view": """
                MATCH (u:User {id: $user_id})
                MATCH (r:Recipe {id: $recipe_id})
                MERGE (u)-[rel:VIEWED]->(r)
                SET rel.count = coalesce(rel.count, 0) + 1,
                    rel.last_at = datetime($occurred_at),
                    rel.source = $source
            """,
            "save": """
                MATCH (u:User {id: $user_id})
                MATCH (r:Recipe {id: $recipe_id})
                MERGE (u)-[rel:SAVED]->(r)
                SET rel.at = coalesce(rel.at, datetime($occurred_at)),
                    rel.last_at = datetime($occurred_at),
                    rel.source = $source
            """,
            "cook": """
                MATCH (u:User {id: $user_id})
                MATCH (r:Recipe {id: $recipe_id})
                MERGE (u)-[rel:COOKED]->(r)
                SET rel.at = coalesce(rel.at, datetime($occurred_at)),
                    rel.last_at = datetime($occurred_at),
                    rel.source = $source
            """,
        }

        cypher = cypher_by_action.get(action)
        if cypher is None:
            return False

        async with driver.session() as session:
            result = await session.run(
                cypher,
                user_id=str(user.get("user_id") or user.get("_id")),
                recipe_id=str(recipe_payload["id"] if recipe_payload else ""),
                occurred_at=occurred_at.isoformat(),
                source="mongo_truth",
            )
            await result.consume()
        return True

    async def ranking(self, period: str, limit: int):
        driver = await self.connect()
        if driver is None:
            return []

        days = {"week": 7, "month": 30, "all": 36500}.get((period or "month").lower(), 30)
        cypher = """
        MATCH (:User)-[rel:VIEWED|SAVED|COOKED]->(r:Recipe)
        WHERE coalesce(rel.last_at, rel.at) >= datetime() - duration({days: $days})
        WITH r,
             sum(
                 CASE type(rel)
                     WHEN 'VIEWED' THEN 0.5 * coalesce(rel.count, 1)
                     WHEN 'SAVED' THEN 5.0
                     WHEN 'COOKED' THEN 8.0
                     ELSE 0.0
                 END
             ) AS ranking
        RETURN r.id AS id, ranking
        ORDER BY ranking DESC, r.score DESC, r.title ASC
        LIMIT $limit
        """
        return await self._ranked_rows(cypher, days=days, limit=max(int(limit), 1))

    async def recommend_by_content(self, recipe_id: str, limit: int = 6, mode: str = "hybrid"):
        driver = await self.connect()
        if driver is None:
            return []

        mode = _normalize_mode(mode)
        cypher = """
        MATCH (anchor:Recipe {id: $recipe_id})
        MATCH (candidate:Recipe)
        WHERE candidate.id <> anchor.id
        OPTIONAL MATCH (anchor)-[:USES]->(ai:Ingredient)<-[:USES]-(candidate)
        OPTIONAL MATCH (anchor)-[:IN_CATEGORY]->(ac:Category)<-[:IN_CATEGORY]-(candidate)
        OPTIONAL MATCH (anchor)-[:HAS_DIFFICULTY]->(ad:Difficulty)<-[:HAS_DIFFICULTY]-(candidate)
        WITH candidate,
             count(DISTINCT ai) AS shared_ingredients,
             count(DISTINCT ac) > 0 AS same_category,
             count(DISTINCT ad) > 0 AS same_difficulty,
             coalesce(candidate.score, 0.0) AS candidate_score
        WITH candidate,
             shared_ingredients,
             same_category,
             same_difficulty,
             candidate_score,
             CASE $mode
                 WHEN 'ingredients' THEN (shared_ingredients * 3.0) +
                     CASE WHEN same_category THEN 1.0 ELSE 0.0 END +
                     CASE WHEN same_difficulty THEN 0.2 ELSE 0.0 END
                 WHEN 'type' THEN CASE WHEN same_category THEN 4.0 ELSE 0.0 END +
                     (shared_ingredients * 1.0) +
                     CASE WHEN same_difficulty THEN 0.5 ELSE 0.0 END
                 ELSE (shared_ingredients * 2.0) +
                     CASE WHEN same_category THEN 3.0 ELSE 0.0 END +
                     CASE WHEN same_difficulty THEN 0.4 ELSE 0.0 END
             END + candidate_score * 0.08 AS ranking
        WHERE shared_ingredients > 0 OR same_category OR same_difficulty
        RETURN candidate.id AS id,
               ranking,
               shared_ingredients,
               same_category,
               same_difficulty
        ORDER BY ranking DESC, candidate_score DESC, candidate.title ASC
        LIMIT $limit
        """
        return await self._ranked_rows(cypher, recipe_id=recipe_id, mode=mode, limit=max(int(limit), 1))

    async def recommend_from_anchor_audience(self, recipe_id: str, limit: int = 6):
        driver = await self.connect()
        if driver is None:
            return []

        cypher = """
        MATCH (anchor:Recipe {id: $recipe_id})<-[:SAVED|COOKED]-(peer:User)-[peer_rel:SAVED|COOKED]->(candidate:Recipe)
        WHERE candidate.id <> anchor.id
        WITH DISTINCT anchor, peer, peer_rel, candidate
        CALL {
            WITH anchor, candidate
            OPTIONAL MATCH (anchor)-[:USES]->(ai:Ingredient)<-[:USES]-(candidate)
            RETURN count(DISTINCT ai) AS shared_ingredients
        }
        CALL {
            WITH anchor, candidate
            OPTIONAL MATCH (anchor)-[:IN_CATEGORY]->(ac:Category)<-[:IN_CATEGORY]-(candidate)
            RETURN count(DISTINCT ac) > 0 AS same_category
        }
        WITH candidate,
             count(DISTINCT peer) AS peer_count,
             sum(CASE type(peer_rel) WHEN 'COOKED' THEN 8.0 ELSE 5.0 END) AS peer_signal,
             max(shared_ingredients) AS shared_ingredients,
             max(same_category) AS same_category
        WITH candidate,
             peer_count,
             shared_ingredients,
             same_category,
             peer_signal +
             (peer_count * 2.0) +
             (shared_ingredients * 1.2) +
             CASE WHEN same_category THEN 2.0 ELSE 0.0 END AS ranking
        RETURN candidate.id AS id,
               ranking,
               peer_count,
               shared_ingredients,
               same_category
        ORDER BY ranking DESC, peer_count DESC, candidate.score DESC, candidate.title ASC
        LIMIT $limit
        """
        return await self._ranked_rows(cypher, recipe_id=recipe_id, limit=max(int(limit), 1))

    async def recommend_for_user_from_recipe(self, user_id: str, recipe_id: str, limit: int = 6):
        driver = await self.connect()
        if driver is None or not user_id:
            return []

        cypher = """
        MATCH (anchor:Recipe {id: $recipe_id})
        MATCH (me:User {id: $user_id})
        MATCH (peer:User)
        WHERE peer.id <> me.id
        WITH anchor, me, peer,
             size([cat IN coalesce(me.preferred_categories, []) WHERE cat IN coalesce(peer.preferred_categories, [])]) AS profile_overlap,
             CASE
                 WHEN toLower(coalesce(me.favorite_difficulty, '')) <> '' AND
                      toLower(coalesce(me.favorite_difficulty, '')) = toLower(coalesce(peer.favorite_difficulty, ''))
                 THEN 1 ELSE 0
             END AS same_pref_difficulty,
             CASE
                 WHEN toLower(coalesce(me.experience_level, '')) <> '' AND
                      toLower(coalesce(me.experience_level, '')) = toLower(coalesce(peer.experience_level, ''))
                 THEN 1 ELSE 0
             END AS same_experience
        WHERE profile_overlap > 0 OR same_pref_difficulty = 1 OR same_experience = 1 OR EXISTS {
            MATCH (me)-[:SAVED|COOKED]->(:Recipe)<-[:SAVED|COOKED]-(peer)
        }
        OPTIONAL MATCH (me)-[:SAVED|COOKED]->(shared_history:Recipe)<-[:SAVED|COOKED]-(peer)
        WITH anchor, me, peer, profile_overlap, same_pref_difficulty, same_experience,
             count(DISTINCT shared_history) AS shared_history_count
        MATCH (peer)-[peer_rel:SAVED|COOKED]->(candidate:Recipe)
        WHERE candidate.id <> anchor.id
          AND NOT EXISTS { MATCH (me)-[:COOKED]->(candidate) }
        WITH DISTINCT anchor, candidate, peer, peer_rel, profile_overlap, same_pref_difficulty, same_experience, shared_history_count
        CALL {
            WITH anchor, candidate
            OPTIONAL MATCH (anchor)-[:USES]->(ai:Ingredient)<-[:USES]-(candidate)
            RETURN count(DISTINCT ai) AS shared_ingredients
        }
        CALL {
            WITH anchor, candidate
            OPTIONAL MATCH (anchor)-[:IN_CATEGORY]->(ac:Category)<-[:IN_CATEGORY]-(candidate)
            RETURN count(DISTINCT ac) > 0 AS same_category
        }
        CALL {
            WITH anchor, candidate
            OPTIONAL MATCH (anchor)-[:HAS_DIFFICULTY]->(ad:Difficulty)<-[:HAS_DIFFICULTY]-(candidate)
            RETURN count(DISTINCT ad) > 0 AS same_difficulty
        }
        WITH candidate,
             count(DISTINCT peer) AS peer_count,
             sum(CASE type(peer_rel) WHEN 'COOKED' THEN 8.0 ELSE 5.0 END) AS peer_signal,
             max(profile_overlap) AS profile_overlap,
             max(shared_history_count) AS shared_history_count,
             max(same_pref_difficulty) AS same_pref_difficulty,
             max(same_experience) AS same_experience,
             max(shared_ingredients) AS shared_ingredients,
             max(same_category) AS same_category,
             max(same_difficulty) AS same_difficulty
        WITH candidate,
             peer_count,
             profile_overlap,
             shared_history_count,
             shared_ingredients,
             same_category,
             same_difficulty,
             peer_signal +
             (peer_count * 2.5) +
             (profile_overlap * 1.5) +
             (shared_history_count * 2.0) +
             (same_pref_difficulty * 1.0) +
             (same_experience * 0.75) +
             (shared_ingredients * 1.25) +
             CASE WHEN same_category THEN 2.5 ELSE 0.0 END +
             CASE WHEN same_difficulty THEN 0.5 ELSE 0.0 END AS ranking
        RETURN candidate.id AS id,
               ranking,
               peer_count,
               profile_overlap,
               shared_ingredients,
               same_category,
               same_difficulty
        ORDER BY ranking DESC, peer_count DESC, candidate.score DESC, candidate.title ASC
        LIMIT $limit
        """
        return await self._ranked_rows(
            cypher,
            user_id=user_id,
            recipe_id=recipe_id,
            limit=max(int(limit), 1),
        )

    async def recommend_for_user(self, user_id: str, limit: int = 6):
        driver = await self.connect()
        if driver is None or not user_id:
            return []

        cypher = """
        MATCH (me:User {id: $user_id})
        MATCH (peer:User)
        WHERE peer.id <> me.id
        WITH me, peer,
             size([cat IN coalesce(me.preferred_categories, []) WHERE cat IN coalesce(peer.preferred_categories, [])]) AS profile_overlap,
             CASE
                 WHEN toLower(coalesce(me.favorite_difficulty, '')) <> '' AND
                      toLower(coalesce(me.favorite_difficulty, '')) = toLower(coalesce(peer.favorite_difficulty, ''))
                 THEN 1 ELSE 0
             END AS same_pref_difficulty,
             CASE
                 WHEN toLower(coalesce(me.experience_level, '')) <> '' AND
                      toLower(coalesce(me.experience_level, '')) = toLower(coalesce(peer.experience_level, ''))
                 THEN 1 ELSE 0
             END AS same_experience
        WHERE profile_overlap > 0 OR same_pref_difficulty = 1 OR same_experience = 1 OR EXISTS {
            MATCH (me)-[:SAVED|COOKED]->(:Recipe)<-[:SAVED|COOKED]-(peer)
        }
        OPTIONAL MATCH (me)-[:SAVED|COOKED]->(shared_history:Recipe)<-[:SAVED|COOKED]-(peer)
        WITH me, peer, profile_overlap, same_pref_difficulty, same_experience,
             count(DISTINCT shared_history) AS shared_history_count
        MATCH (peer)-[peer_rel:SAVED|COOKED]->(candidate:Recipe)
        WHERE NOT EXISTS { MATCH (me)-[:VIEWED|SAVED|COOKED]->(candidate) }
        WITH me, candidate,
             count(DISTINCT peer) AS peer_count,
             sum(CASE type(peer_rel) WHEN 'COOKED' THEN 8.0 ELSE 5.0 END) AS peer_signal,
             max(profile_overlap) AS profile_overlap,
             max(shared_history_count) AS shared_history_count,
             max(same_pref_difficulty) AS same_pref_difficulty,
             max(same_experience) AS same_experience
        CALL {
            WITH candidate
            OPTIONAL MATCH (candidate)-[:IN_CATEGORY]->(category:Category)
            RETURN collect(DISTINCT category.name) AS candidate_categories
        }
        CALL {
            WITH candidate
            OPTIONAL MATCH (candidate)-[:HAS_DIFFICULTY]->(difficulty:Difficulty)
            RETURN head(collect(DISTINCT difficulty.name)) AS candidate_difficulty
        }
        WITH candidate,
             peer_count,
             profile_overlap,
             shared_history_count,
             peer_signal,
             size([cat IN coalesce(me.preferred_categories, []) WHERE cat IN candidate_categories]) AS preferred_category_hits,
             CASE
                 WHEN toLower(coalesce(me.favorite_difficulty, '')) <> '' AND
                      toLower(coalesce(me.favorite_difficulty, '')) = toLower(coalesce(candidate_difficulty, ''))
                 THEN 1 ELSE 0
             END AS preferred_difficulty_hit,
             same_pref_difficulty,
             same_experience
        WITH candidate,
             peer_count,
             profile_overlap,
             preferred_category_hits,
             peer_signal +
             (peer_count * 2.2) +
             (profile_overlap * 1.5) +
             (shared_history_count * 2.0) +
             (preferred_category_hits * 1.25) +
             (preferred_difficulty_hit * 0.75) +
             (same_pref_difficulty * 0.75) +
             (same_experience * 0.5) +
             coalesce(candidate.score, 0.0) * 0.08 AS ranking
        RETURN candidate.id AS id,
               ranking,
               peer_count,
               profile_overlap,
               preferred_category_hits AS shared_ingredients
        ORDER BY ranking DESC, peer_count DESC, candidate.score DESC, candidate.title ASC
        LIMIT $limit
        """
        return await self._ranked_rows(cypher, user_id=user_id, limit=max(int(limit), 1))

    async def _ensure_schema(self):
        if self.driver is None or self._schema_initialized:
            return

        statements = [
            "CREATE CONSTRAINT recipe_id IF NOT EXISTS FOR (r:Recipe) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT ingredient_name IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.name IS UNIQUE",
            "CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT difficulty_name IF NOT EXISTS FOR (d:Difficulty) REQUIRE d.name IS UNIQUE",
        ]
        async with self.driver.session() as session:
            for statement in statements:
                await session.run(statement)
        self._schema_initialized = True

    async def _ranked_rows(self, cypher: str, **params):
        driver = await self.connect()
        if driver is None:
            return []
        async with driver.session() as session:
            result = await session.run(cypher, **params)
            return await result.data()


def _normalize_mode(mode: str) -> str:
    normalized = (mode or "hybrid").strip().lower()
    if normalized not in {"hybrid", "ingredients", "type"}:
        return "hybrid"
    return normalized


def _recipe_payload(recipe: Any) -> dict | None:
    if recipe is None:
        return None
    if hasattr(recipe, "model_dump"):
        payload = recipe.model_dump(mode="json")
    elif isinstance(recipe, dict):
        payload = dict(recipe)
    else:
        return None

    recipe_id = payload.get("id") or payload.get("_id")
    if not recipe_id:
        return None

    updated_at = payload.get("updated_at") or payload.get("created_at") or datetime.now(timezone.utc)
    created_at = payload.get("created_at") or updated_at
    ingredients = [str(item).strip().lower() for item in payload.get("ingredients") or [] if str(item).strip()]

    return {
        "id": str(recipe_id),
        "title": str(payload.get("title") or ""),
        "description": str(payload.get("description") or ""),
        "category": str(payload.get("category") or payload.get("category_potato") or "GENERAL"),
        "difficulty": str(payload.get("difficulty") or "unknown"),
        "cooking_time": int(payload.get("cooking_time") or 0),
        "score": float(payload.get("score") or 0.0),
        "image_url": payload.get("image_url"),
        "source_name": str(payload.get("source_name") or payload.get("source") or "cookpad_pe"),
        "source_url": str(payload.get("source_url") or ""),
        "category_key": str(payload.get("category") or payload.get("category_potato") or "GENERAL").strip() or "GENERAL",
        "difficulty_key": str(payload.get("difficulty") or "unknown").strip().lower() or "unknown",
        "ingredients": ingredients,
        "created_at": _isoformat(created_at),
        "updated_at": _isoformat(updated_at),
    }


def _user_payload(user: dict | None) -> dict | None:
    if not user:
        return None
    user_id = user.get("user_id") or user.get("_id")
    email = user.get("email") or user_id
    if not user_id:
        return None

    profile = user.get("profile") or {}
    preferences = user.get("preferences") or {}
    preferred_categories = profile.get("preferred_categories") or preferences.get("preferred_categories") or []

    created_at = user.get("created_at") or datetime.now(timezone.utc)
    updated_at = user.get("updated_at") or created_at
    last_login_at = user.get("last_login_at") or updated_at

    return {
        "id": str(user_id),
        "email": str(email),
        "name": str(user.get("name") or "PotatoHub User"),
        "status": str(user.get("status") or "active"),
        "role": str(user.get("role") or "user"),
        "source": str(user.get("source") or "mongo_truth"),
        "seed_persona": user.get("seed_persona"),
        "preferred_categories": [str(item).strip().upper() for item in preferred_categories if str(item).strip()],
        "favorite_difficulty": str(profile.get("favorite_difficulty") or preferences.get("difficulty") or ""),
        "experience_level": str(profile.get("experience_level") or ""),
        "household_size": int(profile.get("household_size") or 0),
        "city": str(profile.get("city") or ""),
        "created_at": _isoformat(created_at),
        "updated_at": _isoformat(updated_at),
        "last_login_at": _isoformat(last_login_at),
    }


def _isoformat(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)

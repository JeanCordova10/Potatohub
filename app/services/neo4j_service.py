from __future__ import annotations

from typing import Any, Iterable, List

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

    async def _ensure_schema(self):
        if self.driver is None or self._schema_initialized:
            return

        statements = [
            "CREATE CONSTRAINT recipe_id IF NOT EXISTS FOR (r:Recipe) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT ingredient_name IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.name IS UNIQUE",
            "CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT difficulty_name IF NOT EXISTS FOR (d:Difficulty) REQUIRE d.name IS UNIQUE",
        ]
        async with self.driver.session() as session:
            for statement in statements:
                await session.run(statement)
        self._schema_initialized = True

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
            r.source_url = $source_url
        WITH r
        OPTIONAL MATCH (r)-[existing_category:IN_CATEGORY]->(:Category)
        DELETE existing_category
        WITH r
        MERGE (category:Category {name: $category_key})
        MERGE (r)-[:IN_CATEGORY]->(category)
        WITH r
        OPTIONAL MATCH (r)-[existing_difficulty:HAS_DIFFICULTY]->(:Difficulty)
        DELETE existing_difficulty
        WITH r
        MERGE (difficulty:Difficulty {name: $difficulty_key})
        MERGE (r)-[:HAS_DIFFICULTY]->(difficulty)
        WITH r
        UNWIND $ingredients AS ingredient
        MERGE (i:Ingredient {name: ingredient})
        MERGE (r)-[:USES]->(i)
        """
        written = 0
        async with driver.session() as session:
            for recipe in recipes:
                if hasattr(recipe, "model_dump"):
                    payload = recipe.model_dump(mode="json")
                elif isinstance(recipe, dict):
                    payload = dict(recipe)
                else:
                    continue
                ingredients = payload.get("ingredients") or []
                payload["category_key"] = (payload.get("category") or "General").strip() or "General"
                payload["difficulty_key"] = (payload.get("difficulty") or "unknown").strip().lower() or "unknown"
                payload["ingredients"] = [str(item).strip() for item in ingredients if str(item).strip()]
                result = await session.run(cypher, **payload)
                await result.consume()
                written += 1
        return written

    async def recommendations(self, recipe_id: str, limit: int = 6, mode: str = "hybrid"):
        driver = await self.connect()
        if driver is None:
            return []

        mode = (mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "ingredients", "type"}:
            mode = "hybrid"

        cypher = """
        MATCH (anchor:Recipe {id: $recipe_id})
        MATCH (candidate:Recipe)
        WHERE candidate.id <> anchor.id
        OPTIONAL MATCH (anchor)-[:USES]->(ai:Ingredient)<-[:USES]-(candidate)
        OPTIONAL MATCH (anchor)-[:IN_CATEGORY]->(ac:Category)<-[:IN_CATEGORY]-(candidate)
        OPTIONAL MATCH (anchor)-[:HAS_DIFFICULTY]->(ad:Difficulty)<-[:HAS_DIFFICULTY]-(candidate)
        WITH candidate,
             count(DISTINCT ai) AS shared_ingredients,
             count(DISTINCT ac) AS same_category_count,
             count(DISTINCT ad) AS same_difficulty_count
        WITH candidate,
             shared_ingredients,
             same_category_count > 0 AS same_category,
             same_difficulty_count > 0 AS same_difficulty,
             CASE $mode
                 WHEN 'ingredients' THEN (shared_ingredients * 3.0) +
                     CASE WHEN same_category_count > 0 THEN 1.0 ELSE 0.0 END +
                     CASE WHEN same_difficulty_count > 0 THEN 0.2 ELSE 0.0 END
                 WHEN 'type' THEN CASE WHEN same_category_count > 0 THEN 4.0 ELSE 0.0 END +
                     (shared_ingredients * 1.25) +
                     CASE WHEN same_difficulty_count > 0 THEN 0.5 ELSE 0.0 END
                 ELSE (shared_ingredients * 2.0) +
                     CASE WHEN same_category_count > 0 THEN 3.0 ELSE 0.0 END +
                     CASE WHEN same_difficulty_count > 0 THEN 0.4 ELSE 0.0 END
             END + coalesce(candidate.score, 0) * 0.1 AS ranking
        WHERE shared_ingredients > 0 OR same_category
        RETURN candidate {
            .id,
            .title,
            .description,
            .category,
            .difficulty,
            .cooking_time,
            .image_url,
            .source_name,
            .source_url,
            .score
        } AS recipe,
        shared_ingredients,
        same_category,
        same_difficulty,
        ranking
        ORDER BY ranking DESC, candidate.score DESC, candidate.title ASC
        LIMIT $limit
        """

        async with driver.session() as session:
            result = await session.run(cypher, recipe_id=recipe_id, limit=max(int(limit), 1), mode=mode)
            rows = await result.data()

        recommendations: List[dict] = []
        for row in rows:
            recipe = row.get("recipe")
            if not recipe:
                continue
            recipe["similarity"] = {
                "shared_ingredients": row.get("shared_ingredients", 0),
                "same_category": row.get("same_category", False),
                "same_difficulty": row.get("same_difficulty", False),
                "ranking": row.get("ranking", 0),
            }
            recommendations.append(recipe)
        return recommendations

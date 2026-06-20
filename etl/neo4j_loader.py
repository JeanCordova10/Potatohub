from __future__ import annotations

from typing import Any, Iterable

from app.services.neo4j_service import Neo4jService


async def load_recipes_to_neo4j(recipes: Iterable[Any], neo4j_service: Neo4jService):
    if neo4j_service is None:
        return 0
    return await neo4j_service.write_recipes(recipes)

from __future__ import annotations

from typing import Iterable, List, Optional

from app.config import get_settings
from app.database import RecipeRepository
from app.models import Recipe
from app.services.mongo_service import MongoService
from app.services.neo4j_service import Neo4jService
from app.services.redis_service import RedisService
from etl.cookpad_scraper import scrape_cookpad
from etl.neo4j_loader import load_recipes_to_neo4j
from etl.recetasgratis_scraper import scrape_recetasgratis
from etl.transformer import build_demo_recipes, normalize_scraped_recipe


class SyncWorker:
    def __init__(
        self,
        repository: RecipeRepository,
        settings=None,
        mongo_service: Optional[MongoService] = None,
        redis_service: Optional[RedisService] = None,
        neo4j_service: Optional[Neo4jService] = None,
    ):
        self.settings = settings or get_settings()
        self.repository = repository
        self.mongo_service = mongo_service
        self.redis_service = redis_service
        self.neo4j_service = neo4j_service
        self.last_summary = None

    async def bootstrap(self):
        await self.repository.ensure_loaded()
        if await self.repository.count() > 0:
            return {"success": True, "stored": await self.repository.count(), "sources": [], "scraped": 0, "fallback_used": False}
        if not self.settings.auto_seed_on_startup:
            return {"success": True, "stored": 0, "sources": [], "scraped": 0, "fallback_used": False}
        summary = await self.refresh_catalog()
        if summary["stored"] == 0:
            demo = [normalize_scraped_recipe(item) for item in build_demo_recipes()]
            await self.repository.seed(demo, preserve_stats=False)
            summary = {
                "success": True,
                "stored": await self.repository.count(),
                "sources": ["demo"],
                "scraped": 0,
                "fallback_used": True,
            }
        return summary

    async def refresh_catalog(self, sources: Optional[Iterable[str]] = None, preserve_stats: bool = True):
        source_names = list(sources) if sources is not None else list(self.settings.scrape_sources)
        scraped = []
        used_sources = []
        fallback_used = False

        for source_name in source_names:
            if source_name == "recetasgratis":
                items = await scrape_recetasgratis(
                    terms=self.settings.recetasgratis_terms,
                    limit=self.settings.scrape_limit_per_source,
                    user_agent=self.settings.user_agent,
                    timeout_seconds=self.settings.request_timeout_seconds,
                )
            elif source_name == "cookpad":
                items = await scrape_cookpad(
                    terms=self.settings.cookpad_terms,
                    limit=self.settings.scrape_limit_per_source,
                    user_agent=self.settings.user_agent,
                    timeout_seconds=self.settings.request_timeout_seconds,
                )
            else:
                items = []

            if items:
                scraped.extend(items)
                used_sources.append(source_name)

        if not scraped:
            fallback_used = True
            scraped = build_demo_recipes()
            used_sources = ["demo"]

        normalized = [normalize_scraped_recipe(item) for item in scraped]
        if preserve_stats:
            await self.repository.seed(normalized, preserve_stats=True)
        else:
            await self.repository.replace_all(normalized)

        if self.settings.enable_mongo_sync and self.mongo_service is not None:
            await self.mongo_service.replace_recipes(normalized)

        if self.settings.enable_redis_cache and self.redis_service is not None:
            await self.redis_service.cache_json(
                "potatohub:catalog:summary",
                {"count": len(normalized), "sources": used_sources},
                ttl_seconds=300,
            )

        if self.settings.enable_neo4j_sync and self.neo4j_service is not None:
            await load_recipes_to_neo4j(normalized, self.neo4j_service)

        summary = {
            "success": True,
            "stored": await self.repository.count(),
            "sources": used_sources,
            "scraped": len(scraped),
            "fallback_used": fallback_used,
        }
        self.last_summary = summary
        return summary

    async def close(self):
        if self.mongo_service is not None:
            await self.mongo_service.close()
        if self.redis_service is not None:
            await self.redis_service.close()
        if self.neo4j_service is not None:
            await self.neo4j_service.close()

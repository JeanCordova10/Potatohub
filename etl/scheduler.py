from __future__ import annotations

import asyncio
from typing import Optional

from app.database import RecipeRepository
from app.services.mongo_service import MongoService
from app.services.neo4j_service import Neo4jService
from app.services.redis_service import RedisService
from app.services.sync_worker import SyncWorker

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:  # pragma: no cover - optional dependency
    AsyncIOScheduler = None


def build_scheduler(worker: SyncWorker, interval_minutes: int = 360):
    if AsyncIOScheduler is None:
        return None
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        worker.refresh_catalog,
        "interval",
        minutes=interval_minutes,
        id="potatohub_catalog_refresh",
        replace_existing=True,
    )
    return scheduler


async def run_one_shot():
    repository = RecipeRepository()
    worker = SyncWorker(repository)
    await worker.bootstrap()
    return await repository.count()


async def main():
    count = await run_one_shot()
    print("Catalog ready with %s recipes." % count)


if __name__ == "__main__":
    asyncio.run(main())

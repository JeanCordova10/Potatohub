from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import RecipeRepository
from app.models import HealthResponse
from app.routers import interact, ranking, search
from app.services.mongo_service import MongoService
from app.services.neo4j_service import Neo4jService
from app.services.redis_service import RedisService
from app.services.sync_worker import SyncWorker


settings = get_settings()
repository = RecipeRepository(settings.recipe_store_path)
mongo_service = MongoService(settings.mongo_uri, settings.mongo_db, enabled=settings.enable_mongo_sync)
redis_service = RedisService(settings.redis_url, enabled=settings.enable_redis_cache)
neo4j_service = Neo4jService(
    settings.neo4j_uri,
    settings.neo4j_user,
    settings.neo4j_password,
    enabled=settings.enable_neo4j_sync,
)
sync_worker = SyncWorker(
    repository=repository,
    settings=settings,
    mongo_service=mongo_service,
    redis_service=redis_service,
    neo4j_service=neo4j_service,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = settings
    app.state.repository = repository
    app.state.mongo_service = mongo_service
    app.state.redis_service = redis_service
    app.state.neo4j_service = neo4j_service
    app.state.sync_worker = sync_worker

    await repository.load()
    await sync_worker.bootstrap()

    yield

    await sync_worker.close()


app = FastAPI(
    title=settings.app_name,
    description=settings.description,
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(settings.frontend_dir)), name="static")

app.include_router(search.router, prefix=settings.api_prefix)
app.include_router(ranking.router, prefix=settings.api_prefix)
app.include_router(interact.router, prefix=settings.api_prefix)


@app.get("/")
async def serve_frontend():
    return FileResponse(str(settings.frontend_dir / "index.html"))


@app.get("/health", response_model=HealthResponse)
async def health():
    recipe_count = await repository.count()
    return HealthResponse(
        status="ok",
        recipes=recipe_count,
        storage_file=str(settings.recipe_store_path),
        mongo_enabled=settings.enable_mongo_sync,
        redis_enabled=settings.enable_redis_cache,
        neo4j_enabled=settings.enable_neo4j_sync,
        mongo_status=mongo_service.status(),
        redis_status=redis_service.status(),
        neo4j_status=neo4j_service.status(),
    )

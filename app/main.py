import asyncio
import os
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import database
from app.database import doc_to_recipe, user_to_public
from app.routers import auth, recipes, users
from app.services.neo4j_service import Neo4jService

load_dotenv()


async def _sync_graph_projection(service: Neo4jService) -> None:
    if service.status() == "unavailable":
        return

    recipe_docs = await database.get_recipes().find({}).to_list(length=None)
    if recipe_docs:
        await service.write_recipes([doc_to_recipe(doc) for doc in recipe_docs])

    user_docs = await database.get_users().find({"deleted_at": None, "status": "active"}).to_list(length=None)
    if user_docs:
        await service.write_users(user_docs)


async def _sync_graph_projection_safe(service: Neo4jService) -> None:
    try:
        await _sync_graph_projection(service)
    except Exception:
        return


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_client()
    await database.ensure_indexes()
    demo_user = await database.ensure_demo_user()

    neo4j_service = Neo4jService(
        uri=os.getenv("NEO4J_URI_LOCAL", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "potatohub123"),
        enabled=True,
    )
    await neo4j_service.connect()
    await neo4j_service.write_user(demo_user)

    app.state.neo4j_service = neo4j_service
    app.state.demo_user = user_to_public(demo_user)
    projection_task = asyncio.create_task(_sync_graph_projection_safe(neo4j_service))
    app.state.graph_projection_task = projection_task

    yield

    if projection_task and not projection_task.done():
        projection_task.cancel()
        with suppress(asyncio.CancelledError):
            await projection_task
    await neo4j_service.close()
    database.close_client()


app = FastAPI(
    title="PotatoHub API",
    description="Plataforma NoSQL de Recetas de Papa - PUCP 2026-1",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/health", tags=["system"])
async def health():
    recipes_count = await database.get_recipes().count_documents({})
    users_count = await database.get_users().count_documents({"deleted_at": None})
    neo4j_service = getattr(app.state, "neo4j_service", None)
    graph_status = neo4j_service.status() if neo4j_service else "unknown"
    return {
        "status": "ok",
        "service": "PotatoHub API",
        "recipes": recipes_count,
        "users": users_count,
        "neo4j": graph_status,
    }


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("frontend/index.html")

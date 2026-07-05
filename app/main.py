from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import database, neo4j_db
from app.limiter import limiter
from app.routers import recipes

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_client()
    await database.init_indexes()
    await neo4j_db.init_driver()
    await neo4j_db.ensure_constraints()
    yield
    database.close_client()
    await neo4j_db.close_driver()


app = FastAPI(
    title="PotatoHub API",
    description="Plataforma NoSQL de Recetas de Papa — PUCP 2026-1",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/health", tags=["sistema"])
async def health():
    count = await database.get_recipes().count_documents({})
    return {"status": "ok", "servicio": "PotatoHub API", "recipes": count}


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("frontend/index.html")

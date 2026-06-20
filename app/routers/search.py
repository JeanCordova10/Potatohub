from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import CatalogFiltersResponse, Recipe, RefreshResponse, SearchResponse


router = APIRouter(prefix="/recipes", tags=["recipes"])


def _repository(request: Request):
    return request.app.state.repository


def _sync_worker(request: Request):
    return request.app.state.sync_worker


@router.get("/filters", response_model=CatalogFiltersResponse)
async def catalog_filters(request: Request):
    filters = await _repository(request).available_filters()
    return CatalogFiltersResponse(**filters)


@router.get("/search", response_model=SearchResponse)
async def search_recipes(
    request: Request,
    q: str = Query("*", description="Search term or * for the full catalog"),
    category: str = Query("", description="Optional category filter"),
    difficulty: str = Query("", description="Optional difficulty filter"),
    page: int = Query(0, ge=0),
    size: int = Query(6, ge=1, le=50),
):
    total, results = await _repository(request).search(
        query=q,
        category=category,
        difficulty=difficulty,
        page=page,
        size=size,
    )
    return SearchResponse(total=total, page=page, size=size, results=results)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_catalog(request: Request):
    summary = await _sync_worker(request).refresh_catalog()
    return RefreshResponse(**summary)


@router.get("/{recipe_id}", response_model=Recipe)
async def get_recipe(request: Request, recipe_id: str):
    recipe = await _repository(request).get(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe

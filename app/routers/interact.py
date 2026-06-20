from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import InteractionRequest, InteractionResponse


router = APIRouter(prefix="/recipes", tags=["interactions"])


def _repository(request: Request):
    return request.app.state.repository


def _neo4j_service(request: Request):
    return request.app.state.neo4j_service


@router.post("/{recipe_id}/interact", response_model=InteractionResponse)
async def interact(request: Request, recipe_id: str, payload: InteractionRequest):
    try:
        recipe = await _repository(request).record_interaction(recipe_id, payload.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return InteractionResponse(
        success=True,
        recipe_id=recipe.id,
        action=payload.action,
        views=recipe.stats.views,
        saved=recipe.stats.saved,
        score=recipe.score,
    )


@router.get("/{recipe_id}/recommendations")
async def recommendations(
    request: Request,
    recipe_id: str,
    limit: int = Query(6, ge=1, le=24),
    mode: str = Query("hybrid", pattern="^(hybrid|ingredients|type)$"),
):
    results = []
    service = _neo4j_service(request)
    if service is not None:
        try:
            results = await service.recommendations(recipe_id, limit=limit, mode=mode)
        except Exception:
            results = []

    if not results:
        results = await _repository(request).recommendations(recipe_id, limit=limit, mode=mode)

    if not results:
        raise HTTPException(status_code=404, detail="Recipe not found or no recommendations available")
    return {"recipe_id": recipe_id, "mode": mode, "results": results}

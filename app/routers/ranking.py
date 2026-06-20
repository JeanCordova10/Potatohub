from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.models import RankingResponse


router = APIRouter(prefix="/recipes", tags=["ranking"])


def _repository(request: Request):
    return request.app.state.repository


@router.get("/ranking/{period}", response_model=RankingResponse)
async def ranking(request: Request, period: str, limit: int = Query(10, ge=1, le=50)):
    results = await _repository(request).ranking(period=period, limit=limit)
    return RankingResponse(period=period, results=results)

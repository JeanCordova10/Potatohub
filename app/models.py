from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class RecipeStats(BaseModel):
    views: int = 0
    saved: int = 0


class Recipe(BaseModel):
    id: str
    title: str
    description: str = ""
    category: str = ""
    difficulty: str = ""
    cooking_time: int = 0
    ingredients: list[str] = []
    instructions: list[str] = []
    image_url: Optional[str] = None
    source_name: str = "cookpad_pe"
    source_url: str = ""
    tags: list[str] = []
    stats: RecipeStats = RecipeStats()
    score: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    results: list[Recipe]


class InteractionRequest(BaseModel):
    action: str


class InteractionResponse(BaseModel):
    success: bool
    recipe_id: str
    action: str
    views: int
    saved: int
    score: float


class RecommendationsResponse(BaseModel):
    recipe_id: str
    mode: str
    results: list[Recipe]


class RefreshResponse(BaseModel):
    success: bool
    stored: int
    sources: list[str]
    scraped: int
    fallback_used: bool

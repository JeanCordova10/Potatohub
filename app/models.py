from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utcnow():
    return datetime.now(timezone.utc)


def normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return " ".join(value.split())
    return " ".join(str(value).split())


def normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = []
        for item in value:
            if isinstance(item, dict):
                candidate = item.get("text") or item.get("name") or item.get("@value") or item.get("value")
                if candidate:
                    items.append(str(candidate))
            else:
                items.append(str(item))
    else:
        items = [str(value)]

    cleaned: List[str] = []
    seen = set()
    for item in items:
        text = " ".join(str(item).split())
        if not text:
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


class RecipeStats(BaseModel):
    views: int = 0
    saved: int = 0


class Recipe(BaseModel):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)

    id: str
    title: str
    description: str = ""
    category: str = ""
    difficulty: str = ""
    cooking_time: int = 0
    ingredients: List[str] = Field(default_factory=list)
    instructions: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    source_name: str = "demo"
    source_url: str = ""
    tags: List[str] = Field(default_factory=list)
    stats: RecipeStats = Field(default_factory=RecipeStats)
    score: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator(
        "id",
        "title",
        "description",
        "category",
        "difficulty",
        "source_name",
        "source_url",
        "image_url",
        mode="before",
    )
    def _normalize_text_fields(cls, value):
        return normalize_text(value, "")

    @field_validator("cooking_time", mode="before")
    def _normalize_time(cls, value):
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    @field_validator("ingredients", "instructions", "tags", mode="before")
    def _normalize_list_fields(cls, value):
        return normalize_list(value)


class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    results: List[Recipe]


class FilterOption(BaseModel):
    value: str
    label: str
    count: int = 0


class CatalogFiltersResponse(BaseModel):
    categories: List[FilterOption]
    difficulties: List[FilterOption]
    sources: List[FilterOption]


class RankingResponse(BaseModel):
    period: str
    results: List[Recipe]


class InteractionRequest(BaseModel):
    action: str


class InteractionResponse(BaseModel):
    success: bool
    recipe_id: str
    action: str
    views: int
    saved: int
    score: float


class RefreshResponse(BaseModel):
    success: bool
    stored: int
    sources: List[str]
    scraped: int
    fallback_used: bool


class HealthResponse(BaseModel):
    status: str
    recipes: int
    storage_file: str
    mongo_enabled: bool
    redis_enabled: bool
    neo4j_enabled: bool
    mongo_status: str = "disabled"
    redis_status: str = "disabled"
    neo4j_status: str = "disabled"

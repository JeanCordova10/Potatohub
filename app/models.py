from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RecipeStats(BaseModel):
    views: int = 0
    saved: int = 0
    cooked: int = 0


class RecommendationSimilarity(BaseModel):
    graph_score: float = 0.0
    content_score: float = 0.0
    audience_score: float = 0.0
    personalized_score: float = 0.0
    shared_ingredients: int = 0
    shared_title_terms: int = 0
    peer_count: int = 0
    profile_overlap: int = 0
    same_category: bool = False
    same_difficulty: bool = False


class Recipe(BaseModel):
    id: str
    title: str
    description: str = ""
    category: str = ""
    difficulty: str = ""
    cooking_time: int = 0
    ingredients: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    source_name: str = "cookpad_pe"
    source_url: str = ""
    tags: list[str] = Field(default_factory=list)
    stats: RecipeStats = Field(default_factory=RecipeStats)
    score: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    similarity: Optional[RecommendationSimilarity] = None
    recommendation_reason: str = ""


class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    results: list[Recipe]


class InteractionRequest(BaseModel):
    action: str
    user_id: str = ""


class InteractionResponse(BaseModel):
    success: bool
    recipe_id: str
    action: str
    user_id: str = "anonymous"
    views: int
    saved: int
    cooked: int = 0
    score: float


class RecommendationsResponse(BaseModel):
    recipe_id: str
    mode: str
    results: list[Recipe]


class UserRecommendationsResponse(BaseModel):
    user_id: str
    results: list[Recipe]


class UserLibraryResponse(BaseModel):
    user_id: str
    saved: list[Recipe]
    cooked: list[Recipe]


class RefreshResponse(BaseModel):
    success: bool
    stored: int
    sources: list[str]
    scraped: int
    fallback_used: bool


class UserProfile(BaseModel):
    experience_level: str = ""
    household_size: int = 0
    city: str = ""
    preferred_categories: list[str] = Field(default_factory=list)
    favorite_difficulty: str = ""


class UserPreferences(BaseModel):
    preferred_categories: list[str] = Field(default_factory=list)
    difficulty: str = ""
    newsletter: bool = False
    cooking_days: list[str] = Field(default_factory=list)


class PublicUser(BaseModel):
    id: str
    email: str
    name: str
    status: str = "active"
    role: str = "user"
    source: str = ""
    profile: UserProfile = Field(default_factory=UserProfile)
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthSessionResponse(BaseModel):
    token: str
    user: PublicUser

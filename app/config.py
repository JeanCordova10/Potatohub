from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PotatoHub API"
    version: str = "1.0.0"
    description: str = "Plataforma NoSQL de recetas de papa - PUCP 2026-1"
    api_prefix: str = "/api"

    frontend_dir: Path = Field(default_factory=lambda: BASE_DIR / "frontend")
    data_dir: Path = Field(default_factory=lambda: BASE_DIR / "data")
    recipe_store_path: Path = Field(default_factory=lambda: BASE_DIR / "data" / "recipes.json")

    scrape_sources_csv: str = "recetasgratis,cookpad"
    bootstrap_terms_csv: str = "papa,patata,pure de papa,papas bravas"
    recetasgratis_terms_csv: str = "papa,patata,pollo,ensalada,postre,arroz"
    cookpad_terms_csv: str = "potato,lasagna,chicken soup,pancakes,mashed potato,baked potato"
    scrape_limit_per_source: int = 8
    default_page_size: int = 6
    request_timeout_seconds: float = 15.0
    user_agent: str = "PotatoHubBot/1.0"

    auto_seed_on_startup: bool = True
    enable_mongo_sync: bool = False
    enable_redis_cache: bool = False
    enable_neo4j_sync: bool = False

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "potatohub"
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "potatohub123"

    @property
    def scrape_sources(self):
        return [item.strip() for item in self.scrape_sources_csv.split(",") if item.strip()]

    @property
    def bootstrap_terms(self):
        return [item.strip() for item in self.bootstrap_terms_csv.split(",") if item.strip()]

    @property
    def recetasgratis_terms(self):
        return [item.strip() for item in self.recetasgratis_terms_csv.split(",") if item.strip()]

    @property
    def cookpad_terms(self):
        return [item.strip() for item in self.cookpad_terms_csv.split(",") if item.strip()]


@lru_cache()
def get_settings():
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.frontend_dir.mkdir(parents=True, exist_ok=True)
    return settings

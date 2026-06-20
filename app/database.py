from __future__ import annotations

import json
import math
import re
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.config import get_settings
from app.models import Recipe, RecipeStats, normalize_list, normalize_text, utcnow


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return utcnow()
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return utcnow()


class RecipeRepository:
    def __init__(self, storage_path: Optional[Path] = None):
        settings = get_settings()
        self.storage_path = storage_path or settings.recipe_store_path
        self._recipes: Dict[str, Recipe] = {}
        self._loaded = False
        self._lock = threading.RLock()

    async def load(self):
        with self._lock:
            if self._loaded:
                return
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.storage_path.exists():
                self._loaded = True
                return
            try:
                raw = self.storage_path.read_text(encoding="utf-8")
                payload = json.loads(raw)
            except (OSError, ValueError):
                payload = {}

            if isinstance(payload, list):
                items = payload
            else:
                items = payload.get("recipes", [])

            for item in items:
                try:
                    recipe = Recipe.model_validate(item)
                    self._recipes[recipe.id] = recipe
                except Exception:
                    continue
            self._loaded = True

    async def ensure_loaded(self):
        if not self._loaded:
            await self.load()

    async def count(self):
        await self.ensure_loaded()
        return len(self._recipes)

    async def all(self):
        await self.ensure_loaded()
        recipes = list(self._recipes.values())
        recipes.sort(key=lambda recipe: (-recipe.score, recipe.title.lower()))
        return recipes

    async def available_filters(self):
        await self.ensure_loaded()

        category_counts: Dict[str, int] = {}
        difficulty_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}

        for recipe in self._recipes.values():
            category = normalize_text(recipe.category)
            difficulty = normalize_text(recipe.difficulty).lower()
            source = normalize_text(recipe.source_name)

            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
            if difficulty:
                difficulty_counts[difficulty] = difficulty_counts.get(difficulty, 0) + 1
            if source:
                source_counts[source] = source_counts.get(source, 0) + 1

        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}

        def build_options(counter: Dict[str, int], label_transform=None):
            items = list(counter.items())
            items.sort(key=lambda item: (-item[1], item[0].lower()))
            options = []
            for value, count in items:
                label = label_transform(value) if label_transform else value
                options.append({"value": value, "label": label, "count": count})
            return options

        categories = build_options(category_counts)
        difficulties = build_options(difficulty_counts, label_transform=lambda value: value.capitalize())
        difficulties.sort(
            key=lambda item: (
                difficulty_order.get(item["value"], 99),
                -item["count"],
                item["value"],
            )
        )
        sources = build_options(source_counts, label_transform=lambda value: value.capitalize())

        return {
            "categories": categories,
            "difficulties": difficulties,
            "sources": sources,
        }

    async def get(self, recipe_id: str):
        await self.ensure_loaded()
        return self._recipes.get(recipe_id)

    async def seed(self, recipes: Iterable[Recipe], preserve_stats: bool = True):
        await self.ensure_loaded()
        with self._lock:
            for recipe in recipes:
                if not isinstance(recipe, Recipe):
                    recipe = Recipe.model_validate(recipe)
                current = self._recipes.get(recipe.id)
                if current and preserve_stats:
                    recipe.stats = current.stats
                    recipe.score = current.score
                    recipe.created_at = current.created_at
                    if not recipe.image_url:
                        recipe.image_url = current.image_url
                    if not recipe.source_url:
                        recipe.source_url = current.source_url
                self._recipes[recipe.id] = recipe
            self._save_locked()

    async def replace_all(self, recipes: Iterable[Recipe]):
        await self.ensure_loaded()
        with self._lock:
            self._recipes = {}
            for recipe in recipes:
                if not isinstance(recipe, Recipe):
                    recipe = Recipe.model_validate(recipe)
                self._recipes[recipe.id] = recipe
            self._save_locked()

    async def record_interaction(self, recipe_id: str, action: str):
        await self.ensure_loaded()
        with self._lock:
            recipe = self._recipes.get(recipe_id)
            if recipe is None:
                return None
            action = (action or "").strip().lower()
            if action == "view":
                recipe.stats.views += 1
            elif action == "save":
                recipe.stats.saved += 1
            else:
                raise ValueError("Unsupported action: %s" % action)
            recipe.score = self._compute_engagement_score(recipe.stats)
            recipe.updated_at = utcnow()
            self._recipes[recipe_id] = recipe
            self._save_locked()
            return recipe

    async def search(self, query: str = "*", category: str = "", difficulty: str = "", page: int = 0, size: int = 6):
        await self.ensure_loaded()
        query = normalize_text(query, "*")
        category = normalize_text(category).lower()
        difficulty = normalize_text(difficulty).lower()
        page = max(int(page), 0)
        size = max(int(size), 1)

        tokens = self._tokenize(query)
        matches = []

        for recipe in self._recipes.values():
            if category and recipe.category.lower() != category:
                continue
            if difficulty and recipe.difficulty.lower() != difficulty:
                continue

            relevance = self._relevance(recipe, query, tokens)
            if query not in ("", "*") and relevance <= 0:
                continue
            matches.append((relevance, recipe.score, recipe.updated_at, recipe))

        matches.sort(key=lambda item: (-item[0], -item[1], item[2], item[3].title.lower()))
        total = len(matches)
        start = page * size
        end = start + size
        results = [item[3] for item in matches[start:end]]
        return total, results

    async def ranking(self, period: str = "monthly", limit: int = 10):
        await self.ensure_loaded()
        recipes = list(self._recipes.values())
        recipes.sort(key=lambda recipe: (-recipe.score, -recipe.stats.saved, -recipe.stats.views, recipe.title.lower()))
        return recipes[: max(int(limit), 1)]

    async def recommendations(self, recipe_id: str, limit: int = 6, mode: str = "hybrid"):
        await self.ensure_loaded()
        anchor = self._recipes.get(recipe_id)
        if anchor is None:
            return []

        anchor_ingredients = set(self._tokenize(" ".join(anchor.ingredients)))
        anchor_tags = set(self._tokenize(" ".join(anchor.tags)))
        anchor_title = set(self._tokenize(anchor.title))
        anchor_category = normalize_text(anchor.category).lower()
        anchor_difficulty = normalize_text(anchor.difficulty).lower()
        mode = normalize_text(mode, "hybrid").lower()
        if mode not in {"hybrid", "ingredients", "type"}:
            mode = "hybrid"

        scored = []
        for candidate in self._recipes.values():
            if candidate.id == recipe_id:
                continue
            candidate_ingredients = set(self._tokenize(" ".join(candidate.ingredients)))
            candidate_tags = set(self._tokenize(" ".join(candidate.tags)))
            shared_ingredients = len(anchor_ingredients.intersection(candidate_ingredients))
            shared_tags = len(anchor_tags.intersection(candidate_tags))
            shared_title = len(anchor_title.intersection(set(self._tokenize(candidate.title))))

            same_category = bool(anchor_category and normalize_text(candidate.category).lower() == anchor_category)
            same_difficulty = bool(anchor_difficulty and normalize_text(candidate.difficulty).lower() == anchor_difficulty)

            score = 0.0
            if mode == "ingredients":
                score += shared_ingredients * 3.0
                score += self._ingredient_overlap_bonus(anchor_ingredients, candidate_ingredients) * 1.5
                score += shared_tags * 0.75
                score += 1.0 if same_category else 0.0
                score += 0.2 if same_difficulty else 0.0
            elif mode == "type":
                score += 4.0 if same_category else 0.0
                score += shared_ingredients * 1.25
                score += shared_tags * 0.75
                score += 0.5 if same_difficulty else 0.0
            else:
                score += shared_ingredients * 2.0
                score += shared_tags * 1.0
                score += shared_title * 0.5
                score += 3.0 if same_category else 0.0
                score += 0.4 if same_difficulty else 0.0
                score += self._ingredient_overlap_bonus(anchor_ingredients, candidate_ingredients)

            score += candidate.score * 0.1
            scored.append((score, candidate.updated_at, candidate))

        scored.sort(key=lambda item: (-item[0], item[1], item[2].title.lower()))
        return [item[2] for item in scored[: max(int(limit), 1)]]

    def _save_locked(self):
        payload = {
            "updated_at": utcnow().isoformat(),
            "count": len(self._recipes),
            "recipes": [recipe.model_dump(mode="json") for recipe in self._recipes.values()],
        }
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _tokenize(self, text: str):
        normalized = normalize_text(text).lower()
        return [token for token in re.split(r"[^a-z0-9áéíóúüñ]+", normalized) if token]

    def _relevance(self, recipe: Recipe, query: str, tokens: Sequence[str]):
        if query in ("", "*"):
            return recipe.score

        haystack = " ".join(
            [
                recipe.title,
                recipe.description,
                recipe.category,
                recipe.difficulty,
                recipe.source_name,
                " ".join(recipe.ingredients),
                " ".join(recipe.instructions),
                " ".join(recipe.tags),
            ]
        ).lower()

        score = 0.0
        if query.lower() in haystack:
            score += 5.0
        for token in tokens:
            if token in haystack:
                score += 1.0
        score += recipe.score * 0.05
        return score

    def _ingredient_overlap_bonus(self, anchor: set, candidate: set):
        if not anchor or not candidate:
            return 0.0
        overlap = len(anchor.intersection(candidate))
        return min(overlap, 3) * 0.4

    def _compute_engagement_score(self, stats: RecipeStats):
        return round((stats.saved * 5.0) + (stats.views * 0.5), 2)

    def _tokenize(self, text: str):
        normalized = normalize_text(text).casefold()
        normalized = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
        return [token for token in re.split(r"[^a-z0-9]+", normalized) if token]

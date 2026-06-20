from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from bs4 import BeautifulSoup

from app.models import Recipe, RecipeStats, normalize_list, normalize_text, utcnow


def clean_text(value: Any, default: str = "") -> str:
    text = normalize_text(value, default)
    if not text:
        return default
    return html_lib.unescape(text)


def slugify(value: Any) -> str:
    text = clean_text(value).lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "recipe"


def parse_duration(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(int(value), 0)

    text = clean_text(value).lower()
    if not text:
        return 0

    iso_match = re.match(r"^p(?:t)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", text)
    if iso_match:
        hours = int(iso_match.group(1) or 0)
        minutes = int(iso_match.group(2) or 0)
        seconds = int(iso_match.group(3) or 0)
        return max((hours * 60) + minutes + int(round(seconds / 60.0)), 0)

    hour_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:h|hour|hours|hr|hrs)", text)
    minute_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m|min|mins|minute|minutes)", text)
    total = 0.0
    if hour_match:
        total += float(hour_match.group(1).replace(",", ".")) * 60.0
    if minute_match:
        total += float(minute_match.group(1).replace(",", "."))

    if total > 0:
        return int(round(total))

    number_match = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if number_match:
        return int(round(float(number_match.group(1).replace(",", "."))))
    return 0


def infer_category(title: str, ingredients: List[str], tags: List[str]) -> str:
    haystack = " ".join([title, " ".join(ingredients), " ".join(tags)]).lower()
    mapping = [
        ("Potato", ["papa", "patata", "potato", "papas"]),
        ("Breakfast", ["desayuno", "breakfast", "huevos", "eggs", "pancake"]),
        ("Soup", ["sopa", "soup", "crema", "broth"]),
        ("Salad", ["ensalada", "salad"]),
        ("Main dish", ["pollo", "chicken", "beef", "carne", "pescado", "fish"]),
        ("Snack", ["snack", "aperitivo", "tapa", "antojito"]),
        ("Dessert", ["postre", "dessert", "cake", "tarta", "bizcocho"]),
    ]
    for label, keywords in mapping:
        if any(keyword in haystack for keyword in keywords):
            return label
    return "General"


def infer_difficulty(cooking_time: int, ingredients: List[str], instructions: List[str]) -> str:
    step_count = len(instructions)
    ingredient_count = len(ingredients)
    if cooking_time and cooking_time <= 20 and step_count <= 5 and ingredient_count <= 8:
        return "easy"
    if cooking_time and cooking_time <= 45 and step_count <= 8:
        return "medium"
    if step_count >= 9 or ingredient_count >= 12 or cooking_time > 60:
        return "hard"
    return "medium"


def _flatten_json_ld(node: Any):
    if isinstance(node, list):
        for item in node:
            for child in _flatten_json_ld(item):
                yield child
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            child = node.get(key)
            if isinstance(child, (list, dict)):
                for sub_child in _flatten_json_ld(child):
                    yield sub_child


def _load_json_payload(text: str):
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        cleaned = re.sub(r"^\s*<!--|-->\s*$", "", text).strip()
        try:
            return json.loads(cleaned)
        except ValueError:
            return None


def _extract_instructions(value: Any):
    instructions: List[str] = []

    if isinstance(value, str):
        parts = re.split(r"(?:\r?\n)+|(?<=[.!?])\s+", clean_text(value))
        instructions.extend([part.strip(" -") for part in parts if part.strip(" -")])
        return instructions

    if isinstance(value, dict):
        if value.get("text"):
            instructions.extend(_extract_instructions(value.get("text")))
        if value.get("name"):
            instructions.extend(_extract_instructions(value.get("name")))
        if value.get("itemListElement"):
            instructions.extend(_extract_instructions(value.get("itemListElement")))
        return instructions

    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if item.get("text"):
                    instructions.extend(_extract_instructions(item.get("text")))
                elif item.get("name"):
                    instructions.extend(_extract_instructions(item.get("name")))
                elif item.get("itemListElement"):
                    instructions.extend(_extract_instructions(item.get("itemListElement")))
            else:
                instructions.extend(_extract_instructions(item))

    cleaned: List[str] = []
    seen = set()
    for instruction in instructions:
        text = clean_text(instruction)
        if not text:
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


def _extract_image(value: Any):
    if isinstance(value, dict):
        return value.get("url") or value.get("contentUrl")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                candidate = item.get("url") or item.get("contentUrl")
                if candidate:
                    return candidate
            elif item:
                return item
        return None
    return value


def _candidate_title(soup: BeautifulSoup):
    meta_title = soup.find("meta", property="og:title")
    if meta_title and meta_title.get("content"):
        return clean_text(meta_title.get("content"))

    title_tag = soup.find("title")
    if title_tag:
        return clean_text(title_tag.get_text(" "))

    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text(" "))
    return ""


def _candidate_description(soup: BeautifulSoup):
    for selector in [
        ("meta", {"name": "description"}),
        ("meta", {"property": "og:description"}),
    ]:
        tag = soup.find(selector[0], selector[1])
        if tag and tag.get("content"):
            return clean_text(tag.get("content"))
    first_paragraph = soup.find("p")
    if first_paragraph:
        return clean_text(first_paragraph.get_text(" "))
    return ""


def _candidate_category(soup: BeautifulSoup):
    meta_section = soup.find("meta", property="article:section")
    if meta_section and meta_section.get("content"):
        return clean_text(meta_section.get("content"))
    breadcrumb = soup.find(attrs={"class": re.compile("breadcrumb", re.I)})
    if breadcrumb:
        text = clean_text(breadcrumb.get_text(" "))
        if text:
            return text
    return ""


def _extract_recipe_from_json_ld(soup: BeautifulSoup):
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        payload = _load_json_payload(script.get_text(" ", strip=True))
        if payload is None:
            continue
        for candidate in _flatten_json_ld(payload):
            recipe_type = candidate.get("@type") or candidate.get("type")
            if isinstance(recipe_type, list):
                type_values = [str(item).lower() for item in recipe_type]
            else:
                type_values = [str(recipe_type).lower()]
            if not any("recipe" in item for item in type_values):
                continue

            ingredients = normalize_list(candidate.get("recipeIngredient") or candidate.get("ingredients"))
            instructions = _extract_instructions(
                candidate.get("recipeInstructions")
                or candidate.get("instructions")
                or candidate.get("step")
                or []
            )
            tags = normalize_list(candidate.get("keywords"))
            category = clean_text(candidate.get("recipeCategory") or candidate.get("category") or "")
            image = _extract_image(candidate.get("image"))
            total_time = candidate.get("totalTime") or candidate.get("cookTime") or candidate.get("prepTime")

            title = clean_text(candidate.get("name") or candidate.get("headline") or "")
            description = clean_text(candidate.get("description") or "")
            if not title:
                title = _candidate_title(soup)

            return {
                "title": title,
                "description": description,
                "category": category,
                "difficulty": "",
                "cooking_time": parse_duration(total_time),
                "ingredients": ingredients,
                "instructions": instructions,
                "image_url": image,
                "source_name": "",
                "source_url": "",
                "tags": tags,
            }
    return None


def extract_recipe_from_html(html_text: str, url: str, source_name: str):
    soup = BeautifulSoup(html_text, "html.parser")
    structured = _extract_recipe_from_json_ld(soup)
    if structured is None:
        structured = {
            "title": _candidate_title(soup),
            "description": _candidate_description(soup),
            "category": _candidate_category(soup),
            "difficulty": "",
            "cooking_time": 0,
            "ingredients": [],
            "instructions": [],
            "image_url": None,
            "source_name": "",
            "source_url": "",
            "tags": [],
        }

    if not structured.get("title"):
        slug = url.rstrip("/").split("/")[-1]
        structured["title"] = clean_text(slug.replace("-", " ").replace("_", " ").title()) or "Recipe"

    structured["source_name"] = source_name
    structured["source_url"] = url
    structured["tags"] = normalize_list(structured.get("tags"))
    structured["ingredients"] = normalize_list(structured.get("ingredients"))
    structured["instructions"] = _extract_instructions(structured.get("instructions"))
    structured["category"] = clean_text(structured.get("category"))
    structured["description"] = clean_text(structured.get("description"))
    structured["cooking_time"] = parse_duration(structured.get("cooking_time"))
    structured["difficulty"] = clean_text(structured.get("difficulty"))
    structured["image_url"] = _extract_image(structured.get("image_url"))
    return structured


def normalize_scraped_recipe(raw: Any):
    if isinstance(raw, Recipe):
        return raw

    raw = dict(raw or {})
    title = clean_text(raw.get("title") or raw.get("name") or raw.get("headline") or "Recipe")
    source_name = clean_text(raw.get("source_name") or raw.get("source") or "demo") or "demo"
    source_url = clean_text(raw.get("source_url") or raw.get("url") or raw.get("link") or "")
    description = clean_text(raw.get("description") or "")
    ingredients = normalize_list(raw.get("ingredients") or raw.get("recipeIngredient") or [])
    instructions = _extract_instructions(raw.get("instructions") or raw.get("recipeInstructions") or [])
    tags = normalize_list(raw.get("tags") or raw.get("keywords") or [])
    category = clean_text(raw.get("category") or raw.get("recipeCategory") or "")
    cooking_time = parse_duration(raw.get("cooking_time") or raw.get("cook_time") or raw.get("total_time") or raw.get("totalTime"))
    difficulty = clean_text(raw.get("difficulty") or raw.get("level") or "")
    image_url = _extract_image(raw.get("image_url") or raw.get("image") or raw.get("imageUrl"))

    if not category:
        category = infer_category(title, ingredients, tags)
    if not difficulty:
        difficulty = infer_difficulty(cooking_time, ingredients, instructions)
    if not description:
        description = "Recipe for %s" % title.lower()

    stats_payload = raw.get("stats") or {}
    if isinstance(stats_payload, RecipeStats):
        stats = stats_payload
    else:
        if not isinstance(stats_payload, dict):
            stats_payload = {}
        views = stats_payload.get("views", raw.get("views", 0))
        saved = stats_payload.get("saved", raw.get("saved", 0))
        stats = RecipeStats(views=int(views or 0), saved=int(saved or 0))

    recipe_id = clean_text(raw.get("id") or raw.get("_id") or "")
    if not recipe_id:
        basis = "|".join([source_name, source_url, title])
        suffix = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:8]
        recipe_id = "%s-%s" % (slugify(title), suffix)

    score = raw.get("score")
    if score in (None, "", 0):
        score = round((stats.saved * 5.0) + (stats.views * 0.5), 2)

    created_at = raw.get("created_at") or utcnow()
    updated_at = raw.get("updated_at") or utcnow()

    return Recipe(
        id=recipe_id,
        title=title,
        description=description,
        category=category,
        difficulty=difficulty,
        cooking_time=cooking_time,
        ingredients=ingredients,
        instructions=instructions,
        image_url=image_url,
        source_name=source_name,
        source_url=source_url,
        tags=tags,
        stats=stats,
        score=float(score or 0),
        created_at=created_at,
        updated_at=updated_at,
    )


def build_demo_recipes():
    return [
        {
            "title": "Papa al horno con romero",
            "description": "Papas doradas con ajo, romero y aceite de oliva.",
            "category": "Potato",
            "difficulty": "easy",
            "cooking_time": 35,
            "ingredients": [
                "4 papas medianas",
                "2 cucharadas de aceite de oliva",
                "2 dientes de ajo",
                "Romero fresco",
                "Sal y pimienta",
            ],
            "instructions": [
                "Precalentar el horno a 200 C.",
                "Cortar las papas en gajos y mezclar con aceite, ajo y romero.",
                "Hornear hasta dorar y servir caliente.",
            ],
            "source_name": "demo",
            "source_url": "",
            "tags": ["papa", "horno", "romero"],
            "stats": {"views": 24, "saved": 9},
        },
        {
            "title": "Pure de papa cremoso",
            "description": "Pure suave con mantequilla y leche.",
            "category": "Potato",
            "difficulty": "easy",
            "cooking_time": 25,
            "ingredients": [
                "5 papas",
                "2 cucharadas de mantequilla",
                "1 taza de leche",
                "Sal",
            ],
            "instructions": [
                "Hervir las papas hasta que esten tiernas.",
                "Machacar con mantequilla y leche hasta lograr una textura cremosa.",
            ],
            "source_name": "demo",
            "source_url": "",
            "tags": ["pure", "papas", "guarnicion"],
            "stats": {"views": 18, "saved": 7},
        },
        {
            "title": "Papas bravas caseras",
            "description": "Papas fritas con salsa picante y alioli.",
            "category": "Snack",
            "difficulty": "medium",
            "cooking_time": 40,
            "ingredients": [
                "4 papas grandes",
                "Aceite para freir",
                "Pimenton dulce",
                "Ajies o salsa picante",
                "Mayonesa o alioli",
            ],
            "instructions": [
                "Cortar y freir las papas hasta que esten crujientes.",
                "Mezclar la salsa con pimenton y servir sobre las papas.",
            ],
            "source_name": "demo",
            "source_url": "",
            "tags": ["picante", "aperitivo", "papas"],
            "stats": {"views": 30, "saved": 12},
        },
        {
            "title": "Tortilla de papa clasica",
            "description": "Tortilla esponjosa con cebolla y papa.",
            "category": "Breakfast",
            "difficulty": "medium",
            "cooking_time": 45,
            "ingredients": [
                "6 papas",
                "1 cebolla",
                "5 huevos",
                "Aceite de oliva",
                "Sal",
            ],
            "instructions": [
                "Cocinar las papas y la cebolla a fuego bajo.",
                "Batir los huevos y mezclar con las papas.",
                "Cuajar en una sarten por ambos lados.",
            ],
            "source_name": "demo",
            "source_url": "",
            "tags": ["tortilla", "huevos", "desayuno"],
            "stats": {"views": 42, "saved": 15},
        },
        {
            "title": "Papa rellena peruana",
            "description": "Papa dorada con relleno de carne y especias.",
            "category": "Main dish",
            "difficulty": "hard",
            "cooking_time": 70,
            "ingredients": [
                "8 papas",
                "250 g de carne molida",
                "1 cebolla",
                "Aceitunas",
                "Huevo duro",
            ],
            "instructions": [
                "Preparar un relleno sazonado con carne y cebolla.",
                "Formar las papas con el relleno en el centro.",
                "Pasar por huevo y freir hasta dorar.",
            ],
            "source_name": "demo",
            "source_url": "",
            "tags": ["peruana", "rellena", "carne"],
            "stats": {"views": 36, "saved": 14},
        },
        {
            "title": "Ensalada tibia de papa",
            "description": "Ensalada fresca con papas, mostaza y hierbas.",
            "category": "Salad",
            "difficulty": "easy",
            "cooking_time": 30,
            "ingredients": [
                "5 papas",
                "Mostaza",
                "Perejil",
                "Cebollin",
                "Aceite de oliva",
            ],
            "instructions": [
                "Cocer las papas y cortarlas en trozos.",
                "Mezclar con mostaza, aceite y hierbas frescas.",
            ],
            "source_name": "demo",
            "source_url": "",
            "tags": ["ensalada", "hierbas", "guarnicion"],
            "stats": {"views": 20, "saved": 8},
        },
    ]

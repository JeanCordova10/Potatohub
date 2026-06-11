import hashlib
from datetime import datetime, timezone
from etl.config import CATEGORY_KEYWORDS


def make_id(url: str) -> str:
    """Genera un ID único y reproducible a partir de la URL (hash MD5)."""
    return hashlib.md5(url.encode()).hexdigest()


def classify_category(title: str, search_term: str) -> str:
    """Clasifica la receta en una categoría según el título y el término buscado."""
    text = (title + " " + search_term).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return "GENERAL"


def transform(raw: dict) -> dict:
    """
    Recibe un dict crudo del scraper y retorna el documento
    listo para insertar en MongoDB.
    """
    url = raw["source_url"]
    title = raw["title"]
    now = datetime.now(timezone.utc)

    return {
        "_id": make_id(url),
        "title": title,
        "source": raw["source"],
        "source_url": url,
        "search_term": raw["search_term"],
        "lang": raw.get("lang", "es"),
        "country": raw.get("country", "PE"),
        "category_potato": classify_category(title, raw["search_term"]),
        # Campos que se enriquecerán más adelante (scraping de detalle)
        "description": None,
        "ingredients": [],
        "instructions": [],
        "difficulty": None,
        "prep_time_min": None,
        "cook_time_min": None,
        "total_time_min": None,
        "servings": None,
        "tags": [],
        "stats": {"views": 0, "saved": 0},
        "scraped_at": now,
        "created_at": now,
        "updated_at": now,
    }


def transform_all(raw_list: list[dict]) -> list[dict]:
    """Transforma una lista de recetas crudas."""
    return [transform(r) for r in raw_list]
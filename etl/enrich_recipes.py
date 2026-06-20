import os
import re
import time
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI   = os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true")
MONGO_DB    = os.getenv("MONGO_DB", "potatohub")
RATE_LIMIT  = 3  # segundos entre requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-PE,es;q=0.9",
}


def fetch(url: str) -> BeautifulSoup | None:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "html.parser")
        return None
    except Exception as e:
        print(f"    [!] Error: {e}")
        return None


def extract_cookpad_detail(url: str) -> dict:
    """Extrae ingredientes e instrucciones de una receta de Cookpad."""
    soup = fetch(url)
    if not soup:
        return {}

    # Ingredientes: id="ingredient_XXXXXXX"
    ingredients = []
    for el in soup.select('[id^="ingredient_"]'):
        text = el.get_text(strip=True)
        if text:
            ingredients.append(text)

    # Pasos: id="step_XXXXXXX" — el texto empieza con el número del paso
    instructions = []
    for el in soup.select('[id^="step_"]'):
        text = el.get_text(strip=True)
        # Quitar el número inicial (ej: "1Hacer hervir..." → "Hacer hervir...")
        text = re.sub(r'^\d+', '', text).strip()
        if text:
            instructions.append(text)

    return {
        "ingredients":  ingredients,
        "instructions": instructions,
    }


def enrich(limit: int = 200, source: str = "cookpad_pe"):
    """
    Enriquece `limit` recetas de `source` que aún no tienen ingredientes.
    """
    client     = MongoClient(MONGO_URI)
    collection = client[MONGO_DB]["recipes"]

    # Recetas sin ingredientes de la fuente indicada
    pendientes = list(collection.find(
        {"source": source, "ingredients": []},
        {"_id": 1, "source_url": 1, "title": 1}
    ).limit(limit))

    total = len(pendientes)
    print(f"\nEnriqueciendo {total} recetas de '{source}'...")
    print("=" * 55)

    enriquecidas = 0
    sin_datos    = 0

    for i, recipe in enumerate(pendientes, 1):
        titulo = recipe["title"][:45]
        print(f"  [{i:>3}/{total}] {titulo}")

        detail = extract_cookpad_detail(recipe["source_url"])

        if detail.get("ingredients"):
            collection.update_one(
                {"_id": recipe["_id"]},
                {"$set": {
                    "ingredients":  detail["ingredients"],
                    "instructions": detail["instructions"],
                    "updated_at":   datetime.now(timezone.utc),
                }}
            )
            ing_count  = len(detail["ingredients"])
            step_count = len(detail["instructions"])
            print(f"         ✓ {ing_count} ingredientes, {step_count} pasos")
            enriquecidas += 1
        else:
            print(f"         ✗ sin datos")
            sin_datos += 1

        time.sleep(RATE_LIMIT)

    print("=" * 55)
    print(f"  Enriquecidas con éxito : {enriquecidas}")
    print(f"  Sin datos              : {sin_datos}")
    print(f"  Total procesadas       : {total}")


if __name__ == "__main__":
    enrich(limit=3008, source="cookpad_pe")
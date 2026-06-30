"""
Extrae image_url de cada receta visitando su source_url en Cookpad.
Solo procesa recetas que ya tienen ingredientes pero les falta image_url.

Uso:
    python -m etl.fetch_images            # procesa todas (puede tomar horas)
    python -m etl.fetch_images --limit 50 # prueba con 50 primero
"""

import argparse
import os
import time
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

from etl.config import HEADERS

load_dotenv()

MONGO_URI  = os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true")
MONGO_DB   = os.getenv("MONGO_DB", "potatohub")
RATE_LIMIT = 1.5   # segundos entre requests
BATCH_SIZE = 50    # bulk writes cada N recetas


def fetch_image_url(source_url: str) -> str | None:
    try:
        resp = httpx.get(source_url, headers=HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find("meta", property="og:image")
        if tag and tag.get("content"):
            return tag["content"]
        # fallback: primera imagen con src de Cookpad CDN
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if "cpcdn.com" in src or "cookpad.com" in src:
                return src
        return None
    except Exception as exc:
        print(f"    [!] {exc}")
        return None


def run(limit: int = 0):
    client     = MongoClient(MONGO_URI)
    col        = client[MONGO_DB]["recipes"]

    filtro = {
        "ingredients": {"$exists": True, "$not": {"$size": 0}},
        "$or": [{"image_url": None}, {"image_url": {"$exists": False}}, {"image_url": ""}],
    }
    total = col.count_documents(filtro)
    target = min(total, limit) if limit else total
    print(f"\nRecetas sin imagen: {total}  |  A procesar: {target}")
    print("=" * 60)

    cursor   = col.find(filtro, {"_id": 1, "source_url": 1, "title": 1}).limit(target)
    batch    = []
    ok = fail = 0

    for i, doc in enumerate(cursor, 1):
        titulo = doc.get("title", "")[:50]
        url    = doc.get("source_url", "")
        print(f"  [{i:>4}/{target}] {titulo}")

        image_url = fetch_image_url(url) if url else None

        if image_url:
            batch.append(UpdateOne(
                {"_id": doc["_id"]},
                {"$set": {"image_url": image_url, "updated_at": datetime.now(timezone.utc)}},
            ))
            print(f"           ✓ {image_url[:70]}")
            ok += 1
        else:
            print("           ✗ sin imagen")
            fail += 1

        if len(batch) >= BATCH_SIZE:
            col.bulk_write(batch, ordered=False)
            batch.clear()

        time.sleep(RATE_LIMIT)

    if batch:
        col.bulk_write(batch, ordered=False)

    print("=" * 60)
    print(f"  Con imagen  : {ok}")
    print(f"  Sin imagen  : {fail}")
    print(f"  Total       : {ok + fail}")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Máximo de recetas a procesar (0 = todas)")
    args = parser.parse_args()
    run(limit=args.limit)

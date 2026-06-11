import os
from dotenv import load_dotenv
from etl.scraper import scrape_cookpad, scrape_recetasgratis
from etl.transformer import transform_all
from etl.mongo_loader import upsert_recipes
from etl.config import COOKPAD_TERMS, RECETASGRATIS_TERMS

load_dotenv()

# Para el ETL que corre en la máquina local (fuera de Docker)
# usa localhost en lugar de los hostnames internos de Docker
MONGO_URI = os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true")
MONGO_DB  = os.getenv("MONGO_DB", "potatohub")


def run():
    print("=" * 55)
    print("  PotatoHub ETL — inicio")
    print("=" * 55)

    total_insertadas = 0
    total_existentes = 0

    # ── Cookpad PE ────────────────────────────────────────
    print("\n[1/2] Scrapeando Cookpad PE...")
    for term in COOKPAD_TERMS:
        raw = scrape_cookpad(term)
        docs = transform_all(raw)
        ins, ex = upsert_recipes(docs, MONGO_URI, MONGO_DB)
        total_insertadas += ins
        total_existentes += ex
        print(f"  [{term}] → {ins} nuevas, {ex} ya existían\n")

    # ── RecetasGratis ─────────────────────────────────────
    print("\n[2/2] Scrapeando RecetasGratis...")
    for term in RECETASGRATIS_TERMS:
        raw = scrape_recetasgratis(term)
        docs = transform_all(raw)
        ins, ex = upsert_recipes(docs, MONGO_URI, MONGO_DB)
        total_insertadas += ins
        total_existentes += ex
        print(f"  [{term}] → {ins} nuevas, {ex} ya existían\n")

    # ── Resumen ───────────────────────────────────────────
    print("=" * 55)
    print(f"  ETL completado")
    print(f"  Recetas nuevas insertadas : {total_insertadas}")
    print(f"  Recetas ya existentes     : {total_existentes}")
    print("=" * 55)


if __name__ == "__main__":
    run()
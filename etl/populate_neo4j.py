"""
Siembra nodos Recipe e Ingredient en Neo4j leyendo desde MongoDB.
Solo necesita correr UNA VEZ (o tras un re-scraping masivo).

Uso:
    python -m etl.populate_neo4j
"""

import os
import re
from dotenv import load_dotenv
from pymongo import MongoClient
from neo4j import GraphDatabase

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true")
MONGO_DB  = os.getenv("MONGO_DB", "potatohub")
NEO4J_URI = os.getenv("NEO4J_URI_LOCAL", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "potatohub123")

BATCH = 200


def extract_keywords(ingredients: list[str]) -> list[str]:
    return list({
        word.lower()
        for ing in ingredients
        for word in re.split(r"\W+", ing)
        if len(word) > 3
    })[:20]


def run():
    mongo  = MongoClient(MONGO_URI)
    col    = mongo[MONGO_DB]["recipes"]
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as s:
        s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (r:Recipe)     REQUIRE r.id   IS UNIQUE")
        s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User)       REQUIRE u.id   IS UNIQUE")
        s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.name IS UNIQUE")
        s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Category)   REQUIRE c.name IS UNIQUE")

    total = col.count_documents({})
    print(f"\nRecetas en MongoDB: {total}")
    print("Poblando Neo4j...\n")

    cursor    = col.find({}, {"_id": 1, "title": 1, "category_potato": 1, "ingredients": 1})
    batch     = []
    processed = 0

    def flush(session, batch):
        session.run(
            """
            UNWIND $rows AS row
            MERGE (r:Recipe {id: row.id})
            SET r.title    = row.title,
                r.category = row.category
            MERGE (c:Category {name: row.category})
            MERGE (r)-[:BELONGS_TO]->(c)
            WITH r, row
            UNWIND row.keywords AS kw
            MERGE (i:Ingredient {name: kw})
            MERGE (r)-[:CONTAINS]->(i)
            """,
            rows=batch,
        )

    with driver.session() as s:
        for doc in cursor:
            ingredients = doc.get("ingredients") or []
            keywords    = extract_keywords(ingredients)
            batch.append({
                "id":       str(doc["_id"]),
                "title":    doc.get("title") or "",
                "category": doc.get("category_potato") or "GENERAL",
                "keywords": keywords,
            })
            if len(batch) >= BATCH:
                flush(s, batch)
                processed += len(batch)
                print(f"  {processed}/{total} nodos creados")
                batch.clear()

        if batch:
            flush(s, batch)
            processed += len(batch)

    print(f"\nListo. {processed} recetas cargadas en Neo4j.")
    driver.close()
    mongo.close()


if __name__ == "__main__":
    run()

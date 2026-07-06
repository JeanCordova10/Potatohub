"""
Clasifica la dificultad de cada receta segun su cantidad de ingredientes:
<=7 ingredientes -> Facil, 8-11 -> Media, >=12 -> Dificil.
Los cortes vienen de los terciles reales del catalogo (33/67 percentil).

Uso:
    python -m etl.classify_difficulty
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

from app.semantic_search import (
    SEMANTIC_VERSION,
    build_recipe_search_fields,
    classify_difficulty_by_ingredient_count,
)

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true")
MONGO_DB = os.getenv("MONGO_DB", "potatohub")

BATCH = 250


def run():
    client = MongoClient(MONGO_URI)
    collection = client[MONGO_DB]["recipes"]

    total = collection.count_documents({})
    print(f"\nClasificando dificultad de {total} recetas...\n")

    operations: list[UpdateOne] = []
    processed = 0
    counts_by_label = {"Facil": 0, "Media": 0, "Dificil": 0}

    for doc in collection.find({}, {"ingredients": 1, "difficulty": 1, "difficulty_canonical": 1, "title": 1, "category": 1, "category_potato": 1, "description": 1, "instructions": 1, "tags": 1}):
        label = classify_difficulty_by_ingredient_count(len(doc.get("ingredients") or []))
        counts_by_label[label] += 1

        doc["difficulty"] = label
        fields = build_recipe_search_fields(doc)
        fields["difficulty"] = label
        fields["search_semantic_version"] = SEMANTIC_VERSION

        operations.append(UpdateOne({"_id": doc["_id"]}, {"$set": fields}))
        if len(operations) >= BATCH:
            collection.bulk_write(operations, ordered=False)
            processed += len(operations)
            print(f"  {processed}/{total} recetas actualizadas")
            operations = []

    if operations:
        collection.bulk_write(operations, ordered=False)
        processed += len(operations)

    print(f"\nListo. {processed} recetas clasificadas.")
    print(f"  Facil   : {counts_by_label['Facil']}")
    print(f"  Media   : {counts_by_label['Media']}")
    print(f"  Dificil : {counts_by_label['Dificil']}")
    client.close()


if __name__ == "__main__":
    run()

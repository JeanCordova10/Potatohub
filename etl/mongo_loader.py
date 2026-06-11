from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError


def get_collection(mongo_uri: str, db_name: str, collection_name: str):
    """Retorna la colección de MongoDB."""
    client = MongoClient(mongo_uri)
    return client[db_name][collection_name]


def upsert_recipes(recipes: list[dict], mongo_uri: str, db_name: str = "potatohub"):
    """
    Inserta las recetas en MongoDB de forma idempotente.
    Si una receta con el mismo _id ya existe, NO la sobreescribe.
    Solo inserta las nuevas.
    """
    if not recipes:
        print("  [!] No hay recetas para insertar.")
        return 0, 0

    collection = get_collection(mongo_uri, db_name, "recipes")

    operations = [
        UpdateOne(
            {"_id": recipe["_id"]},
            {"$setOnInsert": recipe},  # solo inserta si NO existe
            upsert=True
        )
        for recipe in recipes
    ]

    try:
        result = collection.bulk_write(operations, ordered=False)
        inserted = result.upserted_count
        existing = len(recipes) - inserted
        return inserted, existing
    except BulkWriteError as e:
        print(f"  [!] Error en bulk write: {e.details}")
        return 0, 0
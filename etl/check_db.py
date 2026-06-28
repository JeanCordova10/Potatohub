from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/?directConnection=true")
db = client.potatohub

total_recetas = db.recipes.count_documents({})
print(f"\nTotal de recetas: {total_recetas}")

print("\nPor fuente:")
for row in db.recipes.aggregate([{"$group": {"_id": "$source", "total": {"$sum": 1}}}]):
    print(f"  {row['_id']}: {row['total']}")

print("\nPor categoria:")
for row in db.recipes.aggregate([{"$group": {"_id": "$category_potato", "total": {"$sum": 1}}}]):
    print(f"  {row['_id']}: {row['total']}")

receta = db.recipes.find_one({"source": "cookpad_pe"}) or db.recipes.find_one({})
if receta:
    print("\nEjemplo de receta:")
    print(f"  Titulo    : {receta['title']}")
    print(f"  Fuente    : {receta['source']}")
    print(f"  Categoria : {receta['category_potato']}")
    print(f"  URL       : {receta['source_url']}")

print("\nRecetas con ingredientes:")
con_ingredientes = db.recipes.count_documents({"ingredients": {"$ne": []}})
print(f"  {con_ingredientes} de {total_recetas} total")

print("\nRecetas sin ingredientes:")
sin_ingredientes = db.recipes.count_documents({"ingredients": []})
print(f"  {sin_ingredientes} de {total_recetas} total")

print("\n3 titulos de ejemplo:")
for receta in db.recipes.find({"source": "cookpad_pe"}, {"title": 1, "source_url": 1}).limit(3):
    print(f"  - {receta['title']}")
    print(f"    {receta['source_url']}")

receta_con = db.recipes.find_one({"source": "cookpad_pe", "ingredients": {"$ne": []}})
if receta_con:
    print("\nEjemplo de receta con ingredientes:")
    print(f"  Titulo      : {receta_con['title']}")
    print(f"  Ingredientes: {receta_con['ingredients'][:3]}")
    print(f"  Pasos       : {receta_con['instructions'][:2]}")

print("\nEjemplos de URLs de Cookpad:")
for receta in db.recipes.find({"source": "cookpad_pe"}, {"title": 1, "source_url": 1}).limit(5):
    print(f"  - {receta['title'][:40]}")
    print(f"    {receta['source_url']}")

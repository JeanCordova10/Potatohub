from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/?directConnection=true")
db = client.potatohub

print(f"\nTotal de recetas: {db.recipes.count_documents({})}")

print("\nPor fuente:")
for r in db.recipes.aggregate([{"$group": {"_id": "$source", "total": {"$sum": 1}}}]):
    print(f"  {r['_id']}: {r['total']}")

print("\nPor categoría:")
for r in db.recipes.aggregate([{"$group": {"_id": "$category_potato", "total": {"$sum": 1}}}]):
    print(f"  {r['_id']}: {r['total']}")

print("\nEjemplo de receta:")
receta = db.recipes.find_one({})
print(f"  Título   : {receta['title']}")
print(f"  Fuente   : {receta['source']}")
print(f"  Categoría: {receta['category_potato']}")
print(f"  URL      : {receta['source_url']}")


print("\nRecetas CON ingredientes:")
con_ingredientes = db.recipes.count_documents({"ingredients": {"$ne": []}})
print(f"  {con_ingredientes} de {db.recipes.count_documents({})} total")

print("\nRecetas SIN ingredientes:")
sin_ingredientes = db.recipes.count_documents({"ingredients": []})
print(f"  {sin_ingredientes} de {db.recipes.count_documents({})} total")

print("\n3 títulos de ejemplo:")
for r in db.recipes.find({}, {"title": 1, "source_url": 1}).limit(3):
    print(f"  - {r['title']}")
    print(f"    {r['source_url']}")

print("\nEjemplo de receta CON ingredientes:")
receta_con = db.recipes.find_one({"ingredients": {"$ne": []}})
if receta_con:
    print(f"  Título      : {receta_con['title']}")
    print(f"  Ingredientes: {receta_con['ingredients'][:3]}")
    print(f"  Pasos       : {receta_con['instructions'][:2]}")

print("\nEjemplos de URLs por fuente:")
for fuente in ["recetasgratis", "ceciliatupac", "mariaperez"]:
    print(f"\n  {fuente}:")
    for r in db.recipes.find({"source": fuente}, {"title": 1, "source_url": 1}).limit(5):
        print(f"    - {r['title'][:40]}")
        print(f"      {r['source_url']}")
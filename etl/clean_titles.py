"""
Limpia titulos de recetas en MongoDB.

Reglas aplicadas:
  1. Elimina caracteres unicode invisibles (Braille blank, zero-width, etc.)
     EXCEPTO U+200D (ZWJ, une partes de emoji como 👩‍🍳) y U+FE0F (variation
     selector que hace ❤️ verse en color).
  2. Quita simbolos/puntuacion al inicio que no sean letras, digitos, ¡ ¿ o comillas.
  3. Quita puntuacion sucia al final (.:- y variantes).
  4. Colapsa espacios multiples.

Uso:
    python -m etl.clean_titles          # dry run (solo muestra cambios)
    python -m etl.clean_titles --apply  # aplica los cambios
"""

import argparse
import os
import re
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true")
MONGO_DB  = os.getenv("MONGO_DB", "potatohub")

# Caracteres invisibles que se pueden eliminar de forma segura.
# NO incluye U+200D (ZWJ) ni U+FE00-U+FE0F (variation selectors de emoji).
INVISIBLE = re.compile(
    "["
    "­"          # soft hyphen
    "͏"          # combining grapheme joiner
    "؜"          # arabic letter mark
    "ᅟᅠ"    # hangul fillers
    "឴឵"    # khmer vowel inherent
    "᠋-᠍"   # mongolian free variation selectors
    "᠎"          # mongolian vowel separator
    "​"          # zero width space
    "‌"          # zero width non-joiner
    # U+200D (ZWJ) excluido: une partes de emoji compuestos
    "\u200E\u200F"    # left/right-to-right marks
    "\u202A-\u202E"   # directional formatting
    "⁠-⁤"   # word joiner y similares
    "\u2066-⁯"   # directional isolates
    "⠀"          # braille blank (el que aparecia en titulos)
    # U+FE00-U+FE0F excluidos: variation selectors (hacen ❤ -> ❤️)
    "﻿"          # BOM / zero width no-break space
    "ﾠ"          # halfwidth hangul filler
    "]+",
)

# Caracteres al inicio que no sean letra, digito, ¡, ¿ o comillas.
# Las comillas se conservan para no romper titulos como "Causa" vegetariana.
LEADING_JUNK = re.compile(r'^[^\w\"\'«»“”¡¿À-ɏḀ-ỿ]+', re.UNICODE)

# Puntuacion sucia al final.
TRAILING_JUNK = re.compile(r'[\s.\-:·；：･~!]+$')


def clean(title: str) -> str:
    t = INVISIBLE.sub('', title)
    t = LEADING_JUNK.sub('', t)
    t = TRAILING_JUNK.sub('', t)
    t = re.sub(r' {2,}', ' ', t).strip()
    return t


def run(apply: bool = False):
    client = MongoClient(MONGO_URI)
    col    = client[MONGO_DB]["recipes"]

    changed = []
    for doc in col.find({}, {"_id": 1, "title": 1}):
        original = doc.get("title") or ""
        cleaned  = clean(original)
        if cleaned != original:
            changed.append((doc["_id"], original, cleaned))

    print(f"\nTitulos que cambiarian: {len(changed)}\n")
    for _id, orig, new in changed[:50]:
        print(f"  ANTES: {orig}")
        print(f"  AFTER: {new}")
        print()

    if len(changed) > 50:
        print(f"  ... y {len(changed) - 50} mas\n")

    if not apply:
        print("(dry run -- usa --apply para guardar los cambios)")
        return

    ops = [
        UpdateOne({"_id": _id}, {"$set": {"title": new}})
        for _id, _, new in changed
    ]
    if ops:
        result = col.bulk_write(ops, ordered=False)
        print(f"Actualizados: {result.modified_count} titulos")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Aplica los cambios (sin esto solo muestra que cambiaria)")
    args = parser.parse_args()
    run(apply=args.apply)

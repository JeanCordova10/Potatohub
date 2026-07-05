from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from pymongo import ASCENDING, MongoClient, ReplaceOne
from pymongo.errors import OperationFailure


BASE_DIR = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd()
SEED_SOURCE = "seed_v1"
DEFAULT_USER_COUNT = 100
DEFAULT_RANDOM_SEED = 20260704
DEFAULT_MONGO_LOCAL_URI = "mongodb://localhost:27017/?directConnection=true"
DEFAULT_NEO4J_LOCAL_URI = "bolt://localhost:7687"

FIRST_NAMES = [
    "Ana", "Luis", "Carmen", "Diego", "Valeria", "Mateo", "Lucia", "Andres",
    "Sofia", "Jose", "Camila", "Javier", "Daniela", "Rafael", "Mariana", "Tomas",
    "Gabriela", "Nicolas", "Elena", "Hector", "Paula", "Martin", "Natalia", "Bruno",
    "Ariana", "Sebastian", "Renata", "Alvaro", "Claudia", "Fernando",
]

LAST_NAMES = [
    "Lopez", "Garcia", "Torres", "Mendoza", "Paredes", "Rojas", "Silva", "Castro",
    "Vega", "Flores", "Navarro", "Suarez", "Morales", "Diaz", "Salazar", "Romero",
    "Herrera", "Quispe", "Campos", "Vargas",
]

PERSONA_ARCHETYPES = [
    {
        "slug": "home-comfort",
        "categories": ["PURE", "GUISO", "SOPA", "GENERAL"],
        "experience": "beginner",
        "difficulty": "easy",
        "saved_range": (5, 10),
        "cooked_range": (2, 5),
        "view_range": (12, 24),
    },
    {
        "slug": "crispy-lover",
        "categories": ["FRITA", "HORNEADA", "RELLENA", "GENERAL"],
        "experience": "intermediate",
        "difficulty": "medium",
        "saved_range": (6, 11),
        "cooked_range": (3, 6),
        "view_range": (14, 28),
    },
    {
        "slug": "traditional-peru",
        "categories": ["CAUSA", "OCOPA", "CHUÑO", "GUISO"],
        "experience": "intermediate",
        "difficulty": "medium",
        "saved_range": (6, 12),
        "cooked_range": (3, 7),
        "view_range": (16, 30),
    },
    {
        "slug": "adventurous-cook",
        "categories": ["RELLENA", "HORNEADA", "CAUSA", "FRITA"],
        "experience": "advanced",
        "difficulty": "hard",
        "saved_range": (7, 14),
        "cooked_range": (4, 8),
        "view_range": (18, 34),
    },
]


@dataclass
class RecipeRecord:
    recipe_id: str
    title: str
    category: str
    difficulty: str
    source_name: str
    source_url: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def running_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def resolve_mongo_uri() -> str:
    direct = os.getenv("MONGO_URI_LOCAL")
    if direct and not running_in_docker():
        return direct
    container_uri = os.getenv("MONGO_URI", "")
    if container_uri and (running_in_docker() or "mongo1" not in container_uri):
        return container_uri
    return DEFAULT_MONGO_LOCAL_URI


def resolve_neo4j_uri() -> str:
    direct = os.getenv("NEO4J_URI_LOCAL")
    if direct and not running_in_docker():
        return direct
    container_uri = os.getenv("NEO4J_URI", "")
    if container_uri and (running_in_docker() or "neo4j" not in container_uri):
        return container_uri
    return DEFAULT_NEO4J_LOCAL_URI


def build_password_hash(email: str) -> str:
    digest = hashlib.sha256(f"{SEED_SOURCE}:{email}:potatohub".encode("utf-8")).hexdigest()
    return f"seeded_sha256${digest}"


def load_recipes_from_mongo(db) -> list[RecipeRecord]:
    docs = db.recipes.find(
        {},
        {
            "_id": 1,
            "title": 1,
            "category_potato": 1,
            "difficulty": 1,
            "source": 1,
            "source_url": 1,
        },
    )
    recipes = []
    for doc in docs:
        recipes.append(
            RecipeRecord(
                recipe_id=str(doc["_id"]),
                title=str(doc.get("title") or "Untitled recipe"),
                category=str(doc.get("category_potato") or "GENERAL"),
                difficulty=str(doc.get("difficulty") or ""),
                source_name=str(doc.get("source") or "cookpad_pe"),
                source_url=str(doc.get("source_url") or ""),
            )
        )
    return recipes


def load_recipes_from_json(path: Path) -> list[RecipeRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload["recipes"] if isinstance(payload, dict) else payload
    recipes = []
    for item in items:
        recipes.append(
            RecipeRecord(
                recipe_id=str(item.get("id") or item.get("_id")),
                title=str(item.get("title") or "Untitled recipe"),
                category=str(item.get("category") or item.get("category_potato") or "GENERAL"),
                difficulty=str(item.get("difficulty") or ""),
                source_name=str(item.get("source_name") or item.get("source") or "demo"),
                source_url=str(item.get("source_url") or ""),
            )
        )
    return recipes


def choose_weighted_recipes(
    rng: random.Random,
    preferred_categories: list[str],
    recipes_by_category: dict[str, list[RecipeRecord]],
    all_recipes: list[RecipeRecord],
    amount: int,
) -> list[RecipeRecord]:
    chosen: list[RecipeRecord] = []
    seen: set[str] = set()

    preferred_pool: list[RecipeRecord] = []
    for category in preferred_categories:
        preferred_pool.extend(recipes_by_category.get(category, []))

    fallback_pool = all_recipes[:]
    rng.shuffle(preferred_pool)
    rng.shuffle(fallback_pool)

    target_preferred = max(int(amount * 0.7), min(amount, 4))
    for recipe in preferred_pool:
        if len(chosen) >= target_preferred:
            break
        if recipe.recipe_id in seen:
            continue
        chosen.append(recipe)
        seen.add(recipe.recipe_id)

    for recipe in fallback_pool:
        if len(chosen) >= amount:
            break
        if recipe.recipe_id in seen:
            continue
        chosen.append(recipe)
        seen.add(recipe.recipe_id)

    return chosen


def build_user_profile(index: int, rng: random.Random, categories: list[str]) -> dict:
    first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
    last_name = LAST_NAMES[(index * 3) % len(LAST_NAMES)]
    archetype = PERSONA_ARCHETYPES[index % len(PERSONA_ARCHETYPES)]
    preferred_categories = [cat for cat in archetype["categories"] if cat in categories]
    if not preferred_categories:
        preferred_categories = categories[: min(3, len(categories))]

    household_size = 1 + (index % 5)
    weekday_cooking_days = sorted(rng.sample(
        ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        k=3,
    ))
    email = f"user{index:03d}@potatohub.local"

    return {
        "_id": email,
        "user_id": email,
        "name": f"{first_name} {last_name}",
        "email": email,
        "password_hash": build_password_hash(email),
        "status": "active",
        "role": "user",
        "source": SEED_SOURCE,
        "is_seeded": True,
        "profile": {
            "experience_level": archetype["experience"],
            "household_size": household_size,
            "city": "Lima" if index % 2 == 0 else "Bogota",
            "preferred_categories": preferred_categories,
            "favorite_difficulty": archetype["difficulty"],
        },
        "preferences": {
            "preferred_categories": preferred_categories,
            "difficulty": archetype["difficulty"],
            "newsletter": False,
            "cooking_days": weekday_cooking_days,
        },
        "seed_persona": archetype["slug"],
    }


def build_user_state_documents(
    user: dict,
    rng: random.Random,
    all_recipes: list[RecipeRecord],
    recipes_by_category: dict[str, list[RecipeRecord]],
) -> tuple[list[dict], list[dict], dict[str, int], dict[str, int]]:
    preferred_categories = user["preferences"]["preferred_categories"]
    persona = next(item for item in PERSONA_ARCHETYPES if item["slug"] == user["seed_persona"])

    view_total = rng.randint(*persona["view_range"])
    saved_total = rng.randint(*persona["saved_range"])
    cooked_total = rng.randint(*persona["cooked_range"])

    viewed_recipes = choose_weighted_recipes(
        rng,
        preferred_categories,
        recipes_by_category,
        all_recipes,
        view_total,
    )
    saved_recipes = viewed_recipes[: min(saved_total, len(viewed_recipes))]
    cooked_recipes = saved_recipes[: min(cooked_total, len(saved_recipes))]

    now = utcnow()
    created_at = now - timedelta(days=rng.randint(25, 180))
    last_login = now - timedelta(days=rng.randint(0, 12), hours=rng.randint(0, 23))

    user["created_at"] = created_at
    user["updated_at"] = now
    user["deleted_at"] = None
    user["last_login_at"] = last_login

    state_docs: list[dict] = []
    event_docs: list[dict] = []
    recipe_view_increments: dict[str, int] = defaultdict(int)
    recipe_save_increments: dict[str, int] = defaultdict(int)

    for order, recipe in enumerate(viewed_recipes):
        viewed_count = rng.randint(1, 4)
        first_seen_at = created_at + timedelta(days=rng.randint(0, 90), hours=order % 11)
        last_seen_at = first_seen_at + timedelta(days=rng.randint(0, 15), hours=rng.randint(0, 12))
        saved = recipe in saved_recipes
        cooked = recipe in cooked_recipes
        saved_at = last_seen_at + timedelta(hours=1) if saved else None
        cooked_at = saved_at + timedelta(days=rng.randint(1, 10)) if cooked and saved_at else None

        recipe_view_increments[recipe.recipe_id] += viewed_count
        if saved:
            recipe_save_increments[recipe.recipe_id] += 1

        last_action = "cook" if cooked else "save" if saved else "view"
        last_action_at = cooked_at or saved_at or last_seen_at

        state_docs.append(
            {
                "_id": f"{user['_id']}::{recipe.recipe_id}",
                "user_id": user["_id"],
                "recipe_id": recipe.recipe_id,
                "viewed_count": viewed_count,
                "saved": saved,
                "saved_at": saved_at,
                "cooked": cooked,
                "cooked_at": cooked_at,
                "last_action": last_action,
                "last_action_at": last_action_at,
                "source": SEED_SOURCE,
                "created_at": first_seen_at,
                "updated_at": last_action_at,
            }
        )

        for view_index in range(viewed_count):
            event_docs.append(
                {
                    "_id": f"{user['_id']}::{recipe.recipe_id}::view::{view_index + 1}",
                    "user_id": user["_id"],
                    "recipe_id": recipe.recipe_id,
                    "action": "view",
                    "source": SEED_SOURCE,
                    "created_at": first_seen_at + timedelta(hours=view_index),
                }
            )
        if saved:
            event_docs.append(
                {
                    "_id": f"{user['_id']}::{recipe.recipe_id}::save",
                    "user_id": user["_id"],
                    "recipe_id": recipe.recipe_id,
                    "action": "save",
                    "source": SEED_SOURCE,
                    "created_at": saved_at,
                }
            )
        if cooked:
            event_docs.append(
                {
                    "_id": f"{user['_id']}::{recipe.recipe_id}::cook",
                    "user_id": user["_id"],
                    "recipe_id": recipe.recipe_id,
                    "action": "cook",
                    "source": SEED_SOURCE,
                    "created_at": cooked_at,
                }
            )

    return state_docs, event_docs, recipe_view_increments, recipe_save_increments


def ensure_indexes(db) -> None:
    index_specs = [
        (db.users, [("email", ASCENDING)], {"unique": True}),
        (db.users, [("source", ASCENDING)], {}),
        (db.user_recipe_states, [("user_id", ASCENDING), ("recipe_id", ASCENDING)], {"unique": True}),
        (db.user_recipe_states, [("source", ASCENDING)], {}),
        (db.user_events, [("user_id", ASCENDING), ("created_at", ASCENDING)], {}),
        (db.user_events, [("source", ASCENDING)], {}),
    ]
    for collection, keys, options in index_specs:
        try:
            collection.create_index(keys, **options)
        except OperationFailure as exc:
            if exc.code != 85:
                raise


def sync_seed_users_to_neo4j(uri: str, user: str, password: str, users: list[dict], states: list[dict], recipe_map: dict[str, RecipeRecord]) -> None:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (r:Recipe) REQUIRE r.id IS UNIQUE")
            session.run(
                """
                MATCH (u:User {source: $source})-[rel:VIEWED|SAVED|COOKED]->(:Recipe)
                DELETE rel
                """,
                source=SEED_SOURCE,
            ).consume()

            for payload in users:
                session.run(
                    """
                    MERGE (u:User {id: $id})
                    SET u.name = $name,
                        u.email = $email,
                        u.status = $status,
                        u.source = $source,
                        u.seed_persona = $seed_persona,
                        u.preferred_categories = $preferred_categories,
                        u.favorite_difficulty = $favorite_difficulty,
                        u.experience_level = $experience_level,
                        u.updated_at = datetime($updated_at),
                        u.created_at = datetime($created_at)
                    """,
                    id=payload["_id"],
                    name=payload["name"],
                    email=payload["email"],
                    status=payload["status"],
                    source=payload["source"],
                    seed_persona=payload["seed_persona"],
                    preferred_categories=payload["preferences"]["preferred_categories"],
                    favorite_difficulty=payload["preferences"]["difficulty"],
                    experience_level=payload["profile"]["experience_level"],
                    created_at=payload["created_at"].isoformat(),
                    updated_at=payload["updated_at"].isoformat(),
                ).consume()

            for state in states:
                recipe = recipe_map.get(state["recipe_id"])
                if recipe is None:
                    continue

                session.run(
                    """
                    MERGE (r:Recipe {id: $recipe_id})
                    SET r.title = $title,
                        r.category = $category,
                        r.difficulty = $difficulty,
                        r.source_name = $source_name,
                        r.source_url = $source_url
                    """,
                    recipe_id=recipe.recipe_id,
                    title=recipe.title,
                    category=recipe.category,
                    difficulty=recipe.difficulty,
                    source_name=recipe.source_name,
                    source_url=recipe.source_url,
                ).consume()

                session.run(
                    """
                    MATCH (u:User {id: $user_id})
                    MATCH (r:Recipe {id: $recipe_id})
                    MERGE (u)-[rel:VIEWED]->(r)
                    SET rel.count = $viewed_count,
                        rel.last_at = datetime($last_action_at),
                        rel.source = $source
                    """,
                    user_id=state["user_id"],
                    recipe_id=state["recipe_id"],
                    viewed_count=state["viewed_count"],
                    last_action_at=state["last_action_at"].isoformat(),
                    source=SEED_SOURCE,
                ).consume()

                if state["saved"]:
                    session.run(
                        """
                        MATCH (u:User {id: $user_id})
                        MATCH (r:Recipe {id: $recipe_id})
                        MERGE (u)-[rel:SAVED]->(r)
                        SET rel.at = datetime($saved_at),
                            rel.source = $source
                        """,
                        user_id=state["user_id"],
                        recipe_id=state["recipe_id"],
                        saved_at=state["saved_at"].isoformat(),
                        source=SEED_SOURCE,
                    ).consume()
                else:
                    session.run(
                        """
                        MATCH (u:User {id: $user_id})-[rel:SAVED]->(r:Recipe {id: $recipe_id})
                        DELETE rel
                        """,
                        user_id=state["user_id"],
                        recipe_id=state["recipe_id"],
                    ).consume()

                if state["cooked"]:
                    session.run(
                        """
                        MATCH (u:User {id: $user_id})
                        MATCH (r:Recipe {id: $recipe_id})
                        MERGE (u)-[rel:COOKED]->(r)
                        SET rel.at = datetime($cooked_at),
                            rel.source = $source
                        """,
                        user_id=state["user_id"],
                        recipe_id=state["recipe_id"],
                        cooked_at=state["cooked_at"].isoformat(),
                        source=SEED_SOURCE,
                    ).consume()
                else:
                    session.run(
                        """
                        MATCH (u:User {id: $user_id})-[rel:COOKED]->(r:Recipe {id: $recipe_id})
                        DELETE rel
                        """,
                        user_id=state["user_id"],
                        recipe_id=state["recipe_id"],
                    ).consume()
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fake PotatoHub users into MongoDB and Neo4j.")
    parser.add_argument("--count", type=int, default=DEFAULT_USER_COUNT, help="Number of fake users to generate.")
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="Deterministic random seed.")
    parser.add_argument("--mongo-uri", default="", help="Override MongoDB connection string.")
    parser.add_argument("--mongo-db", default=os.getenv("MONGO_DB", "potatohub"), help="MongoDB database name.")
    parser.add_argument("--neo4j-uri", default="", help="Override Neo4j connection string.")
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"), help="Neo4j username.")
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", "potatohub123"), help="Neo4j password.")
    args = parser.parse_args()

    load_dotenv(BASE_DIR / ".env")

    mongo_uri = args.mongo_uri or resolve_mongo_uri()
    neo4j_uri = args.neo4j_uri or resolve_neo4j_uri()

    rng = random.Random(args.seed)
    client = MongoClient(mongo_uri)
    db = client[args.mongo_db]

    ensure_indexes(db)

    recipes = load_recipes_from_mongo(db)
    if not recipes:
        recipes = load_recipes_from_json(BASE_DIR / "data" / "recipes.json")
    if not recipes:
        raise RuntimeError("No recipes available to seed fake users.")

    recipe_map = {recipe.recipe_id: recipe for recipe in recipes}
    recipes_by_category: dict[str, list[RecipeRecord]] = defaultdict(list)
    for recipe in recipes:
        recipes_by_category[recipe.category].append(recipe)
    categories = sorted(recipes_by_category)

    users: list[dict] = []
    states: list[dict] = []
    events: list[dict] = []

    recipe_view_increments: dict[str, int] = defaultdict(int)
    recipe_save_increments: dict[str, int] = defaultdict(int)

    for index in range(1, args.count + 1):
        user_doc = build_user_profile(index, rng, categories)
        state_docs, event_docs, view_increments, save_increments = build_user_state_documents(
            user_doc,
            rng,
            recipes,
            recipes_by_category,
        )
        users.append(user_doc)
        states.extend(state_docs)
        events.extend(event_docs)
        for recipe_id, amount in view_increments.items():
            recipe_view_increments[recipe_id] += amount
        for recipe_id, amount in save_increments.items():
            recipe_save_increments[recipe_id] += amount

    db.users.bulk_write(
        [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in users],
        ordered=False,
    )
    db.user_recipe_states.bulk_write(
        [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in states],
        ordered=False,
    )

    db.user_events.delete_many({"source": SEED_SOURCE})
    if events:
        db.user_events.insert_many(events, ordered=False)

    sync_seed_users_to_neo4j(
        neo4j_uri,
        args.neo4j_user,
        args.neo4j_password,
        users,
        states,
        recipe_map,
    )

    summary = {
        "seed_source": SEED_SOURCE,
        "users_upserted": len(users),
        "recipe_states_upserted": len(states),
        "events_inserted": len(events),
        "unique_recipes_touched": len({doc["recipe_id"] for doc in states}),
        "view_events_generated": sum(recipe_view_increments.values()),
        "save_events_generated": sum(recipe_save_increments.values()),
        "mongo_uri": mongo_uri,
        "neo4j_uri": neo4j_uri,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError


ROOT_DIR = Path(__file__).resolve().parents[1]
SEED_SOURCE = "seed_v1"
QA_EMAIL_PREFIX = "qa-nosql"
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
INDEX_SCAN_STAGES = {"IXSCAN", "COUNT_SCAN", "DISTINCT_SCAN", "IDHACK", "EXPRESS_IXSCAN"}
NEO4J_INDEX_OPERATORS = {"NodeIndexSeek", "NodeUniqueIndexSeek", "NodeIndexScan"}
MONGO_REQUIRED_COLLECTIONS = ["recipes", "users", "user_recipe_states", "user_events"]

NEO4J_RECOMMENDATION_QUERY = """
MATCH (me:User {id: $user_id})
MATCH (peer:User)
WHERE peer.id <> me.id
WITH me, peer,
     size([cat IN coalesce(me.preferred_categories, []) WHERE cat IN coalesce(peer.preferred_categories, [])]) AS profile_overlap,
     CASE
         WHEN toLower(coalesce(me.favorite_difficulty, '')) <> '' AND
              toLower(coalesce(me.favorite_difficulty, '')) = toLower(coalesce(peer.favorite_difficulty, ''))
         THEN 1 ELSE 0
     END AS same_pref_difficulty,
     CASE
         WHEN toLower(coalesce(me.experience_level, '')) <> '' AND
              toLower(coalesce(me.experience_level, '')) = toLower(coalesce(peer.experience_level, ''))
         THEN 1 ELSE 0
     END AS same_experience
WHERE profile_overlap > 0 OR same_pref_difficulty = 1 OR same_experience = 1 OR EXISTS {
    MATCH (me)-[:SAVED|COOKED]->(:Recipe)<-[:SAVED|COOKED]-(peer)
}
OPTIONAL MATCH (me)-[:SAVED|COOKED]->(shared_history:Recipe)<-[:SAVED|COOKED]-(peer)
WITH me, peer, profile_overlap, same_pref_difficulty, same_experience,
     count(DISTINCT shared_history) AS shared_history_count
MATCH (peer)-[peer_rel:SAVED|COOKED]->(candidate:Recipe)
WHERE NOT EXISTS { MATCH (me)-[:VIEWED|SAVED|COOKED]->(candidate) }
WITH me, candidate,
     count(DISTINCT peer) AS peer_count,
     sum(CASE type(peer_rel) WHEN 'COOKED' THEN 8.0 ELSE 5.0 END) AS peer_signal,
     max(profile_overlap) AS profile_overlap,
     max(shared_history_count) AS shared_history_count,
     max(same_pref_difficulty) AS same_pref_difficulty,
     max(same_experience) AS same_experience
CALL {
    WITH candidate
    OPTIONAL MATCH (candidate)-[:IN_CATEGORY]->(category:Category)
    RETURN collect(DISTINCT category.name) AS candidate_categories
}
CALL {
    WITH candidate
    OPTIONAL MATCH (candidate)-[:HAS_DIFFICULTY]->(difficulty:Difficulty)
    RETURN head(collect(DISTINCT difficulty.name)) AS candidate_difficulty
}
WITH candidate,
     peer_count,
     profile_overlap,
     shared_history_count,
     peer_signal,
     size([cat IN coalesce(me.preferred_categories, []) WHERE cat IN candidate_categories]) AS preferred_category_hits,
     CASE
         WHEN toLower(coalesce(me.favorite_difficulty, '')) <> '' AND
              toLower(coalesce(me.favorite_difficulty, '')) = toLower(coalesce(candidate_difficulty, ''))
         THEN 1 ELSE 0
     END AS preferred_difficulty_hit,
     same_pref_difficulty,
     same_experience
WITH candidate,
     peer_count,
     profile_overlap,
     preferred_category_hits,
     peer_signal +
     (peer_count * 2.2) +
     (profile_overlap * 1.5) +
     (shared_history_count * 2.0) +
     (preferred_category_hits * 1.25) +
     (preferred_difficulty_hit * 0.75) +
     (same_pref_difficulty * 0.75) +
     (same_experience * 0.5) +
     coalesce(candidate.score, 0.0) * 0.08 AS ranking
RETURN candidate.id AS id, ranking
ORDER BY ranking DESC, peer_count DESC, candidate.score DESC, candidate.title ASC
LIMIT $limit
"""


@dataclass
class QaCheck:
    section: str
    title: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetric:
    title: str
    avg_ms: float
    min_ms: float
    max_ms: float
    samples: int


class Reporter:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.results: list[QaCheck] = []
        self.current_section = ""

    def section(self, title: str) -> None:
        self.current_section = title
        if self.verbose:
            print("")
            print(f"== {title} ==")

    def add(
        self,
        title: str,
        status: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        payload = QaCheck(
            section=self.current_section,
            title=title,
            status=status,
            message=message,
            details=details or {},
        )
        self.results.append(payload)
        if self.verbose:
            print(f"[{status}] {title}: {message}")
            for key, value in payload.details.items():
                print(f"  - {key}: {json.dumps(to_jsonable(value), ensure_ascii=True)}")

    @property
    def failures(self) -> list[QaCheck]:
        return [item for item in self.results if item.status == FAIL]

    @property
    def warnings(self) -> list[QaCheck]:
        return [item for item in self.results if item.status == WARN]

    def summary_status(self) -> str:
        return "Mal" if self.failures else "Bien"


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def running_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def resolve_mongo_uri(cli_value: str) -> str:
    if cli_value and cli_value.lower() != "auto":
        return cli_value
    if running_in_docker():
        return os.getenv("MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
    return os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true")


def resolve_neo4j_uri(cli_value: str) -> str:
    if cli_value and cli_value.lower() != "auto":
        return cli_value
    if running_in_docker():
        return os.getenv("NEO4J_URI", "bolt://localhost:7687")
    return os.getenv("NEO4J_URI_LOCAL", os.getenv("NEO4J_URI", "bolt://localhost:7687"))


def api_candidates(cli_value: str) -> list[str]:
    if cli_value and cli_value.lower() != "auto":
        return [cli_value.rstrip("/")]

    candidates = []
    env_candidate = os.getenv("POTATOHUB_API_BASE", "").strip()
    if env_candidate:
        candidates.append(env_candidate.rstrip("/"))
    candidates.extend(
        [
            "http://127.0.0.1:8002",
            "http://127.0.0.1:8001",
            "http://localhost:8002",
            "http://localhost:8001",
        ]
    )

    unique: list[str] = []
    seen = set()
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def auto_detect_api_base(cli_value: str, reporter: Reporter) -> tuple[str, dict[str, Any]]:
    client = httpx.Client(timeout=5.0)
    scored: list[tuple[int, str, dict[str, Any]]] = []
    try:
        for base in api_candidates(cli_value):
            try:
                response = client.get(f"{base}/health")
                response.raise_for_status()
                payload = response.json()
                score = 0
                if payload.get("status") == "ok":
                    score += 2
                if payload.get("service") == "PotatoHub API":
                    score += 3
                if "users" in payload:
                    score += 3
                if "neo4j" in payload:
                    score += 3
                if "recipes" in payload:
                    score += 1
                scored.append((score, base.rstrip("/"), payload))
            except Exception:
                continue
    finally:
        client.close()

    if not scored:
        reporter.add(
            "API auto-detect",
            FAIL,
            "No se encontro una API PotatoHub saludable en los puertos probados.",
            {"candidates": api_candidates(cli_value)},
        )
        return "", {}

    scored.sort(key=lambda item: (item[0], item[2].get("recipes", 0), item[1]), reverse=True)
    _, base, payload = scored[0]
    reporter.add(
        "API detectada",
        PASS,
        f"Se usara {base} para las pruebas HTTP.",
        {"health": payload},
    )
    return base, payload


def measure_ms(fn: Callable[[], Any], repeats: int = 5) -> PerformanceMetric:
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    avg_ms = sum(samples) / len(samples)
    return PerformanceMetric(
        title="",
        avg_ms=round(avg_ms, 2),
        min_ms=round(min(samples), 2),
        max_ms=round(max(samples), 2),
        samples=len(samples),
    )


def mongo_stages(node: Any) -> list[str]:
    stages: list[str] = []
    if isinstance(node, dict):
        stage = node.get("stage")
        if stage:
            stages.append(str(stage))
        for key in ("inputStage", "inputStages", "queryPlan", "winningPlan", "shards", "executionStages"):
            child = node.get(key)
            if isinstance(child, list):
                for item in child:
                    stages.extend(mongo_stages(item))
            elif child:
                stages.extend(mongo_stages(child))
    elif isinstance(node, list):
        for item in node:
            stages.extend(mongo_stages(item))
    return stages


def neo4j_profile_operators(plan: Any) -> list[str]:
    operators: list[str] = []

    def visit(node: Any) -> None:
        if node is None:
            return

        operator = getattr(node, "operator_type", None)
        children = getattr(node, "children", None)
        if operator is None and isinstance(node, dict):
            operator = node.get("operatorType") or node.get("operator_type")
            children = node.get("children")

        if operator:
            operators.append(str(operator))

        if children:
            for child in children:
                visit(child)

    visit(plan)
    return operators


def upsert_neo4j_user(session: Any, user_doc: dict) -> None:
    profile = user_doc.get("profile") or {}
    preferences = user_doc.get("preferences") or {}
    preferred_categories = profile.get("preferred_categories") or preferences.get("preferred_categories") or []
    deleted_at = user_doc.get("deleted_at")
    session.run(
        """
        MERGE (u:User {id: $id})
        SET u.name = $name,
            u.email = $email,
            u.status = $status,
            u.role = $role,
            u.source = $source,
            u.seed_persona = $seed_persona,
            u.preferred_categories = $preferred_categories,
            u.favorite_difficulty = $favorite_difficulty,
            u.experience_level = $experience_level,
            u.household_size = $household_size,
            u.city = $city,
            u.updated_at = datetime($updated_at),
            u.last_login_at = datetime($last_login_at),
            u.deleted_at = CASE WHEN $deleted_at = '' THEN null ELSE datetime($deleted_at) END
        SET u.created_at = coalesce(u.created_at, datetime($created_at))
        """,
        id=str(user_doc.get("user_id") or user_doc.get("_id") or ""),
        name=str(user_doc.get("name") or "PotatoHub User"),
        email=str(user_doc.get("email") or user_doc.get("_id") or ""),
        status=str(user_doc.get("status") or "active"),
        role=str(user_doc.get("role") or "user"),
        source=str(user_doc.get("source") or ""),
        seed_persona=user_doc.get("seed_persona"),
        preferred_categories=[str(item).strip().upper() for item in preferred_categories if str(item).strip()],
        favorite_difficulty=str(profile.get("favorite_difficulty") or preferences.get("difficulty") or ""),
        experience_level=str(profile.get("experience_level") or ""),
        household_size=int(profile.get("household_size") or 0),
        city=str(profile.get("city") or ""),
        created_at=(user_doc.get("created_at") or utc_now()).isoformat(),
        updated_at=(user_doc.get("updated_at") or utc_now()).isoformat(),
        last_login_at=(user_doc.get("last_login_at") or user_doc.get("updated_at") or utc_now()).isoformat(),
        deleted_at=deleted_at.isoformat() if isinstance(deleted_at, datetime) else "",
    ).consume()


def build_recommendations(issues: dict[str, int], performance: dict[str, PerformanceMetric]) -> list[str]:
    recommendations: list[str] = []
    if issues.get("mongo_missing_seed_users", 0) > 0:
        recommendations.append("Re-sembrar usuarios seed_v1 y validar la carga en MongoDB.")
    if issues.get("consistency_discrepancies", 0) > 0:
        recommendations.append("Re-sincronizar Neo4j desde MongoDB y volver a correr la validacion cruzada.")
    if issues.get("missing_constraints", 0) > 0:
        recommendations.append("Aplicar restricciones de unicidad en Neo4j para User.id y Recipe.id.")
    if issues.get("missing_compound_index", 0) > 0:
        recommendations.append("Crear o reparar el indice unico compuesto (user_id, recipe_id) en user_recipe_states.")

    mongo_metric = performance.get("mongo_profile")
    if mongo_metric and mongo_metric.avg_ms > 50.0:
        recommendations.append("Revisar explain() de consultas de perfil en MongoDB e indices de users y user_recipe_states.")

    neo4j_metric = performance.get("neo4j_recommendations")
    if neo4j_metric and neo4j_metric.avg_ms > 300.0:
        recommendations.append("Revisar PROFILE de consultas de recomendacion en Neo4j y cardinalidad de relaciones.")

    if not recommendations:
        recommendations.append("No se detectaron optimizaciones urgentes; mantener esta verificacion como gate de CI/CD.")
    return recommendations


def main() -> int:
    parser = argparse.ArgumentParser(description="QA integral para MongoDB y Neo4j en PotatoHub.")
    parser.add_argument("--mongo-uri", default="auto", help="MongoDB URI. Usa 'auto' para detectar desde .env.")
    parser.add_argument("--mongo-db", default=os.getenv("MONGO_DB", "potatohub"), help="Nombre de base de datos MongoDB.")
    parser.add_argument("--neo4j-uri", default="auto", help="Neo4j URI. Usa 'auto' para detectar desde .env.")
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"), help="Usuario Neo4j.")
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", "potatohub123"), help="Password Neo4j.")
    parser.add_argument("--api-base", default="auto", help="Base URL de la API. Usa 'auto' para detectar 8002/8001.")
    parser.add_argument("--expected-seed-users", type=int, default=100, help="Cantidad esperada de usuarios seed_v1.")
    parser.add_argument("--seed-source", default=SEED_SOURCE, help="Valor source esperado para usuarios sembrados.")
    parser.add_argument("--json", action="store_true", help="Imprime tambien el resumen final en JSON.")
    parser.add_argument("--json-out", default="", help="Ruta opcional para guardar el resumen final en JSON.")
    parser.add_argument("--quiet", action="store_true", help="Reduce la salida en consola.")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env")

    reporter = Reporter(verbose=not args.quiet)
    counts: dict[str, Any] = {}
    issues: dict[str, int] = {
        "mongo_missing_seed_users": 0,
        "consistency_discrepancies": 0,
        "missing_constraints": 0,
        "missing_compound_index": 0,
    }
    performance: dict[str, PerformanceMetric] = {}
    cleanup_info: dict[str, Any] = {}

    mongo_uri = resolve_mongo_uri(args.mongo_uri)
    neo4j_uri = resolve_neo4j_uri(args.neo4j_uri)
    api_base, detected_health = auto_detect_api_base(args.api_base, reporter)

    mongo_client = None
    mongo_db = None
    neo4j_driver = None
    http_client = None

    seed_user_ids: list[str] = []
    sample_user_id = ""
    sample_recipe_id = ""
    created_qa_email = ""
    qa_recipe_id = ""
    qa_saved = False
    qa_cooked = False

    try:
        reporter.section("1. Conexion y estado")
        try:
            mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
            mongo_client.admin.command("ping")
            mongo_db = mongo_client[args.mongo_db]
            reporter.add("MongoDB ping", PASS, "Conexion MongoDB operativa.", {"mongo_uri": mongo_uri, "db": args.mongo_db})
        except Exception as exc:
            reporter.add("MongoDB ping", FAIL, "No fue posible conectar a MongoDB.", {"error": str(exc), "mongo_uri": mongo_uri})

        if mongo_db is not None:
            try:
                hello = mongo_client.admin.command("hello")
                reporter.add(
                    "MongoDB hello",
                    PASS,
                    "Handshake MongoDB correcto.",
                    {
                        "isWritablePrimary": bool(hello.get("isWritablePrimary") or hello.get("ismaster")),
                        "setName": hello.get("setName"),
                        "hosts": hello.get("hosts", []),
                    },
                )
            except Exception as exc:
                reporter.add("MongoDB hello", WARN, "No se pudo obtener metadata hello de MongoDB.", {"error": str(exc)})

            try:
                repl_status = mongo_client.admin.command("replSetGetStatus")
                member_states = [member.get("stateStr") for member in repl_status.get("members", [])]
                primary_count = sum(1 for value in member_states if value == "PRIMARY")
                status = PASS if primary_count == 1 else FAIL
                reporter.add(
                    "Replica set MongoDB",
                    status,
                    "Replica set consultado correctamente." if status == PASS else "Replica set sin PRIMARY unico.",
                    {
                        "set": repl_status.get("set"),
                        "member_states": member_states,
                        "ok": repl_status.get("ok"),
                    },
                )
            except OperationFailure as exc:
                reporter.add("Replica set MongoDB", FAIL, "MongoDB no reporta estado de replica set.", {"error": str(exc)})
            except PyMongoError as exc:
                reporter.add("Replica set MongoDB", FAIL, "Error consultando replica set.", {"error": str(exc)})

            collection_names = sorted(mongo_db.list_collection_names())
            missing_collections = [name for name in MONGO_REQUIRED_COLLECTIONS if name not in collection_names]
            reporter.add(
                "Colecciones MongoDB",
                PASS if not missing_collections else FAIL,
                "Colecciones requeridas encontradas." if not missing_collections else "Faltan colecciones requeridas.",
                {"collections": collection_names, "missing": missing_collections},
            )

        try:
            neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
            neo4j_driver.verify_connectivity()
            reporter.add(
                "Neo4j connectivity",
                PASS,
                "Conexion Neo4j operativa.",
                {"neo4j_uri": neo4j_uri, "neo4j_user": args.neo4j_user},
            )
        except Exception as exc:
            reporter.add("Neo4j connectivity", FAIL, "No fue posible conectar a Neo4j.", {"error": str(exc), "neo4j_uri": neo4j_uri})

        if neo4j_driver is not None:
            with neo4j_driver.session() as session:
                try:
                    db_rows = session.run(
                        "SHOW DATABASES YIELD name, currentStatus, home, default RETURN name, currentStatus, home, default"
                    ).data()
                    reporter.add(
                        "Neo4j databases",
                        PASS,
                        "Estado de bases Neo4j consultado.",
                        {"databases": db_rows},
                    )
                except Exception as exc:
                    reporter.add("Neo4j databases", WARN, "No se pudo ejecutar SHOW DATABASES.", {"error": str(exc)})

                constraints = session.run(
                    "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties RETURN name, type, entityType, labelsOrTypes, properties"
                ).data()
                indexes = session.run(
                    "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state RETURN name, type, entityType, labelsOrTypes, properties, state"
                ).data()
                reporter.add(
                    "Neo4j schema",
                    PASS,
                    "Restricciones e indices recuperados.",
                    {"constraint_count": len(constraints), "index_count": len(indexes)},
                )

                required_constraints = {
                    ("NODE", ("User",), ("id",)),
                    ("NODE", ("Recipe",), ("id",)),
                }
                constraint_keys = {
                    (
                        str(item.get("entityType") or ""),
                        tuple(item.get("labelsOrTypes") or []),
                        tuple(item.get("properties") or []),
                    )
                    for item in constraints
                }
                missing_constraints = [item for item in required_constraints if item not in constraint_keys]
                if missing_constraints:
                    issues["missing_constraints"] += len(missing_constraints)
                reporter.add(
                    "Restricciones User.id y Recipe.id",
                    PASS if not missing_constraints else FAIL,
                    "Restricciones de unicidad presentes." if not missing_constraints else "Faltan restricciones de unicidad.",
                    {"missing_constraints": missing_constraints},
                )

        reporter.section("2. Integridad de datos en MongoDB")
        if mongo_db is not None:
            users_col = mongo_db["users"]
            recipes_col = mongo_db["recipes"]
            states_col = mongo_db["user_recipe_states"]
            events_col = mongo_db["user_events"]

            total_users = users_col.count_documents({})
            total_seed_users = users_col.count_documents({"source": args.seed_source, "deleted_at": None})
            total_recipes = recipes_col.count_documents({})
            total_states = states_col.count_documents({})
            total_events = events_col.count_documents({})
            counts.update(
                {
                    "mongo_users_total": total_users,
                    "mongo_seed_users": total_seed_users,
                    "mongo_recipes_total": total_recipes,
                    "mongo_user_recipe_states": total_states,
                    "mongo_user_events": total_events,
                }
            )
            if total_seed_users != args.expected_seed_users:
                issues["mongo_missing_seed_users"] += abs(total_seed_users - args.expected_seed_users)
            reporter.add(
                "Usuarios seed_v1 en MongoDB",
                PASS if total_seed_users == args.expected_seed_users else FAIL,
                "Conteo de usuarios sembrados validado." if total_seed_users == args.expected_seed_users else "Conteo de usuarios sembrados no coincide.",
                {"expected": args.expected_seed_users, "actual": total_seed_users, "total_users": total_users},
            )

            seed_user_ids = list(
                users_col.distinct("_id", {"source": args.seed_source, "deleted_at": None})
            )
            sample_user_id = seed_user_ids[0] if seed_user_ids else ""
            sample_recipe_doc = states_col.find_one({"user_id": sample_user_id}, {"recipe_id": 1}) if sample_user_id else None
            sample_recipe_id = str(sample_recipe_doc.get("recipe_id") or "") if sample_recipe_doc else ""

            user_ids = set(users_col.distinct("_id"))
            recipe_ids = set(recipes_col.distinct("_id"))
            invalid_states = []
            for state in states_col.find({}, {"user_id": 1, "recipe_id": 1}).limit(20000):
                if state.get("user_id") not in user_ids or state.get("recipe_id") not in recipe_ids:
                    invalid_states.append(
                        {"user_id": state.get("user_id"), "recipe_id": state.get("recipe_id")}
                    )
                    if len(invalid_states) >= 10:
                        break
            reporter.add(
                "Referencias en user_recipe_states",
                PASS if not invalid_states else FAIL,
                "Todas las referencias user_id y recipe_id son validas." if not invalid_states else "Se encontraron referencias invalidas en user_recipe_states.",
                {"invalid_samples": invalid_states},
            )

            invalid_events = []
            for event in events_col.find({}, {"user_id": 1, "recipe_id": 1, "action": 1}).limit(50000):
                if event.get("user_id") not in user_ids or event.get("recipe_id") not in recipe_ids:
                    invalid_events.append(
                        {
                            "user_id": event.get("user_id"),
                            "recipe_id": event.get("recipe_id"),
                            "action": event.get("action"),
                        }
                    )
                    if len(invalid_events) >= 10:
                        break
            reporter.add(
                "Referencias en user_events",
                PASS if not invalid_events else FAIL,
                "Todas las referencias en user_events son validas." if not invalid_events else "Se encontraron referencias invalidas en user_events.",
                {"invalid_samples": invalid_events},
            )

            duplicate_pairs = list(
                states_col.aggregate(
                    [
                        {"$group": {"_id": {"user_id": "$user_id", "recipe_id": "$recipe_id"}, "count": {"$sum": 1}}},
                        {"$match": {"count": {"$gt": 1}}},
                        {"$limit": 10},
                    ]
                )
            )
            state_indexes = states_col.index_information()
            has_compound_unique = any(
                tuple(item.get("key") or []) == (("user_id", 1), ("recipe_id", 1)) and bool(item.get("unique"))
                for item in state_indexes.values()
            )
            if not has_compound_unique:
                issues["missing_compound_index"] += 1
            reporter.add(
                "Indice compuesto user_recipe_states",
                PASS if has_compound_unique else FAIL,
                "Indice unico compuesto encontrado." if has_compound_unique else "No existe indice unico compuesto user_id + recipe_id.",
                {"indexes": list(state_indexes.keys())},
            )
            reporter.add(
                "Duplicados user_id + recipe_id",
                PASS if not duplicate_pairs else FAIL,
                "No hay duplicados en el indice compuesto." if not duplicate_pairs else "Se encontraron duplicados en user_recipe_states.",
                {"duplicate_samples": duplicate_pairs},
            )

            event_mismatches = []
            if seed_user_ids:
                event_group = {}
                for row in events_col.aggregate(
                    [
                        {"$match": {"user_id": {"$in": seed_user_ids}}},
                        {
                            "$group": {
                                "_id": {
                                    "user_id": "$user_id",
                                    "recipe_id": "$recipe_id",
                                    "action": "$action",
                                },
                                "count": {"$sum": 1},
                            }
                        },
                    ]
                ):
                    key = (
                        row["_id"]["user_id"],
                        row["_id"]["recipe_id"],
                        row["_id"]["action"],
                    )
                    event_group[key] = int(row["count"])

                for state in states_col.find(
                    {"user_id": {"$in": seed_user_ids}},
                    {"user_id": 1, "recipe_id": 1, "viewed_count": 1, "saved": 1, "cooked": 1},
                ):
                    user_id = str(state["user_id"])
                    recipe_id = str(state["recipe_id"])
                    views = int(state.get("viewed_count") or 0)
                    save_count = event_group.get((user_id, recipe_id, "save"), 0)
                    cook_count = event_group.get((user_id, recipe_id, "cook"), 0)
                    view_count = event_group.get((user_id, recipe_id, "view"), 0)

                    if view_count != views or (bool(state.get("saved")) != (save_count > 0)) or (bool(state.get("cooked")) != (cook_count > 0)):
                        event_mismatches.append(
                            {
                                "user_id": user_id,
                                "recipe_id": recipe_id,
                                "mongo_viewed_count": views,
                                "event_view_count": view_count,
                                "mongo_saved": bool(state.get("saved")),
                                "event_save_count": save_count,
                                "mongo_cooked": bool(state.get("cooked")),
                                "event_cook_count": cook_count,
                            }
                        )
                        if len(event_mismatches) >= 10:
                            break
            reporter.add(
                "Consistencia states vs events",
                PASS if not event_mismatches else WARN,
                "user_recipe_states y user_events estan alineados." if not event_mismatches else "Se detectaron diferencias entre states y events.",
                {"mismatch_samples": event_mismatches},
            )

        reporter.section("3. Integridad de datos en Neo4j")
        neo4j_constraints = []
        if neo4j_driver is not None:
            with neo4j_driver.session() as session:
                total_seed_users_graph = session.run(
                    "MATCH (u:User {source: $source}) RETURN count(u) AS total",
                    source=args.seed_source,
                ).single()["total"]
                total_users_graph = session.run("MATCH (u:User) RETURN count(u) AS total").single()["total"]
                total_recipes_graph = session.run("MATCH (r:Recipe) RETURN count(r) AS total").single()["total"]
                connected_recipes = session.run(
                    "MATCH (r:Recipe) WHERE (r)--() RETURN count(r) AS total"
                ).single()["total"]
                disconnected_recipes = max(int(total_recipes_graph) - int(connected_recipes), 0)
                counts.update(
                    {
                        "neo4j_users_total": int(total_users_graph),
                        "neo4j_seed_users": int(total_seed_users_graph),
                        "neo4j_recipes_total": int(total_recipes_graph),
                        "neo4j_recipes_connected": int(connected_recipes),
                    }
                )
                reporter.add(
                    "Nodos User en Neo4j",
                    PASS if int(total_seed_users_graph) == args.expected_seed_users else FAIL,
                    "Cantidad de nodos User seed_v1 validada." if int(total_seed_users_graph) == args.expected_seed_users else "Cantidad de nodos User seed_v1 no coincide.",
                    {"expected": args.expected_seed_users, "actual": int(total_seed_users_graph), "total_users": int(total_users_graph)},
                )
                reporter.add(
                    "Nodos Recipe en Neo4j",
                    PASS if int(total_recipes_graph) > 0 else FAIL,
                    "Existen nodos Recipe y relaciones en el grafo." if int(total_recipes_graph) > 0 and disconnected_recipes < int(total_recipes_graph) else "No hay suficientes Recipe conectadas en el grafo.",
                    {
                        "total_recipes": int(total_recipes_graph),
                        "connected_recipes": int(connected_recipes),
                        "disconnected_recipes": int(disconnected_recipes),
                    },
                )

                viewed_summary = session.run(
                    """
                    MATCH (:User {source: $source})-[rel:VIEWED]->(:Recipe)
                    RETURN count(rel) AS edges, coalesce(sum(rel.count), 0) AS total_count
                    """,
                    source=args.seed_source,
                ).single()
                saved_edges = session.run(
                    "MATCH (:User {source: $source})-[rel:SAVED]->(:Recipe) RETURN count(rel) AS edges",
                    source=args.seed_source,
                ).single()["edges"]
                cooked_edges = session.run(
                    "MATCH (:User {source: $source})-[rel:COOKED]->(:Recipe) RETURN count(rel) AS edges",
                    source=args.seed_source,
                ).single()["edges"]
                counts.update(
                    {
                        "neo4j_viewed_edges": int(viewed_summary["edges"]),
                        "neo4j_viewed_total_count": int(viewed_summary["total_count"]),
                        "neo4j_saved_edges": int(saved_edges),
                        "neo4j_cooked_edges": int(cooked_edges),
                    }
                )
                reporter.add(
                    "Relaciones VIEWED/SAVED/COOKED",
                    PASS if int(viewed_summary["edges"]) > 0 and int(saved_edges) > 0 and int(cooked_edges) > 0 else WARN,
                    "Relaciones principales encontradas en Neo4j." if int(viewed_summary["edges"]) > 0 else "No se encontraron suficientes relaciones en Neo4j.",
                    {
                        "viewed_edges": int(viewed_summary["edges"]),
                        "viewed_total_count": int(viewed_summary["total_count"]),
                        "saved_edges": int(saved_edges),
                        "cooked_edges": int(cooked_edges),
                    },
                )

                neo4j_constraints = session.run(
                    "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties RETURN name, type, entityType, labelsOrTypes, properties"
                ).data()
                constraint_names = [item.get("name") for item in neo4j_constraints]
                reporter.add(
                    "Restricciones de unicidad Neo4j",
                    PASS if len(neo4j_constraints) >= 2 else WARN,
                    "Se pudieron leer las restricciones del grafo.",
                    {"constraint_names": constraint_names},
                )

        reporter.section("4. Consistencia entre MongoDB y Neo4j")
        discrepancies: list[dict[str, Any]] = []
        user_count_mismatches: list[dict[str, Any]] = []
        if mongo_db is not None and neo4j_driver is not None and seed_user_ids:
            mongo_states = {}
            mongo_user_summary: dict[str, dict[str, int]] = {}
            states_cursor = mongo_db["user_recipe_states"].find(
                {"user_id": {"$in": seed_user_ids}},
                {"user_id": 1, "recipe_id": 1, "viewed_count": 1, "saved": 1, "cooked": 1},
            )
            for state in states_cursor:
                user_id = str(state["user_id"])
                recipe_id = str(state["recipe_id"])
                mongo_states[(user_id, recipe_id)] = {
                    "viewed_count": int(state.get("viewed_count") or 0),
                    "saved": bool(state.get("saved")),
                    "cooked": bool(state.get("cooked")),
                }
                summary = mongo_user_summary.setdefault(
                    user_id,
                    {"viewed_edges": 0, "viewed_total": 0, "saved_edges": 0, "cooked_edges": 0},
                )
                if int(state.get("viewed_count") or 0) > 0:
                    summary["viewed_edges"] += 1
                    summary["viewed_total"] += int(state.get("viewed_count") or 0)
                if bool(state.get("saved")):
                    summary["saved_edges"] += 1
                if bool(state.get("cooked")):
                    summary["cooked_edges"] += 1

            graph_states: dict[tuple[str, str], dict[str, Any]] = {}
            graph_user_summary: dict[str, dict[str, int]] = {}
            with neo4j_driver.session() as session:
                for row in session.run(
                    """
                    MATCH (u:User {source: $source})-[rel:VIEWED]->(r:Recipe)
                    RETURN u.id AS user_id, r.id AS recipe_id, coalesce(rel.count, 1) AS viewed_count
                    """,
                    source=args.seed_source,
                ):
                    key = (str(row["user_id"]), str(row["recipe_id"]))
                    graph_states.setdefault(key, {"viewed_count": 0, "saved": False, "cooked": False})
                    graph_states[key]["viewed_count"] = int(row["viewed_count"] or 0)
                    summary = graph_user_summary.setdefault(
                        key[0],
                        {"viewed_edges": 0, "viewed_total": 0, "saved_edges": 0, "cooked_edges": 0},
                    )
                    summary["viewed_edges"] += 1
                    summary["viewed_total"] += int(row["viewed_count"] or 0)

                for row in session.run(
                    """
                    MATCH (u:User {source: $source})-[rel:SAVED]->(r:Recipe)
                    RETURN u.id AS user_id, r.id AS recipe_id
                    """,
                    source=args.seed_source,
                ):
                    key = (str(row["user_id"]), str(row["recipe_id"]))
                    graph_states.setdefault(key, {"viewed_count": 0, "saved": False, "cooked": False})
                    graph_states[key]["saved"] = True
                    graph_user_summary.setdefault(
                        key[0],
                        {"viewed_edges": 0, "viewed_total": 0, "saved_edges": 0, "cooked_edges": 0},
                    )["saved_edges"] += 1

                for row in session.run(
                    """
                    MATCH (u:User {source: $source})-[rel:COOKED]->(r:Recipe)
                    RETURN u.id AS user_id, r.id AS recipe_id
                    """,
                    source=args.seed_source,
                ):
                    key = (str(row["user_id"]), str(row["recipe_id"]))
                    graph_states.setdefault(key, {"viewed_count": 0, "saved": False, "cooked": False})
                    graph_states[key]["cooked"] = True
                    graph_user_summary.setdefault(
                        key[0],
                        {"viewed_edges": 0, "viewed_total": 0, "saved_edges": 0, "cooked_edges": 0},
                    )["cooked_edges"] += 1

            all_pairs = set(mongo_states) | set(graph_states)
            for key in sorted(all_pairs):
                mongo_state = mongo_states.get(key, {"viewed_count": 0, "saved": False, "cooked": False})
                graph_state = graph_states.get(key, {"viewed_count": 0, "saved": False, "cooked": False})
                if (
                    mongo_state["viewed_count"] != graph_state["viewed_count"]
                    or mongo_state["saved"] != graph_state["saved"]
                    or mongo_state["cooked"] != graph_state["cooked"]
                ):
                    discrepancies.append(
                        {
                            "user_id": key[0],
                            "recipe_id": key[1],
                            "mongo": mongo_state,
                            "neo4j": graph_state,
                        }
                    )
                    if len(discrepancies) >= 10:
                        break

            for user_id in seed_user_ids:
                mongo_summary = mongo_user_summary.get(
                    user_id,
                    {"viewed_edges": 0, "viewed_total": 0, "saved_edges": 0, "cooked_edges": 0},
                )
                graph_summary = graph_user_summary.get(
                    user_id,
                    {"viewed_edges": 0, "viewed_total": 0, "saved_edges": 0, "cooked_edges": 0},
                )
                if mongo_summary != graph_summary:
                    user_count_mismatches.append(
                        {
                            "user_id": user_id,
                            "mongo": mongo_summary,
                            "neo4j": graph_summary,
                        }
                    )
                    if len(user_count_mismatches) >= 10:
                        break

            issues["consistency_discrepancies"] += len(discrepancies) + len(user_count_mismatches)
            reporter.add(
                "Estados Mongo vs relaciones Neo4j",
                PASS if not discrepancies else FAIL,
                "Estados y relaciones estan sincronizados." if not discrepancies else "Se detectaron diferencias por usuario/receta.",
                {"sample_discrepancies": discrepancies},
            )
            reporter.add(
                "Conteo de relaciones por usuario",
                PASS if not user_count_mismatches else FAIL,
                "Los conteos agregados por usuario coinciden." if not user_count_mismatches else "Se detectaron diferencias agregadas por usuario.",
                {"sample_user_mismatches": user_count_mismatches},
            )

        reporter.section("5. Rendimiento y queries tipicas")
        if mongo_db is not None and sample_user_id:
            try:
                metric = measure_ms(
                    lambda: mongo_db["users"].find_one(
                        {"_id": sample_user_id},
                        {
                            "_id": 1,
                            "preferences": 1,
                            "profile": 1,
                            "status": 1,
                            "source": 1,
                        },
                    ),
                    repeats=5,
                )
                metric.title = "Mongo profile query"
                performance["mongo_profile"] = metric
                reporter.add(
                    "Tiempo consulta perfil MongoDB",
                    PASS,
                    "Consulta de perfil de usuario medida.",
                    asdict(metric),
                )
            except Exception as exc:
                reporter.add("Tiempo consulta perfil MongoDB", FAIL, "No se pudo medir la consulta MongoDB.", {"error": str(exc)})

            try:
                explain_plan = mongo_db["user_recipe_states"].find(
                    {"user_id": sample_user_id, "recipe_id": sample_recipe_id}
                ).explain()
                plan_stages = mongo_stages(explain_plan.get("queryPlanner", {}).get("winningPlan", {}))
                uses_index = any(stage in INDEX_SCAN_STAGES for stage in plan_stages)
                reporter.add(
                    "Explain MongoDB user_recipe_states",
                    PASS if uses_index else FAIL,
                    "El explain usa indices." if uses_index else "El explain no muestra uso claro de indices.",
                    {"stages": plan_stages},
                )
            except Exception as exc:
                reporter.add("Explain MongoDB user_recipe_states", FAIL, "No se pudo ejecutar explain() en MongoDB.", {"error": str(exc)})

        if neo4j_driver is not None and sample_user_id:
            with neo4j_driver.session() as session:
                try:
                    metric = measure_ms(
                        lambda: list(session.run(NEO4J_RECOMMENDATION_QUERY, user_id=sample_user_id, limit=6)),
                        repeats=3,
                    )
                    metric.title = "Neo4j recommendation query"
                    performance["neo4j_recommendations"] = metric
                    reporter.add(
                        "Tiempo consulta recomendacion Neo4j",
                        PASS,
                        "Consulta de recomendacion medida.",
                        asdict(metric),
                    )
                except Exception as exc:
                    reporter.add("Tiempo consulta recomendacion Neo4j", FAIL, "No se pudo medir la consulta de recomendacion.", {"error": str(exc)})

                try:
                    result = session.run("PROFILE MATCH (u:User {id: $user_id}) RETURN u", user_id=sample_user_id)
                    list(result)
                    profile = result.consume().profile
                    operators = neo4j_profile_operators(profile)
                    uses_index = any(item in NEO4J_INDEX_OPERATORS for item in operators)
                    reporter.add(
                        "PROFILE Neo4j User lookup",
                        PASS if uses_index else FAIL,
                        "PROFILE muestra operador indexado." if uses_index else "PROFILE no muestra operador indexado.",
                        {"operators": operators},
                    )
                except Exception as exc:
                    reporter.add("PROFILE Neo4j User lookup", FAIL, "No se pudo ejecutar PROFILE en Neo4j.", {"error": str(exc)})

        reporter.section("6. Pruebas CRUD")
        if api_base:
            try:
                http_client = httpx.Client(base_url=api_base, timeout=20.0)
                health_response = http_client.get("/health")
                health_response.raise_for_status()
                reporter.add("API health", PASS, "La API responde correctamente.", {"health": health_response.json()})
            except Exception as exc:
                reporter.add("API health", FAIL, "La API no esta operativa para pruebas CRUD.", {"error": str(exc), "api_base": api_base})

        if mongo_db is not None and neo4j_driver is not None and http_client is not None:
            created_qa_email = f"{QA_EMAIL_PREFIX}-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}@potatohub.local"
            register_payload = {
                "name": "QA Verify",
                "email": created_qa_email,
                "password": "potato123",
            }
            token = ""
            try:
                response = http_client.post("/api/auth/register", json=register_payload)
                response.raise_for_status()
                register_data = response.json()
                token = register_data.get("token", "")
                reporter.add(
                    "Crear usuario de prueba",
                    PASS,
                    "Usuario temporal creado via API.",
                    {"email": created_qa_email},
                )
                mongo_user = mongo_db["users"].find_one({"_id": created_qa_email})
                with neo4j_driver.session() as session:
                    graph_user = session.run(
                        "MATCH (u:User {id: $id}) RETURN u.id AS id, u.status AS status, u.email AS email",
                        id=created_qa_email,
                    ).single()
                reporter.add(
                    "Usuario de prueba en ambas bases",
                    PASS if mongo_user and graph_user else FAIL,
                    "Usuario temporal visible en MongoDB y Neo4j." if mongo_user and graph_user else "Usuario temporal no esta en ambas bases.",
                    {
                        "mongo_exists": bool(mongo_user),
                        "neo4j_exists": bool(graph_user),
                    },
                )

                update_now = utc_now()
                mongo_db["users"].update_one(
                    {"_id": created_qa_email},
                    {
                        "$set": {
                            "preferences.preferred_categories": ["HORNEADA", "CAUSA"],
                            "preferences.difficulty": "medium",
                            "profile.preferred_categories": ["HORNEADA", "CAUSA"],
                            "profile.favorite_difficulty": "medium",
                            "updated_at": update_now,
                        }
                    },
                )
                updated_user = mongo_db["users"].find_one({"_id": created_qa_email})
                with neo4j_driver.session() as session:
                    upsert_neo4j_user(session, updated_user)
                    graph_preferences = session.run(
                        """
                        MATCH (u:User {id: $id})
                        RETURN u.preferred_categories AS preferred_categories,
                               u.favorite_difficulty AS favorite_difficulty
                        """,
                        id=created_qa_email,
                    ).single()
                preferences_ok = bool(graph_preferences) and sorted(graph_preferences["preferred_categories"]) == ["CAUSA", "HORNEADA"] and graph_preferences["favorite_difficulty"] == "medium"
                reporter.add(
                    "Actualizar preferencias",
                    PASS if preferences_ok else FAIL,
                    "Preferencias actualizadas y sincronizadas." if preferences_ok else "Las preferencias no quedaron sincronizadas.",
                    {
                        "mongo_preferences": updated_user.get("preferences"),
                        "neo4j_preferences": dict(graph_preferences) if graph_preferences else None,
                    },
                )

                qa_recipe_doc = mongo_db["recipes"].find_one({}, {"_id": 1})
                qa_recipe_id = str(qa_recipe_doc.get("_id") or "") if qa_recipe_doc else ""
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                if qa_recipe_id:
                    save_response = http_client.post(
                        f"/api/recipes/{qa_recipe_id}/interact",
                        headers=headers,
                        json={"action": "save"},
                    )
                    save_response.raise_for_status()
                    qa_saved = True

                    cook_response = http_client.post(
                        f"/api/recipes/{qa_recipe_id}/interact",
                        headers=headers,
                        json={"action": "cook"},
                    )
                    cook_response.raise_for_status()
                    qa_cooked = True

                    state_doc = mongo_db["user_recipe_states"].find_one(
                        {"user_id": created_qa_email, "recipe_id": qa_recipe_id}
                    )
                    save_events = mongo_db["user_events"].count_documents(
                        {"user_id": created_qa_email, "recipe_id": qa_recipe_id, "action": "save"}
                    )
                    cook_events = mongo_db["user_events"].count_documents(
                        {"user_id": created_qa_email, "recipe_id": qa_recipe_id, "action": "cook"}
                    )
                    with neo4j_driver.session() as session:
                        graph_rel = session.run(
                            """
                            MATCH (u:User {id: $user_id})-[saved:SAVED]->(r:Recipe {id: $recipe_id})
                            OPTIONAL MATCH (u)-[cooked:COOKED]->(r)
                            RETURN count(saved) AS saved_count, count(cooked) AS cooked_count
                            """,
                            user_id=created_qa_email,
                            recipe_id=qa_recipe_id,
                        ).single()

                    interaction_ok = bool(state_doc and state_doc.get("saved") and state_doc.get("cooked")) and save_events > 0 and cook_events > 0 and graph_rel and int(graph_rel["saved_count"]) > 0 and int(graph_rel["cooked_count"]) > 0
                    reporter.add(
                        "Guardar y cocinar receta",
                        PASS if interaction_ok else FAIL,
                        "Las operaciones SAVED y COOKED quedaron reflejadas en ambas bases." if interaction_ok else "Las operaciones SAVED/COOKED no quedaron sincronizadas.",
                        {
                            "recipe_id": qa_recipe_id,
                            "mongo_state": state_doc,
                            "save_events": save_events,
                            "cook_events": cook_events,
                            "neo4j_relations": dict(graph_rel) if graph_rel else None,
                        },
                    )

                delete_now = utc_now()
                mongo_db["users"].update_one(
                    {"_id": created_qa_email},
                    {
                        "$set": {
                            "status": "deleted",
                            "deleted_at": delete_now,
                            "updated_at": delete_now,
                        }
                    },
                )
                soft_deleted_user = mongo_db["users"].find_one({"_id": created_qa_email})
                with neo4j_driver.session() as session:
                    session.run(
                        """
                        MATCH (u:User {id: $id})
                        SET u.status = 'deleted',
                            u.deleted_at = datetime($deleted_at),
                            u.updated_at = datetime($updated_at)
                        """,
                        id=created_qa_email,
                        deleted_at=delete_now.isoformat(),
                        updated_at=delete_now.isoformat(),
                    ).consume()
                    graph_deleted = session.run(
                        "MATCH (u:User {id: $id}) RETURN u.status AS status, toString(u.deleted_at) AS deleted_at",
                        id=created_qa_email,
                    ).single()

                login_after_delete = http_client.post(
                    "/api/auth/login",
                    json={"email": created_qa_email, "password": "potato123"},
                )
                delete_ok = bool(soft_deleted_user and soft_deleted_user.get("deleted_at")) and graph_deleted and graph_deleted["status"] == "deleted" and login_after_delete.status_code in {401, 403}
                reporter.add(
                    "Soft delete de usuario",
                    PASS if delete_ok else FAIL,
                    "Soft delete validado en MongoDB, Neo4j y API." if delete_ok else "Soft delete no quedo reflejado correctamente.",
                    {
                        "mongo_status": soft_deleted_user.get("status") if soft_deleted_user else None,
                        "mongo_deleted_at": soft_deleted_user.get("deleted_at") if soft_deleted_user else None,
                        "neo4j_status": dict(graph_deleted) if graph_deleted else None,
                        "login_status_code": login_after_delete.status_code,
                    },
                )
            except Exception as exc:
                reporter.add("Flujo CRUD", FAIL, "Fallo el flujo CRUD de verificacion.", {"error": str(exc), "qa_email": created_qa_email})
            finally:
                if mongo_db is not None and created_qa_email:
                    cleanup_info["qa_email"] = created_qa_email
                    if qa_recipe_id and (qa_saved or qa_cooked):
                        decrement = {}
                        if qa_saved:
                            decrement["stats.saved"] = -1
                        if qa_cooked:
                            decrement["stats.cooked"] = -1
                        if decrement:
                            mongo_db["recipes"].update_one({"_id": qa_recipe_id}, {"$inc": decrement})
                    mongo_db["user_recipe_states"].delete_many({"user_id": created_qa_email})
                    mongo_db["user_events"].delete_many({"user_id": created_qa_email})
                    mongo_db["users"].delete_one({"_id": created_qa_email})

                if neo4j_driver is not None and created_qa_email:
                    with neo4j_driver.session() as session:
                        session.run("MATCH (u:User {id: $id}) DETACH DELETE u", id=created_qa_email).consume()

        reporter.section("7. Reporte final")
        summary = {
            "estado_general": reporter.summary_status(),
            "counts": to_jsonable(counts),
            "performance_ms": {key: asdict(value) for key, value in performance.items()},
            "discrepancias_encontradas": {
                "checks_fail": len(reporter.failures),
                "checks_warn": len(reporter.warnings),
                "consistency_discrepancies": issues["consistency_discrepancies"],
                "missing_constraints": issues["missing_constraints"],
                "missing_compound_index": issues["missing_compound_index"],
            },
            "recommendaciones": build_recommendations(issues, performance),
            "api_detected_health": detected_health,
            "cleanup": cleanup_info,
        }

        reporter.add(
            "Resumen ejecutivo",
            PASS if not reporter.failures else FAIL,
            f"Estado general: {summary['estado_general']}",
            summary,
        )

        if args.json:
            print("")
            print(json.dumps(to_jsonable(summary), ensure_ascii=True, indent=2))

        if args.json_out:
            output_path = Path(args.json_out)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(to_jsonable(summary), ensure_ascii=True, indent=2), encoding="utf-8")

        return 1 if reporter.failures else 0
    finally:
        if http_client is not None:
            http_client.close()
        if mongo_client is not None:
            mongo_client.close()
        if neo4j_driver is not None:
            neo4j_driver.close()


if __name__ == "__main__":
    raise SystemExit(main())

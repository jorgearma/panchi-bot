#!/usr/bin/env python3
"""
analyzers/data_model.py — Genera DATA_MODEL_MAP.json.

Información detallada de la capa de persistencia: modelos, tablas, campos,
relaciones y qué archivos de cada capa acceden a cada modelo.

Es el mapa de referencia que el planner consulta cuando necesita entender
la estructura de datos antes de modificar lógica de acceso a DB.

Solo se genera si el proyecto tiene ORM o base de datos detectada.

Estructura:
  orm              — ORM detectado (SQLAlchemy, TypeORM, Prisma, …)
  database         — Motor de base de datos (Postgres, MySQL, SQLite, …)
  pattern          — "Manager / Repository" o "Direct DB access"
  connection_files — archivos de conexión a DB
  migrations       — archivos de migración (sin seeds)
  models[]         — {name, table, file, fields[], relationships[], test_file}
  query_files[]    — archivos con acceso a datos
  service_files[]  — servicios que llaman a query_files
  api_files[]      — controllers que llaman a service/query files
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzers.core import (
    FileInfo,
    ModelInfo,
    _walk_repo_models_cache,
    detect_stack,
    find_test_file,
    git_cochange,
    resolve_dependencies,
    walk_repo,
)

DB_ORMS = frozenset({
    "SQLAlchemy", "Django ORM", "TypeORM", "Prisma", "Mongoose",
    "Sequelize", "Drizzle", "Peewee", "Tortoise ORM", "MongoEngine", "PyMongo", "Knex",
})
DB_INFRA = ("SQL", "Postgres", "MySQL", "Mongo", "Redis", "SQLite", "Dynamo")


def _resolve_layer(
    target_files: set[str],
    forward: dict[str, list[str]],
    files_by_path: dict[str, FileInfo],
    role_filter: str | None = None,
) -> list[str]:
    """
    Devuelve archivos que importan a alguno de target_files,
    opcionalmente filtrados por rol.
    """
    result: list[str] = []
    for path, deps in forward.items():
        if not any(t in deps for t in target_files):
            continue
        fi = files_by_path.get(path)
        if not fi:
            continue
        if role_filter and fi.role != role_filter:
            continue
        result.append(path)
    return result


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera DATA_MODEL_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    db_techs = [t for t in stack if t in DB_ORMS]
    db_infra = [t for t in stack if any(k in t for k in DB_INFRA) and t not in DB_ORMS]

    # Si no hay ORM ni infraestructura detectada, saltar (proyecto puro frontend)
    if not db_techs and not db_infra:
        result: dict = {"skipped": True, "reason": "No ORM or database detected in stack"}
        maps_dir = root / ".claude" / "maps"
        maps_dir.mkdir(parents=True, exist_ok=True)
        (maps_dir / "DATA_MODEL_MAP.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return result

    models_cache: list[ModelInfo] = list(_walk_repo_models_cache)
    real_models = [
        m for m in models_cache
        if (
            any(k in m.file for k in ("model", "entit", "domain", "schema.prisma"))
            or m.file in ("models.py", "model.py")
            or (m.fields and len(m.fields) >= 2)
        )
    ]

    migrations = [f.rel_path for f in files if f.role == "migration"]
    seeds = [m for m in migrations if "seed" in m.lower()]
    pure_migrations = [m for m in migrations if "seed" not in m.lower()]
    db_conn = [
        f.rel_path for f in files
        if f.role == "db_connection" and "test" not in f.rel_path.lower()
    ]

    # Archivos con acceso a datos
    db_files = [f for f in files if f.has_db_access and f.role not in ("test", "migration")]
    da_files = [f for f in files if f.role == "data_access"]
    all_query = list({f.rel_path: f for f in db_files + da_files}.values())
    all_query.sort(key=lambda f: f.rel_path)

    has_repo = any(f.role == "data_access" for f in all_query)
    pattern = "Manager / Repository" if has_repo else "Direct DB access"

    # Resolver capas superiores via grafo de dependencias
    prod_files = [f for f in files if f.role not in ("test", "migration")]
    dep_graph = resolve_dependencies(prod_files)
    forward = dep_graph.get("forward", {})
    files_by_path = {f.rel_path: f for f in files}

    query_paths = {f.rel_path for f in all_query}
    service_files = _resolve_layer(query_paths, forward, files_by_path, role_filter="service")
    service_paths = set(service_files)
    api_files = _resolve_layer(service_paths | query_paths, forward, files_by_path, role_filter="controller")

    result = {
        "orm": db_techs[0] if db_techs else None,
        "database": db_infra[0] if db_infra else None,
        "pattern": pattern,
        "connection_files": db_conn,
        "migrations": pure_migrations,
        "seeds": seeds,
        "models": [
            {
                "name": m.name,
                "table": m.table,
                "file": m.file,
                "fields": m.fields,
                "relationships": m.relationships,
                "test_file": find_test_file(m.file, files),
            }
            for m in sorted(real_models, key=lambda x: x.name)
        ],
        "query_files": [f.rel_path for f in all_query[:25]],
        "service_files": service_files[:15],
        "api_files": api_files[:15],
    }

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "DATA_MODEL_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera DATA_MODEL_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd(),
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("DATA_MODEL_MAP.json generado.")

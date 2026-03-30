#!/usr/bin/env python3
"""
analyzers/routing.py — Genera ROUTING_MAP.json.

Este es el primer map que lee el reader. Es pequeño e informa:
  - project_summary: nombre, stack, arquitectura, entry_points
  - glossary: términos de negocio y sus sinónimos (derivados de file stems + stack)
  - domains[]: name, keywords, negative_keywords, priority, preferred_indexes
  - default_constraints: restricciones que aplican a cualquier dominio
  - entry_points: archivos de arranque

Centraliza el enrutamiento real en ROUTING_MAP.json + DOMAIN_INDEX_*.json.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from analyzers.core import (
    FileInfo,
    detect_project_name,
    detect_readme_summary,
    detect_stack,
    infer_architecture,
    scan_structure,
    walk_repo,
)

# ─── Definición de dominios ───────────────────────────────────────────────────

DOMAINS: list[dict] = [
    {
        "name": "api",
        "keywords": [
            "endpoint", "ruta", "blueprint", "HTTP", "request", "response",
            "webhook", "API", "route", "GET", "POST", "PUT", "DELETE", "PATCH",
            "REST", "controller", "handler", "middleware",
        ],
        "negative_keywords": ["migration", "seed", "test"],
        "priority": 1,
        "preferred_indexes": ["DOMAIN_INDEX_api.json"],
    },
    {
        "name": "data",
        "keywords": [
            "modelo", "tabla", "migración", "campo", "relación",
            "ORM", "schema", "base de datos", "database", "model",
            "table", "field", "relationship", "consulta", "query", "filtro",
            "join", "repository", "manager", "acceso a datos", "data access",
        ],
        "negative_keywords": ["test", "fixture"],
        "priority": 2,
        "preferred_indexes": ["DOMAIN_INDEX_data.json", "DATA_MODEL_MAP.json"],
    },
    {
        "name": "services",
        "keywords": [
            "servicio", "integración", "externo", "Twilio", "Stripe", "Redis",
            "Monei", "SMS", "email", "pago", "payment", "service", "integration",
            "external", "SDK", "tercero", "third-party", "webhook",
        ],
        "negative_keywords": ["test", "mock"],
        "priority": 3,
        "preferred_indexes": ["DOMAIN_INDEX_services.json"],
    },
    {
        "name": "ui",
        "keywords": [
            "vista", "componente", "pantalla", "formulario", "plantilla",
            "frontend", "view", "component", "template", "page", "layout",
            "UI", "interfaz", "interface", "render", "HTML", "CSS",
        ],
        "negative_keywords": ["test", "migration"],
        "priority": 4,
        "preferred_indexes": ["DOMAIN_INDEX_ui.json"],
    },
    {
        "name": "jobs",
        "keywords": [
            "tarea", "job", "celery", "queue", "cola", "cron", "programado",
            "worker", "scheduled", "task", "background", "periodic", "interval",
        ],
        "negative_keywords": ["test"],
        "priority": 5,
        "preferred_indexes": ["DOMAIN_INDEX_jobs.json"],
    },
]

# ─── Generación de glosario básico ───────────────────────────────────────────

# Stem suffixes que aportan vocabulario de dominio (no roles técnicos)
_ROLE_SUFFIXES = frozenset({
    "manager", "gestor", "service", "servicio", "blueprint", "router",
    "controller", "handler", "model", "schema", "repository", "repo",
    "adapter", "client", "provider", "job", "task",
})


def _build_glossary(files: list[FileInfo], stack: dict) -> dict[str, list[str]]:
    """
    Deriva glosario mínimo: término → sinónimos.

    Estrategia:
    1. Extrae stems de dominio de archivos de producción (sin role suffixes).
    2. Agrupa variantes del mismo concepto (español/inglés, plural/singular).
    3. Añade entradas del stack (frameworks y servicios externos).

    El glosario es intencional mente pequeño — solo conceptos recurrentes
    (aparecen en ≥2 archivos). Los términos únicos no aportan routing value.
    """
    glossary: dict[str, list[str]] = {}

    # Contar aparición de stems de dominio
    stem_counts: Counter[str] = Counter()
    for fi in files:
        if fi.role in ("test", "migration", "template", "component"):
            continue
        stem = Path(fi.rel_path).stem.lower()
        parts = [p for p in re.split(r"[_\-]", stem) if len(p) > 2]
        domain_parts = [p for p in parts if p not in _ROLE_SUFFIXES]
        for p in domain_parts:
            stem_counts[p] += 1

    # Solo términos que aparecen en ≥2 archivos
    for term, count in stem_counts.items():
        if count >= 2:
            # Variantes simples (plural, inglés-español común)
            synonyms: list[str] = []
            if term.endswith("s"):
                synonyms.append(term[:-1])   # plural → singular
            else:
                synonyms.append(term + "s")  # singular → plural
            glossary[term] = [s for s in synonyms if s != term]

    # Añadir entradas del stack como términos reconocibles
    for pkg in stack:
        key = pkg.lower()
        if key not in glossary:
            glossary[key] = []

    return glossary


# ─── run() ────────────────────────────────────────────────────────────────────

def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera ROUTING_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    name, description = detect_project_name(root)
    if not description:
        description = detect_readme_summary(root)

    folder_structure = scan_structure(root)

    class _MinProj:
        def __init__(self) -> None:
            self.folder_structure = folder_structure
            self.stack = stack

    architecture = infer_architecture(_MinProj())

    entry_points = [f.rel_path for f in files if f.role == "entry_point"]

    lang_counts = Counter(
        f.language for f in files if f.language not in ("html", "sql", "other")
    )
    languages = [lang for lang, _ in lang_counts.most_common()]

    glossary = _build_glossary(files, stack)

    # Filtrar dominios que realmente tienen índice generado
    # (preferred_indexes se valida en runtime por el reader, no aquí)
    result: dict = {
        "project_summary": {
            "name": name,
            "description": description,
            "languages": languages,
            "stack": stack,
            "architecture": architecture,
            "entry_points": entry_points,
        },
        "glossary": glossary,
        "domains": DOMAINS,
        "entry_points": entry_points,
        "default_constraints": [
            "No romper endpoints públicos documentados en CONTRACT_MAP.json",
            "No modificar migraciones ya aplicadas",
            "No cambiar env vars sin actualizar .env.example",
        ],
    }

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "ROUTING_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    p = argparse.ArgumentParser(description="Genera ROUTING_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()

    if args.root:
        repo_root = Path(args.root).resolve()
    else:
        cwd = Path.cwd()
        for candidate in [cwd, *cwd.parents]:
            if (candidate / ".claude").exists():
                repo_root = candidate
                break
        else:
            repo_root = cwd

    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print(f"ROUTING_MAP.json generado en {repo_root / '.claude' / 'maps'}")

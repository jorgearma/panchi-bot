#!/usr/bin/env python3
"""
analyzers/data.py — Genera DOMAIN_INDEX_data.json.

Fusiona la lógica de dominio de db.py + query.py en un índice uniforme.

Candidatos del dominio DATA:
  - "seed"   : data_access files (managers, repositories, DAOs) y
               archivos con acceso directo a DB (has_db_access=True)
  - "review" : model files, db_connection files, migration files relevantes

La información detallada de modelos/tablas vive en DATA_MODEL_MAP.json.
Este índice solo dice al reader QUÉ archivos tocar, no la estructura interna.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from analyzers.core import (
    FileInfo,
    _walk_repo_models_cache,
    detect_stack,
    git_cochange,
    resolve_dependencies,
    walk_repo,
)
from analyzers.domain_index import build_candidate, write_domain_index

# Carpetas de infraestructura que no son candidatos de dominio
_SKIP_DIRS = frozenset({"tests", "test", "__tests__", "spec", "scripts", "seeds"})


def _in_skip_dir(rel_path: str) -> bool:
    return any(p.lower() in _SKIP_DIRS for p in Path(rel_path).parts[:-1])


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera DOMAIN_INDEX_data.json. Escribe en .claude/maps/. Devuelve el dict."""
    cochange = git_cochange(root)
    prod_files = [f for f in files if f.role not in ("test", "migration") and not _in_skip_dir(f.rel_path)]
    dep_graph = resolve_dependencies(prod_files)
    dep_forward = dep_graph.get("forward", {})

    # Modelos conocidos para detectar contratos (tabla/modelo que toca cada archivo)
    models_cache = list(_walk_repo_models_cache)
    model_files: set[str] = {m.file for m in models_cache}
    # model_by_file: archivo → nombres de modelos
    model_by_file: dict[str, list[str]] = {}
    for m in models_cache:
        model_by_file.setdefault(m.file, []).append(m.name)

    candidates: list[dict] = []
    seen: set[str] = set()

    # ── 1. Data access files (seeds) ──────────────────────────────────────────
    for fi in files:
        if fi.role != "data_access" or _in_skip_dir(fi.rel_path):
            continue
        contracts = [f"model:{m}" for m in model_by_file.get(fi.rel_path, [])]
        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            contracts=contracts,
            open_priority="seed",
            confidence_signals=["is_data_access_role"],
        ))
        seen.add(fi.rel_path)

    # ── 2. Archivos con acceso directo a DB (seeds) ───────────────────────────
    for fi in files:
        if fi.rel_path in seen or not fi.has_db_access:
            continue
        if fi.role in ("test", "migration") or _in_skip_dir(fi.rel_path):
            continue
        contracts = [f"model:{m}" for m in model_by_file.get(fi.rel_path, [])]
        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            contracts=contracts,
            open_priority="seed",
            confidence_signals=["has_db_access"],
        ))
        seen.add(fi.rel_path)

    # ── 3. Model files (review) ───────────────────────────────────────────────
    for fi in files:
        if fi.rel_path in seen or fi.role != "model":
            continue
        if _in_skip_dir(fi.rel_path):
            continue
        names = model_by_file.get(fi.rel_path, [])
        contracts = [f"model:{n}" for n in names]
        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            contracts=contracts,
            open_priority="review",
            confidence_signals=["is_model"],
        ))
        seen.add(fi.rel_path)

    # ── 4. DB connection files (review) ───────────────────────────────────────
    for fi in files:
        if fi.rel_path in seen or fi.role != "db_connection":
            continue
        if "test" in fi.rel_path.lower():
            continue
        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            open_priority="review",
            confidence_signals=["is_db_connection"],
        ))
        seen.add(fi.rel_path)

    return write_domain_index(root, "data", candidates)


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera DOMAIN_INDEX_data.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd(),
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("DOMAIN_INDEX_data.json generado.")

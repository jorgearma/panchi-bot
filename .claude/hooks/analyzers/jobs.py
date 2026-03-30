#!/usr/bin/env python3
"""
analyzers/jobs.py — Genera DOMAIN_INDEX_jobs.json.

Candidatos del dominio JOBS:
  - "seed"   : archivos con tareas Celery/RQ declaradas con decoradores
  - "review" : scripts manuales (carpeta jobs/ con función main/run)

Cada candidato lleva contracts[] = ["job:nombre_funcion", "trigger:cron|interval|manual"]
"""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

from analyzers.core import FileInfo, detect_stack, git_cochange, resolve_dependencies, walk_repo
from analyzers.domain_index import build_candidate, write_domain_index

RE_CRON = re.compile(r'\d+\s+\d+\s+\*\s+\*\s+\*|\*/\d+|\bcron\b', re.IGNORECASE)
RE_INTERVAL = re.compile(r'every\s+\d+|interval\s*=|countdown\s*=', re.IGNORECASE)
RE_CELERY_TASK = re.compile(r'@\w+\.task|@shared_task|@app\.task')

_SKIP_DIRS = frozenset({"scripts"})


def _detect_scheduler(files: list[FileInfo], stack: dict) -> str | None:
    for name in stack:
        key = name.lower()
        if "celery" in key:
            return "celery"
        if key == "rq":
            return "rq"
        if "apscheduler" in key:
            return "apscheduler"
    for fi in files:
        for imp in fi.imports_external:
            low = imp.lower()
            if low == "celery":
                return "celery"
            if low == "rq":
                return "rq"
            if low == "apscheduler":
                return "apscheduler"
    return None


def _celery_jobs_in_file(fi: FileInfo, root: Path) -> list[dict]:
    """Extrae tareas Celery: devuelve [{function, trigger, schedule}]."""
    try:
        source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not RE_CELERY_TASK.search(source):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    jobs: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_task = False
        trigger = "manual"
        schedule = None
        for dec in node.decorator_list:
            try:
                ds = ast.unparse(dec) if hasattr(ast, "unparse") else str(dec)
            except Exception:
                ds = ""
            if "task" in ds.lower() or "shared_task" in ds.lower():
                is_task = True
            if RE_CRON.search(ds):
                trigger = "cron"
                schedule = ds
            elif RE_INTERVAL.search(ds):
                trigger = "interval"
                schedule = ds
        if is_task:
            jobs.append({"function": node.name, "trigger": trigger, "schedule": schedule})
    return jobs


def _rq_jobs_in_file(fi: FileInfo, root: Path) -> list[dict]:
    """Extrae jobs RQ: devuelve [{function, trigger, schedule}]."""
    try:
        source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if "@job" not in source and "enqueue" not in source:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    jobs: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_job = any(
            "job" in (ast.unparse(dec) if hasattr(ast, "unparse") else "").lower()
            for dec in node.decorator_list
        )
        if is_job:
            jobs.append({"function": node.name, "trigger": "manual", "schedule": None})
    return jobs


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera DOMAIN_INDEX_jobs.json. Escribe en .claude/maps/. Devuelve el dict."""
    scheduler = _detect_scheduler(files, stack)
    cochange = git_cochange(root)
    prod = [f for f in files if f.role not in ("test", "migration")]
    dep_forward = resolve_dependencies(prod).get("forward", {})

    candidates: list[dict] = []
    seen: set[str] = set()

    # ── 1. Celery / RQ seeds ──────────────────────────────────────────────────
    for fi in files:
        if fi.language != "python":
            continue
        jobs: list[dict] = []
        sig = []
        if scheduler == "celery":
            jobs = _celery_jobs_in_file(fi, root)
            sig = ["has_celery_decorator"]
        elif scheduler == "rq":
            jobs = _rq_jobs_in_file(fi, root)
            sig = ["has_rq_decorator"]
        if not jobs:
            continue

        contracts = []
        for j in jobs:
            contracts.append(f"job:{j['function']}")
            contracts.append(f"trigger:{j['trigger']}")

        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            contracts=contracts,
            open_priority="seed",
            confidence_signals=sig,
        ))
        seen.add(fi.rel_path)

    # ── 2. Manual job scripts (review) ────────────────────────────────────────
    for fi in files:
        if fi.rel_path in seen or fi.language != "python":
            continue
        parts = Path(fi.rel_path).parts
        if any(p.lower() in _SKIP_DIRS for p in parts[:-1]):
            continue
        if "job" not in fi.rel_path.lower():
            continue
        if "main" not in fi.functions and "run" not in fi.functions:
            continue
        fn = "main" if "main" in fi.functions else "run"
        contracts = [f"job:{fn}", "trigger:manual"]
        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            contracts=contracts,
            open_priority="review",
            confidence_signals=["is_manual_job"],
        ))
        seen.add(fi.rel_path)

    return write_domain_index(root, "jobs", candidates)


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera DOMAIN_INDEX_jobs.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd(),
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("DOMAIN_INDEX_jobs.json generado.")

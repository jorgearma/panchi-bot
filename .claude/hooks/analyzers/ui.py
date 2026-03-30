#!/usr/bin/env python3
"""
analyzers/ui.py — Genera DOMAIN_INDEX_ui.json.

Candidatos del dominio UI:
  - "seed"   : componentes y templates con contenido real
  - "review" : archivos de routing frontend (controllers que renderizan vistas)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from analyzers.core import (
    FileInfo,
    detect_stack,
    git_cochange,
    resolve_dependencies,
    walk_repo,
)
from analyzers.domain_index import build_candidate, write_domain_index

UI_FRAMEWORKS = frozenset({"React", "Vue", "Angular", "Svelte", "Solid", "Next.js", "Nuxt.js", "Gatsby"})
TEMPLATE_ENGINES = frozenset({"Jinja2", "Handlebars", "Nunjucks"})


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera DOMAIN_INDEX_ui.json. Escribe en .claude/maps/. Devuelve el dict."""
    cochange = git_cochange(root)
    prod_files = [f for f in files if f.role not in ("test", "migration")]
    dep_graph = resolve_dependencies(prod_files)
    dep_forward = dep_graph.get("forward", {})

    candidates: list[dict] = []
    seen: set[str] = set()

    # ── 1. Templates y componentes (seeds) ────────────────────────────────────
    for fi in files:
        if fi.role not in ("template", "component"):
            continue
        signals: list[str] = []
        if fi.role == "template":
            signals.append("is_template")
        else:
            signals.append("is_component")

        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            open_priority="seed",
            confidence_signals=signals,
        ))
        seen.add(fi.rel_path)

    # ── 2. Controllers que renderizan vistas (review) ─────────────────────────
    for fi in files:
        if fi.rel_path in seen or fi.role != "controller":
            continue
        # Solo incluir si hay indicios de render (imports de template engine o
        # palabras clave de render en funciones)
        has_render = any(
            kw in fi.rel_path.lower()
            for kw in ("view", "template", "render", "page", "ui")
        ) or any(
            kw in (fn.lower() for fn in fi.functions)
            for kw in ("render", "template", "view")
        )
        if not has_render:
            continue

        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            open_priority="review",
            confidence_signals=["is_view_router"],
        ))
        seen.add(fi.rel_path)

    return write_domain_index(root, "ui", candidates)


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera DOMAIN_INDEX_ui.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd(),
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("DOMAIN_INDEX_ui.json generado.")

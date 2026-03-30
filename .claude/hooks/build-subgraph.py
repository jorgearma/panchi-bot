#!/usr/bin/env python3
"""
build-subgraph.py — Pre-loader: enriquece reader-context.json con el subgrafo real de dependencias.

Corre entre el reader y el planner. Lee:
  - .claude/runtime/reader-context.json    (seeds: files_to_open)
  - .claude/maps/DEPENDENCY_MAP.json       (grafo resuelto de imports reales)

Escribe de vuelta en reader-context.json:
  - dependency_graph: subgrafo filtrado (arcos de seeds + deps directas, sin hubs)
  - dependency_context: resumen pre-digerido — callers, deps directas, hubs omitidos
  - files_to_review: expandido con nodos relevantes y hints descriptivos

Estrategia anti-ruido:
  - Hubs (out-degree >= HUB_MIN_DEGREE o __init__.py): se anotan pero NO se expanden.
    Esto evita que un __init__.py agregador llene el contexto con módulos irrelevantes.
  - Cada nodo descubierto recibe un hint que explica su relación concreta con el seed:
    quién lo llama, de quién depende, y el riesgo real si se modifica.
  - dependency_context organiza la info en callers (riesgo de rotura) y deps (contexto
    de implementación) para que el planner no tenga que inferirlo del grafo crudo.
"""

from __future__ import annotations

import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PLUGIN_DIR = Path(__file__).resolve().parents[1]
RUNTIME    = PLUGIN_DIR / "runtime"
MAPS_DIR   = PLUGIN_DIR / "maps"

READER_CONTEXT_PATH = RUNTIME / "reader-context.json"
DEPENDENCY_MAP_PATH = MAPS_DIR / "DEPENDENCY_MAP.json"

# BFS forward depth-2: seeds → sus imports → imports de esos imports
# BFS reverse depth-1: quién importa directamente a los seeds (callers inmediatos)
FORWARD_DEPTH = 2
REVERSE_DEPTH = 1

# Nodos con out-degree >= HUB_MIN_DEGREE en el grafo forward son "hubs":
# se incluyen como aristas pero sus vecinos NO se expanden (evita explosión).
# También: cualquier __init__.py se trata como hub.
HUB_MIN_DEGREE = 5

# Roles que se excluyen de files_to_review (poco valor, mucho ruido)
_SKIP_ROLES = frozenset({"test", "migration", "config", "other", "entry_point"})


@dataclass
class NodeOrigin:
    """Cómo fue descubierto un nodo en el BFS."""
    seed: str
    direction: str        # "forward" | "reverse"
    depth: int
    via: Optional[str]    # nodo intermedio si depth > 1, None si depth <= 1


def is_hub(path: str, forward: dict[str, list[str]]) -> bool:
    """Un nodo es hub si es __init__.py o tiene demasiados vecinos forward."""
    if Path(path).name == "__init__.py":
        return True
    return len(forward.get(path, [])) >= HUB_MIN_DEGREE


def bfs_forward(
    forward: dict[str, list[str]],
    seeds: set[str],
    depth: int,
) -> tuple[dict[str, list[str]], dict[str, NodeOrigin], list[str]]:
    """
    BFS forward desde seeds hasta `depth` saltos.
    Detiene la expansión en hubs: los registra pero no visita sus vecinos.

    Returns:
      subgraph   — {src: [vecinos]} con todas las aristas recorridas
      origins    — {node: NodeOrigin} para cada nodo no-seed descubierto
      hubs_found — rutas de nodos identificados como hubs
    """
    subgraph: dict[str, list[str]] = {}
    origins: dict[str, NodeOrigin] = {}
    hubs_found: list[str] = []
    visited: set[str] = set(seeds)

    # (node, level, via_node, origin_seed)
    queue: deque[tuple[str, int, Optional[str], str]] = deque()
    for seed in seeds:
        queue.append((seed, 0, None, seed))

    while queue:
        node, level, via, seed = queue.popleft()
        neighbors = forward.get(node, [])
        if neighbors:
            subgraph[node] = neighbors

        # Registrar origen para nodos no-seed
        if node not in seeds and node not in origins:
            origins[node] = NodeOrigin(
                seed=seed,
                direction="forward",
                depth=level,
                via=via,
            )

        # En hubs: anotar pero no expandir
        if node not in seeds and is_hub(node, forward):
            if node not in hubs_found:
                hubs_found.append(node)
            continue

        if level < depth:
            # via para el siguiente nivel: si estamos en nivel 0 no hay intermedio
            next_via = node if level >= 1 else None
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, level + 1, next_via, seed))

    return subgraph, origins, hubs_found


def bfs_reverse(
    reverse: dict[str, list[str]],
    seeds: set[str],
    depth: int,
) -> tuple[dict[str, NodeOrigin], dict[str, str]]:
    """
    BFS reverse desde seeds hasta `depth` saltos.

    Returns:
      origins   — {caller: NodeOrigin}
      caller_of — {caller: seed_que_llama} solo para callers directos (depth=1)
    """
    origins: dict[str, NodeOrigin] = {}
    caller_of: dict[str, str] = {}
    visited: set[str] = set(seeds)
    queue: deque[tuple[str, int, str]] = deque()

    for seed in seeds:
        queue.append((seed, 0, seed))

    while queue:
        node, level, seed = queue.popleft()
        if level < depth:
            for caller in reverse.get(node, []):
                if caller not in visited:
                    visited.add(caller)
                    origins[caller] = NodeOrigin(
                        seed=seed,
                        direction="reverse",
                        depth=level + 1,
                        via=None,
                    )
                    if level == 0:
                        caller_of[caller] = seed
                    queue.append((caller, level + 1, seed))

    return origins, caller_of


def make_hint(path: str, origin: NodeOrigin) -> str:
    """Hint descriptivo que explica la relación concreta del archivo con el seed."""
    seed_name = Path(origin.seed).name
    seed_stem = Path(origin.seed).stem

    if origin.direction == "reverse":
        return (
            f"Importa directamente {seed_name} — "
            f"revisar si cambia la firma pública de {seed_stem}"
        )
    # forward
    if origin.depth == 1:
        return (
            f"Depende directamente de {seed_name} — "
            f"{seed_stem} lo importa, contexto de implementación"
        )
    via_name = Path(origin.via).name if origin.via else "?"
    return (
        f"Dep. transitiva de {seed_name} via {via_name} — "
        f"revisar solo si se modifica {Path(origin.via).stem if origin.via else via_name}"
    )


def main() -> int:
    # ── Cargar reader-context ──────────────────────────────────────────────────
    if not READER_CONTEXT_PATH.exists():
        print("build-subgraph: reader-context.json no encontrado, omitiendo.", file=sys.stderr)
        return 0

    try:
        ctx = json.loads(READER_CONTEXT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"build-subgraph: error leyendo reader-context.json: {e}", file=sys.stderr)
        return 1

    # ── Cargar DEPENDENCY_MAP ──────────────────────────────────────────────────
    if not DEPENDENCY_MAP_PATH.exists():
        print("build-subgraph: DEPENDENCY_MAP.json no encontrado — omitiendo.", file=sys.stderr)
        return 0

    try:
        dep_map = json.loads(DEPENDENCY_MAP_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"build-subgraph: error leyendo DEPENDENCY_MAP.json: {e}", file=sys.stderr)
        return 1

    forward: dict[str, list[str]] = dep_map.get("forward", {})
    reverse: dict[str, list[str]] = dep_map.get("reverse", {})
    nodes:   dict[str, dict]      = dep_map.get("nodes", {})
    cycles:  list[str]            = dep_map.get("cycles", [])

    # ── Seeds desde files_to_open ──────────────────────────────────────────────
    seeds = {item["path"] for item in ctx.get("files_to_open", []) if "path" in item}
    if not seeds:
        print("build-subgraph: no hay seeds en files_to_open, omitiendo.", file=sys.stderr)
        return 0

    # ── BFS ────────────────────────────────────────────────────────────────────
    fwd_subgraph, fwd_origins, hubs_found = bfs_forward(forward, seeds, FORWARD_DEPTH)
    rev_origins, caller_of = bfs_reverse(reverse, seeds, REVERSE_DEPTH)

    # ── Construir dependency_graph (filtrado) ──────────────────────────────────
    # Solo incluye arcos relevantes: seeds y sus deps directas (no hubs), más callers.
    # Los arcos de hubs quedan en dependency_context.hubs_not_expanded.
    dependency_graph: dict[str, list[str]] = {}

    for src, deps in fwd_subgraph.items():
        origin = fwd_origins.get(src)
        if src in seeds:
            # Seed: incluir todos sus arcos directos (el planner los necesita completos)
            dependency_graph[src] = deps
        elif origin and origin.depth == 1 and src not in hubs_found:
            # Dep. directa no-hub: incluir sus arcos (contexto de implementación útil)
            dependency_graph[src] = deps
        # Hubs y depth>1: excluidos — su info va en dependency_context

    # Callers directos de seeds (reverse depth=1)
    for caller, seed in caller_of.items():
        if Path(caller).name != "__init__.py":
            existing = dependency_graph.setdefault(caller, [])
            if seed not in existing:
                existing.append(seed)

    # ── Construir dependency_context ──────────────────────────────────────────
    # Resumen pre-digerido para el planner: no necesita inferir relaciones del grafo.

    # Qué usan directamente los seeds (deps directas forward, excluyendo hubs)
    seed_dep_map: dict[str, list[str]] = {}
    for src, deps in fwd_subgraph.items():
        if src in seeds:
            for dep in deps:
                seed_dep_map.setdefault(dep, []).append(src)

    dependency_context: dict = {
        "seeds": sorted(seeds),
        "callers_of_seeds": [
            {
                "file": caller,
                "calls_into": seed,
                "risk": f"puede romper si cambia la firma pública de {Path(seed).stem}",
            }
            for caller, seed in sorted(caller_of.items())
            if Path(caller).name != "__init__.py"
        ],
        "seed_dependencies": [
            {
                "file": dep,
                "used_by": users if len(users) > 1 else users[0],
            }
            for dep, users in sorted(seed_dep_map.items())
        ],
        "hubs_not_expanded": sorted(hubs_found),
    }

    # Ciclos que involucran seeds (dato crítico para el planner)
    seed_cycles = [c for c in cycles if any(s in c for s in seeds)]
    if seed_cycles:
        dependency_context["cycles_involving_seeds"] = seed_cycles

    # ── Limpiar entradas previas de build-subgraph (idempotencia) ─────────────
    # Dos estrategias combinadas para garantizar limpieza en cualquier escenario:
    #   1. Por path exacto: usa _subgraph_added (tracking formal, desde esta versión).
    #   2. Por hint pattern: limpia entradas del build-subgraph antiguo sin tracking.
    # Las entradas del reader nunca tienen el hint genérico ni están en _subgraph_added.
    prev_added: set[str] = set(ctx.pop("_subgraph_added", []))
    ctx["files_to_review"] = [
        f for f in ctx.get("files_to_review", [])
        if f.get("path") not in prev_added
        and not f.get("hint", "").startswith("Descubierto via grafo de dependencias")
    ]

    # ── Descubrir nodos nuevos para files_to_review ────────────────────────────
    already_listed = (
        {item["path"] for item in ctx.get("files_to_open", [])} |
        {item["path"] for item in ctx.get("files_to_review", [])}
    )

    all_origins: dict[str, NodeOrigin] = {**fwd_origins, **rev_origins}

    new_entries: list[dict] = []
    for path in sorted(all_origins.keys()):
        if path in already_listed or path in seeds:
            continue

        # Hubs: están en dependency_context.hubs_not_expanded, no en files_to_review
        if path in hubs_found:
            continue

        origin = all_origins[path]
        node_meta = nodes.get(path, {})
        role = node_meta.get("role", "other")

        if role in _SKIP_ROLES:
            continue

        symbols     = node_meta.get("symbols", [])
        top_symbols = [s["name"] for s in symbols[:3] if "name" in s]

        entry: dict = {
            "path": path,
            "hint": make_hint(path, origin),
            "test_file": None,
        }
        if top_symbols:
            entry["key_symbols"] = top_symbols
        new_entries.append(entry)

    # ── Escribir reader-context.json enriquecido ───────────────────────────────
    ctx["dependency_graph"]   = dependency_graph
    ctx["dependency_context"] = dependency_context
    ctx["_subgraph_added"]    = [e["path"] for e in new_entries]
    if new_entries:
        ctx.setdefault("files_to_review", [])
        ctx["files_to_review"].extend(new_entries)

    READER_CONTEXT_PATH.write_text(
        json.dumps(ctx, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # ── Reporte ────────────────────────────────────────────────────────────────
    n_edges   = sum(len(v) for v in dependency_graph.values())
    n_callers = len(dependency_context["callers_of_seeds"])
    n_deps    = len(dependency_context["seed_dependencies"])
    print(f"  Subgrafo: {len(dependency_graph)} nodos, {n_edges} aristas "
          f"(fwd-depth={FORWARD_DEPTH}, rev-depth={REVERSE_DEPTH})")
    print(f"  Callers de seeds: {n_callers}  |  Deps directas: {n_deps}")
    if hubs_found:
        print(f"  Hubs omitidos (no expandidos): {', '.join(Path(h).name for h in hubs_found)}")
    if new_entries:
        print(f"  Nodos nuevos en files_to_review: {len(new_entries)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

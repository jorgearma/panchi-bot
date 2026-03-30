"""
analyzers/dependency.py — Genera DEPENDENCY_MAP.json con el grafo completo de dependencias.

El grafo tiene tres capas:
  - forward:  {archivo → [archivos que importa]}   (qué usa cada módulo)
  - reverse:  {archivo → [archivos que lo importan]} (quién consume cada módulo)
  - nodes:    {archivo → {role, symbols[{name,line,end_line,kind}]}} (símbolos con rangos)

El reader usa este MAP para hacer BFS desde los archivos semilla y entregar al planner
el subgrafo exacto relevante a la petición, incluyendo puntos de entrada y consumidores.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from analyzers.core import (
    FileInfo,
    resolve_dependencies,
    detect_dependency_cycles,
)

# Detecta llamadas: app.register_blueprint(var_name)
RE_REGISTER_BP = re.compile(r'\.register_blueprint\s*\(\s*(\w+)')
# Detecta definiciones de Blueprint en módulos: bp = Blueprint('name', __name__)
RE_BLUEPRINT_VAR = re.compile(r'^(\w+)\s*=\s*Blueprint\s*\(', re.MULTILINE)


def _add_blueprint_edges(
    source_files: list[FileInfo],
    root: Path,
    forward: dict[str, list[str]],
    reverse: dict[str, list[str]],
) -> int:
    """
    Detecta register_blueprint(x) y añade aristas explícitas al grafo.

    Resuelve x mirando:
    1. Funciones y clases exportadas por cada archivo (fi.functions, fi.classes)
    2. Variables Blueprint definidas a nivel de módulo (bp = Blueprint(...))

    Retorna el número de aristas nuevas añadidas.
    """
    # Índice: nombre de símbolo → archivo que lo define
    symbol_to_file: dict[str, str] = {}
    for fi in source_files:
        # Funciones y clases
        for sym in (fi.classes + fi.functions):
            if sym not in symbol_to_file:
                symbol_to_file[sym] = fi.rel_path
        # Variables Blueprint de módulo (no capturadas por AST como funciones/clases)
        try:
            src = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
            if "Blueprint(" in src:
                for m in RE_BLUEPRINT_VAR.finditer(src):
                    bp_var = m.group(1)
                    if bp_var not in symbol_to_file:
                        symbol_to_file[bp_var] = fi.rel_path
        except OSError:
            pass

    added = 0
    for fi in source_files:
        try:
            source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "register_blueprint" not in source:
            continue

        existing_deps = set(forward.get(fi.rel_path, []))
        for m in RE_REGISTER_BP.finditer(source):
            var_name = m.group(1)
            dep_file = symbol_to_file.get(var_name)
            if not dep_file or dep_file == fi.rel_path or dep_file in existing_deps:
                continue
            # Arista nueva: fi depende de dep_file vía register_blueprint
            forward.setdefault(fi.rel_path, [])
            forward[fi.rel_path].append(dep_file)
            forward[fi.rel_path].sort()
            existing_deps.add(dep_file)
            reverse.setdefault(dep_file, [])
            if fi.rel_path not in reverse[dep_file]:
                reverse[dep_file].append(fi.rel_path)
                reverse[dep_file].sort()
            added += 1

    return added


_TEST_FOLDERS   = frozenset({"tests", "test", "__tests__", "spec"})
_SCRIPT_FOLDERS = frozenset({"scripts", "migrations", "seeds"})


def _is_noise_file(rel_path: str, role: str) -> bool:
    """True si el archivo no pertenece al grafo de producción (tests, scripts, migrations)."""
    parts = Path(rel_path).parts
    folders = {p.lower() for p in parts[:-1]}
    if folders & (_TEST_FOLDERS | _SCRIPT_FOLDERS):
        return True
    if role in ("test", "migration"):
        return True
    stem = parts[-1].lower() if parts else ""
    return stem.startswith("test_") or stem.endswith("_test.py") or "_test." in stem


def _build_node(fi: FileInfo) -> dict:
    """Construye el nodo enriquecido para un archivo: role + símbolos con rangos de línea."""
    fn_by_start = {(fn.name, fn.start_line): fn for fn in fi.function_infos}
    fn_any      = {fn.name: fn for fn in fi.function_infos}  # fallback: última aparición

    symbols = []
    for name, line in sorted(fi.symbols_with_lines.items(), key=lambda x: x[1]):
        kind = "class" if name in fi.classes else "function"
        entry: dict = {"name": name, "line": line, "kind": kind}
        fn = fn_by_start.get((name, line)) or fn_any.get(name)
        if fn:
            entry["end_line"] = max(fn.end_line, line)  # garantiza end_line >= line
        symbols.append(entry)
    return {
        "role":    fi.role,
        "symbols": symbols[:20],
    }


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera DEPENDENCY_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""

    # Excluir tests, scripts y migrations — solo código de producción
    source_files = [f for f in files if not _is_noise_file(f.rel_path, f.role)]

    # ── Grafo bidireccional ────────────────────────────────────────────────────
    graph   = resolve_dependencies(source_files)
    forward = graph["forward"]   # {src: [dep, ...]}
    reverse = graph["reverse"]   # {dep: [src, ...]}

    # ── Entry points ──────────────────────────────────────────────────────────
    entry_points = [f.rel_path for f in source_files if f.role == "entry_point"]

    # ── Nodos enriquecidos (solo archivos que participan en el grafo) ──────────
    graph_paths = set(forward.keys()) | set(reverse.keys()) | set(entry_points)
    file_map    = {f.rel_path: f for f in source_files}

    nodes: dict[str, dict] = {}
    for path in sorted(graph_paths):
        fi = file_map.get(path)
        if fi:
            nodes[path] = _build_node(fi)

    # ── register_blueprint: aristas extra no capturadas por imports ───────────
    bp_edges_added = _add_blueprint_edges(source_files, root, forward, reverse)

    # Recalcular graph_paths tras las aristas nuevas
    graph_paths = set(forward.keys()) | set(reverse.keys()) | set(entry_points)

    # Añadir nodos nuevos descubiertos vía register_blueprint
    for path in sorted(graph_paths - set(nodes.keys())):
        fi = file_map.get(path)
        if fi:
            nodes[path] = _build_node(fi)

    # ── Ciclos de dependencia ─────────────────────────────────────────────────
    raw_cycles = detect_dependency_cycles(forward)
    cycles     = [" → ".join(c) for c in raw_cycles[:10]]

    # ── Stats ─────────────────────────────────────────────────────────────────
    stats = {
        "total_files":          len(source_files),
        "connected_files":      len(graph_paths),
        "edges":                sum(len(v) for v in forward.values()),
        "cycles_found":         len(raw_cycles),
        "blueprint_edges_added": bp_edges_added,
    }

    result = {
        "entry_points": entry_points,
        "forward":      forward,
        "reverse":      reverse,
        "nodes":        nodes,
        "cycles":       cycles,
        "stats":        stats,
    }

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    out_path = maps_dir / "DEPENDENCY_MAP.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result

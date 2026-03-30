#!/usr/bin/env python3
"""
analyzers/api.py — Genera DOMAIN_INDEX_api.json.

Candidatos del dominio API:
  - "seed"   : archivos con rutas definidas (blueprints/routers con @.route)
  - "review" : middleware, auth decorators, schema/validator files

Cada candidato lleva contracts[] = ["METHOD /prefix/route", ...] para que
el planner sepa qué endpoints proteger sin abrir CONTRACT_MAP.json.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from analyzers.core import FileInfo, detect_stack, find_test_file, walk_repo
from analyzers.domain_index import build_candidate, write_domain_index

# ─── Patrones ─────────────────────────────────────────────────────────────────

AUTH_DECORATORS = frozenset({
    "login_required", "jwt_required", "token_required",
    "require_auth", "permission_required", "auth_required",
})
KNOWN_FRAMEWORKS = frozenset({"Flask", "FastAPI", "Express", "Fastify", "NestJS"})

RE_SCHEMA_FILE = re.compile(r"from pydantic|class\s+\w+Schema|@dataclass", re.MULTILINE)
RE_BLUEPRINT = re.compile(
    r'(\w+)\s*=\s*Blueprint\s*\(\s*["\']([^"\']+)["\']'
    r'(?:.*?url_prefix\s*=\s*["\']([^"\']+)["\'])?',
    re.DOTALL,
)
RE_ROUTE = re.compile(
    r'@(\w+)\.route\s*\(\s*["\']([^"\']+)["\'](?:[^)]*methods\s*=\s*\[([^\]]+)\])?[^)]*\)'
)
RE_METHODS = re.compile(r'["\'](\w+)["\']')
SCHEMA_DIRS = frozenset({"schemas", "serializers", "validators"})


# ─── Extracción de rutas Flask ────────────────────────────────────────────────

def _extract_routes_regex(source: str, bp_vars: dict) -> dict:
    """Fallback regex cuando hay SyntaxError."""
    if not bp_vars:
        return bp_vars
    for m in RE_ROUTE.finditer(source):
        bp_var = m.group(1)
        route_path = m.group(2)
        methods_raw = m.group(3) or '"GET"'
        methods = RE_METHODS.findall(methods_raw)
        pos = m.end()
        fn_match = re.search(r'def\s+(\w+)\s*\(', source[pos:pos + 200])
        if not fn_match:
            continue
        func_name = fn_match.group(1)
        ep = {
            "function": func_name,
            "line": source[: m.start()].count("\n") + 1,
            "methods": methods or ["GET"],
            "route": route_path,
            "auth_required": False,
        }
        target = bp_vars.get(bp_var) or list(bp_vars.values())[0]
        target["endpoints"].append(ep)
    return bp_vars


def _extract_routes_ast(source: str, bp_vars: dict) -> dict:
    """Parseo AST para extraer endpoints con decoradores."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_routes_regex(source, bp_vars)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        route_info = None
        auth_req = False

        for dec in node.decorator_list:
            try:
                dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
            except Exception:
                dec_str = ""

            dec_base = dec_str.split("(")[0].split(".")[-1]
            if dec_base in AUTH_DECORATORS:
                auth_req = True

            if ".route(" in dec_str:
                m = re.search(r'\.route\s*\(\s*["\']([^"\']+)["\']', dec_str)
                methods_m = re.search(r'methods\s*=\s*\[([^\]]+)\]', dec_str)
                if m:
                    route_path = m.group(1)
                    methods = (
                        [x.strip().strip("\"'") for x in methods_m.group(1).split(",")]
                        if methods_m else ["GET"]
                    )
                    before = dec_str.split(".route(")[0]
                    bp_var = before.split(".")[-1]
                    if bp_var not in bp_vars:
                        bp_var = list(bp_vars.keys())[0]
                    route_info = (bp_var, route_path, methods)

        if route_info:
            bp_var, route_path, methods = route_info
            ep = {
                "function": node.name,
                "line": node.lineno,
                "methods": methods,
                "route": route_path,
                "auth_required": auth_req,
            }
            target = bp_vars.get(bp_var) or list(bp_vars.values())[0]
            target["endpoints"].append(ep)

    return bp_vars


def _parse_flask_file(path: Path, root: Path) -> dict | None:
    """
    Devuelve {var_name: {name, prefix, file, endpoints[]}} o None.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if "Blueprint" not in source and ".route" not in source:
        return None

    rel = str(path.relative_to(root))
    bp_vars: dict[str, dict] = {}

    for m in RE_BLUEPRINT.finditer(source):
        var_name, bp_name, prefix = m.group(1), m.group(2), m.group(3) or ""
        bp_vars[var_name] = {
            "name": bp_name,
            "prefix": prefix,
            "file": rel,
            "endpoints": [],
        }

    if not bp_vars and ".route" in source:
        bp_vars["app"] = {
            "name": Path(rel).stem,
            "prefix": "",
            "file": rel,
            "endpoints": [],
        }

    if not bp_vars:
        return None

    return _extract_routes_ast(source, bp_vars)


# ─── run() ────────────────────────────────────────────────────────────────────

def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera DOMAIN_INDEX_api.json. Escribe en .claude/maps/. Devuelve el dict."""
    from analyzers.core import git_cochange, resolve_dependencies

    cochange = git_cochange(root)
    prod_files = [f for f in files if f.role not in ("test", "migration")]
    dep_graph = resolve_dependencies(prod_files)
    dep_forward = dep_graph.get("forward", {})

    candidates: list[dict] = []
    seen_paths: set[str] = set()

    # ── 1. Archivos con rutas (seeds) ─────────────────────────────────────────
    for fi in files:
        if fi.language != "python":
            continue
        bp_data = _parse_flask_file(root / fi.rel_path, root)
        if not bp_data:
            continue

        # Acumular contratos de todas las blueprints de este archivo
        file_contracts: list[str] = []
        for bp_info in bp_data.values():
            for ep in bp_info["endpoints"]:
                methods = ep.get("methods", ["GET"])
                route = ep.get("route", "")
                prefix = bp_info.get("prefix", "")
                full = (prefix.rstrip("/") + "/" + route.lstrip("/")).rstrip("/") or route
                for method in methods:
                    file_contracts.append(f"{method} {full}")

        if not file_contracts:
            continue

        has_auth = any(ep.get("auth_required") for bp in bp_data.values() for ep in bp["endpoints"])
        signals = ["has_route_decorators"]
        if has_auth:
            signals.append("has_auth_decorator")
        has_webhook = any(
            "webhook" in ep.get("route", "").lower() or "callback" in ep.get("route", "").lower()
            for bp in bp_data.values()
            for ep in bp["endpoints"]
        )
        if has_webhook:
            signals.append("has_webhook_route")

        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            contracts=file_contracts,
            open_priority="seed",
            confidence_signals=signals,
        ))
        seen_paths.add(fi.rel_path)

    # ── 2. Schema / validator files (review) ──────────────────────────────────
    for fi in files:
        if fi.rel_path in seen_paths or fi.language != "python":
            continue
        parts = Path(fi.rel_path).parts
        in_schema_dir = any(p in SCHEMA_DIRS for p in parts[:-1])
        if not in_schema_dir:
            continue
        try:
            src = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not RE_SCHEMA_FILE.search(src):
            continue
        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            open_priority="review",
            confidence_signals=["is_schema_file"],
        ))
        seen_paths.add(fi.rel_path)

    # ── 3. Middleware / auth files (review) ───────────────────────────────────
    for fi in files:
        if fi.rel_path in seen_paths:
            continue
        if fi.role == "middleware" or any(
            kw in fi.rel_path.lower()
            for kw in ("auth", "middleware", "decorator", "guard")
        ):
            candidates.append(build_candidate(
                fi, files, cochange, dep_forward,
                open_priority="review",
                confidence_signals=["is_middleware"],
            ))
            seen_paths.add(fi.rel_path)

    return write_domain_index(root, "api", candidates)


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera DOMAIN_INDEX_api.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd(),
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("DOMAIN_INDEX_api.json generado.")

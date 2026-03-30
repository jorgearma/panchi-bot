#!/usr/bin/env python3
"""
analyzers/contract.py — Genera CONTRACT_MAP.json.

Captura los contratos públicos del sistema: lo que no se puede romper sin
coordinar con otros equipos, clientes o sistemas externos.

Estructura del output:
  endpoints[]     — rutas HTTP públicas con owner, símbolos y tests
  payload_schemas[] — clases de schema/validación referenciadas por endpoints
  events[]        — eventos publicados/consumidos (detección básica)
  env_vars[]      — variables de entorno requeridas con su archivo fuente
  legacy_contracts[] — contratos marcados explícitamente en código
"""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path
import json

from analyzers.core import FileInfo, detect_stack, find_test_file, walk_repo

# ─── Patrones compartidos con api.py ─────────────────────────────────────────

RE_BLUEPRINT = re.compile(
    r'(\w+)\s*=\s*Blueprint\s*\(\s*["\']([^"\']+)["\']'
    r'(?:.*?url_prefix\s*=\s*["\']([^"\']+)["\'])?',
    re.DOTALL,
)
RE_ROUTE = re.compile(
    r'@(\w+)\.route\s*\(\s*["\']([^"\']+)["\'](?:[^)]*methods\s*=\s*\[([^\]]+)\])?[^)]*\)'
)
RE_METHODS = re.compile(r'["\'](\w+)["\']')

RE_ENV_VAR = re.compile(
    r'(?:os\.environ\.get|os\.environ|os\.getenv)\s*[\[\(]\s*["\']'
    r'([A-Z][A-Z0-9_]+(?:_KEY|_SECRET|_TOKEN|_URL|_SID|_API|_PASSWORD|_PASS|_AUTH)["\'])',
)

# Marcadores de contrato legacy en comentarios/docstrings
RE_LEGACY = re.compile(r'#\s*(?:CONTRACT|LEGACY|DEPRECATED)[:\s]+(.*)', re.IGNORECASE)

SCHEMA_DIRS = frozenset({"schemas", "serializers", "validators"})

AUTH_DECORATORS = frozenset({
    "login_required", "jwt_required", "token_required",
    "require_auth", "permission_required", "auth_required",
})


# ─── Extracción de endpoints ──────────────────────────────────────────────────

def _extract_endpoints(files: list[FileInfo], root: Path) -> list[dict]:
    """
    Extrae todos los endpoints HTTP del proyecto.
    Cada endpoint: method, full_path, owner, breaking_if_changed
    """
    # 1. Obtener prefijos de blueprints desde archivos de registro
    bp_prefixes: dict[str, str] = {}  # bp_name → url_prefix
    for fi in files:
        if fi.language != "python":
            continue
        try:
            src = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in RE_BLUEPRINT.finditer(src):
            bp_name = m.group(2)
            prefix = m.group(3) or ""
            if bp_name not in bp_prefixes:
                bp_prefixes[bp_name] = prefix

    endpoints: list[dict] = []

    for fi in files:
        if fi.language != "python":
            continue
        try:
            source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if "Blueprint" not in source and ".route" not in source:
            continue

        # Detectar blueprints en este archivo
        file_bps: dict[str, dict] = {}
        for m in RE_BLUEPRINT.finditer(source):
            var_name, bp_name, prefix = m.group(1), m.group(2), m.group(3) or ""
            file_bps[var_name] = {"name": bp_name, "prefix": prefix}

        if not file_bps and ".route" in source:
            file_bps["app"] = {"name": Path(fi.rel_path).stem, "prefix": ""}

        if not file_bps:
            continue

        # Parsear rutas
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Regex fallback
            for m in RE_ROUTE.finditer(source):
                bp_var = m.group(1)
                route_path = m.group(2)
                methods_raw = m.group(3) or '"GET"'
                methods = RE_METHODS.findall(methods_raw)
                fn_match = re.search(r'def\s+(\w+)\s*\(', source[m.end():m.end() + 200])
                if not fn_match:
                    continue
                func = fn_match.group(1)
                bp_info = file_bps.get(bp_var) or list(file_bps.values())[0]
                prefix = bp_info["prefix"]
                full = (prefix.rstrip("/") + "/" + route_path.lstrip("/")).rstrip("/") or route_path
                test = find_test_file(fi.rel_path, files)
                for method in (methods or ["GET"]):
                    endpoints.append({
                        "method": method,
                        "full_path": full,
                        "owner": fi.rel_path,
                        "breaking_if_changed": True,
                    })
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            route_info = None
            auth_req = False

            for dec in node.decorator_list:
                try:
                    ds = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                except Exception:
                    ds = ""
                dec_base = ds.split("(")[0].split(".")[-1]
                if dec_base in AUTH_DECORATORS:
                    auth_req = True
                if ".route(" in ds:
                    rm = re.search(r'\.route\s*\(\s*["\']([^"\']+)["\']', ds)
                    mm = re.search(r'methods\s*=\s*\[([^\]]+)\]', ds)
                    if rm:
                        rp = rm.group(1)
                        methods = (
                            [x.strip().strip("\"'") for x in mm.group(1).split(",")]
                            if mm else ["GET"]
                        )
                        bp_var = ds.split(".route(")[0].split(".")[-1]
                        if bp_var not in file_bps:
                            bp_var = list(file_bps.keys())[0]
                        route_info = (bp_var, rp, methods)

            if not route_info:
                continue

            bp_var, route_path, methods = route_info
            bp_info = file_bps.get(bp_var) or list(file_bps.values())[0]
            prefix = bp_info.get("prefix") or bp_prefixes.get(bp_info.get("name", ""), "")
            full = (prefix.rstrip("/") + "/" + route_path.lstrip("/")).rstrip("/") or route_path

            for method in methods:
                endpoints.append({
                    "method": method,
                    "full_path": full,
                    "owner": fi.rel_path,
                    "breaking_if_changed": True,
                })

    # Deduplicar por (method, full_path)
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for ep in endpoints:
        key = (ep["method"], ep["full_path"])
        if key not in seen:
            seen.add(key)
            unique.append(ep)

    return unique


# ─── Extracción de schemas ────────────────────────────────────────────────────

def _extract_payload_schemas(files: list[FileInfo], root: Path) -> list[dict]:
    """Detecta clases de schema/validación en carpetas de schemas."""
    schemas: list[dict] = []
    RE_SCHEMA_CLASS = re.compile(r"class\s+(\w+)(?:Schema|Validator|Request|Response)?\s*[\(:]")

    for fi in files:
        if fi.language != "python":
            continue
        parts = Path(fi.rel_path).parts
        if not any(p in SCHEMA_DIRS for p in parts[:-1]):
            continue
        try:
            src = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        class_names = RE_SCHEMA_CLASS.findall(src)
        if not class_names:
            continue

        # Archivos que usan este schema (importan el archivo)
        used_by = [
            f.rel_path for f in files
            if fi.rel_path in (f.imports_internal or [])
            or Path(fi.rel_path).stem in " ".join(f.imports_internal or [])
        ]

        schemas.append({
            "file": fi.rel_path,
            "classes": class_names[:8],
            "used_by": used_by[:6],
            "breaking_if_changed": True,
        })

    return schemas


# ─── Extracción de env_vars ───────────────────────────────────────────────────

def _extract_env_vars(files: list[FileInfo], root: Path) -> list[dict]:
    """Recopila env vars de credenciales de todos los archivos fuente."""
    var_to_files: dict[str, list[str]] = {}

    for fi in files:
        if fi.role in ("test", "migration"):
            continue
        try:
            src = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in RE_ENV_VAR.finditer(src):
            var = m.group(1).strip("\"'")
            var_to_files.setdefault(var, [])
            if fi.rel_path not in var_to_files[var]:
                var_to_files[var].append(fi.rel_path)

    return [
        {
            "name": var,
            "owner": flist[0] if flist else None,
        }
        for var, flist in sorted(var_to_files.items())
    ]


# ─── Extracción de contratos legacy ──────────────────────────────────────────

def _extract_legacy_contracts(files: list[FileInfo], root: Path) -> list[dict]:
    """Detecta contratos marcados con # CONTRACT: o # LEGACY: en el código."""
    legacy: list[dict] = []
    for fi in files:
        try:
            src = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in RE_LEGACY.finditer(src):
            line_no = src[: m.start()].count("\n") + 1
            legacy.append({
                "description": m.group(1).strip(),
                "file": fi.rel_path,
                "line": line_no,
            })
    return legacy


# ─── run() ────────────────────────────────────────────────────────────────────

def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera CONTRACT_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    result = {
        "endpoints": _extract_endpoints(files, root),
        "payload_schemas": _extract_payload_schemas(files, root),
        "events": [],          # detección futura (Celery signals, event bus)
        "env_vars": _extract_env_vars(files, root),
        "legacy_contracts": _extract_legacy_contracts(files, root),
    }

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "CONTRACT_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera CONTRACT_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd(),
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("CONTRACT_MAP.json generado.")

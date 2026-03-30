"""
analyzers/core.py — Infraestructura compartida para todos los analyzers.

Extraído de analyze-repo.py. Contiene:
  - Constantes de clasificación (IGNORE_DIRS, SOURCE_EXTS, ROLE_PATTERNS, …)
  - Dataclasses (FileInfo, FunctionInfo, ModelInfo, ProjectSummary)
  - Funciones de detección de stack, escaneo, AST, Git y enriquecimiento semántico
  - API pública: walk_repo(), git_hotspots(), git_cochange()
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import pathspec as _pathspec
    _PATHSPEC_AVAILABLE = True
except ImportError:
    _PATHSPEC_AVAILABLE = False

# ─── Rutas del plugin ────────────────────────────────────────────────────────
# Usadas por los analyzers para saber dónde escribir los MAPs.
PLUGIN_DIR = Path(__file__).resolve().parents[2]  # .claude/
MAPS_DIR   = PLUGIN_DIR / "maps"

# ─── Constantes de clasificación ──────────────────────────────────────────────

IGNORE_DIRS: set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "htmlcov", ".tox", ".eggs",
    "site-packages", ".idea", ".vscode",
}

IGNORE_EXTS: set[str] = {
    ".pyc", ".pyo", ".lock", ".sum", ".map",
    ".min.js", ".min.css", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".pdf",
}

SOURCE_EXTS: dict[str, str] = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".rb": "ruby", ".go": "go", ".java": "java", ".php": "php",
    ".rs": "rust", ".cs": "csharp",
    ".html": "html", ".jinja2": "jinja2", ".jinja": "jinja2",
    ".hbs": "handlebars", ".ejs": "ejs", ".njk": "nunjucks",
    ".vue": "vue", ".svelte": "svelte", ".sql": "sql",
}

# Patrones de rol por nombre de archivo (orden importa: primero más específico)
ROLE_PATTERNS: list[tuple[str, str]] = [
    (r"(main|app|server|index|wsgi|asgi)\.(py|ts|js|mjs)$",   "entry_point"),
    (r"state[s]?\.(py|ts|js)$",                               "state_machine"),
    (r"(blueprint|router|route)\w*\.(py|ts|js)$",             "controller"),
    (r"\w*(blueprint|router|route)\w*\.(py|ts|js)$",          "controller"),
    (r"(controller|view|handler)\w*\.(py|ts|js)$",            "controller"),
    (r"\w*(controller|handler)\w*\.(py|ts|js)$",              "controller"),
    (r"(service|adapter|client|provider)\w*\.(py|ts|js)$",    "service"),
    (r"\w*(service|adapter|client|provider)\w*\.(py|ts|js)$", "service"),
    (r"(manager|gestor|repository|repo|dao|store)\w*\.(py|ts|js)$", "data_access"),
    (r"\w*(manager|gestor|repository|repo|dao)\w*\.(py|ts|js)$",    "data_access"),
    (r"models?\.(py|ts|js)$",                                 "model"),
    (r"(entity|entities|domain)\w*\.(py|ts|js)$",             "model"),
    (r"\w*\.(entity|model)\.(py|ts|js)$",                     "model"),
    (r"(schema|schemas)\.(py|ts|js)$",                        "schema"),
    (r"(config|settings|configuration)\w*\.(py|ts|js)$",      "config"),
    (r"database?\.(py|ts|js)$",                               "db_connection"),
    (r"(middleware|guard|interceptor)\w*\.(py|ts|js)$",       "middleware"),
    (r"(util|helper|tool|lib|common)\w*\.(py|ts|js)$",        "utility"),
    (r"\w*(util|helper|lib)\w*\.(py|ts|js)$",                 "utility"),
    (r"(test|spec)\w*\.(py|ts|js)$",                          "test"),
    (r"\w*(test|spec)\w*\.(py|ts|js)$",                       "test"),
    (r"(migration|migrate|seed)\w*\.(py|ts|js|sql)$",         "migration"),
    (r"\w*\.(html|jinja2|jinja|hbs|ejs|njk|pug)$",            "template"),
    (r"\w*\.(vue|svelte)$",                                    "component"),
    (r"\w*\.(jsx|tsx)$",                                       "component"),
    (r"\w*\.component\.(ts|js)$",                             "component"),
]

FOLDER_ROLES: dict[str, str] = {
    "blueprints": "routing HTTP",
    "routes": "routing HTTP",
    "routers": "routing HTTP",
    "api": "API endpoints",
    "endpoints": "API endpoints",
    "controllers": "lógica de negocio",
    "handlers": "lógica de negocio",
    "managers": "acceso a datos (DB + caché)",
    "repositories": "acceso a datos",
    "services": "adaptadores externos / lógica de servicio",
    "adapters": "adaptadores externos",
    "providers": "proveedores de servicio",
    "models": "modelos ORM / entidades",
    "entities": "modelos ORM / entidades",
    "domain": "dominio del negocio",
    "schemas": "validación de entrada",
    "middlewares": "middlewares",
    "middleware": "middlewares",
    "utils": "helpers sin estado",
    "helpers": "helpers sin estado",
    "lib": "utilidades compartidas",
    "common": "código compartido",
    "shared": "código compartido",
    "templates": "plantillas HTML",
    "views": "vistas / plantillas",
    "components": "componentes UI",
    "pages": "páginas / rutas UI",
    "layouts": "layouts UI",
    "static": "assets estáticos",
    "public": "assets públicos",
    "assets": "assets",
    "tests": "tests", "test": "tests", "__tests__": "tests", "spec": "tests",
    "migrations": "migraciones DB",
    "seeds": "datos iniciales DB",
    "config": "configuración",
    "docs": "documentación",
    "scripts": "scripts de utilidad",
    "hooks": "hooks del sistema",
    "types": "definiciones de tipos",
    "interfaces": "interfaces TS",
    "dto": "Data Transfer Objects",
    "dtos": "Data Transfer Objects",
    "decorators": "decoradores",
    "guards": "guards de autenticación",
    "pipes": "pipes de transformación",
    "filters": "filtros de excepciones",
    "interceptors": "interceptores",
    "jobs": "tareas programadas",
    "tasks": "tareas",
    "queues": "colas de trabajo",
    "events": "eventos / pub-sub",
    "commands": "comandos CQRS",
    "queries": "queries CQRS",
}

# Mapeo de carpeta → rol (fallback cuando el nombre de archivo no da pistas)
FOLDER_TO_ROLE: dict[str, str] = {
    "controllers": "controller",
    "handlers":    "controller",
    "blueprints":  "controller",
    "routes":      "controller",
    "routers":     "controller",
    "schemas":     "schema",
    "serializers": "schema",
    "validators":  "schema",
    "services":    "service",
    "adapters":    "service",
    "providers":   "service",
    "clients":     "service",
    "integrations":"service",
    "repositories":"data_access",
    "repos":       "data_access",
    "managers":    "data_access",
    "dao":         "data_access",
    "models":      "model",
    "entities":    "model",
    "domain":      "model",
    "middleware":  "middleware",
    "middlewares": "middleware",
    "guards":      "middleware",
    "utils":       "utility",
    "helpers":     "utility",
    "lib":         "utility",
    "common":      "utility",
    "shared":      "utility",
    "config":      "config",
    "tests":       "test",
    "test":        "test",
    "__tests__":   "test",
    "spec":        "test",
    "migrations":  "migration",
    "seeds":       "migration",
}

# Indicadores de framework (clave lowercase del paquete → nombre legible)
FRAMEWORK_MAP: dict[str, str] = {
    "flask": "Flask", "django": "Django", "fastapi": "FastAPI",
    "aiohttp": "aiohttp", "tornado": "Tornado", "starlette": "Starlette",
    "sanic": "Sanic", "bottle": "Bottle", "falcon": "Falcon",
    "sqlalchemy": "SQLAlchemy", "peewee": "Peewee", "tortoise-orm": "Tortoise ORM",
    "mongoengine": "MongoEngine", "pymongo": "PyMongo",
    "alembic": "Alembic", "aerich": "Aerich",
    "celery": "Celery", "rq": "RQ", "dramatiq": "Dramatiq",
    "pydantic": "Pydantic", "marshmallow": "Marshmallow",
    "redis": "Redis", "aioredis": "aioredis",
    "tenacity": "Tenacity", "httpx": "httpx", "requests": "requests",
    "twilio": "Twilio", "boto3": "AWS SDK", "stripe": "Stripe",
    "pytest": "pytest", "unittest": "unittest",
    "sentry-sdk": "Sentry", "loguru": "loguru",
    "express": "Express", "fastify": "Fastify", "koa": "Koa",
    "@nestjs/core": "NestJS", "nestjs": "NestJS",
    "next": "Next.js", "nuxt": "Nuxt.js", "gatsby": "Gatsby",
    "typeorm": "TypeORM", "sequelize": "Sequelize",
    "mongoose": "Mongoose", "@prisma/client": "Prisma", "prisma": "Prisma",
    "knex": "Knex", "drizzle-orm": "Drizzle",
    "react": "React", "vue": "Vue", "@angular/core": "Angular",
    "svelte": "Svelte", "solid-js": "Solid",
    "vite": "Vite", "webpack": "Webpack",
    "jest": "Jest", "vitest": "Vitest", "mocha": "Mocha",
}

# Patrones de acceso a DB para query detection
RE_DB_PY = re.compile(
    r'\b(session\.(query|execute|add|commit|delete|merge|flush|scalar)|'
    r'db\.(session|engine)|'
    r'\.filter\(|\.filter_by\(|\.first\(\)|\.all\(\)|\.one\(\)|\.count\(\)|'
    r'cursor\.execute\(|connection\.execute\(|engine\.execute\(|'
    r'text\(|select\(|insert\(|update\(|delete\()\b'
)

RE_DB_JS = re.compile(
    r'\b(repository\.(find|save|update|delete|create|query|upsert)|'
    r'prisma\.\w+\.(find|create|update|delete|upsert|aggregate)|'
    r'Model\.(find|create|update|aggregate|deleteOne)|'
    r'sequelize\.query\(|knex\(|\.where\(|\.select\(|\.from\()\b'
)

# ─── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class FileInfo:
    rel_path: str
    language: str
    role: str
    size: int
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    imports_internal: list[str] = field(default_factory=list)
    imports_external: list[str] = field(default_factory=list)
    jsdoc: dict[str, str] = field(default_factory=dict)
    has_db_access: bool = False
    docstring: str = ""          # module-level docstring o JSDoc @description
    query_examples: list[str] = field(default_factory=list)  # patrones ORM/SQL reales
    symbols_with_lines: dict[str, int] = field(default_factory=dict)  # nombre → línea
    function_infos: list = field(default_factory=list)                 # list[FunctionInfo]

@dataclass
class ModelField:
    name: str
    col_type: str = ""

@dataclass
class FunctionInfo:
    name: str
    start_line: int
    end_line: int
    params: list[str] = field(default_factory=list)
    return_type: str = ""
    decorators: list[str] = field(default_factory=list)
    complexity: int = 0   # lines of code (end_line - start_line + 1)
    is_async: bool = False


@dataclass
class ModelInfo:
    name: str
    file: str
    table: str
    fields: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)

@dataclass
class ProjectSummary:
    name: str
    root: Path
    description: str
    stack: dict[str, str]         # display_name → version
    languages: list[str]
    entry_points: list[str]
    folder_structure: dict[str, str]  # rel_folder → role
    files: list[FileInfo] = field(default_factory=list)
    models: list[ModelInfo] = field(default_factory=list)
    git_hotspots: list[tuple[str, int]] = field(default_factory=list)
    git_cochange: dict[str, list[str]] = field(default_factory=dict)
    git_recent_changes: dict[str, int] = field(default_factory=dict)   # file → commits last 30d
    git_ownership: dict[str, str] = field(default_factory=dict)        # file → primary author email
    git_pending: list[str] = field(default_factory=list)               # uncommitted files
    readme_summary: str = ""

# ─── Detección de stack ───────────────────────────────────────────────────────

def detect_stack(root: Path) -> dict[str, str]:
    """
    Extrae paquetes y versiones de manifests.
    Solo incluye paquetes presentes en FRAMEWORK_MAP (frameworks y libs relevantes).
    Retorna {nombre_display: version}.
    """
    stack: dict[str, str] = {}

    # requirements.txt
    req = root / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_\-\.]+)([><=!~^]+(.*))?", line)
            if m:
                pkg = m.group(1).lower().replace("_", "-")
                ver = (m.group(3) or "").strip()
                if pkg in FRAMEWORK_MAP:
                    stack[FRAMEWORK_MAP[pkg]] = ver

    # pyproject.toml / Pipfile (solo regex, sin dependencia toml)
    for toml_path in [root / "pyproject.toml", root / "Pipfile"]:
        if toml_path.exists():
            content = toml_path.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'"([A-Za-z0-9_\-\.]+)"\s*=\s*"([^"]*)"', content):
                pkg = m.group(1).lower().replace("_", "-")
                if pkg in FRAMEWORK_MAP:
                    stack[FRAMEWORK_MAP[pkg]] = m.group(2)

    # package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for pkg, ver in all_deps.items():
                display = FRAMEWORK_MAP.get(pkg.lower(), None)
                if display:
                    stack[display] = ver.lstrip("^~>=")
        except json.JSONDecodeError:
            pass

    return stack

def detect_project_name(root: Path) -> tuple[str, str]:
    """Retorna (nombre, descripcion_breve)."""
    # package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            return data.get("name", root.name), data.get("description", "")
        except json.JSONDecodeError:
            pass

    # pyproject.toml
    toml = root / "pyproject.toml"
    if toml.exists():
        content = toml.read_text(encoding="utf-8", errors="replace")
        m_name = re.search(r'name\s*=\s*"([^"]+)"', content)
        m_desc = re.search(r'description\s*=\s*"([^"]+)"', content)
        if m_name:
            return m_name.group(1), (m_desc.group(1) if m_desc else "")

    # setup.py
    setup = root / "setup.py"
    if setup.exists():
        content = setup.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", content)
        if m:
            return m.group(1), ""

    return root.name, ""

def detect_readme_summary(root: Path) -> str:
    """Extrae la primera línea de contenido real del README."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        readme = root / name
        if readme.exists():
            lines = readme.read_text(encoding="utf-8", errors="replace").splitlines()
            # Busca primera línea no vacía que no sea un encabezado de título
            meaningful = [
                l.strip() for l in lines
                if l.strip() and not l.startswith("#") and not l.startswith("=")
            ]
            return meaningful[0] if meaningful else ""
    return ""

# ─── Scanner de archivos ──────────────────────────────────────────────────────

def classify_role(rel_path: str) -> str:
    filename = Path(rel_path).name.lower()
    for pattern, role in ROLE_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            return role
    # Fallback: deduce rol por la carpeta padre más cercana
    parts = Path(rel_path).parts
    for part in reversed(parts[:-1]):
        folder_role = FOLDER_TO_ROLE.get(part.lower())
        if folder_role:
            return folder_role
    return "other"

def should_ignore(path: Path) -> bool:
    for part in path.parts:
        if part in IGNORE_DIRS or part.endswith(".egg-info"):
            return True
    return path.suffix in IGNORE_EXTS

def load_gitignore_spec(root: Path):
    """Carga .gitignore del root y retorna pathspec.PathSpec, o None si no disponible."""
    if not _PATHSPEC_AVAILABLE:
        return None
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return None
    lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    return _pathspec.PathSpec.from_lines("gitwildmatch", lines)

def scan_structure(root: Path) -> dict[str, str]:
    """Retorna {carpeta_relativa: rol} para carpetas de primer y segundo nivel."""
    result: dict[str, str] = {}
    try:
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name in IGNORE_DIRS or entry.name.startswith("."):
                continue
            role = FOLDER_ROLES.get(entry.name.lower(), "")
            result[entry.name] = role
            # Segundo nivel si la carpeta no tiene rol conocido
            if not role:
                for sub in sorted(entry.iterdir()):
                    if sub.is_dir() and sub.name not in IGNORE_DIRS and not sub.name.startswith("."):
                        sub_role = FOLDER_ROLES.get(sub.name.lower(), "")
                        if sub_role:
                            result[f"{entry.name}/{sub.name}"] = sub_role
    except PermissionError:
        pass
    return result

def walk_source_files(root: Path, gitignore_spec=None) -> list[Path]:
    """Devuelve todos los archivos de código fuente, respetando IGNORE_DIRS y .gitignore."""
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in IGNORE_DIRS and not d.startswith(".")
            and not d.endswith(".egg-info")
        )
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix not in SOURCE_EXTS or should_ignore(fpath):
                continue
            rel = str(fpath.relative_to(root))
            if gitignore_spec and gitignore_spec.match_file(rel):
                continue
            result.append(fpath)
    return result

# ─── Extracción de query examples ────────────────────────────────────────────

RE_QUERY_EXAMPLES = re.compile(
    r'session\.(?:query|execute)\s*\([^)\n]{8,100}\)'
    r'|\.filter(?:_by)?\s*\([^)\n]{5,80}\)'
    r'|\.order_by\s*\([^)\n]{5,60}\)'
    r'|repository\.\w+\s*\([^)\n]{5,80}\)'
    r'|prisma\.\w+\.(?:find\w*|create|update|delete)\s*\([^)\n]{5,80}\)',
    re.MULTILINE,
)

def extract_query_examples(source: str) -> list[str]:
    seen: set[str] = set()
    examples: list[str] = []
    for m in RE_QUERY_EXAMPLES.finditer(source):
        ex = re.sub(r'\s+', ' ', m.group(0).strip())
        if ex not in seen:
            seen.add(ex)
            examples.append(ex)
        if len(examples) >= 4:
            break
    return examples

# ─── Extracción Python (AST) ──────────────────────────────────────────────────

def _ast_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_ast_name(node.value)}.{node.attr}"
    return ""

def _ast_call_name(node: ast.Call) -> str:
    return _ast_name(node.func)

def extract_python(path: Path, project_root: Path) -> FileInfo:
    rel = str(path.relative_to(project_root))
    size = path.stat().st_size
    lang = "python"
    role = classify_role(rel)

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return FileInfo(rel, lang, role, size)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return FileInfo(rel, lang, role, size)

    classes: list[str] = []
    functions: list[str] = []
    imports_int: list[str] = []
    imports_ext: list[str] = []
    models: list[ModelInfo] = []
    symbols_with_lines: dict[str, int] = {}
    has_db = bool(RE_DB_PY.search(source))

    # Docstring de módulo (primer statement si es una cadena literal)
    module_docstring = ""
    if tree.body and isinstance(tree.body[0], ast.Expr):
        val = tree.body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            raw = val.value.strip()
            # Primera línea no vacía, máx 150 chars
            first = next((l.strip() for l in raw.splitlines() if l.strip()), raw)
            module_docstring = first[:150]

    # Tops internos válidos: nombre del paquete + cualquier archivo/carpeta Python en la raíz.
    # Cubre proyectos Flask planos y namespace packages (sin __init__.py, Python 3.3+).
    project_pkg = project_root.name
    _internal_tops: set[str] = {project_pkg}
    try:
        root_entries = list(project_root.iterdir())
    except (PermissionError, OSError):
        root_entries = []
    for _entry in root_entries:
        if _entry.suffix == ".py":
            _internal_tops.add(_entry.stem)
        elif (
            _entry.is_dir()
            and _entry.name not in IGNORE_DIRS
            and not _entry.name.startswith(".")
        ):
            # Paquete tradicional (__init__.py) o namespace package (solo archivos .py)
            try:
                is_pkg = (_entry / "__init__.py").exists() or (
                    next(_entry.glob("*.py"), None) is not None
                )
            except (PermissionError, OSError):
                is_pkg = False
            if is_pkg:
                _internal_tops.add(_entry.name)

    fn_infos: list[FunctionInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if node.name not in symbols_with_lines:
                symbols_with_lines[node.name] = node.lineno
            # Params
            params = [a.arg for a in node.args.args if a.arg != "self"]
            # Return type
            ret = ""
            if node.returns:
                try:
                    ret = ast.unparse(node.returns) if hasattr(ast, "unparse") else ""
                except Exception:
                    ret = ""
            # Decorators
            decs = []
            for d in node.decorator_list:
                try:
                    decs.append(ast.unparse(d) if hasattr(ast, "unparse") else "")
                except Exception:
                    pass
            end_ln = getattr(node, "end_lineno", node.lineno)
            fn_infos.append(FunctionInfo(
                name=node.name,
                start_line=node.lineno,
                end_line=end_ln,
                params=params[:8],
                return_type=ret[:60],
                decorators=[d for d in decs if d][:4],
                complexity=max(1, end_ln - node.lineno + 1),
                is_async=isinstance(node, ast.AsyncFunctionDef),
            ))

        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
            if node.name not in symbols_with_lines:
                symbols_with_lines[node.name] = node.lineno
            bases = [_ast_name(b) for b in node.bases]

            # Detectar modelos SQLAlchemy / Django ORM
            is_sqla = any(
                b in ("Base", "db.Model", "Model") or b.endswith("Base") or "Model" in b
                for b in bases
            )
            if is_sqla:
                fields: list[str] = []
                rels: list[str] = []
                table_name = node.name.lower()

                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if not isinstance(target, ast.Name):
                                continue
                            if target.id == "__tablename__" and isinstance(item.value, ast.Constant):
                                table_name = str(item.value.value)
                            elif isinstance(item.value, ast.Call):
                                fn = _ast_call_name(item.value)
                                if "Column" in fn or "mapped_column" in fn:
                                    # Intenta extraer el tipo del primer arg
                                    col_type = ""
                                    if item.value.args:
                                        col_type = _ast_name(item.value.args[0])
                                    fields.append(f"{target.id}:{col_type}" if col_type else target.id)
                                elif "relationship" in fn or "Relationship" in fn:
                                    rels.append(target.id)
                            elif isinstance(item.value, ast.Attribute):
                                # mapped_column via annotation
                                pass
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        # SQLAlchemy 2.0 Mapped[X] style
                        ann = ast.unparse(item.annotation) if hasattr(ast, "unparse") else ""
                        if "Mapped" in ann or "mapped_column" in ann:
                            fields.append(item.target.id)
                        elif "relationship" in ann.lower():
                            rels.append(item.target.id)

                models.append(ModelInfo(node.name, rel, table_name, fields, rels))

        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _internal_tops:
                    imports_int.append(alias.name)
                else:
                    imports_ext.append(top)

        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                imports_int.append(f".{node.module or ''}")
            elif node.module:
                top = node.module.split(".")[0]
                if top in _internal_tops:
                    imports_int.append(node.module)
                else:
                    imports_ext.append(top)

    # Solo top-level functions (no métodos): reparse
    top_functions = [
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    # Aproximación: las funciones de ast.walk incluyen métodos; filtramos startswith("_") menores
    top_functions = [f for f in top_functions if not f.startswith("_")][:20]

    fi = FileInfo(
        rel_path=rel, language=lang, role=role, size=size,
        classes=classes, functions=top_functions,
        imports_internal=list(set(imports_int)),
        imports_external=list(set(imports_ext)),
        has_db_access=has_db,
        docstring=module_docstring,
        query_examples=extract_query_examples(source) if has_db else [],
        symbols_with_lines=symbols_with_lines,
        function_infos=fn_infos,
    )
    fi.__dict__["_models"] = models  # transporte temporal
    return fi

# ─── Extracción JS/TS (Regex) ─────────────────────────────────────────────────

RE_EXPORT     = re.compile(r'export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|type|interface|enum|abstract\s+class)\s+(\w+)')
RE_EXPORT_OBJ = re.compile(r'export\s*\{([^}]+)\}')
RE_IMPORT     = re.compile(r"import\s+(?:type\s+)?(?:\{[^}]*\}|\w+|\*\s+as\s+\w+)\s+from\s+['\"]([^'\"]+)['\"]")
RE_CLASS      = re.compile(r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)')
RE_FUNCTION   = re.compile(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)')
RE_JSDOC      = re.compile(r'/\*\*([\s\S]*?)\*/')
RE_JSDOC_TAG  = re.compile(r'@(\w+)\s+(.*)')
RE_ENTITY_TS  = re.compile(r'@Entity\(')
RE_SCHEMA_MG  = re.compile(r'new\s+Schema\s*\(')
RE_PRISMA_MDL = re.compile(r'^model\s+(\w+)\s*\{', re.MULTILINE)

def _line_of(source: str, pos: int) -> int:
    """Retorna el número de línea (1-based) para una posición en el texto."""
    return source[:pos].count("\n") + 1


def extract_js_ts(path: Path, project_root: Path) -> FileInfo:
    rel = str(path.relative_to(project_root))
    size = path.stat().st_size
    lang = SOURCE_EXTS.get(path.suffix, "javascript")
    role = classify_role(rel)

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return FileInfo(rel, lang, role, size)

    # JSDoc tags + descripción del primer bloque como docstring
    jsdoc: dict[str, str] = {}
    module_docstring = ""
    first_jsdoc = RE_JSDOC.search(source)
    if first_jsdoc:
        block_text = first_jsdoc.group(1)
        # Líneas sin @ son la descripción libre del bloque
        desc_lines = [
            l.strip().lstrip("* ").strip()
            for l in block_text.splitlines()
            if l.strip() and not l.strip().lstrip("* ").startswith("@")
        ]
        if desc_lines:
            module_docstring = desc_lines[0][:150]
    for block in RE_JSDOC.finditer(source):
        for tag in RE_JSDOC_TAG.finditer(block.group(1)):
            jsdoc[tag.group(1)] = tag.group(2).strip()
    # @description o @purpose sobreescriben la descripción libre
    if jsdoc.get("description") or jsdoc.get("purpose"):
        module_docstring = (jsdoc.get("description") or jsdoc.get("purpose", ""))[:150]

    # Exports
    exports: list[str] = []
    for m in RE_EXPORT.finditer(source):
        exports.append(m.group(1))
    for m in RE_EXPORT_OBJ.finditer(source):
        for name in m.group(1).split(","):
            name = name.strip().split(" as ")[0].strip()
            if name and re.match(r'^\w+$', name):
                exports.append(name)

    # Imports
    imports_int: list[str] = []
    imports_ext: list[str] = []
    for m in RE_IMPORT.finditer(source):
        spec = m.group(1)
        if spec.startswith("."):
            imports_int.append(spec)
        else:
            top = spec.split("/")[0].lstrip("@")
            imports_ext.append(top)

    symbols_with_lines: dict[str, int] = {}
    classes = list(dict.fromkeys(m.group(1) for m in RE_CLASS.finditer(source)))
    for m in RE_CLASS.finditer(source):
        name = m.group(1)
        if name not in symbols_with_lines:
            symbols_with_lines[name] = _line_of(source, m.start())
    functions = list(dict.fromkeys(m.group(1) for m in RE_FUNCTION.finditer(source) if not m.group(1).startswith("_")))
    for m in RE_FUNCTION.finditer(source):
        name = m.group(1)
        if not name.startswith("_") and name not in symbols_with_lines:
            symbols_with_lines[name] = _line_of(source, m.start())
    for m in RE_EXPORT.finditer(source):
        name = m.group(1)
        if name not in symbols_with_lines:
            symbols_with_lines[name] = _line_of(source, m.start())

    # FunctionInfo para JS/TS (limitado: sin tipos completos vía regex)
    fn_infos_js: list[FunctionInfo] = []
    RE_FN_PARAMS = re.compile(
        r'(?:async\s+)?function\s+(\w+)\s*\(([^)]{0,200})\)'
        r'|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]{0,200})\)\s*(?::\s*\w[\w<>[\], ]*?)?\s*=>'
    )
    RE_DEC = re.compile(r'@(\w[\w.]*)\s*(?:\([^)]*\))?\s*\n\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)')
    decorators_by_name: dict[str, list[str]] = defaultdict(list)
    for m in RE_DEC.finditer(source):
        decorators_by_name[m.group(2)].append(m.group(1))

    for m in RE_FN_PARAMS.finditer(source):
        fname = m.group(1) or m.group(3)
        raw_params = m.group(2) or m.group(4) or ""
        if not fname or fname.startswith("_"):
            continue
        params = [p.strip().split(":")[0].strip() for p in raw_params.split(",") if p.strip()]
        line = _line_of(source, m.start())
        fn_infos_js.append(FunctionInfo(
            name=fname,
            start_line=line,
            end_line=line,   # end_line no fiable con regex
            params=params[:8],
            decorators=decorators_by_name.get(fname, [])[:4],
            complexity=1,
            is_async="async" in (source[max(0, m.start()-10):m.start()] + m.group(0))[:20],
        ))

    has_db = bool(RE_DB_JS.search(source))

    # Detectar modelos TypeORM / Mongoose
    models: list[ModelInfo] = []
    if RE_ENTITY_TS.search(source):
        for cls in classes:
            models.append(ModelInfo(cls, rel, cls.lower(), [], []))
    if RE_SCHEMA_MG.search(source):
        for cls in classes:
            if "schema" in cls.lower() or "model" in cls.lower():
                models.append(ModelInfo(cls, rel, cls.lower().replace("schema","").replace("model",""), [], []))

    fi = FileInfo(
        rel_path=rel, language=lang, role=role, size=size,
        classes=classes, functions=functions[:20],
        exports=exports[:20],
        imports_internal=list(set(imports_int)),
        imports_external=list(set(imports_ext)),
        jsdoc=jsdoc, has_db_access=has_db,
        docstring=module_docstring,
        query_examples=extract_query_examples(source) if has_db else [],
        symbols_with_lines=symbols_with_lines,
        function_infos=fn_infos_js,
    )
    fi.__dict__["_models"] = models
    return fi

def extract_prisma_models(root: Path) -> list[ModelInfo]:
    models: list[ModelInfo] = []
    for schema_file in root.rglob("schema.prisma"):
        if should_ignore(schema_file):
            continue
        source = schema_file.read_text(encoding="utf-8", errors="replace")
        for m in RE_PRISMA_MDL.finditer(source):
            name = m.group(1)
            # Extrae campos del bloque
            block_start = m.end()
            depth = 1
            block_end = block_start
            for i, ch in enumerate(source[block_start:], block_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        block_end = i
                        break
            block = source[block_start:block_end]
            fields = [
                line.strip().split()[0]
                for line in block.splitlines()
                if line.strip() and not line.strip().startswith("//") and not line.strip().startswith("@@")
                and len(line.strip().split()) >= 2
            ]
            rel = str(schema_file.relative_to(root))
            models.append(ModelInfo(name, rel, name.lower(), fields, []))
    return models

# ─── Análisis de Git ──────────────────────────────────────────────────────────

def analyze_git(root: Path, max_commits: int = 200) -> tuple[list[tuple[str, int]], dict[str, list[str]]]:
    """
    Retorna:
      hotspots: [(archivo, n_commits)] — archivos más modificados
      cochange: {archivo: [archivos_que_cambian_juntos]} — top 3 por archivo
    """
    try:
        result = subprocess.run(
            ["git", "log", "--name-only", f"--max-count={max_commits}", "--format="],
            cwd=root, capture_output=True, text=True, timeout=15
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [], {}

    if result.returncode != 0:
        return [], {}

    # Agrupar archivos por commit (separados por línea vacía)
    commits: list[list[str]] = []
    current: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            current.append(line)
        else:
            if current:
                commits.append(current)
                current = []
    if current:
        commits.append(current)

    # Hotspots
    freq: dict[str, int] = defaultdict(int)
    for commit in commits:
        for f in commit:
            freq[f] += 1
    hotspots = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:15]

    # Co-change
    cochange: dict[str, list[str]] = defaultdict(lambda: defaultdict(int))
    for commit in commits:
        if len(commit) < 2:
            continue
        for i, fa in enumerate(commit):
            for fb in commit[i+1:]:
                cochange[fa][fb] += 1
                cochange[fb][fa] += 1

    # Retener solo top 3 co-changes por archivo con >= 3 co-apariciones
    result_cochange: dict[str, list[str]] = {}
    for fa, partners in cochange.items():
        top = sorted(partners.items(), key=lambda x: x[1], reverse=True)
        strong = [f for f, cnt in top[:3] if cnt >= 3]
        if strong:
            result_cochange[fa] = strong

    return hotspots, result_cochange

def analyze_git_extended(root: Path) -> tuple[dict[str, int], dict[str, str], list[str]]:
    """
    Returns:
        recent_changes: {file: commits in last 30 days}
        ownership:      {file: primary author email (most commits)}
        pending:        list of files with uncommitted changes
    """
    recent_changes: dict[str, int] = defaultdict(int)
    ownership_raw: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pending: list[str] = []

    # Recent changes: last 30 days
    try:
        r = subprocess.run(
            ["git", "log", "--since=30 days ago", "--name-only", "--format=%ae"],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            current_author = ""
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line:
                    current_author = ""
                    continue
                if "@" in line or "." in line and "/" not in line:
                    current_author = line
                else:
                    recent_changes[line] += 1
                    if current_author:
                        ownership_raw[line][current_author] += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Full ownership from all history (merge with recent)
    try:
        r = subprocess.run(
            ["git", "log", "--name-only", "--format=%ae", "--max-count=500"],
            cwd=root, capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0:
            current_author = ""
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line:
                    current_author = ""
                    continue
                if "@" in line or ("." in line and "/" not in line and len(line) < 80):
                    current_author = line
                else:
                    if current_author:
                        ownership_raw[line][current_author] += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Resolve ownership: primary author per file
    ownership: dict[str, str] = {}
    for fpath, authors in ownership_raw.items():
        if authors:
            ownership[fpath] = max(authors, key=lambda a: authors[a])

    # Pending uncommitted changes
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if len(line) > 3:
                    pending.append(line[3:].strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return dict(recent_changes), ownership, pending

# ─── Inferencia de arquitectura ───────────────────────────────────────────────

def infer_architecture(proj: ProjectSummary) -> str:
    """Infiere la cadena de capas a partir de carpetas detectadas."""
    folders = {k.split("/")[0].lower() for k in proj.folder_structure}

    layers: list[str] = []
    if folders & {"blueprints", "routes", "routers", "api", "endpoints", "controllers", "handlers"}:
        sample = next(iter(folders & {"blueprints", "routes", "routers", "api", "endpoints", "controllers", "handlers"}))
        layers.append(sample.upper())
    if folders & {"controllers", "handlers"} and layers:
        if "CONTROLLERS" not in layers[0].upper() and "HANDLERS" not in layers[0].upper():
            layers.append("CONTROLLERS")
    if folders & {"services", "adapters", "providers"}:
        layers.append("SERVICES")
    if folders & {"managers", "repositories", "repos", "dao"}:
        sample = next(iter(folders & {"managers", "repositories", "repos", "dao"}))
        layers.append(sample.upper())
    if folders & {"models", "entities", "domain"}:
        layers.append("MODELS")

    if not layers:
        return "Arquitectura no inferida — revisar estructura de carpetas"

    # Externos detectados
    externals: list[str] = []
    stack_keys = set(proj.stack.keys())
    if stack_keys & {"SQLAlchemy", "Django ORM", "TypeORM", "Prisma", "Mongoose", "Sequelize", "Drizzle"}:
        externals.append("DB")
    if stack_keys & {"Redis", "aioredis"}:
        externals.append("Redis")
    if stack_keys & {"Twilio", "httpx", "requests"}:
        externals.append("APIs externas")

    chain = " → ".join(layers)
    if externals:
        chain += f" → [{' | '.join(externals)}]"
    return chain

def detect_code_smells(proj: ProjectSummary) -> list[str]:
    """Detecta god objects, archivos grandes y otros smells básicos."""
    smells: list[str] = []
    # Archivos > 50 KB en código fuente
    large = sorted(
        [f for f in proj.files if f.size > 50_000 and f.language in ("python", "typescript", "javascript")],
        key=lambda x: x.size, reverse=True
    )[:5]
    for f in large:
        kb = f.size // 1024
        smells.append(f"`{f.rel_path}` ({kb} KB) — archivo sobredimensionado, posible God Object")

    # Archivos con muchas clases
    multi_class = [f for f in proj.files if len(f.classes) > 8]
    for f in multi_class:
        if not any(f.rel_path in s for s in smells):
            smells.append(f"`{f.rel_path}` — {len(f.classes)} clases en un archivo")

    return smells

# ─── Enriquecimiento semántico ────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "py", "ts", "js", "mjs", "test", "tests", "spec", "the", "for", "is",
    "get", "set", "add", "del", "run", "use", "new", "old", "base", "init",
    "by", "to", "of", "in", "my", "do", "on", "at",
})

# Stems demasiado genéricos para aportar valor en related_to
_GENERIC_STEMS = frozenset({
    "index", "main", "app", "base", "init", "utils", "helpers", "common",
    "config", "types", "constants", "shared", "core",
})

_ROLE_VERBS: dict[str, str] = {
    "entry_point":   "Punto de entrada de la aplicación",
    "controller":    "Define rutas HTTP para",
    "service":       "Adapta el servicio externo de",
    "data_access":   "Gestiona acceso a datos de",
    "model":         "Define los modelos ORM de",
    "schema":        "Valida el esquema de entrada para",
    "utility":       "Utilidades para",
    "config":        "Configuración de",
    "state_machine": "Define la máquina de estados de",
    "db_connection": "Gestiona la conexión a la base de datos",
    "migration":     "Migración de esquema de",
    "middleware":    "Middleware para",
    "component":     "Componente UI de",
    "template":      "Plantilla HTML de",
}

def extract_keywords(fi: FileInfo) -> list[str]:
    """
    Extrae términos de búsqueda greppables para que los readers encuentren el archivo.
    Solo nombres completos — sin fragmentos de snake_case ni CamelCase splits.
    """
    seen: set[str] = set()
    result: list[str] = []

    def add(token: str) -> None:
        t = token.strip()
        if len(t) > 2 and t.lower() not in _STOP_WORDS and t not in seen:
            seen.add(t)
            result.append(t)

    # 1. Fragmentos del stem del archivo (dominio: "pedidos" de "gestor_pedidos.py")
    stem = Path(fi.rel_path).stem
    for part in re.split(r"[_\-\.]", stem):
        add(part.lower())

    # 2. Nombres completos de clases (greppables directamente)
    for cls in fi.classes[:4]:
        add(cls)

    # 3. Nombres completos de funciones públicas (greppables directamente)
    for fn in (fi.functions or fi.exports)[:6]:
        add(fn)

    # 4. Palabras clave del docstring (conceptos del dominio, máx 3)
    if fi.docstring:
        doc_words = re.findall(r"[a-zA-Z]{4,}", fi.docstring)
        count = 0
        for w in doc_words:
            if w.lower() not in _STOP_WORDS:
                add(w.lower())
                count += 1
                if count >= 3:
                    break

    return result[:8]

def infer_purpose(fi: FileInfo) -> str:
    """Infiere el propósito del módulo en este orden: docstring → JSDoc → heurística."""
    if fi.docstring:
        sentence = fi.docstring.split(".")[0].strip()
        if len(sentence) > 10:
            return sentence
    desc = fi.jsdoc.get("description") or fi.jsdoc.get("purpose")
    if desc:
        return desc.split(".")[0].strip()[:120]
    # Heurística por rol + nombre
    stem = Path(fi.rel_path).stem
    parts = [k for k in re.split(r"[_\-]", stem) if len(k) > 2]
    verb = _ROLE_VERBS.get(fi.role, "Módulo de")
    subject = " ".join(parts[1:]) if len(parts) > 1 else (parts[0] if parts else stem)
    return f"{verb} {subject}"

def find_related(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
    dep_forward: dict[str, list[str]] | None = None,
) -> list[str]:
    """Encuentra módulos relacionados: grafo de deps resuelto → co-change git → imports por stem."""
    stem = Path(fi.rel_path).stem
    related: list[str] = []
    seen: set[str] = set()

    # 1. Dependencias resueltas (más preciso: paths completos)
    if dep_forward:
        for dep_path in dep_forward.get(fi.rel_path, []):
            dep_stem = Path(dep_path).stem
            if dep_path != fi.rel_path and dep_stem not in _GENERIC_STEMS and dep_path not in seen:
                seen.add(dep_path)
                related.append(dep_path)

    # 2. Git co-change (patrones de cambio conjunto)
    for cochanged_path in cochange.get(fi.rel_path, []):
        co_stem = Path(cochanged_path).stem
        if co_stem != stem and cochanged_path not in seen and co_stem not in _GENERIC_STEMS:
            seen.add(cochanged_path)
            related.append(cochanged_path)

    # 3. Fallback: stem matching sobre imports internos sin resolver
    if not dep_forward:
        stems_by_path = {f.rel_path: Path(f.rel_path).stem for f in all_files}
        for imp in fi.imports_internal:
            imp_stem = imp.rstrip("/").replace(".", "/").split("/")[-1]
            if imp_stem and imp_stem != stem and imp_stem not in seen:
                if any(s == imp_stem for s in stems_by_path.values()):
                    seen.add(imp_stem)
                    related.append(imp_stem)

    return related[:6]

def find_test_file(rel_path: str, all_files: list[FileInfo]) -> str | None:
    """
    Busca el archivo de test asociado a rel_path dentro de all_files.
    Heurística en cascada — nunca inventa rutas, solo devuelve paths que existen en all_files.
    """
    stem = Path(rel_path).stem
    dir_ = str(Path(rel_path).parent)
    all_paths = {f.rel_path for f in all_files}

    # Excluir el propio archivo (evita que test files se apunten a sí mismos)
    if stem.startswith("test_") or stem.endswith("_test"):
        return None

    candidates = [
        f"tests/test_{stem}.py",
        f"tests/{stem}_test.py",
        f"{dir_}/tests/test_{stem}.py",
        f"{dir_}/tests/{stem}_test.py",
    ]
    for c in candidates:
        if c in all_paths:
            return c

    # Fallback: cualquier archivo cuyo stem contiene "test" + stem del archivo
    for f in all_files:
        f_stem = Path(f.rel_path).stem
        if ("test" in f_stem.lower()) and (stem.lower() in f_stem.lower()):
            return f.rel_path

    return None

# Roles que deben tener tests (si no los tienen, se reporta no_tests)
_LOGIC_ROLES = frozenset({"controller", "service", "data_access"})
# Roles que se excluyen de problemas
_SKIP_ROLES = frozenset({"test", "migration", "seed", "template", "component"})

def detect_problems(files: list[FileInfo]) -> list[dict]:
    """
    Detecta señales de riesgo en el conjunto de archivos.
    Solo evalúa archivos de lógica (excluye tests, migrations, templates).
    """
    # Construir set de stems de archivos de test para detectar no_tests
    test_stems: set[str] = set()
    for fi in files:
        if fi.role == "test" or "test" in Path(fi.rel_path).stem.lower():
            test_stems.add(Path(fi.rel_path).stem.lower())

    problems: list[dict] = []
    for fi in files:
        if fi.role in _SKIP_ROLES:
            continue
        if "test" in Path(fi.rel_path).parts[0].lower() if Path(fi.rel_path).parts else False:
            continue

        # god_object: >400 líneas aproximadas (size / 80) O >15 funciones
        approx_lines = fi.size // 80 if fi.size > 0 else 0
        fn_count = len(fi.functions or [])
        if approx_lines > 400 or fn_count > 15:
            problems.append({
                "file": fi.rel_path,
                "type": "god_object",
                "description": f"{approx_lines} líneas aprox, {fn_count} funciones",
            })
            continue  # no acumular no_tests sobre el mismo archivo

        # no_tests: roles de lógica sin test file asociado
        if fi.role in _LOGIC_ROLES:
            stem = Path(fi.rel_path).stem.lower()
            has_test = (
                f"test_{stem}" in test_stems
                or f"{stem}_test" in test_stems
                or any(stem in ts for ts in test_stems)
            )
            if not has_test:
                problems.append({
                    "file": fi.rel_path,
                    "type": "no_tests",
                    "description": "sin archivo de test asociado",
                })

    return problems


def build_symbols(fi: FileInfo) -> list[dict]:
    """Devuelve lista de {name, line, kind, end_line?} para grep quirúrgico y recorte de contexto."""
    # Indexar por (name, start_line) para encontrar el FunctionInfo que coincide con symbols_with_lines.
    # Evita el bug de line > end_line cuando hay métodos con el mismo nombre en distintas clases.
    fn_by_start: dict[tuple[str, int], "FunctionInfo"] = {}
    fn_any: dict[str, "FunctionInfo"] = {}
    for fn in fi.function_infos:
        fn_by_start[(fn.name, fn.start_line)] = fn
        fn_any[fn.name] = fn  # fallback: última aparición

    result = []
    for name, line in sorted(fi.symbols_with_lines.items(), key=lambda x: x[1]):
        kind = "class" if name in fi.classes else "function"
        entry: dict = {"name": name, "line": line, "kind": kind}
        fn = fn_by_start.get((name, line)) or fn_any.get(name)
        if fn:
            end_ln = max(fn.end_line, line)  # garantiza end_line >= line
            entry["end_line"] = end_ln
        result.append(entry)
    return result[:10]


def build_module_entry(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
    dep_forward: dict[str, list[str]] | None = None,
) -> dict:
    """Construye el objeto enriquecido para un módulo de análisis."""
    return {
        "path":            fi.rel_path,
        "purpose":         infer_purpose(fi),
        "search_keywords": extract_keywords(fi),
        "related_to":      find_related(fi, all_files, cochange, dep_forward),
        "symbols":         build_symbols(fi),
        "test_file":       find_test_file(fi.rel_path, all_files),
    }

def build_query_entry(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
) -> dict:
    """Objeto mínimo legible para resumir un archivo con queries."""
    return {
        "path":           fi.rel_path,
        "role":           fi.role,
        "functions":      (fi.functions or fi.exports)[:10],
        "query_examples": fi.query_examples[:3],
        "test_file":      find_test_file(fi.rel_path, all_files),
    }


def resolve_dependencies(files: list[FileInfo]) -> dict:
    """
    Construye grafo de dependencias bidireccional:
    {"forward": {file: [dep_paths]}, "reverse": {file: [dependent_paths]}}

    Estrategias de resolución (orden descendente de precisión):
    1. Ruta completa sin extensión  → by_full_no_ext
    2. Claves multi-segmento (2-4)  → by_segments
    3. Directorio index (index/__init__) → by_index
    4. Stem (último segmento)       → by_stem
    """
    # ── Construir índices ──────────────────────────────────────────────────────
    by_stem:         dict[str, str] = {}   # "views" → rel_path
    by_segments:     dict[str, str] = {}   # "auth/views" → rel_path
    by_full_no_ext:  dict[str, str] = {}   # "src/auth/views" → rel_path
    by_index:        dict[str, str] = {}   # "src/auth" → "src/auth/index.ts"

    for f in files:
        p = Path(f.rel_path)
        # Ruta completa sin extensión (lowercase, forward slashes)
        no_ext = str(p.with_suffix("")).lower().replace("\\", "/")
        by_full_no_ext[no_ext] = f.rel_path

        stem = p.stem.lower()
        if stem not in by_stem:
            by_stem[stem] = f.rel_path

        # Multi-segmento: keys de 2 a 4 componentes del path sin extensión
        parts = p.with_suffix("").parts
        for n in range(2, min(len(parts) + 1, 5)):
            key = "/".join(parts[-n:]).lower()
            if key not in by_segments:
                by_segments[key] = f.rel_path

        # Index files: __init__.py / index.ts / index.js
        if stem in ("__init__", "index"):
            dir_key = str(p.parent).lower().replace("\\", "/")
            if dir_key not in by_index:
                by_index[dir_key] = f.rel_path

    # ── Resolvers por lenguaje ─────────────────────────────────────────────────

    def _lookup(parts_list: list[str]) -> str | None:
        """Intenta resolver una lista de segmentos usando los índices, de más específico a menos."""
        if not parts_list:
            return None
        # 1. Ruta completa normalizada
        full_key = "/".join(p.lower() for p in parts_list)
        if full_key in by_full_no_ext:
            return by_full_no_ext[full_key]
        # 2. Multi-segmento (decreciente)
        for n in range(min(len(parts_list), 4), 1, -1):
            key = "/".join(p.lower() for p in parts_list[-n:])
            if key in by_segments:
                return by_segments[key]
        # 3. Index del directorio
        dir_key = "/".join(p.lower() for p in parts_list)
        if dir_key in by_index:
            return by_index[dir_key]
        # 4. Stem del último segmento
        last_stem = Path(parts_list[-1]).stem.lower()
        if last_stem and last_stem not in ("index", "__init__") and last_stem in by_stem:
            return by_stem[last_stem]
        return None

    def resolve_python(imp: str, file_path: str) -> str | None:
        p_file = Path(file_path)
        if imp.startswith("."):
            # Import relativo: ".module", "..pkg.module"
            level = len(imp) - len(imp.lstrip("."))
            module_part = imp.lstrip(".")
            base = p_file.parent
            for _ in range(level - 1):
                base = base.parent
            if not module_part:
                # "from . import X" → __init__.py del directorio actual
                dir_key = str(base).lower().replace("\\", "/")
                return by_index.get(dir_key)
            module_path = module_part.replace(".", "/")
            target_parts = list(base.parts) + module_path.split("/")
            return _lookup(target_parts)
        else:
            # Import absoluto interno: "myapp.auth.views"
            parts_list = imp.split(".")
            return _lookup(parts_list)

    def resolve_js(imp: str, file_path: str) -> str | None:
        # Normaliza separadores
        imp_clean = imp.replace("\\", "/")
        file_dir_parts = file_path.replace("\\", "/").split("/")[:-1]

        # Resuelve el path relativo manualmente (sin acceso al filesystem real)
        out: list[str] = list(file_dir_parts)
        for segment in imp_clean.split("/"):
            if segment in ("", "."):
                continue
            elif segment == "..":
                if out:
                    out.pop()
            else:
                out.append(segment)

        if not out:
            return None

        # Elimina extensión si el último segmento ya la trae
        last = out[-1]
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            if last.lower().endswith(ext):
                out[-1] = last[: -len(ext)]
                break

        return _lookup(out)

    # ── Construir grafo forward ────────────────────────────────────────────────
    forward: dict[str, list[str]] = {}

    for f in files:
        seen: set[str] = set()
        for imp in f.imports_internal:
            resolved = (
                resolve_python(imp, f.rel_path)
                if f.language == "python"
                else resolve_js(imp, f.rel_path)
            )
            if resolved and resolved != f.rel_path and resolved not in seen:
                seen.add(resolved)
        if seen:
            forward[f.rel_path] = sorted(seen)

    # ── Construir grafo reverse ────────────────────────────────────────────────
    reverse: dict[str, list[str]] = {}
    for src, deps in forward.items():
        for dep in deps:
            reverse.setdefault(dep, [])
            if src not in reverse[dep]:
                reverse[dep].append(src)
    for k in reverse:
        reverse[k].sort()

    return {"forward": forward, "reverse": reverse}

# ─── Validación de calidad del análisis ───────────────────────────────────────

def detect_dependency_cycles(deps: dict) -> list[list[str]]:
    """Acepta tanto el grafo forward plano como el objeto {forward, reverse}."""
    if isinstance(deps, dict) and "forward" in deps:
        deps = deps["forward"]
    """Detecta ciclos en el grafo de dependencias mediante DFS."""
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        in_stack.add(node)
        for neighbor in deps.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path + [neighbor])
            elif neighbor in in_stack and len(cycles) < 5:
                try:
                    idx = path.index(neighbor)
                    cycles.append(path[idx:] + [neighbor])
                except ValueError:
                    cycles.append([neighbor])
        in_stack.discard(node)

    for node in list(deps.keys()):
        if node not in visited:
            dfs(node, [node])

    return cycles


def validate_maps(proj: ProjectSummary, project_map: dict) -> list[dict]:
    """
    Valida coherencia del análisis. Retorna lista de issues con tipo, path y descripción.
    """
    issues: list[dict] = []

    # 1. Archivos referenciados en modules que no existen en disco
    for role, module_list in project_map.get("modules", {}).items():
        for module in module_list:
            fpath = proj.root / module["path"]
            if not fpath.exists():
                issues.append({
                    "type": "missing_file",
                    "path": module["path"],
                    "detail": f"En modules.{role} pero no existe en disco",
                })

    # 2. Módulos sin símbolos en archivos de código no triviales (> 500 bytes)
    for fi in proj.files:
        if (fi.role not in ("other", "test", "template", "migration", "config")
                and fi.language in ("python", "typescript", "javascript")
                and not fi.functions and not fi.classes
                and fi.size > 500):
            issues.append({
                "type": "empty_module",
                "path": fi.rel_path,
                "detail": f"Archivo de {fi.size} bytes sin funciones ni clases detectadas",
            })

    # 3. Ciclos de dependencia
    dep_graph = project_map.get("dependencies", {})
    forward_graph = dep_graph.get("forward", dep_graph) if isinstance(dep_graph, dict) else {}
    cycles = detect_dependency_cycles(forward_graph)
    for cycle in cycles:
        issues.append({
            "type": "dependency_cycle",
            "path": cycle[0],
            "detail": f"Ciclo: {' → '.join(cycle)}",
        })

    # 4. Archivos con imports internos que no resolvieron a ningún archivo conocido
    # Usa el grafo forward: archivos con imports pero sin ninguna resolución exitosa
    resolved_sources = set(forward_graph.keys())
    for fi in proj.files:
        if fi.imports_internal and fi.rel_path not in resolved_sources:
            # Al menos un import no pudo resolverse
            unresolved = [
                imp for imp in fi.imports_internal
                if len(imp.strip().lstrip("./").replace(".", "/").split("/")[-1]) > 3
            ]
            if unresolved:
                issues.append({
                    "type": "broken_import",
                    "path": fi.rel_path,
                    "detail": f"Ningún import interno resolvió: {unresolved[:3]}",
                })

    # Deduplica broken_import (mismo archivo puede tener muchos)
    seen_broken: set[str] = set()
    deduped: list[dict] = []
    for issue in issues:
        key = f"{issue['type']}:{issue['path']}"
        if key not in seen_broken:
            seen_broken.add(key)
            deduped.append(issue)

    return deduped

# ─── API pública para analyzers ───────────────────────────────────────────────

# Cache temporal de modelos — los analyzers que necesiten modelos leen esto
_walk_repo_models_cache: list = []


def walk_repo(root: Path) -> list:
    """Recorre el repo y retorna lista de FileInfo. Llama una sola vez desde el orquestador."""
    global _walk_repo_models_cache
    gitignore_spec = load_gitignore_spec(root)
    source_files = walk_source_files(root, gitignore_spec)
    all_files = []
    all_models = []

    for fpath in source_files:
        lang = SOURCE_EXTS.get(fpath.suffix, "other")
        if lang == "python":
            fi = extract_python(fpath, root)
        elif lang in ("typescript", "javascript", "vue", "svelte"):
            fi = extract_js_ts(fpath, root)
        else:
            rel = str(fpath.relative_to(root))
            fi = FileInfo(rel, lang, classify_role(rel), fpath.stat().st_size)
        all_files.append(fi)
        all_models.extend(fi.__dict__.pop("_models", []))

    # Adjuntar modelos deduplicados
    seen: set = set()
    unique_models = []
    for m in all_models + extract_prisma_models(root):
        if m.name not in seen:
            seen.add(m.name)
            unique_models.append(m)

    _walk_repo_models_cache.clear()
    _walk_repo_models_cache.extend(unique_models)

    return all_files


def git_hotspots(root: Path) -> list:
    """Retorna [(archivo, n_commits)]. Devuelve [] si no hay historial git."""
    hotspots, _ = analyze_git(root)
    return hotspots


def git_cochange(root: Path) -> dict:
    """Retorna {archivo: [archivos_cochangiados]}. Devuelve {} si no hay historial git."""
    _, cochange = analyze_git(root)
    return cochange

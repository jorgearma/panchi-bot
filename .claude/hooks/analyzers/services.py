#!/usr/bin/env python3
"""
analyzers/services.py — Genera DOMAIN_INDEX_services.json.

Candidatos del dominio SERVICES (integraciones externas):
  - "seed"   : archivos que importan SDKs conocidos directamente
  - "review" : archivos que solo leen env vars de credenciales

Cada candidato lleva contracts[] = ["integration:NombreSDK", "env:VAR_NAME", ...]
para que el planner sepa qué credenciales/integraciones no puede romper.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from analyzers.core import FileInfo, detect_stack, git_cochange, resolve_dependencies, walk_repo
from analyzers.domain_index import build_candidate, write_domain_index

# SDK → (nombre display, tipo)
SDK_MAP: dict[str, tuple[str, str]] = {
    "twilio":        ("Twilio", "sms"),
    "vonage":        ("Vonage", "sms"),
    "sinch":         ("Sinch", "sms"),
    "sendgrid":      ("SendGrid", "email"),
    "mailgun":       ("Mailgun", "email"),
    "boto3":         ("AWS S3", "storage"),
    "stripe":        ("Stripe", "payments"),
    "monei":         ("Monei", "payments"),
    "paypalrestsdk": ("PayPal", "payments"),
    "braintree":     ("Braintree", "payments"),
    "google.cloud.storage": ("GCS", "storage"),
    "azure.storage": ("Azure Storage", "storage"),
    "redis":         ("Redis", "cache"),
    "aioredis":      ("Redis (async)", "cache"),
    "memcache":      ("Memcached", "cache"),
    "celery":        ("Celery", "queue"),
    "rq":            ("RQ", "queue"),
    "dramatiq":      ("Dramatiq", "queue"),
    "sentry_sdk":    ("Sentry", "monitoring"),
    "datadog":       ("Datadog", "monitoring"),
    "newrelic":      ("New Relic", "monitoring"),
    "httpx":         ("httpx", "http"),
    "requests":      ("requests", "http"),
}

DISPLAY_TO_SDK: dict[str, tuple[str, str]] = {v[0]: (k, v[1]) for k, v in SDK_MAP.items()}

RE_ENV_VAR = re.compile(
    r'(?:os\.environ\.get|os\.environ|os\.getenv)\s*[\[\(]\s*["\']'
    r'([A-Z][A-Z0-9_]+(?:_KEY|_SECRET|_TOKEN|_URL|_SID|_API|_PASSWORD|_PASS|_AUTH)["\'])',
)


def _sdk_imports(fi: FileInfo) -> list[str]:
    """Devuelve lista de display names de SDKs importados por este archivo."""
    found: list[str] = []
    for imp in fi.imports_external:
        key = imp.lower().replace("-", "_")
        for sdk_key, (sdk_name, _) in SDK_MAP.items():
            if key == sdk_key or key.startswith(sdk_key + "."):
                found.append(sdk_name)
                break
    return found


def _env_vars(fi: FileInfo, root: Path) -> list[str]:
    """Extrae env vars de credenciales del source de este archivo."""
    try:
        src = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [m.group(1).strip("\"'") for m in RE_ENV_VAR.finditer(src)]


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera DOMAIN_INDEX_services.json. Escribe en .claude/maps/. Devuelve el dict."""
    cochange = git_cochange(root)
    prod = [f for f in files if f.role not in ("test", "migration")]
    dep_forward = resolve_dependencies(prod).get("forward", {})

    candidates: list[dict] = []
    seen: set[str] = set()

    # ── 1. Archivos con imports directos de SDK (seeds) ───────────────────────
    for fi in files:
        sdks = _sdk_imports(fi)
        if not sdks:
            continue
        env_vars = _env_vars(fi, root)
        contracts = [f"integration:{s}" for s in sdks] + [f"env:{v}" for v in env_vars]
        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            contracts=contracts,
            open_priority="seed",
            confidence_signals=["has_sdk_import"],
        ))
        seen.add(fi.rel_path)

    # ── 2. Service files sin SDK directo pero con env vars (review) ───────────
    service_path_kws = ("service", "adapter", "provider", "integration", "client")
    for fi in files:
        if fi.rel_path in seen:
            continue
        is_service_file = any(kw in fi.rel_path.lower() for kw in service_path_kws)
        if not is_service_file:
            continue
        env_vars = _env_vars(fi, root)
        if not env_vars:
            continue
        contracts = [f"env:{v}" for v in env_vars]
        candidates.append(build_candidate(
            fi, files, cochange, dep_forward,
            contracts=contracts,
            open_priority="review",
            confidence_signals=["has_env_vars", "is_service_file"],
        ))
        seen.add(fi.rel_path)

    # ── 3. Integraciones detectadas desde stack pero sin archivo propio ────────
    # (solo añadir a contracts del primer candidato existente si ya hay archivos;
    #  si no hay ningún candidato para esa integración, crear candidato vacío no aporta)

    return write_domain_index(root, "services", candidates)


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera DOMAIN_INDEX_services.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd(),
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("DOMAIN_INDEX_services.json generado.")

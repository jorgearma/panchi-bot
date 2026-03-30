#!/usr/bin/env python3
"""
analyzers/domain_index.py — Helper compartido para construir DOMAIN_INDEX_<domain>.json.

Todos los dominios emiten la misma estructura candidates[] usando build_candidate().
Eso hace que el reader sea determinista: siempre sabe qué campos esperar.
"""
from __future__ import annotations

import json
from pathlib import Path

from analyzers.core import (
    FileInfo,
    find_related,
    find_test_file,
    infer_purpose,
)


def build_candidate(
    fi: FileInfo,
    all_files: list[FileInfo],
    cochange: dict[str, list[str]],
    dep_forward: dict[str, list[str]] | None = None,
    contracts: list[str] | None = None,
    open_priority: str = "review",
    confidence_signals: list[str] | None = None,
) -> dict:
    """
    Construye un candidato uniforme para DOMAIN_INDEX_<domain>.json.

    Campos incluidos — solo lo que el reader necesita para decidir qué abrir:
      path, role, purpose      → identidad del archivo
      key_symbols              → nombres de funciones/clases (sin líneas — eso es del planner)
      test_files               → tests asociados
      related_paths            → vecinos por deps o co-change
      contracts                → qué no romper ("POST /route", "model:X", "env:VAR")
      open_priority            → "seed" → files_to_open | "review" → files_to_review
      confidence_signals       → por qué es candidato (informativo)

    NO incluidos:
      symbols[]  — líneas exactas por símbolo: el planner las obtiene con Grep directamente
      keywords[] — ya sirvieron para el routing en ROUTING_MAP; aquí son ruido
    """
    test = find_test_file(fi.rel_path, all_files)
    return {
        "path": fi.rel_path,
        "role": fi.role,
        "purpose": infer_purpose(fi),
        "key_symbols": (fi.functions or fi.exports)[:4],
        "test_files": [test] if test else [],
        "related_paths": find_related(fi, all_files, cochange, dep_forward),
        "contracts": contracts or [],
        "open_priority": open_priority,
        "confidence_signals": confidence_signals or [],
    }


def write_domain_index(root: Path, domain: str, candidates: list[dict]) -> dict:
    """Serializa candidates[] en DOMAIN_INDEX_<domain>.json y devuelve el dict."""
    result: dict = {"domain": domain, "candidates": candidates}
    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / f"DOMAIN_INDEX_{domain}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result

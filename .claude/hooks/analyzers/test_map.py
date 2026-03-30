#!/usr/bin/env python3
"""
analyzers/test_map.py — Genera TEST_MAP.json.

Responde: dado un archivo fuente, ¿qué tests lo cubren?
Y a la inversa: dado un test, ¿qué fuentes prueba?

El reader usa este map para que el planner sepa cómo validar sus cambios
sin abrir manualmente los archivos de test.

Estructura:
  source_to_tests   — {source_path: [test_paths]}
  test_to_sources   — {test_path: [source_paths]}
  fixtures_by_test  — {test_path: [conftest_paths]}
  integration_tests — lista de tests marcados como integración
  smoke_tests       — lista de tests de smoke/sanity
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from analyzers.core import FileInfo, detect_stack, find_test_file, walk_repo

# Patrones que identifican tests de integración y smoke
RE_INTEGRATION = re.compile(r'integration|e2e|end.to.end|functional', re.IGNORECASE)
RE_SMOKE = re.compile(r'smoke|sanity|health', re.IGNORECASE)

# Patrones para detectar imports de fuentes dentro de tests
RE_PYTHON_IMPORT = re.compile(r'^(?:from|import)\s+([\w.]+)', re.MULTILINE)


def _find_conftest_files(test_path: str, all_paths: set[str]) -> list[str]:
    """Devuelve conftest.py accesibles desde test_path (en su dir y padres hasta raíz del test suite)."""
    parts = Path(test_path).parts
    conftests: list[str] = []
    # Sube desde el directorio del test hasta 3 niveles
    for depth in range(1, min(len(parts), 4)):
        ancestor = "/".join(parts[:depth])
        conftest = f"{ancestor}/conftest.py" if ancestor else "conftest.py"
        if conftest in all_paths:
            conftests.append(conftest)
    # También raíz
    if "conftest.py" in all_paths:
        conftests.append("conftest.py")
    return list(dict.fromkeys(conftests))  # dedup preserving order


def _source_stem_from_test(test_path: str) -> str | None:
    """Extrae el stem fuente de un archivo de test. test_foo → foo, foo_test → foo."""
    stem = Path(test_path).stem.lower()
    if stem.startswith("test_"):
        return stem[5:]
    if stem.endswith("_test"):
        return stem[:-5]
    return None


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera TEST_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    all_paths: set[str] = {f.rel_path for f in files}
    by_path: dict[str, FileInfo] = {f.rel_path: f for f in files}

    # Todos los archivos de test: en directorios de test o con nombre test_*
    test_files = [
        f for f in files
        if (
            f.role == "test"
            or any(p.lower() in ("tests", "test", "__tests__", "spec") for p in Path(f.rel_path).parts[:-1])
            or Path(f.rel_path).stem.lower().startswith("test_")
            or Path(f.rel_path).stem.lower().endswith("_test")
        )
    ]
    test_paths = {f.rel_path for f in test_files}
    source_files = [f for f in files if f.rel_path not in test_paths and f.role not in ("migration",)]

    # ── source_to_tests: para cada fuente, encontrar sus tests ────────────────
    source_to_tests: dict[str, list[str]] = {}
    for fi in source_files:
        test = find_test_file(fi.rel_path, files)
        if test:
            source_to_tests[fi.rel_path] = [test]

    # ── test_to_sources: para cada test, inferir sus fuentes ──────────────────
    test_to_sources: dict[str, list[str]] = {}
    for tf in test_files:
        src_stem = _source_stem_from_test(tf.rel_path)
        if not src_stem:
            continue
        # Buscar archivos fuente cuyo stem coincide
        matched: list[str] = [
            f.rel_path for f in source_files
            if Path(f.rel_path).stem.lower() == src_stem
        ]
        # Además, intentar detectar por imports dentro del test
        try:
            src_text = (root / tf.rel_path).read_text(encoding="utf-8", errors="replace")
            for m in RE_PYTHON_IMPORT.finditer(src_text):
                imp = m.group(1).replace(".", "/")
                # Buscar archivos que coincidan con el import path
                for candidate in source_files:
                    no_ext = str(Path(candidate.rel_path).with_suffix("")).lower().replace("\\", "/")
                    if no_ext.endswith(imp.lower()):
                        if candidate.rel_path not in matched:
                            matched.append(candidate.rel_path)
        except OSError:
            pass

        if matched:
            test_to_sources[tf.rel_path] = matched[:6]

    # ── fixtures_by_test ──────────────────────────────────────────────────────
    fixtures_by_test: dict[str, list[str]] = {
        tf.rel_path: _find_conftest_files(tf.rel_path, all_paths)
        for tf in test_files
        if _find_conftest_files(tf.rel_path, all_paths)
    }

    # ── integration_tests y smoke_tests ───────────────────────────────────────
    integration_tests: list[str] = [
        tf.rel_path for tf in test_files
        if RE_INTEGRATION.search(tf.rel_path)
    ]
    smoke_tests: list[str] = [
        tf.rel_path for tf in test_files
        if RE_SMOKE.search(tf.rel_path)
    ]

    result = {
        "source_to_tests": source_to_tests,
        "test_to_sources": test_to_sources,
        "fixtures_by_test": fixtures_by_test,
        "integration_tests": integration_tests,
        "smoke_tests": smoke_tests,
    }

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "TEST_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


# ─── CLI standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera TEST_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd(),
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("TEST_MAP.json generado.")

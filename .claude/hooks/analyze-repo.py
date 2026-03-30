#!/usr/bin/env python3
"""
analyze-repo.py — Orquestador que genera los MAP.json del plugin.

Llama core.walk_repo() UNA SOLA VEZ y delega en cada analyzer.

MAPs generados:
  routing     → ROUTING_MAP.json          (router de dominio, siempre leer primero)
  api         → DOMAIN_INDEX_api.json     (candidatos del dominio API)
  data        → DOMAIN_INDEX_data.json    (candidatos del dominio DATA)
  ui          → DOMAIN_INDEX_ui.json      (candidatos del dominio UI)
  services    → DOMAIN_INDEX_services.json (candidatos de integraciones externas)
  jobs        → DOMAIN_INDEX_jobs.json    (candidatos del dominio JOBS)
  contract    → CONTRACT_MAP.json         (contratos públicos que no se pueden romper)
  test        → TEST_MAP.json             (cobertura de tests por archivo fuente)
  data_model  → DATA_MODEL_MAP.json       (modelos, tablas y capas de persistencia)
  dependency  → DEPENDENCY_MAP.json       (grafo de dependencias bidireccional)

Uso:
    python3 .claude/hooks/analyze-repo.py [--root DIR] [--maps routing,api,...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
HOOKS_DIR  = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

from analyzers import core
from analyzers.routing     import run as run_routing
from analyzers.api         import run as run_api
from analyzers.data        import run as run_data
from analyzers.ui          import run as run_ui
from analyzers.services    import run as run_services
from analyzers.jobs        import run as run_jobs
from analyzers.contract    import run as run_contract
from analyzers.test_map    import run as run_test
from analyzers.data_model  import run as run_data_model
from analyzers.dependency  import run as run_dependency

ANALYZER_MAP = {
    "routing":    run_routing,
    "api":        run_api,
    "data":       run_data,
    "ui":         run_ui,
    "services":   run_services,
    "jobs":       run_jobs,
    "contract":   run_contract,
    "test":       run_test,
    "data_model": run_data_model,
    "dependency": run_dependency,
}

DEFAULT_MAPS = "routing,api,data,ui,services,jobs,contract,test,data_model,dependency"

# Orden de generación: routing siempre primero (otros pueden leerlo),
# dependency al final (necesita todos los archivos procesados).
GEN_ORDER = ["routing", "api", "data", "ui", "services", "jobs", "contract", "test", "data_model", "dependency"]

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera MAP.json para el plugin de Claude.")
    p.add_argument("--root", default=None,
                   help="Raíz del repositorio a analizar (default: directorio que contiene .claude/)")
    p.add_argument("--maps", default=DEFAULT_MAPS,
                   help="MAPs a generar, coma-separados.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.root:
        root = Path(args.root).resolve()
    else:
        cwd = Path.cwd()
        for candidate in [cwd, *cwd.parents]:
            if (candidate / ".claude").exists():
                root = candidate
                break
        else:
            root = PLUGIN_DIR.parent

    maps_to_gen = {m.strip().lower() for m in args.maps.split(",")}
    invalid = maps_to_gen - set(ANALYZER_MAP.keys())
    if invalid:
        print(f"MAPs desconocidos: {', '.join(sorted(invalid))}")
        print(f"Opciones válidas: {', '.join(sorted(ANALYZER_MAP.keys()))}")
        return 1

    print(f"Analizando repositorio: {root}")

    print("  Detectando stack...")
    stack = core.detect_stack(root)

    print("  Escaneando archivos...")
    files = core.walk_repo(root)

    print(f"  Archivos fuente: {len(files)}")
    print(f"  Stack: {len(stack)} paquetes relevantes")

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    for map_name in GEN_ORDER:
        if map_name not in maps_to_gen:
            continue
        output_name = _output_filename(map_name)
        print(f"  Generando {output_name}...")
        ANALYZER_MAP[map_name](root, files, stack)
        print(f"  OK {output_name}")

    print(f"\n  {len(maps_to_gen)} MAP(s) generados correctamente.")
    return 0


def _output_filename(map_name: str) -> str:
    mapping = {
        "routing":    "ROUTING_MAP.json",
        "api":        "DOMAIN_INDEX_api.json",
        "data":       "DOMAIN_INDEX_data.json",
        "ui":         "DOMAIN_INDEX_ui.json",
        "services":   "DOMAIN_INDEX_services.json",
        "jobs":       "DOMAIN_INDEX_jobs.json",
        "contract":   "CONTRACT_MAP.json",
        "test":       "TEST_MAP.json",
        "data_model": "DATA_MODEL_MAP.json",
        "dependency": "DEPENDENCY_MAP.json",
    }
    return mapping.get(map_name, f"{map_name.upper()}_MAP.json")


if __name__ == "__main__":
    sys.exit(main())

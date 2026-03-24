#!/usr/bin/env python3
"""Resetea el estado de runtime para iniciar un nuevo ciclo de ejecucion.

Uso:
    python3 .claude/hooks/recover-cycle.py           # reset completo
    python3 .claude/hooks/recover-cycle.py --keep-plan  # conserva plan.json y reader-context.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
RUNTIME = PLUGIN_DIR / "runtime"

INITIAL_APPROVAL = {
    "status": "pending",
    "approved_by": "",
    "notes": "",
}

INITIAL_DISPATCH = {
    "status": "blocked",
    "approved": False,
    "task": "",
    "selected_agents": [],
    "step_ids": [],
    "reason": "Execution requires a newly approved plan.",
}

INITIAL_BRIEF = {
    "task": "",
    "approval_status": "pending_operator_review",
    "target_agents": [],
    "context_summary": "",
    "files_to_open": [],
    "files_to_review": [],
    "implementation_steps": [
        {
            "id": "pending-brief",
            "owner": "frontend",
            "instruction": "Esperando que writer genere el execution brief definitivo.",
        }
    ],
    "done_criteria": [
        "Writer debe reemplazar este archivo con un execution brief valido antes de ejecutar."
    ],
    "notes": "Plantilla inicial del execution brief.",
    "operator_action": "Esperar generacion del brief y revisar antes de aprobar.",
}

INITIAL_PLAN = {
    "task": "",
    "context_inputs": {
        "selected_readers": [],
        "maps_used": [],
        "files_to_open": [],
        "files_to_review": [],
        "notes": "",
    },
    "steps": [],
    "risks": [],
    "done_criteria": [],
}

INITIAL_REVIEWER_DISPATCH = {
    "status": "blocked",
    "result_available": False,
    "agents_completed": [],
    "reason": "Ciclo reseteado. Ejecutar agentes antes de despachar al reviewer.",
}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def delete_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def main() -> int:
    keep_plan = "--keep-plan" in sys.argv

    write_json(RUNTIME / "operator-approval.json", INITIAL_APPROVAL)
    write_json(RUNTIME / "execution-dispatch.json", INITIAL_DISPATCH)
    write_json(RUNTIME / "execution-brief.json", INITIAL_BRIEF)
    write_json(RUNTIME / "reviewer-dispatch.json", INITIAL_REVIEWER_DISPATCH)

    delete_if_exists(RUNTIME / "result.json")

    brief_md = RUNTIME / "execution-brief.md"
    if brief_md.exists():
        brief_md.unlink()

    if not keep_plan:
        write_json(RUNTIME / "plan.json", INITIAL_PLAN)
        delete_if_exists(RUNTIME / "reader-context.json")
        print("Ciclo reseteado completamente. Listo para nueva peticion.")
    else:
        print("Ciclo reseteado conservando plan.json y reader-context.json.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

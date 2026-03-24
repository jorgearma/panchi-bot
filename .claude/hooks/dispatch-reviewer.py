#!/usr/bin/env python3
"""Genera reviewer-dispatch.json tras la ejecucion de agentes frontend/backend."""

from __future__ import annotations

import json
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
RESULT_PATH = PLUGIN_DIR / "runtime" / "result.json"
DISPATCH_PATH = PLUGIN_DIR / "runtime" / "execution-dispatch.json"
REVIEWER_DISPATCH_PATH = PLUGIN_DIR / "runtime" / "reviewer-dispatch.json"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    if not RESULT_PATH.exists():
        payload = {
            "status": "blocked",
            "result_available": False,
            "agents_completed": [],
            "reason": "result.json no existe. Los agentes ejecutores no han terminado.",
        }
        write_json(REVIEWER_DISPATCH_PATH, payload)
        print("Reviewer dispatch blocked: result.json not found.")
        return 1

    result = load_json(RESULT_PATH)

    if not result:
        payload = {
            "status": "blocked",
            "result_available": False,
            "agents_completed": [],
            "reason": "result.json esta vacio. Ningun agente produjo salida.",
        }
        write_json(REVIEWER_DISPATCH_PATH, payload)
        print("Reviewer dispatch blocked: result.json is empty.")
        return 1

    agents_completed = [agent for agent in ("frontend", "backend") if agent in result]
    agents_partial = [
        agent for agent in agents_completed if result[agent].get("status") == "partial"
    ]
    agents_blocked = [
        agent for agent in agents_completed if result[agent].get("status") == "blocked"
    ]

    notes = []
    if agents_partial:
        notes.append(f"Ejecucion parcial en: {', '.join(agents_partial)}.")
    if agents_blocked:
        notes.append(f"Bloqueados sin salida: {', '.join(agents_blocked)}.")

    payload = {
        "status": "ready",
        "result_available": True,
        "agents_completed": agents_completed,
        "reason": " ".join(notes) if notes else "Ejecucion completada. Revision disponible.",
    }
    write_json(REVIEWER_DISPATCH_PATH, payload)

    print("Reviewer dispatch ready.")
    print(f"Agents completed: {', '.join(agents_completed) if agents_completed else 'none'}")
    if notes:
        print(f"Notes: {' '.join(notes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

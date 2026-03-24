#!/usr/bin/env python3
"""Despacha la ejecucion simple a frontend y backend segun el plan aprobado."""

from __future__ import annotations

import json
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
PLAN_PATH = PLUGIN_DIR / "runtime" / "plan.json"
BRIEF_PATH = PLUGIN_DIR / "runtime" / "execution-brief.json"
APPROVAL_PATH = PLUGIN_DIR / "runtime" / "operator-approval.json"
DISPATCH_PATH = PLUGIN_DIR / "runtime" / "execution-dispatch.json"
ALLOWED_AGENTS = {"frontend", "backend"}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    approval = load_json(APPROVAL_PATH)
    plan = load_json(PLAN_PATH)

    if approval.get("status") != "approved":
        payload = {
            "status": "blocked",
            "approved": False,
            "task": plan.get("task", ""),
            "selected_agents": [],
            "step_ids": [],
            "reason": "Plan is not approved by the operator.",
        }
        write_json(DISPATCH_PATH, payload)
        print("Execution blocked: plan is not approved.")
        return 1

    if not BRIEF_PATH.exists():
        payload = {
            "status": "blocked",
            "approved": True,
            "task": plan.get("task", ""),
            "selected_agents": [],
            "step_ids": [],
            "reason": "Execution brief is missing. Run writer before dispatching execution.",
        }
        write_json(DISPATCH_PATH, payload)
        print("Execution blocked: execution brief is missing.")
        return 1

    if not plan.get("task"):
        payload = {
            "status": "blocked",
            "approved": True,
            "task": "",
            "selected_agents": [],
            "step_ids": [],
            "reason": "Plan does not define a task.",
        }
        write_json(DISPATCH_PATH, payload)
        print("Execution blocked: plan does not define a task.")
        return 1

    selected_agents: list[str] = []
    step_ids: list[str] = []

    for step in plan.get("steps", []):
        owner = step.get("owner")
        if owner in ALLOWED_AGENTS:
            if owner not in selected_agents:
                selected_agents.append(owner)
            step_id = step.get("id")
            if step_id:
                step_ids.append(step_id)

    if not selected_agents:
        payload = {
            "status": "blocked",
            "approved": True,
            "task": plan.get("task", ""),
            "selected_agents": [],
            "step_ids": [],
            "reason": "Plan has no executable frontend or backend steps.",
        }
        write_json(DISPATCH_PATH, payload)
        print("Execution blocked: no frontend/backend steps found.")
        return 1

    payload = {
        "status": "ready",
        "approved": True,
        "task": plan.get("task", ""),
        "selected_agents": selected_agents,
        "step_ids": step_ids,
        "reason": "Execution can proceed for the selected specialized agents.",
    }
    write_json(DISPATCH_PATH, payload)

    print("Execution ready")
    print(f"Selected agents: {', '.join(selected_agents) if selected_agents else 'none'}")
    print(f"Step ids: {', '.join(step_ids) if step_ids else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

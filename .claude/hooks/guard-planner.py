#!/usr/bin/env python3
"""PreToolUse hook — restringe al planner a los archivos autorizados por el reader.

Lee runtime/planner-allowlist.json (generado por planner-only.py) y:
  1. Bloquea Read/Grep a paths no autorizados
  2. Bloquea Read duplicados (mismo archivo leído dos veces)
  3. Solo permite Write a plan.json

Protocolo de hooks PreToolUse (Claude Code):
  - Recibe JSON por stdin con {tool_name, tool_input, ...}
  - Responde JSON por stdout con hookSpecificOutput.permissionDecision
  - "allow" → deja pasar, "deny" → bloquea con razón
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PLUGIN_DIR.parent
RUNTIME = PLUGIN_DIR / "runtime"
ALLOWLIST_FILE = RUNTIME / "planner-allowlist.json"
READS_LOG = RUNTIME / "planner-reads.log"


def allow():
	"""Permite la tool call."""
	print(json.dumps({"hookSpecificOutput": {
		"hookEventName": "PreToolUse",
		"permissionDecision": "allow",
	}}))
	sys.exit(0)


def deny(reason: str):
	"""Bloquea la tool call con razón visible para Claude."""
	print(json.dumps({"hookSpecificOutput": {
		"hookEventName": "PreToolUse",
		"permissionDecision": "deny",
		"permissionDecisionReason": reason,
	}}))
	sys.exit(0)


# Solo se activa si existe el allowlist (planner-only.py lo crea antes de lanzar claude)
if not ALLOWLIST_FILE.exists():
	allow()

try:
	hook_input = json.loads(sys.stdin.read())
except (json.JSONDecodeError, EOFError):
	allow()

tool_name = hook_input.get("tool_name", "")
tool_input = hook_input.get("tool_input", {})

# Solo nos interesan Read, Grep, Write y Glob
if tool_name not in ("Read", "Grep", "Write", "Glob"):
	allow()

# Cargar allowlist
try:
	allowlist = json.loads(ALLOWLIST_FILE.read_text(encoding="utf-8"))
except (json.JSONDecodeError, OSError):
	allow()

allowed_paths: set[str] = set(allowlist.get("allowed_paths", []))
plan_output: str = allowlist.get("plan_output", "")


# ── Resolver el path que Claude quiere usar ──────────────────────────────────

def resolve_target(tool: str, inp: dict) -> str | None:
	"""Extrae y normaliza el path objetivo de la tool call."""
	if tool in ("Write", "Read"):
		raw = inp.get("file_path", "")
	elif tool == "Grep":
		raw = inp.get("path", "")
		if not raw:
			return "__PROJECT_WIDE__"
	elif tool == "Glob":
		raw = inp.get("path", "")
		if not raw:
			return "__PROJECT_WIDE__"
	else:
		return None

	if not raw:
		return None

	# Convertir absoluto a relativo respecto al proyecto
	try:
		p = Path(raw).resolve()
		return str(p.relative_to(PROJECT_ROOT))
	except (ValueError, OSError):
		return raw


target = resolve_target(tool_name, tool_input)

if not target:
	allow()

# ── Write: solo permitir plan.json ────────────────────────────────────────────

if tool_name == "Write":
	if target == plan_output:
		allow()
	deny(f"Write a '{target}' no permitido. Solo puedes escribir '{plan_output}'.")

# ── Glob: no permitir escaneo de proyecto completo ────────────────────────────

if tool_name == "Glob":
	if target == "__PROJECT_WIDE__":
		deny("Glob sin path específico. Solo puedes buscar dentro de los archivos autorizados.")
	# Glob a un directorio que contiene archivos permitidos → ok
	allow()

# ── Grep sin path → escaneo de proyecto completo ─────────────────────────────

if target == "__PROJECT_WIDE__":
	deny("Grep sin path específico. Usa Grep solo en archivos autorizados.")

# ── Read/Grep: verificar contra allowlist ─────────────────────────────────────

if target not in allowed_paths:
	deny(
		f"'{target}' no está en la lista de archivos autorizados por el reader. "
		f"Archivos permitidos: {', '.join(sorted(allowed_paths))}"
	)

# ── Read: permitir hasta 3 relecturas (límite para evitar loops) ──────────────

if tool_name == "Read":
	MAX_READS = 3
	read_count: dict[str, int] = {}
	if READS_LOG.exists():
		try:
			lines = READS_LOG.read_text(encoding="utf-8").splitlines()
			for line in lines:
				read_count[line] = read_count.get(line, 0) + 1
		except OSError:
			pass

	if target in read_count and read_count[target] >= MAX_READS:
		deny(
			f"'{target}' ya fue leído {MAX_READS} veces. "
			"Usa la información que obtuviste en las lecturas anteriores o registra en risks si necesitas más contexto."
		)

	# Registrar lectura
	try:
		with READS_LOG.open("a", encoding="utf-8") as f:
			f.write(target + "\n")
	except OSError:
		pass

# Todo ok
allow()

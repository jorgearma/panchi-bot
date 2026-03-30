#!/usr/bin/env python3
"""PreToolUse hook — restringe al writer a plan.json (read) y execution-brief (write).

Lee runtime/writer-allowlist.json (generado por writer-only.py) y:
  1. Bloquea Read a paths fuera de plan.json y execution-brief schema
  2. Bloquea Read duplicados (mismo archivo leído dos veces)
  3. Solo permite Write a execution-brief.json y execution-brief.md (una vez cada uno)
  4. Bloquea Edit (debe usar Write)
  5. Bloquea Bash, Glob, Grep — el writer no los necesita

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
ALLOWLIST_FILE = RUNTIME / "writer-allowlist.json"
READS_LOG = RUNTIME / "writer-reads.log"
WRITES_LOG = RUNTIME / "writer-writes.log"


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


# Solo se activa si existe el allowlist (writer-only.py lo crea antes de lanzar claude)
if not ALLOWLIST_FILE.exists():
	allow()

try:
	hook_input = json.loads(sys.stdin.read())
except (json.JSONDecodeError, EOFError):
	allow()

tool_name = hook_input.get("tool_name", "")
tool_input = hook_input.get("tool_input", {})

# ── Bloquear herramientas prohibidas ──────────────────────────────────────────

if tool_name in ("Bash", "Glob", "Grep"):
	deny(
		f"{tool_name} no permitido. El writer solo puede usar Read (plan.json, schema) "
		"y Write (execution-brief.json, execution-brief.md). No explores el repo."
	)

# Solo nos interesan Read, Write y Edit
if tool_name not in ("Read", "Write", "Edit"):
	allow()

# Cargar allowlist
try:
	allowlist = json.loads(ALLOWLIST_FILE.read_text(encoding="utf-8"))
except (json.JSONDecodeError, OSError):
	allow()

allowed_reads: set[str] = set(allowlist.get("allowed_reads", []))
allowed_writes: set[str] = set(allowlist.get("allowed_writes", []))


# ── Resolver el path que Claude quiere usar ──────────────────────────────────

def resolve_target(inp: dict) -> str | None:
	"""Extrae y normaliza el path objetivo de la tool call."""
	raw = inp.get("file_path", "")
	if not raw:
		return None
	try:
		p = Path(raw).resolve()
		return str(p.relative_to(PROJECT_ROOT))
	except (ValueError, OSError):
		return raw


target = resolve_target(tool_input)

if not target:
	allow()

# ── Edit: nunca permitido para el writer ──────────────────────────────────────

if tool_name == "Edit":
	deny(
		"Edit no permitido. Usa Write para crear los archivos de una sola vez. "
		"No edites ni corrijas — genera el contenido completo y correcto en un solo Write."
	)

# ── Write: solo execution-brief.json y .md, una vez cada uno ─────────────────

if tool_name == "Write":
	if target not in allowed_writes:
		deny(f"Write a '{target}' no permitido. Solo puedes escribir: {', '.join(sorted(allowed_writes))}")

	# Verificar si ya escribió este archivo
	already_written: set[str] = set()
	if WRITES_LOG.exists():
		try:
			already_written = set(WRITES_LOG.read_text(encoding="utf-8").splitlines())
		except OSError:
			pass

	if target in already_written:
		deny(
			f"Ya escribiste '{target}'. No lo reescribas ni corrijas. "
			"Si tenía un error, el validador lo detectará después."
		)

	# Registrar escritura
	try:
		with WRITES_LOG.open("a", encoding="utf-8") as f:
			f.write(target + "\n")
	except OSError:
		pass

	allow()

# ── Read: verificar contra allowlist ──────────────────────────────────────────

if target not in allowed_reads:
	deny(
		f"'{target}' no está en la lista de archivos autorizados. "
		f"Solo puedes leer: {', '.join(sorted(allowed_reads))}"
	)

# ── Read: verificar duplicado ────────────────────────────────────────────────

already_read: set[str] = set()
if READS_LOG.exists():
	try:
		already_read = set(READS_LOG.read_text(encoding="utf-8").splitlines())
	except OSError:
		pass

if target in already_read:
	deny(
		f"'{target}' ya fue leído. No leas el mismo archivo dos veces. "
		"Usa la información que ya obtuviste."
	)

# Registrar lectura
try:
	with READS_LOG.open("a", encoding="utf-8") as f:
		f.write(target + "\n")
except OSError:
	pass

# Todo ok
allow()
